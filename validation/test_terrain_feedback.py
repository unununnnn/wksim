import math
import unittest

from Simulator.wksim_runtime.terrain_feedback import (
    support_height_to_terrain15d,
    vehicle60_to_enu_query_point,
)


class TerrainFeedbackTests(unittest.TestCase):
    def test_vehicle60_ned_position_maps_to_world_enu(self):
        state = [float(index) for index in range(60)]
        state[6:9] = [12.5, 34.0, -6.25]
        original = list(state)

        self.assertEqual(vehicle60_to_enu_query_point(state), [34.0, 12.5, 6.25])
        self.assertEqual(vehicle60_to_enu_query_point(tuple(state)), [34.0, 12.5, 6.25])
        self.assertEqual(state, original)

    def test_vehicle60_requires_every_value_and_never_fabricates_initial_state(self):
        for value in (None, [], [0.0] * 59, [0.0] * 61, "0" * 60):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vehicle60_to_enu_query_point(value)
        for bad in (True, math.nan, math.inf, -math.inf):
            state = [0.0] * 60
            state[30] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                vehicle60_to_enu_query_point(state)

    def test_support_height_maps_only_the_ned_down_input(self):
        terrain = support_height_to_terrain15d(5)
        self.assertEqual(terrain, [-5.0] + [0.0] * 14)
        self.assertTrue(all(type(value) is float for value in terrain))
        self.assertEqual(support_height_to_terrain15d(-2.5), [2.5] + [0.0] * 14)

    def test_signed_zero_is_accepted(self):
        state = [-0.0] * 60
        self.assertEqual(vehicle60_to_enu_query_point(state), [0.0, 0.0, 0.0])
        for height in (-0.0, 0.0):
            terrain = support_height_to_terrain15d(height)
            self.assertEqual(terrain, [0.0] * 15)
            self.assertEqual(math.copysign(1.0, terrain[0]), 1.0)

    def test_support_height_rejects_non_numeric_nonfinite_and_bool(self):
        for value in (None, "0", True, False, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                support_height_to_terrain15d(value)

    def test_terrain_feedback_independent_observers_and_mapping(self):
        from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback
        epoch = "0123456789abcdef0123456789abcdef"
        tf = TerrainFeedback(epoch)

        # Ensure observers are independent instances for arducopter and px4
        self.assertIn("arducopter", tf.observers)
        self.assertIn("px4", tf.observers)
        self.assertIsNot(tf.observers["arducopter"], tf.observers["px4"])
        self.assertEqual(tf.observers["arducopter"].epoch, epoch)
        self.assertEqual(tf.observers["px4"].epoch, epoch)

        # Prior states:
        # arducopter: outside box -> support height 0.0 -> terrain15d[0] = 0.0
        state_ap = [0.0] * 120
        state_ap[6:9] = [10.0, 20.0, -5.0]
        # px4: above box center [2.0, 0.0] -> support height 1.0 -> terrain15d[0] = -1.0
        state_px4 = [0.0] * 120
        state_px4[6:9] = [0.0, 2.0, -2.0]

        # Step 1 for both stacks at same tick
        terrain_ap = tf.query_terrain("arducopter", 1, state_ap)
        terrain_px4 = tf.query_terrain("px4", 1, state_px4)

        self.assertEqual(terrain_ap, [0.0] * 15)
        self.assertEqual(terrain_px4, [-1.0] + [0.0] * 14)

        # Watermarks advance independently
        self.assertEqual(tf.observers["arducopter"].last_step, 1)
        self.assertEqual(tf.observers["px4"].last_step, 1)

        # Step 2 with new prior state
        state_ap[6:9] = [0.0, 2.0, -3.0]
        terrain_ap_2 = tf.query_terrain("arducopter", 2, state_ap)
        self.assertEqual(terrain_ap_2, [-1.0] + [0.0] * 14)
        self.assertEqual(tf.observers["arducopter"].last_step, 2)
        self.assertEqual(tf.observers["px4"].last_step, 1)

    def test_terrain_feedback_validation_and_freeze(self):
        from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback
        epoch = "0123456789abcdef0123456789abcdef"
        tf = TerrainFeedback(epoch)

        valid_state = [0.0] * 120

        # Unknown stack
        with self.assertRaises(ValueError):
            tf.query_terrain("unknown_stack", 1, valid_state)

        # Invalid state length
        with self.assertRaises(ValueError):
            tf.query_terrain("arducopter", 1, [0.0] * 60)
        with self.assertRaises(ValueError):
            tf.query_terrain("arducopter", 1, [0.0] * 121)

        # Non-finite values anywhere in 120 state
        bad_state = [0.0] * 120
        bad_state[100] = math.nan
        with self.assertRaises(ValueError):
            tf.query_terrain("arducopter", 1, bad_state)

        bad_state[100] = True
        with self.assertRaises(ValueError):
            tf.query_terrain("arducopter", 1, bad_state)

        # Valid step 1
        tf.query_terrain("arducopter", 1, valid_state)

        # Stale feedback (same tick or backward tick) freezes observer
        with self.assertRaises(RuntimeError) as ctx:
            tf.query_terrain("arducopter", 1, valid_state)
        self.assertIn("froze", str(ctx.exception))
        self.assertTrue(tf.observers["arducopter"].frozen)

        # Once frozen, cannot query again
        with self.assertRaises(RuntimeError) as ctx2:
            tf.query_terrain("arducopter", 2, valid_state)
        self.assertIn("is frozen", str(ctx2.exception))

        # Other stack observer is unaffected
        self.assertFalse(tf.observers["px4"].frozen)
        terrain_px4 = tf.query_terrain("px4", 1, valid_state)
        self.assertEqual(len(terrain_px4), 15)

    def test_terrain_feedback_manifest(self):
        from Simulator.wksim_runtime.terrain_feedback import TerrainFeedback
        epoch = "0123456789abcdef0123456789abcdef"
        tf = TerrainFeedback(epoch)
        manifest = tf.manifest()

        self.assertEqual(manifest["schema"], "wksim.terrain-feedback-manifest.v1")
        self.assertEqual(manifest["scene_id"], "static-plane-box-v1")
        self.assertEqual(manifest["scene_hash"], "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514")
        self.assertEqual(manifest["epoch"], epoch)
        self.assertEqual(
            manifest["mapping"],
            "state[k-1].Vehicle60 -> world ENU support height -> terrain[k].Terrain15D",
        )
        self.assertEqual(manifest["worker_trace_field"], "terrain")
        self.assertEqual(manifest["stacks"], {
            "arducopter": {"body_id": "uav1"},
            "px4": {"body_id": "uav2"},
        })


if __name__ == "__main__":
    unittest.main()
