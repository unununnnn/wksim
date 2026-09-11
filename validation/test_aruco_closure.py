#!/usr/bin/env python3
"""Focused regression tests for the JSON-only ArUco closure audit."""

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from tools.audit_aruco_closure import audit, write_report


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "validation/coordination/aruco-closure-manifest.json"


class TestArucoClosure(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def _audit_copy(self, manifest):
        with tempfile.TemporaryDirectory(prefix="aruco-closure-test-") as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            return audit(path)

    def _audit_mutated_report(self, manifest, stack, report_name, mutate):
        with tempfile.TemporaryDirectory(prefix="aruco-closure-report-", dir=ROOT) as directory:
            source = ROOT / manifest["runs"][stack]["reports"][report_name]["path"]
            report = json.loads(source.read_text(encoding="utf-8"))
            mutate(report)
            target = Path(directory) / f"{report_name}.json"
            target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            manifest["runs"][stack]["reports"][report_name] = {
                "path": target.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
            return self._audit_copy(manifest)

    def _audit_mutated_publisher(self, manifest, stack, mutate):
        with tempfile.TemporaryDirectory(prefix="aruco-closure-publisher-", dir=ROOT) as directory:
            source = ROOT / manifest["runs"][stack]["reports"]["publishers"]["path"]
            report = json.loads(source.read_text(encoding="utf-8"))
            mutate(report)
            target = Path(directory) / "publishers.json"
            target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            manifest["runs"][stack]["reports"]["publishers"] = {
                "path": target.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
            return self._audit_copy(manifest)

    def test_retained_ap15_and_px4_run21_pass(self):
        result = audit(MANIFEST)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["runs"]["arducopter"]["run_id"], "aruco-track-aa766cf3f8")
        self.assertEqual(result["runs"]["px4"]["run_id"], "aruco-track-405ebd92a0")
        self.assertEqual(result["reports"]["arducopter"]["raw"], "pending")
        self.assertEqual(result["reports"]["px4"]["publishers"], "snapshots_verified_and_bound")
        binding = result["identity_bindings"]["px4"]
        self.assertEqual(binding["direct"]["raw"]["epoch"], "59e79980b4f849c082559e73108e63de")
        self.assertEqual(binding["transitive"]["native_raw_sha256"], "6ffc300a534c1d675d25ed318f42f4f4de978a04a991275da56dc1043bfddb9f")

    def test_identity_mismatch_fails_closed(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["runs"]["px4"]["run_id"] = "aruco-track-aa766cf3f8"
        result = self._audit_copy(manifest)
        self.assertEqual(result["status"], "failed")
        self.assertIn("run_id", result["failures"][0]["message"])

    def test_epoch_must_be_lower_hex32(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["runs"]["px4"]["epoch"] = manifest["runs"]["px4"]["epoch"].upper()
        result = self._audit_copy(manifest)
        self.assertEqual(result["status"], "failed")
        self.assertIn("lowercase hex32", result["failures"][0]["message"])

    def test_absolute_and_parent_paths_fail_closed(self):
        for bad_path in (
            str(ROOT / "validation/coordination/aruco-15-ap-physical.json"),
            "validation/coordination/../coordination/aruco-15-ap-physical.json",
        ):
            manifest = copy.deepcopy(self.manifest)
            manifest["runs"]["arducopter"]["reports"]["physical"]["path"] = bad_path
            result = self._audit_copy(manifest)
            self.assertEqual(result["status"], "failed")
            self.assertRegex(result["failures"][0]["message"], r"relative path|must not contain")

    def test_symlink_path_component_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="aruco-closure-link-", dir=ROOT) as directory:
            link = Path(directory) / "validation-link"
            try:
                os.symlink(ROOT / "validation", link, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink unavailable: {error}")
            manifest = copy.deepcopy(self.manifest)
            manifest["runs"]["arducopter"]["reports"]["physical"]["path"] = (
                link.relative_to(ROOT) / "coordination/aruco-15-ap-physical.json"
            ).as_posix()
            result = self._audit_copy(manifest)
        self.assertEqual(result["status"], "failed")
        self.assertIn("symlink", result["failures"][0]["message"])

    def test_pinned_report_sha_mismatch_fails_closed(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["runs"]["arducopter"]["reports"]["physical"]["sha256"] = "0" * 64
        result = self._audit_copy(manifest)
        self.assertEqual(result["status"], "failed")
        self.assertIn("SHA-256", result["failures"][0]["message"])

    def test_open_raw_loss_hold_gate_fails_closed(self):
        manifest = copy.deepcopy(self.manifest)
        with tempfile.TemporaryDirectory(prefix="aruco-closure-gate-", dir=ROOT) as directory:
            raw_path = Path(directory) / "raw.json"
            raw = json.loads((ROOT / manifest["runs"]["px4"]["reports"]["raw"]["path"]).read_text(encoding="utf-8"))
            raw["loss_hold"]["gate"] = "open"
            raw_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            manifest["runs"]["px4"]["reports"]["raw"] = {
                "path": raw_path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "raw_sha256": manifest["runs"]["px4"]["reports"]["raw"]["raw_sha256"],
            }
            result = self._audit_copy(manifest)
        self.assertEqual(result["status"], "failed")
        self.assertIn("gate", result["failures"][0]["message"])

    def test_native_raw_sha_binding_fails_closed(self):
        manifest = copy.deepcopy(self.manifest)
        result = self._audit_mutated_report(
            manifest, "px4", "native_holds", lambda report: report.__setitem__("raw_sha256", "0" * 64)
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("raw_sha256", result["failures"][0]["message"])

    def test_native_stack_binding_fails_closed(self):
        manifest = copy.deepcopy(self.manifest)
        result = self._audit_mutated_report(
            manifest, "px4", "native_holds", lambda report: report.__setitem__("stack", "arducopter")
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("native_holds identity", result["failures"][0]["message"])

    def test_native_epoch_binding_fails_closed(self):
        manifest = copy.deepcopy(self.manifest)
        result = self._audit_mutated_report(
            manifest, "px4", "native_timestamps", lambda report: report.__setitem__("epoch", "0" * 32)
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("native_timestamps identity", result["failures"][0]["message"])

    def test_publisher_raw_capture_cannot_cross_stack(self):
        manifest = copy.deepcopy(self.manifest)
        result = self._audit_mutated_publisher(
            manifest,
            "px4",
            lambda report: report["results_by_stack"]["px4"]["raw_capture"].__setitem__(
                "path", report["results_by_stack"]["arducopter"]["raw_capture"]["path"]
            ),
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("canonical px4 raw capture", result["failures"][0]["message"])

    def test_publisher_raw_capture_sha_must_match_evidence(self):
        manifest = copy.deepcopy(self.manifest)

        def mutate(report):
            raw_path = report["results_by_stack"]["px4"]["raw_capture"]["path"]
            normalized = raw_path.replace("\\", "/")
            marker = "/run/"
            raw_key = "run/" + normalized[normalized.index(marker) + len(marker):]
            matching_keys = [
                key for key in report["evidence_sha256"]
                if key.replace("\\", "/").strip("/").lower() == raw_key.lower()
            ]
            self.assertEqual(len(matching_keys), 1)
            report["evidence_sha256"][matching_keys[0]] = "0" * 64

        result = self._audit_mutated_publisher(manifest, "px4", mutate)
        self.assertEqual(result["status"], "failed")
        self.assertIn("evidence SHA", result["failures"][0]["message"])

    def test_output_is_exclusive_and_disallows_nan(self):
        with tempfile.TemporaryDirectory(prefix="aruco-closure-output-") as directory:
            output = Path(directory) / "audit.json"
            write_report({"status": "pass"}, output)
            with self.assertRaises(FileExistsError):
                write_report({"status": "pass"}, output)
            with self.assertRaises(ValueError):
                write_report({"value": math.nan}, Path(directory) / "nan.json")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "pass")


if __name__ == "__main__":
    unittest.main()
