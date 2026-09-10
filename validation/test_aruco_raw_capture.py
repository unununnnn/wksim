"""Strict unit and negative test suite for ArucoRawCapture (#104).

Verifies:
- Default channels locked strictly to wksim_msgs.msg.SetupRequest and CommandRequest.
- Stack/uav_id coupling (arducopter=1, px4=2).
- Epoch hex32 requirement.
- Drain limit 1..200 integer requirement (rejecting bool).
- Symlink rejection on output_path.
- Authentic CDR validation: even-length hex >= 8 chars, valid OMG CDR header.
- GID validation: non-empty, non-all-zero, variable length.
- Timestamps validation: must be present int, reject bool/defaulting.
- Canonical JSON hash chain over start, samples, and end records.
- Safe serialization of non-finite floats (:nan:, :inf:) in decoded message.
- Write failure explicit error raising and status='write_failed'.
- Constructor failure cleanup.
- Unquiesced queue overflow exception.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import sys
import types
from types import SimpleNamespace
from typing import Any, Optional
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime.aruco_raw_capture import (
    ArucoRawCapture,
    ChannelSpec,
    INITIAL_HASH_SEED,
    SCHEMA_VERSION,
    VALID_CDR_HEADERS,
    build_default_aruco_channels,
)

VALID_EPOCH = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
VALID_CDR_LE = b"\x00\x01\x00\x00\x10\x20\x30\x40"  # 8 bytes: valid CDR_LE header + 4 payload bytes
VALID_GID_16 = b"\x01" * 16
VALID_GID_24 = b"\x00" * 23 + b"\x05"  # 24-byte non-all-zero GID


class MockSubscription:
    def __init__(self, topic_name: str, msg_type: Any):
        self.topic_name = topic_name
        self.msg_type = msg_type


class MockRawNode:
    def __init__(self, name: str = "wksim_aruco_raw_arducopter"):
        self.name = name
        self.subscriptions = []
        self.destroyed_subscriptions = []
        self.is_destroyed = False

    def create_subscription(self, msg_type, topic, callback, qos):
        sub = MockSubscription(topic, msg_type)
        self.subscriptions.append(sub)
        return sub

    def destroy_subscription(self, sub):
        self.destroyed_subscriptions.append(sub)

    def destroy_node(self):
        self.is_destroyed = True


class MockRCTake:
    def __init__(self, queue_map: Optional[dict] = None):
        self.queues = {k: list(v) for k, v in (queue_map or {}).items()}

    def take(self, subscription):
        topic = subscription.topic_name
        q = self.queues.get(topic, [])
        if q:
            return q.pop(0)
        return None


def create_sample_info(
    cdr_bytes: bytes = VALID_CDR_LE,
    gid_bytes: bytes = VALID_GID_16,
    src_ts: int = 100000000,
    rcv_ts: int = 100005000,
):
    return SimpleNamespace(
        cdr_hex=cdr_bytes.hex(),
        publisher_gid=gid_bytes,
        source_timestamp=src_ts,
        received_timestamp=rcv_ts,
    )


class TestArucoRawCapture(unittest.TestCase):
    def setUp(self):
        try:
            from wksim_msgs.msg import SetupRequest, CommandRequest
            from rclpy.qos import QoSProfile
        except ImportError:
            # Explicit test-only stand-ins; production must import real ROS types.
            msg=types.ModuleType('wksim_msgs.msg');qos=types.ModuleType('rclpy.qos')
            msg.SetupRequest=type('SetupRequest',(),{'__module__':'wksim_msgs.msg'})
            msg.CommandRequest=type('CommandRequest',(),{'__module__':'wksim_msgs.msg'})
            qos.QoSProfile=lambda **kwargs:SimpleNamespace(**kwargs)
            qos.ReliabilityPolicy=SimpleNamespace(RELIABLE=1)
            self.enterContext(patch.dict(sys.modules,{'wksim_msgs.msg':msg,'rclpy.qos':qos}))
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output_path = self.root / "rc-dds.jsonl"
        self.node = MockRawNode()
        self.channels = build_default_aruco_channels(1, "arducopter")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_channels_locked_to_wksim_msgs(self):
        """Test default channels strictly contain v2/setup and v2/command of wksim_msgs types."""
        ard_channels = build_default_aruco_channels(1, "arducopter")
        self.assertEqual(len(ard_channels), 2)
        setup_ch = ard_channels[0]
        cmd_ch = ard_channels[1]

        self.assertEqual(setup_ch.topic, "/uav1/prometheus/v2/setup")
        self.assertEqual(setup_ch.type_name, "wksim_msgs/msg/SetupRequest")
        self.assertEqual(setup_ch.msg_type.__name__, "SetupRequest")

        self.assertEqual(cmd_ch.topic, "/uav1/prometheus/v2/command")
        self.assertEqual(cmd_ch.type_name, "wksim_msgs/msg/CommandRequest")
        self.assertEqual(cmd_ch.msg_type.__name__, "CommandRequest")

        px4_channels = build_default_aruco_channels(2, "px4")
        self.assertEqual(len(px4_channels), 2)
        self.assertEqual(px4_channels[0].topic, "/uav2/prometheus/v2/setup")
        self.assertEqual(px4_channels[1].topic, "/uav2/prometheus/v2/command")

    def test_stack_uav_id_coupling_enforced(self):
        """Test arducopter requires uav_id=1 and px4 requires uav_id=2; mismatches rejected."""
        rc_take = MockRCTake()
        # arducopter with uav_id=2 must fail
        with self.assertRaises(ValueError) as ctx:
            ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=2,
                            raw_node=self.node, rc_take=rc_take)
        self.assertIn("stack 'arducopter' requires uav_id=1", str(ctx.exception))

        # px4 with uav_id=1 must fail
        with self.assertRaises(ValueError) as ctx:
            ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="px4", uav_id=1,
                            raw_node=self.node, rc_take=rc_take)
        self.assertIn("stack 'px4' requires uav_id=2", str(ctx.exception))

        # bool uav_id must fail
        with self.assertRaises(ValueError):
            ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=True,
                            raw_node=self.node, rc_take=rc_take)

    def test_epoch_hex32_enforced(self):
        """Test epoch must be exactly 32 hex characters."""
        rc_take = MockRCTake()
        for bad_epoch in ("123", "not_a_hex_epoch_at_all_12345678", VALID_EPOCH + "f", 12345, None):
            with self.assertRaises(ValueError):
                ArucoRawCapture(self.output_path, run_id="run-1", epoch=bad_epoch, stack="arducopter", uav_id=1,
                                raw_node=self.node, rc_take=rc_take)

    def test_drain_limit_bounds_and_bool_rejection(self):
        """Test max_drain_limit must be 1..200 int, rejecting bool and out-of-range."""
        rc_take = MockRCTake()
        for bad_limit in (True, False, 0, 201, -1, "50"):
            with self.assertRaises(ValueError):
                ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                raw_node=self.node, rc_take=rc_take, max_drain_limit=bad_limit)

    def test_symlink_output_path_rejected(self):
        """Test output_path as a symlink or passing through a symlink is rejected."""
        rc_take = MockRCTake()
        real_file = self.root / "real_file.jsonl"
        link_file = self.root / "link_file.jsonl"
        try:
            os.symlink(str(real_file), str(link_file))
            with self.assertRaises(ValueError) as ctx:
                ArucoRawCapture(link_file, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                raw_node=self.node, rc_take=rc_take)
            self.assertIn("cannot be a symlink", str(ctx.exception))
        except (OSError, NotImplementedError):
            pass  # Some Windows environments require Administrator for symlink creation

    def test_odd_and_short_raw_cdr_hex_rejected(self):
        """Test odd-length or <8 chars CDR hex is strictly rejected."""
        rc_take = MockRCTake()
        capture = ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take)

        # Odd length hex
        odd_info = SimpleNamespace(cdr_hex="0001000", publisher_gid=VALID_GID_16, source_timestamp=1, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, odd_info)]
        with self.assertRaises(ValueError) as ctx:
            capture.drain()
        self.assertIn("Invalid raw CDR hex", str(ctx.exception))

        # Short hex (<8 chars / 4 bytes)
        short_info = SimpleNamespace(cdr_hex="000100", publisher_gid=VALID_GID_16, source_timestamp=1, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, short_info)]
        with self.assertRaises(ValueError) as ctx:
            capture.drain()
        self.assertIn("Invalid raw CDR hex", str(ctx.exception))
        capture.close()

    def test_invalid_cdr_encapsulation_header_rejected(self):
        """Test CDR lacking standard encapsulation header (0000, 0001, 0002, 0003) is rejected."""
        rc_take = MockRCTake()
        capture = ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take)

        bad_hdr_cdr = b"\xff\xff\x00\x00\x10\x20\x30\x40"
        bad_hdr_info = SimpleNamespace(cdr_hex=bad_hdr_cdr.hex(), publisher_gid=VALID_GID_16, source_timestamp=1, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, bad_hdr_info)]
        with self.assertRaises(ValueError) as ctx:
            capture.drain()
        self.assertIn("Invalid CDR encapsulation header: ffff", str(ctx.exception))
        capture.close()

    def test_empty_and_all_zero_gid_rejected(self):
        """Test empty or all-zero GID is rejected; variable length non-zero GID accepted."""
        rc_take = MockRCTake()
        capture = ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take)

        # Empty GID
        empty_gid_info = SimpleNamespace(cdr_hex=VALID_CDR_LE.hex(), publisher_gid=b"", source_timestamp=1, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, empty_gid_info)]
        with self.assertRaises(ValueError) as ctx:
            capture.drain()
        self.assertIn("publisher_gid must be non-empty and non-zero bytes", str(ctx.exception))

        # All-zero GID (16 bytes zeros)
        zero_gid_info = SimpleNamespace(cdr_hex=VALID_CDR_LE.hex(), publisher_gid=b"\x00" * 16, source_timestamp=1, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, zero_gid_info)]
        with self.assertRaises(ValueError) as ctx:
            capture.drain()
        self.assertIn("publisher_gid must be non-empty and non-zero bytes", str(ctx.exception))

        # Valid 24-byte variable GID accepted
        var_gid_info = SimpleNamespace(cdr_hex=VALID_CDR_LE.hex(), publisher_gid=VALID_GID_24, source_timestamp=1, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, var_gid_info)]
        count = capture.drain()
        self.assertEqual(count, 1)
        self.assertEqual(capture.take_sequence, 1)
        capture.close()

    def test_missing_and_bool_timestamps_rejected(self):
        """Test timestamps must be present integers and cannot be bool or missing."""
        rc_take = MockRCTake()
        capture = ArucoRawCapture(self.output_path, run_id="run-1", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take)

        # Missing source_timestamp
        no_src = SimpleNamespace(cdr_hex=VALID_CDR_LE.hex(), publisher_gid=VALID_GID_16, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, no_src)]
        with self.assertRaises(ValueError) as ctx:
            capture.drain()
        self.assertIn("source_timestamp and received_timestamp must be present", str(ctx.exception))

        # Bool source_timestamp
        bool_src = SimpleNamespace(cdr_hex=VALID_CDR_LE.hex(), publisher_gid=VALID_GID_16, source_timestamp=True, received_timestamp=2)
        rc_take.queues[self.channels[0].topic] = [({"id": 1}, bool_src)]
        with self.assertRaises(ValueError) as ctx:
            capture.drain()
        self.assertIn("must be integer nanoseconds, not bool", str(ctx.exception))
        capture.close()

    def test_canonical_json_hash_chain_across_start_samples_end(self):
        """Test start, samples, and end records form an unbroken, verifiable canonical JSON hash chain."""
        queue_map = {
            self.channels[0].topic: [
                ({"req": "setup_1"}, create_sample_info(VALID_CDR_LE, VALID_GID_16, src_ts=10, rcv_ts=15)),
            ],
            self.channels[1].topic: [
                ({"cmd": "takeoff"}, create_sample_info(VALID_CDR_LE, VALID_GID_24, src_ts=20, rcv_ts=25)),
            ],
        }
        rc_take = MockRCTake(queue_map)
        capture = ArucoRawCapture(self.output_path, run_id="run-chain", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take)

        drained = capture.drain()
        self.assertEqual(drained, 2)
        summary = capture.close()

        self.assertEqual(summary["total_samples"], 2)
        self.assertEqual(summary["status"], "complete")

        # Read back raw lines and independently re-verify canonical hash chain
        lines = [json.loads(l) for l in self.output_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 4)  # start, sample 1, sample 2, end

        expected_prev = INITIAL_HASH_SEED
        for idx, rec in enumerate(lines):
            self.assertEqual(rec["prev_record_sha256"], expected_prev, f"Hash chain broken at record {idx}")

            # Recompute canonical hash
            rec_copy = dict(rec)
            actual_sha = rec_copy.pop("record_sha256")
            canonical_bytes = json.dumps(rec_copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
            recomputed_sha = hashlib.sha256(canonical_bytes).hexdigest()
            self.assertEqual(actual_sha, recomputed_sha, f"Canonical digest mismatch at record {idx}")
            expected_prev = actual_sha

        self.assertEqual(summary["final_hash_chain"], lines[-1]["record_sha256"])

    def test_non_finite_floats_sanitized_without_bare_nan(self):
        """Test non-finite floats in decoded messages are encoded as :nan:/:inf: without bare NaN."""
        queue_map = {
            self.channels[0].topic: [
                (
                    {"vel": [1.0, float("nan"), float("inf"), float("-inf")]},
                    create_sample_info(VALID_CDR_LE, VALID_GID_16, src_ts=100, rcv_ts=105),
                )
            ]
        }
        rc_take = MockRCTake(queue_map)
        capture = ArucoRawCapture(self.output_path, run_id="run-nan", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take)
        capture.drain()
        capture.close()

        raw_text = self.output_path.read_text(encoding="utf-8")
        self.assertNotIn("NaN", raw_text)
        self.assertNotIn("Infinity", raw_text)

        lines = [json.loads(l) for l in raw_text.splitlines() if l.strip()]
        sample = lines[1]
        self.assertEqual(sample["message"]["vel"], [1.0, ":nan:", ":inf:", ":-inf:"])

    def test_write_failure_raises_explicit_error_and_marks_failed(self):
        """Test write failure raises IOError immediately to fail the task and marks status='write_failed'."""
        queue_map = {
            self.channels[0].topic: [
                ({"id": 1}, create_sample_info(VALID_CDR_LE)),
            ]
        }
        rc_take = MockRCTake(queue_map)
        capture = ArucoRawCapture(self.output_path, run_id="run-io", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take)

        with patch.object(capture.log_file, "write", side_effect=IOError("Simulated disk error")):
            with self.assertRaises(IOError) as ctx:
                capture.drain()
            self.assertIn("Simulated disk error", str(ctx.exception))

        self.assertEqual(capture.status, "write_failed")
        summary = capture.close()
        self.assertEqual(summary["status"], "write_failed")
        self.assertGreater(summary["write_failures"], 0)

    def test_constructor_failure_cleans_up_resources(self):
        """Construction failure destroys resources and preserves partial evidence."""
        rc_take = MockRCTake()
        # Patch write_canonical_record to fail during start record write
        with patch.object(ArucoRawCapture, "_write_canonical_record", side_effect=RuntimeError("Init write crash")):
            with self.assertRaises(RuntimeError):
                ArucoRawCapture(self.output_path, run_id="run-fail", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                channels=self.channels, raw_node=self.node, rc_take=rc_take)

        self.assertTrue(self.output_path.exists())
        # Subscriptions on mock node must be destroyed
        self.assertGreater(len(self.node.destroyed_subscriptions), 0)

    def test_exclusive_open_failure_preserves_existing_evidence(self):
        self.output_path.write_bytes(b'prior evidence\n')
        with self.assertRaises(FileExistsError):
            ArucoRawCapture(self.output_path,run_id='same-path',epoch=VALID_EPOCH,stack='arducopter',uav_id=1,
                            channels=self.channels,raw_node=self.node,rc_take=MockRCTake())
        self.assertEqual(self.output_path.read_bytes(),b'prior evidence\n')

    def test_terminal_write_failure_cannot_report_complete(self):
        capture=ArucoRawCapture(self.output_path,run_id='end-failure',epoch=VALID_EPOCH,stack='arducopter',uav_id=1,
                               channels=self.channels,raw_node=self.node,rc_take=MockRCTake())
        self.assertEqual(capture.get_summary()['status'],'recording')
        with patch.object(capture.log_file,'write',side_effect=OSError('disk full')):
            result=capture.close()
        self.assertEqual(result['status'],'write_failed')

    def test_unquiesced_queue_overflow_raises_bounded_error(self):
        """Test queue failing to quiesce within bound raises RuntimeError."""
        queue_map = {
            self.channels[0].topic: [
                ({"id": i}, create_sample_info(VALID_CDR_LE)) for i in range(5)
            ]
        }
        rc_take = MockRCTake(queue_map)
        capture = ArucoRawCapture(self.output_path, run_id="run-burst", epoch=VALID_EPOCH, stack="arducopter", uav_id=1,
                                  channels=self.channels, raw_node=self.node, rc_take=rc_take, max_drain_limit=3)

        with self.assertRaises(RuntimeError) as ctx:
            capture.drain(max_per_sub=3)
        self.assertIn("did not quiesce within bound (3)", str(ctx.exception))
        capture.close()


if __name__ == "__main__":
    unittest.main()
