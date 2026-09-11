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
        self.assertEqual(support_height_to_terrain15d(-0.0), [0.0] * 15)

    def test_support_height_rejects_non_numeric_nonfinite_and_bool(self):
        for value in (None, "0", True, False, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                support_height_to_terrain15d(value)


if __name__ == "__main__":
    unittest.main()
