"""Drive the formal joint action API through the public velocity+yaw task; independent evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.evidence import write_json

EXPECTED=('autonomous_hold_ready','arming_completed','armed','task_control_ready','takeoff_reached',
          'hold_completed','velocity_step_accepted','velocity_step_settled','velocity_step_tracking',
          'velocity_hold_accepted','velocity_hold_settled','velocity_zero_hold',
          'yaw_rate_accepted','yaw_rate_tracking','land_accepted','landed_disarmed_public',
          'ground_hold_completed','normal_stop_ready')
AP_EXTRA=('velocity_rehold_accepted','velocity_rehold_settled','invalid_combo_rejected',
          'invalid_combo_no_side_effects')


def run(directory,output):
    evidence=dict(directory=str(directory),actions=[],tasks={})
    def status():
        path=directory/'status.json'
        return json.loads(path.read_text()) if path.is_file() else None
    def wait(label,predicate,seconds=300):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=status()
            if value and value['phase']=='failed':
                detail=json.loads((Path(value['epoch_dir'])/'result.json').read_text())
                raise RuntimeError(label+': '+str(detail.get('error')))
            if value and predicate(value): return value
            time.sleep(.05)
        raise TimeoutError(label)
    def action(name,epoch,seconds=20):
        command=[sys.executable,'-B','-m','Simulator.wksim_runtime.joint_actions',str(directory),name,'--epoch',epoch]
        submitted=json.loads(subprocess.check_output(command,cwd=REPO,text=True))
        target=Path(submitted['result_file'])
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if target.is_file():
                response=json.loads(target.read_text())
                if response['state']=='completed':
                    evidence['actions'].append(dict(command=command,submitted=submitted,response=response))
                    return response
                if response['state'] in ('failed','rejected'): raise RuntimeError(str(response))
            time.sleep(.02)
        raise TimeoutError('Action did not complete: '+name)
    try:
        ready=wait('native ground ready',lambda value:'start-task' in value['allowed_actions'])
        epoch=ready['epoch'];epoch_dir=Path(ready['epoch_dir'])
        action('start-task',epoch)
        completed=wait('public velocity yaw tasks completed',lambda value:value['task_state']=='completed')
        assert all(not peer['state']['armed'] for peer in completed['participants'].values())
        groups=list(epoch_dir.glob('tasks/*'))
        assert len(groups)==1,'Expected exactly one task group'
        for stack in ('arducopter','px4'):
            report=json.loads((groups[0]/stack/'result.json').read_text())
            assert report['status']=='pass' and report['task_mode']=='initial',stack
            phases=[row['phase'] for row in report['phases']]
            missing=[name for name in EXPECTED if name not in phases]
            assert not missing,(stack,missing)
            envelopes=report['task']['request_envelopes']
            commands=[row['command']['command_id'] for row in envelopes if 'command' in row]
            assert commands==list(range(1,len(commands)+1)),commands
            if stack=='arducopter':
                extra=[name for name in AP_EXTRA if name not in phases]
                assert not extra,(stack,extra)
                rejections=[row for row in report['task']['events'] if row.get('event')=='command_rejected']
                assert any(row.get('reason')=='arducopter_velocity_requires_yaw_rate_mode'
                           and row.get('command_id')==5 for row in rejections),rejections
            evidence['tasks'][stack]=report
        action('stop',epoch)
        deadline=time.monotonic()+20
        while not (directory/'result.json').is_file() and time.monotonic()<deadline: time.sleep(.05)
        result=json.loads((directory/'result.json').read_text())
        assert result['status']=='pass'
        assert all(not row['remaining_group_members'] for row in result['epochs'])
        assert result['epochs'][-1]['result']['physical_task_proof']
        evidence.update(status='pass',result=result)
    except BaseException as error:
        evidence.update(status='failed',error=repr(error))
        current=status()
        if current and 'stop' in current['allowed_actions']:
            try: action('stop',current['epoch'])
            except Exception as stop_error: evidence['stop_error']=repr(stop_error)
    write_json(output,evidence)
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    evidence=run(args.directory,args.output)
    print(json.dumps(dict(status=evidence['status'],error=evidence.get('error'))))
    raise SystemExit(0 if evidence['status']=='pass' else 1)
