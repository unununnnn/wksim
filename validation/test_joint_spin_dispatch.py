"""Coalescing may not suppress permissions or explicit phase transitions."""
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
import unittest

from validation.test_joint_lifecycle_deadline import SCENE_AVAILABLE
if SCENE_AVAILABLE:
    from Simulator.wksim_runtime.joint_lifecycle import JointLifecycle


@unittest.skipUnless(SCENE_AVAILABLE,'Explicit scene source/candidate required')
class DispatchTests(unittest.TestCase):
    def instance(self):
        v=JointLifecycle.__new__(JointLifecycle)
        v.phase='running';v.sequence=0;v.next_publish=0.;v.next_spin=1000.
        v.clock=NS(epoch='epoch',tick=4,last_request=0,recoverable=False)
        v.run_id='run';v.faulted_uav_ids=[];v.acks={1:'old'};v.observer=NS(phase='running')
        v.Message=NS;v.publisher=Mock();v.clock_publisher=Mock();v.serialize=lambda m:b'wire'
        v.ros=Mock();v.node=object();v.record=Mock()
        return v

    def test_due_permission_is_not_deferred_with_executor(self):
        v=self.instance()
        with patch('Simulator.wksim_runtime.joint_lifecycle.time.monotonic',return_value=10.):v.periodic()
        v.publisher.publish.assert_called_once();v.ros.spin_once.assert_not_called()
        self.assertEqual(v.sequence,1)
        self.assertEqual(v.next_publish,10.1)

    def test_explicit_phase_always_dispatches_and_clears_old_acks(self):
        v=self.instance()
        with patch('Simulator.wksim_runtime.joint_lifecycle.time.monotonic',return_value=10.):v.set_phase('paused')
        v.ros.spin_once.assert_called_once_with(v.node,timeout_sec=0)
        v.publisher.publish.assert_called_once();v.clock_publisher.publish.assert_called_once_with(v.clock)
        self.assertEqual(v.acks,{})
        self.assertEqual(v.observer.phase,'paused')


if __name__=='__main__':unittest.main()
