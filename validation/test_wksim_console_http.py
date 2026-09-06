"""Exercise real local HTTP boundaries; flight processes are never started."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Simulator.wksim_console import records
from Simulator.wksim_console.server import ConsoleServer
from Simulator.wksim_console.workspace import Workspace
from Simulator.wksim_runtime.mission_actions import ActionMailbox, request_action
from validation.test_wksim_console_records import session


class ConsoleHttpTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(Path(self.temp.name)/'console')
        self.handles = []
        self.server = ConsoleServer(self.workspace, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(2)
        self.server.server_close()
        for handle in self.handles:
            handle.returncode = 1
        self.workspace.close()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            result = connection.getresponse()
            data = result.read()
            return result.status, dict(result.getheaders()), data
        finally:
            connection.close()

    def post(self, path, value, **headers):
        return self.request('POST', path, json.dumps(value),
            {'Content-Type': 'application/json', 'X-Wksim-CSRF': self.server.csrf, **headers})

    def action_flight(self):
        """Only substitute process creation. HTTP, files and readers remain real."""
        def launch(argv, job, stdout_name):
            handle = SimpleNamespace(pid=4242, returncode=None)
            handle.poll = lambda: handle.returncode
            self.handles.append(handle)
            self.workspace.processes[job['id']] = handle
            job.update(status='running', pid=handle.pid)

        config = self.workspace.bootstrap()['defaults']['px4']
        with patch.object(self.workspace, '_launch', side_effect=launch):
            check = self.workspace.preflight(config)
            path = Path(check['directory']) / 'preflight.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"ok":true}', encoding='utf-8')
            self.handles[-1].returncode = 0
            deadline = time.monotonic() + 5
            while self.workspace.get_run(check['id'])['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(self.workspace.get_run(check['id'])['status'], 'pass')
            job = self.workspace.start(config, check['id'], False)
        self.directory = Path(job['directory'])
        self.directory.mkdir(parents=True, exist_ok=True)
        self.mission = dict(version=1, run_id=job['run_id'], mission_id='b' * 32,
                            action_token='c' * 32, control_epoch='a' * 32,
                            native_generation=2, state='running', allowed_actions=['pause'])
        self.put_mission()
        (self.directory / 'mission.jsonl').write_text('', encoding='utf-8')
        # The monitor and public request share this same reader. Establish real
        # cross-poll source advancement while excluding only monitor scheduling.
        with self.workspace.lock:
            reader = self.workspace.readers[job['id']]
            for sequence in (1, 2):
                row = session(sequence, 900000 + sequence, 10 + sequence,
                              run_id=job['run_id'], native_generation=2)
                row['message']['state'].update(armed=True, mode='OFFBOARD')
                row['message']['control'].update(control_state=2)
                with (self.directory / 'prometheus.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row) + '\n')
                self.workspace.jobs[job['id']]['live'] = reader.poll()
            self.assertEqual(self.workspace.jobs[job['id']]['live']['action_offer']['allowed_actions'], ['pause'])
        self.job = job
        self.action_path = '/api/runs/' + job['id'] + '/mission-action'
        self.body = {key: self.mission[key] for key in
                     ('mission_id', 'action_token', 'control_epoch', 'native_generation')}
        self.body['action'] = 'pause'
        return job

    def put_mission(self, **changes):
        (self.directory / 'mission-status.json').write_text(
            json.dumps(dict(self.mission, **changes)), encoding='utf-8')

    def assert_no_action_file(self):
        self.assertEqual(list(self.directory.glob('mission-action-*.json')), [])

    def test_mission_action_is_submission_not_completion_with_exact_audit(self):
        job = self.action_flight()
        with patch('subprocess.Popen', side_effect=AssertionError('command path reached')):
            status, _, raw = self.post(self.action_path, self.body)
            response = json.loads(raw)
            self.assertEqual(status, 200, response)
            self.assertTrue(response['submitted'])
            self.assertEqual(set(response), {'submitted', 'request'})
            self.assertEqual(json.loads(self.post(self.action_path, self.body)[2]), response)
        request = response['request']
        for key, value in self.body.items():
            self.assertEqual(request[key], value)
        self.assertEqual(request['run_id'], job['run_id'])
        mailbox = ActionMailbox(self.directory, job['run_id'], self.mission['mission_id'])
        self.assertEqual(mailbox.poll('c' * 32, 'a' * 32, 2, ['pause']), request)
        self.assertIsNone(mailbox.poll('c' * 32, 'a' * 32, 2, ['pause']))
        self.assertEqual(json.loads(self.request('GET', '/api/runs/' + job['id'])[2])['status'], 'running')
        self.assertEqual(json.loads((self.directory / 'mission-status.json').read_text())['state'], 'running')
        audit = (self.workspace.root / 'http-actions.jsonl').read_text(encoding='utf-8')
        self.assertNotIn(self.server.csrf, audit)
        actions = [json.loads(line) for line in audit.splitlines() if self.action_path in line]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]['request'], {k: v for k, v in request.items() if k != 'version'})

    def test_mission_action_requires_exact_body_and_current_csrf(self):
        self.action_flight()
        for body in ({k: v for k, v in self.body.items() if k != 'control_epoch'},
                     dict(self.body, extra=1), dict(self.body, native_generation=True),
                     dict(self.body, native_generation=2.0), dict(self.body, action='cancel'),
                     dict(self.body, action=['pause']), dict(self.body, mission_id='../bad')):
            with self.subTest(body=body):
                self.assertEqual(self.post(self.action_path, body)[0], 400)
                self.assert_no_action_file()
        self.assertEqual(self.post(self.action_path, self.body, **{'X-Wksim-CSRF':'old'})[0], 403)
        self.assertEqual(self.request('GET', self.action_path)[0], 404)
        self.assert_no_action_file()

    def test_mission_action_repolls_offer_instead_of_trusting_cached_catalog(self):
        job = self.action_flight()
        for change in (dict(mission_id='d' * 32), dict(action_token='e' * 32),
                       dict(control_epoch='f' * 32), dict(native_generation=3),
                       dict(allowed_actions=[]), dict(state='pausing')):
            with self.subTest(change=change):
                self.put_mission(**change)
                self.assertEqual(self.post(self.action_path, self.body)[0], 400)
                self.assert_no_action_file()
        self.put_mission()
        # No cross-host clock assumptions: age only the host's last observation.
        with self.workspace.lock:
            self.workspace.readers[job['id']].observed_at -= records.STALE_AFTER_S + 1
        self.assertEqual(self.post(self.action_path, self.body)[0], 400)
        self.assert_no_action_file()

    def test_mission_action_pins_confirmed_generation_across_file_read_race(self):
        self.action_flight()
        for change in (dict(control_epoch='d' * 32), dict(native_generation=3)):
            self.put_mission()
            def transition(*args, **kwargs):
                self.put_mission(**change)
                return request_action(*args, **kwargs)
            with self.subTest(change=change), patch(
                    'Simulator.wksim_console.workspace.request_action', side_effect=transition):
                code, _, raw = self.post(self.action_path, self.body)
                self.assertEqual(code, 400)
                self.assertIn('confirmed offer identity changed', json.loads(raw)['error'])
                self.assert_no_action_file()

    def test_mission_action_refuses_unowned_or_finished_jobs(self):
        job = self.action_flight()
        with self.workspace.lock:
            self.workspace.jobs[job['id']]['server_instance'] = 'old'
        self.assertEqual(self.post(self.action_path, self.body)[0], 400)
        with self.workspace.lock:
            self.workspace.jobs[job['id']]['server_instance'] = self.workspace.server_instance
            self.workspace.jobs[job['id']]['status'] = 'unowned'
        self.assertEqual(self.post(self.action_path, self.body)[0], 400)
        with self.workspace.lock:
            self.workspace.jobs[job['id']]['status'] = 'running'
            self.handles[-1].returncode = 0
        self.assertEqual(self.post(self.action_path, self.body)[0], 400)
        self.assert_no_action_file()

    def test_bootstrap_and_local_assets_are_no_store_no_cdn(self):
        code, headers, body = self.request('GET', '/api/bootstrap')
        bootstrap = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(bootstrap['csrf'], self.server.csrf)
        self.assertEqual(set(bootstrap['defaults']), {'px4', 'arducopter'})
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        for path in ('/', '/app.js', '/app.css'):
            self.assertEqual(self.request('GET', path)[0], 200)

    def test_host_origin_and_cross_site_are_rejected_even_for_bootstrap(self):
        for headers in ({'Host': 'evil.test'}, {'Origin': 'https://evil.test'},
                        {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'},
                        {'Sec-Fetch-Site': 'same-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET', '/api/bootstrap', headers=headers)[0], 403)

    def test_csrf_and_json_boundaries_do_not_call_flight(self):
        with patch.object(self.workspace, 'start', side_effect=AssertionError('flight reached')):
            self.assertEqual(self.request('POST', '/api/start', '{}', {'Content-Type':'application/json'})[0],403)
            self.assertEqual(self.post('/api/start', {}, Origin='https://evil.test')[0],403)
            for body in ('{"a":1,"a":2}', '{"a":NaN}', '[]', '{', ' ' * 65537):
                status = self.request('POST', '/api/start', body,
                    {'Content-Type':'application/json','X-Wksim-CSRF':self.server.csrf})[0]
                self.assertEqual(status,400)
            self.assertEqual(self.request('POST','/api/start','{}',
                {'Content-Type':'text/plain','X-Wksim-CSRF':self.server.csrf})[0],400)

    def test_arbitrary_files_unknown_fields_and_methods_are_rejected(self):
        for path in ('/../AGENTS.md', '/%2e%2e/AGENTS.md', '/api/runs/../../AGENTS.md', '/api/bootstrap?path=C:/'):
            self.assertIn(self.request('GET',path)[0],(400,404))
        self.assertEqual(self.request('OPTIONS','/api/start')[0],405)
        self.assertEqual(self.post('/api/preflight',dict(config={},command='echo hello'))[0],400)

    def test_save_reload_and_revision_conflict_with_auditable_hash(self):
        data = json.loads(self.request('GET','/api/bootstrap')[2])
        config = data['defaults']['px4']
        first = self.post('/api/configs', dict(name='px4-demo',config=config,expected_revision=None))
        self.assertEqual(first[0],200)
        saved=json.loads(first[2])
        refreshed=json.loads(self.request('GET','/api/bootstrap')[2])
        self.assertEqual(refreshed['configs'],[saved])
        self.assertEqual(saved['config'],config)
        self.assertEqual(self.post('/api/configs',dict(name='px4-demo',config=config,expected_revision=None))[0],400)
        audit=(self.workspace.root/'http-actions.jsonl').read_text(encoding='utf-8')
        self.assertIn(saved['revision'],audit)
        self.assertNotIn(self.server.csrf,audit)

    def test_shutdown_refusal_does_not_stop_server(self):
        with patch.object(self.workspace,'close',side_effect=ValueError('live owned flight')):
            status,_,body=self.post('/api/shutdown',{})
        self.assertEqual(status,400)
        self.assertIn('live owned flight',json.loads(body)['error'])
        self.assertEqual(self.request('GET','/api/bootstrap')[0],200)


if __name__ == '__main__':
    unittest.main()
