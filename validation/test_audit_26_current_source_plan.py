"""Pure offline contract tests for the #26 current-wrapper cold-recheck plan.

Scope and honesty notes
-----------------------
These tests exercise the *plan's* preconditions and the *existing* tool
contracts it relies on.  They deliberately do **not** mirror the plan document
back at itself, and they do not assert on numbers the plan says are unknown.

Every assertion here is a real invariant that must hold for the plan to be
executable, so a change in the wrapper, the driver surface, the checker's
binding rules, or the plan's command line fails the suite loudly.

None of the following is executed anywhere in this file:

* no ``.so`` / DLL is loaded;
* no compiler is invoked;
* no MATLAB or Embedded Coder process;
* no native, flight, ROS or UE node;
* no WSL command (the WSL runner is replaced by an in-process recorder).

Yields, not repeats: the suite checks that the plan's named new evidence
identifiers do not collide with existing evidence, that the two existing tools
agree on the wrapper, and that the checker's hard-coded bindings really do
block a naive "just make a new manifest" workaround.
"""

import ast
import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import audit_26_closure_readiness as checker
import build_generated_e0 as driver

WRAPPER = ROOT / "Simulator/wksim_core/model.cpp"
PLAN = ROOT / "docs/plan/26-current-wrapper-recheck-plan.md"

# Frozen on 2026-09-12 from the live checkout; the plan asserts these values.
CURRENT_WRAPPER_SHA256 = "150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290"
CURRENT_WRAPPER_SIZE = 4070
PINNED_WRAPPER_SHA256 = "3f325678b1d85c9aa3fd07bd644d82935aa26d82885926defeced139f02ddf2c"
PINNED_WRAPPER_SIZE = 1864
PINNED_LIBRARY_SHA256 = "7da6853201b89238c273f2e1360ad21fe479e267d0ed08cf3500f98bf535505e"

# The plan's chosen identifiers.
PLAN_BUILD_ID = "current-wrapper-01"
PLAN_EVIDENCE_DIR = ROOT / "validation/codegen-e0-build-current-wrapper-01"
PLAN_WSL_DIR = "/root/wksim-codegen-e0-build-current-wrapper-01"
PLAN_LIFECYCLE_DIR = ROOT / "validation/codegen-e0-lifecycle-current-wrapper-01"

HISTORICAL_DIRS = (
    ROOT / "validation/codegen-e0-build-short-cycle-01",
    ROOT / "validation/codegen-e0-lifecycle-01",
    ROOT / "validation/codegen-e0/short-cycle-codegen-01",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checker_expected_staged_sources():
    """Extract the staged-sources set the checker requires.

    The checker pins the six build inputs via its ``expected_staged`` set
    literal inside ``tools/audit_26_closure_readiness.py``.  Read that
    literal out of the checker source so the test compares the driver
    against what the checker actually requires, not a copy of itself.
    """
    source = (ROOT / "tools/audit_26_closure_readiness.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Set)
            and any(
                isinstance(target, ast.Name) and target.id == "expected_staged"
                for target in node.targets
            )
        ):
            return {elt.value for elt in node.value.elts}
    raise AssertionError(
        "expected_staged set literal not found in tools/audit_26_closure_readiness.py"
    )


# --------------------------------------------------------------------------
# 1. Input identity: the plan's premise must still be true.
# --------------------------------------------------------------------------


class WrapperIdentityTests(unittest.TestCase):
    def test_current_wrapper_matches_the_plan_premise(self):
        """If the wrapper changes again, the plan is stale and must be redone."""
        self.assertEqual(sha256(WRAPPER), CURRENT_WRAPPER_SHA256)
        self.assertEqual(WRAPPER.stat().st_size, CURRENT_WRAPPER_SIZE)

    def test_wrapper_is_actually_drifted_from_the_pinned_identity(self):
        """The plan exists only because these two identities differ."""
        self.assertNotEqual(CURRENT_WRAPPER_SHA256, PINNED_WRAPPER_SHA256)
        self.assertNotEqual(CURRENT_WRAPPER_SIZE, PINNED_WRAPPER_SIZE)
        self.assertEqual(CURRENT_WRAPPER_SIZE - PINNED_WRAPPER_SIZE, 2206)

    def test_pinned_wrapper_hash_is_still_what_history_records(self):
        """The old pin must remain untouched, or historical evidence is invalid."""
        build = json.loads(
            (ROOT / "validation/codegen-e0-build-short-cycle-01/build-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        staged = build["staged_sources"]["model.cpp"]
        self.assertEqual(staged["sha256"], PINNED_WRAPPER_SHA256)
        self.assertEqual(staged["size_bytes"], PINNED_WRAPPER_SIZE)
        audit = json.loads(
            (ROOT / "validation/codegen-e0-lifecycle-01/audit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(audit["source_sha256"]["model.cpp"], PINNED_WRAPPER_SHA256)
        self.assertEqual(audit["library_sha256"], PINNED_LIBRARY_SHA256)


# --------------------------------------------------------------------------
# 2. Tool agreement: both tools must point at the same wrapper.
# --------------------------------------------------------------------------


class ToolAgreementTests(unittest.TestCase):
    def test_driver_default_wrapper_is_the_checker_allowed_wrapper(self):
        driver_rel = driver.DEFAULT_WRAPPER_SOURCE.resolve().relative_to(ROOT).as_posix()
        self.assertEqual(driver_rel, "Simulator/wksim_core/model.cpp")
        self.assertIn(driver_rel, checker.ALLOWED_REPO_WRAPPERS)
        self.assertEqual(WRAPPER.resolve(), driver.DEFAULT_WRAPPER_SOURCE.resolve())

    def test_driver_stages_exactly_the_six_sources_the_checker_pins(self):
        self.assertEqual(
            set(driver.REQUIRED_BUILD_SOURCES),
            {
                "Exp1_MinModelTemp.cpp",
                "Exp1_MinModelTemp.h",
                "rtwtypes.h",
                "model.cpp",
                "rtw_continuous.h",
                "rtw_solver.h",
            },
        )
        # The checker requires the same set for build-manifest staged_sources;
        # compare against the checker's own expected_staged literal.
        self.assertEqual(set(driver.REQUIRED_BUILD_SOURCES), checker_expected_staged_sources())

    def test_driver_excludes_only_ert_main(self):
        self.assertEqual(set(driver.EXCLUDED_BUILD_SOURCES), {"ert_main.cpp"})

    def test_driver_compiler_flags_match_the_recorded_historical_flags(self):
        build = json.loads(
            (ROOT / "validation/codegen-e0-build-short-cycle-01/build-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(driver.COMPILER_FLAGS, build["toolchain"]["flags"])

    def test_driver_has_no_dry_run_so_the_plan_cannot_quietly_be_executed(self):
        import inspect

        params = inspect.signature(driver.build_and_evaluate).parameters
        for required in ("wrapper_source", "run_test", "evidence_root", "build_id"):
            self.assertIn(required, params)
        self.assertNotIn("dry_run", params)


# --------------------------------------------------------------------------
# 3. Driver evidence gates: the approved path refuses stale or tampered input.
# --------------------------------------------------------------------------


class DriverGateTests(unittest.TestCase):
    def test_reference_generation_evidence_satisfies_every_gate(self):
        """The real codegen evidence dir must pass the gate without changes."""
        if not driver.DEFAULT_GENERATION_DIR.exists():
            self.skipTest(
                f"private generation evidence tree absent: {driver.DEFAULT_GENERATION_DIR}"
            )
        result = driver.verify_generation_evidence(
            generation_evidence_dir=driver.DEFAULT_GENERATION_DIR,
            project_root=ROOT,
        )
        self.assertEqual(result["generation_run_id"], "short-cycle-codegen-01")
        for name in ("Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "rtwtypes.h"):
            entry = result["verified_sources"][name]
            self.assertEqual(entry["sha256"], result["expected_hashes"][name])

    def test_mathworks_include_prerequisites_resolve(self):
        if not driver.DEFAULT_MATLAB_INCLUDE.exists():
            self.skipTest(
                f"private MATLAB include tree absent: {driver.DEFAULT_MATLAB_INCLUDE}"
            )
        result = driver.verify_external_prerequisites(
            matlab_include_dir=driver.DEFAULT_MATLAB_INCLUDE,
            wrapper_source=WRAPPER,
        )
        self.assertEqual(result["model.cpp"]["sha256"], CURRENT_WRAPPER_SHA256)
        self.assertEqual(result["model.cpp"]["size_bytes"], CURRENT_WRAPPER_SIZE)
        for header in ("rtw_continuous.h", "rtw_solver.h"):
            self.assertGreater(result[header]["size_bytes"], 0)

    @staticmethod
    def _generation_fixture(tmp, tamper_generated=False):
        """Build a structurally valid synthetic generation evidence fixture.

        Mirrors the real layout: ``command.json['cwd']`` is the staged model
        directory holding ``codegen_config.json``, whose ``codegen_folder``
        holds ``Exp1_MinModelTemp_ert_rtw`` with the generated sources.
        Returns ``(evidence_dir, codegen_source_dir)``.
        """
        root = Path(tmp)
        staged = root / "staged-model"
        codegen = root / "codegen"
        source_dir = codegen / "Exp1_MinModelTemp_ert_rtw"
        source_dir.mkdir(parents=True)
        staged.mkdir(parents=True)
        evidence = root / "evidence"
        evidence.mkdir()

        generated = {}
        for name in ("Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "rtwtypes.h", "ert_main.cpp"):
            path = source_dir / name
            path.write_bytes(f"// synthetic {name}\n".encode("utf-8"))
            generated[name] = path
        declared = {name: sha256(path) for name, path in generated.items()}
        if tamper_generated:
            declared["Exp1_MinModelTemp.cpp"] = "0" * 64

        (codegen / "codegen_config.json").parent.mkdir(parents=True, exist_ok=True)
        (staged / "codegen_config.json").write_text(
            json.dumps({"codegen_folder": str(codegen)}), encoding="utf-8"
        )
        (evidence / "generated-sources-manifest.json").write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "relative_path": f"Exp1_MinModelTemp_ert_rtw/{name}",
                            "sha256": digest,
                            "size_bytes": generated[name].stat().st_size,
                        }
                        for name, digest in declared.items()
                    ]
                }
            ),
            encoding="utf-8",
        )
        (evidence / "command.json").write_text(
            json.dumps(
                {
                    "return_code": 0,
                    "timed_out": False,
                    "cleanup_unverified": False,
                    "cwd": str(staged),
                }
            ),
            encoding="utf-8",
        )
        (evidence / "summary.json").write_text(
            json.dumps(
                {
                    "status": "generated",
                    "matlab_return_code": 0,
                    "stages_ok": True,
                    "licenses_ok": True,
                    "has_valid_artifacts": True,
                    "source_tampered": False,
                    "staged_tampered": False,
                    "timed_out": False,
                    "cleanup_unverified": False,
                }
            ),
            encoding="utf-8",
        )
        unchanged = json.dumps(
            [{"filename": "x.slx", "expected_sha256": "a" * 64, "actual_sha256": "a" * 64, "unchanged": True}]
        )
        (evidence / "post-source-verification.json").write_text(unchanged, encoding="utf-8")
        (evidence / "post-staged-verification.json").write_text(unchanged, encoding="utf-8")
        (evidence / "codegen-report.json").write_text(
            json.dumps(
                {
                    "status": "generated",
                    "stages": [
                        {"name": name, "status": "ok"}
                        for name in (
                            "license_verification",
                            "fileGenControl",
                            "load_system",
                            "verify_solver",
                            "configure_target",
                            "initialization",
                            "slbuild",
                            "artifact_verification",
                            "close_model",
                        )
                    ],
                    "licenses": {
                        "test": {name.replace("-", "_"): 1 for name in driver.REQUIRED_LICENSES},
                        "checkout": {name.replace("-", "_"): 1 for name in driver.REQUIRED_LICENSES},
                    },
                }
            ),
            encoding="utf-8",
        )
        return evidence, source_dir

    def test_synthetic_fixture_reaches_the_generated_source_hash_gate(self):
        """Control: the untampered fixture must pass, proving the negative is meaningful."""
        with tempfile.TemporaryDirectory() as tmp:
            evidence, source_dir = self._generation_fixture(tmp, tamper_generated=False)
            result = driver.verify_generation_evidence(
                generation_evidence_dir=evidence,
                codegen_source_dir=source_dir,
                project_root=Path(tmp),
            )
            self.assertIn("Exp1_MinModelTemp.cpp", result["verified_sources"])

    def test_tampered_generated_source_is_rejected(self):
        """A drifted generated source must not silently enter a build."""
        with tempfile.TemporaryDirectory() as tmp:
            evidence, source_dir = self._generation_fixture(tmp, tamper_generated=True)
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                driver.verify_generation_evidence(
                    generation_evidence_dir=evidence,
                    codegen_source_dir=source_dir,
                    project_root=Path(tmp),
                )

    def test_empty_post_verification_is_rejected(self):
        """'unchanged' proof cannot be vacuous."""
        with tempfile.TemporaryDirectory() as tmp:
            evidence, source_dir = self._generation_fixture(tmp)
            (evidence / "post-source-verification.json").write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty list"):
                driver.verify_generation_evidence(
                    generation_evidence_dir=evidence,
                    codegen_source_dir=source_dir,
                    project_root=Path(tmp),
                )

    def test_codegen_source_dir_override_must_match_the_bound_folder(self):
        """The driver refuses a codegen source folder it was not bound to."""
        with tempfile.TemporaryDirectory() as tmp:
            evidence, source_dir = self._generation_fixture(tmp)
            elsewhere = Path(tmp) / "elsewhere"
            elsewhere.mkdir()
            with self.assertRaisesRegex(ValueError, "does not match bound staged codegen_config folder"):
                driver.verify_generation_evidence(
                    generation_evidence_dir=evidence,
                    codegen_source_dir=elsewhere,
                    project_root=Path(tmp),
                )


# --------------------------------------------------------------------------
# 4. Output-directory rules: the plan's new paths must be new.
# --------------------------------------------------------------------------


class OutputDirectoryRuleTests(unittest.TestCase):
    def test_driver_rejects_a_directory_it_would_reuse(self):
        """The rule that made current-wrapper-01 a fresh id is still enforced."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "validation").mkdir()
            occupied = root / "validation/codegen-e0-build-occupied"
            occupied.mkdir()
            (occupied / "summary.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                driver.validate_evidence_containment(occupied, project_root=root)
            empty = root / "validation/codegen-e0-build-empty"
            empty.mkdir()
            driver.validate_evidence_containment(empty, project_root=root)

    def test_executed_evidence_ids_are_unique(self):
        """Both current-wrapper ids must coexist with the historical lifecycle id."""
        self.assertEqual(
            sorted(path.name for path in (ROOT / "validation").glob("codegen-e0-build-current-wrapper-*")),
            ["codegen-e0-build-current-wrapper-01"],
        )
        self.assertEqual(
            sorted(path.name for path in (ROOT / "validation").glob("codegen-e0-lifecycle-*")),
            ["codegen-e0-lifecycle-01", "codegen-e0-lifecycle-current-wrapper-01"],
        )

    def test_wsl_build_dir_satisfies_the_driver_pattern(self):
        driver.validate_wsl_build_dir(PLAN_WSL_DIR)

    def test_wsl_build_dir_rejects_traversal_and_reuse_of_historical_ids(self):
        for bad in (
            "/root/wksim-codegen-e0-build-../etc",
            "/tmp/wksim-codegen-e0-build-x",
            "/root/other",
            "/root/wksim-codegen-e0-build-short-cycle-01/",
        ):
            with self.assertRaises(ValueError):
                driver.validate_wsl_build_dir(bad)

    def test_evidence_must_stay_inside_validation(self):
        """Containment rule, exercised on a fresh tree (existing dirs refuse reuse)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "validation").mkdir()
            fresh = root / "validation/codegen-e0-build-fresh"
            driver.validate_evidence_containment(fresh, project_root=root)
            (root / "docs").mkdir()
            with self.assertRaises(ValueError):
                driver.validate_evidence_containment(root / "docs/plan", project_root=root)
            with self.assertRaises(ValueError):
                driver.validate_evidence_containment(root / "validation", project_root=root)
        # The executed evidence really does live inside the repo validation root.
        self.assertTrue(PLAN_EVIDENCE_DIR.is_dir())
        self.assertEqual(PLAN_EVIDENCE_DIR.parent.name, "validation")

    def test_historical_directories_are_named_by_the_plan_as_read_only(self):
        text = PLAN.read_text(encoding="utf-8")
        for path in HISTORICAL_DIRS:
            self.assertIn(path.relative_to(ROOT).as_posix(), text)
        self.assertIn("零改动", text)

    def test_optional_lifecycle_output_now_carries_the_run_result(self):
        """The plan's step 7 entry point has since been executed by the main session."""
        self.assertTrue(PLAN_LIFECYCLE_DIR.is_dir())
        audit = json.loads((PLAN_LIFECYCLE_DIR / "audit.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["cycles"], 4)
        self.assertEqual(audit["ticks_per_cycle"], 1000)
        self.assertEqual(audit["compared_values"], 4 * 1000 * 120)
        self.assertEqual(audit["library_sha256"], "528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328")
        # Four raw cycle files must be byte-identical across original and cold.
        raw = {key: sha256(PLAN_LIFECYCLE_DIR / key) for key in audit["raw_sha256"]}
        self.assertEqual(set(raw), {
            "original/cycle-0.jsonl", "original/cycle-1.jsonl",
            "cold/cycle-0.jsonl", "cold/cycle-1.jsonl",
        })
        self.assertEqual(len(set(raw.values())), 1)
        self.assertEqual(set(raw.values()), set(audit["raw_sha256"].values()))
        # original and cold are independent processes that both exited cleanly.
        self.assertEqual({run["name"] for run in audit["runs"]}, {"original", "cold"})
        self.assertTrue(all(run["returncode"] == 0 for run in audit["runs"]))
        self.assertEqual(len({run["identity"]["pid"] for run in audit["runs"]}), 2)


# --------------------------------------------------------------------------
# 3b. The executed evidence itself (read-only hashing; no load, no compile).
# --------------------------------------------------------------------------


class ExecutedEvidenceTests(unittest.TestCase):
    """Locks in the main session's current-wrapper-01 result.

    Pure file hashing and JSON reading only: no ``.so`` is loaded, nothing is
    compiled, and no model is stepped.  These assertions make the recorded
    result reproducible and catch any silent overwrite of historical pins.
    """

    EVIDENCE = ROOT / "validation/codegen-e0-build-current-wrapper-01"
    FREEZE = ROOT / "validation/coordination/native-inputs-20260912/current-wrapper-01.json"
    NEW_LIBRARY_SHA256 = "528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328"
    NEW_LIBRARY_SIZE = 87584
    WRAPPER_SHA256 = "150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290"
    WRAPPER_SIZE = 4070

    def setUp(self):
        if not self.EVIDENCE.is_dir():
            self.skipTest("current-wrapper-01 evidence not present")

    def manifest(self):
        return json.loads((self.EVIDENCE / "build-manifest.json").read_text(encoding="utf-8"))

    def test_manifest_binds_the_current_wrapper_not_the_pinned_one(self):
        staged = self.manifest()["staged_sources"]["model.cpp"]
        self.assertEqual(staged["sha256"], self.WRAPPER_SHA256)
        self.assertEqual(staged["size_bytes"], self.WRAPPER_SIZE)
        self.assertNotEqual(staged["sha256"], PINNED_WRAPPER_SHA256)

    def test_library_identity_is_recorded_and_differs_from_history(self):
        manifest = self.manifest()
        self.assertEqual(manifest["output_library"]["sha256"], self.NEW_LIBRARY_SHA256)
        self.assertEqual(manifest["output_library"]["size_bytes"], self.NEW_LIBRARY_SIZE)
        self.assertNotEqual(manifest["output_library"]["sha256"], PINNED_LIBRARY_SHA256)

    def test_summary_and_manifest_agree_for_the_validator_entrypoint(self):
        """The next entry point requires summary.json beside build-manifest.json."""
        summary = json.loads((self.EVIDENCE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["library_sha256"], self.NEW_LIBRARY_SHA256)
        self.assertEqual(summary["status"], "tested")
        self.assertTrue(summary["clean_runtime_deps"])
        self.assertEqual(summary["library_sha256"], self.manifest()["output_library"]["sha256"])

    def test_probe_covered_only_a_100_step_constant_input_window(self):
        probe = json.loads((self.EVIDENCE / "test-probe.json").read_text(encoding="utf-8"))
        self.assertTrue(probe["success"])
        self.assertEqual(probe["steps_evaluated"], 100)
        self.assertEqual(probe["step_size_seconds"], 0.001)
        self.assertEqual(probe["sim_time_seconds"], 0.1)
        self.assertTrue(probe["all_outputs_finite"])
        self.assertIsNone(probe["non_finite_step"])
        self.assertEqual(probe["output_dimension"], 120)

    def test_ldd_audit_is_clean_and_free_of_matlab_traces(self):
        audit = self.manifest()["ldd_audit"]
        self.assertTrue(audit["clean"])
        self.assertEqual(audit["violations"], [])
        lowered = " ".join(audit["dependencies"]).lower()
        for forbidden in ("matlab", "simulink", "libmw", "mcr", "rflysim"):
            self.assertNotIn(forbidden, lowered)

    def test_evidence_contains_no_reset_or_cold_cycle_artifacts(self):
        """Documents the coverage gap rather than assuming it away."""
        names = {path.name for path in self.EVIDENCE.rglob("*") if path.is_file()}
        for absent in ("audit.json", "cycle-0.jsonl", "contract.json"):
            self.assertNotIn(absent, names)
        self.assertFalse(any(path.is_dir() for path in self.EVIDENCE.rglob("cold")))
        self.assertFalse(any(path.is_dir() for path in self.EVIDENCE.rglob("original")))

    def test_evidence_never_mentions_terrain_so_that_interface_is_unverified(self):
        blob = " ".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in self.EVIDENCE.rglob("*")
            if path.is_file()
        ).lower()
        self.assertNotIn("terrain", blob)

    def test_freeze_record_declares_a_limited_scope(self):
        freeze = json.loads(self.FREEZE.read_text(encoding="utf-8"))
        self.assertIs(freeze["full_or_g6_acceptance"], False)
        self.assertEqual(freeze["library_sha256"], self.NEW_LIBRARY_SHA256)
        self.assertEqual(freeze["status"], "tested")
        self.assertEqual(freeze["steps"], 100)
        self.assertTrue(freeze["historical_and_input_hashes_unchanged"])
        self.assertEqual(freeze["changes"], [])
        self.assertEqual(
            freeze["hashes_before"]["Simulator/wksim_core/model.cpp"], self.WRAPPER_SHA256
        )
        self.assertEqual(
            freeze["hashes_before"]["tools/build_generated_e0.py"],
            "0f6c7a8caa6b6b885115e76986bceb0ecc07f06050ea78c316d8aa14747c1c68",
        )

    def test_historical_pins_are_still_intact_after_the_new_build(self):
        """The new build must not have rewritten the old evidence."""
        pin_view = {
            "validation/codegen-e0-build-short-cycle-01/build-manifest.json": "0669730aeff54012e70c55e8fc1d103cfeb00cc33ec5b3147144df847fc7aa1c",
            "validation/codegen-e0/short-cycle-codegen-01/codegen-report.json": "e5f32bd2890137591b61eba72fe0b21893fef578fd0a57094baf8fe92398f822",
            "validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json": "85c40213cec0f349d36664c5621bb53c46ad96f9756cdd4eaa2bb97a7b2acc67",
            "validation/codegen-e0/short-cycle-codegen-01/summary.json": "42bc11a2a55fc26542cb52d34fc22d7ae8b3c6fc66deec19708aa232eb910f7c",
            "validation/codegen-e0-lifecycle-01/audit.json": "3d5c7896de10d10521ff4a1881eaffc8c96e73b196be72f9a044f2fc1aed346d",
            "docs/plan/26-closure-readiness-manifest.json": "229eb94c8bc4cec71693719b32ad86f716b8a92ac4a2e19b541fc701bc72a1d7",
        }
        for relative, expected in pin_view.items():
            self.assertEqual(sha256(ROOT / relative), expected, relative)

    def test_validator_entrypoint_prerequisites_are_satisfied(self):
        """第 50 行六源集与第 57 行 summary.json 同目录要求。"""
        staged = set(self.manifest()["staged_sources"])
        self.assertEqual(
            staged,
            {
                "Exp1_MinModelTemp.cpp",
                "Exp1_MinModelTemp.h",
                "rtwtypes.h",
                "model.cpp",
                "rtw_continuous.h",
                "rtw_solver.h",
            },
        )
        self.assertTrue((self.EVIDENCE / "summary.json").is_file())


# --------------------------------------------------------------------------
# 5. Why "just write a new manifest" is not enough.
# --------------------------------------------------------------------------


class CheckerBindingTests(unittest.TestCase):
    def test_checker_hardcodes_the_single_historical_build_and_lifecycle_paths(self):
        source = (ROOT / "tools/audit_26_closure_readiness.py").read_text(encoding="utf-8")
        self.assertIn("validation/codegen-e0-build-short-cycle-01/build-manifest.json", source)
        self.assertIn("validation/codegen-e0-lifecycle-01/audit.json", source)
        self.assertEqual(
            checker.PINNED_GENERATED_ROOT, "work/codegen-e0/short-cycle-codegen-01/codegen/"
        )

    def test_checker_allows_exactly_one_wrapper_path(self):
        self.assertEqual(
            set(checker.ALLOWED_REPO_WRAPPERS), {"Simulator/wksim_core/model.cpp"}
        )

    def test_checker_pins_are_bound_to_exact_historical_paths(self):
        flattened = {path for paths in checker.EXPECTED_PIN_PATHS.values() for path in paths}
        self.assertTrue(all(not path.startswith("validation/codegen-e0-build-current-wrapper-01") for path in flattened))
        self.assertIn("validation/codegen-e0-build-short-cycle-01/build-manifest.json", flattened)

    def test_checker_cli_has_no_root_flag_but_the_api_does(self):
        """The plan's 'do not build a second checker' rule rests on this gap."""
        import inspect

        main_src = inspect.getsource(checker.main)
        tree = ast.parse(main_src.strip())
        flags = {
            arg.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("--")
        }
        self.assertEqual(flags, {"--manifest", "--output"})
        self.assertNotIn("--root", flags)
        # The API-level entry point really does accept a replacement root.
        self.assertIn("root", inspect.signature(checker.audit).parameters)

    def test_report_carries_the_three_semantics_without_new_field_names(self):
        """The plan must not need new CLI merely for nicer field names."""
        with tempfile.TemporaryDirectory() as tmp:
            report = checker.audit(
                ROOT / "docs/plan/26-closure-readiness-manifest.json", root=Path(tmp)
            )
        self.assertIn("status", report)
        self.assertIn("violations", report)
        self.assertIn("blocking_issue", report)
        self.assertEqual(report["blocking_issue"], 9)
        self.assertEqual(report["status"], "not_ready")
        self.assertTrue(report["violations"])

    def test_checker_refuses_a_posix_provenance_path_on_windows(self):
        """This is the host-mapping artefact the plan must not misread."""
        if checker.os.name != "nt":
            self.skipTest("Windows-specific mapping rule")
        self.assertIsNone(checker._as_host_path("/root/wksim-codegen-e0-build-x/lib.so", ROOT))

    def test_checker_maps_windows_provenance_to_mnt_on_posix_hosts(self):
        if checker.os.name == "nt":
            self.skipTest("POSIX-specific mapping rule")
        mapped = checker._as_host_path(r"D:\matlab\install date\simulink\include\rtw_solver.h", ROOT)
        self.assertEqual(
            mapped.as_posix(), "/mnt/d/matlab/install date/simulink/include/rtw_solver.h"
        )


# --------------------------------------------------------------------------
# 5b. The checker's strict JSON loader must fail closed on hostile input.
# --------------------------------------------------------------------------


class CheckerStrictJsonTests(unittest.TestCase):
    """Direct pure tests of the checker's strict JSON parsing helpers.

    Only ``_load_json``, ``_strict_object_pairs``, ``_reject_constant`` and
    ``_strict_number`` are exercised, on in-memory temp files: no evidence
    tree, no execution, no external process.
    """

    def _load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hostile.json"
            path.write_text(text, encoding="utf-8")
            return checker._load_json(path, "hostile input")

    def test_duplicate_keys_fail_closed(self):
        with self.assertRaisesRegex(checker.AuditDataError, "duplicate JSON key: a"):
            self._load('{"a": 1, "a": 2}')

    def test_nan_and_infinity_literals_fail_closed(self):
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(literal=literal):
                with self.assertRaisesRegex(
                    checker.AuditDataError, "non-finite JSON number"
                ):
                    self._load('{"value": %s}' % literal)

    def test_1e999_is_rejected_downstream_not_by_json_decoding(self):
        """1e999 decodes to float('inf'): the stdlib never calls
        parse_constant for overflow literals, so the strict loader alone
        accepts it.  The checker rejects it only downstream, where its
        finite-number validation applies."""
        # The stdlib fact the wording rests on: decoding 1e999 yields inf.
        self.assertEqual(json.loads("1e999"), float("inf"))
        # Hence the strict loader also accepts it...
        self.assertEqual(self._load('{"value": 1e999}')["value"], float("inf"))
        # ...and the downstream finite-number gate is what fails closed.
        with self.assertRaisesRegex(checker.AuditDataError, "must be a finite"):
            checker._strict_number(float("inf"), "hostile value")


# --------------------------------------------------------------------------
# 6. The plan document itself must remain executable and honest.
# --------------------------------------------------------------------------


class PlanDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PLAN.read_text(encoding="utf-8")

    def test_plan_exposes_every_executable_command_token(self):
        for token in (
            "tools/build_generated_e0.py",
            "--wrapper-source",
            "--generation-dir",
            "--matlab-include-dir",
            "--build-id",
            "--evidence-root",
            "--wsl-build-dir",
            "--run-test",
            "--test-steps",
        ):
            self.assertIn(token, self.text)

    def test_plan_names_only_new_output_directories(self):
        self.assertIn("validation/codegen-e0-build-current-wrapper-01/", self.text)
        self.assertIn("/root/wksim-codegen-e0-build-current-wrapper-01", self.text)
        self.assertIn("validation/codegen-e0-lifecycle-current-wrapper-01/", self.text)

    def test_plan_forbids_reusing_historical_identifiers(self):
        self.assertRegex(self.text, r"不得使用 `short-cycle-01`")
        for forbidden in (
            "validation/codegen-e0-build-short-cycle-01/",
            "validation/codegen-e0-lifecycle-01/",
        ):
            self.assertIn(forbidden, self.text)

    def test_plan_records_the_input_assertions_the_test_can_check(self):
        self.assertIn(CURRENT_WRAPPER_SHA256, self.text)
        self.assertIn(str(CURRENT_WRAPPER_SIZE), self.text)
        self.assertIn(PINNED_WRAPPER_SHA256, self.text)
        self.assertIn(PINNED_LIBRARY_SHA256, self.text)

    def test_plan_records_the_measured_library_without_generalising(self):
        """The measured value is recorded as an observation, not a law."""
        self.assertIn("528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328", self.text)
        self.assertIn("87584", self.text)
        self.assertIn("不构成", self.text)
        self.assertIn("普遍推断", self.text)

    def test_plan_records_the_coverage_gaps_explicitly(self):
        section = self.text.split("### B.3", 1)[1].split("### B.4", 1)[0]
        for gap in ("reset / 冷重建周期", "terrain", "G6", "已初始化态"):
            self.assertIn(gap, section)

    def test_plan_records_the_validator_entrypoint_verdict(self):
        section = self.text.split("### A.2", 1)[1].split("### A.3", 1)[0]
        self.assertIn("不接受显式 library 参数", section)
        self.assertIn("--library", section)
        self.assertIn("validation/codegen-e0-build-current-wrapper-01/build-manifest.json", section)
        self.assertIn("validation/codegen-e0-lifecycle-current-wrapper-01", section)

    def test_plan_no_longer_claims_the_entrypoint_is_unfrozen(self):
        """The superseded old state must be marked as superseded, not left live."""
        self.assertIn("已被取代", self.text)
        self.assertIn("缺口 A 已解除", self.text)

    def test_plan_carries_the_non_extrapolation_boundaries(self):
        self.assertIn("禁止外推边界", self.text)
        # Every forbidden inference must name the exact thing it forbids.
        for boundary in (
            "#26 可关闭",
            "物理精度通过",
            "G6",
            "R1",
            "terrain",
        ):
            self.assertIn(boundary, self.text)
        self.assertIn("AC1–AC4", self.text)
        # Each numbered boundary must be a real prohibition.
        section = self.text.split("### C.3", 1)[1].split("### C.4", 1)[0]
        numbered = re.findall(r"^\d+\. .+$", section, flags=re.MULTILINE)
        self.assertGreaterEqual(len(numbered), 8)
        self.assertTrue(all("不得" in line for line in numbered), numbered)

    def test_plan_separates_real_blocker_from_inapplicable_gaps(self):
        """Gap A is resolved; B (budget) and C (ABI) do not apply to this scope."""
        self.assertIn("缺口 A 已解除", self.text)
        self.assertIn("G6", self.text)
        self.assertIn("R1", self.text)

    def test_plan_states_nothing_is_executed_by_this_module(self):
        self.assertIn("不重新生成、不编译、不运行 MATLAB", self.text)


if __name__ == "__main__":
    unittest.main()
