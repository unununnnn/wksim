"""Mutations of real scheduled AP ground evidence, not fabricated positive traces."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_ap_gnss_schedule import audit,digest


@unittest.skipUnless(os.environ.get('WKSIM_GNSS_SCHEDULE_AUDIT')=='1','retained native ground probe required')
class ScheduledAuditTests(unittest.TestCase):
    source=Path('/root/wksim-ap-gnss-scheduled-dds-01')

    def clone(self,directory):
        root=Path(directory)/'run';root.mkdir()
        for name in ('manifest.json','native.tsv','wire.jsonl','process.log'):
            shutil.copy2(self.source/name,root/name)
        return root

    def test_actual_native_record_passes(self):
        self.assertEqual(audit(self.source)['status'],'pass')

    def test_native_ubx_corruption_rejected_even_with_new_file_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp);path=root/'native.tsv'
            rows=path.read_text().splitlines()
            for i,line in enumerate(rows):
                parts=line.split('\t')
                if parts[0]=='WRITE' and len(parts[5])==4:
                    parts[5]=parts[5][:-1]+('0' if parts[5][-1]!='0' else '1')
                    rows[i]='\t'.join(parts);break
            path.write_text('\n'.join(rows)+'\n')
            manifest=json.loads((root/'manifest.json').read_text());manifest['raw_sha256']['native.tsv']=digest(path)
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'UBX'):audit(root)

    def test_changed_plan_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=self.clone(temp);path=root/'native.tsv'
            raw=path.read_text().replace('PLAN\t45000\t50000\t65000','PLAN\t45000\t50000\t65001')
            path.write_text(raw)
            manifest=json.loads((root/'manifest.json').read_text());manifest['raw_sha256']['native.tsv']=digest(path)
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'Plan'):audit(root)


if __name__=='__main__':unittest.main()
