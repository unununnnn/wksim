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
    retire_manager,
    restore_cleanup_signal_handlers, run, run_owned_preflight,
    wait_owned_process, watch_host_input,
)

ROOT = Path(__file__).resolve().parents[1]


class SchedulerHostLifetimeTests(unittest.TestCase):
    def test_host_eof_emits_exactly_one_shutdown_notification(self):
        called = threading.Event()
        callback = Mock(side_effect=called.set)
        stopped = watch_host_input(io.BytesIO(b'ignored host bytes'), callback)
        self.assertTrue(called.wait(1))
        callback.assert_called_once_with()
        stopped.set()

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


if __name__ == '__main__':
    unittest.main()
