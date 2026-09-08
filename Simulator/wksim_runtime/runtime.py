"""Product entry for one isolated, independently clocked quad-X SITL experiment."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

from .config import load_config, validate_config
from .preflight import preflight
from .isolation import Reservation, resources, check_isolation, isolate_temporary_files

REPO = Path(__file__).resolve().parents[2]
AP_SHA256 = '98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5'
PX4_SHA256 = '987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd'


def digest(path):
    with Path(path).open('rb') as source:
        value = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def launch_spec(config, directory, library, *, fc_directory=None, physics_duration=600):
    """Pinned launch semantics; no subprocesses or filesystem writes here."""
    ap = config['stack'] == 'arducopter'
    dds, px4 = Path(config['dds_workspace']), Path(config['px4_root'])
    core = REPO / 'Simulator/wksim_core'
    agent = dds / ('ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent' if ap else 'agent-install/bin/MicroXRCEAgent')
    physics = [sys.executable, '-m', 'Simulator.wksim_core.' + ('ap_json' if ap else 'px4_mavlink'),
               '--library', str(library), '--port', '19002' if ap else '4581',
               '--trace', str(directory / 'truth.jsonl')]
    if type(physics_duration) is not int or not 600 <= physics_duration <= 3600:
        raise ValueError('Explicit physics duration must be an integer from 600 to 3600 simulation seconds')
    physics += ['--run-until-stopped'] if config.get('mission') else ['--duration', str(physics_duration)]
    if config.get('display_socket'):
        physics += ['--state-socket', config['display_socket'], '--run-id', config['run_id'],
                    '--vehicle-id', str(config['vehicle_id'])]
    control = [sys.executable, '-m', 'prometheus_control.node', '--ros-args',
               '-p', 'flight_stack:=' + config['stack'], '-p', 'uav_id:=1',
               '-p', 'native_prefix:=' + ('/ap' if ap else '/wksim_px4_21'),
               '-p', 'native_system_id:=22', '-p', 'arducopter_position_yaw:=true']
    if config.get('control_protocol', 'legacy_v1') == 'session_v1':
        control += ['-p', 'run_id:=' + config['run_id']]
    overrides = {}
    if ap:
        candidate = Path(config['ap_candidate'])
        binary = candidate / 'build/sitl/bin/arducopter'
        defaults_files = [candidate / 'src/Tools/autotest/default_params/copter.parm',
                          core / 'arducopter-quad-x.parm']
        if config.get('telemetry_socket'):
            defaults_files.append(Path(__file__).with_name('arducopter-telemetry.parm'))
        # 1511f271 AP_Param overwrites done_all_default_params for each file.
        # Keep late-created DDS defaults LAST so dynamic-subtree reload is not
        # suppressed by an earlier fully resolved GCS stream-rate file.
        defaults_files.append(directory / 'dds.parm')
        defaults = ','.join(map(str, defaults_files))
        fc = [str(binary), '--model', 'JSON:127.0.0.1', '--rate', '1000', '--speedup', '3',
              '--base-port', '16600', '--instance', '11', '--sysid', '241', '--sim-address', '127.0.0.1',
              '--sim-port-out', '19002', '--sim-port-in', '19003', '--rc-in-port', '19004',
              '--serial0', 'udpclient:127.0.0.1:14660', '--serial1', 'none', '--serial2', 'none',
              '--defaults', defaults, '--home', '40.1540302,116.2593683,50,0']
    else:
        binary = px4 / 'build/px4_sitl_default/bin/px4'
        fc = [str(binary), '-d', str(px4 / 'build/px4_sitl_default/etc'),
              '-t', str(px4/'test_data'), '-i', '21', '-w', str(fc_directory or directory)]
        overrides = dict(PX4_SYS_AUTOSTART='10016', PX4_SIM_MODEL='none_iris', PX4_SIM_HOST_ADDR='127.0.0.1',
                         PX4_SIM_SPEED_FACTOR='3', PX4_UXRCE_DDS_PORT='18888', PX4_UXRCE_DDS_NS='wksim_px4_21',
                         ROS_DOMAIN_ID='77', WKSIM_MAVLINK_LOCAL_PORT='18591', WKSIM_MAVLINK_REMOTE_PORT='14661',
                         PX4_PARAM_SIM_GZ_EN='0', PX4_PARAM_SIM_BAT_ENABLE='1', PX4_PARAM_UXRCE_DDS_SYNCT='0')
        arm = 0.225 / math.sqrt(2)
        for rotor, (x, y) in enumerate(((arm, arm), (-arm, -arm), (arm, -arm), (-arm, arm))):
            overrides[f'PX4_PARAM_CA_ROTOR{rotor}_PX'] = str(x)
            overrides[f'PX4_PARAM_CA_ROTOR{rotor}_PY'] = str(y)
            overrides[f'PX4_PARAM_CA_ROTOR{rotor}_KM'] = str((1 if rotor < 2 else -1) * 2.783e-7 / 1.681e-5)
        overrides['PATH'] = str(core) + os.pathsep + str(binary.parent) + os.pathsep + os.environ.get('PATH', '')
    result = dict(agent=[str(agent), 'udp4', '-p', '12019' if ap else '18888', '-v', '4'],
                  physics=physics, fc=fc, control=control, fc_environment=overrides)
    if fc_directory is not None:
        result['fc_cwd'] = str(fc_directory)
    return result


def stop_children(children):
    """Only groups created with start_new_session=True; also reap orphan descendants."""
    errors = []
    for name, child, log in reversed(children):
        try:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            # The group leader can exit before its children. Kill remaining members.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            errors.append(f'{name}: {error}')
        finally:
            log.close()
    return errors


def truth_summary(path):
    maximum, nearest, final, count = -math.inf, math.inf, None, 0
    with path.open(encoding='utf-8') as source:
        for line in source:
            if not line.endswith('\n'):
                break  # An interrupted trace can end with a partial record.
            record = json.loads(line)
            position = record['vehicle'][6:9]
            if len(position) != 3 or not all(math.isfinite(v) for v in position):
                raise ValueError('Invalid physical truth')
            maximum = max(maximum, -position[2])
            nearest = min(nearest, math.dist(position, [3, 2, -3]))
            final, count = record, count + 1
    if final is None:
        raise RuntimeError('Missing physical truth')
    return dict(records=count, max_height_m=maximum, min_waypoint_error_m=nearest,
                final_height_m=-final['vehicle'][8], final_time=final['time'])


def udp_listening(port):
    # Read kernel state, without sending anything to the Agent's protocol socket.
    with Path('/proc/net/udp').open() as source:
        return any(line.split()[1].endswith(f':{port:04X}') for line in list(source)[1:])


def parameter_storage_metadata(config, storage):
    """Validate a borrowed lease; resource admission still runs independently."""
    from .parameter_storage import ParameterStorage
    if (not isinstance(storage, ParameterStorage) or config.get('kind') == 'joint_scene'
            or config.get('runtime_profile') != 'independent_quad_dds_v1'
            or config.get('control_protocol') != 'session_v1'
            or any(config.get(key) for key in ('mission', 'display_socket', 'telemetry_socket',
                'gcs_udp_forward', 'restart_control_on_ground', 'promotion_flight'))):
        raise ValueError('Retained parameter storage requires an explicit independent maintenance session')
    metadata = storage.check(config['stack'], px4_root=config['px4_root'] if config['stack'] == 'px4' else None)
    lease, directory = os.fstat(storage.fd), storage.path.stat()
    metadata['directory_identity'] = dict(lease_device=lease.st_dev, lease_inode=lease.st_ino,
                                        storage_device=directory.st_dev, storage_inode=directory.st_ino)
    names = ('eeprom.bin',) if config['stack'] == 'arducopter' else ('parameters.bson', 'parameters_backup.bson')
    metadata['parameter_files'] = {name: dict(sha256=digest(storage.path/name), size=(storage.path/name).stat().st_size)
                                   for name in names if (storage.path/name).is_file()}
    return metadata


def run(config, output_root, *, task_factory=None, use_prepared_run=None, parameter_storage=None, physics_duration=None):
    config = validate_config(config)
    if physics_duration is not None:
        if (type(physics_duration) is not int or not 600 <= physics_duration <= 3600 or task_factory is None
                or use_prepared_run is not None or config.get('kind')=='joint_scene' or config.get('mission')):
            raise ValueError('Extended physics duration requires an explicit independent task and 600..3600 simulation seconds')
    if parameter_storage is not None:
        if task_factory is None or use_prepared_run is not None:
            raise ValueError('Retained parameter storage requires an explicit maintenance task')
        parameter_storage_metadata(config, parameter_storage)
    if config.get('kind')=='joint_scene':
        if task_factory is not None:
            raise ValueError('Joint product entry does not accept a replacement task factory')
        from .joint_runtime import run_joint
        if use_prepared_run is not None:
            return run_joint(config,output_root,use_prepared_run=use_prepared_run)
        return run_joint(config,output_root)
    if use_prepared_run is not None:
        raise ValueError("Prepared runs require joint_scene")
    if sys.platform != 'linux' or os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
        raise RuntimeError('Use run-wksim.sh: a private Linux network namespace is required')
    check_isolation()
    directory = Path(output_root).resolve() / config['run_id']
    resource = resources(config, directory)
    with Reservation(resource) as reservation:
        options = {'parameter_storage': parameter_storage} if parameter_storage is not None else {}
        if physics_duration is not None:
            options['physics_duration']=physics_duration
        return _run_reserved(config, output_root, resource, reservation, task_factory, **options)


def _run_reserved(config, output_root, resource, reservation, task_factory=None, *, parameter_storage=None, physics_duration=600):
    if any(os.environ.get(k) != v for k, v in dict(ROS_DOMAIN_ID='77', ROS_LOCALHOST_ONLY='1',
                                                  RMW_IMPLEMENTATION='rmw_fastrtps_cpp').items()):
        raise RuntimeError('Requires isolated ROS domain77/FastDDS/localhost environment')
    directory = Path(output_root).resolve() / config['run_id']
    directory.mkdir(parents=True, exist_ok=False)
    result = dict(status='failed', config=config, run_dir=str(directory), phases=[], children={},
                  run_id=config['run_id'], vehicle_id=config['vehicle_id'], stack=config['stack'],
                  safe_landing=False, scope='one independent SITL experiment; public Prometheus task',
                  network_namespace=os.readlink('/proc/self/ns/net'))
    result['resources'] = resource
    result['started_unix'] = time.time()
    if physics_duration != 600:
        result['physics_duration_s']=physics_duration
    (directory / 'isolation.json').write_text(json.dumps(resource, indent=2) + '\n', encoding='utf-8')
    (directory / 'config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    children, task, ros = [], None, None
    storage_fds = ()
    expected_exits = set()
    optional_children = set()
    started = time.monotonic()
    wall_budget = 180 + 45 * len(config.get('mission', {}).get('waypoints', []))
    def phase(name):
        result['phases'].append(dict(phase=name, wall_seconds=time.monotonic() - started))
        print(name, flush=True)
    def health():
        operator_wait = getattr(task, 'operator_wait_seconds', 0.0)
        if time.monotonic() - started - operator_wait > wall_budget:
            raise TimeoutError(f'{wall_budget} second active-wall watchdog (operator wait excluded)')
        for name, child, _ in children:
            if child.poll() is not None and child.pid not in expected_exits:
                if child.pid in optional_children:
                    result['telemetry']['observer_exit'] = child.returncode
                    continue
                raise RuntimeError(f'{name} exited: {child.returncode}')
    def wait(label, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            health()
            if predicate():
                phase(label)
                return
            if time.monotonic() >= deadline:
                raise TimeoutError(label)
            time.sleep(0.02)
    def launch(name, argv, env=None, cwd=None):
        log = (directory / (name + '.log')).open('x', encoding='utf-8')
        try:
            child = subprocess.Popen(argv, cwd=cwd or directory, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True,
                                     pass_fds=tuple(reservation.fds) + storage_fds)
        except BaseException:
            log.close()
            raise
        children.append((name, child, log))
        result['children'][name] = dict(argv=argv, pid=child.pid, pgid=child.pid, log=str(directory / (name + '.log')))
        if parameter_storage is not None:
            result['children'][name].update(cwd=str(cwd or directory), parameter_storage_fd=parameter_storage.fd)
        return child
    def restart_control():
        health()
        truth = truth_summary(directory / 'truth.jsonl')
        if (task is None or not task.fresh() or not grounded(task.state)
                or abs(truth['final_height_m']) >= 0.3
                or time.time() - (directory / 'truth.jsonl').stat().st_mtime > 2):
            raise RuntimeError('Control restart requires fresh public and physical disarmed ground evidence')
        old = next(item for item in children if item[0] == 'control')
        errors = stop_children([old])
        if errors:
            raise RuntimeError('Control retirement failed: ' + str(errors))
        expected_exits.add(old[1].pid)
        new = launch('control-restarted', plan['control'])
        phase('control_restarted_on_ground')
        return dict(old_pid=old[1].pid, new_pid=new.pid, old_returncode=old[1].poll(),
                    physics_pid=result['children']['physics']['pid'], fc_pid=result['children']['fc']['pid'],
                    model_time_before=truth['final_time'],
                    scope='explicit pre-arm ground restart; physics and FC are not restarted')
    def interrupted(signum, frame):
        raise InterruptedError(f'Interrupted by signal {signum}; no airborne stop policy selected')
    old_signals = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if parameter_storage is not None:
            result['parameter_storage_before'] = parameter_storage_metadata(config, parameter_storage)
            storage_fds = (parameter_storage.fd,)
        result['preflight'] = preflight(config)
        if not result['preflight']['ok']:
            raise RuntimeError('Preflight rejected: ' + json.dumps(result['preflight']['reasons']))
        result['private_temporary_files']=isolate_temporary_files(
            config[key] for key in ('display_socket','telemetry_socket') if config.get(key))
        config = result['preflight']['config']
        result['config'] = config
        (directory / 'config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
        phase('preflight_admitted')
        # Import/resolve the installed node before starting any FC, never a source-tree substitute.
        spec = importlib.util.find_spec('prometheus_control')
        install = Path(config['prometheus_workspace']).resolve() / 'install'
        if spec is None or spec.origin is None or not Path(spec.origin).resolve().is_relative_to(install):
            raise RuntimeError('prometheus_control must resolve inside the selected installed workspace')
        package = Path(spec.origin).resolve().parent
        result['product_sha256'] = {p.name: digest(p) for p in package.glob('*.py')}
        library = Path(result['preflight']['identities']['model_library']['path'])
        if library.resolve() != Path(config['model_library']).resolve():
            raise RuntimeError('Preflight model path identity disagrees with normalized configuration')
        result['model_build'] = result['preflight']['identities']['model_build']
        phase('model_identity_checked')
        options = {'fc_directory': parameter_storage.path} if parameter_storage is not None else {}
        if physics_duration != 600:
            options['physics_duration']=physics_duration
        plan = launch_spec(config, directory, library, **options)
        binary = Path(plan['fc'][0])
        result['fc_binary'], result['fc_sha256'] = str(binary), digest(binary)
        expected = (result['preflight']['identities']['firmware']['expected_sha256'] if config.get('runtime_profile')
                    else AP_SHA256 if config['stack'] == 'arducopter' else PX4_SHA256)
        if result['fc_sha256'] != expected:
            raise RuntimeError('FC binary differs from the pinned flown baseline')
        result['agent_sha256'] = digest(plan['agent'][0])
        result['fc_commit'] = result['preflight']['identities']['firmware_commit']
        result['runtime_sha256'] = {str(p.relative_to(REPO)): digest(p) for p in
                                   (Path(__file__), Path(__file__).with_name('isolation.py'), Path(__file__).with_name('task.py'),
                                    Path(__file__).with_name('config.py'), Path(__file__).with_name('preflight.py'),
                                    REPO / 'tools/run-wksim.sh', REPO / 'Simulator/wksim_core/model.py',
                                    REPO / 'Simulator/wksim_core/model.cpp', REPO / 'Simulator/wksim_core/state_stream.py',
                                    REPO / 'Simulator/wksim_core' / ('ap_json.py' if config['stack'] == 'arducopter' else 'px4_mavlink.py'),
                                    REPO / 'Simulator/wksim_core' / ('arducopter-quad-x.parm' if config['stack'] == 'arducopter' else 'px4-rc.mavlink'))}
        if parameter_storage is not None:
            source = Path(__file__).with_name('parameter_storage.py')
            result['runtime_sha256'][str(source.relative_to(REPO))] = digest(source)
        if config.get('runtime_profile'):
            for name in ('independent_profile.py','independent-profile-evidence.json','joint_profile.py','joint-profiles.json','build_identity.py'):
                source=Path(__file__).with_name(name)
                result['runtime_sha256'][str(source.relative_to(REPO))]=digest(source)
        if config.get('mission'):
            for name in ('mission_task.py', 'mission_plan.py', 'mission_cancel.py', 'mission_actions.py', 'mission_evidence.py'):
                source = Path(__file__).with_name(name)
                result['runtime_sha256'][str(source.relative_to(REPO))] = digest(source)
        if config.get('telemetry_socket'):
            for name in ('telemetry.py', 'telemetry_dialect.py', 'telemetry-dialects.json', 'arducopter-telemetry.parm'):
                source = Path(__file__).with_name(name)
                result['runtime_sha256'][str(source.relative_to(REPO))] = digest(source)
        result['fc_environment'] = plan['fc_environment']
        ap = config['stack'] == 'arducopter'
        ports = [(socket.SOCK_DGRAM, p) for p in ((12019, 19002, 19003, 19004, 14660) if ap else (18888, 18591, 14661))]
        if not ap:
            ports.append((socket.SOCK_STREAM, 4581))
        for kind, port in ports:
            with socket.socket(socket.AF_INET, kind) as probe:
                probe.bind(('127.0.0.1', port))
        if ap:
            (directory / 'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n', encoding='utf-8')
        phase('resources_checked')
        if config.get('telemetry_socket'):
            Path(config['telemetry_socket']).parent.mkdir(mode=0o700, exist_ok=True)
            result['telemetry'] = dict(policy='observe_only_v1', control_path=False)
            child = launch('telemetry', [sys.executable, '-m', 'Simulator.wksim_runtime.telemetry',
                                         str(directory / 'config.json')])
            # A selected but invalid observer fails before the FC starts. Once
            # ready it is optional: its failure must not govern physics/control.
            wait('telemetry_listening', lambda: '"ready": true' in (directory / 'telemetry.log').read_text())
            optional_children.add(child.pid)
        if config.get('display_socket'):
            # The display consumer may already be bound; physics send failures are nonblocking.
            Path(config['display_socket']).parent.mkdir(mode=0o700, exist_ok=True)
        launch('physics', plan['physics'])
        wait('physics_listening', lambda: '"ready": true' in (directory / 'physics.log').read_text())
        launch('agent', plan['agent'])
        wait('agent_listening', lambda: udp_listening(12019 if ap else 18888))
        if parameter_storage is not None:
            parameter_storage_metadata(config, parameter_storage)
        launch('fc', plan['fc'], dict(os.environ, **plan['fc_environment']), cwd=plan.get('fc_cwd'))
        wait('physics_fc_coupled', lambda: (directory / 'truth.jsonl').exists() and
             (directory / 'truth.jsonl').stat().st_size > 0, 30)
        launch('control', plan['control'])
        import rclpy
        from .task import Task, grounded
        ros = rclpy
        ros.init()
        mission_options = {}
        default_task = Task
        if config.get('mission'):
            from .mission_task import MissionTask
            default_task = MissionTask
            mission_options = dict(mission=config['mission'], truth_cursor=lambda: truth_summary(directory / 'truth.jsonl'))
        task = (task_factory or default_task)(directory, health, phase, config['stack'], run_id=config['run_id'],
                    protocol=config.get('control_protocol', 'legacy_v1'),
                    restart_control=restart_control if config.get('restart_control_on_ground') else None, **mission_options)
        task.execute()
        health()
        truth = truth_summary(directory / 'truth.jsonl')
        if (not task.fresh() or not grounded(task.state) or abs(truth['final_height_m']) >= 0.3
                or time.time() - (directory / 'truth.jsonl').stat().st_mtime > 2):
            raise RuntimeError('Normal stop requires disarmed public state and corroborating physical ground truth')
        if config.get('mission'):
            from .mission_evidence import audit_mission_truth
            result['mission_truth'] = audit_mission_truth(directory / 'truth.jsonl', task.report()['mission'])
        elif truth['max_height_m'] < 2.5 or truth['min_waypoint_error_m'] > 0.5:
            raise RuntimeError('Single-waypoint physical integration gate failed')
        result['safe_landing'], result['status'], result['truth'] = True, 'pass', truth
        if config.get('mission') and task.mission_state == 'cancelled':
            result['status'] = 'cancelled'
        phase('landed_stop')
    except (Exception, KeyboardInterrupt) as error:
        result['error'] = str(error)
        if config.get('mission') and task is not None and task.mission_state != 'failed':
            task.fail(str(error))
    finally:
        # A second terminal signal must not interrupt the owned-child cleanup.
        for sig in old_signals:
            signal.signal(sig, signal.SIG_IGN)
        errors = []
        if task is not None:
            try:
                result['task'] = task.report()
                task.close()
            except Exception as error:
                errors.append(f'task: {error}')
        if ros is not None and ros.ok():
            try:
                ros.shutdown()
            except Exception as error:
                errors.append(f'ROS: {error}')
        errors.extend(stop_children([item for item in children if item[1].pid not in expected_exits]))
        result['cleanup_errors'] = errors
        result['children_reaped'] = all(child.poll() is not None for _, child, _ in children)
        if parameter_storage is not None:
            try:
                result['parameter_storage_after'] = parameter_storage_metadata(config, parameter_storage)
            except Exception as error:
                errors.append('parameter storage: ' + str(error))
        result['stop_kind'] = 'landed_stop' if result['safe_landing'] else 'unsuccessful_isolated_teardown'
        if errors or not result['children_reaped']:
            result['status'] = 'failed'
        result['wall_seconds'] = time.monotonic() - started
        result['operator_wait_seconds'] = getattr(task, 'operator_wait_seconds', 0.0)
        result['active_wall_seconds'] = result['wall_seconds'] - result['operator_wait_seconds']
        result['finished_unix'] = time.time()
        for name, child, _ in children:
            result['children'][name]['returncode'] = child.poll()
            if name == 'telemetry':
                result['telemetry']['returncode'] = child.poll()
                # Optional observer diagnostics never turn a successful landing
                # into failure. A missing final report is explicit, not success.
                result['telemetry']['final_report'] = None
                for line in (directory / 'telemetry.log').read_text().splitlines():
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict) and 'counters' in record:
                        result['telemetry']['final_report'] = record
        (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        for sig, previous in old_signals.items():
            signal.signal(sig, previous)
        print(json.dumps(dict(status=result['status'], result=str(directory / 'result.json'))), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--output-root', type=Path, default=REPO / 'validation/runs')
    parser.add_argument('--prepared', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--preflight',action='store_true',help='Verify configuration/resources without launching flight processes')
    lifecycle=parser.add_mutually_exclusive_group()
    lifecycle.add_argument('--prepare-run',action='store_true',help='Prepare a joint run identity without launching physics')
    lifecycle.add_argument('--use-prepared-run',type=Path,help='Consume this prepared joint run directory once')
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.prepare_run or args.use_prepared_run is not None:
            if config.get('kind')!='joint_scene' or args.preflight:
                raise ValueError('Preparation flags require joint_scene and cannot combine with --preflight')
            from .joint_runtime import _joint_directory
            _joint_directory(args.output_root,config['run_id'])
        if args.prepare_run:
            from .joint_runtime import prepare_joint
            print(json.dumps(prepare_joint(config,args.output_root),allow_nan=False),flush=True)
            return 0
        if not args.prepared:
            if config.get('kind')=='joint_scene' or config.get('runtime_profile'):
                if config.get('kind')=='joint_scene':
                    from .joint_profile import select_profile
                    profile=select_profile(config['runtime_profile'])
                else:
                    from .independent_profile import select_config
                    _,profile=select_config(config)
                script='''set -eo pipefail
setup_count=$1
shift
for ((setup_index=0; setup_index<setup_count; setup_index++)); do source "$1"; shift; done
export LD_LIBRARY_PATH="$1/agent-install/lib:${LD_LIBRARY_PATH:-}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
shift
exec python3 -B -m Simulator.wksim_runtime.runtime --prepared "$@"
'''
                os.execvp('bash',['bash','-c',script,'wksim',str(len(profile['setup_files'])),
                                 *profile['setup_files'],profile['dds_workspace'],str(args.config.resolve()),
                                 '--output-root',str(args.output_root.resolve()),*(['--preflight'] if args.preflight else []),
                                 *(['--use-prepared-run',str(args.use_prepared_run.absolute())] if args.use_prepared_run is not None else [])])
            # Source overlays in the verified order; paths are positional arguments, never shell code.
            dds, prom = config['dds_workspace'], config['prometheus_workspace']
            ap = config.get('ap_candidate', '') if config['stack'] == 'arducopter' else ''
            script = '''set -eo pipefail
source "$1/ros-install/setup.bash"
if [[ -n $2 ]]; then source "$2/ros-install/local_setup.bash"; fi
source "$3/install/local_setup.bash"
export LD_LIBRARY_PATH="$1/agent-install/lib:${LD_LIBRARY_PATH:-}"
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
shift 3
exec python3 -m Simulator.wksim_runtime.runtime --prepared "$@"
'''
            os.execvp('bash', ['bash', '-c', script, 'wksim', dds, ap, prom,
                              str(args.config.resolve()), '--output-root', str(args.output_root.resolve()),
                              *(['--preflight'] if args.preflight else []),
                                 *(['--use-prepared-run',str(args.use_prepared_run.absolute())] if args.use_prepared_run is not None else [])])
        if args.preflight:
            result=preflight(config)
            print(json.dumps(result,indent=2,allow_nan=False))
            return 0 if result['ok'] else 2
        options={'use_prepared_run':args.use_prepared_run} if args.use_prepared_run is not None else {}
        return 0 if run(config, args.output_root,**options)['status'] in ('pass', 'cancelled','stopped') else 1
    except (OSError, ValueError, RuntimeError) as error:
        print(f'wksim: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
