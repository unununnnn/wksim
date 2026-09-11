"""Pure offline binding for the frozen planner scene geometry.

The planner profile is the only geometry source in this module.  The AABB and
the ordered point cloud are read from :mod:`Simulator.wksim_planning.scene_profile`
at construction time; no runtime, UE, ROS, SITL, terrain, or force interface is
involved.  The resulting manifest is an identity contract for a later runtime
integration, not evidence that such an integration already exists.

The existing ``static-plane-box-v1`` scene remains a separate contract.  This
module rejects that scene id and hash rather than silently treating its
geometry as the planner obstacle.

The mutation guards in this module provide consistency and misuse protection
for the ordinary in-process assignment, deletion, subclassing, and
post-capture monkeypatch paths covered by the contract.  They are not a
security boundary against a caller that already has arbitrary Python
reflection or code-execution authority in this process.  Runtime integrity
must therefore be established by the surrounding evidence/release checks
that pin the profile and binding source hashes, together with a controlled
process boundary.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from numbers import Real
from types import MappingProxyType
from typing import Any, Mapping

from Simulator.wksim_planning.scene_profile import (
    AABB,
    EGO_SINGLE_BOX_V1,
    PROFILE_ID,
    SceneProfile,
)


_SCENE_PROFILE_TYPE = SceneProfile
_PROFILE_AABB_TYPE = AABB
_PROFILE_FIELD_NAMES = frozenset(SceneProfile.__dataclass_fields__)
_ORIGINAL_PROFILE_HASH_DESCRIPTOR = SceneProfile.__dict__["profile_hash"]
_ORIGINAL_POINT_CLOUD_METHOD = SceneProfile.__dict__["point_cloud"]


MANIFEST_SCHEMA = "wksim.planner-scene-binding.v1"
CONTACT_SCHEMA = "wksim.planner-contact.v1"
QUERY_VERSION = "planner-aabb-point-contact-v1"
TICK_NS = 1_000_000

# These are stable source identities, not filesystem paths supplied by a
# caller.  Forward slashes keep the canonical bytes identical on Windows and
# WSL.
PROFILE_SOURCE_IDENTITY = "Simulator/wksim_planning/scene_profile.py"
BINDING_SOURCE_IDENTITY = "Simulator/wksim_runtime/planner_scene_binding.py"

# The old #29 fixture is intentionally preserved and is never an alias for
# this planner geometry.
LEGACY_SCENE_ID = "static-plane-box-v1"
LEGACY_SCENE_HASH = "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514"

GEOMETRY_ID = f"{PROFILE_ID}:obstacle"
PHYSICS_AUTHORITY = "WSL"

# These identities are part of the committed binding contract.  The binding
# runtime captures its own copies during module initialization; these public
# names remain compatibility constants and are not consulted by construction.
EXPECTED_PROFILE_HASH = "49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7"
EXPECTED_COLLISION_HASH = "08b88651775ae2181e5082f124d16c6a434597703fdf2ff08bfc0bd59205c07c"
EXPECTED_VOXEL_HASH = "3602530733cf10fd0960212dc413b157e56e662d330b4b314a71f4c21abae638"
EXPECTED_POINT_CLOUD_HASH = "d14d6311a45e3e7d1c323afdb67205510c5370eed2959d23bff70cd1ac04f2ad"
EXPECTED_SCENE_HASH = "40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba"


class PlannerSceneBindingError(ValueError):
    """Raised when a planner scene identity or query input is unsafe."""


class PlannerSceneIdentityError(PlannerSceneBindingError):
    """Raised when a manifest or query names a different scene."""


def _canonical_bytes(value: Any) -> bytes:
    """Encode JSON with the repository's cross-platform canonical settings."""
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PlannerSceneBindingError("value is not canonically serializable") from error


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise PlannerSceneBindingError(f"{name} must be a finite real number")
    return float(value)


def _vector(value: Any, name: str) -> tuple[float, float, float]:
    if type(value) not in (tuple, list) or len(value) != 3:
        raise PlannerSceneBindingError(f"{name} must be a three-element sequence")
    return tuple(_finite(item, f"{name}[{index}]") for index, item in enumerate(value))


def _step(value: Any, name: str = "step") -> int:
    if type(value) is not int or value < 0:
        raise PlannerSceneBindingError(f"{name} must be a non-negative integer")
    return value


def _epoch(value: Any) -> str:
    if (not isinstance(value, str) or len(value) != 32 or value != value.lower()
            or any(character not in "0123456789abcdef" for character in value)):
        raise PlannerSceneBindingError("epoch must be a lowercase 32-character hexadecimal id")
    return value


def _identity(value: Any, name: str) -> str:
    if (not isinstance(value, str) or not value or value.strip() != value
            or "\x00" in value):
        raise PlannerSceneBindingError(f"{name} must be a non-empty identity string")
    return value


def _hash(value: Any, name: str) -> str:
    if (not isinstance(value, str) or len(value) != 64 or value != value.lower()
            or any(character not in "0123456789abcdef" for character in value)):
        raise PlannerSceneBindingError(f"{name} must be a lowercase SHA-256 hexadecimal string")
    return value


@dataclass(frozen=True)
class _ProfileSnapshot:
    """Primitive, construction-time profile data used by the binding."""

    profile_id: str
    version: int
    frame: str
    coordinate_system: str
    length_unit: str
    time_unit: str
    angle_unit: str
    origin: tuple[float, float, float]
    size: tuple[float, float, float]
    voxel_resolution: float
    voxel_order: str
    voxel_center_convention: str
    ground_z: float
    ceiling_z: float
    obstacle_minimum: tuple[float, float, float]
    obstacle_maximum: tuple[float, float, float]
    vehicle_radius: float
    required_clearance: float
    obstacle_index_bounds: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    voxel_indices: tuple[tuple[int, int, int], ...]
    point_cloud: tuple[tuple[float, float, float], ...]


def _read_field(value: Any, name: str) -> Any:
    """Read an instance field without invoking a profile property."""
    try:
        return object.__getattribute__(value, name)
    except (AttributeError, TypeError) as error:
        raise PlannerSceneIdentityError("only the committed ego scene profile is accepted") from error


def _snapshot_profile(profile: Any) -> _ProfileSnapshot:
    """Rebuild canonical geometry from exact dataclass fields only."""
    if type(profile) is not _SCENE_PROFILE_TYPE:
        raise PlannerSceneIdentityError("only the committed ego scene profile is accepted")
    try:
        if (_SCENE_PROFILE_TYPE.__dict__.get("profile_hash")
                is not _ORIGINAL_PROFILE_HASH_DESCRIPTOR
                or _SCENE_PROFILE_TYPE.__dict__.get("point_cloud")
                is not _ORIGINAL_POINT_CLOUD_METHOD):
            raise PlannerSceneIdentityError("only the committed ego scene profile is accepted")
        # An exact SceneProfile instance can still be tampered with through
        # object.__setattr__.  Reject injected profile_hash/point_cloud (or any
        # other override) before reading the canonical dataclass fields.
        instance_fields = object.__getattribute__(profile, "__dict__")
        if type(instance_fields) is not dict or set(instance_fields) != _PROFILE_FIELD_NAMES:
            raise PlannerSceneIdentityError("only the committed ego scene profile is accepted")
        obstacle = _read_field(profile, "obstacle")
        if type(obstacle) is not _PROFILE_AABB_TYPE:
            raise PlannerSceneIdentityError("only the committed ego scene profile is accepted")
        minimum = _vector(_read_field(obstacle, "minimum"), "obstacle.minimum")
        maximum = _vector(_read_field(obstacle, "maximum"), "obstacle.maximum")
        snapshot = {
            "profile_id": _read_field(profile, "profile_id"),
            "version": _read_field(profile, "version"),
            "frame": _read_field(profile, "frame"),
            "coordinate_system": _read_field(profile, "coordinate_system"),
            "length_unit": _read_field(profile, "length_unit"),
            "time_unit": _read_field(profile, "time_unit"),
            "angle_unit": _read_field(profile, "angle_unit"),
            "origin": _vector(_read_field(profile, "origin"), "origin"),
            "size": _vector(_read_field(profile, "size"), "size"),
            "voxel_resolution": _finite(_read_field(profile, "voxel_resolution"),
                                         "voxel_resolution"),
            "voxel_order": _read_field(profile, "voxel_order"),
            "voxel_center_convention": _read_field(profile, "voxel_center_convention"),
            "ground_z": _finite(_read_field(profile, "ground_z"), "ground_z"),
            "ceiling_z": _finite(_read_field(profile, "ceiling_z"), "ceiling_z"),
            "obstacle_minimum": minimum,
            "obstacle_maximum": maximum,
            "vehicle_radius": _finite(_read_field(profile, "vehicle_radius"),
                                      "vehicle_radius"),
            "required_clearance": _finite(_read_field(profile, "required_clearance"),
                                           "required_clearance"),
        }
        if (type(snapshot["profile_id"]) is not str
                or type(snapshot["version"]) is not int
                or any(type(snapshot[name]) is not str for name in (
                    "frame", "coordinate_system", "length_unit", "time_unit",
                    "angle_unit", "voxel_order", "voxel_center_convention"))):
            raise PlannerSceneIdentityError("only the committed ego scene profile is accepted")
        if any(lo >= hi for lo, hi in zip(minimum, maximum)):
            raise PlannerSceneIdentityError("only the committed ego scene profile is accepted")
        bounds: list[tuple[int, int]] = []
        for map_origin, lo, hi in zip(snapshot["origin"], minimum, maximum):
            low_float = (lo - map_origin) / snapshot["voxel_resolution"]
            count_float = (hi - lo) / snapshot["voxel_resolution"]
            low = round(low_float)
            count = round(count_float)
            if (not math.isclose(low_float, low, rel_tol=0.0, abs_tol=1e-9)
                    or not math.isclose(count_float, count, rel_tol=0.0, abs_tol=1e-9)
                    or count <= 0):
                raise PlannerSceneIdentityError("only the committed ego scene profile is accepted")
            bounds.append((int(low), int(low + count - 1)))
        index_bounds = tuple(bounds)
        indices = tuple((x, y, z)
                        for x in range(index_bounds[0][0], index_bounds[0][1] + 1)
                        for y in range(index_bounds[1][0], index_bounds[1][1] + 1)
                        for z in range(index_bounds[2][0], index_bounds[2][1] + 1))
        point_cloud = tuple(
            tuple(round(origin + (index + 0.5) * snapshot["voxel_resolution"], 12)
                  for origin, index in zip(snapshot["origin"], index_tuple))
            for index_tuple in indices
        )
        return _ProfileSnapshot(
            **snapshot,
            obstacle_index_bounds=index_bounds,
            voxel_indices=indices,
            point_cloud=point_cloud,
        )
    except PlannerSceneBindingError:
        raise
    except (ArithmeticError, KeyError, TypeError, ValueError) as error:
        raise PlannerSceneIdentityError("only the committed ego scene profile is accepted") from error


def _profile_payload(profile: _ProfileSnapshot) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "version": profile.version,
        "frame": profile.frame,
        "coordinate_system": profile.coordinate_system,
        "units": {
            "length": profile.length_unit,
            "time": profile.time_unit,
            "angle": profile.angle_unit,
        },
        "origin": list(profile.origin),
        "size": list(profile.size),
        "voxel_resolution": profile.voxel_resolution,
        "voxel_order": profile.voxel_order,
        "voxel_center_convention": profile.voxel_center_convention,
        "ground_z": profile.ground_z,
        "ceiling_z": profile.ceiling_z,
        "obstacle": {
            "min": list(profile.obstacle_minimum),
            "max": list(profile.obstacle_maximum),
        },
        "vehicle_radius": profile.vehicle_radius,
        "required_clearance": profile.required_clearance,
    }


def _rebuild_profile(profile: _ProfileSnapshot) -> SceneProfile:
    """Recreate a clean profile object without retaining caller-owned state."""
    return _SCENE_PROFILE_TYPE(
        profile_id=profile.profile_id,
        version=profile.version,
        frame=profile.frame,
        coordinate_system=profile.coordinate_system,
        length_unit=profile.length_unit,
        time_unit=profile.time_unit,
        angle_unit=profile.angle_unit,
        origin=profile.origin,
        size=profile.size,
        voxel_resolution=profile.voxel_resolution,
        voxel_order=profile.voxel_order,
        voxel_center_convention=profile.voxel_center_convention,
        ground_z=profile.ground_z,
        ceiling_z=profile.ceiling_z,
        obstacle=_PROFILE_AABB_TYPE(profile.obstacle_minimum, profile.obstacle_maximum),
        vehicle_radius=profile.vehicle_radius,
        required_clearance=profile.required_clearance,
    )


def _point_cloud_hash(profile: _ProfileSnapshot) -> str:
    """Hash the ordered centre coordinates derived from the frozen grid."""
    return _sha256({
        "profile_id": profile.profile_id,
        "voxel_order": profile.voxel_order,
        "center_convention": profile.voxel_center_convention,
        "points_enu_m": [list(point) for point in profile.point_cloud],
    })


def _manifest_payload(profile: _ProfileSnapshot, point_cloud_hash: str,
                      *, manifest_schema: str, query_version: str,
                      geometry_id: str, physics_authority: str,
                      profile_source_identity: str,
                      binding_source_identity: str,
                      profile_hash: str, collision_hash: str,
                      voxel_hash: str) -> dict[str, Any]:
    """Build the hash-free manifest payload from the frozen profile snapshot."""
    return {
        "schema": manifest_schema,
        "scene_id": profile.profile_id,
        "scene_version": profile.version,
        "query_version": query_version,
        "frame": profile.frame,
        "coordinate_frame": profile.coordinate_system,
        "units": {
            "length": profile.length_unit,
            "time": profile.time_unit,
            "angle": profile.angle_unit,
        },
        "origin_enu_m": list(profile.origin),
        "map_size_m": list(profile.size),
        "ground_z_m": profile.ground_z,
        "ceiling_z_m": profile.ceiling_z,
        "profile_hash": profile_hash,
        "collision_hash": collision_hash,
        "voxel_hash": voxel_hash,
        "point_cloud_hash": point_cloud_hash,
        "geometry": {
            "geometry_id": geometry_id,
            "kind": "aabb",
            "minimum_enu_m": list(profile.obstacle_minimum),
            "maximum_enu_m": list(profile.obstacle_maximum),
        },
        "point_cloud": {
            "count": len(profile.voxel_indices),
            "voxel_resolution_m": profile.voxel_resolution,
            "voxel_order": profile.voxel_order,
            "center_convention": profile.voxel_center_convention,
            "index_bounds": [list(bounds) for bounds in profile.obstacle_index_bounds],
        },
        "physics_authority": physics_authority,
        "capabilities": {
            "contact_geometry": True,
            "forces": False,
            "impulses": False,
            "terrain_response": False,
        },
        "visual_mirror": {"system": "UE", "binding_status": "not_bound"},
        "geometry_source_identity": profile_source_identity,
        "binding_source_identity": binding_source_identity,
    }


def _fixed_identities() -> dict[str, str]:
    """Return literals for the committed binding identity and its boundaries."""
    return {
        "manifest_schema": "wksim.planner-scene-binding.v1",
        "contact_schema": "wksim.planner-contact.v1",
        "query_version": "planner-aabb-point-contact-v1",
        "tick_ns": "1000000",
        "profile_source_identity": "Simulator/wksim_planning/scene_profile.py",
        "binding_source_identity": "Simulator/wksim_runtime/planner_scene_binding.py",
        "legacy_scene_id": "static-plane-box-v1",
        "legacy_scene_hash": "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514",
        "physics_authority": "WSL",
        "profile_hash": "49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7",
        "collision_hash": "08b88651775ae2181e5082f124d16c6a434597703fdf2ff08bfc0bd59205c07c",
        "voxel_hash": "3602530733cf10fd0960212dc413b157e56e662d330b4b314a71f4c21abae638",
        "point_cloud_hash": "d14d6311a45e3e7d1c323afdb67205510c5370eed2959d23bff70cd1ac04f2ad",
        "scene_hash": "40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba",
        "profile_id": "ego-single-box-v1",
        "geometry_id": "ego-single-box-v1:obstacle",
    }


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate keys instead of accepting json.load's last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlannerSceneBindingError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _path_is_link(path: Path) -> bool:
    """Treat symlinks and Windows junctions as unsafe aliases."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction()) if is_junction is not None else False
    except OSError as error:
        raise PlannerSceneBindingError("manifest path cannot be inspected") from error


def _safe_manifest_path(path: str | Path) -> Path:
    if not isinstance(path, (str, Path)):
        raise PlannerSceneBindingError("manifest path must be a string or Path")
    path_value = Path(path)
    if "\x00" in str(path_value):
        raise PlannerSceneBindingError("manifest path contains a NUL byte")
    try:
        absolute = Path(os.path.abspath(os.fspath(path_value)))
        resolved = path_value.resolve(strict=True)
        if os.path.normcase(os.fspath(absolute)) != os.path.normcase(os.fspath(resolved)):
            raise PlannerSceneBindingError("manifest path must not resolve through an alias")
        cursor = absolute
        while True:
            if _path_is_link(cursor):
                raise PlannerSceneBindingError("manifest file and parents must not be symlinks")
            parent = cursor.parent
            if parent == cursor:
                break
            cursor = parent
        if not absolute.is_file():
            raise PlannerSceneBindingError("manifest path is not a regular file")
    except PlannerSceneBindingError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise PlannerSceneBindingError("manifest path is not a safe regular file") from error
    return absolute


def _make_binding_runtime():
    """Build the binding class around one private, immutable geometry snapshot.

    The returned class deliberately closes over every trusted input.  Its
    instances have no storage, so ``object.__setattr__`` and an instance
    ``__dict__`` cannot replace the geometry used by ``query`` or ``manifest``.
    This is a consistency guard for ordinary in-process misuse, not a defense
    against arbitrary Python reflection or code execution.
    """
    # Capture imports and types before exposing the module.  None of the
    # runtime methods below performs a later lookup through a module global.
    json_module = json
    hashlib_module = hashlib
    math_module = math
    deepcopy_function = deepcopy
    os_module = os
    path_type = Path
    real_type = Real
    mapping_proxy_type = MappingProxyType
    profile_type = SceneProfile
    aabb_type = AABB
    snapshot_type = _ProfileSnapshot
    binding_error_type = PlannerSceneBindingError
    identity_error_type = PlannerSceneIdentityError
    profile_field_names = frozenset(profile_type.__dataclass_fields__)
    aabb_field_names = frozenset(aabb_type.__dataclass_fields__)
    canonical_profile = EGO_SINGLE_BOX_V1

    # These literals are the committed contract.  They are intentionally
    # separate from the public module names and from _fixed_identities().
    identities = mapping_proxy_type({
        "manifest_schema": "wksim.planner-scene-binding.v1",
        "contact_schema": "wksim.planner-contact.v1",
        "query_version": "planner-aabb-point-contact-v1",
        "tick_ns": 1_000_000,
        "profile_source_identity": "Simulator/wksim_planning/scene_profile.py",
        "binding_source_identity": "Simulator/wksim_runtime/planner_scene_binding.py",
        "legacy_scene_id": "static-plane-box-v1",
        "legacy_scene_hash": "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514",
        "physics_authority": "WSL",
        "profile_hash": "49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7",
        "collision_hash": "08b88651775ae2181e5082f124d16c6a434597703fdf2ff08bfc0bd59205c07c",
        "voxel_hash": "3602530733cf10fd0960212dc413b157e56e662d330b4b314a71f4c21abae638",
        "point_cloud_hash": "d14d6311a45e3e7d1c323afdb67205510c5370eed2959d23bff70cd1ac04f2ad",
        "scene_hash": "40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba",
        "profile_id": "ego-single-box-v1",
        "geometry_id": "ego-single-box-v1:obstacle",
    })

    def canonical_bytes(value: Any) -> bytes:
        try:
            return json_module.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise binding_error_type("value is not canonically serializable") from error

    def sha256_bytes(value: bytes) -> str:
        return hashlib_module.sha256(value).hexdigest()

    def sha256_value(value: Any) -> str:
        return sha256_bytes(canonical_bytes(value))

    def finite(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, real_type) or not math_module.isfinite(value):
            raise binding_error_type(f"{name} must be a finite real number")
        return float(value)

    def vector(value: Any, name: str) -> tuple[float, float, float]:
        if type(value) not in (tuple, list) or len(value) != 3:
            raise binding_error_type(f"{name} must be a three-element sequence")
        return tuple(finite(item, f"{name}[{index}]") for index, item in enumerate(value))

    def step(value: Any, name: str = "step") -> int:
        if type(value) is not int or value < 0:
            raise binding_error_type(f"{name} must be a non-negative integer")
        return value

    def epoch(value: Any) -> str:
        if (not isinstance(value, str) or len(value) != 32 or value != value.lower()
                or any(character not in "0123456789abcdef" for character in value)):
            raise binding_error_type("epoch must be a lowercase 32-character hexadecimal id")
        return value

    def identity(value: Any, name: str) -> str:
        if (not isinstance(value, str) or not value or value.strip() != value
                or "\x00" in value):
            raise binding_error_type(f"{name} must be a non-empty identity string")
        return value

    def hash_text(value: Any, name: str) -> str:
        if (not isinstance(value, str) or len(value) != 64 or value != value.lower()
                or any(character not in "0123456789abcdef" for character in value)):
            raise binding_error_type(f"{name} must be a lowercase SHA-256 hexadecimal string")
        return value

    def capture_profile(profile: Any) -> _ProfileSnapshot:
        """Read only raw dataclass fields; never invoke a profile method."""
        if type(profile) is not profile_type:
            raise identity_error_type("only the committed ego scene profile is accepted")
        try:
            fields = object.__getattribute__(profile, "__dict__")
            if type(fields) is not dict or set(fields) != profile_field_names:
                raise identity_error_type("only the committed ego scene profile is accepted")
            obstacle = fields["obstacle"]
            if type(obstacle) is not aabb_type:
                raise identity_error_type("only the committed ego scene profile is accepted")
            obstacle_fields = object.__getattribute__(obstacle, "__dict__")
            if type(obstacle_fields) is not dict or set(obstacle_fields) != aabb_field_names:
                raise identity_error_type("only the committed ego scene profile is accepted")
            minimum = vector(obstacle_fields["minimum"], "obstacle.minimum")
            maximum = vector(obstacle_fields["maximum"], "obstacle.maximum")
            values = {
                "profile_id": fields["profile_id"],
                "version": fields["version"],
                "frame": fields["frame"],
                "coordinate_system": fields["coordinate_system"],
                "length_unit": fields["length_unit"],
                "time_unit": fields["time_unit"],
                "angle_unit": fields["angle_unit"],
                "origin": vector(fields["origin"], "origin"),
                "size": vector(fields["size"], "size"),
                "voxel_resolution": finite(fields["voxel_resolution"], "voxel_resolution"),
                "voxel_order": fields["voxel_order"],
                "voxel_center_convention": fields["voxel_center_convention"],
                "ground_z": finite(fields["ground_z"], "ground_z"),
                "ceiling_z": finite(fields["ceiling_z"], "ceiling_z"),
                "obstacle_minimum": minimum,
                "obstacle_maximum": maximum,
                "vehicle_radius": finite(fields["vehicle_radius"], "vehicle_radius"),
                "required_clearance": finite(fields["required_clearance"], "required_clearance"),
            }
            if (type(values["profile_id"]) is not str
                    or type(values["version"]) is not int
                    or any(type(values[name]) is not str for name in (
                        "frame", "coordinate_system", "length_unit", "time_unit",
                        "angle_unit", "voxel_order", "voxel_center_convention"))):
                raise identity_error_type("only the committed ego scene profile is accepted")
            if any(lo >= hi for lo, hi in zip(minimum, maximum)):
                raise identity_error_type("only the committed ego scene profile is accepted")
            bounds: list[tuple[int, int]] = []
            for map_origin, lo, hi in zip(values["origin"], minimum, maximum):
                low_float = (lo - map_origin) / values["voxel_resolution"]
                count_float = (hi - lo) / values["voxel_resolution"]
                low = round(low_float)
                count = round(count_float)
                if (not math_module.isclose(low_float, low, rel_tol=0.0, abs_tol=1e-9)
                        or not math_module.isclose(count_float, count, rel_tol=0.0, abs_tol=1e-9)
                        or count <= 0):
                    raise identity_error_type("only the committed ego scene profile is accepted")
                bounds.append((int(low), int(low + count - 1)))
            index_bounds = tuple(bounds)
            indices = tuple((x, y, z)
                            for x in range(index_bounds[0][0], index_bounds[0][1] + 1)
                            for y in range(index_bounds[1][0], index_bounds[1][1] + 1)
                            for z in range(index_bounds[2][0], index_bounds[2][1] + 1))
            point_cloud = tuple(
                tuple(round(origin + (index + 0.5) * values["voxel_resolution"], 12)
                      for origin, index in zip(values["origin"], index_tuple))
                for index_tuple in indices
            )
            return snapshot_type(
                **values,
                obstacle_index_bounds=index_bounds,
                voxel_indices=indices,
                point_cloud=point_cloud,
            )
        except identity_error_type:
            raise
        except (ArithmeticError, KeyError, TypeError, ValueError) as error:
            raise identity_error_type("only the committed ego scene profile is accepted") from error

    def profile_payload(profile: _ProfileSnapshot) -> dict[str, Any]:
        return {
            "profile_id": profile.profile_id,
            "version": profile.version,
            "frame": profile.frame,
            "coordinate_system": profile.coordinate_system,
            "units": {
                "length": profile.length_unit,
                "time": profile.time_unit,
                "angle": profile.angle_unit,
            },
            "origin": list(profile.origin),
            "size": list(profile.size),
            "voxel_resolution": profile.voxel_resolution,
            "voxel_order": profile.voxel_order,
            "voxel_center_convention": profile.voxel_center_convention,
            "ground_z": profile.ground_z,
            "ceiling_z": profile.ceiling_z,
            "obstacle": {
                "min": list(profile.obstacle_minimum),
                "max": list(profile.obstacle_maximum),
            },
            "vehicle_radius": profile.vehicle_radius,
            "required_clearance": profile.required_clearance,
        }

    def point_cloud_hash(profile: _ProfileSnapshot) -> str:
        return sha256_value({
            "profile_id": profile.profile_id,
            "voxel_order": profile.voxel_order,
            "center_convention": profile.voxel_center_convention,
            "points_enu_m": [list(point) for point in profile.point_cloud],
        })

    def manifest_payload(profile: _ProfileSnapshot, profile_hash: str,
                         collision_hash: str, voxel_hash: str,
                         cloud_hash: str) -> dict[str, Any]:
        return {
            "schema": identities["manifest_schema"],
            "scene_id": profile.profile_id,
            "scene_version": profile.version,
            "query_version": identities["query_version"],
            "frame": profile.frame,
            "coordinate_frame": profile.coordinate_system,
            "units": {
                "length": profile.length_unit,
                "time": profile.time_unit,
                "angle": profile.angle_unit,
            },
            "origin_enu_m": list(profile.origin),
            "map_size_m": list(profile.size),
            "ground_z_m": profile.ground_z,
            "ceiling_z_m": profile.ceiling_z,
            "profile_hash": profile_hash,
            "collision_hash": collision_hash,
            "voxel_hash": voxel_hash,
            "point_cloud_hash": cloud_hash,
            "geometry": {
                "geometry_id": identities["geometry_id"],
                "kind": "aabb",
                "minimum_enu_m": list(profile.obstacle_minimum),
                "maximum_enu_m": list(profile.obstacle_maximum),
            },
            "point_cloud": {
                "count": len(profile.voxel_indices),
                "voxel_resolution_m": profile.voxel_resolution,
                "voxel_order": profile.voxel_order,
                "center_convention": profile.voxel_center_convention,
                "index_bounds": [list(bounds) for bounds in profile.obstacle_index_bounds],
            },
            "physics_authority": identities["physics_authority"],
            "capabilities": {
                "contact_geometry": True,
                "forces": False,
                "impulses": False,
                "terrain_response": False,
            },
            "visual_mirror": {"system": "UE", "binding_status": "not_bound"},
            "geometry_source_identity": identities["profile_source_identity"],
            "binding_source_identity": identities["binding_source_identity"],
        }

    def calculated_hashes(profile: _ProfileSnapshot) -> tuple[str, str, str, str]:
        profile_hash = sha256_value(profile_payload(profile))
        collision_hash = sha256_value({
            "profile_id": profile.profile_id,
            "obstacle": {
                "min": list(profile.obstacle_minimum),
                "max": list(profile.obstacle_maximum),
            },
        })
        voxel_hash = sha256_value({
            "profile_id": profile.profile_id,
            "voxel_resolution": profile.voxel_resolution,
            "voxel_order": profile.voxel_order,
            "indices": [list(index) for index in profile.voxel_indices],
        })
        return profile_hash, collision_hash, voxel_hash, point_cloud_hash(profile)

    canonical_snapshot = capture_profile(canonical_profile)
    canonical_profile_hash, canonical_collision_hash, canonical_voxel_hash, canonical_cloud_hash = (
        calculated_hashes(canonical_snapshot)
    )
    if (canonical_snapshot.profile_id != identities["profile_id"]
            or (canonical_profile_hash, canonical_collision_hash, canonical_voxel_hash,
                canonical_cloud_hash) != (
                    identities["profile_hash"], identities["collision_hash"],
                    identities["voxel_hash"], identities["point_cloud_hash"])):
        raise identity_error_type("committed planner scene profile hashes are invalid")
    frozen_payload = manifest_payload(
        canonical_snapshot,
        canonical_profile_hash,
        canonical_collision_hash,
        canonical_voxel_hash,
        canonical_cloud_hash,
    )
    frozen_scene_hash = sha256_value(frozen_payload)
    if frozen_scene_hash != identities["scene_hash"]:
        raise identity_error_type("committed planner scene manifest hash is invalid")
    frozen_profile_bytes = canonical_bytes(profile_payload(canonical_snapshot))

    def validate_profile(profile: Any) -> None:
        candidate = capture_profile(profile)
        profile_hash, collision_hash, voxel_hash, cloud_hash = calculated_hashes(candidate)
        if (candidate.profile_id != identities["profile_id"]
                or canonical_bytes(profile_payload(candidate)) != frozen_profile_bytes
                or (profile_hash, collision_hash, voxel_hash, cloud_hash) != (
                    identities["profile_hash"], identities["collision_hash"],
                    identities["voxel_hash"], identities["point_cloud_hash"])):
            raise identity_error_type("only the committed ego scene profile is accepted")

    def make_aabb(profile: _ProfileSnapshot) -> AABB:
        result = object.__new__(aabb_type)
        object.__setattr__(result, "minimum", profile.obstacle_minimum)
        object.__setattr__(result, "maximum", profile.obstacle_maximum)
        return result

    def make_profile(profile: _ProfileSnapshot) -> SceneProfile:
        result = object.__new__(profile_type)
        for name, value in (
            ("profile_id", profile.profile_id),
            ("frame", profile.frame),
            ("coordinate_system", profile.coordinate_system),
            ("length_unit", profile.length_unit),
            ("time_unit", profile.time_unit),
            ("angle_unit", profile.angle_unit),
            ("origin", profile.origin),
            ("size", profile.size),
            ("voxel_resolution", profile.voxel_resolution),
            ("ground_z", profile.ground_z),
            ("ceiling_z", profile.ceiling_z),
            ("obstacle", make_aabb(profile)),
            ("vehicle_radius", profile.vehicle_radius),
            ("required_clearance", profile.required_clearance),
            ("voxel_order", profile.voxel_order),
            ("voxel_center_convention", profile.voxel_center_convention),
            ("version", profile.version),
        ):
            object.__setattr__(result, name, value)
        return result

    def manifest_copy() -> dict[str, Any]:
        value = deepcopy_function(frozen_payload)
        value["scene_hash"] = frozen_scene_hash
        return value

    def validate_manifest_value(manifest: Any) -> dict[str, Any]:
        if type(manifest) is not dict:
            raise binding_error_type("manifest must be a mapping")
        try:
            encoded = canonical_bytes(manifest)
            expected = canonical_bytes(manifest_copy())
        except binding_error_type:
            raise
        if encoded != expected:
            if (manifest.get("scene_id") == identities["legacy_scene_id"]
                    or manifest.get("scene_hash") == identities["legacy_scene_hash"]):
                raise identity_error_type("static-plane-box-v1 cannot be used as planner geometry")
            raise identity_error_type("planner scene manifest identity mismatch")
        supplied_scene_hash = hash_text(manifest.get("scene_hash"), "scene_hash")
        if supplied_scene_hash != sha256_bytes(canonical_bytes({
                key: value for key, value in manifest.items() if key != "scene_hash"})):
            raise identity_error_type("scene_hash does not match canonical manifest")
        return deepcopy_function(manifest)

    def reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise binding_error_type(f"duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def path_is_link(path: Path) -> bool:
        try:
            if path.is_symlink():
                return True
            is_junction = getattr(path, "is_junction", None)
            return bool(is_junction()) if is_junction is not None else False
        except OSError as error:
            raise binding_error_type("manifest path cannot be inspected") from error

    def safe_manifest_path(path: str | Path) -> Path:
        if not isinstance(path, (str, path_type)):
            raise binding_error_type("manifest path must be a string or Path")
        path_value = path_type(path)
        if "\x00" in str(path_value):
            raise binding_error_type("manifest path contains a NUL byte")
        try:
            absolute = path_type(os_module.path.abspath(os_module.fspath(path_value)))
            resolved = path_value.resolve(strict=True)
            if os_module.path.normcase(os_module.fspath(absolute)) != os_module.path.normcase(os_module.fspath(resolved)):
                raise binding_error_type("manifest path must not resolve through an alias")
            cursor = absolute
            while True:
                if path_is_link(cursor):
                    raise binding_error_type("manifest file and parents must not be symlinks")
                parent = cursor.parent
                if parent == cursor:
                    break
                cursor = parent
            if not absolute.is_file():
                raise binding_error_type("manifest path is not a regular file")
        except binding_error_type:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise binding_error_type("manifest path is not a safe regular file") from error
        return absolute

    required_query_fields = frozenset({
        "scene_id", "scene_hash", "profile_hash", "collision_hash", "voxel_hash",
        "point_cloud_hash", "query_version", "epoch", "step", "sim_time_ns",
        "body_id", "geometry_id", "point_enu_m", "source_identity",
    })

    def validate_query(request: Any) -> dict[str, Any]:
        if type(request) is not dict or set(request) != required_query_fields:
            raise binding_error_type("query must contain exactly the binding identity fields")
        if (request["scene_id"] != identities["profile_id"]
                or request["scene_hash"] != frozen_scene_hash):
            raise identity_error_type("query scene identity mismatch")
        if (request["scene_id"] == identities["legacy_scene_id"]
                or request["scene_hash"] == identities["legacy_scene_hash"]):
            raise identity_error_type("static-plane-box-v1 cannot be used as planner geometry")
        for field, expected in (
            ("profile_hash", identities["profile_hash"]),
            ("collision_hash", identities["collision_hash"]),
            ("voxel_hash", identities["voxel_hash"]),
            ("point_cloud_hash", identities["point_cloud_hash"]),
        ):
            if request[field] != expected:
                raise identity_error_type(f"query {field} mismatch")
            hash_text(request[field], field)
        if request["query_version"] != identities["query_version"]:
            raise identity_error_type("query version mismatch")
        if request["source_identity"] != identities["binding_source_identity"]:
            raise identity_error_type("query source identity mismatch")
        parsed_epoch = epoch(request["epoch"])
        parsed_step = step(request["step"])
        sim_time_ns = request["sim_time_ns"]
        if type(sim_time_ns) is not int or sim_time_ns != parsed_step * identities["tick_ns"]:
            raise binding_error_type("sim_time_ns must equal step * 1_000_000")
        body_id = identity(request["body_id"], "body_id")
        if request["geometry_id"] != identities["geometry_id"]:
            raise identity_error_type("query geometry identity mismatch")
        return {
            "epoch": parsed_epoch,
            "step": parsed_step,
            "sim_time_ns": sim_time_ns,
            "body_id": body_id,
            "point_enu_m": vector(request["point_enu_m"], "point_enu_m"),
        }

    frozen_classes: set[type] = set()

    class _FrozenBindingMeta(type):
        """Prevent changing the public binding class after construction."""

        __slots__ = ()

        def __new__(mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any],
                    **kwargs: Any):
            cls = super().__new__(mcls, name, bases, namespace, **kwargs)
            frozen_classes.add(cls)
            return cls

        def __setattr__(cls, name: str, value: Any) -> None:
            if cls in frozen_classes:
                raise TypeError("PlannerSceneBinding class is frozen")
            super().__setattr__(name, value)

        def __delattr__(cls, name: str) -> None:
            if cls in frozen_classes:
                raise TypeError("PlannerSceneBinding class is frozen")
            super().__delattr__(name)

    class PlannerSceneBinding(metaclass=_FrozenBindingMeta):
        """Offline binding with no instance state and ordinary mutation guards.

        The class guard and closure snapshot reduce accidental or unsupported
        same-process reconfiguration.  They do not replace the pinned-source
        and controlled-process integrity boundary described by the contract.
        """

        __slots__ = ()

        def __init__(self, profile: SceneProfile = canonical_profile) -> None:
            validate_profile(profile)

        def __init_subclass__(cls, **kwargs: Any) -> None:
            raise TypeError("PlannerSceneBinding cannot be subclassed")

        @property
        def scene_id(self) -> str:
            return identities["profile_id"]

        @property
        def scene_hash(self) -> str:
            return frozen_scene_hash

        @property
        def geometry_id(self) -> str:
            return identities["geometry_id"]

        @property
        def profile(self) -> SceneProfile:
            return make_profile(canonical_snapshot)

        @property
        def aabb(self) -> AABB:
            return make_aabb(canonical_snapshot)

        @property
        def point_cloud(self) -> tuple[tuple[float, float, float], ...]:
            return canonical_snapshot.point_cloud

        @property
        def point_cloud_hash(self) -> str:
            return identities["point_cloud_hash"]

        @property
        def manifest(self) -> dict[str, Any]:
            return manifest_copy()

        def canonical_manifest_bytes(self) -> bytes:
            """Return hash-free canonical bytes used to derive ``scene_hash``."""
            return canonical_bytes(frozen_payload)

        def _validate_manifest(self, manifest: Any) -> dict[str, Any]:
            return validate_manifest_value(manifest)

        def validate_manifest(self, manifest: Any) -> dict[str, Any]:
            """Fail closed unless ``manifest`` is byte-equivalent to this binding."""
            return validate_manifest_value(manifest)

        def load_manifest(self, path: str | Path) -> dict[str, Any]:
            """Load and validate a generated manifest from a safe regular file."""
            try:
                safe_path = safe_manifest_path(path)
                with safe_path.open("r", encoding="utf-8", newline="") as handle:
                    value = json_module.load(handle, object_pairs_hook=reject_duplicate_json_pairs)
            except binding_error_type:
                raise
            except (OSError, ValueError, TypeError, json_module.JSONDecodeError) as error:
                raise binding_error_type("manifest path or JSON is invalid") from error
            return validate_manifest_value(value)

        def _validate_query(self, request: Any) -> dict[str, Any]:
            return validate_query(request)

        def query(self, request: Mapping[str, Any]) -> dict[str, Any]:
            """Run a pure point-versus-AABB geometry query."""
            parsed = validate_query(request)
            point = parsed["point_enu_m"]
            minimum = canonical_snapshot.obstacle_minimum
            maximum = canonical_snapshot.obstacle_maximum
            if all(lo <= coordinate <= hi
                   for coordinate, lo, hi in zip(point, minimum, maximum)):
                candidates = (
                    (point[0] - minimum[0], (minimum[0], point[1], point[2]), (-1.0, 0.0, 0.0)),
                    (maximum[0] - point[0], (maximum[0], point[1], point[2]), (1.0, 0.0, 0.0)),
                    (point[1] - minimum[1], (point[0], minimum[1], point[2]), (0.0, -1.0, 0.0)),
                    (maximum[1] - point[1], (point[0], maximum[1], point[2]), (0.0, 1.0, 0.0)),
                    (point[2] - minimum[2], (point[0], point[1], minimum[2]), (0.0, 0.0, -1.0)),
                    (maximum[2] - point[2], (point[0], point[1], maximum[2]), (0.0, 0.0, 1.0)),
                )
                depth, contact_point, normal = min(candidates, key=lambda item: item[0])
                envelope = {
                    "schema": identities["contact_schema"],
                    "scene_id": identities["profile_id"],
                    "scene_hash": frozen_scene_hash,
                    "profile_hash": identities["profile_hash"],
                    "collision_hash": identities["collision_hash"],
                    "voxel_hash": identities["voxel_hash"],
                    "point_cloud_hash": identities["point_cloud_hash"],
                    "query_version": identities["query_version"],
                    "epoch": parsed["epoch"],
                    "step": parsed["step"],
                    "sim_time_ns": parsed["sim_time_ns"],
                    "valid_from_step": parsed["step"],
                    "valid_until_step": parsed["step"],
                    "body_id": parsed["body_id"],
                    "geometry_id": identities["geometry_id"],
                    "contact_point_enu_m": list(contact_point),
                    "normal_enu": list(normal),
                    "penetration_m": depth,
                    "source_identity": identities["binding_source_identity"],
                    "geometry_source_identity": identities["profile_source_identity"],
                }
                return {
                    "result": "contact",
                    "observation": "valid",
                    "scene_id": identities["profile_id"],
                    "scene_hash": frozen_scene_hash,
                    "query_version": identities["query_version"],
                    "epoch": parsed["epoch"],
                    "step": parsed["step"],
                    "sim_time_ns": parsed["sim_time_ns"],
                    "body_id": parsed["body_id"],
                    "geometry_id": identities["geometry_id"],
                    "envelope": envelope,
                }
            return {
                "result": "no_contact",
                "observation": "valid",
                "scene_id": identities["profile_id"],
                "scene_hash": frozen_scene_hash,
                "query_version": identities["query_version"],
                "epoch": parsed["epoch"],
                "step": parsed["step"],
                "sim_time_ns": parsed["sim_time_ns"],
                "body_id": parsed["body_id"],
                "geometry_id": identities["geometry_id"],
                "envelope": None,
            }

    def canonical_manifest_bytes(manifest: Any) -> bytes:
        validated = validate_manifest_value(manifest)
        return canonical_bytes({
            key: value for key, value in validated.items() if key != "scene_hash"
        })

    return PlannerSceneBinding, canonical_manifest_bytes


PlannerSceneBinding, canonical_manifest_bytes = _make_binding_runtime()
EGO_SINGLE_BOX_BINDING = PlannerSceneBinding()
