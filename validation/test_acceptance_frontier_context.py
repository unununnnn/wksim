"""Offline context-binding tests for the untracked acceptance frontier document.

Scope (single file, fully offline, no network, no native/build/runtime runs):

* Bind the untracked context-only evidence document
  ``docs/coordination/acceptance-frontier.json`` to its pinned SHA256
  ``885ea287c58ee412a1577cff18428a8b9425ff4b70e0c0ed9433bf18d46a16c2`` exactly
  as recorded under ``host_bounded_gaps.acceptance_frontier`` in the tracked
  ``docs/plan/9-vendor-abi-defer-boundary.json``.
* Strict-load both JSON documents, rejecting duplicate object keys,
  ``NaN``/``Infinity``/``-Infinity`` literals and numeric overflow such as
  ``1e999``.
* Assert the frontier records version ``1.1`` and the exact five issue
  entries ``#62``/``#102``/``#83``/``#29``/``#26`` with no duplicates.
* Assert the exact single pin under the tracked defer-boundary JSON carries a
  matching path/hash and records the frontier as historical context
  (``tracked == false``).
* Assert every repository path referenced by the frontier is tracked in git
  and present in the working tree.

Explicitly OUTSIDE offline verification (see
``TestRecordedLiveStateOutsideOfflineVerification``):
  * GitHub issue ``state == "OPEN"`` and ``requires_owner_input`` are recorded
    snapshot fields of the pinned document only. Nothing here queries GitHub,
    and passing these tests does NOT claim issue acceptance, owner approval,
    dependency closure, or any decision about #9/#26/#29 or any other ticket.

Observed at authoritative HEAD ``e8defc1d8317892e022ee24de086b026c1317e5a``.
"""

import copy
import hashlib
import json
import math
import os
import re
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRONTIER_REL = "docs/coordination/acceptance-frontier.json"
DEFER_REL = "docs/plan/9-vendor-abi-defer-boundary.json"

FRONTIER_SHA256 = "885ea287c58ee412a1577cff18428a8b9425ff4b70e0c0ed9433bf18d46a16c2"

EXPECTED_ISSUE_ORDER = ["#62", "#102", "#83", "#29", "#26"]
EXPECTED_REPO_PATHS = [
    "tools/run_joint_scheduler_windows.py",
    "validation/lunar-29-terrain-reset-c8f05c6e",
    "docs/plan/29-terrain-closure-report.md",
    "docs/plan/26-closure-readiness-manifest.json",
    "docs/2026-09-10-generated-e0-lifecycle.md",
    "validation/codegen-e0-lifecycle-01/audit.json",
]

# Repository-relative location prefixes actually used by the pinned frontier
# document. The document is hash-pinned, so this bounded set is sufficient.
_REPO_PATH_PREFIXES = ("docs", "tools", "validation", "Simulator")
_REPO_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:%s)/[A-Za-z0-9_\-./]+" % "|".join(_REPO_PATH_PREFIXES)
)


# --------------------------------------------------------------------------
# Strict JSON loading
# --------------------------------------------------------------------------

def strict_loads(text):
    """json.loads with fail-closed rejection of unsafe JSON constructs.

    Rejects duplicate object keys, NaN/Infinity/-Infinity literals, and
    non-finite numeric overflow (e.g. ``1e999``).
    """
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


def git_tracked(rel_path):
    """True iff at least one index entry exists under rel_path (git ls-files)."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", rel_path],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return bool(result.stdout.strip(b"\x00"))


def load_frontier():
    raw = read_repo_bytes(FRONTIER_REL)
    return raw, strict_loads(raw.decode("utf-8"))


def load_defer():
    raw = read_repo_bytes(DEFER_REL)
    return raw, strict_loads(raw.decode("utf-8"))


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_strings(key)
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def extract_referenced_repo_paths(data):
    """Repository-relative paths referenced by the frontier document."""
    found = []
    for text in iter_strings(data):
        for match in _REPO_PATH_RE.findall(text):
            path = match.rstrip(".")
            if path not in found:
                found.append(path)
    return found


def frontier_issues(data):
    return [entry["issue"] for entry in data["acceptance_frontier"]]


# --------------------------------------------------------------------------
# Fail-closed binding checks (shared by positive and negative tests)
# --------------------------------------------------------------------------

def bind_frontier_hash(raw_bytes):
    digest = sha256_hex(raw_bytes)
    if digest != FRONTIER_SHA256:
        raise ValueError(
            "frontier hash drift: expected %s, observed %s"
            % (FRONTIER_SHA256, digest)
        )
    return digest


def validate_frontier(data):
    if data.get("version") != "1.1":
        raise ValueError("frontier version mismatch: %r" % data.get("version"))
    entries = data.get("acceptance_frontier")
    if not isinstance(entries, list):
        raise ValueError("acceptance_frontier must be a list")
    issues = frontier_issues(data)
    if len(issues) != len(set(issues)):
        raise ValueError("duplicate issue entries in frontier: %s" % issues)
    if issues != EXPECTED_ISSUE_ORDER:
        raise ValueError(
            "frontier issue set/order mismatch: expected %s, observed %s"
            % (EXPECTED_ISSUE_ORDER, issues)
        )
    return issues


def bind_defer_pin(defer_data, actual_frontier_digest):
    """Bind the exact single host_bounded_gaps pin to the frontier evidence."""
    gaps = defer_data.get("host_bounded_gaps")
    if not isinstance(gaps, dict):
        raise ValueError("host_bounded_gaps missing or malformed")
    matching = [
        (key, entry)
        for key, entry in gaps.items()
        if isinstance(entry, dict) and entry.get("path") == FRONTIER_REL
    ]
    if len(matching) != 1:
        raise ValueError(
            "expected exactly one host_bounded_gaps pin for %s, found %d"
            % (FRONTIER_REL, len(matching))
        )
    key, pin = matching[0]
    if key != "acceptance_frontier":
        raise ValueError("frontier pin carried under unexpected key: %s" % key)
    if pin.get("sha256") != actual_frontier_digest:
        raise ValueError(
            "pin hash drift: pin records %s, frontier evidence is %s"
            % (pin.get("sha256"), actual_frontier_digest)
        )
    if pin.get("tracked") is not False:
        raise ValueError(
            "tracked promotion rejected: context-only frontier pin must stay "
            "tracked=false, observed %r" % (pin.get("tracked"),)
        )
    # Exact single occurrence of the frontier path anywhere in the record.
    occurrences = [
        text for text in iter_strings(defer_data) if text == FRONTIER_REL
    ]
    if len(occurrences) != 1:
        raise ValueError(
            "frontier path must occur exactly once in the defer record, "
            "found %d occurrences" % len(occurrences)
        )
    return pin


def require_tracked_present(paths):
    failures = []
    for path in paths:
        if not os.path.exists(os.path.join(REPO_ROOT, path)):
            failures.append("%s (absent from working tree)" % path)
        if not git_tracked(path):
            failures.append("%s (not tracked in git index)" % path)
    if failures:
        raise ValueError("missing tracked reference(s): %s" % "; ".join(failures))


# --------------------------------------------------------------------------
# Positive tests
# --------------------------------------------------------------------------

class TestStrictJsonLoader(unittest.TestCase):
    def test_loads_both_real_documents(self):
        _, frontier = load_frontier()
        _, defer = load_defer()
        self.assertEqual(frontier["version"], "1.1")
        self.assertEqual(defer["schema"], "wksim.9-vendor-abi-defer-boundary.v1")

    def test_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            strict_loads('{"a": 1, "a": 2}')

    def test_rejects_nested_duplicate_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            strict_loads('{"outer": {"x": 1, "x": 2}}')

    def test_rejects_nan_infinity_constants(self):
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaisesRegex(ValueError, "non-finite JSON constant"):
                strict_loads('{"value": %s}' % literal)

    def test_rejects_numeric_overflow_1e999(self):
        with self.assertRaisesRegex(ValueError, "numeric overflow"):
            strict_loads('{"value": 1e999}')

    def test_rejects_malformed_json(self):
        for text in ('{"a": 1,}', '{"a": 1', "not json at all", '{"a": 1} trailing'):
            with self.assertRaises(ValueError):
                strict_loads(text)


class TestFrontierContextBinding(unittest.TestCase):
    """Binds the untracked frontier as context-only offline evidence."""

    def setUp(self):
        self.raw, self.data = load_frontier()

    def test_frontier_hash_matches_pinned_sha256(self):
        self.assertEqual(bind_frontier_hash(self.raw), FRONTIER_SHA256)

    def test_frontier_context_file_is_present(self):
        # Tracking can change during admission; the historical false value is
        # bound separately in TestDeferBoundaryPinBinding.
        self.assertTrue(os.path.exists(os.path.join(REPO_ROOT, FRONTIER_REL)))

    def test_version_is_1_1(self):
        self.assertEqual(self.data["version"], "1.1")

    def test_exact_five_issue_entries_in_order(self):
        self.assertEqual(frontier_issues(self.data), EXPECTED_ISSUE_ORDER)

    def test_issue_entries_have_no_duplicates(self):
        issues = frontier_issues(self.data)
        self.assertEqual(len(issues), len(set(issues)))

    def test_referenced_repo_paths_are_tracked_and_present(self):
        paths = extract_referenced_repo_paths(self.data)
        self.assertEqual(paths, EXPECTED_REPO_PATHS)
        require_tracked_present(paths)


class TestDeferBoundaryPinBinding(unittest.TestCase):
    """Binds the exact single pin in the tracked defer-boundary JSON."""

    def setUp(self):
        _, self.defer = load_defer()
        self.frontier_digest = sha256_hex(read_repo_bytes(FRONTIER_REL))

    def test_defer_boundary_is_tracked(self):
        self.assertTrue(git_tracked(DEFER_REL))

    def test_exactly_single_pin_for_frontier(self):
        pin = bind_defer_pin(self.defer, self.frontier_digest)
        self.assertEqual(pin["path"], FRONTIER_REL)

    def test_pin_hash_matches_frontier_evidence(self):
        self.assertEqual(self.frontier_digest, FRONTIER_SHA256)
        pin = bind_defer_pin(self.defer, self.frontier_digest)
        self.assertEqual(pin["sha256"], FRONTIER_SHA256)

    def test_pin_records_historical_tracked_false(self):
        pin = bind_defer_pin(self.defer, self.frontier_digest)
        self.assertIs(pin["tracked"], False)
        self.assertIn("untracked", pin["reason"])


class TestRecordedLiveStateOutsideOfflineVerification(unittest.TestCase):
    """Recorded snapshot fields only — explicitly OUTSIDE offline verification.

    These assertions describe what the pinned context document records at its
    ``generated_at`` timestamp. No GitHub query is performed. Passing these
    tests does NOT claim issue acceptance, owner approval, dependency closure,
    or any live repository/issue state; the authoritative live state remains
    with the repository owner on GitHub.
    """

    def setUp(self):
        _, self.data = load_frontier()

    def test_recorded_issue_states_are_open(self):
        for entry in self.data["acceptance_frontier"]:
            self.assertEqual(entry["state"], "OPEN")

    def test_recorded_requires_owner_input_flags_are_false(self):
        for entry in self.data["acceptance_frontier"]:
            self.assertIs(entry["requires_owner_input"], False)

    def test_no_acceptance_or_owner_approval_is_claimed_anywhere(self):
        _, defer = load_defer()
        self.assertIs(defer["policy"]["acceptance_claimed"], False)
        self.assertEqual(defer["policy"]["acceptance_status_recommended"], "not_ready")
        self.assertEqual(defer["owner_decision"]["state"], "not_made")
        self.assertIs(defer["owner_decision"]["rejection_decided"], False)
        self.assertIs(defer["owner_decision"]["closure_decided"], False)
        self.assertIs(defer["recommendation"]["proposed_actions"]["acceptance_granted"], False)
        self.assertIs(defer["recommendation"]["proposed_actions"]["github_mutated"], False)


# --------------------------------------------------------------------------
# Meaningful negative tests (in-memory mutations only; no file is modified)
# --------------------------------------------------------------------------

class TestNegativeMutations(unittest.TestCase):
    def setUp(self):
        self.raw, self.data = load_frontier()
        _, self.defer = load_defer()

    def test_hash_drift_rejected(self):
        drifted = self.raw.replace(b'"1.1"', b'"1.2"')
        self.assertNotEqual(sha256_hex(drifted), FRONTIER_SHA256)
        with self.assertRaisesRegex(ValueError, "hash drift"):
            bind_frontier_hash(drifted)

    def test_duplicate_issue_rejected(self):
        mutated = copy.deepcopy(self.data)
        mutated["acceptance_frontier"].append(
            copy.deepcopy(mutated["acceptance_frontier"][0])
        )
        with self.assertRaisesRegex(ValueError, "duplicate issue entries"):
            validate_frontier(mutated)

    def test_pin_drift_rejected(self):
        mutated = copy.deepcopy(self.defer)
        mutated["host_bounded_gaps"]["acceptance_frontier"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "pin hash drift"):
            bind_defer_pin(mutated, FRONTIER_SHA256)

    def test_tracked_promotion_rejected(self):
        mutated = copy.deepcopy(self.defer)
        mutated["host_bounded_gaps"]["acceptance_frontier"]["tracked"] = True
        with self.assertRaisesRegex(ValueError, "tracked promotion rejected"):
            bind_defer_pin(mutated, FRONTIER_SHA256)

    def test_malformed_json_rejected(self):
        for text in (
            '{"version": "1.1", "version": "1.0"}',  # duplicate key
            '{"version": NaN}',                       # non-finite constant
            '{"version": 1e999}',                     # numeric overflow
            '{"version": "1.1"',                      # truncation
        ):
            with self.assertRaises(ValueError):
                strict_loads(text)

    def test_missing_tracked_reference_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing tracked reference"):
            require_tracked_present(["docs/plan/definitely-not-a-repo-file.md"])


if __name__ == "__main__":
    unittest.main()
