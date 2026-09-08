"""Independent offline raw audit of the frozen full-XYZ P+V candidate flight.

No publisher, admission, simulator or process launch. A pass needs the real run;
unit checks of this auditor do not establish flight acceptance.
"""
import argparse
from bisect import bisect_left
from collections import Counter
import json
import math
from pathlib import Path
import re
import struct
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from audit_joint_flight import audit_timeline, digest, lines, require
from audit_joint_rate import schedule, measurement
from Simulator.wksim_runtime.evidence import json_value

PROFILE = 'full_xyz_pv_yaw_v1'
DELTAS = ((1.5, 1., .4, .6), (-1., .5, -.2, -.3))
STACKS = (('arducopter', 1), ('px4', 2))


def read(path):
    return json.loads(Path(path).read_text())


def stamp(message):
    value = message['header']['stamp']
    return value['sec'] * 1_000_000_000 + value['nanosec']


def angle(value):
    return math.remainder(value, 2 * math.pi)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def wire_command(command):
    """The generated Python setter retains yaw double precision until CDR float32 encoding."""
    require(type(command['yaw_ref']) is float and math.isfinite(command['yaw_ref']), 'Invalid pre-encoding yaw scalar')
    return dict(command, yaw_ref=f32(command['yaw_ref']))


def wire_request(request):
    return dict(request, command=wire_command(request['command'])) if 'command' in request else request


def rejected_bootstrap_ack(event, event_ns, first_request_ns):
    """An unsolicited ACK rejected before any public request is not a failed task ACK."""
    identity = event.get('request_identity')
    return (0 <= event_ns < first_request_ns and event.get('event') == 'native_input_rejected'
            and event.get('reason') == 'unmatched_ack' and event.get('source') == 'ack'
            and event.get('request_id') == 0 and type(event.get('command')) is int
            and 0 <= event['command'] <= 65535 and isinstance(identity, list) and len(identity) == 2
            and all(type(v) is int and 0 <= v <= 255 for v in identity))


def analytic(elapsed, position, yaw, leg):
    """Independently evaluate the frozen polynomial, not the executed task helper."""
    require(leg in (1, 2) and math.isfinite(elapsed), 'Invalid analytic reference')
    s = min(1., max(0., elapsed / 12.))
    q = s**3 * (10 + s * (-15 + 6*s))
    dq = 30*s*s*(1-s)**2 / 12.
    ddq = 60*s*(1-s)*(1-2*s) / 144.
    delta = DELTAS[leg-1]
    return ([p+d*q for p, d in zip(position, delta)],
            [d*dq for d in delta[:3]], [d*ddq for d in delta[:3]], yaw+delta[3]*q)


def enu(state):
    return [state[7], state[6], -state[8]], [state[4], state[3], -state[5]], angle(math.pi/2-state[11])


def close_vector(actual, expected, tolerance=1e-6):
    return len(actual) == len(expected) and all(math.isfinite(a) and abs(a-b) <= tolerance for a, b in zip(actual, expected))


def tracking(state, reference):
    position, velocity, yaw = enu(state)
    p, v, _, heading = reference
    metrics = [math.dist(position, p), max(abs(a-b) for a, b in zip(velocity, v)), abs(angle(yaw-heading))]
    require(all(value <= limit for value, limit in zip(metrics, (.5, .3, .15))),
            '1ms trajectory/endpoint gate exceeded: '+str(metrics))
    return metrics


def truth_window(rows, start_ns, end_ns):
    require(type(start_ns) is int and type(end_ns) is int and start_ns % 1_000_000 == end_ns % 1_000_000 == 0
            and 1_000_000 <= start_ns < end_ns <= len(rows)*1_000_000, 'Physical window is off-grid or incomplete')
    return rows[start_ns//1_000_000-1:end_ns//1_000_000]


def retained_identity(root, result):
    require(result['status'] == 'pass' and result['flight_completed'] and result['source_unchanged']
            and result['control_shutdown_clean'] and not result['cleanup_errors'], 'Candidate run/cleanup did not pass')
    require(result['task_profile'] == PROFILE and result['unowned_ap_before'] == result['unowned_ap_after'],
            'Wrong task profile or unrelated process changed')
    require(result['bounds'] == dict(wall_seconds=900, simulation_ticks=180000, task_position_error_m=.5,
            task_speed_m_s=.5, takeoff_min_height_m=2.5, ground_abs_height_m=.3), 'Frozen run bounds changed')
    final = result['final_authority']
    terminal = result['terminal_transition']
    require(terminal['action'] == 'stop' and terminal['phase'] == 'stopped' and terminal['tick'] == final['tick']
            and type(terminal['issued_monotonic_ns']) is int, 'Missing explicit terminal boundary')
    require(final['epoch'] == result['scene_epoch'] and final['phase'] == 'stopped' and final['pending_tick'] is None
            and 0 < final['tick'] <= 180000 and final['tick'] % 4 == 0 and result['wall_seconds'] <= 900,
            'Final authority or watchdog bound differs')
    for key in ('pause_probe_requested', 'scene_lifecycle_requested', 'scene_lease_loss_requested', 'dds_loss_requested',
                'diagnostic_land_step_period_s'):
        require(not result.get(key), 'Unexpected alternate workflow: '+key)
    sources = result['source_sha256']
    mandatory = {'tools/run_joint_flight.py', 'tools/pv_trajectory_task.py', 'tools/ap_pv_candidate.py',
                 'tools/verify_ap_pv_candidate.py', 'Simulator/wksim_runtime/task.py',
                 'Simulator/wksim_runtime/joint_rate.py', 'docs/2026-09-09-pv-flight-plan.md'}
    require(mandatory <= sources.keys(), 'Missing executed source identity')
    expected_names = {'source__'+name.replace('/', '__')+'.txt' for name in sources}
    require({p.name for p in root.glob('source__*')} == expected_names, 'Missing/extra retained source file')
    for name, expected in sources.items():
        require(digest(root/('source__'+name.replace('/', '__')+'.txt')) == expected, 'Retained source changed: '+name)
    admission = read(root/'experimental-admission.json')
    require(admission == result['pv_admission'] and admission['ok'] and admission['experimental']
            and not admission['production_admitted'] and not admission['flown']
            and admission['children_created'] == 0 and not admission['reasons'] and admission['task_profile'] == PROFILE,
            'Experimental admission identity/scope differs')
    require(admission['capability'] == dict(profile=PROFILE, position_axes='xyz', velocity_axes='xyz', yaw=True,
            acceleration=False, yaw_rate=False, mixed_axes=False, arducopter_type_mask=2496), 'Capability scope changed')
    for name, expected in admission['identities']['source_sha256'].items():
        require(sources.get(name) == expected, 'Admission/execution source mismatch: '+name)
    require(digest(root/'ap-build.json') == result['manifest_sha256']['ap'] == admission['manifest_sha256']
            and digest(root/'control-build.json') == result['manifest_sha256']['control'] == admission['control_manifest_sha256'],
            'Selected build manifest changed')
    ap, control = read(root/'ap-build.json'), read(root/'control-build.json')
    require(ap == admission['candidate'] and control == admission['control_candidate'] == result['control_candidate']
            and control['python_sha256'] == result['control_source_sha256'], 'Candidate record differs')
    actual = {p.relative_to(root/'control-source').as_posix(): digest(p)
              for p in (root/'control-source').rglob('*') if p.is_file()}
    require(actual == control['python_sha256'], 'Sealed retained control source differs')
    verified = admission['candidate_verification']
    require(verified == admission['identities']['ap_pv'] and verified['status'] == 'verified-built-not-admitted'
            and verified['current_source_matches_prebuild_snapshot'] and verified['fixed_baseline_unchanged']
            and verified['source_files'] == 24593 and verified['manifest_sha256'] == admission['manifest_sha256']
            and verified['source_manifest_sha256'] == ap['source_manifest_sha256']
            and verified['artifacts']['build/sitl/bin/arducopter']['sha256'] == ap['binary_sha256'],
            'Full source admission is missing or bound to another candidate')
    baseline = admission['identities']['baseline']
    profiles = read(root/'source__Simulator__wksim_runtime__joint-profiles.json.txt')['profiles']
    pinned = next(p for p in profiles if p['id'] == 'joint_quad_dds_v1')
    require(admission['baseline_profile'] == pinned and baseline['manifests'] == pinned['manifests']
            and ap['baseline_manifest_sha256'] == pinned['manifests']['ap']['sha256']
            and control['root'] != pinned['control_workspace'], 'Fixed baseline/candidate separation differs')
    require(result['model_build'] == baseline['model'], 'Physical model differs from admission')
    expected_firmware = {'arducopter': dict(path=ap['binary'], sha256=ap['binary_sha256']), 'px4': baseline['px4']}
    require(len(result['children']) == 10 and set(result['native_runtime_maps']) == {'running', 'completed'},
            'Missing owned processes or native mapping observations')
    for name, child in result['children'].items():
        require(child['identity']['pid'] == child['identity']['pgid'] and not child['remaining_group_members']
                and child['returncode'] is not None, 'Unretired owned group: '+name)
        if name.endswith(('-model', '-task', '-control')):
            require(child['returncode'] == 0, 'Unclean child exit: '+name)
    for stack, _ in STACKS:
        expected = expected_firmware[stack]
        child = result['children'][stack+'-fc']
        require(child['argv'][0] == expected['path'], 'Executed firmware selection differs')
        for label in ('running', 'completed'):
            observation = result['native_runtime_maps'][label][stack]
            require(observation['scene_phase'] == ('running' if label == 'running' else 'stopped')
                    and (label == 'running' or observation['captured_monotonic_ns'] >= terminal['issued_monotonic_ns']),
                    'Final native mapping was not captured after the explicit stop')
            require(all(observation['identity'][k] == child['identity'][k] for k in ('pid', 'pgid', 'start_ticks'))
                    and observation['executable'] == expected['path'] and observation['executable_sha256'] == expected['sha256']
                    and not observation['forbidden_libraries'], 'Native loaded process/binary identity differs')
            path = root/observation['maps_file']
            require(path.parent == root and digest(path) == observation['sha256'], 'Native maps file changed/escaped')
            raw = path.read_text()
            require(any(line.split()[-1] == expected['path'] and 'x' in line.split()[1] for line in raw.splitlines())
                    and not any(token in raw.lower() for token in ('libgz-', 'libgazebo', 'libignition', 'matlab', '(deleted)')),
                    'Native maps lack executable or contain forbidden/deleted files')
    require(set(result['model_runtime_maps']) == {'running', 'completed'}, 'Missing physical model mapping observations')
    for stack, _ in STACKS:
        observed = [result['model_runtime_maps'][label][stack] for label in ('running', 'completed')]
        child = result['children'][stack+'-model']
        for label, record in zip(('running', 'completed'), observed):
            require(record['scene_phase'] == ('running' if label == 'running' else 'stopped')
                    and (label == 'running' or record['captured_monotonic_ns'] >= terminal['issued_monotonic_ns']),
                    'Final model mapping was not captured after the explicit stop')
            require(all(record['identity'][key] == child['identity'][key] for key in ('pid', 'pgid', 'start_ticks'))
                    and record['model_library'] == baseline['model']['library']
                    and record['model_library_sha256'] == baseline['model']['library_sha256']
                    and re.fullmatch('[0-9a-f]{64}', record['executable_sha256']), 'Physical model process/library identity differs')
            path = root/record['maps_file']
            require(path.parent == root and digest(path) == record['maps_sha256'], 'Physical model maps file differs')
            raw = path.read_text()
            for expected in (record['executable'], record['model_library']):
                require(any(line.split()[-1] == expected and 'x' in line.split()[1] for line in raw.splitlines()),
                        'Actual physical process did not map executable/model library')
            require(not any(token in raw.lower() for token in ('libgz-', 'libgazebo', 'libignition', 'matlab', 'coptersim.exe', '(deleted)')),
                    'Physical process mapped forbidden/deleted libraries')
        require(observed[0]['executable'] == observed[1]['executable']
                and observed[0]['executable_sha256'] == observed[1]['executable_sha256'], 'Physical model executable changed during run')
    return dict(source_files=len(sources), retained_control_files=len(actual), admitted_ap_source_files=verified['source_files'],
                native_executable_sha256={s: v['sha256'] for s, v in expected_firmware.items()},
                loaded_maps_verified=['running', 'completed'])


def decode(root, result):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from prometheus_msgs.msg import TextInfo
    from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState
    from std_msgs.msg import Bool
    from ardupilot_msgs.msg import GlobalPosition, WksimState
    from px4_msgs.msg import TrajectorySetpoint, OffboardControlMode, VehicleLocalPosition, VehicleStatus
    from Simulator.wksim_runtime.joint_profile import package_digest
    for name, pin in result['pv_admission']['identities']['baseline']['message_packages'].items():
        require(package_digest(pin['prefix'], complete=pin.get('complete_snapshot', False)) == pin['sha256'],
                'Raw CDR message schema package differs: '+name)
    types = {'/ap/cmd_gps_pose': GlobalPosition, '/ap/wksim/local_state_v1': WksimState}
    for _, uid in STACKS:
        for suffix, cls in (('v2/command', CommandRequest), ('v2/setup', SetupRequest), ('v2/state', SessionState),
                            ('text_info', TextInfo), ('stop_control_state', Bool)):
            types[f'/uav{uid}/prometheus/'+suffix] = cls
    for direction, name, cls in (('in', 'trajectory_setpoint', TrajectorySetpoint), ('in', 'offboard_control_mode', OffboardControlMode),
                                ('out', 'vehicle_local_position', VehicleLocalPosition), ('out', 'vehicle_status', VehicleStatus)):
        version = getattr(cls, 'MESSAGE_VERSION', 0)
        types[f'/wksim_px4_21/fmu/{direction}/{name}'+(f'_v{version}' if version else '')] = cls
    data = {name: [] for name in types}
    previous_tick, previous_wall = 0, 0.
    for number, row in enumerate(lines(root/'pv-dds.jsonl'), 1):
        require(row['sequence'] == number and row['epoch'] == result['scene_epoch']
                and previous_tick <= row['tick'] <= result['final_authority']['tick']
                and math.isfinite(row['wall']) and previous_wall <= row['wall'] <= 900
                and row['topic'] in types, 'Invalid raw DDS chronology/topic/identity')
        raw = bytes.fromhex(row['cdr_hex'])
        require(len(raw) > 4, 'Truncated raw CDR')
        message = message_to_ordereddict(deserialize_message(raw, types[row['topic']]))
        data[row['topic']].append((row, message))
        previous_tick, previous_wall = row['tick'], row['wall']
    require(all(data.values()), 'Missing required public/native raw DDS channel')
    return data


def task_evidence(root, result, data):
    tasks, phases, requests = {}, {}, {}
    tokens = set()
    for stack, uid in STACKS:
        report = read(root/stack/'result.json')
        require(report == result['tasks'][stack] and report['status'] == 'pass' and report['run_id'] == result['run_id']
                and report['scene_epoch'] == result['scene_epoch'] and report['uav_id'] == uid and report['use_sim_time']
                and report['task_profile'] == PROFILE, 'Task report identity differs')
        task = report['task']; tasks[stack] = task
        graph = task['pv_request_graph']
        require(set(graph) == {'setup', 'command'}, 'Missing named passive-observer graph proof')
        for endpoints in graph.values():
            require(len(endpoints) == 2 and {e['node_name'] for e in endpoints} == {
                'wksim_joint_'+stack+'_control', 'wksim_joint_flight_clock'}
                and all(e['node_namespace'] == '/' and re.fullmatch('[0-9a-f]+', e['endpoint_gid'])
                        and int(e['endpoint_gid'], 16) != 0 for e in endpoints),
                'Unexpected control/observer subscriber graph')
        require(task['pv_profile'] == PROFILE and len(task['pv_legs']) == 2 and not task['control_restarts'], 'Missing/restarted P+V task')
        phase = {p['phase']: p for p in report['phases']}; phases[stack] = phase
        counts = Counter(p['phase'] for p in report['phases'])
        require(all(count == 1 or name in ('pv_1_reference', 'pv_2_reference') for name, count in counts.items()),
                'Unexpected repeated phase')
        times = [p['ros_time_ns'] for p in report['phases']]
        require(times == sorted(times) and all(type(t) is int and 0 < t <= result['final_authority']['tick']*1_000_000
                and t % 1_000_000 == 0 for t in times), 'Task phase clock is off authoritative grid')
        base = f'/uav{uid}/prometheus/'
        raw_requests = sorted(data[base+'v2/setup']+data[base+'v2/command'], key=lambda item: item[1]['request_id'])
        requests[stack] = raw_requests
        require([m for _, m in raw_requests] == [wire_request(r) for r in task['request_envelopes']]
                and len(raw_requests) == len(task['sent']),
                'Raw public request stream differs from task report')
        setups = [(i, e['setup']) for i, (_, e) in enumerate(raw_requests) if 'setup' in e]
        require([i for i, _ in setups] == [0, 1, 2, len(raw_requests)-1]
                and [m['cmd'] for _, m in setups] == [1, 0, 3, 1]
                and setups[0][1]['px4_mode'] == setups[-1][1]['px4_mode'] == 'AUTO.LOITER'
                and setups[1][1]['arming'] and setups[2][1]['control_state'] == 'COMMAND_CONTROL',
                'Unexpected public setup sequence')
        commands = [e['command'] for _, e in raw_requests if 'command' in e]
        expected_agents = [4]
        for record in task['pv_legs']:
            expected_agents += [4]*len(record['samples'])+[2]
        expected_agents += [3]
        require([m['agent_cmd'] for m in commands] == expected_agents
                and [m['command_id'] for m in commands] == list(range(1, len(commands)+1))
                and commands[0]['move_mode'] == 0 and commands[0]['position_ref'] == [2., 3., 3.]
                and commands[0]['yaw_ref'] == 0. and commands[0]['control_level'] == 0
                and all(m['move_mode'] == 6 for m in commands[1:] if m['agent_cmd'] == 4),
                'Unexpected/replayed public command sequence')
        events = []
        first_request_ns = min(stamp(e.get('command', e.get('setup'))) for _, e in raw_requests)
        for row, message in data[base+'text_info']:
            event = json.loads(message['message'])
            require(message['message_type'] < 2 or message['message_type'] == 2
                    and event.get('run_id') == result['run_id'] and event.get('control_epoch') == task['control_epoch']
                    and rejected_bootstrap_ack(event, stamp(message), first_request_ns),
                    'Unexpected raw public ERROR/FATAL: '+str(event))
            if event.get('run_id') != result['run_id'] or event.get('control_epoch') != task['control_epoch']:
                require(event.get('request_id', 0) == 0, 'Foreign request event')
                continue
            require(event.get('event') not in ('setup_rejected', 'command_rejected', 'control_revoked')
                    and not event.get('error') and not (event.get('event') == 'native_ack' and not event.get('accepted')),
                    'Unexpected raw rejection/revocation/native failure')
            events.append(event)
        require(all(event in events for event in task['events']), 'Task event has no raw CDR corroboration')
        for index, ((row, envelope), sent) in enumerate(zip(raw_requests, task['sent']), 1):
            require(envelope['version'] == 1 and envelope['run_id'] == result['run_id']
                    and envelope['control_epoch'] == task['control_epoch'] and envelope['request_id'] == index,
                    'Public request identity/replay differs')
            setup = 'setup' in envelope; body = envelope['setup' if setup else 'command']
            recorded = task['request_envelopes'][index-1]
            require(recorded['setup' if setup else 'command'] == sent
                    and body == (sent if setup else wire_command(sent)) and body['header']['frame_id'] == 'map'
                    and 0 < stamp(body) <= row['tick']*1_000_000, 'Public payload/frame/clock differs')
            accepted = [e for e in events if e.get('request_id') == index and e.get('event') == ('setup_completed' if setup else 'command_accepted')]
            require(len(accepted) == 1 and (setup or accepted[0]['command_id'] == body['command_id']), 'Public acceptance missing/duplicated')
            acks = [e for e in events if e.get('request_id') == index and e.get('event') == 'native_ack']
            if setup:
                require(acks and all(e['accepted'] for e in acks), 'Public setup lacks native setup ACK')
            elif body['agent_cmd'] != 3:
                require(not acks, 'Trajectory/hover target incorrectly claimed a native ACK')
        states = data[base+'v2/state']
        require(all(a['sequence'] < b['sequence'] for (_, a), (_, b) in zip(states, states[1:])), 'Public state sequence regressed')
        for _, message in states:
            require(message['version'] == 1 and message['run_id'] == result['run_id']
                    and message['control_epoch'] == task['control_epoch']
                    and message['state']['uav_id'] == message['control']['uav_id'] == uid, 'Public state crossed session/vehicle')
        # The retained runner writes explicit markers for unavailable telemetry
        # (e.g. battery/range NaN); raw CDR retains IEEE nonfinite values.
        fresh_states = {json.dumps(json_value(m['state']), sort_keys=True)
                        for _, m in states if m['source_received_valid']
                        and 0 <= m['published_monotonic_s']-m['source_received_monotonic_s'] <= 2}
        for p in report['phases']:
            if p['state'] is not None:
                require(json.dumps(p['state'], sort_keys=True) in fresh_states,
                        'Phase state lacks fresh raw public corroboration: '+stack+'/'+p['phase'])
        final = task['final']['state']
        require(final['connected'] and final['odom_valid'] and not final['armed'] and abs(final['position'][2]) < .3,
                'Task did not finish freshly grounded')
        for leg, record in enumerate(task['pv_legs'], 1):
            ready = read(root/stack/f'pv-ready-{leg}.json'); go = read(root/f'pv-go-{leg}.json')
            require(ready == record['ready'] == go['tasks'][stack] and go == record['offer'], 'Ready/go echo differs')
            require(ready['version'] == go['version'] == 1 and ready['profile'] == go['profile'] == PROFILE
                    and ready['leg'] == go['leg'] == leg and ready['run_id'] == go['run_id'] == result['run_id']
                    and ready['scene_epoch'] == go['scene_epoch'] == result['scene_epoch']
                    and ready['control_epoch'] == task['control_epoch'] and ready['uav_id'] == uid
                    and re.fullmatch('[0-9a-f]{32}', ready['token']) and ready['token'] not in tokens,
                    'Trajectory readiness is foreign/reused')
            tokens.add(ready['token'])
            require(type(go['start_ns']) is int and go['start_ns'] % 4_000_000 == 0
                    and type(go['issued_tick']) is int and go['issued_tick'] % 4 == 0
                    and go['start_ns'] == (go['issued_tick']+1000)*1_000_000
                    and phase[f'pv_{leg}_offer_ready']['ros_time_ns'] < go['start_ns']
                    <= phase[f'pv_{leg}_started']['ros_time_ns'] <= go['start_ns']+250_000_000,
                    'Common start/offer clock differs')
            require(record['acceleration_executed'] is False, 'Acceleration execution scope changed')
            origin_phase = phase['waypoint_completed' if leg == 1 else 'pv_1_stop_held']
            if leg == 1:
                require(ready['position'] == [2., 3., 3.] and ready['yaw'] == 0., 'First origin differs')
            else:
                require(ready['position'] == origin_phase['state']['position']
                        and ready['yaw'] == origin_phase['state']['attitude'][2], 'Second leg reused old origin')
            require(origin_phase['state']['connected'] and origin_phase['state']['odom_valid']
                    and 0 <= origin_phase['ros_time_ns']-stamp(origin_phase['state']) <= 2_000_000_000,
                    'Trajectory origin lacks fresh actual state')
            samples = record['samples']
            require(len(samples) >= 49 and 0 <= samples[0]['elapsed'] <= .25 and samples[-1]['elapsed'] >= 12
                    and all(0 < b['elapsed']-a['elapsed'] <= .250000000001 for a, b in zip(samples, samples[1:])),
                    'Reference sequence absent, repeated, or exceeded 250ms')
            native_requests = [(row, env) for row, env in raw_requests if 'command' in env
                               and env['command']['agent_cmd'] == 4 and env['command']['move_mode'] == 6
                               and go['start_ns'] <= stamp(env['command']) < go['start_ns']+12_250_000_001]
            require(len(native_requests) == len(samples), 'Samples do not match raw trajectory request count')
            for i, (sample, (_, env)) in enumerate(zip(samples, native_requests)):
                command = env['command']; expected = analytic(sample['elapsed'], ready['position'], ready['yaw'], leg)
                require(abs(sample['ros_time_s']-go['start_ns']/1e9-sample['elapsed']) < 1e-8
                        and abs(stamp(command)/1e9-sample['ros_time_s']) <= .004000001,
                        'Reference timestamp differs from analytic sample')
                for key, values in zip(('position', 'velocity', 'acceleration'), expected[:3]):
                    require(close_vector(sample[key], values, 1e-10)
                            and close_vector(command[key+'_ref'], [f32(v) for v in values]), 'Raw reference polynomial differs')
                require(abs(sample['yaw']-expected[3]) < 1e-10 and abs(command['yaw_ref']-f32(expected[3])) <= 1e-6
                        and not command['yaw_rate_mode'] and command['yaw_rate_ref'] == 0
                        and command['control_level'] == (2 if leg == 2 and i == 0 else 0), 'Reference yaw/control level differs')
            last = native_requests[-1][1]['command']
            require(close_vector(last['velocity_ref'], [0., 0., 0.], 0), 'Exact endpoint does not command zero velocity')
            stop = [env['command'] for _, env in raw_requests if 'command' in env and env['command']['agent_cmd'] == 2
                    and abs(stamp(env['command'])/1e9-record['stop_requested_ros_s']) <= .004000001]
            require(len(stop) == 1 and stop[0]['control_level'] == 1
                    and record['stop_anchor'] == phase[f'pv_{leg}_endpoint_held']['state']['position'], 'Stop/anchor differs')
        stop_values = [m['data'] for _, m in data[base+'stop_control_state']]
        require(stop_values == [True, False, True, False], 'Actual stop Bool transitions differ')
        transition_commands = [e['command'] for _, e in raw_requests if 'command' in e
                               and e['command']['control_level'] in (1, 2)]
        require(len(transition_commands) == 4, 'Unexpected absolute-control command')
        for (row, message), command in zip(data[base+'stop_control_state'], transition_commands):
            require(stamp(command) <= row['tick']*1_000_000
                    and message['data'] == (command['control_level'] == 1), 'Stop Bool predates/differs from public transition')
        lands = [e['command'] for _, e in raw_requests if 'command' in e and e['command']['agent_cmd'] == 3]
        require(len(lands) == 1 and lands[0]['control_level'] == 2, 'LAND did not exit absolute control')
    require(tasks['arducopter']['control_epoch'] != tasks['px4']['control_epoch'], 'Control epochs not distinct')
    return tasks, phases, requests


def physical(root, result, tasks, phases):
    timeline, _ = audit_timeline(root, result, phases)
    output = {}
    for stack, _ in STACKS:
        rows = [row['state'] for row in lines(root/(stack+'-truth.jsonl'))]
        phase = phases[stack]; legs = []
        for start, end, seconds in (('takeoff_reached', 'hold_completed', 5), ('waypoint_reached', 'waypoint_completed', 2)):
            lo, hi = phase[start]['ros_time_ns'], phase[end]['ros_time_ns']
            require(hi-lo >= seconds*1_000_000_000, 'Baseline dwell shortened')
            for state in truth_window(rows, lo, hi):
                p, v, yaw = enu(state)
                if start == 'waypoint_reached':
                    require(math.dist(p, [2, 3, 3]) <= .5 and math.hypot(*v) <= .5 and abs(yaw) <= .15,
                            'Baseline raw physical position/speed/yaw gate exceeded')
                else:
                    require(abs(p[2]-3) <= .6 and max(abs(v) for v in state[9:11]) <= .35, 'Raw initial hold gate exceeded')
        for leg, record in enumerate(tasks[stack]['pv_legs'], 1):
            ready = record['ready']; start = record['offer']['start_ns']; end = start+12_000_000_000
            maxima = [0., 0., 0.]
            for offset, state in enumerate(truth_window(rows, start, end)):
                values = tracking(state, analytic(offset/1000., ready['position'], ready['yaw'], leg))
                maxima = [max(a, b) for a, b in zip(maxima, values)]
            prepared = phase[f'pv_{leg}_endpoint_prepared']['ros_time_ns']
            held = phase[f'pv_{leg}_endpoint_held']['ros_time_ns']
            last_stamp = round(record['samples'][-1]['ros_time_s']*1e9)
            require(prepared-last_stamp >= 2_000_000_000 and held-prepared >= 2_000_000_000,
                    'Endpoint preparation/hold shorter than frozen 2s/2s')
            for state in truth_window(rows, prepared, held):
                tracking(state, analytic(12., ready['position'], ready['yaw'], leg))
            stop_prepared = phase[f'pv_{leg}_stop_prepared']['ros_time_ns']
            stop_held = phase[f'pv_{leg}_stop_held']['ros_time_ns']
            require(stop_prepared-round(record['stop_requested_ros_s']*1e9) >= 2_000_000_000
                    and stop_held-stop_prepared >= 4_000_000_000, 'Stop preparation/hold shorter than frozen 2s/4s')
            speed, drift = 0., 0.
            for state in truth_window(rows, stop_prepared, stop_held):
                p, v, _ = enu(state); speed = max(speed, math.hypot(*v)); drift = max(drift, math.dist(p, record['stop_anchor']))
                require(speed <= .25 and drift <= 1., 'Raw stop speed/drift gate exceeded')
            legs.append(dict(leg=leg, continuous_reference_ticks=12001, max_position_error_m=maxima[0],
                max_axis_velocity_error_m_s=maxima[1], max_yaw_error_rad=maxima[2], stop_max_speed_m_s=speed, stop_max_drift_m=drift))
        output[stack] = legs
    return dict(raw_timeline=timeline, trajectory_and_stop=output)


def native_targets(data, requests):
    def channel(suffix):
        matches = [rows for topic, rows in data.items() if suffix in topic]
        require(len(matches) == 1, 'Ambiguous/missing native channel '+suffix)
        return matches[0]
    def xyz(value):
        return [value[k] for k in ('x', 'y', 'z')]
    homes = {m['time_boot_us']: (row, m) for row, m in data['/ap/wksim/local_state_v1']}
    positions = {m['timestamp']: (row, m) for row, m in channel('/out/vehicle_local_position')}
    offboards = channel('/in/offboard_control_mode')
    reports = {}
    for stack, targets in (('arducopter', data['/ap/cmd_gps_pose']), ('px4', channel('/in/trajectory_setpoint'))):
        count = 0; covered = set(); nonzero = [False]*3; boundary_overlaps = 0
        commands = [(r, e) for r, e in requests[stack] if 'command' in e]
        uid = 1 if stack == 'arducopter' else 2
        accepted = {}
        for event_row, message in data[f'/uav{uid}/prometheus/text_info']:
            event = json.loads(message['message'])
            if event.get('event') == 'command_accepted':
                accepted[event['request_id']] = (event_row, stamp(message))
        for row, target in targets:
            if stack == 'arducopter':
                require(target['type_mask'] in (0x9C0, 0x9F8), 'Unexpected AP native mask/axis combination')
            else:
                require(all(math.isfinite(v) for v in target['position'])
                        and (all(math.isfinite(v) for v in target['velocity']) or all(math.isnan(v) for v in target['velocity']))
                        and all(math.isnan(v) for v in (*target['acceleration'], *target['jerk'], target['yawspeed'])),
                        'PX4 target carries unexpected partial or active acceleration/yaw-rate axes')
            full = target['type_mask'] == 0x9C0 if stack == 'arducopter' else all(math.isfinite(v) for v in (*target['position'], *target['velocity']))
            if not full:
                continue
            # Different DDS topics/publishers have no global reception order.
            # Public payload and acceptance carry ROS issue times; native targets
            # carry a native source sample time, not an emission timestamp.
            prior = [e for _, e in commands if e['command']['agent_cmd'] == 4 and e['command']['move_mode'] == 6
                     and stamp(e['command']) <= row['tick']*1_000_000
                     and e['request_id'] in accepted and accepted[e['request_id']][1] <= row['tick']*1_000_000]
            require(prior, 'Full P+V target has no prior public trajectory command')
            if stack == 'arducopter':
                boot = stamp(target)//1000
                require(stamp(target) % 1000 == 0 and boot in homes and boot*1000 <= row['tick']*1_000_000
                        and abs(homes[boot][0]['wall']-row['wall']) <= 2
                        and target['coordinate_frame'] == 6 and target['header']['frame_id'] == 'map',
                        'AP native map/frame/actual bootstamp differs')
                home = homes[boot][1]
                require(home['home_valid'] and home['position_valid'] and home['velocity_valid'] and home['attitude_valid'],
                        'AP target source lacks valid native state')
                require(all(v == 0 for field in ('linear', 'angular') for v in xyz(target['acceleration_or_force'][field]))
                        and all(v == 0 for v in xyz(target['velocity']['angular'])), 'AP inactive acceleration/yaw-rate payload differs')
                def matches(command):
                    east, north, up = command['position_ref']
                    lat = home['home_latitude_e7'] + int(north/.011131884502145034)
                    mid = (lat+home['home_latitude_e7'])/2e7
                    lon = home['home_longitude_e7'] + int(east/(.011131884502145034*math.cos(math.radians(mid))))
                    lon = (lon+1800000000) % 3600000000-1800000000
                    return (abs(target['latitude']-lat/1e7) < 1e-10 and abs(target['longitude']-lon/1e7) < 1e-10
                            and abs(target['altitude']-f32(up)) <= 1e-6
                            and close_vector(xyz(target['velocity']['linear']), command['velocity_ref'])
                            and abs(angle(target['yaw']-command['yaw_ref'])) <= 1e-6)
            else:
                boot = target['timestamp']
                require(boot in positions and boot*1000 <= row['tick']*1_000_000
                        and abs(positions[boot][0]['wall']-row['wall']) <= 2, 'PX4 target bootstamp lacks fresh actual native source')
                source = positions[boot][1]
                require(all(source[key] for key in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid')),
                        'PX4 target source lacks valid native position/velocity')
                require(all(math.isnan(v) for v in (*target['acceleration'], *target['jerk'], target['yawspeed'])),
                        'PX4 acceleration/jerk/yaw-rate axes became active')
                modes = [m for r, m in offboards if m['timestamp'] == boot and abs(r['wall']-row['wall']) <= 2]
                require(any(m['position'] and m['velocity']
                        and not any(value for key, value in m.items() if key != 'timestamp' and key not in ('position', 'velocity')) for m in modes),
                        'PX4 full P+V OffboardControlMode differs')
                def matches(command):
                    p, v = command['position_ref'], command['velocity_ref']
                    return (close_vector(target['position'], [p[1], p[0], -p[2]])
                            and close_vector(target['velocity'], [v[1], v[0], -v[2]])
                            and abs(angle(target['yaw']-angle(math.pi/2-command['yaw_ref']))) <= 1e-6)
            matched = next((e for e in reversed(prior) if matches(e['command'])), None)
            require(matched is not None, 'Actual full P+V target differs from every prior public command')
            superseding = next(((r, e) for r, e in commands if e['request_id'] > matched['request_id']), None)
            if superseding is not None and accepted[superseding[1]['request_id']][1] < row['tick']*1_000_000:
                # Only the existing 2s middleware/native freshness bound applies
                # to cross-topic overlap. Static endpoint targets remain active
                # until a later command: there is no invented command TTL.
                require(row['wall']-accepted[superseding[1]['request_id']][0]['wall'] <= 2,
                        'Superseded native target observed outside communication freshness bound')
                boundary_overlaps += 1
            covered.add(matched['request_id']); count += 1
            nonzero = [old or abs(v) > .001 for old, v in zip(nonzero, matched['command']['velocity_ref'])]
        expected = {e['request_id'] for _, e in requests[stack] if 'command' in e and e['command']['agent_cmd'] == 4 and e['command']['move_mode'] == 6}
        require(count and covered == expected and all(nonzero), 'Missing native output for a public reference or nonzero velocity axis')
        reports[stack] = dict(full_pv_targets=count, public_references_with_native_output=len(covered),
                              nonzero_velocity_axes=nonzero, target_ack_available=False, acceleration_executed=False,
                              cross_topic_boundary_observations=boundary_overlaps,
                              ordering_claim='ROS-stamped public acceptance precedes target observation; DDS cross-topic receive order is not emission order')
    return reports


def rate_windows(root, result):
    reports = []
    segments = schedule(root/'rate.jsonl', result['scene_epoch'])
    require(len(segments) == 1, 'P+V flight must have one uninterrupted active rate segment')
    synchronized = None
    for row in lines(root/'joint-wire.jsonl'):
        if row['kind'] == 'barrier':
            if synchronized is not None:
                require(row['synchronized'], 'Native synchronization was lost during the rate segment')
            elif row['synchronized']:
                synchronized = row['tick']
    for segment in segments.values():
        anchor = segment['anchor']
        require(anchor['requested_rate'] == .5, 'Frozen half-rate differs')
        require(not anchor['anchor']['transition'] and anchor['anchor']['tick'] == synchronized
                and segment['groups'][-1]['end_tick'] == result['final_authority']['tick'],
                'Rate supervision did not cover synchronization through the final physical boundary')
        require(anchor['steady_after_ns'] == anchor['anchor']['wall_ns']+2_000_000_000, 'Rate stabilization changed')
        samples = segment['groups']; ends = [row['actual_end_ns'] for row in samples]
        first = bisect_left(ends, anchor['steady_after_ns']); checked = {}
        for seconds, budget in ((10, .02), (60, .01)):
            count, worst = 0, 0.
            for begin in range(first, len(samples)):
                end = bisect_left(ends, ends[begin]+seconds*1_000_000_000)
                if end == len(samples):
                    break
                value = measurement(samples[begin], samples[end], .5)
                worst = max(worst, abs(value['relative_error'])); count += 1
                require(abs(value['relative_error']) <= budget, f'A full {seconds}s rate window exceeded original budget')
            checked[str(seconds)] = dict(all_complete_sliding_windows=count, worst_absolute_relative_error=worst, budget=budget)
        reports.append(dict(segment_id=anchor['segment_id'], requested_rate=.5, windows=checked, worst_lateness_ns=segment['worst_ns']))
    boundaries = [r for r in lines(root/'rate.jsonl') if r['kind'] == 'rate_boundary_check']
    require(boundaries and boundaries[-1]['boundary_tick'] == result['final_authority']['tick']
            and boundaries[-1]['actual_check_ns'] <= result['terminal_transition']['issued_monotonic_ns'],
            'Final rate check did not precede the explicit stop')
    require(reports and any(r['windows']['60']['all_complete_sliding_windows'] for r in reports), 'Missing complete 60s rate evidence')
    return reports


def audit(root):
    root = Path(root)
    result = read(root/'result.json')
    identity = retained_identity(root, result)
    raw = decode(root, result)
    tasks, phases, requests = task_evidence(root, result, raw)
    native = native_targets(raw, requests)
    physics = physical(root, result, tasks, phases)
    rates = rate_windows(root, result)
    artifacts = {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob('*'))
                 if p.is_file() and p.name not in ('pv-audit.json', 'audit.json')}
    return dict(status='pass', task_profile=PROFILE, run_id=result['run_id'], scene_epoch=result['scene_epoch'],
                pre_encoding_yaw_float32_narrowings={stack: sum(
                    r['command']['yaw_ref'] != f32(r['command']['yaw_ref']) for r in task['request_envelopes'] if 'command' in r)
                    for stack, task in tasks.items()},
                rejected_unsolicited_bootstrap_acks={stack: [json.loads(m['message']) for _, m in
                    raw[f'/uav{uid}/prometheus/text_info'] if m['message_type'] == 2] for stack, uid in STACKS},
                identity=identity, raw_dds_channels={name:len(rows) for name, rows in raw.items()}, native_targets=native,
                **physics, rate_segments=rates, result_sha256=digest(root/'result.json'), evidence_sha256=artifacts,
                audit_source_sha256=digest(__file__),
                audit_evidence_formatter_sha256=digest(REPO/'Simulator/wksim_runtime/evidence.py'),
                outstanding_checks=[], limitations=[
                    'Bounded experimental full XYZ P+V+yaw only; production and mixed axes remain unadmitted.',
                    'Raw target publication is not native target acknowledgement; setup ACKs are checked separately.',
                    'Acceleration input is retained but native acceleration/yaw-rate axes are inactive.',
                    'Native fence/origin/timeout boundary scenarios and external GCS mode changes are not covered.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        require(not args.output.resolve().is_relative_to(args.directory.resolve()), 'Audit output must be outside raw evidence')
    try:
        report = audit(args.directory)
    except (OSError, ValueError, KeyError, TypeError, ImportError, AssertionError, IndexError, StopIteration, OverflowError) as error:
        report = dict(status='failed', directory=str(args.directory), error=repr(error), audit_source_sha256=digest(__file__),
                      outstanding_checks=['Audit terminated at the reported failure; downstream checks are not accepted.'])
    raw = json.dumps(report, indent=2, allow_nan=False)+'\n'
    if args.output:
        args.output.write_text(raw)
    print(raw, end='')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
