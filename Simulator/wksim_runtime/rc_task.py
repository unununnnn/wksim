"""Bounded software-RC scenarios through the installed public control node."""
import json
import math
import time
import uuid
from std_msgs.msg import String
from rclpy.qos import QoSProfile, ReliabilityPolicy
from Simulator.wksim_control.rc_input import SOURCE, VERSION
from .task import Task, grounded

NEUTRAL = [1500, 1500, 1500, 1500, 1000, 1500, 1000, 1000]
SCENARIOS = ('movement', 'recenter', 'yaw', 'stream-stall', 'mode-out', 'new-takeover')


def physical(row):
    v = row['vehicle']
    w, x, y, z = v[12:16]
    yaw = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
    return dict(time=row['time'], position=(v[7], v[6], -v[8]),
                velocity=(v[4], v[3], -v[5]), yaw=math.pi/2-yaw)


class RCTask(Task):
    def __init__(self, directory, health, phase, flight_stack, *, scenario, boot_id, stream_id,
                 truth_path, **kwargs):
        if kwargs.get('protocol') != 'session_v1' or scenario not in SCENARIOS:
            raise ValueError('Select session_v1 and one RC scenario')
        self.scenario, self.boot_id, self.stream_id = scenario, boot_id, stream_id
        self.truth_path = truth_path
        self.rc_sequence, self.last_rc = 0, 0.
        self.channels = None
        self.expected_revocation = None
        self.rc_phases = []
        def record(label, **fields):
            rows = self.truth_rows()
            entry = dict(phase=label, monotonic_ns=time.monotonic_ns(),
                         truth=rows[-1] if rows else None, stream_id=self.stream_id, **fields)
            self.rc_phases.append(entry)
            self.log.write(json.dumps(dict(rc_phase=entry))+'\n')
            phase(label)
        super().__init__(directory, health, record, flight_stack, **kwargs)
        self.rc_pub = self.node.create_publisher(String, self.topic_root+'v2/rc_input',
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        from prometheus_control.rc_transport import RCTake
        from prometheus_control.frames import topic
        from prometheus_msgs.msg import TextInfo
        from wksim_msgs.msg import SessionState
        self.raw_take = RCTake()
        self.raw_node = self.ros.create_node('wksim_rc_audit_receiver')
        self.raw_log = (directory/'rc-dds.jsonl').open('x', buffering=1)
        channels = [(self.topic_root+'v2/rc_input', String), (self.topic_root+'text_info', TextInfo),
                    (self.topic_root+'v2/state', SessionState), (self.topic_root+'v2/setup', self.SetupRequest)]
        if flight_stack == 'arducopter':
            from ardupilot_msgs.msg import GlobalPosition, WksimState, Status
            channels += [('/ap/cmd_gps_pose', GlobalPosition), ('/ap/wksim/local_state_v1', WksimState), ('/ap/status', Status)]
        else:
            from px4_msgs.msg import TrajectorySetpoint, VehicleLocalPosition, VehicleStatus, VehicleControlMode, VehicleCommand
            channels += [(topic('/wksim_px4_21', direction, name, cls), cls) for direction, name, cls in (
                ('in', 'trajectory_setpoint', TrajectorySetpoint), ('out', 'vehicle_local_position', VehicleLocalPosition),
                ('in', 'vehicle_command', VehicleCommand),
                ('out', 'vehicle_status', VehicleStatus), ('out', 'vehicle_control_mode', VehicleControlMode))]
        self.raw_subs = [self.raw_node.create_subscription(cls, name, lambda _: None,
            QoSProfile(depth=500, reliability=ReliabilityPolicy.BEST_EFFORT)) for name, cls in channels]

    def truth_rows(self):
        rows = []
        with open(self.truth_path, encoding='utf-8') as handle:
            for line in handle:
                if line.endswith('\n'):
                    rows.append(physical(json.loads(line)))
        return rows

    def publish_rc(self, channels):
        self.rc_sequence += 1
        payload = dict(version=VERSION, source=SOURCE, run_id=self.run_id, control_epoch=self.epoch,
            uav_id=self.uav_id, boot_id=self.boot_id, stream_id=self.stream_id, sequence=self.rc_sequence,
            produced_monotonic_ns=time.monotonic_ns(), channels_us=list(channels))
        self.rc_pub.publish(String(data=json.dumps(payload)))
        self.log.write(json.dumps(dict(published='rc_frame', message=payload))+'\n')
        self.last_rc = time.monotonic()

    def pump(self):
        if self.channels is not None and self.epoch is not None and time.monotonic()-self.last_rc >= .02:
            self.publish_rc(self.channels)
        super().pump()
        if not self.active and self.expected_revocation is not None and not self.recovery_transport_fresh():
            raise RuntimeError('RC withdrawal observation lost native transport')
        for subscription in self.raw_subs:
            for _ in range(200):
                sample = self.raw_take.take(subscription)
                if sample is None:
                    break
                msg, info = sample
                self.raw_log.write(json.dumps(dict(topic=subscription.topic_name,
                    type=type(msg).__module__.split('.')[0]+'/msg/'+type(msg).__name__,
                    monotonic_ns=time.monotonic_ns(), cdr_hex=info.cdr_hex,
                    publisher_gid=info.publisher_gid.hex(), source_timestamp=info.source_timestamp,
                    received_timestamp=info.received_timestamp, message=self.convert(msg)))+'\n')
            else:
                raise RuntimeError('RC independent recorder queue did not quiesce')

    def pump_rc(self, channels, seconds):
        self.channels = channels
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            self.pump()

    def on_control_revoked(self, event):
        if self.expected_revocation is not None and event.get('reason') == self.expected_revocation:
            self.active = False
            return
        super().on_control_revoked(event)

    def rc_setup(self):
        start = len(self.events)
        self.channels = NEUTRAL
        self.wait('rc_candidate', lambda: any(e.get('event') == 'rc_frame' and e.get('accepted')
                  and e.get('state') == 'CANDIDATE' for e in self.events[start:]), 5)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='RC_POS_CONTROL'), 'rc_active')
        self.phase('rc_segment_start')

    def execute(self):
        self.wait('public_control_ready', lambda: self.fresh() and self.epoch is not None
                  and self.setup_pub.get_subscription_count() == 2
                  and self.command_pub.get_subscription_count() == 1, 55)
        if not grounded(self.state):
            raise RuntimeError('RC experiment requires disarmed physical ground start')
        self.active = True
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
        if self.flight_stack == 'px4':
            after = time.monotonic()
            self.wait('native_prearm_health_ready', lambda: self.arm_ready(after), 55)
        self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'command_takeoff_completed', 45)
        self.dwell('initial_hold', lambda: self.fresh() and self.state.position[2] > 2.5, 2)
        self.rc_setup()
        getattr(self, 'scenario_'+self.scenario.replace('-', '_'))()
        self.phase('rc_scenario_complete')
        self.channels = None
        self.expected_revocation = 'explicit_native_mode_exit'
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LAND'), 'land_mode_completed', 15)
        self.wait('landed_disarmed_public', lambda: grounded(self.state), 60)
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')

    def movement(self, seconds=4.):
        stick = list(NEUTRAL); stick[1] = 1650
        self.phase('movement_begin')
        self.pump_rc(stick, seconds)
        self.phase('movement_end')

    def scenario_movement(self):
        self.movement()
        self.pump_rc(NEUTRAL, 2.)

    def scenario_recenter(self):
        self.movement(3.)
        self.pump_rc(NEUTRAL, 3.)
        self.phase('hold_begin')
        self.pump_rc(NEUTRAL, 4.)
        self.phase('hold_end')

    def scenario_yaw(self):
        stick = list(NEUTRAL); stick[3] = 1650
        self.phase('yaw_begin')
        self.pump_rc(stick, 3.)
        self.pump_rc(NEUTRAL, 2.)
        self.phase('yaw_end')

    def stall(self):
        self.movement(2.)
        self.expected_revocation = 'rc_input_revoked:input_expired'
        self.channels = None
        start = len(self.events)
        self.phase('stall_begin')
        self.wait('stall_revoked', lambda: any(e.get('event') == 'control_revoked'
                  and e.get('reason') == self.expected_revocation for e in self.events[start:]), 5)
        self.pump_rc(NEUTRAL, 2.)
        self.phase('retired_stream_observed')

    def scenario_stream_stall(self):
        self.stall()
        self.restore_native_hold()

    def restore_native_hold(self):
        if self.flight_stack == 'px4':
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'recovery_hold')
        self.wait('recovery_navigation_ready', self.fresh, 10)
        self.active = True

    def scenario_mode_out(self):
        self.movement(2.)
        self.expected_revocation = 'external_mode_left_no_automatic_reacquisition'
        mode = 'AUTO.LOITER' if self.flight_stack == 'px4' else 'BRAKE'
        if self.flight_stack == 'px4':
            from px4_msgs.msg import VehicleCommand
            from prometheus_control.frames import topic
            from .task import state_time
            pub=self.node.create_publisher(VehicleCommand,topic('/wksim_px4_21','in','vehicle_command',VehicleCommand),1)
            self.wait('external_mode_transport',lambda:pub.get_subscription_count()>=2,5)
            request=VehicleCommand(timestamp=int(state_time(self.state)*1e6),command=176,
                target_system=22,target_component=1,source_system=245,source_component=191,
                from_external=True,param1=1.,param2=4.,param3=3.)
            self.phase('external_mode_request',request=self.convert(request))
            pub.publish(request)
        else:
            from ardupilot_msgs.srv import ModeSwitch
            client=self.node.create_client(ModeSwitch,'/ap/mode_switch')
            self.wait('external_mode_transport',client.service_is_ready,5)
            request=ModeSwitch.Request(mode=17)
            self.phase('external_mode_request',request=self.convert(request))
            future=client.call_async(request)
            self.wait('external_mode_response',future.done,5)
            response=future.result()
            if not response.status or response.curr_mode!=17:
                raise RuntimeError('External AP BRAKE request rejected')
            from rclpy.serialization import serialize_message
            self.phase('external_mode_ack',response=self.convert(response),cdr_hex=serialize_message(response).hex())
        self.wait('mode_out_completed',lambda:self.state.mode==mode
                  and any(e.get('event')=='control_revoked' and e.get('reason')==self.expected_revocation for e in self.events),5)
        self.pump_rc(NEUTRAL, 3.)
        self.phase('mode_out_observed', mode=mode)

    def scenario_new_takeover(self):
        command = list(NEUTRAL); command[5] = 2000
        self.pump_rc(command, .2)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'), 'command_handoff')
        self.stream_id, self.rc_sequence = uuid.uuid4().hex, 0
        self.rc_setup()
        self.stall()
        self.channels = None
        self.restore_native_hold()
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'), 'new_command_takeover', 45)
        self.stream_id, self.rc_sequence = uuid.uuid4().hex, 0
        self.expected_revocation = None
        self.rc_setup()
        self.movement(3.)
        self.pump_rc(NEUTRAL, 2.)

    def report(self):
        return dict(super().report(), rc=dict(scenario=self.scenario, phases=self.rc_phases))

    def close(self):
        self.raw_log.close()
        self.raw_node.destroy_node()
        super().close()
