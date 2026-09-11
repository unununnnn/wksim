"""Identity and environment tests for an explicit message overlay."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import joint_message_candidate as candidate
from tools import run_joint_flight as runner


class MessageCandidateTests(unittest.TestCase):
    def fixture(self, base):
        repo, root, evidence = base/'repo', base/'wksim-ros2-Test12', base/'repo/validation/prometheus-ros2-test'
        for name in candidate.PACKAGES:
            for directory in (repo/'ros2/src'/name, root/'src'/name):
                directory.mkdir(parents=True)
                (directory/'package.xml').write_text(name)
            prefix = root/'install'/name
            prefix.mkdir(parents=True)
            (prefix/'installed').write_text(name)
        for directory in (repo/'ros2/src/wksim_msgs/msg', root/'src/wksim_msgs/msg'):
            directory.mkdir()
            (directory/'SessionState.msg').write_text('uint32 command_high_water\n')
        generated = root/'install/wksim_msgs'/candidate.PYTHON/'wksim_msgs/msg/_session_state.py'
        generated.parent.mkdir(parents=True)
        generated.write_text('command_high_water = 0\n')
        (repo/'tools').mkdir()
        (repo/'tools/build-prometheus-ros2.sh').write_text('build\n')
        evidence.mkdir(parents=True)
        (evidence/'workspace.txt').write_text(str(root)+'\n')
        (evidence/'exit-code.txt').write_text('0\n')
        (evidence/'result.json').write_text(json.dumps(dict(status='pass', workspace=str(root))))
        for name in candidate.EVIDENCE_FILES[3:]:
            (evidence/name).write_text(name+'\n')
        return repo, root, evidence

    def test_source_install_evidence_and_environment_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, root, evidence = self.fixture(Path(temporary))
            with patch.object(candidate, 'REPO', repo), patch.object(candidate, 'root_path', return_value=root), \
                    patch.object(candidate, 'package_digest', side_effect=lambda p, complete: 'installed-'+Path(p).name):
                value = candidate.snapshot(root, evidence)
                manifest = root/'message-build.json'
                manifest.write_text(json.dumps(value))
                checksum = candidate.digest(manifest)
                self.assertEqual(candidate.check(manifest, checksum), value)
                env = candidate.environment(value, {'PYTHONPATH':'old-python', 'AMENT_PREFIX_PATH':'old-ament',
                                                    'LD_LIBRARY_PATH':'old-lib'})
                self.assertTrue(env['PYTHONPATH'].startswith(str(root/'install/prometheus_msgs'/candidate.PYTHON)))
                self.assertTrue(env['AMENT_PREFIX_PATH'].startswith(str(root/'install/prometheus_msgs')))
                self.assertTrue(env['LD_LIBRARY_PATH'].startswith(str(root/'install/prometheus_msgs/lib')))
                (root/'src/wksim_msgs/msg/SessionState.msg').write_text('tampered\n')
                with self.assertRaises(ValueError):
                    candidate.check(manifest, checksum)
                (root/'src/wksim_msgs/msg/SessionState.msg').write_text('uint32 command_high_water\n')
                (evidence/'exit-code.txt').write_text('1\n')
                with self.assertRaises(ValueError):
                    candidate.check(manifest, checksum)

    def test_root_policy(self):
        for value in ('relative', '/tmp/wksim-ros2-x', '/root/not-messages'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                candidate.root_path(value)

    def test_runner_prepends_message_overlay_after_control_environment(self):
        control = {'root': '/root/control'}
        messages = {'root': '/root/messages'}
        control_env = {'PYTHONPATH': 'control'}
        message_env = {'PYTHONPATH': 'messages:control'}
        with patch.object(runner, 'control_environment', return_value=control_env) as control_call, \
                patch.object(runner, 'message_environment', return_value=message_env) as message_call:
            self.assertEqual(runner.candidate_environment(control, messages), message_env)
        control_call.assert_called_once_with(control)
        message_call.assert_called_once_with(messages, control_env)
        with patch.object(runner, 'control_environment', return_value=control_env), \
                patch.object(runner, 'message_environment') as message_call:
            self.assertEqual(runner.candidate_environment(control), control_env)
        message_call.assert_not_called()

    def test_runner_activates_and_records_candidate_module_origins(self):
        control = {'package': '/candidate/python/prometheus_control'}
        messages = {'packages': {
            'prometheus_msgs': {'prefix': '/candidate/prometheus_msgs'},
            'wksim_msgs': {'prefix': '/candidate/wksim_msgs'},
        }}
        env = {'PYTHONPATH': os.pathsep.join(['/new/one', '/new/two']),
               'AMENT_PREFIX_PATH': '/new/ament', 'LD_LIBRARY_PATH': '/new/lib'}
        specs = {
            'prometheus_control': '/candidate/python/prometheus_control/__init__.py',
            'prometheus_msgs': '/candidate/prometheus_msgs/local/lib/python3.10/dist-packages/prometheus_msgs/__init__.py',
            'wksim_msgs': '/candidate/wksim_msgs/local/lib/python3.10/dist-packages/wksim_msgs/__init__.py',
        }
        from types import SimpleNamespace
        with patch.dict(os.environ, {}, clear=False), \
                patch.object(runner, 'candidate_environment', return_value=env), \
                patch.object(runner.importlib.util, 'find_spec',
                             side_effect=lambda name: SimpleNamespace(origin=specs[name])), \
                patch.object(runner.Path, 'resolve', lambda self: self):
            old_path = list(runner.sys.path)
            try:
                observed = runner.activate_candidate_imports(control, messages)
                self.assertEqual(runner.sys.path[:2], ['/new/one', '/new/two'])
                self.assertEqual(os.environ['AMENT_PREFIX_PATH'], '/new/ament')
            finally:
                runner.sys.path[:] = old_path
        self.assertEqual(observed['prometheus_control'], str(Path(control['package'])))


if __name__ == '__main__':
    unittest.main()
