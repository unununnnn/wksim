"""Convert a fresh ArUco target observation into a bounded body velocity intent."""
from dataclasses import dataclass
import math
import re


SCHEMA = "wksim.target-intent.v1"
TARGET_SCHEMA = "wksim.aruco-target.v1"


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _identity(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _step(value, name):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,18}", value):
        return int(value)
    raise ValueError(f"{name} must be a non-negative authority step")


@dataclass(frozen=True)
class TargetIntentConfig:
    """Explicit task configuration; no flight or vehicle defaults are supplied."""

    desired_body_flu_m: tuple
    gain_per_s: float
    max_speed_mps: float

    def __post_init__(self):
        desired = tuple(self.desired_body_flu_m)
        if len(desired) != 3 or any(not _finite(value) for value in desired):
            raise ValueError("desired_body_flu_m must contain three finite values")
        if not _finite(self.gain_per_s) or self.gain_per_s <= 0:
            raise ValueError("gain_per_s must be positive and finite")
        if not _finite(self.max_speed_mps) or self.max_speed_mps <= 0:
            raise ValueError("max_speed_mps must be positive and finite")
        object.__setattr__(self, "desired_body_flu_m", desired)


class TargetIntent:
    """Bounded, non-ROS consumer of ``wksim.aruco-target.v1`` observations."""

    def __init__(self, config, *, run_id, epoch, stream_id):
        if not isinstance(config, TargetIntentConfig):
            raise TypeError("TargetIntentConfig is required; flight defaults are not provided")
        self.config = config
        self.run_id = _identity(run_id, "run_id")
        self.epoch = _identity(epoch, "epoch")
        self.stream_id = _identity(stream_id, "stream_id")
        self._last_step = None
        self.reason = "uninitialized"

    def bind(self, *, run_id, epoch, stream_id):
        """Switch authority binding and discard observations from the old stream."""
        run_id, epoch, stream_id = (_identity(run_id, "run_id"), _identity(epoch, "epoch"),
                                    _identity(stream_id, "stream_id"))
        changed = (run_id, epoch, stream_id) != (self.run_id, self.epoch, self.stream_id)
        self.run_id, self.epoch, self.stream_id = run_id, epoch, stream_id
        self._clear("awaiting_fresh_target" if changed else self.reason)

    def _clear(self, reason):
        self._last_step = None
        self.reason = reason

    def _hold(self, authority_step, reason):
        self._clear(reason)
        return {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "epoch": self.epoch,
            "stream_id": self.stream_id,
            "step": authority_step,
            "move_mode": "HOLD",
            "velocity_ref": [0.0, 0.0, 0.0],
            "yaw_rate_mode": True,
            "yaw_rate_ref": 0.0,
            "reason": reason,
        }

    def update(self, target, *, authority_step):
        """Return XYZ_VEL_BODY for one fresh target, otherwise an explicit HOLD."""
        try:
            authority_step = _step(authority_step, "authority_step")
        except ValueError as error:
            self._clear("invalid_authority_step")
            raise ValueError(str(error)) from error
        if target is None:
            return self._hold(authority_step, "target_missing")
        if not isinstance(target, dict):
            return self._hold(authority_step, "target_invalid")
        try:
            if target.get("schema") != TARGET_SCHEMA:
                raise ValueError("target schema differs")
            if any(target.get(key) != value for key, value in (
                    ("run_id", self.run_id), ("epoch", self.epoch), ("stream_id", self.stream_id))):
                raise ValueError("target authority binding differs")
            target_step = _step(target.get("step"), "target.step")
            valid_until = _step(target.get("valid_until_step"), "target.valid_until_step")
            if valid_until < target_step:
                raise ValueError("target validity ends before its capture step")
            if target_step > authority_step:
                raise ValueError("target is from the future")
            if authority_step > valid_until:
                raise ValueError("target is expired")
            if self._last_step is not None and target_step <= self._last_step:
                raise ValueError("target step is duplicate or regressing")
            observed = target.get("position_body_flu_m")
            if (not isinstance(observed, list) or len(observed) != 3
                    or any(not _finite(value) for value in observed)):
                raise ValueError("target body position is invalid")
            error = [desired - actual for desired, actual in zip(self.config.desired_body_flu_m, observed)]
            velocity = [self.config.gain_per_s * value for value in error]
            norm = math.sqrt(sum(value * value for value in velocity))
            if not _finite(norm):
                raise ValueError("target velocity is not finite")
            if norm > self.config.max_speed_mps:
                scale = self.config.max_speed_mps / norm
                velocity = [value * scale for value in velocity]
            if any(not _finite(value) for value in velocity):
                raise ValueError("bounded velocity is not finite")
        except (KeyError, TypeError, ValueError) as error:
            return self._hold(authority_step, "rejected: " + str(error))
        self._last_step = target_step
        self.reason = "target_accepted"
        return {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "epoch": self.epoch,
            "stream_id": self.stream_id,
            "step": target_step,
            "valid_until_step": valid_until,
            "move_mode": "XYZ_VEL_BODY",
            "velocity_ref": velocity,
            "yaw_rate_mode": True,
            "yaw_rate_ref": 0.0,
        }
