"""Bounded profile admission negatives; no flight processes or installations."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime import joint_profile as profile
from Simulator.wksim_runtime.build_identity import file_identity


class JointProfileTests(unittest.TestCase):
    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            profile.select_profile('unknown')
        self.assertFalse(profile.check_profile('unknown','run')['ok'])

    def test_descriptor_copy(self):
        selected=profile.select_profile('joint_quad_dds_v1')
        selected['setup_files'].clear()
        self.assertEqual(len(profile.select_profile('joint_quad_dds_v1')['setup_files']),5)

    def test_bad_run_rejected_before_source_or_process(self):
        with patch.object(profile,'_firmware',side_effect=AssertionError('must not walk')):
            result=profile.check_profile('joint_quad_dds_v1','../bad')
        self.assertFalse(result['ok'])
        self.assertEqual(result['children_created'],0)
        self.assertIn('run_id',result['reasons'][0]['message'])

    def test_missing_ros_rejected_before_source(self):
        with patch.dict(os.environ,{'ROS_DISTRO':'wrong'}), patch.object(profile.platform,'system',return_value='Linux'), patch.object(profile,'_firmware',side_effect=AssertionError('must not walk')):
            result=profile.check_profile('joint_quad_dds_v1','run')
        self.assertFalse(result['ok'])

    def test_manifest_hash_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'build.json'; path.write_text('{}')
            pin=dict(path=str(path),sha256=profile.digest(path))
            self.assertEqual(profile._pinned_json(pin),{})
            path.write_text('{"tampered":true}')
            with self.assertRaisesRegex(ValueError,'SHA256'):
                profile._pinned_json(pin)

    def test_source_file_tamper_and_escape(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external:
            root=Path(directory); path=root/'source.py'; path.write_text('one')
            expected={'source.py':file_identity(path,root)}
            profile._files(root,expected)
            path.write_text('two')
            with self.assertRaisesRegex(ValueError,'identity'):
                profile._files(root,expected)
            path.unlink(); outside=Path(external)/'source.py'; outside.write_text('one'); path.symlink_to(outside)
            with self.assertRaisesRegex(ValueError,'escapes'):
                profile._files(root,expected)

    def test_mixed_python_overlay(self):
        with patch.object(profile.importlib.util,'find_spec',return_value=None):
            with self.assertRaisesRegex(ValueError,'mixed overlay'):
                profile._overlay('prometheus_msgs','/wrong')

    def test_firmware_source_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            record=dict(candidate_root=directory,commit='1511f27194f1dcc3728270883047bdf022b3fd53',source={'files':{}})
            with patch.object(profile,'source_snapshot',return_value={'files':{'new':{}}}):
                with self.assertRaisesRegex(ValueError,'source snapshot'):
                    profile._firmware(record,'ap')

    def test_sealed_build_inputs_belong_to_historical_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            repo=root/'repo'; candidate=root/'candidate'
            package=candidate/'install/prometheus_control'/profile.PYTHON/'prometheus_control'
            staged=candidate/'src/prometheus_control'
            current=repo/'ros2/src/prometheus_control'
            for base in (package, staged/'prometheus_control', current/'prometheus_control'):
                base.mkdir(parents=True)
                (base/'__init__.py').write_text('same')
            (staged/'CMakeLists.txt').write_text('historical build')
            (current/'CMakeLists.txt').write_text('new candidate build')
            (candidate/'build.log').write_text('built')
            (repo/'tools').mkdir(); (repo/'tools/build-joint-control.sh').write_text('builder')
            record=dict(root=str(candidate),package=str(package),
                python_sha256={'__init__.py':profile.digest(package/'__init__.py')},
                build_inputs={'CMakeLists.txt':profile.digest(staged/'CMakeLists.txt')},
                build_log_sha256=profile.digest(candidate/'build.log'),
                build_script_sha256=profile.digest(repo/'tools/build-joint-control.sh'))
            with patch.object(profile,'REPO',repo):
                self.assertEqual(profile._control(record,sealed=True),str(package))
                with self.assertRaisesRegex(ValueError,'build input'):
                    profile._control(record,sealed=False)
                (staged/'CMakeLists.txt').write_text('tampered historical build')
                with self.assertRaisesRegex(ValueError,'build input'):
                    profile._control(record,sealed=True)


if __name__=='__main__':
    unittest.main()
