"""Fixed Prometheus NE port (ENU / FLU), without ROS or controller selection.

Source: 5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce, pos_controller_NE.h.
Preserves the upstream LLF update followed by output_LLF.setZero(), the
pre-integration disturbance estimate, and per-axis (not cone) tilt limits.
Differences: explicit mass, finite validated inputs, actual dt, atomic failed
cycles, and complete cold reset of filters (upstream init only sets their T).
Inactive calls reject; caller must reset on release, loss, epoch/timing change.
Tracking-error print statistics are omitted; they do not feed the algorithm.
Native thrust calibration remains the caller's explicit model/stack contract.
"""

from dataclasses import dataclass
import math

from .position_pid import PIDState, PIDReference, Vec3, _finite, _vector

UPSTREAM_COMMIT = "5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce"
UPSTREAM_NE_PATH = "Modules/uav_control/include/Position_Controller/pos_controller_NE.h"
UPSTREAM_NE_SHA256 = "759e3296ea32eb34050ed8764c75e4bd88f6ba8cdb52da82c5e10b745f45fe7f"
ZERO = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class NEConfig:
    mass_kg: float
    kp: Vec3 = (0.5, 0.5, 0.5)
    kd: Vec3 = (2.0, 2.0, 2.0)
    disturbance_limit: Vec3 = (1.0, 1.0, 1.0)
    t_ude_s: float = 1.0
    t_ne_s: float = 1.0
    tilt_limit_deg: float = 20.0

    def __post_init__(self):
        for name in ("mass_kg", "t_ude_s", "t_ne_s", "tilt_limit_deg"):
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
class NEMemory:
    integral: Vec3 = ZERO
    velocity_integral: Vec3 = ZERO
    lpf: Vec3 = ZERO
    hpf: Vec3 = ZERO
    hpf_input: Vec3 = ZERO
    llf: Vec3 = ZERO
    llf_input: Vec3 = ZERO


@dataclass(frozen=True)
class NEOutput:
    acceleration_enu: Vec3
    force_enu_n: Vec3
    roll_pitch_yaw_enu_rad: Vec3
    projected_thrust_n: float
    mass_kg: float
    noise_estimator: Vec3
    nominal_acceleration: Vec3
    disturbance_estimate: Vec3
    memory: NEMemory
    controller: str = "ne"


class PositionNE:
    name = "ne"

    def __init__(self, config: NEConfig):
        if not isinstance(config, NEConfig):
            raise ValueError("explicit NEConfig required")
        self.config = config
        self.reset("initialize")

    @property
    def memory(self):
        return self._memory

    @property
    def initial_position_enu(self):
        return self._initial_position

    def reset(self, reason: str, *, initial_position_enu=ZERO):
        """Cold reset, including all nine filters and initial-position binding.

        Zero initial position matches original construction; callers may bind
        an explicit position as upstream set_initial_pos would. Rebinding a
        running controller is deliberately available only through full reset.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reset reason required")
        initial = _vector(initial_position_enu, 3, "initial_position_enu")
        self._memory = NEMemory()
        self._initial_position = initial
        self.last_reset_reason = reason

    def update(self, state: PIDState, reference: PIDReference, *, dt_s: float,
               external_control_active: bool) -> NEOutput:
        dt = _finite(dt_s, "dt_s")
        if dt <= 0 or external_control_active is not True:
            raise ValueError("positive dt and verified active control required")
        if not isinstance(state, PIDState) or not isinstance(reference, PIDReference):
            raise ValueError("PIDState/PIDReference contract required")
        cfg, old = self.config, self._memory
        t = cfg.t_ne_s
        denom = _finite(t + dt, "filter denominator")
        pe = tuple(a-b for a, b in zip(reference.position_enu, state.position_enu))
        ve = tuple(a-b for a, b in zip(reference.velocity_enu, state.velocity_enu))
        hp_in = tuple(a-b for a, b in zip(self._initial_position, state.position_enu))
        lp = tuple(t/denom*old.lpf[i] + dt/denom*state.velocity_enu[i] for i in range(3))
        hp = tuple(1/denom*(t*old.hpf[i]+hp_in[i]-old.hpf_input[i]) for i in range(3))
        noise = tuple(lp[i]+hp[i] for i in range(3))
        nominal = tuple(reference.acceleration_enu[i] + cfg.kp[i]*pe[i]
                        + cfg.kd[i]*(ve[i]+noise[i]) for i in range(3))
        vi = tuple(old.velocity_integral[i]+state.velocity_enu[i]*dt for i in range(3))
        ll_in = tuple(vi[i]-state.position_enu[i]+self._initial_position[i] for i in range(3))
        ll = tuple(1/denom*(t*old.llf[i]+ll_in[i]-old.llf_input[i]
                           +dt*cfg.kd[i]*ll_in[i]) for i in range(3))
        # Original computes LLF then discards its output, but retains history.
        raw_dist = tuple(1/cfg.t_ude_s*(state.velocity_enu[i]-old.integral[i]) for i in range(3))
        integ = tuple(old.integral[i]+(reference.acceleration_enu[i]+cfg.kp[i]*pe[i]
                      +cfg.kd[i]*ve[i])*dt if abs(pe[i]) < 100 else 0.0 for i in range(3))
        for v in (*pe, *ve, *raw_dist, *integ, *vi, *lp, *hp, *ll, *ll_in, *hp_in, *nominal):
            _finite(v, "NE intermediate")
        dist = tuple(min(cfg.disturbance_limit[i], max(-cfg.disturbance_limit[i], raw_dist[i])) for i in range(3))
        acc = tuple(nominal[i]-dist[i] for i in range(3))
        mg = _finite(cfg.mass_kg*9.8, "weight")
        force = [cfg.mass_kg*acc[i]+(mg if i == 2 else 0) for i in range(3)]
        for v in force:
            _finite(v, "force")
        if force[2] == 0:
            raise ValueError("zero vertical force undefined upstream")
        target = min(2*mg, max(0.5*mg, force[2]))
        if target != force[2]:
            force = [v/force[2]*target for v in force]
        for v in force:
            _finite(v, "scaled force")
        tilt = math.tan(math.radians(cfg.tilt_limit_deg))
        for i in range(2):
            if abs(force[i]/force[2]) > tilt:
                force[i] = math.copysign(force[2]*tilt, force[i])
        w, x, y, z = state.attitude_flu_to_enu
        norm2 = w*w+x*x+y*y+z*z
        yaw = math.atan2(2*(w*z+x*y)/norm2, 1-2*(y*y+z*z)/norm2)
        c, s = math.cos(yaw), math.sin(yaw)
        rpy = (math.atan2(s*force[0]-c*force[1], force[2]),
               math.atan2(c*force[0]+s*force[1], force[2]), reference.yaw_enu_rad)
        body_z = (2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y))
        thrust = sum(a*b for a, b in zip(force, body_z))
        for v in (*acc, *force, *rpy, thrust):
            _finite(v, "NE output")
        memory = NEMemory(integ, vi, lp, hp, hp_in, ll, ll_in)
        out = NEOutput(acc, tuple(force), rpy, thrust, cfg.mass_kg, noise, nominal, dist, memory)
        self._memory = memory
        return out
