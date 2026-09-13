"""Physical auditor rejects a one-tick excursion and a failed recovery window."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from tools.audit_aruco_tracking_physical import evaluate_trace,verify_async_evidence

PROFILE=json.loads((Path(__file__).resolve().parents[1]/'Simulator/wksim_runtime/aruco-tracking-v1.json').read_text())
EPOCH='a'*32


class PhysicalAuditTests(unittest.TestCase):
    def test_async_completion_cannot_hide_truncated_file_or_live_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);records={}
            for name in ('wire.jsonl','rate.jsonl','clock.jsonl','public-dds.jsonl','scene-lifecycle.jsonl'):
                (root/name).write_bytes(b'{}\n')
                records[name]=dict(complete=True,closed=True,alive=False,error=None,
                                   submitted_bytes=3,written_bytes=3,queue_highwater=1)
            self.assertEqual(len(verify_async_evidence(root,records)),5)
            (root/'wire.jsonl').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'byte counts'):verify_async_evidence(root,records)
            (root/'wire.jsonl').write_bytes(b'{}\n')
            records['wire.jsonl']['alive']=True
            with self.assertRaisesRegex(ValueError,'did not retire'):verify_async_evidence(root,records)

    def run_trace(self,change=None):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'truth.jsonl'
            with path.open('w') as stream:
                for tick in range(1,12003):
                    state=[0.]*120;state[2]=tick/1000;state[12]=1.
                    state[7]=min(4000,max(0,tick-1-2000))*.00025
                    state[8]=-3. if tick<=12001 else 0.
                    if change:change(tick,state)
                    stream.write(json.dumps(dict(tick=tick,epoch=EPOCH,state=state))+'\n')
            return evaluate_trace(path,EPOCH,1,12001,np.array([0,0,3]),np.eye(3),PROFILE,True)

    def test_truth_follows_world_target(self):
        result=self.run_trace()
        self.assertEqual(result['status'],'pass')
        self.assertEqual(result['samples'],12001)
        self.assertLess(result['max_tracking_error_m'],1e-12)

    def test_single_tick_excursion_cannot_be_averaged_away(self):
        result=self.run_trace(lambda tick,state:state.__setitem__(6,.8) if tick==3000 else None)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['failure_count'],1)
        self.assertEqual(result['failure_examples'][0]['gate'],'tracking')

    def test_recovery_gate_stricter_than_tracking(self):
        result=self.run_trace(lambda tick,state:state.__setitem__(6,.4) if tick==11900 else None)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['failure_examples'][0]['gate'],'recovery')
        self.assertLess(result['max_tracking_error_m'],PROFILE['mission']['tracking_error_m'])

    def test_nonfinite_truth_rejected(self):
        with self.assertRaisesRegex(ValueError,'numeric'):
            self.run_trace(lambda tick,state:state.__setitem__(6,float('nan')) if tick==5 else None)


if __name__=='__main__':unittest.main()
