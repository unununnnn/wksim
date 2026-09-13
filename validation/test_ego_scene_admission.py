"""Pure offline tests for the #102/#39 trajectory scene-admission slice.

No ROS, no planner, no socket, no SITL/UE/MATLAB, no wall clock.  The admission
gate consumes the decoder's bridge-mapping output shape directly (the TCP module
is intentionally not imported here, so this suite is independent of it), bridges
it to an EgoSpline, checks the sampled polyline against the committed
ego-single-box-v1 obstacle AABB and map envelope, and only on a pass activates
the adapter exactly once.  The result is honestly a sampled/segment check, never
a continuous-curve safety proof.

Scene geometry under test (committed ego-single-box-v1):
  obstacle AABB  min=(-0.5,-1.0,0.0) max=(0.5,1.0,5.5)
  map bounds     min=(-10,-6,0)      max=(10,6,6)
  vehicle_radius 0.35, required_clearance 0.30  (margin 0.65)
"""
import math
import unittest

from Simulator.wksim_planning.ego_evaluator import EgoSpline, UniformBspline
from Simulator.wksim_planning.ego_trajectory_adapter import EgoTrajectoryAdapter
from Simulator.wksim_planning.trajectory_session import TrajectorySession
from Simulator.wksim_runtime.planner_scene_binding import (
    EGO_SINGLE_BOX_BINDING,
    PlannerSceneBinding,
)
from Simulator.wksim_planning.ego_scene_admission import (
    DEFAULT_SAMPLE_PERIOD_S,
    EVIDENCE_KIND,
    MAX_ADMISSION_SAMPLES,
    NON_CLAIMS,
    SceneAdmissionError,
    TrajectorySceneAdmission,
    assess_spline_clearance,
    _sample_times,
)

IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1, control_epoch="epoch-a",
                planner_generation=0, command_high_water=0)

REQUIRED_CLEARANCE = EGO_SINGLE_BOX_BINDING.profile.required_clearance   # 0.30
VEHICLE_RADIUS = EGO_SINGLE_BOX_BINDING.profile.vehicle_radius           # 0.35


def identity_for(session):
    return dict(IDENTITY, planner_generation=session.generation)


def clear_cps():
    """Straight order-3 path at y=3, z=1: clear of the obstacle and inside the map."""
    return [(float(i) * 0.5, 3.0, 1.0) for i in range(7)]


def collision_cps():
    """Straight path at y=0, z=1 crossing the obstacle x-slab: collides."""
    return [(float(i - 3) * 0.5, 0.0, 1.0) for i in range(7)]


def envelope_margin_cps():
    """Path at z=5.9 (0.1 from the z=6 ceiling): inside the map but within margin."""
    return [(float(i) * 0.5, 3.0, 5.9) for i in range(7)]


def outside_map_cps():
    """Path running to x=11, beyond the map x-max of 10: strictly outside."""
    return [(8.0 + float(i) * 0.5, 3.0, 1.0) for i in range(7)]


def end_dip_cps():
    """Clear start (y=3) whose tail dips into the obstacle near the end."""
    return [(-3.0, 3.0, 1.0), (-2.0, 3.0, 1.0), (-1.0, 3.0, 1.0), (0.0, 3.0, 1.0),
            (0.0, 2.0, 1.0), (0.0, 0.5, 1.0), (0.0, 0.0, 1.0)]


def make_spline(cps):
    return EgoSpline(3, list(UniformBspline(3, cps, 0.1).knots), [tuple(p) for p in cps])


def make_mapping(cps, *, traj_id=1, start_time_ns=0, order=3, drone_id=0):
    """Build the decoder-output bridge mapping shape that bridge_bspline consumes."""
    return {
        "drone_id": drone_id,
        "order": order,
        "traj_id": traj_id,
        "start_time": start_time_ns,                 # integer nanoseconds (decoded form)
        "knots": list(UniformBspline(order, cps, 0.1).knots),
        "pos_pts": [tuple(float(c) for c in p) for p in cps],
        "yaw_pts": [],
        "yaw_dt": 0.0,
    }


def make_controller():
    session = TrajectorySession(dict(IDENTITY))
    adapter = EgoTrajectoryAdapter(session)
    controller = TrajectorySceneAdmission(adapter, anchor_ns=0)
    return session, adapter, controller


def spy_on_activate(adapter):
    """Wrap adapter.replan_and_activate to count invocations without changing behavior."""
    calls = []
    original = adapter.replan_and_activate

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    adapter.replan_and_activate = spy
    return calls


def session_snapshot(session):
    return (session.state, session.generation, session.last_event_sequence,
            session.last_command_id)


class ClearanceAssessmentTests(unittest.TestCase):
    """Pure geometry: assess_spline_clearance over the sampled polyline."""

    def assert_admission_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(SceneAdmissionError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_clear_polyline_admitted(self):
        report = assess_spline_clearance(make_spline(clear_cps()))
        self.assertTrue(report.admitted)
        self.assertIsNone(report.violation)
        self.assertGreaterEqual(report.min_obstacle_clearance, REQUIRED_CLEARANCE)
        self.assertGreaterEqual(report.min_envelope_clearance, REQUIRED_CLEARANCE)
        self.assertEqual(report.sample_count, report.segment_count + 1)
        self.assertGreater(report.segment_count, 1)

    def test_collision_polyline_rejected(self):
        report = assess_spline_clearance(make_spline(collision_cps()))
        self.assertFalse(report.admitted)
        self.assertEqual(report.violation["kind"], "obstacle_clearance")
        self.assertLess(report.min_obstacle_clearance, REQUIRED_CLEARANCE)

    def test_envelope_margin_rejected(self):
        # z=5.9 is inside the map but only 0.1 from the ceiling; net of the 0.35
        # radius that is -0.25, below the 0.30 required clearance.
        report = assess_spline_clearance(make_spline(envelope_margin_cps()))
        self.assertFalse(report.admitted)
        self.assertEqual(report.violation["kind"], "map_envelope")
        self.assertLess(report.min_envelope_clearance, REQUIRED_CLEARANCE)

    def test_strictly_outside_map_rejected(self):
        report = assess_spline_clearance(make_spline(outside_map_cps()))
        self.assertFalse(report.admitted)
        self.assertEqual(report.violation["kind"], "map_envelope")

    def test_end_dip_into_obstacle_rejected(self):
        report = assess_spline_clearance(make_spline(end_dip_cps()))
        self.assertFalse(report.admitted)
        self.assertEqual(report.violation["kind"], "obstacle_clearance")

    def test_grid_includes_exact_endpoints(self):
        for duration in (0.4, 0.05, 0.033, 1.0):
            times = _sample_times(duration, DEFAULT_SAMPLE_PERIOD_S)
            self.assertEqual(times[0], 0.0)                 # exact start
            self.assertEqual(times[-1], duration)           # exact end
            self.assertTrue(all(times[i] < times[i + 1] for i in range(len(times) - 1)))

    def test_grid_bound_is_exact_and_endpoint_is_reserved(self):
        step = 0.1
        duration = (MAX_ADMISSION_SAMPLES - 1) * step
        times = _sample_times(duration, step)
        self.assertEqual(len(times), MAX_ADMISSION_SAMPLES)
        self.assertEqual(times[0], 0.0)
        self.assertEqual(times[-1], duration)
        self.assertTrue(all(times[i] < times[i + 1] for i in range(len(times) - 1)))

        with self.assertRaises(SceneAdmissionError) as ctx:
            _sample_times(MAX_ADMISSION_SAMPLES * step, step)
        self.assertEqual(ctx.exception.reason, "invalid_grid")

    def test_grid_bound_uses_adjacent_float_values(self):
        step = 0.1
        boundary = (MAX_ADMISSION_SAMPLES - 1) * step

        below = math.nextafter(boundary, 0.0)
        times = _sample_times(below, step)
        self.assertEqual(len(times), MAX_ADMISSION_SAMPLES)
        self.assertEqual(times[-1], below)
        self.assertTrue(all(times[i] < times[i + 1] for i in range(len(times) - 1)))

        above = math.nextafter(boundary, math.inf)
        with self.assertRaises(SceneAdmissionError) as ctx:
            _sample_times(above, step)
        self.assertEqual(ctx.exception.reason, "invalid_grid")

    def test_assessment_evaluates_exact_curve_endpoints(self):
        spline = make_spline(clear_cps())
        report = assess_spline_clearance(spline)
        self.assertEqual(report.start_point, tuple(spline.position_at(0.0)))
        self.assertEqual(report.end_point, tuple(spline.position_at(spline.duration)))

    def test_honest_sampled_segment_labelling(self):
        report = assess_spline_clearance(make_spline(clear_cps()))
        # The result is a sampled/segment check, never a continuous-curve proof.
        self.assertFalse(report.continuous_proof)
        self.assertEqual(report.evidence_kind, "sampled_segment_checked")
        self.assertEqual(report.evidence_kind, EVIDENCE_KIND)
        text = " ".join(report.non_claims).lower()
        self.assertIn("sampled polyline", text)
        self.assertIn("continuous", text)
        self.assertIn("terrain15d", text)                    # explicitly never driven
        self.assertIn("force", text)
        self.assertIn("flight", text)
        # No 0.010 s stride is advertised as a continuous-safety sufficiency.
        self.assertIn("not a proof", text)

    def test_identity_fields_come_from_committed_binding(self):
        report = assess_spline_clearance(make_spline(clear_cps()))
        self.assertEqual(report.scene_id, "ego-single-box-v1")
        self.assertEqual(report.scene_hash, EGO_SINGLE_BOX_BINDING.scene_hash)
        self.assertEqual(report.geometry_id, "ego-single-box-v1:obstacle")
        self.assertEqual(report.profile_hash, EGO_SINGLE_BOX_BINDING.profile.profile_hash)
        self.assertEqual(report.vehicle_radius, VEHICLE_RADIUS)
        self.assertEqual(report.required_clearance, REQUIRED_CLEARANCE)
        self.assertAlmostEqual(report.clearance_margin, VEHICLE_RADIUS + REQUIRED_CLEARANCE)

    def test_invalid_inputs_fail_closed(self):
        spline = make_spline(clear_cps())
        self.assert_admission_error("invalid_binding", assess_spline_clearance, spline, binding=object())
        self.assert_admission_error("invalid_spline", assess_spline_clearance, object())
        self.assert_admission_error("invalid_grid", assess_spline_clearance, spline, sample_period_s=0.0)
        self.assert_admission_error("invalid_grid", assess_spline_clearance, spline, sample_period_s=-1.0)
        self.assert_admission_error("invalid_grid", assess_spline_clearance, spline,
                                    sample_period_s=float("nan"))
        degenerate = make_spline(clear_cps())
        degenerate.duration = 0.0
        self.assert_admission_error("invalid_spline", assess_spline_clearance, degenerate)

    def test_sample_grid_is_bounded(self):
        # A tiny stride on a real duration would explode the grid; it fails closed.
        self.assert_admission_error(
            "invalid_grid", assess_spline_clearance, make_spline(clear_cps()),
            sample_period_s=1e-9)


class AdmissionWiringTests(unittest.TestCase):
    """Full chain: decoded mapping -> bridge -> clearance -> atomic activation."""

    def assert_admission_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(SceneAdmissionError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_pass_activates_adapter_exactly_once(self):
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        report, accepted = controller.admit(
            make_mapping(clear_cps(), traj_id=1, start_time_ns=0),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertTrue(report.admitted)
        self.assertEqual(accepted, 1)
        self.assertEqual(len(calls), 1)                      # exactly one adapter call
        args, _ = calls[0]
        # Wired through with identity, sequence, the bridged spline, traj_id, start_tick.
        self.assertIsInstance(args[2], EgoSpline)
        self.assertEqual(args[3], 1)                          # trajectory_id
        self.assertEqual(args[4], 0)                          # start_tick
        self.assertEqual(session.state, "ACTIVE")
        self.assertEqual(session.generation, 1)
        self.assertEqual(session.last_event_sequence, 1)
        self.assertEqual(adapter.trajectory_id, 1)

    def test_collision_never_calls_adapter(self):
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        before = session_snapshot(session)
        error = self.assert_admission_error(
            "clearance_violation", controller.admit,
            make_mapping(collision_cps(), traj_id=1),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(len(calls), 0)                       # adapter untouched
        self.assertEqual(session_snapshot(session), before)   # session unchanged
        self.assertIsNotNone(error.report)
        self.assertFalse(error.report.admitted)

    def test_map_violation_never_calls_adapter(self):
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        before = session_snapshot(session)
        self.assert_admission_error(
            "map_violation", controller.admit,
            make_mapping(envelope_margin_cps(), traj_id=1),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(len(calls), 0)
        self.assertEqual(session_snapshot(session), before)

    def test_identity_mismatch_never_calls_adapter(self):
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        before = session_snapshot(session)
        for bad in (dict(identity_for(session), run_id="other"),
                    dict(identity_for(session), control_epoch="other"),
                    dict(identity_for(session), mission_id="other"),
                    dict(identity_for(session), uav_id=2)):
            with self.subTest(bad=bad):
                self.assert_admission_error(
                    "identity_mismatch", controller.admit, make_mapping(clear_cps()),
                    identity=bad, event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(len(calls), 0)
        self.assertEqual(session_snapshot(session), before)

    def test_bridge_rejection_never_calls_adapter(self):
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        before = session_snapshot(session)
        # order != 3 -> unsupported_order
        error = self.assert_admission_error(
            "bridge_rejected", controller.admit,
            make_mapping(clear_cps(), traj_id=1, order=2),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(error.bridge_reason, "unsupported_order")
        # off-grid start_time (0.5 ms) -> start_off_grid
        error = self.assert_admission_error(
            "bridge_rejected", controller.admit,
            make_mapping(clear_cps(), traj_id=1, start_time_ns=500_000),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(error.bridge_reason, "start_off_grid")
        # start in the past relative to current_tick -> start_in_past
        error = self.assert_admission_error(
            "bridge_rejected", controller.admit,
            make_mapping(clear_cps(), traj_id=1, start_time_ns=0),
            identity=identity_for(session), event_sequence=1, current_tick=10, fallback_yaw=0.0)
        self.assertEqual(error.bridge_reason, "start_in_past")
        self.assertEqual(len(calls), 0)
        self.assertEqual(session_snapshot(session), before)

    def test_invalid_mapping_never_calls_adapter(self):
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        before = session_snapshot(session)
        mapping = make_mapping(clear_cps())
        del mapping["knots"]                                   # missing field
        self.assert_admission_error(
            "invalid_mapping", controller.admit, mapping,
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assert_admission_error(
            "invalid_mapping", controller.admit, "not-a-mapping",
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(len(calls), 0)
        self.assertEqual(session_snapshot(session), before)

    def test_adapter_rejection_rolls_back_without_mutation(self):
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        # First, a clean admission commits generation 1 / event_sequence 1.
        controller.admit(make_mapping(clear_cps(), traj_id=1, start_time_ns=0),
                         identity=identity_for(session), event_sequence=1,
                         current_tick=0, fallback_yaw=0.0)
        self.assertEqual((session.generation, session.last_event_sequence), (1, 1))
        before = session_snapshot(session)
        # Reusing event_sequence 1 must be rejected by the session and roll back.
        self.assert_admission_error(
            "adapter_rejected", controller.admit,
            make_mapping(clear_cps(), traj_id=2, start_time_ns=0),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(session_snapshot(session), before)
        # A stale generation identity is rejected by the adapter's own gate.
        stale = dict(IDENTITY, planner_generation=0)           # session is at 1 now
        self.assert_admission_error(
            "adapter_rejected", controller.admit,
            make_mapping(clear_cps(), traj_id=2, start_time_ns=0),
            identity=stale, event_sequence=2, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(session_snapshot(session), before)

    def test_successive_admissions_preserve_atomic_boundary(self):
        session, adapter, controller = make_controller()
        spy_on_activate(adapter)
        # Admission 1 at tick 0.
        controller.admit(make_mapping(clear_cps(), traj_id=1, start_time_ns=0),
                         identity=identity_for(session), event_sequence=1,
                         current_tick=0, fallback_yaw=0.0)
        # Admission 2 at a later authority tick (0.5 s -> tick 500), higher ids.
        report, accepted = controller.admit(
            make_mapping(clear_cps(), traj_id=2, start_time_ns=500_000_000),
            identity=identity_for(session), event_sequence=2,
            current_tick=500, fallback_yaw=0.0)
        self.assertEqual(accepted, 2)
        # Stable identity is pinned; generation and event sequence advanced exactly once each.
        self.assertEqual((session.identity.run_id, session.identity.control_epoch),
                         (IDENTITY["run_id"], IDENTITY["control_epoch"]))
        self.assertEqual(session.generation, 2)
        self.assertEqual(session.last_event_sequence, 2)
        self.assertEqual(adapter.trajectory_id, 2)
        self.assertTrue(report.admitted)

    def test_construction_validates_adapter_binding_anchor(self):
        session = TrajectorySession(dict(IDENTITY))
        adapter = EgoTrajectoryAdapter(session)
        with self.assertRaises(SceneAdmissionError) as ctx:
            TrajectorySceneAdmission(object(), anchor_ns=0)
        self.assertEqual(ctx.exception.reason, "invalid_adapter")
        with self.assertRaises(SceneAdmissionError) as ctx:
            TrajectorySceneAdmission(adapter, binding=object(), anchor_ns=0)
        self.assertEqual(ctx.exception.reason, "invalid_binding")
        with self.assertRaises(SceneAdmissionError) as ctx:
            TrajectorySceneAdmission(adapter, anchor_ns=-1)
        self.assertEqual(ctx.exception.reason, "invalid_anchor")
        with self.assertRaises(SceneAdmissionError) as ctx:
            TrajectorySceneAdmission(adapter, anchor_ns=0, sample_period_s=0.0)
        self.assertEqual(ctx.exception.reason, "invalid_grid")
        # A real committed binding instance is accepted.
        self.assertIsInstance(
            TrajectorySceneAdmission(adapter, binding=PlannerSceneBinding(), anchor_ns=0),
            TrajectorySceneAdmission)


if __name__ == "__main__":
    unittest.main()
