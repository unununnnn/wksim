"""Negative audits mutate retained real native evidence and update its checksum."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import subprocess
import sys
from tools.audit_motor_efficiency import audit,digest


@unittest.skipUnless(os.environ.get('WKSIM_EFFICIENCY_NATIVE_AUDIT')=='1','explicit retained native benches required')
class NativeAuditTests(unittest.TestCase):
    def paths(self):
        return [Path('/root/wksim-efficiency-native-'+name) for name in (
            'reference-02','normal-02','event-02','event-03','revoke-pending-02','revoke-active-02','tamper-02')]

    def clone(self,source,destination):
        destination.mkdir()
        for name in ('result.json','raw.jsonl'): shutil.copy2(source/name,destination/name)
        return destination

    def rewrite(self,root,rows):
        (root/'raw.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        result=json.loads((root/'result.json').read_text())
        result['raw_sha256']=digest(root/'raw.jsonl')
        (root/'result.json').write_text(json.dumps(result))

    def test_original_benches_pass(self):
        self.assertEqual(audit(*self.paths())['status'],'pass')

    def test_second_plan_cannot_claim_same_native_lifetime(self):
        program='''
import json
from Simulator.wksim_core.motor_efficiency_model import EfficiencyModel
from Simulator.wksim_core.motor_efficiency_event import make_plan,EfficiencyEvent
from validation.test_motor_efficiency_event import identity
m=EfficiencyModel('/root/wksim-efficiency-model-r97g_cit/libwksim_efficiency.so')
i=identity(); i.update(library_sha256=m.library_sha256,model_identity='sha256:'+m.library_sha256)
p=make_plan(i,0); first=EfficiencyEvent(p,i,loaded_tick=0)
first.step(m,[.55]*4+[0.]*12,tick=0)
second=EfficiencyEvent(p,i,loaded_tick=1)
try: second.step(m,[.55]*4+[0.]*12,tick=1)
except ValueError as error: assert 'Second event' in str(error)
else: raise AssertionError('Second plan accepted')
try: first.step(m,[.55]*4+[0.]*12,tick=1)
except ValueError as error: assert 'latched' in str(error)
else: raise AssertionError('Failed lifetime resumed')
assert m.ticks==1 and m.efficiency()==[1.]*4
m.close()
print('native ownership guard passed')
'''
        result=subprocess.run([sys.executable,'-B','-c',program],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('guard passed',result.stdout)

    def test_another_rotor_affected_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=self.paths()
            paths[4]=self.clone(paths[4],Path(temp)/'mutated')
            rows=[json.loads(line) for line in (paths[4]/'raw.jsonl').read_text().splitlines()]
            rows[10]['eta'][1]=.97
            self.rewrite(paths[4],rows)
            with self.assertRaisesRegex(ValueError,'Wrong motor'): audit(*paths)

    def test_force_logs_without_physical_change_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=self.paths()
            baseline=[json.loads(line)['output120'] for line in (paths[1]/'raw.jsonl').read_text().splitlines()]
            for index in (2,3):
                paths[index]=self.clone(paths[index],Path(temp)/str(index))
                rows=[json.loads(line) for line in (paths[index]/'raw.jsonl').read_text().splitlines()]
                for row,output in zip(rows,baseline): row['output120']=output
                self.rewrite(paths[index],rows)
            with self.assertRaisesRegex(ValueError,'only changed records'): audit(*paths)


if __name__=='__main__': unittest.main()
