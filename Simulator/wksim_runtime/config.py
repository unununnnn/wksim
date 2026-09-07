"""Strict, shared v1 input contract for one independent experiment."""
import json
from pathlib import Path, PurePosixPath
import re

from .mission_plan import validate_mission


class ConfigError(ValueError):
    pass


def validate_config(data):
    """Return a new normalized dict; never touch resources or launch a process."""
    if isinstance(data,dict) and data.get('kind')=='joint_scene':
        from .joint_config import validate_joint_config
        return validate_joint_config(data)
    if not isinstance(data, dict):
        raise ConfigError("Configuration must be a JSON object")
    required = {'schema_version', 'run_id', 'vehicle_id', 'stack', 'model_profile',
                'communication', 'dds_workspace', 'prometheus_workspace', 'px4_root'}
    optional = {'ap_candidate', 'capabilities', 'model_library', 'display_socket', 'control_protocol',
                'restart_control_on_ground', 'mission', 'telemetry_socket', 'runtime_profile'}
    if required - data.keys():
        raise ConfigError('Missing fields: ' + ', '.join(sorted(required - data.keys())))
    if data.keys() - required - optional:
        raise ConfigError('Unknown fields: ' + ', '.join(sorted(data.keys() - required - optional)))
    for key, expected in [('schema_version', 1), ('vehicle_id', 1)]:
        if type(data[key]) is not int or data[key] != expected:
            raise ConfigError(f'{key} must be integer {expected}')
    if not isinstance(data['run_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', data['run_id']):
        raise ConfigError('run_id must be 1..64 ASCII letters/digits/underscore/hyphen, starting with a letter or digit')
    for key, choices in [('stack', ('px4', 'arducopter')), ('model_profile', ('quad_x',)),
                         ('communication', ('native_dds',))]:
        if data[key] not in choices:
            raise ConfigError(f'Unsupported {key}: {data[key]!r}; allowed: {choices}')
    if data['stack'] == 'arducopter' and 'ap_candidate' not in data:
        raise ConfigError('arducopter requires ap_candidate')
    if data['stack'] == 'px4' and 'ap_candidate' in data:
        raise ConfigError('ap_candidate is only valid for arducopter')
    if data.get('control_protocol', 'legacy_v1') not in ('legacy_v1', 'session_v1'):
        raise ConfigError('control_protocol must explicitly select legacy_v1 or session_v1')
    if 'runtime_profile' in data:
        if data['runtime_profile'] != 'independent_quad_dds_v1' or data.get('control_protocol') != 'session_v1':
            raise ConfigError('Independent runtime_profile requires independent_quad_dds_v1 and session_v1')
    if 'restart_control_on_ground' in data:
        if type(data['restart_control_on_ground']) is not bool:
            raise ConfigError('restart_control_on_ground must be a boolean')
        if data['restart_control_on_ground'] and data.get('control_protocol') != 'session_v1':
            raise ConfigError('Ground control restart requires session_v1')
    for key in ('dds_workspace', 'prometheus_workspace', 'px4_root', 'ap_candidate', 'model_library',
                'display_socket', 'telemetry_socket'):
        if key in data:
            value = data[key]
            if (not isinstance(value, str) or not value.startswith('/') or value.startswith('//')
                    or '\\' in value or any(ord(c) < 32 for c in value)
                    or '..' in PurePosixPath(value).parts):
                raise ConfigError(f'{key} must be an absolute Linux path without traversal/control characters')
    for key in ('display_socket', 'telemetry_socket'):
        if key not in data:
            continue
        socket = PurePosixPath(data[key])
        if (len(socket.parts) != 4 or socket.parts[1] != 'tmp'
                or data['run_id'] not in socket.parent.name
                or len(data[key].encode('utf-8')) > 107):
            raise ConfigError(f'{key} must be /tmp/<directory containing run_id>/<socket>, at most 107 UTF-8 bytes')
    if ('telemetry_socket' in data and 'display_socket' in data
            and PurePosixPath(data['telemetry_socket']) == PurePosixPath(data['display_socket'])):
        raise ConfigError('telemetry_socket and display_socket must be distinct')
    requested = data.get('capabilities', ['native_position_mission'])
    if (not isinstance(requested, list) or not requested or
            any(not isinstance(item, str) or not item for item in requested) or
            len(set(requested)) != len(requested)):
        raise ConfigError('capabilities must be a nonempty list of unique capability identifiers')
    result = dict(data, capabilities=list(requested))
    if 'mission' in data:
        if data.get('control_protocol') != 'session_v1':
            raise ConfigError('mission requires explicit session_v1')
        if data.get('restart_control_on_ground', False):
            raise ConfigError('mission cannot be combined with restart_control_on_ground=true')
        try:
            result['mission'] = validate_mission(data['mission'])
        except ValueError as error:
            raise ConfigError(str(error)) from error
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ConfigError(f'Invalid JSON constant: {value}')


def load_config(path):
    """Load strict JSON and validate; all expected input failures use ConfigError."""
    try:
        return validate_config(json.loads(Path(path).read_text(encoding='utf-8'),
                                         object_pairs_hook=_unique_object,
                                         parse_constant=_invalid_constant))
    except (OSError, UnicodeError, ValueError) as error:
        raise ConfigError(str(error)) from error
