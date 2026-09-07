"""Explicit joint SITL profile admission; no diagnostic imports or flight launches."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from .build_identity import file_identity, source_snapshot
from .config import validate_config
from .preflight import REPO, INDEX, digest, package_digest

PROFILES = Path(__file__).with_name('joint-profiles.json')
PYTHON = 'local/lib/python3.10/dist-packages'
SCOPE = 'Pinned AP/PX4 quad-X joint DDS public tasks and approved recovery; admission is not flight readiness or complete G2/Full acceptance'


def select_profile(profile_id):
    catalog = json.loads(PROFILES.read_text(encoding='utf-8'))
    if catalog['schema_version'] != 1 or profile_id != 'joint_quad_dds_v1':
        raise ValueError('Unknown joint profile')
    rows = [p for p in catalog['profiles'] if p['id'] == profile_id]
    if len(rows) != 1:
        raise ValueError('Missing or ambiguous joint profile')
    return copy.deepcopy(rows[0])


def _pinned_json(pin):
    path = Path(pin['path'])
    if not path.is_absolute():
        path = REPO / path
    raw = path.read_bytes()
    import hashlib
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('Pinned SHA256 differs: ' + str(path))
    return json.loads(raw)


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


def _control(record):
    root = Path(record['root'])
    package = root/'install/prometheus_control'/PYTHON/'prometheus_control'
    if root.resolve(strict=True) != root or root.is_symlink() or str(package) != record['package']:
        raise ValueError('Control root/package differs')
    for directory in (REPO/'ros2/src/prometheus_control/prometheus_control',
                      root/'src/prometheus_control/prometheus_control', package):
        actual = {}
        for path in directory.rglob('*'):
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Control path escapes source boundary')
            if path.is_file() and '__pycache__' not in path.parts:
                actual[path.relative_to(directory).as_posix()] = digest(path)
        if actual != record['python_sha256']:
            raise ValueError('Control source or installed file set differs')
    for base in (REPO/'ros2/src/prometheus_control', root/'src/prometheus_control'):
        for name, expected in record['build_inputs'].items():
            if digest(base/name) != expected:
                raise ValueError('Control build input differs')
    for path, expected in ((root/'build.log',record['build_log_sha256']),
                           (REPO/'tools/build-joint-control.sh',record['build_script_sha256'])):
        if digest(path) != expected:
            raise ValueError('Control build evidence differs')
    return str(package)


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
                  model_library='',control_package='',identities={},scope=SCOPE)
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
                  model_library='', control_package='', identities={}, scope=SCOPE)
    try:
        if stacks not in (('arducopter', 'px4'), ('arducopter',), ('px4',)):
            raise ValueError('Unsupported resource stack selection')
        if p != select_profile('joint_quad_dds_v1'):
            raise ValueError('Resource descriptor differs from pinned joint profile')
        if platform.system() != 'Linux':
            raise ValueError('Ubuntu 22.04 required')
        release = dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        if release.get('ID','').strip('"')!='ubuntu' or release.get('VERSION_ID','').strip('"')!='22.04':
            raise ValueError('Ubuntu 22.04 required')
        if os.environ.get('ROS_DISTRO')!='humble':
            raise ValueError('ROS_DISTRO must be humble')
        keys = ['ap' if stack == 'arducopter' else 'px4' for stack in stacks] + ['control']
        records = {key:_pinned_json(p['manifests'][key]) for key in keys}
        for key,record in records.items():
            root = record.get('candidate_root',record.get('root'))
            if p['manifests'][key]['path'] != str(Path(root)/('build.json' if key=='control' else 'wksim-build.json')):
                raise ValueError('Manifest root differs')
        for stack in stacks:
            key = 'ap' if stack == 'arducopter' else 'px4'
            result['identities'][key] = _firmware(records[key],key)
        result['control_package'] = _control(records['control'])
        result['identities']['manifests'] = p['manifests']
        healthy = None
        for pin in p['evidence']:
            flight,audit = _pinned_json(pin['result']),_pinned_json(pin['audit'])
            if (flight['status']!='pass' or not flight['flight_completed'] or not flight['control_shutdown_clean']
                    or not flight['source_unchanged'] or flight['cleanup_errors'] or audit['status']!='pass'
                    or audit['result_sha256']!=pin['result']['sha256']
                    or flight['manifest_sha256']!={k:v['sha256'] for k,v in p['manifests'].items()}
                    or flight['control_candidate']!=records['control']):
                raise ValueError('Flight proof does not match joint builds')
            for name,expected in audit['evidence_sha256'].items():
                path = (REPO/pin['result']['path']).parent/name
                if digest(path)!=expected:
                    raise ValueError('Raw flight evidence differs: '+name)
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
        # Agent executable identities are inherited from the exact flown preflights.
        for stack,name in (('arducopter','ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent'),('px4','agent-install/bin/MicroXRCEAgent')):
            if stack not in stacks:
                continue
            preflight_pin=(REPO/p['evidence'][-1]['result']['path']).parent/(stack+'-preflight.json')
            old=json.loads(preflight_pin.read_text())
            while 'baseline_preflight' in old:
                old=old['baseline_preflight']
            expected=old['identities']['agent']['expected_sha256']
            path=Path(p['dds_workspace'])/name
            if digest(path)!=expected or not os.access(path,os.X_OK):
                raise ValueError('DDS agent identity differs: '+stack)
            result['identities'][stack+'_agent']=dict(path=str(path),sha256=expected)
        for path in p['setup_files']:
            if not Path(path).is_file():
                raise ValueError('Missing setup: '+path)
        result['ok']=True
    except (OSError,ValueError,KeyError,TypeError,ImportError,subprocess.CalledProcessError) as error:
        result['reasons'].append(dict(code='joint_profile_rejected',message=str(error)))
    return result
