"""Late successful ACKs fail; exited owned children remain retireable."""
from types import SimpleNamespace
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch

from Simulator.wksim_runtime.joint_aruco_profile import TASK as ARUCO_TASK
from Simulator.wksim_runtime.joint_config import FIXED_TASKS
from Simulator.wksim_runtime import joint_runtime
from Simulator.wksim_runtime.joint_runtime import (image_identity,resume_confirmed,
    validate_evidence_requests,validate_model_writer_summary)


class RetirementTests(unittest.TestCase):
    def test_manager_scheduler_always_sets_reset_on_fork(self):
        calls=[]
        fake_os=SimpleNamespace(SCHED_FIFO=1,SCHED_RESET_ON_FORK=0x40000000,
            sched_param=lambda value: ('sched_param',value),
            sched_setscheduler=lambda *args: calls.append(args),
            sched_getscheduler=lambda _pid: 0x40000001,
            sched_getparam=lambda _pid: SimpleNamespace(sched_priority=50))
        with patch.object(joint_runtime, 'os', fake_os):
            value=joint_runtime._set_manager_scheduler()
        self.assertEqual(calls,[(0,0x40000001,fake_os.sched_param(50))])
        self.assertTrue(value['reset_on_fork'])
        self.assertEqual(value['actual_policy'],0x40000001)

    def test_launch_helper_popen_has_no_preexec_fn(self):
        child=Mock(pid=123)
        popen=Mock(return_value=child)
        with patch.object(joint_runtime.subprocess,'Popen',popen):
            result,observation=joint_runtime._launch_child(
                ['preflight'],Path('.'),Mock(),'preflight',lambda _child: 'ordinary')
        self.assertIs(result,child)
        self.assertEqual(observation,'ordinary')
        self.assertNotIn('preexec_fn',popen.call_args.kwargs)

    def test_preflight_scheduler_mismatch_is_reaped_before_native_launch(self):
        child=Mock(pid=123)
        child.poll.return_value=None
        popen=Mock(return_value=child)
        log=Mock()
        native_launch=Mock()
        mismatch=dict(policy='SCHED_FIFO',policy_value=1,priority=50,nice=-10)
        fake_os=SimpleNamespace(SCHED_OTHER=0)
        with patch.object(joint_runtime,'os',fake_os), \
                patch.object(joint_runtime.subprocess,'Popen',popen):
            try:
                joint_runtime._launch_child(
                    ['preflight'],Path('.'),log,'preflight',
                    lambda child: joint_runtime._require_preflight_scheduler(child.pid,mismatch))
            except RuntimeError as error:
                self.assertIn('demotion failed',str(error))
            else:
                native_launch()
        child.terminate.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=5)
        log.close.assert_called_once_with()
        native_launch.assert_not_called()

    def test_preflight_scheduler_read_failure_is_reaped_and_closed(self):
        child=Mock(pid=123)
        child.poll.return_value=None
        popen=Mock(return_value=child)
        log=Mock()
        with patch.object(joint_runtime.subprocess,'Popen',popen):
            with self.assertRaisesRegex(OSError,'scheduler read failed'):
                joint_runtime._launch_child(
                    ['preflight'],Path('.'),log,'preflight',
                    lambda _child: (_ for _ in ()).throw(OSError('scheduler read failed')))
        child.terminate.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=5)
        log.close.assert_called_once_with()

    def test_preflight_terminate_error_still_waits_and_closes(self):
        child=Mock(pid=123)
        child.poll.side_effect=[None,None,0]
        child.terminate.side_effect=OSError('terminate failed')
        log=Mock()
        errors=joint_runtime._terminate_and_reap(child,log)
        self.assertEqual(errors,["OSError('terminate failed')"])
        child.terminate.assert_called_once_with()
        child.kill.assert_not_called()
        child.wait.assert_called_once_with(timeout=5)
        log.close.assert_called_once_with()

    def test_preflight_wait_timeout_kills_and_reaps(self):
        child=Mock(pid=123)
        child.poll.side_effect=[None,None,None,0]
        child.wait.side_effect=[subprocess.TimeoutExpired(['preflight'],5),0]
        log=Mock()
        errors=joint_runtime._terminate_and_reap(child,log)
        self.assertEqual(len(errors),1)
        self.assertIn('TimeoutExpired',errors[0])
        child.terminate.assert_called_once_with()
        child.kill.assert_called_once_with()
        self.assertEqual(child.wait.call_count,2)
        log.close.assert_called_once_with()

    def test_preflight_kill_error_still_finally_waits_and_closes(self):
        child=Mock(pid=123)
        child.poll.side_effect=[None,None,None,None,0]
        child.wait.side_effect=[subprocess.TimeoutExpired(['preflight'],5),OSError('final wait failed')]
        child.kill.side_effect=OSError('kill failed')
        log=Mock()
        errors=joint_runtime._terminate_and_reap(child,log)
        self.assertEqual(len(errors),3)
        self.assertTrue(any('TimeoutExpired' in error for error in errors))
        self.assertTrue(any("OSError('kill failed')" == error for error in errors))
        self.assertTrue(any("OSError('final wait failed')" == error for error in errors))
        child.terminate.assert_called_once_with()
        child.kill.assert_called_once_with()
        self.assertEqual(child.wait.call_count,2)
        log.close.assert_called_once_with()

    def test_preflight_unexpected_cleanup_error_still_reaches_kill_and_close(self):
        child=Mock(pid=123)
        child.poll.side_effect=[None,None,None,0]
        child.wait.side_effect=[RuntimeError('unexpected wait failed'),0]
        log=Mock()
        errors=joint_runtime._terminate_and_reap(child,log)
        self.assertEqual(errors,["RuntimeError('unexpected wait failed')"])
        child.terminate.assert_called_once_with()
        child.kill.assert_called_once_with()
        self.assertEqual(child.wait.call_count,2)
        log.close.assert_called_once_with()

    def test_preflight_cleanup_errors_are_returned_to_launch_caller(self):
        child=Mock(pid=123);child.poll.side_effect=[None,None,None,0]
        child.wait.side_effect=[subprocess.TimeoutExpired(['preflight'],5),0]
        child.kill.side_effect=RuntimeError('kill failed')
        popen=Mock(return_value=child);log=Mock();cleanup_errors=[]
        with patch.object(joint_runtime.subprocess,'Popen',popen):
            with self.assertRaisesRegex(RuntimeError,'admission failed'):
                joint_runtime._launch_child(
                    ['preflight'],Path('.'),log,'preflight',
                    lambda _child: (_ for _ in ()).throw(RuntimeError('admission failed')),
                    cleanup_errors=cleanup_errors)
        self.assertEqual(len(cleanup_errors),2)
        self.assertTrue(any('TimeoutExpired' in error for error in cleanup_errors))
        self.assertTrue(any("RuntimeError('kill failed')" == error for error in cleanup_errors))

    def test_child_identity_none_is_a_failure(self):
        child=Mock(pid=123)
        with patch.object(joint_runtime,'json_identity',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                joint_runtime._require_child_identity(child)

    def test_child_identity_missing_fields_is_a_failure(self):
        child=Mock(pid=123)
        with patch.object(joint_runtime,'json_identity',return_value={'pid':123}):
            with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                joint_runtime._require_child_identity(child)

    def test_child_identity_empty_values_are_a_failure(self):
        child=Mock(pid=123)
        identity={'pid':123,'pgid':None,'start_ticks':None}
        with patch.object(joint_runtime,'json_identity',return_value=identity):
            with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                joint_runtime._require_child_identity(child)

    def test_child_identity_requires_positive_non_bool_fields(self):
        child=Mock(pid=123)
        valid={'pid':123,'pgid':456,'start_ticks':789}
        for field,bad in (
                ('pid',0),('pid',-1),('pid',True),
                ('pgid',0),('pgid',-1),('pgid',False),
                ('start_ticks',0),('start_ticks',-1),('start_ticks',True)):
            with self.subTest(field=field,bad=bad):
                identity=dict(valid);identity[field]=bad
                with patch.object(joint_runtime,'json_identity',return_value=identity):
                    with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                        joint_runtime._require_child_identity(child)

    def test_child_identity_pid_must_match_child(self):
        child=Mock(pid=123)
        identity={'pid':124,'pgid':456,'start_ticks':789}
        with patch.object(joint_runtime,'json_identity',return_value=identity):
            with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                joint_runtime._require_child_identity(child)

    def test_preflight_identity_none_reaps_before_raising(self):
        child=Mock(pid=123);child.poll.return_value=None
        popen=Mock(return_value=child);log=Mock()
        with patch.object(joint_runtime,'json_identity',return_value=None), \
                patch.object(joint_runtime.subprocess,'Popen',popen):
            with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                joint_runtime._launch_child(
                    ['preflight'],Path('.'),log,'preflight',
                    joint_runtime._require_child_identity)
        child.terminate.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=5)
        log.close.assert_called_once_with()

    def test_preflight_identity_none_after_quick_exit_closes_without_false_kill(self):
        child=Mock(pid=123);child.poll.return_value=-15
        popen=Mock(return_value=child);log=Mock()
        with patch.object(joint_runtime,'json_identity',return_value=None), \
                patch.object(joint_runtime.subprocess,'Popen',popen):
            with self.assertRaisesRegex(RuntimeError,'identity unavailable'):
                joint_runtime._launch_child(
                    ['preflight'],Path('.'),log,'preflight',
                    joint_runtime._require_child_identity)
        child.terminate.assert_not_called()
        child.kill.assert_not_called()
        child.wait.assert_not_called()
        log.close.assert_called_once_with()

    def test_outer_stop_does_not_close_preflight_log_twice(self):
        child=Mock(pid=123)
        child.poll.return_value=-15
        log=Mock();log.closed=True
        self.assertEqual(joint_runtime.stop_processes([('preflight',child,log)]),[])
        log.close.assert_not_called()

    def test_child_nice_targets_preserve_scheduler_roles(self):
        self.assertEqual(joint_runtime._child_nice_target('preflight'),0)
        for role in ('model','fc'):
            with self.subTest(role=role):
                self.assertEqual(joint_runtime._child_nice_target(role),-10)
        for role in ('agent','control','task'):
            with self.subTest(role=role):
                self.assertEqual(joint_runtime._child_nice_target(role),-5)

    def test_preflight_phase_metadata_keeps_monotonic_elapsed(self):
        timing=dict(started_monotonic_ns=100)
        with patch.object(joint_runtime.time,'monotonic_ns',return_value=235):
            value=joint_runtime._finish_preflight_timing(timing,'completed')
        self.assertEqual(value,dict(started_monotonic_ns=100,finished_monotonic_ns=235,
            elapsed_ns=135,elapsed_seconds=135e-9,outcome='completed'))
        with patch.object(joint_runtime.time,'monotonic_ns',return_value=999):
            self.assertIs(joint_runtime._finish_preflight_timing(timing),timing)
        self.assertEqual(timing['finished_monotonic_ns'],235)

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
