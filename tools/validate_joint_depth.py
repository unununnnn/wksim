"""Real public dual-FC flight with optional native depth and truth-bound audit.

Single sensor slice only; optical geometry acceptance is a separate fixture audit.
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
from Simulator.ue55.depth import Reader
from tools.validate_joint_visual import unc,read,save


def observe_module(view, manifest, output, name='ue-loaded-module.json'):
    pid=view.poll()['pids']['ue']
    script='''$p=[int]$env:WKSIM_DEPTH_UE_PID
(Get-Process -Id $p).Modules | Where-Object { $_.ModuleName -eq 'UnrealEditor-WksimVisual.dll' } | ForEach-Object {
 [pscustomobject]@{path=$_.FileName;pid=$p}
} | ConvertTo-Json -Compress'''
    result=subprocess.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive',
        '-Command',script],capture_output=True,text=True,timeout=20,
        env=dict(os.environ,WKSIM_DEPTH_UE_PID=str(pid)),creationflags=subprocess.CREATE_NO_WINDOW)
    save(output/(name+'.probe.json'),dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if result.returncode or not result.stdout.strip():raise RuntimeError('UE module probe failed: '+result.stderr)
    loaded=json.loads(result.stdout);build=read(manifest)
    loaded['sha256']=hashlib.sha256(Path(loaded['path']).read_bytes()).hexdigest()
    assert loaded['pid']==pid and Path(loaded['path']).resolve()==Path(build['binary']).resolve()
    assert loaded['sha256']==build['binary_sha256']
    save(output/name,loaded)
    return loaded


def run(manifest,output,lifecycle=False):
    airborne=not lifecycle
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    names=['tools/validate_joint_depth.py','Simulator/ue55/depth.py','Simulator/ue55/rgb.py','Simulator/ue55/state_relay.py',
           'Simulator/ue55/product_bridge.py','Simulator/wksim_console/visual.py',
           'tools/audit_joint_rgb.py','tools/validate_joint_visual.py']
    names += [str(p.relative_to(REPO)).replace('\\','/') for p in (REPO/'Simulator/ue55/Source/WksimVisual').glob('*') if p.suffix in ('.cpp','.h','.cs')]
    implementation=dict(captured_unix_s=time.time(),scope='Source bytes captured before launching the owned run',sha256={})
    for name in names:
        data=(REPO/name).read_bytes();target=output/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        implementation['sha256'][name]=hashlib.sha256(data).hexdigest()
    save(output/'implementation.json',implementation)
    run_id='joint-depth-'+uuid.uuid4().hex[:10]
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,runtime_profile='joint_quad_dds_v1',
                requested_rate=.5,task='public_position',display_socket='/tmp/wksim-'+run_id+'/state.sock')
    if airborne:config['task_dwell_seconds']=dict(hold=8,waypoint=4)
    save(output/'config.json',config)
    wsl=['wsl.exe','-d','Ubuntu-22.04','-u','root','--cd',wsl_path(REPO),'--exec']
    made=subprocess.run([*wsl,'mktemp','-d','/root/wksim-joint-depth-XXXXXXXX'],capture_output=True,text=True,check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    runs=made.stdout.strip()
    if not runs.startswith('/root/wksim-joint-depth-') or '/' in runs[len('/root/'):]:raise ValueError('Unexpected output root')
    directory=runs+'/'+run_id;shared=unc(directory)
    entry=[*wsl,'bash',wsl_path(REPO/'tools/run-wksim.sh'),wsl_path(output/'config.json'),'--output-root',runs]
    report=dict(status='failed',scope=__doc__,runtime_directory=directory,config=config,manifest=str(manifest.resolve()),frames=[],
                started_unix_s=time.time(),airborne_requested=airborne,lifecycle_requested=lifecycle,views=[])
    manager=None;view=None;reader=None
    def physical_airborne(state):
        if not state or len(state.get('participants', {})) != 2:
            return False
        tick=state['authority']['tick']
        for stack in ('arducopter','px4'):
            path=unc(state['epoch_dir'])/(stack+'-truth.jsonl')
            if not path.is_file():return False
            with path.open('rb') as trace:
                trace.seek(max(0,path.stat().st_size-131072))
                lines=trace.read().split(b'\n')
            found=False
            for line in reversed(lines[1:-1]):
                row=json.loads(line)
                if row['tick']==tick:
                    found=row['epoch']==state['epoch'] and row['state'][8]<-2.5
                    break
            if not found:return False
        return True
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
        current=view.poll() if view else None
        if current and current['state'] in ('failed','unavailable'):raise RuntimeError(current['error'])
        if state:
            if state.get('display_stream',{}).get('sent')==0 and state.get('display_stream',{}).get('dropped',0)>100:
                raise RuntimeError('Display transport unavailable: '+str(state['display_stream'].get('last_error')))
            if state['authority']['phase']=='faulted':raise RuntimeError(str(state['authority']))
            if reader:
                reader.set_epoch(state['epoch'],state['generation'],minimum_step=state['authority']['tick'])
                for frame in reader.poll():
                    # Large derived arrays are retained separately, not embedded in report JSON.
                    cloud_path=Path(frame['metadata_path']).with_suffix('.cloud.json')
                    mask_path=Path(frame['metadata_path']).with_suffix('.mask.u8')
                    save(cloud_path,frame.pop('point_cloud'))
                    mask_path.write_bytes(frame.pop('valid_mask'))
                    depths=frame.pop('depths')
                    frame.update(cloud_path=str(cloud_path),mask_path=str(mask_path),
                                 valid_pixels=sum(math.isfinite(z) for z in depths))
                    report['frames'].append(frame)
        return state
    try:
        prepared=subprocess.run([*entry,'--prepare-run'],capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        report['preparation']=dict(command=[*entry,'--prepare-run'],returncode=prepared.returncode,stdout=prepared.stdout,stderr=prepared.stderr)
        if prepared.returncode:raise RuntimeError('Preparation failed: '+prepared.stderr)
        session=read(shared/'session.json');report['session']=session
        settings=dict(version=1,vehicle_id=2,sensor_id='front_depth',width=160,height=120,horizontal_fov_degrees=90,
                      position_cm=[30,0,50],quaternion_xyzw=[0,0,0,1],interval_steps=500,notify_port=19073,max_depth_meters=100)
        view=View(output/'view',run_id,config['display_socket'],joint_instance=session['instance_id'],build_manifest=manifest,
                  depth_config=settings)
        reader=Reader(view.depth_directory,run_id,session['instance_id'],settings,stream_id=view.depth_stream_id)
        report['producer_streams']=[view.depth_stream_id]
        view.start();deadline=time.monotonic()+90
        while not view.poll()['transport_ready']:
            current=view.poll()
            if current['state'] in ('failed','unavailable'):raise RuntimeError(current['error'])
            if time.monotonic()>deadline:raise TimeoutError('UE preparation')
            time.sleep(.1)
        observe_module(view,manifest,output)
        command=[*entry,'--use-prepared-run',directory];report['command']=command
        with (output/'service.log').open('w') as log:
            manager=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            report['manager_pid']=manager.pid;deadline=time.monotonic()+180
            while len(report['frames'])<10:
                state=sample()
                if time.monotonic()>deadline:raise TimeoutError('Ten real depth frames')
                time.sleep(.1)
            if lifecycle:
                record=report['depth_lifecycle']=dict(before_epoch=state['epoch'],before_generation=state['generation'],
                    old_notification=report['frames'][-1]['notification'],old_stream=view.depth_stream_id,
                    restart_kind='capture_stream')
                old_directory=view.depth_directory
                record['disable']=view.set_depth_enabled(False)
                before=sample();count=len(report['frames']);began=time.monotonic()
                stopped=view.poll();report['views'].append(stopped)
                files_before=sorted(p.name for p in old_directory.glob('*.json'))
                while time.monotonic()-began<3:
                    state=sample();time.sleep(.1)
                files_after=sorted(p.name for p in old_directory.glob('*.json'))
                assert set(files_after)<=set(files_before), 'Stopped producer published new metadata'
                assert len(report['frames'])==count, 'Stopped producer delivered new frames'
                assert state['epoch']==before['epoch'] and state['authority']['tick']>=before['authority']['tick']+1000
                record['producer_outage']=dict(before=before['authority'],after=state['authority'],
                    wall_seconds=time.monotonic()-began,files_before=files_before,files_after=files_after,
                    old_view=stopped)
                reader.close();reader=None
                record['enable']=view.set_depth_enabled(True)
                assert view.depth_stream_id!=record['old_stream']
                report['producer_streams'].append(view.depth_stream_id)
                reader=Reader(view.depth_directory,run_id,session['instance_id'],settings,stream_id=view.depth_stream_id)
                reader.set_epoch(state['epoch'],state['generation'],minimum_step=state['authority']['tick'])
                count=len(report['frames']);restart_tick=state['authority']['tick'];deadline=time.monotonic()+30
                while len(report['frames'])<count+5:
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('Restarted producer actual frames')
                    time.sleep(.1)
                record['restarted_first_frame']=report['frames'][count]
                record['restart_tick']=restart_tick
                assert int(report['frames'][count]['metadata']['step'])>=restart_tick
                def reject_old(notification):
                    before_rejected=reader.rejected;before_count=len(report['frames'])
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as negative:
                        negative.sendto(json.dumps(notification).encode(),('127.0.0.1',settings['notify_port']))
                    deadline=time.monotonic()+2
                    while reader.rejected==before_rejected:
                        sample()
                        if time.monotonic()>deadline:raise TimeoutError('Retired notification rejection')
                        time.sleep(.01)
                    assert all(f['notification']!=notification for f in report['frames'][before_count:])
                    return dict(notification=notification,rejected=reader.rejected-before_rejected,
                        observed_unix_s=time.time())
                record['old_producer_rejection']=reject_old(record['old_notification'])
                record['before_reset_notification']=report['frames'][-1]['notification']
                old_epoch=state['epoch'];count=len(report['frames'])
                record['reset']=action('cold-reset');deadline=time.monotonic()+180
                while len(report['frames'])<count+5:
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('New epoch actual depth frames')
                    time.sleep(.1)
                assert state['epoch']!=old_epoch and state['generation']==record['before_generation']+1
                assert all(f['metadata']['epoch']==state['epoch'] for f in report['frames'][count:])
                record['reset_first_frame']=report['frames'][count]
                record['after_epoch']=state['epoch'];record['after_generation']=state['generation']
                record['old_epoch_rejection']=reject_old(record['before_reset_notification'])
                record['status']='pass'
                save(output/'report.json',report)
            if airborne:
                deadline=time.monotonic()+240
                while not state or 'start-task' not in state['allowed_actions']:
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('Normal joint preflight readiness')
                    time.sleep(.1)
                action('start-task')
                flight_start=len(report['frames']);observed=[]
                while not (len(state.get('participants',{}))==2 and
                           all(p['state']['armed'] and p['state']['position'][2]>2.5 for p in state['participants'].values()) and
                           physical_airborne(state)):
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('Dual airborne before consumer outage')
                    time.sleep(.1)
                before=dict(epoch=state['epoch'],tick=state['authority']['tick'],last_frame=report['frames'][-1],wall=time.time())
                reader.close();reader=None;began=time.monotonic()
                while time.monotonic()-began<3:
                    state=sample();time.sleep(.1)
                report['consumer_outage']=dict(before=before,after_tick=state['authority']['tick'],wall_seconds=time.monotonic()-began)
                assert state['authority']['tick']>=before['tick']+1000
                count=len(report['frames']);resume_tick=state['authority']['tick']
                reader=Reader(view.depth_directory,run_id,session['instance_id'],settings,stream_id=view.depth_stream_id)
                deadline=time.monotonic()+20
                while len(report['frames'])<count+5:
                    state=sample()
                    if time.monotonic()>deadline:raise TimeoutError('Fresh depth consumer reconnect')
                    time.sleep(.1)
                assert int(report['frames'][count]['metadata']['step'])>=resume_tick
                report['consumer_reconnect']=dict(start_tick=resume_tick,first_frame=report['frames'][count],rejected=reader.rejected)

                deadline=time.monotonic()+240
                while state['task_state']!='completed':
                    state=sample()
                    if all(p['state']['armed'] and p['state']['position'][2]>2.5 for p in state['participants'].values()):
                        observed.append(dict(epoch=state['epoch'],tick=state['authority']['tick'],
                                             last_frame_index=len(report['frames'])-1))
                    if time.monotonic()>deadline:raise TimeoutError('Public task with live depth completion')
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


def audit(directory):
    """Use original physical truth and committed clocks, never displayed pose as oracle."""
    from tools.audit_joint_rgb import rotated, multiplied, require, sha
    directory=Path(directory).resolve();report=read(directory/'report.json')
    lifecycle=report.get('lifecycle_requested',False)
    require(report['status']=='pass' and report['manager_returncode']==0,'Live run failed')
    require(report['result']==read(directory/'run/result.json'),'Retained run result differs')
    require(report['result']['status']==('stopped' if lifecycle else 'pass') and all(not e['remaining_group_members'] and
            (lifecycle or e['result']['flight_completed']) for e in report['result']['epochs']),'Public flight/retirement failed')
    require(all(not e['result'].get('faults') and not e['result'].get('authority',{}).get('fault')
                for e in report['result']['epochs']),'Unexpected physical fault in a sensor-only experiment')
    provenance=read(directory/'implementation.json')
    for name,digest in provenance['sha256'].items():
        require(sha(directory/'sources'/name)==digest,'Retained source changed')
    build=read(report['manifest']);loaded=read(directory/'ue-loaded-module.json')
    require(loaded['sha256'].lower()==build['binary_sha256']==sha(build['binary']) and
            Path(loaded['path']).resolve()==Path(build['binary']).resolve(),'Loaded module differs')
    for item in build['build_inputs']:
        source=directory/'sources/Simulator/ue55'/item['path']
        if source.is_file():require(sha(source)==item['source_sha256']==item['staging_sha256'],'Source/build mismatch')
    views=report.get('views',[])+[report['view_final']]
    by_stream={v['depth_stream_id']:v for v in views}
    require(len(by_stream)==len(views),'Repeated producer stream identity')
    for view in views:
        require(Path(view['depth_directory']).resolve().is_relative_to(directory),'Depth output escaped owned directory')
    wanted={(f['metadata']['epoch'],int(f['metadata']['step'])) for f in report['frames']}
    if lifecycle:
        record=report['depth_lifecycle'];outage=record['producer_outage']
        for endpoint in ('before','after'):wanted.add((outage[endpoint]['epoch'],outage[endpoint]['tick']))
    else:
        outage=report['consumer_outage']
        outage_key=(outage['before']['epoch'],outage['before']['tick'])
        wanted.add(outage_key)
    truth={};committed=set();evidence={}
    for epoch in report['result']['epochs']:
        folder=directory/'run/epochs'/epoch['epoch']
        for filename in ('clock.jsonl','arducopter-truth.jsonl','px4-truth.jsonl'):
            path=folder/filename;evidence[str(path.relative_to(directory))]=sha(path)
            with path.open() as rows:
                for line in rows:
                    row=json.loads(line);key=(epoch['epoch'],row['tick'])
                    if key not in wanted:continue
                    if filename=='clock.jsonl':
                        if row['pending_tick'] is None and row['time_ns']==row['tick']*1000000:committed.add(key)
                    else:
                        uid=1 if filename.startswith('arducopter') else 2
                        require(row['epoch']==epoch['epoch'] and (*key,uid) not in truth,'Repeated or foreign truth')
                        truth[(*key,uid)]=row['state']
    # No socket is opened for the retained-byte audit. Use exactly the production
    # admission/parser after explicitly restoring each recorded authoritative binding.
    readers={}
    for stream,view in by_stream.items():
        reader=Reader.__new__(Reader)
        reader.config=view['depth_config'];reader.directory=Path(view['depth_directory']).resolve();reader.run_id=report['config']['run_id']
        reader.instance_id=report['session']['instance_id'];reader.stream_id=stream
        reader.epoch=None;reader.generation=0;reader.minimum_step=0;reader.last_step=reader.last_frame=-1
        readers[stream]=reader
    if not lifecycle:
        require(all(truth[(*outage_key,uid)][8]<-2.5 for uid in (1,2)),'Consumer outage did not start during dual flight')
    checked=[];airborne=[]
    for recorded in report['frames']:
        data=recorded['metadata'];step=int(data['step']);key=(data['epoch'],step)
        reader=readers[data['stream_id']];root=reader.directory;settings=reader.config
        require(key in committed,'Depth step is not an original committed physics step')
        require(Path(recorded['metadata_path']).resolve().parent==root and
                Path(recorded['image_path']).resolve().parent==root,'Foreign frame path')
        reader.set_epoch(data['epoch'],data['generation'])
        frame=reader._read(recorded['notification'])
        require(frame['metadata']==data,'Retained native metadata differs from consumed bytes')
        state=truth[(*key,settings['vehicle_id'])];p=state[6:9];w,x,y,z=state[12:16]
        q=[-x,-y,z,w];offset=rotated(q,settings['position_cm'])
        expected=[p[0]*100+offset[0],p[1]*100+offset[1],-p[2]*100+offset[2]]
        q=multiplied(q,settings['quaternion_xyzw']);pose=data['camera_world_pose']
        position=math.dist(pose['position_cm'],expected)
        quaternion=min(math.dist(pose['quaternion_xyzw'],q),math.dist(pose['quaternion_xyzw'],[-v for v in q]))
        require(position<=2e-4 and quaternion<=2e-6,'Depth capture pose differs from original physical truth')
        require(abs(state[2]-data['sim_time_seconds'])<=1e-8,'Depth time differs from physical model time')
        cloud_path=Path(recorded['cloud_path']);mask_path=Path(recorded['mask_path'])
        require(cloud_path.parent.resolve()==root and mask_path.parent.resolve()==root,'Foreign derived output')
        require(read(cloud_path)==frame['point_cloud'] and mask_path.read_bytes()==frame['valid_mask'],
                'Retained ENU meter cloud/mask differs from original depth bytes')
        if all(truth[(*key,uid)][8]<-2.5 for uid in (1,2)):airborne.append(step)
        checked.append(dict(epoch=key[0],step=step,position_error_cm=position,quaternion_l2=quaternion,
                            valid_pixels=sum(frame['valid_mask']),metadata_sha256=sha(recorded['metadata_path']),
                            depth_sha256=sha(recorded['image_path']),cloud_sha256=sha(cloud_path),mask_sha256=sha(mask_path)))
    require(len(checked)>=15 and (lifecycle or len(airborne)>=5),'Insufficient consumed/dual-airborne depth frames')
    require(sum(f['valid_pixels'] for f in checked)>=100,'No useful valid native depth samples')
    if lifecycle:
        record=report['depth_lifecycle'];outage=record['producer_outage']
        require(record['status']=='pass' and len(by_stream)==2,'Missing actual producer restart')
        stopped=outage['old_view']
        require(record['restart_kind']=='capture_stream' and stopped['depth_enabled'] is False,
                'Producer was not explicitly disabled')
        for action,enabled in (('disable',False),('enable',True)):
            request,response=record[action]['request'],record[action]['response']
            require(request['enabled'] is enabled and response==dict(request,kind='depth_stream_controlled'),
                    'Missing correlated capture state acknowledgement')
        before,after=outage['before'],outage['after']
        require(before['epoch']==after['epoch'] and before['epoch']==record['before_epoch'],'Producer outage crossed epoch')
        advance=after['tick']-before['tick']
        require(outage['wall_seconds']>=3 and advance>=1000 and set(outage['files_after'])<=set(outage['files_before']),
                'Producer stop did not preserve independent physics/no-image boundary')
        for endpoint in (before,after):
            key=(endpoint['epoch'],endpoint['tick'])
            require(key in committed and all((*key,uid) in truth for uid in (1,2)),'Outage endpoint lacks committed raw truth')
        new_stream=record['restarted_first_frame']['metadata']['stream_id']
        require(new_stream!=record['old_stream'] and new_stream in by_stream,'Producer restart retained old stream')
        require(int(record['restarted_first_frame']['metadata']['step'])>=record['restart_tick'], 'Restart replayed old data')
        require(record['after_epoch']!=record['before_epoch'] and record['after_generation']==record['before_generation']+1,
                'Cold reset did not create next physical generation')
        require([e['epoch'] for e in report['result']['epochs']]==[record['before_epoch'],record['after_epoch']],
                'Cold reset evidence lacks two actual physical epochs')
        for label,notification in (('old_producer_rejection',record['old_notification']),
                                   ('old_epoch_rejection',record['before_reset_notification'])):
            require(record[label]['notification']==notification and record[label]['rejected']>=1,'Missing retired notification rejection')
            try:readers[new_stream]._read(notification)
            except ValueError:pass
            else:raise ValueError('Production parser accepted retired notification in final binding')
        require(stopped['pids']['ue']==report['view_final']['pids']['ue']==loaded['pid'],
                'Capture restart unexpectedly replaced the verified UE process')
        require(any(f['metadata']['epoch']==record['after_epoch'] for f in report['frames']), 'No new-epoch native depth')
        boundary=dict(producer_outage_tick_advance=advance,producer_streams=list(by_stream),
            retired_notifications_rejected=True,epochs=[record['before_epoch'],record['after_epoch']])
    else:
        outage=report['consumer_outage'];reconnect=report['consumer_reconnect']
        require(outage['wall_seconds']>=3 and outage['after_tick']-outage['before']['tick']>=1000,'Consumer outage stalled physics')
        require(int(reconnect['first_frame']['metadata']['step'])>=reconnect['start_tick']>outage['before']['tick'],
                'Consumer reconnect replayed earlier frames')
        boundary=dict(consumer_outage_tick_advance=outage['after_tick']-outage['before']['tick'])
    return dict(status='pass',frames=checked,airborne_frame_steps=airborne,evidence_sha256=evidence,
                report_sha256=sha(directory/'report.json'),**boundary,
                limitations=['Single 160x120 depth sensor only; no complete issue #31 acceptance.',
                             'Optical distance accuracy uses the separately executed native geometry fixtures.',
                             'Ground lifecycle and airborne consumer cases are separate; Full sensor fault modes remain separate obligations.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--audit-only',action='store_true')
    parser.add_argument('--lifecycle',action='store_true',help='Ground producer restart and real cold-reset isolation; no flight task')
    args=parser.parse_args()
    if not args.audit_only:
        if args.manifest is None:parser.error('--manifest is required for a live run')
        result=run(args.manifest,args.output,args.lifecycle)
    else:result=read(args.output/'report.json')
    if result['status']=='pass':
        try:
            result=audit(args.output)
        except Exception as error:
            result=dict(status='failed',error=repr(error),traceback=traceback.format_exc())
        save(args.output/'depth-audit.json',result)
    print(json.dumps({k:result.get(k) for k in ('status','error','cleanup_error','manager_returncode')}))
    raise SystemExit(result['status']!='pass')
