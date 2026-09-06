"""Restart/correlation regressions using actual ROS schemas and recording transports."""
from copy import deepcopy
import unittest

from px4_msgs.msg import VehicleCommand, VehicleCommandAck
from rclpy.serialization import serialize_message, deserialize_message
from ardupilot_msgs.srv import ModeSwitch
from prometheus_control.native_px4 import PX4Link
from validation import test_prometheus_native as fixtures
from validation.test_prometheus_native import RecordingNode


class EpochTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.NativeTests()
        fixture.setUp()
        self.fixture = fixture
        self.px, self.ap = fixture.px, fixture.ap

    def test_duplicate_frozen_and_regressed_state(self):
        for link, key in ((self.px, 'position'), (self.ap, 'local'), (self.px, 'status'), (self.ap, 'status')):
            with self.subTest(key=key, adapter=type(link).__name__):
                original = deepcopy(link.latest[key])
                received = link.received[key]
                self.fixture.now += 3
                link.receive(key, deepcopy(original))
                self.assertEqual(link.received[key], received)
                self.assertEqual(link.latest[key], original)
                self.assertFalse(link.fresh(key))
                self.assertEqual(link.consume_rejections()[-1]['reason'], 'duplicate_source')
        for link, key, field in ((self.px, 'position', 'timestamp'), (self.ap, 'local', 'time_boot_us')):
            old = deepcopy(link.latest[key])
            setattr(old, field, getattr(old, field)-1)
            link.receive(key, old)
            self.assertEqual(link.consume_resets(), {'clock'})
            self.assertFalse(link.latest)
            setattr(old, field, getattr(old, field)+100)
            link.receive(key, old)
            self.assertFalse(link.fresh(key))
            self.assertFalse(link.latest)

    def test_receive_clock_rewind_never_resurrects_cache(self):
        self.fixture.now -= 1
        self.assertFalse(self.px.fresh('position'))
        self.assertFalse(self.ap.fresh('local'))

        self.fixture.now += 1.1
        self.assertFalse(self.px.fresh('position'))
        self.assertFalse(self.ap.fresh('local'))
        self.assertIsNone(self.ap.state_received_monotonic)

    def test_sample_clock_and_receive_stamp(self):
        self.assertEqual(self.px.state_received_monotonic, 10.)
        self.assertEqual(self.ap.state_received_monotonic, 10.)
        pos = deepcopy(self.px.latest['position'])
        pos.timestamp += 10
        self.fixture.now += 1
        self.px.receive('position', pos)
        self.assertEqual(self.px.state_received_monotonic, 10.)
        pos.timestamp_sample += 1
        self.px.receive('position', pos)
        self.assertEqual(self.px.state_received_monotonic, 11.)
        pos = deepcopy(pos)
        pos.timestamp += 1
        pos.timestamp_sample -= 1
        self.px.receive('position', pos)
        self.assertIsNone(self.px.state_received_monotonic)
        self.assertFalse(self.px.fresh('position'))
        self.fixture.now += 1.1
        self.assertFalse(self.px.fresh('position'))
        self.assertFalse(self.ap.fresh('local'))

    def test_restart_same_command_requires_allocated_pair(self):
        identities = iter(((245, 192), (245, 193)))
        new = PX4Link(RecordingNode(), '', 22, request_identity=lambda: next(identities), clock=lambda: self.fixture.now)
        new.receive('position', deepcopy(self.px.latest['position']))
        new.request('arm', True)
        new.cancel_request()
        new.request('arm', True)
        ack = VehicleCommandAck(timestamp=1_000_100, command=400, target_system=245, target_component=192, result=0)
        new.receive('ack', ack)
        self.assertIsNone(new.poll_request())
        ack.target_component = 193
        ack.timestamp = 999_999
        new.receive('ack', ack)
        self.assertIsNone(new.poll_request())
        ack.timestamp = 1_000_101
        ack.result = 5
        ack.result_param1 = 60
        new.receive('ack', deepcopy(ack))
        ack.result = 0
        new.receive('ack', deepcopy(ack))
        self.assertIsNone(new.poll_request())  # Same source stamp cannot turn progress into success.
        ack.timestamp += 1
        ack.result = 5
        ack.result_param1 = 30
        new.receive('ack', deepcopy(ack))
        self.assertEqual(new.latest['ack'].result_param1, 60)
        ack.timestamp += 1
        ack.result = 0
        new.receive('ack', ack)
        self.assertEqual(new.poll_request(), (True, 'native_result_0'))
        self.assertEqual(new.publishers['command'].messages[-1].source_component, 193)

    def test_allocator_failure_or_reuse_never_publishes(self):
        self.px.request_identity = lambda: (245, 192)
        self.px.request('arm', True)
        self.px.cancel_request()
        with self.assertRaises(ValueError):
            self.px.request('arm', True)
        self.assertEqual(len(self.px.publishers['command'].messages), 1)
        self.px.request_identity = lambda: (0, 256)
        with self.assertRaises(ValueError):
            self.px.request('arm', True)
        self.assertEqual(len(self.px.publishers['command'].messages), 1)

    def test_actual_identity_schema_roundtrip(self):
        self.assertEqual(VehicleCommand.get_fields_and_field_types()['source_system'], 'uint8')
        self.assertEqual(VehicleCommand.get_fields_and_field_types()['source_component'], 'uint16')
        self.assertEqual(VehicleCommandAck.get_fields_and_field_types()['target_component'], 'uint16')
        for system, component in ((200, 1), (254, 255)):
            command = VehicleCommand(source_system=system, source_component=component)
            ack = VehicleCommandAck(target_system=system, target_component=component)
            self.assertEqual(deserialize_message(serialize_message(command), VehicleCommand), command)
            self.assertEqual(deserialize_message(serialize_message(ack), VehicleCommandAck), ack)

    def test_cancelled_ap_future_cannot_complete_next_request(self):
        self.ap.request('mode', 'POSCTL')
        old = self.ap.pending['future']
        client = self.ap.pending['client']
        self.ap.cancel_request()
        self.assertIs(client.removed, old)
        self.ap.request('mode', 'POSCTL')
        current = self.ap.pending['future']
        old.set_result(ModeSwitch.Response(status=True, curr_mode=5))
        self.assertIsNone(self.ap.poll_request())
        current.set_result(ModeSwitch.Response(status=True, curr_mode=5))
        self.assertEqual(self.ap.poll_request(), (True, 'native_service_accepted'))

    def test_rejection_backlog_bounded_and_drained(self):
        sample = deepcopy(self.px.latest['position'])
        for _ in range(200):
            self.px.receive('position', sample)
        self.assertEqual(len(self.px.consume_rejections()), 128)
        self.assertEqual(self.px.consume_rejections(), [])


if __name__ == '__main__':
    unittest.main()
