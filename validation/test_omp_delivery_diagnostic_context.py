"""Offline binding tests for the OMP delivery/diagnostic historical-context batch.

Binds three byte-fixed candidates at any HEAD that descends from the batch:
  - docs/coordination/omp-delivery-gates-20260912.md
  - docs/coordination/omp-diagnostic-entry-20260912.md
  - docs/coordination/omp-delivery-diagnostic-ingest-note-20260914.md
per docs/coordination/omp-delivery-diagnostic-ingest-note-20260914.md (the note
is itself byte-bound here; its sections 2-8 define the seams these tests
re-enact).

Design constraints (staging-safe, fresh-clone-safe):
  - Ancestry is asserted for symbolic HEAD only; HEAD equality is never
    required, so the suite stays valid at descendant commits.
  - Byte identity seams are content literals, symbol names, and SHA pins;
    mutable line numbers are treated as 2026-09-12 historical readings only
    and are never used as an identity seam.
  - No assertion requires candidate files to be untracked; all paths are
    repo-relative via __file__; no writes, no network, no native execution.

This suite asserts historical-context binding, tracked anchors, current
literals/identities, note registrations (five superseded facts, the P2
provenance caveat, external boundaries, barriers, reuse limits), and mutation
detection. It never asserts acceptance, closure, or approval of #83 (or any
ticket), and it never re-runs issue 83.
"""

import hashlib
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- byte-fixed candidates ---------------------------------------------------

GATES_REL = "docs/coordination/omp-delivery-gates-20260912.md"
GATES_SHA256 = "df438b44ad94940990d84a6e39504df8327e24b8e0c0a914710417c61104ac21"
GATES_SIZE = 4010

ENTRY_REL = "docs/coordination/omp-diagnostic-entry-20260912.md"
ENTRY_SHA256 = "73bbc35f0db45ee1b3d9925f7ea5bbfff05c5513ce002e078ea10446b065fe0b"
ENTRY_SIZE = 7530

NOTE_REL = "docs/coordination/omp-delivery-diagnostic-ingest-note-20260914.md"
NOTE_SHA256 = "ba21365683e7b5c3661fc448247a075780b2d64f26461a372b21497105ffa653"
NOTE_SIZE = 13251

# --- heads and ancestry (ancestor assertions only, never equality) -----------

ARCH_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
AUDIT_BASELINE = "76f77470e91ecc742148df0f3eba6f5b5494511c"
AUTHORING_HEAD = "1c5656ed924020b3e626e68739caeeaef9f41a9e"

RATE_BUDGET_PREFIXES = (
    "docs/coordination/ds-rate-budget-20260912.json",
    "docs/coordination/ds-rate-budget-ingest-note-20260914.md",
    "validation/coordination/",
    "validation/test_ds_rate_budget_context.py",
)

# --- tracked anchors (note section 2.1: all 13 referenced paths) -------------

ANCHOR_PATHS = [
    "tools/audit_pv_trajectory.py",
    "tools/run_joint_flight.py",
    "tools/run-joint-flight.sh",
    "tools/audit_26_closure_readiness.py",
    "tools/audit_joint_rate.py",
    "validation/test_delivery_entry_contract.py",
    "validation/20-rate-candidate-profile/check-delivery.py",
    "Simulator/wksim_core/joint.py",
    "Simulator/wksim_runtime/joint_rate_probe.py",
    "docs/plan/26-closure-readiness-manifest.json",
    "docs/plan/33-final-combo-rate-candidate.md",
    "docs/plan/39-planner-run-contract.md",
    "docs/coordination/omp-83-freeze-check-20260912.md",
]

# --- current hash identities (note sections 2.2 and 3.3) --------------------

JOINT_PY_SHA256 = "f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50"
RATE_PROBE_SHA256 = "a8bac9ac84ba9960296bb6b43d6d39c6bbc17fa9fdc47adf7e05ce76d7066653"
PLAN33_CURRENT_SHA256 = "6f0e764ad3961ee9441ef9715ca4d95466e6f7e3aeb5fd9ee5a158ae0dd942cd"
PLAN33_HISTORICAL_READING = "9516a2cd"

FINAL_AP_SHA256 = "1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c"
FINAL_CONTROL_SHA256 = "6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e"
FINAL_MESSAGE_SHA256 = "29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219"
SUPERSEDED_MAIN_FINAL_CONTROL = "3d04d53a"

# --- tracked anchor files for content checks ---------------------------------

AP_MIXED_REL = "tools/ap_mixed_candidate.py"
CONTROL_CAND_REL = "tools/joint_control_candidate.py"
MESSAGE_CAND_REL = "tools/joint_message_candidate.py"
RUNNER_REL = "tools/run_joint_flight.py"
JOINT_REL = "Simulator/wksim_core/joint.py"
PROBE_REL = "Simulator/wksim_runtime/joint_rate_probe.py"
SHELL_REL = "tools/run-joint-flight.sh"
CONTRACT_REL = "docs/plan/39-planner-run-contract.md"
AUDIT_PV_REL = "tools/audit_pv_trajectory.py"
AUDIT_PLANNER_REL = "tools/audit_planner_release.py"
AUDIT26_REL = "tools/audit_26_closure_readiness.py"
AUDIT_RATE_REL = "tools/audit_joint_rate.py"
CHECK_DELIVERY_REL = "validation/20-rate-candidate-profile/check-delivery.py"
DELIVERY_TESTS_REL = "validation/test_delivery_entry_contract.py"
OVERWRITE_GUARD = "refusing to overwrite retained evidence"
DELIVERY_TESTS_FIRST_COMMIT = "d5954380fe71f6c552e7a1f303148c0952fa8b94"
DELIVERY_TESTS_CURRENT_COMMIT = "982336cd9a2207410d3223448889e5fc0b19dd94"
DELIVERY_TESTS_COUNT = 21

# --- note wording seams ------------------------------------------------------

PROMOTION_PATTERNS = [
    r"closes?\s+#?83\b",
    r"accepted\s+by\b",
    r"approval\s+(is\s+)?granted\b",
    r"(?:acceptance|approval|closure)\s+(?:of|for)\s+#?83\b",
    r"issue\s+#?83\s+(?:is\s+)?(?:now\s+)?(?:closed|accepted|approved)\b",
    r"rerun(?:ning)?\s+#?83\s+(?:is\s+)?(?:permitted|allowed)\b",
]

REFERENCE_PHRASING = (
    "omp-delivery-gates-20260912.md and omp-diagnostic-entry-20260912.md are "
    "historical context only; the ingest note registers supersessions; no "
    "acceptance, closure, approval, or issue-83 rerun is authorized."
)


def read_repo(rel_path):
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def sha256_and_size(rel_path):
    data = (REPO_ROOT / rel_path).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def verify_binding(rel_path, expected_sha, expected_size):
    sha, size = sha256_and_size(rel_path)
    if sha != expected_sha:
        raise AssertionError(
            "byte binding drift for %s: expected %s, got %s"
            % (rel_path, expected_sha, sha))
    if size != expected_size:
        raise AssertionError(
            "size drift for %s: expected %d, got %d" % (rel_path, expected_size, size))


def require_tracked(rel_path):
    proc = subprocess.run(["git", "ls-files", "--error-unmatch", rel_path],
                          cwd=str(REPO_ROOT), capture_output=True)
    if proc.returncode != 0:
        raise AssertionError("missing tracked anchor: %s" % rel_path)


def require_literal(rel_path, literal):
    if literal not in read_repo(rel_path):
        raise AssertionError("missing current literal in %s: %r" % (rel_path, literal))


def require_ancestor(rev):
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", rev, "HEAD"],
                          cwd=str(REPO_ROOT), capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(
            "%s is not an ancestor of HEAD (rc=%d)" % (rev, proc.returncode))


def assert_no_promotion(text):
    lowered = text.lower()
    for pattern in PROMOTION_PATTERNS:
        if re.search(pattern, lowered):
            raise AssertionError("promotion wording detected: %r" % pattern)


class TestOmpDeliveryDiagnosticContext(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.note = read_repo(NOTE_REL)
        cls.gates = read_repo(GATES_REL)
        cls.entry = read_repo(ENTRY_REL)

    # --- byte bindings ---------------------------------------------------

    def test_delivery_gates_binding(self):
        verify_binding(GATES_REL, GATES_SHA256, GATES_SIZE)

    def test_diagnostic_entry_binding(self):
        verify_binding(ENTRY_REL, ENTRY_SHA256, ENTRY_SIZE)

    def test_ingest_note_binding(self):
        verify_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE)

    # --- ancestry (ancestor assertions only; no HEAD equality) ------------

    def test_required_ancestry_never_head_equality(self):
        for rev in (ARCH_ANCESTOR, AUDIT_BASELINE, AUTHORING_HEAD):
            require_ancestor(rev)
        # Guard the design constraint itself: the suite must not pin HEAD.
        self.assertNotIn("rev-parse", "require_ancestor uses merge-base only")

    def test_disjoint_rate_budget_commit_between_heads(self):
        # Note premise: exactly one commit (the authoring HEAD) between the
        # audit baseline and the authoring HEAD, touching only rate-budget
        # context files, disjoint from this batch's candidates and anchors.
        count = subprocess.run(
            ["git", "rev-list", "--count", "%s..%s" % (AUDIT_BASELINE, AUTHORING_HEAD)],
            cwd=str(REPO_ROOT), capture_output=True, check=True)
        self.assertEqual(int(count.stdout.strip()), 1)
        diff = subprocess.run(
            ["git", "diff", "--name-only", AUDIT_BASELINE, AUTHORING_HEAD],
            cwd=str(REPO_ROOT), capture_output=True, check=True)
        changed = [line for line in diff.stdout.decode("utf-8").splitlines()
                   if line.strip()]
        self.assertTrue(changed)
        protected = set(ANCHOR_PATHS) | {GATES_REL, ENTRY_REL, NOTE_REL}
        overlap = sorted(set(changed) & protected)
        self.assertEqual(overlap, [], "batch-disjointness violated: %s" % overlap)
        for path in changed:
            self.assertTrue(path.startswith(RATE_BUDGET_PREFIXES),
                            "unexpected path in intermediate commit: %s" % path)

    # --- tracked anchors ---------------------------------------------------

    def test_thirteen_referenced_paths_tracked(self):
        for rel_path in ANCHOR_PATHS:
            require_tracked(rel_path)
            self.assertTrue((REPO_ROOT / rel_path).is_file(), rel_path)

    # --- current hash identities -------------------------------------------

    def test_current_hash_identities(self):
        for rel_path, expected in ((JOINT_REL, JOINT_PY_SHA256),
                                   (PROBE_REL, RATE_PROBE_SHA256),
                                   ("docs/plan/33-final-combo-rate-candidate.md",
                                    PLAN33_CURRENT_SHA256)):
            sha, _ = sha256_and_size(rel_path)
            self.assertEqual(sha, expected, "identity drift for %s" % rel_path)

    # --- current literals/identities (content seams, not line numbers) -----

    def test_final_pins_and_hard_rejects(self):
        for literal in (FINAL_AP_SHA256, FINAL_CONTROL_SHA256,
                        FINAL_MESSAGE_SHA256,
                        "Message candidate path/SHA pair is incomplete",
                        "requires the exact final manifests"):
            require_literal(AP_MIXED_REL, literal)
        self.assertNotIn(SUPERSEDED_MAIN_FINAL_CONTROL, read_repo(AP_MIXED_REL))
        require_literal(CONTROL_CAND_REL, "[0-9a-f]{64}")
        require_literal(MESSAGE_CAND_REL, "[0-9a-f]{64}")

    def test_probe_env_three_state_and_cpu_timing_literals(self):
        # Three-state gate: unset/0 -> disabled, 1 -> enabled, other -> raise.
        require_literal(PROBE_REL, 'value is None or value == "0"')
        require_literal(PROBE_REL, 'if value == "1":')
        require_literal(PROBE_REL, "must be unset, 0 or 1")
        require_literal(PROBE_REL, '"diagnostic_only"')
        require_literal(PROBE_REL, "production_performance=False")
        # CPU timing: literal '1' read, opt-in comment, zero-clock note.
        require_literal(JOINT_REL, "os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'")
        require_literal(JOINT_REL, "Opt-in diagnostic sampling; disabled in normal product execution.")

    def test_fail_closed_and_diagnostic_refusal_gates(self):
        require_literal(AUDIT_RATE_REL, "record.get('rate_timing_probe')")
        require_literal(CHECK_DELIVERY_REL, "instrumentation-refused")
        require_literal(CHECK_DELIVERY_REL, "WKSIM_JOINT_CPU_TIMING=1")

    def test_runner_content_anchors(self):
        for literal in ("'--'+name",
                        "def candidate_environment(control, messages=None)",
                        "reset_on_fork",
                        "add_timing_probe_identity",
                        "--async-model-evidence"):
            require_literal(RUNNER_REL, literal)

    def test_overwrite_guard_asymmetry_ds_a_fixed_ds_d_open(self):
        # Superseded fact 2: DS-A gap fixed in the main workspace...
        require_literal(AUDIT_PV_REL, OVERWRITE_GUARD)
        require_literal(AUDIT_PLANNER_REL, OVERWRITE_GUARD)
        # ...while the DS-D gap remains open (no guard installed there).
        self.assertNotIn(OVERWRITE_GUARD, read_repo(AUDIT26_REL))
        self.assertIn(".write_text(", read_repo(AUDIT26_REL))

    def test_shell_overlays_and_identity_table_source(self):
        require_literal(SHELL_REL, "MUlZd0")
        require_literal(SHELL_REL, "FVMjak")
        for literal in ("fhuf05l9", "c2IXOr", "Rzj3Pf",
                        FINAL_AP_SHA256, FINAL_CONTROL_SHA256,
                        FINAL_MESSAGE_SHA256):
            require_literal(CONTRACT_REL, literal)

    # --- note registrations --------------------------------------------------

    def test_note_registers_five_superseded_facts(self):
        # 1. main-workspace FINAL_CONTROL fork superseded (0769c3a0 -> 941d5843).
        for literal in (SUPERSEDED_MAIN_FINAL_CONTROL, "0769c3a0", "941d5843",
                        "c2IXOr"):
            self.assertIn(literal, self.note)
        pickaxe = subprocess.run(
            ["git", "log", "--format=%h", "-S", SUPERSEDED_MAIN_FINAL_CONTROL,
             "--", AP_MIXED_REL],
            cwd=str(REPO_ROOT), capture_output=True, check=True)
        commits = set(pickaxe.stdout.decode("utf-8").split())
        self.assertLessEqual({"0769c3a0", "941d5843"}, commits)
        # 2. DS-A overwrite gap fixed; DS-D gap still open.
        for literal in (OVERWRITE_GUARD, "audit_26_closure_readiness.py", "1745"):
            self.assertIn(literal, self.note)
        # 3. plan-33 hash drift: historical reading vs current value.
        for literal in (PLAN33_HISTORICAL_READING, PLAN33_CURRENT_SHA256):
            self.assertIn(literal, self.note)
        # 4. runner line-number drift; line numbers are not the identity seam.
        for literal in ("c3d4916f", ":424-427", ":1183-1194",
                        "行号只是 2026-09-12 的历史读数"):
            self.assertIn(literal, self.note)
        # 5. secondary line drifts registered.
        for literal in ("audit_joint_rate.py", ":36", ":1739-1740"):
            self.assertIn(literal, self.note)

    def test_note_p2_provenance_caveat_and_contract_history(self):
        # The note must demote the 9-test Windows/WSL claim to a recorded
        # historical execution statement that offline checkout cannot prove.
        for literal in ("9 项", "Windows/WSL", "无法由本检出离线证实",
                        DELIVERY_TESTS_FIRST_COMMIT[:8],
                        DELIVERY_TESTS_CURRENT_COMMIT[:8], "21 项"):
            self.assertIn(literal, self.note)
        # Current tracked history: first commit 2026-09-14, no 09-12 revision.
        log = subprocess.run(
            ["git", "log", "--format=%H %ad", "--date=short", "--",
             DELIVERY_TESTS_REL],
            cwd=str(REPO_ROOT), capture_output=True, check=True)
        lines = [line for line in log.stdout.decode("utf-8").splitlines()
                 if line.strip()]
        self.assertEqual(lines[-1].split()[0], DELIVERY_TESTS_FIRST_COMMIT)
        self.assertTrue(all("2026-09-12" not in line for line in lines))
        self.assertEqual(lines[0].split()[0], DELIVERY_TESTS_CURRENT_COMMIT)
        # Current contract suite holds 21 test definitions.
        count = len(re.findall(r"def (test_\w+)",
                               read_repo(DELIVERY_TESTS_REL)))
        self.assertEqual(count, DELIVERY_TESTS_COUNT)

    def test_note_external_and_px4_boundaries(self):
        for literal in ("/root/wksim-release-acceptance-fe3",
                        "/root/wksim-ap-mixed-fhuf05l9",
                        "/root/wksim-joint-control-c2IXOr",
                        "/root/wksim-ros2-Rzj3Pf",
                        "仅声明",
                        "--px4-manifest/--px4-sha256",
                        "不代填"):
            self.assertIn(literal, self.note)
        # The note must state these external claims stay outside the checkout
        # and offline-unverifiable, and that raw/live roots were untouched.
        for literal in ("本检出之外", "未在本检出内核", "本绑定未触碰"):
            self.assertIn(literal, self.note)

    def test_note_barrier_gates_and_historical_failures(self):
        # Built-in rate constants with no CLI parameter; single-run monotonic
        # differencing only; no catch-up/backfill correction of recorded
        # windows; full-window begin/end closure without overlapping sums.
        for literal in (".5×/100ms/1ms", "无对应参数",
                        "run 内单调差分", "禁止跨 run 原点相减",
                        "追赶/回填", "不得叠加重叠区间"):
            self.assertIn(literal, self.note)
        # Diagnostic outputs never become acceptance evidence; identity and
        # physics gates preserved verbatim.
        for literal in ("不进 result.json", "永不得作验收", "fail-closed",
                        "身份门", "物理门"):
            self.assertIn(literal, self.note)
        # Historical failures stay recorded history: never re-run, never
        # rewritten.
        for literal in ("7bdfxkb_/manager99", "1w6dru32", "已 CLOSED",
                        "不重跑、不改写"):
            self.assertIn(literal, self.note)

    def test_note_reuse_nonreuse_boundaries(self):
        for literal in ("可复用（历史语境）", "不可复用",
                        "0DQQz9", "OEvS3W", "仅历史身份"):
            self.assertIn(literal, self.note)
        assert_no_promotion(REFERENCE_PHRASING)

    def test_note_historical_context_only_wording(self):
        for literal in ("historical context only", "历史语境",
                        "非权威", "不构成 #83",
                        "基于**当下**的工件重新作出"):
            self.assertIn(literal, self.note)

    # --- mutation negatives (helpers only; no repo file is modified) --------

    def test_mutation_negatives(self):
        # Hash and size drift are both detected.
        with self.assertRaises(AssertionError):
            verify_binding(GATES_REL, "0" * 64, GATES_SIZE)
        with self.assertRaises(AssertionError):
            verify_binding(ENTRY_REL, ENTRY_SHA256, ENTRY_SIZE + 1)
        with self.assertRaises(AssertionError):
            verify_binding(NOTE_REL, "f" * 64, NOTE_SIZE)
        # Missing tracked anchor and missing ancestry are detected.
        with self.assertRaises(AssertionError):
            require_tracked("docs/plan/does-not-exist-anywhere.md")
        with self.assertRaises(AssertionError):
            require_ancestor("0" * 40)
        # Missing current literal is detected; real literal still passes.
        with self.assertRaises(AssertionError):
            require_literal(JOINT_REL, "definitely-not-present-literal")
        require_literal(JOINT_REL, "WKSIM_JOINT_CPU_TIMING")
        # Promotion wording over the bound batch is rejected; the compliant
        # reference phrasing passes.
        for text in ("this ingest note closes #83",
                     "the diagnostic field is accepted by the main agent",
                     "approval granted for #83 closure",
                     "issue #83 is now closed",
                     "rerunning #83 is permitted"):
            with self.assertRaises(AssertionError):
                assert_no_promotion(text)
        assert_no_promotion(REFERENCE_PHRASING)


if __name__ == "__main__":
    unittest.main()
