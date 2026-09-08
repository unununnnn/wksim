"""Formal live joint task -> nonblocking state -> owned Windows UE integration."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_console.visual import View
from Simulator.wksim_console.workspace import wsl_path


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def unc(path):return Path('\\\\wsl.localhost\\Ubuntu-22.04'+str(path).replace('/','\\'))


def run(manifest,output,reconnect_view=False,reset_scene=False,stale_target=None):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    run_id='joint-view-'+uuid.uuid4().hex[:10]
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,runtime_profile='joint_quad_dds_v1',
                requested_rate=.5,task='public_position',task_dwell_seconds=dict(hold=20,waypoint=12),
                display_socket='/tmp/wksim-'+run_id+'/state.sock')
    save(output/'config.json',config)
    wsl=['wsl.exe','-d','Ubuntu-22.04','-u','root','--cd',wsl_path(REPO),'--exec']
    made=subprocess.run([*wsl,'mktemp','-d','/root/wksim-joint-view-XXXXXXXX'],capture_output=True,text=True,check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    runs=made.stdout.strip()
    if not runs.startswith('/root/wksim-joint-view-') or '/' in runs[len('/root/'):]:raise ValueError('Unexpected owned output root')
    directory=runs+'/'+run_id;shared=unc(directory)
    entry=[*wsl,'bash',wsl_path(REPO/'tools/run-wksim.sh'),wsl_path(output/'config.json'),'--output-root',runs]
    command=[*entry,'--use-prepared-run',directory]
    report=dict(status='failed',config=config,command=command,manifest=str(manifest.resolve()),actions=[],views=[],
                started_unix_s=time.time(),runtime_directory=directory,view_reconnect_requested=reconnect_view)
    manager=None;view=None
    def wait(label,predicate,seconds=180):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if manager.poll() is not None:raise RuntimeError(label+': manager exited')
            state=read(shared/'status.json') if (shared/'status.json').is_file() else None
            current=view.poll() if view else None
            if state and state.get('display_stream',{}).get('sent')==0 and state['display_stream'].get('dropped',0)>100:
                report['display_transport_failure']=state
                raise RuntimeError('No successful display sends: '+str(state['display_stream'].get('last_error')))
            if state and state['authority']['phase']=='faulted':raise RuntimeError(label+': '+str(state['authority']))
            if current and current['state'] in ('failed','unavailable'):raise RuntimeError(label+': '+str(current['error']))
            if predicate(state,current):return state,current
            time.sleep(.05)
        raise TimeoutError(label)
    def action(name,epoch,seconds=30):
        script='import json,sys;from pathlib import Path;from Simulator.wksim_runtime.joint_actions import submit;print(json.dumps(submit(Path(sys.argv[1]),sys.argv[2],sys.argv[3])))'
        called=subprocess.run([*wsl,'python3','-B','-c',script,directory,name,epoch],capture_output=True,text=True,
                              timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        if called.returncode:raise RuntimeError(called.stderr)
        request=json.loads(called.stdout);path=request['result_file']
        if not path.startswith(directory+'/action-results/'):raise ValueError('Foreign action result')
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if unc(path).is_file():
                result=read(unc(path))
                if result['state'] in ('completed','failed','rejected'):
                    report['actions'].append(dict(submitted=request,response=result));save(output/'report.json',report)
                    if result['state']!='completed':raise RuntimeError(str(result))
                    return result
            if view:view.poll()
            time.sleep(.05)
        raise TimeoutError(name)
    try:
        prepared=subprocess.run([*entry,'--prepare-run'],capture_output=True,text=True,timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        report['preparation']=dict(command=[*entry,'--prepare-run'],returncode=prepared.returncode,
                                   stdout=prepared.stdout,stderr=prepared.stderr)
        if prepared.returncode:raise RuntimeError('Run preparation failed: '+prepared.stderr)
        preparation=json.loads(prepared.stdout)
        if preparation['status']!='prepared' or preparation['run_dir']!=directory:
            raise ValueError('Unexpected prepared run identity')
        session=read(shared/'session.json');report['session']=session
        if session['instance_id']!=preparation['instance_id']:raise ValueError('Prepared instance differs')
        view=View(output/'view-1',run_id,config['display_socket'],joint_instance=session['instance_id'],build_manifest=manifest)
        view.start()
        deadline=time.monotonic()+90
        while True:
            current=view.poll()
            if current['state'] in ('failed','unavailable'):raise RuntimeError(current['error'])
            if current['transport_ready']:break
            if time.monotonic()>deadline:raise TimeoutError('Display initialization before explicit execution')
            time.sleep(.05)
        report['view_prepared_before_execution']=dict(observed_unix_s=time.time(),view=current)
        with (output/'service.log').open('w',encoding='utf-8') as log:
            manager=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            report['manager_pid']=manager.pid
            state,_=wait('ground and actual joint view ready',lambda s,v:s and 'start-task' in s['allowed_actions'] and v and v['state']=='live')
            epoch=state['epoch'];report['epoch']=epoch
            action('start-task',epoch)
            state,current=wait('dual airborne settled display',lambda s,v:s and 'pause' in s['allowed_actions'] and v and v['state']=='live'
                and all(item['state']['armed'] and item['state']['position'][2]>2.5 for item in s['participants'].values()))
            report['airborne_actor']=current['latest_actor']
            if stale_target:
                from tools.validate_joint_stale import observe_stall
                observe_stall(wsl, shared, state, view, manager, report, output, stale_target)
                action('stop',epoch)
                manager.wait(timeout=30)
                result=read(shared/'result.json')
                assert manager.returncode==0 and result['status']=='stopped' and all(not item['remaining_group_members'] for item in result['epochs'])
                report.update(status='pass',result=result,manager_returncode=manager.returncode)
                return report
            report['camera_selections']=[]
            for target in (2,1):
                selected=view.select_vehicle(target)
                _,current=wait('actual selected Actor',lambda s,v:v and v['state']=='live'
                    and v['latest_actor']['ack']['selected_vehicle_id']==target)
                selected['actor']=current['latest_actor'];report['camera_selections'].append(selected)
            paused=action('pause',epoch);tick=paused['authority']['tick']
            _,current=wait('paused Actor boundary',lambda s,v:v and v['state']=='live'
                and v['latest_actor']['ack']['step']==tick)
            first=current['latest_actor'];began=time.monotonic()
            while time.monotonic()-began<4:
                state,current=wait('paused state remains current',lambda s,v:s and v and v['state']=='live',5)
                assert state['authority']['tick']==tick and current['latest_actor']['ack']['step']==tick
                assert [v['rotor_yaw_deg'] for v in current['latest_actor']['ack']['vehicles']]==[v['rotor_yaw_deg'] for v in first['ack']['vehicles']]
                time.sleep(.05)
            report['pause']=dict(first=first,last=current['latest_actor'],wall_seconds=time.monotonic()-began)
            stepped=action('step',epoch);assert stepped['authority']['tick']==tick+4
            _,current=wait('four-tick Actor step',lambda s,v:v and v['state']=='live' and v['latest_actor']['ack']['step']==tick+4)
            report['stepped_actor']=current['latest_actor']
            action('resume',epoch)
            state,_=wait('native resume and continuing shared clock',lambda s,v:s and s['authority']['tick']>tick+4 and 'pause' in s['allowed_actions'])
            if reconnect_view:
                before=state['authority']['tick'];report['views'].append(view.stop());view=None
                time.sleep(3)
                state,_=wait('physics continued without view',lambda s,v:s and s['authority']['tick']>=before+1000)
                report['view_outage']=dict(before_tick=before,after_tick=state['authority']['tick'])
                view=View(output/'view-2',run_id,config['display_socket'],joint_instance=session['instance_id'],build_manifest=manifest)
                view.start()
                wait('fresh view reconnected',lambda s,v:v and v['state']=='live')
            state,current=wait('public tasks landed',lambda s,v:s and s['task_state']=='completed',300)
            assert all(not item['state']['armed'] for item in state['participants'].values())
            report['final_actor']=current['latest_actor']
            if reset_scene:
                old_generation=current['latest_actor']['ack']['generation']
                reset=action('cold-reset',epoch,180)
                state,current=wait('new epoch ground display after scene reset',lambda s,v:
                    s and s['epoch']!=epoch and 'start-task' in s['allowed_actions']
                    and v and v['state']=='live' and v['latest_actor']['ack']['epoch']==s['epoch']
                    and v['latest_actor']['ack']['generation']==old_generation+1
                    and len(v['latest_actor']['ack']['vehicles'])==2
                    and all(not item['stale'] for item in v['latest_actor']['ack']['observed_vehicles']),180)
                assert reset['new_epoch']==state['epoch'] and state['task_state']=='idle'
                report['scene_reset']=dict(old_epoch=epoch,new_epoch=state['epoch'],old_generation=old_generation,
                                           new_actor=current['latest_actor'],
                                           isolation='new epoch/generation accepted only with both vehicles fresh; old-generation datagrams rejected by the validated receiver (LatestJointState)')
                epoch=state['epoch']
            action('stop',epoch)
            manager.wait(timeout=30);report['manager_returncode']=manager.returncode
        result=read(shared/'result.json')
        assert manager.returncode==0 and result['status']=='pass' and all(not item['remaining_group_members'] for item in result['epochs'])
        report.update(status='pass',result=result)
    except BaseException as error:
        report['error']=repr(error)
        try:
            if manager is not None and manager.poll() is None and (shared/'status.json').is_file():
                state=read(shared/'status.json')
                if 'stop' in state['allowed_actions']:action('stop',state['epoch'])
                manager.wait(timeout=30)
        except Exception as error:report['cleanup_error']=repr(error)
    finally:
        if view:report['views'].append(view.stop())
        if manager is not None and manager.poll() is None:
            report['cleanup_incomplete']=True
        if shared.is_dir():
            try:
                # Linux resolves PX4's runtime links in their actual filesystem;
                # Windows UNC traversal cannot reliably follow these links.
                copied=subprocess.run([*wsl,'python3','-B','-c',
                    'import shutil,sys;shutil.copytree(sys.argv[1],sys.argv[2])',directory,wsl_path(output/'run')],
                    capture_output=True,text=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
                if copied.returncode:raise RuntimeError(copied.stderr)
            except Exception as error:
                report.update(status='failed',retention_error=repr(error))
        report['finished_unix_s']=time.time();save(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--reconnect-view',action='store_true',help='Also restart the entire UE process while airborne; record host resource failures')
    parser.add_argument('--reset-scene',action='store_true',help='Also cold-reset the scene after landing and verify old-generation display isolation')
    args=parser.parse_args();result=run(args.manifest,args.output,args.reconnect_view,args.reset_scene)
    print(json.dumps({key:result.get(key) for key in ('status','error','cleanup_error','cleanup_incomplete')}))
    raise SystemExit(0 if result['status']=='pass' else 1)
