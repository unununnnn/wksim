"""SHA-pinned ctypes adapter for the wksim#84 native release-wait candidate.

Not wired into production pacing. This module never compiles, searches for, or
auto-loads anything: ``bind`` resolves the caller-supplied library path to an
absolute canonical path FIRST, then hashes and loads that same path (a relative
or bare filename handed to the dynamic loader could make it search for and load
a different file than the one hashed). Loading requires the SHA-256 of the
resolved file to match the caller-supplied digest, on Linux only, with an
explicit int64 ctypes signature. ``loader`` is injectable so adapter behavior
can be tested with a fake library; fake-library tests prove nothing about C
semantics or overhead.
"""
from __future__ import annotations

import ctypes
import hashlib
import re
import sys
from pathlib import Path

SOURCE = Path(__file__).with_suffix(".c")
SYMBOL = "wk_release_wait_until"
INT64_MAX = (1 << 63) - 1
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
STATUS_NAMES = {
    0: "ok",
    1: "invalid_argument",
    2: "clock_failure",
    3: "clock_regressed",
    4: "deadline_out_of_range",
}


class NativeReleaseWaitError(RuntimeError):
    """Raised for any adapter or native-contract failure; never succeeds early."""


def compile_argv(compiler="cc"):
    """Real compile argv for the candidate. Returned, never executed here."""
    return [compiler, "-O2", "-fPIC", "-shared", "-std=c11",
            "-Wall", "-Wextra", "-Werror",
            "-o", "libwksim_release_wait.so", str(SOURCE)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(library_path, expected_sha256, *, loader=ctypes.CDLL, platform=None):
    """Load the pinned library and return a ``wait_until(deadline_ns) -> int``.

    ``deadline_ns`` must be a plain int within [0, INT64_MAX]; bools are
    rejected. ``library_path`` is resolved to an absolute canonical path
    before anything else; the SHA-256 check and the loader both use that
    same resolved path, preventing a basename search in other directories.
    The returned value is the
    CLOCK_MONOTONIC time observed by the native side, guaranteed by
    contract (and re-checked here) to be at or after the deadline.
    """
    platform = sys.platform if platform is None else platform
    if platform != "linux":
        raise NativeReleaseWaitError(
            f"native release wait is Linux-only, not {platform!r}")
    if type(expected_sha256) is not str or not SHA256_HEX.fullmatch(
            expected_sha256):
        raise NativeReleaseWaitError(
            "expected_sha256 must be a 64-character lowercase hex digest")

    # Resolve to an absolute canonical path first; hash and load that SAME
    # path. A relative or bare filename passed to the loader could make the
    # dynamic loader search standard locations and load a different file
    # than the one hashed (or break if the CWD changes in between).
    path = Path(library_path).resolve()
    if not path.is_file():
        raise NativeReleaseWaitError(f"library missing: {path}")
    if _sha256(path) != expected_sha256:
        raise NativeReleaseWaitError(f"library SHA-256 mismatch: {path}")

    try:
        library = loader(str(path))
        function = getattr(library, SYMBOL)
    except (OSError, AttributeError) as error:
        raise NativeReleaseWaitError(
            f"library lacks {SYMBOL} or cannot load: {error}") from error
    function.argtypes = [ctypes.c_int64, ctypes.POINTER(ctypes.c_int64)]
    function.restype = ctypes.c_int

    def wait_until(deadline_ns):
        if type(deadline_ns) is not int:
            raise NativeReleaseWaitError("deadline_ns must be an int")
        if deadline_ns < 0 or deadline_ns > INT64_MAX:
            raise NativeReleaseWaitError(
                "deadline_ns outside int64 range [0, 2**63-1]")
        observed = ctypes.c_int64(0)
        status = function(deadline_ns, ctypes.byref(observed))
        if status != 0:
            name = STATUS_NAMES.get(status, f"unknown_status_{status}")
            raise NativeReleaseWaitError(f"native wait failed: {name}")
        value = observed.value
        if value < deadline_ns:
            raise NativeReleaseWaitError(
                "native observed time precedes deadline")
        return value

    return wait_until
