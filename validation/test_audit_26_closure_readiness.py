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
ARCHIVED_WRAPPER_RELATIVE = (
    "validation/lunar-20-epoch-1/case/run/epochs/"
    "2a8d5df1dd4244c3868dc7f38e85a369/source/Simulator/wksim_core/model.cpp"
)
IDENTITIES_RELATIVE = audit_mod.HISTORICAL_IDENTITIES_RELATIVE


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def _git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, timeout=30
    )


def _commit(root, message="fixture"):
    # --allow-empty keeps re-fixture runs (identical bytes) working.
    _git(
        root,
        "-c", "user.name=fixture", "-c", "user.email=fixture@example.com",
        "commit", "-q", "--allow-empty", "-m", message,
    )



def _fixture(root):
    """Build a complete, offline-verifiable evidence fixture."""
    for relative in EVIDENCE_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    wrapper = root / "Simulator/wksim_core/model.cpp"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "Simulator/wksim_core/model.cpp", wrapper)

    generated_manifest_path = root / EVIDENCE_FILES[2]
    generated_manifest = json.loads(generated_manifest_path.read_text(encoding="utf-8"))
    codegen_report_path = root / EVIDENCE_FILES[1]
    codegen_report = json.loads(codegen_report_path.read_text(encoding="utf-8"))
    build_path = root / EVIDENCE_FILES[4]
    build = json.loads(build_path.read_text(encoding="utf-8"))
    generated_dir = root / "work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw"
    generated_dir.mkdir(parents=True, exist_ok=True)
    fixture_sources = {
        "Exp1_MinModelTemp.cpp": b"// synthetic generated implementation fixture\n",
        "Exp1_MinModelTemp.h": b"// synthetic generated interface fixture\n",
        "rtwtypes.h": b"// synthetic generated type fixture\n",
        "ert_main.cpp": b"// synthetic excluded main fixture\n",
    }
    for basename, payload in fixture_sources.items():
        (generated_dir / basename).write_bytes(payload)
    generated_by_name = {
        Path(item["relative_path"].replace("\\", "/")).name: item
        for item in generated_manifest["sources"]
    }
    report_by_name = {item["name"]: item for item in codegen_report["artifacts"]}
    for basename in fixture_sources:
        source = generated_dir / basename
        generated_by_name[basename]["sha256"] = _sha(source)
        generated_by_name[basename]["size_bytes"] = source.stat().st_size
        report_by_name[basename]["bytes"] = source.stat().st_size
    _write(generated_manifest_path, generated_manifest)
    _write(codegen_report_path, codegen_report)
    external_dir = root.parent / f"{root.name}-external-inputs"
    external_dir.mkdir(parents=True, exist_ok=True)
    (external_dir / "rtw_continuous.h").write_bytes(b"// synthetic external continuous header fixture\n")
    (external_dir / "rtw_solver.h").write_bytes(b"// synthetic external solver header fixture\n")
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
    lifecycle["source_sha256"] = {
        basename: item["sha256"] for basename, item in build["staged_sources"].items()
    }
    for run in lifecycle["runs"]:
        old_probe = run["command"][run["command"].index("--probe") + 1]
        probe = artifact if run["name"] == "original" else cold_artifact
        run["command"] = [str(probe) if value == old_probe else value for value in run["command"]]
        run["identity"]["argv"] = list(run["command"])
    _write(audit_path, lifecycle)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["library_sha256"] = lifecycle["library_sha256"]
    manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["source_sha256"] = dict(lifecycle["source_sha256"])
    for binding in manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]["run_bindings"]:
        binding["library_sha256"] = lifecycle["library_sha256"]
        binding["source_sha256"] = dict(lifecycle["source_sha256"])
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
    _git(root, "init", "-q")
    tracked = [*EVIDENCE_FILES, "Simulator/wksim_core/model.cpp", "manifest.json", *raw_paths,
               "artifacts/libwksim_e0.so", "artifacts/cold/libwksim_e0.so"]
    # Pin conversion off so HEAD blob bytes equal the worktree bytes exactly,
    # then establish a real HEAD commit: HEAD-blob checks must not be
    # satisfiable by index registration alone.
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "add", "--", *tracked)
    _commit(root)
    return manifest_path


def _refresh_pin(manifest_path, relative, root):
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in data["acceptance_evidence"].values():
        for pin in entry["pins"]:
            if pin["path"] == relative:
                pin["sha256"] = _sha(root / relative)
    _write(manifest_path, data)


def _declare_historical_wrapper(manifest_path, root, *, staging="commit",
                                archived_bytes=b"// archived historical wrapper\n"):
    """Repin the fixture's model.cpp evidence to a declared historical digest.

    The frozen snapshot is the only copy the wrapper digest is allowed to be
    re-hashed from.  ``staging`` distinguishes the three durability classes
    the audit must separate: ``"commit"`` (real HEAD commit), ``"staged"``
    (index-only ``git add``, never committed) and ``"untracked"``.
    Returns ``(archived_path, digest, size_bytes)``.
    """
    archived = root / ARCHIVED_WRAPPER_RELATIVE
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_bytes(archived_bytes)
    digest = _sha(archived)
    size = archived.stat().st_size

    build_path = root / EVIDENCE_FILES[4]
    build = json.loads(build_path.read_text(encoding="utf-8"))
    build["staged_sources"]["model.cpp"]["sha256"] = digest
    build["staged_sources"]["model.cpp"]["size_bytes"] = size
    _write(build_path, build)

    lifecycle_path = root / EVIDENCE_FILES[5]
    lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    lifecycle["source_sha256"]["model.cpp"] = digest
    _write(lifecycle_path, lifecycle)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    requirements = manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]
    requirements["source_sha256"]["model.cpp"] = digest
    for binding in requirements["run_bindings"]:
        binding["source_sha256"]["model.cpp"] = digest
    _write(manifest_path, manifest)

    wrapper = root / "Simulator/wksim_core/model.cpp"
    declaration = {
        "schema": audit_mod.HISTORICAL_IDENTITIES_SCHEMA,
        "kind": "declared_historical_wrapper_identities",
        "issue": 26,
        "date": "2026-09-13",
        "purpose": "fixture declaration for the fail-closed wrapper binding",
        "rule": "re-hash the archived copy; missing, untracked or drifted is rejected",
        "canonical_wrapper_path": "Simulator/wksim_core/model.cpp",
        "current_canonical_wrapper": {
            "sha256": _sha(wrapper),
            "size_bytes": wrapper.stat().st_size,
        },
        "identities": [
            {
                "sha256": digest,
                "size_bytes": size,
                "archived_repo_path": ARCHIVED_WRAPPER_RELATIVE,
                "archived_repo_path_verified_sha256": digest,
                "archived_repo_path_verified_size_bytes": size,
            }
        ],
        "acceptance_effect": {
            "rewrites_historical_pin": False,
            "new_digest_still_fails_closed": True,
        },
    }
    _write(root / IDENTITIES_RELATIVE, declaration)
    _refresh_pin(manifest_path, EVIDENCE_FILES[4], root)
    _refresh_pin(manifest_path, EVIDENCE_FILES[5], root)
    if staging in ("commit", "staged"):
        _git(root, "add", "-f", "--", ARCHIVED_WRAPPER_RELATIVE, IDENTITIES_RELATIVE)
    if staging == "commit":
        _commit(root, "declare historical wrapper identity")
    return archived, digest, size


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

    # -- declared historical wrapper identity -------------------------------

    def test_declared_historical_wrapper_is_verified_from_the_archived_snapshot(self):
        archived, digest, _ = _declare_historical_wrapper(self.manifest, self.root)
        wrapper = self.root / "Simulator/wksim_core/model.cpp"
        self.assertNotEqual(_sha(wrapper), digest)  # the canonical path moved on
        report = self.report()
        self.assertEqual(report["violations"], [], report["violations"])
        self.assertEqual(report["status"], "ready_blocked_by_formal_dependency")
        self.assertEqual(_sha(archived), digest)

    def test_current_wrapper_drift_stales_the_committed_declaration(self):
        # P1-1: the declared current-canonical digest is cross-hashed against
        # the live wrapper, so drifting the canonical checkpoint after the
        # declaration commit fails closed instead of moving underneath it.
        archived, digest, size = _declare_historical_wrapper(self.manifest, self.root)
        manifest_bytes = self.manifest.read_bytes()
        archived_bytes = archived.read_bytes()
        wrapper = self.root / "Simulator/wksim_core/model.cpp"
        wrapper.write_bytes(wrapper.read_bytes() + b"\n// later drift\n")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(
            any("current canonical wrapper disagrees" in item for item in report["violations"]),
            report["violations"],
        )
        # The historical pin itself is never rewritten.
        self.assertEqual(self.manifest.read_bytes(), manifest_bytes)
        self.assertEqual(archived.read_bytes(), archived_bytes)
        self.assertEqual(_sha(archived), digest)
        self.assertEqual(archived.stat().st_size, size)

    def test_missing_archived_snapshot_fails_closed(self):
        archived, _, _ = _declare_historical_wrapper(self.manifest, self.root)
        archived.unlink()
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(
            any("archived historical wrapper" in item for item in report["violations"]),
            report["violations"],
        )

    def test_drifted_archived_snapshot_fails_closed(self):
        archived, _, _ = _declare_historical_wrapper(self.manifest, self.root)
        original = archived.read_bytes()
        replacement = b"X" + original[1:]  # same length, different bytes
        self.assertEqual(len(replacement), len(original))
        archived.write_bytes(replacement)
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(any("hash drifted" in item for item in report["violations"]), report["violations"])

    def test_untracked_archived_snapshot_fails_closed(self):
        _declare_historical_wrapper(self.manifest, self.root, staging="untracked")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(any("not committed at HEAD" in item for item in report["violations"]), report["violations"])

    def test_undeclared_wrapper_digest_still_fails_closed(self):
        _declare_historical_wrapper(self.manifest, self.root)
        path = self.root / EVIDENCE_FILES[4]
        build = json.loads(path.read_text(encoding="utf-8"))
        build["staged_sources"]["model.cpp"]["sha256"] = "a" * 64
        _write(path, build)
        _refresh_pin(self.manifest, EVIDENCE_FILES[4], self.root)
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(any("model.cpp" in item for item in report["violations"]), report["violations"])

    # -- P1 regressions: the declaration cannot authorize itself ------------

    def test_staged_only_declaration_and_snapshot_fail_closed(self):
        # A1/A2: ``git add`` without a commit must not satisfy the binding.
        _declare_historical_wrapper(self.manifest, self.root, staging="staged")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(
            any("not committed at HEAD" in item for item in report["violations"]),
            report["violations"],
        )

    def test_untracked_declaration_fails_closed(self):
        # A2: a dropped declaration file is not honored even when the
        # archived snapshot itself is properly committed.
        _declare_historical_wrapper(self.manifest, self.root, staging="untracked")
        _git(self.root, "add", "-f", "--", ARCHIVED_WRAPPER_RELATIVE)
        _commit(self.root, "commit archived snapshot only")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(
            any(
                "historical wrapper identities declaration" in item and "not committed at HEAD" in item
                for item in report["violations"]
            ),
            report["violations"],
        )

    def test_declaration_worktree_drift_after_commit_fails_closed(self):
        # A3: mutating the declaration after its commit is byte drift.
        _declare_historical_wrapper(self.manifest, self.root)
        declaration = self.root / IDENTITIES_RELATIVE
        declaration.write_bytes(declaration.read_bytes() + b" \n")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(
            any(
                "historical wrapper identities declaration" in item and "drifted from its HEAD blob" in item
                for item in report["violations"]
            ),
            report["violations"],
        )

    def test_recommitted_declaration_with_wrong_canonical_digest_fails_closed(self):
        # A3: even a fully committed declaration is cross-hashed against the
        # live canonical wrapper.
        _declare_historical_wrapper(self.manifest, self.root)
        declaration = self.root / IDENTITIES_RELATIVE
        data = json.loads(declaration.read_text(encoding="utf-8"))
        data["current_canonical_wrapper"]["sha256"] = "0" * 64
        data["purpose"] = "rewritten by an attacker"
        _write(declaration, data)
        _git(self.root, "add", "-f", "--", IDENTITIES_RELATIVE)
        _commit(self.root, "tampered declaration")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(
            any("current canonical wrapper disagrees" in item for item in report["violations"]),
            report["violations"],
        )

    def test_unborn_head_fails_closed(self):
        # A1 variant: with no HEAD at all, nothing can be committed at HEAD.
        _declare_historical_wrapper(self.manifest, self.root)
        _git(self.root, "update-ref", "-d", "HEAD")
        report = self.report()
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(
            any("not committed at HEAD" in item for item in report["violations"]),
            report["violations"],
        )


    # -- host boundary classification ---------------------------------------

    @unittest.skipUnless(os.name == "nt", "POSIX-host boundary classification")
    def test_unaddressable_posix_artifact_is_host_bounded_not_a_violation(self):
        report = {"violations": [], "host_bounded": []}
        result = audit_mod._provenance_path(
            "/root/wksim-codegen-e0-cold-fixture/libwksim_e0.so",
            self.root,
            "lifecycle cold_library",
            report,
        )
        self.assertIsNone(result)
        self.assertEqual(report["violations"], [])
        self.assertEqual(len(report["host_bounded"]), 1)
        self.assertEqual(
            report["host_bounded"][0]["path"],
            "/root/wksim-codegen-e0-cold-fixture/libwksim_e0.so",
        )

    def test_missing_host_addressable_artifact_fails_closed(self):
        missing = (
            r"Z:\wksim-missing\libwksim_e0.so"
            if os.name == "nt"
            else "/root/wksim-missing/libwksim_e0.so"
        )
        report = {"violations": [], "host_bounded": []}
        candidate = audit_mod._provenance_path(missing, self.root, "build output library", report)
        self.assertIsNotNone(candidate)
        self.assertFalse(
            audit_mod._actual_file(candidate, "build output library", report, sha256="0" * 64)
        )
        self.assertTrue(any("build output library" in item for item in report["violations"]))
        self.assertEqual(report["host_bounded"], [])

    # -- vendor classification ----------------------------------------------

    @staticmethod
    def _receipt(found):
        return {
            "checked_unix": 1789000000.0,
            "distro": "RflySim-20.04",
            "boot_id": "00000000-0000-0000-0000-000000000000",
            "uptime": "10.0 20.0",
            "found": found,
        }

    def _track(self, relative, payload):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (bytes, bytearray)):
            path.write_bytes(payload)
        else:
            path.write_text(payload, encoding="utf-8")
        subprocess.run(
            ["git", "add", "-f", "--", relative],
            cwd=self.root, check=True, capture_output=True, timeout=30,
        )
        return path

    def test_empty_wsl_precheck_receipts_are_not_vendor_material(self):
        self._track(
            "validation/coordination/probe/precheck-RflySim-20.04.json",
            json.dumps(self._receipt([]), indent=2) + "\n",
        )
        self._track(
            "validation/coordination/probe/RflySim-20.04-precheck.txt",
            json.dumps(self._receipt([])) + "\n\n",
        )
        report = self.report()
        self.assertEqual(report["violations"], [], report["violations"])

    def test_real_wsl_warning_receipt_form_is_accepted(self):
        # The exact trailing warning of the real tracked receipt
        # validation/coordination/perf-open-admission-20260913-01/RflySim-20.04-precheck.txt
        # must keep classifying as a clean receipt.
        self._track(
            "validation/coordination/probe/RflySim-20.04-precheck.txt",
            json.dumps(self._receipt([]))
            + "\nwsl: Failed to start the systemd user session for 'root'. "
              "See journalctl for more details.\n",
        )
        report = self.report()
        self.assertEqual(report["violations"], [], report["violations"])

    def test_wsl_receipt_trailing_payload_is_vendor_material(self):
        # A4: anything after the JSON document that is not whitespace or the
        # one exact documented WSL systemd warning makes the file an offender.
        receipt = json.dumps(self._receipt([]))
        real_warning = (
            "wsl: Failed to start the systemd user session for 'root'. "
            "See journalctl for more details."
        )
        cases = {
            "second JSON document": receipt + "\n{\"found\": []}\n",
            "base64 payload": receipt + "\nTVqQAAMAAAAEAAAA//8AALgAAAAAAAAAQAAAAAAAAAAA\n",
            "warning then payload": receipt + "\nwsl: warning\nTVqQAAMAAAAEAAAA\n",
            "non-wsl line": receipt + "\nLoading vendor runtime...\n",
            "payload before warning": receipt + "\nnot-a-warning\nwsl: warning\n",
            "bare wsl prefix": receipt + "\nwsl:warning without space\n",
            "generic wsl warning": receipt + "\nwsl: warning\n",
            "wsl-prefixed vendor payload": receipt + "\nwsl: TVqQAAMAAAAEAAAA\n",
            "warning with extra suffix": receipt + "\n" + real_warning + " TVqQ\n",
            "two warning lines": receipt + "\n" + real_warning + "\n" + real_warning + "\n",
            "unsafe username": receipt + (
                "\nwsl: Failed to start the systemd user session for 'root payload'. "
                "See journalctl for more details.\n"
            ),
        }
        for name, payload in cases.items():
            with self.subTest(case=name):
                self._track("validation/coordination/probe/RflySim-20.04-precheck.txt", payload)
                report = self.report()
                self.assertTrue(
                    any("vendor artifacts" in item for item in report["violations"]),
                    f"{name}: {report['violations']}",
                )

    def test_wsl_receipt_strict_schema(self):
        # P1-3: duplicate keys, non-finite numbers, missing/extra keys,
        # wrong field types and a non-list ``found`` are all rejected.
        receipt = self._receipt([])
        compact = json.dumps(receipt)
        cases = {
            "duplicate key": compact[:-1] + ', "distro": "RflySim-20.04"}',
            "NaN constant": compact.replace("1789000000.0", "NaN"),
            "Infinity overflow literal": compact.replace("1789000000.0", "1e999"),
            "missing key": json.dumps({k: v for k, v in receipt.items() if k != "boot_id"}),
            "extra key": json.dumps({**receipt, "note": "extra"}),
            "found not a list": json.dumps({**receipt, "found": ""}),
            "found non-string element": json.dumps({**receipt, "found": [None]}),
            "checked_unix wrong type": json.dumps({**receipt, "checked_unix": "1789000000"}),
            "distro wrong type": json.dumps({**receipt, "distro": 20.04}),
        }
        for name, payload in cases.items():
            with self.subTest(case=name):
                self._track("validation/coordination/probe/RflySim-20.04-precheck.txt", payload)
                report = self.report()
                self.assertTrue(
                    any("vendor artifacts" in item for item in report["violations"]),
                    f"{name}: {report['violations']}",
                )


    def test_nonempty_found_receipt_is_vendor_material(self):
        self._track(
            "validation/coordination/probe/precheck-RflySim-20.04.json",
            json.dumps(self._receipt(["/usr/bin/rflysim-core"])),
        )
        report = self.report()
        self.assertTrue(any("vendor artifacts" in item for item in report["violations"]), report["violations"])

    def test_binary_rflysim_named_file_is_vendor_material(self):
        self._track("validation/coordination/probe/RflySim-20.04-blob.bin", b"\x00\x01\x02rflysim")
        report = self.report()
        self.assertTrue(any("vendor artifacts" in item for item in report["violations"]), report["violations"])

    def test_real_dll_is_vendor_material(self):
        self._track("validation/coordination/probe/RflySim-20.04-native.dll", b"MZ vendor")
        report = self.report()
        self.assertTrue(any("vendor artifacts" in item for item in report["violations"]), report["violations"])

    def test_rflysim_named_non_receipt_text_is_vendor_material(self):
        self._track(
            "validation/coordination/probe/rflysim-notes.txt",
            "rflysim dependency is loaded\n",
        )
        report = self.report()
        self.assertTrue(any("vendor artifacts" in item for item in report["violations"]), report["violations"])

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
    def report(self):
        return audit_mod.audit(MANIFEST, root=ROOT)

    def _declaration_committed(self):
        return subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{IDENTITIES_RELATIVE}"],
            cwd=ROOT, capture_output=True, timeout=30,
        ).returncode == 0

    def test_real_pin_and_vendor_rules_are_no_longer_misclassified(self):
        report = self.report()
        joined = " | ".join(report["violations"])
        if not self._declaration_committed():
            # The uncommitted declaration is rejected and its historical
            # identity is not honored, so the build-manifest wrapper pin
            # cascades onto the current 4070-byte source.  Both violations
            # are the intended fail-closed state until main commits it.
            self.assertEqual(report["status"], "not_ready")
            self.assertIn("historical wrapper identities declaration", joined)
            self.assertIn("expected 1864", joined)
            return
        self.assertNotIn("expected 1864", joined)
        self.assertNotIn("vendor artifacts", joined)
        self.assertNotIn("cannot be mapped on this host", joined)
        self.assertEqual(report["blocking_issue"], 9)

    def test_real_status_tracks_the_declaration_commit_state(self):
        declaration = ROOT / IDENTITIES_RELATIVE
        if not declaration.is_file():
            self.skipTest("historical wrapper identity declaration not present")
        committed = self._declaration_committed()
        report = self.report()
        if not committed:
            # The declaration cannot self-authorize: until it is committed on
            # main the audit must report not_ready on every host.
            self.assertEqual(report["status"], "not_ready")
            self.assertTrue(
                any(
                    "historical wrapper identities declaration" in item
                    for item in report["violations"]
                ),
                report["violations"],
            )
            return
        if report["violations"]:
            # Only a POSIX host that genuinely lacks the Linux-only /root
            # products may still fail; on Windows the declared snapshot and
            # the empty receipts must make the audit clean.
            if os.name == "nt":
                self.fail(f"unexpected violations on Windows: {report['violations']}")
            self.assertEqual(report["status"], "not_ready")
        else:
            self.assertEqual(report["status"], "ready_blocked_by_formal_dependency")

    def test_real_host_bounded_items_are_reported_separately(self):
        report = self.report()
        for item in report["host_bounded"]:
            self.assertIn("field", item)
            self.assertIn("path", item)
            self.assertIn("reason", item)
        if os.name == "nt":
            self.assertTrue(report["host_bounded"])
        else:
            self.assertEqual(report["host_bounded"], [])

    def test_cli_exit_codes(self):
        ok = subprocess.run([sys.executable, "-B", str(ROOT / "tools/audit_26_closure_readiness.py")], capture_output=True, timeout=60)
        report = json.loads(ok.stdout.decode())
        self.assertEqual(report["blocking_issue"], 9)
        if os.name == "nt" and not report["violations"]:
            self.assertEqual(ok.returncode, 0, ok.stderr.decode())
        else:
            self.assertEqual(ok.returncode, 2, ok.stderr.decode())
        bad = subprocess.run([sys.executable, "-B", str(ROOT / "tools/audit_26_closure_readiness.py"), "--manifest", "absent.json"], capture_output=True, timeout=60)
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
