"""Corrupt copies of retained flight evidence; never run or substitute a flight."""
import argparse
import copy
import json
from pathlib import Path
import tempfile

from audit_joint_dds_recovery import audit
from audit_joint_flight import digest, lines


def changed_evidence(root, name):
    result = json.loads((root/'result.json').read_text())
    changes = {}
    if name == 'foreign_authorization':
        value = json.loads((root/'recovery-go.json').read_text())
        value['run_id'] = 'another-run'
        changes['recovery-go.json'] = json.dumps(value)
        expected = 'Recovery task authorization differs'
    elif name == 'relaxed_bounds':
        result['bounds']['task_position_error_m'] = 2.0
        expected = 'Predeclared bounds changed'
    elif name == 'wrong_ack_request':
        fresh = copy.deepcopy(result['tasks']['px4'])
        for event in fresh['task']['events']:
            if event['event'] == 'native_ack' and event['accepted']:
                event['request_id'] = 0
        result['tasks']['px4'] = fresh
        changes['px4-recovery/result.json'] = json.dumps(fresh)
        expected = 'Recovery acknowledgement differs from raw DDS'
    elif name == 'tampered_logged_request':
        records = list(lines(root/'px4-recovery/prometheus.jsonl'))
        next(row for row in records if row.get('request_envelope'))['message']['request_id'] = 1
        changes['px4-recovery/prometheus.jsonl'] = ''.join(json.dumps(row)+'\n' for row in records)
        expected = 'Logged public recovery requests differ'
    elif name == 'replayed_request':
        fresh = copy.deepcopy(result['tasks']['px4'])
        fresh['task']['request_envelopes'][0]['request_id'] = 3
        result['tasks']['px4'] = fresh
        changes['px4-recovery/result.json'] = json.dumps(fresh)
        expected = 'Recovery reused old public request identities'
    elif name == 'moved_frozen_model':
        result['dds_recovery']['reconnected_frozen']['models']['arducopter']['state'][6] += .01
        expected = 'Agent loss/restart changed frozen physics'
    else:
        raise ValueError('Unknown evidence corruption: '+name)
    changes['result.json'] = json.dumps(result)
    return changes, expected


def mirrored_copy(source, target, changes, prefix=''):
    """Only changed files are copied; all untouched evidence stays read-only."""
    target.mkdir()
    for path in source.iterdir():
        relative = prefix+path.name
        destination = target/path.name
        if relative in changes:
            destination.write_text(changes[relative])
        elif path.is_dir() and any(name.startswith(relative+'/') for name in changes):
            mirrored_copy(path, destination, changes, relative+'/')
        else:
            destination.symlink_to(path.resolve(), target_is_directory=path.is_dir())


CASES = ('foreign_authorization', 'relaxed_bounds', 'wrong_ack_request',
         'tampered_logged_request', 'replayed_request', 'moved_frozen_model')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    root = args.directory.resolve()
    report = dict(scope=__doc__, evidence=str(root), result_sha256=digest(root/'result.json'),
                  audit_sha256=digest(Path(__file__).with_name('audit_joint_dds_recovery.py')), cases=[])
    for name in (args.case,) if args.case else CASES:
        changes, expected = changed_evidence(root, name)
        originals = {relative:digest(root/relative) for relative in changes}
        error = None
        with tempfile.TemporaryDirectory(prefix='wksim-dds-audit-negative-') as temporary:
            target = Path(temporary)/'evidence'
            mirrored_copy(root, target, changes)
            try:
                audit(target, current=True)
            except Exception as failure:
                error = str(failure)
        unchanged = originals == {relative:digest(root/relative) for relative in changes}
        passed = error is not None and expected in error and unchanged
        row = dict(case=name, status='pass' if passed else 'failed', expected_rejection=expected,
                   actual_rejection=error, original_evidence_unchanged=unchanged)
        report['cases'].append(row)
        print(json.dumps(row), flush=True)
    report['status'] = 'pass' if all(row['status']=='pass' for row in report['cases']) else 'failed'
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(0 if report['status']=='pass' else 1)
