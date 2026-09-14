"""Offline binding test for docs/coordination/ds-model-closure-20260912.md.

Re-enacts the byte-level binding and supersession registration described in
docs/coordination/ds-model-closure-ingest-note-20260914.md (offline-test seam,
note section 5). No network, no model/MATLAB/build execution, no vendor bytes.

This test file itself asserts only historical-context binding, pin stability,
tracked supersession anchors, and wording containment. It never asserts that
any candidate file stays untracked, and it makes no live-GitHub inference.
"""

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ORIGINAL_REL = "docs/coordination/ds-model-closure-20260912.md"
ORIGINAL_SHA256 = "a869117ff88c3e594fb44240b8970ee463aaedd39dca67e578b80f03dbe51d28"
ORIGINAL_SIZE = 15346

NOTE_REL = "docs/coordination/ds-model-closure-ingest-note-20260914.md"
NOTE_SHA256 = "979b37553f9716b58559df38d36a4070182d2b84d092e21f797a17d0533c11e9"

MANIFEST_REL = "docs/plan/26-closure-readiness-manifest.json"

# Six manifest pins, byte-bound via the ingest note section 2.1
# (manifest acceptance_evidence, 5 groups -> 6 pins).
MANIFEST_PINS = [
    ("source_chain", "docs/2026-09-10-generated-e0-lifecycle.md",
     "60a223620e7fc96b519bfa383fd1712c40386b99ed5812f6d2262c3b644a3d7a"),
    ("source_chain", "validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json",
     "85c40213cec0f349d36664c5621bb53c46ad96f9756cdd4eaa2bb97a7b2acc67"),
    ("matlab_license_actual_checkout", "validation/codegen-e0/short-cycle-codegen-01/codegen-report.json",
     "e5f32bd2890137591b61eba72fe0b21893fef578fd0a57094baf8fe92398f822"),
    ("matlab_free_lifecycle", "validation/codegen-e0-lifecycle-01/audit.json",
     "3d5c7896de10d10521ff4a1881eaffc8c96e73b196be72f9a044f2fc1aed346d"),
    ("vendor_materials_controlled", "validation/codegen-e0/short-cycle-codegen-01/summary.json",
     "42bc11a2a55fc26542cb52d34fc22d7ae8b3c6fc66deec19708aa232eb910f7c"),
    ("delivery_identity", "validation/codegen-e0-build-short-cycle-01/build-manifest.json",
     "0669730aeff54012e70c55e8fc1d103cfeb00cc33ec5b3147144df847fc7aa1c"),
]

# Three generated-source pins (note section 2.2).
GENERATED_PIN_REL = "work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw"
GENERATED_PINS = [
    ("Exp1_MinModelTemp.cpp",
     "2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274"),
    ("Exp1_MinModelTemp.h",
     "7601dbd721f0502e4bd67758d86cc21abf8e5c9568a31fb3160283df1df8c4bc"),
    ("rtwtypes.h",
     "1b08664b70d40d08ee2952ca47254bd16a9e045be8b5edc9781fe620fb7c199f"),
]

MODEL_CPP_REL = "Simulator/wksim_core/model.cpp"
MODEL_CPP_SHA256 = "150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290"
MODEL_CPP_SIZE = 4070
SELF_DECLARED_REV = "7126d4d774a33c7d4b2504b9931a93ac27d7fa51"
ANCESTOR_F333316E = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

SUPERSESSION_TRACKED_FILES = [
    "docs/plan/full-acceptance-report.md",
    "docs/plan/26-current-source-ac-evidence-20260912.md",
    "docs/plan/9-vendor-abi-defer-boundary.json",
]
CURRENT_WRAPPER_DIRS = [
    "validation/codegen-e0-build-current-wrapper-01",
    "validation/codegen-e0-lifecycle-current-wrapper-01",
]
CURRENT_WRAPPER_MIN_TRACKED = 22

# How this test references the bound documents (wording containment).
REFERENCE_PHRASING = (
    "ds-model-closure-20260912.md is historical context only; the ingest note "
    "registers supersessions; conditions A/C/D remain open observations "
    "requiring current authority."
)

FORBIDDEN_PROMOTION_PATTERNS = [
    r"closes?\s+condition\s+[a-e]\b",
    r"accepted\s+by\b",
    r"approval\s+(is\s+)?granted\b",
    r"(?:acceptance|approval|closure)\s+(?:of|for)\s+#?26\b",
    r"issue\s+#?26\s+(?:is\s+)?(?:now\s+)?(?:closed|accepted|approved)\b",
]


def sha256_and_size(rel_path):
    data = (REPO_ROOT / rel_path).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def verify_binding(rel_path, expected_sha, expected_size=None):
    sha, size = sha256_and_size(rel_path)
    if sha != expected_sha:
        raise AssertionError(
            "byte binding drift for %s: expected sha256 %s, got %s"
            % (rel_path, expected_sha, sha))
    if expected_size is not None and size != expected_size:
        raise AssertionError(
            "byte binding drift for %s: expected size %d, got %d"
            % (rel_path, expected_size, size))


def verify_pin(rel_path, expected_sha):
    sha, _ = sha256_and_size(rel_path)
    if sha != expected_sha:
        raise AssertionError(
            "pin drift for %s: expected %s, current %s"
            % (rel_path, expected_sha, sha))


def git(args, check=True):
    proc = subprocess.run(["git"] + args, cwd=str(REPO_ROOT),
                          capture_output=True)
    if check and proc.returncode != 0:
        raise AssertionError(
            "git %s failed (rc=%d): %s"
            % (" ".join(args), proc.returncode,
               proc.stderr.decode("utf-8", "replace").strip()))
    return proc


def assert_ancestor(rev):
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", rev, "HEAD"],
        cwd=str(REPO_ROOT), capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(
            "missing ancestry: %s is not an ancestor of HEAD (rc=%d)"
            % (rev, proc.returncode))


def assert_tracked(rel_path):
    proc = subprocess.run(["git", "ls-files", "--error-unmatch", rel_path],
                          cwd=str(REPO_ROOT), capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(
            "missing tracked supersession anchor: %s is not git-tracked"
            % rel_path)


def assert_no_authority_promotion(text):
    lowered = text.lower()
    for pattern in FORBIDDEN_PROMOTION_PATTERNS:
        if re.search(pattern, lowered):
            raise AssertionError(
                "authority wording promotion detected: pattern %r matched"
                % pattern)


class TestDsModelClosureContext(unittest.TestCase):

    # --- byte bindings ---------------------------------------------------

    def test_original_doc_binding(self):
        verify_binding(ORIGINAL_REL, ORIGINAL_SHA256, ORIGINAL_SIZE)

    def test_ingest_note_binding(self):
        verify_binding(NOTE_REL, NOTE_SHA256)

    # --- pins ------------------------------------------------------------

    def test_manifest_pins_current(self):
        manifest = json.loads(
            (REPO_ROOT / MANIFEST_REL).read_text(encoding="utf-8"))
        groups = manifest["acceptance_evidence"]
        self.assertEqual(len(groups), 5)
        live_pins = {}
        for group in groups.values():
            for pin in group["pins"]:
                live_pins[pin["path"]] = pin["sha256"]
        self.assertEqual(len(live_pins), 6)
        for _ac, rel_path, expected_sha in MANIFEST_PINS:
            self.assertIn(rel_path, live_pins)
            # manifest's recorded pin still equals the bound value
            self.assertEqual(live_pins[rel_path], expected_sha,
                             "manifest pin rewritten for %s" % rel_path)
            # current file bytes still equal the pin
            verify_pin(rel_path, expected_sha)

    def test_generated_source_pins_current(self):
        for name, expected_sha in GENERATED_PINS:
            verify_pin("%s/%s" % (GENERATED_PIN_REL, name), expected_sha)

    # --- wrapper model.cpp identity ---------------------------------------

    def test_model_cpp_identical_at_self_declared_rev_and_head(self):
        verify_binding(MODEL_CPP_REL, MODEL_CPP_SHA256, MODEL_CPP_SIZE)
        for rev in (SELF_DECLARED_REV, "HEAD"):
            proc = git(["show", "%s:%s" % (rev, MODEL_CPP_REL)])
            blob_sha = hashlib.sha256(proc.stdout).hexdigest()
            self.assertEqual(
                blob_sha, MODEL_CPP_SHA256,
                "model.cpp blob at %s drifted: %s" % (rev, blob_sha))
        proc = git(["log", "%s..HEAD" % SELF_DECLARED_REV, "--",
                    MODEL_CPP_REL], check=False)
        self.assertEqual(
            proc.returncode, 0, "git log range failed for model.cpp")
        self.assertEqual(
            proc.stdout.strip(), b"",
            "model.cpp changed after self-declared rev 7126d4d7")

    # --- tracked supersession anchors -------------------------------------

    def test_tracked_supersession_anchors_exist(self):
        for rel_path in SUPERSESSION_TRACKED_FILES:
            assert_tracked(rel_path)
            self.assertTrue((REPO_ROOT / rel_path).is_file(), rel_path)
        for rel_dir in CURRENT_WRAPPER_DIRS:
            proc = git(["ls-files", rel_dir + "/"])
            tracked = [line for line in proc.stdout.decode().splitlines()
                       if line.strip()]
            self.assertTrue(
                tracked, "no tracked evidence files in %s" % rel_dir)
        proc = git(["ls-files"] + [d + "/" for d in CURRENT_WRAPPER_DIRS])
        total = len([line for line in proc.stdout.decode().splitlines()
                     if line.strip()])
        self.assertGreaterEqual(
            total, CURRENT_WRAPPER_MIN_TRACKED,
            "current-wrapper evidence shrank: %d tracked files" % total)

    # --- ancestry -----------------------------------------------------------

    def test_required_ancestry(self):
        assert_ancestor(ANCESTOR_F333316E)
        assert_ancestor(SELF_DECLARED_REV)

    # --- note wording (enforced against the bound note bytes) ---------------

    def test_note_wording_historical_context_only(self):
        note = (REPO_ROOT / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("historical context only", note)
        self.assertIn("历史语境", note)
        # section 0: the note itself is not acceptance/approval/closure/review
        self.assertIn("不构成 #26 的验收、批准、收口或复核记录", note)
        self.assertIn("当前权威", note)

    def test_note_registers_supersessions(self):
        note = (REPO_ROOT / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("full-acceptance-report.md", note)
        self.assertIn("26-current-source-ac-evidence-20260912.md", note)
        # condition B executed and separated into independent evidence dirs
        self.assertIn("codegen-e0-build-current-wrapper-01", note)
        self.assertIn("codegen-e0-lifecycle-current-wrapper-01", note)
        # 68c6965b classified as a line-ending artifact with no object
        self.assertIn("68c6965b", note)
        self.assertIn("行尾", note)
        self.assertIn("无对象", note)

    def test_note_conditions_acd_remain_open_observations(self):
        note = (REPO_ROOT / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("仍开放", note)
        self.assertIn("待当前权威处置", note)
        # no live-GitHub inference: the note declares it queried no GitHub
        # state and contains no gh command output being cited as fact
        self.assertIn("未查询实时 GitHub 状态", note)
        self.assertNotIn("gh issue view", note)
        assert_no_authority_promotion(REFERENCE_PHRASING)

    # --- negative mutations (helpers only; no repo file is modified) --------

    def test_mutation_hash_drift_detected(self):
        drifted_sha = "0" * 64
        with self.assertRaises(AssertionError):
            verify_binding(ORIGINAL_REL, drifted_sha, ORIGINAL_SIZE)
        with self.assertRaises(AssertionError):
            verify_binding(NOTE_REL, drifted_sha)
        with self.assertRaises(AssertionError):
            verify_binding(ORIGINAL_REL, ORIGINAL_SHA256, ORIGINAL_SIZE + 1)

    def test_mutation_pin_drift_detected(self):
        _ac, rel_path, expected_sha = MANIFEST_PINS[0]
        with self.assertRaises(AssertionError):
            verify_pin(rel_path, "f" * 64)
        with self.assertRaises(AssertionError):
            verify_pin("%s/%s" % (GENERATED_PIN_REL, "rtwtypes.h"),
                       "f" * 64)
        verify_pin(rel_path, expected_sha)  # sanity: real pin still passes

    def test_mutation_missing_tracked_and_ancestry_detected(self):
        with self.assertRaises(AssertionError):
            assert_tracked("docs/plan/does-not-exist-anywhere.md")
        with self.assertRaises(AssertionError):
            assert_ancestor("0" * 40)
        # current anchors still pass (sanity against over-broad rejection)
        assert_tracked(SUPERSESSION_TRACKED_FILES[0])
        assert_ancestor(SELF_DECLARED_REV)

    def test_mutation_wording_promotion_detected(self):
        promoted = [
            "the ingest note closes condition A",
            "ds-model-closure-20260912.md is accepted by the main agent",
            "approval granted for #26 closure",
            "issue #26 is now closed",
        ]
        for text in promoted:
            with self.assertRaises(AssertionError):
                assert_no_authority_promotion(text)


if __name__ == "__main__":
    unittest.main()
