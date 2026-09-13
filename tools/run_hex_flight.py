"""Reusable independent Hex experiment, raw observations pending independent audit."""
import argparse
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
from tools.hex_candidate import admit, clean_environment, digest, require, native_parameters
from tools.hex_launch_plan import launch_plan as hex_plan
from Simulator.wksim_runtime.isolation import Reservation, check_isolation, resources, isolate_temporary_files
from Simulator.wksim_runtime.runtime import launch_spec, stop_children as stop_runtime_children, truth_summary, udp_listening
from Simulator.wksim_runtime.evidence import write_json
from Simulator.wksim_runtime.hex_task import protocol_for

PROTOCOL = REPO/'Simulator/wksim_runtime/hex-flight-v1.json'


def stop_children(children):
    """Flush the owned physical terminal before FC retirement closes its socket."""
    return stop_runtime_children([row for row in children if row[0] != 'physics']
                                 + [row for row in children if row[0] == 'physics'])


SOURCE_NAMES = ['tools/hex_candidate.py', 'tools/run_hex_flight.py', 'tools/run-hex-flight.sh',
    'tools/hex_physics.py', 'tools/hex_launch_plan.py', 'tools/build_hex_model_candidate.py',
    'Simulator/wksim_runtime/hex_task.py', 'Simulator/wksim_runtime/hex-flight-v1.json',
    'Simulator/wksim_runtime/runtime.py', 'Simulator/wksim_runtime/isolation.py',
    'Simulator/wksim_runtime/task.py', 'Simulator/wksim_runtime/evidence.py',
    'Simulator/wksim_runtime/telemetry_dialect.py', 'Simulator/wksim_runtime/telemetry-dialects.json',
    'Simulator/wksim_core/model.py', 'Simulator/wksim_core/model.cpp',
    'Simulator/wksim_core/ap_json.py', 'Simulator/wksim_core/px4_mavlink.py',
    'Simulator/wksim_core/state_stream.py', 'Simulator/wksim_core/px4-rc.mavlink']


def launch_plan(config, directory, library):
    require(config['model_profile'] == 'hex_x', 'Explicit Hex model profile required')
    plan = launch_spec(config, directory, library)
    ap = config['stack'] == 'arducopter'
    if ap:
        plan['fc'][plan['fc'].index('--speedup')+1] = '1'
        plan['fc'][plan['fc'].index('--defaults')+1] = ','.join(map(str, [
            Path(config['ap_candidate'])/'src/Tools/autotest/default_params/copter.parm',
            directory/'hex.parm', directory/'dds.parm']))
    else:
        # Remove every original quad/unsupported override before applying Hex.
        env = {k:v for k,v in plan['fc_environment'].items() if not k.startswith('PX4_PARAM_')}
        env.update(hex_plan()['px4_environment'])
        env.update({'PX4_PARAM_'+k:str(v) for k,v in native_parameters('px4').items()})
        plan['fc_environment'] = env
    plan['physics'] = ['/usr/bin/python3', '-B', str(REPO/'tools/hex_physics.py'),
        '--stack', config['stack'], '--library', str(library), '--config', config['hex_config'],
        '--port', '19002' if ap else '4581', '--trace', str(directory/'truth.jsonl'),
        '--raw', str(directory/'physics-1ms.jsonl'), '--run-id', config['run_id']]
    return plan


def process_identity(pid):
    """Linux PID plus boot/starttime; argv/cwd prove which lifetime was owned."""
    root = Path('/proc')/str(pid)
    stat = (root/'stat').read_text()
    return dict(pid=pid, boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        starttime_ticks=int(stat[stat.rfind(')')+2:].split()[19]),
        argv=(root/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0'),
        cwd=os.readlink(root/'cwd'), executable=os.readlink(root/'exe'))


def prior_result(path, admission):
    """Read-only cold reset: never signal, rewrite, or revive a prior experiment."""
    if path is None:
        return None
    path = Path(path).resolve(strict=True)
    previous = json.loads(path.read_text())
    require(previous.get('model_profile') == 'hex_x' and previous.get('status') == 'observed'
        and previous.get('safe_landing') is True and previous.get('children_reaped') is True
        and previous.get('cleanup_errors') == [] and previous.get('processes_absent_after_stop') is True,
        'Cold reset requires a completed, safely landed, reaped previous Hex observation')
    require(previous['admission']['configuration_identity'] == admission['configuration_identity']
        and previous['run_id'] != admission['config']['run_id'], 'Cold reset requires same config and a new run id')
    selected, _ = protocol_for(admission['config']['stack'])
    require(previous.get('protocol_sha256') == digest(selected), 'Cold reset protocol identity differs')
    require('supervisor' in previous, 'Missing previous supervisor identity')
    owners = list(previous['children'].values())+[dict(pid=previous['supervisor']['pid'],
                returncode=0, identity=previous['supervisor'])]
    for child in owners:
        require(child.get('returncode') is not None and 'identity' in child, 'Missing old process retirement identity')
        try:
            now = process_identity(child['pid'])
        except FileNotFoundError:
            continue
        old = child['identity']
        require((now['boot_id'], now['starttime_ticks']) != (old['boot_id'], old['starttime_ticks']),
                'Prior owned process is still alive; reset refuses to kill it')
    return dict(path=str(path), sha256=digest(path), run_id=previous['run_id'],
        control_epoch=previous['task']['control_epoch'], children=previous['children'],
        configuration_identity=admission['configuration_identity'], semantics='cold rebuild from terminal result')


def initial_model(path):
    with Path(path).open() as stream:
        start = json.loads(next(stream))
        require(start['kind'] == 'start' and start['dt_s'] == .001, 'Missing initial Hex raw identity')
        initialized = json.loads(next(stream))
        require(initialized['kind'] == 'initialized' and initialized['initial_tick'] == 0,
                'Fresh Hex model must initialize at tick zero')
    return initialized


def run(admission, output, parent=None):
    check_isolation()
    require(admission['ok'], 'Hex admission failed')
    require(all(os.environ.get(k) == v for k,v in dict(ROS_DOMAIN_ID='77', ROS_LOCALHOST_ONLY='1',
        RMW_IMPLEMENTATION='rmw_fastrtps_cpp').items()), 'Requires private domain77/FastDDS/localhost')
    require(not any(k.startswith('PX4_PARAM_') for k in os.environ), 'Inherited PX4 parameter overrides forbidden')
    require(not output.exists() and output.parent == Path('/root') and output.name.startswith('wksim-hex-flight-'),
            'Use a fresh /root/wksim-hex-flight-* output directory')
    config = admission['config']
    parent_record = prior_result(parent, admission)
    output.mkdir(mode=0o700)
    directory = output/config['run_id']
    directory.mkdir(mode=0o700)
    resource = resources(config, directory)
    selected, protocol_sha = protocol_for(config['stack'])
    budget = json.loads(selected.read_text())
    require(digest(selected) == protocol_sha, 'Frozen Hex protocol differs before launch')
    source_names = [selected.relative_to(REPO).as_posix() if name == PROTOCOL.relative_to(REPO).as_posix() else name
                    for name in SOURCE_NAMES]
    result = dict(status='failed', model_profile='hex_x', experimental=True, production_admitted=False,
        stack=config['stack'], run_id=config['run_id'], config=config, run_dir=str(directory),
        admission=admission, children={}, phases=[], safe_landing=False, resources=resource,
        supervisor=process_identity(os.getpid()),
        cold_reset_from=parent_record, protocol=budget, protocol_sha256=protocol_sha,
        scope='Source-template Hex public position task; all flight claims pending independent raw audit')
    for name,value in [('admission', admission), ('config', config), ('isolation', resource), ('protocol', budget)]:
        (directory/(name+'.json')).write_text(json.dumps(value, indent=2)+'\n')
    result['source_sha256'] = {name:digest(REPO/name) for name in source_names}
    for name in source_names:
        target = directory/'run-source'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    children, task, ros = [], None, None
    started = time.monotonic()
    def phase(name):
        result['phases'].append(dict(phase=name, wall_s=time.monotonic()-started))
        print(name, flush=True)
    def health():
        if time.monotonic()-started > budget['wall_watchdog_s']:
            raise TimeoutError('Frozen 300 second Hex watchdog')
        for name, child, _ in children:
            if child.poll() is not None:
                raise RuntimeError(f'{name} exited: {child.returncode}')
    def wait(label, predicate, seconds=30):
        end = time.monotonic()+seconds
        while not predicate():
            health()
            if time.monotonic() > end:
                raise TimeoutError(label)
            time.sleep(.02)
        phase(label)
    def interrupt(signum, frame):
        raise InterruptedError(f'Interrupted by signal {signum}')
    old = {sig:signal.signal(sig, interrupt) for sig in (signal.SIGTERM, signal.SIGINT)}
    with Reservation(resource) as reservation:
        def launch(name, argv, env=None):
            log = (directory/(name+'.log')).open('x')
            try:
                child = subprocess.Popen(argv, cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True, pass_fds=tuple(reservation.fds))
            except BaseException:
                log.close()
                raise
            children.append((name, child, log))
            result['children'][name] = dict(argv=argv, cwd=str(directory), pid=child.pid, pgid=child.pid,
                                           identity=process_identity(child.pid))
        try:
            result['private_temporary_files'] = isolate_temporary_files()
            spec = importlib.util.find_spec('prometheus_control')
            fixed = admission['identities']['baseline']
            from Simulator.wksim_runtime import joint_profile
            for name, pin in fixed['message_packages'].items():
                joint_profile._overlay(name, pin['prefix'])
            require(spec is not None and spec.origin is not None
                    and str(Path(spec.origin).resolve().parent) == fixed['sealed_control_package'],
                    'Actual Control import is not the sealed original package')
            result['actual_control_sha256'] = {p.name:digest(p) for p in Path(spec.origin).parent.glob('*.py')}
            require(result['actual_control_sha256'] == fixed['sealed_control']['python_sha256'],
                    'Actual Control bytes differ from fixed original')
            plan = launch_plan(config, directory, admission['library'])
            result['launch_plan'] = plan
            if config['stack'] == 'arducopter':
                (directory/'hex.parm').write_text(hex_plan(config['stack'])['ap_parameter_file']+'LOG_DISARMED 1\n')
                (directory/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
            firmware = fixed['ap' if config['stack'] == 'arducopter' else 'px4']
            agent = fixed[config['stack']+'_agent']
            require(str(Path(plan['fc'][0]).resolve()) == firmware['path'] and digest(plan['fc'][0]) == firmware['sha256'],
                    'Actual FC differs from fixed resource admission')
            require(str(Path(plan['agent'][0]).resolve()) == agent['path'] and digest(plan['agent'][0]) == agent['sha256'],
                    'Actual Agent differs from fixed resource admission')
            for port in resource['ports']:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if port['protocol'] == 'udp' else socket.SOCK_STREAM) as sock:
                    sock.bind(('127.0.0.1', port['port']))
            launch('physics', plan['physics'])
            wait('physics_listening', lambda: '"ready": true' in (directory/'physics.log').read_text())
            launch('agent', plan['agent'])
            wait('agent_listening', lambda: udp_listening(12019 if config['stack'] == 'arducopter' else 18888))
            launch('fc', plan['fc'], dict(os.environ, **plan['fc_environment']))
            wait('physics_fc_coupled', lambda: (directory/'truth.jsonl').exists() and (directory/'truth.jsonl').stat().st_size > 0)
            launch('control', plan['control'])
            import rclpy
            from Simulator.wksim_runtime.hex_task import HexTask
            ros = rclpy
            ros.init()
            task = HexTask(directory, health, phase, config['stack'], run_id=config['run_id'], protocol='session_v1',
                parameters=admission['parameters'], parameter_types=admission['parameter_types'],
                protocol_sha256=result['protocol_sha256'])
            for name, child, _ in children:
                (directory/(name+'.maps')).write_bytes(Path(f'/proc/{child.pid}/maps').read_bytes())
            task.execute()
            health()
            require(task.ground_current(), 'Public and physical ground required for normal stop')
            if parent_record:
                require(task.epoch != parent_record['control_epoch'], 'Cold reset reused prior control epoch')
            result.update(status='observed', safe_landing=True, truth=truth_summary(directory/'truth.jsonl'))
            phase('landed_stop')
        except (Exception, KeyboardInterrupt) as error:
            result['error'] = f'{type(error).__name__}: {error}'
        finally:
            for sig in old:
                signal.signal(sig, signal.SIG_IGN)
            if task is not None:
                try:
                    result['task'] = task.report()
                    task.close()
                except Exception as error:
                    result['task_close_error'] = str(error)
            if ros is not None and ros.ok():
                try:
                    ros.shutdown()
                except Exception as error:
                    result['ros_close_error'] = str(error)
            result['cleanup_errors'] = stop_children(children)
            for name, child, _ in children:
                result['children'][name]['returncode'] = child.poll()
            result['children_reaped'] = all(child.poll() is not None for _, child, _ in children)
            result['processes_absent_after_stop'] = all(not Path(f'/proc/{child.pid}').exists() for _, child, _ in children)
            result['source_unchanged'] = all(digest(REPO/name) == value for name,value in result['source_sha256'].items())
            try:
                post = admit(config['stack'], config['run_id'])
                (directory/'postflight-admission.json').write_text(json.dumps(post, indent=2)+'\n')
                result['candidate_unchanged'] = post['ok'] and post['identities'] == admission['identities']
            except Exception as error:
                result['candidate_unchanged'] = False
                result['postflight_identity_error'] = str(error)
            result['raw_native_logs'] = {str(p.relative_to(directory)):dict(sha256=digest(p), size=p.stat().st_size)
                for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in ('.bin', '.ulg')}
            try:
                result['model_initialization'] = initial_model(directory/'physics-1ms.jsonl')
            except (OSError, ValueError, KeyError, StopIteration) as error:
                result['status'] = 'failed'
                result['model_initialization_error'] = str(error)
            result['wall_seconds'] = time.monotonic()-started
            result['stop_kind'] = 'landed_stop' if result['safe_landing'] else 'unsuccessful_isolated_teardown'
            if (result['cleanup_errors'] or not result['children_reaped'] or not result['processes_absent_after_stop']
                    or not result['source_unchanged'] or not result['candidate_unchanged'] or not result['raw_native_logs']
                    or 'task_close_error' in result or 'ros_close_error' in result):
                result['status'] = 'failed'
            if parent_record:
                result['parent_unchanged'] = digest(parent_record['path']) == parent_record['sha256']
                if not result['parent_unchanged']:
                    result['status'] = 'failed'
            # Optional unsupported UAVState fields may be NaN. Preserve them as
            # explicit nonfinite markers; required physical/control fields were
            # already checked, and original wire bytes remain untouched.
            write_json(directory/'result.json', result)
            for sig, previous in old.items():
                signal.signal(sig, previous)
    print(json.dumps(dict(status=result['status'], result=str(directory/'result.json'))), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', required=True, choices=('px4', 'arducopter'))
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--cold-reset-from', type=Path)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--prepared', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    admission = admit(args.stack, args.run_id)
    if not admission['ok'] or args.preflight:
        if admission['ok'] and args.cold_reset_from:
            admission['cold_reset_from'] = prior_result(args.cold_reset_from, admission)
        print(json.dumps(admission, indent=2))
        return 0 if admission['ok'] else 2
    require(args.output_root is not None, '--output-root required')
    if not args.prepared:
        script = 'set -eo pipefail\n'+''.join('source '+shlex.quote(p)+'\n' for p in admission['setup_files'])
        script += 'export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp PYTHONDONTWRITEBYTECODE=1\n'
        script += 'export LD_LIBRARY_PATH=/root/wksim-dds-VxM6Ni/agent-install/lib:${LD_LIBRARY_PATH:-}\n'
        argv = ['/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--prepared', '--stack', args.stack,
                '--run-id', args.run_id, '--output-root', str(args.output_root)]
        if args.cold_reset_from:
            argv += ['--cold-reset-from', str(args.cold_reset_from)]
        script += 'exec '+shlex.join(argv)+'\n'
        os.execve('/bin/bash', ['bash', '--noprofile', '--norc', '-c', script], clean_environment())
    return 0 if run(admission, args.output_root, args.cold_reset_from)['status'] == 'observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
