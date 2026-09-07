"""Opt-in, read-only experimental admission for tools probes (never flight proof).

Seal after a completed build; pass the printed SHA through an independent channel.
No build or flight process is started. Git commands only inspect source/patches.
The ROS environment must retain the fixed baseline state overlay.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.preflight import preflight
from Simulator.wksim_runtime.build_identity import file_identity, git, sha
from Simulator.wksim_runtime.build_identity import source_snapshot as _source_snapshot

COMMIT = '1511f27194f1dcc3728270883047bdf022b3fd53'
BASELINE_ROOT = '/root/wksim-ap-dds-yaw-state-4Wr27s'
BASELINE_SHA256 = '98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5'
BINARY = 'build/sitl/bin/arducopter'
PATCHES = ('patches/arducopter/0001-dds-global-position-yaw.patch',
           'patches/arducopter/0002-dds-local-state.patch',
           'patches/arducopter/0003-json-integer-clock-interruptible-stop.patch')
BUILD_SCRIPT = 'tools/build-ap-dds-yaw.sh'


def candidate_root(value):
    if not isinstance(value, str) or not re.fullmatch(r'/root/wksim-ap-clock-stop-[A-Za-z0-9_-]+', value):
        raise ValueError('Candidate must be an absolute /root/wksim-ap-clock-stop-* root')
    root = Path(value)
    if not root.is_dir() or root.is_symlink() or root.resolve(strict=True) != root:
        raise ValueError('Candidate root must exist without symlink ancestors')
    return root


def source_snapshot(source, commit=COMMIT):
    return _source_snapshot(source, commit=commit)


def snapshot(root):
    source = root / 'src'
    inputs = {name: file_identity(REPO / name, REPO, nonempty=True)
              for name in (*PATCHES, BUILD_SCRIPT)}
    git(source, 'apply', '--reverse', '--check', *(str(REPO / p) for p in reversed(PATCHES)))
    result = dict(schema_version=1, candidate_root=str(root), commit=COMMIT,
                  baseline_root=BASELINE_ROOT, baseline_binary_sha256=BASELINE_SHA256,
                  source=source_snapshot(source), repository_inputs=inputs,
                  artifacts={name: file_identity(root / name, root, nonempty=True)
                             for name in (BINARY, 'configure.log', 'build.log')})
    if not os.access(root / BINARY, os.X_OK):
        raise ValueError('Candidate binary is not executable')
    return result


def seal(root):
    root = candidate_root(str(root))
    manifest = root / 'wksim-build.json'
    if manifest.exists() or manifest.is_symlink():
        raise FileExistsError(str(manifest))
    record = snapshot(root)
    raw = (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    with manifest.open('xb') as stream:
        stream.write(raw)
    return manifest, sha(raw)


def admit(config, manifest_path=None, manifest_sha256=None):
    baseline = preflight(copy.deepcopy(config))
    if (manifest_path is None) != (manifest_sha256 is None):
        raise ValueError('Provide both manifest path and external SHA256')
    if manifest_path is None:
        return config, baseline
    if baseline.get('ok') is not True or baseline.get('reasons') != []:
        raise ValueError('Fixed baseline preflight rejected: ' + str(baseline))
    if config.get('stack') != 'arducopter' or config.get('ap_candidate') != BASELINE_ROOT:
        raise ValueError('Experimental admission requires the unchanged fixed AP baseline config')
    if not isinstance(manifest_sha256, str) or not re.fullmatch('[0-9a-f]{64}', manifest_sha256):
        raise ValueError('Invalid external manifest SHA256')
    path = Path(manifest_path)
    raw = path.read_bytes()
    if sha(raw) != manifest_sha256:
        raise ValueError('Manifest SHA256 mismatch')
    record = json.loads(raw)
    if not isinstance(record, dict) or type(record.get('schema_version')) is not int or record['schema_version'] != 1:
        raise ValueError('Invalid manifest schema')
    root = candidate_root(record.get('candidate_root'))
    if path != root / 'wksim-build.json' or path.is_symlink():
        raise ValueError('Manifest must belong to the candidate root')
    # Exact comparison checks all fields and independently re-enumerates every set.
    if record != snapshot(root):
        raise ValueError('Candidate snapshot mismatch')
    updated = copy.deepcopy(config)
    updated['ap_candidate'] = str(root)
    return updated, dict(ok=True, experimental=True, production_admitted=False, flown=False,
                         baseline_preflight=baseline, candidate=record,
                         manifest_path=str(path), manifest_sha256=manifest_sha256,
                         ros_overlay_root=BASELINE_ROOT,
                         scope='tools probes only; baseline flight evidence does not prove candidate flight')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seal').add_argument('root')
    args = parser.parse_args(argv)
    try:
        path, checksum = seal(args.root)
        print(json.dumps(dict(manifest_path=str(path), sha256=checksum)))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Candidate rejected: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
