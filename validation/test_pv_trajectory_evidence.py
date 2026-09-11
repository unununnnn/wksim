"""Offline auditor boundaries only; synthetic observations are never flight proof."""
import copy
import hashlib
import json
import math
import os
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.audit_pv_trajectory import analytic, tracking, truth_window, native_targets, wire_request, rejected_bootstrap_ack


def header(seconds):
    ns = round(seconds*1e9)
    return dict(frame_id='map', stamp=dict(sec=ns//1_000_000_000, nanosec=ns % 1_000_000_000))


def row(sequence, seconds):
    return dict(sequence=sequence, tick=round(seconds*1000), wall=seconds*2)


def native_fixture():
    command = dict(header=header(10), agent_cmd=4, move_mode=6, position_ref=[0., 0., 3.],
                   velocity_ref=[.1, .2, .3], yaw_ref=0.)
    request = dict(request_id=1, command=command)
    stop = dict(request_id=2, command=dict(header=header(10.1), agent_cmd=2, move_mode=0))
    zero = dict(x=0., y=0., z=0.)
    home = dict(time_boot_us=10_000_000, home_latitude_e7=400000000, home_longitude_e7=1000000000,
                home_valid=True, position_valid=True, velocity_valid=True, attitude_valid=True)
    ap = dict(header=header(10), type_mask=2496, coordinate_frame=6, latitude=40., longitude=100., altitude=3., yaw=0.,
              velocity=dict(linear=dict(x=.1, y=.2, z=.3), angular=zero),
              acceleration_or_force=dict(linear=zero, angular=zero))
    px = dict(timestamp=10_000_000, position=[0., 0., -3.], velocity=[.2, .1, -.3],
              acceleration=[math.nan]*3, jerk=[math.nan]*3, yaw=math.pi/2, yawspeed=math.nan)
    # Public request, acceptance, local state and Offboard callbacks deliberately
    # arrive after the native target. STOP arrives before that delayed target.
    data = {'/ap/wksim/local_state_v1': [(row(9, 10.13), home)], '/ap/cmd_gps_pose': [(row(5, 10.12), ap)],
            '/px/fmu/out/vehicle_local_position': [(row(10, 10.13), dict(timestamp=10_000_000,
                xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True))],
            '/px/fmu/in/trajectory_setpoint': [(row(6, 10.12), px)],
            '/px/fmu/in/offboard_control_mode': [(row(12, 10.14), dict(timestamp=10_000_000,
                position=True, velocity=True, acceleration=False, attitude=False))]}
    requests = {stack: [(row(8, 10.13), copy.deepcopy(request)), (row(3, 10.11), copy.deepcopy(stop))]
                for stack in ('arducopter', 'px4')}
    for uid in (1, 2):
        data[f'/uav{uid}/prometheus/text_info'] = [(row(11, 10.14), dict(header=header(10), message=json.dumps(
            dict(event='command_accepted', request_id=1)))), (row(4, 10.11), dict(header=header(10.1),
            message=json.dumps(dict(event='command_accepted', request_id=2))))]
    return data, requests


def model_evidence_fixture(root):
    epoch = 'a'*32
    library = root/'fixed-model.so'
    library.write_bytes(b'fixed-model')
    library_sha256 = hashlib.sha256(library.read_bytes()).hexdigest()
    model = dict(library=str(library), library_sha256=library_sha256)
    summaries = {}
    children = {}
    for stack in ('arducopter', 'px4'):
        trace = root/(stack+'-truth.jsonl')
        trace.write_bytes(b'{}\n')
        summary = dict(submitted_bytes=3, written_bytes=3, queue_highwater=1,
                       alive=False, closed=True, error=None, io_calls=1,
                       max_io_wall_ns=10, complete=True, epoch=epoch,
                       truth_trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
                       model_library=str(library), model_library_sha256=library_sha256,
                       writer_scheduler=dict(available=True, policy='SCHED_OTHER', priority=0,
                                             actual_policy=0, actual_priority=0))
        Path(str(trace)+'.writer.json').write_text(json.dumps(summary))
        summaries[stack] = summary
        children[stack+'-model'] = {
            'argv': ['python', '--async-evidence'],
            'scheduling': {'reset_on_fork': True, 'actual_policy': 0x40000001,
                           'actual_priority': 40},
        }
    result = dict(scene_epoch=epoch, epoch=epoch, model_library=str(library),
                  model_build=dict(model), pv_admission=dict(
                      model_library=str(library), identities=dict(
                          baseline=dict(model=dict(model)))),
                  async_model_evidence_requested=True, async_evidence_requested=False,
                  manager_scheduling={'reset_on_fork': True, 'actual_policy': 0x40000001,
                                      'actual_priority': 50},
                  source_sha256={'Simulator/wksim_runtime/evidence_stream.py': 'a'*64},
                  children=children, async_model_evidence=summaries)
    return result


class PVRawAuditBoundaries(unittest.TestCase):
    def test_async_model_evidence_requires_both_current_writer_sidecars(self):
        from tools import audit_pv_trajectory as audit
        with TemporaryDirectory(prefix='pv-model-evidence-') as directory:
            root = Path(directory)
            result = model_evidence_fixture(root)
            checked = audit.model_evidence_identity(root, result)
            self.assertTrue(checked['requested'])
            self.assertEqual(checked['stacks']['px4']['truth_bytes'], 3)

    def test_async_model_evidence_rejects_missing_flag_or_incomplete_sidecar(self):
        from tools import audit_pv_trajectory as audit
        with TemporaryDirectory(prefix='pv-model-evidence-') as directory:
            root = Path(directory)
            result = model_evidence_fixture(root)
            result['children']['px4-model']['argv'] = ['python']
            with self.assertRaisesRegex(ValueError, 'px4 model was not launched'):
                audit.model_evidence_identity(root, result)

    def test_async_model_evidence_rejects_scheduler_inheritance_gap(self):
        from tools import audit_pv_trajectory as audit
        with TemporaryDirectory(prefix='pv-model-evidence-') as directory:
            root = Path(directory)
            result = model_evidence_fixture(root)
            result['children']['px4-model']['scheduling']['actual_policy'] = 1
            with self.assertRaisesRegex(ValueError, 'px4 model did not reset'):
                audit.model_evidence_identity(root, result)

    def test_async_model_evidence_rejects_each_identity_mismatch_per_stack(self):
        from tools import audit_pv_trajectory as audit
        for stack in ('arducopter', 'px4'):
            for field, bad in (('epoch', 'b'*32),
                               ('truth_trace_sha256', 'b'*64),
                               ('model_library', '/wrong/model.so'),
                               ('model_library_sha256', 'b'*64)):
                with self.subTest(stack=stack, field=field), TemporaryDirectory(prefix='pv-model-evidence-') as directory:
                    root = Path(directory)
                    result = model_evidence_fixture(root)
                    result['async_model_evidence'][stack][field] = bad
                    Path(str(root/(stack+'-truth.jsonl'))+'.writer.json').write_text(
                        json.dumps(result['async_model_evidence'][stack]))
                    with self.assertRaisesRegex(ValueError, stack+' model evidence'):
                        audit.model_evidence_identity(root, result)

    def test_async_model_evidence_rejects_result_summary_mismatch_and_trace_rehash(self):
        from tools import audit_pv_trajectory as audit
        with TemporaryDirectory(prefix='pv-model-evidence-') as directory:
            root = Path(directory)
            result = model_evidence_fixture(root)
            result['async_model_evidence']['px4']['complete'] = False
            with self.assertRaisesRegex(ValueError, 'px4 model evidence writer'):
                audit.model_evidence_identity(root, result)

        with TemporaryDirectory(prefix='pv-model-evidence-') as directory:
            root = Path(directory)
            result = model_evidence_fixture(root)
            trace = root/'arducopter-truth.jsonl'
            trace.write_bytes(b'changed\n')
            with self.assertRaisesRegex(ValueError, 'arducopter model evidence truth digest'):
                audit.model_evidence_identity(root, result)

    def test_unrequested_model_evidence_remains_compatible_with_legacy_result(self):
        from tools import audit_pv_trajectory as audit
        self.assertEqual(audit.model_evidence_identity(Path('/unused'), {}),
                         dict(requested=False, legacy=True))
        self.assertEqual(audit.model_evidence_identity(Path('/unused'),
                                                        {'async_model_evidence_requested': False}),
                         dict(requested=False, legacy=False))

    def test_explicit_message_candidate_is_bound_to_admission_archive_and_recheck(self):
        from tools import audit_pv_trajectory as audit
        candidate = dict(root='/root/wksim-ros2-Test12', packages={name: {
            'prefix': '/root/wksim-ros2-Test12/install/'+name}
            for name in ('prometheus_msgs', 'wksim_msgs')})
        with TemporaryDirectory(prefix='pv-message-evidence-') as directory:
            root = Path(directory)
            archived = root/'message-build.json'
            archived.write_text(json.dumps(candidate))
            checksum = hashlib.sha256(archived.read_bytes()).hexdigest()
            admission = dict(message_candidate=candidate,
                             message_manifest_path=str(Path(candidate['root'])/'message-build.json'),
                             message_manifest_sha256=checksum,
                             identities=dict(message_candidate=candidate))
            result = dict(message_candidate=candidate, message_unchanged=True,
                          manifest_sha256={'message': checksum}, pv_admission=admission,
                          control_candidate={'package': '/root/control/prometheus_control'},
                          candidate_import_roots={
                              'prometheus_control': '/root/control/prometheus_control',
                              'prometheus_msgs': str(Path('/root/wksim-ros2-Test12/install/prometheus_msgs/local/lib/python3.10/dist-packages/prometheus_msgs')),
                              'wksim_msgs': str(Path('/root/wksim-ros2-Test12/install/wksim_msgs/local/lib/python3.10/dist-packages/wksim_msgs'))},
                          source_sha256={'tools/joint_message_candidate.py': 'a'*64})
            with patch('joint_message_candidate.check', return_value=candidate) as checker:
                checked = audit.message_evidence_identity(root, result)
            self.assertTrue(checked['requested'])
            checker.assert_called_once_with(Path(candidate['root'])/'message-build.json', checksum)
            for change in (
                    lambda value: value.update(message_unchanged=False),
                    lambda value: value['manifest_sha256'].update(message='b'*64),
                    lambda value: value['pv_admission'].update(message_manifest_path='/root/wrong.json'),
                    lambda value: value['pv_admission']['identities'].update(message_candidate={}),
                    lambda value: value['source_sha256'].clear()):
                altered = copy.deepcopy(result)
                change(altered)
                with self.subTest(change=change), patch('joint_message_candidate.check', return_value=candidate), \
                        self.assertRaises(ValueError):
                    audit.message_evidence_identity(root, altered)

    def test_missing_message_fields_are_legacy_only_when_all_are_absent(self):
        from tools import audit_pv_trajectory as audit
        self.assertEqual(audit.message_evidence_identity(Path('/unused'), {}),
                         dict(requested=False, legacy=True))
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            audit.message_evidence_identity(Path('/unused'),
                                            {'message_candidate': {'root': '/root/wksim-ros2-Test12'}})

    def test_explicit_message_candidate_replaces_only_its_decoder_packages(self):
        from tools import audit_pv_trajectory as audit
        baseline = {name: {'prefix': '/old/'+name, 'sha256': name}
                    for name in ('prometheus_msgs', 'wksim_msgs', 'px4_msgs', 'ardupilot_msgs')}
        current = {name: {'prefix': '/new/'+name, 'installed_sha256': 'new-'+name}
                   for name in ('prometheus_msgs', 'wksim_msgs')}
        result = dict(pv_admission={'identities': {'baseline': {'message_packages': baseline}}},
                      message_candidate={'packages': current})
        packages = audit.decoder_message_packages(result, 'pv_admission')
        self.assertEqual(packages['px4_msgs'], baseline['px4_msgs'])
        for name in current:
            self.assertEqual(packages[name], dict(prefix='/new/'+name, sha256='new-'+name,
                                                  complete_snapshot=True))
        result['message_candidate']['packages'].pop('wksim_msgs')
        with self.assertRaisesRegex(ValueError, 'package set'):
            audit.decoder_message_packages(result, 'pv_admission')

    def test_mixed_identity_is_dispatched_without_relabeling(self):
        from tools import audit_pv_trajectory as audit
        result = dict(mixed_admission=dict(task_profile=audit.PROFILE))
        with patch('audit_mixed_control.retained_identity', return_value={'checked': 'mixed'}) as checker:
            self.assertEqual(audit.retained_identity(Path('/unused'), result), {'checked': 'mixed'})
            checker.assert_called_once_with(Path('/unused'), result, task_profile=audit.PROFILE)
        self.assertNotIn('pv_admission', result)

    def test_control_flags_distinguish_old_mixed_and_final_dual_profile(self):
        from tools.audit_mixed_control import control_profiles, PROFILE, PV_PROFILE
        result = dict(children={stack+'-control': dict(argv=['python', '--ros-args'])
                                for stack in ('arducopter', 'px4')})
        argv = result['children']['arducopter-control']['argv']
        argv += ['-p', 'arducopter_mixed_profile:='+PROFILE]
        self.assertEqual(control_profiles(result), {'arducopter_mixed_profile': PROFILE})
        with self.assertRaisesRegex(ValueError, 'was not enabled'):
            control_profiles(result, require_pv=True)
        argv += ['-p', 'arducopter_pv_profile:='+PV_PROFILE]
        self.assertEqual(len(control_profiles(result, require_pv=True)), 2)
        for bad in ('arducopter_pv_profile:=wrong', 'arducopter_pv_profile:='+PV_PROFILE):
            changed = copy.deepcopy(result)
            changed['children']['arducopter-control']['argv'] += ['-p', bad]
            with self.assertRaises(ValueError):
                control_profiles(changed, require_pv=True)
        changed = copy.deepcopy(result)
        changed['children']['px4-control']['argv'] += ['-p', 'arducopter_pv_profile:='+PV_PROFILE]
        with self.assertRaises(ValueError):
            control_profiles(changed, require_pv=True)

    def test_unsolicited_bootstrap_ack_does_not_allow_a_failed_task_request(self):
        event = dict(event='native_input_rejected', reason='unmatched_ack', source='ack',
                     request_id=0, command=211, request_identity=[51, 80])
        self.assertTrue(rejected_bootstrap_ack(event, 60_000_000, 40_000_000_000))
        self.assertFalse(rejected_bootstrap_ack(event, 40_000_000_000, 40_000_000_000))
        for key, value in (('request_id', 1), ('source', 'position'), ('reason', 'regressed_source'),
                           ('event', 'setup_rejected'), ('request_identity', [256, 1])):
            self.assertFalse(rejected_bootstrap_ack(dict(event, **{key:value}), 1, 10))

    @unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS') == '1', 'requires actual generated ROS codec')
    def test_only_declared_yaw_float32_encoding_is_normalized(self):
        from prometheus_msgs.msg import UAVCommand
        from wksim_msgs.msg import CommandRequest
        from rclpy.serialization import serialize_message, deserialize_message
        from rosidl_runtime_py.convert import message_to_ordereddict
        command = UAVCommand(yaw_ref=.123456789, position_ref=[2., 3., 3.], command_id=4)
        message = CommandRequest(version=1, run_id='pv-codec-test', control_epoch='a'*32, request_id=7, command=command)
        request = message_to_ordereddict(message)
        original = copy.deepcopy(request)
        expected = message_to_ordereddict(deserialize_message(serialize_message(message), CommandRequest))
        self.assertNotEqual(request, expected)
        self.assertEqual(wire_request(request), expected)
        self.assertEqual(request, original)
        for key, value in (('request_id', 8),):
            changed = copy.deepcopy(expected); changed[key] = value
            self.assertNotEqual(wire_request(request), changed)
        changed = copy.deepcopy(expected); changed['command']['position_ref'][1] += 1e-5
        self.assertNotEqual(wire_request(request), changed)
        changed = copy.deepcopy(expected); changed['command']['yaw_ref'] += 1e-7
        self.assertNotEqual(wire_request(request), changed)

    def test_independent_polynomial_endpoints(self):
        for leg in (1, 2):
            start = analytic(0, [2, 3, 3], 0, leg)
            self.assertEqual(start, ([2., 3., 3.], [0., 0., 0.], [0., 0., 0.], 0.))
            self.assertEqual(analytic(12, [2, 3, 3], 0, leg)[1:3], ([0., 0., 0.], [0., 0., 0.]))

    def test_every_millisecond_and_original_gates(self):
        state = [0.]*120
        state[11] = math.pi/2
        expected = ([0., 0., 0.], [0., 0., 0.], [0., 0., 0.], 0.)
        self.assertEqual(tracking(state, expected), [0., 0., 0.])
        rows = [copy.deepcopy(state) for _ in range(12001)]
        self.assertEqual(len(truth_window(rows, 1_000_000, 12_001_000_000)), 12001)
        for index, value in ((6, .500001), (3, .300001), (11, math.pi/2+.150001)):
            bad = copy.deepcopy(state); bad[index] = value
            with self.assertRaisesRegex(ValueError, 'gate exceeded'):
                tracking(bad, expected)
        rows[7000][3] = .300001
        with self.assertRaises(ValueError):
            for value in truth_window(rows, 1_000_000, 12_001_000_000):
                tracking(value, expected)
        with self.assertRaises(ValueError):
            truth_window(rows, 1_000_001, 12_001_000_000)

    def test_cross_topic_reordering_preserves_known_binding(self):
        data, requests = native_fixture()
        report = native_targets(data, requests)
        self.assertEqual(report['arducopter']['full_pv_targets'], 1)
        self.assertEqual(report['px4']['cross_topic_boundary_observations'], 1)
        self.assertFalse(report['arducopter']['target_ack_available'])

    def test_unknown_target_and_active_acceleration_fail(self):
        data, requests = native_fixture()
        data['/ap/cmd_gps_pose'][0][1]['velocity']['linear']['x'] = .9
        with self.assertRaisesRegex(ValueError, 'differs from every prior'):
            native_targets(data, requests)
        data, requests = native_fixture()
        data['/px/fmu/in/trajectory_setpoint'][0][1]['acceleration'][0] = 0.
        with self.assertRaisesRegex(ValueError, 'active acceleration'):
            native_targets(data, requests)

    def test_unbounded_overlap_and_missing_source_fail(self):
        data, requests = native_fixture()
        data['/ap/cmd_gps_pose'][0][0]['wall'] += 2.01
        with self.assertRaises(ValueError):
            native_targets(data, requests)
        data, requests = native_fixture()
        data['/ap/wksim/local_state_v1'][0][1]['time_boot_us'] += 1
        with self.assertRaisesRegex(ValueError, 'bootstamp'):
            native_targets(data, requests)


if __name__ == '__main__':
    unittest.main()
