"""Resolve portable experiment intent against separately pinned local deployments.

Only implemented experiment/vehicle/firmware combinations compile to commands.
Build identity and source checks remain in the selected native launch adapter.
Callers that must bind a document identity to its parsed semantics read each
document once with `load_document_with_digest`; a later `verify_document_identity`
is a fail-closed execution guard, never the source of the recorded digest.
"""
import copy
import hashlib
import json
from pathlib import Path,PurePosixPath
import re


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate configuration key: '+key)
        result[key]=value
    return result


def _parse(text):
    def invalid(value):raise ValueError('Nonfinite JSON constant: '+value)
    return json.loads(text,object_pairs_hook=_object,parse_constant=invalid)


def load_document(path):
    return _parse(Path(path).read_text(encoding='utf-8'))


def load_document_with_digest(path):
    """Return `(document,sha256)`, both derived from one single read of the bytes."""
    raw=Path(path).read_bytes()
    return _parse(raw.decode('utf-8')),hashlib.sha256(raw).hexdigest()


def document_digest(path):
    """Digest the current bytes of a document for verification only."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_document_identity(path,digest):
    """Fail closed when the bytes on disk no longer match a digest recorded at read time."""
    try:
        current=document_digest(path)
    except OSError as error:
        raise RuntimeError('Experiment input is unreadable after it was read: '+str(path)) from error
    if current!=digest:
        raise RuntimeError('Experiment input changed after it was read: '+str(path))


def resolve(intent,deployment):
    if not isinstance(intent,dict) or set(intent)-{'schema_version','id','kind','vehicle_model','firmware','algorithms','path_controller','disturbance'}:
        raise ValueError('Unknown experiment fields')
    if type(intent.get('schema_version')) is not int or intent['schema_version']!=1:
        raise ValueError('Unsupported experiment schema')
    if not isinstance(intent.get('id'),str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',intent['id']):
        raise ValueError('Explicit experiment identity required')
    if not isinstance(deployment,dict) or set(deployment)!={'schema_version','firmware_releases'} or type(deployment['schema_version']) is not int or deployment['schema_version']!=1:
        raise ValueError('Unsupported deployment document')
    releases=deployment['firmware_releases']
    if not isinstance(releases,dict) or not isinstance(intent.get('firmware'),str) or intent['firmware'] not in releases:
        raise ValueError('Experiment selects an unknown firmware release')
    release=releases[intent['firmware']]
    fields={'family','target','vehicle_model','manifest_linux','manifest_sha256'}
    if not isinstance(release,dict) or set(release)!=fields:
        raise ValueError('Firmware deployment must declare target, vehicle and pinned receipt')
    path=release['manifest_linux'];checksum=release['manifest_sha256']
    if (not isinstance(path,str) or not path.startswith('/') or path.startswith('//') or '\\' in path
            or '..' in PurePosixPath(path).parts or any(ord(c)<32 for c in path)
            or not isinstance(checksum,str) or not re.fullmatch('[0-9a-f]{64}',checksum)):
        raise ValueError('Canonical Linux receipt path and SHA256 required')
    if intent.get('vehicle_model')!=release['vehicle_model']:
        raise ValueError('Vehicle model does not match the firmware deployment')
    if intent.get('kind')=='body_rate_comparison':
        if (release['family'],release['target'],release['vehicle_model']) not in (
                ('px4','multicopter_sitl','quad_x'),('ardupilot','copter_sitl','quad_x')) or 'path_controller' in intent:
            raise ValueError('Body-rate comparison requires an implemented quad rate adapter')
        algorithms=intent.get('algorithms')
        if (not isinstance(algorithms,list) or not algorithms or any(a not in ('native','pid','lqr','mpc') for a in algorithms)
                or len(set(algorithms))!=len(algorithms)):
            raise ValueError('Unique explicit implemented rate algorithms required')
        argv=['tools/run_rate_control_comparison.py','--manifest',path,'--sha256',checksum,'--algorithms',*algorithms]
        disturbance=intent.get('disturbance','none')
        if disturbance not in ('none','motor0_command_97pct_1s'):raise ValueError('Unknown actuator disturbance')
        if disturbance!='none':argv.append('--motor-command-disturbance')
    elif intent.get('kind')=='ground_waypoints':
        if (release['family'],release['target'],release['vehicle_model'])!=('ardupilot','rover','ackermann_v1') or 'algorithms' in intent or 'disturbance' in intent:
            raise ValueError('Ground waypoints require Rover and the ground model, not ArduCopter')
        controller=intent.get('path_controller','pure_pursuit')
        if controller not in ('pure_pursuit','native_scurve'):raise ValueError('Unknown ground path controller')
        argv=['tools/run_rover_experiment.py','--manifest',path,'--sha256',checksum,'--path-controller',controller]
    else:
        raise ValueError('Unimplemented experiment kind')
    # The resolved record owns deep copies so a caller mutating its own intent or
    # deployment objects afterwards cannot rewrite an already-resolved plan.
    return dict(schema_version=1,experiment_id=intent['id'],intent=copy.deepcopy(intent),
                deployment=copy.deepcopy(release),python_argv=argv,production_admitted=False)
