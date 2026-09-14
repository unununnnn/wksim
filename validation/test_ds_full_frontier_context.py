"""Offline context-binding tests for the ds-full-frontier snapshot ingest.

Scope (single file, fully offline, no network, no native/build/runtime runs):

* Bind the 2026-09-12 prior-slot snapshot
  ``docs/coordination/ds-full-frontier-20260912.json`` to SHA256
  ``3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4``
  (36161 bytes) and the ingest note
  ``docs/coordination/ds-full-frontier-ingest-note-20260914.md`` to SHA256
  ``7701eee11c91615c069fab26b309512830315c5f5d6cb62cb6ce87a41c8d9a61``.
* Strict-load the snapshot and the tracked attestation
  ``validation/coordination/ds-g0-g5-frontier-20260913-01/checks/checks.json``,
  rejecting duplicate keys, NaN/Infinity constants and ``1e999`` overflow.
* Assert the attestation contains exactly one record binding the original
  path/hash/size, and that tracked-file ``git grep`` for the exact original
  path, pathspec-scoped to the pinned evidence directory
  ``validation/coordination/ds-g0-g5-frontier-20260913-01``, hits exactly the
  four files under it. The scope makes the assertion staging-stable: staging
  the candidates (git grep enumerates staged-but-uncommitted files) cannot
  change a pathspec-scoped result; exact historical allowlist validation is
  retained inside that scope (review finding F-01).
* Assert the note binds context-only/non-current/non-authority semantics, the
  named supersession anchors — including the boundary-2 later-G6 records and
  the boundary-4 #26 audit-advancement evidence (review finding F-02) — the
  closure rule, R1 ``numerical_failed``, and the #83 non-acceptance boundary.
* Assert the representative supersession files and boundary anchors exist, are
  tracked, and that the binding baseline ``cc42c19f`` and ancestors
  ``e8defc1d``/``f333316e`` are ANCESTORS of whatever HEAD the suite runs at.
  HEAD equality with ``cc42c19f`` is deliberately NOT required, so the suite
  remains valid at future commits whose history contains the baseline (review
  finding F-04).

Binding the snapshot as context does NOT confer authority, approval,
acceptance, or any current Full/G0-G6 state; the note's semantics are asserted
fail-closed below.

Observed at binding baseline ``cc42c19f1b06538cf5bfd326d7dcd11f7b1ed6a5``.
"""

import copy
import hashlib
import json
import math
import os
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ORIGINAL_REL = "docs/coordination/ds-full-frontier-20260912.json"
NOTE_REL = "docs/coordination/ds-full-frontier-ingest-note-20260914.md"
CHECKS_REL = "validation/coordination/ds-g0-g5-frontier-20260913-01/checks/checks.json"
DS_G0_G5_DIR = "validation/coordination/ds-g0-g5-frontier-20260913-01"

ORIGINAL_SHA256 = "3fcf2003bc589b8692b95f350bf0b697dc52ac1567c9b8b98d2c32cd27c209c4"
ORIGINAL_SIZE = 36161
NOTE_SHA256 = "7701eee11c91615c069fab26b309512830315c5f5d6cb62cb6ce87a41c8d9a61"
# Binding baseline: must be an ANCESTOR of the running HEAD, never required
# to equal it (review finding F-04).
BASELINE_FULL = "cc42c19f1b06538cf5bfd326d7dcd11f7b1ed6a5"
ANCESTOR_FULL = "e8defc1d8317892e022ee24de086b026c1317e5a"

GIT_GREP_EXPECTED = sorted([
    DS_G0_G5_DIR + "/audit.json",
    DS_G0_G5_DIR + "/audit.md",
    DS_G0_G5_DIR + "/checks/checks.json",
    DS_G0_G5_DIR + "/verify_frontier.py",
])

SUPERSESSION_PATHS = [
    "docs/plan/full-acceptance-report.md",
    "docs/plan/9-vendor-abi-defer-boundary.json",
]

# Note §3 boundary 2: concrete tracked later-G6 records (all dated after the
# 2026-09-12 snapshot; the #59 packet is PROPOSED / effective:false — no
# approval or acceptance is claimed for it or for any G6 state).
G6_RECORD_PATHS = [
    "docs/plan/59-g6-solve-form-decision-20260914.md",
    "validation/e0-g6-solve-form-decision-20260914.json",
    "docs/plan/g6-c3g-stage2-boundary.md",
]

# Note §3 boundary 4: concrete tracked later-#26 audit evidence (hardened /
# added on 2026-09-14; evidences audit-work advancement only, NOT closure).
AUDIT26_PATHS = [
    "tools/audit_26_closure_readiness.py",
    "validation/test_audit_26_closure_readiness.py",
    "validation/test_audit_26_current_source_plan.py",
]

NOTE_BOUNDARY_PHRASES = [
    # context-only / non-current / non-authority semantics
    "context only, non-authoritative",
    "historical context only",
    "not the current Full-acceptance or G0",
    "not authority over any current plan, verdict, or frontier decision",
    "not approval of anything",
    "not acceptance of anything",
    "were not re-verified against GitHub",
]

NOTE_ANCHOR_PHRASES = [
    # named supersession anchors (boundaries 1 and 3)
    "docs/plan/full-acceptance-report.md",
    "docs/plan/9-vendor-abi-defer-boundary.json",
    # boundary 2: concrete tracked later-G6 records
    "docs/plan/59-g6-solve-form-decision-20260914.md",
    "validation/e0-g6-solve-form-decision-20260914.json",
    "docs/plan/g6-c3g-stage2-boundary.md",
    # boundary 2 honesty: the packet's own proposal layering is preserved
    "authority: proposal_only",
    # boundary 4: concrete tracked later-#26 audit evidence
    "tools/audit_26_closure_readiness.py",
    "validation/test_audit_26_closure_readiness.py",
    "validation/test_audit_26_current_source_plan.py",
    # boundary 4 honesty: no closure/approval invented
    "does not record #26 closure or",
    # closure rule (snapshot-preserved wording)
    "closure_rule_in_force",
    "父票只有在原 AC 与原 Blocked-by 同时满足时才可关闭",
    # R1 numerical_failed state
    "numerical_failed",
    "保持原状，不改判",
    # #83 offline-evidence binding is NOT acceptance
    "does **not** constitute Full/G6 acceptance",
]


# --------------------------------------------------------------------------
# Strict JSON loading
# --------------------------------------------------------------------------

def strict_loads(text):
    """json.loads rejecting duplicate keys, NaN/Infinity and 1e999 overflow."""
    def _no_duplicate_keys(pairs):
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError("duplicate JSON key(s): %s" % ", ".join(dupes))
        return dict(pairs)

    def _reject_constant(name):
        raise ValueError("non-finite JSON constant not allowed: %s" % name)

    def _parse_float(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("numeric overflow in JSON float: %s" % token)
        return value

    return json.loads(
        text,
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_constant,
        parse_float=_parse_float,
    )


# --------------------------------------------------------------------------
# Evidence helpers
# --------------------------------------------------------------------------

def read_repo_bytes(rel_path):
    with open(os.path.join(REPO_ROOT, rel_path), "rb") as handle:
        return handle.read()


def sha256_hex(raw_bytes):
    return hashlib.sha256(raw_bytes).hexdigest()


def git(*args):
    return subprocess.run(
        ["git"] + list(args), cwd=REPO_ROOT, capture_output=True, check=True
    )


def git_tracked(rel_path):
    return bool(git("ls-files", "-z", "--", rel_path).stdout.strip(b"\x00"))


def require_tracked_present(paths):
    failures = []
    for path in paths:
        if not os.path.exists(os.path.join(REPO_ROOT, path)):
            failures.append("%s (absent from working tree)" % path)
        if not git_tracked(path):
            failures.append("%s (not tracked in git index)" % path)
    if failures:
        raise ValueError("missing tracked reference(s): %s" % "; ".join(failures))


def require_phrases(text, phrases):
    missing = [phrase for phrase in phrases if phrase not in text]
    if missing:
        raise ValueError("missing required phrase(s): %s" % " | ".join(missing))


def bind_original(raw_bytes):
    digest = sha256_hex(raw_bytes)
    if digest != ORIGINAL_SHA256:
        raise ValueError(
            "original hash drift: expected %s, observed %s"
            % (ORIGINAL_SHA256, digest)
        )
    if len(raw_bytes) != ORIGINAL_SIZE:
        raise ValueError(
            "original size drift: expected %d, observed %d"
            % (ORIGINAL_SIZE, len(raw_bytes))
        )
    return digest


def bind_attestation(checks_data, original_digest):
    """Exactly one record in checks.json binding original path/hash/size."""
    records = []

    def _walk(value):
        if isinstance(value, dict):
            if value.get("path") == ORIGINAL_REL:
                records.append(value)
            for item in value.values():
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(checks_data)
    if len(records) != 1:
        raise ValueError(
            "expected exactly one attestation record for %s, found %d"
            % (ORIGINAL_REL, len(records))
        )
    record = records[0]
    if record.get("sha256") != original_digest:
        raise ValueError(
            "attestation hash drift: record %s, evidence %s"
            % (record.get("sha256"), original_digest)
        )
    if record.get("size_bytes") != ORIGINAL_SIZE:
        raise ValueError(
            "attestation size drift: record %r, expected %r"
            % (record.get("size_bytes"), ORIGINAL_SIZE)
        )
    return record


# --------------------------------------------------------------------------
# Positive tests
# --------------------------------------------------------------------------

class TestStrictJsonLoading(unittest.TestCase):
    def test_strict_loads_original_and_checks(self):
        original = strict_loads(read_repo_bytes(ORIGINAL_REL).decode("utf-8"))
        checks = strict_loads(read_repo_bytes(CHECKS_REL).decode("utf-8"))
        self.assertEqual(original["schema"], "wksim.ds-full-frontier.v1")
        self.assertEqual(checks["schema"], "wksim.ds-g0-g5-frontier-checks.v1")

    def test_rejects_duplicate_keys_nonfinite_and_overflow(self):
        for text in (
            '{"a": 1, "a": 2}',   # duplicate key
            '{"a": NaN}',          # non-finite constant
            '{"a": Infinity}',     # non-finite constant
            '{"a": 1e999}',        # numeric overflow
        ):
            with self.assertRaises(ValueError):
                strict_loads(text)


class TestOriginalSnapshotBinding(unittest.TestCase):
    def test_original_hash_and_size_bound(self):
        raw = read_repo_bytes(ORIGINAL_REL)
        self.assertEqual(bind_original(raw), ORIGINAL_SHA256)
        self.assertEqual(len(raw), ORIGINAL_SIZE)


class TestAttestationBinding(unittest.TestCase):
    def setUp(self):
        self.checks = strict_loads(read_repo_bytes(CHECKS_REL).decode("utf-8"))
        self.original_digest = sha256_hex(read_repo_bytes(ORIGINAL_REL))

    def test_attestation_exactly_one_record_binds_original(self):
        record = bind_attestation(self.checks, self.original_digest)
        self.assertIs(record["exists"], True)

    def test_git_grep_exact_four_tracked_files(self):
        # Pathspec-scoped to the pinned evidence directory (review finding
        # F-01): git grep enumerates staged-but-uncommitted files, so a global
        # grep would self-break once the candidates are staged. The scoped
        # result is invariant under staging and still pins the exact
        # historical four-file allowlist within the scope.
        result = git("grep", "-l", "-F", ORIGINAL_REL, "--", DS_G0_G5_DIR)
        found = sorted(result.stdout.decode("utf-8").splitlines())
        self.assertEqual(found, GIT_GREP_EXPECTED)
        self.assertTrue(
            all(path.startswith(DS_G0_G5_DIR + "/") for path in found),
            "scoped grep leaked outside the pinned evidence directory",
        )


class TestNoteBinding(unittest.TestCase):
    def setUp(self):
        self.raw = read_repo_bytes(NOTE_REL)
        self.text = self.raw.decode("utf-8")

    def test_note_hash_bound(self):
        self.assertEqual(sha256_hex(self.raw), NOTE_SHA256)

    def test_note_context_only_non_current_non_authority(self):
        require_phrases(self.text, NOTE_BOUNDARY_PHRASES)

    def test_note_supersession_closure_r1_and_83_boundary(self):
        require_phrases(self.text, NOTE_ANCHOR_PHRASES)
        # The note binds the original path/hash/size it ingests.
        require_phrases(self.text, [ORIGINAL_REL, ORIGINAL_SHA256])


class TestSupersessionAndAncestry(unittest.TestCase):
    def test_supersession_files_exist_and_are_tracked(self):
        require_tracked_present(SUPERSESSION_PATHS)
        require_tracked_present(G6_RECORD_PATHS)
        require_tracked_present(AUDIT26_PATHS)

    def test_binding_baseline_is_ancestor_of_running_head(self):
        # Review finding F-04: cc42c19f is the binding baseline, NOT a pin on
        # future HEAD equality. Exit 0 only when the ancestry holds, so the
        # suite stays valid at any descendant commit.
        git("merge-base", "--is-ancestor", BASELINE_FULL, "HEAD")
        git("merge-base", "--is-ancestor", ANCESTOR_FULL, "HEAD")


# --------------------------------------------------------------------------
# Focused negative tests (in-memory mutations only; no file is modified)
# --------------------------------------------------------------------------

class TestNegativeMutations(unittest.TestCase):
    def setUp(self):
        self.raw = read_repo_bytes(ORIGINAL_REL)
        self.checks = strict_loads(read_repo_bytes(CHECKS_REL).decode("utf-8"))
        self.note_text = read_repo_bytes(NOTE_REL).decode("utf-8")

    def test_hash_drift_and_malformed_json_rejected(self):
        drifted = self.raw.replace(b'"DS-D"', b'"DS-X"')
        self.assertNotEqual(sha256_hex(drifted), ORIGINAL_SHA256)
        with self.assertRaisesRegex(ValueError, "hash drift"):
            bind_original(drifted)
        for text in (
            '{"schema": "wksim.ds-full-frontier.v1", "schema": "dup"}',
            '{"schema": NaN}',
            '{"schema": 1e999}',
        ):
            with self.assertRaises(ValueError):
                strict_loads(text)

    def test_duplicate_and_drifted_attestation_rejected(self):
        record = bind_attestation(self.checks, sha256_hex(self.raw))
        duplicated = copy.deepcopy(self.checks)
        duplicated["pinned_artifacts"]["G4"].append(copy.deepcopy(record))
        with self.assertRaisesRegex(ValueError, "exactly one attestation record"):
            bind_attestation(duplicated, sha256_hex(self.raw))
        drifted = copy.deepcopy(self.checks)
        g4 = drifted["pinned_artifacts"]["G4"]
        target = next(entry for entry in g4 if entry["path"] == ORIGINAL_REL)
        target["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "attestation hash drift"):
            bind_attestation(drifted, sha256_hex(self.raw))

    def test_missing_note_boundary_rejected(self):
        require_phrases(self.note_text, NOTE_BOUNDARY_PHRASES)
        require_phrases(self.note_text, NOTE_ANCHOR_PHRASES)
        stripped = self.note_text.replace("context only, non-authoritative", "elided")
        with self.assertRaisesRegex(ValueError, "missing required phrase"):
            require_phrases(stripped, NOTE_BOUNDARY_PHRASES)
        # Removing a boundary-2 later-G6 anchor or a boundary-4 later-#26
        # anchor from the note must fail (review finding F-02 is enforced).
        for anchor in ("docs/plan/59-g6-solve-form-decision-20260914.md",
                       "tools/audit_26_closure_readiness.py"):
            stripped = self.note_text.replace(anchor, "elided")
            with self.assertRaisesRegex(ValueError, "missing required phrase"):
                require_phrases(stripped, NOTE_ANCHOR_PHRASES)

    def test_missing_ancestry_rejected(self):
        # The binding baseline is NOT an ancestor of the older e8defc1d
        # commit; the reversed direction must fail, proving the check is
        # directional.
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", BASELINE_FULL, ANCESTOR_FULL],
            cwd=REPO_ROOT, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_grep_allowlist_mutation_rejected(self):
        result = git("grep", "-l", "-F", ORIGINAL_REL, "--", DS_G0_G5_DIR)
        found = sorted(result.stdout.decode("utf-8").splitlines())
        self.assertEqual(found, GIT_GREP_EXPECTED)
        # A lost or gained anchor inside the scope must not pass.
        with self.assertRaises(AssertionError):
            self.assertEqual(found, GIT_GREP_EXPECTED[:-1])
        with self.assertRaises(AssertionError):
            self.assertEqual(found, GIT_GREP_EXPECTED + [GIT_GREP_EXPECTED[0]])


if __name__ == "__main__":
    unittest.main()
