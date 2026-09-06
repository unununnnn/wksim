"""Windows integration gate: product runtime -> live IPC -> UE, never trace-to-UE.

Diagnostic truth/readback files are only observed. Stopping the bridge while
airborne tests a real transport disconnect; the private physics/FC run continues.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from Simulator.ue55.bridge import LatestTruth
from validate_ue55 import wsl_path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def invalid_product_packets(packet):
    base = dict(packet, sequence=packet['sequence'] + 10**9,
                sim_time_s=packet['sim_time_s'] + 100, display_wall_time_s=time.time())
    return [dict(base, run_id='foreign-run'), dict(base, vehicle_id=2), dict(base, version=1),
            dict(base, quaternion_wxyz=[0, 0, 0, 0]), dict(base, position_frame='ENU'),
            dict(base, position_ned_m=[0, 0]), dict(base, rotor_rpm=[-1, 0, 0, 0]),
            dict(base, display_wall_time_s=time.time()-30), dict(base, display_wall_time_s=time.time()+30),
            dict(packet, display_wall_time_s=time.time())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', required=True, choices=('px4', 'arducopter'))
    parser.add_argument('--control-protocol', choices=('session_v1', 'legacy_v1'), default='session_v1')
    args = parser.parse_args()
    run_id = 'visual-' + args.stack + '-' + uuid.uuid4().hex[:10]
    evidence = Path(tempfile.mkdtemp(prefix='product-visual-' + args.stack + '-', dir=REPO / 'validation'))
    frames = evidence / 'frames'
    frames.mkdir()
    suffix = '-session' if args.control_protocol == 'session_v1' else ''
    config = json.loads((REPO / ('Simulator/wksim_runtime/examples/' + args.stack + suffix + '.json')).read_text())
    socket_directory = '/tmp/wksim-' + run_id
    config.update(run_id=run_id, display_socket=socket_directory + '/state.sock')
    (evidence / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    build = json.loads((REPO / 'Simulator/ue55/state-build-manifest.json').read_text())
    result = dict(status='failed', run_id=run_id, stack=args.stack, evidence=str(evidence),
                  thresholds=dict(position_cm=2e-4, quaternion_l2=2e-6, sim_time_s=1e-8,
                                  minimum_readbacks=30, outage_wall_s=3, outage_sim_progress_s=1),
                  scope='single-vehicle product state, real FC, UE Actor + rendered frames; no joint scene')
    (evidence / 'thresholds.json').write_text(json.dumps(result['thresholds'], indent=2))
    result['validator_sha256'] = sha(__file__)
    result['source_sha256'] = {p: sha(REPO / p) for p in ('Simulator/ue55/product_bridge.py',
        'Simulator/ue55/state_relay.py', 'Simulator/ue55/bridge.py', 'Simulator/wksim_core/state_stream.py')}
    result['ue_binary_sha256'] = sha(build['binary'])
    if result['ue_binary_sha256'] != build['binary_sha256']:
        raise ValueError('Built UE binary identity changed')
    for source in build['build_inputs']:
        if sha(REPO / 'Simulator/ue55' / source['path']) != source['source_sha256']:
            raise ValueError('UE source changed since build: ' + source['path'])
    port = 19060
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as check:
        check.bind(('127.0.0.1', port))
    children, handles = [], []
    ue = flight = bridge = None
    start = time.monotonic()
    deadline = start + 240
    run_directory = evidence / 'runs' / run_id
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe_socket.bind(('127.0.0.1', 0))
    probe_socket.setblocking(False)
    probes_sent, probe_acks = False, 0

    def launch(argv, name):
        log = (evidence / (name + '.log')).open('x', encoding='utf-8')
        handles.append(log)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        child = subprocess.Popen(argv, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup)
        children.append((name, child))
        result[name] = dict(argv=argv, pid=child.pid)
        return child

    def wsl(*argv):
        return subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--exec', *argv],
                              capture_output=True, text=True, timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW)

    def start_bridge(number):
        return launch([sys.executable, '-X', 'utf8', '-m', 'Simulator.ue55.product_bridge',
                       '--wsl-repo', wsl_path(REPO), '--state-socket', config['display_socket'],
                       '--run-id', run_id, '--vehicle-id', '1', '--port', str(port),
                       '--readback', str(evidence / f'actor-{number}.jsonl')], f'bridge-{number}')

    try:
        created = wsl('mkdir', '-m', '700', '--', socket_directory)
        if created.returncode:
            raise RuntimeError(created.stderr)
        ue = launch(['E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe', build['project'],
                     '/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
                     '-game', '-windowed', '-ResX=1280', '-ResY=720', '-NoSound', '-NoSplash', '-unattended',
                     '-ExecCmds=t.IdleWhenNotForeground 0,t.MaxFPS 30', '-WksimVehicle=1',
                     '-WksimRunId=' + run_id, '-WksimPort=' + str(port),
                     '-abslog=' + str(evidence / 'ue.log'), '-WksimCaptureDir=' + str(frames)], 'ue-launch')
        while True:
            if ue.poll() is not None:
                raise RuntimeError('UE exited during startup')
            if time.monotonic() - start > 60:
                raise TimeoutError('UE startup')
            log = evidence / 'ue.log'
            if log.exists() and 'WKSIM_READY' in log.read_text(errors='replace'):
                break
            time.sleep(0.1)
        bridge = start_bridge(1)
        flight = launch(['wsl.exe', '-d', 'Ubuntu-22.04', '--cd', wsl_path(REPO), '--exec', 'bash',
                         'tools/run-wksim.sh', wsl_path(evidence / 'config.json'),
                         '--output-root', wsl_path(evidence / 'runs')], 'flight')
        truth = LatestTruth(run_directory / 'truth.jsonl')
        latest, outage, done_at = None, None, None
        print(json.dumps(dict(evidence=str(evidence), run_id=run_id)), flush=True)
        while time.monotonic() < deadline:
            now = time.monotonic()
            sample = truth.poll()
            if sample:
                latest = sample
            readback = evidence / 'actor-1.jsonl'
            if not probes_sent and readback.is_file() and readback.stat().st_size:
                lines = readback.read_bytes().split(b'\n')[:-1]
                if lines:
                    packet = json.loads(lines[-1])['packet']
                    probes = invalid_product_packets(packet)
                    for invalid in probes:
                        probe_socket.sendto(json.dumps(invalid).encode(), ('127.0.0.1', port))
                    result['rejection_probes'] = len(probes)
                    probes_sent = True
            try:
                probe_socket.recvfrom(4096)
                probe_acks += 1
            except (BlockingIOError, ConnectionResetError):
                pass
            if latest and outage is None and -latest['vehicle'][8] >= 2.5 and readback.is_file() and readback.stat().st_size > 10000:
                outage = dict(start_sim_s=latest['time'], start_wall_s=now-start)
                bridge.terminate()  # Kill only our view consumer; pipe EOF ends its own WSL relay.
                bridge.wait(timeout=5)
                outage['bridge_stopped'] = True
                print('Product display disconnected; physics and public task untouched', flush=True)
            if outage and 'end_sim_s' not in outage and now-start-outage['start_wall_s'] >= 3:
                if wsl('test', '!', '-e', config['display_socket']).returncode:
                    raise RuntimeError('Bridge relay failed to clean its owned socket after EOF')
                outage.update(end_sim_s=latest['time'], end_wall_s=now-start,
                              sim_progress_s=latest['time']-outage['start_sim_s'])
                bridge = start_bridge(2)
                print('Product display restarted at latest state', flush=True)
            if ue.poll() is not None:
                raise RuntimeError('UE exited')
            if bridge.poll() is not None and (outage is None or 'end_sim_s' in outage):
                raise RuntimeError('Product bridge exited')
            if flight.poll() is not None:
                done_at = done_at or now
                if now - done_at >= 4:
                    break
            time.sleep(0.02)
        if flight.poll() is None:
            raise TimeoutError('Runtime/visual acceptance deadline')
        result['flight_exit'] = flight.returncode
        flight_result = json.loads((run_directory / 'result.json').read_text())
        result['flight_result'] = str(run_directory / 'result.json')
        result['flight_result_sha256'] = sha(result['flight_result'])
        result['outage'] = outage
        rows = []
        for path in sorted(evidence.glob('actor-*.jsonl')):
            rows.extend(json.loads(line) for line in path.read_text().splitlines())
        result['readbacks'] = len(rows)
        result['unexpected_probe_acks'] = probe_acks
        result['rejected_max'] = max((r['ack']['rejected'] for r in rows), default=0)
        result['max_error'] = {key: max((r['errors'][key] for r in rows), default=float('inf'))
                               for key in ('position_cm', 'quaternion_l2', 'sim_time_s')}
        captures = []
        for line in (evidence / 'ue.log').read_text(errors='replace').splitlines():
            match = re.search(r'WKSIM_CAPTURE .*?(frame-\d+\.png) sequence=(-?\d+) sim=([\d.]+) stale=(\d)', line)
            if match and (frames / match[1]).is_file():
                captures.append(dict(file=str(frames / match[1]), sequence=int(match[2]),
                                     sim_time_s=float(match[3]), stale=bool(int(match[4])), sha256=sha(frames / match[1])))
        result['captures'] = captures
        result['checks'] = dict(flight_pass=flight_result['status'] == 'pass' and flight.returncode == 0,
            landed=flight_result['safe_landing'], children_reaped=flight_result['children_reaped'],
            readbacks=len(rows) >= 30,
            invalid_packets_rejected=bool(probes_sent and probe_acks == 0 and
                result['rejected_max'] >= result['rejection_probes']),
            coordinates=all(result['max_error'][k] <= result['thresholds'][k] for k in result['max_error']),
            physics_progress=bool(outage and outage.get('sim_progress_s', 0) >= 1),
            live_frame=any(not c['stale'] and c['sequence'] >= 0 for c in captures),
            stale_during_loss=bool(outage and any(c['stale'] and c['sequence'] >= 0 and
                                  c['sim_time_s'] <= outage['start_sim_s'] for c in captures)),
            recovered_current=bool(outage and any(not c['stale'] and c['sim_time_s'] >= outage.get('end_sim_s', float('inf')) for c in captures)))
        result['status'] = 'pass' if all(result['checks'].values()) else 'failed'
    except Exception as error:
        result['error'] = str(error)
    finally:
        # Product runtime has its own 180s watchdog and scoped cleanup. Do not kill
        # the WSL launcher before its children can be reaped if the viewer fails.
        while flight and flight.poll() is None and time.monotonic() < deadline + 15:
            time.sleep(0.1)
        for name, child in reversed(children):
            if child is flight and child.poll() is None:
                result['runtime_cleanup_pending'] = True
                continue
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        result['launcher_returncodes'] = {name: child.poll() for name, child in children}
        result['display_socket_removed'] = wsl('test', '!', '-e', config['display_socket']).returncode == 0
        for handle in handles:
            handle.close()
        probe_socket.close()
        result['wall_s'] = time.monotonic() - start
        (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'captures'}, indent=2), flush=True)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
