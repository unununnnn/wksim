"""Use retained real airborne images; reject forged geometry, lifecycle and results."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from tools.audit_aruco_flight_scene import audit


@unittest.skipUnless(os.environ.get('WKSIM_ARUCO_FLIGHT_SCENE_FIXTURE'),'actual airborne scene required')
class FlightSceneAuditTests(unittest.TestCase):
    def source(self):return Path(os.environ['WKSIM_ARUCO_FLIGHT_SCENE_FIXTURE'])
    def changed(self,change,reason):
        report=json.loads((self.source()/'report.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);change(report,root)
            (root/'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,reason):audit(root)
    def test_actual_airborne_capture(self):self.assertEqual(audit(self.source())['status'],'pass')
    def test_initial_capture_before_enable_is_rejected(self):
        def change(report,root):report['initial_scene']['anchor_valid']=True
        self.changed(change,'before enable')
    def test_geometry_change_even_with_updated_scene_hash_is_rejected(self):
        def change(report,root):
            row=report['frames'][1];scene=json.loads(Path(row['scene_path']).read_text())
            scene['objects'][1]['scale'][1]*=1.2
            path=root/'scene.json';path.write_text(json.dumps(scene))
            row['scene_path']=str(path);row['scene_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        self.changed(change,'marker size')
    def test_forged_pose_cannot_replace_raw_measurement(self):
        def change(report,root):report['frames'][0]['target']['position_optical_m'][2]+=.001
        self.changed(change,'raw image pose')
    def test_unretired_process_group_is_rejected(self):
        def change(report,root):report['result']['epochs'][0]['remaining_group_members']=[{'pid':123}]
        self.changed(change,'Live epoch')
    def test_missing_occlusion_samples_is_rejected(self):
        def change(report,root):report['frames']=[r for r in report['frames'] if r['target'] is not None]
        self.changed(change,'velocity|Velocity|Insufficient')


if __name__=='__main__':unittest.main()
