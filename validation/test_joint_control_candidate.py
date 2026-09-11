"""Identity boundary tests, not simulated flight or control behavior."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import joint_control_candidate as candidate


class CandidateTests(unittest.TestCase):
    def test_source_install_and_manifest_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary); repo=base/'repo'; root=base/'candidate'; package=repo/'package'
            for directory in (package/'prometheus_control',root/'src/prometheus_control/prometheus_control',
                              root/'install/prometheus_control'/candidate.PYTHON/'prometheus_control'):
                directory.mkdir(parents=True)
                (directory/'__init__.py').write_text('')
                (directory/'node.py').write_text('VALUE = 1\n')
            for directory in (package,root/'src/prometheus_control'):
                (directory/'scripts').mkdir()
                (directory/'src').mkdir()
                (directory/'launch').mkdir()
                for name in candidate.BUILD_INPUTS:
                    (directory/name).write_text('fixture\n')
            for namespace, names in candidate.SIMULATOR_FILES.items():
                for directory in (repo/'Simulator'/namespace, root/'Simulator'/namespace,
                                  root/'install/prometheus_control'/candidate.PYTHON/'Simulator'/namespace):
                    directory.mkdir(parents=True)
                    for name in names:
                        (directory/name).write_text('fixture simulator\n')
            for source, installed_name in candidate.INSTALLED_INPUTS.items():
                installed = root/'install/prometheus_control'/installed_name
                installed.parent.mkdir(parents=True, exist_ok=True)
                installed.write_bytes((package/source).read_bytes())
            transport=root/'install/prometheus_control/lib/libwksim_rc_take.so'
            transport.parent.mkdir(parents=True, exist_ok=True)
            transport.write_bytes(b'fixture transport\n')
            (repo/'tools').mkdir()
            (repo/'tools/build-joint-control.sh').write_text('fixture build\n')
            (repo/'tools/joint_control_candidate.py').write_text('fixture sealer\n')
            (root/'build-joint-control.sh').write_text('fixture build\n')
            (root/'build.log').write_text('fixture completed\n')
            message_manifest = base/'message-build.json'
            message_manifest.write_text('sealed message fixture\n')
            message_sha256 = candidate.digest(message_manifest)
            messages = dict(version=1, root='/root/wksim-ros2-Test12', packages={})

            def check_message_fixture(path, checksum):
                if path != message_manifest or candidate.digest(path) != checksum:
                    raise ValueError('Message fixture changed')
                return messages

            with patch.object(candidate,'REPO',repo),patch.object(candidate,'PACKAGE',package),\
                    patch.object(candidate,'root_path',return_value=root),\
                    patch.object(candidate,'MESSAGE_MANIFEST',message_manifest),\
                    patch.object(candidate,'MESSAGE_SHA256',message_sha256),\
                    patch.object(candidate,'check_messages',side_effect=check_message_fixture) as check_messages:
                manifest=root/'build.json'; manifest.write_text(json.dumps(candidate.snapshot(root)))
                checksum=candidate.digest(manifest)
                record = candidate.check(manifest,checksum)
                self.assertEqual(record['version'],2)
                self.assertEqual(record['sealer_sha256'], candidate.digest(repo/'tools/joint_control_candidate.py'))
                self.assertEqual(record['message_candidate'], messages)
                self.assertEqual(record['message_manifest_path'], str(message_manifest))
                self.assertEqual(record['message_manifest_sha256'], message_sha256)
                check_messages.assert_called_with(message_manifest, message_sha256)
                self.assertEqual(messages['version'],1)  # Sealed v1 message records remain admissible.
                with self.assertRaises(ValueError): candidate.check(manifest,'0'*64)
                (repo/'tools/joint_control_candidate.py').write_text('drifted sealer\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                (repo/'tools/joint_control_candidate.py').write_text('fixture sealer\n')
                message_manifest.write_text('drifted message fixture\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                message_manifest.write_text('sealed message fixture\n')
                alternate_message_manifest = base/'alternate-message-build.json'
                alternate_message_manifest.write_text('sealed message fixture\n')
                with patch.object(candidate,'MESSAGE_MANIFEST',alternate_message_manifest):
                    with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                installed=root/'install/prometheus_control'/candidate.PYTHON/'prometheus_control/node.py'
                installed.write_text('VALUE = 2\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                installed.write_text('VALUE = 1\n')
                extra=installed.with_name('shadow.so');extra.write_bytes(b'not a permitted Python source')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                extra.unlink()
                transport.write_bytes(b'tampered transport\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                transport.write_bytes(b'fixture transport\n')
                simulator = root/'install/prometheus_control'/candidate.PYTHON/'Simulator/wksim_runtime/task.py'
                simulator.write_text('tampered simulator\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)
                simulator.write_text('fixture simulator\n')
                entrypoint = root/'install/prometheus_control/lib/prometheus_control/trajectory_bridge_node'
                entrypoint.write_text('tampered entrypoint\n')
                with self.assertRaises(ValueError): candidate.check(manifest,checksum)

    def test_candidate_root_policy(self):
        for value in ('relative','/tmp/candidate','/root/wksim-ap-clock-stop-x','/root/wksim-joint-control-../x'):
            with self.subTest(value=value),self.assertRaises(ValueError): candidate.root_path(value)


if __name__=='__main__': unittest.main()
