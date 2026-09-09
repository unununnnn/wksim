"""Offline #34 audit. Receiver cursors never mean native acceptance.

Run in the admitted ROS overlay after the owned flight has terminated. This tool
does not start ROS nodes, FCs, models, admission checks or motion publishers.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
BUDGET_SHA = '9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f'
ENTRY_SHA = 'debd99a2b8c245608dd04bdaee61a9b9bc0e2c7240771c973eedec7c673c03c3'
ENTRY_PATH = 'Simulator/wksim_runtime/attitude-entry-v1.json'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def lines(path):
    with Path(path).open() as stream:
        for number, line in enumerate(stream, 1):
            require(line.endswith('\n'), f'Incomplete JSONL record {path}:{number}')
            yield json.loads(line)


def angle(value):
    return math.remainder(value, 2*math.pi)


def enu(v):
    return dict(time=v[2], position=(v[7], v[6], -v[8]), velocity=(v[4], v[3], -v[5]),
                attitude=(v[9], -v[10], angle(math.pi/2-v[11])))


def window(states, start, end):
    """Fixed closed 1ms window; no interpolation, phase shift or best-window scan."""
    lo, hi = math.ceil(start*1000-1e-7), math.floor(end*1000+1e-7)
    require(1 <= lo < hi <= len(states), 'Incomplete fixed physical window')
    return states[lo-1:hi]


def physical_evidence(root, stack):
    trace = list(lines(root/'truth.jsonl'))
    trace_ticks = {round(r['time']*1000): r for r in trace}
    require(len(trace_ticks) == len(trace) and trace, 'Duplicate/empty 50Hz truth')
    states, motors = [], []
    first = last = None
    group, substep, held, count = 0, 0, None, 0
    for row in lines(root/'physics-1ms.jsonl'):
        if row['kind'] == 'start':
            require(first is None and not states, 'Repeated physical start')
            first = row
            require(row['schema'] == 'wksim.attitude.physics.v1' and row['initial_tick'] == 0
                    and row['dt_s'] == .001, 'Physical schema/initial grid differs')
        elif row['kind'] == 'step':
            require(first is not None and last is None, 'Step outside physical start/end')
            v, command = row['output120'], row['input16']
            require(row['tick'] == len(states)+1 and len(v) == 120 and len(command) == 16
                    and all(math.isfinite(x) for x in v+command)
                    and all(0 <= x <= 1 for x in command) and command[4:] == [0.]*12
                    and abs(v[2]-row['tick']*.001) < 1e-8, 'Physical tick/input/output invalid')
            expected_steps = 1 if stack == 'arducopter' else 4
            require(row['group_steps'] == expected_steps, 'Adapter group length differs')
            if row['substep'] == 0:
                require(substep == count and row['group'] == group+1, 'Incomplete or reordered physical group')
                group, substep, held, count = row['group'], 0, command, row['group_steps']
            require(row['group'] == group and row['substep'] == substep and command == held,
                    'Group input not held or substep missing')
            substep += 1
            states.append(enu(v)); motors.append(command[:4])
            if row['tick'] in trace_ticks:
                r = trace_ticks.pop(row['tick'])
                require(r['vehicle'] == v[:60] and r['sensor'] == v[60:90] and r['time'] == v[2],
                        '50Hz truth differs from original 1ms output')
                expected = ([max(0, x-1000)/1000 for x in r['pwm'][:4]]+[0.]*12
                            if stack == 'arducopter' else r['controls'])
                require(command == expected, '50Hz actuator/PWM differs from held physical input')
        elif row['kind'] == 'end':
            require(last is None and row['ticks'] == len(states) and row['groups'] == group
                    and substep == count, 'Physical terminal/group incomplete')
            last = row
        else:
            raise ValueError('Unknown physical record')
    require(first and last and states and not trace_ticks, 'Missing physical boundary or trace samples')
    require(all(a['time'] < b['time'] for a, b in zip(trace, trace[1:])), '50Hz time regressed')
    require(first['observer_sha256'] == digest(root/'run-source/tools/attitude_physics.py'),
            'Executed observer differs from raw physical header')
    return dict(ticks=len(states), groups=group, trace_samples=len(trace), initial=first,
                interval_s=.001, raw_actuator_packet_capture=False), states, motors, trace


def retained_identity(root, result):
    admission = read(root/'admission.json')
    require(admission == result['admission'] and admission['ok'] and admission['experimental']
            and not admission['production_admitted'] and not admission['flown']
            and admission['task_profile'] == 'attitude_thrust_v1', 'Candidate admission differs')
    require(read(root/'config.json') == result['config'] == admission['config'], 'Run config differs')
    require(result['experimental'] and not result['production_admitted'], 'Candidate scope differs')
    identities = admission['identities']
    require(identities['flight_budget']['sha256'] == BUDGET_SHA
            and digest(REPO/'work/ap-attitude-stage-20260909/flight-budget.json') == BUDGET_SHA,
            'Frozen budget SHA differs')
    sources = result['source_sha256']
    for name, checksum in sources.items():
        require(digest(root/'run-source'/name) == checksum, 'Retained executed source differs: '+name)
    require(result['source_unchanged'], 'Executed source identity changed')
    post = read(root/'postflight-admission.json')
    require(post['ok'] and all(post['identities'][k] == identities[k] for k in
            ('ap','px4','model_build','native','control','setup_sha256')),
            'Postflight candidate seals differ')
    before,after = identities['source_sha256'],post['identities']['source_sha256']
    require(all(after.get(k) == v for k,v in before.items())
            and all(sources.get(k) == v for k,v in after.items() if k not in before),
            'Postflight source additions were not sealed before execution')
    stack = result['stack']
    firmware = identities['ap' if stack == 'arducopter' else 'px4']
    agent = identities['baseline'][stack+'_agent']
    for name, pin, checksum in [('fc',firmware,result['launched_binary_sha256']),
                                ('agent',agent,result['launched_agent_sha256'])]:
        child = result['children'][name]
        require(child['argv'] == result['launch_plan'][name] and child['argv'][0] == pin['path']
                and child['executable'] == pin['path'] and checksum == pin['sha256'] == digest(pin['path']),
                'Actual binary/argv differs: '+name)
        require(pin['path'] in (root/(name+'.maps')).read_text(), 'Actual binary absent from maps: '+name)
    require(result['actual_control_sha256'] == identities['control']['installed_python_hashes'],
            'Actual installed control files differ')
    for name,checksum in result['actual_control_sha256'].items():
        require(digest(Path(identities['control']['package'])/name)==checksum,'Installed candidate changed: '+name)
    for name in ('physics','control'):
        require(result['children'][name]['argv'] == result['launch_plan'][name], 'Actual argv differs: '+name)
    controls = result['children']['control']['argv']
    require('native_attitude_profile:=attitude_thrust_v1' in controls
            and 'enable_external_attitude:=true' in controls, 'Explicit attitude switches missing')
    require(admission['library'] in (root/'physics.maps').read_text(), 'Admitted model not loaded')
    require(digest(admission['library'])==identities['model_build']['library_sha256'],
            'Actual model library differs from admitted build')
    if stack == 'arducopter':
        argv = result['children']['fc']['argv']
        require(argv[argv.index('--speedup')+1] == '1'
                and (root/'attitude.parm').read_text() == 'GUID_OPTIONS 8\nGUID_TIMEOUT 3\nLOG_DISARMED 1\n'
                    + ('PSC_ANGLE_MAX 10\n' if result['task']['attitude_thrust'].get('entry_contract_sha256') else ''),
                'AP candidate explicit parameter/speedup differs')
        if result['task']['attitude_thrust'].get('entry_contract_sha256'):
            candidate_parameters(root,result)
    else:
        require(result['launch_plan']['fc_environment']['PX4_SIM_SPEED_FACTOR'] == '1', 'PX4 speedup differs')
    return dict(source_files=len(sources), firmware=firmware, control_manifest=identities['control']['manifest_sha256'],
                model_library=admission['library'], production_admitted=False,
                original_candidate_unchanged=result['candidate_unchanged'],
                postflight_added_presealed_sources=sorted(set(after)-set(before)))


def observer_equivalence(root,result):
    directory=REPO/'validation/attitude-physics-equivalence-20260909'
    summary=read(directory/'summary.json');protocol=read(directory/'protocol.json')
    for name,checksum in summary['files_sha256'].items():
        require(digest(directory/name)==checksum,'Observer equivalence artifact changed')
    original=list(lines(directory/'original.jsonl'));observed=list(lines(directory/'observed.jsonl'))
    require(original==observed and len(original)==200,'Observer controlled replay differs')
    raw=list(lines(directory/'observed.raw.jsonl'))
    require(len(raw)==802 and raw[-1]['ticks']==800,'Observer equivalence grid incomplete')
    for tick,row in enumerate(raw[1:-1],1):
        group=(tick-1)//4
        require(row['tick']==tick and row['group']==group+1 and row['substep']==(tick-1)%4
                and row['input16']==original[group]['input'],'Observer equivalence input/group differs')
        if tick%4==0:
            require(row['output120']==original[group]['output'],'Observer equivalence final state differs')
    require(protocol['observer_sha256']==digest(root/'run-source/tools/attitude_physics.py')
            and protocol['library_sha256']==result['admission']['identities']['model_build']['library_sha256'],
            'Observer replay used another observer/model')
    return dict(groups=200,exact_output_values=24000,raw_steps=800,scope='Controlled original-vs-observed replay, not flight PASS')


def phase_evidence(result, trace):
    values = result['task']['attitude_thrust']['phases']
    phases = {}
    previous = 0
    for p in values:
        require(p['phase'] not in phases, 'Duplicate phase: '+p['phase'])
        phases[p['phase']] = p
        cursor = p['physical_cursor']
        if cursor is None:
            continue
        n = cursor['records']
        require(previous <= n <= len(trace) and n > 0 and trace[n-1]['time'] == cursor['final_time']
                and -trace[n-1]['vehicle'][8] == cursor['final_height_m'], 'Relabelled phase physical cursor')
        previous = n
    require(all(a['observed_monotonic_s'] < b['observed_monotonic_s'] for a,b in zip(values,values[1:])),
            'Phase monotonic time regressed')
    return phases


def errors(state, anchor, yaw):
    a = state['attitude']
    return (math.dist(state['position'], anchor), math.hypot(*state['velocity']),
            math.degrees(max(abs(a[0]),abs(a[1]))), math.degrees(abs(angle(a[2]-yaw))))


def fixed_metrics(states, phases, calibration):
    """Check precisely the online-declared windows against every recorded 1ms state."""
    reports = {}
    def fixed(label):
        p = phases[label+'_begin']
        return p['physical_start'], p['physical_start']+p['duration_seconds']
    def bounds(label, limits, anchor, yaw, start, end):
        samples = window(states,start,end)
        maxima = tuple(max(v) for v in zip(*(errors(s,anchor,yaw) for s in samples)))
        reports[label] = dict(start_s=start,end_s=end,samples=len(samples),max_position_m=maxima[0],
            max_speed_mps=maxima[1],max_tilt_deg=maxima[2],max_yaw_error_deg=maxima[3],
            passed=all(a <= b+1e-9 for a,b in zip(maxima,limits)))
    anchor, yaw = calibration['anchor'], calibration['yaw']
    lo, hi = fixed('hover_observation')
    require(abs(hi-lo-3) < 1e-8, 'Hover window differs from frozen 3s')
    bounds('hover_observation',(.25,.15,2,3),(2,3,3),0,lo,hi)
    entry = phases['entry_end']
    bounds('entry',(.25,.15,2,3),(2,3,3),0,entry['stable_since'],entry['physical_cursor']['final_time'])
    require(entry['physical_cursor']['final_time']-entry['stable_since'] >= 2, 'Entry dwell short')
    lo, hi = fixed('level_calibration')
    require(abs(hi-lo-2) < 1e-8, 'Calibration duration differs')
    samples = window(states,lo,hi)
    height = window(states,phases['level_calibration_offered']['physical_cursor']['final_time']-.001,
                    phases['level_calibration_offered']['physical_cursor']['final_time'])[-1]['position'][2]
    drift = max(abs(s['position'][2]-height) for s in samples)
    speed = max(abs(s['velocity'][2]) for s in samples)
    reports['level_calibration'] = dict(start_s=lo,end_s=hi,samples=len(samples),max_vertical_drift_m=drift,
        max_vertical_speed_mps=speed,passed=drift <= .3 and speed <= .2)
    if 'attitude_tracking_begin' in phases:
        lo,hi = fixed('attitude_tracking')
        start = phases['attitude_settling_begin']['physical_start']
        require(abs(lo-start-.5) < 1e-8 and abs(hi-lo-.4) < 1e-8, 'Attitude settle/dwell differs')
        completed = 'attitude_tracking_end' in phases
        actual_hi = hi if completed else min(hi, phases.get('failure_land_accepted',phases['attitude_tracking_begin'])['physical_cursor']['final_time'])
        samples = window(states,lo,actual_hi)
        maxima = [max(math.degrees(abs(angle(s['attitude'][i]-target))) for s in samples)
                  for i,target in enumerate((math.radians(5),0,yaw))]
        reports['attitude_tracking'] = dict(start_s=lo,end_s=actual_hi,required_end_s=hi,
            completed=completed,samples=len(samples),max_errors_deg=maxima,
            passed=completed and all(x <= limit for x,limit in zip(maxima,(2,2,3))))
        if 'attitude_remaining_begin' in phases:
            last_lo,last_hi=fixed('attitude_remaining')
            require(abs(last_lo-start-.9)<1e-8 and abs(last_hi-start-1.)<1e-8,
                    'Frozen total attitude duration differs')
    if 'thrust_step_begin' in phases:
        lo,hi = fixed('thrust_step')
        require(abs(hi-lo-.5) < 1e-8, 'Thrust duration differs')
        baseline=phases['thrust_baseline_begin'];baseline_end=phases['thrust_baseline_end']
        require(baseline['duration_seconds']==.2
                and baseline_end['physical_cursor']['final_time']>=baseline['physical_start']+.2-1e-9
                and baseline_end['physical_cursor']['final_time']<=lo
                and baseline_end['observed_monotonic_s']<phases['thrust_step_offered']['observed_monotonic_s'],
                'Original full preceding thrust baseline differs')
        before = window(states,lo-.2,lo)
        after = window(states,hi-.1,hi)
        delta = statistics.mean(s['velocity'][2] for s in after)-statistics.mean(s['velocity'][2] for s in before)
        reports['thrust_step'] = dict(start_s=lo,end_s=hi,preceding_samples=len(before),final_samples=len(after),
            up_velocity_increase_mps=delta,passed=delta >= .05)
    for label in ('calibration_recovery','attitude_recovery','thrust_recovery'):
        if label+'_recovered_end' not in phases:
            if label+'_offered' in phases:
                offered=phases[label+'_offered'];end=phases.get('failure_land_accepted',list(phases.values())[-1])
                lo,hi=offered['physical_cursor']['final_time'],end['physical_cursor']['final_time']
                if hi>lo:
                    bounds(label,(.4,.3,3,3),offered['payload']['position_ref'],offered['payload']['yaw_ref'],lo,hi)
                    reports[label].update(completed=False,passed=False,required_dwell_s=1.5,timeout_s=8)
            continue
        end = phases[label+'_recovered_end']; offered = phases[label+'_offered']
        a = offered['payload']['position_ref']; heading = offered['payload']['yaw_ref']
        start,end_time = end['stable_since'],end['physical_cursor']['final_time']
        require(end_time-start >= 1.5 and end_time-offered['physical_cursor']['final_time'] <= 8,
                'Recovery dwell/timeout differs: '+label)
        bounds(label,(.4,.3,3,3),a,heading,start,end_time)
    envelope_start = phases['position_baseline_reached']['physical_cursor']['final_time']
    envelope_end = phases.get('thrust_recovery_recovered_end',phases.get('failure_land_accepted',list(phases.values())[-1]))['physical_cursor']['final_time']
    freeze = phases['hover_candidate_frozen']['physical_cursor']['final_time']
    samples = window(states,envelope_start,envelope_end)
    violations = [s['time'] for s in samples if not (1.5 <= s['position'][2] <= 4.5)
        or math.dist(s['position'],(2,3,3) if s['time'] < freeze else anchor) > 4
        or max(abs(x) for x in s['attitude'][:2]) > math.radians(15)]
    reports['abort_envelope'] = dict(samples=len(samples),violations=len(violations),
        first_violation_s=violations[0] if violations else None,passed=not violations)
    return reports


def ulog(path):
    """Use PX4's pyulog parser; preserve actual decoder package identity."""
    import importlib.metadata
    import pyulog
    from pyulog import ULog
    wanted = ['vehicle_attitude_setpoint','vehicle_attitude','actuator_motors','actuator_outputs',
              'vehicle_rates_setpoint','sensor_combined','vehicle_thrust_setpoint']
    parsed = ULog(str(path), wanted)
    data = defaultdict(list)
    for dataset in parsed.data_list:
        for i in range(len(dataset.data['timestamp'])):
            row = {k:v[i].item() for k,v in dataset.data.items()}
            row['multi_id'] = dataset.multi_id
            for key in ('q_d','q','xyz','control','output'):
                fields = [k for k in row if k.startswith(key+'[')]
                if fields:
                    row[key] = [row[k] for k in sorted(fields,key=lambda x:int(x.split('[')[1][:-1]))]
            data[dataset.name].append(row)
    return dict(data), dict(path=str(path),sha256=digest(path),
        dropout_durations_ms=[d.duration for d in parsed.dropouts],
        decoder=dict(version=importlib.metadata.version('pyulog'),path=pyulog.__file__,
                     core_sha256=digest(Path(pyulog.__file__).with_name('core.py'))),
        topics={d.name:dict(samples=len(d.data['timestamp']),fields=list(d.data)) for d in parsed.data_list})


def q_from_euler(r,p,y):
    cr,sr,cp,sp,cy,sy = math.cos(r/2),math.sin(r/2),math.cos(p/2),math.sin(p/2),math.cos(y/2),math.sin(y/2)
    return [cr*cp*cy+sr*sp*sy,sr*cp*cy-cr*sp*sy,cr*sp*cy+sr*cp*sy,cr*cp*sy-sr*sp*cy]


def native_q(q):
    w,x,y,z = q; k = math.sqrt(.5)
    return [k*(w+z),k*(x+y),k*(x-y),k*(w-z)]


def q_distance(a,b):
    return min(math.dist(a,b),math.dist(a,[-x for x in b]))


def decode_native(root,result):
    import importlib
    from rclpy.serialization import deserialize_message, serialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rosidl_runtime_py.set_message import set_message_fields
    from prometheus_msgs.msg import TextInfo
    from wksim_msgs.msg import CommandRequest, SetupRequest, SessionState
    from px4_msgs.msg import VehicleAttitudeSetpoint, OffboardControlMode, VehicleAttitude, TrajectorySetpoint, VehicleControlMode
    from ardupilot_msgs.msg import WksimAttitudeTarget, WksimState, GlobalPosition
    from Simulator.wksim_runtime.telemetry_dialect import load_dialect
    from Simulator.wksim_runtime.evidence import json_value
    from Simulator.wksim_runtime.joint_profile import package_digest
    identities=result['admission']['identities']
    for name in ('px4_msgs','prometheus_msgs','wksim_msgs','ardupilot_msgs'):
        module=importlib.import_module(name)
        require(module.__file__==identities['candidate_imports']['import_paths'][name],
                'Actual ROS decoder import path differs: '+name)
        if name!='ardupilot_msgs':
            pin=identities['baseline']['message_packages'][name]
            require(package_digest(pin['prefix'],complete=pin.get('complete_snapshot',False))==pin['sha256'],
                    'Actual generated message codec bytes differ: '+name)
    ap_root=Path(identities['candidate_imports']['import_paths']['ardupilot_msgs']).parents[7]
    for name,checksum in identities['native']['overlay_hashes'].items():
        if name.startswith('install/'):
            require(digest(ap_root/name)==checksum,'AP generated message install changed: '+name)
    types = {'/ap/wksim/attitude_target_v1':WksimAttitudeTarget,'/ap/wksim/local_state_v1':WksimState,
             '/ap/cmd_gps_pose':GlobalPosition}
    for suffix,cls in [('v2/command',CommandRequest),('v2/setup',SetupRequest),('v2/state',SessionState),('text_info',TextInfo)]:
        types['/uav1/prometheus/'+suffix] = cls
    for direction,name,cls in [('in','vehicle_attitude_setpoint',VehicleAttitudeSetpoint),
        ('in','offboard_control_mode',OffboardControlMode),('out','vehicle_attitude',VehicleAttitude),
        ('in','trajectory_setpoint',TrajectorySetpoint),('out','vehicle_control_mode',VehicleControlMode)]:
        version = getattr(cls,'MESSAGE_VERSION',0)
        types['/wksim_px4_21/fmu/'+direction+'/'+name+(f'_v{version}' if version else '')] = cls
    dialect, identity = load_dialect(result['stack'])
    decoder = dialect.MAVLink(None)
    data,messages,recorded_messages,discovery = defaultdict(list),[],[],[]
    target = 241 if result['stack'] == 'arducopter' else 22
    peer = None
    last = 0
    for row in lines(root/'attitude-native.jsonl'):
        require(row['run_id'] == result['run_id'] and row['monotonic'] >= last, 'Raw identity/time differs')
        last = row['monotonic']
        if row['kind'] == 'dds':
            require(row['per_message_publisher_gid_available'] is False and 'publisher_gid' not in row
                    and type(row['source_timestamp']) is int and type(row['received_timestamp']) is int,
                    'Fabricated GID or DDS metadata differs')
            value = deserialize_message(bytes.fromhex(row['cdr_hex']),types[row['topic']])
            data[row['topic']].append((row,dict(message_to_ordereddict(value))))
        elif row['kind'] == 'mavlink_rx':
            require(row['peer'][0] == '127.0.0.1', 'Unexpected native telemetry address')
            if peer is not None and row['peer'] != peer:
                continue
            for message in decoder.parse_buffer(bytes.fromhex(row['datagram_hex'])) or []:
                if message.get_srcSystem() == target and message.get_srcComponent() == 1:
                    if peer is None:
                        if message.get_type() != 'HEARTBEAT' or result['stack']=='px4' and row['peer'][1]!=18591:
                            continue
                        peer = row['peer']
                    messages.append((row,message.to_dict()))
        elif row['kind'] == 'mavlink_decoded':
            recorded_messages.append(row)
        elif row['kind'] == 'dds_discovery_publishers':
            discovery.append(row)
        elif row['kind'] == 'telemetry_identity':
            require(row['dialect'] == identity, 'Actual raw telemetry decoder identity differs')
    require(len(messages) == len(recorded_messages), 'Raw/online native decoded counts differ')
    for (_,actual),recorded in zip(messages,recorded_messages):
        require(json_value(actual) == recorded['message'], 'MAVLink datagram decoded differently')
    public = sorted(data['/uav1/prometheus/v2/command']+data['/uav1/prometheus/v2/setup'],key=lambda x:x[1]['request_id'])
    requests = result['task']['request_envelopes']
    require(len(public) == len(requests), 'Raw public request count differs')
    for (row,value),request in zip(public,requests):
        cls = CommandRequest if 'command' in request else SetupRequest
        expected = cls(); set_message_fields(expected,request)
        # Compare decoded values, not CDR padding bytes.
        require(value == dict(message_to_ordereddict(deserialize_message(serialize_message(expected),cls))),
                'Actual public CDR differs from task request')
    events=[json.loads(m['message']) for _,m in data['/uav1/prometheus/text_info']]
    for _,request in public:
        require(request['version']==1 and request['run_id']==result['run_id']
                and request['control_epoch']==result['task']['control_epoch'], 'Raw request authority differs')
        matches=[e for e in events if e.get('run_id')==request['run_id']
                 and e.get('control_epoch')==request['control_epoch'] and e.get('request_id')==request['request_id']]
        require(any(e.get('event')==('command_accepted' if 'command' in request else 'setup_completed') for e in matches),
                'Public command acceptance/setup completion absent from raw CDR')
    require(discovery and all(not any('publisher_gid' in x for x in entries)
            for graph in discovery for entries in graph['publishers'].values()), 'Discovery evidence missing')
    return data,messages,recorded_messages,dict(dds_records=sum(len(x) for x in data.values()),
        topics={k:len(v) for k,v in data.items()},public_requests=len(public),mavlink_messages=len(messages),
        discovery_records=len(discovery),per_message_publisher_gid_available=False,dialect=identity)


def px4_parameter_value(message):
    require(message['param_type'] in (6,9),'Unsupported PX4 parameter type')
    return (struct.unpack('<i',struct.pack('<f',message['param_value']))[0]
            if message['param_type']==6 else message['param_value'])


def entry_contract(root,result):
    """A missing report field cannot downgrade a run whose retained source uses the gate."""
    claimed=result['task']['attitude_thrust'].get('entry_contract_sha256')
    retained=root/'run-source'/ENTRY_PATH
    task=root/'run-source/Simulator/wksim_runtime/attitude_task.py'
    present=claimed is not None or retained.exists() or 'ENTRY_CONTRACT_SHA' in task.read_text()
    if not present:
        return dict(status='historical_without_entry_contract',required=False)
    require(claimed==ENTRY_SHA and result['source_sha256'].get(ENTRY_PATH)==ENTRY_SHA
            and digest(retained)==ENTRY_SHA, 'Entry contract report/run-source seal differs')
    contract=read(retained)
    require(contract['original_budget_sha256']==BUDGET_SHA, 'Entry changed original budget')
    return dict(status='sealed',required=True,sha256=ENTRY_SHA,contract=contract)


def candidate_parameters(root,result):
    expected={'GUID_OPTIONS':8,'GUID_TIMEOUT':3,'LOG_DISARMED':1,'PSC_ANGLE_MAX':10}
    actual={}
    for line in (root/'attitude.parm').read_text().splitlines():
        name,value=line.split()
        require(name not in actual,'Duplicate candidate parameter')
        actual[name]=float(value)
    require(actual==expected==result['experimental_parameters'],'Recorded candidate parameter file differs')
    argv=result['children']['fc']['argv']
    defaults=argv[argv.index('--defaults')+1].split(',')
    require(defaults.count(str(root/'attitude.parm'))==1
            and defaults[-2:]==[str(root/'attitude.parm'),str(root/'dds.parm')],
            'Actual AP defaults do not load candidate file before DDS file')
    require((root/'dds.parm').read_text()=='DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n',
            'Later AP defaults override candidate parameters')
    # Inspect every actual earlier defaults file; candidate overrides are explicit,
    # and baseline position-angle configuration must remain the original zero.
    for filename in defaults[:-2]:
        for line in Path(filename).read_text().splitlines():
            fields=line.split('#',1)[0].replace(',',' ').split()
            if fields and fields[0] in ('PSC_ANGLE_MAX','ATC_ANGLE_MAX'):
                require(float(fields[1])==(0 if fields[0]=='PSC_ANGLE_MAX' else 30),
                        'Original AP angle baseline was changed')
    return dict(candidate=actual,actual_defaults=defaults)


def entry_gate_evidence(result,data,recorded,phases,states,discovery,contract):
    """Rebuild the declared gate from decoded wire records, never scan a better window."""
    if result['stack']!='px4':
        require(not any('_preconditioning_' in name for name in phases),'AP acquired a PX4-only gate')
        return dict(status='not_applicable',stages=[])
    calibration=result['task']['attitude_thrust']['calibration']
    completed=result['task']['attitude_thrust']['status']=='completed_pending_raw_audit'
    gates=(('level_calibration_entry','hover_candidate_frozen','level_calibration','level_calibration',2),
           ('attitude_step_entry','calibration_recovery_recovered_end','attitude_step','attitude_settling',.5),
           ('thrust_baseline_entry','attitude_recovery_recovered_end','thrust_baseline','thrust_baseline',.2))
    mode_topics=[name for name in data if '/out/vehicle_control_mode' in name]
    mode_topic=mode_topics[0] if mode_topics else None
    modes=data.get(mode_topic,[])
    require(all(a['timestamp']<b['timestamp'] for (_,a),(_,b) in zip(modes,modes[1:])),
            'Raw VehicleControlMode timestamp did not advance')
    targets=[pair for name,rows in data.items() if '/in/vehicle_attitude_setpoint' in name for pair in rows]
    offboard=[pair for name,rows in data.items() if '/in/offboard_control_mode' in name for pair in rows]
    public=data.get('/uav1/prometheus/v2/command',[])
    reports=[]
    for label,previous,next_label,duration_label,duration in gates:
        begin=phases.get(label+'_preconditioning_begin')
        complete=phases.get(label+'_preconditioning_complete')
        require(begin is not None or next_label+'_offered' not in phases,'Required entry gate missing: '+label)
        if begin is None:
            reports.append(dict(label=label,status='not_reached'));continue
        require(previous in phases and phases[previous]['observed_monotonic_s']<begin['observed_monotonic_s'],
                'Entry occurred before required previous phase: '+label)
        start=begin['physical_start']; wall_start=begin['observed_monotonic_s']
        require(start==begin['physical_cursor']['final_time'] and begin['physical_deadline']==start+2
                and begin['wall_timeout_seconds']==10,'Entry deadline declaration differs')
        require(calibration and len(begin['neutral_attitude'])==4
                and all(abs(a-b)<1e-9 for a,b in zip(begin['neutral_attitude'],(0,0,calibration['yaw'],calibration['hover']))),
                'Entry changed frozen neutral target')
        if complete is None:
            require(next_label+'_offered' not in phases,'Task continued after incomplete entry')
            reports.append(dict(label=label,status='incomplete'));continue
        end=complete['physical_cursor']['final_time']; wall_end=complete['observed_monotonic_s']
        require(0<=end-start<=2 and 0<wall_end-wall_start<10,'Entry completion exceeded frozen deadline')
        offered=phases[label+'_neutral_offered']
        observed=phases[label+'_neutral_native_observed']
        requests=[(row,value) for row,value in public if value['command']['command_id']==offered['command_id']]
        require(len(requests)==1,'Neutral raw public request missing/ambiguous')
        request_row,request=requests[0]
        frozen_command('level_calibration',request['command'],calibration)
        require(wall_start<=offered['observed_monotonic_s']<=request_row['monotonic']
                <=observed['observed_monotonic_s']<wall_end,'Neutral public/native phase order differs')
        q=native_q(q_from_euler(0,0,calibration['yaw'])); hover=calibration['hover']
        raw_inputs=[(row,m) for row,m in targets if request_row['monotonic']<=row['monotonic']<=observed['observed_monotonic_s']
                    and q_distance(m['q_d'],q)<1e-5 and abs(-m['thrust_body'][2]-hover)<1e-5]
        require(raw_inputs,'No new raw neutral native publication')
        input_row,native=raw_inputs[0]
        stamp=native['timestamp']
        require(complete['offered_native_stamp']==stamp==observed['native_target']['native_source_stamp']
                and observed['native_target']['physical_time']==input_row['physical_cursor']['final_time']
                and native['thrust_body'][:2]==[0.,0.], 'Declared neutral native observation differs')
        ocm=[m for row,m in offboard if m['timestamp']==stamp and wall_start<=row['monotonic']<=wall_end]
        require(len(ocm)==1 and ocm[0]['attitude'] and not any(ocm[0][key] for key in
                ('position','velocity','acceleration','body_rate','thrust_and_torque','direct_actuator')),
                'Raw neutral OffboardControlMode axes differ')
        declared=complete['control_mode']
        selected=[(row,m) for row,m in modes if wall_start<=row['monotonic']<=wall_end
                  and m['timestamp']==declared['native_source_stamp']]
        require(len(selected)==1,'Declared control mode absent from new raw CDR')
        mode_row,mode=selected[0]
        available_modes=[pair for pair in modes if wall_start<=pair[0]['monotonic']<=wall_end]
        require(selected[0]==available_modes[-1],'Entry selected an older passing control mode')
        require(mode==declared['flags'] and mode['timestamp']>=stamp
                and mode_row['source_timestamp']==declared['source_timestamp']
                and mode_row['received_timestamp']==declared['received_timestamp']
                and mode_row['physical_cursor']['final_time']==declared['physical_time']
                and 0<=end-declared['physical_time']<=.75
                and all(mode.get(k) is True for k in contract['required_true'])
                and all(mode.get(k) is False for k in contract['required_false']),
                'Raw control-mode flags/timestamp/freshness differ')
        selected_targets=[r for r in recorded if r['message']['mavpackettype']=='ATTITUDE_TARGET'
            and wall_start<=r['monotonic']<=wall_end and
            dict(physical_time=r['physical_time'],native_boot_s=r['message']['time_boot_ms']/1000,
                 thrust=r['message']['thrust'],quaternion=r['message']['q'])==complete['actual_attitude_target']]
        require(len(selected_targets)==1,'Declared actual target absent from raw MAVLink')
        target=selected_targets[0]; message=target['message']
        require(message['time_boot_ms']*1000>mode['timestamp'] and q_distance(message['q'],q)<1e-5
                and abs(message['thrust']-hover)<1e-5 and 0<=end-target['physical_time']<=.25,
                'Actual neutral target is stale, wrong, or not strictly after control mode')
        eligible=[r for r in recorded if r['message']['mavpackettype']=='ATTITUDE_TARGET'
            and wall_start<=r['monotonic']<=wall_end and r['message']['time_boot_ms']*1000>mode['timestamp']
            and 0<=end-r['physical_time']<=.25 and abs(r['message']['thrust']-hover)<1e-5
            and q_distance(r['message']['q'],q)<1e-5]
        require(target==eligible[0],'Entry did not retain first eligible raw target')
        graphs=[r for r in discovery if r['monotonic']<=wall_end]
        require(graphs,'Control-mode publisher discovery missing')
        active=[r for r in graphs if r['monotonic']>=wall_start]
        prior=[r for r in graphs if r['monotonic']<wall_start]
        if prior:active.insert(0,prior[-1])
        endpoints=complete['publisher_endpoints']
        require(len(endpoints)==1 and bool(bytes.fromhex(endpoints[0]['endpoint_gid']))
                and any(bytes.fromhex(endpoints[0]['endpoint_gid']))
                and all(r['publishers'].get(mode_topic)==endpoints for r in active),
                'Control-mode discovery identity is missing, competing, or changed')
        samples=window(states,start,end)
        require(all(1.5<=s['position'][2]<=4.5 and math.dist(s['position'],calibration['anchor'])<=4
                    and max(abs(a) for a in s['attitude'][:2])<=math.radians(15) for s in samples),
                'Original abort envelope violated during entry')
        if next_label+'_offered' in phases:
            next_offer=phases[next_label+'_offered']
            require(wall_end<next_offer['observed_monotonic_s']
                    and end<=next_offer['physical_cursor']['final_time'],'Original case began before gate complete')
        if duration_label+'_begin' in phases:
            original=phases[duration_label+'_begin']
            require(original['physical_start']>=end and original['duration_seconds']==duration,
                    'Preconditioning consumed the original full window')
            if next_label!='thrust_baseline':
                require(original['physical_start']==phases[next_label+'_native_observed']['native_target']['physical_time'],
                        'Original attitude case origin shifted from native observation')
        if completed:
            require(all(name in phases for name in (next_label+'_offered',next_label+'_native_observed',
                duration_label+'_begin',duration_label+'_end')), 'Completed task omitted original full window')
            original=phases[duration_label+'_begin']; terminal=phases[duration_label+'_end']
            require(terminal['physical_cursor']['final_time']>=original['physical_start']+duration-1e-9,
                    'Original full window ended early')
            if next_label=='thrust_baseline':
                require(terminal['observed_monotonic_s']<phases['thrust_step_offered']['observed_monotonic_s']
                        and terminal['physical_cursor']['final_time']<=phases['thrust_step_begin']['physical_start'],
                        'Thrust step consumed the full preceding baseline')
            if next_label=='attitude_step':
                require('attitude_remaining_begin' in phases and 'attitude_remaining_end' in phases,
                        'Completed attitude step omitted the full one-second duration')
                require(phases['attitude_remaining_end']['physical_cursor']['final_time']
                        >=original['physical_start']+1.-1e-9, 'Original one-second attitude step ended early')
        reports.append(dict(label=label,status='verified',physical_start=start,physical_end=end,
            wall_elapsed_s=wall_end-wall_start,neutral_native_stamp=stamp,control_mode_stamp=mode['timestamp'],
            actual_target_stamp=message['time_boot_ms']*1000,physical_samples=len(samples),
            publisher_discovery=endpoints,per_message_publisher_gid_available=False))
    if completed:
        require(all(r['status']=='verified' for r in reports),'Completed task lacks all three verified gates')
    return dict(status='verified_reached_stages',stages=reports)


def parameters(root,result,messages):
    values = result['task']['attitude_thrust']['parameter_readback']
    if result['stack'] != 'px4':
        from rcl_interfaces.srv import GetParameters
        from rclpy.serialization import deserialize_message
        decoded={}
        for row in lines(root/'attitude-native.jsonl'):
            if row['kind'] != 'parameter_get_response':
                continue
            message=deserialize_message(bytes.fromhex(row['serialized_cdr_hex']),GetParameters.Response)
            require(len(message.values)==1 and message.values[0].type in (2,3), 'AP parameter schema differs')
            p=message.values[0]
            decoded[row['name']]=p.integer_value if p.type==2 else p.double_value
        require(decoded==values and decoded['GUID_OPTIONS']==8 and decoded['GUID_TIMEOUT']==3,
                'AP actual parameter response differs')
        native_parms={}
        if result['task']['attitude_thrust'].get('entry_contract_sha256'):
            require(decoded.get('PSC_ANGLE_MAX')==10 and decoded.get('ATC_ANGLE_MAX')==30,
                    'Actual AP recovery parameter readback differs')
            from pymavlink import mavutil
            for path in root.rglob('*.BIN'):
                log=mavutil.mavlink_connection(str(path))
                while True:
                    row=log.recv_match(type='PARM')
                    if row is None:break
                    value=row.to_dict();name=value['Name']
                    if name in ('PSC_ANGLE_MAX','ATC_ANGLE_MAX'):
                        require(value['Value']==decoded[name],'Native BIN PARM differs from actual response')
                        native_parms.setdefault(name,[]).append(value)
                log.close()
        return dict(decoded=decoded,encoding='rcl_interfaces ParameterValue type 2=int64, 3=float64',
                    native_bin_angle_parameters=native_parms,
                    limitation='Client-returned response serialization; not a captured DDS service packet')
    decoded = {}
    for name,expected in values.items():
        matches = [m for _,m in messages if m.get('mavpackettype') == 'PARAM_VALUE' and m['param_id'] == name]
        require(expected in matches, 'Parameter readback absent from original datagrams: '+name)
        decoded[name] = px4_parameter_value(expected)
    require(set(decoded) == {'MPC_THR_HOVER','MPC_USE_HTE','MPC_THR_MIN','MPC_THR_MAX','THR_MDL_FAC'},
            'Required PX4 parameter missing')
    return dict(decoded=decoded,encoding='PX4 PARAM_VALUE int32 bytewise; float32 numeric')


def calibration_evidence(result, recorded, phases):
    value = result['task']['attitude_thrust']['calibration']
    if value is None:
        return dict(status='not_reached')
    start = phases['hover_observation_begin']['physical_start']
    end = phases['hover_observation_end']['physical_cursor']['final_time']
    selected = [dict(physical_time=r['physical_time'],native_boot_s=r['message']['time_boot_ms']/1000,
                     thrust=r['message']['thrust'],quaternion=r['message']['q']) for r in recorded
                if r['message']['mavpackettype'] == 'ATTITUDE_TARGET' and r['physical_time'] is not None
                and r['monotonic'] <= phases['hover_observation_end']['observed_monotonic_s']
                and start <= r['physical_time'] <= end]
    require(selected == value['samples'] and selected, 'Calibration samples differ from raw native datagrams')
    require(selected[0]['physical_time'] <= start+.1 and selected[-1]['physical_time'] >= end-.1
            and all(b['physical_time']-a['physical_time'] <= .25 for a,b in zip(selected,selected[1:])),
            'Native hover observation window has gaps')
    hover = statistics.median(s['thrust'] for s in selected)
    require(hover == value['hover'] and .15 <= hover <= .8 and value['frozen_at_physical_time'] == end,
            'Frozen calibration median/value differs')
    return dict(status=value['status'],hover=hover,samples=len(selected),start_receiver_s=start,end_receiver_s=end,
                first_native_boot_s=selected[0]['native_boot_s'],last_native_boot_s=selected[-1]['native_boot_s'],
                selection='Predeclared receiver physical interval; native stamps retained separately')


def frozen_command(label,command,calibration):
    expected_roll=math.radians(5) if label=='attitude_step' else 0.
    expected_thrust=calibration['hover']+(.03 if label=='thrust_step' else 0.)
    expected=(expected_roll,0.,calibration['yaw'],expected_thrust)
    require(label in ('level_calibration','attitude_step','thrust_baseline','thrust_step',
                     'level_calibration_entry_neutral','attitude_step_entry_neutral','thrust_baseline_entry_neutral')
            and command['agent_cmd']==4 and command['move_mode']==7
            and len(command['att_ref'])==4
            and all(abs(a-b)<1e-6 for a,b in zip(command['att_ref'],expected)),
            'Public command differs from frozen attitude/thrust case: '+label)


def px4_effects(root,result,data,phases,trace,motors,states):
    paths = list(root.rglob('*.ulg'))
    require(len(paths) == 1, 'Expected one actual PX4 ULog')
    native,meta = ulog(paths[0])
    require(not meta['dropout_durations_ms'], 'ULog dropout recorded')
    # Fixed simulator path sends output[60] (HIL sensor usec) on the model clock;
    # received actuator timestamp unlocks the following four physical substeps.
    mappings = [(round(r['time']*1e6),r['actuator_time_usec']) for r in trace if r['actuator_time_usec'] is not None]
    require(mappings and all(t-a == 4000 for t,a in mappings), 'PX4 native/physics time mapping differs')
    samples = native['actuator_outputs']
    comparisons=[]
    for r in samples:
        tick = r['timestamp']//1000
        if tick < 1 or tick+4 > len(motors) or max(r['output'][:4]) <= 1000:
            continue
        expected = [max(0,x-1000)/1000 for x in r['output'][:4]]
        error = max(abs(a-b) for a,b in zip(expected,motors[tick]))
        comparisons.append(error)
    require(comparisons and max(comparisons) < 1e-6, 'Native actuator outputs differ from next held physical input')
    public = [v for _,v in data['/uav1/prometheus/v2/command'] if v['command']['move_mode'] == 7]
    targets = next(rows for name,rows in data.items() if '/in/vehicle_attitude_setpoint' in name)
    offboard = {m['timestamp']:m for name,rows in data.items() if '/in/offboard_control_mode' in name for _,m in rows}
    cases=[]
    for request in public:
        cmd=request['command'];cid=cmd['command_id'];r,p,y,demand=cmd['att_ref']
        q=native_q(q_from_euler(r,p,y))
        phase=next(v for k,v in phases.items() if k.endswith('_offered') and v.get('command_id') == cid)
        label=phase['phase'][:-8]
        frozen_command(label,cmd,result['task']['attitude_thrust']['calibration'])
        offered=phase['physical_cursor']['final_time']
        later=[v['physical_cursor']['final_time'] for k,v in phases.items()
               if k.endswith('_offered') and v.get('command_id',0)>cid]
        stop=min(later) if later else phases.get('failure_land_accepted',list(phases.values())[-1])['physical_cursor']['final_time']
        actual=[(row,m) for row,m in targets if offered-.05 <= m['timestamp']/1e6 <= stop
                and q_distance(m['q_d'],q)<1e-6 and abs(-m['thrust_body'][2]-demand)<1e-6]
        require(actual,'Actual native attitude CDR missing: '+label)
        for row,m in actual:
            require(abs(math.hypot(*m['q_d'])-1)<1e-6 and m['thrust_body'][:2] == [0.,0.]
                    and -1<=m['thrust_body'][2]<=0, 'Native basis/thrust range differs')
            mode=offboard[m['timestamp']]
            require(mode['attitude'] and not any(mode[k] for k in
                ('position','velocity','acceleration','body_rate','thrust_and_torque','direct_actuator')),
                'Native offboard active axes differ')
        sp=[s for s in native['vehicle_attitude_setpoint'] if offered <= s['timestamp']/1e6 <= stop]
        timeline=[dict(native_boot_s=s['timestamp']/1e6,physical_s=s['timestamp']/1e6,
            matches_public=q_distance(s['q_d'],q)<1e-6 and abs(-s['thrust_body[2]']-demand)<1e-6,
            q_ned_frd=s['q_d'],normalized_thrust=-s['thrust_body[2]']) for s in sp]
        matching=[s for s in timeline if s['matches_public']]
        source_times=[m['timestamp']/1e6 for _,m in actual]
        publisher_times=[row['source_timestamp']/1e9 for row,_ in actual]
        tracking_start=phases.get('attitude_tracking_begin',{}).get('physical_start',math.inf)
        tracking=[s for s in timeline if tracking_start<=s['physical_s']<=tracking_start+.4]
        cases.append(dict(label=label,command_id=cid,public_att_ref=cmd['att_ref'],
            first_native_cdr_stamp_s=source_times[0],last_native_cdr_stamp_s=source_times[-1],
            native_cdr_count=len(actual),max_native_cdr_gap_s=max((b-a for a,b in zip(source_times,source_times[1:])),default=0),
            measured_native_mean_hz=(len(actual)-1)/(source_times[-1]-source_times[0]) if len(actual)>1 else None,
            measured_dds_source_mean_hz=(len(actual)-1)/(publisher_times[-1]-publisher_times[0]) if len(actual)>1 else None,
            first_logged_match_s=matching[0]['native_boot_s'] if matching else None,
            native_setpoint_timeline=timeline,
            exact_first_native_acceptance_known=False,
            mixed_logged_targets=any(not s['matches_public'] for s in timeline),
            frozen_tracking_native_samples=len(tracking) if label=='attitude_step' else None,
            frozen_tracking_native_verified=(bool(tracking) and all(s['matches_public'] for s in tracking))
                if label=='attitude_step' else None,
            first_receiver_cursor_s=actual[0][0]['physical_cursor']['final_time']))
    return dict(ulog=meta,clock_mapping='PX4 boot us = physics us; HIL actuator unlocks next four 1ms steps',
        clock_mapping_samples=len(mappings),motor_comparisons=len(comparisons),max_motor_input_error=max(comparisons),
        cases=cases,limitations=['ULog actuator outputs are ~10Hz; setpoints are sampled, not every publication.',
        'Raw DDS Humble metadata has source/received timestamps, no per-message publisher GID.',
        'Receiver cursor is an observation time; logged setpoint membership proves native uORB observation, not exact acceptance tick.'])


def ap_guided_transition(timeline,raw_targets,physical_start,first_new_stamp):
    """Only explain pre-window old targets using actual preceding native input."""
    transitions=[]
    for row in timeline:
        if row['matches_public']:continue
        require(row['physical_s']<physical_start,'AP wrong guided target inside frozen physical window')
        preceding=[m for _,m in raw_targets if m['header']['stamp']['sec']
                   +m['header']['stamp']['nanosec']/1e9<=row['native_boot_s']]
        require(preceding,'AP pre-window target has no preceding actual native CDR')
        previous=max(preceding,key=lambda m:(m['header']['stamp']['sec'],m['header']['stamp']['nanosec']))
        stamp=previous['header']['stamp']['sec']+previous['header']['stamp']['nanosec']/1e9
        q=native_q([previous['orientation'][k] for k in ('w','x','y','z')])
        logged=q_from_euler(*(math.radians(row[k]) for k in ('roll_deg','pitch_deg','yaw_deg')))
        require(stamp<first_new_stamp and q_distance(q,logged)<1e-6
                and abs(previous['normalized_thrust']-row['normalized_thrust'])<1e-6
                and previous['header']['frame_id']=='map', 'AP pre-window target differs from preceding actual native CDR')
        transitions.append(dict(logged_native_boot_s=row['native_boot_s'],preceding_native_cdr_stamp_s=stamp,
            normalized_thrust=row['normalized_thrust'],frozen_physical_start_s=physical_start,
            explanation='Previous actual native input; public offered time is not native acceptance'))
    require(any(row['physical_s']>=physical_start and row['matches_public'] for row in timeline),
            'AP actual target absent from frozen physical window')
    return transitions


def ap_effects(root,result,data,phases,trace,motors,states):
    import importlib.metadata
    from pymavlink import mavutil
    paths=list(root.rglob('*.BIN'))
    require(len(paths)==1,'Expected one actual AP BIN')
    log=mavutil.mavlink_connection(str(paths[0]));native=defaultdict(list)
    while True:
        row=log.recv_match(type=['GUIA','GUIP','RCOU','SIM2','ATT'])
        if row is None:break
        native[row.get_type()].append(row.to_dict())
    require(native['GUIA'] and native['RCOU'] and native['SIM2'],'AP native effect channels missing')
    # The sealed JSON adapter quantizes absolute state.timestamp once and adds
    # its delta. fill_fdm logs SIM2 before HAL stop_clock consumes the new FDM
    # timestamp, so SIM2's state is one tick newer than its AP_HAL TimeUS.
    # This +1 is the read source order, not a fitted observation shift.
    mapping=[]
    for row in native['SIM2']:
        tick=round(row['TimeUS']/1000)+1
        if not 1<=tick<=len(states):continue
        s=states[tick-1]
        actual=(row['PE'],row['PN'], -row['PD'],row['VE'],row['VN'],-row['VD'])
        expected=(*s['position'],*s['velocity'])
        mapping.append(max(abs(a-b) for a,b in zip(actual,expected)))
    require(mapping and max(mapping)<1e-4,'AP source-derived native clock/physics map differs')
    comparisons=[]
    for row in native['RCOU']:
        tick=round(row['TimeUS']/1000)
        if not 1<=tick<len(motors):continue
        expected=[max(0,row['C'+str(i)]-1000)/1000 for i in range(1,5)]
        comparisons.append(max(abs(a-b) for a,b in zip(expected,motors[tick])))
    require(comparisons and max(comparisons)<1e-6,'AP actual motor outputs differ from next physical input')
    cases=[]
    for _,request in data['/uav1/prometheus/v2/command']:
        command=request['command']
        if command['move_mode']!=7:continue
        cid=command['command_id'];r,p,y,thrust=command['att_ref']
        phase=next(v for k,v in phases.items() if k.endswith('_offered') and v.get('command_id')==cid)
        frozen_command(phase['phase'][:-8],command,result['task']['attitude_thrust']['calibration'])
        start=phase['physical_cursor']['final_time']
        later=[v['physical_cursor']['final_time'] for k,v in phases.items()
               if k.endswith('_offered') and v.get('command_id',0)>cid]
        stop=min(later) if later else phases.get('failure_land_accepted',list(phases.values())[-1])['physical_cursor']['final_time']
        targets=[(row,m) for row,m in data['/ap/wksim/attitude_target_v1']
            if start-.05 <= m['header']['stamp']['sec']+m['header']['stamp']['nanosec']/1e9 <= stop]
        q=q_from_euler(r,p,y)
        targets=[(row,m) for row,m in targets if q_distance([m['orientation'][k] for k in ('w','x','y','z')],q)<1e-6
                 and abs(m['normalized_thrust']-thrust)<1e-6]
        require(targets,'AP actual native CDR missing')
        for _,m in targets:
            require(m['header']['frame_id']=='map','AP native frame differs')
        gui=[row for row in native['GUIA'] if start<=row['TimeUS']/1e6<=stop]
        timeline=[dict(native_boot_s=row['TimeUS']/1e6,physical_s=row['TimeUS']/1e6,roll_deg=row['Roll'],
            pitch_deg=row['Pitch'],yaw_deg=row['Yaw'],normalized_thrust=row['Thrust'],
            matches_public=abs(row['Roll']-math.degrees(r))<1e-4 and abs(row['Pitch']+math.degrees(p))<1e-4
            and abs(math.degrees(angle(math.radians(row['Yaw'])-(math.pi/2-y))))<1e-4
            and abs(row['Thrust']-thrust)<1e-6 and row['ClimbRt']==0
            and row['RollRt']==row['PitchRt']==row['YawRt']==0) for row in gui]
        require(timeline,'AP logged guided target missing')
        label=phase['phase'][:-8]
        native_phase=phases[label+'_native_observed']['native_target']
        actual_first=targets[0][1]['header']['stamp']
        require(native_phase['native_source_stamp']==actual_first
                and native_phase['physical_time']==targets[0][0]['physical_cursor']['final_time'],
                'AP original native observation differs from raw CDR')
        physical_start=native_phase['physical_time']
        original_label='attitude_settling' if label=='attitude_step' else label
        require(phases[original_label+'_begin']['physical_start']>=physical_start
                and (label=='thrust_baseline' or phases[original_label+'_begin']['physical_start']==physical_start),
                'AP frozen original physical window origin differs')
        physical_start=phases[original_label+'_begin']['physical_start']
        transitions=ap_guided_transition(timeline,data['/ap/wksim/attitude_target_v1'],physical_start,
                                         actual_first['sec']+actual_first['nanosec']/1e9)
        tracking_start=phases.get('attitude_tracking_begin',{}).get('physical_start',math.inf)
        tracking=[s for s in timeline if tracking_start<=s['physical_s']<=tracking_start+.4]
        source_times=[m['header']['stamp']['sec']+m['header']['stamp']['nanosec']/1e9 for _,m in targets]
        publisher_times=[row['source_timestamp']/1e9 for row,_ in targets]
        cases.append(dict(label=phase['phase'][:-8],command_id=cid,public_att_ref=command['att_ref'],
            native_cdr_count=len(targets),native_setpoint_timeline=timeline,
            pre_window_transitions=transitions,frozen_physical_start_s=physical_start,
            first_native_cdr_stamp_s=source_times[0],last_native_cdr_stamp_s=source_times[-1],
            max_native_cdr_gap_s=max((b-a for a,b in zip(source_times,source_times[1:])),default=0),
            measured_native_mean_hz=(len(targets)-1)/(source_times[-1]-source_times[0]) if len(targets)>1 else None,
            measured_dds_source_mean_hz=(len(targets)-1)/(publisher_times[-1]-publisher_times[0]) if len(targets)>1 else None,
            frozen_tracking_native_samples=len(tracking) if phase['phase']=='attitude_step_offered' else None,
            frozen_tracking_native_verified=(bool(tracking) and all(s['matches_public'] for s in tracking))
                if phase['phase']=='attitude_step_offered' else None,
            first_logged_match_s=timeline[0]['native_boot_s'],exact_first_native_acceptance_known=False))
    return dict(bin_path=str(paths[0]),bin_sha256=digest(paths[0]),decoder_version=importlib.metadata.version('pymavlink'),
        actual_native_log_name='GUIA',cases=cases,clock_mapping='Quantized absolute JSON -> FDM -> HAL boot clock; zero offset. SIM2 fill_fdm logs new state before stop_clock: state tick = TimeUS/1000+1, source-derived, no fit.',
        sim2_mapping_samples=len(mapping),max_sim2_mapping_error=max(mapping),motor_comparisons=len(comparisons),
        max_next_tick_motor_input_error=max(comparisons),
        recovery_native_position_targets=[row for row in native['GUIP'] if 'attitude_recovery_offered' in phases
            and phases['attitude_recovery_offered']['physical_cursor']['final_time']<=row['TimeUS']/1e6
            <=phases.get('failure_land_accepted',list(phases.values())[-1])['physical_cursor']['final_time']],
        limitations=['GUIA records native Guided setter targets, not a per-motor acceptance acknowledgement.',
                    'RCOU is sampled; no raw actuator datagram was captured.'])


def audit(root):
    root=Path(root)
    result=read(root/'result.json')
    require(result['children_reaped'] and all(c['returncode'] is not None for c in result['children'].values()),
            'Run has not terminated')
    report=dict(status='failed',run_id=result['run_id'],stack=result['stack'],original_runtime_status=result['status'],
        original_runtime_error=result.get('error'),budget_sha256=BUDGET_SHA,checks={},errors=[],limitations=[],
        auditor_sha256=digest(__file__))
    def check(name,call):
        try:
            value=call(); report['checks'][name]=value; return value
        except Exception as error:
            report['errors'].append(dict(check=name,error=f'{type(error).__name__}: {error}'))
            return None
    check('identity',lambda:retained_identity(root,result))
    entry=check('entry_contract',lambda:entry_contract(root,result))
    check('observer_equivalence',lambda:observer_equivalence(root,result))
    physical=check('physics_read',lambda:physical_evidence(root,result['stack']))
    if physical:
        meta,states,motors,trace=physical
        report['checks']['physics_read']=meta
        phases=check('phases',lambda:phase_evidence(result,trace))
        if phases:
            report['checks']['phases']=dict(count=len(phases),labels=list(phases))
        decoded=check('raw_decode',lambda:decode_native(root,result))
        if decoded:
            data,messages,recorded,meta=decoded; report['checks']['raw_decode']=meta
            check('parameters',lambda:parameters(root,result,messages))
            if phases:
                if entry and entry['required']:
                    discovery=[row for row in lines(root/'attitude-native.jsonl') if row['kind']=='dds_discovery_publishers']
                    check('entry_gates',lambda:entry_gate_evidence(result,data,recorded,phases,states,
                                                                  discovery,entry['contract']['px4']))
                check('calibration',lambda:calibration_evidence(result,recorded,phases))
                calibration=result['task']['attitude_thrust']['calibration']
                if calibration:
                    check('fixed_windows',lambda:fixed_metrics(states,phases,calibration))
                if result['stack']=='px4':
                    check('native_effects',lambda:px4_effects(root,result,data,phases,trace,motors,states))
                else:
                    check('native_effects',lambda:ap_effects(root,result,data,phases,trace,motors,states))
        report['checks']['terminal']=dict(children_reaped=result['children_reaped'],cleanup_errors=result['cleanup_errors'],
            final_physical_height_m=states[-1]['position'][2],runtime_safe_landing=result['safe_landing'])
    completed=result.get('task',{}).get('attitude_thrust',{}).get('status')=='completed_pending_raw_audit'
    windows=report['checks'].get('fixed_windows',{})
    required={'hover_observation','entry','level_calibration','attitude_tracking','thrust_step',
              'calibration_recovery','attitude_recovery','thrust_recovery','abort_envelope'}
    terminal=report['checks'].get('terminal',{})
    native_cases=report['checks'].get('native_effects',{}).get('cases',[])
    native_tracking=any(c['label']=='attitude_step' and c['frozen_tracking_native_verified'] for c in native_cases)
    if (result['status']=='observed' and completed and not report['errors'] and not report['limitations']
            and terminal.get('runtime_safe_landing') and not terminal.get('cleanup_errors')
            and native_tracking
            and abs(terminal.get('final_physical_height_m',math.inf))<.3
            and required<=windows.keys() and all(v['passed'] for v in windows.values())):
        report['status']='pass'
    report['evidence_sha256']={str(p.relative_to(root)):digest(p) for p in root.rglob('*')
        if p.is_file() and (p.name in ('result.json','admission.json','config.json','postflight-admission.json',
            'physics-1ms.jsonl','truth.jsonl','attitude-native.jsonl','attitude-progress.json')
            or p.suffix in ('.ulg','.BIN','.maps'))}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--decoder-path',type=Path)
    args=parser.parse_args()
    if args.output:
        require(not args.output.resolve().is_relative_to(args.root.resolve()),
                'Audit output must be new and outside the original run directory')
    if args.decoder_path:
        sys.path.insert(0,str(args.decoder_path))
    value=audit(args.root)
    content=json.dumps(value,indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x') as stream: stream.write(content)
    else:
        print(content)
    return 0 if value['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
