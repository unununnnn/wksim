"""Prepare/seal a separate mixed-axis candidate; never alter or promote the PV baseline."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot, sha
from verify_ap_pv_candidate import checked_json, verify

BASE = Path('/root/wksim-ap-pv-vn04950x')
BASE_SHA = 'e05e5c9d0b2b576d2cf1751b01557219d6da36998b22ded396ca33d7f5c4db62'
COMMIT = '1511f27194f1dcc3728270883047bdf022b3fd53'
PATCH = REPO/'patches/arducopter/0005-dds-mixed-xy-velocity-z-position.patch'
PROFILE = 'xy_velocity_z_position_yaw_v1'


def baseline():
    verification = verify(BASE/'pv-build.json', BASE_SHA)
    build = checked_json(BASE/'pv-build.json', BASE_SHA)
    source = checked_json(BASE/'pv-source.json', build['source_manifest_sha256'])
    return verification, source['source']


def prepare():
    verified, before = baseline()
    root = Path(tempfile.mkdtemp(prefix='wksim-ap-mixed-', dir='/root'))
    (root/'baseline-pv-build.json').write_bytes((BASE/'pv-build.json').read_bytes())
    (root/'candidate.patch').write_bytes(PATCH.read_bytes())
    shutil.copy2(__file__, root/'prepare_ap_mixed_candidate.py')
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE/'src'), str(root/'src')], check=True)
    source = root/'src'
    if not (source/'.git').is_dir() or (source/'.git').resolve() != source/'.git':
        raise ValueError('Mixed source must own its Git directory')
    top = subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(top).resolve() != source or source_snapshot(source, commit=COMMIT) != before:
        raise ValueError('Mixed source copy escaped or differs from the sealed PV source')
    for options in (('--check', '--whitespace=error'), ('--whitespace=error',)):
        subprocess.run(['git', '-C', str(source), 'apply', *options, str(root/'candidate.patch')], check=True)
    subprocess.run(['git', '-C', str(source), 'diff', '--check'], check=True)
    after = source_snapshot(source, commit=COMMIT)
    if baseline()[1] != before:
        raise ValueError('PV source changed during preparation')
    value = dict(schema_version=1, status='source-only-not-built-not-admitted', profile=PROFILE,
        candidate_root=str(root), baseline_root=str(BASE), baseline_manifest_sha256=BASE_SHA, commit=COMMIT,
        baseline_verification=verified, patch_sha256=sha(PATCH.read_bytes()),
        prepare_sha256=sha(Path(__file__).read_bytes()), source=after)
    path = root/'mixed-source.json'
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True)+'\n')
    return dict(candidate_root=str(root), manifest=str(path), manifest_sha256=sha(path.read_bytes()))


def seal(root, source_sha256):
    root = Path(root)
    if (root.parent != Path('/root') or not re.fullmatch('wksim-ap-mixed-[A-Za-z0-9_-]+', root.name)
            or root.is_symlink() or root.resolve(strict=True) != root):
        raise ValueError('Expected a real /root/wksim-ap-mixed-* candidate')
    manifest = root/'mixed-build.json'
    if manifest.exists() or manifest.is_symlink():
        raise FileExistsError(str(manifest))
    prepared = checked_json(root/'mixed-source.json', source_sha256)
    if (prepared['schema_version'] != 1 or prepared['candidate_root'] != str(root)
            or prepared['status'] != 'source-only-not-built-not-admitted' or prepared['profile'] != PROFILE
            or prepared['baseline_root'] != str(BASE) or prepared['baseline_manifest_sha256'] != BASE_SHA
            or prepared['commit'] != COMMIT or prepared['source'] != source_snapshot(root/'src', commit=COMMIT)
            or prepared['patch_sha256'] != sha(PATCH.read_bytes())
            or prepared['patch_sha256'] != sha((root/'candidate.patch').read_bytes())
            or prepared['prepare_sha256'] != sha(Path(__file__).read_bytes())
            or prepared['prepare_sha256'] != sha((root/'prepare_ap_mixed_candidate.py').read_bytes())):
        raise ValueError('Mixed source/preparer/patch changed during build')
    verified, _ = baseline()
    if prepared['baseline_verification'] != verified or (root/'baseline-pv-build.json').read_bytes() != (BASE/'pv-build.json').read_bytes():
        raise ValueError('Sealed PV baseline changed')
    binary = root/'build/sitl/bin/arducopter'
    if not os.access(binary, os.X_OK):
        raise ValueError('No executable mixed candidate')
    artifacts = {}
    for relative in ('build/sitl/bin/arducopter', 'configure.log', 'build.log'):
        path = root/relative
        if path.is_symlink() or path.resolve(strict=True) != path or not path.stat().st_size:
            raise ValueError('Missing/aliased mixed build artifact: '+relative)
        artifacts[relative] = sha(path.read_bytes())
    value = dict(schema_version=1, status='built-not-admitted', profile=PROFILE, candidate_root=str(root),
        baseline_root=str(BASE), baseline_manifest_sha256=BASE_SHA,
        source_manifest_sha256=sha((root/'mixed-source.json').read_bytes()),
        patch_sha256=prepared['patch_sha256'], artifacts=artifacts, source_unchanged_during_build=True,
        fixed_pv_baseline_unchanged=True, production_admitted=False, flown=False)
    with manifest.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True)+'\n')
    return dict(candidate_root=str(root), manifest=str(manifest), manifest_sha256=sha(manifest.read_bytes()), status=value['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare')
    sealer = sub.add_parser('seal')
    sealer.add_argument('root')
    sealer.add_argument('--source-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare() if args.command == 'prepare' else seal(args.root, args.source_sha256)))
