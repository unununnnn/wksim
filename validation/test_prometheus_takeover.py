"""Bounded public-envelope regressions; generated ROS, recording native links.

Run in private net/ipc/mount namespaces with fresh /dev/shm and /tmp, domain
79, installed message overlays and source prometheus_control on PYTHONPATH.
These tests exercise on_request/tick, not a real flight controller or flight
acceptance. No executor is spun and native publishers only record messages.
"""
from copy import deepcopy
import json
import math
import os
import unittest
from unittest.mock import patch
import uuid

import rclpy
from rclpy.serialization import deserialize_message, serialize_message
from prometheus_msgs.msg import UAVCommand as Cmd, UAVSetup, UAVControlState as Control
from wksim_msgs.msg import SetupRequest, CommandRequest
from px4_msgs.msg import (VehicleStatus, VehicleLocalPosition, VehicleAttitude,
                          SensorGps, EstimatorStatusFlags, VehicleLandDetected,
                          VehicleCommandAck)
from prometheus_control.frames import ned_frd_quaternion
from prometheus_control.native_px4 import PX4Link
from prometheus_control.native_arducopter import ArduCopterLink
from ardupilot_msgs.msg import Status
from ardupilot_msgs.srv import ModeSwitch
from prometheus_control.node import ControlNode
from validation.test_prometheus_native import Recorder, RecordingNode, ap_sample


class TakeoverTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('ROS_DOMAIN_ID'), '79')
        for kind in ('net', 'ipc', 'mnt'):
            self.assertNotEqual(os.readlink('/proc/self/ns/' + kind),
                                os.readlink('/proc/1/ns/' + kind))
        self.assertIn('WK_SESSION_HOST_SHM_DEV', os.environ)
        self.assertNotEqual(str(os.stat('/dev/shm').st_dev),
                            os.environ['WK_SESSION_HOST_SHM_DEV'])
        self.now, self.boot = 10., 1_000_000
        self.pose, self.yaw, self.mode, self.flying = (1., 2., 0.), .3, 2, False
        self.samples = {}
        self.native = PX4Link(RecordingNode(), '', 1, clock=lambda: self.now)
        rclpy.init(args=['--ros-args', '-p', 'flight_stack:=px4', '-p',
                         'run_id:=takeover-' + uuid.uuid4().hex])
        self.addCleanup(rclpy.shutdown)
        with patch('prometheus_control.native_px4.PX4Link', return_value=self.native):
            self.node = ControlNode()
        self.addCleanup(self.node.destroy_node)
        self.node.wall = lambda: self.now
        self.node.info_pub = Recorder()
        self.node.session_pub = Recorder()
        self.refresh()
        self.tick()

    def refresh(self, *, pose=None, yaw=None, mode=None, flying=None, **position):
        if pose is not None:
            self.pose = pose
        if yaw is not None:
            self.yaw = yaw
        if mode is not None:
            self.mode = mode
        if flying is not None:
            self.flying = flying
        self.boot += 100_000
        x, y, z = self.pose
        self.samples = dict(
            status=VehicleStatus(timestamp=self.boot, system_id=1, vehicle_type=1,
                                 arming_state=2, nav_state=self.mode),
            position=VehicleLocalPosition(timestamp=self.boot, timestamp_sample=self.boot,
                xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True,
                heading_good_for_control=True, xy_global=True, z_global=True,
                ref_alt=50., x=y, y=x, z=-z),
            attitude=VehicleAttitude(timestamp=self.boot, q=list(ned_frd_quaternion(
                (math.cos(self.yaw/2), 0., 0., math.sin(self.yaw/2))))),
            gps=SensorGps(timestamp=self.boot, fix_type=3),
            estimator=EstimatorStatusFlags(timestamp=self.boot, cs_tilt_align=True, cs_yaw_align=True),
            land=VehicleLandDetected(timestamp=self.boot, landed=not self.flying))
        for field, value in position.items():
            setattr(self.samples['position'], field, value)
        for key, msg in self.samples.items():
            self.native.receive(key, msg)

    def tick(self, elapsed=.05):
        self.now += elapsed
        self.node.tick()
        return self.node.session_pub.messages[-1]

    def request(self, number, kind='setup'):
        state = self.node.session_pub.messages[-1]
        cls = SetupRequest if kind == 'setup' else CommandRequest
        msg = cls(version=state.version, run_id=state.run_id,
                  control_epoch=state.control_epoch, request_id=number)
        nested = getattr(msg, kind)
        nested.header.stamp = self.node.get_clock().now().to_msg()
        if kind == 'setup':
            nested.cmd, nested.control_state = UAVSetup.SET_CONTROL_MODE, 'COMMAND_CONTROL'
        else:
            nested.agent_cmd, nested.move_mode, nested.command_id = Cmd.MOVE, Cmd.XYZ_POS, number
            nested.position_ref, nested.yaw_ref = [7., 8., 9.], -.4
        return msg

    def send(self, msg, kind='setup', event='setup_received'):
        start = len(self.node.info_pub.messages)
        self.node.on_request(kind, deserialize_message(serialize_message(msg), type(msg)))
        events = [json.loads(m.message) for m in self.node.info_pub.messages[start:]]
        self.assertTrue(any(e['event'] == event and e['request_id'] == msg.request_id
                            for e in events), events)
        return events

    @property
    def outputs(self):
        return self.native.publishers['position'].messages

    def assert_pose(self, outputs, pose, yaw):
        self.assertTrue(outputs)
        for msg in outputs:
            for actual, expected in zip(msg.position, (pose[1], pose[0], -pose[2])):
                self.assertAlmostEqual(actual, expected, places=5)
            self.assertAlmostEqual(math.remainder(msg.yaw - (math.pi/2-yaw), 2*math.pi), 0., places=5)

    def ack(self, result=0):
        command = self.native.publishers['command'].messages[-1]
        self.native.receive('ack', VehicleCommandAck(timestamp=self.boot, command=command.command,
            target_system=command.source_system, target_component=command.source_component, result=result))

    def finish_warmup(self):
        for _ in range(11):
            self.refresh()
            self.tick(.1)
        self.assertEqual(self.native.publishers['command'].messages[-1].command, 176)
        self.refresh(mode=14)
        self.ack()
        before = len(self.outputs)
        state = self.tick()
        self.assertEqual(state.control.control_state, Control.COMMAND_CONTROL)
        self.assertEqual(len(self.outputs), before+1)

    def airborne(self, number=1):
        self.refresh(pose=(12., -8., 6.), yaw=1.1, flying=True)
        self.tick()
        msg = self.request(number)
        self.send(msg)
        return msg

    def test_ground_native_takeoff_then_home_plus_three_yaw_zero(self):
        self.send(self.request(1))
        command = self.native.publishers['command'].messages[-1]
        self.assertEqual((command.command, command.param7), (22, 53.))
        self.ack()
        self.tick()
        self.assertEqual(self.outputs, [])
        self.refresh(pose=(1., 2., 3.), yaw=.8, flying=True, mode=17)
        self.tick()
        self.finish_warmup()
        self.refresh(pose=(4., 5., 4.), yaw=-.7)
        self.tick()
        self.assert_pose(self.outputs, (1., 2., 3.), 0.)

    def test_airborne_reference_survives_drift_and_new_command_supersedes(self):
        self.airborne()
        self.refresh(pose=(20., -10., 9.), yaw=-1.)
        self.tick()
        self.finish_warmup()
        for _ in range(3):
            self.refresh(pose=(21., -11., 10.), yaw=-.6)
            self.tick()
        self.assert_pose(self.outputs, (12., -8., 6.), 1.1)
        references = [json.loads(m.message) for m in self.node.info_pub.messages
                      if json.loads(m.message)['event'] == 'takeover_reference']
        self.assertEqual(len(references), 1)
        self.assertTrue(references[0]['airborne'])
        self.assertEqual(references[0]['position_enu_m'], [12., -8., 6.])
        before = len(self.outputs)
        self.send(self.request(2, 'command'), 'command', 'command_accepted')
        self.tick()
        self.assert_pose(self.outputs[before:], (7., 8., 9.), -.4)

    def test_mode_loss_replay_and_fresh_takeover_never_resume_old_move(self):
        setup = self.airborne()
        self.finish_warmup()
        move = self.request(2, 'command')
        self.send(move, 'command', 'command_accepted')
        self.tick()
        before = len(self.outputs)
        self.refresh(mode=2)
        self.assertTrue(self.tick().control.failsafe)
        self.refresh(mode=14, pose=(-4., 5., 8.), yaw=-.9)
        for _ in range(3):
            self.assertEqual(self.tick().control.control_state, Control.INIT)
        self.send(setup, event='setup_rejected')
        self.send(move, 'command', 'command_rejected')
        wrong = self.request(3)
        wrong.control_epoch = 'wrong-epoch'
        self.send(wrong, event='setup_rejected')
        stale = self.request(3)
        stale.setup.header.stamp.sec -= 10
        self.send(stale, event='setup_rejected')
        self.send(self.request(3), event='setup_rejected')
        self.tick()
        self.assertEqual(len(self.outputs), before)
        self.send(self.request(4))
        self.refresh(pose=(-9., 7., 11.), yaw=.5)
        self.finish_warmup()
        self.tick()
        self.assert_pose(self.outputs[before:], (-4., 5., 8.), -.9)

    def test_native_failsafe_during_transition_stops_outputs(self):
        self.transition_fault('failsafe')

    def test_stale_native_state_during_transition_stops_outputs(self):
        self.transition_fault('stale')

    def test_native_reset_during_transition_stops_outputs(self):
        self.transition_fault('reset')

    def test_rejected_native_ack_does_not_activate(self):
        self.transition_fault('ack')

    def test_px4_rejects_explicit_brake_without_native_request(self):
        self.refresh(flying=True, pose=(1., 2., 6.))
        self.tick()
        msg = self.request(1)
        msg.setup.cmd, msg.setup.px4_mode = UAVSetup.SET_PX4_MODE, 'BRAKE'
        self.send(msg, event='setup_rejected')
        self.tick()
        self.assertEqual(self.native.publishers['command'].messages, [])
        self.assertEqual(self.outputs, [])

    def transition_fault(self, fault):
        self.airborne()
        self.tick()
        if fault == 'ack':
            for _ in range(11):
                self.refresh()
                self.tick(.1)
            self.ack(result=2)
        elif fault == 'failsafe':
            msg = deepcopy(self.samples['status'])
            msg.timestamp += 1
            msg.failsafe = True
            self.native.receive('status', msg)
        elif fault == 'reset':
            self.refresh(xy_reset_counter=1)
        before = len(self.outputs)
        state = self.tick(2.1 if fault == 'stale' else .05)
        self.assertTrue(state.control.failsafe)
        self.assertEqual(state.control.control_state, Control.INIT)
        self.assertEqual(len(self.outputs), before)
        self.refresh(mode=14, **({'xy_reset_counter': 1} if fault == 'reset' else {}))
        for _ in range(3):
            self.assertEqual(self.tick().control.control_state, Control.INIT)
        self.assertEqual(len(self.outputs), before)
        completed = [json.loads(m.message) for m in self.node.info_pub.messages
                     if json.loads(m.message)['event'] == 'setup_completed']
        self.assertEqual(completed, [])


class ArduCopterBrakeTests(unittest.TestCase):
    tick = TakeoverTests.tick
    request = TakeoverTests.request
    send = TakeoverTests.send

    def setUp(self):
        self.assertEqual(os.environ.get('ROS_DOMAIN_ID'), '79')
        for kind in ('net', 'ipc', 'mnt'):
            self.assertNotEqual(os.readlink('/proc/self/ns/' + kind),
                                os.readlink('/proc/1/ns/' + kind))
        self.assertIn('WK_SESSION_HOST_SHM_DEV', os.environ)
        self.assertNotEqual(str(os.stat('/dev/shm').st_dev),
                            os.environ['WK_SESSION_HOST_SHM_DEV'])
        self.now, self.boot = 10., 1_000_000
        self.native = ArduCopterLink(RecordingNode(), position_yaw=True, clock=lambda: self.now)
        rclpy.init(args=['--ros-args', '-p', 'flight_stack:=arducopter', '-p',
                         'run_id:=brake-' + uuid.uuid4().hex])
        self.addCleanup(rclpy.shutdown)
        with patch('prometheus_control.native_arducopter.ArduCopterLink', return_value=self.native):
            self.node = ControlNode()
        self.addCleanup(self.node.destroy_node)
        self.node.wall = lambda: self.now
        self.node.info_pub, self.node.session_pub = Recorder(), Recorder()
        self.refresh()
        self.tick()

    def refresh(self, mode=4, valid=True):
        self.boot += 100_000
        local = ap_sample()
        local.time_boot_us = self.boot
        local.ahrs_healthy = valid
        status = Status(vehicle_type=2, mode=mode, armed=True, flying=True)
        status.header.stamp.sec = self.boot // 1_000_000
        status.header.stamp.nanosec = (self.boot % 1_000_000) * 1000
        self.native.receive('local', local)
        self.native.receive('status', status)

    def brake(self, number=1):
        msg = self.request(number)
        msg.setup.cmd, msg.setup.px4_mode = UAVSetup.SET_PX4_MODE, 'BRAKE'
        return msg

    def completions(self):
        return [event for message in self.node.info_pub.messages
                if (event := json.loads(message.message))['event'] == 'setup_completed']

    def test_brake_dispatches_17_and_requires_observed_mode_after_ack(self):
        self.send(self.brake())
        client, _ = self.native.services['mode']
        self.assertEqual([m.mode for m in client.messages], [17])
        self.tick()
        self.assertEqual(self.completions(), [])
        client.future.set_result(ModeSwitch.Response(status=True, curr_mode=17))
        self.assertEqual(self.tick().state.mode, 'GUIDED')
        self.assertEqual(self.completions(), [])  # Service success is not observed mode.
        self.refresh(mode=17)
        state = self.tick()
        self.assertEqual(state.state.mode, 'BRAKE')
        self.assertEqual(state.control.control_state, Control.INIT)
        completed = self.completions()
        self.assertEqual(len(completed), 1)
        self.assertEqual((completed[0]['request_id'], completed[0]['value'],
                          completed[0]['native_mode']), (1, 'BRAKE', 'BRAKE'))
        self.tick()
        self.assertEqual(len(self.completions()), 1)
        self.assertEqual(self.native.position_pub.messages, [])
        self.assertEqual(len(client.messages), 1)

    def test_airborne_invalid_state_rejects_brake_without_native_request(self):
        self.refresh(valid=False)
        self.assertFalse(self.tick().state.odom_valid)
        self.send(self.brake(), event='setup_rejected')
        self.tick()
        for client, _ in self.native.services.values():
            self.assertEqual(client.messages, [])
        self.assertEqual(self.native.position_pub.messages, [])
        self.assertEqual(self.completions(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
