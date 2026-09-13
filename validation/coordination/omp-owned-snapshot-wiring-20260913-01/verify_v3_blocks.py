"""Executable verification of the v3 owned-snapshot wiring blocks (narrow scope).

Extracts the REAL marked blocks from the pinned v3 candidate
(1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373) by marker
text and execs them against fakes.  Scope is exactly the previously missed
checks: early pin/import/source validation, cancellation propagation, boot
change -> zero PID reads, ordinary metadata failure preserving the business
error, default-off zero side effects.  D's lifecycle ordering and the
author's 16 v3 tests are not rerun here.  No FC/model/build.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import textwrap
import types
import unittest

HERE = Path(__file__).resolve().parent
CANDIDATE = (HERE.parent / "claude-owned-snapshot-wiring-20260913-01"
             / "run_joint_flight-owned-snapshot-candidate-v3.py.txt")
EXPECTED_SHA256 = ("1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b09"
                   "39142774373")
HELPER_SHA256 = ("a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b17"
                 "16f8e9e")


def extract_blocks(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("v3 candidate SHA differs; re-pin before conclusions")
    text = path.read_text(encoding="utf-8")
    blocks = {}
    for number in range(1, 11):
        begin = f"# --- owned-snapshot-wiring begin {number} "
        end = f"# --- owned-snapshot-wiring end {number} ---"
        start = text.index(begin)
        stop = text.index(end)
        blocks[number] = text[start:text.index("\n", stop) + 1]
    return blocks


BLOCKS = extract_blocks(CANDIDATE)


def exec_block(number, namespace):
    body = textwrap.indent(BLOCKS[number], "    ", lambda line: bool(line.strip()))
    exec("if True:\n" + body, namespace)


def base_ns(tmp):
    import os
    return {
        "owned_snapshot": True, "MIXED_PROFILE": "xy_velocity_z_position_yaw_v1",
        "timing_probe": True,
        "result": {"children": {}}, "live": tmp, "REPO": tmp,
        "Path": Path, "os": os, "sys": sys, "json": json,
        "__file__": str(CANDIDATE),
        "json_identity": lambda pid: {"pid": pid, "pgid": pid,
                                      "start_ticks": 42},
        "digest": lambda path: hashlib.sha256(
            Path(path).read_bytes()).hexdigest(),
    }


def fake_capture_module(boot="boot-A", fail_with=None, calls=None,
                        capture_boot=None, module_file=None):
    module = types.ModuleType("capture_owned_scheduling")
    if module_file is not None:
        module.__file__ = module_file

    class ProcReader:
        def __init__(self, root):
            pass

        def read_text(self, *parts):
            return boot + "\n"

    class OwnedSchedulingCapture:
        def __init__(self, children, output, *, phase="unspecified",
                     proc_root="/proc"):
            self.output = Path(output)

        def capture(self):
            if calls is not None:
                calls.append("capture")
            if fail_with is not None:
                raise fail_with
            host_boot = capture_boot if capture_boot is not None else boot
            self.output.write_text(json.dumps({"host": {"boot_id": host_boot}}))
            return {"host": {"boot_id": host_boot}}

    module.ProcReader = ProcReader
    module.OwnedSchedulingCapture = OwnedSchedulingCapture
    return module


class V3BlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ns = base_ns(self.tmp)
        exec_block(1, self.ns)  # constants, gates, read_boot_id

    def gate_ok(self):
        """Exec block 2 (gate + early helper import/pin) with pinned digest."""
        self.ns["args"] = types.SimpleNamespace(
            task_profile="xy_velocity_z_position_yaw_v1",
            owned_scheduling_snapshot=True)
        self.ns["digest"] = lambda path: HELPER_SHA256
        helper = sys.modules.get("capture_owned_scheduling")
        if helper is not None:
            helper.__file__ = str(self.tmp / "tools"
                                  / "capture_owned_scheduling.py")
        exec_block(2, self.ns)

    def fresh_meta(self):
        self.ns["result"]["owned_scheduling"] = dict(
            boot_id=None, before=None, after=None)

    # --- gate: early pin/import/source validation -------------------------- #
    def test_gate_parent_only_and_combination_rejection(self):
        validate = self.ns["validate_owned_snapshot_request"]
        validate("xy_velocity_z_position_yaw_v1", True, True, False)
        validate("any", False, False, True)  # off: returns before checks
        with self.assertRaisesRegex(ValueError, "MIXED"):
            validate("other_profile", True, True, False)
        with self.assertRaisesRegex(ValueError, "parent timing probe"):
            validate("xy_velocity_z_position_yaw_v1", True, False, False)
        with self.assertRaisesRegex(ValueError, "plain bool"):
            validate("xy_velocity_z_position_yaw_v1", 1, True, False)
        with self.assertRaisesRegex(ValueError, "stands alone"):
            validate("xy_velocity_z_position_yaw_v1", True, True, True)
        for name in ("rate_spin_cpu_timing", "pause_probe", "scene_lease_loss",
                     "early_work_timing"):
            self.assertIn(name, self.ns["OWNED_SNAPSHOT_CONFLICTS"])

    def test_missing_or_unpinned_helper_fails_before_any_child(self):
        self.ns["args"] = types.SimpleNamespace(
            task_profile="xy_velocity_z_position_yaw_v1",
            owned_scheduling_snapshot=True)
        self.ns["digest"] = lambda path: "0" * 64
        with self.assertRaisesRegex(ValueError, "differs from the reviewed pin"):
            exec_block(2, self.ns)          # wrong helper SHA: no import needed
        sys.modules.pop("capture_owned_scheduling", None)
        self.ns["digest"] = lambda path: HELPER_SHA256

        class Blocker:
            def find_module(self, name, path=None):
                if name == "capture_owned_scheduling":
                    raise ImportError("blocked for test")
                return None

        sys.meta_path.insert(0, Blocker())
        try:
            with self.assertRaises(ImportError):
                exec_block(2, self.ns)
        finally:
            sys.meta_path.pop(0)
        text = CANDIDATE.read_text(encoding="utf-8")
        self.assertLess(text.index("owned-snapshot-wiring begin 2"),
                        text.index("subprocess.Popen"))

    # --- cancellation propagation ------------------------------------------ #
    def test_cancellation_propagates_ordinary_error_recorded(self):
        calls = []
        sys.modules["capture_owned_scheduling"] = fake_capture_module(
            fail_with=RuntimeError("ordinary"), calls=calls)
        self.gate_ok()
        self.fresh_meta()
        exec_block(5, self.ns)
        self.assertIn("RuntimeError",
                      self.ns["result"]["owned_scheduling"]["before_error"])
        self.assertIsNone(self.ns["result"]["owned_scheduling"].get("before"))
        sys.modules["capture_owned_scheduling"] = fake_capture_module(
            fail_with=KeyboardInterrupt(), calls=calls)
        self.ns["OwnedSchedulingCapture"] = sys.modules[
            "capture_owned_scheduling"].OwnedSchedulingCapture
        self.fresh_meta()
        with self.assertRaises(KeyboardInterrupt):
            exec_block(5, self.ns)

    # --- boot change: zero PID reads ---------------------------------------- #
    def test_boot_change_after_phase_runs_zero_capture(self):
        calls = []
        sys.modules["capture_owned_scheduling"] = fake_capture_module(
            boot="boot-B", calls=calls)
        self.gate_ok()
        self.fresh_meta()
        exec_block(5, self.ns)              # before: pins boot-B, one capture
        self.assertEqual(calls, ["capture"])
        meta = self.ns["result"]["owned_scheduling"]
        self.assertEqual(meta["boot_id"], "boot-B")
        self.assertTrue(meta["before_validated"])
        # after: current boot differs -> refused before any capture
        sys.modules["capture_owned_scheduling"] = fake_capture_module(
            boot="boot-A", calls=calls)
        self.ns["owned_snapshot_after_once"]()
        self.assertEqual(calls, ["capture"])      # unchanged: zero PID reads
        self.assertIn("boot changed", meta["after_error"])
        self.assertIsNone(meta["after"])
        # capture host boot differing from the pinned boot: hard error
        sys.modules["capture_owned_scheduling"] = fake_capture_module(
            boot="boot-A", capture_boot="boot-C")
        self.gate_ok()
        self.fresh_meta()
        exec_block(5, self.ns)
        self.assertIn("host boot differs",
                      self.ns["result"]["owned_scheduling"]["before_error"])
        self.assertNotIn("before_validated",
                         self.ns["result"]["owned_scheduling"])

    def test_after_runs_once(self):
        calls = []
        sys.modules["capture_owned_scheduling"] = fake_capture_module(
            calls=calls)
        self.gate_ok()
        self.fresh_meta()
        exec_block(5, self.ns)
        self.ns["owned_snapshot_after_once"]()
        self.ns["owned_snapshot_after_once"]()
        self.assertEqual(calls, ["capture", "capture"])  # before+after once
        self.assertTrue(self.ns["result"]["owned_scheduling"]["after_attempted"])

    # --- metadata failure never masks the business error --------------------- #
    def test_metadata_failure_preserves_business_exception(self):
        (self.tmp / "owned-scheduling-before.json").write_text("{}")
        self.fresh_meta()
        self.ns["result"]["status"] = "failed"
        self.ns["result"]["source_sha256"] = {}
        self.ns["digest"] = lambda path: (_ for _ in ()).throw(
            OSError("digest blown"))
        business = RuntimeError("business-in-flight")
        try:
            try:
                raise business
            finally:
                exec_block(7, self.ns)
        except RuntimeError as error:
            self.assertIs(error, business)
        meta = self.ns["result"]["owned_scheduling"]
        self.assertIn("digest blown", meta["metadata_error"])
        self.assertNotIn("before", meta.get("refreshed", {}))
        self.assertEqual(self.ns["result"]["status"], "failed")

    # --- default off: zero import / zero side effect -------------------------- #
    def test_default_off_no_import_no_proc_no_record(self):
        sys.modules.pop("capture_owned_scheduling", None)
        ns = base_ns(self.tmp)
        exec_block(1, ns)
        ns["owned_snapshot"] = False
        ns["args"] = types.SimpleNamespace(
            task_profile="xy_velocity_z_position_yaw_v1")
        ns["digest"] = lambda path: HELPER_SHA256
        for number in (2, 5, 7):
            exec_block(number, ns)
        self.assertNotIn("capture_owned_scheduling", sys.modules)
        self.assertNotIn("owned_scheduling", ns["result"])


if __name__ == "__main__":
    unittest.main()
