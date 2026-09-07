"""Independent read-only owned FC/model stall audit, using retained raw evidence."""
import argparse
import json
from pathlib import Path
import sys
from audit_joint_flight import digest, lines, require,audit_timeline
from audit_joint_product import audit_product_timeline, cdr_string,ProductTimeline,lifecycle
from audit_joint_product_lifecycle import retained_identity, raw_public
from Simulator.wksim_runtime.evidence import write_json, group_members
from Simulator.wksim_runtime.joint_actions import validate_request
from Simulator.wksim_runtime.joint_evidence import verify_tasks


def read(path):
    return json.loads(path.read_text())


def input_boundary(flow, fault, life, wire, truth, request):
    frozen=fault['authority'];tick=frozen['tick'];stack=flow['target'].removesuffix('-fc')
    require(fault['type']=='InputTimeout' and frozen==flow['fault']['authority']
            and frozen['phase']=='faulted' and frozen['recoverable'] and frozen['input_pending']
            and frozen['pending_tick'] is None,'Not a latched recoverable input fault')
    inflight=fault['physical_inflight']
    require(inflight['tick']==tick and inflight['stage']==('ap_input' if stack=='arducopter' else 'px4_input')
            and inflight['model_ticks']==dict(arducopter=tick,px4=tick),'Wrong unfinished input stage')
    require(all(value==dict(failed=False,last_response_tick=tick) for value in fault['model_channels'].values())
            and set(fault['model_channels'])=={'arducopter','px4'},'Model response was partial/poisoned')
    sensor=next(row for row in wire if row['kind']=='sensor' and row['stack']==stack and row['tick']==tick)
    wait=fault['issued_monotonic_s']-sensor['issued_monotonic_s']
    require(5<=wait<5.2 and 5<=fault['issued_monotonic_s']-flow['injection']['monotonic_s']<5.3,
            'Input timeout differs from approved 5s window')
    requested=[row for row in life if row['kind']=='input_recovery_requested']
    repaired=[row for row in life if row['kind']=='input_recovery_verified']
    require(len(requested)==len(repaired)==1 and requested[0]['request']==request
            and requested[0]['authority']==repaired[0]['before']==frozen,'Repair lacks original explicit action')
    after=repaired[0]['after'];expected=dict(frozen,input_pending=False,last_input_tick=tick)
    if tick%4==0: expected['last_barrier_tick']=tick
    require(after==expected,'Repair changed physical authority rather than only input ACK')
    require(flow['late_process_resumed']['before']==flow['late_process_resumed']['after']
            and flow['late_process_resumed']['status']['authority']==frozen,'Late process automatically progressed')
    for name in ('arducopter','px4'):
        sample=truth[name][tick-1]
        require(flow['late_process_resumed']['before'][name]==sample and sample['tick']==tick
                and -sample['state'][8]>2.5,'Frozen committed model state differs')
    action_time=request['command_id']/1e9
    require(action_time>flow['late_process_resumed']['status']['issued_monotonic_s']>fault['issued_monotonic_s'],
            'Recovery preceded late fault observation')
    require(not any(row['kind'] in ('step','sensor','gps') and
            fault['issued_monotonic_s']<=row['issued_monotonic_s']<action_time for row in wire),
            'Extra physical/input completion before explicit recovery')
    step=[row for row in wire if row['kind']=='step' and row['tick']==tick]
    require(len(step)==1 and step[0]['issued_monotonic_s']>=action_time
            and all(step[0][key]==inflight[key] for key in ('ap_source_frame','px4_source_time_us','model_ticks')),
            'Recovered step was replayed or changed original inputs')
    return dict(tick=tick,input_wait_seconds=wait,original_input_completed_after_action=True)


def model_boundary(flow,fault,life,wire,truth):
    frozen=fault['authority'];tick=frozen['tick'];pending=tick+1
    stack=flow['target'].removesuffix('-model')
    require(fault['type']=='TimeoutError' and frozen==flow['fault']['authority']
            and frozen['phase']=='faulted' and not frozen['recoverable'] and not frozen['input_pending']
            and frozen['pending_tick']==pending,'Model timeout was not an unrecoverable pending step')
    require(fault['physical_inflight']['stage']=='model' and fault['physical_inflight']['tick']==pending
            and fault['model_channels'][stack]['failed'] is True,'Failed model RPC was not poisoned')
    wait=fault['issued_monotonic_s']-flow['injection']['monotonic_s']
    require(3<=wait<3.3,'Model RPC did not use the approved 3s deadline')
    stopped=flow['injection'].get('kernel_stopped')
    require(stopped is not None and stopped['state']=='T' and all(stopped[key]==flow['injection']['identity'][key]
            for key in ('pid','pgid','start_ticks')),'Missing actual stopped-model kernel identity')
    late=flow['late_process_resumed']
    require(late['status']['authority']==frozen and 'recover' not in late['status']['allowed_actions'],
            'Late model response repaired authority or offered unsafe recovery')
    for name,rows in truth.items():
        require(len(rows) in (tick,pending),'A model executed beyond the one already-issued step')
        for phase in ('before','after'):
            sample=late[phase][name]
            require(sample['tick'] in (tick,pending) and sample==rows[sample['tick']-1],
                    'Partial model observation differs from raw trace')
        require(rows[-1]==late['after'][name],'Model advanced after the late response observation')
    require(not any(row['tick']>tick for row in wire),'Uncommitted model state reached a native wire')
    require(not any(row['kind'] in ('step','sensor','gps') and row['issued_monotonic_s']>=fault['issued_monotonic_s']
                    for row in wire),'Poisoned model caused further native/physical progress')
    for row in life:
        require(row['kind'] not in ('input_recovery_requested','input_recovery_verified','physics_recovery_verified'),
                'Model failure incorrectly followed input or physics recovery')
        if row['kind']=='permission':
            value=cdr_string(row['cdr_hex'])
            require(value['phase']!='recovering','Model failure published a recovery permission')
            if value['phase']=='faulted':require(value['tick']==tick,'Faulted model authority advanced')
    return dict(committed_tick=tick,uncommitted_tick=pending,retained_model_ticks={name:len(rows) for name,rows in truth.items()},
                observed_rpc_timeout_seconds=wait,late_response_not_committed=True,flight_completed=False)


def audit(evidence,*,current_host=False):
    root=evidence/'run';flow=read(evidence/'flow.json');result=read(root/'result.json')
    require(flow['status']=='pass' and flow['result']==result and flow['returncode']==0
            and not flow['remaining_manager_group'],
            'Driver or manager cleanup failed')
    require(len(result['epochs'])==2,'Expected old and cold-reset epochs')
    old,new=result['epochs'];epoch=old['epoch'];new_epoch=new['epoch'];run_id=result['run_id']
    require(epoch!=new_epoch and all(item['namespace_comparison']=='held_file_descriptors' for item in (old,new))
            and all(old['namespace_objects'][kind]!=new['namespace_objects'][kind] for kind in ('net','ipc','mnt')),
            'Cold reset reused namespaces or epoch')
    first=root/'epochs'/epoch;second=root/'epochs'/new_epoch
    retired=retained_identity(first,old,run_id,current_host=current_host)
    ground=retained_identity(second,new,run_id,current_host=current_host)
    if current_host:
        require(not group_members(flow['manager']['pgid']),'Owned manager group remains on the verified current host')
    require(retired['status']=='cold_reset' and ground['status']=='stopped' and not ground['tasks']
            and not ground['flight_completed'],'Reset did not leave idle fresh ground epoch')
    victim=retired['children'][flow['target']]
    require(all(flow['injection']['identity'][key]==victim['identity'][key] for key in ('pid','pgid','start_ticks'))
            and flow['injection']['executable']==retired['runtime_images']['ready'][flow['target']]['executable'],
            'Injection did not target retained owned executable/PID/start time')
    require(flow['injection']['status']['epoch']==epoch and flow['injection']['status']['phase']=='running'
            and all(v['state']['position'][2]>2.5 for v in flow['injection']['status']['participants'].values()),
            'Injection did not occur during real dual flight')
    model_case=flow['target'].endswith('-model')
    ordered=['start-task','cold-reset','stop'] if model_case else ['start-task','recover','start-recovery-task','cold-reset','stop']
    require([row['response']['action'] for row in flow['actions']]==ordered,'Unexpected action sequence')
    requests={};responses={}
    for row in flow['actions']:
        request=row['submitted']['request'];response=row['response']
        validate_request(request,run_id,new_epoch if request['action']=='stop' else epoch)
        name=f"{request['command_id']:020d}-{request['token']}.json"
        require(read(root/'actions'/name)==request and read(root/'action-results'/request['epoch']/(request['token']+'.json'))==response
                and response['state']=='completed','Formal action lacks retained completion')
        requests[request['action']]=request;responses[request['action']]=response
    require(responses['cold-reset']['new_epoch']==new_epoch,'Reset response has wrong epoch')
    life=list(lines(first/'scene-lifecycle.jsonl'));wire=list(lines(first/'wire.jsonl'))
    faults=read(first/'faults.json')
    require(faults==retired['faults']==[row['observation'] for row in life if row['kind']=='fault_latched']
            and len(faults)==1,'Fault latch summary differs from original LC')
    fault=faults[0];tick=fault['authority']['tick']
    truth={stack:list(lines(first/(stack+'-truth.jsonl'))) for stack in ('arducopter','px4')}
    if model_case:
        boundary=model_boundary(flow,fault,life,wire,truth)
        require(not retired['flight_completed'] and retired['physical_task_proof'] is None
                and result['status']=='stopped','Model fault falsely completed a flight')
        require(len(retired['tasks'])==2 and all(report['status']=='failed' and report['task_mode']=='initial'
                for report in retired['tasks'].values()),'Old tasks did not fail without replacement')
        timeline,_=audit_timeline(ProductTimeline(first),dict(final_authority=retired['authority'],scene_epoch=epoch,
            clock_publications=retired['clock_publications']),require_ground=False,pending_model_tick=tick+1)
        lc=lifecycle(first,epoch,tick,retired['clock_publications'],run_id)
        reset,reset_strict,reset_lc=audit_product_timeline(second,ground,require_flight=False)
        ground_events,_,counts=raw_public(second,new_epoch,run_id)
        require(all(v['max_height_m']<.3 for v in reset['physical'].values()) and all(not any(
            event['event'] in ('native_ack','setup_completed','command_accepted') for event in events)
            for events in ground_events.values()),'Model cold reset replayed a task')
        return dict(status='pass',scope='Real model RPC timeout, poisoned late response, explicit cold reset; not a completed flight',
            target=flow['target'],boundary=boundary,committed_timeline=timeline,reset_timeline=reset,
            lifecycle=[lc,reset_lc],reset_strict_barriers=reset_strict,ground_raw_state_counts=counts,
            epochs=[epoch,new_epoch],current_host_verification=current_host,
            limitations=['Uncommitted model rows are retained and audited separately; no rollback or hot recovery is claimed.',
                         'Recorded image/cleanup evidence is historical unless --current-host explicitly verifies a matching boot.'])
    require(retired['flight_completed'] and result['status']=='pass','Input recovery did not complete flight')
    boundary=input_boundary(flow,fault,life,wire,truth,requests['recover'])
    recovery=responses['recover']['observation']
    require([row['observation'] for row in life if row['kind']=='physics_recovery_verified']==[recovery]
            and 0<recovery['wall_seconds']<5 and recovery['task_control_released'],'Recovery readiness evidence differs')
    acks=[cdr_string(row['cdr_hex']) for row in life if row['kind']=='ack_raw']
    permissions=[cdr_string(row['cdr_hex']) for row in life if row['kind']=='permission']
    require(set(recovery['control_ack'])=={'1','2'},'Missing dual recovery ACK')
    for ack in recovery['control_ack'].values():
        require(ack in acks and ack['ready'] and ack['task_control_released'] and ack['phase']=='recovering'
                and ack['source_boot_ns']>tick*1000000 and ack['home_initialized'] and ack['native_flying'],
                'Recovery used stale or unreleased native ACK')
    require(all(p['tick']==tick for p in permissions if p['phase']=='faulted'),'Fault permission advanced time')
    events,last,counts=raw_public(first,epoch,run_id)
    summaries=tasks(first,retired,run_id,epoch,recovery,events)
    physical=verify_tasks(first,epoch,retired['authority']['tick'],retired['tasks'])
    require(physical==retired['physical_task_proof'],'Physical task proof differs')
    flight,strict,lc=audit_product_timeline(first,retired)
    reset,reset_strict,reset_lc=audit_product_timeline(second,ground,require_flight=False)
    ground_events,ground_last,ground_counts=raw_public(second,new_epoch,run_id)
    require(all(v['max_height_m']<.3 for v in reset['physical'].values()),'Cold reset moved before task')
    for uid in (1,2):
        require(last[uid].control_epoch!=ground_last[uid].control_epoch and not any(
            event['event'] in ('native_ack','setup_completed','command_accepted') for event in ground_events[uid]),
            'Reset replayed an old control/task identity')
    return dict(status='pass',scope='Owned FC input stall, original barrier repair, new public flight and cold reset',
                target=flow['target'],boundary=boundary,tasks=summaries,physical_task_proof=physical,
                flight_timeline=flight,reset_timeline=reset,strict_barriers=[strict,reset_strict],
                lifecycle=[lc,reset_lc],raw_state_counts=[counts,ground_counts],epochs=[epoch,new_epoch],
                current_host_verification=current_host,
                limitations=['SIGSTOP/SIGCONT causality uses retained driver PID/executable/start_ticks observations, not an independent kernel signal trace.',
                             '5s wall check allows 200ms observation/scheduling overhead; it does not extend the configured deadline.',
                             'Default uses retained process/image/cleanup evidence; live process/file checks require --current-host and a matching recorded boot identity.'])


def tasks(first,retired,run_id,epoch,recovery,events):
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
    return summaries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--current-host',action='store_true')
    args=parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.directory.resolve()),'Output must be outside evidence')
    repo=Path(__file__).resolve().parents[1]
    paths=[Path(__file__),*(repo/'tools').glob('audit_joint_*.py'),
           repo/'Simulator/wksim_runtime/evidence.py',repo/'Simulator/wksim_runtime/joint_evidence.py',
           repo/'Simulator/wksim_runtime/joint_actions.py',repo/'Simulator/wksim_core/ap_json.py',
           repo/'Simulator/wksim_core/px4_mavlink.py']
    before={str(p.relative_to(repo)):digest(p) for p in paths}
    try:
        report=audit(args.directory,current_host=args.current_host)
        report['evidence_sha256']={str(p.relative_to(args.directory)):digest(p) for p in sorted(args.directory.rglob('*')) if p.is_file()}
    except (ValueError,KeyError,OSError,TypeError,ImportError,StopIteration,AssertionError) as error:
        report=dict(status='failed',error=repr(error))
    after={str(p.relative_to(repo)):digest(p) for p in paths}
    report.update(audit_dependencies_before=before,audit_dependencies_after=after)
    if before!=after: report.update(status='failed',error='Audit dependency changed during execution')
    write_json(args.output,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('evidence_sha256','physical_task_proof')},indent=2))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
