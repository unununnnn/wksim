"""Identity continuity and actual launch selectors for the independent candidate."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_attitude_flight import launch_plan, same_identities


class AttitudeRunnerTests(unittest.TestCase):
    def test_later_imports_require_an_earlier_source_seal(self):
        identity={k:{'sha256':'fixed'} for k in ('ap','px4','model_build','native','control','setup_sha256')}
        identity['source_sha256']={'before.py':'a'}
        before={'ok':True,'identities':identity}
        after=copy.deepcopy(before)
        after['identities']['source_sha256']['task.py']='b'
        self.assertTrue(same_identities(before,after,{'task.py':'b'}))
        self.assertFalse(same_identities(before,after,{}))
        self.assertFalse(same_identities(before,after,{'task.py':'changed'}))
        for key in ('ap','px4','model_build','native','control','setup_sha256','source_sha256'):
            changed=copy.deepcopy(after); changed['identities'][key]['sha256']='changed'
            self.assertFalse(same_identities(before,changed,{'task.py':'b'}))
        after['ok']=False
        self.assertFalse(same_identities(before,after,{'task.py':'b'}))

    def test_explicit_candidate_flags_speed_and_dds_default_order(self):
        for stack in ('px4','arducopter'):
            config=dict(stack=stack,dds_workspace='/root/dds',px4_root='/root/px4/src',
                        ap_candidate='/root/ap',control_protocol='session_v1',run_id='attitude-test')
            plan=launch_plan(config,Path('/root/run'),'/root/model.so')
            self.assertEqual(plan['control'][-4:],['-p','native_attitude_profile:=attitude_thrust_v1',
                                                '-p','enable_external_attitude:=true'])
            self.assertIn('--raw',plan['physics'])
            if stack=='arducopter':
                self.assertEqual(plan['fc'][plan['fc'].index('--speedup')+1],'1')
                paths=plan['fc'][plan['fc'].index('--defaults')+1].split(',')
                self.assertTrue(paths[-2].endswith('attitude.parm'))
                self.assertTrue(paths[-1].endswith('dds.parm'))
            else:
                self.assertEqual(plan['fc_environment']['PX4_SIM_SPEED_FACTOR'],'1')


if __name__=='__main__': unittest.main()
