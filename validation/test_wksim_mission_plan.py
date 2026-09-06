"""Mission contract checks only: no ROS substitutes or flight claims."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Simulator'))
from wksim_runtime.config import ConfigError, load_config, validate_config
from wksim_runtime.mission_plan import resolve_waypoint, validate_mission

EXAMPLES = Path(__file__).resolve().parents[1] / 'Simulator/wksim_runtime/examples'


def mission(**point):
    return {'version': 1, 'cancel_policy': 'land',
            'waypoints': [dict(frame='enu', position_m=[2, 3, 3], **point)]}


class MissionPlanTests(unittest.TestCase):
    def test_defaults_and_deepcopy(self):
        source = mission()
        normalized = validate_mission(source)
        self.assertEqual(normalized['waypoints'][0]['yaw_rad'], 0)
        self.assertEqual(normalized['waypoints'][0]['dwell_s'], 2)
        normalized['waypoints'][0]['position_m'][0] = 10
        normalized['waypoints'].append({})
        self.assertEqual(source, mission())

    def test_strict_mission(self):
        invalid = [None, [], {}, dict(mission(), extra=1)]
        for field in mission():
            item = mission()
            del item[field]
            invalid.append(item)
        for version in (True, 1.0, 0, 2, '1'):
            invalid.append(dict(mission(), version=version))
        for policy in (None, 'hold', True, {}):
            invalid.append(dict(mission(), cancel_policy=policy))
        for points in ([], [mission()['waypoints'][0]] * 9, {}, None, ()):
            invalid.append(dict(mission(), waypoints=points))
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_mission(item)
        self.assertEqual(len(validate_mission(dict(mission(), waypoints=mission()['waypoints'] * 8))['waypoints']), 8)

    def test_strict_waypoint_and_numbers(self):
        point = mission()['waypoints'][0]
        invalid = [None, [], {}, dict(point, extra=1)]
        for field in point:
            item = dict(point)
            del item[field]
            invalid.append(item)
        for frame in ('ned', None, {}, True):
            invalid.append(dict(point, frame=frame))
        for value in (None, [], [1, 2], [1, 2, 3, 4], '123'):
            invalid.append(dict(point, position_m=value))
        for value in (True, False, '2', None, math.nan, math.inf, -math.inf, 10**400):
            for field in ('yaw_rad', 'dwell_s'):
                invalid.append(dict(point, **{field: value}))
            for axis in range(3):
                position = [2, 3, 3]
                position[axis] = value
                invalid.append(dict(point, position_m=position))
        for field, values in [('yaw_rad', [-math.pi-0.001, math.pi+0.001]),
                              ('dwell_s', [1.999, 10.001])]:
            invalid.extend(dict(point, **{field: value}) for value in values)
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_mission(dict(mission(), waypoints=[item]))

    def test_position_and_scalar_boundaries(self):
        for frame, bounds in [('enu', [(-20, 20), (-20, 20), (1, 10)]),
                              ('body_flu', [(-10, 10)] * 3)]:
            for axis, (low, high) in enumerate(bounds):
                for value in (low, high, low-0.001, high+0.001):
                    point = {'frame': frame, 'position_m': [0, 0, 3]}
                    point['position_m'][axis] = value
                    data = dict(mission(), waypoints=[point])
                    with self.subTest(frame=frame, axis=axis, value=value):
                        if low <= value <= high:
                            validate_mission(data)
                        else:
                            with self.assertRaises(ValueError):
                                validate_mission(data)
        for yaw in (-math.pi, math.pi):
            for dwell in (2, 10):
                validate_mission(mission(yaw_rad=yaw, dwell_s=dwell))

    def test_enu_is_absolute_and_independent(self):
        point = mission(yaw_rad=math.pi)['waypoints'][0]
        result = resolve_waypoint(point, [10, 10, 5], -1)
        self.assertEqual(result, {'position_enu_m': [2, 3, 3], 'yaw_enu_rad': math.pi})
        result['position_enu_m'][0] = 0
        self.assertEqual(point['position_m'], [2, 3, 3])

    def test_body_rotation_and_relative_yaw(self):
        point = {'frame': 'body_flu', 'position_m': [1, 2, 1], 'yaw_rad': math.pi/2}
        for heading, expected in [(0, [4, 6, 4]), (math.pi/2, [1, 5, 4]),
                                  (-math.pi/2, [5, 3, 4]), (math.pi, [2, 2, 4])]:
            result = resolve_waypoint(point, [3, 4, 3], heading)
            for actual, target in zip(result['position_enu_m'], expected):
                self.assertAlmostEqual(actual, target)
            self.assertAlmostEqual(math.sin(result['yaw_enu_rad']), math.sin(heading+math.pi/2))
            self.assertAlmostEqual(math.cos(result['yaw_enu_rad']), math.cos(heading+math.pi/2))
            self.assertTrue(-math.pi <= result['yaw_enu_rad'] <= math.pi)

    def test_resolved_bounds_and_invalid_snapshot(self):
        for origin, offset in [([20, 0, 3], [1, 0, 0]), ([-20, 0, 3], [-1, 0, 0]),
                               ([0, 20, 3], [0, 1, 0]), ([0, -20, 3], [0, -1, 0]),
                               ([0, 0, 10], [0, 0, 1]), ([0, 0, 1], [0, 0, -1])]:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                resolve_waypoint({'frame': 'body_flu', 'position_m': offset}, origin, 0)
        point = {'frame': 'body_flu', 'position_m': [0, 0, 0]}
        for position, yaw in [([0, 0], 0), ([True, 0, 3], 0), ([math.inf, 0, 3], 0),
                              ([0, 0, 3], math.nan), ([0, 0, 3], True)]:
            with self.assertRaises(ValueError):
                resolve_waypoint(point, position, yaw)

    def test_config_combinations_and_examples(self):
        for stack in ('px4', 'arducopter'):
            base = json.loads((EXAMPLES / f'{stack}-session.json').read_text())
            legacy = dict(base)
            del legacy['control_protocol']
            self.assertEqual(validate_config(legacy), legacy)
            self.assertEqual(validate_config(dict(legacy, control_protocol='legacy_v1')),
                             dict(legacy, control_protocol='legacy_v1'))
            for config in (legacy, dict(base, control_protocol='legacy_v1')):
                with self.assertRaises(ConfigError):
                    validate_config(dict(config, mission=mission()))
            for value in (None, {}, dict(mission(), extra=1)):
                with self.assertRaises(ConfigError):
                    validate_config(dict(base, mission=value))
            source = dict(base, mission=mission(), restart_control_on_ground=False)
            before = copy.deepcopy(source)
            result = validate_config(source)
            result['mission']['waypoints'][0]['position_m'][0] = 10
            self.assertEqual(source, before)
            example = load_config(EXAMPLES / f'{stack}-mission.json')
            self.assertNotEqual(example['run_id'], base['run_id'])
            self.assertEqual({k: v for k, v in example.items() if k not in ('mission', 'run_id')},
                             {k: v for k, v in base.items() if k != 'run_id'})
            self.assertEqual(example['mission'], {'version': 1, 'cancel_policy': 'land', 'waypoints': [
                {'frame': 'enu', 'position_m': [2, 3, 3], 'yaw_rad': 0, 'dwell_s': 2},
                {'frame': 'enu', 'position_m': [2, 3, 3], 'yaw_rad': math.pi/2, 'dwell_s': 2},
                {'frame': 'body_flu', 'position_m': [1, 0, 0], 'yaw_rad': 0, 'dwell_s': 2}]})


if __name__ == '__main__':
    unittest.main()
