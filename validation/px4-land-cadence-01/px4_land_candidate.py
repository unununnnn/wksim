"""Source/build seal for an opt-in native land observation cadence candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from Simulator.wksim_runtime.build_identity import source_snapshot, file_identity

REPO = Path(__file__).resolve().parents[1]
BASELINE = Path('/root/wksim-px4-state-ONa1Kw/src')
COMMIT = 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4'
PATCH = 'patches/px4/0004-land-observation-cadence.patch'
BUILDER = 'tools/build-px4-land-cadence.sh'
BINARY = 'build/px4_sitl_default/bin/px4'
TARGET = 'src/modules/land_detector/LandDetector.cpp'
ROOT_PARENT = Path('/root')
ROOT_PATTERN = r'wksim-px4-land-[A-Za-z0-9]+'
MANIFEST_PATTERN = r'land-build(?:-v[1-9][0-9]*)?\.json'
DEPENDENCY_POLICY = dict(reject_missing='not found',
                         forbidden_pattern=r'lib(?:gz-|gazebo|ignition|matlab)')


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _linked_libraries(binary):
    return subprocess.check_output(['ldd', str(binary)], text=True)


def expected_patched_source():
    """Rebuild the one allowed outcome: baseline TARGET bytes plus the unique patch.

    The candidate's LandDetector.cpp must equal these bytes exactly, so any other
    edit to the file (even far from the hunk) is rejected, not just delta-listed.
    """
    with tempfile.TemporaryDirectory(prefix='wksim-px4-land-expected-') as work:
        work = Path(work)
        target = work/TARGET
        target.parent.mkdir(parents=True)
        target.write_bytes((BASELINE/TARGET).read_bytes())
        subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', str(REPO/PATCH)],
                       cwd=work, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return target.read_bytes()


def snapshot(root):
    root = Path(root)
    if root.parent != ROOT_PARENT or not re.fullmatch(ROOT_PATTERN, root.name) or root.resolve(strict=True) != root:
        raise ValueError('Expected private PX4 land candidate root')
    before = source_snapshot(BASELINE, commit=COMMIT)
    after = source_snapshot(root/'src', commit=COMMIT)
    delta = {k for k in before['files'].keys() | after['files'].keys()
             if before['files'].get(k) != after['files'].get(k)}
    if delta != {TARGET}:
        raise ValueError('Unexpected native source changes: '+str(sorted(delta)))
    expected = expected_patched_source()
    if (root/'src'/TARGET).read_bytes() != expected:
        raise ValueError('Patched land source mismatch: '+TARGET)
    subprocess.run(['git', '-C', str(root/'src'), 'apply', '--reverse', '--check', str(REPO/PATCH)], check=True)
    linked = _linked_libraries(root/'src'/BINARY)
    if DEPENDENCY_POLICY['reject_missing'] in linked or re.search(DEPENDENCY_POLICY['forbidden_pattern'], linked):
        raise ValueError('Missing or forbidden native dependency')
    runtime = root/'src/build/px4_sitl_default'
    artifacts = {p.relative_to(root).as_posix(): file_identity(p, root)
                 for base in ('bin', 'etc') for p in sorted((runtime/base).rglob('*')) if p.is_file()}
    return dict(schema='px4-land-cadence-v1', root=str(root), source=after,
        baseline_source=before, baseline_binary_sha256=digest(BASELINE/BINARY),
        binary_sha256=digest(root/'src'/BINARY), artifacts=artifacts,
        expected_sources={TARGET: hashlib.sha256(expected).hexdigest()},
        dependency_policy=DEPENDENCY_POLICY,
        build_log_sha256=digest(root/'build.log'),
        dependency_check_sha256=digest(root/'dependency-check.log'),
        linked=[line.strip().split(' (0x', 1)[0] for line in linked.splitlines()],
        repository_sources={name: digest(REPO/name) for name in (PATCH, BUILDER, 'tools/px4_land_candidate.py')},
        semantics='200ms native owner land observation/publish; land-state changes still publish immediately; detection, native timestamps and the 2s consumer freshness check unchanged; no production promotion')


def seal(root, manifest_name='land-build.json'):
    value = snapshot(root)
    if not re.fullmatch(MANIFEST_PATTERN, manifest_name):
        raise ValueError('Use a versioned land-build manifest name')
    path = Path(root)/manifest_name
    with path.open('x') as stream: json.dump(value, stream, indent=2); stream.write('\n')
    return path, digest(path)


def check(path, checksum):
    path = Path(path)
    if digest(path) != checksum or not re.fullmatch(MANIFEST_PATTERN, path.name):
        raise ValueError('PX4 land manifest identity mismatch')
    value = json.loads(path.read_text())
    if value != snapshot(path.parent): raise ValueError('PX4 land candidate changed')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('seal', 'check'))
    parser.add_argument('path', type=Path, help='seal: candidate root; check: manifest file')
    parser.add_argument('--manifest-name', default='land-build.json')
    parser.add_argument('--sha256', help='required for check: sealed manifest checksum')
    args = parser.parse_args()
    if args.command == 'seal':
        path, checksum = seal(args.path, args.manifest_name)
        print(json.dumps(dict(manifest=str(path), sha256=checksum)))
    else:
        if not args.sha256:
            raise ValueError('check requires --sha256')
        value = check(args.path, args.sha256)
        print(json.dumps(dict(manifest=str(args.path), verified=True,
                              binary_sha256=value['binary_sha256'])))
