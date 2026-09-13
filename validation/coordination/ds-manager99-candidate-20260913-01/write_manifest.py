"""Write the SHA-256 manifest for the ds-manager99 candidate module.

    python write_manifest.py
    python write_manifest.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = (
    'candidate.py.txt',
    'candidate.diff',
    'candidate.json',
    'build_candidate.py',
    'verify_candidate.py',
    'verify_reversibility.py',
    'README.md',
    'write_manifest.py',
    'evidence/candidate-verification.json',
    'evidence/reversibility.json',
)
SCOPE = 'validation/coordination/ds-manager99-candidate-20260913-01'
SNAPSHOT_SHA256 = '1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373'


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def build():
    files = []
    for name in FILES:
        target = os.path.join(HERE, *name.split('/'))
        if not os.path.isfile(target):
            raise SystemExit('missing module file: %s' % target)
        files.append({'path': name, 'bytes': os.path.getsize(target),
                      'sha256': sha256_file(target)})
    return {
        'task': 'ds-manager99-candidate-20260913-01',
        'scope': SCOPE,
        'purpose': ('minimal manager-only scheduling candidate: manager target FIFO 50 -> 99, '
                    'not applied to any runtime, staging copy or process'),
        'frozen_base': {
            'path': ('validation/coordination/claude-owned-snapshot-wiring-20260913-01/'
                     'run_joint_flight-owned-snapshot-candidate-v3.py.txt'),
            'sha256': SNAPSHOT_SHA256,
        },
        'candidate_sha256': sha256_file(os.path.join(HERE, 'candidate.py.txt')),
        'diff_sha256': sha256_file(os.path.join(HERE, 'candidate.diff')),
        'status': 'candidate_verified_as_manager_only',
        'acceptance': False,
        'files': files,
        'file_count': len(files),
        'notes': [
            'the change is one priority expression plus four comment lines and one comment '
            'correction; candidate.diff is the authoritative record',
            'the inverse edit reproduces the frozen snapshot byte-for-byte',
            'verified with a fake os ledger: manager target 50 -> 99, every other role and the '
            'whole call ledger unchanged, failure paths unchanged',
            'no performance, latency or acceptance claim; the observed 11-process priorities '
            'are motivation, not causal proof',
            'no native, scheduling, model, ROS, MATLAB or build operation was performed',
            'no new flag, option or framework was added to the runner',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    manifest = build()
    path = os.path.join(HERE, 'MANIFEST.json')
    if args.check:
        if not os.path.isfile(path):
            print(json.dumps({'check': 'failed', 'problems': ['MANIFEST.json missing']}))
            return 1
        recorded = json.load(open(path, 'r', encoding='utf-8'))
        problems = []
        for entry in recorded['files']:
            target = os.path.join(HERE, *entry['path'].split('/'))
            if not os.path.isfile(target):
                problems.append('missing: %s' % entry['path'])
            elif sha256_file(target) != entry['sha256']:
                problems.append('sha256 differs: %s' % entry['path'])
        print(json.dumps({'check': 'ok' if not problems else 'failed',
                          'files': recorded['file_count'], 'problems': problems},
                         sort_keys=True))
        return 0 if not problems else 1
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps({'files': manifest['file_count'],
                      'candidate_sha256': manifest['candidate_sha256'],
                      'manifest_sha256': sha256_file(path)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
