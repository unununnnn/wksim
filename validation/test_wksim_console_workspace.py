"""Workspace contract tests: real files/observer, inert handles, no WSL/FC/UE.

Run: D:/date/miniconda/python.exe -X utf8 -B -m unittest
     validation.test_wksim_console_workspace -v
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from Simulator.wksim_console.workspace import Workspace, decode


class Process:
    pid = 4242

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode


class OwnedView:
    """Inert ownership fixture; never constructs or starts a real UE view."""
    state = 'live'

    def poll(self):
        return {'state': self.state}

    def stop(self):
        self.state = 'stopped'


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'console'
        self.handles = {}
        self.launches = []
        self.launch_error = None

        def launch(owner, argv, job, stdout_name):
            self.launches.append((list(argv), job['id'], stdout_name))
            if self.launch_error:
                raise OSError(self.launch_error)
            handle = Process()
            self.handles[job['id']] = handle
            owner.processes[job['id']] = handle
            job.update(status='running', pid=handle.pid)

        self.launch_patch = patch.object(Workspace, '_launch', launch)
        self.launch_patch.start()
        self.addCleanup(self.launch_patch.stop)
        self.workspaces = []
        self.addCleanup(self.cleanup_workspaces)
        self.ws = self.new_workspace()
        self.config = self.ws.bootstrap()['defaults']['px4']

    def new_workspace(self):
        workspace = Workspace(self.root)
        self.workspaces.append(workspace)
        return workspace

    def cleanup_workspaces(self):
        for handle in self.handles.values():
            handle.returncode = 1
        for workspace in reversed(self.workspaces):
            for view in workspace.views.values():
                view.stop()
            workspace.close()

    @staticmethod
    def put(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, allow_nan=False) + '\n', encoding='utf-8')

    def finish(self, job, result, code=0):
        path = (Path(job['directory']) / ('preflight.json' if job['kind'] == 'preflight'
                                       else 'result.json'))
        if result is not None:
            self.put(path, result)
        self.handles[job['id']].returncode = code
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = self.ws.get_run(job['id'])
            if current['status'] in ('pass', 'failed', 'cancelled'):
                return current
            time.sleep(.02)
        self.fail('Observer did not finish job: ' + repr(current))

    def admitted(self):
        check = self.ws.preflight(self.config)
        self.assertEqual(self.finish(check, {'ok': True})['status'], 'pass')
        return check['id']

    def flight(self):
        job = self.ws.start(self.config, self.admitted(), False)
        self.assertEqual(job['status'], 'running', job)
        return job

    def test_strict_configuration_and_mission_validation(self):
        cases = [None, [], dict(self.config, unexpected=1),
                 dict(self.config, schema_version=True),
                 dict(self.config, px4_root='/tmp/../escape'),
                 dict(self.config, control_protocol='legacy_v1'),
                 dict(self.config, display_socket='/tmp/' + self.config['run_id'] + '/state.sock')]
        no_mission = deepcopy(self.config)
        del no_mission['mission']
        cases.append(no_mission)
        bad_mission = deepcopy(self.config)
        bad_mission['mission']['waypoints'][0]['position_m'][0] = float('nan')
        cases.append(bad_mission)
        for config in cases:
            with self.subTest(config=config):
                for action in (lambda: self.ws.save_config('bad', config),
                               lambda: self.ws.preflight(config),
                               lambda: self.ws.start(config, '0' * 32, False)):
                    with self.assertRaises(ValueError):
                        action()
        self.assertEqual(self.ws.bootstrap()['configs'], [])
        self.assertEqual(self.ws.list_runs(), [])
        self.assertEqual(self.launches, [])

    def test_strict_json_decoder(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)

    def test_compare_and_save_reload_and_input_isolation(self):
        for name in ('../escape', '', 'a/b', 'a' * 65, None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.ws.save_config(name, self.config)
        first = self.ws.save_config('mission', self.config)
        edited = deepcopy(self.config)
        edited['mission']['waypoints'][0]['dwell_s'] = 3
        for expected in (None, 'stale'):
            with self.assertRaises(ValueError):
                self.ws.save_config('mission', edited, expected)
        self.assertEqual(self.ws.bootstrap()['configs'], [first])
        second = self.ws.save_config('mission', edited, first['revision'])
        self.assertNotEqual(first['revision'], second['revision'])
        edited['mission']['waypoints'][0]['dwell_s'] = 4
        self.ws.close()
        reopened = self.new_workspace()
        self.assertEqual(reopened.bootstrap()['configs'], [second])
        self.assertEqual(self.launches, [])

    def test_only_exact_successful_preflight_admits_start(self):
        with self.assertRaises(ValueError):
            self.ws.start(self.config, '0' * 32, False)
        for result, code in (({'ok': False}, 0), ({'ok': True}, 1), ({'ok': 1}, 0), (None, 0)):
            with self.subTest(result=result, code=code):
                check = self.ws.preflight(self.config)
                self.assertEqual(self.finish(check, result, code)['status'], 'failed')
                with self.assertRaises(ValueError):
                    self.ws.start(self.config, check['id'], False)
        ticket = self.admitted()
        changed = deepcopy(self.config)
        changed['mission']['waypoints'][0]['dwell_s'] = 3
        with self.assertRaises(ValueError):
            self.ws.start(changed, ticket, False)
        for value in (0, 1, 'false', None):
            with self.subTest(with_view=value), self.assertRaises(ValueError):
                self.ws.start(self.config, ticket, value)
        flight = self.ws.start(self.config, ticket, False)
        self.finish(flight, {'status': 'pass', 'children_reaped': True})
        with self.assertRaises(ValueError):
            self.ws.start(self.config, flight['id'], False)

    def test_repeated_starts_have_fresh_execution_identity_and_stable_config(self):
        original = deepcopy(self.config)
        saved = self.ws.save_config('repeat', self.config)
        saved_path = self.root / 'configs/repeat.json'
        digest = hashlib.sha256(saved_path.read_bytes()).hexdigest()
        ticket = self.admitted()
        flights = []
        for _ in range(2):
            job = self.ws.start(self.config, ticket, False)
            self.assertEqual(job['status'], 'running', job)
            requested = json.loads((self.root / 'jobs' / job['id'] / 'requested-config.json').read_text())
            runtime = json.loads((self.root / 'jobs' / job['id'] / 'runtime-config.json').read_text())
            self.assertEqual(requested, saved['config'])
            self.assertEqual(job['config_revision'], saved['revision'])
            self.assertEqual(runtime.pop('run_id'), job['run_id'])
            socket = runtime.pop('display_socket')
            self.assertIn(job['run_id'], socket)
            self.assertEqual(runtime, {k: v for k, v in requested.items() if k != 'run_id'})
            flights.append((job, socket))
            self.finish(job, {'status': 'pass', 'children_reaped': True})
        for key in ('id', 'run_id', 'directory'):
            self.assertNotEqual(flights[0][0][key], flights[1][0][key])
        self.assertNotEqual(flights[0][1], flights[1][1])
        self.assertEqual(self.config, original)
        self.assertEqual(hashlib.sha256(saved_path.read_bytes()).hexdigest(), digest)

    def test_active_check_and_flight_exclude_new_jobs_and_shutdown(self):
        check = self.ws.preflight(self.config)
        with self.assertRaises(ValueError):
            self.ws.start(self.config, check['id'], False)
        with self.assertRaises(ValueError):
            self.ws.preflight(self.config)
        with self.assertRaises(ValueError):
            self.ws.cancel(check['id'], 'a' * 32)
        with self.assertRaises(ValueError):
            self.ws.close()
        self.finish(check, {'ok': True})
        flight = self.ws.start(self.config, check['id'], False)
        before = len(self.launches)
        with self.assertRaises(ValueError):
            self.ws.start(self.config, check['id'], False)
        with self.assertRaises(ValueError):
            self.ws.preflight(self.config)
        with self.assertRaises(ValueError):
            self.ws.close()
        self.assertEqual(len(self.launches), before)
        self.assertEqual(self.ws.get_run(flight['id'])['status'], 'running')

    def test_launch_failure_is_failed_and_never_fabricates_result(self):
        ticket = self.admitted()
        self.launch_error = 'injected process creation failure'
        for launch in (lambda: self.ws.preflight(self.config),
                       lambda: self.ws.start(self.config, ticket, False)):
            job = launch()
            self.assertEqual(job['status'], 'failed')
            self.assertIn(self.launch_error, job['error'])
            self.assertIsNone(job['result'])
            with self.assertRaises((ValueError, OSError)):
                self.ws.result(job['id'])
        self.ws.close()

    def test_flight_success_requires_formal_result_and_zero_exit(self):
        ticket = self.admitted()
        for result, code, expected in ((None, 0, 'failed'),
                                      ({'status': 'pass', 'children_reaped': False}, 0, 'failed'),
                                      ({'status': 'pass', 'children_reaped': True}, 1, 'failed'),
                                      ({'status': 'cancelled', 'children_reaped': True}, 0, 'cancelled')):
            with self.subTest(result=result, code=code):
                job = self.ws.start(self.config, ticket, False)
                self.assertEqual(self.finish(job, result, code)['status'], expected)

    def test_restart_does_not_adopt_persisted_live_flight(self):
        job = self.flight()
        catalog_path = self.root / 'jobs' / job['id'] / 'job.json'
        persisted_live = json.loads(catalog_path.read_text(encoding='utf-8'))
        self.finish(job, {'status': 'pass', 'children_reaped': True})
        self.ws.close()
        # Restore the on-disk catalog from before process completion to represent
        # an interrupted server. No second owner or real crashed process needed.
        self.put(catalog_path, persisted_live)
        count = len(self.launches)
        reopened = self.new_workspace()
        historical = reopened.get_run(job['id'])
        self.assertEqual(historical['status'], 'unowned')
        self.assertEqual(len(self.launches), count)
        for action in (lambda: reopened.cancel(job['id'], 'a' * 32),
                       lambda: reopened.view(job['id'], 'open'),
                       lambda: reopened.evidence(job['id'], 'truth', 0, 50),
                       lambda: reopened.result(job['id'])):
            with self.assertRaises(ValueError):
                action()
        reopened.close()

    def test_duplicate_root_refused_and_close_releases_ownership(self):
        saved = self.ws.save_config('owned', self.config)
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, 'already owns'):
                self.new_workspace()
        self.assertEqual(self.ws.bootstrap()['configs'], [saved])
        self.ws.close()
        reopened = self.new_workspace()
        self.assertEqual(reopened.bootstrap()['configs'], [saved])
        with self.assertRaisesRegex(ValueError, 'already owns'):
            self.new_workspace()
        self.assertEqual(self.launches, [])

    def test_catalog_is_compact_without_erasing_selected_run_details(self):
        job = self.flight()
        # Wait for a real reader projection, independent of launch/prepare order.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            selected = self.ws.get_run(job['id'])
            if selected['live'] is not None:
                break
            time.sleep(.02)
        self.assertIsNotNone(selected['live'])
        result = {'status': 'pass', 'children_reaped': True, 'detail': {'retained': 7}}
        selected = self.finish(job, result)
        self.assertEqual(selected['result'], result)
        self.assertIsNotNone(selected['live'])
        for catalog in (self.ws.list_runs(), self.ws.bootstrap()['runs']):
            entry = next(row for row in catalog if row['id'] == job['id'])
            self.assertIsNone(entry['live'])
            self.assertIsNone(entry['result'])
            self.assertEqual(entry['status'], 'pass')
            entry['config']['run_id'] = 'caller-mutation'
        again = self.ws.get_run(job['id'])
        self.assertEqual(again['result'], selected['result'])
        self.assertEqual(again['live'], selected['live'])
        self.assertEqual(again['config'], selected['config'])

    def test_cancel_requires_current_mission_and_live_owned_handle(self):
        job = self.flight()
        directory = Path(job['directory'])
        mission = 'a' * 32
        self.put(directory / 'mission-status.json', dict(version=1, run_id=job['run_id'],
                 mission_id=mission, update_sequence=1, state='running'))
        for identity in ('b' * 32, '', None):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.ws.cancel(job['id'], identity)
        self.assertFalse((directory / 'mission-cancel.json').exists())
        response = self.ws.cancel(job['id'], mission)
        self.assertTrue(response['submitted'])
        self.assertEqual(response['request']['mission_id'], mission)
        self.assertEqual(response['request']['run_id'], job['run_id'])
        self.assertEqual(response, self.ws.cancel(job['id'], mission))
        self.assertEqual(self.ws.get_run(job['id'])['status'], 'running')
        before = (directory / 'mission-cancel.json').read_bytes()
        self.handles[job['id']].returncode = 0
        with self.assertRaises(ValueError):
            self.ws.cancel(job['id'], mission)
        self.assertEqual((directory / 'mission-cancel.json').read_bytes(), before)

    def test_shutdown_refuses_owned_view_until_closed(self):
        job = self.flight()
        self.finish(job, {'status': 'pass', 'children_reaped': True})
        # Seed an inert owned view because real View.start launches UE outside _launch.
        view = OwnedView()
        self.ws.views[job['id']] = view
        for state in ('starting', 'live', 'stale'):
            view.state = state
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.ws.close()
        self.assertEqual(self.ws.view(job['id'], 'close')['state'], 'stopped')
        self.ws.close()

    def test_optional_view_preparation_precedes_physics_and_reserves_workspace(self):
        ticket=self.admitted()
        view=OwnedView(); view.state='starting'
        view.start=lambda: None
        with patch('Simulator.wksim_console.visual.View',return_value=view):
            job=self.ws.start(self.config,ticket,True)
            self.assertEqual(job['status'],'queued')
            self.assertFalse(job['preparation']['physics_started'])
            self.assertNotIn(job['id'],self.handles)
            with self.assertRaises(ValueError):
                self.ws.close()
            with self.assertRaises(ValueError):
                self.ws.preflight(self.config)
            view.state='stale'  # Ready viewer has no physics samples yet.
            deadline=time.monotonic()+3
            while job['id'] not in self.handles and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertIn(job['id'],self.handles)
            self.assertTrue(self.ws.get_run(job['id'])['preparation']['physics_started'])
            self.finish(job,{'status':'pass','children_reaped':True})

    def test_failed_optional_view_does_not_fake_readiness_or_block_headless_run(self):
        ticket=self.admitted()
        with patch('Simulator.wksim_console.visual.View',side_effect=ValueError('wrong DLL')):
            job=self.ws.start(self.config,ticket,True)
            deadline=time.monotonic()+3
            while job['id'] not in self.handles and time.monotonic()<deadline:
                time.sleep(.02)
            self.assertIn(job['id'],self.handles)
            current=self.ws.get_run(job['id'])
            self.assertEqual(current['view']['state'],'failed')
            self.assertIn('wrong DLL',current['view']['error'])
            self.finish(job,{'status':'pass','children_reaped':True})

    def test_failed_view_with_owned_resource_still_blocks_shutdown(self):
        job=self.flight()
        self.finish(job,{'status':'pass','children_reaped':True})
        view=OwnedView(); view.state='failed'
        view.poll=lambda:dict(state=view.state,resource_held=view.state!='stopped')
        self.ws.views[job['id']]=view
        with self.assertRaises(ValueError):
            self.ws.close()
        self.ws.view(job['id'],'close')
        self.ws.close()

    def test_restarted_server_does_not_advertise_historical_view_as_live(self):
        job=self.flight()
        self.finish(job,{'status':'pass','children_reaped':True})
        self.ws.jobs[job['id']]['view']=dict(state='live',latest_actor={'previous':True})
        self.ws._persist(self.ws.jobs[job['id']])
        self.ws.close()
        reopened=self.new_workspace()
        historical=reopened.get_run(job['id'])
        self.assertEqual(historical['status'],'pass')
        self.assertEqual(historical['view']['state'],'unavailable')
        self.assertEqual(historical['view']['historical_state'],'live')
        self.assertIsNone(historical['view']['latest_actor'])

    def test_evidence_is_terminal_known_flight_only_and_read_only(self):
        check = self.ws.preflight(self.config)
        with self.assertRaises(ValueError):
            self.ws.evidence(check['id'], 'truth', 0, 50)
        self.finish(check, {'ok': True})
        with self.assertRaises(ValueError):
            self.ws.evidence(check['id'], 'truth', 0, 50)
        job = self.ws.start(self.config, check['id'], False)
        with self.assertRaises(ValueError):
            self.ws.evidence(job['id'], 'truth', 0, 50)
        with self.assertRaises(ValueError):
            self.ws.result(job['id'])
        directory = Path(job['directory'])
        directory.mkdir(parents=True, exist_ok=True)
        raw = '{"time": 1.25, "position": [1, 2, 3]}\n'
        (directory / 'truth.jsonl').write_text(raw, encoding='utf-8')
        result = {'status': 'pass', 'children_reaped': True, 'run_id': job['run_id'],
                  'epoch': 'b' * 32, 'extra_runtime_evidence': {'retained': True}}
        self.finish(job, result)
        snapshot = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        launches = len(self.launches)
        page = self.ws.evidence(job['id'], 'truth', 0, 1)
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['records'][0]['raw_json'], snapshot['truth.jsonl'].decode('utf-8'))
        self.assertEqual(page['records'][0]['clock'], 'physics')
        self.assertEqual(self.ws.evidence(job['id'], 'truth', 1, 1)['records'], [])
        missing = self.ws.evidence(job['id'], 'dds', 0, 50)
        self.assertEqual(missing['records'], [])
        self.assertTrue(any(d['code'] == 'missing_file' and d.get('file') == 'dds.jsonl'
                            for d in missing['diagnostics']))
        for stream, offset, limit in (('../result.json', 0, 1), ('truth', -1, 1),
                                     ('truth', True, 1), ('truth', 0, 101), ('truth', 0, False)):
            with self.subTest(stream=stream, offset=offset, limit=limit), self.assertRaises(ValueError):
                self.ws.evidence(job['id'], stream, offset, limit)
        for ident in ('0' * 32, '../result.json', str(directory)):
            with self.subTest(ident=ident):
                with self.assertRaises(ValueError):
                    self.ws.evidence(ident, 'truth', 0, 1)
                with self.assertRaises(ValueError):
                    self.ws.result(ident)
        self.assertEqual(self.ws.result(job['id'])['values'], result)
        self.assertEqual(self.ws.result(job['id'])['raw_json'], snapshot['result.json'].decode('utf-8'))
        self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}, snapshot)
        self.assertEqual(len(self.launches), launches)


if __name__ == '__main__':
    unittest.main()
