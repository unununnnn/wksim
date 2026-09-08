"""Independent model truth for completed public tasks in one formal epoch."""
import json
import math


def final_run_status(epochs):
    """Completed windows cannot clear an active fault; recovered history can."""
    final=epochs[-1]['result']
    if final['status']=='stopped' and any(row['result'].get('flight_completed') for row in epochs):
        return 'failed' if final.get('authority',{}).get('fault') else 'pass'
    return final['status']


def verify_tasks(directory,epoch,total_ticks,reports,task_type='public_position'):
    if task_type not in ('public_position','public_velocity_yaw'):
        raise ValueError('Unknown public task audit type')
    completed=[report for report in reports.values() if report['status']=='pass']
    if not completed:
        return None
    by_stack={stack:[report for report in completed if report['stack']==stack] for stack in ('arducopter','px4')}
    if not all(by_stack.values()):
        return None
    proof={}
    for stack,values in by_stack.items():
        trace=[]
        for tick,line in enumerate((directory/(stack+'-truth.jsonl')).open(),1):
            row=json.loads(line)
            if (row['epoch']!=epoch or row['tick']!=tick or len(row['state'])!=120
                    or not all(math.isfinite(value) for value in row['state'])
                    or abs(row['state'][2]-tick/1000)>1e-8):
                raise ValueError('Joint model identity/time/numeric evidence differs')
            trace.append(row['state'])
        if len(trace)!=total_ticks or not trace or abs(trace[-1][8])>=.3:
            raise ValueError('Completed task lacks complete landed model truth')
        windows=[]
        for report in values:
            if report['scene_epoch']!=epoch:
                raise ValueError('Task evidence crossed scene epoch')
            if task_type=='public_velocity_yaw':
                from .velocity_evidence import verify_velocity_windows
                windows.extend(verify_velocity_windows(trace,report))
                continue
            phases={row['phase']:row for row in report['phases']}
            if report['task_mode']=='initial':
                specs=[('takeoff_reached','hold_completed',5,'altitude'),
                       ('waypoint_reached','waypoint_completed',2,'waypoint')]
            else:
                specs=[('airborne_recovery_state_confirmed','airborne_recovery_hold_completed',2,'recovery')]
            for start,finish,seconds,kind in specs:
                lo,hi=phases[start]['ros_time_ns'],phases[finish]['ros_time_ns']
                if hi-lo<seconds*10**9:
                    raise ValueError('Task dwell did not cover its required common time')
                rows=trace[max(0,lo//1_000_000-1):hi//1_000_000]
                if not rows:
                    raise ValueError('Missing independent dwell samples')
                if kind=='recovery':
                    point=phases[start]['state']['position']
                    target=[point[1],point[0],-point[2]]
                else:
                    target=[3.,2.,-3.]
                error=max(abs(row[8]+3.) if kind=='altitude' else math.dist(row[6:9],target) for row in rows)
                speed=max(math.hypot(*row[3:6]) for row in rows)
                if error>(.6 if kind=='altitude' else .5) or kind=='recovery' and speed>.5:
                    raise ValueError(f'{stack} {kind} independent truth failed: {error}, {speed}')
                windows.append(dict(kind=kind,from_ns=lo,to_ns=hi,max_error_m=error,max_speed_m_s=speed))
        proof[stack]=dict(records=len(trace),final_height_m=-trace[-1][8],windows=windows)
    return proof
