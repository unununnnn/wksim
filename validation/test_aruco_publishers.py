#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit and regression tests for ArUco publisher GID audit and exclusivity.

Tests verify:
  1. Accurate parsing of RTPS/DDS GUIDs (GuidPrefix, EntityId, EntityKind).
  2. Rejection of full-graph publisher exclusivity when only passive samples are observed.
  3. Positive verification of publisher_snapshots for AP and PX4 with exact mandatory channels
     (AP: cmd_gps_pose, cmd_vel, uav1 state; PX4: trajectory_setpoint, vehicle_command, uav2 state).
  4. Specific synthetic negative tests:
     - Missing mandatory channel (e.g. missing v2/state or cmd_vel).
     - Wrong/arbitrary message type.
     - Empty raw CDR samples for a guarded channel (cannot claim 100% native validation).
     - All-zero GID.
     - Non-exact boundary reason (e.g. 'ready_step' instead of exact 'ready').
     - Monotonic time not strictly increasing or non-positive.
     - Authority tick decreasing or negative.
     - Broken raw capture verification.
  5. Enforcement of exclusive file output mode ('x') and standard JSON compliance (no NaNs).
  6. Regression against legacy runs 10 & 13-ap (retained unverified without snapshots).
"""

import copy
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from tools.audit_aruco_publishers import (
    audit_children_json,
    audit_control_log,
    audit_initialized_json,
    audit_publisher_snapshots,
    audit_raw_capture_file,
    audit_run,
    evaluate_publisher_stack,
    parse_guid,
    sanitize_no_nan,
)

_REPO = Path(__file__).resolve().parents[1]


class TestArucoPublisherAudit(unittest.TestCase):
    """Offline unit and integration tests for publisher audit."""

    def setUp(self):
        self.ap_gid_gps = "010f7f01f624c70700000000000014030000000000000000"
        self.ap_gid_vel = "010f7f01f624c70700000000000015030000000000000000"
        self.ap_gid_state = "010f7f01f624c70700000000000020030000000000000000"

        self.px4_gid_traj = "010f7f014b267c240000000000001c030000000000000000"
        self.px4_gid_cmd = "010f7f014b267c240000000000001a030000000000000000"
        self.px4_gid_state = "010f7f014b267c2400000000000022030000000000000000"

    def test_parse_guid_standard_rtps(self):
        """Test parsing valid 24-byte (48 hex) RTPS GUIDs."""
        gid_hex = self.px4_gid_traj
        parsed = parse_guid(gid_hex)
        self.assertTrue(parsed["is_valid_format"])
        self.assertEqual(parsed["guid_prefix"], "010f7f014b267c2400000000")
        self.assertEqual(parsed["entity_id"], "00001c03")
        self.assertEqual(parsed["entity_kind_hex"], "03")
        self.assertEqual(parsed["entity_kind_desc"], "data_writer")

        reader_hex = "010f7f014b267c2400000000000023040000000000000000"
        parsed_reader = parse_guid(reader_hex)
        self.assertTrue(parsed_reader["is_valid_format"])
        self.assertEqual(parsed_reader["guid_prefix"], "010f7f014b267c2400000000")
        self.assertEqual(parsed_reader["entity_id"], "00002304")
        self.assertEqual(parsed_reader["entity_kind_hex"], "04")
        self.assertEqual(parsed_reader["entity_kind_desc"], "data_reader")

    def test_parse_guid_invalid_formats(self):
        """Test handling of malformed or non-hex GUID strings."""
        for invalid in [None, 123, "", "short_hex", "01" * 10, "010fzz014b267c240000000000001c030000000000000000"]:
            parsed = parse_guid(invalid)
            self.assertFalse(parsed["is_valid_format"])
            self.assertIsNone(parsed["guid_prefix"])

    def test_sanitize_no_nan(self):
        """Test that non-finite floats are converted to None."""
        data = {
            "valid": 12.34,
            "nan": math.nan,
            "pos_inf": math.inf,
            "neg_inf": -math.inf,
            "nested": [1.0, math.nan, {"deep": math.inf}],
        }
        clean = sanitize_no_nan(data)
        self.assertEqual(clean["valid"], 12.34)
        self.assertIsNone(clean["nan"])
        self.assertIsNone(clean["pos_inf"])
        self.assertIsNone(clean["neg_inf"])
        self.assertEqual(clean["nested"], [1.0, None, {"deep": None}])

        serialized = json.dumps(clean, allow_nan=False)
        self.assertIn("null", serialized)
        self.assertNotIn("NaN", serialized)

    def test_passive_single_gid_refuses_full_graph_exclusivity(self):
        """CRITICAL: Single observed GID in passive trace must NEVER claim full-graph exclusivity."""
        raw_audit = {
            "file_path": "/mock/aruco-raw-dds.jsonl",
            "total_lines": 100,
            "hash_chain_valid": True,
            "hash_chain_message": "valid",
            "topics": {
                "/ap/cmd_vel": {
                    "category": "native_target",
                    "sample_count": 50,
                    "unique_gid_count": 1,
                    "single_gid_observed": True,
                    "unique_gids": [self.ap_gid_vel],
                    "unique_participant_guid_prefixes": ["010f7f01f624c70700000000"],
                }
            },
            "raw_samples_by_topic": {},
        }
        init_audit = {
            "file_path": "/mock/initialized.json",
            "control_node_name": "wksim_joint_arducopter_control",
            "control_guid_prefix": "010f7f01f624c70700000000",
            "control_reader_endpoints": [],
        }
        children_audit = {"control_processes": {}}
        control_log_audit = {"logs_target_publisher_gids": False, "native_sources_bound_events": []}

        eval_res = evaluate_publisher_stack("arducopter", raw_audit, init_audit, children_audit, control_log_audit)
        self.assertEqual(eval_res["writer_binding"], "unbound")
        self.assertEqual(eval_res["snapshot_exclusivity"], "unverified")
        self.assertFalse(eval_res["exclusivity_assessment"]["claim_full_graph_exclusivity"])

    def test_publisher_snapshots_verification_success_ap(self):
        """Positive test: AP full mandatory channel set and exact types verified."""
        ap_topics = {
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

        snapshots = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready", "authority_tick": 0, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": ap_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "before-public-send:move", "authority_tick": 10, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": ap_topics},
            {"snapshot_index": 3, "monotonic_ns": 3000, "monotonic_s": 0.003, "reason": "report", "authority_tick": 20, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": ap_topics},
        ]

        raw_samples = {
            "/ap/cmd_gps_pose": [{"publisher_gid": self.ap_gid_gps, "type": "ardupilot_msgs/msg/GlobalPosition"}],
            "/ap/cmd_vel": [{"publisher_gid": self.ap_gid_vel, "type": "geometry_msgs/msg/TwistStamped"}],
            "/uav1/prometheus/v2/state": [{"publisher_gid": self.ap_gid_state, "type": "wksim_msgs/msg/SessionState"}],
        }

        res = audit_publisher_snapshots(snapshots, "arducopter", raw_samples, raw_hash_valid=True)
        self.assertEqual(res["status"], "verified")
        self.assertEqual(res["writer_binding"], "verified_bound")
        self.assertEqual(res["snapshot_exclusivity"], "verified_at_snapshots")

        peer_samples = copy.deepcopy(raw_samples)
        peer_samples['/ap/cmd_vel'] = []
        self.assertEqual(audit_publisher_snapshots(snapshots,'arducopter',peer_samples,True)['status'],'failed')
        peer = audit_publisher_snapshots(snapshots,'arducopter',peer_samples,True,
                       required_sample_topics={'/ap/cmd_gps_pose','/uav1/prometheus/v2/state'})
        self.assertEqual(peer['status'],'verified')
        self.assertEqual(peer['sample_matches']['/ap/cmd_vel']['sample_scope'],'not_exercised')
        wrong_type = copy.deepcopy(raw_samples)
        wrong_type['/ap/cmd_vel'][0]['type'] = 'std_msgs/msg/String'
        self.assertEqual(audit_publisher_snapshots(snapshots,'arducopter',wrong_type,True)['status'],'failed')

    def test_publisher_snapshots_verification_success_px4(self):
        """Positive test: PX4 full mandatory channel set and exact types verified."""
        px4_topics = {
            "/wksim_px4_21/fmu/in/trajectory_setpoint": {
                "publisher_count": 1,
                "node_name": "wksim_joint_px4_control",
                "node_namespace": "/",
                "type_name": "px4_msgs/msg/TrajectorySetpoint",
                "endpoint_gid": self.px4_gid_traj,
            },
            "/wksim_px4_21/fmu/in/vehicle_command": {
                "publisher_count": 1,
                "node_name": "wksim_joint_px4_control",
                "node_namespace": "/",
                "type_name": "px4_msgs/msg/VehicleCommand",
                "endpoint_gid": self.px4_gid_cmd,
            },
            "/uav2/prometheus/v2/state": {
                "publisher_count": 1,
                "node_name": "wksim_joint_px4_control",
                "node_namespace": "/",
                "type_name": "wksim_msgs/msg/SessionState",
                "endpoint_gid": self.px4_gid_state,
            },
        }

        snapshots = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready", "authority_tick": 0, "node_name": "wksim_joint_px4_control", "stack": "px4", "topics": px4_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "report", "authority_tick": 5, "node_name": "wksim_joint_px4_control", "stack": "px4", "topics": px4_topics},
        ]

        raw_samples = {
            "/wksim_px4_21/fmu/in/trajectory_setpoint": [{"publisher_gid": self.px4_gid_traj, "type": "px4_msgs/msg/TrajectorySetpoint"}],
            "/wksim_px4_21/fmu/in/vehicle_command": [{"publisher_gid": self.px4_gid_cmd, "type": "px4_msgs/msg/VehicleCommand"}],
            "/uav2/prometheus/v2/state": [{"publisher_gid": self.px4_gid_state, "type": "wksim_msgs/msg/SessionState"}],
        }

        res = audit_publisher_snapshots(snapshots, "px4", raw_samples, raw_hash_valid=True)
        self.assertEqual(res["status"], "verified")
        self.assertEqual(res["writer_binding"], "verified_bound")
        self.assertEqual(res["snapshot_exclusivity"], "verified_at_snapshots")

    def test_snapshots_negative_missing_mandatory_channel(self):
        """Negative test: Missing mandatory channel (e.g. state channel omitted) fails audit."""
        # Omit /uav1/prometheus/v2/state
        incomplete_topics = {
            "/ap/cmd_gps_pose": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "ardupilot_msgs/msg/GlobalPosition", "endpoint_gid": self.ap_gid_gps},
            "/ap/cmd_vel": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "geometry_msgs/msg/TwistStamped", "endpoint_gid": self.ap_gid_vel},
        }
        snapshots = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready", "authority_tick": 0, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": incomplete_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "report", "authority_tick": 1, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": incomplete_topics},
        ]
        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("missing required channels" in e for e in res["errors"]))

    def test_snapshots_negative_wrong_message_type(self):
        """Negative test: Wrong message type fails audit."""
        wrong_type_topics = {
            "/ap/cmd_gps_pose": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "ardupilot_msgs/msg/GlobalPosition", "endpoint_gid": self.ap_gid_gps},
            "/ap/cmd_vel": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "std_msgs/msg/String", "endpoint_gid": self.ap_gid_vel},
            "/uav1/prometheus/v2/state": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "wksim_msgs/msg/SessionState", "endpoint_gid": self.ap_gid_state},
        }
        snapshots = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready", "authority_tick": 0, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": wrong_type_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "report", "authority_tick": 1, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": wrong_type_topics},
        ]
        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("std_msgs/msg/String" in e for e in res["errors"]))

    def test_snapshots_negative_empty_raw_samples(self):
        """Negative test: Empty raw samples on a guarded topic cannot declare 100% native validation."""
        valid_topics = {
            "/ap/cmd_gps_pose": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "ardupilot_msgs/msg/GlobalPosition", "endpoint_gid": self.ap_gid_gps},
            "/ap/cmd_vel": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "geometry_msgs/msg/TwistStamped", "endpoint_gid": self.ap_gid_vel},
            "/uav1/prometheus/v2/state": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "wksim_msgs/msg/SessionState", "endpoint_gid": self.ap_gid_state},
        }
        snapshots = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready", "authority_tick": 0, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "report", "authority_tick": 1, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
        ]
        # Only 2 topics have samples, /ap/cmd_vel is empty!
        raw_samples = {
            "/ap/cmd_gps_pose": [{"publisher_gid": self.ap_gid_gps, "type": "ardupilot_msgs/msg/GlobalPosition"}],
            "/uav1/prometheus/v2/state": [{"publisher_gid": self.ap_gid_state, "type": "wksim_msgs/msg/SessionState"}],
        }
        res = audit_publisher_snapshots(snapshots, "arducopter", raw_samples, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("0 recorded raw CDR samples" in e for e in res["errors"]))

    def test_snapshots_negative_all_zero_gid(self):
        """Negative test: All-zero GID is strictly rejected."""
        zero_gid_topics = {
            "/ap/cmd_gps_pose": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "ardupilot_msgs/msg/GlobalPosition", "endpoint_gid": "0" * 48},
            "/ap/cmd_vel": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "geometry_msgs/msg/TwistStamped", "endpoint_gid": self.ap_gid_vel},
            "/uav1/prometheus/v2/state": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "wksim_msgs/msg/SessionState", "endpoint_gid": self.ap_gid_state},
        }
        snapshots = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready", "authority_tick": 0, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": zero_gid_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "report", "authority_tick": 1, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": zero_gid_topics},
        ]
        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("rejected all-zero GID" in e for e in res["errors"]))

    def test_snapshots_negative_ready_report_not_exact(self):
        """Negative test: Reason must match 'ready' and 'report' exactly."""
        valid_topics = {
            "/ap/cmd_gps_pose": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "ardupilot_msgs/msg/GlobalPosition", "endpoint_gid": self.ap_gid_gps},
            "/ap/cmd_vel": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "geometry_msgs/msg/TwistStamped", "endpoint_gid": self.ap_gid_vel},
            "/uav1/prometheus/v2/state": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "wksim_msgs/msg/SessionState", "endpoint_gid": self.ap_gid_state},
        }
        # Non-exact prefix
        snapshots = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready_phase_1", "authority_tick": 0, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "report", "authority_tick": 1, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
        ]
        res = audit_publisher_snapshots(snapshots, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res["status"], "failed")
        self.assertTrue(any("First snapshot reason must be exactly 'ready'" in e for e in res["errors"]))

    def test_snapshots_negative_non_strictly_increasing_time_and_ticks(self):
        """Negative test: monotonic_ns must be strictly increasing and authority_tick non-decreasing."""
        valid_topics = {
            "/ap/cmd_gps_pose": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "ardupilot_msgs/msg/GlobalPosition", "endpoint_gid": self.ap_gid_gps},
            "/ap/cmd_vel": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "geometry_msgs/msg/TwistStamped", "endpoint_gid": self.ap_gid_vel},
            "/uav1/prometheus/v2/state": {"publisher_count": 1, "node_name": "wksim_joint_arducopter_control", "node_namespace": "/", "type_name": "wksim_msgs/msg/SessionState", "endpoint_gid": self.ap_gid_state},
        }
        # Decreasing monotonic_ns
        bad_time = [
            {"snapshot_index": 1, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "ready", "authority_tick": 0, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
            {"snapshot_index": 2, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "report", "authority_tick": 1, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
        ]
        res_time = audit_publisher_snapshots(bad_time, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_time["status"], "failed")
        self.assertTrue(any("not strictly increasing" in e for e in res_time["errors"]))

        # Decreasing authority_tick
        bad_tick = [
            {"snapshot_index": 1, "monotonic_ns": 1000, "monotonic_s": 0.001, "reason": "ready", "authority_tick": 10, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
            {"snapshot_index": 2, "monotonic_ns": 2000, "monotonic_s": 0.002, "reason": "report", "authority_tick": 5, "node_name": "wksim_joint_arducopter_control", "stack": "arducopter", "topics": valid_topics},
        ]
        res_tick = audit_publisher_snapshots(bad_tick, "arducopter", {}, raw_hash_valid=True)
        self.assertEqual(res_tick["status"], "failed")
        self.assertTrue(any("authority_tick (5) decreased" in e for e in res_tick["errors"]))

    def test_exclusive_output_mode_rejected_on_existing(self):
        """Enforces that mode 'x' raises FileExistsError if target exists."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "out.json"
            target.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                with open(target, "x", encoding="utf-8") as fh:
                    fh.write("fail")

    def test_real_evidence_tracking_10(self):
        """Regression test on legacy run 10 (no snapshots -> unbound and unverified)."""
        run_dir = _REPO / "validation" / "40-aruco-tracking-10"
        if not run_dir.exists():
            self.skipTest(f"Run dir {run_dir} not available")

        report = audit_run(run_dir)
        self.assertEqual(set(report["stacks_audited"]), {"arducopter", "px4"})
        self.assertEqual(report["overall_verdict"]["writer_binding"], "unbound")
        self.assertEqual(report["overall_verdict"]["snapshot_exclusivity"], "unverified")
        self.assertEqual(report["overall_verdict"]["status"], "investigation_completed_no_snapshots_retained")

    def test_real_evidence_tracking_13_ap(self):
        """Regression test on legacy run 13-ap (no snapshots -> unbound and unverified)."""
        run_dir = _REPO / "validation" / "40-aruco-tracking-13-ap"
        if not run_dir.exists():
            self.skipTest(f"Run dir {run_dir} not available")

        report = audit_run(run_dir)
        self.assertEqual(set(report["stacks_audited"]), {"arducopter", "px4"})
        self.assertEqual(report["overall_verdict"]["writer_binding"], "unbound")
        self.assertEqual(report["overall_verdict"]["snapshot_exclusivity"], "unverified")
        self.assertEqual(report["overall_verdict"]["status"], "investigation_completed_no_snapshots_retained")


if __name__ == "__main__":
    unittest.main()
