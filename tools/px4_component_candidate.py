"""Seal an explicit PX4 wait-observation candidate derived from the sealed land build."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from Simulator.wksim_runtime.build_identity import source_snapshot,file_identity
from tools import px4_land_candidate as land

REPO=Path(__file__).resolve().parents[1]
PARENT=Path('/root/wksim-px4-land-7RjMjQ/land-build.json')
PARENT_SHA='45c5332cf06a84952189fcf2eabc5d2e15fde9236c704a5c3d6318e7f5dcb3ac'
PATCH='patches/px4/0005-component-wait-tracing.patch'
BUILDER='tools/build-px4-component-timing.sh'
TARGETS=(
 'src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp',
 'platforms/posix/src/px4/common/lockstep_scheduler/src/lockstep_components.cpp',
 'platforms/posix/src/px4/common/lockstep_scheduler/include/lockstep_scheduler/lockstep_components.h',
 'platforms/common/px4_work_queue/WorkQueue.cpp',
 'platforms/common/include/px4_platform_common/px4_work_queue/WorkQueue.hpp')
ENVIRONMENT={'WKSIM_PX4_COMPONENT_TIMING':'1'}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_sources(parent):
    with tempfile.TemporaryDirectory(prefix='wksim-px4-wait-expected-') as tmp:
        root=Path(tmp)
        for name in TARGETS:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((parent/'src'/name).read_bytes())
        subprocess.run(['git','-c','core.autocrlf=false','apply',str(REPO/PATCH)],
                       cwd=root,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} != set(TARGETS):
            raise ValueError('Trace patch changed the allowed source set')
        return {name:(root/name).read_bytes() for name in TARGETS}


def snapshot(root):
    root=Path(root)
    if (root.parent!=Path('/root') or not re.fullmatch(r'wksim-px4-component-[A-Za-z0-9]+',root.name)
            or root.resolve(strict=True)!=root):
        raise ValueError('Expected private PX4 component observation root')
    parent=land.check(PARENT,PARENT_SHA)
    expected=expected_sources(PARENT.parent)
    after=source_snapshot(root/'src',commit=land.COMMIT)
    before=parent['source']
    delta={k for k in before['files'].keys()|after['files'].keys()
           if before['files'].get(k)!=after['files'].get(k)}
    if delta!=set(TARGETS):raise ValueError('Unexpected native source delta: '+str(sorted(delta)))
    for name,data in expected.items():
        if (root/'src'/name).read_bytes()!=data:raise ValueError('Trace source differs: '+name)
    linked=land._linked_libraries(root/'src'/land.BINARY)
    if ('not found' in linked or re.search(land.DEPENDENCY_POLICY['forbidden_pattern'],linked)):
        raise ValueError('Missing or forbidden native dependency')
    runtime=root/'src/build/px4_sitl_default'
    artifacts={p.relative_to(root).as_posix():file_identity(p,root)
               for base in ('bin','etc') for p in sorted((runtime/base).rglob('*')) if p.is_file()}
    return dict(schema='px4-component-timing-v2',root=str(root),source=after,
        parent_manifest=dict(path=str(PARENT),sha256=PARENT_SHA,binary_sha256=parent['binary_sha256']),
        baseline_source=parent['baseline_source'],baseline_binary_sha256=parent['baseline_binary_sha256'],
        binary_sha256=digest(root/'src'/land.BINARY),artifacts=artifacts,
        expected_sources={name:hashlib.sha256(data).hexdigest() for name,data in expected.items()},
        environment=ENVIRONMENT,build_log_sha256=digest(root/'build.log'),
        dependency_check_sha256=digest(root/'dependency-check.log'),
        linked=[line.strip().split(' (0x',1)[0] for line in linked.splitlines()],
        repository_sources={name:digest(REPO/name) for name in (PATCH,BUILDER,'tools/px4_component_candidate.py')},
        semantics='Explicit wait observations only; original polls, component registration/progress/semaphore and all clock barriers retained; not a production promotion')


def check(path,checksum):
    path=Path(path)
    if path.name!='component-build.json' or digest(path)!=checksum:
        raise ValueError('PX4 component manifest identity differs')
    value=json.loads(path.read_text())
    if value!=snapshot(path.parent):raise ValueError('PX4 component candidate changed')
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('seal','check'))
    p.add_argument('path',type=Path);p.add_argument('--sha256');a=p.parse_args()
    if a.command=='seal':
        value=snapshot(a.path);path=a.path/'component-build.json'
        with path.open('x') as f:json.dump(value,f,indent=2)
        print(json.dumps(dict(manifest=str(path),sha256=digest(path))))
    else:
        value=check(a.path,a.sha256);print(json.dumps(dict(verified=True,binary_sha256=value['binary_sha256'])))
