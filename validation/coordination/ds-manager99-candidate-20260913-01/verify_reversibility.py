"""Verify the candidate is exactly reversible: the inverse edit reproduces the snapshot.

    python verify_reversibility.py --out evidence/reversibility.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SNAPSHOT = os.path.join(
    ROOT, 'validation', 'coordination', 'claude-owned-snapshot-wiring-20260913-01',
    'run_joint_flight-owned-snapshot-candidate-v3.py.txt')
CANDIDATE = os.path.join(HERE, 'candidate.py.txt')
SNAPSHOT_SHA256 = '1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373'

ADDED_COMMENT = (
    "        # Manager-only change under test: raise the manager target to FIFO/99,\n"
    "        # just below the 99-priority work-queue/hrtimer service threads observed on\n"
    "        # this host.  The model target stays 40, nice/-10 and the reset-on-fork rule\n"
    "        # are unchanged, so only the manager's own priority differs.\n"
)
NEW_PRIORITY = "        value['target_fifo_priority'] = 99 if role=='manager' else 40\n"
OLD_PRIORITY = "        value['target_fifo_priority'] = 50 if role=='manager' else 40\n"
NEW_COMMENT = "        # and inherit FIFO/99.  The model leader is then explicitly promoted to\n"
OLD_COMMENT = "        # and inherit FIFO/50.  The model leader is then explicitly promoted to\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    findings = []
    snapshot = open(SNAPSHOT, 'r', encoding='utf-8').read()
    candidate = open(CANDIDATE, 'r', encoding='utf-8').read()

    restored = candidate
    # each entry is (text present in the candidate, text it replaces in the snapshot)
    for new, old in ((NEW_PRIORITY, OLD_PRIORITY), (NEW_COMMENT, OLD_COMMENT),
                     (ADDED_COMMENT, '')):
        if restored.count(new) != 1:
            findings.append('candidate does not contain exactly one %r' % new[:60])
        restored = restored.replace(new, old)

    restored_sha = hashlib.sha256(restored.encode('utf-8')).hexdigest()
    matches = restored_sha == SNAPSHOT_SHA256
    if not matches:
        findings.append('inverse edit does not reproduce the snapshot: %s' % restored_sha)

    report = {
        'artifact': 'ds-manager99-candidate-reversibility',
        'snapshot_sha256': SNAPSHOT_SHA256,
        'candidate_sha256': hashlib.sha256(candidate.encode('utf-8')).hexdigest(),
        'restored_sha256': restored_sha,
        'restored_bytes': len(restored.encode('utf-8')),
        'inverse_reproduces_snapshot': matches,
        'status': 'candidate_exactly_reversible' if matches else 'reversibility_failed',
        'findings': findings,
    }
    if args.out:
        directory = os.path.dirname(os.path.abspath(args.out))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(args.out, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    print(json.dumps({'status': report['status'],
                      'restored_sha256': restored_sha,
                      'matches_snapshot': matches, 'out': args.out}, sort_keys=True))
    for item in findings[:4]:
        print('  finding: %s' % item)
    return 0 if matches else 1


if __name__ == '__main__':
    sys.exit(main())
