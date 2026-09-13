"""Source/build seal for an opt-in native home observation heartbeat."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from Simulator.wksim_runtime.build_identity import source_snapshot, file_identity

REPO = Path(__file__).resolve().parents[1]
BASELINE = Path('/root/wksim-px4-state-ONa1Kw/src')
COMMIT = 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4'
PATCH = 'patches/px4/0003-home-observation-heartbeat.patch'
BUILDER = 'tools/build-px4-home-heartbeat.sh'
BINARY = 'build/px4_sitl_default/bin/px4'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(root):
    root = Path(root)
    if root.parent != Path('/root') or not re.fullmatch('wksim-px4-home-[A-Za-z0-9]+', root.name) or root.resolve(strict=True) != root:
        raise ValueError('Expected private PX4 home candidate root')
    before = source_snapshot(BASELINE, commit=COMMIT)
    after = source_snapshot(root/'src', commit=COMMIT)
    delta = {k for k in before['files'].keys() | after['files'].keys()
             if before['files'].get(k) != after['files'].get(k)}
    if delta != {'src/modules/commander/HomePosition.cpp'}:
        raise ValueError('Unexpected native source changes: '+str(sorted(delta)))
    subprocess.run(['git', '-C', str(root/'src'), 'apply', '--reverse', '--check', str(REPO/PATCH)], check=True)
    linked = subprocess.check_output(['ldd', str(root/'src'/BINARY)], text=True)
    if 'not found' in linked or re.search('lib(?:gz-|gazebo|ignition|matlab)', linked):
        raise ValueError('Missing or forbidden native dependency')
    runtime = root/'src/build/px4_sitl_default'
    artifacts = {p.relative_to(root).as_posix(): file_identity(p, root)
                 for base in ('bin', 'etc') for p in sorted((runtime/base).rglob('*')) if p.is_file()}
    return dict(schema='px4-home-heartbeat-v1', root=str(root), source=after,
        baseline_source=before, baseline_binary_sha256=digest(BASELINE/BINARY),
        binary_sha256=digest(root/'src'/BINARY), artifacts=artifacts,
        build_log_sha256=digest(root/'build.log'),
        dependency_check_sha256=digest(root/'dependency-check.log'),
        linked=[line.strip().split(' (0x', 1)[0] for line in linked.splitlines()],
        repository_sources={name: digest(REPO/name) for name in (PATCH, BUILDER, 'tools/px4_home_candidate.py')},
        semantics='500ms native owner observations; home update_count unchanged by heartbeat; no production promotion')


def check(path, checksum):
    path = Path(path)
    if digest(path) != checksum or not re.fullmatch(r'home-build(?:-v[1-9][0-9]*)?\.json', path.name):
        raise ValueError('PX4 home manifest identity mismatch')
    value = json.loads(path.read_text())
    if value != snapshot(path.parent): raise ValueError('PX4 home candidate changed')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('seal',))
    parser.add_argument('root', type=Path)
    parser.add_argument('--manifest-name', default='home-build.json')
    args = parser.parse_args()
    value = snapshot(args.root)
    if not re.fullmatch(r'home-build(?:-v[1-9][0-9]*)?\.json', args.manifest_name):
        raise ValueError('Use a versioned home-build manifest name')
    path = args.root/args.manifest_name
    with path.open('x') as stream: json.dump(value, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(manifest=str(path), sha256=digest(path))))
