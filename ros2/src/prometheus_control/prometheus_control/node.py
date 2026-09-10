# Copyright 2022 AMOVLAB; wksim native ROS2 migration changes 2026.
# SPDX-License-Identifier: Apache-2.0
"""Prometheus setup/command/control-state node using native flight-stack DDS.

Source behavior: uav_controller.cpp setup callback, mainloop and the migrated
CommandProcessor/SetpointShaper. Embedded PID/UDE/NE and reboot
are not implemented here. Native requests and observed completion are distinct.
"""
from copy import deepcopy
import json
import math
import re
import signal
import time

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Bool, String
from prometheus_msgs.msg import UAVCommand as Cmd, UAVSetup, UAVState, UAVControlState as Control, TextInfo
from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState

from .command import CommandProcessor, Desired
from .shaping import Setpoint, SetpointShaper, scalar
from .session import RunSession


class ControlNode(Node):
    scene = scene_hold = scene_recovery = None
    def __init__(self):
        super().__init__('prometheus_native_control')
        def parameter(name, default):
            return self.declare_parameter(name, default, ParameterDescriptor(read_only=True)).value
        stack = parameter('flight_stack', '')
        self.uav_id = parameter('uav_id', 1)
        if stack not in ('px4', 'arducopter') or not isinstance(self.uav_id, int) or not 1 <= self.uav_id <= 255:
            raise ValueError('Select flight_stack=px4|arducopter and uav_id in 1..255')
        prefix = parameter('native_prefix', '/ap' if stack == 'arducopter' else '')
        if prefix and not re.fullmatch(r'(?:/[A-Za-z_][A-Za-z_0-9]*)+', prefix):
            raise ValueError('native_prefix must be an absolute ROS namespace without a trailing slash')
        self.wall = time.monotonic
        self.operation_uses_sim_time = bool(self.get_parameter('use_sim_time').value)
        self.last_operation_time = None
        self.input_age = scalar(parameter('input_max_age_seconds', 2.0))
        self.takeoff_height = scalar(parameter('takeoff_height', 3.0))
        stale = scalar(parameter('state_timeout_seconds', 2.0))
        self.output_period = 1 / scalar(parameter('output_rate_hz', 40.0))
        if self.input_age <= 0 or not 0.005 <= self.output_period <= 0.1:
            raise ValueError('Input age must be positive; output rate must be 10..200 Hz')
        if stack == 'px4':
            from .native_px4 import PX4Link
            self.native = PX4Link(self, prefix, parameter('native_system_id', 1), stale_seconds=stale,
                                  request_identity=lambda: self.session.native_identity())
        else:
            from .native_arducopter import ArduCopterLink
            self.native = ArduCopterLink(self, prefix, position_yaw=parameter('arducopter_position_yaw', False),
                                        pv_profile=parameter('arducopter_pv_profile', ''),
                                        mixed_profile=parameter('arducopter_mixed_profile', ''),
                                        stale_seconds=stale)
        self.processor = CommandProcessor(takeoff_height=self.takeoff_height,
            enable_external_control=parameter('enable_external_attitude', False))
        self.shaper = SetpointShaper()
        self.state = UAVState(uav_id=self.uav_id)
        self.state.attitude_q.w = 1.0
        self.operation = None
        self.warmup_target = None
        self.revoked = False
        self.native_generation = self.native.generation
        self.last_output = -math.inf
        self.last_move_id = 0
        self.last_command_stamp = 0
        self.event_id = 0
        self.sequence = 0
        self.request_context = self.command_request_id = 0
        root = f'/uav{self.uav_id}/prometheus'
        self.state_pub = self.create_publisher(UAVState, root + '/state', 10)
        self.control_pub = self.create_publisher(Control, root + '/control_state', 10)
        self.info_pub = self.create_publisher(TextInfo, root + '/text_info', 10)
        self.stop_pub = self.create_publisher(Bool, root + '/stop_control_state', 10)
        self.session_pub = self.create_publisher(SessionState, root + '/v2/state', 10)
        self.setup_sub = self.create_subscription(SetupRequest, root + '/v2/setup',
                                                  lambda msg: self.on_request('setup', msg), 1)
        self.command_sub = self.create_subscription(CommandRequest, root + '/v2/command',
                                                    lambda msg: self.on_request('command', msg), 1)
        self.legacy_setup_sub = self.create_subscription(UAVSetup, root + '/setup',
            lambda msg: self.event('setup_rejected', error=True, reason='legacy_input_requires_session', request_id=0), 1)
        self.legacy_command_sub = self.create_subscription(Cmd, root + '/command',
            lambda msg: self.event('command_rejected', error=True, reason='legacy_input_requires_session', request_id=0), 1)
        self.session = RunSession(parameter('run_id', ''), self.uav_id)
        self.rc_input = None
        self.rc_receiver = None
        rc_boot_id = parameter('rc_boot_id', '')
        if rc_boot_id:
            from Simulator.wksim_control.rc_input import RCInput
            if not re.fullmatch(r'[0-9a-f]{32}', rc_boot_id):
                raise ValueError('rc_boot_id must be 32 lowercase hex characters')
            self.rc_input = RCInput({'run_id': self.session.run_id, 'control_epoch': self.session.epoch,
                                     'uav_id': self.uav_id, 'boot_id': rc_boot_id})
            from rclpy.qos import qos_profile_sensor_data, QoSProfile
            from .rc_transport import RCTake
            self.rc_take = RCTake()
            self.rc_receiver = rclpy.create_node('wksim_rc_receiver', namespace=f'/uav{self.uav_id}')
            self.rc_sub = self.rc_receiver.create_subscription(String, root + '/v2/rc_input', lambda msg: None,
                QoSProfile(depth=1, reliability=qos_profile_sensor_data.reliability))
        self.scene = self.scene_hold = self.scene_recovery = None
        self.scene_native_endpoints = {}
        self.retired_native_endpoints = set()
        scene_epoch = parameter('scene_epoch', '')
        if scene_epoch:
            from .scene import SceneLease, TOPIC
            if not self.operation_uses_sim_time:
                raise ValueError('Scene permission requires explicit ROS simulation time')
            self.scene = SceneLease(self.session.run_id, scene_epoch, self.wall)
            self.scene_sub = self.create_subscription(String, TOPIC, self.on_scene, 1)
            self.scene_ack = self.create_publisher(String, TOPIC+f'/control/uav{self.uav_id}', 1)
            self.native.frozen_freshness = self.frozen_native_fresh
        # Watchdogs/control keep running even if a ROS simulation clock is paused.
        self.timer = self.create_timer(0.01, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))
        try:
            self.event('started', stack=stack, native_prefix=prefix, position_yaw=self.native.position_yaw,
                       operation_clock='ros' if self.operation_uses_sim_time else 'monotonic',
                       communication_clock='monotonic')
        except BaseException:
            self.session.close()
            raise

    def event(self, event, *, error=False, **fields):
        self.event_id += 1
        fields.setdefault('request_id', self.request_context or
                          (self.operation or {}).get('request_id', self.command_request_id))
        msg = TextInfo(message_type=TextInfo.ERROR if error else TextInfo.INFO,
                       message=json.dumps(dict(event=event, event_id=self.event_id,
                           version=RunSession.VERSION, run_id=self.session.run_id,
                           emitted_monotonic_ns=time.monotonic_ns(), emitted_unix_ns=time.time_ns(),
                           control_epoch=self.session.epoch, **fields), allow_nan=False))
        msg.header.stamp = self.get_clock().now().to_msg()
        self.info_pub.publish(msg)
        self.get_logger().info(msg.message)

    def on_request(self, kind, request):
        try:
            self.request_context = self.session.accept(request)
        except ValueError as error:
            self.event(kind + '_rejected', error=True, reason=str(error), request_id=request.request_id,
                       requested_run_id=request.run_id, requested_epoch=request.control_epoch)
            return
        try:
            if self.scene is not None:
                try:
                    permission = self.scene.check()
                    if permission['phase'] != 'running' or self.scene_hold is not None:
                        raise ValueError('scene_suspended_no_new_high_level_request')
                except ValueError as error:
                    self.event(kind+'_rejected', error=True, reason=str(error))
                    return
            (self.on_setup if kind == 'setup' else self.on_command)(getattr(request, kind))
        finally:
            self.request_context = 0

    def unfrozen_state(self):
        callback, self.native.frozen_freshness = self.native.frozen_freshness, None
        try:
            return self.native.state(self.uav_id)
        finally:
            self.native.frozen_freshness = callback

    def scene_endpoints(self):
        # A read-only observer may subscribe to outgoing control topics, so
        # subscription counts alone do not prove a native FC DDS session.
        # Bind the actual native state writers while their samples are valid.
        endpoints = {}
        for subscription in self.native.subscriptions:
            if 'command_ack' in subscription.topic_name:
                continue
            writers = [writer for writer in self.get_publishers_info_by_topic(subscription.topic_name)
                       if bytes(writer.endpoint_gid).hex() not in self.retired_native_endpoints]
            if len(writers) != 1:
                raise ValueError('scene_requires_one_native_state_writer_per_topic: '
                                 +subscription.topic_name+': count='+str(len(writers)))
            endpoints[subscription.topic_name] = bytes(writers[0].endpoint_gid).hex()
        if not endpoints:
            raise ValueError('scene_native_state_writers_missing')
        return endpoints

    def on_scene(self, message):
        accepted = False
        try:
            if not self.scene.accept(message.data):
                return
            accepted = True
            permission = self.scene.check()
            if permission['phase'] == 'recovering':
                if (not self.revoked or self.processor.control_state != Control.INIT
                        or self.operation is not None or self.native.pending is not None):
                    raise ValueError('scene_recovery_requires_withdrawn_task_control')
                if self.scene_recovery is None or self.scene_recovery['request_id'] != permission['request_id']:
                    if self.uav_id in permission.get('faulted_uav_ids',[]):
                        if not self.scene_native_endpoints:
                            raise ValueError('No previously bound native source to retire')
                        self.retired_native_endpoints.update(self.scene_native_endpoints.values())
                        self.event('scene_native_sources_retired', scene_epoch=self.scene.epoch,
                            scene_request_id=permission['request_id'], native_endpoints=self.scene_native_endpoints)
                    self.scene_hold = None
                    self.scene_recovery = dict(request_id=permission['request_id'],
                        frozen_ns=permission['time_ns'], generation=self.native.generation, ready=False)
                    self.event('scene_recovery_requested', scene_epoch=self.scene.epoch,
                        scene_request_id=permission['request_id'], frozen_ns=permission['time_ns'],
                        task_control_released=True)
            elif permission['phase'] == 'running' and self.scene_recovery is not None:
                if not self.recovery_state_ready():
                    raise ValueError('scene_running_before_fresh_recovery_evidence')
                self.scene_native_endpoints = self.scene_recovery['native_endpoints']
                self.scene_recovery = None
                self.event('scene_physics_ready_new_task_required', scene_epoch=self.scene.epoch,
                    scene_request_id=permission['request_id'], task_control_released=self.revoked)
            elif permission['phase'] == 'paused' and self.scene_hold is None:
                state = self.unfrozen_state()
                if (self.revoked or self.operation is not None or self.native.pending is not None
                        or self.processor.control_state != Control.COMMAND_CONTROL
                        or not state.connected or not state.odom_valid or not state.armed
                        or state.mode != self.native.external_mode or not self.native.available()):
                    raise ValueError('scene_pause_requires_current_settled_position_control')
                self.scene_hold = dict(generation=self.native.generation,
                    received=dict(self.native.received), paused_ns=permission['time_ns'], resumed_ready=False,
                    native_endpoints=self.scene_endpoints())
                self.event('scene_pause_bound', scene_epoch=self.scene.epoch, tick=permission['tick'],
                           scene_request_id=permission['request_id'], native_endpoints=self.scene_hold['native_endpoints'])
            elif permission['phase'] == 'resuming' and self.scene_hold is not None:
                # Every new resume requires new native evidence beyond the last
                # frozen boundary, including after a four-tick single step.
                if self.scene_hold.get('resume_request') != permission['request_id']:
                    self.scene_hold.update(paused_ns=permission['time_ns'], resumed_ready=False,
                                           resume_request=permission['request_id'])
            elif permission['phase'] == 'running' and self.scene_hold is not None:
                if not self.scene_hold['resumed_ready']:
                    raise ValueError('scene_running_before_new_native_resume_evidence')
                self.scene_hold = None
                self.event('scene_running_confirmed', scene_epoch=self.scene.epoch, tick=permission['tick'],
                           scene_request_id=permission['request_id'])
            if self.scene_hold is not None and self.scene_endpoints() != self.scene_hold['native_endpoints']:
                raise ValueError('scene_native_dds_writer_identity_changed')
        except (ValueError, TypeError, OverflowError) as error:
            # Malformed/foreign messages never grant an exemption. Once bound,
            # a rejected transition retires active control, never replays it.
            if accepted and str(error).startswith('scene_running_before_'):
                self.scene.error = 'scene_faulted_control_released'
            if (accepted or self.scene.error is not None) and not self.revoked:
                self.revoke(str(error))
            self.event('scene_permission_rejected', error=True, reason=str(error))

    def recovery_state_ready(self):
        recovery = self.scene_recovery
        if recovery is not None:
            recovery.update(home_initialized=self.processor.home is not None,native_flying=None)
        if (recovery is None or not self.revoked or self.native.generation != recovery['generation']
                or self.native.clock_invalid or not self.native.available()):
            if recovery is not None:
                recovery['not_ready_reason']='generation_clock_or_native_endpoints_not_ready'
            return False
        state = self.unfrozen_state()
        stamp = state.header.stamp.sec*10**9+state.header.stamp.nanosec
        if not (state.connected and self.native.navigation_valid and state.armed and stamp > recovery['frozen_ns']):
            recovery['not_ready_reason']='fresh_armed_navigation_not_ready'
            return False
        recovery['native_flying']=self.native.flying
        if not recovery['home_initialized'] or recovery['native_flying'] is not True:
            recovery['not_ready_reason']='fresh_home_and_airborne_evidence_not_ready'
            return False
        try:
            recovery['native_endpoints']=self.scene_endpoints()
        except ValueError as error:
            recovery['not_ready_reason']=str(error)
            return False
        recovery['not_ready_reason']=None
        return True

    def supervise_recovery(self):
        permission = self.scene.check()
        if permission['phase'] != 'recovering' or not self.revoked:
            raise ValueError('Recovery phase cannot restore task ownership')
        if self.native.generation != self.scene_recovery['generation'] or self.native.clock_invalid:
            raise ValueError('Recovery cannot repair native time/origin regression')
        ready = self.recovery_state_ready()
        self.scene_recovery['ready'] = ready
        reason=self.scene_recovery.get('not_ready_reason')
        if self.scene_recovery.get('last_reported_reason','initial') != reason:
            self.event('scene_recovery_readiness', reason=reason, ready=ready,
                       connected=self.state.connected, odom_valid=self.state.odom_valid,
                       armed=self.state.armed, native_generation=self.native.generation)
            self.scene_recovery['last_reported_reason']=reason
        stamp = self.state.header.stamp.sec*10**9+self.state.header.stamp.nanosec
        self.scene_ack.publish(String(data=json.dumps(dict(version=1, run_id=self.session.run_id,
            scene_epoch=self.scene.epoch, control_epoch=self.session.epoch, uav_id=self.uav_id,
            phase='recovering', request_id=permission['request_id'], sequence=permission['sequence'],
            tick=permission['tick'], ready=ready, source_boot_ns=stamp, issued_monotonic_s=self.wall(),
            task_control_released=True, native_generation=self.native.generation,
            readiness='native_link_navigation_home_and_airborne',
            home_initialized=self.scene_recovery.get('home_initialized',False),
            native_flying=self.scene_recovery.get('native_flying'),
            command_control_eligible=bool(ready and self.state.odom_valid),
            native_failsafe=self.native.failed, native_mode=self.state.mode,
            native_endpoints=self.scene_recovery.get('native_endpoints',{})), allow_nan=False)))

    def frozen_native_fresh(self, key, received):
        if self.scene is None or self.scene_hold is None or self.revoked:
            return False
        try:
            permission = self.scene.check()
        except ValueError:
            return False
        return (permission['phase'] in ('paused', 'stepping', 'resuming')
                and self.scene_hold['generation'] == self.native.generation
                and key in self.scene_hold['received']
                and received >= self.scene_hold['received'][key] and self.native.available())

    def scene_supervise(self):
        permission = self.scene.check()
        if self.scene_hold is None:
            if permission['phase'] != 'running':
                raise ValueError('scene_suspended_without_control_binding')
            return
        if (self.native.generation != self.scene_hold['generation'] or not self.native.available()
                or not self.state.connected or not self.state.odom_valid or self.native.failed):
            raise ValueError('scene_frozen_state_or_link_invalid')
        stamp = self.state.header.stamp.sec*10**9+self.state.header.stamp.nanosec
        if permission['phase'] in ('paused', 'stepping') and stamp > permission['time_ns']+(4000000 if permission['phase'] == 'stepping' else 0):
            raise ValueError('native_state_advanced_past_paused_scene')
        ready = permission['phase'] == 'paused'
        if permission['phase'] == 'resuming':
            current = self.unfrozen_state()
            stamp = current.header.stamp.sec*10**9+current.header.stamp.nanosec
            ready = (current.connected and current.odom_valid and current.armed
                     and current.mode == self.native.external_mode and stamp > self.scene_hold['paused_ns'])
            self.scene_hold['resumed_ready'] |= bool(ready)
        self.scene_ack.publish(String(data=json.dumps(dict(version=1, run_id=self.session.run_id,
            scene_epoch=self.scene.epoch, control_epoch=self.session.epoch, uav_id=self.uav_id,
            phase=permission['phase'], request_id=permission['request_id'],
            sequence=permission['sequence'], tick=permission['tick'], ready=bool(ready),
            source_boot_ns=stamp, issued_monotonic_s=self.wall()), allow_nan=False)))

    def input_stamp(self, header):
        stamp = header.stamp.sec * 10**9 + header.stamp.nanosec
        age = (self.get_clock().now().nanoseconds - stamp) / 1e9
        if stamp <= 0 or not -0.5 <= age <= self.input_age:
            raise ValueError('missing_stale_or_future_command_stamp')
        if header.frame_id not in ('', 'map', 'world'):
            raise ValueError('unsupported_command_frame')
        return stamp

    def operation_time(self):
        """Physical operation durations follow explicit ROS simulation time.

        Native transport freshness, ACK waiting and output servicing keep their
        existing monotonic wall clock. This adds no pause freshness exemption.
        """
        if bool(self.get_parameter('use_sim_time').value) != self.operation_uses_sim_time:
            raise ValueError('operation_clock_source_changed')
        now = self.get_clock().now().nanoseconds / 1e9 if self.operation_uses_sim_time else self.wall()
        if (not math.isfinite(now) or self.operation_uses_sim_time and now <= 0
                or self.last_operation_time is not None and now < self.last_operation_time):
            raise ValueError('operation_clock_missing_or_regressed')
        self.last_operation_time = now
        return now

    def operation_ns(self):
        return int(self.operation_time() * 1_000_000_000)

    def on_rc(self, msg, info):
        if self.rc_input is None:
            return
        gid = bytes(info.publisher_gid)
        try:
            now_ns = time.monotonic_ns()
            if self.rc_input.state == 'REVOKED':
                self.rc_input.reset()
            if self.rc_input.state == 'UNBOUND':
                answer = self.rc_input.bind(msg.data, gid, now_ns=now_ns)
            else:
                answer = self.rc_input.receive(msg.data, gid, received_ns=now_ns)
        except (ValueError, RuntimeError) as error:
            answer = {'accepted': False, 'reason': str(error)}
        self.event('rc_frame', accepted=bool(answer.get('accepted')), state=self.rc_input.state,
                   reason=answer.get('reason'), sequence=answer.get('sequence', 0),
                   publisher_gid=gid.hex(), received_monotonic_ns=now_ns,
                   cdr_hex=getattr(info, 'cdr_hex', None),
                   raw=msg.data, native_generation=self.native_generation, native_mode=self.state.mode)
        if self.rc_input.state == 'REVOKED' and self.processor.control_state == Control.RC_POS_CONTROL:
            self.revoke('rc_input_revoked:' + str(self.rc_input.last_rejection))

    def revoke(self, reason):
        request_id = (self.operation or {}).get('request_id', self.command_request_id)
        self.processor.enter_control(Control.INIT)
        self.shaper.reset()
        self.operation = self.warmup_target = None
        self.scene_hold = self.scene_recovery = None
        self.revoked = True
        # Clearing observation is not cancelling a command already inside the FC.
        self.native.cancel_request()
        if self.rc_input is not None and self.rc_input.state != 'REVOKED':
            self.rc_input.revoke('control_revoked')
        self.event('control_revoked', error=True, reason=reason, request_id=request_id)

    def on_setup(self, msg):
        try:
            self.input_stamp(msg.header)
            self.operation_time()  # Reject a broken time source before any native side effect.
            if self.operation is not None or self.native.pending is not None:
                raise ValueError('setup_busy')
            if not self.state.connected or not self.native.available():
                raise ValueError('native_link_not_ready')
            if msg.cmd == UAVSetup.SET_CONTROL_MODE:
                if msg.control_state not in ('COMMAND_CONTROL', 'RC_POS_CONTROL'):
                    raise ValueError('control_setup_mode_not_implemented')
                if msg.control_state == 'RC_POS_CONTROL' and self.rc_input is None:
                    raise ValueError('rc_input_not_configured')
                if not self.state.armed or not self.state.odom_valid:
                    raise ValueError('command_control_requires_armed_valid_state')
                if not self.native.position_yaw:
                    raise ValueError('firmware_position_yaw_not_enabled')
                if self.processor.control_state == Control.COMMAND_CONTROL and not self.revoked \
                        and msg.control_state == 'COMMAND_CONTROL':
                    self.event('setup_completed', cmd=int(msg.cmd), control_state='COMMAND_CONTROL', unchanged=True)
                    return
                if self.processor.control_state == Control.RC_POS_CONTROL and not self.revoked \
                        and msg.control_state == 'RC_POS_CONTROL':
                    self.event('setup_completed', cmd=int(msg.cmd), control_state='RC_POS_CONTROL', unchanged=True)
                    return
                if self.processor.home is None or self.native.flying is None:
                    raise ValueError('missing_home_or_landed_state')
                if msg.control_state == 'RC_POS_CONTROL':
                    if (self.native.flying is not True or self.processor.local_position()[2] < .2
                            or self.state.mode != self.native.external_mode or not self.native.ready_external):
                        raise ValueError('rc_requires_airborne_external_mode')
                    writers = self.get_publishers_info_by_topic(self.rc_sub.topic_name)
                    if len(writers) != 1 or bytes(writers[0].endpoint_gid) != self.rc_input.owner_gid:
                        raise ValueError('rc_requires_one_bound_publisher')
                    # RC never starts native takeoff or changes the FC mode.
                    self.operation = dict(request_id=self.request_context, requested_mode='RC_POS_CONTROL')
                    try:
                        self.activate()
                    except (ValueError, RuntimeError):
                        self.operation = None
                        raise
                    return
                if self.processor.control_state == Control.RC_POS_CONTROL:
                    if (self.state.mode != self.native.external_mode or not self.native.ready_external
                            or not self.rc_input.command_handoff_ready(time.monotonic_ns())):
                        raise ValueError('rc_to_command_requires_neutral_intent')
                    answer = self.processor.enter_control(Control.COMMAND_CONTROL,
                        initial_hover=Desired('position', position=self.processor.local_position(), yaw=self.processor.yaw))
                    if not answer.accepted:
                        raise ValueError(answer.reason)
                    self.rc_input.revoke('explicit_command_handoff')
                    self.shaper.reset()
                    self.command_request_id = self.request_context
                    self.event('setup_completed', control_state='COMMAND_CONTROL', native_mode=self.state.mode)
                    return
                if self.native.flying is False:
                    # AP may update home while arming; bind only the current frame.
                    self.processor.home = self.processor.local_position()
                    p = self.processor.home
                    initial_hover = None
                    target = Setpoint('local', position=(p[0], p[1], p[2]+self.takeoff_height), yaw=0.0)
                else:
                    # A new airborne request is a hold here, not a second takeoff
                    # or a replay of the interrupted mission. Keep one reference
                    # through warmup and activation, including its observed yaw.
                    initial_hover = Desired('position', position=self.processor.local_position(),
                                            yaw=self.processor.yaw)
                    target = Setpoint('local', position=initial_hover.position, yaw=initial_hover.yaw)
                self.warmup_target = target
                self.revoked = False
                if self.native.external_mode == 'OFFBOARD':
                    if self.native.flying is False:
                        # PX4's final magnetic alignment happens after climbing.
                        # Its native takeoff owns yaw reset handling before Offboard.
                        self.native.request('takeoff', self.warmup_target.position[2])
                        self.operation = dict(stage='takeoff', deadline=self.operation_time()+35, ack=False)
                    elif self.native.ready_external:
                        self.operation = dict(stage='warmup', started=self.operation_time(), deadline=self.operation_time()+10, ack=False)
                    else:
                        raise ValueError('external_heading_alignment_not_ready')
                else:
                    self.native.request('mode', 'OFFBOARD')
                    self.operation = dict(stage='external', deadline=self.operation_time()+10, ack=False)
                self.operation['initial_hover'] = initial_hover
                self.operation['requested_mode'] = msg.control_state
                self.shaper.reset()
                self.event('takeover_reference', airborne=initial_hover is not None,
                           position_enu_m=target.position, yaw_enu_rad=target.yaw,
                           source_boot_ns=self.state.header.stamp.sec * 10**9 + self.state.header.stamp.nanosec,
                           native_generation=self.native_generation)
            elif msg.cmd == UAVSetup.ARMING:
                if not msg.arming and self.native.flying is not False:
                    raise ValueError('ordinary_disarm_requires_confirmed_ground_state')
                if msg.arming and not self.state.odom_valid:
                    raise ValueError('arming_requires_valid_state')
                if self.state.armed == msg.arming:
                    self.event('setup_completed', cmd=int(msg.cmd), armed=bool(msg.arming), unchanged=True)
                    return
                self.native.request('arm', bool(msg.arming))
                self.operation = dict(stage='simple', action='arm', value=bool(msg.arming), deadline=self.operation_time()+10, ack=False)
            elif msg.cmd == UAVSetup.SET_PX4_MODE:
                if msg.px4_mode == 'OFFBOARD':
                    raise ValueError('use_COMMAND_CONTROL_for_warmed_external_mode')
                if msg.px4_mode == 'BRAKE' and (self.native.external_mode != 'GUIDED'
                        or not self.state.armed or not self.state.odom_valid
                        or self.native.flying is not True or self.native.failed):
                    raise ValueError('BRAKE_requires_arducopter_airborne_valid_state')
                if msg.px4_mode not in ('POSCTL', 'AUTO.LOITER', 'AUTO.LAND', 'AUTO.RTL', 'BRAKE'):
                    raise ValueError('native_mode_not_implemented')
                self.native.request('mode', msg.px4_mode)
                if self.processor.control_state == Control.RC_POS_CONTROL:
                    self.rc_input.revoke('explicit_native_mode_exit')
                    self.revoked = True
                    self.event('control_revoked', reason='explicit_native_mode_exit', requested_mode=msg.px4_mode)
                self.processor.enter_control(Control.INIT)
                self.shaper.reset()
                self.operation = dict(stage='simple', action='mode', value=msg.px4_mode, deadline=self.operation_time()+10, ack=False)
            else:
                raise ValueError('setup_command_not_implemented')
            self.operation['request_id'] = self.request_context
            self.event('setup_received', cmd=int(msg.cmd), stage=self.operation['stage'])
        except (ValueError, RuntimeError) as error:
            self.event('setup_rejected', error=True, cmd=int(msg.cmd), reason=str(error))

    def on_command(self, msg):
        try:
            stamp = self.input_stamp(msg.header)
            if self.revoked or self.operation is not None:
                raise ValueError('control_not_active_or_transition_pending')
            if stamp < self.last_command_stamp:
                raise ValueError('out_of_order_command_stamp')
            if msg.agent_cmd == Cmd.MOVE and msg.command_id <= self.last_move_id:
                raise ValueError('command_id_not_increasing')
            reason = self.native.supports(msg)
            if reason:
                raise ValueError(reason)
            answer = self.processor.accept(msg)
            if answer.stop_control is not None:
                self.stop_pub.publish(Bool(data=answer.stop_control))
            if not answer.accepted:
                raise ValueError(answer.reason)
            self.last_command_stamp = stamp
            if msg.agent_cmd == Cmd.MOVE:
                self.last_move_id = msg.command_id
            self.command_request_id = self.request_context
            self.event('command_accepted', command_id=int(msg.command_id), agent_cmd=int(msg.agent_cmd))
        except (ValueError, RuntimeError) as error:
            self.event('command_rejected', error=True, command_id=int(msg.command_id), reason=str(error))

    def activate(self):
        request_id = (self.operation or {}).get('request_id', self.request_context)
        if not self.native.ready_external:
            raise ValueError('external_heading_alignment_not_ready')
        requested = (self.operation or {}).get('requested_mode', 'COMMAND_CONTROL')
        if requested == 'RC_POS_CONTROL':
            rc_answer = self.rc_input.activate(now_ns=time.monotonic_ns(), operation_ns=self.operation_ns(),
                                               position=self.processor.local_position(),
                                               yaw=self.processor.yaw, setup_id=request_id)
            if not rc_answer.get('accepted'):
                raise ValueError(rc_answer.get('reason', 'rc_activate_rejected'))
            answer = self.processor.enter_control(Control.RC_POS_CONTROL)
            if not answer.accepted:
                raise ValueError(answer.reason)
            self.operation = self.warmup_target = None
            self.revoked = False
            self.shaper.reset()
            self.command_request_id = request_id
            self.event('setup_completed', control_state='RC_POS_CONTROL', native_mode=self.state.mode,
                       request_id=request_id, rc_stream_bound=True, rc_stream_id=self.rc_input.stream_id,
                       publisher_gid=self.rc_input.owner_gid.hex(),
                       position_enu_m=self.rc_input.target['position'], yaw_enu_rad=self.rc_input.target['yaw'])
            return
        answer = self.processor.enter_control(Control.COMMAND_CONTROL,
                                              initial_hover=(self.operation or {}).get('initial_hover'))
        if not answer.accepted:
            raise ValueError(answer.reason)
        self.operation = self.warmup_target = None
        self.revoked = False
        self.event('setup_completed', control_state='COMMAND_CONTROL', native_mode=self.state.mode, request_id=request_id)

    def advance(self):
        op = self.operation
        if self.operation_time() > op['deadline']:
            raise ValueError('setup_observed_completion_timeout')
        if op['stage'] == 'warmup':
            if self.operation_time() - op['started'] >= 1.0:
                self.native.request('mode', 'OFFBOARD')
                op.update(stage='external', ack=False, deadline=self.operation_time()+10)
            return
        if not op['ack']:
            response = self.native.poll_request()
            if response is None:
                return
            accepted, reason = response
            self.event('native_ack', accepted=accepted, reason=reason, stage=op['stage'])
            if not accepted:
                raise ValueError(reason)
            op['ack'] = True
        if op['stage'] == 'external' and self.state.mode == self.native.external_mode:
            if self.native.external_mode != 'OFFBOARD' and self.native.flying is False:
                self.native.request('takeoff', self.warmup_target.position[2])
                op.update(stage='takeoff', ack=False, deadline=self.operation_time()+25)
            elif self.native.flying is not None:
                self.activate()
        elif op['stage'] == 'takeoff':
            ready = (self.state.odom_valid and self.native.flying is True and self.native.ready_external
                     and self.state.position[2] >= self.warmup_target.position[2]-0.3)
            if self.native.external_mode == 'GUIDED':
                # AP can publish a last takeoff yaw reset just after first
                # crossing the height threshold. Keep native takeoff ownership
                # until its observed velocity has settled continuously.
                ready = ready and math.hypot(*self.state.velocity) <= .3
                if not ready:
                    op.pop('takeoff_stable_since', None)
                else:
                    op.setdefault('takeoff_stable_since', self.operation_time())
                    ready = self.operation_time()-op['takeoff_stable_since'] >= .5
            if not ready or self.operation_time() < op.get('settled_after', 0):
                return
            if self.native.external_mode == 'OFFBOARD':
                op.update(stage='warmup', started=self.operation_time(), deadline=self.operation_time()+10, ack=False)
            else:
                self.activate()
        elif op['stage'] == 'simple':
            confirmed = (self.state.armed == op['value'] if op['action'] == 'arm'
                         else self.state.mode == self.native.mode_name(op['value']))
            if confirmed:
                self.event('setup_completed', action=op['action'], value=op['value'], native_mode=self.state.mode)
                self.operation = None
        elif op['stage'] == 'land' and self.state.mode == self.native.mode_name('AUTO.LAND'):
            self.event('land_mode_confirmed')
            self.operation = None

    def tick(self):
        if self.rc_receiver is not None:
            try:
                for _ in range(10):
                    sample = self.rc_take.take(self.rc_sub)
                    if sample is None:
                        break
                    self.on_rc(*sample)
            except (ValueError, RuntimeError) as error:
                self.revoke(str(error))
        for rejected in self.native.consume_rejections():
            self.event('native_input_rejected', error=True, **rejected)
        try:
            self.state = self.native.state(self.uav_id)
        except (ValueError, RuntimeError, OverflowError) as error:
            self.state.connected = self.state.odom_valid = False
            if not self.revoked:
                self.revoke(str(error))
        else:
            try:
                if self.scene is not None and not self.scene_native_endpoints and self.state.connected and self.state.odom_valid:
                    self.scene_native_endpoints=self.scene_endpoints()
                    self.event('scene_native_sources_bound',scene_epoch=self.scene.epoch,
                               native_endpoints=self.scene_native_endpoints)
                if self.scene_recovery is not None:
                    self.supervise_recovery()
                self.drive()
            except (ValueError, RuntimeError, OverflowError) as error:
                # A rejected setup/ACK does not mean the transport disconnected.
                if not self.revoked or self.operation is not None:
                    self.revoke(str(error))
        self.state_pub.publish(self.state)
        control = Control(uav_id=self.uav_id, control_state=self.processor.control_state,
                          pos_controller=Control.PX4_ORIGIN, failsafe=self.revoked or self.processor.failsafe)
        control.header = deepcopy(self.state.header)
        self.control_pub.publish(control)
        self.sequence += 1
        received = self.native.state_received_monotonic
        self.session_pub.publish(SessionState(version=RunSession.VERSION, run_id=self.session.run_id,
            control_epoch=self.session.epoch, sequence=self.sequence, last_request_id=self.session.last_request,
            native_generation=self.native.generation, source_clock='fc_boot',
            source_received_valid=received is not None, source_received_monotonic_s=received or 0.0,
            published_monotonic_s=self.wall(), state=self.state, control=control))

    def drive(self):
        active = self.processor.control_state != Control.INIT or self.operation is not None
        if active:
            if self.scene is not None:
                self.scene_supervise()
            self.operation_time()  # A clock fault must also stop cached/ongoing output.
        if self.native.generation != self.native_generation:
            self.native_generation = self.native.generation
            kinds = self.native.consume_resets()
            self.event('native_reset_observed', kinds=sorted(kinds), active=active)
            arm_home_change = (kinds == {'home'}
                and self.operation is not None and self.operation.get('action') == 'arm'
                and self.operation.get('value') is True and self.native.flying is False
                and self.processor.control_state == Control.INIT)
            takeoff_yaw_alignment = (kinds == {'yaw'} and self.operation is not None
                and self.operation['stage'] == 'takeoff' and self.processor.control_state == Control.INIT)
            if takeoff_yaw_alignment:
                self.operation['settled_after'] = self.operation_time()+0.5
                self.operation.pop('takeoff_stable_since', None)
            if active and not (arm_home_change or takeoff_yaw_alignment):
                raise ValueError('native_clock_or_origin_reset')
        if not active and not self.state.odom_valid:
            return  # Publish invalid startup state; do not feed synthetic pose to the processor.
        if self.processor.control_state == Control.RC_POS_CONTROL and (not self.state.armed or not self.state.odom_valid):
            raise ValueError('rc_armed_or_navigation_lost')
        self.processor.update_state(self.state)
        if active and not self.state.connected:
            raise ValueError('native_state_stale')
        observing_operator_hold = (self.revoked
            and self.processor.control_state == Control.INIT and self.native.external_mode == 'OFFBOARD'
            and self.operation is not None and self.operation.get('stage')=='simple'
            and self.operation.get('action')=='mode' and self.operation.get('value')=='AUTO.LOITER')
        if active and self.native.failed and not observing_operator_hold:
            raise ValueError('native_failsafe_control_released')
        if self.operation is not None:
            self.advance()
        elif self.processor.control_state == Control.COMMAND_CONTROL and self.state.mode != self.native.external_mode:
            raise ValueError('external_mode_left_no_automatic_reacquisition')
        elif self.processor.control_state == Control.COMMAND_CONTROL and not self.native.ready_external:
            raise ValueError('external_heading_alignment_lost')
        elif self.processor.control_state == Control.RC_POS_CONTROL:
            if self.state.mode != self.native.external_mode:
                raise ValueError('external_mode_left_no_automatic_reacquisition')
            if not self.native.ready_external:
                raise ValueError('external_heading_alignment_lost')
            scene_running = self.scene is None or (self.scene_hold is None and self.scene_recovery is None)
            rc_out = self.rc_input.step(now_ns=time.monotonic_ns(), operation_ns=self.operation_ns(), running=scene_running,
                                        operation_mode='running' if scene_running else 'paused')
            if self.rc_input.state == 'REVOKED':
                self.processor.clear_rc_desired()
                raise ValueError('rc_input_revoked:' + str(self.rc_input.last_rejection))
            if rc_out is not None:
                self.event('rc_integrated', **rc_out, operation_ns=self.rc_input.last_step_ns,
                           produced_monotonic_ns=self.rc_input.produced_ns,
                           received_monotonic_ns=self.rc_input.received_ns,
                           serviced_monotonic_ns=time.monotonic_ns(),
                           publisher_gid=self.rc_input.owner_gid.hex(), native_generation=self.native_generation,
                           native_mode=self.state.mode)
                rc_answer = self.processor.set_rc_desired(Desired('position', position=tuple(rc_out['position']),
                                                                  yaw=float(rc_out['yaw'])))
                if not rc_answer.accepted:
                    raise ValueError(rc_answer.reason)
        rc_age = 0.0
        if self.processor.control_state == Control.RC_POS_CONTROL and self.rc_input is not None \
                and self.rc_input.received_ns is not None:
            rc_age = max(0.0, (time.monotonic_ns() - self.rc_input.received_ns) / 1_000_000_000)
        command = self.processor.command
        capture_mixed_body = (command.agent_cmd == Cmd.MOVE and command.move_mode == Cmd.XY_VEL_Z_POS_BODY
                              and not command.yaw_rate_mode and self.processor.body_reference is None)
        reference = self.processor.step(rc_age=rc_age)
        target = self.shaper.shape(reference, self.processor.local_position())
        if capture_mixed_body and reference is not None and reference is self.processor.body_reference:
            # Capture is a resolved reference, not proof of native publication/ACK.
            # It happens at the actual first step, even if output pacing sends later.
            q = self.processor.state.attitude_q
            header = self.processor.state.header.stamp
            self.event('mixed_body_reference_captured', command_id=int(command.command_id),
                source_boot_ns=int(header.sec)*1_000_000_000+int(header.nanosec),
                source_position=list(self.processor.position), source_yaw=float(self.processor.yaw),
                source_quaternion_wxyz=[float(v) for v in (q.w,q.x,q.y,q.z)],
                reference_position=list(reference.position), reference_velocity=list(reference.velocity),
                reference_yaw=float(reference.yaw),
                shaped_position=[None if v is None else float(v) for v in target.position],
                shaped_velocity=[None if v is None else float(v) for v in target.velocity])
        if target is not None and target.kind == 'land':
            if self.state.armed and self.state.mode != self.native.mode_name('AUTO.LAND') and self.operation is None:
                self.native.request('land')
                self.operation = dict(stage='land', deadline=self.operation_time()+10, ack=False, request_id=self.command_request_id)
        else:
            # AP native takeoff must not be interrupted by a position stream.
            if self.operation is not None and self.operation['stage'] in ('warmup', 'external') and self.native.external_mode == 'OFFBOARD':
                target = self.warmup_target
            if target is not None and self.wall() - self.last_output >= self.output_period:
                self.native.send(target)
                self.last_output = self.wall()

    def destroy_node(self):
        if self.rc_receiver is not None:
            self.rc_receiver.destroy_node()
        self.native.cancel_request()
        self.session.close()
        return super().destroy_node()


def main():
    from rclpy.signals import SignalHandlerOptions
    stopping = False
    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True
    previous = {number: signal.signal(number, request_stop) for number in (signal.SIGINT, signal.SIGTERM)}
    node = None
    try:
        # Finish the current callback before destroying its ROS context. The
        # default asynchronous signal shutdown can invalidate a live publisher.
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = ControlNode()
        while not stopping and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if node is not None:
                node.destroy_node()
        finally:
            if rclpy.ok():
                rclpy.shutdown()
            for number, handler in previous.items():
                signal.signal(number, handler)


if __name__ == '__main__':
    main()
