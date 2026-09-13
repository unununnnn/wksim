"""Copy this task's own deliverables into the assigned coordination scope.

The assigned scope is ``validation/coordination/ds-group-audit-20260913-01``.
Only the files listed in DELIVERABLES are copied; nothing else in the
coordination tree is read, written, moved or renamed, and the originals under
``validation/ds-group-audit-20260913-01`` are left untouched.

Writes ``MANIFEST.json`` next to the copies: every file's source path, byte size
and sha256, the tool hashes, the archive identity and the registry of
originals, so the copy can be verified without re-running anything.

    python sync_coordination_scope.py            # copy + manifest
    python sync_coordination_scope.py --check    # verify only, no writes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
COORDINATION = os.path.join(WORKSPACE, 'validation', 'coordination',
                            'ds-group-audit-20260913-01')
ARCHIVE = ('/root/wksim-release-acceptance-fe3/validation/'
           'joint-public-flight-rfw9nmbb')

# Source (relative to HERE) -> destination (relative to COORDINATION).
DELIVERABLES = {
    'ds_group_audit.py': 'ds_group_audit.py',
    'gap_map.py': 'gap_map.py',
    'test_ds_group_audit.py': 'test_ds_group_audit.py',
    'test_gap_map.py': 'test_gap_map.py',
    'run_audit.py': 'run_audit.py',
    'sync_coordination_scope.py': 'sync_coordination_scope.py',
    'verify_counterexamples.py': 'verify_counterexamples.py',
    'inspect_counterexamples.py': 'inspect_counterexamples.py',
    'FINDINGS.md': 'FINDINGS.md',
    'README-probes.md': 'README-probes.md',
    'recon_probe.py': 'recon_probe.py',
    'recon_probe2.py': 'recon_probe2.py',
    'scratch_offset.py': 'scratch_offset.py',
    # v2 artifacts (current).  The pre-repair snapshots below are copied as well
    # and are never overwritten by a re-sync, because their names differ.
    'evidence/joint-public-flight-rfw9nmbb-audit-v2.json':
        'evidence/joint-public-flight-rfw9nmbb-audit-v2.json',
    'evidence/joint-public-flight-rfw9nmbb-gap-map-v2.json':
        'evidence/joint-public-flight-rfw9nmbb-gap-map-v2.json',
    'evidence/joint-public-flight-rfw9nmbb-audit-v2.manifest.json':
        'evidence/joint-public-flight-rfw9nmbb-audit-v2.manifest.json',
    'evidence/verification-v2.json': 'evidence/verification-v2.json',
    # pre-repair snapshots, preserved as delivered
    'evidence/joint-public-flight-rfw9nmbb-audit.json':
        'evidence/joint-public-flight-rfw9nmbb-audit.json',
    'evidence/joint-public-flight-rfw9nmbb-gap-map.json':
        'evidence/joint-public-flight-rfw9nmbb-gap-map.json',
    'evidence/joint-public-flight-rfw9nmbb-audit.manifest.json':
        'evidence/joint-public-flight-rfw9nmbb-audit.manifest.json',
}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def build_manifest():
    files = []
    for source_name, dest_name in sorted(DELIVERABLES.items()):
        source = os.path.join(HERE, *source_name.split('/'))
        if not os.path.isfile(source):
            raise SystemExit('missing deliverable: %s' % source)
        files.append({
            'path': dest_name,
            'source': 'validation/ds-group-audit-20260913-01/' + source_name,
            'source_relative': source_name,
            'bytes': os.path.getsize(source),
            'sha256': sha256_file(source),
        })
    manifest = {
        'task': 'ds-group-audit-20260913-01',
        'assigned_scope': 'validation/coordination/ds-group-audit-20260913-01',
        'originals': 'validation/ds-group-audit-20260913-01',
        'archive': ARCHIVE,
        'archive_label': os.path.basename(ARCHIVE),
        'archive_read_only': True,
        'files': files,
        'file_count': len(files),
        'notes': [
            'only this task\'s own deliverables are copied; no other entry in the '
            'coordination tree is written, moved or renamed',
            'the originals under validation/ds-group-audit-20260913-01 are preserved '
            'unchanged; the two trees are byte-identical for these files',
            'no __pycache__ or other build residue is copied',
            'the archive itself is read-only and was never written to',
        ],
    }
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true',
                        help='verify the copies against the manifest without writing')
    parser.add_argument('--scope', default=None,
                        help='coordination directory to write or verify '
                             '(default: <workspace>/validation/coordination/'
                             'ds-group-audit-20260913-01)')
    args = parser.parse_args(argv)
    scope = args.scope or COORDINATION
    manifest = build_manifest()

    if args.check:
        problems = []
        for entry in manifest['files']:
            target = os.path.join(scope, *entry['path'].split('/'))
            if not os.path.isfile(target):
                problems.append('missing: %s' % entry['path'])
                continue
            if os.path.getsize(target) != entry['bytes']:
                problems.append('size differs: %s' % entry['path'])
            if sha256_file(target) != entry['sha256']:
                problems.append('sha256 differs: %s' % entry['path'])
        stale = []
        for root, directories, names in os.walk(scope):
            directories[:] = [name for name in directories if name != '__pycache__']
            for name in names:
                relative = os.path.relpath(os.path.join(root, name), scope)
                relative = relative.replace(os.sep, '/')
                if relative not in DELIVERABLES.values() and relative != 'MANIFEST.json':
                    stale.append(relative)
        if stale:
            problems.append('unexpected files present: %s' % sorted(stale))
        print(json.dumps({'check': 'ok' if not problems else 'failed',
                          'scope': scope,
                          'files': manifest['file_count'],
                          'problems': problems}, sort_keys=True))
        return 0 if not problems else 1

    os.makedirs(scope, exist_ok=True)
    for entry in manifest['files']:
        source = os.path.join(HERE, *entry['source_relative'].split('/'))
        target = os.path.join(scope, *entry['path'].split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.abspath(source) != os.path.abspath(target):
            shutil.copyfile(source, target)
    manifest_path = os.path.join(scope, 'MANIFEST.json')
    with open(manifest_path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps({'scope': 'validation/coordination/ds-group-audit-20260913-01',
                      'resolved_scope': scope,
                      'files': manifest['file_count'],
                      'manifest': 'MANIFEST.json',
                      'manifest_sha256': sha256_file(manifest_path)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
