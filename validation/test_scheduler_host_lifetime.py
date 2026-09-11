"""Host EOF, deferred signals and owned preflight cleanup; no SITL or tracefs."""
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock

from tools.profile_joint_scheduler import (
    check_host_cancelled, install_cleanup_signal_handlers,
    restore_cleanup_signal_handlers, run, wait_owned_process, watch_host_input,
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
