"""Pure offline tests for the #102/#39 trajectory scene-admission slice.

No ROS, no planner, no socket, no SITL/UE/MATLAB, no wall clock.  The admission
gate consumes the decoder's bridge-mapping output shape directly (the TCP module
is intentionally not imported here, so this suite is independent of it), bridges
it to an EgoSpline, checks the sampled polyline against the committed
ego-single-box-v1 obstacle AABB and map envelope, certifies the CONTINUOUS curve
from the B-spline control-point convex hulls, and only on a pass activates the
adapter exactly once.

Two honest evidence modes are covered:
  * strict (default): a PASS carries ``convex_hull_span_certified`` +
    ``continuous_proof=True``; a curve whose control hulls intrude the margin is
    rejected as ``continuous_clearance_unproven`` even when the 10 ms sampled
    polyline of the same curve looks clean (the alternating-control-point
    witness), and a certificate that cannot be built fails closed;
  * legacy (``strict_continuous=False``): the sampled polyline is the only
    evidence and the label stays ``sampled_segment_checked`` /
    ``continuous_proof=False``.

Scene geometry under test (committed ego-single-box-v1):
  obstacle AABB  min=(-0.5,-1.0,0.0) max=(0.5,1.0,5.5)
  map bounds     min=(-10,-6,0)      max=(10,6,6)
  vehicle_radius 0.35, required_clearance 0.30  (margin 0.65)
"""
import math
import random
import unittest

from Simulator.wksim_planning.ego_evaluator import EgoSpline, SplineError, UniformBspline
from Simulator.wksim_planning.ego_trajectory_adapter import EgoTrajectoryAdapter
from Simulator.wksim_planning.trajectory_session import TrajectorySession
from Simulator.wksim_runtime.planner_scene_binding import (
    EGO_SINGLE_BOX_BINDING,
    PlannerSceneBinding,
)
from Simulator.wksim_planning.ego_scene_admission import (
    CONTINUOUS_EVIDENCE_KIND,
    DEFAULT_SAMPLE_PERIOD_S,
    EVIDENCE_KIND,
    MAX_ADMISSION_SAMPLES,
    NON_CLAIMS,
    STRUCTURAL_CERTIFICATE_REASON,
    SceneAdmissionError,
    TrajectorySceneAdmission,
    assess_spline_clearance,
    certify_continuous_clearance,
    _sample_times,
)
from Simulator.wksim_planning.scene_profile import segment_clearance

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


def make_spline_with_knots(cps, knots):
    """Build an EgoSpline with an explicit (possibly repeated-knot) knot vector."""
    return EgoSpline(3, list(knots), [tuple(p) for p in cps])


# The audit's decisive counterexample (validation/coordination/
# ds-g3-closure-frontier-20260913-01, section G): alternating control points at
# knot interval 0.005 s whose curve period equals the 0.010 s sample stride, so
# every sample lands on the curve's x-peak and the sampled gate sees a clean
# 0.40 m while the continuous curve dips to ~0.20 m (0.10 m inside the 0.30 m
# requirement).
WITNESS_CENTER, WITNESS_AMPLITUDE, WITNESS_KNOT_H, WITNESS_POINTS = 1.15, 0.30, 0.005, 203


def witness_cps():
    return [(WITNESS_CENTER - WITNESS_AMPLITUDE * ((-1) ** i), 0.0, 2.0)
            for i in range(WITNESS_POINTS)]


def witness_knots():
    return list(UniformBspline(3, witness_cps(), WITNESS_KNOT_H).knots)


def witness_spline():
    return make_spline_with_knots(witness_cps(), witness_knots())


def dense_min_clearance(spline, samples=20_000):
    """Independent dense scan of the CONTINUOUS curve (never the admission grid)."""
    duration = spline.duration
    best = math.inf
    previous = spline.position_at(0.0)
    for index in range(1, samples + 1):
        current = spline.position_at(duration * index / samples)
        best = min(best, segment_clearance(previous, current))
        previous = current
    return best


def make_mapping(cps, *, traj_id=1, start_time_ns=0, order=3, drone_id=0, knot_h=0.1):
    """Build the decoder-output bridge mapping shape that bridge_bspline consumes."""
    return {
        "drone_id": drone_id,
        "order": order,
        "traj_id": traj_id,
        "start_time": start_time_ns,                 # integer nanoseconds (decoded form)
        "knots": list(UniformBspline(order, cps, knot_h).knots),
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
        # Legacy sampled-only mode keeps the original honesty label verbatim.
        report = assess_spline_clearance(make_spline(clear_cps()), strict_continuous=False)
        self.assertFalse(report.continuous_proof)
        self.assertEqual(report.evidence_kind, "sampled_segment_checked")
        self.assertEqual(report.evidence_kind, EVIDENCE_KIND)
        self.assertIsNone(report.continuous_certificate)
        text = " ".join(report.non_claims).lower()
        self.assertIn("sampled polyline", text)
        self.assertIn("continuous", text)
        self.assertIn("terrain15d", text)                    # explicitly never driven
        self.assertIn("force", text)
        self.assertIn("flight", text)
        # No 0.010 s stride is advertised as a continuous-safety sufficiency.
        self.assertIn("not a proof", text)

    def test_strict_mode_labels_continuous_proof(self):
        report = assess_spline_clearance(make_spline(clear_cps()))     # strict is the default
        self.assertTrue(report.admitted)
        self.assertTrue(report.continuous_proof)
        self.assertEqual(report.evidence_kind, CONTINUOUS_EVIDENCE_KIND)
        self.assertEqual(report.evidence_kind, "convex_hull_span_certified")
        self.assertIsNotNone(report.continuous_certificate)
        self.assertTrue(report.continuous_certificate.proven)
        text = " ".join(report.non_claims).lower()
        self.assertIn("convex hull", text)
        self.assertIn("continuous", text)
        self.assertIn("terrain15d", text)
        self.assertIn("not a proof", text)

    def test_strict_flag_must_be_a_strict_bool(self):
        for bad in (1, 0, "yes", None):
            with self.subTest(bad=bad):
                self.assert_admission_error(
                    "invalid_grid", assess_spline_clearance, make_spline(clear_cps()),
                    strict_continuous=bad)

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


class ContinuousCertificateTests(unittest.TestCase):
    """The continuous control-hull certificate: sound, conservative, fail-closed."""

    def assert_admission_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(SceneAdmissionError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def interval_cover(self, certificate):
        return [(start, end) for start, end, _, _ in certificate.intervals]

    def test_witness_is_rejected_despite_clean_sampled_grid(self):
        """The audit's 0.20 m true-min witness must never be admitted again."""
        spline = witness_spline()
        report = assess_spline_clearance(spline)
        # The sampled polyline of the SAME curve still looks clean ...
        self.assertGreaterEqual(report.min_obstacle_clearance, REQUIRED_CLEARANCE)
        # ... but the report is not admitted and says exactly why.
        self.assertFalse(report.admitted)
        self.assertEqual(report.violation["kind"], "continuous_clearance_unproven")
        self.assertFalse(report.continuous_proof)
        self.assertEqual(report.evidence_kind, EVIDENCE_KIND)
        certificate = report.continuous_certificate
        self.assertIsNotNone(certificate)
        self.assertFalse(certificate.proven)
        self.assertIsNone(certificate.structural_reason)
        self.assertEqual(certificate.interval_count, WITNESS_POINTS - 3)   # 200 intervals
        # The certificate's own number is the true continuous minimum (the control
        # hull touches the margin), not the 0.40 m the sampled grid reported.
        self.assertLess(certificate.min_net_obstacle_clearance, REQUIRED_CLEARANCE)
        self.assertAlmostEqual(certificate.min_net_obstacle_clearance, 0.0, delta=1e-9)
        self.assertGreater(certificate.min_hull_inset_clearance, 0.0)

    def test_witness_true_minimum_is_independently_violating(self):
        """Cross-check: a dense independent scan agrees the curve intrudes."""
        spline = witness_spline()
        truth = dense_min_clearance(spline)
        self.assertLess(truth, REQUIRED_CLEARANCE - 1e-6)
        self.assertGreaterEqual(REQUIRED_CLEARANCE - truth, 0.05)
        # The conservative certificate reports a value no larger than the truth.
        certificate = certify_continuous_clearance(spline)
        self.assertLessEqual(certificate.min_net_obstacle_clearance, truth + 1e-9)

    def test_witness_rejection_is_stable_under_finer_and_coarser_grids(self):
        """No sampling stride can turn the witness into an admitted trajectory."""
        spline = witness_spline()
        for step in (0.05, 0.01, 0.005, 0.001):
            with self.subTest(step=step):
                report = assess_spline_clearance(spline, sample_period_s=step)
                self.assertFalse(report.admitted)
                self.assertFalse(report.continuous_proof)
                # 10 ms is the only stride the witness fools end to end: it is
                # exactly the one that leaves the sampled gate clean, so the
                # continuous certificate is the gate that rejects there.
                reported_kinds = {report.violation["kind"]}
                if step == DEFAULT_SAMPLE_PERIOD_S:
                    self.assertEqual(reported_kinds, {"continuous_clearance_unproven"})
                    self.assertGreaterEqual(report.min_obstacle_clearance, REQUIRED_CLEARANCE)
                else:
                    self.assertTrue(
                        reported_kinds & {"continuous_clearance_unproven", "obstacle_clearance"})

    def test_safe_parallel_curve_with_1cm_margin_is_proved(self):
        """A curve 1 cm beyond the required margin must be accepted (soundness)."""
        cps = [(WITNESS_CENTER + 0.01, 0.0, 2.0) for _ in range(WITNESS_POINTS)]
        spline = make_spline_with_knots(cps, witness_knots())
        report = assess_spline_clearance(spline)
        self.assertTrue(report.admitted)
        self.assertTrue(report.continuous_proof)
        self.assertEqual(report.evidence_kind, CONTINUOUS_EVIDENCE_KIND)
        certificate = report.continuous_certificate
        # Control hull x in [1.16, 1.16] -> obstacle gap = 1.16 - 0.5 = 0.66.
        self.assertAlmostEqual(certificate.min_net_obstacle_clearance, 0.66 - VEHICLE_RADIUS,
                               delta=1e-12)
        self.assertGreaterEqual(certificate.min_net_obstacle_clearance, REQUIRED_CLEARANCE)
        # And the dense scan confirms the true curve is at least that clear.
        self.assertGreaterEqual(dense_min_clearance(spline, samples=400), REQUIRED_CLEARANCE)

    def test_small_safe_sinusoid_is_proved(self):
        cps = [(WITNESS_CENTER + 0.02 + 0.01 * math.sin(i * math.pi / 25.0), 0.0, 2.0)
               for i in range(WITNESS_POINTS)]
        spline = make_spline_with_knots(cps, witness_knots())
        report = assess_spline_clearance(spline)
        self.assertTrue(report.admitted)
        self.assertTrue(report.continuous_proof)
        self.assertGreater(report.continuous_certificate.min_net_obstacle_clearance,
                           REQUIRED_CLEARANCE)
        self.assertGreaterEqual(dense_min_clearance(spline, samples=400), REQUIRED_CLEARANCE)

    def test_threshold_equality_is_accepted_and_the_adjacent_double_below_is_rejected(self):
        """Exact-boundary determinism: the certificate tests `>= required_clearance`.

        Geometry is chosen so the hull<->obstacle gap is a single exact axis
        difference: the control box straddles the obstacle x-slab (so the x
        separation is zero) and overlaps it in z, leaving the gap exactly
        ``y_min - 1.0`` -- no sqrt rounding is involved.  ``y = 1.65`` is itself
        one double BELOW the requirement (0.65 - 0.35 rounds down to
        0.29999999999999993), so the adjacent double above it is the smallest
        accepted centreline height.
        """
        boundary = 1.0 + REQUIRED_CLEARANCE + VEHICLE_RADIUS      # y = 1.65
        just_below = boundary
        just_above = math.nextafter(boundary, math.inf)

        def certificate_for(y_low):
            cps = [(float(index) * 0.5 - 1.5, y_low, 2.0) for index in range(7)]
            return assess_spline_clearance(make_spline(cps)).continuous_certificate

        below = certificate_for(just_below)
        self.assertEqual(below.obstacle_hull_gap, just_below - 1.0)
        self.assertEqual(below.min_net_obstacle_clearance, (just_below - 1.0) - VEHICLE_RADIUS)
        self.assertLess(below.min_net_obstacle_clearance, REQUIRED_CLEARANCE)
        self.assertFalse(below.proven)

        above = certificate_for(just_above)
        self.assertEqual(above.obstacle_hull_gap, just_above - 1.0)
        self.assertGreaterEqual(above.min_net_obstacle_clearance, REQUIRED_CLEARANCE)
        self.assertTrue(above.proven)

    def test_map_inset_boundary_equality_is_accepted_and_below_is_rejected(self):
        """Envelope face equality passes; an intrusion past the inset fails closed.

        The map floor is ``z = 0.0`` and the margin is ``0.35 + 0.30``, so the
        certificate's ``z - (floor + margin)`` arithmetic is exactly tangent at
        ``z = 0.65``: that centreline is proved (``inset_clearance >= 0.0``) while
        one centimetre lower is rejected.  The certificate's own decision is a
        plain ``>= 0.0`` on the multi-axis inset minimum, so a *few-ulp* intrusion
        can still be absorbed by the face arithmetic; the pre-existing sampled
        envelope gate keeps its stricter rounding on the same tangent centreline,
        so the report as a whole is never more permissive than before.
        """
        def certificate_for(z_low):
            cps = [(3.0, 3.0, z_low) for _ in range(7)]
            return certify_continuous_clearance(make_spline(cps))

        tangent = 0.65
        self.assertTrue(certificate_for(tangent).proven)
        self.assertGreaterEqual(certificate_for(tangent).min_hull_inset_clearance, 0.0)
        self.assertTrue(certificate_for(math.nextafter(tangent, math.inf)).proven)

        outside = certificate_for(tangent - 0.01)
        self.assertFalse(outside.proven)
        self.assertLess(outside.min_hull_inset_clearance, 0.0)
        # The certificate is not weaker than the sampled envelope on the same
        # centreline; where it ADDS power is curvature between samples, which is
        # covered for the obstacle case by the witness test above.
        report = assess_spline_clearance(make_spline([(3.0, 3.0, 0.5)] * 8))
        self.assertFalse(report.admitted)
        self.assertFalse(report.continuous_proof)
        self.assertLess(report.continuous_certificate.min_hull_inset_clearance, 0.0)

    def test_rejected_boundary_report_never_claims_continuous_proof(self):
        """A strict rejection must not publish the certified-pass labels.

        Review ds-g3-continuous-clearance-review-20260913-01 (P2-1): within one
        ulp of the margin the sampled gate can reject while the control-hull
        certificate still proves.  Such a report must carry
        ``continuous_proof=False`` / ``sampled_segment_checked``; publishing
        ``convex_hull_span_certified`` on a rejected report would contradict the
        contract ("continuous_proof True only on a strict pass").
        """
        boundary_scenes = [
            ((0.0, 1.6500000000000001, 2.75), "obstacle_clearance"),
            ((3.0, 3.0, 0.6499999999999999), "map_envelope"),
            ((3.0, 3.0, 0.65), "map_envelope"),
        ]
        for point, kind in boundary_scenes:
            with self.subTest(point=point):
                report = assess_spline_clearance(make_spline([point] * 7))
                self.assertFalse(report.admitted)
                self.assertEqual(report.violation["kind"], kind)
                # The certificate itself still proves at these ulp-boundary
                # scenes; the report must not turn that into a pass claim.
                self.assertTrue(report.continuous_certificate.proven)
                self.assertFalse(report.continuous_proof)
                self.assertEqual(report.evidence_kind, EVIDENCE_KIND)

    def test_randomized_cover_is_a_sound_outer_bound(self):
        """Seeded cross-check: the certificate is never contradicted by the curve.

        For a fixed pseudo-random family of splines (no wall clock, no OS RNG):
        1. every densely sampled curve point must lie inside the AABB of the active
           control points of the interval that claims to contain it (+1e-9), which
           is the soundness claim the cover rests on;
        2. a `proven` certificate must never coexist with a dense-scan clearance
           violation, i.e. the certificate never admits an intruding curve.
        """
        generator = random.Random(20260913)
        checked = 0
        proven = 0
        for _ in range(120):
            count = generator.randint(4, 10)
            knot_h = generator.choice((0.05, 0.1, 0.2))
            origin_x = generator.uniform(-3.0, 4.0)
            cps = [(origin_x + generator.uniform(-1.2, 1.2) + index * knot_h,
                    generator.uniform(-2.5, 2.5), generator.uniform(0.4, 5.0))
                   for index in range(count)]
            spline = make_spline_with_knots(cps, list(UniformBspline(3, cps, knot_h).knots))
            certificate = certify_continuous_clearance(spline)
            if certificate.structural_reason is not None:
                continue
            checked += 1
            duration = spline.duration
            for start_u, end_u, first, last in certificate.intervals:
                active = spline.position._points[first - 3:last + 1]
                low = [min(point[axis] for point in active) for axis in range(3)]
                high = [max(point[axis] for point in active) for axis in range(3)]
                for step in range(21):
                    point = spline.position_at(start_u + (end_u - start_u) * step / 20.0)
                    for axis in range(3):
                        self.assertLessEqual(max(low[axis] - point[axis], point[axis] - high[axis]),
                                             1e-9)
            dense = min(
                segment_clearance(spline.position_at(duration * index / 400.0),
                                  spline.position_at(duration * (index + 1) / 400.0))
                for index in range(400))
            if certificate.proven:
                proven += 1
                self.assertGreaterEqual(dense, REQUIRED_CLEARANCE - 1e-6)
        self.assertGreater(checked, 100)
        self.assertGreater(proven, 0)

    def test_repeated_knots_cannot_reach_the_certificate(self):
        """Repeated knots are fail-closed everywhere; the grouping is dead code.

        No repeated-knot vector can be constructed through the public bridge
        path (pinned here), and a tampered repeated knot is rejected fail-closed
        as ``non_monotone_knots`` BEFORE the interval walk (see
        ``test_non_monotone_knots_fail_closed``).  The certificate's
        repeated-knot grouping and degenerate-span skip are therefore
        unreachable defensive code, never a live soundness argument.
        """
        cps = [(float(index) * 0.2, 3.0, 1.0) for index in range(10)]
        repeated = [0.0, 0.0, 0.0, 0.0, 0.05, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.3, 0.3, 0.3]
        self.assertEqual(len(repeated), len(cps) + 4)
        with self.assertRaises(SplineError):
            make_spline_with_knots(cps, repeated)

    def test_degenerate_curve_collapses_to_one_certified_interval(self):
        """A curve short enough to live in one span still gets a full-domain cover."""
        cps = [(3.0, 3.0, 1.0), (3.0, 3.0, 1.0), (3.0, 3.0, 1.0), (3.0, 3.0, 1.0)]
        knots = [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4]
        spline = make_spline_with_knots(cps, knots)
        self.assertEqual(len(knots), len(cps) + 4)
        self.assertEqual(spline.duration, 0.1)
        report = assess_spline_clearance(spline)
        self.assertTrue(report.admitted)
        certificate = report.continuous_certificate
        self.assertTrue(certificate.proven)
        self.assertEqual(certificate.interval_count, 1)
        self.assertEqual(self.interval_cover(certificate), [(0.0, 0.1)])
        self.assertEqual(certificate.domain_start_u, 0.0)
        self.assertEqual(certificate.domain_end_u, 0.1)
        # The single active set is the full control set (the only span there is).
        self.assertEqual(certificate.intervals[0][2:], (3, 3))
        self.assertEqual(certificate.control_point_count, 4)

    def test_malformed_certificate_structure_fails_closed(self):
        """A structurally broken spline must never be admitted by default."""
        spline = make_spline(clear_cps())
        spline.position._knots = list(spline.position._knots[:-1])   # knot cardinality broken
        report = assess_spline_clearance(spline)
        certificate = report.continuous_certificate
        self.assertFalse(certificate.proven)
        self.assertEqual(certificate.structural_reason, STRUCTURAL_CERTIFICATE_REASON)
        self.assertEqual(certificate.interval_count, 0)
        self.assertEqual(certificate.min_net_obstacle_clearance, -math.inf)
        self.assertFalse(report.admitted)
        self.assertEqual(report.violation["kind"], "continuous_clearance_unproven")
        self.assertEqual(report.violation["structural_reason"], STRUCTURAL_CERTIFICATE_REASON)
        self.assertFalse(report.continuous_proof)
        # The malformed-certificate case is decided by the certificate alone.
        self.assertGreaterEqual(report.min_obstacle_clearance, REQUIRED_CLEARANCE)

    def test_non_monotone_knots_fail_closed(self):
        spline = make_spline(clear_cps())
        knots = list(spline.position._knots)
        knots[5] = knots[4]
        spline.position._knots = knots
        certificate = certify_continuous_clearance(spline)
        self.assertFalse(certificate.proven)
        self.assertEqual(certificate.structural_reason, "non_monotone_knots")

    def test_certificate_rejects_malformed_inputs(self):
        self.assert_admission_error("invalid_binding", certify_continuous_clearance,
                                    make_spline(clear_cps()), binding=object())
        self.assert_admission_error("invalid_spline", certify_continuous_clearance, object())

    def test_legacy_mode_keeps_witness_admitted_and_labelled_sampled(self):
        """The pre-fix behaviour stays reachable, explicitly and unambiguously."""
        report = assess_spline_clearance(witness_spline(), strict_continuous=False)
        self.assertTrue(report.admitted)
        self.assertFalse(report.continuous_proof)
        self.assertEqual(report.evidence_kind, EVIDENCE_KIND)
        self.assertIsNone(report.continuous_certificate)
        self.assertIsNone(report.violation)

    def test_clear_polyline_certificate_is_fully_covered(self):
        spline = make_spline(clear_cps())
        certificate = certify_continuous_clearance(spline)
        self.assertTrue(certificate.proven)
        self.assertEqual(certificate.control_point_count, len(clear_cps()))
        self.assertEqual(certificate.knot_count, len(clear_cps()) + 4)
        self.assertEqual(certificate.interval_count, len(clear_cps()) - 3)
        self.assertEqual(certificate.order, 3)
        cover = self.interval_cover(certificate)
        self.assertAlmostEqual(cover[0][0], 0.0)
        self.assertAlmostEqual(cover[-1][1], spline.duration)
        self.assertTrue(all(cover[i][1] == cover[i + 1][0] for i in range(len(cover) - 1)))
        # Every interval's active set is a real p+1 window inside the control points.
        for _, _, first, last in certificate.intervals:
            self.assertEqual(last - first + 1, 1)             # uniform knots: one span each
            self.assertGreaterEqual(first, 3)
            self.assertLessEqual(last, certificate.control_point_count - 1)
            # The convex-hull bound is the p+1 control points P_{k-p}..P_k.
            active = spline.position._points[first - 3:last + 1]
            self.assertEqual(len(active), 4)


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

    def test_continuous_unproven_never_calls_adapter(self):
        """The audit witness must be rejected at the seam, atomically."""
        session, adapter, controller = make_controller()
        calls = spy_on_activate(adapter)
        before = session_snapshot(session)
        error = self.assert_admission_error(
            "continuous_clearance_unproven", controller.admit,
            make_mapping(witness_cps(), traj_id=1, knot_h=WITNESS_KNOT_H),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(len(calls), 0)                       # adapter untouched
        self.assertEqual(session_snapshot(session), before)   # session unchanged
        self.assertIsNotNone(error.report)
        self.assertFalse(error.report.admitted)
        self.assertEqual(error.report.violation["kind"], "continuous_clearance_unproven")
        self.assertGreaterEqual(error.report.min_obstacle_clearance, REQUIRED_CLEARANCE)
        self.assertFalse(error.report.continuous_proof)
        # The transport/caller burned nothing: the same traj_id can be retried
        # through the legacy channel and still activate exactly once.
        legacy = TrajectorySceneAdmission(adapter, anchor_ns=0, strict_continuous=False)
        report, accepted = legacy.admit(
            make_mapping(witness_cps(), traj_id=1, knot_h=WITNESS_KNOT_H),
            identity=identity_for(session), event_sequence=1, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(accepted, 1)
        self.assertEqual(len(calls), 1)
        self.assertFalse(report.continuous_proof)
        self.assertEqual(session.generation, 1)

    def test_construction_validates_strict_continuous(self):
        session = TrajectorySession(dict(IDENTITY))
        adapter = EgoTrajectoryAdapter(session)
        for bad in (1, 0, "yes", None):
            with self.subTest(bad=bad):
                with self.assertRaises(SceneAdmissionError) as ctx:
                    TrajectorySceneAdmission(adapter, anchor_ns=0, strict_continuous=bad)
                self.assertEqual(ctx.exception.reason, "invalid_grid")
        self.assertTrue(TrajectorySceneAdmission(adapter, anchor_ns=0)._strict_continuous)

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
