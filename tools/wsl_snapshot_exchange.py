"""Pure data contract and atomic create-only exchange for WSL root task snapshots.

Provides the file-based rendezvous schema and verification routines connecting
the Linux diagnostic collector and the Windows host snapshot engine.

Neither collector nor driver is integrated here, and no FC startup barrier is
introduced. The contract supports two distinct snapshot phases:
  - 'pre_bootstrap_leaders': early snapshot of base roles and FC process leaders
  - 'post_capture_tasks': post-step snapshot of all active tasks/helper threads

Security & Integrity Limitations:
  Unauthenticated local filesystem writes under the same user account cannot
  prevent deliberate tampering by a malicious peer with identical local UID/SID.
  This protocol guarantees crash-consistency, create-only non-overwrite semantics,
  schema conformance, and strict challenge-response binding against cross-request
  replay, duplicate keys, and transmission corruption.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

REQUEST_SCHEMA = "wksim.wsl-snapshot-request.v1"
RESPONSE_SCHEMA = "wksim.wsl-snapshot-response.v1"

VALID_PHASES = frozenset({"pre_bootstrap_leaders", "post_capture_tasks"})
REQUIRED_OWNER_ROLES = frozenset({
    "supervisor",
    "ap_worker",
    "px4_worker",
    "ap_fc",
    "px4_fc",
})


def _reject_constants(val: str) -> None:
    raise ValueError(f"Nonfinite JSON constant rejected: {val}")


def _reject_duplicate_keys(pairs: list[tuple[str, any]]) -> dict[str, any]:
    seen: set[str] = set()
    result: dict[str, any] = {}
    for k, v in pairs:
        if k in seen:
            raise ValueError(f"Duplicate JSON key rejected: {k}")
        seen.add(k)
        result[k] = v
    return result


def decode_json_strict(raw: bytes | str) -> dict[str, any]:
    """Decode JSON strictly, rejecting duplicate keys and nonfinite numbers."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    parsed = json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constants,
    )
    if not isinstance(parsed, dict):
        raise ValueError(f"Top-level JSON entity must be an object, got: {type(parsed).__name__}")
    _validate_finite_recursive(parsed)
    return parsed


def encode_json_strict(val: dict[str, any]) -> bytes:
    """Encode dictionary to formatted UTF-8 bytes, rejecting nonfinites."""
    if not isinstance(val, dict):
        raise ValueError(f"Value to encode must be a dict, got: {type(val).__name__}")
    _validate_finite_recursive(val)
    return (json.dumps(val, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _validate_finite_recursive(item: any) -> None:
    """Ensure no float NaN, Inf, or -Inf exists in nested structures."""
    if isinstance(item, float):
        if not math.isfinite(item):
            raise ValueError(f"Nonfinite float rejected: {item}")
    elif isinstance(item, dict):
        for k, v in item.items():
            if not isinstance(k, str):
                raise ValueError(f"Dict key must be str, got: {type(k).__name__}")
            _validate_finite_recursive(v)
    elif isinstance(item, (list, tuple)):
        for elem in item:
            _validate_finite_recursive(elem)


def is_strict_int(val: any) -> bool:
    """Return True only if val is an int and strictly not a bool."""
    return isinstance(val, int) and not isinstance(val, bool)


def is_strict_pos_int(val: any) -> bool:
    """Return True only if val is an int > 0 and strictly not a bool."""
    return isinstance(val, int) and not isinstance(val, bool) and val > 0


def validate_32_hex(val: any, label: str) -> str:
    """Validate that val is a 32-character lowercase hex string."""
    if not isinstance(val, str) or len(val) != 32 or not re.fullmatch(r"[0-9a-f]{32}", val):
        raise ValueError(f"{label} must be a 32-char lowercase hex string, got: {val!r}")
    return val


def validate_identity_record(identity: any, label: str) -> dict[str, any]:
    """Validate process identity record requiring strictly positive pid and start_ticks."""
    if not isinstance(identity, dict):
        raise ValueError(f"{label} must be a dict, got: {type(identity).__name__}")
    pid = identity.get("pid")
    start_ticks = identity.get("start_ticks")
    if not is_strict_pos_int(pid):
        raise ValueError(f"{label} pid must be a positive int, got: {pid!r}")
    if not is_strict_pos_int(start_ticks):
        raise ValueError(f"{label} start_ticks must be a positive int, got: {start_ticks!r}")
    if "pgid" in identity and not is_strict_pos_int(identity["pgid"]):
        raise ValueError(f"{label} pgid must be a positive int, got: {identity['pgid']!r}")
    if "argv" in identity:
        argv = identity["argv"]
        if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
            raise ValueError(f"{label} argv must be a list of str")
    return identity


def validate_owners_dict(owners: any) -> dict[str, dict[str, any]]:
    """Validate that owners contains exactly the 5 required roles with valid identities."""
    if not isinstance(owners, dict):
        raise ValueError(f"owners must be a dict, got: {type(owners).__name__}")
    observed_roles = set(owners.keys())
    if observed_roles != REQUIRED_OWNER_ROLES:
        missing = sorted(REQUIRED_OWNER_ROLES - observed_roles)
        extra = sorted(observed_roles - REQUIRED_OWNER_ROLES)
        raise ValueError(f"owners roles mismatch. Missing: {missing}, Extra: {extra}")
    validated = {}
    for role, ident in sorted(owners.items()):
        validated[role] = validate_identity_record(ident, f"owner {role}")
    return validated


def make_snapshot_request(
    *,
    run_id: str,
    epoch: str,
    boot_id: str,
    target_pid_ns: int,
    collector: dict[str, any],
    owners: dict[str, dict[str, any]],
    phase: str,
    request_id: str | None = None,
) -> dict[str, any]:
    """Construct a validated WSL snapshot request dictionary."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError(f"run_id must be a non-empty str, got: {run_id!r}")
    epoch_clean = validate_32_hex(epoch, "epoch")
    if not isinstance(boot_id, str) or not boot_id.strip():
        raise ValueError(f"boot_id must be a non-empty str, got: {boot_id!r}")
    req_id = validate_32_hex(request_id or uuid.uuid4().hex, "request_id")
    if not is_strict_pos_int(target_pid_ns):
        raise ValueError(f"target_pid_ns must be a positive int, got: {target_pid_ns!r}")
    if phase not in VALID_PHASES:
        raise ValueError(f"phase must be one of {sorted(VALID_PHASES)}, got: {phase!r}")

    col_clean = validate_identity_record(collector, "collector")
    own_clean = validate_owners_dict(owners)

    return {
        "schema": REQUEST_SCHEMA,
        "run_id": run_id,
        "epoch": epoch_clean,
        "boot_id": boot_id,
        "request_id": req_id,
        "phase": phase,
        "target_pid_ns": target_pid_ns,
        "collector": {
            "pid": col_clean["pid"],
            "start_ticks": col_clean["start_ticks"],
        },
        "owners": own_clean,
    }


def validate_snapshot_request(request: any) -> dict[str, any]:
    """Validate all fields of an unmarshalled snapshot request, failing closed."""
    if not isinstance(request, dict):
        raise ValueError(f"Request must be a dict, got: {type(request).__name__}")
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError(f"Unexpected request schema: {request.get('schema')!r} != {REQUEST_SCHEMA}")

    run_id = request.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError(f"Invalid run_id: {run_id!r}")

    validate_32_hex(request.get("epoch"), "epoch")

    boot_id = request.get("boot_id")
    if not isinstance(boot_id, str) or not boot_id.strip():
        raise ValueError(f"Invalid boot_id: {boot_id!r}")

    validate_32_hex(request.get("request_id"), "request_id")

    phase = request.get("phase")
    if phase not in VALID_PHASES:
        raise ValueError(f"Invalid request phase: {phase!r}")

    target_pid_ns = request.get("target_pid_ns")
    if not is_strict_pos_int(target_pid_ns):
        raise ValueError(f"Invalid target_pid_ns: {target_pid_ns!r}")

    validate_identity_record(request.get("collector"), "collector")
    validate_owners_dict(request.get("owners"))

    _validate_finite_recursive(request)
    return request


def make_snapshot_response(
    *,
    request: dict[str, any],
    request_bytes: bytes,
    boot_id: str,
    snapshot: dict[str, any],
    issued_monotonic_ns: int | None = None,
) -> dict[str, any]:
    """Construct a validated snapshot response bound cryptographically to the request."""
    req_validated = validate_snapshot_request(request)
    if not isinstance(request_bytes, (bytes, bytearray)):
        raise ValueError("request_bytes must be bytes")
    if encode_json_strict(decode_json_strict(bytes(request_bytes))) != encode_json_strict(req_validated):
        raise ValueError("request object differs from bound request bytes")
    actual_req_sha = hashlib.sha256(request_bytes).hexdigest()

    if not isinstance(boot_id, str) or not boot_id.strip():
        raise ValueError(f"boot_id must be a non-empty str, got: {boot_id!r}")
    if not isinstance(snapshot, dict) or not snapshot:
        raise ValueError("snapshot payload must be a non-empty dict")
    snapshot = _snapshot_wire_value(snapshot)
    _validate_finite_recursive(snapshot)

    issued = issued_monotonic_ns if issued_monotonic_ns is not None else time.monotonic_ns()
    if not is_strict_pos_int(issued):
        raise ValueError(f"issued_monotonic_ns must be a positive int, got: {issued!r}")

    return {
        "schema": RESPONSE_SCHEMA,
        "run_id": req_validated["run_id"],
        "epoch": req_validated["epoch"],
        "phase": req_validated["phase"],
        "target_pid_ns": req_validated["target_pid_ns"],
        "request_id": req_validated["request_id"],
        "request_sha256": actual_req_sha,
        "boot_id": boot_id,
        "collector": dict(req_validated["collector"]),
        "snapshot": snapshot,
        "issued_monotonic_ns": issued,
    }


def validate_snapshot_response(response: any) -> dict[str, any]:
    """Validate all fields of an unmarshalled snapshot response, failing closed."""
    if not isinstance(response, dict):
        raise ValueError(f"Response must be a dict, got: {type(response).__name__}")
    if response.get("schema") != RESPONSE_SCHEMA:
        raise ValueError(f"Unexpected response schema: {response.get('schema')!r} != {RESPONSE_SCHEMA}")

    run_id = response.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError(f"Invalid run_id: {run_id!r}")

    validate_32_hex(response.get("epoch"), "epoch")
    validate_32_hex(response.get("request_id"), "request_id")

    phase = response.get("phase")
    if phase not in VALID_PHASES:
        raise ValueError(f"Invalid response phase: {phase!r}")

    target_pid_ns = response.get("target_pid_ns")
    if not is_strict_pos_int(target_pid_ns):
        raise ValueError(f"Invalid target_pid_ns: {target_pid_ns!r}")

    req_sha = response.get("request_sha256")
    if not isinstance(req_sha, str) or len(req_sha) != 64 or not re.fullmatch(r"[0-9a-f]{64}", req_sha):
        raise ValueError(f"Invalid request_sha256: {req_sha!r}")

    boot_id = response.get("boot_id")
    if not isinstance(boot_id, str) or not boot_id.strip():
        raise ValueError(f"Invalid boot_id: {boot_id!r}")

    validate_identity_record(response.get("collector"), "collector")

    snapshot = response.get("snapshot")
    if not isinstance(snapshot, dict) or not snapshot:
        raise ValueError("Invalid snapshot payload: must be non-empty dict")

    issued = response.get("issued_monotonic_ns")
    if not is_strict_pos_int(issued):
        raise ValueError(f"Invalid issued_monotonic_ns: {issued!r}")

    _validate_finite_recursive(response)
    return response


def verify_snapshot_response_binding(
    response: dict[str, any],
    *,
    expected_request: dict[str, any],
    expected_request_bytes: bytes,
    expected_boot_id: str | None = None,
) -> None:
    """Verify that response matches expected request exactly, guarding against replay/tampering."""
    validate_snapshot_request(expected_request)
    if encode_json_strict(decode_json_strict(expected_request_bytes)) != encode_json_strict(expected_request):
        raise ValueError("request object differs from bound request bytes")
    resp = validate_snapshot_response(response)

    expected_sha = hashlib.sha256(expected_request_bytes).hexdigest()
    if resp["request_sha256"] != expected_sha:
        raise ValueError(
            f"Response request_sha256 mismatch: {resp['request_sha256']!r} != {expected_sha!r}"
        )
    if resp["request_id"] != expected_request["request_id"]:
        raise ValueError(
            f"Response request_id mismatch: {resp['request_id']!r} != {expected_request['request_id']!r}"
        )
    if resp["run_id"] != expected_request["run_id"]:
        raise ValueError(f"Response run_id mismatch: {resp['run_id']!r} != {expected_request['run_id']!r}")
    if resp["epoch"] != expected_request["epoch"]:
        raise ValueError(f"Response epoch mismatch: {resp['epoch']!r} != {expected_request['epoch']!r}")
    if resp["phase"] != expected_request["phase"]:
        raise ValueError(f"Response phase mismatch: {resp['phase']!r} != {expected_request['phase']!r}")
    if resp["target_pid_ns"] != expected_request["target_pid_ns"]:
        raise ValueError(
            f"Response target_pid_ns mismatch: {resp['target_pid_ns']!r} != {expected_request['target_pid_ns']!r}"
        )

    resp_col = (resp["collector"]["pid"], resp["collector"]["start_ticks"])
    exp_col = (expected_request["collector"]["pid"], expected_request["collector"]["start_ticks"])
    if resp_col != exp_col:
        raise ValueError(f"Response collector identity mismatch: {resp_col!r} != {exp_col!r}")

    if resp["boot_id"] != expected_request["boot_id"]:
        raise ValueError("Response boot_id mismatch with request")
    if expected_boot_id is not None and resp["boot_id"] != expected_boot_id:
        raise ValueError(f"Response boot_id mismatch: {resp['boot_id']!r} != {expected_boot_id!r}")


def _snapshot_wire_value(value):
    """Represent the snapshot tool's PID-keyed maps as unambiguous JSON maps."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if type(key) is int and key > 0:
                key = str(key)
            elif not isinstance(key, str):
                raise ValueError("snapshot map keys must be strings or positive integer PIDs")
            if key in result:
                raise ValueError("snapshot map keys collide after PID serialization")
            result[key] = _snapshot_wire_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_snapshot_wire_value(item) for item in value]
    return value


def publish_create_only(path: Path | str, payload: dict[str, any]) -> bytes:
    """Atomically publish payload to target path using exclusive create-only semantics.

    Refuses symlinks, rejects overwriting existing files, and performs an immediate
    read-back verification. Returns the exact written bytes.
    """
    raw_path = Path(path)
    # Windows/WSL callers exchange under a local Windows directory and its
    # /mnt/<drive> view.  UNC redirectors need not support atomic hard links;
    # never fall back to publishing a partially written destination.
    if os.name == "nt" and str(raw_path).startswith(("\\\\", "//")):
        raise ValueError("UNC publication is unsupported; use a local Windows directory and its WSL drive mount")
    if raw_path.is_symlink() or os.path.islink(raw_path):
        raise ValueError(f"Symlink target path rejected: {raw_path}")
    if raw_path.parent.is_symlink() or os.path.islink(raw_path.parent):
        raise ValueError(f"Symlink parent path rejected: {raw_path.parent}")

    target = raw_path.resolve(strict=False)
    if target.is_symlink() or os.path.islink(target):
        raise ValueError(f"Symlink target path rejected: {target}")
    if target.exists():
        raise FileExistsError(f"Target path already exists: {target}")

    parent = target.parent
    if parent.is_symlink() or os.path.islink(parent):
        raise ValueError(f"Symlink parent path rejected: {parent}")
    if not parent.is_dir():
        raise FileNotFoundError(f"Parent directory does not exist: {parent}")

    raw = encode_json_strict(payload)
    temporary = parent / f".{target.name}-{uuid.uuid4().hex}.tmp"

    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(descriptor, raw[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    try:
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"Target already exists before link: {target}")
        os.link(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    # Read-back verification
    read_back = target.read_bytes()
    if read_back != raw:
        raise RuntimeError(
            f"Read-back content mismatch on {target}: wrote {len(raw)} bytes, read {len(read_back)} bytes"
        )
    return raw


def verify_elapsed_monotonic(start_monotonic_ns: int, timeout_s: float) -> int:
    """Validate that caller's own monotonic elapsed time has not exceeded timeout.

    Evaluates exclusively against the local caller's clock; never compares
    timestamps across operating system boundaries.
    """
    if not is_strict_pos_int(start_monotonic_ns):
        raise ValueError(f"start_monotonic_ns must be a positive int, got: {start_monotonic_ns!r}")
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or timeout_s <= 0
        or not math.isfinite(timeout_s)
    ):
        raise ValueError(f"timeout_s must be a finite positive number, got: {timeout_s!r}")

    now = time.monotonic_ns()
    elapsed_ns = now - start_monotonic_ns
    if elapsed_ns < 0:
        raise RuntimeError("Monotonic clock rewound")
    timeout_ns = int(timeout_s * 1_000_000_000)
    if elapsed_ns > timeout_ns:
        raise TimeoutError(f"Snapshot exchange timed out: elapsed {elapsed_ns / 1e9:.3f}s > {timeout_s:.3f}s")
    return elapsed_ns
