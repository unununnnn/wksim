"""Pure offline tests for the G6 budget skeleton gate (#10/#59)."""

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import generate_g6_budget_manifest as gen
import validate_g6_budget_manifest as val

RHS_PRESENT = (ROOT / gen.RHS_ARTIFACT).is_file()


@unittest.skipUnless(RHS_PRESENT, "pinned RHS artifact absent")
class GeneratorTests(unittest.TestCase):
    def test_generates_exactly_56_deterministic_blocked_rows(self):
        first = gen.serialize(gen.generate())
        second = gen.serialize(gen.generate())
        self.assertEqual(first, second)
        manifest = json.loads(first.decode("utf-8"))
        self.assertEqual(manifest["slot_count"], 56)
        self.assertEqual(len(manifest["rows"]), 56)
        self.assertIs(manifest["acceptance"], False)
        for row in manifest["rows"]:
            self.assertIsNone(row["abs_budget"])
            self.assertIsNone(row["rel_budget"])
            self.assertIsNone(row["rms_budget"])
            self.assertIsNone(row["approval"])
            self.assertIsNone(row["contract_sha256"])
        statuses = [row["status"] for row in manifest["rows"]]
        self.assertEqual(sum(1 for s in statuses if s == "pending_owner_decision"), 3)
        self.assertEqual(sum(1 for s in statuses if s == "blocked"), 53)
        self.assertNotIn("approved", statuses)
        by_observable = {row["observable"]: row["status"] for row in manifest["rows"]}
        self.assertEqual(by_observable["vehicle_time"], "pending_owner_decision")
        self.assertEqual(by_observable["sensor_time"], "pending_owner_decision")
        self.assertEqual(by_observable["gps_time"], "pending_owner_decision")

    def test_units_come_only_from_pinned_conformance(self):
        manifest = gen.generate()
        by_slot = {row["slot"]: row for row in manifest["rows"]}
        self.assertEqual(by_slot["Vehicle60[3]"]["unit"], "m/s")
        self.assertEqual(by_slot["Vehicle60[2]"]["unit"], "s")
        for row in manifest["rows"]:
            self.assertIsNone(row["frame"])
            self.assertIsNone(row["datum"])
            self.assertEqual(row["sample_phase"], "major_root_output")

    def test_input_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing or linked"):
                gen.generate(root=directory)

    def test_pinned_json_hash_and_parse_use_one_bytes_snapshot(self):
        target = ROOT / gen.RHS_ARTIFACT
        original = Path.read_bytes
        calls = []

        def counted(path):
            if path == target:
                calls.append(path)
            return original(path)

        with unittest.mock.patch.object(Path, "read_bytes", counted):
            gen._load_pinned(ROOT, gen.RHS_ARTIFACT, gen.RHS_SHA256)
        self.assertEqual(calls, [target])

    def test_malformed_nested_source_mapping_fails_closed(self):
        rhs = gen._load_pinned(ROOT, gen.RHS_ARTIFACT, gen.RHS_SHA256)
        source = gen._load_pinned(ROOT, gen.SLOT_MANIFEST, gen.SLOT_MANIFEST_SHA256)
        conformance = gen._load_pinned(ROOT, gen.CONFORMANCE, gen.CONFORMANCE_SHA256)
        source["slots"][0]["source_mapping"]["historical_r1_cpp"] = []
        with unittest.mock.patch.object(gen, "_load_pinned",
                                        side_effect=[rhs, source, conformance]):
            with self.assertRaisesRegex(ValueError, "source_mapping"):
                gen.generate()

    def test_duplicate_conformance_observable_fails_closed(self):
        rhs = gen._load_pinned(ROOT, gen.RHS_ARTIFACT, gen.RHS_SHA256)
        source = gen._load_pinned(ROOT, gen.SLOT_MANIFEST, gen.SLOT_MANIFEST_SHA256)
        conformance = gen._load_pinned(ROOT, gen.CONFORMANCE, gen.CONFORMANCE_SHA256)
        conformance["observables"].append(dict(conformance["observables"][0]))
        with unittest.mock.patch.object(gen, "_load_pinned",
                                        side_effect=[rhs, source, conformance]):
            with self.assertRaisesRegex(ValueError, "duplicated"):
                gen.generate()


@unittest.skipUnless(RHS_PRESENT, "pinned RHS artifact absent")
class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "manifest.json"
        self.manifest = gen.generate()
        self.path.write_bytes(gen.serialize(self.manifest))

    def rewrite(self, manifest):
        self.path.write_bytes(json.dumps(manifest).encode("utf-8"))

    def test_fresh_skeleton_validates(self):
        report = val.validate(self.path)
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["status"], "valid_structure_blocked_budgets")
        self.assertIs(report["acceptance"], False)

    def test_schema_pin_matches_final_schema_bytes(self):
        self.assertEqual(hashlib.sha256(val.SCHEMA.read_bytes()).hexdigest(),
                         val.SCHEMA_SHA256)

    def test_budget_smuggling_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"][0]["abs_budget"] = 0.5
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("claim fields" in v for v in report["violations"]))
        self.assertEqual(report["status"], "fail-closed")

    def test_blocked_claim_and_non_time_pending_status_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"][0]["approval"] = "self-declared"
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("claim fields" in v for v in report["violations"]))

        manifest = json.loads(json.dumps(self.manifest))
        row = next(row for row in manifest["rows"]
                   if row["observable"] not in gen.TIME_OBSERVABLES)
        row["status"] = "pending_owner_decision"
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("reserved for time semantics" in v for v in report["violations"]))

        manifest = json.loads(json.dumps(self.manifest))
        row = next(row for row in manifest["rows"]
                   if row["observable"] in gen.TIME_OBSERVABLES)
        row["status"] = "blocked"
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("require owner decision" in v for v in report["violations"]))

    def test_non_blocked_without_audit_chain_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"][0]["status"] = "identity_check"
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("schema" in v or "identity_check" in v
                            for v in report["violations"]))

    def test_identity_check_pseudo_approval_is_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        row = manifest["rows"][0]
        row.update({
            "status": "identity_check",
            "metric": "rmse",
            "derivation": "self-declared",
            "domain": "self-declared",
            "approval": "self-approved",
            "contract_sha256": "0" * 64,
        })
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertEqual(report["status"], "fail-closed")
        self.assertTrue(any("schema" in v or "identity_check" in v
                            for v in report["violations"]))

    def test_unknown_status_rejected_by_schema(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"][0]["status"] = "approved"
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("schema" in v for v in report["violations"]))

    def test_slot_add_remove_reorder_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"].append(dict(manifest["rows"][0]))
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("schema" in v for v in report["violations"]))

        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"] = manifest["rows"][:-1]
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("schema" in v for v in report["violations"]))

        manifest = json.loads(json.dumps(self.manifest))
        rows = manifest["rows"]
        rows[0], rows[1] = rows[1], rows[0]
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("order or identity" in v for v in report["violations"]))

    def test_input_pin_drift_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["inputs"]["numerical_conformance"]["sha256"] = "0" * 64
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("schema" in v or "pins differ" in v
                            for v in report["violations"]))

        with tempfile.TemporaryDirectory() as directory:
            fake_root = Path(directory)
            for pin in val.PINNED_INPUTS.values():
                destination = fake_root / pin["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / pin["path"]).read_bytes())
            drifted = fake_root / gen.CONFORMANCE
            drifted.write_bytes(drifted.read_bytes() + b"\n")
            self.rewrite(self.manifest)
            with unittest.mock.patch.object(val, "ROOT", fake_root):
                report = val.validate(self.path)
        self.assertTrue(any("drifted" in v for v in report["violations"]))

    def test_malformed_non_object_pinned_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_root = Path(directory)
            for pin in val.PINNED_INPUTS.values():
                destination = fake_root / pin["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / pin["path"]).read_bytes())
            for name in ("rhs_references", "source_to_slot_manifest",
                         "numerical_conformance"):
                destination = fake_root / val.PINNED_INPUTS[name]["path"]
                destination.write_bytes(b"[]")
                with self.subTest(name=name), unittest.mock.patch.object(val, "ROOT", fake_root):
                    report = val.validate(self.path)
                self.assertEqual(report["status"], "fail-closed")
                self.assertTrue(any("pinned provenance structure" in v
                                    or name in v for v in report["violations"]))
                destination.write_bytes((ROOT / val.PINNED_INPUTS[name]["path"]).read_bytes())

    def test_input_path_substitution_and_row_identity_drift_rejected(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["inputs"]["rhs_references"]["path"] = gen.SLOT_MANIFEST
        manifest["inputs"]["rhs_references"]["sha256"] = gen.SLOT_MANIFEST_SHA256
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("schema" in v or "pins differ" in v
                            for v in report["violations"]))

        for field, value in (("array", "GPS30"), ("index", 999),
                             ("outport", "HILGPS30d"), ("line_ranges", [[1, 1]])):
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(self.manifest))
                manifest["rows"][0]["source_mapping"][field] = value
                self.rewrite(manifest)
                report = val.validate(self.path)
                self.assertTrue(any("identity differs" in v for v in report["violations"]))

    def test_pinned_metadata_and_strict_json_are_enforced(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"][0]["unit"] = "invented-unit"
        self.rewrite(manifest)
        report = val.validate(self.path)
        self.assertTrue(any("metadata differs" in v for v in report["violations"]))

        raw = gen.serialize(self.manifest).decode("utf-8")
        self.path.write_text(raw.replace('"schema_version": 1',
                                         '"schema_version": 1, "schema_version": 1', 1),
                             encoding="utf-8")
        report = val.validate(self.path)
        self.assertTrue(any("duplicate JSON key" in v for v in report["violations"]))

    def test_missing_jsonschema_fails_closed(self):
        import builtins
        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        with unittest.mock.patch.object(builtins, "__import__", blocked):
            sys.modules.pop("jsonschema", None)
            report = val.validate(self.path)
        self.assertTrue(any("jsonschema" in v for v in report["violations"]))

    def test_jsonschema_runtime_error_fails_closed(self):
        import builtins
        real_import = builtins.__import__

        def broken(name, *args, **kwargs):
            if name == "jsonschema":
                raise RuntimeError("dependency initialization failed")
            return real_import(name, *args, **kwargs)

        with unittest.mock.patch.object(builtins, "__import__", broken):
            sys.modules.pop("jsonschema", None)
            report = val.validate(self.path)
        self.assertEqual(report["status"], "fail-closed")
        self.assertTrue(any("jsonschema" in v for v in report["violations"]))

    def test_pinned_input_permission_error_fails_closed(self):
        original = Path.read_bytes
        target = val.ROOT / gen.RHS_ARTIFACT

        def denied(path):
            if path == target:
                raise PermissionError("pinned input denied")
            return original(path)

        with unittest.mock.patch.object(Path, "read_bytes", denied):
            report = val.validate(self.path)
        self.assertEqual(report["status"], "fail-closed")
        self.assertTrue(any("rhs_references" in v for v in report["violations"]))

    def test_schema_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            drifted = Path(directory) / "schema.json"
            drifted.write_text('{"type":"object"}', encoding="utf-8")
            with unittest.mock.patch.object(val, "SCHEMA", drifted):
                report = val.validate(self.path)
        self.assertEqual(report["status"], "fail-closed")
        self.assertTrue(any("schema" in v and "drift" in v
                            for v in report["violations"]))

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, "-B",
                             str(ROOT / "tools/validate_g6_budget_manifest.py"),
                             str(self.path)], capture_output=True, timeout=60)
        self.assertEqual(ok.returncode, 3, ok.stderr.decode())
        self.assertEqual(json.loads(ok.stdout.decode("utf-8"))["acceptance"], False)
        manifest = json.loads(json.dumps(self.manifest))
        manifest["rows"][0]["abs_budget"] = 1.0
        bad_path = Path(self.dir.name) / "bad.json"
        bad_path.write_bytes(json.dumps(manifest).encode("utf-8"))
        bad = subprocess.run([sys.executable, "-B",
                              str(ROOT / "tools/validate_g6_budget_manifest.py"),
                              str(bad_path)], capture_output=True, timeout=60)
        self.assertEqual(bad.returncode, 2)

    def test_generator_cli_is_deterministic_and_writes_nothing_by_default(self):
        first = subprocess.run([sys.executable, "-B",
                                str(ROOT / "tools/generate_g6_budget_manifest.py")],
                               capture_output=True, timeout=60)
        second = subprocess.run([sys.executable, "-B",
                                 str(ROOT / "tools/generate_g6_budget_manifest.py")],
                                capture_output=True, timeout=60)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stdout, gen.serialize(gen.generate()))

    def test_generator_output_is_create_only_and_requires_canonical_parent(self):
        command = [sys.executable, "-B",
                   str(ROOT / "tools/generate_g6_budget_manifest.py")]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            existing = base / "existing.json"
            existing.write_bytes(b"keep")
            result = subprocess.run(command + ["--output", str(existing)],
                                    capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(existing.read_bytes(), b"keep")

            created = base / "created.json"
            result = subprocess.run(command + ["--output", str(created)],
                                    capture_output=True, timeout=60)
            if os.name == "nt":
                self.assertEqual(result.returncode, 2)
                self.assertFalse(created.exists())
                return
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(created.read_bytes(), result.stdout)

            real_parent = base / "real-parent"
            real_parent.mkdir()
            alias_parent = base / "alias-parent"
            try:
                alias_parent.symlink_to(real_parent, target_is_directory=True)
            except OSError:
                alias_parent = None
            if alias_parent is not None:
                aliased = alias_parent / "should-not-exist.json"
                result = subprocess.run(command + ["--output", str(aliased)],
                                        capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 2)
                self.assertFalse((real_parent / aliased.name).exists())

            target = base / "target.json"
            target.write_bytes(b"keep-target")
            link = base / "output-link.json"
            try:
                link.symlink_to(target)
            except OSError:
                link = None
            if link is not None:
                result = subprocess.run(command + ["--output", str(link)],
                                        capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(target.read_bytes(), b"keep-target")

    @unittest.skipUnless(os.name != "nt", "dirfd publication is POSIX-only")
    def test_output_parent_swap_cannot_publish_through_replaced_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            parent = base / "publish"
            parent.mkdir()
            outside = base / "outside"
            outside.mkdir()
            target = parent / "manifest.json"
            real_open = gen.os.open
            swapped = False

            def swapping_open(path, flags, *args, **kwargs):
                nonlocal swapped
                fd = real_open(path, flags, *args, **kwargs)
                if (not swapped and isinstance(path, str)
                        and Path(path) == parent
                        and flags & os.O_DIRECTORY):
                    swapped = True
                    moved = base / "publish-real"
                    parent.rename(moved)
                    parent.symlink_to(outside, target_is_directory=True)
                return fd

            with unittest.mock.patch.object(gen.os, "open", swapping_open):
                with self.assertRaises((ValueError, FileNotFoundError, OSError)):
                    gen._write_output(target, b"race")
            self.assertFalse((outside / target.name).exists())
            self.assertFalse((base / "publish-real" / target.name).exists())


if __name__ == "__main__":
    unittest.main()
