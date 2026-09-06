"""Offline checks of the HTTP acceptance observer, never browser/flight proof."""
from copy import deepcopy
import unittest

from tools.validate_operator_http import ACTION_FIELDS, action_event, confirmed_action


class OperatorLifecycleObserverTests(unittest.TestCase):
    def setUp(self):
        self.flight = dict(id='job-a', run_id='run-a', kind='flight', status='running', live=dict(
            freshness=dict(status='live'), action_offer=dict(version=1, mission_id='a' * 32,
            action_token='b' * 32, control_epoch='c' * 32, native_generation=2, allowed_actions=['pause'])))
        self.body = {key: self.flight['live']['action_offer'][key] for key in ACTION_FIELDS}
        self.body['action'] = 'pause'
        self.request = dict(version=1, run_id='run-a', request_id='d' * 32, **self.body)

    def test_reget_then_exact_post_without_new_identity_or_native_command(self):
        calls = []
        def api(path, body=None):
            calls.append((path, body))
            return deepcopy(self.flight) if body is None else dict(submitted=True, request=self.request)
        self.assertEqual(confirmed_action(api, self.flight, 'pause'), self.request)
        self.assertEqual(calls, [('/api/runs/job-a', None), ('/api/runs/job-a/mission-action', self.body)])

    def test_changed_offer_prevents_post_not_automatic_upgrade(self):
        changes = [lambda f: f.update(status='pass'), lambda f: f.update(run_id='old'),
                   lambda f: f['live']['freshness'].update(status='stale'),
                   lambda f: f['live']['action_offer'].update(allowed_actions=[])]
        changes += [lambda f, k=key: f['live']['action_offer'].update({k: 'changed'}) for key in ACTION_FIELDS]
        for change in changes:
            calls, latest = [], deepcopy(self.flight)
            change(latest)
            def api(path, body=None):
                calls.append((path, body))
                return latest
            with self.subTest(change=change), self.assertRaises(ValueError):
                confirmed_action(api, self.flight, 'pause')
            self.assertEqual(calls, [('/api/runs/job-a', None)])

    def test_mismatched_response_is_unknown_and_never_retried(self):
        calls = []
        def api(path, body=None):
            calls.append((path, body))
            return deepcopy(self.flight) if body is None else dict(submitted=True,
                request=dict(self.request, request_id='wrong'))
        with self.assertRaisesRegex(ValueError, 'outcome unknown'):
            confirmed_action(api, self.flight, 'pause')
        self.assertEqual(len(calls), 2)

    def test_feedback_requires_outer_scope_inner_request_and_correct_stream(self):
        event = dict(event='mission_paused', run_id='run-a', mission_id='a' * 32,
                     control_epoch='c' * 32, native_generation=2,
                     pause=dict(pause_request=self.request))
        self.flight['live']['events'] = [dict(stream='mission', payload=event)]
        self.assertEqual(action_event(self.flight, self.request, 'mission_paused'), event)
        for key in ('run_id', 'mission_id', 'control_epoch', 'native_generation', 'event'):
            bad = deepcopy(event)
            bad[key] = 'wrong'
            self.flight['live']['events'] = [dict(stream='mission', payload=bad)]
            self.assertIsNone(action_event(self.flight, self.request, 'mission_paused'))
        self.flight['live']['events'] = [dict(stream='prometheus', payload=event)]
        self.assertIsNone(action_event(self.flight, self.request, 'mission_paused'))
        bad = deepcopy(event)
        bad['pause']['pause_request']['request_id'] = 'e' * 32
        self.flight['live']['mission'] = bad
        self.assertIsNone(action_event(self.flight, self.request, 'mission_paused'))
        self.flight['live']['mission'] = event
        self.assertEqual(action_event(self.flight, self.request, 'mission_paused'), event)


if __name__ == '__main__':
    unittest.main()
