"""Offline native payload/header timestamp cross-check; ArUco MOVE/HOLD intervals only.

Fills the gap left by the field-exact auditors: whether the native setpoint's own
timestamp traces to REAL feedback the bridge held, per the installed sources. The
control node is SINGLE-THREADED (node.py main spin_once): each tick reads the native
state, drive() publishes the native setpoint, then publishes SessionState
(node.py:671-703). A DDS producer sample can be published yet stay unconsumed in the
node's queue, so "latest by arrival" is NOT a valid reference — state and setpoint in
one tick are built from the SAME consumed feedback sample, and that sample is found by
content, not by recency.

- PX4 (native_px4.py): send() stamps TrajectorySetpoint.timestamp = self.timestamp()
  (:159-165, :233-241) = latest consumed VehicleLocalPosition .timestamp (NOT
  timestamp_sample); the same-tick following SessionState header is stamped from
  pos.timestamp_sample or pos.timestamp (:205, frames.py:50-52) and its position/
  velocity are the ned_axes ENU swap of that same sample (:202-203). The two clocks
  need NOT be equal and are never equated here: the reference sample is the unique
  earlier raw VehicleLocalPosition whose (timestamp_sample or timestamp), ENU position
  AND velocity match the following state; the payload timestamp must equal THAT
  sample's .timestamp. Distinct matching timestamps or a missing reference are
  unresolved (no guessing); a payload that matches no such sample is a mismatch.
- AP (native_arducopter.py): cmd_gps_pose/cmd_vel headers are stamped from
  latest['local'].time_boot_us (:269/:285/:300/:320) and the same-tick following
  SessionState header likewise (:186-188) — one consumed WksimState — so they must be
  EXACTLY equal. A WksimState produced-but-unconsumed before the state cannot have run
  its callback mid-tick, so a difference is a real mismatch, never excused.

Attribution reuses the proven raw verifier (verify_raw_capture/reconcile_identity) and
the strict following-SessionState window lookup (state_for_sample); session
control_epoch/run_id and sequence continuity are enforced. A window is in scope only
when the owning state's last_request_id resolves to a public MOVE/XYZ_VEL_BODY or a
post-MOVE CURRENT_POS_HOVER; LAND, setup, initial-takeover and out-of-bounds samples
are counted under 'skipped', not judged. Native CDR is deserialized with the real
installed ROS messages only. No ROS nodes are created; production native send paths
are never called.

Usage: python3 -B tools/audit_aruco_native_timestamps.py <capture_root> --output <new.json>
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_aruco_tracking_raw import verify_raw_capture, reconcile_identity
from tools.audit_aruco_native_holds import require, state_for_sample

FEEDBACK_TYPE = {'px4': 'px4_msgs/msg/VehicleLocalPosition',
                 'arducopter': 'ardupilot_msgs/msg/WksimState'}
NATIVE_TYPE = {'px4': ('px4_msgs/msg/TrajectorySetpoint',),
               'arducopter': ('geometry_msgs/msg/TwistStamped', 'ardupilot_msgs/msg/GlobalPosition')}
AP_TOPIC = {'move': '/ap/cmd_vel', 'hold': '/ap/cmd_gps_pose'}
SCHEMA = 'wksim.aruco-native-timestamps.v1'
UNCOVERED = ['LAND/setup/initial-takeover intervals are counted under skipped, not judged',
             'Field-exact MOVE velocity / HOLD position content: audit_aruco_native_moves.py / audit_aruco_native_holds.py',
             'PX4 payload and state-header clocks are resolved against one reference sample, never equated',
             'Graph-wide native publisher identity/exclusivity requires separate proof',
             'Public request acceptance, loss causality and wrap-up rate remain the raw auditor scope']


def header_us(stamp):
    """Inverse of frames.stamp_us; None when the header is not its microsecond product."""
    if stamp.nanosec % 1000:
        return None
    return stamp.sec * 1_000_000 + stamp.nanosec // 1000


def lp_header(message):
    """native_px4.state() header source (:205): timestamp_sample falling back to timestamp."""
    return getattr(message, 'timestamp_sample', 0) or message.timestamp


def px4_reference_timestamps(feedback, stamp, state_us, position, velocity):
    """Distinct .timestamp of every raw VehicleLocalPosition produced before the native
    sample (source_timestamp < stamp) that the following SessionState was built from:
    header value (:205) plus the ENU position/velocity ned_axes swap of that NED sample
    (:202-203). Produced-but-unconsumed newer samples never match the state's
    position/velocity, so no 'latest by arrival' matcher is used; more than one distinct
    match makes the reference ambiguous."""
    return {m.timestamp for r, m in feedback
            if r['source_timestamp'] < stamp
            and lp_header(m) == state_us
            and (m.y, m.x, -m.z) == position
            and (m.vy, m.vx, -m.vz) == velocity}


def check_px4(window, row, message, state_row, state, feedback, failures, unresolved):
    stamp = row['source_timestamp']
    detail = dict(topic=row['topic'], source_timestamp=stamp, window=window,
                  request_id=int(state.last_request_id))
    if window == 'move':  # XYZ_VEL_BODY + yaw rate: velocity set, yaw NaN, yawspeed set.
        shape = (any(not math.isnan(v) for v in message.velocity)
                 and math.isnan(message.yaw) and not math.isnan(message.yawspeed)
                 and all(math.isnan(v) for v in (*message.position, *message.acceleration, *message.jerk)))
    else:  # CURRENT_POS_HOVER: position + yaw angle set, velocity/acceleration/jerk/yawspeed NaN.
        shape = (all(not math.isnan(v) for v in message.position)
                 and not math.isnan(message.yaw) and math.isnan(message.yawspeed)
                 and all(math.isnan(v) for v in (*message.velocity, *message.acceleration, *message.jerk)))
    if not shape:
        failures.append(dict(code='window_shape_differs', **detail))
        return False
    if not 0 < message.timestamp < 10**12:  # native_px4.timestamp() range guard :163-164
        failures.append(dict(code='payload_timestamp_out_of_range', value=int(message.timestamp), **detail))
        return False
    state_us = header_us(state.state.header.stamp)
    state_detail = dict(detail, state_sequence=int(state.sequence),
                        state_source_timestamp=state_row['source_timestamp'])
    if state_us is None:
        failures.append(dict(code='state_header_not_stamp_us_product', **state_detail))
        return False
    # float32[3] state axes normalize to plain floats; feedback scalars are already doubles.
    position = tuple(float(v) for v in state.state.position)
    velocity = tuple(float(v) for v in state.state.velocity)
    matches = px4_reference_timestamps(feedback, stamp, state_us, position, velocity)
    if not matches:
        unresolved.append(dict(what='reference', reason='no earlier raw VehicleLocalPosition matches'
                               ' the following state header/position/velocity', **state_detail))
        return False
    if len(matches) > 1:
        unresolved.append(dict(what='reference', reason='distinct matching feedback timestamps;'
                               ' ambiguous reference, no guessing',
                               timestamps=sorted(int(t) for t in matches), **state_detail))
        return False
    reference = matches.pop()
    if message.timestamp != reference:
        failures.append(dict(code='payload_timestamp_differs', expected=int(reference),
                             actual=int(message.timestamp), **state_detail))
        return False
    return True


def check_ap(window, row, message, state_row, state, failures, unresolved):
    detail = dict(topic=row['topic'], source_timestamp=row['source_timestamp'], window=window,
                  request_id=int(state.last_request_id),
                  state_sequence=int(state.sequence),
                  state_source_timestamp=state_row['source_timestamp'])
    expected = AP_TOPIC[window]
    if row['topic'] != expected:
        failures.append(dict(code='window_topic_differs', expected=expected, **detail))
        return False
    if message.header.frame_id != 'map':
        failures.append(dict(code='cmd_frame_differs', frame_id=message.header.frame_id, **detail))
        return False
    value = header_us(message.header.stamp)
    if (value is None or not 0 < value < 10**12
            or not 0 <= message.header.stamp.nanosec < 1_000_000_000):
        failures.append(dict(code='cmd_header_not_valid_boot_microseconds', **detail))
        return False
    # One single-threaded tick stamps both from the same consumed WksimState; exact equality.
    if message.header.stamp != state.state.header.stamp:
        failures.append(dict(code='cmd_header_differs_from_following_state',
                             cmd=dict(sec=int(message.header.stamp.sec),
                                      nanosec=int(message.header.stamp.nanosec)),
                             state=dict(sec=int(state.state.header.stamp.sec),
                                        nanosec=int(state.state.header.stamp.nanosec)), **detail))
        return False
    return True


def audit(root):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from prometheus_msgs.msg import UAVCommand as Cmd
    root = Path(root)
    report = json.loads((root / 'report.json').read_text())
    require(report.get('status') == 'captured_pending_independent_audit', 'Run did not complete capture')
    epochs = report['result']['epochs']
    require(len(epochs) == 1, 'Multi-epoch ArUco run needs a dedicated lifecycle audit')
    epoch = epochs[0]['epoch']
    directory = root / 'run' / 'epochs' / epoch
    selected = report['config']['aruco_experiment']['selected_stack']
    paths = list(directory.glob('tasks/*/' + selected + '/aruco-raw-dds.jsonl'))
    require(len(paths) == 1, 'Expected one selected-stack raw capture')
    raw = verify_raw_capture(paths[0], run_id=report['session']['run_id'], epoch=epoch,
                             stack=selected, uav_id=1 if selected == 'arducopter' else 2)
    provenance = reconcile_identity(raw, directory, json.loads((directory / 'preflight.json').read_text()))
    classes, decoded = {}, []
    for row in raw['samples']:
        classes.setdefault(row['type'], get_message(row['type']))
        decoded.append((row, deserialize_message(bytes.fromhex(row['cdr_hex']), classes[row['type']])))
    states = [(r, m) for r, m in decoded if r['topic'].endswith('/v2/state')]
    commands = [(r, m) for r, m in decoded if r['topic'].endswith('/v2/command')]
    require(states and commands, 'Missing raw states or commands')
    stamps = [r['source_timestamp'] for r, _ in states]
    control_epoch = states[0][1].control_epoch
    for i, (r, m) in enumerate(states):
        require(m.run_id == report['session']['run_id'] and m.control_epoch == control_epoch,
                'Session identity differs')
        require(i == 0 or (m.sequence == states[i - 1][1].sequence + 1 and stamps[i] > stamps[i - 1]),
                'Session sequence/time gap')
    move_rids, hold_rids, previous, seen_requests = set(), set(), None, set()
    for r, m in commands:
        require(m.run_id == report['session']['run_id'] and m.control_epoch == control_epoch,
                'Command identity differs')
        require(m.request_id not in seen_requests,'Duplicate public command request id')
        seen_requests.add(m.request_id)
        command = m.command
        if (command.agent_cmd == Cmd.MOVE and command.move_mode == Cmd.XYZ_VEL_BODY
                and command.yaw_rate_mode is True and command.yaw_rate_ref == 0):
            move_rids.add(m.request_id)  # Frozen scenario only; other MOVEs are skipped, not judged.
        elif command.agent_cmd == Cmd.CURRENT_POS_HOVER and previous == Cmd.MOVE:
            hold_rids.add(m.request_id)  # Post-MOVE HOLDs only; initial takeover is setup scope.
        previous = command.agent_cmd
    feedback = [(r, m) for r, m in decoded if r['type'] == FEEDBACK_TYPE[selected]]
    native = [(r, m) for r, m in decoded if r['type'] in NATIVE_TYPE[selected]]
    failures, unresolved, skipped = [], [], {}
    windows = {'move': dict(samples=0, verified=0), 'hold': dict(samples=0, verified=0)}
    gids = set()
    for row, message in native:
        stamp = row['source_timestamp']
        if stamp <= stamps[0] or stamp >= stamps[-1]:
            skipped['outside_state_bounds'] = skipped.get('outside_state_bounds', 0) + 1
            continue
        try:
            state_row, state = state_for_sample(stamps, states, stamp)
        except ValueError:
            skipped['ambiguous_state_bound'] = skipped.get('ambiguous_state_bound', 0) + 1
            unresolved.append(dict(reason='Ambiguous native/state timestamp bound',
                                   source_timestamp=stamp,topic=row['topic']))
            continue
        request_id = state.last_request_id
        if request_id in move_rids:
            window = 'move'
        elif request_id in hold_rids:
            window = 'hold'
        else:
            skipped['not_move_hold'] = skipped.get('not_move_hold', 0) + 1
            continue
        windows[window]['samples'] += 1
        gids.add(row['publisher_gid'])
        if selected == 'px4':
            good = check_px4(window, row, message, state_row, state, feedback, failures, unresolved)
        else:
            good = check_ap(window, row, message, state_row, state, failures, unresolved)
        if good:
            windows[window]['verified'] += 1
    if not any(w['samples'] for w in windows.values()):
        unresolved.append(dict(reason='no native setpoint samples in MOVE/HOLD windows'))
    verified = sum(w['verified'] for w in windows.values())
    status = 'failed' if failures else 'pass' if verified and not unresolved else 'unresolved'
    return dict(schema=SCHEMA, status=status, stack=selected, epoch=epoch,
                windows=windows, verified=verified, skipped=skipped,
                failures=failures, unresolved=unresolved, native_gids=sorted(gids),
                provenance=provenance,
                raw_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='Native setpoint payload/header timestamps versus real feedback; MOVE/HOLD windows only',
                uncovered=list(UNCOVERED))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.root)
    except Exception as error:
        result = dict(schema=SCHEMA, status='failed', error=str(error))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: result.get(k) for k in ('status', 'verified', 'skipped')}))
    raise SystemExit(result['status'] == 'failed')
