"""Read-only mixed-axis build verification and explicit bounded experimental admission."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot, sha, git
from Simulator.wksim_runtime.config import validate_config
from prepare_ap_mixed_candidate import BASE, BASE_SHA, COMMIT, PATCH, PROFILE, baseline
from verify_ap_pv_candidate import checked_json
from ap_pv_candidate import _fixed_resources
from Simulator.wksim_runtime import joint_profile as joint
from joint_control_candidate import check as check_control

PV_PROFILE = 'full_xyz_pv_yaw_v1'
FINAL_AP_SHA = '1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c'
FINAL_CONTROL_SHA = 'd9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e'


def verify(manifest, checksum):
    path = Path(manifest)
    if (path.name != 'mixed-build.json' or path.parent.parent != Path('/root')
            or not re.fullmatch('wksim-ap-mixed-[A-Za-z0-9_-]+', path.parent.name)):
        raise ValueError('Expected /root/wksim-ap-mixed-*/mixed-build.json')
    record = checked_json(path, checksum)
    root = path.parent
    keys = {'schema_version', 'status', 'profile', 'candidate_root', 'baseline_root', 'baseline_manifest_sha256',
            'source_manifest_sha256', 'patch_sha256', 'artifacts', 'source_unchanged_during_build',
            'fixed_pv_baseline_unchanged', 'production_admitted', 'flown'}
    if (set(record) != keys or type(record['schema_version']) is not int or record['schema_version'] != 1
            or record['status'] != 'built-not-admitted' or record['profile'] != PROFILE
            or record['candidate_root'] != str(root) or record['baseline_root'] != str(BASE)
            or record['baseline_manifest_sha256'] != BASE_SHA or record['source_unchanged_during_build'] is not True
            or record['fixed_pv_baseline_unchanged'] is not True or record['production_admitted'] is not False
            or record['flown'] is not False):
        raise ValueError('Mixed build schema/status/identity differs')
    prepared = checked_json(root/'mixed-source.json', record['source_manifest_sha256'])
    if (type(prepared['schema_version']) is not int or prepared['schema_version'] != 1
            or prepared['status'] != 'source-only-not-built-not-admitted' or prepared['profile'] != PROFILE
            or prepared['candidate_root'] != str(root) or prepared['baseline_root'] != str(BASE)
            or prepared['baseline_manifest_sha256'] != BASE_SHA or prepared['commit'] != COMMIT):
        raise ValueError('Mixed source identity differs')
    source = root/'src'
    if not (source/'.git').is_dir() or (source/'.git').resolve() != source/'.git':
        raise ValueError('Mixed source must own its independent Git directory')
    if source_snapshot(source, commit=COMMIT) != prepared['source']:
        raise ValueError('Mixed source differs from its prebuild snapshot')
    for item in (PATCH, root/'candidate.patch'):
        if sha(item.read_bytes()) != record['patch_sha256'] or record['patch_sha256'] != prepared['patch_sha256']:
            raise ValueError('Mixed patch differs')
    for item in (REPO/'tools/prepare_ap_mixed_candidate.py', root/'prepare_ap_mixed_candidate.py'):
        if sha(item.read_bytes()) != prepared['prepare_sha256']:
            raise ValueError('Mixed preparation script differs')
    git(source, 'apply', '--reverse', '--check', str(PATCH))
    verified, _ = baseline()
    if (verified != prepared['baseline_verification']
            or (root/'baseline-pv-build.json').read_bytes() != (BASE/'pv-build.json').read_bytes()):
        raise ValueError('Original PV baseline changed')
    if set(record['artifacts']) != {'build/sitl/bin/arducopter', 'configure.log', 'build.log'}:
        raise ValueError('Mixed build artifact set differs')
    for name, expected in record['artifacts'].items():
        item = root/name
        if (item.is_symlink() or item.resolve(strict=True) != item or not item.stat().st_size
                or sha(item.read_bytes()) != expected):
            raise ValueError('Mixed artifact differs: '+name)
    binary = root/'build/sitl/bin/arducopter'
    if not os.access(binary, os.X_OK):
        raise ValueError('Mixed firmware is not executable')
    return dict(status='verified-built-not-admitted', production_admitted=False, flown=False,
        manifest_path=str(path), manifest_sha256=checksum, candidate=record,
        binary=dict(path=str(binary), sha256=record['artifacts']['build/sitl/bin/arducopter']),
        source_files=len(prepared['source']['files']), source_repositories=len(prepared['source']['repositories']),
        source_manifest_sha256=record['source_manifest_sha256'], baseline_verification=verified,
        verifier_sha256=sha(Path(__file__).read_bytes()),
        scope='Current mixed build bytes only; no native behavior, experimental admission or flight proof')


def admit(manifest, checksum, control_manifest, control_checksum, run_id, *, task_profile=PROFILE):
    result = dict(ok=False, experimental=True, production_admitted=False, flown=False, children_created=0,
        task_profile=task_profile, reasons=[], configs={}, model_library='', control_candidate=None, identities={})
    try:
        if task_profile not in (PROFILE, PV_PROFILE):
            raise ValueError('Unsupported task for mixed firmware')
        if task_profile == PV_PROFILE and (checksum != FINAL_AP_SHA or control_checksum != FINAL_CONTROL_SHA):
            raise ValueError('P+V compatibility requires the exact final mixed/control manifests')
        p = joint.select_profile('joint_quad_dds_v1')
        base = dict(schema_version=1, run_id=run_id, vehicle_id=1, model_profile='quad_x',
            communication='native_dds', control_protocol='session_v1', capabilities=['native_position_mission'],
            dds_workspace=p['dds_workspace'], prometheus_workspace=p['control_workspace'],
            px4_root=str(Path(p['manifests']['px4']['path']).parent/'src'), model_library=p['model_library'])
        validate_config(dict(base, stack='px4'))
        native = verify(manifest, checksum)
        if native['baseline_verification']['baseline_manifest_sha256'] != p['manifests']['ap']['sha256']:
            raise ValueError('Mixed/PV baseline does not descend from the fixed joint AP')
        fixed = _fixed_resources(p)
        checked_json(Path(control_manifest), control_checksum)
        control = check_control(control_manifest, control_checksum)
        if control['root'] == p['control_workspace']:
            raise ValueError('Mixed experiment requires a separately built control candidate')
        configs = {stack: validate_config(dict(base, stack=stack, **(
            {'ap_candidate': native['candidate']['candidate_root']} if stack == 'arducopter' else {})))
            for stack in ('arducopter', 'px4')}
        sources = ('tools/ap_mixed_candidate.py', 'tools/prepare_ap_mixed_candidate.py',
            'tools/ap_pv_candidate.py', 'tools/verify_ap_pv_candidate.py', 'tools/joint_control_candidate.py',
            'tools/run_joint_flight.py', 'Simulator/wksim_runtime/joint_profile.py',
            'Simulator/wksim_runtime/config.py', 'Simulator/wksim_runtime/runtime.py',
            'Simulator/wksim_runtime/build_identity.py')
        result.update(ok=True, configs=configs, model_library=p['model_library'], control_candidate=control,
            candidate=native['candidate'], candidate_verification=native, baseline_profile=p,
            manifest_path=str(manifest), manifest_sha256=checksum,
            control_manifest_path=str(control_manifest), control_manifest_sha256=control_checksum,
            identities=dict(baseline=fixed, ap_mixed=native, control_candidate=control,
                source_sha256={name:joint.digest(REPO/name) for name in sources}),
            capability=dict(profile=PROFILE, position_axes='z', velocity_axes='xy', yaw=True,
                yaw_rate=False, acceleration=False, terrain=False, arducopter_type_mask=2531,
                native_submode=7, vertical_velocity_avoidance=False),
            scope='Bounded mixed XY velocity/Z position/yaw trial only; full PV/native boundaries/production remain separate')
        if task_profile == PV_PROFILE:
            result.update(capability=dict(profile=PV_PROFILE, position_axes='xyz', velocity_axes='xyz', yaw=True,
                acceleration=False, yaw_rate=False, mixed_axes=False, arducopter_type_mask=2496),
                scope='Bounded full XYZ P+V/yaw task on final mixed firmware with both control profiles enabled; production remains separate')
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.CalledProcessError) as error:
        result['reasons'].append(dict(code='ap_mixed_candidate_rejected', message=str(error)))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    verifier = sub.add_parser('verify')
    admission = sub.add_parser('admit')
    for command in (verifier, admission):
        command.add_argument('--ap-mixed-manifest', required=True)
        command.add_argument('--ap-mixed-sha256', required=True)
    for field in ('control-manifest', 'control-sha256', 'run-id'):
        admission.add_argument('--'+field, required=True)
    admission.add_argument('--task-profile', choices=(PROFILE, PV_PROFILE), default=PROFILE)
    args = parser.parse_args()
    if args.command == 'verify':
        print(json.dumps(verify(args.ap_mixed_manifest, args.ap_mixed_sha256), indent=2))
    else:
        report = admit(args.ap_mixed_manifest, args.ap_mixed_sha256, args.control_manifest, args.control_sha256, args.run_id,
                       task_profile=args.task_profile)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report['ok'] else 2)
