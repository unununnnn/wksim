"""Offline contract checks; optional pinned-resource checks never start ROS/FC."""
import copy
import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime.config import ConfigError, load_config, validate_config
from Simulator.wksim_runtime.preflight import INDEX, REPO, digest, package_digest, preflight


class PreflightTests(unittest.TestCase):
    def test_selected_stack_still_requires_its_own_firmware(self):
        ap = load_config(INDEX.parent / 'examples/arducopter.json')
        ap.pop('px4_root', None)
        self.assertNotIn('px4_root', validate_config(ap))
        px4 = dict(ap, stack='px4')
        del px4['ap_candidate']
        with self.assertRaisesRegex(ConfigError, 'px4 requires px4_root'):
            validate_config(px4)

    def test_legacy_ap_admission_reads_own_firmware_without_peer_directory(self):
        from Simulator.wksim_runtime import preflight as admission
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cfg = dict(schema_version=1, run_id='ap-only', vehicle_id=1, stack='arducopter',
                model_profile='quad_x', communication='native_dds', dds_workspace=str(root/'dds'),
                prometheus_workspace=str(root/'control'), ap_candidate=str(root/'ap'))
            # Windows paths cannot exercise the Linux resource contract.
            if os.name != 'posix':
                self.skipTest('Linux absolute resource paths')
            for name in ('dds', 'control', 'ap'):
                (root/name).mkdir()
            firmware = root/'ap/build/sitl/bin/arducopter'
            firmware.parent.mkdir(parents=True)
            firmware.write_bytes(b'fixture only, not executable firmware')
            firmware.chmod(0o700)
            agent = root/'dds/ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent'
            agent.parent.mkdir(parents=True)
            agent.write_bytes(b'fixture only, not a DDS agent')
            agent.chmod(0o700)
            evidence = dict(status='pass', stack='arducopter', prometheus={},
                fc_binary_sha256=digest(firmware), fc_commit='fixture', agent_sha256=digest(agent),
                model_build={'library': str(root/'missing-model.so')})
            proof = root/'evidence.json'
            proof.write_text(json.dumps(evidence))
            baseline = dict(result=str(proof), result_sha256=digest(proof), roots={
                key: cfg[key] for key in ('dds_workspace', 'prometheus_workspace', 'ap_candidate')})
            baseline['roots']['px4_root'] = str(root/'not-installed-px4')
            index = root/'index.json'
            index.write_text(json.dumps(dict(capabilities=[dict(id='native_position_mission', admitted=True)],
                                             known_unflown_candidates=[])))
            with patch.object(admission, 'INDEX', index), \
                    patch.object(admission, 'consumer_rejections', return_value=[]), \
                    patch.object(admission, 'control_profile', return_value=baseline), \
                    patch('subprocess.Popen', side_effect=AssertionError('no process may start')):
                result = admission.preflight(cfg)
                self.assertTrue(result['identities']['firmware']['match'])
                self.assertTrue(result['identities']['agent']['match'])
                self.assertEqual(result['children_created'], 0)
                # Intentionally stop at the absent model; never claim full admission.
                self.assertFalse(result['ok'])
                self.assertIn('model_manifest_mismatch', [row['code'] for row in result['reasons']])
                firmware.write_bytes(b'changed selected firmware')
                rejected = admission.preflight(cfg)
                self.assertFalse(rejected['identities']['firmware']['match'])
                self.assertIn('identity_mismatch', [row['code'] for row in rejected['reasons']])

    def setUp(self):
        self.config = load_config(INDEX.parent / 'examples/arducopter.json')

    @unittest.skipUnless(os.environ.get('WKSIM_PREFLIGHT_LIVE_RESOURCES')=='1',
                         'explicit pinned environment; no process is launched')
    def test_missing_independent_px4_alias_is_rejected_before_startup(self):
        selected=load_config(INDEX.parent/'examples/px4.json')
        def unavailable(path):
            if Path(path).name=='px4-alias.sh':
                raise FileNotFoundError('injected missing generated alias')
            return digest(path)
        with patch('Simulator.wksim_runtime.preflight.digest',side_effect=unavailable):
            result=preflight(selected)
        self.assertFalse(result['ok'])
        self.assertEqual(result['children_created'],0)
        self.assertTrue(any(row['code']=='resource_missing' and 'px4-alias.sh' in row['message'] for row in result['reasons']))

    def test_strict_configuration(self):
        for key, value in [('schema_version', True), ('vehicle_id', 2), ('stack', 'sih'),
                           ('model_profile', 'hex'), ('communication', 'UDP_Full'),
                           ('run_id', '../old'), ('run_id', '实验'), ('run_id', ''),
                           ('dds_workspace', '/root/../other'), ('dds_workspace', 'relative'),
                           ('capabilities', []), ('capabilities', ['a', 'a'])]:
            with self.subTest(key=key, value=value), self.assertRaises(ConfigError):
                validate_config(dict(self.config, **{key: value}))
        with self.assertRaises(ConfigError):
            validate_config(dict(self.config, silent_fallback=True))
        with self.assertRaises(ConfigError):
            validate_config({k: v for k, v in self.config.items() if k != 'ap_candidate'})
        original = copy.deepcopy(self.config)
        validate_config(self.config)['capabilities'].append('mutated')
        self.assertEqual(self.config, original)

    def test_json_duplicates_and_constants(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            for text in ('{"stack":"px4","stack":"arducopter"}', '{"x":NaN}', '[]', '{'):
                path.write_text(text)
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_display_socket_contract(self):
        good = f"/tmp/wksim-{self.config['run_id']}/state.sock"
        self.assertEqual(validate_config(dict(self.config, display_socket=good))['display_socket'], good)
        for value in ('/tmp/state.sock', '/tmp/other/state.sock', '/run/state.sock', good + 'x' * 108):
            with self.assertRaises(ConfigError):
                validate_config(dict(self.config, display_socket=value))

    def test_telemetry_is_explicit_distinct_and_has_private_run_path(self):
        good = f"/tmp/wksim-{self.config['run_id']}/telemetry.sock"
        self.assertNotIn('telemetry_socket', validate_config(self.config))
        self.assertEqual(validate_config(dict(self.config, telemetry_socket=good))['telemetry_socket'], good)
        for value in ('/tmp/t.sock', '/tmp/other/t.sock', '/run/t.sock', good + 'x' * 108,
                      '/tmp/../tmp/t.sock', '/tmp/' + self.config['run_id'] + '/x/../t.sock'):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                validate_config(dict(self.config, telemetry_socket=value))
        with self.assertRaisesRegex(ConfigError, 'distinct'):
            validate_config(dict(self.config, telemetry_socket=good, display_socket=good))

    @unittest.skipUnless(os.environ.get('WKSIM_PREFLIGHT_LIVE_RESOURCES') == '1',
                         'requires selected Ubuntu overlays; no flight is launched')
    def test_telemetry_destination_present_absent_and_unsafe(self):
        with tempfile.TemporaryDirectory(prefix='wksim-' + self.config['run_id'], dir='/tmp') as directory:
            path = Path(directory) / 'telemetry.sock'
            config = dict(self.config, telemetry_socket=str(path))
            self.assertTrue(preflight(config)['ok'])
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(str(path))
                path.chmod(0o600)
                self.assertTrue(preflight(config)['ok'])
                path.chmod(0o666)
                self.assertFalse(preflight(config)['ok'])
            path.unlink()
            path.write_text('not a socket')
            self.assertFalse(preflight(config)['ok'])
            path.unlink()
            path.symlink_to(Path(directory) / 'missing')
            self.assertFalse(preflight(config)['ok'])
            path.unlink()
            Path(directory).chmod(0o755)
            self.assertFalse(preflight(config)['ok'])

    def test_unsupported_never_launches(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not spawn')):
            for name in ('invented', 'full.1', 'ticket.9.joint-clock'):
                result = preflight(dict(self.config, capabilities=[name]))
                self.assertFalse(result['ok'])
                self.assertEqual(result['reasons'][0]['code'], 'unsupported_capability')
                self.assertEqual(result['children_created'], 0)

    def test_content_identity_includes_relative_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'message.py'
            path.write_text('first')
            first = package_digest(root)
            path.write_text('second')
            self.assertNotEqual(first, package_digest(root))
            second = package_digest(root)
            path.rename(root / 'renamed.py')
            self.assertNotEqual(second, package_digest(root))

    def test_frozen_index_and_evidence(self):
        index = json.loads(INDEX.read_text(encoding='utf-8'))
        rows = index['capabilities']
        self.assertEqual(len(rows), len({r['id'] for r in rows}))
        self.assertEqual(sum(r['admitted'] for r in rows), 1)
        full = [r for r in rows if r['id'].startswith('full.')]
        self.assertEqual(len(full), 48)
        self.assertEqual(sum(r['category'] == '仿真模式逐项映射' for r in full), 12)
        self.assertEqual(sum(r['category'] == '通信模式逐项映射' for r in full), 7)
        self.assertTrue(all(not r['admitted'] and r['flown'] is None for r in full))
        for baseline in index['baselines'].values():
            self.assertEqual(digest(REPO / baseline['result']), baseline['result_sha256'])

    @unittest.skipUnless(os.environ.get('WKSIM_PREFLIGHT_LIVE_RESOURCES') == '1',
                         'requires selected Ubuntu overlays; no flight is launched')
    def test_pinned_resources_and_mismatches(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not spawn')):
            result = preflight(self.config)
            self.assertTrue(result['ok'], result['reasons'])
            self.assertEqual(result['config']['model_library'], result['identities']['model_library']['path'])
            self.assertNotIn('model_library', self.config)
            for field, value in [('ap_candidate', '/root/wksim-ap-dds-yaw-fJUTtb'),
                                 ('model_library', '/dev/null')]:
                rejected = preflight(dict(self.config, **{field: value}))
                self.assertFalse(rejected['ok'])
                self.assertEqual(rejected['children_created'], 0)
            with patch.dict(os.environ, {'AMENT_PREFIX_PATH': ''}):
                rejected = preflight(self.config)
                self.assertFalse(rejected['ok'])
                self.assertTrue(any(r['code'] == 'mixed_overlay' for r in rejected['reasons']))

    @unittest.skipUnless(os.environ.get('WKSIM_PREFLIGHT_LIVE_RESOURCES') == '1',
                         'requires selected Ubuntu overlays; no flight is launched')
    def test_display_receiver_present_absent_and_unsafe(self):
        with tempfile.TemporaryDirectory(prefix='wksim-' + self.config['run_id'], dir='/tmp') as directory:
            path = Path(directory) / 'state.sock'
            config = dict(self.config, display_socket=str(path))
            self.assertTrue(preflight(config)['ok'])
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(str(path))
                self.assertTrue(preflight(config)['ok'])
            path.unlink()
            path.write_text('not a socket')
            self.assertFalse(preflight(config)['ok'])
            path.unlink()
            path.symlink_to(Path(directory) / 'missing')
            self.assertFalse(preflight(config)['ok'])
            path.unlink()
            Path(directory).chmod(0o755)
            self.assertFalse(preflight(config)['ok'])


if __name__ == '__main__':
    unittest.main()
