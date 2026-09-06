"""Command semantics, using the real generated ROS2 Prometheus messages."""
from copy import deepcopy
import math
import unittest

from geometry_msgs.msg import Quaternion
from prometheus_msgs.msg import UAVCommand as Cmd, UAVControlState as Control, UAVState
from prometheus_control.command import CommandProcessor, Desired
from prometheus_control.shaping import SetpointShaper, float32


def state(position=(10., 20., 2.), yaw=0., armed=True):
    return UAVState(connected=True, armed=armed, odom_valid=True, location_source=UAVState.GPS,
                    position=list(position), attitude_q=Quaternion(w=math.cos(yaw/2), z=math.sin(yaw/2)))


def processor(yaw=0., **kwargs):
    obj = CommandProcessor(**kwargs)
    obj.update_state(state(yaw=yaw, armed=False))
    obj.set_offset(1., 2.)
    obj.update_state(state(yaw=yaw))
    assert obj.enter_control(Control.COMMAND_CONTROL).accepted
    return obj


def move(mode=Cmd.XYZ_POS, number=1, **kwargs):
    return Cmd(agent_cmd=Cmd.MOVE, move_mode=mode, command_id=number, **kwargs)


class CommandTests(unittest.TestCase):
    def test_home_hover_and_landing_lifecycle(self):
        obj = processor(takeoff_height=3.)
        self.assertEqual(obj.step().position, (9., 18., 5.))
        hover = Cmd(agent_cmd=Cmd.CURRENT_POS_HOVER, command_id=1)
        self.assertTrue(obj.accept(hover).accepted)
        captured = obj.step()
        obj.update_state(state(position=(12., 25., 4.), yaw=1.))
        self.assertTrue(obj.accept(hover).accepted)
        self.assertEqual(obj.step(), captured)
        obj.accept(Cmd(agent_cmd=Cmd.LAND, command_id=2))
        self.assertEqual(obj.step().kind, 'land')
        self.assertEqual(obj.control_state, Control.LAND_CONTROL)
        obj.update_state(state(armed=False))
        self.assertEqual(obj.control_state, Control.INIT)
        self.assertIsNone(obj.step())

    def test_priority_stop_resume_and_input_copy(self):
        obj = processor()
        hold = Cmd(agent_cmd=Cmd.CURRENT_POS_HOVER, control_level=Cmd.ABSOLUTE_CONTROL)
        decision = obj.accept(hold)
        self.assertTrue(decision.accepted and decision.stop_control)
        hold.agent_cmd = Cmd.LAND
        self.assertEqual(obj.command.agent_cmd, Cmd.CURRENT_POS_HOVER)
        obj.step()
        denied = obj.accept(move(position_ref=[1., 2., 3.]))
        self.assertFalse(denied.accepted)
        self.assertTrue(denied.stop_control)
        release = obj.accept(move(control_level=Cmd.EXIT_ABSOLUTE_CONTROL, position_ref=[4., 5., 6.]))
        self.assertTrue(release.accepted)
        self.assertIs(release.stop_control, False)
        self.assertEqual(obj.step().position, (3., 3., 6.))

    def test_world_and_trajectory_references(self):
        obj = processor()
        for mode in (Cmd.XYZ_POS, Cmd.TRAJECTORY):
            obj.accept(move(mode, position_ref=[4., 6., 3.], velocity_ref=[1., 2., 3.], acceleration_ref=[.1, .2, .3], yaw_ref=.5))
            desired = obj.step()
            self.assertEqual(desired.position, (3., 4., 3.))
            self.assertEqual(desired.yaw, .5)
            self.assertEqual(desired.velocity, (1., 2., 3.) if mode == Cmd.TRAJECTORY else None)
            if mode == Cmd.TRAJECTORY:
                self.assertAlmostEqual(desired.acceleration[2], .3, places=6)

    def test_body_latch_duplicate_pending_and_out_of_order(self):
        obj = processor(yaw=math.pi/2)
        command = move(Cmd.XYZ_POS_BODY, position_ref=[2., 3., 1.], yaw_ref=.2)
        self.assertTrue(obj.accept(command).accepted)
        self.assertFalse(obj.accept(command).accepted)  # Duplicate before the first tick too.
        first = obj.step()
        for actual, expected in zip(first.position, (6., 20., 3.)):
            self.assertAlmostEqual(actual, expected)
        obj.update_state(state(position=(40., 40., 4.), yaw=0.))
        self.assertEqual(obj.step(), first)
        self.assertFalse(obj.accept(move(Cmd.XYZ_POS_BODY, number=0)).accepted)
        self.assertEqual(obj.step(), first)
        self.assertTrue(obj.accept(move(Cmd.XYZ_POS_BODY, number=2, position_ref=[2., 3., 1.])).accepted)
        self.assertEqual(obj.step().position, (41., 41., 5.))

    def test_all_velocity_modes_and_fresh_mixed_yaw_rate(self):
        for mode in CommandProcessor.VELOCITY:
            with self.subTest(mode=mode):
                obj = processor(yaw=math.pi/2)
                obj.accept(move(mode, velocity_ref=[2., 0., 1.], position_ref=[0., 0., 3.], yaw_rate_mode=True, yaw_rate_ref=.75))
                desired = obj.step()
                self.assertIsNone(desired.yaw)
                self.assertEqual(desired.yaw_rate, .75)
                if mode in (Cmd.XYZ_VEL_BODY, Cmd.XY_VEL_Z_POS_BODY):
                    self.assertAlmostEqual(desired.velocity[0], 0.)
                    self.assertAlmostEqual(desired.velocity[1], 2.)
                else:
                    self.assertEqual(desired.velocity[:2], (2., 0.))
                if mode in (Cmd.XY_VEL_Z_POS, Cmd.XY_VEL_Z_POS_BODY):
                    self.assertEqual(desired.velocity[2], 0.)
                    self.assertEqual(desired.position[2], 5. if mode == Cmd.XY_VEL_Z_POS_BODY else 3.)

    def test_attitude_global_and_explicit_rejections(self):
        obj = processor()
        before = deepcopy(obj.command)
        self.assertEqual(obj.accept(move(Cmd.XYZ_ATT, att_ref=[.1, .2, .3, .5])).reason, 'external_attitude_disabled')
        self.assertEqual(obj.command, before)
        obj = processor(enable_external_control=True)
        self.assertTrue(obj.accept(move(Cmd.XYZ_ATT, att_ref=[.1, .2, .3, .5])).accepted)
        self.assertEqual(obj.step().attitude[3], .5)
        self.assertFalse(obj.accept(move(Cmd.XYZ_ATT, att_ref=[0., 0., 0., 1.1])).accepted)
        self.assertTrue(obj.accept(move(Cmd.LAT_LON_ALT, latitude=47., longitude=8., altitude=3.)).accepted)
        self.assertEqual(obj.step().global_position, (47., 8., 3.))
        self.assertFalse(obj.accept(move(Cmd.LAT_LON_ALT, latitude=91.)).accepted)
        self.assertFalse(obj.accept(Cmd(agent_cmd=Cmd.USER_MODE)).accepted)
        self.assertFalse(obj.accept(move(99)).accepted)
        self.assertFalse(obj.accept(move(control_level=99)).accepted)
        invalid = move()
        invalid.position_ref[0] = math.nan
        self.assertEqual(obj.accept(invalid).reason, 'non_finite_command')

    def test_entry_gating_geofence_and_disconnect(self):
        obj = CommandProcessor()
        self.assertFalse(obj.enter_control(Control.COMMAND_CONTROL).accepted)
        self.assertFalse(obj.accept(move()).accepted)
        self.assertFalse(obj.set_offset(1., 2.).accepted)
        obj = processor()
        obj.update_state(state(position=(101., 20., 2.)))
        self.assertEqual(obj.step().kind, 'land')
        self.assertTrue(obj.failsafe)
        obj = processor()
        disconnected = state()
        disconnected.connected = False
        obj.update_state(disconnected)
        self.assertIsNone(obj.step())
        self.assertEqual(obj.safety_flag(), -1)
        obj.update_state(state())
        self.assertEqual(obj.safety_flag(sim_mode=False, rc_age=1.51), 3)
        invalid_odom = state()
        invalid_odom.odom_valid = False
        obj.update_state(invalid_odom)
        self.assertEqual(obj.step().kind, 'land')

    def test_config_validation_and_hover_entry_idempotence(self):
        for value in (0., -1., math.nan, math.inf):
            with self.assertRaises(ValueError):
                CommandProcessor(takeoff_height=value)
        with self.assertRaises(ValueError):
            CommandProcessor(fence=((2., 1.),) * 3)
        obj = processor()
        with self.assertRaises(ValueError):
            obj.update_state(UAVState(attitude_q=Quaternion(w=0.0)))
        obj.enter_control(Control.RC_POS_CONTROL)
        hover = obj.step()
        obj.update_state(state(position=(20., 30., 4.)))
        obj.enter_control(Control.RC_POS_CONTROL)
        self.assertEqual(obj.step(), hover)


class ShapingTests(unittest.TestCase):
    def test_all_eight_velocity_axis_combinations(self):
        for bits in range(8):
            with self.subTest(bits=bits):
                shaper = SetpointShaper()
                velocity = tuple(1.0 if bits & (4 >> axis) else 0.0 for axis in range(3))
                desired = Desired('velocity', velocity=velocity, yaw=.5)
                first = shaper.shape(desired, (10., 20., 3.))
                result = shaper.shape(desired, (10.1, 20.2, 3.3))
                self.assertIsNotNone(first)
                if bits == 0:
                    self.assertEqual(result.position, (10., 20., 3.))
                    self.assertEqual(result.velocity, (None, None, None))
                elif bits == 1:
                    self.assertEqual(result.position, (10., 20., None))
                    self.assertEqual(result.velocity, (None, None, 1.))
                else:
                    self.assertEqual(result.position, (None, None, None if bits & 1 else 3.))
                    self.assertAlmostEqual(result.velocity[0], 1. if bits & 4 else -float32(1.8)*.1)
                    self.assertAlmostEqual(result.velocity[1], 1. if bits & 2 else -float32(1.8)*.2)
                    self.assertEqual(result.velocity[2], 1. if bits & 1 else 0.)

    def test_velocity_and_yaw_changes_never_drop_or_reset_other_axes(self):
        shaper = SetpointShaper()
        for index, velocity in enumerate([(0., 1., 0.), (0., 1., 0.), (0., -1., 0.), (0., 0., 0.)]):
            result = shaper.shape(Desired('velocity', velocity=velocity, yaw=index*.2), (10.+index, 20.+index, 3.))
            self.assertIsNotNone(result)
            self.assertAlmostEqual(result.yaw, index*.2, places=6)
        self.assertEqual(result.position, (10., 23., 3.))

    def test_mixed_axes_and_independent_history(self):
        for velocity in [(0., 1., 0.), (1., 0., 0.), (1., 1., 0.), (0., 0., 0.)]:
            shaper = SetpointShaper()
            shaper.shape(Desired('velocity', velocity=(1., 1., 1.), yaw=0.), (-10., -20., 1.))
            desired = Desired('velocity_xy_position_z', velocity=velocity, position=(0., 0., 5.), yaw=.01)
            shaper.shape(desired, (10., 20., 3.))
            result = shaper.shape(desired, (10.1, 20.2, 4.))
            self.assertEqual(result.position[2], 5.)
            self.assertAlmostEqual(result.yaw, .01)
            if velocity == (0., 0., 0.):
                self.assertEqual(result.position, (10., 20., 5.))
            else:
                self.assertAlmostEqual(result.velocity[0], 1. if velocity[0] else -float32(1.8)*.1)
                self.assertAlmostEqual(result.velocity[1], 1. if velocity[1] else -float32(1.8)*.2)

    def test_direct_rate_modes_and_reset(self):
        shaper = SetpointShaper()
        hold = Desired('velocity', velocity=(0., 0., 0.), yaw=0.)
        shaper.shape(hold, (0., 0., 0.))
        for kind in ('velocity', 'velocity_xy_position_z'):
            result = shaper.shape(Desired(kind, velocity=(.01, 0., .02), position=(0., 0., 5.), yaw_rate=.7), (1., 2., 3.))
            self.assertEqual(result.velocity, (.01, 0., .02 if kind == 'velocity' else 0.))
            self.assertIsNone(result.yaw)
            self.assertAlmostEqual(result.yaw_rate, .7)
        self.assertEqual(shaper.shape(hold, (9., 8., 7.)).position, (9., 8., 7.))
        self.assertIsNone(shaper.shape(None, (9., 8., 7.)))
        self.assertEqual(shaper.shape(hold, (4., 5., 6.)).position, (4., 5., 6.))
        self.assertEqual(shaper.shape(Desired('land'), (4., 5., 6.)).kind, 'land')
        self.assertIsNone(shaper.family)

    def test_position_trajectory_acceleration_attitude_and_global(self):
        shaper = SetpointShaper()
        for kind in ('position', 'trajectory', 'acceleration'):
            output = shaper.shape(Desired(kind, position=(1., 2., 3.), velocity=(4., 5., 6.), acceleration=(.1, .2, .3), yaw=.7), (0., 0., 0.))
            self.assertEqual(output.position, (None,)*3 if kind == 'acceleration' else (1., 2., 3.))
            self.assertEqual(output.velocity, (4., 5., 6.) if kind == 'trajectory' else (None,)*3)
            self.assertEqual(output.acceleration, (.1, .2, .3) if kind == 'acceleration' else (None,)*3)
        output = shaper.shape(Desired('attitude', attitude=(0., 0., math.pi/2, .5)), (0., 0., 0.))
        self.assertAlmostEqual(output.quaternion_xyzw[2], math.sqrt(.5))
        self.assertAlmostEqual(output.quaternion_xyzw[3], math.sqrt(.5))
        self.assertEqual(output.thrust, .5)
        self.assertEqual(shaper.shape(Desired('global', global_position=(47., 8., 3.), yaw=0.), (0., 0., 0.)).global_position, (47., 8., 3.))

    def test_threshold_edges_and_yaw_hold(self):
        shaper = SetpointShaper()
        speed = shaper.speed_deadband
        result = shaper.shape(Desired('velocity', velocity=(speed, -speed, speed), yaw=shaper.yaw_deadband), (1., 2., 3.))
        self.assertEqual(result.position, (1., 2., 3.))
        self.assertEqual(result.yaw, 0.)
        result = shaper.shape(Desired('velocity', velocity=(speed+1e-6, 0., 0.), yaw=.5), (1., 2., 3.))
        self.assertEqual(result.velocity[0], speed+1e-6)
        self.assertEqual(shaper.shape(Desired('velocity', velocity=(1., 0., 0.), yaw=.51), (1., 2., 3.)).yaw, .5)
        shaper.reset()
        ref = Desired('velocity', velocity=(0., 1., 0.), yaw=0.)
        shaper.shape(ref, (0., 0., 0.))
        self.assertEqual(shaper.shape(ref, (shaper.hold_gap-1e-8, 0., 0.)).velocity[0], 0.)
        self.assertLess(shaper.shape(ref, (shaper.hold_gap, 0., 0.)).velocity[0], 0.)

    def test_invalid_inputs_do_not_mutate_hold(self):
        shaper = SetpointShaper()
        hold = Desired('velocity', velocity=(0., 0., 0.), yaw=0.)
        shaper.shape(hold, (1., 2., 3.))
        before = deepcopy(shaper.__dict__)
        for ref in [Desired('velocity', velocity=(math.nan, 0., 0.), yaw=0.),
                    Desired('velocity', velocity=(0., 0., 0.), yaw=1., yaw_rate=1.),
                    Desired('position', position=(0., 1.), yaw=0.),
                    Desired('attitude', attitude=(0., 0., 0., 2.)),
                    Desired('global', global_position=(91., 0., 0.), yaw=0.),
                    Desired('unknown', yaw=0.)]:
            with self.assertRaises(ValueError):
                shaper.shape(ref, (9., 8., 7.))
            self.assertEqual(shaper.__dict__, before)
        with self.assertRaises(ValueError):
            shaper.shape(hold, (0., math.inf, 0.))
        for kwargs in [dict(speed_deadband=0), dict(hold_gain=-1), dict(yaw_deadband=math.nan), dict(hold_gap=1e100)]:
            with self.assertRaises(ValueError):
                SetpointShaper(**kwargs)

    def test_processor_integration_uses_local_offset_and_disarm_reset(self):
        obj, shaper = processor(), SetpointShaper()
        obj.accept(move(Cmd.XYZ_VEL, velocity_ref=[0., 0., 0.]))
        output = shaper.shape(obj.step(), obj.local_position())
        self.assertEqual(output.position, (9., 18., 2.))  # Not raw shared-frame (10,20,2).
        obj.update_state(state(armed=False))
        self.assertIsNone(shaper.shape(obj.step(), obj.local_position()))
        self.assertIsNone(shaper.family)


if __name__ == '__main__':
    unittest.main()
