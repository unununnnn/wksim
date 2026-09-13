"""Offline tests for the ROS1 EGO profile PointCloud2 payload helper."""

from __future__ import annotations

import hashlib
import json
import sys
import types
import unittest
from unittest import mock

from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1
from tools.publish_ego_profile_scene import (
    FRAME_ALIAS,
    TOPIC,
    decode_xyz32,
    float32_round_trip,
    pack_xyz32,
    payload_identity,
    point_to_voxel_index,
    source_points,
    validate_pointcloud_message,
    voxel_set_hash,
)


class EgoProfilePointCloudPayloadTests(unittest.TestCase):
    def test_payload_uses_profile_api_and_fixed_ros_contract(self):
        points = source_points()
        self.assertEqual(len(points), 11000)
        self.assertEqual(points[0], (-0.45, -0.95, 0.05))
        self.assertEqual(points[-1], (0.45, 0.95, 5.45))

        identity = payload_identity()
        self.assertEqual(identity["profile_id"], "ego-single-box-v1")
        self.assertEqual(identity["profile_hash"], EGO_SINGLE_BOX_V1.profile_hash)
        self.assertEqual(identity["voxel_hash"], EGO_SINGLE_BOX_V1.voxel_hash)
        self.assertEqual(identity["point_count"], 11000)
        self.assertEqual(identity["message_point_count"], 11000)
        self.assertEqual(identity["topic"], TOPIC)
        self.assertEqual(identity["frame_alias"], FRAME_ALIAS)
        self.assertTrue(identity["message_matches_source_voxel_set"])
        self.assertEqual(identity["message_voxel_set_hash"],
                         identity["source_voxel_set_hash"])

    def test_float32_payload_reconstructs_the_same_voxel_set(self):
        points = source_points()
        payload = pack_xyz32(points)
        reconstructed = decode_xyz32(payload, count=len(points))
        expected_indices = tuple(EGO_SINGLE_BOX_V1.voxel_indices())
        actual_indices = tuple(point_to_voxel_index(point) for point in reconstructed)

        self.assertEqual(len(payload), 11000 * 12)
        self.assertEqual(len(reconstructed), 11000)
        self.assertEqual(set(actual_indices), set(expected_indices))
        self.assertEqual(voxel_set_hash(actual_indices), voxel_set_hash(expected_indices))
        self.assertNotEqual(hashlib.sha256(payload).hexdigest(),
                            voxel_set_hash(actual_indices),
                            "float32 bytes must not be called the voxel-set hash")

    def test_float32_round_trip_is_the_message_coordinate_representation(self):
        points = source_points()
        reconstructed = float32_round_trip(points)
        self.assertNotEqual(reconstructed[0], points[0])
        self.assertEqual(tuple(point_to_voxel_index(point) for point in reconstructed),
                         EGO_SINGLE_BOX_V1.voxel_indices())

    def test_voxel_set_hash_is_order_independent(self):
        indices = ((1, 2, 3), (0, 4, 5), (1, 2, 3))
        self.assertEqual(voxel_set_hash(indices), voxel_set_hash(reversed(indices)))

    def test_payload_identity_is_json_serializable(self):
        json.dumps(payload_identity(), sort_keys=True)

    def test_actual_pointcloud_payload_rejects_voxel_counterexample(self):
        fields = tuple(
            types.SimpleNamespace(name=name, offset=offset, datatype=7, count=1)
            for name, offset in (("x", 0), ("y", 4), ("z", 8))
        )
        points = list(source_points())
        points[0] = (points[0][0], points[0][1], points[0][2] + 0.1)
        message = types.SimpleNamespace(
            header=types.SimpleNamespace(frame_id=FRAME_ALIAS),
            fields=fields,
            is_bigendian=False,
            point_step=12,
            width=11000,
            height=1,
            row_step=11000 * 12,
            data=pack_xyz32(points),
        )

        with self.assertRaisesRegex(ValueError, "voxel set"):
            validate_pointcloud_message(message)

    def test_actual_pointcloud_payload_rejects_field_counterexample(self):
        fields = tuple(
            types.SimpleNamespace(name=name, offset=offset, datatype=7, count=1)
            for name, offset in (("x", 0), ("y", 8), ("z", 4))
        )
        message = types.SimpleNamespace(
            header=types.SimpleNamespace(frame_id=FRAME_ALIAS),
            fields=fields,
            is_bigendian=False,
            point_step=12,
            width=11000,
            height=1,
            row_step=11000 * 12,
            data=pack_xyz32(source_points()),
        )

        with self.assertRaisesRegex(ValueError, "fields"):
            validate_pointcloud_message(message)


class _FrozenRosClockPublisherTests(unittest.TestCase):
    def test_publish_uses_wall_clock_when_ros_clock_is_frozen(self):
        import tools.publish_ego_profile_scene as publisher_module

        class FakeTime:
            @staticmethod
            def now():
                return 42.0

        class FakePublisher:
            def __init__(self):
                self.messages = []

            def get_num_connections(self):
                return 1

            def publish(self, message):
                self.messages.append(message)

        fake_publisher = FakePublisher()
        fake_rospy = types.ModuleType("rospy")
        fake_rospy.init_node = lambda *args, **kwargs: None
        fake_rospy.get_param = lambda name, default: True
        fake_rospy.is_shutdown = lambda: False
        fake_rospy.Publisher = lambda *args, **kwargs: fake_publisher
        fake_rospy.Time = FakeTime

        class FakePointCloud2:
            pass

        class FakeHeader:
            def __init__(self, frame_id=""):
                self.frame_id = frame_id
                self.stamp = None

        fake_point_cloud2 = types.ModuleType("sensor_msgs.point_cloud2")

        def create_cloud_xyz32(header, points):
            fields = tuple(
                types.SimpleNamespace(name=name, offset=offset, datatype=7, count=1)
                for name, offset in (("x", 0), ("y", 4), ("z", 8))
            )
            return types.SimpleNamespace(
                header=header,
                fields=fields,
                is_bigendian=False,
                point_step=12,
                width=len(points),
                height=1,
                row_step=len(points) * 12,
                data=pack_xyz32(points),
            )

        fake_point_cloud2.create_cloud_xyz32 = create_cloud_xyz32
        fake_sensor_msgs = types.ModuleType("sensor_msgs")
        fake_sensor_msgs.point_cloud2 = fake_point_cloud2
        fake_sensor_msgs_msg = types.ModuleType("sensor_msgs.msg")
        fake_sensor_msgs_msg.PointCloud2 = FakePointCloud2
        fake_std_msgs = types.ModuleType("std_msgs")
        fake_std_msgs_msg = types.ModuleType("std_msgs.msg")
        fake_std_msgs_msg.Header = FakeHeader

        fake_wall = [0.0]

        def wall_monotonic():
            return fake_wall[0]

        def wall_sleep(seconds):
            self.assertGreater(seconds, 0.0)
            fake_wall[0] += seconds

        args = types.SimpleNamespace(
            master_uri="http://127.0.0.1:11311",
            duration=0.25,
            rate=10.0,
            subscriber_timeout=0.2,
        )
        module_names = {
            "rospy": fake_rospy,
            "sensor_msgs": fake_sensor_msgs,
            "sensor_msgs.point_cloud2": fake_point_cloud2,
            "sensor_msgs.msg": fake_sensor_msgs_msg,
            "std_msgs": fake_std_msgs,
            "std_msgs.msg": fake_std_msgs_msg,
        }
        with mock.patch.dict(sys.modules, module_names), \
             mock.patch.object(publisher_module.time, "monotonic", side_effect=wall_monotonic), \
             mock.patch.object(publisher_module.time, "sleep", side_effect=wall_sleep), \
             mock.patch.object(publisher_module.time, "time", return_value=0.0):
            summary = publisher_module.publish(args)

        self.assertTrue(summary["use_sim_time"])
        self.assertGreater(summary["published_count"], 0)
        self.assertEqual(len(fake_publisher.messages), summary["published_count"])
        self.assertTrue(all(message.header.stamp == 42.0 for message in fake_publisher.messages))


if __name__ == "__main__":
    unittest.main()
