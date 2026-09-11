"""Pure offline scene-admission gate for a bridged EGO B-spline (#102/#39 slice).

This module is the narrow, previously missing seam between "a Bspline payload
decoded off the wire" and "the trajectory is allowed to drive the session".  The
existing pieces each stop short of it:

- ``Simulator/wksim_runtime/bspline_tcp_envelope.py`` (BsplineTcpDecoder) only
  guarantees transport fidelity; its contract states downstream admission is
  narrower than envelope validity.
- ``Simulator/wksim_planning/ego_bspline_bridge.py`` (bridge_bspline) converts
  the decoded mapping into an ``(EgoSpline, trajectory_id, start_tick)`` triple
  but performs no scene geometry check.
- ``Simulator/wksim_runtime/planner_scene_binding.py`` (PlannerSceneBinding)
  exposes only point-versus-AABB contact queries, not a swept-trajectory gate.
- ``Simulator/wksim_planning/ego_trajectory_adapter.py`` (EgoTrajectoryAdapter)
  activates any spline it is handed; it has no obstacle/map knowledge.

``TrajectorySceneAdmission`` closes exactly that gap and nothing more: it takes
the decoder's bridge-mapping output, bridges it, checks the resulting EgoSpline
against the committed ``ego-single-box-v1`` obstacle clearance and map envelope,
and only on a pass calls ``EgoTrajectoryAdapter.replan_and_activate`` exactly
once.  Every failure path leaves the adapter, the TrajectorySession, its event
sequence, and its generation untouched.

CRITICAL HONESTY BOUNDARY (read before relying on a PASS):
  The clearance result is computed by sampling the spline on a fixed, explicit,
  bounded time grid (including the exact endpoints t=0 and t=duration) and then
  checking each straight segment between adjacent samples.  It therefore proves
  something about the SAMPLED POLYLINE ONLY.  A cubic B-spline does not in
  general coincide with the chords between its samples, so this is NOT a proof
  that the continuous curve keeps clearance between sample instants.  The
  deterministic 0.010 s grid is the adapter's streaming cadence used as an
  evaluation grid; it is NOT claimed to be a sufficient condition for
  continuous-curve safety.  Every report is labelled ``sampled_segment_checked``
  with ``continuous_proof=False``.  A tighter grid raises sample density but can
  never turn a sampled check into a continuous guarantee.

Non-claims: this module does no force, impulse, UE, SITL, ROS, planner, socket,
or flight work, and it never reads or drives Terrain15D -- the obstacle is a
vertical AABB, not terrain support.  It mints no identifiers and reads no wall
clock.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Mapping, Optional, Tuple

from Simulator.wksim_planning.ego_bspline_bridge import (
    BSPLINE_FIELDS,
    BridgeError,
    bridge_bspline,
)
from Simulator.wksim_planning.ego_evaluator import EgoSpline
from Simulator.wksim_planning.ego_trajectory_adapter import (
    SAMPLE_PERIOD_S,
    AdapterError,
    EgoTrajectoryAdapter,
)
from Simulator.wksim_planning.trajectory_session import Identity, TrajectorySession
from Simulator.wksim_planning.scene_profile import segment_clearance
from Simulator.wksim_runtime.planner_scene_binding import (
    EGO_SINGLE_BOX_BINDING,
    PlannerSceneBinding,
)

# The adapter streams one sample every 10 ms; that cadence is reused here purely
# as a deterministic evaluation grid.  It is NOT a claimed safety bound (see the
# module docstring): the result is a sampled/segment check, never continuous
# proof, whatever the stride.
DEFAULT_SAMPLE_PERIOD_S = SAMPLE_PERIOD_S          # 0.010 s
# Hard fail-closed bound on the grid size so a hostile or degenerate duration /
# stride cannot make admission unbounded.  1e6 samples at 10 ms is ~2.8 h of
# trajectory, far beyond any real replan.
MAX_ADMISSION_SAMPLES = 1_000_000

EVIDENCE_KIND = "sampled_segment_checked"

ADMISSION_REASONS = (
    "invalid_adapter",
    "invalid_binding",
    "invalid_anchor",
    "invalid_grid",
    "invalid_spline",
    "invalid_mapping",
    "identity_mismatch",
    "bridge_rejected",
    "clearance_violation",
    "map_violation",
    "adapter_rejected",
)

NON_CLAIMS = (
    "clearance is proven only for the sampled polyline of straight segments, "
    "not for the continuous B-spline curve between sample instants",
    "the deterministic 0.010 s grid is an evaluation cadence, not a proof that "
    "the stride is sufficient for continuous-curve safety",
    "no force, impulse, UE, SITL, ROS, planner, socket, or flight claim",
    "the obstacle is a vertical AABB; Terrain15D / terrain-height is never read "
    "or driven",
    "no identifier is minted and no wall clock is read",
)


class SceneAdmissionError(ValueError):
    """A stable reason-coded admission rejection raised before any session mutation."""

    def __init__(self, reason: str, message: str = "", *, report: Optional["SceneClearanceReport"] = None,
                 bridge_reason: Optional[str] = None):
        if reason not in ADMISSION_REASONS:
            raise ValueError(f"unknown scene admission error reason: {reason!r}")
        full = f"[{reason}] {message}" if message else reason
        super().__init__(full)
        self.reason = reason
        self.message = message
        self.report = report
        self.bridge_reason = bridge_reason


@dataclass(frozen=True)
class SceneClearanceReport:
    """Honest evidence for one spline assessment.

    ``evidence_kind`` is always ``sampled_segment_checked`` and
    ``continuous_proof`` is always False: the numbers below describe the sampled
    polyline, never the continuous B-spline between samples.
    """

    admitted: bool
    evidence_kind: str
    continuous_proof: bool
    scene_id: str
    scene_hash: str
    geometry_id: str
    profile_hash: str
    vehicle_radius: float
    required_clearance: float
    clearance_margin: float                 # vehicle_radius + required_clearance
    sample_period_s: float
    duration_s: float
    sample_count: int
    segment_count: int
    start_point: Tuple[float, float, float]
    end_point: Tuple[float, float, float]
    min_obstacle_clearance: float           # min segment_clearance over sampled segments
    min_envelope_clearance: float           # min (inward face distance - radius) over samples
    violation: Optional[Mapping[str, Any]]  # first violation (time order), else None
    non_claims: Tuple[str, ...] = NON_CLAIMS


def _sample_period(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value <= 0.0:
        raise SceneAdmissionError("invalid_grid", "sample_period_s must be a positive finite number of seconds")
    return float(value)


def _sample_times(duration: float, step: float) -> list:
    """Deterministic grid 0, step, 2*step, ... < duration, then the exact endpoint.

    The first entry is literally 0.0 and the last is literally ``duration`` (the
    curve domain endpoints), so the exact start and end positions are always
    evaluated.  The endpoint consumes one of the bounded sample slots.  The
    boundary comparison uses the same direct ``n * step`` arithmetic as the
    grid, so adjacent representable durations cannot be misclassified by a
    rounded ``duration / step`` count.
    """
    # The endpoint is always appended after the strict ``n * step < duration``
    # grid.  Therefore `(MAX - 1) * step` is the largest duration boundary that
    # can still produce MAX samples; a duration above it would need at least
    # MAX - 1 interior samples plus the two endpoints.
    if (MAX_ADMISSION_SAMPLES - 1) * step < duration:
        raise SceneAdmissionError(
            "invalid_grid", f"sample grid exceeds {MAX_ADMISSION_SAMPLES} samples")

    times = [0.0]
    n = 1
    while True:
        sample = n * step
        if sample >= duration:
            break
        # Reserve one slot for the literal duration endpoint.  This guard is
        # defensive against any floating-point boundary discrepancy above.
        if len(times) >= MAX_ADMISSION_SAMPLES - 1:
            raise SceneAdmissionError(
                "invalid_grid", f"sample grid exceeds {MAX_ADMISSION_SAMPLES} samples")
        if sample <= times[-1]:
            raise SceneAdmissionError("invalid_grid", "sample grid is not strictly increasing")
        times.append(sample)
        n += 1
    times.append(float(duration))
    if len(times) > MAX_ADMISSION_SAMPLES or times[-2] >= times[-1]:
        raise SceneAdmissionError("invalid_grid", "sample grid is not strictly increasing")
    return times


def _inward_face_distance(point: Tuple[float, float, float], bounds) -> float:
    """Minimum distance from an interior point to any map-boundary face.

    Negative when the point lies outside the map on some axis, so a single
    formula covers both the inside-margin and the outside cases.
    """
    return min(
        min(coordinate - low, high - coordinate)
        for coordinate, low, high in zip(point, bounds.minimum, bounds.maximum)
    )


def assess_spline_clearance(spline: EgoSpline, *, binding: PlannerSceneBinding = EGO_SINGLE_BOX_BINDING,
                            sample_period_s: float = DEFAULT_SAMPLE_PERIOD_S) -> SceneClearanceReport:
    """Assess one EgoSpline against the committed scene; never touches a session.

    Returns a SceneClearanceReport.  Raises SceneAdmissionError only for malformed
    inputs (bad binding, bad grid, non-spline, non-positive duration); a clearance
    or map shortfall is reported via ``report.admitted is False`` + ``violation``,
    not raised, so callers can inspect the honest evidence.
    """
    if not isinstance(binding, PlannerSceneBinding):
        raise SceneAdmissionError("invalid_binding", "binding must be a PlannerSceneBinding")
    step = _sample_period(sample_period_s)
    if not isinstance(spline, EgoSpline):
        raise SceneAdmissionError("invalid_spline", "spline must be an EgoSpline")
    duration = spline.duration
    if isinstance(duration, bool) or not isinstance(duration, Real) or not math.isfinite(duration) or duration <= 0.0:
        raise SceneAdmissionError("invalid_spline", "spline duration must be a positive finite number")
    duration = float(duration)

    profile = binding.profile                       # committed ego-single-box-v1 geometry
    bounds = profile.map_bounds
    vehicle_radius = profile.vehicle_radius
    required_clearance = profile.required_clearance
    margin = vehicle_radius + required_clearance

    times = _sample_times(duration, step)
    min_obstacle = math.inf
    min_envelope = math.inf
    violation: Optional[Mapping[str, Any]] = None
    start_point: Optional[Tuple[float, float, float]] = None
    previous: Optional[Tuple[float, float, float]] = None
    point = start_point
    for index, t in enumerate(times):
        point = tuple(float(c) for c in spline.position_at(t))
        if start_point is None:
            start_point = point
        # Map envelope: every sampled centre must sit at least `margin` inside the
        # map.  The shrunk map is a convex AABB, so if both endpoints of every
        # segment satisfy this, the whole segment does too (exact for the polyline).
        envelope = _inward_face_distance(point, bounds) - vehicle_radius
        if envelope < min_envelope:
            min_envelope = envelope
        if violation is None and envelope < required_clearance:
            violation = {
                "kind": "map_envelope",
                "sample_index": index,
                "time_s": t,
                "clearance": envelope,
                "threshold": required_clearance,
            }
        # Obstacle surface: exact segment<->AABB clearance, net of vehicle radius.
        if previous is not None:
            clearance = segment_clearance(previous, point, profile=profile)
            if clearance < min_obstacle:
                min_obstacle = clearance
            if violation is None and clearance < required_clearance:
                violation = {
                    "kind": "obstacle_clearance",
                    "segment_index": index - 1,
                    "end_time_s": t,
                    "clearance": clearance,
                    "threshold": required_clearance,
                }
        previous = point

    end_point = point
    admitted = violation is None
    return SceneClearanceReport(
        admitted=admitted,
        evidence_kind=EVIDENCE_KIND,
        continuous_proof=False,
        scene_id=binding.scene_id,
        scene_hash=binding.scene_hash,
        geometry_id=binding.geometry_id,
        profile_hash=profile.profile_hash,
        vehicle_radius=vehicle_radius,
        required_clearance=required_clearance,
        clearance_margin=margin,
        sample_period_s=step,
        duration_s=duration,
        sample_count=len(times),
        segment_count=len(times) - 1,
        start_point=start_point,
        end_point=end_point,
        min_obstacle_clearance=min_obstacle,
        min_envelope_clearance=min_envelope,
        violation=violation,
    )


class TrajectorySceneAdmission:
    """Wire decoded Bspline -> bridge -> scene clearance -> atomic adapter activation.

    Constructed against one EgoTrajectoryAdapter (hence one TrajectorySession), one
    committed PlannerSceneBinding, and one fixed authority-clock ``anchor_ns``.  The
    session's stable identity tuple (run_id, mission_id, uav_id, control_epoch) is
    pinned at construction and re-checked on every call BEFORE any geometry or
    adapter work; the generation, event-sequence, and tick monotonicity are enforced
    downstream by the bridge, adapter, and session.
    """

    def __init__(self, adapter: EgoTrajectoryAdapter, *, binding: PlannerSceneBinding = EGO_SINGLE_BOX_BINDING,
                 anchor_ns: int, sample_period_s: float = DEFAULT_SAMPLE_PERIOD_S):
        if not isinstance(adapter, EgoTrajectoryAdapter):
            raise SceneAdmissionError("invalid_adapter", "adapter must be an EgoTrajectoryAdapter")
        if not isinstance(binding, PlannerSceneBinding):
            raise SceneAdmissionError("invalid_binding", "binding must be a PlannerSceneBinding")
        if isinstance(anchor_ns, bool) or type(anchor_ns) is not int or anchor_ns < 0:
            raise SceneAdmissionError("invalid_anchor", "anchor_ns must be a non-negative integer")
        self._adapter = adapter
        self._binding = binding
        self._anchor_ns = anchor_ns
        self._sample_period_s = _sample_period(sample_period_s)
        session_identity = adapter.session.identity      # public, fixed for the session lifetime
        self._identity_tuple = (
            session_identity.run_id,
            session_identity.mission_id,
            session_identity.uav_id,
            session_identity.control_epoch,
        )

    @property
    def anchor_ns(self) -> int:
        return self._anchor_ns

    def _check_identity(self, identity: Any) -> Identity:
        try:
            candidate = Identity.from_value(identity)
        except ValueError as error:
            raise SceneAdmissionError("identity_mismatch", f"invalid identity: {error}") from error
        if (candidate.run_id, candidate.mission_id, candidate.uav_id, candidate.control_epoch) != self._identity_tuple:
            raise SceneAdmissionError(
                "identity_mismatch", "identity stable tuple differs from the pinned session identity")
        return candidate

    def assess(self, spline: EgoSpline) -> SceneClearanceReport:
        return assess_spline_clearance(spline, binding=self._binding, sample_period_s=self._sample_period_s)

    def admit(self, mapping: Mapping[str, Any], *, identity: Any, event_sequence: int,
              current_tick: int, fallback_yaw: float):
        """Admit one decoded Bspline mapping; activate the adapter exactly once on a pass.

        Order is fixed and fail-closed, and NO step mutates the adapter/session on
        failure:
          1. identity stable-tuple gate (admission level),
          2. decode-mapping shape check,
          3. bridge_bspline (payload + authority-clock anchor/grid/past checks),
          4. scene clearance + map envelope over the sampled polyline,
          5. only if admitted: a single adapter.replan_and_activate, which commits
             identity/epoch/tick/generation/trajectory atomically in the session.

        Returns ``(report, trajectory_id)`` on a pass.  Raises SceneAdmissionError
        otherwise; the adapter and session are then guaranteed untouched.
        """
        # 1. identity / epoch gate (before any geometry or adapter work).
        self._check_identity(identity)
        # 2. the input must be the decoder's bridge-mapping output shape.
        if type(mapping) is not dict or set(mapping) != set(BSPLINE_FIELDS):
            raise SceneAdmissionError(
                "invalid_mapping", "mapping must be the decoded Bspline bridge mapping with exact fields")
        # 3. bridge: payload shape + authority timing (anchor/grid/past).  A
        #    BridgeError here never touched the adapter or session.
        try:
            spline, trajectory_id, start_tick = bridge_bspline(
                mapping, anchor_ns=self._anchor_ns, current_tick=current_tick)
        except BridgeError as error:
            raise SceneAdmissionError(
                "bridge_rejected", f"bridge rejected the payload: {error.reason}",
                bridge_reason=error.reason) from error
        # 4. scene geometry gate over the sampled polyline.  On any shortfall the
        #    adapter is NEVER called.
        report = self.assess(spline)
        if not report.admitted:
            reason = "map_violation" if report.violation["kind"] == "map_envelope" else "clearance_violation"
            raise SceneAdmissionError(reason, "scene clearance/map gate failed", report=report)
        # 5. admitted: the single, atomic adapter activation.  The session validates
        #    and commits event-sequence/generation/tick/trajectory in one operation,
        #    so a rejection here still leaves the session unchanged.
        try:
            accepted = self._adapter.replan_and_activate(
                identity, event_sequence, spline, trajectory_id, start_tick, fallback_yaw)
        except (AdapterError, ValueError, OverflowError) as error:
            raise SceneAdmissionError(
                "adapter_rejected", f"adapter/session rejected the activation: {error}", report=report) from error
        return report, accepted
