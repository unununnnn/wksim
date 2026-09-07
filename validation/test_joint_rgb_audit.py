"""Tamper real evidence copies; never modify original recordings."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.audit_joint_rgb import audit

SOURCE=Path(__file__).resolve().parent/'joint-rgb-20260907-run2'


class JointRgbAuditTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt' and (SOURCE/'report.json').is_file(),'Original Windows RGB paths required; exercised on Windows')
    def test_capture_pose_pixels_and_physical_source_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'case';root.mkdir()
            for name in ('implementation.json','ue-loaded-module.json'):
                shutil.copyfile(SOURCE/name,root/name)
            shutil.copytree(SOURCE/'sources',root/'sources')
            original=json.loads((SOURCE/'report.json').read_text())
            view=original['view_final']
            paths=[Path(view['readback_path']),*Path(view['rgb_directory']).glob('*')]
            for ep in original['result']['epochs']:
                paths.extend(SOURCE/'run/epochs'/ep['epoch']/name for name in
                             ('arducopter-truth.jsonl','px4-truth.jsonl','clock.jsonl'))
            for path in paths:
                target=root/path.relative_to(SOURCE);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
            def remap(value):
                if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
                if isinstance(value,list):return [remap(v) for v in value]
                if isinstance(value,str) and value.startswith(str(SOURCE)):return str(root)+value[len(str(SOURCE)):]
                return value
            report=remap(original)
            report_path=root/'report.json';report_path.write_text(json.dumps(report))
            self.assertEqual(audit(root)['status'],'pass')
            metadata=Path(report['frames'][0]['metadata_path']);old=metadata.read_bytes()
            report['frames'][0]['metadata']['camera_world_pose']['position_cm'][0]+=1
            metadata.write_text(json.dumps(report['frames'][0]['metadata']));report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'capture pose'):audit(root)
            metadata.write_bytes(old);report=remap(original);report_path.write_text(json.dumps(report))
            image=Path(report['frames'][0]['image_path']);old=image.read_bytes();image.write_bytes(old[:40])
            with self.assertRaises(OSError):audit(root)
            image.write_bytes(old)
            trace=root/'run/epochs'/report['result']['epochs'][0]['epoch']/'px4-truth.jsonl'
            step=int(report['frames'][0]['metadata']['step']);rows=[json.loads(line) for line in trace.read_text().splitlines()]
            next(row for row in rows if row['tick']==step)['state'][6]+=1
            trace.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            with self.assertRaisesRegex(ValueError,'physical state'):audit(root)


if __name__=='__main__':unittest.main()
