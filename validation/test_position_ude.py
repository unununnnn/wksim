"""Pure UDE contract and failure-boundary tests; no native runtime."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"Simulator"))
from wksim_control.position_ude import UDEConfig, PositionUDE
from wksim_control.position_pid import PIDState, PIDReference, NativeThrustConfig

STATE = PIDState((0, 0, 0), (0, 0, 0), (1, 0, 0, 0))


class UDETests(unittest.TestCase):
    def setUp(self):
        self.ude = PositionUDE(UDEConfig(2))

    def update(self, ref=None, **kwargs):
        return self.ude.update(STATE, ref or PIDReference((0, 0, 0)),
                               dt_s=kwargs.get("dt", 0.01), external_control_active=kwargs.get("active", True))

    def test_hover_and_mapping(self):
        out = self.update()
        self.assertEqual(out.controller, "ude")
        self.assertEqual(out.force_enu_n, (0, 0, 19.6))
        self.assertEqual(out.integral, (0, 0, 0))
        mapping = NativeThrustConfig("px4", "test-model", 2, 0.5)
        self.assertEqual(mapping.normalized_collective(out, model_identity="test-model"), 0.5)
        with self.assertRaises(ValueError):
            mapping.normalized_collective(out, model_identity="other")

    def test_old_integral_and_sign(self):
        ref = PIDReference((0.25, 0, 0))
        first, second = self.update(ref), self.update(ref)
        self.assertEqual(first.nominal_acceleration_enu[0], 0.125)
        self.assertEqual(first.disturbance_acceleration_enu[0], -0.5)
        self.assertEqual(first.acceleration_enu[0], 0.625)
        self.assertAlmostEqual(second.disturbance_acceleration_enu[0], -0.50125)

    def test_error_clamp_is_three(self):
        self.assertEqual(self.update(PIDReference((4, -4, 0))).nominal_acceleration_enu, (1.5, -1.5, 0))

    def test_threshold_clear_uses_old_integral(self):
        self.update(PIDReference((0.25, 0, 0)), dt=1)
        self.ude = PositionUDE(UDEConfig(2, disturbance_limit=(100,)*3))
        self.update(PIDReference((0.25, 0, 0)), dt=1)
        out = self.update(PIDReference((0.5, 0, 0)))
        self.assertEqual(out.integral[0], 0)
        self.assertEqual(out.disturbance_acceleration_enu[0], -1.125)

    def test_disturbance_limit_does_not_limit_integral(self):
        for _ in range(10):
            out = self.update(PIDReference((0.25, -0.25, 0)), dt=1)
        self.assertEqual(out.integral[:2], (2.5, -2.5))
        self.assertEqual(out.disturbance_acceleration_enu[:2], (-1, 1))

    def test_moving_reference_does_not_reset(self):
        ref = PIDReference((0.25, 0, 0), (0.1, 0, 0))
        self.update(ref)
        self.assertEqual(self.update(ref).integral[0], 0.005)

    def test_reset_all_history(self):
        ref = PIDReference((0.25, 0, 0))
        fresh = self.update(ref)
        self.update(ref)
        self.ude.reset("controller switch")
        self.assertIsNone(self.ude.last_output)
        self.assertEqual(self.ude.integral, (0, 0, 0))
        self.assertEqual(self.update(ref), fresh)
        with self.assertRaises(ValueError):
            self.ude.reset("")

    def test_inactive_clears_and_rejects(self):
        self.update(PIDReference((0.25, 0, 0)))
        with self.assertRaisesRegex(ValueError, "inactive"):
            self.update(active=False)
        self.assertEqual(self.ude.integral, (0, 0, 0))
        self.assertIsNone(self.ude.last_output)

    def test_invalid_cycle_preserves_state(self):
        before = self.update(PIDReference((0.25, 0, 0)))
        for dt in (0, -1, math.nan, math.inf, True):
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                self.update(dt=dt)
            self.assertEqual(self.ude.last_output, before)
        with self.assertRaises(ValueError):
            self.update(active=1)
        with self.assertRaises(ValueError):
            self.ude.update(None, None, dt_s=0.01, external_control_active=True)
        self.assertEqual(self.ude.integral, before.integral)

    def test_zero_force_and_overflow_are_transactional(self):
        before = self.update(PIDReference((0.25, 0, 0)))
        for acc in ((0, 0, -9.8), (1e308, 0, 0)):
            with self.assertRaises(ValueError):
                self.update(PIDReference((0, 0, 0), acceleration_enu=acc))
            self.assertEqual(self.ude.last_output, before)
            self.assertEqual(self.ude.integral, before.integral)

    def test_force_limits_and_negative_vertical(self):
        for az, expected_z in ((-20, 9.8), (-8, 9.8), (30, 39.2)):
            self.ude.reset("case")
            out = self.update(PIDReference((0, 0, 0), acceleration_enu=(20, -20, az)))
            self.assertAlmostEqual(out.force_enu_n[2], expected_z)
            self.assertLessEqual(abs(out.force_enu_n[0]/expected_z), math.tan(math.radians(20))+1e-15)
            self.assertEqual(out.force_enu_n[0] < 0, az == -20)

    def test_invalid_config_and_inputs(self):
        for values in ({"mass_kg": 0}, {"mass_kg": math.inf}, {"mass_kg": 2, "t_ude_s": 0},
                       {"mass_kg": 2, "tilt_limit_deg": 90}, {"mass_kg": 2, "kp": (-1, 0, 0)},
                       {"mass_kg": 2, "disturbance_limit": (math.nan, 0, 0)}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                UDEConfig(**values)
        for ctor in (lambda: PIDReference((math.nan, 0, 0)),
                     lambda: PIDState((0, 0, 0), (math.inf, 0, 0), (1, 0, 0, 0)),
                     lambda: PIDState((0, 0, 0), (0, 0, 0), (2, 0, 0, 0))):
            with self.assertRaises(ValueError):
                ctor()


if __name__ == "__main__":
    unittest.main()
