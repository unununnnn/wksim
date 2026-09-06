"""Only the diagnostic trigger is modeled here; flight evidence uses actual FCs."""
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'tools'))
from joint_pause_probe import PauseProbe


class PauseTriggerTests(unittest.TestCase):
    def setUp(self):
        self.probe = PauseProbe.__new__(PauseProbe)
        self.probe.clock = NS(tick=100, last_barrier=100, synchronized=True, phase='running', pending=None)
        self.probe.sessions = {uid:NS(version=1, run_id='current', source_received_valid=True,
            source_received_monotonic_s=time.monotonic(), published_monotonic_s=time.monotonic(),
            state=NS(uav_id=uid, connected=True, odom_valid=True, armed=True),
            control=NS(uav_id=uid, control_state=1, COMMAND_CONTROL=1, failsafe=False)) for uid in (1, 2)}
        self.states = {stack:[0.]*8+[-3.]+[0.]*111 for stack in ('arducopter', 'px4')}

    def ready(self):
        return self.probe.ready('current', self.states)

    def test_requires_both_real_truth_heights_and_completed_barrier(self):
        self.assertTrue(self.ready())
        self.states['px4'][8] = -2.4
        self.assertFalse(self.ready())
        self.states['px4'][8] = -3.
        self.probe.clock.last_barrier = 96
        self.assertFalse(self.ready())

    def test_rejects_foreign_run_or_nested_vehicle_before_pause(self):
        self.probe.sessions[2].run_id = 'retired'
        self.assertFalse(self.ready())
        self.probe.sessions[2].run_id = 'current'
        self.probe.sessions[2].control.uav_id = 1
        self.assertFalse(self.ready())

    def test_repeated_publication_does_not_make_stale_or_future_source_fresh(self):
        session = self.probe.sessions[1]
        for stamp in (time.monotonic()-3, time.monotonic()+3, float('nan')):
            session.source_received_monotonic_s = stamp
            self.assertFalse(self.ready())


if __name__ == '__main__':
    unittest.main()
