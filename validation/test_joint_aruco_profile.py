"""Experimental resources must never silently select the normal joint task."""
import copy
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime.config import ConfigError
from Simulator.wksim_runtime.joint_config import validate_joint_config
from Simulator.wksim_runtime.joint_aruco_profile import PROFILE, TASK, select_config
from Simulator.wksim_runtime.joint_profile import LEGACY_PROFILE, select_profile
from Simulator.wksim_runtime.joint_trajectory import supported_actions
from Simulator.wksim_runtime.joint_evidence import verify_tasks


def candidate():
    return dict(schema_version=1,kind='joint_scene',run_id='aruco-flight-example',
                runtime_profile=PROFILE,task=TASK,requested_rate=.5,
                aruco_experiment=dict(selected_stack='px4',
                    control=dict(path='/root/wksim-joint-control-ABC123/build.json',sha256='a'*64),
                    px4=dict(path='/root/wksim-px4-land-DEF456/land-build.json',sha256='b'*64)))


class ArUcoProfileTests(unittest.TestCase):
    def test_component_observation_requires_its_exact_path_pair(self):
        data=candidate()
        data['aruco_experiment']['px4']['path']='/root/wksim-px4-component-ABC123/component-build.json'
        value=validate_joint_config(data)
        selected=select_config(value)
        self.assertEqual(selected['manifests']['px4'],data['aruco_experiment']['px4'])
        self.assertFalse(selected['production_admitted'])
        for path in ('/root/wksim-px4-land-ABC123/component-build.json',
                     '/root/wksim-px4-component-ABC123/land-build.json',
                     '/root/wksim-px4-component-ABC123/../component-build.json'):
            data['aruco_experiment']['px4']['path']=path
            with self.assertRaises(ConfigError):validate_joint_config(data)

    def test_selection_changes_only_explicit_resources(self):
        baseline=select_profile(LEGACY_PROFILE)
        value=validate_joint_config(candidate()); selected=select_config(value)
        self.assertEqual(selected['manifests']['ap'],baseline['manifests']['ap'])
        self.assertEqual(selected['model_library'],baseline['model_library'])
        self.assertEqual(selected['capabilities'],[TASK])
        self.assertFalse(selected['production_admitted'])
        self.assertTrue(selected['experimental'])
        self.assertEqual(selected['setup_files'][:-1],baseline['setup_files'][:-1])
        self.assertEqual(selected['setup_files'][-1],'/root/wksim-joint-control-ABC123/install/local_setup.bash')
        self.assertEqual(select_profile(LEGACY_PROFILE),baseline)

    def test_missing_or_mixed_contract_rejected(self):
        for field,value in (('runtime_profile',LEGACY_PROFILE),('task','public_position'),
                            ('aruco_experiment',None),('requested_rate',1),
                            ('task_dwell_seconds',dict(hold=20))):
            with self.subTest(field=field):
                data=candidate();data[field]=value
                with self.assertRaises(ConfigError):validate_joint_config(data)

    def test_explicit_canonical_private_pins(self):
        for key,value in (('path','/root/wksim-px4-state-ONa1Kw/wksim-build.json'),
                          ('path','/root/wksim-px4-land-DEF456/../land-build.json'),
                          ('path','/root//wksim-px4-land-DEF456/land-build.json'),
                          ('sha256','not-a-hash'),('sha256',True)):
            data=candidate();data['aruco_experiment']['px4'][key]=value
            with self.subTest(value=value),self.assertRaises(ConfigError):validate_joint_config(data)

    def test_configuration_does_not_admit_or_run(self):
        with patch('subprocess.run',side_effect=AssertionError('unexpected subprocess')):
            select_config(validate_joint_config(candidate()))

    def test_default_remains_legacy(self):
        value=validate_joint_config(dict(schema_version=1,kind='joint_scene',run_id='plain',runtime_profile=LEGACY_PROFILE))
        self.assertEqual(value['task'],'public_position')
        self.assertNotIn('aruco_experiment',value)
        with self.assertRaises(ValueError):select_profile(PROFILE)

    def test_candidate_cannot_pause_recover_or_claim_flight(self):
        self.assertEqual(supported_actions(TASK,['start-task','pause','step','resume','recovery-task','stop','cold-reset']),
                         ['start-task','stop','cold-reset'])
        self.assertIsNone(verify_tasks(None,'a'*32,12000,{'fake':{'status':'pass'}},TASK))


if __name__=='__main__':unittest.main()
