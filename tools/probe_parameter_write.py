"""Candidate native write/read/restore probe followed by the standard Task flight."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import socket
import time

from tools.probe_parameter_read import ReadProbe, byte_evidence, read_config
from Simulator.wksim_runtime.parameter_protocol import ParameterProtocol, restore_request_value
from Simulator.wksim_runtime.runtime import run
from Simulator.wksim_runtime.task import Task


class WriteProbe(ReadProbe):
    def __init__(self, directory, *args, **kwargs):
        super().__init__(directory, *args, **kwargs)
        self.probe_phase = 'waiting_for_ground'
        self.probe.update(scope='candidate native write/read/restore plus standard public Task flight',
                          pending_restore=False, retry_count=0, standard_task_status='not_started',
                          write_contract={'arducopter': {'WP_SPD': [3, 10], 'step': 0.1},
                                          'px4': {'MPC_XY_CRUISE': [3, 5], 'step': 1}})
        for path in [Path(__file__), Path(__file__).with_name('run-parameter-write-probe.sh')]:
            self.probe['sources_sha256'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()

    def record(self, kind, **data):
        self.probe['evidence'].append(dict(kind=kind, phase=self.probe_phase,
            monotonic=time.monotonic(), unix=time.time(), **data))
        (self.directory / 'parameter-write.json').write_text(json.dumps(self.probe, indent=2) + '\n')

    def cycle(self, protocol, get, set_value):
        self.probe_phase = 'read_original'
        original = get(None)
        restore = restore_request_value(protocol.stack, protocol.name, original)
        self.probe.update(original_value=original, restore_request_value=restore)
        self.record('restore_prevalidated', original_value=original, request_value=restore)
        self.probe_phase = 'write_trial'
        set_value(4.0)
        self.probe_phase = 'read_trial'
        self.probe['trial_readback'] = get(4.0)
        self.record('trial_storage_confirmed', value=self.probe['trial_readback'])
        # No finally-based write: unknown outcomes or stale authority stop here.
        self.probe_phase = 'restore_original'
        set_value(restore)
        self.probe_phase = 'read_restored'
        restored = get(restore)
        if restored != original:
            raise RuntimeError('Restoration changed original storage value')
        self.probe.update(restored_value=restored, pending_restore=False)
        self.record('restore_storage_confirmed', value=restored)

    def write_attempt(self, value):
        # Persist uncertainty before transport publication, including send errors.
        self.probe['pending_restore'] = True
        self.probe['parameter_writes'] += 1
        self.probe['parameter_write_operations'].append(dict(phase=self.probe_phase, value=value,
                                                            status='unknown'))
        self.record('write_attempt', value=value)

    def write_ap(self, context):
        from rcl_interfaces.srv import GetParameters, SetParameters
        from rclpy.serialization import serialize_message
        clients = []
        self.probe.update(correlation='one real ROS future per serialized operation; CDR is not packet capture',
            services=['/ap/get_parameters', '/ap/set_parameters'])
        protocol = ParameterProtocol('arducopter', 'WP_SPD', context, self.ground_state, max_age=2)
        try:
            for service_type, service in [(GetParameters, '/ap/get_parameters'),
                                          (SetParameters, '/ap/set_parameters')]:
                client = self.node.create_client(service_type, service)
                clients.append(client)
                self.wait('parameter_service_ready', client.service_is_ready, 10)
                graph = self.node.get_service_names_and_types()
                expected_type = 'rcl_interfaces/srv/' + service_type.__name__
                self.record('service_graph', services=graph, actual_client_service=client.srv_name,
                            expected_type=expected_type, ready=client.service_is_ready())
                if client.srv_name != service or not any(name == service and expected_type in types
                                                       for name, types in graph):
                    raise RuntimeError('Fixed AP service name/type absent from actual graph')

            def call(client, request, value=None):
                future = None
                self.recheck_current(protocol)
                self.record('request', service=client.srv_name, message=self.convert(request),
                            raw=byte_evidence(serialize_message(request), 'ROS CDR'))
                if value is not None:
                    self.write_attempt(value)
                protocol.check_current()
                try:
                    future = client.call_async(request)
                    self.wait('parameter_response', future.done, 10)
                    response = future.result()
                    self.record('response', service=client.srv_name, message=self.convert(response),
                                raw=byte_evidence(serialize_message(response), 'ROS CDR'))
                    self.recheck_current(protocol)
                    return response
                finally:
                    if future is not None and not future.done():
                        future.cancel()

            def get(expected):
                return protocol.ap_get_value(call(clients[0], protocol.ap_get_request()), expected=expected)

            def set_value(value):
                accepted, reason = protocol.ap_set_result(call(clients[1], protocol.ap_set_request(value), value))
                self.probe['parameter_write_operations'][-1].update(
                    status='native_accepted' if accepted else 'native_rejected', reason=reason)
                self.record('set_result', successful=accepted, reason=reason)
                if not accepted:
                    raise RuntimeError('Native SetParameters rejected: ' + reason)

            self.cycle(protocol, get, set_value)
        finally:
            for client in clients:
                self.node.destroy_client(client)
            self.record('clients_closed', transport='ROS GetParameters and SetParameters', count=len(clients))

    def write_px4(self, context):
        from Simulator.wksim_runtime.telemetry_dialect import load_dialect
        dialect, identity = load_dialect('px4')
        peer = ('127.0.0.1', 18591)
        self.probe.update(dialect=identity, local=['127.0.0.1', 14661], peer=peer,
            target_system=22, target_component=1, source_system=245, source_component=190,
            correlation='PARAM_VALUE has no native request_id; observed storage only, not COMMAND_ACK or strong causal correlation')
        encoder = dialect.MAVLink(None, srcSystem=245, srcComponent=190)
        parser = dialect.MAVLink(None)
        try:
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
                    return [(message, sender, raw) for message in parser.parse_buffer(raw) or []]

                deadline = time.monotonic() + 10
                heartbeat_seen = False
                while not heartbeat_seen:
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
                        heartbeat_seen = True
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Expected PX4 heartbeat not observed')
                protocol = ParameterProtocol('px4', 'MPC_XY_CRUISE', context, self.ground_state,
                    max_age=2, dialect=dialect, peer=peer, target_system=22, target_component=1)

                def exchange(request, expected, value=None):
                    nonlocal parser
                    drained = 0
                    deadline = time.monotonic() + 1
                    while True:
                        try:
                            channel.recvfrom(65535)
                            drained += 1
                        except BlockingIOError:
                            break
                        if drained >= 10000 or time.monotonic() >= deadline:
                            raise TimeoutError('PX4 pre-request drain did not quiesce')
                    parser = dialect.MAVLink(None)
                    self.record('input_drained', datagrams=drained)
                    raw = request.pack(encoder)
                    self.recheck_current(protocol)
                    self.record('request_prepared', peer=peer, message=request.to_dict(),
                                raw=byte_evidence(raw, 'MAVLink UDP datagram'))
                    if value is not None:
                        self.write_attempt(value)
                    protocol.check_current()
                    sent = channel.sendto(raw, peer)
                    encoder.seq = (encoder.seq + 1) % 256
                    self.record('request_sent', peer=peer, bytes_sent=sent,
                                raw=byte_evidence(raw, 'MAVLink UDP datagram'))
                    if sent != len(raw):
                        raise RuntimeError('Incomplete parameter send; result unknown')
                    deadline = time.monotonic() + 10
                    while True:
                        for message, sender, raw in receive():
                            if message.get_type() != 'PARAM_VALUE':
                                continue
                            self.record('response', peer=sender, source_system=message.get_srcSystem(),
                                source_component=message.get_srcComponent(), message=message.to_dict(),
                                raw=byte_evidence(raw, 'MAVLink UDP datagram'))
                            self.recheck_current(protocol)
                            return protocol.px4_value(message, peer=sender, context=context, expected=expected)
                        if time.monotonic() >= deadline:
                            raise TimeoutError('PARAM_VALUE unknown/timeout; no retry or native rejection inferred')

                def get(expected):
                    return exchange(protocol.px4_read_message(), expected)

                def set_value(value):
                    observed = exchange(protocol.px4_set_message(value), value, value)
                    self.probe['parameter_write_operations'][-1]['status'] = 'observed'
                    self.record('set_value_observed', value=observed, native_request_id=None)

                self.cycle(protocol, get, set_value)
        finally:
            self.record('clients_closed', transport='dedicated MAVLink UDP socket')

    def execute(self):
        try:
            self.wait('parameter_public_physical_ground_ready', self.ready, 55)
            context = self.ground_state().context
            self.probe.update(context=asdict(context), status='running',
                              parameter='WP_SPD' if self.flight_stack == 'arducopter' else 'MPC_XY_CRUISE')
            if self.flight_stack == 'arducopter':
                self.write_ap(context)
            else:
                self.write_px4(context)
            self.probe['status'] = 'write_read_restore_pass'
            self.probe_phase = 'standard_task'
            self.probe['standard_task_status'] = 'running'
            self.record('parameter_cycle_completed')
            Task.execute(self)
            self.probe['standard_task_status'] = 'completed'
            self.record('standard_task_completed')
        except Exception as error:
            self.probe['status'] = 'failed'
            self.record('failure', error=str(error), automatic_recovery_write=False)
            raise

    def report(self):
        return dict(Task.report(self), parameter_write=self.probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--prepared', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    config = read_config(args.config, args.run_id)
    if args.output_root.exists():
        raise ValueError('Write probe requires a new output-root')
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
exec python3 -B -m tools.probe_parameter_write --prepared "$@"
'''
        os.execvp('bash', ['bash', '-c', script, 'parameter-write', str(len(setup_files)),
            *setup_files, config['dds_workspace'], str(args.config.resolve()),
            '--run-id', args.run_id, '--output-root', str(args.output_root.resolve())])
    result = run(config, args.output_root, task_factory=WriteProbe)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
