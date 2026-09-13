"""Real generated native messages exercise global identity and publish gates.

These are transport-boundary regressions, not flight/datum acceptance evidence.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import json
import math
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from px4_msgs.msg import HomePosition, VehicleGlobalPosition, VehicleLocalPosition
from ardupilot_msgs.msg import WksimState
from std_msgs.msg import String
from prometheus_msgs.msg import UAVControlState as Control
from prometheus_control.global_native import GlobalNative
from prometheus_control.native_px4 import PX4Link
from prometheus_control.native_arducopter import ArduCopterLink
from Simulator.wksim_control.global_reference import GlobalCommand, SCHEMA, resolve


class GlobalNativeTests(unittest.TestCase):
    def fixture(self, stack='px4'):
        now = [10.]
        gid = bytes(range(24))
        native = NS(prefix='/native', navigation_valid=True, ready_external=True,
                    external_mode='OFFBOARD' if stack == 'px4' else 'GUIDED', send_global=Mock())
        session = NS(run_id='run', epoch='a'*32, accept=lambda v: v.request_id)
        node = NS(session=session, native=native, uav_id=1, wall=lambda: now[0], event=Mock(),
            create_subscription=lambda cls, name, cb, qos: NS(topic_name=name, callback=cb),
            create_publisher=lambda *args: NS(publish=Mock()),
            get_publishers_info_by_topic=lambda _: [NS(endpoint_gid=gid)],
            processor=NS(control_state=Control.COMMAND_CONTROL), revoked=False, operation=None,
            state=NS(armed=True, odom_valid=True, mode=native.external_mode),
            scene_hold=None, scene_recovery=None, scene=None, command_request_id=0)
        proof = dict(scene_origin=dict(id='scene', latitude_deg=0., longitude_deg=0., alt_amsl_m=100.))
        with patch('prometheus_control.global_native.load_proof', return_value=proof), \
                patch('rclpy.create_node', return_value=node), patch('prometheus_control.rc_transport.RCTake'):
            boundary = GlobalNative(node, stack, dict(proof_sha256='d'*64))
        def revoke(reason):
            node.revoked = True
            boundary.clear()
        node.revoke = Mock(side_effect=revoke)
        info = NS(publisher_gid=gid)
        if stack == 'px4':
            home = HomePosition(timestamp=100, lat=0., lon=0., alt=123., valid_hpos=True,
                                valid_alt=True, valid_lpos=True, update_count=1)
            local = VehicleLocalPosition(timestamp=100, ref_timestamp=90, ref_lat=0., ref_lon=0.,
                                         ref_alt=118., xy_global=True, z_global=True)
            glob = VehicleGlobalPosition(timestamp=100, lat_lon_valid=True, alt_valid=True)
            messages = dict(home=home, global_=glob, local=local)
            messages['global'] = messages.pop('global_')
        else:
            local = WksimState(time_boot_us=100, home_valid=True, home_latitude_e7=0,
                home_longitude_e7=0, home_altitude_cm=12300, position_valid=True)
            messages = dict(local=local)
        for key, msg in messages.items():
            boundary.receive(key, msg, info)
        return boundary, node, now, messages, info

    def accept(self, b, command_id=1, **fields):
        home, origin = b.snapshots()
        command = GlobalCommand(SCHEMA, 0., 0., 3., 'home_relative', home.identity,
            home.home_generation, origin.origin_id, origin.local_origin_generation,
            command_id, b.node.wall(), b.node.wall()+2.)
        command = replace(command, **fields)
        envelope = dict(version=1, run_id='run', control_epoch=b.node.session.epoch,
            request_id=command_id, command=asdict(command), yaw_enu_rad=.25)
        b.on_command(String(data=json.dumps(envelope)))
        return command

    def test_each_stack_binds_native_home_and_keeps_distinct_origin(self):
        for stack in ('px4', 'arducopter'):
            b, n, now, messages, info = self.fixture(stack)
            self.accept(b)
            self.assertIsNotNone(b.target)
            b.publish()
            target, yaw = n.native.send_global.call_args.args
            self.assertEqual(target.native_target, (0., 0., -8.) if stack == 'px4' else (0, 0, 300))
            self.assertEqual(target.home.alt_amsl_m, 123.)
            self.assertNotEqual(target.origin.alt_amsl_m, target.home.alt_amsl_m)
            self.assertEqual(yaw, .25)

    def test_duplicate_sample_does_not_renew_home_lease(self):
        b, n, now, messages, info = self.fixture()
        now[0] = 11.9
        b.receive('home', messages['home'], info)
        self.assertEqual(b.samples['home'][2], 10.)
        now[0] = 12.01
        with self.assertRaisesRegex(ValueError, 'snapshot_stale'):
            b.snapshots()

    def test_home_change_and_revert_cannot_reanimate_target(self):
        for stack in ('px4', 'arducopter'):
            b, n, now, messages, info = self.fixture(stack)
            self.accept(b)
            key = 'home' if stack == 'px4' else 'local'
            msg = deepcopy(messages[key])
            if stack == 'px4':
                msg.timestamp = 101; msg.update_count = 2
            else:
                msg.time_boot_us = 101; msg.home_altitude_cm += 1
            b.receive(key, msg, info)
            self.assertIsNone(b.target)
            self.assertTrue(n.revoked)
            if stack == 'px4':
                msg.timestamp = 102; msg.update_count = 1
            else:
                msg.time_boot_us = 102; msg.home_altitude_cm -= 1
            b.receive(key, msg, info)
            self.assertEqual(b.home_generation, 3)
            n.native.send_global.assert_not_called()

    def test_publisher_or_clock_change_latches_session_failure(self):
        for failure in ('gid', 'source', 'clock', 'duplicate_changed'):
            b, n, now, messages, info = self.fixture()
            self.accept(b)
            msg = deepcopy(messages['home'])
            if failure == 'gid': info = NS(publisher_gid=bytes(reversed(range(24))))
            if failure == 'source': msg.timestamp = 99
            if failure == 'clock': now[0] = 9.
            if failure == 'duplicate_changed': msg.alt += 1
            b.receive('home', msg, info)
            self.assertIsNotNone(b.error)
            self.assertIsNone(b.target)
            n.native.send_global.assert_not_called()

    def test_expired_command_does_not_publish_with_fresh_native_samples(self):
        b, n, now, messages, info = self.fixture()
        self.accept(b)
        now[0] = 12.01
        for key, msg in messages.items():
            fresh = deepcopy(msg); fresh.timestamp = 200
            b.receive(key, fresh, info)
        with self.assertRaisesRegex(ValueError, 'command_expired'):
            b.publish()
        n.native.send_global.assert_not_called()

    def test_competing_writer_and_pause_block_all_global_output(self):
        for failure in ('writers', 'pause', 'disarm', 'mode', 'invalid_position'):
            b, n, now, messages, info = self.fixture()
            self.accept(b)
            if failure == 'writers': n.get_publishers_info_by_topic = lambda _: []
            if failure == 'pause': n.scene_hold = {}
            if failure == 'disarm': n.state.armed = False
            if failure == 'mode': n.state.mode = 'AUTO.LAND'
            if failure == 'invalid_position': n.state.odom_valid = False
            with self.assertRaises(ValueError): b.publish()
            n.native.send_global.assert_not_called()

    def test_outside_fence_and_unbound_identity_publish_nothing(self):
        for fields in (dict(latitude_deg=.1), dict(home_generation=77),
                       dict(height_reference='ellipsoid'), dict(height_m=True)):
            b, n, now, messages, info = self.fixture()
            self.accept(b, **fields)
            self.assertIsNone(b.target)
            n.native.send_global.assert_not_called()
            self.assertEqual(n.event.call_args.args[0], 'global_command_rejected')

    def test_global_reset_and_local_origin_changes_revoke_immediately(self):
        for key, field in (('global', 'alt_reset_counter'), ('global', 'lat_lon_reset_counter'),
                           ('local', 'ref_timestamp'), ('local', 'xy_reset_counter')):
            b, n, now, messages, info = self.fixture()
            self.accept(b)
            msg = deepcopy(messages[key]); msg.timestamp = 101
            setattr(msg, field, getattr(msg, field)+1)
            b.receive(key, msg, info)
            self.assertIsNone(b.target)
            n.revoke.assert_called_once()

    def test_native_uint32_home_counter_and_unrelated_nan_fields(self):
        b, n, now, messages, info = self.fixture()
        home = deepcopy(messages['home']); home.timestamp = 101; home.update_count = 4294967295
        b.receive('home', home, info)
        local = deepcopy(messages['local']); local.timestamp = 101; local.vxy_max = math.nan
        b.receive('local', local, info)
        self.accept(b)
        self.assertIsNotNone(b.target)
        self.assertIsNone(b.error)
        b.receive('local', deepcopy(local), info)
        self.assertIsNone(b.error)
        home.timestamp = 102; home.update_count = 0
        b.receive('home', home, info)
        self.assertIsNone(b.target)
        n.revoke.assert_called_once()

    def test_invalid_projection_origin_is_not_advertised_as_ready(self):
        b, n, now, messages, info = self.fixture()
        local = deepcopy(messages['local']); local.timestamp = 101; local.ref_lat = math.nan
        b.receive('local', local, info)
        b.observe()
        advertised = json.loads(b.reference_pub.publish.call_args.args[0].data)
        self.assertFalse(advertised['ready'])
        self.assertIsNone(b.error)  # Normal startup absence does not poison later valid samples.

    def test_same_tick_authoritative_home_update_revokes_without_renewing_lease(self):
        b, n, now, messages, info = self.fixture()
        self.accept(b)
        now[0] = 11.
        home = deepcopy(messages['home']); home.update_count += 1; home.alt += .1
        b.receive('home', home, info)
        self.assertIsNone(b.error)
        self.assertIsNone(b.target)
        n.revoke.assert_called_once()
        self.assertEqual(b.samples['home'][2], 10.)
        self.assertEqual(b.home_generation, 2)
        now[0] = 12.01
        with self.assertRaisesRegex(ValueError, 'snapshot_stale'): b.snapshots()

    def test_real_native_message_output_has_correct_axes_datums_and_mask(self):
        for stack in ('px4', 'arducopter'):
            b, n, now, messages, info = self.fixture(stack)
            self.accept(b)
            if stack == 'px4':
                link = NS(timestamp=lambda: 100,
                    publishers={key: NS(publish=Mock()) for key in ('offboard', 'position')})
                PX4Link.send_global(link, b.target, .25)
                msg = link.publishers['position'].publish.call_args.args[0]
                self.assertEqual(list(msg.position), [0., 0., -8.])
                self.assertTrue(all(math.isnan(x) for x in msg.velocity))
                self.assertAlmostEqual(msg.yaw, math.pi/2-.25, places=6)
            else:
                link = NS(position_yaw=True, navigation_valid=True, fresh=lambda _: True,
                    latest={'local': messages['local']}, position_pub=NS(publish=Mock()))
                ArduCopterLink.send_global(link, b.target, .25)
                msg = link.position_pub.publish.call_args.args[0]
                self.assertEqual(msg.type_mask, 0x9F8)
                self.assertEqual(msg.coordinate_frame, msg.FRAME_GLOBAL_REL_ALT)
                self.assertEqual(msg.altitude, 3.)
                self.assertEqual(msg.header.frame_id, 'map')

    def test_live_humble_take_retains_real_publisher_gid(self):
        import os
        import time
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        self.assertNotEqual(os.readlink('/proc/self/ns/net'), os.readlink('/proc/1/ns/net'))
        rclpy.init()
        node = rclpy.create_node('global_native_transport_regression')
        boundary = None
        try:
            node.session = NS(run_id='live', epoch='b'*32)
            node.native = NS(prefix='/global_test', navigation_valid=True)
            node.uav_id, node.wall, node.event = 1, time.monotonic, Mock()
            node.revoke = Mock()
            proof = dict(scene_origin=dict(id='scene', latitude_deg=0., longitude_deg=0., alt_amsl_m=100.))
            with patch('prometheus_control.global_native.load_proof', return_value=proof):
                boundary = GlobalNative(node, 'arducopter', dict(proof_sha256='d'*64))
            publisher = node.create_publisher(WksimState, '/global_test/wksim/local_state_v1', qos_profile_sensor_data)
            deadline = time.monotonic()+5
            while publisher.get_subscription_count() != 1 and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=.02)
            self.assertEqual(publisher.get_subscription_count(), 1)
            publisher.publish(WksimState(time_boot_us=100, home_valid=True,
                home_altitude_cm=12300, position_valid=True))
            while not boundary.samples and time.monotonic() < deadline:
                boundary.poll()
                time.sleep(.01)
            home, origin = boundary.snapshots()
            self.assertEqual(home.alt_amsl_m, 123.)
            writer = node.get_publishers_info_by_topic('/global_test/wksim/local_state_v1')[0]
            self.assertEqual(boundary.gids['local'], bytes(writer.endpoint_gid).hex())
            observation = next(call.kwargs for call in node.event.call_args_list
                               if call.args[0] == 'global_native_observation')
            self.assertTrue(observation['cdr_hex'])
        finally:
            if boundary is not None: boundary.close()
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
