"""Offline display-scene binding for wksim.display-manifest.v1.

This module is a fail-closed consumer of existing identities.  It validates
display manifests, consumes ``wksim.contact.v1`` envelopes at a frame that
equals the authority step, and checks a freeze/recover frame-evidence schema.
It does not start or control UE, ROS, FC, native, MATLAB, or a build, and it
does not close issue #29.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from Simulator.wksim_core.static_contact import ERROR_CODES, TICK_NS, ContactError
from Simulator.wksim_planning.scene_profile import (
    EGO_SINGLE_BOX_V1,
    PROFILE_ID,
    SCENE_PROFILE_HASH,
)
from Simulator.wksim_runtime.contact_observer import (
    CONTACT_FIELDS,
    ContactObserver,
    DEFAULT_SCENE_PATH,
    FROZEN_SCENE_SHA256,
)
from Simulator.wksim_runtime.planner_scene_binding import (
    BINDING_SOURCE_IDENTITY as PLANNER_BINDING_SOURCE_IDENTITY,
    EGO_SINGLE_BOX_BINDING,
    EXPECTED_PROFILE_HASH,
    EXPECTED_SCENE_HASH,
    LEGACY_SCENE_HASH,
    LEGACY_SCENE_ID,
    PROFILE_SOURCE_IDENTITY,
)
from Simulator.wksim_runtime.terrain_feedback import STACK_BODIES, TerrainFeedback


DISPLAY_MANIFEST_SCHEMA = "wksim.display-manifest.v1"
CONTACT_SCHEMA = "wksim.contact.v1"
FRAME_SCHEMA = "wksim.display-frame.v1"
FRAME_EVIDENCE_SCHEMA = "wksim.display-frame-evidence.v1"
BINDING_SCHEMA = "wksim.display-scene-binding.v1"
TERRAIN_MANIFEST_SCHEMA = "wksim.terrain-feedback-manifest.v1"

DISPLAY_SCENE_ID = LEGACY_SCENE_ID
DISPLAY_SCENE_HASH = FROZEN_SCENE_SHA256
COORDINATE_FRAME = "ENU"
UNIT = "metre"
PHYSICS_AUTHORITY = "WSL"
AUTHORITY_TEXT = (
    "physics is authoritative in WSL; this manifest is display-only "
    "and cannot alter physics"
)
BINDING_SOURCE_IDENTITY = "Simulator/wksim_runtime/display_scene_binding.py"
OBSERVER_SOURCE_IDENTITY = "Simulator/wksim_runtime/contact_observer.py"
TERRAIN_SOURCE_IDENTITY = "Simulator/wksim_runtime/terrain_feedback.py"

PROBE_SCENE_ID = "static-plane-box-v1-real-tick0"
PROBE_SCENE_HASH = "4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300"

RETAINED_LIVE_EPOCH = "c3d4e5f60718293a4b5c6d7e8f90a1b2"
RETAINED_FREEZE_FRAME = 30019
RETAINED_BOUNDARY_STEP = 29999
RETAINED_RECOVER_FRAME = 30039
RETAINED_FREEZE_REASON = "stale_feedback"
RETAINED_RECOVER_REASON = "fresh valid feedback after freeze; explicit recovery"

OBSERVER_MANIFEST_FIELDS = frozenset({
    "schema", "scene_id", "scene_hash", "coordinate_frame", "unit",
    "origin_enu_m", "plane", "box",
})
RETAINED_MANIFEST_FIELDS = frozenset({
    "schema", "scene_id", "scene_hash", "coordinate_frame", "unit",
    "display_geometries", "authority",
})
FRAME_RECORD_FIELDS = frozenset({
    "schema", "scene_id", "scene_hash", "epoch", "frame", "result", "envelope",
})
FRAME_EVIDENCE_FIELDS = frozenset({
    "schema", "scene_id", "scene_hash", "epoch", "tick_ns",
    "contact_schema", "display_manifest_schema",
    "display_modifies_physics", "ue_session", "ue_disconnect_reconnect",
    "acceptance", "events", "source_identity",
})
FREEZE_EVENT_FIELDS = frozenset({"event", "frame", "reason", "boundary_step"})
RECOVER_EVENT_FIELDS = frozenset({"event", "frame", "reason"})
FRAME_RESULTS = frozenset({"contact", "no_contact", "frozen"})
FREEZE_REASONS = frozenset(ERROR_CODES) - {"accepted"}
FORBIDDEN_FORCE_FIELDS = (
    "force", "contact_force", "impulse", "stiffness", "damping",
    "friction", "torque", "wrench",
)

if (DISPLAY_SCENE_HASH != LEGACY_SCENE_HASH
        or DISPLAY_SCENE_ID != LEGACY_SCENE_ID
        or EGO_SINGLE_BOX_BINDING.scene_hash != EXPECTED_SCENE_HASH
        or EGO_SINGLE_BOX_V1.profile_id != PROFILE_ID
        or EGO_SINGLE_BOX_V1.profile_hash != EXPECTED_PROFILE_HASH
        or EGO_SINGLE_BOX_V1.profile_hash != SCENE_PROFILE_HASH
        or EGO_SINGLE_BOX_BINDING.manifest["visual_mirror"]
        != {"system": "UE", "binding_status": "not_bound"}
        or len({DISPLAY_SCENE_HASH, EXPECTED_SCENE_HASH, PROBE_SCENE_HASH}) != 3
        or DISPLAY_SCENE_ID == PROFILE_ID
        or DISPLAY_SCENE_ID == PROBE_SCENE_ID):
    raise RuntimeError("display-scene binding identities drifted from committed modules")


class DisplaySceneBindingError(ValueError):
    """Raised when a display manifest, frame, or contact record is unsafe."""


class DisplaySceneIdentityError(DisplaySceneBindingError):
    """Raised when a record names a different scene identity."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DisplaySceneBindingError("value is not canonically serializable") from error


def _copy(value: Any) -> Any:
    return deepcopy(value)


def _epoch(value: Any) -> str:
    if (not isinstance(value, str) or len(value) != 32 or value != value.lower()
            or any(character not in "0123456789abcdef" for character in value)):
        raise DisplaySceneBindingError("epoch must be a lowercase 32-character hexadecimal id")
    return value


def _nonneg_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise DisplaySceneBindingError(f"{name} must be a non-negative integer")
    return value


def _identity(value: Any, name: str) -> str:
    if (not isinstance(value, str) or not value or value.strip() != value
            or "\x00" in value):
        raise DisplaySceneBindingError(f"{name} must be a non-empty identity string")
    return value


def _hash(value: Any, name: str) -> str:
    if (not isinstance(value, str) or len(value) != 64 or value != value.lower()
            or any(character not in "0123456789abcdef" for character in value)):
        raise DisplaySceneBindingError(f"{name} must be a lowercase SHA-256 hexadecimal string")
    return value


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DisplaySceneBindingError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_foreign_identity(scene_id: Any, scene_hash: Any) -> None:
    if scene_id == PROFILE_ID or scene_hash == EXPECTED_SCENE_HASH:
        raise DisplaySceneIdentityError("planner ego identity cannot be used as display identity")
    if scene_id == PROBE_SCENE_ID or scene_hash == PROBE_SCENE_HASH:
        raise DisplaySceneIdentityError("generated-model probe identity cannot be used as display identity")
    if scene_id != DISPLAY_SCENE_ID or scene_hash != DISPLAY_SCENE_HASH:
        raise DisplaySceneIdentityError("display scene identity mismatch")


def _reject_force_fields(record: dict[str, Any]) -> None:
    for field in FORBIDDEN_FORCE_FIELDS:
        if field in record:
            raise DisplaySceneBindingError("display binding cannot consume force or impulse fields")


def observer_display_manifest(observer: ContactObserver) -> dict[str, Any]:
    """Return the observer's display-only manifest without adding fields."""
    manifest = observer.get_display_manifest()
    if type(manifest) is not dict or set(manifest) != OBSERVER_MANIFEST_FIELDS:
        raise DisplaySceneBindingError("observer display manifest shape is invalid")
    return _copy(manifest)


def retained_display_manifest(observer: ContactObserver) -> dict[str, Any]:
    """Return the #81 on-disk display-manifest.v1 shape from the bound scene."""
    scene = observer.scene
    return {
        "schema": DISPLAY_MANIFEST_SCHEMA,
        "scene_id": scene.scene_id,
        "scene_hash": scene.scene_sha256,
        "coordinate_frame": COORDINATE_FRAME,
        "unit": UNIT,
        "display_geometries": [
            {"geometry_id": scene.plane_id, "kind": "plane", "z_m": float(scene.plane_z)},
            {
                "geometry_id": scene.box_id,
                "kind": "box",
                "center_enu_m": list(scene.box_center),
                "size_m": list(scene.box_size),
            },
        ],
        "authority": AUTHORITY_TEXT,
    }


def retained_offline_frame_evidence() -> dict[str, Any]:
    """Return the #81 freeze/recover pins. This is not a UE session record."""
    return {
        "schema": FRAME_EVIDENCE_SCHEMA,
        "scene_id": DISPLAY_SCENE_ID,
        "scene_hash": DISPLAY_SCENE_HASH,
        "epoch": RETAINED_LIVE_EPOCH,
        "tick_ns": TICK_NS,
        "contact_schema": CONTACT_SCHEMA,
        "display_manifest_schema": DISPLAY_MANIFEST_SCHEMA,
        "display_modifies_physics": False,
        "ue_session": False,
        "ue_disconnect_reconnect": False,
        "acceptance": False,
        "events": [
            {
                "event": "freeze",
                "frame": RETAINED_FREEZE_FRAME,
                "reason": RETAINED_FREEZE_REASON,
                "boundary_step": RETAINED_BOUNDARY_STEP,
            },
            {
                "event": "recover",
                "frame": RETAINED_RECOVER_FRAME,
                "reason": RETAINED_RECOVER_REASON,
            },
        ],
        "source_identity": BINDING_SOURCE_IDENTITY,
    }


class DisplaySceneBinding:
    """Bind the frozen display fixture and consume contact/frame records."""

    def __init__(self, run_epoch: str, scene_source=DEFAULT_SCENE_PATH,
                 expected_sha256: str = DISPLAY_SCENE_HASH) -> None:
        epoch = _epoch(run_epoch)
        expected = _hash(expected_sha256, "expected_sha256")
        _reject_foreign_identity(DISPLAY_SCENE_ID, expected)
        try:
            self.observer = ContactObserver(
                scene_source=scene_source,
                run_epoch=epoch,
                expected_sha256=expected,
            )
        except ContactError as error:
            raise DisplaySceneBindingError(error.reason) from error
        if (self.observer.scene.scene_id != DISPLAY_SCENE_ID
                or self.observer.scene.scene_sha256 != DISPLAY_SCENE_HASH):
            raise DisplaySceneIdentityError("display scene identity mismatch")
        self.epoch = epoch

    def display_manifest(self) -> dict[str, Any]:
        return observer_display_manifest(self.observer)

    def retained_manifest(self) -> dict[str, Any]:
        return retained_display_manifest(self.observer)

    def validate_manifest(self, manifest: Any) -> dict[str, Any]:
        if type(manifest) is not dict:
            raise DisplaySceneBindingError("display manifest must be a mapping")
        _reject_force_fields(manifest)
        fields = set(manifest)
        if fields == OBSERVER_MANIFEST_FIELDS:
            expected = observer_display_manifest(self.observer)
        elif fields == RETAINED_MANIFEST_FIELDS:
            expected = retained_display_manifest(self.observer)
        else:
            _reject_foreign_identity(manifest.get("scene_id"), manifest.get("scene_hash"))
            raise DisplaySceneBindingError("display manifest field set is not an accepted v1 form")
        if manifest.get("schema") != DISPLAY_MANIFEST_SCHEMA:
            raise DisplaySceneBindingError("display manifest schema mismatch")
        _reject_foreign_identity(manifest.get("scene_id"), manifest.get("scene_hash"))
        if (manifest.get("coordinate_frame") != COORDINATE_FRAME
                or manifest.get("unit") != UNIT):
            raise DisplaySceneBindingError("display manifest frame or unit mismatch")
        if _canonical_bytes(manifest) != _canonical_bytes(expected):
            raise DisplaySceneIdentityError("display manifest is not bound to the frozen fixture")
        return _copy(manifest)

    def load_manifest(self, path: str | Path) -> dict[str, Any]:
        if not isinstance(path, (str, Path)):
            raise DisplaySceneBindingError("manifest path must be a string or Path")
        file_path = Path(path)
        try:
            if not file_path.is_file() or file_path.is_symlink():
                raise DisplaySceneBindingError("manifest path is not a regular file")
            with file_path.open("r", encoding="utf-8", newline="") as handle:
                value = json.load(handle, object_pairs_hook=_reject_duplicate_json_pairs)
        except DisplaySceneBindingError:
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise DisplaySceneBindingError("manifest path or JSON is invalid") from error
        return self.validate_manifest(value)

    def consume_contact(self, envelope: Any, current_step: Any, epoch: Any = None) -> dict[str, Any]:
        current_step = _nonneg_int(current_step, "current_step")
        if epoch is None:
            epoch = self.epoch
        else:
            epoch = _epoch(epoch)
        if type(envelope) is not dict:
            raise DisplaySceneBindingError("contact envelope must be a mapping")
        _reject_force_fields(envelope)
        if envelope.get("schema") != CONTACT_SCHEMA:
            raise DisplaySceneIdentityError("only wksim.contact.v1 can be consumed by the display binding")
        _reject_foreign_identity(envelope.get("scene_id"), envelope.get("scene_hash"))
        if set(envelope) != CONTACT_FIELDS:
            raise DisplaySceneBindingError("contact envelope field set is invalid")
        result = self.observer.validate_envelope(envelope, current_step, epoch=epoch)
        return _copy(result)

    def observe_frame(self, frame: Any, body_id: Any, point_enu_m: Any,
                      epoch: Any = None) -> dict[str, Any]:
        frame = _nonneg_int(frame, "frame")
        body_id = _identity(body_id, "body_id")
        observation = self.observer.observe_step(frame, body_id, point_enu_m, epoch=epoch)
        return self._frame_from_observation(frame, observation)

    def recover_frame(self, frame: Any, body_id: Any, point_enu_m: Any,
                      reason: str = "explicit_recovery", epoch: Any = None) -> dict[str, Any]:
        frame = _nonneg_int(frame, "frame")
        body_id = _identity(body_id, "body_id")
        if epoch is None:
            epoch = self.epoch
        else:
            epoch = _epoch(epoch)
        if epoch != self.epoch:
            raise DisplaySceneIdentityError("recovery epoch is not the bound display epoch")
        try:
            recovered = self.observer.recover(frame, body_id, point_enu_m, reason=reason)
        except ContactError as error:
            raise DisplaySceneBindingError(error.reason) from error
        return self._frame_from_observation(frame, recovered)

    def consume_frame(self, record: Any) -> dict[str, Any]:
        if type(record) is not dict or set(record) != FRAME_RECORD_FIELDS:
            raise DisplaySceneBindingError("frame record must contain exactly the display-frame fields")
        _reject_force_fields(record)
        if record["schema"] != FRAME_SCHEMA:
            raise DisplaySceneBindingError("frame schema mismatch")
        _reject_foreign_identity(record.get("scene_id"), record.get("scene_hash"))
        epoch = _epoch(record["epoch"])
        if epoch != self.epoch:
            raise DisplaySceneIdentityError("frame epoch is not the bound display epoch")
        frame = _nonneg_int(record["frame"], "frame")
        result = record["result"]
        envelope = record["envelope"]
        if result not in FRAME_RESULTS:
            raise DisplaySceneBindingError("frame result must be contact, no_contact, or frozen")
        self._assert_frame_payload(frame, result, envelope, epoch)
        if result == "contact":
            if self.observer.frozen:
                raise DisplaySceneBindingError("frozen binding cannot consume a live contact frame")
            consumed = self.consume_contact(envelope, frame, epoch=epoch)
            if consumed.get("status") != "ok":
                raise DisplaySceneBindingError(consumed.get("reason") or "contact_invalid")
        elif result == "no_contact":
            if self.observer.frozen:
                raise DisplaySceneBindingError("frozen binding cannot consume a live no_contact frame")
        elif not self.observer.frozen:
            raise DisplaySceneBindingError("frozen frame requires a prior observer freeze")
        elif frame != self.observer.freeze_step:
            raise DisplaySceneBindingError("frozen frame must equal the authority freeze step")
        return _copy(record)

    def validate_frame_evidence(self, evidence: Any) -> dict[str, Any]:
        if type(evidence) is not dict or set(evidence) != FRAME_EVIDENCE_FIELDS:
            raise DisplaySceneBindingError("frame evidence must contain exactly the evidence fields")
        if evidence["schema"] != FRAME_EVIDENCE_SCHEMA:
            raise DisplaySceneBindingError("frame evidence schema mismatch")
        _reject_foreign_identity(evidence.get("scene_id"), evidence.get("scene_hash"))
        evidence_epoch = _epoch(evidence["epoch"])
        if evidence_epoch != self.epoch:
            raise DisplaySceneIdentityError("frame evidence epoch is not the bound display epoch")
        if evidence["tick_ns"] != TICK_NS:
            raise DisplaySceneBindingError("frame evidence tick_ns must be 1000000")
        if (evidence["contact_schema"] != CONTACT_SCHEMA
                or evidence["display_manifest_schema"] != DISPLAY_MANIFEST_SCHEMA):
            raise DisplaySceneIdentityError("frame evidence schema identity mismatch")
        if evidence["display_modifies_physics"] is not False:
            raise DisplaySceneBindingError("display cannot modify physics")
        if evidence["ue_session"] is not False or evidence["ue_disconnect_reconnect"] is not False:
            raise DisplaySceneBindingError("this binding cannot claim a UE session")
        if evidence["acceptance"] is not False:
            raise DisplaySceneBindingError("this binding cannot claim #29 acceptance")
        if evidence["source_identity"] != BINDING_SOURCE_IDENTITY:
            raise DisplaySceneIdentityError("frame evidence source identity mismatch")
        events = evidence["events"]
        if type(events) is not list or len(events) != 2:
            raise DisplaySceneBindingError("frame evidence must be one freeze then one recover")
        freeze, recover = events
        if type(freeze) is not dict or set(freeze) != FREEZE_EVENT_FIELDS:
            raise DisplaySceneBindingError("freeze event field set is invalid")
        if type(recover) is not dict or set(recover) != RECOVER_EVENT_FIELDS:
            raise DisplaySceneBindingError("recover event field set is invalid")
        if freeze["event"] != "freeze" or recover["event"] != "recover":
            raise DisplaySceneBindingError("frame evidence events must be freeze then recover")
        freeze_frame = _nonneg_int(freeze["frame"], "freeze.frame")
        recover_frame = _nonneg_int(recover["frame"], "recover.frame")
        boundary = _nonneg_int(freeze["boundary_step"], "freeze.boundary_step")
        if freeze["reason"] not in FREEZE_REASONS:
            raise DisplaySceneBindingError("freeze reason is not a committed fail-closed reason")
        _identity(recover["reason"], "recover.reason")
        if recover_frame <= freeze_frame:
            raise DisplaySceneBindingError("recover frame must be later than freeze frame")
        if boundary > freeze_frame:
            raise DisplaySceneBindingError("freeze boundary_step cannot be later than freeze frame")
        return _copy(evidence)

    def binding_record(self) -> dict[str, Any]:
        return {
            "schema": BINDING_SCHEMA,
            "display_manifest_schema": DISPLAY_MANIFEST_SCHEMA,
            "contact_schema": CONTACT_SCHEMA,
            "frame_schema": FRAME_SCHEMA,
            "frame_evidence_schema": FRAME_EVIDENCE_SCHEMA,
            "scene_id": DISPLAY_SCENE_ID,
            "scene_hash": DISPLAY_SCENE_HASH,
            "epoch": self.epoch,
            "coordinate_frame": COORDINATE_FRAME,
            "unit": UNIT,
            "physics_authority": PHYSICS_AUTHORITY,
            "authority": AUTHORITY_TEXT,
            "visual_mirror": {"system": "UE", "binding_status": "not_bound"},
            "capabilities": {
                "contact_geometry": True,
                "forces": False,
                "impulses": False,
                "terrain_response": False,
                "ue_process_control": False,
            },
            "acceptance": False,
            "issue_29_open": True,
            "ue_session": False,
            "binding_source_identity": BINDING_SOURCE_IDENTITY,
            "observer_source_identity": OBSERVER_SOURCE_IDENTITY,
            "profile_source_identity": PROFILE_SOURCE_IDENTITY,
            "planner_binding_source_identity": PLANNER_BINDING_SOURCE_IDENTITY,
            "terrain_source_identity": TERRAIN_SOURCE_IDENTITY,
            "rejected_display_identities": [
                {"scene_id": PROFILE_ID, "scene_hash": EXPECTED_SCENE_HASH},
                {"scene_id": PROBE_SCENE_ID, "scene_hash": PROBE_SCENE_HASH},
            ],
        }

    def identity_table(self) -> dict[str, Any]:
        terrain = TerrainFeedback(self.epoch)
        terrain_manifest = terrain.manifest()
        if (terrain_manifest["schema"] != TERRAIN_MANIFEST_SCHEMA
                or terrain_manifest["scene_hash"] != DISPLAY_SCENE_HASH
                or terrain_manifest["scene_id"] != DISPLAY_SCENE_ID):
            raise DisplaySceneIdentityError("terrain feedback is not bound to the display fixture")
        planner = EGO_SINGLE_BOX_BINDING.manifest
        return {
            "display_fixture": {
                "scene_id": DISPLAY_SCENE_ID,
                "scene_hash": DISPLAY_SCENE_HASH,
                "role": "display_manifest_and_contact_observer",
                "accepted_as_display": True,
            },
            "generated_model_probe": {
                "scene_id": PROBE_SCENE_ID,
                "scene_hash": PROBE_SCENE_HASH,
                "role": "real_terrain_probe",
                "accepted_as_display": False,
            },
            "planner_ego": {
                "scene_id": PROFILE_ID,
                "scene_hash": EXPECTED_SCENE_HASH,
                "profile_hash": EXPECTED_PROFILE_HASH,
                "visual_mirror": _copy(planner["visual_mirror"]),
                "accepted_as_display": False,
            },
            "terrain_feedback": {
                "schema": TERRAIN_MANIFEST_SCHEMA,
                "scene_id": terrain_manifest["scene_id"],
                "scene_hash": terrain_manifest["scene_hash"],
                "stacks": dict(STACK_BODIES),
            },
        }

    def _frame_from_observation(self, frame: int, observation: dict[str, Any]) -> dict[str, Any]:
        status = observation.get("status")
        result = observation.get("result")
        if status in ("freeze", "frozen") or observation.get("freeze") or result == "frozen":
            if observation.get("freeze_step") != frame:
                raise DisplaySceneBindingError("frozen observation is not at the authority freeze step")
            frame_result = "frozen"
            envelope = None
        elif result in ("contact", "no_contact"):
            frame_result = result
            envelope = observation.get("envelope")
            if frame_result == "no_contact" and envelope is not None:
                raise DisplaySceneBindingError("no_contact observation must not invent an envelope")
        else:
            raise DisplaySceneBindingError("observation cannot be bound to a display frame")
        record = {
            "schema": FRAME_SCHEMA,
            "scene_id": DISPLAY_SCENE_ID,
            "scene_hash": DISPLAY_SCENE_HASH,
            "epoch": self.epoch,
            "frame": frame,
            "result": frame_result,
            "envelope": _copy(envelope) if envelope is not None else None,
        }
        self._assert_frame_payload(frame, frame_result, record["envelope"], self.epoch)
        return _copy(record)

    def _assert_frame_payload(self, frame: int, result: str, envelope: Any, epoch: str) -> None:
        if result == "contact":
            if type(envelope) is not dict:
                raise DisplaySceneBindingError("contact frame must carry a contact envelope")
            if envelope.get("step") != frame or envelope.get("epoch") != epoch:
                raise DisplaySceneBindingError("contact envelope step or epoch does not match the frame")
            if envelope.get("sim_time_ns") != frame * TICK_NS:
                raise DisplaySceneBindingError("contact envelope time is not bound to the frame")
        elif envelope is not None:
            raise DisplaySceneBindingError(f"{result} frame must carry a null envelope")
