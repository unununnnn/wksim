"""Tamper captured UE evidence; geometry gates must work beyond file hashes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from tools.audit_aruco_scene import audit


@unittest.skipUnless(os.environ.get('WKSIM_ARUCO_SCENE_FIXTURE'),'explicit actual UE capture required')
class ArUcoSceneAuditTests(unittest.TestCase):
    def source(self):return Path(os.environ['WKSIM_ARUCO_SCENE_FIXTURE'])

    def changed(self,change,reason):
        report=json.loads((self.source()/'report.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);change(report,root)
            (root/'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,reason):audit(root)

    def test_actual_capture(self):self.assertEqual(audit(self.source())['status'],'pass')

    def test_wrong_physical_size_with_updated_hash(self):
        def change(report,root):
            row=report['frames'][0];scene=json.loads(Path(row['scene_path']).read_text())
            scene['objects'][1]['scale'][1]*=1.2
            path=root/'changed-scene.json';path.write_text(json.dumps(scene))
            row['scene_path']=str(path);row['scene_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        self.changed(change,'dimensions/motion')

    def test_wrong_material_with_updated_hash(self):
        def change(report,root):
            row=report['frames'][0];scene=json.loads(Path(row['scene_path']).read_text())
            scene['objects'][1]['material_emissive_rgba']=[1,1,1,1]
            path=root/'changed-scene.json';path.write_text(json.dumps(scene))
            row['scene_path']=str(path);row['scene_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        self.changed(change,'material/collision')

    def test_stale_frame(self):
        def change(report,root):report['frames'][0]['now_step']=int(report['frames'][0]['frame']['metadata']['step'])+301
        self.changed(change,'stale admitted')

    def test_missing_occlusion_phase(self):
        def change(report,root):
            report['frames']=[row for row in report['frames'] if row['target'] is not None]
        self.changed(change,'Insufficient samples')

    def test_scene_identity_relabelled(self):
        def change(report,root):
            row=report['frames'][0];scene=json.loads(Path(row['scene_path']).read_text());scene['epoch']='f'*32
            path=root/'changed-scene.json';path.write_text(json.dumps(scene))
            row['scene_path']=str(path);row['scene_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        self.changed(change,'identity differs')


if __name__=='__main__':unittest.main()
