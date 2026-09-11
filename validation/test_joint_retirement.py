"""Late successful ACKs fail; exited owned children remain retireable."""
from types import SimpleNamespace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from Simulator.wksim_runtime.joint_aruco_profile import TASK as ARUCO_TASK
from Simulator.wksim_runtime.joint_config import FIXED_TASKS
from Simulator.wksim_runtime.joint_runtime import (image_identity,resume_confirmed,
    validate_evidence_requests,validate_model_writer_summary)


class RetirementTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(__import__('os'),'SCHED_OTHER'),
                         'Linux scheduler API is unavailable')
    def test_model_writer_summary_binds_epoch_trace_model_and_scheduler(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);trace=root/'truth.jsonl';library=root/'model.so'
            trace.write_bytes(b'{}\n');library.write_bytes(b'model')
            sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
            summary=dict(complete=True,alive=False,closed=True,error=None,
                submitted_bytes=3,written_bytes=3,epoch='a'*32,
                truth_trace_sha256=sha(trace),model_library=str(library.resolve()),
                model_library_sha256=sha(library),writer_scheduler=dict(
                    available=True,policy='SCHED_OTHER',priority=0,
                    actual_policy=0,actual_priority=0))
            self.assertIs(validate_model_writer_summary(summary,trace,library,'a'*32),summary)
            for field,bad in (('epoch','b'*32),('truth_trace_sha256','b'*64),
                              ('model_library_sha256','b'*64),('written_bytes',True)):
                with self.subTest(field=field):
                    changed=dict(summary);changed[field]=bad
                    with self.assertRaisesRegex(ValueError,'identity or completeness'):
                        validate_model_writer_summary(changed,trace,library,'a'*32)

    def test_model_async_evidence_is_allowed_for_fixed_tasks_only(self):
        for task in FIXED_TASKS:
            self.assertIsNone(validate_evidence_requests(task,False,True))
        self.assertIsNone(validate_evidence_requests(ARUCO_TASK,True,True))
        with self.assertRaisesRegex(ValueError,'fixed PV/MIXED or ArUco'):
            validate_evidence_requests('public_position',False,True)

    def test_general_async_evidence_remains_aruco_only(self):
        with self.assertRaisesRegex(ValueError,'explicit ArUco'):
            validate_evidence_requests(FIXED_TASKS[0],True,False)

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
