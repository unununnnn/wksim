"""Write SHA256SUMS and manifest.json for this exclusive-write audit directory.

Read-only over the retained originals; writes only SHA256SUMS and manifest.json here.
Run this LAST: SHA256SUMS is the content-addressed endpoint of the deliverable and is
not itself referenced by any file it hashes, so there is no self-reference.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DELIVERABLES = ['audit.md', 'audit.json', 'build_audit.py', 'render_md.py',
                'verify_inputs.py', 'write_manifest.py', '.gitattributes']


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


files = []
for name in DELIVERABLES:
    path = HERE / name
    entry = {'path': name, 'exists': path.is_file()}
    if path.is_file():
        entry['sha256'] = sha256(path)
        entry['size_bytes'] = path.stat().st_size
    files.append(entry)

sha_lines = ['# SHA256SUMS - ds-g6-budget-evidence-20260913-01 (exclusive-write audit deliverable)']
for entry in files:
    sha_lines.append('%s  %s' % (entry['sha256'], entry['path']))
(HERE / 'SHA256SUMS').write_text('\n'.join(sha_lines) + '\n', encoding='utf-8', newline='\n')
sums_sha = sha256(HERE / 'SHA256SUMS')

manifest = {
    'schema': 'wksim.g6-budget-evidence-manifest.v1',
    'audit_id': 'ds-g6-budget-evidence-20260913-01',
    'scope': ('Exclusive-write audit deliverable for the G6 per-quantity budget evidence chain. '
              'SHA256SUMS records this directory only; audit.json records the retained originals '
              'this audit cites.'),
    'checkout': {
        'cwd': 'C:/Users/PC/Documents/odid编译/wksim',
        'branch': 'main',
        'head': 'abf1ac3934e3ad8dcfbcb5c7b4dc49712d407c18',
        'architecture_ancestor': 'f333316e6efa6b299b4288a9d91fb2bccedfb9d6',
        'architecture_ancestor_exit_code': 0,
    },
    'deliverable_hashes': files,
    'sha256sums': {'path': 'SHA256SUMS', 'sha256': sums_sha},
    'no_epsilon_approved': True,
    'g6_acceptance': False,
    'physical_accuracy': False,
    'write_scope': ('this directory only; the shared ledger, the frozen R1 contract and every '
                    'existing G6 file are untouched'),
    'regeneration_order': ['build_audit.py', 'render_md.py', 'verify_inputs.py', 'write_manifest.py'],
}
(HERE / 'manifest.json').write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
    encoding='utf-8', newline='\n')
print((HERE / 'SHA256SUMS').read_text(encoding='utf-8'))
