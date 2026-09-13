"""Thin loader for the wksim#84 CPython extension candidate.

Verifies a caller-supplied local absolute extension path by SHA-256, imports it
under the fixed module name ``_wksim_release_wait_native`` (never derived from
the file name, so no collision with this loader or the ctypes adapter),
validates exported metadata, and returns the C ``wait_until`` callable
directly — no per-call Python wrapper. Linux + CPython 3.10 only. ``loader``
is injectable for pure adapter tests; fake-module tests prove nothing about C
semantics or overhead. Never compiles, searches, or auto-loads anything.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

MODULE_NAME = "_wksim_release_wait_native"
EXT_SUFFIX = ".cpython-310-x86_64-linux-gnu.so"
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
SOURCES = (Path(__file__).with_suffix(".c"),
           Path(__file__).with_name("native_release_wait.c"))


class ReleaseWaitExtensionError(RuntimeError):
    """Raised for any loader or module-metadata failure; never succeeds early."""


def compile_argv(compiler="cc"):
    """Real compile argv for the candidate. Returned, never executed here."""
    return [compiler, "-O2", "-fPIC", "-shared", "-std=c11",
            "-Wall", "-Wextra", "-Werror", "-I/usr/include/python3.10",
            "-o", MODULE_NAME + EXT_SUFFIX,
            str(SOURCES[0]), str(SOURCES[1])]


def _default_loader(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReleaseWaitExtensionError(f"cannot create import spec: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError) as error:
        raise ReleaseWaitExtensionError(f"extension import failed: {error}") \
            from error
    return module


def load(library_path, expected_sha256, *, loader=None, platform=None,
         implementation=None, version_info=None):
    """Load the pinned extension and return its ``wait_until`` C callable."""
    platform = sys.platform if platform is None else platform
    implementation = (sys.implementation.name if implementation is None
                      else implementation)
    version_info = sys.version_info if version_info is None else version_info
    if platform != "linux" or implementation != "cpython" \
            or tuple(version_info[:2]) != (3, 10):
        raise ReleaseWaitExtensionError(
            "release wait extension requires Linux CPython 3.10")
    if type(expected_sha256) is not str or not SHA256_HEX.fullmatch(
            expected_sha256):
        raise ReleaseWaitExtensionError(
            "expected_sha256 must be a 64-character lowercase hex digest")

    path = Path(library_path)
    if not path.is_absolute():
        raise ReleaseWaitExtensionError("library_path must be absolute")
    if not path.name.endswith(EXT_SUFFIX):
        raise ReleaseWaitExtensionError(
            f"extension file name must end with {EXT_SUFFIX}")
    if not path.is_file():
        raise ReleaseWaitExtensionError(f"extension missing: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ReleaseWaitExtensionError(f"extension SHA-256 mismatch: {path}")

    module = (loader or _default_loader)(MODULE_NAME, str(path))
    compiled_version = getattr(module, "PYTHON_VERSION", None)
    if getattr(module, "CLOCK_DOMAIN", None) != "CLOCK_MONOTONIC" \
            or getattr(module, "SPIN_LIMIT_NS", None) != 1_000_000 \
            or type(compiled_version) is not str \
            or not re.fullmatch(r"3\.10\.\d+(?:[a-zA-Z0-9.+-]*)?", compiled_version):
        raise ReleaseWaitExtensionError(
            "extension metadata mismatch: clock domain, spin limit or "
            "compiled Python version")
    wait_until = getattr(module, "wait_until", None)
    if not callable(wait_until):
        raise ReleaseWaitExtensionError("extension lacks callable wait_until")
    return wait_until
