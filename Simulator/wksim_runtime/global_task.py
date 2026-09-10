"""Leased native global flight, with independently recorded physical feedback."""
from copy import deepcopy
import json
import math
from pathlib import Path
import time
import uuid

from std_msgs.msg import String
from rclpy.qos import QoSProfile, ReliabilityPolicy
from .rc_task import RCTask
from .efficiency_task import EfficiencyTask
from .task import Task, grounded
from Simulator.wksim_control.global_reference import reproject, project, AP_SCALE


class GlobalTask(RCTask):
    truth_rows = EfficiencyTask.truth_rows

    def __init__(self, directory, health, phase, flight_stack, *, scene_epoch, **kwargs):
        self.directory, self.scene_epoch = Path(directory), scene_epoch
        self.profile = json.loads((self.directory/'global-profile.json').read_text())
        self.proof = json.loads((self.directory/'datum-proof.json').read_text())
        self.reference = None
        self.binding = self.route = None
        self.last_global = -math.inf
        self.global_id = 0
        self._truth_stream, self._truth_cache = None, []
        self.home_actor = None
        super().__init__(directory, health, phase, flight_stack, scenario='movement',
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-', ''),
            stream_id=uuid.uuid4().hex, truth_path=directory/'truth.jsonl', **kwargs)
        root = self.topic_root+'v2/'
        self.global_pub = self.node.create_publisher(String, root+'global_command', 1)
        self.subscriptions.append(self.node.create_subscription(String, root+'global_reference', self.on_reference, 1))
        channels = [(root+'global_command', String), (root+'global_reference', String),
                    (root+'command', self.CommandRequest)]
        if flight_stack == 'px4':
            from px4_msgs.msg import HomePosition, VehicleGlobalPosition
            from prometheus_control.frames import topic
            channels += [(topic('/wksim_px4_21', 'out', name, cls), cls) for name, cls in (
                ('home_position', HomePosition), ('vehicle_global_position', VehicleGlobalPosition))]
        qos = QoSProfile(depth=500, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.raw_subs += [self.raw_node.create_subscription(cls, name, lambda _: None, qos) for name, cls in channels]
        if 'home_change' in self.profile:
            from .home_mutation import HomeMutation
            self.home_actor = HomeMutation(flight_stack, self.directory, self.run_id)

    def on_reference(self, msg):
        self.reference = json.loads(msg.data)
        self.log.write(json.dumps(dict(global_reference=self.reference))+'\n')

    def envelope(self, lat, lon, height, *, height_reference='home_relative'):
        binding = self.binding
        self.global_id += 1
        self.request_id += 1
        now = time.monotonic()
        command = dict(schema='global-home-v1', latitude_deg=float(lat), longitude_deg=float(lon),
            height_m=float(height), height_reference=height_reference, identity=binding['home']['identity'],
            home_generation=binding['home']['home_generation'], origin_id=binding['origin']['origin_id'],
            local_origin_generation=binding['origin']['local_origin_generation'], command_id=self.global_id,
            issued_monotonic=now, expires_monotonic=now+self.profile['command_ttl_seconds'])
        return dict(version=1, run_id=self.run_id, control_epoch=self.epoch, request_id=self.request_id,
                    command=command, yaw_enu_rad=0.)

    def publish_global(self, envelope):
        self.global_pub.publish(String(data=json.dumps(envelope, allow_nan=False)))
        self.log.write(json.dumps(dict(global_request=envelope))+'\n')
        self.last_global = time.monotonic()

    def pump(self):
        if self.home_actor is not None:
            self.home_actor.poll()
        if self.route is not None and time.monotonic()-self.last_global >= self.profile['renewal_seconds']:
            fraction = min(1., max(0., (self.last_stamp-self.route['start_boot_s'])/self.route['duration_s']))
            lat = self.route['start_lat']+(self.route['latitude_deg']-self.route['start_lat'])*fraction
            lon = self.route['start_lon']+(self.route['longitude_deg']-self.route['start_lon'])*fraction
            self.publish_global(self.envelope(lat, lon, self.route['height_relative_m']))
        super().pump()

    def receive(self, key, msg):
        super().receive(key, msg)
        if key == 'text_info' and self.active:
            event = json.loads(msg.message)
            if (event.get('event') == 'global_command_rejected' and event.get('control_epoch') == self.epoch
                    and event.get('request_id') != getattr(self, 'expected_global_rejection', None)):
                self.error = 'Global request rejected: '+event.get('reason', '')

    def hold(self, label, target, seconds):
        since = None
        def stable():
            nonlocal since
            rows = self.truth_rows()
            if not rows or not self.fresh(): return False
            row = rows[-1]
            if (math.dist(row['position'], target) > self.profile['position_error_m']
                    or math.hypot(*row['velocity']) > self.profile['speed_mps']):
                since = None
                return False
            if since is None: since = row['time']
            return row['time']-since >= seconds
        self.wait(label, stable, 45)

    def exercise_home_change(self, latitude, longitude, height_amsl, physical_target):
        if self.home_actor is None: return
        self.route = None
        self.wait('home_operator_link_ready', lambda: self.home_actor.peer is not None, 5)
        before = deepcopy(self.binding)
        self.active = False
        event_start = len(self.events)
        request = self.home_actor.change(before['home'], altitude_delta_m=self.profile['home_change']['altitude_delta_m'])
        self.phase('home_change_requested', request=request, original_binding=before)
        def changed():
            return (self.home_actor.ack is not None and self.reference and self.reference.get('ready')
                and self.reference['home']['home_generation'] != before['home']['home_generation']
                and any(e.get('event') == 'control_revoked' and e.get('reason') in (
                    'global_home_changed', 'native_clock_or_origin_reset') for e in self.events[event_start:]))
        self.wait('native_home_changed_control_released', changed, 5)
        self.phase('changed_home_observed', binding=self.reference, native_ack=self.home_actor.ack)
        deadline = time.monotonic()+self.profile['home_change']['no_reacquisition_seconds']
        while time.monotonic() < deadline:
            self.pump()
            control = self.latest.get('control_state')
            if control is None or control.control_state != control.INIT:
                raise RuntimeError('Home change automatically reacquired control')
        self.phase('home_change_no_automatic_reacquisition')
        # PX4's native offboard-loss action can be LAND after withdrawal. Clear
        # that action through an explicit operator hold before requesting a new
        # task takeover; do not suppress or bypass the native failsafe gate.
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'),
                  'home_change_explicit_native_hold', 10)
        self.wait('home_change_fresh_navigation', self.fresh, 5)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'home_change_explicit_takeover', 15)
        self.active = True
        # A fresh request with a fresh TTL still cannot reuse the retired home.
        old = self.envelope(latitude, longitude, height_amsl, height_reference='amsl')
        self.expected_global_rejection = old['request_id']
        self.publish_global(old)
        self.wait('old_home_command_rejected', lambda: any(e.get('event') == 'global_command_rejected'
            and e.get('request_id') == old['request_id'] and e.get('reason') == 'home_changed'
            for e in self.events), 5)
        self.binding = deepcopy(self.reference)
        fresh = self.envelope(latitude, longitude, height_amsl, height_reference='amsl')
        self.publish_global(fresh)
        self.wait('new_home_command_accepted', lambda: any(e.get('event') == 'global_command_accepted'
            and e.get('request_id') == fresh['request_id'] for e in self.events), 1)
        self.route = dict(latitude_deg=latitude, longitude_deg=longitude,
            height_relative_m=height_amsl-self.binding['home']['alt_amsl_m'],
            start_lat=latitude, start_lon=longitude, start_boot_s=self.last_stamp, duration_s=1.)
        self.hold('home_changed_target_held', physical_target, self.profile['home_change']['restored_hold_seconds'])
        self.route = None

    def execute(self):
        try:
            self.wait('public_ready', lambda: self.fresh() and self.epoch is not None
                and self.setup_pub.get_subscription_count() == 2 and self.command_pub.get_subscription_count() == 2, 55)
            if not grounded(self.state): raise RuntimeError('Global run requires disarmed ground start')
            self.active = True
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'initial_hold')
            if self.flight_stack == 'px4':
                after = time.monotonic()
                self.wait('native_prearm_ready', lambda: self.arm_ready(after), 55)
            self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'armed')
            self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'), 'takeoff', 45)
            self.hold('initial_five_second_hold', [0., 0., 3.], self.profile['initial_hold_seconds'])
            self.wait('global_reference_ready', lambda: self.reference is not None
                and self.reference.get('ready') and self.reference['control_epoch'] == self.epoch
                and self.global_pub.get_subscription_count() == 2, 10)
            self.binding = deepcopy(self.reference)
            home, origin = self.binding['home'], self.proof['scene_origin']
            east, north, height = self.profile['offset_enu_m']
            lat, lon = reproject(home['latitude_deg'], home['longitude_deg'], north, east)
            if self.flight_stack == 'px4':
                pn, pe = project(origin['latitude_deg'], origin['longitude_deg'], lat, lon)
            else:
                pn = (lat-origin['latitude_deg'])*1e7*AP_SCALE
                pe = (lon-origin['longitude_deg'])*1e7*AP_SCALE*math.cos(math.radians((lat+origin['latitude_deg'])/2))
            target = [pe, pn, home['alt_amsl_m']+height-origin['alt_amsl_m']]
            self.route = dict(latitude_deg=lat, longitude_deg=lon, height_relative_m=height,
                start_lat=home['latitude_deg'], start_lon=home['longitude_deg'], start_boot_s=self.last_stamp,
                duration_s=math.hypot(east, north)/self.profile['reference_speed_mps'])
            self.phase('global_target_frozen', binding=self.binding, route=self.route, physical_target_enu_m=target)
            self.hold('global_target_held', target, self.profile['target_hold_seconds'])
            # An out-of-fence request is rejected while the current valid stream continues.
            bad = self.envelope(lat+.01, lon, height)
            self.expected_global_rejection = bad['request_id']
            self.publish_global(bad)
            self.wait('out_of_fence_rejected', lambda: any(e.get('event') == 'global_command_rejected'
                and e.get('request_id') == bad['request_id'] and e.get('reason') == 'horizontal_range' for e in self.events), 5)
            self.route = None
            # Explicit AMSL uses the same frozen home and objective.
            self.publish_global(self.envelope(lat, lon, home['alt_amsl_m']+height, height_reference='amsl'))
            self.wait('amsl_target_accepted', lambda: any(e.get('event') == 'global_command_accepted'
                and e.get('request_id') == self.request_id for e in self.events), 1)
            self.exercise_home_change(lat, lon, home['alt_amsl_m']+height, target)
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LAND'), 'land_mode')
            self.wait('landed_disarmed', lambda: grounded(self.state), 60)
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold')
        except Exception:
            self.route = None
            self.active = False
            self.error = None
            try:
                self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LAND'), 'failure_land', 10)
                self.wait('failure_landed', lambda: grounded(self.state), self.profile['failure_landing_timeout_s'])
            except Exception as error:
                self.log.write(json.dumps(dict(failure_landing_error=repr(error)))+'\n')
            raise

    def report(self):
        return dict(Task.report(self), global_flight=dict(profile=self.profile, phases=self.rc_phases,
                    binding=self.binding, observed_global_commands=self.global_id))

    def close(self):
        if self.home_actor is not None: self.home_actor.close()
        if self._truth_stream is not None: self._truth_stream.close()
        super().close()
