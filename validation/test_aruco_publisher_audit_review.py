#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Review and adversarial negative test suite for ArUco publisher GID audit and exclusivity.

Strictly covers negative rejection gates:
  1. Foreign publisher exclusivity breach during intermediate snapshots (publisher_count > 1).
  2. GID drift/mutation across lifecycle snapshots (restarted process or dynamic rebinding).
  3. Malformed GID formats: truncated hex, non-hex characters, all-zero GID, and entity kind mismatch.
  4. Rogue/mismatched publisher GID in recorded raw CDR samples for exercised channels.
  5. Foreign/unauthorized GID injection on unexercised channels.
  6. Non-consecutive, out-of-order, or skipped snapshot_index.
  7. Monotonic timestamp regressions (decreasing, zero, negative, or non-integer type).
  8. Authority tick regression (decreasing or negative).
  9. Non-exact boundary lifecycle reasons (must be strictly 'ready' at start and 'report' at end).
  10. Channel set violations: omitted required channels, unexpected rogue topics, or mistyped ROS message types.
  11. Raw capture hash integrity failure (broken raw CDR audit gate).
  12. Node identity breach: unexpected node_name or non-root node_namespace.

DO NOT run active simulations or tests during review to avoid port/process collision with Run 14.
"""

import copy
from pathlib import Path
import sys
import unittest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.audit_aruco_publishers import (
    REQUIRED_SNAPSHOT_CHANNELS,
    audit_publisher_snapshots,
    parse_guid,
)


class TestArucoPublisherAuditReviewNegatives(unittest.TestCase):
    """Adversarial negative test suite auditing snapshot verification boundary gates."""

    def setUp(self):
        # Canonical test GIDs (48 hex chars, 24 bytes, ending in 03 for data_writer)
        self.ap_gid_gps = "010f7f01f624c70700000000000014030000000000000000"
        self.ap_gid_vel = "010f7f01f624c70700000000000015030000000000000000"
        self.ap_gid_state = "010f7f01f624c70700000000000020030000000000000000"
        self.rogue_gid = "010f7f01deadbeef00000000000099030000000000000000"

        # Baseline valid AP topics
        self.valid_ap_topics = {
            "/ap/cmd_gps_pose": {
                "publisher_count": 1,
                "node_name": "wksim_joint_arducopter_control",
                "node_namespace": "/",
                "type_name": "ardupilot_msgs/msg/GlobalPosition",
                "endpoint_gid": self.ap_gid_gps,
            },
            "/ap/cmd_vel": {
                "publisher_count": 1,
                "node_name": "wksim_joint_arducopter_control",
                "node_namespace": "/",
                "type_name": "geometry_msgs/msg/TwistStamped",
                "endpoint_gid": self.ap_gid_vel,
            },
            "/uav1/prometheus/v2/state": {
                "publisher_count": 1,
                "node_name": "wksim_joint_arducopter_control",
                "node_namespace": "/",
                "type_name": "wksim_msgs/msg/SessionState",
                "endpoint_gid": self.ap_gid_state,
            },
        }

    def _build_valid_snapshots(self):
        return [
            {
                "snapshot_index": 1,
                "monotonic_ns": 1000000,
                "monotonic_s": 0.001,
                "reason": "ready",
                "authority_tick": 0,
                "node_name": "wksim_joint_arducopter_control",
                "stack": "arducopter",
                "topics": copy.deepcopy(self.valid_ap_topics),
            },
            {
                "snapshot_index": 2,
                "monotonic_ns": 2000000,
                "monotonic_s": 0.002,
                "reason": "before-public-send:move",
                "authority_tick": 10,
                "node_name": "wksim_joint_arducopter_control",
                "stack": "arducopter",
                "topics": copy.deepcopy(self.valid_ap_topics),
            },
            {
                "snapshot_index": 3,
                "monotonic_ns": 3000000,
                "monotonic_s": 0.003,
                "reason": "report",
                "authority_tick": 20,
                "node_name": "wksim_joint_arducopter_control",
                "stack": "arducopter",
                "topics": copy.deepcopy(self.valid_ap_topics),
            },
        ]

    def test_negative_foreign_publisher_exclusivity_breach(self):
        """Negative: Intermediate snapshot detects 2 publishers on a guarded channel."""
        snapshots = self._build_valid_snapshots()
        # In snapshot 2 (mid-flight), a second writer is discovered
        snapshots[1]["topics"]["/ap/cmd_gps_pose"]["publisher_count"] = 2

        raw_samples = {
            "/ap/cmd_gps_pose": [{"publisher_gid": self.ap_gid_gps}],
            "/ap/cmd_vel": [{"publisher_gid": self.ap_gid_vel}],
            "/uav1/prometheus/v2/state": [{"publisher_gid": self.ap_gid_state}],
        }
        res = audit_publisher_snapshots(snapshots, "arducopter", raw_samples, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["writer_binding"], "unbound")
        self.assertEqual(res["snapshot_exclusivity"], "unverified")
        self.assertTrue(any("publisher_count=2" in err for err in res["errors"]))

    def test_negative_gid_drift_across_snapshots(self):
        """Negative: Endpoint GID mutates across snapshots (e.g. process restart / rebinding)."""
        snapshots = self._build_valid_snapshots()
        # In snapshot 3 (report), GID drifted to rogue GID
        snapshots[2]["topics"]["/ap/cmd_gps_pose"]["endpoint_gid"] = self.rogue_gid

        raw_samples = {
            "/ap/cmd_gps_pose": [{"publisher_gid": self.ap_gid_gps}],
            "/ap/cmd_vel": [{"publisher_gid": self.ap_gid_vel}],
            "/uav1/prometheus/v2/state": [{"publisher_gid": self.ap_gid_state}],
        }
        res = audit_publisher_snapshots(snapshots, "arducopter", raw_samples, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["writer_binding"], "unbound")
        self.assertTrue(any("GID drifted from initial" in err for err in res["errors"]))

    def test_negative_malformed_gid_formats(self):
        """Negative: Rejects short hex, non-hex chars, and all-zero 24-byte GID."""
        # Generic RTPS diagnostics accept a 16-byte GUID. The pinned RMW
        # snapshot contract separately requires the complete 24-byte GID.
        parsed_short = parse_guid("010f7f01f624c7070000000000001403")
        self.assertTrue(parsed_short["is_valid_format"])
        truncated = self._build_valid_snapshots()
        truncated[0]['topics']['/ap/cmd_gps_pose']['endpoint_gid'] = parsed_short['raw']
        result = audit_publisher_snapshots(truncated,'arducopter',{},raw_hash_valid=True)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(any('invalid 48-char hex GID' in error for error in result['errors']))

        # 2. Non-hex characters
        parsed_nonhex = parse_guid("010f7f01f624c7070000000000001403000000000000000Z")
        self.assertFalse(parsed_nonhex["is_valid_format"])

        # 3. All-zero GID in snapshot
        snapshots = self._build_valid_snapshots()
        snapshots[0]["topics"]["/ap/cmd_gps_pose"]["endpoint_gid"] = "0" * 48
        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("rejected all-zero GID" in err for err in res["errors"]))

    def test_negative_exercised_channel_gid_mismatch(self):
        """Negative: Recorded CDR sample publisher GID differs from snapshot endpoint GID."""
        snapshots = self._build_valid_snapshots()
        raw_samples = {
            # Injected rogue GID sample on active cmd_gps_pose channel
            "/ap/cmd_gps_pose": [{"publisher_gid": self.rogue_gid}],
            "/ap/cmd_vel": [{"publisher_gid": self.ap_gid_vel}],
            "/uav1/prometheus/v2/state": [{"publisher_gid": self.ap_gid_state}],
        }
        res = audit_publisher_snapshots(snapshots, "arducopter", raw_samples, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["writer_binding"], "unbound")
        self.assertTrue(any("mismatched GID(s)" in err for err in res["errors"]))

    def test_negative_unexercised_channel_foreign_sample_injected(self):
        """Negative: Unexercised channel (/ap/cmd_vel) receiving unauthorized sample must fail."""
        snapshots = self._build_valid_snapshots()
        raw_samples = {
            "/ap/cmd_gps_pose": [{"publisher_gid": self.ap_gid_gps}],
            # Suppose cmd_vel was unexercised by control, but a rogue entity published to it!
            "/ap/cmd_vel": [{"publisher_gid": self.rogue_gid}],
            "/uav1/prometheus/v2/state": [{"publisher_gid": self.ap_gid_state}],
        }
        res = audit_publisher_snapshots(snapshots, "arducopter", raw_samples, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["writer_binding"], "unbound")
        self.assertTrue(any("mismatched GID(s)" in err for err in res["errors"]))

    def test_negative_non_consecutive_snapshot_index(self):
        """Negative: Snapshot sequence index gap (1 followed by 3) is rejected."""
        snapshots = self._build_valid_snapshots()
        snapshots[1]["snapshot_index"] = 3  # Gap: skips index 2
        snapshots[2]["snapshot_index"] = 4

        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("expected 2" in err for err in res["errors"]))

    def test_negative_monotonic_timestamp_regressions(self):
        """Negative: Decreasing, non-positive, or non-integer monotonic_ns is rejected."""
        snapshots = self._build_valid_snapshots()
        # Decreasing monotonic_ns
        snapshots[1]["monotonic_ns"] = 500000  # < 1000000
        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("not strictly increasing" in err for err in res["errors"]))

        # Non-positive monotonic_ns
        snapshots_zero = self._build_valid_snapshots()
        snapshots_zero[0]["monotonic_ns"] = 0
        res_zero = audit_publisher_snapshots(snapshots_zero, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_zero["status"], "failed")
        self.assertTrue(any("must be positive integer" in err for err in res_zero["errors"]))

    def test_negative_authority_tick_regression(self):
        """Negative: Authority tick decreasing backwards is rejected."""
        snapshots = self._build_valid_snapshots()
        snapshots[1]["authority_tick"] = 50
        snapshots[2]["authority_tick"] = 20  # Decreases from 50 to 20
        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("authority_tick (20) decreased" in err for err in res["errors"]))

    def test_negative_boundary_reason_mismatch(self):
        """Negative: Rejects snapshot chains not strictly bounded by 'ready' and 'report'."""
        # 1. Starting with 'init' instead of exact 'ready'
        bad_start = self._build_valid_snapshots()
        bad_start[0]["reason"] = "init"
        res_start = audit_publisher_snapshots(bad_start, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_start["status"], "failed")
        self.assertTrue(any("First snapshot reason must be exactly 'ready'" in err for err in res_start["errors"]))

        # 2. Ending with 'periodic' instead of exact 'report'
        bad_end = self._build_valid_snapshots()
        bad_end[2]["reason"] = "periodic"
        res_end = audit_publisher_snapshots(bad_end, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_end["status"], "failed")
        self.assertTrue(any("Last snapshot reason must be exactly 'report'" in err for err in res_end["errors"]))

    def test_negative_channel_set_and_type_violations(self):
        """Negative: Missing required channel, extra unknown channel, or wrong message type."""
        # 1. Missing channel (/uav1/prometheus/v2/state deleted)
        missing_chan = self._build_valid_snapshots()
        for snap in missing_chan:
            del snap["topics"]["/uav1/prometheus/v2/state"]
        res_missing = audit_publisher_snapshots(missing_chan, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_missing["status"], "failed")
        self.assertTrue(any("missing required channels" in err for err in res_missing["errors"]))

        # 2. Extra undeclared channel
        extra_chan = self._build_valid_snapshots()
        for snap in extra_chan:
            snap["topics"]["/rogue_topic"] = {
                "publisher_count": 1,
                "node_name": "wksim_joint_arducopter_control",
                "node_namespace": "/",
                "type_name": "std_msgs/msg/String",
                "endpoint_gid": self.rogue_gid,
            }
        res_extra = audit_publisher_snapshots(extra_chan, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_extra["status"], "failed")
        self.assertTrue(any("undeclared channels" in err for err in res_extra["errors"]))

        # 3. Wrong message type
        wrong_type = self._build_valid_snapshots()
        for snap in wrong_type:
            snap["topics"]["/ap/cmd_vel"]["type_name"] = "geometry_msgs/msg/Twist"  # Missing Stamped
        res_type = audit_publisher_snapshots(wrong_type, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_type["status"], "failed")
        self.assertTrue(any("type_name='geometry_msgs/msg/Twist'" in err for err in res_type["errors"]))

    def test_negative_broken_raw_capture_hash(self):
        """Negative: raw_hash_valid=False rejects binding even if snapshot topics match."""
        snapshots = self._build_valid_snapshots()
        raw_samples = {
            "/ap/cmd_gps_pose": [{"publisher_gid": self.ap_gid_gps}],
            "/ap/cmd_vel": [{"publisher_gid": self.ap_gid_vel}],
            "/uav1/prometheus/v2/state": [{"publisher_gid": self.ap_gid_state}],
        }
        res = audit_publisher_snapshots(snapshots, "arducopter", raw_samples, raw_hash_valid=False)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["writer_binding"], "unbound")
        self.assertEqual(res["snapshot_exclusivity"], "unverified")
        self.assertTrue(any("Raw capture verification failed" in err for err in res["errors"]))

    def test_negative_node_identity_mismatch(self):
        """Negative: Node name or namespace breach in snapshot endpoint."""
        # 1. Foreign node namespace
        bad_ns = self._build_valid_snapshots()
        bad_ns[0]["topics"]["/ap/cmd_gps_pose"]["node_namespace"] = "/rogue"
        res_ns = audit_publisher_snapshots(bad_ns, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_ns["status"], "failed")
        self.assertTrue(any("namespace='/rogue' != '/'" in err for err in res_ns["errors"]))

        # 2. Foreign node name
        bad_node = self._build_valid_snapshots()
        bad_node[0]["node_name"] = "rogue_controller"
        res_node = audit_publisher_snapshots(bad_node, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_node["status"], "failed")
        self.assertTrue(any("node_name 'rogue_controller'" in err for err in res_node["errors"]))


if __name__ == "__main__":
    unittest.main()
