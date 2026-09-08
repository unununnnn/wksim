"""Retained real flight fixtures; corrupt copies never touch original evidence."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.audit_independent_velocity import audit

REPO=Path(__file__).resolve().parents[1]
EVIDENCE=REPO/'validation/independent-velocity-20260909'


@unittest.skipUnless((EVIDENCE/'px4-final/independent-velocity.json').is_file(),'Retained independent velocity flights required')
class EvidenceTests(unittest.TestCase):
    def test_both_actual_stack_windows_pass(self):
        for stack in ('px4','ap'):
            result=audit(EVIDENCE/(stack+'-final'),verify_sources=False)
            self.assertEqual(result['status'],'pass')
            self.assertEqual(result['requests'],13)

    def test_corrupted_physics_identity_and_ack_are_rejected(self):
        original=EVIDENCE/'px4-final'
        wrapper=json.loads((original/'independent-velocity.json').read_text())
        run_id=wrapper['runtime_result']['run_id']
        truth_lines=(original/run_id/'truth.jsonl').read_text().splitlines()
        phases={p['phase']:p for p in wrapper['runtime_result']['task']['independent_velocity']['phases']}
        for fault in ('velocity','body','zero','yaw','time','ack','vehicle','firmware'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='velocity-negative-',dir=EVIDENCE) as directory:
                root=Path(directory)
                self.assertTrue(root.resolve().is_relative_to(EVIDENCE.resolve()))
                (root/run_id).mkdir()
                shutil.copyfile(original/run_id/'prometheus.jsonl',root/run_id/'prometheus.jsonl')
                value=copy.deepcopy(wrapper)
                trace=truth_lines.copy()
                changes={'velocity':('velocity_step_settled',4,1.3),
                         'body':('body_velocity_settled',4,1.7),
                         'zero':('velocity_hold_settled',3,.6),
                         'yaw':('velocity_zero_hold',11,0.)}
                if fault in changes:
                    phase,axis,number=changes[fault]
                    index=phases[phase]['physical_cursor']['records']+1
                    row=json.loads(trace[index]);row['vehicle'][axis]=number;trace[index]=json.dumps(row)
                elif fault=='time':
                    row=json.loads(trace[1]);row['time']=json.loads(trace[0])['time'];trace[1]=json.dumps(row)
                elif fault=='ack':
                    value['runtime_result']['task']['events']=[e for e in value['runtime_result']['task']['events'] if e['event']!='native_ack']
                elif fault=='vehicle':
                    value['runtime_result']['task']['independent_velocity']['phases'][0]['state']['uav_id']=2
                else:
                    value['runtime_result']['fc_sha256']='0'*64
                (root/'independent-velocity.json').write_text(json.dumps(value))
                (root/run_id/'result.json').write_text(json.dumps(value['runtime_result']))
                (root/run_id/'truth.jsonl').write_text('\n'.join(trace)+'\n')
                with self.assertRaises(ValueError):
                    audit(root,verify_sources=False)


if __name__=='__main__':unittest.main()
