# SPDX-License-Identifier: Apache-2.0
"""Native home/origin observations and a leased, explicitly bound global stream.

This opt-in boundary owns neither arming nor mode changes. The ControlNode
retains those gates and revokes control if an active global target expires.
"""
from dataclasses import asdict
import hashlib
import json
import math
from types import SimpleNamespace

from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data
from rosidl_runtime_py.convert import message_to_ordereddict
from prometheus_msgs.msg import UAVControlState as Control

from Simulator.wksim_control.global_reference import (SCHEMA, Identity, HomeSnapshot,
    OriginSnapshot, GlobalCommand, resolve, validate_current, validate_observations, require, number)
from Simulator.wksim_control.global_profile import load_proof
from .frames import topic


class GlobalNative:
    def __init__(self, node, stack, profile):
        self.node, self.stack, self.profile = node, stack, profile
        self.proof = load_proof(profile, stack, node.session.run_id)
        self.samples, self.gids = {}, {}
        self.error = None
        self.home_token = self.origin_token = None
        self.home_generation = self.origin_generation = 0
        self.target = None
        self.yaw = None
        self.last_command_id = 0
        self.last_reference = -math.inf
        self.subscriptions = []
        import rclpy
        from .rc_transport import RCTake
        self.receiver = rclpy.create_node('wksim_global_native_receiver', namespace=f'/uav{node.uav_id}')
        self.take = RCTake()
        if stack == 'px4':
            from px4_msgs.msg import HomePosition, VehicleGlobalPosition, VehicleLocalPosition
            topics = [(key, cls, topic(node.native.prefix, 'out', name, cls)) for key, cls, name in (
                ('home', HomePosition, 'home_position'),
                ('global', VehicleGlobalPosition, 'vehicle_global_position'),
                ('local', VehicleLocalPosition, 'vehicle_local_position'))]
        else:
            from ardupilot_msgs.msg import WksimState
            topics = [('local', WksimState, node.native.prefix+'/wksim/local_state_v1')]
        self.keys = [key for key, _, _ in topics]
        for key, cls, name in topics:
            # Humble drops MessageInfo in Python callbacks. Use the already
            # verified serialized RMW take on an unspun receiver, retaining GID.
            self.subscriptions.append(self.receiver.create_subscription(cls, name, lambda _: None, qos_profile_sensor_data))
        root = f'/uav{node.uav_id}/prometheus/v2'
        self.reference_pub = node.create_publisher(String, root+'/global_reference', 1)
        self.command_sub = node.create_subscription(String, root+'/global_command', self.on_command, 1)

    def clear(self):
        self.target = self.yaw = None

    def poll(self):
        for key, subscription in zip(self.keys, self.subscriptions):
            for _ in range(100):
                sample = self.take.take(subscription)
                if sample is None: break
                self.receive(key, *sample)

    def close(self):
        self.receiver.destroy_node()

    def receive(self, key, msg, info):
        now = self.node.wall()
        stamp = int(msg.time_boot_us if self.stack == 'arducopter' else msg.timestamp)
        gid = bytes(info.publisher_gid).hex()
        previous = self.samples.get(key)
        received = now
        try:
            require(bool(gid) and any(bytes(info.publisher_gid)), 'native_gid_missing')
            require(self.error is None, self.error or 'global_session_invalid')
            require(key not in self.gids or self.gids[key] == gid, 'native_publisher_changed')
            require(math.isfinite(now) and stamp > 0, 'native_time_invalid')
            if previous is not None:
                require(now >= previous[2], 'clock_regressed')
                require(stamp >= previous[1], 'source_clock_regressed')
                if stamp == previous[1]:
                    # Repeated samples never renew the two-second lease.
                    # Compare typed fields rather than serialization padding;
                    # canonical NaNs in unrelated native fields compare equal.
                    if json.dumps(message_to_ordereddict(msg), sort_keys=True) == json.dumps(
                            message_to_ordereddict(previous[0]), sort_keys=True):
                        return
                    # The owner can update home multiple times inside one 4ms
                    # native tick. Its uint32 counter supplies a new identity,
                    # but the old receipt time remains the freshness boundary.
                    require(self.stack == 'px4' and key == 'home'
                            and msg.update_count != previous[0].update_count, 'duplicate_source_changed')
                    received = previous[2]
            self.gids[key] = gid
            self.samples[key] = (msg, stamp, received)
            self.track_generations()
            self.node.event('global_native_observation', source=key, source_timestamp=stamp,
                received_monotonic=received, taken_monotonic=now, publisher_gid=gid,
                cdr_hex=getattr(info, 'cdr_hex', None))
        except ValueError as error:
            self.error = str(error)
            self.node.event('global_native_rejected', error=True, source=key, reason=self.error)
            if self.target is not None:
                self.node.revoke(self.error)

    def track_generations(self):
        """Observe every native change, including changes reverted between sends."""
        if self.stack == 'px4':
            home = self.samples.get('home')
            htoken = None if home is None else tuple(getattr(home[0], key) for key in (
                'valid_hpos', 'valid_alt', 'valid_lpos', 'lat', 'lon', 'alt', 'update_count', 'manual_home'))
            local, glob = self.samples.get('local'), self.samples.get('global')
            otoken = None if local is None or glob is None else (
                local[0].ref_timestamp, local[0].ref_lat, local[0].ref_lon, local[0].ref_alt,
                local[0].xy_reset_counter, local[0].z_reset_counter, local[0].heading_reset_counter,
                glob[0].lat_lon_reset_counter, glob[0].alt_reset_counter)
        else:
            local = self.samples['local'][0]
            htoken = (local.home_valid, local.home_latitude_e7, local.home_longitude_e7, local.home_altitude_cm)
            otoken = (local.yaw_reset_ms, local.position_ne_reset_ms, local.position_down_reset_ms)
        changed = []
        for name, token in (('home', htoken), ('origin', otoken)):
            if token is not None and token != getattr(self, name+'_token'):
                setattr(self, name+'_token', token)
                setattr(self, name+'_generation', getattr(self, name+'_generation')+1)
                changed.append(name)
        if changed and self.target is not None:
            self.node.revoke('global_'+'_and_'.join(changed)+'_changed')

    def snapshots(self):
        require(self.error is None, self.error or 'global_session_invalid')
        now = self.node.wall()
        keys = ('home', 'global', 'local') if self.stack == 'px4' else ('local',)
        for key in keys:
            require(key in self.samples and 0 <= now-self.samples[key][2] <= 2., 'snapshot_stale')
        # MessageInfo binds the samples, graph inspection rejects competing writers.
        for key, sub in zip(keys, self.subscriptions):
            writers = self.node.get_publishers_info_by_topic(sub.topic_name)
            require(len(writers) == 1 and bytes(writers[0].endpoint_gid).hex() == self.gids[key],
                    'native_writer_ambiguous')
        local, stamp, received = self.samples['local']
        binding = hashlib.sha256(json.dumps(self.gids, sort_keys=True).encode()).hexdigest()
        identity = Identity(self.stack, self.node.session.run_id, f'uav{self.node.uav_id}',
            self.node.uav_id, int(self.node.session.epoch, 16), binding, binding,
            self.proof['scene_origin']['id'])
        datum = self.profile['proof_sha256']
        if self.stack == 'px4':
            home, home_stamp, home_received = self.samples['home']
            glob, _, _ = self.samples['global']
            htoken = (home.valid_hpos, home.valid_alt, home.valid_lpos, home.lat, home.lon,
                      home.alt, home.update_count, home.manual_home)
            otoken = (local.ref_timestamp, local.ref_lat, local.ref_lon, local.ref_alt,
                local.xy_reset_counter, local.z_reset_counter, local.heading_reset_counter,
                glob.lat_lon_reset_counter, glob.alt_reset_counter)
            nav = bool(self.node.native.navigation_valid and local.xy_global and local.z_global
                and glob.lat_lon_valid and glob.alt_valid and not glob.dead_reckoning)
            hfields = (home.lat, home.lon, float(home.alt), datum, bool(home.valid_hpos),
                       bool(home.valid_alt), bool(home.valid_lpos), int(home.update_count), bool(home.manual_home), None)
            ofields = (int(local.ref_timestamp), local.ref_lat, local.ref_lon, float(local.ref_alt),
                       (int(glob.lat_lon_reset_counter), int(glob.alt_reset_counter)),
                       (int(local.xy_reset_counter), int(local.z_reset_counter), int(local.heading_reset_counter)))
        else:
            raw = (int(local.home_latitude_e7), int(local.home_longitude_e7), int(local.home_altitude_cm))
            htoken = (local.home_valid, *raw)
            otoken = (local.yaw_reset_ms, local.position_ne_reset_ms, local.position_down_reset_ms)
            home_stamp, home_received = stamp, received
            nav = bool(self.node.native.navigation_valid)
            hfields = (raw[0]/1e7, raw[1]/1e7, raw[2]/100, datum,
                       bool(local.home_valid), bool(local.home_valid), bool(local.position_valid), None, None, raw)
            # AP exposes home-relative local state, not its internal EKF origin.
            # The separately named scene origin is only the truth/datum reference;
            # native global commands remain latitude/longitude/relative altitude.
            origin = self.proof['scene_origin']
            ofields = (1, origin['latitude_deg'], origin['longitude_deg'], origin['alt_amsl_m'],
                       (0,), tuple(int(v) for v in otoken))
        home = HomeSnapshot(SCHEMA, identity, home_stamp, home_received, self.home_generation, *hfields)
        origin = OriginSnapshot(identity, ('px4-ekf' if self.stack == 'px4' else 'ap-scene-reference'),
            self.origin_generation, *ofields, stamp, received, nav, datum)
        validate_observations(home, origin, now=now)
        return home, origin

    def observe(self):
        now = self.node.wall()
        if now-self.last_reference < .2:
            return
        self.last_reference = now
        try:
            home, origin = self.snapshots()
            value = dict(schema=SCHEMA, ready=True, control_epoch=self.node.session.epoch,
                home=asdict(home), origin=asdict(origin), observed_monotonic=now)
        except ValueError as error:
            value = dict(schema=SCHEMA, ready=False, reason=str(error))
        self.reference_pub.publish(String(data=json.dumps(value, allow_nan=False)))

    def running(self):
        node = self.node
        require(not node.revoked and node.operation is None
                and node.processor.control_state == Control.COMMAND_CONTROL
                and node.state.armed and node.state.odom_valid and node.native.ready_external
                and node.state.mode == node.native.external_mode, 'global_control_not_active')
        require(node.scene_hold is None and node.scene_recovery is None, 'paused')
        if node.scene is not None:
            require(node.scene.check()['phase'] == 'running', 'paused')

    def on_command(self, msg):
        node = self.node
        try:
            value = json.loads(msg.data)
            require(type(value) is dict and set(value) == {'version', 'run_id', 'control_epoch',
                    'request_id', 'command', 'yaw_enu_rad'}, 'global_request_fields')
            node.request_context = node.session.accept(SimpleNamespace(**value))
            self.running()
            command = dict(value['command'])
            command['identity'] = Identity(**command['identity'])
            command = GlobalCommand(**command)
            yaw = number(value['yaw_enu_rad'])
            home, origin = self.snapshots()
            target = resolve(command, now=node.wall(), home=home, origin=origin,
                last_command_id=self.last_command_id)
            self.target, self.yaw = target, yaw
            self.last_command_id = command.command_id
            node.command_request_id = node.request_context
            node.event('global_command_accepted', raw=msg.data, resolved=asdict(target), yaw_enu_rad=yaw)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            node.event('global_command_rejected', error=True, reason=str(error), raw=msg.data)
        finally:
            node.request_context = 0

    def publish(self):
        self.running()
        home, origin = self.snapshots()
        target = validate_current(self.target, now=self.node.wall(), home=home, origin=origin)
        self.node.native.send_global(target, self.yaw)
        self.target = target
        self.node.event('global_native_published', resolved=asdict(target), yaw_enu_rad=self.yaw)
