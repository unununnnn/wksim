"""Frozen #22 checks against raw model state, independent of task verdicts."""
import math


def require(value, message):
    if not value:
        raise ValueError(message)


def verify_velocity_windows(trace, report):
    stack = report['stack']
    uid = {'arducopter': 1, 'px4': 2}[stack]
    phases = {row['phase']: row for row in report['phases']}
    require(len(phases) == len(report['phases']), 'Duplicate task phase')
    previous = 0
    for phase in report['phases']:
        ns = phase['ros_time_ns']
        require(type(ns) is int and previous <= ns <= len(trace)*1_000_000
                and ns > 0 and ns % 1_000_000 == 0, 'Task phase outside ordered scene grid')
        previous = ns
        require(phase['state'] is not None and phase['state']['uav_id'] == uid,
                'Task phase vehicle identity differs')
    task = report['task']
    require(report['uav_id'] == uid and report['task_mode'] == 'initial'
            and task['run_id'] == report['run_id'] and task['protocol'] == 'session_v1',
            'Velocity task identity differs')
    requests = task['request_envelopes']
    require(len(requests) == len(task['sent']) == (10 if stack == 'arducopter' else 8),
            'Velocity public operation count differs')
    events = task['events']
    for event in events:
        require(event['version'] == 1 and event['run_id'] == report['run_id']
                and event['control_epoch'] == task['control_epoch'], 'Event identity differs')
        require(event['event'] not in ('control_revoked', 'setup_rejected'), 'Task authority was rejected/revoked')
    commands = []
    for number, request in enumerate(requests, 1):
        require(request['version'] == 1 and request['run_id'] == report['run_id']
                and request['control_epoch'] == task['control_epoch'] and request['request_id'] == number,
                'Request envelope identity/replay differs')
        body = request.get('command', request.get('setup'))
        require(body == task['sent'][number-1], 'Request differs from retained sent payload')
        matching = [e for e in events if e.get('request_id') == number]
        if 'setup' in request:
            expected = ({'cmd': 1, 'px4_mode': 'AUTO.LOITER'} if number in (1, len(requests)) else
                        {'cmd': 0, 'arming': True} if number == 2 else
                        {'cmd': 3, 'control_state': 'COMMAND_CONTROL'})
            require(all(body[k] == v for k, v in expected.items()), 'Setup payload differs')
            require(any(e['event'] == 'setup_completed' for e in matching)
                    and any(e['event'] == 'native_ack' and e['accepted'] for e in matching),
                    'Setup completion/native ACK missing')
            continue
        cid = body['command_id']
        commands.append(cid)
        phase_name = {1: 'velocity_step_accepted', 2: 'velocity_hold_accepted', 3: 'yaw_rate_accepted',
                      4: 'velocity_rehold_accepted', 5: 'invalid_combo_rejected', 6: 'land_accepted'}[cid]
        stamp = body['header']['stamp']
        stamp_ns = stamp['sec']*1_000_000_000+stamp['nanosec']
        require(0 < stamp_ns <= phases[phase_name]['ros_time_ns'], 'Command/phase scene time differs')
        if cid in (2, 3):
            anchor_phase = 'velocity_step_tracking' if cid == 2 else 'velocity_zero_hold'
            require(stamp_ns >= phases[anchor_phase]['ros_time_ns'], 'Command predates its physical anchor')
        rejected = stack == 'arducopter' and cid == 5
        relevant = [e for e in matching if e['event'] in ('command_accepted', 'command_rejected')]
        require(len(relevant) == 1 and relevant[0]['command_id'] == cid, 'Command acceptance identity differs')
        require(relevant[0]['event'] == ('command_rejected' if rejected else 'command_accepted'),
                'Command acceptance result differs')
        if rejected:
            require(relevant[0]['reason'] == 'arducopter_velocity_requires_yaw_rate_mode',
                    'Invalid-combination rejection reason differs')
        if cid == 6:
            require(body['agent_cmd'] == 3 and any(e['event'] == 'native_ack' and e['accepted']
                    and e['stage'] == 'land' for e in matching), 'LAND/native ACK differs')
        else:
            expected = [1., 0., 0.] if rejected else [.8, .4, 0.] if cid == 1 else [0., 0., 0.]
            require(body['agent_cmd'] == 4 and body['move_mode'] == 2
                    and len(body['velocity_ref']) == 3
                    and all(abs(a-b) < 1e-7 for a,b in zip(body['velocity_ref'], expected))
                    and body['yaw_rate_mode'] == (not rejected)
                    and body['yaw_rate_ref'] == (.5 if cid == 3 else 0.) and body['yaw_ref'] == 0.,
                    'Frozen velocity/yaw command differs')
    require(commands == ([1,2,3,4,5,6] if stack == 'arducopter' else [1,2,3,6]),
            'Command sequence differs')
    require(sum(e['event'] == 'command_rejected' for e in events) == (1 if stack == 'arducopter' else 0),
            'Unexpected command rejection')
    final = task['final']['state']
    require(final['uav_id'] == uid and final['connected'] and final['odom_valid'] and not final['armed']
            and abs(final['position'][2]) < .3, 'Final public grounded state differs')
    for name in ('landed_disarmed_public', 'ground_hold_completed', 'normal_stop_ready'):
        require(name in phases and not phases[name]['state']['armed'], 'Normal task exit phase missing')

    def samples(start, finish, seconds):
        require(start in phases and finish in phases, 'Missing velocity window: '+start+'/'+finish)
        lo, hi = phases[start]['ros_time_ns']//1_000_000, phases[finish]['ros_time_ns']//1_000_000
        require(hi-lo >= seconds*1000, 'Frozen velocity dwell duration not met')
        return lo, hi, trace[lo-1:hi]

    windows = []
    for start, finish, seconds, kind in (
            ('takeoff_reached', 'hold_completed', 5, 'altitude'),
            ('velocity_step_settled', 'velocity_step_tracking', 3, 'velocity'),
            ('velocity_hold_settled', 'velocity_zero_hold', 4, 'zero_hold'),
            ('velocity_zero_hold', 'yaw_rate_tracking', 4, 'yaw_rate'),
            *((('invalid_combo_rejected', 'invalid_combo_no_side_effects', 2, 'invalid_combo'),)
              if stack == 'arducopter' else ())):
        lo, hi, rows = samples(start, finish, seconds)
        metrics = dict(kind=kind, from_ns=lo*1_000_000, to_ns=hi*1_000_000, samples=len(rows))
        if kind == 'altitude':
            error = max(abs(row[8]+3.) for row in rows)
            require(error <= .6, stack+' altitude independent truth failed')
            metrics['max_error_m'] = error
        elif kind == 'velocity':
            error = max(max(abs(row[4]-.8), abs(row[3]-.4), abs(row[5])) for row in rows)
            require(error <= .3, stack+' velocity independent truth failed')
            metrics['max_axis_error_m_s'] = error
        elif kind in ('zero_hold', 'invalid_combo'):
            speed = max(math.hypot(*row[3:6]) for row in rows)
            require(speed <= .25, stack+' '+kind+' independent speed failed')
            metrics['max_speed_m_s'] = speed
            if kind == 'zero_hold':
                anchor = trace[phases['velocity_step_tracking']['ros_time_ns']//1_000_000-1][6:9]
                drift = max(math.dist(row[6:9], anchor) for row in rows)
                require(drift <= 1., stack+' zero hold independent drift failed')
                metrics['max_drift_m'] = drift
        else:
            # Vehicle ABI attitude[2] is NED yaw. Unwrap each raw 1 ms increment;
            # ENU yaw advances with the opposite sign, including across +/-pi.
            advance = 0.
            error = 0.
            previous = rows[0][11]
            for index, row in enumerate(rows):
                advance -= (row[11]-previous+math.pi) % (2*math.pi)-math.pi
                previous = row[11]
                error = max(error, abs(advance-.5*index/1000))
            require(error <= .35, stack+' yaw integral independent truth failed')
            metrics['max_integral_error_rad'] = error
        windows.append(metrics)
    return windows
