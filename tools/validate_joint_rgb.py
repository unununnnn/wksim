"""Real dual-FC ground simulation -> native RGB -> optional consumer outage.

Ground sensor integration only: no flight, calibration or collision acceptance.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_console.visual import View
from Simulator.wksim_console.workspace import wsl_path
from Simulator.ue55.rgb import Reader
from tools.validate_joint_visual import unc,read,save


def run(manifest,output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    run_id='joint-rgb-'+uuid.uuid4().hex[:10]
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,runtime_profile='joint_quad_dds_v1',
                requested_rate=.5,task='public_position',display_socket='/tmp/wksim-'+run_id+'/state.sock')
    save(output/'config.json',config)
    wsl=['wsl.exe','-d','Ubuntu-22.04','-u','root','--cd',wsl_path(REPO),'--exec']
    made=subprocess.run([*wsl,'mktemp','-d','/root/wksim-joint-rgb-XXXXXXXX'],capture_output=True,text=True,check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    runs=made.stdout.strip()
    if not runs.startswith('/root/wksim-joint-rgb-') or '/' in runs[len('/root/'):]:raise ValueError('Unexpected output root')
    directory=runs+'/'+run_id;shared=unc(directory)
    entry=[*wsl,'bash',wsl_path(REPO/'tools/run-wksim.sh'),wsl_path(output/'config.json'),'--output-root',runs]
    report=dict(status='failed',scope=__doc__,runtime_directory=directory,config=config,manifest=str(manifest),frames=[],
                started_unix_s=time.time())
    manager=None;view=None;reader=None
    def action(name):
        state=read(shared/'status.json')
        script='import json,sys;from pathlib import Path;from Simulator.wksim_runtime.joint_actions import submit;print(json.dumps(submit(Path(sys.argv[1]),sys.argv[2],sys.argv[3])))'
        called=subprocess.run([*wsl,'python3','-B','-c',script,directory,name,state['epoch']],capture_output=True,text=True,
                              timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        if called.returncode:raise RuntimeError(called.stderr)
        request=json.loads(called.stdout)
        if not request['result_file'].startswith(directory+'/action-results/'):raise ValueError('Foreign action result')
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            path=unc(request['result_file'])
            if path.is_file():
                result=read(path)
                if result['state'] in ('completed','failed','rejected'):
                    report.setdefault('actions',[]).append(dict(request=request,result=result))
                    if result['state']!='completed':raise RuntimeError(str(result))
                    return result
            time.sleep(.1)
        raise TimeoutError(name)
    def sample():
        if manager.poll() is not None:raise RuntimeError('Manager exited')
        state=read(shared/'status.json') if (shared/'status.json').is_file() else None
        current=view.poll()
        if current['state'] in ('failed','unavailable'):raise RuntimeError(current['error'])
        if state:
            if state.get('display_stream',{}).get('sent')==0 and state.get('display_stream',{}).get('dropped',0)>100:
                raise RuntimeError('Display transport unavailable: '+str(state['display_stream'].get('last_error')))
            if state['authority']['phase']=='faulted':raise RuntimeError(str(state['authority']))
            if reader:
                reader.set_epoch(state['epoch'],state['generation'])
                report['frames'].extend(reader.poll())
        return state
    try:
        prepared=subprocess.run([*entry,'--prepare-run'],capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        report['preparation']=dict(command=[*entry,'--prepare-run'],returncode=prepared.returncode,stdout=prepared.stdout,stderr=prepared.stderr)
        if prepared.returncode:raise RuntimeError('Preparation failed: '+prepared.stderr)
        session=read(shared/'session.json');report['session']=session
        settings=dict(version=1,vehicle_id=2,sensor_id='front_rgb',width=640,height=480,horizontal_fov_degrees=90,
                      position_cm=[30,0,50],quaternion_xyzw=[0,0,0,1],interval_steps=100,notify_port=19072)
        view=View(output/'view',run_id,config['display_socket'],joint_instance=session['instance_id'],build_manifest=manifest,rgb_config=settings)
        reader=Reader(view.rgb_directory,run_id,session['instance_id'],settings)
        view.start();deadline=time.monotonic()+90
        while not view.poll()['transport_ready']:
            current=view.poll()
            if current['state'] in ('failed','unavailable'):raise RuntimeError(current['error'])
            if time.monotonic()>deadline:raise TimeoutError('UE preparation')
            time.sleep(.1)
        command=[*entry,'--use-prepared-run',directory];report['command']=command
        with (output/'service.log').open('w') as log:
            manager=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            report['manager_pid']=manager.pid;deadline=time.monotonic()+180
            while len(report['frames'])<10:
                state=sample()
                if time.monotonic()>deadline:raise TimeoutError('Ten real RGB frames')
                time.sleep(.1)
            before=dict(tick=state['authority']['tick'],last_frame=report['frames'][-1],wall=time.time())
            reader.close();reader=None;began=time.monotonic()
            while time.monotonic()-began<3:
                state=sample();time.sleep(.1)
            report['consumer_outage']=dict(before=before,after_tick=state['authority']['tick'],wall_seconds=time.monotonic()-began)
            assert state['authority']['tick']>=before['tick']+1000
            count=len(report['frames']);resume_tick=state['authority']['tick']
            reader=Reader(view.rgb_directory,run_id,session['instance_id'],settings)
            deadline=time.monotonic()+20
            while len(report['frames'])<count+5:
                state=sample()
                if time.monotonic()>deadline:raise TimeoutError('Fresh RGB consumer reconnect')
                time.sleep(.1)
            assert int(report['frames'][count]['metadata']['step'])>=resume_tick
            report['consumer_reconnect']=dict(start_tick=resume_tick,first_frame=report['frames'][count],rejected=reader.rejected)
            assert all(not row['state']['armed'] for row in state['participants'].values())
            action('stop');manager.wait(timeout=30)
        result=read(shared/'result.json')
        assert manager.returncode==0 and result['status']=='stopped'
        assert all(not epoch['remaining_group_members'] for epoch in result['epochs'])
        report.update(status='pass',result=result,manager_returncode=manager.returncode)
    except BaseException as error:
        report['error']=repr(error)
    finally:
        if manager is not None and manager.poll() is None:
            try:action('stop');manager.wait(timeout=30)
            except Exception as error:report['cleanup_error']=repr(error)
        if reader:reader.close()
        if view:report['view_final']=view.stop()
        if manager is not None:report['manager_returncode']=manager.poll()
        if shared.is_dir():
            copied=subprocess.run([*wsl,'python3','-B','-c','import shutil,sys;shutil.copytree(sys.argv[1],sys.argv[2])',
                                   directory,wsl_path(output/'run')],capture_output=True,text=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
            if copied.returncode:report.update(status='failed',retention_error=copied.stderr)
        report['finished_unix_s']=time.time();save(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();result=run(args.manifest,args.output)
    print(json.dumps({k:result.get(k) for k in ('status','error','cleanup_error','manager_returncode')}))
    raise SystemExit(result['status']!='pass')
