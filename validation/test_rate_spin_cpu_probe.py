"""Behavior tests for tools/rate_spin_cpu_probe.py (real parents, fake clocks).

No native/ROS/build.  JointRate/JointRateTimingProbe execute for real; only
the wall clock, thread clock, sleep, and health are controllable fakes.

Run from the worktree root:
    python3 -B -m unittest validation.test_rate_spin_cpu_probe
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from Simulator.wksim_runtime.joint_rate import JointRate, RateUnmet  # noqa: E402
from Simulator.wksim_runtime.joint_rate_probe import (  # noqa: E402
    JointRateTimingProbe,
)
from tools.rate_spin_cpu_probe import (  # noqa: E402
    BIG_GAP_NS,
    SPIN_WINDOW_NS,
    JointRateSpinCpuProbe,
)

EPOCH = "e" * 32
PERIOD_NS = 8_000_000


class FakeWall:
    """Monotonic wall: per-read step; set() places it without reading."""

    def __init__(self, start=1_000_000_000, read_step_ns=1000):
        self.t = start
        self.read_step_ns = read_step_ns
        self.reads = 0

    def __call__(self):
        self.reads += 1
        self.t += self.read_step_ns
        return self.t

    def set(self, value):
        self.t = value


class FakeCpu:
    def __init__(self, start=0, read_step_ns=1000, fault_at=None,
                 fault=RuntimeError("cpu"), wall=None, fault_wall_ns=None):
        self.c = start
        self.read_step_ns = read_step_ns
        self.reads = 0
        self.fault_at = fault_at
        self.fault = fault
        self.wall = wall
        self.fault_wall_ns = fault_wall_ns
        self._fired = False

    def __call__(self):
        self.reads += 1
        if self.fault_at is not None and self.reads == self.fault_at:
            raise self.fault
        if (self.fault_wall_ns is not None and not self._fired
                and self.wall.t >= self.fault_wall_ns):
            self._fired = True
            raise self.fault
        self.c += self.read_step_ns
        return self.c


def fake_sleep_factory(wall, overshoot_ns=0):
    def fake_sleep(seconds):
        wall.t += round(seconds * 1e9) + overshoot_ns
    return fake_sleep


def fake_health_factory(wall, cost_ns=0):
    def health():
        wall.t += cost_ns
    return health


def make_record_sink(records):
    def sink(kind, **fields):
        records.append(dict(fields, kind=kind))
    return sink


def make_probe(cls, wall, cpu=None, sleep=None):
    records = []
    probe = cls(EPOCH, 0.5, make_record_sink(records), now=wall,
                sleep=sleep or fake_sleep_factory(wall),
                **({"thread_now": cpu, "after_now": lambda: wall.t}
                   if cpu is not None else {}))
    return probe, records


def anchor_and_place(probe, wall, *, remaining_ns, tick=44):
    """Drive one quick first group, then place wall so the OBSERVED second
    group begins with remaining_ns left.  The first group's earliest edge is
    always in the past by construction, so observations target the second."""
    probe.reanchor(40, "synchronized_boundary")
    probe.begin_group(40, fake_health_factory(wall))
    probe.end_group(44)
    # earliest = max(ideal, previous_start+period): use the parent's own edge
    # computation (previous group lateness pushes the next earliest forward).
    earliest = probe._planned_edges()[1]
    assert probe.completed == 1 and tick == 44, (probe.completed, tick)
    wall.set(earliest - remaining_ns)
    return earliest


def begin_records(records, kind):
    return [r for r in records if r.get("kind") == kind]


def spin_records(records):
    return begin_records(records, "rate_spin_cpu_probe")


class CoreContractTests(unittest.TestCase):
    def test_core_events_identical_to_parent_plus_my_record(self):
        def run(cls):
            wall = FakeWall(read_step_ns=2000)
            records = []
            probe = cls(EPOCH, 0.5, make_record_sink(records), now=wall,
                        sleep=fake_sleep_factory(wall),
                        **({"thread_now": FakeCpu(read_step_ns=2000),
                            "after_now": lambda: wall.t}
                           if cls is JointRateSpinCpuProbe else {}))
            anchor_and_place(probe, wall, remaining_ns=1_100_000)
            probe.begin_group(44, fake_health_factory(wall))
            return records

        parent_records = run(JointRateTimingProbe)
        mine_records = run(JointRateSpinCpuProbe)
        parent_kinds = [r["kind"] for r in parent_records]
        mine_kinds = [r["kind"] for r in mine_records]
        # Shared core records are identical and in the same order (my record
        # kind filtered out of the interleaving).
        mine_shared = [k for k in mine_kinds if k != "rate_spin_cpu_probe"]
        self.assertEqual(mine_shared, parent_kinds)
        for kind in ("rate_group_start", "rate_timing_probe"):
            self.assertEqual(begin_records(parent_records, kind),
                             begin_records(mine_records, kind))
        mine_probe_idx = mine_kinds.index("rate_timing_probe")
        self.assertEqual(mine_kinds[mine_probe_idx + 1], "rate_spin_cpu_probe")

    def test_spin_window_constants(self):
        self.assertEqual(SPIN_WINDOW_NS, 1_000_000)
        self.assertEqual(BIG_GAP_NS, 10_000)


class SpinObservationTests(unittest.TestCase):
    def test_known_off_cpu_pairs_are_big_gaps_with_same_pair_records(self):
        wall = FakeWall(read_step_ns=50_000)
        cpu = FakeCpu(read_step_ns=1000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertGreater(record["pairs_observed"], 0)
        self.assertEqual(record["pairs_valid"], record["pairs_observed"])
        self.assertEqual(record["big_gap_count"], record["pairs_observed"])
        gap = record["max_gap"]
        self.assertEqual(gap["gap_wall_ns"], 50_000)
        self.assertEqual(gap["gap_cpu_ns"], 1000)
        self.assertLess(gap["prev_wall_ns"], gap["wall_ns"])
        self.assertLess(gap["prev_cpu_ns"], gap["cpu_ns"])
        self.assertEqual(record["cpu_errors"], 0)
        self.assertFalse(record["cpu_disabled"])

    def test_cpu_busy_pairs_are_not_big_gaps(self):
        wall = FakeWall(read_step_ns=5000)
        cpu = FakeCpu(read_step_ns=5000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertEqual(record["big_gap_count"], 0)
        # max_gap now covers ALL valid pairs (big gaps are a separate count):
        # here the max is the small busy pair itself.
        self.assertIsNotNone(record["max_gap"])
        self.assertEqual(record["max_gap"]["gap_wall_ns"], 5000)
        self.assertEqual(record["max_gap"]["gap_cpu_ns"], 5000)
        self.assertGreater(record["pairs_valid"], 0)

    def test_crossing_pair_into_window_is_kept_and_marked(self):
        # Coarse 600us reads: the first in-window pair opens before the window.
        wall = FakeWall(read_step_ns=600_000)
        cpu = FakeCpu(read_step_ns=1000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        # Entry lands 1.5ms before the edge (below the 1ms window); the parent
        # before-health read lands 0.9ms before it (inside, no health time in
        # the pair): that adjacent pair crosses into the window.
        anchor_and_place(probe, wall, remaining_ns=2_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertGreaterEqual(record["pairs_observed"], 1)
        self.assertIsNotNone(record["max_gap"])
        self.assertTrue(record["max_gap"]["crossing"])

    def test_health_boundary_pair_excluded_and_previous_cleared(self):
        # remaining 3.5M: read (3.498M>1M) -> sleep 2M -> read is due for loop
        # health (now >= entry+2M) with remaining >1M: health fires with a 500us
        # cost, then remaining <=1M and the final spin begins.  The pair that
        # would span the health call must never form.
        wall = FakeWall(read_step_ns=2000)
        cpu = FakeCpu(read_step_ns=2000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=3_500_000)
        probe.begin_group(44, fake_health_factory(wall, 500_000))
        record = spin_records(records)[-1]
        self.assertGreaterEqual(record["excluded_boundary_crossings"], 1)
        if record["max_gap"] is not None:
            self.assertNotEqual(record["max_gap"]["gap_wall_ns"], 500_000)
        # The post-health spin pairs still exist and are clean.
        self.assertGreaterEqual(record["pairs_valid"], 1)

    def test_sleep_boundary_pair_excluded(self):
        wall = FakeWall(read_step_ns=2000)
        cpu = FakeCpu(read_step_ns=2000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=3_000_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertGreaterEqual(record["excluded_boundary_crossings"], 1)
        if record["max_gap"] is not None:
            self.assertLess(record["max_gap"]["gap_wall_ns"], 2_000_000)

    def test_negative_cpu_pairs_invalid_never_valid(self):
        wall = FakeWall(read_step_ns=50_000)
        cpu = FakeCpu(read_step_ns=-2000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertGreater(record["pairs_observed"], 0)
        self.assertEqual(record["pairs_valid"], 0)
        self.assertEqual(record["pairs_invalid_cpu"], record["pairs_observed"])
        self.assertIsNone(record["max_gap"])


class FailureSemanticsTests(unittest.TestCase):
    def test_parent_rate_unmet_propagates_and_records_order(self):
        wall = FakeWall(read_step_ns=1000)
        cpu = FakeCpu()
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        probe.reanchor(40, "synchronized_boundary")
        wall.set(probe.anchor["wall_ns"] + 200_000_000)
        with self.assertRaises(RateUnmet):
            probe.begin_group(40, fake_health_factory(wall))

        kinds = [r["kind"] for r in records]
        self.assertEqual(kinds[-2:], ["rate_timing_probe", "rate_spin_cpu_probe"])
        self.assertEqual(records[-1]["outcome"], "rate_unmet")

    def test_cancellation_propagates_and_is_not_listed(self):
        wall = FakeWall(read_step_ns=50_000)
        cpu = FakeCpu(fault_at=6, fault=KeyboardInterrupt())
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        with self.assertRaises(KeyboardInterrupt):
            probe.begin_group(44, fake_health_factory(wall))
        kinds = [r["kind"] for r in records]
        self.assertIn("rate_timing_probe", kinds)
        self.assertIn("rate_spin_cpu_probe", kinds)
        self.assertEqual(records[-1]["cpu_errors"], 0)

    def test_cpu_sampling_exception_listed_and_disabled_not_masking(self):
        wall = FakeWall(read_step_ns=50_000)
        cpu = FakeCpu(fault=RuntimeError("cpu-read"), wall=wall)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        earliest = anchor_and_place(probe, wall, remaining_ns=1_100_000)
        # Fault as soon as the second group's window starts being sampled.
        cpu.fault_wall_ns = earliest - 900_000
        probe.begin_group(44, fake_health_factory(wall))  # completes; no mask
        records_by_group = spin_records(records)
        self.assertEqual(len(records_by_group), 2)
        clean = records_by_group[0]
        self.assertEqual(clean["cpu_errors"], 0)
        faulted = records_by_group[1]
        self.assertEqual(faulted["cpu_errors"], 1)
        self.assertTrue(faulted["cpu_disabled"])
        self.assertEqual(faulted["outcome"], "started")
        # Pairs observed after the fault are wall-only: never "valid".  A
        # pre-fault pair may legitimately be valid, so assert the accounting
        # identity and that post-fault invalid pairs exist.
        self.assertGreater(faulted["pairs_invalid_cpu"], 0)
        self.assertEqual(faulted["pairs_valid"] + faulted["pairs_invalid_cpu"],
                         faulted["pairs_observed"])

    def test_bounded_state_no_per_group_lists(self):
        wall = FakeWall(read_step_ns=50_000)
        cpu = FakeCpu(read_step_ns=1000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        for tick in (44, 48, 52):
            probe.begin_group(tick, fake_health_factory(wall))
            probe.end_group(tick + 4)
        self.assertIsNone(probe._spin)
        self.assertEqual(len(probe._spin_record_errors), 0)
        self.assertEqual(probe._spin_record_error_total, 0)
        # Parent timings list is the parent's own contract; my probe adds none.
        self.assertEqual(len(spin_records(records)), 4)  # 1 throwaway + 3 observed


class ReleaseCrossingTests(unittest.TestCase):
    """The pair crossing the release deadline is kept, marked, and final."""

    def test_release_crossing_pair_kept_with_lateness_and_stops(self):
        wall = FakeWall(read_step_ns=600_000)
        cpu = FakeCpu(read_step_ns=1000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        earliest = anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertEqual(record["pairs_observed"], 1)
        self.assertTrue(record["release_crossed"])
        crossing = record["release_crossing"]
        self.assertEqual(crossing["lateness_ns"], 100_000)
        self.assertEqual(crossing["wall_ns"], earliest + 100_000)
        self.assertLess(crossing["prev_wall_ns"], earliest)
        self.assertEqual(crossing["gap_wall_ns"], 600_000)
        self.assertEqual(crossing["gap_cpu_ns"], 1000)
        self.assertEqual(record["release_lateness_ns"], 100_000)

    def test_first_read_past_edge_forms_no_pair(self):
        wall = FakeWall(read_step_ns=50_000)
        cpu = FakeCpu(read_step_ns=1000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=10_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        # Everything started at/past the edge: no comparable previous point.
        self.assertEqual(record["pairs_observed"], 0)
        self.assertFalse(record["release_crossed"])
        self.assertIsNone(record["release_crossing"])


class CpuKindTests(unittest.TestCase):
    """CPU values must be plain non-negative ints; anything else disables
    this group's CPU sampling and is listed, never breaking the parent."""

    def run_with_thread(self, thread_now):
        wall = FakeWall(read_step_ns=50_000)
        records = []
        probe = JointRateSpinCpuProbe(
            EPOCH, 0.5, make_record_sink(records), now=wall,
            sleep=fake_sleep_factory(wall), thread_now=thread_now)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        return spin_records(records)[-1]

    def test_invalid_cpu_kinds_listed_and_disabled(self):
        for bad in (True, "cpu", 1.5, -1):
            record = self.run_with_thread(lambda value=bad: value)
            self.assertEqual(record["cpu_errors"], 1, bad)
            self.assertTrue(record["cpu_disabled"], bad)
            self.assertEqual(record["pairs_valid"], 0, bad)
            self.assertEqual(record["outcome"], "started", bad)

    def test_cpu_regression_listed_and_disabled(self):
        wall = FakeWall(read_step_ns=50_000)
        cpu = FakeCpu(read_step_ns=-2000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertGreaterEqual(record["cpu_errors"], 1)
        self.assertTrue(record["cpu_disabled"])
        self.assertEqual(record["pairs_valid"], 0)


class CancellationContractTests(unittest.TestCase):
    """Record-time cancellation: business exception wins; success lets it fly."""

    @staticmethod
    def cancel_sink(records, cancel_kind, on_nth=1):
        state = {"n": 0}

        def sink(kind, **fields):
            records.append(dict(fields, kind=kind))
            if kind == "rate_spin_cpu_probe":
                state["n"] += 1
                if state["n"] == on_nth:
                    raise cancel_kind()
        return sink

    def test_recorder_cancel_with_business_exception_keeps_original(self):
        for cancel in (KeyboardInterrupt, SystemExit, InterruptedError):
            wall = FakeWall(read_step_ns=1000)
            records = []
            probe = JointRateSpinCpuProbe(
                EPOCH, 0.5, self.cancel_sink(records, cancel), now=wall,
                sleep=fake_sleep_factory(wall),
                thread_now=FakeCpu(read_step_ns=1000))
            probe.reanchor(40, "synchronized_boundary")
            wall.set(probe.anchor["wall_ns"] + 200_000_000)
            with self.assertRaises(RateUnmet) as caught:
                probe.begin_group(40, fake_health_factory(wall))
            self.assertIs(caught.exception.__class__, RateUnmet)
            self.assertEqual(probe._spin_record_error_total, 1, cancel)
            self.assertEqual(len(probe._spin_record_errors), 1, cancel)

    def test_recorder_cancel_on_success_propagates(self):
        wall = FakeWall(read_step_ns=50_000)
        records = []
        probe = JointRateSpinCpuProbe(
            EPOCH, 0.5, self.cancel_sink(records, KeyboardInterrupt, on_nth=2), now=wall,
            sleep=fake_sleep_factory(wall),
            thread_now=FakeCpu(read_step_ns=1000))
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        with self.assertRaises(KeyboardInterrupt):
            probe.begin_group(44, fake_health_factory(wall))


class MeasurementBiasTests(unittest.TestCase):
    """The CPU read's own duration must be visible in the v2 bounds, never
    hidden: a naive wall/CPU ratio would misattribute it."""

    def test_cpu_read_duration_bias_visible_in_bounds(self):
        # Wall steps 10us per pacing read; the thread-CPU read itself costs
        # 40us of wall (slow read), CPU advances only 10us per read.  The
        # naive wall/CPU ratio (5x) would scream off-CPU; the v2 bounds show
        # the read window dominates the gap instead.
        wall = FakeWall(read_step_ns=10_000)

        def slow_cpu():
            wall.t += 40_000  # the CPU read itself costs 40us of wall
            slow_cpu.c += 10_000
            return slow_cpu.c
        slow_cpu.c = 0

        records = []
        probe = JointRateSpinCpuProbe(
            EPOCH, 0.5, make_record_sink(records), now=wall,
            sleep=fake_sleep_factory(wall), thread_now=slow_cpu,
            after_now=lambda: wall.t)
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        gap = record["max_gap"]
        self.assertEqual(gap["gap_wall_ns"], 50_000)     # raw: 10 + 40 read cost
        self.assertEqual(gap["gap_cpu_ns"], 10_000)
        self.assertEqual(gap["cpu_read_window_ns"], 40_000)
        # Bounds: the gap minus the read's own window brackets the true span.
        self.assertEqual(gap["wall_gap_lower_ns"], 10_000)
        self.assertEqual(gap["wall_gap_upper_ns"], 90_000)
        # Naive ratio would claim 5x off-CPU; the bounds and the 40us read
        # window make the bias visible instead of attributing it.
        self.assertGreater(record["pairs_valid"], 0)

    def test_after_clock_invalid_or_regressing_disables_group(self):
        for after in (lambda: -1, lambda: 0.5):
            wall = FakeWall(read_step_ns=50_000)
            records = []
            probe = JointRateSpinCpuProbe(
                EPOCH, 0.5, make_record_sink(records), now=wall,
                sleep=fake_sleep_factory(wall),
                thread_now=FakeCpu(read_step_ns=1000), after_now=after)
            anchor_and_place(probe, wall, remaining_ns=1_100_000)
            probe.begin_group(44, fake_health_factory(wall))
            record = spin_records(records)[-1]
            self.assertEqual(record["cpu_errors"], 1, after)
            self.assertTrue(record["cpu_disabled"], after)

    def test_after_clock_regression_disables_group(self):
        wall = FakeWall(read_step_ns=50_000)
        descending = iter([10_000_000, 5_000_000])
        records = []
        probe = JointRateSpinCpuProbe(
            EPOCH, 0.5, make_record_sink(records), now=wall,
            sleep=fake_sleep_factory(wall),
            thread_now=FakeCpu(read_step_ns=1000),
            after_now=lambda: next(descending, 5_000_000))
        anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        record = spin_records(records)[-1]
        self.assertEqual(record["cpu_errors"], 1)
        self.assertTrue(record["cpu_disabled"])

    def test_release_crossing_record_carries_windows_and_bounds(self):
        wall = FakeWall(read_step_ns=600_000)
        cpu = FakeCpu(read_step_ns=1000)
        probe, records = make_probe(JointRateSpinCpuProbe, wall, cpu)
        earliest = anchor_and_place(probe, wall, remaining_ns=1_100_000)
        probe.begin_group(44, fake_health_factory(wall))
        crossing = spin_records(records)[-1]["release_crossing"]
        self.assertEqual(crossing["lateness_ns"], 100_000)
        self.assertEqual(crossing["wall_gap_lower_ns"], 600_000)
        self.assertEqual(crossing["wall_gap_upper_ns"], 600_000)
        self.assertIn("prev_cpu_read_window_ns", crossing)
        self.assertIn("cpu_read_window_ns", crossing)


if __name__ == "__main__":
    unittest.main()
