"""Misalignment negative tests for tools/audit_aruco_tracking_physical.py.

Synthetic truth traces are generated in the model's real convention (state[2]
seconds, state[6:9] NED, state[12:16] WXYZ quaternion — verified against the
retained scene-03 trace) so the auditor's bridge mapping [N,E,-D] /
quat[-x,-y,z,w] is exercised for detection, not re-implemented. No ROS,
simulation, or build is started.

Run: work/dependencies/aruco-python/Scripts/python.exe -B -m unittest validation.test_aruco_physical_review -v
(numpy only; the pinned ArUco venv provides it)
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from tools.audit_aruco_tracking_physical import evaluate_trace
from tools.audit_aruco_scene import rotation
from Simulator.wksim_runtime.aruco_joint_task import load_frozen_profile

PROFILE, _ = load_frozen_profile()
EPOCH = "e6462b20c769429c9c559b241fc1dff1"
FIRST, END = 1000, 13000
ANCHOR = np.array([0.0, 0.0, 3.0])
IDENTITY_Q = [1.0, 0.0, 0.0, 0.0]  # WXYZ, as the model truth stores it.
YAW90_Q = [np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)]
YAW90_FLIPPED = [np.sqrt(0.5), 0.0, 0.0, -np.sqrt(0.5)]  # wrong bridge convention


def movement(tick):
    return np.array([0.0, min(4000, max(0, tick - FIRST - 2000)) * 0.00025, 0.0])


def write_trace(path, *, quat=IDENTITY_Q, z_sign=-1.0, drop_tick=None,
                tracking_offset=None, recovery_error=0.0, anchor_rot=None):
    """One synthetic truth.jsonl in the model convention. Vehicle perfectly
    tracks unless tracking_offset (world NEU, added to the correct position)
    or recovery_error (extra +X NEU offset inside the recovery window) given."""
    anchor_rot = IDENTITY_Q if anchor_rot is None else anchor_rot
    rot = rotation([-anchor_rot[1], -anchor_rot[2], anchor_rot[3], anchor_rot[0]])
    desired = np.asarray(PROFILE["controller"]["desired_body_flu_m"])
    last = END + 500
    with open(path, "w", encoding="utf-8") as stream:
        for tick in range(1, last + 1):
            if tick == drop_tick:
                continue
            if FIRST <= tick <= END:
                target = ANCHOR + rot @ np.array([2.3, 0.32, 0.06]) + movement(tick)
                position = ANCHOR + movement(tick)
                if tracking_offset is not None:
                    position = position + tracking_offset
                if tick >= END - PROFILE["mission"]["recovery_hold_steps"]:
                    position = position + np.array([recovery_error, 0.0, 0.0])
                # Keep the auditor's body relation exact for the pass cases.
                if tracking_offset is None and recovery_error == 0.0:
                    position = target - rot @ np.array([desired[0], -desired[1], desired[2]])
                z = position[2]
            elif tick > END:
                z = 0.0
                position = np.array([0.0, 0.0, 0.0])
            else:
                z = 0.0
                position = np.array([0.0, 0.0, 0.0])
            state = [0.0] * 120
            state[2] = tick / 1000
            state[6:9] = [position[0], position[1], z_sign * z]
            state[12:16] = quat
            stream.write(json.dumps({"tick": tick, "epoch": EPOCH, "state": state}) + "\n")
    return path


def run_trace(path, selected=True):
    return evaluate_trace(Path(path), EPOCH, FIRST, END, ANCHOR,
                          rotation([0.0, 0.0, 0.0, 1.0]), PROFILE, selected)


class TruthLayoutEvidenceTests(unittest.TestCase):
    def test_retained_real_trace_confirms_index_and_sign_convention(self):
        real = (ROOT / "validation/40-aruco-flight-scene-03/run/epochs"
                / "3604073ff2b94dc5938972d7cd95e092/px4-truth.jsonl")
        rows = {}
        with real.open() as stream:
            for line in stream:
                row = json.loads(line)
                if row["tick"] in (1, 53168):
                    rows[row["tick"]] = row["state"]
        self.assertAlmostEqual(rows[1][2], 0.001)          # state[2] seconds
        self.assertEqual(rows[1][6:9], [0.0, 0.0, 0.0])    # ground origin
        self.assertEqual(rows[1][12:16], [1.0, 0.0, 0.0, 0.0])  # WXYZ identity
        self.assertAlmostEqual(rows[53168][8], -3.0, delta=0.2)  # NED Down ~ -3 airborne
        self.assertAlmostEqual(rows[53168][2], 53.168)


class EvaluateTraceTests(unittest.TestCase):
    def test_perfect_tracking_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_trace(write_trace(Path(tmp) / "t.jsonl"))
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["samples"], END - FIRST + 1)
            self.assertLess(result["max_tracking_error_m"], 1e-9)

    def test_yawed_vehicle_with_correct_quaternion_mapping_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_trace(Path(tmp) / "t.jsonl", quat=YAW90_Q, anchor_rot=YAW90_Q)
            result = evaluate_trace(Path(path), EPOCH, FIRST, END, ANCHOR,
                                    rotation([0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)]), PROFILE, True)
            self.assertEqual(result["status"], "pass", result["failure_examples"][:2])

    def test_flipped_quaternion_convention_is_caught(self):
        # Same physical scene, but the truth quaternion stored with the wrong
        # z sign (as if the bridge [-x,-y,z,w] mapping were forgotten).
        with tempfile.TemporaryDirectory() as tmp:
            path = write_trace(Path(tmp) / "t.jsonl", quat=YAW90_FLIPPED, anchor_rot=YAW90_Q)
            result = evaluate_trace(Path(path), EPOCH, FIRST, END, ANCHOR,
                                    rotation([0.0, 0.0, np.sqrt(0.5), np.sqrt(0.5)]), PROFILE, True)
            self.assertEqual(result["status"], "failed")
            gates = {f["gate"] for f in result["failure_examples"]}
            self.assertIn("tracking", gates)

    def test_up_positive_position_convention_is_caught(self):
        # Producer stored z up-positive (NEU) instead of NED Down.
        with tempfile.TemporaryDirectory() as tmp:
            result = run_trace(write_trace(Path(tmp) / "t.jsonl", z_sign=1.0))
            self.assertEqual(result["status"], "failed")

    def test_missing_tick_breaks_the_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                run_trace(write_trace(Path(tmp) / "t.jsonl", drop_tick=7000))

    def test_tracking_error_beyond_gate_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_trace(write_trace(Path(tmp) / "t.jsonl",
                                           tracking_offset=np.array([0.7, 0.0, 0.0])))
            self.assertEqual(result["status"], "failed")
            self.assertGreater(result["max_tracking_error_m"], PROFILE["mission"]["tracking_error_m"])

    def test_recovery_window_error_is_caught_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 0.4 m extra error only inside the recovery window: under the 0.65
            # tracking gate but above the 0.3 recovery gate.
            result = run_trace(write_trace(Path(tmp) / "t.jsonl", recovery_error=0.4))
            self.assertEqual(result["status"], "failed")
            self.assertGreater(result["max_final_recovery_error_m"],
                               PROFILE["mission"]["recovery_error_m"])

    def test_peer_stack_evaluated_without_tracking_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_trace(write_trace(Path(tmp) / "t.jsonl"), selected=False)
            self.assertEqual(result["status"], "pass")
            self.assertIsNone(result["max_tracking_error_m"])


if __name__ == "__main__":
    unittest.main()
