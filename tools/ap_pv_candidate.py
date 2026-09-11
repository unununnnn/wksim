"""Explicit full-XYZ P+V experiment admission; never change production pins or fly."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime import joint_profile as joint
from Simulator.wksim_runtime.config import validate_config
from joint_control_candidate import check as check_control
from verify_ap_pv_candidate import checked_json, verify

PROFILE = 'full_xyz_pv_yaw_v1'
SCOPE = 'Bounded experimental full XYZ position+velocity+yaw only; no mixed axes, flight proof or production admission'


def _pv_record(manifest, checksum):
    path = Path(manifest)
    if (path.name != 'pv-build.json' or path.parent.parent != Path('/root') or
            not re.fullmatch('wksim-ap-pv-[A-Za-z0-9_-]+', path.parent.name)):
        raise ValueError('Expected /root/wksim-ap-pv-*/pv-build.json')
    record = checked_json(path, checksum)
    hashes = ('binary_sha256', 'source_manifest_sha256', 'patch_sha256',
              'baseline_manifest_sha256', 'configure_log_sha256', 'build_log_sha256')
    if set(record) != set(hashes) | {'status', 'candidate_root', 'binary',
                                    'source_unchanged_during_build', 'fixed_baseline_unchanged'}:
        raise ValueError('Unexpected PV build manifest schema')
    if (record['status'] != 'built-not-admitted' or
            record['candidate_root'] != str(path.parent) or
            record['binary'] != str(path.parent / 'build/sitl/bin/arducopter') or
            record['source_unchanged_during_build'] is not True or
            record['fixed_baseline_unchanged'] is not True or
            any(not isinstance(record[key], str) or not re.fullmatch('[0-9a-f]{64}', record[key])
                for key in hashes)):
        raise ValueError('PV build identity or unchanged-source assertions differ')
    return record


def _sealed_control(record):
    """Verify the historical baseline against its own sealed source and build inputs."""
    return joint._control(record, sealed=True)


def _fixed_resources(p):
    """Same fixed shared checks as joint.check_resources, explicit sealed-control branch."""
    if p != joint.select_profile('joint_quad_dds_v1'):
        raise ValueError('Resource descriptor differs from pinned joint profile')
    if platform.system() != 'Linux':
        raise ValueError('Ubuntu 22.04 required')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '22.04':
        raise ValueError('Ubuntu 22.04 required')
    if os.environ.get('ROS_DISTRO') != 'humble':
        raise ValueError('ROS_DISTRO must be humble')
    records = {key: joint._pinned_json(p['manifests'][key]) for key in ('ap', 'px4', 'control')}
    for key, record in records.items():
        root = record.get('candidate_root', record.get('root'))
        if p['manifests'][key]['path'] != str(Path(root) / ('build.json' if key == 'control' else 'wksim-build.json')):
            raise ValueError('Manifest root differs')
    identities = {key: joint._firmware(records[key], key) for key in ('ap', 'px4')}
    identities.update(manifests=p['manifests'], sealed_control=records['control'],
                      sealed_control_package=_sealed_control(records['control']))
    healthy = None
    for pin in p['evidence']:
        flight, audit = joint._pinned_json(pin['result']), joint._pinned_json(pin['audit'])
        if (flight['status'] != 'pass' or not flight['flight_completed'] or not flight['control_shutdown_clean']
                or not flight['source_unchanged'] or flight['cleanup_errors'] or audit['status'] != 'pass'
                or audit['result_sha256'] != pin['result']['sha256']
                or flight['manifest_sha256'] != {k: v['sha256'] for k, v in p['manifests'].items()}
                or flight['control_candidate'] != records['control']):
            raise ValueError('Flight proof does not match joint builds')
        for name, expected in audit['evidence_sha256'].items():
            if joint.digest((REPO / pin['result']['path']).parent / name) != expected:
                raise ValueError('Raw flight evidence differs: ' + name)
        if flight.get('dds_loss_requested') is None:
            healthy = flight
    if healthy is None:
        raise ValueError('Missing healthy joint flight proof')
    model, library = healthy['model_build'], Path(p['model_library'])
    for path, expected in ((library, model['library_sha256']), (Path(model['archive']), model['archive_sha256']),
                           (REPO / 'Simulator/wksim_core/model.cpp', model['wrapper_sha256']),
                           (REPO / 'Simulator/wksim_core/model.py', healthy['source_sha256']['Simulator/wksim_core/model.py'])):
        if joint.digest(path) != expected:
            raise ValueError('Model identity differs: ' + str(path))
    if json.loads(library.with_name('build.json').read_text()) != model:
        raise ValueError('Model build manifest differs')
    identities['model'] = model
    index = json.loads(joint.INDEX.read_text())
    packages = {name: pin for baseline in index['baselines'].values()
                for name, pin in baseline['message_packages'].items() if name != 'prometheus_msgs'}
    packages.update({name: pin for name, pin in index['control_profiles']['session_v1']['installed_packages'].items()
                     if name != 'prometheus_control'})
    for name, pin in packages.items():
        if joint.package_digest(pin['prefix'], complete=pin.get('complete_snapshot', False)) != pin['sha256']:
            raise ValueError('Message content differs: ' + name)
        joint._overlay(name, pin['prefix'])
    joint._overlay('prometheus_control', Path(p['control_workspace']) / 'install/prometheus_control')
    identities['message_packages'] = packages
    for stack, name in (('arducopter', 'ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent'),
                        ('px4', 'agent-install/bin/MicroXRCEAgent')):
        path = (REPO / p['evidence'][-1]['result']['path']).parent / (stack + '-preflight.json')
        old = json.loads(path.read_text())
        while 'baseline_preflight' in old:
            old = old['baseline_preflight']
        expected = old['identities']['agent']['expected_sha256']
        path = Path(p['dds_workspace']) / name
        if joint.digest(path) != expected or not os.access(path, os.X_OK):
            raise ValueError('DDS agent identity differs: ' + stack)
        identities[stack + '_agent'] = dict(path=str(path), sha256=expected)
    for path in p['setup_files']:
        if not Path(path).is_file():
            raise ValueError('Missing setup: ' + path)
    identities['flight_evidence'] = p['evidence']
    return identities


def admit(manifest, sha, control_manifest, control_sha, run_id):
    result = dict(ok=False, experimental=True, production_admitted=False, flown=False,
                  children_created=0, reasons=[], configs={}, model_library='',
                  control_candidate=None, identities={}, task_profile=PROFILE, scope=SCOPE)
    try:
        p = joint.select_profile('joint_quad_dds_v1')
        # Validate run identity and selectors before expensive full source walks.
        base = dict(schema_version=1, run_id=run_id, vehicle_id=1, model_profile='quad_x',
                    communication='native_dds', control_protocol='session_v1',
                    capabilities=['native_position_mission'], dds_workspace=p['dds_workspace'],
                    prometheus_workspace=p['control_workspace'],
                    px4_root=str(Path(p['manifests']['px4']['path']).parent / 'src'), model_library=p['model_library'])
        validate_config(dict(base, stack='px4'))
        record = _pv_record(manifest, sha)
        # Strict JSON/path/hash check supplements check_control's exact current snapshot.
        checked_json(Path(control_manifest), control_sha)
        verified = verify(manifest, sha)
        if verified['baseline_manifest_sha256'] != p['manifests']['ap']['sha256']:
            raise ValueError('PV base differs from the pinned joint AP')
        baseline = _fixed_resources(p)
        control = check_control(control_manifest, control_sha)
        if control['root'] == p['control_workspace']:
            raise ValueError('PV requires a separate experimental control candidate')
        configs = {stack: validate_config(dict(base, stack=stack, **(
            {'ap_candidate': record['candidate_root']} if stack == 'arducopter' else {})))
            for stack in ('arducopter', 'px4')}
        sources = ('tools/ap_pv_candidate.py', 'tools/verify_ap_pv_candidate.py',
                   'tools/joint_control_candidate.py', 'tools/run_joint_flight.py',
                   'Simulator/wksim_runtime/joint_profile.py', 'Simulator/wksim_runtime/config.py',
                   'Simulator/wksim_runtime/runtime.py', 'Simulator/wksim_runtime/build_identity.py')
        result.update(ok=True, configs=configs, model_library=p['model_library'], control_candidate=control,
                      manifest_path=str(manifest), manifest_sha256=sha,
                      control_manifest_path=str(control_manifest), control_manifest_sha256=control_sha,
                      candidate=record, candidate_verification=verified, baseline_profile=p,
                      identities=dict(baseline=baseline, ap_pv=verified, control_candidate=control,
                                      source_sha256={name: joint.digest(REPO / name) for name in sources}),
                      capability=dict(profile=PROFILE, position_axes='xyz', velocity_axes='xyz',
                                      yaw=True, acceleration=False, yaw_rate=False, mixed_axes=False,
                                      arducopter_type_mask=2496),
                      control_binding='Current repository/staged/installed Python bound only to the new explicit candidate; old flown control remains independently sealed')
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.CalledProcessError) as error:
        result['reasons'].append(dict(code='ap_pv_candidate_rejected', message=str(error)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ap-pv-manifest', required=True)
    parser.add_argument('--ap-pv-sha256', required=True)
    parser.add_argument('--control-manifest', required=True)
    parser.add_argument('--control-sha256', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = admit(args.ap_pv_manifest, args.ap_pv_sha256, args.control_manifest, args.control_sha256, args.run_id)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
