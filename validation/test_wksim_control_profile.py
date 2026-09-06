"""In-memory fault injection and optional read-only checks of the real flown candidate.

Run with python3 -B -m unittest validation.test_wksim_control_profile -v.
Set WKSIM_CONTROL_PROFILE_LIVE_RESOURCES=1 with the pinned Humble overlays sourced
to exercise actual admission and failures. No fixtures are written or processes started.
"""
import copy
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime import preflight as admission
from Simulator.wksim_runtime.config import load_config


@contextmanager
def read_only():
    original = Path.open

    def checked(path, mode='r', *args, **kwargs):
        if any(flag in mode for flag in 'wax+'):
            raise AssertionError('preflight attempted a write')
        return original(path, mode, *args, **kwargs)

    with ExitStack() as guards:
        guards.enter_context(patch.object(Path, 'open', checked))
        for target in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.fork'):
            guards.enter_context(patch(target, side_effect=AssertionError('must not spawn'), create=True))
        yield


class ControlProfileTests(unittest.TestCase):
    def setUp(self):
        self.index = json.loads(admission.INDEX.read_text(encoding='utf-8'))

    def select(self, index=None, stack='px4'):
        return admission.control_profile(index or self.index, 'session_v1', stack,
                                         lambda *args: None)

    def test_legacy_baselines_are_unchanged(self):
        frozen = hashlib.sha256(json.dumps(self.index['baselines'], sort_keys=True).encode()).hexdigest()
        self.assertEqual(frozen, '9994bef882fe47519001a44387351354d0e5f30ab3fe6aba0c060031f6467706')
        before = copy.deepcopy(self.index)
        for stack in ('px4', 'arducopter'):
            self.assertIs(admission.control_profile(self.index, 'legacy_v1', stack, lambda *a: None),
                          self.index['baselines'][stack])
            selected = self.select(stack=stack)
            self.assertEqual(selected['roots']['prometheus_workspace'], '/root/wksim-ros2-MUlZd0')
            self.assertIn('wksim_msgs', selected['message_packages'])
        self.assertEqual(self.index, before)

    def test_both_real_evidence_pins_and_source_sets(self):
        with read_only():
            self.select()
        for pin in self.index['control_profiles']['session_v1']['evidence'].values():
            self.assertEqual(admission.digest(admission.REPO / pin['result']), pin['result_sha256'])

    def test_unknown_protocol_is_rejected(self):
        config = load_config(admission.INDEX.parent / 'examples/px4.json')
        with read_only():
            result = admission.preflight(dict(config, control_protocol='session_v2'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['children_created'], 0)

    def test_either_flight_tampering_blocks_both_stacks(self):
        original = Path.read_bytes
        for peer, pin in self.index['control_profiles']['session_v1']['evidence'].items():
            target = admission.REPO / pin['result']

            def changed(path):
                raw = original(path)
                return raw + b' ' if path == target else raw

            for stack in ('px4', 'arducopter'):
                with self.subTest(peer=peer, stack=stack), patch.object(Path, 'read_bytes', changed):
                    with self.assertRaisesRegex(ValueError, 'SHA256 differs'):
                        self.select(stack=stack)

    def test_evidence_semantics_fail_closed_even_with_recomputed_pin(self):
        # Recomputed pins isolate semantic checks; normal tampering fails SHA first.
        mutations = {
            'unflown': lambda e: e.update(status='not_run'),
            'wrong_stack': lambda e: e.update(stack='other'),
            'cross_protocol': lambda e: e['prometheus'].update(protocol='legacy_v1'),
            'wrong_workspace': lambda e: e.update(prometheus_workspace='/root/unflown'),
            'wrong_dds': lambda e: e.update(dds_workspace='/root/unflown'),
            'observer_commands': lambda e: e['dds'].update(commands=[{'command': 'arm'}]),
            'observer_missing': lambda e: e['dds'].pop('commands'),
            'firmware': lambda e: e.update(fc_binary_sha256='0' * 64),
            'source_commit': lambda e: e.update(fc_commit='0' * 40),
            'agent': lambda e: e.update(agent_sha256='0' * 64),
            'model': lambda e: e['model_build'].update(library_sha256='0' * 64),
            'missing_session_source': lambda e: e['prometheus']['implementation_sha256'].pop('session.py'),
            'source_disagreement': lambda e: e['prometheus']['implementation_sha256'].update(node='0' * 64),
            'empty_epoch': lambda e: e['prometheus'].update(control_epoch=''),
            'wrong_run': lambda e: e['prometheus'].update(run_id='another-run'),
            'no_envelopes': lambda e: e['prometheus'].update(request_envelopes=[]),
            'stale_epoch': lambda e: e['prometheus']['request_envelopes'][0].update(control_epoch='old'),
            'wrong_request': lambda e: e['prometheus']['request_envelopes'][0].update(request_id=99),
            'wrong_payload': lambda e: e['prometheus']['request_envelopes'][0].update(setup={}),
        }
        original = Path.read_bytes
        for peer in ('px4', 'arducopter'):
            for label, mutate in mutations.items():
                index = copy.deepcopy(self.index)
                pin = index['control_profiles']['session_v1']['evidence'][peer]
                target = admission.REPO / pin['result']
                evidence = json.loads(original(target))
                mutate(evidence)
                raw = json.dumps(evidence).encode()
                pin['result_sha256'] = hashlib.sha256(raw).hexdigest()

                def changed(path):
                    return raw if path == target else original(path)

                with self.subTest(peer=peer, mutation=label), patch.object(Path, 'read_bytes', changed):
                    with self.assertRaises((ValueError, KeyError)):
                        self.select(index)

    def test_missing_peer_evidence_rejects(self):
        original = Path.read_bytes
        target = admission.REPO / self.index['control_profiles']['session_v1']['evidence']['arducopter']['result']

        def missing(path):
            if path == target:
                raise FileNotFoundError(str(path))
            return original(path)

        with patch.object(Path, 'read_bytes', missing), self.assertRaises(FileNotFoundError):
            self.select()


@unittest.skipUnless(os.environ.get('WKSIM_CONTROL_PROFILE_LIVE_RESOURCES') == '1',
                     'requires pinned Ubuntu resources and sourced session overlay; never flies')
class InstalledControlProfileTests(unittest.TestCase):
    def config(self, stack):
        config = load_config(admission.INDEX.parent / f'examples/{stack}.json')
        return dict(config, control_protocol='session_v1', prometheus_workspace='/root/wksim-ros2-MUlZd0')

    def run_check(self, config, ok, code=None):
        before = copy.deepcopy(config)
        with read_only():
            result = admission.preflight(config)
        self.assertEqual(result['ok'], ok, result['reasons'])
        self.assertEqual(result['children_created'], 0)
        self.assertEqual(config, before)
        if code:
            self.assertIn(code, [r['code'] for r in result['reasons']], result['reasons'])
        return result

    def test_real_candidate_both_stacks(self):
        for stack in ('px4', 'arducopter'):
            with self.subTest(stack=stack):
                result = self.run_check(self.config(stack), True)
                self.assertTrue(result['candidate_status']['flown'])
                self.assertIn('prometheus/session.py', result['identities'])
                self.assertIn('messages/wksim_msgs', result['identities'])

    def test_original_47_schemas_and_three_session_messages(self):
        workspace = Path('/root/wksim-ros2-MUlZd0')
        source = workspace / 'src/prometheus_msgs'
        schemas = [p for p in source.rglob('*') if p.suffix in ('.msg', '.srv', '.action')]
        self.assertEqual(len(schemas), 47)
        for path in schemas:
            relative = path.relative_to(source)
            old = Path('/root/wksim-ros2-0viK3f/install/prometheus_msgs/share/prometheus_msgs') / relative
            installed = workspace / 'install/prometheus_msgs/share/prometheus_msgs' / relative
            self.assertEqual(admission.digest(path), admission.digest(old), str(relative))
            self.assertEqual(admission.digest(path), admission.digest(installed), str(relative))
        session = workspace / 'install/wksim_msgs/share/wksim_msgs/msg'
        self.assertEqual({p.name for p in session.glob('*.msg')},
                         {'CommandRequest.msg', 'SetupRequest.msg', 'SessionState.msg'})

    def test_protocol_workspace_crossing_and_unknown_candidates(self):
        for stack in ('px4', 'arducopter'):
            config = self.config(stack)
            for change in ({'control_protocol': 'legacy_v1'},
                           {'prometheus_workspace': '/root/wksim-ros2-0viK3f'},
                           {'prometheus_workspace': '/root/not-flown-2egljG'},
                           {'model_library': '/dev/null'}):
                with self.subTest(stack=stack, change=change):
                    self.run_check(dict(config, **change), False)
            default = dict(config)
            default.pop('control_protocol')
            self.run_check(default, False, 'candidate_not_pinned')
        self.run_check(dict(self.config('arducopter'), ap_candidate='/root/wksim-ap-dds-yaw-fJUTtb'), False)

    def test_evidence_tampering_at_preflight_boundary(self):
        original = Path.read_bytes
        index = json.loads(admission.INDEX.read_text())
        target = admission.REPO / index['control_profiles']['session_v1']['evidence']['arducopter']['result']

        def tampered(path):
            raw = original(path)
            return raw + b' ' if path == target else raw

        with patch.object(Path, 'read_bytes', tampered):
            self.run_check(self.config('px4'), False, 'preflight_unavailable')

    def test_every_installed_control_source_is_hashed(self):
        original = admission.digest
        index = json.loads(admission.INDEX.read_text())
        pin = json.loads((admission.REPO / index['control_profiles']['session_v1']['evidence']['px4']['result']).read_text())
        for name in pin['prometheus']['implementation_sha256']:
            def tampered(path):
                if Path(path).name == name and 'install/prometheus_control/' in str(path):
                    return '0' * 64
                return original(path)
            with self.subTest(file=name), patch.object(admission, 'digest', tampered):
                self.run_check(self.config('px4'), False, 'identity_mismatch')

    def test_added_python_source_is_rejected(self):
        original = Path.rglob

        def added(path, pattern):
            yield from original(path, pattern)
            if path.name == 'prometheus_control' and pattern == '*.py':
                yield path / 'unflown.py'

        with patch.object(Path, 'rglob', added):
            self.run_check(self.config('px4'), False, 'identity_mismatch')

    def test_schema_library_and_metadata_tampering(self):
        original = admission.digest
        root = Path('/root/wksim-ros2-MUlZd0/install')
        targets = [root / 'prometheus_msgs/share/prometheus_msgs/msg/UAVCommand.msg',
                   root / 'wksim_msgs/share/wksim_msgs/msg/SessionState.msg',
                   root / 'prometheus_control/share/prometheus_control/package.xml']
        for name in ('prometheus_msgs', 'wksim_msgs'):
            targets.append(next((root / name / 'lib').glob('*.so')))
        for target in targets:
            self.assertTrue(target.is_file(), str(target))

            def tampered(path):
                return '0' * 64 if Path(path) == target else original(path)

            with self.subTest(file=str(target)), patch.object(admission, 'digest', tampered):
                self.run_check(self.config('px4'), False, 'message_identity_mismatch')

    def test_ament_linker_and_python_overlay_rejections(self):
        for variable in ('AMENT_PREFIX_PATH', 'LD_LIBRARY_PATH'):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: ''}):
                self.run_check(self.config('px4'), False, 'mixed_overlay')
        old_prefix = '/root/wksim-ros2-0viK3f/install/prometheus_msgs'
        for variable, value in (('AMENT_PREFIX_PATH', old_prefix), ('LD_LIBRARY_PATH', old_prefix + '/lib')):
            with patch.dict(os.environ, {variable: value + os.pathsep + os.environ.get(variable, '')}):
                self.run_check(self.config('px4'), False, 'mixed_overlay')
        original = admission.importlib.util.find_spec
        for name in ('prometheus_control', 'prometheus_msgs', 'wksim_msgs'):
            def wrong_spec(module):
                return types.SimpleNamespace(origin='/wrong/' + name + '/__init__.py') if module == name else original(module)
            with self.subTest(module=name), patch.object(admission.importlib.util, 'find_spec', wrong_spec):
                self.run_check(self.config('px4'), False, 'mixed_overlay')
            module = types.ModuleType(name + '.stale')
            module.__file__ = '/wrong/' + name + '/stale.py'
            with patch.dict(admission.sys.modules, {name + '.stale': module}):
                self.run_check(self.config('px4'), False, 'mixed_overlay')


if __name__ == '__main__':
    unittest.main()
