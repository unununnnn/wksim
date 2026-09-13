"""Pure offline unit tests for the #29 terrain evidence fail-closed audit."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import audit_29_terrain_evidence as audit_mod

MANIFEST_PATH = ROOT / "docs/plan/29-terrain-evidence-manifest.json"


class TestRealRepositoryTerrainEvidence(unittest.TestCase):
    """Verify that the actual repository evidence passes the audit in partial_open state."""

    def test_real_repo_audit_passes_partial_open(self):
        report = audit_mod.audit(MANIFEST_PATH, root=ROOT)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["status"], "partial_open")
        self.assertIs(report["acceptance"], False)
        self.assertEqual(report["blocking_issue"], 9)
        self.assertTrue(report["scene_identities"]["distinct"])
        self.assertEqual(
            report["scene_identities"]["visual_static_scene"],
            audit_mod.SCENE_VISUAL_STATIC,
        )
        self.assertEqual(
            report["scene_identities"]["real_terrain_scene"],
            audit_mod.SCENE_REAL_TERRAIN,
        )

        counts = report["verified_counts"]
        self.assertEqual(counts["pins"], 24)
        self.assertEqual(counts["truth_trace_files_checked"], 6)
        self.assertEqual(counts["truth_trace_rows_checked"], 300)
        self.assertEqual(counts["state_dimension"], 120)
        self.assertEqual(counts["terrain_dimension"], 15)
        self.assertEqual(counts["workers_reaped"], 6)
        self.assertEqual(report["upstream_declared"]["static_assertions_80"], 85)
        self.assertEqual(report["upstream_declared"]["live_assertions_81"], 30895)
        self.assertNotIn("static_assertions", counts)
        self.assertNotIn("live_assertions", counts)

        boundaries = report["unproven_boundaries"]
        self.assertIn("missing_real_ue_physics_colocation", boundaries)
        self.assertIn("missing_fc_closed_loop", boundaries)
        self.assertIn("missing_slope_contact_force_dynamics", boundaries)

    def test_cli_execution_real_manifest(self):
        cmd = [sys.executable, "-B", str(ROOT / "tools/audit_29_terrain_evidence.py"), "--manifest", str(MANIFEST_PATH)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, f"CLI stderr: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "partial_open")
        self.assertIs(data["acceptance"], False)
        self.assertEqual(data["violations"], [])

    def test_cli_execution_missing_manifest(self):
        cmd = [sys.executable, "-B", str(ROOT / "tools/audit_29_terrain_evidence.py"), "--manifest", "missing-manifest.json"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 2)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "audit_failed")
        self.assertTrue(len(data["violations"]) > 0)


class TestAuditSecurityAndManifestRules(unittest.TestCase):
    """Test path security, strict JSON rules, and invariant enforcement."""

    def _audit_tampered(self, manifest):
        """Audit a tampered manifest placed inside a transient in-root directory."""
        with tempfile.TemporaryDirectory(dir=ROOT) as work:
            path = Path(work) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return audit_mod.audit(path, root=ROOT)

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError) as ctx:
            audit_mod.load_strict_json('{"a": 1, "a": 2}')
        self.assertIn("duplicate key", str(ctx.exception))

    def test_strict_json_rejects_nan_and_infinity(self):
        for bad in ('{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}'):
            with self.assertRaises(ValueError):
                audit_mod.load_strict_json(bad)

    def test_manifest_outside_root_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "manifest.json"
            path.write_text(MANIFEST_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            report = audit_mod.audit(path, root=ROOT)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("inside the audit root" in v for v in report["violations"]))

    def test_verify_secure_path_rejects_escape_and_absolute(self):
        with self.assertRaises(ValueError):
            audit_mod.verify_secure_path(ROOT, "../outside")
        with self.assertRaises(ValueError):
            audit_mod.verify_secure_path(ROOT, "/abs/path")

    def test_verify_secure_path_rejects_symlinks(self):
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError) as ctx:
                audit_mod.verify_secure_path(ROOT, "docs/plan/29-terrain-evidence-manifest.json")
            self.assertIn("symlink/reparse", str(ctx.exception))

    def test_forged_status_pass_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        manifest["status"] = "pass"
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("manifest status must be 'partial_open'" in v for v in report["violations"]))

    def test_forged_acceptance_true_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        manifest["acceptance"] = True
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("manifest acceptance must be false" in v for v in report["violations"]))

    def test_forged_blocking_issue_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        manifest["blocking_issue"] = 10
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("blocking_issue must be 9" in v for v in report["violations"]))

    def test_missing_unproven_boundaries_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        del manifest["unproven_boundaries"]["missing_real_ue_physics_colocation"]
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("missing required unproven boundary" in v for v in report["violations"]))

    def test_swapped_scene_identities_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        manifest["scene_identities"]["visual_static_scene"]["scene_sha256"] = audit_mod.SCENE_REAL_TERRAIN
        manifest["scene_identities"]["real_terrain_scene"]["scene_sha256"] = audit_mod.SCENE_VISUAL_STATIC
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("visual_static_scene hash mismatch" in v for v in report["violations"]))

    def test_identical_scene_conflation_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        manifest["scene_identities"]["visual_static_scene"]["scene_sha256"] = audit_mod.SCENE_REAL_TERRAIN
        manifest["scene_identities"]["real_terrain_scene"]["scene_sha256"] = audit_mod.SCENE_REAL_TERRAIN
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(
            any("must not be identical" in v or "hash mismatch" in v for v in report["violations"])
        )

    def test_deleted_pin_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        manifest["evidence_pins"]["static_contact_80"]["pins"].pop(0)
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("pins in manifest" in v or "missing pin" in v for v in report["violations"]))

    def test_tampered_pin_hash_rejected(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        manifest["evidence_pins"]["static_contact_80"]["pins"][0]["sha256"] = "0" * 64
        report = self._audit_tampered(manifest)
        self.assertEqual(report["status"], "audit_failed")
        self.assertTrue(any("SHA-256 mismatch" in v for v in report["violations"]))

    def test_upstream_declared_never_masquerades_as_verified(self):
        report = audit_mod.audit(MANIFEST_PATH, root=ROOT)
        self.assertIn("upstream_declared", report)
        self.assertNotIn("static_assertions", report["verified_counts"])
        self.assertNotIn("live_assertions", report["verified_counts"])
        self.assertEqual(report["upstream_declared"]["static_assertions_80"], 85)
        self.assertEqual(report["upstream_declared"]["live_assertions_81"], 30895)

    def test_fixed_non_claims_present(self):
        report = audit_mod.audit(MANIFEST_PATH, root=ROOT)
        self.assertEqual(report["non_claims"], [
            "no independent recomputation of upstream #80/#81 assertion logic",
            "result.json status field is self-reported metadata, not independent proof",
            "no real UE physics colocation, no FC closed loop, no slope contact force dynamics",
            "not a pass or closure of #29; acceptance stays false",
        ])


class TestAuditSubsystemChecks(unittest.TestCase):
    """Test detailed failure branches in truth trace, cold reset, and worker reaped checkers."""

    def test_forged_truth_trace_row_count_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        fake_line = json.dumps({
            "step": 0, "epoch": 1, "sim_time": 0.0, "time_usec": 0,
            "state": [0.0] * 120, "terrain": [0.0] * 15
        })
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
            reset_dir.mkdir(parents=True)
            for name in (
                "baseline-arducopter-truth.jsonl",
                "baseline-px4-truth.jsonl",
                "elevated-arducopter-truth.jsonl",
                "elevated-px4-truth.jsonl",
                "elevated_reset-arducopter-truth.jsonl",
                "elevated_reset-px4-truth.jsonl",
            ):
                # 49 rows instead of 50
                (reset_dir / name).write_text((fake_line + "\n") * 49, encoding="utf-8")

            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("expected 50 rows, got 49" in v for v in report["violations"]))

    def test_forged_state_dimension_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        fake_line = json.dumps({
            "step": 0, "epoch": 1, "sim_time": 0.0, "time_usec": 0,
            "state": [0.0] * 119, "terrain": [0.0] * 15
        })
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
            reset_dir.mkdir(parents=True)
            for name in (
                "baseline-arducopter-truth.jsonl",
                "baseline-px4-truth.jsonl",
                "elevated-arducopter-truth.jsonl",
                "elevated-px4-truth.jsonl",
                "elevated_reset-arducopter-truth.jsonl",
                "elevated_reset-px4-truth.jsonl",
            ):
                (reset_dir / name).write_text((fake_line + "\n") * 50, encoding="utf-8")

            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("state length is not 120" in v for v in report["violations"]))

    def test_forged_terrain_dimension_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        fake_line = json.dumps({
            "step": 0, "epoch": 1, "sim_time": 0.0, "time_usec": 0,
            "state": [0.0] * 120, "terrain": [0.0] * 14
        })
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
            reset_dir.mkdir(parents=True)
            for name in (
                "baseline-arducopter-truth.jsonl",
                "baseline-px4-truth.jsonl",
                "elevated-arducopter-truth.jsonl",
                "elevated-px4-truth.jsonl",
                "elevated_reset-arducopter-truth.jsonl",
                "elevated_reset-px4-truth.jsonl",
            ):
                (reset_dir / name).write_text((fake_line + "\n") * 50, encoding="utf-8")

            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("terrain length is not 15" in v for v in report["violations"]))

    def test_forged_cold_reset_same_epoch_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        elevated_line = json.dumps({
            "step": 0, "epoch": 999, "sim_time": 0.0, "time_usec": 0,
            "state": [0.0] * 120, "terrain": [-1.0] + [0.0] * 14
        })
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
            reset_dir.mkdir(parents=True)
            for name in ("baseline-arducopter-truth.jsonl", "baseline-px4-truth.jsonl"):
                base_line = json.dumps({
                    "step": 0, "epoch": 100, "sim_time": 0.0, "time_usec": 0,
                    "state": [0.0] * 120, "terrain": [0.0] * 15
                })
                (reset_dir / name).write_text((base_line + "\n") * 50, encoding="utf-8")

            for name in (
                "elevated-arducopter-truth.jsonl",
                "elevated-px4-truth.jsonl",
                "elevated_reset-arducopter-truth.jsonl",
                "elevated_reset-px4-truth.jsonl",
            ):
                (reset_dir / name).write_text((elevated_line + "\n") * 50, encoding="utf-8")

            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("cold reset epoch must differ from elevated epoch" in v for v in report["violations"]))

    def test_forged_cold_reset_state_divergence_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        elevated_line = json.dumps({
            "step": 0, "epoch": 111, "sim_time": 0.0, "time_usec": 0,
            "state": [0.0] * 120, "terrain": [-1.0] + [0.0] * 14
        })
        drift_line = json.dumps({
            "step": 0, "epoch": 222, "sim_time": 0.0, "time_usec": 0,
            "state": [1.0] + [0.0] * 119, "terrain": [-1.0] + [0.0] * 14
        })
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
            reset_dir.mkdir(parents=True)
            for name in ("baseline-arducopter-truth.jsonl", "baseline-px4-truth.jsonl"):
                base_line = json.dumps({
                    "step": 0, "epoch": 100, "sim_time": 0.0, "time_usec": 0,
                    "state": [0.0] * 120, "terrain": [0.0] * 15
                })
                (reset_dir / name).write_text((base_line + "\n") * 50, encoding="utf-8")

            (reset_dir / "elevated-arducopter-truth.jsonl").write_text((elevated_line + "\n") * 50, encoding="utf-8")
            (reset_dir / "elevated-px4-truth.jsonl").write_text((elevated_line + "\n") * 50, encoding="utf-8")
            (reset_dir / "elevated_reset-arducopter-truth.jsonl").write_text((drift_line + "\n") * 50, encoding="utf-8")
            (reset_dir / "elevated_reset-px4-truth.jsonl").write_text((elevated_line + "\n") * 50, encoding="utf-8")

            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("state drift between elevated and cold reset" in v for v in report["violations"]))

    def test_forged_mixed_epoch_middle_row_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        good = json.dumps({
            "tick": 0, "epoch": "aaaa", "state": [0.0] * 120,
            "terrain": [0.0] * 15
        })
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
            reset_dir.mkdir(parents=True)
            for index, name in enumerate((
                "baseline-arducopter-truth.jsonl",
                "baseline-px4-truth.jsonl",
                "elevated-arducopter-truth.jsonl",
                "elevated-px4-truth.jsonl",
                "elevated_reset-arducopter-truth.jsonl",
                "elevated_reset-px4-truth.jsonl",
            )):
                rows = []
                for tick in range(1, 51):
                    row = json.loads(good)
                    row["tick"] = tick
                    row["epoch"] = f"epoch-{name}"
                    rows.append(json.dumps(row))
                if name == "elevated-px4-truth.jsonl":
                    middle = json.loads(rows[24])
                    middle["epoch"] = "intruder-epoch"
                    rows[24] = json.dumps(middle)
                (reset_dir / name).write_text("\n".join(rows) + "\n", encoding="utf-8")
            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("mixed epochs inside one trace" in v
                                for v in report["violations"]))

    def _write_six_traces(self, td_path, row_mutate=None):
        reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
        reset_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "baseline-arducopter-truth.jsonl", "baseline-px4-truth.jsonl",
            "elevated-arducopter-truth.jsonl", "elevated-px4-truth.jsonl",
            "elevated_reset-arducopter-truth.jsonl", "elevated_reset-px4-truth.jsonl",
        ):
            rows = []
            for tick in range(1, 51):
                epoch = f"epoch-{name.replace('elevated_reset', 'reset')}"
                row = {"tick": tick, "epoch": epoch, "version": 1,
                       "state": [0.0] * 120,
                       "terrain": [0.0] * 15 if "baseline" in name else [-1.0] + [0.0] * 14,
                       "request": {"tick": tick, "epoch": epoch},
                       "input": json.dumps({"tick": tick, "epoch": epoch}),
                       "commands": [0.0] * 16}
                if row_mutate:
                    row = row_mutate(name, tick, row)
                rows.append(json.dumps(row))
            (reset_dir / name).write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_forged_tick_step_and_start_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # wrong start: ticks begin at 0
            self._write_six_traces(td_path, lambda n, t, r: dict(r, tick=t - 1,
                                   request={"tick": t - 1, "epoch": r["epoch"]},
                                   input=json.dumps({"tick": t - 1, "epoch": r["epoch"]})))
            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("1-based row index" in v for v in report["violations"]))

        report = {"violations": [], "verified_counts": {}}
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # wrong step: tick jumps by 2 in the middle
            def skip(name, tick, row):
                if "elevated-arducopter" in name and tick >= 25:
                    tick += 1
                    return dict(row, tick=tick,
                                request={"tick": tick, "epoch": row["epoch"]},
                                input=json.dumps({"tick": tick, "epoch": row["epoch"]}))
                return row
            self._write_six_traces(td_path, skip)
            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("1-based row index" in v for v in report["violations"]))

    def test_forged_request_and_embedded_tick_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            def drift(name, tick, row):
                if "elevated-px4" in name and tick == 10:
                    return dict(row, request={"tick": tick + 1, "epoch": row["epoch"]})
                if "baseline-px4" in name and tick == 10:
                    return dict(row, input=json.dumps({"tick": tick + 1,
                                                       "epoch": row["epoch"]}))
                return row
            self._write_six_traces(td_path, drift)
            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("request tick/epoch disagrees" in v for v in report["violations"]))
            self.assertTrue(any("embedded input tick/epoch disagrees" in v
                                for v in report["violations"]))

    def test_forged_nan_row_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            self._write_six_traces(td_path)
            target = td_path / "validation/lunar-29-terrain-reset-c8f05c6e/baseline-arducopter-truth.jsonl"
            lines = target.read_text(encoding="utf-8").splitlines()
            row = json.loads(lines[5])
            row["state"][0] = float("nan")
            lines[5] = json.dumps(row).replace("NaN", "NaN")
            # json.dumps emits NaN token which strict parsing must refuse
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")
            audit_mod._check_truth_traces_and_cold_reset(td_path, report)
            self.assertTrue(any("failed reading truth trace" in v for v in report["violations"]))

    def test_records_pin_hash_and_size_enforced(self):
        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        pin = next(p for p in manifest["evidence_pins"]["live_contact_81"]["pins"]
                   if p["path"].endswith("records.jsonl"))
        self.assertEqual(pin["size_bytes"], 1594243)
        report = audit_mod.audit(MANIFEST_PATH, root=ROOT)
        self.assertEqual(report["verified_counts"]["pins"], 24)
        pin["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(dir=ROOT) as work:
            path = Path(work) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            bad = audit_mod.audit(path, root=ROOT)
        self.assertEqual(bad["status"], "audit_failed")
        self.assertTrue(any("SHA-256 mismatch" in v for v in bad["violations"]))

        manifest = audit_mod.load_strict_json(MANIFEST_PATH)
        pin = next(p for p in manifest["evidence_pins"]["live_contact_81"]["pins"]
                   if p["path"].endswith("records.jsonl"))
        pin["size_bytes"] += 1
        with tempfile.TemporaryDirectory(dir=ROOT) as work:
            path = Path(work) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            bad = audit_mod.audit(path, root=ROOT)
        self.assertTrue(any("size mismatch" in v for v in bad["violations"]))

    def test_forged_worker_failure_rejected(self):
        report = {"violations": [], "verified_counts": {}}
        result_data = {
            "version": 1,
            "status": "passed",
            "ticks": 50,
            "fixed_step_ns": 1_000_000,
            "elevated_reset_comparison": {
                "epoch_changed": True,
                "reason_code": "cold_reset_elevated_exact_replay",
                "scene_hash_equal": True,
            },
            "library": {"sha256": "fake_lib_sha"},
            "source_sha256": {"Simulator/wksim_core/model.cpp": "fake_wrapper_sha"},
            "probe": "terrain_probe_reset_test",
            "scene_config": {"scene_sha256": audit_mod.SCENE_REAL_TERRAIN},
            "scenarios": {
                "baseline": {
                    "scene_hash": audit_mod.SCENE_REAL_TERRAIN,
                    "children": [
                        {"role": "baseline-arducopter", "pid": 101, "returncode": 0, "reaped": True},
                        {"role": "baseline-px4", "pid": 102, "returncode": 1, "reaped": True},
                    ],
                },
                "elevated": {
                    "scene_hash": audit_mod.SCENE_REAL_TERRAIN,
                    "children": [
                        {"role": "elevated-arducopter", "pid": 103, "returncode": 0, "reaped": True},
                        {"role": "elevated-px4", "pid": 104, "returncode": 0, "reaped": True},
                    ],
                },
                "elevated_reset": {
                    "scene_hash": audit_mod.SCENE_REAL_TERRAIN,
                    "children": [
                        {"role": "elevated_reset-arducopter", "pid": 105, "returncode": 0, "reaped": True},
                        {"role": "elevated_reset-px4", "pid": 106, "returncode": 0, "reaped": True},
                    ],
                },
            },
        }
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            reset_dir = td_path / "validation/lunar-29-terrain-reset-c8f05c6e"
            reset_dir.mkdir(parents=True)
            (reset_dir / "result.json").write_text(json.dumps(result_data), encoding="utf-8")
            (reset_dir / "elevated-scene.json").write_text(
                json.dumps({"version": 1, "origin": [0.0, 0.0, 0.0], "static_obstacles": [{"type": "box", "center": [0.0, 0.0, 0.5]}]}),
                encoding="utf-8",
            )
            (reset_dir / "elevated_reset-scene.json").write_text(
                json.dumps({"version": 1, "origin": [0.0, 0.0, 0.0], "static_obstacles": [{"type": "box", "center": [0.0, 0.0, 0.5]}]}),
                encoding="utf-8",
            )
            (reset_dir / "model-build.json").write_text(
                json.dumps({"library_sha256": "fake_lib_sha", "wrapper_sha256": "fake_wrapper_sha"}),
                encoding="utf-8",
            )
            audit_mod._check_result_json_metadata(td_path, report)
            self.assertTrue(any("returned non-zero code" in v for v in report["violations"]))


if __name__ == "__main__":
    unittest.main()
