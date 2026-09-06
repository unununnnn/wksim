"""Actual ControlNode operation clock seam; recordings here never arm a FC."""
import unittest
import os
from types import SimpleNamespace as NS
from unittest.mock import Mock

from prometheus_control.node import ControlNode


@unittest.skipUnless(os.environ.get('WKSIM_JOINT_CONTROL_TESTS') == '1', 'explicit new installed control candidate required')
class OperationClockTests(unittest.TestCase):
    def node(self, simulated):
        node = NS(operation_uses_sim_time=simulated, last_operation_time=None)
        node.sim_time, node.wall_time = 10., 100.
        node.get_parameter = lambda name: NS(value=simulated)
        node.get_clock = lambda: NS(now=lambda: NS(nanoseconds=round(node.sim_time*1e9)))
        node.wall = lambda: node.wall_time
        return node

    def test_default_wall_is_preserved(self):
        node = self.node(False)
        self.assertEqual(ControlNode.operation_time(node), 100.)
        node.sim_time = 500.
        self.assertEqual(ControlNode.operation_time(node), 100.)
        node.wall_time = 101.
        self.assertEqual(ControlNode.operation_time(node), 101.)

    def test_simulation_duration_does_not_follow_wall(self):
        node = self.node(True)
        self.assertEqual(ControlNode.operation_time(node), 10.)
        node.wall_time += 100.
        self.assertEqual(ControlNode.operation_time(node), 10.)
        node.sim_time += 1.
        self.assertEqual(ControlNode.operation_time(node), 11.)
        node.sim_time = 0.
        with self.assertRaises(ValueError):
            ControlNode.operation_time(node)
        node.sim_time = 10.5
        with self.assertRaisesRegex(ValueError, 'regressed'):
            ControlNode.operation_time(node)

    def test_clock_source_cannot_change_under_an_operation(self):
        node = self.node(True)
        node.get_parameter = lambda name: NS(value=False)
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            ControlNode.operation_time(node)

    def test_invalid_clock_rejects_setup_before_native_side_effect(self):
        from prometheus_msgs.msg import UAVSetup
        node=NS(input_stamp=lambda header:1, operation=None,
                operation_time=Mock(side_effect=ValueError('operation_clock_missing_or_regressed')),
                native=NS(pending=None,available=lambda:True,request=Mock()),
                state=NS(connected=True,armed=False,odom_valid=True),event=Mock())
        ControlNode.on_setup(node,UAVSetup(cmd=UAVSetup.ARMING,arming=True))
        node.native.request.assert_not_called()
        self.assertEqual(node.event.call_args.args[0],'setup_rejected')

    def test_invalid_clock_stops_already_active_cached_output(self):
        from prometheus_msgs.msg import UAVControlState
        target=NS(kind='local')
        node=NS(scene=None,operation=None,operation_time=Mock(side_effect=ValueError('operation_clock_missing_or_regressed')),
                processor=NS(control_state=UAVControlState.COMMAND_CONTROL,update_state=Mock(),
                             step=lambda:target,local_position=lambda:(0.,0.,3.)),
                native_generation=1,native=NS(generation=1,failed=False,ready_external=True,external_mode='OFFBOARD',
                                            request=Mock(),send=Mock()),
                state=NS(connected=True,odom_valid=True,mode='OFFBOARD'),
                shaper=NS(shape=lambda *args:target),wall=lambda:100.,last_output=0.,output_period=.025)
        with self.assertRaisesRegex(ValueError,'clock'):
            ControlNode.drive(node)
        node.native.request.assert_not_called()
        node.native.send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
