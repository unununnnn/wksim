"""Explicit experimental installed control identity; never replace production pins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / 'ros2/src/prometheus_control'
PYTHON = 'local/lib/python3.10/dist-packages'
SIMULATOR_FILES = {
    'wksim_runtime': ('__init__.py', 'task.py', 'trajectory_bridge.py'),
    'wksim_planning': ('ego_bspline_bridge.py', 'ego_evaluator.py',
                       'ego_trajectory_adapter.py', 'trajectory_session.py'),
}
BUILD_INPUTS = ('CMakeLists.txt', 'package.xml', 'scripts/prometheus_control_node',
                'scripts/trajectory_bridge_node', 'launch/trajectory_bridge.launch.py',
                'src/rc_take.cpp')
INSTALLED_INPUTS = {
    'scripts/prometheus_control_node': 'lib/prometheus_control/prometheus_control_node',
    'scripts/trajectory_bridge_node': 'lib/prometheus_control/trajectory_bridge_node',
    'launch/trajectory_bridge.launch.py': 'share/prometheus_control/launch/trajectory_bridge.launch.py',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def root_path(value):
    root = Path(value)
    if (root.parent != Path('/root') or not re.fullmatch('wksim-joint-control-[A-Za-z0-9]+', root.name)
            or not root.is_dir() or root.is_symlink() or root.resolve() != root):
        raise ValueError('Requires a real isolated /root/wksim-joint-control-* candidate')
    return root


def snapshot(root):
    staged = root / 'src/prometheus_control'
    installed = root / 'install/prometheus_control' / PYTHON / 'prometheus_control'
    def files(directory):
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError('Missing or symlinked control package')
        result = {}
        for path in sorted(directory.rglob('*')):
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Control package path escapes or is symlinked')
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            if path.suffix != '.py':
                raise ValueError('Unexpected non-Python control package content')
            result[path.relative_to(directory).as_posix()] = digest(path)
        return result
    source = files(PACKAGE / 'prometheus_control')
    if not source or source != files(staged / 'prometheus_control') or source != files(installed):
        raise ValueError('Repository, staged and installed control sources differ')
    simulator = {}
    for package, names in SIMULATOR_FILES.items():
        expected = {name: digest(REPO / 'Simulator' / package / name) for name in names}
        if (expected != files(root / 'Simulator' / package)
                or expected != files(root / 'install/prometheus_control' / PYTHON / 'Simulator' / package)):
            raise ValueError('Repository, staged and installed Simulator sources differ: ' + package)
        simulator.update({package + '/' + name: value for name, value in expected.items()})
    config = {name: digest(PACKAGE / name) for name in BUILD_INPUTS}
    if config != {name: digest(staged / name) for name in config}:
        raise ValueError('Staged control build inputs differ')
    installed_inputs = {name: digest(root / 'install/prometheus_control' / target)
                        for name, target in INSTALLED_INPUTS.items()}
    if installed_inputs != {name: config[name] for name in INSTALLED_INPUTS}:
        raise ValueError('Installed control entry points differ')
    if not (root / 'build.log').stat().st_size:
        raise ValueError('Missing build evidence')
    staged_builder = root / 'build-joint-control.sh'
    if digest(staged_builder) != digest(REPO / 'tools/build-joint-control.sh'):
        raise ValueError('Staged control build script differs')
    return dict(version=2, root=str(root), package=str(installed), python_sha256=source,
                simulator_python_sha256=simulator, build_inputs=config,
                installed_inputs=installed_inputs, build_log_sha256=digest(root / 'build.log'),
                rc_transport_sha256=digest(root/'install/prometheus_control/lib/libwksim_rc_take.so'),
                build_script_sha256=digest(staged_builder),
                scope='experimental continuous joint ROS-time operations; no production admission')


def check(manifest, checksum):
    path = Path(manifest)
    raw = path.read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', checksum or '') or hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError('Explicit control manifest SHA256 differs')
    value = json.loads(raw)
    root = root_path(value['root'])
    if path != root / 'build.json' or path.is_symlink() or value != snapshot(root):
        raise ValueError('Control candidate changed or manifest path is not owned')
    return value


def environment(value):
    prefix = Path(value['root']) / 'install/prometheus_control'
    env = dict(os.environ)
    env['PYTHONPATH'] = str(prefix / PYTHON) + os.pathsep + env.get('PYTHONPATH', '')
    env['AMENT_PREFIX_PATH'] = str(prefix) + os.pathsep + env.get('AMENT_PREFIX_PATH', '')
    return env


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['seal'])
    parser.add_argument('root')
    args = parser.parse_args()
    root = root_path(args.root)
    value = snapshot(root)
    manifest = root / 'build.json'
    with manifest.open('x') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
    print(json.dumps(dict(manifest=str(manifest), sha256=digest(manifest))))
