"""Independent equation/boundary checks; native original comparison is a tool."""

import hashlib
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Simulator"))
from wksim_control import NativeThrustConfig, PIDConfig, PIDReference, PIDState, select_controller
from wksim_control.position_pid import UPSTREAM_PID_PATH, UPSTREAM_PID_SHA256

ZERO = (0.0, 0.0, 0.0)
LEVEL = PIDState(ZERO, ZERO, (1.0, 0.0, 0.0, 0.0))


class PositionPIDTests(unittest.TestCase):
    def setUp(self):
        self.pid = select_controller("pid", PIDConfig(mass_kg=2.0))

    def update(self, reference, state=LEVEL, dt=0.01, active=True):
        return self.pid.update(state, reference, dt_s=dt, external_control_active=active)

    def test_original_source_pin(self):
        self.assertEqual(hashlib.sha256((ROOT / UPSTREAM_PID_PATH).read_bytes()).hexdigest(), UPSTREAM_PID_SHA256)

    def test_hover_force_and_stack_specific_mapping(self):
        result = self.update(PIDReference(ZERO))
        self.assertEqual(result.force_enu_n, (0.0, 0.0, 19.6))
        self.assertEqual(result.roll_pitch_yaw_enu_rad, ZERO)
        # Test fixtures only: runtime must supply evidence-bound calibrations.
        for stack, hover in (("arducopter", 0.313), ("px4", 0.531)):
            config = NativeThrustConfig(stack, "fixture-sha256", 2.0, hover)
            self.assertAlmostEqual(config.normalized_collective(result, model_identity="fixture-sha256"), hover)
            with self.assertRaises(ValueError):
                config.normalized_collective(result, model_identity="different-model")
            with self.assertRaises(ValueError):
                NativeThrustConfig(stack, "fixture-sha256", 1.0, hover).normalized_collective(result, model_identity="fixture-sha256")

    def test_feedback_feedforward_and_position_integral(self):
        ref = PIDReference((0.1, -0.1, 0.25), acceleration_enu=(0.3, -0.2, 0.4))
        out = self.update(ref, dt=0.1)
        self.assertEqual(out.integral, (0.010000000000000002, -0.010000000000000002, 0.025))
        for actual, expected in zip(out.acceleration_enu, (0.503, -0.403, 0.9075)):
            self.assertAlmostEqual(actual, expected)

    def test_discontinuous_original_error_limits(self):
        a = self.update(PIDReference((3.0, -3.0, 3.0), velocity_enu=(3.0, -3.0, 3.0)))
        b = self.update(PIDReference((3.001, -3.001, 3.001), velocity_enu=(3.001, -3.001, 3.001)))
        self.assertEqual(a.acceleration_enu, (12.0, -12.0, 12.0))
        self.assertEqual(b.acceleration_enu, (6.0, -6.0, 6.0))

    def test_integral_gate_saturation_and_mode(self):
        self.pid = select_controller("pid", PIDConfig(2.0, integral_limit=(0.02, 0.02, 0.02)))
        ref = PIDReference((0.1, -0.1, 0.25))
        for _ in range(20):
            result = self.update(ref, dt=0.1)
        self.assertEqual(result.integral, (0.02, -0.02, 0.02))
        self.assertEqual(self.update(ref, active=False).integral, ZERO)
        self.assertEqual(self.update(PIDReference((0.21, -0.21, 0.5))).integral, ZERO)
        # Preserve the float32 0.2 gate from the source rather than rounding it.
        self.assertGreater(self.update(PIDReference((0.2, 0.2, 0.0))).integral[0], 0)

    def test_moving_reference_resets_then_integrates_one_sample(self):
        ref = PIDReference((0.1, 0.1, 0.1), velocity_enu=(0.01, 0.0, 0.0))
        first = self.update(ref, dt=0.1)
        self.assertEqual(first.integral, self.update(ref, dt=0.1).integral)
        self.assertAlmostEqual(first.integral[0], 0.01)

    def test_reset_and_selection_do_not_retain_previous_integral(self):
        self.update(PIDReference((0.1, 0.1, 0.1)))
        self.pid.reset("native ownership lost")
        self.assertEqual(self.pid.integral, ZERO)
        self.assertEqual(self.pid.last_reset_reason, "native ownership lost")
        self.assertEqual(select_controller("pid", self.pid.config).integral, ZERO)
        for name in ("ude", "ne", "default", "PID", "", None):
            with self.assertRaises(ValueError):
                select_controller(name, self.pid.config)

    def test_vertical_scaling_and_per_axis_tilt_are_original(self):
        low = self.update(PIDReference(ZERO, acceleration_enu=(2.0, -2.0, -8.0)))
        self.assertAlmostEqual(low.force_enu_n[2], 9.8)
        limit = 9.8 * math.tan(math.radians(10))
        self.assertAlmostEqual(low.force_enu_n[0], limit)
        self.assertAlmostEqual(low.force_enu_n[1], -limit)
        high = self.update(PIDReference(ZERO, acceleration_enu=(0.0, 0.0, 30.0)))
        self.assertAlmostEqual(high.force_enu_n[2], 39.2)
        negative = self.update(PIDReference(ZERO, acceleration_enu=(1.0, 0.0, -20.0)))
        self.assertLess(negative.force_enu_n[0], 0.0)  # Original negative-z rescale flips X.
        self.assertAlmostEqual(negative.force_enu_n[2], 9.8)

    def test_current_yaw_rotation_and_current_body_projection(self):
        q = (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
        out = self.update(PIDReference(ZERO, acceleration_enu=(1.0, 0.0, 0.0), yaw_enu_rad=-0.7),
                          PIDState(ZERO, ZERO, q))
        self.assertAlmostEqual(out.roll_pitch_yaw_enu_rad[0], math.atan2(2.0, 19.6))
        self.assertAlmostEqual(out.roll_pitch_yaw_enu_rad[1], 0.0)
        self.assertEqual(out.roll_pitch_yaw_enu_rad[2], -0.7)
        angle = math.radians(30)
        out = self.update(PIDReference(ZERO), PIDState(ZERO, ZERO, (math.cos(angle / 2), math.sin(angle / 2), 0.0, 0.0)))
        self.assertAlmostEqual(out.projected_thrust_n, 19.6 * math.cos(angle))

    def test_thrust_clamps_match_original(self):
        upside_down = PIDState(ZERO, ZERO, (0.0, 1.0, 0.0, 0.0))
        mapping = NativeThrustConfig("px4", "test", 2.0, 0.8)
        low = self.update(PIDReference(ZERO), upside_down)
        high = self.update(PIDReference(ZERO, acceleration_enu=(0.0, 0.0, 20.0)))
        self.assertEqual(mapping.normalized_collective(low, model_identity="test"), 0.1)
        self.assertEqual(mapping.normalized_collective(high, model_identity="test"), 1.0)

    def test_invalid_inputs_and_atomic_undefined_zero_force(self):
        ref = PIDReference((0.1, 0.1, 0.1))
        self.update(ref)
        previous = self.pid.integral
        for dt in (0.0, -1.0, math.inf, math.nan, True):
            with self.assertRaises(ValueError):
                self.update(ref, dt=dt)
            self.assertEqual(self.pid.integral, previous)
        with self.assertRaises(ValueError):
            self.update(PIDReference((0.1, 0.1, 0.5), acceleration_enu=(0.0, 0.0, -10.8)))
        self.assertEqual(self.pid.integral, previous)
        with self.assertRaises(ValueError):
            self.update(ref, active="OFFBOARD")
        for q in ((0, 0, 0, 0), (1, 0, 0), (math.nan, 0, 0, 0), (2, 0, 0, 0)):
            with self.assertRaises(ValueError):
                PIDState(ZERO, ZERO, q)
        for mass in (0, -1, math.inf, math.nan, True):
            with self.assertRaises(ValueError):
                PIDConfig(mass)
        with self.assertRaises(ValueError):
            PIDReference((math.inf, 0.0, 0.0))

    def test_deterministic_step_trace_and_dt_partition(self):
        ref = PIDReference((0.1, 0.1, 0.1))
        first = [self.update(ref, dt=0.01) for _ in range(40)]
        self.pid.reset("replay")
        second = [self.update(ref, dt=0.01) for _ in range(40)]
        self.assertEqual(first, second)
        self.pid.reset("different cadence")
        for _ in range(20):
            result = self.update(ref, dt=0.02)
        for a, b in zip(first[-1].integral, result.integral):
            self.assertAlmostEqual(a, b)


if __name__ == "__main__":
    unittest.main()
