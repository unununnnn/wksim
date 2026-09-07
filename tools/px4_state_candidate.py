"""Explicit experimental PX4 state-cadence admission; never changes the baseline."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess

from ap_clock_candidate import source_snapshot, file_identity, git, sha
from Simulator.wksim_runtime.preflight import preflight

REPO = Path(__file__).resolve().parents[1]
BASELINE = Path('/root/wksim-dependencies/px4-d6f12ad1')
COMMIT = 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4'
BASELINE_BINARY_SHA = '987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd'
BINARY = 'build/px4_sitl_default/bin/px4'
PATCHES = ('patches/px4/0001-estimator-status-cadence.patch',
           'patches/px4/0002-independent-sitl-without-gazebo.patch')
BUILDER = 'tools/build-px4-state-cadence.sh'
CHANGED_SOURCES = {'src/modules/ekf2/EKF2.cpp', 'boards/px4/sitl/default.px4board'}


def candidate_root(value):
    if not isinstance(value,str) or not re.fullmatch(r'/root/wksim-px4-state-[A-Za-z0-9_-]+',value):
        raise ValueError('Expected an explicit /root/wksim-px4-state-* candidate root')
    root = Path(value)
    if root.is_symlink() or not root.is_dir() or root.resolve(strict=True)!=root:
        raise ValueError('Candidate must be an existing private directory without symlink ancestors')
    return root


def snapshot(root):
    source = root/'src'
    if sha((BASELINE/BINARY).read_bytes()) != BASELINE_BINARY_SHA:
        raise ValueError('Fixed PX4 baseline binary changed')
    baseline = source_snapshot(BASELINE, commit=COMMIT)
    actual = source_snapshot(source, commit=COMMIT)
    git(source,'apply','--reverse','--check',*(str(REPO/name) for name in reversed(PATCHES)))
    differences = {name for name in set(baseline['files'])|set(actual['files'])
                   if baseline['files'].get(name)!=actual['files'].get(name)}
    if differences != CHANGED_SOURCES | {'wksim-runtime-files.json'}:
        raise ValueError('Candidate source differs beyond the declared cadence patch: '+str(sorted(differences)))
    runtime = source/'build/px4_sitl_default'
    required = [runtime/'bin/px4',runtime/'bin/px4-alias.sh']
    if any(not path.is_file() for path in required) or not os.access(required[0],os.X_OK):
        raise ValueError('Candidate firmware or generated aliases missing')
    # Generated rc.serial is legitimately empty for this SITL target. Preserve
    # its exact identity; only the executable and aliases must be nonempty.
    artifacts = {path.relative_to(source).as_posix():file_identity(path,source,nonempty=path in required)
                 for base in (runtime/'bin',runtime/'etc') for path in sorted(base.rglob('*'))
                 if path.is_file()}
    dependencies = subprocess.run(['ldd',str(required[0])],check=True,text=True,capture_output=True).stdout
    linked = sorted(line.split()[0] for line in dependencies.splitlines() if '=>' in line)
    if ('not found' in dependencies or any(re.search(r'gz-|gazebo|ignition|matlab',name,re.I) for name in linked)):
        raise ValueError('Candidate still links forbidden or missing runtime libraries: '+str(linked))
    return dict(schema_version=1,candidate_root=str(root),px4_root=str(source),commit=COMMIT,
        baseline_root=str(BASELINE),baseline_binary_sha256=BASELINE_BINARY_SHA,
        baseline_source=baseline,source=actual,changed_sources=sorted(differences),artifacts=artifacts,
        linked_libraries=linked,
        repository_inputs={name:file_identity(REPO/name,REPO,nonempty=True) for name in (*PATCHES,BUILDER)},
        build_log=file_identity(root/'build.log',root,nonempty=True),
        dependency_check=file_identity(root/'dependency-check.log',root,nonempty=True),
        scope='optional PX4 SITL native estimator status cadence; no hardware or default production admission')


def admit(config, manifest_path, checksum):
    baseline = preflight(copy.deepcopy(config))
    if not baseline['ok'] or config.get('stack')!='px4' or config.get('px4_root')!=str(BASELINE):
        raise ValueError('Unchanged fixed PX4 baseline preflight required')
    if not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}',checksum):
        raise ValueError('External PX4 manifest SHA256 required')
    path = Path(manifest_path)
    raw = path.read_bytes()
    if sha(raw)!=checksum:
        raise ValueError('PX4 manifest SHA256 differs')
    record = json.loads(raw)
    root = candidate_root(record.get('candidate_root'))
    if path!=root/'wksim-build.json' or path.is_symlink() or record!=snapshot(root):
        raise ValueError('PX4 candidate manifest/source/runtime identity differs')
    updated = copy.deepcopy(config)
    updated['px4_root'] = record['px4_root']
    return updated,dict(ok=True,experimental=True,production_admitted=False,flown=False,
        baseline_preflight=baseline,candidate=record,manifest_path=str(path),manifest_sha256=checksum,
        identities={'firmware':{'expected_sha256':record['artifacts'][BINARY]['sha256']}},
        scope='bounded candidate experiments only; fixed baseline success does not prove this candidate')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['seal'])
    parser.add_argument('root')
    args = parser.parse_args()
    root = candidate_root(args.root)
    record = snapshot(root)
    path = root/'wksim-build.json'
    raw = (json.dumps(record,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as output:
        output.write(raw)
    print(json.dumps(dict(manifest_path=str(path),sha256=sha(raw))))
