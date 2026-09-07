"""Real dual-FC ground simulation -> native RGB -> optional consumer outage.

Ground sensor integration only: no flight, calibration or collision acceptance.
"""
import argparse
import hashlib
import json
import math
import os
import socket
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from Simulator.wksim_console.visual import View
from Simulator.wksim_console.workspace import wsl_path
from Simulator.ue55.rgb import Reader
from tools.validate_joint_visual import unc,read,save


def run(manifest,output,fixture_case=None,lifecycle=False,airborne=False):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    names=['tools/validate_joint_rgb.py','Simulator/ue55/rgb.py','Simulator/ue55/state_relay.py',
           'Simulator/ue55/product_bridge.py','Simulator/wksim_console/visual.py']
    names += [str(p.relative_to(REPO)).replace('\\','/') for p in (REPO/'Simulator/ue55/Source/WksimVisual').glob('*') if p.suffix in ('.cpp','.h','.cs')]
    implementation=dict(captured_unix_s=time.time(),scope='Source bytes captured before launching the owned run',sha256={})
    for name in names:
        data=(REPO/name).read_bytes();target=output/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        implementation['sha256'][name]=hashlib.sha256(data).hexdigest()
    save(output/'implementation.json',implementation)
    if fixture_case is not None:
        contract=REPO/'docs/rgb-geometry-fixture.md'
        save(output/'geometry-conditions.json',dict(document=str(contract),sha256=hashlib.sha256(contract.read_bytes()).hexdigest(),
             edge_pixels=2,coverage=.995,minimum_core_pixels=500,declared_before_run=True))
    run_id='joint-rgb-'+uuid.uuid4().hex[:10]
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,runtime_profile='joint_quad_dds_v1',
                requested_rate=.5,task='public_position',display_socket='/tmp/wksim-'+run_id+'/state.sock')
    if airborne:config['task_dwell_seconds']=dict(hold=12,waypoint=8)
    save(output/'config.json',config)
    wsl=['wsl.exe','-d','Ubuntu-22.04','-u','root','--cd',wsl_path(REPO),'--exec']
    made=subprocess.run([*wsl,'mktemp','-d','/root/wksim-joint-rgb-XXXXXXXX'],capture_output=True,text=True,check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    runs=made.stdout.strip()
    if not runs.startswith('/root/wksim-joint-rgb-') or '/' in runs[len('/root/'):]:raise ValueError('Unexpected output root')
    directory=runs+'/'+run_id;shared=unc(directory)
    entry=[*wsl,'bash',wsl_path(REPO/'tools/run-wksim.sh'),wsl_path(output/'config.json'),'--output-root',runs]
    report=dict(status='failed',scope=__doc__,runtime_directory=directory,config=config,manifest=str(manifest),frames=[],
                started_unix_s=time.time(),fixture_case=fixture_case,lifecycle_requested=lifecycle,airborne_requested=airborne)
    manager=None;view=None;reader=None
    def action(name):
        state=read(shared/'status.json')
        script='import json,sys;from pathlib import Path;from Simulator.wksim_runtime.joint_actions import submit;print(json.dumps(submit(Path(sys.argv[1]),sys.argv[2],sys.argv[3])))'
        called=subprocess.run([*wsl,'python3','-B','-c',script,directory,name,state['epoch']],capture_output=True,text=True,
                              timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        if called.returncode:raise RuntimeError(called.stderr)
        request=json.loads(called.stdout)
        if not request['result_file'].startswith(directory+'/action-results/'):raise ValueError('Foreign action result')
        deadline=time.monotonic()+(180 if name=='cold-reset' else 30)
        while time.monotonic()<deadline:
            path=unc(request['result_file'])
            if path.is_file():
                result=read(path)
                if result['state'] in ('completed','failed','rejected'):
                    report.setdefault('actions',[]).append(dict(request=request,result=result))
                    if result['state']!='completed':raise RuntimeError(str(result))
                    return result
            if view:view.poll()
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
                reader.set_epoch(state['epoch'],state['generation'],minimum_step=state['authority']['tick'])
                report['frames'].extend(reader.poll())
        return state
    try:
        prepared=subprocess.run([*entry,'--prepare-run'],capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        report['preparation']=dict(command=[*entry,'--prepare-run'],returncode=prepared.returncode,stdout=prepared.stdout,stderr=prepared.stderr)
        if prepared.returncode:raise RuntimeError('Preparation failed: '+prepared.stderr)
        session=read(shared/'session.json');report['session']=session
        settings=dict(version=1,vehicle_id=2,sensor_id='front_rgb',width=640,height=480,horizontal_fov_degrees=90,
                      position_cm=[30,0,50],quaternion_xyzw=[0,0,0,1],interval_steps=100,notify_port=19072)
        if fixture_case is not None:
            settings['position_cm']=[30,80,120] if fixture_case==1 else [30,0,100]
            if fixture_case==3:settings['quaternion_xyzw']=[0,0,math.sin(math.radians(10)),math.cos(math.radians(10))]
        view=View(output/'view',run_id,config['display_socket'],joint_instance=session['instance_id'],build_manifest=manifest,
                  rgb_config=settings,rgb_fixture_case=fixture_case)
        reader=Reader(view.rgb_directory,run_id,session['instance_id'],settings,stream_id=view.rgb_stream_id)
        report['producer_streams']=[view.rgb_stream_id]
        view.start();deadline=time.monotonic()+90
        while not view.poll()['transport_ready']:
            current=view.poll()
            if current['state'] in ('failed','unavailable'):raise RuntimeError(current['error'])
            if time.monotonic()>deadline:raise TimeoutError('UE preparation')
            time.sleep(.1)
        # Read only our already-running UE module, before starting physics.
        module_script='''$ueModulePid=[int]$env:WKSIM_RGB_UE_PID
(Get-Process -Id $ueModulePid).Modules | Where-Object { $_.ModuleName -eq 'UnrealEditor-WksimVisual.dll' } | ForEach-Object {
 [pscustomobject]@{path=$_.FileName;sha256=(Get-FileHash -LiteralPath $_.FileName -Algorithm SHA256).Hash;pid=$ueModulePid}
} | ConvertTo-Json -Compress'''
        if fixture_case is not None:
            native=read(Path(view.poll()['rgb_fixture_manifest']))
            loaded=dict(path=native['module_path'],pid=native['process_id'],
                        sha256=hashlib.sha256(Path(native['module_path']).read_bytes()).hexdigest(),
                        mechanism='GetModuleHandleExW FROM_ADDRESS + GetModuleFileNameW inside actual fixture module')
        else:
            module_result=subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive',
                                          '-Command',module_script],capture_output=True,text=True,timeout=20,
                                         env=dict(os.environ,WKSIM_RGB_UE_PID=str(view.poll()['pids']['ue'])),creationflags=subprocess.CREATE_NO_WINDOW)
            save(output/'module-probe.json',dict(returncode=module_result.returncode,stdout=module_result.stdout,stderr=module_result.stderr))
            if module_result.returncode or not module_result.stdout.strip():raise RuntimeError('UE module probe returned no result: '+module_result.stderr)
            loaded=json.loads(module_result.stdout)
        build=read(manifest)
        assert loaded['pid']==view.poll()['pids']['ue'] and Path(loaded['path']).resolve()==Path(build['binary']).resolve()
        assert loaded['sha256'].lower()==build['binary_sha256']
        save(output/'ue-loaded-module.json',loaded)
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
            reader=Reader(view.rgb_directory,run_id,session['instance_id'],settings,stream_id=view.rgb_stream_id)
            deadline=time.monotonic()+20
            while len(report['frames'])<count+5:
                state=sample()
                if time.monotonic()>deadline:raise TimeoutError('Fresh RGB consumer reconnect')
                time.sleep(.1)
            assert int(report['frames'][count]['metadata']['step'])>=resume_tick
            report['consumer_reconnect']=dict(start_tick=resume_tick,first_frame=report['frames'][count],rejected=reader.rejected)
            if lifecycle:
                record=dict(before_epoch=state['epoch'],before_generation=state['generation'],
                            old_notification=report['frames'][-1]['notification'])
                record['disable']=view.set_rgb_enabled(False)
                record['queued_before_disable']=reader.poll()
                stopped_at=state['authority']['tick'];count=len(report['frames']);began=time.monotonic()
                while time.monotonic()-began<3:
                    state=sample();time.sleep(.1)
                assert len(report['frames'])==count, 'Disabled producer delivered a new frame'
                assert state['authority']['tick']>=stopped_at+1000, 'Physics stalled with producer disabled'
                record['disabled_window']=dict(start_tick=stopped_at,end_tick=state['authority']['tick'],wall_seconds=time.monotonic()-began)
                reader.close();reader=None
                record['enable']=view.set_rgb_enabled(True)
                report['producer_streams'].append(view.rgb_stream_id)
                reader=Reader(view.rgb_directory,run_id,session['instance_id'],settings,stream_id=view.rgb_stream_id)
                reader.set_epoch(state['epoch'],state['generation'],minimum_step=state['authority']['tick'])
                rejected=reader.rejected
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as negative:
                    negative.sendto(json.dumps(record['old_notification']).encode(),('127.0.0.1',settings['notify_port']))
                deadline=time.monotonic()+20
                while len(report['frames'])<count+5:
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('Restarted producer actual frames')
                    time.sleep(.1)
                assert reader.rejected>rejected, 'Retired producer notification was not rejected'
                record['restarted_first_frame']=report['frames'][count]
                record['old_producer_rejections']=reader.rejected-rejected
                record['before_reset_notification']=report['frames'][-1]['notification']
                old_epoch=state['epoch'];count=len(report['frames'])
                record['reset']=action('cold-reset');deadline=time.monotonic()+180
                while True:
                    state=sample()
                    if state and state['epoch']!=old_epoch:break
                    if time.monotonic()>deadline:raise TimeoutError('New physical epoch')
                    time.sleep(.1)
                record['after_epoch']=state['epoch'];record['after_generation']=state['generation']
                rejected=reader.rejected
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as negative:
                    negative.sendto(json.dumps(record['before_reset_notification']).encode(),('127.0.0.1',settings['notify_port']))
                while len(report['frames'])<count+5:
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('New epoch actual camera frames')
                    time.sleep(.1)
                assert reader.rejected>rejected, 'Retired epoch notification was not rejected'
                assert all(f['metadata']['epoch']==state['epoch'] for f in report['frames'][count:])
                record['reset_first_frame']=report['frames'][count]
                record['old_epoch_rejections']=reader.rejected-rejected
                report['rgb_lifecycle']=record
            if airborne:
                deadline=time.monotonic()+240
                while not state or 'start-task' not in state['allowed_actions']:
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('Normal joint preflight readiness')
                    time.sleep(.1)
                action('start-task')
                flight_start=len(report['frames']);observed=[]
                while state['task_state']!='completed':
                    state=sample()
                    if all(p['state']['armed'] and p['state']['position'][2]>2.5 for p in state['participants'].values()):
                        observed.append(dict(epoch=state['epoch'],tick=state['authority']['tick'],
                                             last_frame_index=len(report['frames'])-1))
                    if time.monotonic()>deadline:raise TimeoutError('Public task with live RGB completion')
                    time.sleep(.1)
                assert len(observed)>=5, 'No sustained actual dual-airborne observation'
                report['airborne']=dict(frame_start=flight_start,observations=observed)
            assert all(not row['state']['armed'] for row in state['participants'].values())
            action('stop');manager.wait(timeout=30)
        result=read(shared/'result.json')
        assert manager.returncode==0 and result['status']==('pass' if airborne else 'stopped')
        assert all(not epoch['remaining_group_members'] for epoch in result['epochs'])
        report.update(status='pass',result=result,manager_returncode=manager.returncode)
    except BaseException as error:
        report['error']=repr(error)
        report['traceback']=traceback.format_exc()
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
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--fixture-case',type=int,choices=range(4))
    parser.add_argument('--lifecycle',action='store_true')
    parser.add_argument('--airborne',action='store_true')
    args=parser.parse_args();result=run(args.manifest,args.output,args.fixture_case,args.lifecycle,args.airborne)
    print(json.dumps({k:result.get(k) for k in ('status','error','cleanup_error','manager_returncode')}))
    raise SystemExit(result['status']!='pass')
