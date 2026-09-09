"""Read-only independent hash/terminal/reset and complete live-audit recheck."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import audit_hex_live as live

directory = ROOT/'validation/25-px4-reset-live-20260909-02'
flight = live.read(directory/'flight-audit.json')
stored = live.read(directory/'reviewed-audit.json')
assert flight['passed'] and not flight['errors'] and stored['passed']
assert live.audit(directory, directory/'render-review.json') == stored


def native_path(path):
    return Path(r'\\wsl.localhost\Ubuntu-22.04'+path.replace('/', '\\')) if sys.platform == 'win32' else Path(path)


counts = {}
for report in (flight, flight['checks']['cold_reset']['parent_audit']):
    root = native_path(report['root'])
    assert report['passed'] and not report['errors']
    for name, expected in report['inputs_sha256'].items():
        path = (root/name).resolve()
        assert path.is_relative_to(root.resolve()) and live.digest(path) == expected, name
    result = live.read(root/'result.json')
    for name, expected in result['source_sha256'].items():
        assert live.digest(root/'run-source'/name) == expected, name
    counts[result['run_id']] = dict(input_hashes=len(report['inputs_sha256']), source_hashes=len(result['source_sha256']))
root = native_path(flight['root'])
result = live.read(root/'result.json')
link = result['cold_reset_from']
parent = live.read(native_path(link['path']))
assert live.digest(native_path(link['path'])) == link['sha256'] == flight['checks']['cold_reset']['parent_result_sha256']
assert result['run_id'] != parent['run_id'] and result['task']['control_epoch'] != parent['task']['control_epoch']
assert result['admission']['configuration_identity'] == parent['admission']['configuration_identity']
assert result['model_initialization']['initial_tick'] == parent['model_initialization']['initial_tick'] == 0
assert result['source_unchanged'] and result['candidate_unchanged'] and result['parent_unchanged']
assert result['safe_landing'] and result['children_reaped'] and not result['cleanup_errors']
assert result['processes_absent_after_stop'] and result['stop_kind'] == 'landed_stop'
end = None
with (root/'physics-1ms.jsonl').open() as stream:
    for line in stream:
        row = json.loads(line)
        if row['kind'] == 'end':
            assert end is None
            end = row
assert end['status'] == 'interrupted_or_failed' and end['error_type'] == 'InterruptedError'
assert end['error'] == 'Owned Hex physics process retired'
manifest = live.read(directory/'manifest.json')
module = Path(manifest['commands']['ue'][1]).parent/'Binaries/Win64/UnrealEditor-WksimVisual.dll'
assert live.digest(module) == manifest['module_sha256'] == live.MODULE_SHA
summary = dict(decision='PX4 Hex cold-reset/live evidence PASS', run_id=result['run_id'],
    counts=counts, parent_result_sha256=link['sha256'], expected_terminal=end,
    configuration_identity=result['admission']['configuration_identity'],
    control_epoch=result['task']['control_epoch'], parent_control_epoch=parent['task']['control_epoch'],
    module_sha256=manifest['module_sha256'], protocol_sha256=result['protocol_sha256'],
    ack_count=stored['ack_count'], phases=stored['phase_ack_counts'], maxima=stored['maxima'],
    raw_physics=flight['checks']['physics'], render_review=live.read(directory/'render-review.json'),
    children={name:dict(pid=value['pid'],returncode=value['returncode']) for name,value in result['children'].items()},
    evidence_sha256={name:live.digest(directory/name) for name in ('flight-audit.json','automatic-audit.json',
        'render-review.json','reviewed-audit.json','completion.json','manifest.json')})
print(json.dumps(summary, indent=2))
