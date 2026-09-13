"""Deterministic offline tests for the #102 Bspline -> adapter bridge slice.

No ROS, no planner, no point cloud, no SITL/UE/MATLAB, no wall clock. The payload is a
pure normalized mapping with the actual Bspline.msg field names; start_time is integer
nanoseconds and the anchor/current tick are explicit caller inputs. The bridge only
produces the (EgoSpline, trajectory_id, start_tick) triple; admission stays with the
adapter/session.
"""
import unittest

from Simulator.wksim_planning.ego_bspline_bridge import (
    BRIDGE_REASONS,
    BridgeError,
    bridge_bspline,
)
from Simulator.wksim_planning.ego_evaluator import EgoSpline, SplineError, UniformBspline
from Simulator.wksim_planning.ego_trajectory_adapter import (
    MAX_TICK,
    MAX_TRAJECTORY_ID,
    AdapterError,
    EgoTrajectoryAdapter,
)
from Simulator.wksim_planning.trajectory_session import TrajectorySession

IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1, control_epoch="epoch-a",
                planner_generation=0, command_high_water=0)


def identity(session):
    value = dict(IDENTITY)
    value["planner_generation"] = session.generation
    return value


def valid_payload(points=7, scale=0.5, start_time=5_000_000, traj_id=1):
    """A normalized local single-vehicle payload on the 1 ms grid (anchor 0)."""
    cps = [(float(i) * scale, 0.0, 1.0) for i in range(points)]
    knots = list(UniformBspline(3, cps, 0.1).knots)
    return dict(drone_id=0, order=3, traj_id=traj_id, start_time=start_time,
                knots=knots, pos_pts=cps, yaw_pts=[], yaw_dt=0.0)


class BridgeTests(unittest.TestCase):
    def assert_reason(self, reason, payload, **kwargs):
        with self.assertRaises(BridgeError) as caught:
            bridge_bspline(payload, **kwargs)
        self.assertEqual(caught.exception.reason, reason)
        return caught.exception

    def test_happy_path_matches_direct_construction(self):
        payload = valid_payload()
        spline, traj_id, start_tick = bridge_bspline(payload, anchor_ns=0, current_tick=0)
        self.assertEqual((traj_id, start_tick), (1, 5))
        direct = EgoSpline(3, list(payload["knots"]), list(payload["pos_pts"]))
        self.assertEqual(spline.position.knots, direct.position.knots)
        self.assertEqual(spline.duration, direct.duration)
        for frac in (0.0, 0.3, 0.65, 1.0):
            t = spline.duration * frac
            self.assertEqual(spline.position_at(t), direct.position_at(t))
            self.assertEqual(spline.velocity_at(t), direct.velocity_at(t))

    def test_nonuniform_lengthened_knots_accepted(self):
        payload = valid_payload(points=6)
        payload["knots"][6] += 0.05                 # upstream lengthenTime moves knots
        spline, _, _ = bridge_bspline(payload, anchor_ns=0, current_tick=0)
        base = EgoSpline(3, None, list(payload["pos_pts"]))
        self.assertGreater(spline.duration, base.duration)

    def test_tuple_sequences_accepted_and_payload_not_mutated(self):
        payload = valid_payload()
        payload["knots"] = tuple(payload["knots"])
        payload["pos_pts"] = tuple(payload["pos_pts"])
        original = dict(payload)
        bridge_bspline(payload, anchor_ns=0, current_tick=0)
        self.assertEqual(payload, original)

    def test_invalid_payload_shape(self):
        for bad in ("not-a-mapping", [1, 2, 3]):
            with self.subTest(bad=bad):
                with self.assertRaises(BridgeError) as caught:
                    bridge_bspline(bad, anchor_ns=0, current_tick=0)
                self.assertEqual(caught.exception.reason, "invalid_payload")
        for mutate in (lambda p: p.pop("knots"), lambda p: p.update(extra=1),
                       lambda p: p.update(knots="0" * 11), lambda p: p.update(pos_pts="abc"),
                       lambda p: p.update(yaw_pts="0"),
                       lambda p: p.update(start_time=True),
                       lambda p: p.update(start_time=5.0),
                       lambda p: p.update(start_time=-1)):
            payload = valid_payload()
            mutate(payload)
            with self.subTest(payload=sorted(payload)):
                self.assert_reason("invalid_payload", payload, anchor_ns=0, current_tick=0)

    def test_unbounded_iterables_are_rejected_without_iteration(self):
        def must_not_iterate():
            raise AssertionError("bridge consumed an arbitrary iterable")
            yield None

        for field in ("knots", "pos_pts", "yaw_pts"):
            payload = valid_payload()
            payload[field] = must_not_iterate()
            with self.subTest(field=field):
                self.assert_reason("invalid_payload", payload, anchor_ns=0, current_tick=0)

    def test_container_subclasses_cannot_override_bounded_iteration(self):
        class HostileList(list):
            def __iter__(self):
                raise AssertionError("bridge iterated a container subclass")

        class HostileDict(dict):
            def __iter__(self):
                raise AssertionError("bridge iterated a mapping subclass")

        payload = valid_payload()
        payload["knots"] = HostileList(payload["knots"])
        self.assert_reason("invalid_payload", payload, anchor_ns=0, current_tick=0)
        self.assert_reason("invalid_payload", HostileDict(valid_payload()),
                           anchor_ns=0, current_tick=0)

    def test_drone_id_must_be_local_zero(self):
        for bad in (1, -1, 2, True, "0"):
            payload = valid_payload()
            payload["drone_id"] = bad
            with self.subTest(bad=bad):
                self.assert_reason("foreign_drone_id", payload, anchor_ns=0, current_tick=0)

    def test_order_must_be_ego_three(self):
        for bad in (0, 2, 4, True, "3"):
            payload = valid_payload()
            payload["order"] = bad
            with self.subTest(bad=bad):
                self.assert_reason("unsupported_order", payload, anchor_ns=0, current_tick=0)

    def test_knot_cardinality_closes_upstream_setknot_gap(self):
        for mutate in (lambda p: p.update(knots=p["knots"][:-1]),
                       lambda p: p.update(knots=p["knots"] + [p["knots"][-1] + 0.1]),
                       lambda p: p.update(knots=[])):
            payload = valid_payload()
            mutate(payload)
            with self.subTest(length=len(payload["knots"])):
                self.assert_reason("knot_cardinality", payload, anchor_ns=0, current_tick=0)

    def test_traj_id_range(self):
        for bad in (0, -1, True, MAX_TRAJECTORY_ID + 1, "1"):
            payload = valid_payload()
            payload["traj_id"] = bad
            with self.subTest(bad=bad):
                self.assert_reason("invalid_traj_id", payload, anchor_ns=0, current_tick=0)
        for good in (1, MAX_TRAJECTORY_ID):
            payload = valid_payload()
            payload["traj_id"] = good
            with self.subTest(good=good):
                _, traj_id, _ = bridge_bspline(payload, anchor_ns=0, current_tick=0)
                self.assertEqual(traj_id, good)

    def test_yaw_must_be_unpopulated(self):
        for mutate in (lambda p: p.update(yaw_pts=[0.0]),
                       lambda p: p.update(yaw_pts=[0.0] * 7),
                       lambda p: p.update(yaw_dt=0.1),
                       lambda p: p.update(yaw_dt=float("nan")),
                       lambda p: p.update(yaw_dt=True),
                       lambda p: p.update(yaw_dt="0")):
            payload = valid_payload()
            mutate(payload)
            with self.subTest(yaw_pts=payload["yaw_pts"], yaw_dt=payload["yaw_dt"]):
                self.assert_reason("yaw_populated", payload, anchor_ns=0, current_tick=0)
        for good in (0, 0.0, -0.0):
            payload = valid_payload()
            payload["yaw_dt"] = good
            with self.subTest(good=good):
                bridge_bspline(payload, anchor_ns=0, current_tick=0)

    def test_anchor_and_current_tick_validation(self):
        for bad in (-1, True, "0", 0.5):
            with self.subTest(anchor=bad):
                self.assert_reason("invalid_anchor", valid_payload(),
                                   anchor_ns=bad, current_tick=0)
            with self.subTest(current_tick=bad):
                self.assert_reason("invalid_anchor", valid_payload(),
                                   anchor_ns=0, current_tick=bad)
        self.assert_reason("invalid_anchor", valid_payload(),
                           anchor_ns=0, current_tick=MAX_TICK + 1)

    def test_start_time_anchor_grid_and_past(self):
        self.assert_reason("start_before_anchor", valid_payload(),
                           anchor_ns=6_000_000, current_tick=0)
        payload = valid_payload()
        payload["start_time"] = 5_000_001          # 1 ns off the 1 ms grid
        self.assert_reason("start_off_grid", payload, anchor_ns=0, current_tick=0)
        payload = valid_payload()
        payload["start_time"] = 4_500_001          # 1 ns off grid from a nonzero anchor
        self.assert_reason("start_off_grid", payload, anchor_ns=500_000, current_tick=0)
        self.assert_reason("start_in_past", valid_payload(), anchor_ns=0, current_tick=6)
        # Boundary: start_tick == current_tick is accepted (contract: >=).
        _, _, start_tick = bridge_bspline(valid_payload(), anchor_ns=0, current_tick=5)
        self.assertEqual(start_tick, 5)

    def test_start_tick_must_fit_the_adapter_domain(self):
        payload = valid_payload()
        payload["start_time"] = MAX_TICK * 1_000_000
        _, _, start_tick = bridge_bspline(payload, anchor_ns=0, current_tick=0)
        self.assertEqual(start_tick, MAX_TICK)

        payload["start_time"] = (MAX_TICK + 1) * 1_000_000
        self.assert_reason("start_overflow", payload, anchor_ns=0, current_tick=0)

    def test_numerical_validation_delegates_to_egospline(self):
        payload = valid_payload()
        payload["knots"][4] = payload["knots"][3]  # duplicate knot, correct length
        error = self.assert_reason("invalid_spline", payload, anchor_ns=0, current_tick=0)
        self.assertIsInstance(error.__cause__, SplineError)
        payload = valid_payload()
        payload["pos_pts"][3] = (0.0, 0.0, float("nan"))
        error = self.assert_reason("invalid_spline", payload, anchor_ns=0, current_tick=0)
        self.assertIsInstance(error.__cause__, SplineError)
        payload = valid_payload()
        payload["pos_pts"][3] = (0.0, 0.0)         # 2-vector position
        error = self.assert_reason("invalid_spline", payload, anchor_ns=0, current_tick=0)
        self.assertIsInstance(error.__cause__, SplineError)

    def test_rejection_order_is_deterministic(self):
        payload = valid_payload()
        payload.update(drone_id=1, order=2)
        self.assert_reason("foreign_drone_id", payload, anchor_ns=0, current_tick=0)
        payload = valid_payload()
        payload.update(order=2, knots=payload["knots"][:-1])
        self.assert_reason("unsupported_order", payload, anchor_ns=0, current_tick=0)
        payload = valid_payload()
        payload.update(knots=payload["knots"][:-1], traj_id=0)
        self.assert_reason("knot_cardinality", payload, anchor_ns=0, current_tick=0)
        payload = valid_payload()
        payload.update(traj_id=0, yaw_pts=[0.0])
        self.assert_reason("invalid_traj_id", payload, anchor_ns=0, current_tick=0)
        payload = valid_payload()
        payload.update(yaw_pts=[0.0])
        self.assert_reason("yaw_populated", payload, anchor_ns=-1, current_tick=0)
        payload = valid_payload()
        payload["start_time"] = 4_500_000          # before anchor AND off grid
        self.assert_reason("start_before_anchor", payload,
                           anchor_ns=6_000_000, current_tick=0)
        payload = valid_payload()
        payload["start_time"] = 5_000_001          # off grid AND in the past
        self.assert_reason("start_off_grid", payload, anchor_ns=0, current_tick=6)

    def test_reason_codes_are_stable_and_bridge_error_is_adapter_error(self):
        self.assertTrue(issubclass(BridgeError, AdapterError))
        for reason in BRIDGE_REASONS:
            self.assertEqual(BridgeError(reason).reason, reason)
        with self.assertRaises(ValueError):
            BridgeError("not-a-reason")


class AdapterIntegrationTests(unittest.TestCase):
    def test_bridge_activate_step_intent_and_monotonic_ids(self):
        session = TrajectorySession(IDENTITY)
        adapter = EgoTrajectoryAdapter(session)
        spline, traj_id, start_tick = bridge_bspline(valid_payload(),
                                                     anchor_ns=0, current_tick=0)
        self.assertEqual((traj_id, start_tick), (1, 5))
        adapter.begin_replan(identity(session), 1)
        accepted = adapter.activate(spline, traj_id, start_tick, identity(session),
                                    fallback_yaw=0.0)
        self.assertEqual(accepted, 1)
        intent = adapter.step(identity(session), start_tick, True, True)
        self.assertEqual(intent["intent"], "trajectory")
        self.assertEqual((intent["trajectory_id"], intent["command_id"], intent["tick"]),
                         (1, 1, 5))
        self.assertEqual(len(intent["position_ref"]), 3)
        self.assertEqual(intent["yaw_ref"], 0.0)
        # Second bridged payload: traj_id strictly increases, start moves forward on
        # the grid, and the session's command_id stays strictly monotonic.
        spline2, traj_id2, start2 = bridge_bspline(
            valid_payload(traj_id=2, start_time=20_000_000), anchor_ns=0, current_tick=6)
        self.assertEqual((traj_id2, start2), (2, 20))
        adapter.begin_replan(identity(session), 2)
        adapter.activate(spline2, traj_id2, start2, identity(session), fallback_yaw=0.0)
        intent2 = adapter.step(identity(session), start2, True, True)
        self.assertEqual(intent2["intent"], "trajectory")
        self.assertEqual((intent2["trajectory_id"], intent2["tick"]), (2, 20))
        self.assertGreater(intent2["command_id"], intent["command_id"])

    def test_bridged_stale_start_tick_is_rejected_by_adapter(self):
        session = TrajectorySession(IDENTITY)
        adapter = EgoTrajectoryAdapter(session)
        spline, traj_id, start_tick = bridge_bspline(valid_payload(),
                                                     anchor_ns=0, current_tick=0)
        adapter.begin_replan(identity(session), 1)
        adapter.activate(spline, traj_id, start_tick, identity(session), fallback_yaw=0.0)
        adapter.step(identity(session), start_tick, True, True)
        # The bridge itself refuses a start behind the caller's current tick...
        with self.assertRaises(BridgeError) as caught:
            bridge_bspline(valid_payload(traj_id=2), anchor_ns=0, current_tick=6)
        self.assertEqual(caught.exception.reason, "start_in_past")
        # ...and a grid-valid but already-observed start_tick is refused by the adapter.
        spline2, traj_id2, start2 = bridge_bspline(
            valid_payload(traj_id=2, start_time=5_000_000), anchor_ns=0, current_tick=0)
        adapter.begin_replan(identity(session), 2)
        with self.assertRaises(AdapterError):
            adapter.activate(spline2, traj_id2, start2, identity(session), fallback_yaw=0.0)


if __name__ == "__main__":
    unittest.main()
