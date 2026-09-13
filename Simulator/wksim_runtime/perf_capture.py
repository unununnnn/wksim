"""Explicit owner-thread ctypes calls for the diagnostic perf recorder.

The launcher owns provenance, finally-path cleanup and independent raw validation.
A live handle after an error remains owned by this object. No destructor stops it.
Successful stop alone never certifies capture completeness.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import platform
import threading

TESTED_KERNEL_RELEASE = '6.6.87.2-microsoft-standard-WSL2'


class PerfCaptureError(RuntimeError):
    pass


def _owner():
    return os.getpid(), threading.get_native_id()


class PerfStreamCapture:
    def __init__(self, library_path, library_sha256, raw_path, meta_path):
        if platform.system() != 'Linux' or platform.release() != TESTED_KERNEL_RELEASE:
            raise PerfCaptureError('Perf capture requires the reviewed Linux kernel')
        library = Path(library_path)
        if not library.is_absolute() or library.suffix != '.so' or not library.is_file():
            raise PerfCaptureError('An existing absolute .so path is required')
        if (not isinstance(library_sha256, str) or len(library_sha256) != 64
                or any(c not in '0123456789abcdef' for c in library_sha256)):
            raise PerfCaptureError('An exact lowercase SHA256 is required')
        digest = hashlib.sha256()
        with library.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != library_sha256:
            raise PerfCaptureError('Perf library SHA256 mismatch')
        outputs = tuple(Path(p) for p in (raw_path, meta_path))
        for path in outputs:
            if not path.is_absolute() or not path.parent.is_dir() or os.path.lexists(path):
                raise PerfCaptureError('Outputs must be absent in existing absolute directories')
        if outputs[0].resolve() == outputs[1].resolve():
            raise PerfCaptureError('Raw and metadata paths must differ')
        self.library_path = str(library)
        self.library_sha256 = library_sha256
        self.raw_path, self.meta_path = map(str, outputs)
        self.owner_pid, self.owner_tid = _owner()
        self._library = ctypes.CDLL(str(library), use_errno=True)
        pointer = ctypes.POINTER(ctypes.c_void_p)
        self._start = self._library.wksim_perf_start
        self._start.argtypes = [pointer]
        self._start.restype = ctypes.c_int
        self._stop = self._library.wksim_perf_stop
        self._stop.argtypes = [pointer, ctypes.c_char_p, ctypes.c_char_p]
        self._stop.restype = ctypes.c_int
        self._last_error = self._library.wksim_perf_last_error
        self._last_error.argtypes = []
        self._last_error.restype = ctypes.c_char_p
        self._handle = ctypes.c_void_p()
        self._attempted = self._start_ok = self._stop_ok = False

    @property
    def owns_handle(self):
        return self._handle.value is not None

    @property
    def handle_value(self):
        return self._handle.value

    @property
    def stop_completed(self):
        """True only after successful start and successful, consuming stop."""
        return self._stop_ok

    def _check_owner(self):
        if _owner() != (self.owner_pid, self.owner_tid):
            raise PerfCaptureError('Perf operation requires the original process and native thread')

    def _failure(self, operation, code):
        message = self._last_error()
        detail = message.decode('utf-8', errors='replace') if message else ''
        return PerfCaptureError(f'{operation} returned {code}; retained={self.owns_handle}; {detail}')

    def start(self):
        self._check_owner()
        if self._attempted:
            raise PerfCaptureError('A capture object permits only one start attempt')
        if any(os.path.lexists(p) for p in (self.raw_path, self.meta_path)):
            raise PerfCaptureError('A capture output appeared before start')
        self._attempted = True
        code = self._start(ctypes.byref(self._handle))
        if code != 0:
            raise self._failure('wksim_perf_start', code)
        if not self.owns_handle:
            raise PerfCaptureError('Successful start returned a NULL handle')
        self._start_ok = True
        return self.handle_value

    def stop(self):
        self._check_owner()
        if not self.owns_handle:
            raise PerfCaptureError('No live perf handle to stop')
        # Existing outputs must not prevent C from disabling and cleaning up.
        code = self._stop(ctypes.byref(self._handle), os.fsencode(self.raw_path),
                          os.fsencode(self.meta_path))
        if code != 0:
            raise self._failure('wksim_perf_stop', code)
        if self.owns_handle:
            raise PerfCaptureError('Successful stop retained a live handle')
        self._stop_ok = self._start_ok
        return 0
