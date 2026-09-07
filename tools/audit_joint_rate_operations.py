"""Raw rate-overload recovery and cold-reset audit; no runtime or publishers."""
import argparse
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from audit_joint_flight import digest,lines,require
from audit_joint_rate import schedule
from audit_joint_product import audit_product_timeline,cdr_string
from audit_joint_product_lifecycle import retained_identity,raw_public
from audit_joint_input_stall import tasks
from Simulator.wksim_runtime.joint_evidence import verify_tasks
from Simulator.wksim_runtime.joint_actions import validate_request


def read(path):return json.loads(Path(path).read_text())


def audit(root):
    flow=read(root/'flow.json');manager=read(root/'wrapper.json');run=read(root/'run/result.json')
    require(flow['status']=='behavior_pass' and flow['result']==run and manager['driver_returncode']==0
            and manager['manager_returncode']==0 and not manager['remaining_manager_group'],'Driver/manager did not finish')
    require(flow['mode'] in ('overload','ground-reset'),'This audit covers overload or ground-reset only')
    result=[]
    for item in run['epochs']:
        folder=root/'run/epochs'/item['epoch'];record=retained_identity(folder,item,run['run_id'])
        result.append((folder,record,item))
    actions={}
    for action in flow['actions']:
        request=action['submitted']['request'];response=action['response']
        validate_request(request,run['run_id'],request['epoch'])
        require(request['epoch'] in {item['epoch'] for item in run['epochs']},'Request crossed an unknown epoch')
        require(response['state']=='completed' and all(response[key]==request[key] for key in
                ('version','run_id','epoch','action','command_id','token')),'Action receipt identity differs')
        require(read(root/'run/actions'/f"{request['command_id']:020d}-{request['token']}.json")==request
                and read(root/'run/action-results'/request['epoch']/(request['token']+'.json'))==response,
                'Action differs from its original mailbox/receipt')
        actions[request['action']]=(request,response)
    if flow['mode']=='ground-reset':
        require(len(result)==2 and list(actions)==['cold-reset','stop'] and run['status']=='stopped','Unexpected ground reset workflow')
        first,second=result;old,new=first[2],second[2]
        require(old['epoch']!=new['epoch'] and all(old['namespace_objects'][kind]!=new['namespace_objects'][kind]
                for kind in ('net','ipc','mnt')) and all(item['namespace_comparison']=='held_file_descriptors' for item in (old,new)),
                'Cold reset reused a live namespace/epoch')
        require(actions['cold-reset'][1]['new_epoch']==new['epoch'],'Reset did not complete the new ready epoch')
        rejection=flow['reset']['rejected_rate_request'];request=rejection['request']
        require(request['epoch']==old['epoch'] and request['action']=='set-rate' and request['requested_rate']==1
                and rejection['state']=='rejected' and rejection['epoch']==new['epoch'],'Retired rate action not rejected')
        name=f"rejected-{request['command_id']:020d}-{request['token']}.json"
        require(read(root/'run/action-results'/new['epoch']/name)==rejection,'Missing raw rejection')
        timelines=[]
        for folder,record,item in result:
            require(not record['tasks'] and not record['flight_completed'],'Ground reset claimed a flight/task')
            timeline,strict,life=audit_product_timeline(folder,record,require_flight=False)
            events,_,counts=raw_public(folder,item['epoch'],run['run_id'])
            require(all(p['max_height_m']<.3 for p in timeline['physical'].values())
                    and all(not any(e['event'] in ('native_ack','setup_completed','command_accepted') for e in es)
                            for es in events.values()),'Ground epoch executed an unrequested task')
            segments=schedule(folder/'rate.jsonl',item['epoch'])
            require(all(s['anchor']['requested_rate']==.5 and s['anchor']['request_id']=='config' for s in segments.values()),
                    'Retired rate request changed the new configured rate')
            timelines.append(dict(epoch=item['epoch'],timeline=timeline,strict_barriers=strict,lifecycle=life,raw_states=counts))
        return dict(status='pass',scope='Real ground cold reset, new authority/namespace, retired set-rate rejection; not flight',epochs=timelines)
    require(len(result)==1 and list(actions)==['start-task','recover','start-recovery-task','stop']
            and run['status']=='pass','Unexpected overload workflow')
    folder,record,item=result[0];epoch=item['epoch']
    faults=read(folder/'faults.json');life=list(lines(folder/'scene-lifecycle.jsonl'))
    require(len(faults)==1 and faults==record['faults']==[r['observation'] for r in life if r['kind']=='fault_latched'],
            'Fault summary differs from original lifecycle')
    fault=faults[0];freeze=fault['authority'];tick=freeze['tick']
    require(fault['type']=='RateUnmet' and freeze['fault']=='rate_unmet/resource_insufficient'
            and freeze==flow['fault_status']['authority'] and tick==flow['frozen_tick'] and tick%4==0
            and freeze['last_input_tick']==freeze['last_barrier_tick']==tick and freeze['pending_tick'] is None
            and freeze['recoverable'] and not freeze['input_pending'],'Overload did not freeze a complete recoverable barrier')
    require(all(v==dict(failed=False,last_response_tick=tick) for v in fault['model_channels'].values()),
            'Rate fault hid a poisoned/incomplete model response')
    require(all(v['request_tick']==tick and v['sent_bytes']>0 and v['response_received']
                for v in fault['model_transport'].values()),'Rate fault lacks both actual RPC confirmations')
    injection=flow['injection'];identity=injection['supervisor'];kernel=injection['kernel_stopped']
    require(identity['pid']==identity['pgid']==item['process_identity'] and kernel['state']=='T'
            and all(kernel[k]==identity[k] for k in ('pid','pgid','start_ticks'))
            and (injection['end_ns']-injection['confirmed_stop_ns'])/1e9>=.15,'Missing owned actual scheduler stop')
    requested=actions['recover'][0]['command_id']/1e9
    require(requested-flow['fault_status']['issued_monotonic_s']>=4,'Fault did not remain frozen for four wall seconds')
    for row in lines(folder/'wire.jsonl'):
        require(not fault['issued_monotonic_s']<=row['issued_monotonic_s']<requested,'Native/model wire progressed before explicit recover')
    for row in life:
        if row['kind']=='permission':
            permission=cdr_string(row['cdr_hex'])
            if fault['issued_monotonic_s']<=permission['issued_monotonic_s']<requested:
                require(permission['phase']=='faulted' and permission['tick']==tick,'Permission advanced/recovered before action')
    recovery=actions['recover'][1]['observation']
    require(recovery['frozen']==freeze and 0<recovery['wall_seconds']<5 and recovery['task_control_released']
            and [r['observation'] for r in life if r['kind']=='physics_recovery_verified']==[recovery],
            'Explicit physical recovery differs from raw observation')
    acks=[cdr_string(r['cdr_hex']) for r in life if r['kind']=='ack_raw']
    require(all(a in acks and a['ready'] and a['task_control_released'] and a['source_boot_ns']>tick*1_000_000
                for a in recovery['control_ack'].values()),'Recovery lacked fresh native released-control ACKs')
    events,_,counts=raw_public(folder,epoch,run['run_id'])
    task_proof=tasks(folder,record,run['run_id'],epoch,recovery,events)
    physical=verify_tasks(folder,epoch,record['authority']['tick'],record['tasks'])
    require(physical==record['physical_task_proof'] and physical is not None,'New task independent landing proof differs')
    timeline,strict,lc=audit_product_timeline(folder,record)
    segments=schedule(folder/'rate.jsonl',epoch,allow_failure=True)
    failed=[s for s in segments.values() if 'failure' in s]
    require(len(failed)==1 and failed[0]['failure']['tick']==tick,'Rate fault/reanchor trace differs')
    return dict(status='pass',scope='Real owned scheduling overload, four-second freeze, explicit recovery and new Task landing',
        epoch=epoch,frozen_tick=tick,lateness_ns=failed[0]['failure']['lateness_ns'],recovery_wall_seconds=recovery['wall_seconds'],
        tasks=task_proof,physical_task_proof=physical,timeline=timeline,strict_barriers=strict,lifecycle=lc,raw_states=counts,
        limitations=['This fault flow is not a 60s positive throughput cohort or a dynamics equivalence comparison.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.directory.resolve()),'Output must be outside evidence')
    dependencies=[Path(__file__),REPO/'tools/audit_joint_rate.py',REPO/'tools/audit_joint_input_stall.py',
        REPO/'tools/audit_joint_product.py',REPO/'tools/audit_joint_product_lifecycle.py',REPO/'tools/audit_joint_flight.py']
    before={str(p.relative_to(REPO)):digest(p) for p in dependencies}
    try:result=audit(args.directory)
    except (OSError,ValueError,KeyError,TypeError,ImportError,AssertionError,StopIteration) as error:
        result=dict(status='failed',error=repr(error))
    after={str(p.relative_to(REPO)):digest(p) for p in dependencies}
    result.update(audit_dependencies_before=before,audit_dependencies_after=after)
    if before!=after:result.update(status='failed',error='Audit source changed while running')
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result.get(k) for k in ('status','scope','error')}));raise SystemExit(0 if result['status']=='pass' else 1)
