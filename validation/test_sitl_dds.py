"""Small native DDS boundary checks; real wire/control verification is separate."""
from pathlib import Path
import math
import tempfile
import time
from types import SimpleNamespace
import unittest

from tools.sitl_dds import NativeDDS, angle_error, enu_to_ned, ned_yaw_to_enu, offset_latlon, px4_topic, quaternion_yaw
from tools.validate_dds_schemas import check


class DDSBoundaryTests(unittest.TestCase):
    def test_yaw_feedback_frames_and_wrap(self):
        for yaw in (0.0, -math.pi / 2, math.pi / 3, math.pi - 0.01, -math.pi + 0.01):
            q = SimpleNamespace(x=0, y=0, z=2 * math.sin(yaw / 2), w=2 * math.cos(yaw / 2))
            self.assertLess(angle_error(quaternion_yaw(q), yaw), 1e-12)
        self.assertAlmostEqual(ned_yaw_to_enu(0.0), math.pi / 2)
        self.assertAlmostEqual(ned_yaw_to_enu(math.pi / 2), 0.0)
        self.assertAlmostEqual(angle_error(math.pi - 0.01, -math.pi + 0.01), 0.02)
        for value in (0.0, math.nan, math.inf):
            with self.assertRaises(ValueError):
                quaternion_yaw(SimpleNamespace(x=0, y=0, z=0, w=value))
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                ned_yaw_to_enu(value)
            with self.assertRaises(ValueError):
                angle_error(value, 0.0)

    def test_axes_and_small_global_waypoint(self):
        self.assertEqual(enu_to_ned([2, 3, 4]), [3, 2, -4])
        lat, lon = offset_latlon(40, 116, 3, 2)
        self.assertAlmostEqual(lat, 40.00002694946, places=9)
        self.assertAlmostEqual(lon, 116.00002345335, places=9)

    def test_versioned_topic_name(self):
        self.assertEqual(px4_topic("out", "vehicle_status", SimpleNamespace(MESSAGE_VERSION=1)),
                         "/wksim_px4_21/fmu/out/vehicle_status_v1")
        self.assertEqual(px4_topic("in", "offboard_control_mode", SimpleNamespace()),
                         "/wksim_px4_21/fmu/in/offboard_control_mode")

    def test_simulation_timestamp_is_not_wall_clock_and_rejects_stale_state(self):
        controller = NativeDDS.__new__(NativeDDS)
        controller.latest = {"position": SimpleNamespace(timestamp=9000000)}
        controller.received_at = {"position": time.monotonic()}
        self.assertEqual(controller.px4_timestamp(), 9000000)
        controller.received_at["position"] -= 3
        with self.assertRaises(RuntimeError):
            controller.px4_timestamp()

    def test_schema_comparison_checks_nested_fields_and_constants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "px4/src/modules/uxrce_dds_client").mkdir(parents=True)
            (root / "px4/msg").mkdir()
            (root / "ros/msg").mkdir(parents=True)
            (root / "px4/src/modules/uxrce_dds_client/dds_topics.yaml").write_text(
                "publications:\n  - topic: /fmu/out/parent\n    type: px4_msgs::msg::Parent\n")
            for side in ("px4", "ros"):
                (root / side / "msg/Parent.msg").write_text("uint32 MESSAGE_VERSION = 1\nChild[2] child\n")
                (root / side / "msg/Child.msg").write_text("float32 value\n")
            self.assertEqual(check(root / "px4", root / "ros")["status"], "pass")
            (root / "ros/msg/Child.msg").write_text("float64 value\n")
            self.assertFalse(check(root / "px4", root / "ros")["schemas"]["Child"]["match"])
            (root / "ros/msg/Parent.msg").write_text("uint32 MESSAGE_VERSION = 2\nChild[2] child\n")
            self.assertFalse(check(root / "px4", root / "ros")["schemas"]["Parent"]["match"])


if __name__ == "__main__":
    unittest.main()
