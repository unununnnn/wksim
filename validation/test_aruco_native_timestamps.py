"""Offline tests for tools/audit_aruco_native_timestamps.py.

Checker logic is exercised directly with real installed ROS message objects (construct
+ CDR round-trip via rclpy serialization only; no node/simulation/DDS participant).
The PX4 reference is matched by CONTENT (header value + ENU position/velocity) against
the following SessionState — never by feedback recency — because the single-threaded
tick builds state and setpoint from the SAME consumed sample while newer produced
samples may sit unconsumed in the queue. The payload clock (timestamp) and the state
header clock (timestamp_sample or timestamp) are resolved independently, never equated.

Pure-logic boundary cases run anywhere; the CDR cases are skipped where the ROS
message overlays are unavailable (Windows) and run in WSL.
"""
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.audit_aruco_native_timestamps import (
    check_px4, check_ap, header_us, lp_header, px4_reference_timestamps)

try:
    from rclpy.serialization import serialize_message, deserialize_message
    from px4_msgs.msg import TrajectorySetpoint, VehicleLocalPosition
    from geometry_msgs.msg import TwistStamped, Twist, Vector3
    from ardupilot_msgs.msg import GlobalPosition
    from wksim_msgs.msg import SessionState
    from prometheus_msgs.msg import UAVState, UAVControlState
    ROS = True
except ImportError:
    ROS = False

RUN = 'aruco-ts-test'
EPOCH = 'ab' * 16
SETPOINT_TOPIC = '/wksim_px4_21/fmu/in/trajectory_setpoint'
LP_TOPIC = '/wksim_px4_21/fmu/out/vehicle_local_position_v1'
PX4_STATE_TOPIC = '/uav2/prometheus/v2/state'
AP_STATE_TOPIC = '/uav1/prometheus/v2/state'
CMD_VEL = '/ap/cmd_vel'
CMD_GPS = '/ap/cmd_gps_pose'


class PureLogic(unittest.TestCase):
    """Attribute-boundary cases for the pure matchers (no ROS needed)."""

    def test_header_us_is_stamp_us_inverse(self):
        # stamp_us stores nanosec = (us % 1_000_000) * 1000, so 3_250_000us -> sec=3, nanosec=250_000_000.
        self.assertEqual(header_us(NS(sec=3, nanosec=250_000_000)), 3_250_000)
        self.assertEqual(header_us(NS(sec=0, nanosec=0)), 0)

    def test_header_us_rejects_non_microsecond_product(self):
        self.assertIsNone(header_us(NS(sec=1, nanosec=1)))
        self.assertIsNone(header_us(NS(sec=0, nanosec=999)))

    def test_lp_header_prefers_sample_then_timestamp(self):
        self.assertEqual(lp_header(NS(timestamp_sample=1500, timestamp=2000)), 1500)
        self.assertEqual(lp_header(NS(timestamp_sample=0, timestamp=2000)), 2000)

    def test_reference_matches_content_not_recency(self):
        older = NS(timestamp=2000, timestamp_sample=0,
                   x=1.0, y=2.0, z=3.0, vx=0.5, vy=0.25, vz=-0.25)
        newer = NS(timestamp=3000, timestamp_sample=0,
                   x=9.0, y=9.0, z=9.0, vx=9.0, vy=9.0, vz=9.0)  # produced, not consumed
        feedback = [({'source_timestamp': 500}, older), ({'source_timestamp': 600}, newer)]
        found = px4_reference_timestamps(feedback, 700, 2000, (2.0, 1.0, -3.0), (0.25, 0.5, 0.25))
        self.assertEqual(found, {2000})

    def test_reference_ambiguous_when_timestamps_differ(self):
        a = NS(timestamp=2000, timestamp_sample=5000, x=1.0, y=2.0, z=3.0, vx=0.5, vy=0.25, vz=-0.25)
        b = NS(timestamp=3000, timestamp_sample=5000, x=1.0, y=2.0, z=3.0, vx=0.5, vy=0.25, vz=-0.25)
        feedback = [({'source_timestamp': 500}, a), ({'source_timestamp': 600}, b)]
        found = px4_reference_timestamps(feedback, 700, 5000, (2.0, 1.0, -3.0), (0.25, 0.5, 0.25))
        self.assertEqual(found, {2000, 3000})

    def test_reference_requires_strictly_earlier_producer_stamp(self):
        lp = NS(timestamp=2000, timestamp_sample=0, x=1.0, y=2.0, z=3.0, vx=0.5, vy=0.25, vz=-0.25)
        feedback = [({'source_timestamp': 700}, lp)]  # not strictly before the target stamp
        self.assertEqual(px4_reference_timestamps(
            feedback, 700, 2000, (2.0, 1.0, -3.0), (0.25, 0.5, 0.25)), set())


@unittest.skipUnless(ROS, 'requires the ROS message overlays (WSL)')
class Px4Cdr(unittest.TestCase):
    def cdr(self, msg):
        return deserialize_message(serialize_message(msg), msg.__class__)

    def lp(self, timestamp, sample, ned_pos, ned_vel, source_ns):
        msg = VehicleLocalPosition()
        msg.timestamp = timestamp
        msg.timestamp_sample = sample
        msg.x, msg.y, msg.z = (float(v) for v in ned_pos)
        msg.vx, msg.vy, msg.vz = (float(v) for v in ned_vel)
        return {'topic': LP_TOPIC, 'source_timestamp': source_ns, 'publisher_gid': '01'}, self.cdr(msg)

    def state(self, lp_msg, rid, sequence, source_ns):
        uav = UAVState()
        sec, rem = divmod(lp_msg.timestamp_sample or lp_msg.timestamp, 1_000_000)
        uav.header.stamp.sec = sec
        uav.header.stamp.nanosec = rem * 1000
        uav.position = [lp_msg.y, lp_msg.x, -lp_msg.z]
        uav.velocity = [lp_msg.vy, lp_msg.vx, -lp_msg.vz]
        ss = SessionState(version=1, run_id=RUN, control_epoch=EPOCH, sequence=sequence,
                          last_request_id=rid, native_generation=1, source_clock='fc_boot',
                          source_received_valid=True, source_received_monotonic_s=1.0,
                          published_monotonic_s=2.0, state=uav, control=UAVControlState())
        return {'topic': PX4_STATE_TOPIC, 'source_timestamp': source_ns, 'publisher_gid': '01'}, self.cdr(ss)

    def setpoint(self, window, timestamp, source_ns):
        msg = TrajectorySetpoint()
        msg.timestamp = timestamp
        if window == 'move':
            msg.position, msg.acceleration, msg.jerk = [math.nan] * 3, [math.nan] * 3, [math.nan] * 3
            msg.velocity = [0.0, 0.1, 0.0]
            msg.yaw, msg.yawspeed = math.nan, 0.0
        else:
            msg.position = [2.0, 1.0, -3.0]
            msg.velocity, msg.acceleration, msg.jerk = [math.nan] * 3, [math.nan] * 3, [math.nan] * 3
            msg.yaw, msg.yawspeed = 0.5, math.nan
        return {'topic': SETPOINT_TOPIC, 'source_timestamp': source_ns, 'publisher_gid': '01'}, self.cdr(msg)

    def run_check(self, window, sp, st, feedback):
        failures, unresolved = [], []
        ok = check_px4(window, sp[0], sp[1], st[0], st[1], feedback, failures, unresolved)
        return ok, failures, unresolved

    def test_distinct_payload_and_header_clocks_pass(self):
        # timestamp (payload) != timestamp_sample (state header); both resolve to one sample.
        lp = self.lp(2000, 1500, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        st = self.state(lp[1], rid=7, sequence=3, source_ns=900)
        sp = self.setpoint('move', 2000, 700)
        ok, failures, unresolved = self.run_check('move', sp, st, [lp])
        self.assertTrue(ok)
        self.assertEqual((failures, unresolved), ([], []))
        self.assertEqual(header_us(st[1].state.header.stamp), 1500)  # header used the sample clock

    def test_newer_unconsumed_feedback_does_not_corrupt(self):
        older = self.lp(2000, 0, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        newer = self.lp(3000, 0, (9, 9, 9), (9, 9, 9), 600)  # produced but not consumed this tick
        st = self.state(older[1], rid=7, sequence=3, source_ns=900)
        sp = self.setpoint('move', 2000, 700)
        ok, failures, unresolved = self.run_check('move', sp, st, [older, newer])
        self.assertTrue(ok)
        self.assertEqual((failures, unresolved), ([], []))

    def test_ambiguous_reference_is_unresolved_not_guessed(self):
        a = self.lp(2000, 5000, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        b = self.lp(3000, 5000, (1, 2, 3), (0.5, 0.25, -0.25), 600)  # same header+pos+vel, other timestamp
        st = self.state(a[1], rid=7, sequence=3, source_ns=900)
        sp = self.setpoint('move', 2000, 700)
        ok, failures, unresolved = self.run_check('move', sp, st, [a, b])
        self.assertFalse(ok)
        self.assertEqual(failures, [])
        self.assertEqual([u['what'] for u in unresolved], ['reference'])
        self.assertIn('ambiguous', unresolved[0]['reason'])

    def test_payload_timestamp_mismatch_fails(self):
        lp = self.lp(2000, 0, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        st = self.state(lp[1], rid=7, sequence=3, source_ns=900)
        sp = self.setpoint('move', 9999, 700)  # payload timestamp is not the reference sample's
        ok, failures, unresolved = self.run_check('move', sp, st, [lp])
        self.assertFalse(ok)
        self.assertEqual([f['code'] for f in failures], ['payload_timestamp_differs'])
        self.assertEqual((failures[0]['expected'], failures[0]['actual']), (2000, 9999))

    def test_missing_reference_is_unresolved(self):
        lp = self.lp(2000, 0, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        st = self.state(lp[1], rid=7, sequence=3, source_ns=900)
        sp = self.setpoint('move', 2000, 700)
        ok, failures, unresolved = self.run_check('move', sp, st, [])  # no feedback retained
        self.assertFalse(ok)
        self.assertEqual(failures, [])
        self.assertEqual([u['what'] for u in unresolved], ['reference'])

    def test_hold_window_passes(self):
        lp = self.lp(2000, 0, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        st = self.state(lp[1], rid=8, sequence=4, source_ns=900)
        sp = self.setpoint('hold', 2000, 700)
        ok, failures, unresolved = self.run_check('hold', sp, st, [lp])
        self.assertTrue(ok)
        self.assertEqual((failures, unresolved), ([], []))

    def test_window_shape_mismatch_fails(self):
        lp = self.lp(2000, 0, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        st = self.state(lp[1], rid=8, sequence=4, source_ns=900)
        sp = self.setpoint('move', 2000, 700)  # velocity-shaped sample inside a HOLD window
        ok, failures, unresolved = self.run_check('hold', sp, st, [lp])
        self.assertFalse(ok)
        self.assertEqual([f['code'] for f in failures], ['window_shape_differs'])

    def test_payload_timestamp_out_of_range_fails(self):
        lp = self.lp(2000, 0, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        st = self.state(lp[1], rid=7, sequence=3, source_ns=900)
        sp = self.setpoint('move', 0, 700)  # rejected by native_px4.timestamp() range guard
        ok, failures, unresolved = self.run_check('move', sp, st, [lp])
        self.assertFalse(ok)
        self.assertEqual([f['code'] for f in failures], ['payload_timestamp_out_of_range'])

    def test_state_header_not_stamp_us_product_fails(self):
        lp = self.lp(2000, 0, (1, 2, 3), (0.5, 0.25, -0.25), 500)
        st = self.state(lp[1], rid=7, sequence=3, source_ns=900)
        st[1].state.header.stamp.nanosec = 1  # not a whole-microsecond stamp_us product
        sp = self.setpoint('move', 2000, 700)
        ok, failures, unresolved = self.run_check('move', sp, st, [lp])
        self.assertFalse(ok)
        self.assertEqual([f['code'] for f in failures], ['state_header_not_stamp_us_product'])


@unittest.skipUnless(ROS, 'requires the ROS message overlays (WSL)')
class ApCdr(unittest.TestCase):
    def cdr(self, msg):
        return deserialize_message(serialize_message(msg), msg.__class__)

    def cmd(self, topic, stamp_us, source_ns, frame_id='map'):
        msg = TwistStamped() if topic == CMD_VEL else GlobalPosition()
        msg.header.frame_id = frame_id
        sec, rem = divmod(stamp_us, 1_000_000)
        msg.header.stamp.sec = sec
        msg.header.stamp.nanosec = rem * 1000
        if topic == CMD_VEL:
            msg.twist = Twist(linear=Vector3(x=0.1, y=0.0, z=0.0),
                              angular=Vector3(x=0.0, y=0.0, z=0.0))
        return {'topic': topic, 'source_timestamp': source_ns, 'publisher_gid': '01'}, self.cdr(msg)

    def state(self, stamp_us, rid, sequence, source_ns):
        uav = UAVState()
        sec, rem = divmod(stamp_us, 1_000_000)
        uav.header.stamp.sec = sec
        uav.header.stamp.nanosec = rem * 1000
        ss = SessionState(version=1, run_id=RUN, control_epoch=EPOCH, sequence=sequence,
                          last_request_id=rid, native_generation=1, source_clock='fc_boot',
                          source_received_valid=True, source_received_monotonic_s=1.0,
                          published_monotonic_s=2.0, state=uav, control=UAVControlState())
        return {'topic': AP_STATE_TOPIC, 'source_timestamp': source_ns, 'publisher_gid': '01'}, self.cdr(ss)

    def run_check(self, window, cmd, st):
        failures, unresolved = [], []
        ok = check_ap(window, cmd[0], cmd[1], st[0], st[1], failures, unresolved)
        return ok, failures, unresolved

    def test_cmd_vel_header_equals_following_state(self):
        cmd = self.cmd(CMD_VEL, 1_250_000, 700)
        st = self.state(1_250_000, rid=7, sequence=3, source_ns=900)
        ok, failures, unresolved = self.run_check('move', cmd, st)
        self.assertTrue(ok)
        self.assertEqual((failures, unresolved), ([], []))

    def test_matching_zero_headers_are_not_valid_boot_time(self):
        cmd = self.cmd(CMD_VEL,0,700)
        st = self.state(0,rid=7,sequence=3,source_ns=900)
        ok,failures,unresolved = self.run_check('move',cmd,st)
        self.assertFalse(ok)
        self.assertEqual(failures[0]['code'],'cmd_header_not_valid_boot_microseconds')

    def test_cmd_gps_pose_header_equals_following_state(self):
        cmd = self.cmd(CMD_GPS, 1_250_000, 700)
        st = self.state(1_250_000, rid=8, sequence=4, source_ns=900)
        ok, failures, unresolved = self.run_check('hold', cmd, st)
        self.assertTrue(ok)
        self.assertEqual((failures, unresolved), ([], []))

    def test_header_mismatch_is_a_failure_not_excused(self):
        # A newer WksimState stamp on the cmd than on the following state is a real
        # mismatch: the single-threaded tick cannot have run a callback mid-tick.
        cmd = self.cmd(CMD_VEL, 1_250_000, 700)
        st = self.state(1_000_000, rid=7, sequence=3, source_ns=900)
        ok, failures, unresolved = self.run_check('move', cmd, st)
        self.assertFalse(ok)
        self.assertEqual([f['code'] for f in failures], ['cmd_header_differs_from_following_state'])
        self.assertEqual(unresolved, [])

    def test_window_topic_mismatch_fails(self):
        cmd = self.cmd(CMD_GPS, 1_250_000, 700)  # gps_pose sample inside a velocity window
        st = self.state(1_250_000, rid=7, sequence=3, source_ns=900)
        ok, failures, unresolved = self.run_check('move', cmd, st)
        self.assertFalse(ok)
        self.assertEqual([f['code'] for f in failures], ['window_topic_differs'])

    def test_frame_id_mismatch_fails(self):
        cmd = self.cmd(CMD_VEL, 1_250_000, 700, frame_id='odom')
        st = self.state(1_250_000, rid=7, sequence=3, source_ns=900)
        ok, failures, unresolved = self.run_check('move', cmd, st)
        self.assertFalse(ok)
        self.assertEqual([f['code'] for f in failures], ['cmd_frame_differs'])


if __name__ == '__main__':
    unittest.main()
