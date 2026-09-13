"""Build a separate PX4 SITL firmware candidate with an explicit inner-loop seam.

No production profile, parent source or existing binary is changed. The candidate
receipt pins the copied source, extensions, build recipe and generated outputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.build_identity import source_snapshot

BASE = Path('/root/wksim-px4-state-ONa1Kw')
PARENT_MANIFEST_SHA256 = 'd7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6'
COMMIT = 'd6f12ad1c4f70ad3230afd7d86e971421e02fef4'
MODULE = 'src/modules/mc_rate_control/'
INPUTS = ('Simulator/firmware/rate_control/px4_adapter.hpp', 'tools/rate_control_candidate.py',
          'Simulator/wksim_runtime/build_identity.py',
          'Simulator/firmware/rate_control/predictive_rate.hpp',
          'Simulator/firmware/rate_control/generated_design.hpp',
          'Simulator/firmware/rate_control/quad-x-design.json', 'tools/design_rate_control.py')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one retained source seam: ' + old[:100])
    return text.replace(old, new, 1)


def install_adapter(source, inputs):
    header = source / (MODULE+'MulticopterRateControl.hpp')
    text = header.read_text()
    text = replace_once(text, 'using namespace time_literals;',
                        '#include "wksim_rate_adapter.hpp"\n\nusing namespace time_literals;')
    text = replace_once(text, '\tRateControl _rate_control;',
                        '\tWksimRateAdapter _wksim_rate;\n\tRateControl _rate_control;')
    header.write_text(text)
    cpp = source / (MODULE+'MulticopterRateControl.cpp')
    text = cpp.read_text()
    text = replace_once(text, 'MulticopterRateControl::init()\n{',
        'MulticopterRateControl::init()\n{\n\tif (!_wksim_rate.valid()) { PX4_ERR("Invalid wksim rate experiment/trace"); return false; }')
    text = replace_once(text,
        '_rate_control.update(rates, _rates_setpoint, angular_accel, dt, _maybe_landed || _landed)',
        '_wksim_rate.update(_rate_control, rates, _rates_setpoint, angular_accel, dt, '
        '_maybe_landed || _landed, _vehicle_control_mode.flag_armed, angular_velocity.timestamp_sample)')
    text = replace_once(text, '\t\t\t_vehicle_torque_setpoint_pub.publish(vehicle_torque_setpoint);',
        '\t\t\t_vehicle_torque_setpoint_pub.publish(vehicle_torque_setpoint);\n'
        '\t\t\t_wksim_rate.record_applied(Vector3f{vehicle_torque_setpoint.xyz}, Vector3f{vehicle_thrust_setpoint.xyz});')
    cpp.write_text(text)
    shutil.copyfile(inputs/'Simulator/firmware/rate_control/px4_adapter.hpp',
                    source/(MODULE+'wksim_rate_adapter.hpp'))
    for name in ('predictive_rate.hpp', 'generated_design.hpp'):
        shutil.copyfile(inputs/'Simulator/firmware/rate_control'/name, source/MODULE/name)


def build():
    if sys.platform != 'linux' or digest(BASE/'wksim-build.json') != PARENT_MANIFEST_SHA256:
        raise ValueError('Requires the retained PX4 SITL parent in WSL')
    parent = json.loads((BASE/'wksim-build.json').read_text())
    if source_snapshot(BASE/'src', commit=COMMIT) != parent['source']:
        raise ValueError('Retained parent source no longer matches its receipt')
    binary = 'build/px4_sitl_default/bin/px4'
    if digest(BASE/'src'/binary) != parent['artifacts'][binary]['sha256']:
        raise ValueError('Retained parent binary changed')
    root = Path(tempfile.mkdtemp(prefix='wksim-px4-inner-', dir='/root'))
    print(json.dumps({'candidate_root': str(root)}), flush=True)
    inputs = root/'inputs'
    for name in INPUTS:
        destination = inputs/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, destination)
    source = root/'src'
    with (root/'copy.log').open('w') as log:
        copy = subprocess.run(['cp', '-a', '--reflink=auto', str(BASE/'src'), str(source)],
                              stdout=log, stderr=subprocess.STDOUT)
    if copy.returncode:
        raise RuntimeError('Candidate copy failed: '+str(root/'copy.log'))
    # CMake's generated files contain absolute paths. Delete only this new
    # candidate's copied build; the verified parent build is never touched.
    generated = source/'build'
    if generated.exists():
        if generated.is_symlink() or generated.resolve().parent != source.resolve():
            raise ValueError('Unsafe copied build directory')
        shutil.rmtree(generated)
    install_adapter(source, inputs)
    recipe = ['make', '-C', str(source), '-j4', 'px4_sitl_default']
    prepared = dict(schema='wksim.inner-loop-candidate.v1', family='px4', target='multicopter_sitl',
        candidate_root=str(root), source_root=str(source), upstream_commit=COMMIT,
        parent_manifest=str(BASE/'wksim-build.json'), parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        control_stage='firmware_body_rate', algorithms=['native', 'pid', 'lqr', 'mpc'],
        design_sha256=digest(inputs/'Simulator/firmware/rate_control/quad-x-design.json'),
        repository_inputs={name:digest(inputs/name) for name in INPUTS}, build_argv=recipe,
        state='prepared', production_admitted=False)
    (root/'prepared.json').write_text(json.dumps(prepared, indent=2)+'\n')
    with (root/'build.log').open('w') as log:
        result = subprocess.run(recipe, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('PX4 build failed: '+str(root/'build.log'))
    artifacts = {p.relative_to(source).as_posix(): digest(p)
        for base in ('bin','etc') for p in sorted((source/'build/px4_sitl_default'/base).rglob('*')) if p.is_file()}
    (root/'candidate.json').write_text(json.dumps(dict(prepared, state='built',
        source=source_snapshot(source, commit=COMMIT), artifacts=artifacts,
        binary=str(source/binary), binary_sha256=digest(source/binary)),indent=2)+'\n')
    print(json.dumps({'manifest':str(root/'candidate.json'),'sha256':digest(root/'candidate.json')}),flush=True)


def verify(path, checksum):
    path = Path(path)
    root = path.parent
    if root.name.startswith('wksim-ap-inner-'):
        from build_ap_rate_candidate import verify as verify_ap
        return verify_ap(path,checksum)
    if (root.parent != Path('/root') or not root.name.startswith('wksim-px4-inner-')
            or path.name != 'candidate.json' or path.resolve(strict=True) != path
            or path.is_symlink() or digest(path) != checksum):
        raise ValueError('Explicit canonical candidate receipt and matching SHA256 required')
    record = json.loads(path.read_text())
    source = root/'src'
    if (record['schema'] != 'wksim.inner-loop-candidate.v1' or record['state'] != 'built'
            or record['production_admitted'] is not False or record['candidate_root'] != str(root)
            or record['source_root'] != str(source) or record['upstream_commit'] != COMMIT
            or record['parent_manifest_sha256'] != PARENT_MANIFEST_SHA256
            or digest(BASE/'wksim-build.json') != PARENT_MANIFEST_SHA256):
        raise ValueError('Candidate firmware identity differs')
    if source_snapshot(source, commit=COMMIT) != record['source']:
        raise ValueError('Candidate source differs from the built receipt')
    for name, expected in record['repository_inputs'].items():
        if digest(root/'inputs'/name) != expected:
            raise ValueError('Candidate build input differs: '+name)
    for name, expected in record['artifacts'].items():
        if digest(source/name) != expected:
            raise ValueError('Candidate runtime artifact differs: '+name)
    if digest(record['binary']) != record['binary_sha256']:
        raise ValueError('Candidate executable changed')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'verify'])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.action == 'build': build()
    else: print(json.dumps(verify(args.manifest, args.sha256)['binary_sha256']))
