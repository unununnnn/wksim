import json
from pathlib import Path
import tempfile
import unittest

from tools.analyze_joint_rate_probe import analyze
from tools.audit_joint_rate import TIMING_PROBE_IDENTITY


def sample(**updates):
    row = {
        "kind": "rate_timing_probe",
        "epoch": "a" * 32,
        "outcome": "started",
        "start_tick": 40,
        "end_tick": 44,
        "entry_ns": 100,
        "initial_health_end_ns": 110,
        "terminal_ns": 150,
        "ideal_start_ns": 120,
        "earliest_start_ns": 120,
        "entry_to_initial_health_ns": 10,
        "loop_health_ns": 5,
        "loop_health_calls": 1,
        "sleep_requested_ns": 20,
        "sleep_elapsed_ns": 25,
        "sleep_calls": 1,
        "sleep_max_overshoot_ns": 5,
        "final_spin_other_ns": 10,
        "release_excess_ns": 30,
        "observed_elapsed_ns": 50,
        "phase_total_ns": 50,
        "rate_timing_probe": dict(TIMING_PROBE_IDENTITY),
    }
    row.update(updates)
    return row


class AnalyzeJointRateProbeTests(unittest.TestCase):
    def analyze_rows(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rate.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            return analyze(path)

    def test_aggregates_closed_samples_as_diagnostic_only(self):
        result = self.analyze_rows([
            sample(),
            sample(start_tick=44, end_tick=48, outcome="rate_unmet",
                   entry_ns=130, initial_health_end_ns=140,
                   entry_to_initial_health_ns=10, loop_health_ns=0,
                   sleep_requested_ns=0, sleep_elapsed_ns=0, sleep_calls=0,
                   sleep_max_overshoot_ns=0, final_spin_other_ns=10,
                   observed_elapsed_ns=20, phase_total_ns=20),
        ])
        self.assertEqual(result["status"], "diagnostic")
        self.assertFalse(result["production_performance"])
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["outcomes"], {"rate_unmet": 1, "started": 1})
        self.assertEqual(result["phases"]["sleep_elapsed_ns"]["total_ns"], 25)
        self.assertAlmostEqual(
            sum(item["observed_share"] for item in result["phases"].values()), 1.0
        )
        self.assertEqual(result["release_excess_ns"]["entry_lateness"]["total"], 10)
        self.assertEqual(result["release_excess_ns"]["post_entry_excess"]["total"], 50)

    def test_rejects_identity_phase_and_release_tampering(self):
        cases = [
            sample(rate_timing_probe={**TIMING_PROBE_IDENTITY, "production_performance": True}),
            sample(phase_total_ns=49),
            sample(release_excess_ns=29),
            sample(sleep_max_overshoot_ns=26),
            sample(end_tick=45),
        ]
        for row in cases:
            with self.subTest(row=row), self.assertRaises((AssertionError, ValueError)):
                self.analyze_rows([row])

    def test_requires_samples_from_one_epoch(self):
        with self.assertRaises((AssertionError, ValueError)):
            self.analyze_rows([sample(), sample(epoch="b" * 32)])
        with self.assertRaises((AssertionError, ValueError)):
            self.analyze_rows([{"kind": "rate_anchor", "epoch": "a" * 32}])


if __name__ == "__main__":
    unittest.main()
