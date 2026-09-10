"""Joint-gated seam from a fresh ArUco target to the public velocity entry.

The camera chain is accepted only against the authoritative joint dual-vehicle
scene state: both joint stacks (px4 + arducopter) must share one run/epoch,
and the RGB stream must be the one the authoritative View bound. A
single-stack status, a foreign or replayed frame, or a regressing authority
step never reaches the public command fields.

Identity rules follow the existing contracts, not new ones: run_id uses the
product rule from ``wksim_core.state_stream.identity``
(``[A-Za-z0-9][A-Za-z0-9_-]{0,63}``, e.g. the real #103 run
``aruco-scene-267899ace7``); epoch/stream/instance stay strict hex32 per
``Consumer.bind``/``Reader.set_epoch``. Binding transitions follow those same
sources: a new epoch requires a strictly higher generation; a camera restart
may replace its stream within one epoch. An identical binding keeps
TargetIntent's deduplication history; retired epochs/streams never revive.

This module reuses ``wksim_perception.target_intent.TargetIntent`` unchanged,
has no ROS dependency and publishes nothing. HOLD is not a stop: the control
processor re-resolves the last accepted MOVE every cycle
(``command.py`` ``step``), so a HOLD record carries an explicit
``hold_action`` telling the runtime task to publish the public
``CURRENT_POS_HOVER`` command (or follow its revocation path) if it actually
wants to stop the persisted velocity setpoint.
"""
import copy
import re

from Simulator.wksim_perception.target_intent import TargetIntent, TargetIntentConfig


AUTHORITY_SCHEMA = "wksim.aruco-joint-authority.v1"
SEAM_SCHEMA = "wksim.aruco-tracking-input.v1"
JOINT_STACKS = ("px4", "arducopter")
MAX_STEP = 9007199254  # Consumer.current / Reader.set_epoch upper bound.
HOLD_PUBLIC_COMMAND = "CURRENT_POS_HOVER"  # UAVCommand agent_cmd=2; replaces the persisted MOVE.

_HEX32 = re.compile(r"[0-9a-f]{32}")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def _run_id(value):
    if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
        raise ValueError("run_id must be 1..64 ASCII letters/digits/underscore/hyphen, starting alphanumeric")
    return value


def _hex32(value, name):
    if not isinstance(value, str) or _HEX32.fullmatch(value) is None:
        raise ValueError(f"{name} must be a 32-digit hex identity")
    return value


def _step(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative authority step")
    if isinstance(value, str):
        if re.fullmatch(r"0|[1-9][0-9]{0,18}", value) is None:
            raise ValueError(f"{name} must be a non-negative authority step")
        value = int(value)
    if not isinstance(value, int) or not 0 <= value <= MAX_STEP:
        raise ValueError(f"{name} must be within 0..{MAX_STEP}")
    return value


def validate_authority(value):
    """Normalize one joint dual-vehicle authority record; reject any other shape."""
    if not isinstance(value, dict):
        raise ValueError("authority must be a dict")
    if value.get("schema") != AUTHORITY_SCHEMA:
        raise ValueError("authority schema differs")
    if value.get("kind") != "joint_scene":
        raise ValueError("authority is not the authoritative joint scene state")
    authority = {
        "schema": AUTHORITY_SCHEMA,
        "kind": "joint_scene",
        "run_id": _run_id(value.get("run_id")),
        "epoch": _hex32(value.get("epoch"), "epoch"),
        "instance_id": _hex32(value.get("instance_id"), "instance_id"),
        "stream_id": _hex32(value.get("stream_id"), "stream_id"),
        "generation": None,
        "authority_step": _step(value.get("authority_step"), "authority_step"),
    }
    generation = value.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise ValueError("generation must be a positive integer")
    authority["generation"] = generation
    camera = value.get("camera")
    if not isinstance(camera, dict):
        raise ValueError("camera binding is missing")
    vehicle_id = camera.get("vehicle_id")
    if not isinstance(vehicle_id, int) or isinstance(vehicle_id, bool) or not 1 <= vehicle_id <= 2:
        raise ValueError("camera vehicle_id must be a joint vehicle 1..2")
    sensor_id = camera.get("sensor_id")
    if not isinstance(sensor_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", sensor_id):
        raise ValueError("camera sensor identity is invalid")
    authority["camera"] = {"vehicle_id": vehicle_id, "sensor_id": sensor_id}
    vehicles = value.get("vehicles")
    if not isinstance(vehicles, dict) or set(vehicles) != set(JOINT_STACKS):
        raise ValueError("authority must bind both joint stacks; single-stack state is not accepted")
    authority["vehicles"] = {}
    for stack in JOINT_STACKS:
        entry = vehicles[stack]
        if not isinstance(entry, dict):
            raise ValueError(f"vehicle {stack} entry is missing")
        uav_id = entry.get("uav_id")
        if not isinstance(uav_id, int) or isinstance(uav_id, bool) or not 1 <= uav_id <= 255:
            raise ValueError(f"vehicle {stack} uav_id must be in 1..255")
        if entry.get("run_id") != authority["run_id"] or entry.get("epoch") != authority["epoch"]:
            raise ValueError(f"vehicle {stack} does not share the joint run/epoch")
        authority["vehicles"][stack] = {"uav_id": uav_id}
    return authority


def command_fields(intent):
    """Map one target intent onto public command fields; HOLD publishes nothing.

    Only the public Prometheus velocity subset is ever returned; Consumer
    diagnostics (world position/velocity, reprojection) are never forwarded.
    A ``None`` result never implies the vehicle stops: see ``hold_action``.
    """
    if not isinstance(intent, dict) or intent.get("move_mode") != "XYZ_VEL_BODY":
        return None
    velocity = intent.get("velocity_ref")
    if not isinstance(velocity, list) or len(velocity) != 3:
        return None
    return {
        "agent_cmd": "MOVE",
        "move_mode": "XYZ_VEL_BODY",
        "velocity_ref": [float(value) for value in velocity],
        "yaw_rate_mode": True,
        "yaw_rate_ref": 0.0,
    }


def hold_action(reason):
    """Explicit stop requirement attached to every seam HOLD record.

    The control processor re-resolves the last accepted MOVE command every
    cycle, so losing the target does NOT stop the vehicle by itself. The
    runtime task must publish the public ``CURRENT_POS_HOVER`` command (or
    follow its own revocation path) to replace the persisted velocity setpoint.
    """
    return {
        "required": True,
        "public_command": HOLD_PUBLIC_COMMAND,
        "effect": "replaces the persisted velocity setpoint with a hover at the current position",
        "reason": reason,
    }


class ArucoTrackingSeam:
    """Bounded joint-gated consumer of ``wksim.aruco-target.v1`` targets."""

    def __init__(self, config, *, authority):
        if not isinstance(config, TargetIntentConfig):
            raise TypeError("TargetIntentConfig is required; flight defaults are not provided")
        self.authority = validate_authority(authority)
        self.intent = TargetIntent(config, run_id=self.authority["run_id"],
                                   epoch=self.authority["epoch"], stream_id=self.authority["stream_id"])
        self._last_authority_step = self.authority["authority_step"]
        self._minimum_target_step = self.authority['authority_step']
        self._retired_epochs = set()
        self._retired_streams = set()
        self.reason = "bound"

    def _record(self, authority_step, reason, intent, command):
        return {
            "schema": SEAM_SCHEMA,
            "run_id": self.authority["run_id"],
            "epoch": self.authority["epoch"],
            "stream_id": self.authority["stream_id"],
            "instance_id": self.authority["instance_id"],
            "generation": self.authority["generation"],
            "authority_step": authority_step,
            "reason": reason,
            "intent": intent,
            "command": command,
            "hold_action": None if command is not None else hold_action(reason),
        }

    def _hold(self, authority_step, reason):
        self.reason = reason
        intent = self.intent.update(None, authority_step=authority_step)
        intent["reason"] = reason
        return self._record(authority_step, reason, intent, None)

    def _foreign(self, target):
        """Camera-stream identity not covered by the TargetIntent binding."""
        camera = self.authority["camera"]
        return any(target.get(key) != expected for key, expected in (
            ("instance_id", self.authority["instance_id"]),
            ("generation", self.authority["generation"]),
            ("vehicle_id", str(camera["vehicle_id"])),
            ("sensor_id", camera["sensor_id"])))

    def rebind(self, authority, *, authority_step):
        """Accept a newer joint binding; identical binding is a no-op.

        Follows Consumer.bind/Reader.set_epoch: generation strictly increases
        together with a new epoch, while a new stream can join the same epoch;
        a retired epoch or stream never revives;
        every check runs before any state changes, so failure cannot partially
        rewrite the binding. ``authority_step`` must equal the record's own
        ``authority_step`` so the parameter never contradicts the structure.
        """
        authority = validate_authority(authority)
        authority_step = _step(authority_step, "authority_step")
        if authority_step != authority["authority_step"]:
            raise ValueError("authority_step contradicts the authority record")
        previous = self.authority
        if authority["epoch"] in self._retired_epochs:
            raise ValueError("retired epoch cannot be revived")
        if authority["stream_id"] in self._retired_streams:
            raise ValueError("retired stream cannot be revived")
        if authority["generation"] < previous["generation"]:
            raise ValueError("generation regressed; retired binding")
        if any(authority[key] != previous[key] for key in ('run_id','instance_id','camera','vehicles')):
            raise ValueError('Run, instance and camera configuration require a new tracking object')
        if authority["generation"] == previous["generation"]:
            if authority["epoch"] != previous["epoch"]:
                raise ValueError("epoch changed without a new generation")
            if authority_step < self._last_authority_step:
                raise ValueError("authority step regressed within one binding")
            if authority['stream_id'] == previous['stream_id']:
                self.authority = authority
                self._last_authority_step = authority_step
                return copy.deepcopy(self.authority)  # Keep TargetIntent history.
        elif authority["epoch"] == previous["epoch"]:
            raise ValueError("generation advanced without a new epoch")
        # All checks passed; only now mutate. The old binding is retired.
        if previous['epoch'] != authority['epoch']:
            self._retired_epochs.add(previous["epoch"])
        if previous['stream_id'] != authority['stream_id']:
            self._retired_streams.add(previous["stream_id"])
        self.authority = authority
        self._last_authority_step = authority_step
        self._minimum_target_step = authority_step
        self.intent.bind(run_id=authority["run_id"], epoch=authority["epoch"],
                         stream_id=authority["stream_id"])
        self.reason = "rebound"
        return copy.deepcopy(self.authority)

    def update(self, target, *, authority_step):
        """One authority step: return the seam record; replay never reaches command."""
        authority_step = _step(authority_step, "authority_step")
        if authority_step < self._last_authority_step:
            raise ValueError("authority step regressed; a replayed frame is not a fresh authority")
        self._last_authority_step = authority_step
        if target is not None and isinstance(target, dict) and self._foreign(target):
            # Rejected before TargetIntent: a foreign frame must not consume a step.
            return self._hold(authority_step, "foreign_camera_stream")
        if isinstance(target,dict):
            try:
                if _step(target.get('step'),'target.step') < self._minimum_target_step:
                    return self._hold(authority_step,'target_before_binding')
            except ValueError:
                return self._hold(authority_step,'invalid_target_step')
        intent = self.intent.update(copy.deepcopy(target), authority_step=authority_step)
        if intent["move_mode"] == "XYZ_VEL_BODY":
            self.reason = "target_accepted"
            return self._record(authority_step, self.reason, intent, command_fields(intent))
        self.reason = intent.get("reason", "rejected")
        return self._record(authority_step, self.reason, intent, None)
