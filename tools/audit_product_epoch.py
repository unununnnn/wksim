"""Read-only current-source audit of #13/#14 evidence; optional exclusive new report."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from validate_product_evidence import audit as visual_audit

REPO = Path(__file__).resolve().parents[1]
WSL_REPO = '/mnt/c/Users/PC/Documents/odid编译/wksim'


def local(value):
    value = str(value).replace('\\', '/')
    if value.startswith(WSL_REPO + '/'):
        return REPO / value[len(WSL_REPO) + 1:]
    return Path(value)


def sha(path):
    return hashlib.sha256(local(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(local(path).read_text(encoding='utf-8'))


def flight(path, restart):
    path = local(path)
    run = load(path)
    assert run['status'] == 'pass' and run['safe_landing'] and run['children_reaped']
    assert run['stop_kind'] == 'landed_stop' and not run['cleanup_errors']
    assert run['config']['control_protocol'] == run['task']['protocol'] == 'session_v1'
    assert run['preflight']['ok'] and run['preflight']['children_created'] == 0
    assert all(c['returncode'] is not None for c in run['children'].values())
    for source, expected in run['runtime_sha256'].items():
        assert sha(REPO / source) == expected, source
    for name, expected in run['product_sha256'].items():
        assert sha(REPO / 'ros2/src/prometheus_control/prometheus_control' / name) == expected, name
    task = run['task']
    envelopes = task['request_envelopes']
    assert len(envelopes) == len(task['sent']) == (7 if restart else 6)
    watermarks = {}
    for envelope, payload in zip(envelopes, task['sent']):
        epoch, number = envelope['control_epoch'], envelope['request_id']
        assert len(epoch) == 32 and envelope['version'] == 1 and envelope['run_id'] == run['run_id']
        assert number > watermarks.get(epoch, 0)
        watermarks[epoch] = number
        assert envelope.get('setup', envelope.get('command')) == payload
    assert len(watermarks) == (2 if restart else 1)
    states, previous = 0, {}
    for line in (path.parent / 'prometheus.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row.get('topic') != '/uav1/prometheus/v2/state':
            continue
        msg = row['message']
        assert msg['run_id'] == run['run_id'] and msg['source_clock'] == 'fc_boot'
        assert msg['control_epoch'] in watermarks
        if not msg['source_received_valid']:
            continue
        received, published = msg['source_received_monotonic_s'], msg['published_monotonic_s']
        assert math.isfinite(received) and math.isfinite(published) and 0 < received <= published
        stamp = msg['state']['header']['stamp']
        source = stamp['sec'] * 10**9 + stamp['nanosec']
        if source == 0:
            # PX4 can receive position before its first attitude. The assembled
            # public state is then explicitly invalid, with no source stamp yet.
            assert not msg['state']['connected'] and not msg['state']['odom_valid']
            continue
        key = msg['control_epoch'], source
        if key in previous:
            assert previous[key] == received, 'Repeated native source sample was re-stamped'
        previous[key] = received
        states += 1
    assert states > 30
    truth = [json.loads(s) for s in (path.parent / 'truth.jsonl').read_text().splitlines()]
    count = run['truth']['records']
    assert len(truth) >= count
    assert all(a['time'] < b['time'] for a, b in zip(truth, truth[1:]))
    # Runtime takes its grounded-stop snapshot before reaping children. Physics
    # can still append ground records during that bounded cleanup; retain them.
    assert truth[count-1]['time'] == run['truth']['final_time']
    assert all(abs(r['vehicle'][8]) < .3 for r in truth[count:])
    positions = [r['vehicle'][6:9] for r in truth[:count]]
    assert max(-p[2] for p in positions) == run['truth']['max_height_m'] >= 2.5
    assert min(math.dist(p, [3, 2, -3]) for p in positions) == run['truth']['min_waypoint_error_m'] <= .5
    assert abs(positions[-1][2]) < .3
    assert bool(task['control_restarts']) == restart
    if restart:
        change, = task['control_restarts']
        assert change['old_pid'] == run['children']['control']['pid']
        assert change['new_pid'] == run['children']['control-restarted']['pid'] != change['old_pid']
        assert change['physics_pid'] == run['children']['physics']['pid']
        assert change['fc_pid'] == run['children']['fc']['pid']
        assert change['model_time_after'] > change['model_time_before']
        assert change['old_epoch'] != change['new_epoch'] == task['control_epoch']
        assert set(watermarks) == {change['old_epoch'], change['new_epoch']}
        probe = task['epoch_probe']
        assert len(probe['checks']) == (8 if run['stack'] == 'px4' else 7)
        assert all(c['status'] == 'pass' for c in probe['checks'])
        assert all(c.get('new_native_commands', 0) == c.get('new_native_targets', 0) == 0 for c in probe['checks'])
        assert all(e.get('accepted', True) for e in task['events'] if e['event'] == 'native_ack')
        assert not any(e['event'] == 'control_revoked' for e in task['events'])
    return dict(stack=run['stack'], result=str(path), sha256=sha(path), truth=run['truth'],
                raw_truth_records=len(truth), ground_records_during_cleanup=len(truth)-count,
                session_state_records=states, restarts=task['control_restarts'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolation', required=True, type=Path)
    parser.add_argument('--epochs', required=True, nargs=2, type=Path)
    parser.add_argument('--visuals', required=True, nargs=2, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    isolation = load(args.isolation)
    assert isolation['status'] == 'pass' and not isolation['remaining_owned_processes']
    assert sha(REPO / 'tools/validate_product_isolation.py') == isolation['validator_sha256']
    assert isolation['original_before'] == isolation['original_after']
    isolated = [flight(p, False) for p in isolation['results'].values()]
    resources = [load(p)['resources'] for p in isolation['results'].values()]
    for key in ('network_namespace', 'ipc_namespace', 'shm_device'):
        assert len({r[key] for r in resources}) == 2
    stopped = isolation['normal_stop']
    assert any(s['wall'] >= stopped['wall'] and s['alive'][stopped['survivor']]
               and s['times'][stopped['survivor']] is not None
               and s['times'][stopped['survivor']] > stopped['time'] + 1 for s in isolation['samples'])
    assert isolation['startup_refusal']
    epochs = []
    for path in args.epochs:
        gate = load(path)
        assert gate['status'] == 'pass' and not gate['remaining_owned_processes']
        assert gate['validator_sha256'] == sha(REPO / 'tools/validate_control_restart.py')
        assert gate['original_before'] == gate['original_after'] == isolation['original_before']
        epochs.append(flight(gate['runtime_result'], True))
    assert {r['stack'] for r in epochs} == {'px4', 'arducopter'}
    report = dict(status='pass', scope='independent runs and explicit ground control restart, not Full or joint time',
                  current_source_checked=True, isolation=isolated, epochs=epochs,
                  visuals=visual_audit(args.visuals),
                  auditor_sha256=sha(Path(__file__)))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
