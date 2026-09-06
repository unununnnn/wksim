"""Read-only DDS evidence around a bounded airborne physics pause.

This diagnoses the existing controller, without changing freshness, keepalive,
task requests or FC health checks. Four wall seconds is an observation window,
not a production timeout. A completed observation is not a completed flight.
"""
import json
import math
import time

from Simulator.wksim_core.worker import receive_worker

PAUSE_SECONDS = 4.0


class PauseProbeComplete(Exception):
    pass


class PauseProbe:
    def __init__(self, node, clock, directory, started, repeat_clock=False):
        import rclpy
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from rclpy.serialization import serialize_message
        from rosgraph_msgs.msg import Clock
        from wksim_msgs.msg import SessionState
        from prometheus_msgs.msg import TextInfo
        from px4_msgs.msg import VehicleStatus, VehicleLocalPosition, OffboardControlMode, TrajectorySetpoint
        from ardupilot_msgs.msg import WksimState, GlobalPosition
        from prometheus_control.frames import topic
        self.node, self.clock, self.started = node, clock, started
        self.ros, self.serialize = rclpy, serialize_message
        self.log = (directory/'pause-dds.jsonl').open('x', buffering=65536)
        self.repeat_log = (directory/'pause-clock-publications.jsonl').open('x')
        self.repeat_clock = repeat_clock
        self.sequence, self.last_clock_ns, self.phase = 0, None, 'flight'
        self.sessions, self.subscriptions = {}, []
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        channels = [('/clock', Clock), ('/ap/wksim/local_state_v1', WksimState),
                    ('/ap/cmd_gps_pose', GlobalPosition)]
        for uid in (1, 2):
            channels += [(f'/uav{uid}/prometheus/v2/state', SessionState),
                         (f'/uav{uid}/prometheus/text_info', TextInfo)]
        for direction, name, cls in (('out', 'vehicle_status', VehicleStatus),
                ('out', 'vehicle_local_position', VehicleLocalPosition),
                ('in', 'offboard_control_mode', OffboardControlMode),
                ('in', 'trajectory_setpoint', TrajectorySetpoint)):
            channels.append((topic('/wksim_px4_21', direction, name, cls), cls))
        for name, cls in channels:
            self.subscriptions.append(node.create_subscription(cls, name,
                lambda message, name=name: self.receive(name, message), qos))

    def receive(self, name, message):
        self.sequence += 1
        self.log.write(json.dumps(dict(sequence=self.sequence, wall=time.monotonic()-self.started,
            epoch=self.clock.epoch, tick=self.clock.tick, phase=self.phase, topic=name,
            cdr_hex=self.serialize(message).hex()), separators=(',', ':'))+'\n')
        if name == '/clock':
            self.last_clock_ns = message.clock.sec*10**9+message.clock.nanosec
        elif name.endswith('/v2/state'):
            self.sessions[message.state.uav_id] = message

    def pump(self):
        self.ros.spin_once(self.node, timeout_sec=0)

    def ready(self, run_id, states):
        if (self.clock.tick % 4 or not self.clock.synchronized or self.clock.phase != 'running'
                or self.clock.pending is not None or self.clock.last_barrier != self.clock.tick):
            return False
        now = time.monotonic()
        for stack, uid in (('arducopter', 1), ('px4', 2)):
            session = self.sessions.get(uid)
            if (session is None or session.version != 1 or session.run_id != run_id
                    or type(session.state.uav_id) is not int or session.state.uav_id != uid
                    or type(session.control.uav_id) is not int or session.control.uav_id != uid
                    or not session.source_received_valid
                    or any(not math.isfinite(stamp) or not 0 <= now-stamp <= 2 for stamp in
                           (session.source_received_monotonic_s, session.published_monotonic_s))
                    or not session.state.connected
                    or not session.state.odom_valid or not session.state.armed
                    or session.control.control_state != session.control.COMMAND_CONTROL
                    or session.control.failsafe or -states[stack][8] < 2.5):
                return False
        return True

    def observe(self, physics, children, publisher):
        request = dict(version=1, epoch=self.clock.epoch,
                       request_id=self.clock.last_request+1, action='pause')
        self.clock.request(request)
        self.phase = 'paused'
        def snapshot():
            return dict(authority=self.clock.snapshot(), ros_observed_ns=self.last_clock_ns,
                clock_publications=publisher.publications,
                paused_clock_republications=publisher.paused_republications,
                models={name:receive_worker(child, dict(version=1, epoch=self.clock.epoch, snapshot=True),
                        self.clock.epoch) for name, child in physics.workers.items()})
        before = snapshot()
        start = time.monotonic()
        next_repeat = start
        while time.monotonic()-start < PAUSE_SECONDS:
            if self.repeat_clock and time.monotonic() >= next_repeat:
                publisher.publish(self.clock)
                self.repeat_log.write(json.dumps(dict(epoch=self.clock.epoch, tick=self.clock.tick,
                    time_ns=self.clock.tick*self.clock.STEP_NS, wall=time.monotonic()-self.started,
                    publication=publisher.publications))+'\n')
                next_repeat = time.monotonic()+.1
            self.pump()
            for name, child, _ in children:
                # Task failure is an observation in this diagnostic only. The
                # normal flight supervisor still rejects every unexpected exit.
                if not name.endswith('-task') and child.poll() is not None:
                    raise RuntimeError(f'{name} exited during pause observation: {child.returncode}')
            time.sleep(.001)
        after = snapshot()
        errors = []
        if before['models'] != after['models'] or before['authority'] != after['authority']:
            errors.append('model_or_authority_changed')
        repeats = after['paused_clock_republications']-before['paused_clock_republications']
        if after['clock_publications']-before['clock_publications'] != repeats:
            errors.append('unexpected_new_clock_tick')
        if after['ros_observed_ns'] != self.clock.tick*self.clock.STEP_NS:
            errors.append('consumer_missing_exact_paused_boundary')
        self.log.flush()
        self.repeat_log.flush()
        return dict(status='failed' if errors else 'observed', verification_errors=errors,
                    repeat_paused_clock=self.repeat_clock, window_seconds=PAUSE_SECONDS, request=request,
                    before=before, after=after, started_wall=start-self.started,
                    finished_wall=time.monotonic()-self.started,
                    task_exit_codes={name:child.poll() for name, child, _ in children if name.endswith('-task')})

    def close(self):
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)
        self.log.close()
        self.repeat_log.close()
