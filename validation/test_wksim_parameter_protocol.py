"""Offline native ROS serialization and pinned MAVLink wire-codec tests.

Run in project WSL Ubuntu-22.04 with /opt/ros/humble/setup.bash sourced.
No ROS node, network socket, FC, UE, or physics process is started.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Simulator'))
from wksim_runtime.parameter_protocol import (
    GroundState, ParameterContext, ParameterError, ParameterProtocol, validate_value, float32_value, restore_request_value,
)


class ParameterProtocolTest(unittest.TestCase):
    def setUp(self):
        self.context = ParameterContext('op-1', 'run-1', '768795a5e42943edac2a6bf4992ad750', 3)
        self.state = GroundState(self.context, 10.0, True, True, False)

    def protocol(self, stack='arducopter', **kwargs):
        return ParameterProtocol(stack, 'WP_SPD' if stack == 'arducopter' else 'MPC_XY_CRUISE',
                                 self.context, lambda: self.state, clock=lambda: 10.1, **kwargs)

    def test_allowlist_range_type_increment(self):
        for stack, name in [('arducopter', 'WP_SPD'), ('px4', 'MPC_XY_CRUISE')]:
            for value in [True, False, '4', None, 10**400, float('nan'), float('inf'), -float('inf'), 2.9, 10.1, 3.01, 3.0000001]:
                with self.subTest(stack=stack, value=value), self.assertRaises(ParameterError):
                    validate_value(stack, name, value)
            for value in [3, 4.0, 5]:
                self.assertEqual(validate_value(stack, name, value), value)
            with self.assertRaises(ParameterError):
                validate_value(stack, 'UNKNOWN', 4)
        self.assertEqual(validate_value('arducopter', 'WP_SPD', 3.1), 3.1)
        with self.assertRaises(ParameterError):
            validate_value('px4', 'MPC_XY_CRUISE', 3.1)

    def test_exact_storage_and_lossless_restore(self):
        protocol = self.protocol()
        for n in range(30, 101):
            requested = n / 10
            actual = float32_value(requested)
            self.assertEqual(restore_request_value('arducopter', 'WP_SPD', actual), requested)
            self.assertEqual(protocol._value(actual, requested), actual)
            with self.assertRaises(ParameterError):
                protocol._value(actual + 1e-10, requested)
        self.assertEqual(restore_request_value('arducopter', 'WP_SPD', 10), 10)
        for value in [3.1, 3.125, 2.0, 11.0, True, float('nan')]:
            with self.subTest(value=value), self.assertRaises(ParameterError):
                restore_request_value('arducopter', 'WP_SPD', value)
        for value in [3.1, 5.1, 10.0]:
            with self.assertRaises(ParameterError):
                validate_value('px4', 'MPC_XY_CRUISE', value)
        for value in [3, 4, 5]:
            self.assertEqual(restore_request_value('px4', 'MPC_XY_CRUISE', value), value)

    def test_write_cycle_stops_without_recovery_on_unknown(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.probe_parameter_write import WriteProbe
        from types import SimpleNamespace
        protocol = SimpleNamespace(stack='arducopter', name='WP_SPD')
        for original, fail_read, expected_writes in [(10.0, None, [4.0, 10.0]),
                                                   (3.125, None, []),
                                                   (10.0, 2, [4.0]),
                                                   (10.0, 3, [4.0, 10.0])]:
            probe = object.__new__(WriteProbe)
            probe.probe = {'pending_restore': False}
            probe.record = lambda *args, **kwargs: None
            writes, reads = [], []
            def get(expected):
                reads.append(expected)
                if len(reads) == fail_read:
                    raise TimeoutError('unknown read result')
                return original if expected is None else float32_value(expected)
            def set_value(value):
                writes.append(value)
                probe.probe['pending_restore'] = True
            if fail_read or original == 3.125:
                with self.assertRaises((ValueError, TimeoutError)):
                    probe.cycle(protocol, get, set_value)
            else:
                probe.cycle(protocol, get, set_value)
                self.assertEqual(reads, [None, 4.0, 10.0])
                self.assertFalse(probe.probe['pending_restore'])
            self.assertEqual(writes, expected_writes)
            if fail_read:
                self.assertTrue(probe.probe['pending_restore'])

    def test_current_state_invalidation_is_latched(self):
        changes = [dict(disarmed=False), dict(grounded=False), dict(active_task=True),
                   dict(disarmed=1), dict(observed_at=9.0), dict(observed_at=11.0),
                   dict(observed_at=float('nan')), dict(observed_at=10**400)]
        changes += [dict(context=replace(self.context, **{field: value})) for field, value in
                    [('operation_id', 'op-2'), ('run_id', 'run-2'), ('control_epoch', '1' * 32), ('native_generation', 4)]]
        original = self.state
        for change in changes:
            with self.subTest(change=change):
                self.state = original
                protocol = self.protocol()
                self.state = replace(original, **change)
                with self.assertRaises(ParameterError):
                    protocol.ap_set_request(4)
                self.state = original
                with self.assertRaises(ParameterError):
                    protocol.ap_set_request(4)

        self.state = original
        for bad_now in [True, '10.1', None, 10**400, float('nan'), float('inf'), 10.05]:
            with self.subTest(now=bad_now):
                now = [10.1]
                protocol = ParameterProtocol('arducopter', 'WP_SPD', self.context,
                                             lambda: self.state, clock=lambda: now[0])
                now[0] = bad_now
                with self.assertRaises(ParameterError):
                    protocol.check_current()
                now[0] = 10.2
                with self.assertRaises(ParameterError):
                    protocol.check_current()
                with self.assertRaises(ParameterError):
                    protocol.ap_set_request(4)

    def test_real_ros_requests_and_responses(self):
        from rcl_interfaces.msg import ParameterType, ParameterValue, SetParametersResult
        from rcl_interfaces.srv import GetParameters, SetParameters
        from rclpy.serialization import serialize_message, deserialize_message
        protocol = self.protocol()
        request = protocol.ap_get_request()
        self.assertEqual(deserialize_message(serialize_message(request), GetParameters.Request).names, ['WP_SPD'])
        request = protocol.ap_set_request(3.1)
        decoded = deserialize_message(serialize_message(request), SetParameters.Request)
        self.assertEqual(len(decoded.parameters), 1)
        self.assertEqual(decoded.parameters[0].name, 'WP_SPD')
        self.assertEqual(decoded.parameters[0].value.type, ParameterType.PARAMETER_DOUBLE)
        self.assertEqual(decoded.parameters[0].value.double_value, 3.1)
        accepted = SetParameters.Response(results=[SetParametersResult(successful=True, reason='Parameter accepted')])
        self.assertEqual(protocol.ap_set_result(deserialize_message(serialize_message(accepted), SetParameters.Response)),
                         (True, 'Parameter accepted'))
        rejected = SetParameters.Response(results=[SetParametersResult(successful=False, reason='Parameter not found')])
        self.assertEqual(protocol.ap_set_result(rejected), (False, 'Parameter not found'))
        for results in [[], accepted.results + rejected.results]:
            with self.assertRaises(ParameterError):
                protocol.ap_set_result(SetParameters.Response(results=results))
        actual = 3.0999999046325684  # actual float32 storage widened to ROS double
        response = GetParameters.Response(values=[ParameterValue(type=3, double_value=actual)])
        self.assertEqual(protocol.ap_get_value(deserialize_message(serialize_message(response), GetParameters.Response),
                                               expected=3.1), actual)
        for values in [[], response.values * 2, [ParameterValue(type=0)],
                       [ParameterValue(type=2, integer_value=4)],
                       [ParameterValue(type=3, double_value=float('nan'))]]:
            with self.assertRaises(ParameterError):
                protocol.ap_get_value(GetParameters.Response(values=values))
        with self.assertRaises(ParameterError):
            protocol.ap_get_value(response, expected=4)
        for stored in [11.0, 3.1234]:
            response = GetParameters.Response(values=[ParameterValue(type=3, double_value=stored)])
            self.assertEqual(protocol.ap_get_value(response), stored)
            with self.assertRaises(ParameterError):
                protocol.ap_set_request(stored)
            with self.assertRaises(ParameterError):
                protocol.ap_get_value(response, expected=stored)

    def test_real_pinned_mavlink_roundtrip_and_peer_checks(self):
        from wksim_runtime.telemetry_dialect import load_dialect
        dialect, evidence = load_dialect('px4')
        self.assertEqual(evidence['fc_commit'], 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4')
        peer = ('127.0.0.1', 18000)
        protocol = self.protocol('px4', dialect=dialect, peer=peer, target_system=1, target_component=1)

        def wire(message, system=1, component=1):
            encoder = dialect.MAVLink(None, srcSystem=system, srcComponent=component)
            return dialect.MAVLink(None).parse_char(message.pack(encoder))

        read = wire(protocol.px4_read_message(), 250, 190)
        self.assertEqual(read.get_type(), 'PARAM_REQUEST_READ')
        self.assertEqual((read.target_system, read.target_component, read.param_index, read.param_id),
                         (1, 1, -1, 'MPC_XY_CRUISE'))
        write = wire(protocol.px4_set_message(4), 250, 190)
        self.assertEqual(write.get_type(), 'PARAM_SET')
        self.assertEqual((write.target_system, write.target_component, write.param_id, write.param_value, write.param_type),
                         (1, 1, 'MPC_XY_CRUISE', 4.0, dialect.MAV_PARAM_TYPE_REAL32))

        def response(name=b'MPC_XY_CRUISE', value=4.0, param_type=9, system=1, component=1):
            return wire(dialect.MAVLink_param_value_message(name, value, param_type, 100, 20), system, component)

        good = response()
        self.assertEqual(protocol.px4_value(good, peer=peer, context=self.context, expected=4), 4)
        # Identical duplicate observations remain indistinguishable on this wire protocol.
        self.assertEqual(protocol.px4_value(good, peer=peer, context=self.context, expected=4), 4)
        self.assertEqual(protocol.px4_value(response(value=10), peer=peer, context=self.context), 10)
        self.assertAlmostEqual(protocol.px4_value(response(value=3.125), peer=peer, context=self.context), 3.125)
        cases = [dict(peer=('127.0.0.1', 18001)), dict(context=replace(self.context, control_epoch='1' * 32)),
                 dict(context=replace(self.context, native_generation=2)), dict(message=response(system=2)),
                 dict(message=response(component=2)), dict(message=response(name=b'UNKNOWN')),
                 dict(message=response(param_type=6)), dict(message=response(value=5.0)),
                 dict(message=response(value=float('nan'))), dict(message=response(value=6.0)),
                 dict(message=wire(dialect.MAVLink_command_ack_message(400, 0)))]
        for change in cases:
            args = dict(message=good, peer=peer, context=self.context, expected=4)
            args.update(change)
            with self.subTest(change=change), self.assertRaises(ParameterError):
                protocol.px4_value(**args)
        self.state = replace(self.state, active_task=True)
        with self.assertRaises(ParameterError):
            protocol.px4_set_message(4)


if __name__ == '__main__':
    unittest.main()
