"""Pure refusal/identity checks; these tests are not native flight evidence."""
import argparse
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_ap_mixed_timeout import (AP_MANIFEST, AP_SHA, SCOPE, FINAL_ALTITUDE, parameter_contract,
                                 validate_inputs, validate_offer, validate_mixed_target, validate_audit_output,
                                 initial_yaw_alignment)


class TimeoutContractTests(unittest.TestCase):
    def test_initial_yaw_alignment_never_waives_other_resets_or_mixed_resets(self):
        old=(401540302,1162593683,4997,5375,40888,3930)
        new=(*old[:3],48775,*old[4:])
        fields=dict(takeoff_preparation=True,observed=[],height=2.64,boot_us=48785000)
        self.assertTrue(initial_yaw_alignment(old,new,**fields))
        for key,value in (('takeoff_preparation',False),('observed',[{}]),('height',2.),('boot_us',48774000)):
            with self.subTest(key=key):
                self.assertFalse(initial_yaw_alignment(old,new,**dict(fields,**{key:value})))
        for index in (0,1,2,4,5):
            changed=list(new); changed[index]+=1
            self.assertFalse(initial_yaw_alignment(list(old),changed,**fields))

    def test_full_mixed_payload_refusal(self):
        zero = dict(x=0.,y=0.,z=0.)
        target = dict(type_mask=2531,coordinate_frame=6,header=dict(frame_id='map'),latitude=0.,longitude=0.,
                      yaw=0.,altitude=FINAL_ALTITUDE,velocity=dict(linear=dict(x=.8,y=.4,z=0.),angular=zero.copy()),
                      acceleration_or_force=dict(linear=zero.copy(),angular=zero.copy()))
        validate_mixed_target(target)
        for section,key in (('velocity','angular'),('acceleration_or_force','linear'),('acceleration_or_force','angular')):
            value = copy.deepcopy(target); value[section][key]['z'] = .1
            with self.subTest(section=section,key=key), self.assertRaises(ValueError):
                validate_mixed_target(value)
        for key,value in (('type_mask',2552),('altitude',6.),('yaw',float('nan')),('latitude',1.)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_mixed_target(dict(target,**{key:value}))

    def test_audit_never_overwrites_raw_or_existing_result(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); raw = base/'raw'; raw.mkdir()
            validate_audit_output(raw,base/'audit.json')
            with self.assertRaises(ValueError):
                validate_audit_output(raw,raw/'audit.json')
            existing = base/'existing.json'; existing.write_text('{}')
            with self.assertRaises(ValueError):
                validate_audit_output(raw,existing)

    def test_parameter_refusals(self):
        baseline = dict(GUID_TIMEOUT=3.,GUID_OPTIONS=0.,LOG_DISARMED=1.,FENCE_ENABLE=0.,AVOID_ENABLE=7.)
        self.assertEqual(parameter_contract(baseline),3000)
        for name,value in (('GUID_TIMEOUT',.1),('GUID_TIMEOUT',float('nan')),('GUID_OPTIONS',16.),
                           ('GUID_OPTIONS',32.),('GUID_OPTIONS',.5),('FENCE_ENABLE',1.),('LOG_DISARMED',0.)):
            with self.subTest(name=name,value=value), self.assertRaises(ValueError):
                parameter_contract(dict(baseline,**{name:value}))
        with self.assertRaises(ValueError):
            parameter_contract({key:value for key,value in baseline.items() if key!='AVOID_ENABLE'})

    def test_exact_candidate_inputs(self):
        values = dict(ap_mixed_manifest=AP_MANIFEST,ap_mixed_sha256=AP_SHA,
                      control_manifest='/root/wksim-joint-control-Example/build.json',control_sha256='a'*64)
        validate_inputs(argparse.Namespace(**values))
        for name,value in (('ap_mixed_manifest','/root/alternate/mixed-build.json'),('ap_mixed_sha256','a'*64),
                           ('control_manifest','/root/default/build.json'),('control_sha256','unsealed')):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_inputs(argparse.Namespace(**dict(values,**{name:value})))

    def test_recovery_offer_rejects_replay_identity_or_extra_policy(self):
        ready = dict(run_id='run',scene_epoch='scene',control_epoch='c'*32,start_token='d'*32,uav_id=1)
        offer = dict(version=1,scope=SCOPE,action='new_recovery_task',**ready)
        validate_offer(offer,ready)
        for key in ready:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_offer(dict(offer,**{key:'old'}),ready)
        with self.assertRaises(ValueError):
            validate_offer(dict(offer,allow_native_hold=True),ready)


if __name__=='__main__':
    unittest.main()
