"""Strict selection checks; mocked reports are not flight or build evidence."""
import unittest
import os
from pathlib import PurePosixPath
from unittest.mock import patch

from Simulator.wksim_runtime import independent_profile as profile
from Simulator.wksim_runtime import joint_profile


def config(stack='px4'):
    p = joint_profile.select_profile('joint_quad_dds_v1')
    data = dict(schema_version=1, run_id='independent-test', vehicle_id=1, stack=stack,
                runtime_profile=profile.PROFILE_ID, model_profile='quad_x',
                communication='native_dds', control_protocol='session_v1',
                dds_workspace=p['dds_workspace'], prometheus_workspace=p['control_workspace'],
                px4_root='/root/wksim-px4-state-ONa1Kw/src')
    if stack == 'arducopter':
        data['ap_candidate'] = '/root/wksim-ap-clock-stop-OXQqdR'
    return data


class IndependentProfileTests(unittest.TestCase):
    def test_strict_selection_before_resource_checks(self):
        changes = [dict(runtime_profile='unknown'), dict(control_protocol='legacy_v1'),
                   dict(capabilities=['unknown']), dict(capabilities=['native_position_mission', 'full.2']),
                   dict(dds_workspace='/wrong'), dict(prometheus_workspace='/wrong'),
                   dict(px4_root='/wrong'), dict(model_library='/wrong'), dict(run_id='../bad'),
                   dict(model_profile='plane'), dict(stack='unknown'),
                   dict(restart_control_on_ground=True)]
        with patch.object(joint_profile, 'check_resources', side_effect=AssertionError('must not inspect')):
            for change in changes:
                with self.subTest(change=change):
                    result = profile.check_profile(dict(config(), **change))
                    self.assertFalse(result['ok'])
                    self.assertEqual(result['children_created'], 0)
            self.assertFalse(profile.check_profile(dict(config('arducopter'), ap_candidate='/wrong'))['ok'])

    def test_only_selected_stack_requested_and_report_compatible(self):
        for stack in ('px4', 'arducopter'):
            key = 'ap' if stack == 'arducopter' else 'px4'
            report = dict(ok=True, reasons=[], children_created=0, model_library='/model',
                          identities={key: dict(path='/firmware', sha256='fw', commit='commit'),
                                      stack + '_agent': dict(path='/agent', sha256='agent'),
                                      'model': dict(library_sha256='model')})
            original = config(stack)
            with patch.object(joint_profile, 'check_resources', return_value=report) as check, \
                    patch.object(profile, 'check_flight_evidence', return_value={'mocked_contract_only': True}):
                result = profile.check_profile(original)
            self.assertEqual(check.call_args.kwargs, dict(stacks=(stack,)))
            self.assertTrue(result['ok'])
            self.assertTrue(result['candidate_status']['flown'])
            self.assertEqual(result['identities']['firmware']['expected_sha256'], 'fw')
            self.assertEqual(result['identities']['model_library']['path'], '/model')
            self.assertNotIn('model_library', original)
            self.assertEqual(result['config']['runtime_profile'], profile.PROFILE_ID)

    def test_resource_failure_preserved(self):
        with patch.object(joint_profile, 'check_resources', return_value=dict(
                ok=False, reasons=[dict(code='joint_profile_rejected', message='identity mismatch')],
                identities={}, children_created=0)):
            result = profile.check_profile(config())
        self.assertFalse(result['ok'])
        self.assertFalse(result['candidate_status']['built'])
        self.assertEqual(result['reasons'][0]['message'], 'identity mismatch')

    def test_resource_selector_cannot_weaken_pins(self):
        p = joint_profile.select_profile('joint_quad_dds_v1')
        self.assertFalse(joint_profile.check_resources(p, stacks=())['ok'])
        p['manifests']['px4']['sha256'] = 'wrong'
        self.assertFalse(joint_profile.check_resources(p, stacks=('px4',))['ok'])

    @unittest.skipUnless(os.name == 'posix', 'Ubuntu admission path')
    def test_shared_checker_does_not_read_peer_firmware(self):
        p = joint_profile.select_profile('joint_quad_dds_v1')
        for stack, key in (('px4', 'px4'), ('arducopter', 'ap')):
            records = [dict(candidate_root=str(PurePosixPath(p['manifests'][key]['path']).parent)),
                       dict(root=p['control_workspace'])]
            with patch.dict(os.environ, ROS_DISTRO='humble'), \
                    patch.object(joint_profile, '_pinned_json', side_effect=records) as read, \
                    patch.object(joint_profile, '_firmware', side_effect=ValueError('stop before source walk')) as firmware:
                result = joint_profile.check_resources(p, stacks=(stack,))
            self.assertFalse(result['ok'])
            self.assertEqual([call.args[0] for call in read.call_args_list],
                             [p['manifests'][key], p['manifests']['control']])
            self.assertEqual(firmware.call_args.args[1], key)


if __name__ == '__main__':
    unittest.main()
