# SPDX-License-Identifier: Apache-2.0
"""Native ArduCopter services and explicit, optional WksimState SITL profile.

Requires patches/arducopter/0002 and its matching ardupilot_msgs overlay.
Position+yaw also requires explicit opt-in to patch 0001; no MAVLink fallback.
Full XYZ P+V+yaw requires the separate experimental PV firmware/profile;
acceleration and mixed position/velocity axes remain unsupported.
Legacy PoseStamped/GeoPointStamped are not sufficient to prove valid odometry.
"""
import math
import time
from collections import deque

from ardupilot_msgs.msg import GlobalPosition, Status, WksimState
from geometry_msgs.msg import TwistStamped
from ardupilot_msgs.srv import ArmMotors, ModeSwitch, Takeoff
from prometheus_msgs.msg import UAVCommand as Cmd, UAVState
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from .frames import set_orientation, stamp_us, wrap_pi
from .shaping import float32, scalar, vector


def home_offset(home, position):
    """Invert AP Location home-relative coordinates inside the 100 m SITL fence.

    Uses the pinned AP LATLON_TO_M and midpoint longitude scale. Geographic
    targets outside this local envelope must use the explicit global mode.
    """
    east, north, up = vector(position)
    latitude, longitude = home.home_latitude_e7, home.home_longitude_e7
    if abs(latitude) > 850000000 or not -1800000000 <= longitude <= 1800000000:
        raise ValueError('Local ArduCopter home outside validated latitude/longitude envelope')
    if max(abs(east), abs(north), abs(up)) > 100:
        raise ValueError('Local ArduCopter target exceeds 100 m envelope')
    latitude += int(north / 0.011131884502145034)
    midpoint = (latitude + home.home_latitude_e7) / 2e7
    longitude += int(east / (0.011131884502145034 * math.cos(math.radians(midpoint))))
    longitude = (longitude + 1800000000) % 3600000000 - 1800000000
    return latitude / 1e7, longitude / 1e7, up


class ArduCopterLink:
    external_mode = 'GUIDED'

    def __init__(self, node, prefix='/ap', *, position_yaw=False, pv_profile='',
                 stale_seconds=2.0, clock=time.monotonic):
        self.node, self.prefix = node, prefix.rstrip('/')
        self.position_yaw = bool(position_yaw)
        if pv_profile not in ('', 'full_xyz_pv_yaw_v1') or pv_profile and not self.position_yaw:
            raise ValueError('ArduCopter P+V profile must be empty or full_xyz_pv_yaw_v1 with position_yaw enabled')
        self.pv_profile = pv_profile
        self.clock, self.stale_seconds = clock, scalar(stale_seconds)
        if self.stale_seconds <= 0:
            raise ValueError('State timeout must be positive')
        self.latest, self.received = {}, {}
        self.source_stamps = {}
        self.rejections = deque(maxlen=128)
        self.clock_invalid = False
        self.last_clock = clock()
        self.generation, self.reset_kind, self.reset_token = 0, None, None
        self.reset_kinds = set()
        self.pending = None
        self.frozen_freshness = None
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        self.subscriptions = [node.create_subscription(cls, self.prefix+suffix,
            lambda msg, key=key: self.receive(key, msg), qos) for key, cls, suffix in (
                ('status', Status, '/status'), ('local', WksimState, '/wksim/local_state_v1'))]
        self.position_pub = node.create_publisher(GlobalPosition, self.prefix+'/cmd_gps_pose', 1)
        self.velocity_pub = node.create_publisher(TwistStamped, self.prefix+'/cmd_vel', 1)
        self.services = {key: (node.create_client(cls, self.prefix+suffix), cls) for key, cls, suffix in (
            ('arm', ArmMotors, '/arm_motors'), ('mode', ModeSwitch, '/mode_switch'),
            ('takeoff', Takeoff, '/experimental/takeoff'))}

    def receive(self, key, msg):
        now = self._now()
        stamp = (msg.time_boot_us if key == 'local' else
                 msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec)
        previous_stamp = self.source_stamps.get(key)
        if previous_stamp is not None and stamp <= previous_stamp:
            if stamp < previous_stamp:
                self._invalidate_clock()
            self._reject('regressed_source' if stamp < previous_stamp else 'duplicate_source', key, source_stamp=stamp)
            return
        if self.clock_invalid:
            self._reject('clock_invalid', key, source_stamp=stamp)
            return
        if key == 'local':
            resets = (msg.yaw_reset_ms, msg.position_ne_reset_ms, msg.position_down_reset_ms)
            home = (msg.home_valid, msg.home_latitude_e7, msg.home_longitude_e7, msg.home_altitude_cm)
            token = (resets, home)
            kind = None
            if self.reset_token is not None:
                if resets != self.reset_token[0]:
                    kind = 'yaw' if resets[1:] == self.reset_token[0][1:] and home == self.reset_token[1] else 'position'
                elif home != self.reset_token[1]:
                    kind = 'home'
            if kind:
                self.generation += 1
                self.reset_kind = kind
                self.reset_kinds.add(kind)
            self.reset_token = token
        self.source_stamps[key] = stamp
        self.latest[key], self.received[key] = msg, now

    def _reject(self, reason, source, **fields):
        self.rejections.append(dict(reason=reason, source=source, **fields))

    def consume_rejections(self):
        result = list(self.rejections)
        self.rejections.clear()
        return result

    def _invalidate_clock(self):
        if not self.clock_invalid:
            self.generation += 1
            self.reset_kind = 'clock'
            self.reset_kinds.add('clock')
        self.clock_invalid = True
        self.latest.clear()
        self.received.clear()

    def _now(self):
        now = self.clock()
        if not math.isfinite(now) or now < self.last_clock:
            self._invalidate_clock()
        self.last_clock = now
        return now

    def consume_resets(self):
        kinds, self.reset_kinds = self.reset_kinds, set()
        return kinds

    @property
    def state_received_monotonic(self):
        self._now()
        return self.received.get('local')

    @property
    def ready_external(self):
        return self.fresh('local') and self.latest['local'].attitude_valid

    def fresh(self, *keys):
        now = self._now()
        return not self.clock_invalid and all(key in self.latest and 0 <= now-self.received[key]
            and (now-self.received[key] <= self.stale_seconds or
                 self.frozen_freshness is not None and self.frozen_freshness(key, self.received[key])) for key in keys)

    @property
    def flying(self):
        return bool(self.latest['status'].flying) if self.fresh('status') else None

    @property
    def failed(self):
        return bool(self.latest['status'].failsafe) if self.fresh('status') else False

    @property
    def navigation_valid(self):
        if not self.fresh('status','local'):
            return False
        local=self.latest['local']
        return bool(local.filter_status_valid and local.ahrs_healthy and local.attitude_valid
                    and local.position_valid and local.velocity_valid and local.home_valid and local.gps_fix_type>=3)

    def state(self, uav_id):
        msg = UAVState(uav_id=uav_id, location_source=UAVState.GPS)
        msg.header.frame_id = 'map'
        msg.position = msg.velocity = msg.attitude = msg.attitude_rate = [math.nan] * 3
        msg.range = msg.latitude = msg.longitude = msg.altitude = msg.rel_alt = math.nan
        msg.battery_state = msg.battery_percetage = math.nan
        status = self.latest.get('status')
        if status is not None:
            if status.vehicle_type != Status.APM_ARDUCOPTER:
                raise ValueError('Unexpected native ArduPilot vehicle type')
            msg.armed = status.armed
            msg.mode = {0: 'STABILIZE', 2: 'ALT_HOLD', 4: 'GUIDED', 5: 'LOITER',
                        6: 'RTL', 9: 'LAND', 16: 'POSHOLD', 17: 'BRAKE'}.get(status.mode, f'AP:{status.mode}')
        msg.connected = self.fresh('status', 'local')
        local = self.latest.get('local')
        if local is None:
            return msg
        if local.header.frame_id != 'map' or not 0 < local.time_boot_us < 10**12:
            raise ValueError('Unexpected WksimState frame or boot clock')
        stamp_us(msg.header, local.time_boot_us)
        if local.position_valid:
            p = local.pose.position
            msg.position = list(vector((p.x, p.y, p.z)))
            msg.rel_alt = float(msg.position[2])
        if local.velocity_valid:
            v = local.twist.linear
            msg.velocity = list(vector((v.x, v.y, v.z)))
        if local.attitude_valid:
            q, rates = local.pose.orientation, local.twist.angular
            set_orientation(msg, (q.w, q.x, q.y, q.z))
            msg.attitude_rate = list(vector((rates.x, rates.y, rates.z)))
        msg.gps_status, msg.gps_num = local.gps_fix_type, local.gps_num_sats
        if msg.gps_status >= 3:
            msg.latitude, msg.longitude, msg.altitude = (local.gps_latitude_e7/1e7,
                local.gps_longitude_e7/1e7, local.gps_altitude_cm/100.0)
        msg.odom_valid = bool(self.navigation_valid and not self.failed)
        return msg

    def supports(self, command):
        if command.agent_cmd != Cmd.MOVE:
            return None
        if not self.position_yaw:
            return 'arducopter_position_yaw_not_enabled'
        if command.move_mode == Cmd.TRAJECTORY and self.pv_profile:
            return 'arducopter_trajectory_requires_yaw_angle' if command.yaw_rate_mode else None
        if command.move_mode in (Cmd.XYZ_VEL, Cmd.XYZ_VEL_BODY):
            if not command.yaw_rate_mode:
                # The DDS velocity entry carries yaw rate only; a yaw-angle
                # velocity target cannot be accepted without side effects.
                return 'arducopter_velocity_requires_yaw_rate_mode'
            return None
        if command.move_mode not in (Cmd.XYZ_POS, Cmd.XYZ_POS_BODY, Cmd.LAT_LON_ALT):
            return 'arducopter_move_mode_not_implemented'
        return None

    def available(self):
        return bool(self.position_pub.get_subscription_count() and self.velocity_pub.get_subscription_count() and
                    all(client.service_is_ready() for client, _ in self.services.values()))

    @staticmethod
    def mode_name(value):
        try:
            return {'OFFBOARD': 'GUIDED', 'POSCTL': 'LOITER', 'AUTO.LOITER': 'LOITER',
                    'AUTO.LAND': 'LAND', 'AUTO.RTL': 'RTL', 'BRAKE': 'BRAKE'}[value]
        except KeyError as error:
            raise ValueError('Unsupported ArduCopter mode') from error

    def send(self, target):
        if not self.position_yaw or not self.fresh('local', 'status') or not self.available():
            raise ValueError('ArduCopter position+yaw link is not ready')
        local = self.latest['local']
        if not self.state(1).odom_valid:
            raise ValueError('ArduCopter odometry is invalid')
        if self.pv_profile and target.kind == 'local':
            try:
                axes = tuple(tuple(values) for values in (target.position, target.velocity, target.acceleration))
            except TypeError as error:
                raise ValueError('ArduCopter local target requires three-axis vectors') from error
            if any(len(values) != 3 for values in axes):
                raise ValueError('ArduCopter local target requires three-axis vectors')
            if any(v is not None for v in axes[0]) and any(v is not None for v in axes[1]):
                if any(v is not None for v in axes[2]) or target.yaw is None or target.yaw_rate is not None:
                    raise ValueError('ArduCopter P+V requires full position/velocity/yaw without acceleration/yaw rate')
                lat, lon, alt = home_offset(local, axes[0])
                velocity = vector(axes[1])
                # DDS Vector3 is double; the native AP handler consumes Vector3f.
                for value in velocity:
                    float32(value)
                yaw = wrap_pi(float32(target.yaw))
                msg = GlobalPosition(coordinate_frame=GlobalPosition.FRAME_GLOBAL_REL_ALT,
                    type_mask=0x9C0, latitude=lat, longitude=lon, altitude=alt, yaw=yaw)
                msg.velocity.linear.x, msg.velocity.linear.y, msg.velocity.linear.z = velocity
                msg.header.frame_id = 'map'
                stamp_us(msg.header, local.time_boot_us)
                self.position_pub.publish(msg)
                return
        if target.kind == 'local' and any(v is not None for v in target.velocity):
            if any(v is not None for v in (*target.position, *target.acceleration)):
                raise ValueError('ArduCopter velocity profile cannot carry position/acceleration axes')
            if target.yaw is not None:
                raise ValueError('ArduCopter velocity profile carries yaw rate, not yaw angle')
            if not all(math.isfinite(v) for v in target.velocity):
                raise ValueError('ArduCopter velocity reference must be finite')
            rate = float(target.yaw_rate) if target.yaw_rate is not None else 0.0
            if not math.isfinite(rate):
                raise ValueError('ArduCopter velocity yaw rate must be finite')
            msg = TwistStamped()
            msg.header.frame_id = 'map'
            stamp_us(msg.header, local.time_boot_us)
            msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z = (float(v) for v in target.velocity)
            msg.twist.angular.z = rate
            self.velocity_pub.publish(msg)
            return
        if target.yaw is None or target.yaw_rate is not None:
            raise ValueError('ArduCopter position profile requires yaw, not yaw rate')
        if target.kind == 'local':
            if any(v is not None for v in (*target.velocity, *target.acceleration)):
                raise ValueError('ArduCopter position profile cannot carry velocity/acceleration')
            lat, lon, alt = home_offset(local, target.position)
        elif target.kind == 'global':
            lat, lon, alt = vector(target.global_position)
        else:
            raise ValueError('Unsupported ArduCopter setpoint')
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and -100 <= alt <= 100):
            raise ValueError('Global target exceeds validated SITL altitude/coordinate envelope')
        msg = GlobalPosition(coordinate_frame=GlobalPosition.FRAME_GLOBAL_REL_ALT,
            type_mask=0x9F8, latitude=lat, longitude=lon, altitude=alt, yaw=wrap_pi(target.yaw))
        msg.header.frame_id = 'map'
        stamp_us(msg.header, local.time_boot_us)
        self.position_pub.publish(msg)

    def request(self, action, value=None):
        self._now()
        if self.clock_invalid:
            raise ValueError('Native clock invalid; recreate adapter after transport reset')
        if self.pending is not None:
            raise ValueError('Native command already pending')
        if action == 'arm':
            key, fields = 'arm', dict(arm=bool(value))
        elif action == 'takeoff':
            altitude = scalar(value)
            if not 0 < altitude <= 100:
                raise ValueError('Takeoff altitude must be 0..100 m above home')
            key, fields = 'takeoff', dict(alt=altitude)
        elif action == 'land' or action == 'mode':
            modes = {'GUIDED': 4, 'LOITER': 5, 'RTL': 6, 'LAND': 9, 'BRAKE': 17}
            key, fields = 'mode', dict(mode=modes['LAND' if action == 'land' else self.mode_name(value)])
        else:
            raise ValueError('Unsupported native ArduCopter setup')
        client, cls = self.services[key]
        if not client.service_is_ready():
            raise ValueError('Native service is absent')
        self.pending = dict(future=client.call_async(cls.Request(**fields)), client=client,
                            started=self.clock(), key=key, fields=fields)

    def cancel_request(self):
        if self.pending is not None:
            pending = self.pending
            self.pending = None
            future = pending['future']
            self._reject('request_cancelled', pending['key'], request_identity=id(future))
            pending['client'].remove_pending_request(future)
            future.cancel()

    def poll_request(self):
        if self.pending is None:
            raise ValueError('No native command pending')
        now = self._now()
        if self.clock_invalid:
            self.cancel_request()
            return False, 'native_clock_invalid'
        pending, future = self.pending, self.pending['future']
        if future.done():
            self.pending = None
            if future.cancelled() or future.exception() is not None:
                return False, 'native_service_failed'
            response = future.result()
            accepted = response.result if pending['key'] == 'arm' else response.status
            if pending['key'] == 'mode':
                accepted = accepted and response.curr_mode == pending['fields']['mode']
            return bool(accepted), 'native_service_accepted' if accepted else 'native_service_rejected'
        if now-pending['started'] > 5:
            self.cancel_request()
            return False, 'native_ack_timeout'
        return None
