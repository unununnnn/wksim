"""Late successful ACKs fail; exited owned children remain retireable."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from Simulator.wksim_runtime.joint_runtime import image_identity,resume_confirmed


class RetirementTests(unittest.TestCase):
    def test_resume_rejects_success_at_or_after_deadline(self):
        lifecycle=SimpleNamespace(acknowledged=lambda:True,acks={1:dict(source_boot_ns=9)})
        request=dict(began=10.,frozen_ns=8)
        for now in (15.,15.001):
            with self.subTest(now=now),patch('Simulator.wksim_runtime.joint_runtime.time.monotonic',return_value=now):
                with self.assertRaises(TimeoutError):resume_confirmed(lifecycle,SimpleNamespace(tick=4),request)
        with patch('Simulator.wksim_runtime.joint_runtime.time.monotonic',return_value=14.999):
            self.assertTrue(resume_confirmed(lifecycle,SimpleNamespace(tick=4),request))

    def test_exited_child_has_explicit_missing_image_without_reading_reused_pid(self):
        child=Mock(pid=42);child.poll.return_value=-9
        original=dict(pid=42,pgid=40,start_ticks=123)
        with patch('Simulator.wksim_runtime.joint_runtime.json_identity',side_effect=AssertionError('reused PID read')):
            result=image_identity(child,original,allow_exited=True)
        self.assertEqual(result,dict(state='exited',identity=original,returncode=-9,maps_available=False))

    def test_live_replacement_is_rejected_even_during_retirement(self):
        child=Mock(pid=42);child.poll.return_value=None
        original=dict(pid=42,pgid=40,start_ticks=123)
        with patch('Simulator.wksim_runtime.joint_runtime.json_identity',return_value=dict(original,start_ticks=124)):
            with self.assertRaises(RuntimeError):image_identity(child,original,allow_exited=True)


if __name__=='__main__':unittest.main()
