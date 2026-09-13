"""ctypes boundary faults without loading or executing a native library."""
import ctypes
from contextlib import ExitStack
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from Simulator.wksim_runtime import perf_capture as module


class FakeLibrary:
    def __init__(self):
        self.start_code = self.stop_code = 0
        self.start_handle = 1234
        self.stop_handle = None
        self.wksim_perf_start = Mock(side_effect=self.start)
        self.wksim_perf_stop = Mock(side_effect=self.stop)
        self.wksim_perf_last_error = Mock(return_value=b'injected failure')

    def start(self, pointer):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0] = self.start_handle
        return self.start_code

    def stop(self, pointer, raw, meta):
        assert isinstance(raw, bytes) and isinstance(meta, bytes)
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0] = self.stop_handle
        return self.stop_code


class PerfCaptureTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.library = self.root / 'reviewed.so'
        self.library.write_bytes(b'fake bytes; never execute')
        self.digest = hashlib.sha256(self.library.read_bytes()).hexdigest()
        self.fake = FakeLibrary()
        self.loader = self.stack.enter_context(patch.object(module.ctypes, 'CDLL', return_value=self.fake))
        self.stack.enter_context(patch.object(module.platform, 'system', return_value='Linux'))
        self.stack.enter_context(patch.object(module.platform, 'release', return_value=module.TESTED_KERNEL_RELEASE))

    def capture(self):
        return module.PerfStreamCapture(self.library, self.digest,
                                       self.root / 'switch.raw', self.root / 'switch.meta.json')

    def test_success_and_exact_pointer_signatures(self):
        capture = self.capture()
        pointer = ctypes.POINTER(ctypes.c_void_p)
        self.assertEqual(self.fake.wksim_perf_start.argtypes, [pointer])
        self.assertEqual(self.fake.wksim_perf_stop.argtypes,
                         [pointer, ctypes.c_char_p, ctypes.c_char_p])
        self.assertIs(self.fake.wksim_perf_stop.restype, ctypes.c_int)
        self.assertIs(self.fake.wksim_perf_last_error.restype, ctypes.c_char_p)
        self.assertEqual(capture.start(), 1234)
        self.assertTrue(capture.owns_handle)
        self.assertEqual(capture.stop(), 0)
        self.assertFalse(capture.owns_handle)
        self.assertTrue(capture.stop_completed)
        self.assertEqual(list(self.root.iterdir()), [self.library])
        with self.assertRaises(module.PerfCaptureError):
            capture.stop()
        with self.assertRaises(module.PerfCaptureError):
            capture.start()
        self.assertEqual(self.fake.wksim_perf_stop.call_count, 1)

    def test_failed_start_retains_handle_for_cleanup_without_valid_capture(self):
        capture = self.capture()
        self.fake.start_code = -1
        with self.assertRaisesRegex(module.PerfCaptureError, 'returned -1; retained=True'):
            capture.start()
        self.assertEqual(capture.handle_value, 1234)
        self.assertEqual(capture.stop(), 0)
        self.assertFalse(capture.owns_handle)
        self.assertFalse(capture.stop_completed)

    def test_failed_start_without_handle_cannot_be_retried(self):
        capture = self.capture()
        self.fake.start_code, self.fake.start_handle = -1, None
        with self.assertRaises(module.PerfCaptureError):
            capture.start()
        with self.assertRaises(module.PerfCaptureError):
            capture.start()
        self.assertEqual(self.fake.wksim_perf_start.call_count, 1)

    def test_failed_stop_is_error_even_after_handle_consumed(self):
        capture = self.capture()
        capture.start()
        self.fake.stop_code = -1
        with self.assertRaisesRegex(module.PerfCaptureError, 'returned -1; retained=False'):
            capture.stop()
        self.assertFalse(capture.owns_handle)
        self.assertFalse(capture.stop_completed)

    def test_failed_stop_retains_library_and_handle_for_owner_retry(self):
        capture = self.capture()
        capture.start()
        self.fake.stop_code, self.fake.stop_handle = -1, 1234
        with self.assertRaises(module.PerfCaptureError):
            capture.stop()
        self.assertTrue(capture.owns_handle)
        self.assertIs(capture._library, self.fake)
        self.fake.stop_code, self.fake.stop_handle = 0, None
        capture.stop()
        self.assertTrue(capture.stop_completed)

    def test_wrong_process_or_thread_never_calls_native(self):
        capture = self.capture()
        for owner in ((capture.owner_pid + 1, capture.owner_tid),
                      (capture.owner_pid, capture.owner_tid + 1)):
            with patch.object(module, '_owner', return_value=owner):
                with self.assertRaises(module.PerfCaptureError):
                    capture.start()
        self.fake.wksim_perf_start.assert_not_called()
        capture.start()
        with patch.object(module, '_owner', return_value=(capture.owner_pid + 1, capture.owner_tid)):
            with self.assertRaises(module.PerfCaptureError):
                capture.stop()
        self.fake.wksim_perf_stop.assert_not_called()
        capture.stop()

    def test_hash_kernel_and_existing_output_refuse_before_loading(self):
        self.digest = '0' * 64
        with self.assertRaises(module.PerfCaptureError):
            self.capture()
        self.digest = hashlib.sha256(self.library.read_bytes()).hexdigest()
        with patch.object(module.platform, 'release', return_value='unreviewed'):
            with self.assertRaises(module.PerfCaptureError):
                self.capture()
        (self.root / 'switch.raw').write_bytes(b'preserve')
        with self.assertRaises(module.PerfCaptureError):
            self.capture()
        self.loader.assert_not_called()

    def test_output_created_after_start_does_not_bypass_native_cleanup(self):
        capture = self.capture()
        capture.start()
        (self.root / 'switch.raw').write_bytes(b'preserve')
        self.fake.stop_code = -1
        with self.assertRaises(module.PerfCaptureError):
            capture.stop()
        self.fake.wksim_perf_stop.assert_called_once()
        self.assertFalse(capture.owns_handle)
        self.assertEqual((self.root / 'switch.raw').read_bytes(), b'preserve')

    def test_impossible_success_handle_states_are_rejected(self):
        capture = self.capture()
        self.fake.start_handle = None
        with self.assertRaisesRegex(module.PerfCaptureError, 'NULL'):
            capture.start()
        capture = self.capture()
        self.fake.start_handle = self.fake.stop_handle = 1234
        capture.start()
        with self.assertRaisesRegex(module.PerfCaptureError, 'retained'):
            capture.stop()
        self.assertTrue(capture.owns_handle)
        self.assertFalse(capture.stop_completed)


if __name__ == '__main__':
    unittest.main()
