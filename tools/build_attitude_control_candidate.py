"""Build the exact reviewed #34 patch on a sealed OEv copy; no runtime admission."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
BASE = Path('/root/wksim-joint-control-OEvS3W')
BASE_SHA = 'd9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e'
PATCH = REPO/'work/ap-attitude-stage-20260909/control.patch'
PATCH_SHA = '27224021ddd7f9f1c6078ff3708af76cb436acece33d9a4fb941955a33e63390'
NATIVE = Path('/root/wksim-ap-attitude-hejigg76')
NATIVE_SHA = 'bd8257094e6ab21034e7e6982835d833441d22582c0324b22fe8aa13fa0a4fe4'
MSGS = Path('/root/wksim-ap-attitude-msgs-qOmnF9fT')
PACKAGE = Path('ros2/src/prometheus_control')
OVERLAYS = [Path('/opt/ros/humble/setup.bash'),
    Path('/root/wksim-dds-VxM6Ni/ros-install/local_setup.bash'),
    Path('/root/wksim-ros2-MUlZd0/install/local_setup.bash'),
    MSGS/'install/local_setup.bash']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        assert not path.is_symlink(), path
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = digest(path)
    assert result, directory
    return result


def base_check():
    assert digest(BASE/'build.json') == BASE_SHA
    manifest = json.loads((BASE/'build.json').read_text())
    package = BASE/'src/prometheus_control'
    assert hashes(package/'prometheus_control') == manifest['python_sha256']
    assert hashes(Path(manifest['package'])) == manifest['python_sha256']
    assert {p: digest(package/p) for p in manifest['build_inputs']} == manifest['build_inputs']
    assert digest(BASE/'build.log') == manifest['build_log_sha256']
    assert len(manifest['python_sha256']) == 9
    return manifest


def native_check():
    assert digest(NATIVE/'attitude-build.json') == NATIVE_SHA
    value = json.loads((NATIVE/'attitude-build.json').read_text())
    assert value['messages_root'] == str(MSGS)
    for name, checksum in value['overlay_hashes'].items():
        assert digest(MSGS/name) == checksum, name
    return value


def apply(tree, patch, *, reverse=False):
    args = ['git', 'apply', '--whitespace=error'] + (['--reverse'] if reverse else [])
    subprocess.run(args + ['--check', str(patch)], cwd=tree, check=True)
    subprocess.run(args + [str(patch)], cwd=tree, check=True)


def main():
    base = base_check()
    native_check()
    assert digest(PATCH) == PATCH_SHA
    original = hashes(REPO/PACKAGE)
    before = hashes(BASE/'src/prometheus_control')
    root = Path(tempfile.mkdtemp(prefix='wksim-attitude-control-', dir='/root'))
    print(str(root), flush=True)
    tree = root/'tree'
    shutil.copytree(BASE/'src/prometheus_control', tree/PACKAGE)
    shutil.copy2(PATCH, root/'control.patch')
    assert hashes(tree/PACKAGE) == before
    apply(tree, root/'control.patch')
    after = hashes(tree/PACKAGE)
    staged = json.loads((REPO/'work/ap-attitude-stage-20260909/stage-manifest.json').read_text())
    expected = dict(before)
    for entry in staged['files']:
        if entry['kind'] == 'control':
            relative = Path(entry['path']).relative_to(PACKAGE).as_posix()
            assert before[relative] == entry['baseline_sha256']
            assert after[relative] == entry['staged_sha256']
            expected[relative] = entry['staged_sha256']
    assert after == expected
    reverse_tree = root/'reverse-proof'
    shutil.copytree(tree, reverse_tree)
    apply(reverse_tree, root/'control.patch', reverse=True)
    assert hashes(reverse_tree/PACKAGE) == before
    command = ['colcon', '--log-base', str(root/'colcon-log'), 'build', '--base-paths', str(tree/PACKAGE),
        '--packages-select', 'prometheus_control', '--build-base', str(root/'build'),
        '--install-base', str(root/'install'), '--executor', 'sequential',
        '--cmake-args', '-DCMAKE_BUILD_TYPE=Release']
    script = 'set -eo pipefail\n' + ''.join('source '+shlex.quote(str(p))+'\n' for p in OVERLAYS)
    script += 'export PYTHONDONTWRITEBYTECODE=1 CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2\n'
    script += shlex.join(command)+'\n'
    (root/'build.sh').write_text(script)
    with (root/'build.log').open('w') as log:
        result = subprocess.run(['bash', str(root/'build.sh')], cwd=root, stdout=log, stderr=subprocess.STDOUT)
    (root/'build.exit').write_text(str(result.returncode)+'\n')
    assert result.returncode == 0, root/'build.log'
    installed = root/'install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control'
    assert hashes(installed) == hashes(tree/PACKAGE/'prometheus_control')
    assert hashes(tree/PACKAGE) == after
    assert hashes(REPO/PACKAGE) == original
    assert hashes(BASE/'src/prometheus_control') == before
    assert base_check() == base
    value = dict(schema_version=1, status='built-reviewed-patch-candidate-not-admitted', root=str(root),
        base_root=str(BASE), base_manifest_sha256=BASE_SHA, patch_sha256=PATCH_SHA,
        native_manifest_sha256=NATIVE_SHA, messages_root=str(MSGS), overlays=[str(p) for p in OVERLAYS],
        package=str(installed), base_package_hashes=before, patched_package_hashes=after,
        original_repository_package_hashes=original, installed_python_hashes=hashes(installed),
        reverse_patch_restored_sealed_base=True, original_repository_unchanged=True,
        build_exit=0, build_log_sha256=digest(root/'build.log'), build_shell_sha256=digest(root/'build.sh'),
        builder_sha256=digest(__file__), production_admitted=False, flown=False)
    (root/'attitude-control-build.json').write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(manifest=str(root/'attitude-control-build.json'),
        sha256=digest(root/'attitude-control-build.json'))))


if __name__ == '__main__':
    main()
