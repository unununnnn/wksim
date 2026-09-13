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
        def test_mixed_body_capture_records_first_step_not_later_yaw(self):
            import json
            import rclpy
            from prometheus_control.node import ControlNode
            rclpy.init(args=['--ros-args', '-p', 'flight_stack:=px4', '-p', 'run_id:=mixed-body-capture'])
            node = ControlNode()
            events = []
            try:
                node.native, node.wall = self.px, lambda: self.now
                node.event = lambda name, **fields: events.append((name, fields))
                def heading(yaw, timestamp):
                    ned = math.pi/2-yaw
                    self.px.receive('attitude', VehicleAttitude(timestamp=timestamp,
                        q=[math.cos(ned/2), 0., 0., math.sin(ned/2)]))
                heading(.6, 1_010_000)
                node.tick()
                self.assertTrue(node.processor.enter_control(Control.COMMAND_CONTROL).accepted)
                def command(cid):
                    item = Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XY_VEL_Z_POS_BODY, command_id=cid,
                               position_ref=[0., 0., 1.], velocity_ref=[.8, .4, 0.], yaw_ref=.3)
                    item.header.stamp = node.get_clock().now().to_msg()
                    node.request_context = cid
                    node.on_command(item)
                    node.request_context = 0
                    node.tick()
                command(1)
                captured = [fields for name, fields in events if name == 'mixed_body_reference_captured']
                self.assertEqual(len(captured), 1)
                self.assertAlmostEqual(captured[0]['source_yaw'], .6, places=6)
                first_velocity = node.processor.body_reference.velocity
                self.now += .1
                heading(1.1, 1_110_000)
                node.tick()
                self.assertEqual(node.processor.body_reference.velocity, first_velocity)
                self.assertEqual(sum(name == 'mixed_body_reference_captured' for name, _ in events), 1)
                command(2)
                captured = [fields for name, fields in events if name == 'mixed_body_reference_captured']
                self.assertEqual(len(captured), 2)
                self.assertAlmostEqual(captured[1]['source_yaw'], 1.1, places=6)
                self.assertNotEqual(captured[1]['reference_velocity'], captured[0]['reference_velocity'])
                json.dumps(captured, allow_nan=False)
            finally:
                node.destroy_node()
                rclpy.shutdown()

        def mixed_candidate(self, pv_profile=''):
            candidate = ArduCopterLink(RecordingNode(), position_yaw=True, pv_profile=pv_profile,
                mixed_profile='xy_velocity_z_position_yaw_v1', clock=lambda: self.now)
            candidate.receive('local', deepcopy(self.ap.latest['local']))
            candidate.receive('status', deepcopy(self.ap.latest['status']))
            return candidate

        def test_ap_mixed_profile_is_explicit_and_yaw_angle_only(self):
            self.assertEqual(self.ap.mixed_profile, '')
            for profile, enabled in (('xy_velocity_z_position_yaw_v1', False),
                                     ('xy_velocity_z_position_yaw', True),
                                     ('XY_VELOCITY_Z_POSITION_YAW_V1', True), (True, True), (None, True)):
                with self.subTest(profile=profile, enabled=enabled), self.assertRaises(ValueError):
                    ArduCopterLink(RecordingNode(), position_yaw=enabled, mixed_profile=profile)
            candidate = self.mixed_candidate()
            for mode in (Cmd.XY_VEL_Z_POS, Cmd.XY_VEL_Z_POS_BODY):
                command = Cmd(agent_cmd=Cmd.MOVE, move_mode=mode)
                self.assertEqual(self.ap.supports(command), 'arducopter_move_mode_not_implemented')
                self.assertIsNone(candidate.supports(command))
                command.yaw_rate_mode = True
                self.assertEqual(candidate.supports(command), 'arducopter_mixed_requires_yaw_angle')
            for mode, reason in ((Cmd.TRAJECTORY, 'arducopter_move_mode_not_implemented'),
                                 (Cmd.XYZ_ATT, 'arducopter_move_mode_not_implemented'),
                                 (Cmd.XYZ_VEL, 'arducopter_velocity_requires_yaw_rate_mode')):
                self.assertEqual(candidate.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=mode)), reason)
            target = Setpoint('local', position=(None, None, 4.), velocity=(1., -.5, 0.), yaw=.5)
            with self.assertRaises(ValueError):
                self.ap.send(target)
            self.assertEqual(self.ap.position_pub.messages, [])
            self.assertEqual(self.ap.velocity_pub.messages, [])

        def test_ap_mixed_wire_has_no_xy_position_and_preserves_pv_p_v(self):
            from unittest.mock import patch
            self.ap.latest['local'].time_boot_us = 1_234_567
            candidate = self.mixed_candidate('full_xyz_pv_yaw_v1')
            pv = ArduCopterLink(RecordingNode(), position_yaw=True, pv_profile='full_xyz_pv_yaw_v1',
                               clock=lambda: self.now)
            pv.receive('local', deepcopy(self.ap.latest['local']))
            pv.receive('status', deepcopy(self.ap.latest['status']))
            for target in (Setpoint('local', position=(2., 3., 4.), yaw=.5),
                           Setpoint('local', velocity=(1., .5, -.25), yaw_rate=.3),
                           Setpoint('global', global_position=(40., 116., 3.), yaw=-.5),
                           Setpoint('local', position=(2., 3., 4.), velocity=(1., -.5, .25), yaw=.5)):
                candidate.send(target)
                pv.send(target)
            for output in ('position_pub', 'velocity_pub'):
                self.assertEqual(getattr(candidate, output).messages, getattr(pv, output).messages)
            target = Setpoint('local', position=(None, None, 4.), velocity=(1., -.5, -0.), yaw=-.75)
            with patch('prometheus_control.native_arducopter.home_offset', side_effect=AssertionError('XY fabrication')):
                candidate.send(target)
            msg = candidate.position_pub.messages[-1]
            self.assertEqual(deserialize_message(serialize_message(msg), GlobalPosition), msg)
            self.assertEqual((msg.type_mask, msg.coordinate_frame, msg.header.frame_id), (0x9E3, 6, 'map'))
            self.assertEqual((msg.header.stamp.sec, msg.header.stamp.nanosec), (1, 234_567_000))
            self.assertEqual((msg.altitude, msg.velocity.linear.x, msg.velocity.linear.y, msg.yaw),
                             (4., 1., -.5, -.75))
            self.assertEqual((msg.latitude, msg.longitude, msg.velocity.linear.z), (0., 0., 0.))
            self.assertEqual(msg.velocity.angular, GlobalPosition().velocity.angular)
            self.assertEqual(msg.acceleration_or_force, GlobalPosition().acceleration_or_force)
            self.assertEqual(len(candidate.velocity_pub.messages), 1)

        def test_ap_mixed_invalid_targets_never_publish(self):
            target = Setpoint('local', position=(None, None, 4.), velocity=(1., -.5, 0.), yaw=.5)
            changes = [dict(position=None), dict(position=(None, 4.)), dict(velocity=None),
                       dict(velocity=(1., 2., 0., 0.)), dict(acceleration=None), dict(acceleration=()),
                       dict(yaw=None), dict(yaw_rate=0.), dict(yaw_rate=math.nan),
                       dict(acceleration=(0., None, None)), dict(velocity=(1., 2., None)),
                       dict(velocity=(1., 2., 1e-300)), dict(position=(None, None, 100.01)),
                       dict(position=(None, None, -100.01))]
            for axis in (0, 1):
                for value in (0., math.nan, math.inf):
                    position = list(target.position)
                    position[axis] = value
                    changes.append(dict(position=tuple(position)))
                velocity = list(target.velocity)
                velocity[axis] = None
                changes.append(dict(velocity=tuple(velocity)))
            for value in (math.nan, math.inf, -math.inf, 1e40, 10**400):
                changes += [dict(position=(None, None, value)), dict(yaw=value)]
                for axis in range(3):
                    velocity = list(target.velocity)
                    velocity[axis] = value
                    changes.append(dict(velocity=tuple(velocity)))
            limit = math.sqrt(float.fromhex('0x1.fffffep+127') / 4.) / 100.
            from prometheus_control.shaping import float32
            invalid_speeds = [math.nextafter(limit, math.inf), -math.nextafter(limit, math.inf)]
            if float32(limit) > limit:
                invalid_speeds += [limit, -limit]  # DDS double passes, native float32 setter refuses.
            for value in invalid_speeds:
                changes += [dict(velocity=(value, 0., 0.)), dict(velocity=(0., value, 0.))]
            for pv_profile in ('', 'full_xyz_pv_yaw_v1'):
                candidate = self.mixed_candidate(pv_profile)
                candidate.send(target)
                before = deepcopy(candidate.position_pub.messages)
                for change in changes:
                    with self.subTest(pv=pv_profile, change=change), self.assertRaises(ValueError):
                        candidate.send(replace(target, **change))
                    self.assertEqual(candidate.position_pub.messages, before)
                    self.assertEqual(candidate.velocity_pub.messages, [])
                # High but representable numbers are codec tests, never flight targets.
                candidate.send(replace(target, velocity=(limit / 2., -limit / 2., 0.)))

        def test_ap_mixed_readiness_is_required(self):
            from unittest.mock import patch
            target = Setpoint('local', position=(None, None, 4.), velocity=(1., -.5, 0.), yaw=.5)
            for condition in ('stale', 'odom', 'subscriber', 'service', 'disabled'):
                candidate = self.mixed_candidate()
                if condition == 'stale':
                    candidate.received['local'] -= 2.01
                elif condition == 'odom':
                    candidate.latest['local'].home_valid = False
                elif condition == 'disabled':
                    candidate.position_yaw = False
                transport = candidate.position_pub if condition == 'subscriber' else candidate.services['arm'][0]
                method = 'get_subscription_count' if condition == 'subscriber' else 'service_is_ready'
                with self.subTest(condition=condition), patch.object(transport, method,
                        return_value=0 if condition in ('subscriber', 'service') else 1):
                    with self.assertRaises(ValueError):
                        candidate.send(target)
                self.assertEqual(candidate.position_pub.messages, [])
                self.assertEqual(candidate.velocity_pub.messages, [])

        def test_ap_mixed_body_once_capture_and_shaped_holds(self):
            from prometheus_control.command import CommandProcessor
            from prometheus_control.shaping import SetpointShaper
            from prometheus_control.frames import set_orientation
            candidate = self.mixed_candidate()
            processor, shaper = CommandProcessor(), SetpointShaper()
            state = self.ap.state(1)
            state.position = [12., 23., 3.]
            set_orientation(state, (math.sqrt(.5), 0., 0., math.sqrt(.5)))
            processor.update_state(state)
            self.assertTrue(processor.set_offset(10., 20.).accepted)
            self.assertTrue(processor.enter_control(Control.COMMAND_CONTROL).accepted)
            command = Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XY_VEL_Z_POS_BODY, command_id=1,
                          position_ref=[0., 0., 2.], velocity_ref=[1., 0., 0.], yaw_ref=.25)
            self.assertTrue(processor.accept(command).accepted)
            reference = processor.step()
            self.assertAlmostEqual(reference.velocity[0], 0., places=6)
            self.assertAlmostEqual(reference.velocity[1], 1., places=6)
            target = shaper.shape(reference, processor.local_position())
            self.assertEqual(target.position, (None, None, 5.))
            candidate.send(target)
            state.position = [12.2, 24., 4.]
            set_orientation(state, (1., 0., 0., 0.))
            processor.update_state(state)
            self.assertEqual(processor.step(), reference)
            target = shaper.shape(processor.step(), processor.local_position())
            self.assertAlmostEqual(target.velocity[0], -.2 * shaper.hold_gain, places=6)
            self.assertAlmostEqual(target.velocity[1], 1.)
            candidate.send(target)
            self.assertEqual(candidate.position_pub.messages[-1].type_mask, 0x9E3)
            command = Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XY_VEL_Z_POS, command_id=2,
                          position_ref=[0., 0., 5.], velocity_ref=[0., 0., 0.], yaw_ref=.25)
            self.assertTrue(processor.accept(command).accepted)
            hold = shaper.shape(processor.step(), processor.local_position())
            self.assertEqual(hold.velocity, (None, None, None))
            self.assertAlmostEqual(hold.position[0], 2.)
            self.assertAlmostEqual(hold.position[1], 4.)
            candidate.send(hold)
            self.assertEqual(candidate.position_pub.messages[-1].type_mask, 0x9F8)

        def test_ap_mixed_node_parameter_and_preaccept_rejection(self):
            from unittest.mock import patch
            import rclpy
            from rclpy.parameter import Parameter
            from prometheus_control.node import ControlNode
            self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
            for profile in ('', 'xy_velocity_z_position_yaw_v1'):
                args = ['--ros-args', '-p', 'flight_stack:=arducopter', '-p', 'arducopter_position_yaw:=true',
                        '-p', 'run_id:=mixed-node-regression']
                if profile:
                    args += ['-p', 'arducopter_mixed_profile:=' + profile]
                rclpy.init(args=args)
                node = ControlNode()
                try:
                    self.assertEqual(node.native.mixed_profile, profile)
                    self.assertTrue(node.describe_parameter('arducopter_mixed_profile').read_only)
                    result = node.set_parameters([Parameter('arducopter_mixed_profile', value='invalid')])[0]
                    self.assertFalse(result.successful)
                    self.assertEqual(node.native.mixed_profile, profile)
                    rejected = [(Cmd.XY_VEL_Z_POS, True), (Cmd.XY_VEL_Z_POS_BODY, True),
                                (Cmd.TRAJECTORY, False), (Cmd.XYZ_VEL, False), (Cmd.XYZ_ATT, False)]
                    if not profile:
                        rejected += [(Cmd.XY_VEL_Z_POS, False), (Cmd.XY_VEL_Z_POS_BODY, False)]
                    for mode, rate in rejected:
                        command = Cmd(agent_cmd=Cmd.MOVE, move_mode=mode, yaw_rate_mode=rate, command_id=1)
                        before = deepcopy(node.processor.command)
                        with patch.object(node, 'input_stamp', return_value=1), patch.object(node.processor, 'accept') as accept:
                            node.on_command(command)
                            accept.assert_not_called()
                        self.assertEqual(node.processor.command, before)
                        self.assertEqual((node.last_move_id, node.last_command_stamp), (0, 0))
                finally:
                    node.destroy_node()
                    rclpy.shutdown()

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

    return unittest.TestSuite(CandidateTests(name) for name in CandidateTests.__dict__ if name.startswith('test_'))


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
