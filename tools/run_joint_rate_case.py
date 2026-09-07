"""One owned formal flight plus the public rate driver; repeat for a cohort."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_runtime.evidence import write_json,group_members
from Simulator.wksim_runtime.joint_actions import submit
from tools.validate_joint_rate import run as drive


def run(output,mode,rate,cpu_timing=False):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    runs=Path(tempfile.mkdtemp(prefix='wksim-rate-case-',dir='/root'))
    run_id='rate-case-'+uuid.uuid4().hex[:10];directory=runs/run_id
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,runtime_profile='joint_quad_dds_v1',
                requested_rate=rate,task_dwell_seconds=dict(hold=35,waypoint=35))
    write_json(output/'config.json',config)
    command=['bash',str(ROOT/'tools/run-wksim.sh'),str(output/'config.json'),'--output-root',str(runs)]
    report=dict(status='failed',command=command,config=config,mode=mode,cpu_timing=cpu_timing,started_unix_s=time.time())
    manager=None
    try:
        with (output/'service.log').open('w') as log:
            manager=subprocess.Popen(command,cwd=ROOT,env=dict(os.environ,WKSIM_JOINT_CPU_TIMING='1' if cpu_timing else '0'),
                                     stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            report['manager_pid']=manager.pid;deadline=time.monotonic()+180
            while not (directory/'status.json').is_file():
                if manager.poll() is not None:raise RuntimeError('Manager exited during startup')
                if time.monotonic()>deadline:raise TimeoutError('Joint status startup')
                time.sleep(.05)
            report['driver']=drive(directory,output/'driver.json',mode)
            manager.wait(timeout=35)
        result=json.loads((directory/'result.json').read_text());report['result']=result
        report['manager_code']=manager.returncode;report['manager_group']=group_members(manager.pid)
        assert manager.returncode==0 and result['status']=='pass' and not report['manager_group']
        assert all(not e['remaining_group_members'] for e in result['epochs'])
        report['status']='behavior_pass'
    except BaseException as error:report['error']=repr(error)
    finally:
        if manager is not None and manager.poll() is None:
            try:
                state=json.loads((directory/'status.json').read_text())
                if 'stop' in state['allowed_actions']:report['cleanup_stop']=submit(directory,'stop',state['epoch'])
                manager.wait(timeout=35)
            except Exception as error:report['cleanup_error']=repr(error)
        if manager is not None:report['final_manager_code']=manager.poll()
        if directory.is_dir():shutil.copytree(directory,output/'run')
        report['finished_unix_s']=time.time();write_json(output/'report.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=('steady','steady-one-after-ready','lifecycle','overload','ground-reset'),default='steady')
    p.add_argument('--rate',type=float,choices=(.5,1),default=.5);a=p.parse_args();r=run(a.output,a.mode,a.rate)
    print(json.dumps({k:r.get(k) for k in ('status','error','cleanup_error','final_manager_code')}))
    raise SystemExit(r['status']!='behavior_pass')
