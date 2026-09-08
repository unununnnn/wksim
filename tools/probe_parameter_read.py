"""One native parameter read, then the standard public Task flight; no parameter writes."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid

from Simulator.wksim_runtime.config import load_config, validate_config
from Simulator.wksim_runtime.parameter_protocol import GroundState, ParameterContext, ParameterProtocol
from Simulator.wksim_runtime.runtime import run, truth_summary
from Simulator.wksim_runtime.task import Task, grounded


def read_config(path, run_id):
    config = load_config(path)
    forbidden = {'mission', 'display_socket', 'telemetry_socket', 'gcs_udp_forward',
                 'restart_control_on_ground', 'promotion_flight'}
    if config.get('kind') == 'joint_scene' or forbidden.intersection(config):
        raise ValueError('Read probe requires independent configuration without mission/display/telemetry/GCS/restart/promotion fields')
    if config.get('control_protocol') != 'session_v1':
        raise ValueError('Read probe requires session_v1')
    return validate_config(dict(config, run_id=run_id))


def byte_evidence(raw, encoding):
    return dict(encoding=encoding, hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))


class ReadProbe(Task):
    def __init__(self, directory, *args, **kwargs):
        super().__init__(directory, *args, **kwargs)
        self.directory = directory
        self.source_received = 0.0
        self.operation_id = uuid.uuid4().hex
        self.probe = dict(status='not_started', parameter_writes=0, parameter_write_operations=[],
                          restart_operations=[], scope='native read probe plus standard public Task flight',
                          evidence=[])
        sources = [Path(__file__), Path(__file__).with_name('run-parameter-read-probe.sh'),
                   Path(__file__).resolve().parents[1] / 'Simulator/wksim_runtime/parameter_protocol.py',
                   Path(__file__).resolve().parents[1] / 'Simulator/wksim_runtime/telemetry_dialect.py']
        self.probe['sources_sha256'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}

    def receive_session(self, msg):
        previous = self.session_sequence
        super().receive_session(msg)
        if self.session_sequence != previous:
            self.source_received = msg.source_received_monotonic_s

    def ground_state(self):
        path = self.directory / 'truth.jsonl'
        # Stat before reading: a later append must not make an earlier row look newer.
        mtime = path.stat().st_mtime
        truth = truth_summary(path)
        wall, now = time.time(), time.monotonic()
        age = wall - mtime
        if not 0 <= age <= 2:
            raise RuntimeError(f'Physical truth mtime stale or in the future: age_s={age}, mtime={mtime}, observed_unix={wall}')
        context = ParameterContext(self.operation_id, self.run_id, self.epoch, self.native_generation)
        oldest = min(self.source_received, self.received.get('state', 0), self.advanced_at, now - age)
        public_ground = self.fresh() and grounded(self.state, self.uav_id) and not self.error
        self.last_ground = dict(context=asdict(context), observed_at_monotonic=oldest,
            checked_at_monotonic=now, checked_at_unix=wall, truth_mtime_unix=mtime,
            truth_age_s=age, truth=truth, source_received_monotonic=self.source_received,
            public_received_monotonic=self.received.get('state', 0), public_advanced_monotonic=self.advanced_at,
            public_state=self.convert(self.state) if self.state is not None else None,
            max_age_s=2, ground_height_limit_m=0.3,
            time_source='Task accepted session native source monotonic; truth file Unix mtime mapped with current Unix/monotonic pair')
        return GroundState(context, oldest, bool(public_ground),
                           bool(public_ground and abs(truth['final_height_m']) < 0.3), self.active)

    def ready(self):
        if not self.fresh() or not grounded(self.state, self.uav_id) or self.epoch is None or self.native_generation is None:
            return False
        state = self.ground_state()
        return state.disarmed and state.grounded and not state.active_task and 0 <= time.monotonic()-state.observed_at <= 2

    def record(self, kind, **data):
        self.probe['evidence'].append(dict(kind=kind, monotonic=time.monotonic(), unix=time.time(), **data))
        (self.directory / 'parameter-read.json').write_text(json.dumps(self.probe, indent=2) + '\n')

    def recheck_current(self, protocol):
        protocol.check_current()
        self.record('ground_authority', **self.last_ground)

    def read_ap(self, context):
        from rcl_interfaces.srv import GetParameters
        from rclpy.serialization import serialize_message
        service = '/ap/get_parameters'
        self.probe.update(service=service, request_topic='rq/ap/get_parametersRequest',
                          response_topic='rr/ap/get_parametersReply',
                          correlation='single real ROS client future; CDR serialization is not a packet capture')
        client = self.node.create_client(GetParameters, service)
        future = None
        try:
            self.wait('parameter_service_ready', client.service_is_ready, 10)
            graph = self.node.get_service_names_and_types()
            self.record('service_graph', services=graph, actual_client_service=client.srv_name,
                        ready=client.service_is_ready())
            if (client.srv_name != service or not any(name == service and 'rcl_interfaces/srv/GetParameters' in types
                                                     for name, types in graph)):
                raise RuntimeError('Fixed AP service name/type absent from actual graph')
            protocol = ParameterProtocol('arducopter', 'WP_SPD', context, self.ground_state, max_age=2)
            request = protocol.ap_get_request()
            self.recheck_current(protocol)
            self.record('request', message=self.convert(request), raw=byte_evidence(serialize_message(request), 'ROS CDR'))
            protocol.check_current()
            future = client.call_async(request)
            self.wait('parameter_read_response', future.done, 10)
            response = future.result()
            self.record('response', message=self.convert(response), raw=byte_evidence(serialize_message(response), 'ROS CDR'))
            self.recheck_current(protocol)
            self.probe['original_value'] = protocol.ap_get_value(response)
        finally:
            if future is not None and not future.done():
                future.cancel()
            self.record('service_graph_at_close', services=self.node.get_service_names_and_types(),
                        actual_client_service=client.srv_name, ready=client.service_is_ready())
            self.node.destroy_client(client)
            self.record('client_closed', transport='ROS GetParameters', retry_count=0)

    def read_px4(self, context):
        from Simulator.wksim_runtime.telemetry_dialect import load_dialect
        dialect, identity = load_dialect('px4')
        peer = ('127.0.0.1', 18591)
        self.probe.update(dialect=identity, local=['127.0.0.1', 14661], peer=peer,
            target_system=22, target_component=1, source_system=245, source_component=190,
            correlation='PARAM_VALUE has no request_id; same-context matching observation only, not strong request correlation')
        parser = dialect.MAVLink(None)
        encoder = dialect.MAVLink(None, srcSystem=245, srcComponent=190)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as channel:
            channel.bind(('127.0.0.1', 14661))
            channel.setblocking(False)

            def receive():
                self.pump()
                try:
                    raw, sender = channel.recvfrom(65535)
                except BlockingIOError:
                    return []
                if sender != peer:
                    raise RuntimeError('Unexpected PX4 datagram peer: ' + repr(sender))
                messages = parser.parse_buffer(raw) or []
                return [(message, sender, raw) for message in messages]

            deadline = time.monotonic() + 10
            while True:
                matched = False
                for message, sender, raw in receive():
                    if message.get_type() != 'HEARTBEAT':
                        continue
                    self.record('heartbeat', peer=sender, message=message.to_dict(),
                                raw=byte_evidence(raw, 'MAVLink UDP datagram'))
                    if (message.get_srcSystem() != 22 or message.get_srcComponent() != 1
                            or message.autopilot != dialect.MAV_AUTOPILOT_PX4
                            or message.type != dialect.MAV_TYPE_QUADROTOR
                            or message.base_mode & dialect.MAV_MODE_FLAG_SAFETY_ARMED):
                        raise RuntimeError('PX4 heartbeat identity/type/disarmed check failed')
                    matched = True
                if matched:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Expected PX4 heartbeat not observed in private namespace')
            # Discard all input queued before publication, with a bounded drain.
            drained = 0
            drain_deadline = time.monotonic() + 1
            while True:
                try:
                    channel.recvfrom(65535)
                    drained += 1
                except BlockingIOError:
                    break
                if drained >= 10000 or time.monotonic() >= drain_deadline:
                    raise TimeoutError('PX4 pre-request drain did not quiesce')
            parser = dialect.MAVLink(None)
            self.record('input_drained', datagrams=drained)
            protocol = ParameterProtocol('px4', 'MPC_XY_CRUISE', context, self.ground_state,
                max_age=2, dialect=dialect, peer=peer, target_system=22, target_component=1)
            request = protocol.px4_read_message()
            raw = request.pack(encoder)
            self.recheck_current(protocol)
            protocol.check_current()
            sent = channel.sendto(raw, peer)
            self.record('request', peer=peer, message=request.to_dict(), bytes_sent=sent,
                        raw=byte_evidence(raw, 'MAVLink UDP datagram'))
            if sent != len(raw):
                raise RuntimeError('Incomplete parameter request send')
            deadline = time.monotonic() + 10
            while True:
                for message, sender, raw in receive():
                    if message.get_type() != 'PARAM_VALUE':
                        continue
                    self.record('response', peer=sender, source_system=message.get_srcSystem(),
                                source_component=message.get_srcComponent(), message=message.to_dict(),
                                raw=byte_evidence(raw, 'MAVLink UDP datagram'))
                    self.recheck_current(protocol)
                    self.probe['original_value'] = protocol.px4_value(message, peer=sender, context=context)
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError('PARAM_VALUE unknown/timeout; no retry and no native rejection inferred')

    def execute(self):
        self.probe['status'] = 'waiting_for_ground'
        try:
            self.wait('parameter_public_physical_ground_ready', self.ready, 55)
            context = self.ground_state().context
            self.probe.update(context=asdict(context), parameter='WP_SPD' if self.flight_stack == 'arducopter' else 'MPC_XY_CRUISE')
            self.probe['status'] = 'reading'
            if self.flight_stack == 'arducopter':
                self.read_ap(context)
            else:
                try:
                    self.read_px4(context)
                finally:
                    self.record('client_closed', transport='dedicated MAVLink UDP socket', retry_count=0)
            self.probe['status'] = 'read_pass'
            self.record('read_completed')
        except Exception as error:
            self.probe['status'] = 'failed'
            self.record('failure', error=str(error))
            raise
        super().execute()

    def report(self):
        return dict(super().report(), parameter_read=self.probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--prepared', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    config = read_config(args.config, args.run_id)
    if not args.prepared:
        if config.get('runtime_profile'):
            from Simulator.wksim_runtime.independent_profile import select_config
            _, profile = select_config(config)
            setup_files = profile['setup_files']
        else:
            setup_files = [config['dds_workspace'] + '/ros-install/setup.bash']
            if config['stack'] == 'arducopter':
                setup_files.append(config['ap_candidate'] + '/ros-install/local_setup.bash')
            setup_files.append(config['prometheus_workspace'] + '/install/local_setup.bash')
        script = '''set -eo pipefail
setup_count=$1
shift
for ((i=0; i<setup_count; i++)); do source "$1"; shift; done
export LD_LIBRARY_PATH="$1/agent-install/lib:${LD_LIBRARY_PATH:-}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
shift
exec python3 -B -m tools.probe_parameter_read --prepared "$@"
'''
        os.execvp('bash', ['bash', '-c', script, 'parameter-read', str(len(setup_files)),
            *setup_files, config['dds_workspace'], str(args.config.resolve()),
            '--run-id', args.run_id, '--output-root', str(args.output_root.resolve())])
    result = run(config, args.output_root, task_factory=ReadProbe)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
