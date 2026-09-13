"""Strict, deterministic length-prefixed UTF-8 JSON envelope for Bspline TCP transport (#102).

This module provides pure offline serialization, framing, and validation for
transporting prometheus_msgs/Bspline payloads across process or host boundaries
(e.g., ROS 1 relay -> ROS 2 transport) without importing ROS (rospy/rclpy),
without launching sockets, and without wall-clock or identity assumptions.

Design & Invariants:
1. Wire framing:
   4-byte big-endian unsigned integer length prefix (>I) followed by UTF-8 encoded JSON.
2. Exact envelope metadata:
   - schema: "wksim.bspline-tcp-envelope.v1"
   - transport_session_id: exactly 32 lowercase hex characters [0-9a-f]{32}
   - sequence: strictly monotonic integer (prev + 1)
   - source_package: "prometheus_msgs"
   - source_msg_type: "prometheus_msgs/Bspline"
   - ros1_msg_sha256: pinned hash of Modules/common/prometheus_msgs/msg/Bspline.msg
   - ros2_msg_sha256: pinned hash of ros2/src/prometheus_msgs/msg/Bspline.msg
   - payload: dictionary of the 8 Bspline fields.
3. Strict fail-closed payload validation:
   - Exact field keys: drone_id, order, traj_id, start_time, knots, pos_pts, yaw_pts, yaw_dt.
   - Exact types and ranges:
     * drone_id, order: int32 ([-2**31, 2**31 - 1], order > 0, non-bool)
     * traj_id: int64 ([-2**63, 2**63 - 1], non-bool)
     * start_time: {"sec": int, "nanosec": int} (0 <= nanosec < 1_000_000_000, non-bool, sec >= 0)
     * knots: bounded list of finite floats (non-bool, no NaN, no Inf)
     * pos_pts: bounded list of {"x": float, "y": float, "z": float} with exact keys (non-bool, finite)
     * yaw_pts: bounded list of finite floats (non-bool, finite)
     * yaw_dt: finite float (non-bool, finite)
   - Rejection of duplicate JSON keys, NaN/Inf constants, extra fields, missing fields.
4. Bridge output mapping:
   - Decodes directly into the normalized dictionary expected by
     Simulator.wksim_planning.ego_bspline_bridge.bridge_bspline(payload, anchor_ns=..., current_tick=...).
   - Converts start_time into integer nanoseconds: sec * 1_000_000_000 + nanosec.
   - Converts pos_pts into list of 3-tuples (x, y, z).
5. State API:
   - Encoder: sequence high-water mark advances only upon successful encoding.
   - Decoder: expected sequence advances only upon successful decoding; failure leaves high-water mark intact.
6. Scope & Non-claims:
   - Does NOT mint run_id, mission_id, epoch, request_id, command_id.
   - Does NOT mutate start_time (no clock translation or offsets).
   - Does NOT claim socket, ROS, or full transport pass.
"""
from __future__ import annotations

import hashlib
import json
import math
from numbers import Real
from pathlib import Path
import re
import struct
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
ROS1_MSG_FILE = REPO_ROOT / "Modules" / "common" / "prometheus_msgs" / "msg" / "Bspline.msg"
ROS2_MSG_FILE = REPO_ROOT / "ros2" / "src" / "prometheus_msgs" / "msg" / "Bspline.msg"
MESSAGE_PIN_DIR = Path(__file__).resolve().parent / "message_pins"
ROS1_MESSAGE_PIN_FILE = MESSAGE_PIN_DIR / "ros1_Bspline.msg"
ROS2_MESSAGE_PIN_FILE = MESSAGE_PIN_DIR / "ros2_Bspline.msg"


def _message_paths() -> Tuple[Path, Path]:
    """Select repository messages, or the explicit installed asset fallback.

    A partially present repository checkout must keep the original pair so
    that the missing side is rejected.  The module-local assets are selected
    only when both canonical repository paths are absent (including broken
    links, which remain a rejection rather than an installation fallback).
    """
    canonical_present = any(
        path.exists() or path.is_symlink()
        for path in (ROS1_MSG_FILE, ROS2_MSG_FILE)
    )
    if canonical_present:
        return ROS1_MSG_FILE, ROS2_MSG_FILE
    return ROS1_MESSAGE_PIN_FILE, ROS2_MESSAGE_PIN_FILE


def _verify_repo_msg_pins(
    ros1_sha256: str,
    ros2_sha256: str,
    *,
    _ros1_path: Optional[Path] = None,
    _ros2_path: Optional[Path] = None,
) -> None:
    """Recompute both pinned message hashes; reject drift or absence."""
    if _ros1_path is None and _ros2_path is None:
        _ros1_path, _ros2_path = _message_paths()
    else:
        # Explicit paths are retained for the offline test seam and preserve
        # the old one-sided default behavior for callers of this helper.
        _ros1_path = ROS1_MSG_FILE if _ros1_path is None else _ros1_path
        _ros2_path = ROS2_MSG_FILE if _ros2_path is None else _ros2_path
    for path, expected, label in ((_ros1_path, ros1_sha256, "ros1"),
                                  (_ros2_path, ros2_sha256, "ros2")):
        if path.is_symlink() or not path.is_file():
            raise BsplineEnvelopeError("hash_mismatch", f"{label} Bspline.msg missing or linked: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise BsplineEnvelopeError("hash_mismatch",
                                       f"{label} Bspline.msg drifted from the frozen pin: {actual}")

_PINNED_SCHEMA_V1 = "wksim.bspline-tcp-envelope.v1"
_PINNED_SOURCE_PACKAGE = "prometheus_msgs"
_PINNED_SOURCE_MSG_TYPE = "prometheus_msgs/Bspline"
_PINNED_ROS1_BSPLINE_MSG_SHA256 = "08ab59c600038eaff054bab381c48f3bf16c693a34007c64b8ba98b8a44ee706"
_PINNED_ROS2_BSPLINE_MSG_SHA256 = "83922f2387a58be693aaad1f4d35d5421719e9288daa65ed5f48f27132c4dbe8"
_PINNED_MAX_FRAME_BYTES = 1048576
_PINNED_MAX_PAYLOAD_BYTES = _PINNED_MAX_FRAME_BYTES - 4
_PINNED_MAX_POINTS = 4096
_PINNED_MAX_KNOTS = 4096 + 32
_PINNED_MAX_YAW_PTS = 4096
_PINNED_MAX_BUFFER_BYTES = 2097152
_PINNED_INT32_MIN = -2147483648
_PINNED_INT32_MAX = 2147483647
_PINNED_INT64_MIN = -9223372036854775808
_PINNED_INT64_MAX = 9223372036854775807
_PINNED_NANOSEC_LIMIT = 1_000_000_000
_PINNED_SESSION_PATTERN = r"^[0-9a-f]{32}$"
_PINNED_CONTROL_SCHEMA_V2 = "wksim.bspline-tcp-envelope.v2"
_PINNED_CONTROL_ENVELOPE_FIELDS = (
    "schema",
    "transport_session_id",
    "sequence",
    "control",
)
_PINNED_CONTROL_KINDS = ("gate", "hold", "cancel")

# These names are intentionally public for callers and documentation.  The
# private values above are the construction-time protocol pins: changing a
# module global cannot silently change what a newly constructed instance uses.
SCHEMA_V1 = _PINNED_SCHEMA_V1
SOURCE_PACKAGE = _PINNED_SOURCE_PACKAGE
SOURCE_MSG_TYPE = _PINNED_SOURCE_MSG_TYPE
ROS1_BSPLINE_MSG_SHA256 = _PINNED_ROS1_BSPLINE_MSG_SHA256
ROS2_BSPLINE_MSG_SHA256 = _PINNED_ROS2_BSPLINE_MSG_SHA256
MAX_FRAME_BYTES = _PINNED_MAX_FRAME_BYTES       # 1 MiB wire frame maximum
MAX_PAYLOAD_BYTES = _PINNED_MAX_PAYLOAD_BYTES
MAX_POINTS = _PINNED_MAX_POINTS                 # Consistent with ego_evaluator.MAX_POINTS
MAX_KNOTS = _PINNED_MAX_KNOTS                   # Upper bound for uniform/non-uniform knot vector
CONTROL_SCHEMA_V2 = _PINNED_CONTROL_SCHEMA_V2
CONTROL_ENVELOPE_FIELDS = _PINNED_CONTROL_ENVELOPE_FIELDS
CONTROL_KINDS = _PINNED_CONTROL_KINDS
MAX_YAW_PTS = _PINNED_MAX_YAW_PTS               # Bounded yaw sequence
MAX_BUFFER_BYTES = _PINNED_MAX_BUFFER_BYTES     # 2 MiB stream buffer cap

INT32_MIN = _PINNED_INT32_MIN
INT32_MAX = _PINNED_INT32_MAX
INT64_MIN = _PINNED_INT64_MIN
INT64_MAX = _PINNED_INT64_MAX
NANOSEC_LIMIT = _PINNED_NANOSEC_LIMIT

BSPLINE_PAYLOAD_FIELDS = (
    "drone_id",
    "order",
    "traj_id",
    "start_time",
    "knots",
    "pos_pts",
    "yaw_pts",
    "yaw_dt",
)

ENVELOPE_FIELDS = (
    "schema",
    "transport_session_id",
    "sequence",
    "source_package",
    "source_msg_type",
    "ros1_msg_sha256",
    "ros2_msg_sha256",
    "payload",
)

ENVELOPE_REASONS = (
    "invalid_frame_header",
    "truncated_frame",
    "spliced_frame",
    "oversized_frame",
    "invalid_json",
    "invalid_control_kind",
    "invalid_control_payload",
    "control_frame_unexpected",
    "duplicate_key",
    "invalid_envelope_schema",
    "invalid_session_id",
    "session_mismatch",
    "sequence_mismatch",
    "invalid_source",
    "hash_mismatch",
    "invalid_payload",
    "invalid_field",
    "invalid_time",
    "invalid_point",
    "array_length_exceeded",
)

# The public tuples above are part of the documented surface, while these
# aliases are the private construction pins.  The *_AT_IMPORT defaults below
# capture the tuple objects at function/class definition time, so changing the
# public and private names together cannot replace the protocol used by an
# existing or newly constructed instance.
_PINNED_BSPLINE_PAYLOAD_FIELDS = BSPLINE_PAYLOAD_FIELDS
_PINNED_ENVELOPE_FIELDS = ENVELOPE_FIELDS
_PINNED_ENVELOPE_REASONS = ENVELOPE_REASONS
_BSPLINE_PAYLOAD_FIELDS_AT_IMPORT = BSPLINE_PAYLOAD_FIELDS
_ENVELOPE_FIELDS_AT_IMPORT = ENVELOPE_FIELDS
_ENVELOPE_REASONS_AT_IMPORT = ENVELOPE_REASONS
_CONTROL_ENVELOPE_FIELDS_AT_IMPORT = CONTROL_ENVELOPE_FIELDS
_CONTROL_KINDS_AT_IMPORT = CONTROL_KINDS

_HEX_SESSION_RE = re.compile(_PINNED_SESSION_PATTERN)


class BsplineEnvelopeError(ValueError):
    """Reason-coded exception for Bspline TCP envelope encode/decode failures."""

    def __init__(
        self,
        reason: str,
        message: str = "",
        _reasons: Tuple[str, ...] = _ENVELOPE_REASONS_AT_IMPORT,
    ):
        if reason not in _reasons:
            raise ValueError(f"unknown envelope error reason: {reason!r}")
        full_msg = f"[{reason}] {message}" if message else reason
        super().__init__(full_msg)
        self.reason = reason
        self.message = message


class _ProtocolSnapshot(NamedTuple):
    """Immutable protocol values captured by one encoder/decoder instance."""

    schema: str
    source_package: str
    source_msg_type: str
    ros1_msg_sha256: str
    ros2_msg_sha256: str
    max_frame_bytes: int
    max_payload_bytes: int
    max_points: int
    max_knots: int
    max_yaw_pts: int
    max_buffer_bytes: int
    int32_min: int
    int32_max: int
    int64_min: int
    int64_max: int
    nanosec_limit: int
    session_pattern: str
    payload_fields: Tuple[str, ...]
    envelope_fields: Tuple[str, ...]
    envelope_reasons: Tuple[str, ...]
    control_schema: str
    control_envelope_fields: Tuple[str, ...]
    control_kinds: Tuple[str, ...]


def _capture_protocol_snapshot(
    *,
    # Defaults capture the import-time contract.  Constructor validation below
    # still rejects any mutation of either the public or private module names,
    # but a simultaneous monkeypatch cannot change the values used by an
    # otherwise valid instance.
    _schema: str = _PINNED_SCHEMA_V1,
    _source_package: str = _PINNED_SOURCE_PACKAGE,
    _source_msg_type: str = _PINNED_SOURCE_MSG_TYPE,
    _ros1_msg_sha256: str = _PINNED_ROS1_BSPLINE_MSG_SHA256,
    _ros2_msg_sha256: str = _PINNED_ROS2_BSPLINE_MSG_SHA256,
    _max_frame_bytes: int = _PINNED_MAX_FRAME_BYTES,
    _max_payload_bytes: int = _PINNED_MAX_PAYLOAD_BYTES,
    _max_points: int = _PINNED_MAX_POINTS,
    _max_knots: int = _PINNED_MAX_KNOTS,
    _max_yaw_pts: int = _PINNED_MAX_YAW_PTS,
    _max_buffer_bytes: int = _PINNED_MAX_BUFFER_BYTES,
    _int32_min: int = _PINNED_INT32_MIN,
    _int32_max: int = _PINNED_INT32_MAX,
    _int64_min: int = _PINNED_INT64_MIN,
    _int64_max: int = _PINNED_INT64_MAX,
    _nanosec_limit: int = _PINNED_NANOSEC_LIMIT,
    _session_pattern: str = _PINNED_SESSION_PATTERN,
    _verify_pins: Any = _verify_repo_msg_pins,
    _payload_fields: Tuple[str, ...] = _BSPLINE_PAYLOAD_FIELDS_AT_IMPORT,
    _envelope_fields: Tuple[str, ...] = _ENVELOPE_FIELDS_AT_IMPORT,
    _envelope_reasons: Tuple[str, ...] = _ENVELOPE_REASONS_AT_IMPORT,
    _control_schema: str = _PINNED_CONTROL_SCHEMA_V2,
    _control_envelope_fields: Tuple[str, ...] = _CONTROL_ENVELOPE_FIELDS_AT_IMPORT,
    _control_kinds: Tuple[str, ...] = _CONTROL_KINDS_AT_IMPORT,
) -> _ProtocolSnapshot:
    """Validate module pins and capture the complete instance protocol contract."""
    if SCHEMA_V1 != _schema or _PINNED_SCHEMA_V1 != _schema:
        raise BsplineEnvelopeError("invalid_envelope_schema", "module schema pin was modified")
    if (
        SOURCE_PACKAGE != _source_package
        or SOURCE_MSG_TYPE != _source_msg_type
        or _PINNED_SOURCE_PACKAGE != _source_package
        or _PINNED_SOURCE_MSG_TYPE != _source_msg_type
    ):
        raise BsplineEnvelopeError("invalid_source", "module source identity pin was modified")
    if ROS1_BSPLINE_MSG_SHA256 != _ros1_msg_sha256 or _PINNED_ROS1_BSPLINE_MSG_SHA256 != _ros1_msg_sha256:
        raise BsplineEnvelopeError("hash_mismatch", "module ROS 1 message hash pin was modified")
    if ROS2_BSPLINE_MSG_SHA256 != _ros2_msg_sha256 or _PINNED_ROS2_BSPLINE_MSG_SHA256 != _ros2_msg_sha256:
        raise BsplineEnvelopeError("hash_mismatch", "module ROS 2 message hash pin was modified")
    if (
        MAX_FRAME_BYTES != _max_frame_bytes
        or MAX_PAYLOAD_BYTES != _max_payload_bytes
        or MAX_BUFFER_BYTES != _max_buffer_bytes
        or _PINNED_MAX_FRAME_BYTES != _max_frame_bytes
        or _PINNED_MAX_PAYLOAD_BYTES != _max_payload_bytes
        or _PINNED_MAX_BUFFER_BYTES != _max_buffer_bytes
        or _max_payload_bytes != _max_frame_bytes - 4
    ):
        raise BsplineEnvelopeError("invalid_frame_header", "module frame or buffer size pin was modified")
    if (
        MAX_POINTS != _max_points
        or MAX_KNOTS != _max_knots
        or MAX_YAW_PTS != _max_yaw_pts
        or _PINNED_MAX_POINTS != _max_points
        or _PINNED_MAX_KNOTS != _max_knots
        or _PINNED_MAX_YAW_PTS != _max_yaw_pts
    ):
        raise BsplineEnvelopeError("array_length_exceeded", "module payload array size pin was modified")
    if (
        INT32_MIN != _int32_min
        or INT32_MAX != _int32_max
        or INT64_MIN != _int64_min
        or INT64_MAX != _int64_max
        or NANOSEC_LIMIT != _nanosec_limit
        or _PINNED_INT32_MIN != _int32_min
        or _PINNED_INT32_MAX != _int32_max
        or _PINNED_INT64_MIN != _int64_min
        or _PINNED_INT64_MAX != _int64_max
        or _PINNED_NANOSEC_LIMIT != _nanosec_limit
    ):
        raise BsplineEnvelopeError("invalid_field", "module integer range pin was modified")
    if (
        _PINNED_SESSION_PATTERN != _session_pattern
        or not isinstance(_HEX_SESSION_RE, re.Pattern)
        or _HEX_SESSION_RE.pattern != _session_pattern
    ):
        raise BsplineEnvelopeError("invalid_session_id", "module session validation pin was modified")
    if (
        BSPLINE_PAYLOAD_FIELDS != _payload_fields
        or _PINNED_BSPLINE_PAYLOAD_FIELDS != _payload_fields
    ):
        raise BsplineEnvelopeError("invalid_payload", "module payload field pin was modified")
    if ENVELOPE_FIELDS != _envelope_fields or _PINNED_ENVELOPE_FIELDS != _envelope_fields:
        raise BsplineEnvelopeError("invalid_envelope_schema", "module envelope field pin was modified")
    if CONTROL_SCHEMA_V2 != _control_schema or _PINNED_CONTROL_SCHEMA_V2 != _control_schema:
        raise BsplineEnvelopeError("invalid_envelope_schema", "module control schema pin was modified")
    if (CONTROL_ENVELOPE_FIELDS != _control_envelope_fields
            or _PINNED_CONTROL_ENVELOPE_FIELDS != _control_envelope_fields):
        raise BsplineEnvelopeError("invalid_envelope_schema", "module control envelope field pin was modified")
    if CONTROL_KINDS != _control_kinds or _PINNED_CONTROL_KINDS != _control_kinds:
        raise BsplineEnvelopeError("invalid_control_kind", "module control kind pin was modified")

    # Verify the repository files against private pins, never against mutable
    # public globals.  This also prevents edited message files and edited
    # module constants from being made self-consistent at construction time.
    _verify_pins(_ros1_msg_sha256, _ros2_msg_sha256)
    return _ProtocolSnapshot(
        schema=_schema,
        source_package=_source_package,
        source_msg_type=_source_msg_type,
        ros1_msg_sha256=_ros1_msg_sha256,
        ros2_msg_sha256=_ros2_msg_sha256,
        max_frame_bytes=_max_frame_bytes,
        max_payload_bytes=_max_payload_bytes,
        max_points=_max_points,
        max_knots=_max_knots,
        max_yaw_pts=_max_yaw_pts,
        max_buffer_bytes=_max_buffer_bytes,
        int32_min=_int32_min,
        int32_max=_int32_max,
        int64_min=_int64_min,
        int64_max=_int64_max,
        nanosec_limit=_nanosec_limit,
        session_pattern=_session_pattern,
        payload_fields=_payload_fields,
        envelope_fields=_envelope_fields,
        envelope_reasons=_envelope_reasons,
        control_schema=_control_schema,
        control_envelope_fields=_control_envelope_fields,
        control_kinds=_control_kinds,
    )


def _format_keys(keys: Any) -> str:
    """Render arbitrary mapping keys without leaking a sorting TypeError."""
    return "[" + ", ".join(sorted((repr(key) for key in keys))) + "]"


def validate_session_id(session_id: Any, *, pattern: Optional[str] = None) -> str:
    """Validate 32 lowercase hex characters session ID."""
    if not isinstance(session_id, str):
        raise BsplineEnvelopeError("invalid_session_id", "session_id must be a string")
    matched = _HEX_SESSION_RE.fullmatch(session_id) if pattern is None else re.fullmatch(pattern, session_id)
    if matched is None:
        raise BsplineEnvelopeError("invalid_session_id", "session_id must be exactly 32 lowercase hex characters")
    return session_id


def _strict_int(value: Any, min_val: int, max_val: int, reason: str, name: str) -> int:
    """Enforce strict integer (non-bool) within [min_val, max_val]."""
    if isinstance(value, bool) or type(value) is not int:
        raise BsplineEnvelopeError(reason, f"{name} must be an integer, got {type(value).__name__}")
    if not (min_val <= value <= max_val):
        raise BsplineEnvelopeError(reason, f"{name} out of range [{min_val}, {max_val}]: {value}")
    return value


def _strict_finite_float(value: Any, reason: str, name: str) -> float:
    """Enforce non-bool, finite real number converted to float."""
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise BsplineEnvelopeError(reason, f"{name} must be a finite real number, got {value!r}")
    return float(value)


def _reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """object_pairs_hook callback to reject duplicate JSON keys."""
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise BsplineEnvelopeError("duplicate_key", f"duplicate JSON key: {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _reject_json_constant(constant: str) -> None:
    """parse_constant callback to reject NaN, Infinity, -Infinity in JSON."""
    raise BsplineEnvelopeError("invalid_field", f"disallowed JSON constant: {constant!r}")


def parse_json_bytes(raw_bytes_or_str: bytes | str) -> Dict[str, Any]:
    """Parse JSON bytes/str with duplicate key rejection and NaN/Inf rejection."""
    if isinstance(raw_bytes_or_str, (bytes, bytearray)):
        try:
            text = raw_bytes_or_str.decode("utf-8")
        except UnicodeDecodeError as err:
            raise BsplineEnvelopeError("invalid_json", f"UTF-8 decode failed: {err}") from err
    elif isinstance(raw_bytes_or_str, str):
        text = raw_bytes_or_str
    else:
        raise BsplineEnvelopeError("invalid_json", f"expected bytes or str, got {type(raw_bytes_or_str).__name__}")

    try:
        data = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as err:
        raise BsplineEnvelopeError("invalid_json", f"JSON syntax error: {err}") from err

    if type(data) is not dict:
        raise BsplineEnvelopeError("invalid_envelope_schema", f"expected JSON object, got {type(data).__name__}")
    return data


def serialize_envelope_json(envelope: Dict[str, Any]) -> bytes:
    """Serialize envelope dict to deterministic UTF-8 JSON bytes (sorted keys, no nan)."""
    try:
        return json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except ValueError as err:
        raise BsplineEnvelopeError("invalid_field", f"JSON serialization failed: {err}") from err


def normalize_time_input(
    raw_time: Any,
    *,
    int32_min: Optional[int] = None,
    int32_max: Optional[int] = None,
    nanosec_limit: Optional[int] = None,
) -> Dict[str, int]:
    """Normalize input time representation to {'sec': int, 'nanosec': int}.

    Accepts:
    - dict with exact keys {'sec', 'nanosec'} or {'secs', 'nsecs'}
    - object with attributes sec and nanosec, or secs and nsecs
    """
    if int32_min is None:
        int32_min = INT32_MIN
    if int32_max is None:
        int32_max = INT32_MAX
    if nanosec_limit is None:
        nanosec_limit = NANOSEC_LIMIT
    if isinstance(raw_time, dict):
        keys = set(raw_time.keys())
        if keys == {"sec", "nanosec"}:
            s = raw_time["sec"]
            ns = raw_time["nanosec"]
        elif keys == {"secs", "nsecs"}:
            s = raw_time["secs"]
            ns = raw_time["nsecs"]
        else:
            raise BsplineEnvelopeError(
                "invalid_time",
                f"time dict must have exact keys ('sec', 'nanosec') or ('secs', 'nsecs'), got {_format_keys(keys)}",
            )
    elif hasattr(raw_time, "sec") and hasattr(raw_time, "nanosec"):
        s = getattr(raw_time, "sec")
        ns = getattr(raw_time, "nanosec")
    elif hasattr(raw_time, "secs") and hasattr(raw_time, "nsecs"):
        s = getattr(raw_time, "secs")
        ns = getattr(raw_time, "nsecs")
    else:
        raise BsplineEnvelopeError("invalid_time", f"unsupported time object: {type(raw_time).__name__}")

    s = _strict_int(s, 0, int32_max, "invalid_time", "start_time.sec")
    ns = _strict_int(ns, 0, nanosec_limit - 1, "invalid_time", "start_time.nanosec")
    return {"sec": s, "nanosec": ns}


def validate_wire_time(
    wire_time: Any,
    *,
    int32_min: Optional[int] = None,
    int32_max: Optional[int] = None,
    nanosec_limit: Optional[int] = None,
) -> Dict[str, int]:
    """Validate time object from wire envelope with exact {'sec', 'nanosec'} keys."""
    if int32_min is None:
        int32_min = INT32_MIN
    if int32_max is None:
        int32_max = INT32_MAX
    if nanosec_limit is None:
        nanosec_limit = NANOSEC_LIMIT
    if type(wire_time) is not dict:
        raise BsplineEnvelopeError("invalid_time", f"wire start_time must be dict, got {type(wire_time).__name__}")
    if set(wire_time.keys()) != {"sec", "nanosec"}:
        raise BsplineEnvelopeError(
            "invalid_time",
            f"wire start_time must have exact keys {{'sec', 'nanosec'}}, got {_format_keys(wire_time.keys())}",
        )
    s = _strict_int(wire_time["sec"], 0, int32_max, "invalid_time", "start_time.sec")
    ns = _strict_int(wire_time["nanosec"], 0, nanosec_limit - 1, "invalid_time", "start_time.nanosec")
    return {"sec": s, "nanosec": ns}


def normalize_point_input(raw_pt: Any) -> Dict[str, float]:
    """Normalize input point representation to {'x': float, 'y': float, 'z': float}."""
    if isinstance(raw_pt, dict):
        if set(raw_pt.keys()) != {"x", "y", "z"}:
            raise BsplineEnvelopeError(
                "invalid_point",
                f"point dict must have exact keys {{'x', 'y', 'z'}}, got {_format_keys(raw_pt.keys())}",
            )
        x = _strict_finite_float(raw_pt["x"], "invalid_point", "point.x")
        y = _strict_finite_float(raw_pt["y"], "invalid_point", "point.y")
        z = _strict_finite_float(raw_pt["z"], "invalid_point", "point.z")
    elif isinstance(raw_pt, (list, tuple)):
        if len(raw_pt) != 3:
            raise BsplineEnvelopeError("invalid_point", f"point sequence must have exactly 3 coordinates, got {len(raw_pt)}")
        x = _strict_finite_float(raw_pt[0], "invalid_point", "point.x")
        y = _strict_finite_float(raw_pt[1], "invalid_point", "point.y")
        z = _strict_finite_float(raw_pt[2], "invalid_point", "point.z")
    elif hasattr(raw_pt, "x") and hasattr(raw_pt, "y") and hasattr(raw_pt, "z"):
        x = _strict_finite_float(getattr(raw_pt, "x"), "invalid_point", "point.x")
        y = _strict_finite_float(getattr(raw_pt, "y"), "invalid_point", "point.y")
        z = _strict_finite_float(getattr(raw_pt, "z"), "invalid_point", "point.z")
    else:
        raise BsplineEnvelopeError("invalid_point", f"unsupported point type: {type(raw_pt).__name__}")
    return {"x": x, "y": y, "z": z}


def validate_wire_point(wire_pt: Any) -> Dict[str, float]:
    """Validate point object from wire envelope with exact {'x', 'y', 'z'} keys."""
    if type(wire_pt) is not dict:
        raise BsplineEnvelopeError("invalid_point", f"wire point must be dict, got {type(wire_pt).__name__}")
    if set(wire_pt.keys()) != {"x", "y", "z"}:
        raise BsplineEnvelopeError(
            "invalid_point",
            f"wire point must have exact keys {{'x', 'y', 'z'}}, got {_format_keys(wire_pt.keys())}",
        )
    x = _strict_finite_float(wire_pt["x"], "invalid_point", "point.x")
    y = _strict_finite_float(wire_pt["y"], "invalid_point", "point.y")
    z = _strict_finite_float(wire_pt["z"], "invalid_point", "point.z")
    return {"x": x, "y": y, "z": z}


def validate_and_normalize_payload(
    raw_payload: Any,
    *,
    max_points: Optional[int] = None,
    max_knots: Optional[int] = None,
    max_yaw_pts: Optional[int] = None,
    int32_min: Optional[int] = None,
    int32_max: Optional[int] = None,
    int64_min: Optional[int] = None,
    int64_max: Optional[int] = None,
    nanosec_limit: Optional[int] = None,
    payload_fields: Tuple[str, ...] = _BSPLINE_PAYLOAD_FIELDS_AT_IMPORT,
) -> Dict[str, Any]:
    """Validate and normalize input payload for encoding.

    The optional limits default to the module's import-time contract for this
    top-level helper.  Stateful instances pass their construction snapshot.
    """
    if max_points is None:
        max_points = MAX_POINTS
    if max_knots is None:
        max_knots = MAX_KNOTS
    if max_yaw_pts is None:
        max_yaw_pts = MAX_YAW_PTS
    if int32_min is None:
        int32_min = INT32_MIN
    if int32_max is None:
        int32_max = INT32_MAX
    if int64_min is None:
        int64_min = INT64_MIN
    if int64_max is None:
        int64_max = INT64_MAX
    if nanosec_limit is None:
        nanosec_limit = NANOSEC_LIMIT
    if type(raw_payload) is not dict:
        raise BsplineEnvelopeError("invalid_payload", f"payload must be dict, got {type(raw_payload).__name__}")
    if set(raw_payload.keys()) != set(payload_fields):
        raise BsplineEnvelopeError(
            "invalid_payload",
            f"payload must have exact fields {_format_keys(payload_fields)}, got {_format_keys(raw_payload.keys())}",
        )

    drone_id = _strict_int(raw_payload["drone_id"], int32_min, int32_max, "invalid_field", "drone_id")
    order = _strict_int(raw_payload["order"], 1, int32_max, "invalid_field", "order")
    traj_id = _strict_int(raw_payload["traj_id"], int64_min, int64_max, "invalid_field", "traj_id")
    start_time = normalize_time_input(
        raw_payload["start_time"],
        int32_min=int32_min,
        int32_max=int32_max,
        nanosec_limit=nanosec_limit,
    )

    knots_in = raw_payload["knots"]
    if type(knots_in) not in (list, tuple):
        raise BsplineEnvelopeError("invalid_field", f"knots must be a list or tuple, got {type(knots_in).__name__}")
    if len(knots_in) > max_knots:
        raise BsplineEnvelopeError("array_length_exceeded", f"knots length {len(knots_in)} exceeds maximum {max_knots}")
    knots = [_strict_finite_float(k, "invalid_field", "knot") for k in knots_in]

    pos_pts_in = raw_payload["pos_pts"]
    if type(pos_pts_in) not in (list, tuple):
        raise BsplineEnvelopeError("invalid_field", f"pos_pts must be a list or tuple, got {type(pos_pts_in).__name__}")
    if len(pos_pts_in) > max_points:
        raise BsplineEnvelopeError("array_length_exceeded", f"pos_pts length {len(pos_pts_in)} exceeds maximum {max_points}")
    pos_pts = [normalize_point_input(pt) for pt in pos_pts_in]

    yaw_pts_in = raw_payload["yaw_pts"]
    if type(yaw_pts_in) not in (list, tuple):
        raise BsplineEnvelopeError("invalid_field", f"yaw_pts must be a list or tuple, got {type(yaw_pts_in).__name__}")
    if len(yaw_pts_in) > max_yaw_pts:
        raise BsplineEnvelopeError("array_length_exceeded", f"yaw_pts length {len(yaw_pts_in)} exceeds maximum {max_yaw_pts}")
    yaw_pts = [_strict_finite_float(y, "invalid_field", "yaw_point") for y in yaw_pts_in]

    yaw_dt = _strict_finite_float(raw_payload["yaw_dt"], "invalid_field", "yaw_dt")

    return {
        "drone_id": drone_id,
        "order": order,
        "traj_id": traj_id,
        "start_time": start_time,
        "knots": knots,
        "pos_pts": pos_pts,
        "yaw_pts": yaw_pts,
        "yaw_dt": yaw_dt,
    }


def validate_wire_payload(
    wire_payload: Any,
    *,
    max_points: Optional[int] = None,
    max_knots: Optional[int] = None,
    max_yaw_pts: Optional[int] = None,
    int32_min: Optional[int] = None,
    int32_max: Optional[int] = None,
    int64_min: Optional[int] = None,
    int64_max: Optional[int] = None,
    nanosec_limit: Optional[int] = None,
    payload_fields: Tuple[str, ...] = _BSPLINE_PAYLOAD_FIELDS_AT_IMPORT,
) -> Dict[str, Any]:
    """Validate decoded wire payload dictionary strictly.

    The optional limits default to the module's import-time contract for this
    top-level helper.  Stateful instances pass their construction snapshot.
    """
    if max_points is None:
        max_points = MAX_POINTS
    if max_knots is None:
        max_knots = MAX_KNOTS
    if max_yaw_pts is None:
        max_yaw_pts = MAX_YAW_PTS
    if int32_min is None:
        int32_min = INT32_MIN
    if int32_max is None:
        int32_max = INT32_MAX
    if int64_min is None:
        int64_min = INT64_MIN
    if int64_max is None:
        int64_max = INT64_MAX
    if nanosec_limit is None:
        nanosec_limit = NANOSEC_LIMIT
    if type(wire_payload) is not dict:
        raise BsplineEnvelopeError("invalid_payload", f"payload must be dict, got {type(wire_payload).__name__}")
    if set(wire_payload.keys()) != set(payload_fields):
        raise BsplineEnvelopeError(
            "invalid_payload",
            f"wire payload must have exact fields {_format_keys(payload_fields)}, got {_format_keys(wire_payload.keys())}",
        )

    drone_id = _strict_int(wire_payload["drone_id"], int32_min, int32_max, "invalid_field", "drone_id")
    order = _strict_int(wire_payload["order"], 1, int32_max, "invalid_field", "order")
    traj_id = _strict_int(wire_payload["traj_id"], int64_min, int64_max, "invalid_field", "traj_id")
    start_time = validate_wire_time(
        wire_payload["start_time"],
        int32_min=int32_min,
        int32_max=int32_max,
        nanosec_limit=nanosec_limit,
    )

    knots_in = wire_payload["knots"]
    if type(knots_in) is not list:
        raise BsplineEnvelopeError("invalid_field", f"wire knots must be a list, got {type(knots_in).__name__}")
    if len(knots_in) > max_knots:
        raise BsplineEnvelopeError("array_length_exceeded", f"knots length {len(knots_in)} exceeds maximum {max_knots}")
    knots = [_strict_finite_float(k, "invalid_field", "knot") for k in knots_in]

    pos_pts_in = wire_payload["pos_pts"]
    if type(pos_pts_in) is not list:
        raise BsplineEnvelopeError("invalid_field", f"wire pos_pts must be a list, got {type(pos_pts_in).__name__}")
    if len(pos_pts_in) > max_points:
        raise BsplineEnvelopeError("array_length_exceeded", f"pos_pts length {len(pos_pts_in)} exceeds maximum {max_points}")
    pos_pts = [validate_wire_point(pt) for pt in pos_pts_in]

    yaw_pts_in = wire_payload["yaw_pts"]
    if type(yaw_pts_in) is not list:
        raise BsplineEnvelopeError("invalid_field", f"wire yaw_pts must be a list, got {type(yaw_pts_in).__name__}")
    if len(yaw_pts_in) > max_yaw_pts:
        raise BsplineEnvelopeError("array_length_exceeded", f"yaw_pts length {len(yaw_pts_in)} exceeds maximum {max_yaw_pts}")
    yaw_pts = [_strict_finite_float(y, "invalid_field", "yaw_point") for y in yaw_pts_in]

    yaw_dt = _strict_finite_float(wire_payload["yaw_dt"], "invalid_field", "yaw_dt")

    return {
        "drone_id": drone_id,
        "order": order,
        "traj_id": traj_id,
        "start_time": start_time,
        "knots": knots,
        "pos_pts": pos_pts,
        "yaw_pts": yaw_pts,
        "yaw_dt": yaw_dt,
    }


def parse_and_validate_envelope(
    raw_data: bytes | str | Dict[str, Any],
    *,
    expected_session_id: Optional[str] = None,
    expected_sequence: Optional[int] = None,
    expected_schema: Optional[str] = None,
    expected_ros1_msg_sha256: Optional[str] = None,
    expected_ros2_msg_sha256: Optional[str] = None,
    expected_source_package: Optional[str] = None,
    expected_source_msg_type: Optional[str] = None,
    expected_session_pattern: Optional[str] = None,
    max_points: Optional[int] = None,
    max_knots: Optional[int] = None,
    max_yaw_pts: Optional[int] = None,
    int32_min: Optional[int] = None,
    int32_max: Optional[int] = None,
    int64_min: Optional[int] = None,
    int64_max: Optional[int] = None,
    nanosec_limit: Optional[int] = None,
    payload_fields: Tuple[str, ...] = _BSPLINE_PAYLOAD_FIELDS_AT_IMPORT,
    envelope_fields: Tuple[str, ...] = _ENVELOPE_FIELDS_AT_IMPORT,
) -> Dict[str, Any]:
    """Parse and validate envelope metadata and payload.

    Omitted expectations use the module's current scalar defaults and its
    import-time field contract.  Stateful encoder and decoder instances
    always pass their immutable construction snapshot.
    """
    if expected_schema is None:
        expected_schema = SCHEMA_V1
    if expected_ros1_msg_sha256 is None:
        expected_ros1_msg_sha256 = ROS1_BSPLINE_MSG_SHA256
    if expected_ros2_msg_sha256 is None:
        expected_ros2_msg_sha256 = ROS2_BSPLINE_MSG_SHA256
    if expected_source_package is None:
        expected_source_package = SOURCE_PACKAGE
    if expected_source_msg_type is None:
        expected_source_msg_type = SOURCE_MSG_TYPE
    if expected_session_pattern is None:
        expected_session_pattern = _HEX_SESSION_RE.pattern
    if int32_min is None:
        int32_min = INT32_MIN
    if int32_max is None:
        int32_max = INT32_MAX
    if int64_min is None:
        int64_min = INT64_MIN
    if int64_max is None:
        int64_max = INT64_MAX
    if nanosec_limit is None:
        nanosec_limit = NANOSEC_LIMIT
    if isinstance(raw_data, (bytes, bytearray, str)):
        envelope = parse_json_bytes(raw_data)
    elif type(raw_data) is dict:
        envelope = raw_data
    else:
        raise BsplineEnvelopeError("invalid_envelope_schema", f"expected bytes, str or dict, got {type(raw_data).__name__}")

    if set(envelope.keys()) != set(envelope_fields):
        raise BsplineEnvelopeError(
            "invalid_envelope_schema",
            f"envelope must have exact keys {_format_keys(envelope_fields)}, got {_format_keys(envelope.keys())}",
        )

    if envelope["schema"] != expected_schema:
        raise BsplineEnvelopeError("invalid_envelope_schema", f"schema mismatch: expected {expected_schema}, got {envelope['schema']!r}")

    session_id = validate_session_id(envelope["transport_session_id"], pattern=expected_session_pattern)
    if expected_session_id is not None and session_id != expected_session_id:
        raise BsplineEnvelopeError("session_mismatch", f"session mismatch: expected {expected_session_id}, got {session_id}")

    seq = envelope["sequence"]
    if isinstance(seq, bool) or type(seq) is not int or seq < 0:
        raise BsplineEnvelopeError("sequence_mismatch", f"sequence must be non-negative int, got {seq!r}")
    if expected_sequence is not None and seq != expected_sequence:
        raise BsplineEnvelopeError("sequence_mismatch", f"sequence mismatch: expected {expected_sequence}, got {seq}")

    if envelope["source_package"] != expected_source_package:
        raise BsplineEnvelopeError("invalid_source", f"source_package mismatch: expected {expected_source_package}, got {envelope['source_package']!r}")
    if envelope["source_msg_type"] != expected_source_msg_type:
        raise BsplineEnvelopeError("invalid_source", f"source_msg_type mismatch: expected {expected_source_msg_type}, got {envelope['source_msg_type']!r}")

    if envelope["ros1_msg_sha256"] != expected_ros1_msg_sha256:
        raise BsplineEnvelopeError(
            "hash_mismatch",
            f"ros1_msg_sha256 mismatch: expected {expected_ros1_msg_sha256}, got {envelope['ros1_msg_sha256']!r}",
        )
    if envelope["ros2_msg_sha256"] != expected_ros2_msg_sha256:
        raise BsplineEnvelopeError(
            "hash_mismatch",
            f"ros2_msg_sha256 mismatch: expected {expected_ros2_msg_sha256}, got {envelope['ros2_msg_sha256']!r}",
        )

    validated_payload = validate_wire_payload(
        envelope["payload"],
        max_points=max_points,
        max_knots=max_knots,
        max_yaw_pts=max_yaw_pts,
        int32_min=int32_min,
        int32_max=int32_max,
        int64_min=int64_min,
        int64_max=int64_max,
        nanosec_limit=nanosec_limit,
        payload_fields=payload_fields,
    )

    return {
        "schema": expected_schema,
        "transport_session_id": session_id,
        "sequence": seq,
        "source_package": expected_source_package,
        "source_msg_type": expected_source_msg_type,
        "ros1_msg_sha256": expected_ros1_msg_sha256,
        "ros2_msg_sha256": expected_ros2_msg_sha256,
        "payload": validated_payload,
    }


def validate_control(control: Any, *,
                     kinds: Tuple[str, ...] = _CONTROL_KINDS_AT_IMPORT) -> Dict[str, Any]:
    """Validate one v2 control payload; return a normalized copy.

    Exact-key, strict-type contracts per kind:
    - ``{"kind": "gate", "open": <strict bool>}`` -- the planner output gate
      (upstream ``ego_command_stop_pub`` Bool; it is ONLY a gate, never a
      cancel);
    - ``{"kind": "hold"}`` -- session hold (no-route); the anchor is
      receiver-local state and is NEVER carried on the wire;
    - ``{"kind": "cancel"}`` -- planner-initiated terminal session cancel.
    """
    if type(control) is not dict:
        raise BsplineEnvelopeError(
            "invalid_control_payload", f"control must be a dict, got {type(control).__name__}")
    kind = control.get("kind")
    if kind not in kinds:
        raise BsplineEnvelopeError(
            "invalid_control_kind", f"unknown control kind: {kind!r}")
    if kind == "gate":
        if set(control.keys()) != {"kind", "open"}:
            raise BsplineEnvelopeError(
                "invalid_control_payload",
                f"gate control must have exactly keys (kind, open), got {sorted(control.keys())}")
        if type(control["open"]) is not bool:
            raise BsplineEnvelopeError(
                "invalid_control_payload", "gate open must be a strict bool")
        return {"kind": "gate", "open": control["open"]}
    if set(control.keys()) != {"kind"}:
        raise BsplineEnvelopeError(
            "invalid_control_payload",
            f"{kind} control must have exactly key (kind), got {sorted(control.keys())}")
    return {"kind": kind}


def parse_and_validate_control_envelope(
    raw_data: bytes | str | Dict[str, Any],
    *,
    expected_session_id: Optional[str] = None,
    expected_sequence: Optional[int] = None,
    expected_session_pattern: Optional[str] = None,
    expected_schema: Optional[str] = None,
    control_fields: Tuple[str, ...] = _CONTROL_ENVELOPE_FIELDS_AT_IMPORT,
    kinds: Tuple[str, ...] = _CONTROL_KINDS_AT_IMPORT,
) -> Dict[str, Any]:
    """Parse and validate one v2 control envelope (schema-discriminated type).

    The v1 Bspline envelope contract is untouched; this is the explicit v2
    type sharing the SAME transport session and sequence counter.
    """
    if expected_session_pattern is None:
        expected_session_pattern = _HEX_SESSION_RE.pattern
    if expected_schema is None:
        expected_schema = CONTROL_SCHEMA_V2
    if isinstance(raw_data, (bytes, bytearray, str)):
        envelope = parse_json_bytes(raw_data)
    elif type(raw_data) is dict:
        envelope = raw_data
    else:
        raise BsplineEnvelopeError(
            "invalid_envelope_schema",
            f"expected bytes, str or dict, got {type(raw_data).__name__}")
    if set(envelope.keys()) != set(control_fields):
        raise BsplineEnvelopeError(
            "invalid_envelope_schema",
            f"control envelope fields must be exactly {list(control_fields)}")
    if envelope["schema"] != expected_schema:
        raise BsplineEnvelopeError(
            "invalid_envelope_schema",
            f"schema mismatch: expected {expected_schema!r}, got {envelope['schema']!r}")
    session_id = validate_session_id(
        envelope["transport_session_id"], pattern=expected_session_pattern)
    if expected_session_id is not None and session_id != expected_session_id:
        raise BsplineEnvelopeError(
            "session_mismatch",
            f"session mismatch: expected {expected_session_id}, got {session_id}")
    seq = envelope["sequence"]
    if isinstance(seq, bool) or type(seq) is not int or seq < 0:
        raise BsplineEnvelopeError(
            "sequence_mismatch", f"sequence must be non-negative int, got {seq!r}")
    if expected_sequence is not None and seq != expected_sequence:
        raise BsplineEnvelopeError(
            "sequence_mismatch",
            f"sequence mismatch: expected {expected_sequence}, got {seq}")
    return {
        "schema": expected_schema,
        "transport_session_id": session_id,
        "sequence": seq,
        "control": validate_control(envelope["control"], kinds=kinds),
    }


def _to_bridge_mapping(
    envelope_or_payload: Dict[str, Any],
    *,
    nanosec_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Convert a VALIDATED envelope payload into the mapping expected by ego_bspline_bridge.

    Private: callers must go through the decoder (or parse_and_validate_envelope)
    first.  This helper does not re-validate; feeding it unvalidated data bypasses
    the envelope contract by definition.

    start_time is converted into exact integer nanoseconds (sec * 1e9 + nanosec) without
    wall-clock translation or time offset. pos_pts is converted to list of (x, y, z) 3-tuples.
    """
    if nanosec_limit is None:
        nanosec_limit = NANOSEC_LIMIT
    if "payload" in envelope_or_payload and isinstance(envelope_or_payload["payload"], dict):
        payload = envelope_or_payload["payload"]
    else:
        payload = envelope_or_payload

    time_obj = payload["start_time"]
    if isinstance(time_obj, dict) and "sec" in time_obj and "nanosec" in time_obj:
        sec = time_obj["sec"]
        nanosec = time_obj["nanosec"]
    else:
        norm_time = normalize_time_input(time_obj, nanosec_limit=nanosec_limit)
        sec = norm_time["sec"]
        nanosec = norm_time["nanosec"]

    start_time_ns = sec * nanosec_limit + nanosec

    pos_pts = [
        (float(p["x"]), float(p["y"]), float(p["z"]))
        if isinstance(p, dict)
        else (float(p[0]), float(p[1]), float(p[2]))
        for p in payload["pos_pts"]
    ]

    return {
        "drone_id": int(payload["drone_id"]),
        "order": int(payload["order"]),
        "traj_id": int(payload["traj_id"]),
        "start_time": start_time_ns,
        "knots": [float(k) for k in payload["knots"]],
        "pos_pts": pos_pts,
        "yaw_pts": [float(y) for y in payload["yaw_pts"]],
        "yaw_dt": float(payload["yaw_dt"]),
    }


def pack_frame(
    payload_bytes: bytes,
    *,
    max_frame_bytes: Optional[int] = None,
    max_payload_bytes: Optional[int] = None,
) -> bytes:
    """Frame payload bytes with 4-byte big-endian unsigned length header (>I).

    Omitted limits use current module defaults; stateful instances pass their
    construction snapshot.  A zero-length payload is never a valid frame.
    """
    if not isinstance(payload_bytes, (bytes, bytearray)):
        raise BsplineEnvelopeError("invalid_frame_header", f"payload_bytes must be bytes or bytearray, got {type(payload_bytes).__name__}")
    if max_frame_bytes is None:
        max_frame_bytes = MAX_FRAME_BYTES
    if max_payload_bytes is None:
        max_payload_bytes = MAX_PAYLOAD_BYTES
    length = len(payload_bytes)
    if length == 0:
        raise BsplineEnvelopeError("invalid_frame_header", "frame payload length must be greater than zero")
    if length > max_payload_bytes or length + 4 > max_frame_bytes:
        raise BsplineEnvelopeError("oversized_frame", f"payload length {length} exceeds maximum {max_payload_bytes}")
    return struct.pack(">I", length) + bytes(payload_bytes)


def _enforce_json_payload_size(raw_bytes_or_str: Any, max_payload_bytes: int) -> None:
    """Reject an already-deframed JSON value whose UTF-8 bytes exceed the instance cap."""
    if isinstance(raw_bytes_or_str, (bytes, bytearray)):
        byte_length = len(raw_bytes_or_str)
    elif isinstance(raw_bytes_or_str, str):
        try:
            byte_length = len(raw_bytes_or_str.encode("utf-8"))
        except UnicodeEncodeError as err:
            raise BsplineEnvelopeError("invalid_json", f"UTF-8 encode failed: {err}") from err
    else:
        # parse_json_bytes() owns the stable type classification for all other
        # values; do not turn a bad type into an unrelated size error here.
        return
    if byte_length > max_payload_bytes:
        raise BsplineEnvelopeError(
            "oversized_frame",
            f"JSON payload length {byte_length} exceeds maximum {max_payload_bytes}",
        )


def unpack_frame_header(
    header_bytes: bytes,
    *,
    max_frame_bytes: Optional[int] = None,
    max_payload_bytes: Optional[int] = None,
) -> int:
    """Unpack 4-byte length prefix and validate against maximum frame size."""
    if not isinstance(header_bytes, (bytes, bytearray)):
        raise BsplineEnvelopeError("invalid_frame_header", f"header_bytes must be bytes or bytearray, got {type(header_bytes).__name__}")
    if len(header_bytes) < 4:
        raise BsplineEnvelopeError("truncated_frame", f"header too short: {len(header_bytes)} < 4")
    if max_frame_bytes is None:
        max_frame_bytes = MAX_FRAME_BYTES
    if max_payload_bytes is None:
        max_payload_bytes = MAX_PAYLOAD_BYTES
    (length,) = struct.unpack(">I", header_bytes[:4])
    if length == 0:
        raise BsplineEnvelopeError("invalid_frame_header", "frame payload length must be greater than zero")
    if length > max_payload_bytes or length + 4 > max_frame_bytes:
        raise BsplineEnvelopeError("oversized_frame", f"frame length header {length} exceeds maximum {max_payload_bytes}")
    return length


class BsplineTcpEncoder:
    """Stateful encoder for Bspline TCP envelope frames.

    Sequence high-water mark advances only upon successful frame construction.
    """

    def __init__(self, session_id: str, initial_sequence: int = 1):
        # Snapshot the frozen identity at construction: later monkeypatching of the
        # module globals cannot alter this instance, and construction re-verifies
        # the pins against the actual repository message files.
        self._protocol = _capture_protocol_snapshot()
        self.session_id = validate_session_id(session_id, pattern=self._protocol.session_pattern)
        if isinstance(initial_sequence, bool) or type(initial_sequence) is not int or initial_sequence < 0:
            raise BsplineEnvelopeError("sequence_mismatch", "initial_sequence must be non-negative integer")
        self.next_sequence = initial_sequence
        self.high_water_sequence = initial_sequence - 1

    def build_envelope(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate payload and construct envelope dictionary without advancing sequence."""
        validated_payload = validate_and_normalize_payload(
            payload,
            max_points=self._protocol.max_points,
            max_knots=self._protocol.max_knots,
            max_yaw_pts=self._protocol.max_yaw_pts,
            int32_min=self._protocol.int32_min,
            int32_max=self._protocol.int32_max,
            int64_min=self._protocol.int64_min,
            int64_max=self._protocol.int64_max,
            nanosec_limit=self._protocol.nanosec_limit,
            payload_fields=self._protocol.payload_fields,
        )
        return {
            "schema": self._protocol.schema,
            "transport_session_id": self.session_id,
            "sequence": self.next_sequence,
            "source_package": self._protocol.source_package,
            "source_msg_type": self._protocol.source_msg_type,
            "ros1_msg_sha256": self._protocol.ros1_msg_sha256,
            "ros2_msg_sha256": self._protocol.ros2_msg_sha256,
            "payload": validated_payload,
        }

    def encode_envelope(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate, construct envelope, and advance sequence high-water mark once."""
        envelope = self.build_envelope(payload)
        self.high_water_sequence = self.next_sequence
        self.next_sequence += 1
        return envelope

    def encode_frame(self, payload: Dict[str, Any]) -> bytes:
        """Validate, serialize to deterministic JSON, frame with >I, and advance sequence once."""
        envelope = self.build_envelope(payload)
        json_bytes = serialize_envelope_json(envelope)
        frame = pack_frame(
            json_bytes,
            max_frame_bytes=self._protocol.max_frame_bytes,
            max_payload_bytes=self._protocol.max_payload_bytes,
        )
        # Advance high-water mark ONLY after serialization and framing succeed completely
        self.high_water_sequence = self.next_sequence
        self.next_sequence += 1
        return frame

    def build_control_envelope(self, control: Dict[str, Any]) -> Dict[str, Any]:
        """Validate one v2 control and construct its envelope WITHOUT advancing the sequence."""
        return {
            "schema": self._protocol.control_schema,
            "transport_session_id": self.session_id,
            "sequence": self.next_sequence,
            "control": validate_control(control, kinds=self._protocol.control_kinds),
        }

    def encode_control_frame(self, control: Dict[str, Any]) -> bytes:
        """Validate, serialize, and frame one v2 control on the SAME sequence counter.

        Bspline and control frames share this instance's ``next_sequence``, so
        both types travel in one ordered TCP sequence stream -- no cross-channel
        reorder is possible.  The sequence advances ONLY after serialization
        and framing succeed completely.
        """
        envelope = self.build_control_envelope(control)
        json_bytes = serialize_envelope_json(envelope)
        frame = pack_frame(
            json_bytes,
            max_frame_bytes=self._protocol.max_frame_bytes,
            max_payload_bytes=self._protocol.max_payload_bytes,
        )
        self.high_water_sequence = self.next_sequence
        self.next_sequence += 1
        return frame


class BsplineTcpDecoder:
    """Stateful decoder for Bspline TCP envelope frames.

    Expected sequence and high-water mark advance only upon successful decoding.
    A frame that fails validation is a poison frame: it stays at the head of the
    stream buffer, blocks this decoder permanently, and recovery requires
    discarding the decoder/connection and starting a new transport_session_id.
    """

    def __init__(self, session_id: str, initial_sequence: int = 1, *,
                 accept_control: bool = False):
        # Same frozen-identity snapshot discipline as the encoder.
        self._protocol = _capture_protocol_snapshot()
        self.session_id = validate_session_id(session_id, pattern=self._protocol.session_pattern)
        if isinstance(initial_sequence, bool) or type(initial_sequence) is not int or initial_sequence < 0:
            raise BsplineEnvelopeError("sequence_mismatch", "initial_sequence must be non-negative integer")
        if type(accept_control) is not bool:
            raise BsplineEnvelopeError("invalid_envelope_schema", "accept_control must be a strict bool")
        # Explicit opt-in: a default decoder is a pure v1 reader; a v2 control
        # frame on it is an unknown schema and poisons exactly like any other
        # contract violation.
        self.accept_control = accept_control
        self.expected_sequence = initial_sequence
        self.high_water_sequence = initial_sequence - 1
        self.last_envelope: Optional[Dict[str, Any]] = None
        self._buffer = bytearray()

    def decode_envelope_payload(self, raw_bytes_or_str: bytes | str) -> Dict[str, Any]:
        """Decode deframed JSON bytes, validate against expected sequence/session, and advance state.

        Returns the normalized bridge mapping ready for ego_bspline_bridge.
        """
        _enforce_json_payload_size(raw_bytes_or_str, self._protocol.max_payload_bytes)
        envelope = parse_and_validate_envelope(
            raw_bytes_or_str,
            expected_session_id=self.session_id,
            expected_sequence=self.expected_sequence,
            expected_schema=self._protocol.schema,
            expected_ros1_msg_sha256=self._protocol.ros1_msg_sha256,
            expected_ros2_msg_sha256=self._protocol.ros2_msg_sha256,
            expected_source_package=self._protocol.source_package,
            expected_source_msg_type=self._protocol.source_msg_type,
            expected_session_pattern=self._protocol.session_pattern,
            max_points=self._protocol.max_points,
            max_knots=self._protocol.max_knots,
            max_yaw_pts=self._protocol.max_yaw_pts,
            int32_min=self._protocol.int32_min,
            int32_max=self._protocol.int32_max,
            int64_min=self._protocol.int64_min,
            int64_max=self._protocol.int64_max,
            nanosec_limit=self._protocol.nanosec_limit,
            payload_fields=self._protocol.payload_fields,
            envelope_fields=self._protocol.envelope_fields,
        )
        mapping = _to_bridge_mapping(envelope["payload"], nanosec_limit=self._protocol.nanosec_limit)
        # Advance high-water mark ONLY after all validation succeeds
        self.high_water_sequence = self.expected_sequence
        self.expected_sequence += 1
        self.last_envelope = envelope
        return mapping

    def decode_frame(self, frame_bytes: bytes) -> Dict[str, Any]:
        """Decode a single standalone complete frame with length header.

        Fails closed on truncated frames, oversized frames, or trailing (spliced) bytes.
        """
        if not isinstance(frame_bytes, (bytes, bytearray)):
            raise BsplineEnvelopeError("invalid_frame_header", "frame_bytes must be bytes or bytearray")
        if len(frame_bytes) < 4:
            raise BsplineEnvelopeError("truncated_frame", f"frame shorter than 4-byte header: {len(frame_bytes)} < 4")
        payload_len = unpack_frame_header(
            frame_bytes[:4],
            max_frame_bytes=self._protocol.max_frame_bytes,
            max_payload_bytes=self._protocol.max_payload_bytes,
        )
        actual_payload_len = len(frame_bytes) - 4
        if actual_payload_len < payload_len:
            raise BsplineEnvelopeError("truncated_frame", f"expected {payload_len} bytes, got {actual_payload_len}")
        if actual_payload_len > payload_len:
            raise BsplineEnvelopeError("spliced_frame", f"frame has trailing bytes: {actual_payload_len} > {payload_len}")
        payload_bytes = frame_bytes[4 : 4 + payload_len]
        return self.decode_envelope_payload(payload_bytes)

    def feed(self, chunk: bytes) -> None:
        """Feed bytes into streaming buffer."""
        if not isinstance(chunk, (bytes, bytearray)):
            raise BsplineEnvelopeError("invalid_frame_header", "chunk must be bytes or bytearray")
        proposed = bytes(self._buffer) + bytes(chunk)
        if len(proposed) > self._protocol.max_buffer_bytes:
            raise BsplineEnvelopeError("oversized_frame", "stream buffer capacity exceeded")
        # Validate every complete frame header before committing the append.
        # Partial headers and partial payloads remain admissible until a later
        # feed completes them.  This keeps zero-length frames out of the
        # buffer even when they follow a complete valid frame in one chunk.
        offset = 0
        while len(proposed) - offset >= 4:
            payload_len = unpack_frame_header(
                proposed[offset : offset + 4],
                max_frame_bytes=self._protocol.max_frame_bytes,
                max_payload_bytes=self._protocol.max_payload_bytes,
            )
            total_len = 4 + payload_len
            if len(proposed) - offset < total_len:
                break
            offset += total_len
        self._buffer.extend(chunk)


    def _peek_frame(self):
        """Deframe the head frame WITHOUT decoding; None if incomplete."""
        if len(self._buffer) < 4:
            return None
        payload_len = unpack_frame_header(
            self._buffer[:4],
            max_frame_bytes=self._protocol.max_frame_bytes,
            max_payload_bytes=self._protocol.max_payload_bytes,
        )
        total_len = 4 + payload_len
        if len(self._buffer) < total_len:
            return None
        return total_len, bytes(self._buffer[4:total_len])

    def _frame_is_control(self, payload_bytes: bytes) -> bool:
        """Best-effort schema peek; malformed JSON is left to the decode path."""
        try:
            envelope = parse_json_bytes(payload_bytes)
        except BsplineEnvelopeError:
            return False
        return (isinstance(envelope, dict)
                and envelope.get("schema") == self._protocol.control_schema)

    def read_frame_any(self):
        """Typed read for control-opt-in consumers: ("bspline", mapping) |
        ("control", control), or None if no complete frame is buffered.

        Both types share this decoder's sequence expectation, so the returned
        order IS the single TCP stream order.
        """
        peek = self._peek_frame()
        if peek is None:
            return None
        total_len, payload_bytes = peek
        if self.accept_control and self._frame_is_control(payload_bytes):
            _enforce_json_payload_size(payload_bytes, self._protocol.max_payload_bytes)
            envelope = parse_and_validate_control_envelope(
                payload_bytes,
                expected_session_id=self.session_id,
                expected_sequence=self.expected_sequence,
                expected_session_pattern=self._protocol.session_pattern,
                expected_schema=self._protocol.control_schema,
                control_fields=self._protocol.control_envelope_fields,
                kinds=self._protocol.control_kinds,
            )
            # Advance high-water mark ONLY after all validation succeeds
            self.high_water_sequence = self.expected_sequence
            self.expected_sequence += 1
            self.last_envelope = envelope
            del self._buffer[:total_len]
            return "control", envelope["control"]
        mapping = self.decode_envelope_payload(payload_bytes)
        del self._buffer[:total_len]
        return "bspline", mapping

    def read_frame(self) -> Optional[Dict[str, Any]]:
        """Attempt to deframe and decode the next Bspline frame from the buffer.

        Returns None if buffer does not have a complete frame yet.
        Legacy v1 contract, stated precisely: this raw decoder has NO poison
        latch of its own.  On a v2 control frame it raises
        ``invalid_envelope_schema`` (decoder without ``accept_control``) or
        ``control_frame_unexpected`` (opted-in decoder) WITHOUT consuming the
        frame: the frame stays buffered, a later ``read_frame_any`` on an
        opted-in decoder can still consume it, and repeated ``read_frame``
        calls keep raising at the same head-of-line frame.  The POISONED state
        is latched by the PUMP (which treats any BsplineEnvelopeError from a
        read as transport poison); calling ``read_frame`` on a mixed stream is
        API misuse with defined recovery (switch to ``read_frame_any``), not
        decoder corruption.  Mixed-stream consumers must use
        ``read_frame_any()`` on an accept_control decoder.
        """
        peek = self._peek_frame()
        if peek is None:
            return None
        total_len, payload_bytes = peek
        if self.accept_control and self._frame_is_control(payload_bytes):
            raise BsplineEnvelopeError(
                "control_frame_unexpected",
                "v2 control frame requires read_frame_any(); read_frame() is bspline-only")
        mapping = self.decode_envelope_payload(payload_bytes)
        # Succeeded: discard the processed frame from buffer
        del self._buffer[:total_len]
        return mapping
