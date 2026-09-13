"""Offline loader tests for the wksim#84 CPython extension candidate.

A fake module is injected via ``loader``; these tests prove ONLY the loader
contract (runtime gating, absolute path, SHA pinning, fixed module name,
metadata validation, direct-callable return). They are not evidence of C
semantics or overhead; the coordinator compiles and runs the full-path
microbenchmark separately.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from tools import native_release_wait_extension as ext


LINUX_CPYTHON = dict(platform="linux", implementation="cpython",
                     version_info=(3, 10, 12))


def fake_module(**overrides):
    values = dict(CLOCK_DOMAIN="CLOCK_MONOTONIC", SPIN_LIMIT_NS=1_000_000,
                  PYTHON_VERSION="3.10.12",
                  wait_until=lambda deadline: deadline + 7)
    values.update(overrides)
    return SimpleNamespace(**values)


class ReleaseWaitExtensionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.library = Path(self.directory.name).resolve() / (
            ext.MODULE_NAME + ext.EXT_SUFFIX)
        self.library.write_bytes(b"fake-extension-object")
        self.sha = hashlib.sha256(self.library.read_bytes()).hexdigest()

    def load(self, module=None, **kwargs):
        calls = []

        def loader(name, path):
            calls.append((name, path))
            return fake_module() if module is None else module

        options = {**LINUX_CPYTHON, "loader": loader, **kwargs}
        return ext.load(self.library, self.sha, **options), calls

    def test_compile_argv_is_real_but_never_executed(self):
        argv = ext.compile_argv("cc")
        self.assertEqual(argv[0], "cc")
        for flag in ("-O2", "-fPIC", "-shared", "-std=c11",
                     "-I/usr/include/python3.10"):
            self.assertIn(flag, argv)
        output = argv[argv.index("-o") + 1]
        self.assertEqual(output, ext.MODULE_NAME + ext.EXT_SUFFIX)
        sources = argv[argv.index("-o") + 2:]
        self.assertEqual([Path(s).name for s in sources],
                         ["native_release_wait_extension.c",
                          "native_release_wait.c"])

    def test_rejects_unsupported_runtime(self):
        for overrides in (dict(platform="win32"), dict(platform="darwin"),
                          dict(implementation="pypy"),
                          dict(version_info=(3, 11, 0))):
            with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                        "Linux CPython 3.10"):
                self.load(**{**LINUX_CPYTHON, **overrides})

    def test_rejects_relative_path(self):
        with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                    "must be absolute"):
            ext.load("relative/name" + ext.EXT_SUFFIX, self.sha,
                     loader=lambda name, path: fake_module(), **LINUX_CPYTHON)

    def test_rejects_wrong_suffix(self):
        wrong = self.library.with_name("wrong_name.dll")
        wrong.write_bytes(b"x")
        with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                    "must end with"):
            ext.load(wrong, "ab" * 32, loader=lambda name, path: fake_module(),
                     **LINUX_CPYTHON)

    def test_rejects_missing_extension(self):
        with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                    "extension missing"):
            ext.load(self.library.with_name("absent" + ext.EXT_SUFFIX),
                     "ab" * 32, loader=lambda name, path: fake_module(),
                     **LINUX_CPYTHON)

    def test_rejects_malformed_expected_sha(self):
        for bad in ("zz" * 32, "AB" * 32, "abc", 1234, None):
            with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                        "64-character lowercase hex"):
                ext.load(self.library, bad,
                         loader=lambda name, path: fake_module(),
                         **LINUX_CPYTHON)

    def test_rejects_sha_mismatch_without_loading(self):
        calls = []
        with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                    "SHA-256 mismatch"):
            ext.load(self.library, "00" * 32,
                     loader=lambda name, path: calls.append((name, path))
                     or fake_module(), **LINUX_CPYTHON)
        self.assertEqual(calls, [])

    def test_returns_c_callable_directly_with_fixed_module_name(self):
        module = fake_module()
        wait_until, calls = self.load(module)
        self.assertEqual(calls, [(ext.MODULE_NAME, str(self.library))])
        self.assertIs(wait_until, module.wait_until)

    def test_rejects_metadata_mismatch(self):
        for overrides in (dict(CLOCK_DOMAIN="CLOCK_REALTIME"),
                          dict(SPIN_LIMIT_NS=2_000_000),
                          dict(PYTHON_VERSION="3.11.0"),
                          dict(PYTHON_VERSION="3.100.0"),
                          dict(PYTHON_VERSION="3.10wrong"),
                          dict(PYTHON_VERSION=3.10)):
            with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                        "metadata mismatch"):
                self.load(fake_module(**overrides))

    def test_rejects_module_without_callable_entry(self):
        with self.assertRaisesRegex(ext.ReleaseWaitExtensionError,
                                    "lacks callable wait_until"):
            self.load(fake_module(wait_until=None))


if __name__ == "__main__":
    unittest.main()
