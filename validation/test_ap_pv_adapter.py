"""Candidate adapter tests in a fresh process; installed baseline tests stay independent."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

REPO = Path(__file__).resolve().parents[1]


def candidate_suite():
    from copy import deepcopy
    from dataclasses import replace
    import math
    import unittest

    from ardupilot_msgs.msg import GlobalPosition, Status, WksimState
    from ardupilot_msgs.srv import ModeSwitch
    from px4_msgs.msg import VehicleStatus, VehicleLocalPosition, VehicleAttitude, SensorGps, VehicleCommandAck, EstimatorStatusFlags
    from prometheus_msgs.msg import UAVCommand as Cmd, UAVControlState as Control, UAVSetup
    from rclpy.serialization import serialize_message, deserialize_message
    from rclpy.task import Future
    from prometheus_control.frames import ned_axes, ned_frd_quaternion, euler
    from prometheus_control.native_arducopter import ArduCopterLink, home_offset
    from prometheus_control.native_px4 import PX4Link
    from prometheus_control.shaping import Setpoint

    from validation import test_prometheus_native as fixtures
    RecordingNode, ap_sample = fixtures.RecordingNode, fixtures.ap_sample
    import prometheus_control
    expected = REPO/'ros2/src/prometheus_control/prometheus_control'
    if Path(prometheus_control.__file__).resolve().parent != expected.resolve():
        raise RuntimeError('P+V unit tests did not import the explicit current source')

    class CandidateTests(fixtures.NativeTests):
        def test_ap_pv_profile_is_explicit_and_yaw_angle_only(self):
            command = Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.TRAJECTORY)
            self.assertEqual(self.ap.pv_profile, '')
            self.assertEqual(self.ap.supports(command), 'arducopter_move_mode_not_implemented')
            with self.assertRaises(ValueError):
                self.ap.send(Setpoint('local', position=(2., 3., 4.), velocity=(1., 0., 0.), yaw=0.))
            self.assertEqual(self.ap.position_pub.messages, [])
            self.assertEqual(self.ap.velocity_pub.messages, [])
            for profile, enabled in (('full_xyz_pv_yaw_v1', False), ('full_xyz_pv_yaw', True),
                                     ('FULL_XYZ_PV_YAW_V1', True), (True, True), (None, True)):
                with self.subTest(profile=profile, enabled=enabled), self.assertRaises(ValueError):
                    ArduCopterLink(RecordingNode(), position_yaw=enabled, pv_profile=profile)
            candidate = ArduCopterLink(RecordingNode(), position_yaw=True, pv_profile='full_xyz_pv_yaw_v1')
            self.assertIsNone(candidate.supports(command))
            command.yaw_rate_mode = True
            self.assertEqual(candidate.supports(command), 'arducopter_trajectory_requires_yaw_angle')
            for mode in (Cmd.XY_VEL_Z_POS, Cmd.XY_VEL_Z_POS_BODY, Cmd.XYZ_ATT):
                command.move_mode = mode
                self.assertEqual(candidate.supports(command), 'arducopter_move_mode_not_implemented')

        def test_ap_pv_native_wire_and_original_p_v_outputs(self):
            candidate = ArduCopterLink(RecordingNode(), position_yaw=True, pv_profile='full_xyz_pv_yaw_v1',
                                      clock=lambda: self.now)
            sample = ap_sample()
            sample.time_boot_us = 1_234_567
            candidate.receive('local', sample)
            candidate.receive('status', deepcopy(self.ap.latest['status']))
            self.ap.latest['local'] = deepcopy(sample)
            # Opting in must preserve the old pure P and pure V native messages.
            for target in (Setpoint('local', position=(2., 3., 4.), yaw=.5),
                           Setpoint('local', velocity=(1., .5, -.25), yaw_rate=.3),
                           Setpoint('global', global_position=(40., 116., 3.), yaw=-.5)):
                candidate.send(target)
                self.ap.send(target)
            for output in ('position_pub', 'velocity_pub'):
                self.assertEqual(getattr(candidate, output).messages, getattr(self.ap, output).messages)
            target = Setpoint('local', position=(2., 3., 4.), velocity=(1., -.5, .25), yaw=-.75)
            candidate.send(target)
            msg = candidate.position_pub.messages[-1]
            self.assertEqual(deserialize_message(serialize_message(msg), GlobalPosition), msg)
            self.assertEqual((msg.type_mask, msg.coordinate_frame, msg.header.frame_id), (0x9C0, 6, 'map'))
            self.assertEqual((msg.header.stamp.sec, msg.header.stamp.nanosec), (1, 234_567_000))
            lat, lon, alt = home_offset(sample, target.position)
            self.assertEqual((msg.latitude, msg.longitude, msg.altitude), (lat, lon, alt))
            self.assertEqual((msg.velocity.linear.x, msg.velocity.linear.y, msg.velocity.linear.z), target.velocity)
            self.assertEqual(msg.yaw, target.yaw)
            self.assertEqual(len(candidate.velocity_pub.messages), 1)

        def test_ap_pv_invalid_targets_never_publish(self):
            candidate = ArduCopterLink(RecordingNode(), position_yaw=True, pv_profile='full_xyz_pv_yaw_v1',
                                      clock=lambda: self.now)
            candidate.receive('local', ap_sample())
            candidate.receive('status', deepcopy(self.ap.latest['status']))
            target = Setpoint('local', position=(2., 3., 4.), velocity=(1., -.5, .25), yaw=.5)
            candidate.send(target)
            position_before = deepcopy(candidate.position_pub.messages)
            changes = [dict(position=None), dict(position=(1., 2.)), dict(velocity=None),
                       dict(velocity=(1., 2., 3., 4.)), dict(acceleration=None), dict(acceleration=()),
                       dict(yaw=None), dict(yaw=math.nan), dict(yaw=1e40), dict(yaw_rate=0.),
                       dict(yaw_rate=math.nan), dict(acceleration=(0., 0., 0.))]
            for field in ('position', 'velocity', 'acceleration'):
                for axis in range(3):
                    for value in (None, math.nan, math.inf, 1e40, 10**400):
                        if field == 'acceleration' and value is None:
                            continue
                        values = list(getattr(target, field))
                        values[axis] = value
                        changes.append({field: tuple(values)})
            for axis in range(3):
                values = list(target.position)
                values[axis] = 100.01
                changes.append(dict(position=tuple(values)))
            for change in changes:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    candidate.send(replace(target, **change))
                self.assertEqual(candidate.position_pub.messages, position_before)
                self.assertEqual(candidate.velocity_pub.messages, [])

        def test_ap_pv_preserves_readiness_checks(self):
            from unittest.mock import patch
            target = Setpoint('local', position=(2., 3., 4.), velocity=(1., -.5, .25), yaw=.5)
            for condition in ('stale', 'odom', 'subscriber', 'service', 'disabled'):
                with self.subTest(condition=condition):
                    candidate = ArduCopterLink(RecordingNode(), position_yaw=True, pv_profile='full_xyz_pv_yaw_v1',
                                              clock=lambda: self.now)
                    candidate.receive('local', ap_sample())
                    candidate.receive('status', deepcopy(self.ap.latest['status']))
                    if condition == 'stale':
                        candidate.received['local'] -= 2.01
                    elif condition == 'odom':
                        candidate.latest['local'].home_valid = False
                    elif condition == 'disabled':
                        candidate.position_yaw = False
                    transport = candidate.position_pub if condition == 'subscriber' else candidate.services['arm'][0]
                    method = 'get_subscription_count' if condition == 'subscriber' else 'service_is_ready'
                    with patch.object(transport, method, return_value=0 if condition in ('subscriber', 'service') else 1):
                        with self.assertRaises(ValueError):
                            candidate.send(target)
                    self.assertEqual(candidate.position_pub.messages, [])
                    self.assertEqual(candidate.velocity_pub.messages, [])

        def test_ap_pv_node_parameter_is_default_off_and_read_only(self):
            import os
            import rclpy
            from rclpy.parameter import Parameter
            from prometheus_control.node import ControlNode
            self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
            for profile in ('', 'full_xyz_pv_yaw_v1'):
                args = ['--ros-args', '-p', 'flight_stack:=arducopter', '-p', 'arducopter_position_yaw:=true',
                        '-p', 'run_id:=pv-node-regression']
                if profile:
                    args += ['-p', 'arducopter_pv_profile:=' + profile]
                rclpy.init(args=args)
                node = ControlNode()
                try:
                    self.assertEqual(node.native.pv_profile, profile)
                    self.assertTrue(node.describe_parameter('arducopter_pv_profile').read_only)
                    result = node.set_parameters([Parameter('arducopter_pv_profile', value='invalid')])[0]
                    self.assertFalse(result.successful)
                    self.assertEqual(node.native.pv_profile, profile)
                finally:
                    node.destroy_node()
                    rclpy.shutdown()

    return unittest.TestSuite(CandidateTests(name) for name in ['test_ap_pv_profile_is_explicit_and_yaw_angle_only', 'test_ap_pv_native_wire_and_original_p_v_outputs', 'test_ap_pv_invalid_targets_never_publish', 'test_ap_pv_preserves_readiness_checks', 'test_ap_pv_node_parameter_is_default_off_and_read_only'])


class CandidateSourceTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS') == '1', 'requires isolated ROS test wrapper')
    def test_pv_source_adapter_boundaries(self):
        self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
        env = dict(os.environ)
        env['PYTHONPATH'] = str(REPO/'ros2/src/prometheus_control')+os.pathsep+str(REPO)+os.pathsep+env.get('PYTHONPATH','')
        result = subprocess.run([sys.executable, '-B', '-m', 'validation.test_ap_pv_adapter', '--child'],
                                cwd=REPO, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__':
    if sys.argv[1:] != ['--child'] or os.environ.get('WKSIM_TEST_PRIVATE_ROS') != '1':
        raise SystemExit('Use tools/check-session-product.sh for isolated candidate tests')
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(candidate_suite()).wasSuccessful() else 1)
