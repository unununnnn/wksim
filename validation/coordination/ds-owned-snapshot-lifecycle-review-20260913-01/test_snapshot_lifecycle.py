"""Adversarial pure-fixture tests for the owned-scheduling snapshot lifecycle.

Run:  python -B validation/coordination/ds-owned-snapshot-lifecycle-review-20260913-01/test_snapshot_lifecycle.py
Exit 0 = the recorded v2 gap holds and the v3 candidate satisfies its required
properties. Only reads the authors' files; writes nothing outside this directory.

The tests do not assert that two arbitrary callbacks fire in some order. They assert
that every cited line still holds its verbatim text, then replay the runner's real
success and exception control flow, including the runner's own explicit model close
and its cleanup_children finally block.
"""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

import lifecycle_fixture as fixture
from lifecycle_fixture import Engine

LIFECYCLE_EVENTS = ('stop_action', 'model_close', 'model_stdin_close',
                    'cleanup_children', 'exitstack_unwind')


class AnchorIntegrity(unittest.TestCase):
    """Every cited line must still hold its text, or the fixture proves nothing."""

    def test_every_cited_line_matches(self):
        wrong = {key: fixture.anchor_text(key)
                 for key, ok in fixture.anchors_verified().items() if not ok}
        self.assertEqual(wrong, {}, 'cited source lines drifted')

    def test_v2_wiring_sites(self):
        self.assertEqual(fixture.anchor_text('v2_after_registration'),
                         'resources.callback(owned_snapshot_after)')
        self.assertEqual(fixture.anchor_text('v2_model_stdin_close'),
                         'child.stdin.close(); child.wait(timeout=3)')
        self.assertEqual(fixture.anchor_text('v2_finally_cleanup'),
                         'cleanup_children(result, children, child_specs,')

    def test_v3_wiring_sites(self):
        self.assertEqual(fixture.anchor_text('v3_success_after'),
                         'owned_snapshot_after_once()')
        self.assertEqual(fixture.anchor_text('v3_after_registration'),
                         'resources.callback(owned_snapshot_after_once)')
        self.assertEqual(fixture.anchor_text('v3_once_guard'),
                         "if meta.get('after_attempted'):")
        self.assertIn('_validated', fixture.anchor_text('v3_validated_flag'))
        self.assertIn('_validated', fixture.anchor_text('v3_refresh_validated'))

    def test_registration_is_inside_the_with_block_and_before_the_close(self):
        for variant, registration, open_key, close_key, cleanup_key in (
                ('v2', 'v2_after_registration', 'v2_exitstack_open',
                 'v2_model_stdin_close', 'v2_finally_cleanup'),
                ('v3', 'v3_after_registration', 'v3_exitstack_open',
                 'v3_model_stdin_close', 'v3_finally_cleanup')):
            path, line, _ = fixture.ANCHORS[registration]
            open_path, open_line, _ = fixture.ANCHORS[open_key]
            self.assertEqual(path, open_path, variant)
            self.assertLess(open_line, line, variant)
            self.assertLess(line, fixture.ANCHORS[close_key][1], variant)
            self.assertLess(line, fixture.ANCHORS[cleanup_key][1], variant)

    def test_v3_success_after_call_precedes_stop_and_close(self):
        after_line = fixture.ANCHORS['v3_success_after'][1]
        self.assertLess(after_line, fixture.ANCHORS['v3_stop_action'][1])
        self.assertLess(after_line, fixture.ANCHORS['v3_model_close'][1])
        self.assertLess(after_line, fixture.ANCHORS['v3_finally_cleanup'][1])

    def test_helper_pin_matches_the_candidate_constant(self):
        self.assertEqual(hashlib.sha256(fixture.HELPER.read_bytes()).hexdigest(),
                         fixture.HELPER_PIN)
        for candidate in (fixture.V2, fixture.V3):
            self.assertIn(fixture.HELPER_PIN, candidate.read_text(encoding='utf-8',
                                                                  errors='replace'))


class BaselineIsNotTheDefect(unittest.TestCase):
    """The unmodified runner has no after capture; the defect is in the candidates."""

    def test_baseline_has_no_owned_snapshot_after(self):
        text = fixture.BASELINE.read_text(encoding='utf-8', errors='replace')
        self.assertNotIn('owned_snapshot_after', text)
        self.assertNotIn('capture_owned_scheduling', text)

    def test_v1_and_v2_registered_after_the_same_way(self):
        for path in (fixture.V1, fixture.V2):
            text = path.read_text(encoding='utf-8', errors='replace')
            self.assertIn('resources.callback(owned_snapshot_after)', text)


class SuccessBranch(unittest.TestCase):
    """v2: the after capture cannot run until the with-block unwinds."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.live = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_v2_after_runs_after_the_model_closed(self):
        engine = Engine('v2', live=self.live)
        engine.run()
        # by the time the ExitStack unwinds, the explicit model close already happened
        self.assertEqual(engine.before_after(), ['stop_action', 'model_close'])
        self.assertIn('cleanup_children', engine.after_after())
        after = engine.first('after_capture')
        # the gap: the capture is reached only after stop and after the model's own
        # stdin.close()/wait() teardown; cleanup_children follows it in the finally block
        for name in ('stop_action', 'model_close', 'model_stdin_close'):
            self.assertGreater(after['seq'], engine.first(name)['seq'], name)
        self.assertLess(after['seq'], engine.first('cleanup_children')['seq'])
        self.assertEqual(engine.count('after_capture'), 1)
        self.assertEqual(engine.count('model_stdin_close'), 2)

    def test_v2_after_runs_after_group_cleanup_and_worker_retirement(self):
        engine = Engine('v2', live=self.live)
        engine.run()
        after = engine.first('after_capture')
        self.assertLess(after['seq'], engine.first('cleanup_children')['seq'])
        self.assertLess(after['seq'], engine.first('retire_stdin_close')['seq'])

    def test_every_v2_event_is_anchored_to_a_real_line(self):
        engine = Engine('v2', live=self.live)
        engine.run()
        for event in engine.events:
            if event['source'] is not None:
                self.assertIsInstance(event['line'], int)
                self.assertTrue(fixture.anchors_verified()[event['source']])

    def test_v2_capture_is_adopted_but_the_flight_is_not_promoted(self):
        engine = Engine('v2', live=self.live)
        result = engine.run()
        self.assertEqual(result['status'], 'observed')
        self.assertIs(result['owned_scheduling']['full_acceptance'], False)
        self.assertIsNotNone(result['owned_scheduling']['after'])


class ExceptionBranch(unittest.TestCase):
    """v2: the only backstop is the same unwind path, still after the model close."""

    def test_v2_business_error_capture_is_still_only_on_the_unwind(self):
        """A business error does capture, but only while the with-block unwinds."""
        engine = Engine('v2')
        engine.run(business_error=RuntimeError('independent model truth failed'))
        self.assertEqual(engine.count('after_capture'), 1)
        after = engine.first('after_capture')
        self.assertGreater(after['seq'], engine.first('after_registered')['seq'])
        self.assertLess(after['seq'], engine.first('exception_caught')['seq'])
        self.assertLess(after['seq'], engine.first('cleanup_children')['seq'])
        self.assertEqual(engine.result['status'], 'failed')

    def test_v2_after_captures_after_the_close_when_the_close_is_what_failed(self):
        """The sharpest case: the model close itself raised, the capture follows it."""
        engine = Engine('v2', close_error=RuntimeError('Model did not close normally'))
        engine.run()
        self.assertEqual(engine.count('after_capture'), 1)
        after = engine.first('after_capture')
        self.assertGreater(after['seq'], engine.first('model_stdin_close')['seq'])
        self.assertLess(after['seq'], engine.first('exception_caught')['seq'])
        self.assertLess(after['seq'], engine.first('cleanup_children')['seq'])

    def test_connect_failure_fabricates_no_after_capture(self):
        for variant in ('v2', 'v3'):
            engine = Engine(variant)
            engine.run(connect=False)
            self.assertEqual(engine.count('after_capture'), 0, variant)
            self.assertEqual(engine.count('after_capture_call'), 0, variant)
            self.assertEqual(engine.count('after_skipped_unconnected'), 1 if variant == 'v3' else 0,
                             variant)
            self.assertIsNone(engine.result['owned_scheduling']['after'])
            self.assertIsNone(engine.result['owned_scheduling'].get('after_error'))
            self.assertIsNone(engine.result['owned_scheduling'].get('after_attempted'))

    def test_no_variant_ever_runs_after_twice(self):
        for variant in ('v1', 'v2', 'v3'):
            for kwargs in ({}, {'business_error': RuntimeError('x')},
                           {'pause_complete': True}, {'connect': False}):
                engine = Engine(variant)
                engine.run(**kwargs)
                self.assertLessEqual(engine.count('after_capture'), 1, (variant, kwargs))


class V3Requirements(unittest.TestCase):
    """The properties A's v3 must have."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.live = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_v3_success_after_precedes_stop_cleanup_and_model_close(self):
        engine = Engine('v3', live=self.live)
        engine.run()
        self.assertEqual(engine.before_after(), [])
        after = engine.first('after_capture')
        for name in LIFECYCLE_EVENTS:
            self.assertLess(after['seq'], engine.first(name)['seq'], name)
        self.assertEqual(engine.after_attempts, 1)
        self.assertEqual(engine.after_validations, 1)
        self.assertEqual(engine.result['status'], 'observed')

    def test_v3_after_kept_after_the_stop_request_would_fail(self):
        engine = Engine('v3', live=self.live, after_mode='after-stop')
        engine.run()
        self.assertEqual(engine.before_after(), ['stop_action'])
        self.assertIn('model_close', engine.after_after())

    def test_v3_backstop_never_duplicates_the_success_capture(self):
        # the after capture already ran; the model then fails to close normally
        engine = Engine('v3', live=self.live,
                        close_error=RuntimeError('Model did not close normally'))
        engine.run()
        self.assertEqual(engine.after_attempts, 1)
        self.assertEqual(engine.after_validations, 1)
        self.assertEqual(engine.count('after_skipped_once'), 1)
        self.assertEqual(engine.result['status'], 'failed')

    def test_v3_failed_after_capture_is_attempted_once_and_never_adopted(self):
        engine = Engine('v3', live=self.live,
                        capture_error=ValueError('targets file differs from history'))
        result = engine.run()
        self.assertEqual(engine.after_attempts, 1)
        self.assertEqual(engine.after_validations, 0)
        self.assertEqual(engine.count('after_skipped_once'), 1)
        self.assertIsNotNone(result['owned_scheduling'].get('after_error'))
        self.assertFalse(engine.after_adopted_by_refresh)
        self.assertIsNone(result['owned_scheduling'].get('after_validated'))

    def test_v3_before_capture_failure_does_not_suppress_the_after_capture(self):
        engine = Engine('v3', live=self.live, fail_before_capture=True)
        result = engine.run()
        self.assertEqual(engine.after_attempts, 1)
        self.assertEqual(engine.after_validations, 1)
        self.assertIsNotNone(result['owned_scheduling'].get('before_error'))
        self.assertIsNotNone(result['owned_scheduling']['after'])

    def test_v3_boot_change_neither_writes_nor_validates_an_after_capture(self):
        engine = Engine('v3', live=self.live, boot_changed=True)
        result = engine.run()
        self.assertEqual(engine.after_validations, 0)
        self.assertIsNone(result['owned_scheduling'].get('after'))
        self.assertIn('boot changed', result['owned_scheduling'].get('after_error', ''))


class CaptureFileAcceptance(unittest.TestCase):
    """Is a failed or wrong-phase capture file re-designated as validated?"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.live = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_stale_after(self, boot='boot-OLD', phase='after'):
        stale = self.live / 'owned-scheduling-after.json'
        stale.write_text(json.dumps(dict(
            schema='wksim.owned-scheduling-snapshot.v1', phase=phase,
            host={'boot_id': boot})) + '\n', encoding='utf-8')
        return stale

    def test_v2_adopts_a_wrong_phase_file_as_after(self):
        engine = Engine('v2', live=self.live, wrong_phase='before')
        result = engine.run()
        adopted = result['owned_scheduling']['after']
        self.assertIsNotNone(adopted)
        self.assertTrue(engine.after_adopted_by_refresh)
        document = json.loads((self.live / adopted['file']).read_text(encoding='utf-8'))
        self.assertEqual(document['phase'], 'before')

    def test_v2_adopts_a_stale_file_left_by_a_failed_capture(self):
        stale = self.write_stale_after()
        engine = Engine('v2', live=self.live,
                        capture_error=ValueError('targets file differs from history'))
        result = engine.run()
        self.assertIsNotNone(result['owned_scheduling'].get('after_error'))
        self.assertIsNotNone(result['owned_scheduling']['after'])
        self.assertTrue(engine.after_adopted_by_refresh)
        self.assertEqual(json.loads(stale.read_text(encoding='utf-8'))['host']['boot_id'],
                         'boot-OLD')

    def test_v3_legacy_refresh_still_adopts_the_stale_file(self):
        """Isolates the refresh bug from the ordering fix."""
        self.write_stale_after()
        engine = Engine('v3-legacy-refresh', live=self.live,
                        capture_error=ValueError('targets file differs from history'))
        result = engine.run()
        self.assertTrue(engine.after_adopted_by_refresh)
        self.assertEqual(result['owned_scheduling']['after']['file'],
                         'owned-scheduling-after.json')

    def test_v3_trusts_the_flag_rather_than_re_reading_the_file(self):
        """The refresh never re-opens the capture file; it presents name+hash+flag.

        v3 is therefore correct on this point only because the caller passes the right
        phase to the helper -- the flag, not the file contents, is what the metadata
        refresh re-validates.
        """
        engine = Engine('v3', live=self.live)
        result = engine.run()
        after = result['owned_scheduling']['after']
        self.assertIs(after['validated'], True)
        self.assertNotIn('after_validated', after)
        document = json.loads((self.live / after['file']).read_text(encoding='utf-8'))
        self.assertEqual(document['phase'], 'after')
        # the refresh looked up the pinned boot only through the flag, not the file
        looked_up = [event for event in engine.events
                     if event['event'] in ('refresh_validated', 'refresh_raw_note',
                                           'refresh_missing')]
        self.assertEqual([event['event'] for event in looked_up],
                         ['refresh_validated', 'refresh_validated'])

    def test_v3_never_re_labels_a_failed_capture_file_as_after(self):
        self.write_stale_after()
        engine = Engine('v3', live=self.live, stale_file=True,
                        capture_error=ValueError('targets file differs from history'))
        result = engine.run()
        self.assertEqual(engine.after_validations, 0)
        self.assertFalse(engine.after_adopted_by_refresh)
        after = result['owned_scheduling'].get('after')
        self.assertIsNotNone(after)
        self.assertIs(after['validated'], False)
        self.assertIsNone(result['owned_scheduling'].get('after_validated'))

    def test_v3_validated_capture_is_presented_with_its_hash(self):
        engine = Engine('v3', live=self.live)
        result = engine.run()
        after = result['owned_scheduling']['after']
        self.assertIs(after['validated'], True)
        path = self.live / after['file']
        self.assertEqual(after['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_v3_internal_bookkeeping_flags_leak_into_the_report(self):
        """meta.update(refreshed) cannot remove the internal flags; they stay visible."""
        engine = Engine('v3', live=self.live)
        result = engine.run()
        meta = result['owned_scheduling']
        self.assertIn('after_attempted', meta)
        self.assertIs(meta['after_validated'], True)  # True, so the refresh error branch cannot fire


def dump_traces(path):
    """Write the real event traces so a reviewer can read the order, not just trust it."""
    scenarios = [
        ('v2-success', Engine('v2'), {}),
        ('v2-after-capture-failed',
         Engine('v2', capture_error=ValueError('targets file differs from history')), {}),
        ('v2-business-error', Engine('v2'), dict(business_error=RuntimeError('truth bounds'))),
        ('v2-connect-failed', Engine('v2'), dict(connect=False)),
        ('v3-success', Engine('v3'), {}),
        ('v3-model-close-error-once-guard',
         Engine('v3', close_error=RuntimeError('Model did not close normally')), {}),
        ('v3-connect-failed', Engine('v3'), dict(connect=False)),
    ]
    lines = []
    for name, engine, kwargs in scenarios:
        engine.run(**kwargs)
        lines.append(dict(scenario=name, order=engine.order(),
                          before_after=engine.before_after(),
                          after_after=engine.after_after(),
                          after_attempts=engine.after_attempts,
                          after_validations=engine.after_validations,
                          flight_status=engine.result['status'],
                          meta={key: value for key, value
                                in engine.result['owned_scheduling'].items()
                                if key in ('after', 'after_error', 'after_attempted',
                                           'after_validated', 'before', 'before_error')}))
        lines.append(dict(scenario=name + '/events', events=engine.events))
    Path(path).write_text('\n'.join(json.dumps(line, sort_keys=True) for line in lines) + '\n',
                          encoding='utf-8')
    return lines


if __name__ == '__main__':
    unittest.main(verbosity=2)
