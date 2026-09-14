"""Read-only integrity tests for the two #83 diagnostic evidence originals.

Targets (never modified by these tests):

- docs/coordination/ds-7bdfxkb-diagnostic-analysis.json
- docs/coordination/omp-83-freeze-check-20260912.md

The tests pin the exact SHA256 of both files, load the JSON strictly
(rejecting duplicate object keys and NaN/Infinity constants), reconcile the
recorded arithmetic only (no analyzer or runtime execution), cross-check the
three manifest SHAs against the OMP freeze-check Markdown table, and verify
that ``candidate_pointer.document`` resolves to an existing tracked file.

Everything is offline and deterministic; any schema or type change fails
closed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]

JSON_REL = "docs/coordination/ds-7bdfxkb-diagnostic-analysis.json"
MD_REL = "docs/coordination/omp-83-freeze-check-20260912.md"

JSON_SHA256 = "692a067123126797862edd89c2961634530ae04374e8ba1b4f69fe2b8e12981e"
MD_SHA256 = "273a99613f707dba2fb9d0c92f18de0887ccdab900e031025963d4464d13f638"

SCHEMA = "wksim.ds-rate-diagnostic-analysis.v1"

# Recorded latch reconciliation constants pinned by the evidence task.
LATCH_TOTAL_NS = 100050657
MAX_GROUP_START_LATENESS_NS = 99880816
RATE_UNMET_TICK = 109776

# Role -> Markdown table first column, for the three cross-checked manifests.
MANIFEST_ROLES = {
    "ap": "AP mixed",
    "control": "Control",
    "message": "Message",
}


def _reject_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        seen.add(key)
    return dict(pairs)


def _reject_constant(name):
    raise ValueError(f"non-finite JSON constant not allowed: {name}")


def strict_loads(text: str):
    """json.loads that rejects duplicate keys and NaN/Infinity/-Infinity."""
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def strict_load(path: Path):
    return strict_loads(path.read_text(encoding="utf-8"))


def _require(value, expected_type, label):
    # exact type check: bool is a subclass of int, so exclude it explicitly
    if type(value) is not expected_type:
        raise AssertionError(
            f"{label}: expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_tracked(rel: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


DOCUMENT = strict_load(ROOT / JSON_REL)
MARKDOWN = (ROOT / MD_REL).read_text(encoding="utf-8")


class TestEvidenceOriginalHashes(unittest.TestCase):
    def test_json_original_sha256(self):
        self.assertEqual(_sha256(ROOT / JSON_REL), JSON_SHA256)

    def test_markdown_original_sha256(self):
        self.assertEqual(_sha256(ROOT / MD_REL), MD_SHA256)


class TestStrictJsonSchema(unittest.TestCase):
    def test_schema_and_scalars_fail_closed(self):
        self.assertEqual(_require(DOCUMENT["schema"], str, "schema"), SCHEMA)
        for label in ("run_id", "analyzed_local_time", "owner", "scope"):
            _require(DOCUMENT[label], str, label)

    def test_structure_types_fail_closed(self):
        structure = DOCUMENT["structure"]
        self.assertIsInstance(structure, dict)
        for label in (
            "segments",
            "anchors",
            "rate_group_start",
            "rate_group_end",
            "rate_timing_probe",
            "max_group_start_lateness_ns",
        ):
            _require(structure[label], int, f"structure.{label}")
        outcomes = structure["probe_outcomes"]
        _require(outcomes["started"], int, "probe_outcomes.started")
        _require(outcomes["rate_unmet"], int, "probe_outcomes.rate_unmet")

    def test_latch_reconciliation_types_fail_closed(self):
        latch = DOCUMENT["latch_reconciliation"]
        self.assertIsInstance(latch, dict)
        for label in (
            "groups",
            "intervals",
            "recorded_latch_lateness_ns",
            "rate_unmet_tick",
            "last_group_start_lateness_ns",
            "last_group_boundary_tick",
        ):
            _require(latch[label], int, f"latch_reconciliation.{label}")

    def test_probe_phases_types_fail_closed(self):
        split = DOCUMENT["probe_phases"]["release_excess_split"]
        self.assertIsInstance(split, dict)
        for label in (
            "total_ns",
            "entry_lateness_total_ns",
            "post_entry_excess_total_ns",
        ):
            _require(split[label], int, f"release_excess_split.{label}")
        _require(
            DOCUMENT["probe_phases"]["sample_count"],
            int,
            "probe_phases.sample_count",
        )


class TestRecordedArithmeticReconciliation(unittest.TestCase):
    def setUp(self):
        self.latch = DOCUMENT["latch_reconciliation"]
        self.structure = DOCUMENT["structure"]
        self.split = DOCUMENT["probe_phases"]["release_excess_split"]

    def test_intervals_equal_groups_minus_one(self):
        self.assertEqual(self.latch["intervals"], self.latch["groups"] - 1)

    def test_latch_total_matches_release_excess_split(self):
        self.assertEqual(self.latch["recorded_latch_lateness_ns"], LATCH_TOTAL_NS)
        self.assertEqual(self.split["total_ns"], LATCH_TOTAL_NS)

    def test_entry_plus_post_entry_equals_latch_total(self):
        self.assertEqual(
            self.split["entry_lateness_total_ns"]
            + self.split["post_entry_excess_total_ns"],
            LATCH_TOTAL_NS,
        )

    def test_dominant_entry_lateness_rows_within_entry_total(self):
        rows = DOCUMENT["dominant_events"]["rows"]
        self.assertIsInstance(rows, list)
        self.assertTrue(rows)
        total = 0
        for index, row in enumerate(rows):
            self.assertIsInstance(row, dict)
            total += _require(
                row["entry_lateness_ns"], int, f"dominant_events.rows[{index}]"
            )
        self.assertLessEqual(total, self.split["entry_lateness_total_ns"])

    def test_started_plus_rate_unmet_equals_sample_count(self):
        outcomes = self.structure["probe_outcomes"]
        self.assertEqual(
            outcomes["started"] + outcomes["rate_unmet"],
            DOCUMENT["probe_phases"]["sample_count"],
        )

    def test_max_and_last_group_start_lateness_pinned(self):
        self.assertEqual(
            self.structure["max_group_start_lateness_ns"],
            MAX_GROUP_START_LATENESS_NS,
        )
        self.assertEqual(
            self.latch["last_group_start_lateness_ns"],
            MAX_GROUP_START_LATENESS_NS,
        )

    def test_last_boundary_tick_matches_rate_unmet_tick(self):
        self.assertEqual(self.latch["last_group_boundary_tick"], RATE_UNMET_TICK)
        self.assertEqual(self.latch["rate_unmet_tick"], RATE_UNMET_TICK)


class TestCrossFileManifestEvidence(unittest.TestCase):
    def test_three_manifest_shas_match_omp_table(self):
        manifests = DOCUMENT["identity_check"]["manifests"]
        self.assertIsInstance(manifests, dict)
        for key, role in MANIFEST_ROLES.items():
            recorded = _require(
                manifests[key], str, f"identity_check.manifests.{key}"
            )
            self.assertRegex(recorded, r"^[0-9a-f]{64}$")
            pattern = re.compile(
                r"^\|\s*" + re.escape(role) + r"\s*\|[^|]*\|\s*`([0-9a-f]{64})`\s*\|",
                re.MULTILINE,
            )
            matches = pattern.findall(MARKDOWN)
            self.assertEqual(
                len(matches), 1, f"OMP table row for {role!r} not unique"
            )
            self.assertEqual(recorded, matches[0])

    def test_candidate_pointer_document_is_tracked_and_present(self):
        pointer = DOCUMENT["candidate_pointer"]
        rel = _require(pointer["document"], str, "candidate_pointer.document")
        self.assertNotIn("..", Path(rel).parts)
        target = ROOT / rel
        self.assertTrue(target.is_file(), f"missing candidate document: {rel}")
        self.assertTrue(_git_tracked(rel), f"not tracked in git index: {rel}")


class TestStrictJsonRejectionRegression(unittest.TestCase):
    def test_rejects_duplicate_object_keys(self):
        with self.assertRaises(ValueError):
            strict_loads('{"a": 1, "a": 2}')

    def test_rejects_nan_constant(self):
        with self.assertRaises(ValueError):
            strict_loads('{"a": NaN}')

    def test_rejects_infinity_constant(self):
        with self.assertRaises(ValueError):
            strict_loads('{"a": Infinity}')

    def test_rejects_negative_infinity_constant(self):
        with self.assertRaises(ValueError):
            strict_loads('{"a": -Infinity}')

    def test_plain_json_would_accept_what_strict_rejects(self):
        # sanity guard: the rejection comes from the strict hooks, not syntax
        self.assertEqual(json.loads('{"a": 1, "a": 2}'), {"a": 2})
        self.assertTrue(json.loads('{"a": NaN}')["a"] != json.loads('{"a": NaN}')["a"])


if __name__ == "__main__":
    unittest.main()
