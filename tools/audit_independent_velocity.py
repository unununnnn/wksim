"""Audit actual independent 50 Hz model records, not a synthetic joint grid."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def require(value,message):
    if not value:raise ValueError(message)


def audit(root,*,verify_sources=True):
    root=Path(root)
    wrapper=json.loads((root/'independent-velocity.json').read_text())
    result=wrapper['runtime_result']
    task=result['task'];stack=result['stack']
    directory=root/result['run_id']
    recorded=json.loads((directory/'result.json').read_text())
    require(json.dumps(recorded,sort_keys=True)==json.dumps(result,sort_keys=True)
            and wrapper['config']==result['config'],'Wrapper/formal result or configuration differs')
    require(result['preflight']['ok'] and result['config']['runtime_profile']=='independent_quad_dds_v1',
            'Independent resource admission missing')
    require(result['fc_sha256']==result['preflight']['identities']['firmware']['expected_sha256'],
            'Actual firmware hash differs from admission')
    require(wrapper['status']==result['status']=='pass' and result['safe_landing']
            and result['children_reaped'] and result['cleanup_errors']==[], 'Independent flight/cleanup failed')
    require(all(c['returncode'] is not None for c in result['children'].values()),'Child exit missing')
    require(task['protocol']=='session_v1' and task['run_id']==result['run_id'],'Task identity differs')
    trace=[json.loads(line) for line in (directory/'truth.jsonl').read_text().splitlines()]
    require(all(math.isfinite(r['time']) and all(math.isfinite(v) for v in r['vehicle']) for r in trace),
            'Non-finite physical state')
    require(all(a['time']<b['time'] for a,b in zip(trace,trace[1:])),'Physical time not increasing')
    phase_list=task['independent_velocity']['phases']
    phases={p['phase']:p for p in phase_list}
    require(len(phases)==len(phase_list),'Duplicate phase')
    previous=0
    for p in phase_list:
        cursor=p['physical_cursor'];count=cursor['records']
        require(previous<=count<=len(trace) and count>0,'Physical cursor order differs')
        require(trace[count-1]['time']==cursor['final_time'] and -trace[count-1]['vehicle'][8]==cursor['final_height_m'],
                'Physical cursor relabelled')
        require(p['state']['uav_id']==1 and p['native_boot_s']>0,'Independent native identity differs')
        previous=count
    require(all(a['observed_monotonic_s']<b['observed_monotonic_s'] for a,b in zip(phase_list,phase_list[1:])),
            'Phase observations not ordered')
    public=[json.loads(line) for line in (directory/'prometheus.jsonl').read_text().splitlines()]
    requests=task['request_envelopes']
    require(requests==[r['message'] for r in public if r.get('request_envelope')], 'Published envelope evidence differs')
    require(len(requests)==len(task['sent'])==13,'Complete supported profile operation count differs')
    require(all(e['run_id']==result['run_id'] and e['control_epoch']==task['control_epoch'] for e in task['events']),
            'Event run/epoch differs')
    raw_events=[json.loads(r['message']['message']) for r in public if r.get('topic','').endswith('/text_info')]
    cursor=0
    for event in task['events']:
        while cursor<len(raw_events) and raw_events[cursor]!=event:cursor+=1
        require(cursor<len(raw_events),'Reported event absent from ordered raw public log')
        cursor+=1
    require(not any(e['event'] in ('control_revoked','setup_rejected') for e in task['events']), 'Control authority failed')
    command_ids=[]
    for number,request in enumerate(requests,1):
        require(request['request_id']==number and request['version']==1 and request['run_id']==result['run_id']
                and request['control_epoch']==task['control_epoch'],'Request identity differs')
        body=request.get('command',request.get('setup'))
        require(body==task['sent'][number-1], 'Sent payload differs')
        matching=[e for e in task['events'] if e.get('request_id')==number]
        if 'setup' in request:
            expected=({'cmd':1,'px4_mode':'AUTO.LOITER'} if number in (1,13) else
                      {'cmd':0,'arming':True} if number==2 else {'cmd':3,'control_state':'COMMAND_CONTROL'})
            require(all(body[k]==v for k,v in expected.items()),'Setup differs')
            require(any(e['event']=='setup_completed' for e in matching) and
                    any(e['event']=='native_ack' and e['accepted'] for e in matching),'Setup ACK/completion missing')
            continue
        cid=body['command_id'];command_ids.append(cid)
        rejected=stack=='arducopter' and cid==6
        outcomes=[e for e in matching if e['event'] in ('command_accepted','command_rejected')]
        require(len(outcomes)==1 and outcomes[0]['command_id']==cid and
                outcomes[0]['event']==('command_rejected' if rejected else 'command_accepted'),'Command acceptance differs')
        if rejected:
            require(outcomes[0]['reason']=='arducopter_velocity_requires_yaw_rate_mode','Wrong capability rejection')
        if cid==9:
            require(body['agent_cmd']==3 and any(e['event']=='native_ack' and e['accepted'] and e['stage']=='land'
                    for e in matching),'LAND ACK missing')
        elif cid==1:
            require(body['agent_cmd']==4 and body['move_mode']==0 and body['position_ref']==[2.,3.,3.],
                    'Position baseline differs')
        else:
            velocity=([1.,0.,0.] if rejected else [.8,.4,0.] if cid in (2,7) or (stack=='px4' and cid==5) else [0.,0.,0.])
            angle=stack=='px4' and cid in (5,6)
            require(body['agent_cmd']==4 and body['move_mode']==(4 if cid in (7,8) else 2)
                    and len(body['velocity_ref'])==3
                    and all(abs(a-b)<1e-7 for a,b in zip(body['velocity_ref'],velocity))
                    and body['yaw_rate_mode']==(not rejected and not angle)
                    and body['yaw_rate_ref']==(.5 if cid==4 else 0.)
                    and abs(body['yaw_ref']-(.6 if angle else 0.))<1e-7,'Frozen velocity/angle/body payload differs')
    require(command_ids==list(range(1,10)),'Command sequence differs')
    require(sum(e['event']=='command_rejected' for e in task['events'])==(1 if stack=='arducopter' else 0),
            'Unexpected command rejection')
    require(task['final']['state']['uav_id']==1 and not task['final']['state']['armed']
            and abs(trace[-1]['vehicle'][8])<.3,'Final independent ground state differs')

    windows=[]
    cases=[('position_baseline_reached','position_baseline_dwell',2,'position'),
           ('velocity_step_settled','velocity_step_tracking',3,'world'),
           ('velocity_hold_settled','velocity_zero_hold',4,'zero'),
           ('velocity_zero_hold','yaw_rate_tracking',4,'yaw_rate')]
    if stack=='px4':
        cases += [('angle_velocity_settled','angle_velocity_tracking',3,'angle'),
                  ('angle_hold_settled','angle_zero_hold',4,'angle_zero')]
    else:
        cases += [('invalid_combo_rejected','invalid_combo_no_side_effects',2,'invalid')]
    cases += [('body_velocity_settled','body_velocity_tracking',3,'body'),
              ('body_hold_settled','body_zero_hold',4,'body_zero')]
    for first,last,minimum,kind in cases:
        lo=phases[first]['physical_cursor']['records'];hi=phases[last]['physical_cursor']['records']
        samples=trace[lo:hi]
        require(len(samples)>=2,'Insufficient independent samples')
        duration=samples[-1]['time']-samples[0]['time']
        require(duration>=minimum,'Frozen physical minimum dwell not met: '+kind)
        require(max(b['time']-a['time'] for a,b in zip(samples,samples[1:]))<=.021,
                'Physical sample gap exceeds the configured 20ms trace cadence')
        metrics=dict(kind=kind,start_record_exclusive=lo,end_record_inclusive=hi,samples=len(samples),duration_s=duration)
        if kind in ('world','body','angle'):
            error=0.;yaw_error=0.
            for row in samples:
                v=row['vehicle'];velocity=(v[4],v[3],-v[5]);yaw=math.pi/2-v[11]
                if kind=='body':
                    c,s=math.cos(yaw),math.sin(yaw)
                    velocity=(c*velocity[0]+s*velocity[1],-s*velocity[0]+c*velocity[1],velocity[2])
                error=max(error,max(abs(a-b) for a,b in zip(velocity,(.8,.4,0.))))
                yaw_error=max(yaw_error,abs(math.remainder(yaw-.6,2*math.pi)))
            require(error<=.3,'Independent velocity gate failed: '+kind)
            metrics['max_axis_error_m_s']=error
            if kind=='angle':
                require(yaw_error<=.15,'Independent yaw angle gate failed')
                metrics['max_yaw_error_rad']=yaw_error
        elif kind in ('zero','angle_zero','body_zero','invalid'):
            speed=max(math.hypot(*r['vehicle'][3:6]) for r in samples)
            require(speed<=.25,'Independent zero/rejection speed failed')
            metrics['max_speed_m_s']=speed
            if kind!='invalid':
                anchor_phase={'zero':'velocity_step_tracking','angle_zero':'angle_velocity_tracking','body_zero':'body_velocity_tracking'}[kind]
                anchor=trace[phases[anchor_phase]['physical_cursor']['records']-1]['vehicle'][6:9]
                drift=max(math.dist(r['vehicle'][6:9],anchor) for r in samples)
                require(drift<=1.,'Independent zero drift failed')
                metrics['max_drift_m']=drift
            if kind=='angle_zero':
                yaw_error=max(abs(math.remainder(math.pi/2-r['vehicle'][11]-.6,2*math.pi)) for r in samples)
                require(yaw_error<=.15,'Independent zero-hold yaw angle failed')
                metrics['max_yaw_error_rad']=yaw_error
        elif kind=='position':
            error=max(math.dist((r['vehicle'][7],r['vehicle'][6],-r['vehicle'][8]),(2.,3.,3.)) for r in samples)
            speed=max(math.hypot(*r['vehicle'][3:6]) for r in samples)
            yaw=max(abs(math.remainder(math.pi/2-r['vehicle'][11],2*math.pi)) for r in samples)
            require(error<=.5 and speed<=.5 and yaw<=.15,'Independent position baseline failed')
            metrics.update(max_position_error_m=error,max_speed_m_s=speed,max_yaw_error_rad=yaw)
        else:
            previous=samples[0]['vehicle'][11];advance=0.;error=0.
            for row in samples:
                yaw=row['vehicle'][11]
                advance-=math.remainder(yaw-previous,2*math.pi);previous=yaw
                error=max(error,abs(advance-.5*(row['time']-samples[0]['time'])))
            require(error<=.35,'Independent yaw integral failed')
            metrics['max_integral_error_rad']=error
        windows.append(metrics)
    if verify_sources:
        repo=Path(__file__).resolve().parents[1]
        for name,digest in result['runtime_sha256'].items():
            require(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,'Runtime source changed: '+name)
        for name,digest in wrapper['sources_sha256'].items():
            require(hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,'Driver source changed: '+name)
        for name,digest in result['product_sha256'].items():
            require(hashlib.sha256((repo/'ros2/src/prometheus_control/prometheus_control'/name).read_bytes()).hexdigest()==digest,
                    'Installed product source changed: '+name)
    return dict(status='pass',run_id=result['run_id'],stack=stack,windows=windows,requests=len(requests),
                final_height_m=-trace[-1]['vehicle'][8],scope='independent task control; no joint rate acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);args=parser.parse_args()
    print(json.dumps(audit(args.root),indent=2))
