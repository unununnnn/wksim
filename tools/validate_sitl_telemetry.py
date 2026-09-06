"""Real two-stack one-way telemetry gate; the formal Prometheus task flies.

This receiver sends no UDP/MAVLink commands, launches no ground station and
does not substitute for QGC UI or explicit control-handoff acceptance.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.telemetry import decode_datagram
from validate_product_isolation import identity, group_members


def last_truth(path):
    if not path.exists():
        return None
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 32768))
        lines = stream.read().split(b'\n')
    for line in reversed(lines[1:-1]):
        try:
            row = json.loads(line)
            return dict(time=row['time'], height_m=-row['vehicle'][8])
        except (ValueError, KeyError):
            continue
    return None


def owned_observer(runtime_pid, config_path):
    """Resolve only a direct child of the live runtime, with exact config argv."""
    parent = Path(f'/proc/{runtime_pid}/task/{runtime_pid}/children')
    for pid in map(int, parent.read_text().split()):
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[:-1]
        if (len(args) == 4 and args[1:3] == [b'-m', b'Simulator.wksim_runtime.telemetry']
                and args[3].decode() == str(config_path)):
            return identity(pid)
    raise RuntimeError('No uniquely identified direct telemetry child')


def run_gate(stack, evidence):
    run_id = 'telemetry-' + stack + '-' + uuid.uuid4().hex[:10]
    config = json.loads((REPO / f'Simulator/wksim_runtime/examples/{stack}-mission.json').read_text())
    config['run_id'] = run_id
    output = evidence / 'runs'
    directory = output / run_id
    socket_directory = Path(tempfile.mkdtemp(prefix=run_id + '-', dir='/tmp'))
    destination = socket_directory / 'native.sock'
    config['telemetry_socket'] = str(destination)
    config_path = evidence / (stack + '.json')
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    expected_id = 241 if stack == 'arducopter' else 22
    receiver, receiver_inode, child = None, None, None
    report = dict(stack=stack, run_id=run_id, status='failed', records=0,
                  steps=[], runtime_result=str(directory / 'result.json'), commands_sent=0,
                  original_before=identity(828), source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

    def bind():
        nonlocal receiver, receiver_inode
        receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        receiver.bind(str(destination))
        destination.chmod(0o600)
        receiver_inode = destination.stat().st_ino
        receiver.setblocking(False)

    def detach():
        nonlocal receiver
        if receiver is not None:
            receiver.close()
            receiver = None
        if destination.exists() and destination.lstat().st_ino == receiver_inode:
            destination.unlink()

    try:
        bind()
        argv = ['bash', str(REPO / 'tools/run-wksim.sh'), str(config_path), '--output-root', str(output)]
        report['argv'] = argv
        with (evidence / (stack + '.log')).open('x') as log, (evidence / (stack + '-native.jsonl')).open('x') as capture:
            child = subprocess.Popen(argv, cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
            report['runtime_pid'] = child.pid
            deadline = time.monotonic() + 340
            heartbeat_armed, message_ids = False, set()
            sequence, disconnected_at, resumed_at, stopped = 0, None, None, False
            resumed_records = 0
            while child.poll() is None:
                now = time.monotonic()
                if now >= deadline:
                    raise TimeoutError('Bounded telemetry flight gate')
                truth = last_truth(directory / 'truth.jsonl')
                if receiver is not None:
                    for _ in range(128):
                        try:
                            raw, sender = receiver.recvfrom(16384)
                        except BlockingIOError:
                            break
                        row = json.loads(raw)
                        if (row['schema_version'] != 1 or row['kind'] != 'native_mavlink_observation'
                                or row['run_id'] != run_id or row['stack'] != stack
                                or row['vehicle_id'] != 1 or row['system_id'] != expected_id
                                or row['component_id'] != 1 or row['sequence'] <= sequence):
                            raise RuntimeError('Wrong run, FC identity or non-increasing observation sequence')
                        messages = decode_datagram(base64.b64decode(row['packet_base64'], validate=True), expected_id)
                        if row['message_ids'] != [m.get_msgId() for m in messages]:
                            raise RuntimeError('Metadata disagrees with independently decoded raw bytes')
                        if sender not in (None, ''):
                            raise RuntimeError('Unexpected bound return path on observer output')
                        sequence = row['sequence']
                        message_ids.update(row['message_ids'])
                        for message in messages:
                            if message.get_type() == 'HEARTBEAT' and message.base_mode & 128:
                                heartbeat_armed = True
                        report['records'] += 1
                        if resumed_at is not None:
                            resumed_records += 1
                        capture.write(json.dumps(dict(receiver_monotonic_s=now, observation=row)) + '\n')
                if (disconnected_at is None and heartbeat_armed and truth is not None
                        and truth['height_m'] > 2 and report['records'] > 10):
                    detach()
                    disconnected_at = now
                    report['steps'].append(dict(event='consumer_detached_airborne', truth=truth, sequence=sequence,
                                                wall_monotonic_s=now))
                    print(stack + ': consumer detached airborne', flush=True)
                elif disconnected_at is not None and resumed_at is None and now - disconnected_at >= 2:
                    previous = report['steps'][-1]['truth']
                    if truth is None or truth['time'] <= previous['time']:
                        raise RuntimeError('Physics stopped while the telemetry consumer was absent')
                    bind()
                    resumed_at = now
                    report['steps'].append(dict(event='new_receiver_same_run', truth=truth, sequence=sequence,
                                                wall_monotonic_s=now))
                    print(stack + ': receiver reopened; physics advanced', flush=True)
                elif resumed_records >= 10 and not stopped:
                    # Exercise optional helper exit after receiving real new data.
                    # This does not inject a flight-control command or kill the FC.
                    target = owned_observer(child.pid, directory / 'config.json')
                    if identity(target['pid']) != target:
                        raise RuntimeError('Telemetry process identity changed before signal')
                    os.kill(target['pid'], signal.SIGTERM)
                    stopped = True
                    report['steps'].append(dict(event='owned_observer_stopped', identity=target, truth=truth,
                                                sequence=sequence, wall_monotonic_s=now))
                    print(stack + ': owned observer stopped; normal task continues', flush=True)
                time.sleep(0.01)
            report['runtime_exit'] = child.returncode
            result = json.loads((directory / 'result.json').read_text())
            report['runtime_result_sha256'] = hashlib.sha256((directory / 'result.json').read_bytes()).hexdigest()
            report['native_message_ids'] = sorted(message_ids)
            report['resumed_records'] = resumed_records
            report['original_after'] = identity(828)
            report['remaining_owned_groups'] = group_members({row['pgid'] for row in result['children'].values()})
            assert report['original_before'] == report['original_after'], 'Unowned original FC changed'
            assert child.returncode == 0 and result['status'] == 'pass', result.get('error')
            assert result['safe_landing'] and result['stop_kind'] == 'landed_stop'
            assert stopped and resumed_records >= 10, 'Missing disconnect/reopen/observer-exit evidence'
            assert result['truth']['final_time'] > report['steps'][-1]['truth']['time']
            assert {0, 30, 33}.issubset(message_ids), 'Missing native heartbeat, attitude or global position'
            assert result['telemetry']['observer_exit'] == 0
            final = result['telemetry']['final_report']
            assert final and final['control_path'] is False and final['counters']['sent'] > 10
            assert final['counters']['dropped'] > 0, 'Consumer-loss drops not observed'
            assert final['counters']['invalid'] == 0 and final['counters']['wrong_peer'] == 0, final
            assert not report['remaining_owned_groups'] and result['children_reaped'] and not result['cleanup_errors']
            report['status'] = 'pass'
    except (Exception, KeyboardInterrupt) as error:
        report['error'] = str(error)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()  # the exact Popen we created; runtime owns teardown
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                report['cleanup_error'] = 'Owned runtime did not exit after SIGTERM; inspect explicitly, no global kill'
        detach()
        socket_directory.rmdir()  # only the exact newly created empty directory
        report['original_final'] = identity(828)
        (evidence / (stack + '-result.json')).write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stack', choices=('px4', 'arducopter', 'both'), default='both')
    args = parser.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='sitl-telemetry-', dir=REPO / 'validation'))
    print(str(evidence), flush=True)
    reports = [run_gate(stack, evidence) for stack in
               (('px4', 'arducopter') if args.stack == 'both' else (args.stack,))]
    report = dict(status='pass' if all(r['status'] == 'pass' for r in reports) else 'failed', results=reports,
                  scope='real native telemetry and optional observer lifecycle, not QGC/UI/control-handoff acceptance')
    (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], evidence=str(evidence))), flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
