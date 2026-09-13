"""Offline adapter tests for the wksim#84 native release-wait candidate.

These tests inject a fake library and prove ONLY the Python adapter contract:
pinning, platform, absolute-path resolution before hash/load, argument and
native-contract checks. They never inspect the C source (no string matching
against it): they are not evidence of C semantics or overhead, which requires
the isolated microbenchmark on the real compiled library, run separately by
the coordinator.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from tools import native_release_wait as nrw


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class FakeLibrary:
    """Mimics the native contract: observed time is never before deadline."""

    def __init__(self, status=0, skew_ns=7):
        def wait(deadline, observed_ptr):
            observed_ptr._obj.value = deadline + skew_ns
            return status
        self.wk_release_wait_until = FakeFunction(wait)


def _good_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NativeReleaseWaitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        # Pre-resolved so str(self.library) equals the canonical absolute path
        # the adapter must hand to the loader.
        self.library = (Path(self.directory.name)
                        / "native_release_wait.so").resolve()
        self.library.write_bytes(b"fake-shared-object")

    def bind(self, library=None, status=0, skew_ns=7, **kwargs):
        loaded = []
        library = FakeLibrary(status, skew_ns) if library is None else library

        def loader(path):
            loaded.append(path)
            return library

        wait = nrw.bind(self.library, _good_sha(self.library),
                        loader=loader, platform="linux", **kwargs)
        return wait, library, loaded

    def test_compile_argv_is_real_but_never_executed(self):
        argv = nrw.compile_argv("cc")
        self.assertEqual(argv[0], "cc")
        for flag in ("-O2", "-fPIC", "-shared", "-std=c11"):
            self.assertIn(flag, argv)
        self.assertIn("-o", argv)
        self.assertTrue(argv[-1].endswith("native_release_wait.c"))

    def test_rejects_non_linux(self):
        for platform in ("win32", "darwin"):
            with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                        "Linux-only"):
                nrw.bind(self.library, _good_sha(self.library),
                         loader=lambda path: FakeLibrary(), platform=platform)

    def test_rejects_missing_library(self):
        with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                    "library missing"):
            nrw.bind(self.library.with_name("absent.so"), "ab" * 32,
                     loader=lambda path: FakeLibrary(), platform="linux")

    def test_rejects_malformed_expected_sha(self):
        for bad in ("zz" * 32, "AB" * 32, "abc", 1234, None):
            with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                        "64-character lowercase hex"):
                nrw.bind(self.library, bad, loader=lambda path: FakeLibrary(),
                         platform="linux")

    def test_rejects_sha_mismatch_without_loading(self):
        calls = []
        with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                    "SHA-256 mismatch"):
            nrw.bind(self.library, "00" * 32,
                     loader=lambda path: calls.append(path) or FakeLibrary(),
                     platform="linux")
        self.assertEqual(calls, [])

    def test_bare_relative_filename_resolved_before_hash_and_load(self):
        # A bare filename handed to the dynamic loader would trigger a search
        # of standard locations, possibly loading a different file than the
        # one hashed; the adapter must resolve first and load that same path.
        previous_cwd = os.getcwd()
        os.chdir(self.directory.name)
        try:
            loaded = []
            wait = nrw.bind(Path("native_release_wait.so"),  # bare relative name
                            _good_sha(self.library),
                            loader=lambda path: loaded.append(path) or FakeLibrary(),
                            platform="linux")
        finally:
            os.chdir(previous_cwd)
        self.assertEqual(loaded, [str(self.library)])  # absolute canonical path
        self.assertTrue(Path(loaded[0]).is_absolute())
        self.assertEqual(wait(42), 49)  # sha was checked on that same file

    def test_relative_path_with_dotdot_canonicalized_before_load(self):
        sub = Path(self.directory.name) / "sub"
        sub.mkdir()
        target = (sub / "wait.so").resolve()
        target.write_bytes(b"other-fake-shared-object")
        previous_cwd = os.getcwd()
        os.chdir(self.directory.name)
        try:
            loaded = []
            nrw.bind(Path("sub/../sub/wait.so"),  # relative, non-canonical
                     _good_sha(target),
                     loader=lambda path: loaded.append(path) or FakeLibrary(),
                     platform="linux")
        finally:
            os.chdir(previous_cwd)
        self.assertEqual(loaded, [str(target)])  # canonical, not the spelling
        self.assertNotIn("..", loaded[0])
        self.assertTrue(Path(loaded[0]).is_absolute())

    def test_binds_int64_signature_and_returns_observed(self):
        wait, library, loaded = self.bind()
        self.assertEqual(loaded, [str(self.library)])
        function = library.wk_release_wait_until
        self.assertEqual(function.argtypes,
                         [ctypes.c_int64, ctypes.POINTER(ctypes.c_int64)])
        self.assertIs(function.restype, ctypes.c_int)
        self.assertEqual(wait(1_000_000_000), 1_000_000_007)

    def test_rejects_non_int_and_bool_deadline(self):
        wait, _, _ = self.bind()
        for bad in (True, False, 1.5, "1000", None):
            with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                        "must be an int"):
                wait(bad)

    def test_rejects_out_of_range_deadline(self):
        wait, _, _ = self.bind()
        for bad in (-1, nrw.INT64_MAX + 1):
            with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                        "outside int64 range"):
                wait(bad)
        self.assertEqual(wait(0), 7)
        high, _, _ = self.bind(skew_ns=0)
        self.assertEqual(high(nrw.INT64_MAX), nrw.INT64_MAX)

    def test_maps_native_status_codes_to_named_errors(self):
        for status, name in ((1, "invalid_argument"), (2, "clock_failure"),
                             (3, "clock_regressed"),
                             (4, "deadline_out_of_range")):
            wait, _, _ = self.bind(status=status)
            with self.assertRaisesRegex(nrw.NativeReleaseWaitError, name):
                wait(42)

    def test_unknown_native_status_is_an_error(self):
        wait, _, _ = self.bind(status=99)
        with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                    "unknown_status_99"):
            wait(42)

    def test_rejects_native_observed_time_before_deadline(self):
        wait, _, _ = self.bind(skew_ns=-1)
        with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                    "precedes deadline"):
            wait(42)

    def test_rejects_library_without_symbol(self):
        with self.assertRaisesRegex(nrw.NativeReleaseWaitError,
                                    "lacks wk_release_wait_until"):
            self.bind(library=object())


if __name__ == "__main__":
    unittest.main()
