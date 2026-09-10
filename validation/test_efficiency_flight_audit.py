"""Tamper real efficiency-flight evidence; no new flight or synthetic plant."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.audit_efficiency_flight import audit

@unittest.skipUnless(os.environ.get('WKSIM_EFFICIENCY_FLIGHT_TESTS')=='1','explicit retained flight required')
class EfficiencyFlightAuditTests(unittest.TestCase):
    fixture=Path('/root/wksim-efficiency-flight-px4-baseline-01/efficiency-px4-baseline-01')

    def clone(self,temp):
        target=Path(temp)/'run';target.mkdir()
        for name in ('result.json','efficiency-profile.json','efficiency-origin.json','physics-1ms.jsonl','rc-dds.jsonl','control.log'):
            shutil.copy2(self.fixture/name,target/name)
        shutil.copytree(self.fixture/'run-source',target/'run-source')
        return target

    def test_retained_baseline_passes(self):
        self.assertEqual(audit(self.fixture)['status'],'pass')

    def test_budget_edit_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp);path=root/'efficiency-profile.json'
            profile=json.loads(path.read_text());profile['position_error_m']=30
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError,'budgets'):audit(root)

    def test_pwm_scaling_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp);path=root/'physics-1ms.jsonl';temporary=root/'changed.jsonl'
            with path.open() as source,temporary.open('w') as dest:
                changed=False
                for line in source:
                    if not changed and '"kind": "step"' in line:
                        row=json.loads(line);row['applied_input16'][0]=.01;line=json.dumps(row)+'\n';changed=True
                    dest.write(line)
            temporary.replace(path)
            with self.assertRaisesRegex(ValueError,'PWM scaled'):audit(root)

    def test_missing_native_terminal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp);path=root/'physics-1ms.jsonl'
            with path.open('r+b') as handle:
                handle.seek(-4096,2);offset=handle.tell();tail=handle.read()
                start=tail.rfind(b'\n{"kind": "end"')
                self.assertGreaterEqual(start,0)
                handle.truncate(offset+start+1)
            with self.assertRaisesRegex(ValueError,'terminal'):audit(root)

if __name__=='__main__':unittest.main()
