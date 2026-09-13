"""Read-only, explicit Hex source-template admission; no production Quad preflight."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime import joint_profile as joint
from tools.build_hex_model_candidate import load_config, verify_build, canonical
from tools.hex_launch_plan import launch_plan
from tools.hex_physics import LIBRARY_SHA256, MODEL_IDENTITY

LIBRARY = Path('/root/wksim-hex-candidate-private/build-ihnane6f/libwksim_hex_candidate.so')
BUILD_SHA = '1f6534d11b5634723fa1c3c2e4d518ee11a281d5a28f24149c836eb56199834c'
PLAN_IDENTITY = 'sha256:319c5cba50eb11b81f70ac3ade707879c2fdba252335aa039674e93b9168e1a0'
AP47_PLAN_IDENTITY = 'sha256:5c07a2d5c1e4b13580ae8b3ba43ce686324ec340adf2c12e9b4ffaabbba8486a'


def plan_identity(stack):
    require(stack in ('px4', 'arducopter'), 'Unsupported stack')
    return AP47_PLAN_IDENTITY if stack == 'arducopter' else PLAN_IDENTITY


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def native_parameters(stack):
    plan = launch_plan(stack)
    if stack == 'arducopter':
        return dict(plan['ap_parameters'], DDS_ENABLE=1, DDS_UDP_PORT=12019, DDS_DOMAIN_ID=77, LOG_DISARMED=1)
    require(stack == 'px4', 'Unsupported stack')
    return dict(plan['px4_parameters'], SIM_BAT_ENABLE=1, UXRCE_DDS_SYNCT=0, SYS_AUTOSTART=10016)


def clean_environment():
    return dict(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                HOME='/root', LANG='C.UTF-8', PYTHONDONTWRITEBYTECODE='1')


def fixed_probe(profile):
    script = 'set -eo pipefail\n'+''.join('source '+shlex.quote(p)+'\n' for p in profile['setup_files'])
    script += 'exec '+shlex.join(['/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--probe'])
    value = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c', script], cwd=REPO,
        env=clean_environment(), capture_output=True, text=True, timeout=300)
    require(value.returncode == 0, 'Fixed clean-overlay resource probe failed: '+value.stderr[-5000:])
    return json.loads(value.stdout)


def admit(stack, run_id):
    result = dict(ok=False, experimental=True, production_admitted=False, model_profile='hex_x',
                  flown=False, children_created=0, reasons=[])
    try:
        require(stack in ('arducopter', 'px4') and isinstance(run_id, str)
                and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run_id), 'Invalid stack/run identity')
        profile = joint.select_profile('joint_quad_dds_v1')
        fixed = fixed_probe(profile)
        config = load_config(LIBRARY.with_name('config.json'))
        library = verify_build(LIBRARY, config)
        require(library == LIBRARY and digest(library) == LIBRARY_SHA256
                and digest(library.with_name('build.json')) == BUILD_SHA
                and config['model_identity'] == MODEL_IDENTITY, 'Hex build/config/library identity differs')
        plan = launch_plan(stack)
        selected_plan = plan_identity(stack)
        require(plan['plan_identity'] == selected_plan, 'Frozen six-channel plan differs')
        px4_root = Path(profile['manifests']['px4']['path']).parent/'src'
        xml = px4_root/'build/px4_sitl_default/parameters.xml'
        types = {p.attrib['name']: p.attrib['type'] for p in ET.parse(xml).iter('parameter')}
        parameters = native_parameters(stack)
        if stack == 'px4':
            require(all(types.get(k) in ('INT32', 'FLOAT') for k in parameters), 'Missing/unsupported PX4 parameter')
            parameter_types = {k: types[k] for k in parameters}
        else:
            parameter_types = {k: 'native GetParameters numeric' for k in parameters}
        runtime = dict(schema_version=1, run_id=run_id, vehicle_id=1, stack=stack, model_profile='hex_x',
            communication='native_dds', control_protocol='session_v1', capabilities=['native_position_mission'],
            dds_workspace=profile['dds_workspace'], prometheus_workspace=profile['control_workspace'],
            ap_candidate=str(Path(profile['manifests']['ap']['path']).parent), px4_root=str(px4_root),
            model_library=str(library), hex_config=str(library.with_name('config.json')))
        identity = dict(model_identity=MODEL_IDENTITY, plan_identity=selected_plan, model_profile='hex_x',
                        stack=stack, native_parameters=parameters, fixed_manifests=profile['manifests'])
        result.update(ok=True, config=runtime, library=str(library), setup_files=profile['setup_files'],
            parameters=parameters, parameter_types=parameter_types,
            configuration_identity='sha256:'+hashlib.sha256(canonical(identity).encode()).hexdigest(),
            identities=dict(baseline=fixed, hex_build_sha256=BUILD_SHA, hex_library_sha256=LIBRARY_SHA256,
                hex_config=config, plan_identity=selected_plan, parameters_xml_sha256=digest(xml),
                setup_sha256={p:digest(p) for p in profile['setup_files']}))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, ET.ParseError) as error:
        result['reasons'].append(str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--stack', choices=('arducopter', 'px4'))
    parser.add_argument('--run-id')
    args = parser.parse_args()
    if args.probe:
        from ap_pv_candidate import _fixed_resources
        value = _fixed_resources(joint.select_profile('joint_quad_dds_v1'))
    else:
        value = admit(args.stack, args.run_id)
    print(json.dumps(value, indent=2, allow_nan=False))
    return 0 if value.get('ok', True) else 2


if __name__ == '__main__':
    raise SystemExit(main())
