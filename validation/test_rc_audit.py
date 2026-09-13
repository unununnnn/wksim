"""Mutate retained real-flight evidence; the offline auditor must reject it."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.audit_rc_flight import audit

@unittest.skipUnless(os.environ.get('RC_AUDIT_FIXTURE'), 'explicit retained RC flight required')
class RCAuditTests(unittest.TestCase):
    def clone(self, temp):
        source=Path(os.environ['RC_AUDIT_FIXTURE']); target=Path(temp)/'run'
        target.mkdir()
        for name in ('result.json','control.log','rc-dds.jsonl','truth.jsonl'):
            shutil.copy2(source/name,target/name)
        shutil.copytree(source/'run-source',target/'run-source')
        return target

    def test_unmodified_actual_run(self):
        self.assertEqual(audit(Path(os.environ['RC_AUDIT_FIXTURE']))['status'],'pass')

    def test_raw_cdr_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp)
            records=(root/'rc-dds.jsonl').read_text().splitlines()
            for i,line in enumerate(records):
                row=json.loads(line)
                if '/in/trajectory_setpoint' in row['topic']:
                    row['message']['position'][0]+=10
                    records[i]=json.dumps(row); break
            (root/'rc-dds.jsonl').write_text('\n'.join(records)+'\n')
            with self.assertRaisesRegex(ValueError,'CDR differs'): audit(root)

    def test_missing_native_channel_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp)
            rows=[line for line in (root/'rc-dds.jsonl').read_text().splitlines()
                  if '/in/trajectory_setpoint' not in json.loads(line)['topic']]
            (root/'rc-dds.jsonl').write_text('\n'.join(rows)+'\n')
            with self.assertRaisesRegex(ValueError,'native DDS'): audit(root)

    def test_task_relabelled_physical_cursor_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp)
            result=json.loads((root/'result.json').read_text())
            for phase in result['task']['rc']['phases']:
                if phase['phase']=='movement_end': phase['truth']['position'][0]+=10
            (root/'result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'cursor'): audit(root)

if __name__=='__main__': unittest.main()
