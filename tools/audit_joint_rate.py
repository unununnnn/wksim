"""Independent schedule, raw joint flight and phase-aware rate-window audit."""
import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from audit_joint_flight import digest,lines,require
from audit_joint_product import audit_epoch
from audit_joint_product_lifecycle import retained_identity


def read(path):return json.loads(Path(path).read_text())


def schedule(path,epoch,*,allow_failure=False):
    segments={};active=None;pending=None;previous_end=None
    for row in lines(path):
        require(row['epoch']==epoch,'Rate trace crossed epoch')
        kind=row['kind']
        if kind=='rate_anchor':
            require(pending is None and row['segment_id'] not in segments,'Anchor interrupted or reused a group')
            require(row['requested_rate'] in (.5,1) and row['anchor']['tick']%4==0,'Invalid rate/anchor')
            active=dict(anchor=row,groups=[],previous_start=None,worst_ns=0)
            segments[row['segment_id']]=active
        elif kind=='rate_group_start':
            require(active is not None and pending is None and row['segment_id']==active['anchor']['segment_id'],
                    'Group start lacks a unique active anchor')
            anchor=active['anchor'];period=int(4_000_000/anchor['requested_rate'])
            index=len(active['groups']);tick=anchor['anchor']['tick']+4*index
            ideal=anchor['anchor']['wall_ns']+index*period
            earliest=max(ideal,ideal if active['previous_start'] is None else active['previous_start']+period)
            require(row['tick']==row['start_tick']==tick and row['end_tick']==tick+4
                    and row['requested_rate']==anchor['requested_rate'] and row['request_id']==anchor['request_id']
                    and row['ideal_start_ns']==ideal and row['ideal_end_ns']==ideal+period
                    and row['earliest_start_ns']==earliest and row['actual_start_ns']>=earliest
                    and (previous_end is None or row['actual_start_ns']>=previous_end),
                    'Rate group changed tick/identity/ideal schedule or caught up an overdue group')
            require(row['lateness_ns']==max(0,row['actual_start_ns']-ideal),'Start phase error was relabelled')
            active['worst_ns']=max(active['worst_ns'],row['lateness_ns'])
            active['previous_start']=row['actual_start_ns'];pending=row
        elif kind=='rate_group_end':
            require(pending is not None and all(row[key]==pending[key] for key in
                    ('segment_id','request_id','requested_rate','transition','start_tick','end_tick','ideal_start_ns',
                     'ideal_end_ns','earliest_start_ns','actual_start_ns'))
                    and row['tick']==row['end_tick'] and row['actual_end_ns']>=row['actual_start_ns'],
                    'Rate group completion changed or lacks its original start')
            require(row['lateness_ns']==max(0,row['actual_end_ns']-row['ideal_end_ns']),'End phase error was relabelled')
            active['worst_ns']=max(active['worst_ns'],row['lateness_ns'])
            active['groups'].append(row);previous_end=row['actual_end_ns'];pending=None
        elif kind=='rate_boundary_check':
            require(active is not None and pending is None,'Boundary check lacks a completed active group')
            anchor=active['anchor'];tick=anchor['anchor']['tick']+4*len(active['groups'])
            ideal=anchor['anchor']['wall_ns']+len(active['groups'])*int(4_000_000/anchor['requested_rate'])
            require(row['tick']==row['boundary_tick']==tick and row['segment_id']==anchor['segment_id']
                    and row['request_id']==anchor['request_id'] and row['requested_rate']==anchor['requested_rate']
                    and row['ideal_boundary_ns']==ideal and row['actual_check_ns']>=anchor['anchor']['wall_ns']
                    and (previous_end is None or row['actual_check_ns']>=previous_end)
                    and row['lateness_ns']==max(0,row['actual_check_ns']-ideal),
                    'Boundary check changed the old active schedule or its actual phase error')
            active['worst_ns']=max(active['worst_ns'],row['lateness_ns'])
        elif kind=='rate_segment_end':
            require(active is not None and pending is None and row['segment_id']==active['anchor']['segment_id']
                    and row['completed_groups']==len(active['groups']) and row['worst_lateness_ns']==active['worst_ns'],
                    'Segment summary hid an incomplete group or phase error')
            active=None
        elif kind=='rate_unmet':
            require(allow_failure and active is not None and pending is None
                    and row['segment_id']==active['anchor']['segment_id'] and row['lateness_ns']>100_000_000
                    and row['tick']==active['anchor']['anchor']['tick']+4*len(active['groups'])
                    and 'failure' not in active,'This cohort contains a real resource-insufficient segment')
            active['failure']=row
            active['worst_ns']=max(active['worst_ns'],row['lateness_ns'])
    require(pending is None and active is None and segments,'Unclosed/absent timed schedule')
    require(all(s['worst_ns']<=100_000_000 or allow_failure and 'failure' in s for s in segments.values()),
            'Approved cumulative lateness exceeded without a fault record')
    return segments


def measurement(start,end,rate):
    wall=(end['actual_end_ns']-start['actual_end_ns'])/1e9
    measured=(end['end_tick']-start['end_tick'])*.001/wall
    return dict(start_tick=start['end_tick'],end_tick=end['end_tick'],wall_seconds=wall,
                measured_rate=measured,relative_error=measured/rate-1)


def audit_failure(root):
    root=Path(root);wrapper_path=root/'wrapper.json';run_path=root/'run/result.json'
    require(wrapper_path.exists(),'Missing wrapper.json')
    require(run_path.exists(),'Missing run/result.json')
    wrapper=read(wrapper_path);run=read(run_path)
    require(not wrapper.get('remaining_manager_group'),'Lingering processes after failure')
    require(type(wrapper.get('manager_returncode')) is int
            and wrapper['manager_returncode'] != 0,'Failure manager must exit nonzero')
    if 'driver_returncode' in wrapper:
        require(type(wrapper['driver_returncode']) is int
                and wrapper['driver_returncode'] != 0,'Failure driver must exit nonzero')
    require(wrapper.get('mode')=='steady','Failure case was not the frozen steady mode')
    require(run.get('status')=='failed','Failure audit requires failed run status')
    require(isinstance(run.get('run_id'),str) and run['run_id'],'Run identity missing')
    require(isinstance(run.get('epochs'),list) and len(run['epochs'])==1,
            'Failure case must contain exactly one epoch record')
    item=run['epochs'][0];epoch=item.get('epoch')
    require(isinstance(epoch,str) and len(epoch)==32 and epoch==epoch.lower()
            and all(c in '0123456789abcdef' for c in epoch),'Invalid epoch in run result')
    epoch_result=item.get('result',{})
    require(epoch_result.get('status')=='failed'
            and epoch_result.get('run_id')==run['run_id']
            and epoch_result.get('epoch')==epoch,
            'Epoch result status or identity is invalid')
    directory=root/'run/epochs'/epoch
    require(directory.is_dir(),'Epoch directory missing')
    faults=epoch_result.get('faults')
    if not faults and (directory/'faults.json').exists():
        faults=read(directory/'faults.json')
    require(isinstance(faults,list) and faults,'Missing faults record')
    rate_fault=next((f for f in faults if f.get('type')=='RateUnmet'
                     or 'rate_unmet' in str(f.get('fault',''))
                     or 'RateUnmet' in str(f.get('error',''))),None)
    require(rate_fault is not None,'Missing RateUnmet in faults record')
    rate_path=directory/'rate.jsonl'
    require(rate_path.exists(),'Missing rate.jsonl in epoch directory')
    segments=schedule(rate_path,epoch,allow_failure=True)
    failed_segments=[s for s in segments.values() if 'failure' in s]
    require(len(failed_segments)==1,'Expected exactly one certified rate_unmet segment')
    failed_segment=failed_segments[0]
    fail_row=failed_segment['failure']
    require(fail_row.get('kind')=='rate_unmet','Failure record is not rate_unmet')
    require(fail_row.get('reason')=='resource_insufficient','Failure reason is not resource_insufficient')
    require(fail_row.get('lateness_ns',0)>100_000_000,'Failure lateness did not exceed 100ms threshold')
    require(failed_segment['worst_ns']>100_000_000,'Worst lateness did not exceed 100ms')
    requested_rate=run.get('config',{}).get('requested_rate')
    require(requested_rate==failed_segment['anchor']['requested_rate']
            and wrapper.get('requested_rate')==requested_rate,
            'Requested rate identity differs across wrapper/run/schedule')
    authority=rate_fault.get('authority')
    require(isinstance(authority,dict) and authority.get('epoch')==epoch
            and authority.get('tick')==fail_row.get('tick')
            and authority.get('fault')=='rate_unmet/resource_insufficient',
            'Runtime fault authority does not match the rate_unmet row')
    source_sha=epoch_result.get('source_sha256')
    require(isinstance(source_sha,dict) and source_sha
            and all(isinstance(path,str) and isinstance(value,str) and len(value)==64
                    and value==value.lower() and all(c in '0123456789abcdef' for c in value)
                    for path,value in source_sha.items()),'Source identity is absent or malformed')
    code_snapshot=hashlib.sha256(json.dumps(source_sha,sort_keys=True).encode()).hexdigest()
    return dict(status='failed',classification='rate_unmet',epoch=epoch,run_id=run.get('run_id'),
                requested_rate=requested_rate,code_snapshot=code_snapshot,
                failure_tick=fail_row.get('tick'),lateness_ns=fail_row.get('lateness_ns'),
                worst_lateness_ns=failed_segment['worst_ns'],reason=fail_row.get('reason'),
                completed_groups=failed_segment.get('completed_groups',len(failed_segment.get('groups',[]))),
                fault_authority=authority,
                limitations=['Certified RateUnmet failure: run exceeded 100ms phase limit without steady window. Non-PASS.'])


def audit_steady(root):
    root=Path(root);wrapper=read(root/'wrapper.json');flow=read(root/'flow.json');run=read(root/'run/result.json')
    require(wrapper['driver_returncode']==wrapper['manager_returncode']==0 and not wrapper['remaining_manager_group']
            and flow['status']=='behavior_pass' and flow['mode']=='steady' and flow['result']==run
            and run['status']=='pass' and len(run['epochs'])==1,'Steady formal flight/cleanup did not pass')
    require(read(root/'experiment.json')['task_dwell_seconds']=={'hold':35,'waypoint':35},'Cohort dwell differs from preset')
    item=run['epochs'][0];directory=root/'run/epochs'/item['epoch']
    result=retained_identity(directory,item,run['run_id'])
    native=audit_epoch(root/'run',item,run['run_id'])
    require(not result.get('faults') and result['task_dwell_seconds']=={'hold':35,'waypoint':35},'Healthy rate cohort faulted/changed dwell')
    initialization=result.get('initialization')
    if initialization:
        require(initialization['physical_tick']==0 and initialization['task_execution_requires_explicit_go']
                and all(r['tick']==0 and r['state'] is None for r in initialization['models']['models'].values()),
                'Transport initialization consumed a model step')
    start_action=next(r['submitted']['request'] for r in flow['actions'] if r['response']['action']=='start-task')
    from rclpy.serialization import deserialize_message
    from prometheus_msgs.msg import TextInfo
    for row in lines(directory/'public-dds.jsonl'):
        if row['topic'].endswith('/text_info'):
            event=json.loads(deserialize_message(bytes.fromhex(row['cdr_hex']),TextInfo).message)
            if event.get('request_id',0)>0 and event.get('event') in ('setup_completed','command_accepted','native_ack'):
                require(row['received_monotonic_s']>=start_action['command_id']/1e9,
                        'Public/native task acceptance preceded the explicit start action')
    phases={}
    for report in result['tasks'].values():
        require(report['task_dwell_seconds']==result['task_dwell_seconds'],'Task ignored configured dwell')
        values={p['phase']:p['ros_time_ns']//1_000_000 for p in report['phases']}
        phases[report['stack']]=values
        for start,end in (('takeoff_reached','hold_completed'),('waypoint_reached','waypoint_completed')):
            require(values[end]-values[start]>=35000,'Task did not complete predeclared 35s simulated dwell')
    intervals={name:(max(p[start] for p in phases.values()),min(p[end] for p in phases.values()))
               for name,start,end in (('hold','takeoff_reached','hold_completed'),('waypoint','waypoint_reached','waypoint_completed'))}
    heights={stack:[-row['state'][8] for row in lines(directory/(stack+'-truth.jsonl'))] for stack in ('arducopter','px4')}
    bad_air=[0];bad_ground=[0]
    for a,b in zip(heights['arducopter'],heights['px4']):
        bad_air.append(bad_air[-1]+int(min(a,b)<=1))
        bad_ground.append(bad_ground[-1]+int(max(abs(a),abs(b))>=.3))
    def category(lo,hi):
        if bad_air[hi]==bad_air[lo]:
            return next((name for name,(a,b) in intervals.items() if a<=lo and hi<=b),'airborne_transition')
        return 'ground' if bad_ground[hi]==bad_ground[lo] else 'mixed_transition'
    timed=[]
    for segment in schedule(directory/'rate.jsonl',item['epoch']).values():
        anchor=segment['anchor']
        if anchor['anchor']['transition']:continue
        require(anchor['steady_after_ns']==anchor['anchor']['wall_ns']+2_000_000_000,'Stabilization boundary changed')
        samples=segment['groups'];ends=[s['actual_end_ns'] for s in samples]
        start=bisect_left(ends,anchor['steady_after_ns']);first=start;windows=[]
        while start<len(samples):
            end=bisect_left(ends,ends[start]+10_000_000_000)
            if end==len(samples):break
            value=measurement(samples[start],samples[end],anchor['requested_rate'])
            value['phase']=category(value['start_tick'],value['end_tick'])
            require(abs(value['relative_error'])<=.02,'A complete 10s window exceeded the approved 2% budget')
            windows.append(value);start=end
        sixty=None;airborne_sixty=None
        if first<len(samples):
            end=bisect_left(ends,ends[first]+60_000_000_000)
            if end<len(samples):sixty=measurement(samples[first],samples[end],anchor['requested_rate'])
            for begin in range(first,len(samples)):
                end=bisect_left(ends,ends[begin]+60_000_000_000)
                if end==len(samples):break
                lo,hi=samples[begin]['end_tick'],samples[end]['end_tick']
                if bad_air[hi]==bad_air[lo]:
                    airborne_sixty=measurement(samples[begin],samples[end],anchor['requested_rate']);break
        for value in (sixty,airborne_sixty):
            if value:require(abs(value['relative_error'])<=.01,'A 60s segment exceeded the approved 1% budget')
        timed.append(dict(segment_id=anchor['segment_id'],requested_rate=anchor['requested_rate'],windows=windows,
                          first_sixty_seconds=sixty,airborne_sixty_seconds=airborne_sixty,worst_lateness_ns=segment['worst_ns']))
    require(any(s['airborne_sixty_seconds'] for s in timed),'No continuous 60s airborne performance segment')
    require(all(any(w['phase']==name for s in timed for w in s['windows']) for name in ('hold','waypoint')),
            'Missing a full 10s window in each sustainable dual flight stage')
    code_snapshot=hashlib.sha256(json.dumps(result['source_sha256'],sort_keys=True).encode()).hexdigest()
    return dict(status='pass',epoch=item['epoch'],requested_rate=result['requested_rate'],code_snapshot=code_snapshot,
                raw_native_and_physical=native,initialized_without_steps=bool(initialization),
                timed_segments=timed,limitations=['No UE load in this cohort; higher rates, lifecycle and overload are separate.',
                    'Rate error budgets are wall performance budgets, not G6 dynamics equivalence tolerances.'])


def audit(root,*,mode='steady',allow_failure=False):
    is_failure=(mode=='failure') or allow_failure
    flow_path=Path(root)/'flow.json'
    if not flow_path.exists():
        if not is_failure:
            raise ValueError('Steady formal flight requires flow.json; use --mode failure or --allow-failure for RateUnmet runs')
        return audit_failure(root)
    if is_failure:
        run_path=Path(root)/'run/result.json'
        if run_path.exists() and read(run_path).get('status')=='failed':
            return audit_failure(root)
        raise ValueError('Failure audit mode cannot be used to accept a passing run')
    return audit_steady(root)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',nargs='+',type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--require-epochs',type=int,choices=(1,3),default=1)
    parser.add_argument('--mode',choices=('steady','failure'),default='steady')
    parser.add_argument('--allow-failure',action='store_true')
    args=parser.parse_args()
    require(all(not args.output.resolve().is_relative_to(p.resolve()) for p in args.directories),'Output must be outside evidence')
    failure_mode=(args.mode=='failure') or args.allow_failure
    require(not failure_mode or not args.output.exists(),
            'Failure audit output already exists; refusing to overwrite retained evidence')
    result=dict(status='failed',runs=[],required_epochs=args.require_epochs,mode=args.mode,
                allow_failure=failure_mode,audit_sha256=digest(__file__))
    for path in args.directories:
        try:result['runs'].append(audit(path,mode=args.mode,allow_failure=failure_mode))
        except (OSError,ValueError,KeyError,TypeError,ImportError,AssertionError) as error:
            result['runs'].append(dict(status='failed',directory=str(path),error=repr(error)))
    if (not failure_mode
            and all(r.get('status')=='pass' for r in result['runs'])
            and len({r['epoch'] for r in result['runs'] if r.get('epoch')})>=args.require_epochs
            and len({r['requested_rate'] for r in result['runs'] if r.get('requested_rate')})==1
            and len({r['code_snapshot'] for r in result['runs'] if r.get('code_snapshot')})==1):result['status']='pass'
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'],runs=[{k:r.get(k) for k in ('status','epoch','classification','lateness_ns','error') if k in r} for r in result['runs']])))
    raise SystemExit(0 if result['status']=='pass' else 1)
