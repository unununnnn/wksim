"""Bounded common-time two-FC public Task flight, not a completed G2 product.

Explicit candidates exercise healthy lifecycle or controlled DDS Agent loss.
Collision/spawn offsets and the complete G2 product remain separate gates.
All mode/arm/takeoff/move/land requests go through installed Prometheus control.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_core.model import build_model
from Simulator.wksim_core.joint import JointPhysics
from Simulator.wksim_runtime.scene_clock import SceneClock, ClockPublisher
from Simulator.wksim_runtime.isolation import check_isolation, isolate_temporary_files
from Simulator.wksim_runtime.config import load_config
from Simulator.wksim_runtime.preflight import preflight
from Simulator.wksim_runtime.runtime import launch_spec, stop_children, digest
from Simulator.wksim_runtime.joint_rate import JointRate
from Simulator.wksim_runtime.joint_rate_probe import (
    JointRateTimingProbe,
    TIMING_PROBE_ENV,
    add_timing_probe_identity,
    timing_probe_enabled,
    timing_probe_identity,
)
from ap_clock_candidate import admit
from joint_control_candidate import check as check_control, environment as control_environment
from joint_message_candidate import check as check_messages, environment as message_environment
from probe_joint_clock import json_identity, group_members
from joint_pause_probe import PauseProbe, PauseProbeComplete
from pv_trajectory_task import PROFILE as PV_PROFILE
from tools.mixed_control_task import PROFILE as MIXED_PROFILE

WALL_LIMIT, MAX_TICKS = 900, 180000


def make_joint_rate(epoch, requested_rate, record, *, diagnostic):
    rate_type = JointRateTimingProbe if diagnostic else JointRate
    return rate_type(epoch, requested_rate, record)


def candidate_rate_sources(_diagnostic):
    return [
        "Simulator/wksim_runtime/joint_rate.py",
        "Simulator/wksim_runtime/joint_rate_probe.py",
    ]


def candidate_environment(control, messages=None):
    env = control_environment(control)
    return message_environment(messages, env) if messages is not None else env


def model_environment(base=None):
    """Keep the complete repository runtime ahead of partial control overlays."""
    env = dict(os.environ if base is None else base)
    repo = str(REPO)
    pythonpath = [value for value in env.get('PYTHONPATH', '').split(os.pathsep)
                  if value and value != repo]
    env['PYTHONPATH'] = os.pathsep.join([repo, *pythonpath])
    return env


def activate_candidate_imports(control, messages):
    env = candidate_environment(control, messages)
    for name in ('PYTHONPATH', 'AMENT_PREFIX_PATH', 'LD_LIBRARY_PATH'):
        if name in env:
            os.environ[name] = env[name]
    for path in reversed([value for value in env.get('PYTHONPATH', '').split(os.pathsep) if value]):
        while path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
    expected = dict(prometheus_control=control['package'])
    expected.update({name: str(Path(value['prefix'])/'local/lib/python3.10/dist-packages'/name)
                     for name, value in messages['packages'].items()})
    observed = {}
    for name, directory in expected.items():
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            raise RuntimeError('Candidate Python module is unavailable: '+name)
        observed[name] = str(Path(spec.origin).resolve().parent)
        if observed[name] != str(Path(directory).resolve()):
            raise RuntimeError('Candidate Python module origin differs: '+name)
    return observed


def scheduling(pid, role, *, async_model_evidence=False):
    """Same own-process policy as the formal joint manager; record actual results."""
    value = dict(target_nice=-10 if role in ('manager','model','fc') else -5)
    try:
        os.setpriority(os.PRIO_PROCESS,pid,value['target_nice'])
        value['actual_nice'] = os.getpriority(os.PRIO_PROCESS,pid)
    except OSError as error:
        value['nice_error'] = repr(error)
    if role in ('manager','model','fc'):
        value['target_fifo_priority'] = 50 if role=='manager' else 40
        # The manager must reset its children before Popen so the model worker's
        # background writer cannot race the parent's post-spawn scheduling call
        # and inherit FIFO/50.  The model leader is then explicitly promoted to
        # FIFO/40 with the same reset flag while its existing writer stays
        # ordinary-scheduled.
        reset_on_fork = role in ('manager', 'model') and async_model_evidence
        if reset_on_fork:
            value['reset_on_fork'] = True
        try:
            policy = os.SCHED_FIFO
            if reset_on_fork:
                policy |= os.SCHED_RESET_ON_FORK
            os.sched_setscheduler(pid,policy,os.sched_param(value['target_fifo_priority']))
            value['actual_policy'] = os.sched_getscheduler(pid)
            value['actual_priority'] = os.sched_getparam(pid).sched_priority
        except OSError as error:
            value['scheduler_error'] = repr(error)
    return value


def verify_async_model_evidence(directory):
    """Require both model trace writers to retire with lossless output."""
    directory = Path(directory)
    records = {}
    for stack in ('arducopter', 'px4'):
        trace = directory / (stack + '-truth.jsonl')
        sidecar = Path(str(trace) + '.writer.json')
        try:
            summary = json.loads(sidecar.read_text())
            size = trace.stat().st_size
        except (OSError, ValueError, TypeError) as error:
            raise RuntimeError(f'Missing {stack} model trace writer evidence: {error}') from error
        if (not isinstance(summary, dict)
                or summary.get('complete') is not True or summary.get('alive') is not False
                or summary.get('closed') is not True or summary.get('error') is not None
                or summary.get('writer_scheduler') != dict(
                    available=True, policy='SCHED_OTHER', priority=0,
                    actual_policy=getattr(os, 'SCHED_OTHER', 0), actual_priority=0)
                or type(summary.get('submitted_bytes')) is not int
                or type(summary.get('written_bytes')) is not int
                or summary['submitted_bytes'] != summary['written_bytes']
                or summary['written_bytes'] != size):
            raise RuntimeError(f'{stack} model trace writer did not retire with complete bytes')
        # Keep the result entry byte-for-byte identical to the writer sidecar;
        # the offline auditor owns the trace hash/artifact digest.
        records[stack] = summary
    return records


def retire_model_workers(children, child_specs, *, timeout=3):
    """Close async model-worker stdin before owned-group teardown.

    A model worker publishes its writer sidecar only after its input loop sees
    EOF and the evidence-stream context has retired.  A manager fault used to
    call ``stop_children`` immediately, which sent SIGTERM to the model
    workers and discarded that finalization step along with the sidecar.  Ask
    only live model workers to consume EOF; the normal group cleanup remains
    responsible for every other process and for workers that do not retire in
    time.  Errors are returned so a failed retirement can never turn a failed
    flight into a pass.
    """
    errors = []
    for name, child, _ in children:
        if child_specs.get(child.pid, {}).get('role') != 'model' or child.poll() is not None:
            continue
        stream = getattr(child, 'stdin', None)
        try:
            if stream is not None and not getattr(stream, 'closed', False):
                stream.close()
        except (OSError, ValueError) as error:
            errors.append(f'{name}: stdin close failed: {error}')
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            errors.append(f'{name}: model worker did not retire before timeout: {error}')
        except OSError as error:
            errors.append(f'{name}: model worker wait failed: {error}')
    return errors


def cleanup_children(result, children, child_specs, *, async_model_evidence=False):
    """Retire workers, always tear down groups, and preserve existing errors."""
    errors = []
    if async_model_evidence:
        try:
            errors.extend(retire_model_workers(children, child_specs))
        except BaseException as error:
            errors.append(f'async model worker retirement failed: {error!r}')
    errors.extend(stop_children(children))
    result['cleanup_errors'] = errors
    if errors:
        result['status'] = 'failed'


def save(path, data):
    def evidence(value):
        if isinstance(value, float) and not math.isfinite(value):
            return {'nonfinite_number': repr(value)}
        if isinstance(value, dict):
            return {key:evidence(item) for key,item in value.items()}
        if isinstance(value, (list,tuple)):
            return [evidence(item) for item in value]
        return value
    target = Path(path)
    raw = json.dumps(evidence(data), indent=2, allow_nan=False)+'\n'
    descriptor, temporary = tempfile.mkstemp(prefix='.'+target.name+'-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as output:
            output.write(raw)
        os.replace(temporary,target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify_planner_execution(task_report, control):
    """Match the child's actual imported module bytes to the sealed candidate."""
    release = task_report['task']['release']
    if release['child_returncode'] != 0 or release['child_teardown'] not in ('terminated', 'already_exited'):
        raise ValueError('Planner release node did not exit normally')
    modules = release.get('planner_loaded_modules', {})
    required = {'Simulator.wksim_runtime.planner_transport_node',
                'Simulator.wksim_runtime.planner_transport_receiver',
                'Simulator.wksim_runtime.planner_command_egress'}
    if not required <= modules.keys():
        raise ValueError('Missing actual planner module provenance')
    prefix = Path(control['package']).parent/'Simulator'
    for name, record in modules.items():
        path = Path(record['path'])
        relative = path.relative_to(prefix).as_posix()
        module_path = name.removeprefix('Simulator.').replace('.', '/')
        if (relative not in (module_path+'.py', module_path+'/__init__.py')
                or record['sha256'] != control['simulator_python_sha256'].get(relative)
                or digest(path) != record['sha256']):
            raise ValueError('Planner module differs from sealed Control: '+name)
    return modules


def task_main(args):
    check_isolation()
    import rclpy
    from Simulator.wksim_runtime.task import Task
    root = Path(args.output)
    result = dict(status='failed', stack=args.stack, uav_id=args.uav_id,
                  run_id=args.run_id, scene_epoch=args.scene_epoch, phases=[], task_mode=args.task_mode,
                  task_profile=args.task_profile)
    started = time.monotonic()
    task = None
    rclpy.init(args=[])
    try:
        def health():
            if time.monotonic()-started > WALL_LIMIT:
                raise TimeoutError('Independent task wall watchdog')
        def phase(name):
            value = dict(phase=name, wall=time.monotonic()-started,
                         ros_time_ns=task.node.get_clock().now().nanoseconds,
                         state=task.convert(task.state) if task.state is not None else None)
            result['phases'].append(value)
            save(root/'progress.json', value)
            print(json.dumps(dict(phase=name, uav_id=args.uav_id, ros_time_ns=value['ros_time_ns'])), flush=True)
        if args.task_profile == PV_PROFILE:
            from pv_trajectory_task import PVTask
            task_class, extra = PVTask, dict(trajectory_epoch=args.scene_epoch)
            if args.planner_release_proof:
                from planner_release_task import PlannerReleaseTask
                task_class = PlannerReleaseTask
        elif args.task_profile == MIXED_PROFILE:
            from tools.mixed_control_task import MixedTask
            task_class, extra = MixedTask, dict(trajectory_epoch=args.scene_epoch)
        else:
            task_class, extra = Task, {}
        task = task_class(root, health, phase, args.stack, run_id=args.run_id,
                    protocol='session_v1', uav_id=args.uav_id, use_sim_time=True,
                    scene_epoch=args.scene_epoch if args.scene_lifecycle else None, **extra)
        if args.scene_lifecycle:
            implementation = Path(importlib.util.find_spec('prometheus_control.scene').origin).resolve()
            if implementation.parent != Path(args.control_package) or digest(implementation) != args.scene_module_sha:
                raise RuntimeError('Task did not load the sealed scene permission implementation')
            result['scene_implementation'] = dict(path=str(implementation), sha256=digest(implementation))
        if args.task_mode == 'recover':
            while task.task_time() == 0:
                health()
                rclpy.spin_once(task.node, timeout_sec=.02)
        elif args.task_profile in (PV_PROFILE, MIXED_PROFILE):
            deadline = time.monotonic()+15
            while not task.request_graph_ready():
                health()
                if time.monotonic()>=deadline:
                    raise TimeoutError('Candidate task transport initialization exceeded 15 wall seconds')
                rclpy.spin_once(task.node, timeout_sec=.02)
            save(root/'initialized.json',dict(version=1,run_id=args.run_id,scene_epoch=args.scene_epoch,
                uav_id=args.uav_id,task_profile=args.task_profile,request_graph=task.pv_request_graph,
                ros_time_ns=task.node.get_clock().now().nanoseconds,
                **(dict(planner_prewarm=task._prepared_planner_handoff.record)
                   if args.planner_release_proof and args.stack=='arducopter' else {})))
        task.wait('joint_public_ready', lambda: (task.recovery_transport_fresh() if args.task_mode=='recover' else task.fresh())
                  and (task.request_graph_ready() if args.task_profile in (PV_PROFILE, MIXED_PROFILE) else
                       task.setup_pub.get_subscription_count() == task.command_pub.get_subscription_count() == 1), 55)
        save(root/'ready.json', dict(run_id=args.run_id, scene_epoch=args.scene_epoch,
                                    uav_id=args.uav_id, control_epoch=task.epoch,
                                    task_mode=args.task_mode, start_token=args.start_token,
                                    request_high_water=task.request_id))
        go_file = root.parent/('recovery-go.json' if args.task_mode == 'recover' else 'go.json')
        while not go_file.is_file():
            task.pump()
        go = json.loads(go_file.read_text())
        if go['epoch'] != args.scene_epoch:
            raise ValueError('Joint start belongs to another scene epoch')
        if args.task_mode == 'recover':
            offer = go['tasks'][args.stack]
            if (go.get('version') != 1 or go.get('run_id') != args.run_id
                    or go.get('action') != 'new_recovery_task'
                    or go.get('scene_request_id') != task.scene_lease.check()['request_id']
                    or offer.get('start_token') != args.start_token or offer.get('uav_id') != args.uav_id
                    or offer.get('control_epoch') != task.epoch):
                raise ValueError('Recovery task requires a current explicit start offer')
            if 'native_hold_policy' in offer and (args.stack!='px4' or offer.get('allow_native_hold') is not True
                    or offer['native_hold_policy']!='explicit_before_task_control'):
                raise ValueError('Unknown or unauthorized native hold entry policy')
            task.recover_then_land(allow_native_hold=offer.get('allow_native_hold',False))
        else:
            task.execute()
        result.update(status='pass', task=task.report(), task_final_ros_ns=task.node.get_clock().now().nanoseconds,
                      use_sim_time=task.node.get_parameter('use_sim_time').value)
    except BaseException as error:
        result.update(error=repr(error), traceback=traceback.format_exc())
        print(result['traceback'],file=sys.stderr,flush=True)
        if task is not None:
            result['task'] = task.report()
    finally:
        try:
            if task is not None:
                task.close()
            if rclpy.ok():
                rclpy.shutdown()
        except Exception as error:
            result['status'], result['cleanup_error'] = 'failed', repr(error)
        result['wall_seconds'] = time.monotonic()-started
        save(root/'result.json', result)
    return 0 if result['status'] == 'pass' else 1


def run(args):
    if getattr(args, 'planner_release_proof', False):
        from planner_release_task import PlannerReleaseTask  # Validate helper import before launching actors.
    timing_probe = timing_probe_enabled()
    if timing_probe and args.task_profile not in (PV_PROFILE, MIXED_PROFILE):
        raise ValueError(f"{TIMING_PROBE_ENV}=1 is only allowed for candidate/PV task profiles")
    async_model_evidence = getattr(args, 'async_model_evidence', False)
    if async_model_evidence and args.task_profile not in (PV_PROFILE, MIXED_PROFILE):
        raise ValueError('--async-model-evidence is only allowed for PV/MIXED task profiles')
    model_promotion_flight = getattr(args, 'model_promotion_flight', False)
    diagnostic_identity = timing_probe_identity() if timing_probe else None
    check_isolation()
    promotion_profile = None
    if model_promotion_flight:
        from Simulator.wksim_runtime.joint_profile import LEGACY_PROFILE, select_profile
        promotion_profile = select_profile(LEGACY_PROFILE)
        supplied = {
            'ap': (args.ap_manifest, args.ap_sha256),
            'px4': (args.px4_manifest, args.px4_sha256),
            'control': (args.control_manifest, args.control_sha256),
        }
        for key, (path, checksum) in supplied.items():
            pin = promotion_profile['manifests'][key]
            if path is None or Path(path).resolve(strict=True) != Path(pin['path']).resolve(strict=True) or checksum != pin['sha256']:
                raise ValueError('Model promotion must retain the pinned ' + key + ' manifest')
    def interrupted(signum, frame):
        raise InterruptedError('Owned joint validation interrupted; not a production airborne stop policy')
    signal.signal(signal.SIGTERM, interrupted)
    if os.readlink('/proc/self/ns/mnt') == os.readlink('/proc/1/ns/mnt'):
        raise RuntimeError('Private mount namespace required')
    archive = Path(tempfile.mkdtemp(prefix='joint-public-flight-', dir=REPO/'validation'))
    live = Path(tempfile.mkdtemp(prefix='wksim-joint-flight-', dir='/root'))
    pv = args.task_profile == PV_PROFILE
    mixed = args.task_profile == MIXED_PROFILE
    mixed_firmware = bool(args.ap_mixed_manifest)
    candidate = pv or mixed
    result = dict(status='failed', run_id=archive.name, scene_epoch=uuid.uuid4().hex, task_profile=args.task_profile,
                  model_promotion_flight_requested=model_promotion_flight,
                  pause_probe_requested=args.pause_probe,
                  scene_lifecycle_requested=args.scene_lifecycle,
                  scene_lease_loss_requested=args.scene_lease_loss,
                  dds_loss_requested=args.dds_loss,
                  native_state_trace_requested=args.native_state_trace,
                  diagnostic_land_step_period_s=.012 if args.probe_land_freshness else None,
                  require_clean_control_exit=True,
                  archive=str(archive), live=str(live), children={}, tasks={},
                  isolation={n: os.readlink('/proc/self/ns/'+n) for n in ('net','ipc','mnt')},
                  unowned_ap_before=json_identity(828),
                  bounds=dict(wall_seconds=WALL_LIMIT, simulation_ticks=MAX_TICKS,
                              task_position_error_m=.5, task_speed_m_s=.5,
                              takeoff_min_height_m=2.5, ground_abs_height_m=.3),
                  scope=__doc__)
    result['async_model_evidence_requested'] = async_model_evidence
    if diagnostic_identity is not None:
        result['rate_timing_probe'] = dict(diagnostic_identity)
    print(json.dumps(dict(archive=str(archive), live=str(live))), flush=True)
    children, expected_exits = [], set()
    child_specs, dds_pending, dds_injection, dds_handled = {}, None, None, False
    clock, started = SceneClock(result['scene_epoch']), time.monotonic()
    pause_probe = lifecycle = rate = messages = None
    sources = ['tools/run_joint_flight.py','tools/run-joint-flight.sh','tools/joint_control_candidate.py',
               'tools/pv_trajectory_task.py','tools/mixed_control_task.py',
               'tools/ap_clock_candidate.py','Simulator/wksim_core/joint.py','Simulator/wksim_core/worker.py',
               'Simulator/wksim_core/model.py','Simulator/wksim_core/model.cpp',
               'Simulator/wksim_core/ap_json.py','Simulator/wksim_core/px4_mavlink.py',
               'Simulator/wksim_runtime/scene_clock.py','Simulator/wksim_runtime/task.py',
               'tools/joint_pause_probe.py','Simulator/wksim_runtime/runtime.py',
               'Simulator/wksim_runtime/isolation.py',
               'Simulator/wksim_runtime/preflight.py','Simulator/wksim_runtime/config.py',
               'Simulator/wksim_runtime/capability-index.json',
               'Simulator/wksim_runtime/examples/arducopter-session.json',
               'Simulator/wksim_runtime/examples/px4-session.json']
    if args.scene_lifecycle:
        sources += ['tools/joint_lifecycle.py','Simulator/wksim_runtime/joint_lifecycle.py']
    if args.native_state_trace:
        sources += ['tools/debug_px4_native_state.py']
    if candidate:
        sources += ['tools/ap_pv_candidate.py','tools/verify_ap_pv_candidate.py','tools/prepare_ap_pv_candidate.py',
                    'tools/joint_message_candidate.py']
        sources += candidate_rate_sources(timing_probe)
        sources += ['Simulator/wksim_runtime/joint_profile.py',
                    'Simulator/wksim_runtime/joint-profiles.json','Simulator/wksim_runtime/build_identity.py']
    if async_model_evidence:
        sources += ['Simulator/wksim_runtime/evidence_stream.py']
    if pv:
        sources += ['docs/2026-09-09-pv-flight-plan.md']
    if args.planner_release_proof:
        sources += ['tools/planner_release_task.py', 'tools/planner_release_handoff.py']
        from joint_control_candidate import SIMULATOR_FILES, SIMULATOR_ASSETS
        for package, names in {**SIMULATOR_FILES, **SIMULATOR_ASSETS}.items():
            sources += [f'Simulator/{package}/{name}' for name in names
                        if f'Simulator/{package}/{name}' not in sources]
    if mixed_firmware:
        sources += ['tools/ap_mixed_candidate.py','tools/prepare_ap_mixed_candidate.py',
                    'docs/2026-09-09-mixed-flight-plan.md',
                    'patches/arducopter/0005-dds-mixed-xy-velocity-z-position.patch']
        if pv:
            sources += ['docs/2026-09-09-final-combo-pv-plan.md']
    if args.px4_manifest:
        sources += ['tools/px4_state_candidate.py','tools/build-px4-state-cadence.sh',
                    'patches/px4/0001-estimator-status-cadence.patch',
                    'patches/px4/0002-independent-sitl-without-gazebo.patch']
    result['source_sha256'] = {name:digest(REPO/name) for name in sources}
    for name in sources:
        (live/('source__'+name.replace('/','__')+'.txt')).write_bytes((REPO/name).read_bytes())
    try:
        result['private_temporary_files']=isolate_temporary_files()
        if candidate:
            if not mixed_firmware:
                from ap_pv_candidate import admit as admit_candidate
                ap_manifest, ap_sha = args.ap_pv_manifest, args.ap_pv_sha256
            else:
                from ap_mixed_candidate import admit as admit_candidate
                ap_manifest, ap_sha = args.ap_mixed_manifest, args.ap_mixed_sha256
            admission = admit_candidate(ap_manifest, ap_sha, args.control_manifest, args.control_sha256, result['run_id'],
                message_manifest=args.message_manifest, message_checksum=args.message_sha256,
                **({'task_profile': args.task_profile} if mixed_firmware else {}))
            save(live/'experimental-admission.json', admission)
            if not admission['ok']:
                raise ValueError('Explicit experimental admission rejected: '+str(admission['reasons']))
            result['mixed_admission' if mixed_firmware else 'pv_admission'] = admission
            configs, control = admission['configs'], admission['control_candidate']
            messages = admission.get('message_candidate')
            if messages is not None:
                result['message_candidate'] = messages
                result.setdefault('manifest_sha256', {})['message'] = args.message_sha256
                shutil.copyfile(args.message_manifest, live/'message-build.json')
                result['candidate_import_roots'] = activate_candidate_imports(control, messages)
            library = Path(admission['model_library'])
        else:
            library = build_model()
            configs = {stack:load_config(REPO/f'Simulator/wksim_runtime/examples/{stack}-session.json')
                       for stack in ('arducopter','px4')}
            for stack, config in configs.items():
                config['model_library'] = str(library)
                if model_promotion_flight:
                    config['model_promotion_flight'] = True
                if stack == 'arducopter':
                    configs[stack], admission = admit(config, args.ap_manifest, args.ap_sha256)
                elif args.px4_manifest:
                    from px4_state_candidate import admit as admit_px4
                    configs[stack], admission = admit_px4(config, args.px4_manifest, args.px4_sha256)
                else:
                    admission = preflight(config)
                save(live/(stack+'-preflight.json'), admission)
                if not admission['ok']:
                    raise ValueError('Fixed environment admission failed: '+str(admission['reasons']))
            if model_promotion_flight:
                from Simulator.wksim_runtime.joint_profile import _control, _pinned_json
                control = _pinned_json(promotion_profile['manifests']['control'])
                _control(control, sealed=True)
            else:
                control = check_control(args.control_manifest, args.control_sha256)
        model_manifest = library.with_name('build.json')
        result['model_build'] = json.loads(model_manifest.read_text())
        result['model_build_manifest_sha256'] = digest(model_manifest)
        shutil.copyfile(model_manifest, live/'model-build.json')
        if model_promotion_flight:
            from Simulator.wksim_core.model import probe_model
            if digest(library) != result['model_build']['library_sha256']:
                raise ValueError('Promotion model changed after static preflight')
            result['model_promotion_probe'] = probe_model(library)
            if (json.loads(library.with_name('build.json').read_text()) != result['model_build']
                    or digest(library) != result['model_build']['library_sha256']):
                raise ValueError('Promotion model changed during the pre-launch ABI probe')
        if args.scene_lifecycle:
            sys.path.insert(0, str(Path(control['package']).parent))
        result['control_candidate'] = control
        if candidate:
            result['control_source_sha256'] = control['python_sha256']
            for name, expected in control['python_sha256'].items():
                source = Path(control['package'])/name
                if digest(source) != expected:
                    raise ValueError('Candidate control changed before source retention')
                target = live/'control-source'/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        result['manifest_sha256'] = dict(ap=ap_sha if candidate else args.ap_sha256, control=args.control_sha256)
        if messages is not None:
            result['manifest_sha256']['message'] = args.message_sha256
        if args.px4_manifest:
            result['manifest_sha256']['px4'] = args.px4_sha256
            shutil.copyfile(args.px4_manifest, live/'px4-build.json')
        shutil.copyfile(ap_manifest if candidate else args.ap_manifest, live/'ap-build.json')
        shutil.copyfile(args.control_manifest, live/'control-build.json')
        if mixed_firmware:
            from verify_ap_pv_candidate import checked_json
            native_root = Path(ap_manifest).parent
            prepared = checked_json(native_root/'mixed-source.json', admission['candidate']['source_manifest_sha256'])
            shutil.copyfile(native_root/'mixed-source.json', live/'mixed-source.json')
            shutil.copyfile(native_root/'baseline-pv-build.json', live/'baseline-pv-build.json')
            native_files = ('libraries/AP_DDS/AP_DDS_ExternalControl.cpp',
                'libraries/AP_ExternalControl/AP_ExternalControl.h', 'ArduCopter/AP_ExternalControl_Copter.h',
                'ArduCopter/AP_ExternalControl_Copter.cpp', 'ArduCopter/mode.h', 'ArduCopter/mode_guided.cpp',
                'ArduCopter/GCS_MAVLink_Copter.cpp', 'ArduCopter/Log.cpp')
            result['native_source_root'] = str(native_root/'src')
            result['native_source_sha256'] = {}
            for name in native_files:
                source = native_root/'src'/name
                expected = prepared['source']['files'][name]['sha256']
                if digest(source) != expected:
                    raise ValueError('Native source changed before retention: '+name)
                target = live/'native-source'/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                result['native_source_sha256'][name] = expected

        def physics_health():
            if pause_probe is not None:
                pause_probe.pump()
            if lifecycle is not None:
                lifecycle.periodic()
            if time.monotonic()-started > WALL_LIMIT:
                raise TimeoutError('Joint run wall watchdog')
            for name, child, _ in children:
                code = child.poll()
                if code is None or child.pid in expected_exits:
                    continue
                role = child_specs.get(child.pid,{}).get('role','model')
                if role in ('model','fc','control'):
                    raise RuntimeError(f'{name} exited unexpectedly: {code}')

        def health():
            nonlocal dds_pending
            physics_health()
            for name, child, _ in children:
                code = child.poll()
                if code is None or child.pid in expected_exits:
                    continue
                spec = child_specs[child.pid]
                if (args.dds_loss and not dds_handled and dds_injection is not None
                        and name == args.dds_loss+'-agent'):
                    dds_pending = (name, child)
                    lifecycle.record('agent_exit_detected', name=name, pid=child.pid, returncode=code)
                    return
                if spec['role'] == 'task' and code == 0:
                    stack = spec['result_key']
                    report = json.loads((spec['directory']/'result.json').read_text())
                    if (report['status'] != 'pass' or report['scene_epoch'] != clock.epoch
                            or report['run_id'] != result['run_id']):
                        raise RuntimeError('Task exited without matching successful result')
                    if args.scene_lifecycle and report.get('scene_implementation') != dict(
                            path=str(Path(control['package'])/'scene.py'), sha256=control['python_sha256']['scene.py']):
                        raise RuntimeError('Task scene permission implementation identity differs')
                    if args.planner_release_proof and stack == 'arducopter':
                        result['planner_executed_modules'] = verify_planner_execution(report, control)
                    expected_exits.add(child.pid)
                    result['tasks'][stack] = report
                else:
                    raise RuntimeError(f'{name} exited unexpectedly: {code}')

        def launch(name, argv, cwd, env=None, role=None, result_key=None):
            log = (live/(name+'.log')).open('x')
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=log,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
            children.append((name,child,log))
            child_specs[child.pid] = dict(role=role or name.rsplit('-',1)[-1], directory=Path(cwd),
                                          result_key=result_key or name[:-5], env=env)
            result['children'][name] = dict(identity=json_identity(child.pid), argv=argv, cwd=str(cwd))
            if candidate:
                result['children'][name]['scheduling'] = scheduling(child.pid,child_specs[child.pid]['role'])
            return child

        def launch_task(stack, uid, directory, task_mode='initial', start_token=None):
            command = [sys.executable,'-B',str(Path(__file__).resolve()),'task',
                '--stack',stack,'--uav-id',str(uid),'--run-id',result['run_id'],
                '--scene-epoch',clock.epoch,'--output',str(directory),'--task-mode',task_mode,
                '--task-profile',args.task_profile]
            if args.planner_release_proof:
                command += ['--planner-release-proof']
            if args.scene_lifecycle:
                command += ['--scene-lifecycle','--control-package',control['package'],
                            '--scene-module-sha',control['python_sha256']['scene.py']]
            if start_token is not None:
                command += ['--start-token',start_token]
            name = stack+('-recovery-task' if task_mode == 'recover' else '-task')
            return launch(name,command,directory,candidate_environment(control, messages)
                          if args.scene_lifecycle or candidate else None,
                          role='task',result_key=stack)

        def record_native_maps(label):
            observations = {}
            for stack in ('arducopter','px4'):
                name = stack+'-fc'
                child = next(process for key,process,_ in children if key==name)
                identity = json_identity(child.pid)
                expected = result['children'][name]['identity']
                if identity is None or any(identity[key]!=expected[key] for key in ('pid','pgid','start_ticks')):
                    raise RuntimeError('Native library observation lost owned process identity')
                proc = Path('/proc')/str(child.pid)
                executable = (proc/'exe').resolve()
                if executable!=Path(result['children'][name]['argv'][0]).resolve():
                    raise RuntimeError('Native executable changed before library observation')
                raw = (proc/'maps').read_text()
                path = live/(name+'-'+label+'-maps.txt')
                path.write_text(raw)
                forbidden = sorted({line.split()[-1] for line in raw.splitlines()
                                    if any(token in line.lower() for token in ('libgz-','libgazebo','libignition','matlab'))})
                observations[stack] = dict(identity=identity,executable=str(executable),executable_sha256=digest(executable),
                    maps_file=path.name,sha256=digest(path),forbidden_libraries=forbidden,
                    scene_phase=clock.phase, captured_monotonic_ns=time.monotonic_ns())
                if (candidate or stack=='px4' and args.px4_manifest) and forbidden:
                    raise RuntimeError('Independent PX4 candidate loaded forbidden libraries')
            result.setdefault('native_runtime_maps',{})[label] = observations
            if candidate:
                models = {}
                for stack in ('arducopter', 'px4'):
                    name = stack+'-model'
                    child = next(process for key,process,_ in children if key == name)
                    identity = json_identity(child.pid)
                    expected = result['children'][name]['identity']
                    if identity is None or any(identity[key] != expected[key] for key in ('pid','pgid','start_ticks')):
                        raise RuntimeError('Model mapping lost owned process identity')
                    proc = Path('/proc')/str(child.pid)
                    executable = (proc/'exe').resolve()
                    raw = (proc/'maps').read_text()
                    path = live/(name+'-'+label+'-maps.txt')
                    path.write_text(raw)
                    if (executable != Path(result['children'][name]['argv'][0]).resolve()
                            or str(library) not in raw or any(token in raw.lower() for token in
                                ('libgz-','libgazebo','libignition','matlab','coptersim.exe'))):
                        raise RuntimeError('Model mapped an unexpected executable or library')
                    models[stack] = dict(identity=identity, executable=str(executable),
                        executable_sha256=digest(executable), maps_file=path.name, maps_sha256=digest(path),
                        model_library=str(library), model_library_sha256=digest(library),
                        scene_phase=clock.phase, captured_monotonic_ns=time.monotonic_ns())
                result.setdefault('model_runtime_maps',{})[label] = models

        def recover_agent(advance):
            nonlocal dds_handled
            name, failed_agent = dds_pending
            failure_before = lifecycle.snapshot(physics)
            progress = dict(status='running', affected_stack=args.dds_loss, injection=dds_injection,
                            before_failure=failure_before)
            result['dds_recovery'] = progress
            lifecycle.communication_fault(name+'_exited',[1 if args.dds_loss=='arducopter' else 2])
            expected_exits.add(failed_agent.pid)
            old_tasks = [(n,p) for n,p,_ in children if child_specs[p.pid]['role']=='task']
            expected_exits.update(p.pid for _,p in old_tasks)
            began = time.monotonic()
            while time.monotonic()-began < 3:
                physics_health()
                time.sleep(.002)
            old_reports = {}
            for task_name, process in old_tasks:
                if process.poll() != 1:
                    raise RuntimeError('Original tasks must naturally fail and retire after DDS loss')
                spec = child_specs[process.pid]
                old_reports[spec['result_key']] = json.loads((spec['directory']/'result.json').read_text())
                if old_reports[spec['result_key']]['status'] != 'failed':
                    raise RuntimeError('Old task was not recorded as failed')
            frozen = lifecycle.snapshot(physics)
            progress.update(frozen=frozen,old_tasks=old_reports)
            if frozen['models'] != failure_before['models']:
                raise RuntimeError('DDS failure advanced physics before explicit recovery')
            if any(not pause_probe.sessions[uid].control.failsafe for uid in (1,2)):
                raise RuntimeError('Both controls must withdraw after a participant DDS loss')
            original = result['children'][name]
            replacement = launch(name+'-reconnected',original['argv'],Path(original['cwd']),
                                 child_specs[failed_agent.pid]['env'],role='agent')
            lifecycle.record('agent_restarted', name=name, old_pid=failed_agent.pid, new_pid=replacement.pid)
            until = time.monotonic()+1
            while time.monotonic() < until:
                physics_health()
                if replacement.poll() is not None:
                    raise RuntimeError('Replacement Agent exited before explicit recovery')
                time.sleep(.002)
            reconnected_frozen = lifecycle.snapshot(physics)
            progress.update(reconnected_frozen=reconnected_frozen,replacement_agent_pid=replacement.pid)
            if reconnected_frozen['models'] != frozen['models']:
                raise RuntimeError('Agent restart automatically advanced physics')
            recovery_boundary = lifecycle.begin_recovery()
            if args.dds_loss == 'px4':
                import socket, struct
                px_process=next(p for n,p,_ in children if n=='px4-fc')
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
                    peer.settimeout(1)
                    peer.connect('/tmp/px4-sock-21')
                    peer_pid,peer_uid,peer_gid=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if (peer_pid!=px_process.pid or json_identity(px_process.pid)!=result['children']['px4-fc']['identity']
                        or px_process.poll() is not None):
                    raise RuntimeError('Native DDS client command did not resolve to the owned PX4 daemon')
                lifecycle.record('px4_cli_peer_verified',pid=peer_pid,uid=peer_uid,gid=peer_gid)
                commands=[['stop'],['start','-t','udp','-h','127.0.0.1','-p','18888','-n','wksim_px4_21']]
                progress['native_dds_restart']=[]
                for command in commands:
                    argv=[str(Path(configs['px4']['px4_root'])/'build/px4_sitl_default/bin/px4-uxrce_dds_client'),
                          '--instance','21',*command]
                    process=launch('px4-dds-'+command[0],argv,live/'px4',role='service')
                    while process.poll() is None:
                        if time.monotonic()-lifecycle.recovery_started>=5:
                            lifecycle.communication_fault('native_dds_client_restart_timeout')
                            raise TimeoutError('Native DDS client restart exceeded the approved recovery window')
                        advance()
                    if process.returncode:
                        raise RuntimeError('Native DDS client '+command[0]+' failed: '+str(process.returncode))
                    expected_exits.add(process.pid)
                    event=dict(argv=argv,pid=process.pid,returncode=process.returncode,phase=command[0])
                    progress['native_dds_restart'].append(event)
                    lifecycle.record('native_dds_client_restarted',observation=event)
            offers = {}
            for stack, uid in (('arducopter',1),('px4',2)):
                directory = live/(stack+'-recovery')
                directory.mkdir()
                token = uuid.uuid4().hex
                offers[stack] = dict(start_token=token,uav_id=uid,control_epoch=pause_probe.sessions[uid].control_epoch)
                launch_task(stack,uid,directory,'recover',token)
            physical_recovery = lifecycle.recover_physics(advance,recovery_boundary)
            progress['physics_recovery'] = physical_recovery
            for stack in offers:
                offers[stack]['allow_native_hold']=stack=='px4'
                if stack=='px4':
                    offers[stack]['native_hold_policy']='explicit_before_task_control'
            # No new high-level flight request is authorized by Agent restart or
            # by the physical recovery alone. This is a new explicit task offer.
            authorization = dict(version=1,epoch=clock.epoch,run_id=result['run_id'],
                scene_request_id=clock.last_request,action='new_recovery_task',tasks=offers)
            save(live/'recovery-go.json',authorization)
            lifecycle.record('new_task_authorized', authorization=authorization)
            dds_handled = True
            progress.update(status='pass',affected_stack=args.dds_loss,
                injection=dds_injection, before_failure=failure_before, frozen=frozen,
                reconnected_frozen=reconnected_frozen, old_tasks=old_reports,
                replacement_agent_pid=replacement.pid, physics_recovery=physical_recovery,
                new_task_authorization=authorization)

        import rclpy
        rclpy.init(args=[])
        with ExitStack() as resources:
            resources.callback(rclpy.shutdown)
            node = rclpy.create_node('wksim_joint_flight_clock')
            resources.callback(node.destroy_node)
            publisher = ClockPublisher(node)
            resources.callback(publisher.close)
            if candidate:
                from pv_trajectory_task import PVProbe
                pause_probe = PVProbe(node, clock, live, started)
                resources.callback(pause_probe.close)
                rate_log = resources.enter_context((live/'rate.jsonl').open('x', buffering=65536))
                def record_rate(kind, **fields):
                    if diagnostic_identity is not None:
                        fields = add_timing_probe_identity(fields, diagnostic_identity)
                    rate_log.write(json.dumps(dict(kind=kind, epoch=clock.epoch, tick=clock.tick,
                        issued_monotonic_ns=time.monotonic_ns(), **fields), separators=(',', ':'))+'\n')
                rate = make_joint_rate(clock.epoch, .5, record_rate, diagnostic=timing_probe)
                record_rate('rate_bootstrap', classification='untimed_until_first_synchronized_barrier')
            elif args.pause_probe or args.scene_lifecycle:
                pause_probe = PauseProbe(node, clock, live, started, args.repeat_paused_clock)
                resources.callback(pause_probe.close)
            wire = resources.enter_context((live/'joint-wire.jsonl').open('x', buffering=65536))
            clock_log = resources.enter_context((live/'clock.jsonl').open('x', buffering=65536))
            def record(kind, **data):
                wire.write(json.dumps(dict(kind=kind, epoch=clock.epoch,tick=clock.tick,
                                          wall=time.monotonic()-started,**data),separators=(',',':'),allow_nan=False)+'\n')
            workers = {}
            physics = JointPhysics(resources, clock, workers, physics_health, record)
            publisher.publish(clock)
            clock_log.write(json.dumps(clock.snapshot())+'\n')
            if args.scene_lifecycle:
                # Use the explicitly sealed candidate package for the shared
                # permission schema as well as the actual controller process.
                from joint_lifecycle import JointLifecycle
                lifecycle = JointLifecycle(node, clock, publisher, live, result['run_id'], started, pause_probe)
                resources.callback(lifecycle.close)
            if candidate:
                result['manager_scheduling'] = scheduling(
                    0, 'manager', async_model_evidence=async_model_evidence)
            for stack, uid in (('arducopter',1),('px4',2)):
                directory = live/stack
                directory.mkdir()
                (directory/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
                log = (live/(stack+'-model.log')).open('x')
                argv = [sys.executable,'-B','-m','Simulator.wksim_core.worker','--library',str(library),
                        '--trace',str(live/(stack+'-truth.jsonl')),'--epoch',clock.epoch]
                if async_model_evidence:
                    argv.append('--async-evidence')
                runtime_env = model_environment()
                child = subprocess.Popen(argv,cwd=directory,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                         stderr=log,text=True,start_new_session=True,env=runtime_env)
                children.append((stack+'-model',child,log)); workers[stack]=child
                child_specs[child.pid] = dict(role='model',directory=directory,result_key=stack,env=runtime_env)
                result['children'][stack+'-model'] = dict(identity=json_identity(child.pid),argv=argv,cwd=str(directory))
                result['children'][stack+'-model']['runtime_python_root'] = str(REPO)
                if candidate:
                    result['children'][stack+'-model']['scheduling'] = scheduling(
                        child.pid, 'model', async_model_evidence=async_model_evidence)
                plan = launch_spec(configs[stack], directory, library)
                launch(stack+'-agent',plan['agent'],directory)
                launch(stack+'-fc',plan['fc'],directory,dict(os.environ,**plan['fc_environment']))
                result['children'][stack+'-fc']['environment_overrides'] = plan['fc_environment']
                for index, value in enumerate(plan['control']):
                    if value.startswith('uav_id:='): plan['control'][index] = 'uav_id:='+str(uid)
                    if value.startswith('run_id:='): plan['control'][index] = 'run_id:='+result['run_id']
                plan['control'] += ['-p','use_sim_time:=true','-r','__node:=wksim_joint_'+stack+'_control']
                if (pv or mixed_firmware) and stack == 'arducopter':
                    plan['control'] += ['-p','arducopter_pv_profile:='+PV_PROFILE]
                if mixed_firmware and stack == 'arducopter':
                    plan['control'] += ['-p','arducopter_mixed_profile:='+MIXED_PROFILE]
                if args.scene_lifecycle:
                    plan['control'] += ['-p', 'scene_epoch:='+clock.epoch]
                verifier = ('import importlib.util,pathlib; '
                    'assert pathlib.Path(importlib.util.find_spec("prometheus_control").origin).parent == pathlib.Path('
                    +repr(control['package'])+'); ')
                if messages is not None:
                    module_roots = {name: str(Path(value['prefix'])/'local/lib/python3.10/dist-packages'/name)
                                    for name, value in messages['packages'].items()}
                    verifier += ('roots='+repr(module_roots)+'; assert all(pathlib.Path(importlib.util.find_spec(name).origin).parent '
                                 '== pathlib.Path(path) for name,path in roots.items()); ')
                verifier += 'import prometheus_control.node as n; n.main()'
                if args.native_state_trace and stack == 'px4':
                    verifier = ('from tools.debug_px4_native_state import install; install('
                        +repr(str(live/'px4-native-state-trace.jsonl'))+'); '+verifier)
                command = [sys.executable,'-B','-c',verifier,*plan['control'][3:]]
                launch(stack+'-control',command,directory,candidate_environment(control, messages))
                launch_task(stack,uid,directory)
            save(live/'children-start.json',result['children'])
            if candidate:
                deadline = time.monotonic()+15
                while not all((live/stack/'initialized.json').is_file() for stack in ('arducopter','px4')):
                    physics_health()
                    if time.monotonic()>=deadline:
                        raise TimeoutError('Candidate transport initialization exceeded 15 wall seconds before clock start')
                    time.sleep(.002)
                initialized = {}
                for stack,uid in (('arducopter',1),('px4',2)):
                    record = json.loads((live/stack/'initialized.json').read_text())
                    if (record['version']!=1 or record['run_id']!=result['run_id']
                            or record['scene_epoch']!=clock.epoch or record['uav_id']!=uid
                            or record['task_profile']!=args.task_profile or record['ros_time_ns']!=0):
                        raise ValueError('Candidate startup identity or zero clock differs')
                    if args.planner_release_proof and stack=='arducopter':
                        warm=record['planner_prewarm']
                        if (warm['outcome']!='prepared_at_clock_zero'
                                or warm['timestamps']['node_spawned_ros_ns']!=0
                                or warm['timestamps']['warm_ready_ros_ns']!=0
                                or warm['child']['pgid']!=result['children']['arducopter-task']['identity']['pgid']):
                            raise ValueError('Planner prewarm did not complete inside the task group at clock zero')
                    initialized[stack] = record
                from Simulator.wksim_core.worker import receive_worker
                snapshots = {stack:receive_worker(worker,dict(version=1,epoch=clock.epoch,snapshot=True),clock.epoch)
                             for stack,worker in workers.items()}
                if clock.tick!=0 or any(row['tick']!=0 or row['state'] is not None for row in snapshots.values()):
                    raise ValueError('Candidate startup advanced the model clock')
                record_native_maps('running')
                result['initialization'] = dict(physical_tick=0,tasks=initialized,models=snapshots,
                    task_execution_requires_go=True,completed_monotonic_ns=time.monotonic_ns())
            physics.connect()
            summaries = {name:dict(max_height_m=0., min_waypoint_error_m=1e30) for name in workers}
            land_pacing_next = None
            def advance():
                nonlocal land_pacing_next
                if rate is not None and clock.tick%4 == 0 and clock.synchronized and clock.phase == 'running':
                    if rate.anchor is None:
                        rate.reanchor(clock.tick, 'synchronized_boundary')
                    rate.begin_group(clock.tick, physics_health)
                session = pause_probe.sessions.get(2) if args.probe_land_freshness else None
                if (args.probe_land_freshness and dds_handled and clock.tick%4==0
                        and session is not None and session.state.mode=='AUTO.LAND'):
                    if land_pacing_next is None:
                        record('diagnostic_land_pacing_started', minimum_barrier_wall_seconds=.012,
                               reason='reproduce low-rate estimator wall freshness without changing any health threshold')
                    else:
                        while time.monotonic() < land_pacing_next:
                            health()
                            time.sleep(min(.001, max(0,land_pacing_next-time.monotonic())))
                    land_pacing_next = time.monotonic()+.012
                states = physics.advance()
                publisher.publish(clock)
                clock_log.write(json.dumps(clock.snapshot(),separators=(',',':'))+'\n')
                if rate is not None and clock.tick%4 == 0 and rate.group is not None:
                    rate.end_group(clock.tick)
                return states
            while clock.tick < MAX_TICKS:
                health()
                if dds_pending is not None and not dds_handled:
                    recover_agent(advance)
                states = advance()
                if clock.tick==5000 and not candidate:
                    record_native_maps('running')
                if not (live/'go.json').exists() and all((live/name/'ready.json').exists() for name in workers):
                    save(live/'go.json', clock.snapshot())
                if pv and clock.tick%4 == 0:
                    for leg in (1, 2):
                        go_path = live/f'pv-go-{leg}.json'
                        ready_paths = {stack:live/stack/f'pv-ready-{leg}.json' for stack in workers}
                        if not go_path.exists() and all(path.is_file() for path in ready_paths.values()):
                            offers = {stack:json.loads(path.read_text()) for stack, path in ready_paths.items()}
                            for stack, uid in (('arducopter', 1), ('px4', 2)):
                                initial = json.loads((live/stack/'ready.json').read_text())
                                offer = offers[stack]
                                if (offer['version'] != 1 or offer['profile'] != PV_PROFILE or offer['leg'] != leg
                                        or offer['run_id'] != result['run_id'] or offer['scene_epoch'] != clock.epoch
                                        or offer['uav_id'] != uid or offer['control_epoch'] != initial['control_epoch']
                                        or len(offer['token']) != 32):
                                    raise ValueError('P+V readiness identity differs')
                            save(go_path, dict(version=1, profile=PV_PROFILE, run_id=result['run_id'],
                                scene_epoch=clock.epoch, leg=leg, issued_tick=clock.tick,
                                start_ns=(clock.tick+1000)*clock.STEP_NS, tasks=offers))
                for name,state in states.items():
                    import math
                    row=summaries[name]
                    row['max_height_m']=max(row['max_height_m'],-state[8])
                    row['min_waypoint_error_m']=min(row['min_waypoint_error_m'],math.dist(state[6:9],[3,2,-3]))
                    row['final_height_m']=-state[8]
                if clock.tick % 5000 == 0:
                    print(json.dumps(dict(tick=clock.tick,heights={k:round(-v[8],3) for k,v in states.items()},
                                          completed_tasks=list(result['tasks']))),flush=True)
                if args.dds_loss and dds_injection is None and pause_probe.ready(result['run_id'],states):
                    target = next(p for n,p,_ in children if n == args.dds_loss+'-agent')
                    identity = json_identity(target.pid)
                    expected_identity=result['children'][args.dds_loss+'-agent']['identity']
                    executable=Path('/proc')/str(target.pid)/'exe'
                    observation=dict(expected=expected_identity,observed=identity,
                                     executable=os.readlink(executable) if executable.exists() else None)
                    result['agent_identity_before_injection']=observation
                    if (identity is None or any(identity[key]!=expected_identity[key] for key in ('pid','pgid','start_ticks'))
                            or not executable.exists() or executable.resolve()!=Path(result['children'][args.dds_loss+'-agent']['argv'][0]).resolve()
                            or target.poll() is not None):
                        raise RuntimeError('Agent identity changed before owned failure injection')
                    dds_injection = dict(tick=clock.tick,wall=time.monotonic()-started,identity=identity)
                    lifecycle.record('agent_stop_requested', observation=dds_injection)
                    target.terminate()
                if (not args.dds_loss and lifecycle is not None and not lifecycle.completed
                        and pause_probe.ready(result['run_id'], states)):
                    observed = lifecycle.exercise(physics, health, advance, children if args.scene_lease_loss else None)
                    if args.scene_lease_loss:
                        result['scene_fault_observation'] = observed
                        for child in workers.values():
                            child.stdin.close(); child.wait(timeout=3)
                            if child.returncode: raise RuntimeError('Faulted paused model did not close normally')
                        clock.request(dict(version=1,epoch=clock.epoch,request_id=clock.last_request+1,action='stop'))
                        result['final_authority'] = clock.snapshot()
                        result['clock_publications'] = publisher.publications
                        raise PauseProbeComplete('Scene permission loss observed; no automatic control recovery')
                    result['scene_lifecycle'] = observed
                    states = physics.states
                if args.pause_probe and pause_probe.ready(result['run_id'], states):
                    print(json.dumps(dict(pause_probe='begin', tick=clock.tick)), flush=True)
                    result['pause_observation'] = pause_probe.observe(physics, children, publisher)
                    if result['pause_observation']['status'] != 'observed':
                        raise RuntimeError('Pause observation failed: '+str(result['pause_observation']['verification_errors']))
                    for child in workers.values():
                        child.stdin.close(); child.wait(timeout=3)
                        if child.returncode: raise RuntimeError('Paused model did not close normally')
                    clock.request(dict(version=1,epoch=clock.epoch,request_id=clock.last_request+1,action='stop'))
                    result['final_authority'] = clock.snapshot()
                    result['clock_publications'] = publisher.publications
                    raise PauseProbeComplete('Airborne pause observed; flight deliberately incomplete')
                if len(result['tasks']) == 2 and clock.tick % 4 == 0:
                    break
            if len(result['tasks']) != 2:
                raise TimeoutError('Both public tasks did not finish inside the fixed simulation budget')
            if any(row['max_height_m']<2.5 or (not args.dds_loss and row['min_waypoint_error_m']>.5) or abs(row['final_height_m'])>.3
                   for row in summaries.values()):
                raise ValueError('Independent model truth failed the fixed flight bounds')
            result['truth_summary'] = summaries
            result['clock_publications'] = publisher.publications
            result['paused_clock_republications'] = publisher.paused_republications
            result['faulted_clock_republications'] = publisher.faulted_republications
            if args.dds_loss and not dds_handled:
                raise RuntimeError('Requested DDS recovery was not exercised')
            if args.scene_lifecycle and not args.dds_loss and (lifecycle is None or not lifecycle.completed):
                raise RuntimeError('Requested lifecycle exercise did not complete')
            if rate is not None:
                rate.check_boundary(clock.tick)
                rate.close_segment('completed', clock.tick)
                result['rate'] = rate.last_summary
            clock.request(dict(version=1,epoch=clock.epoch,request_id=clock.last_request+1,action='stop'))
            result['final_authority'] = clock.snapshot()
            result['terminal_transition'] = dict(action='stop', tick=clock.tick, phase=clock.phase,
                                                 issued_monotonic_ns=time.monotonic_ns())
            record_native_maps('completed')
            for child in workers.values():
                child.stdin.close(); child.wait(timeout=3)
                if child.returncode: raise RuntimeError('Model did not close normally')
            result['status']='pass'
    except PauseProbeComplete as error:
        result.update(status='observed', observation=str(error))
    except BaseException as error:
        if clock.phase != 'faulted':
            clock.fault(str(error))
        result.update(error=repr(error),traceback=traceback.format_exc(),faulted_authority=clock.snapshot())
        print('Joint flight failed: '+repr(error),flush=True)
    finally:
        cleanup_children(result, children, child_specs,
                         async_model_evidence=async_model_evidence)
        for name,child,_ in children:
            result['children'][name].update(returncode=child.returncode,remaining_group_members=group_members(child.pid))
        if async_model_evidence:
            try:
                result['async_model_evidence'] = verify_async_model_evidence(live)
            except BaseException as error:
                result['status'] = 'failed'
                result.setdefault('error', 'Async model evidence incomplete')
                result['async_model_evidence_error'] = repr(error)
        result['unowned_ap_after']=json_identity(828)
        result['source_unchanged']=result['source_sha256']=={name:digest(REPO/name) for name in sources}
        if candidate and result.get('control_source_sha256'):
            result['source_unchanged'] = result['source_unchanged'] and all(
                digest(Path(result['control_candidate']['package'])/name) == expected
                and digest(live/'control-source'/name) == expected
                for name, expected in result['control_source_sha256'].items())
        if result.get('native_source_sha256'):
            result['source_unchanged'] = result['source_unchanged'] and all(
                digest(Path(result['native_source_root'])/name) == expected
                and digest(live/'native-source'/name) == expected
                for name, expected in result['native_source_sha256'].items())
        if args.planner_release_proof and result.get('control_candidate'):
            try:
                result['planner_control_unchanged'] = (check_control(args.control_manifest, args.control_sha256)
                                                       == result['control_candidate'])
            except (OSError, ValueError, KeyError, TypeError, ImportError):
                result['planner_control_unchanged'] = False
            if not result['planner_control_unchanged']:
                result['status'] = 'failed'
                result.setdefault('error', 'Planner Control candidate changed during execution')
        if result.get('message_candidate'):
            try:
                result['message_unchanged'] = (check_messages(args.message_manifest, args.message_sha256)
                                               == result['message_candidate'])
            except (OSError, ValueError, KeyError, TypeError, ImportError):
                result['message_unchanged'] = False
        if result.get('model_promotion_flight_requested') and result.get('model_build'):
            try:
                model_library=Path(result['model_build']['library'])
                result['model_unchanged'] = (digest(model_library)==result['model_build']['library_sha256']
                    and digest(model_library.with_name('build.json'))==result['model_build_manifest_sha256']
                    and json.loads(model_library.with_name('build.json').read_text())==result['model_build'])
            except (OSError, ValueError, KeyError, TypeError):
                result['model_unchanged'] = False
        result['control_shutdown_clean']=all(child['returncode']==0 for name,child in result['children'].items()
                                              if name.endswith('-control'))
        if result['status'] in ('pass', 'observed') and not result['control_shutdown_clean']:
            result['status'], result['error'] = 'failed', 'Control nodes did not stop normally'
        if (result['cleanup_errors'] or any(v['remaining_group_members'] for v in result['children'].values())
                or not result['source_unchanged'] or result['unowned_ap_before']!=result['unowned_ap_after']
                or result.get('message_candidate') and not result.get('message_unchanged')
                or result.get('model_promotion_flight_requested') and not result.get('model_unchanged')):
            result['status']='failed'
        if args.planner_release_proof:
            if result['status'] == 'pass':
                result['status'] = 'observed'
            result['planner_release_proof'] = True
            result['nominal_pv_acceptance'] = False
        result['flight_completed'] = result['status']=='pass'
        result['wall_seconds']=time.monotonic()-started
        save(live/'result.json',result)
        shutil.copytree(live,archive,dirs_exist_ok=True)
        print(json.dumps(dict(status=result['status'],archive=str(archive),error=result.get('error'),
                              wall_seconds=result['wall_seconds'])),flush=True)
    return 0 if result['status'] in ('pass', 'observed') else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='role',required=True)
    runner=sub.add_parser('run')
    runner.add_argument('--planner-release-proof', action='store_true')
    runner.add_argument('--pause-probe', action='store_true',
                        help='Observe four wall seconds at a true airborne pause, then stop without resuming')
    runner.add_argument('--repeat-paused-clock', action='store_true',
                        help='Explicit pause-probe candidate: re-publish the committed frozen clock every 100ms')
    runner.add_argument('--scene-lifecycle', action='store_true',
                        help='Approved opt-in permission candidate: long pause, four ticks, pause, explicit resume')
    runner.add_argument('--scene-lease-loss', action='store_true',
                        help='Withhold permission at an airborne pause, observe withdrawal and no automatic recovery, then stop')
    runner.add_argument('--dds-loss', choices=('arducopter','px4'),
                        help='Stop one actual Agent at hover, freeze on observed exit, explicitly recover physics and launch new landing tasks')
    runner.add_argument('--native-state-trace', action='store_true',
                        help='Read-only debug observation of the actual PX4 Control callbacks and state decisions')
    runner.add_argument('--probe-land-freshness', action='store_true',
                        help='Diagnostic only: pace landing at >=12ms wall per 4ms joint barrier to reproduce low-rate state expiry')
    runner.add_argument('--model-promotion-flight', action='store_true',
                        help='Explicit unflown current-model ABI admission for one healthy position flight')
    runner.add_argument('--async-model-evidence', action='store_true',
                        help='Explicit bounded model truth-writer candidate for PV/MIXED flights')
    for name in ('control-manifest','control-sha256'):
        runner.add_argument('--'+name,required=True)
    for name in ('ap-manifest','ap-sha256','ap-pv-manifest','ap-pv-sha256','ap-mixed-manifest','ap-mixed-sha256'):
        runner.add_argument('--'+name)
    runner.add_argument('--message-manifest')
    runner.add_argument('--message-sha256')
    runner.add_argument('--task-profile', choices=('position', PV_PROFILE, MIXED_PROFILE), default='position')
    runner.add_argument('--px4-manifest')
    runner.add_argument('--px4-sha256')
    task=sub.add_parser('task')
    task.add_argument('--stack',choices=['arducopter','px4'],required=True)
    task.add_argument('--uav-id',type=int,required=True)
    task.add_argument('--planner-release-proof', action='store_true')
    task.add_argument('--scene-lifecycle', action='store_true')
    task.add_argument('--control-package')
    task.add_argument('--scene-module-sha')
    task.add_argument('--task-mode',choices=('initial','recover'),default='initial')
    task.add_argument('--task-profile', choices=('position', PV_PROFILE, MIXED_PROFILE), default='position')
    task.add_argument('--start-token')
    for name in ('run-id','scene-epoch','output'): task.add_argument('--'+name,required=True)
    args=parser.parse_args(argv)
    if args.planner_release_proof and args.task_profile != PV_PROFILE:
        parser.error('Planner release proof requires the explicit PV-capable profile')
    if args.role == 'run':
        pv = args.task_profile == PV_PROFILE
        mixed = args.task_profile == MIXED_PROFILE
        if args.async_model_evidence and not (pv or mixed):
            parser.error('--async-model-evidence is only allowed for PV/MIXED task profiles')
        if pv:
            pv_pair = bool(args.ap_pv_manifest and args.ap_pv_sha256 and not args.ap_mixed_manifest and not args.ap_mixed_sha256)
            mixed_pair = bool(args.ap_mixed_manifest and args.ap_mixed_sha256 and not args.ap_pv_manifest and not args.ap_pv_sha256)
            if (not (pv_pair or mixed_pair) or not args.message_manifest or not args.message_sha256
                    or args.ap_manifest or args.ap_sha256
                    or args.px4_manifest or args.px4_sha256 or args.pause_probe or args.scene_lifecycle
                    or args.scene_lease_loss or args.dds_loss or args.native_state_trace or args.probe_land_freshness):
                parser.error('P+V requires exactly one explicit PV or mixed AP manifest/SHA pair and no alternate probes')
        elif mixed:
            if (not args.ap_mixed_manifest or not args.ap_mixed_sha256 or args.ap_manifest or args.ap_sha256
                    or args.ap_pv_manifest or args.ap_pv_sha256 or args.px4_manifest or args.px4_sha256
                    or (args.message_manifest is None) != (args.message_sha256 is None)
                    or args.pause_probe or args.scene_lifecycle or args.scene_lease_loss or args.dds_loss
                    or args.native_state_trace or args.probe_land_freshness):
                parser.error('Mixed profile requires its own AP manifest/SHA and no alternate probes')
        elif (not args.ap_manifest or not args.ap_sha256 or args.ap_pv_manifest or args.ap_pv_sha256
                or args.ap_mixed_manifest or args.ap_mixed_sha256 or args.message_manifest or args.message_sha256):
            parser.error('Position experiment requires the existing AP clock manifest/SHA')
        if args.model_promotion_flight and (args.task_profile != 'position' or args.pause_probe
                or args.repeat_paused_clock or args.scene_lifecycle or args.scene_lease_loss
                or args.dds_loss or args.native_state_trace or args.probe_land_freshness):
            parser.error('Model promotion requires the fixed healthy position flight without alternate probes/candidates')
    if args.role == 'task' and args.task_profile in (PV_PROFILE, MIXED_PROFILE) and (args.task_mode != 'initial' or args.scene_lifecycle):
        parser.error('P+V task is a separate initial experimental flow')
    if args.role == 'run' and args.repeat_paused_clock and not args.pause_probe:
        parser.error('--repeat-paused-clock requires --pause-probe')
    if args.role == 'run' and args.scene_lifecycle and args.pause_probe:
        parser.error('--scene-lifecycle and --pause-probe are separate experiments')
    if args.role == 'run' and args.scene_lease_loss and not args.scene_lifecycle:
        parser.error('--scene-lease-loss requires --scene-lifecycle')
    if args.role == 'task' and args.scene_lifecycle and not (args.control_package and args.scene_module_sha):
        parser.error('Scene task requires the explicit sealed package and module SHA')
    if args.role == 'run' and args.dds_loss and (not args.scene_lifecycle or args.scene_lease_loss or args.pause_probe):
        parser.error('--dds-loss requires its own --scene-lifecycle experiment')
    if args.role == 'run' and args.probe_land_freshness and (not args.native_state_trace or not args.dds_loss):
        parser.error('--probe-land-freshness requires --native-state-trace and --dds-loss')
    if args.role == 'run' and (args.px4_manifest is None)!=(args.px4_sha256 is None):
        parser.error('Optional PX4 candidate requires both manifest and external SHA256')
    if args.role == 'run' and (args.message_manifest is None)!=(args.message_sha256 is None):
        parser.error('Explicit message candidate requires both manifest and external SHA256')
    if args.role == 'task' and args.task_mode == 'recover' and (not args.scene_lifecycle or not args.start_token):
        parser.error('New recovery task requires a scene and explicit start token')
    return task_main(args) if args.role=='task' else run(args)


if __name__ == '__main__':
    raise SystemExit(main())
