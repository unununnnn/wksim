"""Real single-FC SIGSTOP -> shared authority freeze -> read-only UE stale query."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.ue55.bridge import actor_errors
from Simulator.wksim_console.visual import ACTOR_LIMITS
from tools.validate_joint_visual import read, save, unc

# Same PID/start-time/executable check used by validate_joint_input_stall.py.
# SIGCONT in finally only releases the exact owned process; it is not recovery.
SIGNAL_SCRIPT = """import json,os,signal,sys,time
from pathlib import Path
from Simulator.wksim_runtime.evidence import json_identity,process_identity,host_boot_id
child=json.loads(Path(sys.argv[1]).read_text())[sys.argv[2]]
expected=child['identity']; current=json_identity(expected['pid'])
assert current and all(current[k]==expected[k] for k in ('pid','pgid','start_ticks'))
exe=(Path('/proc')/str(current['pid'])/'exe').resolve(strict=True)
assert exe==Path(child['argv'][0]).resolve(strict=True)
sent=time.monotonic(); os.kill(current['pid'],getattr(signal,sys.argv[3]))
deadline=time.monotonic()+1
while True:
    kernel=process_identity(current['pid'])
    assert kernel and all(kernel[k]==current[k] for k in ('pid','pgid','start_ticks'))
    if (kernel['state']=='T')==(sys.argv[3]=='SIGSTOP'): break
    assert time.monotonic()<deadline
    time.sleep(.002)
print(json.dumps(dict(identity=current,executable=str(exe),host_boot_id=host_boot_id(),
    signal=sys.argv[3],monotonic_s=sent,kernel={k:kernel[k] for k in ('pid','pgid','start_ticks','state')})))
"""


def query(packet):
    request = {key: packet[key] for key in ('run_id', 'instance_id', 'epoch', 'generation')}
    request.update(version=3, kind='joint_actor_query', request_sequence=time.monotonic_ns() // 1000)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
        peer.bind(('127.0.0.1', 0)); peer.settimeout(2)
        peer.sendto(json.dumps(request).encode(), ('127.0.0.1', 19060))
        raw, sender = peer.recvfrom(8193)
    if sender != ('127.0.0.1', 19060) or len(raw) > 8192:
        raise ValueError('Foreign or oversized UE snapshot')
    response = json.loads(raw)
    if response.get('kind') != 'joint_actor_snapshot' or any(
            response.get(k) != v for k, v in request.items() if k != 'kind'):
        raise ValueError('Uncorrelated UE snapshot')
    return dict(request=request, response=response, observed_unix_s=time.time())


def audit_snapshot(snapshot, packet, truths, authority):
    """Compare actual queried Actor to its retained raw physical tick, not display age."""
    if any(snapshot.get(k) != packet[k] for k in ('run_id', 'instance_id', 'epoch', 'generation')):
        raise ValueError('Snapshot crossed scene identity')
    tick = snapshot['step']
    if type(tick) is not int or not 0 < tick <= authority['tick']:
        raise ValueError('Invalid displayed authoritative step')
    observed = snapshot['observed_vehicles']
    if len(observed) != 2 or {v['vehicle_id'] for v in observed} != {1, 2} or any(
            v['stale'] is not True or v['visible'] is not True or v['step'] != tick for v in observed):
        raise ValueError('Both actual Actors must be visible and stale at the same step')
    actors = snapshot['vehicles']
    if len(actors) != 2 or {v['vehicle_id'] for v in actors} != {1, 2}:
        raise ValueError('Missing or duplicate actual Actors')
    errors = {}
    for actor in actors:
        stack = {1: 'arducopter', 2: 'px4'}[actor['vehicle_id']]
        truth = truths[stack]
        if truth['tick'] != tick:
            raise ValueError('Raw physical sample does not match Actor tick')
        state = truth['state']
        common = dict(run_id=packet['run_id'], sequence=snapshot['sequence'], sim_time_s=tick / 1000)
        value = actor_errors(dict(common, position_ned_m=state[6:9], quaternion_wxyz=state[12:16]), dict(actor, **common))
        if any(value[key] > limit for key, limit in ACTOR_LIMITS.items()):
            raise ValueError('Actual Actor differs from raw physical state')
        errors[stack] = value
    return dict(displayed_tick=tick, frozen_authority_tick=authority['tick'], actor_errors=errors,
                limitation='Query observes rotor yaw but not RPM; RPM is covered only by normal pre-stall Actor ACK.')


def observe_stall(wsl, shared, flying, view, manager, report, output, target):
    epoch_dir = unc(flying['epoch_dir'])
    children = flying['epoch_dir'] + '/children.json'
    packet = report['airborne_actor']['packet']
    record = report['single_fc_stall'] = dict(target=target, before=flying, snapshots=[])
    def signal(name):
        result = subprocess.run([*wsl, 'python3', '-B', '-c', SIGNAL_SCRIPT, children, target, name],
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)
    stopped = False
    try:
        # Prove this build supports an actual query before interfering with the FC.
        record['before_query'] = query(packet)
        stopped = True  # Also attempt scoped resume if SIGSTOP succeeded but observation failed.
        record['injection'] = signal('SIGSTOP')
        save(output / 'report.json', report)
        deadline = time.monotonic() + 9
        while True:
            state = read(shared / 'status.json')
            if state['phase'] == 'faulted': break
            if manager.poll() is not None: raise RuntimeError('Service exited before fault')
            if time.monotonic() > deadline: raise TimeoutError('Real FC input fault')
            view.poll(); time.sleep(.05)
        record['fault'] = state
        if not state['authority']['input_pending'] or not state['authority']['recoverable']:
            raise ValueError('Expected real recoverable input timeout')
        faults = read(epoch_dir / 'faults.json')
        if len(faults) != 1 or faults[0]['type'] != 'InputTimeout':
            raise ValueError('Unexpected physical fault')
        expected_stage = 'ap_input' if target == 'arducopter-fc' else 'px4_input'
        if faults[0]['authority'] != state['authority'] or faults[0]['physical_inflight']['stage'] != expected_stage:
            raise ValueError('Fault is not the deliberately stopped FC input')
        record['raw_fault'] = faults[0]
        for _ in range(2):
            time.sleep(1)
            snapshot = query(packet)
            current = read(shared / 'status.json')
            if current['authority'] != state['authority']:
                raise ValueError('Faulted authority advanced')
            truths = {}
            tails = {}
            for stack in ('arducopter', 'px4'):
                with (epoch_dir / (stack + '-truth.jsonl')).open(encoding='utf-8') as source:
                    for line in source:
                        row = json.loads(line)
                        if row['tick'] == snapshot['response']['step']: truths[stack] = row
                        tails[stack] = row
                if tails[stack]['tick'] != state['authority']['tick']:
                    raise ValueError('Raw physics not frozen at committed authority')
            sample = dict(snapshot=snapshot, status=current, truth=truths, tails=tails)
            record['snapshots'].append(sample)
            save(output / 'report.json', report)  # Retain the failing raw sample before its audit.
            checked = audit_snapshot(snapshot['response'], packet, truths, state['authority'])
            sample['audit'] = checked
            save(output / 'report.json', report)
        first, last = record['snapshots']
        if first['tails'] != last['tails'] or any(first['snapshot']['response'][key] != last['snapshot']['response'][key]
                for key in ('step', 'vehicles', 'observed_vehicles')):
            raise ValueError('Physical or displayed state changed during fault')
        record['status'] = 'pass'
    finally:
        if stopped:
            record['continued'] = signal('SIGCONT')
        save(output / 'report.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', choices=('arducopter-fc', 'px4-fc'), default='arducopter-fc')
    args = parser.parse_args()
    from tools.validate_joint_visual import run
    sources = [Path(__file__), REPO / 'tools/validate_joint_visual.py']
    before = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result = run(args.manifest, args.output, stale_target=args.target)
    result['driver_sha256'] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result['driver_sha256_before'] = before
    if before != result['driver_sha256']:
        result.update(status='failed', error='Driver changed during execution')
    for path in sources:
        (args.output / path.name).write_bytes(path.read_bytes())
    save(args.output / 'report.json', result)
    print(json.dumps({key: result.get(key) for key in ('status', 'error', 'cleanup_error')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
