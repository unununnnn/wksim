"""Bounded #8 ground investigation. No flight commands, task node or UE.

--native-clocks adds two Agents and a read-only DDS observer, never a controller.

One authority issues every 1ms tick to two process-isolated generated models.
AP JSON receives 1ms states; PX4 HIL_SENSOR receives 4ms states. Startup is
explicitly weaker than a barrier; after the first PX4 actuator, each 4ms
barrier requires its exact raw clock and the next AP servo frame. This is a
candidate protocol experiment, not an accepted production scheduler.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_core.model import Model, build_model
from Simulator.wksim_core.ap_json import decode_servos, sensor_message
from Simulator.wksim_runtime.config import load_config
from Simulator.wksim_runtime.isolation import check_isolation
from Simulator.wksim_runtime.preflight import preflight
from Simulator.wksim_runtime.runtime import digest, launch_spec, stop_children
from ap_clock_candidate import admit

PRE_TICKS, POST_TICKS, MACRO_TICKS = 8000, 2000, 4
PAUSE_SECONDS, WALL_LIMIT = 2.0, 90.0


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False)


def step_request(request, current_tick):
    if (not isinstance(request, dict) or set(request) != {'tick', 'commands'}
            or type(request['tick']) is not int or request['tick'] != current_tick + 1):
        raise ValueError('Model worker requires exactly the next authoritative tick')
    return request['commands']


def model_worker(library, trace):
    # The generated model has static parameters: one instance per OS process.
    with Model(library) as model, Path(trace).open('x', encoding='utf-8') as log:
        state = None
        for line in sys.stdin:
            request = json.loads(line)
            if request == {'snapshot': True}:
                response = dict(tick=model.ticks, state=state)
            else:
                commands = step_request(request, model.ticks)
                state = model.step(commands)
                response = dict(tick=model.ticks, state=state)
                log.write(encoded(dict(**response, commands=commands)) + '\n')
            print(encoded(response), flush=True)


def receive_worker(child, request):
    child.stdin.write(encoded(request) + '\n')
    child.stdin.flush()
    if not select.select([child.stdout], [], [], 3)[0]:
        raise TimeoutError('Model worker response timeout')
    line = child.stdout.readline()
    if not line:
        raise RuntimeError('Model worker exited without a response')
    return json.loads(line)


def process_identity(pid):
    root = Path('/proc') / str(pid)
    try:
        fields = (root / 'stat').read_text().rsplit(')', 1)[1].split()
        return dict(pid=pid, state=fields[0], pgid=int(fields[2]), start_ticks=int(fields[19]),
                    argv=(root / 'cmdline').read_bytes().split(b'\0')[:-1])
    except FileNotFoundError:
        return None


def json_identity(pid):
    value = process_identity(pid)
    if value:
        value.pop('state')  # Runnable/sleeping is not a process identity change.
        value['argv'] = [part.decode(errors='replace') for part in value['argv']]
    return value


def group_members(pgid):
    return [item for entry in Path('/proc').iterdir() if entry.name.isdecimal()
            and (item := json_identity(int(entry.name))) and item['pgid'] == pgid]


class WireProbe:
    def __init__(self, stack, logs, children):
        from pymavlink.dialects.v20 import common as mavlink
        self.mavlink = mavlink
        self.stack, self.logs, self.children = stack, logs, children
        self.started = time.monotonic()
        self.phase, self._tick = 'startup', 0
        self.authority = self.scene_observer = None
        self.ap = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        self.ap.bind(('127.0.0.1', 19002))
        self.ap.setblocking(False)
        self.listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        # Cold construction reuses our private port after the retired TCP
        # connection enters TIME_WAIT; no foreign listener is displaced.
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(('127.0.0.1', 4581))
        self.listener.listen(1)
        self.listener.settimeout(25)
        self.connection = None
        self.peer = None
        self.pending_ap = None
        self.last_px_time = None
        self.native = None
        self.px_commands = [0.0] * 16
        self.latest, self.counts = {}, {}
        self.raw_counts = {'ap': 0, 'px4': 0, 'sensor_ap': 0, 'sensor_px4': 0}
        self.telemetry = {}
        for name, port in [('arducopter', 14660), ('px4', 14661)]:
            sock = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            sock.bind(('127.0.0.1', port))
            sock.setblocking(False)
            parser = mavlink.MAVLink(None)
            parser.robust_parsing = True
            self.telemetry[sock] = (name, parser)

    def log(self, stream, **event):
        self.logs[stream].write(encoded(dict(phase=self.phase, tick=self.tick,
                                            wall=time.monotonic() - self.started, **event)) + '\n')

    @property
    def tick(self):
        return self.authority.tick if self.authority is not None else self._tick

    def worker_rpc(self, child, request):
        if self.authority is None:
            return receive_worker(child, request)
        from Simulator.wksim_core.worker import receive_worker as epoch_rpc
        return epoch_rpc(child, dict(version=1, epoch=self.authority.epoch, **request), self.authority.epoch)

    def scene_action(self, action):
        request = dict(version=1, epoch=self.authority.epoch,
                       request_id=self.authority.last_request+1, action=action)
        self.authority.request(request)
        self.log('scene-clock', kind='action', request=request, authority=self.authority.snapshot())

    def health(self):
        if time.monotonic() - self.started > WALL_LIMIT:
            raise TimeoutError('Bounded ground probe wall watchdog')
        for name, child, _ in self.children:
            if child.poll() is not None:
                raise RuntimeError(f'{name} exited unexpectedly: {child.returncode}')

    def telemetry_pump(self):
        self.health()
        if self.scene_observer:
            self.scene_observer.pump()
        if self.native:
            self.native.pump()
        for sock, (name, parser) in self.telemetry.items():
            while True:
                try:
                    data = sock.recv(65535)
                except BlockingIOError:
                    break
                self.log('telemetry-wire', stack=name, packet_hex=data.hex())
                for message in parser.parse_buffer(data) or []:
                    kind = message.get_type()
                    if kind == 'BAD_DATA':
                        # A serial startup banner is not a FC clock sample. Keep
                        # the exact bytes and parser reason; never turn it into one.
                        key = name + '/BAD_DATA'
                        self.counts[key] = self.counts.get(key, 0) + 1
                        self.log('telemetry', stack=name, invalid_data_hex=bytes(message.data).hex(),
                                 reason=message.reason)
                        continue
                    if kind not in ('HEARTBEAT', 'ATTITUDE', 'LOCAL_POSITION_NED', 'SYSTEM_TIME'):
                        continue
                    if message.get_srcSystem() != (241 if name == 'arducopter' else 22):
                        raise ValueError(f'Unexpected {name}/{kind} telemetry system identity: {message.get_srcSystem()}')
                    if kind == 'HEARTBEAT' and message.base_mode & 128:
                        raise RuntimeError('Ground-only probe observed an armed heartbeat')
                    value = message.to_dict()
                    self.latest[name + '/' + kind] = value
                    self.counts[name + '/' + kind] = self.counts.get(name + '/' + kind, 0) + 1
                    self.log('telemetry', stack=name, message=value)

    def connect(self):
        self.connection, address = self.listener.accept()
        if address[0] != '127.0.0.1':
            raise RuntimeError('Non-loopback simulator peer')
        self.stack.enter_context(self.connection)
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connection.settimeout(2)
        from Simulator.wksim_core.px4_mavlink import Sender
        self.protocol = self.mavlink.MAVLink(Sender(self.connection), srcSystem=254, srcComponent=51)
        self.log('wire', direction='connect', stack='px4', peer=list(address))
        self.pending_ap = self.wait_ap(None)

    def read_ap(self):
        packet, address = self.ap.recvfrom(4096)
        if self.peer is None:
            self.peer = address
        if address != self.peer or address[0] != '127.0.0.1':
            raise ValueError('AP simulator peer changed')
        frame, rate, pwm, commands = decode_servos(packet)
        if any(commands):
            raise RuntimeError('Ground-only probe received nonzero AP motor input')
        self.raw_counts['ap'] += 1
        self.log('wire', direction='receive', stack='arducopter', packet_hex=packet.hex(),
                 frame=frame, rate=rate, pwm=pwm)
        return dict(frame=frame, rate=rate, commands=commands)

    def wait_ap(self, previous):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.telemetry_pump()
            if not select.select([self.ap], [], [], 0.002)[0]:
                continue
            packet = self.read_ap()
            if previous is None or packet['frame'] == (previous + 1) % 2**32:
                return packet
            if packet['frame'] != previous:
                raise RuntimeError('AP actuator frame discontinuity')
            # A stale duplicate is logged but cannot grant another model step.
        raise TimeoutError('AP next actuator frame timeout')

    def read_px(self):
        data = self.connection.recv(8192)
        if not data:
            raise ConnectionError('PX4 simulator TCP closed')
        result = []
        from Simulator.wksim_core.px4_mavlink import actuator_commands
        for message in self.protocol.parse_buffer(data) or []:
            if message.get_type() != 'HIL_ACTUATOR_CONTROLS':
                continue
            self.raw_counts['px4'] += 1
            self.log('wire', direction='receive', stack='px4', message=message.to_dict(),
                     packet_hex=bytes(message.get_msgbuf()).hex())
            if not message.flags & 1 or message.mode & 128:
                raise RuntimeError('PX4 must report lockstep and remain disarmed')
            if message.time_usec > self.tick * 1000:
                raise RuntimeError('PX4 clock ahead of authoritative model time')
            if self.last_px_time is not None and message.time_usec < self.last_px_time:
                raise RuntimeError('PX4 actuator clock regressed')
            self.last_px_time = message.time_usec
            self.px_commands = actuator_commands(message)
            result.append(message.time_usec)
        return result

    def wait_px(self):
        bootstrapping = self.last_px_time is None
        deadline = time.monotonic() + (0.004 if bootstrapping else 5)
        while time.monotonic() < deadline:
            self.telemetry_pump()
            if select.select([self.connection], [], [], 0.001)[0]:
                timestamps = self.read_px()
                if self.tick * 1000 in timestamps:
                    return True
        if not bootstrapping:
            raise TimeoutError('PX4 did not acknowledge the exact macro-barrier time')
        return False

    def advance(self, workers):
        self.health()
        target = self.authority.begin_step() if self.authority else self.tick + 1
        source_ap, source_px = self.pending_ap['frame'], self.last_px_time
        states, responses = {}, {}
        for name, commands in [('arducopter', self.pending_ap['commands']), ('px4', self.px_commands)]:
            answer = self.worker_rpc(workers[name], dict(tick=target, commands=commands))
            if answer['tick'] != target or abs(answer['state'][2] - target * .001) > 1e-8:
                raise RuntimeError('Model did not reach the authoritative tick')
            states[name] = answer['state']
            responses[name] = answer
        if self.authority:
            self.authority.commit(responses)
            self.scene_observer.publish()
        else:
            self._tick = target
        ap_packet = sensor_message(states['arducopter'])
        # Explicitly keep the fixed candidate's default virtual-time semantics.
        # This is sensor transport configuration, never a flight/control command.
        ap_value = json.loads(ap_packet)
        ap_value.update(no_lockstep=False, no_time_sync=False)
        ap_packet = ('\n' + encoded(ap_value) + '\n').encode('ascii')
        self.ap.sendto(ap_packet, self.peer)
        self.raw_counts['sensor_ap'] += 1
        self.log('wire', direction='send', stack='arducopter', sensor_time=states['arducopter'][2],
                 packet_sha256=hashlib.sha256(ap_packet).hexdigest(), source_frame=source_ap)
        if self.tick % MACRO_TICKS == 0:
            from Simulator.wksim_core.px4_mavlink import gps_arguments
            sensor = states['px4'][60:90]
            if round(sensor[0]) != self.tick * 1000:
                raise RuntimeError('Generated PX4 sensor time is not the shared tick')
            self.protocol.hil_sensor_send(round(sensor[0]), *sensor[1:14], round(sensor[14]))
            if self.tick % 100 == 0:
                self.protocol.hil_gps_send(*gps_arguments(states['px4']))
            self.raw_counts['sensor_px4'] += 1
            self.log('wire', direction='send', stack='px4', sensor_time_usec=round(sensor[0]))
        self.pending_ap = self.wait_ap(source_ap)
        if self.tick % MACRO_TICKS == 0:
            synchronized = self.wait_px()
            if self.authority:
                self.authority.barrier(self.pending_ap['frame'], self.last_px_time, synchronized)
            self.log('barriers', synchronized=synchronized, px4_time_usec=self.last_px_time,
                     ap_next_frame=self.pending_ap['frame'])
        self.log('steps', ap_source_frame=source_ap, px4_source_time_usec=source_px,
                 model_ticks={name: self.tick for name in states})
        if self.tick > 4000 and self.last_px_time is None:
            raise TimeoutError('PX4 actuator startup exceeded 4 simulated seconds')

    def snapshot(self, workers):
        result = {}
        for name, worker in workers.items():
            answer = self.worker_rpc(worker, {'snapshot': True})
            result[name] = dict(tick=answer['tick'], state_time=answer['state'][2],
                                state_sha256=hashlib.sha256(encoded(answer['state']).encode()).hexdigest())
        snapshot = dict(models=result, tick=self.tick, px4_time_usec=self.last_px_time,
                    ap_pending_frame=self.pending_ap['frame'], telemetry=dict(self.latest),
                    raw_counts=dict(self.raw_counts))
        if self.native:
            snapshot['native_clocks'] = self.native.snapshot()
        if self.authority:
            snapshot['authority'] = self.authority.snapshot()
            snapshot['ros_time_ns'] = self.scene_observer.last_ns
        return snapshot

    def pause(self, workers):
        if self.authority:
            if self.authority.phase == 'running':
                self.scene_action('pause')
            if self.authority.phase != 'paused':
                raise RuntimeError('Scene authority did not reach paused state')
            self.scene_observer.at_boundary()
        before = self.snapshot(workers)
        started = time.monotonic()
        while time.monotonic() - started < PAUSE_SECONDS:
            self.telemetry_pump()
            ready, _, _ = select.select([self.ap, self.connection], [], [], .02)
            for sock in ready:
                if sock is self.ap:
                    if self.read_ap()['frame'] != before['ap_pending_frame']:
                        raise RuntimeError('AP advanced to another frame while sensors were paused')
                else:
                    if any(t != before['px4_time_usec'] for t in self.read_px()):
                        raise RuntimeError('PX4 advanced its actuator clock while sensors were paused')
        after = self.snapshot(workers)
        if after['models'] != before['models']:
            raise RuntimeError('A model advanced without an authoritative step')
        if self.authority and before['ros_time_ns'] != after['ros_time_ns']:
            raise RuntimeError('Real ROS time advanced during physical pause')
        for kind in ('sensor_ap', 'sensor_px4'):
            if before['raw_counts'][kind] != after['raw_counts'][kind]:
                raise RuntimeError('Sensors were sent during the pause')
        return dict(before=before, after=after, wall_seconds=time.monotonic() - started)


def main(native_clocks=False, ap_build_manifest=None, ap_build_sha256=None, require_aligned_clocks=False,
         scene_clock=False, retired_epoch=None):
    check_isolation()
    prefix = 'joint-scene-clock-' if scene_clock else 'joint-native-clock-' if native_clocks else 'joint-clock-ground-'
    output = Path(tempfile.mkdtemp(prefix=prefix, dir=REPO / 'validation'))
    scratch = Path(tempfile.mkdtemp(prefix='wksim-joint-clock-'))
    result = dict(status='failed', scope='experimental disarmed ground handshake; NOT G2 acceptance',
                  result_dir=str(output), scratch=str(scratch), run_epoch=uuid.uuid4().hex,
                  commands_sent=0, agents_started=0, ros_nodes_started=0,
                  native_clocks_enabled=native_clocks,
                  scene_clock_enabled=scene_clock, retired_epoch=retired_epoch,
                  require_aligned_clocks=require_aligned_clocks,
                  ap_build_manifest_sha256=ap_build_sha256,
                  thresholds=dict(pre_ticks=PRE_TICKS, post_ticks=POST_TICKS, macro_ticks=MACRO_TICKS,
                                  step_ms=1, pause_wall_seconds=PAUSE_SECONDS, wall_limit=WALL_LIMIT),
                  isolation={kind: os.readlink('/proc/self/ns/' + kind) for kind in ('net', 'ipc', 'mnt')},
                  unowned_ap_before=json_identity(828), children={}, pauses=[])
    print('Experimental evidence: ' + str(output), flush=True)
    children, workers = [], {}
    probe = None
    started = time.monotonic()
    implementation = ['tools/probe_joint_clock.py', 'tools/run-joint-clock-probe.sh',
                      'Simulator/wksim_core/model.py', 'Simulator/wksim_core/model.cpp',
                      'Simulator/wksim_core/ap_json.py', 'Simulator/wksim_core/px4_mavlink.py',
                      'Simulator/wksim_core/px4-rc.mavlink', 'Simulator/wksim_core/arducopter-quad-x.parm',
                      'Simulator/wksim_runtime/runtime.py', 'Simulator/wksim_runtime/preflight.py',
                      'Simulator/wksim_runtime/arducopter-telemetry.parm']
    if native_clocks:
        implementation.append('tools/joint_clock_observer.py')
    implementation.append('tools/ap_clock_candidate.py')
    if scene_clock:
        implementation += ['Simulator/wksim_core/worker.py', 'Simulator/wksim_runtime/scene_clock.py',
                           'tools/scene_clock_observer.py']
    result['implementation_sha256'] = {path: digest(REPO / path) for path in implementation}
    result['source_snapshots'] = {path: 'source__' + path.replace('/', '__') + '.txt' for path in implementation}
    for source, target in result['source_snapshots'].items():
        (output / target).write_bytes((REPO / source).read_bytes())
    (output / 'probe-start.json').write_text(json.dumps(result, indent=2) + '\n')
    try:
        library = build_model()
        result['model_build'] = json.loads(library.with_name('build.json').read_text())
        configs = {name: load_config(REPO / f'Simulator/wksim_runtime/examples/{name}-session.json')
                   for name in ('px4', 'arducopter')}
        for name, config in configs.items():
            config['model_library'] = str(library)
            if name == 'arducopter':
                config, admission = admit(config, ap_build_manifest, ap_build_sha256)
                configs[name] = config
                if ap_build_manifest:
                    (output / 'ap-build-manifest.json').write_bytes(Path(ap_build_manifest).read_bytes())
            else:
                admission = preflight(config)
            (output / (name + '-preflight.json')).write_text(json.dumps(admission, indent=2) + '\n')
            if not admission['ok']:
                raise RuntimeError(f'{name} fixed candidate admission failed: {admission["reasons"]}')

        def launch(name, argv, directory, env=None, worker=False):
            log = (output / (name + '.log')).open('x')
            child = subprocess.Popen(argv, cwd=directory, env=env,
                                     stdin=subprocess.PIPE if worker else subprocess.DEVNULL,
                                     stdout=subprocess.PIPE if worker else log, stderr=log,
                                     text=True, bufsize=1, start_new_session=True)
            children.append((name, child, log))
            result['children'][name] = dict(identity=json_identity(child.pid), argv=argv,
                                            cwd=str(directory), environment_overrides={})
            return child

        with ExitStack() as stack:
            logs = {name: stack.enter_context((output / (name + '.jsonl')).open('x', buffering=1))
                    for name in ('wire', 'telemetry', 'telemetry-wire', 'steps', 'barriers', 'native-clock', 'scene-clock')}
            probe = WireProbe(stack, logs, children)
            if native_clocks:
                from joint_clock_observer import NativeClockObserver
                probe.native = NativeClockObserver(probe)
                result['ros_nodes_started'] += 1
                stack.callback(probe.native.close)
            if scene_clock:
                from Simulator.wksim_runtime.scene_clock import SceneClock
                from scene_clock_observer import SceneClockObservation
                probe.authority = SceneClock(result['run_epoch'])
                if retired_epoch:
                    old_request = dict(version=1, epoch=retired_epoch, request_id=1, action='stop')
                    before = probe.authority.snapshot()
                    try:
                        probe.authority.request(old_request)
                    except ValueError:
                        result['retired_request_rejected'] = probe.authority.snapshot() == before
                    else:
                        raise RuntimeError('Retired scene request changed the new epoch')
                probe.scene_observer = SceneClockObservation(probe, probe.authority)
                stack.callback(probe.scene_observer.close)
                result['ros_nodes_started'] += 2
                result['initial_authority'] = probe.authority.snapshot()
            for name in configs:
                directory = scratch / name
                directory.mkdir()
                if name == 'arducopter':
                    (directory / 'dds.parm').write_text('DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
                worker_argv = ([sys.executable, '-B', '-m', 'Simulator.wksim_core.worker',
                    '--library', str(library), '--trace', str(output / (name + '-truth.jsonl')),
                    '--epoch', result['run_epoch']] if scene_clock else [sys.executable, str(Path(__file__).resolve()),
                    '--worker-library', str(library), '--worker-trace', str(output / (name + '-truth.jsonl'))])
                workers[name] = launch(name + '-model', worker_argv, directory, worker=True)
                spec = launch_spec(configs[name], directory, library)
                if name == 'arducopter':
                    # Read-only telemetry rates; no extra MAVLink writes or health overrides.
                    index = spec['fc'].index('--defaults') + 1
                    defaults = spec['fc'][index].split(',')
                    defaults.insert(-1, str(REPO / 'Simulator/wksim_runtime/arducopter-telemetry.parm'))
                    spec['fc'][index] = ','.join(defaults)
                (output / (name + '-launch.json')).write_text(json.dumps(spec, indent=2) + '\n')
                env = dict(os.environ, **spec['fc_environment'])
                if native_clocks:
                    launch(name + '-agent', spec['agent'], directory)
                    result['agents_started'] += 1
                launch(name + '-fc', spec['fc'], directory, env=env)
                result['children'][name + '-fc']['environment_overrides'] = spec['fc_environment']
            (output / 'children-start.json').write_text(json.dumps(result['children'], indent=2) + '\n')
            probe.connect()
            result['physics_peers'] = dict(ap=list(probe.peer), px4=list(probe.connection.getpeername()))
            while probe.tick < PRE_TICKS:
                probe.advance(workers)
            if probe.last_px_time != probe.tick * 1000:
                raise RuntimeError('No strict PX4 barrier at pause entry')
            if probe.native and not probe.native.ready():
                raise RuntimeError('Native clock/status observations not ready at the fixed pause tick')
            for name in configs:
                if name + '/HEARTBEAT' not in probe.latest or name + '/ATTITUDE' not in probe.latest:
                    raise RuntimeError('Missing read-only FC ground/clock telemetry: ' + name)
            probe.phase = 'paused-before-single-step'
            print('Both models reached tick 8000; pause, single macro-step, pause', flush=True)
            result['pauses'].append(probe.pause(workers))
            probe.phase = 'single-macro-step'
            if scene_clock:
                probe.scene_action('step')
            for _ in range(MACRO_TICKS):
                probe.advance(workers)
            result['single_step'] = probe.snapshot(workers)
            probe.phase = 'paused-after-single-step'
            result['pauses'].append(probe.pause(workers))
            probe.phase = 'resumed'
            if scene_clock:
                probe.scene_action('resume')
            for _ in range(POST_TICKS):
                probe.advance(workers)
            result['final'] = probe.snapshot(workers)
            result['telemetry_counts'] = probe.counts
            if probe.native:
                result['native_clock_observer'] = probe.native.report()
            if scene_clock:
                probe.scene_observer.at_boundary()
                result['scene_clock_observer'] = probe.scene_observer.report()
                probe.scene_action('stop')
                result['stopped_authority'] = probe.authority.snapshot()
            if require_aligned_clocks:
                from joint_clock_observer import audit_native_clock
                result['aligned_clock_check'] = audit_native_clock(output, result)
                if any(clock['off_millisecond_grid'] for clock in result['aligned_clock_check']['clocks'].values()):
                    raise RuntimeError('Actual native AP/PX4 timestamps are not on the authoritative 1ms grid')
            result['status'] = 'pass'
            for worker in workers.values():
                worker.stdin.close()
                worker.wait(timeout=3)
                if worker.returncode != 0:
                    raise RuntimeError('Model worker did not exit cleanly')
    except Exception as error:
        if probe is not None and probe.authority is not None:
            probe.authority.fault(str(error))
            result['faulted_authority'] = probe.authority.snapshot()
        result['status'], result['error'] = 'failed', repr(error)
        result['traceback'] = traceback.format_exc()
        print('Ground probe failed: ' + repr(error), flush=True)
    finally:
        result['cleanup_errors'] = stop_children(children)
        for name, child, _ in children:
            result['children'][name]['returncode'] = child.returncode
            result['children'][name]['remaining_group_members'] = group_members(child.pid)
        if ap_build_manifest and result['children'].get('arducopter-fc', {}).get('returncode') != 0:
            result['status'] = 'failed'
            result['stop_error'] = 'Independent AP candidate did not exit normally after sensors stopped'
        result['unowned_ap_after'] = json_identity(828)
        result['implementation_unchanged'] = result['implementation_sha256'] == {
            path: digest(REPO / path) for path in implementation}
        if (result['cleanup_errors'] or any(value['remaining_group_members'] for value in result['children'].values())
                or result['unowned_ap_before'] != result['unowned_ap_after'] or not result['implementation_unchanged']):
            result['status'] = 'failed'
        result['wall_seconds'] = time.monotonic() - started
        result['evidence_sha256'] = {path.name: digest(path) for path in output.iterdir() if path.is_file()}
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(encoded({key: result[key] for key in ('status', 'result_dir', 'wall_seconds')}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-library', type=Path)
    parser.add_argument('--worker-trace', type=Path)
    parser.add_argument('--native-clocks', action='store_true')
    parser.add_argument('--ap-build-manifest')
    parser.add_argument('--ap-build-sha256')
    parser.add_argument('--require-aligned-clocks', action='store_true', help='Fail unless actual AP and PX4 clock samples are on the authority grid')
    parser.add_argument('--scene-clock', action='store_true', help='Use epoch-fenced core workers, shared authority and a real ROS /clock consumer')
    parser.add_argument('--cold-reset-once', action='store_true', help='After complete owned-process retirement, create a new scene epoch and run again')
    arguments = parser.parse_args()
    if arguments.require_aligned_clocks and not arguments.native_clocks:
        parser.error('--require-aligned-clocks requires --native-clocks')
    if arguments.scene_clock and not (arguments.native_clocks and arguments.ap_build_manifest and arguments.require_aligned_clocks):
        parser.error('--scene-clock requires native clocks, explicit AP build, and strict alignment')
    if arguments.cold_reset_once and not arguments.scene_clock:
        parser.error('--cold-reset-once requires --scene-clock')
    if arguments.worker_library:
        if not arguments.worker_trace:
            parser.error('--worker-trace is required with --worker-library')
        model_worker(arguments.worker_library, arguments.worker_trace)
    else:
        if arguments.worker_trace:
            parser.error('--worker-library is required with --worker-trace')
        first = main(arguments.native_clocks, arguments.ap_build_manifest,
                     arguments.ap_build_sha256, arguments.require_aligned_clocks, arguments.scene_clock)
        if arguments.cold_reset_once and first['status'] == 'pass':
            # main() returns only after all owned groups are proven absent. No
            # live model/FC/Agent/ROS context is reused for the new epoch.
            second = main(arguments.native_clocks, arguments.ap_build_manifest,
                          arguments.ap_build_sha256, arguments.require_aligned_clocks, True, first['run_epoch'])
            reset = dict(first=first['result_dir'], second=second['result_dir'],
                         first_epoch=first['run_epoch'], second_epoch=second['run_epoch'],
                         status=second['status'], scope='full owned process retirement and cold construction; not task replay acceptance')
            Path(second['result_dir'], 'cold-reset.json').write_text(json.dumps(reset, indent=2)+'\n')
            raise SystemExit(0 if second['status'] == 'pass' else 1)
        raise SystemExit(0 if first['status'] == 'pass' else 1)
