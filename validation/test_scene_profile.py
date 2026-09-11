"""Pure offline contract tests for the frozen #39 scene profile.

These tests deliberately do not import ROS, the planner, a map server, SITL or
the trajectory runtime.  They verify the shared geometry and the input boundary
that a later runtime integration must consume.
"""

import math
import unittest

from Simulator.wksim_planning.scene_profile import (
    AABB,
    EGO_SINGLE_BOX_V1,
    FRAME,
    NO_ROUTE_PROFILE,
    PROFILE_ID,
    REQUIRED_CLEARANCE,
    SCENE_PROFILE_HASH,
    SceneProfile,
    SceneProfileError,
    ProfileMismatchError,
    canonical_profile_hash,
    minimum_clearance,
    no_route_profile,
    path_clearance,
    path_meets_clearance,
    segment_clearance,
    segment_surface_distance,
    validate_clearance,
    validate_profile,
    validate_replan_input,
)


class SceneProfileShapeTests(unittest.TestCase):
    def test_frozen_profile_identity_and_units(self):
        profile = EGO_SINGLE_BOX_V1
        self.assertEqual(profile.profile_id, PROFILE_ID)
        self.assertEqual(profile.frame, "map")
        self.assertEqual(profile.coordinate_system, "ENU")
        self.assertEqual(profile.units, {"length": "m", "time": "s", "angle": "rad"})
        self.assertEqual(profile.origin, (-10.0, -6.0, 0.0))
        self.assertEqual(profile.size, (20.0, 12.0, 6.0))
        self.assertEqual(profile.voxel_resolution, 0.1)
        self.assertEqual(profile.obstacle.minimum, (-0.5, -1.0, 0.0))
        self.assertEqual(profile.obstacle.maximum, (0.5, 1.0, 5.5))
        self.assertEqual(profile.vehicle_radius, 0.35)
        self.assertEqual(profile.required_clearance, REQUIRED_CLEARANCE)
        # Fixed cross-file identity digests from docs/plan/39-planner-scene-contract.md.
        self.assertEqual(profile.profile_hash,
                         "49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7")
        self.assertEqual(profile.collision_hash,
                         "08b88651775ae2181e5082f124d16c6a434597703fdf2ff08bfc0bd59205c07c")
        self.assertEqual(profile.voxel_hash,
                         "3602530733cf10fd0960212dc413b157e56e662d330b4b314a71f4c21abae638")
        self.assertEqual(profile.profile_hash, SCENE_PROFILE_HASH)
        self.assertEqual(canonical_profile_hash(profile), SCENE_PROFILE_HASH)

    def test_canonical_hash_is_order_independent_and_detects_mutation(self):
        value = EGO_SINGLE_BOX_V1.to_dict()
        reordered = {key: value[key] for key in reversed(tuple(value))}
        self.assertEqual(validate_profile(reordered, require_hash=True).profile_hash,
                         SCENE_PROFILE_HASH)
        value["size"][0] = 19.9
        with self.assertRaises(ProfileMismatchError):
            validate_profile(value, require_hash=True)

    def test_bad_units_frame_nonfinite_and_unknown_fields_fail_closed(self):
        value = EGO_SINGLE_BOX_V1.to_dict()
        value["units"]["length"] = "cm"
        with self.assertRaises(SceneProfileError):
            validate_profile(value, require_hash=True)

        value = EGO_SINGLE_BOX_V1.to_dict()
        value["frame"] = "NED"
        with self.assertRaises(SceneProfileError):
            validate_profile(value, require_hash=True)

        value = EGO_SINGLE_BOX_V1.to_dict()
        value["origin"][1] = float("nan")
        with self.assertRaises(SceneProfileError):
            validate_profile(value, require_hash=True)

        value = EGO_SINGLE_BOX_V1.to_dict()
        value["unexpected"] = 1
        with self.assertRaises(SceneProfileError):
            validate_profile(value, require_hash=True)

        with self.assertRaises(SceneProfileError):
            EGO_SINGLE_BOX_V1.with_obstacle(
                AABB((-0.45, -1.0, 0.0), (0.55, 1.0, 5.5)),
                profile_id="ego-single-box-v1-invalid-grid",
            )

    def test_hash_fields_are_checked_independently(self):
        value = EGO_SINGLE_BOX_V1.to_dict()
        value["profile_hash"] = "0" * 64
        with self.assertRaises(ProfileMismatchError):
            validate_profile(value, require_hash=True)
        value = EGO_SINGLE_BOX_V1.to_dict()
        value["collision_hash"] = "0" * 64
        with self.assertRaises(ProfileMismatchError):
            validate_profile(value, require_hash=True)
        value = EGO_SINGLE_BOX_V1.to_dict()
        value["point_cloud_hash"] = "0" * 64
        with self.assertRaises(ProfileMismatchError):
            validate_profile(value, require_hash=True)

    def test_voxel_centres_are_complete_and_ordered(self):
        profile = EGO_SINGLE_BOX_V1
        self.assertEqual(profile.grid_shape(), (200, 120, 60))
        self.assertEqual(profile.obstacle_index_bounds(), ((95, 104), (50, 69), (0, 54)))
        indices = profile.voxel_indices()
        centres = profile.voxel_centers()
        self.assertEqual(len(indices), 10 * 20 * 55)
        self.assertEqual(len(centres), len(indices))
        self.assertEqual(indices[0], (95, 50, 0))
        self.assertEqual(indices[1], (95, 50, 1))
        self.assertEqual(indices[55], (95, 51, 0))
        self.assertEqual(indices[-1], (104, 69, 54))
        self.assertEqual(centres[0], (-0.45, -0.95, 0.05))
        self.assertEqual(centres[-1], (0.45, 0.95, 5.45))
        self.assertTrue(all(profile.obstacle.contains(point, inclusive=False)
                            for point in centres))
        self.assertEqual(profile.voxel_indices(), profile.voxel_indices())
        self.assertEqual(profile.voxel_hash, profile.voxel_hash)

    def test_no_route_is_an_explicit_derived_geometry(self):
        profile = no_route_profile()
        self.assertEqual(profile, NO_ROUTE_PROFILE)
        self.assertEqual(profile.profile_id, "ego-single-box-v1-no-route")
        self.assertEqual(profile.obstacle.minimum, (-0.5, -6.0, 0.0))
        self.assertEqual(profile.obstacle.maximum, (0.5, 6.0, 6.0))
        self.assertEqual(len(profile.voxel_centers()), 10 * 120 * 60)
        self.assertNotEqual(profile.profile_hash, SCENE_PROFILE_HASH)


class ClearanceTests(unittest.TestCase):
    def test_segment_distance_detects_intersection_and_clearance(self):
        self.assertEqual(segment_surface_distance((-4, 0, 3), (4, 0, 3)), 0.0)
        self.assertAlmostEqual(segment_clearance((-4, 0, 3), (4, 0, 3)), -0.35)
        self.assertAlmostEqual(segment_surface_distance((1.15, 0, 3), (1.15, 1, 3)), 0.65)
        self.assertAlmostEqual(segment_clearance((1.15, 0, 3), (1.15, 1, 3)), 0.30)
        self.assertAlmostEqual(segment_clearance((1.15, 0, 3), (1.15, 1, 3)), REQUIRED_CLEARANCE)

    def test_boundary_touch_is_not_a_pass(self):
        # At x=0.5+radius+clearance the surface and swept-clearance boundaries
        # are exactly at the acceptance threshold; moving one representable
        # step inward fails the gate.
        boundary = 0.5 + 0.35 + 0.30
        self.assertAlmostEqual(path_clearance([(boundary, -2, 3), (boundary, 2, 3)]),
                                 REQUIRED_CLEARANCE)
        self.assertTrue(path_meets_clearance([(boundary + 1e-9, -2, 3),
                                               (boundary + 1e-9, 2, 3)]))
        self.assertFalse(path_meets_clearance([(boundary - 1e-6, -2, 3),
                                                (boundary - 1e-6, 2, 3)]))
        self.assertFalse(path_meets_clearance([(0.5, -2, 3), (0.5, 2, 3)]))

    def test_path_minimum_is_segment_minimum(self):
        safe = [(1.2, -2, 3), (1.2, 0, 3), (1.2, 2, 3)]
        self.assertAlmostEqual(path_clearance(safe), 0.35)
        self.assertAlmostEqual(minimum_clearance(safe[0], safe[1]), 0.35)
        self.assertTrue(validate_clearance(safe))
        self.assertLess(path_clearance([(-4, 0, 3), (4, 0, 3)]), 0.0)

    def test_units_and_nonfinite_clearance_inputs_fail_closed(self):
        for kwargs in ({"frame": "world"}, {"frame": "map", "units": "cm"},
                       {"frame": "map", "units": {"length": "cm"}}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SceneProfileError):
                    segment_clearance((1, 0, 3), (1, 1, 3), **kwargs)
        with self.assertRaises(SceneProfileError):
            segment_clearance((float("nan"), 0, 3), (1, 1, 3))
        with self.assertRaises(SceneProfileError):
            path_clearance([(1, 0, 3)])


class ReplanInputTests(unittest.TestCase):
    def _request(self, **changes):
        request = {
            "profile_id": PROFILE_ID,
            "profile_hash": SCENE_PROFILE_HASH,
            "frame": FRAME,
            "units": "m",
            "start": [-4, 0, 3],
            "goal": [4, 0, 3],
            "generation": 2,
        }
        request.update(changes)
        return request

    def test_start_goal_and_replan_generation_are_normalized(self):
        parsed = validate_replan_input(self._request())
        self.assertEqual(parsed.start, (-4.0, 0.0, 3.0))
        self.assertEqual(parsed.goal, (4.0, 0.0, 3.0))
        self.assertEqual(parsed.generation, 2)
        self.assertEqual(parsed.as_dict()["profile_hash"], SCENE_PROFILE_HASH)
        direct = validate_replan_input([-4, 0, 3], [4, 2, 3],
                                       profile_hash=SCENE_PROFILE_HASH)
        self.assertEqual(direct.goal, (4.0, 2.0, 3.0))

    def test_replan_profile_hash_frame_units_and_generation_fail_closed(self):
        for changes in ({"profile_hash": "0" * 64}, {"profile_id": "other"},
                        {"frame": "world"}, {"units": "cm"}, {"generation": -1},
                        {"start": [float("inf"), 0, 3]},
                        {"goal": [4, float("nan"), 3]},
                        {"start": [0, 0, 3]}, {"goal": [0, 0, 3]}):
            with self.subTest(changes=changes):
                with self.assertRaises((SceneProfileError, ProfileMismatchError)):
                    validate_replan_input(self._request(**changes))
        with self.assertRaises(ProfileMismatchError):
            validate_replan_input([-4, 0, 3], [4, 0, 3], profile_hash=None)


if __name__ == "__main__":
    unittest.main()
