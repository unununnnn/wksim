"""Raw formal-entry DDS recovery and cold-reset audit; no running publishers."""
import argparse
import json
from pathlib import Path

from audit_joint_flight import digest,lines,require
from audit_joint_product import audit_product_timeline,cdr_string
from Simulator.wksim_runtime.evidence import group_members,host_boot_id,write_json
from Simulator.wksim_runtime.joint_evidence import verify_tasks
from Simulator.wksim_runtime.joint_actions import validate_request


def recorded_host(result,item,*,current_host=False):
    """Historical cleanup is not a query against potentially reused live PIDs."""
    if 'unowned_ap_before' in result:
        require(result['unowned_ap_before']==result['unowned_ap_after'],'Recorded unowned AP identity changed')
    else:
        require(isinstance(result.get('host_boot_id'),str) and len(result['host_boot_id'])==36,
                'Missing recorded host identity')
    require(not item['remaining_group_members'],'Recorded owned epoch group remained')
    if current_host:
        require(result.get('host_boot_id')==host_boot_id(),'Current-host check requires the same recorded boot identity')
        require(not group_members(item['process_identity']),'Owned group remains on current host')


def retained_identity(directory,item,run_id,*,current_host=False):
    result=json.loads((directory/'result.json').read_text())
    require(result==item['result'] and result['epoch']==item['epoch'] and result['run_id']==run_id,
            'Manager and retained epoch identity differ')
    require(result['status'] in ('stopped','cold_reset') and not result['cleanup_errors']
            and result['changed_sources']==[],'Epoch cleanup/source integrity failed')
    recorded_host(result,item,current_host=current_host)
    for name,sha in result['source_sha256'].items():
        require(digest(directory/'source'/name)==sha,'Retained executed source differs: '+name)
    preflight=json.loads((directory/'preflight.json').read_text())
    require(preflight==result['preflight'] and preflight['ok'],'Original admitted identity differs')
    for label in ('ready','stopping'):
        records=result['runtime_images'][label]
        require(set(records)=={'arducopter-fc','px4-fc','arducopter-model','px4-model'},'Missing actual runtime images')
        for name,record in records.items():
            child=result['children'][name]
            require(all(record['identity'][key]==child['identity'][key] for key in ('pid','pgid','start_ticks'))
                    and child['identity']['pgid']==item['process_identity']
                    and child['returncode']==0,'Runtime image identity or normal exit differs')
            path=directory/record['maps_file']
            require(digest(path)==record['maps_sha256'] and not record['forbidden_libraries'],'Runtime maps differ')
            text=path.read_text()
            require(not any(token in text.lower() for token in ('libgz-','libgazebo','libignition','matlab','coptersim.exe')),
                    'Forbidden runtime image was loaded')
            if current_host:
                require(digest(record['executable'])==record['executable_sha256'],'Executed binary changed after run')
            if name.endswith('-fc'):
                pin=preflight['identities']['ap' if name.startswith('arducopter') else 'px4']
                require(record['executable']==pin['path'] and record['executable_sha256']==pin['sha256'],
                        'Executed firmware differs from admitted firmware')
            else:
                require(preflight['model_library'] in text,'Admitted model missing from actual mappings')
    for name,child in result['children'].items():
        require(child['identity']['pgid']==item['process_identity'] and child['returncode'] is not None,
                'Unretired or foreign process: '+name)
    return result


def raw_public(directory,epoch,run_id):
    from rclpy.serialization import deserialize_message
    from prometheus_msgs.msg import TextInfo
    from wksim_msgs.msg import SessionState
    events={1:[],2:[]};last={};counts={1:0,2:0}
    for row in lines(directory/'public-dds.jsonl'):
        require(row['epoch']==epoch,'Public DDS crossed scene epoch')
        uid=next((uid for uid in (1,2) if row['topic'].startswith(f'/uav{uid}/prometheus/')),None)
        require(uid is not None,'Public topic crossed vehicle identity')
        if row['topic'].endswith('/text_info'):
            value=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),TextInfo).message)
            require(value['run_id']==run_id,'Raw event crossed run identity')
            events[uid].append(value)
        else:
            require(row['topic'].endswith('/v2/state'),'Unknown public DDS topic')
            value=deserialize_message(bytes.fromhex(row['cdr_hex']),SessionState)
            require(value.run_id==run_id and value.state.uav_id==value.control.uav_id==uid,'Public state identity differs')
            last[uid]=value;counts[uid]+=1
    require(set(last)=={1,2},'Missing dual public states')
    for value in last.values():
        require(value.state.connected and value.state.odom_valid and not value.state.armed
                and abs(value.state.position[2])<.3,'Final native state was not valid and landed')
    return events,last,counts


def audit(evidence,*,current_host=False):
    root=evidence/'run';flow=json.loads((evidence/'flow.json').read_text())
    result=json.loads((root/'result.json').read_text())
    require(flow['status']=='pass' and flow['result']==result and result['status']=='pass','Formal lifecycle flow did not pass')
    require(len(result['epochs'])==2 and flow['affected'] in ('arducopter','px4'),'Expected one flight and one reset generation')
    run_id=result['run_id'];old,new=result['epochs'];epoch=old['epoch'];new_epoch=new['epoch']
    require(epoch!=new_epoch and old['network_namespace']!=new['network_namespace'],'Cold reset reused epoch/network namespace')
    require(all(item['namespace_comparison']=='held_file_descriptors' for item in (old,new))
            and all(old['namespace_objects'][kind]!=new['namespace_objects'][kind] for kind in ('net','ipc','mnt')),
            'Reset namespace comparison lacked retained kernel object references')
    first=root/'epochs'/epoch;second=root/'epochs'/new_epoch
    retired=retained_identity(first,old,run_id,current_host=current_host)
    ground=retained_identity(second,new,run_id,current_host=current_host)
    require(retired['status']=='cold_reset' and ground['status']=='stopped' and not ground['tasks'],
            'Cold reset replayed tasks or did not complete')
    require(retired['flight_completed'] and not ground['flight_completed'],'Ground reset falsely completed a flight')
    ordered=['start-task','recover','start-recovery-task','cold-reset','stop']
    require([row['response']['action'] for row in flow['actions']]==ordered,'Unexpected formal lifecycle action sequence')
    responses={};requests={}
    for row in flow['actions']:
        request=row['submitted']['request'];response=row['response']
        validate_request(request,run_id,new_epoch if request['action']=='stop' else epoch)
        filename=f"{request['command_id']:020d}-{request['token']}.json"
        require(json.loads((root/'actions'/filename).read_text())==request,'Submitted action file differs')
        require(json.loads((root/'action-results'/request['epoch']/(request['token']+'.json')).read_text())==response
                and response['state']=='completed','Action completion lacks retained response')
        responses[request['action']]=response;requests[request['action']]=request
    require(all(a['command_id']<b['command_id'] for a,b in zip(requests.values(),list(requests.values())[1:])),
            'Formal action identity moved backwards')
    require(responses['cold-reset']['new_epoch']==new_epoch,'Reset response did not name the new epoch')
    rejection=flow['reset']['retired_request_rejection']
    rejected=rejection['request'];name=f"rejected-{rejected['command_id']:020d}-{rejected['token']}.json"
    require(rejected['epoch']==epoch and rejection['epoch']==new_epoch and rejection['state']=='rejected'
            and json.loads((root/'action-results'/new_epoch/name).read_text())==rejection,'Retired action was not rejected')

    affected=flow['affected'];uid=1 if affected=='arducopter' else 2
    dead=retired['children'][affected+'-agent']
    replacement=[value for name,value in retired['children'].items() if name.startswith(affected+'-agent-reconnected-')]
    require(len(replacement)==1,'Missing unique replacement Agent')
    replacement=replacement[0]
    require(dead['identity']==flow['injected_agent']['identity'] and dead['returncode']==-15
            and replacement['identity']['pid']!=dead['identity']['pid'] and replacement['argv']==dead['argv']
            and replacement['cwd']==dead['cwd'],'Agent death/replacement identity differs')
    recovery=responses['recover']['observation'];freeze=recovery['frozen'];tick=freeze['tick']
    require(tick==flow['frozen_tick'] and freeze['phase']=='faulted' and freeze['recoverable']
            and freeze['pending_tick'] is None and freeze['last_input_tick']==tick
            and 0<recovery['wall_seconds']<5 and recovery['task_control_released'],'Invalid approved recovery boundary')
    require(flow['freeze']['before']==flow['freeze']['after'] and flow['freeze']['wall_seconds']>=4,
            'Physics changed during retained fault freeze')
    for stack in ('arducopter','px4'):
        sample=next(row for row in lines(first/(stack+'-truth.jsonl')) if row['tick']==tick)
        require(flow['freeze']['before'][stack]==sample and -sample['state'][8]>2.5,'Freeze differs from airborne model truth')
    acks=[];permissions=[];markers=[];cli_peer=[];native_cli=[]
    for row in lines(first/'scene-lifecycle.jsonl'):
        if row['kind']=='ack_raw': acks.append(cdr_string(row['cdr_hex']))
        elif row['kind']=='permission': permissions.append(cdr_string(row['cdr_hex']))
        elif row['kind']=='physics_recovery_verified':markers.append(row['observation'])
        elif row['kind']=='px4_cli_peer_verified':cli_peer.append(row['pid'])
        elif row['kind']=='native_dds_client_restarted':native_cli.append(row)
    require(markers==[recovery],'Recovery response differs from original lifecycle observation')
    fault=[value for value in permissions if value['phase']=='faulted']
    resuming=[value for value in permissions if value['phase']=='recovering']
    require(fault and resuming and all(value['tick']==tick and value['faulted_uav_ids']==[uid] for value in fault),
            'Fault permission advanced time or retired an unrelated native source')
    require(resuming[0]['issued_monotonic_s']>=requests['recover']['command_id']/1e9,'Recovery preceded explicit action')
    for row in lines(first/'wire.jsonl'):
        if row['kind'] in ('step','sensor','gps'):
            require(not fault[0]['issued_monotonic_s']<=row['issued_monotonic_s']<resuming[0]['issued_monotonic_s'],
                    'Physics advanced between fault permission and explicit recovery')
    events,last,counts=raw_public(first,epoch,run_id)
    retired_sources={peer:[event['native_endpoints'] for event in values if event['event']=='scene_native_sources_retired']
                     for peer,values in events.items()}
    require(len(retired_sources[uid])==1 and not retired_sources[3-uid],'Unexpected native source retirement')
    original_bound=next(event['native_endpoints'] for event in events[uid] if event['event']=='scene_native_sources_bound')
    require(retired_sources[uid][0]==original_bound,'Retired endpoints were not the originally bound native sources')
    if affected=='px4':
        require(cli_peer==[retired['children']['px4-fc']['identity']['pid']] and len(native_cli)==2,
                'Native DDS client restart did not retain the verified owned peer')
        expected=[['stop'],['start','-t','udp','-h','127.0.0.1','-p','18888','-n','wksim_px4_21']]
        binary=str(Path(retired['children']['px4-fc']['argv'][0]).parent/'px4-uxrce_dds_client')
        for row,command in zip(native_cli,expected):
            require(row['argv']==[binary,'--instance','21',*command] and row['returncode']==0
                    and any(child['identity']['pid']==row['pid'] and child['argv']==row['argv'] and child['returncode']==0
                            for child in retired['children'].values()),'Native DDS restart command identity differs')
    else:
        require(not cli_peer and not native_cli,'AP recovery unexpectedly ran PX4 native CLI')
    require(set(recovery['control_ack'])=={'1','2'},'Missing dual native recovery ACK')
    for peer,ack in recovery['control_ack'].items():
        require(ack in acks and ack['ready'] and ack['task_control_released'] and ack['phase']=='recovering'
                and ack['source_boot_ns']>tick*1000000 and ack['home_initialized'] and ack['native_flying'],
                'Recovery used old, unready or uncorrelated native ACK')
        if int(peer)==uid:
            require(not set(ack['native_endpoints'].values())&set(retired_sources[uid][0].values()),'Retired native writer reused')
    summaries={}
    for stack,peer in (('arducopter',1),('px4',2)):
        reports=[]
        for path in first.glob('tasks/*/'+stack+'/result.json'):
            report=json.loads(path.read_text());name=stack+'-task-'+path.parent.parent.name
            require(report==retired['tasks'][name] and report['run_id']==run_id and report['scene_epoch']==epoch,
                    'Task result differs from actual owned task')
            ready=json.loads((path.parent/'ready.json').read_text())
            go=json.loads((path.parent.parent/'go.json').read_text())
            require(go['run_id']==run_id and go['epoch']==epoch and go['tasks'][stack]==ready,'Task bypassed its common ready/go identity')
            raw=[row['message'] for row in lines(path.parent/'prometheus.jsonl') if row.get('request_envelope')]
            require(raw==report['task']['request_envelopes'],'Public request summary differs from original log')
            reports.append((report,raw,retired['children'][name]['returncode']))
        require(len(reports)==2,'Expected original and explicit recovery task only')
        original=next(item for item in reports if item[0]['task_mode']=='initial')
        fresh=next(item for item in reports if item[0]['task_mode']=='recovery')
        require(original[0]['status']=='failed' and original[2]==1 and fresh[0]['status']=='pass' and fresh[2]==0,
                'Old task resumed or fresh task failed')
        require(original[0]['task']['control_epoch']==fresh[0]['task']['control_epoch'],'Unexpected Control restart')
        floor=max(value['request_id'] for value in original[1])
        require(len(original[1])==3 and len(fresh[1])==(4 if stack=='px4' else 3)
                and [value['request_id'] for value in fresh[1]]==list(range(floor+1,floor+len(fresh[1])+1)),
                'Recovery reused request identities or replayed the old task')
        for request in fresh[1]:
            require(request['run_id']==run_id and request['control_epoch']==fresh[0]['task']['control_epoch'],
                    'New task request crossed identity')
            matched=[event for event in events[peer] if event.get('request_id')==request['request_id']
                     and event.get('control_epoch')==request['control_epoch']]
            require(any(event['event']=='native_ack' and event.get('accepted') for event in matched)
                    and any(event['event']==('setup_completed' if 'setup' in request else 'command_accepted') for event in matched),
                    'New task lacks raw native ACK or public completion')
            body=request.get('setup',request.get('command'));stamp=body['header']['stamp']
            require(stamp['sec']*10**9+stamp['nanosec']>=recovery['recovered']['time_ns'],'New request preceded physical recovery')
        summaries[stack]=dict(old_status='failed',new_request_ids=[value['request_id'] for value in fresh[1]])
    physical=verify_tasks(first,epoch,retired['authority']['tick'],retired['tasks'])
    require(physical==retired['physical_task_proof'],'Retained physical proof differs from raw truth')
    flight,strict,life=audit_product_timeline(first,retired)
    reset_timeline,reset_strict,reset_life=audit_product_timeline(second,ground,require_flight=False)
    ground_events,ground_last,ground_counts=raw_public(second,new_epoch,run_id)
    require(all(value['max_height_m']<.3 for value in reset_timeline['physical'].values()),'New epoch moved before a task')
    for peer in (1,2):
        require(last[peer].control_epoch!=ground_last[peer].control_epoch,'Cold reset retained old Control epoch')
        require(not any(event['event'] in ('native_ack','setup_completed','command_accepted') for event in ground_events[peer]),
                'Old native task was replayed after reset')
    return dict(status='pass',scope='Formal Agent loss, explicit new recovery tasks, cold reset and retired action isolation',
        affected=affected,freeze_tick=tick,recovery_wall_seconds=recovery['wall_seconds'],tasks=summaries,
        physical_task_proof=physical,flight_timeline=flight,reset_timeline=reset_timeline,
        strict_barriers=[strict,reset_strict],lifecycles=[life,reset_life],raw_state_counts=[counts,ground_counts],
        epochs=[epoch,new_epoch],groups_without_residue=2,
        current_host_verification=current_host,
        limitations=['Fault freeze is audited from the first raw fault permission until explicit recovering permission; wire/model authority is never inferred from wall-clock pacing.',
                     'Default verification uses recorded process/image/cleanup evidence. Live PIDs and current executable files are checked only with --current-host and a matching recorded boot identity.'],
        evidence_sha256={str(path.relative_to(evidence)):digest(path) for path in sorted(evidence.rglob('*')) if path.is_file()})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--current-host',action='store_true')
    args=parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.directory.resolve()),'Output must be outside retained evidence')
    source_sha=digest(Path(__file__))
    try: result=audit(args.directory,current_host=args.current_host)
    except (ValueError,KeyError,OSError,TypeError,ImportError,StopIteration) as error:
        result=dict(status='failed',error=repr(error))
    result['audit_source_sha256']=source_sha
    if digest(Path(__file__))!=source_sha:
        result.update(status='failed',error='Audit source changed during execution')
    write_json(args.output,result)
    print(json.dumps({key:value for key,value in result.items() if key not in ('evidence_sha256','physical_task_proof')},indent=2))
    raise SystemExit(0 if result['status']=='pass' else 1)
