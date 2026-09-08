"""Auditor preflight boundaries. Synthetic evidence never establishes a real flight."""
import copy
import json
import math
import os
from pathlib import Path
import unittest

from tools.audit_mixed_control import (PROFILE, f32, wire_request, quaternion_yaw, body_reference,
    command_contract, physical_metrics, truth_window, native_expected, native_matches,
    native_targets, guip_target, validate_build, rejected_bootstrap_ack, exact_request, completion_clock_ok,
    identical_status_duplicate, after_completed_window)


def header(seconds):
    ns = round(seconds*1e9)
    return dict(frame_id='map', stamp=dict(sec=ns//1_000_000_000, nanosec=ns % 1_000_000_000))


def row(sequence, seconds):
    return dict(sequence=sequence, tick=round(seconds*1000), wall=seconds*2)


def body_fixture(zero=False):
    yaw = .6
    q = [2*math.cos(yaw/2), 0., 0., 2*math.sin(yaw/2)]  # Normalization must be independent.
    w, x, y, z = (v/math.hypot(*q) for v in q)
    yaw = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
    command = dict(command_id=8, agent_cmd=4, move_mode=5, yaw_rate_mode=False,
                   position_ref=[0., 0., 0. if zero else 1.], velocity_ref=[0., 0., 0.] if zero else [f32(.8), f32(.4), 0.],
                   yaw_ref=0. if zero else f32(.3))
    x, y = command['velocity_ref'][:2]
    velocity = [x*math.cos(yaw)-y*math.sin(yaw), x*math.sin(yaw)+y*math.cos(yaw), 0.]
    p = [12., 8., 3.]
    altitude = p[2]+command['position_ref'][2]
    event = dict(event='mixed_body_reference_captured', request_id=11, command_id=8,
                 source_boot_ns=10_000_000_000, source_position=p, source_quaternion_wxyz=q, source_yaw=yaw,
                 reference_position=[0., 0., altitude], reference_velocity=velocity, reference_yaw=yaw+command['yaw_ref'],
                 shaped_position=[12., 8., altitude] if zero else [None, None, altitude],
                 shaped_velocity=[None]*3 if zero else velocity)
    state = dict(header=header(10), position=p, attitude_q=dict(zip(('w', 'x', 'y', 'z'), q)))
    states = [(row(9, 10.02), dict(state=state, last_request_id=11, source_received_valid=True,
              published_monotonic_s=20.02, source_received_monotonic_s=20.))]
    return command, event, states


def native_fixture():
    waypoint = dict(request_id=1, command=dict(header=header(10), agent_cmd=4, move_mode=0,
                                              position_ref=[2., 3., 3.], yaw_ref=0.))
    mixed = dict(request_id=2, command=dict(header=header(10.1), agent_cmd=4, move_mode=1,
                    position_ref=[0., 0., 4.], velocity_ref=[f32(.8), f32(.4), 0.], yaw_ref=0.))
    stop = dict(request_id=3, command=dict(header=header(10.2), agent_cmd=3, move_mode=0))
    zero = dict(x=0., y=0., z=0.)
    home = dict(time_boot_us=10_000_000, home_latitude_e7=400000000, home_longitude_e7=1000000000,
                home_valid=True, position_valid=True, velocity_valid=True, attitude_valid=True)
    p = dict(header=header(10), position=[2., 3., 3.])
    ref = dict(position=[2., 3., 3.], yaw=0.)
    expected = ([2., 3., 3.], [None]*3, 0.)
    latitude = home['home_latitude_e7']+int(3/.011131884502145034)
    longitude = home['home_longitude_e7']+int(2/(.011131884502145034*math.cos(math.radians((latitude+home['home_latitude_e7'])/2e7))))
    ap_hold = dict(header=header(10), type_mask=0x9F8, coordinate_frame=6, latitude=latitude/1e7, longitude=longitude/1e7,
        altitude=3., yaw=0., velocity=dict(linear=zero, angular=zero), acceleration_or_force=dict(linear=zero, angular=zero))
    ap_mixed = dict(ap_hold, header=header(10.15), type_mask=0x9E3, latitude=0., longitude=0., altitude=4.,
                    velocity=dict(linear=dict(x=f32(.8), y=f32(.4), z=0.), angular=zero))
    px_hold = dict(timestamp=10_000_000, position=[3., 2., -3.], velocity=[math.nan]*3,
                   acceleration=[math.nan]*3, jerk=[math.nan]*3, yaw=f32(math.pi/2), yawspeed=math.nan)
    px_mixed = dict(px_hold, timestamp=10_150_000, position=[math.nan, math.nan, -4.], velocity=[f32(.4), f32(.8), 0.])
    data = {'/ap/wksim/local_state_v1': [(row(15, 10.04), home), (row(25, 10.26), dict(home, time_boot_us=10_150_000))],
            '/ap/cmd_gps_pose': [(row(5, 10.02), ap_hold), (row(10, 10.24), ap_mixed)],
            '/px/fmu/out/vehicle_local_position': [(row(16, 10.04), dict(timestamp=10_000_000,
                xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True)), (row(26, 10.26), dict(timestamp=10_150_000,
                xy_valid=True, z_valid=True, v_xy_valid=True, v_z_valid=True))],
            '/px/fmu/in/trajectory_setpoint': [(row(6, 10.02), px_hold), (row(11, 10.24), px_mixed)],
            '/px/fmu/in/offboard_control_mode': [(row(17, 10.04), dict(timestamp=10_000_000, position=True,
                velocity=False, acceleration=False, attitude=False)), (row(27, 10.26), dict(timestamp=10_150_000,
                position=True, velocity=True, acceleration=False, attitude=False))]}
    requests, refs, tasks = {}, {}, {}
    for stack, uid in (('arducopter', 1), ('px4', 2)):
        requests[stack] = [(row(14, 10.03), copy.deepcopy(waypoint)), (row(24, 10.25), copy.deepcopy(mixed)),
                           (row(8, 10.21), copy.deepcopy(stop))]
        refs[stack] = dict(waypoint=dict(envelope=waypoint, reference=ref, first_state=p),
                          world_step=dict(envelope=mixed, reference=dict(velocity=[f32(.8), f32(.4)], altitude=4., yaw=0.), first_state=p))
        tasks[stack] = dict(mixed_segments=[dict(name='world_step', start_ns=10_100_000_000, end_ns=10_190_000_000)])
        data[f'/uav{uid}/prometheus/text_info'] = [(row(18, 10.04), dict(header=header(10), message=json.dumps(
            dict(event='command_accepted', request_id=1)))), (row(28, 10.26), dict(header=header(10.1), message=json.dumps(
            dict(event='command_accepted', request_id=2)))), (row(9, 10.21), dict(header=header(10.2), message=json.dumps(
            dict(event='command_accepted', request_id=3))))]
        data[f'/uav{uid}/prometheus/v2/state'] = [(row(19, 10.04), dict(state=p, source_received_valid=True,
            published_monotonic_s=20.02, source_received_monotonic_s=20.)), (row(29, 10.26), dict(state=dict(p, header=header(10.15)),
            source_received_valid=True, published_monotonic_s=20.5, source_received_monotonic_s=20.48))]
    return data, requests, refs, tasks


class MixedRawAuditBoundaries(unittest.TestCase):
    def test_source_stamp_overlap_needs_a_completed_window_and_new_acceptance(self):
        self.assertTrue(after_completed_window(6, 5, 60_672_000_000, 60_672_000_000, 60673))
        self.assertFalse(after_completed_window(6, 5, 60_671_000_000, 60_672_000_000, 60673))
        self.assertFalse(after_completed_window(6, 5, 60_672_000_000, 60_672_000_000, 60671))
        self.assertFalse(after_completed_window(5, 5, 60_672_000_000, 60_672_000_000, 60673))

    def test_duplicate_status_requires_two_identical_raw_statuses(self):
        event = dict(event='native_input_rejected', reason='duplicate_source', source='status', source_stamp=1000)
        sample = dict(timestamp=1000, system_id=22, nav_state=18)
        data = {'/px/fmu/out/vehicle_status': [(row(1, .001), sample), (row(2, .001), dict(sample))]}
        self.assertTrue(identical_status_duplicate(event, row(3, .002), data, 'px4'))
        self.assertFalse(identical_status_duplicate(event, row(3, .002), data, 'arducopter'))
        self.assertFalse(identical_status_duplicate(dict(event, reason='regressed_source'), row(3, .002), data, 'px4'))
        data['/px/fmu/out/vehicle_status'][1][1]['nav_state'] = 14
        self.assertFalse(identical_status_duplicate(event, row(3, .002), data, 'px4'))

    def test_setup_completion_is_not_input_receipt_age(self):
        takeoff = dict(header=header(10), cmd=3)
        self.assertTrue(completion_clock_ok(takeoff, 16_000_000_000, 16001, setup=True))
        self.assertFalse(completion_clock_ok(takeoff, 51_000_000_000, 51001, setup=True))
        move = dict(header=header(10))
        self.assertTrue(completion_clock_ok(move, 9_996_000_000, 10001, setup=False))
        self.assertFalse(completion_clock_ok(move, 9_000_000_000, 10001, setup=False))
        self.assertFalse(completion_clock_ok(move, 13_000_000_000, 13001, setup=False))
        self.assertFalse(completion_clock_ok(takeoff, 16_000_000_000, 15000, setup=True))

    def test_mixed_build_is_its_own_schema_and_fixed_chain(self):
        admission = json.loads((Path(__file__).parent/'ap-mixed-20260909/admission-02.json').read_text())
        validate_build(admission['candidate'], admission['candidate_verification'])
        for key, value in (('profile', 'full_xyz_pv_yaw_v1'), ('schema_version', True),
                           ('baseline_manifest_sha256', '0'*64), ('production_admitted', True)):
            bad = copy.deepcopy(admission['candidate']); bad[key] = value
            with self.assertRaises(ValueError):
                validate_build(bad, admission['candidate_verification'])

    def test_actual_quaternion_capture_and_shape_are_independent(self):
        for zero in (False, True):
            command, capture, states = body_fixture(zero)
            result = body_reference(command, capture, states)
            self.assertAlmostEqual(result['yaw'], .6+command['yaw_ref'])
            self.assertEqual(result['altitude'], 3. if zero else 4.)
            for key, value in (('source_yaw', .61), ('source_position', [12.1, 8., 3.]),
                               ('reference_velocity', [.8, .4, 0.]), ('shaped_velocity', [0.]*3),
                               ('source_boot_ns', 9_000_000_000)):
                bad = dict(capture, **{key:value})
                with self.assertRaises(ValueError, msg=key):
                    body_reference(command, bad, states)
        with self.assertRaises(ValueError):
            quaternion_yaw([0.]*4)
        with self.assertRaises(ValueError):
            body_reference(command, capture, [])

    def test_no_recapture_or_rotate_with_later_yaw(self):
        command, capture, states = body_fixture()
        good = body_reference(command, capture, states)
        record = dict(reference=good, first_state=states[0][1]['state'])
        first = native_expected('body_step', record, dict(position=[12., 8., 3.]))
        later = native_expected('body_step', record, dict(position=[18., 16., 4.], attitude=[0., 0., 1.3]))
        self.assertEqual(first, later)
        bad = copy.deepcopy(capture); bad['reference_yaw'] += .3
        with self.assertRaises(ValueError):
            body_reference(command, bad, states)

    def test_one_axis_existing_hold_feedback_is_not_constant_zero(self):
        record = dict(reference=dict(velocity=[0., f32(.6)], altitude=3., yaw=0.), first_state=dict(position=[10., 8., 3.]))
        target = native_expected('world_one_axis', record, dict(position=[10.2, 8., 3.]))
        self.assertEqual(target[0], [None, None, 3.])
        self.assertAlmostEqual(target[1][0], -f32(1.8)*.2)
        self.assertEqual(target[1][1:], [f32(.6), 0.])
        self.assertEqual(native_expected('world_one_axis', record, dict(position=[10.01, 8., 3.]))[1][0], 0.)

    def test_native_masks_and_original_px4_vertical_sentinel(self):
        data, _, _, _ = native_fixture()
        ap = data['/ap/cmd_gps_pose'][1][1]; px = data['/px/fmu/in/trajectory_setpoint'][1][1]
        expected = ([None, None, 4.], [f32(.8), f32(.4), 0.], 0.)
        self.assertTrue(native_matches('arducopter', ap, expected))
        self.assertTrue(native_matches('px4', px, expected))
        for key, value in (('type_mask', 0x9C0), ('type_mask', 0x9F8), ('latitude', 40.), ('altitude', 3.)):
            self.assertFalse(native_matches('arducopter', dict(ap, **{key:value}), expected))
        for velocity in ([f32(.4), f32(.8), math.nan], [f32(.4), f32(.8), .1]):
            self.assertFalse(native_matches('px4', dict(px, velocity=velocity), expected))

    def test_cross_topic_reordering_and_bounded_overlap(self):
        data, requests, refs, tasks = native_fixture()
        report = native_targets(data, requests, refs, tasks)
        self.assertEqual(report['arducopter']['cross_topic_boundary_observations'], 1)
        self.assertEqual(report['px4']['targets_inside_windows'], {'world_step':1})
        bad = copy.deepcopy(data)
        bad['/ap/cmd_gps_pose'][1][0]['wall'] += 3
        with self.assertRaises(ValueError):
            native_targets(bad, requests, refs, tasks)
        bad = copy.deepcopy(data); bad['/px/fmu/in/offboard_control_mode'].pop()
        with self.assertRaises(ValueError):
            native_targets(bad, requests, refs, tasks)

    def test_native_guip_type7_has_inactive_placeholders(self):
        data, _, _, _ = native_fixture()
        target = data['/ap/cmd_gps_pose'][1][1]
        rows = [dict(boot_us=10_150_000, target=target)]
        message = dict(TimeUS=10_160_000, Type=7, pX=0., pY=0., pZ=-8.35, Terrain=0,
                       vX=f32(.4), vY=f32(.8), vZ=0., aX=0., aY=0., aZ=0.)
        self.assertEqual(guip_target(message, rows), rows)  # pZ deliberately differs from home Z.
        for key, value in (('Type', 3), ('pX', 1.), ('vZ', .1), ('Terrain', 1), ('pZ', math.nan)):
            with self.assertRaises(ValueError):
                guip_target(dict(message, **{key:value}), rows)
        self.assertEqual(guip_target(dict(message, vY=.1), rows), [])

    def test_every_millisecond_frozen_physical_gates(self):
        reference = dict(velocity=[.8, .4], altitude=4., yaw=0.)
        state = [0.]*120; state[8] = -4.; state[3:5] = [.4, .8]; state[11] = math.pi/2
        self.assertEqual(physical_metrics(state, 'world_step', reference)['xy_velocity_error_m_s'], 0.)
        rows = [copy.deepcopy(state) for _ in range(3001)]
        rows[1703][4] += .300001
        with self.assertRaisesRegex(ValueError, '1ms mixed tracking'):
            for item in truth_window(rows, 1_000_000, 3_001_000_000):
                physical_metrics(item, 'world_step', reference)
        for index, value in ((8, -4.500001), (11, math.pi/2+.150001)):
            bad = copy.deepcopy(state); bad[index] = value
            with self.assertRaises(ValueError):
                physical_metrics(bad, 'world_step', reference)
        with self.assertRaises(ValueError):
            truth_window(rows, 1_000_001, 3_001_000_000)
        with self.assertRaises(ValueError):
            truth_window(rows, 1_000_000, 3_002_000_000)

    def test_one_axis_zero_and_rejection_no_effect_limits(self):
        state = [0.]*120; state[8] = -3.; state[11] = math.pi/2; state[6:8] = [8., 10.]
        ref = dict(velocity=[0., .6], altitude=3., yaw=0.)
        state[3] = .6
        physical_metrics(state, 'world_one_axis', ref, [10., 8., 3.])
        state[4] = .250001
        with self.assertRaises(ValueError):
            physical_metrics(state, 'world_one_axis', ref, [10., 8., 3.])
        state[3:5] = [0., 0.]
        for name in ('world_zero', 'body_zero', 'invalid_world_yaw_rate', 'world_absolute_stop', 'body_absolute_stop'):
            ref = dict(velocity=[0., 0.], altitude=3., yaw=0.)
            physical_metrics(state, name, ref, [10., 8., 3.])
            with self.assertRaises(ValueError):
                physical_metrics(state, name, ref, [8.999999, 8., 3.])

    def test_unsolicited_ack_exception_never_accepts_a_task_failure(self):
        event = dict(event='native_input_rejected', reason='unmatched_ack', source='ack', request_id=0,
                     command=211, request_identity=[51, 80])
        self.assertTrue(rejected_bootstrap_ack(event, 1, 100))
        self.assertFalse(rejected_bootstrap_ack(dict(event, request_id=8), 1, 100))
        self.assertFalse(rejected_bootstrap_ack(event, 101, 100))

    def test_request_equality_never_coerces_bool_integer_or_float(self):
        retained = dict(request_id=8, command=dict(yaw_ref=.3, yaw_rate_mode=False, position_ref=[0., 0., 3.]))
        raw = wire_request(retained)
        self.assertTrue(exact_request(raw, retained))
        for field, value in (('yaw_rate_mode', 0), ('position_ref', [0, 0, 3])):
            bad = copy.deepcopy(raw); bad['command'][field] = value
            self.assertFalse(exact_request(bad, retained))
        self.assertFalse(exact_request(dict(raw, request_id=8.), retained))

    @unittest.skipUnless(os.environ.get('WKSIM_TEST_PRIVATE_ROS') == '1', 'requires actual generated ROS codec')
    def test_real_float32_codec_preserves_exact_request_identity_and_values(self):
        from prometheus_msgs.msg import UAVCommand
        from wksim_msgs.msg import CommandRequest
        from rclpy.serialization import serialize_message, deserialize_message
        from rosidl_runtime_py.convert import message_to_ordereddict
        command = UAVCommand(agent_cmd=4, move_mode=5, yaw_ref=.3, position_ref=[0., 0., 1.],
                             velocity_ref=[.8, .4, 0.], command_id=8)
        message = CommandRequest(version=1, run_id='mixed-codec-test', control_epoch='a'*32, request_id=11, command=command)
        original = message_to_ordereddict(message)
        decoded = message_to_ordereddict(deserialize_message(serialize_message(message), CommandRequest))
        self.assertNotEqual(original, decoded)
        self.assertEqual(wire_request(original), decoded)
        for key, value in (('request_id', 12), ('version', 2), ('control_epoch', 'b'*32)):
            self.assertNotEqual(wire_request(original), dict(decoded, **{key:value}))
        for key, value in (('yaw_ref', decoded['command']['yaw_ref']+1e-7), ('yaw_rate_mode', True),
                           ('position_ref', [0., 0., 1.00001]), ('velocity_ref', [.8, .4, .00001]), ('move_mode', 1)):
            bad = copy.deepcopy(decoded); bad['command'][key] = value
            self.assertNotEqual(wire_request(original), bad)


if __name__ == '__main__':
    unittest.main()
