"""Offline bridge: a normalized Bspline payload -> EgoTrajectoryAdapter activation input.

This is the smallest offline #102 planner-output seam. It converts one explicitly
supplied, already-decoded traj_utils/Bspline-equivalent payload -- a pure Python mapping
with the actual Bspline.msg field names, no ROS import -- into the exact
``(EgoSpline, trajectory_id, start_tick)`` triple that ``EgoTrajectoryAdapter.activate``
consumes. The bridge mints no IDs, owns no generation, and never reads a wall clock.

Repository evidence behind each rule (pinned upstream 5dcd8cfa764d):

- order: producers hardcode 3 (Modules/ego_planner_swarm/plan_manage/src/
  ego_replan_fsm.cpp:1022,1083,1138). UniformBspline derives exactly m+1 = N+p+1 knots
  for N control points and order p (bspline_opt/src/uniform_bspline.cpp:7-44), and the
  consumer's setKnot (uniform_bspline.cpp:44) performs NO validation -- so the
  cardinality check ``len(knots) == len(pos_pts) + 4`` lives here, before EgoSpline's
  numerical validation, which then enforces finite/strictly-increasing content.
- drone_id: the local planning/bspline fill site (ego_replan_fsm.cpp:1021-1063) never
  sets drone_id (wire default 0) and the consumer bsplineCallback
  (plan_manage/src_for_prometheus/traj_server_for_prometheus.cpp:221-254) never reads
  it; routing is topic-scoped (traj_server_for_prometheus.cpp:58-61). The local
  single-vehicle payload therefore requires drone_id == 0 exactly; the vehicle binding
  is carried by the caller's adapter identity, never by this field.
- traj_id: int64 upstream, initialized 0 and incremented before every publish
  (plan_manage/src/planner_manager.cpp:35,631), so wire values are >= 1 and
  process-local monotonic. The uint32 cap is the #101 TrajectorySession narrowing
  (MAX_TRAJECTORY_ID), not the upstream field width. Strict increase across
  activations is re-checked by the adapter high-water; a planner process restart must
  arrive under a new identity, never a reused epoch.
- start_time: the producer stamps its wall clock at plan success
  (planner_manager.cpp:623-625) and the consumer evaluates now - start_time
  (traj_server_for_prometheus.cpp:158,243). Offline there is no wall clock: the caller
  normalizes builtin_interfaces/Time to integer nanoseconds before bridging, and
  supplies anchor_ns/current_tick in the SAME authority clock domain. start_tick =
  (start_time - anchor_ns) / 1 ms must land exactly on the integer 1 ms authority grid
  and must be >= current_tick (the adapter additionally requires it to exceed every
  previously observed tick). The bridge never rounds and never invents an anchor.
- yaw: no producer fills yaw_pts/yaw_dt and the consumer derives yaw from position,
  last_yaw and wall clock (traj_server_for_prometheus.cpp:263-310). A populated yaw
  field therefore means an unreviewed producer: fail closed. The adapter's explicit
  finite fallback yaw stays mandatory and is not handled here.
- frame: Bspline carries no frame field; coordinates are world/map ENU by launch-time
  convention (consumer commands use frame_id="world",
  traj_server_for_prometheus.cpp:196; world->map is an origin/axis-preserving rename
  per docs/plan/39-planner-contract.md). No conversion happens here; the adapter
  accepts only the ENU 'map' frame.

Fail-closed rejection order is fixed and deterministic:
invalid_payload, foreign_drone_id, unsupported_order, knot_cardinality,
invalid_traj_id, yaw_populated, invalid_anchor, start_before_anchor, start_off_grid,
start_overflow, start_in_past, invalid_spline. Deep numerical validation delegates to
EgoSpline, whose SplineError is caught and re-raised as BridgeError("invalid_spline")
(chained), so the public surface is one stable reason-coded BridgeError.
"""
import math
from numbers import Real

from Simulator.wksim_planning.ego_evaluator import EGO_ORDER, EgoSpline, SplineError
from Simulator.wksim_planning.ego_trajectory_adapter import (
    MAX_TICK,
    MAX_TRAJECTORY_ID,
    TICK_NS,
    AdapterError,
)

BSPLINE_FIELDS = ("drone_id", "order", "traj_id", "start_time",
                  "knots", "pos_pts", "yaw_pts", "yaw_dt")
LOCAL_DRONE_ID = 0            # local planning/bspline fill site never sets drone_id
BRIDGE_REASONS = (
    "invalid_payload", "foreign_drone_id", "unsupported_order", "knot_cardinality",
    "invalid_traj_id", "yaw_populated", "invalid_anchor", "start_before_anchor",
    "start_off_grid", "start_overflow", "start_in_past", "invalid_spline",
)


class BridgeError(AdapterError):
    """A stable reason-coded bridge rejection, raised before any session mutation."""

    def __init__(self, reason):
        if reason not in BRIDGE_REASONS:
            raise ValueError("unknown bridge error reason")
        super().__init__(reason)
        self.reason = reason


def _sequence(value):
    # Only bounded containers: consuming an arbitrary iterable (e.g. an unbounded
    # generator) could hang before EgoSpline's MAX_POINTS validation ever runs.
    if type(value) not in (list, tuple):
        raise BridgeError("invalid_payload")
    return value


def _strict_int(value, reason):
    if isinstance(value, bool) or type(value) is not int:
        raise BridgeError(reason)
    return value


def bridge_bspline(payload, *, anchor_ns, current_tick):
    """Convert one normalized Bspline payload into an adapter activation triple.

    ``payload`` is a mapping with exactly the Bspline.msg field names; ``start_time``
    is already normalized to integer nanoseconds by the caller. ``anchor_ns`` and
    ``current_tick`` are explicit nonnegative integers in the same authority clock
    domain; the bridge owns neither. Returns ``(EgoSpline, trajectory_id, start_tick)``.
    Raises only BridgeError (reason-coded, deterministic order); delegated numerical
    validation is exposed as ``invalid_spline`` with SplineError retained as its
    chained cause. Never mutates the payload, never reads a wall clock, and never
    touches a TrajectorySession -- activation admission stays with the adapter.
    """
    # 1. invalid_payload: exact field set, sequence shapes, normalized integer time.
    if type(payload) is not dict or set(payload) != set(BSPLINE_FIELDS):
        raise BridgeError("invalid_payload")
    knots = _sequence(payload["knots"])
    pos_pts = _sequence(payload["pos_pts"])
    yaw_pts = _sequence(payload["yaw_pts"])
    start_time = _strict_int(payload["start_time"], "invalid_payload")
    if start_time < 0:
        raise BridgeError("invalid_payload")
    # 2. foreign_drone_id: the reviewed local producer never sets it (wire 0).
    if _strict_int(payload["drone_id"], "foreign_drone_id") != LOCAL_DRONE_ID:
        raise BridgeError("foreign_drone_id")
    # 3. unsupported_order: only the real EGO order.
    if _strict_int(payload["order"], "unsupported_order") != EGO_ORDER:
        raise BridgeError("unsupported_order")
    # 4. knot_cardinality: the upstream setKnot gap is closed here.
    if len(knots) != len(pos_pts) + EGO_ORDER + 1:
        raise BridgeError("knot_cardinality")
    # 5. invalid_traj_id: wire values are >= 1; uint32 cap is the #101 narrowing.
    traj_id = _strict_int(payload["traj_id"], "invalid_traj_id")
    if not 1 <= traj_id <= MAX_TRAJECTORY_ID:
        raise BridgeError("invalid_traj_id")
    # 6. yaw_populated: no reviewed producer fills yaw; unknown semantics otherwise.
    yaw_dt = payload["yaw_dt"]
    if yaw_pts or (isinstance(yaw_dt, bool) or not isinstance(yaw_dt, Real)
                   or not math.isfinite(yaw_dt) or yaw_dt != 0):
        raise BridgeError("yaw_populated")
    # 7. invalid_anchor: explicit nonnegative integers, one shared clock domain;
    #    current_tick additionally bounded by the adapter's MAX_TICK.
    anchor_ns = _strict_int(anchor_ns, "invalid_anchor")
    current_tick = _strict_int(current_tick, "invalid_anchor")
    if anchor_ns < 0 or current_tick < 0 or current_tick > MAX_TICK:
        raise BridgeError("invalid_anchor")
    # 8. start_before_anchor
    if start_time < anchor_ns:
        raise BridgeError("start_before_anchor")
    # 9. start_off_grid: exact integer 1 ms authority grid, never rounded.
    delta_ns = start_time - anchor_ns
    if delta_ns % TICK_NS:
        raise BridgeError("start_off_grid")
    # 10. start_overflow / 11. start_in_past
    start_tick = delta_ns // TICK_NS
    if start_tick > MAX_TICK:
        raise BridgeError("start_overflow")
    if start_tick < current_tick:
        raise BridgeError("start_in_past")
    # 12. invalid_spline: delegated numerical validation (finite strictly-increasing
    #     knots, finite 3-vector ENU control points, non-empty evaluation domain),
    #     wrapped so the public surface stays one reason-coded BridgeError.
    try:
        spline = EgoSpline(EGO_ORDER, list(knots), list(pos_pts))
    except SplineError as error:
        raise BridgeError("invalid_spline") from error
    return spline, traj_id, start_tick
