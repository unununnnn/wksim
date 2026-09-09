"""Mixed experimental admission boundaries; no build or flight proof."""
from contextlib import ExitStack
import json
from pathlib import Path
import platform
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import ap_mixed_candidate as mixed


@unittest.skipUnless(platform.system() == 'Linux', 'native absolute Linux paths')
class MixedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.files = ExitStack(); self.addCleanup(self.files.close)
        self.root = Path(self.files.enter_context(tempfile.TemporaryDirectory(prefix='wksim-ap-mixed-test-', dir='/root')))
        self.path = self.root/'mixed-build.json'
        self.record = dict(schema_version=1, status='built-not-admitted', profile=mixed.PROFILE,
            candidate_root=str(self.root), baseline_root=str(mixed.BASE), baseline_manifest_sha256=mixed.BASE_SHA,
            source_manifest_sha256='a'*64, patch_sha256='b'*64, artifacts={}, source_unchanged_during_build=True,
            fixed_pv_baseline_unchanged=True, production_admitted=False, flown=False)
        self.control_root = Path(self.files.enter_context(tempfile.TemporaryDirectory(prefix='wksim-joint-control-', dir='/root')))
        self.control_path = self.control_root/'build.json'
        self.control = dict(root=str(self.control_root), package=str(self.control_root/'package'))
        self.control_path.write_text(json.dumps(self.control))
        self.control_sha = mixed.sha(self.control_path.read_bytes())

    def write(self, value):
        self.path.write_text(json.dumps(value))
        return mixed.sha(self.path.read_bytes())

    def test_wrong_schema_identity_and_scope_rejected_before_source_walk(self):
        for change in (dict(schema_version=True), dict(profile='full_xyz_pv_yaw_v1'), dict(status='admitted'),
                       dict(flown=True), dict(production_admitted=True), dict(source_unchanged_during_build=1),
                       dict(fixed_pv_baseline_unchanged=1), dict(candidate_root='/root/elsewhere'), dict(extra=True)):
            with self.subTest(change=change), patch.object(mixed, 'source_snapshot', side_effect=AssertionError('source walk')):
                checksum = self.write(dict(self.record, **change))
                with self.assertRaises(ValueError):
                    mixed.verify(self.path, checksum)
        checksum = self.write(self.record)
        with self.assertRaises(ValueError):
            mixed.verify(self.path, 'f'*64)
        with self.assertRaises(ValueError):
            mixed.verify('/root/wksim-ap-pv-vn04950x/mixed-build.json', checksum)

    def test_symlink_manifest_is_not_a_new_candidate(self):
        original = self.root/'original.json'
        original.write_text(json.dumps(self.record))
        self.path.symlink_to(original)
        with self.assertRaises(ValueError):
            mixed.verify(self.path, mixed.sha(original.read_bytes()))

    def test_admission_fails_closed_and_owns_the_new_control(self):
        p = mixed.joint.select_profile('joint_quad_dds_v1')
        native = dict(candidate=self.record, baseline_verification=dict(baseline_manifest_sha256=p['manifests']['ap']['sha256']))
        with patch.object(mixed, 'verify', return_value=native), patch.object(mixed, '_fixed_resources', return_value={}), \
                patch.object(mixed, 'check_control', return_value=self.control):
            report = mixed.admit(str(self.path), 'a'*64, str(self.control_path), self.control_sha, 'mixed-unit')
            self.assertTrue(report['ok'])
            self.assertFalse(report['production_admitted']); self.assertFalse(report['flown'])
            self.assertEqual(report['configs']['arducopter']['ap_candidate'], str(self.root))
            self.assertNotIn('runtime_profile', report['configs']['arducopter'])
            for function in ('verify', '_fixed_resources', 'check_control'):
                with self.subTest(function=function), patch.object(mixed, function, side_effect=ValueError('changed identity')):
                    report = mixed.admit(str(self.path), 'a'*64, str(self.control_path), self.control_sha, 'mixed-unit')
                    self.assertFalse(report['ok']); self.assertEqual(report['configs'], {})
                    self.assertEqual(report['children_created'], 0)
            with patch.object(mixed, 'check_control', return_value=dict(root=p['control_workspace'])):
                self.assertFalse(mixed.admit(str(self.path), 'a'*64, str(self.control_path), self.control_sha, 'mixed-unit')['ok'])

    def test_invalid_run_cannot_start_verification(self):
        with patch.object(mixed, 'verify', side_effect=AssertionError('verification began')):
            report = mixed.admit(str(self.path), 'a'*64, str(self.control_path), self.control_sha, '../bad')
            self.assertFalse(report['ok']); self.assertEqual(report['configs'], {})

    def test_pv_task_keeps_true_mixed_verification_and_exact_final_pins(self):
        p = mixed.joint.select_profile('joint_quad_dds_v1')
        native = dict(candidate=self.record, baseline_verification=dict(baseline_manifest_sha256=p['manifests']['ap']['sha256']))
        with patch.object(mixed, 'verify', return_value=native) as verify, \
                patch.object(mixed, '_fixed_resources', return_value={}), \
                patch.object(mixed, 'checked_json'), patch.object(mixed, 'check_control', return_value=self.control):
            report = mixed.admit(str(self.path), mixed.FINAL_AP_SHA, str(self.control_path), mixed.FINAL_CONTROL_SHA,
                                 'pv-mixed-unit', task_profile=mixed.PV_PROFILE)
            self.assertTrue(report['ok'], report['reasons'])
            self.assertEqual(report['task_profile'], mixed.PV_PROFILE)
            self.assertEqual(report['candidate']['profile'], mixed.PROFILE)
            self.assertIs(report['identities']['ap_mixed'], native)
            self.assertNotIn('ap_pv', report['identities'])
            self.assertEqual(report['capability']['arducopter_type_mask'], 2496)
            for task, ap_sha, control_sha in ((mixed.PV_PROFILE, 'a'*64, mixed.FINAL_CONTROL_SHA),
                    (mixed.PV_PROFILE, mixed.FINAL_AP_SHA, 'a'*64), ('position', mixed.FINAL_AP_SHA, mixed.FINAL_CONTROL_SHA)):
                verify.reset_mock()
                rejected = mixed.admit(str(self.path), ap_sha, str(self.control_path), control_sha,
                                       'pv-mixed-unit', task_profile=task)
                self.assertFalse(rejected['ok']); self.assertEqual(rejected['children_created'], 0)
                verify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
