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

    def test_v2_control_checks_named_repo_support_and_complete_candidate_trees(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            repo=root/'repo'; candidate=root/'candidate'
            package=candidate/'install/prometheus_control'/profile.PYTHON/'prometheus_control'
            staged=candidate/'src/prometheus_control'
            current=repo/'ros2/src/prometheus_control'
            for base in (package, staged/'prometheus_control', current/'prometheus_control'):
                base.mkdir(parents=True)
                (base/'__init__.py').write_text('same')
            simulator={}
            for namespace,names in profile.CONTROL_SIMULATOR_FILES.items():
                for base in (repo/'Simulator', candidate/'Simulator',
                             candidate/'install/prometheus_control'/profile.PYTHON/'Simulator'):
                    (base/namespace).mkdir(parents=True,exist_ok=True)
                    for name in names:
                        (base/namespace/name).write_text(namespace+'/'+name)
                for name in names:
                    simulator[namespace+'/'+name]=profile.digest(repo/'Simulator'/namespace/name)
            # The repository owns many runtime modules outside the installed candidate subset.
            (repo/'Simulator/wksim_runtime/unrelated.py').write_text('not a candidate input')
            installed_targets={
                'scripts/prometheus_control_node':'lib/prometheus_control/prometheus_control_node',
                'scripts/trajectory_bridge_node':'lib/prometheus_control/trajectory_bridge_node',
                'launch/trajectory_bridge.launch.py':'share/prometheus_control/launch/trajectory_bridge.launch.py',
            }
            build_inputs={}
            for name,target in installed_targets.items():
                for base in (current,staged):
                    path=base/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(name)
                installed=candidate/'install/prometheus_control'/target
                installed.parent.mkdir(parents=True,exist_ok=True); installed.write_text(name)
                build_inputs[name]=profile.digest(current/name)
            (candidate/'build.log').write_text('built')
            (repo/'tools').mkdir(); (repo/'tools/build-joint-control.sh').write_text('builder')
            (candidate/'build-joint-control.sh').write_text('builder')
            record=dict(version=2,root=str(candidate),package=str(package),
                python_sha256={'__init__.py':profile.digest(package/'__init__.py')},
                simulator_python_sha256=simulator,build_inputs=build_inputs,
                installed_inputs={name:profile.digest(candidate/'install/prometheus_control'/target)
                                  for name,target in installed_targets.items()},
                build_log_sha256=profile.digest(candidate/'build.log'),
                build_script_sha256=profile.digest(candidate/'build-joint-control.sh'))
            with patch.object(profile,'REPO',repo):
                self.assertEqual(profile._control(record,sealed=False),str(package))
                self.assertEqual(profile._control(record,sealed=True),str(package))
                (repo/'Simulator/wksim_runtime/task.py').write_text('tampered')
                with self.assertRaisesRegex(ValueError,'Simulator support'):
                    profile._control(record,sealed=False)
                (repo/'Simulator/wksim_runtime/task.py').write_text('wksim_runtime/task.py')
                (candidate/'Simulator/wksim_runtime/extra.py').write_text('extra')
                with self.assertRaisesRegex(ValueError,'Simulator support'):
                    profile._control(record,sealed=True)
                (candidate/'Simulator/wksim_runtime/extra.py').unlink()
                (candidate/'install/prometheus_control/lib/prometheus_control/trajectory_bridge_node').write_text('tampered')
                with self.assertRaisesRegex(ValueError,'entry points'):
                    profile._control(record,sealed=True)

    def test_v1_sealed_control_requires_known_historical_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); candidate=root/'candidate'
            package=candidate/'install/prometheus_control'/profile.PYTHON/'prometheus_control'
            staged=candidate/'src/prometheus_control'
            for base in (package, staged/'prometheus_control'):
                base.mkdir(parents=True); (base/'__init__.py').write_text('same')
            (staged/'CMakeLists.txt').write_text('historical')
            (candidate/'build.log').write_text('built')
            record=dict(version=1,root=str(candidate),package=str(package),
                python_sha256={'__init__.py':profile.digest(package/'__init__.py')},
                build_inputs={'CMakeLists.txt':profile.digest(staged/'CMakeLists.txt')},
                build_log_sha256=profile.digest(candidate/'build.log'),
                build_script_sha256=next(iter(profile.LEGACY_CONTROL_BUILD_SCRIPTS)))
            self.assertEqual(profile._control(record,sealed=True),str(package))
            record['build_script_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'Unknown legacy'):
                profile._control(record,sealed=True)


if __name__=='__main__':
    unittest.main()
