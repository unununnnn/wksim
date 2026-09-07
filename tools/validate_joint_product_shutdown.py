"""Stop or interrupt the actual formal service while its read-only preflight runs."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from Simulator.wksim_runtime.evidence import write_json,json_identity,group_members


def run(directory,output,manager,mode):
    result=dict(mode=mode,manager=json_identity(manager.pid),status='failed')
    try:
        deadline=time.monotonic()+20
        path=directory/'status.json'
        while not path.is_file() and time.monotonic()<deadline: time.sleep(.02)
        state=json.loads(path.read_text())
        assert state['phase']=='starting'
        result['initial_status']=state
        started=time.monotonic()
        if mode=='startup-stop':
            command=[sys.executable,'-B','-m','Simulator.wksim_runtime.joint_actions',str(directory),
                     'stop','--epoch',state['epoch']]
            submitted=json.loads(subprocess.check_output(command,text=True))
            result.update(command=command,submitted=submitted)
        else:
            current=json_identity(manager.pid)
            assert all(current[key]==result['manager'][key] for key in ('pid','pgid','start_ticks'))
            result['manager_at_interrupt']=current
            os.kill(manager.pid,signal.SIGTERM)
        manager.wait(timeout=20)
        result['wall_seconds']=time.monotonic()-started
        report=json.loads((directory/'result.json').read_text())
        result['result']=report
        assert report['status']==('stopped' if mode=='startup-stop' else 'failed')
        assert len(report['epochs'])==1 and set(report['epochs'][0]['result']['children'])<={'preflight'}
        assert not group_members(state['supervisor']['pgid'])
        assert not report['epochs'][0]['remaining_group_members']
        if mode=='startup-stop':
            response=json.loads(Path(submitted['result_file']).read_text())
            assert response['state']=='completed'
            result['response']=response
        result['status']='pass'
    except BaseException as error:
        result['error']=repr(error)
        raise
    finally:
        write_json(output,result)
    return result
