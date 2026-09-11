"""Independent raw audit of the frozen bounded XY-velocity/Z-position flight.

Read-only evidence inspection. Build, admission, target publication, native setup
ACK, native mixed-submode entry, and physical completion are separate claims.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from audit_joint_flight import audit_timeline, digest, lines, require
from audit_pv_trajectory import (read, stamp, angle, f32, wire_command, wire_request,
    rejected_bootstrap_ack, enu, close_vector, truth_window, decode, rate_windows)
from Simulator.wksim_runtime.evidence import json_value

PROFILE = 'xy_velocity_z_position_yaw_v1'
PV_PROFILE = 'full_xyz_pv_yaw_v1'
STACKS = (('arducopter', 1), ('px4', 2))
AP_SHA = '1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c'
CONTROL_SHA = 'd9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e'
PV_CONTROL_SHA = 'a6a17b42f92cf6df4b92fe36b6e1e65f6e4e42f684daac4113091591a1802346'
PV_MESSAGE_SHA = '29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219'
PV_SHA = 'e05e5c9d0b2b576d2cf1751b01557219d6da36998b22ded396ca33d7f5c4db62'
BASE_SHA = 'f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a'
MOVING = ('world_step', 'world_reverse', 'world_one_axis', 'world_reentry', 'body_step')
SEGMENTS = ('world_step', 'world_reverse', 'world_one_axis', 'world_zero',
            'world_reentry', 'world_absolute_stop', 'body_heading', 'body_step', 'body_zero', 'body_absolute_stop')


def completion_clock_ok(body, event_ns, observed_tick, *, setup):
    # Completion of ARM/mode/takeoff is not the receipt of its input message.
    # Task.send uses 40s for COMMAND_CONTROL and 10s for simple setup; MOVE
    # acceptance/rejection happens inside the original -0.5..2s input age gate.
    limit = (40 if body['cmd'] == 3 else 10) if setup else 2
    delta = event_ns-stamp(body)
    return -.5e9 <= delta <= limit*1e9 and event_ns <= observed_tick*1_000_000


def identical_status_duplicate(event, event_row, data, stack):
    if (stack != 'px4' or event.get('event') != 'native_input_rejected'
            or event.get('reason') != 'duplicate_source' or event.get('source') != 'status'
            or type(event.get('source_stamp')) is not int):
        return False
    channels = [rows for topic, rows in data.items() if '/out/vehicle_status' in topic]
    if len(channels) != 1:
        return False
    samples = [(row, message) for row, message in channels[0]
               if message['timestamp'] == event['source_stamp'] and abs(row['wall']-event_row['wall']) <= 2]
    return (len(samples) >= 2 and event['source_stamp'] > 0
            and event['source_stamp']*1000 <= event_row['tick']*1_000_000
            and all(message['system_id'] == 22 and normalized(message) == normalized(samples[0][1])
                    for _, message in samples))


def after_completed_window(matched_request, expected_request, accepted_ns, window_end_ns, observed_tick):
    return (matched_request > expected_request and accepted_ns >= window_end_ns
            and observed_tick*1_000_000 >= accepted_ns)


def validate_build(ap, verified):
    keys = {'schema_version', 'status', 'profile', 'candidate_root', 'baseline_root', 'baseline_manifest_sha256',
            'source_manifest_sha256', 'patch_sha256', 'artifacts', 'source_unchanged_during_build',
            'fixed_pv_baseline_unchanged', 'production_admitted', 'flown'}
    require(set(ap) == keys and type(ap['schema_version']) is int and ap['schema_version'] == 1
            and ap['status'] == 'built-not-admitted' and ap['profile'] == PROFILE
            and ap['candidate_root'] == '/root/wksim-ap-mixed-fhuf05l9'
            and ap['baseline_root'] == '/root/wksim-ap-pv-vn04950x' and ap['baseline_manifest_sha256'] == PV_SHA
            and ap['source_unchanged_during_build'] is True and ap['fixed_pv_baseline_unchanged'] is True
            and ap['production_admitted'] is False and ap['flown'] is False,
            'Frozen mixed build schema/identity differs')
    require(verified['candidate'] == ap and verified['status'] == 'verified-built-not-admitted'
            and verified['production_admitted'] is False and verified['flown'] is False
            and verified['source_files'] == 24593 and verified['source_repositories'] == 22
            and verified['binary'] == dict(path=ap['candidate_root']+'/build/sitl/bin/arducopter',
                sha256=ap['artifacts']['build/sitl/bin/arducopter']), 'Mixed verification does not bind native binary')
    pv = verified['baseline_verification']
    require(pv['manifest_sha256'] == PV_SHA and pv['baseline_manifest_sha256'] == BASE_SHA
            and pv['status'] == 'verified-built-not-admitted' and pv['fixed_baseline_unchanged'] is True
            and pv['current_source_matches_prebuild_snapshot'] is True and pv['production_admitted'] is False
            and pv['flown'] is False, 'Mixed -> PV -> fixed AP chain differs')


def control_profiles(result, *, require_pv=False):
    """Read actual launch arguments; a historical single flag is not dual-flag evidence."""
    profiles = {}
    allowed = {'arducopter_pv_profile': PV_PROFILE, 'arducopter_mixed_profile': PROFILE}
    for stack, _ in STACKS:
        argv = result['children'][stack+'-control']['argv']
        for index, value in enumerate(argv):
            key, separator, selected = value.partition(':=')
            if key not in allowed:
                continue
            require(stack == 'arducopter' and index > 0 and argv[index-1] == '-p'
                    and separator and selected == allowed[key] and key not in profiles,
                    'Control profile argument differs or is duplicated')
            profiles[key] = selected
    require(profiles.get('arducopter_mixed_profile') == PROFILE
            and (not require_pv or profiles.get('arducopter_pv_profile') == PV_PROFILE),
            'Required mixed/P+V control profile was not enabled')
    return profiles


def retained_identity(root, result, *, task_profile=PROFILE):
    from audit_pv_trajectory import candidate_initialization
    message_identity = candidate_initialization(root, result)
    require(task_profile in (PROFILE, PV_PROFILE), 'Unsupported task for mixed firmware audit')
    require(result['status'] == 'pass' and result['flight_completed'] and result['source_unchanged']
            and result['control_shutdown_clean'] and not result['cleanup_errors'], 'Candidate run/cleanup did not pass')
    require(result['task_profile'] == task_profile and result['unowned_ap_before'] == result['unowned_ap_after'],
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
    mandatory = {'tools/run_joint_flight.py', 'tools/pv_trajectory_task.py', 'tools/mixed_control_task.py', 'tools/ap_mixed_candidate.py',
                 'tools/ap_pv_candidate.py', 'tools/prepare_ap_mixed_candidate.py',
                 'tools/verify_ap_pv_candidate.py', 'Simulator/wksim_runtime/task.py',
                 'Simulator/wksim_runtime/joint_rate.py', 'docs/2026-09-09-mixed-flight-plan.md', 'patches/arducopter/0005-dds-mixed-xy-velocity-z-position.patch'}
    if task_profile == PV_PROFILE:
        mandatory |= {'docs/2026-09-09-pv-flight-plan.md', 'docs/2026-09-09-final-combo-pv-plan.md'}
    require(mandatory <= sources.keys(), 'Missing executed source identity')
    expected_names = {'source__'+name.replace('/', '__')+'.txt' for name in sources}
    require({p.name for p in root.glob('source__*')} == expected_names, 'Missing/extra retained source file')
    for name, expected in sources.items():
        require(digest(root/('source__'+name.replace('/', '__')+'.txt')) == expected, 'Retained source changed: '+name)
    admission = read(root/'experimental-admission.json')
    require(admission == result['mixed_admission'] and admission['ok'] and admission['experimental']
            and not admission['production_admitted'] and not admission['flown']
            and admission['children_created'] == 0 and not admission['reasons'] and admission['task_profile'] == task_profile
            and 'pv_admission' not in result,
            'Experimental admission identity/scope differs')
    capability = (dict(profile=PV_PROFILE, position_axes='xyz', velocity_axes='xyz', yaw=True,
            acceleration=False, yaw_rate=False, mixed_axes=False, arducopter_type_mask=2496)
        if task_profile == PV_PROFILE else dict(profile=PROFILE, position_axes='z', velocity_axes='xy', yaw=True,
            yaw_rate=False, acceleration=False, terrain=False, arducopter_type_mask=2531,
            native_submode=7, vertical_velocity_avoidance=False))
    require(admission['capability'] == capability, 'Mixed firmware task capability scope changed')
    selected_control_sha = admission['control_manifest_sha256']
    allowed_control_sha = ({PV_CONTROL_SHA} if task_profile == PV_PROFILE
                           else {CONTROL_SHA, PV_CONTROL_SHA})
    require(admission['manifest_sha256'] == AP_SHA and selected_control_sha in allowed_control_sha,
            'Frozen mixed build/control selection changed')
    if selected_control_sha == PV_CONTROL_SHA:
        require(message_identity.get('requested') is True
                and result['manifest_sha256'].get('message') == PV_MESSAGE_SHA,
                'Frozen current message candidate selection changed')
    else:
        require(message_identity == dict(requested=False, legacy=True),
                'Historical mixed control cannot use a current message candidate')
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
    validate_build(ap, verified)
    require(verified == admission['identities']['ap_mixed'] and verified['manifest_sha256'] == AP_SHA
            and verified['source_manifest_sha256'] == ap['source_manifest_sha256'],
            'Mixed full source admission is missing or bound to another build')
    require(digest(root/'mixed-source.json') == ap['source_manifest_sha256']
            and digest(root/'baseline-pv-build.json') == PV_SHA, 'Retained native source/PV baseline seal differs')
    prepared = read(root/'mixed-source.json')
    require(prepared['candidate_root'] == ap['candidate_root'] and prepared['profile'] == PROFILE
            and prepared['patch_sha256'] == ap['patch_sha256']
            and sources['patches/arducopter/0005-dds-mixed-xy-velocity-z-position.patch'] == ap['patch_sha256'],
            'Native patch/prebuild source binding differs')
    native_sources = {p.relative_to(root/'native-source').as_posix(): digest(p)
                      for p in (root/'native-source').rglob('*') if p.is_file()}
    expected_native_sources = {'libraries/AP_DDS/AP_DDS_ExternalControl.cpp',
        'libraries/AP_ExternalControl/AP_ExternalControl.h', 'ArduCopter/AP_ExternalControl_Copter.h',
        'ArduCopter/AP_ExternalControl_Copter.cpp', 'ArduCopter/mode.h', 'ArduCopter/mode_guided.cpp',
        'ArduCopter/GCS_MAVLink_Copter.cpp', 'ArduCopter/Log.cpp'}
    require(result['native_source_root'] == ap['candidate_root']+'/src'
            and native_sources == result['native_source_sha256'] and set(native_sources) == expected_native_sources
            and all(expected == prepared['source']['files'][name]['sha256'] for name, expected in native_sources.items()),
            'Retained native source differs from prebuild seal')
    baseline = admission['identities']['baseline']
    profiles = read(root/'source__Simulator__wksim_runtime__joint-profiles.json.txt')['profiles']
    pinned = next(p for p in profiles if p['id'] == 'joint_quad_dds_v1')
    require(admission['baseline_profile'] == pinned and baseline['manifests'] == pinned['manifests']
            and verified['baseline_verification']['baseline_manifest_sha256'] == pinned['manifests']['ap']['sha256']
            and control['root'] != pinned['control_workspace'], 'Fixed baseline/candidate separation differs')
    require(result['model_build'] == baseline['model'], 'Physical model differs from admission')
    expected_firmware = {'arducopter': verified['binary'], 'px4': baseline['px4']}
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
                control_profiles=control_profiles(result, require_pv=task_profile == PV_PROFILE),
                loaded_maps_verified=['running', 'completed'], message_candidate=message_identity)


def normalized(value):
    return json.dumps(json_value(value), sort_keys=True, allow_nan=False)


def exact_request(actual, retained):
    """CDR narrowing is explicit; JSON typing distinguishes bool/int/float too."""
    return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(wire_request(retained), sort_keys=True, allow_nan=False)


def quaternion_yaw(values):
    require(len(values) == 4 and all(math.isfinite(v) for v in values), 'Invalid capture quaternion')
    norm = math.hypot(*values)
    require(norm >= 1e-9, 'Zero capture quaternion')
    w, x, y, z = (v/norm for v in values)
    return math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))


def body_reference(command, event, states):
    """Compute BODY reference from exact raw command and actual public quaternion."""
    require(command['agent_cmd'] == 4 and command['move_mode'] == 5 and not command['yaw_rate_mode'],
            'Capture belongs to another command kind')
    require(event['command_id'] == command['command_id'], 'BODY capture command differs')
    matching = [m for _, m in states if stamp(m['state']) == event['source_boot_ns']
                and m['last_request_id'] == event['request_id'] and m['source_received_valid']
                and 0 <= m['published_monotonic_s']-m['source_received_monotonic_s'] <= 2
                and m['state']['position'] == event['source_position']
                and [m['state']['attitude_q'][k] for k in ('w', 'x', 'y', 'z')] == event['source_quaternion_wxyz']]
    require(matching, 'BODY capture lacks the exact fresh public source state')
    yaw = quaternion_yaw(event['source_quaternion_wxyz'])
    require(abs(angle(yaw-event['source_yaw'])) <= 1e-12, 'Capture yaw differs from actual quaternion')
    x, y = command['velocity_ref'][:2]
    velocity = [x*math.cos(yaw)-y*math.sin(yaw), x*math.sin(yaw)+y*math.cos(yaw), 0.]
    position = [0., 0., event['source_position'][2]+command['position_ref'][2]]
    heading = yaw+command['yaw_ref']
    require(close_vector(event['reference_position'], position, 1e-12)
            and close_vector(event['reference_velocity'], velocity, 1e-12)
            and abs(event['reference_yaw']-heading) <= 1e-12, 'BODY reference was not captured from raw input')
    held = abs(x) <= .001 and abs(y) <= .001
    expected_p = [*event['source_position'][:2], position[2]] if held else [None, None, position[2]]
    require(event['shaped_position'] == expected_p
            and event['shaped_velocity'] == ([None]*3 if held else velocity),
            'BODY shaped axes/sentinel or new zero anchor differs')
    return dict(velocity=velocity[:2], altitude=position[2], yaw=heading, body_capture=event)


def command_contract(commands, stack):
    names = ['waypoint', *SEGMENTS, 'land']
    if stack == 'arducopter':
        names.insert(names.index('world_reentry'), 'invalid_world_yaw_rate')
    require(len(commands) == len(names), 'Unexpected mixed command count')
    result = dict(zip(names, commands))
    world = {'world_step': ([.8, .4], 4.), 'world_reverse': ([-.4, .6], 3.),
             'world_one_axis': ([0., .6], 3.), 'world_zero': ([0., 0.], 3.), 'world_reentry': ([.4, -.3], 3.6),
             'invalid_world_yaw_rate': ([1., 0.], 3.), 'body_step': ([.8, .4], 1.), 'body_zero': ([0., 0.], 0.)}
    for index, (name, env) in enumerate(result.items(), 1):
        c = env['command']
        require(c['command_id'] == index and c['acceleration_ref'] == [0.]*3 and c['att_ref'] == [0.]*4
                and c['latitude'] == c['longitude'] == c['altitude'] == 0., 'Unexpected command identity/unused fields')
        level = 1 if name.endswith('absolute_stop') else 2 if name in ('body_heading', 'land') else 0
        require(c['control_level'] == level, 'Frozen command priority differs: '+name)
        if name in world:
            velocity, altitude = world[name]
            invalid = name == 'invalid_world_yaw_rate'
            require(c['agent_cmd'] == 4 and c['move_mode'] == (5 if name.startswith('body_') else 1)
                    and c['position_ref'] == [0., 0., f32(altitude)]
                    and c['velocity_ref'] == [*map(f32, velocity), 0.]
                    and c['yaw_ref'] == f32(.3 if name == 'body_step' else 0.)
                    and c['yaw_rate_mode'] is invalid and c['yaw_rate_ref'] == (.5 if invalid else 0.),
                    'Frozen mixed command differs: '+name)
        else:
            require(c['agent_cmd'] == (3 if name == 'land' else 2 if name.endswith('absolute_stop') else 4)
                    and c['move_mode'] == 0 and c['velocity_ref'] == [0.]*3 and not c['yaw_rate_mode']
                    and c['yaw_rate_ref'] == 0. and c['yaw_ref'] == f32(.6 if name == 'body_heading' else 0.),
                    'Frozen position/stop/land command differs: '+name)
            if name != 'body_heading':
                require(c['position_ref'] == ([2., 3., 3.] if name == 'waypoint' else [0.]*3),
                        'Unexpected position payload: '+name)
    return result


def task_evidence(root, result, data, *, recorder_name='wksim_joint_flight_clock', task_root=None):
    task_root = root if task_root is None else task_root
    tasks, phases, requests, references = {}, {}, {}, {}
    for stack, uid in STACKS:
        report = read(task_root/stack/'result.json')
        require(report == result['tasks'][stack] and report['status'] == 'pass' and report['run_id'] == result['run_id']
                and report['scene_epoch'] == result['scene_epoch'] and report['uav_id'] == uid and report['use_sim_time']
                and report['task_profile'] == PROFILE, 'Task identity differs')
        task = tasks[stack] = report['task']
        require(task['mixed_profile'] == PROFILE and not task['control_restarts'], 'Missing/restarted mixed task')
        graph = task['mixed_request_graph']
        require(set(graph) == {'setup', 'command'}, 'Missing passive subscriber proof')
        for endpoints in graph.values():
            require(len(endpoints) == 2 and {e['node_name'] for e in endpoints} == {
                'wksim_joint_'+stack+'_control', recorder_name}
                and len({e['endpoint_gid'] for e in endpoints}) == 2
                and all(e['node_namespace'] == '/' and re.fullmatch('[0-9a-f]+', e['endpoint_gid'])
                        and int(e['endpoint_gid'], 16) != 0 for e in endpoints), 'Unexpected subscriber graph')
        phase = phases[stack] = {p['phase']: p for p in report['phases']}
        require(len(phase) == len(report['phases']), 'Repeated phase')
        times = [p['ros_time_ns'] for p in report['phases']]
        require(times == sorted(times) and all(type(t) is int and 0 < t <= result['final_authority']['tick']*1_000_000
                and t % 1_000_000 == 0 for t in times), 'Task phase is off authoritative grid')
        base = f'/uav{uid}/prometheus/'
        raw = sorted(data[base+'v2/setup']+data[base+'v2/command'], key=lambda item: item[1]['request_id'])
        requests[stack] = raw
        require(len(raw) == len(task['sent']) == len(task['request_envelopes'])
                and all(exact_request(m, retained) for (_, m), retained in zip(raw, task['request_envelopes'])),
                'Exact raw public request stream differs from retained task')
        setups = [(i, e['setup']) for i, (_, e) in enumerate(raw) if 'setup' in e]
        require([i for i, _ in setups] == [0, 1, 2, len(raw)-1] and [m['cmd'] for _, m in setups] == [1, 0, 3, 1]
                and setups[0][1]['px4_mode'] == setups[-1][1]['px4_mode'] == 'AUTO.LOITER'
                and setups[1][1]['arming'] is True and setups[2][1]['control_state'] == 'COMMAND_CONTROL',
                'Unexpected public setup sequence')
        named = command_contract([e for _, e in raw if 'command' in e], stack)
        invalid_id = named['invalid_world_yaw_rate']['request_id'] if stack == 'arducopter' else None
        events, event_times = [], {}
        first_ns = min(stamp(e.get('command', e.get('setup'))) for _, e in raw)
        for row, message in data[base+'text_info']:
            e = json.loads(message['message'])
            bootstrap = rejected_bootstrap_ack(e, stamp(message), first_ns)
            duplicate = identical_status_duplicate(e, row, data, stack)
            expected_rejection = (invalid_id is not None and e.get('event') == 'command_rejected'
                and e.get('request_id') == invalid_id and e.get('command_id') == named['invalid_world_yaw_rate']['command']['command_id']
                and e.get('reason') == 'arducopter_mixed_requires_yaw_angle')
            require(message['message_type'] < 2 or message['message_type'] == 2 and (bootstrap or expected_rejection or duplicate),
                    'Unexpected raw public ERROR/FATAL: '+str(e))
            if e.get('run_id') != result['run_id'] or e.get('control_epoch') != task['control_epoch']:
                require(e.get('request_id', 0) == 0 and not expected_rejection, 'Foreign request event')
                continue
            require((e.get('event') not in ('setup_rejected', 'command_rejected', 'control_revoked', 'native_input_rejected')
                    or expected_rejection or bootstrap or duplicate) and not e.get('error')
                    and not (e.get('event') == 'native_ack' and not e.get('accepted')), 'Unexpected rejection/revocation/ACK failure')
            require(e['event_id'] not in event_times, 'Duplicate raw event identity')
            events.append(e); event_times[e['event_id']] = (row, stamp(message))
        require(all(e in events for e in task['events']), 'Task event lacks raw CDR corroboration')
        for index, ((row, envelope), sent) in enumerate(zip(raw, task['sent']), 1):
            require(envelope['version'] == 1 and envelope['run_id'] == result['run_id']
                    and envelope['control_epoch'] == task['control_epoch'] and envelope['request_id'] == index,
                    'Public request identity/replay differs')
            setup = 'setup' in envelope
            body = envelope['setup' if setup else 'command']
            require(task['request_envelopes'][index-1]['setup' if setup else 'command'] == sent
                    and body == (sent if setup else wire_command(sent)) and body['header']['frame_id'] == 'map'
                    and 0 < stamp(body) <= row['tick']*1_000_000, 'Public payload/frame/clock differs')
            accepted = [e for e in events if e.get('request_id') == index
                        and e.get('event') == ('setup_completed' if setup else 'command_accepted')]
            rejected = [e for e in events if e.get('request_id') == index and e.get('event') == 'command_rejected']
            if index == invalid_id:
                require(not accepted and len(rejected) == 1, 'Invalid mixed yaw rate was not rejected before acceptance')
            else:
                require(len(accepted) == 1 and not rejected and (setup or accepted[0]['command_id'] == body['command_id']),
                        'Public acceptance missing/duplicated')
            completion = rejected[0] if index == invalid_id else accepted[0]
            completion_row, completion_ns = event_times[completion['event_id']]
            require(completion_clock_ok(body, completion_ns, completion_row['tick'], setup=setup),
                    'Request completion source clock differs')
            acks = [e for e in events if e.get('request_id') == index and e.get('event') == 'native_ack']
            if setup:
                require(acks and all(e['accepted'] for e in acks), 'Setup lacks native ACK')
            elif body['agent_cmd'] != 3:
                require(not acks, 'Streamed target/rejected command incorrectly claims native ACK')
        states = data[base+'v2/state']
        require(all(b['sequence'] == a['sequence']+1 for (_, a), (_, b) in zip(states, states[1:])),
                'Public state gap prevents exact first-step capture audit')
        for _, m in states:
            require(m['version'] == 1 and m['run_id'] == result['run_id'] and m['control_epoch'] == task['control_epoch']
                    and m['state']['uav_id'] == m['control']['uav_id'] == uid and m['source_clock'] == 'fc_boot',
                    'Public state crossed session/vehicle/source clock')
        fresh_states = {normalized(m['state']) for _, m in states if m['source_received_valid']
                        and 0 <= m['published_monotonic_s']-m['source_received_monotonic_s'] <= 2}
        for p in report['phases']:
            if p['state'] is not None:
                require(normalized(p['state']) in fresh_states and 0 <= p['ros_time_ns']-stamp(p['state']) <= 2_000_000_000,
                        'Phase state lacks fresh raw public source: '+p['phase'])
        final = task['final']['state']
        require(normalized(final) in fresh_states and final['connected'] and final['odom_valid']
                and not final['armed'] and abs(final['position'][2]) < .3, 'Public final ground completion is absent')
        captures = [e for e in events if e.get('event') == 'mixed_body_reference_captured']
        require(len(captures) == 2 and {e['request_id'] for e in captures} == {named[n]['request_id'] for n in ('body_step', 'body_zero')},
                'BODY was not captured exactly once per command')
        refs = references[stack] = {}
        for name, env in named.items():
            c = env['command']
            first = next((m for _, m in states if m['last_request_id'] == env['request_id']), None)
            require(first is not None, 'Missing actual first processor public state: '+name)
            if name in ('body_step', 'body_zero'):
                event = next(e for e in captures if e['request_id'] == env['request_id'])
                require(event['source_boot_ns'] == stamp(first['state']) and first['state']['position'] == event['source_position'],
                        'BODY capture does not match first processor state')
                acceptance = next(e for e in events if e.get('event') == 'command_accepted' and e.get('request_id') == env['request_id'])
                require(event['source_boot_ns'] <= event_times[event['event_id']][1]
                        and event_times[acceptance['event_id']][1] <= event_times[event['event_id']][1],
                        'BODY capture source/acceptance clock differs')
                ref = body_reference(c, event, states)
            elif c['agent_cmd'] == 4 and c['move_mode'] == 1:
                ref = dict(velocity=c['velocity_ref'][:2], altitude=c['position_ref'][2], yaw=c['yaw_ref'])
            elif c['agent_cmd'] == 4:
                ref = dict(position=c['position_ref'], yaw=.6 if name == 'body_heading' else c['yaw_ref'])
            elif name.endswith('absolute_stop'):
                previous = 'world_reentry' if name.startswith('world') else 'body_zero'
                source = phase[previous+'_completed']['state']
                ref = dict(altitude=source['position'][2], yaw=source['attitude'][2])
            else:
                continue
            refs[name] = dict(reference=ref, envelope=env, first_state=first['state'])
        refs['world_zero']['native_anchor'] = [refs['world_one_axis']['first_state']['position'][0],
            refs['world_zero']['first_state']['position'][1], refs['world_zero']['reference']['altitude']]
        require(named['body_heading']['command']['position_ref'] == phase['world_absolute_stop_completed']['state']['position'],
                'BODY heading did not use actual stopped position')
        names = list(SEGMENTS)
        if invalid_id is not None:
            names.insert(names.index('world_reentry'), 'invalid_world_yaw_rate')
        require([s['name'] for s in task['mixed_segments']] == names, 'Frozen mixed segment sequence differs')
        for segment in task['mixed_segments']:
            name = segment['name']; env = named[name]
            expected = refs['world_zero']['reference'] if name == 'invalid_world_yaw_rate' else refs[name]['reference']
            require(segment['status'] == 'pass' and segment['request_id'] == env['request_id']
                    and segment['command_id'] == env['command']['command_id'] and segment['reference'] == expected,
                    'Mixed descriptor is not derived from exact raw command/capture: '+name)
            require(segment['start_ns'] == phase[name+'_started']['ros_time_ns']
                    and segment['end_ns'] == phase[name+'_completed']['ros_time_ns']
                    and segment['start_state'] == phase[name+'_started']['state']
                    and segment['end_state'] == phase[name+'_completed']['state'], 'Segment boundary/phase differs')
            if 'anchor' in segment:
                previous = {'world_one_axis':'world_reverse', 'world_zero':'world_one_axis',
                            'invalid_world_yaw_rate':'world_one_axis', 'world_absolute_stop':'world_reentry',
                            'body_absolute_stop':'body_zero'}.get(name)
                anchor = (refs['body_zero']['reference']['body_capture']['shaped_position'] if name == 'body_zero'
                          else phase[previous+'_completed']['state']['position'])
                require(segment['anchor'] == anchor, 'Physical hold descriptor uses fabricated/old anchor: '+name)
        stops = data[base+'stop_control_state']
        require([m['data'] for _, m in stops] == [True, False, True, False], 'Exact four stop Bool transitions differ')
        transitions = [env['command'] for env in named.values() if env['command']['control_level'] in (1, 2)]
        require(len(transitions) == 4, 'Unexpected priority transition command')
        for (row, m), c in zip(stops, transitions):
            require(stamp(c) <= row['tick']*1_000_000 and m['data'] == (c['control_level'] == 1),
                    'Stop Bool predates/differs from public command')
    require(tasks['arducopter']['control_epoch'] != tasks['px4']['control_epoch'], 'Control epochs not distinct')
    return tasks, phases, requests, references


def physical_metrics(state, name, reference, anchor=None):
    p, v, yaw = enu(state)
    metrics = dict(yaw_error_rad=abs(angle(yaw-reference['yaw'])))
    require(metrics['yaw_error_rad'] <= .15, '1ms yaw gate exceeded: '+name)
    if name == 'body_heading':
        metrics.update(position_error_m=math.dist(p, reference['position']), speed_m_s=math.hypot(*v))
        require(metrics['position_error_m'] <= .5 and metrics['speed_m_s'] <= .5, '1ms heading hold gate exceeded')
    elif name.endswith('absolute_stop'):
        metrics.update(speed_m_s=math.hypot(*v), drift_m=math.dist(p, anchor))
        require(metrics['speed_m_s'] <= .25 and metrics['drift_m'] <= 1., '1ms absolute stop gate exceeded: '+name)
    else:
        metrics.update(altitude_error_m=abs(p[2]-reference['altitude']),
                       xy_velocity_error_m_s=max(abs(a-b) for a, b in zip(v[:2], reference['velocity'])))
        require(metrics['altitude_error_m'] <= .5 and metrics['xy_velocity_error_m_s'] <= .3,
                '1ms mixed tracking gate exceeded: '+name)
        if name == 'world_one_axis':
            metrics.update(x_speed_m_s=abs(v[0]), x_drift_m=abs(p[0]-anchor[0]))
            require(metrics['x_speed_m_s'] <= .25 and metrics['x_drift_m'] <= 1., '1ms one-axis gate exceeded')
        if name in ('world_zero', 'body_zero', 'invalid_world_yaw_rate'):
            metrics.update(speed_m_s=math.hypot(*v), drift_m=math.dist(p, anchor))
            require(metrics['speed_m_s'] <= .25 and metrics['drift_m'] <= 1., '1ms zero/no-effect hold gate exceeded: '+name)
    return metrics


def physical(root, result, tasks, phases, *, wire_name='joint-wire.jsonl'):
    timeline, _ = audit_timeline(root, result, phases, wire_name=wire_name)
    output = {}
    for stack, _ in STACKS:
        rows = [row['state'] for row in lines(root/(stack+'-truth.jsonl'))]
        phase = phases[stack]
        for start, end, seconds in (('takeoff_reached', 'hold_completed', 5), ('waypoint_reached', 'waypoint_completed', 2)):
            lo, hi = phase[start]['ros_time_ns'], phase[end]['ros_time_ns']
            require(hi-lo >= seconds*1_000_000_000, 'Baseline dwell shortened')
            for state in truth_window(rows, lo, hi):
                p, v, yaw = enu(state)
                if start == 'waypoint_reached':
                    require(math.dist(p, [2, 3, 3]) <= .5 and math.hypot(*v) <= .5 and abs(yaw) <= .15,
                            'Baseline raw position/speed/yaw gate exceeded')
                else:
                    require(abs(p[2]-3) <= .6 and max(abs(x) for x in state[9:11]) <= .35, 'Raw initial hold gate exceeded')
        output[stack] = []
        for segment in tasks[stack]['mixed_segments']:
            name = segment['name']; lo, hi = segment['start_ns'], segment['end_ns']
            seconds = 3 if name in MOVING and name != 'world_one_axis' else 2 if name in ('body_heading', 'invalid_world_yaw_rate') else 4
            require(hi-lo >= seconds*1_000_000_000, 'Frozen segment dwell shortened: '+name)
            if name in ('world_one_axis', 'world_zero', 'body_zero', 'world_absolute_stop', 'body_absolute_stop'):
                require(phase[name+'_prepared']['ros_time_ns']-phase[name+'_accepted']['ros_time_ns'] >= 2_000_000_000
                        and lo >= phase[name+'_prepared']['ros_time_ns'], 'Frozen preparation shortened: '+name)
            elif name != 'invalid_world_yaw_rate':
                require(0 <= phase[name+'_ready']['ros_time_ns']-phase[name+'_accepted']['ros_time_ns'] <= 20_000_000_000,
                        'Frozen readiness budget exceeded: '+name)
                if name in MOVING:
                    require(phase[name+'_prepared']['ros_time_ns']-phase[name+'_ready']['ros_time_ns'] >= 2_000_000_000
                            and lo >= phase[name+'_prepared']['ros_time_ns'], 'Moving settling preparation shortened: '+name)
            else:
                require(lo >= phase['invalid_world_yaw_rate_rejected']['ros_time_ns'], 'No-effect hold predates rejection')
            maxima = {}
            if name in ('world_zero', 'body_zero', 'world_absolute_stop', 'body_absolute_stop', 'body_heading'):
                settled = segment['hold_settling']
                require(settled['wall_limit_s'] == 12. and settled['stable_minimum_s'] == 1.5
                        and 0 <= settled['ready_monotonic_s']-settled['started_monotonic_s'] <= 12.
                        and settled['ready_s']-settled['stable_from_s'] >= 1.5
                        and round(settled['ready_s']*1e9) == phase[name+'_stable']['ros_time_ns'] == lo
                        and round(settled['stable_from_s']*1e9) >= phase[name+('_ready' if name == 'body_heading' else '_prepared')]['ros_time_ns'],
                        'Stop preparation lacked bounded continuous stability: '+name)
                for state in truth_window(rows, round(settled['stable_from_s']*1e9), round(settled['ready_s']*1e9)):
                    physical_metrics(state, name, segment['reference'], segment.get('anchor'))
            window = truth_window(rows, lo, hi)
            for state in window:
                for key, value in physical_metrics(state, name, segment['reference'], segment.get('anchor')).items():
                    maxima[key] = max(maxima.get(key, 0.), value)
            output[stack].append(dict(name=name, start_ns=lo, end_ns=hi, physical_ticks=len(window), maxima=maxima))
    return dict(raw_timeline=timeline, continuous_mixed_windows=output)


def native_expected(name, record, source):
    """Independent shaping arithmetic; never instantiate the executed shaper."""
    reference = record['reference']
    if name in MOVING:
        velocity = list(reference['velocity'])
        if name == 'world_one_axis':
            error = source['position'][0]-record['first_state']['position'][0]
            velocity[0] = -f32(1.8)*error if abs(error) >= f32(.04) else 0.
        return [None, None, reference['altitude']], [*velocity, 0.], f32(reference['yaw'])
    if name == 'world_zero':
        return record['native_anchor'], [None]*3, f32(reference['yaw'])
    if name == 'body_zero':
        return reference['body_capture']['shaped_position'], [None]*3, f32(reference['yaw'])
    if name.endswith('absolute_stop'):
        state = record['first_state']
        return state['position'], [None]*3, f32(quaternion_yaw([state['attitude_q'][k] for k in ('w', 'x', 'y', 'z')]))
    return reference['position'], [None]*3, f32(reference['yaw'])


def native_matches(stack, target, expected, home=None):
    p, v, yaw = expected
    mixed = p[:2] == [None, None]
    if stack == 'arducopter':
        if target['type_mask'] != (0x9E3 if mixed else 0x9F8):
            return False
        if mixed:
            xy = target['latitude'] == target['longitude'] == 0.
        else:
            latitude = home['home_latitude_e7']+int(p[1]/.011131884502145034)
            midpoint = (latitude+home['home_latitude_e7'])/2e7
            longitude = home['home_longitude_e7']+int(p[0]/(.011131884502145034*math.cos(math.radians(midpoint))))
            longitude = (longitude+1800000000) % 3600000000-1800000000
            xy = target['latitude'] == latitude/1e7 and target['longitude'] == longitude/1e7
        velocity = [target['velocity']['linear'][k] for k in ('x', 'y', 'z')]
        return (xy and abs(target['altitude']-p[2]) <= 1e-6
                and close_vector(velocity, v if mixed else [0.]*3)
                and abs(angle(target['yaw']-yaw)) <= 1e-6)
    def ned(values):
        return [values[1], values[0], None if values[2] is None else -values[2]]
    def axes(actual, wanted):
        return len(actual) == 3 and all(math.isnan(a) if b is None else math.isfinite(a) and abs(a-f32(b)) <= 1e-6
                                      for a, b in zip(actual, wanted))
    return (axes(target['position'], ned(p)) and axes(target['velocity'], ned(v))
            and abs(angle(target['yaw']-f32(angle(math.pi/2-yaw)))) <= 1e-6)


def native_targets(data, requests, references, tasks):
    def channel(suffix):
        selected = [rows for topic, rows in data.items() if suffix in topic]
        require(len(selected) == 1, 'Missing/ambiguous native channel: '+suffix)
        return selected[0]
    homes = {m['time_boot_us']: (r, m) for r, m in data['/ap/wksim/local_state_v1']}
    positions = {m['timestamp']: (r, m) for r, m in channel('/out/vehicle_local_position')}
    offboard = channel('/in/offboard_control_mode')
    output = {}
    for stack, uid in STACKS:
        targets = data['/ap/cmd_gps_pose'] if stack == 'arducopter' else channel('/in/trajectory_setpoint')
        public = data[f'/uav{uid}/prometheus/v2/state']
        states = {}
        for r, m in public:
            if m['source_received_valid'] and 0 <= m['published_monotonic_s']-m['source_received_monotonic_s'] <= 2:
                states.setdefault(stamp(m['state']), []).append((r, m))
        accepted = {}
        for r, m in data[f'/uav{uid}/prometheus/text_info']:
            e = json.loads(m['message'])
            if e.get('event') == 'command_accepted':
                accepted[e['request_id']] = (r, stamp(m))
        commands = [(r, e) for r, e in requests[stack] if 'command' in e and e['request_id'] in accepted]
        refs = references[stack]
        coverage = Counter(); during = Counter(); overlaps = 0; native_rows = []; window_end_overlaps = 0
        initial_armed = next((m['state'] for _, m in public if m['state'].get('armed')), None)
        startup_overlaps = 0
        for row, target in targets:
            if stack == 'arducopter':
                require(target['type_mask'] in (0x9E3, 0x9F8) and target['coordinate_frame'] == 6
                        and target['header']['frame_id'] == 'map', 'Unexpected AP mask/frame')
                require(all(target['acceleration_or_force'][part][axis] == 0. for part in ('linear', 'angular') for axis in ('x', 'y', 'z'))
                        and all(target['velocity']['angular'][axis] == 0. for axis in ('x', 'y', 'z'))
                        and target['velocity']['linear']['z'] == 0., 'AP ignored payload/vertical feedforward differs')
                if target['type_mask'] == 0x9E3:
                    require(target['latitude'] == target['longitude'] == 0., 'AP inactive Pxy payload became an anchor')
                boot_ns = stamp(target)
            else:
                require(all(math.isnan(v) for v in (*target['acceleration'], *target['jerk'], target['yawspeed'])),
                        'PX4 acceleration/jerk/yaw-rate axes active')
                mixed = all(math.isnan(v) for v in target['position'][:2]) and math.isfinite(target['position'][2])
                hold = all(math.isfinite(v) for v in target['position'])
                require((mixed and all(math.isfinite(v) for v in target['velocity']) and target['velocity'][2] == 0.)
                        or (hold and all(math.isnan(v) for v in target['velocity'])), 'PX4 mixed/hold shape differs; Vz must remain zero in mixed')
                boot_ns = target['timestamp']*1000
            if row['tick']*1_000_000 < accepted[refs['waypoint']['envelope']['request_id']][1]:
                continue  # Native takeoff/warmup is covered by baseline physics/setup ACK.
            require(boot_ns <= row['tick']*1_000_000 and boot_ns in states, 'Target lacks raw public source bootstamp')
            public_sources = [(r, m) for r, m in states[boot_ns] if abs(r['wall']-row['wall']) <= 2]
            require(public_sources, 'Native target public source is stale')
            if stack == 'arducopter':
                require(boot_ns//1000 in homes and abs(homes[boot_ns//1000][0]['wall']-row['wall']) <= 2,
                        'AP target lacks fresh native source')
                home = homes[boot_ns//1000][1]
                require(all(home[k] for k in ('home_valid', 'position_valid', 'velocity_valid', 'attitude_valid')), 'Invalid AP target source')
            else:
                require(boot_ns//1000 in positions and abs(positions[boot_ns//1000][0]['wall']-row['wall']) <= 2,
                        'PX4 target lacks fresh native source')
                source = positions[boot_ns//1000][1]
                require(all(source[k] for k in ('xy_valid', 'z_valid', 'v_xy_valid', 'v_z_valid')), 'Invalid PX4 target source')
                modes = [m for r, m in offboard if m['timestamp']*1000 == boot_ns and abs(r['wall']-row['wall']) <= 2]
                require(any(m['position'] and m['velocity'] == mixed and not any(value for key, value in m.items()
                    if key not in ('timestamp', 'position', 'velocity')) for m in modes), 'PX4 OffboardControlMode differs')
                home = None
            matched = None
            for name, record in reversed(list(refs.items())):
                if name == 'invalid_world_yaw_rate':
                    continue
                rid = record['envelope']['request_id']
                if accepted[rid][1] > row['tick']*1_000_000:
                    continue
                for _, state in public_sources:
                    if native_matches(stack, target, native_expected(name, record, state['state']), home):
                        matched = name
                        break
                if matched:
                    break
            if matched is None and initial_armed is not None:
                first_accept = accepted[refs['waypoint']['envelope']['request_id']]
                initial_hold = ([*initial_armed['position'][:2], initial_armed['position'][2]+3.], [None]*3, 0.)
                if (boot_ns <= first_accept[1] and row['wall']-first_accept[0]['wall'] <= 2
                        and native_matches(stack, target, initial_hold, home)):
                    startup_overlaps += 1
                    continue
            require(matched is not None, 'Native target differs from every exact accepted command/captured reference')
            rid = refs[matched]['envelope']['request_id']
            successor = next((e for _, e in commands if e['request_id'] > rid), None)
            if successor and accepted[successor['request_id']][1] < row['tick']*1_000_000:
                require(row['wall']-accepted[successor['request_id']][0]['wall'] <= 2,
                        'Superseded target outside existing 2s communication bound')
                overlaps += 1
            coverage[matched] += 1
            for segment in tasks[stack]['mixed_segments']:
                if segment['start_ns'] <= boot_ns <= segment['end_ns']:
                    expected_name = 'world_zero' if segment['name'] == 'invalid_world_yaw_rate' else segment['name']
                    expected_rid = refs[expected_name]['envelope']['request_id']
                    if matched != expected_name and after_completed_window(rid, expected_rid, accepted[rid][1],
                                                                           segment['end_ns'], row['tick']):
                        window_end_overlaps += 1
                        continue
                    require(matched == expected_name, 'Wrong active native command within frozen continuous window: '
                        +str(dict(stack=stack, expected=expected_name, matched=matched, source_boot_ns=boot_ns,
                                  observed_tick=row['tick'], window_start_ns=segment['start_ns'],
                                  window_end_ns=segment['end_ns'], matched_accepted_ns=accepted[rid][1])))
                    during[segment['name']] += 1
            if stack == 'arducopter' and target['type_mask'] == 0x9E3:
                native_rows.append(dict(name=matched, boot_us=boot_ns//1000, wall=row['wall'], target=target))
        require(set(coverage) == set(refs)-{'invalid_world_yaw_rate'} and all(during[s['name']] for s in tasks[stack]['mixed_segments']),
                'Missing native output for a public command or physical window')
        output[stack] = dict(targets_by_command=dict(coverage), targets_inside_windows=dict(during),
            cross_topic_boundary_observations=overlaps, startup_boundary_observations=startup_overlaps,
            source_stamp_window_end_overlaps=window_end_overlaps, target_ack_available=False,
            ordering_claim='Exact request identity and source/public timestamps; no DDS cross-topic FIFO claim')
        if stack == 'arducopter':
            output[stack]['mixed_rows'] = native_rows
    return output


def guip_target(message, native_rows):
    require(message['Type'] == 7 and message['Terrain'] == 0 and message['TimeUS'] > 0
            and all(math.isfinite(message[k]) for k in ('pX', 'pY', 'pZ', 'vX', 'vY', 'vZ', 'aX', 'aY', 'aZ'))
            and all(message[k] == 0. for k in ('pX', 'pY', 'vZ', 'aX', 'aY', 'aZ')),
            'Native GUIP type 7 inactive Pxy/Vz/acceleration or terrain differs')
    return [row for row in native_rows if row['boot_us'] <= message['TimeUS']
            and message['vX'] == f32(row['target']['velocity']['linear']['y'])
            and message['vY'] == f32(row['target']['velocity']['linear']['x'])]


def native_logs(root, tasks, native, data):
    from pymavlink import DFReader
    source = (root/'native-source/ArduCopter/Log.cpp').read_text()
    require(re.search(r'"GUIP",\s*"QBfffbffffff",\s*"TimeUS,Type,pX,pY,pZ,Terrain,vX,vY,vZ,aX,aY,aZ"', source),
            'Retained native GUIP schema differs from audited decoder')
    paths = sorted((root/'arducopter/logs').glob('*.BIN'))
    require(paths, 'Missing raw AP DataFlash log')
    rows = []; parameters = []; errors = []
    for path in paths:
        reader = DFReader.DFReader_binary(str(path))
        while True:
            message = reader.recv_msg()
            if message is None:
                break
            kind = message.get_type()
            if kind == 'GUIP':
                rows.append(message.to_dict())
            elif kind == 'PARM' and message.Name == 'LOG_DISARMED':
                parameters.append(message.Value)
            elif kind == 'BAD_DATA':
                errors.append(str(message))
    require(not errors and parameters and all(value == 1. for value in parameters),
            'Native log is truncated/corrupt or LOG_DISARMED is not 1')
    mixed = [m for m in rows if m['Type'] == 7]
    require(mixed, 'Native GUIP never entered new submode 7')
    native_rows = native['arducopter'].pop('mixed_rows')
    boot_observations = sorted((m['time_boot_us'], r['wall']) for r, m in data['/ap/wksim/local_state_v1'])
    from bisect import bisect_left
    boot_times = [boot for boot, _ in boot_observations]
    coverage = Counter(); maximum_age = 0
    for m in mixed:
        candidates = guip_target(m, native_rows)
        index = bisect_left(boot_times, m['TimeUS'])
        require(0 < index < len(boot_observations), 'GUIP time lacks surrounding raw native boot observations')
        before, after = boot_observations[index-1], boot_observations[index]
        # Bound association with observed walls around this native boot time;
        # this is the existing 2s communication bound, not a new command TTL.
        candidates = [row for row in candidates if before[1]-2 <= row['wall'] <= after[1]+2]
        require(candidates, 'Native GUIP mixed acceptance has no preceding raw DDS target')
        latest = max(candidates, key=lambda row: row['boot_us'])
        maximum_age = max(maximum_age, m['TimeUS']-latest['boot_us'])
        # Restrict native-submode completion proof to the actual frozen windows.
        for segment in tasks['arducopter']['mixed_segments']:
            if segment['start_ns'] <= m['TimeUS']*1000 <= segment['end_ns']:
                require(segment['name'] in MOVING and latest['name'] == segment['name'],
                        'Native submode 7 appeared during zero/rejection/absolute hold')
                coverage[segment['name']] += 1
    require(set(coverage) == set(MOVING), 'A mixed physical window lacks native submode 7 acceptance evidence')
    return dict(files={p.name:digest(p) for p in paths}, message='GUIP', native_submode=7,
                mixed_acceptances=len(mixed), acceptances_inside_windows=dict(coverage),
                maximum_matching_target_boot_age_us=maximum_age, log_disarmed=1,
                inactive_fields=['pX', 'pY', 'vZ', 'aX', 'aY', 'aZ'],
                altitude_interpretation='pZ is NED relative to EKF origin; no direct equality to home-relative Z is claimed')


def audit(root):
    root = Path(root)
    result = read(root/'result.json')
    identity = retained_identity(root, result)
    raw = decode(root, result, admission_key='mixed_admission')
    tasks, phases, requests, references = task_evidence(root, result, raw)
    native = native_targets(raw, requests, references, tasks)
    logs = native_logs(root, tasks, native, raw)
    physics = physical(root, result, tasks, phases)
    rates = rate_windows(root, result)
    artifacts = {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob('*')) if p.is_file()}
    return dict(status='pass', task_profile=PROFILE, run_id=result['run_id'], scene_epoch=result['scene_epoch'],
        identity=identity, raw_dds_channels={name:len(rows) for name, rows in raw.items()}, native_targets=native,
        native_guided_submode=logs, **physics, rate_segments=rates, result_sha256=digest(root/'result.json'),
        evidence_sha256=artifacts, audit_source_sha256=digest(__file__),
        reused_audit_source_sha256={name:digest(REPO/'tools'/name) for name in
            ('audit_pv_trajectory.py', 'audit_joint_flight.py', 'audit_joint_rate.py')},
        audit_evidence_formatter_sha256=digest(REPO/'Simulator/wksim_runtime/evidence.py'), outstanding_checks=[],
        limitations=['Bounded experimental XY velocity/Z position/yaw only; production remains unadmitted.',
            'Public command acceptance, raw target publication, setup ACK, GUIP submode entry and physical completion are separate evidence.',
            'PX4 mixed Vz remains zero feedforward; AP adapter explicitly ignores native Vz. Acceleration is inactive.',
            'Native fence/origin-failure/timeout/pause/EKF-reset/avoidance boundary scenarios require separate runs.'])


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
            outstanding_checks=['Audit terminated at the reported failure; missing evidence is incomplete, and downstream checks are not accepted.'])
    raw = json.dumps(report, indent=2, allow_nan=False)+'\n'
    if args.output:
        args.output.write_text(raw)
    print(raw, end='')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
