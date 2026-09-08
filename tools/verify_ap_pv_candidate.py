"""Read-only verification of a sealed P+V build; never admit, install or fly it."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from prepare_ap_pv_candidate import BASE, COMMIT, MANIFEST_SHA, PATCH, REPO
from Simulator.wksim_runtime.build_identity import file_identity, git, sha, source_snapshot
from Simulator.wksim_runtime.config import _unique_object


def checked_json(path, expected_sha):
    if not isinstance(expected_sha, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha):
        raise ValueError('An external SHA256 is required')
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError('Manifest must be an absolute file without symlink ancestors')
    raw = path.read_bytes()
    if sha(raw) != expected_sha:
        raise ValueError('Manifest SHA256 differs: ' + str(path))
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError('Manifest must be an object')
    return value


def verify(manifest, expected_sha):
    manifest = Path(manifest)
    record = checked_json(manifest, expected_sha)
    root = manifest.parent
    if (manifest.name != 'pv-build.json' or root.parent != Path('/root') or
            not re.fullmatch('wksim-ap-pv-[A-Za-z0-9_-]+', root.name)):
        raise ValueError('Expected /root/wksim-ap-pv-*/pv-build.json')
    if record.get('status') != 'built-not-admitted' or record.get('candidate_root') != str(root):
        raise ValueError('Build status or candidate root differs')
    if record.get('baseline_manifest_sha256') != MANIFEST_SHA:
        raise ValueError('Unexpected fixed baseline manifest')
    baseline = checked_json(BASE / 'wksim-build.json', MANIFEST_SHA)
    if (root / 'baseline-manifest.json').read_bytes() != (BASE / 'wksim-build.json').read_bytes():
        raise ValueError('Preserved baseline manifest differs')
    prepared = checked_json(root / 'pv-source.json', record['source_manifest_sha256'])
    if (type(prepared.get('schema_version')) is not int or prepared['schema_version'] != 1 or
            prepared.get('status') != 'source-only-not-built-not-admitted' or
            prepared.get('candidate_root') != str(root) or prepared.get('baseline_root') != str(BASE) or
            prepared.get('baseline_manifest_sha256') != MANIFEST_SHA or prepared.get('commit') != COMMIT):
        raise ValueError('Preparation identity differs')
    for path in (PATCH, root / 'candidate.patch'):
        if sha(path.read_bytes()) != record['patch_sha256'] or record['patch_sha256'] != prepared['patch_sha256']:
            raise ValueError('Candidate patch differs')
    for path in (REPO / 'tools/prepare_ap_pv_candidate.py', root / 'prepare_ap_pv_candidate.py'):
        if sha(path.read_bytes()) != prepared['prepare_sha256']:
            raise ValueError('Preparation script differs')
    source = root / 'src'
    if not (source / '.git').is_dir() or (source / '.git').resolve() != source / '.git':
        raise ValueError('Candidate must own an independent Git directory')
    if source_snapshot(source, commit=COMMIT) != prepared['source']:
        raise ValueError('Candidate source differs from prebuild snapshot')
    if source_snapshot(BASE / 'src', commit=COMMIT) != baseline['source']:
        raise ValueError('Fixed baseline source changed')
    # --check never edits the candidate, its index or the fixed source.
    git(source, 'apply', '--reverse', '--check', str(PATCH))
    binary = root / 'build/sitl/bin/arducopter'
    if record.get('binary') != str(binary) or not os.access(binary, os.X_OK):
        raise ValueError('Candidate executable path or permission differs')
    identities = {}
    for name, key in (('build/sitl/bin/arducopter', 'binary_sha256'),
                      ('configure.log', 'configure_log_sha256'), ('build.log', 'build_log_sha256')):
        identity = file_identity(root / name, root, nonempty=True)
        if identity['sha256'] != record[key]:
            raise ValueError('Build artifact differs: ' + name)
        identities[name] = identity
    return dict(status='verified-built-not-admitted', production_admitted=False, flown=False,
                manifest_path=str(manifest), manifest_sha256=expected_sha,
                candidate_root=str(root), commit=COMMIT, artifacts=identities,
                current_source_matches_prebuild_snapshot=True, fixed_baseline_unchanged=True,
                source_files=len(prepared['source']['files']),
                source_repositories=len(prepared['source']['repositories']),
                source_manifest_sha256=record['source_manifest_sha256'],
                patch_sha256=record['patch_sha256'], baseline_manifest_sha256=MANIFEST_SHA,
                verifier_sha256=sha(Path(__file__).read_bytes()),
                scope='Current bytes and preserved build evidence only; no native behavior or flight acceptance')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--sha256', required=True, help='SHA256 obtained from the sealed build handoff')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.manifest, args.sha256), indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps(dict(status='rejected', reason=str(error)), allow_nan=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
