"""Small corruption checks for product-specific raw lifecycle adaptation."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_joint_product import lifecycle
from audit_joint_product_lifecycle import verify_no_task_replay, verify_reset_action_isolation


class ProductAuditCorruption(unittest.TestCase):
    def check(self, mutate=None):
        message = dict(run_id='run', scene_epoch='epoch', tick=4, time_ns=4000000,
                       phase='paused', lease_seconds=.5)
        data = json.dumps(message).encode() + b'\0'
        rows = [dict(kind='permission', epoch='epoch', tick=4, phase='paused', message=message,
                     cdr_hex=(b'\0\1\0\0' + struct.pack('<I', len(data)) + data).hex()),
                dict(kind='paused_clock', epoch='epoch', tick=4, phase='paused',
                     time_ns=4000000, publication=6)]
        if mutate:
            mutate(rows)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'scene-lifecycle.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            return lifecycle(directory, 'epoch', 4, 6, 'run')

    def test_retained_raw_permission(self):
        self.assertEqual(self.check(), dict(permissions=1, clock_republications=1))

    def test_summary_cannot_override_raw_permission(self):
        with self.assertRaisesRegex(ValueError, 'Raw permission differs'):
            self.check(lambda rows: rows[0]['message'].update(lease_seconds=5))

    def test_clock_replay_cannot_count_as_progress(self):
        with self.assertRaisesRegex(ValueError, 'fabricated'):
            self.check(lambda rows: rows[1].update(time_ns=5000000))

    def test_missing_raw_republication_fails(self):
        with self.assertRaisesRegex(ValueError, 'Missing raw'):
            self.check(lambda rows: rows.pop())

    def test_reset_receipts_are_epoch_scoped_and_rejections_are_explicit(self):
        old_epoch, new_epoch = 'a' * 32, 'b' * 32
        root = Path(tempfile.mkdtemp())
        try:
            (root / 'actions').mkdir()
            (root / 'action-results' / old_epoch).mkdir(parents=True)
            (root / 'action-results' / new_epoch).mkdir(parents=True)

            def row(epoch, command_id, action, token):
                request = dict(version=1, run_id='run', epoch=epoch,
                               command_id=command_id, action=action,
                               offer_token='offer-' + token, token=token)
                response = dict(version=1, run_id='run', epoch=epoch,
                                command_id=command_id, action=action,
                                token=token, state='completed')
                (root / 'actions' / f'{command_id:020d}-{token}.json').write_text(json.dumps(request))
                (root / 'action-results' / epoch / (token + '.json')).write_text(json.dumps(response))
                return dict(submitted=dict(request=request), response=response)

            old_start = row(old_epoch, 1, 'start-task', 'old-start')
            old_reset = row(old_epoch, 2, 'cold-reset', 'old-reset')
            new_stop = row(new_epoch, 3, 'stop', 'new-stop')
            retired_request = dict(version=1, run_id='run', epoch=old_epoch,
                                   command_id=1, action='start-task',
                                   offer_token='offer-old-start', token='stale')
            (root / 'actions' / '00000000000000000001-stale.json').write_text(
                json.dumps(retired_request))
            rejection = dict(state='rejected', reason='Foreign, retired or malformed joint request',
                             run_id='run', epoch=new_epoch, request=retired_request)
            (root / 'action-results' / new_epoch /
             'rejected-00000000000000000001-stale.json').write_text(json.dumps(rejection))
            retired_request_2 = dict(retired_request, token='stale-two')
            (root / 'actions' / '00000000000000000001-stale-two.json').write_text(
                json.dumps(retired_request_2))
            rejection_2 = dict(rejection, request=retired_request_2)
            (root / 'action-results' / new_epoch /
             'rejected-00000000000000000001-stale-two.json').write_text(json.dumps(rejection_2))
            flow = dict(actions=[old_start, old_reset, new_stop],
                        reset=dict(retired_request_rejection=rejection))
            self.assertEqual(verify_reset_action_isolation(root, flow, old_epoch, new_epoch),
                             dict(old_action_results=2, new_completions=1, retired_rejections=2))

            (root / 'action-results' / old_epoch / 'old-start.json').write_text(json.dumps(rejection))
            with self.assertRaisesRegex(ValueError, 'Retained action result differs'):
                verify_reset_action_isolation(root, flow, old_epoch, new_epoch)

            (root / 'action-results' / old_epoch / 'old-start.json').write_text(
                json.dumps(dict(version=1, run_id='run', epoch=old_epoch, command_id=1,
                                action='start-task', token='old-start', state='completed')))
            (root / 'actions' / '00000000000000000001-stale.json').unlink()
            with self.assertRaisesRegex(ValueError, 'Retired request action file'):
                verify_reset_action_isolation(root, flow, old_epoch, new_epoch)

            (root / 'actions' / '00000000000000000001-stale.json').write_text(
                json.dumps(dict(retired_request, action='stop')))
            with self.assertRaisesRegex(ValueError, 'Retired request action file'):
                verify_reset_action_isolation(root, flow, old_epoch, new_epoch)
            (root / 'actions' / '00000000000000000001-stale.json').write_text(
                json.dumps(retired_request))
            collision_request = dict(new_stop['submitted']['request'], token='old-start')
            collision_response = dict(new_stop['response'], token='old-start')
            (root / 'actions' / '00000000000000000003-old-start.json').write_text(
                json.dumps(collision_request))
            (root / 'action-results' / new_epoch / 'new-stop.json').unlink()
            (root / 'action-results' / new_epoch / 'old-start.json').write_text(
                json.dumps(collision_response))
            flow['actions'][-1] = dict(submitted=dict(request=collision_request),
                                       response=collision_response)
            with self.assertRaisesRegex(ValueError, 'reused across cold-reset epochs'):
                verify_reset_action_isolation(root, flow, old_epoch, new_epoch)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_reset_generation_with_task_files_or_events_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'tasks' / 'stale').mkdir(parents=True)
            (directory / 'tasks' / 'stale' / 'result.json').write_text('{}')
            ground = dict(tasks={}, run_id='run', epoch='b' * 32)
            with self.assertRaisesRegex(ValueError, 'task files'):
                verify_no_task_replay(directory, ground, {1: [], 2: []})

            (directory / 'tasks' / 'stale' / 'result.json').unlink()
            identity = dict(version=1, run_id='run', control_epoch='b' * 32,
                            event_id=1, emitted_monotonic_ns=1, emitted_unix_ns=1,
                            stack='px4', native_prefix='', position_yaw=False,
                            operation_clock='ros', communication_clock='monotonic')
            idle = [{**identity, 'event': 'started'},
                    {**identity, 'event': 'scene_native_sources_bound', 'event_id': 2,
                     'emitted_monotonic_ns': 2, 'emitted_unix_ns': 2,
                     'scene_epoch': 'b' * 32, 'native_endpoints': {'state': 'gid'}}]
            other_idle = [{**value, 'event_id': value['event_id'] + 100,
                           'emitted_monotonic_ns': value['emitted_monotonic_ns'] + 100,
                           'emitted_unix_ns': value['emitted_unix_ns'] + 100}
                          for value in idle]
            verify_no_task_replay(directory, ground, {1: idle, 2: other_idle})
            for event in ('command_accepted', 'task_started', 'unknown_replay'):
                with self.subTest(event=event), self.assertRaisesRegex(
                        ValueError, 'Unknown, task, replay or foreign'):
                    verify_no_task_replay(directory, ground,
                                          {1: [{**identity, 'event': event}], 2: list(idle)})
            with self.assertRaisesRegex(ValueError, 'Unknown, task, replay or foreign'):
                verify_no_task_replay(directory, ground, {
                    1: [{**identity, 'event': 'started', 'control_epoch': 'c' * 32}], 2: list(idle)})
            with self.assertRaisesRegex(ValueError, 'event order'):
                verify_no_task_replay(directory, ground, {1: list(reversed(idle)), 2: list(idle)})
            backwards = [dict(value) for value in idle]
            backwards[1]['emitted_monotonic_ns'] = 1
            backwards[1]['emitted_unix_ns'] = 1
            with self.assertRaisesRegex(ValueError, 'event order'):
                verify_no_task_replay(directory, ground, {1: backwards, 2: list(idle)})
            missing_started_field = [dict(value) for value in idle]
            del missing_started_field[0]['stack']
            with self.assertRaisesRegex(ValueError, 'startup identity'):
                verify_no_task_replay(directory, ground,
                                      {1: missing_started_field, 2: list(idle)})


if __name__ == '__main__':
    unittest.main()
