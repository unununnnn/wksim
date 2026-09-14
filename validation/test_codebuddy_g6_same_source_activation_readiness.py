"""Offline readiness tests for docs/plan/59-g6-same-source-activation-readiness-20260914.md.

This pair is the minimal same-source *activation-readiness* evidence for #59: it
records the exact implemented preflight order of
``tools/run_e0_same_source_conformance.py``, the current fail-closed blockers,
the future authorized command shape, the expected output/evidence fields and the
deterministic READY/BLOCKED rule.  The current verdict is BLOCKED (0/120 budgets
approved); nothing here approves a budget, launches MATLAB/native, or closes
#59, #84, G6 or Full.

The suite is pure stdlib and entirely offline (no MATLAB/native/ROS/DDS/SITL/
Unreal/build/flight, no #83 rerun, no network).  It checks, fail-closed:

* the exact bytes (SHA-256 + size + LF) of the readiness document;
* exactly six *tracked* source pins (SHA-256 + size) and, for each, that the
  bytes come from the HEAD blob (``git ls-tree`` / ``git show HEAD:<path>``) and
  still equal the worktree - staged-only, untracked or drifted pins fail;
* the documented preflight order against the real call order inside ``run()``;
* the documented frozen constants, command shapes and result/evidence fields
  against the implemented entry module;
* the real blocked behavior of the entry for a missing contract, the frozen R1
  contract (refused by path) and an incomplete budget contract - no launch and
  no evidence directory in any case;
* negative wording mutations: dropping a non-closure token, a readiness gate,
  the fail-closed token or a prohibition marker must be detected;
* ancestry gates for ``f333316e``, ``6eafdf9c`` and ``31e5b65f`` (an invalid
  object name is rejected) with no exact-HEAD pin anywhere;
* the two candidate files exist as worktree bytes and are never compared to the
  shared real index.

Run modes (env ``WKSIM_G6_SSAR_TEST_MODE``):

* ``normal`` (default): worktree run; no index-touching git call is made and a
  guard test asserts that.
* ``external-index``: requires ``GIT_INDEX_FILE`` pointing to a repo-external
  temporary index in which exactly the two candidates are staged at stage 0;
  only that external index is read.  The shared real ``.git/index`` is never
  read, fingerprinted, staged or modified in any mode.

Suggested external run (PowerShell, repo-external temp index):

    $TMPIDX = Join-Path $env:TEMP 'wksim-tmpidx-g6ssar'
    $env:GIT_INDEX_FILE = $TMPIDX
    git add -- docs/plan/59-g6-same-source-activation-readiness-20260914.md `
               validation/test_codebuddy_g6_same_source_activation_readiness.py
    $env:WKSIM_G6_SSAR_TEST_MODE = 'external-index'
    python -B -m unittest validation.test_codebuddy_g6_same_source_activation_readiness -v
    Remove-Item $TMPIDX

The exact two staged entries are the readiness document and this test module.
"""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOC_REL = "docs/plan/59-g6-same-source-activation-readiness-20260914.md"
TEST_REL = "validation/test_codebuddy_g6_same_source_activation_readiness.py"
ENTRY_REL = "tools/run_e0_same_source_conformance.py"
LEDGER_REL = "validation/e0-budget-approval-provenance-20260914.json"
FRAME_REL = "validation/e0-frame-datum-binding-20260914.json"
R1_REL = "Simulator/wksim_core/numerical-conformance-v1.json"

CANDIDATES = (DOC_REL, TEST_REL)

DOC_PATH = ROOT / DOC_REL
TEST_PATH = ROOT / TEST_REL
ENTRY_PATH = ROOT / ENTRY_REL

MODE_ENV = "WKSIM_G6_SSAR_TEST_MODE"
MODE_NORMAL = "normal"
MODE_EXTERNAL = "external-index"

DOC_SHA256 = "9958b00feafb9bc6dc0098da123ab6f2a668e06bb03da551eaa56ac46dacb106"
DOC_SIZE = 15498

# Exactly six tracked source pins: (relative path, sha256, bytes).  These bytes
# are the HEAD blobs of this checkout; nothing else is pinned by this slice and
# no untracked reference-sampling document is a dependency.
PINNED_SOURCES = (
    ("tools/run_e0_same_source_conformance.py",
     "8398100b7fb6b839e279afd6e8f8708e57e415450dbb6621acdc9ea9ecc46517", 64513),
    ("docs/plan/59-e0-same-source-command.md",
     "345caff0fd354717a64ed1dfac2c3ad33f87c72713cf3362483c395fb66b197e", 10221),
    ("docs/plan/10-g6-remediation-contract.md",
     "48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0", 9935),
    (LEDGER_REL,
     "2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d", 285820),
    (FRAME_REL,
     "5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f", 105018),
    (R1_REL,
     "23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0", 29846),
)
PINNED_PATHS = tuple(row[0] for row in PINNED_SOURCES)

# Ancestry gates only: these must stay ancestors of the current HEAD.  The
# current HEAD is deliberately never pinned, so later unrelated commits do not
# invalidate this binding.
ANCESTOR_COMMITS = (
    "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",
    "6eafdf9c0b734db07a9fe790c86b409d3468c10b",
    "31e5b65f5448c5558450d16d0f46da0ef0f0a03c",
)

DOC_TEXT = DOC_PATH.read_text(encoding="utf-8")
ENTRY_TEXT = ENTRY_PATH.read_text(encoding="utf-8")
TEST_SOURCE = TEST_PATH.read_bytes().decode("utf-8")

# git plumbing that would read or write an index; used by the normal-mode guard.
INDEX_CMDS = frozenset(
    {"ls-files", "update-index", "add", "rm", "write-tree", "read-tree",
     "commit", "reset", "checkout", "restore", "status", "diff", "stash"}
)
INDEX_TOUCHING_CALLS = []

# Required non-closure vocabulary of the document.
NONCLOSURE_TOKENS = ("numerical_failed", "#59", "#84", "G6", "Full", "not-closed", "不关闭")

# Budget-inference sources that may only ever appear under an explicit
# prohibition; each of these must co-occur with a prohibition marker.
PROHIBITION_MARKERS = ("禁止", "不得", "不能", "不足以", "不是", "无法", "不构成")
FORBIDDEN_INFERENCE_TOKENS = ("观测差值", "ULP", "噪声", "RK4", "SITL", "控制接缝")

# The deterministic READY conjunction and the fail-closed BLOCKED definition.
READINESS_GATES = ("blocking_reasons", "validate_execution",
                   "native executable identity probe", "_prepare_execution")
NEGATION_MARKERS = ("不等于", "不代表", "不是", "不构成")
FAIL_CLOSED_TOKEN = "任一不成立"

# (source step label, call-site literal inside run()) in implemented order.
SOURCE_STEPS = (
    ("validate_contract", "validate_contract(contract_path)"),
    ("validate_execution", "validate_execution(contract_path, contract)"),
    ("native_identity_probe_preflight",
     "observed = _verify_native_executable(execution, native_identity_probe)"),
    ("prepare_execution", "_prepare_execution(contract_path, execution, evidence_dir)"),
    ("normal_launch", "side='normal'"),
    ("validate_reference_outputs", "_validate_reference_outputs(prepared, execution)"),
    ("native_identity_probe_prelaunch",
     "launch_observed = _verify_native_executable(execution, native_identity_probe)"),
    ("native_launch", "side='native'"),
    ("validate_native_inputs", "_validate_native_inputs(evidence"),
    ("parse_native_record", "parse_native_record(evidence"),
    ("align", "aligned = align(normal_values"),
    ("compare_aligned", "comparison = compare_aligned(aligned"),
    ("execution_result",
     "result = _execution_result(prepared, execution, normal_status, native_status,"),
)
DOC_STEP_TOKENS = (
    "validate_contract", "validate_execution", "_verify_native_executable",
    "_prepare_execution", "_launch_process", "_validate_reference_outputs",
    "_verify_native_executable", "_launch_process", "_validate_native_inputs",
    "parse_native_record", "align(", "compare_aligned", "_execution_result",
)

RESULT_FIELDS = (
    "status", "case_id", "epoch", "contract_id", "contract_sha256", "input_sha256",
    "execution_attempted", "matlab_launched", "native_launched", "normal", "native",
    "sampling", "comparison", "scalar_count", "comparisons", "failed_values",
    "failed_conditions", "failed_scalars", "physical_accuracy", "g6_acceptance",
)
BLOCKED_FIELDS = ("blocking_reasons", "scope")
SCALAR_FIELDS = (
    "observable", "array", "index", "sample_count", "max_abs_error", "rms_error",
    "abs_budget", "rel_budget", "rms_budget", "pointwise_failed_count",
    "first_pointwise_failure_k", "rms_failed", "failed_count",
)
EVIDENCE_ARTIFACTS = (
    "contract.json", "input.csv", "manifest.json", "native-build-manifest.json",
    "reference.json", "applied-input.f64", "normal.stdout.log", "normal.stderr.log",
    "normal-process.json", "native-launch-identity.json", "native.stdout.log",
    "native.stderr.log", "native-process.json", "result.json",
)
ARRAY_F64_ARTIFACTS = ("Vehicle60.f64", "Sensor30.f64", "GPS30.f64")

DOC_HEADINGS = (
    "# #59 G6 同源 e0 激活就绪性",
    "## 1. 已实现预检次序",
    "## 2. 当前 fail-closed 阻塞项",
    "## 3. 未来已授权命令形态",
    "## 4. 期望输出与证据字段",
    "## 5. 确定性 READY/BLOCKED 规则",
    "## 6. 禁止的预算推导来源",
    "## 7. 来源 pin",
    "## 8. 非关闭声明",
    "## 9. 验证",
)


def current_mode():
    return os.environ.get(MODE_ENV, MODE_NORMAL)


def blob_sha1(data):
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def _git(args, extra_env=None):
    """Run git read-only plumbing; never inherits GIT_INDEX_FILE by default."""
    env = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
    if extra_env:
        env.update(extra_env)
    if args and args[0] in INDEX_CMDS:
        INDEX_TOUCHING_CALLS.append(tuple(args))
    return subprocess.run(["git"] + list(args), cwd=str(ROOT), env=env,
                          capture_output=True, timeout=60)


def _git_text(args, extra_env=None):
    done = _git(args, extra_env)
    return done, done.stdout.decode("utf-8", "strict")


def is_ancestor(sha):
    """True only on exit status 0; invalid object names and non-ancestors are False."""
    return _git(["merge-base", "--is-ancestor", sha, "HEAD"]).returncode == 0


def _doc_section(start_marker, end_marker):
    _, tail = DOC_TEXT.split(start_marker, 1)
    section, _ = tail.split(end_marker, 1)
    return section


def _run_body():
    source = ENTRY_TEXT
    return source[source.index("def run("):source.index("def _result(")]


def detect_nonclosure(text):
    """Violations if any required non-closure/frozen-failure token is absent."""
    return ["missing_nonclosure:" + token for token in NONCLOSURE_TOKENS if token not in text]


def detect_forbidden_inference(text):
    """Violations if a forbidden budget-inference source is stated without a prohibition."""
    violations = []
    for token in FORBIDDEN_INFERENCE_TOKENS:
        lines = [line for line in text.splitlines() if token in line]
        if not any(marker in line for line in lines for marker in PROHIBITION_MARKERS):
            violations.append("unprohibited_inference_source:" + token)
    return violations


def detect_ready_blocked_rule(text):
    """Violations of the deterministic, fail-closed READY/BLOCKED statement."""
    violations = []
    if "READY" not in text or "BLOCKED" not in text:
        violations.append("missing_readiness_vocabulary")
    for gate in READINESS_GATES:
        if gate not in text:
            violations.append("missing_readiness_gate:" + gate)
    if FAIL_CLOSED_TOKEN not in text:
        violations.append("blocked_not_fail_closed")
    for line in text.splitlines():
        if "READY" in line and "通过" in line and not any(m in line for m in NEGATION_MARKERS):
            violations.append("ready_claimed_as_pass")
            break
    return violations


def _load_entry():
    spec = importlib.util.spec_from_file_location("g6_ssar_entry", ENTRY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENTRY = _load_entry()


class TestDocBytes(unittest.TestCase):
    """Byte and section binding of the readiness document."""

    def test_doc_bytes_bound_and_lf_normalized(self):
        raw = DOC_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), DOC_SHA256)
        self.assertEqual(len(raw), DOC_SIZE)
        self.assertNotIn(b"\r", raw, "the document must be LF-normalized")
        self.assertTrue(raw.endswith(b"\n"))

    def test_doc_sections_complete(self):
        for heading in DOC_HEADINGS:
            with self.subTest(heading=heading):
                self.assertIn(heading, DOC_TEXT)
        self.assertIn("BLOCKED（入口未就绪，0/120 预算获批）", DOC_TEXT)

    def test_doc_preserves_r1_failure_and_open_issues(self):
        for token in NONCLOSURE_TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, DOC_TEXT)
        self.assertIn("#59/#84/G6 = open", DOC_TEXT)
        self.assertIn("Full = not-closed", DOC_TEXT)
        for token in ("budget_approved=false", "g6_acceptance=false",
                      "physical_accuracy=false", "issues_closed=false"):
            with self.subTest(token=token):
                self.assertIn(token, DOC_TEXT)

    def test_doc_required_wording_detectors_clean(self):
        self.assertEqual(detect_nonclosure(DOC_TEXT), [])
        self.assertEqual(detect_forbidden_inference(DOC_TEXT), [])
        self.assertEqual(detect_ready_blocked_rule(DOC_TEXT), [])


class TestDocumentedBlockers(unittest.TestCase):
    """The documented blocker counts must be re-derivable from the pinned artifacts."""

    def test_documented_blocker_counts_match_pinned_artifacts(self):
        ledger = json.loads((ROOT / LEDGER_REL).read_text(encoding="utf-8"))
        frame = json.loads((ROOT / FRAME_REL).read_text(encoding="utf-8"))
        self.assertEqual(ledger["r1_status"], "numerical_failed")
        self.assertEqual(frame["r1_status"], "numerical_failed")
        self.assertFalse(ledger["budget_approved"])
        self.assertFalse(frame["budget_approved"])
        self.assertFalse(ledger["g6_acceptance"])
        self.assertEqual(ledger["slot_set"]["total_slots"], 120)
        self.assertEqual(ledger["counts"]["slots_with_numeric_budget"], 0)
        self.assertEqual(ledger["counts"]["slots_approved"], 0)
        self.assertEqual(frame["counts"]["frame_bound"], 25)
        self.assertEqual(frame["counts"]["datum_bound"], 10)
        for key, value in sorted(ledger["counts"].items()):
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            with self.subTest(ledger_count=key):
                self.assertIn("%s=%d" % (key, value), DOC_TEXT)
        for key, value in sorted(frame["counts"].items()):
            if key == "slots_total" or isinstance(value, bool) or not isinstance(value, int):
                continue
            with self.subTest(frame_count=key):
                self.assertIn("%s=%d" % (key, value), DOC_TEXT)
        self.assertIn("slot_count=%d" % frame["slot_count"], DOC_TEXT)


class TestSourcePins(unittest.TestCase):
    """Exactly six tracked source pins, hash-bound and HEAD-blob bound."""

    def test_six_sources_hashed_and_sized(self):
        self.assertEqual(len(PINNED_SOURCES), 6)
        for rel, sha, size in PINNED_SOURCES:
            with self.subTest(path=rel):
                data = (ROOT / rel).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), sha)
                self.assertEqual(len(data), size)
                self.assertIn("| `%s` | %d | `%s` |" % (rel, size, sha), DOC_TEXT)

    def test_six_sources_tracked_at_head_blob_matches(self):
        for rel, sha, size in PINNED_SOURCES:
            with self.subTest(path=rel):
                listed, listing = _git_text(["ls-tree", "-r", "--name-only", "HEAD", "--", rel])
                self.assertEqual(listed.returncode, 0, listing)
                self.assertIn(rel, listing.splitlines(), "not tracked at HEAD: " + rel)
                shown = _git(["show", "HEAD:" + rel])
                self.assertEqual(shown.returncode, 0, "git show HEAD:%s failed" % rel)
                blob = shown.stdout
                self.assertEqual(hashlib.sha256(blob).hexdigest(), sha)
                self.assertEqual(len(blob), size)
                self.assertEqual(blob, (ROOT / rel).read_bytes(),
                                 "worktree bytes drifted from the HEAD blob: " + rel)

    def test_pin_set_is_exactly_six_tracked_sources_and_no_sampling_dep(self):
        self.assertEqual(len(set(PINNED_PATHS)), 6)
        for rel in PINNED_PATHS:
            with self.subTest(path=rel):
                self.assertNotIn("sampling", rel.lower())
                self.assertIn("`%s`" % rel, DOC_TEXT)
        pattern = r'[^\s`">]*sampling[^\s`"<]*\.(?:md|json|py|csv|slx)'
        self.assertEqual(re.findall(pattern, DOC_TEXT), [],
                         "no untracked reference-sampling document may be a dependency")
        for rel in CANDIDATES:
            self.assertNotIn("sampling", rel.lower())


class TestPreflightOrder(unittest.TestCase):
    """The documented preflight order must match the implemented call order."""

    def test_doc_preflight_order_matches_entry_source(self):
        self.assertEqual(len(SOURCE_STEPS), len(DOC_STEP_TOKENS))
        body = _run_body()
        positions = []
        for label, pattern in SOURCE_STEPS:
            index = body.find(pattern)
            self.assertGreaterEqual(index, 0, "source step missing: %s (%s)" % (label, pattern))
            positions.append(index)
        self.assertTrue(all(b > a for a, b in zip(positions, positions[1:])),
                        "the implemented run() call order changed: %r" % (positions,))
        section = _doc_section("## 1.", "## 2.")
        cursor = -1
        for token in DOC_STEP_TOKENS:
            found = section.find(token, cursor + 1)
            self.assertGreaterEqual(
                found, 0, "documented preflight step missing or out of order: " + token)
            cursor = found


class TestFrozenConstants(unittest.TestCase):
    """The documented constants must match the implemented entry module."""

    def test_entry_frozen_constants_match_doc(self):
        self.assertEqual(ENTRY.ARRAY_LENGTHS, {"Vehicle60": 60, "Sensor30": 30, "GPS30": 30})
        self.assertEqual(ENTRY.TOTAL_SCALARS, 120)
        self.assertEqual(ENTRY.SAMPLES, 501)
        self.assertEqual(ENTRY.TIME_STEP_S, 0.001)
        self.assertEqual(ENTRY.FROZEN_METRIC, "abs_le_a_plus_r_absref_with_rms_cap_v1")
        self.assertEqual(
            {ENTRY.STATUS_BLOCKED, ENTRY.STATUS_INVALID_RUN,
             ENTRY.STATUS_NUMERICAL_FAILED, ENTRY.STATUS_DECLARED_CASES_PASS},
            {"blocked", "invalid_run", "numerical_failed", "declared_cases_pass"})
        for literal in (ENTRY.FROZEN_METRIC, "0.001", "501", "120", "numerical_failed",
                        "declared_cases_pass", "invalid_run",
                        "wksim-e0-fixed-reference-native-preservation-v1"):
            with self.subTest(literal=literal):
                self.assertIn(literal, DOC_TEXT)


class TestCommandShape(unittest.TestCase):
    """Documented future command shapes must match the entry CLI and argv builders."""

    def test_authorized_command_shape_matches_entry(self):
        for token in ("python tools/run_e0_same_source_conformance.py <新合同路径>",
                      "--output <新结果路径>", "--evidence-dir <新证据目录>"):
            with self.subTest(token=token):
                self.assertIn(token, DOC_TEXT)
        self.assertIn("必须指向**新**的同源合同文件", DOC_TEXT)
        for token in ("parser.add_argument('contract'", "--output", "--evidence-dir"):
            with self.subTest(source=token):
                self.assertIn(token, ENTRY_TEXT)

    def test_normal_and_native_command_shapes_match_source(self):
        for token in ("-wait -sd", "-batch export_model_reference"):
            with self.subTest(doc=token):
                self.assertIn(token, DOC_TEXT)
        for token in ("timeout --signal=TERM --kill-after=5s", "--record <wsl-input.csv>",
                      "wsl.exe -d"):
            with self.subTest(doc=token):
                self.assertIn(token, DOC_TEXT)
        for token in ("'-wait', '-sd', str(stage)", "'-batch', 'export_model_reference'",
                      "'timeout', '--signal=TERM', '--kill-after=5s'",
                      "'--record', wsl_input", "'wsl.exe', '-d'"):
            with self.subTest(source=token):
                self.assertIn(token, ENTRY_TEXT)


class TestEvidenceFields(unittest.TestCase):
    """Documented result.json / evidence fields must exist in the implementation."""

    def test_result_json_and_evidence_fields_documented(self):
        for field in RESULT_FIELDS + BLOCKED_FIELDS + SCALAR_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, DOC_TEXT)
                self.assertIn(field, ENTRY_TEXT)
        for artifact in EVIDENCE_ARTIFACTS:
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, DOC_TEXT)
                self.assertIn("'%s'" % artifact, ENTRY_TEXT)
        for artifact in ARRAY_F64_ARTIFACTS:
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, DOC_TEXT)
        self.assertIn("'.f64'", ENTRY_TEXT)


class TestBlockedBehaviour(unittest.TestCase):
    """Real fail-closed behavior of the entry: blocked, deterministic, no launch."""

    def test_missing_contract_blocks_before_any_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence"
            absent = Path(tmp) / "absent-contract.json"
            first = ENTRY.run(absent, evidence_dir=evidence)
            second = ENTRY.run(absent, evidence_dir=evidence)
            self.assertEqual(first["status"], ENTRY.STATUS_BLOCKED)
            self.assertEqual(first["status"], second["status"])
            self.assertEqual(first["blocking_reasons"], second["blocking_reasons"])
            self.assertTrue(first["blocking_reasons"])
            self.assertIn("not found", " ".join(first["blocking_reasons"]))
            for key in ("execution_attempted", "matlab_launched", "native_launched",
                        "physical_accuracy", "g6_acceptance"):
                with self.subTest(key=key):
                    self.assertFalse(first[key])
            self.assertFalse(evidence.exists(),
                             "no evidence directory may be created before a launch")

    def test_frozen_r1_contract_refused_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence"
            result = ENTRY.run(ROOT / R1_REL, evidence_dir=evidence)
            self.assertEqual(result["status"], ENTRY.STATUS_BLOCKED)
            self.assertTrue(any("frozen R1 contract" in reason
                                for reason in result["blocking_reasons"]),
                            result["blocking_reasons"])
            self.assertFalse(result["matlab_launched"])
            self.assertFalse(result["native_launched"])
            self.assertFalse(result["execution_attempted"])
            self.assertFalse(evidence.exists())

    def test_partial_budget_contract_blocks_with_reasons(self):
        contract = {
            "schema_version": 1,
            "contract_id": "wksim-e0-same-source-conformance-v1-probe",
            "status": "frozen",
            "identity": {
                "reference_revision": "e0-slx-11.8",
                "target_revision": "e0-native-11.8",
                "reference_engine": "MATLAB R2022b normal",
                "target_profile": "same-source-native",
                "slx": {"path": "x.slx", "sha256": "a" * 64},
                "init": {"path": "x_init.m", "sha256": "b" * 64},
            },
            "sampling": {
                "array_lengths": {"Vehicle60": 60, "Sensor30": 30, "GPS30": 30},
                "fixed_step_s": 0.001, "k_first": 0, "k_last": 500,
            },
            "observables": [{
                "observable": "velocity_ned", "source_mapping": "cpp:7865",
                "unit": "m/s", "frame": "NED", "datum": "origin",
                "sample_phase": "major_root_output",
                "metric": "abs_le_a_plus_r_absref_with_rms_cap_v1",
                "abs_budget": None, "rel_budget": None, "rms_budget": None,
                "derivation": "not_derived", "domain": "C0", "approval": "not_made",
                "contract_sha256": "c" * 64, "array": "Vehicle60", "indices": [3],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            contract_path = Path(tmp) / "probe-contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            evidence = Path(tmp) / "evidence"
            result = ENTRY.run(contract_path, evidence_dir=evidence)
            reasons = " ".join(result["blocking_reasons"])
            self.assertEqual(result["status"], ENTRY.STATUS_BLOCKED)
            self.assertIn("abs_budget", reasons)
            self.assertIn("coverage", reasons)
            self.assertIn("not_made", reasons)
            self.assertFalse(result["matlab_launched"])
            self.assertFalse(result["native_launched"])
            self.assertFalse(evidence.exists())

    def test_ready_blocked_rule_helper_is_fail_closed(self):
        result = ENTRY._result(ENTRY.STATUS_BLOCKED, ["probe"], physical_accuracy=False)
        self.assertFalse(result["physical_accuracy"])
        self.assertFalse(result["g6_acceptance"])
        self.assertFalse(result["execution_attempted"])
        self.assertFalse(result["matlab_launched"])
        self.assertFalse(result["native_launched"])
        self.assertEqual(result["blocking_reasons"], ["probe"])
        self.assertIn("scope", result)
        body = _run_body()
        self.assertLess(body.index("validate_contract(contract_path)"),
                        body.index("validate_execution(contract_path, contract)"),
                        "a blocked contract must be returned before the execution stage")


class TestWordingMutations(unittest.TestCase):
    """Negative mutations: the wording detectors must actually fail on bad input."""

    def test_wording_mutation_negatives_rejected(self):
        for token in ("numerical_failed", "#59", "#84", "G6", "Full", "not-closed"):
            mutated = DOC_TEXT.replace(token, "")
            with self.subTest(nonclosure_token=token):
                self.assertNotEqual(mutated, DOC_TEXT)
                self.assertTrue(detect_nonclosure(mutated))
        mutated = DOC_TEXT.replace(READINESS_GATES[1], "")
        self.assertNotEqual(mutated, DOC_TEXT)
        self.assertTrue(detect_ready_blocked_rule(mutated))
        mutated = DOC_TEXT.replace(FAIL_CLOSED_TOKEN, "全部成立")
        self.assertNotEqual(mutated, DOC_TEXT)
        self.assertTrue(detect_ready_blocked_rule(mutated))
        mutated = DOC_TEXT.replace("不是数值通过，也不是物理精度或 G6 通过",
                                   "是数值通过与物理精度通过")
        self.assertNotEqual(mutated, DOC_TEXT)
        self.assertTrue(detect_ready_blocked_rule(mutated))

    def test_forbidden_inference_mutations_rejected(self):
        mutations = (
            ("禁止从**已观测差值**", "可以从**已观测差值**"),
            ("禁止以 double **ULP**", "以 double **ULP**"),
            ("禁止用**噪声**", "用**噪声**"),
            ("禁止用 ODE4/**RK4**", "用 ODE4/**RK4**"),
            ("禁止把 **SITL**", "把 **SITL**"),
            ("禁止把**控制接缝**", "把**控制接缝**"),
        )
        for old, new in mutations:
            mutated = DOC_TEXT.replace(old, new)
            with self.subTest(prohibition=old):
                self.assertNotEqual(mutated, DOC_TEXT)
                self.assertTrue(detect_forbidden_inference(mutated))


class TestAncestry(unittest.TestCase):
    """Ancestry gates for the named commits; no exact-HEAD pin anywhere."""

    def test_named_ancestors_of_head(self):
        for sha in ANCESTOR_COMMITS:
            with self.subTest(sha=sha):
                self.assertTrue(is_ancestor(sha), "not an ancestor of HEAD: " + sha)

    def test_non_ancestor_and_invalid_object_rejected(self):
        self.assertFalse(is_ancestor("0" * 40), "an invalid object name must be rejected")
        self.assertFalse(is_ancestor("f" * 40), "an invalid object name must be rejected")
        done = _git(["merge-base", "--is-ancestor", "0" * 40, "HEAD"])
        self.assertNotEqual(done.returncode, 0)

    def test_no_exact_head_pin(self):
        head, head_text = _git_text(["rev-parse", "HEAD"])
        self.assertEqual(head.returncode, 0)
        current = head_text.strip()
        self.assertRegex(current, r"^[0-9a-f]{40}$")
        self.assertNotIn(current, TEST_SOURCE, "the current HEAD must not be pinned")
        self.assertNotIn(current, DOC_TEXT, "the document must not pin the current HEAD")
        self.assertIsNone(
            re.search(r"(?m)^(PINNED_HEAD|HEAD_SHA|EXACT_HEAD)\s*=", TEST_SOURCE),
            "a pinned-HEAD constant must not be introduced")
        self.assertIn("不绑定 HEAD 精确值", DOC_TEXT)


class TestIndexModes(unittest.TestCase):
    """Candidate presence and the two run modes; the real index is never used."""

    def test_normal_mode_makes_no_index_touching_git_call(self):
        if current_mode() != MODE_NORMAL:
            self.skipTest("only meaningful in %s mode" % MODE_NORMAL)
        for rel in CANDIDATES:
            with self.subTest(path=rel):
                self.assertTrue((ROOT / rel).is_file())
        self.assertEqual(INDEX_TOUCHING_CALLS, [],
                         "no index-touching git call is allowed in normal mode")

    def test_external_index_stages_exactly_two_candidates(self):
        if current_mode() != MODE_EXTERNAL:
            self.skipTest("only meaningful in %s mode" % MODE_EXTERNAL)
        index_env = os.environ.get("GIT_INDEX_FILE")
        if not index_env:
            self.fail("%s mode requires GIT_INDEX_FILE pointing to a repo-external index"
                      % MODE_EXTERNAL)
        index_path = Path(index_env).resolve()
        self.assertNotIn(ROOT.resolve(), index_path.parents,
                         "GIT_INDEX_FILE must be outside the repository")
        self.assertNotEqual(index_path, ROOT.resolve() / ".git" / "index",
                            "the shared real index must never be used")
        done = _git(["ls-files", "-s", "-z"], extra_env={"GIT_INDEX_FILE": str(index_path)})
        self.assertEqual(done.returncode, 0, done.stderr)
        entries = [entry for entry in done.stdout.decode("utf-8").split("\x00") if entry]
        self.assertEqual(len(entries), 2,
                         "exactly the two candidates must be staged, got %r" % (entries,))
        parsed = {}
        for entry in entries:
            meta, path = entry.split("\t", 1)
            mode, sha, stage = meta.split()
            parsed[path] = (mode, sha, stage)
        self.assertEqual(set(parsed), set(CANDIDATES))
        for rel in CANDIDATES:
            data = (ROOT / rel).read_bytes()
            mode, sha, stage = parsed[rel]
            with self.subTest(path=rel):
                self.assertEqual(mode, "100644")
                self.assertEqual(stage, "0")
                self.assertEqual(sha, blob_sha1(data))


if __name__ == "__main__":
    unittest.main(verbosity=2)
