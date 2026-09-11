import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from tools import probe_joint_terrain_feedback as probe
from Simulator.wksim_core.static_contact import StaticScene


EPOCH = "0123456789abcdef0123456789abcdef"


def state(tick, marker=0.0):
    values = [0.0] * 120
    values[0] = marker
    values[2] = tick * 0.001
    values[60] = tick * 1000.0
    return values


def trace_rows(terrain, marker):
    rows = []
    for tick in range(1, probe.TICKS + 1):
        request = {
            "version": 1,
            "epoch": EPOCH,
            "tick": tick,
            "commands": [0.0] * 16,
            "terrain": list(terrain),
        }
        rows.append({
            "version": 1,
            "epoch": EPOCH,
            "tick": tick,
            "state": state(tick, marker),
            "request": request,
            "input": json.dumps(request, separators=(",", ":")),
            "commands": [0.0] * 16,
            "terrain": list(terrain),
        })
    return rows


def clocks():
    result = []
    for tick in range(probe.TICKS + 1):
        result.append({
            "tick": tick,
            "time_ns": tick * 1_000_000,
            "pending_tick": None,
            "phase": "running",
            "last_barrier_tick": tick - tick % 4,
            "last_input_tick": tick,
            "synchronized": tick >= 4,
            "input_pending": False,
            "recoverable": False,
        })
    return result


class ProbePureLogicTests(unittest.TestCase):
    def test_native_io_stub_messages_supply_deterministic_evidence_bytes(self):
        clock = Mock(tick=4)
        stub = probe.DeterministicNativeIOStub(clock)
        first = stub.hil_sensor_encode(4_000, 1.0, 2.0)
        second = stub.hil_sensor_encode(4_000, 1.0, 2.0)
        self.assertEqual(bytes(first.get_msgbuf()), bytes(second.get_msgbuf()))
        self.assertEqual(
            json.loads(bytes(first.get_msgbuf()).decode("ascii")),
            {"kind": "HIL_SENSOR", "arguments": [4_000, 1.0, 2.0]},
        )

    def test_direct_cli_entry_can_import_repository_modules(self):
        completed = subprocess.run(
            [sys.executable, "-B", str(probe.REPO_ROOT / "tools" /
                                        "probe_joint_terrain_feedback.py"), "--help"],
            cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--library", completed.stdout)
        self.assertIn("--output", completed.stdout)

    def test_generated_scene_is_hash_verified_and_has_one_metre_support(self):
        config = probe.make_elevated_scene([3.25, -1.5, 9.0])

        self.assertEqual(config["schema"], "wksim.static-scene.v1")
        self.assertEqual(config["coordinate_frame"], "ENU")
        self.assertEqual(config["unit"], "metre")
        self.assertEqual(config["origin_enu_m"], [0.0, 0.0, 0.0])
        self.assertEqual(config["plane"], {"geometry_id": "plane_z0", "z_m": 0.0})
        self.assertEqual(config["box"]["center_enu_m"], [3.25, -1.5, 0.5])
        self.assertEqual(config["box"]["size_m"], [1.0, 1.0, 1.0])
        expected = hashlib.sha256(
            json.dumps(
                {
                    "origin_enu_m": [0.0, 0.0, 0.0],
                    "plane": {"geometry_id": "plane_z0", "z_m": 0.0},
                    "box": config["box"],
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(config["scene_sha256"], expected)
        scene = StaticScene(config)
        self.assertEqual(scene.support_height_enu_m([3.25, -1.5, 9.0]), 1.0)

    def test_initial_sidecar_is_exactly_one_read_only_tick_zero_record(self):
        request = {"version": 1, "epoch": EPOCH, "initial": True}
        row = {
            "version": 1,
            "epoch": EPOCH,
            "tick": 0,
            "state": state(0),
            "initial": True,
            "input": json.dumps(request, separators=(",", ":")),
            "request": request,
        }

        digest = probe.audit_initial_sidecar([row], EPOCH)

        self.assertEqual(len(digest), 64)
        row["request"] = dict(request, initial=False)
        with self.assertRaisesRegex(probe.ProbeError, "sidecar"):
            probe.audit_initial_sidecar([row], EPOCH)

    def test_audit_requires_exact_terrain_trace_and_clock_evidence(self):
        expected = [-1.0] + [0.0] * 14
        evidence = {
            "epoch": EPOCH,
            "trace_rows": {
                "arducopter": trace_rows(expected, 1.0),
                "px4": trace_rows(expected, 1.0),
            },
            "clock_snapshots": clocks(),
            "expected_terrain": expected,
        }

        summary = probe.audit_scenario(evidence)

        self.assertTrue(summary["stacks_identical"])
        self.assertEqual(summary["ticks"], probe.TICKS)
        self.assertEqual(summary["terrain_by_trace"]["arducopter"], [expected] * probe.TICKS)
        self.assertEqual(summary["final_state_sha256"]["px4"], summary["final_state_sha256"]["arducopter"])

        evidence["trace_rows"]["px4"][0]["terrain"][0] = -0.5
        with self.assertRaisesRegex(probe.ProbeError, "terrain"):
            probe.audit_scenario(evidence)

    def test_compare_requires_different_final_states_for_both_stacks(self):
        baseline = probe.audit_scenario({
            "epoch": EPOCH,
            "trace_rows": {
                "arducopter": trace_rows([0.0] * 15, 0.0),
                "px4": trace_rows([0.0] * 15, 0.0),
            },
            "clock_snapshots": clocks(),
            "expected_terrain": [0.0] * 15,
        })
        elevated = probe.audit_scenario({
            "epoch": EPOCH,
            "trace_rows": {
                "arducopter": trace_rows([-1.0] + [0.0] * 14, 1.0),
                "px4": trace_rows([-1.0] + [0.0] * 14, 1.0),
            },
            "clock_snapshots": clocks(),
            "expected_terrain": [-1.0] + [0.0] * 14,
        })

        comparison = probe.compare_scenarios(baseline, elevated)

        self.assertEqual(comparison["differing_indices"]["arducopter"], [0])
        self.assertEqual(comparison["differing_indices"]["px4"], [0])

    def test_output_must_be_a_new_directory(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            library = root / "libwksim_model.so"
            library.write_bytes(b"library")
            output = root / "existing"
            output.mkdir()

            with self.assertRaisesRegex(probe.ProbeError, "new output directory"):
                probe.validate_cli_inputs(library, output, platform="linux")

    def test_library_and_platform_are_validated_before_execution(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            output = root / "evidence"
            with self.assertRaisesRegex(probe.ProbeError, "library"):
                probe.validate_cli_inputs(root / "missing.so", output, platform="linux")
            library = root / "libwksim_model.so"
            library.write_bytes(b"library")
            with self.assertRaisesRegex(probe.ProbeError, "Linux"):
                probe.validate_cli_inputs(library, output, platform="win32")
            self.assertFalse(output.exists())

    def test_failure_cleanup_terminates_and_reaps_every_child(self):
        processes = []
        records = []
        for pid in (101, 202):
            process = Mock()
            process.pid = pid
            process.poll.return_value = None
            process.wait.return_value = 1
            process.returncode = 1
            process.stdin = Mock()
            processes.append(process)
            records.append({"process": process, "pid": pid, "reaped": False})

        probe.retire_children(records, failed=True)

        for record, process in zip(records, processes):
            process.stdin.close.assert_called_once_with()
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once()
            self.assertTrue(record["reaped"])
            self.assertEqual(record["returncode"], 1)


if __name__ == "__main__":
    unittest.main()
