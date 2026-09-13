"""Contract rejects precede native integration; actual native proof uses the bench CLI."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from Simulator.wksim_core.motor_efficiency_event import EfficiencyEvent,make_plan,publish_plan,load_plan,canonical


def identity():
    return dict(run_id='event-test',instance_id=1,control_epoch='a'*32,model_identity='sha256:'+'b'*64,
                library_sha256='b'*64,config_sha256='c'*64,protocol_sha256='d'*64,
                original_source_sha256='e'*64,parameterized_source_sha256='f'*64,wrapper_sha256='1'*64)


class EfficiencyPlanTests(unittest.TestCase):
    def test_exact_frozen_interval_and_early_admission(self):
        plan=make_plan(identity(),6000)
        self.assertEqual((plan['start_tick'],plan['end_tick'],plan['recovery_deadline_tick']),(8000,9000,17000))
        EfficiencyEvent(plan,identity(),loaded_tick=7000)
        with self.assertRaisesRegex(ValueError,'1000 ticks'):
            EfficiencyEvent(plan,identity(),loaded_tick=7001)

    def test_identity_and_scalar_mutations_rejected(self):
        plan=make_plan(identity(),0)
        for key,value in (('origin_tick',True),('start_tick',2000.),('seed',False),('multiplier',.96),
                          ('motor_index',1),('control_epoch','c'*32),('library_sha256','c'*64),('unknown',0)):
            changed=copy.deepcopy(plan); changed[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                EfficiencyEvent(changed,identity(),loaded_tick=0)
        for value in (-1,True,2**53,0.):
            with self.assertRaises(ValueError): make_plan(identity(),value)

    def test_one_immutable_canonical_publication(self):
        plan=make_plan(identity(),0)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'event.json'
            publish_plan(path,plan)
            self.assertEqual(load_plan(path),plan)
            EfficiencyEvent(plan,identity(),loaded_tick=0,path=path)
            with self.assertRaises(FileExistsError): publish_plan(path,plan)
            path.write_text(json.dumps(plan,indent=2))
            with self.assertRaisesRegex(ValueError,'canonical'):
                EfficiencyEvent(plan,identity(),loaded_tick=0,path=path)
            path.write_bytes(b'{"seed":0,"seed":0}')
            with self.assertRaisesRegex(ValueError,'Duplicate'): load_plan(path)


if __name__=='__main__': unittest.main()
