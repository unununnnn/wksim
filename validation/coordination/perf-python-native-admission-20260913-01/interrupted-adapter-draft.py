"""ctypes lifecycle adapter for the diagnostic self-thread switch stream recorder.

Implements only the calling side of docs/coordination/perf-stream-contract-20260913.md,
against the accepted C API in validation/coordination/ds-perf-stream-recorder-20260913-01:

    int         wksim_perf_start(void **handle);
    int         wksim_perf_stop(void **handle, const char *raw_path, const char *meta_path);
    const char *wksim_perf_last_error(void);

Scope and limits:

* the caller supplies the library path and the exact SHA256 of the reviewed C build;
  both are validated before ctypes.CDLL is called, so an unreviewed library is never
  loaded. The tested kernel release is required to match exactly;
* the output directory must already exist. Raw and metadata files are created only by
  the C stop() call, with exclusive creation; this adapter never creates or writes a
  capture file and refuses paths that already exist;
* start() and stop() are explicit and must run on the same thread that start() ran on.
  The original owner pid and native tid are recorded at start. There is no destructor,
  context manager or per-group callback magic, and no implicit cleanup: a failed start
  or a failed stop that retains a non-NULL handle keeps that handle observable so the
  owner can decide to retry stop();
* any nonzero C return is a failure even if the handle was cleared. stop() raises with
  the C return code and the native last_error text, and never silently discards them;
* raw bytes and metadata are not parsed and completeness is not certified here. The
  independent consumer (--require-kernel-counter) and the main launcher's hash sealing
  own those claims.

Dependencies: ctypes and the standard library only.
"""
import ctypes
import hashlib
import hmac
import os
import platform
import re

TESTED_KERNEL_RELEASE = '6.6.87.2-microsoft-standard-WSL2'
_DIGEST_RE = re.compile(r'\A[0-9a-f]{64}\Z')
_c_void_p = ctypes.c_void_p
_c_char_p = ctypes.c_char_p
_c_int = ctypes.c_int


class PerfCaptureError(Exception):
    """Base class for every refusal from this adapter."""


class PerfCapturePreconditionError(PerfCaptureError):
    """A precondition failed before the native library was loaded or called."""


class PerfCaptureLifecycleError(PerfCaptureError):
    """A native call failed, or the owned handle state refuses the operation."""


def _cdll(path):
    """Load hook. Tests replace this; production always loads the given path."""
    return ctypes.CDLL(path)


def _kernel_release():
    """Read the running kernel release string."""
    return platform.release()


def _native_thread_id():
    """Read this thread's native tid without a syscall (Linux /proc/thread-self)."""
    target = os.readlink('/proc/thread-self')
    return int(os.path.basename(target.rstrip('/')))


def _read_digest(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _require_library(path, expected_sha256):
    if not isinstance(path, str) or not path:
        raise PerfCapturePreconditionError('library path must be a non-empty string')
    if not os.path.isabs(path):
        raise PerfCapturePreconditionError('library path must be absolute: %r' % (path,))
    if not path.endswith('.so'):
        raise PerfCapturePreconditionError('library path must be a .so file: %r' % (path,))
    if not os.path.isfile(path):
        raise PerfCapturePreconditionError('library path is not an existing file: %r' % (path,))
    if not isinstance(expected_sha256, str) or not _DIGEST_RE.match(expected_sha256.lower()):
        raise PerfCapturePreconditionError('expected sha256 must be 64 hex characters')
    actual = _read_digest(path)
    if not hmac.compare_digest(actual, expected_sha256.lower()):
        raise PerfCapturePreconditionError(
            'library sha256 mismatch: expected %s, actual %s' % (expected_sha256.lower(), actual))
    return actual


def _require_kernel(release):
    if release != TESTED_KERNEL_RELEASE:
        raise PerfCapturePreconditionError(
            'kernel %r is not the tested release %r' % (release, TESTED_KERNEL_RELEASE))


def _require_output_paths(raw_path, meta_path):
    paths = []
    for label, path in (('raw', raw_path), ('meta', meta_path)):
        if not isinstance(path, str) or not path:
            raise PerfCapturePreconditionError('%s path must be a non-empty string' % (label,))
        if not os.path.isabs(path):
            raise PerfCapturePreconditionError('%s path must be absolute: %r' % (label, path))
        if os.path.exists(path):
            raise PerfCapturePreconditionError('%s path already exists: %r' % (label, path))
        paths.append(os.path.dirname(path))
    for directory in paths:
        if not os.path.isdir(directory):
            raise PerfCapturePreconditionError(
                'output directory does not exist: %r' % (directory,))
        if not os.access(directory, os.W_OK | os.X_OK):
            raise PerfCapturePreconditionError(
                'output directory is not writable: %r' % (directory,))
    if os.path.abspath(raw_path) == os.path.abspath(meta_path):
        raise PerfCapturePreconditionError('raw and meta paths must differ')
    return os.path.abspath(raw_path), os.path.abspath(meta_path)


class PerfStreamCapture(object):
    """One lifecycle: validate, load, start() on the owner thread, stop() on it.

    ``owns_handle`` is the ownership state the caller's finally path needs: it is true
    whenever a native handle is still held, including after a failed start or a failed
    stop, in which case the owner may call stop() again to attempt cleanup.
    """

    def __init__(self, library_path, library_sha256, raw_path, meta_path):
        self.library_path = library_path
        self.library_sha256 = library_sha256
        self.raw_path = raw_path
        self.meta_path = meta_path
        _require_kernel(_kernel_release())
        self._sha256 = _require_library(library_path, library_sha256)
        self._raw_path, self._meta_path = _require_output_paths(raw_path, meta_path)
        self.owner_pid = os.getpid()
        self.owner_tid = _native_thread_id()
        self._library = _cdll(library_path)
        self._bind()
        self._handle = None
        self._started = False
        self._stop_ok = False

    def _bind(self):
        library = self._library
        names = ('wksim_perf_start', 'wksim_perf_stop', 'wksim_perf_last_error')
        missing = [name for name in names if not hasattr(library, name)]
        if missing:
            raise PerfCapturePreconditionError(
                'library is missing required symbol(s): %s' % (', '.join(missing),))
        start, stop, last_error = (getattr(library, name) for name in names)
        expected = ((start, [_c_void_p], _c_int),
                    (stop, [_c_void_p, _c_char_p, _c_char_p], _c_int),
                    (last_error, [], _c_char_p))
        for function, argtypes, restype in expected:
            function.argtypes = argtypes
            function.restype = restype
        for function, argtypes, restype in expected:
            if list(function.argtypes) != argtypes or function.restype is not restype:
                raise PerfCapturePreconditionError(
                    'ctypes signature binding did not take for %r' % (function,))
        self._start = start
        self._stop = stop
        self._last_error = last_error

    @property
    def owns_handle(self):
        return self._handle is not None

    @property
    def handle_value(self):
        return None if self._handle is None else int(self._handle)

    @property
    def stop_completed(self):
        return self._stop_ok

    def _last_error_text(self):
        text = self._last_error()
        if text is None:
            return ''
        return text.decode('utf-8', 'replace') if isinstance(text, bytes) else str(text)

    def _fail(self, operation, code):
        return PerfCaptureLifecycleError(
            '%s failed: return code %r, last_error=%r' % (operation, code, self._last_error_text()))

    def _same_owner_thread(self):
        return _native_thread_id() == self.owner_tid

    def start(self):
        """Begin the capture. Sets self.owns_handle on success."""
        if self._handle is not None or self._started or self._stop_ok:
            raise PerfCaptureLifecycleError(
                'start refused: this owner already holds a handle or has completed a capture')
        if not self._same_owner_thread():
            raise PerfCaptureLifecycleError(
                'start refused: calling thread is not the owner thread %d' % (self.owner_tid,))
        handle = _c_void_p(None)
        code = self._start(ctypes.byref(handle))
        # Ownership is read from the caller's pointer on every path, success or not.
        self._handle = handle if handle.value else None
        if code != 0:
            detail = ' (handle retained for cleanup retry)' if self._handle is not None else ''
            raise self._fail('wksim_perf_start' + detail, code)
        if self._handle is None:
            raise PerfCaptureLifecycleError(
                'wksim_perf_start returned 0 with a NULL handle: last_error=%r'
                % (self._last_error_text(),))
        self._started = True
        return self.handle_value

    def stop(self):
        """End the capture and let C write raw/meta exclusively.

        Returns the native return code 0. Raises PerfCaptureLifecycleError with the
        native code and last_error on any nonzero return, keeping the handle whenever
        C retained it so the owner can retry.
        """
        if self._handle is None:
            raise PerfCaptureLifecycleError('stop refused: this owner holds no handle')
        if self._stop_ok:
            raise PerfCaptureLifecycleError('stop refused: this capture already stopped')
        if not self._same_owner_thread():
            raise PerfCaptureLifecycleError(
                'stop refused before the native call: calling thread is not the owner thread %d'
                % (self.owner_tid,))
        code = self._stop(ctypes.byref(self._handle), self._raw_path.encode('utf-8'),
                          self._meta_path.encode('utf-8'))
        # A nonzero return is a failure even when C cleared the handle; a retained handle
        # stays observable so the owner may retry. A zero return with a live handle is a
        # contradiction and is not accepted.
        retained = self._handle.value if self._handle is not None else None
        self._handle = self._handle if retained else None
        if code != 0:
            detail = ' (handle retained for cleanup retry)' if retained else ' (handle consumed)'
            raise self._fail('wksim_perf_stop' + detail, code)
        if retained:
            raise PerfCaptureLifecycleError(
                'wksim_perf_stop returned 0 while the handle is still non-NULL: '
                'last_error=%r' % (self._last_error_text(),))
        self._handle = None
        self._stop_ok = True
        return 0
