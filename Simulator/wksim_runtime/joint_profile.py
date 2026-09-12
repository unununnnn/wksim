"""Explicit joint SITL profile admission; no diagnostic imports or flight launches."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

from .build_identity import file_identity, source_snapshot
from .config import validate_config, _unique_object
from .preflight import REPO, INDEX, digest, package_digest

PROFILES = Path(__file__).with_name('joint-profiles.json')
PYTHON = 'local/lib/python3.10/dist-packages'
SCOPE = 'Pinned AP/PX4 quad-X joint DDS public tasks and approved recovery; admission is not flight readiness or complete G2/Full acceptance'
LEGACY_PROFILE = 'joint_quad_dds_v1'
MIXED_PROFILE = 'joint_quad_dds_mixed_pv_v1'
MIXED_TASKS = ('full_xyz_pv_yaw_v1', 'xy_velocity_z_position_yaw_v1')
LEGACY_CONTROL_BUILD_SCRIPTS = frozenset((
    'cee40ea5324de3f38613fd3e8f05bbfde2a5814b1c76e038ec26917795e3365c',
))
CONTROL_SIMULATOR_FILES = {
    'wksim_runtime': ('__init__.py', 'task.py', 'trajectory_bridge.py'),
    'wksim_planning': ('ego_bspline_bridge.py', 'ego_evaluator.py',
                       'ego_trajectory_adapter.py', 'trajectory_session.py'),
}


def select_profile(profile_id):
    catalog = json.loads(PROFILES.read_text(encoding='utf-8'))
    if catalog['schema_version'] != 1 or profile_id not in (LEGACY_PROFILE, MIXED_PROFILE):
        raise ValueError('Unknown joint profile')
    rows = [p for p in catalog['profiles'] if p['id'] == profile_id]
    if len(rows) != 1:
        raise ValueError('Missing or ambiguous joint profile')
    return copy.deepcopy(rows[0])


def _pinned_json(pin):
    if (set(pin) != {'path', 'sha256'} or not isinstance(pin['path'], str)
            or not isinstance(pin['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', pin['sha256'])):
        raise ValueError('Invalid pinned JSON descriptor')
    path = Path(pin['path'])
    if not path.is_absolute():
        path = REPO / path
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError('Pinned JSON path must not resolve through symlinks')
    raw = path.read_bytes()
    import hashlib
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('Pinned SHA256 differs: ' + str(path))
    return json.loads(raw, object_pairs_hook=_unique_object)


def _files(root, expected):
    for name, identity in expected.items():
        if file_identity(root / name, root, directory_links=True) != identity:
            raise ValueError('File identity differs: ' + str(root / name))


def _firmware(record, stack):
    root = Path(record['candidate_root'])
    if root.is_symlink() or root.resolve(strict=True) != root:
        raise ValueError('Firmware root resolves through a symlink')
    source = root / 'src'
    commit = {'ap':'1511f27194f1dcc3728270883047bdf022b3fd53',
              'px4':'d6f12ad1c4f70ad3230afd7d86e971421e02fef4'}[stack]
    if record['commit'] != commit or source_snapshot(source, commit=commit) != record['source']:
        raise ValueError('Firmware source snapshot differs: ' + stack)
    _files(REPO, record['repository_inputs'])
    artifact_root = root if stack == 'ap' else source
    _files(artifact_root, record['artifacts'])
    if stack == 'px4':
        _files(root, {'build.log':record['build_log'], 'dependency-check.log':record['dependency_check']})
        runtime = source/'build/px4_sitl_default'
        names = {p.relative_to(source).as_posix() for base in (runtime/'bin', runtime/'etc')
                 for p in base.rglob('*') if p.is_file()}
        if names != set(record['artifacts']):
            raise ValueError('PX4 runtime file set differs')
    binary = artifact_root / ('build/sitl/bin/arducopter' if stack=='ap' else 'build/px4_sitl_default/bin/px4')
    if not os.access(binary, os.X_OK):
        raise ValueError('Firmware is not executable')
    return dict(path=str(binary), sha256=digest(binary), commit=commit,
                source_files=len(record['source']['files']))


def _control(record, *, sealed=False):
    if not sealed:
        if record.get('version') != 2:
            raise ValueError('Current control candidate requires manifest version 2')
        # Use the same complete source/stage/install/message seal that built the
        # current candidate; a second import-closure list had drifted to 7 files.
        from tools.joint_control_candidate import check
        manifest = Path(record['root'])/'build.json'
        checked = check(manifest, digest(manifest))
        if checked != record:
            raise ValueError('Current control record differs from its manifest')
        return checked['package']
    root = Path(record['root'])
    package = root/'install/prometheus_control'/PYTHON/'prometheus_control'
    if root.resolve(strict=True) != root or root.is_symlink() or str(package) != record['package']:
        raise ValueError('Control root/package differs')
    directories = (root/'src/prometheus_control/prometheus_control', package)
    for directory in directories:
        if not directory.is_dir() or directory.is_symlink() or directory.resolve(strict=True) != directory:
            raise ValueError('Missing or symlinked control package')
        actual = {}
        for path in directory.rglob('*'):
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Control path escapes source boundary')
            if path.is_file() and '__pycache__' not in path.parts:
                actual[path.relative_to(directory).as_posix()] = digest(path)
        if not actual or actual != record['python_sha256']:
            raise ValueError('Control source or installed file set differs')
    if record.get('version') == 2:
        from tools.joint_control_candidate import SIMULATOR_ASSETS
        assets = record.get('simulator_asset_sha256', {})
        supported_assets = {namespace+'/'+name for namespace,names in SIMULATOR_ASSETS.items()
                            for name in names}
        if not isinstance(assets, dict) or assets and set(assets) != supported_assets:
            raise ValueError('Sealed Simulator support asset set differs')
        simulator_bases = [root/'Simulator', root/'install/prometheus_control'/PYTHON/'Simulator']
        for base in simulator_bases:
            actual = {}
            for namespace, names in CONTROL_SIMULATOR_FILES.items():
                directory = base/namespace
                if not directory.is_dir() or directory.is_symlink():
                    raise ValueError('Missing or symlinked Simulator support package')
                for path in directory.rglob('*'):
                    if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                        raise ValueError('Simulator support path escapes source boundary')
                    if path.is_file() and '__pycache__' not in path.parts:
                        if path.suffix != '.py':
                            if namespace+'/'+path.relative_to(directory).as_posix() in assets:
                                continue
                            raise ValueError('Unexpected non-Python Simulator support content')
                        actual[namespace+'/'+path.relative_to(directory).as_posix()] = digest(path)
            if actual != record['simulator_python_sha256']:
                raise ValueError('Simulator support source or installed file set differs')
            for name, expected in assets.items():
                path = base/name
                if path.is_symlink() or path.resolve(strict=True) != path or digest(path) != expected:
                    raise ValueError('Simulator support asset differs: '+name)
    # A sealed historical installation is checked against its own build inputs.
    # The current candidate has separate source/stage/install admission; evolving
    # its CMake targets cannot alter the bytes used to build the old installation.
    build_bases = (root/'src/prometheus_control',)
    for base in build_bases:
        for name, expected in record['build_inputs'].items():
            if digest(base/name) != expected:
                raise ValueError('Control build input differs')
    if record.get('version') == 2:
        installed = {name:digest(root/'install/prometheus_control'/target) for name,target in {
            'scripts/prometheus_control_node':'lib/prometheus_control/prometheus_control_node',
            'scripts/trajectory_bridge_node':'lib/prometheus_control/trajectory_bridge_node',
            'launch/trajectory_bridge.launch.py':'share/prometheus_control/launch/trajectory_bridge.launch.py',
        }.items()}
        if installed != record['installed_inputs']:
            raise ValueError('Installed control entry points differ')
    builder_paths = []
    if record.get('version') == 2:
        builder_paths.append(root/'build-joint-control.sh')
    elif sealed and record.get('version') == 1:
        # These are the exact builders recorded by immutable pre-v2 candidates.
        if record['build_script_sha256'] not in LEGACY_CONTROL_BUILD_SCRIPTS:
            raise ValueError('Unknown legacy control build script')
    else:
        builder_paths.append(REPO/'tools/build-joint-control.sh')
    for path, expected in ((root/'build.log',record['build_log_sha256']),
                           *((path,record['build_script_sha256']) for path in builder_paths)):
        if digest(path) != expected:
            raise ValueError('Control build evidence differs')
    return str(package)


def _profile_contract(p):
    """Only catalog-owned selectors can choose historical source or mixed firmware."""
    if p != select_profile(p['id']):
        raise ValueError('Resource descriptor differs from pinned joint profile')
    if p['id'] == LEGACY_PROFILE:
        if (p['control_source'] != 'sealed_legacy'
                or p['capabilities'] != ['public_position', 'public_velocity_yaw']):
            raise ValueError('Legacy control source policy differs')
        return False
    if (p['control_source'] != 'current' or p['evidence_schema'] != 'joint_mixed_pv_v1'
            or p['manifest_kinds'] != dict(ap='ap_mixed_v1', px4='wksim_build_v1', control='joint_control_v1')
            or p['capabilities'] != ['public_position', 'public_velocity_yaw', *MIXED_TASKS]):
        raise ValueError('Mixed profile capability/manifest/source contract differs')
    if (len(p['evidence']) != len(MIXED_TASKS)
            or {pin['task_profile'] for pin in p['evidence']} != set(MIXED_TASKS)):
        raise ValueError('Missing final mixed/PV capability flight proofs')
    return True


def _mixed_firmware(pin):
    # Import only the read-only verifier; importing it never admits or starts a run.
    sys.path.insert(0, str(REPO/'tools'))
    from ap_mixed_candidate import verify
    verified = verify(pin['path'], pin['sha256'])
    baseline = select_profile(LEGACY_PROFILE)
    if verified['baseline_verification']['baseline_manifest_sha256'] != baseline['manifests']['ap']['sha256']:
        raise ValueError('Mixed/PV source chain differs from fixed joint AP')
    return dict(**verified['binary'], commit='1511f27194f1dcc3728270883047bdf022b3fd53',
                source_files=verified['source_files']), verified


def _raw_proof(pin, audit):
    root = (REPO/pin['result']['path']).parent
    if not audit['evidence_sha256']:
        raise ValueError('Missing raw flight evidence')
    for name, expected in audit['evidence_sha256'].items():
        path = root/name
        if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or digest(path) != expected:
            raise ValueError('Raw flight evidence differs: '+name)
    return root


def _mixed_proofs(p, records, identities):
    """Bind both audited task capabilities to one actual AP/PX4/control/model set."""
    if (len(p['evidence']) != 2 or {pin['task_profile'] for pin in p['evidence']} != set(MIXED_TASKS)):
        raise ValueError('Missing final mixed/PV capability flight proofs')
    resources = None
    healthy = None
    for pin in p['evidence']:
        if set(pin) != {'task_profile', 'result', 'audit', 'admission'}:
            raise ValueError('Mixed capability proof descriptor schema differs')
        flight, audit, admission = (_pinned_json(pin[key]) for key in ('result', 'audit', 'admission'))
        if 'rate_timing_probe' in flight:
            raise ValueError('Formal mixed/PV evidence cannot include rate_timing_probe')
        task = pin['task_profile']
        if (flight['status'] != 'pass' or flight['flight_completed'] is not True
                or flight['source_unchanged'] is not True or flight['control_shutdown_clean'] is not True
                or flight['cleanup_errors'] or audit['status'] != 'pass' or audit['outstanding_checks']
                or flight['task_profile'] != task or audit['task_profile'] != task
                or audit['result_sha256'] != pin['result']['sha256']
                or audit['run_id'] != flight['run_id'] or audit['scene_epoch'] != flight['scene_epoch']):
            raise ValueError('Mixed/PV flight capability or raw audit did not pass')
        root = _raw_proof(pin, audit)
        if ((REPO/pin['admission']['path']).resolve() != (root/'experimental-admission.json').resolve()
                or audit['evidence_sha256'].get('experimental-admission.json') != pin['admission']['sha256']
                or admission != flight['mixed_admission'] or admission['task_profile'] != task
                or admission['ok'] is not True or admission['experimental'] is not True
                or admission['production_admitted'] is not False or admission['flown'] is not False
                or admission['children_created'] != 0 or admission['reasons']):
            raise ValueError('Mixed/PV retained admission identity differs')
        capability = (dict(profile=task, position_axes='xyz', velocity_axes='xyz', yaw=True,
                           acceleration=False, yaw_rate=False, mixed_axes=False, arducopter_type_mask=2496)
                      if task == MIXED_TASKS[0] else dict(profile=task, position_axes='z', velocity_axes='xy',
                           yaw=True, yaw_rate=False, acceleration=False, terrain=False, arducopter_type_mask=2531,
                           native_submode=7, vertical_velocity_avoidance=False))
        if admission['capability'] != capability:
            raise ValueError('Mixed/PV admitted task capability differs')
        manifests = {key: p['manifests'][key]['sha256'] for key in ('ap', 'control')}
        if (flight['manifest_sha256'] != manifests
                or admission['manifest_sha256'] != manifests['ap']
                or admission['control_manifest_sha256'] != manifests['control']
                or admission['manifest_path'] != p['manifests']['ap']['path']
                or admission['control_manifest_path'] != p['manifests']['control']['path']
                or admission['candidate'] != records['ap']
                or flight['control_candidate'] != records['control']
                or admission['control_candidate'] != records['control']):
            raise ValueError('Mixed/PV proof does not match selected AP/control pins')
        for key in ('ap', 'control'):
            if audit['evidence_sha256'].get(key+'-build.json') != manifests[key]:
                raise ValueError('Retained mixed build manifest differs: '+key)
        native = admission['candidate_verification']
        if admission['identities']['ap_mixed'] != native:
            raise ValueError('Mixed source verification identity differs')
        for key in ('candidate', 'binary', 'source_files', 'source_repositories',
                    'source_manifest_sha256', 'baseline_verification'):
            if native[key] != identities['ap_mixed'][key]:
                raise ValueError('Mixed full sealed source chain differs: '+key)
        if (native['status'] != 'verified-built-not-admitted' or native['production_admitted'] is not False
                or native['flown'] is not False
                or audit['evidence_sha256'].get('mixed-source.json') != native['source_manifest_sha256']
                or audit['evidence_sha256'].get('baseline-pv-build.json') != records['ap']['baseline_manifest_sha256']):
            raise ValueError('Missing mixed/PV sealed source proof')
        sources = flight['source_sha256']
        required = {'tools/run_joint_flight.py', 'tools/ap_mixed_candidate.py',
                    'tools/prepare_ap_mixed_candidate.py', 'tools/verify_ap_pv_candidate.py',
                    'Simulator/wksim_runtime/joint_profile.py', 'Simulator/wksim_core/model.py'}
        if not required <= sources.keys():
            raise ValueError('Missing executed mixed proof source identity')
        for name, expected in sources.items():
            if audit['evidence_sha256'].get('source__'+name.replace('/', '__')+'.txt') != expected:
                raise ValueError('Retained executed source is not sealed: '+name)
        for name, expected in admission['identities']['source_sha256'].items():
            if sources.get(name) != expected:
                raise ValueError('Admission/execution source differs: '+name)
        argv = flight['children']['arducopter-control']['argv']
        profiles = dict(arducopter_pv_profile=MIXED_TASKS[0], arducopter_mixed_profile=MIXED_TASKS[1])
        if audit['identity']['control_profiles'] != profiles:
            raise ValueError('Mixed/PV audit did not verify both capability parameters')
        for key, value in profiles.items():
            flag = key+':='+value
            if ([arg for arg in argv if arg.startswith(key+':=')] != [flag]
                    or argv.index(flag) == 0 or argv[argv.index(flag)-1] != '-p'):
                raise ValueError('Mixed/PV proof did not execute both capability parameters')
        baseline = admission['identities']['baseline']
        if (baseline['manifests']['px4'] != p['manifests']['px4']
                or baseline['px4'] != identities['px4'] or baseline['model'] != flight['model_build']
                or baseline['model']['library'] != p['model_library']):
            raise ValueError('Mixed/PV proof PX4/model identity differs')
        current = {key: baseline[key] for key in ('px4', 'model', 'message_packages', 'arducopter_agent', 'px4_agent')}
        if resources is not None and current != resources:
            raise ValueError('Mixed/PV capability proofs use different resources')
        resources, healthy = current, flight
    return healthy, resources


def _overlay(name, prefix):
    prefix = Path(prefix)
    spec = importlib.util.find_spec(name)
    expected = prefix/PYTHON/name/'__init__.py'
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != expected.resolve():
        raise ValueError(name + ': Python mixed overlay')
    active = next((Path(p).resolve() for p in os.environ.get('AMENT_PREFIX_PATH','').split(os.pathsep)
                   if p and (Path(p)/'share/ament_index/resource_index/packages'/name).is_file()),None)
    if active != prefix.resolve():
        raise ValueError(name + ': ament mixed overlay')
    for library in (prefix/'lib').glob('*.so*'):
        active = next((Path(p)/library.name for p in os.environ.get('LD_LIBRARY_PATH','').split(os.pathsep)
                       if p and (Path(p)/library.name).is_file()),None)
        if active is None or active.resolve() != library.resolve():
            raise ValueError(name + ': linker mixed overlay')
    for key,module in tuple(sys.modules.items()):
        filename = getattr(module,'__file__',None)
        if filename and (key==name or key.startswith(name+'.')) and not Path(filename).resolve().is_relative_to(prefix.resolve()):
            raise ValueError(name + ': imported mixed overlay')


def check_profile(profile_id, run_id):
    result = dict(ok=False,reasons=[],children_created=0,profile=None,configs={},
                  model_library='',control_package='',identities={},capabilities=[],scope=SCOPE)
    try:
        p = select_profile(profile_id)
        result['profile'] = p
        # Validate user identity before expensive source walks or any subprocess.
        base = dict(schema_version=1,run_id=run_id,vehicle_id=1,model_profile='quad_x',
                    communication='native_dds',control_protocol='session_v1',
                    capabilities=['native_position_mission'],dds_workspace=p['dds_workspace'],
                    prometheus_workspace=p['control_workspace'],
                    px4_root=str(Path(p['manifests']['px4']['path']).parent/'src'),model_library=p['model_library'])
        result['configs'] = {stack:validate_config(dict(base,stack=stack,**(
            {'ap_candidate':str(Path(p['manifests']['ap']['path']).parent)} if stack=='arducopter' else {})))
            for stack in ('arducopter','px4')}
        result.update(check_resources(p))
    except (OSError,ValueError,KeyError,TypeError,ImportError,subprocess.CalledProcessError) as error:
        result['reasons'].append(dict(code='joint_profile_rejected',message=str(error)))
    return result


def check_resources(p, stacks=('arducopter', 'px4')):
    """Check exact joint pins, optionally only one stack's firmware and agent.

    Shared messages and all evidence remain pinned because Control imports both stacks.
    This is resource admission; it does not establish independent-flight readiness.
    """
    result = dict(ok=False, reasons=[], children_created=0, profile=p,
                  model_library='', control_package='', identities={}, capabilities=[], scope=SCOPE)
    try:
        if stacks not in (('arducopter', 'px4'), ('arducopter',), ('px4',)):
            raise ValueError('Unsupported resource stack selection')
        mixed = _profile_contract(p)
        if platform.system() != 'Linux':
            raise ValueError('Ubuntu 22.04 required')
        release = dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        if release.get('ID','').strip('"')!='ubuntu' or release.get('VERSION_ID','').strip('"')!='22.04':
            raise ValueError('Ubuntu 22.04 required')
        if os.environ.get('ROS_DISTRO')!='humble':
            raise ValueError('ROS_DISTRO must be humble')
        keys = ['ap' if stack == 'arducopter' else 'px4' for stack in stacks] + ['control']
        if mixed:
            keys = ['ap', 'px4', 'control']
        records = {key:_pinned_json(p['manifests'][key]) for key in keys}
        for key,record in records.items():
            root = record.get('candidate_root',record.get('root'))
            name = 'build.json' if key == 'control' else ('mixed-build.json' if mixed and key == 'ap' else 'wksim-build.json')
            if p['manifests'][key]['path'] != str(Path(root)/name):
                raise ValueError('Manifest root differs')
        for stack in (('arducopter', 'px4') if mixed else stacks):
            key = 'ap' if stack == 'arducopter' else 'px4'
            if mixed and key == 'ap':
                result['identities']['ap'], result['identities']['ap_mixed'] = _mixed_firmware(p['manifests']['ap'])
            else:
                result['identities'][key] = _firmware(records[key],key)
        result['control_package'] = _control(records['control'], sealed=not mixed)
        result['identities']['manifests'] = p['manifests']
        healthy = None
        proof_resources = None
        if mixed:
            healthy, proof_resources = _mixed_proofs(p, records, result['identities'])
        for pin in (() if mixed else p['evidence']):
            flight,audit = _pinned_json(pin['result']),_pinned_json(pin['audit'])
            if (flight['status']!='pass' or not flight['flight_completed'] or not flight['control_shutdown_clean']
                    or not flight['source_unchanged'] or flight['cleanup_errors'] or audit['status']!='pass'
                    or audit['result_sha256']!=pin['result']['sha256']
                    or flight['manifest_sha256']!={k:v['sha256'] for k,v in p['manifests'].items()}
                    or flight['control_candidate']!=records['control']):
                raise ValueError('Flight proof does not match joint builds')
            _raw_proof(pin, audit)
            if flight.get('dds_loss_requested') is None:
                healthy = flight
        if healthy is None:
            raise ValueError('Missing healthy joint flight proof')
        model=healthy['model_build']; library=Path(p['model_library'])
        for path,expected in ((library,model['library_sha256']), (Path(model['archive']),model['archive_sha256']),
                              (REPO/'Simulator/wksim_core/model.cpp',model['wrapper_sha256']),
                              (REPO/'Simulator/wksim_core/model.py',healthy['source_sha256']['Simulator/wksim_core/model.py'])):
            if digest(path)!=expected:
                raise ValueError('Model identity differs: '+str(path))
        if json.loads(library.with_name('build.json').read_text())!=model:
            raise ValueError('Model build manifest differs')
        result['model_library']=str(library)
        result['identities']['model']=model
        index=json.loads(INDEX.read_text())
        packages={name:pin for baseline in index['baselines'].values() for name,pin in baseline['message_packages'].items() if name!='prometheus_msgs'}
        packages.update({name:pin for name,pin in index['control_profiles']['session_v1']['installed_packages'].items() if name!='prometheus_control'})
        for name,pin in packages.items():
            if package_digest(pin['prefix'],complete=pin.get('complete_snapshot',False))!=pin['sha256']:
                raise ValueError('Message content differs: '+name)
            _overlay(name,pin['prefix'])
        _overlay('prometheus_control',Path(p['control_workspace'])/'install/prometheus_control')
        result['identities']['message_packages']=packages
        if mixed and proof_resources['message_packages'] != packages:
            raise ValueError('Mixed/PV proof message packages differ')
        # Agent executable identities are inherited from the exact flown preflights.
        for stack,name in (('arducopter','ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent'),('px4','agent-install/bin/MicroXRCEAgent')):
            if stack not in stacks:
                continue
            path=Path(p['dds_workspace'])/name
            if mixed:
                agent = proof_resources[stack+'_agent']
                if agent['path'] != str(path):
                    raise ValueError('Mixed/PV proof Agent path differs: '+stack)
                expected = agent['sha256']
            else:
                preflight_pin=(REPO/p['evidence'][-1]['result']['path']).parent/(stack+'-preflight.json')
                old=json.loads(preflight_pin.read_text())
                while 'baseline_preflight' in old:
                    old=old['baseline_preflight']
                expected=old['identities']['agent']['expected_sha256']
            if digest(path)!=expected or not os.access(path,os.X_OK):
                raise ValueError('DDS agent identity differs: '+stack)
            result['identities'][stack+'_agent']=dict(path=str(path),sha256=expected)
        for path in p['setup_files']:
            if not Path(path).is_file():
                raise ValueError('Missing setup: '+path)
        result['capabilities'] = list(p['capabilities'])
        result['ok']=True
    except (OSError,ValueError,KeyError,TypeError,ImportError,subprocess.CalledProcessError) as error:
        result['reasons'].append(dict(code='joint_profile_rejected',message=str(error)))
    return result
