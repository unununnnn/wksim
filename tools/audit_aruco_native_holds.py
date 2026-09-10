"""Offline post-MOVE HOLD targets; requires the separate public/provenance audit.

Control tick resolves CURRENT_POS_HOVER from that tick's state, caches it,
publishes native output if due, then SessionState. Native samples therefore
belong to the immediately following continuous SessionState, not the preceding
one. The first state carrying a HOLD supplies its frozen position and heading.
Only HOLDs following an executed MOVE are covered; initial takeover is separate.
No ROS nodes, physical tolerance, or flight-completion verdict is introduced.
"""
import argparse
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_aruco_tracking_raw import verify_raw_capture, reconcile_identity


def require(condition, message):
    if not condition:
        raise ValueError(message)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def yaw(q):
    norm = math.hypot(q.w, q.x, q.y, q.z)
    require(math.isfinite(norm) and norm >= 1e-9, 'Invalid reference quaternion')
    w, x, y, z = (v / norm for v in (q.w, q.x, q.y, q.z))
    return math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))


def wrap(value):
    return math.atan2(math.sin(value), math.cos(value))


def expected_ap(position, heading, home):
    east, north, up = position
    latitude, longitude = home
    lat = latitude + int(north / 0.011131884502145034)
    lon = longitude + int(east / (0.011131884502145034 * math.cos(math.radians((lat+latitude)/2e7))))
    lon = (lon+1800000000) % 3600000000 - 1800000000
    return lat/1e7, lon/1e7, f32(up), f32(wrap(f32(heading)))


def state_for_sample(stamps, states, timestamp):
    index = bisect_right(stamps, timestamp)
    require(0 < index < len(states), 'Native sample lacks two bounding SessionStates')
    require(stamps[index-1] < timestamp < stamps[index], 'Ambiguous native/state timestamp')
    return states[index]


def audit(root):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from prometheus_msgs.msg import UAVCommand as Cmd, UAVControlState as Control
    root = Path(root)
    report = json.loads((root/'report.json').read_text())
    require(report['status'] == 'captured_pending_independent_audit', 'Run did not complete capture')
    epoch = report['result']['epochs'][0]['epoch']
    directory = root/'run/epochs'/epoch
    selected = report['config']['aruco_experiment']['selected_stack']
    paths = list(directory.glob('tasks/*/'+selected+'/aruco-raw-dds.jsonl'))
    require(len(paths) == 1, 'Expected one selected-stack raw capture')
    raw = verify_raw_capture(paths[0], run_id=report['session']['run_id'], epoch=epoch,
                             stack=selected, uav_id=1 if selected == 'arducopter' else 2)
    provenance = reconcile_identity(raw, directory, json.loads((directory/'preflight.json').read_text()))
    classes = {}
    decoded = []
    for row in raw['samples']:
        classes.setdefault(row['type'], get_message(row['type']))
        decoded.append((row, deserialize_message(bytes.fromhex(row['cdr_hex']), classes[row['type']])))
    states = [(r,m) for r,m in decoded if r['topic'].endswith('/v2/state')]
    commands = [(r,m) for r,m in decoded if r['topic'].endswith('/v2/command')]
    require(states and commands, 'Missing raw states or commands')
    stamps = [r['source_timestamp'] for r,m in states]
    ce = states[0][1].control_epoch
    for i,(r,m) in enumerate(states):
        require(m.run_id == report['session']['run_id'] and m.control_epoch == ce, 'Session identity differs')
        require(i == 0 or (m.sequence == states[i-1][1].sequence+1 and stamps[i] > stamps[i-1]),
                'Session sequence/time gap')
    refs = {}
    for r,m in states:
        refs.setdefault(m.last_request_id, (r,m))
    lookup = {}
    holds = {}
    previous = None
    unresolved = []
    for r,m in commands:
        require(m.run_id == report['session']['run_id'] and m.control_epoch == ce, 'Command identity differs')
        require(m.request_id not in lookup, 'Duplicate command request')
        lookup[m.request_id] = m
        if m.request_id not in refs:
            unresolved.append(dict(request_id=m.request_id,agent_cmd=m.command.agent_cmd,reason='No SessionState carried accepted command'))
            previous = m.command.agent_cmd
            continue
        sr,state = refs[m.request_id]
        require(sr['source_timestamp'] > r['source_timestamp'], 'Reference predates command')
        if m.command.agent_cmd == Cmd.CURRENT_POS_HOVER and previous == Cmd.MOVE:
            require(state.control.control_state == Control.COMMAND_CONTROL and not state.control.failsafe,
                    'HOLD state is not active command control')
            holds[m.request_id] = dict(position=[float(x) for x in state.state.position],
                                      yaw=yaw(state.state.attitude_q), sequence=state.sequence, samples=0)
        previous = m.command.agent_cmd
    require(holds, 'No post-MOVE HOLD exercised')
    # Hold reference persists through repeated HOVER commands; the frozen task
    # normally suppresses them. Do not silently use a new reference if present.
    ordered = [m.request_id for r,m in commands]
    hold_owner = {}
    owner = None
    for rid in ordered:
        if rid in holds: owner = rid
        elif lookup[rid].command.agent_cmd != Cmd.CURRENT_POS_HOVER: owner = None
        if owner is not None: hold_owner[rid] = owner
    native = [(r,m) for r,m in decoded if (r['topic'].endswith('/trajectory_setpoint')
              or r['topic'] in ('/ap/cmd_gps_pose','/ap/cmd_vel'))]
    local = [m for r,m in decoded if r['topic'] == '/ap/wksim/local_state_v1']
    homes = {(m.home_latitude_e7,m.home_longitude_e7) for m in local if m.home_valid}
    if selected == 'arducopter':
        require(len(homes) == 1, 'AP home is missing or changed')
    failures = []
    gids = set()
    for r,m in native:
        timestamp = r['source_timestamp']
        if timestamp <= stamps[0] or timestamp >= stamps[-1]: continue
        sr,state = state_for_sample(stamps,states,timestamp)
        owner = hold_owner.get(state.last_request_id)
        if owner is None: continue
        ref = holds[owner]
        ref['samples'] += 1
        gids.add(r['publisher_gid'])
        p = ref['position']
        if selected == 'px4':
            expected = (f32(p[1]),f32(p[0]),f32(-p[2]))
            good = (tuple(m.position) == expected and math.isnan(m.yawspeed)
                    and all(math.isnan(v) for v in (*m.velocity,*m.acceleration,*m.jerk))
                    and m.yaw == f32(wrap(math.pi/2-f32(ref['yaw']))))
        else:
            expected = expected_ap(p,ref['yaw'],next(iter(homes)))
            good = (r['topic'] == '/ap/cmd_gps_pose' and m.header.frame_id == 'map'
                    and m.coordinate_frame == m.FRAME_GLOBAL_REL_ALT and m.type_mask == 0x9F8
                    and (m.latitude,m.longitude,m.altitude,m.yaw) == expected
                    and m.header.stamp == state.state.header.stamp)
        if not good:
            failures.append(dict(request_id=owner,source_timestamp=timestamp,topic=r['topic']))
    unresolved.extend(dict(request_id=rid,reason='Post-MOVE HOLD has no native sample') for rid,v in holds.items() if not v['samples'])
    require(len(gids) == 1, 'HOLD targets have missing/multiple observed publisher GIDs')
    return dict(status='failed' if failures else 'pending' if unresolved else 'pass', unresolved=unresolved, scope=__doc__, epoch=epoch,stack=selected,
                holds=holds,failures=failures,observed_gid=next(iter(gids)),provenance=provenance,
                raw_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                uncovered=['Initial takeover HOLD', 'Public request acceptance and loss causality require raw audit',
                           'Graph-wide native publisher identity/exclusivity requires separate proof'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try: result=audit(args.root)
    except Exception as error: result=dict(status='failed',error=str(error))
    with args.output.open('x') as f: json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('holds','scope','failures')}))
    raise SystemExit(result['status'] != 'pass')
