"""No FC/UI: explicit human gates and actual pinned MAVLink decoding."""
import base64
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.validate_gcs_handoff import HumanHandoffTask, gcs_mode_evidence
from tools.request_gcs_takeover import request_takeover
import tools.request_gcs_takeover as request_module
from validate_airborne_takeover import TakeoverProbe


class HumanGatesTests(unittest.TestCase):
    def test_operator_cli_publishes_one_complete_current_decision(self):
        with tempfile.TemporaryDirectory() as root, patch.object(request_module,'REPO',Path(root)):
            output=Path(root)/'validation'/'human'
            formal=output/'formal'
            formal.mkdir(parents=True)
            request=dict(version=1,action='takeover',run_id='human-test',control_epoch='1'*32,nonce='2'*32)
            (output/'config.json').write_text(json.dumps({'run_id':'human-test'}))
            (formal/'report.json').write_text(json.dumps({'status':'running'}))
            (formal/'human-handoff.json').write_text(json.dumps({'current':dict(event='awaiting_explicit_takeover',
                run_id='human-test',control_epoch='1'*32,request=request)}))
            self.assertEqual(request_takeover(output)['status'],'request_written')
            self.assertEqual(json.loads((formal/'takeover-request.json').read_text()),request)
            with self.assertRaises(FileExistsError):
                request_takeover(output)
            self.assertEqual(list(formal.glob('*.tmp')),[])
            (output/'report.json').write_text('{}')
            with self.assertRaises(ValueError):
                request_takeover(output)

    def task(self, directory):
        task=HumanHandoffTask.__new__(HumanHandoffTask)
        task.Setup=type('Setup',(),{'SET_PX4_MODE':1})
        task.release_mode='AUTO.LOITER'
        task.run_id,task.epoch='human-test','1'*32
        task.operator_directory=Path(directory)
        task.human_events=[]
        task.observed_human_revocation=None
        task.expect_human_release=False
        task._human_wait_elapsed=0.0
        task._human_wait_started=None
        task.owns_control=lambda:True
        task.loitering=lambda:True
        task.latest={'state':SimpleNamespace(mode='AUTO.LOITER')}
        task.convert=vars
        return task

    def test_release_waits_for_external_mode_without_publishing_a_substitute(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(TakeoverProbe,'send') as send:
            task=self.task(directory)
            msg=task.Setup()
            msg.cmd,msg.px4_mode=1,'AUTO.LOITER'
            def wait(label,predicate,timeout):
                self.assertFalse(predicate())
                task.on_control_revoked(dict(reason='external_mode_left_no_automatic_reacquisition'))
                self.assertTrue(predicate())
                self.assertEqual(timeout,300)
            task.wait=wait
            task.send(msg,'yield_mode_completed')
            send.assert_not_called()
            self.assertFalse(task.expect_human_release)
            self.assertEqual(task.human_events[-1]['event'],'human_qgc_mode_observed')

    def test_other_revocation_and_absent_user_action_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(TakeoverProbe,'send') as send:
            task=self.task(directory)
            task.expect_human_release=True
            with patch.object(TakeoverProbe,'on_control_revoked') as revoked:
                task.on_control_revoked(dict(reason='native_clock_or_origin_reset'))
                revoked.assert_called_once()
            msg=task.Setup()
            msg.cmd,msg.px4_mode=1,'AUTO.LOITER'
            task.wait=lambda *args:(_ for _ in ()).throw(TimeoutError('human absent'))
            with self.assertRaises(TimeoutError):
                task.send(msg,'yield_mode_completed')
            send.assert_not_called()
            self.assertFalse(task.expect_human_release)

    def test_takeover_requires_new_exact_operator_request(self):
        for mode in ('valid','wrong_nonce','preexisting','absent'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, \
                    patch.object(TakeoverProbe,'send') as send:
                task=self.task(directory)
                task.observed_human_revocation={'reason':'external_mode_left_no_automatic_reacquisition'}
                path=Path(directory)/'takeover-request.json'
                if mode=='preexisting':
                    path.write_text('{}')
                def wait(label,predicate,timeout):
                    self.assertFalse(predicate())
                    if mode=='absent':
                        raise TimeoutError('human absent')
                    request=dict(task.human_events[-1]['request'])
                    if mode=='wrong_nonce':
                        request['nonce']='old'
                    path.write_text(json.dumps(request))
                    self.assertTrue(predicate())
                task.wait=wait
                if mode=='valid':
                    task.send(SimpleNamespace(),'fresh_airborne_takeover_completed')
                    send.assert_called_once()
                else:
                    with self.assertRaises((RuntimeError,TimeoutError)):
                        task.send(SimpleNamespace(),'fresh_airborne_takeover_completed')
                    send.assert_not_called()


@unittest.skipUnless(sys.platform=='linux', 'Pinned dialect source belongs to WSL')
class ModeEvidenceTests(unittest.TestCase):
    def test_real_mode_bytes_need_correct_target_mode_and_successful_forwarding(self):
        from Simulator.wksim_runtime.telemetry_dialect import load_dialect
        for stack in ('px4','arducopter'):
            dialect,_=load_dialect(stack)
            encoder=dialect.MAVLink(None,srcSystem=255,srcComponent=190)
            target=22 if stack=='px4' else 241
            custom=(4<<16)|(3<<24) if stack=='px4' else 17
            good=dialect.MAVLink_set_mode_message(target,1,custom).pack(encoder)
            wrong=dialect.MAVLink_set_mode_message(target+1,1,custom).pack(encoder)
            wrong_mode=dialect.MAVLink_set_mode_message(target,1,custom+1).pack(encoder)
            foreign=dialect.MAVLink_set_mode_message(target,1,custom).pack(
                dialect.MAVLink(None,srcSystem=254,srcComponent=190))
            command=dialect.MAVLink_command_long_message(target,1,dialect.MAV_CMD_DO_SET_MODE,0,
                1,4 if stack=='px4' else 17,3 if stack=='px4' else 0,0,0,0,0).pack(encoder)
            def row(raw,count):
                return json.dumps(dict(kind='gcs_bridge_reverse',relay={'reverse_forwarded':count},
                                       packet_base64=base64.b64encode(raw).decode()))+'\n'
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'bridge.jsonl'
                path.write_text(row(good,1)+'{"partial":')
                result=gcs_mode_evidence(path,stack)
                self.assertEqual(len(result['matches']),1)
                self.assertEqual(result['matches'][0]['source_system'],255)
                path.write_text(row(command,1))
                self.assertEqual(gcs_mode_evidence(path,stack)['matches'][0]['message']['mavpackettype'],'COMMAND_LONG')
                for content in (row(good,0),row(wrong,1),row(wrong_mode,1),row(foreign,1),row(good,2)):
                    path.write_text(content)
                    with self.assertRaises(ValueError):
                        gcs_mode_evidence(path,stack)


if __name__=='__main__':
    unittest.main()
