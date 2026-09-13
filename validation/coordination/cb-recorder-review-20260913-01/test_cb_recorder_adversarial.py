"""Independent adversarial regression tests for tools/group_work_timing.py.

Codebuddy-scope review (cb-recorder-review-20260913-01). Pure in-memory tests;
inputs are constructed directly or taken from the REAL captured fixture stream
(group-work-timing-integration-20260913/group-work-timing-fixture.json), never
rebuilt from expected output reports. Focus: hidden state growth, duplicates,
epoch/segment transitions, invalid census coverage, emitted/dropped accounting,
callback errors, finish file lifetime. No source edits; no flight/native/build.
"""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools import group_work_timing as gwt

FIXTURE = (ROOT / 'validation/coordination/group-work-timing-integration-20260913'
           / 'group-work-timing-fixture.json')

EPOCH = 'cb-adversarial'
WALL0 = 10_000_000_000
STAGE_WALLS = (100, 60, 40)


def cpu_row(tick, ws, epoch=EPOCH):
    return dict(kind='diagnostic_step_cpu_timing', epoch=epoch, tick=tick,
                wall_start_ns=ws, wall_end_ns=ws + sum(STAGE_WALLS),
                stages={name: dict(wall_ns=w, thread_cpu_ns=c)
                        for name, w, c in zip(gwt.STAGES, STAGE_WALLS, (40, 70, 10))},
                limitation='fixture')


def step_row(tick, epoch=EPOCH):
    return dict(kind='step', epoch=epoch, tick=tick, ap_source_frame=tick,
                px4_source_time_us=tick * 1000, model_ticks=4)


def start_row(P, segment, ideal, earliest, actual_start, rate=1.0, epoch=EPOCH):
    period = gwt.period_ns(rate)
    return dict(kind='rate_group_start', epoch=epoch, tick=P, segment_id=segment,
                request_id='config', requested_rate=rate, transition=False,
                lateness_ns=max(0, actual_start - ideal), start_tick=P, end_tick=P + 4,
                ideal_start_ns=ideal, ideal_end_ns=ideal + period,
                earliest_start_ns=earliest, actual_start_ns=actual_start)


def end_row(start):
    return dict(start) | dict(kind='rate_group_end', tick=start['end_tick'],
                              actual_end_ns=start['actual_start_ns'],
                              lateness_ns=0)


class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.reports = []
        self.rec = gwt.GroupWorkTiming(emit=self.reports.append)

    def feed(self, rows, rec=None):
        for row in rows:
            (rec or self.rec).observe(row)

    def simple_group(self, P, segment=1, ideal=WALL0, earliest=None, work=1_000):
        earliest = ideal if earliest is None else earliest
        start = start_row(P, segment, ideal, earliest, earliest)
        end = end_row(start)
        end['actual_end_ns'] = start['actual_start_ns'] + work
        end['lateness_ns'] = max(0, end['actual_end_ns'] - start['ideal_end_ns'])
        return [start] + [step_row(P + i) for i in range(1, 5)] + [end]

    # ---------------------------------------------------------- state growth
    def test_state_stays_bounded_under_floods(self):
        # 300 complete groups, then one open group flooded with junk rows.
        for index in range(300):
            work = 9_000_000 if index % 7 == 0 else 1_000
            self.feed(self.simple_group(index * 4, ideal=WALL0 + index * 4_000_000,
                                        earliest=WALL0 + index * 4_000_000, work=work))
        self.assertEqual(self.rec.counts['groups_complete'], 300)
        self.assertEqual(len(self.reports), 16)  # cap; rest dropped
        self.assertEqual(self.rec.counts['reports_dropped'],
                         sum(1 for i in range(300) if i % 7 == 0) - 16)
        # Open a group, complete its steps, then flood: extra steps and 100 bad rows.
        self.feed([start_row(1200, 1, WALL0 + 300 * 4_000_000,
                             WALL0 + 300 * 4_000_000, WALL0 + 300 * 4_000_000)]
                  + [step_row(1200 + i) for i in range(1, 5)])
        bad = cpu_row(1201, WALL0)
        bad['stages']['encode_send']['wall_ns'] = -1  # schema-level garbage
        for _ in range(100):
            self.rec.observe(dict(bad))
        for tick in range(1205, 1405):  # 200 steps past the open group
            self.rec.observe(step_row(tick))
        group = self.rec._current
        self.assertLessEqual(len(group['steps']), 4)
        self.assertEqual(len(group['cpu_rows']), 0)
        self.assertEqual(len(group['native_rows']), 0)
        self.assertEqual(self.rec.counts['diagnostic_errors'], 100)  # honest count
        self.assertLessEqual(len(self.rec._reasons), gwt.MAX_REASONS)  # bounded reasons
        summary = self.rec.finish()
        self.assertEqual(summary['counts']['groups_incomplete'], 1)
        self.assertIsNone(summary['unfinished_group'])

    # ------------------------------------------------------------- duplicates
    def test_duplicate_group_rows_rejected(self):
        rows = self.simple_group(0)
        self.feed(rows)
        self.assertEqual(self.rec.counts['groups_complete'], 1)
        self.rec.observe(rows[0])  # duplicate start: tick regresses
        self.rec.observe(rows[-1])  # duplicate end: orphan
        self.assertEqual(self.rec.counts['diagnostic_errors'], 2)
        self.assertEqual(self.rec.counts['groups_complete'], 1)
        self.assertEqual(len(self.reports), 0)

    def test_zero_length_work_group_is_normal(self):
        self.feed(self.simple_group(0, work=0))  # actual_end == actual_start
        self.assertEqual(self.rec.counts['groups_complete'], 1)
        self.assertEqual(self.rec.counts['over_budget_groups'], 0)
        self.assertEqual(self.reports, [])
        self.assertTrue(self.rec.summary()['valid'])

    # --------------------------------------------------- epoch and segments
    def test_ignored_kinds_do_not_bind_epoch(self):
        self.rec.observe(dict(kind='rate_request', epoch='foreign-epoch', tick=40,
                              request_id='config', requested_rate=0.5))
        self.assertIsNone(self.rec._epoch)  # not consumed: no binding, no error
        self.feed(self.simple_group(40))
        self.assertEqual(self.rec._epoch, EPOCH)
        self.assertEqual(self.rec.counts['diagnostic_errors'], 0)
        self.assertTrue(self.rec.summary()['valid'])

    def test_reanchor_same_tick_and_earliest_equation(self):
        self.feed(self.simple_group(0))  # segment 1 ends at tick 4
        # reanchor to segment 2 at the same boundary tick: earliest must == ideal
        ideal2 = WALL0 + 10_000_000
        self.feed(self.simple_group(4, segment=2, ideal=ideal2, earliest=ideal2))
        self.assertEqual(self.rec.counts['groups_complete'], 2)
        # reanchor with earliest != ideal is rejected
        self.rec.observe(start_row(8, 3, ideal2 + 10_000_000,
                                   ideal2 + 11_000_000, ideal2 + 11_000_000))
        self.assertEqual(self.rec.counts['diagnostic_errors'], 1)
        self.assertIn('reanchor', self.rec._reasons[-1])

    def test_group_after_incomplete_skips_continuity_but_summary_invalid(self):
        rows = self.simple_group(0)[:-2]  # open group, never ended
        self.feed(rows)
        # next start finalizes the incomplete group; its own earliest equation
        # is unverifiable (documented) and the whole diagnostic is invalid.
        self.feed(self.simple_group(4))
        counts = self.rec.summary()['counts']
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertEqual(counts['groups_complete'], 1)
        self.assertFalse(self.rec.summary()['valid'])

    def test_bad_rate_type_and_bad_start_tick_rejected(self):
        self.rec.observe(start_row(0, 1, WALL0, WALL0, WALL0, rate=1))  # int not float
        self.rec.observe(start_row(2, 1, WALL0, WALL0, WALL0))          # tick % 4 != 0
        self.assertEqual(self.rec.counts['diagnostic_errors'], 2)
        self.assertIsNone(self.rec._current)

    def test_missing_epoch_rejected(self):
        self.rec.observe(dict(kind='step', tick=1))
        self.assertEqual(self.rec.counts['diagnostic_errors'], 1)

    # ------------------------------------------------------- census coverage
    def test_census_group_without_native_rows_reports_empty_waits(self):
        rec = gwt.GroupWorkTiming(emit=self.reports.append, census=True)
        start = start_row(0, 1, WALL0, WALL0, WALL0, rate=1.0)
        rows = [start]
        for i in range(1, 5):
            rows.append(step_row(i))
            rows.append(cpu_row(i, WALL0 + i * 1000))
        end = end_row(start)
        end['actual_end_ns'] = WALL0 + 9_000_000
        end['lateness_ns'] = max(0, end['actual_end_ns'] - start['ideal_end_ns'])
        rows.append(end)
        for row in rows:
            rec.observe(row)
        self.assertEqual(len(self.reports), 1)
        self.assertEqual(self.reports[0]['visible_native_waits'], [])
        self.assertTrue(self.reports[0]['work_decomposition']['closes'])
        self.assertTrue(rec.summary()['valid'])

    def test_census_native_tick_without_cpu_row_rejected(self):
        rec = gwt.GroupWorkTiming(emit=self.reports.append, census=True)
        start = start_row(0, 1, WALL0, WALL0, WALL0, rate=1.0)
        rows = [start]
        for i in range(1, 5):
            rows.append(step_row(i))
            if i != 3:
                rows.append(cpu_row(i, WALL0 + i * 1000))
        # native row at tick 3 (no cpu row there), window inside the group span
        ws = WALL0 + 3 * 1000
        rows.insert(7, dict(kind='diagnostic_native_input_timing', epoch=EPOCH, tick=3,
                            ap_source_frame=3, px4_source_time_us=3000,
                            native_wait_wall_ns=10, limitation='fixture',
                            waits=[dict(stack='arducopter', wall_start_ns=ws + 160,
                                        wall_end_ns=ws + 170, wall_ns=10,
                                        thread_cpu_ns=2, ap_frame=3)]))
        end = end_row(start)
        end['actual_end_ns'] = WALL0 + 9_000_000
        end['lateness_ns'] = max(0, end['actual_end_ns'] - start['ideal_end_ns'])
        rows.append(end)
        for row in rows:
            rec.observe(row)
        self.assertEqual(self.reports, [])
        self.assertTrue(any('census group lacks the cpu row' in r for r in rec._reasons))
        self.assertFalse(rec.summary()['valid'])

    def test_cpu_window_past_actual_end_rejected_at_group_end(self):
        start = start_row(0, 1, WALL0, WALL0, WALL0)
        rows = [start, step_row(1)]
        late = cpu_row(1, WALL0 + 1000)
        late['wall_start_ns'] = WALL0 + 500
        late['wall_end_ns'] = WALL0 + 500 + sum(STAGE_WALLS)
        rows += [late, step_row(2), step_row(3), step_row(4)]
        end = end_row(start)
        end['actual_end_ns'] = WALL0 + 600  # inside the cpu window
        end['lateness_ns'] = 0
        rows.append(end)
        self.feed(rows)
        counts = self.rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 1)
        self.assertEqual(counts['groups_incomplete'], 1)
        self.assertIn('outside group span', self.rec._reasons[-1])

    # -------------------------------------------------- accounting/callbacks
    def test_emit_failure_keeps_accounting_honest_and_recorder_live(self):
        calls = []
        state = {'fail': True}

        def flaky(report):
            calls.append(report['start_tick'])
            if state['fail']:
                raise OSError('diagnostic file write failed')

        rec = gwt.GroupWorkTiming(emit=flaky)
        rows = self.simple_group(0, work=9_000_000)
        for row in rows[:-1]:
            self.assertTrue(rec.observe(row))
        with self.assertRaises(OSError):
            rec.observe(rows[-1])  # caller callback error propagates unchanged
        self.assertEqual(rec.counts['over_budget_groups'], 1)
        self.assertEqual(rec.counts['reports_emitted'], 0)   # failure not counted
        self.assertEqual(rec.counts['reports_dropped'], 0)
        self.assertFalse(rec.invalid)                        # caller's error, not a fault
        state['fail'] = False
        self.feed(self.simple_group(4, ideal=WALL0 + 4_000_000,
                                    earliest=WALL0 + 4_000_000, work=9_000_000), rec=rec)
        self.assertEqual(rec.counts['reports_emitted'], 1)
        self.assertEqual(calls, [0, 4])
        self.assertTrue(rec.summary()['valid'])

    # ------------------------------------------------------- finish lifetime
    def test_finish_never_emits_and_is_idempotent(self):
        calls = []
        rec = gwt.GroupWorkTiming(emit=calls.append)
        # Open a group whose partial data would be over-budget if it ever ended.
        self.feed([start_row(0, 1, WALL0, WALL0, WALL0)] + [step_row(i) for i in (1, 2)],
                  rec=rec)
        first = rec.finish()
        second = rec.finish()
        self.assertEqual(calls, [])  # finish never writes through the callback
        self.assertEqual(first['counts']['groups_incomplete'], 1)
        self.assertEqual(second['counts']['groups_incomplete'], 1)  # no double count
        self.assertIsNone(second['unfinished_group'])

    def test_malformed_rows_rejected_without_tainting_group(self):
        start = start_row(0, 1, WALL0, WALL0, WALL0)
        rows = [start, step_row(1)]
        bad_native = dict(kind='diagnostic_native_input_timing', epoch=EPOCH, tick=1,
                          ap_source_frame=1, px4_source_time_us=1000,
                          native_wait_wall_ns=99, limitation='fixture',
                          waits=[dict(stack='arducopter', wall_start_ns=WALL0 + 160,
                                      wall_end_ns=WALL0 + 170, wall_ns=10,
                                      thread_cpu_ns=2, ap_frame=1)])  # sum mismatch
        bad_cpu = cpu_row(1, WALL0 + 1000)
        del bad_cpu['stages']['encode_send']  # missing stage
        rows += [bad_native, bad_cpu, step_row(2), step_row(3), step_row(4)]
        rows.append(end_row(start))
        self.feed(rows)
        counts = self.rec.summary()['counts']
        self.assertEqual(counts['diagnostic_errors'], 2)
        self.assertEqual(counts['groups_complete'], 1)  # group itself was clean
        self.assertEqual(counts['groups_incomplete'], 0)

    # ------------------------------------- real captured fixture through the
    # recorder directly (inputs are the actual stream, not report-derived)
    def test_real_fixture_census_and_sampled_streams(self):
        fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        for mode, expect_report in (('census_true', True), ('census_false', False)):
            with self.subTest(mode=mode):
                run = fixture['runs'][mode]
                reports = []
                rec = gwt.GroupWorkTiming(emit=reports.append, census=True)
                for row in run['rate_rows'][:-1]:
                    rec.observe(row)
                for row in run['wire']:
                    rec.observe(row)
                rec.observe(run['rate_rows'][-1])
                summary = rec.finish()
                if expect_report:
                    self.assertEqual(len(reports), 1)
                    self.assertEqual(reports[0]['work_ns'], run['work_ns'])
                    self.assertTrue(summary['valid'])
                else:  # sampled stream into a census recorder must not decompose
                    self.assertEqual(reports, [])
                    self.assertFalse(summary['valid'])
                    self.assertTrue(any('census group has' in r for r in summary['reasons']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
