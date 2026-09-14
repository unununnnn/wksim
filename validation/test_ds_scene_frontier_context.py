"""Offline binding test for docs/coordination/ds-scene-frontier-20260912.md.

Re-enacts the byte-level binding, supersession registration, and offline-test
seam described in docs/coordination/ds-scene-frontier-ingest-note-20260914.md
(note sections 2, 4, and 5). No network, no live GitHub queries, no model /
build / UE / SITL / FC / ROS / MATLAB execution, no vendor bytes.

This test file itself asserts only historical-context binding, pin stability,
tracked anchors, manifest status facts, identity separation, and wording
containment. It never asserts that any candidate file stays untracked (so it
remains valid after staging or committing the candidates), and it makes no
live-GitHub inference. All git ancestry checks run against the symbolic
``HEAD``, so the suite stays valid in descendant commits.
"""

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

FRONTIER_REL = "docs/coordination/ds-scene-frontier-20260912.md"
FRONTIER_SHA256 = "9922942f3e13d712d02c050e62825dcc004f9cac41205de8b169b83c232a557e"
FRONTIER_SIZE = 7691

NOTE_REL = "docs/coordination/ds-scene-frontier-ingest-note-20260914.md"
NOTE_SHA256 = "f4804e46035c3f9be4c2ae5300ad51b84bc71068d469ef65e19e0eb4a7ebfe3e"
NOTE_SIZE = 9376

COMPANION_TEST_REL = "validation/test_scene_frontier_contract.py"
COMPANION_TEST_SHA256 = "3f593d8f3bdb3c34db5c7b51014c305fd9596a73ce803a1c187e3d509b6c3de2"
COMPANION_TEST_COMMIT = "cf509f5361f468e78bb81e47b3992ddf7db02957"

BINDING_HEAD = "9c581ad5b2e316904c9ef53e8543c5a6f413d6f9"
ARCH_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

MANIFEST_REL = "docs/plan/29-terrain-evidence-manifest.json"
MANIFEST_LAST_COMMIT = "c3f0d319"

# Retained scene identity layers (evidence manifest; note section 2.3).
VISUAL_SCENE_ID = "static-plane-box-v1"
VISUAL_SCENE_HASH = "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514"
VISUAL_BOX_CENTER_ENU_M = [2.0, 0.0, 0.5]
PROBE_SCENE_ID = "static-plane-box-v1-real-tick0"
PROBE_SCENE_HASH = "4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300"
PROBE_BOX_CENTER_ENU_M = [0.0, 0.0, 0.5]
PLANNER_SCENE_HASH = "40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba"

UNPROVEN_BOUNDARY_KEYS = [
    "missing_real_ue_physics_colocation",
    "missing_fc_closed_loop",
    "missing_slope_contact_force_dynamics",
]

# Tracked anchors the ingest note section 4 requires any later reference,
# re-check, or ingest manifest to name.
TRACKED_ANCHORS = [
    "docs/plan/29-terrain-evidence-manifest.json",
    "docs/plan/29-contact-observer-contract.md",
    "docs/plan/29-102-scene-binding-contract.md",
    "docs/plan/29-terrain-closure-report.md",
    "docs/plan/9-vendor-abi-defer-boundary.json",
    "Simulator/wksim_runtime/planner_scene_binding.py",
    "Simulator/wksim_runtime/contact_observer.py",
    "Simulator/wksim_runtime/terrain_feedback.py",
    "tools/probe_joint_terrain_feedback.py",
    COMPANION_TEST_REL,
    "validation/test_planner_scene_binding.py",
    "validation/test_audit_29_terrain_evidence.py",
]

FIXTURE_DIRS = [
    "validation/lunar-29-static-contact",
    "validation/lunar-29-live-contact",
    "validation/lunar-29-terrain-reset-c8f05c6e",
]

# Supersession fact (note section 3.1): the frontier doc's zero-occurrence
# claim was true only for the pre-slice test inventory. Current expectations,
# per file, of the probe (4889e2ea) / planner (40ee9281) identity tokens.
SUPERSEDED_TOKEN_FILES = [
    ("validation/test_scene_frontier_contract.py", True, True),
    ("validation/coordination/ds-g3-closure-frontier-20260913-01/check_g3_closure.py",
     False, True),
    ("validation/coordination/omp-g4-terrain-readiness-20260913-01/probe.py",
     True, False),
    ("validation/coordination/deepseek-102-residual-20260914-01/probe.py",
     False, True),
]

# How this test references the bound documents (wording containment).
REFERENCE_PHRASING = (
    "ds-scene-frontier-20260912.md is historical context only; the ingest "
    "note registers supersessions; the section 2 ticket table is a "
    "2026-09-12 snapshot requiring live re-query; no acceptance, closure, "
    "owner approval, or native execution permission is claimed."
)

FORBIDDEN_PROMOTION_PATTERNS = [
    r"closes?\s+#?29\b",
    r"closes?\s+#?102\b",
    r"closes?\s+#?9\b",
    r"(?:acceptance|approval|closure)\s+(?:of|for)\s+#?(?:29|102|9)\b",
    r"issue\s+#?(?:29|102)\s+(?:is\s+)?(?:now\s+)?(?:closed|accepted|approved)\b",
    r"grants?\s+native\s+execution\s+permission\b",
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
            "missing ancestry: %s is not an ancestor of symbolic HEAD (rc=%d)"
            % (rev, proc.returncode))


def assert_tracked(rel_path):
    proc = subprocess.run(["git", "ls-files", "--error-unmatch", rel_path],
                          cwd=str(REPO_ROOT), capture_output=True)
    if proc.returncode != 0:
        raise AssertionError(
            "missing tracked anchor: %s is not git-tracked" % rel_path)


def assert_no_authority_promotion(text):
    lowered = text.lower()
    for pattern in FORBIDDEN_PROMOTION_PATTERNS:
        if re.search(pattern, lowered):
            raise AssertionError(
                "authority wording promotion detected: pattern %r matched"
                % pattern)


def _load_manifest():
    def reject_duplicates(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise ValueError("duplicate manifest key %r" % (key,))
            seen.add(key)
        return dict(pairs)

    return json.loads(
        (REPO_ROOT / MANIFEST_REL).read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates)


class TestDsSceneFrontierContext(unittest.TestCase):

    # --- byte bindings ---------------------------------------------------

    def test_frontier_doc_binding(self):
        verify_binding(FRONTIER_REL, FRONTIER_SHA256, FRONTIER_SIZE)

    def test_ingest_note_binding(self):
        verify_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE)

    def test_companion_contract_test_binding(self):
        verify_binding(COMPANION_TEST_REL, COMPANION_TEST_SHA256)
        proc = git(["show", "%s:%s" % (COMPANION_TEST_COMMIT,
                                       COMPANION_TEST_REL)])
        blob_sha = hashlib.sha256(proc.stdout).hexdigest()
        self.assertEqual(
            blob_sha, COMPANION_TEST_SHA256,
            "companion test blob at %s drifted from the bound bytes"
            % COMPANION_TEST_COMMIT)
        # The companion test is a tracked anchor (staging-safe: staging or
        # committing candidates cannot untrack it).
        assert_tracked(COMPANION_TEST_REL)

    # --- ancestry against symbolic HEAD ------------------------------------

    def test_required_ancestry_against_symbolic_head(self):
        assert_ancestor(BINDING_HEAD)
        assert_ancestor(ARCH_ANCESTOR)

    # --- tracked anchors -----------------------------------------------------

    def test_tracked_anchors_exist(self):
        for rel_path in TRACKED_ANCHORS:
            assert_tracked(rel_path)
            self.assertTrue((REPO_ROOT / rel_path).is_file(), rel_path)
        for rel_dir in FIXTURE_DIRS:
            proc = git(["ls-files", rel_dir + "/"])
            tracked = [line for line in proc.stdout.decode().splitlines()
                       if line.strip()]
            self.assertTrue(
                tracked, "no tracked fixture files in %s" % rel_dir)
        proc = git(["ls-files"] + [d + "/" for d in FIXTURE_DIRS])
        total = len([line for line in proc.stdout.decode().splitlines()
                     if line.strip()])
        self.assertGreaterEqual(
            total, 3, "lunar-29 fixture evidence shrank below 3 files")

    def test_manifest_history_contains_binding_audit_commit(self):
        # Descendant-safe binding of the audit anchor: c3f0d319 must remain in
        # the manifest's history; the note's seam re-checks status fields, not
        # commit identity, so legitimate later manifest revisions only require
        # re-registration, not a broken context suite.
        proc = git(["log", "--format=%H", "--", MANIFEST_REL])
        heads = [line.strip() for line in proc.stdout.decode().splitlines()
                 if line.strip()]
        self.assertTrue(heads, "manifest has no commit history")
        self.assertTrue(
            any(h.startswith(MANIFEST_LAST_COMMIT) for h in heads),
            "binding audit commit %s not in manifest history"
            % MANIFEST_LAST_COMMIT)

    # --- manifest status facts (note section 2.2) ----------------------------

    def test_manifest_status_partial_open_not_accepted_blocked_by_9(self):
        manifest = _load_manifest()
        self.assertEqual(manifest["status"], "partial_open")
        self.assertIs(manifest["acceptance"], False)
        self.assertEqual(manifest["blocking_issue"], 9)

    def test_manifest_declares_exactly_three_unproven_boundaries(self):
        manifest = _load_manifest()
        boundaries = manifest["unproven_boundaries"]
        self.assertEqual(sorted(boundaries.keys()),
                         sorted(UNPROVEN_BOUNDARY_KEYS))
        for key in UNPROVEN_BOUNDARY_KEYS:
            self.assertIsInstance(boundaries[key], str)
            self.assertTrue(boundaries[key].strip(), key)

    # --- identity layers and frozen seam (note section 2.3) ------------------

    def test_manifest_scene_identities_match_pinned_values(self):
        manifest = _load_manifest()
        identities = manifest["scene_identities"]
        visual = identities["visual_static_scene"]
        real = identities["real_terrain_scene"]
        self.assertEqual(visual["scene_id"], VISUAL_SCENE_ID)
        self.assertEqual(visual["scene_sha256"], VISUAL_SCENE_HASH)
        self.assertEqual(list(visual["box_center_enu_m"]),
                         VISUAL_BOX_CENTER_ENU_M)
        self.assertEqual(real["scene_id"], PROBE_SCENE_ID)
        self.assertEqual(real["scene_sha256"], PROBE_SCENE_HASH)
        self.assertEqual(list(real["box_center_enu_m"]),
                         PROBE_BOX_CENTER_ENU_M)
        # The identity rule names both scene layers by abbreviated hash.
        self.assertIn(VISUAL_SCENE_HASH[:8],
                      identities["scene_identity_rule"])
        self.assertIn(PROBE_SCENE_HASH[:8],
                      identities["scene_identity_rule"])

    def test_three_identity_layers_distinct_and_frozen_seam_binds_visual(self):
        from Simulator.wksim_runtime.contact_observer import FROZEN_SCENE_SHA256
        from Simulator.wksim_runtime.planner_scene_binding import (
            EXPECTED_SCENE_HASH,
            LEGACY_SCENE_HASH,
            LEGACY_SCENE_ID,
        )

        self.assertEqual(LEGACY_SCENE_ID, VISUAL_SCENE_ID)
        self.assertEqual(LEGACY_SCENE_HASH, VISUAL_SCENE_HASH)
        self.assertEqual(EXPECTED_SCENE_HASH, PLANNER_SCENE_HASH)
        # Pairwise distinct: visual fixture, real probe, planner ego binding.
        self.assertNotEqual(VISUAL_SCENE_HASH, PROBE_SCENE_HASH)
        self.assertNotEqual(VISUAL_SCENE_HASH, PLANNER_SCENE_HASH)
        self.assertNotEqual(PROBE_SCENE_HASH, PLANNER_SCENE_HASH)
        # The runtime terrain seam stays on the frozen visual fixture.
        self.assertEqual(FROZEN_SCENE_SHA256, VISUAL_SCENE_HASH)
        self.assertNotEqual(FROZEN_SCENE_SHA256, PROBE_SCENE_HASH)

    # --- superseded zero-occurrence and delivery asymmetry (note section 3) --

    def test_note_registers_superseded_zero_occurrence_with_current_hits(self):
        note = (REPO_ROOT / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("零出现", note)
        self.assertIn("已被取代", note)
        # The note names the current token-bearing files as the supersession.
        for rel_path, has_probe, has_planner in SUPERSEDED_TOKEN_FILES:
            name = rel_path.rsplit("/", 1)[-1]
            self.assertIn(name, note, rel_path)
            text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
            self.assertEqual("4889e2ea" in text, has_probe, rel_path)
            self.assertEqual("40ee9281" in text, has_planner, rel_path)

    def test_note_registers_delivery_asymmetry_and_companion_stays_tracked(self):
        note = (REPO_ROOT / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("不对称", note)
        self.assertIn(COMPANION_TEST_COMMIT, note)
        self.assertIn(FRONTIER_SHA256, note)
        self.assertIn(str(FRONTIER_SIZE), note)
        # Staging-safe: only the companion's tracked state is asserted live;
        # the frontier doc's untracked status is registered in note text, not
        # asserted against the live index here.
        assert_tracked(COMPANION_TEST_REL)

    # --- historical / snapshot-only / no-authority wording --------------------

    def test_note_wording_historical_context_and_snapshot_scoping(self):
        note = (REPO_ROOT / NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("historical context only", note)
        self.assertIn("历史语境", note)
        self.assertIn("历史文件", note)
        # Section 0 non-authority disclaimer.
        self.assertIn("不构成 #29、#102 或 #9 的验收、批准、收口或复核记录", note)
        self.assertIn("不构成任何实时票面状态裁定", note)
        self.assertIn("也不授予任何原生物理/构建/联调执行许可", note)
        # Snapshot scoping of the ticket table.
        self.assertIn("2026-09-12 快照", note)
        self.assertIn("需实时重查", note)
        # No live GitHub inference claimed anywhere in the note.
        self.assertIn("未查询实时 GitHub 状态", note)
        self.assertNotIn("gh issue view", note)
        # Offline seam and boundary declarations present.
        self.assertIn("offline-test seam", note)
        self.assertIn("git add/commit/push", note)
        assert_no_authority_promotion(REFERENCE_PHRASING)

    # --- negative mutations (helpers only; no repo file is modified) ----------

    def test_mutation_hash_and_size_drift_detected(self):
        drifted_sha = "0" * 64
        with self.assertRaises(AssertionError):
            verify_binding(FRONTIER_REL, drifted_sha, FRONTIER_SIZE)
        with self.assertRaises(AssertionError):
            verify_binding(NOTE_REL, drifted_sha)
        with self.assertRaises(AssertionError):
            verify_binding(FRONTIER_REL, FRONTIER_SHA256, FRONTIER_SIZE + 1)
        with self.assertRaises(AssertionError):
            verify_binding(NOTE_REL, NOTE_SHA256, NOTE_SIZE - 1)
        with self.assertRaises(AssertionError):
            verify_binding(COMPANION_TEST_REL, "f" * 64)
        verify_binding(FRONTIER_REL, FRONTIER_SHA256)  # sanity: real passes

    def test_mutation_missing_anchor_and_ancestry_detected(self):
        with self.assertRaises(AssertionError):
            assert_tracked("docs/plan/does-not-exist-anywhere.md")
        with self.assertRaises(AssertionError):
            assert_ancestor("0" * 40)
        # Current anchors still pass (sanity against over-broad rejection).
        assert_tracked(TRACKED_ANCHORS[0])
        assert_ancestor(BINDING_HEAD)

    def test_mutation_wording_promotion_detected(self):
        promoted = [
            "the ingest note closes #29",
            "issue #102 is now closed",
            "approval for #9 dependency closure",
            "grants native execution permission for the frontier slice",
            "acceptance of #29 by this manifest",
        ]
        for text in promoted:
            with self.assertRaises(AssertionError):
                assert_no_authority_promotion(text)
        # Sanity: a reference phrasing without the promoted verb forms passes.
        assert_no_authority_promotion(REFERENCE_PHRASING)

    def test_mutation_manifest_drift_detected(self):
        manifest = _load_manifest()
        mutated = dict(manifest, status="closed")
        self.assertNotEqual(mutated["status"], manifest["status"])
        # The real manifest must still carry the bound status facts.
        self.assertEqual(manifest["status"], "partial_open")
        self.assertIs(manifest["acceptance"], False)
        self.assertEqual(manifest["blocking_issue"], 9)


if __name__ == "__main__":
    unittest.main()
