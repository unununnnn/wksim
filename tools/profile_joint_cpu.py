"""Bounded formal dual-FC ground measurement; no flight or rate acceptance claim."""
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
from Simulator.wksim_runtime.joint_actions import submit
from Simulator.wksim_runtime.evidence import write_json,group_members


def run(output,rate,seconds,samples):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    runs=Path(tempfile.mkdtemp(prefix='wksim-cpu-profile-',dir='/root'))
    run_id='cpu-profile-'+uuid.uuid4().hex[:10];directory=runs/run_id
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,runtime_profile='joint_quad_dds_v1',requested_rate=rate)
    write_json(output/'config.json',config)
    command=['bash',str(ROOT/'tools/run-wksim.sh'),str(output/'config.json'),'--output-root',str(runs)]
    report=dict(status='failed',scope=__doc__,command=command,samples=samples,requested_observation_seconds=seconds,
                started_unix_s=time.time(),host_uptime=Path('/proc/uptime').read_text(),
                schedstats_enabled=Path('/proc/sys/kernel/sched_schedstats').read_text().strip())
    environment=dict(os.environ,WKSIM_JOINT_CPU_TIMING='1' if samples else '0')
    manager=None
    def read_status():return json.loads((directory/'status.json').read_text())
    def stop():
        state=read_status();request=submit(directory,'stop',state['epoch']);report['stop_request']=request
        manager.wait(timeout=35)
    try:
        with (output/'service.log').open('w') as log:
            manager=subprocess.Popen(command,cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            report['manager_pid']=manager.pid;deadline=time.monotonic()+180;began=None
            while manager.poll() is None:
                if (directory/'status.json').is_file():
                    state=read_status()
                    if state['authority']['tick'] and began is None:began=time.monotonic()
                    if state['authority']['phase']=='faulted' or began is not None and time.monotonic()-began>=seconds:
                        report['last_observation']=state;break
                if time.monotonic()>deadline:raise TimeoutError('Formal ground observation')
                time.sleep(.05)
            if manager.poll() is None:stop()
        result=json.loads((directory/'result.json').read_text());report['result']=result
        report['returncode']=manager.returncode
        report['remaining_manager_group']=group_members(manager.pid)
        assert manager.returncode==0 and result['status']=='stopped' and not report['remaining_manager_group']
        assert all(not e['remaining_group_members'] for e in result['epochs'])
        assert report['last_observation']['authority']['tick']>0
        report['status']='measurement_retired'
    except BaseException as error:report['error']=repr(error)
    finally:
        if manager is not None and manager.poll() is None:
            try:stop()
            except Exception as error:report['cleanup_error']=repr(error)
        if manager is not None:report['final_manager_code']=manager.poll()
        if directory.is_dir():shutil.copytree(directory,output/'run')
        report['finished_unix_s']=time.time();write_json(output/'report.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rate',type=float,choices=(.5,1),default=1);p.add_argument('--seconds',type=float,default=20)
    p.add_argument('--cpu-samples',action='store_true');a=p.parse_args()
    if not 1<=a.seconds<=60:p.error('seconds must be 1..60')
    r=run(a.output,a.rate,a.seconds,a.cpu_samples)
    print(json.dumps({k:r.get(k) for k in ('status','error','cleanup_error','last_observation')}))
    raise SystemExit(r['status']!='measurement_retired')
