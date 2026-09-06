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
    def setUp(self):
        self.config = load_config(INDEX.parent / 'examples/arducopter.json')

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
