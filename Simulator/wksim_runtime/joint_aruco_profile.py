"""Explicit ArUco experiment resources; never a production capability promotion."""
import copy
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

PROFILE = 'joint_quad_dds_aruco_experimental_v1'
TASK = 'aruco_tracking_experimental_v1'
SCOPE = 'Explicit camera tracking experiment; resource identity only, no flight or Full acceptance'


def validate_experiment(value):
    if not isinstance(value, dict) or set(value) != {'selected_stack', 'control', 'px4'}:
        raise ValueError('ArUco experiment requires selected_stack and explicit control/PX4 manifest pins')
    if value['selected_stack'] not in ('arducopter', 'px4'):
        raise ValueError('Invalid ArUco selected stack')
    for key, pattern, filename in (
            ('control', r'wksim-joint-control-[A-Za-z0-9]+', r'build\.json'),
            ('px4', r'wksim-px4-land-[A-Za-z0-9]+', r'land-build(?:-v[1-9][0-9]*)?\.json')):
        pin = value[key]
        if (not isinstance(pin, dict) or set(pin) != {'path', 'sha256'}
                or not isinstance(pin['path'], str) or not isinstance(pin['sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', pin['sha256'])):
            raise ValueError('Invalid ArUco '+key+' manifest pin')
        path = PurePosixPath(pin['path'])
        variant = (re.fullmatch(pattern,path.parent.name) and re.fullmatch(filename,path.name))
        if key == 'px4':
            variant = variant or (re.fullmatch(r'wksim-px4-component-[A-Za-z0-9]+',path.parent.name)
                                  and path.name == 'component-build.json')
        if (str(path) != pin['path'] or path.parent.parent != PurePosixPath('/root')
                or not variant):
            raise ValueError('ArUco candidate must have a private, canonical manifest path')
    return copy.deepcopy(value)


def select_config(config):
    from .joint_profile import LEGACY_PROFILE, select_profile
    if config['runtime_profile'] != PROFILE or config.get('task') != TASK:
        raise ValueError('ArUco experiment requires its explicit task and profile')
    candidate = validate_experiment(config.get('aruco_experiment'))
    profile = select_profile(LEGACY_PROFILE)
    previous = profile['control_workspace']
    control = str(PurePosixPath(candidate['control']['path']).parent)
    profile.update(id=PROFILE, control_workspace=control, control_source='current_experimental',
                   capabilities=[TASK], experimental=True, production_admitted=False, scope=SCOPE)
    profile['manifests'].update(control=candidate['control'], px4=candidate['px4'])
    profile['setup_files'] = [control+'/install/local_setup.bash' if p == previous+'/install/local_setup.bash'
                              else p for p in profile['setup_files']]
    return profile


def check(config):
    """Verify the flown baseline in its own overlay, then all changed resources.

    The child is a read-only identity checker, not a ROS or simulator process.
    Historical flight proofs remain bound to the historical resources; they are
    not reused as proof that the two changed resources have flown.
    """
    from .joint_profile import LEGACY_PROFILE, select_profile, _overlay
    from .preflight import REPO
    result = dict(ok=False, reasons=[], children_created=0, capabilities=[], scope=SCOPE,
                  experimental=True, production_admitted=False, flight_verified=False)
    try:
        profile = select_config(config)
        baseline = select_profile(LEGACY_PROFILE)
        code = ('import json,sys;from Simulator.wksim_runtime.joint_profile import check_profile;'
                'print(json.dumps(check_profile(sys.argv[1],sys.argv[2]),allow_nan=False))')
        script = ('set -eo pipefail\ncount=$1; shift\n'
                  'for ((i=0;i<count;i++)); do source "$1"; shift; done\nexec "$@"')
        completed = subprocess.run(['bash', '-c', script, 'wksim-aruco-baseline',
            str(len(baseline['setup_files'])), *baseline['setup_files'], sys.executable, '-B', '-c',
            code, LEGACY_PROFILE, config['run_id']], cwd=REPO, capture_output=True, text=True,
            timeout=180, check=True)
        old = json.loads(completed.stdout)
        if not old['ok']:
            raise ValueError('ArUco baseline rejected: '+str(old['reasons']))
        from tools.joint_control_candidate import check as check_control
        candidate = config['aruco_experiment']
        component_timing = PurePosixPath(candidate['px4']['path']).name == 'component-build.json'
        if component_timing:
            from tools.px4_component_candidate import check as check_px4
        else:
            from tools.px4_land_candidate import check as check_px4
        control = check_control(candidate['control']['path'], candidate['control']['sha256'])
        px4 = check_px4(candidate['px4']['path'], candidate['px4']['sha256'])
        _overlay('prometheus_control', Path(control['root'])/'install/prometheus_control')
        if (control['root'] != profile['control_workspace']
                or px4['root'] != str(Path(candidate['px4']['path']).parent)):
            raise ValueError('ArUco candidate resource path differs')
        # Compare native baseline directly with the pinned, already checked manifest.
        baseline_px4 = json.loads(Path(baseline['manifests']['px4']['path']).read_text())
        if (px4['baseline_source'] != baseline_px4['source']
                or px4['baseline_binary_sha256'] != old['identities']['px4']['sha256']):
            raise ValueError('ArUco land candidate derives from another PX4 baseline')
        configs = copy.deepcopy(old['configs'])
        for value in configs.values():
            value['prometheus_workspace'] = control['root']
            value['px4_root'] = px4['root']+'/src'
        identities = copy.deepcopy(old['identities'])
        identities.update(manifests=profile['manifests'], control_candidate=control,
                          px4_candidate=px4,
                          px4=dict(path=px4['root']+'/src/build/px4_sitl_default/bin/px4',
                                   sha256=px4['binary_sha256'], commit=baseline_px4['commit'],
                                   source_files=len(px4['source']['files'])))
        result.update(ok=True, profile=profile, configs=configs, capabilities=[TASK],
                      native_component_timing=component_timing,
                      model_library=old['model_library'], control_package=control['package'],
                      identities=identities, baseline_admission=old)
    except (OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
        result['reasons'].append(dict(code='aruco_experiment_rejected', message=str(error)))
    return result
