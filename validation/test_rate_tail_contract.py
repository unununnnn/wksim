"""Contract tests for the retained 0.5x rate-tail analyzers.

Two real-data findings are covered with small synthetic records:

1. Latch reconciliation (implemented in tools/analyze_joint_rate_intervals.py).
   The interval report now closes the recorded failure latch against the
   measured increments:

       first_group_start_lateness_ns + creep_total_ns + terminal_unreconciled_ns
           == recorded_latch_lateness_ns

   The terminal increment covers both an end-of-group work overrun and a
   release-wait latch that fires in ``JointRate.begin_group`` before the next
   ``rate_group_start`` is written (the zzmg3k47 / tpwl1k4p shape). A missing
   latch is reported as ``unavailable`` with null values, a latch from another
   epoch/segment/request is isolated instead of joined, and a residual below the
   measured increments fails closed instead of being clamped with max(0).

   Real traces these tests encode:
       zzmg3k47 creep_total_ns=99881013, first=118903, terminal=92179, latch=100092095
       tpwl1k4p creep_total_ns=99877507, first=116719, terminal=44659, latch=100038885
       nqyqcagl creep_total_ns=97921130, first=115025, terminal=6224284, latch=104260439
       8fmacpgy creep_total_ns=70719737, first=114791, terminal=63993754, latch=134828282

2. Probe-free formal traces are valid data but are not phase-attributed.
   tools/analyze_joint_rate_tail_phases.py requires "started" rate_timing_probe
   rows while Simulator/wksim_runtime/joint_profile.py rejects formal mixed/PV
   evidence that contains rate_timing_probe. The same synthetic trace is
   therefore analyzable by the interval tool and refused by the tail tool; the
   refusal is what keeps the tool from inventing a phase split, so this test
   pins the message rather than a fabricated attribution.

Run: python -m unittest validation.test_rate_tail_contract
"""

import json
from pathlib import Path
import tempfile
import unittest

from tools.analyze_joint_rate_intervals import PERIOD_NS, analyze as analyze_intervals
from tools.analyze_joint_rate_tail_phases import analyze as analyze_tail_phases


EPOCH = "1a" * 16
OTHER_EPOCH = "2b" * 16
FIRST_TICK = 40
IDEAL_START_NS = 1_000_000_000
FIRST_START_LATENESS_NS = 50_000
LAST_START_LATENESS_NS = 200_000
TERMINAL_INCREMENT_NS = 150_000
LATCH_LATENESS_NS = 350_000
LAST_BOUNDARY_TICK = FIRST_TICK + 8


def _group(tick, ideal_start_ns, earliest_start_ns, actual_start_ns, work_ns,
           epoch=EPOCH, segment_id=1, request_id="config"):
    """One complete four-tick group pair."""
    common = {
        "epoch": epoch,
        "segment_id": segment_id,
        "request_id": request_id,
        "requested_rate": 0.5,
        "transition": False,
        "start_tick": tick,
        "end_tick": tick + 4,
        "ideal_start_ns": ideal_start_ns,
        "ideal_end_ns": ideal_start_ns + PERIOD_NS,
        "earliest_start_ns": earliest_start_ns,
        "actual_start_ns": actual_start_ns,
    }
    return [
        {
            "kind": "rate_group_start",
            "tick": tick,
            "lateness_ns": max(0, actual_start_ns - ideal_start_ns),
            **common,
        },
        {
            "kind": "rate_group_end",
            "tick": tick + 4,
            "actual_end_ns": actual_start_ns + work_ns,
            "lateness_ns": max(0, actual_start_ns + work_ns - ideal_start_ns - PERIOD_NS),
            **common,
        },
    ]


def _latch(lateness_ns, tick=LAST_BOUNDARY_TICK, epoch=EPOCH, segment_id=1,
           request_id="config"):
    return {
        "kind": "rate_unmet",
        "epoch": epoch,
        "tick": tick,
        "issued_monotonic_ns": 2_000_000_000,
        "reason": "resource_insufficient",
        "lateness_ns": lateness_ns,
        "requested_rate": 0.5,
        "request_id": request_id,
        "segment_id": segment_id,
        "latched": True,
        "anchor": {"tick": FIRST_TICK, "wall_ns": IDEAL_START_NS, "transition": False},
        "measured_rate": 0.499,
        "worst_lateness_ns": lateness_ns,
    }


def _two_groups(second_work_ns=3_000_000):
    """Two closed groups: creep 150000 ns and a 50000 ns first-group offset."""
    first_start = IDEAL_START_NS + FIRST_START_LATENESS_NS
    rows = _group(FIRST_TICK, IDEAL_START_NS, IDEAL_START_NS, first_start, 4_000_000)
    second_ideal = IDEAL_START_NS + PERIOD_NS
    second_earliest = max(second_ideal, first_start + PERIOD_NS)
    second_start = second_ideal + LAST_START_LATENESS_NS
    rows += _group(FIRST_TICK + 4, second_ideal, second_earliest, second_start,
                   second_work_ns)
    return rows


def write_trace(rows):
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "rate.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return directory, path


class LatchReconciliationTests(unittest.TestCase):
    def analyze(self, rows):
        directory, path = write_trace(rows)
        self.addCleanup(directory.cleanup)
        return analyze_intervals(path)

    def test_begin_group_latch_closes_against_interval_totals(self):
        result = self.analyze(_two_groups() + [_latch(LATCH_LATENESS_NS)])
        self.assertEqual(result["status"], "analyzed")
        self.assertEqual(result["groups"], 2)
        self.assertEqual(result["intervals"], 1)
        self.assertEqual(result["creep_total_ns"], TERMINAL_INCREMENT_NS)
        self.assertEqual(result["first_group_start_lateness_ns"], FIRST_START_LATENESS_NS)
        self.assertEqual(result["terminal_unreconciled_ns"], TERMINAL_INCREMENT_NS)
        self.assertEqual(result["recorded_latch_lateness_ns"], LATCH_LATENESS_NS)
        self.assertEqual(
            result["first_group_start_lateness_ns"] + result["creep_total_ns"]
            + result["terminal_unreconciled_ns"],
            result["recorded_latch_lateness_ns"],
        )
        latch = result["latch_reconciliation"]
        self.assertEqual(latch["status"], "reconciled")
        self.assertTrue(latch["closes"])
        self.assertEqual(latch["latch_site"], "begin_group_release_wait")
        self.assertEqual(latch["rate_unmet_tick"], LAST_BOUNDARY_TICK)
        self.assertEqual(latch["last_group_start_lateness_ns"], LAST_START_LATENESS_NS)
        self.assertEqual(latch["last_group_end_lateness_ns"], 0)
        self.assertEqual(latch["foreign_rate_unmet"], [])
        # The pre-existing work-over field cannot carry this residual: the last
        # group's work stays below one period. That is why the terminal field
        # exists.
        self.assertEqual(result["last_group_work_over_unattributed_ns"], 0)

    def test_end_group_latch_closes_against_last_group_work(self):
        work_over_ns = 400_000
        end_lateness_ns = LAST_START_LATENESS_NS + work_over_ns
        rows = _two_groups(second_work_ns=PERIOD_NS + work_over_ns)
        result = self.analyze(rows + [_latch(end_lateness_ns)])
        self.assertEqual(result["creep_total_ns"], TERMINAL_INCREMENT_NS)
        self.assertEqual(result["terminal_unreconciled_ns"], work_over_ns)
        self.assertEqual(result["recorded_latch_lateness_ns"], end_lateness_ns)
        self.assertEqual(result["last_group_work_over_unattributed_ns"], work_over_ns)
        latch = result["latch_reconciliation"]
        self.assertEqual(latch["status"], "reconciled")
        self.assertEqual(latch["latch_site"], "end_group")
        self.assertEqual(latch["last_group_end_lateness_ns"], end_lateness_ns)
        self.assertEqual(
            result["first_group_start_lateness_ns"] + result["creep_total_ns"]
            + result["terminal_unreconciled_ns"],
            result["recorded_latch_lateness_ns"],
        )

    def test_missing_latch_is_unavailable_not_zero(self):
        result = self.analyze(_two_groups())
        self.assertEqual(result["status"], "analyzed")
        self.assertEqual(result["first_group_start_lateness_ns"], FIRST_START_LATENESS_NS)
        self.assertIsNone(result["recorded_latch_lateness_ns"])
        self.assertIsNone(result["terminal_unreconciled_ns"])
        self.assertNotEqual(result["terminal_unreconciled_ns"], 0)
        latch = result["latch_reconciliation"]
        self.assertEqual(latch["status"], "unavailable")
        self.assertEqual(latch["reason"], "no_rate_unmet_for_identity")
        self.assertIsNone(latch["closes"])
        self.assertIsNone(latch["latch_site"])
        self.assertIsNone(latch["rate_unmet_tick"])
        self.assertEqual(latch["foreign_rate_unmet"], [])

    def test_foreign_epoch_and_segment_latches_are_isolated(self):
        rows = _two_groups() + [
            _latch(LATCH_LATENESS_NS, epoch=OTHER_EPOCH),
            _latch(LATCH_LATENESS_NS + 1, segment_id=2),
        ]
        result = self.analyze(rows)
        latch = result["latch_reconciliation"]
        self.assertEqual(latch["status"], "unavailable")
        self.assertEqual(latch["reason"], "no_rate_unmet_for_identity")
        self.assertIsNone(result["recorded_latch_lateness_ns"])
        self.assertIsNone(result["terminal_unreconciled_ns"])
        foreign = latch["foreign_rate_unmet"]
        self.assertEqual(len(foreign), 2)
        self.assertEqual(
            sorted(entry["epoch"] for entry in foreign), sorted([EPOCH, OTHER_EPOCH]))
        self.assertEqual(
            sorted(entry["segment_id"] for entry in foreign), [1, 2])

    def test_matching_latch_ignores_foreign_record(self):
        rows = _two_groups() + [
            _latch(LATCH_LATENESS_NS),
            _latch(9_000_000, epoch=OTHER_EPOCH),
        ]
        result = self.analyze(rows)
        latch = result["latch_reconciliation"]
        self.assertEqual(latch["status"], "reconciled")
        self.assertEqual(result["recorded_latch_lateness_ns"], LATCH_LATENESS_NS)
        self.assertEqual(result["terminal_unreconciled_ns"], TERMINAL_INCREMENT_NS)
        self.assertEqual(len(latch["foreign_rate_unmet"]), 1)
        self.assertEqual(latch["foreign_rate_unmet"][0]["epoch"], OTHER_EPOCH)

    def test_latch_below_measured_increments_is_rejected(self):
        # 180000 < first_group_start_lateness + creep_total, so the residual is
        # negative; a max(0) clamp would silently hide that contradiction.
        rows = _two_groups() + [_latch(180_000)]
        with self.assertRaisesRegex(ValueError, "negative"):
            self.analyze(rows)

    def test_latch_at_another_boundary_is_rejected(self):
        rows = _two_groups() + [_latch(LATCH_LATENESS_NS, tick=FIRST_TICK + 12)]
        with self.assertRaisesRegex(ValueError, "is not the last group boundary"):
            self.analyze(rows)

    def test_duplicate_matching_latches_are_rejected(self):
        # Two latches with the loaded identity cannot be assigned to one
        # schedule; picking one silently would be a cross-record join.
        rows = _two_groups() + [_latch(LATCH_LATENESS_NS), _latch(LATCH_LATENESS_NS)]
        with self.assertRaisesRegex(ValueError, "multiple rate_unmet records"):
            self.analyze(rows)


class ProbeFreeTailContractTests(unittest.TestCase):
    def test_probe_free_trace_analyzes_but_has_no_phase_attribution(self):
        """No probe rows is valid evidence, not damaged evidence."""
        directory, path = write_trace(_two_groups() + [_latch(LATCH_LATENESS_NS)])
        self.addCleanup(directory.cleanup)
        # The interval tool accepts the same trace and closes its latch.
        result = analyze_intervals(path)
        self.assertEqual(result["status"], "analyzed")
        self.assertEqual(result["latch_reconciliation"]["status"], "reconciled")
        # The tail tool refuses to attribute phases instead of inventing them.
        with self.assertRaisesRegex(ValueError, "No rate_timing_probe samples"):
            analyze_tail_phases(path)


if __name__ == "__main__":
    unittest.main()
