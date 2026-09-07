"""Real generated ROS messages; recording transports, no FC commands in unit tests."""
from copy import deepcopy
import math
import unittest

from ardupilot_msgs.msg import Status, WksimState
from ardupilot_msgs.srv import ModeSwitch
from px4_msgs.msg import VehicleStatus, VehicleLocalPosition, VehicleAttitude, SensorGps, VehicleCommandAck, EstimatorStatusFlags
from prometheus_msgs.msg import UAVCommand as Cmd, UAVControlState as Control, UAVSetup
from rclpy.serialization import serialize_message, deserialize_message
from rclpy.task import Future
from prometheus_control.frames import ned_axes, ned_frd_quaternion, euler
from prometheus_control.native_arducopter import ArduCopterLink, home_offset
from prometheus_control.native_px4 import PX4Link
from prometheus_control.shaping import Setpoint


class Recorder:
    def __init__(self):
        self.messages = []
    def publish(self, message):
        self.messages.append(deepcopy(message))
    def get_subscription_count(self):
        return 1
    def service_is_ready(self):
        return True
    def call_async(self, message):
        self.publish(message)
        self.future = Future()
        return self.future
    def remove_pending_request(self, future):
        self.removed = future


class RecordingNode:
    def create_subscription(self, cls, topic, callback, qos):
        return callback
    def create_publisher(self, cls, topic, qos):
        return Recorder()
    def create_client(self, cls, topic):
        return Recorder()


def ap_sample():
    msg = WksimState(time_boot_us=1_000_000, filter_status_valid=True, filter_status=0x3F,
        ahrs_healthy=True, attitude_valid=True, position_valid=True, velocity_valid=True,
        home_valid=True, home_latitude_e7=401540302, home_longitude_e7=1162593683,
        home_altitude_cm=5000, gps_fix_type=3, gps_num_sats=10)
    msg.header.frame_id = 'map'
    msg.pose.orientation.w = 1.0
    msg.pose.position.z = 3.0
    return msg


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.ap = ArduCopterLink(RecordingNode(), position_yaw=True, clock=lambda: self.now)
        self.ap.receive('local', ap_sample())
        self.ap.receive('status', Status(vehicle_type=2, mode=4, armed=True, flying=True))
        self.px = PX4Link(RecordingNode(), '', 22, clock=lambda: self.now)
        self.px.receive('status', VehicleStatus(timestamp=1_000_000, system_id=22, vehicle_type=1, arming_state=2, nav_state=14))
        self.px.receive('position', VehicleLocalPosition(timestamp=1_000_000, timestamp_sample=999_000,
            xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True, heading_good_for_control=True, x=3., y=2., z=-3.))
        self.px.receive('attitude', VehicleAttitude(timestamp=1_000_000, q=[1., 0., 0., 0.]))
        self.px.receive('gps', SensorGps(timestamp=1_000_000, fix_type=3))
        self.px.receive('estimator', EstimatorStatusFlags(timestamp=1_000_000, cs_tilt_align=True, cs_yaw_align=True))

    def test_frames_and_quaternion_roundtrip(self):
        self.assertEqual(ned_axes((1., 2., 3.)), (2., 1., -3.))
        self.assertTrue(math.isnan(ned_axes((None, 2., 3.))[1]))
        for q in ((1., 0., 0., 0.), (.5, .5, .5, .5), (.9, .1, .2, .3)):
            actual = ned_frd_quaternion(ned_frd_quaternion(q))
            for a, b in zip(actual, q):
                self.assertAlmostEqual(a, b/math.hypot(*q))
        self.assertAlmostEqual(euler(ned_frd_quaternion((1., 0., 0., 0.)))[2], math.pi/2)
        with self.assertRaises(ValueError):
            ned_frd_quaternion((0., 0., 0., 0.))

    def test_ap_state_flags_and_wire_roundtrip(self):
        msg = ap_sample()
        self.assertEqual(deserialize_message(serialize_message(msg), WksimState), msg)
        self.assertTrue(self.ap.state(1).odom_valid)
        for index, field in enumerate(('filter_status_valid', 'ahrs_healthy', 'attitude_valid', 'position_valid', 'velocity_valid', 'home_valid'), 1):
            invalid = deepcopy(msg)
            invalid.time_boot_us += index
            setattr(invalid, field, False)
            self.ap.receive('local', invalid)
            self.assertFalse(self.ap.state(1).odom_valid, field)
        invalid.position_valid = False
        invalid.time_boot_us += 1
        self.ap.receive('local', invalid)
        self.assertTrue(math.isnan(self.ap.state(1).position[0]))
        self.now += 2.01
        self.assertFalse(self.ap.state(1).connected)
        self.assertIsNone(self.ap.flying)

    def test_ap_home_and_reset_epoch(self):
        msg = ap_sample()
        msg.time_boot_us += 1
        msg.home_latitude_e7 += 20
        self.ap.receive('local', msg)
        self.assertEqual((self.ap.generation, self.ap.reset_kind), (1, 'home'))
        msg = deepcopy(msg)
        msg.time_boot_us += 1
        msg.yaw_reset_ms = 99
        self.ap.receive('local', msg)
        self.assertEqual((self.ap.generation, self.ap.reset_kind), (2, 'yaw'))
        msg = deepcopy(msg)
        msg.time_boot_us -= 1
        self.ap.receive('local', msg)
        self.assertEqual((self.ap.generation, self.ap.reset_kind), (3, 'clock'))
        self.assertEqual(self.ap.consume_resets(), {'home', 'yaw', 'clock'})
        lat, lon, alt = home_offset(ap_sample(), (2., 3., 4.))
        self.assertAlmostEqual((lat*1e7-401540302)*.011131884502145034, 3., delta=.012)
        self.assertAlmostEqual((lon*1e7-1162593683)*.011131884502145034*math.cos(math.radians(40.154)), 2., delta=.012)
        self.assertEqual(alt, 4.)
        with self.assertRaises(ValueError):
            home_offset(ap_sample(), (101., 0., 0.))

    def test_ap_position_wire_and_explicit_capability(self):
        self.ap.send(Setpoint('local', position=(2., 3., 3.), yaw=-math.pi/2))
        msg = self.ap.position_pub.messages[-1]
        self.assertEqual((msg.type_mask, msg.coordinate_frame, msg.header.stamp.sec), (0x9F8, 6, 1))
        self.assertAlmostEqual(msg.yaw, -math.pi/2, places=6)
        self.assertIsNotNone(self.ap.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_VEL)))
        with self.assertRaises(ValueError):
            self.ap.send(Setpoint('local', position=(2., 3., 3.), velocity=(1., None, None), yaw=0.))
        self.ap.position_yaw = False
        with self.assertRaises(ValueError):
            self.ap.send(Setpoint('local', position=(2., 3., 3.), yaw=0.))
        self.assertEqual(len(self.ap.position_pub.messages), 1)

    def test_ap_velocity_wire_and_capability(self):
        self.assertIsNone(self.ap.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_VEL, yaw_rate_mode=True)))
        self.assertIsNone(self.ap.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_VEL_BODY, yaw_rate_mode=True)))
        self.assertEqual(self.ap.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_VEL)),
                         'arducopter_velocity_requires_yaw_rate_mode')
        self.assertEqual(self.ap.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XY_VEL_Z_POS, yaw_rate_mode=True)),
                         'arducopter_move_mode_not_implemented')
        self.ap.send(Setpoint('local', velocity=(1., .5, -.2), yaw_rate=.3))
        msg = self.ap.velocity_pub.messages[-1]
        self.assertEqual((msg.header.frame_id, msg.header.stamp.sec), ('map', 1))
        self.assertEqual((msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z), (1., .5, -.2))
        self.assertEqual(msg.twist.angular.z, .3)
        self.ap.send(Setpoint('local', velocity=(0., 0., 0.)))
        self.assertEqual(self.ap.velocity_pub.messages[-1].twist.angular.z, 0.)
        for bad in (Setpoint('local', velocity=(1., 0., 0.), yaw=0.),
                    Setpoint('local', position=(2., None, None), velocity=(1., 0., 0.), yaw_rate=0.),
                    Setpoint('local', velocity=(math.inf, 0., 0.), yaw_rate=0.),
                    Setpoint('local', velocity=(1., 0., 0.), yaw_rate=math.nan)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.ap.send(bad)
        self.assertEqual(len(self.ap.velocity_pub.messages), 2)
        self.assertEqual(len(self.ap.position_pub.messages), 0)

    def test_px_velocity_wire_and_capability(self):
        self.assertIsNone(self.px.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_VEL)))
        self.assertIsNone(self.px.supports(Cmd(agent_cmd=Cmd.MOVE, move_mode=Cmd.XYZ_VEL, yaw_rate_mode=True)))
        self.px.send(Setpoint('local', velocity=(1., 0., 0.), yaw_rate=.5))
        mode = self.px.publishers['offboard'].messages[-1]
        self.assertEqual((mode.position, mode.velocity, mode.acceleration), (False, True, False))
        msg = self.px.publishers['position'].messages[-1]
        self.assertEqual(list(msg.velocity), [0., 1., -0.])
        self.assertTrue(math.isnan(msg.yaw))
        self.assertEqual(msg.yawspeed, -.5)
        self.px.send(Setpoint('local', velocity=(0., 0., 0.), yaw=math.pi/2))
        msg = self.px.publishers['position'].messages[-1]
        self.assertAlmostEqual(msg.yaw, 0., places=6)

    def test_ap_service_ack_and_timeout(self):
        self.ap.request('mode', 'POSCTL')
        client, _ = self.ap.services['mode']
        client.future.set_result(ModeSwitch.Response(status=True, curr_mode=4))
        self.assertFalse(self.ap.poll_request()[0])  # Success flag with wrong mode is not success.
        self.ap.request('mode', 'POSCTL')
        client.future.set_result(ModeSwitch.Response(status=True, curr_mode=5))
        self.assertTrue(self.ap.poll_request()[0])
        self.ap.request('mode', 'POSCTL')
        self.now += 5.1
        self.assertEqual(self.ap.poll_request(), (False, 'native_ack_timeout'))
        self.assertTrue(client.future.cancelled())

    def test_px_state_identity_and_epoch(self):
        state = self.px.state(2)
        self.assertTrue(state.odom_valid)
        self.assertEqual(list(state.position), [2., 3., 3.])
        self.assertAlmostEqual(state.attitude[2], math.pi/2, places=6)
        pos = deepcopy(self.px.latest['position'])
        pos.timestamp += 1
        pos.timestamp_sample += 1
        pos.xy_reset_counter = 1
        self.px.receive('position', pos)
        self.assertEqual(self.px.generation, 1)
        self.now += 2.1
        self.assertFalse(self.px.state(2).connected)
        self.px.latest['status'].system_id = 23
        with self.assertRaises(ValueError):
            self.px.state(2)

    def test_px_native_axes_and_ack_correlation(self):
        self.px.send(Setpoint('local', position=(1., 2., None), velocity=(None, None, 3.), yaw=0.))
        msg = self.px.publishers['position'].messages[-1]
        self.assertEqual(list(msg.position[:2]), [2., 1.])
        self.assertTrue(math.isnan(msg.position[2]))
        self.assertEqual(msg.velocity[2], -3.)
        self.assertAlmostEqual(msg.yaw, math.pi/2, places=6)
        self.px.request('arm', True)
        ack = VehicleCommandAck(timestamp=1_000_000, command=400, target_system=244, target_component=191, result=0)
        self.px.receive('ack', ack)
        self.assertIsNone(self.px.poll_request())
        ack.target_system = 245
        self.px.receive('ack', ack)
        self.assertTrue(self.px.poll_request()[0])
        self.px.request('arm', True)
        ack.result = 5
        self.px.receive('ack', ack)
        self.now += 5.1
        self.assertEqual(self.px.poll_request(), (False, 'native_ack_timeout'))

    def test_px_ground_alignment_and_native_takeoff(self):
        pos = self.px.latest['position']
        pos.heading_good_for_control = False
        self.assertTrue(self.px.state(2).odom_valid)  # Initial yaw/tilt are valid.
        self.assertFalse(self.px.ready_external)  # Final in-flight alignment is a distinct gate.
        pos.xy_global = pos.z_global = True
        pos.ref_alt = 50.0
        self.px.request('takeoff', 3.0)
        msg = self.px.publishers['command'].messages[-1]
        self.assertEqual((msg.command, msg.param7), (22, 53.0))
        self.assertTrue(all(math.isnan(v) for v in (msg.param4, msg.param5, msg.param6)))

    def test_node_rejection_does_not_falsify_connection_or_resume(self):
        import os
        import rclpy
        from prometheus_control.node import ControlNode
        self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
        rclpy.init(args=['--ros-args', '-p', 'flight_stack:=px4', '-p', 'run_id:=native-node-regression'])
        node = ControlNode()
        try:
            node.native = self.px
            events = []
            node.event = lambda event, **fields: events.append((event, fields))
            node.tick()
            self.assertTrue(node.state.connected)
            self.assertTrue(node.processor.enter_control(Control.COMMAND_CONTROL).accepted)
            self.px.latest['status'].nav_state = 2
            node.tick()
            self.assertTrue(node.revoked)
            self.assertTrue(node.state.connected)
            self.assertEqual(node.processor.control_state, Control.INIT)
            self.px.latest['status'].nav_state = 14
            node.tick()
            self.assertEqual(node.processor.control_state, Control.INIT)
            node.revoked = False
            node.processor.enter_control(Control.COMMAND_CONTROL)
            node.processor.accept(Cmd(agent_cmd=Cmd.CURRENT_POS_HOVER, control_level=Cmd.ABSOLUTE_CONTROL))
            node.stop_pub = Recorder()
            command = Cmd(agent_cmd=Cmd.MOVE, command_id=1, move_mode=Cmd.XYZ_POS)
            command.header.stamp = node.get_clock().now().to_msg()
            node.on_command(command)
            self.assertTrue(node.stop_pub.messages[-1].data)
            self.assertEqual(events[-1][0], 'command_rejected')
            node.on_setup(UAVSetup(cmd=UAVSetup.ARMING, arming=True))
            self.assertEqual(events[-1][0], 'setup_rejected')
        finally:
            node.destroy_node()
            rclpy.shutdown()

    def test_native_takeoff_alignment_before_command_stream(self):
        import os
        import rclpy
        from prometheus_control.node import ControlNode
        self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
        rclpy.init(args=['--ros-args', '-p', 'flight_stack:=px4', '-p', 'run_id:=native-takeoff-regression'])
        node = ControlNode()
        try:
            node.native, node.wall = self.ap, lambda: self.now
            node.event = lambda *args, **kwargs: None
            node.tick()
            node.warmup_target = Setpoint('local', position=(0., 0., 3.), yaw=0.)
            node.operation = dict(stage='takeoff', deadline=self.now+25, ack=True)
            sample = deepcopy(self.ap.latest['local'])
            sample.time_boot_us += 1
            sample.yaw_reset_ms = 500
            self.ap.receive('local', sample)
            node.tick()
            self.assertFalse(node.revoked)
            self.assertEqual(node.processor.control_state, Control.INIT)
            self.assertEqual(len(self.ap.position_pub.messages), 0)
            self.now += .51
            node.tick()
            self.assertEqual(node.processor.control_state, Control.COMMAND_CONTROL)
            self.assertEqual(len(self.ap.position_pub.messages), 1)
            # An active session never silently absorbs another yaw reset.
            sample = deepcopy(sample)
            sample.time_boot_us += 1
            sample.yaw_reset_ms += 1
            self.ap.receive('local', sample)
            node.tick()
            self.assertTrue(node.revoked)
            self.assertEqual(len(self.ap.position_pub.messages), 1)
        finally:
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
