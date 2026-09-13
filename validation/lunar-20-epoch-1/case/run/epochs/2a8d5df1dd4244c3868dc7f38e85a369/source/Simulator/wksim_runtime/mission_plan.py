"""Pure mission input validation and independent target snapshot estimation.

These bounds are the current quad-X task input safety envelope, not a formal
numerical equivalence budget. Body snapshots do not replace XYZ_POS_BODY commands.
"""
import math
from numbers import Real


def _real(value, name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f'{name} must be a finite non-boolean real number')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f'{name} must be finite') from error
    if not math.isfinite(result):
        raise ValueError(f'{name} must be finite')
    return result


def _vector(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f'{name} must contain three real numbers')
    return [_real(item, name) for item in value]


def _enu_bounds(position):
    if not (-20 <= position[0] <= 20 and -20 <= position[1] <= 20
            and 1 <= position[2] <= 10):
        raise ValueError('ENU position must satisfy x/y [-20,20], z [1,10]')


def _waypoint(data):
    required = {'frame', 'position_m'}
    allowed = required | {'yaw_rad', 'dwell_s'}
    if not isinstance(data, dict) or required - data.keys() or data.keys() - allowed:
        raise ValueError('waypoint requires frame/position_m and only allows yaw_rad/dwell_s')
    if data['frame'] not in ('enu', 'body_flu'):
        raise ValueError('waypoint frame must be enu or body_flu')
    position = _vector(data['position_m'], 'position_m')
    if data['frame'] == 'enu':
        _enu_bounds(position)
    elif any(not -10 <= axis <= 10 for axis in position):
        raise ValueError('body_flu offsets must be in [-10,10] on every axis')
    yaw = _real(data.get('yaw_rad', 0), 'yaw_rad')
    dwell = _real(data.get('dwell_s', 2), 'dwell_s')
    if not -math.pi <= yaw <= math.pi:
        raise ValueError('yaw_rad must be in [-pi,pi]')
    if not 2 <= dwell <= 10:
        raise ValueError('dwell_s must be in [2,10]')
    return {'frame': data['frame'], 'position_m': position,
            'yaw_rad': yaw, 'dwell_s': dwell}


def validate_mission(data):
    """Return a deeply independent normalized dict, or raise ValueError."""
    if not isinstance(data, dict) or data.keys() != {'version', 'waypoints', 'cancel_policy'}:
        raise ValueError('mission requires exactly version, waypoints, cancel_policy')
    if type(data['version']) is not int or data['version'] != 1:
        raise ValueError('mission version must be integer 1')
    if data['cancel_policy'] != 'land':
        raise ValueError('mission cancel_policy must be land')
    points = data['waypoints']
    if not isinstance(points, list) or not 1 <= len(points) <= 8:
        raise ValueError('mission waypoints must be a list of 1..8 waypoints')
    return {'version': 1, 'waypoints': [_waypoint(point) for point in points],
            'cancel_policy': 'land'}


def resolve_waypoint(waypoint, position, yaw):
    """Estimate an ENU target from a current ENU position and heading snapshot."""
    point = _waypoint(waypoint)
    target = point['position_m']
    target_yaw = point['yaw_rad']
    if point['frame'] == 'body_flu':
        origin = _vector(position, 'position')
        heading = _real(yaw, 'yaw')
        c, s = math.cos(heading), math.sin(heading)
        x, y, z = target
        target = [origin[0] + c*x - s*y, origin[1] + s*x + c*y, origin[2] + z]
        target_yaw = (heading % math.tau + target_yaw + math.pi) % math.tau - math.pi
    _enu_bounds(target)
    return {'position_enu_m': target, 'yaw_enu_rad': target_yaw}
