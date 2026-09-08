"""Offline auditor boundaries only; synthetic observations are never flight proof."""
import copy
import json
import math
import unittest

from tools.audit_pv_trajectory import analytic, tracking, truth_window, native_targets


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


class PVRawAuditBoundaries(unittest.TestCase):
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
