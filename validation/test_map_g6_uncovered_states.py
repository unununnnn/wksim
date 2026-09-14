"""Offline tests for the G6 36-state coverage map (2026-09-14).

Run from the repository root::

    python -B -m unittest validation.test_map_g6_uncovered_states

Scope: pure Python, fully offline, no network, no MATLAB/native/ROS/DDS/SITL/
flight/UE/#83 execution, no build, no model run, no real staging/commit/push.
The suite reads only repository-tracked evidence plus the declared on-disk
provenance path, rebuilds the map from those bytes, and proves the map is
deterministic, structurally closed, and fail-closed under negative mutations.

Staging model: every git invocation here is index-independent or index-reading
only (``rev-parse``, ``cat-file``, ``merge-base --is-ancestor``, the
anchor-evidence ``diff --name-only``, and the exact4 helper's ``ls-files
--cached``).  Nothing writes the shared real index.  The suite therefore passes
both in the normal untracked mode and under a repo-external temporary
``GIT_INDEX_FILE`` in which exactly the four candidate files (the generator,
the map JSON, this test, and the plan document) are force-added (``exact4``).
Staging is exercised by the runner, never against the real index.

Pinned to the frozen anchor ee6eb88819cefe255f22e788c39a77c0bbab490e.  The
evidence tree and the tracked-membership flags are read at that anchor; the
live HEAD is observed only to prove anchor ancestry and zero pinned-evidence
drift, and is never embedded in the artifact.  r1_status is numerical_failed
and #84 / G6 / Full remain open; this map is a coverage inventory and confers
no acceptance, approval, budget, or closure.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.map_g6_uncovered_states import (  # noqa: E402
    ANCESTOR,
    ANCHOR,
    ARCHIVE,
    COVERED_COUNT,
    COVERED_HI,
    COVERED_LO,
    DEFAULT_OUT,
    DERIVED_PINS,
    EVIDENCE_PINS,
    NONCLAIMS,
    SCHEMA,
    TOTAL_STATES,
    TRACE_STAGE2_PQR_HEX,
    UNCOVERED_COUNT,
    build_map,
    dumps,
    validate,
    write_map,
)

MAP_RELATIVE = DEFAULT_OUT
MAP_PATH = ROOT / MAP_RELATIVE
GENERATOR_RELATIVE = "tools/map_g6_uncovered_states.py"
TEST_RELATIVE = "validation/test_map_g6_uncovered_states.py"
PLAN_RELATIVE = "docs/plan/59-g6-uncovered-state-map-20260914.md"

# The four candidate files staged under a repo-external temporary
# GIT_INDEX_FILE (exact4 staging).
STAGING_PATHS = [GENERATOR_RELATIVE, MAP_RELATIVE, TEST_RELATIVE, PLAN_RELATIVE]

TRACKED_PIN_KEYS = tuple(sorted(EVIDENCE_PINS))
DERIVED_PIN_KEYS = tuple(sorted(DERIVED_PINS))
ALL_PIN_TABLES = (("pins", EVIDENCE_PINS), ("derived_pins", DERIVED_PINS))

R1_STATUS = "numerical_failed"

ENTRY_REQUIRED_KEYS = {
    "block_symbol", "block_symbol_range", "covered", "entry_class", "entry_kind",
    "entry_reason", "index", "reference_source", "source_line_mapping",
    "symbol_evidence", "symbol_note", "symbol_resolution", "symbol_source",
    "trace_source", "tracked_doc_refs", "tracked_line_bindings",
}
ENTRY_EXTRA_KEYS = {"untracked_provenance", "mrdivide_output_evidence",
                    "output_encoding"}


def _load_map():
    raw = MAP_PATH.read_bytes()
    return json.loads(raw.decode("utf-8")), raw


def _git(*args, check=True):
    return subprocess.run(["git"] + list(args), cwd=str(ROOT),
                          capture_output=True, check=check)


def _anchor_blob(rel_path):
    """Anchor-tree blob bytes, or None when the path is not in the anchor tree."""
    result = _git("cat-file", "blob", "%s:%s" % (ANCHOR, rel_path), check=False)
    return result.stdout if result.returncode == 0 else None


def _tracked_at_anchor(rel_path):
    return _anchor_blob(rel_path) is not None


def _clean_env():
    return {key: value for key, value in os.environ.items()
            if key != "GIT_INDEX_FILE"}


def _staged_mode():
    """True when GIT_INDEX_FILE points at a repo-external temporary index."""
    value = os.environ.get("GIT_INDEX_FILE")
    if not value:
        return False
    index = Path(value).resolve()
    try:
        index.relative_to(ROOT)
    except ValueError:
        return True
    return False


def _staged_paths():
    """Paths present in the active index (the temp index under exact4)."""
    result = _git("ls-files", "--cached", "-z", check=False)
    if result.returncode != 0:
        return set()
    return set(result.stdout.decode("utf-8", "replace").split("\0")) - {""}


def _staged_blob(rel_path):
    result = _git("cat-file", "blob", ":%s" % rel_path, check=False)
    return result.stdout if result.returncode == 0 else None


class TestCommittedMap(unittest.TestCase):
    """The committed map matches a fresh rebuild, byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.document, cls.raw = _load_map()
        cls.rebuilt = build_map(ROOT)

    def test_regeneration_is_byte_identical_and_valid(self):
        self.assertEqual(dumps(self.rebuilt).encode("utf-8"), self.raw)
        self.assertEqual(dumps(build_map(ROOT)).encode("utf-8"), self.raw)
        result = validate(self.document, repo_root=ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["codes"], [])

    def test_writer_creates_new_files_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "map.json"
            digest = write_map(self.rebuilt, target)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                             digest)
            with self.assertRaises(FileExistsError):
                write_map(self.rebuilt, target)

    def test_schema_kind_version_and_identity_keys(self):
        document = self.document
        self.assertEqual(document["schema"], SCHEMA)
        self.assertEqual(document["kind"], "g6_uncovered_state_map")
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["issue"], "#59")
        self.assertEqual(document["work_class"], "new-development")
        self.assertEqual(document["authority"], "none")
        self.assertIs(document["effective"], False)
        self.assertEqual(document["identity"]["nXc"], TOTAL_STATES)
        self.assertEqual(document["identity"]["flat_index_domain"], [0, 35])


class TestCoverageCounts(unittest.TestCase):
    """36 indices, 13 covered (6..18), 23 uncovered (0..5, 19..35)."""

    @classmethod
    def setUpClass(cls):
        cls.document, _ = _load_map()
        cls.entries = cls.document["index_map"]

    def test_index_domain_is_unique_contiguous_and_counted(self):
        indices = [entry["index"] for entry in self.entries]
        self.assertEqual(indices, list(range(TOTAL_STATES)))
        self.assertEqual(len(set(indices)), TOTAL_STATES)
        covered = [e["index"] for e in self.entries if e["covered"]]
        uncovered = [e["index"] for e in self.entries if not e["covered"]]
        self.assertEqual(len(covered), COVERED_COUNT)
        self.assertEqual(len(uncovered), UNCOVERED_COUNT)
        self.assertEqual(covered, list(range(COVERED_LO, COVERED_HI + 1)))
        self.assertEqual(uncovered, list(range(0, 6)) + list(range(19, 36)))
        counts = self.document["counts"]
        self.assertEqual(counts["total_states"], 36)
        self.assertEqual(counts["covered_states"], 13)
        self.assertEqual(counts["uncovered_states"], 23)
        self.assertEqual(counts["covered_block"], [6, 18])
        self.assertEqual(counts["covered_indices"], list(range(6, 19)))
        self.assertEqual(counts["uncovered_indices"],
                         list(range(0, 6)) + list(range(19, 36)))

    def test_covered_entries_name_their_tracked_sources(self):
        for entry in self.entries:
            if not entry["covered"]:
                continue
            with self.subTest(index=entry["index"]):
                self.assertEqual(entry["symbol_resolution"], "resolved")
                self.assertEqual(entry["symbol_evidence"],
                                 "tracked_comparison_v2_target_indices")
                self.assertTrue(entry["trace_source"])
                self.assertTrue(entry["reference_source"])
                self.assertTrue(entry["tracked_line_bindings"])

    def test_covering_classes_are_confined_to_the_residual_entries(self):
        allowed = {"mrdivide_residual_input", "out_of_mrdivide_path"}
        for entry in self.entries:
            if not entry["covered"]:
                continue
            with self.subTest(index=entry["index"]):
                self.assertIn(entry["entry_class"], allowed)
                if entry["index"] in (10, 11, 12):
                    self.assertEqual(entry["entry_class"],
                                     "mrdivide_residual_input")
                else:
                    self.assertEqual(entry["entry_class"],
                                     "out_of_mrdivide_path")


class TestTrackedEvidenceBindings(unittest.TestCase):
    """Every pin is bound, and every tracked claim is verified at the anchor."""

    @classmethod
    def setUpClass(cls):
        cls.document, _ = _load_map()

    def test_every_pin_is_bound_and_anchor_membership_is_truthful(self):
        for container_key, table in ALL_PIN_TABLES:
            for key in sorted(table):
                with self.subTest(pin=key):
                    pin = self.document[container_key][key]
                    self.assertEqual(pin["path"], table[key])
                    raw = (ROOT / pin["path"]).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),
                                     pin["sha256"], key)
                    self.assertEqual(len(raw), pin["size"], key)
                    blob = _anchor_blob(pin["path"])
                    self.assertEqual(pin["tracked_at_anchor"], blob is not None,
                                     key)
                    if blob is not None:
                        self.assertEqual(hashlib.sha256(blob).hexdigest(),
                                         pin["sha256"], key)

    def test_candidates_are_absent_from_anchor_and_staged_under_exact4(self):
        # The map JSON and the plan document are outputs, not pins; the two
        # source candidates were added after the anchor, so they are never in
        # the anchor tree.  Under the exact4 run they are force-added to the
        # repo-external temp index.  No commit is performed here.
        staged = _staged_paths() if _staged_mode() else set()
        for rel in (GENERATOR_RELATIVE, TEST_RELATIVE):
            self.assertTrue((ROOT / rel).exists(), rel)
            self.assertFalse(_tracked_at_anchor(rel),
                             f"{rel} must be absent from the anchor tree")
            if _staged_mode():
                self.assertIn(rel, staged, rel)
        for rel in STAGING_PATHS:
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_anchor_and_ancestors_are_recorded_and_verified(self):
        self.assertEqual(self.document["anchor"], ANCHOR)
        self.assertEqual(self.document["base_ancestor"], ANCESTOR)
        # The observed HEAD is observational only and must not be embedded.
        self.assertNotIn("head", self.document)
        observed = _git("rev-parse", "HEAD").stdout.decode().strip()
        if observed != ANCHOR:
            self.assertNotIn(observed, MAP_PATH.read_text(encoding="utf-8"))
        # The frozen anchor and the base ancestor are ancestors of HEAD.
        anchor = _git("merge-base", "--is-ancestor", ANCHOR, "HEAD",
                      check=False)
        self.assertEqual(anchor.returncode, 0)
        ancestor = _git("merge-base", "--is-ancestor", ANCESTOR, "HEAD",
                        check=False)
        self.assertEqual(ancestor.returncode, 0)
        # Zero pinned-evidence paths changed in anchor..HEAD.
        diff = _git("diff", "--name-only", ANCHOR, "HEAD", "--",
                    *sorted(EVIDENCE_PINS.values()), check=False)
        self.assertEqual(diff.returncode, 0)
        self.assertEqual(diff.stdout.decode("utf-8").strip(), "")
        # validate() itself enforces the anchor relationship fail-closed.
        result = validate(self.document, repo_root=ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertNotIn("anchor_not_ancestor", result["codes"])
        self.assertNotIn("evidence_drift", result["codes"])

    def test_line_bindings_match_worktree_and_anchor_bytes(self):
        for binding in self.document["line_bindings"]:
            with self.subTest(binding=binding["key"]):
                lines = (ROOT / binding["path"]).read_text(
                    encoding="utf-8").splitlines()
                self.assertEqual(binding["tracked_at_anchor"], True)
                self.assertGreaterEqual(binding["line_start"], 1)
                self.assertLessEqual(binding["line_end"], len(lines))
                self.assertEqual(
                    lines[binding["line_start"] - 1:binding["line_end"]],
                    binding["text"])
                self.assertTrue(any(t.strip() for t in binding["text"]))
                blob = _anchor_blob(binding["path"])
                self.assertIsNotNone(blob, binding["path"])
                self.assertEqual(hashlib.sha256(blob).hexdigest(),
                                 binding["sha256"])
                anchor_lines = blob.decode("utf-8").splitlines()
                self.assertEqual(
                    anchor_lines[binding["line_start"] - 1:binding["line_end"]],
                    binding["text"])

    def test_exact4_staging_binds_the_same_bytes(self):
        if not _staged_mode():
            self.skipTest("only meaningful under a repo-external GIT_INDEX_FILE")
        staged = _staged_paths()
        for rel in STAGING_PATHS:
            self.assertIn(rel, staged, rel)
            self.assertEqual(_staged_blob(rel), (ROOT / rel).read_bytes(), rel)
        # Every pin that is absent from the anchor tree is one of the new
        # sources and must be staged byte-identically in the temp index.
        for container_key, table in ALL_PIN_TABLES:
            for key, rel_path in sorted(table.items()):
                pin = self.document[container_key][key]
                if pin["tracked_at_anchor"]:
                    continue
                with self.subTest(pin=key):
                    self.assertIn(rel_path, STAGING_PATHS, key)
                    self.assertEqual(_staged_blob(rel_path),
                                     (ROOT / rel_path).read_bytes(), key)


class TestMrdivideClassification(unittest.TestCase):
    """Only the supported mrdivide entry is classified; nothing physical."""

    @classmethod
    def setUpClass(cls):
        cls.document, _ = _load_map()
        cls.entries = {e["index"]: e for e in cls.document["index_map"]}

    def test_entry_classes_are_closed_and_physical_semantics_absent(self):
        classes = self.document["entry_classes"]
        self.assertEqual(classes["mrdivide_residual_input_indices"], [10, 11, 12])
        self.assertEqual(classes["mrdivide_output_indices"], [10, 11, 12])
        self.assertIs(classes["physical_semantics_inferred"], False)
        self.assertEqual(sorted(classes["supported"]),
                         ["mrdivide_output", "mrdivide_residual_input",
                          "out_of_mrdivide_path"])
        for entry in self.document["index_map"]:
            with self.subTest(index=entry["index"]):
                self.assertIn(entry["entry_class"], classes["supported"])
                self.assertLessEqual(set(entry), ENTRY_REQUIRED_KEYS |
                                     ENTRY_EXTRA_KEYS)
                self.assertTrue(ENTRY_REQUIRED_KEYS <= set(entry))

    def test_residual_entries_carry_line_anchors_and_trace_divergence(self):
        for index in (10, 11, 12):
            entry = self.entries[index]
            self.assertIn("untracked_provenance", entry)
            self.assertEqual(entry["source_line_mapping"],
                             "mapped_via_untracked_generated_cpp")
            self.assertEqual(entry["entry_kind"], "mrdivide_numerator_vector")
            self.assertTrue(entry["tracked_line_bindings"])
        divergence = self.entries[11]["mrdivide_output_evidence"]
        self.assertEqual(divergence["target_trace_hex"], "bc56d4db33a987b9")
        self.assertEqual(divergence["comparison_v2_reference_hex"],
                         "bc56d4db33a987b8")
        self.assertEqual(divergence["ulp"], 1)
        self.assertEqual(
            self.entries[11]["output_encoding"]["result_equals_derivative_slice"],
            [10, 13])
        self.assertEqual(
            self.entries[11]["output_encoding"]["hex_stage2"],
            list(TRACE_STAGE2_PQR_HEX))

    def test_output_encoding_hex_matches_the_pinned_trace(self):
        lines = [json.loads(line) for line in (
            ROOT / "validation/coordination/g6-target-first-step-20260913/"
                   "first-step-trace.jsonl").read_text(
                       encoding="utf-8").splitlines() if line.strip()]
        stage2 = [row for row in lines
                  if row.get("kind") == "ode4_stage"
                  and row.get("stage") == 2][0]
        deriv = [str(h).lower().replace("0x", "") for h in stage2["deriv_hex"]]
        self.assertEqual(
            self.entries[11]["output_encoding"]["hex_stage2"], deriv[10:13])
        self.assertEqual(deriv[10:13], list(TRACE_STAGE2_PQR_HEX))

    def test_declared_provenance_never_becomes_a_tracked_claim(self):
        for key, item in self.document["untracked_provenance"].items():
            with self.subTest(provenance=key):
                self.assertIs(item["tracked_at_anchor"], False)
                self.assertEqual(item["expected_sha256"],
                                 "a35d7c8f39c94f2db8c27b19affee5b66c1b001c63de"
                                 "d334ba83c99f8be54019")
                if item["available_on_disk"]:
                    raw = (ROOT / item["path"]).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),
                                     item["sha256"])
                    self.assertIs(item["matches_expected"], True)
                else:
                    self.assertIsNone(item["sha256"])

    def test_divergence_pair_matches_the_tracked_trace_and_comparison(self):
        divergence = self.document["divergence_pair"]
        lines = [json.loads(line) for line in (
            ROOT / "validation/coordination/g6-target-first-step-20260913/"
                   "first-step-trace.jsonl").read_text(
                       encoding="utf-8").splitlines() if line.strip()]
        stage2 = [row for row in lines
                  if row.get("kind") == "ode4_stage" and row.get("stage") == 2][0]
        self.assertEqual(
            stage2["deriv_hex"][divergence["index"]].lower().replace("0x", ""),
            divergence["target_trace_hex"])
        comparison = json.loads((
            ROOT / "validation/coordination/g6-target-first-step-20260913/"
                   "comparison-v2.json").read_text(encoding="utf-8"))
        pqr = [block for block in comparison["blocks"]
               if block["block"] == "p,q,r"][0]
        pair = [diff for diff in pqr["stage_differences"]
                if diff["stage"] == 2 and diff["index"] == 1][0]
        self.assertEqual(pair["reference_hex"],
                         divergence["comparison_v2_reference_hex"])
        self.assertEqual(pair["target_hex"],
                         divergence["comparison_v2_target_hex"])


class TestUnresolvedAndNonclaims(unittest.TestCase):
    """Unresolved fields and nonclaims are required and stable."""

    @classmethod
    def setUpClass(cls):
        cls.document, _ = _load_map()

    def test_unresolved_items_keep_their_archive_identity(self):
        ids = {item["id"] for item in self.document["unresolved"]}
        for required in ("archive_source_line_mapping",
                         "authoritative_state_layout",
                         "transferfcn_motor_symbol_order",
                         "unmapped_reference_states"):
            self.assertIn(required, ids)
        for item in self.document["unresolved"]:
            with self.subTest(item=item["id"]):
                self.assertEqual(item["status"], "unresolved")
                if item["requires"] == "model_archive":
                    self.assertEqual(item["requires_sha256"], ARCHIVE["sha256"])
                    self.assertTrue(item["requires_path"])

    def test_unmapped_indices_are_declared_unresolved(self):
        for entry in self.document["index_map"]:
            if entry["covered"]:
                continue
            with self.subTest(index=entry["index"]):
                self.assertEqual(entry["source_line_mapping"],
                                 "unresolved_requires_archive_input")
                self.assertEqual(entry["entry_class"], "out_of_mrdivide_path")

    def test_symbol_order_conflict_is_recorded_for_19_to_35(self):
        conflicts = {item["id"]: item
                     for item in self.document["symbol_conflicts"]}
        conflict = conflicts["transferfcn_motor_order"]
        self.assertEqual(conflict["scope"], "indices 19..35")
        self.assertEqual(conflict["resolution"],
                         "conflicted_requires_archive_input")
        self.assertEqual(conflict["requires_member"], ARCHIVE["header_member"])
        unresolved = {item["id"]: item
                      for item in self.document["unresolved"]}
        self.assertEqual(
            unresolved["transferfcn_motor_symbol_order"]["scope"],
            "indices 19..35")
        # The disagreement covers indices 19..24 and is never resolved; the
        # covered and block-agreed ranges stay resolved.
        for entry in self.document["index_map"]:
            with self.subTest(index=entry["index"]):
                if 19 <= entry["index"] <= 35:
                    self.assertEqual(entry["symbol_resolution"],
                                     "conflicted_requires_archive_input")
                else:
                    self.assertEqual(entry["symbol_resolution"], "resolved")
        policy = self.document["evidence_policy"]
        self.assertIs(policy["tracked_evidence_only"], True)
        self.assertIs(policy["frozen_archive_required"], True)
        self.assertEqual(policy["archive"]["sha256"], ARCHIVE["sha256"])
        self.assertEqual(policy["requires_tracked_at_anchor"],
                         sorted(TRACKED_PIN_KEYS))

    def test_nonclaims_boundary_and_open_items(self):
        self.assertEqual(self.document["nonclaims"], list(NONCLAIMS))
        blob = " ".join(self.document["nonclaims"]).lower()
        for needle in ("g6", "r1", "physical", "closure", "budget"):
            self.assertIn(needle, blob)
        self.assertEqual(self.document["r1_status"], R1_STATUS)
        self.assertIs(self.document["g6_acceptance"], False)
        self.assertIs(self.document["physical_accuracy"], False)
        self.assertIs(self.document["issues_closed"], False)
        self.assertIs(self.document["budget_approved"], False)
        self.assertEqual(self.document["pending_approvals"], [])
        states = {item["id"]: item["state"]
                  for item in self.document["open_items"]}
        self.assertEqual(states.get("issue_84"), "open")
        self.assertEqual(states.get("g6"), "open")
        self.assertEqual(states.get("full"), "open")
        for entry in self.document["index_map"]:
            self.assertNotIn("budget", entry)
            self.assertNotIn("approval", entry)


class TestNegativeMutations(unittest.TestCase):
    """The validator fails closed on every malformed mutation."""

    @classmethod
    def setUpClass(cls):
        cls.base, _ = _load_map()

    def _mutated(self, mutate):
        document = copy.deepcopy(self.base)
        mutate(document)
        return document

    def assertRejects(self, mutate, code):
        result = validate(self._mutated(mutate), repo_root=ROOT)
        self.assertFalse(result["ok"], f"{code} not detected")
        self.assertIn(code, result["codes"], result["errors"])

    def test_mutation_table(self):
        cases = [
            ("index_domain_incomplete",
             lambda d: d["index_map"].pop(7)),
            ("duplicate_index",
             lambda d: d["index_map"].__setitem__(
                 8, copy.deepcopy(d["index_map"][9]))),
            ("index_order",
             lambda d: d.__setitem__(
                 "index_map", d["index_map"][:3] + [d["index_map"][5],
                                                    d["index_map"][4]]
                 + d["index_map"][6:])),
            ("index_out_of_domain",
             lambda d: d["index_map"][36 - 1].__setitem__("index", 36)),
            ("count_mismatch",
             lambda d: d["counts"].__setitem__("covered_states", 14)),
            ("covered_count_disagrees",
             lambda d: (d["index_map"][0].__setitem__("covered", True),
                        d["counts"].__setitem__("covered_indices",
                                                list(range(0, 19))))),
            ("uncovered_count_disagrees",
             lambda d: (d["index_map"][36 - 1].__setitem__("covered", True),
                        d["counts"].__setitem__("covered_states", 14),
                        d["counts"].__setitem__("covered_indices",
                                                list(range(0, 19))),
                        d["counts"].__setitem__(
                            "uncovered_indices",
                            list(range(0, 6)) + list(range(19, 36))))),
            ("coverage_flag_mismatch",
             lambda d: d["index_map"][5].__setitem__("covered", True)),
            ("uncovered_class_not_outside",
             lambda d: d["index_map"][0].__setitem__(
                 "entry_class", "mrdivide_output")),
            ("residual_class_mismatch",
             lambda d: d["index_map"][10].__setitem__(
                 "entry_class", "out_of_mrdivide_path")),
            ("unknown_entry_class",
             lambda d: d["index_map"][4].__setitem__(
                 "entry_class", "physical_thrust_state")),
            ("unknown_symbol_resolution",
             lambda d: d["index_map"][30].__setitem__(
                 "symbol_resolution", "guessed")),
            ("unknown_source_line_status",
             lambda d: d["index_map"][3].__setitem__(
                 "source_line_mapping", "known")),
            ("resolved_symbol_without_exact_source",
             lambda d: d["index_map"][2].__setitem__(
                 "symbol_evidence", "invented")),
            ("block_symbol_range_invalid",
             lambda d: d["index_map"][13].__setitem__(
                 "block_symbol_range", [14, 15])),
            ("index_entry_extra_key",
             lambda d: d["index_map"][2].__setitem__("budget", 1)),
            ("index_entry_missing_key",
             lambda d: d["index_map"][2].pop("symbol_note")),
            ("missing_key",
             lambda d: d.pop("nonclaims")),
            ("version_mismatch",
             lambda d: d.__setitem__("version", 2)),
            ("open_item_shape",
             lambda d: d.__setitem__(
                 "open_items", [d["open_items"][0], "g6"])),
            ("forbidden_key",
             lambda d: d.__setitem__("closure", True)),
            ("budget_approval_claim",
             lambda d: d.__setitem__("budget_approved", True)),
            ("r1_status_mismatch",
             lambda d: d.__setitem__("r1_status", "passed")),
            ("g6_acceptance_claim",
             lambda d: d.__setitem__("g6_acceptance", True)),
            ("physical_accuracy_claim",
             lambda d: d.__setitem__("physical_accuracy", True)),
            ("issue_closure_claim",
             lambda d: d.__setitem__("issues_closed", True)),
            ("g6_not_open",
             lambda d: d["open_items"][1].__setitem__("state", "closed")),
            ("full_not_open",
             lambda d: d["open_items"][2].__setitem__("state", "passed")),
            ("entry_class_enum_mismatch",
             lambda d: d["entry_classes"].__setitem__(
                 "supported", ["mrdivide_residual_input"])),
            ("residual_indices_mismatch",
             lambda d: d["entry_classes"].__setitem__(
                 "mrdivide_residual_input_indices", [10, 11])),
            ("physical_semantics_claim",
             lambda d: d["entry_classes"].__setitem__(
                 "physical_semantics_inferred", True)),
            ("divergence_ulp_mismatch",
             lambda d: d["divergence_pair"].__setitem__("ulp", 0)),
            ("divergence_pair_equal",
             lambda d: d["divergence_pair"].__setitem__(
                 "target_trace_hex",
                 d["divergence_pair"]["comparison_v2_reference_hex"])),
            ("unresolved_incomplete",
             lambda d: d.__setitem__(
                 "unresolved",
                 [item for item in d["unresolved"]
                  if item["id"] != "archive_source_line_mapping"])),
            ("unresolved_status",
             lambda d: d["unresolved"][0].__setitem__("status", "resolved")),
            ("unresolved_archive_identity",
             lambda d: [item.__setitem__("requires_sha256", "0" * 64)
                        for item in d["unresolved"]
                        if item["requires"] == "model_archive"]),
            ("archive_not_required",
             lambda d: d["evidence_policy"].__setitem__(
                 "frozen_archive_required", False)),
            ("nonclaims_insufficient",
             lambda d: d.__setitem__("nonclaims", ["nothing claimed"])),
            ("nonclaim_missing",
             lambda d: d.__setitem__(
                 "nonclaims", ["no g6 claim", "no numerical claim",
                               "no physical claim", "no closure claim",
                               "no budget claim"])),
            ("schema_or_kind_mismatch",
             lambda d: d.__setitem__("schema", "wksim.other.v1")),
            ("authority_claim",
             lambda d: d.__setitem__("authority", "owner")),
            ("effective_claim",
             lambda d: d.__setitem__("effective", True)),
            ("pending_approvals_present",
             lambda d: d.__setitem__("pending_approvals", ["budget"])),
            ("open_items_missing",
             lambda d: d.__setitem__("open_items", [])),
            ("open_item_not_open",
             lambda d: d["open_items"][0].__setitem__("state", "closed")),
            ("index_map_not_list",
             lambda d: d.__setitem__("index_map", {"0": {}})),
            ("index_entry_shape",
             lambda d: d["index_map"].__setitem__(3, "index-3")),
            ("index_not_integer",
             lambda d: d["index_map"][3].__setitem__("index", "3")),
            ("counts_missing",
             lambda d: d.__setitem__("counts", "absent")),
            ("covered_block_size",
             lambda d: (d["index_map"][0].__setitem__("covered", True),
                        d["counts"].__setitem__("covered_states", 14))),
            ("uncovered_block_size",
             lambda d: (d["index_map"][36 - 1].__setitem__("covered", True),
                        d["counts"].__setitem__("uncovered_states", 22))),
            ("entry_classes_missing",
             lambda d: d.__setitem__("entry_classes", [])),
            ("output_indices_mismatch",
             lambda d: d["entry_classes"].__setitem__(
                 "mrdivide_output_indices", [10, 12])),
            ("residual_provenance_missing",
             lambda d: d["index_map"][10].pop("untracked_provenance")),
            ("conflicted_symbol_with_tracked_comparison",
             lambda d: d["index_map"][7].__setitem__(
                 "symbol_resolution", "conflicted_requires_archive_input")),
            ("divergence_pair_mismatch",
             lambda d: d.__setitem__("divergence_pair", {"index": 10})),
            ("unresolved_missing",
             lambda d: d.__setitem__("unresolved", [])),
            ("unresolved_shape",
             lambda d: d["unresolved"].__setitem__(0, "archive")),
            ("pin_missing",
             lambda d: d["pins"].pop("agents")),
            ("pin_path_mismatch",
             lambda d: d["pins"]["agents"].__setitem__("path", "AGENTS.txt")),
            ("pins_missing",
             lambda d: d.__setitem__("derived_pins", "absent")),
            ("anchor_mismatch",
             lambda d: d.__setitem__("anchor", "0" * 40)),
            ("base_ancestor_mismatch",
             lambda d: d.__setitem__("base_ancestor", "0" * 40)),
            ("anchor_policy_missing",
             lambda d: d.__setitem__("anchor_policy", "absent")),
            ("anchor_policy_head_embedded",
             lambda d: d["anchor_policy"].__setitem__(
                 "observed_head_embedded", True)),
            ("output_encoding_missing",
             lambda d: d["index_map"][11].pop("output_encoding")),
            ("output_encoding_kind",
             lambda d: d["index_map"][11]["output_encoding"].__setitem__(
                 "kind", "mrdivide_residual_input")),
            ("output_encoding_slice",
             lambda d: d["index_map"][11]["output_encoding"].__setitem__(
                 "result_equals_derivative_slice", [10, 12])),
            ("output_encoding_hex_value",
             lambda d: d["index_map"][11]["output_encoding"].__setitem__(
                 "hex_stage2", ["deadbeefdeadbeef"] * 3)),
            ("output_encoding_hex_mismatch",
             lambda d: d["index_map"][11]["output_encoding"].__setitem__(
                 "hex_stage2", ["deadbeefdeadbeef"] * 3)),
            ("mrdivide_output_evidence_missing",
             lambda d: d["index_map"][11].pop("mrdivide_output_evidence")),
            ("mrdivide_output_evidence_content",
             lambda d: d["index_map"][11][
                 "mrdivide_output_evidence"].__setitem__("ulp", 2)),
            ("line_bindings_not_list",
             lambda d: d.__setitem__("line_bindings", {"0": {}})),
            ("line_bindings_keys_mismatch",
             lambda d: d["line_bindings"].pop(0)),
            ("line_bindings_mismatch",
             lambda d: d["line_bindings"][0].__setitem__(
                 "text", ["corrupted"])),
            ("doc_refs_mismatch",
             lambda d: d["doc_refs"][0].__setitem__("sha256", "0" * 64)),
            ("conflict_range_not_conflicted",
             lambda d: d["index_map"][20].__setitem__(
                 "symbol_resolution", "resolved")),
            ("conflict_outside_range",
             lambda d: d["index_map"][2].__setitem__(
                 "symbol_resolution", "conflicted_requires_archive_input")),
            ("conflicted_symbol_without_conflict_evidence",
             lambda d: d["index_map"][25].__setitem__(
                 "symbol_evidence", "tracked_builder_state_layout")),
            ("conflict_scope_mismatch",
             lambda d: d["symbol_conflicts"][0].__setitem__(
                 "scope", "indices 25..35")),
        ]
        for code, mutate in cases:
            with self.subTest(code=code):
                self.assertRejects(mutate, code)

    def test_tampered_pins_and_line_bindings_reject(self):
        for container_key, table in ALL_PIN_TABLES:
            for key in sorted(table):
                with self.subTest(pin=key):
                    self.assertRejects(
                        lambda d, c=container_key, k=key:
                        d[c][k].__setitem__("sha256", "0" * 64),
                        "pin_hash_mismatch")
        self.assertRejects(
            lambda d: d["derived_pins"]["map_generator"].__setitem__("size", 1),
            "pin_size_mismatch")
        self.assertRejects(
            lambda d: d["derived_pins"]["map_generator"].__setitem__(
                "tracked_at_anchor",
                not d["derived_pins"]["map_generator"]["tracked_at_anchor"]),
            "pin_tracked_flag_mismatch")
        self.assertRejects(
            lambda d: d["index_map"][11]["tracked_line_bindings"][
                0].__setitem__("sha256", "0" * 64),
            "line_binding_hash_mismatch")
        self.assertRejects(
            lambda d: d["index_map"][11]["tracked_line_bindings"][
                0].__setitem__("tracked_at_anchor", False),
            "line_binding_not_tracked")

    def test_unreadable_pin_and_non_object_payload_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp) / "repo"
            sandbox.mkdir()
            result = validate(self.base, repo_root=sandbox)
            self.assertFalse(result["ok"])
            self.assertIn("pin_unreadable", result["codes"])
            # The anchor relationship is unverifiable outside the repository,
            # so validation fails closed rather than assuming provenance.
            self.assertIn("anchor_not_ancestor", result["codes"])
            self.assertIn("evidence_drift_unverifiable", result["codes"])
        result = validate(["not", "a", "map"], repo_root=ROOT)
        self.assertFalse(result["ok"])
        self.assertIn("payload_not_object", result["codes"])


class TestOfflineHygiene(unittest.TestCase):
    """The slice stays offline and never mutates git or the real index."""

    def test_generator_source_never_launches_a_model_or_a_native_tool(self):
        source = (ROOT / GENERATOR_RELATIVE).read_text(encoding="utf-8")
        lowered = source.lower()
        for forbidden in ("subprocess.popen", "os.system", "os.popen",
                          "matlab", "simulink", "ros2", "dds", "unreal",
                          "px4", "arducopter"):
            self.assertNotIn(forbidden, lowered)
        # The only child process is the single read-only git helper
        # (`_git_text`), used for the anchor `ls-tree` membership read and the
        # read-only anchor-ancestry / evidence-drift checks.
        self.assertEqual(lowered.count("subprocess.run("), 1)

    def test_git_access_is_index_and_history_independent(self):
        source = Path(__file__).read_text(encoding="utf-8")
        lowered = source.lower()
        for forbidden in ("\"git\", \"add\"", "\"git\", \"commit\"",
                          "\"git\", \"push\"", "git\", \"status",
                          "git\", \"reset", "git\", \"stash",
                          "\"checkout\""):
            self.assertNotIn(forbidden, lowered)
        for mode in ("rev-parse", "cat-file", "merge-base", "ls-tree",
                     "ls-files", "diff"):
            self.assertIn(mode, lowered)
        cleaned = _clean_env()
        self.assertNotIn("GIT_INDEX_FILE", cleaned)
        original = os.environ.get("GIT_INDEX_FILE")
        try:
            os.environ.pop("GIT_INDEX_FILE", None)
            self.assertFalse(_staged_mode())
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
                self.assertTrue(_staged_mode())
            os.environ["GIT_INDEX_FILE"] = str(ROOT / ".git" / "index")
            self.assertFalse(_staged_mode())
        finally:
            if original is None:
                os.environ.pop("GIT_INDEX_FILE", None)
            else:
                os.environ["GIT_INDEX_FILE"] = original

    def test_real_index_is_never_written_and_candidates_exist(self):
        before = _git("rev-parse", "HEAD").stdout
        before_branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout
        for rel in STAGING_PATHS:
            self.assertTrue((ROOT / rel).exists(), rel)
        after = _git("rev-parse", "HEAD").stdout
        after_branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout
        self.assertEqual(before, after)
        self.assertEqual(before_branch, after_branch)

    def test_plan_document_records_the_same_frontier(self):
        text = (ROOT / PLAN_RELATIVE).read_text(encoding="utf-8")
        for phrase in (SCHEMA, R1_STATUS, "36", "13", "23", "#84", "G6", "Full"):
            self.assertIn(phrase, text)
        for rel in (GENERATOR_RELATIVE, PLAN_RELATIVE):
            candidate = (ROOT / rel).read_text(encoding="utf-8")
            for phrase in ("#84", "G6", "Full", "numerical_failed"):
                self.assertIn(phrase, candidate, f"{rel}:{phrase}")


if __name__ == "__main__":
    unittest.main()
