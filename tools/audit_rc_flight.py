"""Independent raw RC integrator, native DDS and physical-flight audit.

Never import the product RC integrator or treat the task's success as evidence.
Run in the recorded ROS message overlays to decode actual retained CDR.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    with Path(path).open() as source:
        for line in source:
            require(line.endswith('\n'), 'Incomplete raw record: '+str(path))
            yield json.loads(line)


def physical(row):
    v = row['vehicle']
    return dict(time=row['time'], position=[v[7], v[6], -v[8]], velocity=[v[4], v[3], -v[5]],
                yaw=math.remainder(math.pi/2-v[11], 2*math.pi))


def audit(root):
    root = Path(root)
    result = json.loads((root/'result.json').read_text())
    require(result['status'] == 'observed' and result['safe_landing'] and result['children_reaped']
            and not result['cleanup_errors'] and result['source_unchanged'] and result['candidate_unchanged'],
            'Run/cleanup/identity did not complete')
    for name, checksum in result['source_sha256'].items():
        require(digest(root/'run-source'/name) == checksum, 'Retained source differs: '+name)
    require(result['actual_control_sha256'] == result['admission']['control']['python_sha256'], 'Control install differs')
    events = []
    for line in (root/'control.log').read_text().splitlines():
        start = line.find('{"event":')
        if start >= 0:
            events.append(json.loads(line[start:]))
    require(events and all(a['event_id']+1 == b['event_id'] for a,b in zip(events,events[1:])), 'Incomplete Control event sequence')
    frames, targets, activations, revokes, windows = {}, [], [], [], []
    target = None
    last_op = None
    stream = None
    for event in events:
        require(event['run_id'] == result['run_id'], 'Foreign event run')
        if event['event'] == 'rc_frame' and event['accepted']:
            frame = json.loads(event['raw'])
            require(frame['source'] == 'wksim-software-rc-v1' and len(frame['channels_us']) == 8,
                    'Wrong RC envelope')
            require(frame['run_id'] == result['run_id'] and frame['control_epoch'] == event['control_epoch'], 'Foreign frame identity')
            require(0 <= event['received_monotonic_ns']-frame['produced_monotonic_ns'] <= 1_500_000_000, 'Accepted stale/future frame')
            frames[(frame['stream_id'], frame['sequence'])] = (frame, event)
        elif event['event'] == 'setup_completed' and event.get('control_state') == 'RC_POS_CONTROL' and not event.get('unchanged'):
            activations.append(event)
            windows.append([event['emitted_unix_ns'], None])
            stream = event['rc_stream_id']
            target = list(event['position_enu_m'])+[event['yaw_enu_rad']]
            last_op = None
        elif event['event'] == 'control_revoked':
            revokes.append(event)
            if windows and windows[-1][1] is None:
                windows[-1][1] = event['emitted_unix_ns']
            target = None
        elif event['event'] == 'setup_completed' and event.get('control_state') == 'COMMAND_CONTROL':
            if windows and windows[-1][1] is None:
                windows[-1][1] = event['emitted_unix_ns']
            target = None
        elif event['event'] == 'rc_integrated':
            require(target is not None and event['stream_id'] == stream, 'RC output without explicit active owner')
            frame, received = frames[(stream, event['sequence'])]
            require(event['publisher_gid'] == received['publisher_gid'], 'RC writer changed')
            dt = event['dt_s']
            require(0 <= dt <= .05 and (dt == 0 if last_op is None else abs(dt-(event['operation_ns']-last_op)/1e9)<1e-10), 'RC integration dt mismatch')
            require(0 <= event['serviced_monotonic_ns']-frame['produced_monotonic_ns'] <= 1_501_000_000,
                    'Expired RC output')
            pwm = frame['channels_us']
            require(all(type(p) is int and 1000 <= p <= 2000 for p in pwm), 'Illegal accepted PWM')
            normalized = []
            for p in pwm[:4]:
                u = (p-1500)/500
                normalized.append(0. if abs(u)<=.05 else math.copysign((abs(u)-.05)/.95, u))
            require(all(abs(a-b)<1e-12 for a,b in zip(normalized,event['normalized'])), 'Deadzone mismatch')
            d = normalized if pwm[5] == 1500 else [0.]*4
            target = [target[0]+d[1]*1.5*dt, target[1]-d[0]*1.5*dt,
                      max(.2,target[2]+d[2]*1.3*dt), target[3]-d[3]*1.5*dt]
            require(max(abs(a-b) for a,b in zip(target,event['position']+[event['yaw']])) < 1e-9, 'RC integration mismatch')
            targets.append(event)
            last_op = event['operation_ns']
    require(activations and len(targets)>30, 'Missing sustained RC activation/output')
    # Decode retained middleware bytes independently of the runtime's decoded copy.
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rclpy.serialization import deserialize_message
    raw = list(lines(root/'rc-dds.jsonl'))
    observed_frames = {(row['message']['data'],row['publisher_gid']) for row in raw if row['topic'].endswith('/v2/rc_input')}
    for _, accepted in frames.values():
        decoded=deserialize_message(bytes.fromhex(accepted['cdr_hex']),get_message('std_msgs/msg/String'))
        require(decoded.data == accepted['raw'] and (decoded.data,accepted['publisher_gid']) in observed_frames,
                'Accepted RC input absent from independent CDR/GID observation')
    native = []
    for row in raw:
        message = message_to_ordereddict(deserialize_message(bytes.fromhex(row['cdr_hex']), get_message(row['type'])))
        require(json.dumps(message,sort_keys=True)==json.dumps(row['message'],sort_keys=True), 'CDR differs from decoded evidence')
        if '/in/trajectory_setpoint' in row['topic'] or row['topic']=='/ap/cmd_gps_pose':
            native.append(row)
    require(len(native)>30, 'Missing actual native DDS targets')
    require(len({row['publisher_gid'] for row in native})==1, 'Multiple native target writers')
    setups=[row['message'] for row in raw if row['topic'].endswith('/v2/setup')]
    for activation in activations:
        matching=[request for request in setups if request['run_id']==activation['run_id']
                  and request['control_epoch']==activation['control_epoch']
                  and request['request_id']==activation['request_id']
                  and request['setup']['control_state']=='RC_POS_CONTROL']
        require(len(matching)==1, 'RC activation lacks unique raw explicit setup')
    require(all(end is not None for _,end in windows), 'Unclosed RC authority window')
    homes = [row for row in raw if row['topic']=='/ap/wksim/local_state_v1' and row['message']['home_valid']]
    matched = 0
    for start,end in windows:
        observations = [row for row in native if start+100_000_000 < row['source_timestamp'] < end]
        require(len(observations)>=max(1,int((end-start-100_000_000)/100_000_000)),
                'Missing native targets during active RC window')
        for row in observations:
            recent = [e for e in targets if 0 <= row['source_timestamp']-e['emitted_unix_ns'] < 150_000_000]
            msg = row['message']
            if result['stack']=='px4':
                def matches(e):
                    p=e['position']; desired=[p[1],p[0],-p[2]]
                    return (max(abs(a-b) for a,b in zip(msg['position'],desired))<1e-5
                            and abs(math.remainder(msg['yaw']-(math.pi/2-e['yaw']),2*math.pi))<1e-5)
            else:
                prior = [h for h in homes if h['source_timestamp'] <= row['source_timestamp']]
                require(prior, 'Missing actual AP home before target')
                home = prior[-1]['message']
                def matches(e):
                    east,north,up=e['position']
                    lat=home['home_latitude_e7']+int(north/.011131884502145034)
                    mid=(lat+home['home_latitude_e7'])/2e7
                    lon=home['home_longitude_e7']+int(east/(.011131884502145034*math.cos(math.radians(mid))))
                    return (msg['type_mask']==0x9F8 and msg['coordinate_frame']==6
                            and abs(msg['latitude']-lat/1e7)<1e-8 and abs(msg['longitude']-lon/1e7)<1e-8
                            and abs(msg['altitude']-up)<1e-5
                            and abs(math.remainder(msg['yaw']-e['yaw'],2*math.pi))<1e-5)
            require(any(matches(e) for e in recent), 'Native target not derived from active RC input')
            matched += 1
        mode_rows = [row for row in raw if start+100_000_000 < row['source_timestamp'] < end and
                     ('/out/vehicle_status' in row['topic'] or row['topic']=='/ap/status')]
        if not mode_rows:
            prior=[row for row in raw if start-250_000_000 <= row['source_timestamp'] <= start+100_000_000 and
                   ('/out/vehicle_status' in row['topic'] or row['topic']=='/ap/status')]
            mode_rows=prior[-1:]
        require(mode_rows, 'Missing native mode feedback during RC')
        changed=[row for row in mode_rows if not (row['message']['nav_state']==14
                 if result['stack']=='px4' else row['message']['mode']==4)]
        # External mode feedback necessarily precedes the observing Control's
        # withdrawal event. Only that final service interval may contain it.
        if changed:
            require(result['scenario']=='mode-out' and all(
                end-50_000_000 <= row['source_timestamp'] <= end for row in changed)
                and any(e['reason']=='external_mode_left_no_automatic_reacquisition'
                        and e['emitted_unix_ns']==end for e in revokes),
                    'Native mode left without timely RC withdrawal')
    for event in revokes:
        if event['reason'] not in ('rc_input_revoked:input_expired','explicit_native_mode_exit',
                                  'external_mode_left_no_automatic_reacquisition'):
            require(False, 'Unexpected control withdrawal: '+event['reason'])
        after = event['emitted_unix_ns']
        next_setup = min((e['emitted_unix_ns'] for e in events if e['event']=='setup_received'
                          and e['emitted_unix_ns']>after), default=2**63-1)
        require(not any(after+100_000_000 < row['source_timestamp'] < next_setup for row in native),
                'Native target publication continued after RC withdrawal')
    trace = [physical(row) for row in lines(root/'truth.jsonl')]
    require(all(a['time']<b['time'] for a,b in zip(trace,trace[1:])), 'Physical clock not monotonic')
    require(all(math.isfinite(v) for row in trace for v in (*row['position'],*row['velocity'],row['yaw'])), 'Nonfinite truth')
    phases = result['task']['rc']['phases']
    by_time={row['time']:row for row in trace}
    for entry in phases:
        cursor=entry['truth']
        require(cursor is not None and cursor['time'] in by_time, 'Physical phase cursor absent from raw trajectory')
        actual=by_time[cursor['time']]
        require(max(abs(a-b) for key in ('position','velocity') for a,b in zip(cursor[key],actual[key]))<1e-10
                and abs(math.remainder(cursor['yaw']-actual['yaw'],2*math.pi))<1e-9, 'Physical phase cursor relabelled')
    require(all(a['monotonic_ns']<b['monotonic_ns'] and a['truth']['time']<=b['truth']['time']
                for a,b in zip(phases,phases[1:])), 'Physical phase cursor order differs')
    def phase(name, last=False):
        values = [p for p in phases if p['phase']==name]
        require(values, 'Missing phase '+name)
        return values[-1 if last else 0]
    metrics = {}
    if result['scenario'] != 'yaw':
        a,b=phase('movement_begin',True),phase('movement_end',True)
        delta=b['truth']['position'][0]-a['truth']['position'][0]
        require(delta>(.5 if result['scenario'] in ('movement','recenter') else .3), 'No physical +X RC motion')
        metrics['movement_x_m']=delta
    if result['scenario']=='recenter':
        a,b=phase('hold_begin'),phase('hold_end')
        samples=[row for row in trace if a['truth']['time']<=row['time']<=b['truth']['time']]
        require(samples[-1]['time']-samples[0]['time']>=3.8, 'Insufficient physical hold window')
        speed=max(math.hypot(*row['velocity']) for row in samples)
        drift=max(math.dist(row['position'],samples[0]['position']) for row in samples)
        require(speed<=.25 and drift<=1., 'Physical recenter hold failed')
        metrics.update(hold_speed_mps=speed,hold_drift_m=drift)
    if result['scenario']=='yaw':
        a,b=phase('yaw_begin'),phase('yaw_end')
        delta=math.remainder(b['truth']['yaw']-a['truth']['yaw'],2*math.pi)
        require(delta<-.3, 'No physical negative yaw motion')
        metrics['yaw_delta_rad']=delta
        final_targets=[e for e in targets if e['serviced_monotonic_ns']<=b['monotonic_ns']]
        heading_error=abs(math.remainder(b['truth']['yaw']-final_targets[-1]['yaw'],2*math.pi))
        require(heading_error<=.35, 'Physical yaw does not track integrated target')
        metrics['yaw_target_error_rad']=heading_error
    if result['scenario'] in ('stream-stall','new-takeover'):
        require(any(e['reason']=='rc_input_revoked:input_expired' for e in revokes), 'Missing timeout withdrawal')
        require(any(e['event']=='rc_frame' and e.get('reason')=='retired_stream' for e in events), 'Missing old-stream rejection')
        withdrawal=next(e for e in revokes if e['reason']=='rc_input_revoked:input_expired')
        last_input=max(frame['produced_monotonic_ns'] for frame,accepted in frames.values()
                       if accepted['emitted_monotonic_ns']<withdrawal['emitted_monotonic_ns'])
        expiry_seconds=(withdrawal['emitted_monotonic_ns']-last_input)/1e9
        require(1.5<expiry_seconds<=1.55, 'RC expiry was not serviced within one maximum integration interval')
        a,b=phase('stall_revoked'),phase('retired_stream_observed')
        metrics.update(expiry_seconds=expiry_seconds,
            post_withdraw_motion_m=math.dist(a['truth']['position'],b['truth']['position']),
            post_withdraw_final_speed_mps=math.hypot(*b['truth']['velocity']))
    if result['scenario']=='mode-out':
        require(any(e['reason'] in ('explicit_native_mode_exit','external_mode_left_no_automatic_reacquisition')
                    for e in revokes), 'Missing mode exit withdrawal')
        phase('mode_out_observed')
        external=any(p['phase']=='external_mode_request' for p in phases)
        if external:
            require(any(e['reason']=='external_mode_left_no_automatic_reacquisition' for e in revokes), 'External mode did not withdraw RC')
            expected=4 if result['stack']=='px4' else 17
            observed=phase('mode_out_observed')['monotonic_ns']
            modes=[r for r in raw if observed-2_000_000_000 <= r['monotonic_ns'] <= observed and
                   ('/out/vehicle_status' in r['topic'] or r['topic']=='/ap/status')]
            require(modes and all(r['message']['nav_state']==expected if result['stack']=='px4'
                                 else r['message']['mode']==expected for r in modes), 'External native mode feedback missing')
        metrics['mode_exit_source']='external_native_probe' if external else 'explicit_public_setup'
    if result['scenario']=='new-takeover':
        require(len({e['rc_stream_id'] for e in activations})>=3, 'Missing fresh explicit takeover streams')
        phase('command_handoff')
    require(abs(trace[-1]['position'][2])<.3, 'Physical landing missing')
    return dict(status='pass', scope='RC candidate raw audit; no joint-rate or Full claim',
                stack=result['stack'], scenario=result['scenario'], metrics=metrics,
                raw_cdr_records=len(raw), native_target_records=len(native), matched_native_targets=matched, integrated_steps=len(targets),
                result_sha256=digest(root/'result.json'), audit_sha256=digest(__file__))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output.exists() and not args.output.resolve().is_relative_to(args.root.resolve()), 'Use fresh external audit output')
    try:
        result=audit(args.root)
    except Exception as error:
        result=dict(status='failed',error=repr(error),audit_sha256=digest(__file__))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return 0 if result['status']=='pass' else 1


if __name__=='__main__': raise SystemExit(main())
