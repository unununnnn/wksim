"""Pure tests for diagnostic perf capture lifecycle in the joint runner."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from tools import run_joint_flight as runner


BOOT_ID = '11111111-2222-4333-8444-555555555555'


class FakeCapture:
    def __init__(self, root, *, stop_error=None, mutate_library=False):
        self.root = Path(root)
        self.raw_path = str(self.root/'perf-switch.raw')
        self.meta_path = str(self.root/'perf-switch.meta.json')
        self.library_path = str(self.root/'recorder.so')
        Path(self.library_path).write_bytes(b'recorder')
        self.library_sha256 = hashlib.sha256(b'recorder').hexdigest()
        self.owner_pid = 101
        self.owner_tid = 102
        self.owns_handle = True
        self.stop_completed = False
        self.stop_error = stop_error
        self.mutate_library = mutate_library

    def start(self):
        return 103

    def stop(self):
        if self.stop_error is not None:
            raise self.stop_error
        raw = b'x'*64
        Path(self.raw_path).write_bytes(raw)
        Path(self.meta_path).write_text(json.dumps(dict(
            schema='wksim.perf_switch_stream.v1',
            boot_id=BOOT_ID,
            owner_pid=self.owner_pid,
            owner_tid=self.owner_tid,
            enable_after_ns=100,
            disable_before_ns=300,
            captured_bytes=len(raw),
        )))
        if self.mutate_library:
            Path(self.library_path).write_bytes(b'changed')
        self.owns_handle = False
        self.stop_completed = True


def marker():
    return dict(requested=True, status='requested', strict_consumer_passed=False)


class PerfCaptureRequestTests(unittest.TestCase):
    def test_requires_a_complete_pair_and_mixed_profile(self):
        good = SimpleNamespace(task_profile=runner.MIXED_PROFILE,
                               perf_library='/tmp/recorder.so',
                               perf_library_sha256='a'*64)
        self.assertEqual(runner.perf_capture_request(good),
                         ('/tmp/recorder.so', 'a'*64))
        for library, checksum in ((None, 'a'*64), ('/tmp/recorder.so', None)):
            with self.subTest(library=library, checksum=checksum):
                args = SimpleNamespace(task_profile=runner.MIXED_PROFILE,
                                       perf_library=library,
                                       perf_library_sha256=checksum)
                with self.assertRaisesRegex(ValueError, 'supplied together'):
                    runner.perf_capture_request(args)
        with self.assertRaisesRegex(ValueError, 'only allowed for the MIXED'):
            runner.perf_capture_request(SimpleNamespace(
                task_profile='position', perf_library='/tmp/recorder.so',
                perf_library_sha256='a'*64))

    def test_absent_pair_keeps_capture_disabled(self):
        self.assertIsNone(runner.perf_capture_request(
            SimpleNamespace(task_profile=runner.MIXED_PROFILE)))

    def test_real_parser_forwards_the_complete_pair(self):
        argv = [
            'run',
            '--control-manifest', 'control.json',
            '--control-sha256', 'c'*64,
            '--ap-mixed-manifest', 'mixed.json',
            '--ap-mixed-sha256', 'm'*64,
            '--task-profile', runner.MIXED_PROFILE,
            '--perf-library', '/tmp/recorder.so',
            '--perf-library-sha256', 'a'*64,
        ]
        with patch.object(runner, 'run', return_value=17) as execute:
            self.assertEqual(runner.main(argv), 17)
        args = execute.call_args.args[0]
        self.assertEqual(args.perf_library, '/tmp/recorder.so')
        self.assertEqual(args.perf_library_sha256, 'a'*64)

    def test_real_parser_rejects_an_incomplete_pair_or_other_profile(self):
        common = [
            'run',
            '--control-manifest', 'control.json',
            '--control-sha256', 'c'*64,
        ]
        cases = (
            common + [
                '--ap-mixed-manifest', 'mixed.json',
                '--ap-mixed-sha256', 'm'*64,
                '--task-profile', runner.MIXED_PROFILE,
                '--perf-library', '/tmp/recorder.so',
            ],
            common + [
                '--ap-manifest', 'ap.json',
                '--ap-sha256', 'p'*64,
                '--perf-library', '/tmp/recorder.so',
                '--perf-library-sha256', 'a'*64,
            ],
        )
        for argv in cases:
            with self.subTest(argv=argv), patch.object(runner, 'run') as execute:
                with self.assertRaises(SystemExit) as error:
                    runner.main(argv)
                self.assertEqual(error.exception.code, 2)
                execute.assert_not_called()


class PerfCaptureLifecycleTests(unittest.TestCase):
    def result(self):
        return dict(status='pass', perf_switch_capture=marker())

    def rate(self):
        return SimpleNamespace(
            last_summary=dict(segment_id=7, anchor=dict(wall_ns=150)),
            last_end=250)

    def test_start_records_the_native_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = FakeCapture(directory)
            value = marker()
            runner.start_perf_capture(capture, value)
            self.assertEqual(value, dict(
                requested=True, status='running', strict_consumer_passed=False,
                owner_pid=101, owner_tid=102, start_handle=103))

    def test_success_seals_outputs_for_an_external_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = FakeCapture(directory)
            result = self.result()
            with patch.object(runner, 'perf_capture_boot_id', return_value=BOOT_ID):
                runner.finalize_perf_capture(result, Path(directory), capture, self.rate())
            self.assertEqual(result['status'], 'pass')
            record = result['perf_switch_capture']
            self.assertEqual(record['status'], 'sealed_for_external_consumer')
            self.assertTrue(record['capture_lifecycle_complete'])
            self.assertFalse(record['strict_consumer_passed'])
            self.assertFalse(record['owns_handle_after'])
            self.assertEqual(record['window'],
                             dict(id='mixed_rate_segment_7', start_ns=150, end_ns=250))
            windows = json.loads((Path(directory)/'perf-windows.json').read_text())
            self.assertEqual(windows['boot_id'], BOOT_ID)
            self.assertEqual(windows['owner_pid'], 101)
            self.assertEqual(windows['owner_tid'], 102)
            self.assertEqual(windows['windows'], [record['window']])
            self.assertEqual(set(record['outputs']), {'raw', 'metadata', 'windows'})

    def test_stop_error_is_retained_without_escaping_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = FakeCapture(directory, stop_error=RuntimeError('stop failed'))
            result = self.result()
            runner.finalize_perf_capture(result, Path(directory), capture, self.rate())
            self.assertEqual(result['status'], 'failed')
            self.assertIn('stop failed', result['perf_switch_capture']['error'])
            self.assertTrue(result['perf_switch_capture']['owns_handle_after'])

    def test_missing_marker_is_synthesized_and_fails_without_escaping(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = FakeCapture(directory)
            result = dict(status='pass')
            runner.finalize_perf_capture(result, Path(directory), capture, self.rate())
            self.assertEqual(result['status'], 'failed')
            record = result['perf_switch_capture']
            self.assertEqual(record['status'], 'failed')
            self.assertFalse(record['capture_lifecycle_complete'])
            self.assertFalse(record['strict_consumer_passed'])
            self.assertIn('marker is missing or malformed', record['error'])

    def test_missing_segment_or_changed_library_fails_closed(self):
        cases = (
            (False, SimpleNamespace(last_summary=None, last_end=None), 'completed MIXED rate segment'),
            (True, self.rate(), 'library changed'),
        )
        for mutate, rate, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                capture = FakeCapture(directory, mutate_library=mutate)
                result = self.result()
                with patch.object(runner, 'perf_capture_boot_id', return_value=BOOT_ID):
                    runner.finalize_perf_capture(result, Path(directory), capture, rate)
                self.assertEqual(result['status'], 'failed')
                self.assertIn(message, result['perf_switch_capture']['error'])

    def test_window_outside_inner_span_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = FakeCapture(directory)
            result = self.result()
            rate = SimpleNamespace(
                last_summary=dict(segment_id=1, anchor=dict(wall_ns=99)),
                last_end=250)
            with patch.object(runner, 'perf_capture_boot_id', return_value=BOOT_ID):
                runner.finalize_perf_capture(result, Path(directory), capture, rate)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('outside the perf capture inner span',
                          result['perf_switch_capture']['error'])


if __name__ == '__main__':
    unittest.main()
