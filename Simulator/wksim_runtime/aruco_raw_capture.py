"""Authentic raw CDR recorder for ArUco joint flight (#104).

Drains native raw CDR from an un-spun raw node via RCTake (libwksim_rc_take.so).
Contains no re-serialization path: missing native CDR/GID/timestamps causes immediate rejection.
"""
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

SCHEMA_VERSION = 1
INITIAL_HASH_SEED = "0" * 64
VALID_CDR_HEADERS = {b"\x00\x00", b"\x00\x01", b"\x00\x02", b"\x00\x03"}

_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")
_HEX_ONLY = re.compile(r"^[0-9a-fA-F]+$")
_RUN_ID_PAT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ChannelSpec(NamedTuple):
    """Specification of a monitored topic channel."""
    topic: str
    msg_type: Any
    qos: Any = None
    type_name: Optional[str] = None


def _validate_run_id(val: Any) -> str:
    if not isinstance(val, str) or not _RUN_ID_PAT.fullmatch(val):
        raise ValueError(f"Invalid run_id: {val!r}")
    return val


def _validate_epoch(val: Any) -> str:
    if not isinstance(val, str) or not _HEX32.fullmatch(val):
        raise ValueError(f"epoch must be a 32-character hex string, got: {val!r}")
    return val


def _validate_stack_and_uav(stack: Any, uav_id: Any) -> Tuple[str, int]:
    if stack not in ("arducopter", "px4"):
        raise ValueError(f"stack must be 'arducopter' or 'px4', got: {stack!r}")
    if isinstance(uav_id, bool) or not isinstance(uav_id, int):
        raise ValueError(f"uav_id must be an integer, got: {uav_id!r}")
    if stack == "arducopter" and uav_id != 1:
        raise ValueError(f"stack 'arducopter' requires uav_id=1, got: {uav_id}")
    if stack == "px4" and uav_id != 2:
        raise ValueError(f"stack 'px4' requires uav_id=2, got: {uav_id}")
    return stack, uav_id


def _validate_drain_limit(val: Any) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or not (1 <= val <= 200):
        raise ValueError(f"max_drain_limit must be an integer in 1..200, got: {val!r}")
    return val


def _validate_no_symlinks(path: Path) -> Path:
    p = path.resolve() if not path.is_symlink() else path
    if p.is_symlink():
        raise ValueError(f"output_path cannot be a symlink: {path}")
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError(f"output_path parent cannot be a symlink: {parent}")
    return p


def _get_type_name(msg_type: Any, explicit_name: Optional[str] = None) -> str:
    if explicit_name:
        return explicit_name
    if isinstance(msg_type, str):
        return msg_type
    if hasattr(msg_type, "__module__") and hasattr(msg_type, "__name__"):
        mod = msg_type.__module__.split(".")[0]
        return f"{mod}/msg/{msg_type.__name__}"
    return str(msg_type)


def _sanitize_for_json(val: Any) -> Any:
    """Encode non-finite floats safely for standard JSON compliance without bare NaN."""
    if isinstance(val, float):
        if math.isnan(val):
            return ":nan:"
        if math.isinf(val):
            return ":inf:" if val > 0 else ":-inf:"
        return val
    if isinstance(val, dict):
        return {k: _sanitize_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize_for_json(v) for v in val]
    return val


def get_builder_sha256() -> str:
    path = Path(__file__).resolve()
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArucoRawCapture:
    """Authentic raw CDR recorder for ArUco joint flight.

    Captures genuine DDS CDR bytes, publisher GID, and timestamps.
    Operates an un-spun raw node. Writing failures raise immediately to fail the task.
    """

    def __init__(
        self,
        output_path: Union[str, Path],
        *,
        run_id: str,
        epoch: str,
        stack: str,
        uav_id: int,
        channels: Optional[Sequence[Union[ChannelSpec, Tuple[str, Any], Tuple[str, Any, Any]]]] = None,
        ros: Optional[Any] = None,
        raw_node: Optional[Any] = None,
        rc_take: Optional[Any] = None,
        convert: Optional[Callable[[Any], Any]] = None,
        node_name: Optional[str] = None,
        max_drain_limit: int = 200,
    ):
        self.run_id = _validate_run_id(run_id)
        self.epoch = _validate_epoch(epoch)
        self.stack, self.uav_id = _validate_stack_and_uav(stack, uav_id)
        self.max_drain_limit = _validate_drain_limit(max_drain_limit)
        self.node_name = node_name if node_name is not None else f"wksim_aruco_raw_{self.stack}"
        self.convert = convert

        raw_path = Path(output_path)
        self.output_path = _validate_no_symlinks(raw_path)
        if self.output_path.is_dir():
            raise ValueError(f"output_path cannot be an existing directory: {self.output_path}")

        if channels is None:
            self.channel_specs = build_default_aruco_channels(self.uav_id, self.stack)
        else:
            if not channels:
                raise ValueError("channels list cannot be empty")
            self.channel_specs = []
            for ch in channels:
                if isinstance(ch, ChannelSpec):
                    spec = ch
                elif isinstance(ch, (tuple, list)):
                    if len(ch) == 2:
                        spec = ChannelSpec(topic=ch[0], msg_type=ch[1], qos=None)
                    elif len(ch) >= 3:
                        spec = ChannelSpec(topic=ch[0], msg_type=ch[1], qos=ch[2])
                    else:
                        raise ValueError(f"Invalid channel specification tuple: {ch!r}")
                else:
                    raise ValueError(f"Unsupported channel spec type: {type(ch)!r}")
                if not spec.topic or not isinstance(spec.topic, str):
                    raise ValueError(f"Invalid channel topic: {spec.topic!r}")
                tname = _get_type_name(spec.msg_type, spec.type_name)
                self.channel_specs.append(ChannelSpec(topic=spec.topic, msg_type=spec.msg_type, qos=spec.qos, type_name=tname))

        self.is_closed = False
        self.status = "recording"
        self.take_sequence = 0
        self.current_hash = INITIAL_HASH_SEED
        self.samples_per_topic: Dict[str, int] = defaultdict(int)
        self.latest_samples: Dict[str, dict] = {}
        self.write_failures = 0
        self.write_failure_reports: List[Dict[str, Any]] = []

        self._owned_node = False
        self.subscriptions: List[Tuple[Any, ChannelSpec]] = []

        try:
            # Setup RCTake
            if rc_take is not None:
                self.rc_take = rc_take
            else:
                from prometheus_control.rc_transport import RCTake
                self.rc_take = RCTake()

            # Record provenance
            self.source_sha256 = get_builder_sha256()
            self.rc_take_source_sha256 = "mock"
            self.rc_take_lib_sha256 = "mock"
            try:
                import inspect
                rc_mod = inspect.getfile(self.rc_take.__class__)
                if os.path.isfile(rc_mod):
                    self.rc_take_source_sha256 = hashlib.sha256(Path(rc_mod).read_bytes()).hexdigest()
            except Exception:
                pass
            if hasattr(self.rc_take, "path") and Path(self.rc_take.path).is_file():
                self.rc_take_lib_sha256 = hashlib.sha256(Path(self.rc_take.path).read_bytes()).hexdigest()
            if rc_take is None and any(not re.fullmatch('[0-9a-f]{64}', value) for value in
                    (self.rc_take_source_sha256, self.rc_take_lib_sha256)):
                raise ValueError('Native RCTake source/library provenance is missing')

            # Setup raw_node
            if raw_node is not None:
                self.raw_node = raw_node
            elif ros is not None:
                self.raw_node = ros.create_node(self.node_name)
                self._owned_node = True
            else:
                import rclpy
                self.raw_node = rclpy.create_node(self.node_name)
                self._owned_node = True

            for spec in self.channel_specs:
                qos = spec.qos
                if qos is None:
                    from rclpy.qos import QoSProfile, ReliabilityPolicy
                    qos = QoSProfile(depth=200, reliability=ReliabilityPolicy.RELIABLE)
                sub = self.raw_node.create_subscription(spec.msg_type, spec.topic, lambda _: None, qos)
                self.subscriptions.append((sub, spec))

            # Open output file strictly exclusively (fails if exists)
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = self.output_path.open("x", buffering=1, encoding="utf-8")

            # Write start record and seed hash chain
            start_record = {
                "schema_version": SCHEMA_VERSION,
                "kind": "aruco_raw_capture_start",
                "run_id": self.run_id,
                "epoch": self.epoch,
                "stack": self.stack,
                "uav_id": self.uav_id,
                "node_name": self.node_name,
                "source_identity": {
                    "builder": "Simulator/wksim_runtime/aruco_raw_capture.py",
                    "builder_sha256": self.source_sha256,
                    "rc_take_source_sha256": self.rc_take_source_sha256,
                    "rc_take_lib_sha256": self.rc_take_lib_sha256,
                },
                "channels": [{"topic": c.topic, "type": c.type_name} for c in self.channel_specs],
                "start_monotonic_ns": time.monotonic_ns(),
                "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._write_canonical_record(start_record)
        except Exception as exc:
            self._cleanup_on_init_failure()
            if self.status == 'cleanup_failed':
                raise RuntimeError(str(exc)+'; cleanup: '+str(self.write_failure_reports)) from exc
            raise

    def _cleanup_on_init_failure(self):
        """Clean up partially allocated resources on construction failure."""
        if hasattr(self, "log_file") and not self.log_file.closed:
            try:
                self.log_file.close()
            except Exception as error:
                self.status = 'cleanup_failed'
                self.write_failure_reports.append(dict(error='Construction log close failed: '+str(error)))
        # Preserve both pre-existing evidence and this failed attempt's partial
        # file. An exclusive-open failure never transfers ownership to us.
        self._cleanup_resources()

    def _write_canonical_record(self, record: Dict[str, Any]):
        """Hash the record via canonical JSON, attach hash, and write immediately. Raises on failure."""
        if self.is_closed:
            self.status = "write_failed"
            self.write_failures += 1
            raise IOError("Attempted write to closed ArucoRawCapture")

        record["prev_record_sha256"] = self.current_hash
        canonical_bytes = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        record_sha = hashlib.sha256(canonical_bytes).hexdigest()
        record["record_sha256"] = record_sha
        self.current_hash = record_sha

        line = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        try:
            self.log_file.write(line)
        except Exception as err:
            self.status = "write_failed"
            self.write_failures += 1
            self.write_failure_reports.append({
                "error": str(err),
                "kind": record.get("kind"),
                "take_sequence": record.get("take_sequence"),
                "monotonic_ns": time.monotonic_ns(),
            })
            raise IOError(f"ArucoRawCapture write failure: {err}") from err

    def drain(self, max_per_sub: Optional[int] = None) -> int:
        """Bounded synchronous drain across all subscriptions.

        Raises RuntimeError if any subscription fails to quiesce within limit.
        Raises IOError immediately on write failure.
        """
        if self.is_closed:
            raise RuntimeError("Cannot drain closed ArucoRawCapture")

        limit = _validate_drain_limit(max_per_sub) if max_per_sub is not None else self.max_drain_limit
        total_drained = 0

        for sub, spec in self.subscriptions:
            for count in range(limit):
                sample = self.rc_take.take(sub)
                if sample is None:
                    break

                try:
                    msg, info = sample
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Invalid sample tuple returned by RCTake: {err}") from err

                # Validate authentic raw CDR hex
                if info is None or not hasattr(info, "cdr_hex") or info.cdr_hex is None:
                    raise ValueError("Missing native raw CDR: re-serialization is strictly prohibited")
                cdr_hex = info.cdr_hex
                if not isinstance(cdr_hex, str) or len(cdr_hex) % 2 != 0 or len(cdr_hex) < 8 or not _HEX_ONLY.fullmatch(cdr_hex):
                    raise ValueError(f"Invalid raw CDR hex (must be even length >= 8 hex chars): {cdr_hex!r}")

                cdr_bytes = bytes.fromhex(cdr_hex)
                if cdr_bytes[:2] not in VALID_CDR_HEADERS:
                    raise ValueError(f"Invalid CDR encapsulation header: {cdr_bytes[:2].hex()}")

                # Validate publisher GID
                if not hasattr(info, "publisher_gid") or info.publisher_gid is None:
                    raise ValueError("Missing native publisher GID from RCTake info")
                gid = info.publisher_gid
                if isinstance(gid, str):
                    try:
                        gid_bytes = bytes.fromhex(gid)
                    except ValueError:
                        raise ValueError(f"Invalid hex publisher_gid string: {gid!r}")
                elif isinstance(gid, (bytes, bytearray)):
                    gid_bytes = bytes(gid)
                else:
                    try:
                        gid_bytes = bytes(gid)
                    except Exception:
                        raise ValueError(f"Invalid publisher GID type: {type(gid)!r}")

                if len(gid_bytes) == 0 or not any(b != 0 for b in gid_bytes):
                    raise ValueError("publisher_gid must be non-empty and non-zero bytes")
                gid_hex = gid_bytes.hex()

                # Validate timestamps
                if not hasattr(info, "source_timestamp") or not hasattr(info, "received_timestamp"):
                    raise ValueError("source_timestamp and received_timestamp must be present on info")
                src_ts = info.source_timestamp
                rcv_ts = info.received_timestamp
                if isinstance(src_ts, bool) or not isinstance(src_ts, int) or isinstance(rcv_ts, bool) or not isinstance(rcv_ts, int):
                    raise ValueError("source_timestamp and received_timestamp must be integer nanoseconds, not bool")

                decoded_msg = None
                if self.convert is not None:
                    try:
                        decoded_msg = _sanitize_for_json(self.convert(msg))
                    except Exception as conv_err:
                        decoded_msg = {"conversion_error": str(conv_err)}
                elif isinstance(msg, dict):
                    decoded_msg = _sanitize_for_json(msg)

                self.take_sequence += 1
                topic_name = getattr(sub, "topic_name", spec.topic)
                self.samples_per_topic[topic_name] += 1

                record = {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "raw_cdr_sample",
                    "take_sequence": self.take_sequence,
                    "topic": topic_name,
                    "type": spec.type_name,
                    "monotonic_ns": time.monotonic_ns(),
                    "cdr_hex": cdr_hex,
                    "publisher_gid": gid_hex,
                    "source_timestamp": src_ts,
                    "received_timestamp": rcv_ts,
                    "message": decoded_msg,
                }
                self._write_canonical_record(record)
                self.latest_samples[topic_name] = record
                total_drained += 1
            else:
                raise RuntimeError(
                    f"ArUco raw capture queue for topic '{spec.topic}' did not quiesce within bound ({limit})"
                )

        return total_drained

    def close(self) -> Dict[str, Any]:
        """Close capture file, seal hash chain with end record, and release resources."""
        if self.is_closed:
            return self.get_summary()

        end_status = "complete" if (self.status != "write_failed" and self.write_failures == 0) else "write_failed"
        end_record = {
            "schema_version": SCHEMA_VERSION,
            "kind": "aruco_raw_capture_end",
            "status": end_status,
            "total_samples": self.take_sequence,
            "samples_per_topic": dict(self.samples_per_topic),
            "final_hash_chain": self.current_hash,
            "write_failures": self.write_failures,
            "write_failure_reports": list(self.write_failure_reports),
            "close_monotonic_ns": time.monotonic_ns(),
            "close_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        try:
            if hasattr(self, "log_file") and not self.log_file.closed:
                self._write_canonical_record(end_record)
                self.log_file.flush()
        except Exception as err:
            self.status = "write_failed"
            self.write_failures += 1
            self.write_failure_reports.append({"error": f"Failed writing end record: {err}"})
        finally:
            if hasattr(self, "log_file") and not self.log_file.closed:
                try:
                    self.log_file.close()
                except Exception as close_err:
                    self.status = "write_failed"
                    self.write_failure_reports.append({"error": f"Failed closing log file: {close_err}"})
            self.is_closed = True
            self._cleanup_resources()

        return self.get_summary()

    def _cleanup_resources(self):
        if hasattr(self, "raw_node") and self.raw_node is not None:
            if hasattr(self, "subscriptions"):
                for sub, _ in self.subscriptions:
                    if hasattr(self.raw_node, "destroy_subscription"):
                        try:
                            self.raw_node.destroy_subscription(sub)
                        except Exception as error:
                            self.status = 'cleanup_failed'
                            self.write_failure_reports.append(dict(error='Destroy subscription failed: '+str(error)))
            if getattr(self, "_owned_node", False):
                if hasattr(self.raw_node, "destroy_node"):
                    try:
                        self.raw_node.destroy_node()
                    except Exception as error:
                        self.status = 'cleanup_failed'
                        self.write_failure_reports.append(dict(error='Destroy raw node failed: '+str(error)))

    def get_summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "epoch": self.epoch,
            "stack": self.stack,
            "uav_id": self.uav_id,
            "output_path": str(self.output_path),
            "is_closed": self.is_closed,
            "status": (self.status if self.status in ('write_failed','cleanup_failed') else
                       'complete' if self.is_closed else 'recording'),
            "total_samples": self.take_sequence,
            "samples_per_topic": dict(self.samples_per_topic),
            "final_hash_chain": self.current_hash,
            "write_failures": self.write_failures,
            "write_failure_reports": list(self.write_failure_reports),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def build_default_aruco_channels(uav_id: int, flight_stack: str) -> List[ChannelSpec]:
    """Return default monitored channels: strictly v2/setup and v2/command with REL QoS depth=200."""
    _validate_stack_and_uav(flight_stack, uav_id)
    topic_root = f"/uav{uav_id}/prometheus/"

    from wksim_msgs.msg import SetupRequest, CommandRequest
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    rel_qos = QoSProfile(depth=200, reliability=ReliabilityPolicy.RELIABLE)

    return [
        ChannelSpec(topic=f"{topic_root}v2/setup", msg_type=SetupRequest, qos=rel_qos, type_name="wksim_msgs/msg/SetupRequest"),
        ChannelSpec(topic=f"{topic_root}v2/command", msg_type=CommandRequest, qos=rel_qos, type_name="wksim_msgs/msg/CommandRequest"),
    ]
