"""Static contract checks for GridMap runtime parameter updates.

These checks deliberately avoid ROS/catkin.  They protect the source-level
ownership and fail-closed boundaries that cannot be exercised without a ROS
runtime in this validation environment.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / "Modules/ego_planner_swarm/plan_env/include/plan_env/grid_map.h").read_text(
    encoding="utf-8"
)
SOURCE = (ROOT / "Modules/ego_planner_swarm/plan_env/src/grid_map.cpp").read_text(
    encoding="utf-8"
)


def callback_source():
    start = SOURCE.index("void GridMap::gridparam_Callback")
    end = SOURCE.index("// 膨胀地图全部重置", start)
    return SOURCE[start:end]


class TestGridMapParameterSafety(unittest.TestCase):
    def test_init_locals_are_never_stored_as_member_pointers(self):
        for pointer_name in ("grid_params_get_i", "grid_params_get_d", "grid_params_get_b"):
            self.assertNotIn(pointer_name, HEADER)
            self.assertNotIn(pointer_name, SOURCE)
        for legacy_metadata in ("grid_params_compare", "grid_params_compare_all", "pre_grid_params_compare"):
            self.assertNotIn(legacy_metadata, HEADER)
            self.assertNotIn(legacy_metadata, SOURCE)
        for local_name in ("uav_id", "x_size", "y_size", "z_size", "x_origin", "y_origin"):
            self.assertNotIn(f"&{local_name}", SOURCE)
        self.assertNotIn("&mp_.map_size_", SOURCE)
        self.assertNotIn("&mp_.map_origin_", SOURCE)

    def test_callback_rejects_ambiguous_messages_before_indexing(self):
        callback = callback_source()
        self.assertIn("if (!msg)", callback)
        self.assertIn("msg->param_name.size() != 1", callback)
        self.assertIn("msg->param_value.size() != 1", callback)
        self.assertIn("msg->param_name.front()", callback)
        self.assertIn("msg->param_value.front()", callback)
        self.assertNotIn("msg->param_name[0]", callback)
        self.assertNotIn("msg->param_value[0]", callback)
        self.assertNotIn("pre_grid_params_compare", callback)
        self.assertNotIn("grid_params_compare_all", callback)

    def test_numeric_parsing_is_full_consumption_finite_and_exception_safe(self):
        self.assertIn("std::stol(text, &consumed, 10)", SOURCE)
        self.assertIn("std::stod(text, &consumed)", SOURCE)
        self.assertGreaterEqual(SOURCE.count("consumed != text.size()"), 2)
        self.assertIn("std::isfinite(parsed)", SOURCE)
        self.assertGreaterEqual(SOURCE.count("catch (const std::exception&)") , 2)
        self.assertIn('text == "0"', SOURCE)
        self.assertIn('text == "1"', SOURCE)

    def test_runtime_numeric_updates_have_domain_guards(self):
        callback = callback_source()
        self.assertIn("parsed < 0.0", callback)
        self.assertIn("parsed > mp_.map_size_(axis)", callback)
        self.assertIn("gridMapLocalMapMarginLimit(mp_)", callback)
        self.assertIn("gridMapInflationStepLimit(mp_)", callback)
        self.assertIn("kGridMapMaxInflationSteps", SOURCE)
        self.assertIn("gridMapDistanceLimit(mp_)", callback)
        self.assertIn("parsed < mp_.depth_filter_mindist_", callback)
        self.assertIn("parsed > mp_.depth_filter_maxdist_", callback)
        self.assertIn("parsed > mp_.max_ray_length_", callback)
        self.assertIn("parsed < mp_.min_ray_length_", callback)
        self.assertIn("timeout must be non-negative", callback)
        self.assertIn("frame_id cannot be empty", callback)

    def test_initialization_only_parameters_are_explicitly_ignored(self):
        callback = callback_source()
        for name in (
            "uav_id", "resolution", "map_size_x", "map_size_y", "map_size_z",
            "map_origin_x", "map_origin_y", "depth_filter_margin", "skip_pixel",
            "pose_type", "fx", "fy", "cx", "cy", "k_depth_scaling_factor",
            "p_hit", "p_miss", "p_min", "p_max", "p_occ",
            "ground_height", "virtual_ceil_height", "virtual_ceil_yp", "virtual_ceil_yn",
        ):
            self.assertIn(f'"{name}"', SOURCE)
        self.assertIn("initialization-only and was ignored", callback)
        self.assertIn("kGridMapInitializationOnly.count(short_name)", callback)

    def test_only_runtime_safe_fields_are_assignable_in_callback(self):
        callback = callback_source()
        for field in (
            "mp_.local_update_range_", "mp_.local_map_margin_", "mp_.obstacles_inflation_",
            "mp_.depth_filter_tolerance_", "mp_.depth_filter_maxdist_", "mp_.depth_filter_mindist_",
            "mp_.min_ray_length_", "mp_.max_ray_length_", "mp_.visualization_truncate_height_",
            "mp_.use_depth_filter_", "mp_.frame_id_", "mp_.odom_depth_timeout_",
        ):
            self.assertIn(field, callback)
        for initialization_only_field in (
            "mp_.fx_", "mp_.fy_", "mp_.cx_", "mp_.cy_", "mp_.k_depth_scaling_factor_",
        ):
            self.assertNotIn(initialization_only_field, callback)
        self.assertNotIn("mp_.resolution_ =", callback)
        self.assertNotIn("mp_.map_size_ =", callback)
        self.assertNotIn("mp_.map_origin_ =", callback)
        self.assertNotIn("mp_.map_voxel_num_", callback)
        self.assertNotIn("mp_.map_min_boundary_", callback)
        self.assertNotIn("mp_.map_max_boundary_", callback)
        self.assertNotIn("md_.occupancy_buffer_", callback)
        self.assertIn("unsupported parameter", callback)


if __name__ == "__main__":
    unittest.main()
