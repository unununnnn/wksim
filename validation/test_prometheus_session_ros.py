"""#14 boundary regression: generated CDR + real rclpy/RMW ControlNode I/O.

Run with domain 79 inside unshare --net --ipc --mount, loopback up and a
new tmpfs on /dev/shm. Source DDS, AP and candidate ROS overlays first.
Envelope tests use RecordingNode native transports. The delayed AP service
test uses a local RMW ModeSwitch server (no FC, agent or physics).
Recreation here is node destruction/reconstruction in one Python process;
the real flight-stack/process restart harness is a separate validation.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import uuid

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.task import Future
from rclpy.serialization import deserialize_message, serialize_message
from rclpy.utilities import get_rmw_implementation_identifier
from prometheus_msgs.msg import UAVCommand as Cmd, UAVSetup, TextInfo, UAVControlState as Control
from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState
from prometheus_control.node import ControlNode
from prometheus_control.native_px4 import PX4Link
from prometheus_control.native_arducopter import ArduCopterLink
# Direct script execution adds validation/, whereas unittest adds the repo.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validation.test_prometheus_native import RecordingNode, ap_sample
from ardupilot_msgs.msg import Status
from ardupilot_msgs.srv import ModeSwitch
from px4_msgs.msg import (VehicleStatus, VehicleLocalPosition, VehicleAttitude,
                          SensorGps, EstimatorStatusFlags, VehicleLandDetected)


def require_isolation():
    if os.environ.get('ROS_DOMAIN_ID') != '79':
        raise RuntimeError('This test requires ROS_DOMAIN_ID=79')
    for kind in ('net', 'ipc', 'mnt'):
        if os.readlink('/proc/self/ns/' + kind) == os.readlink('/proc/1/ns/' + kind):
            raise RuntimeError('Private namespace required: ' + kind)
    # The launcher supplies the original device number before mounting tmpfs.
    if str(os.stat('/dev/shm').st_dev) == os.environ.get('WK_SESSION_HOST_SHM_DEV', ''):
        raise RuntimeError('A fresh /dev/shm mount is required')
    if 'WK_SESSION_HOST_SHM_DEV' not in os.environ:
        raise RuntimeError('Launcher must record WK_SESSION_HOST_SHM_DEV')


class WireTests(unittest.TestCase):
    def test_three_generated_cdr_types(self):
        for cls in (CommandRequest, SetupRequest, SessionState):
            with self.subTest(message=cls.__name__):
                msg = cls(version=1, run_id='cdr-run', control_epoch='e' * 32)
                if cls is SessionState:
                    msg.sequence = 23
                    msg.last_request_id = 2**63 + 7
                    msg.command_high_water = 2**32 - 1
                    msg.native_generation = 3
                    msg.source_clock = 'fc_boot'
                    msg.source_received_valid = True
                    msg.source_received_monotonic_s = 123.25
                    msg.published_monotonic_s = 124.5
                    msg.state.header.stamp.sec = 7
                    msg.state.header.stamp.nanosec = 987000
                    msg.control.control_state = Control.INIT
                else:
                    msg.request_id = 2**63 + 7
                    nested = msg.command if cls is CommandRequest else msg.setup
                    nested.header.stamp.sec = 13
                    if cls is CommandRequest:
                        nested.command_id = 31
                        nested.position_ref = [1., 2., 3.]
                    else:
                        nested.cmd, nested.arming = UAVSetup.ARMING, True
                wire = serialize_message(msg)
                self.assertGreater(len(wire), 64)
                self.assertEqual(deserialize_message(wire, cls), msg)


class SessionBoundary:
    """Public ingress/egress is RMW; only native transport is a recorder."""
    def setUp(self):
        require_isolation()
        self.run_id = 'session-ros-' + uuid.uuid4().hex
        rclpy.init(args=['--ros-args', '-p', 'flight_stack:=' + self.stack,
                         '-p', 'run_id:=' + self.run_id])
        self.addCleanup(rclpy.shutdown)
        self.executor = SingleThreadedExecutor()
        self.addCleanup(self.executor.shutdown)
        self.peer = Node('session_test_peer')
        self.addCleanup(self.peer.destroy_node)
        self.executor.add_node(self.peer)
        self.events, self.states = [], []
        root = '/uav1/prometheus'
        self.peer.create_subscription(TextInfo, root + '/text_info',
                                      lambda m: self.events.append(json.loads(m.message)), 100)
        self.peer.create_subscription(SessionState, root + '/v2/state', self.states.append, 100)
        self.pubs = {kind: self.peer.create_publisher(cls, root + suffix, 10)
                     for kind, cls, suffix in (
                         ('setup', SetupRequest, '/v2/setup'),
                         ('command', CommandRequest, '/v2/command'),
                         ('legacy_setup', UAVSetup, '/setup'),
                         ('legacy_command', Cmd, '/command'))}
        self.node = None
        self.addCleanup(self.close_node)
        self.make_node()

    def make_node(self):
        if self.stack == 'px4':
            native = PX4Link(RecordingNode(), '', 1, stale_seconds=60.)
            samples = dict(
                status=VehicleStatus(timestamp=1000000, system_id=1, vehicle_type=1,
                                     arming_state=2, nav_state=14),
                position=VehicleLocalPosition(timestamp=1000000, timestamp_sample=999123,
                    xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True,
                    heading_good_for_control=True, x=3., y=2., z=-3.),
                attitude=VehicleAttitude(timestamp=1000000, q=[1., 0., 0., 0.]),
                gps=SensorGps(timestamp=1000000, fix_type=3),
                estimator=EstimatorStatusFlags(timestamp=1000000, cs_tilt_align=True, cs_yaw_align=True),
                land=VehicleLandDetected(timestamp=1000000, landed=False))
            target = 'prometheus_control.native_px4.PX4Link'
        else:
            native = ArduCopterLink(RecordingNode(), position_yaw=True, stale_seconds=60.)
            samples = dict(local=ap_sample(), status=Status(vehicle_type=2, mode=4, armed=True, flying=True))
            target = 'prometheus_control.native_arducopter.ArduCopterLink'
        for key, value in samples.items():
            native.receive(key, value)
        with patch(target, return_value=native):
            self.node = ControlNode()
        self.native = native
        self.executor.add_node(self.node)
        self.until(lambda: all(p.get_subscription_count() for p in self.pubs.values())
                   and any(s.control_epoch == self.node.session.epoch for s in self.states))

    def close_node(self):
        if self.node is not None:
            self.executor.remove_node(self.node)
            self.node.destroy_node()
            self.node = None

    def until(self, predicate, timeout=5.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.executor.spin_once(timeout_sec=.01)
            if predicate():
                return
        self.fail('RMW condition timed out; recent events=' + repr(self.events[-5:]))

    def spin_for(self, seconds=.15):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.executor.spin_once(timeout_sec=.01)

    def request(self, kind, number=1):
        cls = SetupRequest if kind == 'setup' else CommandRequest
        msg = cls(version=1, run_id=self.run_id, control_epoch=self.node.session.epoch, request_id=number)
        nested = getattr(msg, kind)
        nested.header.stamp = self.peer.get_clock().now().to_msg()
        if kind == 'setup':
            nested.cmd, nested.arming = UAVSetup.ARMING, True
        else:
            nested.agent_cmd, nested.command_id, nested.move_mode = Cmd.MOVE, number, Cmd.XYZ_POS
            nested.position_ref = [4., 5., 3.]
        return msg

    def send(self, kind, msg, event, reason=None):
        start = len(self.events)
        self.pubs[kind].publish(msg)
        self.until(lambda: any(e['event'] == event and
                   (reason is None or e.get('reason') == reason) for e in self.events[start:]))
        result = next(e for e in self.events[start:] if e['event'] == event
                      and (reason is None or e.get('reason') == reason))
        self.assertEqual((result['version'], result['run_id'], result['control_epoch']),
                         (1, self.run_id, self.node.session.epoch))
        self.assertEqual(result['request_id'], getattr(msg, 'request_id', 0))
        return result

    def outputs(self):
        pubs = self.native.publishers.values() if self.stack == 'px4' else [self.native.position_pub]
        return sum(len(p.messages) for p in pubs)

    def activate_fixture(self):
        # Boundary precondition, deliberately not a claim of real FC takeover.
        self.assertTrue(self.node.processor.enter_control(Control.COMMAND_CONTROL).accepted)

    def test_wrong_version_run_epoch_both_ingresses(self):
        for kind in ('setup', 'command'):
            for field, value, reason in (
                ('version', 2, 'unsupported_request_version'),
                ('run_id', 'another-run', 'wrong_run_or_control_epoch'),
                ('control_epoch', 'a' * 32, 'wrong_run_or_control_epoch')):
                with self.subTest(kind=kind, field=field):
                    msg = self.request(kind)
                    setattr(msg, field, value)
                    self.send(kind, msg, kind + '_rejected', reason)
                    self.assertEqual(self.node.session.last_request, 0)
        self.spin_for()
        self.assertEqual(self.outputs(), 0)

    def test_shared_request_id_and_semantic_rejection_consumption(self):
        setup = self.request('setup', 7)
        self.send('setup', setup, 'setup_completed')
        self.send('setup', setup, 'setup_rejected', 'request_id_not_increasing')
        self.send('command', self.request('command', 7), 'command_rejected', 'request_id_not_increasing')
        msg = self.request('command', 8)
        self.send('command', msg, 'command_rejected', 'not_command_control')
        self.send('command', msg, 'command_rejected', 'request_id_not_increasing')
        self.assertEqual(self.node.session.last_request, 8)
        self.assertEqual(self.outputs(), 0)

    def test_legacy_inputs_rejected(self):
        for kind in ('setup', 'command'):
            self.send('legacy_' + kind, getattr(self.request(kind), kind),
                      kind + '_rejected', 'legacy_input_requires_session')
        self.spin_for()
        self.assertEqual(self.outputs(), 0)
        self.assertEqual(self.node.session.last_request, 0)

    def test_replay_cannot_replace_setpoint_or_resume_revoked_control(self):
        self.activate_fixture()
        self.assertEqual(self.node.processor.last_command_id, 0)
        self.assertEqual(self.states[-1].command_high_water, 0)
        msg = self.request('command', 1)
        self.send('command', msg, 'command_accepted')
        self.assertEqual(self.node.processor.last_command_id, 1)
        self.until(lambda: self.states[-1].command_high_water == 1)
        self.until(lambda: self.outputs() > 0)
        position_pub = (self.native.publishers['position'] if self.stack == 'px4'
                        else self.native.position_pub)
        prior_wire = serialize_message(position_pub.messages[-1])
        prior_count = len(position_pub.messages)
        state_sequence = self.states[-1].sequence
        accepted = deepcopy(self.node.processor.command)
        replay = deepcopy(msg)
        replay.command.position_ref = [9., 9., 9.]
        self.send('command', replay, 'command_rejected', 'request_id_not_increasing')
        duplicate_move = self.request('command', 2)
        duplicate_move.command.command_id = 1
        self.send('command', duplicate_move, 'command_rejected', 'command_id_not_increasing')
        self.assertEqual(self.node.processor.last_command_id, 1)
        self.until(lambda: self.states[-1].sequence > state_sequence)
        self.assertEqual(self.states[-1].command_high_water, 1)
        self.assertEqual(self.node.processor.command, accepted)
        self.spin_for()
        self.assertGreater(len(position_pub.messages), prior_count)
        for output in position_pub.messages[prior_count:]:
            self.assertEqual(serialize_message(output), prior_wire)
        # An active controller legitimately keeps streaming its accepted target.
        # After revocation, rejected replay must produce no additional output.
        self.node.revoke('test_boundary_revocation')
        count = self.outputs()
        self.send('command', msg, 'command_rejected', 'request_id_not_increasing')
        self.spin_for()
        self.assertEqual(self.outputs(), count)
        self.assertEqual(self.node.processor.control_state, Control.INIT)

    def test_state_source_receive_time_duplicate_and_clock_regression(self):
        first = self.states[-1]
        self.assertEqual((first.version, first.run_id, first.control_epoch),
                         (1, self.run_id, self.node.session.epoch))
        key = 'position' if self.stack == 'px4' else 'local'
        expected_ns = 999123000 if self.stack == 'px4' else 1000000000
        self.assertEqual(first.source_clock, 'fc_boot')
        self.assertTrue(first.source_received_valid)
        self.assertEqual(first.state.header.stamp.sec * 10**9 + first.state.header.stamp.nanosec, expected_ns)
        self.assertEqual(first.control.header, first.state.header)
        received = self.native.state_received_monotonic
        self.assertEqual(first.source_received_monotonic_s, received)
        sample = deepcopy(self.native.latest[key])
        self.native.receive(key, sample)
        self.until(lambda: self.states[-1].sequence > first.sequence)
        later = self.states[-1]
        self.assertEqual(later.source_received_monotonic_s, received)
        self.assertEqual(later.state.header, first.state.header)
        self.assertGreater(later.published_monotonic_s, first.published_monotonic_s)
        self.assertGreaterEqual(first.published_monotonic_s, received)
        field = 'timestamp' if self.stack == 'px4' else 'time_boot_us'
        setattr(sample, field, getattr(sample, field) - 1)
        self.native.receive(key, sample)
        self.until(lambda: self.states[-1].native_generation == 1)
        self.assertFalse(self.states[-1].source_received_valid)
        self.assertEqual(self.states[-1].source_received_monotonic_s, 0.)
        self.assertFalse(self.states[-1].state.connected)

    def test_destroy_same_run_new_epoch_no_old_setpoint(self):
        self.activate_fixture()
        old = self.request('command', 1)
        self.send('command', old, 'command_accepted')
        self.assertEqual(self.node.processor.last_command_id, 1)
        self.until(lambda: self.outputs() > 0)
        session, native = self.node.session, self.native
        token = session.native_identity()
        native.request('mode', 'POSCTL')
        self.assertIsNotNone(native.pending)
        self.close_node()
        self.assertIsNone(session.lock)
        self.assertIsNone(native.pending)
        with self.assertRaisesRegex(ValueError, 'closed'):
            session.accept(old)
        self.make_node()
        self.assertEqual(self.node.session.run_id, old.run_id)
        self.assertNotEqual(self.node.session.epoch, old.control_epoch)
        self.assertNotEqual(self.node.session.native_identity(), token)
        self.assertEqual(self.node.session.last_request, 0)
        self.assertEqual(self.node.processor.last_command_id, 0)
        self.assertEqual(self.states[-1].command_high_water, 0)
        self.assertEqual(self.node.processor.control_state, Control.INIT)
        self.send('command', old, 'command_rejected', 'wrong_run_or_control_epoch')
        old_setup = self.request('setup')
        old_setup.control_epoch = old.control_epoch
        self.send('setup', old_setup, 'setup_rejected', 'wrong_run_or_control_epoch')
        self.spin_for()
        self.assertEqual(self.outputs(), 0)
        fresh = self.request('setup', 1)
        self.send('setup', fresh, 'setup_completed')
        self.activate_fixture()
        self.send('command', self.request('command', 2), 'command_accepted')
        self.until(lambda: self.outputs() > 0)


class PX4SessionTests(SessionBoundary, unittest.TestCase):
    stack = 'px4'


class ArduCopterSessionTests(SessionBoundary, unittest.TestCase):
    stack = 'arducopter'

    def test_local_rmw_delayed_mode_reply_cannot_complete_new_request(self):
        """Real service transport; local server fixture, not FC mode completion."""
        server = Node('delayed_mode_service_fixture')
        self.executor.add_node(server)
        gates = [Future(), Future()]
        received, returned = [], []
        prefix = '/session_service_' + uuid.uuid4().hex

        async def delayed_mode(request, response):
            index = len(received)
            received.append(request.mode)
            await gates[index]
            response.status = True
            response.curr_mode = request.mode
            returned.append(index)
            return response

        server.create_service(ModeSwitch, prefix + '/mode_switch', delayed_mode,
                              callback_group=ReentrantCallbackGroup())
        # A real Node creates the real rclpy client; no RecordingFuture/client.
        link = ArduCopterLink(self.peer, prefix, position_yaw=True)
        client, _ = link.services['mode']
        try:
            self.until(client.service_is_ready)
            link.request('mode', 'POSCTL')
            old = link.pending['future']
            self.until(lambda: len(received) == 1)
            self.assertFalse(old.done())
            link.cancel_request()
            self.assertTrue(old.cancelled())
            self.assertIsNone(link.pending)
            # Identical mode/payload makes transport request correlation essential.
            link.request('mode', 'POSCTL')
            current = link.pending['future']
            self.assertIsNot(current, old)
            self.until(lambda: len(received) == 2)
            self.assertEqual(received, [5, 5])
            self.assertEqual(returned, [])
            gates[0].set_result(True)
            self.until(lambda: returned == [0])
            self.spin_for(.25)
            self.assertTrue(old.cancelled())
            self.assertFalse(current.done())
            self.assertIs(link.pending['future'], current)
            self.assertIsNone(link.poll_request())
            gates[1].set_result(True)
            self.until(current.done)
            self.assertEqual(returned, [0, 1])
            self.assertEqual(link.poll_request(), (True, 'native_service_accepted'))
            self.assertIsNone(link.pending)
        finally:
            link.cancel_request()
            for gate in gates:
                if not gate.done():
                    gate.set_result(True)
            self.spin_for(.05)
            self.executor.remove_node(server)
            server.destroy_node()


if __name__ == '__main__':
    require_isolation()
    import prometheus_control.node as implementation
    print('RMW:', get_rmw_implementation_identifier(), flush=True)
    print('ControlNode:', Path(implementation.__file__).resolve(), flush=True)
    print('Native transport: RecordingNode / local delayed RMW service fixture; no flight controller', flush=True)
    unittest.main(verbosity=2)
