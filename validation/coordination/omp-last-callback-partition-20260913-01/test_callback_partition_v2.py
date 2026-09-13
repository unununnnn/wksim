"""Targeted positive/negative tests for partition_callback_tail v2.

Each negative isolates one v2 rule.  Synthetic rows with real field shapes;
no flight, model, ROS, build.  Standard library only.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from callback_partition_v2 import NEW_FIELDS, PartitionError, \
    partition_callback_tail  # noqa: E402


def row(**overrides):
    base = dict(
        outcome="started",
        entry_ns=1_000_000, terminal_ns=2_000_000,
        earliest_start_ns=1_500_000, initial_health_end_ns=1_100_000,
        entry_to_initial_health_ns=100_000,
        sleep_calls=0, sleep_elapsed_ns=0, sleep_requested_ns=0,
        loop_health_calls=0, loop_health_ns=0,
        final_spin_other_ns=0,
        last_sleep_before_ns=None, last_sleep_after_ns=None,
        last_sleep_requested_ns=None,
        last_health_before_ns=None, last_health_after_ns=None,
    )
    base.update(overrides)
    return base


SLEEP1 = dict(sleep_calls=1, sleep_elapsed_ns=600_000, sleep_requested_ns=590_000,
              last_sleep_before_ns=1_200_000, last_sleep_after_ns=1_800_000,
              last_sleep_requested_ns=590_000)


class PartitionV2Tests(unittest.TestCase):
    def test_started_straddle_positive(self):
        result = partition_callback_tail(row(**SLEEP1))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["window_ns"], 500_000)
        self.assertEqual(result["sleep_in_window_ns"], 300_000)
        self.assertEqual(result["tail_after_last_callback_ns"], 200_000)
        self.assertEqual(result["unattributed_ns"], 0)
        self.assertTrue(result["closure_exact"])
        self.assertTrue(result["terminal_is_release"])

    def test_rejected_before_edge_is_legal_empty_window(self):
        # a sleep fully completed, then the attempt fails before the edge
        result = partition_callback_tail(row(
            outcome="rejected", terminal_ns=1_400_000,
            earliest_start_ns=1_500_000,
            sleep_calls=1, sleep_elapsed_ns=150_000, sleep_requested_ns=140_000,
            last_sleep_before_ns=1_150_000, last_sleep_after_ns=1_300_000,
            last_sleep_requested_ns=140_000))
        self.assertEqual(result["status"], "failed_attempt")
        self.assertFalse(result["terminal_is_release"])
        self.assertEqual(result["window_ns"], 0)
        self.assertEqual(result["sleep_in_window_ns"], 0)
        self.assertEqual(result["tail_after_last_callback_ns"], 0)
        self.assertEqual(result["unattributed_ns"], 0)
        self.assertTrue(result["closure_exact"])
        self.assertIn("unobserved", result["coverage"])

    def test_started_before_edge_rejected(self):
        with self.assertRaisesRegex(PartitionError, "did not reach"):
            partition_callback_tail(row(
                outcome="started", terminal_ns=1_400_000, **SLEEP1))

    def test_zero_calls_require_zero_cumulative_and_none_fields(self):
        with self.assertRaisesRegex(PartitionError, "sleep_calls==0 but"):
            partition_callback_tail(row(sleep_elapsed_ns=1))
        with self.assertRaisesRegex(PartitionError, "sleep_requested_ns!=0"):
            partition_callback_tail(row(sleep_requested_ns=1))
        with self.assertRaisesRegex(PartitionError, "fields present"):
            partition_callback_tail(row(last_health_after_ns=1_200_000))
        with self.assertRaisesRegex(PartitionError, "non-negative"):
            partition_callback_tail(row(loop_health_ns=-1))

    def test_single_call_must_equal_cumulative(self):
        with self.assertRaisesRegex(PartitionError, "single call must equal"):
            partition_callback_tail(row(
                sleep_calls=1, sleep_elapsed_ns=700_000,
                sleep_requested_ns=590_000,
                last_sleep_before_ns=1_200_000, last_sleep_after_ns=1_800_000,
                last_sleep_requested_ns=590_000))
        with self.assertRaisesRegex(PartitionError,
                                    "single sleep requested must equal"):
            partition_callback_tail(row(
                sleep_calls=1, sleep_elapsed_ns=600_000,
                sleep_requested_ns=590_000,
                last_sleep_before_ns=1_200_000, last_sleep_after_ns=1_800_000,
                last_sleep_requested_ns=500_000))

    def test_two_calls_requested_below_cumulative_ok(self):
        result = partition_callback_tail(row(
            sleep_calls=2, sleep_elapsed_ns=900_000, sleep_requested_ns=890_000,
            last_sleep_before_ns=1_200_000, last_sleep_after_ns=1_800_000,
            last_sleep_requested_ns=590_000))
        self.assertTrue(result["closure_exact"])
        with self.assertRaisesRegex(PartitionError, "requested exceeds"):
            partition_callback_tail(row(
                sleep_calls=2, sleep_elapsed_ns=900_000,
                sleep_requested_ns=500_000,
                last_sleep_before_ns=1_200_000, last_sleep_after_ns=1_800_000,
                last_sleep_requested_ns=590_000))

    def test_callback_before_initial_health_end_rejected(self):
        with self.assertRaisesRegex(PartitionError, "before initial health"):
            partition_callback_tail(row(
                sleep_calls=1, sleep_elapsed_ns=100_000,
                sleep_requested_ns=100_000,
                last_sleep_before_ns=1_000_000, last_sleep_after_ns=1_100_000,
                last_sleep_requested_ns=100_000))

    def test_overlapping_callbacks_rejected_not_unioned(self):
        with self.assertRaisesRegex(PartitionError, "overlap"):
            partition_callback_tail(row(
                sleep_calls=1, sleep_elapsed_ns=400_000,
                sleep_requested_ns=390_000,
                last_sleep_before_ns=1_500_000, last_sleep_after_ns=1_900_000,
                last_sleep_requested_ns=390_000,
                loop_health_calls=1, loop_health_ns=200_000,
                last_health_before_ns=1_700_000, last_health_after_ns=1_900_000))

    def test_sequential_callbacks_positive(self):
        result = partition_callback_tail(row(
            sleep_calls=1, sleep_elapsed_ns=200_000, sleep_requested_ns=190_000,
            last_sleep_before_ns=1_500_000, last_sleep_after_ns=1_700_000,
            last_sleep_requested_ns=190_000,
            loop_health_calls=1, loop_health_ns=100_000,
            last_health_before_ns=1_700_000, last_health_after_ns=1_800_000))
        self.assertEqual(result["callback_union_ns"], 300_000)
        self.assertEqual(result["tail_after_last_callback_ns"], 200_000)
        self.assertTrue(result["closure_exact"])

    def test_old_record_unavailable_and_unknown_outcome_rejected(self):
        old = row()
        for key in NEW_FIELDS:
            del old[key]
        self.assertEqual(partition_callback_tail(old)["status"], "unavailable")
        with self.assertRaisesRegex(PartitionError, "unknown outcome"):
            partition_callback_tail(row(outcome="error", **SLEEP1))

    def test_no_callbacks_empty_window_tail_none(self):
        result = partition_callback_tail(row(outcome="rate_unmet",
                                             terminal_ns=1_400_000))
        self.assertIsNone(result["tail_after_last_callback_ns"])
        self.assertEqual(result["window_ns"], 0)
        self.assertEqual(result["unattributed_ns"], 0)


if __name__ == "__main__":
    unittest.main()
