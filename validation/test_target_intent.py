"""Pure contract tests for ArUco target to public body-velocity intent."""
import copy
import unittest

from Simulator.wksim_perception.target_intent import TargetIntent, TargetIntentConfig


IDENTITY = dict(run_id="run", epoch="epoch", stream_id="stream")


def target(**overrides):
    value = {
        "schema": "wksim.aruco-target.v1",
        **IDENTITY,
        "step": "100",
        "valid_until_step": 400,
        "position_body_flu_m": [1.0, 0.0, 0.0],
        "velocity_world_ue_mps": [999.0, 999.0, 999.0],
    }
    value.update(overrides)
    return value


def intent(**config):
    return TargetIntent(TargetIntentConfig(
        config.get("desired_body_flu_m", (0.0, 0.0, 0.0)),
        config.get("gain_per_s", 1.0), config.get("max_speed_mps", 2.0)), **IDENTITY)


class TargetIntentTests(unittest.TestCase):
    def test_axis_limit_and_public_body_velocity_shape(self):
        result = intent().update(target(position_body_flu_m=[-5.0, 0.0, 0.0]), authority_step=100)
        self.assertEqual(result["move_mode"], "XYZ_VEL_BODY")
        self.assertEqual(result["velocity_ref"], [2.0, 0.0, 0.0])
        self.assertTrue(result["yaw_rate_mode"])
        self.assertEqual(result["yaw_rate_ref"], 0.0)
        self.assertNotIn("velocity_world_ue_mps", result)

    def test_diagonal_limit_is_vector_norm_and_diagnostic_speed_is_ignored(self):
        result = intent(max_speed_mps=5.0).update(
            target(position_body_flu_m=[-3.0, -4.0, 0.0], velocity_world_ue_mps=[.01, .02, .03]),
            authority_step=100)
        self.assertAlmostEqual(result["velocity_ref"][0], 3.0)
        self.assertAlmostEqual(result["velocity_ref"][1], 4.0)
        self.assertAlmostEqual(sum(v * v for v in result["velocity_ref"]) ** .5, 5.0)

    def test_future_expired_foreign_and_missing_targets_hold_and_clear(self):
        c = intent()
        self.assertEqual(c.update(target(), authority_step=100)["move_mode"], "XYZ_VEL_BODY")
        cases = (
            (dict(step="101"), 100, "future"),
            (dict(valid_until_step=100), 101, "expired"),
            (dict(run_id="foreign"), 100, "binding"),
            (None, 100, "missing"),
        )
        for mutation, step, label in cases:
            with self.subTest(label=label):
                value = None if mutation is None else {**target(), **mutation}
                result = c.update(value, authority_step=step)
                self.assertEqual(result["move_mode"], "HOLD")
                self.assertIn(label, result["reason"])
                self.assertEqual(result["velocity_ref"], [0.0, 0.0, 0.0])

    def test_reacquisition_after_loss_does_not_reuse_old_step(self):
        c = intent()
        self.assertEqual(c.update(target(), authority_step=100)["step"], 100)
        self.assertEqual(c.update(None, authority_step=150)["reason"], "target_missing")
        reacquired = c.update(target(step="150", position_body_flu_m=[0.5, 0.0, 0.0]), authority_step=150)
        self.assertEqual(reacquired["move_mode"], "XYZ_VEL_BODY")
        self.assertEqual(reacquired["step"], 150)

    def test_config_and_binding_are_explicit(self):
        with self.assertRaises(TypeError):
            TargetIntent(None, **IDENTITY)
        for values in (
                dict(desired_body_flu_m=(0.0, 0.0), gain_per_s=1, max_speed_mps=1),
                dict(desired_body_flu_m=(0.0, 0.0, 0.0), gain_per_s=0, max_speed_mps=1),
                dict(desired_body_flu_m=(0.0, 0.0, 0.0), gain_per_s=1, max_speed_mps=float("nan")),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                TargetIntentConfig(**values)

    def test_duplicate_or_regressing_step_is_rejected(self):
        for step in ("100", "99"):
            with self.subTest(step=step):
                c = intent()
                c.update(target(), authority_step=100)
                result = c.update(target(step=step), authority_step=100)
                self.assertEqual(result["move_mode"], "HOLD")
                self.assertIn("duplicate", result["reason"])

    def test_rebind_clears_the_previous_authority(self):
        c = intent()
        c.update(target(), authority_step=100)
        c.bind(run_id="new-run", epoch="new-epoch", stream_id="new-stream")
        foreign = c.update(target(), authority_step=100)
        self.assertEqual(foreign["move_mode"], "HOLD")
        fresh = copy.deepcopy(target(run_id="new-run", epoch="new-epoch", stream_id="new-stream"))
        self.assertEqual(c.update(fresh, authority_step=100)["move_mode"], "XYZ_VEL_BODY")


if __name__ == "__main__":
    unittest.main()
