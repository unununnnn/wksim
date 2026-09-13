"""Opt-in generated SetupRequest wire checks; no ROS node, graph or FC."""
import os
import unittest

ENABLED = os.environ.get("WKSIM_TEST_PRIVATE_ROS") == "1"
if ENABLED:
    from rclpy.serialization import deserialize_message, serialize_message
    from prometheus_msgs.msg import UAVSetup
    from wksim_msgs.msg import SetupRequest
    from Simulator.wksim_runtime.trajectory_bridge import build_ros_mode_request


@unittest.skipUnless(ENABLED, "requires the sourced ROS2 message overlay")
class ModeRequestWireTests(unittest.TestCase):
    def arguments(self):
        return dict(mode="BRAKE", stamp_ns=12_345_678_901, run_id="release-wire",
                    control_epoch="a" * 32, request_id=2**64 - 1)

    def test_generated_message_round_trip_preserves_public_fields(self):
        for mode in ("POSCTL", "AUTO.LOITER", "AUTO.LAND", "AUTO.RTL", "BRAKE"):
            with self.subTest(mode=mode):
                args = self.arguments(); args["mode"] = mode
                request = build_ros_mode_request(**args)
                decoded = deserialize_message(serialize_message(request), SetupRequest)
                self.assertEqual(decoded.version, SetupRequest.VERSION)
                self.assertEqual(decoded.run_id, args["run_id"])
                self.assertEqual(decoded.control_epoch, args["control_epoch"])
                self.assertEqual(decoded.request_id, args["request_id"])
                self.assertEqual(decoded.setup.cmd, UAVSetup.SET_PX4_MODE)
                self.assertEqual(decoded.setup.px4_mode, mode)
                self.assertEqual(decoded.setup.header.frame_id, "map")
                self.assertEqual((decoded.setup.header.stamp.sec, decoded.setup.header.stamp.nanosec),
                                 (12, 345_678_901))

    def test_malformed_identity_and_counter_rejected_before_message_use(self):
        for field, value in (("mode", "OFFBOARD"), ("mode", None), ("run_id", ""),
                             ("run_id", "x" * 65), ("control_epoch", "A" * 32),
                             ("control_epoch", "wrong"), ("request_id", 0),
                             ("request_id", True), ("request_id", 2**64),
                             ("stamp_ns", True), ("stamp_ns", -1),
                             ("stamp_ns", 2**31 * 1_000_000_000)):
            args = self.arguments(); args[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                build_ros_mode_request(**args)


if __name__ == "__main__":
    unittest.main()
