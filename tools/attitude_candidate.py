"""Read-only admission of the exact bounded #34 independent attitude candidate.

This does not call production preflight, launch nodes, build, or write evidence.
Old shared resources are checked in their own clean environment. Candidate imports
are checked separately, so this API is usable both before and after shell sourcing.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime import joint_profile as joint
from Simulator.wksim_runtime.build_identity import source_snapshot
from Simulator.wksim_runtime.config import validate_config, _unique_object, _invalid_constant
from ap_mixed_candidate import verify as verify_mixed

PROFILE = 'attitude_thrust_v1'
NATIVE = Path('/root/wksim-ap-attitude-hejigg76')
NATIVE_SHA = 'bd8257094e6ab21034e7e6982835d833441d22582c0324b22fe8aa13fa0a4fe4'
CONTROL = Path('/root/wksim-attitude-control-x3_2v4wb')
CONTROL_SHA = '95078a02b863b0307832ae9eb8aad6025a6dd0a88b34506983ae5e3cd43cf8d0'
VERIFICATION_SHA = '4ed5331deac4a20b2fac59d0545df8e5de10ecf6535b4b6d485f94fea30c662c'
# Additional seal of the 52 actual installed files, including launch/setup scripts.
CONTROL_INSTALL_SHA = 'e92ff7938ddbe7c41c19a6ce1774bdb99e5ec493c50dac0f71cb0891ba8b7416'
MESSAGES = Path('/root/wksim-ap-attitude-msgs-qOmnF9fT')
BASE_CONTROL = Path('/root/wksim-joint-control-OEvS3W')
BASE_CONTROL_SHA = 'd9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e'
BASE_NATIVE = Path('/root/wksim-ap-mixed-fhuf05l9')
BASE_NATIVE_SHA = '1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c'
CONTROL_PATCH_SHA = '27224021ddd7f9f1c6078ff3708af76cb436acece33d9a4fb941955a33e63390'
NATIVE_PATCH_SHA = '5db2a0848bd3b46922f049af4db09f339f2978dbfdd8d80f588b52cef93a7669'
STAGE = REPO/'work/ap-attitude-stage-20260909'
STAGE_SHA = '9d838af80767b8617e3c36003175b9595863efd67c15d47671abe822946fe213'
BUDGET_SHA = '9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f'
PACKAGE = Path('ros2/src/prometheus_control')
SETUP_FILES = ['/opt/ros/humble/setup.bash',
    '/root/wksim-dds-VxM6Ni/ros-install/local_setup.bash',
    '/root/wksim-ros2-MUlZd0/install/local_setup.bash',
    str(MESSAGES/'install/local_setup.bash'), str(CONTROL/'install/local_setup.bash')]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_json(path, checksum):
    path = Path(path)
    require(path.resolve(strict=True) == path and not path.is_symlink(), 'Symlinked JSON: '+str(path))
    require(digest(path) == checksum, 'SHA256 differs: '+str(path))
    return json.loads(path.read_text(), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def tree_hashes(root, *, internal_links=False, include_cache=False):
    root = Path(root)
    require(root.is_dir() and root.resolve(strict=True) == root, 'Invalid tree: '+str(root))
    result = {}
    for path in sorted(root.rglob('*')):
        require(path.resolve(strict=True).is_relative_to(root), 'Escaping tree path: '+str(path))
        require(internal_links or not path.is_symlink(), 'Symlinked tree path: '+str(path))
        if path.is_file() and (include_cache or '__pycache__' not in path.parts):
            result[path.relative_to(root).as_posix()] = digest(path)
    require(bool(result), 'Empty tree: '+str(root))
    return result


def check_files(root, expected):
    require(isinstance(expected, dict) and bool(expected), 'Empty file seal')
    for name, checksum in expected.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in name,
                'Invalid sealed relative path: '+name)
        path = root/name
        require(path.resolve(strict=True) == path and not path.is_symlink(), 'Symlinked artifact: '+str(path))
        require(digest(path) == checksum, 'Artifact differs: '+str(path))


def reviewed_files(before, after, entries, kind):
    """Only the reviewed patch deltas may differ; repository Python is not the base."""
    expected = dict(before)
    for entry in entries:
        if entry['kind'] != kind:
            continue
        name = entry['path']
        if kind == 'control':
            name = Path(name).relative_to(PACKAGE).as_posix()
        require(before.get(name) == entry['baseline_sha256'], 'Reviewed baseline differs: '+name)
        expected[name] = entry['staged_sha256']
    require(after == expected, 'Unreviewed '+kind+' package/source delta')


def source_seals():
    """Record all project Python actually imported by this admission process."""
    result = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(REPO) and path.suffix == '.py':
                result[path.relative_to(REPO).as_posix()] = digest(path)
    return dict(sorted(result.items()))


def clean_probe(mode, setup_files):
    # No inherited PYTHONPATH/AMENT/LD_PRELOAD/BASH_ENV can turn the old baseline
    # verification into a candidate-overlay check or contaminate candidate imports.
    environment = dict(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                       HOME='/root', LANG='C.UTF-8', PYTHONDONTWRITEBYTECODE='1')
    script = 'set -eo pipefail\n'+''.join('source '+shlex.quote(p)+'\n' for p in setup_files)
    script += 'exec '+shlex.join(['/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--probe', mode])
    completed = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c', script],
        cwd=REPO, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    require(completed.returncode == 0, mode+' resource probe failed: '+completed.stderr[-5000:])
    return json.loads(completed.stdout, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def check_active_overlays():
    """Check this process's actual imports, ament prefixes and linker search order."""
    packages = dict(prometheus_control=CONTROL/'install/prometheus_control',
        ardupilot_msgs=MESSAGES/'install/ardupilot_msgs',
        px4_msgs=Path('/root/wksim-dds-VxM6Ni/ros-install/px4_msgs'),
        prometheus_msgs=Path('/root/wksim-ros2-MUlZd0/install/prometheus_msgs'),
        wksim_msgs=Path('/root/wksim-ros2-MUlZd0/install/wksim_msgs'))
    origins = {}
    for name, prefix in packages.items():
        joint._overlay(name, prefix)
        origins[name] = str(Path(importlib.import_module(name).__file__).resolve())
    for name in ('command', 'frames', 'native_arducopter', 'native_px4', 'node', 'scene', 'session', 'shaping'):
        module = importlib.import_module('prometheus_control.'+name)
        path = Path(module.__file__).resolve()
        require(path.parent == CONTROL/'install/prometheus_control'/joint.PYTHON/'prometheus_control',
                'Control module imported from another package: '+name)
        origins['prometheus_control.'+name] = str(path)
    from ardupilot_msgs.msg import WksimAttitudeTarget, WksimState
    from rclpy.serialization import serialize_message, deserialize_message
    # Loading the generated type support also exercises the actual dynamic linker.
    for cls in (WksimAttitudeTarget, WksimState):
        instance = cls()
        require(deserialize_message(serialize_message(instance), cls) == instance, 'Generated codec differs')
    for name, prefix in packages.items():
        joint._overlay(name, prefix)
    return dict(import_paths=origins, source_sha256=source_seals(), ros_nodes_started=False)


def native_check(stage):
    record = checked_json(NATIVE/'attitude-build.json', NATIVE_SHA)
    require(record['candidate_root'] == str(NATIVE) and record['messages_root'] == str(MESSAGES)
            and record['status'] == 'built-codec-verified-not-admitted'
            and record['production_admitted'] is False and record['flown'] is False,
            'Native build identity/status differs')
    source = checked_json(NATIVE/'attitude-source.json', record['source_manifest_sha256'])
    require(source['profile'] == PROFILE and source['candidate_root'] == str(NATIVE)
            and source['baseline_root'] == str(BASE_NATIVE) and source['baseline_manifest_sha256'] == BASE_NATIVE_SHA
            and source['patch_sha256'] == NATIVE_PATCH_SHA
            and source['commit'] == '1511f27194f1dcc3728270883047bdf022b3fd53', 'Native source identity differs')
    require((NATIVE/'src/.git').is_dir() and (NATIVE/'src/.git').resolve() == NATIVE/'src/.git',
            'Candidate must own its Git directory')
    require(source_snapshot(NATIVE/'src', commit=source['commit']) == source['source'], 'Native source snapshot differs')
    check_files(NATIVE, record['artifacts'])
    require(tree_hashes(NATIVE/'build/sitl/libraries/AP_DDS/generated') == record['generated_hashes'],
            'Generated native file set differs')
    require(tree_hashes(MESSAGES, internal_links=True, include_cache=True) == record['overlay_hashes'],
            'AP overlay file set differs')
    check_files(REPO, {'patches/arducopter/0006-dds-attitude-thrust.patch': NATIVE_PATCH_SHA,
        'tools/prepare_ap_attitude_candidate.py': source['prepare_sha256'],
        'tools/verify_ap_attitude_candidate.py': record['verifier_sha256'],
        'tools/build-ap-attitude-candidate.sh': record['artifacts']['build-ap-attitude-candidate.sh']})
    check_files(NATIVE, {'prepare_ap_attitude_candidate.py': source['prepare_sha256'],
        'attitude-extra.hwdef': source['extra_hwdef_sha256'], 'candidate.patch': NATIVE_PATCH_SHA,
        'baseline-mixed-build.json': BASE_NATIVE_SHA})
    for name in ('native-build.exit', 'messages-build.exit'):
        require((NATIVE/name).read_text().strip() == '0', 'Failed native/message build')
    require((NATIVE/'messages-root.txt').read_text().strip() == str(MESSAGES), 'Message root changed')
    require('define AP_DDS_WKSIM_ATTITUDE_ENABLED 1' in (NATIVE/'attitude-extra.hwdef').read_text(), 'Attitude build opt-in missing')
    require('#define AP_DDS_WKSIM_ATTITUDE_ENABLED 1' in (NATIVE/'build/sitl/hwdef.h').read_text(), 'Generated attitude opt-in missing')
    baseline = verify_mixed(BASE_NATIVE/'mixed-build.json', BASE_NATIVE_SHA)
    before = checked_json(BASE_NATIVE/'mixed-source.json', baseline['source_manifest_sha256'])['source']
    reviewed_files({k:v['sha256'] for k,v in before['files'].items()},
                   {k:v['sha256'] for k,v in source['source']['files'].items()}, stage['files'], 'ap')
    require(before['deleted_tracked'] == source['source']['deleted_tracked'], 'Native deleted tracked set differs')
    subprocess.run(['git', '-C', str(NATIVE/'src'), 'apply', '--reverse', '--check',
                    str(NATIVE/'candidate.patch')], check=True, capture_output=True)
    binary = NATIVE/'build/sitl/bin/arducopter'
    require(os.access(binary, os.X_OK), 'Native firmware is not executable')
    return dict(manifest_path=str(NATIVE/'attitude-build.json'), manifest_sha256=NATIVE_SHA,
        source_manifest_sha256=record['source_manifest_sha256'], source_files=len(source['source']['files']),
        source_repositories=source['source']['repositories'], artifacts=record['artifacts'],
        generated_hashes=record['generated_hashes'], overlay_hashes=record['overlay_hashes'],
        source_inputs=dict(prepare_sha256=source['prepare_sha256'], verifier_sha256=record['verifier_sha256'],
                           patch_sha256=NATIVE_PATCH_SHA, extra_hwdef_sha256=source['extra_hwdef_sha256']),
        baseline_verification=baseline, binary=dict(path=str(binary), sha256=digest(binary), commit=source['commit']))


def control_check(stage):
    build = checked_json(CONTROL/'attitude-control-build.json', CONTROL_SHA)
    verification = checked_json(CONTROL/'attitude-control-verification.json', VERIFICATION_SHA)
    require(build['root'] == str(CONTROL) and build['base_root'] == str(BASE_CONTROL)
            and build['base_manifest_sha256'] == BASE_CONTROL_SHA and build['native_manifest_sha256'] == NATIVE_SHA
            and build['messages_root'] == str(MESSAGES) and build['overlays'] == SETUP_FILES[:-1]
            and build['patch_sha256'] == CONTROL_PATCH_SHA, 'Control build relationship differs')
    require(build['status'] == 'built-reviewed-patch-candidate-not-admitted'
            and build['production_admitted'] is False and build['flown'] is False and build['build_exit'] == 0
            and verification['status'] == 'built-offline-guards-verified-not-admitted'
            and verification['build_manifest_sha256'] == CONTROL_SHA and verification['root'] == str(CONTROL)
            and verification['ros_nodes_started'] is False and verification['flown'] is False
            and verification['production_admitted'] is False, 'Control build/verification status differs')
    base = checked_json(BASE_CONTROL/'build.json', BASE_CONTROL_SHA)
    require(tree_hashes(BASE_CONTROL/'src/prometheus_control') == build['base_package_hashes'], 'Sealed OEv package changed')
    require(tree_hashes(BASE_CONTROL/'src/prometheus_control/prometheus_control') == base['python_sha256']
            == tree_hashes(Path(base['package'])), 'Sealed OEv Python changed')
    check_files(BASE_CONTROL/'src/prometheus_control', base['build_inputs'])
    check_files(BASE_CONTROL, {'build.log':base['build_log_sha256']})
    package = CONTROL/'install/prometheus_control'/joint.PYTHON/'prometheus_control'
    require(build['package'] == str(package) and verification['installed_import_path'] == str(package), 'Control install path differs')
    require(tree_hashes(CONTROL/'tree'/PACKAGE) == build['patched_package_hashes'], 'Patched control source differs')
    require(tree_hashes(package) == build['installed_python_hashes']
            == tree_hashes(CONTROL/'tree'/PACKAGE/'prometheus_control')
            and len(build['installed_python_hashes']) == 9, 'Installed 9-file control Python set differs')
    reviewed_files(build['base_package_hashes'], build['patched_package_hashes'], stage['files'], 'control')
    for parent in (CONTROL/'reverse-proof', CONTROL/'verification/reverse-proof'):
        require(tree_hashes(parent/PACKAGE) == build['base_package_hashes'], 'Reverse proof differs')
    require(tree_hashes(CONTROL/'verification') == verification['evidence_hashes'], 'Offline verification evidence differs')
    check_files(REPO, verification['tool_hashes'])
    check_files(REPO, {'work/ap-attitude-stage-20260909/control.patch':CONTROL_PATCH_SHA,
                      'tools/build_attitude_control_candidate.py':build['builder_sha256']})
    check_files(CONTROL, {'control.patch':CONTROL_PATCH_SHA, 'build.log':build['build_log_sha256'],
                         'build.sh':build['build_shell_sha256']})
    check_files(NATIVE/'src', verification['native_guards']['source_hashes'])
    require((CONTROL/'build.exit').read_text().strip() == '0', 'Control build failed')
    tests = checked_json(CONTROL/'verification/adapter-results.json', verification['evidence_hashes']['adapter-results.json'])
    require(tests['successful'] is True and tests['count'] == len(tests['tests']) == 21
            and tests['failures'] == tests['errors'] == 0 and tests['ros_nodes_started'] is False
            and tests['sitl_started'] is False, 'Offline regression guards did not pass')
    installed = tree_hashes(CONTROL/'install')
    require(hashlib.sha256(json.dumps(installed, sort_keys=True).encode()).hexdigest() == CONTROL_INSTALL_SHA,
            'Full control install seal differs')
    return dict(root=str(CONTROL), package=str(package), manifest_sha256=CONTROL_SHA,
        verification_sha256=VERIFICATION_SHA, base_manifest_sha256=BASE_CONTROL_SHA,
        base_package_hashes=build['base_package_hashes'], patched_package_hashes=build['patched_package_hashes'],
        installed_python_hashes=build['installed_python_hashes'], installed_files=installed,
        installed_tree_sha256=CONTROL_INSTALL_SHA, verification=verification, offline_tests=tests)


def candidate_config(stack, run_id, profile):
    base = dict(schema_version=1, stack=stack, run_id=run_id, vehicle_id=1, model_profile='quad_x',
        communication='native_dds', control_protocol='session_v1', capabilities=[PROFILE],
        dds_workspace=profile['dds_workspace'], prometheus_workspace=str(CONTROL),
        px4_root=str(Path(profile['manifests']['px4']['path']).parent/'src'), model_library=profile['model_library'])
    if stack == 'arducopter':
        base['ap_candidate'] = str(NATIVE)
    return validate_config(base)


def admit(stack: str, run_id: str):
    result = dict(ok=False, reasons=[], config={}, library='', identities={}, setup_files=[],
        task_profile=PROFILE, experimental=True, production_admitted=False, flown=False,
        children_created=0, ros_nodes_started=False)
    try:
        dependencies_before = source_seals()
        profile = joint.select_profile('joint_quad_dds_v1')
        config = candidate_config(stack, run_id, profile)
        stage = checked_json(STAGE/'stage-manifest.json', STAGE_SHA)
        budget = checked_json(STAGE/'flight-budget.json', BUDGET_SHA)
        native = native_check(stage)
        control = control_check(stage)
        # This executes real fixed-resource checks, never a preflight report or an
        # ok=true fallback. The old flight configuration is never rewritten.
        baseline = clean_probe('baseline', profile['setup_files'])
        require(native['baseline_verification']['baseline_verification']['baseline_manifest_sha256']
                == profile['manifests']['ap']['sha256'], 'Native ancestry differs from fixed AP')
        imports = clean_probe('candidate', SETUP_FILES)
        require({k:imports['import_paths'][k] for k in control['offline_tests']['import_paths']}
                == control['offline_tests']['import_paths'], 'Candidate import proof differs from offline tests')
        ambient = None
        if str(CONTROL/'install/prometheus_control') in os.environ.get('AMENT_PREFIX_PATH', '').split(os.pathsep):
            ambient = check_active_overlays()
        check_files(REPO, dependencies_before)
        identities = dict(ap=native['binary'], px4=baseline['px4'], model_build=baseline['model'],
            model=baseline['model'], baseline=baseline, native=native, control=control,
            candidate_imports=imports, active_process_imports=ambient,
            stage_manifest=dict(path=str(STAGE/'stage-manifest.json'), sha256=STAGE_SHA),
            flight_budget=dict(path=str(STAGE/'flight-budget.json'), sha256=BUDGET_SHA, value=budget),
            setup_sha256={p:digest(p) for p in SETUP_FILES}, source_sha256=source_seals())
        result.update(ok=True, config=config, library=profile['model_library'],
            identities=identities, setup_files=list(SETUP_FILES))
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
        result['reasons'].append(dict(code='attitude_candidate_rejected', message=str(error)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', choices=('baseline', 'candidate'))
    parser.add_argument('--stack', choices=('px4', 'arducopter'))
    parser.add_argument('--run-id')
    args = parser.parse_args()
    dependencies_before = source_seals()
    if args.probe == 'baseline':
        from ap_pv_candidate import _fixed_resources
        report = _fixed_resources(joint.select_profile('joint_quad_dds_v1'))
        report['verification_source_sha256'] = source_seals()
    elif args.probe == 'candidate':
        report = check_active_overlays()
    else:
        if args.stack is None or args.run_id is None:
            parser.error('--stack and --run-id are required')
        report = admit(args.stack, args.run_id)
    check_files(REPO, dependencies_before)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report.get('ok', True) else 2


if __name__ == '__main__':
    raise SystemExit(main())
