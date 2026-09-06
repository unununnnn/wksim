"""Read-only current-source and raw-evidence audit for the #15 product slice."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.mission_evidence import audit_mission_truth
from Simulator.wksim_runtime.mission_plan import resolve_waypoint


def local(value):
    value = str(value).replace('\\', '/')
    prefix = '/mnt/c/Users/PC/Documents/odid编译/wksim/'
    return REPO / value[len(prefix):] if value.startswith(prefix) else Path(value)


def load(path):
    return json.loads(local(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(local(path).read_bytes()).hexdigest()


def audit_run(path, scenario):
    path = local(path)
    run = load(path)
    assert run['children_reaped'] and not run['cleanup_errors']
    assert all(child['returncode'] is not None for child in run['children'].values())
    assert run['preflight']['ok'] and run['preflight']['children_created'] == 0
    assert run['config']['control_protocol'] == 'session_v1'
    for source, expected in run['runtime_sha256'].items():
        assert digest(REPO / source) == expected, 'Source changed after this run: ' + source
    for name, expected in run['product_sha256'].items():
        assert digest(REPO / 'ros2/src/prometheus_control/prometheus_control' / name) == expected
    task, mission = run['task'], run['task']['mission']
    assert mission['plan'] == run['config']['mission']
    assert len(mission['mission_id']) == len(task['control_epoch']) == 32
    envelopes = task['request_envelopes']
    assert len(envelopes) == len(task['sent'])
    previous = 0
    for envelope, payload in zip(envelopes, task['sent']):
        assert envelope['run_id'] == run['run_id'] and envelope['control_epoch'] == task['control_epoch']
        assert envelope['version'] == 1 and envelope['request_id'] > previous
        assert envelope.get('command', envelope.get('setup')) == payload
        previous = envelope['request_id']
    commands = [e for e in envelopes if 'command' in e]
    assert all(a['command']['command_id'] < b['command']['command_id'] for a,b in zip(commands, commands[1:]))
    moves = [e for e in commands if e['command']['agent_cmd'] == 4]
    assert len(moves) == len(mission['waypoints'])
    for envelope, point, planned in zip(moves, mission['waypoints'], mission['plan']['waypoints']):
        assert point['input'] == planned
        command = envelope['command']
        assert point['request_id'] == envelope['request_id'] and point['command_id'] == command['command_id']
        assert command['move_mode'] == (0 if planned['frame'] == 'enu' else 3)
        assert command['position_ref'] == planned['position_m']
        assert abs(command['yaw_ref']-planned['yaw_rad']) < 1e-6  # Actual ROS float32 encoding.
        estimate = resolve_waypoint(planned, point['anchor']['position'], point['anchor']['yaw'])
        assert math.dist(estimate['position_enu_m'], point['target_enu_m']) < 1e-10
        assert abs(estimate['yaw_enu_rad']-point['yaw_enu_rad']) < 1e-10
        assert any(e.get('event') == 'command_accepted' and e.get('request_id') == envelope['request_id']
                   and e.get('command_id') == command['command_id'] for e in task['events'])
    raw = [json.loads(line) for line in (path.parent/'prometheus.jsonl').read_text(encoding='utf-8').splitlines()]
    actual = [r['message'] for r in raw if r.get('request_envelope')]
    assert actual == envelopes
    progress = [json.loads(line) for line in (path.parent/'mission.jsonl').read_text(encoding='utf-8').splitlines()]
    assert progress == mission['progress']
    assert [r['update_sequence'] for r in progress] == list(range(1,len(progress)+1))
    assert all(r['run_id'] == run['run_id'] and r['mission_id'] == mission['mission_id'] for r in progress)
    assert load(path.parent/'mission-status.json') == progress[-1]
    if scenario == 'normal':
        assert run['status'] == 'pass' and mission['state'] == 'completed'
        assert len(moves) == 3 and [e['command']['move_mode'] for e in moves] == [0,0,3]
    elif scenario in ('cancel', 'cancel_ground'):
        assert run['status'] == mission['state'] == 'cancelled'
        assert len(moves) == (0 if scenario == 'cancel_ground' else 2)
        request = load(path.parent/'mission-cancel.json')
        assert request == mission['cancel_request'] and request['mission_id'] == mission['mission_id']
        assert request['run_id'] == run['run_id']
        cancelled = next(r for r in progress if r.get('event') == 'cancel_received')
        assert all(r.get('event') != 'waypoint_running' for r in progress if r['update_sequence'] > cancelled['update_sequence'])
    else:
        assert run['status'] == mission['state'] == 'failed' and not run['safe_landing']
        assert run['stop_kind'] == 'unsuccessful_isolated_teardown'
        assert len(moves) == len(commands) == 2
        if scenario == 'external_mode':
            probe = task['mission_probe']
            assert probe['operator_mode_completed'] and len(probe['operator']) == 1
            assert task['final']['state']['mode'] == ('AUTO.LOITER' if run['stack'] == 'px4' else 'LOITER')
            assert 'lost task control' in run['error']
        else:
            assert scenario == 'invalid_body' and 'ENU position' in run['error']
    if run['status'] in ('pass','cancelled'):
        assert run['safe_landing'] and run['stop_kind'] == 'landed_stop'
        assert not task['final']['state']['armed'] and abs(task['final']['state']['position'][2]) < .3
        assert abs(run['truth']['final_height_m']) < .3
        truth = audit_mission_truth(path.parent/'truth.jsonl', mission)
        assert truth['completed_waypoints'] == run['mission_truth']['completed_waypoints']
    else:
        truth = None
    if scenario != 'normal':
        assert task['mission_probe']['native_commands_published_by_observer'] == 0
    return dict(stack=run['stack'], scenario=scenario, status=run['status'], result=str(path),
                result_sha256=digest(path), run_id=run['run_id'], mission_id=mission['mission_id'],
                request_count=len(envelopes), move_count=len(moves), physical_windows=truth,
                process_groups=[c['pgid'] for c in run['children'].values()])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normal', action='append', required=True)
    parser.add_argument('--case', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = [audit_run(path, 'normal') for path in args.normal]
    for value in args.case:
        acceptance = load(value)
        assert acceptance['status'] == 'pass'
        assert not acceptance['remaining_owned_processes']
        assert acceptance['original_before'] == acceptance['original_after']
        assert acceptance['validator_sha256'] == digest(REPO/'tools/validate_mission_product.py')
        path = acceptance['runtime_result']
        records.append(audit_run(path, load(path)['task']['mission_probe']['scenario']))
    expected = {(stack,scenario) for stack in ('px4','arducopter') for scenario in
                ('normal','cancel','cancel_ground','external_mode','invalid_body')}
    assert {(r['stack'],r['scenario']) for r in records} == expected and len(records) == 10
    result = dict(status='pass', runs=records, auditor_sha256=digest(__file__),
                  scope='10 real product/scenario runs; failed missions are negative-test successes, never safe landings')
    with args.output.open('x', encoding='utf-8') as output:
        output.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(status='pass', audited_runs=len(records), output=str(args.output))))


if __name__ == '__main__':
    main()
