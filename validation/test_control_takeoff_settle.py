"""Regression for observed AP height-crossing versus final takeoff yaw reset."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
import unittest
from prometheus_control.node import ControlNode


class TakeoffSettleTests(unittest.TestCase):
    def node(self):
        node=NS(now=0.,operation=dict(stage='takeoff',deadline=25.,ack=True),
            native=NS(external_mode='GUIDED',flying=True,ready_external=True),
            state=NS(odom_valid=True,position=[0.,0.,2.9],velocity=[0.,0.,.8]),
            warmup_target=NS(position=(0.,0.,3.)),activate=Mock())
        node.operation_time=lambda:node.now
        return node

    def test_ap_height_crossing_cannot_finish_rising_takeoff(self):
        node=self.node()
        ControlNode.advance(node)
        node.now=1.;ControlNode.advance(node)
        node.activate.assert_not_called()
        node.state.velocity=[0.,0.,.2]
        ControlNode.advance(node)
        node.now=1.4;ControlNode.advance(node)
        node.activate.assert_not_called()
        node.state.velocity=[0.,0.,.4];node.now=1.49;ControlNode.advance(node)
        node.state.velocity=[0.,0.,0.];node.now=1.5;ControlNode.advance(node)
        node.now=2.;ControlNode.advance(node)
        node.activate.assert_called_once()

    def test_reset_settling_deadline_still_blocks_activation(self):
        node=self.node();node.state.velocity=[0.,0.,0.]
        node.operation['settled_after']=1.
        ControlNode.advance(node)
        node.now=.7;ControlNode.advance(node)
        node.activate.assert_not_called()
        node.now=1.;ControlNode.advance(node)
        node.activate.assert_called_once()

    def test_px4_retains_its_existing_warmup_path(self):
        node=self.node();node.native.external_mode='OFFBOARD'
        ControlNode.advance(node)
        self.assertEqual(node.operation['stage'],'warmup')
        node.activate.assert_not_called()


if __name__=='__main__':unittest.main()
