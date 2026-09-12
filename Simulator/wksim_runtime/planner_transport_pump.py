"""Pure offline receive-side pump: Bspline TCP bytes -> scene-admitted trajectory (#102/#39).

This module is the smallest missing receive-side seam between the committed
``BsplineTcpDecoder`` (transport) and ``TrajectorySceneAdmission`` (scene gate +
atomic adapter activation).  Nothing upstream owns the loop that turns an arriving
byte stream into admitted trajectories; this pump closes exactly that loop and
nothing more.  It is PURE and DETERMINISTIC: no socket, ROS, DDS, planner, SITL,
UE, MATLAB, native build, or wall clock.  Bytes are supplied explicitly by the
caller; the pump never opens a connection.

TRANSACTION BOUNDARY (read before relying on this pump):
  Transport receipt and session activation are TWO SEPARATE commits with a real
  gap between them, and this pump makes that gap EXPLICIT rather than hiding it:

  1. ``decoder.read_frame()`` (the decoder's PUBLIC API) commits the transport
     sequence high-water and removes the frame from the buffer FIRST.  The pump
     uses only this public API; it never reads or modifies the decoder's private
     buffer, so it cannot and does not interpose admission before the commit.
  2. Only then does the pump run the scene/identity/bridge/adapter admission for
     the decoded mapping.

  Consequently a frame can be transport-consumed yet never activate the session
  (a scene/bridge/identity/adapter rejection).  When the pump returns an outcome,
  it records such a frame as ``transport_consumed=True,
  session_activated=False``: its transport sequence and payload ``trajectory_id``
  are burned, but the pump spends NO ``event_sequence`` (that counter advances
  only on a successful activation or explicit control event). This pump provides NO crash atomicity and NO
  exactly-once guarantee: if the process stops between the two commits, the frame
  and its outcome may be lost from both ledgers.

Poison & recovery (from the committed envelope contract): a frame that fails
transport validation stays at the head of the decoder buffer and blocks it
permanently; recovery REQUIRES a new decoder with a NEW ``transport_session_id``.
  The pump latches a terminal ``POISONED`` state on any transport error, refuses
  further bytes, and only recovers via :meth:`PlannerTransportPump.recover`, which
builds a new decoder (new transport session), a new ``TrajectorySession`` at
``planner_generation + 1`` (preserving ``command_high_water`` so public command
IDs keep increasing across the reconnect), and a fresh admission gate.

The pump admits trajectories and applies explicit hold/cancel events to the
offline session. It never calls ``step``/``next_output``, never produces
a public command output, and never touches a vehicle, UE, or SITL.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional

from Simulator.wksim_runtime.bspline_tcp_envelope import (
    BsplineEnvelopeError,
    BsplineTcpDecoder,
)
from Simulator.wksim_runtime.planner_scene_binding import (
    EGO_SINGLE_BOX_BINDING,
    PlannerSceneBinding,
)
from Simulator.wksim_planning.ego_trajectory_adapter import EgoTrajectoryAdapter
from Simulator.wksim_planning.ego_trajectory_adapter import MAX_TICK
from Simulator.wksim_planning.ego_scene_admission import (
    DEFAULT_SAMPLE_PERIOD_S,
    SceneAdmissionError,
    TrajectorySceneAdmission,
)
from Simulator.wksim_planning.trajectory_session import (
    MAX_COMMAND_ID,
    MAX_GENERATION,
    Identity,
    TrajectorySession,
)

STATE_ACTIVE = "ACTIVE"
STATE_POISONED = "POISONED"

OUTCOME_ACTIVATED = "activated"
OUTCOME_POISON = "poison"

PUMP_REASONS = (
    "invalid_adapter", "invalid_decoder", "invalid_anchor", "invalid_binding",
    "invalid_grid", "invalid_sequence", "invalid_tick", "invalid_chunk",
    "tick_regressed", "poisoned", "invalid_pump", "not_poisoned",
    "session_reuse", "invalid_session_id", "generation_mismatch",
    "sequence_exhausted", "generation_exhausted",
)

# Admission rejection reason -> pump outcome.  All of these happen AFTER
# read_frame() committed the transport sequence, hence transport_consumed=True.
_ADMISSION_REASON_TO_OUTCOME = {
    "identity_mismatch": "rejected_identity",
    "invalid_mapping": "rejected_mapping",
    "bridge_rejected": "rejected_bridge",
    "invalid_grid": "rejected_grid",
    "clearance_violation": "rejected_clearance",
    "map_violation": "rejected_map",
    "adapter_rejected": "rejected_adapter",
}

NON_CLAIMS = (
    "no crash atomicity: a frame consumed by read_frame() but not yet activated "
    "is lost if the process stops",
    "no exactly-once and no transport-delivery guarantee; transport receipt and "
    "session activation are two separate, individually recorded commits",
    "no socket, ROS, DDS, planner, SITL, UE, MATLAB, or native build; pure "
    "in-memory bytes and objects",
    "no wall clock; current_tick is caller-supplied, bounded, and checked for "
    "non-regression",
    "no identifier minting; trajectory_id comes from the payload and "
    "event_sequence is a session-scoped ordering counter spent only on committed activation or control events",
    "no continuous-curve or flight-safety claim; scene clearance inherits the "
    "admission gate's sampled/segment-checked honesty bound",
    "no force, impulse, or Terrain15D; the obstacle is a vertical AABB, not terrain",
    "does not publish or execute control output; it admits trajectories and "
    "applies explicit stop events to the offline session",
)


class PumpError(ValueError):
    """A stable reason-coded pump rejection raised before any state change."""

    def __init__(self, reason: str, message: str = ""):
        if reason not in PUMP_REASONS:
            raise ValueError(f"unknown pump error reason: {reason!r}")
        super().__init__(f"[{reason}] {message}" if message else reason)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class FrameOutcome:
    """One recorded receive/admit decision, making the two-commit boundary explicit."""

    transport_sequence: Optional[int]   # committed transport seq; None if not consumed (poison)
    trajectory_id: Optional[int]        # payload traj_id; None if never decoded
    outcome: str                        # activated | rejected_* | poison
    transport_consumed: bool            # read_frame() committed the transport sequence
    session_activated: bool             # adapter.replan_and_activate committed the session
    event_sequence: Optional[int]       # spent only when session_activated
    detail: str                         # rejection/poison reason ("" when activated)
    report: Optional[Any] = None        # SceneClearanceReport when admission ran


def _strict_int(value: Any, reason: str, name: str, maximum: int) -> int:
    if isinstance(value, bool) or type(value) is not int or not 0 <= value <= maximum:
        raise PumpError(reason, f"{name} must be an integer in [0, {maximum}]")
    return value


def _detail(error: SceneAdmissionError) -> str:
    bridge_reason = getattr(error, "bridge_reason", None)
    return f"{error.reason}:{bridge_reason}" if bridge_reason else error.reason


def _parse_identity(identity: Any):
    """Parse an external identity without leaking Mapping/parser exceptions.

    ``Identity.from_value`` is intentionally strict, but it indexes ``uav_id``
    directly and therefore a malformed or adversarial Mapping may raise
    ``KeyError``/``TypeError`` instead of ``ValueError``.  Only those explicit
    parser/input exceptions are admission-level identity rejection.  Resource
    exhaustion and unrelated implementation exceptions propagate before the
    decoder can mutate.  An explicit integer generation outside the supported
    domain is the one exception to consumed identity rejection: it is a caller
    protocol error and must be rejected before the decoder can mutate.
    """
    raw_generation = None
    if isinstance(identity, Identity):
        raw_generation = identity.planner_generation
    elif isinstance(identity, Mapping):
        try:
            raw_generation = identity.get("planner_generation")
        except (ValueError, KeyError, TypeError):
            raw_generation = None
    try:
        candidate = Identity.from_value(identity)
    except (ValueError, KeyError, TypeError) as error:
        generation_out_of_range = (
            type(raw_generation) is int
            and not 0 <= raw_generation <= MAX_GENERATION
        )
        return None, error, generation_out_of_range
    return candidate, None, False


class PlannerTransportPump:
    """Drive a byte stream through the decoder and scene-admission into the session.

    Owns the admission gate (built from the supplied adapter) and the receive
    ledger.  Single transport session: once POISONED it stays poisoned; recovery
    is a NEW pump via :meth:`recover`.
    """

    def __init__(self, adapter: EgoTrajectoryAdapter, *, decoder: BsplineTcpDecoder,
                 anchor_ns: int, binding: PlannerSceneBinding = EGO_SINGLE_BOX_BINDING,
                 sample_period_s: float = DEFAULT_SAMPLE_PERIOD_S,
                 initial_event_sequence: int = 1, initial_current_tick: int = 0):
        if not isinstance(adapter, EgoTrajectoryAdapter):
            raise PumpError("invalid_adapter", "adapter must be an EgoTrajectoryAdapter")
        if not isinstance(decoder, BsplineTcpDecoder):
            raise PumpError("invalid_decoder", "decoder must be a BsplineTcpDecoder")
        if isinstance(anchor_ns, bool) or type(anchor_ns) is not int or anchor_ns < 0:
            raise PumpError("invalid_anchor", "anchor_ns must be a non-negative integer")
        next_event_sequence = _strict_int(
            initial_event_sequence, "invalid_sequence", "initial_event_sequence", MAX_COMMAND_ID)
        last_event_sequence = adapter.session.last_event_sequence
        if (last_event_sequence is not None
                and next_event_sequence <= last_event_sequence):
            raise PumpError(
                "invalid_sequence",
                "initial_event_sequence must be greater than the session event high-water",
            )
        last_current_tick = _strict_int(
            initial_current_tick, "invalid_tick", "initial_current_tick", MAX_TICK)
        try:
            self._admission = TrajectorySceneAdmission(
                adapter, binding=binding, anchor_ns=anchor_ns, sample_period_s=sample_period_s)
        except SceneAdmissionError as error:
            raise PumpError(error.reason, f"admission construction failed: {error.message}") from error
        self._adapter = adapter
        self._session = adapter.session          # public attribute
        self._decoder = decoder
        self._anchor_ns = anchor_ns
        self._binding = binding
        self._sample_period_s = sample_period_s
        self._next_event_sequence = next_event_sequence
        self._last_current_tick = last_current_tick
        self._event_sequence_exhausted = False
        self._state = STATE_ACTIVE

    # ---- read-only audit properties -------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def next_event_sequence(self) -> int:
        return self._next_event_sequence

    @property
    def last_current_tick(self) -> int:
        return self._last_current_tick

    @property
    def transport_session_id(self) -> str:
        return self._decoder.session_id

    @property
    def session_generation(self) -> int:
        return self._session.generation

    @property
    def command_high_water(self) -> int:
        return self._session.last_command_id

    def _check_feed_identity(self, identity: Any) -> Optional[Identity]:
        """Validate caller generation before touching the decoder.

        A malformed or stable-tuple-mismatched identity remains an admission
        rejection so the transport/admission two-commit boundary is preserved.
        A well-formed stale or future generation is different: it is a caller
        protocol error and must be rejected before decoder mutation.
        """
        candidate, error, generation_out_of_range = _parse_identity(identity)
        if error is not None:
            # A numerically explicit generation outside Identity's domain is
            # still a stale/future caller generation, and must fail before any
            # decoder mutation rather than becoming a consumed identity reject.
            if generation_out_of_range:
                raise PumpError(
                    "generation_mismatch",
                    "caller planner_generation is outside the supported range",
                ) from error
            return None
        if candidate.planner_generation != self._session.generation:
            raise PumpError(
                "generation_mismatch",
                "caller planner_generation must equal the current session generation",
            )
        return candidate

    # ---- control events (hold / cancel) ------------------------------------
    def _spend_event_sequence(self) -> None:
        """Commit the current event sequence exactly like an activation does."""
        if self._next_event_sequence == MAX_COMMAND_ID:
            self._event_sequence_exhausted = True
        else:
            self._next_event_sequence += 1

    def _run_control_event(self, operation: Any, identity: Any, action: str,
                           current_tick: Any) -> str:
        """Route one adapter stop-family call through the pump event allocator.

        The pump owns ``_next_event_sequence``: a direct ``adapter.hold`` /
        ``adapter.cancel`` from a caller would burn the session event
        high-water without advancing the allocator, so the next replan would
        reuse the value and be rejected by the session. Routing here keeps the
        two in lock-step.

        Gates, all evaluated BEFORE any decoder/session/pump mutation:
        poisoned pump, ``current_tick`` validity and non-regression against
        ``last_current_tick`` (same MAX_TICK discipline as ``feed``),
        stale/future caller generation, and an exhausted event-sequence space.
        A malformed or stable-tuple-mismatched identity falls through to the
        adapter, which rejects it before any session mutation (same boundary
        as admission).

        ``TrajectorySession.stop`` is atomic: a rejected call changes NOTHING,
        so the allocator is advanced ONLY after a successful call -- there is
        no compensation or rollback here. The pump's authority-tick ledger is
        updated only on success as well. Adapter/session errors propagate
        unchanged; the adapter's semantics (HOLD via no-route, terminal
        CANCELLED, anchor requirements, generation bump) are reused, never
        re-implemented.
        """
        if self._state != STATE_ACTIVE:
            raise PumpError(
                "poisoned",
                f"cannot {action} while the pump is poisoned; recover with a new transport_session_id")
        current_tick = _strict_int(current_tick, "invalid_tick", "current_tick", MAX_TICK)
        if current_tick < self._last_current_tick:
            raise PumpError(
                "tick_regressed",
                f"cannot {action}: current_tick must not regress below the pump tick high-water")
        candidate = self._check_feed_identity(identity)
        if self._event_sequence_exhausted:
            raise PumpError(
                "sequence_exhausted",
                f"cannot {action}: the event sequence space is exhausted")
        state = operation(candidate, self._next_event_sequence)
        # Success only: the session committed the event.
        self._spend_event_sequence()
        self._last_current_tick = current_tick
        return state

    def hold(self, identity: Any, *, current_tick: Any, anchor: Any = None) -> str:
        """Pump-owned hold (session ``no-route`` -> HOLD) through the allocator.

        No anchor is fabricated here: when the session has no hold anchor, the
        session's own (atomic) rejection applies.
        """
        return self._run_control_event(
            lambda candidate, seq: self._adapter.hold(candidate, seq, anchor=anchor),
            identity, "hold", current_tick)

    def cancel(self, identity: Any, *, current_tick: Any) -> str:
        """Pump-owned cancel (terminal CANCELLED) through the allocator."""
        return self._run_control_event(
            lambda candidate, seq: self._adapter.cancel(candidate, seq),
            identity, "cancel", current_tick)

    # ---- receive loop ----------------------------------------------------
    def feed(self, chunk: Any, *, identity: Any, current_tick: int,
             fallback_yaw: float) -> List[FrameOutcome]:
        """Feed bytes, drain every complete frame in transport order, admit each.

        Returns one FrameOutcome per frame that reached a decision (activated,
        rejected, or poison).  A partial frame yields no outcome until completed.
        Raises PumpError (no state change) for a poisoned pump, a non-bytes chunk,
        an out-of-range/regressed tick, a stale/future caller generation, or an
        exhausted event sequence.  A caller generation that changes after an
        activation leaves later buffered frames for a subsequent feed; the pump
        never rewrites the caller's Identity.
        """
        if self._state == STATE_POISONED:
            raise PumpError("poisoned", "transport is poisoned; recover with a new transport_session_id")
        if not isinstance(chunk, (bytes, bytearray)):
            raise PumpError("invalid_chunk", "chunk must be bytes-like")
        current_tick = _strict_int(current_tick, "invalid_tick", "current_tick", MAX_TICK)
        if current_tick < self._last_current_tick:
            raise PumpError("tick_regressed", "current_tick must not regress across feeds")
        candidate = self._check_feed_identity(identity)
        if self._session.generation >= MAX_GENERATION:
            raise PumpError(
                "generation_exhausted",
                "planner generation is exhausted; no further activation can be admitted",
            )
        if self._event_sequence_exhausted:
            raise PumpError(
                "sequence_exhausted",
                "event sequence is exhausted at MAX_COMMAND_ID; recover cannot reuse it",
            )
        self._last_current_tick = current_tick     # observed authority tick (pump ledger)
        try:
            self._decoder.feed(chunk)
        except BsplineEnvelopeError as error:
            # The peer sent bytes the transport rejects outright (oversized frame,
            # bad leading header, buffer overflow).  The stream is untrustworthy;
            # latch poison.  No frame was consumed and no admission ran.
            self._state = STATE_POISONED
            return [self._poison_outcome(error)]
        outcomes: List[FrameOutcome] = []
        while True:
            # Check again after each activation, before the next public decoder
            # read can consume another transport sequence.
            if candidate is not None and candidate.planner_generation != self._session.generation:
                break
            try:
                mapping = self._decoder.read_frame()   # PUBLIC: commits transport seq FIRST
            except BsplineEnvelopeError as error:
                # A poison frame sits at the head of the buffer and blocks the
                # decoder permanently.  Frames admitted before it stay admitted;
                # everything after it in the buffer is unreachable (head-of-line).
                self._state = STATE_POISONED
                outcomes.append(self._poison_outcome(error))
                break
            if mapping is None:
                break
            outcomes.append(self._admit_frame(mapping, identity, current_tick, fallback_yaw))
        return outcomes

    def _poison_outcome(self, error: BsplineEnvelopeError) -> FrameOutcome:
        return FrameOutcome(
            transport_sequence=None, trajectory_id=None, outcome=OUTCOME_POISON,
            transport_consumed=False, session_activated=False, event_sequence=None,
            detail=getattr(error, "reason", str(error)), report=None)

    def _admit_frame(self, mapping: Any, identity: Any, current_tick: int,
                     fallback_yaw: float) -> FrameOutcome:
        # read_frame() already committed this frame's transport sequence.
        transport_sequence = self._decoder.high_water_sequence
        trajectory_id = mapping["traj_id"]
        candidate, error, _generation_out_of_range = _parse_identity(identity)
        if error is not None:
            return FrameOutcome(
                transport_sequence=transport_sequence, trajectory_id=trajectory_id,
                outcome="rejected_identity", transport_consumed=True, session_activated=False,
                event_sequence=None, detail=str(error), report=None)
        event_sequence = self._next_event_sequence
        try:
            report, accepted = self._admission.admit(
                mapping, identity=candidate, event_sequence=event_sequence,
                current_tick=current_tick, fallback_yaw=fallback_yaw)
        except SceneAdmissionError as error:
            # Transport consumed (read_frame committed) but the session is NOT
            # activated; the transport sequence and trajectory_id are burned, and
            # NO event_sequence is spent.
            return FrameOutcome(
                transport_sequence=transport_sequence, trajectory_id=trajectory_id,
                outcome=_ADMISSION_REASON_TO_OUTCOME.get(error.reason, "rejected_adapter"),
                transport_consumed=True, session_activated=False, event_sequence=None,
                detail=_detail(error), report=error.report)
        # Activated: the session committed.  Only now is the event_sequence spent.
        self._spend_event_sequence()
        return FrameOutcome(
            transport_sequence=transport_sequence, trajectory_id=accepted,
            outcome=OUTCOME_ACTIVATED, transport_consumed=True, session_activated=True,
            event_sequence=event_sequence, detail="", report=report)

    # ---- recovery ----------------------------------------------------------
    @classmethod
    def recover(cls, prior: "PlannerTransportPump", *,
                transport_session_id: str) -> "PlannerTransportPump":
        """Build a NEW pump after a poison: new transport session + new generation.

        The new session shares the stable identity tuple but starts at
        ``planner_generation + 1`` (so a replayed stale frame is rejected by both
        the new transport session and the new generation) and preserves
        ``command_high_water`` (so public command IDs keep increasing across the
        reconnect).  ``event_sequence`` and the tick high-water continue from the
        prior pump; the authority clock does not reset on a transport reconnect.
        """
        if not isinstance(prior, PlannerTransportPump):
            raise PumpError("invalid_pump", "recover requires a prior PlannerTransportPump")
        if prior._state != STATE_POISONED:
            raise PumpError("not_poisoned", "recovery is only defined for a POISONED pump")
        if not isinstance(transport_session_id, str):
            raise PumpError("invalid_session_id", "transport_session_id must be a 32-character lowercase hex string")
        if transport_session_id == prior._decoder.session_id:
            raise PumpError("session_reuse", "recovery requires a NEW transport_session_id")
        old = prior._session
        if old.generation >= MAX_GENERATION:
            raise PumpError("generation_exhausted", "planner generation is exhausted")
        new_identity = {
            "run_id": old.identity.run_id,
            "mission_id": old.identity.mission_id,
            "uav_id": old.identity.uav_id,
            "control_epoch": old.identity.control_epoch,
            "planner_generation": old.generation + 1,
            "command_high_water": old.last_command_id,
        }
        new_session = TrajectorySession(new_identity)
        new_adapter = EgoTrajectoryAdapter(new_session)
        try:
            new_decoder = BsplineTcpDecoder(transport_session_id)
        except BsplineEnvelopeError as error:
            raise PumpError("invalid_session_id", str(error)) from error
        recovered = cls(
            new_adapter, decoder=new_decoder, anchor_ns=prior._anchor_ns,
            binding=prior._binding, sample_period_s=prior._sample_period_s,
            initial_event_sequence=prior._next_event_sequence,
            initial_current_tick=prior._last_current_tick)
        recovered._event_sequence_exhausted = prior._event_sequence_exhausted
        return recovered
