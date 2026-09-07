"""Lifecycle deadline logic only; no ROS, model, or flight evidence."""
from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

if importlib.util.find_spec('prometheus_control') is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ros2/src/prometheus_control'))
SCENE_AVAILABLE = importlib.util.find_spec('prometheus_control.scene') is not None
if SCENE_AVAILABLE:
    from Simulator.wksim_runtime.joint_lifecycle import JointLifecycle


@unittest.skipUnless(SCENE_AVAILABLE, 'Explicit joint control candidate/source required; historical default has no scene module')
class LifecycleDeadlineTests(unittest.TestCase):
    def lifecycle(self):
        value = JointLifecycle.__new__(JointLifecycle)
        value.clock = NS(phase='running', tick=0, last_request=1, epoch='current',
                         snapshot=lambda: dict(tick=4))
        value.phase, value.recovery_started = 'recovering', 10.
        value.acks, value.events, value.completed = {}, [], False
        value.record = Mock()
        value.set_phase = lambda phase: setattr(value, 'phase', phase)
        value.communication_fault = Mock(side_effect=lambda reason: value.set_phase('faulted'))
        return value

    def test_recovery_checks_deadline_even_when_advance_completes_readiness(self):
        for elapsed in (4.999, 5., 5.001):
            with self.subTest(elapsed=elapsed):
                value = self.lifecycle()
                now = [10.]
                value.acknowledged = lambda: bool(value.acks)
                def advance():
                    now[0] = 10.+elapsed
                    value.clock.tick = 4
                    value.acks = {uid: dict(source_boot_ns=1, task_control_released=True) for uid in (1, 2)}
                with patch('Simulator.wksim_runtime.joint_lifecycle.time.monotonic', side_effect=lambda: now[0]):
                    if elapsed < 5:
                        result = value.recover_physics(advance, dict(time_ns=0))
                        self.assertAlmostEqual(result['wall_seconds'], elapsed)
                        self.assertEqual(value.phase, 'running')
                    else:
                        with self.assertRaises(TimeoutError):
                            value.recover_physics(advance, dict(time_ns=0))
                        value.communication_fault.assert_called_once_with('native_recovery_readiness_timeout')
                        self.assertEqual(value.phase, 'faulted')
                        value.record.assert_not_called()

    def test_exercise_resume_checks_deadline_after_final_advance(self):
        for elapsed in (4.999, 5., 5.001):
            with self.subTest(elapsed=elapsed):
                value = self.lifecycle()
                value.clock.request = Mock()
                value.snapshot = lambda physics: dict(authority=dict(tick=value.clock.tick))
                value.pause_window = Mock()
                value.acknowledged = lambda: bool(value.acks)
                now = [10.]
                def advance():
                    value.clock.tick += 1
                    if value.phase == 'stepping' and value.clock.tick == 4:
                        value.clock.phase = 'paused'
                    if value.phase == 'resuming':
                        now[0] = 10.+elapsed
                        value.clock.tick = 8
                        value.acks = {uid: dict(source_boot_ns=8000000) for uid in (1, 2)}
                with patch('Simulator.wksim_runtime.joint_lifecycle.time.monotonic', side_effect=lambda: now[0]):
                    if elapsed < 5:
                        self.assertEqual(value.exercise(None, None, advance)['status'], 'pass')
                        self.assertTrue(value.completed)
                    else:
                        with self.assertRaises(TimeoutError):
                            value.exercise(None, None, advance)
                        self.assertFalse(value.completed)
                        self.assertEqual(value.phase, 'resuming')
                        self.assertFalse(any(event['action'] == 'resume' for event in value.events))


if __name__ == '__main__':
    unittest.main()
