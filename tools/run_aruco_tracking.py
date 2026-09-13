"""Real camera/public-task candidate capture; independent audit grants the verdict."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_console.visual import View
from Simulator.wksim_console.workspace import wsl_path
from Simulator.ue55.rgb import Reader
from Simulator.wksim_perception.aruco import Consumer
from Simulator.wksim_runtime.joint_aruco_profile import PROFILE,TASK,validate_experiment
from tools.validate_joint_visual import unc,read,save


def atomic_json(path,value):
    """Single coordinator owns these files; readers observe complete records."""
    path=Path(path)
    temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(value,allow_nan=False,separators=(',',':'))+'\n')
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def episode_ready(shared,state,run_id):
    """Only the current workers' post-takeoff markers can enable this camera."""
    expected=str(shared/'epochs'/state['epoch'])
    epoch=unc(state['epoch_dir'])
    if str(epoch)!=expected:
        raise ValueError('Foreign epoch directory in runtime status')
    groups=list((epoch/'tasks').glob('*'))
    if len(groups)!=1:
        return None
    result={}
    for stack,uid in (('arducopter',1),('px4',2)):
        path=groups[0]/stack/'tracking-ready.json'
        if not path.is_file():return None
        row=read(path)
        if (row['run_id']!=run_id or row['scene_epoch']!=state['epoch']
                or row['stack']!=stack or row['uav_id']!=uid
                or type(row.get('authority_tick')) is not int or row['authority_tick']<0):
            raise ValueError('Tracking readiness identity differs')
        # Workers publish readiness independently of the supervisor's periodic
        # status snapshot. Wait for a snapshot that has caught up; never use
        # the marker to advance the coordinator's authority time.
        if row['authority_tick']>state['authority']['tick']:
            return None
        result[stack]=row
    return result


def observation(binding,frame,target,sequence):
    metadata=frame['metadata']
    notice=frame['notification']
    if (type(notice.get('generation')) is not int or notice['generation']!=binding['generation']
            or any(notice.get(key)!=binding[key] for key in ('run_id','epoch','stream_id','instance_id'))
            or notice.get('schema')!='wksim.rgb-ready.v2'
            or notice.get('metadata')!=Path(frame['metadata_path']).name):
        raise ValueError('Cannot publish a foreign RGB notification')
    if (metadata['epoch']!=binding['epoch'] or metadata['stream_id']!=binding['stream_id']
            or metadata['instance_id']!=binding['instance_id'] or metadata['run_id']!=binding['run_id']):
        raise ValueError('Cannot publish a frame from a different binding')
    return dict(schema='wksim.aruco-observation.v1',run_id=binding['run_id'],epoch=binding['epoch'],
        instance_id=binding['instance_id'],generation=binding['generation'],stream_id=binding['stream_id'],
        sequence=sequence,capture_step=int(metadata['step']),frame_id=int(metadata['frame_id']),
        target=target,image_sha256=hashlib.sha256(Path(frame['image_path']).read_bytes()).hexdigest())


def run(manifest,output,candidate,*,cpu_timing=False,write_timing=False,async_evidence=False,async_model_evidence=False):
    candidate=validate_experiment(candidate)
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    profile_path=ROOT/'Simulator/wksim_runtime/aruco-tracking-v1.json'
    profile_raw=profile_path.read_bytes();profile=json.loads(profile_raw)
    settings=dict(profile['camera'],vehicle_id={'arducopter':1,'px4':2}[candidate['selected_stack']])
    run_id='aruco-track-'+uuid.uuid4().hex[:10]
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,runtime_profile=PROFILE,
        requested_rate=.5,task=TASK,aruco_experiment=candidate,
        display_socket='/tmp/wksim-'+run_id+'/state.sock')
    save(output/'config.json',config)
    report=dict(status='failed',scope=__doc__,config=config,settings=settings,profile=profile,
        profile_sha256=hashlib.sha256(profile_raw).hexdigest(),frames=[],observations=[],
        started_unix_s=time.time(),manifest=str(manifest.resolve()),source_sha256={},cpu_timing=cpu_timing,
        write_timing=write_timing,async_evidence=async_evidence,async_model_evidence=async_model_evidence)
    names=['tools/run_aruco_tracking.py','Simulator/ue55/rgb.py',
           'Simulator/wksim_console/visual.py','Simulator/wksim_perception/aruco.py',
           'Simulator/wksim_perception/target_intent.py','Simulator/wksim_runtime/aruco-tracking-v1.json']
    for name in names:
        data=(ROOT/name).read_bytes();target=output/'sources'/name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        report['source_sha256'][name]=hashlib.sha256(data).hexdigest()
    wsl=['wsl.exe','-d','Ubuntu-22.04','-u','root','--cd',wsl_path(ROOT),'--exec']
    def call(args,timeout=30):
        return subprocess.run([*wsl,*args],capture_output=True,text=True,timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    made=call(['mktemp','-d','/root/wksim-aruco-track-XXXXXXXX']);made.check_returncode()
    runs=made.stdout.strip()
    if not runs.startswith('/root/wksim-aruco-track-') or '/' in runs[len('/root/'):]:
        raise ValueError('Unexpected output root')
    directory=runs+'/'+run_id;shared=unc(directory);report['runtime_directory']=directory
    entry=['env','WKSIM_OBSERVE_PX4_SETUP=1','bash',wsl_path(ROOT/'tools/run-wksim.sh'),
           wsl_path(output/'config.json'),'--output-root',runs]
    if cpu_timing:entry.insert(2,'WKSIM_JOINT_CPU_TIMING=1')
    if write_timing:entry.insert(2,'WKSIM_JOINT_WRITE_TIMING=1')
    if async_evidence:entry.insert(2,'WKSIM_JOINT_ASYNC_EVIDENCE=1')
    if async_model_evidence:entry.insert(2,'WKSIM_JOINT_ASYNC_MODEL_EVIDENCE=1')
    manager=view=reader=None;binding=None
    def action(name):
        state=read(shared/'status.json')
        code=('import sys,json;from pathlib import Path;from Simulator.wksim_runtime.joint_actions import submit;'
              'print(json.dumps(submit(Path(sys.argv[1]),sys.argv[2],sys.argv[3])))')
        result=call(['python3','-B','-c',code,directory,name,state['epoch']]);result.check_returncode()
        return json.loads(result.stdout)
    def stop():
        report['stop_request']=action('stop');manager.wait(timeout=40)
    try:
        prepared=call(entry+['--prepare-run'])
        report['preparation']=dict(returncode=prepared.returncode,stdout=prepared.stdout,stderr=prepared.stderr)
        prepared.check_returncode()
        session=read(shared/'session.json');report['session']=session
        view=View(output/'view',run_id,config['display_socket'],joint_instance=session['instance_id'],
            build_manifest=manifest,rgb_config=settings,rgb_fixture_case=profile['scene']['fixture_case'])
        target=profile['target']
        consumer=Consumer(settings,run_id=run_id,instance_id=session['instance_id'],**target)
        view.start();deadline=time.monotonic()+400
        while not view.poll()['transport_ready']:
            if view.poll()['state'] in ('failed','unavailable'):raise RuntimeError(str(view.poll()))
            if time.monotonic()>deadline:raise TimeoutError('UE readiness deadline')
            time.sleep(.05)
        native=read(Path(view.poll()['rgb_fixture_manifest']));build=read(manifest)
        loaded=dict(path=native['module_path'],pid=native['process_id'],
                    sha256=hashlib.sha256(Path(native['module_path']).read_bytes()).hexdigest())
        if (loaded['pid']!=view.poll()['pids']['ue'] or Path(loaded['path']).resolve()!=Path(build['binary']).resolve()
                or loaded['sha256']!=build['binary_sha256']):raise ValueError('Loaded UE candidate differs')
        if view.rgb_enabled or native.get('anchor_valid') is not False or native['first_step']!=-1:
            raise ValueError('Tracking scene was not initially disabled and unanchored')
        report.update(loaded_module=loaded,initial_scene=native,command=[*wsl,*entry,'--use-prepared-run',directory])
        with (output/'service.log').open('w') as log:
            manager=subprocess.Popen(report['command'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            task_started=False;stable_since=None;scene_complete=False
            while True:
                if time.monotonic()>deadline:raise TimeoutError('ArUco tracking bounded attempt expired')
                if manager.poll() is not None:raise RuntimeError('Manager exited before capture completed')
                if view.poll()['state'] in ('failed','unavailable'):raise RuntimeError(str(view.poll()))
                if not (shared/'status.json').exists():time.sleep(.03);continue
                state=read(shared/'status.json');tick=state['authority']['tick']
                if state['authority']['phase']=='faulted' or state['task_state']=='failed':
                    raise RuntimeError(str(state))
                if not task_started and 'start-task' in state['allowed_actions']:
                    report['start_request']=action('start-task');task_started=True
                if scene_complete:
                    if state['task_state']=='completed':break
                    time.sleep(.03);continue
                if not view.rgb_enabled:
                    if view.rgb_directory.exists() and list(view.rgb_directory.glob('*.png')):
                        raise ValueError('RGB captured before explicit enable')
                    ready=episode_ready(shared,state,run_id) if task_started else None
                    participants=list(state.get('participants',{}).values())
                    stable=ready is not None and len(participants)==2 and all(p.get('state') and p['state']['armed']
                        and abs(p['state']['position'][2]-3)<=.2
                        and math.sqrt(sum(v*v for v in p['state']['velocity']))<=.2 for p in participants)
                    stable_since=tick if stable and stable_since is None else stable_since if stable else None
                    if stable_since is None or tick-stable_since<1000:time.sleep(.03);continue
                    report.update(enable_state=state,tracking_ready=ready,enable_request=view.set_rgb_enabled(True))
                    reader=Reader(view.rgb_directory,run_id,session['instance_id'],settings,stream_id=view.rgb_stream_id)
                    report['stream_id']=view.rgb_stream_id
                reader.set_epoch(state['epoch'],state['generation'],minimum_step=0)
                consumer.bind(epoch=state['epoch'],generation=state['generation'],stream_id=view.rgb_stream_id,minimum_step=0)
                frames=reader.poll();state=read(shared/'status.json');tick=state['authority']['tick']
                if state['epoch']!=reader.epoch:raise RuntimeError('Unexpected epoch transition')
                scene_dir=unc(state['epoch_dir'])/'aruco'
                for frame in frames:
                    scene_path=view.rgb_directory/f"aruco-{state['epoch']}-{frame['metadata']['step']}.json"
                    scene=read(scene_path)
                    if binding is None:
                        binding=dict(schema='wksim.aruco-binding.v1',run_id=run_id,epoch=state['epoch'],
                            instance_id=session['instance_id'],generation=state['generation'],stream_id=view.rgb_stream_id,
                            camera=dict(vehicle_id=settings['vehicle_id'],sensor_id=settings['sensor_id']),
                            first_step=scene['first_step'],profile_sha256=report['profile_sha256'])
                        atomic_json(scene_dir/'binding.json',binding);report['binding']=binding
                    if scene['first_step']!=binding['first_step']:raise ValueError('Tracking fixture anchor reset')
                    detected=consumer.consume(frame,now_step=tick)
                    row=observation(binding,frame,detected,len(report['observations'])+1)
                    report['frames'].append(dict(frame=frame,scene_path=str(scene_path),
                        scene_sha256=hashlib.sha256(scene_path.read_bytes()).hexdigest(),now_step=tick,
                        image_sha256=row['image_sha256'],authority=dict(epoch=state['epoch'],generation=state['generation'],tick=tick),
                        participants=state.get('participants'),target=detected,reason=consumer.reason))
                    report['observations'].append(row)
                    atomic_json(scene_dir/'observation.json',row)
                consumer.current(tick)
                if binding is not None and tick>=binding['first_step']+sum(profile['scene'][name] for name in
                        ('initial_steps','moving_steps','occluded_steps','recovery_steps')):
                    report['disable_state']=state
                    report['disable_request']=view.set_rgb_enabled(False);scene_complete=True
                time.sleep(.03)
            if any(p['state']['armed'] for p in state['participants'].values()):
                raise ValueError('Tasks reported completed while armed')
            report['completed_state']=state;stop()
        result=read(shared/'result.json')
        if (manager.returncode!=0 or result['status']!='stopped' or not result.get('epochs')
                or any(e['remaining_group_members'] or e['result']['status']!='stopped'
                       or e['result']['authority']['fault'] is not None for e in result['epochs'])):
            raise ValueError('Incomplete candidate retirement')
        report.update(status='captured_pending_independent_audit',result=result)
    except BaseException as error:
        report.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        if manager is not None and manager.poll() is None:
            try:stop()
            except Exception as error:report['cleanup_error']=repr(error)
        if reader:report['reader_rejected']=reader.rejected;reader.close()
        if view:report['view_final']=view.stop()
        if manager is not None:report['manager_returncode']=manager.poll()
        if shared.is_dir():
            copied=call(['python3','-B','-c','import shutil,sys;shutil.copytree(sys.argv[1],sys.argv[2])',
                         directory,wsl_path(output/'run')],timeout=180)
            if copied.returncode:report.update(status='failed',retention_error=copied.stderr)
        report['changed_sources']=[name for name,sha in report['source_sha256'].items()
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha]
        if report['changed_sources'] or report.get('cleanup_error'):report['status']='failed'
        report['finished_unix_s']=time.time();save(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True,help='Explicit selected stack and Control/PX4 build manifest pins')
    parser.add_argument('--cpu-timing',action='store_true',help='Opt-in existing per-stage and per-stack wait timing probe')
    parser.add_argument('--write-timing',action='store_true',help='Measure actual synchronous evidence write calls')
    parser.add_argument('--async-evidence',action='store_true',help='Explicit bounded background JSONL evidence writer experiment')
    parser.add_argument('--async-model-evidence',action='store_true',help='Explicit bounded background model trace writer experiment')
    args=parser.parse_args();result=run(args.manifest,args.output,read(args.candidate),cpu_timing=args.cpu_timing,
                                      write_timing=args.write_timing,async_evidence=args.async_evidence,
                                      async_model_evidence=args.async_model_evidence)
    print(json.dumps({key:result.get(key) for key in ('status','error','cleanup_error','manager_returncode')}))
    raise SystemExit(result['status']!='captured_pending_independent_audit')
