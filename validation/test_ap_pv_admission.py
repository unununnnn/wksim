"""Admission boundary tests, not a real 24k-file candidate verification or flight."""
from contextlib import ExitStack
import json
from pathlib import Path
import platform
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
import ap_pv_candidate as pv


@unittest.skipUnless(platform.system() == 'Linux', 'Admission uses real absolute Linux candidate paths')
class PVAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.files = ExitStack()
        self.addCleanup(self.files.close)
        self.root = Path(self.files.enter_context(tempfile.TemporaryDirectory(prefix='wksim-ap-pv-test-', dir='/root')))
        self.manifest = self.root / 'pv-build.json'
        self.control_root = Path(self.files.enter_context(tempfile.TemporaryDirectory(prefix='wksim-joint-control-', dir='/root')))
        self.control_manifest = self.control_root / 'build.json'
        self.control = dict(root=str(self.control_root), package=str(self.control_root / 'installed-control'))
        self.control_manifest.write_text(json.dumps(self.control))
        self.control_sha = pv.joint.digest(self.control_manifest)
        self.profile = pv.joint.select_profile('joint_quad_dds_v1')
        self.record = dict(status='built-not-admitted', candidate_root=str(self.root),
                           binary=str(self.root / 'build/sitl/bin/arducopter'),
                           source_unchanged_during_build=True, fixed_baseline_unchanged=True,
                           **{name: 'a' * 64 for name in ('binary_sha256', 'source_manifest_sha256',
                              'patch_sha256', 'baseline_manifest_sha256', 'configure_log_sha256', 'build_log_sha256')})
        self.record['baseline_manifest_sha256'] = self.profile['manifests']['ap']['sha256']
        self.seal()

    def seal(self):
        self.manifest.write_text(json.dumps(self.record))
        self.sha = pv.joint.digest(self.manifest)

    def admit(self, run_id='pv-admission-test'):
        return pv.admit(str(self.manifest), self.sha, str(self.control_manifest), self.control_sha, run_id)

    def expensive_checks(self):
        """Only source/resource verification is stubbed; selectors/JSON/config stay real."""
        mocks = {}
        for name, value in (('verify', dict(baseline_manifest_sha256=self.record['baseline_manifest_sha256'])),
                            ('_fixed_resources', {'verified_baseline': True}), ('check_control', self.control)):
            mocks[name] = self.files.enter_context(patch.object(pv, name, return_value=value))
        return mocks

    def test_run_identity_rejected_before_verifiers(self):
        mocks = self.expensive_checks()
        result = self.admit('../bad')
        self.assertFalse(result['ok'])
        self.assertIn('run_id', result['reasons'][0]['message'])
        for mock in mocks.values():
            mock.assert_not_called()

    def test_path_hash_and_schema_refusal(self):
        with self.assertRaisesRegex(ValueError, 'Expected'):
            pv._pv_record(self.root / 'wksim-build.json', self.sha)
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            pv._pv_record(self.manifest, '0' * 64)
        self.record['schema_version'] = 1
        self.seal()
        with self.assertRaisesRegex(ValueError, 'schema'):
            pv._pv_record(self.manifest, self.sha)

    def test_unchanged_flags_are_actual_booleans(self):
        for key in ('source_unchanged_during_build', 'fixed_baseline_unchanged'):
            self.record[key] = 1
            self.seal()
            with self.assertRaisesRegex(ValueError, 'assertions'):
                pv._pv_record(self.manifest, self.sha)
            self.record[key] = True

    def test_symlink_manifest_rejected(self):
        saved = self.root / 'saved.json'
        self.manifest.rename(saved)
        self.manifest.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            pv._pv_record(self.manifest, self.sha)

    def test_duplicate_control_json_rejected_before_source_walk(self):
        mocks = self.expensive_checks()
        self.control_manifest.write_text('{"root":"one","root":"two"}')
        self.control_sha = pv.joint.digest(self.control_manifest)
        result = self.admit()
        self.assertFalse(result['ok'])
        self.assertIn('Duplicate', result['reasons'][0]['message'])
        mocks['verify'].assert_not_called()

    def test_acceptance_owns_candidates_without_production_promotion(self):
        mocks = self.expensive_checks()
        before = pv.joint.PROFILES.read_bytes()
        result = self.admit()
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['production_admitted'])
        self.assertFalse(result['flown'])
        self.assertEqual(result['children_created'], 0)
        self.assertEqual(result['configs']['arducopter']['ap_candidate'], str(self.root))
        self.assertEqual(result['configs']['px4']['px4_root'], str(Path(self.profile['manifests']['px4']['path']).parent / 'src'))
        self.assertEqual(result['model_library'], self.profile['model_library'])
        self.assertEqual(result['control_candidate'], self.control)
        for config in result['configs'].values():
            self.assertNotIn('runtime_profile', config)
            self.assertEqual(config['dds_workspace'], self.profile['dds_workspace'])
            self.assertEqual(config['prometheus_workspace'], self.profile['control_workspace'])
        self.assertEqual(result['capability']['arducopter_type_mask'], 2496)
        self.assertEqual(before, pv.joint.PROFILES.read_bytes())
        mocks['verify'].assert_called_once_with(str(self.manifest), self.sha)
        mocks['_fixed_resources'].assert_called_once_with(self.profile)
        mocks['check_control'].assert_called_once_with(str(self.control_manifest), self.control_sha)

    def test_every_identity_failure_refuses_all_launch_configs(self):
        mocks = self.expensive_checks()
        for name, mock in mocks.items():
            mock.side_effect = ValueError(name + ' mismatch')
            result = self.admit()
            self.assertFalse(result['ok'])
            self.assertEqual(result['configs'], {})
            self.assertIsNone(result['control_candidate'])
            self.assertFalse(result['production_admitted'])
            mock.side_effect = None

    def test_old_control_cannot_be_selected_as_new_candidate(self):
        self.expensive_checks()
        self.control['root'] = self.profile['control_workspace']
        result = self.admit()
        self.assertFalse(result['ok'])
        self.assertIn('separate', result['reasons'][0]['message'])


class SealedControlTests(unittest.TestCase):
    def test_old_source_and_build_checks_remain_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            repo, root = base / 'repo', base / 'old-control'
            staged = root / 'src/prometheus_control'
            package = root / 'install/prometheus_control' / pv.joint.PYTHON / 'prometheus_control'
            source = repo / 'ros2/src/prometheus_control'
            inputs = ('CMakeLists.txt', 'package.xml', 'scripts/prometheus_control_node')
            paths = [staged / 'prometheus_control/node.py', package / 'node.py',
                     source / 'prometheus_control/node.py', root / 'build.log', repo / 'tools/build-joint-control.sh']
            paths += [directory / name for directory in (staged, source) for name in inputs]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('sealed')
            # Current Python deliberately differs: its ownership is the NEW check_control branch.
            (source / 'prometheus_control/node.py').write_text('new candidate')
            record = dict(root=str(root), package=str(package),
                          python_sha256={'node.py': pv.joint.digest(package / 'node.py')},
                          build_inputs={name: pv.joint.digest(staged / name) for name in inputs},
                          build_log_sha256=pv.joint.digest(root / 'build.log'),
                          build_script_sha256=pv.joint.digest(repo / 'tools/build-joint-control.sh'))
            with patch.object(pv, 'REPO', repo):
                self.assertEqual(pv._sealed_control(record), str(package))
                for path in paths:
                    if path == source / 'prometheus_control/node.py':
                        continue
                    with self.subTest(path=str(path)):
                        path.write_text('tampered')
                        with self.assertRaises(ValueError):
                            pv._sealed_control(record)
                        path.write_text('sealed')
                for directory in (staged / 'prometheus_control', package):
                    extra = directory / 'unexpected.py'
                    extra.write_text('new')
                    with self.assertRaisesRegex(ValueError, 'file set'):
                        pv._sealed_control(record)
                    extra.unlink()


if __name__ == '__main__':
    unittest.main()
