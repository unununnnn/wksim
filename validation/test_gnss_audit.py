"""Mutate retained real GNSS flight evidence; no new vehicle execution."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from tools.audit_gnss_flight import audit

@unittest.skipUnless(os.environ.get('WKSIM_GNSS_AUDIT_ROOT'),'explicit retained flight required')
class GNSSAuditTests(unittest.TestCase):
    def clone(self,directory):
        source=Path(os.environ['WKSIM_GNSS_AUDIT_ROOT']);root=Path(directory)/'run';root.mkdir()
        for name in ('result.json','gnss-profile.json','gnss-plan.json','physics-1ms.jsonl','gnss-wire.jsonl','rc-dds.jsonl','control.log'):
            shutil.copy2(source/name,root/name)
        for name in ('run-source','log'):shutil.copytree(source/name,root/name)
        return root

    def test_unmodified_flight(self):
        self.assertEqual(audit(Path(os.environ['WKSIM_GNSS_AUDIT_ROOT']))['status'],'pass')

    def test_changed_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.clone(directory);path=root/'gnss-profile.json';cfg=json.loads(path.read_text())
            cfg['maximum_distance_m']=40.;path.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'profile changed'):audit(root)

    def test_packet_during_outage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.clone(directory);plan=json.loads((root/'gnss-plan.json').read_text())
            path=root/'gnss-wire.jsonl';rows=[json.loads(line) for line in path.read_text().splitlines()]
            for row in rows:
                if row['phase']=='result' and row['tick']==plan['start_tick']:
                    row['raw_frames_hex']=['aa'];break
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with self.assertRaisesRegex(ValueError,'GPS bytes'):audit(root)

    def test_no_new_recovery_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.clone(directory);path=root/'rc-dds.jsonl'
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            commands=[r for r in rows if r['topic'].endswith('/v2/command')]
            last=commands[-1]['message']['request_id']
            rows=[r for r in rows if not (r['topic'].endswith('/v2/command') and r['message']['request_id']==last)]
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with self.assertRaisesRegex(ValueError,'distinct post-recovery task'):audit(root)

if __name__=='__main__':unittest.main()
