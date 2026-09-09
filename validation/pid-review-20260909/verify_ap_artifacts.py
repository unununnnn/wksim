"""Read-only, streaming hash cross-check of a completed AP strict audit."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--audit', type=Path, required=True)
args = parser.parse_args()
report = json.loads(args.audit.read_text())
assert report['schema'] == 'wksim.pid.audit.v1'
assert report['status'] == 'recorded_evidence_pass'
root = Path(report['run_dir'])
result = json.loads((root/'result.json').read_text())


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            sha.update(data)
    return sha.hexdigest()


for name, expected in report['input_sha256'].items():
    assert digest(root/name) == expected, name
for name, expected in report['checks']['identity'].items():
    assert digest(root/'run-source'/name) == expected, name
    assert result['source_sha256'][name] == expected, name
repo = Path(__file__).resolve().parents[2]
assert digest(repo/'tools/audit_pid_flight.py') == report['auditor_sha256']
for name in ('Simulator/wksim_runtime/pid_task.py', 'Simulator/wksim_control/position_pid.py',
             'Simulator/wksim_runtime/pid-flight-v1.json'):
    assert digest(repo/name) == report['checks']['identity'][name], name
native = report['checks']['native']
assert digest(Path(native['log']['path'])) == native['log']['sha256']
admission = json.loads((root/'admission.json').read_text())
postflight = json.loads((root/'postflight-admission.json').read_text())
identities = admission['identities']
for name in ('ap', 'px4', 'model_build', 'native', 'control', 'setup_sha256'):
    assert identities[name] == postflight['identities'][name], name
assert digest(Path(identities['ap']['path'])) == identities['ap']['sha256'] == result['launched_binary_sha256']
assert digest(Path(admission['library'])) == identities['model_build']['library_sha256']
for name, expected in result['actual_control_sha256'].items():
    assert digest(Path(identities['control']['package'])/name) == expected, name
counts = report['checks']['pid_recomputed']
associations = native['request_associations']
assert len(associations) == sum(counts.values()) == result['task']['external_pid']['pid_updates']
assert len({row['request_id'] for row in associations}) == len(associations)
assert len({row['command_id'] for row in associations}) == len(associations)
assert all(row['state_stamp_s'] <= row['target_stamp_s'] <= row['interval_end_s'] for row in associations)
trace = [json.loads(line) for line in (root/'pid-trace.jsonl').open()]
observations = []
telemetry = {}
for line in (root/'attitude-native.jsonl').open():
    row = json.loads(line)
    if row['kind'] == 'pid_native_observed':
        observations.append(row)
    elif row['kind'] == 'mavlink_decoded' and row['message']['mavpackettype'] == 'ATTITUDE_TARGET':
        telemetry.setdefault(row['message']['time_boot_ms']/1000, []).append(row)
byid = {row['public_request_id']:row for row in trace}
assert len(observations) == len(trace) == len(associations)
assert set(byid) == {row['request_id'] for row in observations}
for observation in observations:
    command = byid[observation['request_id']]
    stamps = observation['telemetry_stamps_s']
    assert len(set(stamps)) >= 2
    assert min(stamps) >= observation['native_target_stamp_s'] >= command['native_state_stamp_s']
    for stamp in stamps:
        assert any(row['monotonic'] <= observation['monotonic'] and
                   abs(row['message']['thrust']-command['public_envelope']['command']['att_ref'][3]) < 1e-6
                   for row in telemetry.get(stamp, []))
assert result['safe_landing'] and result['children_reaped'] and not result['cleanup_errors']
assert result['source_unchanged'] and result['candidate_unchanged']
assert result['status'] == 'observed' and result['stop_kind'] == 'landed_stop'
assert not result['task']['final']['state']['armed']
assert all(value['returncode'] is not None for value in result['children'].values())
processes = {}
for name, child in result['children'].items():
    path = Path('/proc')/str(child['pid'])/'stat'
    exists = path.exists()
    processes[name] = {'pid': child['pid'], 'proc_stat_exists': exists, 'returncode': child['returncode']}
    if exists:
        # PID reuse must not be mistaken for an owned process surviving cleanup.
        current = path.read_text().split(') ', 1)[1].split()[19]
        original = child['proc_stat'].split(') ', 1)[1].split()[19]
        assert current != original, f'owned process still alive: {name}'
        processes[name]['reused_pid'] = True
print(json.dumps(dict(decision='AP recorded evidence verified', run_id=result['run_id'],
    audit_path=str(args.audit), audit_sha256=digest(args.audit),
    input_hashes_checked=len(report['input_sha256']), source_hashes_checked=len(report['checks']['identity']),
    auditor_sha256=report['auditor_sha256'], pid_task_sha256=report['checks']['identity']['Simulator/wksim_runtime/pid_task.py'],
    native_binary_sha256=identities['ap']['sha256'], installed_control_hashes_checked=len(result['actual_control_sha256']),
    protocol_sha256=report['protocol_sha256'], stages=counts, request_associations=len(associations),
    verified_pending_observations=len(observations),
    physics={key:report['checks']['physics'][key] for key in ('ticks','applied_ticks','captured_packets')},
    metrics=report['checks']['metrics'], native_motor_comparisons=native['motor_comparisons'],
    processes=processes, limitations=report['limitations']), indent=2))
