"""Check analytic trajectory derivatives without claiming a real flight."""
import math
import os
import json
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tools.pv_trajectory_task import reference, DURATION, PVTask


class PVReferenceTests(unittest.TestCase):
    def test_waypoint_settles_before_original_two_second_dwell(self):
        class BeforeTrajectory(Exception):
            pass

        class Setup:
            SET_PX4_MODE, ARMING, SET_CONTROL_MODE = range(3)

            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        task = PVTask.__new__(PVTask)
        state = SimpleNamespace(position=[2., 3., 3.], velocity=[.49, 0., 0.],
                                attitude=[0., 0., 0.], armed=True)
        task.latest = {'state': state}
        task.flight_stack, task.uav_id = 'arducopter', 1
        task.Setup = Setup
        task.Cmd = SimpleNamespace(MOVE=4, XYZ_POS=0)
        task.send = task.offer = lambda *args, **kwargs: None
        fresh = [True]
        task.fresh = lambda: fresh[0]
        observed = []

        def wait(label, predicate, *args):
            if label != 'waypoint_reached':
                return
            self.assertFalse(predicate())  # native .49 cannot open the raw .5 window
            state.velocity[0] = .4
            fresh[0] = False
            self.assertFalse(predicate())
            fresh[0] = True
            self.assertTrue(predicate())
            observed.append(label)

        def dwell(label, predicate, seconds):
            if label != 'waypoint_completed':
                return
            self.assertEqual(observed, ['waypoint_reached'])
            self.assertEqual(seconds, 2)
            state.velocity[0] = .49
            self.assertTrue(predicate())  # original dwell limit remains .5
            state.velocity[0] = .5001
            self.assertFalse(predicate())
            observed.append(label)
            raise BeforeTrajectory()

        task.wait, task.dwell = wait, dwell
        with patch('tools.pv_trajectory_task.grounded', return_value=True):
            with self.assertRaises(BeforeTrajectory):
                task.execute()
        self.assertEqual(observed, ['waypoint_reached', 'waypoint_completed'])

    @unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS') == '1', 'requires generated ROS messages')
    def test_new_origin_serializes_real_generated_float32_position(self):
        from prometheus_msgs.msg import UAVState
        class BeforeFlight(Exception):
            pass
        def stop_before_offer(*args):
            raise BeforeFlight()
        with tempfile.TemporaryDirectory() as directory:
            task = PVTask.__new__(PVTask)
            task.directory = Path(directory)
            task.latest = {'state': UAVState(position=[3.5, 4., 3.4], attitude=[0., 0., .6])}
            self.assertEqual(type(task.state.position[0]).__name__, 'float32')
            task.uav_id, task.run_id, task.scene_epoch, task.epoch = 1, 'pv-test-origin', 'a'*32, 'b'*32
            task.wait = stop_before_offer
            with self.assertRaises(BeforeFlight):
                task.fly_leg(2)
            ready = json.loads((task.directory/'pv-ready-2.json').read_text())
            self.assertEqual(ready['position'], [float(v) for v in task.state.position])
            self.assertEqual(ready['yaw'], float(task.state.attitude[2]))

    @unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS') == '1', 'requires isolated ROS graph')
    def test_exact_controller_and_passive_recorder_graph(self):
        import rclpy
        from wksim_msgs.msg import SetupRequest, CommandRequest
        self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
        rclpy.init(args=[])
        nodes = []
        try:
            node = rclpy.create_node('pv_graph_test_task'); nodes.append(node)
            task = PVTask.__new__(PVTask)
            task.node, task.flight_stack, task.uav_id = node, 'arducopter', 1
            task.setup_pub = node.create_publisher(SetupRequest, task.topic_root+'v2/setup', 1)
            task.command_pub = node.create_publisher(CommandRequest, task.topic_root+'v2/command', 1)
            def subscriber(name):
                item = rclpy.create_node(name); nodes.append(item)
                item.create_subscription(SetupRequest, task.topic_root+'v2/setup', lambda m: None, 1)
                item.create_subscription(CommandRequest, task.topic_root+'v2/command', lambda m: None, 1)
            def await_count(count):
                deadline = time.monotonic()+5
                while time.monotonic() < deadline:
                    rclpy.spin_once(node, timeout_sec=.02)
                    if task.setup_pub.get_subscription_count() == task.command_pub.get_subscription_count() == count:
                        return
                self.fail('Graph did not reach expected native matching count')
            subscriber('wksim_joint_arducopter_control')
            await_count(1)
            self.assertFalse(task.request_graph_ready())
            subscriber('unapproved_recorder')
            await_count(2)
            self.assertFalse(task.request_graph_ready())
            nodes.pop().destroy_node()
            await_count(1)
            subscriber('wksim_joint_flight_clock')
            await_count(2)
            self.assertTrue(task.request_graph_ready())
            self.assertEqual(set(task.pv_request_graph), {'setup', 'command'})
            subscriber('extra_control')
            await_count(3)
            self.assertFalse(task.request_graph_ready())
        finally:
            for node in reversed(nodes):
                node.destroy_node()
            rclpy.shutdown()

    def test_smooth_endpoints_and_interior_derivatives(self):
        origin, yaw = (2., 3., 3.), .2
        for leg, delta in ((1, (1.5, 1., .4, .6)), (2, (-1., .5, -.2, -.3))):
            p, v, a, heading = reference(0, origin, yaw, leg)
            self.assertEqual((p, v, a, heading), (origin, (0.,)*3, (0.,)*3, yaw))
            p, v, a, heading = reference(DURATION, origin, yaw, leg)
            self.assertEqual(p, tuple(x+d for x, d in zip(origin, delta)))
            self.assertEqual((v, a), ((0.,)*3, (0.,)*3))
            self.assertAlmostEqual(heading, yaw+delta[3])
            for t in (1., 4., 6., 10.):
                h = 1e-4
                lo, now, hi = (reference(u, origin, yaw, leg) for u in (t-h, t, t+h))
                for axis in range(3):
                    self.assertAlmostEqual((hi[0][axis]-lo[0][axis])/(2*h), now[1][axis], places=7)
                    self.assertAlmostEqual((hi[1][axis]-lo[1][axis])/(2*h), now[2][axis], places=7)
                self.assertTrue(all(math.isfinite(x) for x in (*now[0], *now[1], *now[2], now[3])))
        with self.assertRaises(ValueError):
            reference(math.nan, origin, yaw, 1)
        with self.assertRaises(ValueError):
            reference(1., origin, yaw, 3)

    def test_selector_mixing_rejected_before_runtime(self):
        root = Path(__file__).resolve().parents[1]
        base = [sys.executable, '-B', str(root/'tools/run_joint_flight.py'), 'run',
                '--control-manifest', 'unopened-build.json', '--control-sha256', 'a'*64]
        pv = ['--task-profile', 'full_xyz_pv_yaw_v1', '--ap-pv-manifest', 'unopened-pv.json',
              '--ap-pv-sha256', 'b'*64, '--message-manifest', 'unopened-message.json',
              '--message-sha256', 'c'*64]
        for extra in ([], ['--ap-pv-manifest', 'unopened-pv.json'],
                      pv+['--ap-manifest', 'old.json'], pv+['--scene-lifecycle'], pv+['--px4-manifest', 'other.json']):
            with self.subTest(extra=extra):
                result = subprocess.run(base+extra, cwd=root, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertIn('error:', result.stderr)
                self.assertNotIn('archive', result.stdout)


if __name__ == '__main__':
    unittest.main()
