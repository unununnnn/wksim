"""Hex public position task with grounded native readback and raw observations."""
import hashlib
import json
import math
from pathlib import Path
import socket
import struct
import time

from .evidence import json_value, write_json
from .task import Task, grounded, state_time

PROTOCOL = Path(__file__).with_name('hex-flight-v1.json')
PROTOCOL_SHA256 = '33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc'
AP47_PROTOCOL_SHA256 = 'ce4f0aeb3c2de250aaf10c224f3fa43c326fcfcf8140c3746770879558f9df37'


def protocol_for(stack):
    if stack == 'arducopter':
        return PROTOCOL.with_name('hex-flight-ap47-v2.json'), AP47_PROTOCOL_SHA256
    if stack == 'px4':
        return PROTOCOL, PROTOCOL_SHA256
    raise ValueError('Unknown Hex stack')


def wire_payload(message):
    """Extract the original frame payload, including MAVLink2's 10-byte header.

    The pinned generated dialect's get_payload() keeps a four-byte header tail
    on MAVLink2 messages. The original parsed frame has the unambiguous length.
    """
    raw = bytes(message.get_msgbuf())
    if len(raw) < 8 or raw[0] not in (0xfe, 0xfd):
        raise ValueError('Invalid original MAVLink frame')
    header = 10 if raw[0] == 0xfd else 6
    signature = 13 if raw[0] == 0xfd and raw[2] & 1 else 0
    length = raw[1]
    if len(raw) != header+length+2+signature:
        raise ValueError('Original MAVLink frame length differs')
    return raw[header:header+length]


def physical(row):
    v = row['vehicle']
    if len(v) < 12 or not all(math.isfinite(x) for x in (row['time'], *v)):
        raise ValueError('Invalid Hex model truth')
    return dict(time=row['time'], position=(v[7], v[6], -v[8]), velocity=(v[4], v[3], -v[5]),
                attitude=(v[9], -v[10], math.remainder(math.pi/2-v[11], 2*math.pi)))


def parameter_value(row, expected_type, expected):
    """PX4 PARAM_VALUE INT32 is bytewise encoded in its first four payload bytes."""
    message = row['message']
    wire_type = 6 if expected_type == 'INT32' else 9 if expected_type == 'FLOAT' else None
    if message['param_type'] != wire_type:
        raise ValueError('Native parameter type differs')
    raw = bytes.fromhex(row['payload_hex'])
    if len(raw) != 25:
        raise ValueError('PARAM_VALUE payload must contain all 25 bytes')
    value = struct.unpack('<i' if expected_type == 'INT32' else '<f', raw[:4])[0]
    target = int(expected) if expected_type == 'INT32' else struct.unpack('<f', struct.pack('<f', expected))[0]
    if not math.isfinite(value) or value != target:
        raise ValueError(f'Native parameter differs: {value!r} != {target!r}')
    return value


class HexTask(Task):
    def __init__(self, directory, health, phase, flight_stack, *, parameters, parameter_types,
                 protocol_sha256, **kwargs):
        if kwargs.get('protocol') != 'session_v1' or kwargs.get('use_sim_time', False):
            raise ValueError('Hex task requires independent public session_v1')
        selected, expected_sha = protocol_for(flight_stack)
        raw = selected.read_bytes()
        if hashlib.sha256(raw).hexdigest() != protocol_sha256 or protocol_sha256 != expected_sha:
            raise ValueError('Frozen Hex flight protocol changed')
        self.budget = json.loads(raw)
        self.parameters, self.parameter_types = parameters, parameter_types
        self.directory = Path(directory)
        self.hex_result = dict(status='not_started', protocol_sha256=protocol_sha256,
                               phases=[], parameter_readback={}, raw_log='hex-native.jsonl')
        self.truth_rows, self.mav_messages, self.raw_subscriptions = [], [], []
        self.truth_stream = self.channel = self.recorder_node = None
        self.last_graph_at = 0.
        self.raw_log = (self.directory/'hex-native.jsonl').open('x', buffering=1)
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
                if self.truth_rows and not 0 < row['time']-self.truth_rows[-1]['time'] <= self.budget['physical_truth_max_gap_s']+1e-9:
                    raise RuntimeError('Physical clock regressed or truth gap exceeded')
                self.truth_rows.append(row)
        return physical(self.truth_rows[-1]) if self.truth_rows else None

    def cursor(self):
        value = self.read_truth()
        return dict(records=len(self.truth_rows), final_time=value['time']) if value else None

    def mark(self, label):
        self.hex_result['phases'].append(dict(phase=label, observed_monotonic_s=time.monotonic(),
            observed_unix_ns=time.time_ns(), physical_cursor=self.cursor(),
            native_boot_s=state_time(self.state) if self.state else None,
            state=self.convert(self.state) if self.state else None))
        write_json(self.directory/'hex-progress.json', self.hex_result)

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
        from prometheus_msgs.msg import TextInfo
        from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState
        channels = [(self.topic_root+'v2/command', CommandRequest), (self.topic_root+'v2/setup', SetupRequest),
                    (self.topic_root+'v2/state', SessionState), (self.topic_root+'text_info', TextInfo)]
        if self.flight_stack == 'arducopter':
            from ardupilot_msgs.msg import WksimState, GlobalPosition
            channels += [('/ap/wksim/local_state_v1', WksimState), ('/ap/cmd_gps_pose', GlobalPosition)]
        else:
            from prometheus_control.frames import topic
            from px4_msgs.msg import TrajectorySetpoint, OffboardControlMode, VehicleStatus, VehicleControlMode
            for direction, name, cls in (('in', 'trajectory_setpoint', TrajectorySetpoint),
                    ('in', 'offboard_control_mode', OffboardControlMode), ('out', 'vehicle_status', VehicleStatus),
                    ('out', 'vehicle_control_mode', VehicleControlMode)):
                channels.append((topic('/wksim_px4_21', direction, name, cls), cls))
        self.recorder_node = self.ros.create_node('wksim_hex_raw_recorder')
        self.raw_channels = channels
        qos = QoSProfile(depth=200, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.record('dds_recording_method', mechanism='unspun node subscription.handle.take_message(raw=True)',
                    per_message_publisher_gid_available=False)
        for name, cls in channels:
            def receive(raw, info, name=name):
                self.record('dds', topic=name, cdr_hex=bytes(raw).hex(), physical_cursor=self.cursor(),
                    source_timestamp=info['source_timestamp'], received_timestamp=info['received_timestamp'],
                    per_message_publisher_gid_available=False)
            self.raw_subscriptions.append(self.recorder_node.create_subscription(cls, name, receive, qos, raw=True))

    def poll_dds(self):
        for subscription in self.raw_subscriptions:
            for _ in range(200):
                with subscription.handle:
                    value = subscription.handle.take_message(subscription.msg_type, True)
                if value is None:
                    break
                if set(value[1]) != {'source_timestamp', 'received_timestamp'}:
                    raise RuntimeError('Raw DDS metadata changed')
                subscription.callback(*value)
            else:
                raise RuntimeError('Raw DDS queue did not quiesce')
        if time.monotonic()-self.last_graph_at >= .5:
            self.record('dds_discovery_publishers', publishers={name: [dict(node=p.node_name,
                namespace=p.node_namespace, endpoint_gid=bytes(p.endpoint_gid).hex())
                for p in self.recorder_node.get_publishers_info_by_topic(name)] for name, _ in self.raw_channels})
            self.last_graph_at = time.monotonic()

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
                    if message.get_type() != 'HEARTBEAT' or self.flight_stack == 'px4' and sender[1] != 18591:
                        continue
                    self.peer = sender
                row = dict(message=message.to_dict(), payload_hex=wire_payload(message).hex(),
                    packet_hex=bytes(message.get_msgbuf()).hex(), source_system=self.target_system,
                    source_component=1, peer=sender, physical_cursor=self.cursor())
                self.mav_messages.append(row)
                self.record('mavlink_decoded', **row)
        raise RuntimeError('Native observation queue did not quiesce')

    def pump(self):
        super().pump()
        self.poll_dds()
        self.poll_native()
        self.read_truth()
        if getattr(self, '_parameter_guard', None):
            self._parameter_guard()

    def ground_current(self):
        value = self.read_truth()
        age = time.time()-(self.directory/'truth.jsonl').stat().st_mtime if value else math.inf
        return (self.fresh() and grounded(self.state, self.uav_id) and value is not None
                and abs(value['position'][2]) < self.budget['ground_height_abs_lt_m']
                and 0 <= age <= self.budget['physical_truth_max_age_s'])

    def ground_parameters(self):
        self.wait('hex_ground_ready', lambda: self.ground_current() and self.peer is not None
                  and self.epoch is not None and self.public_graph_ready(), 55)
        context = (self.epoch, self.native_generation)
        deadline = time.monotonic()+self.budget['parameter_total_timeout_s'][self.flight_stack]
        def check():
            if not self.ground_current() or (self.epoch, self.native_generation) != context:
                raise RuntimeError('Native parameter read lost ground/generation authority')
            if time.monotonic() >= deadline:
                raise TimeoutError('Frozen aggregate parameter read deadline')
        client = None
        self._parameter_guard = check
        try:
            if self.flight_stack == 'arducopter':
                from rcl_interfaces.srv import GetParameters
                from rclpy.serialization import serialize_message
                client = self.node.create_client(GetParameters, '/ap/get_parameters')
                self.wait('hex_parameter_service', client.service_is_ready, 10)
            else:
                names = self.budget['px4_post_airframe_parameters']
                if names != ['CA_ROTOR0_PX', 'CA_ROTOR1_PX']:
                    raise ValueError('Unexpected post-airframe parameter contract')
                self.hex_result['parameter_application'] = []
                for name in names:
                    check()
                    if self.parameter_types[name] != 'FLOAT' or self.parameters[name] != 0:
                        raise ValueError('Only frozen Hex zero X coordinates may be applied')
                    start = len(self.mav_messages)
                    request = self.dialect.MAVLink_param_set_message(22, 1, name.encode(), 0., 9)
                    raw = request.pack(self.encoder)
                    if self.channel.sendto(raw, self.peer) != len(raw):
                        raise RuntimeError('Incomplete scoped startup parameter application')
                    self.record('parameter_apply_tx', name=name, expected=0., datagram_hex=raw.hex(), peer=self.peer)
                    def applied():
                        for row in self.mav_messages[start:]:
                            if (row['message'].get('mavpackettype') != 'PARAM_VALUE'
                                    or row['message']['param_id'] != name):
                                continue
                            try:
                                parameter_value(row, 'FLOAT', 0.)
                                return True
                            except ValueError:
                                pass  # Retain earlier broadcasts; await the fixed value, never change it.
                        return False
                    self.wait('parameter_applied_'+name, applied, self.budget['parameter_read_timeout_s'])
                    check()
                    self.hex_result['parameter_application'].append(dict(name=name, value=0., grounded=True))
            for name, expected in self.parameters.items():
                check()
                if client is not None:
                    request = GetParameters.Request(names=[name])
                    self.record('parameter_get_request', name=name, serialized_cdr_hex=serialize_message(request).hex(),
                                note='Client serialization, not captured request packet')
                    future = client.call_async(request)
                    self.wait('parameter_read_'+name, future.done, self.budget['parameter_read_timeout_s'])
                    response = future.result()
                    self.record('parameter_get_response', name=name, serialized_cdr_hex=serialize_message(response).hex(),
                                message=self.convert(response))
                    if len(response.values) != 1 or response.values[0].type not in (2, 3):
                        raise RuntimeError('Native parameter unavailable: '+name)
                    p = response.values[0]
                    value = p.integer_value if p.type == 2 else p.double_value
                    if not math.isfinite(value) or value != expected:
                        raise RuntimeError('Native AP parameter differs: '+name)
                else:
                    start = len(self.mav_messages)
                    request = self.dialect.MAVLink_param_request_read_message(22, 1, name.encode(), -1)
                    raw = request.pack(self.encoder)
                    if self.channel.sendto(raw, self.peer) != len(raw):
                        raise RuntimeError('Incomplete parameter read request')
                    self.record('parameter_request_read_tx', name=name, datagram_hex=raw.hex(), peer=self.peer)
                    def responses():
                        return [r for r in self.mav_messages[start:] if r['message'].get('mavpackettype') == 'PARAM_VALUE'
                                and r['message']['param_id'] == name]
                    self.wait('parameter_read_'+name, lambda: bool(responses()), self.budget['parameter_read_timeout_s'])
                    value = parameter_value(responses()[0], self.parameter_types[name], expected)
                check()
                self.hex_result['parameter_readback'][name] = value
            self.hex_result['parameter_context'] = dict(control_epoch=context[0], native_generation=context[1])
            self.mark('parameter_readback_complete')
        finally:
            self._parameter_guard = None
            if client is not None:
                self.node.destroy_client(client)

    def dwell(self, label, predicate, seconds):
        native_start, physical_start = state_time(self.state), self.read_truth()['time']
        deadline = self.task_time()+15  # Original Task's dwell watchdog.
        while (state_time(self.state)-native_start < seconds
               or self.read_truth()['time']-physical_start < seconds):
            self.pump()
            if not predicate():
                raise RuntimeError(label+': frozen public/physical threshold exceeded')
            if self.task_time() >= deadline:
                raise TimeoutError(label+': native/physical dwell timeout')
        self.phase(label)

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
        self.hex_result['public_request_graph'] = graph
        return True

    def physical_gate(self, kind):
        value = self.read_truth()
        if value is None or not 0 <= time.time()-(self.directory/'truth.jsonl').stat().st_mtime <= 2:
            return False
        b = self.budget
        if kind == 'takeoff':
            return value['position'][2] >= b['takeoff_min_height_m']
        if kind == 'hold':
            return (abs(value['position'][2]-b['hold_target_height_m']) <= b['hold_height_error_m']
                    and max(abs(x) for x in value['attitude'][:2]) <= b['hold_tilt_rad'])
        if kind == 'waypoint':
            return (math.dist(value['position'], b['waypoint_enu_m']) <= b['waypoint_error_m']
                    and math.hypot(*value['velocity']) <= b['waypoint_speed_mps'])
        if kind == 'ground':
            return abs(value['position'][2]) < b['ground_height_abs_lt_m']
        raise ValueError('Unknown physical gate')

    def execute(self):
        self.hex_result['status'] = 'running'
        b = self.budget
        self.ground_parameters()
        self.wait('public_control_ready', lambda: self.fresh() and self.public_graph_ready(), b['public_ready_timeout_s'])
        if not self.ground_current():
            raise RuntimeError('Task requires initial disarmed physical/public ground')
        self.active = True
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'autonomous_hold_ready')
        if self.flight_stack == 'px4':
            completed = time.monotonic()
            self.wait('native_prearm_health_ready', lambda: self.arm_ready(completed), b['px4_prearm_timeout_s'])
        if (not self.ground_current() or self.epoch != self.hex_result['parameter_context']['control_epoch']
                or self.native_generation != self.hex_result['parameter_context']['native_generation']):
            raise RuntimeError('Ground parameter session changed before arm')
        self.send(self.Setup(cmd=self.Setup.ARMING, arming=True), 'arming_completed')
        self.wait('armed', lambda: self.state.armed)
        self.send(self.Setup(cmd=self.Setup.SET_CONTROL_MODE, control_state='COMMAND_CONTROL'),
                  'task_control_ready', b['control_timeout_s'])
        self.wait('takeoff_reached', lambda: self.state.position[2] >= b['takeoff_min_height_m']
                  and self.physical_gate('takeoff'), b['takeoff_timeout_s'])
        self.dwell('hold_completed', lambda: abs(self.state.position[2]-3) <= b['hold_height_error_m']
                   and max(abs(x) for x in self.state.attitude[:2]) <= b['hold_tilt_rad']
                   and self.physical_gate('hold'), b['hold_duration_s'])
        self.send(self.Cmd(agent_cmd=self.Cmd.MOVE, move_mode=self.Cmd.XYZ_POS, command_id=1,
                  position_ref=[2., 3., 3.], yaw_ref=0.), 'waypoint_accepted')
        def at_waypoint():
            return (math.dist(self.state.position, b['waypoint_enu_m']) <= b['waypoint_error_m']
                    and math.hypot(*self.state.velocity) <= b['waypoint_speed_mps'] and self.physical_gate('waypoint'))
        self.wait('waypoint_reached', at_waypoint, b['waypoint_timeout_s'])
        self.dwell('waypoint_completed', at_waypoint, b['waypoint_duration_s'])
        self.send(self.Cmd(agent_cmd=self.Cmd.LAND, command_id=2), 'land_accepted')
        self.wait('landed_disarmed_public', lambda: grounded(self.state, self.uav_id)
                  and self.physical_gate('ground'), b['land_timeout_s'])
        self.send(self.Setup(cmd=self.Setup.SET_PX4_MODE, px4_mode='AUTO.LOITER'), 'ground_hold_completed')
        completed = time.monotonic()
        self.wait('normal_stop_ready', lambda: self.ground_current() and self.received.get('state', 0) > completed)
        self.hex_result['status'] = 'observed_pending_independent_raw_audit'

    def report(self):
        return dict(super().report(), hex=self.hex_result)

    def close(self):
        try:
            super().close()
        finally:
            for value in (self.channel, self.truth_stream, self.raw_log):
                if value is not None:
                    value.close()
            if self.recorder_node is not None:
                self.recorder_node.destroy_node()
