"""Offline tests for the independent group work-timing audit CLI.

Everything here is synthetic and stdlib-only: no wksim module is imported, no
native process runs, no archive is read unless ``WKSIM_GROUP_AUDIT_ARCHIVE``
points at one (that integration test is skipped by default).

The fixtures are built by hand so that every malformed-input case is a single,
deliberate mutation of an otherwise valid archive.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_PATH = os.path.join(HERE, 'ds_group_audit.py')

_spec = importlib.util.spec_from_file_location('ds_group_audit_under_test', AUDIT_PATH)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)
AUDIT_MODULE = audit

EPOCH = 'test-epoch-0001'
RATE = 0.5
PERIOD = 8_000_000
ANCHOR_NS = 1_000_000_000
REPORT_LIMIT = 2


def _step_windows(start_tick, start_ns, plan):
    """Build four CPU step windows from a compact per-tick wall plan."""
    windows = []
    cursor = start_ns
    for tick, (health, encode, native) in zip(range(start_tick + 1, start_tick + 5), plan):
        wall_start = cursor
        wall_end = wall_start + health + encode + native
        windows.append({
            'tick': tick,
            'wall_start_ns': wall_start,
            'wall_end_ns': wall_end,
            'stages': {
                'health_and_models': {'wall_ns': health, 'thread_cpu_ns': health - 100},
                'encode_send': {'wall_ns': encode, 'thread_cpu_ns': encode},
                'native_inputs': {'wall_ns': native, 'thread_cpu_ns': native - 200},
            },
        })
        cursor = wall_end
    return windows


def _report(group, previous=None):
    """Turn a synthetic over-budget group into a census report object."""
    windows = _step_windows(group['start_tick'], group['actual_start_ns'] + group['prefix_ns'],
                            group['plan'])
    durations = [w['wall_end_ns'] - w['wall_start_ns'] for w in windows]
    gaps = [windows[i + 1]['wall_start_ns'] - windows[i]['wall_end_ns'] for i in range(3)]
    step_wall = group['prefix_ns'] + sum(durations) + sum(gaps) + group['suffix_ns']
    work = group['actual_end_ns'] - group['actual_start_ns']
    assert step_wall == work, 'fixture plan must close'
    waits = []
    for window in windows:
        stage_start = (window['wall_start_ns']
                       + window['stages']['health_and_models']['wall_ns']
                       + window['stages']['encode_send']['wall_ns'])
        native = window['stages']['native_inputs']['wall_ns']
        waits.append({
            'tick': window['tick'], 'stage_verified': True, 'stack': 'arducopter',
            'wall_start_ns': stage_start, 'wall_end_ns': stage_start + native // 2,
            'wall_ns': native // 2, 'thread_cpu_ns': native // 3,
            'ap_frame': window['tick'],
        })
        if window['tick'] == group['start_tick'] + 4:
            px4_start = stage_start + native // 2
            waits.append({
                'tick': window['tick'], 'stage_verified': True, 'stack': 'px4',
                'wall_start_ns': px4_start, 'wall_end_ns': window['wall_end_ns'],
                'wall_ns': window['wall_end_ns'] - px4_start,
                'thread_cpu_ns': (window['wall_end_ns'] - px4_start) + 5,
                'px4_time_us': 2000,
            })
    phases = {}
    for name in audit.STAGES:
        phases[name] = {
            'wall_ns': sum(w['stages'][name]['wall_ns'] for w in windows),
            'thread_cpu_ns': sum(w['stages'][name]['thread_cpu_ns'] for w in windows),
            'samples': 4,
        }
    report = {
        'kind': 'group_work_timing',
        'schema': audit.SCHEMA_EXPECTED,
        'classification': audit.CLASSIFICATION_EXPECTED,
        'full_acceptance': False,
        'census': True,
        'epoch': EPOCH,
        'segment_id': group['segment_id'],
        'start_tick': group['start_tick'],
        'end_tick': group['end_tick'],
        'requested_rate': RATE,
        'period_ns': PERIOD,
        'work_ns': work,
        'excess_ns': work - PERIOD,
        'preceding_boundary': {
            'ideal_start_ns': group['ideal_start_ns'],
            'earliest_start_ns': group['earliest_start_ns'],
            'actual_start_ns': group['actual_start_ns'],
            'lateness_ns': max(0, group['actual_start_ns'] - group['ideal_start_ns']),
        },
        'following_boundary': {
            'ideal_end_ns': group['ideal_end_ns'],
            'actual_end_ns': group['actual_end_ns'],
            'lateness_ns': max(0, group['actual_end_ns'] - group['ideal_end_ns']),
        },
        'phases': phases,
        'retained_steps': [{
            'tick': w['tick'], 'wall_start_ns': w['wall_start_ns'], 'wall_end_ns': w['wall_end_ns'],
            'wall_ns': w['wall_end_ns'] - w['wall_start_ns'],
            'thread_cpu_ns': sum(w['stages'][n]['thread_cpu_ns'] for n in audit.STAGES),
            'gap_from_previous_retained_ns': (None if i == 0
                                              else w['wall_start_ns'] - windows[i - 1]['wall_end_ns']),
        } for i, w in enumerate(windows)],
        'visible_native_waits': waits,
        'work_decomposition': {
            'prefix_ns': group['prefix_ns'],
            'step_durations_ns': durations,
            'step_gaps_ns': gaps,
            'suffix_ns': group['suffix_ns'],
            'closes': True,
        },
        'step_windows': windows,
    }
    if previous is not None:
        report['previous_group'] = dict(previous)
    return report


def build_fixture():
    """A small, internally consistent archive with one capped-out report.

    Groups at ticks 0/4/8/12/16.  Over budget: group 4 (12ms), group 12 (20ms),
    group 16 (9ms).  With REPORT_LIMIT=2 the tick-16 report must be dropped.
    """
    plans = {
        0: (400_000, 300_000, 2_300_000),
        4: (400_000, 400_000, 2_200_000),
        8: (400_000, 300_000, 2_300_000),
        12: (500_000, 400_000, 2_600_000),
        16: (400_000, 300_000, 2_300_000),
    }
    group_plan = {
        0: ((100_000, 50_000, 400_000), (100_000, 50_000, 400_000),
            (100_000, 50_000, 400_000), (100_000, 50_000, 900_000)),
        4: ((400_000, 90_000, 900_000), (500_000, 90_000, 1_400_000),
            (600_000, 90_000, 1_500_000), (3_000_000, 90_000, 1_880_000)),
        8: ((100_000, 50_000, 300_000), (100_000, 50_000, 300_000),
            (100_000, 50_000, 300_000), (100_000, 50_000, 300_000)),
        12: ((900_000, 120_000, 2_400_000), (900_000, 120_000, 2_600_000),
             (6_000_000, 120_000, 2_500_000), (900_000, 120_000, 2_600_000)),
        16: ((300_000, 80_000, 1_300_000), (300_000, 80_000, 1_400_000),
             (300_000, 80_000, 1_400_000), (3_300_000, 80_000, 1_400_000)),
    }
    lateness = {0: 0, 4: 500_000, 8: 600_000, 12: 4_600_000, 16: 0}
    prefix = {0: 60_000, 4: 30_000, 8: 40_000, 12: 50_000, 16: 20_000}
    suffix = {0: 40_000, 4: 20_000, 8: 30_000, 12: 30_000, 16: 10_000}

    groups = []
    previous_start = None
    for index, start in enumerate((0, 4, 8, 12, 16)):
        ideal_start = ANCHOR_NS + index * PERIOD
        earliest = ideal_start if previous_start is None else max(ideal_start,
                                                                  previous_start + PERIOD)
        actual_start = earliest + lateness[start]
        step_total = sum(sum(stage) for stage in group_plan[start])
        work = prefix[start] + step_total + suffix[start]
        actual_end = actual_start + work
        group = {
            'segment_id': 1, 'start_tick': start, 'end_tick': start + 4,
            'ideal_start_ns': ideal_start, 'ideal_end_ns': ideal_start + PERIOD,
            'earliest_start_ns': earliest, 'actual_start_ns': actual_start,
            'actual_end_ns': actual_end, 'work_ns': work,
            'plan': group_plan[start], 'prefix_ns': prefix[start], 'suffix_ns': suffix[start],
            'first_ns': ideal_start - 3_000_000,
        }
        groups.append(group)
        previous_start = actual_start

    stream = [
        {'kind': 'rate_request', 'epoch': EPOCH, 'tick': 0, 'issued_monotonic_ns': ANCHOR_NS,
         'request_id': 'config', 'requested_rate': RATE},
        {'kind': 'rate_bootstrap', 'epoch': EPOCH, 'tick': 0, 'issued_monotonic_ns': ANCHOR_NS + 1,
         'classification': 'untimed_until_first_synchronized_barrier'},
        {'kind': 'rate_anchor', 'epoch': EPOCH, 'tick': 0, 'issued_monotonic_ns': ANCHOR_NS,
         'reason': 'synchronized_boundary', 'requested_rate': RATE, 'request_id': 'config',
         'segment_id': 1, 'latched': False,
         'anchor': {'tick': 0, 'wall_ns': ANCHOR_NS, 'transition': False},
         'measured_rate': None, 'measurement': 'timed_segment', 'completed_groups': 0,
         'worst_lateness_ns': 0, 'steady_after_ns': ANCHOR_NS + PERIOD},
    ]
    reports = []
    over_budget = []
    previous = None
    for group in groups:
        common = {'epoch': EPOCH, 'segment_id': group['segment_id'],
                  'request_id': 'config', 'requested_rate': RATE, 'transition': False,
                  'start_tick': group['start_tick'], 'end_tick': group['end_tick'],
                  'ideal_start_ns': group['ideal_start_ns'],
                  'ideal_end_ns': group['ideal_end_ns'],
                  'earliest_start_ns': group['earliest_start_ns'],
                  'actual_start_ns': group['actual_start_ns']}
        stream.append(dict({'kind': 'rate_group_start', 'tick': group['start_tick'],
                            'issued_monotonic_ns': group['actual_start_ns'],
                            'lateness_ns': max(0, group['actual_start_ns']
                                               - group['ideal_start_ns'])}, **common))
        stream.append(dict({'kind': 'rate_group_end', 'tick': group['end_tick'],
                            'issued_monotonic_ns': group['actual_end_ns'],
                            'actual_end_ns': group['actual_end_ns'],
                            'lateness_ns': max(0, group['actual_end_ns']
                                               - group['ideal_end_ns'])}, **common))
        if group['work_ns'] > PERIOD:
            over_budget.append(group)
    for group in over_budget[:REPORT_LIMIT]:
        reports.append(_report(group, previous))
        previous = {'segment_id': group['segment_id'], 'start_tick': group['start_tick'],
                    'work_ns': group['work_ns'], 'excess_ns': group['work_ns'] - PERIOD}
    dropped = len(over_budget) - len(reports)
    result = {
        'status': 'failed',
        'run_id': 'synthetic-fixture',
        'scene_epoch': EPOCH,
        'source_unchanged': True,
        'flight_completed': False,
        'group_work_timing': {
            'schema': audit.SCHEMA_EXPECTED,
            'classification': audit.CLASSIFICATION_EXPECTED,
            'full_acceptance': False,
            'field': 'group_work_timing',
            'reports_enabled': True,
            'report_limit': REPORT_LIMIT,
            'census': True,
            'epoch': EPOCH,
            'valid': True,
            'invalid_reason': None,
            'reasons': [],
            'unfinished_group': None,
            'counts': {
                'groups_complete': len(groups),
                'groups_incomplete': 0,
                'over_budget_groups': len(over_budget),
                'reports_emitted': len(reports),
                'reports_dropped': dropped,
                'diagnostic_errors': 0,
            },
        },
    }
    return {'stream': stream, 'reports': reports, 'result': result}


class FixtureDirectory:
    """Write a fixture dict to a temporary archive directory."""

    def __init__(self, fixture=None):
        self.fixture = fixture if fixture is not None else build_fixture()
        self.directory = tempfile.mkdtemp(prefix='ds-group-audit-test-')
        self.write()

    def write(self):
        with open(os.path.join(self.directory, 'rate.jsonl'), 'w', encoding='utf-8',
                  newline='\n') as handle:
            for row in self.fixture['stream']:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        with open(os.path.join(self.directory, 'group-work-timing.jsonl'), 'w', encoding='utf-8',
                  newline='\n') as handle:
            for row in self.fixture['reports']:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        with open(os.path.join(self.directory, 'result.json'), 'w', encoding='utf-8',
                  newline='\n') as handle:
            json.dump(self.fixture['result'], handle)

    @property
    def rate(self):
        return os.path.join(self.directory, 'rate.jsonl')

    @property
    def reports(self):
        return os.path.join(self.directory, 'group-work-timing.jsonl')

    @property
    def result(self):
        return os.path.join(self.directory, 'result.json')

    def cleanup(self):
        shutil.rmtree(self.directory, ignore_errors=True)


def run_audit(fixture_dir, out=None):
    """Run the audit CLI in-process; return ``(exit_code, report_dict, stdout)``."""
    argv = ['--rate', fixture_dir.rate, '--group-work-timing', fixture_dir.reports,
            '--result', fixture_dir.result]
    if out:
        argv += ['--out', out]
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = AUDIT_MODULE.main(argv)
    report = None
    if out and os.path.isfile(out):
        with open(out, 'r', encoding='utf-8') as handle:
            report = json.load(handle)
    return code, report, stdout.getvalue()


def run_audit_cli(fixture_dir, out=None):
    """Run the audit as a real subprocess; return ``(exit_code, report, process)``."""
    argv = [sys.executable, AUDIT_PATH, '--rate', fixture_dir.rate,
            '--group-work-timing', fixture_dir.reports, '--result', fixture_dir.result]
    if out:
        argv += ['--out', out]
    process = subprocess.run(argv, capture_output=True, text=True, check=False)
    report = None
    if out and os.path.isfile(out):
        with open(out, 'r', encoding='utf-8') as handle:
            report = json.load(handle)
    return process.returncode, report, process


def read_jsonl(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path, rows):
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(',', ':')) + '\n')


def write_json(path, value):
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle)


def codes(report):
    return {item['code'] for item in report.get('findings', [])}


class FixtureTestCase(unittest.TestCase):
    def setUp(self):
        self.fixture = FixtureDirectory()
        self.out = os.path.join(self.fixture.directory, 'audit.json')

    def tearDown(self):
        self.fixture.cleanup()

    def audit(self):
        return run_audit(self.fixture, out=self.out)

    def mutate_reports(self, mutate):
        rows = read_jsonl(self.fixture.reports)
        mutate(rows)
        write_jsonl(self.fixture.reports, rows)

    def mutate_rate(self, mutate):
        rows = read_jsonl(self.fixture.rate)
        mutate(rows)
        write_jsonl(self.fixture.rate, rows)

    def mutate_result(self, mutate):
        with open(self.fixture.result, 'r', encoding='utf-8') as handle:
            value = json.load(handle)
        mutate(value)
        write_json(self.fixture.result, value)


class ValidFixtureTest(FixtureTestCase):
    def test_valid_fixture_passes(self):
        code, report, stdout = self.audit()
        self.assertEqual(code, 0, report['findings'] if report else stdout)
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['finding_counts']['error'], 0)
        self.assertEqual(report['rate']['over_budget_groups'], 3)
        self.assertEqual(len(report['reports']), 2)
        self.assertEqual(report['report_limit'], REPORT_LIMIT)

    def test_independent_counts_match_declared(self):
        _, report, _ = self.audit()
        counts = report['counts']
        self.assertEqual(counts['declared'], counts['recomputed'])
        self.assertEqual(counts['independent']['over_budget_derived_from_rate_boundaries'], 3)
        self.assertEqual(counts['independent']['reports_read'], 2)
        self.assertEqual(counts['independent']['rate_groups_closed'], 5)
        replay = counts['independent']['rate_boundary_replay']
        self.assertEqual(replay['groups_complete'], 5)
        self.assertEqual(replay['groups_incomplete'], 0)
        self.assertIn('not visible in the rate stream', replay['note'])

    def test_unreported_region_is_measured_work_only(self):
        _, report, _ = self.audit()
        unreported = report['ranking']['unreported_over_budget_regions']
        self.assertEqual(len(unreported), 1)
        entry = unreported[0]
        self.assertFalse(entry['measured'])
        self.assertEqual(entry['start_tick'], 16)
        self.assertEqual(entry['measured_fields'], ['period_ns', 'work_ns', 'excess_ns'])
        for absent in ('phases', 'retained_steps', 'step_windows', 'visible_native_waits',
                       'work_decomposition', 'breakdown'):
            self.assertNotIn(absent, entry)
        self.assertEqual(report['ranking']['accounting']['unmeasured_work_ns'],
                         entry['work_ns'])

    def test_measured_regions_ranked_by_work(self):
        _, report, _ = self.audit()
        ranked = report['ranking']['ranked_measured_regions']
        self.assertEqual([r['start_tick'] for r in ranked], [12, 4])
        self.assertTrue(ranked[0]['work_ns'] >= ranked[1]['work_ns'])
        for region in ranked:
            breakdown = region['breakdown']
            self.assertEqual(
                breakdown['prefix_ns'] + sum(breakdown['visible_step_durations_ns'])
                + sum(breakdown['inter_step_gaps_ns']) + breakdown['suffix_ns'],
                region['work_ns'])
            self.assertEqual(
                sum(breakdown['phase_wall_ns'].values()),
                breakdown['visible_step_wall_ns'])

    def test_phase_totals_cover_only_measured_regions(self):
        _, report, _ = self.audit()
        accounting = report['ranking']['accounting']
        measured = sum(sum(r['breakdown']['phase_wall_ns'].values())
                       for r in report['ranking']['ranked_measured_regions'])
        self.assertEqual(accounting['measured_visible_step_wall_ns'], measured)
        self.assertIn('not because they had no work', accounting['unmeasured_phase_note'])

    def test_measurement_limits_present_and_uncausal(self):
        _, report, _ = self.audit()
        ids = {item['id'] for item in report['measurement_limits']}
        for expected in ('thread-cpu-shifted-windows', 'native-wait-brackets',
                         'no-causal-attribution', 'diagnostic-only',
                         'unreported-regions-not-decomposed', 'derived-period'):
            self.assertIn(expected, ids)
        text = json.dumps(report).lower()
        for banned in ('because the os', 'caused by windows', 'acceptance: true'):
            self.assertNotIn(banned, text)

    def test_report_is_deterministic(self):
        _, first, _ = self.audit()
        second_out = os.path.join(self.fixture.directory, 'audit2.json')
        _, second, _ = run_audit(self.fixture, out=second_out)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_evidence_hashes_present(self):
        _, report, _ = self.audit()
        inputs = report['evidence']['inputs']
        self.assertEqual(set(inputs), {'group_work_timing', 'rate', 'result'})
        for entry in inputs.values():
            self.assertEqual(len(entry['sha256']), 64)
            self.assertGreater(entry['bytes'], 0)


class MalformedJsonTest(FixtureTestCase):
    def test_truncated_json_line(self):
        with open(self.fixture.reports, 'a', encoding='utf-8') as handle:
            handle.write('{"kind":"group_work_timing","schema":\n')
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('malformed-json', codes(report))

    def test_non_object_row(self):
        with open(self.fixture.rate, 'a', encoding='utf-8') as handle:
            handle.write('[1,2,3]\n')
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('non-object-row', codes(report))

    def test_blank_line_is_warning_not_error(self):
        with open(self.fixture.reports, 'a', encoding='utf-8') as handle:
            handle.write('\n')
        code, report, _ = self.audit()
        self.assertEqual(code, 0)
        self.assertIn('blank-line', codes(report))

    def test_missing_file_is_input_error(self):
        missing = os.path.join(self.fixture.directory, 'nope.jsonl')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = audit.main(['--rate', self.fixture.rate,
                               '--group-work-timing', missing,
                               '--result', self.fixture.result,
                               '--out', os.path.join(self.fixture.directory, 'bad.json')])
        self.assertEqual(code, 2)
        with open(os.path.join(self.fixture.directory, 'bad.json'), 'r', encoding='utf-8') as handle:
            report = json.load(handle)
        self.assertEqual(report['verdict'], 'input_error')
        self.assertIn('missing-file', codes(report))

    def test_unwritable_output_is_failure(self):
        target = os.path.join(self.fixture.directory, 'adir')
        os.makedirs(target)
        code, _, process = run_audit_cli(self.fixture, out=target)
        self.assertEqual(code, 1)
        self.assertIn('write_failed', process.stderr)
        self.assertIn('could not write the audit report', process.stderr)


class ReportStructureTest(FixtureTestCase):
    def test_wrong_schema(self):
        self.mutate_reports(lambda rows: rows[0].__setitem__('schema', 'wksim.group-work-timing.v1'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-declaration', codes(report))

    def test_full_acceptance_upgrade_rejected(self):
        self.mutate_reports(lambda rows: rows[0].__setitem__('full_acceptance', True))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-declaration', codes(report))

    def test_sampled_report_without_decomposition_rejected(self):
        def mutate(rows):
            rows[0]['census'] = False
            rows[0].pop('work_decomposition')
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-not-census', codes(report))

    def test_missing_phase_field(self):
        self.mutate_reports(lambda rows: rows[0]['phases'].pop('encode_send'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-phase-set', codes(report))

    def test_extra_step_window(self):
        def mutate(rows):
            rows[0]['step_windows'][3] = dict(rows[0]['step_windows'][3])
            rows[0]['step_windows'].append(dict(rows[0]['step_windows'][3]))
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-window-count', codes(report))

    def test_epoch_mismatch_between_reports(self):
        def mutate(rows):
            rows[1]['epoch'] = 'other-epoch'
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-cross-epoch', codes(report))


class WorkIdentityTest(FixtureTestCase):
    """The exact prefix + steps + gaps + suffix == work identity and its parts."""

    def _assert_mutation_fails(self, mutate, code_expected):
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn(code_expected, codes(report))

    def test_prefix_does_not_match_first_window(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['work_decomposition'].__setitem__(
                'prefix_ns', rows[0]['work_decomposition']['prefix_ns'] + 1000),
            'report-prefix')

    def test_suffix_does_not_match_last_window(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['work_decomposition'].__setitem__(
                'suffix_ns', rows[0]['work_decomposition']['suffix_ns'] - 1000),
            'report-suffix')

    def test_step_duration_tampered(self):
        def mutate(rows):
            rows[0]['work_decomposition']['step_durations_ns'][2] += 7
        self._assert_mutation_fails(mutate, 'report-durations')

    def test_gap_tampered(self):
        def mutate(rows):
            rows[0]['work_decomposition']['step_gaps_ns'][1] += 7
        self._assert_mutation_fails(mutate, 'report-gaps')

    def test_gap_consumes_the_suffix_so_identity_fails(self):
        """A self-consistent tamper that shifts work still fails the rate identity."""
        def mutate(rows):
            report = rows[0]
            report['work_ns'] += 1
            report['excess_ns'] = report['work_ns'] - report['period_ns']
            report['following_boundary']['actual_end_ns'] += 1
            report['work_decomposition']['suffix_ns'] += 1
        self.mutate_reports(mutate)
        # The report's own identity closes, but rate.jsonl keeps the real end.
        self.mutate_rate(lambda rows: [row for row in rows])
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        found = codes(report)
        self.assertTrue({'report-work-mismatch', 'report-boundary-mismatch',
                         'report-identity'} & found, found)

    def test_closes_flag_false(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['work_decomposition'].__setitem__('closes', False),
            'report-closes-flag')

    def test_negative_gap(self):
        def mutate(rows):
            report = rows[0]
            report['work_decomposition']['step_gaps_ns'][0] = -1
        self._assert_mutation_fails(mutate, 'report-negative-region')

    def test_overlapping_step_windows(self):
        def mutate(rows):
            report = rows[0]
            second = report['step_windows'][1]
            second['wall_start_ns'] = report['step_windows'][0]['wall_end_ns'] - 500
            second['wall_end_ns'] = second['wall_start_ns'] + (
                second['wall_end_ns'] - second['wall_start_ns'])
            second['stages']['health_and_models']['wall_ns'] -= 500
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertTrue({'report-window-order', 'report-wait-outside-stage',
                         'report-stage-sum'} & codes(report), codes(report))

    def test_step_wall_inconsistent_with_bounds(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['retained_steps'][0].__setitem__('wall_ns',
                                                                  rows[0]['retained_steps'][0]['wall_ns'] + 3),
            'report-step-wall')

    def test_step_gap_field_disagrees_with_windows(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['retained_steps'][2].__setitem__(
                'gap_from_previous_retained_ns',
                rows[0]['retained_steps'][2]['gap_from_previous_retained_ns'] + 5),
            'report-step-gap')

    def test_phase_wall_does_not_match_windows(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['phases']['encode_send'].__setitem__(
                'wall_ns', rows[0]['phases']['encode_send']['wall_ns'] + 11),
            'report-phase-wall')

    def test_phase_cpu_does_not_match_windows(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['phases']['native_inputs'].__setitem__(
                'thread_cpu_ns', rows[0]['phases']['native_inputs']['thread_cpu_ns'] + 11),
            'report-phase-cpu')

    def test_phase_samples_not_four(self):
        self._assert_mutation_fails(
            lambda rows: rows[0]['phases']['health_and_models'].__setitem__('samples', 3),
            'report-phase-samples')

    def test_cpu_over_wall_is_accepted(self):
        """The archive records shifted windows where thread CPU exceeds wall."""
        def mutate(rows):
            report = rows[0]
            delta = 100_000
            wait = report['visible_native_waits'][0]
            wait['thread_cpu_ns'] = wait['wall_ns'] + delta
            report['phases']['native_inputs']['thread_cpu_ns'] += delta
            report['retained_steps'][0]['thread_cpu_ns'] += delta
            report['step_windows'][0]['stages']['native_inputs']['thread_cpu_ns'] += delta
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 0, report['findings'] if report else None)
        limits = {item['id']: item for item in report['measurement_limits']}
        self.assertGreater(
            limits['thread-cpu-shifted-windows']['observed']['waits_with_cpu_over_wall'], 0)

    def test_step_window_outside_group_span(self):
        def mutate(rows):
            report = rows[0]
            first = report['step_windows'][0]
            shift = report['preceding_boundary']['actual_start_ns'] - first['wall_start_ns'] + 10
            for window in report['step_windows']:
                window['wall_start_ns'] -= shift
                window['wall_end_ns'] -= shift
            for step in report['retained_steps']:
                step['wall_start_ns'] -= shift
                step['wall_end_ns'] -= shift
            report['work_decomposition']['prefix_ns'] = -10
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertTrue({'report-negative-region', 'report-prefix'} & codes(report),
                        codes(report))


class NativeWaitTest(FixtureTestCase):
    def test_wait_outside_native_inputs_stage(self):
        def mutate(rows):
            report = rows[0]
            wait = report['visible_native_waits'][0]
            wait['wall_start_ns'] = report['step_windows'][0]['wall_start_ns']
            wait['wall_end_ns'] = wait['wall_start_ns'] + wait['wall_ns']
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-wait-outside-stage', codes(report))

    def test_wait_outside_group_span(self):
        def mutate(rows):
            report = rows[0]
            wait = report['visible_native_waits'][-1]
            wait['wall_end_ns'] += 1_000_000
            wait['wall_ns'] += 1_000_000
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertTrue({'report-wait-outside-group', 'report-wait-outside-stage'}
                        & codes(report))

    def test_wait_stack_typo(self):
        self.mutate_reports(lambda rows: rows[0]['visible_native_waits'][0].__setitem__(
            'stack', 'arducopter2'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-wait-stack', codes(report))

    def test_duplicate_stack_in_one_tick(self):
        def mutate(rows):
            report = rows[0]
            duplicate = dict(report['visible_native_waits'][0])
            duplicate['wall_start_ns'] += 1
            duplicate['wall_end_ns'] += 1
            report['visible_native_waits'].append(duplicate)
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-wait-duplicate-stack', codes(report))

    def test_wait_wall_mismatch(self):
        self.mutate_reports(lambda rows: rows[0]['visible_native_waits'][0].__setitem__(
            'wall_ns', rows[0]['visible_native_waits'][0]['wall_ns'] + 1))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-wait-wall', codes(report))

    def test_missing_tick_wait_row(self):
        self.mutate_reports(lambda rows: rows[0]['visible_native_waits'].pop(1))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-wait-missing', codes(report))

    def test_unverified_stage(self):
        self.mutate_reports(lambda rows: rows[0]['visible_native_waits'][0].__setitem__(
            'stage_verified', False))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-wait-unverified', codes(report))


class RateBoundaryTest(FixtureTestCase):
    def test_ideal_end_formula(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_start' and row['start_tick'] == 4:
                    row['ideal_end_ns'] += 1
        self.mutate_rate(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('rate-ideal-end', codes(report))

    def test_no_catch_up_equation(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_start' and row['start_tick'] == 8:
                    row['earliest_start_ns'] += 1_000_000
                    row['actual_start_ns'] += 1_000_000
        self.mutate_rate(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('rate-no-catch-up', codes(report))

    def test_start_lateness_equation(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_start' and row['start_tick'] == 4:
                    row['lateness_ns'] = 0
        self.mutate_rate(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('rate-start-lateness', codes(report))

    def test_end_lateness_equation(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_end' and row['start_tick'] == 4:
                    row['lateness_ns'] += 7
        self.mutate_rate(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('rate-end-lateness', codes(report))

    def test_contiguity_break(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_start' and row['start_tick'] == 8:
                    row['start_tick'] = 9
        self.mutate_rate(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        found = codes(report)
        self.assertTrue({'rate-contiguity', 'report-unmatched-group', 'report-order'} & found,
                        found)

    def test_end_tick_mismatch(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_end' and row['start_tick'] == 4:
                    row['end_tick'] += 1
        self.mutate_rate(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('rate-end-tick-mismatch', codes(report))

    def test_rate_epoch_mismatch(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_start' and row['start_tick'] == 8:
                    row['epoch'] = 'other-epoch'
        self.mutate_rate(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('rate-cross-epoch', codes(report))

    def test_report_period_mismatch(self):
        self.mutate_reports(lambda rows: rows[0].__setitem__('period_ns', PERIOD + 1))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertTrue({'report-period-mismatch', 'report-period-formula', 'report-excess-mismatch'}
                        & codes(report), codes(report))

    def test_report_rate_mismatch(self):
        self.mutate_reports(lambda rows: rows[0].__setitem__('requested_rate', 1.0))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertTrue({'report-rate-mismatch', 'report-period-formula',
                         'report-period-mismatch'} & codes(report), codes(report))

    def test_report_boundary_mismatch(self):
        self.mutate_reports(lambda rows: rows[0]['preceding_boundary'].__setitem__(
            'actual_start_ns', rows[0]['preceding_boundary']['actual_start_ns'] + 1))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('report-boundary-mismatch', codes(report))

    def test_period_formula_truncates_like_the_archived_code(self):
        self.assertEqual(audit.period_ns_from_rate(0.5), 8_000_000)
        self.assertEqual(audit.period_ns_from_rate(1.0), 4_000_000)


class ReportCapAndCounterTest(FixtureTestCase):
    def test_report_cap_exceeded(self):
        """An extra emitted report breaks the report_limit cap."""
        def mutate(rows):
            extra = json.loads(json.dumps(rows[0]))
            extra['start_tick'] = 16
            extra['end_tick'] = 20
            rows.append(extra)
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        found = codes(report)
        self.assertTrue({'report-cap', 'report-unmatched-group'} & found, found)

    def test_emitted_not_prefix_of_over_budget_stream(self):
        def mutate(rows):
            rows[0], rows[1] = rows[1], rows[0]
        self.mutate_reports(mutate)
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        found = codes(report)
        self.assertTrue({'report-stream-order', 'report-order'} & found, found)

    def test_reports_exceed_over_budget_groups(self):
        """Duplicate a valid report and relax the cap so only the stream check can catch it."""
        def mutate(rows):
            rows.append(json.loads(json.dumps(rows[0])))
            rows.append(json.loads(json.dumps(rows[1])))
        self.mutate_reports(mutate)
        self.mutate_result(lambda value: value['group_work_timing'].__setitem__(
            'report_limit', 8))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertTrue({'report-more-than-over-budget', 'report-order'} & codes(report),
                        codes(report))

    def test_declared_counter_mismatch(self):
        self.mutate_result(lambda value: value['group_work_timing']['counts'].__setitem__(
            'over_budget_groups', 4))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-counter-mismatch', codes(report))

    def test_declared_dropped_counter_mismatch(self):
        self.mutate_result(lambda value: value['group_work_timing']['counts'].__setitem__(
            'reports_dropped', 0))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-counter-mismatch', codes(report))

    def test_counter_removed(self):
        self.mutate_result(lambda value: value['group_work_timing']['counts'].pop(
            'reports_emitted'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-counter-type', codes(report))

    def test_summary_upgrades_acceptance(self):
        self.mutate_result(lambda value: value['group_work_timing'].__setitem__(
            'full_acceptance', True))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-full-acceptance', codes(report))

    def test_summary_not_diagnostic_only(self):
        self.mutate_result(lambda value: value['group_work_timing'].__setitem__(
            'classification', 'formal'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-classification', codes(report))

    def test_summary_epoch_mismatch(self):
        self.mutate_result(lambda value: value['group_work_timing'].__setitem__(
            'epoch', 'other-epoch'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        found = codes(report)
        self.assertTrue({'result-epoch', 'result-epoch-rate'} & found, found)

    def test_scene_epoch_mismatch(self):
        self.mutate_result(lambda value: value.__setitem__('scene_epoch', 'other-epoch'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-scene-epoch', codes(report))

    def test_unfinished_group_flag(self):
        self.mutate_result(lambda value: value['group_work_timing'].__setitem__(
            'unfinished_group', {'start_tick': 20, 'segment_id': 1, 'steps_seen': 2}))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-unfinished', codes(report))

    def test_missing_summary(self):
        self.mutate_result(lambda value: value.pop('group_work_timing'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-no-summary', codes(report))

    def test_malformed_result_json(self):
        with open(self.fixture.result, 'w', encoding='utf-8') as handle:
            handle.write('{not json')
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        found = codes(report)
        self.assertTrue({'result-malformed', 'result-no-summary'} & found, found)

    def test_undeclared_report_limit_defaults_to_independent_cap_check(self):
        """When the limit cannot be read, the audit still derives the over-budget set."""
        self.mutate_result(lambda value: value['group_work_timing'].pop('report_limit'))
        code, report, _ = self.audit()
        self.assertEqual(code, 1)
        self.assertIn('result-report-limit', codes(report))
        self.assertEqual(report['rate']['over_budget_groups'], 3)


class StreamDefectRepairTest(FixtureTestCase):
    """The five confirmed stream/admission defects from the independent review.

    Each case is the review's own counterexample shape: a stream whose structural
    defect is visible in the raw rows, with the declared counters adjusted so that
    nothing but the new check can catch it.  Tests are prepared but not run while
    the native MIXED flight is active.
    """

    def _audit_codes(self):
        code, report, stdout = self.audit()
        self.assertEqual(code, 1, report['findings'] if report else stdout)
        return codes(report)

    def test_defect1_short_report_stream_is_rejected(self):
        """emitted reports must equal min(over_budget, report_limit).

        The declared counters are made consistent with the short stream while the
        declared cap stays at the fixture value, so the honest emission law
        (min(3, 2) = 2 reports) is what catches the shortage.
        """
        rows = read_jsonl(self.fixture.reports)
        write_jsonl(self.fixture.reports, rows[:1])

        def mutate(value):
            counts = value['group_work_timing']['counts']
            counts['reports_emitted'] = 1
            counts['reports_dropped'] = 2
        self.mutate_result(mutate)
        found = self._audit_codes()
        self.assertTrue({'result-emit-minimum', 'report-cap-minimum'} & found, found)

    def test_defect1_empty_report_stream_is_rejected(self):
        """Zero emitted reports while over-budget groups exist is not admissible."""
        write_jsonl(self.fixture.reports, [])

        def mutate(value):
            counts = value['group_work_timing']['counts']
            counts['reports_emitted'] = 0
            counts['reports_dropped'] = 3
        self.mutate_result(mutate)
        found = self._audit_codes()
        self.assertTrue({'report-cap-minimum'} & found, found)

    def test_defect2_missing_final_end_row_is_rejected(self):
        """A dangling rate_group_start (starts > ends) must be reported."""
        def mutate(rows):
            ends = [index for index, row in enumerate(rows)
                    if row['kind'] == 'rate_group_end']
            rows.pop(ends[-1])
        self.mutate_rate(mutate)
        # adjust the declared tally to the shortened stream so only the stream
        # structure itself can fail
        self.mutate_result(lambda value: value['group_work_timing']['counts'].__setitem__(
            'groups_complete',
            value['group_work_timing']['counts']['groups_complete'] - 1))
        found = self._audit_codes()
        self.assertTrue({'rate-orphan-start', 'rate-stream-unbalanced',
                         'result-counter-mismatch'} & found, found)

    def test_defect3_duplicate_end_row_is_rejected(self):
        """A second rate_group_end for one group is an orphan end, not a new group."""
        def mutate(rows):
            ends = [row for row in rows if row['kind'] == 'rate_group_end']
            rows.append(dict(ends[-1]))
        self.mutate_rate(mutate)
        found = self._audit_codes()
        self.assertIn('rate-duplicate-end', found)

    def test_defect4_end_rows_moved_after_starts_is_rejected(self):
        """An end that arrives while a different group is open must be rejected."""
        def mutate(rows):
            ends = [index for index, row in enumerate(rows)
                    if row['kind'] == 'rate_group_end']
            rows.append(rows.pop(ends[0]))
        self.mutate_rate(mutate)
        found = self._audit_codes()
        self.assertTrue({'rate-stream-order', 'rate-stream-interleaving',
                         'rate-end-group-mismatch'} & found, found)

    def test_defect4_moved_stream_keeps_the_defect_visible(self):
        """Moving every end row behind every start row must not become admissible."""
        def mutate(rows):
            starts = [row for row in rows if row['kind'] == 'rate_group_start']
            ends = [row for row in rows if row['kind'] == 'rate_group_end']
            others = [row for row in rows if row['kind'] not in
                      ('rate_group_start', 'rate_group_end')]
            rows[:] = others + starts + ends
        self.mutate_rate(mutate)
        found = self._audit_codes()
        self.assertTrue({'rate-stream-order', 'rate-stream-interleaving',
                         'rate-open-group-reconciliation'} & found, found)

    def test_defect5_start_row_tick_bound_to_start_tick(self):
        """The consumer binds a start row's tick to the group's start_tick."""
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_start' and row['start_tick'] == 8:
                    row['tick'] = 9
        self.mutate_rate(mutate)
        found = self._audit_codes()
        self.assertIn('rate-start-row-tick', found)

    def test_defect5_end_row_tick_bound_to_end_tick(self):
        """The consumer binds an end row's tick to the group's end_tick."""
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'rate_group_end' and row['start_tick'] == 8:
                    row['tick'] = 11
        self.mutate_rate(mutate)
        found = self._audit_codes()
        self.assertIn('rate-end-row-tick', found)

    def test_honest_fixture_still_passes_all_five_checks(self):
        """The repairs must not reject the untouched, honest fixture."""
        code, report, stdout = self.audit()
        self.assertEqual(code, 0, report['findings'] if report else stdout)
        self.assertEqual(report['finding_counts']['error'], 0)
        self.assertEqual(len(report['reports']), 2)


class ArchiveIntegrationTest(unittest.TestCase):
    """Opt-in integration run against a real archived flight (skipped by default)."""

    @unittest.skipUnless(os.environ.get('WKSIM_GROUP_AUDIT_ARCHIVE'),
                         'set WKSIM_GROUP_AUDIT_ARCHIVE to a real archive directory')
    def test_real_archive(self):
        archive = os.environ['WKSIM_GROUP_AUDIT_ARCHIVE']
        out = os.path.join(tempfile.mkdtemp(prefix='ds-group-audit-real-'), 'audit.json')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = AUDIT_MODULE.main(['--archive', archive, '--out', out])
        self.assertEqual(code, 0, stdout.getvalue())
        with open(out, 'r', encoding='utf-8') as handle:
            report = json.load(handle)
        self.assertEqual(report['verdict'], 'pass')
        self.assertEqual(report['rate']['over_budget_groups'],
                         report['counts']['declared']['over_budget_groups'])
        self.assertEqual(len(report['reports']), report['report_limit'])
        self.assertFalse(report['ranking']['unreported_over_budget_regions'][0]['measured'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
