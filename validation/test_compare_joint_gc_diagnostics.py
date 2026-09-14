"""Contract tests for tools/compare_joint_gc_diagnostics.py.

The manager GC candidate contract is exercised against the REAL implementation
(``/root/wksim-release-acceptance-fe3/tools/manager_gc_candidate.py``, pinned
SHA256 below) with an injected FakeGC module: ``arm()``/``prepare()``/
``restore()`` run for real and the resulting ``ManagerGCFreeze.report()`` is fed
to the comparator as the retained product. That report is a FIXTURE built by
this test; it is not a new field, not retained evidence and not a performance
claim (``performance_pass`` is False and ``classification`` is
``candidate_not_performance_pass``).

Everything else stays synthetic and small. The suite pins the comparator's
contract: gzip inputs, missing evidence reported as unavailable (never zero),
mixed identity inside one field rejected, cross-field incompatibility rejected,
an absent latch reported as unavailable, a negative residual rejected by the
reused interval analyzer, the real candidate report validated (restore to zero,
unchanged thresholds, tick-0 preparation, source identity), mutation or
result/side-file disagreement rejected, bool/reversed/non-finite clocks and
costs rejected, non-object result/source/metadata rejected without
AttributeError, named-vs-anonymous and empty source maps refused as controlled
pairing, and the no-causal/no-performance-pass claim limits.

Run: python -m unittest validation.test_compare_joint_gc_diagnostics
"""

import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.compare_joint_gc_diagnostics import compare, main, known_field_token


# Pinned identity of A's stable implementation. If this changes, re-read the
# contract, update the pin and re-verify the comparator against the new report.
MANAGER_GC_SHA256 = "cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66"
MANAGER_GC_CANDIDATES = (
    os.environ.get("WKSIM_MANAGER_GC_CANDIDATE"),
    r"\\wsl.localhost\Ubuntu-22.04\root\wksim-release-acceptance-fe3\tools\manager_gc_candidate.py",
    "/root/wksim-release-acceptance-fe3/tools/manager_gc_candidate.py",
)

EPOCH_A = "aa" * 16
EPOCH_B = "bb" * 16
PERIOD_NS = 8_000_000
FIRST_TICK = 40
IDEAL_START_NS = 1_000_000_000
FIRST_LATENESS_NS = 50_000
LAST_LATENESS_NS = 200_000
TERMINAL_INCREMENT_NS = 150_000
LATCH_LATENESS_NS = 350_000
LATCH_ISSUED_NS = IDEAL_START_NS + 100_000_000  # closes the timed window 100 ms in
BOOT_A = "470ea486-9e18-4535-9d91-69de5a3a4572"
BOOT_B = "d01554f1-f19e-4193-8668-69754d6a9170"
MANIFESTS = {"ap": "ap-sha", "control": "control-sha", "message": "message-sha"}
PX4_MANIFEST = {"path": "/root/wksim-px4-state-ONa1Kw/wksim-build.json",
                "sha256": "px4-sha"}
SOURCE_SHA = {
    "tools/run_joint_flight.py": "11" * 32,
    "Simulator/wksim_runtime/joint_rate.py": "22" * 32,
    "Simulator/wksim_core/joint.py": "33" * 32,
}
REAL_GC_CHILD = r"""
import importlib.util, json, sys
path, expected = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("manager_gc_child", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
candidate = module.ManagerGCFreeze(enabled=True, source_sha256=expected)
candidate.arm()
candidate.prepare(monotonic_ns=5_000_000, clock_tick=0)
candidate.restore()
print(json.dumps(candidate.report()))
"""


def manager_gc_path():
    module, _ = load_manager_gc()
    if module is None:
        return None
    for candidate in MANAGER_GC_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def load_manager_gc():
    """Import the real candidate module from the Linux workspace, read-only."""
    for candidate in MANAGER_GC_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != MANAGER_GC_SHA256:
            raise AssertionError(
                "manager_gc_candidate.py changed: expected %s, found %s; re-read the "
                "contract, update the pin and re-verify the comparator"
                % (MANAGER_GC_SHA256, digest))
        spec = importlib.util.spec_from_file_location("manager_gc_candidate_fixture", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, digest
    return None, None


class FakeGC:
    """Minimal collector stand-in for ManagerGCFreeze's documented calls."""

    def __init__(self):
        self.enabled = True
        self.freeze_count = 0
        self.thresholds = (700, 10, 10)
        self.counts = (11, 2, 1)
        self.calls = []

    def isenabled(self):
        return self.enabled

    def get_freeze_count(self):
        return self.freeze_count

    def get_threshold(self):
        return self.thresholds

    def get_count(self):
        return self.counts

    def collect(self):
        self.calls.append("collect")
        return 3

    def freeze(self):
        self.calls.append("freeze")
        self.freeze_count += 1

    def unfreeze(self):
        self.calls.append("unfreeze")
        self.freeze_count = 0


def real_candidate_report():
    """Run the real lifecycle on FakeGC and return its real report (fixture)."""
    module, _ = load_manager_gc()
    if module is None:
        raise unittest.SkipTest("real manager_gc_candidate.py not reachable")
    fake = FakeGC()
    candidate = module.ManagerGCFreeze(
        enabled=True, gc_module=fake, monotonic_ns=lambda: 1_000_000,
        source_sha256=MANAGER_GC_SHA256)
    candidate.arm()
    candidate.prepare(monotonic_ns=5_000_000, clock_tick=0)
    candidate.restore()
    return candidate.report(), fake


def _group(tick, ideal_start_ns, earliest_start_ns, actual_start_ns, work_ns, epoch):
    common = {
        "epoch": epoch, "segment_id": 1, "request_id": "config", "requested_rate": 0.5,
        "transition": False, "start_tick": tick, "end_tick": tick + 4,
        "ideal_start_ns": ideal_start_ns, "ideal_end_ns": ideal_start_ns + PERIOD_NS,
        "earliest_start_ns": earliest_start_ns, "actual_start_ns": actual_start_ns,
    }
    return [
        {"kind": "rate_group_start", "tick": tick,
         "lateness_ns": max(0, actual_start_ns - ideal_start_ns), **common},
        {"kind": "rate_group_end", "tick": tick + 4,
         "actual_end_ns": actual_start_ns + work_ns,
         "lateness_ns": max(0, actual_start_ns + work_ns - ideal_start_ns - PERIOD_NS),
         **common},
    ]


def rate_rows(epoch=EPOCH_A, latch_lateness=LATCH_LATENESS_NS, second_epoch=None,
              with_anchor=True):
    """Two closed groups; creep 150000 ns, first-group offset 50000 ns."""
    rows = []
    if with_anchor:
        rows.append({
            "kind": "rate_anchor", "epoch": epoch, "tick": FIRST_TICK,
            "issued_monotonic_ns": IDEAL_START_NS, "reason": "synchronized_boundary",
            "requested_rate": 0.5, "request_id": "config", "segment_id": 1, "latched": False,
            "anchor": {"tick": FIRST_TICK, "wall_ns": IDEAL_START_NS, "transition": False},
            "measured_rate": None, "measurement": "timed_segment", "completed_groups": 0,
            "worst_lateness_ns": 0, "steady_after_ns": IDEAL_START_NS + 2_000_000_000,
        })
    first_start = IDEAL_START_NS + FIRST_LATENESS_NS
    rows += _group(FIRST_TICK, IDEAL_START_NS, IDEAL_START_NS, first_start, 4_000_000, epoch)
    second_ideal = IDEAL_START_NS + PERIOD_NS
    second_earliest = max(second_ideal, first_start + PERIOD_NS)
    second_start = second_ideal + LAST_LATENESS_NS
    rows += _group(FIRST_TICK + 4, second_ideal, second_earliest, second_start, 3_000_000,
                   second_epoch or epoch)
    if latch_lateness is not None:
        rows.append({
            "kind": "rate_unmet", "epoch": epoch, "tick": FIRST_TICK + 8,
            "issued_monotonic_ns": LATCH_ISSUED_NS, "reason": "resource_insufficient",
            "lateness_ns": latch_lateness, "requested_rate": 0.5, "request_id": "config",
            "segment_id": 1, "latched": True, "anchor": {"tick": FIRST_TICK, "transition": False},
            "measured_rate": 0.499, "worst_lateness_ns": latch_lateness,
        })
    rows.append({
        "kind": "rate_timing_probe", "epoch": epoch, "outcome": "started",
        "start_tick": FIRST_TICK + 4, "end_tick": FIRST_TICK + 8,
        "entry_ns": second_earliest + 100_000, "initial_health_end_ns": second_earliest + 110_000,
        "terminal_ns": second_start, "ideal_start_ns": second_ideal,
        "earliest_start_ns": second_earliest,
        "entry_to_initial_health_ns": 10_000, "loop_health_ns": 5_000,
        "loop_health_calls": 1, "sleep_requested_ns": 18_000, "sleep_elapsed_ns": 20_000,
        "sleep_calls": 1, "sleep_max_overshoot_ns": 2_000, "final_spin_other_ns": 15_000,
        "release_excess_ns": max(0, second_start - second_earliest),
        "observed_elapsed_ns": second_start - (second_earliest + 100_000),
        "phase_total_ns": second_start - (second_earliest + 100_000),
    })
    return rows


def wire_rows(epoch=EPOCH_A, nested=True, preparation_gc_ns=0, straddling=False,
              missing_clock=False):
    """Diagnostic wire fixture placed inside the timed window by default.

    The timed window is [IDEAL_START_NS, LATCH_ISSUED_NS]; preparation GC rows
    (the C1 shape) sit before it, and a straddling row runs past its end.
    """
    gc_end = 1_034_000_000 if nested else 1_040_000_000
    rows = []
    if preparation_gc_ns:
        rows.append({"kind": "diagnostic_gc_timing", "epoch": epoch, "tick": 0, "wall": 0.5,
                     "generation": 2, "collected": 0, "wall_start_ns": 900_000_000,
                     "wall_end_ns": 900_000_000 + preparation_gc_ns,
                     "thread_cpu_ns": preparation_gc_ns})
    if straddling:
        rows.append({"kind": "diagnostic_gc_timing", "epoch": epoch, "tick": 90000, "wall": 1.0,
                     "generation": 2, "collected": 0, "wall_start_ns": 1_050_000_000,
                     "wall_end_ns": 1_150_000_000, "thread_cpu_ns": 100_000_000})
    gc_row = {"kind": "diagnostic_gc_timing", "epoch": epoch, "tick": 52, "wall": 1.0,
              "generation": 2, "collected": 0, "wall_start_ns": 1_010_000_000, "wall_end_ns": gc_end,
              "thread_cpu_ns": 24_000_000}
    if missing_clock:
        gc_row.pop("wall_start_ns")
        gc_row.pop("wall_end_ns")
    rows += [
        gc_row,
        {"kind": "diagnostic_native_input_timing", "epoch": epoch, "tick": 52, "wall": 1.0,
         "native_wait_wall_ns": 25_001_000,
         "waits": [{"stack": "px4", "wall_start_ns": 1_009_999_000, "wall_end_ns": 1_035_000_000,
                    "wall_ns": 25_001_000, "thread_cpu_ns": 25_000_500}]},
        {"kind": "diagnostic_step_cpu_timing", "epoch": epoch, "tick": 52, "wall": 1.0,
         "wall_start_ns": 1_009_900_000, "wall_end_ns": 1_036_000_000,
         "stages": {
             "health_and_models": {"wall_ns": 10_000, "thread_cpu_ns": 9_000},
             "encode_send": {"wall_ns": 10_000, "thread_cpu_ns": 9_000},
             "native_inputs": {"wall_ns": 25_000_000, "thread_cpu_ns": 24_999_000}}},
    ]
    return rows


def result_document(epoch=EPOCH_A, run_id="run-a", manifests=None, profile="full_xyz_pv_yaw_v1",
                    async_requested=True, manager_report=None, source_sha256=None,
                    boot_id=BOOT_A, source_unchanged=True, group_work_timing=None,
                    owned_scheduling=None, markers=None, overflow=None, lost=None):
    document = {
        "run_id": run_id, "scene_epoch": epoch, "task_profile": profile, "status": "failed",
        "error": "RateUnmet('rate_unmet/resource_insufficient')", "wall_seconds": 12.5,
        "flight_completed": False, "source_unchanged": source_unchanged,
        "host_boot_id": boot_id,
        "async_model_evidence_requested": async_requested,
        "rate_timing_probe": {"diagnostic": "joint_rate_timing_probe",
                              "classification": "diagnostic_only",
                              "production_performance": False},
        "manifest_sha256": dict(manifests or MANIFESTS),
        "mixed_admission": {"identities": {"baseline": {"manifests": {"px4": PX4_MANIFEST}}}},
        "source_sha256": dict(SOURCE_SHA if source_sha256 is None else source_sha256),
        "markers": {} if markers is None else markers,
    }
    if group_work_timing is not None:
        document["group_work_timing"] = group_work_timing
    if owned_scheduling is not None:
        document["owned_scheduling"] = owned_scheduling
    if overflow is not None:
        document["overflow"] = overflow
    if lost is not None:
        document["lost"] = lost
    if manager_report is not None:
        document["manager_gc_candidate"] = manager_report
        document.setdefault("source_sha256", {})["tools/manager_gc_candidate.py"] = \
            manager_report.get("source_sha256")
    return document


def write_field(directory, rate=None, wire=None, result=None, gzip_rate=False, gzip_wire=False,
                manager_report=None, side_report=..., omit=()):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if "result" not in omit:
        document = result if result is not None else result_document(manager_report=manager_report)
        (directory / "result.json").write_text(json.dumps(document), encoding="utf-8")
    if "rate" not in omit:
        rows = rate if rate is not None else rate_rows()
        payload = "".join(json.dumps(row) + "\n" for row in rows)
        if gzip_rate:
            with gzip.open(directory / "rate.jsonl.gz", "wt", encoding="utf-8") as stream:
                stream.write(payload)
        else:
            (directory / "rate.jsonl").write_text(payload, encoding="utf-8")
    if "wire" not in omit:
        rows = wire if wire is not None else wire_rows()
        payload = "".join(json.dumps(row) + "\n" for row in rows)
        if gzip_wire:
            with gzip.open(directory / "joint-wire.jsonl.gz", "wt", encoding="utf-8") as stream:
                stream.write(payload)
        else:
            (directory / "joint-wire.jsonl").write_text(payload, encoding="utf-8")
    if side_report is not ...:
        if side_report is not None:
            (directory / "manager-gc-candidate.json").write_text(
                json.dumps(side_report), encoding="utf-8")
    elif manager_report is not None:
        (directory / "manager-gc-candidate.json").write_text(
            json.dumps(manager_report), encoding="utf-8")
    return directory


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def compare(self, baseline_dir, candidate_dir, **kwargs):
        return compare(baseline_dir, candidate_dir, {}, {}, **kwargs)

    def candidate_field(self, name, **kwargs):
        report = kwargs.pop("report", None)
        if report is None:
            report, _ = real_candidate_report()
        return write_field(self.root / name, manager_report=report, **kwargs), report

    def test_real_module_fixture_matches_pinned_source_and_is_not_a_field(self):
        module, digest = load_manager_gc()
        if module is None:
            self.skipTest("real manager_gc_candidate.py not reachable")
        report, fake = real_candidate_report()
        self.assertEqual(digest, MANAGER_GC_SHA256)
        self.assertEqual(report["module"], "tools/manager_gc_candidate.py")
        self.assertEqual(report["classification"], "candidate_not_performance_pass")
        self.assertFalse(report["performance_pass"])
        self.assertTrue(report["candidate"])
        self.assertEqual(fake.calls, ["collect", "freeze", "unfreeze"])
        self.assertEqual(fake.thresholds, (700, 10, 10))
        self.assertEqual(report["activation"]["clock_tick"], 0)
        # The fixture is built here from FakeGC; it is not retained field evidence.
        self.assertNotIn("manager_gc_candidate", json.dumps({"schema": "fixture_only"}))

    def test_compared_with_gzip_inputs_and_valid_candidate_contract(self):
        baseline = write_field(self.root / "base", gzip_rate=True, gzip_wire=True)
        candidate, _ = self.candidate_field("cand", gzip_rate=True, gzip_wire=True)
        report = self.compare(baseline, candidate)
        self.assertEqual(report["status"], "compared")
        self.assertTrue(report["identity_compatibility"]["compatible"])
        contract = report["candidate"]["manager_gc_candidate_contract"]
        self.assertEqual(contract["status"], "validated")
        self.assertEqual(sorted(contract["sources"]), ["result", "side_file"])
        self.assertTrue(contract["validated_fields"]["restore"]["restored_to_original"])
        self.assertEqual(contract["validated_fields"]["restore"]["freeze_count_after_unfreeze"], 0)
        self.assertEqual(report["candidate"]["gc"]["gen2_thread_cpu_max_ns"], 24_000_000)
        self.assertEqual(report["candidate"]["rate_scan"]["max_entry_lateness_ns"], 100_000)
        self.assertEqual(report["candidate"]["latch_status"], "reconciled")
        self.assertEqual(report["deltas"]["gc_gen2_max_thread_cpu_ns"]["delta_ns"], 0)
        self.assertTrue(report["candidate"]["nesting"]["gc_nested_in_native_wait"])
        self.assertTrue(report["candidate"]["nesting"]["native_wait_inside_step"])
        self.assertTrue(report["candidate"]["nesting"]["containing_wait_on_cpu"])
        self.assertFalse(report["performance_pass"])
        self.assertEqual(report["classification"], "diagnostic_only")
        self.assertTrue(report["claim_class"]["descriptive"])
        self.assertTrue(report["claim_class"]["controlled_pairing"])
        self.assertFalse(report["claim_class"]["causal"])
        self.assertEqual(report["identity_compatibility"]["fields"]["boot_match"], True)

    def test_candidate_report_read_from_result_only_is_validated(self):
        report, _ = real_candidate_report()
        baseline = write_field(self.root / "base")
        result_only = write_field(self.root / "result_only",
                                  result=result_document(manager_report=report),
                                  side_report=None)
        outcome = self.compare(baseline, result_only)
        self.assertEqual(outcome["status"], "compared")
        contract = outcome["candidate"]["manager_gc_candidate_contract"]
        self.assertEqual(contract["status"], "validated")
        self.assertEqual(contract["sources"], ["result"])

    def test_side_file_without_result_source_map_is_unavailable(self):
        # A report string cannot authenticate itself: without the runner's
        # retained source map the source identity is unverifiable.
        report, _ = real_candidate_report()
        baseline = write_field(self.root / "base")
        side_only = write_field(self.root / "side_only", side_report=report)
        outcome = self.compare(baseline, side_only)
        self.assertEqual(outcome["status"], "unavailable")
        contract = outcome["candidate"]["manager_gc_candidate_contract"]
        self.assertEqual(contract["status"], "unavailable")
        self.assertIn("source_sha256_not_in_result_source_map",
                      contract["unavailable_reasons"])

    def test_result_and_side_file_disagreement_is_rejected(self):
        report, _ = real_candidate_report()
        mutated = json.loads(json.dumps(report))
        mutated["freeze_count_after"] = 2
        candidate = write_field(self.root / "cand", result=result_document(manager_report=report),
                                side_report=mutated)
        baseline = write_field(self.root / "base")
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        problems = outcome["candidate"]["manager_gc_candidate_contract"]["problems"]
        self.assertIn("report_mismatch_between_result_and_side_file", problems)

    def test_broken_lifecycle_variants_are_rejected(self):
        baseline = write_field(self.root / "base")
        base_report, _ = real_candidate_report()
        document = result_document(manager_report=base_report)
        variants = {
            "restore_not_zero": {"restore": {**base_report["restore"],
                                             "freeze_count_after_unfreeze": 1}},
            "thresholds_changed": {"prepare_check": {**base_report["prepare_check"],
                                                     "thresholds": [100, 5, 5]}},
            "prepared_after_tick_zero": {"activation": {**base_report["activation"],
                                                        "clock_tick": 4}},
            "not_restored": {"restored": False},
            "frozen_graph_not_released": {"froze_own_graph": True},
            "performance_pass_claimed": {"performance_pass": True},
            "source_mismatch": {"source_sha256": "ff" * 32},
            "skipped_path": {"events": [{"event": "restore_noop_not_owner"}]},
        }
        for label, overrides in variants.items():
            with self.subTest(label):
                report = {**base_report, **overrides}
                # The result's own source map keeps the real module hash, so a
                # mutated report source is a detectable contradiction.
                candidate = write_field(
                    self.root / label,
                    result={**document, "manager_gc_candidate": report},
                    side_report=report)
                outcome = self.compare(baseline, candidate)
                self.assertEqual(outcome["status"], "rejected")
                self.assertEqual(
                    outcome["candidate"]["manager_gc_candidate_contract"]["status"], "rejected")

    def test_candidate_error_keys_are_rejected(self):
        report, _ = real_candidate_report()
        document = result_document(manager_report=report)
        document["manager_gc_candidate_error"] = "ManagerGCFreezeError('refused')"
        baseline = write_field(self.root / "base")
        candidate = write_field(self.root / "cand", result=document, side_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertIn("manager_gc_candidate_error",
                      outcome["candidate"]["manager_gc_candidate_contract"]["problems"])

    def test_disabled_report_is_unavailable(self):
        report, _ = real_candidate_report()
        disabled = {**report, "enabled": False}
        baseline = write_field(self.root / "base")
        candidate = write_field(self.root / "cand",
                                result=result_document(manager_report=disabled),
                                side_report=None)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "unavailable")
        self.assertEqual(outcome["candidate"]["manager_gc_candidate_contract"]["reason"],
                         "manager_gc_candidate_not_enabled")

    def test_missing_wire_is_unavailable_without_zeros(self):
        baseline = write_field(self.root / "base", omit=("wire",))
        candidate, _ = self.candidate_field("cand")
        report = self.compare(baseline, candidate)
        self.assertEqual(report["status"], "unavailable")
        self.assertIn("missing_input:wire", report["reasons"][0])
        self.assertNotIn("deltas", report)

    def test_mixed_identity_inside_one_field_is_rejected(self):
        baseline = write_field(self.root / "base",
                               rate=rate_rows(second_epoch=EPOCH_B, latch_lateness=None))
        candidate, _ = self.candidate_field("cand")
        report = self.compare(baseline, candidate)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["baseline"]["analysis_status"], "rejected")
        self.assertIn("mixed_identity_inside_one_field", report["baseline"]["reasons"])

    def test_cross_field_manifest_mismatch_is_rejected(self):
        baseline = write_field(self.root / "base")
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand",
                                result=result_document(manifests={"ap": "other",
                                                                  "control": "control-sha",
                                                                  "message": "message-sha"},
                                                       manager_report=report),
                                manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["ap_match"])
        self.assertTrue(any("ap:" in item for item in outcome["identity_compatibility"]["differences"]))
        self.assertNotIn("deltas", outcome)

    def test_profile_mismatch_is_rejected(self):
        baseline = write_field(self.root / "base")
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand",
                                result=result_document(profile="mixed", manager_report=report),
                                manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["profile_match"])

    def test_absent_latch_is_rejected_and_not_zero(self):
        rows = rate_rows(latch_lateness=None)
        baseline = write_field(self.root / "base", rate=rows)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", rate=rows, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertTrue(any("incomplete_window" in reason for reason in outcome["reasons"]))
        latch = outcome["candidate"]["latch"]["latch_reconciliation"]
        self.assertEqual(latch["status"], "unavailable")
        self.assertIsNone(latch["recorded_latch_lateness_ns"])
        self.assertIsNone(latch["terminal_unreconciled_ns"])
        self.assertEqual(outcome["candidate"]["latch_status"], "unavailable")
        self.assertNotIn("deltas", outcome)
        self.assertFalse(outcome["claim_class"]["controlled_pairing"])
        self.assertFalse(outcome["claim_class"]["causal"])

    def test_negative_residual_is_rejected_by_interval_analyzer(self):
        baseline = write_field(self.root / "base", rate=rate_rows(latch_lateness=180_000))
        candidate, _ = self.candidate_field("cand")
        report = self.compare(baseline, candidate)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["baseline"]["analysis_status"], "rejected")
        self.assertIn("interval_analyzer_rejected", report["baseline"]["reasons"][0])
        self.assertIn("negative", report["baseline"]["reasons"][0])

    def test_candidate_without_report_is_unavailable(self):
        baseline = write_field(self.root / "base")
        candidate = write_field(self.root / "cand")
        report = self.compare(baseline, candidate)
        self.assertEqual(report["status"], "unavailable")
        contract = report["candidate"]["manager_gc_candidate_contract"]
        self.assertEqual(contract["status"], "unavailable")
        self.assertEqual(contract["reason"], "no_manager_gc_candidate_report")
        self.assertTrue(any(reason.startswith("candidate:manager_gc_candidate_contract:unavailable") for reason in report["reasons"]))

    def test_baseline_with_candidate_report_is_rejected(self):
        report, _ = real_candidate_report()
        baseline = write_field(self.root / "base", manager_report=report)
        candidate = write_field(self.root / "cand", manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertIn("baseline:unexpected_gc_candidate_report", outcome["reasons"])

    def test_different_run_and_epoch_is_legal(self):
        baseline = write_field(self.root / "base")
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", rate=rate_rows(epoch=EPOCH_B),
                                result=result_document(epoch=EPOCH_B, run_id="run-b",
                                                       manager_report=report),
                                manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        fields = outcome["identity_compatibility"]["fields"]
        self.assertFalse(fields["same_run_id"])
        self.assertFalse(fields["same_epoch"])
        self.assertTrue(outcome["identity_compatibility"]["compatible"])
        self.assertIn("descriptive listing",
                      outcome["identity_compatibility"]["run_epoch_note"])
        self.assertTrue(outcome["identity_compatibility"]["fields"]["boot_match"])
        self.assertFalse(outcome["claim_class"]["causal"])

    def test_uneven_timing_environments_are_rejected(self):
        baseline = write_field(self.root / "base", wire=[{"kind": "sensor", "tick": 1}])
        candidate, _ = self.candidate_field("cand")
        report = self.compare(baseline, candidate)
        self.assertEqual(report["status"], "rejected")
        self.assertFalse(report["identity_compatibility"]["fields"]["cpu_timing_match"])

    def test_async_mismatch_is_rejected(self):
        baseline = write_field(self.root / "base", result=result_document(async_requested=False))
        candidate, _ = self.candidate_field("cand")
        report = self.compare(baseline, candidate)
        self.assertEqual(report["status"], "rejected")
        self.assertFalse(report["identity_compatibility"]["fields"]["async_match"])

    def test_self_check_mode_is_labelled_and_never_a_candidate(self):
        field = write_field(self.root / "field")
        report = self.compare(field, field, self_check=True)
        self.assertEqual(report["mode"], "self_check")
        self.assertIn("self-check mode", " ".join(report["claim_limits"]))
        self.assertEqual(report["status"], "unavailable")
        self.assertTrue(any(reason.startswith("candidate:manager_gc_candidate_contract:unavailable") for reason in report["reasons"]))

    def test_cli_writes_report_and_refuses_overwrite(self):
        baseline = write_field(self.root / "base")
        candidate, _ = self.candidate_field("cand")
        output = self.root / "out.json"
        self.assertEqual(main(["--baseline", str(baseline), "--candidate", str(candidate),
                               "--output", str(output)]), 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "compared")
        with self.assertRaises(SystemExit):
            main(["--baseline", str(baseline), "--candidate", str(candidate),
                  "--output", str(output)])

    def test_nesting_not_claimed_when_intervals_do_not_contain(self):
        baseline = write_field(self.root / "base", wire=wire_rows(nested=False))
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire_rows(nested=False),
                                manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        self.assertFalse(outcome["candidate"]["nesting"]["gc_nested_in_native_wait"])

    def test_gc_free_rows_are_rejected_and_not_zero(self):
        baseline = write_field(self.root / "base", wire=[{"kind": "sensor", "tick": 1}])
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=[{"kind": "sensor", "tick": 1}],
                                manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertTrue(any("missing_diagnostic_marks" in reason for reason in outcome["reasons"]))
        self.assertEqual(outcome["candidate"]["gc"]["samples"], 0)
        self.assertIsNone(outcome["candidate"]["gc"]["thread_cpu_max_ns"])
        self.assertIsNone(outcome["candidate"]["gc"]["gen2_thread_cpu_max_ns"])
        self.assertEqual(outcome["candidate"]["nesting"]["status"], "unavailable")
        self.assertNotIn("deltas", outcome)

    def test_timed_window_separates_preparation_gc_from_flight_gc(self):
        preparation_gc_ns = 30_000_000
        wire = wire_rows(preparation_gc_ns=preparation_gc_ns)
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        windows = outcome["candidate"]["gc_windows"]
        self.assertEqual(windows["bounds"]["status"], "observed")
        self.assertEqual(windows["bounds"]["timed_start_ns"], IDEAL_START_NS)
        self.assertEqual(windows["bounds"]["timed_end_ns"], LATCH_ISSUED_NS)
        self.assertEqual(windows["preparation"]["gen2_samples"], 1)
        self.assertEqual(windows["preparation"]["gen2_thread_cpu_max_ns"], preparation_gc_ns)
        self.assertEqual(windows["preparation"]["thread_cpu_sum_ns"], preparation_gc_ns)
        self.assertEqual(windows["timed"]["gen2_thread_cpu_max_ns"], 24_000_000)
        self.assertEqual(windows["timed"]["thread_cpu_sum_ns"], 24_000_000)
        # The full ledger still holds both collections.
        self.assertEqual(outcome["candidate"]["gc"]["gen2_samples"], 2)
        self.assertEqual(outcome["candidate"]["gc"]["gen2_thread_cpu_max_ns"], preparation_gc_ns)
        # Deltas compare the timed window, and the preparation cost is explicit.
        self.assertEqual(outcome["deltas"]["gc_gen2_max_thread_cpu_ns"]["candidate"], 24_000_000)
        self.assertEqual(outcome["deltas"]["gc_gen2_max_thread_cpu_ns"]["gc_window"], "timed")
        self.assertEqual(outcome["deltas"]["preparation_gc_thread_cpu_sum_ns"]["candidate"],
                         preparation_gc_ns)
        self.assertEqual(outcome["candidate"]["nesting"]["window"], "timed")
        self.assertEqual(outcome["candidate"]["nesting"]["tick"], 52)
        self.assertEqual(outcome["nesting"]["window"], "timed")
        self.assertEqual(outcome["nesting"]["tick"], 52)

    def test_boundary_straddling_gc_is_reported_unclassified(self):
        wire = wire_rows(straddling=True)
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        windows = outcome["candidate"]["gc_windows"]
        self.assertEqual(windows["unclassified_boundary_straddling"]["samples"], 1)
        self.assertEqual(windows["unclassified_boundary_straddling"]["thread_cpu_max_ns"],
                         100_000_000)
        self.assertEqual(windows["timed"]["thread_cpu_sum_ns"], 24_000_000)
        self.assertEqual(windows["all"]["samples"], 2)
        self.assertNotIn(100_000_000,
                         [windows["timed"]["thread_cpu_max_ns"]])
        self.assertEqual(outcome["deltas"]["gc_gen2_max_thread_cpu_ns"]["candidate"], 24_000_000)

    def test_gc_without_clock_is_unclassified_not_dropped(self):
        wire = wire_rows(missing_clock=True)
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertTrue(any("timebase_inconsistent" in reason for reason in outcome["reasons"]))
        windows = outcome["candidate"]["gc_windows"]
        self.assertEqual(windows["unclassified_missing_clock"]["samples"], 1)
        self.assertEqual(windows["timed"]["samples"], 0)
        self.assertEqual(windows["all"]["samples"], 1)
        self.assertEqual(outcome["candidate"]["nesting"]["status"], "unavailable")
        self.assertNotIn("deltas", outcome)

    def test_missing_anchor_makes_timed_windows_unavailable(self):
        rows = rate_rows(with_anchor=False)
        baseline = write_field(self.root / "base", rate=rows)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", rate=rows, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertTrue(any("timed_windows_unavailable" in reason
                            or "incomplete_window" in reason
                            or "timebase_inconsistent" in reason
                            for reason in outcome["reasons"]))
        windows = outcome["candidate"]["gc_windows"]
        self.assertEqual(windows["bounds"]["status"], "unavailable")
        self.assertEqual(windows["bounds"]["reason"], "no_rate_anchor")
        self.assertEqual(windows["unclassified_no_bounds"]["samples"], 1)
        self.assertIsNone(windows["timed"]["thread_cpu_max_ns"])
        self.assertNotIn("deltas", outcome)

    def test_freeze_count_is_object_count_not_call_count(self):
        # One freeze on a real manager graph moves thousands of objects, and
        # releasing ordinary references can shrink the count without a second
        # freeze: after > restore_before >= 0 is legal.
        report, _ = real_candidate_report()
        report = {**report, "freeze_count_after": 6623,
                  "after": {**report["after"], "freeze_count": 6623},
                  "restore": {**report["restore"], "freeze_count_before_unfreeze": 6622}}
        baseline = write_field(self.root / "base")
        candidate = write_field(self.root / "cand", manager_report=report)
        outcome = self.compare(baseline, candidate)
        contract = outcome["candidate"]["manager_gc_candidate_contract"]
        self.assertEqual(outcome["status"], "compared")
        self.assertEqual(contract["status"], "validated")
        self.assertEqual(contract["validated_fields"]["after_freeze_count"], 6623)
        self.assertEqual(contract["validated_fields"]["freeze_count_after"], 6623)
        self.assertEqual(contract["validated_fields"]["restore"]["freeze_count_after_unfreeze"], 0)

    def test_freeze_count_inconsistencies_are_rejected(self):
        report, _ = real_candidate_report()
        variants = {
            "report_and_snapshot_disagree": {
                "freeze_count_after": 6624,
                "after": {**report["after"], "freeze_count": 6623}},
            "restore_before_exceeds_frozen": {
                "freeze_count_after": 10, "after": {**report["after"], "freeze_count": 10},
                "restore": {**report["restore"], "freeze_count_before_unfreeze": 11}},
            "after_not_positive": {"after": {**report["after"], "freeze_count": 0},
                                   "freeze_count_after": 0},
            "restore_after_not_zero": {
                "restore": {**report["restore"], "freeze_count_after_unfreeze": 5}},
        }
        baseline = write_field(self.root / "base")
        for label, overrides in variants.items():
            with self.subTest(label):
                mutated = {**report, **overrides}
                candidate = write_field(self.root / label, manager_report=mutated)
                outcome = self.compare(baseline, candidate)
                self.assertEqual(outcome["status"], "rejected",
                                 outcome["candidate"]["manager_gc_candidate_contract"])
                self.assertEqual(
                    outcome["candidate"]["manager_gc_candidate_contract"]["status"], "rejected")

    def test_boot_id_from_sidecar_is_accepted(self):
        document = result_document(boot_id=None)
        document.pop("host_boot_id", None)
        baseline = write_field(self.root / "base", result=document)
        (baseline / "terminal-cleanup.json").write_text(
            json.dumps({"boot_id": BOOT_A}), encoding="utf-8")
        report, _ = real_candidate_report()
        cand_doc = result_document(manager_report=report, boot_id=None)
        cand_doc.pop("host_boot_id", None)
        candidate = write_field(self.root / "cand", result=cand_doc, manager_report=report)
        (candidate / "terminal-cleanup.json").write_text(
            json.dumps({"boot_id": BOOT_A}), encoding="utf-8")
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        self.assertEqual(outcome["baseline"]["boot_id"], BOOT_A)
        self.assertTrue(outcome["identity_compatibility"]["fields"]["boot_match"])

    def test_different_boot_is_rejected(self):
        baseline = write_field(self.root / "base",
                               result=result_document(boot_id=BOOT_A))
        report, _ = real_candidate_report()
        candidate = write_field(
            self.root / "cand",
            result=result_document(boot_id=BOOT_B, manager_report=report),
            manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["boot_match"])
        self.assertTrue(any("boot:" in item
                            for item in outcome["identity_compatibility"]["differences"]))
        self.assertNotIn("deltas", outcome)
        self.assertFalse(outcome["claim_class"]["causal"])

    def test_missing_boot_is_rejected(self):
        baseline = write_field(self.root / "base",
                               result=result_document(boot_id=None))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["boot_match"])

    def test_different_source_sha_is_rejected(self):
        baseline = write_field(
            self.root / "base",
            result=result_document(source_sha256={
                **SOURCE_SHA, "tools/run_joint_flight.py": "aa" * 32}))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["source_match"])
        self.assertTrue(any("source:" in item
                            for item in outcome["identity_compatibility"]["differences"]))

    def test_source_changed_flag_is_rejected(self):
        baseline = write_field(self.root / "base",
                               result=result_document(source_unchanged=False))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["source_unchanged_match"])

    def test_overflow_or_lost_is_rejected(self):
        wire = wire_rows() + [{"kind": "diagnostic_gc_timing", "epoch": EPOCH_A,
                               "tick": 60, "generation": 1, "lost": 3,
                               "wall_start_ns": 1_020_000_000,
                               "wall_end_ns": 1_020_100_000, "thread_cpu_ns": 1000}]
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertTrue(any("overflow_or_lost" in reason for reason in outcome["reasons"]))
        self.assertNotIn("deltas", outcome)

    def test_known_fields_with_different_conditions_are_not_paired(self):
        self.assertEqual(known_field_token("joint-public-flight-oayggl_s"), "oayggl_s")
        report, _ = real_candidate_report()
        pairs = (
            ("joint-public-flight-oayggl_s", "joint-public-flight-x39qjvkw"),
            ("joint-public-flight-x39qjvkw", "joint-public-flight-5lfbcy43"),
            ("joint-public-flight-oayggl_s", "joint-public-flight-rfw9nmbb"),
            ("joint-public-flight-5lfbcy43", "joint-public-flight-rfw9nmbb"),
        )
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                baseline = write_field(
                    self.root / left,
                    result=result_document(run_id=left))
                candidate = write_field(
                    self.root / right,
                    result=result_document(run_id=right, manager_report=report),
                    manager_report=report)
                outcome = self.compare(baseline, candidate)
                self.assertEqual(outcome["status"], "rejected")
                self.assertFalse(outcome["identity_compatibility"]["compatible"])
                self.assertFalse(
                    outcome["identity_compatibility"]["fields"]["known_field_compatible"])
                self.assertTrue(any("known_field_condition" in item
                                    for item in outcome["identity_compatibility"]["differences"]))
                self.assertNotIn("deltas", outcome)
                self.assertTrue(outcome["claim_class"]["descriptive"])
                self.assertFalse(outcome["claim_class"]["controlled_pairing"])
                self.assertFalse(outcome["claim_class"]["causal"])

    def test_group_work_timing_mark_does_not_pair_with_unprobed_field(self):
        baseline = write_field(
            self.root / "base",
            result=result_document(run_id="joint-public-flight-oayggl_s"))
        report, _ = real_candidate_report()
        candidate = write_field(
            self.root / "cand",
            result=result_document(run_id="joint-public-flight-rfw9nmbb",
                                   manager_report=report,
                                   group_work_timing={"reports_dropped": 2}),
            manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "rejected")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["group_work_timing_match"])
        self.assertTrue(any("known_field_condition" in item
                            for item in outcome["identity_compatibility"]["differences"]))

    def test_real_gc_subprocess_lifecycle_fixture(self):
        """Real ManagerGCFreeze + the real collector, in a plain child process.

        This is a FIXTURE built by the test in a temporary directory with no
        native/ROS/SITL involved. It is not flight evidence, is never written
        into a retained validation path, and its report is not a performance
        claim. It pins the object-count semantics that a hardcoded == 1 missed.
        """
        module_path = manager_gc_path()
        if module_path is None:
            self.skipTest("real manager_gc_candidate.py not reachable")
        completed = subprocess.run(
            [sys.executable, "-c", REAL_GC_CHILD, str(module_path), MANAGER_GC_SHA256],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertFalse(report["performance_pass"])
        self.assertEqual(report["classification"], "candidate_not_performance_pass")
        self.assertGreaterEqual(report["after"]["freeze_count"], 1000)
        self.assertEqual(report["after"]["freeze_count"], report["freeze_count_after"])
        self.assertEqual(report["restore"]["freeze_count_after_unfreeze"], 0)
        self.assertTrue(report["restore"]["restored_to_original"])
        self.assertLessEqual(report["restore"]["freeze_count_before_unfreeze"],
                             report["after"]["freeze_count"])
        self.assertEqual(report["prepare_check"]["thresholds"], report["original"]["thresholds"])
        self.assertEqual(report["activation"]["clock_tick"], 0)
        baseline = write_field(self.root / "base")
        candidate = write_field(self.root / "cand", manager_report=report)
        outcome = self.compare(baseline, candidate)
        contract = outcome["candidate"]["manager_gc_candidate_contract"]
        self.assertEqual(contract["status"], "validated")
        self.assertEqual(contract["validated_fields"]["after_freeze_count"],
                         report["after"]["freeze_count"])


class TypeStructurePairingGateTests(unittest.TestCase):
    """Official regressions for the 2026-09-14 independent-review P2 cases."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def compare(self, baseline_dir, candidate_dir, **kwargs):
        return compare(baseline_dir, candidate_dir, {}, {}, **kwargs)

    def candidate_field(self, name, **kwargs):
        report = kwargs.pop("report", None)
        if report is None:
            report, _ = real_candidate_report()
        return write_field(self.root / name, manager_report=report, **kwargs), report

    def assert_fail_closed(self, outcome, *needles):
        self.assertIn(outcome["status"], ("rejected", "unavailable"))
        self.assertNotEqual(outcome["status"], "compared")
        self.assertTrue(outcome["claim_class"]["descriptive"])
        self.assertFalse(outcome["claim_class"]["controlled_pairing"])
        self.assertFalse(outcome["claim_class"]["causal"])
        self.assertFalse(outcome["performance_pass"])
        self.assertNotIn("deltas", outcome)
        blob = " ".join(str(item) for item in (outcome.get("reasons") or []))
        for needle in needles:
            self.assertIn(needle, blob, blob)

    def test_bool_anchor_wall_ns_is_rejected(self):
        rows = rate_rows()
        for row in rows:
            if row.get("kind") == "rate_anchor":
                row["anchor"]["wall_ns"] = True
        baseline = write_field(self.root / "base", rate=rows)
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "invalid_clock")
        self.assertNotEqual(
            outcome["baseline"]["rate_scan"]["timed_bounds"]["status"], "observed")

    def test_bool_issued_monotonic_ns_is_rejected(self):
        rows = rate_rows()
        for row in rows:
            if row.get("kind") == "rate_unmet":
                row["issued_monotonic_ns"] = True
        baseline = write_field(self.root / "base", rate=rows)
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "invalid_clock")
        self.assertIsNone(outcome["baseline"]["rate_scan"]["timed_bounds"]["timed_end_ns"])

    def test_reversed_gc_interval_is_rejected(self):
        wire = wire_rows()
        for row in wire:
            if row.get("kind") == "diagnostic_gc_timing":
                row["wall_start_ns"] = 1_020_000_000
                row["wall_end_ns"] = 1_010_000_000
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "timebase_inconsistent")
        self.assertEqual(
            outcome["baseline"]["gc_windows"]["unclassified_reversed_interval"]["samples"], 1)
        self.assertEqual(outcome["baseline"]["gc_windows"]["timed"]["samples"], 0)

    def test_nan_thread_cpu_is_rejected_and_cli_writes_stable_json(self):
        wire = wire_rows()
        for row in wire:
            if row.get("kind") == "diagnostic_gc_timing":
                row["thread_cpu_ns"] = float("nan")
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "invalid_cost")
        output = self.root / "nan-cli.json"
        code = main(["--baseline", str(baseline), "--candidate", str(candidate),
                     "--output", str(output)])
        self.assertEqual(code, 1)
        loaded = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn(loaded["status"], ("rejected", "unavailable"))
        self.assertFalse(loaded["claim_class"]["controlled_pairing"])
        self.assertFalse(loaded["performance_pass"])
        json.dumps(loaded, allow_nan=False)

    def test_lost_infinity_is_rejected(self):
        baseline = write_field(self.root / "base", result=result_document(lost=float("inf")))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "overflow_or_lost")
        self.assertEqual(outcome["baseline"]["integrity"]["status"], "rejected")

    def test_lost_string_is_rejected(self):
        baseline = write_field(self.root / "base", result=result_document(lost="3"))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "overflow_or_lost")
        self.assertEqual(outcome["baseline"]["integrity"]["status"], "rejected")

    def test_result_json_array_is_unavailable_not_attribute_error(self):
        baseline = write_field(self.root / "base")
        (self.root / "base" / "result.json").write_text("[]", encoding="utf-8")
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "result_unreadable")
        self.assertEqual(outcome["baseline"]["analysis_status"], "unavailable")
        self.assertTrue(any("TypeError" in reason or "result_not_object" in reason
                            for reason in outcome["baseline"]["reasons"]))

    def test_source_map_string_is_unavailable_not_attribute_error(self):
        document = result_document()
        document["source_sha256"] = "not-a-map"
        baseline = write_field(self.root / "base", result=document)
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "result_unreadable")
        self.assertEqual(outcome["baseline"]["analysis_status"], "unavailable")

    def test_known_field_cannot_pair_with_anonymous_run(self):
        baseline = write_field(
            self.root / "base",
            result=result_document(run_id="joint-public-flight-oayggl_s"))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome)
        self.assertFalse(outcome["identity_compatibility"]["fields"]["known_field_compatible"])
        self.assertTrue(any("known_field_vs_anonymous" in item
                            for item in outcome["identity_compatibility"]["differences"]))

    def test_empty_source_maps_cannot_be_controlled_pairing(self):
        baseline = write_field(self.root / "base", result=result_document(source_sha256={}))
        report, _ = real_candidate_report()
        candidate = write_field(
            self.root / "cand",
            result=result_document(source_sha256={}, manager_report=report),
            manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "source:unverifiable_or_empty")
        self.assertFalse(outcome["identity_compatibility"]["fields"]["source_match"])

    def test_negative_gc_clock_is_rejected(self):
        wire = wire_rows()
        for row in wire:
            if row.get("kind") == "diagnostic_gc_timing":
                row["wall_start_ns"] = -20
                row["wall_end_ns"] = -10
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "invalid_clock")
        self.assertEqual(
            outcome["baseline"]["gc_windows"]["unclassified_invalid_clock"]["samples"], 1)

    def test_lost_zero_remains_clean(self):
        baseline = write_field(self.root / "base", result=result_document(lost=0))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        self.assertEqual(outcome["baseline"]["integrity"]["status"], "clean")
        self.assertTrue(outcome["claim_class"]["controlled_pairing"])
        self.assertFalse(outcome["claim_class"]["causal"])

    def test_zero_duration_gc_interval_is_legal(self):
        wire = wire_rows()
        for row in wire:
            if row.get("kind") == "diagnostic_gc_timing":
                row["wall_end_ns"] = row["wall_start_ns"]
        baseline = write_field(self.root / "base", wire=wire)
        report, _ = real_candidate_report()
        candidate = write_field(self.root / "cand", wire=wire, manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        self.assertEqual(outcome["candidate"]["gc_windows"]["timed"]["samples"], 1)
        self.assertFalse(outcome["claim_class"]["causal"])

    def test_two_oayggl_s_tokens_remain_pairable(self):
        baseline = write_field(
            self.root / "base",
            result=result_document(run_id="joint-public-flight-oayggl_s"))
        report, _ = real_candidate_report()
        candidate = write_field(
            self.root / "cand",
            result=result_document(run_id="joint-public-flight-oayggl_s",
                                   manager_report=report),
            manager_report=report)
        outcome = self.compare(baseline, candidate)
        self.assertEqual(outcome["status"], "compared")
        self.assertTrue(outcome["identity_compatibility"]["fields"]["known_field_compatible"])
        self.assertTrue(outcome["claim_class"]["controlled_pairing"])
        self.assertFalse(outcome["claim_class"]["causal"])

    def test_bool_lost_is_rejected(self):
        baseline = write_field(self.root / "base", result=result_document(lost=False))
        candidate, _ = self.candidate_field("cand")
        outcome = self.compare(baseline, candidate)
        self.assert_fail_closed(outcome, "overflow_or_lost")


if __name__ == "__main__":
    unittest.main()
