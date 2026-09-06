"""Read-only Linux /proc verification of groups named by mission evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from validate_product_isolation import identity, group_members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--baseline-case', type=Path, required=True)
    parser.add_argument('--failed-result', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text())
    assert audit['status'] == 'pass'
    groups = {group for run in audit['runs'] for group in run['process_groups']}
    for path in args.failed_result:
        failed = json.loads(path.read_text())
        assert failed['status'] == 'failed' and failed['children_reaped']
        groups.update(child['pgid'] for child in failed['children'].values())
    assert groups and all(type(group) is int and group > 1 for group in groups)
    before = json.loads(args.baseline_case.read_text())['original_before']
    after = identity(before['pid'])
    remaining = group_members(groups)
    report = dict(status='pass' if not remaining and before == after else 'failed',
                  process_groups=sorted(groups), remaining_processes=remaining,
                  original_before=before, original_after=after,
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open('x') as output:
        output.write(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
