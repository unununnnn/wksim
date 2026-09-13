"""Pure offline tests for tools/group_work_timing.py.

Fixture rows are synthetic wire dicts shaped after the frozen producer schemas
(joint.py: per tick step -> diagnostic_native_input_timing -> diagnostic_step_cpu_timing,
joint_rate rate_group_start/end). Native wait windows sit inside the same tick's
native_inputs stage (stage bounds from cumulative stage wall_ns). No flight,
native code, compilation, or file writes.
"""
import copy
import unittest
from unittest.mock import patch

from tools import group_work_timing as gwt

EPOCH = 'epoch-gwt'
STAGE_WALLS = (100, 60, 40)   # native_inputs stage = [ws+160, ws+200]
STAGE_CPUS = (40, 70, 10)     # encode_send CPU > wall on purpose: retained as-is


def step_row(tick, epoch=EPOCH):
    return dict(kind='step', epoch=epoch, tick=tick, ap_source_frame=tick,
                px4_source_time_us=tick * 1000, model_ticks=4)


def cpu_row(tick, ws, epoch=EPOCH, stage_walls=STAGE_WALLS, stage_cpus=STAGE_CPUS):
    stages = {name: dict(wall_ns=w, thread_cpu_ns=c)
              for name, w, c in zip(gwt.STAGES, stage_walls, stage_cpus)}
    return dict(kind='diagnostic_step_cpu_timing', epoch=epoch, tick=tick,
                wall_start_ns=ws, wall_end_ns=ws + sum(stage_walls),
                stages=stages, limitation='fixture')


def native_row(tick, cpu_ws, epoch=EPOCH, zero_ap=False):
    """Waits inside the native_inputs stage [cpu_ws+160, cpu_ws+200] of the tick."""
    ap_end = cpu_ws + 160 if zero_ap else cpu_ws + 165
    waits = [dict(stack='arducopter', wall_start_ns=cpu_ws + 160, wall_end_ns=ap_end,
                  wall_ns=ap_end - (cpu_ws + 160),
                  thread_cpu_ns=0 if zero_ap else 3, ap_frame=tick),
             dict(stack='px4', wall_start_ns=cpu_ws + 170, wall_end_ns=cpu_ws + 190,
                  wall_ns=20, thread_cpu_ns=25, px4_time_us=tick * 1000)]
    return dict(kind='diagnostic_native_input_timing', epoch=epoch, tick=tick,
                ap_source_frame=tick, px4_source_time_us=tick * 1000,
                native_wait_wall_ns=sum(w['wall_ns'] for w in waits),
                waits=waits, limitation='fixture')


class Groups:
    """Consistent four-tick group row sequences honoring the boundary equations.

    Per-tick order follows the real producer: step -> native_input -> step_cpu.
    """

    def __init__(self, rate=1.0, epoch=EPOCH, segment=1, wall0=10_000_000_000):
        self.rate = rate
        self.period = gwt.period_ns(rate)
        self.epoch = epoch
        self.segment = segment
        self.ideal = wall0
        self.prev = None
        self.P = 0

    def reanchor(self, segment):
        self.segment = segment
        self.prev = None

    def cpu_ws(self, tick):
        return self.last_start + (tick - self.P) * 1000

    def ws_of(self, tick):
        """CPU window base of a tick in the LAST built group (P already advanced)."""
        return self.last_start + (tick - (self.P - 4)) * 1000

    def group(self, work_ns, lateness_ns=0, cpu_at=(), native_at=(), drop_steps=()):
        P, ideal, period = self.P, self.ideal, self.period
        earliest = ideal if self.prev is None else max(ideal, self.prev + period)
        actual_start = earliest + lateness_ns
        actual_end = actual_start + work_ns
        self.last_start = actual_start
        rows = [dict(kind='rate_group_start', epoch=self.epoch, tick=P,
                     segment_id=self.segment, request_id='config',
                     requested_rate=self.rate, transition=False,
                     lateness_ns=max(0, actual_start - ideal), start_tick=P,
                     end_tick=P + 4, ideal_start_ns=ideal,
                     ideal_end_ns=ideal + period, earliest_start_ns=earliest,
                     actual_start_ns=actual_start)]
        for t in range(P + 1, P + 5):
            if t in drop_steps:
                continue
            rows.append(step_row(t, self.epoch))
            if t in native_at:   # producer order: native before cpu within a tick
                rows.append(native_row(t, self.cpu_ws(t)))
            if t in cpu_at:
                rows.append(cpu_row(t, self.cpu_ws(t)))
        rows.append(dict(kind='rate_group_end', epoch=self.epoch, tick=P + 4,
                         segment_id=self.segment, request_id='config',
                         requested_rate=self.rate, transition=False,
                         actual_end_ns=actual_end,
                         lateness_ns=max(0, actual_end - (ideal + period)),
                         start_tick=P, end_tick=P + 4, ideal_start_ns=ideal,
                         ideal_end_ns=ideal + period, earliest_start_ns=earliest,
                         actual_start_ns=actual_start))
        self.prev = actual_start
        self.ideal += period
        self.P += 4
        return rows


def feed(rec, rows):
    for row in rows:
        assert rec.observe(row)


class GroupWorkTimingTests(unittest.TestCase):
    def test_periods_match_original(self):
        self.assertEqual(gwt.period_ns(0.5), 8_000_000)
        self.assertEqual(gwt.period_ns(1.0), 4_000_000)

    def test_report_limit_capped_at_sixteen(self):
        with self.assertRaisesRegex(ValueError, 'report_limit'):
            gwt.GroupWorkTiming(report_limit=17)
        with self.assertRaisesRegex(ValueError, 'report_limit'):
            gwt.GroupWorkTiming(report_limit=-1)
        rec = gwt.GroupWorkTiming(emit=lambda r: None, report_limit=0)
        feed(rec, Groups().group(work_ns=9_000_000))
        counts = rec.summary()['counts']
        self.assertEqual((counts['reports_emitted'], counts['reports_dropped']), (0, 1))

    def test_normal_group_counted_only_no_emit_valid(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        feed(rec, Groups().group(work_ns=3_999_999, cpu_at=(1, 2)))
        self.assertEqual(reports, [])
        summary = rec.summary()
        self.assertEqual(summary['counts'], dict(groups_complete=1, groups_incomplete=0,
                                                 over_budget_groups=0, reports_emitted=0,
                                                 reports_dropped=0, diagnostic_errors=0))
        self.assertTrue(summary['valid'])
        self.assertIsNone(summary['unfinished_group'])
        self.assertEqual(summary['classification'], 'diagnostic_only')
        self.assertFalse(summary['full_acceptance'])

    def test_disabled_recorder_counts_over_budget_without_reporting(self):
        rec = gwt.GroupWorkTiming()  # default: not enabled, no emit callback
        feed(rec, Groups().group(work_ns=9_000_000))
        summary = rec.summary()
        self.assertFalse(summary['reports_enabled'])
        self.assertEqual(summary['counts']['over_budget_groups'], 1)
        self.assertEqual(summary['counts']['reports_emitted'], 0)
        self.assertTrue(summary['valid'])

    def test_over_budget_report_boundary_equations(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups(rate=1.0)
        feed(rec, g.group(work_ns=5_000_000, cpu_at=(1, 2), native_at=(2,)))
        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report['kind'], 'group_work_timing')
        self.assertFalse(report['census'])
        self.assertIn('sampled: 2 of 4 steps', report['phase_coverage'])
        self.assertEqual(report['work_ns'], 5_000_000)
        self.assertEqual(report['excess_ns'], 1_000_000)
        preceding = report['preceding_boundary']
        self.assertEqual(preceding['earliest_start_ns'], preceding['ideal_start_ns'])
        self.assertEqual(preceding['lateness_ns'],
                         preceding['actual_start_ns'] - preceding['ideal_start_ns'])
        following = report['following_boundary']
        self.assertEqual(following['lateness_ns'],
                         following['actual_end_ns'] - following['ideal_end_ns'])
        self.assertEqual(report['phases']['encode_send'],
                         dict(wall_ns=120, thread_cpu_ns=140, samples=2))
        steps = report['retained_steps']
        self.assertEqual([(s['tick'], s['wall_ns']) for s in steps], [(1, 200), (2, 200)])
        self.assertEqual(steps[0]['wall_start_ns'], g.last_start + 1000)
        self.assertIsNone(steps[0]['gap_from_previous_retained_ns'])
        self.assertEqual(steps[1]['gap_from_previous_retained_ns'], 800)
        waits = report['visible_native_waits']
        self.assertEqual([(w['stack'], w['wall_ns'], w['stage_verified']) for w in waits],
                         [('arducopter', 5, True), ('px4', 20, True)])
        self.assertEqual(waits[1]['thread_cpu_ns'], 25)  # CPU > wall retained verbatim
        self.assertNotIn('previous_group', report)
        self.assertTrue(rec.summary()['valid'])

    def test_native_wait_without_same_tick_cpu_marked_unverified(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        # native row at tick 2 whose window lies inside the group span but has
        # no same-tick cpu row: sampled mode keeps it, stage unverified.
        rows = g.group(work_ns=5_000_000, cpu_at=(1,))
        rows.insert(4, native_row(2, g.ws_of(2)))  # producer order: step2 then native2
        feed(rec, rows)
        waits = reports[0]['visible_native_waits']
        self.assertEqual([w['stage_verified'] for w in waits], [False, False])
        self.assertTrue(rec.summary()['valid'])

    def test_zero_length_wait_accepted(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        feed(rec, Groups().group(work_ns=5_000_000, cpu_at=(1,), native_at=(1,)))
        # zero-length variant: rebuild one group with a zero-length AP wait
        reports.clear()
        g = Groups()
        rows = g.group(work_ns=5_000_000, cpu_at=(1,))
        rows.insert(2, native_row(1, g.ws_of(1), zero_ap=True))  # step1 -> native1 -> cpu1
        rec2 = gwt.GroupWorkTiming(emit=reports.append)
        feed(rec2, rows)
        waits = reports[0]['visible_native_waits']
        self.assertEqual(waits[0]['wall_ns'], 0)
        self.assertEqual(waits[0]['thread_cpu_ns'], 0)
        self.assertTrue(rec2.summary()['valid'])

    def test_second_report_carries_previous_complete_group(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        feed(rec, g.group(work_ns=5_000_000))
        feed(rec, g.group(work_ns=6_000_000))
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[1]['previous_group'],
                         dict(segment_id=1, start_tick=0, work_ns=5_000_000,
                              excess_ns=1_000_000))
        self.assertEqual(reports[1]['preceding_boundary']['earliest_start_ns'],
                         reports[0]['preceding_boundary']['actual_start_ns'] + 4_000_000)

    def test_rate_half_period_is_8ms_and_strictly_greater(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups(rate=0.5)
        feed(rec, g.group(work_ns=8_000_000))   # exactly one period: not over
        feed(rec, g.group(work_ns=8_000_001))   # one ns over
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]['period_ns'], 8_000_000)
        self.assertEqual(reports[0]['excess_ns'], 1)

    def test_report_cap_sixteen_and_dropped_counted(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        for _ in range(20):
            feed(rec, g.group(work_ns=9_000_000))
        counts = rec.summary()['counts']
        self.assertEqual(counts['groups_complete'], 20)
        self.assertEqual(counts['over_budget_groups'], 20)
        self.assertEqual(counts['reports_emitted'], 16)
        self.assertEqual(counts['reports_dropped'], 4)
        self.assertTrue(rec.summary()['valid'])

    def test_census_exact_work_decomposition(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append, census=True)
        g = Groups()
        feed(rec, g.group(work_ns=5_000_000, cpu_at=(1, 2, 3, 4), native_at=(2,)))
        report = reports[0]
        self.assertTrue(report['census'])
        dec = report['work_decomposition']
        self.assertEqual(dec['prefix_ns'], 1000)
        self.assertEqual(dec['step_durations_ns'], [200, 200, 200, 200])
        self.assertEqual(dec['step_gaps_ns'], [800, 800, 800])
        self.assertEqual(dec['suffix_ns'], 5_000_000 - 4200)
        self.assertTrue(dec['closes'])
        self.assertEqual(dec['prefix_ns'] + sum(dec['step_durations_ns'])
                         + sum(dec['step_gaps_ns']) + dec['suffix_ns'],
                         report['work_ns'])
        self.assertEqual(len(report['step_windows']), 4)
        self.assertEqual(report['step_windows'][0]['stages']['encode_send'],
                         dict(wall_ns=60, thread_cpu_ns=70))
        self.assertEqual([w['stage_verified'] for w in report['visible_native_waits']],
                         [True, True])
        self.assertTrue(rec.summary()['valid'])

    def test_census_missing_cpu_row_incomplete_no_report(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append, census=True)
        feed(rec, Groups().group(work_ns=5_000_000, cpu_at=(1, 2, 3)))
        counts = rec.summary()['counts']
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(counts['groups_complete'], 0)
        self.assertEqual(reports, [])
        summary = rec.summary()
        self.assertFalse(summary['valid'])
        self.assertTrue(any('census' in reason for reason in summary['reasons']))

    def test_duplicate_same_tick_cpu_rows_bounded_and_taint_group(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=9_000_000, cpu_at=(1, 2, 3, 4))
        dup = cpu_row(1, g.cpu_ws(1))
        for index in range(99):  # reviewer scenario: 100 same-tick cpu rows
            rows.insert(3 + index, copy.deepcopy(dup))
        feed(rec, rows)
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 99)
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(counts['groups_complete'], 0)
        self.assertEqual(reports, [])
        summary = rec.summary()
        self.assertFalse(summary['valid'])
        self.assertTrue(any('duplicate' in reason for reason in summary['reasons']))

    def test_out_of_order_native_after_cpu_taints_group(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=9_000_000, cpu_at=(1, 2, 3, 4))
        rows.insert(3, native_row(1, g.cpu_ws(1)))  # native AFTER cpu of tick 1
        feed(rec, rows)
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(reports, [])
        self.assertFalse(rec.summary()['valid'])

    def test_cpu_window_outside_group_span_rejected(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=5_000_000, cpu_at=(1, 2))
        for row in rows:
            if row['kind'] == 'diagnostic_step_cpu_timing' and row['tick'] == 2:
                row['wall_start_ns'] = g.last_start - 5000  # before actual start
                row['wall_end_ns'] = row['wall_start_ns'] + 200
        feed(rec, rows)
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(reports, [])

    def test_cpu_windows_overlapping_in_tick_order_rejected(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=5_000_000, cpu_at=(1, 2))
        for row in rows:
            if row['kind'] == 'diagnostic_step_cpu_timing' and row['tick'] == 2:
                row['wall_start_ns'] = g.cpu_ws(1) + 150  # overlaps tick-1 window
                row['wall_end_ns'] = row['wall_start_ns'] + 200
        feed(rec, rows)
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(reports, [])

    def test_native_wait_outside_native_inputs_stage_rejected(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=5_000_000, cpu_at=(1,))
        bad = native_row(1, g.ws_of(1))
        for wait in bad['waits']:  # shift both waits past the stage end (ws+200)
            wait['wall_start_ns'] += 60
            wait['wall_end_ns'] += 60
        rows.insert(2, bad)
        feed(rec, rows)
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(reports, [])
        self.assertTrue(any('native_inputs stage' in reason
                            for reason in rec.summary()['reasons']))

    def test_missing_step_marks_incomplete_and_invalid(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        feed(rec, Groups().group(work_ns=9_000_000, drop_steps=(3,)))
        summary = rec.summary()
        self.assertEqual(summary['counts']['groups_incomplete'], 1)
        self.assertEqual(summary['counts']['diagnostic_errors'], 0)
        self.assertFalse(summary['valid'])
        self.assertTrue(any('incomplete' in reason for reason in summary['reasons']))
        self.assertEqual(reports, [])

    def test_duplicate_and_cross_epoch_rows_counted_honestly(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=3_000_000, cpu_at=(1,))
        rows.insert(3, step_row(1))                       # duplicate step tick
        rows.insert(4, cpu_row(2, g.cpu_ws(2), epoch='other'))  # cross-epoch
        feed(rec, rows)
        summary = rec.summary()
        self.assertEqual(summary['counts']['diagnostic_errors'], 2)
        self.assertEqual(summary['counts']['groups_complete'], 1)
        self.assertFalse(summary['valid'])  # data errors invalidate the diagnostic
        self.assertEqual(reports, [])

    def test_phase_sum_mismatch_rejected_row_not_attached(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=9_000_000)
        bad = cpu_row(1, g.cpu_ws(1), stage_walls=(100, 60, 41))
        bad['wall_end_ns'] = bad['wall_start_ns'] + 200  # stage walls sum to 201
        rows.insert(2, bad)
        feed(rec, rows)
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_complete'], 1)   # row excluded, steps intact
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]['phases']['encode_send']['samples'], 0)
        self.assertFalse(rec.summary()['valid'])

    def test_group_end_equation_tamper_rejected_and_incomplete(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=9_000_000)
        rows[-1]['lateness_ns'] += 1  # boundary equation no longer holds
        feed(rec, rows)
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(counts['groups_complete'], 0)
        self.assertEqual(reports, [])

    def test_unclosed_group_marked_unfinished_then_finalized(self):
        rec = gwt.GroupWorkTiming(emit=lambda report: None)
        g = Groups()
        feed(rec, g.group(work_ns=3_000_000)[:3])     # start + two steps, never ended
        summary = rec.summary()
        self.assertFalse(summary['valid'])
        self.assertEqual(summary['unfinished_group'],
                         dict(start_tick=0, segment_id=1, steps_seen=2))
        summary = rec.finish()
        self.assertIsNone(summary['unfinished_group'])
        self.assertEqual(summary['counts']['groups_incomplete'], 1)
        self.assertTrue(any('unfinished' in reason for reason in summary['reasons']))
        feed(rec, g.group(work_ns=3_000_000))          # recorder still usable
        self.assertEqual(rec.summary()['counts']['groups_complete'], 1)

    def test_orphan_group_end_rejected(self):
        rec = gwt.GroupWorkTiming(emit=lambda report: None)
        self.assertTrue(rec.observe(Groups().group(work_ns=3_000_000)[-1]))
        counts = rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_incomplete'], 0)
        self.assertFalse(rec.summary()['valid'])

    def test_segment_regression_rejected_reanchor_allowed(self):
        rec = gwt.GroupWorkTiming(emit=lambda report: None)
        g = Groups()
        feed(rec, g.group(work_ns=3_000_000))
        g.reanchor(2)
        feed(rec, g.group(work_ns=3_000_000))     # reanchor: earliest == ideal
        bad = Groups(segment=1).group(work_ns=3_000_000)[0]
        bad['start_tick'] = g.P
        self.assertTrue(rec.observe(bad))
        self.assertEqual(rec.summary()['counts']['diagnostic_errors'], 1)
        self.assertEqual(rec.summary()['counts']['groups_complete'], 2)
        self.assertFalse(rec.summary()['valid'])

    def test_inputs_never_mutated(self):
        reports = []
        rec = gwt.GroupWorkTiming(emit=reports.append)
        g = Groups()
        rows = g.group(work_ns=9_000_000, cpu_at=(1, 2), native_at=(2,))
        snapshot = copy.deepcopy(rows)
        feed(rec, rows)
        self.assertEqual(rows, snapshot)
        self.assertEqual(len(reports), 1)

    def test_recorder_fault_invalidates_diagnostic_only(self):
        rec = gwt.GroupWorkTiming(emit=lambda report: None)
        with patch.object(rec, '_process', side_effect=RuntimeError('boom')):
            self.assertFalse(rec.observe(step_row(1)))
            self.assertFalse(rec.observe(step_row(2)))  # stays invalid
        summary = rec.summary()
        self.assertFalse(summary['valid'])
        self.assertIn('boom', summary['invalid_reason'])
        self.assertEqual(summary['counts']['diagnostic_errors'], 1)

    def test_caller_emit_exception_propagates_unchanged(self):
        def failing_emit(report):
            raise ValueError('caller callback')
        rec = gwt.GroupWorkTiming(emit=failing_emit)
        rows = Groups().group(work_ns=9_000_000)
        for row in rows[:-1]:
            self.assertTrue(rec.observe(row))
        with self.assertRaisesRegex(ValueError, 'caller callback'):
            rec.observe(rows[-1])
        summary = rec.summary()
        self.assertIsNone(summary['invalid_reason'])  # not a recorder fault
        self.assertEqual(summary['counts']['reports_emitted'], 0)
        self.assertEqual(summary['counts']['over_budget_groups'], 1)
        self.assertTrue(summary['valid'])


if __name__ == '__main__':
    unittest.main()
