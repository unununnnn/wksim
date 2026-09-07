"""Drive only the formal joint action API; independent model and process audit."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.evidence import write_json


def run(directory,output):
    evidence=dict(directory=str(directory),actions=[],observations=[])
    def status():
        path=directory/'status.json'
        return json.loads(path.read_text()) if path.is_file() else None
    def wait(label,predicate,seconds=180):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=status()
            if value and value['phase']=='failed':
                detail=json.loads((Path(value['epoch_dir'])/'result.json').read_text())
                raise RuntimeError(label+': '+str(detail.get('error')))
            if value and predicate(value): return value
            time.sleep(.05)
        raise TimeoutError(label)
    def action(name,epoch):
        command=[sys.executable,'-B','-m','Simulator.wksim_runtime.joint_actions',str(directory),name,'--epoch',epoch]
        submitted=json.loads(subprocess.check_output(command,cwd=REPO,text=True))
        target=Path(submitted['result_file'])
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if target.is_file():
                response=json.loads(target.read_text())
                if response['state']=='completed':
                    evidence['actions'].append(dict(command=command,submitted=submitted,response=response))
                    return response
                if response['state'] in ('failed','rejected'): raise RuntimeError(str(response))
            time.sleep(.02)
        raise TimeoutError('Action did not complete: '+name)
    def models(value):
        found={}
        for stack in ('arducopter','px4'):
            path=Path(value['epoch_dir'])/(stack+'-truth.jsonl')
            with path.open('rb') as stream:
                stream.seek(0,2);length=stream.tell();stream.seek(max(0,length-65536))
                lines=stream.read().splitlines()
            found[stack]=json.loads(lines[-1])
        return found
    try:
        ready=wait('native ground ready',lambda value:'start-task' in value['allowed_actions'])
        epoch=ready['epoch']
        action('start-task',epoch)
        airborne=wait('actual airborne pause offer',lambda value:'pause' in value['allowed_actions']
            and all(peer['state']['armed'] and peer['state']['position'][2]>2.5 for peer in value['participants'].values()))
        first=action('pause',epoch)
        frozen=status();before=models(frozen)
        assert all(-row['state'][8]>2.5 for row in before.values())
        time.sleep(4)
        after=models(status())
        assert before==after and status()['authority']['tick']==frozen['authority']['tick']
        evidence['observations'].append(dict(kind='pause',tick=frozen['authority']['tick'],models=before,wall_seconds=4))
        step=action('step',epoch)
        stepped=wait('step pause acknowledgements',lambda value:'resume' in value['allowed_actions']
                     and value['authority']['tick']==step['authority']['tick'])
        assert stepped['authority']['tick']==frozen['authority']['tick']+4
        step_models=models(stepped)
        assert all(row['tick']==stepped['authority']['tick'] for row in step_models.values())
        time.sleep(4)
        assert models(status())==step_models
        action('resume',epoch)
        wait('public tasks completed',lambda value:value['task_state']=='completed')
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
        raise
    finally:
        write_json(output,evidence)
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps({key:value for key,value in run(args.directory,args.output).items() if key not in ('result','observations','actions')}))
