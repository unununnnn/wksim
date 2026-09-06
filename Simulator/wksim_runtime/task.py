"""One bounded position task; every command uses public Prometheus messages.

The runtime also observes PX4's native pre-arm health flag read-only. Position
validity alone does not mean that PX4's current mode is ready to arm.
"""
import json
import math
import time


def state_time(state):
    return state.header.stamp.sec + state.header.stamp.nanosec / 1e9


def valid_state(state, uav_id=1):
    if type(uav_id) is not int:
        raise TypeError('uav_id must be an int')
    if not 1 <= uav_id <= 255:
        raise ValueError('uav_id must be in 1..255')
    return bool(state is not None and type(state.uav_id) is int and state.uav_id == uav_id and state.connected and
                state.odom_valid and state.header.frame_id == 'map' and state_time(state) > 0
                and all(math.isfinite(x) for x in (*state.position, *state.velocity, *state.attitude)))


def grounded(state, uav_id=1):
    # Public UAVState has no landed bit: corroborate this with model truth in runtime.
    return valid_state(state, uav_id) and not state.armed and abs(state.position[2]) < 0.3


class Task:
    uav_id, use_sim_time = 1, False

    @property
    def topic_root(self):
        return f'/uav{self.uav_id}/prometheus/'

    def __init__(self, directory, health, phase, flight_stack, *, run_id=None, protocol='legacy_v1', restart_control=None,
                 uav_id=1, use_sim_time=False, scene_epoch=None):
        valid_state(None, uav_id)  # Validate before importing ROS or creating resources.
        if type(use_sim_time) is not bool:
            raise TypeError('use_sim_time must be a bool')
        if scene_epoch is not None and (not use_sim_time or protocol != 'session_v1'):
            raise ValueError('Scene pause requires use_sim_time and session_v1')
        self.scene_lease = None
        self._scene_frozen_stamp = None
        self._scene_phase = None
        self._session_received = 0.0
        if scene_epoch is not None:
            from prometheus_control.scene import SceneLease
            self.scene_lease = SceneLease(run_id, scene_epoch)
        self.uav_id, self.use_sim_time = uav_id, use_sim_time
        self._last_ros_ns = None
        import rclpy
        from prometheus_msgs.msg import UAVCommand, UAVSetup, UAVState, UAVControlState, TextInfo
        from rosidl_runtime_py.convert import message_to_ordereddict
        self.ros, self.convert = rclpy, message_to_ordereddict
        self.Cmd, self.Setup = UAVCommand, UAVSetup
        self.health, self.phase = health, phase
        self.flight_stack = flight_stack
        self.run_id, self.protocol, self.epoch = run_id, protocol, None
        self.restart_control = restart_control
        self.retired_epochs, self.restarts = set(), []
        self.request_id, self.session_sequence = 0, 0
        self.native_generation = None
        self.pending_request_id = None
        self.envelopes = []
        self.native_health = None
        self.health_received = self.health_advanced = 0.0
        self.latest, self.received, self.events, self.sent = {}, {}, [], []
        self.error = None
        self.active = False
        self.last_stamp = None
        self.started = self.advanced_at = time.monotonic()
        self.log = (directory / 'prometheus.jsonl').open('x', encoding='utf-8', buffering=1)
        from rclpy.parameter import Parameter
        self.node = rclpy.create_node('wksim_position_task' if uav_id == 1 else f'wksim_position_task_uav{uav_id}',
            **({'parameter_overrides': [Parameter('use_sim_time', value=True)]} if use_sim_time else {}))
        if use_sim_time:
            from rclpy.clock import JumpThreshold
            from rclpy.duration import Duration
            self._clock_jump = self.node.get_clock().create_jump_callback(
                JumpThreshold(min_forward=None, min_backward=Duration(nanoseconds=-1), on_clock_change=True),
                post_callback=self._on_clock_jump)
        root = self.topic_root
        types = (('state', UAVState), ('control_state', UAVControlState), ('text_info', TextInfo))
        self.subscriptions = [self.node.create_subscription(cls, root + key,
            lambda msg, key=key: self.receive(key, msg), 10) for key, cls in (
                types if protocol == 'legacy_v1' else (('text_info', TextInfo),))]
        if self.scene_lease is not None:
            from std_msgs.msg import String
            self.subscriptions.append(self.node.create_subscription(
                String, '/wksim/scene/lifecycle', self.receive_scene, 10))
        if protocol == 'session_v1':
            from wksim_msgs.msg import SetupRequest, CommandRequest, SessionState
            self.SetupRequest, self.CommandRequest = SetupRequest, CommandRequest
            self.subscriptions.append(self.node.create_subscription(SessionState, root + 'v2/state', self.receive_session, 10))
            self.setup_pub = self.node.create_publisher(SetupRequest, root + 'v2/setup', 1)
            self.command_pub = self.node.create_publisher(CommandRequest, root + 'v2/command', 1)
        else:
            self.setup_pub = self.node.create_publisher(UAVSetup, root + 'setup', 1)
            self.command_pub = self.node.create_publisher(UAVCommand, root + 'command', 1)
        if flight_stack == 'px4':
            from px4_msgs.msg import VehicleStatus
            from rclpy.qos import QoSProfile, ReliabilityPolicy
            from prometheus_control.frames import topic
            self.subscriptions.append(self.node.create_subscription(VehicleStatus,
                topic('/wksim_px4_21', 'out', 'vehicle_status', VehicleStatus), self.receive_health,
                QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)))

    def receive_scene(self, msg):
        self.log.write(json.dumps(dict(wall=time.monotonic()-self.started,
            topic='/wksim/scene/lifecycle', message=self.convert(msg))) + '\n')
        try:
            if self.scene_lease.accept(msg.data):
                self.scene_status()
        except ValueError as exc:
            self.log.write(json.dumps(dict(scene_rejected=str(exc)))+'\n')
            if self.scene_lease.error is not None:
                self.error = f'Scene lifecycle failure: {exc}'

    def scene_status(self):
        if getattr(self, 'scene_lease', None) is None:
            return None
        if not self.active and self.scene_lease.value is None:
            return None
        try:
            status = self.scene_lease.check()
        except ValueError as exc:
            self.error = f'Scene lifecycle failure: {exc}'
            return None
        phase = status['phase']
        if phase in ('faulted', 'stopped'):
            self.error = 'Scene lifecycle ' + phase
        if phase in ('paused', 'stepping', 'resuming') and self._scene_frozen_stamp is None:
            self._scene_frozen_stamp = self.last_stamp
        if phase != self._scene_phase:
            self.log.write(json.dumps(dict(scene_event=phase, sequence=status['sequence'],
                tick=status['tick'], ros_time_ns=self.node.get_clock().now().nanoseconds)) + '\n')
            self._scene_phase = phase
        return status

    def receive_session(self, msg):
        now = time.monotonic()
        self.log.write(json.dumps(dict(wall=now-self.started, topic=self.topic_root + 'v2/state',
                                       message=self.convert(msg))) + '\n')
        if (type(getattr(msg.state, 'uav_id', None)) is not int or msg.state.uav_id != self.uav_id
                or type(getattr(msg.control, 'uav_id', None)) is not int or msg.control.uav_id != self.uav_id):
            return
        if (msg.version != 1 or msg.run_id != self.run_id or len(msg.control_epoch) != 32
                or msg.control_epoch in self.retired_epochs):
            return
        if self.epoch is not None and msg.control_epoch != self.epoch:
            self.error = 'Control epoch changed; explicit new task request required'
            return
        if msg.sequence <= self.session_sequence:
            return
        scene = self.scene_status()
        if getattr(self, 'scene_lease', None) is not None and scene is None:
            return
        held = scene is not None and scene['phase'] in ('paused', 'stepping', 'resuming')
        if scene is not None and self.active and not valid_state(msg.state, self.uav_id):
            self.error = 'Public state invalid or disconnected during scene task'
            return
        if scene is not None and self.active and self.last_stamp is not None and state_time(msg.state) < self.last_stamp:
            self.error = 'Public state boot clock moved backwards'
            return
        if (scene is not None and self._scene_frozen_stamp is not None
                and self.native_generation is not None and msg.native_generation != self.native_generation):
            self.error = 'Native generation changed; explicit new task request required'
            return
        if (not math.isfinite(msg.published_monotonic_s) or not 0 <= now-msg.published_monotonic_s <= 2
                or not msg.source_received_valid or not math.isfinite(msg.source_received_monotonic_s)
                or now < msg.source_received_monotonic_s):
            return
        self._session_received = now
        if not held and now-msg.source_received_monotonic_s > 2:
            return
        if (scene is not None and scene['phase'] in ('paused', 'stepping')
                and msg.state.header.stamp.sec*10**9+msg.state.header.stamp.nanosec >
                    (scene['tick']+(4 if scene['phase'] == 'stepping' else 0))*1000000):
            self.error = 'Public state boot clock exceeds scene boundary'
            return
        self.epoch, self.session_sequence = msg.control_epoch, msg.sequence
        self.request_id = max(self.request_id, msg.last_request_id)
        self.native_generation = msg.native_generation
        self.receive('state', msg.state)
        self.receive('control_state', msg.control)
        if held and self._scene_frozen_stamp is not None:
            self._scene_frozen_stamp = max(self._scene_frozen_stamp, state_time(msg.state))
        elif scene is not None and scene['phase'] == 'running' and self._scene_frozen_stamp is not None:
            if state_time(msg.state) > self._scene_frozen_stamp and self.fresh():
                self._scene_frozen_stamp = None

    def receive_health(self, message):
        now = time.monotonic()
        if self.native_health is not None and message.timestamp <= self.native_health.timestamp:
            return
        if self.native_health is None or message.timestamp > self.native_health.timestamp:
            self.health_advanced = now
        self.native_health, self.health_received = message, now
        self.log.write(json.dumps(dict(wall=now-self.started, topic='/wksim_px4_21/fmu/out/vehicle_status_v1',
                                       message=self.convert(message), observation_only=True)) + '\n')

    def arm_ready(self, after):
        msg = self.native_health
        now = time.monotonic()
        return bool(msg is not None and msg.system_id == 22 and msg.timestamp > 0
                    and msg.pre_flight_checks_pass and msg.nav_state == msg.NAVIGATION_STATE_AUTO_LOITER
                    and self.health_received > after and 0 <= now-self.health_received <= 2
                    and 0 <= now-self.health_advanced <= 2)

    def receive(self, key, msg):
        if key in ('state', 'control_state') and (type(getattr(msg, 'uav_id', None)) is not int or msg.uav_id != self.uav_id):
            return
        now = time.monotonic()
        self.latest[key], self.received[key] = msg, now
        self.log.write(json.dumps(dict(wall=now - self.started, topic=self.topic_root + key,
                                       message=self.convert(msg))) + '\n')
        if key == 'state':
            stamp = state_time(msg)
            if self.last_stamp is not None and stamp < self.last_stamp and self.active:
                self.error = 'Public state boot clock moved backwards'
            if self.last_stamp is None or stamp > self.last_stamp:
                self.advanced_at = now
            self.last_stamp = stamp
        if key == 'text_info':
            try:
                event = json.loads(msg.message)
                if getattr(self, 'protocol', 'legacy_v1') == 'session_v1' and (
                        event.get('run_id') != self.run_id or event.get('control_epoch') != self.epoch):
                    return
                self.events.append(event)
                rejected_own_request = (getattr(self, 'protocol', 'legacy_v1') == 'legacy_v1' or
                    (self.pending_request_id is not None and event.get('request_id') == self.pending_request_id
                     and event.get('requested_run_id', self.run_id) == self.run_id
                     and event.get('requested_epoch', self.epoch) == self.epoch))
                if self.active and event.get('event') == 'control_revoked':
                    self.on_control_revoked(event)
                elif self.active and event.get('event') in ('setup_rejected', 'command_rejected') and rejected_own_request:
                    self.error = f'Product control failure: {event}'
            except (ValueError, AttributeError):
                self.error = 'Malformed product event'

    def on_control_revoked(self, event):
        self.error = f'Product control failure: {event}'

    @property
    def state(self):
        return self.latest.get('state')

    def fresh(self):
        now = time.monotonic()
        if getattr(self, 'scene_lease', None) is not None:
            scene = self.scene_status()
            if scene is None:
                return False
            if scene is not None and (scene['phase'] in ('paused', 'stepping', 'resuming')
                                      or self._scene_frozen_stamp is not None):
                return (not self.error and valid_state(self.state, self.uav_id)
                        and 0 <= now-self._session_received <= 2)
        return (valid_state(self.state, self.uav_id) and now - self.received.get('state', 0) <= 2
                and now - self.advanced_at <= 2)

    def pump(self):
        while True:
            self.health()
            self.ros.spin_once(self.node, timeout_sec=0.02)
            scene = self.scene_status()
            if self.use_sim_time:
                self.task_time()
            if self.error:
                raise RuntimeError(self.error)
            if self.active and not self.fresh():
                raise RuntimeError('Public state invalid, disconnected, or stale')
            if scene is None or (scene['phase'] == 'running' and self._scene_frozen_stamp is None):
                return

    def _on_clock_jump(self, jump):
        self.error = 'Task ROS clock reset, moved backwards, or changed source'

    def task_time(self):
        """Seconds: node ROS time when enabled, otherwise monotonic wall time.

        Zero is the standard ROS clock's not-yet-published value. Backward jumps
        and clock-source changes latch a fatal error; no rebasing or recovery.
        The supervisor health callback retains the independent wall-clock bound.
        """
        if not self.use_sim_time:
            return time.monotonic()
        if self.error:
            raise RuntimeError(self.error)
        now = self.node.get_clock().now().nanoseconds
        if self._last_ros_ns is not None and now < self._last_ros_ns:
            self._on_clock_jump(None)
            raise RuntimeError(self.error)
        self._last_ros_ns = now
        return now / 1e9

    def wait(self, label, predicate, timeout=20):
        deadline = self.task_time() + timeout
        while True:
            self.pump()
            if predicate():
                self.phase(label)
                return
            if self.task_time() >= deadline:
                raise TimeoutError(label)

    def send(self, msg, label, timeout=10):
        start = len(self.events)
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        self.sent.append(self.convert(msg))
        self.log.write(json.dumps(dict(wall=time.monotonic() - self.started,
            **{('published' if self.protocol == 'legacy_v1' else 'public_payload'): type(msg).__name__},
            message=self.sent[-1])) + '\n')
        setup = isinstance(msg, self.Setup)
        outgoing = msg
        expected_request_id = None
        if self.protocol == 'session_v1':
            if self.epoch is None:
                raise RuntimeError('No current control epoch observed')
            self.request_id += 1
            cls = self.SetupRequest if setup else self.CommandRequest
            outgoing = cls(version=1, run_id=self.run_id, control_epoch=self.epoch, request_id=self.request_id,
                           **{('setup' if setup else 'command'): msg})
            self.envelopes.append(self.convert(outgoing))
            self.log.write(json.dumps(dict(wall=time.monotonic()-self.started, published=cls.__name__,
                                           message=self.envelopes[-1], request_envelope=True)) + '\n')
            self.pending_request_id = self.request_id
            expected_request_id = self.request_id
        (self.setup_pub if setup else self.command_pub).publish(outgoing)
        def acknowledged():
            return any(e.get('event') == ('setup_completed' if setup else 'command_accepted')
                       and (setup or e.get('command_id') == msg.command_id)
                       and (self.protocol == 'legacy_v1' or e.get('request_id') == expected_request_id)
                       for e in self.events[start:])
        try:
            self.wait(label, acknowledged, timeout)
        finally:
            self.pending_request_id = None

    def dwell(self, label, predicate, seconds):
        clock = self.task_time if self.use_sim_time else lambda: state_time(self.state)
        start = clock()
        deadline = self.task_time() + 15
        while clock() - start < seconds:
            self.pump()
            if not predicate():
                raise RuntimeError(label + ': integration threshold exceeded')
            if self.task_time() >= deadline:
                raise TimeoutError(label + (': ROS clock dwell timeout' if self.use_sim_time else ': boot clock dwell timeout'))
        self.phase(label)

    def restart_on_ground(self):
        """Explicit configured transition, never recovery after an unexpected loss."""
        if self.protocol != 'session_v1' or not self.fresh() or not grounded(self.state, self.uav_id) or self.epoch is None:
            raise RuntimeError('Control restart requires a current disarmed ground session')
        old_epoch = self.epoch
        self.retired_epochs.add(old_epoch)
        self.active = False
        # The supervisor corroborates this still-current ground state with physics
        # before retiring the process. Clear it only after that ownership transition.
        record = self.restart_control()
        self.epoch, self.request_id, self.session_sequence = None, 0, 0
        self.latest, self.received, self.last_stamp = {}, {}, None
        self.wait('new_control_epoch_ready', lambda: self.fresh() and grounded(self.state, self.uav_id)
                  and self.epoch is not None and self.epoch != old_epoch
                  and self.setup_pub.get_subscription_count() == 1
                  and self.command_pub.get_subscription_count() == 1, 25)
        record.update(old_epoch=old_epoch, new_epoch=self.epoch)
        self.restarts.append(record)
        self.active = True

    def execute(self):
        self.wait('public_control_ready', lambda: self.fresh() and
                  self.setup_pub.get_subscription_count() == 1 and
                  self.command_pub.get_subscription_count() == 1, 55)
        if not grounded(self.state, self.uav_id):
            raise RuntimeError('Task requires initial disarmed ground state')
        self.active = True
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
        if self.restart_control is not None:
            self.restart_on_ground()
            # This is a NEW user-configured task request, not replay of the old envelope.
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'new_epoch_hold_ready')
        if self.flight_stack == 'px4':
            mode_completed_at = time.monotonic()
            self.wait('native_prearm_health_ready', lambda: self.arm_ready(mode_completed_at), 55)
        self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
        self.wait('armed', lambda: self.state.armed)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'task_control_ready', 40)
        self.wait('takeoff_reached', lambda: self.state.position[2] >= 2.5, 25)
        self.dwell('hold_completed', lambda: abs(self.state.position[2] - 3) <= 0.6
                   and max(abs(x) for x in self.state.attitude[:2]) <= 0.35, 5)
        self.send(self.Cmd(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS, command_id=1,
                           position_ref=[2.0, 3.0, 3.0], yaw_ref=0.0), 'waypoint_accepted')
        def at_waypoint():
            return math.dist(self.state.position, [2, 3, 3]) <= 0.5 and math.hypot(*self.state.velocity) <= 0.5
        self.wait('waypoint_reached', at_waypoint)
        self.dwell('waypoint_completed', at_waypoint, 2)
        self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=2), 'land_accepted')
        self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id), 30)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
        completed_at = time.monotonic()
        self.wait('normal_stop_ready', lambda: self.fresh() and grounded(self.state, self.uav_id)
                  and self.received.get('state', 0) > completed_at)

    def report(self):
        return dict(sent=self.sent, events=self.events, protocol=self.protocol, run_id=self.run_id,
                    control_epoch=self.epoch, request_envelopes=self.envelopes,
                    control_restarts=self.restarts,
                    final={key: self.convert(value) for key, value in self.latest.items() if key != 'text_info'})

    def close(self):
        self.node.destroy_node()
        self.log.close()
