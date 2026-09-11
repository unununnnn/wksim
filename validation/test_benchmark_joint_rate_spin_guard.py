"""Deterministic tests for the diagnostic-only spin-guard benchmark."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.benchmark_joint_rate_spin_guard import (
    GUARD_CANDIDATES_NS,
    PERIOD_NS,
    main,
    measure_guard,
    run_benchmark,
    summarize,
    write_result,
)


class FakeClock:
    def __init__(self, sleep_overshoot_ns=0, spin_step_ns=100_000):
        self.ns = 1_000_000_000
        self.sleep_overshoot_ns = sleep_overshoot_ns
        self.spin_step_ns = spin_step_ns
        self.sleep_requests = []
        self.now_calls = 0
        self.sleep_calls = 0
        self.after_sleep = False

    def now(self):
        self.now_calls += 1
        value = self.ns
        if self.after_sleep:
            self.ns += self.spin_step_ns
        return value

    def sleep(self, seconds):
        self.sleep_calls += 1
        requested_ns = round(seconds * 1e9)
        self.sleep_requests.append(requested_ns)
        self.ns += requested_ns + self.sleep_overshoot_ns
        self.after_sleep = True


class SpinGuardBenchmarkTests(unittest.TestCase):
    def test_measurement_sleeps_once_and_spins_to_first_target_read(self):
        clock = FakeClock(sleep_overshoot_ns=50_000)
        result = measure_guard(1_000_000, 1, clock.now, clock.sleep)

        self.assertEqual(clock.sleep_calls, 1)
        self.assertEqual(clock.sleep_requests, [7_000_000])
        self.assertEqual(result['overshoot_ns'], [50_000])
        self.assertEqual(result['spin_elapsed_ns'], [1_000_000])
        self.assertEqual(result['summary']['overshoot_ns']['count'], 1)

    def test_each_guard_candidate_has_exact_fake_clock_measurements(self):
        for guard_ns in GUARD_CANDIDATES_NS:
            with self.subTest(guard_ns=guard_ns):
                clock = FakeClock(sleep_overshoot_ns=50_000)
                result = measure_guard(guard_ns, 1, clock.now, clock.sleep)
                self.assertEqual(result['guard_ns'], guard_ns)
                self.assertEqual(result['overshoot_ns'], [50_000])
                self.assertEqual(result['spin_elapsed_ns'], [guard_ns])

    def test_multiple_samples_set_a_fresh_target_and_retain_each_result(self):
        clock = FakeClock()
        result = measure_guard(1_000_000, 2, clock.now, clock.sleep)

        self.assertEqual(clock.sleep_calls, 2)
        self.assertEqual(clock.sleep_requests, [7_000_000, 6_900_000])
        self.assertEqual(result['overshoot_ns'], [0, 0])
        self.assertEqual(result['spin_elapsed_ns'], [1_000_000, 900_000])

    def test_summary_reports_percentiles_and_strict_thresholds(self):
        result = summarize([0, 10_000, 20_000, 100_000, 600_000])

        self.assertEqual(result, {
            'count': 5,
            'total_ns': 730_000,
            'mean_ns': 146_000.0,
            'median_ns': 20_000,
            'p95_ns': 600_000,
            'p99_ns': 600_000,
            'max_ns': 600_000,
            'count_gt_10us': 3,
            'count_gt_100us': 1,
            'count_gt_500us': 1,
        })

    def test_result_schema_records_diagnostic_metadata_and_candidates(self):
        clock = FakeClock()
        timestamps = iter(('2026-09-11T00:00:00+00:00', '2026-09-11T00:00:01+00:00'))
        result = run_benchmark(
            1,
            now=clock.now,
            sleep=clock.sleep,
            utc_now=lambda: next(timestamps),
            environment={'python': 'fake-python', 'platform': 'fake-platform', 'wsl_distro_name': 'Ubuntu'},
            scheduler={'policy': 'SCHED_OTHER', 'policy_value': 0, 'priority': 0, 'nice': 0},
        )

        self.assertEqual(result['schema'], 'wksim.joint_rate_spin_guard.v1')
        self.assertTrue(result['diagnostic_only'])
        self.assertFalse(result['production_performance'])
        self.assertFalse(result['flight_claim'])
        self.assertEqual(result['period_ns'], PERIOD_NS)
        self.assertEqual(result['candidates_ns'], list(GUARD_CANDIDATES_NS))
        self.assertEqual(result['sample_count'], 1)
        self.assertEqual(result['percentile_method'], 'nearest_rank')
        self.assertEqual(result['started_utc'], '2026-09-11T00:00:00+00:00')
        self.assertEqual(result['finished_utc'], '2026-09-11T00:00:01+00:00')
        self.assertEqual(result['environment']['wsl_distro_name'], 'Ubuntu')
        self.assertEqual(result['scheduler']['nice'], 0)
        self.assertEqual(len(result['candidates']), 3)
        for candidate in result['candidates']:
            self.assertEqual(len(candidate['overshoot_ns']), 1)
            self.assertEqual(len(candidate['spin_elapsed_ns']), 1)
            self.assertEqual(set(candidate['summary']), {'overshoot_ns', 'spin_elapsed_ns'})
        self.assertEqual(list(result)[:7], [
            'schema', 'scope', 'diagnostic_only', 'production_performance',
            'flight_claim', 'period_ns', 'candidates_ns',
        ])

    def test_invalid_measurement_inputs_are_rejected(self):
        clock = FakeClock()
        for guard_ns, samples in ((0, 1), (-1, 1), (1_000_000, 0), (1_000_000, -1)):
            with self.subTest(guard_ns=guard_ns, samples=samples):
                with self.assertRaises(ValueError):
                    measure_guard(guard_ns, samples, clock.now, clock.sleep)
        with self.assertRaises(ValueError):
            measure_guard(1.0, 1, clock.now, clock.sleep)
        with self.assertRaises(ValueError):
            summarize([])

    def test_cli_requires_positive_samples_and_output(self):
        with self.assertRaises(SystemExit):
            main([])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'benchmark.json'
            with self.assertRaises(SystemExit):
                main(['--samples', '0', '--output', str(output)])

    def test_output_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'benchmark.json'
            output.write_text('sentinel', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                write_result(output, {'schema': 'test'})
            with patch(
                'tools.benchmark_joint_rate_spin_guard.run_benchmark',
                side_effect=AssertionError('existing output must be rejected first'),
            ):
                with self.assertRaises(FileExistsError):
                    main(['--samples', '1', '--output', str(output)])
            self.assertEqual(output.read_text(encoding='utf-8'), 'sentinel')


if __name__ == '__main__':
    unittest.main()
