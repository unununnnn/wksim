"""Bounded #35 external PID run using the sealed #34 attitude candidate outlet."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
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


def same_identities(before, after, runtime_sources):
    """Newly imported modules must already have a preflight/run source seal."""
    if not after['ok']:
        return False
    a,b=before['identities'],after['identities']
    if any(a[key]!=b[key] for key in ('ap','px4','model_build','native','control','setup_sha256')):
        return False
    first,last=a['source_sha256'],b['source_sha256']
    if any(last.get(name)!=value for name,value in first.items()):
        return False
    return all(name in first or runtime_sources.get(name)==value for name,value in last.items())


def launch_plan(config, directory, library):
    plan = launch_spec(config, directory, library)
    plan['control'] += ['-p', 'native_attitude_profile:=attitude_thrust_v1',
                        '-p', 'enable_external_attitude:=true']
    ap = config['stack']=='arducopter'
    if ap:
        index = plan['fc'].index('--speedup')
        plan['fc'][index+1] = '1'
        defaults = plan['fc'].index('--defaults')+1
        # DDS dynamic parameters must remain the last file, as in the original.
        files = plan['fc'][defaults].split(',')
        files.insert(-1, str(directory/'attitude.parm'))
        plan['fc'][defaults] = ','.join(files)
    else:
        plan['fc_environment']['PX4_SIM_SPEED_FACTOR']='1'
    plan['physics'] = [sys.executable, '-B', str(REPO/'tools/pid_physics.py'),
        '--stack', config['stack'], '--library', str(library),
        '--port', '19002' if ap else '4581', '--trace', str(directory/'truth.jsonl'),
        '--raw', str(directory/'physics-1ms.jsonl'), '--config', str(directory/'pid-protocol.json'),
        '--run-id', config['run_id']]
    return plan


def run(admission, output, pid_config, config_path):
    from Simulator.wksim_runtime.pid_task import load_config
    if pid_config != load_config(config_path):
        raise ValueError('PID configuration changed after admission')
    check_isolation()
    if any(os.environ.get(k)!=v for k,v in dict(ROS_DOMAIN_ID='77',ROS_LOCALHOST_ONLY='1',
            RMW_IMPLEMENTATION='rmw_fastrtps_cpp').items()):
        raise RuntimeError('Requires private domain77/FastDDS/localhost')
    config = admission['config']
    if output.exists() or output.parent != Path('/root') or not output.name.startswith('wksim-pid-flight-'):
        raise ValueError('Use a fresh /root/wksim-pid-flight-* output directory')
    output.mkdir(mode=0o700)
    directory = output/config['run_id']
    directory.mkdir(mode=0o700)
    resource = resources(config, directory)
    result = dict(status='failed', experimental=True, production_admitted=False,
        stack=config['stack'], run_id=config['run_id'],
        config=dict(config, controller='pid', external_pid=pid_config), run_dir=str(directory),
        admission=admission, children={}, phases=[], safe_landing=False, resources=resource,
        scope=pid_config['scope'])
    (directory/'pid-protocol.json').write_bytes(Path(config_path).read_bytes())
    for name,value in [('admission',admission),('config',result['config']),('isolation',resource)]:
        (directory/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    source_names = ['tools/run_pid_flight.py','tools/run-pid-flight.sh','tools/pid_physics.py',
        'Simulator/wksim_runtime/pid_task.py','Simulator/wksim_runtime/pid-flight-v1.json',
        'Simulator/wksim_control/position_pid.py','Simulator/wksim_control/__init__.py',
        'tools/run_attitude_flight.py','tools/run-attitude-flight.sh','tools/attitude_physics.py',
        'tools/attitude_candidate.py','Simulator/wksim_runtime/attitude_task.py',
        'Simulator/wksim_runtime/attitude-entry-v1.json',
        'Simulator/wksim_runtime/runtime.py','Simulator/wksim_runtime/isolation.py',
        'Simulator/wksim_runtime/task.py','Simulator/wksim_runtime/config.py',
        'Simulator/wksim_runtime/evidence.py','Simulator/wksim_runtime/telemetry_dialect.py',
        'Simulator/wksim_runtime/telemetry-dialects.json',
        'Simulator/wksim_runtime/build_identity.py','Simulator/wksim_core/model.py',
        'Simulator/wksim_core/model.cpp','Simulator/wksim_core/ap_json.py',
        'Simulator/wksim_core/px4_mavlink.py','Simulator/wksim_core/state_stream.py',
        'Simulator/wksim_core/arducopter-quad-x.parm','Simulator/wksim_core/px4-rc.mavlink']
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
        if time.monotonic()-started>360:
            raise TimeoutError('360 second independent PID candidate wall watchdog')
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
            plan=launch_plan(config,directory,admission['library'])
            result['launch_plan']=plan
            # The candidate uses fresh storage: the base GUID_OPTIONS default is
            # zero; preserve it and explicitly add bit 3. Task must read it back.
            if config['stack']=='arducopter':
                (directory/'attitude.parm').write_text(
                    'GUID_OPTIONS 8\nGUID_TIMEOUT 3\nLOG_DISARMED 1\nPSC_ANGLE_MAX 10\n')
                result['experimental_parameters']={
                    'GUID_OPTIONS':8,'GUID_TIMEOUT':3,'LOG_DISARMED':1,'PSC_ANGLE_MAX':10}
                (directory/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
            result['launched_binary_sha256']=digest(plan['fc'][0])
            result['launched_agent_sha256']=digest(plan['agent'][0])
            firmware=admission['identities']['ap' if config['stack']=='arducopter' else 'px4']
            agent=admission['identities']['baseline'][config['stack']+'_agent']
            if (str(Path(plan['fc'][0]).resolve())!=firmware['path']
                    or result['launched_binary_sha256']!=firmware['sha256']
                    or str(Path(plan['agent'][0]).resolve())!=agent['path']
                    or result['launched_agent_sha256']!=agent['sha256']):
                raise ValueError('Actual launch binary/Agent differs from candidate admission')
            control=admission['identities']['control']
            result['actual_control_sha256']={p.name:digest(p) for p in Path(spec.origin).parent.glob('*.py')}
            if result['actual_control_sha256']!=control['installed_python_hashes']:
                raise ValueError('Actual imported control bytes differ from candidate admission')
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
            from Simulator.wksim_runtime.pid_task import PIDTask
            from Simulator.wksim_runtime.task import grounded
            ros=rclpy; ros.init()
            task=PIDTask(directory,health,phase,config['stack'],run_id=config['run_id'],protocol='session_v1',
                pid_config=pid_config)
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
                from attitude_candidate import admit
                post=admit(config['stack'],config['run_id'])
                (directory/'postflight-admission.json').write_text(json.dumps(post,indent=2)+'\n')
                result['candidate_unchanged']=same_identities(admission,post,result['source_sha256'])
            except Exception as error:
                result['candidate_unchanged']=False
                result['postflight_identity_error']=str(error)
            result['wall_seconds']=time.monotonic()-started
            result['stop_kind']='landed_stop' if result['safe_landing'] else 'unsuccessful_isolated_teardown'
            if (result['cleanup_errors'] or not result['children_reaped'] or not result['source_unchanged']
                    or not result['candidate_unchanged']
                    or 'task_close_error' in result or 'ros_close_error' in result):
                result['status']='failed'
            (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            for sig,previous in old.items(): signal.signal(sig,previous)
    print(json.dumps(dict(status=result['status'],result=str(directory/'result.json'))),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack',required=True,choices=('px4','arducopter'))
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--config',required=True,type=Path,help='Exact frozen pid-flight-v1.json; no default controller')
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--prepared',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    from Simulator.wksim_runtime.pid_task import load_config, CONFIG_SHA256
    pid_config=load_config(args.config)
    from attitude_candidate import admit
    admission=admit(args.stack,args.run_id)
    admission['external_pid']=dict(configuration=pid_config,protocol_sha256=CONFIG_SHA256,
        implementation='Simulator.wksim_control.position_pid.PositionPID',
        hover='Must be independently observed and level-validated in this run before PID measurement')
    if admission['ok'] and digest(admission['library']) != pid_config['model']['library_sha256']:
        raise ValueError('PID fixed model library identity differs from candidate admission')
    if not admission['ok'] or args.preflight:
        print(json.dumps(admission,indent=2)); return 0 if admission['ok'] else 2
    if args.output_root is None: raise ValueError('--output-root required for a run')
    if not args.prepared:
        script='set -eo pipefail\n'+''.join('source '+shlex.quote(path)+'\n' for path in admission['setup_files'])
        script+='export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1\n'
        script+='export LD_LIBRARY_PATH=/root/wksim-dds-VxM6Ni/agent-install/lib:${LD_LIBRARY_PATH:-}\n'
        script+='exec '+shlex.join([sys.executable,'-B',str(Path(__file__).resolve()),'--prepared',
            '--stack',args.stack,'--run-id',args.run_id,'--config',str(args.config.resolve()),
            '--output-root',str(args.output_root)])+'\n'
        os.execvp('bash',['bash','-c',script])
    result=run(admission,args.output_root,pid_config,args.config)
    # Observed is deliberately not an audited flight PASS.
    return 0 if result['status']=='observed' else 1


if __name__=='__main__': raise SystemExit(main())
