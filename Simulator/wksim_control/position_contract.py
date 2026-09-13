"""Shared position-control input contract: ENU / FLU, SI, no algorithm or transport.

PIDState/PIDReference remain identity aliases for existing callers and recordings.
"""
from dataclasses import dataclass
import math
from numbers import Real

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]
GRAVITY = 9.8  # Fixed original PID convention, not a model gravity override.


def _finite(value: float, name: str) -> float:
    # ROS fixed float arrays yield real scalars such as numpy.float32.
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _vector(value, size: int, name: str) -> tuple:
    if not isinstance(value, (tuple, list)) or len(value) != size:
        raise ValueError(f"{name} must have {size} components")
    return tuple(_finite(x, name) for x in value)


@dataclass(frozen=True)
class PositionState:
    position_enu: Vec3
    velocity_enu: Vec3
    attitude_flu_to_enu: Quat

    def __post_init__(self):
        for name in ("position_enu", "velocity_enu"):
            object.__setattr__(self, name, _vector(getattr(self, name), 3, name))
        q = _vector(self.attitude_flu_to_enu, 4, "attitude_flu_to_enu")
        if abs(math.hypot(*q) - 1.0) > 1e-6:
            raise ValueError("attitude_flu_to_enu must be a unit wxyz quaternion")
        object.__setattr__(self, "attitude_flu_to_enu", q)


@dataclass(frozen=True)
class PositionReference:
    position_enu: Vec3
    velocity_enu: Vec3 = (0.0, 0.0, 0.0)
    acceleration_enu: Vec3 = (0.0, 0.0, 0.0)
    yaw_enu_rad: float = 0.0

    def __post_init__(self):
        for name in ("position_enu", "velocity_enu", "acceleration_enu"):
            object.__setattr__(self, name, _vector(getattr(self, name), 3, name))
        object.__setattr__(self, "yaw_enu_rad", _finite(self.yaw_enu_rad, "yaw_enu_rad"))


PIDState = PositionState
PIDReference = PositionReference
