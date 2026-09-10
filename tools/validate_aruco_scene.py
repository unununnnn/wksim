"""Acquire the opt-in UE marker through the live RGB Reader and Consumer.

Ground calibration only. No task start, flight claim, or replacement clock.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Simulator.wksim_console.visual import View
from Simulator.wksim_console.workspace import wsl_path
from Simulator.ue55.rgb import Reader
from Simulator.wksim_perception.aruco import Consumer
from tools.validate_joint_visual import unc,read,save


def run(manifest,output):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    settings=dict(version=1,vehicle_id=2,sensor_id='front_rgb',width=640,height=480,
        horizontal_fov_degrees=90,position_cm=[30,20,10],quaternion_xyzw=[0,0,0,1],
        interval_steps=100,notify_port=19072)
    run_id='aruco-scene-'+uuid.uuid4().hex[:10]
    config=dict(schema_version=1,kind='joint_scene',run_id=run_id,
        runtime_profile='joint_quad_dds_v1',requested_rate=.5,task='public_position',
        display_socket='/tmp/wksim-'+run_id+'/state.sock')
    save(output/'config.json',config)
    report=dict(status='failed',scope=__doc__,config=config,settings=settings,frames=[],
        started_unix_s=time.time(),manifest=str(manifest.resolve()))
    source_names=['tools/validate_aruco_scene.py','tools/audit_aruco_scene.py',
        'Simulator/wksim_perception/aruco.py','Simulator/ue55/rgb.py','Simulator/wksim_console/visual.py',
        'docs/plan/40-aruco-live-scene-contract.md']
    report['source_sha256']={}
    for name in source_names:
        data=(ROOT/name).read_bytes();target=output/'sources'/name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        report['source_sha256'][name]=hashlib.sha256(data).hexdigest()
    wsl=['wsl.exe','-d','Ubuntu-22.04','-u','root','--cd',wsl_path(ROOT),'--exec']
    def call(args,timeout=30):
        return subprocess.run([*wsl,*args],capture_output=True,text=True,timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW)
    made=call(['mktemp','-d','/root/wksim-aruco-scene-XXXXXXXX']);made.check_returncode()
    runs=made.stdout.strip()
    if not runs.startswith('/root/wksim-aruco-scene-') or '/' in runs[len('/root/'):]:
        raise ValueError('Unexpected output root')
    directory=runs+'/'+run_id;shared=unc(directory)
    report['runtime_directory']=directory
    entry=['bash',wsl_path(ROOT/'tools/run-wksim.sh'),wsl_path(output/'config.json'),'--output-root',runs]
    manager=view=reader=None
    def stop():
        state=read(shared/'status.json')
        code='import sys,json;from pathlib import Path;from Simulator.wksim_runtime.joint_actions import submit;print(json.dumps(submit(Path(sys.argv[1]),"stop",sys.argv[2])))'
        result=call(['python3','-B','-c',code,directory,state['epoch']]);result.check_returncode()
        report['stop_request']=json.loads(result.stdout)
        manager.wait(timeout=40)
    try:
        prepared=call(entry+['--prepare-run'])
        report['preparation']=dict(returncode=prepared.returncode,stdout=prepared.stdout,stderr=prepared.stderr)
        prepared.check_returncode()
        session=read(shared/'session.json');report['session']=session
        view=View(output/'view',run_id,config['display_socket'],joint_instance=session['instance_id'],
            build_manifest=manifest,rgb_config=settings,rgb_fixture_case=4)
        reader=Reader(view.rgb_directory,run_id,session['instance_id'],settings,stream_id=view.rgb_stream_id)
        consumer=Consumer(settings,run_id=run_id,instance_id=session['instance_id'],dictionary='DICT_6X6_250',
            marker_id=23,side_length_m=.5,max_age_steps=300,max_distance_m=8,max_speed_mps=2,
            max_jump_m=.5,max_reprojection_px=1)
        report['stream_id']=view.rgb_stream_id
        view.start();deadline=time.monotonic()+120
        while not view.poll()['transport_ready']:
            current=view.poll()
            if current['state'] in ('failed','unavailable'):raise RuntimeError(str(current))
            if time.monotonic()>deadline:raise TimeoutError('UE readiness within 120-second attempt')
            time.sleep(.05)
        native=read(Path(view.poll()['rgb_fixture_manifest']));build=read(manifest)
        loaded=dict(path=native['module_path'],pid=native['process_id'],
            sha256=hashlib.sha256(Path(native['module_path']).read_bytes()).hexdigest())
        if (loaded['pid']!=view.poll()['pids']['ue'] or Path(loaded['path']).resolve()!=Path(build['binary']).resolve()
                or loaded['sha256']!=build['binary_sha256']):raise ValueError('Loaded candidate identity differs')
        report['loaded_module']=loaded
        report['command']=[*wsl,*entry,'--use-prepared-run',directory]
        with (output/'service.log').open('w') as log:
            manager=subprocess.Popen(report['command'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            while True:
                if time.monotonic()>deadline:raise TimeoutError('ArUco attempt exceeded 120 wall seconds')
                if manager.poll() is not None:raise RuntimeError('Manager exited before scene completion')
                current=view.poll()
                if current['state'] in ('failed','unavailable'):raise RuntimeError(str(current))
                if not (shared/'status.json').exists():time.sleep(.05);continue
                state=read(shared/'status.json')
                if state['authority']['phase']=='faulted':raise RuntimeError(str(state['authority']))
                reader.set_epoch(state['epoch'],state['generation'],minimum_step=state['authority']['tick'])
                consumer.bind(epoch=state['epoch'],generation=state['generation'],stream_id=view.rgb_stream_id,
                    minimum_step=state['authority']['tick'])
                frames=reader.poll()
                # Obtain the current authoritative step after draining notifications.
                state=read(shared/'status.json');tick=state['authority']['tick']
                if state['epoch']!=reader.epoch:raise RuntimeError('Unexpected calibration epoch transition')
                for frame in frames:
                    target=consumer.consume(frame,now_step=tick)
                    scene_path=view.rgb_directory/f"aruco-{state['epoch']}-{frame['metadata']['step']}.json"
                    scene=read(scene_path)
                    report['frames'].append(dict(frame=frame,scene_path=str(scene_path),
                        scene_sha256=hashlib.sha256(scene_path.read_bytes()).hexdigest(),now_step=tick,
                        image_sha256=hashlib.sha256(Path(frame['image_path']).read_bytes()).hexdigest(),
                        authority=dict(epoch=state['epoch'],generation=state['generation'],tick=tick),
                        target=target,reason=consumer.reason))
                consumer.current(tick)
                if report['frames']:
                    scene=read(Path(report['frames'][-1]['scene_path']))
                    if scene['step']-scene['first_step']>=5000:break
                time.sleep(.03)
            if any(row['state']['armed'] for row in state['participants'].values()):
                raise ValueError('Ground calibration unexpectedly armed')
            stop()
        result=read(shared/'result.json')
        if manager.returncode!=0 or result['status']!='stopped' or not result.get('epochs') or any(
                epoch['remaining_group_members'] for epoch in result['epochs']):raise ValueError('Incomplete retirement')
        report.update(status='acquired',result=result)
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
        report['finished_unix_s']=time.time();save(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.manifest,args.output)
    print(json.dumps({key:result.get(key) for key in ('status','error','cleanup_error','manager_returncode')}))
    raise SystemExit(result['status']!='acquired')
