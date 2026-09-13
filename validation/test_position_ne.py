import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Simulator"))
from wksim_control.position_ne import NEConfig, NEMemory, PositionNE
from wksim_control.position_pid import PIDReference, PIDState


class NETest(unittest.TestCase):
    def setUp(self):
        self.ne = PositionNE(NEConfig(2.0))
        self.state = PIDState((0, 0, 0), (0, 0, 0), (1, 0, 0, 0))
        self.ref = PIDReference((0, 0, 0))

    def step(self, **kw):
        return self.ne.update(kw.pop("state", self.state), kw.pop("reference", self.ref),
                              dt_s=kw.pop("dt_s", .005), external_control_active=kw.pop("active", True), **kw)

    def test_hover(self):
        out = self.step()
        self.assertEqual(out.controller, "ne")
        self.assertEqual(out.force_enu_n, (0, 0, 19.6))
        self.assertEqual(out.projected_thrust_n, 19.6)
        self.assertEqual(out.memory, NEMemory())

    def test_old_integral_and_no_pid_error_clamp(self):
        ref = PIDReference((4, 0, 0))
        first = self.step(reference=ref)
        self.assertEqual(first.nominal_acceleration[0], 2)
        self.assertEqual(first.disturbance_estimate[0], 0)
        self.assertEqual(first.memory.integral[0], .01)
        second = self.step(reference=ref)
        self.assertEqual(second.disturbance_estimate[0], -.01)

    def test_llf_is_updated_but_discarded(self):
        out = self.step(state=PIDState((1, 0, 0), (.5, 0, 0), (1, 0, 0, 0)))
        self.assertNotEqual(out.memory.llf[0], 0)
        self.assertEqual(out.disturbance_estimate[0], .5)
        self.assertNotEqual(out.noise_estimator[0], 0)

    def test_integral_threshold_and_disturbance_saturation(self):
        self.step(reference=PIDReference((99, 0, 0)), dt_s=1)
        out = self.step(reference=PIDReference((100, 0, 0)))
        self.assertEqual(out.memory.integral[0], 0)
        self.assertEqual(out.disturbance_estimate[0], -1)
        out = self.step(reference=PIDReference((-100, 0, 0)))
        self.assertEqual(out.memory.integral[0], 0)

    def test_cold_reset_all_history_and_position(self):
        state = PIDState((1, 2, 3), (.5, -.25, .125), (1, 0, 0, 0))
        self.step(state=state)
        self.assertNotEqual(self.ne.memory, NEMemory())
        self.ne.reset("epoch", initial_position_enu=(1, 2, 3))
        self.assertEqual(self.ne.memory, NEMemory())
        fresh = PositionNE(NEConfig(2))
        fresh.reset("epoch", initial_position_enu=(1, 2, 3))
        self.assertEqual(self.step(state=state), fresh.update(state, self.ref, dt_s=.005, external_control_active=True))
        self.ne.reset("release")
        self.assertEqual(self.ne.initial_position_enu, (0, 0, 0))

    def test_invalid_cycle_is_atomic(self):
        self.step(reference=PIDReference((1, 1, 1)))
        before = self.ne.memory
        for dt in (0, -1, math.nan, math.inf, True, "0.1"):
            with self.subTest(dt=dt), self.assertRaises(ValueError):
                self.step(dt_s=dt)
            self.assertEqual(self.ne.memory, before)
        for active in (False, 1, None):
            with self.assertRaises(ValueError):
                self.step(active=active)
            self.assertEqual(self.ne.memory, before)

    def test_zero_vertical_force_and_overflow_atomic(self):
        for ref in (PIDReference((0, 0, 0), acceleration_enu=(0, 0, -9.8)),
                    PIDReference((0, 0, 0), acceleration_enu=(1e307, 0, -9.8+2e-15)),
                    PIDReference((1e308, 0, 0), velocity_enu=(1e308, 0, 0))):
            with self.assertRaises(ValueError):
                self.step(reference=ref)
            self.assertEqual(self.ne.memory, NEMemory())

    def test_reset_validation_atomic(self):
        self.step(reference=PIDReference((1, 1, 1)))
        before = self.ne.memory
        for reason, initial in (("", (0, 0, 0)), (None, (0, 0, 0)), ("epoch", (math.inf, 0, 0))):
            with self.assertRaises(ValueError):
                self.ne.reset(reason, initial_position_enu=initial)
            self.assertEqual(self.ne.memory, before)

    def test_config_rejects_nonfinite_and_invalid(self):
        for kw in ({"mass_kg": 0}, {"t_ne_s": 0}, {"t_ude_s": -1}, {"kp": (0, math.nan, 0)},
                   {"kd": (-1, 1, 1)}, {"disturbance_limit": (1, -1, 1)}, {"tilt_limit_deg": 90}):
            with self.assertRaises(ValueError):
                NEConfig(**({"mass_kg": 2} | kw))

    def test_input_finiteness(self):
        with self.assertRaises(ValueError):
            PIDState((math.nan, 0, 0), (0, 0, 0), (1, 0, 0, 0))
        with self.assertRaises(ValueError):
            PIDReference((0, 0, 0), acceleration_enu=(math.inf, 0, 0))
        with self.assertRaises(ValueError):
            PIDState((0, 0, 0), (0, 0, 0), (2, 0, 0, 0))

    def test_negative_force_original_scaling(self):
        out = self.step(reference=PIDReference((0, 0, 0), acceleration_enu=(1, 0, -20)))
        self.assertLess(out.force_enu_n[0], 0)
        self.assertAlmostEqual(out.force_enu_n[2], 9.8)

    def test_instances_do_not_share_history(self):
        self.step(reference=PIDReference((1, 0, 0)))
        self.assertEqual(PositionNE(NEConfig(2)).memory, NEMemory())


if __name__ == "__main__":
    unittest.main()
