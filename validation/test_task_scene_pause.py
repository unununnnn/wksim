"""Task pause contract checks; no flight controller or UE is launched."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from validation.test_task_identity import task, session
from Simulator.wksim_runtime.task import Task


class Lease:
    def __init__(self):
        self.status = dict(phase='running', sequence=1, tick=10000)
        self.value = self.status
        self.error = None

    def check(self):
        if self.error:
            raise ValueError(self.error)
        return self.status


def scene_task():
    t = task()
    t.scene_lease = Lease()
    t._scene_frozen_stamp, t._scene_phase = None, None
    t._session_received = 0.
    t.node = NS(get_clock=lambda: NS(now=lambda: NS(nanoseconds=10000000000)))
    t.receive_session(session())
    t.active = True
    return t


class ScenePauseTests(unittest.TestCase):
    @patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100.)
    def test_discovery_waits_without_binding_state_or_claiming_freshness(self, clock):
        t = scene_task()
        t.active = False
        t.scene_lease.value = None
        t.receive_session(session(sequence=2))
        self.assertFalse(t.fresh())
        self.assertIsNone(t.error)
        self.assertEqual(t.session_sequence, 1)
        t.active = True
        t.scene_lease.error = 'missing'
        self.assertFalse(t.fresh())
        self.assertIn('missing', t.error)

    @patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100.)
    def test_pause_keeps_raw_snapshot_and_requires_new_resume_sample(self, clock):
        t = scene_task()
        t.scene_lease.status.update(phase='paused', sequence=2)
        t.scene_status()
        clock.return_value = 104.
        t.receive_session(session(sequence=2, published_monotonic_s=104.))
        self.assertTrue(t.fresh())
        self.assertEqual(t.advanced_at, 100.)
        self.assertEqual(t.last_stamp, 10.)
        t.scene_lease.status.update(phase='running', sequence=3, tick=10004)
        t.receive_session(session(sequence=3, published_monotonic_s=104., source_received_monotonic_s=104.))
        self.assertEqual(t._scene_frozen_stamp, 10.)
        newer = session(sequence=4, published_monotonic_s=104., source_received_monotonic_s=104.)
        newer.state.header.stamp.nanosec = 4000000
        t.receive_session(newer)
        self.assertIsNone(t._scene_frozen_stamp)
        self.assertEqual(t.last_stamp, 10.004)

    @patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100.)
    def test_failures_remain_failures_during_pause(self, clock):
        for failure in ('disconnected', 'generation', 'backwards', 'boundary', 'expired', 'missing_publication'):
            clock.return_value = 100.
            t = scene_task()
            t.scene_lease.status.update(phase='paused', sequence=2)
            t.scene_status()
            clock.return_value = 104.
            msg = session(sequence=2, published_monotonic_s=104.)
            if failure == 'disconnected':
                msg.state.connected = False
            elif failure == 'generation':
                msg.native_generation += 1
            elif failure == 'backwards':
                msg.state.header.stamp.sec = 9
            elif failure == 'boundary':
                msg.state.header.stamp.sec = 11
            elif failure == 'expired':
                t.scene_lease.error = 'expired'
            if failure != 'missing_publication':
                t.receive_session(msg)
            self.assertTrue(t.error or not t.fresh(), failure)

    @patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100.)
    def test_pump_blocks_high_level_progress_but_runs_health(self, clock):
        t = scene_task()
        t.use_sim_time = False
        phases = iter(('paused', 'stepping', 'resuming', 'running'))
        health = []
        t.health = lambda: health.append(True)
        def spin(*args, **kwargs):
            phase = next(phases)
            t.scene_lease.status.update(phase=phase, sequence=t.scene_lease.status['sequence']+1, tick=10004)
            if phase == 'running':
                msg = session(sequence=2)
                msg.state.header.stamp.nanosec = 4000000
                t.receive_session(msg)
        t.ros = NS(spin_once=spin)
        t.pump()
        self.assertEqual(len(health), 4)


@unittest.skipUnless(os.environ.get('WK_TASK_SCENE_ROS_TESTS') == '1', 'explicit isolated ROS mode')
class RealRosPauseTests(unittest.TestCase):
    def test_public_session_and_lifecycle_pause_resume(self):
        import rclpy
        from std_msgs.msg import String
        from rosgraph_msgs.msg import Clock
        from wksim_msgs.msg import SessionState
        self.assertEqual(os.environ['ROS_DOMAIN_ID'], '81')
        for ns in ('net', 'ipc', 'mnt'):
            self.assertNotEqual(os.readlink('/proc/self/ns/'+ns), os.environ['TASK_HOST_'+ns.upper()])
        self.assertNotEqual(str(os.stat('/dev/shm').st_dev), os.environ['TASK_HOST_SHM'])
        rclpy.init()
        self.addCleanup(rclpy.shutdown)
        node = rclpy.create_node('task_scene_pause_probe')
        self.addCleanup(node.destroy_node)
        lifecycle = node.create_publisher(String, '/wksim/scene/lifecycle', 10)
        states = node.create_publisher(SessionState, '/uav1/prometheus/v2/state', 10)
        clocks = node.create_publisher(Clock, '/clock', 10)
        started = time.monotonic()
        sequence = 0
        phase, tick, source = 'running', 10000, started
        request_id = 1
        def publish():
            nonlocal sequence
            self.assertLess(time.monotonic()-started, 15)
            sequence += 1
            now = time.monotonic()
            lifecycle.publish(String(data=json.dumps(dict(version=1, run_id='probe', scene_epoch='a'*32,
                sequence=sequence, request_id=request_id,
                phase=phase, tick=tick, time_ns=tick*1000000, issued_monotonic_s=now, lease_seconds=0.5))))
            c = Clock()
            c.clock.sec, c.clock.nanosec = divmod(tick*1000000, 1000000000)
            clocks.publish(c)
            msg = SessionState()
            msg.version, msg.run_id, msg.control_epoch = 1, 'probe', 'e'*32
            msg.sequence, msg.native_generation = sequence, 3
            msg.published_monotonic_s, msg.source_received_monotonic_s = now, source
            msg.source_received_valid = True
            msg.state.uav_id = msg.control.uav_id = 1
            msg.state.connected = msg.state.odom_valid = True
            msg.state.header.frame_id = 'map'
            msg.state.header.stamp.sec, msg.state.header.stamp.nanosec = divmod(tick*1000000, 1000000000)
            states.publish(msg)
        with tempfile.TemporaryDirectory() as folder:
            t = Task(Path(folder), publish, lambda _: None, 'arducopter', run_id='probe',
                     protocol='session_v1', use_sim_time=True, scene_epoch='a'*32)
            try:
                while not t.fresh():
                    publish()
                    rclpy.spin_once(t.node, timeout_sec=0.02)
                t.active = True
                phase = 'paused'
                request_id = 2
                end = time.monotonic()+2.2
                while time.monotonic() < end:
                    publish()
                    rclpy.spin_once(t.node, timeout_sec=0.02)
                self.assertTrue(t.fresh())
                self.assertEqual(t.last_stamp, 10.)
                self.assertEqual(t.task_time(), 10.)
                phase = 'running'
                request_id = 3
                source = time.monotonic()
                for _ in range(10):
                    publish()
                    rclpy.spin_once(t.node, timeout_sec=0.02)
                self.assertEqual(t._scene_frozen_stamp, 10.)
                tick = 10004
                t.pump()
                self.assertIsNone(t._scene_frozen_stamp)
                self.assertEqual(t.epoch, 'e'*32)
                self.assertEqual(t.native_generation, 3)
                self.assertEqual(t.sent, [])
            finally:
                t.close()


if __name__ == '__main__':
    unittest.main()
