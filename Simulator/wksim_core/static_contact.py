"""Approved static plane/box contact queries for the authoritative WSL physics side.

Implements the #9 environment contract recorded in
docs/plan/9-abi-environment-accepted.md: a z=0 plane and one axis-aligned
box in ENU/metres with explicit origin. Every result is a
``wksim.contact.v1`` envelope valid for exactly the queried authority step
(1 ms tick); expired required feedback is a typed error, never silently
reused. This module is a pure query seam: no I/O, no wall clock, no
threads, no UE dependency. Wiring it into the model worker requires a
separately owned edit ticket.
"""

import hashlib
import json
import math

SCHEMA = "wksim.contact.v1"
CONFIG_SCHEMA = "wksim.static-scene.v1"
TICK_NS = 1_000_000
ERROR_CODES = (
    "accepted", "scene_not_found", "scene_hash_mismatch", "invalid_geometry",
    "foreign_epoch", "stale_feedback", "future_feedback", "unsupported_query",
    "contact_invalid",
)
_FACE_ORDER = ("x-", "x+", "y-", "y+", "z-", "z+")


class ContactError(ValueError):
    def __init__(self, reason):
        if reason not in ERROR_CODES:
            raise ValueError("unknown contact error reason")
        super().__init__(reason)
        self.reason = reason


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContactError("invalid_geometry")
    return float(value)


def _vector(value, name):
    if (not isinstance(value, tuple) and not isinstance(value, list)) or len(value) != 3:
        raise ContactError("invalid_geometry")
    return tuple(_finite(v, name) for v in value)


def _step(value, name="step"):
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ContactError("contact_invalid")
    return value


def _epoch(value):
    if not isinstance(value, str) or len(value) != 32 or value != value.lower() \
            or any(c not in "0123456789abcdef" for c in value):
        raise ContactError("contact_invalid")
    return value


def _canonical_geometry(geometry):
    return json.dumps(geometry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class StaticScene:
    """Frozen static scene: one z=0 plane and one axis-aligned box."""

    def __init__(self, config):
        if not isinstance(config, dict):
            raise ContactError("invalid_geometry")
        required = {"schema", "scene_id", "coordinate_frame", "unit", "origin_enu_m",
                    "plane", "box", "scene_sha256"}
        if set(config) != required:
            raise ContactError("invalid_geometry")
        if config["schema"] != CONFIG_SCHEMA or config["coordinate_frame"] != "ENU" \
                or config["unit"] != "metre":
            raise ContactError("invalid_geometry")
        if not isinstance(config["scene_id"], str) or not config["scene_id"]:
            raise ContactError("invalid_geometry")
        origin = _vector(config["origin_enu_m"], "origin")
        plane = config["plane"]
        box = config["box"]
        if not isinstance(plane, dict) or set(plane) != {"geometry_id", "z_m"}:
            raise ContactError("invalid_geometry")
        if not isinstance(box, dict) or set(box) != {"geometry_id", "center_enu_m", "size_m"}:
            raise ContactError("invalid_geometry")
        plane_z = _finite(plane["z_m"], "plane_z")
        center = _vector(box["center_enu_m"], "box_center")
        size = _vector(box["size_m"], "box_size")
        if min(size) <= 0:
            raise ContactError("invalid_geometry")
        for item in (plane["geometry_id"], box["geometry_id"]):
            if not isinstance(item, str) or not item:
                raise ContactError("invalid_geometry")
        geometry = {"origin_enu_m": origin, "plane": {"geometry_id": plane["geometry_id"], "z_m": plane_z},
                    "box": {"geometry_id": box["geometry_id"], "center_enu_m": center, "size_m": size}}
        expected = hashlib.sha256(_canonical_geometry(geometry).encode("utf-8")).hexdigest()
        if config["scene_sha256"] != expected:
            raise ContactError("scene_hash_mismatch")
        self.scene_id = config["scene_id"]
        self.origin = origin
        self.plane_id = plane["geometry_id"]
        self.plane_z = plane_z
        self.box_id = box["geometry_id"]
        self.box_center = center
        self.box_size = size
        self.scene_sha256 = expected

    def _envelope(self, epoch, step, body_id, geometry_id, point, normal, penetration):
        return {
            "schema": SCHEMA,
            "scene_id": self.scene_id,
            "scene_hash": self.scene_sha256,
            "epoch": epoch,
            "step": step,
            "sim_time_ns": step * TICK_NS,
            "valid_from_step": step,
            "valid_until_step": step,
            "body_id": body_id,
            "geometry_id": geometry_id,
            "contact_point_enu_m": list(point),
            "normal_enu": list(normal),
            "penetration_m": penetration,
            "source_identity": "Simulator/wksim_core/static_contact.py",
        }

    def query(self, epoch, step, body_id, point_enu_m):
        """Query contact at an ENU point. Returns a result record; typed
        ContactError on foreign epoch or invalid input. A no-contact result
        is a valid observation, never an unavailable one."""
        epoch = _epoch(epoch)
        step = _step(step)
        if not isinstance(body_id, str) or not body_id:
            raise ContactError("contact_invalid")
        px, py, pz = (a - b for a, b in zip(_vector(point_enu_m, "point"), self.origin))
        cx, cy, cz = self.box_center
        sx, sy, sz = (v / 2.0 for v in self.box_size)
        dx, dy, dz = px - cx, py - cy, pz - cz
        if abs(dx) <= sx and abs(dy) <= sy and abs(dz) <= sz:
            candidates = (
                ("x-", sx + dx, (cx - sx, py, pz), (-1.0, 0.0, 0.0)),
                ("x+", sx - dx, (cx + sx, py, pz), (1.0, 0.0, 0.0)),
                ("y-", sy + dy, (px, cy - sy, pz), (0.0, -1.0, 0.0)),
                ("y+", sy - dy, (px, cy + sy, pz), (0.0, 1.0, 0.0)),
                ("z-", sz + dz, (px, py, cz - sz), (0.0, 0.0, -1.0)),
                ("z+", sz - dz, (px, py, cz + sz), (0.0, 0.0, 1.0)),
            )
            best = min(candidates, key=lambda c: (c[1], _FACE_ORDER.index(c[0])))
            _, depth, point, normal = best
            return {"result": "contact", "observation": "valid",
                    "envelope": self._envelope(epoch, step, body_id, self.box_id, point, normal, depth)}
        if pz <= self.plane_z:
            depth = self.plane_z - pz
            point = (px, py, self.plane_z)
            return {"result": "contact", "observation": "valid",
                    "envelope": self._envelope(epoch, step, body_id, self.plane_id,
                                               point, (0.0, 0.0, 1.0), depth)}
        return {"result": "no_contact", "observation": "valid", "envelope": None,
                "scene_id": self.scene_id, "scene_hash": self.scene_sha256,
                "epoch": epoch, "step": step}

    def require_fresh(self, envelope, current_step, run_epoch):
        """Required-feedback freshness per the approved contract: a result is
        valid only on its declared authority step and only inside the bound
        run epoch. Expired or foreign feedback is a typed error so the joint
        scene can freeze and require explicit recovery; old envelopes are
        never silently reused."""
        current_step = _step(current_step, "current_step")
        run_epoch = _epoch(run_epoch)
        if not isinstance(envelope, dict) or envelope.get("schema") != SCHEMA:
            raise ContactError("contact_invalid")
        if envelope.get("epoch") is None:
            raise ContactError("contact_invalid")
        _epoch(envelope["epoch"])
        if envelope["epoch"] != run_epoch:
            raise ContactError("foreign_epoch")
        if envelope.get("scene_id") != self.scene_id or envelope.get("scene_hash") != self.scene_sha256:
            raise ContactError("scene_hash_mismatch")
        from_step = _step(envelope.get("valid_from_step"), "valid_from_step")
        until_step = _step(envelope.get("valid_until_step"), "valid_until_step")
        if until_step < from_step:
            raise ContactError("contact_invalid")
        if current_step < from_step:
            raise ContactError("future_feedback")
        if current_step > until_step:
            raise ContactError("stale_feedback")
        return True


def load_scene(path):
    with open(path, "r", encoding="utf-8") as handle:
        return StaticScene(json.load(handle))
