"""Offline binding tests for the OMP mixed-failure historical-context batch.

Binds two byte-fixed candidates as **historical context only**:
  - docs/coordination/omp-mixed-failure-review-20260913.md
  - docs/coordination/omp-mixed-failure-ingest-note-20260914.md
per the ingest note (its sections 2-7 define the seams these tests re-enact).

Design constraints (staging-safe, fresh-clone-safe):
  - Git topology asserts only ancestry: f333316e (architecture), e2ecd62e
    (audit baseline) and 011818876 (authoring HEAD) must be ancestors of the
    symbolic HEAD. HEAD equality is never required and current HEAD is never
    bound, so the suite stays valid at descendant commits.
  - Only tracked artifacts are read as live seams (the relocated analysis
    bundle, the analyzer, the shell of the note). The untracked xtj8wk8i
    classification artifacts are never read; their registration is asserted
    against the note bytes only.
  - No assertion requires candidate files to stay untracked; all paths are
    repo-relative via __file__; no writes, no network, no native execution,
    and issue 83 is never rerun or approved by anything here.
"""

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- byte-fixed candidates ----------------------------------------------------

REVIEW_REL = "docs/coordination/omp-mixed-failure-review-20260913.md"
REVIEW_SHA256 = "2417c299d57ccdc79b7368e03180bd0b767aabb91c012257e1443a17fca331c3"
REVIEW_SIZE = 4448

NOTE_REL = "docs/coordination/omp-mixed-failure-ingest-note-20260914.md"
NOTE_SHA256 = "92f8adf24faf0ba924ed402c2f07a4b0a2ef68f2583639f38e8f1a7bd67862a4"
NOTE_SIZE = 9762

# --- ancestry (ancestor assertions only; current HEAD is never bound) ---------

ARCH_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
AUDIT_BASELINE = "e2ecd62e914e075d0d9e40eef8ea9c034b958d2f"
AUTHORING_HEAD = "011818876c1b94875fd67cedaaa73abfac866633"

# --- stale cited path vs relocated tracked artifact ---------------------------

STALE_DIR_REL = "validation/current-mixed-20260913-01"
STALE_ANALYSIS_REL = STALE_DIR_REL + "/main-rate-analysis.json"

BUNDLE_DIR = "validation/33-formal-promotion/current-mixed-oxv29042"
ANALYSIS_REL = BUNDLE_DIR + "/main-rate-analysis.json"
ANALYSIS_SHA256 = "b4c7f44e12f96ac63b720b217cd102afeba5c846b3ecbf41c6e4dbd275c410cc"
BUNDLE_MANIFEST_REL = BUNDLE_DIR + "/bundle-manifest.json"
BUNDLE_MANIFEST_SHA256 = "f316862f37e6c8997543ef08d03247223c991553919c53152516ee90f804b546"
BUNDLE_MANIFEST_SIZE = 4153
RATE_GZ_REL = BUNDLE_DIR + "/rate.jsonl.gz"
RATE_GZ_SHA256 = "8058ecff7f4730d5fd81a50e8817a8a4190230cc2de3b8170496e46e279c99da"
BUNDLE_TRACKED_FILES = 20

EPOCH_PREFIX = "18c96a7e"
TRACE_SHA256 = "8725b63c568783199b4a5e7d3de7df532003749b73d4c255131da4bcedee8b91"

ANALYZER_REL = "tools/analyze_joint_rate_intervals.py"
ANALYZER_SHA256 = "1c43ac9c4b80f2dcc8eb52ffd9c3fe061f5cd2ef9206d839fe20e7af2f783fc7"

# --- partition / arithmetic / latch facts (bound doc + tracked analysis) ------

PARTITION = {"early": (249, 975731), "cross": (1, 4), "steady": (32679, 98805073)}
CREEP_TOTAL_NS = 99780808
WORK_OVER_NS = 15139984
LATCH_LATENESS_NS = 100034744
LATCH_TICK = 131760
GROUP_END = 32930
ANCHOR_TICK = 40
CHAIN_TERMS = (115732, 99780808, 138204)
MAX_INTERVAL_NS = 5547162
MAX_INTERVAL_WORK_OVER_NS = 5140957
MAX_INTERVAL_RELEASE_EXCESS_NS = 406205
RATE_GATE_NS = 100000000
ANCHOR_WALL_NS = 110030174978

# --- wording seams ------------------------------------------------------------

REFERENCE_PHRASING = (
    "omp-mixed-failure-review-20260913.md is historical context only; the "
    "ingest note registers the relocation and the two retractions; no "
    "acceptance, closure, approval, or issue-83 rerun is authorized."
)

PROMOTION_PATTERNS = [
    r"closes?\s+#?83\b",
    r"accepted\s+by\b",
    r"approval\s+(is\s+)?granted\b",
    r"(?:acceptance|approval|closure)\s+(?:of|for)\s+#?83\b",
    r"issue\s+#?83\s+(?:is\s+)?(?:now\s+)?(?:closed|accepted|approved)\b",
    r"rerun(?:ning)?\s+#?83\s+(?:is\s+)?(?:permitted|allowed)\b",
]


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
            "size drift for %s: expected %d, got %d" % (rel_path, expected_size, size))


def strict_loads(rel_path):
    """Strict JSON parse: duplicate keys rejected; NaN/Infinity rejected."""
    text = read_bytes(rel_path).decode("utf-8")

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


def require_tracked(rel_path):
    proc = subprocess.run(["git", "ls-files", "--error-unmatch", rel_path],
                          cwd=str(REPO_ROOT), capture_output=True)
    if proc.returncode != 0:
        raise AssertionError("missing tracked anchor: %s" % rel_path)


def require_ancestor(rev):
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", rev, "HEAD"],
                          cwd=str(REPO_ROOT), capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(
            "%s is not an ancestor of HEAD (rc=%d)" % (rev, proc.returncode))


def require_literal(rel_path, literal):
    if literal not in read_bytes(rel_path).decode("utf-8"):
        raise AssertionError("missing literal in %s: %r" % (rel_path, literal))


def assert_no_promotion(text):
    lowered = text.lower()
    for pattern in PROMOTION_PATTERNS:
        if re.search(pattern, lowered):
            raise AssertionError("promotion wording detected: %r" % pattern)


import re  # noqa: E402  (kept close to assert_no_promotion usage)


class TestOmpMixedFailureContext(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.note = read_bytes(NOTE_REL).decode("utf-8")
        cls.review = read_bytes(REVIEW_REL).decode("utf-8")

    # --- byte bindings -------------------------------------------------------

    def test_review_doc_binding(self):
        verify_binding(REVIEW_REL, REVIEW_SHA256, REVIEW_SIZE)

    def test_ingest_note_binding(self):
        verify_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE)

    # --- ancestry (ancestor assertions only; no HEAD equality) ----------------

    def test_required_ancestry_ancestor_assertions_only(self):
        for rev in (ARCH_ANCESTOR, AUDIT_BASELINE, AUTHORING_HEAD):
            require_ancestor(rev)

    # --- stale cited path is absent -------------------------------------------

    def test_stale_cited_path_absent(self):
        self.assertFalse((REPO_ROOT / STALE_DIR_REL).exists(), STALE_DIR_REL)
        self.assertFalse((REPO_ROOT / STALE_ANALYSIS_REL).exists(),
                         STALE_ANALYSIS_REL)
        self.assertIn("current-mixed-20260913-01", self.note)
        self.assertIn("不存在", self.note)

    # --- relocated tracked artifact --------------------------------------------

    def test_relocated_analysis_tracked_strict_json_exact_hash(self):
        require_tracked(ANALYSIS_REL)
        sha, _ = sha256_and_size(ANALYSIS_REL)
        self.assertEqual(sha, ANALYSIS_SHA256, ANALYSIS_REL)
        doc = strict_loads(ANALYSIS_REL)
        self.assertIsInstance(doc, dict)

    def test_bundle_manifest_tracked_with_rate_and_trace_pins(self):
        require_tracked(BUNDLE_MANIFEST_REL)
        sha, size = sha256_and_size(BUNDLE_MANIFEST_REL)
        self.assertEqual(sha, BUNDLE_MANIFEST_SHA256, BUNDLE_MANIFEST_REL)
        self.assertEqual(size, BUNDLE_MANIFEST_SIZE, BUNDLE_MANIFEST_REL)
        manifest = strict_loads(BUNDLE_MANIFEST_REL)
        self.assertIsInstance(manifest, dict)
        text = (REPO_ROOT / BUNDLE_MANIFEST_REL).read_text(encoding="utf-8")
        self.assertIn("oxv29042", text)
        self.assertIn(EPOCH_PREFIX, text)
        self.assertIn(TRACE_SHA256, text)
        self.assertIn(ANALYSIS_SHA256, text)
        self.assertIn("rate.jsonl.gz", text)

    def test_rate_gz_tracked(self):
        require_tracked(RATE_GZ_REL)
        sha, _ = sha256_and_size(RATE_GZ_REL)
        self.assertEqual(sha, RATE_GZ_SHA256, RATE_GZ_REL)

    def test_bundle_tracked_file_count_matches_note(self):
        proc = subprocess.run(
            ["git", "ls-files", BUNDLE_DIR + "/"],
            cwd=str(REPO_ROOT), capture_output=True, check=True)
        tracked = [line for line in proc.stdout.decode("utf-8").splitlines()
                   if line.strip()]
        self.assertEqual(len(tracked), BUNDLE_TRACKED_FILES)
        self.assertIn("20 个文件", self.note)

    # --- analyzer identity -------------------------------------------------------

    def test_analyzer_identity_current(self):
        require_tracked(ANALYZER_REL)
        sha, _ = sha256_and_size(ANALYZER_REL)
        self.assertEqual(sha, ANALYZER_SHA256, ANALYZER_REL)
        self.assertIn("1c43ac9c", self.note)

    # --- partition / latch facts inside the tracked analysis -------------------

    def test_partition_and_latch_facts_in_tracked_analysis(self):
        text = read_bytes(ANALYSIS_REL).decode("utf-8")
        for token in (EPOCH_PREFIX, str(ANCHOR_WALL_NS),
                      str(PARTITION["early"][0]), str(PARTITION["early"][1]),
                      str(PARTITION["cross"][0]), str(PARTITION["cross"][1]),
                      str(PARTITION["steady"][0]), str(PARTITION["steady"][1]),
                      str(WORK_OVER_NS), str(LATCH_LATENESS_NS),
                      str(LATCH_TICK), str(GROUP_END),
                      str(CHAIN_TERMS[0]), str(CHAIN_TERMS[2]),
                      str(MAX_INTERVAL_NS), str(MAX_INTERVAL_WORK_OVER_NS),
                      str(MAX_INTERVAL_RELEASE_EXCESS_NS),
                      ANALYZER_SHA256[:8]):
            self.assertIn(token, text, token)

    def test_closed_arithmetic(self):
        total = sum(ns for _, ns in PARTITION.values())
        self.assertEqual(total, CREEP_TOTAL_NS)
        self.assertEqual(sum(CHAIN_TERMS), LATCH_LATENESS_NS)
        self.assertEqual(MAX_INTERVAL_WORK_OVER_NS + MAX_INTERVAL_RELEASE_EXCESS_NS,
                         MAX_INTERVAL_NS)
        self.assertEqual((LATCH_TICK - ANCHOR_TICK) // 4, GROUP_END)
        self.assertEqual(LATCH_LATENESS_NS - RATE_GATE_NS, 34744)

    # --- retractions, residual removal, relocation registration in the note -----

    def test_note_registers_relocation(self):
        self.assertIn(ANALYSIS_SHA256, self.note)
        self.assertIn("validation/33-formal-promotion/current-mixed-oxv29042/"
                      "main-rate-analysis.json", self.note)
        self.assertIn("路径漂移登记", self.note)

    def test_note_registers_two_retractions_and_residual_removal(self):
        self.assertIn("tick≤2040", self.note)
        self.assertIn("已作废", self.note)
        self.assertIn("15.19 ms", self.note)
        self.assertIn("撤回", self.note)
        self.assertIn("residual_note", self.note)
        self.assertIn("removed", self.note)
        self.assertIn("不得复活 tick 域分区", self.note)

    def test_bound_doc_contains_the_two_retractions(self):
        self.assertIn("2040", self.review)
        self.assertIn("已作废", self.review)
        self.assertIn("15.19", self.review)
        self.assertIn("撤回", self.review)

    # --- tracked bundle vs external WSL raw evidence distinction -----------------

    def test_note_distinguishes_tracked_bundle_from_external_wsl(self):
        self.assertIn("tracked", self.note)
        self.assertIn("外部 WSL 侧", self.note)
        self.assertIn("不在主检出", self.note)
        self.assertIn("仅声明", self.note)
        self.assertIn("未触碰", self.note)

    # --- historical-only and gate boundaries --------------------------------------

    def test_note_historical_only_wording(self):
        for literal in ("historical context only", "历史语境", "非权威",
                        "不构成 #83", "基于**当下**的工件重新作出"):
            self.assertIn(literal, self.note)

    def test_note_gate_boundaries(self):
        for literal in ("1 ms", "no-catch-up", "100 ms", "全窗",
                        "run 内单调差分", "禁止跨 run 原点相减",
                        "追赶/回填", "不得叠加重叠区间",
                        "身份门", "物理门", "fail-closed"):
            self.assertIn(literal, self.note)

    def test_note_historical_failures_and_missing_row(self):
        for literal in ("zzmg3k47", "tpwl1k4p", "nqyqcagl", "8fmacpgy",
                        "7bdfxkb_", "1w6dru32", "不重跑", "MISSING",
                        "land_accepted", "不得计 pass"):
            self.assertIn(literal, self.note)

    # --- no issue-83 rerun or approval ------------------------------------------------

    def test_no_issue83_rerun_or_approval_wording(self):
        self.assertIn("不授予任何重跑许可", self.note)
        self.assertIn("未重跑 #83", self.note)
        assert_no_promotion(REFERENCE_PHRASING)
        assert_no_promotion(self.note)
        assert_no_promotion(self.review)

    # --- mutation negatives (helpers only; no repo file is modified) -------------------

    def test_mutation_negatives(self):
        with self.assertRaises(AssertionError):
            verify_binding(REVIEW_REL, "0" * 64, REVIEW_SIZE)
        with self.assertRaises(AssertionError):
            verify_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE + 1)
        with self.assertRaises(AssertionError):
            require_tracked("docs/plan/does-not-exist-anywhere.md")
        with self.assertRaises(AssertionError):
            require_ancestor("0" * 40)
        with self.assertRaises(AssertionError):
            require_literal(ANALYSIS_REL, "definitely-not-present-literal")
        require_literal(ANALYSIS_REL, "1c43ac9c")  # sanity: real value passes
        for text in ("this ingest note closes #83",
                     "the mixed failure review is accepted by the main agent",
                     "approval granted for #83 closure",
                     "issue #83 is now closed",
                     "rerunning #83 is permitted"):
            with self.assertRaises(AssertionError):
                assert_no_promotion(text)
        assert_no_promotion(REFERENCE_PHRASING)  # sanity: compliant phrasing passes


if __name__ == "__main__":
    unittest.main()
