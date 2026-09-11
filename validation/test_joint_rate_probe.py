"""Opt-in JointRate timing probe and runtime-entry tests; no SITL/UE starts."""
import hashlib
import json
import os
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Simulator.wksim_runtime.joint_rate import JointRate, LATE_LIMIT_NS, RateUnmet
from Simulator.wksim_runtime.joint_rate_probe import (
    INSTRUMENTATION_OVERHEAD,
    TIMING_PROBE_ENV,
    TIMING_PROBE_PROFILE,
    JointRateTimingProbe,
    add_timing_probe_identity,
    timing_probe_enabled,
    timing_probe_identity,
)


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tools import run_joint_flight as runner
JOINT_RATE_SHA256 = "0b53a16acd65138b4623a9a8573ec8d643a2b78f4e27e8122c65efb9a6da25c4"


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


class JointRuntimeTimingProbeEntryTests(unittest.TestCase):
    def test_environment_is_strictly_three_state(self):
        self.assertFalse(timing_probe_enabled({}))
        self.assertFalse(timing_probe_enabled({TIMING_PROBE_ENV: "0"}))
        self.assertTrue(timing_probe_enabled({TIMING_PROBE_ENV: "1"}))
        for value in ("", "00", "01", "2", "true", " 1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, TIMING_PROBE_ENV):
                    timing_probe_enabled({TIMING_PROBE_ENV: value})

    def test_real_runner_uses_exact_default_or_probe_class(self):
        default_events = []
        enabled_events = []
        default = runner.make_joint_rate(
            "a" * 32, .5,
            lambda kind, **fields: default_events.append(dict(kind=kind, **fields)),
            diagnostic=False,
        )
        enabled = runner.make_joint_rate(
            "a" * 32, .5,
            lambda kind, **fields: enabled_events.append(dict(kind=kind, **fields)),
            diagnostic=True,
        )
        self.assertIs(type(default), JointRate)
        self.assertIs(type(enabled), JointRateTimingProbe)
        for rate in (default, enabled):
            rate.reanchor(4, "test")
            rate.begin_group(4, lambda: None)
            rate.end_group(8)
        self.assertNotIn("rate_timing_probe", [event["kind"] for event in default_events])
        for event in default_events:
            self.assertNotIn("rate_timing_probe", event)
        probe_event = next(event for event in enabled_events if event["kind"] == "rate_timing_probe")
        self.assertEqual(probe_event["rate_timing_probe"]["diagnostic"], TIMING_PROBE_PROFILE)

    def test_diagnostic_identity_is_nested_without_overwriting_rate_fields(self):
        identity = timing_probe_identity()
        self.assertEqual(identity["diagnostic"], TIMING_PROBE_PROFILE)
        self.assertFalse(identity["production_performance"])
        self.assertEqual(identity["instrumentation_overhead"], INSTRUMENTATION_OVERHEAD)
        bootstrap = dict(kind="rate_bootstrap", classification="untimed_until_first_synchronized_barrier")
        self.assertEqual(add_timing_probe_identity(bootstrap, None), bootstrap)
        marked = add_timing_probe_identity(bootstrap, identity)
        self.assertEqual(marked["classification"], bootstrap["classification"])
        self.assertEqual(marked["rate_timing_probe"], identity)

    def test_candidate_source_manifest_always_retains_runtime_probe_sources(self):
        sources = [
            "Simulator/wksim_runtime/joint_rate.py",
            "Simulator/wksim_runtime/joint_rate_probe.py",
        ]
        self.assertEqual(runner.candidate_rate_sources(False), sources)
        self.assertEqual(runner.candidate_rate_sources(True), sources)

    def test_real_runner_source_manifest_and_source_unchanged_follow_probe_state(self):
        probe = "Simulator/wksim_runtime/joint_rate_probe.py"
        args = SimpleNamespace(
            task_profile=runner.PV_PROFILE,
            pause_probe=False,
            scene_lifecycle=False,
            scene_lease_loss=False,
            dds_loss=False,
            native_state_trace=False,
            probe_land_freshness=False,
            ap_mixed_manifest=None,
            px4_manifest=None,
            repeat_paused_clock=False,
        )
        for value, enabled in (("0", False), ("1", True)):
            with self.subTest(value=value), runner.tempfile.TemporaryDirectory() as root:
                archive = Path(root) / "archive"
                live = Path(root) / "live"
                archive.mkdir()
                live.mkdir()
                with patch.dict(os.environ, {TIMING_PROBE_ENV: value}, clear=False), \
                        patch.object(runner, "check_isolation"), \
                        patch.object(runner.signal, "signal"), \
                        patch.object(runner.os, "readlink",
                                     side_effect=lambda path: "private" if "/proc/self/" in path else "init"), \
                        patch.object(runner.tempfile, "mkdtemp",
                                     side_effect=[str(archive), str(live)]), \
                        patch.object(runner, "isolate_temporary_files",
                                     side_effect=RuntimeError("stop before flight")):
                    self.assertEqual(runner.run(args), 1)
                evidence = json.loads((archive / "result.json").read_text())
                self.assertTrue(evidence["source_unchanged"])
                expected = hashlib.sha256((ROOT / probe).read_bytes()).hexdigest()
                self.assertEqual(evidence["source_sha256"][probe], expected)
                if enabled:
                    self.assertIn("rate_timing_probe", evidence)
                else:
                    self.assertNotIn("rate_timing_probe", evidence)

    def test_enabled_probe_rejects_non_candidate_before_runtime_side_effects(self):
        args = SimpleNamespace(task_profile="position")
        with patch.dict(os.environ, {TIMING_PROBE_ENV: "1"}, clear=False), \
                patch.object(runner, "check_isolation") as isolate, \
                patch.object(runner.signal, "signal") as install_signal, \
                patch.object(runner.os, "readlink",
                             side_effect=lambda path: "private" if "/proc/self/" in path else "init") as readlink, \
                patch.object(runner.tempfile, "mkdtemp") as mkdtemp, \
                patch.object(runner.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, TIMING_PROBE_ENV):
                runner.run(args)
        isolate.assert_not_called()
        install_signal.assert_not_called()
        readlink.assert_not_called()
        mkdtemp.assert_not_called()
        spawn.assert_not_called()
        for value in ("0",):
            with patch.dict(os.environ, {TIMING_PROBE_ENV: value}, clear=False), \
                    patch.object(runner, "check_isolation",
                                 side_effect=RuntimeError("reached legacy entry")) as isolate:
                with self.assertRaisesRegex(RuntimeError, "reached legacy entry"):
                    runner.run(args)
            isolate.assert_called_once()
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(runner, "check_isolation",
                             side_effect=RuntimeError("reached legacy entry")) as isolate:
            with self.assertRaisesRegex(RuntimeError, "reached legacy entry"):
                runner.run(args)
        isolate.assert_called_once()

    def test_invalid_environment_fails_before_isolation_tempfile_or_children(self):
        for value in ("2", "true", "01"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {TIMING_PROBE_ENV: value}, clear=False), \
                        patch.object(runner, "check_isolation") as isolate, \
                        patch.object(runner.tempfile, "mkdtemp") as mkdtemp, \
                        patch.object(runner.subprocess, "Popen") as spawn:
                    with self.assertRaisesRegex(ValueError, TIMING_PROBE_ENV):
                        runner.run(object())
                isolate.assert_not_called()
                mkdtemp.assert_not_called()
                spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
