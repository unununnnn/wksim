"""Bounded common-time two-FC public Task flight, not a completed G2 product.

No physics pause, airborne loss recovery or collision/spawn-offset claim here.
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
from Simulator.wksim_runtime.isolation import check_isolation
from Simulator.wksim_runtime.config import load_config
from Simulator.wksim_runtime.preflight import preflight
from Simulator.wksim_runtime.runtime import launch_spec, stop_children, digest
from ap_clock_candidate import admit
from joint_control_candidate import check as check_control, environment as control_environment
from probe_joint_clock import json_identity, group_members
from joint_pause_probe import PauseProbe, PauseProbeComplete

WALL_LIMIT, MAX_TICKS = 900, 180000


def save(path, data):
    def evidence(value):
        if isinstance(value, float) and not math.isfinite(value):
            return {'nonfinite_number': repr(value)}
        if isinstance(value, dict):
            return {key:evidence(item) for key,item in value.items()}
        if isinstance(value, (list,tuple)):
            return [evidence(item) for item in value]
        return value
    Path(path).write_text(json.dumps(evidence(data), indent=2, allow_nan=False)+'\n')


def task_main(args):
    check_isolation()
    import rclpy
    from Simulator.wksim_runtime.task import Task
    root = Path(args.output)
    result = dict(status='failed', stack=args.stack, uav_id=args.uav_id,
                  run_id=args.run_id, scene_epoch=args.scene_epoch, phases=[])
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
        task = Task(root, health, phase, args.stack, run_id=args.run_id,
                    protocol='session_v1', uav_id=args.uav_id, use_sim_time=True,
                    scene_epoch=args.scene_epoch if args.scene_lifecycle else None)
        task.wait('joint_public_ready', lambda: task.fresh()
                  and task.setup_pub.get_subscription_count() == 1
                  and task.command_pub.get_subscription_count() == 1, 55)
        save(root/'ready.json', dict(run_id=args.run_id, scene_epoch=args.scene_epoch,
                                    uav_id=args.uav_id, control_epoch=task.epoch))
        while not (root.parent/'go.json').is_file():
            task.pump()
        go = json.loads((root.parent/'go.json').read_text())
        if go['epoch'] != args.scene_epoch:
            raise ValueError('Joint start belongs to another scene epoch')
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
    check_isolation()
    def interrupted(signum, frame):
        raise InterruptedError('Owned joint validation interrupted; not a production airborne stop policy')
    signal.signal(signal.SIGTERM, interrupted)
    if os.readlink('/proc/self/ns/mnt') == os.readlink('/proc/1/ns/mnt'):
        raise RuntimeError('Private mount namespace required')
    archive = Path(tempfile.mkdtemp(prefix='joint-public-flight-', dir=REPO/'validation'))
    live = Path(tempfile.mkdtemp(prefix='wksim-joint-flight-', dir='/root'))
    result = dict(status='failed', run_id=archive.name, scene_epoch=uuid.uuid4().hex,
                  pause_probe_requested=args.pause_probe,
                  scene_lifecycle_requested=args.scene_lifecycle,
                  scene_lease_loss_requested=args.scene_lease_loss,
                  require_clean_control_exit=True,
                  archive=str(archive), live=str(live), children={}, tasks={},
                  isolation={n: os.readlink('/proc/self/ns/'+n) for n in ('net','ipc','mnt')},
                  unowned_ap_before=json_identity(828),
                  bounds=dict(wall_seconds=WALL_LIMIT, simulation_ticks=MAX_TICKS,
                              task_position_error_m=.5, task_speed_m_s=.5,
                              takeoff_min_height_m=2.5, ground_abs_height_m=.3),
                  scope=__doc__)
    print(json.dumps(dict(archive=str(archive), live=str(live))), flush=True)
    children, expected_exits = [], set()
    clock, started = SceneClock(result['scene_epoch']), time.monotonic()
    pause_probe = lifecycle = None
    sources = ['tools/run_joint_flight.py','tools/run-joint-flight.sh','tools/joint_control_candidate.py',
               'tools/ap_clock_candidate.py','Simulator/wksim_core/joint.py','Simulator/wksim_core/worker.py',
               'Simulator/wksim_core/model.py','Simulator/wksim_core/model.cpp',
               'Simulator/wksim_core/ap_json.py','Simulator/wksim_core/px4_mavlink.py',
               'Simulator/wksim_runtime/scene_clock.py','Simulator/wksim_runtime/task.py',
               'tools/joint_pause_probe.py']
    if args.scene_lifecycle:
        sources += ['tools/joint_lifecycle.py']
    result['source_sha256'] = {name:digest(REPO/name) for name in sources}
    for name in sources:
        (live/('source__'+name.replace('/','__')+'.txt')).write_bytes((REPO/name).read_bytes())
    try:
        library = build_model()
        result['model_build'] = json.loads(library.with_name('build.json').read_text())
        configs = {stack:load_config(REPO/f'Simulator/wksim_runtime/examples/{stack}-session.json')
                   for stack in ('arducopter','px4')}
        for stack, config in configs.items():
            config['model_library'] = str(library)
            if stack == 'arducopter':
                configs[stack], admission = admit(config, args.ap_manifest, args.ap_sha256)
            else:
                admission = preflight(config)
            save(live/(stack+'-preflight.json'), admission)
            if not admission['ok']:
                raise ValueError('Fixed environment admission failed: '+str(admission['reasons']))
        control = check_control(args.control_manifest, args.control_sha256)
        if args.scene_lifecycle:
            sys.path.insert(0, str(Path(control['package']).parent))
        result['control_candidate'] = control
        result['manifest_sha256'] = dict(ap=args.ap_sha256, control=args.control_sha256)
        shutil.copyfile(args.ap_manifest, live/'ap-build.json')
        shutil.copyfile(args.control_manifest, live/'control-build.json')

        def health():
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
                if name.endswith('-task') and code == 0:
                    stack = name[:-5]
                    report = json.loads((live/stack/'result.json').read_text())
                    if (report['status'] != 'pass' or report['scene_epoch'] != clock.epoch
                            or report['run_id'] != result['run_id']):
                        raise RuntimeError('Task exited without matching successful result')
                    expected_exits.add(child.pid)
                    result['tasks'][stack] = report
                else:
                    raise RuntimeError(f'{name} exited unexpectedly: {code}')

        def launch(name, argv, cwd, env=None):
            log = (live/(name+'.log')).open('x')
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=log,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
            children.append((name,child,log))
            result['children'][name] = dict(identity=json_identity(child.pid), argv=argv, cwd=str(cwd))
            return child

        import rclpy
        rclpy.init(args=[])
        with ExitStack() as resources:
            resources.callback(rclpy.shutdown)
            node = rclpy.create_node('wksim_joint_flight_clock')
            resources.callback(node.destroy_node)
            publisher = ClockPublisher(node)
            resources.callback(publisher.close)
            if args.pause_probe or args.scene_lifecycle:
                pause_probe = PauseProbe(node, clock, live, started, args.repeat_paused_clock)
                resources.callback(pause_probe.close)
            wire = resources.enter_context((live/'joint-wire.jsonl').open('x', buffering=65536))
            clock_log = resources.enter_context((live/'clock.jsonl').open('x', buffering=65536))
            def record(kind, **data):
                wire.write(json.dumps(dict(kind=kind, epoch=clock.epoch,tick=clock.tick,
                                          wall=time.monotonic()-started,**data),separators=(',',':'),allow_nan=False)+'\n')
            workers = {}
            physics = JointPhysics(resources, clock, workers, health, record)
            publisher.publish(clock)
            clock_log.write(json.dumps(clock.snapshot())+'\n')
            if args.scene_lifecycle:
                # Use the explicitly sealed candidate package for the shared
                # permission schema as well as the actual controller process.
                from joint_lifecycle import JointLifecycle
                lifecycle = JointLifecycle(node, clock, publisher, live, result['run_id'], started, pause_probe)
                resources.callback(lifecycle.close)
            for stack, uid in (('arducopter',1),('px4',2)):
                directory = live/stack
                directory.mkdir()
                (directory/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
                log = (live/(stack+'-model.log')).open('x')
                argv = [sys.executable,'-B','-m','Simulator.wksim_core.worker','--library',str(library),
                        '--trace',str(live/(stack+'-truth.jsonl')),'--epoch',clock.epoch]
                child = subprocess.Popen(argv,cwd=directory,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                         stderr=log,text=True,start_new_session=True)
                children.append((stack+'-model',child,log)); workers[stack]=child
                result['children'][stack+'-model'] = dict(identity=json_identity(child.pid),argv=argv,cwd=str(directory))
                plan = launch_spec(configs[stack], directory, library)
                launch(stack+'-agent',plan['agent'],directory)
                launch(stack+'-fc',plan['fc'],directory,dict(os.environ,**plan['fc_environment']))
                result['children'][stack+'-fc']['environment_overrides'] = plan['fc_environment']
                for index, value in enumerate(plan['control']):
                    if value.startswith('uav_id:='): plan['control'][index] = 'uav_id:='+str(uid)
                    if value.startswith('run_id:='): plan['control'][index] = 'run_id:='+result['run_id']
                plan['control'] += ['-p','use_sim_time:=true','-r','__node:=wksim_joint_'+stack+'_control']
                if args.scene_lifecycle:
                    plan['control'] += ['-p', 'scene_epoch:='+clock.epoch]
                verifier = ('import importlib.util,pathlib; '
                    'assert pathlib.Path(importlib.util.find_spec("prometheus_control").origin).parent == pathlib.Path('
                    +repr(control['package'])+'); import prometheus_control.node as n; n.main()')
                command = [sys.executable,'-B','-c',verifier,*plan['control'][3:]]
                launch(stack+'-control',command,directory,control_environment(control))
                task_command = [sys.executable,'-B',str(Path(__file__).resolve()),'task',
                    '--stack',stack,'--uav-id',str(uid),'--run-id',result['run_id'],
                    '--scene-epoch',clock.epoch,'--output',str(directory)]
                if args.scene_lifecycle:
                    task_command += ['--scene-lifecycle']
                launch(stack+'-task', task_command, directory,
                       control_environment(control) if args.scene_lifecycle else None)
            save(live/'children-start.json',result['children'])
            physics.connect()
            summaries = {name:dict(max_height_m=0., min_waypoint_error_m=1e30) for name in workers}
            def advance():
                states = physics.advance()
                publisher.publish(clock)
                clock_log.write(json.dumps(clock.snapshot(),separators=(',',':'))+'\n')
                return states
            while clock.tick < MAX_TICKS:
                states = advance()
                if not (live/'go.json').exists() and all((live/name/'ready.json').exists() for name in workers):
                    save(live/'go.json', clock.snapshot())
                for name,state in states.items():
                    import math
                    row=summaries[name]
                    row['max_height_m']=max(row['max_height_m'],-state[8])
                    row['min_waypoint_error_m']=min(row['min_waypoint_error_m'],math.dist(state[6:9],[3,2,-3]))
                    row['final_height_m']=-state[8]
                if clock.tick % 5000 == 0:
                    print(json.dumps(dict(tick=clock.tick,heights={k:round(-v[8],3) for k,v in states.items()},
                                          completed_tasks=list(result['tasks']))),flush=True)
                if lifecycle is not None and not lifecycle.completed and pause_probe.ready(result['run_id'], states):
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
            if any(row['max_height_m']<2.5 or row['min_waypoint_error_m']>.5 or abs(row['final_height_m'])>.3
                   for row in summaries.values()):
                raise ValueError('Independent model truth failed the fixed flight bounds')
            result['truth_summary'] = summaries
            result['clock_publications'] = publisher.publications
            result['paused_clock_republications'] = publisher.paused_republications
            if args.scene_lifecycle and (lifecycle is None or not lifecycle.completed):
                raise RuntimeError('Requested lifecycle exercise did not complete')
            clock.request(dict(version=1,epoch=clock.epoch,request_id=clock.last_request+1,action='stop'))
            result['final_authority'] = clock.snapshot()
            for child in workers.values():
                child.stdin.close(); child.wait(timeout=3)
                if child.returncode: raise RuntimeError('Model did not close normally')
            result['status']='pass'
    except PauseProbeComplete as error:
        result.update(status='observed', observation=str(error))
    except BaseException as error:
        clock.fault(str(error))
        result.update(error=repr(error),traceback=traceback.format_exc(),faulted_authority=clock.snapshot())
        print('Joint flight failed: '+repr(error),flush=True)
    finally:
        result['flight_completed'] = result['status']=='pass'
        result['cleanup_errors']=stop_children(children)
        for name,child,_ in children:
            result['children'][name].update(returncode=child.returncode,remaining_group_members=group_members(child.pid))
        result['unowned_ap_after']=json_identity(828)
        result['source_unchanged']=result['source_sha256']=={name:digest(REPO/name) for name in sources}
        result['control_shutdown_clean']=all(child['returncode']==0 for name,child in result['children'].items()
                                             if name.endswith('-control'))
        if result['status'] in ('pass', 'observed') and not result['control_shutdown_clean']:
            result['status'], result['error'] = 'failed', 'Control nodes did not stop normally'
        if (result['cleanup_errors'] or any(v['remaining_group_members'] for v in result['children'].values())
                or not result['source_unchanged'] or result['unowned_ap_before']!=result['unowned_ap_after']):
            result['status']='failed'
        result['wall_seconds']=time.monotonic()-started
        save(live/'result.json',result)
        shutil.copytree(live,archive,dirs_exist_ok=True)
        print(json.dumps(dict(status=result['status'],archive=str(archive),error=result.get('error'),
                              wall_seconds=result['wall_seconds'])),flush=True)
    return 0 if result['status'] in ('pass', 'observed') else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='role',required=True)
    runner=sub.add_parser('run')
    runner.add_argument('--pause-probe', action='store_true',
                        help='Observe four wall seconds at a true airborne pause, then stop without resuming')
    runner.add_argument('--repeat-paused-clock', action='store_true',
                        help='Explicit pause-probe candidate: re-publish the committed frozen clock every 100ms')
    runner.add_argument('--scene-lifecycle', action='store_true',
                        help='Approved opt-in permission candidate: long pause, four ticks, pause, explicit resume')
    runner.add_argument('--scene-lease-loss', action='store_true',
                        help='Withhold permission at an airborne pause, observe withdrawal and no automatic recovery, then stop')
    for name in ('ap-manifest','ap-sha256','control-manifest','control-sha256'):
        runner.add_argument('--'+name,required=True)
    task=sub.add_parser('task')
    task.add_argument('--stack',choices=['arducopter','px4'],required=True)
    task.add_argument('--uav-id',type=int,required=True)
    task.add_argument('--scene-lifecycle', action='store_true')
    for name in ('run-id','scene-epoch','output'): task.add_argument('--'+name,required=True)
    args=parser.parse_args()
    if args.role == 'run' and args.repeat_paused_clock and not args.pause_probe:
        parser.error('--repeat-paused-clock requires --pause-probe')
    if args.role == 'run' and args.scene_lifecycle and args.pause_probe:
        parser.error('--scene-lifecycle and --pause-probe are separate experiments')
    if args.role == 'run' and args.scene_lease_loss and not args.scene_lifecycle:
        parser.error('--scene-lease-loss requires --scene-lifecycle')
    raise SystemExit(task_main(args) if args.role=='task' else run(args))
