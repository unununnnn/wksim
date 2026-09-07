"""Read-only raw evidence audit of a formal joint product run (ROS environment)."""
import argparse
import json
from pathlib import Path
import struct
import sys

from audit_joint_flight import audit_timeline, digest, lines, require
from Simulator.wksim_runtime.joint_evidence import verify_tasks


class ProductTimeline:
    """Only a filename adapter: both producers use the same JointPhysics schema."""
    def __init__(self, directory):
        self.directory = directory

    def __truediv__(self, name):
        return self.directory / ('wire.jsonl' if name == 'joint-wire.jsonl' else name)


def cdr_string(raw):
    data = bytes.fromhex(raw)
    require(data[:4] == b'\x00\x01\x00\x00', 'Unsupported String CDR encoding')
    size = struct.unpack_from('<I', data, 4)[0]
    require(size > 0 and len(data) == size + 8 and data[-1] == 0, 'Truncated String CDR')
    return json.loads(data[8:-1].decode('utf8'))


def lifecycle(directory, epoch, total, publications, run_id):
    repeated = 0
    permissions = 0
    for row in lines(directory / 'scene-lifecycle.jsonl'):
        require(row['epoch'] == epoch and 0 <= row['tick'] <= total, 'Lifecycle epoch/tick differs')
        if row['kind'] == 'permission':
            value = cdr_string(row['cdr_hex'])
            require(value == row['message'] and value['run_id'] == run_id
                    and value['scene_epoch'] == epoch and value['tick'] == row['tick']
                    and value['time_ns'] == row['tick'] * 1000000
                    and value['phase'] == row['phase'] and value['lease_seconds'] == .5,
                    'Raw permission differs from recorded authority')
            permissions += 1
        elif row['kind'] in ('paused_clock', 'faulted_clock'):
            repeated += 1
            require(row['phase'] in ('paused', 'faulted')
                    and (row['phase'] == 'faulted' or row['tick'] % 4 == 0)
                    and row['time_ns'] == row['tick'] * 1000000
                    and row['publication'] == row['tick'] + 1 + repeated,
                    'Clock retransmission fabricated time/publication')
        elif row['kind'] == 'ack_raw':
            cdr_string(row['cdr_hex'])
    require(permissions > 0 and publications == total + 1 + repeated, 'Missing raw clock/lifecycle records')
    return dict(permissions=permissions, clock_republications=repeated)


def public_dds(directory, epoch, total, run_id):
    from rclpy.serialization import deserialize_message
    from wksim_msgs.msg import SessionState
    from prometheus_msgs.msg import TextInfo
    counts = {1: 0, 2: 0}
    final = {}
    accepted = {1: set(), 2: set()}
    for row in lines(directory / 'public-dds.jsonl'):
        require(row['epoch'] == epoch and 0 <= row['tick'] <= total, 'DDS crossed scene identity/time')
        uid = next((uid for uid in (1, 2) if row['topic'].startswith(f'/uav{uid}/prometheus/')), None)
        require(uid is not None, 'Unexpected public vehicle/topic')
        suffix = row['topic'].split('/prometheus/')[1]
        require(suffix in ('v2/state', 'text_info'), 'Unexpected public message type')
        message = deserialize_message(bytes.fromhex(row['cdr_hex']), SessionState if suffix == 'v2/state' else TextInfo)
        if suffix == 'v2/state':
            require(message.run_id == run_id and message.state.uav_id == message.control.uav_id == uid,
                    'Raw DDS participant identity differs')
            counts[uid] += 1
            final[uid] = message
        else:
            event = json.loads(message.message)
            require(event['run_id'] == run_id, 'Raw public event crossed run identity')
            require(event['event'] not in ('setup_rejected', 'command_rejected', 'control_revoked'),
                    'Healthy run contains a raw rejected/revoked operation')
            if event['event'] == 'native_ack' and event.get('accepted'):
                accepted[uid].add((event['request_id'], event['stage']))
    require(all(counts.values()), 'Missing raw dual public state')
    for message in final.values():
        require(message.state.connected and message.state.odom_valid and not message.state.armed
                and abs(message.state.position[2]) < .3, 'Raw final DDS state not landed/disarmed')
    expected = {(1, 'simple'), (2, 'simple'), (3, 'takeoff'), (3, 'external'), (5, 'land'), (6, 'simple')}
    require(all(expected <= requests for requests in accepted.values()),
            'Raw DDS lacks the six native setup stages per vehicle')
    return counts


def audit_product_timeline(directory, result, *, require_flight=True):
    """Single-epoch flight timeline only; caller separately proves lifecycle/task outcome."""
    epoch = result['epoch']; authority = result['authority']; total = authority['tick']
    # Do not synthesize diagnostic lifecycle status: its timeline function is
    # used only for unique clock ticks, raw native packets and model requests.
    timeline, _ = audit_timeline(ProductTimeline(directory), dict(final_authority=authority,
        scene_epoch=epoch, clock_publications=total + 1),require_flight=require_flight)
    steps = 0; previous_tick = 0; previous_wall = -1.; strict = 0; synchronized = False
    for row in lines(directory / 'wire.jsonl'):
        require(row['tick'] >= previous_tick and row['issued_monotonic_s'] >= previous_wall,
                'Raw wire ordering moved backwards')
        previous_tick, previous_wall = row['tick'], row['issued_monotonic_s']
        if row['kind'] == 'step':
            steps += 1
            require(row['tick'] == steps, 'Duplicate or missing raw step')
        if row['kind'] == 'barrier':
            require(not synchronized or row['synchronized'], 'Native barrier lost synchronization')
            synchronized |= row['synchronized']
            strict += int(row['synchronized'])
    require(steps == total and strict > 0, 'No complete synchronized native timeline')
    life = lifecycle(directory, epoch, total, result['clock_publications'], result['run_id'])
    timeline['clock_publications'] = result['clock_publications']
    timeline.pop('paused_clock_republications')
    timeline.pop('faulted_clock_republications')
    return timeline, strict, life


def audit_epoch(root, item, run_id):
    epoch = item['epoch']
    require(len(epoch) == 32 and all(c in '0123456789abcdef' for c in epoch), 'Invalid epoch path')
    directory = root / 'epochs' / epoch
    result = json.loads((directory / 'result.json').read_text())
    require(result == item['result'] and result['epoch'] == epoch and result['run_id'] == run_id,
            'Manager and epoch original results differ')
    require(result['status'] == 'stopped' and not result['cleanup_errors'], 'Epoch did not stop cleanly')
    require(not item['remaining_group_members'], 'Owned epoch group remained')
    if 'unowned_ap_before' in result:
        require(result['unowned_ap_before'] == result['unowned_ap_after'], 'Recorded unowned AP identity changed')
    else:
        require(isinstance(result.get('host_boot_id'),str) and len(result['host_boot_id'])==36,
                'Missing recorded host identity')
    authority = result['authority']; total = authority['tick']
    require(0 < total <= 180000 and total % 4 == 0 and authority['phase'] == 'stopped'
            and authority['pending_tick'] is None and authority['time_ns'] == total * 1000000,
            'Invalid terminal authority')
    for name, child in result['children'].items():
        require(child['identity']['pgid'] == item['process_identity'] and child['returncode'] is not None,
                'Unretired or foreign child ' + name)
        if '-agent' not in name:
            require(child['returncode'] == 0, 'Non-normal child exit ' + name)
    preflight = json.loads((directory / 'preflight.json').read_text())
    require(preflight == result['preflight'] and preflight['ok'], 'Original preflight differs')
    model_identity = preflight['identities']['model']
    for stack in ('arducopter', 'px4'):
        config = preflight['configs'][stack]
        argv = result['children'][stack + '-model']['argv']
        require(config['model_profile'] == 'quad_x' and config['model_library'] == model_identity['library']
                and argv[argv.index('--library') + 1] == model_identity['library']
                and argv[argv.index('--epoch') + 1] == epoch, 'Executed model selection differs')
    timeline, strict, life = audit_product_timeline(directory, result)
    reports = {}
    for path in directory.glob('tasks/*/*/result.json'):
        report = json.loads(path.read_text()); name = path.parent.name + '-task-' + path.parent.parent.name
        require(report == result['tasks'][name] and report['status'] == 'pass'
                and report['run_id'] == run_id and report['scene_epoch'] == epoch,
                'Task result identity/completion differs')
        require(report['task_mode'] == 'initial', 'Recovery needs a dedicated raw lifecycle audit')
        phases = report['phases']
        require(len({p['phase'] for p in phases}) == len(phases), 'Duplicate task phase')
        require(all(type(p['ros_time_ns']) is int and 0 < p['ros_time_ns'] <= total * 1000000
                    and p['ros_time_ns'] % 1000000 == 0 for p in phases), 'Task window outside retained timeline')
        require(all(a['ros_time_ns'] <= b['ros_time_ns'] for a,b in zip(phases, phases[1:])),
                'Task phases moved backwards')
        require(any(p['phase'] == 'normal_stop_ready' for p in phases), 'Task lacks terminal phase')
        raw_requests = []; raw_payloads = []
        for row in lines(path.parent / 'prometheus.jsonl'):
            if row.get('request_envelope'):
                raw_requests.append(row['message'])
            if 'public_payload' in row:
                raw_payloads.append(row['message'])
        require(len(raw_requests) == 6 and raw_requests == report['task']['request_envelopes']
                and raw_payloads == report['task']['sent'], 'Task summary differs from original published requests')
        for number, request in enumerate(raw_requests, 1):
            require(request['run_id'] == run_id and request['control_epoch'] == report['task']['control_epoch']
                    and request['request_id'] == number and request['version'] == 1,
                    'Task request envelope identity/replay differs')
        reports[name] = report
    require(set(reports) == set(result['tasks']) and len(reports) == 2, 'Missing complete dual task results')
    physical = verify_tasks(directory, epoch, total, reports)
    require(physical is not None, 'No independent task physical proof')
    dds = public_dds(directory, epoch, total, run_id)
    return dict(epoch=epoch, timeline=timeline, strict_native_barriers=strict,
                simultaneous_flight_seconds=timeline['simultaneous_height_above_1m_ticks']/1000,
                physical_task_windows=physical, lifecycle=life, raw_dds_state_counts=dds,
                retained_model_selection=model_identity,
                remaining_group_members=item['remaining_group_members'])


def audit(root):
    result = json.loads((root / 'result.json').read_text())
    require(result['kind'] == 'joint_scene' and result['status'] == 'pass', 'Product run did not pass')
    require(len(result['epochs']) == 1, 'Cold reset requires a dedicated multi-epoch lifecycle audit')
    epochs = [audit_epoch(root, item, result['run_id']) for item in result['epochs']]
    return dict(status='pass', scope='Formal healthy dual public flight raw timeline and physical task windows',
                epochs=epochs, limitations=['Does not certify fault recovery, cold reset, live process absence, executed binary/source identity, or DDS publisher exclusivity; group absence is the retained manager observation.'],
                evidence_sha256={p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.directory.resolve()), 'Audit output must be outside raw evidence')
    try:
        report = audit(args.directory)
    except (ValueError, KeyError, OSError, ImportError, TypeError, IndexError) as error:
        report = dict(status='fail', error=str(error))
    report['audit_source_sha256'] = digest(Path(__file__))
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'evidence_sha256'}, indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
