"""Deterministic offline tests for the #102 EGO -> TrajectorySession adapter slice.

No ROS, no planner, no point cloud, no SITL/UE/MATLAB, no wall clock. The spline is
built by the pure evaluator (ego_evaluator.py) from explicitly supplied uniform or
lengthened/non-uniform order-3 control points + knots; the session (trajectory_session.py)
is the single command-id writer. The upstream trajectory_id is supplied explicitly and must
strictly increase within uint32; the adapter never mints one and never evaluates a yaw curve
(yaw is a mandatory explicit finite fallback).
"""
import unittest

from Simulator.wksim_planning.ego_evaluator import (
    DEFAULT_ORDER,
    EgoSpline,
    SplineError,
    UniformBspline,
)
from Simulator.wksim_planning.ego_trajectory_adapter import (
    MAX_TICK,
    MAX_TRAJECTORY_ID,
    SAMPLE_STRIDE_TICKS,
    AdapterError,
    EgoTrajectoryAdapter,
    seconds_to_tick,
    tick_to_seconds,
)
from Simulator.wksim_planning.trajectory_session import (
    MAX_COMMAND_ID,
    MAX_GENERATION,
    TrajectorySession,
)

IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1, control_epoch="epoch-a",
                planner_generation=0, command_high_water=0)


def identity(session):
    value = dict(IDENTITY)
    value["planner_generation"] = session.generation
    return value


def straight_spline(scale=0.5, points=7, knots=None, order=DEFAULT_ORDER):
    """A straight, constant-altitude ENU order-3 path; deterministic and finite."""
    cps = [(float(i) * scale, 0.0, 1.0) for i in range(points)]
    return EgoSpline(order, knots, cps)


def make_adapter():
    session = TrajectorySession(IDENTITY)
    return session, EgoTrajectoryAdapter(session)


def activate(session, adapter, spline, trajectory_id=1, start_tick=0, start_event=1,
             fallback_yaw=0.0):
    adapter.begin_replan(identity(session), start_event)
    return adapter.activate(spline, trajectory_id, start_tick, identity(session),
                            fallback_yaw=fallback_yaw)


class EvaluatorTests(unittest.TestCase):
    """Evaluator endpoints / interior reproduce the upstream uniform de Boor math."""

    def test_constant_control_points_give_constant_curve_and_zero_derivatives(self):
        spline = UniformBspline(3, [(1.0, 2.0, 3.0)] * 6, 0.1)
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            t = spline.duration * frac
            self.assertEqual(spline.evaluate_t(t), (1.0, 2.0, 3.0))
            self.assertEqual(spline.derivative().evaluate_t(t), (0.0, 0.0, 0.0))
            self.assertEqual(spline.derivative().derivative().evaluate_t(t), (0.0, 0.0, 0.0))

    def test_linear_control_points_interpolate_linearly(self):
        spline = UniformBspline(3, [(float(i), 0.0, 0.0) for i in range(6)], 0.1)
        self.assertAlmostEqual(spline.evaluate_t(0.0)[0], 1.0)
        self.assertAlmostEqual(spline.evaluate_t(spline.duration)[0], 4.0)
        samples = [spline.evaluate_t(spline.duration * f / 10)[0] for f in range(11)]
        for i in range(len(samples) - 1):
            self.assertGreaterEqual(samples[i + 1], samples[i] - 1e-9)  # monotone
        mid = spline.evaluate_t(spline.duration / 2)
        self.assertAlmostEqual(mid[0], 2.5, places=9)
        self.assertAlmostEqual(mid[1], 0.0)
        self.assertAlmostEqual(mid[2], 0.0)

    def test_evaluator_endpoint_and_interior_differ_for_curved_path(self):
        spline = UniformBspline(3, [(0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (1.0, 4.0, 0.5),
                                    (3.0, 4.0, 1.5), (4.0, 1.0, 2.5), (4.0, 0.0, 3.0)], 0.1)
        start = spline.evaluate_t(0.0)
        interior = spline.evaluate_t(spline.duration / 2)
        self.assertNotEqual(start, interior)
        self.assertTrue(all(map(lambda a, b: abs(a - b) > 1e-6, start, interior)))

    def test_malformed_control_points_rejected(self):
        with self.assertRaises(SplineError):
            UniformBspline(3, [(0.0, 0.0)])            # 2-vector, not 3
        with self.assertRaises(SplineError):
            UniformBspline(3, [(0.0, 0.0, float('nan'))] * 5)  # non-finite
        with self.assertRaises(SplineError):
            UniformBspline(3, [(0.0, 0.0, 0.0)] * 3)   # fewer than order+1
        with self.assertRaises(SplineError):
            UniformBspline(0, [(0.0, 0.0, 0.0)] * 5)   # order 0
        with self.assertRaises(SplineError):
            UniformBspline(3, [])                       # empty

    def test_nonuniform_lengthened_knots_accepted_and_differ(self):
        # Real EGO output lengthens interior knots (lengthenTime), so the uniform layout is
        # not the only valid input. A strictly increasing, exact-length knot vector is used.
        base = UniformBspline(3, [(float(i), 0.0, 0.0) for i in range(6)], 0.1)
        lengthened = list(base.knots)
        lengthened[6] += 0.05                       # still strictly increasing
        spline = UniformBspline(3, [(float(i), 0.0, 0.0) for i in range(6)], 0.1,
                                knots=lengthened)
        self.assertEqual(list(spline.knots), lengthened)
        self.assertGreater(spline.duration, base.duration)   # lengthened -> longer domain
        # The curve changes where the interior knot moved.
        self.assertNotAlmostEqual(spline.evaluate_t(0.2)[0], base.evaluate_t(0.2)[0], places=6)

    def test_nonuniform_derivative_uses_current_knots_and_cuts_ends(self):
        base = UniformBspline(3, [(float(i), 0.0, 0.0) for i in range(6)], 0.1)
        lengthened = list(base.knots)
        lengthened[6] += 0.05
        spline = UniformBspline(3, [(float(i), 0.0, 0.0) for i in range(6)], 0.1,
                                knots=lengthened)
        deriv = spline.derivative()
        # Upstream getDerivative cuts the parent's FIRST and LAST knot.
        self.assertEqual(list(deriv.knots), lengthened[1:-1])
        self.assertEqual(deriv.order, 2)
        # Q_i = p*(P_{i+1}-P_i)/(u(i+p+1)-u(i+1)) with the CURRENT (lengthened) knots.
        p, i = 3, 2
        expected = p * ((i + 1) - i) / (lengthened[i + p + 1] - lengthened[i + 1])
        self.assertAlmostEqual(deriv._points[i][0], expected, places=12)
        # The moved interior knot changes the derivative there.
        base_deriv = base.derivative()
        self.assertNotAlmostEqual(deriv._points[i][0], base_deriv._points[i][0], places=6)

    def test_malformed_knots_rejected(self):
        cps = [(float(i), 0.0, 0.0) for i in range(6)]
        base = UniformBspline(3, cps, 0.1)
        good = base.knots
        with self.assertRaises(SplineError):
            UniformBspline(3, cps, 0.1, knots=good[:-1])               # wrong length
        with self.assertRaises(SplineError):
            UniformBspline(3, cps, 0.1, knots=[0.0] * len(good))       # not increasing
        reversed_knots = list(reversed(good))
        with self.assertRaises(SplineError):
            UniformBspline(3, cps, 0.1, knots=reversed_knots)          # non-monotonic
        repeated = list(good); repeated[5] = repeated[4]               # repeat
        with self.assertRaises(SplineError):
            UniformBspline(3, cps, 0.1, knots=repeated)
        nonfinite = list(good); nonfinite[3] = float('inf')
        with self.assertRaises(SplineError):
            UniformBspline(3, cps, 0.1, knots=nonfinite)

    def test_non_ego_order_rejected_at_construction(self):
        # Only the real EGO order (3) is accepted; order 1/2 would otherwise fail later at
        # the adapter's acceleration (second-derivative) evaluation.
        for order in (1, 2, 4, 0):
            with self.assertRaises(SplineError):
                straight_spline(order=order)

    def test_scalar_position_control_points_rejected_at_construction(self):
        # An EGO position payload is always 3-vector (ENU). A scalar control-point sequence
        # must fail closed at EgoSpline construction, not later at the adapter's step.
        with self.assertRaises(SplineError):
            EgoSpline(3, None, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])       # scalars
        with self.assertRaises(SplineError):
            EgoSpline(3, None, [(0.0,), (1.0,), (2.0,), (3.0,), (4.0,), (5.0,)])  # 1-vectors
        # A 2-vector is also not a valid 3-vector ENU point.
        with self.assertRaises(SplineError):
            EgoSpline(3, None, [(0.0, 0.0)] * 6)


class AdapterActivationTests(unittest.TestCase):
    def test_activation_accepts_current_generation(self):
        session, adapter = make_adapter()
        trajectory_id = activate(session, adapter, straight_spline(), trajectory_id=1)
        self.assertEqual(session.state, "ACTIVE")
        self.assertEqual(adapter.trajectory_id, 1)
        self.assertEqual(trajectory_id, 1)

    def test_activation_requires_explicit_start_tick_id_and_yaw(self):
        session, adapter = make_adapter()
        adapter.begin_replan(identity(session), 1)
        with self.assertRaises(AdapterError):
            adapter.activate("not-a-spline", 1, 0, identity(session), fallback_yaw=0.0)
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(), -1, 0, identity(session), fallback_yaw=0.0)
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(), 1, -5, identity(session), fallback_yaw=0.0)
        # fallback yaw is mandatory and must be finite.
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(), 1, 0, identity(session), fallback_yaw=None)
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(), 1, 0, identity(session),
                             fallback_yaw=float('nan'))
        # A zero-duration (degenerate) payload is rejected.
        degenerate = UniformBspline(3, [(1.0, 1.0, 1.0)] * 4, 0.1)
        with self.assertRaises(AdapterError):
            adapter.activate(degenerate, 1, 0, identity(session), fallback_yaw=0.0)

    def test_frame_mismatch_rejected(self):
        session = TrajectorySession(IDENTITY)
        with self.assertRaises(AdapterError):
            EgoTrajectoryAdapter(session, frame="ned")

    def test_explicit_fallback_yaw_used(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1, fallback_yaw=0.7)
        out = adapter.step(identity(session), 0, True, True)
        self.assertAlmostEqual(out["yaw_ref"], 0.7)

    def test_trajectory_end_falls_to_hold(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        end_tick = adapter._active_end_tick
        for tick in range(0, end_tick, SAMPLE_STRIDE_TICKS):
            adapter.step(identity(session), tick, True, True)
        # end_tick is the last tick the final sample is valid for; one past it -> HOLD.
        out = adapter.step(identity(session), end_tick + 1, True, True)
        self.assertEqual((session.state, out["intent"], out["move_mode"]), ("HOLD", "hold", 0))
        self.assertEqual(out["velocity_ref"], [0.0, 0.0, 0.0])  # never extends last velocity


class AdapterIdentityTests(unittest.TestCase):
    """A wrong identity fails BEFORE any feed, state change, or tick advance."""

    def test_wrong_identity_rejected_on_stride_tick(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)   # feed tick 0, _next_tick -> 10
        next_tick = adapter._next_tick
        last_tick = adapter._last_tick
        wrong = dict(identity(session), mission_id="other")
        with self.assertRaises(AdapterError):
            adapter.step(wrong, 10, True, True)
        # No feed, no state change, no tick advance.
        self.assertEqual(adapter._next_tick, next_tick)
        self.assertEqual(adapter._last_tick, last_tick)
        self.assertEqual(session.state, "ACTIVE")

    def test_wrong_identity_rejected_on_non_stride_tick(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        next_tick = adapter._next_tick
        wrong = dict(identity(session), run_id="other")
        with self.assertRaises(AdapterError):
            adapter.step(wrong, 5, True, True)           # 5 is not a stride tick
        self.assertEqual(adapter._next_tick, next_tick)
        self.assertEqual(session.state, "ACTIVE")

    def test_wrong_identity_rejected_before_lost_control(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        next_tick = adapter._next_tick
        wrong = dict(identity(session), control_epoch="other")
        # Even a lost-control tick must not be processed under a wrong identity.
        with self.assertRaises(AdapterError):
            adapter.step(wrong, 10, False, True)
        self.assertEqual(adapter._next_tick, next_tick)
        self.assertEqual(session.state, "ACTIVE")        # NOT released

    def test_wrong_identity_rejected_on_next_output_wrapper(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        last_tick = adapter._last_tick
        wrong = dict(identity(session), uav_id=2)
        with self.assertRaises(AdapterError):
            adapter.next_output(wrong, 10, True, True)
        self.assertEqual(adapter._last_tick, last_tick)  # tick high-water untouched

    def test_wrong_generation_rejected(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        wrong = dict(identity(session), planner_generation=session.generation + 9)
        with self.assertRaises(AdapterError):
            adapter.step(wrong, 0, True, True)
        with self.assertRaises(AdapterError):
            adapter.begin_replan(wrong, 5)
        with self.assertRaises(AdapterError):
            adapter.cancel(wrong, 5)


class AdapterTickMonotonicityTests(unittest.TestCase):
    """The adapter holds its own last-tick high-water, checked before any feed."""

    def test_repeated_tick_rejected_before_feed(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        next_tick = adapter._next_tick
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 0, True, True)   # repeat tick 0
        self.assertEqual(adapter._next_tick, next_tick)      # no extra feed

    def test_regressed_tick_rejected_before_feed(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        for tick in range(0, 30, SAMPLE_STRIDE_TICKS):
            adapter.step(identity(session), tick, True, True)
        next_tick = adapter._next_tick
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 10, True, True)  # regress below last (20)
        self.assertEqual(adapter._next_tick, next_tick)

    def test_next_output_advances_tick_high_water(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        # A stream-free query still advances the adapter's tick high-water.
        adapter.next_output(identity(session), 5, True, True)
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 5, True, True)   # repeat after query

    def test_replan_cannot_regress_below_walked_tick(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1, start_tick=0)
        for tick in range(0, 100, SAMPLE_STRIDE_TICKS):      # step up to tick 90
            adapter.step(identity(session), tick, True, True)
        adapter.step(identity(session), 100, True, True)     # observe tick 100 (past end)
        # Replan; the new trajectory must start strictly AFTER the highest observed tick.
        adapter.begin_replan(identity(session), 3)
        state_before = session.state                          # HOLD after replan
        self.assertIsNone(adapter._next_tick)                 # replan cleared the feed cursor
        # start == highest observed tick (100) is rejected: it would point the feed cursor
        # at an already-consumed tick, so a strictly-increasing step could never feed it.
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(0.7), 2, 100, identity(session),
                             fallback_yaw=0.0)
        # A regressed start (< highest observed) is also rejected; neither fed anything.
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(0.7), 2, 50, identity(session),
                             fallback_yaw=0.0)
        self.assertEqual(session.state, state_before)
        self.assertIsNone(adapter._next_tick)
        # A strictly greater start (110 > 100) is accepted, and step(110) emits a trajectory.
        adapter.activate(straight_spline(0.7), 2, 110, identity(session), fallback_yaw=0.0)
        self.assertEqual(adapter.trajectory_id, 2)
        out = adapter.step(identity(session), 110, True, True)
        self.assertEqual(out["intent"], "trajectory")
        self.assertEqual(out["trajectory_id"], 2)


class AdapterAtomicReplanTests(unittest.TestCase):
    @staticmethod
    def snapshot(session, adapter):
        return (
            session.state,
            session.generation,
            session.last_event_sequence,
            session.last_command_id,
            session._trajectory,
            session._sample,
            session._last_sample_tick,
            session._last_output_tick,
            session._hold_anchor,
            session._last_reason,
            adapter.trajectory_id,
            adapter._last_tick,
            adapter._active_spline,
            adapter._active_start_tick,
            adapter._active_end_tick,
            adapter._fallback_yaw,
            adapter._next_tick,
        )

    def test_replan_and_activate_commits_once_and_streams_every_ten_ticks(self):
        session = TrajectorySession(dict(IDENTITY, command_high_water=40))
        adapter = EgoTrajectoryAdapter(session)
        accepted = adapter.replan_and_activate(
            identity(session), 1, straight_spline(), 1, 0, 0.0
        )

        self.assertEqual(accepted, 1)
        self.assertEqual((session.state, session.generation,
                          session.last_event_sequence), ("ACTIVE", 1, 1))
        outputs = [
            adapter.step(identity(session), tick, True, True)
            for tick in (0, 10, 20)
        ]
        self.assertEqual([output["tick"] for output in outputs], [0, 10, 20])
        self.assertEqual([output["command_id"] for output in outputs], [41, 42, 43])
        self.assertTrue(all(output["trajectory_id"] == 1 for output in outputs))

    def test_replan_and_activate_rejections_never_mutate_session_or_adapter(self):
        session, adapter = make_adapter()
        adapter.replan_and_activate(
            identity(session), 1, straight_spline(), 1, 0, 0.0
        )
        adapter.step(identity(session), 0, True, True)
        before = self.snapshot(session, adapter)
        empty = straight_spline()
        empty.duration = 0.0
        negative = straight_spline()
        negative.duration = -1.0
        non_finite = straight_spline()
        non_finite.duration = float("nan")

        invalid_calls = (
            (identity(session), 2, straight_spline(), 1, 10, 0.0),
            (identity(session), 2, straight_spline(), 0, 10, 0.0),
            (identity(session), 2, straight_spline(), 2, 0, 0.0),
            (identity(session), 2, object(), 2, 10, 0.0),
            (identity(session), 2, empty, 2, 10, 0.0),
            (identity(session), 2, negative, 2, 10, 0.0),
            (identity(session), 2, non_finite, 2, 10, 0.0),
            (identity(session), 2, straight_spline(), 2, 10, float("nan")),
            (identity(session), 2, straight_spline(), 2, MAX_TICK, 0.0),
            (identity(session), True, straight_spline(), 2, 10, 0.0),
            (identity(session), 1, straight_spline(), 2, 10, 0.0),
            (identity(session), MAX_COMMAND_ID + 1,
             straight_spline(), 2, 10, 0.0),
            (dict(IDENTITY, run_id="other", planner_generation=session.generation),
             2, straight_spline(), 2, 10, 0.0),
            (dict(IDENTITY, planner_generation=session.generation + 1),
             2, straight_spline(), 2, 10, 0.0),
        )
        for call in invalid_calls:
            with self.subTest(event=call[1], trajectory_id=call[3]):
                with self.assertRaises((AdapterError, ValueError)):
                    adapter.replan_and_activate(*call)
                self.assertEqual(self.snapshot(session, adapter), before)

    def test_replan_and_activate_rejects_terminal_session_without_mutation(self):
        session, adapter = make_adapter()
        session.stop("cancel", identity(session), 1)
        before = self.snapshot(session, adapter)

        with self.assertRaises((AdapterError, ValueError)):
            adapter.replan_and_activate(
                identity(session), 2, straight_spline(), 1, 0, 0.0
            )

        self.assertEqual(self.snapshot(session, adapter), before)

    def test_replan_and_activate_rejects_generation_overflow_without_mutation(self):
        session = TrajectorySession(dict(IDENTITY, planner_generation=MAX_GENERATION))
        adapter = EgoTrajectoryAdapter(session)
        before = self.snapshot(session, adapter)

        with self.assertRaises(AdapterError):
            adapter.replan_and_activate(
                identity(session), 1, straight_spline(), 1, 0, 0.0
            )

        self.assertEqual(self.snapshot(session, adapter), before)


class AdapterReplanAndExpiryTests(unittest.TestCase):
    def test_late_replan_at_higher_monotonic_tick(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1, start_tick=0)
        end_tick = adapter._active_end_tick
        for tick in range(0, end_tick, SAMPLE_STRIDE_TICKS):
            adapter.step(identity(session), tick, True, True)
        # Replan: the authority tick is monotonic and never resets; the new trajectory
        # starts at the current (higher) tick, not at 0.
        adapter.begin_replan(identity(session), 3)
        adapter.activate(straight_spline(scale=0.7), 2, end_tick, identity(session),
                         fallback_yaw=0.0)
        self.assertEqual(adapter.trajectory_id, 2)
        out = adapter.step(identity(session), end_tick, True, True)
        self.assertEqual(out["intent"], "trajectory")

    def test_stale_generation_rejected(self):
        session, adapter = make_adapter()
        generation = adapter.begin_replan(identity(session), 1)
        adapter.begin_replan(identity(session), 3)   # generation bumped again -> 1 is stale
        stale_identity = dict(IDENTITY, planner_generation=generation)
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(), 1, 0, stale_identity, fallback_yaw=0.0)

    def test_sample_expiry_falls_to_hold(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)   # feed tick 0 (valid_until=10)
        out = adapter.step(identity(session), 25, True, True)  # lapse past valid_until
        self.assertEqual((session.state, out["intent"]), ("HOLD", "hold"))

    def test_cancel_rejects_late_sample_and_blocks_output(self):
        session, adapter = make_adapter()
        generation = activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        adapter.cancel(identity(session), 3)
        self.assertEqual(session.state, "CANCELLED")
        self.assertIsNone(session.next_output(10, True, True))
        with self.assertRaises(ValueError):
            session.sample(dict(IDENTITY, planner_generation=generation), generation, 1,
                           10, (0, 0, 0), (0, 0, 0), (0, 0, 0), 0.0)


class AdapterSafetyTests(unittest.TestCase):
    def test_lost_control_feeds_no_sample(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        next_tick = adapter._next_tick                       # adapter's next stride tick
        out = adapter.step(identity(session), 10, False, True)   # control lost at tick 10
        # Safety first: no evaluation, no feed -- the adapter's feed cursor does not move,
        # and the session emits no trajectory (it transitions to RELEASED).
        self.assertIsNone(out)
        self.assertEqual(session.state, "RELEASED")
        self.assertEqual(adapter._next_tick, next_tick)

    def test_stale_state_feeds_no_sample(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        next_tick = adapter._next_tick
        out = adapter.step(identity(session), 10, True, False)   # state stale
        self.assertIsNone(out)
        self.assertEqual(session.state, "FAULTED")
        self.assertEqual(adapter._next_tick, next_tick)

    def test_safety_flags_must_be_bool(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 0, 1, True)          # owns_control not bool
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 0, True, 0)          # state_fresh not bool

    def test_safety_path_records_tick_high_water(self):
        # A lost-control step still records the observed tick on the adapter high-water, so
        # a subsequent repeated or regressed tick is rejected at the adapter layer.
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        out = adapter.step(identity(session), 10, False, True)   # lost control at tick 10
        self.assertIsNone(out)
        self.assertEqual(session.state, "RELEASED")
        self.assertEqual(adapter._last_tick, 10)                  # safety path recorded it
        # Repeating or regressing below the recorded tick is now rejected at the adapter.
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 10, False, True)      # repeat
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 5, False, True)       # regress

    def test_stale_state_records_tick_high_water(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)
        out = adapter.step(identity(session), 10, True, False)   # stale state at tick 10
        self.assertIsNone(out)
        self.assertEqual(session.state, "FAULTED")
        self.assertEqual(adapter._last_tick, 10)
        with self.assertRaises(AdapterError):
            adapter.step(identity(session), 10, True, False)     # repeat after stale


class AdapterIdMonotonicityTests(unittest.TestCase):
    def test_trajectory_id_must_strictly_increase(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=5, start_tick=0)
        adapter.begin_replan(identity(session), 3)
        # Reusing or lowering the upstream trajectory_id is stale -> rejected.
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(0.7), 5, 0, identity(session), fallback_yaw=0.0)
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(0.7), 4, 0, identity(session), fallback_yaw=0.0)
        # A strictly greater id is accepted.
        adapter.activate(straight_spline(0.7), 6, 0, identity(session), fallback_yaw=0.0)
        self.assertEqual(adapter.trajectory_id, 6)

    def test_trajectory_id_uint32_overflow_rejected(self):
        session, adapter = make_adapter()
        adapter.begin_replan(identity(session), 1)
        adapter.activate(straight_spline(), MAX_TRAJECTORY_ID, 0, identity(session),
                         fallback_yaw=0.0)
        adapter.begin_replan(identity(session), 3)
        with self.assertRaises(AdapterError):
            adapter.activate(straight_spline(0.7), MAX_TRAJECTORY_ID + 1, 0, identity(session),
                             fallback_yaw=0.0)

    def test_command_ids_strictly_increase_across_replan(self):
        session, adapter = make_adapter()
        activate(session, adapter, straight_spline(), trajectory_id=1, start_tick=0)
        ids = []
        for tick in range(0, 40, SAMPLE_STRIDE_TICKS):
            ids.append(adapter.step(identity(session), tick, True, True)["command_id"])
        end_tick = adapter._active_end_tick
        # Replan; ticks never reset (a real run's authority tick is monotonic).
        adapter.begin_replan(identity(session), 3)
        adapter.activate(straight_spline(0.7), 2, end_tick, identity(session), fallback_yaw=0.0)
        for tick in range(end_tick, end_tick + 40, SAMPLE_STRIDE_TICKS):
            out = adapter.step(identity(session), tick, True, True)
            if out is not None:
                ids.append(out["command_id"])
        self.assertTrue(all(ids[i + 1] > ids[i] for i in range(len(ids) - 1)))
        self.assertEqual(adapter.trajectory_id, 2)

    def test_command_id_overflow_faults(self):
        # High water = MAX-2: the two fed strides consume MAX-1 then MAX; the next
        # output needs MAX+1, which overflows and faults the session.
        session = TrajectorySession(dict(IDENTITY, command_high_water=MAX_COMMAND_ID - 2))
        adapter = EgoTrajectoryAdapter(session)
        activate(session, adapter, straight_spline(), trajectory_id=1)
        adapter.step(identity(session), 0, True, True)    # command_id MAX-1
        adapter.step(identity(session), 10, True, True)   # command_id MAX
        # tick 20 still serves the tick-10 sample (valid_until 20); allocating it overflows.
        with self.assertRaises(OverflowError):
            session.next_output(20, True, True)
        self.assertEqual(session.state, "FAULTED")


class AdapterGridTests(unittest.TestCase):
    def test_off_grid_time_rejected(self):
        with self.assertRaises(AdapterError):
            seconds_to_tick(0.0105)   # not an exact 1 ms multiple
        self.assertEqual(seconds_to_tick(0.01), 10)
        self.assertEqual(tick_to_seconds(10), 0.01)

    def test_nonfinite_evaluated_value_fails_closed(self):
        # The evaluator rejects non-finite control points before the adapter ever runs.
        with self.assertRaises(SplineError):
            EgoSpline(3, None, [(0.0, 0.0, float('inf'))] * 7)


if __name__ == "__main__":
    unittest.main()
