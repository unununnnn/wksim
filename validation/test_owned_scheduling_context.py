# -*- coding: utf-8 -*-
"""Deterministic offline context tests: owned-scheduling historical ingest (2026-09-14).

Scope (batch: codebuddy-owned-scheduling-ingest-note-20260914):
  * Verify the five superseded 2026-09-13 source documents and their tracked
    evidence anchors at the absolute pinned commit (not a floating HEAD).
  * Verify tracked flight snapshots (last-callbacks-run-20260913-01 and
    manager99-run-20260913-01, flight/ dirs) and their result.json chains.
  * Enforce forbidden-promotion and boundary language on the ingest note.
  * Enforce source relationships (historical comparator byte pin preserved,
    superseded comparator/test pins documented, e2e source pins).
  * Candidate paths: docs/coordination/codebuddy-owned-scheduling-ingest-note-20260914.md
    and validation/test_owned_scheduling_context.py.

Safe drift policy (explicit):
  * Content assertions read bytes from the absolute pinned commit
    ANCHOR_COMMIT, so HEAD movement never changes what is asserted.
  * If ANCHOR_COMMIT is not reachable (rewritten history / shallow clone),
    content assertions SKIP with a reason: fail-safe, never guessed, never
    degraded to pass.
  * If the current HEAD differs from ANCHOR_COMMIT, HEAD-specific assertions
    SKIP (safe drift notice); anchor-pinned assertions still run.
  * Any byte/hash/semantic mismatch at the pinned commit FAILS: that is real
    drift and must be reported.
  * The two candidate paths must never exist at ANCHOR_COMMIT (they are new
    candidates; .gitignore covers validation/* so only the main agent may
    exact-stage with -f).

Staged-index mode:
  * When GIT_INDEX_FILE is set (repo-external temporary index), the tests
    additionally assert both candidates are staged in THAT index with blob
    hashes equal to their working-tree bytes, and that the repository's
    default index does NOT contain them (real index untouched).
  * Without GIT_INDEX_FILE, index state is not asserted.

Pure offline: subprocess git plumbing only; no network, no build, no native,
no mutation of any file, index, or ref.
"""

import hashlib
import json
import os
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ANCHOR_COMMIT = "31e5b65f5448c5558450d16d0f46da0ef0f0a03c"
BASELINE_COMMIT = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

NOTE_REL = "docs/coordination/codebuddy-owned-scheduling-ingest-note-20260914.md"
TEST_REL = "validation/test_owned_scheduling_context.py"
CANDIDATES = (NOTE_REL, TEST_REL)

# --- pinned sources: five superseded 2026-09-13 documents -------------------
SOURCE_DOCS = {
    "docs/coordination/codebuddy-owned-scheduling-review-20260913.md": (
        "e7641f65b15d0ef2ea7e865c57ceddffb53ee6e4eefecc74adea63d2138592ce", 5598),
    "docs/coordination/codebuddy-scheduling-comparison-review-20260913.md": (
        "2bc26aaf6a87ed2ddcde746eb06e5cc02c21c111502d74396e4f8c2d1654bdab", 4878),
    "docs/coordination/owned-scheduling-snapshot-20260913.md": (
        "b4f1f5323e2502028f7296d5b158f9b07ec387da6e3b0124cfdc7465e56dd069", 7470),
    "docs/coordination/owned-scheduling-comparison-20260913.md": (
        "0dfd79adfaa9d6b25302e5304290dd337431214e8f9fb0c6817848164010e04c", 6365),
    "docs/coordination/owned-scheduling-e2e-20260913.md": (
        "fc7a74d7b325d691498fd0eed187f1d4a9afab907e097bf6cdeda8b56076247f", 6709),
}

# --- pinned evidence anchors at ANCHOR_COMMIT --------------------------------
TRACKED_ANCHORS = {
    "tools/capture_owned_scheduling.py": (
        "a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e", 20901),
    "validation/test_owned_scheduling.py": (
        "a0e747d3c6fa93f4f68cb08591d8d83708164b8fef261136b042abc908e71319", 22401),
    "tools/compare_owned_scheduling.py": (
        "13a61a7ffd92880571613c69d3d31736f1982e75ff03b365e2602338c928ec6f", 21412),
    "validation/test_compare_owned_scheduling.py": (
        "a8eb584df5c86112fa8f39dff4869f4d2e0baa652a56c8ff3164a12b3cf12ca9", 21061),
    "validation/coordination/owned-scheduling-e2e-20260913/source-compare-v1.py": (
        "033d8af81c8c785c5d28a6476aa909309f1bcae20f196d3d0c17b71b06103c7d", 21218),
    "validation/coordination/owned-scheduling-e2e-20260913/source-run-e2e-v1.py": (
        "b2e691cd8da081e7e93087d8158098dff6905f101922bd873fb344b3f49b9ef2", 8226),
}

# Historical pin from codebuddy-scheduling-comparison-review-20260913.md that
# is superseded and has NO tracked byte copy (documented limitation; must not
# be presented as current fact).
HISTORICAL_COMPARE_PIN = (
    "033d8af81c8c785c5d28a6476aa909309f1bcae20f196d3d0c17b71b06103c7d")
HISTORICAL_TEST_PIN = (
    "20cc459052c2cf8d860e2c1583334e583abd3b95c3d022a8a0795580ab8642fe")

# Ingest note content pin (computed after final edit of that file).
NOTE_SHA256 = "a8559e33f75d4475a4756787ab724b3c3338db4df8832a8fed6037c7d0da75a7"
NOTE_SIZE = 10688

# --- tracked flight snapshots -------------------------------------------------
SNAPSHOTS = {
    "last-callbacks-run-20260913-01": {
        "run_id": "joint-public-flight-5lfbcy43",
        "boot_id": "2e7caa0c-f041-426f-a550-50acd12125c5",
        "children_sha256": "268825bb27300713a3800a6f057fd0cfc78a9f518a70981ccae2037580b6b757",
        "before_sha256": "4647d5a2a6711839db813ba84bbeb9df5abf5d30796f3f38a0098f835736d4e7",
        "after_sha256": "7cf3c046aecf5bde0da9558f65daf3bf3d07aa524cbf21adb2f16989e020c5cb",
        "monotonic_before": 91625358121,
        "monotonic_after": 270719650116,
    },
    "manager99-run-20260913-01": {
        "run_id": "joint-public-flight-x39qjvkw",
        "boot_id": "5906186e-8181-42ff-8c56-d8ec2a26bd62",
        "children_sha256": "8ec3f5803cb3af61f56966352409ff65215ef21f0900962d531f54f932b594e4",
        "before_sha256": "e9bed5bc0f590ab743a7ca05cb5f63c3177ecb703d746cb80452d36179aa396f",
        "after_sha256": "699b4474b287d7815fc9d65092acc501064fdb4250167f693c97d8446ea8c821",
        "monotonic_before": 97474541343,
        "monotonic_after": 316507734204,
    },
}
EXPECTED_ROLES = {
    "arducopter-agent", "arducopter-control", "arducopter-fc",
    "arducopter-model", "arducopter-task", "manager",
    "px4-agent", "px4-control", "px4-fc", "px4-model", "px4-task",
}
CAPTURE_SAMPLER_SHA = TRACKED_ANCHORS["tools/capture_owned_scheduling.py"][0]

E2E_RESULT_REL = "validation/coordination/owned-scheduling-e2e-20260913/result.json"
E2E_SOURCE_PINS = {
    "capture": "a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e",
    "compare": "033d8af81c8c785c5d28a6476aa909309f1bcae20f196d3d0c17b71b06103c7d",
    "run_e2e": "b2e691cd8da081e7e93087d8158098dff6905f101922bd873fb344b3f49b9ef2",
}

# --- module-level environment facts (lazy, cached) ----------------------------
_cache = {}


def _git(args, allow_fail=True, extra_env=None, strip_index_env=False):
    """Run a git plumbing command in REPO_ROOT; return stdout bytes or None."""
    env = dict(os.environ)
    if strip_index_env:
        env.pop("GIT_INDEX_FILE", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["git"] + args, cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        if not allow_fail:
            raise AssertionError(
                "git %s failed (rc=%s): %s" % (
                    " ".join(args), proc.returncode,
                    proc.stderr.decode("utf-8", "replace").strip()))
        return None
    return proc.stdout


def _env_facts():
    if "facts" not in _cache:
        head = _git(["rev-parse", "HEAD"])
        anchor_ok = _git(["cat-file", "-e", ANCHOR_COMMIT + "^{commit}"]) is not None
        baseline_in_anchor = False
        if anchor_ok:
            probe = _git([
                "merge-base", "--is-ancestor", BASELINE_COMMIT, ANCHOR_COMMIT])
            baseline_in_anchor = probe is not None
        _cache["facts"] = {
            "head": head.decode().strip() if head else None,
            "anchor_reachable": anchor_ok,
            "baseline_in_anchor": baseline_in_anchor,
            "index_mode": "GIT_INDEX_FILE" in os.environ,
        }
    return _cache["facts"]


_anchor_blob_cache = {}


def _anchor_bytes(rel):
    """Bytes of rel at ANCHOR_COMMIT, or None if absent (cached)."""
    if rel not in _anchor_blob_cache:
        raw = _git(["show", ANCHOR_COMMIT + ":" + rel]) if _env_facts()["anchor_reachable"] else None
        _anchor_blob_cache[rel] = raw
    return _anchor_blob_cache[rel]


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _blob_sha1_file(rel):
    """Git blob sha1 of a working-tree file (offline plumbing, no writes)."""
    out = _git(["hash-object", "--", rel], allow_fail=False)
    return out.decode().strip()


def _index_entry_blob_sha1(rel, use_index_env):
    """Blob sha1 of rel in the consulted index; None when not staged."""
    out = _git(["ls-files", "-s", "--", rel], strip_index_env=not use_index_env)
    if not out:
        return None
    for line in out.decode().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[3] == rel:
            return parts[1]
    return None


def skip_no_anchor():
    return unittest.skipUnless(
        _env_facts()["anchor_reachable"],
        "safe drift: pinned commit %s not reachable; assertion skipped, "
        "not guessed" % ANCHOR_COMMIT)


class TestEnvironmentAndDriftPolicy(unittest.TestCase):

    def test_repo_root_is_git_worktree(self):
        self.assertTrue(
            os.path.isdir(os.path.join(REPO_ROOT, ".git")),
            "REPO_ROOT is not a git worktree: %s" % REPO_ROOT)

    def test_expected_head(self):
        facts = _env_facts()
        if facts["head"] is None:
            self.skipTest("git rev-parse HEAD unavailable; safe drift skip")
        if facts["head"] != ANCHOR_COMMIT:
            self.skipTest(
                "safe drift: current HEAD %s != pinned %s; HEAD-specific "
                "assertions skipped, anchor-pinned assertions still run"
                % (facts["head"], ANCHOR_COMMIT))
        self.assertEqual(facts["head"], ANCHOR_COMMIT)

    def test_baseline_is_ancestor_of_head_when_head_matches(self):
        facts = _env_facts()
        if facts["head"] != ANCHOR_COMMIT:
            self.skipTest("safe drift: HEAD moved; ancestry checked against "
                          "the anchor commit instead")
        probe = _git(["merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"])
        self.assertIsNotNone(
            probe, "architecture baseline %s is NOT an ancestor of HEAD"
            % BASELINE_COMMIT)

    @skip_no_anchor()
    def test_baseline_is_ancestor_of_anchor_commit(self):
        self.assertTrue(
            _env_facts()["baseline_in_anchor"],
            "baseline %s is not an ancestor of pinned commit %s"
            % (BASELINE_COMMIT, ANCHOR_COMMIT))


@unittest.skipUnless(_env_facts()["anchor_reachable"],
                     "safe drift: pinned commit %s not reachable; content "
                     "assertions skipped, not guessed" % ANCHOR_COMMIT)
class TestSourceDocsAtAnchor(unittest.TestCase):

    def test_five_sources_exist_with_pinned_hash_and_size(self):
        for rel, (sha, size) in sorted(SOURCE_DOCS.items()):
            raw = _anchor_bytes(rel)
            self.assertIsNotNone(raw, "missing at anchor: %s" % rel)
            self.assertEqual(_sha256(raw), sha, "hash drift: %s" % rel)
            self.assertEqual(len(raw), size, "size drift: %s" % rel)

    def test_source_docs_working_tree_matches_anchor(self):
        for rel in sorted(SOURCE_DOCS):
            with open(os.path.join(REPO_ROOT, rel), "rb") as handle:
                work = handle.read()
            self.assertEqual(_sha256(work), _sha256(_anchor_bytes(rel)),
                             "working tree drift vs anchor: %s" % rel)


@unittest.skipUnless(_env_facts()["anchor_reachable"],
                     "safe drift: pinned commit %s not reachable" % ANCHOR_COMMIT)
class TestTrackedAnchorsAtAnchor(unittest.TestCase):

    def test_anchors_exist_with_pinned_hash_and_size(self):
        for rel, (sha, size) in sorted(TRACKED_ANCHORS.items()):
            raw = _anchor_bytes(rel)
            self.assertIsNotNone(raw, "missing at anchor: %s" % rel)
            self.assertEqual(_sha256(raw), sha, "hash drift: %s" % rel)
            self.assertEqual(len(raw), size, "size drift: %s" % rel)

    def test_anchors_working_tree_matches_anchor(self):
        for rel in sorted(TRACKED_ANCHORS):
            with open(os.path.join(REPO_ROOT, rel), "rb") as handle:
                work = handle.read()
            self.assertEqual(_sha256(work), _sha256(_anchor_bytes(rel)),
                             "working tree drift vs anchor: %s" % rel)

    def test_capture_semantic_anchors(self):
        raw = _anchor_bytes("tools/capture_owned_scheduling.py")
        for needle in (
                b'"performance_verdict": "not_evaluated"',
                b'open("x"', b"read_bytes()", b"kernel_prio",
                b"sched_schedstats_disabled", b"sched_schedstats_unreadable",
                b"thread_identity_changed", b"_identity_problem",
                b"sampler_sha256"):
            self.assertIn(needle, raw,
                          "capture semantic anchor missing: %r" % needle)

    def test_compare_semantic_anchors(self):
        raw = _anchor_bytes("tools/compare_owned_scheduling.py")
        for needle in (
                b"_as_int", b"invalid_counter_value",
                b"host_sched_schedstats_not_enabled",
                b'runqueue_counters_valid") is True'):
            self.assertIn(needle, raw,
                          "compare semantic anchor missing: %r" % needle)

    def test_historical_comparator_pin_preserved_not_current(self):
        hist = _anchor_bytes(
            "validation/coordination/owned-scheduling-e2e-20260913/"
            "source-compare-v1.py")
        self.assertEqual(_sha256(hist), HISTORICAL_COMPARE_PIN)
        self.assertNotEqual(
            _sha256(_anchor_bytes("tools/compare_owned_scheduling.py")),
            HISTORICAL_COMPARE_PIN,
            "current comparator must not equal the superseded v1 pin")

    def test_superseded_test_pin_has_no_current_byte_equality(self):
        self.assertNotEqual(
            _sha256(_anchor_bytes("validation/test_compare_owned_scheduling.py")),
            HISTORICAL_TEST_PIN,
            "superseded historical test pin unexpectedly equals current bytes")

    def test_source_relationships_in_review_doc(self):
        raw = _anchor_bytes(
            "docs/coordination/codebuddy-scheduling-comparison-review-20260913.md")
        self.assertIn(HISTORICAL_COMPARE_PIN.encode("ascii"), raw)
        self.assertIn(HISTORICAL_TEST_PIN.encode("ascii"), raw)

    def test_review_doc_pins_match_capture_and_test_owned(self):
        review = _anchor_bytes(
            "docs/coordination/codebuddy-owned-scheduling-review-20260913.md")
        for rel in ("tools/capture_owned_scheduling.py",
                    "validation/test_owned_scheduling.py"):
            self.assertIn(TRACKED_ANCHORS[rel][0].encode("ascii"), review,
                          "review doc missing current pin for %s" % rel)

    def test_e2e_result_source_pins(self):
        raw = _anchor_bytes(E2E_RESULT_REL)
        data = json.loads(raw.decode("utf-8"))
        self.assertEqual(data.get("verdict"), "pass")
        self.assertEqual(data.get("source_sha256"), E2E_SOURCE_PINS)


@unittest.skipUnless(_env_facts()["anchor_reachable"],
                     "safe drift: pinned commit %s not reachable" % ANCHOR_COMMIT)
class TestFlightSnapshotsAtAnchor(unittest.TestCase):

    def _snap(self, run, phase):
        rel = "validation/coordination/%s/flight/owned-scheduling-%s.json" % (
            run, phase)
        raw = _anchor_bytes(rel)
        self.assertIsNotNone(raw, "missing snapshot at anchor: %s" % rel)
        return raw, json.loads(raw.decode("utf-8"))

    def test_snapshot_schema_and_negative_claims(self):
        for run, pin in sorted(SNAPSHOTS.items()):
            for phase in ("before", "after"):
                raw, data = self._snap(run, phase)
                self.assertEqual(
                    data.get("schema"), "wksim.owned-scheduling-snapshot.v1")
                self.assertEqual(data.get("phase"), phase)
                self.assertEqual(data.get("performance_verdict"),
                                 "not_evaluated")
                self.assertEqual(data.get("sampler_sha256"),
                                 CAPTURE_SAMPLER_SHA)
                self.assertEqual(data.get("host", {}).get("boot_id"),
                                 pin["boot_id"])
                self.assertEqual(data.get("host", {}).get("sched_schedstats"),
                                 "0")
                self.assertEqual(data.get("children", {}).get("sha256"),
                                 pin["children_sha256"])

    def test_snapshot_roles_all_captured(self):
        for run in sorted(SNAPSHOTS):
            for phase in ("before", "after"):
                _, data = self._snap(run, phase)
                procs = data.get("procs", {})
                self.assertEqual(set(procs), EXPECTED_ROLES)
                for role, proc in procs.items():
                    self.assertEqual(proc.get("status"), "captured",
                                     "%s/%s role %s not captured"
                                     % (run, phase, role))

    def test_snapshot_monotonic_ordering(self):
        for run, pin in sorted(SNAPSHOTS.items()):
            _, before = self._snap(run, "before")
            _, after = self._snap(run, "after")
            self.assertEqual(
                before["captured"]["monotonic_ns"], pin["monotonic_before"])
            self.assertEqual(
                after["captured"]["monotonic_ns"], pin["monotonic_after"])
            self.assertGreater(pin["monotonic_after"], pin["monotonic_before"])

    def test_result_json_chain_and_no_acceptance(self):
        for run, pin in sorted(SNAPSHOTS.items()):
            rel = "validation/coordination/%s/flight/result.json" % run
            raw = _anchor_bytes(rel)
            self.assertIsNotNone(raw)
            data = json.loads(raw.decode("utf-8"))
            self.assertEqual(data.get("run_id"), pin["run_id"])
            owned = data.get("owned_scheduling", {})
            self.assertEqual(owned.get("classification"), "diagnostic_only")
            self.assertIs(owned.get("full_acceptance"), False)
            for phase, key in (("before", "before_sha256"),
                               ("after", "after_sha256")):
                snap_raw, _ = self._snap(run, phase)
                self.assertEqual(
                    owned[phase].get("sha256"), pin[key],
                    "%s %s hash chain broken" % (run, phase))
                self.assertEqual(_sha256(snap_raw), pin[key])
            self.assertIs(data.get("flight_completed"), False)

    def test_boundary_language_in_sources(self):
        snapshot_doc = _anchor_bytes(
            "docs/coordination/owned-scheduling-snapshot-20260913.md")
        self.assertIn("不是 native 证据".encode("utf-8"), snapshot_doc)
        self.assertIn("performance_verdict".encode("ascii"), snapshot_doc)
        comparison_doc = _anchor_bytes(
            "docs/coordination/owned-scheduling-comparison-20260913.md")
        self.assertIn("主会话收口补记".encode("utf-8"), comparison_doc)
        self.assertIn(
            "13a61a7ffd92880571613c69d3d31736f1982e75ff03b365e2602338c928ec6f"
            .encode("ascii"), comparison_doc)
        e2e_doc = _anchor_bytes("docs/coordination/owned-scheduling-e2e-20260913.md")
        self.assertIn("不是 wksim run 行为证据".encode("utf-8"), e2e_doc)


class TestCandidatePaths(unittest.TestCase):

    @unittest.skipUnless(_env_facts()["anchor_reachable"],
                         "safe drift: pinned commit not reachable")
    def test_candidates_absent_at_anchor_commit(self):
        for rel in CANDIDATES:
            self.assertIsNone(
                _anchor_bytes(rel),
                "candidate path unexpectedly exists at pinned commit: %s" % rel)

    def test_candidates_exist_in_working_tree(self):
        for rel in CANDIDATES:
            path = os.path.join(REPO_ROOT, rel)
            self.assertTrue(os.path.isfile(path), "missing candidate: %s" % rel)
            with open(path, "rb") as handle:
                self.assertGreater(len(handle.read()), 0)

    def test_ingest_note_content_pin_and_boundary_language(self):
        path = os.path.join(REPO_ROOT, NOTE_REL)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertEqual(_sha256(raw), NOTE_SHA256,
                         "ingest note bytes changed; re-pin NOTE_SHA256")
        self.assertEqual(len(raw), NOTE_SIZE)
        text = raw.decode("utf-8")
        for needle in (
                "31e5b65f5448c5558450d16d0f46da0ef0f0a03c",
                "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",
                "diagnostic_only", "full_acceptance=false",
                "not_evaluated", "永不重跑", "不得宣称",
                "13a61a7ffd92880571613c69d3d31736f1982e75ff03b365e2602338c928ec6f",
                "20cc459052c2cf8d860e2c1583334e583abd3b95c3d022a8a0795580ab8642fe",
                "drift"):
            self.assertIn(needle, text, "ingest note missing marker: %r" % needle)
        # Forbidden claim forms; the note may mention "G6 PASS"/"Full PASS"
        # only inside its prohibition sentence, which is covered by the
        # required marker "不得宣称" above.
        for forbidden in ("已通过 G6", "已通过 Full", "flight_completed=true",
                          "full_acceptance=true", "verdict=\"pass\"",
                          "full_acceptance\": true"):
            self.assertNotIn(forbidden, text,
                             "ingest note must not claim: %r" % forbidden)

    def test_test_file_self_presence(self):
        path = os.path.join(REPO_ROOT, TEST_REL)
        with open(path, "rb") as handle:
            raw = handle.read()
        for needle in (b"Safe drift policy", b"ANCHOR_COMMIT",
                       b"TestCandidatePaths", b"validation/test_owned_scheduling_context.py"):
            self.assertIn(needle, raw)


class TestStagedIndexMode(unittest.TestCase):
    """Active only when GIT_INDEX_FILE points at a repo-external index."""

    def test_staged_index_contract(self):
        if not _env_facts()["index_mode"]:
            self.skipTest(
                "GIT_INDEX_FILE not set; index state intentionally not asserted")
        for rel in CANDIDATES:
            staged = _index_entry_blob_sha1(rel, use_index_env=True)
            self.assertIsNotNone(
                staged, "candidate not staged in the external index: %s" % rel)
            self.assertEqual(
                staged, _blob_sha1_file(rel),
                "staged blob differs from working-tree bytes: %s" % rel)
            real = _index_entry_blob_sha1(rel, use_index_env=False)
            self.assertIsNone(
                real,
                "real index must not contain the candidate; staging must be "
                "done only by the main agent with git add -f: %s" % rel)


if __name__ == "__main__":
    unittest.main()
