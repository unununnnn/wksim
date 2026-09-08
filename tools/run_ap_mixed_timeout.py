"""AP native mixed target silence, then a new unchanged public recovery Task.

This separate experiment preserves the joint physics/rate contracts. Runtime
completion is observation only; `audit` determines the native boundary result.
"""
import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO/'tools')]
from run_joint_flight import save, WALL_LIMIT, MAX_TICKS
from Simulator.wksim_runtime.runtime import launch_spec, stop_children, digest
from Simulator.wksim_runtime.isolation import check_isolation, isolate_temporary_files
from Simulator.wksim_runtime.evidence import json_value
from sitl_dds import NativeDDS, angle_error, quaternion_yaw

SCOPE = 'ap_mixed_native_timeout_v1'
AP_MANIFEST = '/root/wksim-ap-mixed-fhuf05l9/mixed-build.json'
AP_SHA = '1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c'
CONTRACT = 'docs/2026-09-09-ap-mixed-timeout-contract.md'
FINAL_ALTITUDE, MAX_HEIGHT = 15., 17.
SOURCES = ('tools/run_ap_mixed_timeout.py', 'tools/run-ap-mixed-timeout.sh',
    'validation/test_ap_mixed_timeout.py', CONTRACT, 'tools/sitl_dds.py',
    'tools/run_joint_flight.py', 'tools/ap_mixed_candidate.py', 'tools/joint_control_candidate.py',
    'tools/prepare_ap_mixed_candidate.py', 'tools/ap_pv_candidate.py','tools/verify_ap_pv_candidate.py',
    'tools/audit_pv_trajectory.py','tools/audit_joint_rate.py',
    'tools/audit_joint_flight.py', 'Simulator/wksim_runtime/task.py',
    'Simulator/wksim_runtime/config.py','Simulator/wksim_runtime/build_identity.py',
    'Simulator/wksim_runtime/joint_profile.py','Simulator/wksim_runtime/evidence.py',
    'Simulator/wksim_runtime/runtime.py', 'Simulator/wksim_runtime/scene_clock.py',
    'Simulator/wksim_runtime/joint_rate.py', 'Simulator/wksim_runtime/joint-profiles.json',
    'Simulator/wksim_core/joint.py', 'Simulator/wksim_core/worker.py',
    'Simulator/wksim_core/model.py', 'Simulator/wksim_core/model.cpp',
    'Simulator/wksim_core/ap_json.py', 'Simulator/wksim_core/px4_mavlink.py')


def require(value, message):
    if not value:
        raise ValueError(message)


def validate_inputs(args):
    require(args.ap_mixed_manifest == AP_MANIFEST and args.ap_mixed_sha256 == AP_SHA,
            'Timeout v1 requires the exact sealed mixed AP manifest and SHA256')
    require(re.fullmatch(r'/root/wksim-joint-control-[A-Za-z0-9]+/build.json', args.control_manifest or ''),
            'An explicit isolated control manifest is required')
    require(re.fullmatch('[0-9a-f]{64}', args.control_sha256 or ''), 'External control SHA256 is required')


def parameter_contract(parameters):
    require(parameters.get('GUID_TIMEOUT') == 3.0, 'This frozen contract requires actual GUID_TIMEOUT=3.0')
    options = parameters.get('GUID_OPTIONS')
    require(type(options) in (float, int) and math.isfinite(options) and options == int(options)
            and not int(options) & 0x30, 'GUID_OPTIONS must retain position and velocity XY stabilization')
    require(parameters.get('LOG_DISARMED') == 1., 'Actual LOG_DISARMED must be 1')
    require(parameters.get('FENCE_ENABLE') == 0., 'Enabled native fences need a separate reviewed contract')
    require('AVOID_ENABLE' in parameters, 'Missing actual avoidance parameter evidence')
    return int(max(parameters['GUID_TIMEOUT'], .1)*1000)


def read_native_log(directory):
    from pymavlink import DFReader
    paths = sorted((Path(directory)/'arducopter/logs').glob('*.BIN'))
    require(paths, 'Missing native DataFlash log')
    rows, parameters, changes = [], {}, []
    for path in paths:
        reader = DFReader.DFReader_binary(str(path))
        while True:
            msg = reader.recv_msg()
            if msg is None:
                break
            kind = msg.get_type()
            require(kind != 'BAD_DATA', 'Corrupt native DataFlash evidence')
            if kind == 'PARM':
                name, value = msg.Name, msg.Value
                if name in parameters and parameters[name] != value:
                    changes.append(dict(name=name, before=parameters[name], after=value))
                parameters[name] = value
            if kind in ('GUIP', 'ORGN'):
                rows.append(msg.to_dict())
        reader.close()
    relevant = {name:value for name,value in parameters.items()
                if name.startswith(('GUID_', 'FENCE_', 'AVOID_')) or name == 'LOG_DISARMED'}
    require(not any(row['name'] in relevant for row in changes), 'Boundary parameters changed during this run')
    return dict(parameters=relevant, rows=rows, files={p.name:digest(p) for p in paths})


def validate_offer(offer, ready):
    require(offer == dict(version=1, scope=SCOPE, action='new_recovery_task', **ready),
            'Recovery requires an exact one-time run/scene/epoch/token start offer')


def validate_mixed_target(msg):
    require(msg['type_mask']==2531 and msg['coordinate_frame']==6 and msg['header']['frame_id']=='map'
            and msg['yaw']==0 and msg['latitude']==msg['longitude']==0
            and abs(msg['velocity']['linear']['x']-.8)<1e-6 and abs(msg['velocity']['linear']['y']-.4)<1e-6
            and msg['velocity']['linear']['z']==0 and all(v==0 for v in msg['velocity']['angular'].values())
            and all(v==0 for axis in msg['acceleration_or_force'].values() for v in axis.values())
            and msg['altitude'] in (3.,FINAL_ALTITUDE), 'Wrong native mixed payload')


def validate_audit_output(root, output):
    require(not output.resolve().is_relative_to(root.resolve()), 'Audit output must be external to retained raw evidence')
    require(not output.exists(), 'Audit output already exists; use a fresh external output')


def recovery_main(args):
    check_isolation()
    import rclpy
    from Simulator.wksim_runtime.task import Task
    root, task, started = Path(args.output), None, time.monotonic()
    report = dict(status='failed', run_id=args.run_id, scene_epoch=args.scene_epoch, phases=[])
    rclpy.init(args=[])
    try:
        def health():
            require(time.monotonic()-started < WALL_LIMIT, 'Recovery wall watchdog exceeded')
        def phase(name):
            report['phases'].append(dict(phase=name, ros_time_ns=task.node.get_clock().now().nanoseconds,
                                        state=task.convert(task.state)))
        task = Task(root, health, phase, 'arducopter', run_id=args.run_id,
                    protocol='session_v1', uav_id=1, use_sim_time=True)
        while task.task_time() == 0:
            health()
            rclpy.spin_once(task.node, timeout_sec=.02)
        task.wait('new_public_ready', lambda: task.fresh() and task.epoch is not None
                  and task.setup_pub.get_subscription_count() == task.command_pub.get_subscription_count() == 1, 55)
        ready = dict(run_id=args.run_id, scene_epoch=args.scene_epoch, control_epoch=task.epoch,
                     start_token=args.start_token, uav_id=1)
        save(root/'ready.json', ready)
        task.wait('explicit_recovery_offer', lambda: (root/'go.json').is_file(), 10)
        offer = json.loads((root/'go.json').read_text())
        validate_offer(offer, ready)
        report['offer'] = offer
        task.recover_then_land()
        report.update(status='pass', task=task.report(), use_sim_time=task.node.get_parameter('use_sim_time').value)
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc())
        if task is not None:
            report['task'] = task.report()
    finally:
        if task is not None:
            task.close()
        if rclpy.ok():
            rclpy.shutdown()
        save(root/'result.json', report)
    return 0 if report['status'] == 'pass' else 1


class NativeBoundary(NativeDDS):
    """Reuse the one native publisher/services, never the position-target pump."""
    def __init__(self, root, clock):
        super().__init__('arducopter', root, state_extension=True)
        from rclpy.parameter import Parameter
        self.node.set_parameters([Parameter('use_sim_time', value=True)])
        self.clock, self.last_target_tick = clock, None
        self.home_token = self.origin_token = None
        self.source_clock, self.advanced = {}, {}
        self.active = False
        self.last_ros_ns = None

    def receive(self, key, msg):
        stamp = getattr(msg, 'time_boot_us', None)
        if stamp is None:
            stamp = msg.header.stamp.sec*1_000_000_000+msg.header.stamp.nanosec
        previous = self.source_clock.get(key)
        if self.active and previous is not None:
            require(stamp >= previous, 'Native source clock regressed')
        if previous is None or stamp > previous:
            self.source_clock[key], self.advanced[key] = stamp, time.monotonic()
        super().receive(key, msg)

    def pump(self):
        self.ros.spin_once(self.node, timeout_sec=0)
        now = self.node.get_clock().now().nanoseconds
        require(self.last_ros_ns is None or now >= self.last_ros_ns, 'Native diagnostic ROS clock regressed')
        self.last_ros_ns = now
        if self.active:
            require(self.navigation_ready(), 'Native state invalid, stale or disconnected')

    def navigation_ready(self):
        now = time.monotonic()
        if 'origin' not in self.latest or not all(
                key in self.latest and now-self.received_at[key] <= 2 and now-self.advanced.get(key, 0) <= 2
                for key in ('status', 'wksim_state')):
            return False
        m, status = self.latest['wksim_state'], self.latest['status']
        if not (m.header.frame_id == 'map' and 0 < m.time_boot_us < 10**12
                and m.filter_status_valid and m.ahrs_healthy and m.attitude_valid and m.position_valid
                and m.velocity_valid and m.home_valid and m.gps_fix_type >= 3 and not status.failsafe):
            return False
        values = (m.pose.position.x,m.pose.position.y,m.pose.position.z,
                  m.twist.linear.x,m.twist.linear.y,m.twist.linear.z, quaternion_yaw(m.pose.orientation))
        require(all(math.isfinite(v) for v in values), 'Nonfinite native navigation')
        home = (m.home_latitude_e7,m.home_longitude_e7,m.home_altitude_cm,
                m.yaw_reset_ms,m.position_ne_reset_ms,m.position_down_reset_ms)
        origin = self.latest['origin'].position
        origin = (origin.latitude,origin.longitude,origin.altitude)
        require(all(math.isfinite(v) for v in origin), 'Nonfinite native origin')
        if self.active:
            require(home == self.home_token and origin == self.origin_token, 'Native home/origin/EKF reset changed')
        else:
            self.home_token, self.origin_token = home, origin
        return True

    def mixed(self, altitude):
        require(altitude in (3., FINAL_ALTITUDE) and self.pending is None, 'Invalid mixed phase or pending native service')
        require('position' in self.publishers, 'Diagnostic publisher has been retired')
        require(self.navigation_ready() and self.armed and self.mode_confirmed(4), 'Mixed target requires fresh armed GUIDED')
        if self.last_target_tick is not None and self.clock.tick-self.last_target_tick < 50:
            return
        msg = self.position_type(coordinate_frame=6, type_mask=2531, altitude=float(altitude), yaw=0.)
        msg.header.frame_id = 'map'
        msg.header.stamp.sec, msg.header.stamp.nanosec = self.clock.tick//1000, self.clock.tick%1000*1_000_000
        msg.velocity.linear.x, msg.velocity.linear.y = .8, .4
        validate_mixed_target(self.to_dict(msg))
        self.publishers['position'].publish(msg)
        self.last_target_tick = self.clock.tick
        self.log.write(json.dumps(dict(published='/ap/cmd_gps_pose', tick=self.clock.tick,
            wall=time.monotonic()-self.started, native_boot_us=self.latest['wksim_state'].time_boot_us,
            message=self.to_dict(msg)))+'\n')

    def retire_publisher(self):
        require(self.pending is None, 'Cannot transfer with a pending native service')
        self.node.destroy_publisher(self.publishers.pop('position'))

    def command(self, command_id, parameters):
        require(self.pending is None,'Native service request already pending')
        super().command(command_id,parameters)
        self.commands[-1]['tick'] = self.clock.tick


class Recorder:
    """Raw CDR/timestamps and separate graph identities; no per-message GID."""
    def __init__(self, native, root, clock):
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from rclpy.serialization import deserialize_message
        from ardupilot_msgs.msg import GlobalPosition, WksimState, Status
        from geometry_msgs.msg import TwistStamped
        from geographic_msgs.msg import GeoPointStamped
        from px4_msgs.msg import VehicleStatus
        from prometheus_msgs.msg import TextInfo
        from wksim_msgs.msg import SessionState
        from sitl_dds import px4_topic
        self.node, self.clock, self.native = native.ros.create_node('wksim_ap_timeout_recorder'), clock, native
        implementation = Path('/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/executors.py')
        save(root/'recorder-method.json',dict(mechanism='supported subscription.handle.take_message(raw=True) on unspun recorder node',
            per_message_publisher_gid_available=False,attribution='separate strict discovered endpoint identities; no per-packet attribution',
            executor_source_path=str(implementation),executor_source_sha256=digest(implementation),
            python_binding_limit='Humble take_message metadata contains only source/received timestamps; executor discards even those'))
        shutil.copyfile(implementation,root/'recorder-executor-source.txt')
        self.log = (root/'native-raw.jsonl').open('x', buffering=65536)
        self.graph = (root/'publisher-graph.jsonl').open('x', buffering=65536)
        self.last_graph = None
        self.last_graph_log_tick = -200
        self.sequence, self.latest, self.subscriptions = 0, {}, []
        self.channels = [('/ap/cmd_gps_pose',GlobalPosition),('/ap/cmd_vel',TwistStamped),
            ('/ap/wksim/local_state_v1',WksimState),('/ap/status',Status),
            ('/ap/gps_global_origin/filtered',GeoPointStamped),
            (px4_topic('out','vehicle_status',VehicleStatus),VehicleStatus),
            ('/uav1/prometheus/v2/state',SessionState),('/uav1/prometheus/text_info',TextInfo)]
        def receiver(topic, cls):
            def callback(raw, info):
                msg = deserialize_message(raw, cls)
                self.sequence += 1
                row = dict(sequence=self.sequence, epoch=clock.epoch, tick=clock.tick, topic=topic,
                    received_monotonic_ns=time.monotonic_ns(), **info,
                    per_message_publisher_gid_available=False,
                    cdr_hex=bytes(raw).hex(), message=json_value(native.to_dict(msg)))
                self.latest[topic] = row
                self.log.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
            return callback
        for topic, cls in self.channels:
            self.subscriptions.append(self.node.create_subscription(cls,topic,receiver(topic,cls),
                QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT),raw=True))

    def publishers(self):
        result = {topic:[dict(node_name=i.node_name,node_namespace=i.node_namespace,
                             gid=bytes(i.endpoint_gid).hex())
                         for i in self.node.get_publishers_info_by_topic(topic)] for topic,_ in self.channels}
        if result != self.last_graph or self.clock.tick-self.last_graph_log_tick>=200:
            self.graph.write(json.dumps(dict(tick=self.clock.tick,epoch=self.clock.epoch,
                received_monotonic_ns=time.monotonic_ns(),publishers=result),separators=(',',':'))+'\n')
            self.last_graph = result
            self.last_graph_log_tick = self.clock.tick
        return result

    def pump(self):
        # One take per channel per health call; no executor can consume this node.
        for subscription in self.subscriptions:
            with subscription.handle:
                value = subscription.handle.take_message(subscription.msg_type,True)
            if value is not None:
                require(set(value[1])=={'source_timestamp','received_timestamp'},'Raw message metadata schema changed')
                subscription.callback(*value)

    def close(self):
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)
        self.node.destroy_node()
        self.log.close()
        self.graph.close()


def run(args):
    validate_inputs(args)
    check_isolation()
    require(os.readlink('/proc/self/ns/mnt') != os.readlink('/proc/1/ns/mnt'), 'Private mount namespace required')
    from ap_mixed_candidate import admit
    from joint_control_candidate import environment
    from probe_joint_clock import json_identity, group_members
    from Simulator.wksim_core.joint import JointPhysics
    from Simulator.wksim_runtime.scene_clock import SceneClock, ClockPublisher
    from Simulator.wksim_runtime.joint_rate import JointRate
    root = Path(tempfile.mkdtemp(prefix='wksim-ap-timeout-',dir='/root'))
    archive = Path(tempfile.mkdtemp(prefix='ap-mixed-timeout-',dir=REPO/'validation'))
    result = dict(status='failed', scope=SCOPE, run_id=archive.name, scene_epoch=uuid.uuid4().hex,
        archive=str(archive),live=str(root),children={},phases=[], production_admitted=False,
        bounds=dict(wall_seconds=WALL_LIMIT,simulation_ticks=MAX_TICKS,requested_rate=.5),
        unowned_ap_before=json_identity(828), source_sha256={name:digest(REPO/name) for name in SOURCES})
    print(json.dumps(dict(archive=str(archive),live=str(root))),flush=True)
    for name in SOURCES:
        (root/('source__'+name.replace('/','__')+'.txt')).write_bytes((REPO/name).read_bytes())
    started, children, expected, retained = time.monotonic(), [], set(), []
    native = recorder = None
    clock = SceneClock(result['scene_epoch'])
    def interrupted(signum, frame):
        raise InterruptedError('Owned timeout diagnostic interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    try:
        result['private_temporary_files'] = isolate_temporary_files()
        admission = admit(args.ap_mixed_manifest,args.ap_mixed_sha256,args.control_manifest,args.control_sha256,result['run_id'])
        save(root/'experimental-admission.json',admission)
        require(admission['ok'],'Explicit mixed admission rejected: '+str(admission['reasons']))
        result['admission'] = admission
        control, configs, library = admission['control_candidate'], admission['configs'], Path(admission['model_library'])
        result['model_library_sha256'] = digest(library)
        result['model_build'] = json.loads(library.with_name('build.json').read_text())
        for source,target in ((args.ap_mixed_manifest,'ap-build.json'),(args.control_manifest,'control-build.json')):
            shutil.copyfile(source,root/target)
        native_root = Path(args.ap_mixed_manifest).parent
        for name in ('mixed-source.json','baseline-pv-build.json'):
            shutil.copyfile(native_root/name,root/name)
        native_files = ('ArduCopter/mode_guided.cpp','ArduCopter/mode.h','ArduCopter/Log.cpp',
            'ArduCopter/AP_ExternalControl_Copter.cpp','libraries/AP_DDS/AP_DDS_ExternalControl.cpp',
            'libraries/AP_DDS/AP_DDS_config.h','libraries/AP_DDS/AP_DDS_Client.cpp',
            'libraries/AC_WPNav/AC_WPNav.h','libraries/AC_WPNav/AC_WPNav.cpp',
            'libraries/AC_AttitudeControl/AC_PosControl.cpp')
        retained = [(Path(control['package'])/name,root/'control-source'/name) for name in control['python_sha256']]
        retained += [(native_root/'src'/name,root/'native-source'/name) for name in native_files]
        for source,target in retained:
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
        result['retained_sha256'] = {str(target.relative_to(root)):digest(source) for source,target in retained}
        def launch(name,argv,cwd,env=None,worker=False):
            log = (root/(name+'.log')).open('x')
            child = subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.PIPE if worker else subprocess.DEVNULL,
                stdout=subprocess.PIPE if worker else log,stderr=log,text=worker,start_new_session=True)
            children.append((name,child,log))
            result['children'][name] = dict(identity=json_identity(child.pid),argv=argv,cwd=str(cwd))
            return child
        def health():
            require(time.monotonic()-started < WALL_LIMIT, 'Independent wall watchdog exceeded')
            if native is not None:
                native.pump()
            if recorder is not None:
                recorder.pump()
            for name,child,_ in children:
                if child.poll() is not None and child.pid not in expected:
                    if name in ('native-parameters','recovery-task') and child.returncode==0:
                        expected.add(child.pid)
                        continue
                    raise RuntimeError(name+' exited unexpectedly: '+str(child.returncode))
        def phase(name,**fields):
            row = dict(phase=name,tick=clock.tick,ros_time_ns=clock.tick*clock.STEP_NS,
                       issued_monotonic_ns=time.monotonic_ns(),**fields)
            result['phases'].append(row)
            save(root/'progress.json',row)
            print(json.dumps(row),flush=True)
        def maps(label):
            for name,child,_ in children:
                if not name.endswith(('-fc','-model','-control')):
                    continue
                original = result['children'][name]
                require(json_identity(child.pid) == original['identity'], 'Owned process identity changed')
                proc = Path('/proc')/str(child.pid)
                executable = (proc/'exe').resolve()
                require(executable == Path(original['argv'][0]).resolve(),'Unexpected loaded executable')
                raw = (proc/'maps').read_text()
                require(not any(word in raw.lower() for word in ('libgz-','libgazebo','libignition','matlab','coptersim.exe')),
                        'Forbidden loaded runtime')
                if name.endswith('-model'):
                    require(str(library) in raw,'Model did not load the fixed library')
                path = root/(name+'-'+label+'-maps.txt')
                path.write_text(raw)
                result.setdefault('runtime_maps',{}).setdefault(label,{})[name] = dict(
                    identity=original['identity'],file=path.name,sha256=digest(path),
                    executable=str(executable),executable_sha256=digest(executable),
                    scene_phase=clock.phase,captured_monotonic_ns=time.monotonic_ns())
        with ExitStack() as resources:
            native = NativeBoundary(root,clock)
            resources.callback(native.close)
            recorder = Recorder(native,root,clock)
            resources.callback(recorder.close)
            publisher = ClockPublisher(native.node)
            resources.callback(publisher.close)
            wire = resources.enter_context((root/'joint-wire.jsonl').open('x',buffering=65536))
            clocks = resources.enter_context((root/'clock.jsonl').open('x',buffering=65536))
            rates = resources.enter_context((root/'rate.jsonl').open('x',buffering=65536))
            def record(kind,**fields):
                wire.write(json.dumps(dict(kind=kind,epoch=clock.epoch,tick=clock.tick,
                    wall=time.monotonic()-started,**fields),separators=(',',':'))+'\n')
            def rate_record(kind,**fields):
                rates.write(json.dumps(dict(kind=kind,epoch=clock.epoch,tick=clock.tick,
                    issued_monotonic_ns=time.monotonic_ns(),**fields),separators=(',',':'))+'\n')
            rate = JointRate(clock.epoch,.5,rate_record)
            workers, plans = {}, {}
            physics = JointPhysics(resources,clock,workers,health,record)
            publisher.publish(clock)
            clocks.write(json.dumps(clock.snapshot())+'\n')
            for stack in ('arducopter','px4'):
                directory = root/stack
                directory.mkdir()
                (directory/'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
                workers[stack] = launch(stack+'-model',[sys.executable,'-B','-m','Simulator.wksim_core.worker',
                    '--library',str(library),'--trace',str(root/(stack+'-truth.jsonl')),'--epoch',clock.epoch],directory,worker=True)
                plans[stack] = plan = launch_spec(configs[stack],directory,library)
                launch(stack+'-agent',plan['agent'],directory)
                launch(stack+'-fc',plan['fc'],directory,dict(os.environ,**plan['fc_environment']))
                result['children'][stack+'-fc']['environment_overrides'] = plan['fc_environment']
            physics.connect()
            stage, stage_tick, stable_tick, parameter_child, recovery_child = 'preflight',0,None,None,None
            recovery_ready, silence_tick, last_graph_tick = None,None,-1000
            def transition(name,**fields):
                nonlocal stage,stage_tick,stable_tick
                stage,stage_tick,stable_tick = name,clock.tick,None
                phase(name,**fields)
            def stable(ok,seconds):
                nonlocal stable_tick
                if not ok:
                    stable_tick = None
                elif stable_tick is None:
                    stable_tick = clock.tick
                return stable_tick is not None and clock.tick-stable_tick >= seconds*1000
            phase(stage)
            while clock.tick < MAX_TICKS:
                # Service-only and new Task normal exits are expected individually.
                for child in (parameter_child,recovery_child):
                    if child is not None and child.poll() == 0:
                        expected.add(child.pid)
                health()
                if clock.tick%4 == 0 and clock.synchronized:
                    if rate.anchor is None:
                        rate.reanchor(clock.tick,'synchronized_boundary')
                    rate.begin_group(clock.tick,health)
                states = physics.advance()
                publisher.publish(clock)
                clocks.write(json.dumps(clock.snapshot(),separators=(',',':'))+'\n')
                if clock.tick%4 == 0 and rate.group is not None:
                    rate.end_group(clock.tick)
                ap,px = states['arducopter'],states['px4']
                require(all(abs(v)<=100 for v in ap[6:9]) and -ap[8]<=MAX_HEIGHT and math.hypot(*ap[3:6])<=5
                        and max(abs(v) for v in ap[9:11])<=.7,'AP model exceeded frozen envelope')
                require(abs(px[8])<.3,'Disarmed PX4 left ground envelope')
                px_rows = [row for topic,row in recorder.latest.items() if '/vehicle_status' in topic]
                if px_rows:
                    require(px_rows[0]['message']['arming_state'] != 2,'PX4 must remain disarmed')
                    if native.active:
                        require(time.monotonic_ns()-px_rows[0]['received_monotonic_ns']<=2_000_000_000,
                                'PX4 native status stale')
                if clock.tick-last_graph_tick >= 200:
                    graph = recorder.publishers()
                    last_graph_tick = clock.tick
                    if stage not in ('recovery','done'):
                        allowed = {'wksim_arducopter_native_validation'}
                        require(all(row['node_name'] in allowed and row['node_namespace']=='/'
                                    for row in graph['/ap/cmd_gps_pose']), 'Unexpected native target publisher')
                        require(len(graph['/ap/cmd_gps_pose'])<=1,'Multiple native target publishers')
                        require(not graph['/ap/cmd_vel'],'Unexpected native velocity publisher')
                        if stage in ('mixed_prepare','mixed_baseline','terminal_burst','silence','stop_prepare','stop_dwell'):
                            require(len(graph['/ap/cmd_gps_pose'])==1,'Native target publisher set changed')
                    else:
                        endpoints = graph['/ap/cmd_gps_pose']
                        require(len(endpoints)<=1 and all(row['node_name']=='wksim_joint_arducopter_control'
                            and row['node_namespace']=='/' and row['gid']!=result['diagnostic_publisher']['gid']
                            for row in endpoints),'Recovery native target publisher differs')
                        if 'recovery_publisher' in result:
                            require(endpoints==[result['recovery_publisher']],'Recovery target publisher disappeared or changed')
                        elif endpoints:
                            result['recovery_publisher'] = endpoints[0]
                elapsed = (clock.tick-stage_tick)/1000
                if stage in ('terminal_burst','silence'):
                    require(abs(ap[5])<=3.,'Terminal-to-timeout vertical truth speed exceeded 3m/s')
                if stage == 'preflight':
                    require(elapsed < 55,'Native readiness timeout')
                    if stable(native.ready() and native.publishers['position'].get_subscription_count()==2
                              and native.navigation_ready() and bool(px_rows),2):
                        endpoints = recorder.publishers()['/ap/cmd_gps_pose']
                        require(len(endpoints)==1,'Diagnostic requires one discovered native target publisher')
                        result['diagnostic_publisher'] = endpoints[0]
                        maps('running')
                        parameter_child = launch('native-parameters',[sys.executable,'-B',str(Path(__file__)),
                            'parameters',str(root)],root)
                        transition('parameters')
                elif stage == 'parameters':
                    require(elapsed < 10,'Native parameter evidence timeout')
                    if parameter_child.poll() == 0:
                        native_log = json.loads((root/'parameters.json').read_text())
                        result['parameter_preflight'] = native_log
                        parameter_contract(native_log['parameters'])
                        native.command(176,[1,4,0,0,0,0,0])
                        transition('guided')
                elif stage in ('guided','armed','takeoff_ack'):
                    require(elapsed < 10,'Native service/status timeout: '+stage)
                    if native.command_done():
                        native.check_command()
                        mode_response = native.commands[-1]['response']
                        if stage == 'guided':
                            require(mode_response.get('curr_mode') == 4,'Mode service did not confirm GUIDED')
                        confirmed = native.mode_confirmed(4) if stage=='guided' else native.armed
                        if confirmed:
                            native.pending = None
                            if stage == 'guided':
                                native.command(400,[1,0,0,0,0,0,0]); transition('armed')
                            elif stage == 'armed':
                                require(native.navigation_ready(),'Native navigation invalid after normal arming')
                                native.active = True
                                native.command(22,[0,0,0,0,0,0,3]); transition('takeoff_ack')
                            else:
                                transition('takeoff')
                elif stage == 'takeoff':
                    require(elapsed < 25,'Native takeoff timeout')
                    if stable(abs(-ap[8]-3)<=.5 and math.hypot(*ap[3:6])<=.5,2):
                        transition('mixed_prepare')
                elif stage in ('mixed_prepare','mixed_baseline','terminal_burst'):
                    native.mixed(FINAL_ALTITUDE if stage=='terminal_burst' else 3.)
                    m = native.latest['wksim_state']
                    tracking = (abs(ap[4]-.8)<=.3 and abs(ap[3]-.4)<=.3 and abs(-ap[8]-3)<=.5
                        and angle_error(quaternion_yaw(m.pose.orientation),0.)<=.15)
                    if stage == 'mixed_prepare':
                        require(elapsed < 20,'Mixed native readiness timeout')
                        if stable(tracking,2):
                            transition('mixed_baseline')
                    elif stage == 'mixed_baseline':
                        require(tracking,'Mixed native baseline threshold exceeded')
                        if elapsed >= 3:
                            transition('terminal_burst')
                    elif elapsed >= .2:
                        silence_tick = native.last_target_tick
                        transition('silence',last_publish_tick=silence_tick,
                                   native_boot_us=native.latest['wksim_state'].time_boot_us)
                elif stage == 'silence':
                    require(native.pending is None,'Pending service in target silence window')
                    if clock.tick-silence_tick >= 3200:
                        transition('stop_prepare')
                elif stage == 'stop_prepare':
                    require(elapsed <= 10,'Native timeout did not settle inside fixed preparation bound')
                    if math.hypot(*ap[3:5])<=.25 and abs(-ap[8]-FINAL_ALTITUDE)<=.5:
                        anchor = ap[6:8]
                        transition('stop_dwell',anchor_ned_xy=anchor)
                elif stage == 'stop_dwell':
                    require(math.hypot(*ap[3:5])<=.25 and abs(-ap[8]-FINAL_ALTITUDE)<=.5
                            and math.dist(ap[6:8],anchor)<=1.,'Native timeout dwell threshold exceeded')
                    if elapsed >= 3:
                        native.retire_publisher()
                        transition('publisher_retired')
                elif stage == 'publisher_retired':
                    require(elapsed < 5,'Diagnostic publisher discovery did not retire')
                    if stable(not recorder.last_graph['/ap/cmd_gps_pose'],.2):
                        require(native.pending is None,'Native service remained at handover')
                        directory = root/'recovery'; directory.mkdir()
                        plan = plans['arducopter']['control']
                        for index,value in enumerate(plan):
                            if value.startswith('run_id:='): plan[index] = 'run_id:='+result['run_id']
                        plan += ['-p','use_sim_time:=true','-r','__node:=wksim_joint_arducopter_control']
                        verifier = ('import importlib.util,pathlib,hashlib,json; p=pathlib.Path('+repr(control['package'])+'); '
                            'assert pathlib.Path(importlib.util.find_spec("prometheus_control").origin).parent==p; '
                            'assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v for n,v in '
                            +repr(control['python_sha256'])+'.items()); import prometheus_control.node as n; n.main()')
                        launch('arducopter-control',[sys.executable,'-B','-c',verifier,*plan[3:]],directory,environment(control))
                        token = uuid.uuid4().hex
                        recovery_child = launch('recovery-task',[sys.executable,'-B',str(Path(__file__)),'recovery',
                            '--run-id',result['run_id'],'--scene-epoch',clock.epoch,'--start-token',token,
                            '--output',str(directory)],directory,environment(control))
                        transition('recovery',start_token=token)
                elif stage == 'recovery':
                    ready_path = root/'recovery/ready.json'
                    if recovery_ready is None and ready_path.is_file() and 'recovery_publisher' in result:
                        recovery_ready = json.loads(ready_path.read_text())
                        require(recovery_ready['run_id']==result['run_id'] and recovery_ready['scene_epoch']==clock.epoch
                            and recovery_ready['start_token']==token and recovery_ready['uav_id']==1
                            and re.fullmatch('[0-9a-f]{32}',recovery_ready['control_epoch']), 'Recovery identity mismatch')
                        save(root/'recovery/go.json',dict(version=1,scope=SCOPE,action='new_recovery_task',**recovery_ready))
                    if recovery_child.poll() == 0 and clock.tick%4 == 0:
                        result['recovery'] = json.loads((root/'recovery/result.json').read_text())
                        require(result['recovery']['status']=='pass' and abs(ap[8])<.3 and not native.armed,
                                'Public recovery/model final ground did not agree')
                        transition('done')
                        break
                if clock.tick%5000 == 0:
                    print(json.dumps(dict(tick=clock.tick,phase=stage,height=-ap[8])),flush=True)
            require(stage=='done','Fixed simulation budget exhausted')
            rate.check_boundary(clock.tick)
            rate.close_segment('completed',clock.tick)
            result['rate'] = rate.last_summary
            result['clock_publications'] = publisher.publications
            clock.request(dict(version=1,epoch=clock.epoch,request_id=clock.last_request+1,action='stop'))
            result['final_authority'] = clock.snapshot()
            result['terminal_transition'] = dict(action='stop',tick=clock.tick,phase=clock.phase,
                                                 issued_monotonic_ns=time.monotonic_ns())
            maps('completed')
            result['native'] = native.report()
            for child in workers.values():
                expected.add(child.pid)
                child.stdin.close(); child.wait(timeout=3)
                require(child.returncode==0,'Model failed normal close')
            result['status'] = 'observed'
    except BaseException as error:
        result.update(error=repr(error),traceback=traceback.format_exc(),authority_at_failure=clock.snapshot())
        print(result['traceback'],file=sys.stderr,flush=True)
    finally:
        result['cleanup_errors'] = stop_children(children)
        for name,child,_ in children:
            result['children'][name].update(returncode=child.returncode,remaining_group_members=group_members(child.pid))
        result['unowned_ap_after'] = json_identity(828)
        result['source_unchanged'] = all(digest(REPO/name)==sha for name,sha in result['source_sha256'].items())
        if 'admission' in result:
            result['source_unchanged'] &= all(digest(source)==digest(target) for source,target in retained)
            result['final_admission'] = admit(args.ap_mixed_manifest,args.ap_mixed_sha256,
                args.control_manifest,args.control_sha256,result['run_id'])
            result['source_unchanged'] &= result['final_admission']['ok']
        result['clean_shutdown'] = (not result['cleanup_errors'] and all(not v['remaining_group_members']
            and (not name.endswith(('-model','-control','-task','-parameters')) or v['returncode']==0)
            for name,v in result['children'].items()))
        if not result['clean_shutdown'] or not result['source_unchanged'] or result['unowned_ap_before']!=result['unowned_ap_after']:
            result['status'] = 'failed'
        result['wall_seconds'] = time.monotonic()-started
        save(root/'result.json',result)
        shutil.copytree(root,archive,dirs_exist_ok=True)
        print(json.dumps(dict(status=result['status'],archive=str(archive),error=result.get('error'))),flush=True)
    return 0 if result['status']=='observed' else 1


def audit(root):
    """Offline raw source/native-clock/truth audit, never flight from mocks."""
    from audit_joint_flight import audit_timeline, lines
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from audit_pv_trajectory import rate_windows
    from Simulator.wksim_runtime.joint_profile import package_digest
    root = Path(root)
    result = json.loads((root/'result.json').read_text())
    require(result['scope']==SCOPE and result['status']=='observed' and result['clean_shutdown']
            and result['source_unchanged'],'Run did not complete cleanly')
    require(set(result['source_sha256'])==set(SOURCES),'Mandatory executed source set differs')
    require(result['bounds']==dict(wall_seconds=900,simulation_ticks=180000,requested_rate=.5)
            and result['wall_seconds']<=900 and result['final_authority']['phase']=='stopped'
            and 0<result['final_authority']['tick']<=180000 and result['final_authority']['tick']%4==0,
            'Frozen runtime bounds or terminal authority differ')
    for name,sha in result['source_sha256'].items():
        require(digest(root/('source__'+name.replace('/','__')+'.txt'))==sha,'Retained runner source differs')
    for name,sha in result['retained_sha256'].items():
        require(digest(root/name)==sha,'Retained control/native source differs')
    admission = json.loads((root/'experimental-admission.json').read_text())
    require(admission==result['admission'] and admission['ok'] and admission['experimental']
            and not admission['production_admitted'] and not admission['flown']
            and admission['manifest_path']==AP_MANIFEST and admission['manifest_sha256']==AP_SHA,
            'Experimental build admission differs')
    require(digest(root/'ap-build.json')==AP_SHA
            and digest(root/'control-build.json')==admission['control_manifest_sha256'], 'Sealed manifests changed')
    require(json.loads((root/'ap-build.json').read_text())==admission['candidate']
            and json.loads((root/'control-build.json').read_text())==admission['control_candidate'],
            'Retained build records differ from admission')
    for name,sha in admission['identities']['source_sha256'].items():
        require(result['source_sha256'].get(name)==sha,'Admission/execution source mismatch: '+name)
    for name,pin in admission['identities']['baseline']['message_packages'].items():
        require(package_digest(pin['prefix'],complete=pin.get('complete_snapshot',False))==pin['sha256'],
                'Raw CDR decoder message package changed: '+name)
    require(result['model_build']==admission['identities']['baseline']['model'], 'Model build differs')
    require(result['model_library_sha256']==result['model_build']['library_sha256'],'Model library hash differs')
    require(result['unowned_ap_before']==result['unowned_ap_after'] and not result['cleanup_errors'], 'Cleanup identity differs')
    expected_children = {'arducopter-model','px4-model','arducopter-fc','px4-fc',
                         'arducopter-agent','px4-agent','native-parameters','arducopter-control','recovery-task'}
    require(set(result['children'])==expected_children,'Unexpected process set')
    for name,child in result['children'].items():
        require(child['identity']['pid']==child['identity']['pgid'] and not child['remaining_group_members'],
                'Owned process was not correctly retired')
        if name.endswith(('-model','-control','-task','-parameters')):
            require(child['returncode']==0,'Expected normal child exit')
    for label,names in (('running',{'arducopter-fc','px4-fc','arducopter-model','px4-model'}),
                        ('completed',{'arducopter-fc','px4-fc','arducopter-model','px4-model','arducopter-control'})):
        require(set(result['runtime_maps'][label])==names,'Missing loaded mapping evidence')
        for name,item in result['runtime_maps'][label].items():
            path = root/item['file']; child = result['children'][name]
            require(digest(path)==item['sha256'] and item['identity']==child['identity']
                    and item['scene_phase']==('running' if label=='running' else 'stopped')
                    and (label=='running' or item['captured_monotonic_ns']>=result['terminal_transition']['issued_monotonic_ns'])
                    and not any(token in path.read_text().lower() for token in
                                ('libgz-','libgazebo','libignition','matlab','coptersim.exe')),
                    'Loaded library mapping identity differs')
            if name=='arducopter-fc':
                expected_binary = admission['candidate_verification']['binary']
            elif name=='px4-fc':
                expected_binary = admission['identities']['baseline']['px4']
            else:
                expected_binary = None
            if expected_binary:
                require(item['executable']==child['argv'][0]==expected_binary['path']
                        and item['executable_sha256']==expected_binary['sha256'],'Loaded firmware differs from sealed admission')
            if name.endswith('-model'):
                require(admission['model_library'] in path.read_text(),'Loaded model library differs')
    timeline,model = audit_timeline(root,result,require_flight=False,require_ground=True)
    rate_report = rate_windows(root,result)
    phases = {row['phase']:row for row in result['phases']}
    require([row['phase'] for row in result['phases']]==['preflight','parameters','guided','armed','takeoff_ack',
        'takeoff','mixed_prepare','mixed_baseline','terminal_burst','silence','stop_prepare','stop_dwell',
        'publisher_retired','recovery','done'], 'Native/public phase contract changed or repeated')
    data = read_native_log(root)
    timeout_ms = parameter_contract(data['parameters'])
    require(data['parameters']==result['parameter_preflight']['parameters'],'Runtime/native final parameters differ')
    raw = list(lines(root/'native-raw.jsonl'))
    method = json.loads((root/'recorder-method.json').read_text())
    require(method['per_message_publisher_gid_available'] is False
            and digest(root/'recorder-executor-source.txt')==method['executor_source_sha256'],
            'Recorder mechanism/installed source evidence differs')
    types = {'/ap/cmd_gps_pose':'ardupilot_msgs/msg/GlobalPosition','/ap/cmd_vel':'geometry_msgs/msg/TwistStamped',
        '/ap/wksim/local_state_v1':'ardupilot_msgs/msg/WksimState','/ap/status':'ardupilot_msgs/msg/Status',
        '/ap/gps_global_origin/filtered':'geographic_msgs/msg/GeoPointStamped',
        '/uav1/prometheus/v2/state':'wksim_msgs/msg/SessionState','/uav1/prometheus/text_info':'prometheus_msgs/msg/TextInfo'}
    for sequence,row in enumerate(raw,1):
        require(row['topic'] in types or row['topic'].startswith('/wksim_px4_21/fmu/out/vehicle_status'),
                'Unexpected raw topic')
        cls = get_message(types.get(row['topic'],'px4_msgs/msg/VehicleStatus'))
        require(row['sequence']==sequence and row['epoch']==result['scene_epoch']
            and row['per_message_publisher_gid_available'] is False and 'publisher_gid' not in row
            and json_value(message_to_ordereddict(deserialize_message(bytes.fromhex(row['cdr_hex']),cls)))==row['message'],
            'Raw CDR, GID, sequence or decoded evidence differs')
    targets = [row for row in raw if row['topic']=='/ap/cmd_gps_pose']
    states = [row for row in raw if row['topic']=='/ap/wksim/local_state_v1']
    require(targets and states,'Missing raw target/native state observations')
    silence_start,transfer = phases['silence']['tick'],phases['recovery']['tick']
    monitored = [row for row in raw if phases['takeoff']['tick']<=row['tick']<=transfer
                 and row['topic'] in ('/ap/status','/ap/wksim/local_state_v1','/ap/gps_global_origin/filtered')]
    for topic in ('/ap/status','/ap/wksim/local_state_v1','/ap/gps_global_origin/filtered'):
        channel = [row for row in monitored if row['topic']==topic]
        require(channel,'Native state channel missing')
        if topic!='/ap/gps_global_origin/filtered':
            require(all(0<b['received_monotonic_ns']-a['received_monotonic_ns']<=2_000_000_000
                        for a,b in zip(channel,channel[1:])),'Native raw observation became stale')
        if topic=='/ap/status':
            require(all(row['message']['armed'] and row['message']['mode']==4 and not row['message']['failsafe']
                        for row in channel),'Native GUIDED/armed/healthy state changed during silence experiment')
        elif topic=='/ap/wksim/local_state_v1':
            keys = ('home_latitude_e7','home_longitude_e7','home_altitude_cm','yaw_reset_ms',
                    'position_ne_reset_ms','position_down_reset_ms')
            require(len({tuple(row['message'][key] for key in keys) for row in channel})==1,
                    'Native home/reset identity changed')
            require(all(b['message']['time_boot_us']>a['message']['time_boot_us'] for a,b in zip(channel,channel[1:])),
                    'Native source boot clock did not advance')
        else:
            require(len({json.dumps(row['message']['position'],sort_keys=True) for row in channel})==1,
                    'Native origin changed')
    commands = result['native']['commands']
    require([row['command_id'] for row in commands]==[176,400,22]
            and all(row['tick']<phases['mixed_prepare']['tick'] for row in commands)
            and commands[0]['response']['status'] and commands[0]['response']['curr_mode']==4
            and commands[1]['response']['result'] and commands[2]['response']['status'],
            'Native services changed or remained inside observation window')
    native_targets = [row for row in targets if row['tick']<transfer]
    graphs = list(lines(root/'publisher-graph.jsonl'))
    diagnostic,recovery = result['diagnostic_publisher'],result['recovery_publisher']
    require(diagnostic['node_name']=='wksim_arducopter_native_validation'
            and recovery['node_name']=='wksim_joint_arducopter_control'
            and diagnostic['node_namespace']==recovery['node_namespace']=='/'
            and diagnostic['gid']!=recovery['gid'],'Discovered native source handoff identities differ')
    zero = [row for row in graphs if phases['publisher_retired']['tick']<=row['tick']<=transfer
            and not row['publishers']['/ap/cmd_gps_pose']]
    require(zero and transfer-zero[0]['tick']>=200,'No observed zero-publisher transfer interval')
    seen_native = {}
    for row in graphs:
        endpoints = row['publishers']['/ap/cmd_gps_pose']
        require(row['epoch']==result['scene_epoch'] and len(endpoints)<=1,'Publisher graph epoch/count differs')
        if phases['mixed_prepare']['tick']<=row['tick']<phases['publisher_retired']['tick']:
            require(endpoints==[diagnostic],'Diagnostic discovered publisher changed')
        elif row['tick']>=transfer:
            require(endpoints in ([],[recovery]),'Unexpected discovered recovery publisher')
        for topic in ('/ap/status','/ap/wksim/local_state_v1','/ap/gps_global_origin/filtered'):
            if phases['takeoff']['tick']<=row['tick']<=transfer:
                current = row['publishers'][topic]
                require(len(current)==1,'Native observation graph has missing/ambiguous publisher')
                if topic in seen_native:
                    require(current==seen_native[topic],'Native discovered state publisher changed')
                seen_native[topic] = current
    burst = phases['terminal_burst']['tick']
    for row in native_targets:
        msg = row['message']; stamp = msg['header']['stamp']['sec']*1000+msg['header']['stamp']['nanosec']/1e6
        validate_mixed_target(msg)
        require(0<stamp<=row['tick'] and row['tick']-stamp<=200,'Native target stamp freshness differs')
        require(msg['altitude']==(3. if stamp<burst else FINAL_ALTITUDE),'Native altitude changed outside frozen terminal phase')
    last = native_targets[-1]
    require(last['message']['altitude']==FINAL_ALTITUDE and last['tick']<=silence_start+200,'Final native target not observed promptly')
    require(not any(last['tick']<row['tick']<transfer for row in targets),'Native target silence was interrupted')
    require(not any(row['topic']=='/ap/cmd_vel' and row['tick']<transfer for row in raw),'Velocity target interrupted native window')
    mixed = [row for row in data['rows'] if row.get('mavpackettype')=='GUIP' and row['Type']==7]
    require(mixed,'No actual GUIP type 7 acceptance')
    accepted = mixed[-1]
    require(accepted['Terrain']==0 and all(accepted[k]==0 for k in ('pX','pY','vZ','aX','aY','aZ'))
            and abs(accepted['vX']-.4)<1e-6 and abs(accepted['vY']-.8)<1e-6,'Last GUIP active/inactive axes differ')
    boundary_us = (int(accepted['TimeUS'])//1000+timeout_ms+1)*1000
    acceptance_before = [row for row in states if row['message']['time_boot_us']<=accepted['TimeUS']]
    acceptance_after = [row for row in states if row['message']['time_boot_us']>accepted['TimeUS']]
    require(acceptance_before and acceptance_after
            and acceptance_before[-1]['tick']>=burst-200 and acceptance_after[0]['tick']<=silence_start+200,
            'Last GUIP acceptance is not associated with the bounded final target burst')
    before = [row for row in states if row['message']['time_boot_us']<boundary_us]
    after = [row for row in states if row['message']['time_boot_us']>=boundary_us]
    require(before and after,'Native timeout boundary lacks surrounding raw boot samples')
    left,right = before[-1],after[0]
    require(left['tick']<right['tick']<phases['stop_dwell']['tick']<transfer,'Native timeout clock ordering differs')
    origins = [row for row in data['rows'] if row.get('mavpackettype')=='ORGN' and row['Type']==0
               and row['TimeUS']<=accepted['TimeUS']]
    require(origins,'Missing EKF ORGN altitude for Pz conversion')
    home = left['message']['home_altitude_cm']/100.
    require(abs(accepted['pZ']+(FINAL_ALTITUDE+home-origins[-1]['Alt']))<=.02,
            'Accepted Pz is not the home/origin converted terminal altitude')
    ap = model['arducopter']
    def samples(lo,hi):
        require(0<lo<=hi<=len(ap),'Invalid audit tick window')
        return [row[0] for row in ap[lo-1:hi]]
    baseline = samples(phases['mixed_baseline']['tick'],phases['terminal_burst']['tick'])
    require(len(baseline)>=3000 and all(abs(row[4]-.8)<=.3 and abs(row[3]-.4)<=.3
            and abs(-row[2]-3)<=.5 for row in baseline),'Every-tick native baseline failed')
    for row in lines(root/'arducopter-truth.jsonl'):
        state = row['state']
        require(all(abs(v)<=100 for v in state[6:9]) and -state[8]<=MAX_HEIGHT
                and math.hypot(*state[3:6])<=5 and max(abs(v) for v in state[9:11])<=.7,
                'Every-tick native physical envelope failed')
        if phases['mixed_baseline']['tick']<=row['tick']<=burst:
            require(angle_error(math.pi/2-state[11],0.)<=.15,'Every-tick baseline truth yaw failed')
    dwell = samples(phases['stop_dwell']['tick'],phases['publisher_retired']['tick'])
    anchor = phases['stop_dwell']['anchor_ned_xy']
    require(len(dwell)>=3000 and all(math.hypot(*row[3:5])<=.25 and abs(-row[2]-FINAL_ALTITUDE)<=.5
            and math.dist(row[:2],anchor)<=1 for row in dwell),'Every-tick timeout stop dwell failed')
    bracket = samples(left['tick'],right['tick'])
    error = min(abs(-row[2]-FINAL_ALTITUDE) for row in bracket)
    require(right['tick']-burst<=3400 and all(abs(row[5])<=3 for row in samples(burst,right['tick'])),
            'Frozen terminal vertical-speed/native-time discriminability envelope failed')
    require(max(math.hypot(*row[3:5]) for row in bracket)>.4,'Timeout was not entered with significant XY velocity')
    require(phases['stop_dwell']['tick']-right['tick']<=10000,'Stop preparation exceeded true timeout boundary allowance')
    report = result['recovery']
    require(report==json.loads((root/'recovery/result.json').read_text())
            and report['status']=='pass' and report['use_sim_time'],'Fresh public recovery failed')
    ready = json.loads((root/'recovery/ready.json').read_text())
    validate_offer(report['offer'],ready)
    require(report['offer']==json.loads((root/'recovery/go.json').read_text())
            and ready['run_id']==result['run_id'] and ready['scene_epoch']==result['scene_epoch'],
            'Public recovery offer identities differ')
    sessions = [row for row in raw if row['topic']=='/uav1/prometheus/v2/state']
    require(sessions and all(row['tick']>=transfer and row['message']['run_id']==result['run_id']
            and row['message']['control_epoch']==ready['control_epoch'] for row in sessions),
            'Raw public sessions do not bind to the new recovery epoch')
    events = [json.loads(row['message']['message']) for row in raw if row['topic']=='/uav1/prometheus/text_info']
    requests = report['task']['request_envelopes']
    require(len(requests)==3 and all(row['run_id']==result['run_id'] and row['control_epoch']==report['offer']['control_epoch']
            for row in requests),'Public recovery envelopes differ')
    require(requests[0]['setup']['cmd']==3 and requests[0]['setup']['control_state']=='COMMAND_CONTROL'
            and requests[1]['command']['agent_cmd']==3 and requests[2]['setup']['cmd']==1
            and requests[2]['setup']['px4_mode']=='AUTO.LOITER'
            and [row['request_id'] for row in requests]==list(range(requests[0]['request_id'],requests[0]['request_id']+3)),
            'Public recovery did not explicitly take over, land and enter ground hold')
    for request in requests:
        expected_event = 'setup_completed' if 'setup' in request else 'command_accepted'
        require(any(event.get('event')==expected_event and event.get('request_id')==request['request_id']
                and event.get('run_id')==result['run_id'] and event.get('control_epoch')==ready['control_epoch']
                for event in events),'Public recovery request lacks matching raw Control event')
    require(not any(e['event'] in ('control_revoked','setup_rejected','command_rejected')
                    for e in report['task']['events']),'Recovery revoked/rejected')
    recovery_targets = [row for row in targets if row['tick']>=transfer]
    require(recovery_targets and all(row['message']['type_mask']==2552 for row in recovery_targets),
            'New public takeover must use full position')
    for row in raw:
        if '/vehicle_status' in row['topic']:
            require(row['message']['arming_state']!=2,'PX4 armed in AP-only boundary experiment')
    return dict(status='pass' if error>.75 else 'inconclusive',scope=SCOPE,timeline=timeline,rate=rate_report,
        last_native_acceptance=accepted,native_timeout_boundary_us=boundary_us,
        timeout_bracket_ticks=[left['tick'],right['tick']],minimum_boundary_z_error_m=error,
        z_correction='pass' if error>.75 else 'inconclusive_already_near_target_at_timeout',
        stop_dwell_ticks=len(dwell),public_recovery='pass',production_admitted=False,
        attribution='strict discovered endpoint transitions; per-message publisher GID unavailable and not reconstructed',
        parameters=data['parameters'],native_log_files=data['files'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='role',required=True)
    runner = sub.add_parser('run')
    runner.add_argument('--ap-mixed-manifest',default=AP_MANIFEST)
    runner.add_argument('--ap-mixed-sha256',default=AP_SHA)
    runner.add_argument('--control-manifest',required=True)
    runner.add_argument('--control-sha256',required=True)
    auditor = sub.add_parser('audit')
    auditor.add_argument('directory',type=Path)
    auditor.add_argument('--output',type=Path,required=True)
    sub.add_parser('parameters').add_argument('directory',type=Path)
    recovery = sub.add_parser('recovery')
    for name in ('run-id','scene-epoch','start-token','output'):
        recovery.add_argument('--'+name,required=True)
    args = parser.parse_args(argv)
    if args.role=='run':
        validate_inputs(args)
        return run(args)
    if args.role=='recovery':
        return recovery_main(args)
    if args.role=='parameters':
        data = read_native_log(args.directory)
        parameter_contract(data['parameters'])
        save(args.directory/'parameters.json',data)
        return 0
    validate_audit_output(args.directory,args.output)
    try:
        report = audit(args.directory)
    except BaseException as error:
        report = dict(status='failed',scope=SCOPE,error=repr(error),traceback=traceback.format_exc())
    save(args.output,report)
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='pass' else 2 if report['status']=='inconclusive' else 1


if __name__=='__main__':
    raise SystemExit(main())
