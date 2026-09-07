"""Small real-FC driver for an already started formal joint_scene service.

Run in its WSL environment. A single run is never the three-epoch acceptance.
The configured dwell times and performance budgets are recorded before actions.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.evidence import write_json,json_identity,process_identity
from Simulator.wksim_runtime.joint_actions import submit
from Simulator.wksim_runtime.joint_rate import validate_rate


def rate_windows(path):
    """Report all full non-overlapping windows, with no speed-based filtering."""
    segments={}
    for line in path.read_text().splitlines():
        row=json.loads(line)
        if row['kind']=='rate_anchor':
            segments[row['segment_id']]=dict(anchor=row,groups=[],lateness=[])
        elif row['kind']=='rate_group_end':
            segments[row['segment_id']]['groups'].append(row)
        if row['kind'] in ('rate_group_start','rate_group_end','rate_unmet'):
            segments[row['segment_id']]['lateness'].append(row['lateness_ns'])
    reports=[]
    for segment in segments.values():
        anchor=segment['anchor'];groups=segment['groups']
        if anchor['anchor']['transition']: continue
        usable=[row for row in groups if row['actual_end_ns']>=anchor['steady_after_ns']]
        windows=[]
        start=usable[0] if usable else None
        for end in usable[1:]:
            if end['actual_end_ns']-start['actual_end_ns']<10_000_000_000: continue
            seconds=(end['actual_end_ns']-start['actual_end_ns'])/1e9
            measured=(end['end_tick']-start['end_tick'])*.001/seconds
            error=measured/anchor['requested_rate']-1
            windows.append(dict(start_tick=start['end_tick'],end_tick=end['end_tick'],wall_seconds=seconds,
                measured_rate=measured,relative_error=error,passed=abs(error)<=.02))
            start=end
        sixty=None
        if usable:
            first=usable[0]
            last=next((row for row in usable if row['actual_end_ns']-first['actual_end_ns']>=60_000_000_000),None)
            if last:
                seconds=(last['actual_end_ns']-first['actual_end_ns'])/1e9
                measured=(last['end_tick']-first['end_tick'])*.001/seconds
                error=measured/anchor['requested_rate']-1
                sixty=dict(start_tick=first['end_tick'],end_tick=last['end_tick'],wall_seconds=seconds,
                           measured_rate=measured,relative_error=error,passed=abs(error)<=.01)
        reports.append(dict(segment_id=anchor['segment_id'],requested_rate=anchor['requested_rate'],
            windows=windows,sixty_seconds=sixty,worst_lateness_ns=max(segment['lateness'],default=None),
            classification='phase_classification_requires_independent_truth_audit'))
    return reports


def run(directory,output,mode):
    directory=directory.resolve(strict=True)
    config=json.loads((directory/'config.json').read_text())
    evidence=dict(status='failed',scope='one_real_epoch_behavior_not_full_rate_acceptance',mode=mode,
        config=config,actions=[],budgets=dict(lateness_ns=100_000_000,stabilization_s=2,
        window_seconds=10,window_relative_error=.02,segment_seconds=60,segment_relative_error=.01))
    write_json(output,evidence)
    def status(): return json.loads((directory/'status.json').read_text())
    def wait(label,predicate,seconds=240,allow_fault=False):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=status()
            if value['phase'] in ('failed','stopped') or (value['authority']['phase']=='faulted' and not allow_fault):
                raise RuntimeError(label+': '+str(value['authority']))
            if predicate(value): return value
            time.sleep(.02)
        raise TimeoutError(label)
    def action(name,epoch,rate=None):
        request=submit(directory,name,epoch,rate)
        target=Path(request['result_file'])
        deadline=time.monotonic()+(180 if name=='cold-reset' else 25)
        while time.monotonic()<deadline:
            if target.is_file():
                response=json.loads(target.read_text())
                if response['state']=='completed':
                    evidence['actions'].append(dict(submitted=request,response=response))
                    write_json(output,evidence)
                    return response
                if response['state'] in ('failed','rejected'): raise RuntimeError(str(response))
            time.sleep(.02)
        raise TimeoutError(name)
    try:
        ready=wait('ground ready',lambda row:'start-task' in row['allowed_actions'])
        epoch=ready['epoch'];epoch_dir=Path(ready['epoch_dir'])
        assert ready['rate']['requested_rate']==validate_rate(config['requested_rate'])
        evidence['epoch']=epoch
        if mode=='ground-reset':
            action('cold-reset',epoch)
            fresh=wait('fresh cold-reset ground',lambda row:row['epoch']!=epoch and 'start-task' in row['allowed_actions'])
            retired=dict(version=1,run_id=config['run_id'],epoch=epoch,command_id=time.monotonic_ns(),
                         action='set-rate',requested_rate=1,offer_token=ready['offer_token'],token=uuid.uuid4().hex)
            name=f"{retired['command_id']:020d}-{retired['token']}.json"
            write_json(directory/'actions'/name,retired)
            rejected=directory/'action-results'/fresh['epoch']/('rejected-'+name)
            deadline=time.monotonic()+5
            while not rejected.is_file() and time.monotonic()<deadline:time.sleep(.02)
            rejection=json.loads(rejected.read_text())
            assert rejection['state']=='rejected' and rejection['request']==retired
            assert status()['task_state']=='idle' and status()['rate']['requested_rate']==config['requested_rate']
            evidence['reset']=dict(old_epoch=epoch,new_epoch=fresh['epoch'],rejected_rate_request=rejection)
            action('stop',fresh['epoch'])
            deadline=time.monotonic()+25
            while not (directory/'result.json').is_file() and time.monotonic()<deadline:time.sleep(.02)
            result=json.loads((directory/'result.json').read_text())
            assert result['status']=='stopped' and len(result['epochs'])==2
            assert all(not r['result']['tasks'] and not r['result']['flight_completed']
                       and not r['remaining_group_members'] for r in result['epochs'])
            evidence.update(status='behavior_pass',scope='ground_cold_reset_and_retired_rate_rejection_not_flight',result=result)
            return evidence
        action('start-task',epoch)
        if mode in ('lifecycle','overload'):
            airborne=wait('both tasks airborne',lambda row:'pause' in row['allowed_actions'] and
                all(peer['state']['armed'] and peer['state']['position'][2]>2.5 for peer in row['participants'].values()))
            if mode=='lifecycle':
                for value in (1,.5):
                    wait('healthy rate offer',lambda row:'set-rate' in row['allowed_actions'])
                    action('set-rate',epoch,value)
                    began=time.monotonic()
                    while time.monotonic()-began<3:
                        row=status()
                        if row['authority']['phase']=='faulted': raise RuntimeError(str(row['authority']))
                        time.sleep(.02)
                paused=action('pause',epoch)
                tick=paused['authority']['tick'];began=time.monotonic()
                while time.monotonic()-began<4:
                    assert status()['authority']['tick']==tick
                    time.sleep(.02)
                step=action('step',epoch)
                assert step['authority']['tick']==tick+4
                wait('step acknowledged',lambda row:'resume' in row['allowed_actions'])
                action('resume',epoch)
            else:
                identity=airborne['supervisor'];current=json_identity(identity['pid'])
                if current is None or any(current[key]!=identity[key] for key in ('pid','pgid','start_ticks')):
                    raise RuntimeError('Owned supervisor identity changed before overload injection')
                executable=(Path('/proc')/str(current['pid'])/'exe').resolve(strict=True)
                if executable!=Path(sys.executable).resolve(strict=True):
                    raise RuntimeError('Overload target is not the admitted Python supervisor')
                # This is an explicit test-only external scheduling interruption,
                # not a hidden runtime setting or a change to a timing budget.
                injection=dict(supervisor=current,executable=str(executable),start_ns=time.monotonic_ns(),requested_delay_s=.15)
                os.kill(current['pid'],signal.SIGSTOP)
                try:
                    deadline=time.monotonic()+1
                    while time.monotonic()<deadline:
                        actual=process_identity(current['pid'])
                        if actual is not None and actual['state']=='T':break
                        time.sleep(.002)
                    assert actual is not None and actual['state']=='T'
                    assert all(actual[key]==current[key] for key in ('pid','pgid','start_ticks'))
                    injection['kernel_stopped']={key:actual[key] for key in ('pid','pgid','start_ticks','state')}
                    injection['confirmed_stop_ns']=time.monotonic_ns()
                    time.sleep(.15)
                finally:
                    actual=json_identity(current['pid'])
                    if actual is not None and all(actual[key]==current[key] for key in ('pid','pgid','start_ticks')):
                        os.kill(current['pid'],signal.SIGCONT)
                injection['end_ns']=time.monotonic_ns();evidence['injection']=injection
                failed=wait('rate failure',lambda row:row['authority']['phase']=='faulted',15,True)
                assert failed['authority']['fault']=='rate_unmet/resource_insufficient'
                tick=failed['authority']['tick']
                assert tick%4==0 and failed['authority']['last_barrier_tick']==tick
                assert 'set-rate' not in failed['allowed_actions']
                began=time.monotonic()
                while time.monotonic()-began<4:
                    assert status()['authority']['tick']==tick
                    time.sleep(.02)
                evidence['frozen_tick']=tick
                evidence['fault_status']=failed
                wait('old tasks retired',lambda row:'recover' in row['allowed_actions'],15,True)
                action('recover',epoch)
                recovered=wait('new recovery task required',lambda row:'start-recovery-task' in row['allowed_actions'])
                assert recovered['task_state']=='recovery_required'
                action('start-recovery-task',epoch)
        completed=wait('public task completion',lambda row:row['task_state']=='completed',
                       max(900,sum(config['task_dwell_seconds'].values())/config['requested_rate']+240))
        assert all(not peer['state']['armed'] for peer in completed['participants'].values())
        action('stop',epoch)
        deadline=time.monotonic()+25
        while not (directory/'result.json').is_file() and time.monotonic()<deadline: time.sleep(.02)
        result=json.loads((directory/'result.json').read_text())
        assert result['status']=='pass' and all(not row['remaining_group_members'] for row in result['epochs'])
        evidence['rate_report']=rate_windows(epoch_dir/'rate.jsonl')
        evidence['result']=result
        evidence['status']='behavior_pass'
    except BaseException as error:
        evidence['error']=repr(error)
        try:
            current=status()
            if 'stop' in current['allowed_actions']: action('stop',current['epoch'])
        except Exception as cleanup: evidence['cleanup_error']=repr(cleanup)
        raise
    finally: write_json(output,evidence)
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=('steady','lifecycle','overload','ground-reset'),default='steady')
    args=parser.parse_args()
    print(json.dumps({'status':run(args.directory,args.output,args.mode)['status'],'output':str(args.output)}))
