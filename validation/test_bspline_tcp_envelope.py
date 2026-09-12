"""Unit tests for #102 Bspline TCP envelope framing, validation, and bridge contract."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_planning.ego_bspline_bridge import bridge_bspline
from Simulator.wksim_planning.ego_evaluator import EgoSpline, UniformBspline
from Simulator.wksim_runtime.bspline_tcp_envelope import (
    BSPLINE_PAYLOAD_FIELDS,
    ENVELOPE_FIELDS,
    ENVELOPE_REASONS,
    INT32_MAX,
    INT32_MIN,
    INT64_MAX,
    INT64_MIN,
    MAX_FRAME_BYTES,
    MAX_KNOTS,
    MAX_PAYLOAD_BYTES,
    MAX_POINTS,
    MAX_YAW_PTS,
    NANOSEC_LIMIT,
    ROS1_BSPLINE_MSG_SHA256,
    ROS2_BSPLINE_MSG_SHA256,
    SCHEMA_V1,
    SOURCE_MSG_TYPE,
    SOURCE_PACKAGE,
    BsplineEnvelopeError,
    BsplineTcpDecoder,
    BsplineTcpEncoder,
    normalize_point_input,
    normalize_time_input,
    pack_frame,
    parse_and_validate_envelope,
    parse_json_bytes,
    serialize_envelope_json,
    _to_bridge_mapping,
    unpack_frame_header,
    validate_and_normalize_payload,
    validate_session_id,
    validate_wire_payload,
    validate_wire_point,
    validate_wire_time,
)

VALID_SESSION_ID = "0123456789abcdef0123456789abcdef"
OTHER_SESSION_ID = "fedcba9876543210fedcba9876543210"


def make_valid_payload(
    points_count: int = 7,
    scale: float = 0.5,
    sec: int = 0,
    nanosec: int = 5_000_000,
    traj_id: int = 1,
    drone_id: int = 0,
    order: int = 3,
):
    """Construct a valid raw input payload compatible with ROS1 relay and ego_bspline_bridge."""
    cps = [(float(i) * scale, 0.0, 1.0) for i in range(points_count)]
    knots = list(UniformBspline(order, cps, 0.1).knots)
    return {
        "drone_id": drone_id,
        "order": order,
        "traj_id": traj_id,
        "start_time": {"secs": sec, "nsecs": nanosec},
        "knots": knots,
        "pos_pts": cps,
        "yaw_pts": [],
        "yaw_dt": 0.0,
    }


class BsplineTcpEnvelopeTests(unittest.TestCase):
    def assert_envelope_error(self, reason: str, callable_obj, *args, **kwargs):
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_repository_message_hashes_pinned_and_exact(self):
        """Verify that pinned hash constants match exact bytes of the repository msg files."""
        repo_root = Path(__file__).resolve().parent.parent
        ros1_file = repo_root / "Modules" / "common" / "prometheus_msgs" / "msg" / "Bspline.msg"
        ros2_file = repo_root / "ros2" / "src" / "prometheus_msgs" / "msg" / "Bspline.msg"

        self.assertTrue(ros1_file.exists(), f"missing ROS1 msg file: {ros1_file}")
        self.assertTrue(ros2_file.exists(), f"missing ROS2 msg file: {ros2_file}")

        computed_ros1_sha = hashlib.sha256(ros1_file.read_bytes()).hexdigest()
        computed_ros2_sha = hashlib.sha256(ros2_file.read_bytes()).hexdigest()

        self.assertEqual(computed_ros1_sha, ROS1_BSPLINE_MSG_SHA256)
        self.assertEqual(computed_ros2_sha, ROS2_BSPLINE_MSG_SHA256)

    def test_message_pin_fallback_requires_both_canonical_paths_absent(self):
        """Installed modules use frozen assets only when the repo pair is absent."""
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        repo_root = Path(__file__).resolve().parent.parent
        ros1_bytes = (repo_root / "Modules" / "common" / "prometheus_msgs" / "msg" / "Bspline.msg").read_bytes()
        ros2_bytes = (repo_root / "ros2" / "src" / "prometheus_msgs" / "msg" / "Bspline.msg").read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            canonical = base / "canonical"
            fallback = base / "message_pins"
            canonical.mkdir()
            fallback.mkdir()
            canonical_ros1 = canonical / "ros1_Bspline.msg"
            canonical_ros2 = canonical / "ros2_Bspline.msg"
            fallback_ros1 = fallback / "ros1_Bspline.msg"
            fallback_ros2 = fallback / "ros2_Bspline.msg"
            canonical_ros1.write_bytes(ros1_bytes)
            canonical_ros2.write_bytes(ros2_bytes)
            fallback_ros1.write_bytes(ros1_bytes)
            fallback_ros2.write_bytes(ros2_bytes)
            with patch.object(module, "ROS1_MSG_FILE", canonical_ros1), \
                    patch.object(module, "ROS2_MSG_FILE", canonical_ros2), \
                    patch.object(module, "ROS1_MESSAGE_PIN_FILE", fallback_ros1), \
                    patch.object(module, "ROS2_MESSAGE_PIN_FILE", fallback_ros2):
                fallback_ros1.write_bytes(b'bad fallback must not replace canonical')
                module._verify_repo_msg_pins(ROS1_BSPLINE_MSG_SHA256, ROS2_BSPLINE_MSG_SHA256)
                fallback_ros1.write_bytes(ros1_bytes)
                canonical_ros1.write_bytes(b'drifted canonical must fail despite valid fallback')
                with self.assertRaises(BsplineEnvelopeError):
                    module._verify_repo_msg_pins(ROS1_BSPLINE_MSG_SHA256, ROS2_BSPLINE_MSG_SHA256)
                canonical_ros1.write_bytes(ros1_bytes)
                canonical_ros2.unlink()
                with self.assertRaisesRegex(BsplineEnvelopeError, "ros2 Bspline.msg missing"):
                    module._verify_repo_msg_pins(ROS1_BSPLINE_MSG_SHA256, ROS2_BSPLINE_MSG_SHA256)
                canonical_ros1.unlink()
                module._verify_repo_msg_pins(ROS1_BSPLINE_MSG_SHA256, ROS2_BSPLINE_MSG_SHA256)
                fallback_ros1.write_bytes(b'drifted installed asset')
                with self.assertRaises(BsplineEnvelopeError):
                    module._verify_repo_msg_pins(ROS1_BSPLINE_MSG_SHA256, ROS2_BSPLINE_MSG_SHA256)

    def test_no_ros_imports(self):
        """Verify that neither rospy nor rclpy has been imported."""
        self.assertNotIn("rospy", sys.modules)
        self.assertNotIn("rclpy", sys.modules)

    def test_happy_path_roundtrip_and_bridge_execution(self):
        """Test full encode -> wire frame -> decode -> bridge_bspline execution."""
        encoder = BsplineTcpEncoder(VALID_SESSION_ID, initial_sequence=1)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID, initial_sequence=1)

        raw_in = make_valid_payload(sec=10, nanosec=5_000_000, traj_id=42)
        frame_bytes = encoder.encode_frame(raw_in)

        self.assertIsInstance(frame_bytes, bytes)
        self.assertGreater(len(frame_bytes), 4)
        header_len = struct.unpack(">I", frame_bytes[:4])[0]
        self.assertEqual(header_len, len(frame_bytes) - 4)

        mapping = decoder.decode_frame(frame_bytes)

        # Check decoded mapping fields
        self.assertEqual(set(mapping.keys()), set(BSPLINE_PAYLOAD_FIELDS))
        self.assertEqual(mapping["drone_id"], 0)
        self.assertEqual(mapping["order"], 3)
        self.assertEqual(mapping["traj_id"], 42)
        self.assertEqual(mapping["start_time"], 10 * 1_000_000_000 + 5_000_000)
        self.assertEqual(mapping["yaw_pts"], [])
        self.assertEqual(mapping["yaw_dt"], 0.0)
        self.assertIsInstance(mapping["pos_pts"], list)
        self.assertTrue(all(isinstance(p, tuple) and len(p) == 3 for p in mapping["pos_pts"]))

        # Check state advances
        self.assertEqual(encoder.next_sequence, 2)
        self.assertEqual(encoder.high_water_sequence, 1)
        self.assertEqual(decoder.expected_sequence, 2)
        self.assertEqual(decoder.high_water_sequence, 1)

        # Directly pass mapping into bridge_bspline without alteration
        spline, traj_id, start_tick = bridge_bspline(
            mapping,
            anchor_ns=10 * 1_000_000_000,
            current_tick=0,
        )
        self.assertEqual(traj_id, 42)
        self.assertEqual(start_tick, 5)
        self.assertIsInstance(spline, EgoSpline)
        self.assertEqual(len(spline.position.knots), len(mapping["knots"]))

    def test_wire_envelope_exact_metadata(self):
        """Verify all exact envelope top-level keys, hashes, and schema."""
        encoder = BsplineTcpEncoder(VALID_SESSION_ID, initial_sequence=1)
        raw_in = make_valid_payload()
        envelope = encoder.encode_envelope(raw_in)

        self.assertEqual(set(envelope.keys()), set(ENVELOPE_FIELDS))
        self.assertEqual(envelope["schema"], SCHEMA_V1)
        self.assertEqual(envelope["transport_session_id"], VALID_SESSION_ID)
        self.assertEqual(envelope["sequence"], 1)
        self.assertEqual(envelope["source_package"], SOURCE_PACKAGE)
        self.assertEqual(envelope["source_msg_type"], SOURCE_MSG_TYPE)
        self.assertEqual(envelope["ros1_msg_sha256"], ROS1_BSPLINE_MSG_SHA256)
        self.assertEqual(envelope["ros2_msg_sha256"], ROS2_BSPLINE_MSG_SHA256)

        # Check wire payload structure
        wire_payload = envelope["payload"]
        self.assertEqual(set(wire_payload.keys()), set(BSPLINE_PAYLOAD_FIELDS))
        self.assertEqual(set(wire_payload["start_time"].keys()), {"sec", "nanosec"})
        for pt in wire_payload["pos_pts"]:
            self.assertEqual(set(pt.keys()), {"x", "y", "z"})

    def test_session_id_validation_strict(self):
        """Verify strict 32 lowercase hex characters requirement."""
        bad_sessions = [
            "",
            "123",
            "0123456789abcdef0123456789abcde",        # 31 chars
            "0123456789abcdef0123456789abcdef0",       # 33 chars
            "0123456789abcdef0123456789abcdef\n",       # fullmatch, no trailing newline
            "0123456789ABCDEF0123456789ABCDEF",       # uppercase hex
            "0123456789abcdef0123456789abcdeg",       # 'g' not hex
            12345678901234567890123456789012,          # int
            None,
        ]
        for bad in bad_sessions:
            with self.subTest(bad=bad):
                self.assert_envelope_error("invalid_session_id", validate_session_id, bad)
                self.assert_envelope_error("invalid_session_id", BsplineTcpEncoder, bad)
                self.assert_envelope_error("invalid_session_id", BsplineTcpDecoder, bad)

        # Decoder session mismatch
        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(OTHER_SESSION_ID)
        frame = encoder.encode_frame(make_valid_payload())
        self.assert_envelope_error("session_mismatch", decoder.decode_frame, frame)

    def test_sequence_monotonicity_and_high_water_invariants(self):
        """Verify strict sequence increase, rewind rejection, duplicate rejection, and state preservation."""
        encoder = BsplineTcpEncoder(VALID_SESSION_ID, initial_sequence=10)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID, initial_sequence=10)

        # Sequence 10: success
        frame_10 = encoder.encode_frame(make_valid_payload())
        self.assertEqual(encoder.next_sequence, 11)
        self.assertEqual(encoder.high_water_sequence, 10)

        decoder.decode_frame(frame_10)
        self.assertEqual(decoder.expected_sequence, 11)
        self.assertEqual(decoder.high_water_sequence, 10)

        # Duplicate sequence 10: must reject and not advance decoder state
        self.assert_envelope_error("sequence_mismatch", decoder.decode_frame, frame_10)
        self.assertEqual(decoder.expected_sequence, 11)
        self.assertEqual(decoder.high_water_sequence, 10)

        # Sequence 11: success
        frame_11 = encoder.encode_frame(make_valid_payload())
        self.assertEqual(encoder.next_sequence, 12)
        decoder.decode_frame(frame_11)
        self.assertEqual(decoder.expected_sequence, 12)

        # Sequence rewind (feeding frame 10 again): reject
        self.assert_envelope_error("sequence_mismatch", decoder.decode_frame, frame_10)
        self.assertEqual(decoder.expected_sequence, 12)

        # Sequence skip: construct a frame with sequence 15 when expecting 12
        bad_envelope = encoder.build_envelope(make_valid_payload())
        bad_envelope["sequence"] = 15
        bad_frame = pack_frame(serialize_envelope_json(bad_envelope))
        self.assert_envelope_error("sequence_mismatch", decoder.decode_frame, bad_frame)
        self.assertEqual(decoder.expected_sequence, 12)

        # Encoder failure does not advance encoder high-water mark
        bad_payload = make_valid_payload()
        bad_payload["order"] = -1  # invalid order
        self.assert_envelope_error("invalid_field", encoder.encode_frame, bad_payload)
        self.assertEqual(encoder.next_sequence, 12)
        self.assertEqual(encoder.high_water_sequence, 11)

        # Subsequent valid payload with sequence 12 succeeds
        frame_12 = encoder.encode_frame(make_valid_payload())
        self.assertEqual(encoder.next_sequence, 13)
        self.assertEqual(encoder.high_water_sequence, 12)
        decoder.decode_frame(frame_12)
        self.assertEqual(decoder.expected_sequence, 13)
        self.assertEqual(decoder.high_water_sequence, 12)

    def test_schema_and_source_and_hash_mismatches(self):
        """Test rejection when schema, source package/type, or hashes are mutated."""
        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)

        base_envelope = encoder.build_envelope(make_valid_payload())

        # Schema mismatch
        bad_env = dict(base_envelope, schema="wksim.bspline-tcp-envelope.v2")
        frame = pack_frame(serialize_envelope_json(bad_env))
        self.assert_envelope_error("invalid_envelope_schema", decoder.decode_frame, frame)

        # Extra key in envelope
        bad_env = dict(base_envelope, extra_field=1)
        frame = pack_frame(serialize_envelope_json(bad_env))
        self.assert_envelope_error("invalid_envelope_schema", decoder.decode_frame, frame)

        # Missing key in envelope
        bad_env = dict(base_envelope)
        del bad_env["source_package"]
        frame = pack_frame(serialize_envelope_json(bad_env))
        self.assert_envelope_error("invalid_envelope_schema", decoder.decode_frame, frame)

        # Source package mismatch
        bad_env = dict(base_envelope, source_package="other_msgs")
        frame = pack_frame(serialize_envelope_json(bad_env))
        self.assert_envelope_error("invalid_source", decoder.decode_frame, frame)

        # Source msg type mismatch
        bad_env = dict(base_envelope, source_msg_type="other_msgs/Other")
        frame = pack_frame(serialize_envelope_json(bad_env))
        self.assert_envelope_error("invalid_source", decoder.decode_frame, frame)

        # ROS 1 hash mismatch
        bad_env = dict(base_envelope, ros1_msg_sha256="0" * 64)
        frame = pack_frame(serialize_envelope_json(bad_env))
        self.assert_envelope_error("hash_mismatch", decoder.decode_frame, frame)

        # ROS 2 hash mismatch
        bad_env = dict(base_envelope, ros2_msg_sha256="1" * 64)
        frame = pack_frame(serialize_envelope_json(bad_env))
        self.assert_envelope_error("hash_mismatch", decoder.decode_frame, frame)

    def test_duplicate_json_keys_rejected(self):
        """Verify that duplicate JSON keys at any level are strictly rejected."""
        # Duplicate top-level key
        dup_top = b'{"schema": "wksim.bspline-tcp-envelope.v1", "schema": "wksim.bspline-tcp-envelope.v1"}'
        self.assert_envelope_error("duplicate_key", parse_json_bytes, dup_top)

        # Duplicate payload key
        dup_payload = b'{"drone_id": 0, "drone_id": 0}'
        self.assert_envelope_error("duplicate_key", parse_json_bytes, dup_payload)

        # Duplicate point coordinate key
        dup_pt = b'{"x": 0.0, "x": 1.0, "y": 0.0, "z": 0.0}'
        self.assert_envelope_error("duplicate_key", parse_json_bytes, dup_pt)

    def test_nan_and_inf_json_constants_rejected(self):
        """Verify that NaN, Infinity, -Infinity are rejected during JSON decode."""
        for bad_constant in [b'{"val": NaN}', b'{"val": Infinity}', b'{"val": -Infinity}']:
            with self.subTest(bad=bad_constant):
                self.assert_envelope_error("invalid_field", parse_json_bytes, bad_constant)

    def test_boolean_rejection_for_integers_and_floats(self):
        """Verify that booleans are strictly rejected wherever numbers are expected."""
        bool_cases = [
            ("drone_id", True, "invalid_field"),
            ("order", False, "invalid_field"),
            ("traj_id", True, "invalid_field"),
            ("yaw_dt", True, "invalid_field"),
        ]
        for field, bad_val, reason in bool_cases:
            with self.subTest(field=field):
                payload = make_valid_payload()
                payload[field] = bad_val
                self.assert_envelope_error(reason, validate_and_normalize_payload, payload)

        # Bool in knots
        payload = make_valid_payload()
        payload["knots"][0] = True
        self.assert_envelope_error("invalid_field", validate_and_normalize_payload, payload)

        # Bool in pos_pts
        payload = make_valid_payload()
        payload["pos_pts"][0] = (True, 0.0, 1.0)
        self.assert_envelope_error("invalid_point", validate_and_normalize_payload, payload)

        # Bool in start_time
        payload = make_valid_payload()
        payload["start_time"] = {"sec": True, "nanosec": 0}
        self.assert_envelope_error("invalid_time", validate_and_normalize_payload, payload)

        payload = make_valid_payload()
        payload["start_time"] = {"sec": 0, "nanosec": False}
        self.assert_envelope_error("invalid_time", validate_and_normalize_payload, payload)

    def test_integer_ranges_and_bounds(self):
        """Verify int32 and int64 boundaries."""
        # drone_id int32
        payload = make_valid_payload(drone_id=INT32_MAX + 1)
        self.assert_envelope_error("invalid_field", validate_and_normalize_payload, payload)

        payload = make_valid_payload(drone_id=INT32_MIN - 1)
        self.assert_envelope_error("invalid_field", validate_and_normalize_payload, payload)

        # order int32 and order > 0
        payload = make_valid_payload()
        payload["order"] = 0
        self.assert_envelope_error("invalid_field", validate_and_normalize_payload, payload)

        payload = make_valid_payload()
        payload["order"] = INT32_MAX + 1
        self.assert_envelope_error("invalid_field", validate_and_normalize_payload, payload)

        # traj_id int64
        payload = make_valid_payload(traj_id=INT64_MAX + 1)
        self.assert_envelope_error("invalid_field", validate_and_normalize_payload, payload)

        payload = make_valid_payload(traj_id=INT64_MIN - 1)
        self.assert_envelope_error("invalid_field", validate_and_normalize_payload, payload)

    def test_start_time_validation(self):
        """Verify time secs/nsecs -> sec/nanosec, boundaries and 0 <= nanosec < 1e9."""
        # Valid secs/nsecs input
        t1 = normalize_time_input({"secs": 10, "nsecs": 500})
        self.assertEqual(t1, {"sec": 10, "nanosec": 500})

        # Valid sec/nanosec input
        t2 = normalize_time_input({"sec": 10, "nanosec": 500})
        self.assertEqual(t2, {"sec": 10, "nanosec": 500})

        # Negative sec
        self.assert_envelope_error("invalid_time", normalize_time_input, {"sec": -1, "nanosec": 0})

        # Negative nanosec
        self.assert_envelope_error("invalid_time", normalize_time_input, {"sec": 0, "nanosec": -1})

        # nanosec >= 1_000_000_000
        self.assert_envelope_error("invalid_time", normalize_time_input, {"sec": 0, "nanosec": NANOSEC_LIMIT})
        self.assert_envelope_error("invalid_time", normalize_time_input, {"sec": 0, "nanosec": NANOSEC_LIMIT + 1})

        # Float sec / nanosec
        self.assert_envelope_error("invalid_time", normalize_time_input, {"sec": 1.5, "nanosec": 0})
        self.assert_envelope_error("invalid_time", normalize_time_input, {"sec": 0, "nanosec": 1.5})

        # Extra key in time dict
        self.assert_envelope_error("invalid_time", normalize_time_input, {"sec": 0, "nanosec": 0, "extra": 1})

    def test_mixed_mapping_keys_never_leak_sort_or_key_errors(self):
        """Mixed key types produce stable reason-coded errors instead of TypeError."""
        mixed_time = {"sec": 0, "nanosec": 0, 1: 0, ("extra",): 0}
        self.assert_envelope_error("invalid_time", normalize_time_input, mixed_time)
        self.assert_envelope_error("invalid_time", validate_wire_time, mixed_time)

        mixed_point = {"x": 0.0, "y": 0.0, "z": 0.0, 1: 0.0, ("extra",): 0.0}
        self.assert_envelope_error("invalid_point", normalize_point_input, mixed_point)
        self.assert_envelope_error("invalid_point", validate_wire_point, mixed_point)

        payload = make_valid_payload()
        payload[1] = 0
        payload[("extra",)] = 0
        self.assert_envelope_error("invalid_payload", validate_and_normalize_payload, payload)
        self.assert_envelope_error("invalid_payload", validate_wire_payload, payload)

        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        envelope = encoder.encode_envelope(make_valid_payload())
        envelope[1] = 0
        envelope[("extra",)] = 0
        self.assert_envelope_error("invalid_envelope_schema", parse_and_validate_envelope, envelope)

    def test_point_coordinates_exactness(self):
        """Verify exact point format {'x', 'y', 'z'}, finite floats, and no extra fields."""
        # Valid inputs: dict, tuple, list
        p_dict = normalize_point_input({"x": 1.0, "y": 2.0, "z": 3.0})
        self.assertEqual(p_dict, {"x": 1.0, "y": 2.0, "z": 3.0})

        p_tup = normalize_point_input((1.0, 2.0, 3.0))
        self.assertEqual(p_tup, {"x": 1.0, "y": 2.0, "z": 3.0})

        # Missing coordinate
        self.assert_envelope_error("invalid_point", normalize_point_input, {"x": 1.0, "y": 2.0})
        self.assert_envelope_error("invalid_point", normalize_point_input, (1.0, 2.0))

        # Extra coordinate / key
        self.assert_envelope_error("invalid_point", normalize_point_input, {"x": 1.0, "y": 2.0, "z": 3.0, "w": 1.0})
        self.assert_envelope_error("invalid_point", normalize_point_input, (1.0, 2.0, 3.0, 4.0))

        # Non-finite coordinates
        self.assert_envelope_error("invalid_point", normalize_point_input, {"x": float("nan"), "y": 0.0, "z": 0.0})
        self.assert_envelope_error("invalid_point", normalize_point_input, {"x": float("inf"), "y": 0.0, "z": 0.0})

        # Wire point validation
        self.assert_envelope_error("invalid_point", validate_wire_point, [1.0, 2.0, 3.0])  # must be dict on wire
        self.assert_envelope_error("invalid_point", validate_wire_point, {"x": 1.0, "y": 2.0, "z": 3.0, "w": 4.0})

    def test_array_length_limits(self):
        """Verify max knots, max pos_pts, and max yaw_pts limits."""
        # Over MAX_POINTS
        payload = make_valid_payload()
        payload["pos_pts"] = [(0.0, 0.0, 1.0)] * (MAX_POINTS + 1)
        self.assert_envelope_error("array_length_exceeded", validate_and_normalize_payload, payload)

        # Over MAX_KNOTS
        payload = make_valid_payload()
        payload["knots"] = [0.0] * (MAX_KNOTS + 1)
        self.assert_envelope_error("array_length_exceeded", validate_and_normalize_payload, payload)

        # Over MAX_YAW_PTS
        payload = make_valid_payload()
        payload["yaw_pts"] = [0.0] * (MAX_YAW_PTS + 1)
        self.assert_envelope_error("array_length_exceeded", validate_and_normalize_payload, payload)

    def test_frame_framing_truncation_splicing_and_oversize(self):
        """Verify length-prefixed wire framing, truncation, splicing, and oversize rejection."""
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        valid_frame = encoder.encode_frame(make_valid_payload())

        # Header too short (< 4 bytes)
        self.assert_envelope_error("truncated_frame", decoder.decode_frame, b"\x00\x00")

        # Declared length greater than actual frame (truncated frame)
        truncated = valid_frame[:-10]
        self.assert_envelope_error("truncated_frame", decoder.decode_frame, truncated)

        # Spliced frames fed to single-frame decode_frame (trailing bytes)
        spliced = valid_frame + b"extra_bytes"
        self.assert_envelope_error("spliced_frame", decoder.decode_frame, spliced)

        # Oversized frame header (> 1 MiB)
        oversized_header = struct.pack(">I", MAX_PAYLOAD_BYTES + 1) + b"{}"
        self.assert_envelope_error("oversized_frame", decoder.decode_frame, oversized_header)
        self.assert_envelope_error("oversized_frame", unpack_frame_header, oversized_header[:4])

    def test_streaming_decoder_buffer_and_chunking(self):
        """Verify streaming feed(), chunking, and multiple concatenated frames."""
        encoder = BsplineTcpEncoder(VALID_SESSION_ID, initial_sequence=1)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID, initial_sequence=1)

        f1 = encoder.encode_frame(make_valid_payload(traj_id=1))
        f2 = encoder.encode_frame(make_valid_payload(traj_id=2))
        stream_data = f1 + f2

        # Feed in arbitrary 17-byte chunks
        chunk_size = 17
        results = []
        for i in range(0, len(stream_data), chunk_size):
            decoder.feed(stream_data[i : i + chunk_size])
            while True:
                res = decoder.read_frame()
                if res is None:
                    break
                results.append(res)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["traj_id"], 1)
        self.assertEqual(results[1]["traj_id"], 2)
        self.assertEqual(decoder.expected_sequence, 3)

    def test_non_claims_and_no_mutation_boundary(self):
        """Verify that no ids are minted and start_time value is strictly preserved."""
        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        raw_in = make_valid_payload(sec=123, nanosec=456789)
        envelope = encoder.encode_envelope(raw_in)

        # Envelope contains ONLY specified fields, no minted IDs
        disallowed_fields = {"run_id", "mission_id", "epoch", "request_id", "command_id"}
        self.assertTrue(disallowed_fields.isdisjoint(set(envelope.keys())))
        self.assertTrue(disallowed_fields.isdisjoint(set(envelope["payload"].keys())))

        # Conversion to bridge mapping strictly preserves time instant: 123 * 1e9 + 456789
        bridge_dict = _to_bridge_mapping(envelope)
        expected_ns = 123 * 1_000_000_000 + 456789
        self.assertEqual(bridge_dict["start_time"], expected_ns)


class BsplineTcpEnvelopeP2RegressionTests(unittest.TestCase):
    def assert_envelope_error(self, reason: str, callable_obj, *args, **kwargs):
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)

    """Regression coverage for the post-audit hardening round."""

    def test_feed_rejects_non_bytes_with_stable_reason(self):
        import Simulator.wksim_runtime.bspline_tcp_envelope as module
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        for bad in ("text", 123, None, [b"x"], {"a": 1}):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(BsplineEnvelopeError) as ctx:
                    decoder.feed(bad)
                self.assertEqual(ctx.exception.reason, "invalid_frame_header")

    def test_pack_and_unpack_frame_header_reject_non_bytes_with_stable_reason(self):
        """pack_frame and unpack_frame_header must reject non-bytes-like inputs with invalid_frame_header."""
        for bad in ("text", 123, None, [b"x"], {"a": 1}):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(BsplineEnvelopeError) as ctx:
                    unpack_frame_header(bad)
                self.assertEqual(ctx.exception.reason, "invalid_frame_header")

                with self.assertRaises(BsplineEnvelopeError) as ctx:
                    pack_frame(bad)
                self.assertEqual(ctx.exception.reason, "invalid_frame_header")

        # bytearray inputs are supported as bytes-like objects
        header_ba = bytearray(struct.pack(">I", 42))
        self.assertEqual(unpack_frame_header(header_ba), 42)
        packed_ba = pack_frame(bytearray(b"test"))
        self.assertIsInstance(packed_ba, bytes)
        self.assertEqual(packed_ba, struct.pack(">I", 4) + b"test")

        # truncated and oversized classifications remain intact
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            unpack_frame_header(b"\x00\x00")
        self.assertEqual(ctx.exception.reason, "truncated_frame")

        with self.assertRaises(BsplineEnvelopeError) as ctx:
            unpack_frame_header(bytearray(b"\x00"))
        self.assertEqual(ctx.exception.reason, "truncated_frame")

        oversized_hdr = struct.pack(">I", MAX_PAYLOAD_BYTES + 1)
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            unpack_frame_header(oversized_hdr)
        self.assertEqual(ctx.exception.reason, "oversized_frame")

        with self.assertRaises(BsplineEnvelopeError) as ctx:
            pack_frame(b"x" * (MAX_PAYLOAD_BYTES + 1))
        self.assertEqual(ctx.exception.reason, "oversized_frame")

    def test_zero_length_frame_rejected_consistently(self):
        """The wire contract is 0 < L; every framing entry point uses one reason."""
        zero_header = struct.pack(">I", 0)
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            pack_frame(b"")
        self.assertEqual(ctx.exception.reason, "invalid_frame_header")

        with self.assertRaises(BsplineEnvelopeError) as ctx:
            unpack_frame_header(zero_header)
        self.assertEqual(ctx.exception.reason, "invalid_frame_header")

        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            decoder.decode_frame(zero_header)
        self.assertEqual(ctx.exception.reason, "invalid_frame_header")

        # feed() validates a complete leading header transactionally, so the
        # zero-length poison header is rejected before entering the buffer.
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            decoder.feed(zero_header)
        self.assertEqual(ctx.exception.reason, "invalid_frame_header")

        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        valid_frame = encoder.encode_frame(make_valid_payload())
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            decoder.feed(valid_frame + zero_header)
        self.assertEqual(ctx.exception.reason, "invalid_frame_header")

    def test_monkeypatched_globals_do_not_change_existing_instances(self):
        import Simulator.wksim_runtime.bspline_tcp_envelope as module
        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        original = module.ROS1_BSPLINE_MSG_SHA256
        try:
            module.ROS1_BSPLINE_MSG_SHA256 = "f" * 64
            # Existing instances keep their construction-time snapshot.
            frame = encoder.encode_frame(make_valid_payload())
            self.assertIn(b'"ros1_msg_sha256":"' + original.encode(), frame)
            mapping = decoder.decode_frame(frame)  # still validates against the real pin
            self.assertEqual(mapping["order"], 3)
        finally:
            module.ROS1_BSPLINE_MSG_SHA256 = original

    def test_monkeypatched_schema_and_size_globals_do_not_change_existing_instances(self):
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        names_and_values = {
            "SCHEMA_V1": "wksim.bspline-tcp-envelope.v999",
            "MAX_FRAME_BYTES": 5,
            "MAX_PAYLOAD_BYTES": 1,
            "MAX_BUFFER_BYTES": 1,
            "MAX_POINTS": 0,
            "MAX_KNOTS": 0,
            "MAX_YAW_PTS": 0,
        }
        originals = {name: getattr(module, name) for name in names_and_values}
        try:
            for name, value in names_and_values.items():
                setattr(module, name, value)
            frame = encoder.encode_frame(make_valid_payload())
            decoder.feed(frame)
            self.assertEqual(decoder.read_frame()["order"], 3)
        finally:
            for name, value in originals.items():
                setattr(module, name, value)

    def test_new_instances_reject_schema_and_size_pin_drift(self):
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        cases = {
            "SCHEMA_V1": ("wksim.bspline-tcp-envelope.v999", "invalid_envelope_schema"),
            "MAX_FRAME_BYTES": (5, "invalid_frame_header"),
            "MAX_PAYLOAD_BYTES": (1, "invalid_frame_header"),
            "MAX_BUFFER_BYTES": (1, "invalid_frame_header"),
            "MAX_POINTS": (0, "array_length_exceeded"),
            "MAX_KNOTS": (0, "array_length_exceeded"),
            "MAX_YAW_PTS": (0, "array_length_exceeded"),
        }
        for name, (value, reason) in cases.items():
            original = getattr(module, name)
            try:
                setattr(module, name, value)
                with self.assertRaises(BsplineEnvelopeError) as ctx:
                    BsplineTcpEncoder(VALID_SESSION_ID)
                self.assertEqual(ctx.exception.reason, reason)
                with self.assertRaises(BsplineEnvelopeError) as ctx:
                    BsplineTcpDecoder(VALID_SESSION_ID)
                self.assertEqual(ctx.exception.reason, reason)
            finally:
                setattr(module, name, original)

    def test_monkeypatched_globals_break_new_instance_construction(self):
        import Simulator.wksim_runtime.bspline_tcp_envelope as module
        original = module.ROS1_BSPLINE_MSG_SHA256
        try:
            module.ROS1_BSPLINE_MSG_SHA256 = "f" * 64
            with self.assertRaises(BsplineEnvelopeError) as ctx:
                BsplineTcpEncoder(VALID_SESSION_ID)
            self.assertEqual(ctx.exception.reason, "hash_mismatch")
            with self.assertRaises(BsplineEnvelopeError):
                BsplineTcpDecoder(VALID_SESSION_ID)
        finally:
            module.ROS1_BSPLINE_MSG_SHA256 = original
        # After restore, construction works again.
        BsplineTcpEncoder(VALID_SESSION_ID)
        BsplineTcpDecoder(VALID_SESSION_ID)

    def test_decoder_enforces_instance_payload_cap_before_json_validation(self):
        """A valid oversized JSON value is rejected by the public decoder entry point."""
        target_bytes = 1_048_681
        prefix = '{"x":"'
        suffix = '"}'
        raw = (prefix + ("a" * (target_bytes - len(prefix) - len(suffix))) + suffix).encode("utf-8")
        self.assertEqual(len(raw), target_bytes)
        self.assertEqual(json.loads(raw), {"x": "a" * (target_bytes - len(prefix) - len(suffix))})

        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            decoder.decode_envelope_payload(raw)
        self.assertEqual(ctx.exception.reason, "oversized_frame")
        self.assertEqual(decoder.expected_sequence, 1)
        self.assertEqual(decoder.high_water_sequence, 0)

    def test_decoder_counts_utf8_bytes_for_string_payload_cap_and_rolls_back(self):
        """A multi-byte str is measured after UTF-8 encoding, not by code-point count."""
        target_bytes = MAX_PAYLOAD_BYTES + 1
        prefix = '{"x":"'
        suffix = '"}'
        budget = target_bytes - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8"))
        raw_str = prefix + ("é" * (budget // 2)) + ("a" * (budget % 2)) + suffix
        self.assertEqual(len(raw_str.encode("utf-8")), target_bytes)
        self.assertLess(len(raw_str), MAX_PAYLOAD_BYTES)
        self.assertEqual(json.loads(raw_str), {"x": "é" * (budget // 2) + "a" * (budget % 2)})

        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            decoder.decode_envelope_payload(raw_str)
        self.assertEqual(ctx.exception.reason, "oversized_frame")
        self.assertEqual(decoder.expected_sequence, 1)
        self.assertEqual(decoder.high_water_sequence, 0)

    def test_scalar_snapshot_immune_to_joint_global_monkeypatch(self):
        """Existing instances use captured scalar bounds and session rules."""
        import re
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        names_and_values = {
            "INT32_MIN": 0,
            "INT32_MAX": 0,
            "INT64_MIN": 0,
            "INT64_MAX": 0,
            "NANOSEC_LIMIT": 1,
            "_PINNED_INT32_MIN": 0,
            "_PINNED_INT32_MAX": 0,
            "_PINNED_INT64_MIN": 0,
            "_PINNED_INT64_MAX": 0,
            "_PINNED_NANOSEC_LIMIT": 1,
            "_PINNED_SESSION_PATTERN": r"^x$",
            "_HEX_SESSION_RE": re.compile(r"^x$"),
        }
        originals = {name: getattr(module, name) for name in names_and_values}
        try:
            for name, value in names_and_values.items():
                setattr(module, name, value)
            frame = encoder.encode_frame(make_valid_payload(sec=10, nanosec=500))
            mapping = decoder.decode_frame(frame)
            self.assertEqual(mapping["start_time"], 10_000_000_500)
            self.assertEqual(decoder.expected_sequence, 2)
        finally:
            for name, value in originals.items():
                setattr(module, name, value)

    def test_joint_private_and_public_pin_monkeypatch_rejected_for_new_instances(self):
        """Changing both visible and private names cannot replace fixed pins."""
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        names_and_values = {
            "SCHEMA_V1": "wksim.bspline-tcp-envelope.v999",
            "_PINNED_SCHEMA_V1": "wksim.bspline-tcp-envelope.v999",
            "ROS1_BSPLINE_MSG_SHA256": "f" * 64,
            "_PINNED_ROS1_BSPLINE_MSG_SHA256": "f" * 64,
            "MAX_FRAME_BYTES": 5,
            "_PINNED_MAX_FRAME_BYTES": 5,
            "MAX_PAYLOAD_BYTES": 1,
            "_PINNED_MAX_PAYLOAD_BYTES": 1,
        }
        originals = {name: getattr(module, name) for name in names_and_values}
        try:
            for name, value in names_and_values.items():
                setattr(module, name, value)
            with self.assertRaises(BsplineEnvelopeError) as ctx:
                BsplineTcpEncoder(VALID_SESSION_ID)
            self.assertEqual(ctx.exception.reason, "invalid_envelope_schema")
            with self.assertRaises(BsplineEnvelopeError) as ctx:
                BsplineTcpDecoder(VALID_SESSION_ID)
            self.assertEqual(ctx.exception.reason, "invalid_envelope_schema")
        finally:
            for name, value in originals.items():
                setattr(module, name, value)

    def test_field_snapshots_survive_joint_patch_and_reject_shape_errors_stably(self):
        """Existing instances keep field contracts while malformed shapes stay reason-coded."""
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        names_and_values = {
            "BSPLINE_PAYLOAD_FIELDS": (),
            "_PINNED_BSPLINE_PAYLOAD_FIELDS": (),
            "ENVELOPE_FIELDS": (),
            "_PINNED_ENVELOPE_FIELDS": (),
            "ENVELOPE_REASONS": (),
            "_PINNED_ENVELOPE_REASONS": (),
        }
        originals = {name: getattr(module, name) for name in names_and_values}
        try:
            for name, value in names_and_values.items():
                setattr(module, name, value)

            frame = encoder.encode_frame(make_valid_payload())
            self.assertEqual(decoder.decode_frame(frame)["order"], 3)
            self.assert_envelope_error("invalid_payload", validate_and_normalize_payload, {})
            self.assert_envelope_error("invalid_payload", validate_wire_payload, {})
            self.assert_envelope_error(
                "invalid_envelope_schema",
                parse_and_validate_envelope,
                {},
            )
            self.assertEqual(BsplineEnvelopeError("invalid_payload").reason, "invalid_payload")
        finally:
            for name, value in originals.items():
                setattr(module, name, value)

    def test_new_instances_reject_joint_field_pin_replacement(self):
        """Changing public and private field pins together cannot alter construction."""
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        cases = (
            (("BSPLINE_PAYLOAD_FIELDS", "_PINNED_BSPLINE_PAYLOAD_FIELDS"), "invalid_payload"),
            (("ENVELOPE_FIELDS", "_PINNED_ENVELOPE_FIELDS"), "invalid_envelope_schema"),
        )
        for names, reason in cases:
            originals = {name: getattr(module, name) for name in names}
            try:
                for name in names:
                    setattr(module, name, ())
                self.assert_envelope_error(reason, BsplineTcpEncoder, VALID_SESSION_ID)
                self.assert_envelope_error(reason, BsplineTcpDecoder, VALID_SESSION_ID)
            finally:
                for name, value in originals.items():
                    setattr(module, name, value)

    def test_missing_and_extra_fields_never_leak_key_error(self):
        """Every payload and envelope shape violation fails before field indexing."""
        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        envelope = encoder.encode_envelope(make_valid_payload())

        missing_payload = dict(envelope["payload"])
        missing_payload.pop("yaw_dt")
        missing_envelope = dict(envelope)
        missing_envelope.pop("payload")
        extra_payload = dict(envelope["payload"], unexpected=0)
        extra_envelope = dict(envelope, unexpected=0)

        self.assert_envelope_error("invalid_payload", validate_wire_payload, missing_payload)
        self.assert_envelope_error("invalid_payload", validate_wire_payload, extra_payload)
        self.assert_envelope_error("invalid_envelope_schema", parse_and_validate_envelope, missing_envelope)
        self.assert_envelope_error("invalid_envelope_schema", parse_and_validate_envelope, extra_envelope)

    def test_reason_tuple_empty_does_not_change_new_instance_error_codes(self):
        """The exception class keeps the import-time reason set after both names are patched."""
        import Simulator.wksim_runtime.bspline_tcp_envelope as module

        names = ("ENVELOPE_REASONS", "_PINNED_ENVELOPE_REASONS")
        originals = {name: getattr(module, name) for name in names}
        try:
            for name in names:
                setattr(module, name, ())
            encoder = BsplineTcpEncoder(VALID_SESSION_ID)
            decoder = BsplineTcpDecoder(VALID_SESSION_ID)
            frame = encoder.encode_frame(make_valid_payload())
            self.assertEqual(decoder.decode_frame(frame)["order"], 3)
            self.assertEqual(BsplineEnvelopeError("invalid_payload").reason, "invalid_payload")
        finally:
            for name, value in originals.items():
                setattr(module, name, value)

    def test_poison_frame_requires_new_session_recovery(self):
        encoder = BsplineTcpEncoder(VALID_SESSION_ID)
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        good = encoder.encode_frame(make_valid_payload(traj_id=1))
        poison = struct.pack(">I", 10) + b"not-json!!"
        decoder.feed(good + poison)
        self.assertEqual(decoder.read_frame()["traj_id"], 1)
        with self.assertRaises(BsplineEnvelopeError):
            decoder.read_frame()
        # Permanent head-of-line block: more valid bytes cannot unblock it.
        decoder.feed(encoder.encode_frame(make_valid_payload(traj_id=2)))
        with self.assertRaises(BsplineEnvelopeError):
            decoder.read_frame()
        self.assertEqual(decoder.expected_sequence, 2)
        self.assertEqual(decoder.high_water_sequence, 1)
        # Recovery contract: new decoder + NEW transport_session_id rejects the
        # old session's frames and only accepts its own fresh stream.
        new_encoder = BsplineTcpEncoder(OTHER_SESSION_ID)
        new_decoder = BsplineTcpDecoder(OTHER_SESSION_ID)
        new_decoder.feed(good)  # old-session frame
        with self.assertRaises(BsplineEnvelopeError) as ctx:
            new_decoder.read_frame()
        self.assertEqual(ctx.exception.reason, "session_mismatch")
        fresh = new_encoder.encode_frame(make_valid_payload(traj_id=1))
        new_decoder2 = BsplineTcpDecoder(OTHER_SESSION_ID)
        new_decoder2.feed(fresh)
        self.assertEqual(new_decoder2.read_frame()["traj_id"], 1)

    def test_unvalidated_direct_mapping_bypass_is_not_public(self):
        import Simulator.wksim_runtime.bspline_tcp_envelope as module
        self.assertFalse(hasattr(module, "to_bridge_mapping"))
        # The private helper cannot be reached through the decoder without
        # validation: a payload violating the envelope contract never maps.
        decoder = BsplineTcpDecoder(VALID_SESSION_ID)
        bad = encoder_envelope_with(  # locally built invalid envelope bytes
            b'{"drone_id":0,"order":3,"traj_id":1,"start_time":{"sec":-1,"nanosec":0},'
            b'"knots":[0.0],"pos_pts":[],"yaw_pts":[],"yaw_dt":0.0}')
        with self.assertRaises(BsplineEnvelopeError):
            decoder.decode_envelope_payload(bad)
        self.assertEqual(decoder.high_water_sequence, 0)


def encoder_envelope_with(payload_json: bytes) -> bytes:
    """Wrap raw payload bytes in an otherwise-valid envelope (test helper)."""
    envelope = (b'{"schema":"wksim.bspline-tcp-envelope.v1","transport_session_id":"'
                + VALID_SESSION_ID.encode()
                + b'","sequence":1,"source_package":"prometheus_msgs",'
                b'"source_msg_type":"prometheus_msgs/Bspline",'
                b'"ros1_msg_sha256":"' + ROS1_BSPLINE_MSG_SHA256.encode() + b'",'
                b'"ros2_msg_sha256":"' + ROS2_BSPLINE_MSG_SHA256.encode() + b'",'
                b'"payload":' + payload_json + b'}')
    return envelope


if __name__ == "__main__":
    unittest.main()
