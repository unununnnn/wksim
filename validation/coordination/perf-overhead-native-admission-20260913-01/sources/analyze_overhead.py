#!/usr/bin/env python3
"""Paired analyzer for the synthetic recorder-overhead rows written by bench_overhead.c.

Takes a disabled row and an enabled row (each `<dir>/result.json` + `<dir>/timing.csv`),
checks that they describe the same requested workload and that neither timing file is
malformed, compressed or incomplete, then reports measured deltas only. No performance
threshold, no verdict, no native-verification claim. The loop is synthetic: even at a real
rate window's duration and period it is not the simulator, not a controller, not a flight
and not true whole-flight overhead. Loss checking, source hashing and kernel-counter
binding belong to the main launcher, not to this tool.

    python -B analyze_overhead.py <base_dir> <variant_dir> <out.json>

Exit: 0 success; 3 rejected input (stderr {ok:false,reason,detail}); 4 usage/IO failure.
`out.json` is created exclusively and never overwritten.
"""
import json
import os
import sys

EXIT_OK, EXIT_REJECTED, EXIT_USAGE = 0, 3, 4
JSON_NAME, CSV_NAME = 'result.json', 'timing.csv'
COLUMNS = ('index', 'ideal_start_ns', 'earliest_start_ns', 'actual_start_ns', 'end_ns')
CLOCKS = ((1, 'ideal_start_ns'), (2, 'earliest_start_ns'), (3, 'actual_start_ns'),
          (4, 'end_ns'))


class Rejected(Exception):
    def __init__(self, reason, detail):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def need(condition, reason, detail):
    if not condition:
        raise Rejected(reason, detail)


def is_pos_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def load_rows(directory):
    """Read one row directory and return (result dict, list of integer timing rows)."""
    json_path, csv_path = (os.path.join(directory, name) for name in (JSON_NAME, CSV_NAME))
    try:
        with open(json_path, 'r', encoding='utf-8') as handle:
            result = json.load(handle)
        with open(csv_path, 'r', encoding='utf-8') as handle:
            text = handle.read()
    except OSError as error:
        raise Rejected('io_error', 'cannot read %s: %s' % (directory, error))
    except json.JSONDecodeError as error:
        raise Rejected('malformed_json', '%s: %s' % (json_path, error))
    need(isinstance(result, dict), 'malformed_json', '%s is not an object' % json_path)
    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split(',')
        need(len(fields) == len(COLUMNS), 'malformed_csv', '%s line %d has %d fields, expected %d'
             % (csv_path, number, len(fields), len(COLUMNS)))
        try:
            rows.append(tuple(int(field) for field in fields))
        except ValueError:
            raise Rejected('malformed_csv', '%s line %d is not all integers' % (csv_path, number))
    need(rows, 'incomplete_timing', '%s holds no timing rows' % csv_path)
    return result, rows


def check_result(result, where, mode):
    """Check only the summary fields this analyzer depends on; nothing self-certifying."""
    need(result.get('mode') == mode, 'wrong_mode', '%s reports mode %r, expected %r'
         % (where, result.get('mode'), mode))
    for key in ('iterations', 'requested_duration_ns', 'requested_period_ns'):
        need(is_pos_int(result.get(key)), 'malformed_json',
             '%s %s is not a positive integer' % (where, key))
    recorder = result.get('recorder')
    need(isinstance(recorder, dict) and recorder.get('enabled') is (mode == 'enabled'),
         'malformed_json', '%s recorder.enabled does not match mode %r' % (where, mode))
    need(result.get('timing_rows') == result['iterations'], 'incomplete_timing',
         '%s timing_rows disagrees with its iteration count' % where)
    need(isinstance(result.get('cpu'), dict)
         and isinstance(result['cpu'].get('owner_thread'), dict)
         and isinstance(result['cpu'].get('process'), dict)
         and isinstance(result.get('measurement'), dict),
         'malformed_json', '%s cpu or measurement section is missing' % where)
    # Defect 4: the declared iteration count must be exactly floor(duration / period), so two
    # mutually matching but truncated or relabelled runs cannot pass as the requested workload.
    need(result['requested_period_ns'] <= result['requested_duration_ns'],
         'iteration_count_mismatch',
         '%s period exceeds its duration, so it could not cover the requested workload'
         % where)
    expected = result['requested_duration_ns'] // result['requested_period_ns']
    need(result['iterations'] == expected, 'iteration_count_mismatch',
         '%s ran %d iterations; duration %d / period %d requires %d'
         % (where, result['iterations'], result['requested_duration_ns'],
            result['requested_period_ns'], expected))
    checksum = result['measurement'].get('body_checksum')
    need(isinstance(checksum, int) and not isinstance(checksum, bool) and checksum >= 0,
         'malformed_json', '%s measurement.body_checksum is not a non-negative integer'
         % where)
    if mode == 'enabled':
        need(recorder.get('start_rc') == 0 and recorder.get('stop_rc') == 0,
             'recorder_lifecycle', '%s recorder start/stop rc is not zero' % where)
        need(recorder.get('retained') is False, 'recorder_retained',
             '%s retained recorder ownership' % where)
    return (result['iterations'], result['requested_duration_ns'],
            result['requested_period_ns'], checksum)


def check_timing(rows, period, iterations, where):
    """Complete rows in original order, nondecreasing clocks, no compressed starts. The
    row-local ordering and the cross-row clock rules are checked in separate passes so a
    tampered file cannot hide one defect behind the other's error message."""
    for index, row in enumerate(rows):
        need(row[0] == index, 'timing_index_gap',
             '%s row %d has index %d; rows must be complete and in original order'
             % (where, index, row[0]))
        need(row[2] >= row[1] and row[3] >= row[2] and row[4] >= row[3], 'timing_row_order',
             '%s row %d: ideal <= earliest <= actual <= end is violated' % (where, index))
        need(row[1] - rows[0][1] == index * period, 'timing_row_order',
             '%s row %d: ideal_start_ns is not start + k*period' % (where, index))
    for index in range(1, len(rows)):
        for column, name in CLOCKS:
            need(rows[index][column] >= rows[index - 1][column], 'timing_clock_regression',
                 '%s row %d: %s went backwards' % (where, index, name))
        gap = rows[index][3] - rows[index - 1][3]
        need(gap >= period, 'compressed_start',
             '%s row %d: actual starts are %d ns apart for a %d ns period'
             % (where, index, gap, period))
    need(len(rows) == iterations, 'incomplete_timing',
         '%s holds %d rows for %d declared iterations' % (where, len(rows), iterations))


def stat(values):
    """p90/p99 are index int(p*n) clamped to the last element; median is the lower middle."""
    ordered = sorted(values)
    return {'count': len(ordered), 'min_ns': ordered[0],
            'median_ns': ordered[(len(ordered) - 1) // 2],
            'p90_ns': ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))],
            'p99_ns': ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))],
            'max_ns': ordered[-1], 'sum_ns': sum(ordered),
            'mean_ns': sum(ordered) // len(ordered)}


def describe(rows, period):
    slipped = sum(1 for row in rows if row[3] > row[1])
    # Defect 5: duration == period is legal and yields exactly one row, so the minimum start
    # gap has no sample and must not be taken over an empty sequence. With one row the gap
    # bound is reported as the full period, which is the value the next row would have to meet.
    gaps = [rows[i][3] - rows[i - 1][3] for i in range(1, len(rows))]
    return {'slip_ns': stat([row[3] - row[1] for row in rows]),
            'start_to_end_ns': stat([row[4] - row[3] for row in rows]),
            'end_minus_earliest_ns': stat([row[4] - row[2] for row in rows]),
            'slipped_iterations': slipped,
            'missed_deadlines': sum(1 for row in rows if row[4] > row[1] + period),
            'min_actual_start_gap_ns': min(gaps) if gaps else period,
            'min_actual_start_gap_defined': bool(gaps),
            'first_ideal_start_ns': rows[0][1], 'last_end_ns': rows[-1][4],
            'loop_span_ns': rows[-1][4] - rows[0][1]}


def delta(base, variant, where):
    need(isinstance(base, int) and isinstance(variant, int)
         and not isinstance(base, bool) and not isinstance(variant, bool),
         'malformed_json', '%s is missing from a result file' % where)
    return {'base': base, 'variant': variant, 'delta': variant - base,
            'delta_us': (variant - base) / 1000.0}


def analyze(base_dir, variant_dir):
    base_result, base_rows = load_rows(base_dir)
    variant_result, variant_rows = load_rows(variant_dir)
    base_iter, base_duration, base_period, base_checksum = check_result(
        base_result, 'base', 'disabled')
    var_iter, var_duration, var_period, var_checksum = check_result(
        variant_result, 'variant', 'enabled')
    need(base_period == var_period and base_duration == var_duration and base_iter == var_iter,
         'workload_mismatch',
         'requested workload differs: period %d/%d, duration %d/%d, iterations %d/%d'
         % (base_period, var_period, base_duration, var_duration, base_iter, var_iter))
    # Defect 4: the deterministic body must end on the same value in both modes. A different
    # checksum means the two rows did not run the same synthetic work, so the pair is refused
    # rather than reported as a comparison.
    need(base_checksum == var_checksum, 'body_checksum_mismatch',
         'body checksum differs between the rows: %d vs %d, so the workload was not identical'
         % (base_checksum, var_checksum))
    check_timing(base_rows, base_period, base_iter, 'base timing.csv')
    check_timing(variant_rows, var_period, var_iter, 'variant timing.csv')
    base_loop, var_loop = describe(base_rows, base_period), describe(variant_rows, var_period)
    d = lambda name, b, v: delta(b, v, name)  # noqa: E731 - short local alias
    return {
        'classification': 'diagnostic_only', 'full_acceptance': False,
        'claim': 'measured differences of a synthetic pacing loop; not the simulator, not a '
                 'controller, not a flight, and not true whole-flight overhead',
        'no_performance_threshold': True,
        'workload': {'requested_duration_ns': base_duration,
                     'requested_period_ns': base_period, 'iterations': base_iter},
        'base': {'mode': base_result.get('mode'), 'body_checksum': base_checksum,
                 'loop': base_loop},
        'variant': {'mode': variant_result.get('mode'), 'body_checksum': var_checksum,
                    'loop': var_loop},
        'statistics_definition': 'sorted ascending; median is the lower middle element; '
                                 'p90/p99 are index int(p*n) clamped to the last element',
        'measured_deltas': {
            'loop_span_ns': d('loop_span_ns', base_loop['loop_span_ns'], var_loop['loop_span_ns']),
            'owner_thread_cpu_ns': d('owner_thread.cpu_ns', base_result['cpu']['owner_thread']['cpu_ns'],
                                     variant_result['cpu']['owner_thread']['cpu_ns']),
            'process_cpu_ns': d('process.cpu_ns', base_result['cpu']['process']['cpu_ns'],
                                variant_result['cpu']['process']['cpu_ns']),
            'mean_slip_ns': d('mean_slip_ns', base_loop['slip_ns']['mean_ns'],
                              var_loop['slip_ns']['mean_ns']),
            'p99_slip_ns': d('p99_slip_ns', base_loop['slip_ns']['p99_ns'],
                             var_loop['slip_ns']['p99_ns']),
            'mean_start_to_end_ns': d('mean_start_to_end_ns', base_loop['start_to_end_ns']['mean_ns'],
                                      var_loop['start_to_end_ns']['mean_ns']),
            'slipped_iterations': d('slipped_iterations', base_loop['slipped_iterations'],
                                    var_loop['slipped_iterations']),
            'missed_deadlines': d('missed_deadlines', base_loop['missed_deadlines'],
                                  var_loop['missed_deadlines']),
            'recorder_start_span_ns': variant_result['measurement']['recorder_start_span_ns'],
            'recorder_stop_span_ns': variant_result['measurement']['recorder_stop_span_ns'],
            'explanation': 'the two rows are separate processes measured at different times, so '
                           'these deltas include scheduler noise, CPU migration and co-tenant '
                           'activity; a small or zero getrusage delta means below-resolution, '
                           'not zero cost',
        },
    }


def main(argv):
    if len(argv) != 3:
        print('usage: analyze_overhead.py <base_dir> <variant_dir> <out.json>', file=sys.stderr)
        return EXIT_USAGE
    base_dir, variant_dir, out_path = argv
    try:
        report = analyze(base_dir, variant_dir)
        if os.path.exists(out_path):
            raise Rejected('output_exists', 'refusing to overwrite %s' % out_path)
        with open(out_path, 'x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    except Rejected as rejection:
        print(json.dumps({'ok': False, 'reason': rejection.reason,
                          'detail': rejection.detail}, sort_keys=True), file=sys.stderr)
        return EXIT_REJECTED
    except OSError as error:
        print(json.dumps({'ok': False, 'reason': 'io_error', 'detail': str(error)},
                         sort_keys=True), file=sys.stderr)
        return EXIT_USAGE
    print('workload: duration=%d ns period=%d ns iterations=%d'
          % (report['workload']['requested_duration_ns'],
             report['workload']['requested_period_ns'], report['workload']['iterations']))
    for name in ('loop_span_ns', 'owner_thread_cpu_ns', 'process_cpu_ns', 'mean_slip_ns',
                 'p99_slip_ns', 'mean_start_to_end_ns', 'missed_deadlines'):
        entry = report['measured_deltas'][name]
        print('%-22s base=%-12d variant=%-12d delta=%d'
              % (name, entry['base'], entry['variant'], entry['delta']))
    print('classification=diagnostic_only full_acceptance=false; no threshold applied')
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
