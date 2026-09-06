"""Read-only corroboration against independent physical record windows.

Public boot-clock duration is not used to relabel or reconstruct physical time.
Vehicle60 NED positions [6:9], NED/FRD quaternion wxyz [12:16] match state_stream.
"""
import json
import math
from pathlib import Path


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Expected finite non-boolean number')
    return value


def audit_mission_truth(path, mission):
    if mission['state'] not in ('completed', 'cancelled'):
        raise ValueError('Mission has no successful terminal disposition')
    rows = []
    with Path(path).open(encoding='utf-8') as source:
        for line in source:
            if not line.endswith('\n'):
                break
            row = json.loads(line)
            stamp = number(row['time'])
            if rows and stamp <= rows[-1]['time']:
                raise ValueError('Physical time must strictly advance')
            vector = row['vehicle']
            if len(vector) != 60:
                raise ValueError('Expected Vehicle60 physical truth')
            n, e, d = (number(v) for v in vector[6:9])
            w, x, y, z = (number(v) for v in vector[12:16])
            if abs(math.hypot(w, x, y, z) - 1) > 1e-3:
                raise ValueError('Invalid physical quaternion')
            yaw = math.pi/2 - math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
            rows.append(dict(time=stamp, position=[e, n, -d], yaw=yaw))
    if not rows:
        raise ValueError('No complete physical records')

    def cursor(value):
        count = value['records']
        if type(count) is not int or not 1 <= count <= len(rows):
            raise ValueError('Physical cursor outside complete records')
        if number(value['final_time']) != rows[count-1]['time']:
            raise ValueError('Physical cursor time does not match its record')
        return count

    points = mission['waypoints']
    if len(points) > len(mission['plan']['waypoints']):
        raise ValueError('More dispatched waypoints than the accepted plan')
    completed, previous_end, partial = [], 0, False
    for index, point in enumerate(points, 1):
        if type(point['index']) is not int or point['index'] != index:
            raise ValueError('Waypoint identities must be an ordered unique prefix')
        if point['status'] != 'completed':
            if point['status'] != 'running' or partial or index != len(points):
                raise ValueError('Only the last dispatched waypoint may remain running')
            partial = True
            continue
        if partial:
            raise ValueError('Completed waypoints must be a continuous prefix')
        start, end = cursor(point['dwell_start_truth']), cursor(point['dwell_end_truth'])
        if start < previous_end or end - start < 2:
            raise ValueError('Overlapping or insufficient physical dwell window')
        if number(point['dwell_end_boot_s']) - number(point['dwell_start_boot_s']) < number(point['dwell_s']):
            raise ValueError('Public boot dwell did not complete')
        target = [number(v) for v in point['target_enu_m']]
        if len(target) != 3:
            raise ValueError('Expected three target coordinates')
        yaw = number(point['yaw_enu_rad'])
        errors, speeds, yaw_errors = [], [], []
        for offset in range(start, end):
            row, before = rows[offset], rows[offset-1]
            errors.append(math.dist(row['position'], target))
            speeds.append(math.dist(row['position'], before['position'])/(row['time']-before['time']))
            yaw_errors.append(abs(math.remainder(row['yaw']-yaw, 2*math.pi)))
        metrics = dict(index=index, start_record_exclusive=start, end_record_inclusive=end,
                       physical_duration_s=rows[end-1]['time']-rows[start-1]['time'],
                       max_position_error_m=max(errors), max_speed_m_s=max(speeds),
                       max_yaw_error_rad=max(yaw_errors))
        if max(errors) > 0.5 or max(speeds) > 0.5 or max(yaw_errors) > 0.15:
            raise ValueError('Physical waypoint integration threshold exceeded: ' + json.dumps(metrics))
        completed.append(metrics)
        previous_end = end
    if mission['state'] == 'completed' and len(completed) != len(mission['plan']['waypoints']):
        raise ValueError('Completed mission is missing completed waypoints')
    return dict(ok=True, completed_waypoints=completed, complete_physical_records=len(rows),
                thresholds=dict(position_m=0.5, speed_m_s=0.5, yaw_rad=0.15),
                clocks='public boot dwell and independent physical intervals are separate')
