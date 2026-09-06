"""Read persisted lifecycle evidence, recompute physical gates and source hashes.

No ROS, FC, physics or display starts. Linux process inventory is read-only.
Includes failed attempts; only accepted flights must match current sources.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.mission_evidence import audit_mission_truth
from validate_mission_lifecycle import audit
from validate_product_isolation import identity, group_members


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = dict(status='pass', runs=[], sources={}, original=identity(828), owned_group_count=0)
    groups = set()
    for directory in args.directories:
        try:
            acceptance = json.loads((directory/'acceptance.json').read_text())
            result_path = Path(acceptance['runtime_result'])
            result = json.loads(result_path.read_text())
            row = dict(directory=str(directory), acceptance_status=acceptance['status'],
                       runtime_status=result['status'], result_sha256=digest(result_path),
                       acceptance_sha256=digest(directory/'acceptance.json'), error=result.get('error'))
            report['runs'].append(row)
            assert result['children_reaped'] and not result['cleanup_errors']
            assert acceptance['original_before'] == acceptance['original_after'] == report['original']
            for child in result['children'].values():
                groups.add(child['pgid'])
            if acceptance['status'] == 'pass':
                row['recomputed'] = audit(result)
                row['physical_audit'] = audit_mission_truth(result_path.with_name('truth.jsonl'), result['task']['mission'])
                for name, expected in result['runtime_sha256'].items():
                    actual = digest(REPO/name)
                    assert actual == expected, 'Source changed since accepted flight: '+name
                    report['sources'][name] = actual
                assert digest(Path(result['fc_binary'])) == result['fc_sha256']
                row['fc_sha256'] = result['fc_sha256']
            else:
                assert result['status'] == 'failed' and not result['safe_landing']
                row['failed_attempt_preserved'] = True
        except Exception as error:
            report['status'] = 'failed'
            report.setdefault('errors', []).append(dict(directory=str(directory), error=str(error)))
    report['owned_group_count'] = len(groups)
    report['remaining_owned_processes'] = group_members(groups)
    if report['remaining_owned_processes']:
        report['status'] = 'failed'
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], runs=len(report['runs']),
                          owned_groups=len(groups), remaining=report['remaining_owned_processes'],
                          errors=report.get('errors', []))), flush=True)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
