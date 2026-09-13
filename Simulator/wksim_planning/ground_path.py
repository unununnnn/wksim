"""Curvature-limited waypoint tracking for a forward Ackermann vehicle.

Produces speed/turn-rate intent; firmware transport and inner loops are separate.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class GroundCommand:
    speed_m_s: float
    turn_rate_rad_s: float


def track_waypoint(position_ne,heading_rad,goal_ne,*,minimum_turn_radius_m,max_speed_m_s=1.5):
    if len(position_ne)!=2 or len(goal_ne)!=2:
        raise ValueError('Ground waypoint needs two horizontal coordinates')
    values=(*position_ne,heading_rad,*goal_ne,minimum_turn_radius_m,max_speed_m_s)
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in values) or min(minimum_turn_radius_m,max_speed_m_s)<=0:
        raise ValueError('Finite pose and positive vehicle limits required')
    north,east=goal_ne[0]-position_ne[0],goal_ne[1]-position_ne[1]
    distance=math.hypot(north,east)
    if distance<.08:return GroundCommand(0.,0.)
    error=math.atan2(math.sin(math.atan2(east,north)-heading_rad),math.cos(math.atan2(east,north)-heading_rad))
    maximum_curvature=1/minimum_turn_radius_m
    curvature=max(-maximum_curvature,min(maximum_curvature,2*math.sin(error)/distance))
    speed=min(max_speed_m_s,1.2*distance)
    if abs(error)>math.pi/2:
        curvature=math.copysign(maximum_curvature,error)
        speed=min(speed,.7)
    return GroundCommand(speed,speed*curvature)
