"""Static contract tests for the profile-closed EGO launch slice.

The tests parse XML and cross-check the committed offline scene profile.  They
never import ROS, start a planner, build catkin, or claim that the configured
point-cloud producer contains the profile geometry.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADVANCED_PATH = ROOT / (
    "Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/"
    "advanced_param_wksim_single_box.xml"
)
SITL_PATH = ROOT / (
    "Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/"
    "sitl_ego_planner_wksim_single_box.launch"
)
CONTRACT_PATH = ROOT / "docs/plan/39-planner-run-contract.md"
PROFILE_PATH = ROOT / "Simulator/wksim_planning/scene_profile.py"
FSM_SOURCE_PATH = ROOT / "Modules/ego_planner_swarm/plan_manage/src/ego_replan_fsm.cpp"
GRID_SOURCE_PATH = ROOT / "Modules/ego_planner_swarm/plan_env/src/grid_map.cpp"
MANAGER_SOURCE_PATH = ROOT / "Modules/ego_planner_swarm/plan_manage/src/planner_manager.cpp"
OPTIMIZER_SOURCE_PATH = ROOT / "Modules/ego_planner_swarm/bspline_opt/src/bspline_optimizer.cpp"
PLANNER_NODE_SOURCE_PATH = ROOT / "Modules/ego_planner_swarm/plan_manage/src/ego_planner_node.cpp"


def _load_profile_module():
    spec = importlib.util.spec_from_file_location("wksim_scene_profile_for_39", PROFILE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROFILE = _load_profile_module()


def _parse(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def _params(root: ET.Element) -> dict[str, ET.Element]:
    params = list(root.iter("param"))
    names = [param.attrib["name"] for param in params]
    if len(names) != len(set(names)):
        raise AssertionError(f"duplicate ROS parameter name in {names}")
    return {param.attrib["name"]: param for param in params}


def _value(params: dict[str, ET.Element], name: str) -> str:
    try:
        return params[name].attrib["value"]
    except KeyError as error:
        raise AssertionError(f"missing ROS parameter {name}") from error


def _typed_params(root: ET.Element) -> dict[str, tuple[str, str]]:
    params = _params(root)
    return {
        name: (element.attrib.get("value", ""), element.attrib.get("type", ""))
        for name, element in params.items()
    }


def _remaps(root: ET.Element) -> dict[str, str]:
    remaps = list(root.iter("remap"))
    pairs = [(remap.attrib["from"], remap.attrib["to"]) for remap in remaps]
    if len(pairs) != len(set(pairs)):
        raise AssertionError(f"duplicate ROS remap in {pairs}")
    names = [source for source, _ in pairs]
    if len(names) != len(set(names)):
        raise AssertionError(f"duplicate ROS remap source in {names}")
    return dict(pairs)


class PlannerLaunchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advanced = _parse(ADVANCED_PATH)
        cls.sitl = _parse(SITL_PATH)
        cls.params = _params(cls.advanced)
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_xml_is_well_formed_and_has_no_launch_arg_override_surface(self):
        self.assertEqual(self.advanced.tag, "launch")
        self.assertEqual(self.sitl.tag, "launch")
        self.assertEqual(list(self.advanced.iter("arg")), [])
        self.assertEqual(list(self.sitl.iter("arg")), [])
        for root in (self.advanced, self.sitl):
            for element in root.iter():
                for value in element.attrib.values():
                    self.assertNotIn("$(arg ", value)

    def test_sitl_includes_closed_profile_and_keeps_traj_server(self):
        includes = list(self.sitl.iter("include"))
        self.assertEqual(len(includes), 1)
        self.assertEqual(
            includes[0].attrib["file"],
            "$(find ego_planner)/launch_for_prometheus/"
            "advanced_param_wksim_single_box.xml",
        )
        nodes = list(self.sitl.iter("node"))
        self.assertEqual(len(nodes), 1)
        self.assertEqual(
            nodes[0].attrib,
            {
                "pkg": "ego_planner",
                "name": "uav1_traj_server_for_prometheus",
                "type": "traj_server_for_prometheus",
                "output": "screen",
            },
        )
        self.assertEqual(
            _typed_params(nodes[0]),
            {
                "uav_id": ("1", "int"),
                "control_flag": ("0", "int"),
                "traj_server/time_forward": ("1.0", "double"),
                "traj_server/last_yaw": ("0.0", "double"),
            },
        )

    def test_all_active_remaps_are_closed_and_unique(self):
        self.assertEqual(
            _remaps(self.advanced),
            {
                "~odom_world": "/uav1/prometheus/odom",
                "~planning/bspline": "/uav1/planning/bspline",
                "~planning/data_display": "/uav1/planning/data_display",
                "~planning/broadcast_bspline_from_planner": "/broadcast_bspline",
                "~planning/broadcast_bspline_to_planner": "/broadcast_bspline",
                "~grid_map/odom": "/uav1/prometheus/odom",
                "~grid_map/cloud": "/map_generator/global_cloud",
                "~grid_map/scan": "/uav1/prometheus/scan",
                "~grid_map/pose": "/depth/no_set",
                "~grid_map/depth": "/depth/image_rect_raw",
            },
        )

    def test_profile_geometry_and_dynamics_are_bound_once(self):
        expected = {
            "grid_map/uav_id": ("1", "int"),
            "fsm/flight_type": ("2", "int"),
            "fsm/thresh_replan_time": ("1.0", "double"),
            "fsm/thresh_no_replan_meter": ("0.2", "double"),
            "fsm/planning_horizon": ("13.5", "double"),
            "fsm/emergency_time": ("1.0", "double"),
            "fsm/realworld_experiment": ("false", "bool"),
            "fsm/fail_safe": ("true", "bool"),
            "fsm/waypoint_num": ("1", "int"),
            "fsm/waypoint0_x": ("4.0", "double"),
            "fsm/waypoint0_y": ("0.0", "double"),
            "fsm/waypoint0_z": ("3.0", "double"),
            "grid_map/resolution": ("0.1", "double"),
            "grid_map/map_size_x": ("20.0", "double"),
            "grid_map/map_size_y": ("12.0", "double"),
            "grid_map/map_size_z": ("6.0", "double"),
            "grid_map/map_origin_x": ("-10.0", "double"),
            "grid_map/map_origin_y": ("-6.0", "double"),
            "grid_map/local_update_range_x": ("9.0", "double"),
            "grid_map/local_update_range_y": ("7.0", "double"),
            "grid_map/local_update_range_z": ("6.0", "double"),
            "grid_map/obstacles_inflation": ("0.8", "double"),
            "grid_map/local_map_margin": ("10", "int"),
            "grid_map/ground_height": ("0.0", "double"),
            "grid_map/cx": ("321.04638671875", "double"),
            "grid_map/cy": ("243.44969177246094", "double"),
            "grid_map/fx": ("387.229248046875", "double"),
            "grid_map/fy": ("387.229248046875", "double"),
            "grid_map/use_depth_filter": ("true", "bool"),
            "grid_map/depth_filter_tolerance": ("0.15", "double"),
            "grid_map/depth_filter_maxdist": ("5.0", "double"),
            "grid_map/depth_filter_mindist": ("0.2", "double"),
            "grid_map/depth_filter_margin": ("2", "int"),
            "grid_map/k_depth_scaling_factor": ("1000.0", "double"),
            "grid_map/skip_pixel": ("2", "int"),
            "grid_map/p_hit": ("0.65", "double"),
            "grid_map/p_miss": ("0.35", "double"),
            "grid_map/p_min": ("0.12", "double"),
            "grid_map/p_max": ("0.90", "double"),
            "grid_map/p_occ": ("0.80", "double"),
            "grid_map/min_ray_length": ("0.1", "double"),
            "grid_map/max_ray_length": ("4.5", "double"),
            "grid_map/virtual_ceil_height": ("5.5", "double"),
            "grid_map/visualization_truncate_height": ("5.5", "double"),
            "grid_map/show_occ_time": ("false", "bool"),
            "grid_map/pose_type": ("2", "int"),
            "grid_map/frame_id": ("world", "string"),
            "manager/max_vel": ("0.8", "double"),
            "manager/max_acc": ("6.0", "double"),
            "manager/control_points_distance": ("0.4", "double"),
            "manager/feasibility_tolerance": ("0.05", "double"),
            "manager/planning_horizon": ("13.5", "double"),
            "manager/use_distinctive_trajs": ("true", "bool"),
            "manager/drone_id": ("1", "int"),
            "optimization/lambda_smooth": ("1.0", "double"),
            "optimization/lambda_collision": ("0.5", "double"),
            "optimization/lambda_feasibility": ("0.1", "double"),
            "optimization/lambda_fitness": ("1.0", "double"),
            "optimization/dist0": ("0.5", "double"),
            "optimization/swarm_clearance": ("0.5", "double"),
            "optimization/max_vel": ("0.8", "double"),
            "optimization/max_acc": ("6.0", "double"),
        }
        self.assertEqual(_typed_params(self.advanced), expected)

    def test_overlay_excludes_unread_or_unenforced_planner_parameters(self):
        for name in ("uav_id", "manager/max_jerk", "bspline/limit_vel",
                     "bspline/limit_acc", "bspline/limit_ratio"):
            self.assertNotIn(name, self.params)
        planner_source = PLANNER_NODE_SOURCE_PATH.read_text(encoding="utf-8")
        grid_source = GRID_SOURCE_PATH.read_text(encoding="utf-8")
        optimizer_source = OPTIMIZER_SOURCE_PATH.read_text(encoding="utf-8")
        manager_source = MANAGER_SOURCE_PATH.read_text(encoding="utf-8")
        self.assertNotIn('param("uav_id"', planner_source)
        self.assertNotIn('param("bspline/limit_', optimizer_source)
        self.assertIn('param("grid_map/uav_id"', grid_source)
        self.assertIn('param("manager/max_vel"', manager_source)
        self.assertIn('param("manager/max_acc"', manager_source)
        self.assertIn('param("manager/drone_id"', manager_source)
        self.assertIn("setPhysicalLimits(pp_.max_vel_, pp_.max_acc_", manager_source)
        self.assertIn('param("optimization/max_vel"', optimizer_source)
        self.assertIn('param("optimization/max_acc"', optimizer_source)

    def test_trigger_and_replan_semantics_are_source_backed(self):
        fsm_source = FSM_SOURCE_PATH.read_text(encoding="utf-8")
        self.assertEqual(_value(self.params, "fsm/realworld_experiment"), "false")
        self.assertIn("have_trigger_ = !flag_realworld_experiment_;", fsm_source)
        self.assertIn('nh.param("fsm/realworld_experiment", flag_realworld_experiment_', fsm_source)
        self.assertIn('trigger_sub_ = nh.subscribe("/uav"', fsm_source)
        self.assertIn("while (ros::ok() && (!have_odom_ || !have_trigger_))", fsm_source)
        self.assertIn('nh.param("fsm/flight_type", target_type_', fsm_source)
        self.assertIn('nh.param("fsm/waypoint_num", waypoint_num_', fsm_source)
        self.assertIn('nh.param("fsm/waypoint" + to_string(i) + "_x"', fsm_source)
        self.assertIn(
            'control_state_sub_ = nh.subscribe("/uav1/prometheus/control_state"',
            fsm_source,
        )
        self.assertIn("if (new_state == 2)", fsm_source)
        self.assertIn("command_mode_active = true", fsm_source)
        gate_start = fsm_source.index("if(!command_mode_active)")
        switch_start = fsm_source.index("switch (exec_state_)")
        self.assertLess(gate_start, switch_start)
        self.assertIn("changeFSMExecState(WAIT_TARGET", fsm_source[gate_start:switch_start])
        self.assertIn("realworld_experiment=false", self.contract)
        self.assertIn("免除外部 `/uav1/ego_trigger` 等待", self.contract)
        self.assertIn("control_state==2", self.contract)

    def test_single_cloud_boundary_and_world_map_alias_are_explicit(self):
        self.assertEqual(_remaps(self.advanced)["~grid_map/cloud"], "/map_generator/global_cloud")
        self.assertEqual(_value(self.params, "grid_map/frame_id"), "world")
        self.assertIn("world", self.contract)
        self.assertIn("map", self.contract)
        self.assertIn("同原点同轴", self.contract)

    def test_grid_param_updates_are_fail_closed_and_do_not_escape_init_storage(self):
        grid_source = GRID_SOURCE_PATH.read_text(encoding="utf-8")
        grid_header = (ROOT / "Modules/ego_planner_swarm/plan_env/include/plan_env/grid_map.h").read_text(
            encoding="utf-8"
        )
        callback_start = grid_source.index("void GridMap::gridparam_Callback")
        callback_end = grid_source.index("// 膨胀地图全部重置", callback_start)
        callback = grid_source[callback_start:callback_end]

        for pointer_member in (
            "grid_params_get_i", "grid_params_get_d", "grid_params_get_b",
            "grid_params_compare", "grid_params_compare_all", "pre_grid_params_compare",
        ):
            self.assertNotIn(pointer_member, grid_source)
            self.assertNotIn(pointer_member, grid_header)
        for local_name in ("uav_id", "x_size", "y_size", "z_size", "x_origin", "y_origin"):
            self.assertNotIn(f"&{local_name}", grid_source)
        self.assertNotIn("&mp_.map_size_", grid_source)
        self.assertNotIn("&mp_.map_origin_", grid_source)

        self.assertIn("if (!msg)", callback)
        self.assertIn("msg->param_name.size() != 1", callback)
        self.assertIn("msg->param_value.size() != 1", callback)
        self.assertIn("msg->param_name.front()", callback)
        self.assertIn("msg->param_value.front()", callback)
        self.assertNotIn("msg->param_name[0]", callback)
        self.assertNotIn("msg->param_value[0]", callback)
        self.assertIn("std::stol(text, &consumed, 10)", grid_source)
        self.assertIn("std::stod(text, &consumed)", grid_source)
        self.assertIn("std::isfinite(parsed)", grid_source)
        self.assertGreaterEqual(grid_source.count("catch (const std::exception&)"), 2)

        for initialization_only in (
            "uav_id", "resolution", "map_size_x", "map_size_y", "map_size_z",
            "map_origin_x", "map_origin_y", "depth_filter_margin", "skip_pixel",
            "pose_type", "fx", "fy", "cx", "cy", "k_depth_scaling_factor",
            "p_hit", "p_miss", "p_min", "p_max", "p_occ",
            "ground_height", "virtual_ceil_height", "virtual_ceil_yp", "virtual_ceil_yn",
        ):
            self.assertIn(f'"{initialization_only}"', grid_source)
        self.assertIn("kGridMapInitializationOnly.count(short_name)", callback)
        self.assertIn("initialization-only and was ignored", callback)

        for runtime_safe in (
            "local_update_range_x", "local_update_range_y", "local_update_range_z",
            "local_map_margin", "obstacles_inflation",
            "depth_filter_tolerance", "depth_filter_maxdist", "depth_filter_mindist",
            "min_ray_length", "max_ray_length",
            "visualization_truncate_height", "odom_depth_timeout", "use_depth_filter",
            "show_occ_time", "frame_id",
        ):
            self.assertIn(f'"{runtime_safe}"', callback)
        for initialization_only_field in (
            "mp_.fx_", "mp_.fy_", "mp_.cx_", "mp_.cy_", "mp_.k_depth_scaling_factor_",
        ):
            self.assertNotIn(initialization_only_field, callback)
        for derived_or_structural in (
            "mp_.resolution_ =", "mp_.map_size_ =", "mp_.map_origin_ =",
            "mp_.map_voxel_num_", "mp_.map_min_boundary_", "mp_.map_max_boundary_",
            "md_.occupancy_buffer_", "mp_.resolution_inv_", "mp_.prob_hit_log_",
            "mp_.prob_miss_log_", "mp_.clamp_min_log_", "mp_.clamp_max_log_",
            "mp_.min_occupancy_log_", "mp_.unknown_flag_", "pre_grid_params_compare",
        ):
            self.assertNotIn(derived_or_structural, callback)
        for boundary_expression in (
            "parsed > mp_.map_size_(axis)", "gridMapLocalMapMarginLimit(mp_)",
            "gridMapInflationStepLimit(mp_)", "kGridMapMaxInflationSteps",
            "gridMapDistanceLimit(mp_)", "parsed < mp_.depth_filter_mindist_",
            "parsed > mp_.depth_filter_maxdist_", "parsed > mp_.max_ray_length_",
            "parsed < mp_.min_ray_length_",
        ):
            self.assertIn(boundary_expression, grid_source)
        self.assertIn("unsupported parameter", callback)

        self.assertIn("param_settings", self.contract)
        self.assertIn("GridMap 参数回调 P1", self.contract)
        self.assertIn("静态修复已覆盖", self.contract)
        self.assertIn("相机内参", self.contract)
        self.assertIn("最多 32 个 voxel", self.contract)
        self.assertIn("未做 catkin/ROS 构建", self.contract)

    def test_scene_profile_values_and_hashes_match_contract(self):
        profile = PROFILE.EGO_SINGLE_BOX_V1
        self.assertEqual(profile.profile_id, "ego-single-box-v1")
        self.assertEqual(profile.origin, (-10.0, -6.0, 0.0))
        self.assertEqual(profile.size, (20.0, 12.0, 6.0))
        self.assertEqual(profile.voxel_resolution, 0.1)
        self.assertEqual(profile.obstacle.minimum, (-0.5, -1.0, 0.0))
        self.assertEqual(profile.obstacle.maximum, (0.5, 1.0, 5.5))
        self.assertEqual(len(profile.point_cloud()), 11000)
        for expected_hash in (
            profile.profile_hash,
            profile.collision_hash,
            profile.voxel_hash,
            profile.point_cloud_hash,
        ):
            self.assertIn(expected_hash, self.contract)

    def test_start_is_a_runtime_precondition_not_a_fake_planner_parameter(self):
        self.assertIn("(-4, 0, 3)", self.contract)
        self.assertIn("odom", self.contract)
        self.assertNotIn("fsm/start_x", self.params)
        self.assertNotIn("fsm/start_y", self.params)
        self.assertNotIn("fsm/start_z", self.params)

    def test_contract_preserves_static_only_boundary(self):
        for phrase in (
            "只做静态合同",
            "不启动 ROS / ROS2",
            "不声明真实规划器",
            "不声明已经完成真实飞行",
        ):
            self.assertIn(phrase, self.contract)
        self.assertIn("#29", self.contract)
        self.assertIn("#33", self.contract)


if __name__ == "__main__":
    unittest.main()
