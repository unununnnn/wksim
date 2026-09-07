"""Initial formal joint-scene configuration; unsupported products are explicit."""
import re
import math
from pathlib import PurePosixPath

from .config import ConfigError
from .joint_rate import validate_rate


def validate_joint_config(data):
    required={'schema_version','kind','run_id','runtime_profile'}
    if not isinstance(data,dict) or set(data)-required-{'task','requested_rate','task_dwell_seconds','display_socket'} or required-set(data):
        raise ConfigError('Joint configuration requires schema_version/kind/run_id/runtime_profile; optional task/requested_rate/task_dwell_seconds')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['kind']!='joint_scene':
        raise ConfigError('Unsupported joint configuration version/kind')
    if not isinstance(data['run_id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',data['run_id']):
        raise ConfigError('Invalid joint run_id')
    if not isinstance(data['runtime_profile'],str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',data['runtime_profile']):
        raise ConfigError('Invalid joint runtime_profile')
    if data.get('task','public_position')!='public_position':
        raise ConfigError('Only the Prometheus public_position task is implemented for this initial joint profile')
    if 'display_socket' in data:
        path=data['display_socket']
        if not isinstance(path,str):raise ConfigError('display_socket must be a Linux pathname')
        parsed=PurePosixPath(path)
        if (str(parsed)!=path or parsed.parent.parent!=PurePosixPath('/tmp') or parsed.name!='state.sock'
                or data['run_id'] not in parsed.parent.name or not re.fullmatch('[A-Za-z0-9_-]+',parsed.parent.name)
                or len(path.encode())>107):
            raise ConfigError('Joint display_socket requires /tmp/<private directory containing run_id>/state.sock')
    try: rate=validate_rate(data.get('requested_rate',.5))
    except ValueError as error: raise ConfigError(str(error)) from error
    dwell=data.get('task_dwell_seconds',{})
    if (not isinstance(dwell,dict) or set(dwell)-{'hold','waypoint'}
            or any(type(value) not in (int,float) or not math.isfinite(value)
                   or not {'hold':5,'waypoint':2}[key]<=value<=600 for key,value in dwell.items())):
        raise ConfigError('task_dwell_seconds accepts hold in 5..600 and waypoint in 2..600 finite seconds')
    return dict(data,task='public_position',requested_rate=rate,
                task_dwell_seconds={'hold':5,'waypoint':2}|dwell)
