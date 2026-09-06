"""Exact symptom oracle: ground AP alive five seconds after signal => exit 1.

Exit 0 means observed exit within bound, not production-safe shutdown. Exit 2
means invalid/incomplete experiment. No control commands, agents or hardware.
"""
import argparse
from contextlib import ExitStack
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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_core.model import Model
from Simulator.wksim_core.ap_json import decode_servos, sensor_message
from Simulator.wksim_runtime.config import load_config
from Simulator.wksim_runtime.isolation import check_isolation
from Simulator.wksim_runtime.preflight import preflight
from Simulator.wksim_runtime.runtime import digest, launch_spec, AP_SHA256
from ap_clock_candidate import admit


def identity(pid):
    root = Path('/proc') / str(pid)
    try:
        fields = (root / 'stat').read_text().rsplit(')', 1)[1].split()
        return dict(pid=pid, pgid=int(fields[2]), start_ticks=int(fields[19]),
                    argv=(root / 'cmdline').read_bytes().decode(errors='replace').split('\0')[:-1])
    except FileNotFoundError:
        return None


def audit():
    """Offline evidence/source capture. Never launch a flight controller."""
    output = Path(tempfile.mkdtemp(prefix='ap-shutdown-audit-', dir=REPO / 'validation'))
    source = Path('/root/wksim-ap-dds-yaw-state-4Wr27s/src')
    paths = ['libraries/AP_HAL_SITL/HAL_SITL_Class.cpp', 'libraries/AP_HAL_SITL/Scheduler.cpp',
             'libraries/AP_HAL_SITL/Scheduler.h', 'libraries/AP_HAL_SITL/SITL_State.cpp',
             'libraries/SITL/SIM_JSON.cpp', 'libraries/AP_HAL/utility/Socket.cpp']
    manifest = dict(sources={}, runs={})
    for name in paths:
        raw = (source / name).read_bytes()
        target = output / Path(name).name
        target.write_bytes(raw)
        committed = subprocess.check_output(['git', '-C', str(source), 'show',
            '1511f27194f1dcc3728270883047bdf022b3fd53:' + name])
        manifest['sources'][name] = dict(sha256=digest(target), matches_fixed_commit=raw == committed)
    for directory in sorted((REPO / 'validation').glob('ap-shutdown-*')):
        path = directory / 'result.json'
        if not path.exists():
            continue
        value = json.loads(path.read_text())
        checks = {name: digest(directory / name) == checksum
                  for name, checksum in value['evidence_sha256'].items()}
        row = {k: value.get(k) for k in ('options', 'verdict', 'ground', 'signal_wait_seconds',
               'ticks_after_wait', 'returncode', 'resume', 'error', 'owned_group_remaining', 'wall_seconds')}
        row.update(result_sha256=digest(path), evidence_hashes_match=all(checks.values()),
                   child=value.get('child'), recorded_pid_now=identity(value['child']['pid']) if value.get('child') else None)
        sent, received, heartbeats = [], [], []
        for line in (directory / 'wire.jsonl').read_text().splitlines():
            event = json.loads(line)
            if 'send' in event:
                sensor = json.loads(bytes.fromhex(event['send']))
                assert sensor['no_lockstep'] is False and sensor['no_time_sync'] is False
                assert abs(sensor['timestamp'] - event['tick'] * .001) < 1e-8
                assert abs(event['state'][8]) < .1
                assert event['tick'] == len(sent) + 1
                sent.append(event)
            else:
                frame, rate, pwm, commands = decode_servos(bytes.fromhex(event['receive']))
                assert not any(commands)
                received.append(frame)
        for line in (directory / 'telemetry.jsonl').read_text().splitlines():
            heartbeats.extend(json.loads(line)['heartbeats'])
        assert all(not hb['base_mode'] & 128 for hb in heartbeats)
        if value['verdict'] != 'INVALID':
            assert heartbeats
            first_signal = value['signals'][0]
            assert first_signal['identity'] == value['child']
            assert first_signal['signal'] == 'SIG' + value['options']['signal']
            if value['options']['flow'] == 'stopped':
                if value['verdict'] == 'RED':
                    bound = json.loads((directory / 'after-five-seconds.json').read_text())['wall']
                    assert not any(first_signal['wall'] <= e['wall'] <= bound for e in sent)
                assert value['ticks_after_wait'] == value['ground']['ticks']
        row['wire_checks'] = dict(sensor_packets=len(sent), actuator_packets=len(received),
                                  disarmed_heartbeats=len(heartbeats), ground_and_tick_checks=True)
        if value.get('debugger'):
            row['debugger_pid_now'] = identity(value['debugger']['pid'])
        manifest['runs'][directory.name] = row
        assert all(checks.values()) and row['recorded_pid_now'] is None
        assert row.get('debugger_pid_now') is None
        assert value.get('owned_group_remaining') is False
    manifest['current_tools'] = {name: digest(REPO / 'tools' / name)
                               for name in ('probe_ap_shutdown.py', 'run-ap-shutdown-probe.sh')}
    (output / 'audit.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(audit=str(output), runs=len(manifest['runs']),
                         all_recorded_owned_pids_absent=True)), flush=True)
    return 0


def main(args):
    check_isolation()
    assert os.readlink('/proc/self/ns/mnt') != os.readlink('/proc/1/ns/mnt')
    output = Path(tempfile.mkdtemp(prefix='ap-shutdown-', dir=REPO / 'validation'))
    scratch = Path(tempfile.mkdtemp(prefix='wksim-ap-stop-'))
    result = dict(verdict='INVALID', options=vars(args), scratch=str(scratch),
                  isolation={n: os.readlink('/proc/self/ns/' + n) for n in ('net', 'ipc', 'mnt')},
                  shm_device=os.stat('/dev/shm').st_dev, supervisor=identity(os.getpid()),
                  commands_sent=0, signals=[])
    child = None
    started = time.monotonic()

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2) + '\n')

    def own():
        current = identity(child.pid)
        if current != result['child']:
            raise RuntimeError('Owned AP identity changed; refusing operation')

    def send(sig):
        own()
        result['signals'].append(dict(signal=signal.Signals(sig).name, wall=time.monotonic()-started,
                                      identity=identity(child.pid)))
        save('signals.json', result['signals'])
        os.killpg(child.pid, sig)

    def snapshot(label):
        own()
        data = dict(identity=identity(child.pid), wall=time.monotonic()-started, threads={})
        for entry in (Path('/proc') / str(child.pid) / 'task').iterdir():
            data['threads'][entry.name] = {}
            for name in ('stat', 'status', 'wchan', 'syscall', 'stack'):
                try:
                    data['threads'][entry.name][name] = (entry / name).read_text()
                except OSError as error:
                    data['threads'][entry.name][name] = repr(error)
        save(label + '.json', data)

    print('Evidence: ' + str(output), flush=True)
    try:
        for name in ('probe_ap_shutdown.py', 'run-ap-shutdown-probe.sh', 'ap_clock_candidate.py'):
            (output / name).write_bytes((REPO / 'tools' / name).read_bytes())
        config = load_config(REPO / 'Simulator/wksim_runtime/examples/arducopter-session.json')
        library = Path('/tmp/wksim-model-5swsjm5f/libwksim_model.so')
        config['model_library'] = str(library)
        config, admission = admit(config, args.ap_build_manifest, args.ap_build_sha256)
        save('preflight.json', admission)
        if not admission['ok']:
            raise RuntimeError('Admission failed: ' + repr(admission['reasons']))
        if args.ap_build_manifest:
            (output / 'ap-build-manifest.json').write_bytes(Path(args.ap_build_manifest).read_bytes())
        candidate = Path(config['ap_candidate'])
        result['source_commit'] = subprocess.check_output(['git', '-C', str(candidate / 'src'),
                                                          'rev-parse', 'HEAD'], text=True).strip()
        assert result['source_commit'] == '1511f27194f1dcc3728270883047bdf022b3fd53'
        result['binary_sha256'] = digest(candidate / 'build/sitl/bin/arducopter')
        if not args.ap_build_manifest:
            assert result['binary_sha256'] == AP_SHA256
        (scratch / 'dds.parm').write_text(f'DDS_ENABLE {args.dds}\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n')
        spec = launch_spec(config, scratch, library)
        idx = spec['fc'].index('--defaults') + 1
        defaults = spec['fc'][idx].split(',')
        defaults.insert(-1, str(REPO / 'Simulator/wksim_runtime/arducopter-telemetry.parm'))
        spec['fc'][idx] = ','.join(defaults)
        save('launch.json', spec)
        result['defaults_sha256'] = {p: digest(p) for p in defaults}
        from pymavlink.dialects.v20 import common
        parser = common.MAVLink(None)
        parser.robust_parsing = True
        with ExitStack() as stack:
            wire = stack.enter_context((output / 'wire.jsonl').open('x', buffering=1))
            telelog = stack.enter_context((output / 'telemetry.jsonl').open('x', buffering=1))
            log = stack.enter_context((output / 'ap.log').open('x'))
            sock = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            sock.bind(('127.0.0.1', 19002))
            sock.setblocking(False)
            tele = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            tele.bind(('127.0.0.1', 14660))
            tele.setblocking(False)
            model = stack.enter_context(Model(library))
            child = subprocess.Popen(spec['fc'], cwd=scratch, env=dict(os.environ, **spec['fc_environment']),
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            result['child'] = identity(child.pid)
            assert result['child']['pgid'] == child.pid and child.pid != 828
            save('start.json', result)
            peer, frame, heartbeat, pending = None, None, None, None

            def pump(advance):
                nonlocal peer, frame, heartbeat, pending
                if time.monotonic() - started > 45:
                    raise TimeoutError('45 second total experiment bound')
                ready = select.select([sock, tele], [], [], .002)[0]
                if tele in ready:
                    data = tele.recv(65535)
                    messages = []
                    for msg in parser.parse_buffer(data) or []:
                        if msg.get_type() == 'HEARTBEAT':
                            assert msg.get_srcSystem() == 241 and not msg.base_mode & 128
                            heartbeat = msg.to_dict()
                            messages.append(heartbeat)
                    telelog.write(json.dumps(dict(wall=time.monotonic()-started, raw=data.hex(), heartbeats=messages))+'\n')
                if sock in ready:
                    packet, address = sock.recvfrom(4096)
                    if peer is None:
                        peer = address
                    assert address == peer and address[0] == '127.0.0.1'
                    current, rate, pwm, commands = decode_servos(packet)
                    assert not any(commands), 'Ground-only: nonzero motor command'
                    wire.write(json.dumps(dict(wall=time.monotonic()-started, receive=packet.hex(), tick=model.ticks))+'\n')
                    if current != frame:
                        assert frame is None or current == (frame+1) % 2**32
                        frame = current
                        pending = commands
                if advance and pending is not None:
                    state = model.step(pending)
                    assert abs(state[8]) < .1, 'Not on ground'
                    value = json.loads(sensor_message(state))
                    value.update(no_lockstep=False, no_time_sync=False)
                    packet = ('\n'+json.dumps(value, separators=(',', ':'))+'\n').encode('ascii')
                    sock.sendto(packet, peer)
                    wire.write(json.dumps(dict(wall=time.monotonic()-started, send=packet.hex(), tick=model.ticks, state=state))+'\n')
                    pending = None

            while model.ticks < args.ticks or pending is None:
                if child.poll() is not None:
                    raise RuntimeError('AP exited before ground')
                pump(model.ticks < args.ticks)
            if heartbeat is None:
                raise RuntimeError('No disarmed ground heartbeat at selected tick')
            result['ground'] = dict(ticks=model.ticks, heartbeat=heartbeat, pending_frame=frame,
                                    wall=time.monotonic()-started)
            snapshot('before-signal')
            signal_started = time.monotonic()
            send(getattr(signal, 'SIG' + args.signal))
            while child.poll() is None and time.monotonic()-signal_started < 5:
                pump(args.flow == 'live')
            result['signal_wait_seconds'] = time.monotonic()-signal_started
            result['ticks_after_wait'] = model.ticks
            result['verdict'] = 'RED' if child.poll() is None else 'GREEN'
            result['returncode_at_bound'] = child.poll()
            if child.poll() is None:
                snapshot('after-five-seconds')
                if args.gdb:
                    own()
                    with (output / 'gdb.txt').open('x') as capture:
                        debugger = subprocess.Popen(['gdb', '-q', '-nx', '-batch', '-p', str(child.pid),
                            '-ex', 'set pagination off', '-ex', 'thread apply all bt',
                            '-ex', "x/1ub &'HALSITL::Scheduler::_should_exit'", '-ex', 'detach'],
                            stdout=capture, stderr=subprocess.STDOUT, cwd=scratch, start_new_session=True)
                        result['debugger'] = identity(debugger.pid)
                        save('debugger-start.json', result['debugger'])
                        try:
                            debugger.wait(timeout=10)
                        finally:
                            if debugger.poll() is None:
                                assert identity(debugger.pid) == result['debugger']
                                os.killpg(debugger.pid, signal.SIGKILL)
                                debugger.wait(timeout=5)
                            result['gdb_returncode'] = debugger.returncode
                            result['debugger_pid_remaining'] = identity(debugger.pid)
                if args.resume:
                    resume_started = time.monotonic()
                    result['resume_start_ticks'] = model.ticks
                    while child.poll() is None and time.monotonic()-resume_started < 5:
                        pump(True)
                    result['resume'] = dict(seconds=time.monotonic()-resume_started,
                                           ticks=model.ticks, returncode=child.poll())
    except BaseException as error:
        result['verdict'], result['error'] = 'INVALID', repr(error)
        result['traceback'] = traceback.format_exc()
    finally:
        if child is not None:
            if child.poll() is None:
                send(signal.SIGKILL)
            child.wait(timeout=5)
            result['returncode'] = child.returncode
            result['owned_pid_remaining'] = identity(child.pid)
            # killpg(0) checks only the group we created; never scan unrelated /proc.
            try:
                os.killpg(child.pid, 0)
                result['owned_group_remaining'] = True
            except ProcessLookupError:
                result['owned_group_remaining'] = False
            if result['owned_group_remaining']:
                result['verdict'] = 'INVALID'
        result['wall_seconds'] = time.monotonic()-started
        result['evidence_sha256'] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
        save('result.json', result)
        print(json.dumps(dict(evidence=str(output), **{k: result.get(k) for k in
            ('verdict', 'returncode', 'signal_wait_seconds', 'owned_group_remaining', 'error')})), flush=True)
    return {'GREEN': 0, 'RED': 1, 'INVALID': 2}[result['verdict']]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticks', type=int, default=10004)
    parser.add_argument('--signal', choices=['TERM', 'INT'], default='TERM')
    parser.add_argument('--flow', choices=['stopped', 'live'], default='stopped')
    parser.add_argument('--dds', type=int, choices=[0, 1], default=1)
    parser.add_argument('--gdb', action='store_true')
    parser.add_argument('--resume', action='store_true', help='After the five-second verdict, resume real sensors for at most five seconds')
    parser.add_argument('--audit', action='store_true', help='Offline: verify saved evidence and capture fixed source, without starting AP')
    parser.add_argument('--ap-build-manifest', help='Explicit independent experimental AP build; production pins remain unchanged')
    parser.add_argument('--ap-build-sha256', help='Reviewed SHA256 of the selected build manifest')
    args = parser.parse_args()
    if not 1000 <= args.ticks <= 10004:
        parser.error('--ticks must be 1000..10004')
    raise SystemExit(audit() if args.audit else main(args))
