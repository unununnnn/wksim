"""Audit actual Agent death, frozen physics, explicit recovery and new tasks."""
import argparse
import json
import math
from pathlib import Path

from audit_joint_flight import audit_timeline,digest,lines,require,verify_control_candidate,AUDIT_OUTPUTS,REPO
from probe_joint_clock import group_members,json_identity


def audit(root,current=False):
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String
    from prometheus_msgs.msg import TextInfo
    result=json.loads((root/'result.json').read_text())
    require(result['status']=='pass' and result['flight_completed'] and result['source_unchanged']
            and not result['cleanup_errors'],'Recovery experiment did not pass')
    recovery=result['dds_recovery']; affected=result['dds_loss_requested']; epoch=result['scene_epoch']
    require(recovery['status']=='pass' and affected in ('arducopter','px4')
            and recovery['affected_stack']==affected,'Wrong fault scenario')
    for name,checksum in result['source_sha256'].items():
        require(digest(root/('source__'+name.replace('/','__')+'.txt'))==checksum,'Source snapshot differs')
        if current: require(digest(REPO/name)==checksum,'Current executed source differs: '+name)
    control=verify_control_candidate(root,result,current)
    for stack in ('arducopter','px4'):
        require(json.loads((root/(stack+'-preflight.json')).read_text())['ok'],'Candidate admission failed')
    require(digest(root/'ap-build.json')==result['manifest_sha256']['ap'],'AP build manifest changed')
    ap=json.loads((root/'ap-build.json').read_text())
    require(digest(Path(ap['candidate_root'])/'build/sitl/bin/arducopter')==ap['artifacts']['build/sitl/bin/arducopter']['sha256'],
            'Actual AP binary changed')
    require(result['unowned_ap_before']==result['unowned_ap_after']==json_identity(828),'Unowned AP changed')
    expected_groups=15 if affected=='px4' else 13
    require(len(result['children'])==expected_groups,'Unexpected owned process/CLI inventory')
    for name,child in result['children'].items():
        require(not child['remaining_group_members'] and not group_members(child['identity']['pgid']),
                'Owned group remains: '+name)
        if name.endswith(('-model','-fc','-control','-recovery-task')):
            require(child['returncode']==0,'Process did not complete normally: '+name)
    dead=result['children'][affected+'-agent']; new=result['children'][affected+'-agent-reconnected']
    require(all(dead['identity'][key]==recovery['injection']['identity'][key] for key in ('pid','pgid','start_ticks'))
            and dead['returncode'] is not None
            and new['argv']==dead['argv'] and new['cwd']==dead['cwd']
            and new['identity']['pid']!=dead['identity']['pid']==dead['identity']['pgid']
            and new['identity']['pid']==recovery['replacement_agent_pid'],'Agent was not actually retired/recreated')
    if 'agent_identity_before_injection' in result:
        observed=result['agent_identity_before_injection']
        require(all(observed['expected'][key]==observed['observed'][key] for key in ('pid','pgid','start_ticks'))
                and Path(observed['executable']).resolve()==Path(dead['argv'][0]).resolve(),
                'Failure injection was not bound to the actual owned Agent executable')
    px_identity=json.loads((root/'px4-preflight.json').read_text())['identities']['firmware']
    require(digest(Path(result['children']['px4-fc']['argv'][0]))==px_identity['expected_sha256'],'Actual PX4 firmware changed')
    before=recovery['before_failure']; frozen=recovery['frozen']; restored=recovery['reconnected_frozen']
    require(before['models']==frozen['models']==restored['models'],'Agent loss/restart changed frozen physics')
    require(frozen['authority']==restored['authority'] and frozen['authority']['phase']=='faulted'
            and frozen['authority']['recoverable'] and frozen['authority']['pending_tick'] is None
            and frozen['authority']['last_input_tick']==frozen['authority']['tick'], 'Invalid frozen boundary')
    freeze_tick=frozen['authority']['tick']
    require(frozen['authority']['last_barrier_tick']==freeze_tick-freeze_tick%4,'Missing preceding PX4 barrier')
    physical=recovery['physics_recovery']
    require(physical['frozen']==frozen['authority'] and 0<physical['wall_seconds']<5
            and physical['recovered']['tick']>freeze_tick and physical['task_control_released'],
            'Explicit physical recovery did not satisfy approved bounds')
    require(set(physical['control_ack'])=={'1','2'},'Missing dual recovery acknowledgements')

    markers={}; acks=[]; retired={}; bound={}; permissions=[]; native_cli=[]; cli_peer=None
    for row in lines(root/'scene-lifecycle.jsonl'):
        require(row['epoch']==epoch,'Lifecycle crossed scene epoch')
        if row['kind'] in ('agent_stop_requested','agent_exit_detected','communication_fault','agent_restarted',
                           'physics_recovery_verified','new_task_authorized'):
            markers.setdefault(row['kind'],row)
        if row['kind']=='permission':
            value=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),String).data)
            require(value==row['message'] and value['version']==2 and value['run_id']==result['run_id']
                    and value['scene_epoch']==epoch and value['time_ns']==row['tick']*1000000
                    and value['lease_seconds']==.5,'Raw recovery permission differs')
            if value['phase'] in ('faulted','recovering'):
                require(value['faulted_uav_ids']==[1 if affected=='arducopter' else 2], 'Wrong authorized native retirement scope')
            permissions.append((row,value))
        elif row['kind']=='ack_raw':
            acks.append(json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),String).data))
        elif row['kind']=='native_dds_client_restarted': native_cli.append(row['observation'])
        elif row['kind']=='px4_cli_peer_verified': cli_peer=row
    require(set(markers)=={'agent_stop_requested','agent_exit_detected','communication_fault','agent_restarted',
                          'physics_recovery_verified','new_task_authorized'},'Incomplete failure/recovery lifecycle')
    require(markers['agent_exit_detected']['tick']==freeze_tick
            and markers['agent_exit_detected']['pid']==dead['identity']['pid']
            and markers['agent_exit_detected']['returncode']==dead['returncode'],'Exit observation differs from kernel result')
    begins=[row for row,value in permissions if value['phase']=='recovering']
    require(begins,'No explicit recovering permission')
    recovery_wall=begins[0]['wall']; detection_wall=markers['agent_exit_detected']['wall']
    require(markers['agent_restarted']['wall']>detection_wall
            and recovery_wall>markers['agent_restarted']['wall']
            and markers['new_task_authorized']['wall']>=markers['physics_recovery_verified']['wall'],
            'Restart or task dispatch implicitly bypassed explicit physical recovery')
    for row in lines(root/'joint-wire.jsonl'):
        if row['kind'] in ('step','sensor','gps'):
            require(not detection_wall<=row['wall']<recovery_wall,'Physics advanced after loss detection and before explicit recovery')
    for row in lines(root/'pause-dds.jsonl'):
        if row['topic'].endswith('/text_info'):
            event=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),TextInfo).message)
            if event['event']=='scene_native_sources_bound': bound[row['topic']]=event['native_endpoints']
            if event['event']=='scene_native_sources_retired': retired[row['topic']]=event['native_endpoints']
    key=f'/uav{1 if affected=="arducopter" else 2}/prometheus/text_info'
    require(set(retired)=={key} and retired[key]==bound[key],'Retired a live/unrelated or unbound native source')
    if affected=='px4':
        private=result['private_temporary_files']
        require(private['mount_namespace']==result['isolation']['mnt'] and private['device']!=private['lower_device'],
                'Native CLI temporary path was not private')
        require(cli_peer is not None and cli_peer['pid']==result['children']['px4-fc']['identity']['pid'],
                'Native CLI peer was not the owned PX4 process')
        binary=Path(result['children']['px4-fc']['argv'][0]).parent/'px4-uxrce_dds_client'
        expected=[['stop'],['start','-t','udp','-h','127.0.0.1','-p','18888','-n','wksim_px4_21']]
        require(len(native_cli)==2,'Missing explicit DDS client restart evidence')
        for item,command in zip(native_cli,expected):
            require(item['argv']==[str(binary),'--instance','21',*command] and item['returncode']==0
                    and result['children']['px4-dds-'+command[0]]['returncode']==0,
                    'Native recovery ran unexpected commands or failed')
    else:
        require(not native_cli and cli_peer is None,'AP recovery unexpectedly used native CLI')
    for uid,ack in physical['control_ack'].items():
        require(ack in acks and ack['ready'] and ack['task_control_released'] and ack['phase']=='recovering'
                and ack['source_boot_ns']>freeze_tick*1000000 and ack['native_endpoints'], 'Recovery used old native evidence')
        if int(uid)==(1 if affected=='arducopter' else 2):
            require(not set(ack['native_endpoints'].values())&set(retired[key].values()),'Old Agent writer admitted after restart')

    timeline,models=audit_timeline(root,result)
    summaries={}
    for stack,uid in (('arducopter',1),('px4',2)):
        old=json.loads((root/stack/'result.json').read_text())
        fresh=json.loads((root/(stack+'-recovery')/'result.json').read_text())
        require(old==recovery['old_tasks'][stack] and old['status']=='failed'
                and result['children'][stack+'-task']['returncode']==1,'Old task was resumed or killed instead of failing')
        require(fresh==result['tasks'][stack] and fresh['status']=='pass' and fresh['task_mode']=='recover'
                and fresh['run_id']==result['run_id'] and fresh['scene_epoch']==epoch and fresh['uav_id']==uid,
                'New recovery task identity differs')
        require(fresh['scene_implementation']==dict(path=str(Path(control['package'])/'scene.py'),
                    sha256=control['python_sha256']['scene.py']),'Task did not use sealed shared protocol')
        require(old['task']['control_epoch']==fresh['task']['control_epoch'],'Unexpected controller restart')
        old_requests=old['task']['request_envelopes']; new_requests=fresh['task']['request_envelopes']
        allow_hold=recovery['new_task_authorization']['tasks'][stack].get('allow_native_hold',False)
        native_hold=len(new_requests)==4
        require(len(old_requests)==3 and len(new_requests) in (3,4)
                and (not native_hold or stack=='px4' and allow_hold),'Unexpected original/recovery public operation count')
        floor=max(request['request_id'] for request in old_requests)
        require([request['request_id'] for request in new_requests]==list(range(floor+1,floor+1+len(new_requests))),
                'Recovery reused old public request identities')
        if native_hold:
            require(new_requests[0]['setup']['px4_mode']=='AUTO.LOITER'
                    and physical['control_ack'][str(uid)]['native_failsafe']
                    and not physical['control_ack'][str(uid)]['command_control_eligible'],
                    'Native hold was not an explicit new response to the actual FC failsafe')
        main_requests=new_requests[1:] if native_hold else new_requests
        require(main_requests[0]['setup']['control_state']=='COMMAND_CONTROL'
                and main_requests[1]['command']['agent_cmd']==3
                and main_requests[2]['setup']['px4_mode']=='AUTO.LOITER','Recovery replayed a takeoff/waypoint instead of new hold/land')
        for request in new_requests:
            body=request.get('setup',request.get('command'))
            stamp=body['header']['stamp']['sec']*10**9+body['header']['stamp']['nanosec']
            require(stamp>=physical['recovered']['time_ns'],'New task sent before physical recovery')
        require(len([event for event in fresh['task']['events'] if event['event']=='native_ack' and event['accepted']])>=len(new_requests),
                'New task lacks actual native acknowledgements')
        phases={event['phase']:event for event in fresh['phases']}
        if native_hold:
            require(phases['recovery_navigation_and_health_ready']['state']['odom_valid']
                    and phases['recovery_autonomous_hold_acknowledged']['ros_time_ns']<=
                        phases['airborne_recovery_control_ready']['ros_time_ns'],
                    'Position control started before actual native health/hold confirmation')
        lo=phases['airborne_recovery_state_confirmed']['ros_time_ns']; hi=phases['airborne_recovery_hold_completed']['ros_time_ns']
        require(hi-lo>=2*10**9,'Recovered task did not dwell for two shared seconds')
        position=phases['airborne_recovery_state_confirmed']['state']['position']
        target=[position[1],position[0],-position[2]]
        rows=models[stack][max(0,lo//1000000-1):hi//1000000]
        error=max(math.dist(row[0][:3],target) for row in rows)
        speed=max(math.hypot(*row[0][3:6]) for row in rows)
        require(error<=.5 and speed<=.5,f'{stack}: recovered hold truth error={error}, speed={speed}, window={lo}..{hi}')
        final=fresh['task']['final']['state']
        require(final['connected'] and final['odom_valid'] and not final['armed'] and abs(final['position'][2])<.3,
                'New task did not reach valid landed/disarmed state')
        summaries[stack]=dict(old_task_status='failed',new_request_ids=[r['request_id'] for r in new_requests],
            explicit_native_hold=native_hold,
            physical_hold_max_error_m=error,physical_hold_max_speed_m_s=speed,control_epoch=fresh['task']['control_epoch'])
    return dict(status='pass',scope='actual Agent termination/restart, frozen joint scene, explicit physical recovery and new public tasks',
        affected_stack=affected,freeze_tick=freeze_tick,requested_loss_tick=recovery['injection']['tick'],
        recovery_wall_seconds=physical['wall_seconds'],old_agent_pid=dead['identity']['pid'],new_agent_pid=new['identity']['pid'],
        extra_physics_steps_while_faulted=0,retired_native_sources=retired,tasks=summaries,timeline=timeline,
        current_source_verification=current,owned_groups_without_residue=expected_groups,native_dds_cli=native_cli,
        result_sha256=digest(root/'result.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--verify-current-sources',action='store_true');args=parser.parse_args()
    report=audit(args.directory,args.verify_current_sources)
    report['audit_source_sha256']=digest(Path(__file__))
    report['evidence_sha256']={path.relative_to(args.directory).as_posix():digest(path) for path in sorted(args.directory.rglob('*'))
                               if path.is_file() and path.name not in AUDIT_OUTPUTS}
    (args.directory/'dds-recovery-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key!='evidence_sha256'},indent=2))
