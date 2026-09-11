"""Offline adapter: an explicitly supplied EGO uniform B-spline -> TrajectorySession.

This is the smallest offline #102 prerequisite slice. It is PURE and DETERMINISTIC:
no ROS, no planner, no point cloud, no SITL/UE/MATLAB, no wall clock. The caller
supplies an EgoSpline payload (built by Simulator/wksim_planning/ego_evaluator.py from
an explicitly supplied traj_utils/Bspline-equivalent, including any lengthened /
non-uniform knot vector exactly as upstream setKnot accepts) and an owning
TrajectorySession (Simulator/wksim_planning/trajectory_session.py). The adapter validates
the payload and drives the session's existing begin_replan / accept_trajectory / sample /
next_output lifecycle on the integer 1 ms authority-tick grid, streaming one sample per
adapter tick exactly as the upstream traj_server evaluates the spline on a 10 ms timer.

Boundary (fail closed, never widened here):
- The adapter does NOT own or mint public request_id; that stays with the public
  command publisher. It only feeds trajectory samples into the session, which alone
  allocates monotonic command_id. No real ROS2 EGO planner is claimed to exist.
- The upstream trajectory_id (Bspline.msg traj_id) is preserved EXPLICITLY by the caller,
  never minted locally. NOTE: Bspline.msg declares traj_id as int64; the uint32 cap here is
  the deliberate narrowing of the #101 TrajectorySession (MAX_COMMAND_ID), NOT the upstream
  field width. It must strictly increase across activations within uint32.
- Activation requires an explicit generation bump, either through begin_replan followed by
  activate or atomically through replan_and_activate, AND an explicit current start_tick: a
  replan can never silently reuse an earlier tick, because a real run's authority tick is
  monotonic and never resets. A payload whose generation is not the session's current
  generation is rejected as a stale replan.
- map == ENU, metres, seconds, radians. There is no implicit coordinate rotation or
  frame conversion; only the ENU 'map' frame is accepted offline.
- Only the real EGO order (3) is accepted, enforced in the evaluator so a lower order can
  never defer a failure to acceleration (second-derivative) evaluation.
- Yaw is NOT evaluated from the trajectory (upstream traj_server only setKnot()s the
  POSITION spline and derives yaw from position/last_yaw/wall clock in calculate_yaw();
  this offline seam has no wall clock). The adapter therefore ALWAYS requires an explicit
  finite fallback yaw at activation and never invents one.
- Identity is validated on EVERY public method before any state change, using the public
  Identity.from_value plus the session's public .identity/.generation; a wrong identity
  fails without feeding a sample, mutating state, or advancing the tick. The adapter never
  calls a session private method or field.
- The adapter holds its OWN last-tick high-water and rejects any non-strictly-increasing
  tick BEFORE evaluating or feeding a sample -- so session.sample can never write a sample
  that next_output would only then reject. A new activation's start_tick must be strictly
  greater than the highest tick already observed.
- Safety is applied BEFORE any evaluation or sample feed: on lost control or stale state
  the adapter never evaluates the spline and never feeds or mutates a session sample.
- Trajectory end and sample expiry fall to HOLD via the session; the adapter never extends
  the last velocity. The adapter never reads the session's private _trajectory.

Evaluation grid: the session consumes integer 1 ms ticks; the upstream evaluation
timer is 10 ms. The adapter therefore advances SAMPLE_STRIDE_TICKS (10) integer ticks
per emitted sample and rejects any sample tick that is off the integer 1 ms grid.
"""
import math
from numbers import Real

from Simulator.wksim_planning.ego_evaluator import EgoSpline
from Simulator.wksim_planning.trajectory_session import (
    MAX_COMMAND_ID,
    Identity,
    TrajectorySession,
)

TICK_NS = 1_000_000                 # 1 ms authority tick
SAMPLE_PERIOD_S = 0.010             # upstream 10 ms evaluation timer
SAMPLE_STRIDE_TICKS = 10            # 10 ms == 10 integer 1 ms ticks
MAX_TICK = 2**63 - 1
# Bspline.msg traj_id is int64 upstream; the uint32 cap below is the #101 TrajectorySession's
# deliberate narrowing (MAX_COMMAND_ID), not the upstream field width.
MAX_TRAJECTORY_ID = MAX_COMMAND_ID


class AdapterError(ValueError):
    """A malformed, mismatched, non-monotonic, stale or overflowing adapter input."""


def _uint(value, name, maximum):
    if isinstance(value, bool) or type(value) is not int or not 0 <= value <= maximum:
        raise AdapterError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _trajectory_id(value):
    value = _uint(value, "trajectory_id", MAX_TRAJECTORY_ID)
    if value == 0:
        raise AdapterError(
            f"trajectory_id must be an integer in [1, {MAX_TRAJECTORY_ID}]"
        )
    return value


def _bool(value, name):
    if type(value) is not bool:
        raise AdapterError(f"{name} must be a bool")
    return value


def tick_to_seconds(tick):
    """Exact integer-tick -> seconds (1 ms per tick)."""
    _uint(tick, "tick", MAX_TICK)
    return tick * TICK_NS / 1_000_000_000.0


def seconds_to_tick(seconds):
    """Seconds -> integer tick; rejects a value that is not an exact 1 ms multiple."""
    if isinstance(seconds, bool) or not isinstance(seconds, Real) or not math.isfinite(seconds):
        raise AdapterError("seconds must be a finite real number")
    tick = seconds * 1_000_000_000.0 / TICK_NS
    rounded = round(tick)
    if abs(tick - rounded) > 1e-9:
        raise AdapterError("time does not land on the 1 ms tick grid")
    return _uint(int(rounded), "tick", MAX_TICK)


def _finite_vector(vec, name):
    if isinstance(vec, (str, bytes)):
        raise AdapterError(f"{name} must be three finite numbers")
    try:
        values = tuple(vec)
    except TypeError as error:
        raise AdapterError(f"{name} must be three finite numbers") from error
    if len(values) != 3:
        raise AdapterError(f"{name} must be three finite numbers")
    for c in values:
        if isinstance(c, bool) or not isinstance(c, Real) or not math.isfinite(c):
            raise AdapterError(f"{name} must be three finite numbers")
    return tuple(float(c) for c in values)


def _finite_scalar(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise AdapterError(f"{name} must be a finite real number")
    return float(value)


class EgoTrajectoryAdapter:
    """One serial adapter bound to a single TrajectorySession (single writer).

    The adapter holds only the active spline, the caller-supplied upstream trajectory_id
    high-water, and its own monotonic tick high-water; all command authority lives in the
    session. Identity and tick monotonicity are checked before any evaluation or feed.
    """

    def __init__(self, session, frame="map"):
        if not isinstance(session, TrajectorySession):
            raise AdapterError("session must be a TrajectorySession")
        if frame != "map":
            # map is the ENU public frame; any other frame would imply a conversion we
            # deliberately do not perform offline.
            raise AdapterError("only the ENU 'map' frame is supported offline")
        self.session = session
        self.frame = frame
        self._trajectory_id_hwm = 0       # caller-supplied upstream traj_id high-water
        self._last_tick = None            # adapter's own monotonic tick high-water
        self._active_spline = None
        self._active_start_tick = None
        self._active_end_tick = None
        self._fallback_yaw = None
        self._next_tick = None            # next stride tick to evaluate/feed

    @property
    def trajectory_id(self):
        """The caller-supplied upstream trajectory_id of the active (or last) activation."""
        return self._trajectory_id_hwm

    def _check_identity(self, identity):
        """Validate the stable identity tuple + current generation via PUBLIC session state.

        Uses Identity.from_value plus session.identity/session.generation; never touches a
        session private member. A mismatch is an AdapterError raised BEFORE any state change.
        """
        try:
            candidate = Identity.from_value(identity)
        except ValueError as error:
            raise AdapterError(f"invalid identity: {error}") from error
        expected = self.session.identity          # public attribute
        if (candidate.run_id, candidate.mission_id, candidate.uav_id, candidate.control_epoch) != (
                expected.run_id, expected.mission_id, expected.uav_id, expected.control_epoch):
            raise AdapterError("identity stable tuple differs from the active session")
        if candidate.planner_generation != self.session.generation:  # public attribute
            raise AdapterError("identity generation differs from the active session")
        return candidate

    def _check_tick(self, tick):
        """Reject any non-strictly-increasing tick BEFORE evaluating or feeding a sample."""
        _uint(tick, "tick", MAX_TICK)
        if self._last_tick is not None and tick <= self._last_tick:
            raise AdapterError("tick must strictly increase across step/next_output calls")

    def begin_replan(self, identity, event_sequence):
        """Explicitly open a new generation (stale-replan isolation lives in the session)."""
        self._check_identity(identity)
        generation = self.session.begin_replan(identity, event_sequence)
        self._active_spline = None
        self._active_start_tick = None
        self._active_end_tick = None
        self._next_tick = None
        return generation

    def activate(self, spline, trajectory_id, start_tick, identity, fallback_yaw):
        """Validate and accept an EGO payload into the session's CURRENT generation.

        ``trajectory_id`` is the upstream Bspline.msg traj_id, preserved explicitly: it must
        strictly increase across activations within uint32 (the #101 session narrowing).
        ``start_tick`` is the current authority tick -- it must be supplied explicitly and
        must be strictly greater than the highest tick already observed (never equal, since
        an equal start would point the feed cursor at an already-consumed tick). ``fallback_yaw`` is a
        mandatory explicit finite scalar (this seam never evaluates a yaw curve). Fails
        closed on a non-EgoSpline payload, a malformed/non-finite spline, a stale or
        overflowing trajectory_id, a stale generation (the session rejects it), a regressed
        start_tick, a non-finite fallback yaw, or a wrong identity. Does NOT allocate or
        touch public command_id. Returns the accepted trajectory_id.
        """
        self._check_identity(identity)
        if not isinstance(spline, EgoSpline):
            raise AdapterError("spline payload must be an EgoSpline")
        trajectory_id = _trajectory_id(trajectory_id)
        start_tick = _uint(start_tick, "start_tick", MAX_TICK)
        fallback_yaw = _finite_scalar(fallback_yaw, "fallback_yaw")
        # The evaluator has already enforced finite knots/control points and order 3. A
        # zero-duration curve cannot be activated.
        if spline.duration <= 0.0:
            raise AdapterError("spline has an empty time domain")
        # A replan must move FORWARD on the monotonic tick grid: the new start_tick must be
        # strictly greater than the highest tick already observed (stepped or queried). An
        # equal start_tick would point _next_tick at a tick already consumed, so the
        # strictly-increasing step() could never feed the first sample.
        if self._last_tick is not None and start_tick <= self._last_tick:
            raise AdapterError("start_tick must be strictly greater than the highest tick already observed")
        # The upstream trajectory_id must strictly increase across activations.
        if trajectory_id <= self._trajectory_id_hwm:
            raise AdapterError("trajectory_id must strictly increase across activations")

        generation = self.session.generation
        end_tick = start_tick + seconds_to_tick(spline.duration)
        if end_tick <= start_tick:
            raise AdapterError("trajectory interval must be non-empty on the tick grid")
        try:
            self.session.accept_trajectory(identity, generation, trajectory_id,
                                           start_tick, end_tick)
        except ValueError as error:
            raise AdapterError(f"trajectory rejected by session: {error}") from error
        self._trajectory_id_hwm = trajectory_id
        self._active_spline = spline
        self._active_start_tick = start_tick
        self._active_end_tick = end_tick
        self._fallback_yaw = fallback_yaw
        self._next_tick = start_tick
        return trajectory_id

    def replan_and_activate(self, identity, event_sequence, spline, trajectory_id,
                            start_tick, fallback_yaw):
        """Validate and atomically replan/accept one trajectory.

        All adapter-owned checks run before the session commit. The session then
        validates and commits its event/generation/trajectory state in one operation;
        the remaining adapter assignments cannot fail.
        """
        self._check_identity(identity)
        if self.session.state in ("CANCELLED", "RELEASED", "FAULTED"):
            raise AdapterError("session is not accepting trajectories")
        if not isinstance(spline, EgoSpline):
            raise AdapterError("spline payload must be an EgoSpline")
        trajectory_id = _trajectory_id(trajectory_id)
        start_tick = _uint(start_tick, "start_tick", MAX_TICK)
        fallback_yaw = _finite_scalar(fallback_yaw, "fallback_yaw")
        duration = _finite_scalar(spline.duration, "spline duration")
        if duration <= 0.0:
            raise AdapterError("spline duration must be positive")
        if self._last_tick is not None and start_tick <= self._last_tick:
            raise AdapterError("start_tick must be strictly greater than the highest tick already observed")
        if trajectory_id <= self._trajectory_id_hwm:
            raise AdapterError("trajectory_id must strictly increase across activations")
        duration_ticks = seconds_to_tick(duration)
        if duration_ticks <= 0:
            raise AdapterError("trajectory interval must be non-empty on the tick grid")
        if duration_ticks > MAX_TICK - start_tick:
            raise AdapterError("trajectory end tick overflows")
        end_tick = start_tick + duration_ticks
        try:
            self.session.replan_and_accept(
                identity, event_sequence, trajectory_id, start_tick, end_tick
            )
        except (ValueError, OverflowError) as error:
            raise AdapterError(f"trajectory replan rejected by session: {error}") from error

        self._trajectory_id_hwm = trajectory_id
        self._active_spline = spline
        self._active_start_tick = start_tick
        self._active_end_tick = end_tick
        self._fallback_yaw = fallback_yaw
        self._next_tick = start_tick
        return trajectory_id

    def _evaluate(self, tick):
        """Evaluate the active spline at a tick, fail closed on non-finite values."""
        spline = self._active_spline
        t = tick_to_seconds(tick - self._active_start_tick)
        position = _finite_vector(spline.position_at(t), "position")
        velocity = _finite_vector(spline.velocity_at(t), "velocity")
        acceleration = _finite_vector(spline.acceleration_at(t), "acceleration")
        return position, velocity, acceleration, self._fallback_yaw

    def step(self, identity, tick, owns_control, state_fresh):
        """Advance one adapter tick: validate identity + tick, apply safety, then stream.

        Identity and tick monotonicity are validated FIRST, before any evaluation, feed, or
        state change. Safety (owns_control / state_fresh) is applied BEFORE any evaluation
        or sample feed: on lost control or stale state the adapter never evaluates the
        spline and never feeds or mutates a session sample -- it only relays the session's
        safety transition. When control is held and state is fresh, the adapter evaluates
        the spline and feeds the session sample for THIS stride tick (valid_until the next
        stride tick, so a missed feed expires to HOLD in the session) and then returns the
        session's single-writer public intent (MOVE/TRAJECTORY, HOLD, or None), so every
        emitted trajectory carries the sample evaluated at its own tick, never a stale one.
        """
        self._check_identity(identity)
        self._check_tick(tick)
        _bool(owns_control, "owns_control")
        _bool(state_fresh, "state_fresh")
        if not (owns_control and state_fresh):
            # Safety first: do NOT evaluate or feed a sample. Relay the session's
            # control-lost / state-stale transition (RELEASED / FAULTED, no sample write).
            # On a successful return the observed tick is still recorded on the high-water,
            # so a repeated or regressed tick is rejected at the adapter layer afterwards.
            intent = self.session.next_output(tick, owns_control, state_fresh)
            self._last_tick = tick
            return intent
        # Control is held and state is fresh: feed this tick's fresh sample, then read.
        if (self._active_spline is not None
                and self.session.state == "ACTIVE"
                and self._next_tick is not None
                and tick == self._next_tick
                and self._active_end_tick is not None
                and tick < self._active_end_tick):
            position, velocity, acceleration, yaw = self._evaluate(tick)
            valid_until = min(tick + SAMPLE_STRIDE_TICKS, self._active_end_tick)
            try:
                self.session.sample(
                    identity, self.session.generation, self._trajectory_id_hwm, tick,
                    position, velocity, acceleration, yaw, valid_until_tick=valid_until)
            except ValueError as error:
                raise AdapterError(f"sample rejected by session at tick {tick}: {error}") from error
            self._next_tick = tick + SAMPLE_STRIDE_TICKS
        intent = self.session.next_output(tick, owns_control, state_fresh)
        self._last_tick = tick
        return intent

    def next_output(self, identity, tick, owns_control, state_fresh):
        """Read the public intent without feeding a new sample (stream-free query).

        Validates identity and tick monotonicity first (this call mutates the session's
        output log), then relays the session intent. Does not feed or evaluate a sample.
        """
        self._check_identity(identity)
        self._check_tick(tick)
        _bool(owns_control, "owns_control")
        _bool(state_fresh, "state_fresh")
        intent = self.session.next_output(tick, owns_control, state_fresh)
        self._last_tick = tick
        return intent

    def cancel(self, identity, event_sequence):
        """Cancel via the session (terminal CANCELLED; late samples are rejected there)."""
        self._check_identity(identity)
        state = self.session.stop("cancel", identity, event_sequence)
        self._active_spline = None
        self._next_tick = None
        return state

    def hold(self, identity, event_sequence, anchor=None):
        """Drive the session to HOLD (no-route/stop), preserving the frozen anchor."""
        self._check_identity(identity)
        state = self.session.stop("no-route", identity, event_sequence, anchor=anchor)
        self._active_spline = None
        self._next_tick = None
        return state
