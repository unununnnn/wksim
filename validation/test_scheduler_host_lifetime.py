"""Host EOF, deferred signals and owned preflight cleanup; no SITL or tracefs."""
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from tools.profile_joint_scheduler import (
    check_host_cancelled, install_cleanup_signal_handlers,
    kill_manager_group,
    _record_collector_capture,
    retire_manager,
    restore_cleanup_signal_handlers, run, run_owned_preflight,
    wait_owned_process, watch_host_input,
)

ROOT = Path(__file__).resolve().parents[1]


class SchedulerHostLifetimeTests(unittest.TestCase):
    def test_host_fd_failure_requests_shutdown_instead_of_silently_disabling_watch(self):
        stream = Mock()
        stream.fileno.return_value = 19
        notified = threading.Event()
        with patch('tools.profile_joint_scheduler.os.name', 'posix'), \
                patch('tools.profile_joint_scheduler.select.select', side_effect=OSError('closed fd')):
            watcher = watch_host_input(stream, notified.set)
            watcher.join(timeout=1)
        self.assertTrue(notified.is_set())
        self.assertFalse(watcher.is_alive())
        stream.read.assert_not_called()

    def test_host_eof_emits_exactly_one_shutdown_notification(self):
        called = threading.Event()
        callback = Mock(side_effect=called.set)
        stopped = watch_host_input(io.BytesIO(b'ignored host bytes'), callback)
        self.assertTrue(called.wait(1))
        callback.assert_called_once_with()
        stopped.set()
        stopped.join(1)
        self.assertFalse(stopped.is_alive())

    def test_signals_can_defer_interrupt_until_handle_is_recorded(self):
        cancelled = threading.Event()
        previous = install_cleanup_signal_handlers(cancelled)
        try:
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            self.assertTrue(cancelled.is_set())
            with self.assertRaises(KeyboardInterrupt):
                check_host_cancelled(cancelled)
        finally:
            restore_cleanup_signal_handlers(previous)

    def test_wait_obeys_cancel_before_waiting_on_child(self):
        cancelled = threading.Event()
        cancelled.set()
        process = Mock()
        with self.assertRaises(KeyboardInterrupt):
            wait_owned_process(process, 180, cancelled)
        process.poll.assert_not_called()

    def test_wait_returns_reaped_exit_code(self):
        process = Mock()
        process.poll.return_value = 7
        self.assertEqual(wait_owned_process(process, 1), 7)

    def test_host_watch_requires_exchange_before_creating_output(self):
        with self.assertRaisesRegex(ValueError, 'exchange directory'):
            run(Path('/root/wksim-scheduler-probe-never-created-host-test'), watch_host_stdin=True)

    def test_preflight_identity_none_after_exit_fails_closed(self):
        process = Mock(pid=123, args=['preflight'])
        process.poll.return_value = 0
        process.returncode = 0
        result = {}
        with patch('tools.profile_joint_scheduler.subprocess.Popen', return_value=process), \
                patch('tools.profile_joint_scheduler.json_identity', return_value=None), \
                patch('tools.profile_joint_scheduler.group_members') as members:
            with self.assertRaisesRegex(RuntimeError, 'identity unavailable'):
                run_owned_preflight(['preflight'], Mock(), result)
        self.assertIn('preflight_cleanup_error', result)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        members.assert_not_called()

    def test_preflight_identity_none_terminates_and_reaps_live_handle(self):
        process = Mock(pid=123, args=['preflight'])
        process.poll.side_effect = [None, None, 0]
        process.wait.return_value = 0
        result = {}
        with patch('tools.profile_joint_scheduler.subprocess.Popen', return_value=process), \
                patch('tools.profile_joint_scheduler.json_identity', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'identity unavailable'):
                run_owned_preflight(['preflight'], Mock(), result)
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)
        self.assertEqual(result['remaining_preflight_group'], [True])

    def test_preflight_identity_read_error_still_reaps_live_handle(self):
        process = Mock(pid=123, args=['preflight'])
        process.poll.side_effect = [None, 0]
        process.wait.return_value = 0
        result = {}
        with patch('tools.profile_joint_scheduler.subprocess.Popen', return_value=process), \
                patch('tools.profile_joint_scheduler.json_identity', side_effect=OSError('proc race')):
            with self.assertRaisesRegex(RuntimeError, 'identity unavailable'):
                run_owned_preflight(['preflight'], Mock(), result)
        process.terminate.assert_called_once_with()
        process.kill.assert_not_called()
        process.wait.assert_called_once_with(timeout=10)

    def test_preflight_start_failure_does_not_enter_cleanup_with_no_handle(self):
        result = {}
        with patch('tools.profile_joint_scheduler.subprocess.Popen',
                   side_effect=OSError('spawn failed')):
            with self.assertRaisesRegex(OSError, 'spawn failed'):
                run_owned_preflight(['preflight'], Mock(), result)
        self.assertNotIn('preflight_identity', result)

    def test_exited_preflight_leader_cleans_saved_residual_group(self):
        process = Mock(pid=123, args=['preflight'])
        process.poll.return_value = 0
        process.returncode = 0
        expected = {'pid': 123, 'start_ticks': 9, 'pgid': 123, 'argv': ['preflight']}
        snapshot = {(123, 9), (124, 10)}
        result = {}
        with patch('tools.profile_joint_scheduler.subprocess.Popen', return_value=process), \
                patch('tools.profile_joint_scheduler.json_identity', return_value=expected), \
                patch('tools.profile_joint_scheduler.manager_group_snapshot', return_value=snapshot), \
                patch('tools.profile_joint_scheduler.kill_manager_group_after_leader') as kill_group, \
                patch('tools.profile_joint_scheduler.group_members',
                      return_value=[{'pid': 124, 'start_ticks': 10, 'pgid': 123}]):
            code = run_owned_preflight(['preflight'], Mock(), result)
        self.assertEqual(code, 0)
        kill_group.assert_called_once_with(expected, snapshot)
        self.assertEqual(result['remaining_preflight_group'],
                         [{'pid': 124, 'start_ticks': 10, 'pgid': 123}])
        self.assertIn('Owned preflight group remains', result['preflight_cleanup_error'])

    def test_live_preflight_refreshes_group_snapshot_before_force_kill(self):
        class LivePreflight:
            pid = 321
            args = ['preflight']

            def __init__(self):
                self.returncode = None

            def poll(self):
                return self.returncode

            def wait(self, timeout):
                self.returncode = -9
                return self.returncode

        process = LivePreflight()
        expected = {'pid': 321, 'start_ticks': 11, 'pgid': 321}
        initial_snapshot = {(321, 11)}
        refreshed_snapshot = {(321, 11), (322, 12)}
        result = {}
        cancelled = threading.Event()
        cancelled.set()
        with patch('tools.profile_joint_scheduler.subprocess.Popen', return_value=process), \
                patch('tools.profile_joint_scheduler.json_identity', return_value=expected), \
                patch('tools.profile_joint_scheduler.manager_group_snapshot',
                      side_effect=[initial_snapshot, refreshed_snapshot]) as snapshot, \
                patch('tools.profile_joint_scheduler.kill_manager_group') as kill_group, \
                patch('tools.profile_joint_scheduler.kill_manager_group_after_leader') as kill_after, \
                patch('tools.profile_joint_scheduler.group_members', return_value=[]):
            with self.assertRaises(KeyboardInterrupt):
                run_owned_preflight(['preflight'], Mock(), result, cancelled)
        self.assertEqual(snapshot.call_count, 2)
        self.assertEqual(result['preflight_group_snapshot'],
                         [{'pid': 321, 'start_ticks': 11}, {'pid': 322, 'start_ticks': 12}])
        kill_group.assert_called_once_with(process, expected, refreshed_snapshot)
        kill_after.assert_called_once_with(expected, refreshed_snapshot)
        self.assertEqual(result['remaining_preflight_group'], [])

    def test_exited_preflight_rejects_unknown_member_using_saved_snapshot(self):
        process = Mock(pid=123, args=['preflight'])
        process.poll.return_value = 0
        process.returncode = 0
        expected = {'pid': 123, 'start_ticks': 9, 'pgid': 123, 'argv': ['preflight']}
        snapshot = {(123, 9), (124, 10)}
        unknown = [{'pid': 125, 'start_ticks': 11, 'pgid': 123}]
        result = {}
        with patch('tools.profile_joint_scheduler.subprocess.Popen', return_value=process), \
                patch('tools.profile_joint_scheduler.json_identity', return_value=expected), \
                patch('tools.profile_joint_scheduler.manager_group_snapshot', return_value=snapshot), \
                patch('tools.profile_joint_scheduler.group_members', return_value=unknown), \
                patch('tools.profile_joint_scheduler.os.name', 'posix'), \
                patch('tools.profile_joint_scheduler.os.killpg', create=True) as killpg:
            run_owned_preflight(['preflight'], Mock(), result)
        killpg.assert_not_called()
        self.assertEqual(result['remaining_preflight_group'], unknown)
        self.assertIn('Manager group member identity differs', result['preflight_cleanup_error'])

    def test_preflight_group_kill_rejects_unknown_member(self):
        process = Mock(pid=123, args=['preflight'])
        process.poll.return_value = None
        expected = {'pid': 123, 'start_ticks': 9, 'pgid': 123, 'argv': ['preflight']}
        snapshot = {(123, 9)}
        with patch('tools.profile_joint_scheduler.json_identity', return_value=expected), \
                patch('tools.profile_joint_scheduler.group_members', return_value=[
                    {'pid': 123, 'start_ticks': 9, 'pgid': 123},
                    {'pid': 124, 'start_ticks': 10, 'pgid': 123}]), \
                patch('tools.profile_joint_scheduler.os.killpg', create=True) as killpg:
            with self.assertRaisesRegex(RuntimeError, 'group member identity differs'):
                kill_manager_group(process, expected, snapshot)
        killpg.assert_not_called()
        process.kill.assert_not_called()

    def test_live_manager_refreshes_group_snapshot_before_force_kill(self):
        class LiveManager:
            pid = 321

            def __init__(self):
                self.returncode = None

            def poll(self):
                return self.returncode

            def wait(self, timeout):
                if timeout == 40:
                    raise subprocess.TimeoutExpired('manager', timeout)
                self.returncode = -9
                return self.returncode

        old_snapshot = [{'pid': 321, 'start_ticks': 11}]
        refreshed_snapshot = {(321, 11), (322, 12)}
        manager = LiveManager()
        result = {
            'run_id': 'run',
            'manager': {'pid': 321, 'start_ticks': 11, 'pgid': 321},
            'manager_group_snapshot': old_snapshot,
        }
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'status.json').write_text(
                json.dumps({'run_id': 'run', 'epoch': 'a' * 32}))
            with patch('tools.profile_joint_scheduler.submit',
                       side_effect=RuntimeError('mailbox unavailable')), \
                    patch('tools.profile_joint_scheduler.save_manager_group_snapshot',
                          return_value=refreshed_snapshot) as refresh, \
                    patch('tools.profile_joint_scheduler.kill_manager_group') as kill, \
                    patch('tools.profile_joint_scheduler.group_members', return_value=[]):
                retire_manager(manager, directory, result)
        refresh.assert_called_once_with(manager, result)
        kill.assert_called_once_with(manager, result['manager'], refreshed_snapshot)
        self.assertEqual(result['manager_returncode'], -9)
        self.assertEqual(result['remaining_manager_group'], [])

    @unittest.skipUnless(os.name == 'posix', 'real Linux process-group cleanup')
    def test_real_stdin_eof_reaps_owned_preflight_through_finally(self):
        program = r'''
import json,os,sys,threading
from tools.profile_joint_scheduler import (install_cleanup_signal_handlers,
    restore_cleanup_signal_handlers,watch_host_input,run_owned_preflight)
cancelled=threading.Event()
previous=install_cleanup_signal_handlers(cancelled)
stopped=watch_host_input(sys.stdin.buffer)
result={}
try:
    with open(os.devnull,'w') as log:
        run_owned_preflight([sys.executable,'-B','-c','import time; time.sleep(30)'],
                            log,result,cancelled)
except KeyboardInterrupt:
    result['interrupted']=True
finally:
    stopped.set()
    stopped.join(1)
    restore_cleanup_signal_handlers(previous)
print(json.dumps(result))
'''
        result = subprocess.run([sys.executable, '-B', '-c', program], cwd=ROOT,
                                input='', text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt['interrupted'])
        self.assertIsInstance(receipt['preflight_returncode'], int)
        self.assertEqual(receipt['remaining_preflight_group'], [])
        self.assertNotIn('preflight_cleanup_error', receipt)

    @unittest.skipUnless(os.name == 'posix', 'real Linux fd watcher')
    def test_real_open_stdin_pipe_child_normal_exit_reaps_watcher(self):
        program = r'''
import json,os,sys
from tools.profile_joint_scheduler import watch_host_input,run_owned_preflight
stopped=watch_host_input(sys.stdin.buffer)
result={}
try:
    with open(os.devnull,'w') as log:
        result['preflight_returncode']=run_owned_preflight(
            [sys.executable,'-B','-c','import sys; sys.exit(0)'], log, result)
finally:
    stopped.set()
    stopped.join(1)
    result['watcher_alive']=stopped.is_alive()
print(json.dumps(result))
'''
        child = subprocess.Popen(
            [sys.executable, '-B', '-c', program], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            code = child.wait(timeout=15)
            stdout = child.stdout.read() if child.stdout is not None else b''
            stderr = child.stderr.read() if child.stderr is not None else b''
        finally:
            if child.stdin is not None and not child.stdin.closed:
                child.stdin.close()
        self.assertEqual(code, 0, stderr.decode(errors='replace'))
        receipt = json.loads(stdout)
        self.assertEqual(receipt['preflight_returncode'], 0)
        self.assertFalse(receipt['watcher_alive'])
        self.assertEqual(receipt['remaining_preflight_group'], [])

    def test_partial_collector_metadata_is_retained_after_retirement(self):
        owners = {
            role: {'pid': index, 'start_ticks': index + 100,
                   'pgid': index, 'argv': [role]}
            for index, role in enumerate(
                ('ap_worker', 'px4_worker', 'supervisor', 'ap_fc', 'px4_fc'), 10)
        }
        collector = {'pid': 99, 'start_ticks': 199, 'pgid': 99, 'argv': ['collector']}
        capture = {
            'schema': 'wksim.private-tracefs.v1', 'run_id': 'run-1', 'epoch': 'e' * 32,
            'instance': '/sys/kernel/tracing/instances/wksim-rate-one',
            'instance_inode': [1, 2], 'collector_pid': 99, 'collector_start_ticks': 199,
            'owners': {role: {'pid': value['pid'], 'start_ticks': value['start_ticks']}
                       for role, value in owners.items()},
            'complete': False, 'instance_removed': True,
            'errors': ['post-capture proof failed'],
        }
        owner = {
            'schema': 'wksim.private-tracefs.instance-owner.v1',
            'instance': capture['instance'], 'instance_inode': capture['instance_inode'],
            'collector_pid': 99, 'collector_start_ticks': 199,
            'supervisor_pid': owners['supervisor']['pid'],
            'supervisor_start_ticks': owners['supervisor']['start_ticks'],
            'owners': owners, 'boot_id': 'boot-1', 'run_id': 'run-1', 'epoch': 'e' * 32,
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'capture'
            output.mkdir()
            (output / 'metadata.json').write_text(json.dumps(capture))
            (output / 'instance-owner.json').write_text(json.dumps(owner))
            result = {'run_id': 'run-1', 'epoch': 'e' * 32, 'boot_id': 'boot-1',
                      'collector': collector, 'owners': owners}
            _record_collector_capture(Path(temp), result)
        self.assertEqual(result['capture'], capture)
        self.assertFalse(result['capture']['complete'])
        self.assertEqual(result['capture']['errors'], ['post-capture proof failed'])
        self.assertNotIn('collector_cleanup_error', result)

    def test_collector_metadata_identity_mismatch_is_rejected(self):
        capture = {
            'schema': 'wksim.private-tracefs.v1', 'run_id': 'run-1', 'epoch': 'e' * 32,
            'instance': '/sys/kernel/tracing/instances/wksim-rate-one',
            'instance_inode': [1, 2], 'collector_pid': 99, 'collector_start_ticks': 199,
            'owners': {}, 'complete': False, 'instance_removed': True, 'errors': [],
        }
        owner = {
            'schema': 'wksim.private-tracefs.instance-owner.v1',
            'instance': capture['instance'], 'instance_inode': capture['instance_inode'],
            'collector_pid': 98, 'collector_start_ticks': 198,
            'supervisor_pid': 10, 'supervisor_start_ticks': 110,
            'owners': {}, 'boot_id': 'boot-1', 'run_id': 'run-1', 'epoch': 'e' * 32,
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'capture'
            output.mkdir()
            (output / 'metadata.json').write_text(json.dumps(capture))
            (output / 'instance-owner.json').write_text(json.dumps(owner))
            result = {'run_id': 'run-1', 'epoch': 'e' * 32, 'boot_id': 'boot-1',
                      'collector': {'pid': 99, 'start_ticks': 199}, 'owners': {}}
            _record_collector_capture(Path(temp), result)
        self.assertEqual(result['capture'], capture)
        self.assertIn('collector_cleanup_error', result)
        self.assertIn('identity', result['collector_cleanup_error'])

    def test_missing_collector_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'capture').mkdir()
            result = {
                'run_id': 'run-1', 'epoch': 'e' * 32, 'boot_id': 'boot-1',
                'collector': {'pid': 99, 'start_ticks': 199}, 'owners': {},
            }
            _record_collector_capture(Path(temp), result)
        self.assertNotIn('capture', result)
        self.assertIn('collector_cleanup_error', result)
        self.assertIn('unavailable', result['collector_cleanup_error'])


if __name__ == '__main__':
    unittest.main()
