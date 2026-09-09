import math
import unittest

from geometry_msgs.msg import Quaternion
from prometheus_msgs.msg import UAVControlState as Control, UAVState
from prometheus_control.command import CommandProcessor, Desired


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


if __name__ == '__main__': unittest.main()
