#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent review and gap analysis tests for ArucoPublisherGuard.

Investigates:
  1. Real rclpy TopicEndpointInfo.endpoint_gid type handling (list of uint8).
  2. Silent second writer detection on DDS native target topics.
  3. GID validation strictness (rejection of non-hex, odd length, non-48-char hex, all-zero).
  4. Multi-topic initial binding atomicity (all-or-nothing guarantee).
  5. Subsequent snapshot state mutation flaw (snapshot_count increment before invariant check).
"""

from collections import namedtuple
import unittest

from Simulator.wksim_runtime.aruco_publisher_guard import (
    ArucoPublisherGuard,
    _is_nonzero_gid,
    _normalize_gid,
)

MockEndpointInfo = namedtuple(
    "MockEndpointInfo",
    ["node_name", "node_namespace", "topic_type", "endpoint_gid"],
)


class MockGraphNode:
    """Mock ROS2 Node implementing get_publishers_info_by_topic for testing."""

    def __init__(self, initial_graph: dict) -> None:
        self._graph = dict(initial_graph)

    def get_publishers_info_by_topic(self, topic: str):
        return list(self._graph.get(str(topic), []))

    def set_publishers(self, topic: str, publishers: list) -> None:
        self._graph[str(topic)] = list(publishers)


class TestArucoPublisherGuardReview(unittest.TestCase):
    """Review and audit test cases for ArucoPublisherGuard implementation."""

    def setUp(self):
        # Realistic 24-byte RTPS GID in integer list form (as provided by rclpy TopicEndpointInfo.endpoint_gid)
        self.raw_gid_int_list = [
            0x01, 0x0F, 0x7F, 0x01, 0xF6, 0x24, 0xC7, 0x07,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x14, 0x03,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        ]
        self.raw_gid_hex = bytes(self.raw_gid_int_list).hex()

    def test_rclpy_real_endpoint_gid_type(self):
        """Verify handling of rclpy TopicEndpointInfo.endpoint_gid runtime type (list of int)."""
        # In rclpy Humble, info.endpoint_gid is a list of integers (0..255)
        self.assertIsInstance(self.raw_gid_int_list, list)
        self.assertTrue(all(isinstance(x, int) for x in self.raw_gid_int_list))

        graph = {
            "/ap/cmd_gps_pose": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=self.raw_gid_int_list,
                )
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(
            node,
            "arducopter",
            {"/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition"},
        )

        res = guard.snapshot()
        self.assertTrue(guard.is_bound)
        # Normalized GID should match the 48-char hex string
        self.assertEqual(
            res["topics"]["/ap/cmd_gps_pose"]["endpoint_gid"],
            self.raw_gid_hex,
        )

    def test_silent_second_writer_rejected(self):
        """Verify that a silent/dormant second writer triggers immediate rejection."""
        graph = {
            "/ap/cmd_gps_pose": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=self.raw_gid_int_list,
                ),
                # Silent second writer (e.g. rogue participant or stale daemon)
                MockEndpointInfo(
                    node_name="dormant_second_writer",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=[0x01] * 24,
                ),
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(
            node,
            "arducopter",
            {"/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition"},
        )

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("multiple publishers", str(ctx.exception))
        self.assertIn("dormant_second_writer", str(ctx.exception))
        # Guard must not be bound
        self.assertFalse(guard.is_bound)

    def test_gid_strictness_rejection_of_invalid_gids(self):
        """Verify that _is_nonzero_gid rejects non-hex, odd length, non-48, and zero GIDs."""
        # Non-hex characters
        self.assertFalse(_is_nonzero_gid("zz" * 24))
        # Odd length (33 chars)
        self.assertFalse(_is_nonzero_gid("010f7f01f624c70700000000000014031"))
        # Non-48 length (32 chars / 16 bytes)
        self.assertFalse(_is_nonzero_gid("01" * 16))
        # Arbitrary length (34 chars)
        self.assertFalse(_is_nonzero_gid("01" * 17))
        # All zeros (48 chars)
        self.assertFalse(_is_nonzero_gid("0" * 48))
        # Valid 48-char hex GID
        self.assertTrue(_is_nonzero_gid(self.raw_gid_hex))

        # Test that guard.snapshot() rejects non-48-char or non-hex GIDs with ValueError
        for bad_gid in ["zz" * 24, "01" * 16, "0" * 48]:
            graph = {
                "/ap/cmd_gps_pose": [
                    MockEndpointInfo(
                        node_name="wksim_joint_arducopter_control",
                        node_namespace="/",
                        topic_type="ardupilot_msgs/msg/GlobalPosition",
                        endpoint_gid=bad_gid,
                    )
                ]
            }
            node = MockGraphNode(graph)
            guard = ArucoPublisherGuard(
                node,
                "arducopter",
                {"/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition"},
            )
            with self.assertRaises(ValueError) as ctx:
                guard.snapshot()
            self.assertIn("zero or incomplete GID", str(ctx.exception))

    def test_multi_topic_initial_binding_atomicity(self):
        """Verify initial snapshot binding is all-or-nothing (atomic)."""
        # Topic 1 is valid, but Topic 2 has no publishers
        graph = {
            "/ap/cmd_gps_pose": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=self.raw_gid_int_list,
                )
            ],
            "/ap/cmd_vel": [],  # missing publisher
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

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("has no publishers", str(ctx.exception))

        # Atomicity assertion: neither topic was partially bound
        self.assertFalse(guard.is_bound)
        self.assertIsNone(guard.bound_snapshot)
        self.assertEqual(guard._snapshot_count, 0)

    def test_subsequent_snapshot_count_advance_flaw(self):
        """GAP AUDIT: Subsequent snapshot increments _snapshot_count before verifying invariant."""
        graph = {
            "/ap/cmd_gps_pose": [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=self.raw_gid_int_list,
                )
            ]
        }
        node = MockGraphNode(graph)
        guard = ArucoPublisherGuard(
            node,
            "arducopter",
            {"/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition"},
        )

        # Initial snapshot passes -> snapshot_count = 1
        guard.snapshot()
        self.assertEqual(guard._snapshot_count, 1)

        # Subsequent snapshot encounters GID swap
        swapped_gid = [0xFF] * 24
        node.set_publishers(
            "/ap/cmd_gps_pose",
            [
                MockEndpointInfo(
                    node_name="wksim_joint_arducopter_control",
                    node_namespace="/",
                    topic_type="ardupilot_msgs/msg/GlobalPosition",
                    endpoint_gid=swapped_gid,
                )
            ],
        )

        with self.assertRaises(ValueError) as ctx:
            guard.snapshot()
        self.assertIn("publisher GID changed across snapshots", str(ctx.exception))

        # Failed discovery must not consume an accepted snapshot sequence.
        self.assertEqual(guard._snapshot_count, 1)


if __name__ == "__main__":
    unittest.main()
