"""Offline context-binding tests for the CodeBuddy module-review admission batch.

Binds docs/coordination/codebuddy-module-review-20260912.md (historical context
only) and registers the current-tree folding status of its five findings:

- D1/D2 folded into tracked docs/coordination/ds-rate-budget-20260912.json
  (parser_coverage.structural_reason); the promotion-gate citation in that
  JSON is a historical reading (joint_profile.py:219-220 at the 2026-09-12
  review time); the live gate is the marker-loop raise, currently at
  joint_profile.py:274-276, asserted here by content anchor only;
- D3 folded into tracked docs/plan/33-rate-next-diagnostic-20260912.md and
  docs/coordination/claude-native-input-timing.md;
- D5 still an ACTIVE fact correction: tracked
  docs/coordination/ds-26-host-recheck-20260912.json still records 782 test
  lines while validation/test_build_generated_e0.py currently has 886.

Design constraints (mirroring the sibling context suites):
- ancestor assertions only; no HEAD-equality assertion anywhere;
- repo-relative paths derived from __file__ (fresh-clone safe);
- no assertion that any candidate stays untracked (staging safe);
- no writes, no network, no native execution;
- mutation negatives invoke the same production-style helpers as the positive
  assertions and are strictly in-memory (no repository file is modified).
"""

import hashlib
import json
import math
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SOURCE_REL = "docs/coordination/codebuddy-module-review-20260912.md"
NOTE_REL = "docs/coordination/codebuddy-module-review-ingest-note-20260914.md"
RATE_BUDGET_REL = "docs/coordination/ds-rate-budget-20260912.json"
PLAN_REL = "docs/plan/33-rate-next-diagnostic-20260912.md"
NATIVE_TIMING_REL = "docs/coordination/claude-native-input-timing.md"
D26_RECHECK_REL = "docs/coordination/ds-26-host-recheck-20260912.json"
E0_TEST_REL = "validation/test_build_generated_e0.py"
JOINT_PROFILE_REL = "Simulator/wksim_runtime/joint_profile.py"

SOURCE_SHA256 = "7fd97029dfd4c0a8f301badfdc3abadb02a097b184c9908a07aa9f85e6f2e2db"
SOURCE_SIZE = 7544
ARCH_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
E0_TEST_LINES = 886

D1_ANCHOR_STRINGS = (
    "Correction to the first edition",
    "tools/audit_pv_trajectory.py contains zero rate_timing_probe/timing_probe checks",
    "pause_probe_requested",
    "scene_lifecycle_requested",
    "scene_lease_loss_requested",
    "dds_loss_requested",
    "diagnostic_land_step_period_s",
)

D2_ANCHOR_STRINGS = (
    "does not reject probe rows wholesale",
    "fails closed only when the sealed identity block is missing or differs",
    "silently ignored by schedule()",
    "no rate_timing_probe branch and no else",
    "Formal mixed/PV evidence cannot include rate_timing_probe",
)


def rel(relpath):
    return REPO / relpath


def sha256_of_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_of(relpath):
    return sha256_of_bytes(rel(relpath).read_bytes())


def count_lines(text):
    """wc -l semantics with EOF handling for a missing trailing newline."""
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def strict_load(text):
    """Production-style strict JSON loader: rejects duplicate keys, the
    NaN/Infinity/-Infinity constants, and non-finite overflow floats."""

    def object_pairs(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise ValueError("duplicate key: %r" % (key,))
            seen.add(key)
        return dict(pairs)

    def reject_constant(token):
        raise ValueError("non-finite JSON constant: %s" % (token,))

    def walk(node):
        if isinstance(node, float) and not math.isfinite(node):
            raise ValueError("non-finite float in document")
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    document = json.loads(
        text, object_pairs_hook=object_pairs, parse_constant=reject_constant
    )
    walk(document)
    return document


def d1_folding_ok(text):
    return all(marker in text for marker in D1_ANCHOR_STRINGS)


def d2_folding_ok(text):
    return all(marker in text for marker in D2_ANCHOR_STRINGS)


def d3_folding_ok(plan_text, timing_text):
    return (
        "`WKSIM_JOINT_RATE_TIMING_PROBE` 只接受 unset/`0`/`1`，其他值 raise" in plan_text
        and "静默关闭、不 raise（`joint.py:54`：`os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'`）"
        in plan_text
        and "WKSIM_JOINT_CPU_TIMING == '1'" in timing_text
        and "默认关闭" in timing_text
    )


def git_is_ancestor(commit):
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


class TestSourceByteBinding(unittest.TestCase):
    def test_source_hash_and_size_exact(self):
        self.assertEqual(sha256_of(SOURCE_REL), SOURCE_SHA256)
        self.assertEqual(rel(SOURCE_REL).stat().st_size, SOURCE_SIZE)

    def test_source_defect_findings_present(self):
        text = rel(SOURCE_REL).read_text(encoding="utf-8")
        for marker in ("缺陷 D1", "缺陷 D2", "缺陷 D3", "缺陷 D4", "缺陷 D5"):
            self.assertIn(marker, text)


class TestAncestry(unittest.TestCase):
    def test_architecture_ancestor_of_symbolic_head(self):
        self.assertTrue(git_is_ancestor(ARCH_ANCESTOR))

    def test_no_head_equality_assertion_in_suite(self):
        module_source = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("--is-ancestor", module_source)
        pattern = "rev-parse" + r"[^\n]*" + "=" * 2
        self.assertIsNone(
            re.search(pattern, module_source),
            "suite must assert ancestry, never HEAD equality",
        )


class TestD1D2Folding(unittest.TestCase):
    def test_rate_budget_json_strict_parse(self):
        document = strict_load(rel(RATE_BUDGET_REL).read_text(encoding="utf-8"))
        self.assertIsInstance(document, dict)

    def test_d1_correction_folded_into_rate_budget_json(self):
        self.assertTrue(
            d1_folding_ok(rel(RATE_BUDGET_REL).read_text(encoding="utf-8"))
        )

    def test_d2_correction_folded_into_structural_reason_only(self):
        document = strict_load(rel(RATE_BUDGET_REL).read_text(encoding="utf-8"))
        structural_reason = document["parser_coverage"]["structural_reason"]
        self.assertTrue(d2_folding_ok(structural_reason))
        # P3-2 fix: the correction carrier is parser_coverage.structural_reason;
        # diagnostic_constraint is not a top-level key of this JSON.
        self.assertNotIn("diagnostic_constraint", document)

    def test_d2_historical_citation_retained_as_historical(self):
        text = rel(RATE_BUDGET_REL).read_text(encoding="utf-8")
        self.assertIn("joint_profile.py:219-220", text)

    def test_live_promotion_gate_content_anchor(self):
        # P3-1/P3-3 fix: current gate asserted by content anchor only; the
        # marker-loop raise now sits at joint_profile.py:274-276 (219-220 was
        # the 2026-09-12 historical location, retained by the tracked JSON).
        text = rel(JOINT_PROFILE_REL).read_text(encoding="utf-8")
        self.assertIn("for marker in ('rate_timing_probe', 'group_work_timing', 'perf_switch_capture'):", text)
        self.assertIn("raise ValueError('Formal mixed/PV evidence cannot include '+marker)", text)

    def test_plan_carries_matching_d1_d2_wording(self):
        text = rel(PLAN_REL).read_text(encoding="utf-8")
        self.assertTrue(
            "直接 raise" in text
            and "被静默忽略" in text
            and "无 `rate_timing_probe` 分支、无 else" in text
            and "0 处** `rate_timing_probe`/`timing_probe`" in text
        )


class TestD3Folding(unittest.TestCase):
    def test_d3_correction_folded_into_tracked_anchors(self):
        self.assertTrue(
            d3_folding_ok(
                rel(PLAN_REL).read_text(encoding="utf-8"),
                rel(NATIVE_TIMING_REL).read_text(encoding="utf-8"),
            )
        )

    def test_live_gate_predicates_still_present(self):
        probe_text = rel("Simulator/wksim_runtime/joint_rate_probe.py").read_text(encoding="utf-8")
        self.assertIn('"WKSIM_JOINT_RATE_TIMING_PROBE"', probe_text)
        self.assertIn("must be unset, 0 or 1", probe_text)
        joint_text = rel("Simulator/wksim_core/joint.py").read_text(encoding="utf-8")
        self.assertIn("os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'", joint_text)


class TestD5LiveFact(unittest.TestCase):
    def test_d5_live_line_count_is_886(self):
        self.assertEqual(count_lines(rel(E0_TEST_REL).read_text(encoding="utf-8")), E0_TEST_LINES)

    def test_d5_tracked_source_still_records_782(self):
        document = strict_load(rel(D26_RECHECK_REL).read_text(encoding="utf-8"))
        self.assertIn("782 行测试", json.dumps(document, ensure_ascii=False))

    def test_d5_note_registers_fact_without_claiming_fix(self):
        note = rel(NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("782", note)
        self.assertIn("886 行", note)
        self.assertIn("仍是活性事实纠错", note)
        self.assertIn("不修改 tracked D5 源", note)
        self.assertIn("不声称：D5 已修复", note)


class TestHistoricalBoundaries(unittest.TestCase):
    def test_source_declares_readonly_historical_scope(self):
        text = rel(SOURCE_REL).read_text(encoding="utf-8")
        self.assertIn("只读复核", text)
        self.assertIn("未运行 native/模型/构建", text)
        self.assertIn("未提交 Git", text)

    def test_note_non_acceptance_wording(self):
        note = rel(NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("不构成任何验收、批准、收口或复核记录", note)
        self.assertIn("historical context only", note)
        self.assertIn("未重跑 #83", note)
        self.assertIn(ARCH_ANCESTOR, note)

    def test_note_declares_folding_not_invalidation(self):
        note = rel(NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("折叠只表示正确语义已进入 tracked 锚", note)
        self.assertIn("源文件按字节保留原样", note)

    def test_note_registers_p3_dispositions_without_approval(self):
        note = rel(NOTE_REL).read_text(encoding="utf-8")
        self.assertIn("P1=0/P2=0/P3=5", note)
        for marker in ("P3-1", "P3-2", "P3-3", "P3-4", "P3-5"):
            self.assertIn(marker, note)
        self.assertIn("已修", note)
        self.assertIn("不声称 P3", note)


class TestMutationNegatives(unittest.TestCase):
    """Mutations are strictly in-memory; each negative re-runs the same
    production-style helper its positive counterpart asserts with, so a real
    drift would be detected by the identical code path."""

    def test_source_hash_drift_detected(self):
        drifted = rel(SOURCE_REL).read_bytes() + b"\n"
        self.assertNotEqual(sha256_of_bytes(drifted), SOURCE_SHA256)

    def test_line_count_drift_detected_by_production_counter(self):
        drifted = rel(E0_TEST_REL).read_text(encoding="utf-8") + "\n"
        self.assertEqual(count_lines(drifted), E0_TEST_LINES + 1)

    def test_d1_text_drift_detected_by_production_assertion(self):
        text = rel(RATE_BUDGET_REL).read_text(encoding="utf-8")
        self.assertTrue(d1_folding_ok(text))
        self.assertFalse(
            d1_folding_ok(text.replace("Correction to the first edition", "", 1))
        )

    def test_d2_text_drift_detected_by_production_assertion(self):
        text = rel(RATE_BUDGET_REL).read_text(encoding="utf-8")
        self.assertTrue(d2_folding_ok(text))
        for needle in (
            "Simulator/wksim_runtime/joint_profile.py:219-220",
            "joint_profile.py:219-220",
        ):
            text = text.replace(needle, "")
        drifted = text.replace(
            "Formal mixed/PV evidence cannot include rate_timing_probe", "", 1
        )
        self.assertFalse(d2_folding_ok(drifted))

    def test_strict_loader_rejects_duplicate_keys_deterministically(self):
        with self.assertRaises(ValueError):
            strict_load('{"schema": "a", "schema": "b"}')

    def test_strict_loader_rejects_nonfinite_and_overflow(self):
        for literal in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.assertRaises(ValueError):
                strict_load('{"probe_value": %s}' % (literal,))


if __name__ == "__main__":
    unittest.main()
