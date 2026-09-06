"""Audit a real airborne pause observation, never report it as G2 acceptance."""
import argparse
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from audit_joint_flight import digest, lines, require
from joint_control_candidate import check as check_control
from probe_joint_clock import group_members, json_identity


def audit(root, verify_current_sources=False):
    from rclpy.serialization import deserialize_message
    from rosgraph_msgs.msg import Clock
    from wksim_msgs.msg import SessionState
    from prometheus_msgs.msg import TextInfo
    from px4_msgs.msg import VehicleStatus, VehicleLocalPosition, OffboardControlMode, TrajectorySetpoint
    from ardupilot_msgs.msg import WksimState, GlobalPosition
    from prometheus_control.frames import topic
    result = json.loads((root/'result.json').read_text())
    require(result['status'] == 'observed' and result['pause_probe_requested']
            and not result['flight_completed'], 'Not a completed pause observation')
    require(result['source_unchanged'] and not result['cleanup_errors'], 'Source or cleanup failed')
    for name, checksum in result['source_sha256'].items():
        require(digest(root/('source__'+name.replace('/', '__')+'.txt')) == checksum, 'Source snapshot differs')
        if verify_current_sources:
            require(digest(REPO/name) == checksum, 'Current executed source changed: '+name)
    for stack in ('arducopter', 'px4'):
        require(json.loads((root/(stack+'-preflight.json')).read_text())['ok'], 'Baseline admission failed')
    require(digest(root/'ap-build.json') == result['manifest_sha256']['ap'], 'AP build manifest differs')
    control = result['control_candidate']
    require(digest(root/'control-build.json') == result['manifest_sha256']['control'], 'Control manifest differs')
    require(check_control(Path(control['root'])/'build.json', result['manifest_sha256']['control']) == control,
            'Actual control source/install changed')
    ap = json.loads((root/'ap-build.json').read_text())
    require(digest(ap['candidate_root']+'/build/sitl/bin/arducopter') ==
            ap['artifacts']['build/sitl/bin/arducopter']['sha256'], 'Actual AP changed')
    require(result['unowned_ap_before'] == result['unowned_ap_after'] == json_identity(828), 'Unowned AP changed')
    require(len(result['children']) == 10, 'Wrong process inventory')
    for name, child in result['children'].items():
        require(not child['remaining_group_members'] and not group_members(child['identity']['pgid']),
                'Owned process group remains: '+name)
        if name.endswith(('-model', '-control', '-fc')):
            require(child['returncode'] == 0, 'Process did not exit normally: '+name)

    pause = result['pause_observation']; before, after = pause['before'], pause['after']
    start, finish = pause['started_wall'], pause['finished_wall']
    total, epoch = before['authority']['tick'], result['scene_epoch']
    require(pause['window_seconds'] == 4.0 and finish-start >= 4.0, 'Observation window changed')
    require(total > 0 and total % 4 == 0 and before['authority'] == after['authority']
            and before['authority']['phase'] == 'paused' and before['authority']['synchronized']
            and before['authority']['last_barrier_tick'] == total, 'Not a synchronized frozen boundary')
    require(result['final_authority']['tick'] == total and result['final_authority']['phase'] == 'stopped',
            'Stop added a physics step or did not retire authority')
    repetitions = after.get('paused_clock_republications', 0)-before.get('paused_clock_republications', 0)
    require(before['models'] == after['models'] and after['ros_observed_ns'] == total*1000000
            and before['clock_publications'] == total+1
            and after['clock_publications'] == total+1+repetitions,
            'Model snapshot or shared clock advanced')
    publication_log = root/'pause-clock-publications.jsonl'
    actual_repeats = 0
    for actual_repeats, row in enumerate(lines(publication_log) if publication_log.exists() else [], 1):
        require(pause.get('repeat_paused_clock') and row['epoch'] == epoch and row['tick'] == total
                and row['time_ns'] == total*1000000 and start <= row['wall'] <= finish
                and row['publication'] == total+1+actual_repeats, 'Paused time retransmission differs')
    require(actual_repeats == repetitions, 'Unaccounted clock retransmission')
    heights = {}
    for stack in ('arducopter', 'px4'):
        last = None; count = 0
        for count, row in enumerate(lines(root/(stack+'-truth.jsonl')), 1):
            state = row['state']
            require(row['epoch'] == epoch and row['tick'] == count and len(state) == 120
                    and all(math.isfinite(value) for value in state) and abs(state[2]-count/1000) < 1e-8
                    and round(state[60]) == count*1000, 'Model tick/time/finite-state evidence differs')
            require(json.loads(row['input']) == row['request'] ==
                    dict(version=1, epoch=epoch, tick=count, commands=row['commands']), 'Model input differs')
            last = state
        require(count == total and last == after['models'][stack]['state']
                and after['models'][stack]['tick'] == total and after['models'][stack]['epoch'] == epoch,
                'Model snapshot does not match actual final trace')
        heights[stack] = -last[8]
        require(heights[stack] >= 2.5, 'Pause did not occur in actual flight')
    count = 0
    for tick, row in enumerate(lines(root/'clock.jsonl')):
        require(row['epoch'] == epoch and row['tick'] == tick and row['time_ns'] == tick*1000000,
                'Clock trace skipped or fabricated time')
        count += 1
    require(count == total+1 and result['clock_publications'] == count+repetitions,
            'Published time advanced during pause/stop')
    sensors = dict(arducopter=0, px4=0)
    for row in lines(root/'joint-wire.jsonl'):
        require(row['epoch'] == epoch and 0 <= row['tick'] <= total, 'Wire crossed scene identity')
        if row['kind'] in ('sensor', 'gps', 'step'):
            require(row['wall'] < start, 'Sensor or step was issued during pause/stop')
        if row['kind'] == 'sensor':
            sensors[row['stack']] += 1
    require(sensors == dict(arducopter=total, px4=total//4), 'Missing or extra sensor updates')

    channels = {'/clock': Clock, '/ap/wksim/local_state_v1': WksimState, '/ap/cmd_gps_pose': GlobalPosition}
    for uid in (1, 2):
        channels.update({f'/uav{uid}/prometheus/v2/state': SessionState,
                         f'/uav{uid}/prometheus/text_info': TextInfo})
    for direction, name, cls in (('out', 'vehicle_status', VehicleStatus),
            ('out', 'vehicle_local_position', VehicleLocalPosition),
            ('in', 'offboard_control_mode', OffboardControlMode),
            ('in', 'trajectory_setpoint', TrajectorySetpoint)):
        channels[topic('/wksim_px4_21', direction, name, cls)] = cls
    counts, revoked, sessions = {}, {}, {}
    outputs = {}; first_connected = {}; last_sequence = 0; last_clock = -1
    for row in lines(root/'pause-dds.jsonl'):
        require(row['sequence'] == last_sequence+1 and row['epoch'] == epoch and row['topic'] in channels,
                'Raw DDS sequence/identity differs')
        last_sequence = row['sequence']
        message = deserialize_message(bytes.fromhex(row['cdr_hex']), channels[row['topic']])
        if isinstance(message, Clock):
            stamp = message.clock.sec*10**9+message.clock.nanosec
            require(last_clock <= stamp <= row['tick']*1000000 and stamp % 1000000 == 0,
                    'Raw ROS time moved backwards, off-grid or past actual physics')
            last_clock = stamp
        if row['phase'] != 'paused':
            continue
        require(row['tick'] == total, 'Observation used a different paused tick')
        key = row['topic']; elapsed = row['wall']-start
        counts[key] = counts.get(key, 0)+1
        if isinstance(message, SessionState):
            uid = message.state.uav_id
            require(uid in (1, 2) and message.control.uav_id == uid and message.run_id == result['run_id'],
                    'Public session crossed run/vehicle')
            sessions[uid] = dict(connected=message.state.connected, odom_valid=message.state.odom_valid,
                failsafe=message.control.failsafe, control_epoch=message.control_epoch, elapsed=elapsed)
            first_connected.setdefault(uid, message.state.connected)
        elif isinstance(message, TextInfo):
            event = json.loads(message.message)
            if event['event'] == 'control_revoked':
                revoked.setdefault(key, dict(elapsed=elapsed, event=event))
        elif isinstance(message, (GlobalPosition, OffboardControlMode, TrajectorySetpoint)):
            value = outputs.setdefault(key, dict(count=0, first_elapsed=elapsed, last_elapsed=elapsed))
            value['count'] += 1; value['last_elapsed'] = elapsed
    require(set(sessions) == {1, 2} and all(first_connected.values()), 'Missing current public state at pause')
    require(last_clock == total*1000000, 'Raw consumer did not reach exact pause boundary')
    tasks = {}
    for stack in ('arducopter', 'px4'):
        task = json.loads((root/stack/'result.json').read_text())
        require(task['scene_epoch'] == epoch and task['run_id'] == result['run_id'], 'Task identity differs')
        tasks[stack] = dict(status=task['status'], error=task.get('error'),
            returncode=result['children'][stack+'-task']['returncode'],
            public_requests=len(task.get('task', {}).get('request_envelopes', [])))
    return dict(status='pass', scope='raw airborne pause observation audit; NOT flight/G2 acceptance',
        scene_epoch=epoch, tick=total, wall_pause_seconds=finish-start, heights_m=heights,
        model_steps_during_pause_and_stop=0, paused_clock_republications=repetitions,
        raw_dds_messages=last_sequence, paused_dds_counts=counts,
        final_public_sessions=sessions, control_revocations=revoked, cached_output_observations=outputs,
        tasks=tasks, owned_groups_without_residue=10, current_source_verification=verify_current_sources,
        source_sha256=result['source_sha256'], result_sha256=digest(root/'result.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--verify-current-sources', action='store_true')
    args = parser.parse_args()
    report = audit(args.directory, args.verify_current_sources)
    report['audit_source_sha256'] = digest(Path(__file__))
    report['evidence_sha256'] = {p.relative_to(args.directory).as_posix(): digest(p)
        for p in sorted(args.directory.rglob('*')) if p.is_file() and p.name != 'pause-audit.json'}
    (args.directory/'pause-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('evidence_sha256', 'source_sha256')}, indent=2))
