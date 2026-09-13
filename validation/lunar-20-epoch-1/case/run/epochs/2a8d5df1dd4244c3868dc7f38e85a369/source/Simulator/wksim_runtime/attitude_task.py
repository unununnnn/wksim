"""Explicit #34 candidate task; no candidate admission or native motion bypass.

Public commands contain ENU/FLU roll, pitch, yaw (radians), collective demand.
DDS records are actual middleware CDR; MAVLink records retain received datagrams.
Online checks use independent model truth. A completed task still needs raw audit.
"""
import hashlib
import json
import math
from pathlib import Path
import socket
import statistics
import time

from .evidence import json_value, write_json
from .task import Task, grounded, state_time


BUDGET = Path(__file__).resolve().parents[2] / 'work/ap-attitude-stage-20260909/flight-budget.json'
BUDGET_SHA = '9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f'
ENTRY_CONTRACT = Path(__file__).with_name('attitude-entry-v1.json')
ENTRY_CONTRACT_SHA = 'debd99a2b8c245608dd04bdaee61a9b9bc0e2c7240771c973eedec7c673c03c3'
MESSAGE_TOLERANCE = 1e-5  # Float32 wire matching only; no physical-budget change.
MODE_TRUE = ('flag_armed', 'flag_control_offboard_enabled', 'flag_control_attitude_enabled',
             'flag_control_rates_enabled', 'flag_control_allocation_enabled')
MODE_FALSE = ('flag_control_position_enabled', 'flag_control_velocity_enabled',
              'flag_control_altitude_enabled', 'flag_control_climb_rate_enabled',
              'flag_control_acceleration_enabled', 'flag_multicopter_position_control_enabled',
              'flag_control_manual_enabled', 'flag_control_auto_enabled', 'flag_control_termination_enabled')
AP_PARAMETERS = ('GUID_OPTIONS', 'GUID_TIMEOUT', 'ATC_ANGLE_BOOST', 'PILOT_THR_FILT',
                 'MOT_THST_EXPO', 'MOT_THST_HOVER', 'MOT_HOVER_LEARN', 'MOT_PWM_MIN',
                 'MOT_PWM_MAX', 'MOT_BAT_VOLT_MIN', 'MOT_BAT_VOLT_MAX', 'PSC_ANGLE_MAX', 'ATC_ANGLE_MAX')
PX4_PARAMETERS = ('MPC_THR_HOVER', 'MPC_USE_HTE', 'MPC_THR_MIN', 'MPC_THR_MAX', 'THR_MDL_FAC')


def require_ap_recovery_parameters(values):
    if values.get('PSC_ANGLE_MAX') != 10 or values.get('ATC_ANGLE_MAX') != 30:
        raise RuntimeError('Candidate recovery requires PSC_ANGLE_MAX=10 and ATC_ANGLE_MAX=30 readback')


def physical(row):
    v = row['vehicle']
    if len(v) < 12 or not all(math.isfinite(x) for x in (row['time'], *v)):
        raise ValueError('Invalid attitude model truth')
    return dict(time=row['time'], position=(v[7], v[6], -v[8]), velocity=(v[4], v[3], -v[5]),
                attitude=(v[9], -v[10], math.remainder(math.pi/2-v[11], 2*math.pi)))


def within(value, anchor, yaw, *, position, speed, tilt, heading):
    angles = value['attitude']
    return (math.dist(value['position'], anchor) <= position
            and math.hypot(*value['velocity']) <= speed
            and max(abs(x) for x in angles[:2]) <= math.radians(tilt)
            and abs(math.remainder(angles[2]-yaw, 2*math.pi)) <= math.radians(heading))


def hover_median(samples, start, end):
    selected = [s for s in samples if start <= s['physical_time'] <= end]
    # Native observations must span the requested three seconds, with endpoints
    # no farther away than one telemetry sample period; never use motor averages.
    if (len(selected) < 2 or selected[0]['physical_time'] > start+.1
            or selected[-1]['physical_time'] < end-.1
            or any(b['physical_time']-a['physical_time'] > .25 for a, b in zip(selected, selected[1:]))):
        raise RuntimeError('Native collective observations do not cover stable hover')
    demands = [s['thrust'] for s in selected]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in demands):
        raise ValueError('Invalid native collective demand')
    value = statistics.median(demands)
    if not .15 <= value <= .8:
        raise RuntimeError('Native hover demand outside frozen calibration range')
    return value, selected


class AttitudeTask(Task):
    def __init__(self, directory, health, phase, flight_stack, *, budget_path=BUDGET, **kwargs):
        if kwargs.get('protocol') != 'session_v1' or kwargs.get('use_sim_time', False):
            raise ValueError('AttitudeTask requires an explicit independent session_v1 task')
        raw = Path(budget_path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != BUDGET_SHA:
            raise ValueError('Frozen attitude budget differs')
        self.budget = json.loads(raw)
        if hashlib.sha256(ENTRY_CONTRACT.read_bytes()).hexdigest() != ENTRY_CONTRACT_SHA:
            raise ValueError('Frozen attitude entry contract differs')
        self.directory = Path(directory)
        self.attitude_result = dict(status='not_started', budget_sha256=BUDGET_SHA, phases=[],
            entry_contract_sha256=ENTRY_CONTRACT_SHA,
            parameter_readback={}, calibration=None, raw_log='attitude-native.jsonl',
            scope='independent candidate; task completion requires a separate raw audit')
        self.native_samples, self.native_targets, self.mav_messages, self.truth_rows = [], [], [], []
        self.control_modes = []
        self.entry_deadline = None
        self.envelope_anchor = None
        self.command_number = 0
        self.truth_stream = None
        self.channel = None
        self.recorder_node = None
        self.raw_subscriptions = []
        self.last_graph = None
        self.last_graph_at = 0.
        self.raw_log = (self.directory/'attitude-native.jsonl').open('x', buffering=1)
        def record_phase(label):
            self.mark(label)
            phase(label)
        super().__init__(directory, health, record_phase, flight_stack, **kwargs)
        try:
            self.open_observation()
        except Exception:
            self.close()
            raise

    def record(self, kind, **data):
        self.raw_log.write(json.dumps(json_value(dict(kind=kind, monotonic=time.monotonic(),
            unix_ns=time.time_ns(), run_id=self.run_id, control_epoch=self.epoch,
            native_generation=self.native_generation, **data)), allow_nan=False)+'\n')

    def read_truth(self):
        path = self.directory/'truth.jsonl'
        if self.truth_stream is None and path.exists():
            self.truth_stream = path.open()
        if self.truth_stream is not None:
            while True:
                offset = self.truth_stream.tell()
                line = self.truth_stream.readline()
                if not line.endswith('\n'):
                    self.truth_stream.seek(offset)
                    break
                row = json.loads(line)
                physical(row)
                if self.truth_rows and row['time'] <= self.truth_rows[-1]['time']:
                    raise RuntimeError('Independent physical clock regressed')
                self.truth_rows.append(row)
        return physical(self.truth_rows[-1]) if self.truth_rows else None

    def cursor(self):
        self.read_truth()
        if not self.truth_rows:
            return None
        return dict(records=len(self.truth_rows), final_time=self.truth_rows[-1]['time'],
                    final_height_m=-self.truth_rows[-1]['vehicle'][8])

    def mark(self, label, **data):
        row = dict(phase=label, observed_monotonic_s=time.monotonic(), observed_unix_ns=time.time_ns(),
            native_boot_s=state_time(self.state) if self.state is not None else None,
            physical_cursor=self.cursor(), state=self.convert(self.state) if self.state is not None else None, **data)
        self.attitude_result['phases'].append(row)
        write_json(self.directory/'attitude-progress.json', self.attitude_result)

    def open_observation(self):
        from .telemetry_dialect import load_dialect
        self.dialect, identity = load_dialect(self.flight_stack)
        self.encoder = self.dialect.MAVLink(None, srcSystem=245, srcComponent=190)
        self.decoder = self.dialect.MAVLink(None)
        self.peer = None
        self.target_system = 241 if self.flight_stack == 'arducopter' else 22
        self.channel = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.channel.bind(('127.0.0.1', 14660 if self.flight_stack == 'arducopter' else 14661))
        self.channel.setblocking(False)
        self.record('telemetry_identity', dialect=identity, local=self.channel.getsockname())
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from rclpy.serialization import deserialize_message
        from prometheus_control.frames import topic
        from prometheus_msgs.msg import TextInfo
        from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState
        channels = [(self.topic_root+'v2/command', CommandRequest),
                    (self.topic_root+'v2/setup', SetupRequest),
                    (self.topic_root+'v2/state', SessionState), (self.topic_root+'text_info', TextInfo)]
        if self.flight_stack == 'arducopter':
            from ardupilot_msgs.msg import WksimAttitudeTarget, WksimState, GlobalPosition
            channels += [('/ap/wksim/attitude_target_v1', WksimAttitudeTarget),
                         ('/ap/wksim/local_state_v1', WksimState), ('/ap/cmd_gps_pose', GlobalPosition)]
        else:
            from px4_msgs.msg import VehicleAttitudeSetpoint, OffboardControlMode, VehicleAttitude, TrajectorySetpoint, VehicleControlMode
            for direction, name, cls in (('in', 'vehicle_attitude_setpoint', VehicleAttitudeSetpoint),
                    ('in', 'offboard_control_mode', OffboardControlMode), ('out', 'vehicle_attitude', VehicleAttitude),
                    ('in', 'trajectory_setpoint', TrajectorySetpoint),
                    ('out', 'vehicle_control_mode', VehicleControlMode)):
                channels.append((topic('/wksim_px4_21', direction, name, cls), cls))
            self.control_mode_topic = topic('/wksim_px4_21', 'out', 'vehicle_control_mode', VehicleControlMode)
        qos = QoSProfile(depth=200, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.recorder_node = self.ros.create_node('wksim_attitude_raw_recorder')
        self.record('dds_recording_method', mechanism='unspun node subscription.handle.take_message(raw=True)',
                    per_message_publisher_gid_available=False,
                    attribution='Discovery endpoints separately recorded; no per-packet publisher attribution')
        self.raw_channels = channels
        for name, cls in channels:
            def receive(raw, info, name=name, cls=cls):
                cursor = self.cursor()
                self.record('dds', topic=name, cdr_hex=bytes(raw).hex(),
                    per_message_publisher_gid_available=False,
                    source_timestamp=info['source_timestamp'], received_timestamp=info['received_timestamp'],
                    physical_cursor=cursor)
                if cursor is not None and '/out/vehicle_control_mode' in name:
                    msg = deserialize_message(raw, cls)
                    row = dict(native_source_stamp=int(msg.timestamp), physical_time=cursor['final_time'],
                        flags=self.convert(msg), source_timestamp=info['source_timestamp'],
                        received_timestamp=info['received_timestamp'])
                    if self.control_modes and row['native_source_stamp'] <= self.control_modes[-1]['native_source_stamp']:
                        raise RuntimeError('VehicleControlMode native timestamp did not advance')
                    self.control_modes.append(row)
                    self.record('vehicle_control_mode_decoded', **row)
                if cursor is not None and ('attitude_target_v1' in name or '/in/vehicle_attitude_setpoint' in name):
                    msg = deserialize_message(raw, cls)
                    if self.flight_stack == 'arducopter':
                        q = [msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w]
                        thrust = msg.normalized_thrust
                    else:
                        # Basis conversion is self-inverse; this helper uses WXYZ.
                        q_ned = tuple(float(v) for v in msg.q_d)
                        k = math.sqrt(.5)
                        w, x, y, z = q_ned
                        q = [k*(x+y), k*(x-y), k*(w-z), k*(w+z)]
                        thrust = -msg.thrust_body[2]
                    self.native_targets.append(dict(physical_time=cursor['final_time'],
                        quaternion_xyzw=[float(v) for v in q], thrust=float(thrust),
                        timing='receiver physical cursor, not native acceptance time',
                        native_source_stamp=(dict(sec=msg.header.stamp.sec, nanosec=msg.header.stamp.nanosec)
                                             if self.flight_stack == 'arducopter' else int(msg.timestamp))))
            self.raw_subscriptions.append(self.recorder_node.create_subscription(cls, name, receive, qos, raw=True))

    def poll_dds(self):
        for subscription in self.raw_subscriptions:
            for _ in range(200):
                with subscription.handle:
                    value = subscription.handle.take_message(subscription.msg_type, True)
                if value is None:
                    break
                if set(value[1]) != {'source_timestamp', 'received_timestamp'}:
                    raise RuntimeError('Native raw metadata schema changed')
                subscription.callback(*value)
            else:
                raise RuntimeError('Native raw DDS queue did not quiesce')
        now = time.monotonic()
        if now-self.last_graph_at >= .5:
            publishers = {name: [dict(node=p.node_name, namespace=p.node_namespace,
                                      endpoint_gid=bytes(p.endpoint_gid).hex())
                                for p in self.recorder_node.get_publishers_info_by_topic(name)]
                          for name, _ in self.raw_channels}
            self.record('dds_discovery_publishers', publishers=publishers, physical_cursor=self.cursor())
            self.last_graph, self.last_graph_at = publishers, now

    def poll_native(self):
        for _ in range(1000):
            try:
                raw, sender = self.channel.recvfrom(65535)
            except BlockingIOError:
                return
            self.record('mavlink_rx', peer=sender, datagram_hex=raw.hex())
            if sender[0] != '127.0.0.1' or self.peer is not None and sender != self.peer:
                continue
            for message in self.decoder.parse_buffer(raw) or []:
                if message.get_srcSystem() != self.target_system or message.get_srcComponent() != 1:
                    continue
                if self.peer is None:
                    if message.get_type() != 'HEARTBEAT':
                        continue
                    if self.flight_stack == 'px4' and sender[1] != 18591:
                        continue
                    self.peer = sender
                data = message.to_dict()
                value = self.read_truth()
                row = dict(message=data, physical_time=value['time'] if value else None,
                           source_system=self.target_system, source_component=1, peer=sender)
                self.mav_messages.append(row)
                self.record('mavlink_decoded', **row)
                if message.get_type() == 'ATTITUDE_TARGET' and value is not None:
                    self.native_samples.append(dict(physical_time=value['time'], native_boot_s=message.time_boot_ms/1000,
                                                    thrust=float(message.thrust), quaternion=list(message.q)))
        raise RuntimeError('Native observation queue did not quiesce')

    def transmit_observation(self, message):
        if self.peer is None:
            raise RuntimeError('No identity-checked native telemetry peer')
        if message.get_type() not in ('COMMAND_LONG', 'PARAM_REQUEST_READ'):
            raise ValueError('Observation transport cannot send motion commands')
        if message.get_type() == 'COMMAND_LONG' and message.command != self.dialect.MAV_CMD_SET_MESSAGE_INTERVAL:
            raise ValueError('Only telemetry interval requests are allowed')
        raw = message.pack(self.encoder)
        sent = self.channel.sendto(raw, self.peer)
        self.record('mavlink_tx_observation', peer=self.peer, message=message.to_dict(), datagram_hex=raw.hex(), sent=sent)
        if sent != len(raw):
            raise RuntimeError('Incomplete observation request')

    def pump(self):
        super().pump()
        self.poll_dds()
        self.poll_native()
        value = self.read_truth()
        if self.entry_deadline is not None:
            physical_end, wall_end = self.entry_deadline
            if value is None or not self.fresh():
                raise RuntimeError('Attitude entry lost fresh physical state')
            if value['time'] > physical_end or time.monotonic() >= wall_end:
                raise TimeoutError('Attitude entry preconditioning deadline')
        if self.envelope_anchor is not None and value is not None:
            p, a = value['position'], value['attitude']
            if (math.dist(p, self.envelope_anchor) > 4 or not 1.5 <= p[2] <= 4.5
                    or max(abs(x) for x in a[:2]) > math.radians(15)):
                raise RuntimeError('Frozen attitude abort envelope exceeded')

    def ground_parameters(self):
        def ground_current():
            value = self.read_truth()
            age = time.time()-(self.directory/'truth.jsonl').stat().st_mtime if value else math.inf
            return (self.fresh() and grounded(self.state, self.uav_id) and value is not None
                    and abs(value['position'][2]) < .3 and 0 <= age <= 2)
        self.wait('attitude_ground_ready', lambda: ground_current()
                  and self.peer is not None, 55)
        context = (self.epoch, self.native_generation)
        def check_ground():
            if not ground_current() or (self.epoch, self.native_generation) != context:
                raise RuntimeError('Parameter read lost ground/native-generation authority')
        if self.flight_stack == 'arducopter':
            from rcl_interfaces.srv import GetParameters
            from rclpy.serialization import serialize_message
            client = self.node.create_client(GetParameters, '/ap/get_parameters')
            try:
                self.wait('attitude_parameter_service', client.service_is_ready, 10)
                for name in AP_PARAMETERS:
                    check_ground()
                    request = GetParameters.Request(names=[name])
                    self.record('parameter_get_request', name=name, serialized_cdr_hex=serialize_message(request).hex(),
                                note='Client serialization; not a captured request packet')
                    future = client.call_async(request)
                    self.wait('parameter_read_'+name, future.done, 10)
                    response = future.result()
                    check_ground()
                    self.record('parameter_get_response', name=name, message=self.convert(response),
                                serialized_cdr_hex=serialize_message(response).hex())
                    if len(response.values) != 1 or response.values[0].type not in (2, 3):
                        raise RuntimeError('Native parameter unavailable: '+name)
                    p = response.values[0]
                    self.attitude_result['parameter_readback'][name] = p.integer_value if p.type == 2 else p.double_value
                    if not math.isfinite(self.attitude_result['parameter_readback'][name]):
                        raise RuntimeError('Native parameter is non-finite: '+name)
            finally:
                self.node.destroy_client(client)
            values = self.attitude_result['parameter_readback']
            require_ap_recovery_parameters(values)
            if (not math.isfinite(values['GUID_OPTIONS']) or int(values['GUID_OPTIONS']) != values['GUID_OPTIONS']
                    or not int(values['GUID_OPTIONS']) & 8 or values['GUID_TIMEOUT'] != 3):
                raise RuntimeError('Actual GUID_OPTIONS/GUID_TIMEOUT does not satisfy frozen prerequisite')
        else:
            for name in PX4_PARAMETERS:
                check_ground()
                start = len(self.mav_messages)
                self.transmit_observation(self.dialect.MAVLink_param_request_read_message(22, 1, name.encode(), -1))
                def response():
                    return [r['message'] for r in self.mav_messages[start:]
                            if r['message'].get('mavpackettype') == 'PARAM_VALUE' and r['message']['param_id'] == name]
                self.wait('parameter_read_'+name, lambda: bool(response()), 10)
                check_ground()
                self.attitude_result['parameter_readback'][name] = response()[0]
        check_ground()
        self.mark('parameter_readback_complete')
        self.transmit_observation(self.dialect.MAVLink_command_long_message(self.target_system, 1,
            self.dialect.MAV_CMD_SET_MESSAGE_INTERVAL, 0, self.dialect.MAVLINK_MSG_ID_ATTITUDE_TARGET,
            25000, 0, 0, 0, 0, 0))

    def public_graph_ready(self):
        graph = {}
        for kind, publisher in (('setup', self.setup_pub), ('command', self.command_pub)):
            endpoints = self.node.get_subscriptions_info_by_topic(self.topic_root+'v2/'+kind)
            if (publisher.get_subscription_count() != 2 or len(endpoints) != 2
                    or {p.node_name for p in endpoints} != {'prometheus_native_control', self.recorder_node.get_name()}
                    or any(p.node_namespace != '/' or not any(p.endpoint_gid) for p in endpoints)
                    or len({bytes(p.endpoint_gid) for p in endpoints}) != 2):
                return False
            graph[kind] = [dict(node=p.node_name, namespace=p.node_namespace,
                                endpoint_gid=bytes(p.endpoint_gid).hex()) for p in endpoints]
        self.attitude_result['public_request_graph'] = graph
        return True

    def command(self, label, *, attitude=None, position=None, yaw=0):
        self.command_number += 1
        msg = self.Cmd(agent_cmd=self.Cmd.MOVE, command_id=self.command_number,
                       move_mode=self.Cmd.XYZ_ATT if attitude is not None else self.Cmd.XYZ_POS,
                       **({'att_ref': list(attitude)} if attitude is not None else
                          {'position_ref': list(position), 'yaw_ref': yaw}))
        offered = self.read_truth()['time']
        self.mark(label+'_offered', command_id=self.command_number, payload=self.convert(msg))
        start = len(self.native_targets)
        self.send(msg, label+'_accepted')
        if attitude is None:
            return offered
        roll, pitch, heading, thrust = attitude
        cr, sr, cp, sp, cy, sy = (math.cos(roll/2), math.sin(roll/2), math.cos(pitch/2),
                                 math.sin(pitch/2), math.cos(heading/2), math.sin(heading/2))
        expected = (sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy)
        def targets():
            return [r for r in self.native_targets[start:] if abs(r['thrust']-thrust) < MESSAGE_TOLERANCE
                    and min(math.dist(r['quaternion_xyzw'], expected),
                            math.dist(r['quaternion_xyzw'], [-v for v in expected])) < MESSAGE_TOLERANCE]
        self.wait(label+'_native_published', lambda: bool(targets()), 2)
        self.mark(label+'_native_observed', native_target=targets()[0])
        self.last_command_target = targets()[0]
        return targets()[0]['physical_time']

    def attitude_entry(self, label, yaw, hover):
        if self.flight_stack != 'px4':
            return
        start = self.read_truth()['time']
        self.entry_deadline = (start+2., time.monotonic()+10.)
        modes_start, samples_start = len(self.control_modes), len(self.native_samples)
        self.mark(label+'_preconditioning_begin', physical_start=start, physical_deadline=start+2.,
                  wall_timeout_seconds=10., neutral_attitude=[0., 0., yaw, hover])
        try:
            self.command(label+'_neutral', attitude=(0., 0., yaw, hover))
            offered = self.last_command_target['native_source_stamp']
            expected = (math.cos((math.pi/2-yaw)/2), 0., 0., math.sin((math.pi/2-yaw)/2))
            identity = None
            while True:
                self.pump()  # Original abort envelope and both entry deadlines remain active.
                endpoints = (self.last_graph or {}).get(self.control_mode_topic, [])
                if len(endpoints) != 1 or not endpoints[0].get('endpoint_gid') or not any(bytes.fromhex(endpoints[0]['endpoint_gid'])):
                    continue
                if identity is not None and endpoints != identity:
                    raise RuntimeError('VehicleControlMode publisher identity changed during entry')
                identity = endpoints
                for mode in self.control_modes[max(modes_start, len(self.control_modes)-1):]:
                    flags = mode['flags']
                    if (mode['native_source_stamp'] < offered
                            or self.read_truth()['time']-mode['physical_time'] > .75
                            or not all(flags.get(name, False) for name in MODE_TRUE)
                            or any(flags.get(name, True) for name in MODE_FALSE)):
                        continue
                    targets = [s for s in self.native_samples[samples_start:]
                        if s['native_boot_s']*1e6 > mode['native_source_stamp']
                        and self.read_truth()['time']-s['physical_time'] <= .25
                        and abs(s['thrust']-hover) < MESSAGE_TOLERANCE
                        and min(math.dist(s['quaternion'], expected),
                                math.dist(s['quaternion'], [-v for v in expected])) < MESSAGE_TOLERANCE]
                    if targets:
                        self.mark(label+'_preconditioning_complete', offered_native_stamp=offered,
                                  control_mode=mode, publisher_endpoints=identity, actual_attitude_target=targets[0])
                        return
        finally:
            self.entry_deadline = None

    def duration(self, label, seconds, predicate, *, start=None):
        start = self.read_truth()['time'] if start is None else start
        deadline = time.monotonic()+max(15, seconds*3)
        self.mark(label+'_begin', physical_start=start, duration_seconds=seconds)
        while True:
            self.pump()
            value = self.read_truth()
            if not self.fresh() or not predicate(value):
                raise RuntimeError(label+': frozen physical condition failed')
            if value['time']-start >= seconds:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(label+': physical clock did not complete')
        self.mark(label+'_end')

    def stable(self, label, anchor, yaw, *, timeout, dwell, position, speed, tilt, heading):
        start = self.read_truth()['time']
        stable_since = None
        wall = time.monotonic()+max(20, timeout*3)
        self.mark(label+'_begin')
        while True:
            self.pump()
            value = self.read_truth()
            if value['time']-start > timeout or time.monotonic() >= wall:
                raise TimeoutError(label+': frozen recovery/stability deadline')
            ok = self.fresh() and within(value, anchor, yaw, position=position, speed=speed, tilt=tilt, heading=heading)
            if not ok:
                stable_since = None
            elif stable_since is None:
                stable_since = value['time']
            if stable_since is not None and value['time']-stable_since >= dwell:
                self.mark(label+'_end', stable_since=stable_since)
                return

    def recovery(self, label, anchor, yaw):
        start = self.read_truth()['time']
        self.command(label, position=anchor, yaw=yaw)
        # Include public command acknowledgement latency in the frozen 8 seconds.
        remaining = 8-(self.read_truth()['time']-start)
        if remaining <= 0:
            raise TimeoutError(label+': command consumed recovery deadline')
        self.stable(label+'_recovered', anchor, yaw, timeout=remaining, dwell=1.5,
                    position=.4, speed=.3, tilt=3, heading=3)

    def execute(self):
        self.attitude_result['status'] = 'running'
        try:
            self.ground_parameters()
            # This task's raw observer is the second middleware subscriber.
            self.wait('public_control_ready', lambda: self.fresh() and self.public_graph_ready(), 55)
            self.active = True
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
            if self.flight_stack == 'px4':
                completed = time.monotonic()
                self.wait('native_prearm_health_ready', lambda: self.arm_ready(completed), 55)
            self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
            self.wait('armed', lambda: self.state.armed)
            self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'), 'task_control_ready', 40)
            self.wait('takeoff_reached', lambda: self.state.position[2] >= 2.5, 25)
            anchor, yaw = (2., 3., 3.), 0.
            self.command('position_baseline', position=anchor, yaw=yaw)
            self.wait('position_baseline_reached', lambda: self.fresh() and within(self.read_truth(), anchor, yaw,
                      position=.25, speed=.15, tilt=2, heading=3), 30)
            self.envelope_anchor = anchor
            self.stable('entry', anchor, yaw, timeout=15, dwell=2, position=.25, speed=.15, tilt=2, heading=3)
            start = self.read_truth()['time']
            self.duration('hover_observation', 3, lambda v: within(v, anchor, yaw, position=.25, speed=.15, tilt=2, heading=3))
            end = self.read_truth()['time']
            hover, samples = hover_median(self.native_samples, start, end)
            anchor = tuple(self.read_truth()['position'])
            yaw = self.read_truth()['attitude'][2]
            self.envelope_anchor = anchor
            self.attitude_result['calibration'] = dict(status='candidate_frozen_before_level_calibration',
                hover=hover, samples=samples, source='native MAVLink ATTITUDE_TARGET collective demand',
                frozen_at_physical_time=end, yaw=yaw, anchor=anchor)
            self.mark('hover_candidate_frozen')
            self.attitude_entry('level_calibration_entry', yaw, hover)
            height = self.read_truth()['position'][2]
            start = self.command('level_calibration', attitude=(0., 0., yaw, hover))
            self.duration('level_calibration', 2, lambda v: abs(v['position'][2]-height) <= .3 and abs(v['velocity'][2]) <= .2,
                          start=start)
            self.attitude_result['calibration']['status'] = 'level_calibrated_frozen_before_steps'
            self.recovery('calibration_recovery', anchor, yaw)
            self.mark('calibration_frozen_before_steps')
            roll = math.radians(5)
            self.attitude_entry('attitude_step_entry', yaw, hover)
            anchor = tuple(self.read_truth()['position'])
            self.mark('attitude_anchor', anchor=anchor, yaw=yaw)
            start = self.command('attitude_step', attitude=(roll, 0., yaw, hover))
            self.duration('attitude_settling', .5, lambda v: True, start=start)
            self.duration('attitude_tracking', .4, lambda v: abs(v['attitude'][0]-roll) <= math.radians(2)
                and abs(v['attitude'][1]) <= math.radians(2)
                and abs(math.remainder(v['attitude'][2]-yaw, 2*math.pi)) <= math.radians(3), start=start+.5)
            self.duration('attitude_remaining', .1, lambda v: True, start=start+.9)
            self.recovery('attitude_recovery', anchor, yaw)
            self.attitude_entry('thrust_baseline_entry', yaw, hover)
            self.command('thrust_baseline', attitude=(0., 0., yaw, hover))
            self.duration('thrust_baseline', .2, lambda v: True)
            anchor = tuple(self.read_truth()['position'])
            self.mark('thrust_anchor', anchor=anchor, yaw=yaw)
            start = self.command('thrust_step', attitude=(0., 0., yaw, hover+.03))
            self.duration('thrust_step', .5, lambda v: True, start=start)
            step_end = start+.5
            def mean_up(lo, hi):
                values = [-r['vehicle'][5] for r in self.truth_rows if lo <= r['time'] <= hi]
                if not values:
                    raise RuntimeError('Missing thrust comparison samples')
                return statistics.mean(values)
            increase = mean_up(step_end-.1, step_end)-mean_up(start-.2, start)
            self.attitude_result['thrust_velocity_increase_mps'] = increase
            if increase < .05:
                raise RuntimeError('Frozen thrust velocity increment not met')
            self.recovery('thrust_recovery', anchor, yaw)
            self.envelope_anchor = None
            self.command_number += 1
            self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=self.command_number), 'land_accepted')
            self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id), 30)
            self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
            self.attitude_result['status'] = 'completed_pending_raw_audit'
        except Exception as error:
            self.attitude_result.update(status='failed', error=str(error))
            self.envelope_anchor = None
            # Existing public LAND path only; zero thrust is never a recovery command.
            if self.state is not None and self.state.armed:
                try:
                    self.command_number += 1
                    self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=self.command_number), 'failure_land_accepted')
                    self.wait('failure_landed', lambda: grounded(self.state, self.uav_id), 30)
                except Exception as cleanup:
                    self.attitude_result['landing_failure'] = str(cleanup)
            raise
        finally:
            write_json(self.directory/'attitude-progress.json', self.attitude_result)

    def report(self):
        return dict(super().report(), attitude_thrust=self.attitude_result)

    def close(self):
        try:
            super().close()
        finally:
            if self.channel is not None:
                self.channel.close()
            if self.recorder_node is not None:
                self.recorder_node.destroy_node()
            if self.truth_stream is not None:
                self.truth_stream.close()
            self.raw_log.close()
