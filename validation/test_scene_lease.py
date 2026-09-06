"""Permission identity/replay/lifetime rules; no simulated FC acceptance."""
import json
import unittest
import os
import importlib.util

if importlib.util.find_spec('prometheus_control.scene') is None:
    raise unittest.SkipTest('Explicit new scene permission source/candidate required')
from prometheus_control.scene import SceneLease


class SceneLeaseTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.lease = SceneLease('run', 'a'*32, lambda:self.now)
        self.value = dict(version=1, run_id='run', scene_epoch='a'*32, sequence=1,
            request_id=0, phase='running', tick=10000, time_ns=10000000000,
            issued_monotonic_s=self.now, lease_seconds=.5)

    def send(self, **values):
        self.value.update(values)
        return self.lease.accept(json.dumps(self.value))

    def test_missing_foreign_or_replayed_lease_cannot_grant_or_refresh(self):
        with self.assertRaisesRegex(ValueError, 'not_received'):
            self.lease.check()
        self.assertFalse(self.send(scene_epoch='b'*32))
        self.assertIsNone(self.lease.value)
        self.assertTrue(self.send(scene_epoch='a'*32))
        self.now += .51
        self.assertFalse(self.send())
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.lease.check()
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.send(sequence=2, issued_monotonic_s=self.now)

    def test_paused_heartbeat_cannot_manufacture_time_or_skip_request(self):
        self.send()
        with self.assertRaisesRegex(ValueError, 'without_new_request'):
            self.send(sequence=2, phase='paused')
        self.setUp(); self.send()
        self.send(sequence=2, request_id=1, phase='paused')
        with self.assertRaisesRegex(ValueError, 'without_step'):
            self.send(sequence=3, tick=10001, time_ns=10001000000)

    def test_explicit_four_step_resume_and_invalid_frames(self):
        self.send()
        self.send(sequence=2, request_id=1, phase='paused')
        self.send(sequence=3, request_id=2, phase='stepping')
        self.send(sequence=4, phase='paused', tick=10004, time_ns=10004000000)
        self.send(sequence=5, request_id=3, phase='resuming')
        self.send(sequence=6, phase='running', tick=10008, time_ns=10008000000)
        self.assertEqual(self.lease.check()['tick'], 10008)
        for field, value in (('version', True), ('phase', []), ('lease_seconds', 10),
                              ('issued_monotonic_s', float('nan')), ('time_ns', 0)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                bad = dict(self.value, sequence=7, **{field:value})
                self.lease.accept(json.dumps(bad))
        self.assertEqual(self.lease.check()['sequence'], 6)


@unittest.skipUnless(os.environ.get('WK_SCENE_ROS_TESTS') == '1', 'explicit isolated ROS environment')
class RealSceneNodeTests(unittest.TestCase):
    def test_scene_control_topics_construct_and_invalid_pause_never_grants_freshness(self):
        import rclpy
        from std_msgs.msg import String
        from prometheus_control.node import ControlNode
        from prometheus_control.scene import TOPIC
        rclpy.init(args=['--ros-args', '-p', 'flight_stack:=px4', '-p', 'run_id:=scene-node-test',
                        '-p', 'use_sim_time:=true', '-p', 'scene_epoch:='+'b'*32])
        node = None
        try:
            node = ControlNode()
            self.assertEqual(node.scene_ack.topic_name, TOPIC+'/control/uav1')
            with self.assertRaisesRegex(ValueError, 'native_state_writer'):
                node.scene_endpoints()
            node.on_scene(String(data=json.dumps(dict(version=1, run_id='scene-node-test',
                scene_epoch='b'*32, sequence=1, request_id=1, phase='paused', tick=10000,
                time_ns=10000000000, issued_monotonic_s=node.wall(), lease_seconds=.5))))
            self.assertIsNone(node.scene_hold)
            self.assertTrue(node.revoked)
            self.assertFalse(node.frozen_native_fresh('position', 0.))
        finally:
            if node is not None:
                node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
