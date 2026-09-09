"""Small, fail-closed adapter from planner samples to public move intents.

The EGO planner owns trajectory generation.  This module owns only session
identity, generation invalidation, stop precedence, and command-id allocation.
It has no ROS or planner dependency so the boundary can be tested directly.
"""

from dataclasses import dataclass
import math
from numbers import Real
from typing import Mapping


MAX_COMMAND_ID = 2**32 - 1
MAX_GENERATION = 2**63 - 1
STATES = frozenset(("WAITING", "ACTIVE", "HOLD", "CANCELLED", "RELEASED", "FAULTED"))
_STOP_REASONS = frozenset(("stop", "no-route", "replan", "cancel", "release", "control-lost", "fault"))


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def _vector(value, name):
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must contain three numbers")
    try:
        values = tuple(value)
    except TypeError as error:
        raise ValueError(f"{name} must contain three numbers") from error
    if len(values) != 3:
        raise ValueError(f"{name} must contain three numbers")
    return tuple(_finite(item, name) for item in values)


def _uint(value, name, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [0, {maximum}]")
    return value


@dataclass(frozen=True)
class Identity:
    run_id: str
    mission_id: str
    uav_id: int
    control_epoch: str
    planner_generation: int = 0
    command_high_water: int = 0

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            value = value.__dict__
        if not isinstance(value, Mapping):
            raise ValueError("session identity must be a mapping")
        required = ("run_id", "mission_id", "control_epoch")
        if any(not isinstance(value.get(key), str) or not value[key] for key in required):
            raise ValueError("run_id, mission_id and control_epoch must be non-empty strings")
        if type(value["uav_id"]) is not int or value["uav_id"] != 1:
            raise ValueError("trajectory session only supports uav_id=1")
        generation = _uint(value.get("planner_generation", 0), "planner_generation", MAX_GENERATION)
        high_water = _uint(value.get("command_high_water", 0), "command_high_water", MAX_COMMAND_ID)
        return cls(value["run_id"], value["mission_id"], value["uav_id"], value["control_epoch"],
                   generation, high_water)


class TrajectorySession:
    """One serial planner owner with monotonic public command identities."""

    def __init__(self, identity):
        self.identity = Identity.from_value(identity)
        self.state = "WAITING"
        self.generation = self.identity.planner_generation
        self.last_command_id = self.identity.command_high_water
        self.last_event_sequence = None
        self._trajectory = None
        self._sample = None
        self._last_sample_tick = None
        self._last_output_tick = None
        self._hold_anchor = None
        self._last_reason = None

    def _check_identity(self, value, generation=None):
        candidate = Identity.from_value(value)
        if (candidate.run_id, candidate.mission_id, candidate.uav_id, candidate.control_epoch) != (
                self.identity.run_id, self.identity.mission_id, self.identity.uav_id, self.identity.control_epoch):
            raise ValueError("trajectory identity differs from the active session")
        expected = self.generation if generation is None else generation
        if candidate.planner_generation != expected:
            raise ValueError("planner generation differs from the active session")
        return candidate

    def _event(self, identity, event_sequence, generation=None):
        self._check_identity(identity, generation)
        _uint(event_sequence, "event_sequence", MAX_COMMAND_ID)
        if self.last_event_sequence is not None and event_sequence <= self.last_event_sequence:
            raise ValueError("event sequence must increase")
        self.last_event_sequence = event_sequence

    def _bump_generation(self):
        if self.generation == MAX_GENERATION:
            self.state = "FAULTED"
            self._clear_trajectory()
            raise OverflowError("planner generation exhausted")
        self.generation += 1
        self._clear_trajectory()
        return self.generation

    def _clear_trajectory(self):
        self._trajectory = None
        self._sample = None
        self._last_sample_tick = None

    @staticmethod
    def _anchor(value):
        if isinstance(value, Mapping):
            try:
                position, yaw = value["position"], value["yaw"]
            except KeyError as error:
                raise ValueError("anchor requires position and yaw") from error
        else:
            try:
                position, yaw = value
            except (TypeError, ValueError) as error:
                raise ValueError("anchor requires position and yaw") from error
        return dict(position=list(_vector(position, "anchor.position")), yaw=_finite(yaw, "anchor.yaw"))

    def begin_replan(self, identity, event_sequence):
        """Invalidate the old result before a new planner generation starts."""
        if self.state in ("CANCELLED", "RELEASED", "FAULTED"):
            raise ValueError("session cannot replan after terminal stop")
        self._event(identity, event_sequence)
        if self._sample is not None:
            self._hold_anchor = dict(position=self._sample["position"], yaw=self._sample["yaw"])
        self._bump_generation()
        self.state = "HOLD"
        self._last_reason = "replan"
        return self.generation

    def accept_trajectory(self, identity, generation, trajectory_id, start_tick, end_tick):
        """Accept only the result belonging to the currently requested generation."""
        if self.state in ("CANCELLED", "RELEASED", "FAULTED"):
            raise ValueError("session is not accepting trajectories")
        if generation != self.generation:
            raise ValueError("trajectory generation is stale")
        self._check_identity(identity, generation)
        _uint(generation, "generation", MAX_GENERATION)
        _uint(trajectory_id, "trajectory_id", MAX_COMMAND_ID)
        _uint(start_tick, "start_tick", 2**63 - 1)
        _uint(end_tick, "end_tick", 2**63 - 1)
        if start_tick >= end_tick:
            raise ValueError("trajectory interval must be non-empty")
        self._trajectory = dict(generation=generation, trajectory_id=trajectory_id,
                                start_tick=start_tick, end_tick=end_tick)
        self._sample = None
        self._last_sample_tick = None
        self.state = "ACTIVE"
        self._last_reason = None
        return True

    def sample(self, identity, generation, trajectory_id, tick, position, velocity, acceleration, yaw,
               *, valid_until_tick=None):
        """Record a finite, strictly ordered planner sample."""
        if self.state in ("CANCELLED", "RELEASED", "FAULTED"):
            raise ValueError("session is not accepting samples")
        if generation != self.generation:
            raise ValueError("sample generation is stale")
        self._check_identity(identity, generation)
        if self._trajectory is None or self._trajectory["generation"] != generation:
            raise ValueError("trajectory generation is not active")
        _uint(trajectory_id, "trajectory_id", MAX_COMMAND_ID)
        if trajectory_id != self._trajectory["trajectory_id"]:
            raise ValueError("trajectory result is stale")
        _uint(tick, "sample_tick", 2**63 - 1)
        if not self._trajectory["start_tick"] <= tick < self._trajectory["end_tick"]:
            raise ValueError("sample tick is outside the trajectory interval")
        if self._last_sample_tick is not None and tick <= self._last_sample_tick:
            raise ValueError("sample ticks must increase")
        if valid_until_tick is None:
            valid_until_tick = tick
        _uint(valid_until_tick, "valid_until_tick", 2**63 - 1)
        if not tick <= valid_until_tick <= self._trajectory["end_tick"]:
            raise ValueError("sample validity interval is invalid")
        row = dict(tick=tick, valid_until_tick=valid_until_tick,
                   position=_vector(position, "position"), velocity=_vector(velocity, "velocity"),
                   acceleration=_vector(acceleration, "acceleration"), yaw=_finite(yaw, "yaw"),
                   generation=generation, trajectory_id=trajectory_id)
        self._sample = row
        self._last_sample_tick = tick
        self._hold_anchor = dict(position=row["position"], yaw=row["yaw"])
        return dict(row)

    def stop(self, reason, identity, event_sequence, anchor=None):
        """Apply a stop event before any sample at the same adapter tick."""
        if reason not in _STOP_REASONS:
            raise ValueError("unknown stop reason")
        if self.state in ("CANCELLED", "RELEASED", "FAULTED"):
            raise ValueError("session is already terminal")
        self._event(identity, event_sequence)
        if anchor is not None:
            self._hold_anchor = self._anchor(anchor)
        elif reason in ("stop", "no-route", "replan") and self._hold_anchor is None:
            raise ValueError("a hold anchor is required before stopping")
        self._bump_generation()
        self._last_reason = reason
        self.state = "CANCELLED" if reason == "cancel" else (
            "RELEASED" if reason in ("release", "control-lost") else (
                "FAULTED" if reason == "fault" else "HOLD"))
        return self.state

    def _allocate_command(self):
        if self.last_command_id >= MAX_COMMAND_ID:
            self.state = "FAULTED"
            self._clear_trajectory()
            raise OverflowError("public command_id exhausted")
        self.last_command_id += 1
        return self.last_command_id

    def _hold_output(self, tick):
        if self._hold_anchor is None:
            return None
        position, yaw = self._hold_anchor["position"], self._hold_anchor["yaw"]
        return dict(agent_cmd=4, move_mode=0, command_id=self._allocate_command(),
                    position_ref=list(position), velocity_ref=[0.0, 0.0, 0.0],
                    acceleration_ref=[0.0, 0.0, 0.0], yaw_ref=yaw, yaw_rate_mode=False,
                    yaw_rate_ref=0.0, generation=self.generation, tick=tick,
                    intent="hold")

    def _trajectory_output(self, tick):
        sample = self._sample
        if sample is None or tick < sample["tick"]:
            return None
        if tick > sample["valid_until_tick"]:
            self.state = "HOLD"
            self._last_reason = "sample-expired"
            return self._hold_output(tick)
        return dict(agent_cmd=4, move_mode=6, command_id=self._allocate_command(),
                    position_ref=list(sample["position"]), velocity_ref=list(sample["velocity"]),
                    acceleration_ref=list(sample["acceleration"]), yaw_ref=sample["yaw"],
                    yaw_rate_mode=False, yaw_rate_ref=0.0, generation=self.generation,
                    trajectory_id=sample["trajectory_id"], tick=tick, intent="trajectory")

    def next_output(self, tick, owns_control, state_fresh):
        """Return one public intent, applying safety state before trajectory data."""
        _uint(tick, "tick", 2**63 - 1)
        if type(owns_control) is not bool or type(state_fresh) is not bool:
            raise ValueError("owns_control and state_fresh must be bool")
        if self._last_output_tick is not None and tick <= self._last_output_tick:
            raise ValueError("output ticks must increase")
        self._last_output_tick = tick
        if not state_fresh:
            if self.state != "FAULTED":
                self._bump_generation()
            self.state = "FAULTED"
            self._last_reason = "state-stale"
            return None
        if not owns_control:
            if self.state != "RELEASED":
                self._bump_generation()
            self.state = "RELEASED"
            self._last_reason = "control-lost"
            return None
        if self.state == "ACTIVE":
            if self._trajectory is None or tick >= self._trajectory["end_tick"]:
                self.state = "HOLD"
                self._last_reason = "trajectory-ended"
                return self._hold_output(tick)
            return self._trajectory_output(tick)
        if self.state == "HOLD":
            return self._hold_output(tick)
        return None
