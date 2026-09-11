"""Offline tests for tools/analyze_joint_rate_tail_phases.py."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.audit_joint_rate import TIMING_PROBE_IDENTITY
from tools.analyze_joint_rate_probe import PHASES
from tools.analyze_joint_rate_tail_phases import (
    LOWER_RELEASE_EXCESS_NS,
    UPPER_RELEASE_EXCESS_NS,
    analyze,
    main,
)


EPOCH = "ab" * 16
PERIOD_NS = 8_000_000


def _group_rows(releases):
    rows = []
    ideal = 1_000_000_000
    actual_start = ideal
    for index, release_excess in enumerate(releases):
        tick = 40 + 4 * index
        earliest = ideal if index == 0 else max(ideal, previous_start + PERIOD_NS)
        if index:
            actual_start = max(earliest, previous_end) + release_excess
        actual_end = actual_start + 4_000_000
        common = {
            "epoch": EPOCH,
            "segment_id": 1,
            "request_id": "config",
            "requested_rate": 0.5,
            "transition": False,
            "start_tick": tick,
            "end_tick": tick + 4,
            "ideal_start_ns": ideal,
            "ideal_end_ns": ideal + PERIOD_NS,
            "earliest_start_ns": earliest,
            "actual_start_ns": actual_start,
        }
        rows.append({
            "kind": "rate_group_start",
            "tick": tick,
            "lateness_ns": max(0, actual_start - ideal),
            **common,
        })
        entry = actual_start - 100
        entry_to_initial = 10 + index
        loop = 20 + index
        sleep = 30 + index
        final = 40 + index
        observed = entry_to_initial + loop + sleep + final
        rows.append({
            "kind": "rate_timing_probe",
            "epoch": EPOCH,
            "rate_timing_probe": dict(TIMING_PROBE_IDENTITY),
            "outcome": "started",
            "start_tick": tick,
            "end_tick": tick + 4,
            "entry_ns": entry,
            "initial_health_end_ns": entry + entry_to_initial,
            "terminal_ns": actual_start,
            "ideal_start_ns": ideal,
            "earliest_start_ns": earliest,
            "entry_to_initial_health_ns": entry_to_initial,
            "loop_health_ns": loop,
            "loop_health_calls": 1,
            "sleep_requested_ns": sleep - 5,
            "sleep_elapsed_ns": sleep,
            "sleep_calls": 1,
            "sleep_max_overshoot_ns": 5,
            "final_spin_other_ns": final,
            "release_excess_ns": max(0, actual_start - earliest),
            "observed_elapsed_ns": observed,
            "phase_total_ns": observed,
        })
        rows.append({
            "kind": "rate_group_end",
            "tick": tick + 4,
            "actual_end_ns": actual_end,
            "lateness_ns": max(0, actual_end - (ideal + PERIOD_NS)),
            **common,
        })
        previous_start = actual_start
        previous_end = actual_end
        ideal += PERIOD_NS
    return rows


def _write_trace(directory, rows, name="rate.jsonl"):
    path = Path(directory) / name
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _probe(rows, start_tick):
    return next(row for row in rows
                if row.get("kind") == "rate_timing_probe"
                and row["start_tick"] == start_tick)


class TailPhaseTests(unittest.TestCase):
    def test_selects_strict_lower_and_inclusive_upper_boundaries(self):
        rows = _group_rows([0, 100_000, 100_001, 500_000, 500_001])
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(_write_trace(directory, rows))

        self.assertEqual(result["bucket"], {
            "lower_ns": LOWER_RELEASE_EXCESS_NS,
            "upper_ns": UPPER_RELEASE_EXCESS_NS,
            "lower_inclusive": False,
            "upper_inclusive": True,
        })
        self.assertEqual(result["interval_count"], 4)
        self.assertEqual(result["selected_count"], 2)
        self.assertEqual(
            [item["current_start_tick"] for item in result["selected"]], [48, 52]
        )
        self.assertEqual(
            [item["release_excess_ns"] for item in result["selected"]],
            [100_001, 500_000],
        )
        self.assertEqual(set(result["selected"][0]) & set(PHASES), set(PHASES))
        self.assertEqual(result["selected"][0]["sleep_max_overshoot_ns"], 5)

    def test_summaries_use_nearest_rank_p95_and_p99(self):
        releases = [0] + [100_001 + index for index in range(20)]
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(_write_trace(directory, _group_rows(releases)))

        self.assertEqual(result["selected_count"], 20)
        self.assertEqual(result["percentile_method"], "nearest_rank")
        release = result["summary"]["release_excess_ns"]
        self.assertEqual(release["count"], 20)
        self.assertEqual(release["nonzero_count"], 20)
        self.assertEqual(release["total_ns"], sum(releases[1:]))
        self.assertEqual(release["mean_ns"], sum(releases[1:]) / 20)
        self.assertEqual(release["p95_ns"], 100_019)
        self.assertEqual(release["p99_ns"], 100_020)
        self.assertEqual(release["max_ns"], 100_020)
        loop = result["summary"]["loop_health_ns"]
        self.assertEqual(loop["total_ns"], sum(range(21, 41)))
        self.assertEqual(loop["p95_ns"], 39)
        self.assertEqual(loop["p99_ns"], 40)

    def test_records_diagnostic_metadata_hashes_and_limitations(self):
        rows = _group_rows([0, 200_000])
        with tempfile.TemporaryDirectory() as directory:
            path = _write_trace(directory, rows)
            result = analyze(path)
            input_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            tool_sha256 = hashlib.sha256(
                (
                    Path(__file__).resolve().parents[1]
                    / "tools/analyze_joint_rate_tail_phases.py"
                ).read_bytes()
            ).hexdigest()

        self.assertEqual(result["schema"], "wksim.rate-tail-phases.v1")
        self.assertTrue(result["diagnostic_only"])
        self.assertFalse(result["production_performance"])
        self.assertEqual(result["input_sha256"], input_sha256)
        self.assertEqual(result["tool_sha256"], tool_sha256)
        self.assertIn("correlation is not causal", " ".join(result["limitations"]))
        self.assertIn("Probe overhead is included", " ".join(result["limitations"]))
        self.assertIn("final_spin_other is residual", " ".join(result["limitations"]))
        self.assertIn("OS scheduler", " ".join(result["limitations"]))

    def test_rejects_missing_duplicate_and_mismatched_probes(self):
        cases = []
        rows = _group_rows([0, 200_000])
        cases.append([row for row in rows
                      if not (row.get("kind") == "rate_timing_probe"
                              and row["start_tick"] == 44)])
        rows = _group_rows([0, 200_000])
        duplicate = dict(_probe(rows, 44))
        rows.insert(3, duplicate)
        cases.append(rows)
        rows = _group_rows([0, 200_000])
        mismatched = _probe(rows, 44)
        mismatched["earliest_start_ns"] += 1
        mismatched["release_excess_ns"] -= 1
        cases.append(rows)
        rows = _group_rows([0, 200_000])
        mismatched = _probe(rows, 44)
        mismatched["terminal_ns"] += 1
        mismatched["observed_elapsed_ns"] += 1
        mismatched["phase_total_ns"] += 1
        mismatched["final_spin_other_ns"] += 1
        mismatched["release_excess_ns"] += 1
        cases.append(rows)

        with tempfile.TemporaryDirectory() as directory:
            for index, candidate in enumerate(cases):
                with self.subTest(case=index):
                    with self.assertRaises((AssertionError, ValueError)):
                        analyze(_write_trace(directory, candidate, f"bad-{index}.jsonl"))

    def test_rejects_malformed_and_non_diagnostic_probe_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.jsonl"
            malformed.write_text("{not json\n", encoding="utf-8")
            with self.assertRaises((AssertionError, ValueError)):
                analyze(malformed)

            rows = _group_rows([0, 200_000])
            _probe(rows, 44)["rate_timing_probe"]["classification"] = "production"
            with self.assertRaises((AssertionError, ValueError)):
                analyze(_write_trace(directory, rows, "identity.jsonl"))

    def test_rejects_non_started_probe_for_join(self):
        rows = _group_rows([0, 200_000])
        _probe(rows, 44)["outcome"] = "rate_unmet"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((AssertionError, ValueError)):
                analyze(_write_trace(directory, rows))

    def test_cli_requires_output_and_refuses_existing_output_before_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = _group_rows([0, 200_000])
            input_path = _write_trace(directory, rows)
            output_path = Path(directory) / "result.json"
            with self.assertRaises(SystemExit):
                main([str(input_path)])
            output_path.write_text("sentinel", encoding="utf-8")
            with patch(
                "tools.analyze_joint_rate_tail_phases.analyze",
                side_effect=AssertionError("analysis must not run"),
            ):
                with self.assertRaises(FileExistsError):
                    main([str(input_path), "--output", str(output_path)])
            self.assertEqual(output_path.read_text(encoding="utf-8"), "sentinel")


if __name__ == "__main__":
    unittest.main()
