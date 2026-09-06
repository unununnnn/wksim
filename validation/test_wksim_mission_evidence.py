"""Synthetic unit fixtures for the read-only auditor; not flight evidence."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest

from Simulator.wksim_runtime.mission_evidence import audit_mission_truth


class MissionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'truth.jsonl'
        vehicle = [0.] * 60
        vehicle[6:9] = [3., 2., -3.]
        vehicle[12:16] = [math.sqrt(.5), 0., 0., math.sqrt(.5)]
        self.rows = [dict(time=i+1., vehicle=vehicle.copy()) for i in range(8)]
        point = dict(index=1, status='completed', target_enu_m=[2.,3.,3.], yaw_enu_rad=0., dwell_s=2.,
                     dwell_start_boot_s=100., dwell_end_boot_s=102.,
                     dwell_start_truth=dict(records=1, final_time=1.),
                     dwell_end_truth=dict(records=4, final_time=4.))
        self.mission = dict(state='completed', plan=dict(waypoints=[{}]), waypoints=[point])

    def audit(self, tail=''):
        self.path.write_text(''.join(json.dumps(r)+'\n' for r in self.rows)+tail, encoding='utf-8')
        return audit_mission_truth(self.path, self.mission)

    def test_different_physical_and_boot_durations_are_not_relabelled(self):
        report = self.audit('{')
        self.assertTrue(report['ok'])
        self.assertEqual(report['completed_waypoints'][0]['physical_duration_s'], 3)
        self.assertEqual(self.mission['waypoints'][0]['dwell_end_boot_s'], 102)

    def test_cancelled_empty_and_completed_prefix(self):
        self.mission.update(state='cancelled', waypoints=[])
        self.assertEqual(self.audit()['completed_waypoints'], [])
        self.mission['state'] = 'completed'
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.audit()

    def test_cursor_must_bind_to_exact_physical_record(self):
        for field, value in (('records', True), ('records', 0), ('records', 100), ('final_time', 9.)):
            before = deepcopy(self.mission)
            self.mission['waypoints'][0]['dwell_start_truth'][field] = value
            with self.assertRaises(ValueError):
                self.audit()
            self.mission = before

    def test_dwell_has_nonoverlapping_sufficient_samples_and_boot_duration(self):
        point = self.mission['waypoints'][0]
        point['dwell_end_truth'] = dict(records=2, final_time=2.)
        with self.assertRaisesRegex(ValueError, 'insufficient'):
            self.audit()
        point['dwell_end_truth'] = dict(records=4, final_time=4.)
        point['dwell_end_boot_s'] = 101.9
        with self.assertRaisesRegex(ValueError, 'boot dwell'):
            self.audit()
        point['dwell_end_boot_s'] = 102.
        second = deepcopy(point)
        second['index'] = 2
        self.mission['plan']['waypoints'].append({})
        self.mission['waypoints'].append(second)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            self.audit()

    def test_order_and_terminal_claims(self):
        self.mission['waypoints'][0]['index'] = 2
        with self.assertRaisesRegex(ValueError, 'identities'):
            self.audit()
        self.mission['waypoints'][0]['index'] = 1
        self.mission['state'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'terminal'):
            self.audit()

    def test_physical_position_speed_yaw_are_independent_gates(self):
        base = deepcopy(self.rows)
        for change in ('position', 'speed', 'yaw'):
            self.rows = deepcopy(base)
            if change == 'position':
                self.rows[2]['vehicle'][6] += 1
            elif change == 'speed':
                self.rows[2]['time'] = 2.1
                self.rows[2]['vehicle'][6] += .1
            else:
                self.rows[2]['vehicle'][12:16] = [1.,0.,0.,0.]
            with self.assertRaisesRegex(ValueError, 'threshold'):
                self.audit()

    def test_nonfinite_truth_and_clock_regression_rejected(self):
        self.rows[1]['time'] = self.rows[0]['time']
        with self.assertRaisesRegex(ValueError, 'advance'):
            self.audit()
        self.rows[1]['time'] = 2.
        self.rows[1]['vehicle'][6] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite'):
            self.audit()
        self.rows[1]['vehicle'][6] = 3.
        self.rows[1]['vehicle'][12] = 5.
        with self.assertRaisesRegex(ValueError, 'quaternion'):
            self.audit()


if __name__ == '__main__':
    unittest.main()
