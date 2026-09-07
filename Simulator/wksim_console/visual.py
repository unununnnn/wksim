"""Owned Windows UE view; no flight commands and no recorded-state playback.

Only Popen handles created here are termination authorities. In particular an
exited UE launcher is never replaced by a process found by name/PID. Descendant
cleanup is deliberately reported as unverified, not as successful tree reaping.
"""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import threading
import time
import uuid

from Simulator.ue55.bridge import actor_errors
from Simulator.wksim_core.state_stream import MAX_AGE, identity, validate

REPO = Path(__file__).resolve().parents[2]
ENGINE = Path('E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe')
PORT = 19060
TAIL_BYTES = 65536
STARTUP_TIMEOUT = 60
# Coexist with an editor on the local 8 GB GPU. No warning suppression; this
# is display scalability only, not physics or camera-sensor calibration.
DISPLAY_COMMANDS = ('t.IdleWhenNotForeground 0,t.MaxFPS 30,sg.ShadowQuality 1,'
                    'sg.GlobalIlluminationQuality 1,sg.ReflectionQuality 1,sg.TextureQuality 1')
# Pinned to tools/validate_product_visual.py's actual-Actor acceptance gate.
ACTOR_LIMITS = dict(position_cm=2e-4, quaternion_l2=2e-6, sim_time_s=1e-8)

# Executed by WSL python with an argument, never a shell interpolation. The
# relay repeats these checks before binding and owns/unlinks only its inode.
_PREPARE_SOCKET = """import os, pathlib, stat, subprocess, sys
# WSL can return an exec process before systemd finishes its boot-time /tmp clear.
# Wait before creating/binding the admitted socket, without changing host services.
if pathlib.Path("/run/systemd/system").is_dir():
    state = subprocess.run(["systemctl", "is-system-running", "--wait"], capture_output=True, text=True, timeout=30)
    if state.stdout.strip() not in ("running", "degraded"):
        raise RuntimeError("WSL host initialization did not settle: " + state.stdout.strip())
p = pathlib.Path(sys.argv[1])
assert str(p) == sys.argv[1] and p.name == 'state.sock' and p.parent.parent == pathlib.Path('/tmp')
try:
    p.parent.mkdir(mode=0o700)
except FileExistsError:
    pass
s = p.parent.lstat()
assert stat.S_ISDIR(s.st_mode) and s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700
assert p.parent.resolve() == p.parent and not p.exists() and not p.is_symlink()
"""


def _tail(path):
    try:
        with path.open('rb') as stream:
            size = stream.seek(0, 2)
            stream.seek(max(0, size - TAIL_BYTES))
            data = stream.read(TAIL_BYTES)
        if size > TAIL_BYTES:
            data = data.partition(b'\n')[2]
        return data
    except FileNotFoundError:
        return b''


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _wsl_path(path):
    value = str(path.resolve()).replace('\\', '/')
    if not re.match(r'^[A-Za-z]:/', value):
        raise ValueError('View repository must be on a Windows drive')
    return '/mnt/' + value[0].lower() + value[2:]


def _probe_port():
    # Do not set REUSEADDR: another program owns the resource even if it is UE.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(('0.0.0.0', PORT))


class _Cancelled(Exception):
    pass


class View:
    _resource = threading.Lock()

    def __init__(self, directory, run_id, state_socket, repo=REPO, *, joint_instance=None, build_manifest=None, rgb_config=None, rgb_fixture_case=None):
        self.directory = Path(directory).resolve()
        self.repo = Path(repo).resolve()
        self.run_id, self.state_socket = run_id, state_socket
        self.joint_instance=joint_instance
        self.rgb_config=None
        if rgb_fixture_case is not None and (type(rgb_fixture_case) is not int or not 0<=rgb_fixture_case<=3 or rgb_config is None):
            raise ValueError('RGB calibration fixture needs a configured camera and case 0..3')
        self.rgb_fixture_case=rgb_fixture_case
        if rgb_config is not None:
            from Simulator.ue55.rgb import config
            if joint_instance is None:raise ValueError('RGB requires an authoritative joint step source')
            self.rgb_config=config(rgb_config)
        self.display_fps=15 if joint_instance is not None else 30
        self._view_request_sequence=0
        self._actor_cursor=None
        self._manifest=Path(build_manifest) if build_manifest is not None else self.repo/'Simulator/ue55/state-build-manifest.json'
        self._mutex = threading.RLock()
        self._cancel = threading.Event()
        self._thread = None
        self._owns_resource = False
        self._children = []
        self._state, self._error = 'stopped', None
        self._ready = False
        self._started = False
        self._attempt = uuid.uuid4().hex
        self.rgb_stream_id = self._attempt
        self.rgb_enabled = rgb_config is not None
        self._root = self.directory / ('view-' + self._attempt)
        self.readback_path = self._root / 'actor.jsonl'
        self.frames_directory = self._root / 'frames'
        self.rgb_directory = self._root / 'rgb'
        self._latest = None
        self._cleanup_pending = False

    def _preflight(self):
        identity(self.run_id, 1)
        if self.joint_instance is not None:
            from Simulator.wksim_core.joint_state_stream import hex_identity
            if not hex_identity(self.joint_instance):raise ValueError('Invalid joint manager instance')
        if not isinstance(self.state_socket, str):
            raise ValueError('state_socket must be a Linux pathname')
        path = PurePosixPath(self.state_socket)
        if (str(path) != self.state_socket or path.name != 'state.sock' or
                path.parent.parent != PurePosixPath('/tmp') or
                not re.fullmatch(r'[A-Za-z0-9_-]+', path.parent.name) or
                self.run_id not in path.parent.name or len(self.state_socket.encode()) > 107):
            raise ValueError('Socket must be /tmp/<private directory containing run_id>/state.sock')
        if os.name != 'nt':
            raise OSError('UE view is available only on Windows')
        build = json.loads(self._manifest.read_text(encoding='utf-8'))
        if build.get('build_exit_code') != 0 or not build.get('build_inputs'):
            raise ValueError('UE build manifest is incomplete or failed')
        if not ENGINE.is_file() or not Path(build['project']).is_file():
            raise FileNotFoundError('Pinned UnrealEditor/project is unavailable')
        if _sha(build['binary']) != build['binary_sha256']:
            raise ValueError('UE DLL hash differs from build manifest')
        source_root = (self.repo / 'Simulator/ue55').resolve()
        stage_root = Path(build['project']).resolve().parent
        assets = build.get('asset_inputs', [])
        if build.get('visual_model') == 'prometheus_p450_visual_v1':
            expected = {'p450-visual-manifest.json'} | {'Content/Wksim/P450/' + name for name in (
                'M_P450_Body.uasset', 'M_P450_Rotor.uasset', 'SM_p450.uasset',
                'SM_p450_ccw.uasset', 'SM_p450_cw.uasset', 'UPSTREAM_LICENSE.txt')}
            if len(assets) != len(expected) or {a['path'] for a in assets} != expected:
                raise ValueError('P450 asset manifest is incomplete')
        for item in build['build_inputs'] + assets:
            relative = Path(item['path'])
            for root, key in ((source_root, 'source_sha256'), (stage_root, 'staging_sha256')):
                candidate = (root / relative).resolve()
                if not candidate.is_relative_to(root) or _sha(candidate) != item[key]:
                    raise ValueError('UE build input hash mismatch: ' + item['path'])
        self._wsl_repo = _wsl_path(self.repo)
        return build

    def _relay_record(self):
        try:
            value = json.loads(_tail(self._root / 'relay.json'))
            if (isinstance(value, dict) and type(value.get('pid')) is int and
                    isinstance(value.get('argv'), list)):
                return value
        except (ValueError, OSError, RecursionError):
            pass
        return None

    def _release_reaped_resource(self):
        if not self._owns_resource:
            return
        if any(row['process'].poll() is None for row in self._children):
            self._cleanup_pending = True
            return
        if any(row['name'] == 'bridge' for row in self._children):
            relay = self._relay_record()
            if relay is None or type(relay.get('returncode')) is not int:
                self._cleanup_pending = True
                return
        View._resource.release()
        self._owns_resource = False

    def _snapshot(self):
        return dict(state=self._state, error=self._error, run_id=self.run_id,
                    joint_instance=self.joint_instance,
                    transport_ready=self._ready,
                    display_fps=self.display_fps,
                    state_socket=self.state_socket,
                    pids={row['name']: row['process'].pid for row in self._children},
                    processes=[dict(name=row['name'], argv=row['argv'], pid=row['process'].pid,
                                    returncode=row['process'].poll()) for row in self._children],
                    readback_path=str(self.readback_path), frames_directory=str(self.frames_directory),
                    rgb_directory=str(self.rgb_directory), rgb_config=self.rgb_config,
                    rgb_stream_id=self.rgb_stream_id,
                    rgb_enabled=self.rgb_enabled,
                    rgb_fixture_case=self.rgb_fixture_case, rgb_fixture_manifest=str(self._root/'rgb-fixture.json'),
                    latest_actor=self._latest, cleanup_pending=self._cleanup_pending,
                    relay=self._relay_record(), resource_held=self._owns_resource,
                    cleanup_scope='Created Popen handles only; UE wrapper descendants and bridge-owned WSL relay reaping unverified')

    def _persist(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / ('view-' + self._attempt + '.tmp')
        temporary.write_text(json.dumps(self._snapshot(), ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
        deadline=time.monotonic()+.25
        while True:
            try:
                os.replace(temporary,self.directory/'view.json')
                break
            except PermissionError:
                # Windows readers can briefly hold a handle without DELETE
                # sharing. The viewer may wait; physics is a separate process.
                if time.monotonic()>=deadline:raise
                time.sleep(.01)

    def start(self):
        with self._mutex:
            if self._started:
                return self._snapshot()
            self._started = True
            self._state = 'starting'
            self._persist()
            self._thread = threading.Thread(target=self._work, name='wksim-view-' + self._attempt, daemon=True)
            self._thread.start()
            return self._snapshot()

    def _launch(self, name, argv, visible=False):
        # Launch and registration share the close lock. stop cannot miss a child
        # between CreateProcess returning and its handle becoming owned.
        with self._mutex:
            if self._cancel.is_set():
                raise _Cancelled()
            # UE owns -abslog=ue.log. Pre-creating it as stdout makes Unreal
            # choose ue_2.log and hides its actual readiness from this observer.
            log = (self._root / (name + '.stdout.log')).open('xb')
            try:
                child = subprocess.Popen(argv, cwd=self.repo, stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.PIPE if name == 'bridge' else subprocess.DEVNULL,
                                         creationflags=0 if visible else getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except BaseException:
                log.close()
                raise
            self._children.append(dict(name=name, argv=list(argv), process=child, log=log))
            self._persist()
            return child

    def _work(self):
        terminal = 'stopped'
        try:
            build = self._preflight()
            if self._cancel.is_set():
                raise _Cancelled()
            if not View._resource.acquire(blocking=False):
                raise RuntimeError('UE port 19060 busy: another console view owns it')
            self._owns_resource = True
            try:
                _probe_port()
            except OSError as error:
                raise RuntimeError('UE port 19060 busy; refusing to take over') from error
            self.frames_directory.mkdir(parents=True, exist_ok=False)
            # Recheck immediately before UE creation, after potentially slow WSL.
            _probe_port()
            vehicle='joint' if self.joint_instance is not None else '1'
            rgb_args=[]
            if self.rgb_config is not None:
                rgb_path=self._root/'rgb-config.json'
                rgb_path.write_text(json.dumps(dict(self.rgb_config,output_directory=str(self.rgb_directory),
                                                    stream_id=self.rgb_stream_id),allow_nan=False)+'\n',encoding='utf-8')
                rgb_args=['-WksimRgbConfig='+str(rgb_path)]
                if self.rgb_fixture_case is not None:
                    rgb_args+=['-WksimRgbFixtureCase='+str(self.rgb_fixture_case),
                               '-WksimRgbFixtureManifest='+str(self._root/'rgb-fixture.json')]
            ue = self._launch('ue', [str(ENGINE), build['project'],
                '/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
                '-game', '-windowed', '-ResX=1280', '-ResY=720', '-NoSound', '-NoSplash', '-unattended',
                '-ExecCmds=' + DISPLAY_COMMANDS.replace('t.MaxFPS 30','t.MaxFPS '+str(self.display_fps)), '-WksimVehicle='+vehicle,
                '-WksimRunId=' + self.run_id, '-WksimPort=' + str(PORT),
                '-abslog=' + str(self._root / 'ue.log'), '-WksimCaptureDir=' + str(self.frames_directory),
                *(['-WksimInstance='+self.joint_instance] if self.joint_instance is not None else []), *rgb_args], visible=True)
            deadline = time.monotonic() + STARTUP_TIMEOUT
            marker = ('WKSIM_READY run=' + self.run_id + ' vehicle='+vehicle+' port=19060 ').encode()
            while marker not in _tail(self._root / 'ue.log'):
                if self._cancel.wait(.05):
                    raise _Cancelled()
                if ue.poll() is not None:
                    self._cleanup_pending = True
                    raise RuntimeError('UE launcher exited; actual wrapper-child ownership cannot be guaranteed')
                if time.monotonic() > deadline:
                    raise TimeoutError('UE_READY timed out')
            if ue.poll() is not None:
                self._cleanup_pending = True
                raise RuntimeError('UE launcher exited at readiness; descendant identity unverified')
            # Exact validated target; existing private directories may be reused
            # only after their owner/mode and absent socket are checked.
            created = self._launch('socket-directory', ['wsl.exe', '-d', 'Ubuntu-22.04', '--exec',
                                   'python3', '-c', _PREPARE_SOCKET, self.state_socket])
            deadline = time.monotonic() + 40
            while created.poll() is None:
                if self._cancel.wait(.05):
                    raise _Cancelled()
                if time.monotonic() > deadline:
                    raise TimeoutError('Private socket directory creation timed out')
            if created.returncode:
                raise RuntimeError('Private socket directory unsafe or socket already exists; refusing reuse')
            bridge = self._launch('bridge', [sys.executable, '-X', 'utf8', '-m', 'Simulator.wksim_console.visual',
                '--bridge-helper', '--relay-record', str(self._root / 'relay.json'),
                '--wsl-repo', self._wsl_repo, '--state-socket', self.state_socket, '--run-id', self.run_id,
                '--vehicle-id', '1', '--port', str(PORT), '--readback', str(self.readback_path),
                *(['--instance-id',self.joint_instance] if self.joint_instance is not None else [])])
            with self._mutex:
                self._ready = True
            while not self._cancel.wait(.1):
                if ue.poll() is not None or bridge.poll() is not None:
                    raise RuntimeError('Owned UE or product bridge exited')
                self.poll()
        except _Cancelled:
            pass
        except Exception as error:
            terminal = 'unavailable' if isinstance(error, (FileNotFoundError, OSError)) else 'failed'
            with self._mutex:
                self._error = str(error)
        finally:
            with self._mutex:
                for row in reversed(self._children):
                    child = row['process']
                    try:
                        if child.poll() is None:
                            if row['name'] == 'bridge' and child.stdin:
                                try:
                                    child.stdin.write(b'!')
                                    child.stdin.flush()
                                    child.stdin.close()
                                    child.wait(timeout=4)
                                except (OSError, ValueError, subprocess.TimeoutExpired):
                                    pass
                            if child.poll() is None:
                                child.terminate()
                            try:
                                child.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                child.kill()
                                child.wait(timeout=3)
                    except Exception as error:
                        self._cleanup_pending = True
                        self._error = (self._error or '') + '; cleanup: ' + str(error)
                    finally:
                        row['log'].close()
                if any(row['name'] in ('ue', 'bridge') for row in self._children):
                    # EOF is the existing bridge relay cleanup protocol, but a
                    # launcher exit does not prove the Linux child was reaped.
                    self._cleanup_pending = True
                self._state = 'failed' if self._state == 'failed' else terminal
                self._release_reaped_resource()
                self._persist()

    def _actor(self):
        for raw in reversed(_tail(self.readback_path).split(b'\n')[:-1]):
            try:
                row = json.loads(raw)
                packet, ack = row['packet'], row['ack']
                # Validate original source clock in its own domain. Windows
                # freshness is the conservative bound written by product_bridge.
                if self.joint_instance is not None:
                    from Simulator.ue55.joint_bridge import joint_actor_errors
                    if packet.get('run_id')!=self.run_id or packet.get('instance_id')!=self.joint_instance:
                        continue
                    errors=joint_actor_errors(packet,ack)
                    error_groups=list(errors.values())
                    cursor=(packet['generation'],packet['epoch'],packet['sequence'])
                    if self._actor_cursor is not None and (cursor[0]<self._actor_cursor[0]
                            or cursor[0]==self._actor_cursor[0] and
                               (cursor[1]!=self._actor_cursor[1] or cursor[2]<self._actor_cursor[2])):
                        continue
                else:
                    validate(packet, self.run_id, 1, now=packet['source_wall_time_s'])
                    errors=actor_errors(packet,ack)
                    error_groups=[errors]
                    cursor=packet['sequence']
                    if self._actor_cursor is not None and cursor<self._actor_cursor:continue
                # The pinned UE ACK omits these fields. Its correlated packet
                # supplies vehicle identity and the clock below supplies age.
                # If an ACK does supply them, never ignore disagreement.
                if ('stale' in ack and not (ack['stale'] is False or
                        type(ack['stale']) is int and ack['stale'] == 0)):
                    return None, False
                for key in ('vehicle_id', 'vehicleID'):
                    if key in ack and (type(ack[key]) is not int or ack[key] != 1):
                        return None, False
                if any(not math.isfinite(group[key]) or group[key] > limit
                       for group in error_groups for key,limit in ACTOR_LIMITS.items()):
                    # Do not fall back to an older good ACK and hide the latest
                    # correlated Actor mismatch as a currently live view.
                    return None, False
                stamp, bound = packet['display_wall_time_s'], packet['transport_age_bound_s']
                if (packet.get('display_clock') != 'windows_utc_bound' or
                        any(type(v) not in (int, float) or not math.isfinite(v) for v in (stamp, bound)) or
                        not 0 <= bound <= MAX_AGE):
                    continue
                age = time.time() - stamp
                peers_fresh=self.joint_instance is None or all(not item['stale'] for item in ack['observed_vehicles'])
                self._actor_cursor=cursor
                return dict(ack=ack, packet=packet, age_s=age, errors=errors,
                            clock='windows_utc_bound'), -0.25 <= age <= MAX_AGE and peers_fresh
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
                continue
        return None, False

    def poll(self):
        with self._mutex:
            if self._thread and not self._thread.is_alive():
                self._release_reaped_resource()
            if self._ready and self._state in ('starting', 'live', 'stale'):
                self._latest, fresh = self._actor()
                alive = all(row['process'].poll() is None for row in self._children if row['name'] in ('ue', 'bridge'))
                if not alive:
                    self._state, self._error = 'failed', 'Owned UE or product bridge exited'
                else:
                    self._state = 'live' if fresh else 'stale'
            self._persist()
            return self._snapshot()


    def select_vehicle(self,vehicle_id):
        """Select the camera only; this endpoint has no route to flight control."""
        with self._mutex:
            if self.joint_instance is None or type(vehicle_id) is not int or vehicle_id not in (1,2):
                raise ValueError('Joint camera selection requires vehicle 1 or 2')
            if not self._ready or self._latest is None:raise ValueError('No current joint Actor identity')
            packet=self._latest['packet']
            self._view_request_sequence=max(self._view_request_sequence+1,int(time.monotonic()*1000))
            request=dict(version=3,kind='joint_view_select',run_id=self.run_id,instance_id=self.joint_instance,
                         epoch=packet['epoch'],generation=packet['generation'],request_sequence=self._view_request_sequence,
                         vehicle_id=vehicle_id)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as peer:
                peer.bind(('127.0.0.1',0));peer.settimeout(.75)
                peer.sendto(json.dumps(request,separators=(',',':')).encode(),('127.0.0.1',PORT))
                raw,sender=peer.recvfrom(8193)
            response=json.loads(raw)
            if sender!=('127.0.0.1',PORT) or len(raw)>8192 or response!=dict(request,kind='joint_view_selected'):
                raise ValueError('Uncorrelated camera selection response')
            record=dict(request=request,response=response,observed_unix_s=time.time())
            with (self._root/'view-actions.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(record,allow_nan=False)+'\n')
            return record

    def set_rgb_enabled(self, enabled):
        """Accept capture stop/start; actual new PNGs establish completion."""
        with self._mutex:
            if self.rgb_config is None or type(enabled) is not bool or enabled==self.rgb_enabled:
                raise ValueError('RGB needs an explicit state change on a configured camera')
            self.poll()
            if not self._ready or self._latest is None or self._state!='live':
                raise ValueError('No current joint Actor identity')
            packet=self._latest['packet']
            self._view_request_sequence=max(self._view_request_sequence+1,int(time.monotonic()*1000))
            new_stream=uuid.uuid4().hex if enabled else self.rgb_stream_id
            request=dict(version=3,kind='rgb_stream_control',run_id=self.run_id,instance_id=self.joint_instance,
                         epoch=packet['epoch'],generation=packet['generation'],request_sequence=self._view_request_sequence,
                         stream_id=self.rgb_stream_id,enabled=enabled,next_stream_id=new_stream)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as peer:
                peer.bind(('127.0.0.1',0));peer.settimeout(.75)
                peer.sendto(json.dumps(request,separators=(',',':')).encode(),('127.0.0.1',PORT))
                raw,sender=peer.recvfrom(8193)
            response=json.loads(raw)
            if sender!=('127.0.0.1',PORT) or len(raw)>8192 or response!=dict(request,kind='rgb_stream_controlled'):
                raise ValueError('Uncorrelated RGB control response')
            self.rgb_stream_id,self.rgb_enabled=new_stream,enabled
            record=dict(request=request,response=response,observed_unix_s=time.time(),
                        completion='capture state accepted; new images require independent observation')
            with (self._root/'rgb-actions.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(record,allow_nan=False)+'\n')
            self._persist()
            return record

    def stop(self):
        self._cancel.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=15)
        with self._mutex:
            if thread and thread.is_alive():
                self._cleanup_pending = True
                self._error = 'View startup/cleanup still pending'
            elif not self._started:
                self._state = 'stopped'
            if not thread or not thread.is_alive():
                self._release_reaped_resource()
            self._persist()
            return self._snapshot()


def _bridge_helper():
    """Run the unchanged product bridge with observable, gracefully closed pipes.

    This instrumentation exists only in the isolated helper interpreter. It
    never replaces the bridge's packet path or sends commands to physics.
    """
    import argparse
    from Simulator.ue55 import product_bridge

    parser = argparse.ArgumentParser()
    parser.add_argument('--bridge-helper', action='store_true')
    parser.add_argument('--relay-record', required=True)
    parser.add_argument('--wsl-repo', required=True)
    parser.add_argument('--state-socket', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--vehicle-id', type=int, default=1)
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--readback', required=True)
    parser.add_argument('--instance-id')
    args = parser.parse_args()
    record = Path(args.relay_record)
    guard = threading.RLock()
    closing = threading.Event()
    children = []
    original = subprocess.Popen

    class RelayProcess(original):
        def __init__(self, argv, **kwargs):
            with guard:
                if closing.is_set():
                    raise _Cancelled()
                super().__init__(argv, **kwargs)
                self.saved_argv = list(argv)
                children.append(self)
                self.save()

        def save(self):
            with guard:
                temporary = record.with_suffix('.tmp')
                temporary.write_text(json.dumps(dict(argv=self.saved_argv, pid=self.pid,
                                          returncode=self.returncode)) + '\n', encoding='utf-8')
                os.replace(temporary, record)

        def wait(self, timeout=4):
            try:
                # Popen.__exit__ otherwise waits forever after bridge teardown.
                return super().wait(timeout=4 if timeout is None else timeout)
            finally:
                self.save()

    def close_on_request():
        sys.stdin.buffer.read(1)  # explicit close or owning console pipe EOF
        closing.set()
        with guard:
            for child in children:
                if child.stdin:
                    child.stdin.close()  # relay's existing scoped EOF protocol

    subprocess.Popen = RelayProcess
    threading.Thread(target=close_on_request, daemon=True).start()
    try:
        product_bridge.bridge(args.wsl_repo, args.state_socket, args.run_id,
                              args.vehicle_id, args.port, args.readback,
                              **({'instance_id':args.instance_id} if args.instance_id is not None else {}))
    except (ConnectionError, ValueError, OSError, _Cancelled):
        if not closing.is_set():
            raise
    finally:
        try:
            for child in children:
                try:
                    if child.stdin:
                        child.stdin.close()
                    if child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait(timeout=3)
                finally:
                    child.save()
        finally:
            subprocess.Popen = original


if __name__ == '__main__':
    _bridge_helper()
