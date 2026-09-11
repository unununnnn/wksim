"""Formal joint service: one private process/network generation per scene epoch."""
import argparse
import hashlib
import stat
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import time
import traceback
import uuid

from .evidence import write_json,json_identity,group_members,host_boot_id
from .isolation import check_isolation,isolate_temporary_files,Reservation
from .joint_actions import Mailbox
from .joint_config import validate_joint_config,FIXED_TASKS
from .joint_aruco_profile import TASK as ARUCO_TASK
from .joint_trajectory import supported_actions,validate_initialized,coordinate_legs
from .joint_rate import JointRate,RateUnmet
from .joint_evidence import verify_tasks,final_run_status,task_group_completed,load_retired_task_report
from .scene_clock import SceneClock,ClockPublisher
from .terrain_feedback import TerrainFeedback
from ..wksim_core.joint import JointPhysics,InputTimeout
from ..wksim_core.joint_state_stream import JointStateWriter,hex_identity

REPO=Path(__file__).resolve().parents[2]


class OperatorRetirement(Exception):
    pass


def resume_confirmed(lifecycle,clock,request):
    ready=lifecycle.acknowledged() and clock.tick%4==0
    if time.monotonic()-request['began']>=5:
        raise TimeoutError('Resume did not obtain fresh native state in 5s')
    if ready and any(value['source_boot_ns']<=request['frozen_ns'] for value in lifecycle.acks.values()):
        raise ValueError('Resume used old native state')
    return ready


def image_identity(child,original,*,allow_exited=False):
    code=child.poll()
    if allow_exited and code is not None:
        return dict(state='exited',identity=original,returncode=code,maps_available=False)
    current=json_identity(child.pid)
    if current is None or any(current[key]!=original[key] for key in ('pid','pgid','start_ticks')):
        raise RuntimeError('Runtime image process identity changed')
    return dict(state='running',identity=current)


def stop_processes(children):
    errors=[]
    for name,child,log in reversed(children):
        try:
            if child.poll() is None:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill();child.wait(timeout=5)
        except (OSError,subprocess.TimeoutExpired) as error:
            errors.append(dict(name=name,error=repr(error)))
        log.close()
    return errors


def epoch_run(directory,epoch,generation=1):
    from .runtime import launch_spec,digest
    from .joint_monitor import JointMonitor
    from .joint_lifecycle import JointLifecycle
    from rosidl_runtime_py.convert import message_to_ordereddict
    import rclpy
    check_isolation()
    config=validate_joint_config(json.loads((directory/'config.json').read_text()))
    fixed_task=config['task'] in FIXED_TASKS
    aruco_task=config['task'] == ARUCO_TASK
    defer_task_reports=aruco_task or fixed_task
    async_evidence=os.environ.get('WKSIM_JOINT_ASYNC_EVIDENCE')=='1'
    async_model_evidence=os.environ.get('WKSIM_JOINT_ASYNC_MODEL_EVIDENCE')=='1'
    if (async_evidence or async_model_evidence) and not aruco_task:
        raise ValueError('Background evidence writes require the explicit ArUco experiment')
    session=json.loads((directory/'session.json').read_text())
    if (set(session)!={'version','run_id','instance_id'} or session['version']!=1
            or session['run_id']!=config['run_id'] or not hex_identity(session['instance_id'])
            or type(generation) is not int or generation<1):
        raise ValueError('Invalid joint manager display identity')
    output=directory/'epochs'/epoch
    output.mkdir(parents=True)
    result=dict(version=1,run_id=config['run_id'],epoch=epoch,status='failed',children={},tasks={},
                action_results=[],host_boot_id=host_boot_id(),flight_completed=False,
                instance_id=session['instance_id'],generation=generation,task_profile=config['task'])
    view=JointStateWriter(None,config['run_id'],session['instance_id'],epoch,generation)
    physics=None
    clock=SceneClock(epoch)
    evidence_streams=[]
    def open_evidence(path,buffering):
        if async_evidence:
            from .evidence_stream import AsyncEvidenceStream
            stream=AsyncEvidenceStream(path)
            evidence_streams.append((Path(path).name,stream))
            return stream
        return Path(path).open('x',buffering=buffering)
    rate_log=open_evidence(output/'rate.jsonl',65536)
    write_probe=write_log=None
    if os.environ.get('WKSIM_JOINT_WRITE_TIMING')=='1':
        from .write_timing import WriteTiming
        write_log=(output/'write-timing.jsonl').open('x',buffering=1)
        write_probe=WriteTiming(write_log,epoch,lambda:clock.tick)
    def record_rate(kind,**fields):
        text=json.dumps(dict(kind=kind,epoch=epoch,tick=clock.tick,
            issued_monotonic_ns=time.monotonic_ns(),**fields),allow_nan=False,separators=(',',':'))+'\n'
        if write_probe: write_probe.write(rate_log,'rate',text)
        else: rate_log.write(text)
    rate=JointRate(epoch,config['requested_rate'],record_rate)
    record_rate('rate_bootstrap',classification='untimed_until_first_synchronized_barrier')
    result['requested_rate']=config['requested_rate']
    result['task_dwell_seconds']=config['task_dwell_seconds']
    mailbox=Mailbox(directory,config['run_id'],epoch)
    children=[]; specs={}; expected=set(); model_workers={}; agents={}
    monitor=lifecycle=probe=None
    task_group=None; task_state='idle'; ever_started=False; needs_recovery_task=False
    offer=uuid.uuid4().hex; previous_offer=None; next_status=0.; pending=None; busy_phase=None
    pending_task_reanchor=False
    physics_wait_started=None; last_child_poll=0.
    started=time.monotonic()
    # Own-process scheduling priority for the latency-critical lockstep loop.
    # A negative nice needs privilege; the actual value is recorded either way
    # so a run never silently claims a priority it did not receive.
    try:
        os.nice(-10)
        result['manager_priority']=dict(target=-10,applied=os.getpriority(os.PRIO_PROCESS,0))
    except OSError as error:
        result['manager_priority']=dict(target=-10,error=repr(error))
    # Real-time scheduling bounds preemption by ordinary processes; RT
    # throttling and host jitter still apply and are not claimed away.
    try:
        # Explicit camera experiment: ordinary children and background threads
        # must not inherit the supervisor's FIFO/50 policy. Native model/FC
        # leaders are still explicitly configured by child_priority below.
        scheduler_policy=os.SCHED_FIFO | (os.SCHED_RESET_ON_FORK if aruco_task else 0)
        os.sched_setscheduler(0,scheduler_policy,os.sched_param(50))
        result['manager_scheduler']=dict(policy='SCHED_FIFO',priority=50,
                                         reset_on_fork=aruco_task,actual_policy=os.sched_getscheduler(0))
    except OSError as error:
        result['manager_scheduler']=dict(policy='SCHED_FIFO',priority=50,error=repr(error))
    def interrupted(signum,frame):
        raise InterruptedError('Owned joint epoch interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    def status(allowed,phase=None):
        nonlocal offer,previous_offer,next_status
        allowed=supported_actions(config['task'],allowed)
        identity=(clock.last_request,mailbox.last_command,phase or clock.phase,task_state,tuple(allowed))
        if identity!=previous_offer:
            offer=uuid.uuid4().hex;previous_offer=identity
        visible_phase=phase or busy_phase or (lifecycle.phase if lifecycle else clock.phase)
        row=dict(version=1,kind='joint_scene',run_id=config['run_id'],epoch=epoch,
            instance_id=session['instance_id'],generation=generation,
            epoch_dir=str(output),phase=visible_phase,authority=clock.snapshot(),task_state=task_state,
            allowed_actions=allowed,offer_token=offer,issued_monotonic_s=time.monotonic(),
            supervisor=json_identity(os.getpid()),last_command_id=mailbox.last_command,
            participants={str(uid):message_to_ordereddict(value) for uid,value in (monitor.sessions.items() if monitor else [])})
        row['rate']=rate.snapshot(clock.tick)
        row['display_stream']=dict(enabled=view.socket is not None,sent=view.sent,dropped=view.dropped,
                                   sequence=view.sequence,setup_error=view.setup_error,last_error=view.last_error)
        row['rate']['last_segment']=rate.last_summary
        row['task_dwell_seconds']=config['task_dwell_seconds']
        row['task_progress']={}
        if task_group is not None:
            for stack in ('arducopter','px4'):
                path=task_group/stack/'progress.json'
                if path.is_file(): row['task_progress'][stack]=json.loads(path.read_text())
        write_json(directory/'status.json',row)
        next_status=time.monotonic()+.1
        return row
    status(['stop'],'starting')
    def child_priority(child,role):
        # Only this manager's own children are ever reniced, right after spawn.
        target=-10 if role in ('model','fc') else -5
        record=dict(target=target)
        try:
            os.setpriority(os.PRIO_PROCESS,child.pid,target)
            record['applied']=os.getpriority(os.PRIO_PROCESS,child.pid)
        except OSError as error:
            record['error']=repr(error)
        # Real-time scheduling only for the lockstep-critical model/FC pair;
        # the applied policy is recorded, never silently assumed.
        if role in ('model','fc'):
            try:
                reset_model_threads=role=='model' and async_model_evidence
                policy=os.SCHED_FIFO | (os.SCHED_RESET_ON_FORK if reset_model_threads else 0)
                os.sched_setscheduler(child.pid,policy,os.sched_param(40))
                record['scheduler']=dict(policy='SCHED_FIFO',priority=40,
                                         reset_on_fork=reset_model_threads,
                                         actual_policy=os.sched_getscheduler(child.pid))
            except OSError as error:
                record['scheduler']=dict(policy='SCHED_FIFO',priority=40,error=repr(error))
        if aruco_task:
            try:
                record['observed_scheduler']=dict(policy=os.sched_getscheduler(child.pid),
                    priority=os.sched_getparam(child.pid).sched_priority)
            except OSError as error:
                record['observed_scheduler']=dict(error=repr(error))
        return record
    def launch(name,argv,cwd,role):
        log=(output/(name+'.log')).open('x')
        child=subprocess.Popen(argv,cwd=cwd,stdout=log,stderr=log,stdin=subprocess.DEVNULL)
        children.append((name,child,log));specs[child.pid]=dict(name=name,argv=argv,cwd=Path(cwd),role=role)
        result['children'][name]=dict(identity=json_identity(child.pid),argv=argv,cwd=str(cwd),
                                      priority=child_priority(child,role))
        write_json(output/'children.json',result['children'])
        return child
    def physics_health():
        nonlocal last_child_poll
        for _,stream in evidence_streams:
            stream.check()
        if lifecycle is not None:
            lifecycle.periodic()
        now=time.monotonic()
        if (busy_phase or physics_wait_started is not None and now-physics_wait_started>=.05) and now>=next_status:
            status(['stop','cold-reset'],busy_phase or 'waiting_input_or_model')
            request=mailbox.poll(offer,['stop','cold-reset'],only={'stop','cold-reset'})
            if request is not None:
                clock_action('stop');lifecycle.set_phase('stopped')
                result['stop_request']=request
                result['status']='cold_reset' if request['action']=='cold-reset' else 'stopped'
                raise OperatorRetirement(request['action'])
        # Child liveness is polled at most once per millisecond: health runs at
        # least once per 1ms tick, so exit detection stays <=1ms, far inside
        # the approved 100ms/500ms/2s/3s/5s supervision budgets. Deadline,
        # permission and operator-request checks above still run every call.
        if now>=last_child_poll+.001:
            last_child_poll=now
            if probe is not None: probe.pump()
            for name,child,_ in children:
                if child.poll() is not None and child.pid not in expected and specs[child.pid]['role'] in ('model','fc','control'):
                    expected.add(child.pid)
                    raise RuntimeError(f'{name} exited: {child.returncode}')
    def record_images(label):
        observed={}
        for name,child,_ in children:
            if specs[child.pid]['role'] not in ('model','fc'): continue
            original=result['children'][name]['identity']
            identity=image_identity(child,original,allow_exited=label=='stopping')
            if identity['state']=='exited':
                observed[name]=identity
                continue
            current=identity['identity']
            process=Path('/proc')/str(child.pid)
            executable=(process/'exe').resolve(strict=True)
            if executable!=Path(specs[child.pid]['argv'][0]).resolve(strict=True):
                raise RuntimeError('Runtime executable changed: '+name)
            content=(process/'maps').read_text()
            forbidden=[token for token in ('libgz-','libgazebo','libignition','matlab','coptersim.exe') if token in content.lower()]
            if forbidden: raise RuntimeError('Independent core loaded forbidden runtime: '+str(forbidden))
            path=output/(name+'-'+label+'-maps.txt');path.write_text(content)
            observed[name]=dict(identity=current,executable=str(executable),executable_sha256=digest(executable),
                maps_file=path.name,maps_sha256=digest(path),forbidden_libraries=forbidden)
            if specs[child.pid]['role']=='model' and str(admission['model_library']) not in content:
                raise RuntimeError('Admitted model library not found in actual process maps')
        result.setdefault('runtime_images',{})[label]=observed
    def complete(request,**fields):
        status(['stop','cold-reset'])
        record=mailbox.respond(request,'completed',authority=clock.snapshot(),**fields)
        result['action_results'].append(record)
    def clock_action(action):
        return clock.request(dict(version=1,epoch=epoch,request_id=clock.last_request+1,action=action))
    def start_tasks(mode,prepare_only=False):
        nonlocal task_group,task_state,ever_started
        if (fixed_task or aruco_task) and mode!='initial':
            raise ValueError('Fixed trajectory recovery is unsupported; use cold-reset')
        if mode=='initial' and task_group is not None and not ever_started and not prepare_only:
            task_state='preparing';ever_started=True
            return
        task_id=uuid.uuid4().hex
        task_group=output/'tasks'/task_id
        task_group.mkdir(parents=True)
        for stack,uid in (('arducopter',1),('px4',2)):
            folder=task_group/stack;folder.mkdir()
            settings=dict(run_id=config['run_id'],epoch=epoch,stack=stack,uav_id=uid,mode=mode,
                          token=uuid.uuid4().hex,parent=json_identity(os.getpid()),control_package=admission['control_package'],
                          task_dwell_seconds=config['task_dwell_seconds'],task_type=config['task'])
            if aruco_task:
                profile=json.loads((Path(__file__).with_name('aruco-tracking-v1.json')).read_text())
                scene=output/'aruco';scene.mkdir(exist_ok=True)
                settings['aruco_settings']=dict(profile=profile,scene_directory=str(scene),
                    binding_path=str(scene/'binding.json'),observation_path=str(scene/'observation.json'),
                    selected_stack=config['aruco_experiment']['selected_stack'],
                    instance_id=session['instance_id'],generation=generation)
            write_json(folder/'task-config.json',settings)
            launch(stack+'-task-'+task_id,[sys.executable,'-B','-m','Simulator.wksim_runtime.joint_task',
                                         str(folder/'task-config.json')],folder,'task')
        if not prepare_only:
            task_state='preparing';ever_started=True
    try:
        # The expensive, read-only identity walk must not block operator stop.
        # It runs in an owned child of this same private epoch process group.
        preflight=launch('preflight',[sys.executable,'-B','-m','Simulator.wksim_runtime.runtime',
                         str(directory/'config.json'),'--prepared','--preflight'],output,'preflight')
        while preflight.poll() is None:
            if time.monotonic()>=next_status:
                status(['stop'],'starting')
                stop=mailbox.poll(offer,['stop'])
                if stop is not None:
                    clock_action('stop');result['stop_request']=stop
                    result['status']='stopped'
                    return result
            time.sleep(.02)
        expected.add(preflight.pid)
        admission=json.loads((output/'preflight.log').read_text())
        result['preflight']=admission
        write_json(output/'preflight.json',admission)
        if not admission['ok']:
            raise RuntimeError('Joint profile rejected: '+str(admission['reasons']))
        if config['task'] not in admission['capabilities']:
            raise ValueError('Selected joint task is not an admitted capability')
        stop=mailbox.poll(offer,['stop'])
        if stop is not None:
            clock_action('stop');result['stop_request']=stop
            result['status']='stopped'
            return result
        result['isolation']={name:os.readlink('/proc/self/ns/'+name) for name in ('net','ipc','mnt')}
        result['private_temporary_files']=isolate_temporary_files(
            [config['display_socket']] if config.get('display_socket') else ())
        view=JointStateWriter(config.get('display_socket'),config['run_id'],session['instance_id'],epoch,generation)
        library=Path(admission['model_library'])
        result['source_sha256']={str(path.relative_to(REPO)):digest(path) for folder in
            (REPO/'Simulator/wksim_runtime',REPO/'Simulator/wksim_core') for path in folder.glob('*.py')}
        result['source_sha256']['Simulator/wksim_core/model.cpp']=digest(REPO/'Simulator/wksim_core/model.cpp')
        if aruco_task:
            for name in ('Simulator/wksim_runtime/aruco-tracking-v1.json',
                         'Simulator/wksim_perception/aruco.py','Simulator/wksim_perception/target_intent.py',
                         'tools/joint_control_candidate.py','tools/px4_land_candidate.py'):
                result['source_sha256'][name]=digest(REPO/name)
            result['experimental']=True
            result['production_admitted']=False
            if admission.get('native_component_timing'):
                candidate=admission['identities']['px4_candidate']
                result['native_component_timing']=dict(environment=candidate['environment'],
                                                       parent_manifest=candidate['parent_manifest'])
                for name in ('tools/px4_component_candidate.py','tools/build-px4-component-timing.sh',
                             'patches/px4/0005-component-wait-tracing.patch'):
                    result['source_sha256'][name]=digest(REPO/name)
                result['native_px4_source_sha256']=candidate['expected_sources']
                for name,checksum in candidate['expected_sources'].items():
                    path=output/'source/native_px4'/name;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes((Path(candidate['root'])/'src'/name).read_bytes())
                    if digest(path)!=checksum:raise ValueError('Native diagnostic source changed during retention')
        observe_px4_setup=os.environ.get('WKSIM_OBSERVE_PX4_SETUP')=='1'
        if observe_px4_setup:
            result['source_sha256']['tools/observe_px4_setup.py']=digest(REPO/'tools/observe_px4_setup.py')
            result['diagnostics']=dict(px4_setup_observer=True,scope='receiver/setup observations only; no decision replacement')
        if fixed_task:
            for name in ('pv_trajectory_task.py','mixed_control_task.py','audit_joint_trajectory.py',
                         'audit_pv_trajectory.py','audit_mixed_control.py','audit_joint_flight.py',
                         'audit_joint_rate.py','audit_joint_product.py','audit_joint_product_lifecycle.py',
                         'ap_mixed_candidate.py','ap_pv_candidate.py','prepare_ap_mixed_candidate.py',
                         'verify_ap_pv_candidate.py','prepare_ap_pv_candidate.py','joint_control_candidate.py'):
                result['source_sha256']['tools/'+name]=digest(REPO/'tools'/name)
            for name in ('tools/run-wksim.sh','Simulator/wksim_core/arducopter-quad-x.parm',
                         'Simulator/wksim_runtime/joint-profiles.json'):
                result['source_sha256'][name]=digest(REPO/name)
            native=Path(admission['configs']['arducopter']['ap_candidate'])/'src/ArduCopter/Log.cpp'
            target=output/'native-source/ArduCopter/Log.cpp';target.parent.mkdir(parents=True)
            target.write_bytes(native.read_bytes())
            result['native_source_sha256']={'ArduCopter/Log.cpp':digest(target)}
            source_manifest=native.parents[2]/'mixed-source.json'
            (output/'mixed-source.json').write_bytes(source_manifest.read_bytes())
            for key,pin in admission['profile']['manifests'].items():
                target=output/(key+'-build.json');target.write_bytes(Path(pin['path']).read_bytes())
                if digest(target)!=pin['sha256']: raise ValueError('Admitted build changed during retention: '+key)
            control=json.loads((output/'control-build.json').read_text())
            for name,sha in control['python_sha256'].items():
                target=output/'control-source'/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((Path(admission['control_package'])/name).read_bytes())
                if digest(target)!=sha: raise ValueError('Admitted control source changed during retention: '+name)
        for name,expected_sha in result['source_sha256'].items():
            snapshot=output/'source'/name;snapshot.parent.mkdir(parents=True,exist_ok=True)
            snapshot.write_bytes((REPO/name).read_bytes())
            if digest(snapshot)!=expected_sha: raise RuntimeError('Source changed while recording '+name)
        rclpy.init(args=[])
        with ExitStack() as resources:
            resources.callback(rclpy.try_shutdown)
            node=rclpy.create_node('wksim_joint_supervisor')
            resources.callback(node.destroy_node)
            publisher=ClockPublisher(node);resources.callback(publisher.close)
            monitor=JointMonitor(node,output,clock,write_probe=write_probe,
                                 log_factory=open_evidence if async_evidence else None);resources.callback(monitor.close)
            if fixed_task:
                from tools.pv_trajectory_task import PVProbe
                probe=PVProbe(node,clock,output,started);resources.callback(probe.close)
            wire=resources.enter_context(open_evidence(output/'wire.jsonl',65536))
            clocks=resources.enter_context(open_evidence(output/'clock.jsonl',65536))
            def record(kind,**fields):
                text=json.dumps(dict(kind=kind,epoch=epoch,tick=clock.tick,
                    issued_monotonic_s=time.monotonic(),**fields),separators=(',',':'))+'\n'
                if write_probe: write_probe.write(wire,'wire',text)
                else: wire.write(text)
            def record_clock(text):
                if write_probe: write_probe.write(clocks,'clock',text)
                else: clocks.write(text)
            terrain_feedback=TerrainFeedback(epoch)
            physics=JointPhysics(resources,clock,model_workers,physics_health,record,
                                 terrain_feedback=terrain_feedback)
            from .loop_timing import LoopTiming
            loop_timing=LoopTiming(physics.cpu_timing,record)
            publisher.publish(clock);record_clock(json.dumps(clock.snapshot())+'\n')
            lifecycle=JointLifecycle(node,clock,publisher,output,config['run_id'],started,monitor,
                                     write_probe=write_probe,log_factory=open_evidence if async_evidence else None)
            resources.callback(lifecycle.close)
            for stack,uid in (('arducopter',1),('px4',2)):
                folder=output/stack;folder.mkdir()
                (folder/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
                argv=[sys.executable,'-B','-m','Simulator.wksim_core.worker','--library',str(library),
                      '--trace',str(output/(stack+'-truth.jsonl')),'--epoch',epoch]
                if async_model_evidence: argv.append('--async-evidence')
                log=(output/(stack+'-model.log')).open('x')
                child=subprocess.Popen(argv,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
                name=stack+'-model';children.append((name,child,log));model_workers[stack]=child
                specs[child.pid]=dict(name=name,role='model',cwd=folder,argv=argv)
                result['children'][name]=dict(identity=json_identity(child.pid),argv=argv,cwd=str(folder),
                                              priority=child_priority(child,'model'))
                plan=launch_spec(admission['configs'][stack],folder,library,
                                 admitted_capabilities=admission['capabilities'])
                if stack=='px4' and admission.get('native_component_timing'):
                    plan['fc_environment'].update(admission['identities']['px4_candidate']['environment'])
                agents[stack]=launch(stack+'-agent',plan['agent'],folder,'agent')
                log=(output/(stack+'-fc.log')).open('x')
                child=subprocess.Popen(plan['fc'],cwd=folder,env=dict(os.environ,**plan['fc_environment']),
                    stdout=log,stderr=log,stdin=subprocess.DEVNULL)
                name=stack+'-fc';children.append((name,child,log))
                specs[child.pid]=dict(name=name,role='fc',cwd=folder,argv=plan['fc'])
                result['children'][name]=dict(identity=json_identity(child.pid),argv=plan['fc'],cwd=str(folder),
                                              priority=child_priority(child,'fc'))
                if stack=='px4' and admission.get('native_component_timing'):
                    result['children'][name]['explicit_environment']=dict(plan['fc_environment'])
                argv=plan['control']
                argv=[f'uav_id:={uid}' if value.startswith('uav_id:=') else value for value in argv]
                argv+=['-p','use_sim_time:=true','-p','scene_epoch:='+epoch,
                       '-r','__node:=wksim_joint_'+stack+'_control']
                if observe_px4_setup and stack=='px4':
                    if argv[1:3]!=['-m','prometheus_control.node']:
                        raise ValueError('Unexpected Control launch shape for setup observer')
                    argv=[sys.executable,'-B','-m','tools.observe_px4_setup',str(output/'px4-setup-observer.jsonl'),
                        admission['control_package'],*argv[3:]]
                launch(stack+'-control',argv,folder,'control')
            # Process startup, DDS discovery and binary hashing belong before
            # paced physics. The staged Task workers cannot execute without
            # the go file written only after an explicit start-task request.
            busy_phase='initializing_task_transport'
            start_tasks('initial',prepare_only=True)
            initialization_deadline=time.monotonic()+15
            while not all((task_group/stack/'initialized.json').is_file() for stack in ('arducopter','px4')):
                physics_health()
                if time.monotonic()>=initialization_deadline:
                    raise TimeoutError('Task transport initialization exceeded 15s before clock start')
                time.sleep(.002)
            for stack in ('arducopter','px4'):
                initialized=json.loads((task_group/stack/'initialized.json').read_text())
                settings=json.loads((task_group/stack/'task-config.json').read_text())
                validate_initialized(initialized,settings)
            initial_models=lifecycle.snapshot(physics)
            if clock.tick!=0 or any(value['tick']!=0 for value in initial_models['models'].values()):
                raise RuntimeError('Startup observation advanced the physical clock')
            initial_states=lifecycle.initial_states(physics)
            if clock.tick!=0 or any(value['tick']!=0 or value.get('initial') is not True
                                    for value in initial_states.values()):
                raise RuntimeError('Explicit initial-state observation advanced the physical clock')
            physics.initialize_states(initial_states)
            record_images('ready')
            if aruco_task:
                scheduler_snapshot={}
                processes=[('supervisor',os.getpid())]+[(name,child.pid) for name,child,_ in children if child.poll() is None]
                for name,pid in processes:
                    threads=[]
                    for entry in (Path('/proc')/str(pid)/'task').iterdir():
                        try:
                            tid=int(entry.name)
                            threads.append(dict(tid=tid,name=(entry/'comm').read_text().strip(),
                                policy=os.sched_getscheduler(tid),priority=os.sched_getparam(tid).sched_priority))
                        except (OSError,ValueError) as error:
                            threads.append(dict(tid=entry.name,error=repr(error)))
                    scheduler_snapshot[name]=dict(pid=pid,threads=threads)
                result['scheduler_snapshot']=scheduler_snapshot
            result['initialization']=dict(physical_tick=0,models=initial_models,initial_states=initial_states,
                terrain_feedback=terrain_feedback.manifest(),task_execution_requires_explicit_go=True)
            record_rate('transport_initialized',physical_tick=0,task_execution_requires_explicit_go=True)
            busy_phase=None
            physics.connect()
            def latch_failure(error):
                nonlocal task_state,needs_recovery_task,busy_phase,pending
                # Both model responses may have committed before an input wait
                # failed. Publish that real tick once; never publish a partial RPC.
                if (clock.pending is None and clock.phase in ('running','stepping')
                        and publisher.last_tick is not None and clock.tick==publisher.last_tick+1):
                    publisher.publish(clock);record_clock(json.dumps(clock.snapshot())+'\n')
                if isinstance(error,RateUnmet):
                    # The rate supervisor is called only outside model groups.
                    # No rollback and no partially completed barrier is hidden.
                    try: clock.suspend(str(error))
                    except ValueError: clock.fault(str(error))
                elif isinstance(error,InputTimeout) and clock.phase in ('running','stepping'):
                    try: clock.suspend_input(str(error))
                    except ValueError: clock.fault(str(error))
                elif not (isinstance(error,TimeoutError) and clock.phase=='faulted'
                          and clock.recoverable and clock.pending is None):
                    clock.fault(str(error))
                rate.close_segment('fault',clock.tick)
                lifecycle.set_phase('faulted')
                task_state='failed';needs_recovery_task=True;busy_phase=None
                observation=dict(error=repr(error),type=type(error).__name__,authority=clock.snapshot(),
                    deadline_monotonic_s=getattr(error,'deadline',None),
                    issued_monotonic_s=time.monotonic(),physical_inflight=None if physics.inflight is None else dict(physics.inflight),
                    model_channels={name:dict(failed=getattr(child,'_wksim_rpc',{}).get('failed'),
                        last_response_tick=getattr(child,'_wksim_rpc',{}).get('tick')) for name,child in model_workers.items()},
                    model_transport={name:{key:getattr(child,'_wksim_rpc',{}).get(key)
                        for key in ('request_tick','sent_bytes','response_received')} for name,child in model_workers.items()})
                result.setdefault('faults',[]).append(observation)
                write_json(output/'faults.json',result['faults'])
                lifecycle.record('fault_latched',observation=observation)
                if pending is not None:
                    mailbox.respond(pending,'failed',reason=str(error),authority=clock.snapshot());pending=None
                status(['stop','cold-reset'],'faulted')
            def advance(loop_origin=None):
                nonlocal physics_wait_started,pending_task_reanchor
                loop_timing.start(loop_origin)
                loop_timing.mark('administration')
                stage='pacing';step_complete=False
                try:
                    if clock.tick%4==0:
                        if clock.phase=='running' and clock.synchronized:
                            if rate.anchor is None:
                                rate.reanchor(clock.tick,'synchronized_boundary',
                                              transition=lifecycle.phase in ('recovering','resuming'))
                            elif pending_task_reanchor:
                                # Preserve the explicitly authorized recovery boundary.
                                pending_task_reanchor=False
                                if not rate.latched:
                                    rate.reanchor(clock.tick,'start-recovery-task',transition=True)
                            rate.begin_group(clock.tick,physics_health)
                        else:
                            record_rate('untimed_group_start',classification='single_step' if clock.phase=='stepping' else 'bootstrap',
                                        start_tick=clock.tick,end_tick=clock.tick+4,actual_start_ns=time.monotonic_ns())
                    loop_timing.mark(stage);stage='physics'
                    physics_wait_started=time.monotonic()
                    states=physics.advance()
                    loop_timing.mark(stage);stage='clock_publish'
                    publisher.publish(clock)
                    loop_timing.mark(stage);stage='clock_evidence'
                    record_clock(json.dumps(clock.snapshot(),separators=(',',':'))+'\n')
                    loop_timing.mark(stage);stage='group_end_and_view'
                    if clock.tick%4==0:
                        if rate.group is not None: rate.end_group(clock.tick)
                        else: record_rate('untimed_group_end',classification='transition' if lifecycle.phase in ('resuming','recovering')
                                          else 'single_step' if lifecycle.phase=='stepping' else 'bootstrap',actual_end_ns=time.monotonic_ns())
                        view.emit(states,clock.tick,'running' if clock.phase=='stepping' else clock.phase)
                    step_complete=True
                    return states
                finally:
                    physics_wait_started=None
                    try:
                        loop_timing.mark(stage)
                        loop_timing.finish(clock.tick,complete=step_complete)
                    except Exception as diagnostic_error:
                        result.setdefault('evidence_errors',[]).append(dict(
                            stream='runtime-timing',phase=stage,error=repr(diagnostic_error)))
                        if step_complete:raise
            def recover(request):
                nonlocal task_state,needs_recovery_task,busy_phase,ever_started
                recovery_started=time.monotonic()
                busy_phase='recovering'
                status(['stop','cold-reset'],busy_phase)
                if clock.input_pending:
                    before=clock.snapshot()
                    lifecycle.record('input_recovery_requested',request=request,authority=before)
                    physics.finish_inputs(recovering=True,deadline=recovery_started+5)
                    lifecycle.record('input_recovery_verified',before=before,after=clock.snapshot())
                for stack,child in list(agents.items()):
                    if child.poll() is not None:
                        expected.add(child.pid)
                        spec=specs[child.pid]
                        agents[stack]=launch(stack+'-agent-reconnected-'+uuid.uuid4().hex[:8],
                                             spec['argv'],spec['cwd'],'agent')
                from .runtime import udp_listening
                while not all(udp_listening(port) for port in (12019,18888)):
                    if time.monotonic()-recovery_started>=5:
                        raise TimeoutError('Agent startup exceeded approved recovery window')
                    physics_health();time.sleep(.002)
                frozen=lifecycle.begin_recovery()
                if clock.tick%4==0:
                    rate.reanchor(clock.tick,'recover_requested',transition=True,recovery=True)
                lifecycle.recovery_started=recovery_started
                if 2 in lifecycle.faulted_uav_ids:
                    process=next(child for name,child,_ in children if name=='px4-fc')
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
                        peer.settimeout(1);peer.connect('/tmp/px4-sock-21')
                        peer_pid,_,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    if peer_pid!=process.pid or process.poll() is not None:
                        raise RuntimeError('DDS restart peer is not the owned PX4')
                    lifecycle.record('px4_cli_peer_verified',pid=peer_pid)
                    binary=Path(admission['configs']['px4']['px4_root'])/'build/px4_sitl_default/bin/px4-uxrce_dds_client'
                    for command in (['stop'],['start','-t','udp','-h','127.0.0.1','-p','18888','-n','wksim_px4_21']):
                        child=launch('px4-dds-'+command[0]+'-'+str(clock.last_request),
                                     [str(binary),'--instance','21',*command],output/'px4','service')
                        while child.poll() is None:
                            if time.monotonic()-lifecycle.recovery_started>=5:
                                raise TimeoutError('DDS restart exceeded approved recovery window')
                            advance()
                        if child.returncode:
                            raise RuntimeError('Native DDS client restart failed')
                        lifecycle.record('native_dds_client_restarted',argv=specs[child.pid]['argv'],
                                         pid=child.pid,returncode=child.returncode)
                        expected.add(child.pid)
                observation=lifecycle.recover_physics(advance,frozen)
                grounded=all(not monitor.sessions[uid].state.armed for uid in (1,2))
                rate.reanchor(clock.tick,'recover_confirmed')
                needs_recovery_task=not grounded
                task_state='idle' if grounded else 'recovery_required'
                if grounded: ever_started=False
                complete(request,effect='physics_recovered_new_task_required',observation=observation)
                busy_phase=None
            while clock.phase!='stopped':
                loop_origin=(time.monotonic_ns(),time.thread_time_ns()) if loop_timing.enabled else None
                try: physics_health()
                except OperatorRetirement: raise
                except (OSError,RuntimeError,ValueError) as error: latch_failure(error)
                if 'runtime_images' not in result and monitor.ready(config['run_id']):
                    record_images('ready')
                for name,child,_ in children:
                    code=child.poll()
                    if code is None or child.pid in expected:
                        continue
                    role=specs[child.pid]['role']
                    expected.add(child.pid)
                    if role=='agent':
                        rate.close_segment('agent_fault',clock.tick)
                        if clock.phase=='faulted':
                            clock.fault('additional_agent_exit');lifecycle.set_phase('faulted')
                        else:
                            lifecycle.communication_fault(name+'_exited',[1 if name.startswith('arducopter') else 2])
                        task_state='failed';needs_recovery_task=True
                    elif role=='task':
                        if defer_task_reports:
                            # Do not parse camera or fixed-trajectory reports
                            # on the rate deadline. Final retirement loads them.
                            report=dict(error=name+' exited with code '+str(code))
                        else:
                            report=json.loads((specs[child.pid]['cwd']/'result.json').read_text())
                            result['tasks'][name]=report
                        if code!=0:
                            rate.close_segment('task_fault',clock.tick)
                            task_state='failed';needs_recovery_task=True
                            if clock.phase!='faulted':
                                try: clock.suspend(name+'_failed')
                                except ValueError: clock.fault(name+'_failed')
                                lifecycle.set_phase('faulted')
                            if pending is not None:
                                mailbox.respond(pending,'failed',reason=report.get('error'),authority=clock.snapshot())
                                pending=None
                if task_group is not None and task_state=='preparing':
                    ready=[task_group/stack/'ready.json' for stack in ('arducopter','px4')]
                    if all(path.is_file() for path in ready):
                        records={stack:json.loads((task_group/stack/'ready.json').read_text()) for stack in ('arducopter','px4')}
                        if any(row['run_id']!=config['run_id'] or row['epoch']!=epoch for row in records.values()):
                            raise ValueError('Task ready identity differs')
                        write_json(task_group/'go.json',dict(run_id=config['run_id'],epoch=epoch,tasks=records))
                        task_state='running'
                if task_group is not None and task_state=='running':
                    if config['task']==FIXED_TASKS[0]:
                        coordinate_legs(task_group,config['run_id'],epoch,clock.tick)
                    reports=[task_group/stack/'result.json' for stack in ('arducopter','px4')]
                    task_processes=[child for _,child,_ in children if specs[child.pid]['role']=='task'
                                    and specs[child.pid]['cwd'].parent==task_group]
                    if task_group_completed(task_processes,reports,defer_report_reads=defer_task_reports):
                        task_state='completed'
                if pending is not None:
                    action=pending['action']
                    if action=='pause' and lifecycle.acknowledged():
                        record_rate('pause_confirmed',request_id=pending['token'])
                        complete(pending,effect='physical_and_control_pause_confirmed');pending=None
                    elif action=='step' and clock.phase=='paused':
                        lifecycle.set_phase('paused');complete(pending,effect='four_ticks_completed');pending=None
                    elif action=='resume':
                        try:
                            if resume_confirmed(lifecycle,clock,pending):
                                rate.reanchor(clock.tick,'resume_confirmed')
                                lifecycle.set_phase('running');complete(pending,effect='fresh_native_resume_confirmed');pending=None
                        except (OSError,RuntimeError,ValueError) as error:
                            latch_failure(error)
                allowed=['stop','cold-reset']
                if pending is None:
                    if (clock.phase=='faulted' and clock.recoverable
                            and (rate.latched or ever_started
                                 and all(uid in monitor.sessions and monitor.sessions[uid].state.armed for uid in (1,2)))
                            and not any(specs[child.pid]['role']=='task' and child.poll() is None for _,child,_ in children)):
                        allowed+=['recover']
                    elif clock.phase=='running':
                        if clock.synchronized and clock.tick%4==0 and monitor.ready(config['run_id']): allowed+=['set-rate']
                        if (not ever_started and monitor.ready(config['run_id'])
                                and all(not value.state.armed for value in monitor.sessions.values())): allowed+=['start-task']
                        elif needs_recovery_task and task_state=='recovery_required': allowed+=['start-recovery-task']
                        elif task_state=='running' and monitor.can_pause(config['run_id']): allowed+=['pause']
                    elif clock.phase=='paused' and lifecycle.acknowledged():
                        allowed+=['step','resume','set-rate']
                allowed=supported_actions(config['task'],allowed)
                if time.monotonic()>=next_status and (clock.phase in ('paused','faulted') or clock.tick%4==0):
                    status(allowed)
                    request=mailbox.poll(offer,allowed)
                    if request:
                        action=request['action']
                        if action!='start-recovery-task': pending_task_reanchor=False
                        if action in ('stop','cold-reset'):
                            if (fixed_task or aruco_task) and clock.phase=='running' and rate.anchor is not None and rate.group is None:
                                try: rate.check_boundary(clock.tick)
                                except (OSError,RuntimeError,ValueError) as error: latch_failure(error)
                            rate.close_segment(action,clock.tick)
                            if pending is not None:
                                mailbox.respond(pending,'failed',reason='Superseded by '+action,authority=clock.snapshot())
                                pending=None
                            clock_action('stop');lifecycle.set_phase('stopped')
                            result['terminal_transition']=dict(action=action,phase=clock.phase,tick=clock.tick,
                                                               issued_monotonic_ns=time.monotonic_ns())
                            result['stop_request']=request
                            result['status']='cold_reset' if action=='cold-reset' else 'stopped'
                            record_images('stopping')
                            break
                        if action in ('start-task','start-recovery-task'):
                            # Approved 2026-09-07 amendment: an explicit operator
                            # start-recovery-task closes the previous rate segment
                            # and re-anchors like recover/resume; every numeric
                            # budget (100ms / 10s ±2% / 60s ±1%) stays unchanged.
                            if action=='start-recovery-task':
                                if (clock.phase=='running' and clock.synchronized and clock.tick%4==0
                                        and rate.anchor is not None and rate.group is None and not rate.latched):
                                    rate.reanchor(clock.tick,'start-recovery-task',transition=True)
                                else:
                                    pending_task_reanchor=True
                            start_tasks('initial' if action=='start-task' else 'recovery')
                            needs_recovery_task=False;complete(request,effect='new_tasks_started')
                        elif action=='set-rate':
                            pending=request
                            try:
                                rate.set_rate(request['requested_rate'],request['token'],clock.tick)
                                if clock.phase=='running': rate.reanchor(clock.tick,'set-rate')
                                complete(request,effect='rate_requested',rate=rate.snapshot(clock.tick))
                            except (OSError,RuntimeError,ValueError) as error: latch_failure(error)
                            else: pending=None
                        elif action=='recover':
                            pending=request
                            try: recover(request)
                            except OperatorRetirement: raise
                            except (OSError,RuntimeError,ValueError) as error: latch_failure(error)
                            else: pending=None
                        else:
                            pending=dict(request,began=time.monotonic(),frozen_ns=clock.tick*1000000)
                            try:
                                if action=='pause': rate.check_boundary(clock.tick)
                                rate.close_segment(action,clock.tick)
                                clock_action(action)
                                lifecycle.set_phase({'pause':'paused','step':'stepping','resume':'resuming'}[action])
                                record_rate('rate_transition',action=action,action_token=request['token'])
                                if action=='resume': rate.reanchor(clock.tick,'resume_requested',transition=True)
                                status(['stop','cold-reset'])
                            except (OSError,RuntimeError,ValueError) as error: latch_failure(error)
                if clock.phase in ('running','stepping'):
                    try: advance(loop_origin)
                    except OperatorRetirement: raise
                    except (OSError,RuntimeError,ValueError) as error: latch_failure(error)
                else:
                    view.emit(physics.states,clock.tick,clock.phase)
                    time.sleep(.002)
            for child in model_workers.values():
                if child.poll() is None:
                    child.stdin.close();child.wait(timeout=3)
            result['authority']=clock.snapshot()
            result['clock_publications']=publisher.publications
    except OperatorRetirement:
        result['authority']=clock.snapshot()
        if pending is not None:
            mailbox.respond(pending,'failed',reason='Operator retired the epoch',authority=clock.snapshot())
    except BaseException as error:
        result.update(status='failed',error=repr(error),traceback=traceback.format_exc())
        clock.fault(str(error));result['authority']=clock.snapshot()
        if pending is not None:
            mailbox.respond(pending,'failed',reason=str(error),authority=clock.snapshot())
    finally:
        if physics is not None:
            view.emit(physics.states,clock.tick,'stopped',force=True)
        result['display_stream']=dict(sent=view.sent,dropped=view.dropped,sequence=view.sequence,
                                      setup_error=view.setup_error,last_error=view.last_error)
        view.close()
        evidence_errors=list(result.get('evidence_errors',[]))
        try:
            rate.close_segment('epoch_retired',clock.tick)
        except Exception as error:
            evidence_errors.append(dict(stream='rate',phase='final_record',error=repr(error)))
        result['rate']=rate.snapshot(clock.tick)
        result['rate']['last_segment']=rate.last_summary
        for name,stream in (evidence_streams if async_evidence else [('rate',rate_log)]):
            try: stream.close()
            except Exception as error:
                evidence_errors.append(dict(stream=name,phase='close',error=repr(error)))
        if write_probe:
            result['write_timing']=write_probe.summary()
            try: write_log.close()
            except Exception as error:
                evidence_errors.append(dict(stream='write-timing',phase='close',error=repr(error)))
        if async_evidence:
            result['async_evidence']={name:stream.summary() for name,stream in evidence_streams}
            for name,summary in result['async_evidence'].items():
                if summary.get('complete') is not True:
                    evidence_errors.append(dict(stream=name,phase='completion',error='Evidence writer did not fully retire'))
        if evidence_errors:
            result['evidence_errors']=evidence_errors
            result['status']='failed'
            result.setdefault('error','Evidence logging failed')
        for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,signal.SIG_IGN)
        result['cleanup_errors']=stop_processes(children)
        for name,child,_ in children:
            result['children'][name]['returncode']=child.poll()
            if defer_task_reports and specs[child.pid]['role']=='task':
                path=specs[child.pid]['cwd']/'result.json'
                try:
                    if path.is_file():
                        result['tasks'][name]=load_retired_task_report(path,config['run_id'],epoch,
                            name.split('-task-',1)[0],child.poll())
                    elif child.poll()==0:
                        raise ValueError('Successful task exited without its result')
                except (OSError,ValueError,TypeError) as error:
                    result.setdefault('task_report_errors',[]).append(dict(task=name,error=str(error)))
                    result['status']='failed'
                    result.setdefault('error','Deferred task report validation failed')
        if async_model_evidence:
            result['async_model_evidence']={}
            for stack in ('arducopter','px4'):
                try:
                    path=output/(stack+'-truth.jsonl.writer.json')
                    summary=json.loads(path.read_text())
                    if (summary.get('complete') is not True or summary.get('alive') is not False
                            or summary.get('error') is not None or summary.get('closed') is not True
                            or summary.get('submitted_bytes')!=summary.get('written_bytes')
                            or summary.get('written_bytes')!=(output/(stack+'-truth.jsonl')).stat().st_size):
                        raise ValueError('Model trace writer did not retire with complete bytes')
                    result['async_model_evidence'][stack]=summary
                except (OSError,ValueError,TypeError) as error:
                    result.setdefault('model_evidence_errors',[]).append(dict(stack=stack,error=str(error)))
                    result['status']='failed'
                    result.setdefault('error','Model trace evidence incomplete')
        if result['host_boot_id']!=host_boot_id():
            result['status']='failed';result['error']='Host boot identity changed'
        result['wall_seconds']=time.monotonic()-started
        result['changed_sources']=[name for name,sha in result.get('source_sha256',{}).items()
            if not (REPO/name).is_file() or digest(REPO/name)!=sha]
        try:
            if result['status'] in ('stopped','cold_reset'):
                result['physical_task_proof']=verify_tasks(output,epoch,clock.tick,result['tasks'],config.get('task','public_position'),
                                                          **({'formal_result':result} if fixed_task else {}))
                result['flight_completed']=result['physical_task_proof'] is not None
        except (OSError,ValueError,KeyError,TypeError,ImportError,AssertionError) as error:
            result['status']='failed';result['error']='Independent truth verification: '+str(error)
        result['changed_sources']=[name for name,sha in result.get('source_sha256',{}).items()
            if not (REPO/name).is_file() or digest(REPO/name)!=sha]
        if result['cleanup_errors'] or result['changed_sources']:
            result['status']='failed';result['error']='Cleanup or source identity changed during execution'
        write_json(output/'result.json',result)
        task_state='completed' if result['flight_completed'] else task_state
        monitor=None
        status([],result['status'])
    return result



def _joint_directory(output_root, run_id):
    directory=Path(os.path.abspath(Path(output_root)/run_id))
    for path in (directory,*directory.parents):
        if path.is_symlink():
            raise ValueError('Joint run paths must not contain symlinks')
    return directory


def _config_digest(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _exclusive_json(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())


def joint_run_files(config,output_root,*,prepare=False,use_prepared_run=None):
    """File-only lifecycle; caller holds the run/output/display Reservation."""
    directory=_joint_directory(output_root,config['run_id'])
    owner=os.geteuid() if hasattr(os,'geteuid') else None
    if use_prepared_run is None:
        directory.mkdir(parents=True,exist_ok=False)
        for name in ('epochs','actions','action-results'): (directory/name).mkdir()
        session=dict(version=1,run_id=config['run_id'],instance_id=uuid.uuid4().hex)
        _exclusive_json(directory/'config.json',config)
        _exclusive_json(directory/'session.json',session)
        if prepare:
            _exclusive_json(directory/'preparation.json',dict(version=1,state='prepared',
                run_id=config['run_id'],instance_id=session['instance_id'],run_dir=str(directory),
                config_sha256=_config_digest(config),owner_uid=owner))
        return directory,session
    if prepare:
        raise ValueError('Preparation and consumption are mutually exclusive')
    supplied=Path(os.path.abspath(use_prepared_run))
    if supplied!=directory:
        raise ValueError('Prepared run must be the configured output-root/run_id directory')
    expected={'config.json','session.json','preparation.json','epochs','actions','action-results'}
    def check_owned(path,is_directory):
        info=path.lstat()
        if (path.is_symlink() or not (stat.S_ISDIR(info.st_mode) if is_directory else stat.S_ISREG(info.st_mode))
                or owner is not None and info.st_uid!=owner):
            raise ValueError('Prepared run has foreign ownership or unsafe file type: '+str(path))
    check_owned(directory,True)
    if {path.name for path in directory.iterdir()}!=expected:
        raise ValueError('Prepared run is consumed or contains unexpected files')
    for name in expected:
        path=directory/name
        check_owned(path,name in ('epochs','actions','action-results'))
        if path.is_dir() and any(path.iterdir()):
            raise ValueError('Prepared run contains existing epochs or actions')
    try:
        saved=json.loads((directory/'config.json').read_text(encoding='utf-8'))
        session=json.loads((directory/'session.json').read_text(encoding='utf-8'))
        preparation=json.loads((directory/'preparation.json').read_text(encoding='utf-8'))
        if (not isinstance(session,dict) or set(session)!={'version','run_id','instance_id'}
                or type(session['version']) is not int or session['version']!=1
                or session['run_id']!=config['run_id'] or not hex_identity(session['instance_id'])):
            raise ValueError('Invalid prepared joint session identity')
        expected_preparation=dict(version=1,state='prepared',run_id=config['run_id'],
            instance_id=session['instance_id'],run_dir=str(directory),config_sha256=_config_digest(config),owner_uid=owner)
        if (not isinstance(preparation,dict) or preparation!=expected_preparation
                or type(preparation.get('version')) is not int or _config_digest(saved)!=_config_digest(config)):
            raise ValueError('Prepared configuration or preparation identity differs')
    except (TypeError,KeyError) as error:
        raise ValueError('Malformed joint preparation files') from error
    _exclusive_json(directory/'execution.started.json',dict(version=1,state='consumed',
        run_id=config['run_id'],instance_id=session['instance_id'],config_sha256=_config_digest(config)))
    return directory,session


def _joint_resource(config,directory):
    return dict(experiment_kind='joint',run_id=config['run_id'],output=str(directory),
        network_namespace=os.readlink('/proc/self/ns/net'),display_socket=config.get('display_socket'),ports=[],
        host_boot_id=host_boot_id())


def prepare_joint(config,output_root):
    check_isolation()
    config=validate_joint_config(config)
    directory=_joint_directory(output_root,config['run_id'])
    with Reservation(_joint_resource(config,directory)):
        directory,session=joint_run_files(config,output_root,prepare=True)
    return dict(status='prepared',kind='joint_scene',run_id=config['run_id'],run_dir=str(directory),
        instance_id=session['instance_id'],session=str(directory/'session.json'),
        scope='identity and empty run directory only; no flight processes or clock steps',
        flight_ready=False,resources_reserved=False)


def _run_joint(config,output_root,*,use_prepared_run=None):
    check_isolation()
    config=validate_joint_config(config)
    directory=_joint_directory(output_root,config['run_id'])
    resource=_joint_resource(config,directory)
    epochs=[];reset_request=None;previous_namespaces=None;previous_namespace_scope=None
    with ExitStack() as namespace_references,Reservation(resource):
        directory,session=joint_run_files(config,output_root,use_prepared_run=use_prepared_run)
        while True:
            epoch=uuid.uuid4().hex
            command=['unshare','--net','--ipc','--mount','--propagation','private','bash','-c',
                'set -e; ip link set lo up; mount -t tmpfs -o nosuid,nodev,mode=1777 tmpfs /dev/shm; exec python3 -B -m Simulator.wksim_runtime.joint_runtime "$@"',
                'wksim',str(directory),epoch,str(len(epochs)+1)]
            log=(directory/(epoch+'.log')).open('x')
            child=subprocess.Popen(command,cwd=REPO,stdout=log,stderr=log,start_new_session=True)
            namespace=None;namespaces={};manager_error=None;cleanup_error=None
            try:
                while child.poll() is None:
                    try:
                        value=os.readlink(f'/proc/{child.pid}/ns/net')
                        if namespace is None and value!=resource['network_namespace']:
                            scope=namespace_references.enter_context(ExitStack())
                            for kind in ('net','ipc','mnt'):
                                handle=scope.enter_context(open(f'/proc/{child.pid}/ns/{kind}','rb'))
                                namespaces[kind]=os.readlink(f'/proc/self/fd/{handle.fileno()}')
                            if previous_namespaces is not None and any(namespaces[kind]==previous_namespaces[kind] for kind in namespaces):
                                raise RuntimeError('Cold reset reused a still-referenced namespace object')
                            # Keep the old kernel objects alive through comparison:
                            # an inode number alone may be reused after destruction.
                            if previous_namespace_scope is not None: previous_namespace_scope.close()
                            previous_namespace_scope=scope;previous_namespaces=namespaces
                            namespace=namespaces['net']
                    except FileNotFoundError: pass
                    if reset_request is not None:
                        path=directory/'status.json'
                        if path.is_file():
                            state=json.loads(path.read_text())
                            if state['epoch']==epoch and 'start-task' in state['allowed_actions']:
                                write_json(directory/'action-results'/reset_request['epoch']/(reset_request['token']+'.json'),
                                    dict(reset_request,state='completed',effect='cold_reset_ready',new_epoch=epoch))
                                reset_request=None
                    time.sleep(.05)
            except (Exception,KeyboardInterrupt) as error:
                manager_error=repr(error)
            finally:
                saved={sig:signal.signal(sig,signal.SIG_IGN) for sig in (signal.SIGINT,signal.SIGTERM)}
                try:
                    for sig in (signal.SIGTERM,signal.SIGKILL):
                        members=group_members(child.pid)
                        if not members: break
                        for row in members:
                            try: actual=os.readlink(f"/proc/{row['pid']}/ns/net")
                            except FileNotFoundError: continue
                            if namespace is None or actual!=namespace:
                                raise RuntimeError('Refusing cleanup of an unverified epoch group')
                        try: os.killpg(child.pid,sig)
                        except ProcessLookupError: pass
                        deadline=time.monotonic()+5
                        while time.monotonic()<deadline:
                            child.poll()
                            if not group_members(child.pid): break
                            time.sleep(.05)
                    if group_members(child.pid): raise RuntimeError('Owned epoch group was not fully retired')
                except (OSError,RuntimeError) as error:
                    cleanup_error=repr(error)
                finally:
                    for sig,handler in saved.items(): signal.signal(sig,handler)
                log.close()
            path=directory/'epochs'/epoch/'result.json'
            result=json.loads(path.read_text()) if path.is_file() else dict(status='failed',error='Epoch exited without a result')
            if manager_error or cleanup_error:
                result.update(status='failed',manager_error=manager_error,manager_cleanup_error=cleanup_error)
            epochs.append(dict(epoch=epoch,result=result,process_identity=child.pid,network_namespace=namespace,
                               namespace_objects=namespaces,namespace_comparison='held_file_descriptors',
                               remaining_group_members=group_members(child.pid)))
            if result['status']=='cold_reset':
                reset_request=result.get('stop_request')
            elif result.get('stop_request'):
                write_json(directory/'action-results'/result['stop_request']['epoch']/(result['stop_request']['token']+'.json'),
                    dict(result['stop_request'],state='completed' if result['status']=='stopped' else 'failed',
                         effect='owned_epoch_stopped',reason=result.get('error'),
                         remaining_group_members=group_members(child.pid)))
            if result['status']=='failed' and reset_request is not None:
                write_json(directory/'action-results'/reset_request['epoch']/(reset_request['token']+'.json'),
                    dict(reset_request,state='failed',reason='New epoch failed',new_epoch=epoch))
            if result['status']!='cold_reset':
                break
        value=dict(status=final_run_status(epochs),
                   kind='joint_scene',run_id=config['run_id'],instance_id=session['instance_id'],config=config,epochs=epochs,run_dir=str(directory),
                   host_boot_id=resource['host_boot_id'])
        if value['status']=='failed' and result.get('authority',{}).get('fault'):
            value['error']=result['authority']['fault']
        write_json(directory/'result.json',value)
        print(json.dumps(dict(status=value['status'],result=str(directory/'result.json'))),flush=True)
        return value


def run_joint(config,output_root,*,use_prepared_run=None):
    def interrupted(signum,frame):
        raise InterruptedError('Joint manager interrupted; retiring owned epoch group')
    previous={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        return _run_joint(config,output_root,use_prepared_run=use_prepared_run)
    finally:
        for sig,handler in previous.items(): signal.signal(sig,handler)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('epoch')
    parser.add_argument('generation',type=int,nargs='?',default=1)
    args=parser.parse_args()
    report=epoch_run(args.directory,args.epoch,args.generation)
    raise SystemExit(0 if report['status'] in ('stopped','cold_reset') else 1)
