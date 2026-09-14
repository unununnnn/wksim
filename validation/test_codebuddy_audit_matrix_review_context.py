"""Offline binding tests for the CodeBuddy audit-matrix historical-context batch.

Binds two byte-fixed candidates as **historical context only**:
  - docs/coordination/codebuddy-audit-matrix-review-20260912.md
  - docs/coordination/codebuddy-audit-matrix-review-ingest-note-20260914.md
per the ingest note (its sections 2-8 define the seams these tests re-enact).

Scope guard: this suite verifies only that the 2026-09-12 CodeBuddy review of
the frozen release auditor and the probe-run-02 one-positive/four-negative
matrix is retained as readable historical context with recomputable tracked
anchors. It grants no issue acceptance/approval/closure, no #83 rerun, no
current G0-G6/Full gate, no native result, and no flight evidence. Issue 83 is
CLOSED/PASS and is never rerun here; #84/G6/Full remain incomplete as far as
this suite is concerned.

Design constraints (staging-safe, fresh-clone-safe):
  - Git topology asserts only ancestry: f333316e (architecture), e897fb8e
    (review-time frozen auditor blob), 5ec3d389 (probe tool first commit) and
    09b9729e (auditor drift commit) must be ancestors of the symbolic HEAD.
    HEAD equality is never required and current HEAD is never bound, so the
    suite stays valid at descendant commits.
  - Tracked-anchor checks read the HEAD tree (`git ls-tree` / `git cat-file`),
    which is index-independent; they therefore pass both in the normal mode
    and under a temporary GIT_INDEX_FILE. The staged-index check is a
    lifecycle-safe candidate-subset verifier: every candidate path (review,
    note, this test) must be present exactly once at mode 100644/stage 0
    with a blob identical to the working bytes, while additional
    independent-review/manifest paths are permitted. Exact staged-batch
    equality is enforced by the manifest/final verifier, not by this
    candidate suite.
  - The test file locates itself via __file__; no cwd dependence, no writes,
    no network, no native execution.
  - In-memory mutation negatives run through the same production helpers that
    the positive assertions use.
"""

import hashlib
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- byte-fixed candidates ----------------------------------------------------

REVIEW_REL = "docs/coordination/codebuddy-audit-matrix-review-20260912.md"
REVIEW_SHA256 = "fbb2568bea73167997ee62782fb71f1aba98dd54cd3e2f99108c591f41abcbf1"
REVIEW_SIZE = 5805

NOTE_REL = ("docs/coordination/"
            "codebuddy-audit-matrix-review-ingest-note-20260914.md")
NOTE_SHA256 = "7fa1bdcc2c210e3e6e3fbe76be1dded409abd793f66c2b643753712962b8f22c"
NOTE_SIZE = 16071

SELF_REL = str(Path(__file__).resolve().relative_to(REPO_ROOT)).replace(
    "\\", "/")
CANDIDATE_PATHS = (REVIEW_REL, NOTE_REL, SELF_REL)

# --- ancestry (ancestor assertions only; current HEAD is never bound) ---------

ARCH_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
FROZEN_AUDITOR_COMMIT = "e897fb8e"  # blob == review-time tools/audit_planner_release.py
PROBE_TOOL_COMMIT = "5ec3d389"     # first tracked probe tool (49128 B)
AUDITOR_DRIFT_COMMIT = "09b9729e"  # current auditor (post-review fix)

FROZEN_AUDITOR_REV = FROZEN_AUDITOR_COMMIT + ":tools/audit_planner_release.py"

# --- tracked audit-matrix directory (five files) ------------------------------

MATRIX_DIR = "validation/39-planner-flight/audit-matrix-20260912"
MAIN_VERIFICATION_REL = MATRIX_DIR + "/main-verification.json"
MAIN_VERIFICATION_SHA256 = ("d4624624be96c67d173191fc0c2025832887701019d6d13d"
                            "12df055f6c8953d7")
MAIN_VERIFICATION_SIZE = 785
PROBE_EXECUTED_REL = MATRIX_DIR + "/probe-executed.py"
PROBE_EXECUTED_SHA256 = ("92a83f4e593c1d399722a3dc57862da902b374872d475bc9531"
                         "31c6503d65815")
PROBE_EXECUTED_SIZE = 41773
PROBE_REPORT_REL = MATRIX_DIR + "/probe-report.json"
PROBE_REPORT_SHA256 = ("4b21beca2a755992f3d76be514c32e5ea3f291a1695856d4de15c"
                       "72f6f42c496")
PROBE_REPORT_SIZE = 95429
AUDITOR_EXECUTED_REL = MATRIX_DIR + "/auditor-executed.py"
AUDITOR_EXECUTED_SHA256 = ("e8d33c5d6562f75cb3f3e5baacf33737af91281d646fefe0c"
                           "c5db369d374177e")
AUDITOR_EXECUTED_SIZE = 24691
PROBE_LOG_REL = MATRIX_DIR + "/probe.log"
PROBE_LOG_SHA256 = ("a3d164a011a5f19561211465d5fa2014e5db2e489c4af41710817428"
                    "0a075b07")
PROBE_LOG_SIZE = 1566

RECORDED_AUDITOR_SHA256 = AUDITOR_EXECUTED_SHA256
RECORDED_PROBE_SHA256 = PROBE_EXECUTED_SHA256
RECORDED_SOURCE_REPORT_SHA256 = PROBE_REPORT_SHA256

# --- current tracked tools (drift-registered states) --------------------------

CURRENT_AUDITOR_REL = "tools/audit_planner_release.py"
CURRENT_AUDITOR_SHA256 = ("bd90c75a03fbc1f4e95c7b56ead58732b3efc66ce6ecc4144f"
                          "4438b471a2eaa5")
CURRENT_AUDITOR_SIZE = 25573

CURRENT_PROBE_REL = "tools/probe_release_audit_integrity.py"
CURRENT_PROBE_SHA256 = ("51342c48d1f7550fa2e353e107ec2a1005add409b514f469285d"
                        "fc5381209a97")
CURRENT_PROBE_SIZE = 49128

# --- F4 content anchors (current tracked sources) -----------------------------

TRANSPORT_NODE_REL = "Simulator/wksim_runtime/planner_transport_node.py"
TRANSPORT_NODE_SHA256 = ("ffc2964393eb67a5f0e3e5335d003e28241103e0070b762a876"
                         "41e03998489ab")
TRANSPORT_NODE_SIZE = 29180
TRAJECTORY_BRIDGE_REL = "Simulator/wksim_runtime/trajectory_bridge.py"
TRAJECTORY_BRIDGE_SHA256 = ("18ce768ab4b2f769b7a2a2fc708e7197e444057ee322e7b9"
                            "379e60e5ce3c969f")
TRAJECTORY_BRIDGE_SIZE = 19902
CONTROL_NODE_REL = "ros2/src/prometheus_control/prometheus_control/node.py"
CONTROL_NODE_SHA256 = ("fd9176b8ef2bbe6b3334eb7054b955d7a22f351992b6b3d7b2f67"
                       "fd68aca2a9a")
CONTROL_NODE_SIZE = 52036
SESSION_REL = "ros2/src/prometheus_control/prometheus_control/session.py"
SESSION_SHA256 = ("da64efa299288738d4520c6a23834c3201c34334f861a8de542fcaa919"
                  "30b126")
SESSION_SIZE = 5662

HANDOFF_REL = ("validation/39-planner-flight/release-bomvjsmg/arducopter/"
               "planner-release/planner-release-handoff.json")
HANDOFF_SHA256 = ("4f3e752e813c180b40e69da55ac58c058a998c5db043471be1336d652"
                  "34f0ca1")
HANDOFF_SIZE = 9497
HANDOFF_KEYS = {
    "adopted_request_high_water", "child", "child_returncode",
    "child_teardown", "deadline_ros_ns", "events", "expected_native_mode",
    "listen_port", "mode", "outcome", "planner_bound",
    "planner_loaded_modules", "timestamps", "transport_session_id",
    "verified_command_high_water", "verified_request_high_water",
}

DEDUP_TEST_REL = "validation/test_release_audit_integrity.py"

# --- run-02 data facts ----------------------------------------------------------

REQUIRED_NEGATIVES = ["command_payload_tamper", "ledger_command_gap",
                      "ledger_tail_truncation", "retained_source_change"]
EXTERNAL_ORIGINAL_REPORT = ("/root/wksim-release-acceptance-fe3/validation/"
                            "coordination/six-end-20260912/probe-run-02/"
                            "probe-report.json")
BASELINE_FILE_COUNT = 319
DERIVED_LISTED = 70
RESOLVED_UNIQUE = 66

# --- staging mode ----------------------------------------------------------------

# When GIT_INDEX_FILE points at a temporary index, tracked-anchor checks use
# the HEAD tree (index-independent) and the staged entries are verified with
# the candidate-subset verifier: all candidate paths present exactly once at
# stage 0 and blob-identical to the working bytes; extra
# independent-review/manifest paths are allowed (exact batch equality is
# enforced by the manifest/final verifier, not here).
STAGED_INDEX_FILE = os.environ.get("GIT_INDEX_FILE")


# --- helpers -------------------------------------------------------------------

def read_bytes(rel_path):
    return (REPO_ROOT / rel_path).read_bytes()


def sha256_and_size(rel_path):
    data = read_bytes(rel_path)
    return hashlib.sha256(data).hexdigest(), len(data)


def verify_binding(rel_path, expected_sha, expected_size):
    sha, size = sha256_and_size(rel_path)
    if sha != expected_sha:
        raise AssertionError(
            "byte binding drift for %s: expected %s, got %s"
            % (rel_path, expected_sha, sha))
    if size != expected_size:
        raise AssertionError(
            "size drift for %s: expected %d, got %d" % (rel_path, expected_size,
                                                        size))


def strict_loads(rel_path):
    """Strict JSON parse of a repo file: duplicate keys and nonfinite
    constants rejected."""
    return strict_loads_text(read_bytes(rel_path).decode("utf-8"))


def strict_loads_text(text):
    def object_pairs_hook(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise ValueError("duplicate JSON key: %r" % key)
            seen.add(key)
        return dict(pairs)

    def parse_constant(name):
        raise ValueError("nonfinite JSON constant: %s" % name)

    return json.loads(text, object_pairs_hook=object_pairs_hook,
                      parse_constant=parse_constant)


def git(args, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(["git"] + args, cwd=str(REPO_ROOT),
                          capture_output=True, env=env)


def require_tracked_in_head(rel_path):
    """Index-independent tracked check: the path must exist in the HEAD tree,
    and the working bytes must be byte-identical to the HEAD blob."""
    proc = git(["ls-tree", "HEAD", "--", rel_path])
    if proc.returncode != 0 or not proc.stdout.strip():
        raise AssertionError("path not tracked in HEAD tree: %s" % rel_path)
    fields = proc.stdout.decode("utf-8").split()
    blob_sha = fields[2]
    blob = git(["cat-file", "blob", "HEAD:" + rel_path])
    if blob.returncode != 0:
        raise AssertionError("HEAD blob unreadable: %s" % rel_path)
    if hashlib.sha256(blob.stdout).hexdigest() != sha256_and_size(rel_path)[0]:
        raise AssertionError(
            "working bytes differ from HEAD blob: %s" % rel_path)
    return blob_sha


def require_head_blob_sha256(rev_path, expected_sha256):
    """SHA256 of a blob reached via `<commit>:<path>` (drift-recovery anchor)."""
    blob = git(["cat-file", "blob", rev_path])
    if blob.returncode != 0:
        raise AssertionError("cannot read blob %s" % rev_path)
    got = hashlib.sha256(blob.stdout).hexdigest()
    if got != expected_sha256:
        raise AssertionError("blob %s sha256 %s != expected %s"
                             % (rev_path, got, expected_sha256))


def require_ancestor(rev):
    proc = git(["merge-base", "--is-ancestor", rev, "HEAD"])
    if proc.returncode != 0:
        raise AssertionError(
            "%s is not an ancestor of HEAD (rc=%d)" % (rev, proc.returncode))


def require_literal(rel_path, literal):
    if literal not in read_bytes(rel_path).decode("utf-8"):
        raise AssertionError("missing literal in %s: %r" % (rel_path, literal))


def git_blob_sha1(data):
    digest = hashlib.sha1()
    digest.update(b"blob %d\0" % len(data))
    digest.update(data)
    return digest.hexdigest()


def verify_staged_index_candidates():
    """Under a temporary GIT_INDEX_FILE, verify the candidate subset: every
    candidate path must be staged exactly once at mode 100644/stage 0 with a
    blob equal to the working bytes. Extra independent-review/manifest paths
    are permitted; exact staged-batch equality is enforced by the
    manifest/final verifier, not by this candidate suite. (P2 lifecycle fix
    2026-09-14: the former exact-three check blocked validating the final
    larger admission batches with the same suite.)"""
    if not STAGED_INDEX_FILE:
        return
    proc = git(["ls-files", "--stage"])
    if proc.returncode != 0:
        raise AssertionError("cannot read staged index %s" % STAGED_INDEX_FILE)
    entries = {}
    for line in proc.stdout.decode("utf-8").splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        mode, sha1, stage = meta.split()[:3]
        entries.setdefault(path, []).append((mode, sha1, stage))
    verify_staged_candidate_entries(entries)


def verify_staged_candidate_entries(entries):
    """Candidate-subset invariants over parsed `ls-files --stage` entries
    (path -> list of (mode, sha1, stage)): each candidate path must appear
    exactly once at mode 100644/stage 0 with a blob sha1 equal to the
    working bytes; extra paths are not inspected here."""
    for rel_path in CANDIDATE_PATHS:
        staged = entries.get(rel_path)
        if not staged:
            raise AssertionError(
                "staged index must contain candidate path %s" % rel_path)
        mode, sha1, stage = staged[0]
        if len(staged) != 1 or mode != "100644" or stage != "0":
            raise AssertionError(
                "candidate %s must appear exactly once at mode 100644/"
                "stage 0; got %r" % (rel_path, staged))
        if sha1 != git_blob_sha1(read_bytes(rel_path)):
            raise AssertionError(
                "staged blob differs from working bytes: %s" % rel_path)


PROMOTION_PATTERNS = [
    r"closes?\s+#?83\b",
    r"accepted\s+by\b",
    r"approval\s+(is\s+)?granted\b",
    r"(?:acceptance|approval|closure)\s+(?:of|for)\s+#?83\b",
    r"issue\s+#?83\s+(?:is\s+)?(?:now\s+)?(?:closed|accepted|approved)\b",
    r"rerun(?:ning)?\s+#?83\s+(?:is\s+)?(?:permitted|allowed)\b",
    r"#?83\s+(?:may|can)\s+be\s+rerun\b",
    r"authoriz\w+\s+(?:a\s+)?#?83\s+rerun\b",
]


def assert_no_promotion(text):
    lowered = text.lower()
    for pattern in PROMOTION_PATTERNS:
        if re.search(pattern, lowered):
            raise AssertionError("promotion wording detected: %r" % pattern)


class TestCodeBuddyAuditMatrixReviewContext(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.note = read_bytes(NOTE_REL).decode("utf-8")
        cls.review = read_bytes(REVIEW_REL).decode("utf-8")
        verify_staged_index_candidates()

    # --- byte bindings -------------------------------------------------------

    def test_review_doc_binding(self):
        verify_binding(REVIEW_REL, REVIEW_SHA256, REVIEW_SIZE)

    def test_ingest_note_binding(self):
        verify_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE)

    def test_self_file_present_with_expected_markers(self):
        text = read_bytes(SELF_REL).decode("utf-8")
        for marker in (REVIEW_SHA256, NOTE_SHA256, "CANDIDATE_PATHS",
                       "verify_staged_index_candidates"):
            self.assertIn(marker, text)

    # --- ancestry (ancestor assertions only; no HEAD equality) ----------------

    def test_required_ancestry_ancestor_assertions_only(self):
        for rev in (ARCH_ANCESTOR, FROZEN_AUDITOR_COMMIT, PROBE_TOOL_COMMIT,
                    AUDITOR_DRIFT_COMMIT):
            require_ancestor(rev)

    # --- tracked audit-matrix directory ----------------------------------------

    def test_matrix_files_tracked_and_byte_exact(self):
        require_tracked_in_head(MAIN_VERIFICATION_REL)
        verify_binding(MAIN_VERIFICATION_REL, MAIN_VERIFICATION_SHA256,
                       MAIN_VERIFICATION_SIZE)
        require_tracked_in_head(PROBE_EXECUTED_REL)
        verify_binding(PROBE_EXECUTED_REL, PROBE_EXECUTED_SHA256,
                       PROBE_EXECUTED_SIZE)
        require_tracked_in_head(PROBE_REPORT_REL)
        verify_binding(PROBE_REPORT_REL, PROBE_REPORT_SHA256,
                       PROBE_REPORT_SIZE)
        require_tracked_in_head(AUDITOR_EXECUTED_REL)
        verify_binding(AUDITOR_EXECUTED_REL, AUDITOR_EXECUTED_SHA256,
                       AUDITOR_EXECUTED_SIZE)
        require_tracked_in_head(PROBE_LOG_REL)
        verify_binding(PROBE_LOG_REL, PROBE_LOG_SHA256, PROBE_LOG_SIZE)

    def test_recorded_bindings_recompute_exactly(self):
        # The review records 8-char prefixes; the note records full hashes.
        self.assertEqual(RECORDED_PROBE_SHA256, PROBE_EXECUTED_SHA256)
        self.assertEqual(RECORDED_SOURCE_REPORT_SHA256, PROBE_REPORT_SHA256)
        self.assertEqual(RECORDED_AUDITOR_SHA256, AUDITOR_EXECUTED_SHA256)
        self.assertEqual(RECORDED_PROBE_SHA256[:8], "92a83f4e")
        self.assertEqual(RECORDED_SOURCE_REPORT_SHA256[:8], "4b21beca")
        self.assertEqual(RECORDED_AUDITOR_SHA256[:8], "e8d33c5d")
        for prefix in ("92a83f4e", "4b21beca", "e8d33c5d"):
            self.assertIn(prefix, self.review)
        for full in (RECORDED_PROBE_SHA256, RECORDED_SOURCE_REPORT_SHA256,
                     RECORDED_AUDITOR_SHA256):
            self.assertIn(full, self.note)

    def test_frozen_auditor_recoverable_from_head_tree(self):
        require_head_blob_sha256(FROZEN_AUDITOR_REV, AUDITOR_EXECUTED_SHA256)

    # --- main-verification.json strict facts ------------------------------------

    def test_main_verification_strict_json_facts(self):
        doc = strict_loads(MAIN_VERIFICATION_REL)
        self.assertEqual(doc["status"], "pass")
        self.assertIs(doc["complete_matrix_pass"], True)
        self.assertEqual(doc["positive_count"], 1)
        self.assertEqual(doc["required_negatives"], REQUIRED_NEGATIVES)
        self.assertIs(doc["baseline_unchanged"], True)
        self.assertIs(doc["full_acceptance"], False)
        self.assertEqual(doc["auditor_sha256"], RECORDED_AUDITOR_SHA256)
        self.assertEqual(doc["probe_sha256"], RECORDED_PROBE_SHA256)
        self.assertEqual(doc["source_report_sha256"],
                         RECORDED_SOURCE_REPORT_SHA256)
        self.assertIn("no new flight, no Full acceptance", doc["scope"])

    def test_main_verification_has_no_self_hash_key(self):
        doc = strict_loads(MAIN_VERIFICATION_REL)
        self.assertEqual(
            set(doc),
            {"status", "complete_matrix_pass", "positive_count",
             "required_negatives", "baseline_unchanged", "auditor_sha256",
             "probe_sha256", "source_report_sha256", "scope",
             "original_report", "full_acceptance"})
        self.assertNotIn("self_hash", doc)
        self.assertNotIn("main_verification_sha256", doc)

    def test_run02_original_report_is_external_path(self):
        doc = strict_loads(MAIN_VERIFICATION_REL)
        self.assertEqual(doc["original_report"], EXTERNAL_ORIGINAL_REPORT)
        self.assertIn(EXTERNAL_ORIGINAL_REPORT, self.note)
        self.assertIn("仅声明", self.note)

    # --- probe-report.json strict facts ------------------------------------------

    def test_probe_report_strict_json_one_positive_four_negatives(self):
        doc = strict_loads(PROBE_REPORT_REL)
        self.assertEqual(doc["kind"],
                         "offline release-audit negative-case probe")
        self.assertEqual(doc["verdict"], "pass")
        outcomes = {s["name"]: s["outcome"] for s in doc["scenarios"]}
        self.assertEqual(outcomes["positive_unmodified"], "accepted")
        for negative in REQUIRED_NEGATIVES:
            self.assertEqual(outcomes[negative], "rejected")
        self.assertEqual(len(doc["scenarios"]), 5)
        self.assertEqual(doc["auditor_sha256"], RECORDED_AUDITOR_SHA256)
        self.assertEqual(doc["baseline"]["file_count"], BASELINE_FILE_COUNT)
        self.assertIs(doc["baseline"]["unchanged"], True)

    def test_probe_report_f5_duplicate_overcount_numbers(self):
        doc = strict_loads(PROBE_REPORT_REL)
        inputs = doc["audit_inputs"]
        self.assertEqual(len(inputs["resolved"]), RESOLVED_UNIQUE)
        derived = inputs["derived_retained_sources"]
        self.assertEqual(len(derived), DERIVED_LISTED)
        self.assertEqual(doc["output_dir"], EXTERNAL_ORIGINAL_REPORT.rsplit(
            "/", 1)[0])

    def test_probe_log_anchors(self):
        verify_binding(PROBE_LOG_REL, PROBE_LOG_SHA256, PROBE_LOG_SIZE)
        require_literal(PROBE_LOG_REL,
                        "baseline files hashed: %d" % BASELINE_FILE_COUNT)
        require_literal(PROBE_LOG_REL,
                        "audit inputs : %d files (%d retained sources derived "
                        "from manifests)" % (RESOLVED_UNIQUE, DERIVED_LISTED))
        require_literal(PROBE_LOG_REL, "outcome=rejected ValueError: publish "
                                       "ledger and captured envelopes differ")
        require_literal(PROBE_LOG_REL, "outcome=accepted")

    # --- F4 content anchors in current tracked sources ----------------------------

    def test_f4_generator_side_anchors(self):
        require_tracked_in_head(TRANSPORT_NODE_REL)
        verify_binding(TRANSPORT_NODE_REL, TRANSPORT_NODE_SHA256,
                       TRANSPORT_NODE_SIZE)
        require_tracked_in_head(TRAJECTORY_BRIDGE_REL)
        verify_binding(TRAJECTORY_BRIDGE_REL, TRAJECTORY_BRIDGE_SHA256,
                       TRAJECTORY_BRIDGE_SIZE)
        require_literal(TRAJECTORY_BRIDGE_REL, "def build_ros_mode_request(")
        require_literal(TRAJECTORY_BRIDGE_REL,
                        "setup.cmd = UAVSetup.SET_PX4_MODE")
        require_literal(TRAJECTORY_BRIDGE_REL, "setup.px4_mode = mode")
        require_literal(TRANSPORT_NODE_REL, "def _publish_setup_envelope")

    def test_f4_consumer_side_anchors(self):
        require_tracked_in_head(CONTROL_NODE_REL)
        verify_binding(CONTROL_NODE_REL, CONTROL_NODE_SHA256, CONTROL_NODE_SIZE)
        node_text = read_bytes(CONTROL_NODE_REL).decode("utf-8")
        self.assertIn("elif msg.cmd == UAVSetup.SET_PX4_MODE:", node_text)
        self.assertIn("self.native.request('mode', msg.px4_mode)", node_text)
        for mode in ("POSCTL", "AUTO.LOITER", "AUTO.LAND", "AUTO.RTL",
                     "BRAKE"):
            self.assertIn("'%s'" % mode, node_text)
        self.assertIn("external_mode != 'GUIDED'", node_text)

    def test_f4_identity_gate_anchors(self):
        require_tracked_in_head(SESSION_REL)
        verify_binding(SESSION_REL, SESSION_SHA256, SESSION_SIZE)
        require_literal(SESSION_REL, "def accept(self, request):")
        require_literal(SESSION_REL, "unsupported_request_version")
        require_literal(SESSION_REL, "wrong_run_or_control_epoch")
        require_literal(SESSION_REL, "request_id_not_increasing")

    def test_f4_helper_record_has_no_envelope(self):
        require_tracked_in_head(HANDOFF_REL)
        verify_binding(HANDOFF_REL, HANDOFF_SHA256, HANDOFF_SIZE)
        doc = strict_loads(HANDOFF_REL)
        self.assertEqual(set(doc), HANDOFF_KEYS)
        for field in ("mode", "expected_native_mode",
                      "adopted_request_high_water",
                      "verified_command_high_water",
                      "verified_request_high_water"):
            self.assertIn(field, doc)
        for absent in ("setup", "envelope", "px4_mode", "cmd"):
            self.assertNotIn(absent, doc)

    # --- drift registration --------------------------------------------------------

    def test_current_auditor_drifted_and_registered(self):
        require_tracked_in_head(CURRENT_AUDITOR_REL)
        verify_binding(CURRENT_AUDITOR_REL, CURRENT_AUDITOR_SHA256,
                       CURRENT_AUDITOR_SIZE)
        self.assertNotEqual(CURRENT_AUDITOR_SHA256, AUDITOR_EXECUTED_SHA256)
        self.assertIn(AUDITOR_DRIFT_COMMIT, self.note)
        self.assertIn("bd90c75a", self.note)

    def test_current_probe_tool_state(self):
        require_tracked_in_head(CURRENT_PROBE_REL)
        verify_binding(CURRENT_PROBE_REL, CURRENT_PROBE_SHA256,
                       CURRENT_PROBE_SIZE)
        require_literal(CURRENT_PROBE_REL, "def probe_tool_identity")
        require_literal(CURRENT_PROBE_REL, '"probe_tool_sha256"')
        require_literal(CURRENT_PROBE_REL,
                        "deliberately stricter than ``verdict``")
        require_literal(CURRENT_PROBE_REL, '"blocked_or_error"')
        require_literal(CURRENT_PROBE_REL,
                        '"derived_retained_sources": sorted(set(inputs'
                        '["derived"]))')

    def test_historical_executed_probe_lacks_dedup_and_self_hash(self):
        probe_text = read_bytes(PROBE_EXECUTED_REL).decode("utf-8")
        self.assertIn('"derived_retained_sources": sorted(inputs["derived"])',
                      probe_text)
        self.assertNotIn("probe_tool_sha256", probe_text)

    def test_dedup_regression_test_tracked(self):
        require_tracked_in_head(DEDUP_TEST_REL)
        require_literal(DEDUP_TEST_REL,
                        "def test_derived_retained_sources_are_deduplicated")

    # --- ingest-note registration seams ---------------------------------------------

    def test_note_binds_source_and_registers_status(self):
        self.assertIn(REVIEW_SHA256, self.note)
        self.assertIn("5805 bytes", self.note)
        self.assertIn("historical context only", self.note)
        self.assertIn("非权威", self.note)
        self.assertIn("31e5b65f5448c5558450d16d0f46da0ef0f0a03c", self.note)

    def test_note_registers_finding_status_distinctions(self):
        self.assertIn("F2b", self.note)
        self.assertIn("F3", self.note)
        self.assertIn("F4", self.note)
        self.assertIn("F5", self.note)
        self.assertIn("boundary-only", self.note)
        self.assertIn("无 full-field source-side ledger", self.note)
        self.assertIn("不得", self.note)
        self.assertIn("reporting-only", self.note)
        self.assertIn("70 listed vs 66 unique", self.note)

    def test_note_registers_line_drift(self):
        self.assertIn("session.py:88–101", self.note)
        self.assertIn("86", self.note)

    # --- gate boundaries and no-promotion ----------------------------------------------

    def test_note_gate_boundaries(self):
        for literal in ("1ms", "native 屏障", "4-tick", "no-catch-up",
                        "100ms", "全窗", "身份门", "物理门",
                        "永不重跑", "未完成"):
            self.assertIn(literal, self.note)

    def test_review_declares_its_own_readonly_scope(self):
        self.assertIn("No native run, no ROS nodes, no build, no full",
                      self.review)
        self.assertIn("Read-only throughout except this report", self.review)

    def test_no_issue83_rerun_or_approval_wording(self):
        self.assertIn("不授予任何重跑许可", self.note)
        self.assertIn("未重跑 #83", self.note)
        assert_no_promotion(self.note)
        assert_no_promotion(self.review)

    # --- mutation negatives (helpers only; no repo file is modified) --------------------

    def test_mutation_negatives(self):
        with self.assertRaises(AssertionError):
            verify_binding(REVIEW_REL, "0" * 64, REVIEW_SIZE)
        with self.assertRaises(AssertionError):
            verify_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE + 1)
        with self.assertRaises(AssertionError):
            verify_binding(PROBE_REPORT_REL, PROBE_REPORT_SHA256,
                           PROBE_REPORT_SIZE - 1)
        with self.assertRaises(AssertionError):
            require_tracked_in_head("docs/coordination/"
                                    "does-not-exist-anywhere.md")
        with self.assertRaises(AssertionError):
            require_tracked_in_head(REVIEW_REL.replace(
                "audit-matrix", "audit-matrix-nonexistent"))
        with self.assertRaises(AssertionError):
            require_ancestor("0" * 40)
        with self.assertRaises(AssertionError):
            require_head_blob_sha256(FROZEN_AUDITOR_REV, "0" * 64)
        with self.assertRaises(AssertionError):
            require_literal(PROBE_LOG_REL,
                            "definitely-not-present-literal")
        require_literal(PROBE_LOG_REL, "outcome=accepted")  # sanity

    def test_staged_index_candidate_subset_negatives_in_memory(self):
        # Synthetic (no git, no repo mutation) checks of the core
        # candidate-subset verifier: exact-3 passes, extra
        # independent-review/manifest paths pass, while a missing candidate,
        # a nonzero stage, a duplicated candidate entry, and a blob mismatch
        # are each rejected.
        good = {rel: [("100644", git_blob_sha1(read_bytes(rel)), "0")]
                for rel in CANDIDATE_PATHS}
        verify_staged_candidate_entries(good)  # exact-3 sanity
        extra = dict(good)
        extra["validation/coordination/"
              "codebuddy-audit-matrix-independent-review-20260914-02/"
              "review.md"] = [("100644", "0" * 40, "0")]
        verify_staged_candidate_entries(extra)  # extra paths allowed
        missing = {k: v for k, v in good.items() if k != CANDIDATE_PATHS[0]}
        with self.assertRaises(AssertionError):
            verify_staged_candidate_entries(missing)
        nonzero_stage = dict(good)
        nonzero_stage[CANDIDATE_PATHS[1]] = [
            ("100644", git_blob_sha1(read_bytes(CANDIDATE_PATHS[1])), "1")]
        with self.assertRaises(AssertionError):
            verify_staged_candidate_entries(nonzero_stage)
        duplicated = dict(good)
        duplicated[CANDIDATE_PATHS[2]] = good[CANDIDATE_PATHS[2]] * 2
        with self.assertRaises(AssertionError):
            verify_staged_candidate_entries(duplicated)
        mismatched = dict(good)
        mismatched[CANDIDATE_PATHS[0]] = [("100644", "0" * 40, "0")]
        with self.assertRaises(AssertionError):
            verify_staged_candidate_entries(mismatched)

    def test_strict_json_duplicate_key_rejection_in_memory(self):
        with self.assertRaises(ValueError):
            strict_loads_text('{"a": 1, "a": 2}')
        with self.assertRaises(ValueError):
            strict_loads_text('{"k": NaN}')
        self.assertEqual(strict_loads_text('{"a": 1}'), {"a": 1})

    def test_promotion_wording_negatives(self):
        for text in ("this ingest note closes #83",
                     "the audit matrix review is accepted by the main agent",
                     "approval granted for #83 closure",
                     "issue #83 is now closed",
                     "rerunning #83 is permitted",
                     "#83 may be rerun after this note",
                     "this note authorizes a #83 rerun"):
            with self.assertRaises(AssertionError):
                assert_no_promotion(text)
        assert_no_promotion(
            "the review is historical context only; #83 remains CLOSED/PASS "
            "and nothing here reruns or re-opens it")  # sanity


if __name__ == "__main__":
    unittest.main()
