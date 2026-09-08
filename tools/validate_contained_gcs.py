"""One owned Windows QGC / independent mission run; never generates MAVLink commands.

Default is read-only preflight. --execute starts real resources; run serially.
"""
import argparse
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import traceback
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    deadline = time.monotonic() + .5
    while True:
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if time.monotonic() >= deadline: raise
            time.sleep(.01)


def read_json(path):
    deadline = time.monotonic() + .5
    while True:
        try: return json.loads(path.read_text())
        except PermissionError:
            if time.monotonic() >= deadline: raise
            time.sleep(.01)


def rows(path):
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            pass  # Live writers may have an incomplete final line.
    return result


def sha(path):
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
        return digest.hexdigest()


def last_truth(path):
    # Same bounded tail strategy as validate_sitl_telemetry; no full trace scan.
    if not path.exists():
        return None
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 32768))
        lines = stream.read(32768).split(b'\n')
    for line in reversed(lines[:-1]):
        try:
            row = json.loads(line)
            return {'time': row['time'], 'height_m': -row['vehicle'][8]}
        except (ValueError, KeyError, IndexError):
            continue
    return None


def settings(path):
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    ini.read(path, encoding='utf-8')
    keys = ('LibrePilot', 'Pixhawk', 'RTKGPS', 'SiKRadio', 'UDP', 'ZeroConf')
    assert all(ini['AutoConnect']['autoConnect' + key] == 'false' for key in keys), 'AutoConnect enabled'
    expected = {'count': '1', 'Link0\\type': '0', 'Link0\\auto': 'true',
                'Link0\\port': '14560', 'Link0\\hostCount': '1',
                'Link0\\host0': '127.0.0.1', 'Link0\\port0': '14570'}
    assert all(ini['LinkConfigurations'].get(k) == v for k, v in expected.items()), 'Saved link differs'
    assert not any(re.match(r'Link[1-9]', k) for k in ini['LinkConfigurations']), 'Extra saved links'
    return {'path': str(path), 'sha256': sha(path), 'verified': expected}


def linux(args):
    """Capture diagnostic bytes while the existing formal validator owns its run."""
    from Simulator.wksim_runtime.evidence import json_identity
    import tempfile
    out = args.output.resolve()
    run_id = 'gcs-' + args.stack + '-' + uuid.uuid4().hex[:12]
    private = Path(tempfile.mkdtemp(prefix=run_id + '-', dir='/tmp'))
    config = json.loads((REPO / 'Simulator/wksim_runtime/examples' / (args.stack + '-mission.json')).read_text())
    config.update(run_id=run_id,
                  telemetry_socket=str(private / 'native.sock'), gcs_udp_forward='127.0.0.1:14560')
    if args.promotion_flight:
        config['promotion_flight'] = True
    save(out / 'config.json', config)
    child = None
    identity = None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as capture, (out / 'native.jsonl').open('w', buffering=1) as evidence:
            capture.bind(config['telemetry_socket'])
            os.chmod(config['telemetry_socket'], 0o600)
            capture.setblocking(False)
            with (out / 'formal-driver.log').open('w') as log:
                child = subprocess.Popen([sys.executable, '-B', str(REPO / 'tools/validate_independent_profile.py'),
                    str(out / 'config.json'), '--output', str(out / 'formal')], stdout=log, stderr=subprocess.STDOUT)
                identity = json_identity(child.pid)
                save(out / 'linux-owned.json', {'wrapper': json_identity(os.getpid()), 'validator': identity,
                    'private': str(private), 'run_id': config['run_id']})
                deadline = time.monotonic() + 420
                truth_path = None
                while child.poll() is None:
                    if (out / 'abort').exists() or time.monotonic() > deadline:
                        raise TimeoutError('Abort requested or formal run exceeded 420 seconds')
                    for _ in range(128):
                        try:
                            raw = capture.recv(65536)
                            evidence.write(raw.decode('utf-8') + '\n')
                        except BlockingIOError:
                            break
                    if truth_path is None:
                        candidates = list(Path('/root').glob('wksim-independent-*/' + config['run_id'] + '/truth.jsonl'))
                        if len(candidates) == 1:
                            truth_path = candidates[0]
                    truth = last_truth(truth_path) if truth_path else None
                    if truth:
                        save(out / 'live-truth.json', truth)
                    if (private / 'gcs-reverse.sock').is_socket() and not (out / 'ready.json').exists():
                        save(out / 'ready.json', {'forward': str(private / 'gcs-forward.sock'),
                                                  'reverse': str(private / 'gcs-reverse.sock')})
                    time.sleep(.002)
                return child.returncode
    finally:
        if child is not None and child.poll() is None:
            if json_identity(child.pid) != identity:
                raise RuntimeError('Validator identity changed; refusing signal')
            child.send_signal(signal.SIGINT)  # Existing validator catches BaseException and reaps its manager.
            try:
                child.wait(timeout=40)
            except subprocess.TimeoutExpired:
                save(out / 'cleanup-incomplete.json', {'validator': identity, 'reason': 'Not killed: descendant cleanup unconfirmed'})
        # Retain private paths on any failure; never recursively remove anything.
        save(out / 'linux-finished.json', {'returncode': None if child is None else child.poll(), 'private': str(private)})


def windows(args):
    from Simulator.wksim_console.gcs_bridge import wsl_path
    exe = REPO / 'work/qgc-contained-build/stage/bin/WksimGCS.exe'
    ini = Path(os.environ['APPDATA']) / 'WksimLocal/WksimGCS Daily.ini'
    preflight = {'settings': settings(ini), 'executable': str(exe), 'exe_sha256': sha(exe), 'driver_sha256': sha(Path(__file__))}
    ps = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
        "Get-Process WksimGCS,QGroundControl -ErrorAction SilentlyContinue | Select-Object Id,Path | ConvertTo-Json -Compress"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert not ps.stdout.strip(), 'Existing QGC found; leave it and its ports untouched: ' + ps.stdout
    for port in (14560, 14570):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(('0.0.0.0', port))
    version = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
        "(Get-Item -LiteralPath '" + str(exe).replace("'", "''") + "').VersionInfo | Select-Object FileVersion,ProductVersion | ConvertTo-Json"],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    preflight['version'] = json.loads(version.stdout)
    if not args.execute:
        print(json.dumps(preflight, indent=2))
        return 0
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'preflight.json', preflight)
    processes = []
    logs = []
    report = {'status': 'failed', 'stack': args.stack, 'manual_mode_switch': 'not performed; separate user acceptance'}

    def start(argv, name):
        log = (out / (name + '.log')).open('wb')
        logs.append(log)
        child = subprocess.Popen(argv, cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append((name, child))
        report[name] = {'pid': child.pid, 'argv': argv}
        return child

    def wait_for(predicate, timeout):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError('Timed out waiting for contained run evidence')
            if any(p.poll() is not None for _, p in processes):
                raise RuntimeError('Owned process exited before expected milestone')
            time.sleep(.2)

    try:
        profile = json.loads((REPO / 'Simulator/wksim_runtime/joint-profiles.json').read_text())['profiles'][0]
        command = ' && '.join('source ' + shlex.quote(p) for p in profile['setup_files'])
        command += ' && exec python3 -B ' + shlex.quote(wsl_path(Path(__file__)))
        command += ' --linux --stack ' + args.stack + ' --output ' + shlex.quote(wsl_path(out))
        if args.promotion_flight: command += ' --promotion-flight'
        formal = start(['wsl.exe', '-d', 'Ubuntu-22.04', '--cd', wsl_path(REPO), '--exec', 'bash', '-c', command], 'linux')
        wait_for(lambda: (out / 'ready.json').exists(), 90)
        ready = read_json(out / 'ready.json')
        bridge = start([sys.executable, '-B', '-m', 'Simulator.wksim_console.gcs_bridge', '--repo', str(REPO),
            '--forward-socket', ready['forward'], '--reverse-socket', ready['reverse'], '--qgc-endpoint', '127.0.0.1:14560',
            '--relay-port', '14570', '--readback', str(out / 'bridge.jsonl'), '--stop-file', str(out / 'bridge.stop')], 'bridge')
        # Category strings are verified in QGC source, not C++ variable names.
        qgc = start([str(exe), '--logging:Comms.LinkManager,Vehicle.MultiVehicleManager', '--log-output'], 'qgc')
        wait_for(lambda: any(r.get('kind') == 'gcs_bridge_reverse' and r.get('relay', {}).get('reverse_forwarded', 0) > 0
                            for r in rows(out / 'bridge.jsonl')) and (out / 'live-truth.json').exists()
                            and read_json(out / 'live-truth.json')['height_m'] > .5, 90)
        before = read_json(out / 'live-truth.json')
        (out / 'bridge.stop').touch()
        bridge.wait(timeout=15)
        assert bridge.returncode == 0, 'Bridge did not close cleanly'
        report['truth_at_bridge_stop'] = before
        formal.wait(timeout=420)
        assert formal.returncode == 0
        result = json.loads((out / 'formal/report.json').read_text())
        assert result['status'] == 'pass'
        truth = last_truth(out / 'formal/run/truth.jsonl')
        assert truth['time'] > before['time'] + 1, 'Physics did not advance after bridge stopped'
        report['truth_after_bridge_stop'] = truth
        forwarded = [r['packet_base64'] for r in rows(out / 'bridge.jsonl') if r.get('kind') == 'gcs_bridge_forward']
        observer = [r for r in rows(out / 'formal/run/telemetry.log') if 'counters' in r][-1]
        source_hashes = set(observer['gcs_forwarded_packet_sha256'])
        assert not observer['gcs_hashes_truncated'], 'Source hash evidence reached its bound'
        assert forwarded and all(hashlib.sha256(base64.b64decode(packet, validate=True)).hexdigest() in source_hashes
                                 for packet in forwarded), 'Forward raw bytes lack observer source hash match'
        report['forward_packets_verified'] = len(forwarded)
        assert observer['counters']['reverse_forwarded'] > 0, 'Observer did not actually forward reverse bytes'
        report['observer'] = observer
        reverse_digest = hashlib.sha256()
        relay_count = 0
        for row in rows(out / 'bridge.jsonl'):
            if row.get('kind') != 'gcs_bridge_reverse':
                continue
            count = row['relay']['reverse_forwarded']
            assert count in (relay_count, relay_count + 1), 'Non-contiguous relay reverse evidence'
            if count > relay_count:
                packet = base64.b64decode(row['packet_base64'], validate=True)
                reverse_digest.update(len(packet).to_bytes(4, 'big') + packet)
            relay_count = count
        report['relay_reverse'] = {'count': relay_count, 'sha256': reverse_digest.hexdigest()}
        reverse_verified = observer.get('reverse_forwarded_sha256') is not None
        if reverse_verified:
            assert relay_count == observer['counters']['reverse_forwarded'], 'Relay and observer successful reverse counts differ'
            assert reverse_digest.hexdigest() == observer['reverse_forwarded_sha256'], 'Reverse raw-byte digest differs'
        log = (out / 'qgc.log').read_text(encoding='utf-8', errors='replace')
        sysid = 22 if args.stack == 'px4' else 241
        identity_lines = [line for line in log.splitlines() if 'Adding new vehicle link:vehicleId:' in line and re.search(r'\b' + str(sysid) + r'\s+1\s+', line)]
        assert identity_lines, 'QGC log lacks expected native vehicle identity'
        report.update(status='pass' if reverse_verified else 'partial', qgc_identity=identity_lines,
            limitation='Manual mode switch not exercised; not full issue #42 acceptance.' if reverse_verified else
            'Observer lacks reverse byte digest; cannot certify end-to-end reverse byte equality. Manual mode switch not exercised.')
    except BaseException as error:
        report['error'] = repr(error)
        report['traceback'] = traceback.format_exc()
    finally:
        (out / 'bridge.stop').touch()
        (out / 'abort').touch()
        for name, child in reversed(processes):
            if child.poll() is None:
                try:
                    if name == 'qgc':
                        child.terminate()  # Exact Popen handle, never name/PID search termination.
                    child.wait(timeout=50 if name == 'linux' else 15)
                except subprocess.TimeoutExpired:
                    report.setdefault('cleanup_incomplete', []).append(name)
            report[name]['returncode'] = child.poll()
        for log in logs:
            log.close()
        identities = []
        owned = out / 'linux-owned.json'
        if owned.exists():
            ownership = json.loads(owned.read_text())
            identities.extend([ownership['wrapper'], ownership['validator']])
        for row in rows(out / 'bridge.jsonl'):
            if row.get('kind') == 'gcs_bridge_start':
                identities.append(row['linux'])
        probe = ('import json,pathlib,sys; live=[]\n'
                 'for row in json.loads(sys.argv[1]):\n'
                 ' p=pathlib.Path("/proc")/str(row["pid"])/"stat"\n'
                 ' try: ticks=p.read_text().rsplit(")",1)[1].split()[19]\n'
                 ' except FileNotFoundError: continue\n'
                 ' if ticks==str(row["start_ticks"]): live.append(row)\n'
                 'print(json.dumps(live))')
        try:
            checked = subprocess.run(['wsl.exe', '-d', 'Ubuntu-22.04', '--exec', 'python3', '-c', probe,
                                      json.dumps(identities)], capture_output=True, text=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW, timeout=15, check=True)
            report['linux_remaining_owned_identities'] = json.loads(checked.stdout)
            if report['linux_remaining_owned_identities']:
                report.update(status='failed', cleanup_incomplete=['Linux identities remain; no broad kill attempted'])
        except Exception as error:
            report.update(status='failed', cleanup_probe_error=repr(error))
        try:
            report['settings_after'] = settings(ini)
        except Exception as error:
            report.update(status='failed', settings_error=repr(error))
        save(out / 'report.json', report)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'pass' and not report.get('cleanup_incomplete') else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', choices=('px4', 'arducopter'), default='px4')
    parser.add_argument('--output', type=Path, default=REPO / 'validation/gcs-bridge-20260908' / ('live-' + uuid.uuid4().hex[:12]))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--promotion-flight', action='store_true', help='Explicit unflown candidate admission; omitted for normal runs')
    parser.add_argument('--linux', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    raise SystemExit(linux(args) if args.linux else windows(args))
