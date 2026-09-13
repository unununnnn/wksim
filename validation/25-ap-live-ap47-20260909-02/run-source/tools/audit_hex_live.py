"""Owned Windows Hex live coordinator and offline raw/Actor/capture audit.

No simulation starts unless the explicit `run` subcommand is used. An automatic
Actor pass remains pending rendered-image review. Existing flight/bridge/UE code
and frozen physical/visual budgets are reused without modification.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Simulator.ue55.hex_bridge import binding, validate, actor_readback_errors
from tools.check_hex_view import LIMITS

MODEL = 'sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a'
MODULE_SHA = '15af1f6e400e77d6a8a207fd047b48b1d04c54260a5668312178051c119e6245'
SOURCES = ('tools/audit_hex_live.py', 'tools/run-hex-live.ps1', 'Simulator/ue55/hex_bridge.py',
           'Simulator/ue55/bridge.py', 'tools/check_hex_view.py', 'docs/2026-09-09-hex-visual-contract.md')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def wsl_path(path):
    path = Path(path).resolve()
    require(re.fullmatch('[A-Za-z]:', path.drive) is not None, 'Expected local Windows drive path')
    return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])


def windows_raw(path):
    require(path.startswith('/root/wksim-hex-flight-') and '..' not in Path(path).parts,
            'Unexpected owned Linux experiment path')
    return Path('\\\\wsl.localhost\\Ubuntu-22.04' + path.replace('/', '\\'))


def wait_ready(child, condition, timeout, label):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        require(child.poll() is None, label + ' process exited before readiness')
        if condition():
            return
        time.sleep(.1)
    raise TimeoutError(label + ' readiness timeout')


def audit(directory, render_review=None):
    directory = Path(directory).resolve()
    manifest = read(directory / 'manifest.json')
    expected = binding(**manifest['binding'])
    require(expected['model_identity'] == MODEL, 'Unreviewed model')
    require(manifest['module_sha256'] == MODULE_SHA, 'Unreviewed UE candidate')
    require(set(manifest['source_sha256']) == set(SOURCES), 'Incomplete live source identity')
    for name, sha in manifest['source_sha256'].items():
        require(digest(directory/'run-source'/name) == sha, 'Archived live source changed: ' + name)
        require(digest(ROOT/name) == sha, 'Current live verifier/source differs from run: ' + name)
    completion = read(directory / 'completion.json')
    require(completion['flight_returncode'] == 0 and completion['bridge_returncode'] == 0,
            'Flight/bridge did not complete normally')
    require(completion['owned_processes_exited'] is True and not completion['errors'], 'Unsuccessful owned cleanup')
    require(completion['source_unchanged'] is True and completion['module_unchanged'] is True,
            'Source/candidate changed during run')
    flight = read(directory / 'flight-audit.json')
    require(flight.get('passed') is True and flight['checks']['result']['run_id'] == expected['run_id'],
            'Independent physical flight audit rejected/foreign')
    require(flight['root'] == manifest['run_dir'], 'Flight audit path differs')
    if manifest['cold_reset_from']:
        cold = flight['checks']['cold_reset']
        require(cold.get('tick0') is True and cold.get('parent_audit', {}).get('passed') is True,
                'Cold-reset audit missing')
    result_path = windows_raw(manifest['run_dir'] + '/result.json') if os.name == 'nt' else Path(manifest['run_dir']) / 'result.json'
    raw_path = result_path.with_name('physics-1ms.jsonl')
    require(digest(result_path) == flight['inputs_sha256']['result.json'], 'Result changed after physical audit')
    require(digest(raw_path) == flight['inputs_sha256']['physics-1ms.jsonl'], 'Raw changed after physical audit')
    for name, sha in flight['inputs_sha256'].items():
        path = (result_path.parent/name).resolve()
        require(path.is_relative_to(result_path.parent.resolve()), 'Escaping flight audit input path')
        require(digest(path) == sha, 'Flight audit input changed: ' + name)
    result = read(result_path)
    require(result['stack'] == manifest['stack'] and result['run_id'] == expected['run_id'], 'Foreign flight result')
    require(result['admission']['identities']['hex_config']['model_identity'] == expected['model_identity'], 'Flight model differs')
    rows = []
    with (directory / 'readback.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            rows.append(json.loads(line))
    require(rows, 'Empty Actor ACK evidence')
    packets = {}
    previous = None
    maxima = dict.fromkeys(LIMITS, 0.)
    for row in rows:
        packet, ack = row['packet'], row['ack']
        # Packet's recorded UTC plus bound reconstructs send-side now. Receiver ACK
        # proves its own freshness guard accepted; original bridge records no ACK UTC.
        validate(packet, expected, now=packet['display_wall_time_s'] + packet['transport_age_bound_s'])
        require(packet['sequence'] == packet['step'], 'Raw bridge sequence differs from tick')
        if previous is None:
            require(ack.get('previous_step') == -1, 'Initial phase history missing')
        else:
            require(ack.get('previous_step') == previous['step'], 'Missing accepted phase continuity')
            require(packet['step'] > previous['step'], 'Regressed ACK')
            require(packet['source_monotonic_s'] > rows[len(packets)-1]['packet']['source_monotonic_s'],
                    'Regressed source clock')
        errors = actor_readback_errors(packet, ack, previous)
        for key, limit in LIMITS.items():
            value = errors.get(key)
            require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= limit,
                    'Visual budget failed: ' + key)
            maxima[key] = max(maxima[key], value)
        packets[packet['step']] = packet
        previous = ack
    matched = set()
    with raw_path.open() as stream:
        first = json.loads(next(stream))
        require(first.get('kind') == 'start' and all(first.get(k) == expected[k] for k in ('run_id', 'model_identity')),
                'Raw start binding differs')
        for line in stream:
            raw = json.loads(line)
            if raw.get('kind') != 'step' or raw['tick'] not in packets:
                continue
            packet = packets[raw['tick']]
            output = raw['output120']
            require(packet['sim_time_s'] == output[2] and packet['position_ned_m'] == output[6:9]
                    and packet['quaternion_wxyz'] == output[12:16] and packet['rotor_rpm'] == output[16:22]
                    and packet['source_monotonic_s'] == raw['observed_monotonic_ns'] / 1e9,
                    'Displayed state differs from actual raw tick')
            matched.add(raw['tick'])
    require(matched == packets.keys(), 'Displayed tick absent from raw')
    phases = {p['phase']: p['physical_cursor']['final_time'] for p in result['task']['hex']['phases']
              if p.get('physical_cursor')}
    # These are existing task phase boundaries, not new duration/cadence budgets.
    # SET_CONTROL_MODE performs native takeoff before its completion event.
    # HexTask records `armed` immediately before publishing that request; starting
    # at task_control_ready would cover only the final 20 ms in retained PX4-03.
    intervals = [('takeoff', 'armed', 'takeoff_reached'),
                 ('hold', 'takeoff_reached', 'hold_completed'),
                 ('waypoint', 'waypoint_accepted', 'waypoint_completed'),
                 ('landing', 'land_accepted', 'landed_disarmed_public')]
    coverage = {}
    for name, start, end in intervals:
        require(start in phases and end in phases, 'Missing flight phase: ' + name)
        coverage[name] = sum(phases[start] <= p['sim_time_s'] <= phases[end] for p in packets.values())
        require(coverage[name] > 0, 'No actual display evidence during ' + name)
    captures = {}
    pattern = re.compile(r'WKSIM_CAPTURE (.+?) sequence=(\d+) sim=([0-9.]+) stale=(\d+) rejected=(\d+)')
    for match in pattern.finditer((directory / 'ue.log').read_text(encoding='utf-8', errors='replace')):
        name = re.split(r'[/\\]', match[1])[-1]
        sequence = int(match[2])
        if match[4] != '0' or sequence not in packets:
            continue
        require(re.fullmatch(r'frame-\d+\.png', name), 'Unexpected capture name')
        require(abs(float(match[3]) - packets[sequence]['sim_time_s']) <= LIMITS['sim_time_s'], 'Capture source time differs')
        path = directory / 'frames' / name
        require(path.is_file() and path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'Missing/invalid rendered capture')
        captures[name] = dict(sha256=digest(path), sequence=sequence)
    require(captures, 'No fresh capture bound to an Actor ACK')
    review = read(render_review) if render_review else None
    if review is not None:
        require(review.get('binding') == expected and review.get('six_rotor_structure_visible') is True
                and review.get('live_hud_visible') is True and isinstance(review.get('reviewer'), str)
                and bool(review['reviewer'].strip()), 'Missing explicit rendered-image review')
        selected = review.get('captures')
        require(type(selected) is dict and selected, 'Empty rendered-image review')
        require(all(name in captures and sha == captures[name]['sha256'] for name, sha in selected.items()),
                'Rendered review capture hash differs')
    steps = sorted(packets)
    return dict(schema='wksim.hex.live.audit.v1', actor_passed=True, passed=review is not None,
                status='passed' if review else 'render_review_required', binding=expected,
                ack_count=len(rows), maxima=maxima, limits=LIMITS, phase_ack_counts=coverage,
                max_accepted_step_gap=max((b-a for a, b in zip(steps, steps[1:])), default=0),
                gap_scope='Reported only; no new display cadence budget introduced', captures=captures,
                freshness_scope='Recorded source/transport bounds plus actual receiver acceptance; no independent ACK receive UTC',
                render_review_sha256=digest(render_review) if review else None,
                inputs_sha256={name:digest(directory/name) for name in
                    ('manifest.json', 'completion.json', 'flight-audit.json', 'readback.jsonl', 'ue.log')})


def coordinate(args):
    require(os.name == 'nt', 'Live coordinator runs on Windows')
    expected = binding(args.run_id, uuid.uuid4().hex, MODEL)
    directory = Path(args.output).resolve()
    require(not directory.exists(), 'Use a fresh evidence directory')
    require(re.fullmatch(r'/root/wksim-hex-flight-[A-Za-z0-9_-]+', args.output_root), 'Invalid fresh experiment output root')
    run_dir = args.output_root + '/' + args.run_id
    require(not windows_raw(args.output_root).exists(), 'Experiment output already exists')
    stage = Path(args.stage).resolve()
    module = stage / 'Binaries/Win64/UnrealEditor-WksimVisual.dll'
    require(digest(module) == MODULE_SHA, 'Candidate UE module hash differs')
    project = stage / 'WksimVisual.uproject'
    require(project.is_file() and Path(args.engine).is_file(), 'UE engine/project missing')
    require(Path(args.audit_runner).is_file(), 'Fixed flight audit overlay runner missing')
    directory.mkdir(parents=True)
    (directory / 'frames').mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    repo = wsl_path(ROOT)
    wsl = ['wsl.exe', '-d', 'Ubuntu-22.04', '-u', 'root', '--cd', repo, '--exec']
    ue = [args.engine, str(project), '/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
          '-game', '-windowed', '-ResX=1280', '-ResY=720', '-NoSound', '-NoSplash', '-unattended',
          '-ExecCmds=t.IdleWhenNotForeground 0,t.MaxFPS 30', '-abslog=' + str(directory/'ue.log'),
          '-WksimRunId=' + args.run_id, '-WksimVehicle=1', '-WksimConfiguration=hex-X',
          '-WksimInstance=' + expected['instance_id'], '-WksimModelIdentity=' + MODEL,
          '-WksimPort=' + str(port), '-WksimCaptureDir=' + str(directory/'frames')]
    bridge = [sys.executable, '-B', '-m', 'Simulator.ue55.hex_bridge', '--wsl-repo', repo,
              '--raw', run_dir+'/physics-1ms.jsonl', '--run-id', args.run_id,
              '--instance-id', expected['instance_id'], '--model-identity', MODEL,
              '--port', str(port), '--readback', str(directory/'readback.jsonl'), '--duration', '330']
    flight = wsl + ['bash', 'tools/run-hex-flight.sh', '--stack', args.stack, '--run-id', args.run_id,
                    '--output-root', args.output_root]
    if args.cold_reset_from:
        require(args.stack == 'px4', 'This slice supports PX4 cold-reset only')
        flight += ['--cold-reset-from', args.cold_reset_from]
    audit_cmd = wsl + ['bash', wsl_path(args.audit_runner), 'tools/audit_hex_flight.py', '--run-dir', run_dir,
                       '--output', wsl_path(directory/'flight-audit.json')]
    if args.cold_reset_from:
        audit_cmd += ['--require-cold-reset']
        parent = str(Path(args.cold_reset_from).parent).replace('\\', '/')
        checked = subprocess.run(wsl + ['bash', wsl_path(args.audit_runner), 'tools/audit_hex_flight.py',
            '--run-dir', parent, '--output', wsl_path(directory/'parent-audit.json')], timeout=300,
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (directory/'parent-audit.log').write_bytes(checked.stdout + checked.stderr)
        require(checked.returncode == 0, 'Cold-reset parent independent audit rejected')
    preflight = subprocess.run(wsl + ['python3', '-B', 'tools/run_hex_flight.py', '--stack', args.stack,
        '--run-id', args.run_id, '--preflight'], timeout=300, capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    (directory/'preflight.log').write_bytes(preflight.stdout + preflight.stderr)
    require(preflight.returncode == 0, 'Read-only Hex preflight rejected')
    admission = json.loads(preflight.stdout)
    require(admission['ok'] is True and admission['identities']['hex_config']['model_identity'] == MODEL,
            'Preflight model does not match launch binding')
    manifest = dict(schema='wksim.hex.live.run.v1', binding=expected, stack=args.stack, run_dir=run_dir,
                    cold_reset_from=args.cold_reset_from, module_sha256=digest(module), port=port,
                    commands=dict(ue=ue, bridge=bridge, flight=flight, audit=audit_cmd),
                    source_sha256={name:digest(ROOT/name) for name in SOURCES},
                    audit_runner=dict(path=str(args.audit_runner), sha256=digest(args.audit_runner)))
    save(directory/'manifest.json', manifest)
    for name in manifest['source_sha256']:
        archived = directory/'run-source'/name
        archived.parent.mkdir(parents=True, exist_ok=True)
        with archived.open('xb') as stream:
            stream.write((ROOT/name).read_bytes())
    children, logs = {}, []
    completion = dict(flight_returncode=None, bridge_returncode=None, owned_processes_exited=False, errors=[])
    def launch(name, argv):
        out = (directory/(name+'.stdout.log')).open('xb')
        err = (directory/(name+'.stderr.log')).open('xb')
        logs.extend([out, err])
        child = subprocess.Popen(argv, cwd=ROOT, stdout=out, stderr=err,
                                 creationflags=subprocess.CREATE_NO_WINDOW,
                                 startupinfo=hidden_startup())
        children[name] = child
        save(directory/(name+'-owner.json'), dict(pid=child.pid, argv=argv,
             started_wall_ns=time.time_ns(), ownership='retained Popen native process handle; never rediscover by PID'))
        return child
    try:
        ue_child = launch('ue', ue)
        log = directory/'ue.log'
        marker = 'WKSIM_READY run=' + args.run_id + ' vehicle=1 port=' + str(port)
        wait_ready(ue_child, lambda: log.exists() and marker in log.read_text(errors='replace'), 120, 'UE')
        bridge_child = launch('bridge', bridge)
        wait_ready(bridge_child, lambda: (directory/'readback.jsonl').exists(), 30, 'Bridge')
        # The bridge's exclusive evidence open proves it reached its pull loop;
        # the relay itself supplies no ready event. All later absence fails audit.
        flight_child = launch('flight', flight)
        completion['flight_returncode'] = flight_child.wait(timeout=330)
        completion['bridge_returncode'] = bridge_child.wait(timeout=15)
    except Exception as error:
        completion['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        for name, child in reversed(list(children.items())):
            if child.poll() is None:
                if name == 'flight':
                    completion['errors'].append('Flight supervisor still running: leave native ownership intact; requires owner inspection')
                    continue
                # Exact retained process handle, no PID-name lookup or global kills.
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    completion['errors'].append(name + ' failed to exit after owned termination')
            completion[name+'_exit'] = child.poll()
        completion['owned_processes_exited'] = all(c.poll() is not None for c in children.values())
        completion['source_unchanged'] = all(digest(ROOT/name) == sha for name, sha in manifest['source_sha256'].items())
        completion['module_unchanged'] = digest(module) == manifest['module_sha256']
        completion['cleanup_scope'] = 'Owned Windows handles; flight audit independently checks native children. Bridge relay has no separate identity record.'
        for stream in logs:
            stream.close()
        save(directory/'completion.json', completion)
    require(not completion['errors'] and completion['flight_returncode'] == 0
            and completion['bridge_returncode'] == 0, 'Live run incomplete; preserve failure evidence')
    checked = subprocess.run(audit_cmd, timeout=300, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    (directory/'flight-audit.log').write_bytes(checked.stdout + checked.stderr)
    require(checked.returncode == 0, 'Independent flight audit rejected')
    return directory


def hidden_startup():
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('audit')
    check.add_argument('--directory', required=True, type=Path)
    check.add_argument('--output', required=True, type=Path)
    check.add_argument('--render-review', type=Path)
    run = sub.add_parser('run')
    run.add_argument('--stack', required=True, choices=['arducopter', 'px4'])
    run.add_argument('--run-id', required=True)
    run.add_argument('--output-root', required=True)
    run.add_argument('--output', required=True, type=Path)
    run.add_argument('--cold-reset-from')
    run.add_argument('--stage', default='E:/ue5.5/build/wksim-native-hex-20260909-01')
    run.add_argument('--engine', default='E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe')
    run.add_argument('--audit-runner', type=Path, default=ROOT/'validation/lunar-65-astra-20260909-01/run-audit.sh')
    args = parser.parse_args()
    output = args.output if args.command == 'audit' else args.output/'automatic-audit.json'
    require(not output.exists(), 'Audit output must be fresh')
    try:
        directory = coordinate(args) if args.command == 'run' else args.directory
        result = audit(directory, getattr(args, 'render_review', None))
    except Exception as error:
        result = dict(schema='wksim.hex.live.audit.v1', passed=False, status='rejected',
                      error=type(error).__name__ + ': ' + str(error))
    if output.parent.exists():
        save(output, result)
    print(json.dumps(result))
    return 0 if result.get('passed') else 2 if result.get('actor_passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
