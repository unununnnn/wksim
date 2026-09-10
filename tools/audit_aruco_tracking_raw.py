"""Read-only raw CDR + public command-chain audit of an ArUco joint tracking capture.

Entry is the preserved Windows capture root (report.json + run/) read via its WSL
path; --run-root names an explicit run directory instead. ROS is sourced only to
deserialize recorded CDR bytes — no nodes, no simulation, no compilation. Raw
records are the ground truth: the task report's sent list never substitutes for
raw publication, no native FC ACK or action completion is inferred, and public
acceptance requires an actual raw TextInfo terminal event. Recorder provenance is
reconciled against the retained epoch source and the pinned control build; 'mock'
provenance is rejected. Clock/wire reuse audit_product_timeline with its defaults
(the 100 ms / rate thresholds are not relaxed). Loss/occlusion→HOLD causality and
native setpoint closure are not retained in evidence, so a fully clean audit
reports 'pending' with the explicit uncovered list, never 'pass'.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

_HERE = Path(__file__).resolve()
for _p in (str(_HERE.parents[1]), str(_HERE.parents[0])):  # repo root, then tools/
    if _p not in sys.path:
        sys.path.insert(0, _p)
from audit_joint_flight import require, lines, digest  # noqa: E402
from audit_joint_product import audit_product_timeline  # noqa: E402

SCHEMA_VERSION = 1
INITIAL_HASH_SEED = '0' * 64
VALID_CDR_HEADERS = {b'\x00\x00', b'\x00\x01', b'\x00\x02', b'\x00\x03'}
STACK_UAV = {'arducopter': 1, 'px4': 2}
HOVER_AGENT_CMD = 2       # prometheus_msgs/msg/UAVCommand.msg:10 CURRENT_POS_HOVER
MOVE_AGENT_CMD = 4        # prometheus_msgs/msg/UAVCommand.msg:12 MOVE
XYZ_VEL_BODY_MODE = 4     # prometheus_msgs/msg/UAVCommand.msg:29 XYZ_VEL_BODY
DEFAULT_CONTROL = 0       # prometheus_msgs/msg/UAVCommand.msg:18 DEFAULT_CONTROL
ACTION_SCHEMA = 'wksim.aruco-public-command.v1'
RAW_NAME = 'aruco-raw-dds.jsonl'
BUILDER_PATH = 'Simulator/wksim_runtime/aruco_raw_capture.py'
REJECT_EVENTS = ('setup_rejected', 'command_rejected', 'control_revoked')
_HEX64 = frozenset('0123456789abcdef')

# This slice proves the raw public chain only; while these stay open the audit
# outcome is 'pending' even when every check below passes.
UNCOVERED = [
    'loss_hold_correlation: each adapter HOLD is matched to its raw CommandRequest '
    'and raw acceptance, but evidence does not retain enough to tie a consumed null '
    'observation / expired authority step to that specific HOLD; not claimed proven',
    'native_setpoint_correlation: raw PX4 TrajectorySetpoint / AP cmd_gps_pose CDR '
    'content is not yet mapped field-by-field to the public MOVE/HOLD it carries',
    'native_fc_ack_or_action_completion: only public TextInfo acceptance is proven; '
    'no native FC ACK or action completion is claimed',
    'dds_publisher_exclusivity and full executed process identity beyond the '
    'reconciled recorder/control build pins are outside this audit',
]


def ros_deserializer():
    """Real CDR deserialization via rclpy; the only ROS use in this audit."""
    from rclpy.serialization import deserialize_message
    from wksim_msgs.msg import SetupRequest, CommandRequest, SessionState
    from prometheus_msgs.msg import TextInfo
    types = {'wksim_msgs/msg/SetupRequest': SetupRequest,
             'wksim_msgs/msg/CommandRequest': CommandRequest,
             'wksim_msgs/msg/SessionState': SessionState,
             'prometheus_msgs/msg/TextInfo': TextInfo}

    def deserialize(cdr_bytes, type_name):
        require(type_name in types, 'Unexpected raw CDR type ' + str(type_name))
        return deserialize_message(cdr_bytes, types[type_name])
    return deserialize


def quantize32(value):
    """Protocol float32 quantization of a reported double; not a physical tolerance."""
    require(type(value) in (int, float) and math.isfinite(value), 'Non-finite public command field')
    return struct.unpack('<f', struct.pack('<f', float(value)))[0]


def record_sha(row):
    """Canonical-record hash exactly as Simulator/wksim_runtime/aruco_raw_capture.py computes it."""
    body = {k: v for k, v in row.items() if k != 'record_sha256'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX64


def verify_raw_capture(path, *, run_id, epoch, stack, uav_id):
    """Full hash chain, start/end counts and identity of one aruco-raw-dds.jsonl."""
    rows = list(lines(path))
    require(rows and rows[0].get('kind') == 'aruco_raw_capture_start'
            and rows[-1].get('kind') == 'aruco_raw_capture_end'
            and sum(r.get('kind') == 'aruco_raw_capture_start' for r in rows) == 1
            and sum(r.get('kind') == 'aruco_raw_capture_end' for r in rows) == 1,
            'Raw capture lacks exactly one start and one end record')
    previous = INITIAL_HASH_SEED
    for row in rows:
        require(row.get('schema_version') == SCHEMA_VERSION, 'Raw capture schema differs')
        require(row.get('prev_record_sha256') == previous, 'Raw capture hash chain broken')
        sha = record_sha(row)
        require(row.get('record_sha256') == sha, 'Raw capture record hash recomputation differs')
        previous = sha
    start, end, samples = rows[0], rows[-1], rows[1:-1]
    require(all(r.get('kind') == 'raw_cdr_sample' for r in samples), 'Unexpected raw record kind')
    require(start.get('run_id') == run_id and start.get('epoch') == epoch
            and start.get('stack') == stack and start.get('uav_id') == uav_id,
            'Raw capture identity differs from the task run')
    identity = start.get('source_identity') or {}
    require(identity.get('builder') == BUILDER_PATH
            and set(identity) == {'builder', 'builder_sha256', 'rc_take_source_sha256', 'rc_take_lib_sha256'}
            and all(_hex64(identity[k]) for k in
                    ('builder_sha256', 'rc_take_source_sha256', 'rc_take_lib_sha256')),
            "Raw capture provenance incomplete or not pinned ('mock' is not auditable)")
    channels = {c.get('topic') for c in start.get('channels') or []}
    require(f'/uav{uav_id}/prometheus/v2/setup' in channels
            and f'/uav{uav_id}/prometheus/v2/command' in channels,
            'Raw capture lacks the public request channels')
    counts = {}
    last_monotonic = -1
    for number, row in enumerate(samples, 1):
        require(row.get('take_sequence') == number, 'Raw capture take sequence gapped or reordered')
        require(row.get('topic') in channels, 'Raw sample on an undeclared channel')
        require(row.get('monotonic_ns', -1) >= last_monotonic, 'Raw capture write order moved backwards')
        last_monotonic = row['monotonic_ns']
        cdr = row.get('cdr_hex')
        require(isinstance(cdr, str) and len(cdr) >= 8 and len(cdr) % 2 == 0,
                'Raw CDR hex malformed')
        try:
            raw = bytes.fromhex(cdr)
        except ValueError:
            require(False, 'Raw CDR hex malformed')
        require(raw[:2] in VALID_CDR_HEADERS, 'Raw CDR encapsulation header differs')
        gid = row.get('publisher_gid')
        require(isinstance(gid, str) and gid and set(gid) <= _HEX64
                and any(c != '0' for c in gid), 'Raw publisher GID missing or zero')
        require(type(row.get('source_timestamp')) is int and type(row.get('received_timestamp')) is int,
                'Raw native timestamps missing')
        counts[row['topic']] = counts.get(row['topic'], 0) + 1
    require(end.get('status') == 'complete' and end.get('write_failures') == 0
            and not end.get('write_failure_reports'), 'Raw capture ended with write failures')
    require(end.get('total_samples') == len(samples) and end.get('samples_per_topic') == counts
            and end.get('final_hash_chain') == end.get('prev_record_sha256'),
            'Raw capture end counts/hash differ')
    return dict(start=start, end=end, samples=samples, counts=counts)


def reconcile_identity(capture, directory, preflight):
    """Recorder provenance versus the retained epoch source and pinned control build."""
    identity = capture['start']['source_identity']
    builder = directory / 'source' / Path(BUILDER_PATH)
    require(builder.is_file(), 'Retained epoch source lacks the raw capture builder')
    require(digest(builder) == identity['builder_sha256'],
            'Raw capture builder differs from the retained epoch source')
    candidate = (preflight.get('identities') or {}).get('control_candidate') or {}
    require(identity['rc_take_source_sha256'] == (candidate.get('python_sha256') or {}).get('rc_transport.py'),
            'rc_take source differs from the pinned control build')
    require(identity['rc_take_lib_sha256'] == candidate.get('rc_transport_sha256'),
            'rc_take library differs from the pinned control build')
    return dict(builder_sha256=identity['builder_sha256'],
                rc_take_source_sha256=identity['rc_take_source_sha256'],
                rc_take_lib_sha256=identity['rc_take_lib_sha256'])


def require_move_fields(fields, body, command_id, origin):
    """Full public MOVE cross-check: every axis and mode under float32 protocol quantization."""
    require(fields.get('agent_cmd') == 'MOVE' and fields.get('move_mode') == 'XYZ_VEL_BODY'
            and fields.get('yaw_rate_mode') is True, origin + ' MOVE fields incomplete')
    require(body.agent_cmd == MOVE_AGENT_CMD and body.move_mode == XYZ_VEL_BODY_MODE
            and body.control_level == DEFAULT_CONTROL and body.command_id == command_id
            and body.yaw_rate_mode is True, 'Raw MOVE differs from the ' + origin)
    velocity = fields.get('velocity_ref')
    require(isinstance(velocity, list) and len(velocity) == 3
            and all(quantize32(value) == body.velocity_ref[axis]
                    for axis, value in enumerate(velocity)),
            'Raw MOVE velocity axes differ from the ' + origin)
    require(quantize32(fields.get('yaw_rate_ref')) == body.yaw_rate_ref,
            'Raw MOVE yaw rate differs from the ' + origin)


def require_hover_fields(body, command_id):
    require(body.agent_cmd == HOVER_AGENT_CMD and body.control_level == DEFAULT_CONTROL
            and body.command_id == command_id, 'Raw HOLD differs from the adapter action')


def public_chain(capture, report, *, run_id, uav_id, deserialize):
    """Raw requests/state/events on exactly this vehicle's public topics versus the report."""
    task = report['task']
    control_epoch = task['control_epoch']
    require(isinstance(control_epoch, str) and len(control_epoch) == 32
            and set(control_epoch) <= _HEX64, 'Task control epoch identity invalid')
    base = f'/uav{uav_id}/prometheus/'
    setup_topic, command_topic = base + 'v2/setup', base + 'v2/command'
    state_topic, info_topic = base + 'v2/state', base + 'text_info'
    requests, events, states, rejected = [], {}, 0, []
    for row in capture['samples']:
        topic = row['topic']
        if '/prometheus/' in topic:
            require(topic.startswith(base), 'Raw sample crossed the public vehicle boundary')
        if topic in (setup_topic, command_topic):
            message = deserialize(bytes.fromhex(row['cdr_hex']), row['type'])
            require(message.version == 1 and message.run_id == run_id
                    and message.control_epoch == control_epoch,
                    'Raw public request identity/epoch differs')
            body = message.setup if topic == setup_topic else message.command
            requests.append(dict(kind='setup' if topic == setup_topic else 'command',
                                 request_id=message.request_id, body=body, sample=row))
        elif topic == info_topic:
            message = deserialize(bytes.fromhex(row['cdr_hex']), row['type'])
            event = json.loads(message.message)
            require(event.get('run_id') == run_id and event.get('control_epoch') == control_epoch,
                    'Raw public event identity/epoch differs')
            events.setdefault(event.get('request_id'), []).append(event)
            if event.get('event') in REJECT_EVENTS:
                rejected.append(event.get('event'))
        elif topic == state_topic:
            message = deserialize(bytes.fromhex(row['cdr_hex']), row['type'])
            require(message.version == 1 and message.run_id == run_id
                    and message.control_epoch == control_epoch and message.state.uav_id == uav_id,
                    'Raw session state identity/epoch differs')
            states += 1
    require(states > 0, 'No raw session state on the public chain')
    require(not rejected, 'Raw public chain contains rejected/revoked operations: '
            + ','.join(sorted(set(rejected))))
    envelopes = task['request_envelopes']
    require([r['request_id'] for r in requests] == [e['request_id'] for e in envelopes]
            and len({r['request_id'] for r in requests}) == len(requests),
            'Raw public requests differ from the reported request envelopes')
    for raw, envelope in zip(requests, envelopes):
        payload = envelope['setup' if raw['kind'] == 'setup' else 'command']
        require(envelope['run_id'] == run_id and envelope['control_epoch'] == control_epoch
                and envelope['version'] == 1, 'Reported envelope identity differs')
        if raw['kind'] == 'command':
            require(payload['command_id'] == raw['body'].command_id
                    and payload['agent_cmd'] == raw['body'].agent_cmd
                    and payload['control_level'] == raw['body'].control_level,
                    'Raw command payload differs from the reported envelope')
            if payload['agent_cmd'] == MOVE_AGENT_CMD:
                require(payload.get('move_mode') == raw['body'].move_mode
                        and isinstance(payload.get('velocity_ref'), list)
                        and len(payload['velocity_ref']) == 3
                        and all(quantize32(value) == raw['body'].velocity_ref[axis]
                                for axis, value in enumerate(payload['velocity_ref']))
                        and bool(payload.get('yaw_rate_mode')) == bool(raw['body'].yaw_rate_mode)
                        and quantize32(payload.get('yaw_rate_ref', 0)) == raw['body'].yaw_rate_ref,
                        'Raw MOVE fields differ from the reported envelope')
        else:
            require(payload['cmd'] == raw['body'].cmd, 'Raw setup payload differs from the reported envelope')
    terminal = {}
    for raw in requests:
        outcome = [e for e in events.get(raw['request_id'], [])
                   if e.get('event') in (('setup_completed', 'setup_rejected') if raw['kind'] == 'setup'
                                         else ('command_accepted', 'command_rejected'))]
        require(len(outcome) == 1, 'Raw public request lacks exactly one raw terminal event')
        event = outcome[0]
        if raw['kind'] == 'command':
            require(event.get('command_id') == raw['body'].command_id,
                    'Raw terminal event command identity differs')
        terminal[raw['request_id']] = event
    return dict(requests=requests, terminal=terminal, session_states=states)


def adapter_chain(chain, report, *, run_id, epoch, selected):
    """report.task.aruco adapter_actions/observation_links versus the raw commands actually sent."""
    task = report.get('task') or {}
    aruco = task.get('aruco')
    require(isinstance(aruco, dict), 'Task report lacks the task.aruco block')
    require(aruco.get('selected') is selected and _hex64(aruco.get('profile_sha256')),
            'ArUco selection/profile identity differs')
    actions = aruco.get('adapter_actions')
    raw_commands = {r['body'].command_id: r for r in chain['requests'] if r['kind'] == 'command'}
    moves = [r for r in chain['requests'] if r['kind'] == 'command' and r['body'].agent_cmd == MOVE_AGENT_CMD]
    if not selected:
        require(actions is None and not aruco.get('observation_links'), 'Peer task carried an adapter')
        require(not moves, 'Peer published a visual MOVE')
        return dict(actions=0, sent=0)
    require(isinstance(actions, list), 'Selected task lacks adapter actions')
    sent = 0
    for action in actions:
        require(action.get('schema') == ACTION_SCHEMA and action.get('run_id') == run_id
                and action.get('scene_epoch') == epoch, 'Adapter action identity differs')
        command_id = action.get('command_id')
        if command_id is None:
            require(action.get('action') in ('suppressed_hold', 'duplicate_record'),
                    'Adapter action without command_id must be a suppression')
            continue
        raw = raw_commands.get(command_id)
        require(raw is not None, 'Adapter action has no raw CommandRequest; task.sent is not proof')
        sent += 1
        if action['action'] == 'move':
            require_move_fields(action.get('public_fields') or {}, raw['body'], command_id,
                                'adapter action')
        else:
            require(action['action'] == 'hover', 'Unknown adapter action ' + str(action.get('action')))
            require_hover_fields(raw['body'], command_id)
        if action.get('send_failed'):
            require(action.get('ack_unconfirmed'), 'Failed send must stay ack-unconfirmed')
            continue  # No acceptance is fabricated for a send whose ACK wait raised.
        event = chain['terminal'].get(raw['request_id'])
        require(event is not None and event.get('event') == 'command_accepted',
                'Adapter command lacks raw public acceptance')
    adapter_moves = {a['command_id'] for a in actions if a.get('action') == 'move'}
    require({r['body'].command_id for r in moves} <= adapter_moves,
            'Raw visual MOVE without an adapter action')
    for link in aruco.get('observation_links') or []:
        require(_hex64(link.get('image_sha256')), 'Observation link image identity invalid')
        if link.get('command_id') is not None:
            require(any(a.get('command_id') == link['command_id'] and a.get('action') == link.get('action')
                        for a in actions), 'Observation link lacks its adapter action')
    return dict(actions=len(actions), sent=sent)


def audit(root, *, run_root=None, deserialize=None, product_timeline=audit_product_timeline):
    root = Path(root)
    if deserialize is None:
        deserialize = ros_deserializer()
    entry = {}
    if run_root is None:
        report_path = root / 'report.json'
        require(report_path.is_file(), 'Capture root lacks report.json (expected <case>/report.json + run/)')
        require((root / 'run' / 'result.json').is_file(), 'Capture root lacks run/result.json')
        case_report = json.loads(report_path.read_text(encoding='utf-8'))
        entry['capture_report_sha256'] = digest(report_path)
        run_root = root / 'run'
    else:
        run_root = Path(run_root)
        require((run_root / 'result.json').is_file(), 'Explicit --run-root lacks result.json')
        case_report = None
    result = json.loads((run_root / 'result.json').read_text(encoding='utf-8'))
    run_id = result['run_id']
    if case_report is not None:
        session = case_report.get('session')
        require(isinstance(session, dict) and session.get('run_id') == run_id,
                'Capture report session differs from the run identity')
    require(len(result['epochs']) == 1, 'Multi-epoch ArUco run needs a dedicated lifecycle audit')
    item = result['epochs'][0]
    epoch = item['epoch']
    require(isinstance(epoch, str) and len(epoch) == 32 and set(epoch) <= _HEX64, 'Invalid epoch path')
    directory = run_root / 'epochs' / epoch
    epoch_result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    require(epoch_result == item['result'] and epoch_result['run_id'] == run_id,
            'Manager and epoch original results differ')
    preflight = json.loads((directory / 'preflight.json').read_text(encoding='utf-8'))
    require(preflight == epoch_result.get('preflight') and preflight.get('ok'),
            'Original preflight differs')
    timeline, strict, life = product_timeline(directory, epoch_result)
    stacks = {}
    selected_count = 0
    for stack, uav_id in STACK_UAV.items():
        matches = sorted(directory.glob('tasks/*/' + stack + '/result.json'))
        require(len(matches) == 1, 'Missing unique ' + stack + ' task result')
        path = matches[0]
        name = path.parent.name + '-task-' + path.parent.parent.name
        report = json.loads(path.read_text(encoding='utf-8'))
        require(report == epoch_result['tasks'][name] and report['run_id'] == run_id
                and report['scene_epoch'] == epoch, 'Task result identity differs')
        capture = verify_raw_capture(path.parent / RAW_NAME, run_id=run_id, epoch=epoch,
                                     stack=stack, uav_id=uav_id)
        pins = reconcile_identity(capture, directory, preflight)
        chain = public_chain(capture, report, run_id=run_id, uav_id=uav_id, deserialize=deserialize)
        selected = bool((report['task'].get('aruco') or {}).get('selected'))
        selected_count += int(selected)
        adapter = adapter_chain(chain, report, run_id=run_id, epoch=epoch, selected=selected)
        require(report['status'] == 'pass',
                stack + ' task did not pass; a failed task cannot yield a clean pending')
        stacks[stack] = dict(samples=capture['end']['total_samples'],
                             counts=capture['counts'], session_states=chain['session_states'],
                             selected=selected, provenance=pins, adapter=adapter)
    require(selected_count == 1, 'Exactly one stack must own the bound camera')
    return dict(status='pending', entry=entry or {'run_root': str(run_root)},
                run_id=run_id, epoch=epoch, stacks=stacks,
                strict_native_barriers=strict, lifecycle=life, timeline=timeline,
                uncovered=list(UNCOVERED),
                limitations=['Raw public chain and shared product timeline only; '
                             'loss-HOLD causality, native setpoint closure, native ACK and '
                             'publisher exclusivity are not certified.'],
                evidence_sha256={p.relative_to(run_root).as_posix(): digest(p)
                                 for p in sorted(run_root.rglob('*')) if p.is_file()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path,
                        help='WSL path of the preserved Windows capture root (report.json + run/)')
    parser.add_argument('--run-root', type=Path, default=None,
                        help='Explicit run directory instead of the capture root layer')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    evidence_root = args.run_root if args.run_root is not None else args.root
    require(not args.output.resolve().is_relative_to(evidence_root.resolve()),
            'Audit output must be outside raw evidence')
    try:
        report = audit(args.root, run_root=args.run_root)
    except (ValueError, KeyError, OSError, ImportError, TypeError, IndexError) as error:
        report = dict(status='fail', error=str(error), uncovered=list(UNCOVERED))
    report['audit_source_sha256'] = digest(_HERE)
    with args.output.open('x') as stream:  # Never overwrite retained evidence.
        stream.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'evidence_sha256'}, indent=2))
    return {'pass': 0, 'pending': 2}.get(report['status'], 1)


if __name__ == '__main__':
    sys.exit(main())
