"""Pure-Python contract tests for the ROS1 Bspline relay.

These tests deliberately do not import rospy, build catkin, start ROS, or claim
that an external ros1_bridge is installed.  They prove the relay's local copy
contract and its topic/legacy-command boundary only.
"""

import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
RELAY_PATH = ROOT / "Modules/ego_planner_swarm/plan_manage/scripts/bspline_ros1_relay.py"
LAUNCH_PATH = ROOT / "Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/bspline_ros1_relay.launch"
CMAKE_PATH = ROOT / "Modules/ego_planner_swarm/plan_manage/CMakeLists.txt"
SPEC = importlib.util.spec_from_file_location("bspline_ros1_relay", RELAY_PATH)
RELAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELAY)


class Ros1BsplineRelayContractTests(unittest.TestCase):
    def test_schema_and_private_topics(self):
        self.assertEqual(
            RELAY.BSPLINE_FIELDS,
            ("drone_id", "order", "traj_id", "start_time",
             "knots", "pos_pts", "yaw_pts", "yaw_dt"),
        )
        input_topic, output_topic = RELAY.relay_topics(1)
        self.assertEqual(input_topic, "/uav1/planning/bspline")
        self.assertEqual(output_topic, "/uav1/planning/bspline_ros1_prometheus")
        self.assertNotEqual(input_topic, output_topic)
        self.assertNotIn("/prometheus/command", output_topic)

    def test_copy_preserves_all_fields_and_does_not_mutate_source(self):
        source = SimpleNamespace(
            drone_id=0,
            order=3,
            traj_id=17,
            start_time=SimpleNamespace(secs=12, nsecs=345),
            knots=[0.0, 0.1, 0.2, 0.3],
            pos_pts=[SimpleNamespace(x=1.0, y=2.0, z=3.0)],
            yaw_pts=[],
            yaw_dt=0.0,
        )
        before = copy.deepcopy(source)
        target = SimpleNamespace()
        result = RELAY.copy_bspline_fields(source, target)

        self.assertIs(result, target)
        self.assertEqual(set(vars(target)), set(RELAY.BSPLINE_FIELDS))
        for field in RELAY.BSPLINE_FIELDS:
            self.assertEqual(getattr(target, field), getattr(source, field))
        self.assertEqual(source, before)

        target.knots.append(9.0)
        target.pos_pts[0].x = 99.0
        self.assertEqual(source.knots, before.knots)
        self.assertEqual(source.pos_pts, before.pos_pts)

    def test_missing_field_is_rejected_without_output_object_mutation(self):
        source = SimpleNamespace(drone_id=0)
        target = SimpleNamespace(existing="sentinel")
        with self.assertRaisesRegex(ValueError, "missing Bspline field: order"):
            RELAY.copy_bspline_fields(source, target)
        self.assertEqual(target.existing, "sentinel")
        self.assertFalse(hasattr(target, "drone_id"))

    def test_relay_source_has_no_legacy_command_boundary(self):
        source = RELAY_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "UAVCommand",
            "CommandRequest",
            "/prometheus/command",
            "/v2/command",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("TrajUtilsBspline", source)
        self.assertIn("PrometheusBspline", source)
        self.assertIn("rospy.Subscriber(input_topic, TrajUtilsBspline", source)
        self.assertIn("rospy.Publisher(output_topic, PrometheusBspline", source)

    def test_catkin_install_declares_existing_relay_launch(self):
        self.assertTrue(LAUNCH_PATH.is_file())
        self.assertEqual(LAUNCH_PATH.read_text(encoding="utf-8").lstrip()[:7], "<launch")
        cmake = CMAKE_PATH.read_text(encoding="utf-8")
        self.assertRegex(
            cmake,
            r"install\(\s*FILES\s+launch_for_prometheus/bspline_ros1_relay\.launch"
            r"\s+DESTINATION\s+\$\{CATKIN_PACKAGE_SHARE_DESTINATION\}/launch_for_prometheus\s*\)",
        )


if __name__ == "__main__":
    unittest.main()
