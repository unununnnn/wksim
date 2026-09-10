"""Read-only raw CDR + public command-chain audit of an ArUco joint tracking capture.

Entry is the preserved Windows capture root (report.json + run/) read via its WSL
path; --run-root names an explicit run directory instead. ROS is sourced only to
deserialize recorded CDR bytes — no nodes, no simulation, no compilation. Raw
records are the ground truth: the task report's sent list never substitutes for
raw publication, no native FC ACK or action completion is inferred, and public
acceptance requires an actual raw TextInfo terminal event. Recorder provenance is
reconciled against the retained epoch source and the pinned control build; 'mock'
provenance is rejected. Clock/wire reuse audit_product_timeline with its defaults
(the 100 ms / rate thresholds are not relaxed). When the capture report retains
binding/frames/observations, an independent loss-HOLD gate runs a temporal state
machine over actual consumption and the adapter's own step invariants: frames and
observations reconcile pairwise against both bindings and the frozen profile file
(real Consumer contract — sensor_id is a string, target step/frame_id are decimal
strings, valid_until_step an int), every retained PNG is rehashed inside the
capture-root boundary, link-less HOLDs are legal only as the real task's initial /
cached-MOVE-expiry / final-boundary shapes, and the gate closes only after a full
null/expired-invalidation -> TTL withdrawal -> recovery cycle is proven; otherwise
it reports not_exercised. Native setpoint closure is not retained in evidence, so
a fully clean audit reports 'pending' with the explicit uncovered list, never
'pass'. A public ACK is never treated as action completion.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
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
BINDING_SCHEMA = 'wksim.aruco-binding.v1'          # run_aruco_tracking.py / aruco_joint_task.py
OBSERVATION_SCHEMA = 'wksim.aruco-observation.v1'  # run_aruco_tracking.py:74
TARGET_SCHEMA = 'wksim.aruco-target.v1'            # wksim_perception/target_intent.py:8
RGB_NOTICE_SCHEMA = 'wksim.rgb-ready.v2'
RGB_METADATA_SCHEMA = 'wksim.rgb.v2'
_HEX64 = frozenset('0123456789abcdef')
_WINDOWS_ABS = re.compile(r'^([A-Za-z]):[\\/](.*)$')

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


PROFILE_REL = 'Simulator/wksim_runtime/aruco-tracking-v1.json'
MAX_AUTHORITY_STEP = 9007199254  # aruco_tracking_input.MAX_STEP
SCENE_STEP_KEYS = ('initial_steps', 'moving_steps', 'occluded_steps', 'recovery_steps')
_STEP_STRING = re.compile(r'0|[1-9][0-9]{0,18}')
_SENSOR_ID = re.compile(r'[A-Za-z0-9_-]{1,96}')


def _basename(path_text):
    """Basename of a stored Windows path on any host (both separators split)."""
    return re.split(r'[\\/]', str(path_text))[-1]


def _stepish(value, name, high=MAX_AUTHORITY_STEP):
    """Strict authority-step parse mirroring aruco_joint_task._stepish: Consumer
    metadata and targets carry decimal strings; lax int() coercions and bools reject."""
    if isinstance(value, str):
        require(_STEP_STRING.fullmatch(value) is not None,
                name + ' is not a strict decimal step: ' + repr(value))
        value = int(value)
    require(type(value) is int and 0 <= value <= high,
            name + ' is outside the authority step budget: ' + repr(value))
    return value


def _frame_file(path_text, root):
    """Map a retained Windows-absolute frame path into this host; bound to the capture root.

    On WSL a C:\\... path converts to /mnt/c/...; the report's original path is
    kept for the record while the converted path must resolve inside the capture
    root being audited. On Windows the path is used as-is. Either way the file
    must exist and resolve (symlinks followed) within the boundary.
    """
    require(isinstance(path_text, str) and _WINDOWS_ABS.match(path_text),
            'Frame image path is not an absolute Windows path: ' + str(path_text))
    if os.name == 'nt':
        candidate = Path(path_text)
    else:
        match = _WINDOWS_ABS.match(path_text)
        candidate = Path('/mnt')/match.group(1).lower()/match.group(2).replace('\\', '/')
    require(candidate.is_file(), 'Frame image is not retained: ' + path_text)
    resolved = candidate.resolve()
    require(resolved.is_relative_to(Path(root).resolve()),
            'Frame image escapes the capture-root boundary: ' + path_text)
    return resolved


def _verify_frames(root, frames, observations, binding, camera, epoch):
    """Pairwise frame/observation identity plus a byte rehash of every retained PNG.

    Real contract (validated against 40-aruco-flight-scene-03 retained frames):
    Consumer metadata and targets carry step/frame_id as DECIMAL STRINGS and
    valid_until_step as an int; sensor_id is a string ('front_rgb'); vehicle_id
    is an int in the binding camera and its decimal string in metadata/target.
    The frame entry's target must equal the published observation target
    field-by-field; both are checked here, not separately.
    """
    require(len(frames) == len(observations), 'Report frames/observations diverge')
    verified = []
    for index, (entry, row) in enumerate(zip(frames, observations), 1):
        require(row.get('schema') == OBSERVATION_SCHEMA and row.get('sequence') == index
                and all(row.get(k) == binding[k]
                        for k in ('run_id', 'epoch', 'instance_id', 'generation', 'stream_id')),
                'Published observation identity differs from the binding')
        capture_step = _stepish(row.get('capture_step'), 'observation.capture_step')
        frame_id = _stepish(row.get('frame_id'), 'observation.frame_id', 2**63 - 1)
        require(_hex64(row.get('image_sha256')), 'Observation image identity invalid')
        frame = entry.get('frame') or {}
        notice, metadata = frame.get('notification') or {}, frame.get('metadata') or {}
        require(notice.get('schema') == RGB_NOTICE_SCHEMA
                and all(notice.get(k) == binding[k]
                        for k in ('run_id', 'epoch', 'instance_id', 'generation', 'stream_id'))
                and notice.get('metadata') == _basename(frame.get('metadata_path')),
                'RGB notification identity differs from the binding')
        require(metadata.get('schema') == RGB_METADATA_SCHEMA
                and all(metadata.get(k) == binding[k]
                        for k in ('run_id', 'epoch', 'instance_id', 'stream_id'))
                and _stepish(metadata.get('step'), 'metadata.step') == capture_step
                and _stepish(metadata.get('frame_id'), 'metadata.frame_id', 2**63 - 1) == frame_id
                and metadata.get('vehicle_id') == str(camera['vehicle_id'])
                and metadata.get('sensor_id') == camera['sensor_id']
                and metadata.get('image') == _basename(frame.get('image_path')),
                'RGB metadata identity/step differs from the observation')
        authority = entry.get('authority') or {}
        require(entry.get('image_sha256') == row['image_sha256']
                and authority.get('epoch') == epoch
                and type(entry.get('now_step')) is int
                and entry.get('now_step') == authority.get('tick'),
                'Frame entry image/authority identity differs')
        require(entry.get('target') == row.get('target'),
                'Frame entry target differs from the published observation target')
        resolved = _frame_file(frame.get('image_path'), root)
        require(hashlib.sha256(resolved.read_bytes()).hexdigest() == row['image_sha256'],
                'Frame PNG rehash differs from the recorded image_sha256')
        verified.append(dict(sequence=index, image_sha256=row['image_sha256'],
                             report_path=str(frame.get('image_path')),
                             resolved=str(resolved)))
        target = row.get('target')
        if target is not None:
            require(isinstance(target, dict) and target.get('schema') == TARGET_SCHEMA
                    and all(target.get(k) == binding[k]
                            for k in ('run_id', 'epoch', 'instance_id', 'generation', 'stream_id'))
                    and target.get('vehicle_id') == str(camera['vehicle_id'])
                    and isinstance(target.get('sensor_id'), str)
                    and target.get('sensor_id') == camera['sensor_id'],
                    'Observation target identity differs')
            target_step = _stepish(target.get('step'), 'target.step')
            require(target_step == capture_step
                    and _stepish(target.get('frame_id'), 'target.frame_id', 2**63 - 1) == frame_id,
                    'Observation target step/frame differs from its capture')
            require(_stepish(target.get('valid_until_step'), 'target.valid_until_step') >= target_step,
                    'Target validity ends before its capture step')
    return verified


def _target_verdict(target, at_step, *, first_step, last_accepted_step):
    """Why one consumed target cannot produce a MOVE, or None when it is fresh+valid.

    Mirrors the provable TargetIntent/seam rejection shapes only: null, from the
    authority future, expired at consumption, captured before the binding, or a
    duplicate/regressing step. Anything else must have produced a MOVE.
    """
    if target is None:
        return 'null'
    target_step = _stepish(target.get('step'), 'target.step')
    valid_until = _stepish(target.get('valid_until_step'), 'target.valid_until_step')
    if target_step > at_step:
        return 'future'
    if at_step > valid_until:
        return 'expired'
    if target_step < first_step:
        return 'before_binding'
    if last_accepted_step is not None and target_step <= last_accepted_step:
        return 'duplicate'
    return None


def loss_hold_chain(root, case_report, *, run_id, epoch, reports, chains):
    """Temporal loss-HOLD gate over the retained frames, links and adapter actions.

    Only the consumed latest sequences are required; Windows-side frame merging is
    allowed, so not every published observation must appear in observation_links.
    Justification comes from a time state machine over actual consumption and
    action.authority_step/authority_now_step against target.valid_until_step and
    the binding/profile episode boundary — never from seam_reason text. A link-less
    HOLD is legal exactly as the real task produces it: the initial HOLD (binding
    loaded, no observation and no consumed valid target yet), the cached-MOVE
    expiry HOLD (authority_now past the persisted intent's valid_until_step), and
    the final HOLD (authority step at/past binding.first_step + profile scene
    steps, after which no MOVE may follow). A consumed non-null but already
    expired target justifies HOLD exactly like a null. The gate closes only after
    at least one full cycle is proven: null/expired invalidation while a MOVE was
    active -> real HOLD send withdrawing it per TTL -> recovery MOVE on a fresh
    valid target; otherwise it reports not_exercised and stays on the uncovered
    list. An accepted public ACK is never treated as action completion.
    """
    frames = case_report['frames']
    observations = case_report['observations']
    binding = case_report.get('binding')
    session = case_report.get('session') or {}
    selected = next(s for s in STACK_UAV
                    if (reports[s]['task'].get('aruco') or {}).get('selected'))
    aruco = reports[selected]['task']['aruco']
    peer = next(s for s in STACK_UAV if s != selected)
    peer_aruco = reports[peer]['task']['aruco']
    task_binding = aruco.get('binding') or {}
    actions = aruco.get('adapter_actions') or []
    links = aruco.get('observation_links') or []
    sent = [a for a in actions if a.get('command_id') is not None]
    if not observations and not frames and not sent:
        return dict(gate='not_exercised',
                    reason='no published observations/frames and no adapter sends; '
                           'the loss-HOLD gate was not exercised by this run')
    require(isinstance(binding, dict) and binding.get('schema') == BINDING_SCHEMA
            and binding.get('run_id') == run_id and binding.get('epoch') == epoch
            and binding.get('instance_id') == session.get('instance_id')
            and binding.get('stream_id') == case_report.get('stream_id'),
            'Report binding identity differs from the run/session')
    profile = case_report.get('profile')
    require(isinstance(profile, dict), 'Capture report lacks the frozen profile content')
    profile_path = root / 'sources' / Path(PROFILE_REL)
    require(profile_path.is_file(), 'Frozen profile file is not retained in the capture')
    raw_profile = profile_path.read_bytes()
    require(_hex64(case_report.get('profile_sha256'))
            and hashlib.sha256(raw_profile).hexdigest() == case_report['profile_sha256']
            and json.loads(raw_profile.decode('utf-8')) == profile
            and (case_report.get('source_sha256') or {}).get(PROFILE_REL)
            == case_report['profile_sha256'],
            'Frozen profile identity differs across report/sources')
    scene = profile.get('scene')
    require(isinstance(scene, dict), 'Frozen profile lacks the scene step plan')
    episode_steps = sum(_stepish(scene.get(k), 'profile.scene.' + k) for k in SCENE_STEP_KEYS)
    camera = binding.get('camera') or {}
    require(type(camera.get('vehicle_id')) is int
            and camera.get('vehicle_id') == STACK_UAV[selected]
            and isinstance(camera.get('sensor_id'), str)
            and _SENSOR_ID.fullmatch(camera['sensor_id']) is not None
            and camera['sensor_id'] == (profile.get('camera') or {}).get('sensor_id'),
            'Binding camera identity differs from the selected stack/profile')
    first_step = _stepish(binding.get('first_step'), 'binding.first_step')
    require(aruco.get('profile_sha256') == case_report['profile_sha256']
            and peer_aruco.get('profile_sha256') == case_report['profile_sha256']
            and binding.get('profile_sha256') == case_report['profile_sha256'],
            'Profile identity differs across report/binding/tasks')
    require(task_binding.get('first_step') == first_step
            and task_binding.get('stream_id') == binding['stream_id']
            and type(task_binding.get('episode_end_step')) is int
            and task_binding['episode_end_step'] == first_step + episode_steps
            and task_binding['episode_end_step'] <= MAX_AUTHORITY_STEP,
            'Task binding differs from the report binding/profile boundary')
    episode_end = task_binding['episode_end_step']
    verified_frames = _verify_frames(root, frames, observations, binding, camera, epoch)
    capture_steps = [_stepish(r.get('capture_step'), 'observation.capture_step')
                     for r in observations]
    frame_ids = [_stepish(r.get('frame_id'), 'observation.frame_id', 2**63 - 1)
                 for r in observations]
    # Consumption: only the consumed latest sequences are audited; merging is allowed.
    previous_sequence, previous_frame = 0, -1
    for link in links:
        sequence = link.get('sequence')
        require(type(sequence) is int and 1 <= sequence <= len(observations)
                and sequence > previous_sequence, 'Consumed observation sequence regressed')
        previous_sequence = sequence
        link_step = _stepish(link.get('authority_step'), 'link.authority_step')
        link_frame = _stepish(link.get('frame_id'), 'link.frame_id', 2**63 - 1)
        require(_stepish(link.get('capture_step'), 'link.capture_step') == capture_steps[sequence - 1]
                and link_frame == frame_ids[sequence - 1]
                and link.get('image_sha256') == observations[sequence - 1]['image_sha256'],
                'Consumed observation link differs from the published record')
        require(link_step >= capture_steps[sequence - 1],
                'Consumed observation is from the authority future')
        require(link_frame > previous_frame, 'Old frame re-fed to the seam')
        previous_frame = link_frame
    link_by_command = {l.get('command_id'): l for l in links if l.get('command_id') is not None}
    idle_links = {}
    for link in links:
        if link.get('command_id') is None:
            require(link.get('action') in ('suppressed_hold', 'duplicate_record'),
                    'Consumed link without command identity must be a suppression')
            idle_links.setdefault((link['action'], _stepish(link.get('authority_step'),
                                                            'link.authority_step')), []).append(link)
    # Temporal state machine with the adapter's own invariants: authority_now_step
    # and record steps never regress, a record step is never in the future, and a
    # duplicate/suppressed record inherits nothing from an expired MOVE.
    moves = holds = cycles = 0
    last_now = last_step = -1
    last_accepted_step = None
    active = None           # dict(step, target_step, valid_until) of the persisted MOVE record
    hover_confirmed = False
    last_hover_now = None
    loss_open = False       # Invalidation withdrew the active MOVE; recovery pending.
    for position, action in enumerate(actions):
        act = action.get('action')
        now = _stepish(action.get('authority_now_step'), 'action.authority_now_step')
        step = _stepish(action.get('authority_step'), 'action.authority_step')
        require(step <= now, 'Adapter action record step is in the authority future')
        require(now >= last_now and step >= last_step, 'Adapter action steps regressed')
        last_now, last_step = now, step
        if now >= episode_end:
            require(act == 'hover' and action.get('command_id') is not None
                    and position == len(actions) - 1
                    and link_by_command.get(action['command_id']) is None,
                    'Actions at/past the episode end must be the single final HOLD')
        if act == 'move':
            moves += 1
            link = link_by_command.get(action['command_id'])
            require(link is not None and link.get('action') == 'move'
                    and _stepish(link.get('authority_step'), 'link.authority_step') == step,
                    'Adapter MOVE without its consumed observation link')
            target = observations[link['sequence'] - 1].get('target')
            require(isinstance(target, dict), 'MOVE consumed a null observation')
            target_step = _stepish(target.get('step'), 'target.step')
            valid_until = _stepish(target.get('valid_until_step'), 'target.valid_until_step')
            require(target_step <= step <= valid_until and now <= valid_until,
                    'MOVE published after the intent validity expired')
            require(last_accepted_step is None or target_step > last_accepted_step,
                    'MOVE target step did not advance past the last accepted target')
            if loss_open:
                cycles += 1  # Recovery after a proven TTL withdrawal.
                loss_open = False
            last_accepted_step = target_step
            active = dict(step=step, target_step=target_step, valid_until=valid_until)
            hover_confirmed = False
        elif act == 'hover':
            holds += 1
            require(not action.get('send_failed'),
                    'HOLD send failure leaves the persisted MOVE withdrawal unproven')
            link = link_by_command.get(action['command_id'])
            if link is not None:
                require(link.get('action') == 'hover'
                        and _stepish(link.get('authority_step'), 'link.authority_step') == step,
                        'HOLD link/action step differs')
                verdict = _target_verdict(observations[link['sequence'] - 1].get('target'),
                                          step, first_step=first_step,
                                          last_accepted_step=last_accepted_step)
                require(verdict is not None, 'HOLD consumed a fresh valid target')
                if active is not None:
                    loss_open = True  # Consumed null/expired record withdrew the MOVE.
                active = None
            elif step >= episode_end:
                active = None  # Final HOLD at the binding.first_step + scene-steps boundary.
            elif active is not None:
                require(active['valid_until'] < now,
                        'Link-less HOLD without invalidation, expiry or boundary justification')
                loss_open = True  # Cached MOVE expired per TTL before any new consumption.
                active = None
            else:
                require(last_accepted_step is None and not hover_confirmed
                        and not any(a.get('action') == 'move' for a in actions[:position]),
                        'Link-less HOLD without invalidation, expiry or boundary justification')
            hover_confirmed = True
            last_hover_now = now
        elif act == 'suppressed_hold':
            require(hover_confirmed, 'suppressed_hold without a prior confirmed hover')
            require(active is None, 'suppressed_hold while a MOVE is still active')
            group = idle_links.get(('suppressed_hold', step))
            link = group.pop(0) if group else None
            if link is not None:
                verdict = _target_verdict(observations[link['sequence'] - 1].get('target'),
                                          step, first_step=first_step,
                                          last_accepted_step=last_accepted_step)
                require(verdict is not None, 'suppressed_hold absorbed a fresh valid target')
            require(not any(_stepish(l.get('authority_step'), 'link.authority_step') > last_hover_now
                            and _stepish(l.get('authority_step'), 'link.authority_step') <= now
                            and _target_verdict(observations[l['sequence'] - 1].get('target'),
                                                _stepish(l.get('authority_step'),
                                                         'link.authority_step'),
                                                first_step=first_step,
                                                last_accepted_step=last_accepted_step) is None
                            for l in links),
                    'suppressed_hold after a fresh target was consumed in the hold window')
        elif act == 'duplicate_record':
            require(position > 0 and active is not None and active['step'] == step
                    and actions[position - 1].get('action') in ('move', 'duplicate_record')
                    and _stepish(actions[position - 1].get('authority_step'),
                                 'action.authority_step') == step,
                    'duplicate_record without its still-active MOVE record')
            require(now <= active['valid_until'], 'duplicate_record kept an expired MOVE active')
            group = idle_links.get(('duplicate_record', step))
            link = group.pop(0) if group else None
            if link is not None:  # A fresh target consumed at the same step; no re-send.
                target = observations[link['sequence'] - 1].get('target')
                require(isinstance(target, dict)
                        and _target_verdict(target, step, first_step=first_step,
                                            last_accepted_step=last_accepted_step) is None,
                        'duplicate_record absorbed an invalid target')
                last_accepted_step = _stepish(target.get('step'), 'target.step')
                active.update(target_step=last_accepted_step,
                              valid_until=_stepish(target.get('valid_until_step'),
                                                   'target.valid_until_step'))
        else:
            require(False, 'Unknown adapter action ' + str(act))
    require(all(not group for group in idle_links.values()),
            'Consumed link lacks its suppressing adapter action')
    require(active is None, 'Active MOVE persisted past the episode end without the final HOLD')
    base = dict(observations=len(observations), consumed=len(links), moves=moves, holds=holds,
                frames_verified=len(verified_frames))
    if not cycles:
        return dict(base, gate='not_exercised',
                    reason='no complete null/expired invalidation -> TTL withdrawal -> '
                           'recovery cycle observed; loss-HOLD causality stays uncovered')
    return dict(base, gate='closed', cycles=cycles, frames=verified_frames,
                note='public send+acceptance only; ACK is not action completion')


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
    reports, chains = {}, {}
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
        reports[stack], chains[stack] = report, chain
        stacks[stack] = dict(samples=capture['end']['total_samples'],
                             counts=capture['counts'], session_states=chain['session_states'],
                             selected=selected, provenance=pins, adapter=adapter)
    require(selected_count == 1, 'Exactly one stack must own the bound camera')
    uncovered = list(UNCOVERED)
    loss_hold = None
    if case_report is not None:
        require(isinstance(case_report.get('frames'), list)
                and isinstance(case_report.get('observations'), list),
                'Capture report lacks frames/observations lists')
        loss_hold = loss_hold_chain(root, case_report, run_id=run_id, epoch=epoch,
                                    reports=reports, chains=chains)
        if loss_hold['gate'] == 'closed':
            uncovered = [u for u in uncovered if not u.startswith('loss_hold_correlation')]
    limitations = ['Raw public chain and shared product timeline only; native setpoint '
                   'closure, native ACK/action completion and publisher exclusivity are '
                   'not certified.']
    if loss_hold is None or loss_hold.get('gate') != 'closed':
        limitations.append('Loss-HOLD causality is not certified by this capture '
                           + ('(gate not exercised).' if loss_hold is not None
                              else '(no capture report layer).'))
    return dict(status='pending', entry=entry or {'run_root': str(run_root)},
                run_id=run_id, epoch=epoch, stacks=stacks, loss_hold=loss_hold,
                strict_native_barriers=strict, lifecycle=life, timeline=timeline,
                uncovered=uncovered,
                limitations=limitations,
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
