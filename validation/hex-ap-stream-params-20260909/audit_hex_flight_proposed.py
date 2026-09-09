"""Offline Hex raw audit (#65). Run in the retained ROS message overlay.

python3 -B tools/audit_hex_flight.py --run-dir /root/wksim-hex-flight-ID/ID \
    --output /absolute/new-audit.json [--require-cold-reset]

Exit 0 proves the declared recorded-flight scope; exit 1 rejects incomplete or
contradictory evidence. No native library, FC, ROS node or flight is started.
Cold-reset proof recursively audits the parent, never trusts its status label.
Synthetic unit cases exercise guards only. They are never flight acceptance.
"""
import argparse
from collections import defaultdict
import hashlib
import importlib
import json
import math
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import hex_physics_evidence as core
from tools.hex_candidate import native_parameters, PLAN_IDENTITY, BUILD_SHA, plan_identity
from Simulator.wksim_runtime.hex_task import protocol_for
from tools.hex_physics import MODEL_IDENTITY, LIBRARY_SHA256
from tools.build_hex_model_candidate import verify_build, canonical

PROTOCOL_SHA = '33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc'
PROTOCOL_PATH = 'Simulator/wksim_runtime/hex-flight-v1.json'
LEGACY_PX4_SOURCE_PAIRS = {'tools/hex_launch_plan.py': (('5576dc5326261d9edd5d68352189ac2923d1ff9c2a868f9e28bc6b4be612dd0f',
                               '9e2a4762033d9e188eff09e469c5e1c526910b5b2b6847975854e1f2122da2cb'),
                              ('5576dc5326261d9edd5d68352189ac2923d1ff9c2a868f9e28bc6b4be612dd0f',
                               '79f245859060c3ed9ac344938cf2ffa581598a53ba463e403536baa550071a6d'),
                              ('9e2a4762033d9e188eff09e469c5e1c526910b5b2b6847975854e1f2122da2cb',
                               '79f245859060c3ed9ac344938cf2ffa581598a53ba463e403536baa550071a6d')),
 'tools/hex_candidate.py': (('337ed9fb3ff0423c7ec2da9c5e02530e413575c357349615408036830af31bbe',
                             'ae6e03d5098dae3e258b3c49f3c42eb32036e283ee55a2c389bff45d42e335e5'),
                            ('337ed9fb3ff0423c7ec2da9c5e02530e413575c357349615408036830af31bbe',
                             '6bf746ed0b0620d0bb02cae951581cd745f482cb9fe8e75c119e86a7cbfd7103'),
                            ('ae6e03d5098dae3e258b3c49f3c42eb32036e283ee55a2c389bff45d42e335e5',
                             '6bf746ed0b0620d0bb02cae951581cd745f482cb9fe8e75c119e86a7cbfd7103')),
 'Simulator/wksim_core/px4_mavlink.py': (('08b3d5fbf6754822572240ceb6beb289341bd0c6653455a35b60b3fb3d85ab3d',
                                          'e8c903f2b4c84a261adf6f512c8437c51364143dc048d1ac2cb873e7cfb53260'),)}
PUBLIC = '/uav1/prometheus/'


def require(value, message):
    if not value:
        raise ValueError(message)


def compatible_source(stack, name, archived, current):
    return archived == current or (stack == 'px4' and
        (archived, current) in LEGACY_PX4_SOURCE_PAIRS.get(name, ()))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    value = {}
    for k, v in pairs:
        require(k not in value, 'Duplicate JSON key: '+k)
        value[k] = v
    return value


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: '+value)))


def read(path):
    return parse(Path(path).read_text(encoding='utf-8'))


def lines(path):
    with Path(path).open(encoding='utf-8') as stream:
        for n, line in enumerate(stream, 1):
            require(line.endswith('\n'), f'Incomplete JSONL {path}:{n}')
            yield parse(line)


def near(a, b, tolerance=1e-6):
    if isinstance(b, (tuple, list)):
        return isinstance(a, (tuple, list)) and len(a) == len(b) and all(near(x, y, tolerance) for x, y in zip(a, b))
    return type(a) in (int, float) and math.isfinite(a) and abs(a-b) <= tolerance


def enu(v):
    return dict(time=v[2], position=[v[7], v[6], -v[8]], velocity=[v[4], v[3], -v[5]],
                attitude=[v[9], -v[10], math.remainder(math.pi/2-v[11], 2*math.pi)])


def stamp(state):
    s = state['header']['stamp']
    return s['sec']+s['nanosec']/1e9


def physical(root, result):
    foundation = core.check(root, expected_run_id=result['run_id'], expected_model_identity=MODEL_IDENTITY)
    require(foundation['passed'], 'Physics foundation rejected: '+json.dumps(foundation['errors'][:8]))
    rows = list(lines(root/'physics-1ms.jsonl'))
    start, init = rows[:2]
    require(start['config'] == result['admission']['identities']['hex_config'], 'Raw model config differs')
    require(start['library_sha256'] == LIBRARY_SHA256, 'Raw library identity differs')
    require(init == result['model_initialization'] and init['readback'] ==
            {k: v['value'] for k, v in start['config']['parameters'].items()}, 'Initial native readback differs')
    for name, checksum in start['sources_sha256'].items():
        require(digest(root/'run-source'/name) == checksum == result['source_sha256'][name], 'Raw source pin: '+name)
    steps = [r for r in rows if r['kind'] == 'step']
    trace = list(lines(root/'truth.jsonl'))
    require(trace, 'No sampled truth')
    previous = 0
    for r in trace:
        tick = round(r['time']*1000)
        require(previous < tick <= len(steps) and (not previous or tick-previous <= 50), 'Truth tick/gap differs')
        raw = steps[tick-1]
        v = raw['output120']
        require(r['vehicle'] == v[:60] and r['sensor'] == v[60:90] and r['time'] == v[2], 'Truth differs from 1ms raw')
        inputs = r['controls'] if result['stack'] == 'px4' else [max(0, p-1000)/1000 for p in r['pwm'][:6]]+[0.]*10
        require(inputs == raw['input16'], 'Truth actuator channels differ')
        previous = tick
    group_size = 4 if result['stack'] == 'px4' else 1
    require(all(r['group_steps'] == group_size for r in steps), 'Native group size differs')
    require(all(type(r['observed_monotonic_ns']) is int and r['observed_monotonic_ns'] > 0 for r in steps)
            and all(a['observed_monotonic_ns'] < b['observed_monotonic_ns'] for a, b in zip(steps, steps[1:])),
            'Physical observation clock invalid')
    require(all(all(x >= 0 for x in r['output120'][16:22]) and r['output120'][22:24] == [0., 0.] for r in steps),
            'Six RPM/unused RPM mapping differs')
    # AP retransmissions may be recorded, but must not create extra integration groups.
    keys = [r['held_packet']['frame' if result['stack'] == 'arducopter' else 'time_usec']
            for r in steps if r['substep'] == 0 and r['held_packet'] is not None]
    require(keys and all(a < b for a, b in zip(keys, keys[1:])), 'Replayed actuator advanced physics')
    require(all(any(r['input16'][i] > 0 and r['output120'][16+i] > 0 for r in steps) for i in range(6)),
            'One of six physical motors never active')
    return dict(counts=foundation['counts'], raw_sha256=digest(root/'physics-1ms.jsonl'),
                initial_tick=0, six_active_motors=True), steps, trace


def identity(root, result):
    selected, protocol_sha = protocol_for(result['stack'])
    protocol_path = selected.relative_to(REPO).as_posix()
    selected_plan = plan_identity(result['stack'])
    admission = read(root/'admission.json')
    require(admission == result['admission'] and admission['ok'] is True, 'Admission mismatch')
    require(result['model_profile'] == admission['model_profile'] == 'hex_x' and result['experimental'] is True
            and result['production_admitted'] is False, 'Not experimental Hex flight evidence')
    require(read(root/'config.json') == result['config'] == admission['config'], 'Config mismatch')
    require(result['config']['run_id'] == result['run_id'] and result['config']['stack'] == result['stack'], 'Run binding mismatch')
    require(result['status'] == 'observed' and result['task']['hex']['status'] == 'observed_pending_independent_raw_audit'
            and result['safe_landing'] is True and result['children_reaped'] is True and result['source_unchanged'] is True
            and result['candidate_unchanged'] is True, 'Runner recorded failure/incomplete lifecycle; not promotable')
    require(digest(root/'protocol.json') == protocol_sha == result['protocol_sha256']
            == digest(selected), 'Frozen physical budget identity changed')
    require(read(root/'protocol.json') == result['protocol'], 'Protocol report mismatch')
    ids = admission['identities']; baseline = ids['baseline']
    require(ids['hex_build_sha256'] == BUILD_SHA and ids['hex_library_sha256'] == LIBRARY_SHA256
            and ids['plan_identity'] == selected_plan and ids['hex_config']['model_identity'] == MODEL_IDENTITY,
            'Hex identity not pinned')
    library = verify_build(admission['library'], ids['hex_config'])  # Read only; never dlopen.
    require(digest(library) == LIBRARY_SHA256 and digest(library.parent/'build.json') == BUILD_SHA, 'Build pin differs')
    required_sources = {'tools/'+n for n in ('hex_candidate.py', 'run_hex_flight.py', 'run-hex-flight.sh',
        'hex_physics.py', 'hex_launch_plan.py', 'build_hex_model_candidate.py')}
    required_sources |= {'Simulator/wksim_runtime/'+n for n in ('hex_task.py', 'hex-flight-v1.json', 'runtime.py',
        'isolation.py', 'task.py', 'evidence.py', 'telemetry_dialect.py', 'telemetry-dialects.json')}
    required_sources |= {'Simulator/wksim_core/'+n for n in ('model.py', 'model.cpp', 'ap_json.py',
        'px4_mavlink.py', 'state_stream.py', 'px4-rc.mavlink')}
    required_sources.remove(PROTOCOL_PATH)
    required_sources.add(protocol_path)
    require(set(result['source_sha256']) == required_sources, 'Executed source inventory incomplete')
    for name, checksum in result['source_sha256'].items():
        require(digest(root/'run-source'/name) == checksum, 'Retained source differs: '+name)
    compatibility = {}
    for name in ('tools/hex_physics.py', 'tools/build_hex_model_candidate.py', 'tools/hex_launch_plan.py',
                 'tools/hex_candidate.py', protocol_path, 'Simulator/wksim_core/px4_mavlink.py',
                 'Simulator/wksim_core/ap_json.py'):
        # Only the reviewed archived/current pair is compatible; any future edit
        # requires a new comparison. Archived bytes are independently verified.
        current = digest(REPO/name)
        archived = result['source_sha256'][name]
        require(compatible_source(result['stack'], name, archived, current),
                'Shared decoding/identity recipe changed: '+name)
        if archived != current:
            compatibility[name] = dict(archived_sha256=archived, reviewed_current_sha256=current)
    require(read(root/'postflight-admission.json')['identities'] == ids, 'Postflight seals differ')
    parameters = native_parameters(result['stack'])
    require(parameters == admission['parameters'], 'Frozen six-channel native parameters differ')
    for pin in baseline['manifests'].values():
        require(digest(pin['path']) == pin['sha256'], 'Fixed build manifest differs')
    expected_identity = dict(model_identity=MODEL_IDENTITY, plan_identity=selected_plan, model_profile='hex_x',
        stack=result['stack'], native_parameters=parameters, fixed_manifests=baseline['manifests'])
    require(admission['configuration_identity'] == 'sha256:'+hashlib.sha256(canonical(expected_identity).encode()).hexdigest(),
            'Configuration identity recomputation differs')
    for path, checksum in ids['setup_sha256'].items():
        require(digest(path) == checksum, 'ROS overlay setup changed')
    for name in ('physics', 'agent', 'fc', 'control'):
        child = result['children'][name]
        require(child['argv'] == result['launch_plan'][name] == child['identity']['argv']
                and child['cwd'] == child['identity']['cwd'] == result['run_dir'], 'Actual launch identity differs: '+name)
    for name, pin in [('fc', baseline['ap' if result['stack'] == 'arducopter' else 'px4']),
                      ('agent', baseline[result['stack']+'_agent'])]:
        require(result['children'][name]['identity']['executable'] == pin['path']
                and digest(pin['path']) == pin['sha256'] and pin['path'] in (root/(name+'.maps')).read_text(),
                'Loaded native binary differs: '+name)
    require(str(library) in (root/'physics.maps').read_text(), 'Admitted model absent from process maps')
    require(result['actual_control_sha256'] == baseline['sealed_control']['python_sha256'], 'Control code identity differs')
    for name, checksum in result['actual_control_sha256'].items():
        require(digest(Path(baseline['sealed_control_package'])/name) == checksum, 'Installed Control changed')
    require(read(root/'isolation.json') == result['resources'] and result['resources']['independent_clock'] is True,
            'Isolation record mismatch')
    if result['stack'] == 'px4':
        xml = Path(result['config']['px4_root'])/'build/px4_sitl_default/parameters.xml'
        require(digest(xml) == ids['parameters_xml_sha256'], 'PX4 type XML changed')
        types = {p.attrib['name']: p.attrib['type'] for p in ET.parse(xml).iter('parameter')}
        require(admission['parameter_types'] == {k: types[k] for k in parameters}, 'Parameter types differ')
        env = result['launch_plan']['fc_environment']
        require(env['PX4_SIM_SPEED_FACTOR'] == '1' and all(env['PX4_PARAM_'+k] == str(v) for k, v in parameters.items()),
                'PX4 startup six-channel values differ')
    else:
        from tools.hex_launch_plan import launch_plan
        require((root/'hex.parm').read_text() == launch_plan('arducopter')['ap_parameter_file']+'LOG_DISARMED 1\n'
                and (root/'dds.parm').read_text() == 'DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n',
                'AP defaults content differs')
        argv = result['children']['fc']['argv']
        require(argv[argv.index('--defaults')+1].split(',') == [str(Path(result['config']['ap_candidate'])/
                'src/Tools/autotest/default_params/copter.parm'), result['run_dir']+'/hex.parm', result['run_dir']+'/dds.parm'],
                'AP defaults order differs')
    return dict(source_files=len(result['source_sha256']), configuration_identity=admission['configuration_identity'],
                model_identity=MODEL_IDENTITY, library_sha256=LIBRARY_SHA256, protocol_sha256=protocol_sha,
                exact_px4_source_compatibility=compatibility)


def decode(root, result):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from Simulator.wksim_runtime.evidence import json_value
    from Simulator.wksim_runtime.telemetry_dialect import load_dialect
    from Simulator.wksim_runtime.joint_profile import package_digest
    from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState
    from prometheus_msgs.msg import TextInfo
    from px4_msgs.msg import TrajectorySetpoint, OffboardControlMode, VehicleStatus, VehicleControlMode
    from ardupilot_msgs.msg import WksimState, GlobalPosition
    from rcl_interfaces.srv import GetParameters
    codecs = {}
    for name, pin in result['admission']['identities']['baseline']['message_packages'].items():
        module = importlib.import_module(name)
        require(Path(module.__file__).is_relative_to(Path(pin['prefix'])), 'Wrong ROS decoder overlay: '+name)
        require(package_digest(pin['prefix'], complete=pin.get('complete_snapshot', False)) == pin['sha256'],
                'ROS generated codec bytes changed: '+name)
        codecs[name] = dict(path=module.__file__, sha256=pin['sha256'])
    types = {PUBLIC+'v2/command': CommandRequest, PUBLIC+'v2/setup': SetupRequest,
             PUBLIC+'v2/state': SessionState, PUBLIC+'text_info': TextInfo,
             '/ap/wksim/local_state_v1': WksimState, '/ap/cmd_gps_pose': GlobalPosition}
    for direction, name, cls in [('in', 'trajectory_setpoint', TrajectorySetpoint),
            ('in', 'offboard_control_mode', OffboardControlMode), ('out', 'vehicle_status', VehicleStatus),
            ('out', 'vehicle_control_mode', VehicleControlMode)]:
        version = getattr(cls, 'MESSAGE_VERSION', 0)
        types['/wksim_px4_21/fmu/'+direction+'/'+name+(f'_v{version}' if version else '')] = cls
    dialect, dialect_identity = load_dialect(result['stack'])
    parser = dialect.MAVLink(None)
    rows = list(lines(root/'hex-native.jsonl'))
    data, messages, recorded, discovery, services = defaultdict(list), [], [], [], []
    target = 22 if result['stack'] == 'px4' else 241
    peer, previous = None, 0
    for row in rows:
        require(row['run_id'] == result['run_id'] and core._number(row['monotonic'])
                and row['monotonic'] >= previous, 'Native identity/clock differs')
        previous = row['monotonic']
        kind = row['kind']
        if kind == 'dds':
            require(row['per_message_publisher_gid_available'] is False and 'publisher_gid' not in row
                    and type(row['source_timestamp']) is int and type(row['received_timestamp']) is int,
                    'Fabricated DDS attribution or invalid timestamp')
            value = dict(message_to_ordereddict(deserialize_message(bytes.fromhex(row['cdr_hex']), types[row['topic']])))
            data[row['topic']].append((row, value))
        elif kind == 'telemetry_identity':
            require(row['dialect'] == dialect_identity, 'Telemetry dialect differs')
        elif kind == 'mavlink_rx':
            require(row['peer'][0] == '127.0.0.1', 'Nonlocal native peer')
            if peer is not None and peer != row['peer']:
                continue
            for message in parser.parse_buffer(bytes.fromhex(row['datagram_hex'])) or []:
                if message.get_srcSystem() != target or message.get_srcComponent() != 1:
                    continue
                if peer is None:
                    if message.get_type() != 'HEARTBEAT' or result['stack'] == 'px4' and row['peer'][1] != 18591:
                        continue
                    peer = row['peer']
                raw = bytes(message.get_msgbuf()); header = 10 if raw[0] == 0xfd else 6
                messages.append((row, message.to_dict(), raw.hex(), raw[header:header+raw[1]].hex()))
        elif kind == 'mavlink_decoded':
            recorded.append(row)
        elif kind == 'dds_discovery_publishers':
            discovery.append(row)
        elif kind in ('parameter_get_request', 'parameter_get_response'):
            cls = GetParameters.Request if kind.endswith('request') else GetParameters.Response
            value = dict(message_to_ordereddict(deserialize_message(bytes.fromhex(row['serialized_cdr_hex']), cls)))
            services.append((row, value))
    require(len(messages) == len(recorded) > 0, 'Raw MAVLink/decoded count differs')
    for (_, value, packet, payload), r in zip(messages, recorded):
        require(json_value(value) == r['message'] and packet == r['packet_hex'] and payload == r['payload_hex']
                and r['source_system'] == target and r['source_component'] == 1 and r['peer'] == peer,
                'MAVLink datagram/decoded payload differs')
    require(discovery and sum(r['kind'] == 'telemetry_identity' for r in rows) == 1, 'Missing native identities')
    return dict(dds_records=sum(map(len, data.values())), mavlink_messages=len(messages), codecs=codecs,
                dialect=dialect_identity, per_message_publisher_gid_available=False), data, recorded, rows, services


def cursor(row, trace):
    c = row['physical_cursor']; n = c['records']
    require(type(n) is int and 1 <= n <= len(trace) and c['final_time'] == trace[n-1]['time'], 'Relabelled physical cursor')
    return c['final_time']


def phases_and_public(result, trace, data):
    from Simulator.wksim_runtime.evidence import json_value
    phases = {}
    previous = (-math.inf, 0)
    for p in result['task']['hex']['phases']:
        t = cursor(p, trace)
        require(p['phase'] not in phases and p['observed_monotonic_s'] > previous[0] and t >= previous[1], 'Phase order differs')
        require(near(stamp(p['state']), p['native_boot_s'], 1e-9), 'Phase boot clock differs')
        phases[p['phase']] = p
        previous = (p['observed_monotonic_s'], t)
    public = sorted(data[PUBLIC+'v2/setup']+data[PUBLIC+'v2/command'], key=lambda x: x[1]['request_id'])
    require(len(public) == 6 and [v['request_id'] for _, v in public] == list(range(1, 7)), 'Public request chain incomplete/replayed')
    require(json_value([v for _, v in public]) == result['task']['request_envelopes'], 'Public CDR/request report differs')
    events = [parse(v['message']) for _, v in data[PUBLIC+'text_info']]
    for row, v in public:
        require(v['version'] == 1 and v['run_id'] == result['run_id'] and v['control_epoch'] == result['task']['control_epoch'],
                'Public authority changed')
        require(any(e.get('request_id') == v['request_id'] and e.get('run_id') == v['run_id']
                    and e.get('control_epoch') == v['control_epoch'] and e.get('event') ==
                    ('command_accepted' if 'command' in v else 'setup_completed') for e in events), 'Missing wire acceptance')
        cursor(row, trace)
    setups = [v.get('setup') for _, v in public]
    require(setups[0]['cmd'] == setups[5]['cmd'] == 1 and setups[0]['px4_mode'] == setups[5]['px4_mode'] == 'AUTO.LOITER'
            and setups[1]['cmd'] == 0 and setups[1]['arming'] is True and setups[2]['cmd'] == 3
            and setups[2]['control_state'] == 'COMMAND_CONTROL', 'Frozen setup sequence differs')
    move, land = public[3][1]['command'], public[4][1]['command']
    require(move['agent_cmd'] == 4 and move['move_mode'] == 0 and move['position_ref'] == [2., 3., 3.]
            and move['yaw_ref'] == 0 and move['yaw_rate_mode'] is False and move['command_id'] == 1
            and land['agent_cmd'] == 3 and land['command_id'] == 2, 'Frozen mission command differs')
    for key in ('setup', 'command'):
        endpoints = result['task']['hex']['public_request_graph'][key]
        require(len(endpoints) == 2 and {e['node'] for e in endpoints} == {'prometheus_native_control', 'wksim_hex_raw_recorder'}
                and all(e['namespace'] == '/' and any(bytes.fromhex(e['endpoint_gid'])) for e in endpoints)
                and len({e['endpoint_gid'] for e in endpoints}) == 2, 'Public subscription graph differs')
    states = data[PUBLIC+'v2/state']
    require(states, 'No raw public states')
    for name, p in phases.items():
        # Match the actual state from CDR, not a boolean in result.json.
        require(any(row['monotonic'] <= p['observed_monotonic_s'] and json_value(v['state']) == p['state']
                    and v['run_id'] == result['run_id'] and v['control_epoch'] == result['task']['control_epoch']
                    for row, v in states), 'Phase state absent from raw CDR: '+name)
    return dict(public_requests=6, phase_count=len(phases)), phases


def fixed_window(steps, begin, end):
    lo, hi = round(begin*1000), round(end*1000)
    require(near(begin, lo*.001, 1e-8) and near(end, hi*.001, 1e-8) and 1 <= lo <= hi <= len(steps), 'Incomplete fixed 1ms window')
    return steps[lo-1:hi]


def gates(result, steps, phases, data):
    b = result['protocol']
    def when(name):
        return phases[name]['physical_cursor']['final_time']
    metrics = {}
    for p in phases.values():
        tick = round(p['physical_cursor']['final_time']*1000)
        age = p['observed_monotonic_s']-steps[tick-1]['observed_monotonic_ns']/1e9
        require(0 <= age <= b['physical_truth_max_age_s'], 'Phase uses stale/future physical cursor')
    for label, first, last, duration, predicate in (
        ('hold', 'takeoff_reached', 'hold_completed', b['hold_duration_s'],
         lambda s: abs(s['position'][2]-b['hold_target_height_m']) <= b['hold_height_error_m']
         and max(abs(x) for x in s['attitude'][:2]) <= b['hold_tilt_rad']),
        ('waypoint', 'waypoint_reached', 'waypoint_completed', b['waypoint_duration_s'],
         lambda s: math.dist(s['position'], b['waypoint_enu_m']) <= b['waypoint_error_m']
         and math.hypot(*s['velocity']) <= b['waypoint_speed_mps'])):
        start, end = when(first), when(last)
        require(end-start >= duration-1e-9 and phases[last]['native_boot_s']-phases[first]['native_boot_s'] >= duration-1e-9,
                label+': incomplete model/native dwell duration')
        samples = fixed_window(steps, start, end)
        violations = [r['tick'] for r in samples if not predicate(enu(r['output120']))]
        public = [v['state'] for row, v in data[PUBLIC+'v2/state']
                  if phases[first]['observed_monotonic_s'] <= row['monotonic'] <= phases[last]['observed_monotonic_s']]
        require(public and all(predicate(s) for s in public), label+': public dwell threshold exceeded')
        metrics[label] = dict(start_tick=samples[0]['tick'], end_tick=samples[-1]['tick'], samples=len(samples),
                             violation_ticks=violations[:20], violation_count=len(violations), passed=not violations)
    takeoff = enu(steps[round(when('takeoff_reached')*1000)-1]['output120'])
    require(takeoff['position'][2] >= b['takeoff_min_height_m'], 'Takeoff physical height failed')
    for first, last, timeout in [('task_control_ready', 'takeoff_reached', b['takeoff_timeout_s']),
            ('waypoint_accepted', 'waypoint_reached', b['waypoint_timeout_s']),
            ('land_accepted', 'landed_disarmed_public', b['land_timeout_s']),
            ('takeoff_reached', 'hold_completed', 15), ('waypoint_reached', 'waypoint_completed', 15)]:
        elapsed = phases[last]['observed_monotonic_s']-phases[first]['observed_monotonic_s']
        require(0 <= elapsed <= timeout, 'Frozen action watchdog exceeded: '+last)
    start = when('landed_disarmed_public'); end = steps[-1]['output120'][2]
    samples = fixed_window(steps, start, end)
    bad = [r['tick'] for r in samples if abs(r['output120'][8]) >= b['ground_height_abs_lt_m']]
    for key in ('landed_disarmed_public', 'ground_hold_completed', 'normal_stop_ready'):
        state = phases[key]['state']
        require(state['armed'] is False and state['connected'] is True and state['odom_valid'] is True
                and abs(state['position'][2]) < b['ground_height_abs_lt_m'], 'Ground public state failed')
    metrics['landing_to_terminal'] = dict(start_tick=samples[0]['tick'], end_tick=samples[-1]['tick'],
                                         samples=len(samples), violation_count=len(bad), violation_ticks=bad[:20], passed=not bad)
    ground = fixed_window(steps, when('hex_ground_ready'), when('parameter_readback_complete'))
    bad = [r['tick'] for r in ground if abs(r['output120'][8]) >= b['ground_height_abs_lt_m']]
    metrics['parameter_ground'] = dict(samples=len(ground), violation_count=len(bad), violation_ticks=bad[:20], passed=not bad)
    for row, value in data[PUBLIC+'v2/state']:
        if phases['hex_ground_ready']['observed_monotonic_s'] <= row['monotonic'] <= phases['parameter_readback_complete']['observed_monotonic_s']:
            state = value['state']
            require(state['armed'] is False and state['connected'] is True and state['odom_valid'] is True
                    and abs(state['position'][2]) < .3, 'Parameter read lost public ground')
    require(core._number(result['wall_seconds']) and 0 < result['wall_seconds'] <= b['wall_watchdog_s'], 'Flight watchdog exceeded')
    return metrics


def parameters(result, rows, messages, services, phases, trace):
    expected = native_parameters(result['stack'])
    begin, end = phases['hex_ground_ready'], phases['parameter_readback_complete']
    require(end['observed_monotonic_s']-begin['observed_monotonic_s'] <= result['protocol']['parameter_total_timeout_s'][result['stack']],
            'Parameter aggregate deadline exceeded')
    actual = {}
    if result['stack'] == 'px4':
        from Simulator.wksim_runtime.telemetry_dialect import load_dialect
        dialect, _ = load_dialect('px4')
        requests = [r for r in rows if r['kind'] == 'parameter_request_read_tx']
        require([r['name'] for r in requests] == list(expected), 'Missing/reordered parameter requests')
        for r in requests:
            parsed = dialect.MAVLink(None).parse_buffer(bytes.fromhex(r['datagram_hex']))
            require(len(parsed) == 1 and parsed[0].get_type() == 'PARAM_REQUEST_READ' and parsed[0].param_id == r['name']
                    and parsed[0].target_system == 22 and parsed[0].target_component == 1 and parsed[0].param_index == -1,
                    'Raw parameter request differs')
            matches = [m for m in messages if m['monotonic'] >= r['monotonic'] and m['message']['mavpackettype'] == 'PARAM_VALUE'
                       and m['message']['param_id'] == r['name']]
            require(matches, 'Missing raw parameter response: '+r['name'])
            m = matches[0]; typ = result['admission']['parameter_types'][r['name']]
            require(m['message']['param_type'] == (6 if typ == 'INT32' else 9), 'Parameter wire type differs')
            raw = bytes.fromhex(m['payload_hex'])
            require(len(raw) == 25, 'Truncated parameter payload')
            value = struct.unpack('<i' if typ == 'INT32' else '<f', raw[:4])[0]
            goal = expected[r['name']] if typ == 'INT32' else struct.unpack('<f', struct.pack('<f', expected[r['name']]))[0]
            require(value == goal, 'Parameter value differs: '+r['name'])
            require(0 <= m['monotonic']-r['monotonic'] <= 10 and m['monotonic'] <= end['observed_monotonic_s'], 'Parameter read timeout')
            actual[r['name']] = value
    else:
        requests = [(r, v) for r, v in services if r['kind'] == 'parameter_get_request']
        responses = [(r, v) for r, v in services if r['kind'] == 'parameter_get_response']
        require([r['name'] for r, _ in requests] == list(expected) and len(responses) == len(requests), 'AP service record count differs')
        for (r, request), (s, response) in zip(requests, responses):
            require(request['names'] == [r['name']] and s['name'] == r['name'] and len(response['values']) == 1
                    and 0 <= s['monotonic']-r['monotonic'] <= 10, 'AP parameter service pairing differs')
            v = response['values'][0]
            require(v['type'] in (2, 3), 'AP numeric parameter type differs')
            actual[r['name']] = v['integer_value'] if v['type'] == 2 else v['double_value']
            require(actual[r['name']] == expected[r['name']], 'AP parameter value differs')
    require(actual == result['task']['hex']['parameter_readback'], 'Parameter summary differs from raw')
    context = result['task']['hex']['parameter_context']
    for r in rows:
        if begin['observed_monotonic_s'] <= r['monotonic'] <= end['observed_monotonic_s']:
            require(r['control_epoch'] == context['control_epoch'] and r['native_generation'] == context['native_generation'],
                    'Ground parameter generation changed')
            if r.get('physical_cursor'):
                require(abs(trace[r['physical_cursor']['records']-1]['vehicle'][8]) < .3, 'Airborne parameter read')
    require(end['observed_monotonic_s'] < phases['arming_completed']['observed_monotonic_s'], 'Parameter reads after arm')
    return dict(count=len(actual), values=actual, ap_service_capture='client serialized request/response, not packet attribution')


def native_delivery(root, result, data, messages, phases):
    start = phases['waypoint_accepted']['observed_monotonic_s']
    end = phases['land_accepted']['observed_monotonic_s']
    logs = result['raw_native_logs']
    require(logs, 'Native log missing')
    for name, pin in logs.items():
        require((root/name).resolve().is_relative_to(root) and digest(root/name) == pin['sha256']
                and (root/name).stat().st_size == pin['size'], 'Raw native log hash/size differs')
    if result['stack'] == 'px4':
        targets = [(r, v) for topic, values in data.items() if '/in/trajectory_setpoint' in topic for r, v in values
                   if start <= r['monotonic'] < end]
        require(targets and all(near(v['position'], [3., 2., -3.]) and near(v['yaw'], math.pi/2)
                               and all(math.isnan(x) for x in v['velocity']+v['acceleration']) for _, v in targets),
                'Raw DDS position target/axes differ')
        modes = [v for topic, values in data.items() if '/in/offboard_control_mode' in topic for r, v in values
                 if start <= r['monotonic'] < end]
        require(modes and all(v['position'] is True and not any(v[k] for k in
                ('velocity', 'acceleration', 'attitude', 'body_rate', 'thrust_and_torque', 'direct_actuator')) for v in modes),
                'Raw DDS offboard axes differ')
        received = [m for m in messages if start <= m['monotonic'] < end and m['message']['mavpackettype'] == 'POSITION_TARGET_LOCAL_NED']
        require(any(near([m['message'][k] for k in ('x', 'y', 'z')], [3., 2., -3.]) for m in received), 'No FC position-target receipt')
        import pyulog
        from pyulog import ULog
        files = [root/name for name in logs if name.endswith('.ulg')]
        require(len(files) == 1, 'Expected one ULog')
        u = ULog(str(files[0]))
        require(not u.dropouts, 'ULog has dropped records')
        by_name = {d.name: d.data for d in u.data_list if d.multi_id == 0}
        native = by_name['trajectory_setpoint']
        wire = {v['timestamp']: v for _, v in targets}
        matched = 0
        for i, t in enumerate(native['timestamp']):
            if int(t) in wire:
                v = wire[int(t)]
                require(near([native[f'position[{j}]'][i].item() for j in range(3)], v['position'])
                        and near(native['yaw'][i].item(), v['yaw']), 'Native ULog/DDS target differs')
                matched += 1
        require(matched > 1, 'Insufficient same-timestamp ULog/DDS targets')
        motors = by_name['actuator_motors']
        require(all(any(math.isfinite(float(x)) and x > 0 for x in motors[f'control[{i}]']) for i in range(6)), 'ULog six motor outputs missing')
        inputs = {r['held_packet']['time_usec']: r['input16'][:6] for r in lines(root/'physics-1ms.jsonl')
                  if r['kind'] == 'step' and r['held_packet'] is not None}
        outputs = by_name['actuator_outputs']
        for i, tick in enumerate(outputs['timestamp']):
            require(int(tick) in inputs and near(inputs[int(tick)],
                    [max(0., float(outputs[f'output[{j}]'][i])-1000)/1000 for j in range(6)]),
                    'ULog actuator channel order differs from physical wire input')
        require(by_name['vehicle_status']['arming_state'][-1] == 1 and by_name['vehicle_land_detected']['landed'][-1] == 1,
                'Native ULog final disarm/land not proven')
        return dict(dds_targets=len(targets), same_timestamp_ulog_targets=matched, six_native_motors=True,
                    same_timestamp_actuator_groups=len(outputs['timestamp']),
                    decoder_sha256=digest(Path(pyulog.__file__).with_name('core.py')), native_logs=logs,
                    boundary='Sampled ULog + MAVLink receipt; no per-packet publisher attribution or exact first acceptance tick')
    # The AP runner records global DDS requests; receipt must be corroborated by FC telemetry/BIN.
    targets = [(r, v) for r, v in data['/ap/cmd_gps_pose'] if start <= r['monotonic'] < end]
    require(targets and all(v['coordinate_frame'] == 6 and v['type_mask'] == 0x9f8 and near(v['altitude'], 3.)
                           and near(v['yaw'], 0.) for _, v in targets), 'AP global DDS target differs')
    native_states = data['/ap/wksim/local_state_v1']
    for row, target in targets:
        matches = [v for r, v in native_states if v['time_boot_us'] == round(stamp(target)*1e6)]
        require(matches, 'AP target boot stamp absent from native WksimState')
        home = matches[-1]
        lat = home['home_latitude_e7']+int(3./0.011131884502145034)
        mid = (lat+home['home_latitude_e7'])/2e7
        lon = home['home_longitude_e7']+int(2./(0.011131884502145034*math.cos(math.radians(mid))))
        lon = (lon+1800000000) % 3600000000-1800000000
        require(target['latitude'] == lat/1e7 and target['longitude'] == lon/1e7, 'AP DDS global-home binding differs')
    received = [m['message'] for m in messages if m['message']['mavpackettype'] == 'POSITION_TARGET_GLOBAL_INT'
                and start <= m['monotonic'] < end]
    require(any(m['lat_int'] == lat and m['lon_int'] == lon and m['coordinate_frame'] == 0
                and near(m['alt'], (home['home_altitude_cm']+300)/100) for m in received),
            'AP FC global target receipt differs from DDS/home')
    from pymavlink import DFReader
    files = [root/name for name in logs if name.lower().endswith('.bin')]
    require(len(files) == 1, 'Expected one AP BIN')
    reader = DFReader.DFReader_binary(str(files[0]))
    records = defaultdict(list)
    while True:
        msg = reader.recv_msg()
        if msg is None:
            break
        require(msg.get_type() != 'BAD_DATA', 'AP BIN decode error')
        if msg.get_type() in ('GUIP', 'RCOU', 'ARM'):
            records[msg.get_type()].append(msg.to_dict())
    low = phases['waypoint_accepted']['native_boot_s']*1e6
    high = phases['land_accepted']['native_boot_s']*1e6
    guided = [r for r in records['GUIP'] if low <= r['TimeUS'] < high]
    local = [m['message'] for m in messages if m['message']['mavpackettype'] == 'POSITION_TARGET_LOCAL_NED'
             and start <= m['monotonic'] < end]
    require(guided and local, 'AP native GUIP/local target receipt absent')
    # GUIP logs the accepted origin-relative NED target for default Pos mode.
    # Check each receipt against subsequent native target telemetry, no model tolerance.
    for r in guided:
        require(any(m['time_boot_ms']*1000 >= r['TimeUS'] and near([r['pX'], r['pY'], r['pZ']],
                    [m['x'], m['y'], m['z']]) for m in local), 'AP GUIP/MAVLink target differs')
    require(records['ARM'] and records['ARM'][-1]['ArmState'] == 0, 'AP BIN disarm absent')
    require(all(any(r[f'C{i}'] > 1000 for r in records['RCOU']) for i in range(1, 7)), 'AP six native motor channels absent')
    require(any(m['message']['mavpackettype'] == 'EXTENDED_SYS_STATE' and m['message']['landed_state'] == 1
                and m['monotonic'] >= phases['landed_disarmed_public']['observed_monotonic_s'] for m in messages),
            'AP native ground corroboration absent')
    return dict(dds_targets=len(targets), bin_guided_targets=len(guided), native_logs=logs,
                decoder_sha256=digest(DFReader.__file__), boundary='AP path requires real Hex evidence; synthetic tests do not prove a flight')


def process_absent(identity):
    require(type(identity['pid']) is int and identity['pid'] > 0 and type(identity['starttime_ticks']) is int
            and identity['starttime_ticks'] > 0 and identity['boot_id'] and identity['argv'] and identity['cwd'], 'Incomplete process identity')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot != identity['boot_id']:
        return True
    try:
        stat = (Path('/proc')/str(identity['pid'])/'stat').read_text()
    except FileNotFoundError:
        return True
    return int(stat[stat.rfind(')')+2:].split()[19]) != identity['starttime_ticks']


def retirement(result):
    require(result['cleanup_errors'] == [] and result['stop_kind'] == 'landed_stop', 'Unsuccessful teardown')
    for name, child in result['children'].items():
        require(child['returncode'] is not None and child['pid'] == child['identity']['pid']
                and process_absent(child['identity']), 'Owned process not retired: '+name)
    require(process_absent(result['supervisor']), 'Supervisor still alive')
    return dict(processes_checked=len(result['children'])+1, method='Current /proc boot_id + pid + starttime; never signal')


def reset_links(result, parent, parent_sha):
    link = result['cold_reset_from']
    require(link['sha256'] == parent_sha and link['run_id'] == parent['run_id'] and link['children'] == parent['children'], 'Cold reset parent binding differs')
    require(result['run_id'] != parent['run_id'] and result['run_dir'] != parent['run_dir']
            and result['task']['control_epoch'] != parent['task']['control_epoch']
            and link['control_epoch'] == parent['task']['control_epoch'], 'Cold reset reused identities/storage')
    require(result['admission']['configuration_identity'] == parent['admission']['configuration_identity'] == link['configuration_identity']
            and result['protocol_sha256'] == parent['protocol_sha256'] == protocol_for(result['stack'])[1], 'Cold reset changed configuration/budget')
    require(result['model_initialization']['initial_tick'] == 0 and parent['model_initialization']['initial_tick'] == 0, 'Cold reset tick0 missing')
    old = {(c['identity']['boot_id'], c['pid'], c['identity']['starttime_ticks']) for c in parent['children'].values()}
    for c in result['children'].values():
        require((c['identity']['boot_id'], c['pid'], c['identity']['starttime_ticks']) not in old
                and c['cwd'] == result['run_dir'], 'Cold reset reused process or native parameter directory')
    require(result['supervisor'] != parent['supervisor'], 'Cold reset reused supervisor identity')
    return dict(parent_run_id=parent['run_id'], parent_result_sha256=parent_sha, new_run_id=result['run_id'], tick0=True)


def check(root, *, require_cold_reset=False, ancestors=()):
    root = Path(root).resolve()
    report = dict(schema='wksim.hex.flight.audit.v1', root=str(root), passed=False, status='rejected', checks={}, errors=[],
                  scope='Recorded Hex native chain and 1ms physical mission; no UE, aircraft calibration, G6 or Full claim',
                  cold_reset_required=require_cold_reset, inputs_sha256={}, auditor_sha256=digest(__file__))
    def stage(name, operation):
        try:
            value = operation()
            report['checks'][name] = value
            return value
        except (OSError, ValueError, KeyError, TypeError, IndexError, ImportError, AttributeError, StopIteration, struct.error, RuntimeError) as error:
            report['errors'].append(dict(check=name, error=type(error).__name__+': '+str(error)))
            return None
    def load_result():
        value = read(root/'result.json')
        require(isinstance(value, dict), 'Result must be an object')
        return value
    result = stage('result', load_result)
    if result is None:
        return report
    report['checks']['result'] = dict(recorded_status=result.get('status'), run_id=result.get('run_id'))
    before = {str(p.relative_to(root)): digest(p) for p in root.rglob('*') if p.is_file()}
    report['inputs_sha256'] = before
    stage('identity', lambda: identity(root, result))
    p = stage('physics', lambda: physical(root, result))
    if p:
        report['checks']['physics'], steps, trace = p
    d = stage('native_decode', lambda: decode(root, result))
    if d:
        report['checks']['native_decode'], data, messages, rows, services = d
    if p and d:
        phases = stage('public_chain', lambda: phases_and_public(result, trace, data))
        if phases:
            report['checks']['public_chain'], phases = phases
            windows = stage('physical_windows', lambda: gates(result, steps, phases, data))
            if windows and any(not v['passed'] for v in windows.values()):
                report['errors'].append(dict(check='physical_windows', error='Fixed 1ms physical window threshold exceeded'))
            stage('native_parameters', lambda: parameters(result, rows, messages, services, phases, trace))
            stage('native_delivery', lambda: native_delivery(root, result, data, messages, phases))
    stage('retirement', lambda: retirement(result))
    link = result.get('cold_reset_from')
    if link:
        def cold():
            parent_path = Path(link['path']).resolve()
            require(parent_path.parent not in (*ancestors, root), 'Cyclic reset ancestry')
            parent_sha = digest(parent_path)
            parent = read(parent_path)
            detail = reset_links(result, parent, parent_sha)
            parent_audit = check(parent_path.parent, ancestors=(*ancestors, root))
            require(parent_audit['passed'], 'Parent independent audit rejected: '+json.dumps(parent_audit['errors']))
            require(digest(parent_path) == parent_sha, 'Parent mutated during audit')
            detail['parent_audit'] = parent_audit
            return detail
        stage('cold_reset', cold)
    else:
        report['checks']['cold_reset'] = dict(status='not_present', passed=False, boundary='No cold-reset flight evidence supplied')
        if require_cold_reset:
            report['errors'].append(dict(check='cold_reset', error='Required cold-reset evidence absent'))
    after = {str(p.relative_to(root)): digest(p) for p in root.rglob('*') if p.is_file()}
    if before != after:
        report['errors'].append(dict(check='immutability', error='Original evidence changed while auditing'))
    report['checks']['immutability'] = dict(passed=before == after, files=len(before))
    report['passed'] = not report['errors']
    report['status'] = 'passed' if report['passed'] else 'rejected'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-cold-reset', action='store_true')
    args = parser.parse_args()
    root, output = args.run_dir.resolve(), args.output.resolve()
    require(not output.is_relative_to(root) and not output.exists(), 'Output must be a new file outside original run')
    # Also protect all ancestors, before doing expensive decoding.
    path, seen = root/'result.json', set()
    while path.is_file():
        require(path not in seen, 'Cyclic reset ancestry')
        seen.add(path)
        require(not output.is_relative_to(path.parent), 'Output inside original/parent evidence')
        link = read(path).get('cold_reset_from')
        if not link:
            break
        path = Path(link['path']).resolve()
    report = check(root, require_cold_reset=args.require_cold_reset)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(status=report['status'], passed=report['passed'], errors=report['errors'], output=str(output))))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
