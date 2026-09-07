"""Formal action API, actual owned Agent loss, and cold-reset epoch isolation."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_runtime.evidence import write_json,json_identity,group_members


def models(directory):
    result={}
    for stack in ('arducopter','px4'):
        with (directory/(stack+'-truth.jsonl')).open('rb') as stream:
            stream.seek(0,2);stream.seek(max(0,stream.tell()-65536))
            result[stack]=json.loads(stream.read().splitlines()[-1])
    return result


def run(directory,output,affected='px4'):
    evidence=dict(directory=str(directory),affected=affected,actions=[])
    def status():
        path=directory/'status.json'
        return json.loads(path.read_text()) if path.is_file() else None
    def wait(label,predicate,seconds=180):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=status()
            if value and value['phase']=='failed':
                raise RuntimeError(label+': '+str(json.loads((Path(value['epoch_dir'])/'result.json').read_text()).get('error')))
            if value and predicate(value):return value
            time.sleep(.05)
        raise TimeoutError(label)
    def action(name,epoch,timeout=20):
        command=[sys.executable,'-B','-m','Simulator.wksim_runtime.joint_actions',str(directory),name,'--epoch',epoch]
        submitted=json.loads(subprocess.check_output(command,cwd=REPO,text=True))
        target=Path(submitted['result_file'])
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if target.is_file():
                response=json.loads(target.read_text())
                if response['state']=='completed':
                    evidence['actions'].append(dict(command=command,submitted=submitted,response=response))
                    return response
                if response['state'] in ('failed','rejected'):raise RuntimeError(str(response))
            time.sleep(.02)
        raise TimeoutError(name+' action did not complete')
    try:
        ready=wait('initial native ready',lambda value:'start-task' in value['allowed_actions'])
        epoch=ready['epoch'];epoch_dir=Path(ready['epoch_dir'])
        action('start-task',epoch)
        flying=wait('both actual task owners airborne',lambda value:'pause' in value['allowed_actions']
            and all(peer['state']['position'][2]>2.5 for peer in value['participants'].values()))
        children=json.loads((epoch_dir/'children.json').read_text())
        agent=children[affected+'-agent']
        current=json_identity(agent['identity']['pid'])
        assert current is not None and all(current[key]==agent['identity'][key] for key in ('pid','pgid','start_ticks'))
        assert (Path('/proc')/str(current['pid'])/'exe').resolve()==Path(agent['argv'][0]).resolve()
        evidence['injected_agent']=dict(identity=current,executable=str(Path(agent['argv'][0]).resolve()))
        os.kill(current['pid'],signal.SIGTERM)
        failed=wait('fault and original task retirement',lambda value:value['authority']['phase']=='faulted'
                    and 'recover' in value['allowed_actions'],15)
        tick=failed['authority']['tick']
        before_models=models(epoch_dir);freeze_started=time.monotonic()
        assert all(-row['state'][8]>2.5 and row['tick']==tick for row in before_models.values())
        time.sleep(4)
        after_models=models(epoch_dir)
        assert status()['authority']['tick']==tick and before_models==after_models
        evidence['frozen_tick']=tick
        evidence['freeze']=dict(before=before_models,after=after_models,wall_seconds=time.monotonic()-freeze_started)
        action('recover',epoch,15)
        wait('explicit new recovery task offer',lambda value:'start-recovery-task' in value['allowed_actions'])
        before=set((epoch_dir/'tasks').iterdir())
        time.sleep(.3)
        assert set((epoch_dir/'tasks').iterdir())==before
        action('start-recovery-task',epoch)
        completed=wait('new public recovery tasks landed',lambda value:value['task_state']=='completed')
        assert all(not peer['state']['armed'] for peer in completed['participants'].values())
        old_namespace=os.readlink(f"/proc/{completed['supervisor']['pid']}/ns/net")
        old_group=completed['supervisor']['pgid']
        reset=action('cold-reset',epoch,180)
        new=wait('new epoch ready without a replayed task',lambda value:value['epoch']!=epoch
                 and 'start-task' in value['allowed_actions'])
        assert reset['new_epoch']==new['epoch'] and new['task_state']=='idle'
        new_namespace=os.readlink(f"/proc/{new['supervisor']['pid']}/ns/net")
        assert old_namespace!=new_namespace and not group_members(old_group)
        assert all(not peer['state']['armed'] for peer in new['participants'].values())
        retired=dict(evidence['actions'][0]['submitted']['request'],token=uuid.uuid4().hex)
        path=directory/'actions'/f"{retired['command_id']:020d}-{retired['token']}.json"
        write_json(path,retired)
        rejection=directory/'action-results'/new['epoch']/('rejected-'+path.name)
        deadline=time.monotonic()+5
        while not rejection.is_file() and time.monotonic()<deadline:time.sleep(.02)
        assert json.loads(rejection.read_text())['state']=='rejected'
        assert status()['task_state']=='idle'
        evidence['reset']=dict(old_epoch=epoch,new_epoch=new['epoch'],old_namespace=old_namespace,
                               new_namespace=new_namespace,retired_request_rejection=json.loads(rejection.read_text()))
        action('stop',new['epoch'])
        deadline=time.monotonic()+20
        while not (directory/'result.json').is_file() and time.monotonic()<deadline:time.sleep(.02)
        result=json.loads((directory/'result.json').read_text())
        assert result['epochs'][0]['result']['physical_task_proof']
        assert all(not item['remaining_group_members'] for item in result['epochs'])
        evidence.update(status='pass',result=result)
    except BaseException as error:
        evidence.update(status='failed',error=repr(error))
        current=status()
        if current and 'stop' in current['allowed_actions']:
            try: action('stop',current['epoch'])
            except Exception as stop_error:evidence['stop_error']=repr(stop_error)
        raise
    finally:
        write_json(output,evidence)
    return evidence
