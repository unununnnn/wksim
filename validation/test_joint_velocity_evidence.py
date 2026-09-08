"""Offline real-trace regression and single-field adversarial evidence checks."""
import copy
import json
from pathlib import Path
import sys
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime.velocity_evidence import verify_velocity_windows
from Simulator.wksim_runtime.joint_evidence import verify_tasks, final_run_status
from tools.audit_joint_velocity_yaw import audit


class VelocityEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = REPO/'validation/joint-velocity-yaw-nnh00wfp/run/epochs/ecd4969e2100465283e4f421054cf4e1'
        cls.result = json.loads((cls.root/'result.json').read_text())
        cls.task = next(t for t in cls.result['tasks'].values() if t['stack'] == 'arducopter')
        with (cls.root/'arducopter-truth.jsonl').open() as stream:
            cls.trace = [json.loads(line)['state'] for line in stream]

    def test_real_dispatch_and_fault_remains_failed(self):
        report = audit(self.root)
        self.assertEqual(report['physical_windows']['status'], 'pass')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['recorded_faults'][0]['type'], 'RateUnmet')
        with self.assertRaisesRegex(KeyError, 'waypoint_reached'):
            verify_tasks(self.root, self.result['epoch'], self.result['authority']['tick'], self.result['tasks'])

    def test_final_status_real_healthy_recovered_and_active_fault(self):
        for name in ('joint-rate-flow-82p4pbu7', 'joint-rate-flow-4kt7s0ei'):
            result = json.loads((REPO/'validation'/name/'run/result.json').read_text())
            self.assertEqual(final_run_status(result['epochs']), 'pass')
        # Replay the post-fix physical-completion outcome on the retained failed
        # epoch without altering its real active RateUnmet or any archived file.
        result = copy.deepcopy(self.result)
        result.update(status='stopped', flight_completed=True)
        self.assertEqual(final_run_status([{'result': result}]), 'failed')
        result['flight_completed'] = False
        self.assertEqual(final_run_status([{'result': result}]), 'stopped')

    def test_raw_physics_tampering(self):
        phases = {p['phase']: p['ros_time_ns']//1_000_000-1 for p in self.task['phases']}
        cases = [('velocity_step_settled', 4, 1.2, 'velocity'),
                 ('velocity_hold_settled', 3, .3, 'speed'),
                 ('velocity_hold_settled', 6, 100., 'drift'),
                 ('yaw_rate_tracking', 11, 0., 'integral'),
                 ('invalid_combo_rejected', 3, .3, 'speed')]
        for phase, axis, value, message in cases:
            with self.subTest(phase=phase, axis=axis):
                trace = self.trace.copy()
                index = phases[phase]
                trace[index] = trace[index].copy()
                trace[index][axis] = value
                with self.assertRaisesRegex(ValueError, message):
                    verify_velocity_windows(trace, self.task)

    def test_identity_ack_rejection_duration_tampering(self):
        for kind in ('request', 'ack', 'reject', 'duration', 'vehicle'):
            with self.subTest(kind=kind):
                task = copy.deepcopy(self.task)
                if kind == 'request':
                    task['task']['request_envelopes'][3]['request_id'] = 1
                elif kind == 'ack':
                    task['task']['events'] = [e for e in task['task']['events'] if e['event'] != 'native_ack']
                elif kind == 'reject':
                    next(e for e in task['task']['events'] if e['event'] == 'command_rejected')['event'] = 'command_accepted'
                elif kind == 'duration':
                    next(p for p in task['phases'] if p['phase'] == 'velocity_step_tracking')['ros_time_ns'] -= 1_000_000
                else:
                    task['uav_id'] = 2
                with self.assertRaises(ValueError):
                    verify_velocity_windows(self.trace, task)


if __name__ == '__main__':
    unittest.main()
