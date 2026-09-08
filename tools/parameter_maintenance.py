"""Set a native parameter, fly, restart the FC with retained storage, then fly again.

This explicit maintenance experiment always runs TWO standard public single-
waypoint Task flights. It is not a read-only utility or Full/#43 acceptance.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

from tools.probe_parameter_read import byte_evidence, read_config
from tools.probe_parameter_write import WriteProbe
from tools.ros_subscription_match import MatchedPublishers
from Simulator.wksim_runtime.parameter_protocol import restore_request_value, validate_value
from Simulator.wksim_runtime.parameter_storage import ParameterStorage
from Simulator.wksim_runtime.runtime import run, parameter_storage_metadata
from Simulator.wksim_runtime.task import Task


def save(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def storage_snapshot(config, lease):
    result = parameter_storage_metadata(config, lease)
    # The runtime records bytes; this transaction also freezes each file inode.
    for name, record in result['parameter_files'].items():
        info = (lease.path / name).stat()
        record.update(device=info.st_dev, inode=info.st_ino)
    marker = (lease.path.parent / 'marker.json').stat()
    result['marker_identity'] = dict(device=marker.st_dev, inode=marker.st_ino)
    return result


def require_retained(before, after):
    if not before['parameter_files']:
        raise RuntimeError('FC left no native parameter storage file')
    for key in ('path', 'transaction_id', 'stack', 'marker_sha256', 'marker_identity',
                'directory_identity', 'parameter_files'):
        if before[key] != after[key]:
            raise RuntimeError('Retained storage differs before FC restart: ' + key)


def require_finished(result):
    if (result.get('status') != 'pass' or result.get('safe_landing') is not True
            or result.get('children_reaped') is not True or result.get('cleanup_errors') != []):
        raise RuntimeError('Phase did not pass flight, landing and owned-child cleanup gates')


def fixed_identity(result):
    identities = result['preflight']['identities']
    return dict(fc_binary=result['fc_binary'], fc_sha256=result['fc_sha256'],
                fc_commit=result['fc_commit'], agent_sha256=result['agent_sha256'],
                model=identities['model'], message_packages=identities['message_packages'],
                product_sha256=result['product_sha256'], runtime_sha256=result['runtime_sha256'])


def require_restart(before, after):
    if fixed_identity(before) != fixed_identity(after):
        raise RuntimeError('Fixed FC/model/messages/product/runtime identity changed across restart')
    old, new = before['children']['fc'], after['children']['fc']
    if old['pid'] == new['pid'] or old.get('returncode') is None:
        raise RuntimeError('FC retirement and a distinct new FC PID were not proven')
    if before['task']['control_epoch'] == after['task']['control_epoch']:
        raise RuntimeError('FC restart did not establish a new control epoch')


class MaintenanceTask(WriteProbe):
    def __init__(self, directory, *args, transaction, report_path, stage, **kwargs):
        super().__init__(directory, *args, **kwargs)
        self.transaction, self.report_path, self.stage = transaction, report_path, stage
        self.probe.update(scope=__doc__, stage=stage, target_value=transaction['target_value'],
                          pending_restore=transaction['pending_restore'])
        self.probe['sources_sha256'].update(transaction['sources_sha256'])
        self.channel_action = stage
        self.session_last_request = None
        if stage == 'after':
            # Task construction does not spin: reject old states from the first callback.
            self.retired_epochs.add(transaction['before_epoch'])
        self.record('task_created', retired_epochs=sorted(self.retired_epochs))

    def record(self, kind, **data):
        self.probe['evidence'].append(dict(kind=kind, phase=self.probe_phase,
            monotonic=time.monotonic(), unix=time.time(), **data))
        self.transaction['pending_restore'] = self.probe['pending_restore']
        self.transaction.setdefault('parameter_phases', {})[self.stage] = self.probe
        save(self.directory / 'parameter-maintenance.json', self.probe)
        save(self.report_path, self.transaction)

    def receive_session(self, msg):
        previous = self.session_sequence
        super().receive_session(msg)
        if self.session_sequence != previous:
            self.session_last_request = msg.last_request_id

    def write_attempt(self, value):
        self.transaction['current_value'] = None
        self.transaction['current_value_status'] = 'unknown_write_outcome'
        super().write_attempt(value)

    def send(self, msg, label, timeout=10):
        if self.stage != 'before' or not isinstance(msg, self.Cmd) or msg.agent_cmd != self.Cmd.MOVE:
            return Task.send(self, msg, label, timeout)
        from rclpy.serialization import serialize_message
        publisher = self.command_pub

        def publish(outgoing):
            if 'old_move_envelope' in self.transaction:
                raise RuntimeError('Before task attempted more than one MOVE')
            raw = serialize_message(outgoing)
            self.transaction.update(before_epoch=outgoing.control_epoch,
                old_move_envelope=self.convert(outgoing), old_move_cdr=byte_evidence(raw, 'ROS CDR'))
            self.record('before_move_publication_prepared', envelope=self.convert(outgoing),
                        raw=byte_evidence(raw, 'ROS CDR'))
            # Publish the bytes we retain; repeated CDR serialization has variable padding.
            publisher.publish(raw)
            self.transaction['before_move_publication_returned'] = True
            self.record('before_move_publication_returned', raw=byte_evidence(raw, 'ROS CDR'))

        self.command_pub = SimpleNamespace(publish=publish, get_subscription_count=publisher.get_subscription_count)
        try:
            return Task.send(self, msg, label, timeout)
        finally:
            self.command_pub = publisher

    def cycle(self, protocol, get, set_value):
        if self.channel_action == 'before':
            self.probe_phase = 'read_original'
            original = get(None)
            restore = restore_request_value(protocol.stack, protocol.name, original)
            self.transaction.update(original_value=original, restore_request_value=restore)
            self.probe.update(original_value=original, restore_request_value=restore)
            self.record('restore_prevalidated', original_value=original, request_value=restore)
            self.probe_phase = 'write_target'
            set_value(self.transaction['target_value'])
            self.probe_phase = 'independent_target_readback'
            actual = get(self.transaction['target_value'])
            self.probe['target_readback'] = actual
        elif self.channel_action == 'after':
            self.probe_phase = 'restart_readback_without_set'
            actual = get(self.transaction['target_value'])
            self.probe['restart_readback'] = actual
            self.transaction['persistence_readback'] = dict(value=actual, context=asdict(protocol.context),
                scope='new native GET after a real FC process restart with retained parameter files')
        elif self.channel_action == 'restore':
            self.probe_phase = 'pre_restore_readback'
            get(self.transaction['target_value'])
            self.probe_phase = 'restore_original'
            set_value(self.transaction['restore_request_value'])
            self.probe_phase = 'independent_restored_readback'
            actual = get(self.transaction['restore_request_value'])
            if actual != self.transaction['original_value']:
                raise RuntimeError('Restoration changed original native storage value')
            self.probe.update(restored_value=actual, pending_restore=False)
        else:
            raise RuntimeError('Unknown maintenance channel action')
        self.transaction.update(current_value=actual, current_value_status='observed_native_readback',
            last_readback=dict(value=actual, context=asdict(protocol.context), action=self.channel_action, unix=time.time()))
        self.record('independent_readback_completed', action=self.channel_action, value=actual)

    def parameter_channel(self):
        self.wait('parameter_public_physical_ground_ready', self.ready, 55)
        context = self.ground_state().context
        self.probe.update(context=asdict(context), parameter='WP_SPD' if self.flight_stack == 'arducopter'
                          else 'MPC_XY_CRUISE')
        self.record('new_parameter_operation', action=self.channel_action, context=asdict(context))
        (self.write_ap if self.flight_stack == 'arducopter' else self.write_px4)(context)
        self.record('parameter_channel_finished', action=self.channel_action)

    def reject_old_move(self):
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rclpy.qos_event import SubscriptionEventCallbacks
        from rclpy.serialization import deserialize_message, serialize_message
        if self.flight_stack == 'arducopter':
            from ardupilot_msgs.msg import GlobalPosition
            from geometry_msgs.msg import TwistStamped
            topics = [('/ap/cmd_gps_pose', GlobalPosition), ('/ap/cmd_vel', TwistStamped)]
        else:
            from px4_msgs.msg import TrajectorySetpoint, OffboardControlMode
            from prometheus_control.frames import topic
            topics = [(topic('/wksim_px4_21', 'in', name, cls), cls) for name, cls in
                      [('trajectory_setpoint', TrajectorySetpoint), ('offboard_control_mode', OffboardControlMode)]]
        subscriptions, writers, samples, alive = [], {}, [], {}
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        window = dict(status='running', topics=[name for name, _ in topics], counts={}, samples=samples)
        self.probe['old_epoch_native_window'] = window
        counter = MatchedPublishers()
        window['matching_api'] = counter.identity

        def matched():
            counts = {name: counter.count(sub) for (name, _), sub in zip(topics, subscriptions)}
            window['matched_publishers'] = counts
            return len(counts) == len(topics) and all(value == 1 for value in counts.values())

        def graph():
            found = {}
            for name, cls in topics:
                infos = self.node.get_publishers_info_by_topic(name)
                if not infos:
                    return None
                expected_type = cls.__module__.split('.')[0] + '/msg/' + cls.__name__
                if (len(infos) != 1 or infos[0].node_name != 'prometheus_native_control'
                        or infos[0].node_namespace != '/' or infos[0].topic_type != expected_type):
                    raise RuntimeError('Native motion topic lacks unique fixed Control publisher: ' + name)
                gid = bytes(infos[0].endpoint_gid).hex()
                if not gid or not any(bytes(infos[0].endpoint_gid)):
                    raise RuntimeError('Native motion publisher has no usable GID')
                found[name] = dict(gid=gid, node_name=infos[0].node_name,
                                   node_namespace=infos[0].node_namespace, topic_type=infos[0].topic_type)
            return found

        def observe(message, name):
            samples.append(dict(topic=name, monotonic=time.monotonic(),
                publisher_gid=writers.get(name, {}).get('gid'),
                publisher_gid_source='unique publisher graph; installed Humble callback provides no MessageInfo',
                message=self.convert(message),
                raw=byte_evidence(serialize_message(message), 'ROS CDR')))
            self.record('unexpected_native_motion_output', sample=samples[-1])

        try:
            for name, cls in topics:
                # Installed Humble Executor._take_subscription discards MessageInfo.
                def callback_for(name):
                    def callback(message):
                        observe(message, name)
                    return callback
                def liveliness_for(name):
                    def changed(event):
                        alive[name] = event.alive_count
                        self.record('native_observer_liveliness', topic=name, alive_count=event.alive_count,
                                    not_alive_count=event.not_alive_count)
                    return changed
                subscriptions.append(self.node.create_subscription(cls, name, callback_for(name), qos,
                    event_callbacks=SubscriptionEventCallbacks(liveliness=liveliness_for(name))))
            self.wait('native_motion_unique_publishers', lambda: graph() is not None and matched(), 10)
            writers.update(graph())
            window['publishers'] = writers
            self.wait('new_epoch_localization_ground_ready', lambda: self.ready()
                      and self.epoch not in self.retired_epochs
                      and self.setup_pub.get_subscription_count() == 1
                      and self.command_pub.get_subscription_count() == 1, 55)
            if self.request_id != 0 or self.session_last_request != 0 or self.envelopes:
                raise RuntimeError('New control session unexpectedly consumed a public request')
            raw = bytes.fromhex(self.transaction['old_move_cdr']['hex'])
            request = deserialize_message(raw, self.CommandRequest)
            if (byte_evidence(raw, 'ROS CDR') != self.transaction['old_move_cdr']
                    or self.convert(request) != self.transaction['old_move_envelope']
                    or request.command.agent_cmd != self.Cmd.MOVE
                    or request.run_id != self.run_id or request.control_epoch not in self.retired_epochs):
                raise RuntimeError('Recorded old MOVE envelope identity differs')
            start_events, sequence = len(self.events), self.session_sequence
            window.update(start_monotonic=time.monotonic(), start_sequence=sequence,
                          request_high_water_before=self.session_last_request)
            self.record('old_move_publication', envelope=self.convert(request), raw=byte_evidence(raw, 'ROS CDR'))
            # Publish the exact recorded envelope: never call send(), which replaces its identity/header.
            self.command_pub.publish(raw)
            rejection_at = None
            deadline = time.monotonic() + 10
            while True:
                self.pump()
                if not self.ready() or graph() != writers or not matched():
                    raise RuntimeError('Ground authority or unique native publisher changed during rejection window')
                if samples:
                    raise RuntimeError('Old-epoch rejection window observed native motion output')
                if self.request_id != 0 or self.session_last_request != 0:
                    raise RuntimeError('Rejected old envelope consumed new session request high-water mark')
                matches = [e for e in self.events[start_events:] if
                    e.get('event') == 'command_rejected' and e.get('reason') == 'wrong_run_or_control_epoch'
                    and e.get('run_id') == self.run_id and e.get('control_epoch') == self.epoch
                    and e.get('requested_run_id') == request.run_id
                    and e.get('requested_epoch') == request.control_epoch
                    and e.get('request_id') == request.request_id]
                if matches and rejection_at is None:
                    rejection_at = time.monotonic()
                    sequence = self.session_sequence
                    window.update(rejection=matches[0], rejection_monotonic=rejection_at)
                    self.record('old_move_rejected', event=matches[0])
                if (rejection_at is not None and time.monotonic() - rejection_at >= 1
                        and self.session_sequence > sequence):
                    window.update(status='pass', end_monotonic=time.monotonic(), end_sequence=self.session_sequence,
                                  request_high_water_after=self.session_last_request,
                                  counts={name: 0 for name, _ in topics})
                    self.record('old_epoch_zero_native_output_confirmed', window=window)
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError('Old MOVE rejection plus one-second native silence not confirmed')
        except BaseException as error:
            window.update(status='failed', error=str(error), end_monotonic=time.monotonic(),
                          counts={name: sum(sample['topic'] == name for sample in samples) for name, _ in topics})
            self.record('old_epoch_check_failed', window=window)
            raise
        finally:
            for subscription in subscriptions:
                self.node.destroy_subscription(subscription)
            self.record('native_motion_observers_closed', count=len(subscriptions))

    def execute(self):
        try:
            self.probe['status'] = 'running'
            if self.stage == 'after':
                self.probe_phase = 'old_epoch_rejection'
                self.reject_old_move()
            self.parameter_channel()
            self.probe_phase = 'standard_public_single_waypoint_flight'
            self.probe['standard_task_status'] = 'running'
            self.record('standard_task_started', new_public_envelopes=True)
            Task.execute(self)
            self.probe['standard_task_status'] = 'completed'
            self.active = False
            self.record('standard_task_completed')
            if self.stage == 'before':
                moves = [e for e in self.envelopes if e.get('command', {}).get('agent_cmd') == self.Cmd.MOVE]
                if (len(moves) != 1 or moves[0] != self.transaction.get('old_move_envelope')
                        or not self.transaction.get('before_move_publication_returned')
                        or self.epoch != self.transaction.get('before_epoch')):
                    raise RuntimeError('Standard before task did not retain its actual MOVE publication')
            elif self.transaction['restore_original']:
                self.channel_action = 'restore'
                self.operation_id = uuid.uuid4().hex
                self.parameter_channel()
            self.probe.update(status='maintenance_phase_completed', native_generation=self.native_generation)
            self.record('maintenance_phase_completed')
        except BaseException as error:
            self.probe['status'] = 'failed'
            self.record('failure', error=str(error), automatic_recovery_write=False)
            raise

    def report(self):
        return dict(Task.report(self), parameter_maintenance=self.probe)


def run_maintenance(config, output_root, value, restore_original=False):
    from Simulator.wksim_runtime.independent_profile import select_config
    if any(key in config for key in ('mission', 'display_socket', 'telemetry_socket',
                                    'gcs_udp_forward', 'restart_control_on_ground', 'promotion_flight')):
        raise ValueError('Maintenance requires a plain independent configuration without optional operation fields')
    config, _ = select_config(config)
    value = validate_value(config['stack'], 'WP_SPD' if config['stack'] == 'arducopter' else 'MPC_XY_CRUISE', value)
    output_root = Path(output_root).absolute()
    if (output_root.parent != Path('/root') or not output_root.name.startswith('wksim-')
            or output_root.resolve() != output_root or output_root.exists() or output_root.is_symlink()):
        raise ValueError('Maintenance output-root must be a new real /root/wksim-* directory')
    if type(restore_original) is not bool:
        raise ValueError('restore_original must be boolean')
    output_root.mkdir(mode=0o700)
    report_path = output_root / 'parameter-maintenance.json'
    sources = [Path(__file__), Path(__file__).with_name('run-wksim-parameter-mission.sh'),
               Path(__file__).with_name('probe_parameter_read.py'), Path(__file__).with_name('probe_parameter_write.py'),
               Path(__file__).with_name('ros_subscription_match.py'),
               Path(__file__).resolve().parents[1] / 'Simulator/wksim_runtime/parameter_protocol.py']
    transaction = dict(version=1, status='running', scope=__doc__, transaction_id=str(uuid.uuid4()),
        config=config, run_id=config['run_id'], target_value=value, restore_original=restore_original,
        pending_restore=False, current_value=None, current_value_status='not_read', stages={},
        sources_sha256={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        started_unix=time.time(), restart_operations=[], acceptance='experimental; #43 and Full remain unaccepted')
    save(report_path, transaction)
    lease = None
    options = {'px4_root': config['px4_root']} if config['stack'] == 'px4' else {}
    try:
        lease = ParameterStorage(transaction['transaction_id'], config['stack'], **options)
        transaction['storage_initial'] = storage_snapshot(config, lease)
        for stage in ('before', 'after'):
            def factory(directory, *args, **kwargs):
                return MaintenanceTask(directory, *args, transaction=transaction, report_path=report_path,
                                       stage=stage, **kwargs)
            transaction['active_stage'] = stage
            save(report_path, transaction)
            result = run(config, output_root / stage, task_factory=factory, parameter_storage=lease)
            transaction['stages'][stage] = result
            save(report_path, transaction)
            require_finished(result)
            maintenance = result['task']['parameter_maintenance']
            if (maintenance.get('status') != 'maintenance_phase_completed'
                    or maintenance.get('standard_task_status') != 'completed'):
                raise RuntimeError('Parameter phase or explicit standard Task did not complete')
            if stage == 'before':
                if not all(key in transaction for key in ('before_epoch', 'old_move_envelope', 'old_move_cdr',
                                                         'original_value', 'restore_request_value')):
                    raise RuntimeError('Before phase omitted original parameter or actual MOVE evidence')
                retired = storage_snapshot(config, lease)
                transaction['storage_before_retired'] = retired
                transaction['restart_operations'].append(dict(old_fc_pid=result['children']['fc']['pid'],
                    old_fc_returncode=result['children']['fc']['returncode'], status='retired_after_safe_flight',
                    old_epoch=result['task']['control_epoch'], unix=time.time()))
                save(report_path, transaction)
                lease.close()
                lease = ParameterStorage(transaction['transaction_id'], config['stack'], reopen=True, **options)
                resumed = storage_snapshot(config, lease)
                transaction['storage_after_before_start'] = resumed
                require_retained(retired, resumed)
                for source, expected in transaction['sources_sha256'].items():
                    if hashlib.sha256(Path(source).read_bytes()).hexdigest() != expected:
                        raise RuntimeError('Maintenance source changed between phases: ' + source)
                save(report_path, transaction)
            else:
                if (maintenance.get('old_epoch_native_window', {}).get('status') != 'pass'
                        or 'persistence_readback' not in transaction
                        or (restore_original and transaction['pending_restore'])):
                    raise RuntimeError('Restart readback, old-epoch silence or requested restoration incomplete')
                require_restart(transaction['stages']['before'], result)
                transaction['storage_final'] = storage_snapshot(config, lease)
                transaction['restart_operations'][-1].update(status='new_fc_and_task_completed',
                    new_fc_pid=result['children']['fc']['pid'], new_epoch=result['task']['control_epoch'])
        transaction['status'] = 'pass'
        transaction['pending_restore_meaning'] = ('target intentionally retained; original value recorded'
            if transaction['pending_restore'] else 'original native value independently read back')
    except BaseException as error:
        transaction.update(status='failed', error=str(error), automatic_recovery_write=False,
                           current_value=None, current_value_status='unknown_after_failure; see last_readback')
    finally:
        if lease is not None:
            lease.close()
        transaction['finished_unix'] = time.time()
        save(report_path, transaction)
    print(json.dumps(dict(status=transaction['status'], report=str(report_path),
                          current_value=transaction['current_value'], pending_restore=transaction['pending_restore'])), flush=True)
    return transaction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config_path', type=Path, nargs='?')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--value', type=float, required=True, help='target m/s; AP [3,10] step 0.1, PX4 [3,5] integer')
    parser.add_argument('--restore-original', action='store_true', help='restore after the second successful flight and new ground check')
    parser.add_argument('--prepared', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (args.config is None) == (args.config_path is None):
        parser.error('provide exactly one positional config or --config')
    path = args.config or args.config_path
    config = read_config(path, args.run_id)
    from Simulator.wksim_runtime.independent_profile import select_config
    config, profile = select_config(config)
    validate_value(config['stack'], 'WP_SPD' if config['stack'] == 'arducopter' else 'MPC_XY_CRUISE', args.value)
    if not args.prepared:
        script = '''set -eo pipefail
setup_count=$1
shift
for ((i=0; i<setup_count; i++)); do source "$1"; shift; done
export LD_LIBRARY_PATH="$1/agent-install/lib:${LD_LIBRARY_PATH:-}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
shift
exec python3 -B -m tools.parameter_maintenance --prepared "$@"
'''
        os.execvp('bash', ['bash', '-c', script, 'parameter-maintenance', str(len(profile['setup_files'])),
            *profile['setup_files'], profile['dds_workspace'], '--config', str(path.resolve()),
            '--run-id', args.run_id, '--output-root', str(args.output_root.absolute()), '--value', str(args.value),
            *(['--restore-original'] if args.restore_original else [])])
    return 0 if run_maintenance(config, args.output_root, args.value, args.restore_original)['status'] == 'pass' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print('wksim parameter maintenance: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
