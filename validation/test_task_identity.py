"""Task identity/time checks; live mode uses only ROS nodes, never a flight stack.

Set WKSIM_TASK_IDENTITY_ROS=1 inside private net/ipc/mount and tmpfs /dev/shm,
with domain 79 and the original ROS/message overlays sourced, for live checks.
"""
import ast
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime.task import Task, grounded, valid_state


def state(uav_id=1):
    return NS(uav_id=uav_id, connected=True, odom_valid=True, armed=False,
              header=NS(frame_id='map', stamp=NS(sec=10, nanosec=0)),
              position=[0., 0., 0.], velocity=[0., 0., 0.], attitude=[0., 0., 0.])


def task(uav_id=1):
    t = Task.__new__(Task)
    t.uav_id, t.run_id, t.protocol = uav_id, 'run', 'session_v1'
    t.epoch, t.native_generation, t.error = None, None, None
    t.request_id, t.session_sequence = 0, 0
    t.retired_epochs, t.latest, t.received = set(), {}, {}
    t.last_stamp, t.active, t.started = None, False, 0.
    t.convert, t.log = lambda msg: {}, io.StringIO()
    t.phase = lambda label: None
    return t


def session(a=1, b=1, **fields):
    return NS(**dict(dict(version=1, run_id='run', control_epoch='e'*32,
        sequence=1, last_request_id=7, native_generation=3,
        published_monotonic_s=100., source_received_valid=True,
        source_received_monotonic_s=100., state=state(a), control=NS(uav_id=b)), **fields))


class IdentityTests(unittest.TestCase):
    def test_strict_parameters_and_helper_defaults(self):
        for value in (True, False, 1., '1', None):
            with self.assertRaises(TypeError):
                Task(None, None, None, 'arducopter', uav_id=value)
            with self.assertRaises(TypeError):
                valid_state(None, value)
        for value in (0, -1, 256):
            with self.assertRaises(ValueError):
                Task(None, None, None, 'arducopter', uav_id=value)
        for value in (1, 0, 'false', None):
            with self.assertRaises(TypeError):
                Task(None, None, None, 'arducopter', use_sim_time=value)
        self.assertTrue(grounded(state()))
        self.assertFalse(grounded(state(2)))
        for uid in (1, 2, 255):
            self.assertTrue(grounded(state(uid), uid))
            self.assertFalse(valid_state(state(True), uid))

    def test_nested_identity_cannot_bind_or_mutate_even_matching_epoch(self):
        with patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100):
            for uid in (1, 2):
                t = task(uid)
                other = 3-uid
                for a, b in ((other, uid), (uid, other), (other, other)):
                    t.receive_session(session(a, b, last_request_id=999))
                    self.assertEqual((t.epoch, t.request_id, t.session_sequence, t.native_generation,
                                      t.latest, t.received, t.error), (None, 0, 0, None, {}, {}, None))
                t.receive_session(session(uid, uid))
                before = (t.epoch, t.request_id, t.session_sequence, t.native_generation,
                          t.latest.copy(), t.received.copy(), t.last_stamp, t.advanced_at, t.error)
                for a, b in ((other, uid), (uid, other), (other, other)):
                    for epoch in ('e'*32, 'f'*32):
                        t.receive_session(session(a, b, sequence=99, last_request_id=999,
                                                  native_generation=99, control_epoch=epoch))
                t.receive('state', state(other))
                t.receive('control_state', NS(uav_id=other))
                t.receive('control_state', NS())
                self.assertEqual(before, (t.epoch, t.request_id, t.session_sequence, t.native_generation,
                    t.latest, t.received, t.last_stamp, t.advanced_at, t.error))
                self.assertTrue(t.fresh())
                self.assertTrue(all(row['topic'].startswith(f'/uav{uid}/prometheus/')
                                    for row in map(json.loads, t.log.getvalue().splitlines())))

    def test_existing_session_filters_remain(self):
        with patch('Simulator.wksim_runtime.task.time.monotonic', return_value=100):
            for fields in (dict(run_id='other'), dict(version=2), dict(sequence=0),
                           dict(control_epoch='bad'), dict(source_received_valid=False),
                           dict(published_monotonic_s=97.), dict(source_received_monotonic_s=101.)):
                t = task()
                t.receive_session(session(**fields))
                self.assertIsNone(t.epoch)
            t = task()
            t.receive_session(session())
            t.receive_session(session(last_request_id=999))
            self.assertEqual(t.request_id, 7)
            t.receive_session(session(control_epoch='f'*32, sequence=2))
            self.assertIn('epoch changed', t.error)

    def test_all_task_and_mission_helper_calls_supply_own_id(self):
        root = Path(__file__).resolve().parents[1] / 'Simulator/wksim_runtime'
        for name in ('task.py', 'mission_task.py'):
            tree = ast.parse((root / name).read_text(encoding='utf-8'))
            for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
                for call in (n for n in ast.walk(cls) if isinstance(n, ast.Call)):
                    if isinstance(call.func, ast.Name) and call.func.id in ('grounded', 'valid_state'):
                        if call.args and isinstance(call.args[0], ast.Constant):
                            continue  # Constructor parameter validation.
                        self.assertEqual(ast.unparse(call.args[1]), 'self.uav_id')

    def test_default_wait_wall_and_dwell_boot(self):
        t = task()
        t.latest['state'] = state()
        wall = [100.]
        def pump():
            wall[0] += 1
        t.pump = pump
        with patch('Simulator.wksim_runtime.task.time.monotonic', side_effect=lambda: wall[0]):
            with self.assertRaises(TimeoutError):
                t.wait('wall', lambda: False, 2)
            self.assertEqual(wall[0], 102.)
            with self.assertRaisesRegex(TimeoutError, 'boot clock dwell'):
                t.dwell('frozen boot', lambda: True, 2)
            def advance_boot():
                t.state.header.stamp.sec += 1
            t.pump = advance_boot
            t.dwell('boot advances without wall', lambda: True, 2)
            self.assertEqual(t.state.header.stamp.sec, 12)


@unittest.skipUnless(os.environ.get('WKSIM_TASK_IDENTITY_ROS') == '1', 'explicit isolated ROS mode')
class RealRosTests(unittest.TestCase):
    def test_real_nodes_clock_and_isolation(self):
        import rclpy
        from rosgraph_msgs.msg import Clock
        from wksim_msgs.msg import SessionState
        self.assertEqual(os.environ['ROS_DOMAIN_ID'], '79')
        for ns in ('net', 'ipc', 'mnt'):
            self.assertNotEqual(os.readlink('/proc/self/ns/'+ns), os.environ['TASK_HOST_'+ns.upper()])
        self.assertNotEqual(str(os.stat('/dev/shm').st_dev), os.environ['TASK_HOST_SHM'])
        rclpy.init()
        self.addCleanup(rclpy.shutdown)
        publisher = rclpy.create_node('task_identity_clock_probe')
        self.addCleanup(publisher.destroy_node)
        clock_pub = publisher.create_publisher(Clock, '/clock', 10)
        with tempfile.TemporaryDirectory() as folder:
            nodes = []
            try:
                for uid, sim in ((1, False), (2, True)):
                    directory = Path(folder) / str(uid)
                    directory.mkdir()
                    limit = time.monotonic()+20
                    def health():
                        if time.monotonic() > limit:
                            raise RuntimeError('parent wall bound')
                    options = {} if uid == 1 else dict(uav_id=uid, use_sim_time=sim,
                                                       protocol='session_v1', run_id='probe')
                    nodes.append(Task(directory, health, lambda label: None, 'arducopter', **options))
                default, simulated = nodes
                self.assertEqual(default.node.get_name(), 'wksim_position_task')
                self.assertNotEqual(default.node.get_name(), simulated.node.get_name())
                self.assertFalse(default.node.get_parameter('use_sim_time').value)
                self.assertTrue(simulated.node.get_parameter('use_sim_time').value)
                for t in nodes:
                    version = 'v2/' if t.protocol == 'session_v1' else ''
                    self.assertEqual(t.setup_pub.topic_name, t.topic_root+version+'setup')
                    self.assertEqual(t.command_pub.topic_name, t.topic_root+version+'command')
                session_pub = publisher.create_publisher(SessionState, simulated.topic_root+'v2/state', 10)
                end = time.monotonic()+3
                while session_pub.get_subscription_count() != 1:
                    self.assertLess(time.monotonic(), end)
                    rclpy.spin_once(simulated.node, timeout_sec=0.02)
                def emit(a, b, sequence):
                    msg = SessionState()
                    msg.version, msg.run_id, msg.control_epoch = 1, 'probe', 'e'*32
                    msg.sequence, msg.last_request_id, msg.native_generation = sequence, 777, 1
                    msg.published_monotonic_s = msg.source_received_monotonic_s = time.monotonic()
                    msg.source_received_valid = True
                    msg.state.uav_id, msg.control.uav_id = a, b
                    session_pub.publish(msg)
                    for _ in range(5):
                        rclpy.spin_once(simulated.node, timeout_sec=0.02)
                emit(1, 2, 99)
                emit(2, 1, 99)
                self.assertEqual((simulated.epoch, simulated.request_id, simulated.native_generation),
                                 (None, 0, None))
                emit(2, 2, 1)
                self.assertEqual((simulated.epoch, simulated.request_id), ('e'*32, 777))
                self.assertIsNone(default.epoch)
                def deliver(sec):
                    end = time.monotonic()+3
                    while simulated.node.get_clock().now().nanoseconds != sec*10**9:
                        if time.monotonic() >= end:
                            self.fail('clock delivery timeout')
                        msg = Clock()
                        msg.clock.sec = sec
                        clock_pub.publish(msg)
                        rclpy.spin_once(simulated.node, timeout_sec=0.02)
                deliver(10)
                self.assertEqual(simulated.task_time(), 10.)
                simulated.latest['state'] = state(2)
                simulated.received['state'] = simulated.advanced_at = time.monotonic()-3
                self.assertFalse(simulated.fresh())  # ROS time never exempts wall freshness.
                real_pump = simulated.pump
                ticks = iter((11, 12))
                def step():
                    deliver(next(ticks))
                    real_pump()
                simulated.pump = step
                with self.assertRaises(TimeoutError):
                    simulated.wait('ROS deadline', lambda: False, 2)
                ticks = iter((13, 14))
                simulated.dwell('ROS dwell with frozen boot', lambda: True, 2)
                self.assertEqual(simulated.task_time(), 14.)
                self.assertEqual(simulated.state.header.stamp.sec, 10)
                ticks = iter((30,))
                with self.assertRaisesRegex(TimeoutError, 'ROS clock dwell timeout'):
                    simulated.dwell('ROS dwell deadline', lambda: True, 100)
                simulated.pump = real_pump
                simulated.health = lambda: (_ for _ in ()).throw(RuntimeError('parent wall bound'))
                with self.assertRaisesRegex(RuntimeError, 'parent wall bound'):
                    simulated.wait('frozen ROS', lambda: False)
                deliver(0)
                with self.assertRaisesRegex(RuntimeError, 'ROS clock'):
                    simulated.task_time()
                deliver(40)
                with self.assertRaisesRegex(RuntimeError, 'ROS clock'):
                    simulated.task_time()  # No automatic recovery after reset.
            finally:
                for t in reversed(nodes):
                    t.close()


if __name__ == '__main__':
    unittest.main()
