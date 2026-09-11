"""Approved static contact runtime observer and stale-feedback freeze adapter.

Implements the #29 runtime observation boundary per the approved environment
contract in docs/plan/9-abi-environment-accepted.md:
1. Loads and binds the frozen static scene with verified SHA256.
2. Emits wksim.contact.v1 envelopes strictly bound to the authority epoch/step.
3. Explicitly rejects stale, future, or foreign-epoch feedback and triggers
   a scene freeze signal without silently reusing old data.
4. Pure geometric observation: does NOT compute or write forces, impulses,
   damping, or penetration corrections.
"""

from pathlib import Path
import math

from Simulator.wksim_core.static_contact import (
    TICK_NS,
    ContactError,
    StaticScene,
    _epoch,
    _step,
    _vector,
    load_scene,
)

FROZEN_SCENE_SHA256 = "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514"
DEFAULT_SCENE_PATH = Path(__file__).resolve().parent / "static-scene-v1.json"
CONTACT_FIELDS = {
    "schema", "scene_id", "scene_hash", "epoch", "step", "sim_time_ns",
    "valid_from_step", "valid_until_step", "body_id", "geometry_id",
    "contact_point_enu_m", "normal_enu", "penetration_m", "source_identity",
}


class ContactObserver:
    """Runtime observer for static geometry contact and feedback lifecycle."""

    def __init__(self, scene_source=DEFAULT_SCENE_PATH, run_epoch=None,
                 expected_sha256=FROZEN_SCENE_SHA256):
        if run_epoch is None:
            raise ContactError("contact_invalid")
        self.epoch = _epoch(run_epoch)
        self.expected_sha256 = expected_sha256

        if isinstance(scene_source, (str, Path)):
            path = Path(scene_source)
            if not path.is_file():
                raise ContactError("scene_not_found")
            self.scene = load_scene(path)
        elif isinstance(scene_source, dict):
            self.scene = StaticScene(scene_source)
        else:
            raise ContactError("invalid_geometry")

        if self.scene.scene_sha256 != self.expected_sha256:
            raise ContactError("scene_hash_mismatch")

        self.frozen = False
        self.freeze_reason = None
        self.freeze_step = None
        self.last_step = None
        self.last_envelope = None
        self.events = []

    def _trigger_freeze(self, reason, step, **extra):
        self.frozen = True
        self.freeze_reason = reason
        self.freeze_step = step
        event = {"event": "freeze", "step": step, "reason": reason, **extra}
        self.events.append(event)
        return {
            "status": "freeze",
            "freeze": True,
            "reason": reason,
            "freeze_step": step,
            "step": step,
            "envelope": None,
            "result": "frozen",
            "observation": "frozen",
        }

    def _validate_contact_envelope(self, envelope, current_step, epoch):
        """Validate the complete contact observation, not only its age window."""
        if not isinstance(envelope, dict) or set(envelope) != CONTACT_FIELDS:
            raise ContactError("contact_invalid")
        self.scene.require_fresh(envelope, current_step, epoch)
        envelope_step = _step(envelope.get("step"))
        if (envelope_step != current_step
                or envelope.get("valid_from_step") != envelope_step
                or envelope.get("valid_until_step") != envelope_step
                or type(envelope.get("sim_time_ns")) is not int
                or envelope["sim_time_ns"] != envelope_step * TICK_NS):
            raise ContactError("contact_invalid")
        if (not isinstance(envelope.get("body_id"), str) or not envelope["body_id"]
                or envelope.get("geometry_id") not in (self.scene.plane_id, self.scene.box_id)
                or envelope.get("source_identity") != "Simulator/wksim_core/static_contact.py"):
            raise ContactError("contact_invalid")
        _vector(envelope.get("contact_point_enu_m"), "contact_point")
        normal = _vector(envelope.get("normal_enu"), "normal")
        penetration = envelope.get("penetration_m")
        if (isinstance(penetration, bool) or not isinstance(penetration, (int, float))
                or not math.isfinite(penetration) or penetration < 0
                or abs(sum(value * value for value in normal) - 1.0) > 1e-12):
            raise ContactError("contact_invalid")

    def observe_step(self, step, body_id, point_enu_m, epoch=None):
        """Query contact observation for a body at an authority step.
        Returns a valid observation or a freeze signal on error/stale condition.
        """
        step = _step(step)
        if epoch is None:
            epoch = self.epoch

        if self.frozen:
            return {
                "status": "frozen",
                "freeze": True,
                "reason": self.freeze_reason,
                "freeze_step": self.freeze_step,
                "step": step,
                "epoch": self.epoch,
                "body_id": body_id,
                "result": "frozen",
                "observation": "frozen",
                "envelope": None,
            }

        try:
            epoch = _epoch(epoch)
        except ContactError as exc:
            return self._trigger_freeze(exc.reason, step, body_id=body_id)
        if epoch != self.epoch:
            return self._trigger_freeze("foreign_epoch", step, body_id=body_id)

        if self.last_step is not None and step <= self.last_step:
            return self._trigger_freeze("stale_feedback", step, body_id=body_id)

        try:
            query_res = self.scene.query(epoch, step, body_id, point_enu_m)
            if query_res["result"] == "contact":
                envelope = query_res["envelope"]
                self._validate_contact_envelope(envelope, step, epoch)
                self.last_envelope = envelope
                self.last_step = step
                return {
                    "status": "ok",
                    "freeze": False,
                    "result": "contact",
                    "observation": "valid",
                    "envelope": envelope,
                    "step": step,
                    "epoch": epoch,
                    "body_id": body_id,
                }
            else:
                self.last_envelope = None
                self.last_step = step
                return {
                    "status": "ok",
                    "freeze": False,
                    "result": "no_contact",
                    "observation": "valid",
                    "envelope": None,
                    "step": step,
                    "epoch": epoch,
                    "body_id": body_id,
                    "scene_id": self.scene.scene_id,
                    "scene_hash": self.scene.scene_sha256,
                }
        except ContactError as exc:
            return self._trigger_freeze(exc.reason, step, body_id=body_id)

    def validate_envelope(self, envelope, current_step, epoch=None):
        """Validate an external contact envelope against authority freshness rules.
        Rejects stale, future, foreign-epoch, or hash-mismatched envelopes with
        a freeze signal.
        """
        current_step = _step(current_step)
        if epoch is None:
            epoch = self.epoch

        if self.frozen:
            return {
                "status": "frozen",
                "freeze": True,
                "reason": self.freeze_reason,
                "freeze_step": self.freeze_step,
                "step": current_step,
            }

        try:
            epoch = _epoch(epoch)
            self._validate_contact_envelope(envelope, current_step, epoch)
            if self.last_step is not None and current_step <= self.last_step:
                raise ContactError("stale_feedback")
            self.last_step = current_step
            self.last_envelope = envelope
            return {
                "status": "ok",
                "freeze": False,
                "valid": True,
                "step": current_step,
                "epoch": epoch,
            }
        except ContactError as exc:
            return self._trigger_freeze(exc.reason, current_step)

    def recover(self, current_step, body_id, point_enu_m, reason="explicit_recovery"):
        """Recover by re-querying the bound authority scene at a forward step."""
        current_step = _step(current_step)
        if not self.frozen or not isinstance(reason, str) or not reason:
            raise ContactError("contact_invalid")
        if ((self.last_step is not None and current_step <= self.last_step)
                or (self.freeze_step is not None and current_step < self.freeze_step)):
            raise ContactError("stale_feedback")
        evidence = self.scene.query(self.epoch, current_step, body_id, point_enu_m)
        envelope = evidence["envelope"]
        if envelope is not None:
            self._validate_contact_envelope(envelope, current_step, self.epoch)
        prev_reason = self.freeze_reason
        self.frozen = False
        self.freeze_reason = None
        self.freeze_step = None
        self.last_step = current_step
        self.last_envelope = envelope
        event = {"event": "recover", "step": current_step, "reason": reason,
                 "previous_reason": prev_reason, "result": evidence["result"]}
        self.events.append(event)
        return {
            "status": "recovered",
            "freeze": False,
            "step": current_step,
            "reason": reason,
            "previous_reason": prev_reason,
            "result": evidence["result"],
            "envelope": envelope,
        }

    def get_display_manifest(self):
        """Return the display-side scene binding manifest bound by SHA256."""
        return {
            "schema": "wksim.display-manifest.v1",
            "scene_id": self.scene.scene_id,
            "scene_hash": self.scene.scene_sha256,
            "coordinate_frame": "ENU",
            "unit": "metre",
            "origin_enu_m": list(self.scene.origin),
            "plane": {"geometry_id": self.scene.plane_id, "z_m": self.scene.plane_z},
            "box": {
                "geometry_id": self.scene.box_id,
                "center_enu_m": list(self.scene.box_center),
                "size_m": list(self.scene.box_size),
            },
        }
