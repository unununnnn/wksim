"""Opt-in JointRate timing probe tests; no SITL or production-path changes."""
import hashlib
import unittest
from pathlib import Path

from Simulator.wksim_runtime.joint_rate import JointRate, LATE_LIMIT_NS, RateUnmet
from Simulator.wksim_runtime.joint_rate_probe import JointRateTimingProbe


ROOT = Path(__file__).resolve().parents[1]
JOINT_RATE_SHA256 = "59e329db948802e545fa5167b2430ae18bf3bdb6e1c534a374a82dafcc70da6c"


class FakeClock:
    def __init__(self, overshoot_ns=0, now_step_ns=0):
        self.ns = 1_000_000_000
        self.overshoot_ns = overshoot_ns
        self.now_step_ns = now_step_ns
        self.sleep_requests = []
        self.now_calls = 0

    def now(self):
        self.now_calls += 1
        value = self.ns
        self.ns += self.now_step_ns
        return value

    def sleep(self, seconds):
        requested_ns = round(seconds * 1e9)
        self.sleep_requests.append(requested_ns)
        self.ns += requested_ns + self.overshoot_ns


class JointRateProbeTests(unittest.TestCase):
    def make_probe(self, clock, rate=.5):
        events = []
        probe = JointRateTimingProbe(
            "a" * 32,
            rate,
            lambda kind, **fields: events.append(dict(kind=kind, **fields)),
            now=clock.now,
            sleep=clock.sleep,
        )
        probe.events = events
        probe.reanchor(4, "test")
        return probe

    @staticmethod
    def run_group(probe, clock, tick, health_ns, work_ns):
        def health():
            clock.ns += health_ns

        probe.begin_group(tick, health)
        clock.ns += work_ns
        probe.end_group(tick + 4)

    def test_fast_and_slow_health_report_closed_phases(self):
        fast_clock = FakeClock(overshoot_ns=50_000, now_step_ns=1_000)
        fast = self.make_probe(fast_clock)
        self.run_group(fast, fast_clock, 4, health_ns=100, work_ns=1_000_000)
        self.run_group(fast, fast_clock, 8, health_ns=100, work_ns=1_000_000)
        fast_sample = fast.timings[-1]

        slow_clock = FakeClock(overshoot_ns=50_000, now_step_ns=1_000)
        slow = self.make_probe(slow_clock)
        self.run_group(slow, slow_clock, 4, health_ns=500_000, work_ns=1_000_000)
        self.run_group(slow, slow_clock, 8, health_ns=500_000, work_ns=1_000_000)
        slow_sample = slow.timings[-1]

        self.assertGreaterEqual(fast_sample.loop_health_calls, 2)
        self.assertGreaterEqual(slow_sample.loop_health_calls, 2)
        self.assertGreater(slow_sample.entry_to_initial_health_ns, fast_sample.entry_to_initial_health_ns)
        for sample in (fast_sample, slow_sample):
            self.assertEqual(sample.outcome, "started")
            self.assertGreaterEqual(sample.entry_to_initial_health_ns, 0)
            self.assertGreaterEqual(sample.loop_health_ns, 0)
            self.assertGreaterEqual(sample.sleep_requested_ns, 0)
            self.assertGreaterEqual(sample.sleep_elapsed_ns, 0)
            self.assertGreaterEqual(sample.sleep_max_overshoot_ns, 0)
            self.assertGreaterEqual(sample.final_spin_other_ns, 0)
            self.assertGreaterEqual(sample.release_excess_ns, 0)
            self.assertEqual(sample.phase_total_ns, sample.observed_elapsed_ns)
            self.assertEqual(
                sample.phase_total_ns,
                sample.entry_to_initial_health_ns
                + sample.loop_health_ns
                + sample.sleep_elapsed_ns
                + sample.final_spin_other_ns,
            )
            self.assertGreater(sample.loop_health_calls, 0)
            self.assertGreater(sample.sleep_calls, 1)
            self.assertGreater(sample.sleep_requested_ns, 0)
            self.assertGreaterEqual(sample.sleep_elapsed_ns, sample.sleep_requested_ns)
            self.assertGreaterEqual(sample.sleep_max_overshoot_ns, 50_000)

    def test_work_over_is_reported_without_catch_up(self):
        clock = FakeClock()
        probe = self.make_probe(clock)
        self.run_group(probe, clock, 4, health_ns=0, work_ns=10_000_000)
        self.run_group(probe, clock, 8, health_ns=0, work_ns=1_000_000)

        starts = [event for event in probe.events if event["kind"] == "rate_group_start"]
        sample = probe.timings[-1]
        self.assertGreaterEqual(starts[1]["actual_start_ns"] - starts[0]["actual_start_ns"], 8_000_000)
        self.assertGreater(sample.release_excess_ns, 0)
        self.assertEqual(sample.sleep_calls, 0)

    def test_rate_unmet_is_recorded_and_rethrown(self):
        clock = FakeClock()
        probe = self.make_probe(clock, rate=1)

        def too_slow_health():
            clock.ns += LATE_LIMIT_NS + 1

        with self.assertRaises(RateUnmet):
            probe.begin_group(4, too_slow_health)

        sample = probe.timings[-1]
        self.assertEqual(sample.outcome, "rate_unmet")
        self.assertGreater(sample.entry_to_initial_health_ns, LATE_LIMIT_NS)
        self.assertEqual(sample.phase_total_ns, sample.observed_elapsed_ns)
        self.assertTrue(probe.latched)
        self.assertIsNone(probe.group)

    def test_default_joint_rate_identity_and_behavior_remain_uninstrumented(self):
        source = ROOT / "Simulator" / "wksim_runtime" / "joint_rate.py"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), JOINT_RATE_SHA256)

        clock = FakeClock()
        events = []
        rate = JointRate(
            "a" * 32,
            .5,
            lambda kind, **fields: events.append(dict(kind=kind, **fields)),
            now=clock.now,
            sleep=clock.sleep,
        )
        rate.reanchor(4, "test")
        rate.begin_group(4, lambda: None)
        clock.ns += 1_000_000
        rate.end_group(8)

        start = next(event for event in events if event["kind"] == "rate_group_start")
        self.assertNotIn("timing_probe", start)
        self.assertNotIn("rate_timing_probe", [event["kind"] for event in events])
        self.assertEqual(rate.completed, 1)
        self.assertEqual(start["actual_start_ns"], start["ideal_start_ns"])
        self.assertEqual(start["earliest_start_ns"], start["ideal_start_ns"])


if __name__ == "__main__":
    unittest.main()
