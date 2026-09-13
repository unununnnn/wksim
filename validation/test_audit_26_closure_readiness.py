"""Pure offline tests for the #26 closure-readiness audit."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_26_closure_readiness as audit_mod

MANIFEST = ROOT / "docs/plan/26-closure-readiness-manifest.json"
EVIDENCE_FILES = [
    "docs/2026-09-10-generated-e0-lifecycle.md",
    "validation/codegen-e0/short-cycle-codegen-01/codegen-report.json",
    "validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json",
    "validation/codegen-e0/short-cycle-codegen-01/summary.json",
    "validation/codegen-e0-build-short-cycle-01/build-manifest.json",
    "validation/codegen-e0-lifecycle-01/audit.json",
]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture(root):
    """Build a complete, offline-verifiable evidence fixture."""
    for relative in EVIDENCE_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    wrapper = root / "Simulator/wksim_core/model.cpp"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "Simulator/wksim_core/model.cpp", wrapper)

    build_path = root / EVIDENCE_FILES[4]
    build = json.loads(build_path.read_text(encoding="utf-8"))
    generated_dir = root / "work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for basename in ("Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "rtwtypes.h", "ert_main.cpp"):
        shutil.copy2(
            ROOT / "work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw" / basename,
            generated_dir / basename,
        )
    external_dir = root.parent / f"{root.name}-external-inputs"
    external_dir.mkdir(parents=True, exist_ok=True)
    header_root = Path(r"D:\matlab\install date\simulink\include")
    if not header_root.is_dir():
        header_root = Path("/mnt/d/matlab/install date/simulink/include")
    shutil.copy2(header_root / "rtw_continuous.h", external_dir / "rtw_continuous.h")
    shutil.copy2(header_root / "rtw_solver.h", external_dir / "rtw_solver.h")
    for basename, item in build["staged_sources"].items():
        if basename in {"Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "rtwtypes.h"}:
            item["source_path"] = str(generated_dir / basename)
        elif basename == "model.cpp":
            item["source_path"] = str(wrapper)
        else:
            item["source_path"] = str(external_dir / basename)
        source_file = Path(item["source_path"])
        item["sha256"] = _sha(source_file)
        item["size_bytes"] = source_file.stat().st_size

    artifact = root / "artifacts/libwksim_e0.so"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"offline fixture library\n")
    cold_artifact = root / "artifacts/cold/libwksim_e0.so"
    cold_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(artifact, cold_artifact)
    build["output_library"]["sha256"] = _sha(artifact)
    build["output_library"]["size_bytes"] = artifact.stat().st_size
    _write(build_path, build)

    audit_path = root / EVIDENCE_FILES[5]
    lifecycle = json.loads(audit_path.read_text(encoding="utf-8"))
    wrapper_hash = _sha(wrapper)
    lifecycle["library_sha256"] = _sha(artifact)
    lifecycle["cold_library"] = str(cold_artifact)
    lifecycle["source_sha256"]["model.cpp"] = wrapper_hash
    for run in lifecycle["runs"]:
        old_probe = run["command"][run["command"].index("--probe") + 1]
        probe = artifact if run["name"] == "original" else cold_artifact
        run["command"] = [str(probe) if value == old_probe else value for value in run["command"]]
        run["identity"]["argv"] = list(run["command"])
    _write(audit_path, lifecycle)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["library_sha256"] = lifecycle["library_sha256"]
    manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["source_sha256"]["model.cpp"] = wrapper_hash
    for binding in manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["run_bindings"]:
        binding["library_sha256"] = lifecycle["library_sha256"]
        binding["source_sha256"]["model.cpp"] = wrapper_hash
        matching_run = next(run for run in lifecycle["runs"] if run["name"] == binding["name"])
        binding["argv"] = list(matching_run["identity"]["argv"])
    for entry in manifest["acceptance_evidence"].values():
        for pin in entry["pins"]:
            pin["sha256"] = _sha(root / pin["path"])
    raw_paths = []
    for key in lifecycle["raw_sha256"]:
        source = ROOT / "validation/codegen-e0-lifecycle-01" / Path(*key.split("/"))
        destination = root / "validation/codegen-e0-lifecycle-01" / Path(*key.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        raw_paths.append(destination.relative_to(root).as_posix())
    manifest_path = root / "manifest.json"
    _write(manifest_path, manifest)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True, timeout=30)
    tracked = [*EVIDENCE_FILES, "Simulator/wksim_core/model.cpp", "manifest.json", *raw_paths,
               "artifacts/libwksim_e0.so", "artifacts/cold/libwksim_e0.so"]
    subprocess.run(["git", "add", "--", *tracked], cwd=root, check=True, capture_output=True, timeout=30)
    return manifest_path


def _refresh_pin(manifest_path, relative, root):
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in data["acceptance_evidence"].values():
        for pin in entry["pins"]:
            if pin["path"] == relative:
                pin["sha256"] = _sha(root / relative)
    _write(manifest_path, data)


class ClosureReadinessTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.manifest = _fixture(self.root)

    def report(self):
        return audit_mod.audit(self.manifest, root=self.root)

    def test_fixture_passes_ready_blocked_by_9(self):
        report = self.report()
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["status"], "ready_blocked_by_formal_dependency")
        self.assertEqual(report["blocking_issue"], 9)

    def test_duplicate_key_and_nan_are_not_parseable(self):
        self.manifest.write_text('{"schema":"x","schema":"y"}\n', encoding="utf-8")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(any("malformed JSON" in item for item in report["violations"]))
        self.manifest.write_text('{"schema":NaN}\n', encoding="utf-8")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(any("non-finite" in item for item in report["violations"]))

    def test_missing_acceptance_and_path_escape_rejected_without_keyerror(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        del data["acceptance_evidence"]["vendor_materials_controlled"]
        _write(self.manifest, data)
        report = self.report()
        self.assertTrue(any("acceptance evidence keys differ" in item for item in report["violations"]))
        self.manifest = _fixture(self.root)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["acceptance_evidence"]["source_chain"]["pins"][0]["path"] = "../escape.json"
        _write(self.manifest, data)
        report = self.report()
        self.assertTrue(any("repository-relative" in item or "traversal" in item for item in report["violations"]))

    def test_required_pin_cannot_be_replaced_by_another_file(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        pins = data["acceptance_evidence"]["delivery_identity"]["pins"]
        pins[0]["path"] = "docs/2026-09-10-generated-e0-lifecycle.md"
        pins[0]["sha256"] = _sha(self.root / pins[0]["path"])
        _write(self.manifest, data)
        report = self.report()
        self.assertTrue(any("exact required evidence paths" in item for item in report["violations"]))

    def test_symlinked_pinned_file_rejected(self):
        target = self.root / EVIDENCE_FILES[0]
        backup = target.with_name("lifecycle-real.md")
        target.rename(backup)
        try:
            target.symlink_to(backup)
        except (OSError, NotImplementedError):
            backup.rename(target)
            self.skipTest("symlink creation unavailable")
        report = self.report()
        self.assertTrue(any("symlink" in item for item in report["violations"]))

    @unittest.skipUnless(os.name == "nt", "Windows reparse junction test")
    def test_windows_junction_parent_rejected(self):
        """A junction ancestor is rejected even when its target stays in root."""
        junction = self.root / "docs"
        real_parent = self.root / "docs-real"
        junction.rename(real_parent)
        created = False
        try:
            # Directory junctions do not require symlink privilege.  Try the
            # native mklink form first, and skip explicitly when the host
            # cannot create one (for example, a restricted Windows runner).
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(real_parent)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                self.skipTest(
                    "junction creation unavailable: "
                    + (result.stderr or result.stdout).strip()
                )
            created = True
            report = self.report()
            self.assertTrue(
                any("symlink or reparse point" in item for item in report["violations"]),
                report["violations"],
            )
        finally:
            if created:
                # Removing the junction entry leaves its target contents
                # intact.  Path.rmdir uses RemoveDirectoryW on Windows and
                # does not recursively delete the target.
                junction.rmdir()
            if real_parent.exists():
                real_parent.rename(junction)

    def test_license_stage_must_be_one_of_exact_nine_passing_stages(self):
        path = self.root / EVIDENCE_FILES[1]
        codegen = json.loads(path.read_text(encoding="utf-8"))
        codegen["stages"][0]["status"] = "skipped"
        _write(path, codegen)
        _refresh_pin(self.manifest, EVIDENCE_FILES[1], self.root)
        report = self.report()
        self.assertTrue(any("did not pass" in item for item in report["violations"]))
        codegen["stages"][0]["status"] = "ok"
        codegen["stages"].append(copy.deepcopy(codegen["stages"][0]))
        _write(path, codegen)
        _refresh_pin(self.manifest, EVIDENCE_FILES[1], self.root)
        report = self.report()
        self.assertTrue(any("exactly nine" in item for item in report["violations"]))

    def test_license_checkout_requires_all_five_products(self):
        path = self.root / EVIDENCE_FILES[1]
        codegen = json.loads(path.read_text(encoding="utf-8"))
        del codegen["licenses"]["checkout"]["SIMULINK"]
        _write(path, codegen)
        _refresh_pin(self.manifest, EVIDENCE_FILES[1], self.root)
        report = self.report()
        self.assertTrue(any("exactly five" in item for item in report["violations"]))

    def test_lifecycle_requires_identity_and_per_run_hash_bindings(self):
        path = self.root / EVIDENCE_FILES[5]
        audit = json.loads(path.read_text(encoding="utf-8"))
        audit["runs"][1]["identity"]["pid"] = audit["runs"][0]["identity"]["pid"]
        _write(path, audit)
        _refresh_pin(self.manifest, EVIDENCE_FILES[5], self.root)
        report = self.report()
        self.assertTrue(any("distinct process identities" in item or "drifted" in item for item in report["violations"]))

    def test_lifecycle_binding_drift_rejected(self):
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["run_bindings"][0]["pgid"] += 1
        _write(self.manifest, data)
        report = self.report()
        self.assertTrue(any("identity drifted" in item for item in report["violations"]))

    def test_generated_source_hash_and_unapproved_wrapper_rejected(self):
        path = self.root / EVIDENCE_FILES[4]
        build = json.loads(path.read_text(encoding="utf-8"))
        build["staged_sources"]["Exp1_MinModelTemp.cpp"]["sha256"] = "0" * 64
        _write(path, build)
        _refresh_pin(self.manifest, EVIDENCE_FILES[4], self.root)
        report = self.report()
        self.assertTrue(any("hash-bound" in item or "hash drifted" in item for item in report["violations"]))
        self.manifest = _fixture(self.root)
        path = self.root / EVIDENCE_FILES[4]
        build = json.loads(path.read_text(encoding="utf-8"))
        build["staged_sources"]["model.cpp"]["source_path"] = str(self.root / "Simulator/other/model.cpp")
        _write(path, build)
        _refresh_pin(self.manifest, EVIDENCE_FILES[4], self.root)
        report = self.report()
        self.assertTrue(any("unapproved repository source" in item for item in report["violations"]))

    def test_private_generated_source_and_vendor_artifact_cannot_be_tracked(self):
        generated = self.root / "work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp"
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_bytes(b"private generated source")
        subprocess.run(["git", "add", "-f", "work"], cwd=self.root, check=True, capture_output=True, timeout=30)
        report = self.report()
        self.assertTrue(any("private/generated source" in item or "private generated subtree" in item or "pinned generated root" in item for item in report["violations"]))
        self.manifest = _fixture(self.root)
        (self.root / "vendor.dll").write_bytes(b"vendor")
        subprocess.run(["git", "add", "-f", "vendor.dll"], cwd=self.root, check=True, capture_output=True, timeout=30)
        report = self.report()
        self.assertTrue(any("vendor artifacts" in item for item in report["violations"]))

    def test_current_repo_wrapper_drift_is_rejected(self):
        wrapper = self.root / "Simulator/wksim_core/model.cpp"
        wrapper.write_bytes(wrapper.read_bytes() + b"\n// drift\n")
        report = self.report()
        self.assertTrue(any("model.cpp" in item and "drifted" in item for item in report["violations"]))

    def test_external_same_basename_wrapper_is_rejected(self):
        external = self.root.parent / f"{self.root.name}-external-wrapper"
        external.mkdir(parents=True, exist_ok=True)
        source = external / "model.cpp"
        shutil.copy2(self.root / "Simulator/wksim_core/model.cpp", source)
        path = self.root / EVIDENCE_FILES[4]
        build = json.loads(path.read_text(encoding="utf-8"))
        build["staged_sources"]["model.cpp"]["source_path"] = str(source)
        _write(path, build)
        _refresh_pin(self.manifest, EVIDENCE_FILES[4], self.root)
        report = self.report()
        self.assertTrue(any("same-basename wrapper" in item for item in report["violations"]))

    def test_raw_cycle_tamper_is_rejected(self):
        raw = self.root / "validation/codegen-e0-lifecycle-01/original/cycle-0.jsonl"
        raw.write_bytes(raw.read_bytes() + b"tamper\n")
        report = self.report()
        self.assertTrue(any("raw cycle original/cycle-0.jsonl" in item and "drifted" in item for item in report["violations"]))

    def test_missing_cold_library_is_rejected(self):
        path = self.root / EVIDENCE_FILES[5]
        lifecycle = json.loads(path.read_text(encoding="utf-8"))
        lifecycle["cold_library"] = str(self.root / "artifacts/cold/missing.so")
        _write(path, lifecycle)
        _refresh_pin(self.manifest, EVIDENCE_FILES[5], self.root)
        report = self.report()
        self.assertTrue(any("cold_library" in item and "regular file" in item for item in report["violations"]))

    def test_cold_probe_must_equal_cold_library(self):
        path = self.root / EVIDENCE_FILES[5]
        lifecycle = json.loads(path.read_text(encoding="utf-8"))
        rogue = self.root / "artifacts/rogue-cold.so"
        shutil.copy2(self.root / "artifacts/cold/libwksim_e0.so", rogue)
        cold = next(run for run in lifecycle["runs"] if run["name"] == "cold")
        probe_index = cold["command"].index("--probe") + 1
        cold["command"][probe_index] = str(rogue)
        cold["identity"]["argv"] = list(cold["command"])
        _write(path, lifecycle)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        binding = next(
            item
            for item in data["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["run_bindings"]
            if item["name"] == "cold"
        )
        binding["argv"] = list(cold["command"])
        _write(self.manifest, data)
        _refresh_pin(self.manifest, EVIDENCE_FILES[5], self.root)
        report = self.report()
        self.assertTrue(any("cold --probe" in item and "cold_library" in item for item in report["violations"]))

    def test_cold_library_is_rehashed_and_limitation_is_nonempty(self):
        path = self.root / EVIDENCE_FILES[5]
        lifecycle = json.loads(path.read_text(encoding="utf-8"))
        cold_path = Path(lifecycle["cold_library"])
        cold_path.write_bytes(cold_path.read_bytes() + b"tamper\n")
        _write(path, lifecycle)
        _refresh_pin(self.manifest, EVIDENCE_FILES[5], self.root)
        report = self.report()
        self.assertTrue(any("cold_library" in item and "hash drifted" in item for item in report["violations"]))

        self.manifest = _fixture(self.root)
        lifecycle_path = self.root / EVIDENCE_FILES[5]
        lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
        lifecycle["limitation"] = ""
        _write(lifecycle_path, lifecycle)
        _refresh_pin(self.manifest, EVIDENCE_FILES[5], self.root)
        report = self.report()
        self.assertTrue(any("limitation" in item and "non-empty" in item for item in report["violations"]))

    def test_raw_sha256_rejects_rogue_entries_in_audit_and_manifest(self):
        path = self.root / EVIDENCE_FILES[5]
        lifecycle = json.loads(path.read_text(encoding="utf-8"))
        lifecycle["raw_sha256"]["rogue/cycle-0.jsonl"] = next(iter(lifecycle["raw_sha256"].values()))
        _write(path, lifecycle)
        _refresh_pin(self.manifest, EVIDENCE_FILES[5], self.root)
        report = self.report()
        self.assertTrue(any("exact expected evidence set" in item and "rogue/cycle-0.jsonl" in item for item in report["violations"]))

        self.manifest = _fixture(self.root)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        requirements = data["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]
        requirements["raw_sha256"]["rogue/cycle-0.jsonl"] = next(iter(requirements["raw_sha256"].values()))
        _write(self.manifest, data)
        report = self.report()
        self.assertTrue(any("requirements.raw_sha256" in item and "exact expected evidence set" in item for item in report["violations"]))

    def test_wsl_maps_every_windows_drive_and_rejects_posix_on_native_windows(self):
        windows_path = r"D:\matlab\install date\simulink\include\rtw_solver.h"
        if audit_mod.os.name == "nt":
            mapped = audit_mod._as_host_path(windows_path, self.root)
            self.assertEqual(str(mapped), windows_path)
            self.assertIsNone(audit_mod._as_host_path("/mnt/d/matlab/rtw_solver.h", self.root))
        else:
            mapped = audit_mod._as_host_path(windows_path, Path("/mnt/c/wksim"))
            self.assertEqual(mapped.as_posix(), "/mnt/d/matlab/install date/simulink/include/rtw_solver.h")

    def test_provenance_parent_symlink_is_rejected(self):
        build_path = self.root / EVIDENCE_FILES[4]
        build = json.loads(build_path.read_text(encoding="utf-8"))
        source = Path(build["staged_sources"]["rtw_solver.h"]["source_path"])
        real_parent = source.parent.with_name(source.parent.name + "-real")
        source.parent.rename(real_parent)
        try:
            try:
                source.parent.symlink_to(real_parent, target_is_directory=True)
            except (OSError, NotImplementedError):
                real_parent.rename(source.parent)
                self.skipTest("directory symlink creation unavailable")
            report = self.report()
            self.assertTrue(any("source_path" in item and "symlink" in item for item in report["violations"]))
        finally:
            if source.parent.is_symlink():
                source.parent.unlink()
            if real_parent.exists():
                real_parent.rename(source.parent)

    def test_nested_null_and_numeric_types_are_rejected(self):
        path = self.root / EVIDENCE_FILES[1]
        codegen = json.loads(path.read_text(encoding="utf-8"))
        codegen["environment"] = None
        _write(path, codegen)
        _refresh_pin(self.manifest, EVIDENCE_FILES[1], self.root)
        report = self.report()
        self.assertTrue(any("codegen environment must be a JSON object" in item for item in report["violations"]))

        self.manifest = _fixture(self.root)
        path = self.root / EVIDENCE_FILES[5]
        lifecycle = json.loads(path.read_text(encoding="utf-8"))
        lifecycle["runs"][0]["returncode"] = 0.0
        _write(path, lifecycle)
        _refresh_pin(self.manifest, EVIDENCE_FILES[5], self.root)
        report = self.report()
        self.assertTrue(any("returncode must be an integer" in item for item in report["violations"]))

    def test_drive_relative_source_path_is_rejected(self):
        path = self.root / EVIDENCE_FILES[4]
        build = json.loads(path.read_text(encoding="utf-8"))
        build["staged_sources"]["rtw_solver.h"]["source_path"] = "C:relative/rtw_solver.h"
        _write(path, build)
        _refresh_pin(self.manifest, EVIDENCE_FILES[4], self.root)
        report = self.report()
        self.assertTrue(any("source_path" in item and "absolute" in item for item in report["violations"]))

    def test_excluded_files_is_an_exact_collection(self):
        path = self.root / EVIDENCE_FILES[4]
        build = json.loads(path.read_text(encoding="utf-8"))
        build["excluded_files"].append("extra.cpp")
        _write(path, build)
        _refresh_pin(self.manifest, EVIDENCE_FILES[4], self.root)
        report = self.report()
        self.assertTrue(any("exact set" in item for item in report["violations"]))

    def test_any_tracked_entry_under_pinned_generated_root_is_rejected(self):
        extra = self.root / "work/codegen-e0/short-cycle-codegen-01/codegen/extra/tracked.txt"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("tracked generated material\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", "work/codegen-e0/short-cycle-codegen-01/codegen/extra/tracked.txt"], cwd=self.root, check=True, capture_output=True, timeout=30)
        report = self.report()
        self.assertTrue(any("pinned generated root" in item for item in report["violations"]))


@unittest.skipUnless(MANIFEST.is_file(), "closure manifest not present")
class RealRepositoryTests(unittest.TestCase):
    def test_real_historical_evidence_is_conservatively_not_ready(self):
        report = audit_mod.audit(MANIFEST, root=ROOT)
        self.assertTrue(report["violations"])
        self.assertEqual(report["status"], "not_ready")

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, "-B", str(ROOT / "tools/audit_26_closure_readiness.py")], capture_output=True, timeout=60)
        self.assertEqual(ok.returncode, 2, ok.stderr.decode())
        report = json.loads(ok.stdout.decode())
        self.assertEqual(report["status"], "not_ready")
        bad = subprocess.run([sys.executable, "-B", str(ROOT / "tools/audit_26_closure_readiness.py"), "--manifest", "absent.json"], capture_output=True, timeout=60)
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
