"""Offline tests for tools/audit_aruco_native_moves.py with real message CDR.

Synthetic evidence uses installed ROS message classes and rclpy serialization
(message construction only; no node/simulation/DDS participant). Timing model
matches the verified source order: within one tick, drive publishes native
setpoints BEFORE the SessionState that first carries the request id, so a
native sample's timestamp precedes its tick's SessionState timestamp.

Skipped where the overlays are unavailable (Windows); runs in WSL.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from rclpy.serialization import serialize_message
    from wksim_msgs.msg import CommandRequest, SessionState
    from prometheus_msgs.msg import UAVCommand, UAVState, UAVControlState
    from px4_msgs.msg import TrajectorySetpoint
    from geometry_msgs.msg import Quaternion, TwistStamped, Twist, Vector3
    ROS = True
except ImportError:
    ROS = False

from tools.audit_aruco_native_moves import (
    audit_epoch, px4_expected, ap_expected, quaternion_yaw)

RUN = "aruco-track-testrun01"
EPOCH = "ab" * 16
GID = "01" * 24


def chain(rows):
    """Apply the capture module's canonical-JSON hash chain."""
    previous = "0" * 64
    for row in rows:
        row["prev_record_sha256"] = previous
        canonical = json.dumps(row, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode()
        row["record_sha256"] = hashlib.sha256(canonical).hexdigest()
        previous = row["record_sha256"]
    return rows


def raw(topic, msg, source_ns, gid=GID):
    parts = msg.__class__.__module__.split(".")
    type_name = f"{parts[0]}/msg/{msg.__class__.__name__}"
    return {"kind": "raw_cdr_sample", "topic": topic, "type": type_name,
            "cdr_hex": serialize_message(msg).hex(), "message": None,
            "publisher_gid": gid, "source_timestamp": source_ns,
            "received_timestamp": source_ns + 1000, "monotonic_ns": source_ns,
            "take_sequence": source_ns, "schema_version": "1"}


def command(rid, command_id, source_ns, velocity=(0.1, 0.0, 0.0), uav=2):
    cmd = UAVCommand(agent_cmd=UAVCommand.MOVE, move_mode=UAVCommand.XYZ_VEL_BODY,
                     velocity_ref=list(velocity), yaw_rate_mode=True, yaw_rate_ref=0.0,
                     command_id=command_id)
    msg = CommandRequest(version=1, run_id=RUN, control_epoch=EPOCH,
                         request_id=rid, command=cmd)
    return raw(f"/uav{uav}/prometheus/v2/command", msg, source_ns)


def state(rid, sequence, source_ns, yaw=0.0, uav=2):
    q = Quaternion(w=math.cos(yaw / 2), x=0.0, y=0.0, z=math.sin(yaw / 2))
    msg = SessionState(version=1, run_id=RUN, control_epoch=EPOCH, sequence=sequence,
                       last_request_id=rid, native_generation=1, source_clock="fc_boot",
                       source_received_valid=True, source_received_monotonic_s=1.0,
                       published_monotonic_s=2.0,
                       state=UAVState(attitude_q=q), control=UAVControlState())
    return raw(f"/uav{uav}/prometheus/v2/state", msg, source_ns)


def setpoint(velocity_ned, source_ns, gid=GID):
    msg = TrajectorySetpoint()
    msg.position = [math.nan] * 3
    msg.velocity = [float(v) for v in velocity_ned]
    msg.acceleration = [math.nan] * 3
    msg.jerk = [math.nan] * 3
    msg.yaw = math.nan
    msg.yawspeed = -0.0
    return raw("/wksim_px4_21/fmu/in/trajectory_setpoint", msg, source_ns, gid)


def twist(linear_enu, source_ns):
    msg = TwistStamped()
    msg.header.frame_id = "map"
    msg.twist = Twist(linear=Vector3(x=float(linear_enu[0]), y=float(linear_enu[1]),
                                     z=float(linear_enu[2])),
                      angular=Vector3(x=0.0, y=0.0, z=0.0))
    return raw("/ap/cmd_vel", msg, source_ns)


def envelope(rows, stack):
    """Wrap data rows with the real capture start/end records."""
    counts = {}
    for row in rows:
        counts[row["topic"]] = counts.get(row["topic"], 0) + 1
    start = {"kind": "aruco_raw_capture_start", "schema_version": "1",
             "node_name": f"wksim_aruco_raw_{stack}", "run_id": RUN, "epoch": EPOCH,
             "stack": stack, "uav_id": {"arducopter": "1", "px4": "2"}[stack],
             "channels": [], "start_monotonic_ns": 1}
    end = {"kind": "aruco_raw_capture_end", "schema_version": "1", "status": "complete",
           "samples_per_topic": counts, "total_samples": len(rows),
           "write_failure_reports": [], "close_monotonic_ns": 2}
    return [start] + rows + [end]


def epoch_dir(tmp, rows_by_stack):
    root = Path(tmp) / "epochs" / EPOCH
    for stack, rows in rows_by_stack.items():
        folder = root / "tasks" / "group" / stack
        folder.mkdir(parents=True)
        full = envelope(rows, stack)
        full[-1]["final_hash_chain"] = None  # Filled after chaining below.
        chained = chain(full)
        chained[-1]["final_hash_chain"] = chained[-2]["record_sha256"]
        # Re-hash the end record after filling final_hash_chain.
        content = {k: v for k, v in chained[-1].items()
                   if k not in ("record_sha256",)}
        chained[-1]["record_sha256"] = hashlib.sha256(json.dumps(
            content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        with (folder / "aruco-raw-dds.jsonl").open("w", encoding="utf-8") as stream:
            for row in chained:
                stream.write(json.dumps(row) + "\n")
    return root


@unittest.skipUnless(ROS, "requires the ROS message overlays (WSL)")
class FormulaTests(unittest.TestCase):
    def test_px4_axes_and_yaw(self):
        import numpy as np
        f32 = np.float32
        expected = px4_expected([0.1, 0.0, 0.05], 0.0, np)
        self.assertEqual([float(v) for v in expected["velocity"]],
                         [float(f32(0.0)), float(f32(0.1)), float(f32(-0.05))])
        yaw90 = quaternion_yaw(math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
        expected = px4_expected([0.1, 0.0, 0.0], yaw90, np)
        self.assertAlmostEqual(float(expected["velocity"][0]), 0.1, places=6)
        self.assertAlmostEqual(float(expected["velocity"][1]), 0.0, places=6)

    def test_ap_velocity_is_not_axis_swapped(self):
        # native_arducopter writes target.velocity unswapped into Twist.linear.
        ap = ap_expected([0.1, 0.0, 0.05], 0.0)
        self.assertEqual(ap["linear"], (0.1, 0.0, 0.05))
        yaw90 = quaternion_yaw(math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
        rotated = ap_expected([0.1, 0.0, 0.0], yaw90)
        self.assertAlmostEqual(rotated["linear"][0], 0.0, places=9)
        self.assertAlmostEqual(rotated["linear"][1], 0.1, places=9)


@unittest.skipUnless(ROS, "requires the ROS message overlays (WSL)")
class AuditTests(unittest.TestCase):
    def px4_fixture(self, tmp, native_rows, velocity=(0.1, -0.2, 0.05), yaw=0.3):
        import numpy as np
        yaw_q = quaternion_yaw(math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2))
        wired = [float(np.float32(v)) for v in velocity]
        expected = px4_expected(wired, yaw_q, np)
        rows = [command(1, 1, 1_000_000_000, wired),
                state(0, 1, 900_000_000), state(1, 2, 1_100_000_000, yaw=yaw)]
        rows[1:1] = native_rows(expected)
        return epoch_dir(tmp, {"px4": rows, "arducopter": []})

    def test_single_move_proven_with_exact_float32_setpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Same tick, native published before the state that carries the rid.
            root = self.px4_fixture(tmp, lambda e: [setpoint(
                [float(v) for v in e["velocity"]], 1_050_000_000)])
            result = audit_epoch(root)
            move = result["stacks"]["px4"]["moves"][0]
            self.assertEqual(move["status"], "proven")
            self.assertEqual(move["samples"], 1)
            self.assertEqual(result["status"], "unresolved")  # AP capture empty.

    def test_sample_after_last_state_is_not_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.px4_fixture(tmp, lambda e: [setpoint(
                [float(v) for v in e["velocity"]], 9_000_000_000)])  # After all states.
            result = audit_epoch(root)
            self.assertEqual(result["stacks"]["px4"]["moves"][0]["status"], "unresolved")
            self.assertTrue(any("after the last" in u.get("reason", "")
                                for u in result["unresolved"]))

    def test_sample_of_next_command_belongs_to_next_request(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            v1 = [float(np.float32(v)) for v in (0.1, 0.0, 0.0)]
            v2 = [float(np.float32(v)) for v in (0.2, 0.0, 0.0)]
            e1 = px4_expected(v1, 0.0, np)
            e2 = px4_expected(v2, 0.0, np)
            rows = [command(1, 1, 1_000_000_000, v1), command(2, 2, 2_000_000_000, v2),
                    setpoint([float(v) for v in e1["velocity"]], 1_050_000_000),
                    setpoint([float(v) for v in e2["velocity"]], 2_050_000_000),
                    state(0, 1, 900_000_000), state(1, 2, 1_100_000_000),
                    state(2, 3, 2_100_000_000)]
            result = audit_epoch(epoch_dir(tmp, {"px4": rows, "arducopter": []}))
            moves = result["stacks"]["px4"]["moves"]
            self.assertEqual([m["status"] for m in moves], ["proven", "proven"])
            self.assertEqual([m["samples"] for m in moves], [1, 1])

    def test_one_ulp_difference_is_caught(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            captured = {}

            def drifted_rows(expected):
                drifted = np.nextafter(expected["velocity"][1], np.float32(1.0))
                return [setpoint([float(expected["velocity"][0]), float(drifted),
                                  float(expected["velocity"][2])], 1_050_000_000)]
            root = self.px4_fixture(tmp, drifted_rows)
            result = audit_epoch(root)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failures"][0]["code"], "native_setpoint_differs")

    def test_missing_native_sample_is_unresolved_not_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.px4_fixture(tmp, lambda e: [])
            result = audit_epoch(root)
            self.assertEqual(result["stacks"]["px4"]["moves"][0]["status"], "unresolved")
            self.assertEqual(result["status"], "unresolved")

    def test_unexecuted_command_is_unresolved(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            wired = [float(np.float32(v)) for v in (0.1, -0.2, 0.05)]
            expected = px4_expected(wired, quaternion_yaw(math.cos(0.15), 0, 0,
                                                          math.sin(0.15)), np)
            # The states never carry rid 1: the request was rejected/merged.
            rebuilt = [command(1, 1, 1_000_000_000, wired),
                       setpoint([float(v) for v in expected["velocity"]], 1_050_000_000),
                       state(0, 1, 900_000_000), state(0, 2, 1_100_000_000, yaw=0.3)]
            result = audit_epoch(epoch_dir(tmp, {"px4": rebuilt, "arducopter": []}))
            self.assertEqual(result["stacks"]["px4"]["moves"][0]["status"], "unresolved")

    def test_state_only_coordination_stack_uses_its_observed_epoch(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [state(0, 14, 900_000_000, uav=1),
                    state(0, 15, 1_100_000_000, uav=1)]
            result = audit_epoch(epoch_dir(tmp, {"px4": [], "arducopter": rows}))
            self.assertEqual(result["failures"], [])
            self.assertEqual(result["stacks"]["arducopter"]["moves"], [])
            self.assertEqual(result["status"], "unresolved")  # PX4 capture is empty.

    def test_state_sequence_gap_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            import numpy as np
            wired = [float(np.float32(v)) for v in (0.1, 0.0, 0.0)]
            expected = px4_expected(wired, 0.0, np)
            rows = [command(1, 1, 1_000_000_000, wired),
                    setpoint([float(v) for v in expected["velocity"]], 1_050_000_000),
                    state(0, 1, 900_000_000), state(1, 3, 1_100_000_000)]  # 1 -> 3
            result = audit_epoch(epoch_dir(tmp, {"px4": rows, "arducopter": []}))
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failures"][0]["code"], "session_state_sequence_gap")

    def test_hash_chain_break_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = envelope([command(1, 1, 1_000_000_000),
                             state(0, 1, 900_000_000), state(1, 2, 1_100_000_000)], "px4")
            rows[-1]["final_hash_chain"] = None
            chained = chain(rows)
            chained[2]["prev_record_sha256"] = "ff" * 32  # Content-consistent relink.
            content = {k: v for k, v in chained[2].items() if k != "record_sha256"}
            chained[2]["record_sha256"] = hashlib.sha256(json.dumps(
                content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            folder = Path(tmp) / "epochs" / EPOCH / "tasks" / "group" / "px4"
            folder.mkdir(parents=True)
            with (folder / "aruco-raw-dds.jsonl").open("w", encoding="utf-8") as stream:
                for row in chained:
                    stream.write(json.dumps(row) + "\n")
            result = audit_epoch(Path(tmp) / "epochs" / EPOCH)
            self.assertEqual(result["status"], "failed")
            self.assertIn("hash_chain_broken", [f["code"] for f in result["failures"]])

    def test_two_native_publishers_rejected(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            wired = [float(np.float32(v)) for v in (0.1, 0.0, 0.0)]
            expected = px4_expected(wired, 0.0, np)
            rows = [command(1, 1, 1_000_000_000, wired),
                    setpoint([float(v) for v in expected["velocity"]], 1_050_000_000),
                    setpoint([float(v) for v in expected["velocity"]], 1_060_000_000,
                             gid="02" * 24),
                    state(0, 1, 900_000_000), state(1, 2, 1_100_000_000)]
            result = audit_epoch(epoch_dir(tmp, {"px4": rows, "arducopter": []}))
            self.assertEqual(result["status"], "failed")
            self.assertIn("native_publisher_gid_not_unique",
                          [f["code"] for f in result["failures"]])

    def test_ap_twist_unswapped_passes_swapped_fails(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            velocity = [float(np.float32(v)) for v in (0.1, -0.2, 0.05)]
            yaw = quaternion_yaw(math.cos(0.15), 0.0, 0.0, math.sin(0.15))
            expected = ap_expected(velocity, yaw)
            rows = [command(1, 1, 1_000_000_000, velocity, uav=1),
                    twist(expected["linear"], 1_050_000_000),
                    state(0, 1, 900_000_000, uav=1), state(1, 2, 1_100_000_000, yaw=0.3, uav=1)]
            result = audit_epoch(epoch_dir(tmp, {"px4": [], "arducopter": rows}))
            self.assertEqual(result["stacks"]["arducopter"]["moves"][0]["status"], "proven")
            swapped = [command(1, 1, 1_000_000_000, velocity, uav=1),
                       twist((expected["linear"][1], expected["linear"][0],
                              expected["linear"][2]), 1_050_000_000),
                       state(0, 1, 900_000_000, uav=1), state(1, 2, 1_100_000_000, yaw=0.3, uav=1)]
            result = audit_epoch(epoch_dir(tmp + "/b", {"px4": [], "arducopter": swapped}))
            self.assertEqual(result["status"], "failed")

    def test_missing_envelope_is_a_failure(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            wired = [float(np.float32(v)) for v in (0.1, 0.0, 0.0)]
            expected = px4_expected(wired, 0.0, np)
            rows = [command(1, 1, 1_000_000_000, wired),
                    setpoint([float(v) for v in expected["velocity"]], 1_050_000_000),
                    state(0, 1, 900_000_000), state(1, 2, 1_100_000_000)]
            root = self._bare(tmp, rows)  # No start/end records at all.
            result = audit_epoch(root)
            self.assertEqual(result["status"], "failed")
            self.assertIn("capture_start_missing", [f["code"] for f in result["failures"]])

    def _bare(self, tmp, rows):
        root = Path(tmp) / "epochs" / EPOCH
        folder = root / "tasks" / "group" / "px4"
        folder.mkdir(parents=True)
        with (folder / "aruco-raw-dds.jsonl").open("w", encoding="utf-8") as stream:
            for row in chain(rows):
                stream.write(json.dumps(row) + "\n")
        return root

    def test_non_frozen_command_variants_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = UAVCommand(agent_cmd=UAVCommand.MOVE, move_mode=UAVCommand.XYZ_VEL,
                             velocity_ref=[0.1, 0.0, 0.0], yaw_rate_mode=True,
                             yaw_rate_ref=0.0, command_id=1)
            msg = CommandRequest(version=1, run_id=RUN, control_epoch=EPOCH,
                                 request_id=1, command=cmd)
            rows = [raw("/uav2/prometheus/v2/command", msg, 1_000_000_000),
                    state(0, 1, 900_000_000)]
            result = audit_epoch(epoch_dir(tmp, {"px4": rows, "arducopter": []}))
            self.assertEqual(result["stacks"]["px4"]["moves"], [])


if __name__ == "__main__":
    unittest.main()
