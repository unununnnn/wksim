"""Boundary checks for the independent raw release auditor."""
import math
import unittest
from tools.audit_planner_release import stop_metrics,tick_of

class StopAuditTests(unittest.TestCase):
    def state(self,speed=0.,north=0.):
        value=[0.]*13;value[3]=speed;value[6]=north;return value
    def test_speed_or_drift_violation_is_rejected(self):
        self.assertEqual(stop_metrics(self.state(.25,1.),[0.,0.,0.]),(.25,1.))
        for state in (self.state(.250001),self.state(0.,1.000001),self.state(math.nan)):
            with self.assertRaises(ValueError):stop_metrics(state,[0.,0.,0.])
    def test_enu_transform_uses_original_physical_axes(self):
        state=self.state();state[6:9]=[3.,2.,-4.]
        self.assertEqual(stop_metrics(state,[2.,3.,4.]),(0.,0.))
    def test_noninteger_or_off_grid_times_rejected(self):
        self.assertEqual(tick_of(67940000000),67940)
        for bad in (0,1000001,1000000.,True):
            with self.assertRaises(ValueError):tick_of(bad)

if __name__=='__main__':unittest.main()
