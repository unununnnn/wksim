"""Destructive copies of real retained input-boundary evidence; no live runtime."""
import copy
import json
from pathlib import Path
import sys
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
sys.path.insert(0,str(REPO))
from audit_joint_input_stall import input_boundary, model_boundary, lines, read


class InputBoundaryTamper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory=REPO/'validation/joint-input-stall-kcnyjj8i'
        flow=read(directory/'flow.json');epoch=flow['fault']['epoch'];first=directory/'run/epochs'/epoch
        fault=read(first/'faults.json')[0];tick=fault['authority']['tick']
        life=list(lines(first/'scene-lifecycle.jsonl'))
        wire=[row for row in lines(first/'wire.jsonl') if row['tick']==tick]
        # Preserve the true tick indexing but load only the single boundary row.
        truth={stack:[None]*(tick-1)+[next(row for row in lines(first/(stack+'-truth.jsonl')) if row['tick']==tick)]
               for stack in ('arducopter','px4')}
        request=next(row['submitted']['request'] for row in flow['actions'] if row['response']['action']=='recover')
        cls.original=(flow,fault,life,wire,truth,request)

    def setUp(self):
        self.data=copy.deepcopy(self.original)

    def test_real_boundary(self):
        self.assertTrue(input_boundary(*self.data)['original_input_completed_after_action'])

    def test_partial_model_cannot_be_input_recovery(self):
        self.data[1]['model_channels']['px4']['failed']=True
        with self.assertRaisesRegex(ValueError,'partial/poisoned'): input_boundary(*self.data)

    def test_early_extra_step_is_rejected(self):
        row=copy.deepcopy(next(row for row in self.data[3] if row['kind']=='step'))
        row['issued_monotonic_s']=self.data[1]['issued_monotonic_s']+.1
        self.data[3].append(row)
        with self.assertRaisesRegex(ValueError,'Extra physical'): input_boundary(*self.data)

    def test_changed_original_input_source_is_rejected(self):
        next(row for row in self.data[3] if row['kind']=='step')['ap_source_frame']-=1
        with self.assertRaisesRegex(ValueError,'original inputs'): input_boundary(*self.data)

    def test_changed_repair_tick_is_rejected(self):
        next(row for row in self.data[2] if row['kind']=='input_recovery_verified')['after']['tick']+=1
        with self.assertRaisesRegex(ValueError,'physical authority'): input_boundary(*self.data)

    def test_shortened_deadline_is_rejected(self):
        self.data[1]['issued_monotonic_s']-=1
        with self.assertRaisesRegex(ValueError,'5s window'): input_boundary(*self.data)


class ModelBoundaryTamper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory=REPO/'validation/joint-input-stall-kp5klq6t'
        flow=read(directory/'flow.json');first=directory/'run/epochs'/flow['fault']['epoch']
        fault=read(first/'faults.json')[0];life=list(lines(first/'scene-lifecycle.jsonl'))
        wire=[row for row in lines(first/'wire.jsonl') if row['tick']>=fault['authority']['tick']]
        truth={}
        for stack in ('arducopter','px4'):
            samples=[flow['late_process_resumed'][phase][stack] for phase in ('before','after')]
            truth[stack]=[None]*max(row['tick'] for row in samples)
            for sample in samples:truth[stack][sample['tick']-1]=sample
        cls.original=(flow,fault,life,wire,truth)

    def setUp(self):self.data=copy.deepcopy(self.original)

    def test_actual_poisoned_boundary(self):
        self.assertTrue(model_boundary(*self.data)['late_response_not_committed'])

    def test_recovery_offer_on_partial_model_is_rejected(self):
        self.data[0]['late_process_resumed']['status']['allowed_actions'].append('recover')
        with self.assertRaisesRegex(ValueError,'unsafe recovery'):model_boundary(*self.data)

    def test_uncommitted_model_state_on_wire_is_rejected(self):
        self.data[3].append(dict(kind='sensor',tick=self.data[1]['authority']['tick']+1))
        with self.assertRaisesRegex(ValueError,'native wire'):model_boundary(*self.data)


if __name__=='__main__': unittest.main()
