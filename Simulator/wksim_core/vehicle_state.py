"""Transport-independent SI truth shared by implemented vehicle model adapters."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class VehicleState:
    time_s: float
    position_ned_m: tuple
    velocity_ned_m_s: tuple
    attitude_frd_to_ned_wxyz: tuple
    angular_velocity_frd_rad_s: tuple
    specific_force_frd_m_s2: tuple

    def __post_init__(self):
        if type(self.time_s) not in (int,float) or not math.isfinite(self.time_s) or self.time_s<0:
            raise ValueError('Nonnegative finite simulation time required')
        for name,size in (('position_ned_m',3),('velocity_ned_m_s',3),
                          ('attitude_frd_to_ned_wxyz',4),('angular_velocity_frd_rad_s',3),
                          ('specific_force_frd_m_s2',3)):
            value=getattr(self,name)
            if not isinstance(value,(tuple,list)) or len(value)!=size or any(type(x) not in (int,float) or not math.isfinite(x) for x in value):
                raise ValueError('Invalid model state: '+name)
            object.__setattr__(self,name,tuple(value))
        if abs(math.hypot(*self.attitude_frd_to_ned_wxyz)-1)>1e-5:
            raise ValueError('Physical orientation must be a unit quaternion')
