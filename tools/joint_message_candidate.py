"""Seal the explicit ROS 2 message overlay used by current joint candidates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.preflight import package_digest


PACKAGES = ('prometheus_msgs', 'wksim_msgs')
PYTHON = 'local/lib/python3.10/dist-packages'
EVIDENCE_FILES = ('result.json', 'workspace.txt', 'exit-code.txt', 'source-check.json',
                  'unit-tests.log', 'build.log', 'control-tests.log', 'runtime.log')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root_path(value):
    root = Path(value)
    if (root.parent != Path('/root') or not re.fullmatch(r'wksim-ros2-[A-Za-z0-9]+', root.name)
            or not root.is_dir() or root.is_symlink() or root.resolve() != root):
        raise ValueError('Requires a real isolated /root/wksim-ros2-* workspace')
    return root


def evidence_path(value):
    path = Path(value)
    base = (REPO/'validation').resolve()
    if not path.is_dir() or path.is_symlink() or path.resolve() != path:
        raise ValueError('Requires an owned validation/prometheus-ros2-* evidence directory')
    if not path.is_relative_to(base):
        # Sealed evidence remains owned by its original checkout. A clean
        # worktree of that same repository may verify it without rewriting
        # the immutable manifest or importing code from the dirty checkout.
        def git_path(root, option):
            output = subprocess.check_output(
                ['git', '-C', str(root), 'rev-parse', '--path-format=absolute', option],
                stderr=subprocess.DEVNULL, text=True, timeout=10).strip()
            return Path(output).resolve(strict=True)
        try:
            common = git_path(REPO, '--git-common-dir')
            owned = any(
                parent.name == 'validation'
                and git_path(parent.parent, '--show-toplevel') == parent.parent
                and git_path(parent.parent, '--git-common-dir') == common
                for parent in path.parents)
        except (OSError, subprocess.SubprocessError):
            owned = False
        if not owned:
            raise ValueError('Message evidence belongs to another repository')
    return path


def files(directory):
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('Missing or symlinked message source package')
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Message source path escapes its package')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            result[path.relative_to(directory).as_posix()] = digest(path)
    if not result:
        raise ValueError('Empty message source package')
    return result


def snapshot(root, evidence):
    root, evidence = root_path(root), evidence_path(evidence)
    if (evidence/'workspace.txt').read_text().strip() != str(root):
        raise ValueError('Message build evidence names a different workspace')
    if (evidence/'exit-code.txt').read_text().strip() != '0':
        raise ValueError('Message build did not complete successfully')
    result = json.loads((evidence/'result.json').read_text())
    if result.get('status') != 'pass' or result.get('workspace') != str(root):
        raise ValueError('Message runtime validation did not pass for this workspace')
    packages = {}
    for name in PACKAGES:
        source = files(REPO/'ros2/src'/name)
        if source != files(root/'src'/name):
            raise ValueError('Repository and staged message sources differ: '+name)
        prefix = root/'install'/name
        packages[name] = dict(source_sha256=source, prefix=str(prefix),
                              installed_sha256=package_digest(prefix, complete=True))
    session = packages['wksim_msgs']['source_sha256'].get('msg/SessionState.msg')
    if session != digest(REPO/'ros2/src/wksim_msgs/msg/SessionState.msg'):
        raise ValueError('SessionState source identity differs')
    generated = root/'install/wksim_msgs'/PYTHON/'wksim_msgs/msg/_session_state.py'
    if 'command_high_water' not in generated.read_text():
        raise ValueError('Installed SessionState lacks command_high_water')
    evidence_sha256 = {name:digest(evidence/name) for name in EVIDENCE_FILES}
    return dict(version=1, root=str(root), packages=packages,
                evidence=str(evidence), evidence_sha256=evidence_sha256,
                build_script_sha256=digest(REPO/'tools/build-prometheus-ros2.sh'),
                scope='Explicit current ROS 2 message overlay; historical flight pins remain unchanged')


def check(manifest, checksum):
    path = Path(manifest)
    raw = path.read_bytes()
    if not re.fullmatch(r'[0-9a-f]{64}', checksum or '') or hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError('Explicit message manifest SHA256 differs')
    value = json.loads(raw)
    root = root_path(value['root'])
    if path != root/'message-build.json' or path.is_symlink() or value != snapshot(root, value['evidence']):
        raise ValueError('Message candidate changed or manifest path is not owned')
    return value


def environment(value, base=None):
    env = dict(os.environ if base is None else base)
    prefixes = [Path(value['packages'][name]['prefix']) for name in PACKAGES]
    env['PYTHONPATH'] = os.pathsep.join(
        [str(prefix/PYTHON) for prefix in prefixes] + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    env['AMENT_PREFIX_PATH'] = os.pathsep.join(
        [str(prefix) for prefix in prefixes] + ([env['AMENT_PREFIX_PATH']] if env.get('AMENT_PREFIX_PATH') else []))
    env['LD_LIBRARY_PATH'] = os.pathsep.join(
        [str(prefix/'lib') for prefix in prefixes] + ([env['LD_LIBRARY_PATH']] if env.get('LD_LIBRARY_PATH') else []))
    return env


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('seal', 'check'))
    parser.add_argument('root')
    parser.add_argument('evidence', nargs='?')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    root = root_path(args.root)
    manifest = root/'message-build.json'
    if args.command == 'seal':
        if not args.evidence:
            parser.error('seal requires an evidence directory')
        value = snapshot(root, args.evidence)
        with manifest.open('x') as output:
            json.dump(value, output, indent=2)
            output.write('\n')
        print(json.dumps(dict(manifest=str(manifest), sha256=digest(manifest))))
    else:
        if args.evidence or not args.sha256:
            parser.error('check requires --sha256 and no evidence argument')
        check(manifest, args.sha256)
        print(json.dumps(dict(status='pass', manifest=str(manifest), sha256=args.sha256)))
