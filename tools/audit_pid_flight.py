"""Independent #85 offline PID audit; never imports the online PID/evaluator.

Usage (inside the admitted ROS overlay):
  python3 -B tools/audit_pid_flight.py --run-dir /root/wksim-pid-flight-ID/ID \
      --output /absolute/new-audit.json
Output schema wksim.pid.audit.v1 retains completed checks and the first failure.
Exit 0 means recorded evidence passed; 1 means rejected/incomplete. No flight,
model, ROS node, source execution, parameter change or in-place evidence edit.
Wire matching uses 1e-6; independent double recomputation uses 1e-10. Neither
tolerance applies to physical budgets. Sampled native logs cannot establish the
exact first acceptance tick or absence of activity between native observations.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import audit_attitude_flight as wire

PROTOCOL = '25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0'
MODEL = 'cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3'
require, digest, read, lines = wire.require, wire.digest, wire.read, wire.lines


def near(actual, expected, tolerance=1e-10):
    if isinstance(expected, (list, tuple)):
        return (isinstance(actual, (list, tuple)) and len(actual) == len(expected)
                and all(near(a, b, tolerance) for a, b in zip(actual, expected)))
    return (type(actual) in (int, float) and math.isfinite(actual)
            and abs(actual-expected) <= tolerance)


def desired(config, kind, elapsed):
    p, v, a = config['point']['position_enu_m'], [0.]*3, [0.]*3
    if kind == 'circle':
        c = config['circle']; w = 2*math.pi/c['period_s']; r = c['radius_m']
        x, y = math.cos(w*elapsed), math.sin(w*elapsed)
        p = [c['center_enu_m'][0]+r*x, c['center_enu_m'][1]+r*y, c['center_enu_m'][2]]
        v, a = [-r*w*y, r*w*x, 0.], [-r*w*w*x, -r*w*w*y, 0.]
    return dict(position_enu=p, velocity_enu=v, acceleration_enu=a,
                yaw_enu_rad=config['point']['yaw_rad'])


def recompute(config, state, ref, dt, integral, hover):
    """Independent equations, including original discontinuities and projection."""
    require(0 < dt <= .2 and math.isfinite(dt), 'PID dt outside frozen contract')
    q = state['attitude_flu_to_enu']
    require(len(q) == 4 and near(math.hypot(*q), 1., 1e-6), 'Nonunit PID state quaternion')
    for key in ('position_enu', 'velocity_enu'):
        require(len(state[key]) == 3 and all(math.isfinite(x) for x in state[key]), 'Invalid PID state')
    pe = [a-b for a, b in zip(ref['position_enu'], state['position_enu'])]
    ve = [a-b for a, b in zip(ref['velocity_enu'], state['velocity_enu'])]
    pe = [math.copysign(1., e) if abs(e) > 3 else e for e in pe]
    ve = [math.copysign(2., e) if abs(e) > 3 else e for e in ve]
    old = [0.]*3 if any(ref['velocity_enu']) else integral
    gains = config['pid']; mass = config['model']['mass_kg']; mg = mass*9.8
    integ = [max(-gains['integral_limit'][i], min(gains['integral_limit'][i], old[i]+pe[i]*dt))
             if abs(pe[i]) < threshold else 0.
             for i, threshold in enumerate((.20000000298023224, .20000000298023224, .5))]
    acc = [ref['acceleration_enu'][i]+gains['kp'][i]*pe[i]+gains['kv'][i]*ve[i]+gains['ki'][i]*integ[i]
           for i in range(3)]
    f = [mass*acc[0], mass*acc[1], mass*acc[2]+mg]
    require(f[2] != 0, 'Undefined zero vertical force')
    zforce = max(.5*mg, min(2*mg, f[2]))
    if zforce != f[2]:
        f = [x/f[2]*zforce for x in f]
    cap = f[2]*math.tan(math.radians(gains['tilt_limit_deg']))
    f[:2] = [max(-cap, min(cap, x)) for x in f[:2]]
    w, x, y, z = q; norm = sum(a*a for a in q)
    yaw = math.atan2(2*(w*z+x*y)/norm, 1-2*(y*y+z*z)/norm)
    fx = math.cos(yaw)*f[0]+math.sin(yaw)*f[1]
    fy = -math.sin(yaw)*f[0]+math.cos(yaw)*f[1]
    rpy = [math.atan2(-fy, f[2]), math.atan2(fx, f[2]), ref['yaw_enu_rad']]
    projected = sum(a*b for a, b in zip(f, (2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y))))
    return (dict(acceleration_enu=acc, force_enu_n=f, roll_pitch_yaw_enu_rad=rpy,
                 projected_thrust_n=projected, integral=integ, mass_kg=mass, controller='pid'),
            max(.1, min(1., projected/(mg/hover))))


def event_check(event, raw, run_id):
    origin = event['declared_origin_tick']
    require(type(origin) is int and origin >= 0, 'Invalid event origin')
    expected = dict(schema='wksim.pid-disturbance.v1', run_id=run_id, protocol_sha256=PROTOCOL,
        stage='pid_disturbance', declared_origin_tick=origin, permitted_start_tick=origin,
        permitted_end_tick=origin+11000, start_tick=origin+2000, end_tick=origin+3000,
        multiplier=.97, channels=[0, 1, 2, 3],
        tick_semantics='zero-based integration interval [tick,tick+1); start inclusive, end exclusive')
    require(event == expected and raw == (json.dumps(expected, sort_keys=True, separators=(',', ':'))+'\n').encode(),
            'Event identity/window/canonical bytes differ')
    return hashlib.sha256(raw).hexdigest()


def decode_packet(packet, stack):
    raw = bytes.fromhex(packet['packet_hex'])
    if stack == 'arducopter':
        require(packet['protocol'] == 'AP_JSON_SERVO16' and len(raw) == 40, 'Invalid AP packet')
        magic, rate, frame, *pwm = struct.unpack('<HHI16H', raw)
        require(magic == 18458 and rate > 0 and pwm == packet['pwm16']
                and frame == packet['frame'] and rate == packet['rate_hint'], 'AP wire fields differ')
        require(all(x == 0 or 1000 <= x <= 2000 for x in pwm[:4]), 'AP PWM range')
        values = [max(0, x-1000)/1000 for x in pwm[:4]]+[0.]*12
        key = frame
    else:
        # Full frame parser checks MAVLink CRC, not just self-reported JSON fields.
        from pymavlink.dialects.v20 import common
        parser = common.MAVLink(None)
        messages = parser.parse_buffer(raw)
        require(messages and len(messages) == 1 and bytes(messages[0].get_msgbuf()) == raw
                and messages[0].get_type() == 'HIL_ACTUATOR_CONTROLS', 'Invalid PX4 actuator frame')
        msg = messages[0]
        require(msg.to_dict() == packet['message'] and packet['protocol'] == 'MAVLink_HIL_ACTUATOR_CONTROLS',
                'PX4 raw fields differ')
        values = list(msg.controls[:4])+[0.]*12 if msg.mode & 128 else [0.]*16
        key = msg.time_usec
    require(values == packet['decoded_input16'] and all(math.isfinite(x) and 0 <= x <= 1 for x in values),
            'Raw actuator decode differs')
    return values, key


def physics(rows, packets, event, event_sha, run_id, stack):
    """Stream full raw output; retransmitted AP packets do not create new ticks."""
    decoded = {}; order = []
    for p in packets:
        value, key = decode_packet(p, stack)
        token = json.dumps(p, sort_keys=True)
        decoded[token] = (value, key); order.append(token)
    require(order, 'No raw actuator packets')
    states = []; originals = []; header = terminal = None
    group = sub = size = 0; held = None; active_count = 0; first_load = None
    previous_key = None; packet_index = 0; packet_seen = False
    for row in rows:
        require(row['run_id'] == run_id and terminal is None, 'Raw run identity or data after terminal')
        if row['kind'] == 'start':
            require(header is None and not states and row['schema'] == 'wksim.pid.physics.v1'
                    and row['initial_tick'] == 0 and row['dt_s'] == .001
                    and row['library_sha256'] == MODEL and row['protocol_sha256'] == PROTOCOL
                    and row['mass_kg'] == 1.515, 'Physical header identity differs')
            header = row; continue
        if row['kind'] == 'end':
            require(header and row['ticks'] == len(states) and row['groups'] == group and sub == size
                    and row['disturbance_applied_ticks'] == active_count == 1000
                    and row['disturbance_event_sha256'] == event_sha and not row['disturbance_revoked'],
                    'Physical terminal or disturbance count differs')
            terminal = row; continue
        require(header and row['kind'] == 'step', 'Missing physical start/unknown record')
        tick = len(states); v = row['output120']; original = row['original_decoded_input16']
        require(row['interval_tick'] == tick and row['tick'] == tick+1 and len(v) == 120
                and len(original) == 16 and row['input16'] == original
                and all(math.isfinite(x) for x in v+original) and all(0 <= x <= 1 for x in original)
                and near(v[2], (tick+1)*.001, 1e-8), 'Missing/repeated tick or invalid output/input')
        if row['substep'] == 0:
            require(sub == size and row['group'] == group+1 and row['group_steps'] == (1 if stack == 'arducopter' else 4),
                    'Incomplete physical group')
            group, sub, size, held = row['group'], 0, row['group_steps'], row['raw_actuator_packet']
            if held is None:
                require(stack == 'px4' and not packet_seen and original == [0.]*16, 'Missing actual actuator input')
            else:
                token = json.dumps(held, sort_keys=True)
                require(token in decoded, 'Applied packet absent from original packet capture')
                values, key = decoded[token]
                while packet_index < len(order) and order[packet_index] != token:
                    # Only exact retransmissions of the last consumed AP frame may be skipped.
                    require(stack == 'arducopter' and decoded[order[packet_index]][1] == previous_key,
                            'Captured input skipped or reordered')
                    packet_index += 1
                require(packet_index < len(order), 'Packet order differs')
                packet_index += 1
                require(values == original, 'Held input differs from source packet')
                if previous_key is not None:
                    require(key == (previous_key+1) % 2**32 if stack == 'arducopter' else key > previous_key,
                            'Duplicate actuator packet incorrectly integrated')
                previous_key, packet_seen = key, True
                if stack == 'px4':
                    require(key == tick*1000, 'PX4 source clock must unlock next four physical ticks')
        require(row['group'] == group and row['substep'] == sub and row['group_steps'] == size
                and row['raw_actuator_packet'] == held, 'Substep/held packet changed')
        if held is not None:
            require(original == decoded[json.dumps(held, sort_keys=True)][0], 'Held input changed inside group')
        sub += 1
        sha = row['disturbance_event_sha256']
        if sha is not None and first_load is None:
            first_load = tick
            require(event['start_tick']-tick >= 1000, 'Late event load')
        require((sha == event_sha if first_load is not None else sha is None)
                and not row['disturbance_revoked'], 'Event hash changed/revoked')
        active = event['start_tick'] <= tick < event['end_tick']
        require(not active or first_load is not None, 'Unloaded disturbance')
        expected = [x*(.97 if active and i < 4 else 1.) for i, x in enumerate(original)]
        require(row['disturbance_active'] is active and row['applied_input16'] == expected,
                'Disturbance missing/extra/incorrect input tick')
        active_count += int(active)
        states.append(wire.enu(v)); originals.append(original)
    require(header and terminal and states and first_load is not None, 'Missing raw start/end/event')
    require(all(stack == 'arducopter' and decoded[token][1] == previous_key for token in order[packet_index:]),
            'Unconsumed new actuator capture at terminal')
    return states, originals, dict(ticks=len(states), applied_ticks=active_count, event_first_load_tick=first_load,
                                  header=header, captured_packets=len(order))


def fixed_metrics(config, states, phases, event):
    metrics = {}
    for kind in ('point', 'circle', 'disturbance'):
        begin = phases['pid_'+kind+'_begin']; end = phases['pid_'+kind+'_end']
        origin = begin['physical_start']; budget = config[kind]
        require(begin['measured_external_pid'] and end['measured_external_pid']
                and begin['settle_s'] == budget['settle_s'], 'Stage declaration differs')
        start = origin+budget['settle_s']
        stop = event['permitted_end_tick']/1000 if kind == 'disturbance' else start+budget['measure_s']
        require(end['physical_cursor']['final_time'] >= stop, 'Stage ended before frozen window')
        if kind == 'disturbance':
            frozen = phases['pid_disturbance_event_frozen']
            require(start <= event['declared_origin_tick']/1000 and frozen['event'] == event
                    and math.ceil(frozen['physical_cursor']['final_time']*1000-1e-7) == event['declared_origin_tick'],
                    'Event declaration differs from retained phase cursor')
            start = event['permitted_start_tick']/1000
        measured = wire.window(states, start, stop)
        errors = []; speeds = []; yaws = []
        for s in wire.window(states, origin, stop):
            envelope = config['envelope']
            require(envelope['minimum_height_m'] <= s['position'][2] <= envelope['maximum_height_m']
                    and math.dist(s['position'], config['point']['position_enu_m']) <= envelope['max_distance_from_point_m']
                    and max(abs(x) for x in s['attitude'][:2]) <= math.radians(envelope['max_axis_tilt_deg']),
                    f'{kind} physical envelope violated at {s["time"]}')
        for s in measured:
            ref = desired(config, kind, s['time']-origin)
            errors.append(math.dist(s['position'], ref['position_enu']))
            speeds.append(math.hypot(*s['velocity']))
            yaws.append(abs(wire.angle(s['attitude'][2]-ref['yaw_enu_rad'])))
            require(errors[-1] <= budget['max_error_m'], f'{kind} position budget at {s["time"]}')
            if kind == 'point':
                require(speeds[-1] <= budget['max_speed_mps'], f'point speed budget at {s["time"]}')
            if kind != 'disturbance':
                require(yaws[-1] <= budget['max_yaw_error_rad'], f'{kind} yaw budget at {s["time"]}')
            elif s['time'] >= stop-budget['return_dwell_s']:
                require(errors[-1] <= budget['return_error_m'] and speeds[-1] <= budget['return_speed_mps']
                        and yaws[-1] <= budget['return_yaw_error_rad'], f'Fixed final recovery dwell at {s["time"]}')
        metrics[kind] = dict(start=start, end=stop, ticks=len(measured), max_error_m=max(errors),
                             max_speed_mps=max(speeds), max_yaw_error_rad=max(yaws))
    return metrics


def identity(root, result):
    require(result['stack'] in ('px4', 'arducopter'), 'Unknown stack')
    require(digest(root/'pid-protocol.json') == PROTOCOL, 'Frozen protocol identity changed')
    config = read(root/'pid-protocol.json')
    require(read(root/'config.json') == result['config'] and result['config']['external_pid'] == config
            and result['config']['controller'] == 'pid', 'PID selection/configuration differs')
    admission = read(root/'admission.json'); post = read(root/'postflight-admission.json')
    require(admission == result['admission'] and admission['ok'] and post['ok'], 'Admission failed/differs')
    seals = result['source_sha256']
    required = ('tools/run_pid_flight.py', 'tools/pid_physics.py', 'Simulator/wksim_runtime/pid_task.py',
                'Simulator/wksim_control/position_pid.py', 'Simulator/wksim_runtime/pid-flight-v1.json')
    require(all(name in seals for name in required), 'Required executed source seal absent')
    for name, sha in seals.items():
        path = (root/'run-source'/name).resolve()
        require(path.is_relative_to((root/'run-source').resolve()) and digest(path) == sha,
                'Retained source identity differs: '+name)
    require(seals[required[-1]] == PROTOCOL and result['source_unchanged'] and result['candidate_unchanged'],
            'Executed source/config changed')
    ids = admission['identities']
    for name in ('ap', 'px4', 'model_build', 'native', 'control', 'setup_sha256'):
        require(ids[name] == post['identities'][name], 'Postflight identity differs: '+name)
    before, after = ids['source_sha256'], post['identities']['source_sha256']
    require(all(after.get(k) == v for k, v in before.items())
            and all(seals.get(k) == v for k, v in after.items() if k not in before), 'Unsealed runtime source')
    for name, pin, value in (
        ('fc', ids['ap' if result['stack'] == 'arducopter' else 'px4'], result['launched_binary_sha256']),
        ('agent', ids['baseline'][result['stack']+'_agent'], result['launched_agent_sha256'])):
        child = result['children'][name]
        require(child['argv'] == result['launch_plan'][name] and child['executable'] == pin['path']
                and child['argv'][0] == pin['path'] and value == pin['sha256'] == digest(pin['path'])
                and pin['path'] in (root/(name+'.maps')).read_text(), 'Actual binary identity differs: '+name)
    require(digest(admission['library']) == ids['model_build']['library_sha256'] == MODEL
            and admission['library'] in (root/'physics.maps').read_text(), 'Loaded model identity differs')
    require(result['actual_control_sha256'] == ids['control']['installed_python_hashes'], 'Control seal differs')
    for name, sha in result['actual_control_sha256'].items():
        require(digest(Path(ids['control']['package'])/name) == sha, 'Installed control changed')
    for name in ('physics', 'control'):
        require(result['children'][name]['argv'] == result['launch_plan'][name], 'Launch argv changed')
    argv = result['children']['control']['argv']
    require('native_attitude_profile:=attitude_thrust_v1' in argv and 'enable_external_attitude:=true' in argv,
            'Native attitude outlet disabled')
    return config


def calibration(config, resolved, result, recorded, phases, states):
    cal = resolved['calibration']
    require(resolved['configuration'] == config and resolved['protocol_sha256'] == PROTOCOL
            and resolved['controller'] == 'pid' and cal == result['task']['external_pid']['calibration']
            and cal['stack'] == result['stack'] and cal['mass_kg'] == 1.515
            and cal['model_identity'] == 'sha256:'+MODEL, 'Calibration run/model/controller differs')
    lo = phases['hover_observation_begin']['physical_start']
    hi = phases['hover_observation_end']['physical_cursor']['final_time']
    require(hi >= lo+3, 'Hover calibration shorter than three seconds')
    selected = [dict(physical_time=r['physical_time'], native_boot_s=r['message']['time_boot_ms']/1000,
                     thrust=r['message']['thrust'], quaternion=r['message']['q']) for r in recorded
                if r['message']['mavpackettype'] == 'ATTITUDE_TARGET' and r['physical_time'] is not None
                and lo <= r['physical_time'] <= hi
                and r['monotonic'] <= phases['hover_observation_end']['observed_monotonic_s']]
    require(selected and selected == cal['samples'] and selected[0]['physical_time'] <= lo+.1
            and selected[-1]['physical_time'] >= hi-.1
            and all(0 <= b['physical_time']-a['physical_time'] <= .25 for a, b in zip(selected, selected[1:])),
            'Same-run native hover samples missing/gapped/changed')
    hover = statistics.median(x['thrust'] for x in selected)
    require(.15 <= hover <= .8 and hover == cal['hover'] and cal['frozen_at_physical_time'] == hi,
            'Same-run hover median differs')
    for s in wire.window(states, lo, hi):
        require(math.dist(s['position'], (2, 3, 3)) <= .25 and math.hypot(*s['velocity']) <= .15
                and max(abs(x) for x in s['attitude'][:2]) <= math.radians(2)
                and abs(wire.angle(s['attitude'][2])) <= math.radians(3), 'Hover calibration physically unstable')
    lo = phases['pid_level_calibration_begin']['physical_start']
    hi = lo+2
    require(phases['pid_level_calibration_end']['physical_cursor']['final_time'] >= hi
            and hi <= phases['pid_point_begin']['physical_start'], 'Level validation duration/order differs')
    # Height was sampled before command emission. Retain that original state,
    # rather than choosing a more favourable first measurement afterwards.
    offered = phases['pid_level_calibration_offered']['physical_cursor']['final_time']
    height = wire.window(states, offered, offered+.001)[0]['position'][2]
    for s in wire.window(states, lo, hi):
        require(abs(s['position'][2]-height) <= .3 and abs(s['velocity'][2]) <= .2,
                'Same-run level calibration physical budget')
    return dict(hover=hover, samples=len(selected), start=lo, end=hi)


def stamp(state):
    value = state['header']['stamp']
    return value['sec']+value['nanosec']/1e9


def trace_audit(config, rows, phases, result, hover, data):
    requests = {v['request_id']: (r, v) for r, v in data['/uav1/prometheus/v2/command']}
    require(len(requests) == len(data['/uav1/prometheus/v2/command']), 'Duplicate public request')
    sessions = data['/uav1/prometheus/v2/state']
    events = [json.loads(v['message']) for _, v in data['/uav1/prometheus/text_info']]
    previous_stage = None; last_request = last_command = -1; counts = {}; matched = []; generation = None
    for row in rows:
        kind = row['stage']
        require(kind in ('point', 'circle', 'disturbance'), 'Unknown PID stage')
        begin = phases['pid_'+kind+'_begin']; end = phases['pid_'+kind+'_end']
        if kind != previous_stage:
            if previous_stage is not None:
                require(0 <= phases['pid_'+previous_stage+'_end']['native_boot_s']-previous_stamp <= .2,
                        'PID trace missing final native-time coverage')
            require(kind not in counts, 'PID stage reentered without new run')
            integral = [0.]*3; previous_stamp = begin['native_boot_s']; counts[kind] = 0
            previous_stage = kind
        if generation is None:
            generation = row['native_generation']
        require(row['native_generation'] == generation, 'Native generation changed within run')
        require(row['controller'] == 'pid' and row['run_id'] == result['run_id']
                and row['protocol_sha256'] == PROTOCOL and row['model_identity'] == 'sha256:'+MODEL
                and row['mass_kg'] == 1.515 and row['calibration'] == hover
                and row['control_epoch'] == result['task']['control_epoch'], 'PID trace identity/calibration differs')
        require(begin['physical_start'] <= row['physical_time'] <= end['physical_cursor']['final_time']
                and row['reference_origin_physical_s'] == begin['physical_start'], 'Reference clock/stage differs')
        ref = desired(config, kind, row['physical_time']-begin['physical_start'])
        require(all(near(row['reference'][k], v) for k, v in ref.items()), 'Circle/point reference differs')
        dt = row['native_state_stamp_s']-previous_stamp
        require(near(row['dt_s'], dt) and 0 < dt <= .2, 'PID native dt/reset discontinuity')
        output, collective = recompute(config, row['state'], ref, dt, integral, hover)
        require(row['output']['controller'] == 'pid' and all(near(row['output'][k], v)
                for k, v in output.items() if k != 'controller')
                and near(row['normalized_collective'], collective), 'Independent PID integral/force/projection differs')
        require(near(row['native_thrust_convention'], [0., 0., -collective] if result['stack'] == 'px4' else collective),
                'Native thrust sign differs')
        integral, previous_stamp = output['integral'], row['native_state_stamp_s']
        rid, cid = row['public_request_id'], row['public_command_id']
        require(rid > last_request and cid > last_command and rid in requests, 'Missing/reused public identity')
        raw, public = requests[rid]; command = public['command']
        envelope = row['public_envelope']
        require(envelope['run_id'] == row['run_id'] and envelope['request_id'] == rid
                and envelope['control_epoch'] == row['control_epoch']
                and envelope['command']['command_id'] == cid and envelope['command']['move_mode'] == 7
                and near(envelope['command']['att_ref'], [*output['roll_pitch_yaw_enu_rad'], collective]),
                'PID trace envelope differs from recomputed output')
        require(public['run_id'] == row['run_id'] and public['control_epoch'] == row['control_epoch']
                and command['command_id'] == cid and command['move_mode'] == row['public_move_mode'] == 7
                and command['agent_cmd'] == 4
                and near(command['att_ref'], [*output['roll_pitch_yaw_enu_rad'], collective], 1e-6),
                'False PID label/public XYZ_ATT payload differs')
        require(any(e.get('event') == 'command_accepted' and e.get('request_id') == rid
                    and e.get('command_id') == cid and e.get('run_id') == row['run_id']
                    and e.get('control_epoch') == row['control_epoch'] for e in events), 'PID command ID ack missing')
        candidates = [v for r, v in sessions if r['monotonic'] <= raw['monotonic']
                      and v['run_id'] == row['run_id'] and v['control_epoch'] == row['control_epoch']
                      and v['native_generation'] == row['native_generation']
                      and stamp(v['state']) == row['native_state_stamp_s']]
        require(any(near(v['state']['position'], row['state']['position_enu'])
                    and near(v['state']['velocity'], row['state']['velocity_enu'])
                    and near([v['state']['attitude_q'][k] for k in ('w', 'x', 'y', 'z')], row['state']['attitude_flu_to_enu'])
                    and v['state']['armed'] and v['state']['connected'] and v['state']['odom_valid']
                    and v['state']['mode'] == ('OFFBOARD' if result['stack'] == 'px4' else 'GUIDED')
                    and v['control']['control_state'] == 2 for v in candidates), 'PID state absent from original public CDR')
        last_request, last_command = rid, cid; counts[kind] += 1; matched.append((row, raw, public))
    require(set(counts) == {'point', 'circle', 'disturbance'} and all(counts.values()), 'Missing PID stages')
    require(0 <= phases['pid_'+previous_stage+'_end']['native_boot_s']-previous_stamp <= .2,
            'PID trace missing final native-time coverage')
    for raw, request in data['/uav1/prometheus/v2/command']:
        for kind in counts:
            lo, hi = phases['pid_'+kind+'_begin'], phases['pid_'+kind+'_end']
            if lo['observed_monotonic_s'] <= raw['monotonic'] <= hi['observed_monotonic_s']:
                require(request['request_id'] in {r['public_request_id'] for r, _, _ in matched}
                        and request['command']['move_mode'] == 7, 'Position/helper command inside measured PID stage')
    for raw, _ in data.get('/uav1/prometheus/v2/setup', []):
        require(not any(phases['pid_'+kind+'_begin']['observed_monotonic_s'] <= raw['monotonic'] <=
                        phases['pid_'+kind+'_end']['observed_monotonic_s'] for kind in counts),
                'Setup override inside measured PID stage')
    return matched, counts


def native_audit(root, result, data, matched, phases, states, originals):
    stack = result['stack']; is_px4 = stack == 'px4'
    def in_stage(time):
        return any(phases['pid_'+k+'_begin']['physical_start'] <= time <=
                   phases['pid_'+k+'_end']['physical_cursor']['final_time'] for k in ('point', 'circle', 'disturbance'))
    targets = [(raw, m) for name, rows in data.items()
               if ('/in/vehicle_attitude_setpoint' in name if is_px4 else name == '/ap/wksim/attitude_target_v1')
               for raw, m in rows]
    require(targets, 'No raw native attitude CDR')
    # This is a source timestamp/value association, never receiver-cursor acceptance.
    def normalized(m):
        if is_px4:
            require(m['thrust_body'][:2] == [0., 0.], 'PX4 nonvertical native thrust')
            return m['timestamp']/1e6, m['q_d'], -m['thrust_body'][2]
        require(m['header']['frame_id'] == 'map', 'AP target frame differs')
        return stamp(m), wire.native_q([m['orientation'][k] for k in ('w', 'x', 'y', 'z')]), m['normalized_thrust']
    normalized_targets = [(raw, *normalized(m)) for raw, m in targets]
    if is_px4:
        paths = list(root.rglob('*.ulg')); require(len(paths) == 1, 'Expected one native ULog')
        native, log_identity = wire.ulog(paths[0])
        require(not log_identity['dropout_durations_ms'], 'Native ULog dropout')
        logged = [(m['timestamp']/1e6, m['q_d'], -m['thrust_body[2]']) for m in native['vehicle_attitude_setpoint']]
        motors = [(round(m['timestamp']/1000), [max(0, x-1000)/1000 for x in m['output'][:4]])
                  for m in native['actuator_outputs'] if max(m['output'][:4]) > 1000]
        modes = [m for name, rows in data.items() if '/out/vehicle_control_mode' in name for _, m in rows]
        offboard = {m['timestamp']: m for name, rows in data.items() if '/in/offboard_control_mode' in name for _, m in rows}
        from Simulator.wksim_runtime.attitude_task import MODE_TRUE, MODE_FALSE
        for m in modes:
            if in_stage(m['timestamp']/1e6):
                require(all(m.get(k, False) for k in MODE_TRUE) and not any(m.get(k, True) for k in MODE_FALSE),
                        'Native position/velocity loop override in measured PID stage')
        for _, t, _, _ in normalized_targets:
            if in_stage(t):
                mode = offboard.get(round(t*1e6))
                require(mode and mode['attitude'] and not any(mode[k] for k in
                        ('position', 'velocity', 'acceleration', 'body_rate', 'thrust_and_torque', 'direct_actuator')),
                        'Native offboard axes differ')
                preceding = [m for m in modes if m['timestamp']/1e6 <= t]
                require(preceding and t-preceding[-1]['timestamp']/1e6 <= .75,
                        'Missing/faded native control-mode evidence')
        for name, rows in data.items():
            if '/in/trajectory_setpoint' in name:
                require(not any(in_stage(m['timestamp']/1e6) for _, m in rows), 'Native trajectory override')
    else:
        from pymavlink import mavutil
        paths = list(root.rglob('*.BIN')); require(len(paths) == 1, 'Expected one native AP BIN')
        log = mavutil.mavlink_connection(str(paths[0])); native = {k: [] for k in ('GUIA', 'GUIP', 'RCOU', 'SIM2')}
        try:
            while True:
                row = log.recv_match(type=list(native))
                if row is None: break
                native[row.get_type()].append(row.to_dict())
        finally:
            log.close()
        log_identity = dict(path=str(paths[0]), sha256=digest(paths[0]))
        require(not any(in_stage(m['TimeUS']/1e6) for m in native['GUIP']), 'AP native position loop override')
        logged = []
        for m in native['GUIA']:
            if in_stage(m['TimeUS']/1e6):
                require(m['ClimbRt'] == m['RollRt'] == m['PitchRt'] == m['YawRt'] == 0, 'AP rate/altitude override')
            logged.append((m['TimeUS']/1e6, wire.q_from_euler(*(math.radians(m[k]) for k in ('Roll','Pitch','Yaw'))), m['Thrust']))
        motors = [(round(m['TimeUS']/1000), [max(0, m['C'+str(i)]-1000)/1000 for i in range(1, 5)])
                  for m in native['RCOU']]
        mappings = 0
        for m in native['SIM2']:
            tick = round(m['TimeUS']/1000)+1
            if 1 <= tick <= len(states):
                s = states[tick-1]
                require(near([m['PE'],m['PN'],-m['PD'],m['VE'],m['VN'],-m['VD']],
                             [*s['position'],*s['velocity']], 1e-4), 'AP source-derived clock mapping differs')
                mappings += 1
        require(mappings, 'Missing AP native/physical clock mapping')
        require(not any(in_stage(stamp(m)) for _, m in data.get('/ap/cmd_gps_pose', [])), 'AP GPS pose override')
    comparisons = 0
    for tick, values in motors:
        if 0 <= tick < len(originals) and in_stage(tick/1000):
            require(near(values, originals[tick][:4], 1e-6), 'Native motor output differs from original applied packet')
            comparisons += 1
    require(comparisons, 'Missing measured native motor output evidence')
    associations = []; used = set(); used_logs = set()
    for i, (row, raw, public) in enumerate(matched):
        r, p, y, thrust = public['command']['att_ref']; q = wire.native_q(wire.q_from_euler(r, p, y))
        # Bound by adjacent consumed native State timestamps, separately retained
        # from physical reference time and raw receiver monotonic timestamps.
        lo = row['native_state_stamp_s']
        hi = matched[i+1][0]['native_state_stamp_s'] if i+1 < len(matched) and matched[i+1][0]['stage'] == row['stage'] else lo+.2
        candidates = [(j, t) for j, (rr, t, qq, u) in enumerate(normalized_targets)
                      if j not in used and rr['monotonic'] >= raw['monotonic'] and lo <= t <= hi
                      and wire.q_distance(q, qq) < 1e-6 and abs(thrust-u) < 1e-6]
        require(candidates, f'No distinct native attitude CDR for PID request {row["public_request_id"]}')
        j, t = candidates[0]; used.add(j)
        execution = [index for index, (at, qq, u) in enumerate(logged) if index not in used_logs
                     and t <= at <= hi and wire.q_distance(q, qq) < 1e-6 and abs(u-thrust) < 1e-6]
        require(execution, f'No native execution log for PID request {row["public_request_id"]}')
        used_logs.add(execution[0])
        associations.append(dict(request_id=row['public_request_id'], command_id=row['public_command_id'],
                                 state_stamp_s=lo, target_stamp_s=t, interval_end_s=hi))
    for t, q, u in logged:
        if in_stage(t):
            require(any(abs(t-nt) <= .2 and nt <= t and wire.q_distance(q, nq) < 1e-6 and abs(u-nu) < 1e-6
                        for _, nt, nq, nu in normalized_targets), 'Unexplained native attitude/thrust target')
    return dict(log=log_identity, request_associations=associations, motor_comparisons=comparisons,
                exact_first_acceptance_tick_known=False, sampled_native_logs=True)


def audit(root):
    root = Path(root).resolve()
    report = dict(schema='wksim.pid.audit.v1', status='rejected', run_dir=str(root), checks={},
        protocol_sha256=PROTOCOL, auditor_sha256=digest(__file__),
        limitations=['No exact first native acceptance tick or per-message publisher GID.',
                     'Native logs and mode messages are sampled; absence between samples is unverified.',
                     'Mass is source/hash bound, not a runtime parameter getter.',
                     'No Full, UI, joint rate, UDE/NE, or motor-efficiency acceptance.'])
    try:
        result = read(root/'result.json'); report['run_id'] = result['run_id']; report['stack'] = result['stack']
        config = identity(root, result); report['checks']['identity'] = result['source_sha256']
        report['input_sha256'] = {name: digest(root/name) for name in (
            'result.json', 'admission.json', 'postflight-admission.json', 'config.json', 'pid-protocol.json',
            'pid-resolved-config.json', 'pid-progress.json', 'pid-trace.jsonl', 'prometheus.jsonl',
            'attitude-native.jsonl', 'physics-actuator-packets.jsonl', 'physics-1ms.jsonl', 'truth.jsonl',
            'disturbance-event.json')}
        progress = read(root/'pid-progress.json')
        require(progress == result['task']['external_pid'], 'Final PID progress differs from result')
        phases = {p['phase']: p for p in progress['phases']}
        require(len(phases) == len(progress['phases']), 'Duplicate phase declarations')
        event_raw = (root/'disturbance-event.json').read_bytes(); event = json.loads(event_raw)
        event_sha = event_check(event, event_raw, result['run_id'])
        require(not (root/'pid-disturbance-revoked.json').exists(), 'Disturbance revoked')
        states, originals, physical = physics(lines(root/'physics-1ms.jsonl'), lines(root/'physics-actuator-packets.jsonl'),
                                              event, event_sha, result['run_id'], result['stack'])
        require(physical['header']['observer_sha256'] == digest(root/'run-source/tools/pid_physics.py'), 'Observer header seal differs')
        report['checks']['physics'] = physical
        truth = {round(r['time']*1000): r for r in lines(root/'truth.jsonl')}
        require(truth, 'Missing sparse truth/reference cursor evidence')
        for raw in lines(root/'physics-1ms.jsonl'):
            if raw['kind'] == 'step' and raw['tick'] in truth:
                r = truth.pop(raw['tick']); v = raw['output120']
                require(r['vehicle'] == v[:60] and r['sensor'] == v[60:90] and r['time'] == v[2],
                        'Sparse reference cursor differs from full physical output')
        require(not truth, 'Sparse reference cursor outside raw physical evidence')
        report['checks']['metrics'] = fixed_metrics(config, states, phases, event)
        data, messages, recorded, codecs = wire.decode_native(root, result)
        report['checks']['raw_codecs'] = codecs
        # Reuse only the #34 raw parameter decoder, adapting the report key in memory.
        parameter_view = dict(result, task=dict(result['task'], attitude_thrust=progress))
        report['checks']['parameters'] = wire.parameters(root, parameter_view, messages)
        cal = calibration(config, read(root/'pid-resolved-config.json'), result, recorded, phases, states)
        report['checks']['calibration'] = cal
        trace_rows = list(lines(root/'pid-trace.jsonl'))
        published = [r['message'] for r in lines(root/'prometheus.jsonl') if r.get('published') == 'CommandRequest']
        for row in trace_rows:
            require(sum(p == row['public_envelope'] for p in published) == 1, 'PID public log publication missing/duplicate')
        require(len(trace_rows) == progress['pid_updates'], 'PID update trace count differs')
        matched, counts = trace_audit(config, trace_rows, phases, result, cal['hover'], data)
        report['checks']['pid_recomputed'] = counts
        report['checks']['native'] = native_audit(root, result, data, matched, phases, states, originals)
        require(result['safe_landing'] and result['children_reaped'] and not result['cleanup_errors']
                and all(x['returncode'] is not None for x in result['children'].values())
                and result['stop_kind'] == 'landed_stop' and abs(states[-1]['position'][2]) < .3,
                'Safe terminal/owned cleanup incomplete')
        final = result['task']['final']['state']
        require(not final['armed'] and abs(final['position'][2]) < .3, 'Final public state not grounded')
        require(result['status'] == 'observed' and progress['status'] == 'completed_pending_raw_audit',
                'Run ended unsuccessfully (status is necessary, never sufficient)')
        report['status'] = 'recorded_evidence_pass'
    except (Exception,) as error:
        report['failure'] = dict(type=type(error).__name__, message=str(error))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.run_dir.resolve()), 'Audit output must be outside sealed run')
    # Exclusive creation protects both prior failed audits and source evidence.
    with args.output.open('x', encoding='utf-8') as stream:
        result = audit(args.run_dir)
        result['command'] = [sys.executable, *sys.argv]
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(status=result['status'], output=str(args.output), failure=result.get('failure'))))
    return 0 if result['status'] == 'recorded_evidence_pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
