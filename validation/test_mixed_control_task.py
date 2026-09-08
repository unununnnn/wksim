"""Task plumbing checks with real ROS codecs; no simulated or real flight."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tools.mixed_control_task import MixedTask, PROFILE


class MixedTaskTests(unittest.TestCase):
    def test_hold_readiness_resets_after_relapse_and_has_wall_bound(self):
        task = MixedTask.__new__(MixedTask)
        seconds = [0., .5, 1., 1.5, 2., 2.5, 3.]
        good = [True, True, False, True, True, True, True]
        current = 0
        task.task_time = lambda: seconds[current]
        def wait(label, ready, timeout):
            nonlocal current
            for current in range(len(seconds)):
                if ready():
                    return
            self.fail('No continuously stable window')
        task.wait = wait
        with patch('tools.mixed_control_task.time.monotonic', side_effect=[0., *seconds]):
            record = task.stable_hold('zero', lambda: good[current])
        self.assertEqual((record['stable_from_s'], record['ready_s']), (1.5, 3.))
        with patch('tools.mixed_control_task.time.monotonic', side_effect=[0., 13.]):
            with self.assertRaises(TimeoutError):
                task.stable_hold('zero', lambda: True)

    def test_mixed_selectors_do_not_silently_select_another_firmware(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, '-B', str(root/'tools/run_joint_flight.py'), 'run',
            '--control-manifest', 'unopened.json', '--control-sha256', 'a'*64, '--task-profile', PROFILE]
        valid = ['--ap-mixed-manifest', 'unopened-mixed.json', '--ap-mixed-sha256', 'b'*64]
        for extra in ([], valid+['--ap-manifest', 'old.json'], valid+['--ap-pv-manifest', 'pv.json'],
                      valid+['--dds-loss', 'px4'], valid+['--scene-lifecycle']):
            result = subprocess.run(command+extra, cwd=root, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
            self.assertIn('error:', result.stderr)
            self.assertNotIn('archive', result.stdout)

    @unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS') == '1', 'requires generated ROS codec')
    def test_body_uses_captured_reference_instead_of_recomputing_it(self):
        from prometheus_msgs.msg import UAVCommand
        from rclpy.serialization import serialize_message, deserialize_message
        from rosidl_runtime_py.convert import message_to_ordereddict
        task = MixedTask.__new__(MixedTask)
        task.Cmd, task.sent, task.events = UAVCommand, [], []
        task.request_id = task.command_id = 0
        capture = dict(event='mixed_body_reference_captured', request_id=1, command_id=1,
            reference_position=[0., 0., 4.], reference_velocity=[.43, .78, 0.], reference_yaw=.9,
            source_position=[3., 2., 3.], source_yaw=.6, shaped_position=[None, None, 4.])
        def offer(label, **fields):
            task.request_id += 1; task.command_id += 1
            message = UAVCommand(command_id=task.command_id, **fields)
            task.sent.append(message_to_ordereddict(deserialize_message(serialize_message(message), UAVCommand)))
            task.events.append(capture)
        task.offer = offer
        task.wait = lambda label, predicate, timeout: self.assertTrue(predicate())
        reference = task.mixed('body_unit', (.8, .4), 1., .3, body=True)
        self.assertEqual(reference['velocity'], [.43, .78])
        self.assertEqual(reference['altitude'], 4.)
        self.assertEqual(reference['yaw'], .9)
        self.assertEqual(task.sent[0]['move_mode'], UAVCommand.XY_VEL_Z_POS_BODY)
        self.assertEqual(task.sent[0]['position_ref'], [0., 0., 1.])
        self.assertEqual(task.sent[0]['velocity_ref'][2], 0.)
        json.dumps(reference, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
