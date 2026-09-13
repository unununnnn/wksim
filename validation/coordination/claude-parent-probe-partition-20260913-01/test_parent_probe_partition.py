"""Tests for analyze_parent_probe_partition.py: synthetic boundaries + real archive.

Synthetic streams are built directly (never reconstructed from analyzer output).
The real-archive test pins counters/totals observed from the retained 0fsmugd1
stream as regression values. Pure stdlib; no native/model/ROS/MATLAB.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_parent_probe_partition as app  # noqa: E402

ARCHIVE = HERE.parents[2] / 'validation/33-formal-promotion/spin-v2-0fsmugd1'
EPOCH = 'partition-test-epoch'
WALL0 = 1_000_000_000
PERIOD = 8_000_000  # rate 0.5


def probe_row(tick, outcome='started', entry=None, health_end=None, terminal=None,
              ideal=None, earliest=None, loop=0, sleep=0, final=0, segment=1):
    entry = entry if entry is not None else WALL0
    health_end = health_end if health_end is not None else entry
    terminal = terminal if terminal is not None else health_end
    observed = terminal - entry
    return dict(kind='rate_timing_probe', epoch=EPOCH, tick=tick, outcome=outcome,
                start_tick=tick, end_tick=tick + 4, segment_id=segment,
                entry_ns=entry, initial_health_end_ns=health_end, terminal_ns=terminal,
                ideal_start_ns=ideal if ideal is not None else WALL0,
                earliest_start_ns=earliest if earliest is not None else WALL0,
                entry_to_initial_health_ns=health_end - entry,
                loop_health_ns=loop, loop_health_calls=0, sleep_requested_ns=sleep,
                sleep_elapsed_ns=sleep, sleep_calls=0, sleep_max_overshoot_ns=0,
                final_spin_other_ns=final, release_excess_ns=max(0, terminal - (earliest or WALL0)),
                observed_elapsed_ns=observed, phase_total_ns=observed)


def start_row(tick, ideal, earliest, actual, segment=1, rate=0.5):
    return dict(kind='rate_group_start', epoch=EPOCH, tick=tick, segment_id=segment,
                request_id='config', requested_rate=rate, transition=False,
                lateness_ns=max(0, actual - ideal), start_tick=tick, end_tick=tick + 4,
                ideal_start_ns=ideal, ideal_end_ns=ideal + int(4_000_000 / rate),
                earliest_start_ns=earliest, actual_start_ns=actual)


def end_row(start, actual_end):
    return dict(start) | dict(kind='rate_group_end', tick=start['end_tick'],
                              actual_end_ns=actual_end,
                              lateness_ns=max(0, actual_end - start['ideal_end_ns']))


class PartitionMathTests(unittest.TestCase):
    def test_prior_work_overruns_the_edge(self):
        # Eprev=1200 > R=1000: [R,S] pieces 200/100/100/600 close to S-R=1000.
        parts = app.partition_regions(1000, 2000, 1200, 1300, 1400)
        self.assertEqual(parts, dict(priorwork_over_ns=200, outside_begin_ns=100,
                                     initial_health_ns=100, remaining_begin_ns=600))

    def test_idle_gap_before_begin_entry(self):
        parts = app.partition_regions(1000, 2000, 500, 1100, 1200)
        self.assertEqual(parts, dict(priorwork_over_ns=0, outside_begin_ns=100,
                                     initial_health_ns=100, remaining_begin_ns=800))

    def test_entry_before_the_edge(self):
        # A<R<=H: only the post-edge part of initial health lies inside [R,S].
        parts = app.partition_regions(1000, 2000, 400, 600, 1500)
        self.assertEqual(parts, dict(priorwork_over_ns=0, outside_begin_ns=0,
                                     initial_health_ns=500, remaining_begin_ns=500))

    def test_health_done_before_the_edge(self):
        parts = app.partition_regions(1000, 2000, 100, 200, 300)
        self.assertEqual(parts, dict(priorwork_over_ns=0, outside_begin_ns=0,
                                     initial_health_ns=0, remaining_begin_ns=1000))

    def test_zero_wait_closes(self):
        parts = app.partition_regions(1000, 1000, 900, 950, 980)
        self.assertEqual(sum(parts.values()), 0)

    def test_chain_violation_rejected(self):
        with self.assertRaises(app.Rejected):
            app.partition_regions(1000, 2000, 1300, 1200, 1400)  # Eprev > A
        with self.assertRaises(app.Rejected):
            app.partition_regions(1000, 2000, 1100, 1200, 2500)  # H > S


class StreamTests(unittest.TestCase):
    def two_group_stream(self):
        ideal0 = WALL0
        actual0 = WALL0 + 100_000
        end0 = actual0 + 8_100_000             # Eprev = WALL0+8.2e6
        ideal1 = ideal0 + PERIOD
        earliest1 = max(ideal1, actual0 + PERIOD)   # R = WALL0+8.1e6
        actual1 = earliest1 + 500_000               # S = WALL0+8.6e6
        start0 = start_row(0, ideal0, ideal0, actual0)
        start1 = start_row(4, ideal1, earliest1, actual1)
        # physical chain holds: Eprev(8.2e6) <= A1(8.3e6) <= H1(8.31e6) <= S1(8.6e6)
        rows = [start0,
                probe_row(0, entry=ideal0 - 50_000, health_end=ideal0 + 20_000,
                          terminal=actual0, ideal=ideal0, earliest=ideal0,
                          sleep=30_000, final=actual0 - (ideal0 + 20_000) - 30_000),
                end_row(start0, end0),
                start1,
                probe_row(4, entry=earliest1 + 200_000, health_end=earliest1 + 210_000,
                          terminal=actual1, ideal=ideal1, earliest=earliest1,
                          loop=5_000, final=285_000),
                end_row(start1, actual1 + 2_000_000)]
        return rows, dict(end0=end0, earliest1=earliest1, actual1=actual1)

    def test_priorwork_attribution_only_same_segment_same_rate(self):
        rows, refs = self.two_group_stream()
        result = app.analyze(rows)
        self.assertEqual(result['groups_started'], 2)
        self.assertEqual(result['groups_with_priorwork_attribution'], 1)
        self.assertEqual(result['initial_groups'], 1)
        second = result['extremes']  # totals carry the attribution
        R = refs['earliest1']
        expected_over = max(0, min(refs['end0'], refs['actual1']) - R)
        self.assertEqual(result['partition_totals_ns']['priorwork_over_ns'], expected_over)
        self.assertGreater(expected_over, 0)  # group 0 overruns group 1's edge
        self.assertEqual(result['closure']['partition_sum_equals_S_minus_R_groups'], 2)
        self.assertEqual(result['closure']['aggregates_reconcile_with_begin_span_groups'], 2)

    def test_segment_change_blocks_priorwork_equivalence(self):
        rows, refs = self.two_group_stream()
        # Re-anchor: third group opens segment 2; earliest must equal its ideal.
        ideal2 = refs['actual1'] + 20_000_000
        start2 = start_row(8, ideal2, ideal2, ideal2, segment=2)
        rows += [start2,
                 probe_row(8, entry=ideal2, health_end=ideal2, terminal=ideal2,
                           ideal=ideal2, earliest=ideal2, segment=2),
                 end_row(start2, ideal2 + 1_000)]
        result = app.analyze(rows)
        self.assertEqual(result['initial_groups'], 2)
        self.assertEqual(result['groups_with_priorwork_attribution'], 1)

    def test_probe_terminal_must_equal_actual_start(self):
        rows, _ = self.two_group_stream()
        for row in rows:
            if row['kind'] == 'rate_timing_probe' and row['start_tick'] == 4:
                row['terminal_ns'] += 1
        with self.assertRaises(app.Rejected):
            app.analyze(rows)

    def test_phase_accounting_must_close(self):
        rows, _ = self.two_group_stream()
        for row in rows:
            if row['kind'] == 'rate_timing_probe' and row['start_tick'] == 0:
                row['final_spin_other_ns'] -= 1
        with self.assertRaises(app.Rejected):
            app.analyze(rows)

    def test_cross_epoch_rejected(self):
        rows, _ = self.two_group_stream()
        rows[-1]['epoch'] = 'other'
        with self.assertRaises(app.Rejected):
            app.analyze(rows)

    def test_nonstarted_attempt_reported_never_fabricated(self):
        rows, refs = self.two_group_stream()
        # A begin_group that raises leaves a probe sample with NO group start row.
        ideal2 = WALL0 + 16_000_000
        earliest2 = WALL0 + 16_600_000  # == max(ideal2, prior actual start + period)
        entry = earliest2 - 100_000
        terminal = earliest2 + 50_000   # crosses the edge by 50us
        # the failed check records its own rate_unmet row just before the raise
        rows.append(dict(kind='rate_unmet', epoch=EPOCH, tick=8,
                         lateness_ns=terminal - ideal2, completed_groups=2,
                         segment_id=1, reason='resource_insufficient'))
        rows.append(probe_row(8, outcome='rate_unmet', entry=entry,
                              health_end=entry + 5_000, terminal=terminal,
                              ideal=ideal2, earliest=earliest2, final=145_000))
        result = app.analyze(rows)
        self.assertEqual(result['groups_started'], 2)
        attempts = result['nonstarted_probe_attempts']
        self.assertEqual(len(attempts), 1)
        attempt = attempts[0]
        self.assertEqual(attempt['outcome'], 'rate_unmet')
        self.assertTrue(attempt['terminal_is_last_read_not_release'])
        self.assertTrue(attempt['crossed_release_edge'])
        self.assertEqual((attempt['entry_ns'], attempt['initial_health_end_ns'],
                          attempt['terminal_ns'], attempt['R_ns']),
                         (entry, entry + 5_000, terminal, earliest2))
        self.assertEqual(attempt['prior_group']['actual_end_ns'], refs['actual1'] + 2_000_000)
        self.assertEqual(attempt['priorwork_equivalence'], 'same segment, same fixed period')
        self.assertEqual(attempt['matched_rate_unmet'],
                         dict(tick=8, lateness_ns=terminal - ideal2,
                              completed_groups=2, reason='resource_insufficient'))
        part = attempt['partition_until_terminal']
        self.assertEqual(sum(v for v in part.values() if v is not None),
                         attempt['terminal_ns'] - attempt['R_ns'])

    def test_attempt_not_crossing_the_edge(self):
        rows, refs = self.two_group_stream()
        ideal2 = WALL0 + 16_000_000
        earliest2 = WALL0 + 16_600_000
        entry = earliest2 - 200_000
        terminal = earliest2 - 50_000  # check fired before the release edge
        rows.append(dict(kind='rate_unmet', epoch=EPOCH, tick=8,
                         lateness_ns=terminal - ideal2, completed_groups=2,
                         segment_id=1, reason='resource_insufficient'))
        rows.append(probe_row(8, outcome='rate_unmet', entry=entry,
                              health_end=entry + 10_000, terminal=terminal,
                              ideal=ideal2, earliest=earliest2, final=140_000))
        result = app.analyze(rows)
        attempt = result['nonstarted_probe_attempts'][0]
        self.assertFalse(attempt['crossed_release_edge'])
        self.assertEqual(attempt['partition_until_terminal']['remaining_begin_ns'], 0)

    def test_rate_unmet_attempt_requires_its_unmet_row(self):
        rows, refs = self.two_group_stream()
        ideal2 = WALL0 + 16_000_000
        earliest2 = WALL0 + 16_600_000
        entry = earliest2 - 100_000
        terminal = earliest2 + 50_000
        rows.append(probe_row(8, outcome='rate_unmet', entry=entry,
                              health_end=entry + 5_000, terminal=terminal,
                              ideal=ideal2, earliest=earliest2, final=145_000))
        with self.assertRaises(app.Rejected):
            app.analyze(rows)  # outcome rate_unmet but no rate_unmet row

    def test_started_probe_without_group_start_rejected(self):
        rows, _ = self.two_group_stream()
        rows.append(probe_row(8, outcome='started'))  # claims started, no start row
        with self.assertRaises(app.Rejected):
            app.analyze(rows)

    def test_nonstarted_probe_contradicting_a_start_row_rejected(self):
        rows, _ = self.two_group_stream()
        for row in rows:
            if row['kind'] == 'rate_timing_probe' and row['start_tick'] == 4:
                row['outcome'] = 'rate_unmet'
        with self.assertRaises(app.Rejected):
            app.analyze(rows)


class OrderedPassTests(unittest.TestCase):
    """The ordered invariant: one open group; start -> started probe -> end."""

    def _valid_stream(self):
        rows, refs = StreamTests().two_group_stream()
        return rows

    def test_start_while_open_rejected(self):
        rows = self._valid_stream()
        rows.insert(2, rows[0])  # second start before the first end
        with self.assertRaisesRegex(app.Rejected, 'still open'):
            app.analyze(rows)

    def test_end_without_open_rejected(self):
        rows = self._valid_stream()
        rows.pop(0)  # drop the first start
        with self.assertRaisesRegex(app.Rejected, 'without an open group'):
            app.analyze(rows)

    def test_end_before_its_probe_rejected(self):
        rows = self._valid_stream()
        # swap first probe and first end: start, end, probe
        rows[1], rows[2] = rows[2], rows[1]
        with self.assertRaisesRegex(app.Rejected, 'before its started probe'):
            app.analyze(rows)

    def test_duplicate_started_probe_rejected(self):
        rows = self._valid_stream()
        rows.insert(2, dict(rows[1]))  # probe twice inside the open group
        with self.assertRaisesRegex(app.Rejected, 'duplicate started probe'):
            app.analyze(rows)

    def test_nonstarted_attempt_while_open_rejected(self):
        rows = self._valid_stream()
        rows.insert(2, probe_row(4, outcome='rate_unmet', entry=WALL0,
                                 health_end=WALL0, terminal=WALL0))
        with self.assertRaisesRegex(app.Rejected, 'while a group is open'):
            app.analyze(rows)

    def test_unclosed_group_at_stream_end_rejected(self):
        rows = self._valid_stream()[:2]  # start+probe, no end
        with self.assertRaisesRegex(app.Rejected, 'ends with an open group'):
            app.analyze(rows)


REORDERED = HERE / 'uy9ov56b/rate-ends-to-tail.jsonl'
OLD_ACCEPT_ARTIFACT = HERE / 'uy9ov56b/reordered-accepted-by-a2e70f7c.json'


@unittest.skipUnless(REORDERED.is_file(), 'reordered real-data copy absent')
class RealReorderedNegativeTests(unittest.TestCase):
    def test_ends_to_tail_real_copy_rejected_now(self):
        rows = [json.loads(line) for line in REORDERED.read_text().splitlines() if line.strip()]
        with self.assertRaisesRegex(app.Rejected, 'still open'):
            app.analyze(rows)

    def test_old_validator_accepted_the_same_bytes(self):
        # Evidence artifact produced by analyzer SHA a2e70f7c (pre-ordering-fix)
        # on exactly these bytes; the gap being fixed is thereby pinned.
        old = json.loads(OLD_ACCEPT_ARTIFACT.read_text())
        self.assertEqual(old['status'], 'ok')
        self.assertEqual(old['identity']['rate_rows'], 67574)


@unittest.skipUnless((ARCHIVE / 'rate.jsonl.gz').is_file(), 'retained archive absent')
class RealArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity, cls.result = app.analyze_archive(ARCHIVE)

    def test_pinned_counters_and_closure(self):
        r = self.result
        self.assertEqual(r['groups_started'], 11737)
        self.assertEqual(r['groups_with_priorwork_attribution'], 11736)
        self.assertEqual(r['initial_groups'], 1)
        self.assertEqual(r['nonstarted_probe_attempts'], [])
        self.assertEqual(r['rate_unmet_rows'], [dict(tick=46988, lateness_ns=100158534,
                                                     completed_groups=11737)])
        self.assertEqual(r['closure'], dict(partition_sum_equals_S_minus_R_groups=11737,
                                            aggregates_reconcile_with_begin_span_groups=11737))

    def test_pinned_totals_and_extremes(self):
        self.assertEqual(self.result['partition_totals_ns'], dict(
            priorwork_over_ns=46023788, outside_begin_ns=5443826, initial_health_ns=3045020,
            remaining_begin_ns=41404171, pre_edge_begin_ns=42095295003, waited_ns=95916805))
        top = self.result['extremes']['waited'][0]
        self.assertEqual(top['start_tick'], 24388)
        self.assertEqual(top['partition']['priorwork_over_ns'], 9805258)

    def test_identity_binds_raw_and_sources(self):
        self.assertEqual(self.identity['rate_sha256'],
                         '8648d034453741f799e8a3348b1878d83287c2c1150dd2e3589fe4a678ecedec')
        self.assertIn('repo:Simulator/wksim_runtime/joint_rate.py', self.identity)
        self.assertIn('source__tools__run_joint_flight.py.txt', self.identity)

    def test_old_result_semantics_unchanged(self):
        # Every data key of the retained v1 result must deep-equal a fresh rerun;
        # only schema/analyzer_sha256/limitations text may differ (deliberate).
        old = json.loads((HERE / 'partition-result.json').read_text())
        _, new = app.analyze_archive(str(ARCHIVE))
        new_full = dict(schema=old['schema'], classification='diagnostic_only',
                        full_acceptance=False, purpose=old.get('purpose'),
                        analyzer_sha256=old['analyzer_sha256'])
        new_full.update(dict(status='ok', identity=self.identity, **new))
        new_full['limitations'] = old['limitations']

        def subset(a, b, path=''):
            diffs = []
            if isinstance(a, dict):
                if not isinstance(b, dict):
                    return [path or '<root>']
                for key, value in a.items():
                    if key not in b:
                        diffs.append(path + '/' + key + ' missing')
                    else:
                        diffs += subset(value, b[key], path + '/' + key)
            elif a != b:
                diffs.append(path)
            return diffs
        self.assertEqual(subset(old, new_full), [])

    def test_cli_exclusive_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'partition.json'
            self.assertEqual(app.main(['--archive', str(ARCHIVE), '--output', str(out)]), 0)
            written = json.loads(out.read_text())
            self.assertEqual(written['status'], 'ok')
            self.assertEqual(written['classification'], 'diagnostic_only')
            self.assertFalse(written['full_acceptance'])
            self.assertEqual(app.main(['--archive', str(ARCHIVE), '--output', str(out)]), 1)
            self.assertEqual(json.loads(out.read_text())['status'], 'ok')  # untouched


if __name__ == '__main__':
    unittest.main(verbosity=2)
