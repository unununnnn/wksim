"""Explicit experimental installed control identity; never replace production pins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

try:
    from joint_message_candidate import check as check_messages
except ImportError:  # Support package-style imports from the repository root.
    from tools.joint_message_candidate import check as check_messages

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / 'ros2/src/prometheus_control'
PYTHON = 'local/lib/python3.10/dist-packages'
SIMULATOR_FILES = {
    # Explicit import closure for trajectory_bridge and the Route-B transport
    # node.  Keep this list narrow: a runtime-wide copy would weaken the
    # candidate identity boundary and hide accidental dependencies.
    'wksim_runtime': (
        '__init__.py', 'task.py', 'trajectory_bridge.py',
        'planner_command_egress.py', 'planner_transport_node.py',
        'planner_transport_receiver.py', 'planner_transport_pump.py',
        'bspline_tcp_envelope.py', 'planner_scene_binding.py',
    ),
    'wksim_planning': (
        'ego_bspline_bridge.py', 'ego_evaluator.py',
        'ego_trajectory_adapter.py', 'trajectory_session.py',
        'ego_scene_admission.py', 'scene_profile.py',
    ),
}
SIMULATOR_ASSETS = {
    # Frozen protocol inputs are installed as data beside the envelope
    # module.  Keep this list explicit so bytes cannot be silently omitted.
    'wksim_runtime/message_pins': ('ros1_Bspline.msg', 'ros2_Bspline.msg'),
}
BUILD_INPUTS = ('CMakeLists.txt', 'package.xml', 'scripts/prometheus_control_node',
                'scripts/trajectory_bridge_node', 'launch/trajectory_bridge.launch.py',
                'src/rc_take.cpp')
INSTALLED_INPUTS = {
    'scripts/prometheus_control_node': 'lib/prometheus_control/prometheus_control_node',
    'scripts/trajectory_bridge_node': 'lib/prometheus_control/trajectory_bridge_node',
    'launch/trajectory_bridge.launch.py': 'share/prometheus_control/launch/trajectory_bridge.launch.py',
}
MESSAGE_MANIFEST = Path('/root/wksim-ros2-Rzj3Pf/message-build.json')
MESSAGE_SHA256 = '29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219'


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
    def files(directory, exclude_dirs=()):
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError('Missing or symlinked control package')
        result = {}
        for path in sorted(directory.rglob('*')):
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Control package path escapes or is symlinked')
            relative = path.relative_to(directory)
            if relative.parts and relative.parts[0] in exclude_dirs:
                continue
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            if path.suffix != '.py':
                raise ValueError('Unexpected non-Python control package content')
            result[path.relative_to(directory).as_posix()] = digest(path)
        return result
    def assets(directory, names):
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError('Missing or symlinked Simulator asset directory')
        expected_names = set(names)
        result = {}
        for name in names:
            path = directory / name
            if (path.is_symlink() or not path.is_file()
                    or not path.resolve().is_relative_to(directory.resolve())):
                raise ValueError('Missing, symlinked or escaping Simulator asset: ' + str(path))
            result[name] = digest(path)
        if {path.name for path in directory.iterdir()} != expected_names:
            raise ValueError('Unexpected Simulator asset in: ' + str(directory))
        return result
    source = files(PACKAGE / 'prometheus_control')
    if not source or source != files(staged / 'prometheus_control') or source != files(installed):
        raise ValueError('Repository, staged and installed control sources differ')
    simulator = {}
    for package, names in SIMULATOR_FILES.items():
        expected = {name: digest(REPO / 'Simulator' / package / name) for name in names}
        asset_dirs = tuple(
            asset_package.split('/')[1]
            for asset_package in SIMULATOR_ASSETS
            if asset_package.startswith(package + '/')
        )
        if (expected != files(root / 'Simulator' / package, asset_dirs)
                or expected != files(root / 'install/prometheus_control' / PYTHON / 'Simulator' / package,
                                     asset_dirs)):
            raise ValueError('Repository, staged and installed Simulator sources differ: ' + package)
        simulator.update({package + '/' + name: value for name, value in expected.items()})
    simulator_assets = {}
    for package, names in SIMULATOR_ASSETS.items():
        expected = {name: digest(REPO / 'Simulator' / package / name) for name in names}
        staged_assets = assets(root / 'Simulator' / package, names)
        installed_assets = assets(root / 'install/prometheus_control' / PYTHON / 'Simulator' / package, names)
        if expected != staged_assets or expected != installed_assets:
            raise ValueError('Repository, staged and installed Simulator assets differ: ' + package)
        simulator_assets.update({package + '/' + name: value for name, value in expected.items()})
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
    messages = check_messages(MESSAGE_MANIFEST, MESSAGE_SHA256)
    return dict(version=2, root=str(root), package=str(installed), python_sha256=source,
                simulator_python_sha256=simulator, build_inputs=config,
                simulator_asset_sha256=simulator_assets,
                installed_inputs=installed_inputs, build_log_sha256=digest(root / 'build.log'),
                rc_transport_sha256=digest(root/'install/prometheus_control/lib/libwksim_rc_take.so'),
                build_script_sha256=digest(staged_builder),
                sealer_sha256=digest(REPO/'tools/joint_control_candidate.py'),
                message_manifest_path=str(MESSAGE_MANIFEST),
                message_manifest_sha256=MESSAGE_SHA256,
                message_candidate=messages,
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
