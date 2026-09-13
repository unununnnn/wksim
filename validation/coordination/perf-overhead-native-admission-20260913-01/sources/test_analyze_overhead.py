#!/usr/bin/env python3
"""Concise pure-Python tests for analyze_overhead.py.

Every fixture is synthetic and built here: no compilation, no perf event, no WSL, no
simulator, no flight. The fixtures obey the benchmark's arithmetic
(ideal[k] = start + k*period, actual[k] - actual[k-1] >= period, end >= actual) so the
analyzer's checks are exercised on inputs shaped like real benchmark output.

    python -B test_analyze_overhead.py
Exit: 0 when every case matches its expectation.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PERIOD, DURATION, ITERATIONS, START = 1_000_000, 5_000_000, 5, 7_000_000_000
BODY_CHECKSUM = 0x1234567890ABCDEF


def load_analyzer():
    spec = importlib.util.spec_from_file_location(
        'analyze_overhead', os.path.join(HERE, 'analyze_overhead.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load_analyzer()


def timing_rows(slip=1000, work=2000, start=START, period=PERIOD, count=ITERATIONS):
    """Rows in the benchmark's own shape: ideal[k] = start + k*period,
    earliest[k] = max(ideal[k], previous_actual + period), actual = earliest + slip."""
    rows, previous = [], start - period
    for k in range(count):
        ideal = start + k * period
        earliest = max(ideal, previous + period)
        actual = earliest + slip
        rows.append((k, ideal, earliest, actual, actual + work))
        previous = actual
    return rows


def result(mode, rows, duration=DURATION, period=PERIOD, **overrides):
    payload = {
        'tool': 'wksim_perf_overhead_bench', 'version': 2, 'mode': mode,
        'classification': 'diagnostic_only', 'full_acceptance': False,
        'requested_duration_ns': duration, 'requested_period_ns': period,
        'iterations': len(rows), 'timing_rows': len(rows),
        'cpu': {'owner_thread': {'cpu_ns': 100_000}, 'process': {'cpu_ns': 300_000}},
        'measurement': {'loop_span_ns': rows[-1][3] - rows[0][1],
                        'body_checksum': BODY_CHECKSUM,
                        'recorder_start_span_ns': 12_000, 'recorder_stop_span_ns': 900_000},
        'recorder': {'enabled': mode == 'enabled', 'start_rc': 0, 'stop_rc': 0,
                     'retained': False},
    }
    payload.update(overrides)
    return payload


class Fixture:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='wksim-overhead-test-')

    def write(self, name, payload, rows):
        directory = os.path.join(self.root, name)
        os.makedirs(directory)
        with open(os.path.join(directory, 'result.json'), 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        with open(os.path.join(directory, 'timing.csv'), 'w', encoding='utf-8') as handle:
            for row in rows:
                handle.write(','.join(str(value) for value in row) + '\n')
        return directory

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Checker:
    def __init__(self):
        self.passed, self.failed, self.failures = 0, 0, []

    def check(self, condition, description):
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.failures.append(description)

    def rejects(self, reason, description, base_payload, base_rows, variant_payload,
                variant_rows):
        fixture = Fixture()
        try:
            base = fixture.write('base', base_payload, base_rows)
            variant = fixture.write('variant', variant_payload, variant_rows)
            try:
                A.analyze(base, variant)
            except A.Rejected as rejection:
                self.check(rejection.reason == reason,
                           '%s (reason %s, expected %s)'
                           % (description, rejection.reason, reason))
            except Exception as error:  # noqa: BLE001 - the test must see any other failure
                self.check(False, '%s (raised %s: %s)'
                           % (description, type(error).__name__, error))
            else:
                self.check(False, '%s (nothing was rejected)' % description)
        finally:
            fixture.cleanup()


def run_success(checker):
    fixture = Fixture()
    try:
        base_rows, variant_rows = timing_rows(slip=1000), timing_rows(slip=4000, work=3000)
        base = fixture.write('base', result('disabled', base_rows), base_rows)
        variant = fixture.write('variant', result('enabled', variant_rows), variant_rows)
        report = A.analyze(base, variant)
        deltas = report['measured_deltas']
        checker.check(report['no_performance_threshold'] is True,
                      'the report declares that no threshold was applied')
        checker.check('pass' not in json.dumps(report).lower(),
                      'the report contains no pass/fail verdict wording')
        checker.check(deltas['owner_thread_cpu_ns']['delta'] == 0,
                      'owner CPU delta is variant minus base')
        # The release rule measures each period from the previous ACTUAL start, so one late
        # group propagates: slip grows by the constant offset and the loop span grows with it.
        # These expectations were read off the fixture, not assumed.
        checker.check(deltas['mean_slip_ns']['delta'] == 9000,
                      'mean slip delta follows the fixture offset (9000 ns)')
        checker.check(deltas['p99_slip_ns']['delta'] == 15000,
                      'p99 slip delta follows the fixture offset (15000 ns)')
        checker.check(deltas['mean_start_to_end_ns']['delta'] == 1000,
                      'mean start-to-end delta is the work delta (1000 ns)')
        checker.check(deltas['loop_span_ns']['delta'] == 16000,
                      'loop span delta follows the propagated slip and work deltas')
        checker.check(deltas['recorder_start_span_ns'] == 12_000,
                      'the enabled row recorder start span is reported verbatim')
    finally:
        fixture.cleanup()


def run_rejections(checker):
    base_rows, variant_rows = timing_rows(), timing_rows()

    checker.rejects('wrong_mode', 'both rows disabled', result('disabled', base_rows),
                    base_rows, result('disabled', variant_rows), variant_rows)

    checker.rejects('recorder_retained', 'the enabled row retained ownership',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows, recorder={
                        'enabled': True, 'start_rc': 0, 'stop_rc': 0, 'retained': True}),
                    variant_rows)

    checker.rejects('recorder_lifecycle', 'the recorder stop returned a failure',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows, recorder={
                        'enabled': True, 'start_rc': 0, 'stop_rc': -1, 'retained': False}),
                    variant_rows)

    # Each row stays internally consistent (its own duration/period/iterations agree), so the
    # pair-level workload mismatch is what must be reported.
    checker.rejects('workload_mismatch', 'the variant requested another period',
                    result('disabled', base_rows), base_rows,
                    result('enabled', timing_rows(period=PERIOD + 1, count=4),
                           period=PERIOD + 1),
                    timing_rows(period=PERIOD + 1, count=4))

    checker.rejects('incomplete_timing', 'the variant CSV lost its last row',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows, timing_rows=ITERATIONS - 1),
                    variant_rows[:-1])

    checker.rejects('timing_index_gap', 'a row is missing from the middle',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows), [variant_rows[0], variant_rows[2],
                                                      variant_rows[3], variant_rows[4]])

    # A regressing "earliest" is the reachable form of clock regression: it cannot be
    # confused with the compressed-start rule, because starts stay a full period apart.
    checker.rejects('timing_clock_regression', 'an earliest start went backwards',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows),
                    [(0, START, START + 2 * PERIOD, START + 2 * PERIOD, START + 3 * PERIOD),
                     (1, START + PERIOD, START + PERIOD, START + 2 * PERIOD,
                      START + 3 * PERIOD)] + variant_rows[2:])

    # Compressed starts cannot occur in a well-formed row sequence: the release rule implies
    # actual[k] - actual[k-1] >= period, so this validator branch is a defensive check for a
    # tampered file. Assert the detection capability directly, and confirm independently that
    # the gap statistic still exposes the defect if the branch ever stopped firing.
    compressed = [(0, START, START, START + 2, START + 4),
                  (1, START + PERIOD, START + PERIOD, START + PERIOD + 1,
                   START + 2 * PERIOD)]
    try:
        A.check_timing(compressed, PERIOD, 2, 'synthetic')
        checker.check(False, 'compressed starts are rejected (nothing was rejected)')
    except A.Rejected as rejection:
        checker.check(rejection.reason in ('compressed_start', 'timing_row_order'),
                      'compressed starts are rejected (reason %s)' % rejection.reason)
    checker.check(A.describe(compressed, PERIOD)['min_actual_start_gap_ns'] == PERIOD - 1,
                  'the gap statistic exposes a compressed start as period - 1')

    checker.rejects('timing_row_order', 'end precedes the actual start',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows),
                    [variant_rows[0][:4] + (variant_rows[0][3] - 1,)] + variant_rows[1:])

    checker.rejects('malformed_csv', 'a CSV line has the wrong field count',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows),
                    [variant_rows[0][:4]] + variant_rows[1:])


def run_boundary_and_checksum(checker):
    """Defect 4/5 coverage: exactly one legal iteration, and a pair whose requested workload
    fields match while the actual work does not."""
    fixture = Fixture()
    try:
        # duration == period is legal at the producer, so the analyzer must accept one row.
        one = timing_rows(count=1)
        base = fixture.write('one-base', result('disabled', one, duration=PERIOD), one)
        variant = fixture.write('one-variant', result('enabled', one, duration=PERIOD), one)
        report = A.analyze(base, variant)
        checker.check(report['workload']['iterations'] == 1,
                      'a one-iteration pair is accepted as the requested workload')
        gap = report['base']['loop']['min_actual_start_gap_ns']
        checker.check(gap == PERIOD and report['base']['loop']['min_actual_start_gap_defined']
                      is False,
                      'a one-iteration run reports the gap bound and marks it undefined')
        checker.check(report['measured_deltas']['missed_deadlines']['delta'] == 0,
                      'a one-iteration pair reports zero deadline-miss delta')
    finally:
        fixture.cleanup()

    base_rows, variant_rows = timing_rows(), timing_rows()

    # Matching requested fields but a truncated run: 4 iterations for duration 5 / period 1.
    checker.rejects('iteration_count_mismatch', 'the pair matching each other but truncated',
                    result('disabled', base_rows[:4]), base_rows[:4],
                    result('enabled', variant_rows[:4]), variant_rows[:4])

    # Matching requested fields but the deterministic body ended elsewhere.
    checker.rejects('body_checksum_mismatch', 'the two rows ran different synthetic work',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows,
                           measurement={'loop_span_ns': 1, 'body_checksum': 7,
                                        'recorder_start_span_ns': 1,
                                        'recorder_stop_span_ns': 1}),
                    variant_rows)

    # A relabelled run whose declared count no longer matches its own request.
    checker.rejects('iteration_count_mismatch', 'the variant relabelled its iteration count',
                    result('disabled', base_rows), base_rows,
                    result('enabled', variant_rows, iterations=4, timing_rows=4),
                    variant_rows)


def main():
    checker = Checker()
    run_success(checker)
    run_boundary_and_checksum(checker)
    run_rejections(checker)
    print('analyze_overhead synthetic tests: %d checks, %d failed'
          % (checker.passed + checker.failed, checker.failed))
    for failure in checker.failures:
        print('  FAIL: %s' % failure)
    return 0 if checker.failed == 0 else 1


if __name__ == '__main__':
    saved_argv, sys.argv = sys.argv, [sys.argv[0]]
    try:
        sys.exit(main())
    finally:
        sys.argv = saved_argv
