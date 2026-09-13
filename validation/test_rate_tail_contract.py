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

from tools.analyze_joint_rate_intervals import (
    PERIOD_NS, TICKS_PER_GROUP, analyze as analyze_intervals)
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


# -- five-group chain with hand-computable creep/work-over/release-excess -----
# Group starts are 8 ms apart plus a deliberate 100/200/300/400 us creep, and
# the first two groups carry work over one period so work_over is non-zero.
CHAIN_ANCHOR_TICK = 44
_CHAIN_ACTUAL_OFFSETS = (0, PERIOD_NS + 100_000, 2 * PERIOD_NS + 300_000,
                         3 * PERIOD_NS + 600_000, 4 * PERIOD_NS + 1_000_000)
_CHAIN_WORKS = (PERIOD_NS + 60_000, PERIOD_NS, PERIOD_NS + 120_000,
                PERIOD_NS, PERIOD_NS)


def _chain_actual_start(index):
    return IDEAL_START_NS + _CHAIN_ACTUAL_OFFSETS[index]


def _chain_latch(lateness_ns=1_100_000):
    """A latch matching the five-group chain: boundary tick 64, creep 1_000_000."""
    return _latch(lateness_ns, tick=CHAIN_ANCHOR_TICK + TICKS_PER_GROUP * len(_CHAIN_WORKS))


def _chain():
    rows = []
    previous_actual = None
    for index, work in enumerate(_CHAIN_WORKS):
        tick = CHAIN_ANCHOR_TICK + TICKS_PER_GROUP * index
        ideal = IDEAL_START_NS + index * PERIOD_NS
        actual = _chain_actual_start(index)
        if index == 0:
            earliest = ideal
        else:
            earliest = max(ideal, previous_actual + PERIOD_NS)
        rows += _group(tick, ideal, earliest, actual, work)
        previous_actual = actual
    return rows


def _anchor(steady_after_ns, anchor_wall_ns=IDEAL_START_NS, tick=CHAIN_ANCHOR_TICK,
            epoch=EPOCH):
    """A ``rate_anchor`` record carrying the wall-clock steady marker."""
    return {
        "kind": "rate_anchor",
        "epoch": epoch,
        "tick": tick,
        "issued_monotonic_ns": anchor_wall_ns + 1,
        "reason": "synchronized_boundary",
        "requested_rate": 0.5,
        "request_id": "config",
        "segment_id": 1,
        "latched": False,
        "anchor": {"tick": tick, "wall_ns": anchor_wall_ns, "transition": False},
        "measured_rate": None,
        "measurement": "timed_segment",
        "completed_groups": 0,
        "worst_lateness_ns": 0,
        "steady_after_ns": steady_after_ns,
    }


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


class PhasePartitionTests(unittest.TestCase):
    """early/steady/crossing partitioning driven by the real wall marker.

    The retained 0.5x schedule has an 8 ms wall group period, so a 2 s warm-up
    is 250 groups and the anchor tick varies between fields. The boundary must
    therefore come from the trace's own ``steady_after_ns`` and be compared
    against ``actual_start_ns``; converting seconds to ticks and adding them to
    the anchor tick is wrong for both reasons.
    """

    def analyze(self, rows):
        directory, path = write_trace(rows)
        self.addCleanup(directory.cleanup)
        return analyze_intervals(path)

    # -- synthetic five-group chain, hand-computable -----------------------

    def chain(self):
        return _chain()

    def test_rate_must_be_exactly_half_x(self):
        rows = _two_groups()
        rows[0]["requested_rate"] = 1.0
        rows[1]["requested_rate"] = 1.0
        rows += [_anchor(IDEAL_START_NS + 2_000_000_000)]
        with self.assertRaisesRegex(ValueError, "0.5"):
            self.analyze(rows)

    def test_crossing_interval_is_listed_separately_and_sums_close(self):
        # A2 + 1ms falls strictly inside the third interval.
        boundary = _chain_actual_start(2) + 1_000_000
        result = self.analyze(self.chain() + [_anchor(boundary)])
        self.assertEqual(result["status"], "analyzed")
        partition = result["phase_partition"]
        self.assertTrue(partition["available"])
        self.assertIsNone(partition["reason"])
        self.assertEqual(partition["boundary"]["source"], "rate_anchor")
        self.assertEqual(partition["boundary"]["anchor_tick"], 44)
        self.assertEqual(partition["boundary"]["steady_after_ns"], boundary)

        classes = partition["classes"]
        self.assertEqual(classes["early"]["intervals"], 2)
        self.assertEqual(classes["crossing"]["intervals"], 1)
        self.assertEqual(classes["steady"]["intervals"], 1)
        self.assertEqual(classes["early"]["creep_ns"], 300_000)
        self.assertEqual(classes["crossing"]["creep_ns"], 300_000)
        self.assertEqual(classes["steady"]["creep_ns"], 400_000)

        crossing = classes["crossing"]["crossing_interval"]
        self.assertIsNotNone(crossing)
        self.assertEqual(crossing["previous_start_tick"], 52)
        self.assertEqual(crossing["current_start_tick"], 56)
        self.assertLess(crossing["previous_actual_start_ns"], boundary)
        self.assertGreater(crossing["current_actual_start_ns"], boundary)

        closure = partition["closure"]
        self.assertTrue(closure["classes_are_disjoint"])
        self.assertEqual(closure["intervals_partitioned"], result["intervals"])
        self.assertEqual(closure["creep_residual_ns"], 0)
        self.assertEqual(closure["work_over_residual_ns"], 0)
        self.assertEqual(closure["release_excess_residual_ns"], 0)
        self.assertTrue(closure["closes"])

    def test_partition_sums_equal_the_published_totals_exactly(self):
        boundary = _chain_actual_start(2) + 1_000_000
        result = self.analyze(self.chain() + [_anchor(boundary)])
        classes = result["phase_partition"]["classes"]
        for class_key, total_key in (("creep_ns", "creep_total_ns"),
                                     ("work_over_ns", "work_over_total_ns"),
                                     ("release_excess_ns", "release_excess_total_ns")):
            summed = sum(classes[name][class_key]
                         for name in ("early", "crossing", "steady"))
            self.assertEqual(summed, result[total_key], class_key)
        # The hand-computed chain totals, so the identity is not vacuous.
        self.assertEqual(result["creep_total_ns"], 1_000_000)
        self.assertEqual(result["work_over_total_ns"], 180_000)
        self.assertEqual(result["release_excess_total_ns"], 820_000)

    def test_boundary_on_a_group_start_leaves_no_crossing(self):
        boundary = _chain_actual_start(2)
        result = self.analyze(self.chain() + [_anchor(boundary)])
        classes = result["phase_partition"]["classes"]
        self.assertEqual(classes["crossing"]["intervals"], 0)
        self.assertIsNone(classes["crossing"]["crossing_interval"])
        self.assertEqual(classes["crossing"]["creep_ns"], 0)
        self.assertEqual(classes["early"]["intervals"], 2)
        self.assertEqual(classes["steady"]["intervals"], 2)
        self.assertTrue(result["phase_partition"]["closure"]["closes"])

    def test_partition_follows_the_wall_marker_not_tick_arithmetic(self):
        last = _chain_actual_start(4)
        everything_early = self.analyze(
            self.chain() + [_anchor(last + 1)])["phase_partition"]
        everything_steady = self.analyze(
            self.chain() + [_anchor(IDEAL_START_NS - 1)])["phase_partition"]
        self.assertEqual(everything_early["classes"]["early"]["intervals"], 4)
        self.assertEqual(everything_early["classes"]["steady"]["intervals"], 0)
        self.assertEqual(everything_steady["classes"]["early"]["intervals"], 0)
        self.assertEqual(everything_steady["classes"]["steady"]["intervals"], 4)
        # Same groups, same ticks, opposite partitions: only the wall marker moved.
        self.assertEqual(everything_early["boundary"]["anchor_tick"],
                         everything_steady["boundary"]["anchor_tick"])
        # A realistic 2 s marker is measured as wall, never as a tick count.
        realistic = self.analyze(
            self.chain() + [_anchor(IDEAL_START_NS + 2_000_000_000)])["phase_partition"]
        self.assertEqual(realistic["boundary"]["steady_after_minus_anchor_ns"],
                         2_000_000_000)
        self.assertEqual(realistic["classes"]["early"]["intervals"], 4)

    def test_anchor_tick_does_not_change_the_partition(self):
        boundary = _chain_actual_start(2) + 1_000_000
        tick44 = self.analyze(self.chain() + [_anchor(boundary, tick=44)])
        tick40 = self.analyze(self.chain() + [_anchor(boundary, tick=40)])
        self.assertEqual(tick44["phase_partition"]["boundary"]["anchor_tick"], 44)
        self.assertEqual(tick40["phase_partition"]["boundary"]["anchor_tick"], 40)
        for name in ("early", "crossing", "steady"):
            self.assertEqual(tick44["phase_partition"]["classes"][name],
                             tick40["phase_partition"]["classes"][name])

    def test_missing_steady_marker_is_unavailable_and_fields_unchanged(self):
        # The five-group chain ends on boundary tick 64 and its creep is
        # 1_000_000 ns, so a closing latch must use that boundary and at least
        # that lateness.
        rows = self.chain() + [_chain_latch()]
        result = self.analyze(rows)
        partition = result["phase_partition"]
        self.assertFalse(partition["available"])
        self.assertEqual(partition["reason"], "no_steady_after_marker")
        self.assertIsNone(partition["boundary"])
        self.assertIsNone(partition["classes"])
        self.assertIsNone(partition["closure"])
        # The pre-existing contract is untouched by the absent marker.
        self.assertEqual(result["status"], "analyzed")
        self.assertEqual(result["creep_total_ns"], 1_000_000)
        self.assertEqual(result["latch_reconciliation"]["status"], "reconciled")

    def test_existing_interval_fields_are_not_reshaped(self):
        boundary = _chain_actual_start(2) + 1_000_000
        result = self.analyze(self.chain() + [_anchor(boundary)])
        expected = {"previous_start_tick", "current_start_tick", "creep_ns",
                    "previous_work_ns", "between_ns", "previous_work_over_ns",
                    "release_excess_ns", "cumulative_share"}
        self.assertEqual(set(result["top_creep_intervals"][0]), expected)
        self.assertEqual(set(result["top_release_excess_intervals"][0]), expected)


if __name__ == "__main__":
    unittest.main()
