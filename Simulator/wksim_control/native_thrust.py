"""Multicopter hover calibration, independent of position algorithms.

This positive-collective mapping is not a fixed-wing surface or rover actuator
contract. Those vehicle families require their own measured actuator mapping.
"""
from dataclasses import dataclass
from typing import Literal

from .position_contract import GRAVITY, _finite


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

    def normalized_collective(self, output, *, model_identity: str) -> float:
        if model_identity != self.model_identity or output.mass_kg != self.mass_kg:
            raise ValueError("PID thrust mapping model identity or mass mismatch")
        thrust = _finite(output.projected_thrust_n, "projected_thrust_n")
        normalized = thrust / (self.mass_kg * GRAVITY / self.hover_thrust)
        return min(1.0, max(0.1, _finite(normalized, "normalized collective")))


