"""Offline tests for the inter-step gap mapping tool.

Synthetic and stdlib-only: a miniature archived source tree and a miniature audit
artifact are written into a temporary directory, so the mapping, the anchor
resolution, the offset derivation and the wire-window reasoning are all exercised
without touching a real archive or importing wksim.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('ds_group_gap_map_under_test',
                                               os.path.join(HERE, 'gap_map.py'))
gap_map = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gap_map)

JOINT = '''\
class JointPhysics:
    def advance(self):
        marks = [(time.monotonic_ns(), time.thread_time_ns())] if self.cpu_timing else None
        self.health()
        if marks is not None: marks.append((time.monotonic_ns(), time.thread_time_ns()))
        self.finish_inputs()
        if marks is not None:
            marks.append((time.monotonic_ns(), time.thread_time_ns()))
            if self.timing_census:
                self.record('diagnostic_step_cpu_timing',
                    stages={name: None
                            for name,a,b in zip(('health_and_models','encode_send','native_inputs'),marks,marks[1:])})
        if tick > 4000 and self.px_time is None:
            raise TimeoutError('PX4 actuator startup exceeded four simulation seconds')
        return self.states
'''

RATE = '''\
class JointRate:
    def begin_group(self, tick, health):
        ideal = 0
        for _ in range(4):
            self.check(max(0, now - ideal))
        self.group = dict(start_tick=tick)
        self.record('rate_group_start',segment_id=self.segment_id,request_id=self.request_id,
                    lateness_ns=max(0,now-ideal),**self.group)
    def end_group(self, tick):
        now = self.now()
        lateness = 0
        self.record('rate_group_end')
        self.completed += 1
        self.check(lateness)
'''

RUNNER = '''\
        def record(kind, **data):
            pass

        def health():
            pass

        def physics_health():
            pass

        def health():
            physics_health()
            for name, child, _ in children:
                code = child.poll()
                if code is not None:
                    raise RuntimeError('Task exited without matching successful result')

            def advance():
                if rate is not None:
                    rate.begin_group(clock.tick, physics_health)
                    states = physics.advance()
                    publisher.publish(clock)
                    clock_log.write(json.dumps(clock.snapshot(),separators=(',',':'))+'\\n')
                if rate is not None:
                    rate.end_group(clock.tick)
                return states
            while clock.tick < MAX_TICKS:
                health()
                states = advance()
'''

CLOCK = 'class ClockPublisher:\n    def publish(self, clock):\n        pass\n'

PERIOD = 8_000_000


def write_sources(directory):
    for name, text in (
            (gap_map.SOURCES['joint'], JOINT),
            (gap_map.SOURCES['rate'], RATE),
            (gap_map.SOURCES['runner'], RUNNER),
            (gap_map.SOURCES['clock'], CLOCK)):
        with open(os.path.join(directory, name), 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)


def build_audit_and_wire(group_start_tick=10_524, prefix=1_000,
                         durations=(2_000_000, 3_000_000, 1_500_000, 1_000_000),
                         gaps=(400_000, 4_987_926, 300_000), base=60_000_000_000):
    """A miniature audit artifact plus a matching joint-wire step/barrier stream."""
    windows = []
    cursor = base + prefix
    for index, duration in enumerate(durations):
        windows.append({'tick': group_start_tick + 1 + index, 'start': cursor,
                        'end': cursor + duration})
        cursor += duration + (gaps[index] if index < 3 else 0)
    actual_end = cursor + 100_000
    region = {
        'rank': 1, 'segment_id': 1, 'start_tick': group_start_tick,
        'end_tick': group_start_tick + 4, 'requested_rate': 0.5, 'period_ns': PERIOD,
        'work_ns': actual_end - base, 'excess_ns': actual_end - base - PERIOD,
        'excess_ratio': 0.0, 'accounted_ns': actual_end - base,
        'interval_ns': [base, actual_end],
        'preceding_boundary': {'ideal_start_ns': base - 1_000_000,
                               'earliest_start_ns': base,
                               'actual_start_ns': base, 'lateness_ns': 0},
        'following_boundary': {'ideal_end_ns': base + PERIOD, 'actual_end_ns': actual_end,
                               'lateness_ns': actual_end - base - PERIOD},
        'measured': True,
        'breakdown': {
            'prefix_ns': prefix, 'suffix_ns': 100_000,
            'visible_step_durations_ns': list(durations),
            'inter_step_gaps_ns': list(gaps),
            'largest_step': {'index': 0, 'tick': group_start_tick + 1,
                             'wall_ns': max(durations)},
            'phase_wall_ns': {name: 0 for name in ('health_and_models', 'encode_send',
                                                   'native_inputs')},
            'phase_thread_cpu_ns': {name: 0 for name in ('health_and_models', 'encode_send',
                                                         'native_inputs')},
            'wall_minus_thread_cpu_ns': {name: 0 for name in ('health_and_models',
                                                              'encode_send', 'native_inputs')},
            'native_wait_wall_ns': 0, 'native_wait_thread_cpu_ns': 0,
            'native_inputs_stage_uncovered_by_visible_waits_ns': 0, 'native_waits': 5,
        },
        'measurement': 'synthetic',
    }
    audit = {'tool': 'ds_group_audit', 'verdict': 'pass',
             'reports': [{'segment_id': 1, 'start_tick': group_start_tick,
                          'end_tick': group_start_tick + 4}],
             'ranking': {'ranked_measured_regions': [region]}}
    return audit, windows, region


def wire_rows(windows, offset, writes_at):
    """Build joint-wire rows; writes_at maps tick -> position inside its window."""
    rows = []
    for window in windows:
        tick = window['tick']
        if tick not in writes_at:
            continue
        monotonic = window['start'] + writes_at[tick]
        rows.append({'kind': 'step', 'epoch': 'e', 'tick': tick,
                     'wall': (monotonic - offset) / 1e9})
        rows.append({'kind': 'barrier', 'epoch': 'e', 'tick': tick,
                     'wall': (monotonic - offset) / 1e9})
    return rows


class GapMapTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='ds-gap-map-test-')
        write_sources(self.directory)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def build(self, audit, rows, sources=True):
        with open(os.path.join(self.directory, 'joint-wire.jsonl'), 'w',
                  encoding='utf-8', newline='\n') as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        audit_path = os.path.join(self.directory, 'audit.json')
        with open(audit_path, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(audit, handle)
        return gap_map.build(self.directory, audit_path, None)

    def test_valid_fixture_passes_and_bounds_the_offset(self):
        audit, windows, _ = build_audit_and_wire()
        offset = 52_296_472_837
        rows = wire_rows(windows, offset, {w['tick']: (w['end'] - w['start']) // 2
                                           for w in windows})
        report, findings = self.build(audit, rows)
        self.assertEqual(findings.counts['error'], 0, findings.items)
        interval = report['clock_alignment']['interval_ns']
        self.assertLessEqual(interval[0], offset)
        self.assertGreaterEqual(interval[1], offset)
        self.assertEqual(report['clock_alignment']['steps_aligned'], 4)
        self.assertTrue(report['clock_alignment']['consistency'])

    def test_seam_regions_are_cited_with_source_hashes(self):
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837,
                         {w['tick']: 1_000 for w in windows})
        report, findings = self.build(audit, rows)
        ids = [region['id'] for region in report['executed_regions']]
        self.assertEqual(ids, [region['id'] for region in sorted(gap_map.REGIONS,
                                                                 key=lambda r: r['order'])])
        for region in report['executed_regions']:
            self.assertEqual(len(region['source']['sha256']), 64)
            self.assertLess(region['source']['line_start'], region['source']['line_end'] + 1)
            self.assertTrue(region['excerpt'].strip())
        for name in ('mark_1', 'mark_2', 'mark_3'):
            self.assertIn(name, report['seam_definition'])

    def test_largest_gap_is_inside_one_group_span(self):
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837,
                         {w['tick']: 1_000 for w in windows})
        report, findings = self.build(audit, rows)
        summary = report['gap_summary']
        self.assertEqual(summary['gaps_total'], 3)
        self.assertEqual(summary['gaps_intra_group'], 3)
        self.assertEqual(summary['gaps_crossing_rate_boundary'], 0)
        self.assertNotIn('gaps_macro_boundary', summary)
        self.assertEqual(summary['gap_max_ns'], 4_987_926)
        target = report['targets'][0]
        self.assertEqual(target['measured_gap_ns'], 4_987_926)
        self.assertTrue(target['within_group_span'])
        self.assertFalse(target['crosses_rate_boundary'])
        self.assertNotIn('macro_boundary', target)
        for region in target['executed_regions']:
            expected = 'not executed' if region['id'] in ('rate_end_group', 'rate_begin_group') \
                else 'executed'
            self.assertIn(expected, region['applicability'])

    def test_rate_boundary_regions_are_never_inside_a_retained_gap(self):
        """end_group sits after the P+4 mark, the next begin_group before P+5."""
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837,
                         {w['tick']: 1_000 for w in windows})
        report, findings = self.build(audit, rows)
        self.assertTrue(report['targets'])
        for target in report['targets']:
            self.assertTrue(target['within_group_span'])
            self.assertFalse(target['crosses_rate_boundary'])
            for region in target['executed_regions']:
                if region['id'] in ('rate_end_group', 'rate_begin_group'):
                    self.assertEqual(region['applicability'],
                                     'not executed inside this gap')
                    self.assertIn('P+4', region['reason'])
                    self.assertIn('P+5', region['reason'])

    def test_no_wire_row_lands_after_a_gap_start(self):
        audit, windows, _ = build_audit_and_wire()
        # write every step row late in its own window, i.e. after its own mark #2
        rows = wire_rows(windows, 52_296_472_837,
                         {w['tick']: (w['end'] - w['start']) - 100 for w in windows})
        report, findings = self.build(audit, rows)
        self.assertEqual(findings.counts['error'], 0, findings.items)
        for target in report['targets']:
            gap_ns = target['measured_gap_ns']
            for annotation in target['wire_step_rows_in_window']:
                offsets = annotation['write_offset_in_gap_ns']
                if offsets is not None:
                    # a late write can only reach the gap boundaries, never beyond
                    self.assertGreaterEqual(offsets[0], 0, annotation)
                    self.assertLessEqual(offsets[1], gap_ns, annotation)
                else:
                    self.assertEqual(annotation['relation'],
                                     'this row was written outside the measured gap')

    def test_region_span_identity_is_checked(self):
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        # tamper: the artifact's own span no longer equals prefix+steps+gaps+suffix
        audit['ranking']['ranked_measured_regions'][0]['interval_ns'][1] += 1
        report, findings = self.build(audit, rows)
        self.assertIn('region-span-identity', {item['code'] for item in findings.items})

    def test_reconstructed_windows_match_the_recorded_gaps(self):
        audit, windows, _ = build_audit_and_wire()
        region = audit['ranking']['ranked_measured_regions'][0]
        rebuilt = list(gap_map.region_windows(region))
        self.assertEqual([w['duration_ns'] for w in rebuilt],
                         region['breakdown']['visible_step_durations_ns'])
        self.assertEqual([w['tick'] for w in rebuilt],
                         [region['start_tick'] + 1 + index for index in range(4)])
        for index in range(3):
            self.assertEqual(rebuilt[index + 1]['start_ns'] - rebuilt[index]['end_ns'],
                             region['breakdown']['inter_step_gaps_ns'][index])
        self.assertEqual(rebuilt[0]['start_ns'] - region['interval_ns'][0],
                         region['breakdown']['prefix_ns'])

    def test_missing_source_is_reported(self):
        audit, windows, _ = build_audit_and_wire()
        os.remove(os.path.join(self.directory, gap_map.SOURCES['joint']))
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        report, findings = self.build(audit, rows)
        self.assertIn('source-missing', {item['code'] for item in findings.items})
        self.assertTrue(findings.errored)

    def test_moved_anchor_is_reported_not_guessed(self):
        audit, windows, _ = build_audit_and_wire()
        path = os.path.join(self.directory, gap_map.SOURCES['joint'])
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write('class JointPhysics:\n    def advance(self):\n        pass\n')
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        report, findings = self.build(audit, rows)
        codes = {item['code'] for item in findings.items}
        self.assertIn('region-unresolved', codes)

    def test_missing_audit_artifact(self):
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        with open(os.path.join(self.directory, 'joint-wire.jsonl'), 'w',
                  encoding='utf-8', newline='\n') as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        report, findings = gap_map.build(self.directory,
                                         os.path.join(self.directory, 'nope.json'), None)
        self.assertIsNone(report)
        self.assertIn('audit-missing', {item['code'] for item in findings.items})

    def test_non_passing_audit_is_rejected(self):
        audit, windows, _ = build_audit_and_wire()
        audit['verdict'] = 'fail'
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        report, findings = self.build(audit, rows)
        self.assertIn('audit-verdict', {item['code'] for item in findings.items})

    def test_inconsistent_region_offset_is_reported(self):
        audit, windows, _ = build_audit_and_wire()
        # Step windows start at 60000001000, then 60002001000, 60005401000, 60010388926.
        # These two wire readings require mutually exclusive process-start offsets, so
        # no single S can place both rows inside their own windows.
        rows = [
            {'kind': 'step', 'epoch': 'e', 'tick': windows[1]['tick'],
             'wall': (windows[1]['start'] + 1_000_000 - 52_296_472_837) / 1e9},
            {'kind': 'step', 'epoch': 'e', 'tick': windows[2]['tick'],
             'wall': (windows[2]['start'] + 4_000_000 - 52_296_472_837) / 1e9},
        ]
        report, findings = self.build(audit, rows)
        codes = {item['code'] for item in findings.items}
        self.assertIn('offset-region-inconsistent', codes)
        self.assertTrue(findings.errored)

    def test_gc_rows_inside_a_gap_are_listed(self):
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        gap_second = windows[1]['end']
        rows.append({'kind': 'diagnostic_gc_timing', 'epoch': 'e', 'tick': windows[1]['tick'],
                     'generation': 2, 'collected': 10,
                     'wall_start_ns': gap_second + 1_000, 'wall_end_ns': gap_second + 2_000,
                     'thread_cpu_ns': 1_000})
        report, findings = self.build(audit, rows)
        target = report['targets'][0]
        self.assertEqual(len(target['diagnostic_gc_rows_in_window']), 1)
        self.assertEqual(report['wire_stream']['diagnostic_gc_rows'][0]['generation'], 2)

    def test_report_is_written_and_deterministic(self):
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        with open(os.path.join(self.directory, 'joint-wire.jsonl'), 'w',
                  encoding='utf-8', newline='\n') as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(',', ':')) + '\n')
        audit_path = os.path.join(self.directory, 'audit.json')
        with open(audit_path, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(audit, handle)
        out_one = os.path.join(self.directory, 'one.json')
        out_two = os.path.join(self.directory, 'two.json')
        gap_map.build(self.directory, audit_path, out_one)
        gap_map.build(self.directory, audit_path, out_two)
        with open(out_one, 'r', encoding='utf-8') as handle:
            first = handle.read()
        with open(out_two, 'r', encoding='utf-8') as handle:
            second = handle.read()
        self.assertEqual(first, second)
        self.assertNotIn('"wall_minus_thread_cpu"', first.replace('_ns', ''))

    def test_no_gap_is_labelled_dead_time_or_descheduling(self):
        audit, windows, _ = build_audit_and_wire()
        rows = wire_rows(windows, 52_296_472_837, {w['tick']: 1_000 for w in windows})
        report, findings = self.build(audit, rows)
        targets = json.dumps(report['targets']).lower()
        for banned in ('dead time', 'dead-time', 'descheduling', 'off-cpu'):
            self.assertNotIn(banned, targets)
        self.assertIn('labels no interval as dead time', json.dumps(report).lower())


class ArchiveIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('WKSIM_GROUP_GAP_ARCHIVE'),
                         'set WKSIM_GROUP_GAP_ARCHIVE to a real archive directory')
    def test_real_archive(self):
        archive = os.environ['WKSIM_GROUP_GAP_ARCHIVE']
        audit_path = os.environ['WKSIM_GROUP_GAP_AUDIT']
        report, findings = gap_map.build(archive, audit_path, None)
        self.assertEqual(findings.counts['error'], 0, findings.items)
        summary = report['gap_summary']
        self.assertEqual(summary['gaps_total'], 48)
        self.assertEqual(summary['gaps_intra_group'], 48)
        self.assertEqual(summary['gaps_crossing_rate_boundary'], 0)
        self.assertEqual(summary['gap_max_ns'], 4_987_926)
        self.assertEqual(report['targets'][0]['from_tick'], 18_814)
        self.assertEqual(report['clock_alignment']['steps_aligned'], 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
