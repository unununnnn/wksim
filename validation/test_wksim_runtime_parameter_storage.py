"""Maintenance storage integration without FC, ROS nodes or physics launches."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from Simulator.wksim_runtime import parameter_storage, runtime
from validation.test_wksim_runtime import config


class StorageLaunchTests(unittest.TestCase):
    def test_human_duration_changes_only_the_bounded_physics_lifetime(self):
        original=runtime.launch_spec(config(),Path('/tmp/run'),Path('/tmp/model.so'))
        extended=runtime.launch_spec(config(),Path('/tmp/run'),Path('/tmp/model.so'),physics_duration=3600)
        index=extended['physics'].index('--duration')+1
        self.assertEqual(extended['physics'][index],'3600')
        extended['physics'][index]='600'
        self.assertEqual(extended,original)
        for duration in (True,599,3601,float('nan')):
            with self.assertRaises(ValueError):
                runtime.launch_spec(config(),Path('/tmp/run'),Path('/tmp/model.so'),physics_duration=duration)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                runtime.run(config(),Path(root)/'unused',physics_duration=3600)
            self.assertFalse((Path(root)/'unused').exists())

    def test_only_fc_working_directory_changes(self):
        for stack in ('arducopter', 'px4'):
            original = runtime.launch_spec(config(stack), Path('/tmp/run'), Path('/tmp/model.so'))
            retained = runtime.launch_spec(config(stack), Path('/tmp/run'), Path('/tmp/model.so'),
                                           fc_directory=Path('/tmp/retained'))
            self.assertEqual(retained.pop('fc_cwd'), str(Path('/tmp/retained')))
            if stack == 'px4':
                index = retained['fc'].index('-w') + 1
                self.assertEqual(retained['fc'][index], str(Path('/tmp/retained')))
                retained['fc'][index] = original['fc'][index]
            self.assertEqual(retained, original)

    def test_storage_requires_explicit_task_before_launch_or_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime.subprocess, 'Popen') as launch:
            output = Path(directory) / 'unused'
            with self.assertRaisesRegex(ValueError, 'maintenance task'):
                runtime.run(config(), output, parameter_storage=object())
            self.assertFalse(output.exists())
            launch.assert_not_called()

    @unittest.skipUnless(sys.platform == 'linux', 'POSIX parameter storage lease')
    def test_real_lease_snapshot_and_scope_rejection(self):
        cfg = dict(config('arducopter'), control_protocol='session_v1',
                   runtime_profile='independent_quad_dds_v1', capabilities=['native_position_mission'])
        with tempfile.TemporaryDirectory() as directory, patch.object(parameter_storage, 'ROOT', Path(directory)):
            with parameter_storage.ParameterStorage(str(uuid4()), 'arducopter') as lease:
                before = runtime.parameter_storage_metadata(cfg, lease)
                self.assertEqual(before['parameter_files'], {})
                (lease.path / 'eeprom.bin').write_bytes(b'fixture retained parameter bytes')
                after = runtime.parameter_storage_metadata(cfg, lease)
                self.assertEqual(before['directory_identity'], after['directory_identity'])
                self.assertEqual(after['parameter_files']['eeprom.bin']['sha256'],
                                 hashlib.sha256(b'fixture retained parameter bytes').hexdigest())
                for fields in ({'mission': {'waypoints': []}}, {'telemetry_socket': '/tmp/t.sock'},
                               {'promotion_flight': True}, {'model_promotion_flight': True},
                               {'runtime_profile': 'other'}):
                    with self.subTest(fields=fields), self.assertRaises(ValueError):
                        runtime.parameter_storage_metadata(dict(cfg, **fields), lease)
            with self.assertRaisesRegex(ValueError, 'closed'):
                runtime.parameter_storage_metadata(cfg, lease)


if __name__ == '__main__':
    unittest.main()
