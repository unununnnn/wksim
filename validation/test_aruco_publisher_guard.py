#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit and regression tests for ArucoPublisherGuard.

Verifies:
  1. Guard initialization and topic type name deduction from ChannelSpec / dict / tuples.
  2. Initial snapshot binding (node_name, namespace, type, GID, monotonic timestamp).
  3. Invariance checks on subsequent snapshots across session lifecycle.
  4. Detection and rejection of a silent second publisher (negative test).
  5. Detection and rejection of missing publisher, wrong node name, wrong namespace, or wrong type.
  6. Detection and rejection of zero/empty GID.
  7. Detection and rejection of mid-session GID change / forking.
  8. Sample validation via validate_sample(topic, gid) rejecting unknown publishers.
"""

from collections import namedtuple
import copy
from typing import Any, Dict, List
import unittest

from Simulator.wksim_runtime.aruco_publisher_guard import ArucoPublisherGuard

# Stub for ROS2 TopicEndpointInfo
MockEndpointInfo = namedtuple(
    "MockEndpointInfo",
    ["node_name", "node_namespace", "topic_type", "endpoint_gid"],
)


class MockGraphNode:
    """Mock ROS2 Node implementing get_publishers_info_by_topic for testing."""

    def __init__(self, initial_graph: Dict[str, List[MockEndpointInfo]]) -> None:
        self._graph: Dict[str, List[MockEndpointInfo]] = copy.deepcopy(initial_graph)

    def get_publishers_info_by_topic(self, topic: str) -> List[MockEndpointInfo]:
        return list(self._graph.get(str(topic), []))

    def set_publishers(self, topic: str, publishers: List[MockEndpointInfo]) -> None:
        self._graph[str(topic)] = list(publishers)


class TestArucoPublisherGuard(unittest.TestCase):
    """Test suite for ArucoPublisherGuard."""

    def setUp(self):
        self.ap_gid_gps = "010f7f01f624c70700000000000014030000000000000000"
        self.ap_gid_vel = "010f7f01f624c70700000000000015030000000000000000"
        self.px4_gid_traj = "010f7f014b267c240000000000001c030000000000000000"
        self.px4_gid_cmd = "010f7f014b267c240000000000001a030000000000000000"

    def test_init_and_topic_normalization(self):
        """Test guard initialization and topic specification flexibility."""
        node = MockGraphNode({})

        # 1. Dict mapping
        topics_dict = {
            "/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition",
            "/ap/cmd_vel": "geometry_msgs/msg/TwistStamped",
        }
        guard = ArucoPublisherGuard(node, "arducopter", topics_dict)
        self.assertEqual(guard.stack, "arducopter")
        self.assertEqual(guard.expected_node_name, "wksim_joint_arducopter_control")
        self.assertEqual(guard.expected_topics, topics_dict)
        self.assertFalse(guard.is_bound)

        # 2. Sequence of ChannelSpec-like objects
        ChannelSpecLike = namedtuple("ChannelSpecLike", ["topic", "msg_type", "type_name"])
        spec_list = [
            ChannelSpecLike("/wksim_px4_21/fmu/in/trajectory_setpoint", None, "px4_msgs/msg/TrajectorySetpoint"),
            ChannelSpecLike("/wksim_px4_21/fmu/in/vehicle_command", None, "px4_msgs/msg/VehicleCommand"),
        ]
        guard_px4 = ArucoPublisherGuard(node, "px4", spec_list)
        self.assertEqual(guard_px4.stack, "px4")
        self.assertEqual(guard_px4.expected_node_name, "wksim_joint_px4_control")
        self.assertEqual(
            guard_px4.expected_topics,
            {
                "/wksim_px4_21/fmu/in/trajectory_setpoint": "px4_msgs/msg/TrajectorySetpoint",
                "/wksim_px4_21/fmu/in/vehicle_command": "px4_msgs/msg/VehicleCommand",
            },
        )

        # 3. Invalid inputs
        with self.assertRaises(ValueError):
            ArucoPublisherGuard(node, "", topics_dict)
        with self.assertRaises(ValueError):
            ArucoPublisherGuard(node, "px4", {})
        with self.assertRaises(TypeError):
            ArucoPublisherGuard(node, "px4", 123)

    def test_initial_snapshot_binding_success(self):
        """Test successful initial snapshot binding with valid graph topology."""
        graph = {
            "/ap/cmd_gps_pose": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=bytes.fromhex(self.ap_gid_gps),
                )
            ],
            "/ap/cmd_vel": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="geometry_msgs/msg/TwistStamped",
                    endpoint_gid=self.ap_gid_vel,
                )
            ],
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(
            node,
            "arducopter",
            {
                "/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition",
                "/ap/cmd_vel": "geometry_msgs/msg/TwistStamped",
            },
        )

        res = guard.snapshot()
        self.assertTrue(guard.is_bound)
        self.assertEqual(res["node_name"], "wksim_joint_arducopter_control")
        self.assertEqual(res["stack"], "arducopter")
        self.assertEqual(res["snapshot_index"], 1)
        self.assertGreater(res["monotonic_ns"], 0)
        self.assertGreater(res["monotonic_s"], 0)

        topics = res["topics"]
        self.assertEqual(topics["/ap/cmd_gps_pose"]["endpoint_gid"], self.ap_gid_gps)
        self.assertEqual(topics["/ap/cmd_gps_pose"]["type_name"], "ardupilot_msgs/msg/GlobalPosition")
        self.assertEqual(topics["/ap/cmd_vel"]["endpoint_gid"], self.ap_gid_vel)

    def test_subsequent_snapshot_invariance(self):
        """Test that multiple subsequent snapshots succeed when topology is invariant."""
        graph = {
            "/ap/cmd_gps_pose": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=self.ap_gid_gps,
                )
            ],
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition"})

        snap1 = guard.snapshot()
        self.assertEqual(snap1["snapshot_index"], 1)

        snap2 = guard.snapshot()
        self.assertEqual(snap2["snapshot_index"], 2)
        self.assertGreaterEqual(snap2["monotonic_ns"], snap1["monotonic_ns"])
        self.assertEqual(snap2["topics"], snap1["topics"])

    def test_silent_second_publisher_detected_and_rejected(self):
        """CRITICAL NEGATIVE TEST: A silent/dormant second publisher must immediately raise ValueError."""
        graph = {
            "/ap/cmd_vel": [
                # Legitimate Control node publisher
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="geometry_msgs/msg/TwistStamped",
                    endpoint_gid=self.ap_gid_vel,
                ),
                # Stray / silent second publisher on the same DDS topic
                MockEndpointInfo(
                    node_name="rogue_or_leftover_publisher",
                    node_namespace="/",
                    topic_type="geometry_msgs/msg/TwistStamped",
                    endpoint_gid="010f7f019999999900000000000015030000000000000000",
                ),
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_vel": "geometry_msgs/msg/TwistStamped"})

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("multiple publishers", str(ctx.exception))
        self.assertIn("rogue_or_leftover_publisher", str(ctx.exception))

    def test_missing_publisher_rejected(self):
        """Negative test: Topic with 0 publishers raises ValueError."""
        node = MockGraphNode({"/ap/cmd_vel": []})
        guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_vel": "geometry_msgs/msg/TwistStamped"})

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("has no publishers", str(ctx.exception))

    def test_wrong_node_name_rejected(self):
        """Negative test: Publisher owned by unexpected node raises ValueError."""
        graph = {
            "/ap/cmd_vel": [
                MockEndpointInfo(
                    node_name="wrong_control_node",
                    node_namespace="/",
                    topic_type="geometry_msgs/msg/TwistStamped",
                    endpoint_gid=self.ap_gid_vel,
                )
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_vel": "geometry_msgs/msg/TwistStamped"})

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("publisher node_name", str(ctx.exception))
        self.assertIn("wrong_control_node", str(ctx.exception))

    def test_wrong_namespace_rejected(self):
        """Negative test: Publisher with non-root namespace raises ValueError."""
        graph = {
            "/ap/cmd_vel": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/uav1",
                    topic_type="geometry_msgs/msg/TwistStamped",
                    endpoint_gid=self.ap_gid_vel,
                )
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_vel": "geometry_msgs/msg/TwistStamped"})

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("publisher node_namespace", str(ctx.exception))

    def test_wrong_message_type_rejected(self):
        """Negative test: Mismatched message type raises ValueError."""
        graph = {
            "/ap/cmd_vel": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="std_msgs/msg/String",
                    endpoint_gid=self.ap_gid_vel,
                )
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_vel": "geometry_msgs/msg/TwistStamped"})

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("message type", str(ctx.exception))

    def test_zero_or_incomplete_gid_rejected(self):
        """Negative test: All-zero or truncated GID raises ValueError."""
        for bad_gid in ["00" * 24, "00" * 16, b"\x00" * 24, "1234"]:
            graph = {
                "/ap/cmd_vel": [
                    MockEndpointInfo(
                        node_name="wksim_joint_arducopter_control",
                        node_namespace="/",
                        topic_type="geometry_msgs/msg/TwistStamped",
                        endpoint_gid=bad_gid,
                    )
                ]
            }
            node = MockGraphNode(graph)
            guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_vel": "geometry_msgs/msg/TwistStamped"})

            with self.assertRaises(ValueError) as ctx:
                guard.snapshot()
            self.assertIn("zero or incomplete GID", str(ctx.exception))

    def test_mid_flight_gid_change_rejected(self):
        """Negative test: Changing GID between initial snapshot and subsequent snapshot raises ValueError."""
        graph = {
            "/ap/cmd_vel": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="geometry_msgs/msg/TwistStamped",
                    endpoint_gid=self.ap_gid_vel,
                )
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(node, "arducopter", {"/ap/cmd_vel": "geometry_msgs/msg/TwistStamped"})

        # Initial snapshot passes
        guard.snapshot()

        # Simulate publisher replacement / forking with a new GID
        swapped_gid = "010f7f01ffffffff00000000000015030000000000000000"
        node.set_publishers(
            "/ap/cmd_vel",
            [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="geometry_msgs/msg/TwistStamped",
                    endpoint_gid=swapped_gid,
                )
            ],
        )

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("publisher GID changed across snapshots", str(ctx.exception))

    def test_validate_sample(self):
        """Test validate_sample against bound publisher GID."""
        graph = {
            "/wksim_px4_21/fmu/in/trajectory_setpoint": [
                MockEndpointInfo(
                    node_name="wksim_joint_px4_control",
                    node_namespace="/",
                    topic_type="px4_msgs/msg/TrajectorySetpoint",
                    endpoint_gid=self.px4_gid_traj,
                )
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(
            node,
            "px4",
            {"/wksim_px4_21/fmu/in/trajectory_setpoint": "px4_msgs/msg/TrajectorySetpoint"},
        )

        # Cannot validate before snapshot
        with self.assertRaises(ValueError):
            guard.validate_sample("/wksim_px4_21/fmu/in/trajectory_setpoint", self.px4_gid_traj)

        # Snapshot and bind
        guard.snapshot()

        # Valid sample (hex string)
        self.assertTrue(guard.validate_sample("/wksim_px4_21/fmu/in/trajectory_setpoint", self.px4_gid_traj))
        # Valid sample (bytes)
        self.assertTrue(guard.validate_sample("/wksim_px4_21/fmu/in/trajectory_setpoint", bytes.fromhex(self.px4_gid_traj)))

        # Invalid sample (different GID)
        with self.assertRaises(ValueError) as ctx:
            guard.validate_sample("/wksim_px4_21/fmu/in/trajectory_setpoint", "010f7f01deadbeef0000000000001c030000000000000000")
        self.assertIn("Rejected sample", str(ctx.exception))

        # Invalid sample (unmanaged topic)
        with self.assertRaises(ValueError) as ctx:
            guard.validate_sample("/wksim_px4_21/fmu/out/vehicle_status_v1", self.px4_gid_traj)
        self.assertIn("not a guarded native target topic", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
