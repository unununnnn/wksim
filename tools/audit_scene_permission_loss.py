"""Audit actual permission expiry and failed automatic revival at a real hover."""
import argparse
import json
from pathlib import Path

from audit_joint_flight import digest, lines, require
from joint_control_candidate import check as check_control
from probe_joint_clock import group_members, json_identity


def audit(root, current=False):
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String
    from prometheus_msgs.msg import TextInfo
    from wksim_msgs.msg import SessionState
    result=json.loads((root/'result.json').read_text())
    require(result['status']=='observed' and not result['flight_completed']
            and result['scene_lease_loss_requested'],'Not a completed permission-loss observation')
    require(result['source_unchanged'] and not result['cleanup_errors'],'Source/cleanup failure')
    repo=Path(__file__).resolve().parents[1]
    for name, checksum in result['source_sha256'].items():
        require(digest(root/('source__'+name.replace('/','__')+'.txt'))==checksum,'Source snapshot differs')
        if current: require(digest(repo/name)==checksum,'Current source changed: '+name)
    control=result['control_candidate']
    require(check_control(Path(control['root'])/'build.json',result['manifest_sha256']['control'])==control,
            'Actual candidate changed')
    require(result['unowned_ap_before']==result['unowned_ap_after']==json_identity(828),'Unowned AP changed')
    require(len(result['children'])==10,'Unexpected participant count')
    for name, child in result['children'].items():
        require(not child['remaining_group_members'] and not group_members(child['identity']['pgid']),
                'Owned process group remains')
        if name.endswith(('-model','-control','-fc')):
            require(child['returncode']==0,'Model/FC/control did not stop normally')
    fault=result['scene_fault_observation']; before,after=fault['before'],fault['after']
    tick=before['authority']['tick']; epoch=result['scene_epoch']
    require(fault['status']=='observed_fault' and fault['withheld_window_s']==1.2
            and fault['renewed_observation_s']==.7,'Fault observation bounds changed')
    require(before['models']==after['models'] and before['authority']==after['authority']
            and before['authority']['phase']=='paused' and before['authority']['last_barrier_tick']==tick,
            'Fault or fresh heartbeat advanced physics')
    require(result['final_authority']['tick']==tick and result['final_authority']['phase']=='stopped',
            'Stop added a physical step')
    original=fault['original_pause']
    require(original['wall_seconds']>=4 and original['before']['models']==original['after']['models']==before['models']
            and all(value['ready'] for value in original['control_ack'].values()),'Healthy pause was not first established')
    heights={}
    for stack in ('arducopter','px4'):
        count=0; last=None
        for count,row in enumerate(lines(root/(stack+'-truth.jsonl')),1):
            require(row['tick']==count and row['epoch']==epoch and round(row['state'][60])==count*1000,
                    'Physical timeline differed')
            last=row['state']
        require(count==tick and last==after['models'][stack]['state'],'Snapshot differs from actual final model trace')
        heights[stack]=-last[8]
        require(heights[stack]>=2.5,'Fault was not observed airborne')
    for row in lines(root/'joint-wire.jsonl'):
        if row['kind'] in ('sensor','gps','step'):
            require(row['wall']<fault['started_wall'] and row['tick']<=tick,'Fault/reconnection issued a model input')
    withheld=renewed=None; raw_permissions=[]
    for row in lines(root/'scene-lifecycle.jsonl'):
        if row['kind']=='permission_withheld': withheld=row['wall']
        elif row['kind']=='fresh_permission_after_expiry': renewed=row['wall']
        elif row['kind']=='permission':
            value=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),String).data)
            require(value==row['message'] and value['scene_epoch']==epoch,'Raw permission identity differs')
            raw_permissions.append((row['wall'],value))
    require(withheld is not None and renewed-withheld>=1.2,'Missing withholding/renewal evidence')
    require(not any(withheld<=wall<renewed for wall,_ in raw_permissions),'Permission was not actually withheld')
    require(any(wall>=renewed for wall,_ in raw_permissions),'No fresh permission was offered after failure')
    revoked={}; rejected={}; final={}
    for row in lines(root/'pause-dds.jsonl'):
        if row['topic'].endswith('/text_info'):
            message=deserialize_message(bytes.fromhex(row['cdr_hex']),TextInfo)
            event=json.loads(message.message)
            if event['event']=='control_revoked' and 'scene_permission_expired' in event.get('reason',''):
                revoked[row['topic']]=dict(seconds_after_withholding=row['wall']-withheld,event=event)
            if row['wall']>=renewed and event['event']=='scene_permission_rejected' and 'expired' in event.get('reason',''):
                rejected[row['topic']]=event
        elif row['topic'].endswith('/v2/state') and row['wall']>=renewed:
            message=deserialize_message(bytes.fromhex(row['cdr_hex']),SessionState)
            require(message.run_id==result['run_id'] and message.state.uav_id==message.control.uav_id,
                    'Revocation state identity changed')
            require(message.control.failsafe,'Fresh permission automatically reacquired task control')
            final[message.state.uav_id]=message.control_epoch
    require(len(revoked)==len(rejected)==len(final)==2,'Missing dual revocation and rejected automatic revival')
    task_errors={}
    for stack in ('arducopter','px4'):
        task=json.loads((root/stack/'result.json').read_text())
        require(task['status']=='failed' and 'Scene lifecycle failure' in task['error']
                and task['scene_epoch']==epoch and task['run_id']==result['run_id'], 'Task did not naturally fail on permission expiry')
        require(result['children'][stack+'-task']['returncode']==1,'Task was killed instead of observing expiry')
        paused=False
        for row in lines(root/stack/'prometheus.jsonl'):
            if row.get('scene_event')=='paused': paused=True
            if paused: require('published' not in row and 'public_payload' not in row,'Old task replayed after pause/failure')
        task_errors[stack]=task['error']
    return dict(status='pass',scope='real airborne permission loss, withdrawal and no automatic heartbeat recovery; not DDS outage acceptance',
        scene_epoch=epoch,tick=tick,heights_m=heights,extra_physics_steps=0,control_revocations=revoked,
        renewed_permission_rejected=rejected,task_errors=task_errors,owned_groups_without_residue=10,
        current_source_verification=current,result_sha256=digest(root/'result.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--verify-current-sources',action='store_true')
    args=parser.parse_args();result=audit(args.directory,args.verify_current_sources)
    result['audit_source_sha256']=digest(Path(__file__))
    result['evidence_sha256']={p.relative_to(args.directory).as_posix():digest(p) for p in args.directory.rglob('*')
                              if p.is_file() and p.name!='permission-loss-audit.json'}
    (args.directory/'permission-loss-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key!='evidence_sha256'},indent=2))
