"""Model/actuator seams tested without a firmware or renderer."""
import math
import unittest

from Simulator.wksim_core.ackermann import AckermannModel,AckermannParameters
from Simulator.wksim_core.actuator_layout import ACKERMANN,QUAD_X,PWMActuator,decode_layout
from Simulator.wksim_core.vehicle_models import VehicleModel
from Simulator.wksim_core.model_parameters import px4_quad_allocation
from Simulator.wksim_planning.ground_path import track_waypoint


class VehicleModelTests(unittest.TestCase):
    def test_same_pwm_has_declared_vehicle_specific_semantics(self):
        pwm=[1500]*16
        self.assertEqual(decode_layout(ACKERMANN,pwm),dict(steering=0.,throttle=0.))
        self.assertTrue(all(x==.5 for x in decode_layout(QUAD_X,pwm).values()))
        pwm[2]=1000
        self.assertEqual(decode_layout(ACKERMANN,pwm)['throttle'],-1.)
        self.assertTrue(all(x==0 for x in decode_layout(ACKERMANN,[0]*16).values()))
        for pwm in (999,2001,True):
            with self.assertRaises(ValueError):ACKERMANN[0].decode(pwm)
        with self.assertRaises(ValueError):decode_layout((ACKERMANN[0],ACKERMANN[0]),[1500]*16)

    def test_ground_model_respects_vehicle_input_and_time_contract(self):
        with VehicleModel('ackermann_v1') as model:
            state=model.step(dict(throttle=.4,steering=0.),1000)
            self.assertAlmostEqual(state.time_s,1.)
            self.assertGreater(state.position_ned_m[0],0.)
            self.assertEqual(state.position_ned_m[1:],(0.,0.))
            with self.assertRaises(ValueError):model.step(dict(front_right=.4),1)
            with self.assertRaises(ValueError):model.step(dict(throttle=math.nan,steering=0.),1)
        with self.assertRaises(ValueError):model.step(dict(throttle=0.,steering=0.))
        with self.assertRaises(ValueError):VehicleModel('fixed_wing')
        with self.assertRaises(ValueError):VehicleModel('ackermann_v1',library='/some/quad.so')

    def test_ground_steady_circle_and_specific_force_match_bicycle_equations(self):
        p=AckermannParameters();model=AckermannModel(p)
        model.speed=2.;model.steering=.25
        state=None
        for _ in range(1000):state=model.step(throttle=.4,steering=.25/p.max_steering_rad,dt_s=.001)
        radius=p.wheelbase_m/math.tan(.25);angle=2/radius
        self.assertAlmostEqual(state.position_ned_m[0],radius*math.sin(angle),places=6)
        self.assertAlmostEqual(state.position_ned_m[1],radius*(1-math.cos(angle)),places=6)
        self.assertAlmostEqual(state.angular_velocity_frd_rad_s[2],2/radius)
        self.assertAlmostEqual(state.specific_force_frd_m_s2[1],4/radius)

    def test_ground_reverse_and_disabled_throttle_are_distinct(self):
        model=AckermannModel()
        for _ in range(2000):state=model.step(throttle=-.2,steering=0.,dt_s=.001)
        self.assertLess(state.position_ned_m[0],-.5)
        for _ in range(3000):state=model.step(throttle=0.,steering=0.,dt_s=.001)
        self.assertLess(abs(state.velocity_ned_m_s[0]),1e-4)

    def test_catalog_derived_px4_allocation_preserves_original_values(self):
        actual=px4_quad_allocation();r=.225/math.sqrt(2)
        for i,(x,y) in enumerate(((r,r),(-r,-r),(r,-r),(-r,r))):
            self.assertEqual(actual[f'PX4_PARAM_CA_ROTOR{i}_PX'],str(x))
            self.assertEqual(actual[f'PX4_PARAM_CA_ROTOR{i}_PY'],str(y))
            self.assertEqual(actual[f'PX4_PARAM_CA_ROTOR{i}_KM'],str((1 if i<2 else -1)*2.783e-7/1.681e-5))

    def test_path_intent_stays_within_vehicle_curvature_and_stops_at_goal(self):
        for goal in ((5.,0.),(0.,5.),(-5.,0.),(0.,-5.)):
            command=track_waypoint((0.,0.),0.,goal,minimum_turn_radius_m=2.)
            self.assertLessEqual(command.speed_m_s,1.5)
            self.assertLessEqual(abs(command.turn_rate_rad_s),command.speed_m_s/2+1e-12)
        self.assertEqual(track_waypoint((5.,5.),0.,(5.,5.),minimum_turn_radius_m=2.).speed_m_s,0.)
