"""Recompute frozen Actor checks against retained raw model traces and exits."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.validate_joint_stale import audit_snapshot


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(directory):
    directory = Path(directory)
    report = json.loads((directory/'report.json').read_text(encoding='utf-8'))
    result = json.loads((directory/'run/result.json').read_text(encoding='utf-8'))
    assert report['status'] == 'pass' and report['manager_returncode'] == 0
    assert result['status'] == 'stopped' and all(not e['remaining_group_members'] for e in result['epochs'])
    assert report['result'] == result and not report.get('cleanup_error') and not report.get('retention_error')
    case = report['single_fc_stall']
    assert case['status'] == 'pass' and len(case['snapshots']) == 2
    assert case['injection']['identity'] == case['continued']['identity']
    assert case['injection']['kernel']['state'] == 'T' and case['continued']['kernel']['state'] != 'T'
    epoch = directory/'run/epochs'/case['fault']['epoch']
    assert json.loads((epoch/'faults.json').read_text()) == [case['raw_fault']]
    samples = case['snapshots']
    ticks = {s['snapshot']['response']['step'] for s in samples}
    truths, hashes, tails = {}, {}, {}
    for stack in ('arducopter', 'px4'):
        path = epoch/(stack+'-truth.jsonl')
        hashes[stack] = digest(path)
        rows = {}
        with path.open() as source:
            for line in source:
                row = json.loads(line)
                if row['tick'] in ticks: rows[row['tick']] = row
                tails[stack] = row
        truths[stack] = rows
    checks = []
    for sample in samples:
        snapshot = sample['snapshot']['response']
        raw = {stack: truths[stack][snapshot['step']] for stack in truths}
        assert sample['truth'] == raw and sample['tails'] == tails
        assert sample['status']['authority'] == case['fault']['authority']
        checks.append(audit_snapshot(snapshot, report['airborne_actor']['packet'], raw, case['fault']['authority']))
    assert checks[0] == checks[1]
    for key in ('step', 'vehicles', 'observed_vehicles'):
        assert samples[0]['snapshot']['response'][key] == samples[1]['snapshot']['response'][key]
    assert samples[1]['snapshot']['observed_unix_s'] - samples[0]['snapshot']['observed_unix_s'] >= 1
    for name, sha in report['driver_sha256'].items():
        assert digest(directory/Path(name).name) == sha == report['driver_sha256_before'][name]
    return dict(status='pass', target=case['target'], run_id=result['run_id'],
        report_sha256=digest(directory/'report.json'), result_sha256=digest(directory/'run/result.json'),
        raw_truth_sha256=hashes, checks=checks, process_groups=len(json.loads((epoch/'children.json').read_text())),
        scope='Real single-FC input loss, frozen raw physics and two read-only UE snapshots; controlled fault stop, not a landing case')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    value = audit(args.directory)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(value))
