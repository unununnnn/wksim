"""Speed-response bounds of the Ackermann ground reference at the 1 ms interface.

Pure model-seam cases: no firmware, ROS node, GPU, MATLAB or vendor model is
started. States remain VehicleState SI/NED/FRD with named actuators. The cases
pin the declared actuator-to-speed response boundary (never step past the
current target speed, never violate max_acceleration_m_s2, report the realised
increment as specific force) and record that default parameters keep the
already verified response path.

Run from the repository root:
    python -m unittest validation.test_ackermann_response_bounds -v
"""
import math
import unittest

from Simulator.wksim_core.ackermann import AckermannModel,AckermannParameters
from Simulator.wksim_core.vehicle_state import VehicleState

SMALL_RESPONSE_S=.0001


def drive(model,throttle,steering,dt_s,steps):
    return [model.step(throttle=throttle,steering=steering,dt_s=dt_s) for _ in range(steps)]


class AckermannResponseBoundsTests(unittest.TestCase):
    def test_small_response_constant_cannot_exceed_the_declared_max_speed(self):
        p=AckermannParameters(speed_response_s=SMALL_RESPONSE_S)
        model=AckermannModel(p)
        states=drive(model,1.,0.,.001,2000)
        self.assertTrue(all(type(state) is VehicleState for state in states))
        for index,state in enumerate(states):
            self.assertGreaterEqual(state.velocity_ned_m_s[0],0.,msg=index)
            self.assertLessEqual(state.velocity_ned_m_s[0],p.max_speed_m_s,msg=index)
        self.assertLessEqual(model.speed,p.max_speed_m_s)
        self.assertEqual(model.speed,p.max_speed_m_s)

    def test_small_response_constant_holds_the_reverse_speed_bound(self):
        p=AckermannParameters(speed_response_s=SMALL_RESPONSE_S)
        model=AckermannModel(p)
        states=drive(model,-1.,0.,.001,2000)
        for index,state in enumerate(states):
            self.assertGreaterEqual(state.velocity_ned_m_s[0],-p.max_speed_m_s,msg=index)
            self.assertLessEqual(state.velocity_ned_m_s[0],0.,msg=index)
        self.assertEqual(model.speed,-p.max_speed_m_s)

    def test_zero_throttle_brakes_to_rest_without_crossing_it(self):
        p=AckermannParameters(speed_response_s=SMALL_RESPONSE_S)
        model=AckermannModel(p)
        model.speed=4.
        previous=model.speed
        for index in range(5000):
            state=model.step(throttle=0.,steering=0.,dt_s=.001)
            self.assertGreaterEqual(state.velocity_ned_m_s[0],0.,msg=index)
            self.assertLessEqual(state.velocity_ned_m_s[0],previous,msg=index)
            previous=state.velocity_ned_m_s[0]
        self.assertEqual(model.speed,0.)

    def test_crossing_step_reports_the_bounded_increment(self):
        p=AckermannParameters(speed_response_s=SMALL_RESPONSE_S)
        model=AckermannModel(p)
        model.speed=p.max_speed_m_s-.001
        state=model.step(throttle=1.,steering=0.,dt_s=.001)
        realised=(model.speed-(p.max_speed_m_s-.001))/.001
        self.assertEqual(model.speed,p.max_speed_m_s)
        self.assertAlmostEqual(state.specific_force_frd_m_s2[0],realised,places=9)
        self.assertAlmostEqual(realised,1.,places=9)
        self.assertLessEqual(abs(state.specific_force_frd_m_s2[0]),p.max_acceleration_m_s2)

    def test_reported_specific_force_is_the_realised_speed_increment(self):
        cases=((AckermannParameters(speed_response_s=SMALL_RESPONSE_S),1.,.001,4000),
               (AckermannParameters(speed_response_s=SMALL_RESPONSE_S),-1.,.001,4000),
               (AckermannParameters(speed_response_s=.0005),.7,.001,3000),
               (AckermannParameters(speed_response_s=.004),1.,.005,400),
               (AckermannParameters(),.4,.02,200))
        for p,throttle,dt_s,steps in cases:
            model=AckermannModel(p)
            for index in range(steps):
                before=model.speed
                state=model.step(throttle=throttle,steering=0.,dt_s=dt_s)
                difference=model.speed-before
                realised=difference/dt_s
                # Roundoff in the model multiply/add and this test's subtract/divide.
                # This bounds only the reconstructed binary64 derivative, not a physical
                # tolerance; speed and the reported acceleration remain strictly bounded.
                product=state.specific_force_frd_m_s2[0]*dt_s
                rounding_slack=(math.ulp(product)+math.ulp(model.speed)+math.ulp(difference))/(2*dt_s)+math.ulp(realised)/2
                self.assertAlmostEqual(state.specific_force_frd_m_s2[0],realised,places=9,msg=(p.speed_response_s,index))
                self.assertLessEqual(abs(state.specific_force_frd_m_s2[0]),p.max_acceleration_m_s2)
                self.assertLessEqual(abs(realised),p.max_acceleration_m_s2+rounding_slack)
                self.assertLess(rounding_slack,1e-9,msg=(p.speed_response_s,index))

    def test_bound_holds_across_every_allowed_step_length(self):
        for response in (SMALL_RESPONSE_S,.002,.05,.25):
            for dt_s in (.0001,.001,.005,.01,.02):
                p=AckermannParameters(speed_response_s=response)
                model=AckermannModel(p)
                previous=0.
                for index in range(3000):
                    state=model.step(throttle=1.,steering=0.,dt_s=dt_s)
                    speed=state.velocity_ned_m_s[0]
                    self.assertGreaterEqual(speed,previous,msg=(response,dt_s,index))
                    self.assertLessEqual(speed,p.max_speed_m_s,msg=(response,dt_s,index))
                    self.assertLessEqual(speed-previous,p.max_acceleration_m_s2*dt_s+1e-12,msg=(response,dt_s,index))
                    previous=speed

    def test_default_parameters_keep_the_verified_response_path(self):
        scenarios=((.4,.25,2.),(1.,0.,0.),(-1.,.3,1.))
        for dt_s in (.001,.02):
            for throttle,steering_target,initial_speed in scenarios:
                p=AckermannParameters()
                model=AckermannModel(p)
                model.speed=initial_speed;model.steering=steering_target
                command=steering_target/p.max_steering_rad
                north=east=yaw=time_s=0.
                for index in range(1000):
                    acceleration=max(-p.max_acceleration_m_s2,min(p.max_acceleration_m_s2,
                        (throttle*p.max_speed_m_s-model.speed)/p.speed_response_s))
                    following_speed=model.speed+acceleration*dt_s
                    steering=model.steering+(command*p.max_steering_rad-model.steering)*(1-math.exp(-dt_s/p.steering_response_s))
                    average_speed=(model.speed+following_speed)/2
                    yaw_rate=average_speed*math.tan(steering)/p.wheelbase_m
                    midpoint=yaw+yaw_rate*dt_s/2
                    north+=average_speed*math.cos(midpoint)*dt_s
                    east+=average_speed*math.sin(midpoint)*dt_s
                    yaw+=yaw_rate*dt_s
                    time_s+=dt_s
                    state=model.step(throttle=throttle,steering=command,dt_s=dt_s)
                    current_yaw_rate=model.speed*math.tan(steering)/p.wheelbase_m
                    location=(dt_s,throttle,index)
                    self.assertEqual(state.position_ned_m,(north,east,0.),msg=location)
                    self.assertEqual(state.velocity_ned_m_s,
                        (model.speed*math.cos(yaw),model.speed*math.sin(yaw),0.),msg=location)
                    self.assertEqual(state.attitude_frd_to_ned_wxyz,
                        (math.cos(yaw/2),0.,0.,math.sin(yaw/2)),msg=location)
                    self.assertEqual(state.angular_velocity_frd_rad_s,(0.,0.,current_yaw_rate),msg=location)
                    self.assertEqual(state.specific_force_frd_m_s2,
                        (acceleration,model.speed*current_yaw_rate,-9.80665),msg=location)
                    self.assertEqual(state.time_s,time_s,msg=location)

    def test_small_response_constants_stay_legal_parameters(self):
        for response in (SMALL_RESPONSE_S,.001,.25,5.):
            self.assertEqual(AckermannParameters(speed_response_s=response).speed_response_s,response)
        for response in (0.,-1.,math.nan,math.inf,'0.1',True):
            with self.assertRaises(ValueError):AckermannParameters(speed_response_s=response)

    def test_signed_command_and_step_contract_is_unchanged(self):
        model=AckermannModel()
        self.assertIsInstance(model.step(throttle=0.,steering=0.,dt_s=.02),VehicleState)
        for throttle,steering,dt_s in ((1.0001,0.,.001),(-1.0001,0.,.001),(0.,1.0001,.001),
                                       (0.,0.,0.),(0.,0.,.0201),(0.,0.,math.nan),(math.nan,0.,.001)):
            with self.assertRaises(ValueError):model.step(throttle=throttle,steering=steering,dt_s=dt_s)


if __name__=='__main__':
    unittest.main()
