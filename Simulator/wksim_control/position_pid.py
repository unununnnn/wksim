"""Prometheus position PID port; see docs/2026-09-09-pid-controller-port.md.

All vectors are ENU, quaternion wxyz rotates body FLU into ENU. The algorithm
owns its integral; the caller owns timing, mode admission and lifecycle resets.
"""

from dataclasses import dataclass
import math
from numbers import Real
from typing import Literal

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]
GRAVITY = 9.8  # Fixed original PID convention, not a model gravity override.
UPSTREAM_COMMIT = "5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce"
UPSTREAM_PID_PATH = "Modules/uav_control/include/Position_Controller/pos_controller_PID.h"
UPSTREAM_PID_SHA256 = "4f75efa91ead6518cf778a2b3294621944e842274a4c1826577fd32c63823f9e"


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
class PIDConfig:
    mass_kg: float  # Must match the selected fixed model; never infer from stack.
    kp: Vec3 = (2.0, 2.0, 2.0)
    kv: Vec3 = (2.0, 2.0, 2.0)
    ki: Vec3 = (0.3, 0.3, 0.3)
    integral_limit: Vec3 = (0.5, 0.5, 0.5)
    tilt_limit_deg: float = 10.0

    def __post_init__(self):
        mass = _finite(self.mass_kg, "mass_kg")
        tilt = _finite(self.tilt_limit_deg, "tilt_limit_deg")
        if mass <= 0 or not 0 < tilt < 90:
            raise ValueError("mass must be positive and tilt must be in (0, 90) degrees")
        object.__setattr__(self, "mass_kg", mass)
        object.__setattr__(self, "tilt_limit_deg", tilt)
        for name in ("kp", "kv", "ki", "integral_limit"):
            vector = _vector(getattr(self, name), 3, name)
            if any(x < 0 for x in vector):
                raise ValueError(f"{name} must be nonnegative")
            object.__setattr__(self, name, vector)


@dataclass(frozen=True)
class PIDState:
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
class PIDReference:
    position_enu: Vec3
    velocity_enu: Vec3 = (0.0, 0.0, 0.0)
    acceleration_enu: Vec3 = (0.0, 0.0, 0.0)
    yaw_enu_rad: float = 0.0

    def __post_init__(self):
        for name in ("position_enu", "velocity_enu", "acceleration_enu"):
            object.__setattr__(self, name, _vector(getattr(self, name), 3, name))
        object.__setattr__(self, "yaw_enu_rad", _finite(self.yaw_enu_rad, "yaw_enu_rad"))


@dataclass(frozen=True)
class PIDOutput:
    acceleration_enu: Vec3  # Feedback + feedforward, before force limiting; no gravity.
    force_enu_n: Vec3  # After original vertical and per-axis tilt limits.
    roll_pitch_yaw_enu_rad: Vec3
    projected_thrust_n: float  # Limited force dotted with current body +Z, original u1.
    integral: Vec3
    mass_kg: float
    controller: Literal["pid"] = "pid"


@dataclass(frozen=True)
class NativeThrustConfig:
    """Local linear hover calibration for one stack and fixed model identity.

    Preserves original u = (F dot body_z) / (mass * 9.8 / hover), clamped
    [0.1, 1]. This is a calibration approximation, not a motor force law.
    AP collective is +u; PX4 FRD thrust_body is (0, 0, -u). Frame/quaternion
    conversion remains the existing attitude outlet's responsibility.
    """

    stack: Literal["arducopter", "px4"]
    model_identity: str
    mass_kg: float
    hover_thrust: float

    def __post_init__(self):
        if self.stack not in ("arducopter", "px4"):
            raise ValueError("unsupported thrust stack")
        if not isinstance(self.model_identity, str) or not self.model_identity.strip():
            raise ValueError("fixed model identity is required")
        mass = _finite(self.mass_kg, "mass_kg")
        hover = _finite(self.hover_thrust, "hover_thrust")
        if mass <= 0 or not 0.1 <= hover <= 1.0:
            raise ValueError("mass must be positive and calibrated hover must be in [0.1, 1]")
        object.__setattr__(self, "mass_kg", mass)
        object.__setattr__(self, "hover_thrust", hover)

    def normalized_collective(self, output: PIDOutput, *, model_identity: str) -> float:
        if model_identity != self.model_identity or output.mass_kg != self.mass_kg:
            raise ValueError("PID thrust mapping model identity or mass mismatch")
        thrust = _finite(output.projected_thrust_n, "projected_thrust_n")
        normalized = thrust / (self.mass_kg * GRAVITY / self.hover_thrust)
        return min(1.0, max(0.1, _finite(normalized, "normalized collective")))


class PositionPID:
    name = "pid"

    def __init__(self, config: PIDConfig):
        if not isinstance(config, PIDConfig):
            raise ValueError("explicit PIDConfig is required")
        self.config = config
        self.reset("initialize")

    @property
    def integral(self) -> Vec3:
        return self._integral

    def reset(self, reason: str) -> None:
        """Call on selection, takeover, release, restart and timing discontinuity."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reset reason is required")
        self._integral = (0.0, 0.0, 0.0)
        self.last_reset_reason = reason

    def update(self, state: PIDState, reference: PIDReference, *, dt_s: float,
               external_control_active: bool) -> PIDOutput:
        """dt is actual simulation elapsed time; no wall clock or fixed 200 Hz.

        external_control_active replaces upstream's literal OFFBOARD test and
        must be derived from verified native takeover (including AP GUIDED).
        False clears integral but does not authorize publishing the result.
        Invalid calls leave integral state unchanged.
        """
        dt = _finite(dt_s, "dt_s")
        if dt <= 0 or type(external_control_active) is not bool:
            raise ValueError("dt must be positive and external_control_active must be bool")
        if not isinstance(state, PIDState) or not isinstance(reference, PIDReference):
            raise ValueError("PIDState and PIDReference are required")
        cfg = self.config
        pe = [a - b for a, b in zip(reference.position_enu, state.position_enu)]
        ve = [a - b for a, b in zip(reference.velocity_enu, state.velocity_enu)]
        for x in (*pe, *ve):
            _finite(x, "tracking error")
        # These discontinuities are original behavior, not ordinary saturation.
        pe = [math.copysign(1.0, x) if abs(x) > 3.0 else x for x in pe]
        ve = [math.copysign(2.0, x) if abs(x) > 3.0 else x for x in ve]
        moving = any(x != 0.0 for x in reference.velocity_enu)
        integ = [0.0] * 3 if moving else list(self._integral)
        for i, threshold in enumerate((0.20000000298023224, 0.20000000298023224, 0.5)):
            if external_control_active and abs(pe[i]) < threshold:
                value = _finite(integ[i] + pe[i] * dt, "integral")
                integ[i] = min(cfg.integral_limit[i], max(-cfg.integral_limit[i], value))
            else:
                integ[i] = 0.0
        acc = tuple(reference.acceleration_enu[i] + cfg.kp[i] * pe[i]
                    + cfg.kv[i] * ve[i] + cfg.ki[i] * integ[i] for i in range(3))
        force = [cfg.mass_kg * acc[i] + (cfg.mass_kg * GRAVITY if i == 2 else 0)
                 for i in range(3)]
        for x in (*acc, *force):
            _finite(x, "PID output")
        if force[2] == 0.0:
            raise ValueError("zero vertical force is undefined in original PID scaling")
        mg = cfg.mass_kg * GRAVITY
        target_z = min(2.0 * mg, max(0.5 * mg, force[2]))
        if target_z != force[2]:
            force = [x / force[2] * target_z for x in force]
        tilt = math.tan(math.radians(cfg.tilt_limit_deg))
        for i in range(2):
            if abs(force[i] / force[2]) > tilt:
                force[i] = math.copysign(force[2] * tilt, force[i])
        w, x, y, z = state.attitude_flu_to_enu
        # Original yaw helper normalizes; original force projection does not.
        norm2 = w * w + x * x + y * y + z * z
        yaw = math.atan2(2 * (w * z + x * y) / norm2,
                         1 - 2 * (y * y + z * z) / norm2)
        c, s = math.cos(yaw), math.sin(yaw)
        fx, fy = c * force[0] + s * force[1], -s * force[0] + c * force[1]
        rpy = (math.atan2(-fy, force[2]), math.atan2(fx, force[2]), reference.yaw_enu_rad)
        body_z = (2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y))
        thrust = sum(a * b for a, b in zip(force, body_z))
        for value in (*force, *rpy, thrust):
            _finite(value, "PID output")
        output = PIDOutput(acc, tuple(force), rpy, thrust, tuple(integ), cfg.mass_kg)
        self._integral = output.integral
        return output


def select_controller(name: str, config):
    """Explicit typed selection; each instance starts with cleared state."""
    if name == "pid":
        return PositionPID(config)
    if name == "ude":
        # Local import avoids a cycle with UDE's shared state/reference types.
        from .position_ude import PositionUDE
        return PositionUDE(config)
    raise ValueError(f"unsupported external position controller: {name!r}")
