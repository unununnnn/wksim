"""Fixed Prometheus UDE, upstream 5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce.

ENU/FLU state, reference and calibrated thrust mapping reuse the PID contract.
No PID computation or native transport is invoked. Selection integration is #90.
Differences: explicit finite/positive input checks, transactional invalid cycles,
and inactive clears all observer state and rejects output. Upstream has no mode
gate. Caller must reset on selection, takeover, release, restart or clock jump.
dt is actual simulation elapsed seconds (upstream uses float32 1/hz).
Diagnostic tracking-error windows/logging are omitted; they do not feed control.
"""

from dataclasses import dataclass
import math
from typing import Literal

from .position_pid import PIDState, PIDReference, Vec3, _finite, _vector

UPSTREAM_COMMIT = "5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce"
UPSTREAM_UDE_PATH = "Modules/uav_control/include/Position_Controller/pos_controller_UDE.h"
UPSTREAM_UDE_SHA256 = "ae0c9a300e435775b836f56667aadf90e4779db0b116218178d747bb50ce6699"


@dataclass(frozen=True)
class UDEConfig:
    mass_kg: float
    kp: Vec3 = (0.5, 0.5, 0.5)
    kd: Vec3 = (2.0, 2.0, 2.0)
    t_ude_s: float = 1.0
    disturbance_limit: Vec3 = (1.0, 1.0, 1.0)
    tilt_limit_deg: float = 20.0

    def __post_init__(self):
        for name in ("mass_kg", "t_ude_s", "tilt_limit_deg"):
            value = _finite(getattr(self, name), name)
            if value <= 0 or (name == "tilt_limit_deg" and value >= 90):
                raise ValueError(f"invalid {name}")
            object.__setattr__(self, name, value)
        for name in ("kp", "kd", "disturbance_limit"):
            value = _vector(getattr(self, name), 3, name)
            if any(x < 0 for x in value):
                raise ValueError(f"negative {name}")
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class UDEOutput:
    acceleration_enu: Vec3
    force_enu_n: Vec3
    roll_pitch_yaw_enu_rad: Vec3
    projected_thrust_n: float
    integral: Vec3
    mass_kg: float
    nominal_acceleration_enu: Vec3
    disturbance_acceleration_enu: Vec3
    controller: Literal["ude"] = "ude"


class PositionUDE:
    name = "ude"

    def __init__(self, config: UDEConfig):
        if not isinstance(config, UDEConfig):
            raise ValueError("explicit UDEConfig required")
        self.config = config
        self.reset("initialize")

    @property
    def integral(self):
        return self._integral

    def reset(self, reason: str):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reset reason required")
        self._integral = (0.0, 0.0, 0.0)
        self.last_output = None
        self.last_reset_reason = reason

    def update(self, state: PIDState, reference: PIDReference, *, dt_s: float,
               external_control_active: bool) -> UDEOutput:
        dt = _finite(dt_s, "dt_s")
        if dt <= 0 or type(external_control_active) is not bool:
            raise ValueError("positive dt and boolean active required")
        if not isinstance(state, PIDState) or not isinstance(reference, PIDReference):
            raise ValueError("PIDState and PIDReference required")
        if not external_control_active:
            self.reset("external control inactive")
            raise ValueError("inactive UDE has no publishable output")
        cfg = self.config
        pe = [_finite(a-b, "position error") for a, b in zip(reference.position_enu, state.position_enu)]
        ve = [_finite(a-b, "velocity error") for a, b in zip(reference.velocity_enu, state.velocity_enu)]
        pe = [min(3.0, max(-3.0, x)) for x in pe]
        ve = [min(3.0, max(-3.0, x)) for x in ve]
        nominal = tuple(reference.acceleration_enu[i] + cfg.kp[i]*pe[i] + cfg.kd[i]*ve[i] for i in range(3))
        # The old integral feeds this cycle, including the cycle clearing it.
        raw_d = tuple(_finite(-1.0/cfg.t_ude_s * (cfg.kp[i]*self._integral[i]
                      + cfg.kd[i]*pe[i] + ve[i]), "observer") for i in range(3))
        integ = tuple(_finite(self._integral[i] + pe[i]*dt, "integral")
                      if abs(pe[i]) < 0.5 else 0.0 for i in range(3))
        disturbance = tuple(min(cfg.disturbance_limit[i], max(-cfg.disturbance_limit[i], raw_d[i])) for i in range(3))
        acc = tuple(_finite(nominal[i]-disturbance[i], "acceleration") for i in range(3))
        mg = _finite(cfg.mass_kg*9.8, "gravity force")
        force = [_finite(cfg.mass_kg*acc[i] + (mg if i == 2 else 0), "force") for i in range(3)]
        if force[2] == 0:
            raise ValueError("zero vertical force undefined in upstream UDE")
        target = min(_finite(2*mg, "force limit"), max(0.5*mg, force[2]))
        if target != force[2]:
            force = [_finite(x/force[2]*target, "scaled force") for x in force]
        tilt = math.tan(math.radians(cfg.tilt_limit_deg))
        for i in range(2):
            if abs(force[i]/force[2]) > tilt:
                force[i] = math.copysign(force[2]*tilt, force[i])
        w, x, y, z = state.attitude_flu_to_enu
        norm2 = w*w + x*x + y*y + z*z
        yaw = math.atan2(2*(w*z+x*y)/norm2, 1-2*(y*y+z*z)/norm2)
        c, s = math.cos(yaw), math.sin(yaw)
        fx, fy = c*force[0]+s*force[1], -s*force[0]+c*force[1]
        rpy = (math.atan2(-fy, force[2]), math.atan2(fx, force[2]), reference.yaw_enu_rad)
        body_z = (2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y))
        thrust = _finite(sum(a*b for a, b in zip(force, body_z)), "projected thrust")
        for value in (*nominal, *force, *rpy):
            _finite(value, "UDE output")
        output = UDEOutput(acc, tuple(force), rpy, thrust, integ, cfg.mass_kg, nominal, disturbance)
        self._integral, self.last_output = integ, output
        return output
