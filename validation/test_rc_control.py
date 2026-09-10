import math
import unittest
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from geometry_msgs.msg import Quaternion
from prometheus_msgs.msg import UAVControlState as Control, UAVState
from prometheus_control.command import CommandProcessor, Desired
from prometheus_control.node import ControlNode
from prometheus_control.shaping import SetpointShaper
from prometheus_msgs.msg import UAVSetup
from Simulator.wksim_control.rc_input import RCInput
from validation.test_rc_input import IDENTITY, frame


def state(position=(1., 2., 3.), yaw=0., armed=True):
    return UAVState(connected=True, armed=armed, odom_valid=True, location_source=UAVState.GPS,
                    position=list(position), attitude_q=Quaternion(w=math.cos(yaw/2), z=math.sin(yaw/2)))


class RCCommandSeamTests(unittest.TestCase):
    def test_rc_desired_replaces_hover_and_clear_restores_hover(self):
        processor = CommandProcessor()
        processor.update_state(state())
        self.assertTrue(processor.enter_control(Control.RC_POS_CONTROL).accepted)
        self.assertEqual(processor.step().position, (1., 2., 3.))
        desired = Desired('position', position=(4., 5., 3.), yaw=.25)
        self.assertTrue(processor.set_rc_desired(desired).accepted)
        self.assertEqual(processor.step(), desired)
        processor.clear_rc_desired()
        self.assertEqual(processor.step().position, (1., 2., 3.))

    def test_rc_seam_rejects_wrong_kind_or_command_state(self):
        processor = CommandProcessor()
        self.assertEqual(processor.set_rc_desired(Desired('position', position=(1., 2., 3.), yaw=0.)).reason,
                         'not_rc_pos_control')
        processor.update_state(state())
        self.assertTrue(processor.enter_control(Control.RC_POS_CONTROL).accepted)
        for desired in (Desired('velocity', velocity=(1., 0., 0.), yaw=0.),
                        Desired('position', position=(1., 2.), yaw=0.),
                        Desired('position', position=(1., 2., 3.), yaw=math.nan)):
            with self.subTest(desired=desired):
                self.assertFalse(processor.set_rc_desired(desired).accepted)
        self.assertIsNone(processor.rc_desired)

    def test_disarm_clears_rc_target_and_control(self):
        processor = CommandProcessor()
        processor.update_state(state())
        processor.enter_control(Control.RC_POS_CONTROL)
        processor.set_rc_desired(Desired('position', position=(4., 5., 3.), yaw=0.))
        grounded = state(armed=False)
        processor.update_state(grounded)
        self.assertEqual(processor.control_state, Control.INIT)
        self.assertIsNone(processor.rc_desired)


class RCNodeTests(unittest.TestCase):
    def node(self):
        processor = CommandProcessor()
        processor.update_state(state())
        processor.home = (0., 0., 0.)
        processor.enter_control(Control.COMMAND_CONTROL)
        node = NS(rc_input=RCInput(IDENTITY), processor=processor, native_generation=1,
            state=state(), event=Mock(), operation=None, warmup_target=None, revoked=False,
            shaper=SetpointShaper(), request_context=5, command_request_id=0,
            operation_ns=lambda: 100_000_000, operation_time=lambda: .1,
            input_stamp=lambda header: 1, rc_sub=NS(topic_name='/uav1/prometheus/v2/rc_input'),
            get_publishers_info_by_topic=lambda topic: [NS(endpoint_gid=b'one')],
            native=NS(pending=None, available=lambda: True, ready_external=True,
                      flying=True, position_yaw=True, external_mode='OFFBOARD', request=Mock(), cancel_request=Mock()))
        node.state.mode = 'OFFBOARD'
        node.activate = lambda: ControlNode.activate(node)
        node.revoke = lambda reason: ControlNode.revoke(node, reason)
        return node

    def bind(self, node, payload=None):
        with patch('prometheus_control.node.time.monotonic_ns', return_value=1_000_000_100):
            ControlNode.on_rc(node, NS(data=json.dumps(payload or frame())), NS(publisher_gid=b'one'))

    def setup(self, node, mode='RC_POS_CONTROL'):
        with patch('prometheus_control.node.time.monotonic_ns', return_value=1_000_000_200):
            ControlNode.on_setup(node, UAVSetup(cmd=UAVSetup.SET_CONTROL_MODE, control_state=mode))

    def test_actual_message_info_wall_clock_and_airborne_activation(self):
        node = self.node(); self.bind(node); self.setup(node)
        self.assertEqual(node.rc_input.received_ns, 1_000_000_100)
        self.assertEqual(node.rc_input.last_step_ns, 100_000_000)
        self.assertEqual(node.processor.control_state, Control.RC_POS_CONTROL)
        self.assertEqual(node.command_request_id, 5)
        node.native.request.assert_not_called()

    def test_rc_cannot_takeoff_change_mode_or_choose_multiple_sources(self):
        for field in ('ground', 'mode', 'writers', 'no_candidate'):
            node = self.node()
            if field != 'no_candidate': self.bind(node)
            if field == 'ground': node.native.flying = False
            if field == 'mode': node.state.mode = 'AUTO.LOITER'
            if field == 'writers': node.get_publishers_info_by_topic = lambda _: [NS(endpoint_gid=b'one'), NS(endpoint_gid=b'two')]
            self.setup(node)
            self.assertEqual(node.event.call_args.args[0], 'setup_rejected', field)
            node.native.request.assert_not_called()
            self.assertEqual(node.processor.control_state, Control.COMMAND_CONTROL)

    def test_explicit_handoff_and_retired_stream_never_replay(self):
        node = self.node(); self.bind(node); self.setup(node)
        self.setup(node, 'COMMAND_CONTROL')
        self.assertEqual(node.event.call_args.kwargs['reason'], 'rc_to_command_requires_neutral_intent')
        channels = [1500, 1500, 1500, 1500, 1000, 2000, 1000, 1000]
        self.bind(node, frame(sequence=2, produced=1_000_000_050, channels=channels))
        self.setup(node, 'COMMAND_CONTROL')
        self.assertEqual(node.processor.control_state, Control.COMMAND_CONTROL)
        self.bind(node, frame(sequence=3, produced=1_000_000_060))
        self.assertEqual(node.event.call_args.kwargs['reason'], 'retired_stream')
        self.bind(node, frame(stream='d'*32))
        self.assertEqual(node.rc_input.state, 'CANDIDATE')
        self.assertEqual(node.processor.control_state, Control.COMMAND_CONTROL)

    def test_malformed_owner_revokes_but_foreign_gid_does_not(self):
        node = self.node(); self.bind(node); self.setup(node)
        with patch('prometheus_control.node.time.monotonic_ns', return_value=1_000_000_100):
            ControlNode.on_rc(node, NS(data='broken'), NS(publisher_gid=b'two'))
        self.assertEqual(node.rc_input.state, 'ACTIVE_RC')
        with patch('prometheus_control.node.time.monotonic_ns', return_value=1_000_000_100):
            ControlNode.on_rc(node, NS(data='broken'), NS(publisher_gid=b'one'))
        self.assertTrue(node.revoked)
        self.assertEqual(node.processor.control_state, Control.INIT)
        node.native.cancel_request.assert_called_once()

    def test_rc_disarm_or_invalid_navigation_stops_before_publish(self):
        for field in ('armed','odom_valid'):
            node=self.node(); self.bind(node); self.setup(node)
            node.scene=None; node.native.generation=1
            setattr(node.state,field,False)
            with self.assertRaisesRegex(ValueError,'rc_armed_or_navigation_lost'):
                ControlNode.drive(node)
            node.native.request.assert_not_called()

    def test_withdrawn_independent_task_can_observe_explicit_native_hold(self):
        node=self.node()
        node.scene=None; node.native.generation=1; node.native.failed=True
        node.revoked=True; node.processor.enter_control(Control.INIT)
        node.operation=dict(stage='simple',action='mode',value='AUTO.LOITER')
        node.advance=Mock(); node.wall=lambda:1.; node.last_output=0.; node.output_period=.025
        ControlNode.drive(node)
        node.advance.assert_called_once()
        node.operation=dict(stage='simple',action='arm',value=True)
        with self.assertRaisesRegex(ValueError,'native_failsafe_control_released'):
            ControlNode.drive(node)


if __name__ == '__main__': unittest.main()
