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

CRITICAL HONESTY BOUNDARY (read before relying on a PASS) -- two distinct modes:

  LEGACY SAMPLED MODE (``strict_continuous=False``; still reachable, still
  honest): the clearance result is computed by sampling the spline on a fixed,
  explicit, bounded time grid (including the exact endpoints t=0 and t=duration)
  and then checking each straight segment between adjacent samples.  It therefore
  proves something about the SAMPLED POLYLINE ONLY.  A cubic B-spline does not in
  general coincide with the chords between its samples, so this is NOT a proof
  that the continuous curve keeps clearance between sample instants.  A report
  from this mode is labelled ``sampled_segment_checked`` with
  ``continuous_proof=False``.  A tighter grid raises sample density but can never
  turn a sampled check into a continuous guarantee.

  STRICT MODE (the default, ``strict_continuous=True``): after the sampled gate,
  the WHOLE CONTINUOUS CURVE is certified from the B-spline convex-hull property
  without sampling it on any grid.  On a knot interval ``[u_k, u_{k+1})`` a
  degree-``p`` B-spline curve is a convex combination of the active control
  points ``P_{k-p}..P_k``, hence inside their axis-aligned bounding box.  The
  certificate tiles the exact clamped domain ``[u_p, u_{m-p}]`` with those
  intervals, and requires, for EVERY interval, that its control-hull AABB is at
  least ``vehicle_radius + required_clearance`` away from the obstacle AABB and
  at least ``vehicle_radius + required_clearance`` INSIDE the map AABB.  Because
  the certificate is a union bound over convex hulls it covers every instant of
  the curve, including the interiors that a finite grid can straddle; a curve
  that passes it is proved clear for the geometric model below.  A curve whose
  control hulls intrude is REJECTED with reason ``continuous_clearance_unproven``
  even when the 10 ms sampled polyline looks clean -- that alternating-control-point
  witness used to be wrongly admitted.
  If the certificate cannot be built at all (malformed internal spline
  structure) it FAILS CLOSED: no PASS is issued.
  What strict mode still does not claim: no dynamics, tracking error, controller
  lag, force/impulse, sensor, planner, or flight safety.  The spatial extent
  behind ``vehicle_radius`` is assumed spherical, and the obstacle is assumed to
  be exactly the committed AABB for the whole trajectory duration.

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
# Evidence kind of a STRICT-mode PASS: the continuous curve was certified from
# the control-point convex hulls on a finite partition of the exact domain, not
# from a time grid.  Existing consumers of "sampled_segment_checked" keep seeing
# that value on every legacy/sampled-only path.
CONTINUOUS_EVIDENCE_KIND = "convex_hull_span_certified"

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
    "continuous_clearance_unproven",
    "adapter_rejected",
)

NON_CLAIMS = (
    "strict mode proves the continuous curve only through the B-spline convex "
    "hull property (control-point AABB per knot interval); the legacy "
    "strict_continuous=False path proves only the sampled polyline of straight "
    "segments, not the continuous curve between sample instants",
    "the deterministic 0.010 s grid is an evaluation cadence, not a proof that "
    "the stride is sufficient for continuous-curve safety",
    "no dynamics, tracking-error, controller-lag, force, impulse, UE, SITL, ROS, "
    "planner, socket, or flight claim",
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
class ContinuousClearanceCertificate:
    """Honest evidence for the continuous-curve (control-hull) certificate.

    ``proven`` is True only when EVERY knot interval of the exact clamped domain
    passed both the obstacle-gap and the map-inset test, i.e. the continuous
    curve is enclosed by certified convex hulls.  When it is False,
    ``structural_reason`` names the fail-closed cause and no clearance claim is
    made: the ``min_*`` fields then carry no proof weight, they are reported for
    diagnosis only.
    """

    proven: bool
    evidence_kind: str
    order: int
    control_point_count: int
    knot_count: int
    interval_count: int
    domain_start_u: float
    domain_end_u: float
    obstacle_hull_gap: float                  # min interval AABB <-> obstacle AABB gap (centreline)
    min_net_obstacle_clearance: float         # obstacle_hull_gap - vehicle_radius
    min_hull_inset_clearance: float           # min interval AABB distance inside the inset map AABB
    required_clearance: float
    vehicle_radius: float
    structural_reason: Optional[str] = None
    intervals: Tuple[Tuple[float, float, int, int], ...] = ()
    non_claims: Tuple[str, ...] = NON_CLAIMS


@dataclass(frozen=True)
class SceneClearanceReport:
    """Honest evidence for one spline assessment.

    ``evidence_kind`` is ``convex_hull_span_certified`` with
    ``continuous_proof=True`` when the strict continuous certificate passed, and
    ``sampled_segment_checked`` with ``continuous_proof=False`` on every
    sampled-only path (legacy mode, or a strict run that failed closed).  The
    sampled numbers always describe the sampled polyline, never the continuous
    B-spline between samples; ``continuous_certificate`` carries the separate
    continuous evidence and is ``None`` outside strict mode.
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
    continuous_certificate: Optional[ContinuousClearanceCertificate] = None


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


def _aabb_gap(low_a, high_a, low_b, high_b) -> float:
    """Exact Euclidean distance between two axis-aligned boxes (0.0 if they overlap).

    Per axis the separation is ``max(0, a_lo - b_hi, b_lo - a_hi)`` and the 3D
    distance is the Euclidean norm of the three separations.  All terms are exact
    real quantities; only the final ``sqrt`` rounds once.
    """
    total = 0.0
    for a_low, a_high, b_low, b_high in zip(low_a, high_a, low_b, high_b):
        separation = max(a_low - b_high, b_low - a_high)
        if separation > 0.0:
            total += separation * separation
    return math.sqrt(total)


def _inset_clearance(low, high, inset_low, inset_high):
    """Per-axis signed clearance of a box from staying inside an inset box.

    Axis ``i`` is ``min(low_i - inset_low_i, inset_high_i - high_i)`` and is
    ``>= 0`` exactly when the box is inside the inset box on that axis.  Returning
    the three axes separately keeps the decision per-axis: a deep intrusion on one
    axis can never be averaged away by a comfortable margin on another.
    """
    return tuple(
        min(lo - face_low, face_high - hi)
        for lo, hi, face_low, face_high in zip(low, high, inset_low, inset_high)
    )


STRUCTURAL_CERTIFICATE_REASON = "certificate_structure_invalid"


def _control_hull_span_certificate(spline: EgoSpline, *,
                                   binding: PlannerSceneBinding) -> ContinuousClearanceCertificate:
    """Conservative continuous-curve clearance certificate (never samples the curve).

    Algorithm (pure, deterministic, no native/ROS/planner work):

    1. Read the bridge/evaluator-owned spline structure: order ``p``, monotone
       knot vector ``u_0..u_m``, control points ``P_0..P_n`` with
       ``len(knots) == n + p + 2``.  Any deviation from those invariants is
       fail-closed: ``proven=False`` with ``structural_reason``.
    2. Walk the knot span indices ``j`` of the evaluation domain
       ``[u_p, u_{m-p}]``.  Any repeated (non-increasing) knot is rejected
       fail-closed as ``non_monotone_knots`` BEFORE this walk, so every
       certified interval is a plain strictly increasing span
       ``[u_j, u_{j+1})`` whose active window ``P_{j-p}..P_j`` contains the
       curve on that span.  (The repeated-knot grouping and degenerate-span
       skip inside the walk are defensive only: the monotonicity gate makes
       them unreachable.)
    3. Require, per interval, ``aabb_gap(control_box, obstacle) - vehicle_radius
       >= required_clearance`` and ``inset_clearance(control_box, map inset)
       >= 0.0``.  The certificate passes only when ALL intervals pass.

    Soundness: a degree-``p`` B-spline on a knot span is a convex combination of
    its active control points, so the curve lies in their convex hull and hence
    in their AABB; a finite, gap-free cover of the domain by such AABBs therefore
    bounds the ENTIRE continuous curve.  Conservatism: the AABB is an outer
    approximation of the hull and the gap-to-obstacle test is a box test, so some
    genuinely safe curves are rejected -- never the reverse.

    Public entry point: ``certify_continuous_clearance``.
    """
    if not isinstance(binding, PlannerSceneBinding):
        raise SceneAdmissionError("invalid_binding", "binding must be a PlannerSceneBinding")
    if not isinstance(spline, EgoSpline):
        raise SceneAdmissionError("invalid_spline", "spline must be an EgoSpline")

    profile = binding.profile
    obstacle = profile.obstacle
    map_bounds = profile.map_bounds
    radius = profile.vehicle_radius
    required = profile.required_clearance
    margin = radius + required
    inset_low = tuple(low + margin for low in map_bounds.minimum)
    inset_high = tuple(high - margin for high in map_bounds.maximum)

    def unproven(reason: str, *, order: int, controls: int, knots: int,
                 start_u: float, end_u: float) -> ContinuousClearanceCertificate:
        return ContinuousClearanceCertificate(
            proven=False,
            evidence_kind=CONTINUOUS_EVIDENCE_KIND,
            order=order,
            control_point_count=controls,
            knot_count=knots,
            interval_count=0,
            domain_start_u=start_u,
            domain_end_u=end_u,
            obstacle_hull_gap=0.0,
            min_net_obstacle_clearance=-math.inf,
            min_hull_inset_clearance=-math.inf,
            required_clearance=required,
            vehicle_radius=radius,
            structural_reason=reason,
        )

    try:
        position = spline.position
        order = position.order
        knots = tuple(position.knots)
        control_points = tuple(position._points)
    except (AttributeError, TypeError) as error:
        raise SceneAdmissionError(
            "invalid_spline", "spline structure is unreadable for the certificate") from error

    knot_count = len(knots)
    control_count = len(control_points)
    if (isinstance(order, bool) or type(order) is not int or order < 1
            or control_count < order + 1
            or knot_count != control_count + order + 1):
        return unproven(STRUCTURAL_CERTIFICATE_REASON, order=order if type(order) is int else 0,
                        controls=control_count, knots=knot_count, start_u=0.0, end_u=0.0)
    for index in range(1, knot_count):
        if not knots[index] > knots[index - 1]:
            return unproven("non_monotone_knots", order=order, controls=control_count,
                            knots=knot_count, start_u=0.0, end_u=0.0)

    start_u = knots[order]
    end_u = knots[control_count]                  # m - p = (n + p + 1) - p = n + 1
    if not end_u > start_u:
        return unproven("degenerate_domain", order=order, controls=control_count,
                        knots=knot_count, start_u=start_u, end_u=end_u)

    intervals = []
    obstacle_low = obstacle.minimum
    obstacle_high = obstacle.maximum
    obstacle_gap = math.inf
    inset_clearance = (math.inf, math.inf, math.inf)
    index = order
    while index <= control_count - 1:             # last span index is m - p - 1 = n
        interval_start = knots[index]
        interval_end = knots[index + 1]
        if interval_end <= interval_start:        # repeated knot: zero-length span
            index += 1
            continue
        last = index
        while last + 1 <= control_count - 1 and knots[last + 1] == interval_start:
            last += 1
        active = control_points[index - order:last + 1]
        low = tuple(min(point[axis] for point in active) for axis in range(3))
        high = tuple(max(point[axis] for point in active) for axis in range(3))
        obstacle_gap = min(obstacle_gap, _aabb_gap(low, high, obstacle_low, obstacle_high))
        inset_clearance = tuple(
            min(current, axis_clearance)
            for current, axis_clearance in zip(inset_clearance,
                                               _inset_clearance(low, high, inset_low, inset_high))
        )
        intervals.append((interval_start, interval_end, index, last))
        index += 1

    if not intervals:
        # No non-degenerate interval can cover a positive-length domain, so the
        # certificate proves nothing: fail closed rather than admit by default.
        return unproven("no_non_degenerate_interval", order=order, controls=control_count,
                        knots=knot_count, start_u=start_u, end_u=end_u)

    net_obstacle = obstacle_gap - radius
    # Per-axis inset decision: EVERY axis must keep the margin, so one axis'
    # intrusion is never traded against another axis' slack.
    proven = (net_obstacle >= required) and all(value >= 0.0 for value in inset_clearance)
    return ContinuousClearanceCertificate(
        proven=proven,
        evidence_kind=CONTINUOUS_EVIDENCE_KIND,
        order=order,
        control_point_count=control_count,
        knot_count=knot_count,
        interval_count=len(intervals),
        domain_start_u=start_u,
        domain_end_u=end_u,
        obstacle_hull_gap=obstacle_gap,
        min_net_obstacle_clearance=net_obstacle,
        min_hull_inset_clearance=min(inset_clearance),
        required_clearance=required,
        vehicle_radius=radius,
        intervals=tuple(intervals),
    )


def certify_continuous_clearance(spline: EgoSpline, *,
                                 binding: PlannerSceneBinding = EGO_SINGLE_BOX_BINDING
                                 ) -> ContinuousClearanceCertificate:
    """Public certificate entry point; see ``_control_hull_span_certificate``.

    Raises SceneAdmissionError only for malformed inputs (bad binding type,
    non-spline); an unprovable or structurally invalid certificate is RETURNED
    with ``proven=False`` so callers decide fail-closed policy.
    """
    return _control_hull_span_certificate(spline, binding=binding)


def _strict_continuous_flag(value: Any) -> bool:
    if type(value) is not bool:
        raise SceneAdmissionError("invalid_grid", "strict_continuous must be a strict bool")
    return value


def assess_spline_clearance(spline: EgoSpline, *, binding: PlannerSceneBinding = EGO_SINGLE_BOX_BINDING,
                            sample_period_s: float = DEFAULT_SAMPLE_PERIOD_S,
                            strict_continuous: bool = True) -> SceneClearanceReport:
    """Assess one EgoSpline against the committed scene; never touches a session.

    Both gates are evaluated on the SAME call so the honest evidence is complete:

    - the sampled polyline gate always runs and always populates
      ``min_obstacle_clearance`` / ``min_envelope_clearance``;
    - with ``strict_continuous=True`` (default) the continuous control-hull
      certificate additionally runs.  The report is admitted only when the
      sampled polyline AND the continuous certificate pass.  A certificate that
      cannot be built or cannot prove clearance makes the report NOT admitted
      (``violation["kind"] == "continuous_clearance_unproven"``), i.e. strict
      mode fails closed.  With ``strict_continuous=False`` the legacy
      sampled-only behaviour is kept verbatim: ``continuous_proof`` stays False,
      ``evidence_kind`` stays ``sampled_segment_checked``, and
      ``continuous_certificate`` stays None.

    Returns a SceneClearanceReport.  Raises SceneAdmissionError only for malformed
    inputs (bad binding, bad grid, non-spline, non-positive duration, non-bool
    mode); a clearance, map, or continuous-certificate shortfall is reported via
    ``report.admitted is False`` + ``violation``, not raised, so callers can
    inspect the honest evidence.
    """
    if not isinstance(binding, PlannerSceneBinding):
        raise SceneAdmissionError("invalid_binding", "binding must be a PlannerSceneBinding")
    step = _sample_period(sample_period_s)
    require_continuous = _strict_continuous_flag(strict_continuous)
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
    # Continuous gate: only reached when the sampled polyline is clean, so a
    # sampled shortfall keeps reporting its own (first-in-time) reason and the
    # certificate only decides the cases sampling cannot see.
    certificate: Optional[ContinuousClearanceCertificate] = None
    if require_continuous:
        certificate = _control_hull_span_certificate(spline, binding=binding)
        if not certificate.proven and violation is None:
            violation = {
                "kind": "continuous_clearance_unproven",
                "structural_reason": certificate.structural_reason,
                "clearance": certificate.min_net_obstacle_clearance,
                "obstacle_hull_gap": certificate.obstacle_hull_gap,
                "envelope_clearance": certificate.min_hull_inset_clearance,
                "threshold": required_clearance,
                "interval_count": certificate.interval_count,
            }

    admitted = violation is None
    # The certified-pass label is conjoined with admission: a strict report the
    # sampled gate rejects must never publish continuous_proof=True even when
    # the certificate itself proves (possible within one ulp of the margin).
    continuous_proof = bool(admitted and certificate is not None and certificate.proven)
    return SceneClearanceReport(
        admitted=admitted,
        evidence_kind=CONTINUOUS_EVIDENCE_KIND if continuous_proof else EVIDENCE_KIND,
        continuous_proof=continuous_proof,
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
        continuous_certificate=certificate,
    )


class TrajectorySceneAdmission:
    """Wire decoded Bspline -> bridge -> scene clearance -> atomic adapter activation.

    Constructed against one EgoTrajectoryAdapter (hence one TrajectorySession), one
    committed PlannerSceneBinding, and one fixed authority-clock ``anchor_ns``.  The
    session's stable identity tuple (run_id, mission_id, uav_id, control_epoch) is
    pinned at construction and re-checked on every call BEFORE any geometry or
    adapter work; the generation, event-sequence, and tick monotonicity are enforced
    downstream by the bridge, adapter, and session.

    ``strict_continuous`` (default True) selects the continuous-certificate gate:
    on a pass the adapter is only activated when the CONTINUOUS curve is certified
    clear (see ``assess_spline_clearance``).  Passing False restores the legacy
    sampled-polyline-only admission for an explicitly opted-in caller.
    """

    def __init__(self, adapter: EgoTrajectoryAdapter, *, binding: PlannerSceneBinding = EGO_SINGLE_BOX_BINDING,
                 anchor_ns: int, sample_period_s: float = DEFAULT_SAMPLE_PERIOD_S,
                 strict_continuous: bool = True):
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
        self._strict_continuous = _strict_continuous_flag(strict_continuous)

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
        return assess_spline_clearance(spline, binding=self._binding, sample_period_s=self._sample_period_s,
                                      strict_continuous=self._strict_continuous)

    def admit(self, mapping: Mapping[str, Any], *, identity: Any, event_sequence: int,
              current_tick: int, fallback_yaw: float):
        """Admit one decoded Bspline mapping; activate the adapter exactly once on a pass.

        Order is fixed and fail-closed, and NO step mutates the adapter/session on
        failure:
          1. identity stable-tuple gate (admission level),
          2. decode-mapping shape check,
          3. bridge_bspline (payload + authority-clock anchor/grid/past checks),
          4. scene gate: the sampled polyline (clearance + map envelope) and, in
             strict mode, the continuous control-hull certificate.  A sampled
             shortfall keeps its existing reason (``clearance_violation`` /
             ``map_violation``); an unprovable continuous certificate fails closed
             as ``continuous_clearance_unproven``,
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
        # 4. scene geometry gate (sampled polyline + strict continuous certificate).
        #    On any shortfall the adapter is NEVER called.
        report = self.assess(spline)
        if not report.admitted:
            kind = report.violation["kind"]
            if kind == "map_envelope":
                reason = "map_violation"
            elif kind == "continuous_clearance_unproven":
                reason = "continuous_clearance_unproven"
            else:
                reason = "clearance_violation"
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
