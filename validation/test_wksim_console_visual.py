"""Controlled process doubles only: these tests do not launch UE, WSL or FC."""
import json
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from Simulator.wksim_console import visual
from Simulator.wksim_core.state_stream import METADATA


class Process:
    next_pid = 40000

    def __init__(self, argv, **kwargs):
        Process.next_pid += 1
        self.pid = Process.next_pid
        self.argv, self.kwargs = argv, kwargs
        self.returncode = 0 if argv[0] == 'wsl.exe' else None
        self.terminated = False
        self.stdin = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated, self.returncode = True, -15

    def kill(self):
        self.terminated, self.returncode = True, -9

    def wait(self, timeout=None):
        return self.returncode


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.children = []
        self.views = []
        self.popen = patch.object(visual.subprocess, 'Popen', side_effect=self.spawn)
        self.popen_mock = self.popen.start()
        self.addCleanup(self.popen.stop)
        self.addCleanup(self.close_views)

    def close_views(self):
        for view in self.views:
            view.stop()

    def spawn(self, argv, **kwargs):
        child = Process(argv, **kwargs)
        self.children.append(child)
        if argv[0] == str(visual.ENGINE):
            for arg in argv:
                if arg.startswith('-abslog='):
                    self.assertNotEqual(Path(kwargs['stdout'].name), Path(arg.partition('=')[2]),
                                        'Launcher stdout must not pre-create Unreal-owned log')
                    Path(arg.partition('=')[2]).write_text('WKSIM_READY run=run-1 vehicle=1 port=19060 world=test\n')
        if '--relay-record' in argv:
            # Controlled nested-launcher evidence, never a real WSL process.
            Path(argv[argv.index('--relay-record') + 1]).write_text(json.dumps(
                dict(argv=['wsl.exe', 'controlled-relay'], pid=50000, returncode=0)))
        return child

    def view(self, suffix='a'):
        view = visual.View(self.root / suffix, 'run-1', '/tmp/wksim-run-1/state.sock')
        self.views.append(view)
        return view

    def ready(self, view):
        deadline = time.monotonic() + 2
        while not view._ready and view._thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(view._ready, view.poll())

    @staticmethod
    def preflight(view):
        view._wsl_repo = '/mnt/c/repo'
        return {'project': 'C:/p/project.uproject'}

    def test_preflight_failure_launches_nothing(self):
        view = self.view()
        with patch.object(view, '_preflight', side_effect=ValueError('DLL mismatch')):
            view.start()
            view._thread.join(2)
        self.assertEqual(view.poll()['state'], 'failed')
        self.assertIn('DLL', view.poll()['error'])
        self.popen_mock.assert_not_called()

    def test_manifest_verifies_dll_source_and_staged_inputs(self):
        repo = self.root / 'repo'
        source = repo / 'Simulator/ue55'
        source.mkdir(parents=True)
        stage = self.root / 'stage'
        stage.mkdir()
        engine, dll, project = stage / 'editor.exe', stage / 'module.dll', stage / 'app.uproject'
        for path in (engine, dll, project, source / 'input.cpp', stage / 'input.cpp'):
            path.write_bytes(b'identity')
        build = dict(project=str(project), binary=str(dll), binary_sha256=visual._sha(dll), build_exit_code=0,
                     build_inputs=[dict(path='input.cpp', source_sha256=visual._sha(source / 'input.cpp'),
                                        staging_sha256=visual._sha(stage / 'input.cpp'))])
        (source / 'state-build-manifest.json').write_text(json.dumps(build))
        view = visual.View(self.root / 'evidence', 'run-1', '/tmp/wksim-run-1/state.sock', repo)
        with patch.object(visual, 'ENGINE', engine), patch.object(visual, '_wsl_path', return_value='/mnt/c/repo'):
            self.assertEqual(view._preflight(), build)
            for path in (dll, source / 'input.cpp', stage / 'input.cpp'):
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    view._preflight()
                path.write_bytes(b'identity')
        self.popen_mock.assert_not_called()

    def test_starting_marker_does_not_admit_bridge_before_render_ready(self):
        entered = threading.Event()
        def preparing(argv, **kwargs):
            child = self.spawn(argv, **kwargs)
            if argv[0] == str(visual.ENGINE):
                log = Path(next(a.partition('=')[2] for a in argv if a.startswith('-abslog=')))
                log.write_text('WKSIM_STARTING run=run-1 vehicle=1 port=19060 world=test\n')
                entered.set()
            return child
        with patch.object(visual.View, '_preflight', self.preflight), patch.object(visual, '_probe_port'), \
                patch.object(visual.subprocess, 'Popen', side_effect=preparing):
            view = self.view()
            view.start()
            self.assertTrue(entered.wait(1))
            self.assertFalse(view._ready)
            self.assertFalse(any('--bridge-helper' in child.argv for child in self.children))
            (view._root / 'ue.log').write_text('WKSIM_READY run=run-1 vehicle=1 port=19060 world=test assets_remaining=0 fence=rhi\n')
            self.ready(view)
            self.assertTrue(any('--bridge-helper' in child.argv for child in self.children))

    def test_missing_p450_manifest_rejected_before_launch(self):
        repo = self.root / 'p450repo'
        source = repo / 'Simulator/ue55'
        source.mkdir(parents=True)
        stage = self.root / 'p450stage'
        stage.mkdir()
        engine, dll, project = stage / 'editor.exe', stage / 'module.dll', stage / 'app.uproject'
        for path in (engine, dll, project, source / 'input.cpp', stage / 'input.cpp'):
            path.write_bytes(b'identity')
        build = dict(project=str(project), binary=str(dll), binary_sha256=visual._sha(dll), build_exit_code=0,
            visual_model='prometheus_p450_visual_v1', asset_inputs=[],
            build_inputs=[dict(path='input.cpp', source_sha256=visual._sha(source / 'input.cpp'),
                               staging_sha256=visual._sha(stage / 'input.cpp'))])
        (source / 'state-build-manifest.json').write_text(json.dumps(build))
        view = visual.View(self.root / 'evidence', 'run-1', '/tmp/wksim-run-1/state.sock', repo)
        with patch.object(visual, 'ENGINE', engine):
            with self.assertRaisesRegex(ValueError, 'P450 asset manifest is incomplete'):
                view._preflight()
        self.popen_mock.assert_not_called()

    def test_bridge_helper_retains_relay_identity_and_uses_eof(self):
        from Simulator.ue55 import product_bridge
        record = self.root / 'relay.json'
        callbacks = []
        created = []

        class RelayDouble(Process):
            def __init__(self, argv, **kwargs):
                super().__init__(argv, **kwargs)
                self.returncode = None
                self.stdin = io.BytesIO()
                created.append(self)

            def wait(self, timeout=None):
                if self.returncode is None:
                    self.returncode = 23
                return self.returncode

        def bridge(*args):
            child = visual.subprocess.Popen(['wsl.exe', '--exec', 'python3', '-m', 'Simulator.ue55.state_relay'])
            callbacks[0]()
            self.assertTrue(child.stdin.closed)
            child.wait(timeout=3)

        argv = ['visual', '--bridge-helper', '--relay-record', str(record), '--wsl-repo', '/mnt/c/repo',
                '--state-socket', '/tmp/wksim-run-1/state.sock', '--run-id', 'run-1', '--readback', 'unused']
        def thread(*, target, **kwargs):
            callbacks.append(target)
            return SimpleNamespace(start=lambda: None)

        with patch.object(visual.subprocess, 'Popen', RelayDouble), patch.object(product_bridge, 'bridge', bridge), \
                patch.object(visual.threading, 'Thread', thread), patch.object(visual.sys, 'argv', argv), \
                patch.object(visual.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'!'))):
            visual._bridge_helper()
        row = json.loads(record.read_text())
        self.assertEqual(row['pid'], created[0].pid)
        self.assertEqual(row['returncode'], 23)
        self.assertIn('Simulator.ue55.state_relay', row['argv'])
        self.assertFalse(created[0].terminated)

        def failed_bridge(*args):
            visual.subprocess.Popen(['wsl.exe', '--exec', 'controlled-relay'])
            raise RuntimeError('controlled bridge failure')

        with patch.object(visual.subprocess, 'Popen', RelayDouble), patch.object(product_bridge, 'bridge', failed_bridge), \
                patch.object(visual.threading, 'Thread', thread), patch.object(visual.sys, 'argv', argv):
            with self.assertRaisesRegex(RuntimeError, 'controlled bridge failure'):
                visual._bridge_helper()
        row = json.loads(record.read_text())
        self.assertEqual(row['pid'], created[-1].pid)
        self.assertEqual(row['returncode'], -15)
        self.assertTrue(created[-1].terminated)

    def test_invalid_socket_launches_nothing(self):
        for path in ('/tmp/state.sock', '/tmp/other/state.sock', '/tmp/run-1/../state.sock',
                     '/tmp/wksim-run-1/other.sock', '/tmp/wksim-run-1//state.sock'):
            view = self.view(str(len(self.views)))
            view.state_socket = path
            view.start()
            view._thread.join(2)
            self.assertEqual(view.poll()['state'], 'failed')
        self.popen_mock.assert_not_called()

    def test_busy_probe_and_process_lock(self):
        with patch.object(visual.View, '_preflight', self.preflight), patch.object(visual, '_probe_port', side_effect=OSError('busy')):
            view = self.view()
            view.start()
            view._thread.join(2)
            self.assertIn('busy', view.poll()['error'])
            self.popen_mock.assert_not_called()
        with patch.object(visual.View, '_preflight', self.preflight), patch.object(visual, '_probe_port'):
            first = self.view('first')
            first.start()
            self.ready(first)
            count = len(self.children)
            second = self.view('second')
            second.start()
            second._thread.join(2)
            self.assertIn('busy', second.poll()['error'])
            self.assertEqual(len(self.children), count)
            second.stop()
            self.assertTrue(all(not p.terminated for p in self.children))

    def test_start_returns_during_preflight_and_stop_race(self):
        entered, release = threading.Event(), threading.Event()
        view = self.view()

        def blocked():
            entered.set()
            release.wait(2)
            return self.preflight(view)

        with patch.object(view, '_preflight', blocked):
            self.assertEqual(view.start()['state'], 'starting')
            self.assertTrue(entered.wait(1))
            closer = threading.Thread(target=view.stop)
            closer.start()
            self.assertTrue(view._cancel.wait(1))
            release.set()
            closer.join(2)
        self.assertFalse(closer.is_alive())
        self.assertEqual(view.poll()['state'], 'stopped')
        self.popen_mock.assert_not_called()

    def test_launch_registration_close_race_and_only_owned_handles(self):
        view = self.view()
        entered, release = threading.Event(), threading.Event()
        foreign = Process(['foreign'])

        def blocked_spawn(argv, **kwargs):
            if argv[0] == str(visual.ENGINE):
                entered.set()
                release.wait(2)
            return self.spawn(argv, **kwargs)

        with patch.object(visual.View, '_preflight', self.preflight), patch.object(visual, '_probe_port'), \
                patch.object(visual.subprocess, 'Popen', side_effect=blocked_spawn):
            view.start()
            self.assertTrue(entered.wait(1))
            closer = threading.Thread(target=view.stop)
            closer.start()
            self.assertTrue(view._cancel.wait(1))
            release.set()
            closer.join(3)
        self.assertFalse(closer.is_alive())
        self.assertFalse(foreign.terminated)
        self.assertTrue(all(p.poll() is not None for p in self.children))
        self.assertFalse(any('--bridge-helper' in p.argv for p in self.children))
        rows = view.poll()['processes']
        self.assertTrue(all(row['argv'] and row['pid'] and row['returncode'] is not None for row in rows))

    def packet(self, age=0, run_id='run-1'):
        packet = dict(METADATA, version=2, run_id=run_id, vehicle_id=1, sequence=7,
                      sim_time_s=1., source_wall_time_s=10., position_ned_m=[1, 2, -3],
                      quaternion_wxyz=[1, 0, 0, 0], rotor_rpm=[100] * 4,
                      display_wall_time_s=time.time() - age, transport_age_bound_s=.1,
                      display_clock='windows_utc_bound')
        ack = dict(run_id=run_id, sequence=7, sim_time_s=1., ue_position_cm=[100, 200, 300],
                   ue_quaternion_xyzw=[0, 0, 0, 1])
        return dict(packet=packet, ack=ack)

    def test_live_requires_fresh_correlated_actual_ack(self):
        with patch.object(visual.View, '_preflight', self.preflight), patch.object(visual, '_probe_port'):
            view = self.view()
            view.start()
            self.ready(view)
            view.readback_path.touch()
            self.assertEqual(view.poll()['state'], 'stale')
            for age, expected in ((0, 'live'), (5, 'stale'), (-5, 'stale')):
                view.readback_path.write_text(json.dumps(self.packet(age)) + '\n')
                self.assertEqual(view.poll()['state'], expected)
            view.readback_path.write_text(json.dumps(self.packet(run_id='foreign')) + '\n')
            self.assertIsNone(view.poll()['latest_actor'])
            wrong = self.packet()
            wrong['ack']['sequence'] = 9
            view.readback_path.write_text(json.dumps(wrong) + '\n')
            self.assertEqual(view.poll()['state'], 'stale')
            view.readback_path.write_text(json.dumps(self.packet()))
            self.assertIsNone(view.poll()['latest_actor'])
            view.readback_path.write_text('x' * (visual.TAIL_BYTES * 2) + '\n' + json.dumps(self.packet()) + '\n')
            self.assertEqual(view.poll()['state'], 'live')
            status = view.stop()
            self.assertEqual(status['state'], 'stopped')
            self.assertTrue(status['cleanup_pending'])
            self.assertEqual(json.loads((view.directory / 'view.json').read_text())['state'], 'stopped')

    def test_ue_exit_is_failure_not_adoption(self):
        def exited(argv, **kwargs):
            p = Process(argv, **kwargs)
            self.children.append(p)
            p.returncode = 0
            return p

        with patch.object(visual.View, '_preflight', self.preflight), patch.object(visual, '_probe_port'), \
                patch.object(visual.subprocess, 'Popen', side_effect=exited):
            view = self.view()
            view.start()
            view._thread.join(2)
        self.assertEqual(view.poll()['state'], 'failed')
        self.assertTrue(view.poll()['cleanup_pending'])
        self.assertIn('ownership', view.poll()['error'])

    def test_actor_mismatch_is_not_live_or_hidden_by_previous_good_ack(self):
        view = self.view()
        view._root.mkdir(parents=True)
        for key, value in (('ue_position_cm', [101, 200, 300]),
                           ('ue_quaternion_xyzw', [1, 0, 0, 0]), ('sim_time_s', 2.)):
            wrong = self.packet()
            wrong['ack'][key] = value
            view.readback_path.write_text(json.dumps(self.packet()) + '\n' + json.dumps(wrong) + '\n')
            self.assertEqual(view._actor(), (None, False))
        good = self.packet()
        good['ack']['ue_quaternion_xyzw'] = [0, 0, 0, -1]
        view.readback_path.write_text(json.dumps(good) + '\n')
        actor, fresh = view._actor()
        self.assertTrue(fresh)
        self.assertEqual(actor['errors'], dict(position_cm=0., quaternion_l2=0., sim_time_s=0.))

    def test_resource_stays_held_until_own_process_and_relay_have_exited(self):
        view = self.view()
        view._root.mkdir(parents=True)
        self.assertTrue(visual.View._resource.acquire(False))
        view._owns_resource = True
        child = Process(['bridge'])
        view._children.append(dict(name='bridge', process=child, argv=child.argv))
        try:
            view._release_reaped_resource()
            self.assertTrue(view._owns_resource)
            child.returncode = -15
            view._release_reaped_resource()
            self.assertTrue(view._owns_resource)  # missing relay evidence
            record = view._root / 'relay.json'
            record.write_text(json.dumps(dict(argv=['wsl.exe'], pid=50001, returncode=None)))
            view._release_reaped_resource()
            self.assertTrue(view._owns_resource)
            record.write_text(json.dumps(dict(argv=['wsl.exe'], pid=50001, returncode=9)))
            view._release_reaped_resource()
            self.assertFalse(view._owns_resource)
            self.assertEqual(view.poll()['relay']['returncode'], 9)
        finally:
            if view._owns_resource:
                visual.View._resource.release()
                view._owns_resource = False

    def test_ack_optional_stale_and_vehicle_fields_are_not_ignored(self):
        view = self.view()
        view._root.mkdir(parents=True)
        for fields in ({'stale': True}, {'stale': 1}, {'stale': 'false'}, {'stale': None},
                       {'vehicle_id': 2}, {'vehicle_id': True}, {'vehicle_id': '1'},
                       {'vehicleID': 2}):
            with self.subTest(fields=fields):
                bad = self.packet()
                bad['ack'].update(fields)
                view.readback_path.write_text(json.dumps(self.packet()) + '\n' + json.dumps(bad) + '\n')
                self.assertEqual(view._actor(), (None, False))
        for fields in ({}, {'stale': False, 'vehicle_id': 1}, {'stale': 0, 'vehicleID': 1}):
            good = self.packet()
            good['ack'].update(fields)
            view.readback_path.write_text(json.dumps(good) + '\n')
            self.assertTrue(view._actor()[1])

    def test_actor_thresholds_match_pinned_gate_and_use_measured_errors(self):
        self.assertEqual(visual.ACTOR_LIMITS, dict(position_cm=2e-4, quaternion_l2=2e-6, sim_time_s=1e-8))
        view = self.view()
        view._root.mkdir(parents=True)
        for delta, fresh in ((1e-4, True), (3e-4, False)):
            row = self.packet()
            row['ack']['ue_position_cm'][0] += delta
            row['errors'] = dict(position_cm=0, quaternion_l2=0, sim_time_s=0)
            view.readback_path.write_text(json.dumps(row) + '\n')
            self.assertEqual(view._actor()[1], fresh)


if __name__ == '__main__':
    unittest.main()
