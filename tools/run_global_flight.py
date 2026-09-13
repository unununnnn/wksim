"""Bounded independent global reference experiment; completion still requires raw audit."""
import argparse
import hashlib
import importlib.util
import json
import os
import numbers
from pathlib import Path
import shlex
import signal
import shutil
import socket
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.isolation import Reservation, check_isolation, resources
from Simulator.wksim_runtime.runtime import launch_spec, stop_children, truth_summary, udp_listening


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric_json(value):
    if isinstance(value,numbers.Integral):return int(value)
    if isinstance(value,numbers.Real):return float(value)
    raise TypeError('Unsupported evidence value: '+type(value).__name__)


def prepare_datum(admission, directory, scene_epoch):
    """Bind configured model origin, sensor sample and native launch evidence."""
    config = admission['config']
    from Simulator.wksim_core.model import Model
    with Model(admission['library']) as model:
        initial = model.step([0.]*16)
    sample = directory/'datum-model-initial.json'
    sample.write_text(json.dumps(dict(output120=initial, library=admission['library'],
        library_sha256=digest(admission['library'])), indent=2)+'\n')
    model_root = Path(admission['library']).parent
    probe = directory/'model-origin-probe'
    argv = ['g++', '-std=c++17', '-O2', '-I', str(model_root),
            str(REPO/'tools/global_origin_probe.cpp'), '-ldl', '-o', str(probe)]
    built = subprocess.run(argv, text=True, capture_output=True, timeout=60)
    (directory/'model-origin-build.log').write_text(built.stdout+built.stderr)
    if built.returncode: raise RuntimeError('Configured model origin probe failed to build')
    origin = json.loads(subprocess.check_output([str(probe), admission['library']], text=True))
    origin_record = directory/'datum-model-origin.json'
    origin_record.write_text(json.dumps(dict(origin=origin, compiler_argv=argv,
        probe_sha256=digest(probe), library_sha256=digest(admission['library']),
        generated_header_sha256=digest(model_root/'Exp1_MinModelTemp.h'),
        generated_source_sha256=digest(model_root/'Exp1_MinModelTemp.cpp')), indent=2)+'\n')
    plan = launch_spec(config, directory, admission['library'])
    native = Path(plan['fc'][0])
    launch = directory/'datum-native-launch.json'
    launch.write_text(json.dumps(plan, indent=2)+'\n')
    if config['stack'] == 'arducopter':
        # AP constructs absolute location from this actual --home origin and
        # the JSON NED position. This is distinct from its subsequently set home.
        lat, lon, alt, _ = map(float, plan['fc'][plan['fc'].index('--home')+1].split(','))
        if (lat, lon, alt) != (origin['latitude_deg'], origin['longitude_deg'], origin['alt_amsl_m']):
            raise ValueError('AP launch origin differs from configured model origin')
        native_source = Path(config['ap_candidate'])/'src/libraries/SITL/SIM_Aircraft.cpp'
    else:
        # Sensor GPS includes noise. The configured origin, not the first GPS
        # sample, defines physical truth's geographic/AMSL reference.
        lat, lon, alt = origin['latitude_deg'], origin['longitude_deg'], origin['alt_amsl_m']
        native_source = Path(config['px4_root'])/'src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp'
    proof = dict(schema='global-datum-proof-v1', stack=config['stack'], run_id=config['run_id'], datum='amsl',
        scene_origin=dict(id=scene_epoch, latitude_deg=lat, longitude_deg=lon, alt_amsl_m=alt),
        native_binary=dict(path=str(native.resolve()), sha256=digest(native)),
        sources={str(p.resolve()): digest(p) for p in (sample, launch, native_source, origin_record, probe,
            model_root/'Exp1_MinModelTemp.h', model_root/'Exp1_MinModelTemp.cpp',
            REPO/'tools/global_origin_probe.cpp',
            REPO/'Simulator/wksim_core/ap_json.py', REPO/'Simulator/wksim_core/px4_mavlink.py')})
    path = directory/'datum-proof.json'
    path.write_text(json.dumps(proof, indent=2)+'\n')
    return dict(schema='global-home-v1', proof_path=str(path), proof_sha256=digest(path),
                require_same_value_home_reset=False)


def launch_plan(config, directory, library, scene_epoch):
    plan = launch_spec(config, directory, library, admitted_capabilities=('global_home_v1',))
    ap = config['stack']=='arducopter'
    if ap:
        plan['fc'][plan['fc'].index('--speedup')+1] = '1'
    else:
        plan['fc_environment']['PX4_SIM_SPEED_FACTOR'] = '1'
        plan['fc_environment']['PX4_PARAM_COM_OBL_RC_ACT']='4'
    plan['physics'] = [sys.executable,'-B',str(REPO/'tools/global_physics.py'),
        '--stack',config['stack'],'--library',str(library),'--port','19002' if ap else '4581',
        '--trace',str(directory/'truth.jsonl'),'--profile',str(directory/'global-profile.json'),
        '--run-id',config['run_id'],'--scene-epoch',scene_epoch]
    return plan


def run(admission, output, scene_epoch, *, home_change=False):
    check_isolation()
    if any(os.environ.get(k)!=v for k,v in dict(ROS_DOMAIN_ID='77',ROS_LOCALHOST_ONLY='1',
            RMW_IMPLEMENTATION='rmw_fastrtps_cpp').items()):
        raise RuntimeError('Requires private domain77/FastDDS/localhost')
    config = admission['config']
    if output.exists() or output.parent != Path('/root') or not output.name.startswith('wksim-global-flight-'):
        raise ValueError('Use a fresh /root/wksim-global-flight-* output directory')
    output.mkdir(mode=0o700)
    directory = output/config['run_id']
    directory.mkdir(mode=0o700)
    resource = resources(config, directory)
    result = dict(status='failed', experimental=True, production_admitted=False,
        stack=config['stack'], run_id=config['run_id'], config=config, run_dir=str(directory),
        admission=admission, children={}, phases=[], safe_landing=False, resources=resource,
        scene_epoch=scene_epoch,scope='Independent global reference flight; raw audit required')
    for name,value in [('admission',admission),('config',config),('isolation',resource)]:
        (directory/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    source_names = ['tools/global_origin_probe.cpp', 'tools/audit_global_home_flight.py', 'Simulator/wksim_runtime/global-flight-v2.json', 'Simulator/wksim_runtime/home_mutation.py', 'tools/audit_global_flight.py', 'tools/px4_home_candidate.py', 'tools/build-px4-home-heartbeat.sh', 'patches/px4/0003-home-observation-heartbeat.patch', 'tools/run_global_flight.py', 'tools/run-global-flight.sh', 'tools/global_physics.py', 'tools/rc_candidate.py', 'tools/joint_control_candidate.py', 'tools/pid_physics.py', 'Simulator/wksim_runtime/global_task.py', 'Simulator/wksim_runtime/global-flight-v1.json', 'Simulator/wksim_runtime/rc_task.py', 'Simulator/wksim_runtime/efficiency_task.py', 'Simulator/wksim_runtime/task.py', 'Simulator/wksim_runtime/runtime.py', 'Simulator/wksim_runtime/isolation.py', 'Simulator/wksim_runtime/config.py', 'Simulator/wksim_runtime/joint_profile.py', 'Simulator/wksim_runtime/build_identity.py', 'Simulator/wksim_core/model.py', 'Simulator/wksim_core/model.cpp', 'Simulator/wksim_control/global_reference.py', 'Simulator/wksim_control/global_profile.py', 'Simulator/wksim_core/px4_mavlink.py', 'Simulator/wksim_core/ap_json.py', 'Simulator/wksim_core/state_stream.py', 'Simulator/wksim_core/arducopter-quad-x.parm', 'Simulator/wksim_core/px4-rc.mavlink']
    result['source_sha256']={name:digest(REPO/name) for name in source_names}
    for name in source_names:
        target=directory/'run-source'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    children,task,ros=[],None,None
    started=time.monotonic()
    def phase(name):
        result['phases'].append(dict(phase=name,wall_s=time.monotonic()-started))
        print(name,flush=True)
    def health():
        if time.monotonic()-started>320:
            raise TimeoutError('320 second independent candidate wall watchdog')
        for name,child,_ in children:
            if child.poll() is not None:
                raise RuntimeError(f'{name} exited: {child.returncode}')
    def wait(label,predicate,seconds=30):
        end=time.monotonic()+seconds
        while not predicate():
            health()
            if time.monotonic()>end: raise TimeoutError(label)
            time.sleep(.02)
        phase(label)
    def interrupt(signum,frame):
        raise InterruptedError(f'Interrupted by signal {signum}')
    old={sig:signal.signal(sig,interrupt) for sig in (signal.SIGTERM,signal.SIGINT)}
    with Reservation(resource) as reservation:
        def launch(name,argv,env=None):
            log=(directory/(name+'.log')).open('x')
            try:
                child=subprocess.Popen(argv,cwd=directory,env=env,stdout=log,stderr=subprocess.STDOUT,
                    start_new_session=True,pass_fds=tuple(reservation.fds))
            except BaseException:
                log.close(); raise
            children.append((name,child,log))
            result['children'][name]=dict(argv=argv,cwd=str(directory),pid=child.pid,pgid=child.pid,
                proc_stat=Path(f'/proc/{child.pid}/stat').read_text(),
                executable=str(Path(f'/proc/{child.pid}/exe').resolve()))
        try:
            spec=importlib.util.find_spec('prometheus_control')
            if spec is None or spec.origin is None or not Path(spec.origin).resolve().is_relative_to(
                    Path(config['prometheus_workspace'])/'install'):
                raise ValueError('Selected candidate is not the actual imported control package')
            profile_name = 'global-flight-v2.json' if home_change else 'global-flight-v1.json'
            shutil.copy2(REPO/'Simulator/wksim_runtime'/profile_name,directory/'global-profile.json')
            config['global_reference'] = prepare_datum(admission, directory, scene_epoch)
            (directory/'config.json').write_text(json.dumps(config, indent=2)+'\n')
            plan=launch_plan(config,directory,admission['library'],scene_epoch)
            result['launch_plan']=plan
            from Simulator.wksim_runtime.isolation import isolate_temporary_files
            result['private_temporary_files'] = isolate_temporary_files()
            if config['stack']=='arducopter':
                (directory/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
            result['launched_binary_sha256']=digest(plan['fc'][0])
            result['launched_agent_sha256']=digest(plan['agent'][0])
            firmware=admission.get('native_override',admission['baseline']['identities']['ap' if config['stack']=='arducopter' else 'px4'])
            agent=admission['baseline']['identities'][config['stack']+'_agent']
            if (str(Path(plan['fc'][0]).resolve())!=firmware['path']
                    or result['launched_binary_sha256']!=firmware['sha256']
                    or str(Path(plan['agent'][0]).resolve())!=agent['path']
                    or result['launched_agent_sha256']!=agent['sha256']):
                raise ValueError('Actual launch binary/Agent differs from candidate admission')
            control=admission['control']
            result['actual_control_sha256']={p.name:digest(p) for p in Path(spec.origin).parent.glob('*.py')}
            if result['actual_control_sha256']!=control['python_sha256']:
                raise ValueError('Actual imported control bytes differ from candidate admission')
            shutil.copytree(Path(control['root'])/'src/prometheus_control', directory/'control-source',
                            ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(admission['control_manifest'], directory/'control-build.json')
            if 'px4_home_manifest' in admission:
                shutil.copy2(admission['px4_home_manifest'], directory/'px4-home-build.json')
            transport=Path(control['root'])/'install/prometheus_control/lib/libwksim_rc_take.so'
            if digest(transport)!=control['rc_transport_sha256']:
                raise ValueError('Installed RC transport library differs')
            shutil.copy2(transport, directory/transport.name)
            for port in resource['ports']:
                kind=socket.SOCK_DGRAM if port['protocol']=='udp' else socket.SOCK_STREAM
                with socket.socket(socket.AF_INET,kind) as sock: sock.bind(('127.0.0.1',port['port']))
            launch('physics',plan['physics'])
            wait('physics_listening',lambda:'"ready": true' in (directory/'physics.log').read_text())
            launch('agent',plan['agent'])
            wait('agent_listening',lambda:udp_listening(12019 if config['stack']=='arducopter' else 18888))
            launch('fc',plan['fc'],dict(os.environ,**plan['fc_environment']))
            wait('physics_fc_coupled',lambda:(directory/'truth.jsonl').exists() and (directory/'truth.jsonl').stat().st_size>0)
            launch('control',plan['control'])
            import rclpy
            from Simulator.wksim_runtime.global_task import GlobalTask
            from Simulator.wksim_runtime.task import grounded
            ros=rclpy; ros.init()
            task=GlobalTask(directory,health,phase,config['stack'],run_id=config['run_id'],protocol='session_v1',scene_epoch=scene_epoch)
            for name,child,_ in children:
                (directory/(name+'.maps')).write_bytes(Path(f'/proc/{child.pid}/maps').read_bytes())
            task.execute()
            health()
            truth=truth_summary(directory/'truth.jsonl')
            if not task.fresh() or not grounded(task.state) or abs(truth['final_height_m'])>=.3:
                raise RuntimeError('Grounded public state and physical truth required for normal stop')
            result.update(status='observed',safe_landing=True,truth=truth)
            phase('landed_stop')
        except (Exception,KeyboardInterrupt) as error:
            result['error']=f'{type(error).__name__}: {error}'
        finally:
            for sig in old: signal.signal(sig,signal.SIG_IGN)
            if task is not None:
                try: result['task']=task.report(); task.close()
                except Exception as error: result['task_close_error']=str(error)
            if ros is not None and ros.ok():
                try: ros.shutdown()
                except Exception as error: result['ros_close_error']=str(error)
            result['cleanup_errors']=stop_children(children)
            for name,child,_ in children: result['children'][name]['returncode']=child.poll()
            result['children_reaped']=all(child.poll() is not None for _,child,_ in children)
            result['source_unchanged']=all(digest(REPO/name)==value for name,value in result['source_sha256'].items())
            try:
                from tools.joint_control_candidate import check
                result['candidate_unchanged'] = check(admission['control_manifest'], admission['control_sha256']) == control
                result['candidate_unchanged'] &= (digest(plan['fc'][0])==result['launched_binary_sha256']
                    and digest(plan['agent'][0])==result['launched_agent_sha256']
                    and digest(admission['library'])==admission['baseline']['identities']['model']['library_sha256'])
                if 'px4_home_manifest' in admission:
                    from tools.px4_home_candidate import check as check_home
                    check_home(admission['px4_home_manifest'], admission['px4_home_sha256'])
            except Exception as error:
                result['candidate_unchanged']=False
                result['postflight_identity_error']=str(error)
            result['wall_seconds']=time.monotonic()-started
            result['stop_kind']='landed_stop' if result['safe_landing'] else 'unsuccessful_isolated_teardown'
            if (result['cleanup_errors'] or not result['children_reaped'] or not result['source_unchanged']
                    or not result['candidate_unchanged']
                    or 'task_close_error' in result or 'ros_close_error' in result):
                result['status']='failed'
            (directory/'result.json').write_text(json.dumps(result,indent=2,default=numeric_json)+'\n')
            for sig,previous in old.items(): signal.signal(sig,previous)
    print(json.dumps(dict(status=result['status'],result=str(directory/'result.json'))),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack',required=True,choices=('px4','arducopter'))
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--scene-epoch',default=None)
    parser.add_argument('--control-manifest', required=True)
    parser.add_argument('--control-sha256', required=True)
    parser.add_argument('--px4-home-manifest')
    parser.add_argument('--px4-home-sha256')
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--home-change',action='store_true',help='Use frozen v2 with actual native home edit and explicit recovery')
    parser.add_argument('--prepared',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if bool(args.px4_home_manifest) != bool(args.px4_home_sha256) or args.px4_home_manifest and args.stack != 'px4':
        raise ValueError('PX4 home candidate requires both manifest and checksum on PX4 only')
    import uuid,re
    args.scene_epoch=args.scene_epoch or uuid.uuid4().hex
    if not re.fullmatch('[0-9a-f]{32}',args.scene_epoch):raise ValueError('Scene epoch must be hex32')
    if args.output_root is None and not args.preflight:
        raise ValueError('--output-root required for a run')
    if not args.prepared:
        from tools.joint_control_candidate import check
        from Simulator.wksim_runtime.joint_profile import select_profile
        control=check(args.control_manifest,args.control_sha256)
        setups=select_profile('joint_quad_dds_v1')['setup_files'][:-1]+[control['root']+'/install/local_setup.bash']
        script='set -eo pipefail\n'+''.join('source '+shlex.quote(path)+'\n' for path in setups)
        script+='export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1\n'
        script+='export LD_LIBRARY_PATH=/root/wksim-dds-VxM6Ni/agent-install/lib:${LD_LIBRARY_PATH:-}\n'
        script+='exec '+shlex.join([sys.executable,'-B',str(Path(__file__).resolve()),'--prepared',
            '--stack',args.stack,'--run-id',args.run_id,'--output-root',str(args.output_root),
            '--scene-epoch',args.scene_epoch,'--control-manifest',args.control_manifest,'--control-sha256',args.control_sha256]
            +(['--px4-home-manifest',args.px4_home_manifest,'--px4-home-sha256',args.px4_home_sha256] if args.px4_home_manifest else [])
            +(['--preflight'] if args.preflight else []))+'\n'
        if args.home_change:
            script=script.rstrip('\n')+' --home-change\n'
        os.execvp('bash',['bash','-c',script])
    from rc_candidate import admit
    admission=admit(args.stack,args.run_id,args.control_manifest,args.control_sha256)
    if args.px4_home_manifest:
        from tools.px4_home_candidate import check as check_home
        home = check_home(args.px4_home_manifest, args.px4_home_sha256)
        if home['baseline_binary_sha256'] != admission['baseline']['identities']['px4']['sha256']:
            raise ValueError('PX4 home candidate derives from a different admitted baseline')
        admission.update(px4_home_manifest=args.px4_home_manifest, px4_home_sha256=args.px4_home_sha256,
            native_override=dict(path=str(Path(home['root'])/'src/build/px4_sitl_default/bin/px4'), sha256=home['binary_sha256']))
        admission['config']['px4_root'] = str(Path(home['root'])/'src')
    if args.preflight:
        print(json.dumps(admission,indent=2)); return 0 if admission['ok'] else 2
    result=run(admission,args.output_root,args.scene_epoch,home_change=args.home_change)
    # Observed is deliberately not an audited flight PASS.
    return 0 if result['status']=='observed' else 1


if __name__=='__main__': raise SystemExit(main())
