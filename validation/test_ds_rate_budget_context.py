"""Historical-context binding tests for the DS rate-budget candidate.

Binds ``docs/coordination/ds-rate-budget-20260912.json`` (together with its
2026-09-14 ingest note) as **historical context only**, and verifies:

* strict JSON parsing (duplicate keys and nonfinite/overflow values rejected),
* the exact byte identity (SHA256 + size) of both input files,
* git ancestry of the generation/baseline commit ``7126d4d7`` and the
  architecture ancestor ``f333316e`` relative to the symbolic HEAD,
* the historical tool content hashes at ``f21fc3af`` and their supersession
  at ``75353c06`` and current HEAD,
* the tracked supersession anchors (``7bdfxkb_`` diagnostic analysis,
  the ``1w6dru32`` / #83 CLOSED record) as recorded history only,
* that ``checks.json`` records the bound file only as an untracked-status
  listing, not as a SHA attestation,
* the note's boundaries (historical context, non-authority, no acceptance,
  no closure, no owner approval, no native rerun), the four distinct control
  identities, the no-cross-run-monotonic-subtraction rule, the no-root-cause
  rule, and the cumulative increment identity arithmetic.

Offline and read-only: every test reads repository bytes (worktree files and
git objects).  No native/build/MATLAB/ROS/DDS/SITL/flight-controller/UE/
model/flight execution is performed and #83 is never rerun.  The suite is
descendant-safe: "current" git content is always read from the symbolic
``HEAD`` (never from a pinned commit), ancestry assertions only require
"is an ancestor of HEAD", no test asserts exact HEAD equality, and no test
asserts that the candidate files remain untracked.
"""

import copy
import hashlib
import json
import math
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ORIGINAL_REL = "docs/coordination/ds-rate-budget-20260912.json"
NOTE_REL = "docs/coordination/ds-rate-budget-ingest-note-20260914.md"

ORIGINAL_SHA256 = "b6db16e282e670177eba0b9ce43d5b637ff0845279d8101a430a808d39681b37"
ORIGINAL_SIZE = 32100
NOTE_SHA256 = "13e18676833ab21783953cb63f45135f3eb24e440e8401d99d6a254b4678dd1b"
NOTE_SIZE = 8751

BASELINE_COMMIT = "7126d4d774a33c7d4b2504b9931a93ac27d7fa51"
ARCH_COMMIT = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
HISTORICAL_TOOL_COMMIT = "f21fc3affa43df22e4a10c2b47ffae8f20361230"
SUPERSEDE_COMMIT = "75353c0600652a062491f306b584feeacb942255"

ANALYZER_REL = "tools/analyze_joint_rate_intervals.py"
TAIL_TEST_REL = "validation/test_rate_tail_contract.py"
ANALYZER_PIN = "c3ba9de8f4ac61d6b39750bdabed737915d85d3bee53d56fed8157237bca98b8"
TAIL_TEST_PIN = "8b468bb727213339962a3f42dac05f396bb898eafce564262499000a58c4fac0"

ANCHOR_ANALYSIS_REL = "docs/coordination/ds-7bdfxkb-diagnostic-analysis.json"
ANCHOR_MEASURED_REL = "docs/plan/33-rate-measured-candidate-20260912.md"
ANCHOR_PLAN_REL = "docs/plan/33-rate-next-diagnostic-20260912.md"
CHECKS_REL = "validation/coordination/ds-g0-g5-frontier-20260913-01/checks/checks.json"

FOUR_RUNS = ("zzmg3k47", "tpwl1k4p", "nqyqcagl", "8fmacpgy")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_worktree(rel: str) -> bytes:
    return (ROOT / rel).read_bytes()


def git(args, check=True):
    proc = subprocess.run(
        ["git", "-C", str(ROOT)] + args, capture_output=True
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            "git %s failed (rc=%s): %s"
            % (args, proc.returncode, proc.stderr.decode("utf-8", "replace"))
        )
    return proc


def git_text(args) -> str:
    return git(args).stdout.decode("utf-8")


def blob_sha256(rev: str, rel: str) -> str:
    return sha256_bytes(git(["cat-file", "blob", "%s:%s" % (rev, rel)]).stdout)


def is_tracked_at_head(rel: str) -> bool:
    return git(["ls-tree", "HEAD", "--", rel]).stdout.strip() != b""


def is_ancestor_of_head(sha: str) -> bool:
    return git(["merge-base", "--is-ancestor", sha, "HEAD"], check=False).returncode == 0


def _reject_nonfinite(node):
    if isinstance(node, float) and not math.isfinite(node):
        raise ValueError("nonfinite JSON number (overflow or NaN/Infinity)")
    if isinstance(node, dict):
        for value in node.values():
            _reject_nonfinite(value)
    elif isinstance(node, list):
        for value in node:
            _reject_nonfinite(value)


def strict_loads(text: str):
    """Strict JSON parse: reject duplicate keys, NaN/Infinity, overflow."""

    def object_pairs_hook(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise ValueError("duplicate JSON key: %r" % key)
            seen.add(key)
        return dict(pairs)

    def parse_constant(name):
        raise ValueError("nonfinite JSON constant: %s" % name)

    doc = json.loads(text, object_pairs_hook=object_pairs_hook, parse_constant=parse_constant)
    _reject_nonfinite(doc)
    return doc


def load_original():
    return strict_loads(read_worktree(ORIGINAL_REL).decode("utf-8"))


def load_note_text() -> str:
    return read_worktree(NOTE_REL).decode("utf-8")


def validate_control_identities(doc):
    """The four failing runs must carry four distinct control identities."""
    candidates, manifests = [], []
    for run in FOUR_RUNS:
        ident = doc["raw_failure_directories"][run]["identities"]
        candidates.append(ident["control_candidate"])
        manifests.append(ident["control_manifest_sha256"])
    if len(set(candidates)) != len(FOUR_RUNS):
        raise ValueError("control candidates must be four distinct values, got %r" % (candidates,))
    if len(set(manifests)) != len(FOUR_RUNS):
        raise ValueError("control manifest hashes must be four distinct values")


def validate_wall_origins(doc):
    """Cross-run monotonic origins must remain distinct (never one origin)."""
    origins = doc["identity_and_timeline"]["different_wall_origins"][
        "rate_request_or_latch_monotonic_ns"
    ]
    # the nqyqcagl origin is recorded under its latch-specific key
    origin_keys = ("zzmg3k47", "tpwl1k4p", "nqyqcagl_latch", "8fmacpgy")
    values = [origins[key] for key in origin_keys]
    if len(set(values)) != len(FOUR_RUNS):
        raise ValueError("monotonic origins across runs must stay distinct, got %r" % (values,))


def validate_increment_identity(doc):
    """Recompute the recorded latch-lateness identity for each failing run."""
    checks = doc["cumulative_increment_identity"]["checks_on_real_traces_read_only"]
    for run in FOUR_RUNS:
        measured = doc["measured_rate"][run]
        recorded = checks[run]
        if recorded["rate_jsonl_sha256"] != doc["raw_failure_directories"][run]["rate_jsonl_sha256"]:
            raise ValueError("rate_jsonl_sha256 mismatch for %s" % run)
        first = measured["first_group_start_lateness_ns"]
        creep = measured["creep_total_ns"]
        total = measured["rate_unmet_lateness_ns"]
        if recorded["latch_site"] == "begin_group_release_wait":
            terminal = total - measured["last_group_start_lateness_ns"]
            if terminal != measured["terminal_increment_over_last_group_start_ns"]:
                raise ValueError("terminal increment mismatch for %s" % run)
        else:
            terminal = measured["last_group_work_over_unattributed_ns"]
        if first + creep + terminal != total:
            raise ValueError(
                "increment identity fails for %s: %d + %d + %d != %d"
                % (run, first, creep, terminal, total)
            )
        expected_sum = "%d + %d + %d = %d" % (first, creep, terminal, total)
        if recorded["sum"] != expected_sum:
            raise ValueError("recorded sum string mismatch for %s" % run)


# ---------------------------------------------------------------------------
# test cases
# ---------------------------------------------------------------------------

class TestStrictParseAndBinding(unittest.TestCase):
    """Byte-level binding and strict parsing of the two input files."""

    def test_original_json_strict_parse_and_schema(self):
        doc = load_original()
        self.assertIsInstance(doc, dict)
        self.assertEqual(doc["schema"], "wksim.ds-rate-budget.v1")
        self.assertEqual(doc["generated_local_time"], "2026-09-12T21:18:00+09:00")
        self.assertIn("7126d4d", doc["workspace_checkout"])

    def test_strict_parser_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError):
            strict_loads('{"schema": "a", "schema": "b"}')
        mutated = load_original()
        mutated["measured_rate"]["zzmg3k47"]["complete_groups"] = 24665
        text = json.dumps(mutated)[:-1] + ', "owner": "injected duplicate"}'
        # a duplicated key at top level must be rejected when re-parsed
        top = json.dumps(mutated)
        duplicated = top[:-1] + ', "schema": "mutant"}'
        with self.assertRaises(ValueError):
            strict_loads(duplicated)

    def test_strict_parser_rejects_nonfinite_and_overflow_values(self):
        with self.assertRaises(ValueError):
            strict_loads('{"schema": NaN}')
        with self.assertRaises(ValueError):
            strict_loads('{"schema": Infinity}')
        with self.assertRaises(ValueError):
            strict_loads('{"schema": -Infinity}')
        with self.assertRaises(ValueError):
            strict_loads('{"x": 1e400}')  # overflow parses to inf, must be rejected
        self.assertTrue(math.isfinite(1.0))  # sanity: guard itself is live

    def test_bound_files_exact_hash_and_size(self):
        original = read_worktree(ORIGINAL_REL)
        note = read_worktree(NOTE_REL)
        self.assertEqual(sha256_bytes(original), ORIGINAL_SHA256)
        self.assertEqual(len(original), ORIGINAL_SIZE)
        self.assertEqual(sha256_bytes(note), NOTE_SHA256)
        self.assertEqual(len(note), NOTE_SIZE)

    def test_note_records_matching_original_hash_and_size(self):
        note = load_note_text()
        self.assertIn(ORIGINAL_SHA256, note)
        self.assertIn("32100 bytes", note)
        self.assertIn(BASELINE_COMMIT, note)
        self.assertIn(HISTORICAL_TOOL_COMMIT, note)
        self.assertIn(SUPERSEDE_COMMIT, note)
        self.assertIn("?? docs/coordination/ds-rate-budget-20260912.json", note)


class TestGitAncestryAndToolHashes(unittest.TestCase):
    """Ancestry anchors and historical tool content hashes."""

    def test_baseline_and_architecture_commits_are_ancestors_of_head(self):
        self.assertTrue(is_ancestor_of_head(BASELINE_COMMIT),
                        "generation/baseline commit 7126d4d7 must be an ancestor of HEAD")
        self.assertTrue(is_ancestor_of_head(ARCH_COMMIT),
                        "architecture ancestor f333316e must be an ancestor of HEAD")

    def test_json_tool_pins_match_f21fc3af_blob_content(self):
        doc = load_original()
        self.assertEqual(doc["method"]["per_file_sha256"][ANALYZER_REL], ANALYZER_PIN)
        self.assertEqual(doc["module_artifacts"][TAIL_TEST_REL], TAIL_TEST_PIN)
        self.assertEqual(blob_sha256(HISTORICAL_TOOL_COMMIT, ANALYZER_REL), ANALYZER_PIN)
        self.assertEqual(blob_sha256(HISTORICAL_TOOL_COMMIT, TAIL_TEST_REL), TAIL_TEST_PIN)

    def test_tool_content_superseded_at_75353c06_and_head(self):
        # at the superseding commit the content no longer matches the pins
        self.assertNotEqual(blob_sha256(SUPERSEDE_COMMIT, ANALYZER_REL), ANALYZER_PIN)
        self.assertNotEqual(blob_sha256(SUPERSEDE_COMMIT, TAIL_TEST_REL), TAIL_TEST_PIN)
        # and the pinned content is not the current HEAD content either
        self.assertNotEqual(blob_sha256("HEAD", ANALYZER_REL), ANALYZER_PIN)
        self.assertNotEqual(blob_sha256("HEAD", TAIL_TEST_REL), TAIL_TEST_PIN)


class TestSupersessionAnchorsAndChecksJson(unittest.TestCase):
    """Tracked supersession anchors, as recorded history only."""

    def test_tracked_supersession_anchors_exist_with_recorded_facts(self):
        for rel in (ANCHOR_ANALYSIS_REL, ANCHOR_MEASURED_REL, ANCHOR_PLAN_REL):
            self.assertTrue(is_tracked_at_head(rel), "expected tracked anchor: %s" % rel)
        analysis = strict_loads(
            git(["cat-file", "blob", "HEAD:%s" % ANCHOR_ANALYSIS_REL]).stdout.decode("utf-8")
        )
        self.assertEqual(analysis["schema"], "wksim.ds-rate-diagnostic-analysis.v1")
        self.assertEqual(analysis["run_id"], "joint-public-flight-7bdfxkb_")
        measured = git(["cat-file", "blob", "HEAD:%s" % ANCHOR_MEASURED_REL]).stdout.decode("utf-8")
        # recorded facts: public PV 1w6dru32 passed and #83 is CLOSED, no rerun,
        # and the diagnostic field never counts as #83 acceptance evidence
        self.assertIn("1w6dru32", measured)
        self.assertIn("CLOSED", measured)
        self.assertIn("#83 不重跑", measured)
        self.assertIn("7bdfxkb_", measured)
        self.assertIn("永不得充当 #83 通过证据", measured)

    def test_checks_json_records_untracked_listing_not_sha_attestation(self):
        self.assertTrue(is_tracked_at_head(CHECKS_REL))
        raw = git(["cat-file", "blob", "HEAD:%s" % CHECKS_REL]).stdout.decode("utf-8")
        checks = strict_loads(raw)
        self.assertEqual(checks["schema"], "wksim.ds-g0-g5-frontier-checks.v1")
        # the occurrence is the raw untracked-status listing ...
        self.assertIn("?? docs/coordination/ds-rate-budget-20260912.json", raw)
        # ... and the manifest carries no SHA256 attestation of the bound file
        self.assertNotIn(ORIGINAL_SHA256, raw)


class TestHistoricalContextBoundaries(unittest.TestCase):
    """Authority boundaries declared by the note and the original JSON."""

    def test_note_declares_historical_context_non_authority_only(self):
        note = load_note_text()
        self.assertIn("历史语境（historical context only）、非权威", note)
        self.assertIn("按字节绑定", note)
        self.assertIn("不构成 #83 的验收、批准、收口、复核或重跑许可", note)
        self.assertIn("必须由当前权威（主代理 / 主会话 / 人类裁决）基于**当下**的工件重新作出", note)

    def test_note_disclaims_acceptance_closure_owner_approval_native_rerun(self):
        note = load_note_text()
        self.assertIn("不授予任何验收、收口、owner 批准或 native 重跑许可", note)
        self.assertIn("未重跑 #83", note)
        self.assertIn("未暂存、未提交、未推送", note)
        self.assertIn("纯只读复核", note)

    def test_original_json_self_limits_to_diagnostic_evidence(self):
        doc = load_original()
        self.assertIn(
            "This file is diagnostic evidence only; it is not a rate pass, "
            "PV pass, or production performance claim.",
            doc["scope"],
        )
        limitations = "\n".join(doc["limitations"])
        self.assertIn("does not close #83, does not re-open any rate gate", limitations)
        non_attribution = "\n".join(doc["non_attribution"])
        self.assertIn(
            "No exclusive CPU, AP, PX4, scheduler, or DDS root cause is assigned",
            non_attribution,
        )
        self.assertIn("overlap is not causation", non_attribution)
        extrapolation = "\n".join(doc["extrapolation_limits"])
        self.assertIn("must not be extrapolated", extrapolation)
        self.assertIn("must not be merged", extrapolation)


class TestControlIdentitiesTimingAndMutations(unittest.TestCase):
    """Identity gates, timing gates, and in-memory negative mutations."""

    def test_four_distinct_control_identities_and_wall_origins(self):
        doc = load_original()
        validate_control_identities(doc)
        validate_wall_origins(doc)
        freeze = doc["next_minimal_diagnosis"]["identity_freeze"]
        self.assertIn("must never be mixed", freeze)
        origins = doc["identity_and_timeline"]["different_wall_origins"]
        self.assertIn("monotonic values across runs must never be subtracted",
                      origins["proof_origins_differ"])
        # the recorded proof that origins differ: tpwl1k4p (earlier calendar)
        # carries a larger monotonic value than 8fmacpgy (later calendar)
        o = origins["rate_request_or_latch_monotonic_ns"]
        self.assertGreater(o["tpwl1k4p"], o["8fmacpgy"])

    def test_increment_identity_arithmetic_and_negative_mutations(self):
        doc = load_original()
        validate_increment_identity(doc)
        rule = doc["method"]["wall_clock_rule"]
        self.assertIn("No value from one run's wall/monotonic origin is "
                      "subtracted from another run's value", rule)

        # mutant 1: perturb creep_total_ns so the recorded identity no longer closes
        mutant = copy.deepcopy(doc)
        mutant["measured_rate"]["zzmg3k47"]["creep_total_ns"] += 1
        with self.assertRaises(ValueError):
            validate_increment_identity(mutant)

        # mutant 2: perturb the recorded sum string
        mutant = copy.deepcopy(doc)
        mutant["cumulative_increment_identity"]["checks_on_real_traces_read_only"][
            "nqyqcagl"]["sum"] = "115025 + 97921130 + 6224284 = 104260440"
        with self.assertRaises(ValueError):
            validate_increment_identity(mutant)

        # mutant 3: collapse two control identities into one
        mutant = copy.deepcopy(doc)
        mutant["raw_failure_directories"]["tpwl1k4p"]["identities"][
            "control_candidate"] = "0DQQz9"
        with self.assertRaises(ValueError):
            validate_control_identities(mutant)

        # mutant 4: collapse two monotonic origins (would license cross-run subtraction)
        mutant = copy.deepcopy(doc)
        origins = mutant["identity_and_timeline"]["different_wall_origins"][
            "rate_request_or_latch_monotonic_ns"]
        origins["tpwl1k4p"] = origins["8fmacpgy"]
        with self.assertRaises(ValueError):
            validate_wall_origins(mutant)

        # mutant 5: detach a rate trace identity from its run record
        mutant = copy.deepcopy(doc)
        mutant["cumulative_increment_identity"]["checks_on_real_traces_read_only"][
            "8fmacpgy"]["rate_jsonl_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_increment_identity(mutant)


if __name__ == "__main__":
    unittest.main()
