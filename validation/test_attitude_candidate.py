"""Admission boundary tests; temporary fixtures only, no nodes or fixed-resource writes."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'tools'))
import attitude_candidate as candidate


class AdmissionTests(unittest.TestCase):
    def test_invalid_selectors_stop_before_resource_probes(self):
        for stack, run_id in (('joint', 'run'), ('px4', '../run'), ('arducopter', ''), ('px4', 'a'*65)):
            with self.subTest(stack=stack, run_id=run_id), patch.object(candidate, 'native_check') as native:
                report = candidate.admit(stack, run_id)
                self.assertFalse(report['ok'])
                self.assertTrue(report['reasons'])
                self.assertEqual(report['children_created'], 0)
                self.assertEqual(report['config'], {})
                native.assert_not_called()

    def test_configuration_explicitly_selects_candidate_without_production_profile(self):
        profile = candidate.joint.select_profile('joint_quad_dds_v1')
        for stack in ('px4', 'arducopter'):
            config = candidate.candidate_config(stack, 'bounded-attitude', profile)
            self.assertNotIn('runtime_profile', config)
            self.assertEqual(config['prometheus_workspace'], str(candidate.CONTROL))
            self.assertEqual(config['capabilities'], ['attitude_thrust_v1'])
            self.assertEqual(config['stack'], stack)
            if stack == 'arducopter':
                self.assertEqual(config['ap_candidate'], str(candidate.NATIVE))
            else:
                self.assertNotIn('ap_candidate', config)

    def test_strict_json_rejects_hash_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve()/'manifest.json'
            for raw in (b'{"ok":true,"ok":false}', b'{"value":NaN}'):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    candidate.checked_json(path, hashlib.sha256(raw).hexdigest())
            path.write_text('{"ok":true}')
            with self.assertRaisesRegex(ValueError, 'SHA256 differs'):
                candidate.checked_json(path, '0'*64)

    def test_full_file_set_and_contents_are_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root/'node.py').write_text('baseline')
            sealed = candidate.tree_hashes(root)
            candidate.check_files(root, sealed)
            (root/'node.py').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'Artifact differs'):
                candidate.check_files(root, sealed)
            (root/'node.py').write_text('baseline')
            (root/'injected.py').write_text('extra')
            self.assertNotEqual(candidate.tree_hashes(root), sealed)
            with self.assertRaisesRegex(ValueError, 'Invalid sealed relative path'):
                candidate.check_files(root, {'../escape':'0'*64})

    def test_reviewed_patch_identity_never_uses_current_repository_equality(self):
        before = {'prometheus_control/node.py':'old', 'CMakeLists.txt':'build'}
        entries = [dict(kind='control', path='ros2/src/prometheus_control/prometheus_control/node.py',
                        baseline_sha256='old', staged_sha256='reviewed')]
        after = dict(before, **{'prometheus_control/node.py':'reviewed'})
        candidate.reviewed_files(before, after, entries, 'control')
        for changed in (dict(after, extra='new'), dict(after, **{'CMakeLists.txt':'unreviewed'}), before):
            with self.assertRaises(ValueError):
                candidate.reviewed_files(before, changed, entries, 'control')

    def test_internal_links_cannot_escape_and_sealed_cache_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root/'data').write_text('sealed')
            (root/'__pycache__').mkdir()
            (root/'__pycache__/data.pyc').write_bytes(b'sealed cache')
            self.assertEqual(set(candidate.tree_hashes(root)), {'data'})
            self.assertEqual(set(candidate.tree_hashes(root, include_cache=True)), {'data', '__pycache__/data.pyc'})
            try:
                (root/'link').symlink_to(root/'data')
            except OSError:
                self.skipTest('This host cannot create fixture symlinks')
            with self.assertRaisesRegex(ValueError, 'Symlinked tree path'):
                candidate.tree_hashes(root)
            self.assertIn('link', candidate.tree_hashes(root, internal_links=True))
            (root/'link').unlink()
            (root/'link').symlink_to(Path(__file__).resolve())
            with self.assertRaisesRegex(ValueError, 'Escaping tree path'):
                candidate.tree_hashes(root, internal_links=True)

    def test_baseline_probe_is_clean_and_failure_is_never_a_bypass(self):
        process = type('Process', (), dict(returncode=2, stdout='{"ok":true}', stderr='old overlay mismatch'))()
        with patch.object(candidate.subprocess, 'run', return_value=process) as run:
            with self.assertRaisesRegex(ValueError, 'old overlay mismatch'):
                candidate.clean_probe('baseline', ['/opt/ros/humble/setup.bash'])
        args, kwargs = run.call_args
        self.assertEqual(args[0][:3], ['/bin/bash', '--noprofile', '--norc'])
        self.assertNotIn('PYTHONPATH', kwargs['env'])
        self.assertNotIn('AMENT_PREFIX_PATH', kwargs['env'])
        self.assertNotIn('LD_PRELOAD', kwargs['env'])
        self.assertIn('--probe baseline', args[0][-1])
        self.assertNotIn('preflight', args[0][-1])

    def test_rejected_resource_has_no_partial_success_config(self):
        with patch.object(candidate, 'checked_json', return_value={}), \
                patch.object(candidate, 'native_check', side_effect=ValueError('sealed native mismatch')), \
                patch.object(candidate, 'clean_probe') as probe:
            report = candidate.admit('px4', 'bounded')
        self.assertFalse(report['ok'])
        self.assertEqual(report['config'], {})
        self.assertEqual(report['setup_files'], [])
        self.assertFalse(report['production_admitted'])
        self.assertIn('sealed native mismatch', report['reasons'][0]['message'])
        probe.assert_not_called()

    def test_active_import_checks_reject_wrong_overlay_before_importing_modules(self):
        with patch.object(candidate.joint, '_overlay', side_effect=ValueError('Python mixed overlay')), \
                patch.object(candidate.importlib, 'import_module') as imported:
            with self.assertRaisesRegex(ValueError, 'mixed overlay'):
                candidate.check_active_overlays()
        imported.assert_not_called()


if __name__ == '__main__':
    unittest.main()
