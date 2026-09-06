"""Joint public flight plus real pause/step/resume/permission evidence audit."""
import argparse
import json
from pathlib import Path

from audit_joint_flight import audit as audit_flight, digest, lines, require


def audit(root, verify_current_sources=False):
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String
    report=audit_flight(root, verify_current_sources)
    result=json.loads((root/'result.json').read_text())
    lifecycle=result['scene_lifecycle']; epoch=result['scene_epoch']
    require(result['scene_lifecycle_requested'] and not result['pause_probe_requested']
            and lifecycle['status']=='pass','Not a completed lifecycle flight')
    require((lifecycle['approved_lease_period_s'],lifecycle['approved_lease_s'],lifecycle['resume_wait_s'])==(.1,.5,5),
            'Approved supervision numbers changed')
    events=lifecycle['events']
    require([event['action'] for event in events]==['first_pause','single_step','second_pause','resume'],
            'Lifecycle sequence incomplete')
    wanted={}
    for event in events[:3]:
        before,after=event['before'],event['after']
        for snapshot in (before,after):
            tick=snapshot['authority']['tick']
            require(snapshot['authority']['epoch']==epoch and snapshot['authority']['phase']=='paused'
                    and snapshot['authority']['last_barrier_tick']==tick and tick%4==0,
                    'Lifecycle did not reach a synchronized paused boundary')
            for stack,model in snapshot['models'].items():
                require(model['epoch']==epoch and model['tick']==tick,'Model snapshot has wrong scene tick')
                wanted[(stack,tick)]=model['state']
        if event['action']=='single_step':
            require(after['authority']['tick']==before['authority']['tick']+4,'Single step was not exactly 4ms')
        else:
            require(event['wall_seconds']>=4 and before['models']==after['models']
                    and before['authority']==after['authority'],'Pause advanced physics or was too short')
            require(all(-model['state'][8]>=2.5 for model in before['models'].values()),'Pause was not airborne')
            require(set(event['control_ack'])=={'1','2'},'Missing dual control acknowledgement')
            for uid,value in event['control_ack'].items():
                require(value['scene_epoch']==epoch and value['uav_id']==int(uid) and value['ready']
                        and value['phase']=='paused' and value['request_id']==before['authority']['last_request_id'],
                        'Wrong pause acknowledgement identity')
    require(events[0]['after']==events[1]['before'],'Single step did not begin at prior frozen state')
    require(events[1]['after']['models']==events[2]['before']['models'],'Second pause moved before its snapshot')
    for stack in ('arducopter','px4'):
        for row in lines(root/(stack+'-truth.jsonl')):
            key=(stack,row['tick'])
            if key in wanted:
                require(wanted.pop(key)==row['state'],'Lifecycle snapshot differs from raw actual model state')
    require(not wanted,'Missing physical trace for lifecycle boundary')
    resume=events[3]
    require(resume['frozen_tick']==events[2]['after']['authority']['tick']
            and resume['resume_tick']>resume['frozen_tick'],'No actual resumption of scene time')
    require(set(resume['control_ack'])=={'1','2'},'Missing dual fresh resume acknowledgement')
    for value in resume['control_ack'].values():
        require(value['phase']=='resuming' and value['request_id']==3 and value['ready']
                and value['source_boot_ns']>resume['frozen_tick']*1000000,'Old sample accepted for resume')

    sequence=0; last_tick=0; last_issued=None; max_gap=0; phases=[]; raw_acks=[]; repeats=0
    for row in lines(root/'scene-lifecycle.jsonl'):
        require(row['epoch']==epoch,'Scene evidence crossed epoch')
        if row['kind']=='permission':
            value=row['message']
            require(json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),String).data)==value,
                    'Raw lifecycle CDR differs from permission record')
            require(value['version']==1 and value['run_id']==result['run_id'] and value['scene_epoch']==epoch
                    and value['sequence']==sequence+1 and value['tick']==row['tick']>=last_tick
                    and value['time_ns']==value['tick']*1000000 and value['lease_seconds']==.5,
                    'Lease identity/time/count differs')
            if last_issued is not None:
                gap=value['issued_monotonic_s']-last_issued
                require(gap>=0,'Permission wall clock regressed')
                max_gap=max(max_gap,gap)
            if value['phase'] in ('paused','stepping','resuming') and last_issued is not None:
                require(gap<=.5,'Permission expired during lifecycle operation')
            sequence,last_tick,last_issued=value['sequence'],value['tick'],value['issued_monotonic_s']
            if not phases or phases[-1]!=value['phase']: phases.append(value['phase'])
        elif row['kind']=='ack_raw':
            value=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),String).data)
            require(value['scene_epoch']==epoch and value['run_id']==result['run_id']
                    and value['uav_id']==row['uav_id'],'Native scene ack raw identity differs')
            raw_acks.append(value)
        elif row['kind']=='paused_clock':
            repeats+=1
    require(phases==['running','paused','stepping','paused','resuming','running'], 'Permission phases differ')
    for event in (events[0],events[2],events[3]):
        for value in event['control_ack'].values():
            require(value in raw_acks,'Summary acknowledgement absent from actual raw DDS')
    task_phases={}
    for stack in ('arducopter','px4'):
        phases=[]; suspended=False
        for row in lines(root/stack/'prometheus.jsonl'):
            if 'scene_event' in row:
                phase=row['scene_event']; phases.append(phase)
                suspended=phase!='running'
            if suspended:
                require('published' not in row and 'public_payload' not in row,
                        'Task replayed/dispatched high-level operation during suspension')
        require(phases==['running','paused','stepping','paused','resuming','running'],
                'Task did not observe the full lifecycle')
        task_phases[stack]=phases
    report.update(scope='real joint public Task flight with approved healthy pause/4ms step/explicit resume; not complete G2',
        lifecycle=dict(events=events, raw_permissions=sequence, raw_control_acknowledgements=len(raw_acks),
            paused_clock_republications=repeats, maximum_permission_gap_s=max_gap, task_phases=task_phases),
        remaining='fault recovery, genuine DDS loss modes, rate control, full reset isolation, formal joint UI/UE and Full remain open')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--verify-current-sources',action='store_true')
    args=parser.parse_args()
    value=audit(args.directory,args.verify_current_sources)
    value['audit_source_sha256']=digest(Path(__file__))
    (args.directory/'lifecycle-audit.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({key:val for key,val in value.items() if key not in ('evidence_sha256','lifecycle')},indent=2))
    print(json.dumps({key:val for key,val in value['lifecycle'].items() if key!='events'},indent=2))
