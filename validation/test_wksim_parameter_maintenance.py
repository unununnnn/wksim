"""Offline transactions, replay protocol and real local leases; never launch FC/ROS."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from tools import parameter_maintenance as maintenance
from Simulator.wksim_runtime import parameter_storage
from Simulator.wksim_runtime.parameter_protocol import (
    GroundState, ParameterContext, ParameterError, ParameterProtocol, float32_value)


class CycleTests(unittest.TestCase):
    def task(self, stage, *, original=10.0, target=3.1):
        task = maintenance.MaintenanceTask.__new__(maintenance.MaintenanceTask)
        task.transaction = dict(target_value=target, original_value=original,
                                restore_request_value=original, current_value=None)
        task.probe = dict(pending_restore=True)
        task.channel_action = stage
        task.record = lambda *args, **kwargs: None
        return task

    def test_before_after_restore_are_separate_channels(self):
        task = self.task('before')
        context = ParameterContext('before-op', 'same-run', '1'*32, 0)
        protocol = SimpleNamespace(stack='arducopter', name='WP_SPD', context=context)
        calls, values = [], iter([10.0, float32_value(3.1)])
        def get(expected):
            calls.append(('get', expected))
            return next(values)
        task.cycle(protocol, get, lambda value: calls.append(('set', value)))
        self.assertEqual(calls, [('get', None), ('set', 3.1), ('get', 3.1)])
        self.assertEqual(task.transaction['restore_request_value'], 10)
        task.channel_action = 'after'
        protocol.context = replace(context, operation_id='after-op', control_epoch='2'*32)
        calls.clear()
        values = iter([float32_value(3.1)])
        task.cycle(protocol, get, lambda value: self.fail('Restart readback must never SET'))
        self.assertEqual(calls, [('get', 3.1)])
        self.assertEqual(task.transaction['persistence_readback']['context']['control_epoch'], '2'*32)
        task.channel_action = 'restore'
        calls.clear()
        values = iter([float32_value(3.1), 10.0])
        task.cycle(protocol, get, lambda value: calls.append(('set', value)))
        self.assertEqual(calls, [('get', 3.1), ('set', 10), ('get', 10)])
        self.assertFalse(task.probe['pending_restore'])

    def test_unknown_readback_and_nonrestorable_original_never_trigger_recovery_write(self):
        protocol = SimpleNamespace(stack='arducopter', name='WP_SPD')
        for original in (3.1234, float32_value(3.1)):
            task, calls = self.task('before'), []
            def get(expected):
                if expected is None:
                    return original
                raise TimeoutError('unknown')
            with self.assertRaises((ParameterError, TimeoutError)):
                task.cycle(protocol, get, lambda value: calls.append(value))
            self.assertEqual(calls, [] if original == 3.1234 else [3.1])
            self.assertTrue(task.probe['pending_restore'])
        task = self.task('restore')
        with self.assertRaises(TimeoutError):
            task.cycle(protocol, lambda expected: (_ for _ in ()).throw(TimeoutError()),
                       lambda value: self.fail('Unknown pre-restore read must not SET'))

    def test_expired_authority_invalidates_operation_without_retry(self):
        context = ParameterContext('old-op', 'same-run', '1'*32, 0)
        state = [GroundState(context, 10, True, True, False)]
        protocol = ParameterProtocol('arducopter', 'WP_SPD', context, lambda: state[0], clock=lambda: 10.1)
        state[0] = replace(state[0], context=replace(context, control_epoch='2'*32))
        with self.assertRaises(ParameterError):
            protocol.check_current()
        state[0] = GroundState(context, 10, True, True, False)
        with self.assertRaisesRegex(ParameterError, 'invalidated'):
            protocol.check_current()

    def test_landing_cleanup_and_process_identity_are_required(self):
        good = dict(status='pass', safe_landing=True, children_reaped=True, cleanup_errors=[])
        maintenance.require_finished(good)
        for fields in ({'status': 'failed'}, {'safe_landing': False}, {'children_reaped': False},
                       {'cleanup_errors': ['child still running']}):
            with self.subTest(fields=fields), self.assertRaises(RuntimeError):
                maintenance.require_finished(dict(good, **fields))
        before = dict(preflight={'identities': {'model': {'sha': 'm'}, 'message_packages': {'sha': 's'}}},
                      fc_binary='/fc', fc_sha256='f', fc_commit='c', agent_sha256='a',
                      product_sha256={'node.py': 'n'}, runtime_sha256={'runtime.py': 'r'},
                      children={'fc': {'pid': 101, 'returncode': 0}}, task={'control_epoch': '1'*32})
        after = deepcopy(before)
        after['children']['fc']['pid'] = 102
        after['task']['control_epoch'] = '2'*32
        maintenance.require_restart(before, after)
        for key, replacement in [('fc_sha256', 'changed'), ('product_sha256', {'node.py': 'changed'})]:
            with self.assertRaises(RuntimeError):
                maintenance.require_restart(before, dict(after, **{key: replacement}))
        with self.assertRaises(RuntimeError):
            maintenance.require_restart(before, before)


class NativeWindowTests(unittest.TestCase):
    def test_matching_rejection_needs_native_silence_and_unchanged_request_floor(self):
        position = type('GlobalPosition', (), {'__module__': 'ardupilot_msgs.msg'})
        velocity = type('TwistStamped', (), {'__module__': 'geometry_msgs.msg'})
        modules = {
            'rclpy': SimpleNamespace(),
            'rclpy.qos': SimpleNamespace(QoSProfile=lambda **kw: kw, ReliabilityPolicy=SimpleNamespace(RELIABLE=1),
                                         DurabilityPolicy=SimpleNamespace(VOLATILE=1)),
            'rclpy.qos_event': SimpleNamespace(SubscriptionEventCallbacks=lambda **kw: SimpleNamespace(**kw)),
            'rclpy.serialization': SimpleNamespace(serialize_message=lambda msg: b'recorded envelope',
                deserialize_message=lambda raw, cls: SimpleNamespace(run_id='same-run', control_epoch='1'*32,
                    request_id=4, command=SimpleNamespace(agent_cmd=4))),
            'rosidl_runtime_py': SimpleNamespace(),
            'rosidl_runtime_py.set_message': SimpleNamespace(set_message_fields=lambda msg, data:
                msg.__dict__.update(dict(data, command=SimpleNamespace(**data['command'])))),
            'ardupilot_msgs': SimpleNamespace(), 'ardupilot_msgs.msg': SimpleNamespace(GlobalPosition=position),
            'geometry_msgs': SimpleNamespace(), 'geometry_msgs.msg': SimpleNamespace(TwistStamped=velocity),
        }
        for fault in (None, 'native_output', 'consumed', 'no_rejection', 'unmatched'):
            with self.subTest(fault=fault), patch.dict(sys.modules, modules), \
                    patch.object(maintenance, 'MatchedPublishers', return_value=SimpleNamespace(
                        identity={'api': 'test-only-mocked-matching'},
                        count=lambda sub: 0 if fault == 'unmatched' else 1)):
                task = maintenance.MaintenanceTask.__new__(maintenance.MaintenanceTask)
                task.flight_stack, task.run_id, task.epoch = 'arducopter', 'same-run', '2'*32
                task.retired_epochs = {'1'*32}
                task.Cmd, task.CommandRequest = SimpleNamespace(MOVE=4), SimpleNamespace
                task.request_id = task.session_last_request = 0
                task.session_sequence = 1
                task.events, task.envelopes, task.probe = [], [], {}
                task.transaction = dict(old_move_envelope=dict(run_id='same-run', control_epoch='1'*32,
                    request_id=4, command={'agent_cmd': 4}), old_move_cdr=maintenance.byte_evidence(b'recorded envelope', 'ROS CDR'))
                task.convert = lambda msg: dict(vars(msg), command=vars(msg.command)) if hasattr(msg, 'command') else vars(msg)
                task.record = lambda *args, **kw: None
                task.ready = lambda: True
                subscriptions, closed, published, now = [], [], [], [100.0]
                def create(cls, name, callback, qos, *, event_callbacks):
                    sub = SimpleNamespace(name=name, callback=callback)
                    subscriptions.append(sub)
                    event_callbacks.liveliness(SimpleNamespace(alive_count=1, not_alive_count=0))
                    return sub
                def publishers(name):
                    kind = 'ardupilot_msgs/msg/GlobalPosition' if name.endswith('pose') else 'geometry_msgs/msg/TwistStamped'
                    return [SimpleNamespace(node_name='prometheus_native_control', node_namespace='/',
                                            topic_type=kind, endpoint_gid=[1]*24)]
                task.node = SimpleNamespace(create_subscription=create, get_publishers_info_by_topic=publishers,
                                            destroy_subscription=closed.append)
                task.command_pub = SimpleNamespace(publish=published.append, get_subscription_count=lambda: 1)
                task.setup_pub = SimpleNamespace(get_subscription_count=lambda: 1)
                def pump():
                    now[0] += 0.1
                    task.session_sequence += 1
                    if published and not task.events and fault != 'no_rejection':
                        task.events.append(dict(event='command_rejected', reason='wrong_run_or_control_epoch',
                            run_id='same-run', control_epoch='2'*32, requested_run_id='same-run',
                            requested_epoch='1'*32, request_id=4))
                    if published and fault == 'native_output':
                        subscriptions[0].callback(SimpleNamespace(native='unexpected'))
                    if published and fault == 'consumed':
                        task.session_last_request = 4
                task.pump = pump
                def wait(label, predicate, timeout):
                    pump()
                    if not predicate():
                        raise TimeoutError(label)
                task.wait = wait
                with patch.object(maintenance.time, 'monotonic', side_effect=lambda: now[0]):
                    if fault:
                        with self.assertRaises((RuntimeError, TimeoutError)):
                            task.reject_old_move()
                    else:
                        task.reject_old_move()
                self.assertEqual(len(published), 0 if fault == 'unmatched' else 1)
                if published:
                    self.assertEqual(published[0], b'recorded envelope')
                self.assertEqual(len(closed), 2)
                window = task.probe['old_epoch_native_window']
                self.assertEqual(window['status'], 'pass' if fault is None else 'failed')
                if fault is None:
                    self.assertGreaterEqual(window['end_monotonic'] - window['rejection_monotonic'], 1)
                    self.assertEqual(window['request_high_water_after'], 0)


@unittest.skipUnless(sys.platform == 'linux', 'Real local POSIX lease and replay counter')
class LeaseAndReplayTests(unittest.TestCase):
    def test_real_reopen_preserves_bytes_inode_marker_and_rejects_same_byte_replacement(self):
        config = dict(stack='arducopter', runtime_profile='independent_quad_dds_v1', control_protocol='session_v1')
        with tempfile.TemporaryDirectory() as root, patch.object(parameter_storage, 'ROOT', Path(root)):
            identity = str(uuid4())
            with parameter_storage.ParameterStorage(identity, 'arducopter') as lease:
                path = lease.path / 'eeprom.bin'
                path.write_bytes(b'fixture parameter storage, no FC')
                before = maintenance.storage_snapshot(config, lease)
            with parameter_storage.ParameterStorage(identity, 'arducopter', reopen=True) as lease:
                after = maintenance.storage_snapshot(config, lease)
                maintenance.require_retained(before, after)
                replacement = lease.path / 'replacement'
                replacement.write_bytes(path.read_bytes())
                replacement.replace(path)
                with self.assertRaisesRegex(RuntimeError, 'parameter_files'):
                    maintenance.require_retained(before, maintenance.storage_snapshot(config, lease))

    def test_actual_session_rejects_retired_move_without_consuming_new_number(self):
        path = Path(__file__).resolve().parents[1] / 'ros2/src/prometheus_control/prometheus_control/session.py'
        spec = importlib.util.spec_from_file_location('maintenance_test_session', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / 'session'
            old = module.RunSession('same-run', 1, directory)
            old_epoch = old.epoch
            old.close()
            current = module.RunSession('same-run', 1, directory)
            try:
                request = SimpleNamespace(version=1, run_id='same-run', control_epoch=old_epoch,
                                          request_id=4, command=SimpleNamespace(agent_cmd='MOVE'))
                with self.assertRaisesRegex(ValueError, 'wrong_run_or_control_epoch'):
                    current.accept(request)
                self.assertEqual(current.last_request, 0)
                request.control_epoch, request.request_id = current.epoch, 1
                self.assertEqual(current.accept(request), 1)
            finally:
                current.close()

    def test_failed_before_result_never_restarts_or_copies_parameter_storage(self):
        config = dict(stack='arducopter', run_id='mock-maintenance', runtime_profile='independent_quad_dds_v1',
                      control_protocol='session_v1')
        with tempfile.TemporaryDirectory(prefix='wksim-maintenance-unit-', dir='/root') as directory:
            output = Path(directory)
            output.rmdir()  # A new output root is part of the CLI contract.
            with tempfile.TemporaryDirectory() as leases, patch.object(parameter_storage, 'ROOT', Path(leases)), \
                    patch('Simulator.wksim_runtime.independent_profile.select_config', return_value=(config, {})), \
                    patch.object(maintenance, 'run', return_value=dict(status='failed', safe_landing=False,
                        children_reaped=True, cleanup_errors=[], error='fixture failure')) as run:
                report = maintenance.run_maintenance(config, output, 3.1)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['restart_operations'], [])
                self.assertIn('before', report['stages'])
                self.assertNotIn('after', report['stages'])
                self.assertTrue((output / 'parameter-maintenance.json').is_file())


if __name__ == '__main__':
    unittest.main()
