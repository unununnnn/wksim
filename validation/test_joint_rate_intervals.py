"""Offline tests for tools/analyze_joint_rate_intervals.py."""

import json
from pathlib import Path
import tempfile
import unittest

from tools.analyze_joint_rate_intervals import PERIOD_NS, analyze


EPOCH = "ab" * 16


def trace(rows):
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    with handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return Path(handle.name)


def group(tick, start_ns, work_ns, ideal_start_ns, earliest_start_ns,
          epoch=EPOCH, segment_id=1, request_id="config", rate=0.5):
    common = {
        "epoch": epoch,
        "segment_id": segment_id,
        "request_id": request_id,
        "requested_rate": rate,
        "transition": False,
        "start_tick": tick,
        "end_tick": tick + 4,
        "ideal_start_ns": ideal_start_ns,
        "ideal_end_ns": ideal_start_ns + PERIOD_NS,
        "earliest_start_ns": earliest_start_ns,
        "actual_start_ns": start_ns,
    }
    return [
        {
            "kind": "rate_group_start",
            "tick": tick,
            "lateness_ns": max(0, start_ns - ideal_start_ns),
            **common,
        },
        {
            "kind": "rate_group_end",
            "tick": tick + 4,
            "actual_end_ns": start_ns + work_ns,
            "lateness_ns": max(0, start_ns + work_ns - ideal_start_ns - PERIOD_NS),
            **common,
        },
    ]


def sequence(works, release_excess_ns=250_000):
    rows = []
    ideal = 1_000_000_000
    start = ideal
    previous_work = None
    for index, work in enumerate(works):
        if previous_work is None:
            earliest = ideal
        else:
            earliest = max(ideal, start + PERIOD_NS)
            start = max(start + PERIOD_NS, start + previous_work) + release_excess_ns
        rows += group(4 + 4 * index, start, work, ideal, earliest)
        ideal += PERIOD_NS
        previous_work = work
    return rows


class IntervalTests(unittest.TestCase):
    def test_exact_decomposition_uses_previous_group_work(self):
        result = analyze(trace(sequence((4_000_000, 9_000_000, 4_000_000))))
        self.assertEqual(result["groups"], 3)
        self.assertEqual(result["intervals"], 2)
        self.assertEqual(result["creep_total_ns"], 1_500_000)
        self.assertEqual(result["work_over_total_ns"], 1_000_000)
        self.assertEqual(result["release_excess_total_ns"], 500_000)
        self.assertEqual(result["top_release_excess_intervals"][0]["release_excess_ns"], 250_000)
        self.assertEqual(
            result["creep_total_ns"],
            result["work_over_total_ns"] + result["release_excess_total_ns"],
        )

    def test_single_group_has_no_attributable_interval(self):
        result = analyze(trace(sequence((9_000_000,))))
        self.assertEqual(result["intervals"], 0)
        self.assertEqual(result["creep_total_ns"], 0)
        self.assertEqual(result["last_group_work_over_unattributed_ns"], 1_000_000)

    def test_rejects_overlap_and_catch_up(self):
        rows = sequence((9_000_000, 4_000_000))
        for row in rows[2:4]:
            row["actual_start_ns"] = rows[0]["actual_start_ns"] + PERIOD_NS - 1
            row["earliest_start_ns"] = row["actual_start_ns"]
        rows[2]["lateness_ns"] = max(0, rows[2]["actual_start_ns"] - rows[2]["ideal_start_ns"])
        rows[3]["actual_end_ns"] = rows[3]["actual_start_ns"] + 4_000_000
        rows[3]["lateness_ns"] = max(0, rows[3]["actual_end_ns"] - rows[3]["ideal_end_ns"])
        with self.assertRaises(ValueError):
            analyze(trace(rows))

    def test_rejects_unpaired_duplicate_and_out_of_order_records(self):
        rows = sequence((4_000_000,))
        with self.assertRaises(ValueError):
            analyze(trace(rows[:1]))
        with self.assertRaises(ValueError):
            analyze(trace([rows[0], rows[0], rows[1]]))
        with self.assertRaises(ValueError):
            analyze(trace([rows[1], rows[0]]))
        with self.assertRaises(ValueError):
            analyze(trace([rows[0], rows[1], rows[1]]))

    def test_rejects_epoch_identity_and_tick_discontinuity(self):
        rows = sequence((4_000_000, 4_000_000))
        rows[2]["epoch"] = "cd" * 16
        rows[3]["epoch"] = "cd" * 16
        with self.assertRaises(ValueError):
            analyze(trace(rows))
        rows = sequence((4_000_000, 4_000_000))
        for row in rows[2:4]:
            row["tick"] += 4
            row["start_tick"] += 4
            row["end_tick"] += 4
        with self.assertRaises(ValueError):
            analyze(trace(rows))

    def test_rejects_wrong_rate_period_and_lateness(self):
        rows = sequence((4_000_000,))
        rows[0]["requested_rate"] = 1.0
        with self.assertRaises(ValueError):
            analyze(trace(rows))
        rows = sequence((4_000_000,))
        rows[1]["ideal_end_ns"] += 1
        with self.assertRaises(ValueError):
            analyze(trace(rows))
        rows = sequence((4_000_000,))
        rows[0]["lateness_ns"] += 1
        with self.assertRaises(ValueError):
            analyze(trace(rows))

    def test_rejects_malformed_json_and_noncanonical_epoch(self):
        bad = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        with bad:
            bad.write("{not json\n")
        with self.assertRaises(ValueError):
            analyze(Path(bad.name))
        rows = sequence((4_000_000,))
        rows[0]["epoch"] = rows[0]["epoch"].upper()
        with self.assertRaises(ValueError):
            analyze(trace(rows))


if __name__ == "__main__":
    unittest.main()
