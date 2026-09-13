"""Ground-vehicle bicycle model with bounded speed and steering response.

SI units, NED position and body FRD. This kinematic reference has a flat contact
plane; it does not model tire slip, suspension, rolling terrain or wheel forces.
No flight-stack, message, UI or UE dependency belongs in this model.
"""
from dataclasses import dataclass
import math

from .vehicle_state import VehicleState


@dataclass(frozen=True)
class AckermannParameters:
    wheelbase_m: float = 1.0
    max_speed_m_s: float = 5.0
    max_steering_rad: float = .55
    speed_response_s: float = .25
    steering_response_s: float = .12
    max_acceleration_m_s2: float = 3.0

    def __post_init__(self):
        for value in self.__dict__.values():
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('Vehicle parameters must be positive finite SI values')
        if self.max_steering_rad>=math.pi/2:
            raise ValueError('Bicycle steering must stay below pi/2')


class AckermannModel:
    def __init__(self, parameters=AckermannParameters()):
        if not isinstance(parameters,AckermannParameters):raise ValueError('Explicit AckermannParameters required')
        self.parameters=parameters
        self.time=0.;self.north=0.;self.east=0.;self.yaw=0.;self.speed=0.;self.steering=0.

    def step(self, *, throttle, steering, dt_s):
        if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (throttle,steering,dt_s))
                or not -1<=throttle<=1 or not -1<=steering<=1 or not 0<dt_s<=.02):
            raise ValueError('Signed actuator commands and dt in (0,.02] required')
        p=self.parameters
        target_speed=throttle*p.max_speed_m_s
        acceleration=max(-p.max_acceleration_m_s2,min(p.max_acceleration_m_s2,
            (target_speed-self.speed)/p.speed_response_s))
        following_speed=self.speed+acceleration*dt_s
        # A step longer than the response constant would otherwise carry the speed past
        # the current target; hold it on the target and report the realised increment.
        if self.speed<target_speed<following_speed or following_speed<target_speed<self.speed:
            following_speed=target_speed
            acceleration=(following_speed-self.speed)/dt_s
        self.steering+=(steering*p.max_steering_rad-self.steering)*(1-math.exp(-dt_s/p.steering_response_s))
        average_speed=(self.speed+following_speed)/2
        yaw_rate=average_speed*math.tan(self.steering)/p.wheelbase_m
        midpoint=self.yaw+yaw_rate*dt_s/2
        self.north+=average_speed*math.cos(midpoint)*dt_s
        self.east+=average_speed*math.sin(midpoint)*dt_s
        self.yaw+=yaw_rate*dt_s
        self.speed=following_speed;self.time+=dt_s
        current_yaw_rate=self.speed*math.tan(self.steering)/p.wheelbase_m
        return VehicleState(self.time,(self.north,self.east,0.),
            (self.speed*math.cos(self.yaw),self.speed*math.sin(self.yaw),0.),
            (math.cos(self.yaw/2),0.,0.,math.sin(self.yaw/2)),
            (0.,0.,current_yaw_rate),(acceleration,self.speed*current_yaw_rate,-9.80665))
