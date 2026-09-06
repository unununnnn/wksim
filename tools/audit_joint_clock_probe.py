"""Recheck raw ground-probe evidence; does not launch or command a simulator."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_joint_clock import encoded, digest, REPO
from Simulator.wksim_core.ap_json import decode_servos, sensor_message


def require(condition, message):
    if not condition:
        raise ValueError(message)


def lines(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            require(line.endswith('\n'), 'Partial evidence line: ' + path.name)
            yield json.loads(line)


def check_px_clock(tick, timestamp, previous, paused):
    require(type(timestamp) is int and timestamp >= 0, 'Invalid PX4 clock')
    require(timestamp <= tick * 1000, 'PX4 clock ran ahead of sensors')
    require(previous is None or timestamp >= previous, 'PX4 received clock regressed')
    if paused:
        require(timestamp == tick * 1000, 'PX4 packet clock changed inside pause')
    return timestamp


def audit(directory, verify_sources=False):
    directory = Path(directory)
    result = json.loads((directory / 'result.json').read_text())
    require(result['status'] == 'pass', 'Probe itself did not pass')
    for name, checksum in result['evidence_sha256'].items():
        require(Path(name).name == name, 'Nonlocal evidence name')
        require(digest(directory / name) == checksum, 'Evidence changed: ' + name)
    if verify_sources:
        for name, checksum in result['implementation_sha256'].items():
            require(digest(REPO / name) == checksum, 'Implementation changed: ' + name)
    for source, snapshot in result.get('source_snapshots', {}).items():
        require(Path(snapshot).name == snapshot, 'Nonlocal source snapshot')
        require(digest(directory / snapshot) == result['implementation_sha256'][source], 'Source snapshot changed')
    require(result['implementation_unchanged'], 'Sources changed during the run')
    native_clocks = result.get('native_clocks_enabled', False)
    scene_clock = result.get('scene_clock_enabled', False)
    require(type(native_clocks) is bool, 'Invalid native observer option')
    require(result['commands_sent'] == 0 and result['agents_started'] == (2 if native_clocks else 0)
            and result['ros_nodes_started'] == (3 if scene_clock else 1 if native_clocks else 0),
            'Unexpected control/ROS scope')
    require(not result['cleanup_errors'], 'Cleanup errors')
    require(result['unowned_ap_before'] == result['unowned_ap_after'], 'Unowned AP identity changed')
    expected_children = {'px4-model', 'arducopter-model', 'px4-fc', 'arducopter-fc'}
    if native_clocks:
        expected_children |= {'px4-agent', 'arducopter-agent'}
    require(set(result['children']) == expected_children, 'Unexpected process set')
    pids = [child['identity']['pid'] for child in result['children'].values()]
    require(len(set(pids)) == len(expected_children), 'Owned children do not have distinct OS processes')
    for name, child in result['children'].items():
        require(child['identity']['pid'] == child['identity']['pgid'], 'Not an owned process group')
        require(not child['remaining_group_members'], 'Residual process group: ' + name)
        if name.endswith('-model'):
            require(child['returncode'] == 0, 'Model did not flush/exit cleanly: ' + name)
    thresholds = result['thresholds']
    require(thresholds == dict(pre_ticks=8000, post_ticks=2000, macro_ticks=4, step_ms=1,
                              pause_wall_seconds=2.0, wall_limit=90.0), 'Experiment bounds changed')
    total = 10004
    require(result['final']['tick'] == total, 'Wrong final tick')
    states = {}
    for name in ('px4', 'arducopter'):
        values = list(lines(directory / (name + '-truth.jsonl')))
        require(len(values) == total, 'Missing or surplus model steps: ' + name)
        for tick, value in enumerate(values, 1):
            require(value['tick'] == tick and len(value['state']) == 120, 'Bad model record')
            require(all(math.isfinite(number) for number in value['state']), 'Nonfinite truth')
            require(abs(value['state'][2] - tick / 1000) <= 1e-8, 'Model clock is not authoritative')
            require(round(value['state'][60]) == tick * 1000, 'Raw model sensor clock differs')
            require(value['commands'] == [0.0] * 16, 'Nonzero ground motor inputs')
            if scene_clock:
                require(value['version'] == 1 and value['epoch'] == result['run_epoch'], 'Model crossed scene epoch')
                request = json.loads(value['input'])
                require(request == value['request'] == dict(version=1, epoch=result['run_epoch'],
                        tick=tick, commands=value['commands']), 'Actual worker input identity differs')
        states[name] = values
        admission = json.loads((directory / (name + '-preflight.json')).read_text())
        require(admission['ok'], 'Fixed-candidate admission failed')

    steps = list(lines(directory / 'steps.jsonl'))
    require(len(steps) == total, 'Wrong authoritative step count')
    for tick, value in enumerate(steps, 1):
        require(value['tick'] == tick and value['model_ticks'] == {'px4': tick, 'arducopter': tick},
                'Missing joint model barrier')
        require(value['ap_source_frame'] == tick - 1, 'AP actuator→step mapping differs')
        source = value['px4_source_time_usec']
        require(source is None or source <= (tick - 1) * 1000, 'PX4 used future output')
        require(not value['phase'].startswith('paused'), 'Model advanced during pause')
    single = [item['tick'] for item in steps if item['phase'] == 'single-macro-step']
    require(single == [8001, 8002, 8003, 8004], 'Single-step advanced wrong ticks')

    wire = list(lines(directory / 'wire.jsonl'))
    ap_frames, px_receipts, sends = [], set(), {'arducopter': [], 'px4': []}
    previous_px_time = None
    paused_ap_duplicates = Counter()
    for item in wire:
        name, tick = item['stack'], item['tick']
        if item['direction'] == 'send':
            require(not item['phase'].startswith('paused'), 'Sensor sent during pause')
            sends[name].append(tick)
            if name == 'arducopter':
                require(item['source_frame'] == tick - 1 and item['sensor_time'] == states[name][tick - 1]['state'][2],
                        'AP sensor→tick/source identity differs')
                value = json.loads(sensor_message(states[name][tick - 1]['state']))
                value.update(no_lockstep=False, no_time_sync=False)
                packet = ('\n' + encoded(value) + '\n').encode('ascii')
                require(hashlib.sha256(packet).hexdigest() == item['packet_sha256'], 'AP wire sensor hash differs')
            else:
                require(item['sensor_time_usec'] == tick * 1000, 'PX4 wire time differs')
        elif item['direction'] == 'receive' and name == 'arducopter':
            frame, rate, pwm, commands = decode_servos(bytes.fromhex(item['packet_hex']))
            require(frame == item['frame'] and rate == item['rate'] and pwm == item['pwm'], 'AP raw decode differs')
            require(commands == [0.0] * 16, 'Armed/nonzero AP output')
            require(frame == tick, 'AP next request is not at the recorded sensor boundary')
            ap_frames.append(frame)
            if item['phase'].startswith('paused'):
                paused_ap_duplicates[item['phase']] += 1
        elif item['direction'] == 'receive' and name == 'px4':
            from pymavlink.dialects.v20 import common as mavlink
            message = mavlink.MAVLink(None).parse_buffer(bytes.fromhex(item['packet_hex']))
            require(len(message) == 1 and message[0].to_dict() == item['message'], 'PX4 raw decode differs')
            value = item['message']
            require(value['mavpackettype'] == 'HIL_ACTUATOR_CONTROLS' and value['flags'] & 1
                    and not value['mode'] & 128, 'PX4 is armed or not lockstep')
            previous_px_time = check_px_clock(tick, value['time_usec'], previous_px_time,
                                               item['phase'].startswith('paused'))
            px_receipts.add((tick, value['time_usec']))
    require(sends['arducopter'] == list(range(1, total + 1)), 'AP sensor sequence not exactly once')
    require(sends['px4'] == list(range(4, total + 1, 4)), 'PX4 sensor sequence differs')
    require(sorted(set(ap_frames)) == list(range(total + 1)), 'Missing AP next-frame confirmation')
    barriers = list(lines(directory / 'barriers.jsonl'))
    require([item['tick'] for item in barriers] == list(range(4, total + 1, 4)), 'Missing macro barriers')
    strict = False
    for item in barriers:
        strict |= item['synchronized']
        if strict:
            require(item['synchronized'] and item['px4_time_usec'] == item['tick'] * 1000
                    and (item['tick'], item['px4_time_usec']) in px_receipts, 'Unproven strict PX4 barrier')
        require(item['ap_next_frame'] == item['tick'], 'AP barrier mapping differs')
    require(strict, 'No post-startup strict phase')

    require(len(result['pauses']) == 2, 'Wrong pause count')
    for index, pause in enumerate(result['pauses']):
        tick = 8000 + 4 * index
        before, after = pause['before'], pause['after']
        require(pause['wall_seconds'] >= 2, 'Pause too short')
        require(before['tick'] == after['tick'] == tick, 'Clock advanced during pause')
        require(before['models'] == after['models'], 'Model state changed during pause')
        for name in states:
            value = before['models'][name]
            expected = hashlib.sha256(encoded(states[name][tick - 1]['state']).encode()).hexdigest()
            require(value['tick'] == tick and value['state_sha256'] == expected, 'Pause snapshot not raw model truth')
        require(before['px4_time_usec'] == after['px4_time_usec'] == tick * 1000, 'PX4 pause clock changed')
        require(before['ap_pending_frame'] == after['ap_pending_frame'] == tick, 'AP request advanced in pause')
        for name in ('sensor_ap', 'sensor_px4'):
            require(before['raw_counts'][name] == after['raw_counts'][name], 'Sensors changed during pause')
    require(all(paused_ap_duplicates[name] >= 1 for name in
                ('paused-before-single-step', 'paused-after-single-step')), 'No live AP retransmission during pauses')

    telemetry = [item for item in lines(directory / 'telemetry.jsonl') if 'message' in item]
    counts = Counter((item['stack'], item['message']['mavpackettype']) for item in telemetry)
    for item in telemetry:
        value = item['message']
        if value['mavpackettype'] == 'HEARTBEAT':
            require(not value['base_mode'] & 128, 'Armed native heartbeat')
    for name in states:
        require(counts[(name, 'HEARTBEAT')] and counts[(name, 'ATTITUDE')], 'Missing native observations')
    summary = dict(status='pass', result_sha256=digest(directory / 'result.json'), total_ticks=total,
                   model_steps={name: len(values) for name, values in states.items()},
                   macro_barriers=len(barriers), strict_barriers=sum(x['synchronized'] for x in barriers),
                   first_strict_tick=next(x['tick'] for x in barriers if x['synchronized']),
                   pause_wall_seconds=[x['wall_seconds'] for x in result['pauses']],
                   paused_ap_duplicates=dict(paused_ap_duplicates),
                   native_observations={name: {kind: counts[(name, kind)] for kind in ('HEARTBEAT', 'ATTITUDE')}
                                        for name in states},
                   source_verification=verify_sources,
                   scope='raw model/input barriers only; AP control-loop ACK and exact native microsecond alignment NOT proven')
    if native_clocks:
        from joint_clock_observer import audit_native_clock
        summary['native_clocks'] = audit_native_clock(directory, result)
    if result.get('require_aligned_clocks'):
        require(native_clocks, 'No real native clock evidence for alignment assertion')
        require(all(clock['off_millisecond_grid'] == 0 for clock in summary['native_clocks']['clocks'].values()),
                'Native clocks are not on the authoritative 1ms grid')
        summary['scope'] = 'Measured native microseconds and raw input barriers aligned; not per-control-loop ACK'
    if result.get('ap_build_manifest_sha256'):
        require(digest(directory / 'ap-build-manifest.json') == result['ap_build_manifest_sha256'],
                'Experimental AP manifest differs from explicitly selected build')
        require(result['children']['arducopter-fc']['returncode'] == 0,
                'Experimental AP did not stop normally without further physics steps')
    if scene_clock:
        events = list(lines(directory / 'scene-clock.jsonl'))
        published = [e for e in events if e['kind'] == 'publish']
        observed = [e for e in events if e['kind'] == 'observe']
        actions = [e for e in events if e['kind'] == 'action']
        require([e['authority']['tick'] for e in published] == list(range(total+1)), 'ROS clock publication skipped/added ticks')
        for e in published:
            a = e['authority']
            require(a['epoch'] == result['run_epoch'] and a['time_ns'] == a['tick']*1000000
                    and a['pending_tick'] is None and e['tick'] == a['tick'], 'Published uncommitted/mixed-epoch time')
        require([e['request']['action'] for e in actions] == ['pause', 'step', 'resume', 'stop'], 'Scene lifecycle actions differ')
        require([e['request']['request_id'] for e in actions] == [1, 2, 3, 4], 'Scene requests were replayed')
        require(all(e['request']['epoch'] == result['run_epoch'] for e in actions), 'Action from wrong epoch')
        stamps = [e['ros_time_ns'] for e in observed]
        require(len(stamps) >= 5 and stamps[0] == 0 and stamps[-1] == total*1000000
                and stamps == sorted(set(stamps)), 'Real ROS consumer did not cover this monotone clock')
        require(all(e['ros_time_ns'] % 1000000 == 0 and 0 <= e['ros_time_ns'] <= e['tick']*1000000
                    for e in observed), 'Real ROS consumer ran off-grid or ahead of physics')
        report = result['scene_clock_observer']
        require(report['samples'] == len(stamps) and report['publications'] == len(published)
                and report['consumer_use_sim_time'] and report['ros_time_is_active']
                and report['publisher_count'] == 1 and report['duplicate_owner_rejected'], 'Unproven ROS /clock ownership/consumer')
        for pause in result['pauses']:
            before, after = pause['before'], pause['after']
            require(before['authority'] == after['authority'] and before['authority']['phase'] == 'paused'
                    and before['ros_time_ns'] == after['ros_time_ns'] == before['tick']*1000000,
                    'Paused authority or actual ROS time advanced')
        require(result['initial_authority']['tick'] == 0 and result['initial_authority']['pending_tick'] is None
                and result['stopped_authority']['tick'] == total and result['stopped_authority']['phase'] == 'stopped',
                'Initial/final authority bounds differ')
        if result['retired_epoch']:
            require(result['retired_epoch'] != result['run_epoch'] and result['retired_request_rejected'],
                    'Cold scene accepted an old lifecycle request')
        summary['scene_clock'] = dict(publications=len(published), observed_distinct_times=len(stamps),
                                     epoch=result['run_epoch'], retired_epoch=result['retired_epoch'],
                                     actions=[e['request']['action'] for e in actions], stop_tick=total,
                                     scope='real epoch-fenced model/FC and ROS clock lifecycle, not joint mission/task timers')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--verify-current-sources', action='store_true')
    args = parser.parse_args()
    report = audit(args.directory, args.verify_current_sources)
    report['audit_source_sha256'] = digest(Path(__file__))
    (args.directory / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
