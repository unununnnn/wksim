# SPDX-License-Identifier: Apache-2.0
"""Pinned PX4 uORB/DDS adapter. No MAVLink, ROS init, spin or process ownership.

The node supplies its executor and monotonic clock. Every command requires a
matching native ACK; actual mode/arming completion is separately observed.
"""
import math
import time
from collections import deque

from prometheus_msgs.msg import UAVCommand as Cmd, UAVState
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from px4_msgs.msg import (VehicleStatus, VehicleLocalPosition, VehicleAttitude,
                         VehicleOdometry, SensorGps, VehicleLandDetected,
                         VehicleCommand, VehicleCommandAck, TrajectorySetpoint,
                         OffboardControlMode, VehicleAttitudeSetpoint, EstimatorStatusFlags)

from .frames import ned_axes, ned_frd_quaternion, set_orientation, stamp_us, topic, wrap_pi
from .shaping import scalar, vector


class PX4Link:
    external_mode = 'OFFBOARD'
    position_yaw = True

    def __init__(self, node, prefix, system_id, *, source_system=245, source_component=191,
                 stale_seconds=2.0, clock=time.monotonic, request_identity=None):
        if not all(isinstance(v, int) and 1 <= v <= 255 for v in (system_id, source_system, source_component)):
            raise ValueError('Native system/component IDs must be in 1..255')
        self.node, self.prefix, self.system_id = node, prefix.rstrip('/'), system_id
        self.source_system, self.source_component = source_system, source_component
        self.request_identity = request_identity
        self.used_identities = set()
        self.rejections = deque(maxlen=128)
        self.source_stamps = {}
        self.clock_invalid = False
        self.last_clock = clock()
        self.clock, self.stale_seconds = clock, scalar(stale_seconds)
        if self.stale_seconds <= 0:
            raise ValueError('State timeout must be positive')
        self.latest, self.received = {}, {}
        self.generation = 0
        self.reset_kinds = set()
        self.reset_token = None
        self.pending = None
        self.frozen_freshness = None
        self.publishers, self.subscriptions = {}, []
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        for key, cls, name in (
                ('status', VehicleStatus, 'vehicle_status'), ('position', VehicleLocalPosition, 'vehicle_local_position'),
                ('attitude', VehicleAttitude, 'vehicle_attitude'), ('odometry', VehicleOdometry, 'vehicle_odometry'),
                ('gps', SensorGps, 'vehicle_gps_position'), ('land', VehicleLandDetected, 'vehicle_land_detected'),
                ('estimator', EstimatorStatusFlags, 'estimator_status_flags'),
                ('ack', VehicleCommandAck, 'vehicle_command_ack')):
            self.subscriptions.append(node.create_subscription(cls, topic(self.prefix, 'out', name, cls),
                                      lambda msg, key=key: self.receive(key, msg), qos))
        for key, cls, name in (('command', VehicleCommand, 'vehicle_command'),
                               ('offboard', OffboardControlMode, 'offboard_control_mode'),
                               ('position', TrajectorySetpoint, 'trajectory_setpoint'),
                               ('attitude', VehicleAttitudeSetpoint, 'vehicle_attitude_setpoint')):
            self.publishers[key] = node.create_publisher(cls, topic(self.prefix, 'in', name, cls), 1)

    def receive(self, key, message):
        now = self._now()
        if key == 'ack':
            pending = self.pending
            identity = (message.target_system, message.target_component)
            if (pending is None or identity != pending['identity'] or message.command != pending['command']):
                self._reject('unmatched_ack', key, request_identity=identity, command=message.command)
                return
            if (self.clock_invalid or message.timestamp < pending['timestamp'] or
                    message.timestamp <= pending.get('ack_timestamp', -1)):
                self._reject('old_ack_source', key, request_identity=identity, source_stamp=message.timestamp)
                return
            previous_ack = self.latest.get('ack')
            if (previous_ack is not None and
                    (previous_ack.result != VehicleCommandAck.VEHICLE_CMD_RESULT_IN_PROGRESS or
                     (message.result == VehicleCommandAck.VEHICLE_CMD_RESULT_IN_PROGRESS and
                      message.result_param1 < previous_ack.result_param1))):
                self._reject('regressed_ack_progress', key, request_identity=identity, source_stamp=message.timestamp)
                return
            pending['ack_timestamp'] = message.timestamp
            self.latest[key], self.received[key] = message, now
            return
        stamp = message.timestamp
        previous_stamp = self.source_stamps.get(key)
        if previous_stamp is not None and stamp <= previous_stamp:
            if stamp < previous_stamp:
                self._invalidate_clock()
            self._reject('regressed_source' if stamp < previous_stamp else 'duplicate_source', key, source_stamp=stamp)
            return
        if self.clock_invalid:
            self._reject('clock_invalid', key, source_stamp=stamp)
            return
        sample_stamp = getattr(message, 'timestamp_sample', 0) or stamp
        previous_sample = self.source_stamps.get(key + ':sample')
        if previous_sample is not None and sample_stamp <= previous_sample:
            if sample_stamp < previous_sample:
                self._invalidate_clock()
            self._reject('regressed_sample' if sample_stamp < previous_sample else 'duplicate_sample', key, source_stamp=sample_stamp)
            return
        previous = self.latest.get(key)
        self.source_stamps[key] = stamp
        self.source_stamps[key + ':sample'] = sample_stamp
        self.latest[key], self.received[key] = message, now
        if key == 'position':
            token = (message.xy_reset_counter, message.z_reset_counter, message.heading_reset_counter, message.ref_timestamp)
            if self.reset_token is not None and token != self.reset_token:
                self.generation += 1
                self.reset_kinds.add('yaw' if token[:2] == self.reset_token[:2] and token[3] == self.reset_token[3] else 'position')
            self.reset_token = token
        if key == 'attitude' and previous is not None and message.quat_reset_counter != previous.quat_reset_counter:
            self.generation += 1
            self.reset_kinds.add('yaw' if max(abs(v) for v in message.delta_q_reset[1:3]) < 1e-3 else 'attitude')

    def _reject(self, reason, source, **fields):
        self.rejections.append(dict(reason=reason, source=source, **fields))

    def consume_rejections(self):
        result = list(self.rejections)
        self.rejections.clear()
        return result

    def _invalidate_clock(self):
        if not self.clock_invalid:
            self.generation += 1
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
        return self.received.get('position')

    @property
    def ready_external(self):
        return bool(self.fresh('position') and self.latest['position'].heading_good_for_control)

    def fresh(self, *keys):
        now = self._now()
        return not self.clock_invalid and all(key in self.latest and 0 <= now-self.received[key]
            and (now-self.received[key] <= self.stale_seconds or
                 self.frozen_freshness is not None and self.frozen_freshness(key, self.received[key])) for key in keys)

    def timestamp(self):
        if not self.fresh('position'):
            raise ValueError('Missing/stale PX4 simulation timestamp')
        timestamp = self.latest['position'].timestamp
        if not 0 < timestamp < 10**12:
            raise ValueError('Expected PX4 boot microseconds; accelerated SITL disables Agent clock sync')
        return timestamp

    @property
    def flying(self):
        return not self.latest['land'].landed if self.fresh('land') else None

    @property
    def failed(self):
        return bool(self.latest['status'].failsafe) if self.fresh('status') else False

    @property
    def navigation_valid(self):
        if not self.fresh('status','position','attitude','gps','estimator'):
            return False
        pos,est=self.latest['position'],self.latest['estimator']
        return bool(self.latest['gps'].fix_type>=3 and pos.xy_valid and pos.z_valid
                    and pos.v_xy_valid and pos.v_z_valid and est.cs_tilt_align and est.cs_yaw_align
                    and not pos.dead_reckoning)

    def state(self, uav_id):
        msg = UAVState(uav_id=uav_id, location_source=UAVState.GPS)
        msg.header.frame_id = 'map'
        msg.attitude_q.w = 1.0
        msg.attitude_rate = [math.nan] * 3
        msg.range = msg.latitude = msg.longitude = msg.altitude = msg.rel_alt = math.nan
        msg.battery_state = msg.battery_percetage = math.nan
        status = self.latest.get('status')
        if status is not None:
            if status.system_id != self.system_id or status.vehicle_type != VehicleStatus.VEHICLE_TYPE_ROTARY_WING:
                raise ValueError('Unexpected native PX4 identity/type')
            msg.armed = status.arming_state == VehicleStatus.ARMING_STATE_ARMED
            msg.mode = {2: 'POSCTL', 14: 'OFFBOARD', 18: 'AUTO.LAND', 5: 'AUTO.RTL', 0: 'MANUAL',
                        1: 'ALTCTL', 4: 'AUTO.LOITER', 17: 'AUTO.TAKEOFF'}.get(status.nav_state, f'PX4:{status.nav_state}')
        msg.connected = self.fresh('status', 'position', 'attitude')
        if 'position' not in self.latest or 'attitude' not in self.latest:
            return msg
        pos, att = self.latest['position'], self.latest['attitude']
        msg.position = list(ned_axes((pos.x, pos.y, pos.z)))
        msg.velocity = list(ned_axes((pos.vx, pos.vy, pos.vz)))
        set_orientation(msg, ned_frd_quaternion(att.q))
        stamp_us(msg.header, pos.timestamp_sample or pos.timestamp)
        if self.fresh('odometry'):
            angular = vector(self.latest['odometry'].angular_velocity)
            msg.attitude_rate = [angular[0], -angular[1], -angular[2]]
        if self.fresh('gps'):
            gps = self.latest['gps']
            msg.gps_status, msg.gps_num = gps.fix_type, gps.satellites_used
            msg.latitude, msg.longitude, msg.altitude = (float(v) for v in (gps.latitude_deg, gps.longitude_deg, gps.altitude_msl_m))
        estimator = self.latest.get('estimator')
        msg.odom_valid = bool(self.navigation_valid and not self.failed)
        if pos.dist_bottom_valid:
            msg.range = float(pos.dist_bottom)
        return msg

    def supports(self, command):
        if command.agent_cmd != Cmd.MOVE:
            return None
        if command.move_mode == Cmd.LAT_LON_ALT:
            return 'px4_global_command_adapter_not_implemented'
        return None if command.move_mode in range(Cmd.XYZ_POS, Cmd.XYZ_ATT + 1) else 'unsupported_move_mode'

    def available(self):
        return all(self.publishers[key].get_subscription_count() for key in ('command', 'offboard', 'position'))

    @staticmethod
    def mode_name(value):
        return value

    def send(self, target):
        timestamp = self.timestamp()
        if target.kind == 'local':
            position, velocity, acceleration = (list(ned_axes(v)) for v in (target.position, target.velocity, target.acceleration))
            flags = [any(v is not None for v in values) for values in (target.position, target.velocity, target.acceleration)]
            if not any(flags):
                raise ValueError('No active trajectory axes')
            self.publishers['offboard'].publish(OffboardControlMode(timestamp=timestamp, position=flags[0], velocity=flags[1], acceleration=flags[2]))
            self.publishers['position'].publish(TrajectorySetpoint(timestamp=timestamp, position=position,
                velocity=velocity, acceleration=acceleration, jerk=[math.nan] * 3,
                yaw=math.nan if target.yaw is None else wrap_pi(math.pi/2-target.yaw),
                yawspeed=math.nan if target.yaw_rate is None else -scalar(target.yaw_rate)))
        elif target.kind == 'attitude':
            x, y, z, w = vector(target.quaternion_xyzw, 4)
            thrust = scalar(target.thrust)
            if not 0 <= thrust <= 1:
                raise ValueError('Invalid normalized thrust')
            self.publishers['offboard'].publish(OffboardControlMode(timestamp=timestamp, attitude=True))
            self.publishers['attitude'].publish(VehicleAttitudeSetpoint(timestamp=timestamp,
                q_d=list(ned_frd_quaternion((w, x, y, z))), thrust_body=[0.0, 0.0, -thrust]))
        else:
            raise ValueError(f'Unsupported PX4 setpoint: {target.kind}')

    def send_global(self, target, yaw):
        """Explicit global projection result; never pass it through local shaping."""
        from Simulator.wksim_control.global_reference import ResolvedTarget, require
        require(type(target) is ResolvedTarget and target.native_kind == 'trajectory_setpoint_ned'
                and target.original.identity.stack == 'px4', 'global_target_wrong_stack')
        timestamp = self.timestamp()
        position = list(vector(target.native_target))
        native_yaw = wrap_pi(math.pi/2-scalar(yaw))
        self.publishers['offboard'].publish(OffboardControlMode(timestamp=timestamp, position=True))
        self.publishers['position'].publish(TrajectorySetpoint(timestamp=timestamp, position=position,
            velocity=[math.nan]*3, acceleration=[math.nan]*3, jerk=[math.nan]*3,
            yaw=native_yaw, yawspeed=math.nan))

    def request(self, action, value=None):
        if self.pending is not None:
            raise ValueError('Native command already pending')
        if not self.available():
            raise ValueError('Native command subscriber is absent')
        parameters = [0.0] * 7
        if action == 'arm':
            command, parameters[0] = 400, float(bool(value))
        elif action == 'takeoff':
            pos = self.latest.get('position')
            height = scalar(value)
            if not self.fresh('position') or not pos.xy_global or not pos.z_global or not 0 < height <= 100:
                raise ValueError('Native takeoff requires a global origin and 0..100 m local altitude')
            command = 22
            parameters[3:6] = [math.nan] * 3
            parameters[6] = scalar(pos.ref_alt) + height  # NAV_TAKEOFF uses AMSL.
        elif action == 'land' or (action == 'mode' and value == 'AUTO.LAND'):
            command = 21
        elif action == 'mode' and value == 'AUTO.RTL':
            command = 20
        elif action == 'mode' and value == 'AUTO.LOITER':
            command, parameters[0], parameters[1], parameters[2] = 176, 1.0, 4.0, 3.0
        elif action == 'mode' and value in ('OFFBOARD', 'POSCTL'):
            command, parameters[0], parameters[1] = 176, 1.0, float(6 if value == 'OFFBOARD' else 3)
        else:
            raise ValueError('Unsupported native PX4 setup')
        timestamp = self.timestamp()
        identity = ((self.source_system, self.source_component) if self.request_identity is None
                    else tuple(self.request_identity()))
        if len(identity) != 2 or not all(type(v) is int and 1 <= v <= 255 for v in identity):
            raise ValueError('Request identity must contain two integers in 1..255')
        if self.request_identity is not None:
            if identity in self.used_identities:
                raise ValueError('Native request identity reused')
            self.used_identities.add(identity)
        request = VehicleCommand(timestamp=timestamp, command=command, target_system=self.system_id,
                                  target_component=1, source_system=identity[0],
                                  source_component=identity[1], from_external=True)
        for index, parameter in enumerate(parameters, 1):
            setattr(request, f'param{index}', parameter)
        self.latest.pop('ack', None)
        self.pending = dict(command=command, timestamp=timestamp, started=self._now(), identity=identity)
        self.publishers['command'].publish(request)

    def poll_request(self):
        if self.pending is None:
            raise ValueError('No native command pending')
        now = self._now()
        if self.clock_invalid:
            self.pending = None
            return False, 'native_clock_invalid'
        ack, pending = self.latest.get('ack'), self.pending
        if (ack is not None and ack.command == pending['command'] and ack.timestamp >= pending['timestamp']
                and (ack.target_system, ack.target_component) == pending['identity']):
            if ack.result != VehicleCommandAck.VEHICLE_CMD_RESULT_IN_PROGRESS:
                self.pending = None
                return ack.result == VehicleCommandAck.VEHICLE_CMD_RESULT_ACCEPTED, f'native_result_{ack.result}'
        if now - pending['started'] > 5:
            self.pending = None
            return False, 'native_ack_timeout'
        return None

    def cancel_request(self):
        if self.pending is not None:
            self._reject('request_cancelled', 'command', request_identity=self.pending['identity'], command=self.pending['command'])
        self.pending = None
        self.latest.pop('ack', None)
