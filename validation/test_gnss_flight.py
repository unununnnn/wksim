"""Physical-owner schedule boundaries before any native controller is started."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.gnss_physics import Schedule
from Simulator.wksim_core.motor_efficiency_event import publish_plan
from Simulator.wksim_control.gnss_recovery_frame import local_after_home_change

PROFILE=Path(__file__).resolve().parents[1]/'Simulator/wksim_runtime/gnss-flight-v3.json'


class ScheduleTests(unittest.TestCase):
    def test_ros_numeric_values_remain_numbers_in_evidence(self):
        import numpy as np
        from tools.run_gnss_flight import numeric_json
        encoded=json.dumps({'position':[np.float32(.3)],'sequence':np.uint64(7)},default=numeric_json)
        value=json.loads(encoded)
        self.assertEqual(value['sequence'],7)
        self.assertAlmostEqual(value['position'][0],.3,places=6)
        with self.assertRaises(TypeError):numeric_json(object())

    def test_recovery_preserves_old_datum_without_physical_feedback(self):
        original=dict(latitude_e7=401540302,longitude_e7=1162593683,altitude_cm=5000)
        current=dict(latitude_e7=401540707,longitude_e7=1162594075,altitude_cm=5010)
        target=local_after_home_change([3.,2.,3.],original,current)
        self.assertLess(target[0],0.)
        self.assertLess(target[1],-2.)
        self.assertAlmostEqual(target[2],2.9)
        self.assertEqual(local_after_home_change([3.,2.,3.],original,original),[3.,2.,3.])
        with self.assertRaises(ValueError):local_after_home_change([3.,2.,3.],original,dict(current,altitude_cm=20000))

    def make(self,root):
        (root/'gnss-profile.json').write_bytes(PROFILE.read_bytes())
        request=dict(run_id='a'*32,scene_epoch='b'*32,control_epoch='c'*32,
                     profile_sha256=hashlib.sha256(PROFILE.read_bytes()).hexdigest())
        return Schedule(root,'a'*32,'b'*32,json.loads(PROFILE.read_text())),request

    def test_physics_owner_selects_aligned_future_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schedule,request=self.make(root)
            schedule.poll(7000);self.assertIsNone(schedule.plan)
            publish_plan(root/'gnss-arm.json',request);schedule.poll(7001)
            self.assertEqual((schedule.plan['origin_tick'],schedule.plan['start_tick'],schedule.plan['end_tick']),(7001,9200,24200))
            schedule.poll(8000);self.assertEqual(schedule.plan['origin_tick'],7001)
            (root/'gnss-arm.json').unlink()
            with self.assertRaisesRegex(ValueError,'disappeared'):schedule.poll(8001)

    def test_foreign_epoch_and_changed_request_rejected(self):
        for field in ('scene_epoch','control_epoch'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);schedule,request=self.make(root)
                request[field]='invalid';publish_plan(root/'gnss-arm.json',request)
                with self.assertRaisesRegex(ValueError,'identity'):schedule.poll(6000)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schedule,request=self.make(root)
            publish_plan(root/'gnss-arm.json',request);schedule.poll(6000)
            (root/'gnss-arm.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'changed'):schedule.poll(6001)

    def test_plan_cannot_exceed_native_tick_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schedule,request=self.make(root)
            publish_plan(root/'gnss-arm.json',request)
            with self.assertRaisesRegex(ValueError,'budget'):schedule.poll(164000)


if __name__=='__main__':unittest.main()
