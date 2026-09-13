"""Pure offline scene/profile and clearance contract for the planner slice.

This module is deliberately independent of ROS, an EGO planner, maps, SITL and
the trajectory runtime.  It describes the one frozen geometry used by the
``ego-single-box-v1`` planning contract and provides deterministic geometry
helpers that an offline test can use before any runtime integration exists.

The public geometry is ENU ``map`` coordinates, with lengths in metres.  A
voxel is a half-open cell ``[lower, upper)`` and its point-cloud sample is its
centre.  Consequently an obstacle whose bounds are aligned to the 0.1 m grid
contains no samples on its upper face.  This makes both the count and ordering
of samples independent of floating-point range loops.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Real
from typing import Any, Mapping, Sequence


PROFILE_ID = "ego-single-box-v1"
NO_ROUTE_PROFILE_ID = "ego-single-box-v1-no-route"
PROFILE_VERSION = 1
FRAME = "map"
COORDINATE_SYSTEM = "ENU"
LENGTH_UNIT = "m"
TIME_UNIT = "s"
ANGLE_UNIT = "rad"
VOXEL_ORDER = "x,y,z"
VOXEL_CENTER_CONVENTION = "lower + (index + 0.5) * resolution"

ORIGIN = (-10.0, -6.0, 0.0)
SIZE = (20.0, 12.0, 6.0)
VOXEL_RESOLUTION = 0.1
OBSTACLE_MIN = (-0.5, -1.0, 0.0)
OBSTACLE_MAX = (0.5, 1.0, 5.5)
GROUND_Z = 0.0
CEILING_Z = 5.5
VEHICLE_RADIUS = 0.35
REQUIRED_CLEARANCE = 0.30


class SceneProfileError(ValueError):
    """Raised when a profile, geometry input, or hash is unsafe to consume."""


class ProfileMismatchError(SceneProfileError):
    """Raised when a supplied profile is not the expected canonical profile."""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise SceneProfileError(f"{name} must be a finite real number")
    return float(value)


def _vector(value: Any, name: str) -> tuple[float, float, float]:
    # Reject arbitrary iterators.  A bounded, repeatable profile input is part of
    # the fail-closed boundary and avoids consuming an unbounded generator.
    if type(value) not in (tuple, list) or len(value) != 3:
        raise SceneProfileError(f"{name} must be a three-element sequence")
    return tuple(_finite(item, f"{name}[{index}]") for index, item in enumerate(value))


def _strict_int(value: Any, name: str) -> int:
    if type(value) is not int:
        raise SceneProfileError(f"{name} must be an integer")
    return value


def _canonical_json(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SceneProfileError("profile is not canonically serializable") from error
    return encoded


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _aligned_obstacle_index_bounds(
    origin: tuple[float, float, float],
    resolution: float,
    obstacle: "AABB",
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Validate that every obstacle face lands on the profile voxel grid."""
    bounds: list[tuple[int, int]] = []
    for map_origin, lo, hi in zip(origin, obstacle.minimum, obstacle.maximum):
        low_float = (lo - map_origin) / resolution
        count_float = (hi - lo) / resolution
        low = round(low_float)
        count = round(count_float)
        if (not math.isclose(low_float, low, rel_tol=0.0, abs_tol=1e-9)
                or not math.isclose(count_float, count, rel_tol=0.0, abs_tol=1e-9)):
            raise SceneProfileError("obstacle bounds must align to the voxel grid")
        if count <= 0:
            raise SceneProfileError("obstacle must contain at least one voxel")
        bounds.append((int(low), int(low + count - 1)))
    return tuple(bounds)  # type: ignore[return-value]


@dataclass(frozen=True)
class AABB:
    """A finite, non-empty axis-aligned box in the profile frame."""

    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    def __post_init__(self) -> None:
        minimum = _vector(self.minimum, "aabb.minimum")
        maximum = _vector(self.maximum, "aabb.maximum")
        if any(lo >= hi for lo, hi in zip(minimum, maximum)):
            raise SceneProfileError("aabb minimum must be strictly below maximum")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    @classmethod
    def from_value(cls, value: Any, name: str = "aabb") -> "AABB":
        if isinstance(value, cls):
            return value
        if type(value) is not dict:
            raise SceneProfileError(f"{name} must be a mapping")
        if set(value) != {"min", "max"}:
            raise SceneProfileError(f"{name} must contain exactly min and max")
        try:
            return cls(tuple(value["min"]), tuple(value["max"]))
        except (TypeError, ValueError) as error:
            raise SceneProfileError(f"{name} has invalid bounds") from error

    def as_dict(self) -> dict[str, list[float]]:
        return {"min": list(self.minimum), "max": list(self.maximum)}

    @property
    def min(self) -> tuple[float, float, float]:
        return self.minimum

    @property
    def max(self) -> tuple[float, float, float]:
        return self.maximum

    @property
    def min_corner(self) -> tuple[float, float, float]:
        return self.minimum

    @property
    def max_corner(self) -> tuple[float, float, float]:
        return self.maximum

    def contains(self, point: Any, *, inclusive: bool = True) -> bool:
        point = _vector(point, "point")
        if inclusive:
            return all(lo <= coordinate <= hi
                       for coordinate, lo, hi in zip(point, self.minimum, self.maximum))
        return all(lo <= coordinate < hi
                   for coordinate, lo, hi in zip(point, self.minimum, self.maximum))


@dataclass(frozen=True)
class SceneProfile:
    """Versioned, hashable scene geometry and clearance policy."""

    profile_id: str
    frame: str
    coordinate_system: str
    length_unit: str
    time_unit: str
    angle_unit: str
    origin: tuple[float, float, float]
    size: tuple[float, float, float]
    voxel_resolution: float
    ground_z: float
    ceiling_z: float
    obstacle: AABB
    vehicle_radius: float
    required_clearance: float
    voxel_order: str = VOXEL_ORDER
    voxel_center_convention: str = VOXEL_CENTER_CONVENTION
    version: int = PROFILE_VERSION

    def __post_init__(self) -> None:
        if type(self.profile_id) is not str or not self.profile_id:
            raise SceneProfileError("profile_id must be a non-empty string")
        for value, expected, name in (
            (self.frame, FRAME, "frame"),
            (self.coordinate_system, COORDINATE_SYSTEM, "coordinate_system"),
            (self.length_unit, LENGTH_UNIT, "length_unit"),
            (self.time_unit, TIME_UNIT, "time_unit"),
            (self.angle_unit, ANGLE_UNIT, "angle_unit"),
            (self.voxel_order, VOXEL_ORDER, "voxel_order"),
            (self.voxel_center_convention, VOXEL_CENTER_CONVENTION,
             "voxel_center_convention"),
        ):
            if value != expected:
                raise SceneProfileError(f"{name} must be {expected!r}")
        if type(self.version) is not int or self.version != PROFILE_VERSION:
            raise SceneProfileError("unsupported profile version")

        origin = _vector(self.origin, "origin")
        size = _vector(self.size, "size")
        if any(value <= 0.0 for value in size):
            raise SceneProfileError("size must be positive")
        resolution = _finite(self.voxel_resolution, "voxel_resolution")
        if resolution <= 0.0:
            raise SceneProfileError("voxel_resolution must be positive")
        for dimension, name in zip(size, ("x", "y", "z")):
            cells = dimension / resolution
            if not math.isclose(cells, round(cells), rel_tol=0.0, abs_tol=1e-9):
                raise SceneProfileError(f"size.{name} must be an integer voxel count")
        ground = _finite(self.ground_z, "ground_z")
        ceiling = _finite(self.ceiling_z, "ceiling_z")
        if not origin[2] <= ground < ceiling <= origin[2] + size[2]:
            raise SceneProfileError("ground_z and ceiling_z must lie within the map")
        radius = _finite(self.vehicle_radius, "vehicle_radius")
        clearance = _finite(self.required_clearance, "required_clearance")
        if radius < 0.0 or clearance < 0.0:
            raise SceneProfileError("vehicle_radius and required_clearance must be non-negative")
        if not isinstance(self.obstacle, AABB):
            raise SceneProfileError("obstacle must be an AABB")

        bounds = AABB(origin, tuple(o + s for o, s in zip(origin, size)))
        if not bounds.contains(self.obstacle.minimum) or not bounds.contains(self.obstacle.maximum):
            raise SceneProfileError("obstacle must lie within map bounds")
        # Enforce the generation precondition while constructing/parsing a profile.
        # A self-consistent hash must never be able to defer a non-generable
        # obstacle until a later voxel call.
        _aligned_obstacle_index_bounds(origin, resolution, self.obstacle)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "voxel_resolution", resolution)
        object.__setattr__(self, "ground_z", ground)
        object.__setattr__(self, "ceiling_z", ceiling)
        object.__setattr__(self, "vehicle_radius", radius)
        object.__setattr__(self, "required_clearance", clearance)

    @property
    def units(self) -> dict[str, str]:
        return {"length": self.length_unit, "time": self.time_unit, "angle": self.angle_unit}

    @property
    def map_bounds(self) -> AABB:
        return AABB(self.origin, tuple(o + s for o, s in zip(self.origin, self.size)))

    @property
    def aabb(self) -> AABB:
        return self.obstacle

    @property
    def profile_hash(self) -> str:
        """SHA-256 over the hash-free canonical profile payload."""
        return _sha256(self.to_dict(include_hashes=False))

    @property
    def canonical_hash(self) -> str:
        return self.profile_hash

    @property
    def hash(self) -> str:
        """Short alias used by evidence writers for the canonical profile hash."""
        return self.profile_hash

    @property
    def collision_hash(self) -> str:
        return _sha256({"profile_id": self.profile_id, "obstacle": self.obstacle.as_dict()})

    @property
    def voxel_hash(self) -> str:
        return _sha256({
            "profile_id": self.profile_id,
            "voxel_resolution": self.voxel_resolution,
            "voxel_order": self.voxel_order,
            "indices": [list(index) for index in self.voxel_indices()],
        })

    @property
    def point_cloud_hash(self) -> str:
        return self.voxel_hash

    def to_dict(self, *, include_hashes: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "profile_id": self.profile_id,
            "version": self.version,
            "frame": self.frame,
            "coordinate_system": self.coordinate_system,
            "units": dict(self.units),
            "origin": list(self.origin),
            "size": list(self.size),
            "voxel_resolution": self.voxel_resolution,
            "voxel_order": self.voxel_order,
            "voxel_center_convention": self.voxel_center_convention,
            "ground_z": self.ground_z,
            "ceiling_z": self.ceiling_z,
            "obstacle": self.obstacle.as_dict(),
            "vehicle_radius": self.vehicle_radius,
            "required_clearance": self.required_clearance,
        }
        if include_hashes:
            value.update({
                "canonical_hash": self.profile_hash,
                "profile_hash": self.profile_hash,
                "collision_hash": self.collision_hash,
                "voxel_hash": self.voxel_hash,
                "point_cloud_hash": self.voxel_hash,
            })
        return value

    as_dict = to_dict

    @classmethod
    def from_value(cls, value: Any, *, expected_hash: str | None = None,
                   require_hash: bool = False) -> "SceneProfile":
        if isinstance(value, cls):
            profile = value
            if expected_hash is not None and profile.profile_hash != expected_hash:
                raise ProfileMismatchError("scene profile hash does not match expected hash")
            return profile
        if type(value) is not dict:
            raise SceneProfileError("scene profile must be a mapping or SceneProfile")
        allowed = {
            "profile_id", "version", "frame", "coordinate_system", "units", "origin", "size",
            "voxel_resolution", "voxel_order", "voxel_center_convention", "ground_z",
            "ceiling_z", "obstacle", "vehicle_radius", "required_clearance",
            "canonical_hash", "profile_hash", "collision_hash", "voxel_hash", "point_cloud_hash",
        }
        if not set(value).issubset(allowed):
            raise SceneProfileError("scene profile contains unknown fields")
        units = value.get("units")
        if type(units) is not dict or set(units) != {"length", "time", "angle"}:
            raise SceneProfileError("units must explicitly contain length, time and angle")
        try:
            profile = cls(
                profile_id=value["profile_id"],
                version=value["version"],
                frame=value["frame"],
                coordinate_system=value["coordinate_system"],
                length_unit=units["length"],
                time_unit=units["time"],
                angle_unit=units["angle"],
                origin=tuple(value["origin"]),
                size=tuple(value["size"]),
                voxel_resolution=value["voxel_resolution"],
                voxel_order=value["voxel_order"],
                voxel_center_convention=value["voxel_center_convention"],
                ground_z=value["ground_z"],
                ceiling_z=value["ceiling_z"],
                obstacle=AABB.from_value(value["obstacle"], "obstacle"),
                vehicle_radius=value["vehicle_radius"],
                required_clearance=value["required_clearance"],
            )
        except KeyError as error:
            raise SceneProfileError(f"scene profile is missing {error.args[0]!r}") from error
        except (TypeError, ValueError) as error:
            if isinstance(error, SceneProfileError):
                raise
            raise SceneProfileError("scene profile has invalid fields") from error

        supplied_hashes = []
        for field in ("canonical_hash", "profile_hash"):
            if field in value:
                supplied_hashes.append(value[field])
        if require_hash and not supplied_hashes:
            raise ProfileMismatchError("scene profile hash is required")
        if supplied_hashes and any(type(item) is not str for item in supplied_hashes):
            raise ProfileMismatchError("scene profile hash must be a hexadecimal string")
        if supplied_hashes and any(item != profile.profile_hash for item in supplied_hashes):
            raise ProfileMismatchError("scene profile hash does not match canonical content")
        if expected_hash is not None and profile.profile_hash != expected_hash:
            raise ProfileMismatchError("scene profile hash does not match expected hash")
        if "collision_hash" in value and value["collision_hash"] != profile.collision_hash:
            raise ProfileMismatchError("collision hash does not match canonical obstacle")
        if "voxel_hash" in value and value["voxel_hash"] != profile.voxel_hash:
            raise ProfileMismatchError("voxel hash does not match deterministic voxel set")
        if "point_cloud_hash" in value and value["point_cloud_hash"] != profile.voxel_hash:
            raise ProfileMismatchError("point cloud hash does not match deterministic voxel set")
        return profile

    def grid_shape(self) -> tuple[int, int, int]:
        return tuple(int(round(size / self.voxel_resolution)) for size in self.size)

    def obstacle_index_bounds(self) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        """Return inclusive integer voxel-index bounds in x/y/z order."""
        return _aligned_obstacle_index_bounds(self.origin, self.voxel_resolution, self.obstacle)

    def voxel_indices(self) -> tuple[tuple[int, int, int], ...]:
        """Deterministic x-major, then y, then z ascending obstacle indices."""
        (x0, x1), (y0, y1), (z0, z1) = self.obstacle_index_bounds()
        return tuple((x, y, z)
                     for x in range(x0, x1 + 1)
                     for y in range(y0, y1 + 1)
                     for z in range(z0, z1 + 1))

    def voxel_centers(self) -> tuple[tuple[float, float, float], ...]:
        """Return all obstacle voxel centres in the fixed index order."""
        return tuple(tuple(round(origin + (index + 0.5) * self.voxel_resolution, 12)
                           for origin, index in zip(self.origin, indices))
                     for indices in self.voxel_indices())

    def point_cloud(self) -> tuple[tuple[float, float, float], ...]:
        return self.voxel_centers()

    @property
    def voxels(self) -> tuple[tuple[float, float, float], ...]:
        return self.voxel_centers()

    def contains(self, point: Any, *, include_boundary: bool = True) -> bool:
        return self.map_bounds.contains(point, inclusive=include_boundary)

    def with_obstacle(self, obstacle: AABB | Mapping[str, Any], *, profile_id: str | None = None,
                      ceiling_z: float | None = None) -> "SceneProfile":
        """Create an explicitly named derived case with identical map semantics."""
        return SceneProfile(
            profile_id=self.profile_id if profile_id is None else profile_id,
            frame=self.frame,
            coordinate_system=self.coordinate_system,
            length_unit=self.length_unit,
            time_unit=self.time_unit,
            angle_unit=self.angle_unit,
            origin=self.origin,
            size=self.size,
            voxel_resolution=self.voxel_resolution,
            ground_z=self.ground_z,
            ceiling_z=self.ceiling_z if ceiling_z is None else ceiling_z,
            obstacle=AABB.from_value(obstacle),
            vehicle_radius=self.vehicle_radius,
            required_clearance=self.required_clearance,
            voxel_order=self.voxel_order,
            voxel_center_convention=self.voxel_center_convention,
            version=self.version,
        )


def _make_default_profile() -> SceneProfile:
    return SceneProfile(
        profile_id=PROFILE_ID,
        version=PROFILE_VERSION,
        frame=FRAME,
        coordinate_system=COORDINATE_SYSTEM,
        length_unit=LENGTH_UNIT,
        time_unit=TIME_UNIT,
        angle_unit=ANGLE_UNIT,
        origin=ORIGIN,
        size=SIZE,
        voxel_resolution=VOXEL_RESOLUTION,
        voxel_order=VOXEL_ORDER,
        voxel_center_convention=VOXEL_CENTER_CONVENTION,
        ground_z=GROUND_Z,
        ceiling_z=CEILING_Z,
        obstacle=AABB(OBSTACLE_MIN, OBSTACLE_MAX),
        vehicle_radius=VEHICLE_RADIUS,
        required_clearance=REQUIRED_CLEARANCE,
    )


EGO_SINGLE_BOX_V1 = _make_default_profile()
DEFAULT_PROFILE = EGO_SINGLE_BOX_V1
SCENE_PROFILE = EGO_SINGLE_BOX_V1
SCENE_PROFILE_HASH = EGO_SINGLE_BOX_V1.profile_hash
CANONICAL_PROFILE_HASH = SCENE_PROFILE_HASH


def no_route_profile() -> SceneProfile:
    """Return the explicit #39 no-route derived case.

    It fills the complete y cross-section and the map's z extent at the same x
    slab.  This helper only describes a test geometry; it does not claim that a
    planner has proved no route.
    """
    return EGO_SINGLE_BOX_V1.with_obstacle(
        AABB((-0.5, -6.0, 0.0), (0.5, 6.0, 6.0)),
        profile_id=NO_ROUTE_PROFILE_ID,
        ceiling_z=6.0,
    )


NO_ROUTE_PROFILE = no_route_profile()


def canonical_profile_hash(profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1) -> str:
    return SceneProfile.from_value(profile).profile_hash


def validate_profile(profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                     *, expected_hash: str | None = None,
                     require_hash: bool = True) -> SceneProfile:
    """Parse and verify profile content and any supplied canonical hashes."""
    return SceneProfile.from_value(profile, expected_hash=expected_hash,
                                   require_hash=require_hash)


def _validate_frame_units(frame: Any, units: Any) -> None:
    if frame != FRAME:
        raise SceneProfileError("only the ENU map frame is supported")
    if units == LENGTH_UNIT:
        return
    if type(units) is dict and units == {"length": LENGTH_UNIT}:
        return
    raise SceneProfileError("length units must be metres ('m')")


def _point(value: Any, name: str) -> tuple[float, float, float]:
    return _vector(value, name)


def _segment_aabb_distance(start: tuple[float, float, float],
                           end: tuple[float, float, float], box: AABB) -> float:
    """Compute the exact minimum Euclidean distance from a segment to an AABB.

    The point-to-box distance is piecewise quadratic along the segment.  Splitting
    at every coordinate face crossing and checking the stationary point of each
    interval avoids a sampling-dependent clearance result.
    """
    delta = tuple(b - a for a, b in zip(start, end))
    breakpoints = {0.0, 1.0}
    for coordinate, direction, lo, hi in zip(start, delta, box.minimum, box.maximum):
        if direction == 0.0:
            continue
        for face in (lo, hi):
            t = (face - coordinate) / direction
            if 0.0 < t < 1.0:
                breakpoints.add(t)
    ordered = sorted(breakpoints)

    def point_distance(t: float) -> float:
        point = tuple(a + t * d for a, d in zip(start, delta))
        squared = sum(
            (lo - coordinate) ** 2 if coordinate < lo else
            (coordinate - hi) ** 2 if coordinate > hi else 0.0
            for coordinate, lo, hi in zip(point, box.minimum, box.maximum)
        )
        return math.sqrt(squared)

    best_squared = min(point_distance(t) ** 2 for t in ordered)
    for left, right in zip(ordered, ordered[1:]):
        midpoint = (left + right) / 2.0
        coefficient_a = 0.0
        coefficient_b = 0.0
        for coordinate, direction, lo, hi in zip(start, delta, box.minimum, box.maximum):
            sample = coordinate + midpoint * direction
            if sample < lo:
                offset = coordinate - lo
            elif sample > hi:
                offset = coordinate - hi
            else:
                continue
            coefficient_a += direction * direction
            coefficient_b += 2.0 * direction * offset
        if coefficient_a > 0.0:
            candidate = -coefficient_b / (2.0 * coefficient_a)
            candidate = min(right, max(left, candidate))
            best_squared = min(best_squared, point_distance(candidate) ** 2)
        else:
            # The whole interval lies inside the box (distance zero) or has a
            # constant distance, both already covered by an endpoint.
            best_squared = min(best_squared, point_distance(midpoint) ** 2)
    return math.sqrt(max(0.0, best_squared))


def segment_surface_distance(start: Any, end: Any, *, profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                             frame: str = FRAME, units: Any = LENGTH_UNIT) -> float:
    """Return centreline segment distance to the obstacle surface in metres."""
    scene = validate_profile(profile)
    _validate_frame_units(frame, units)
    first = _point(start, "segment.start")
    last = _point(end, "segment.end")
    return _segment_aabb_distance(first, last, scene.obstacle)


def segment_clearance(start: Any, end: Any, *, profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                      frame: str = FRAME, units: Any = LENGTH_UNIT) -> float:
    """Return swept vehicle net clearance: surface distance minus radius."""
    scene = validate_profile(profile)
    return segment_surface_distance(start, end, profile=scene, frame=frame, units=units) - scene.vehicle_radius


minimum_segment_clearance = segment_clearance
swept_segment_clearance = segment_clearance


def path_clearance(points: Sequence[Any], *, profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                   frame: str = FRAME, units: Any = LENGTH_UNIT) -> float:
    """Return the minimum swept clearance over all consecutive path segments."""
    scene = validate_profile(profile)
    _validate_frame_units(frame, units)
    if type(points) not in (tuple, list) or len(points) < 2:
        raise SceneProfileError("path must contain at least two bounded points")
    normalized = tuple(_point(point, f"path[{index}]") for index, point in enumerate(points))
    return min(segment_clearance(first, last, profile=scene, frame=frame, units=units)
               for first, last in zip(normalized, normalized[1:]))


minimum_path_clearance = path_clearance


def path_meets_clearance(points: Sequence[Any], *, profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                         frame: str = FRAME, units: Any = LENGTH_UNIT) -> bool:
    scene = validate_profile(profile)
    return path_clearance(points, profile=scene, frame=frame, units=units) >= scene.required_clearance


def minimum_clearance(start: Any, end: Any, *, profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                      frame: str = FRAME, units: Any = LENGTH_UNIT) -> float:
    """Compatibility name for the swept line-segment clearance helper."""
    return segment_clearance(start, end, profile=profile, frame=frame, units=units)


def validate_clearance(points: Sequence[Any], *, profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                       frame: str = FRAME, units: Any = LENGTH_UNIT) -> bool:
    """Return whether every swept path segment meets the profile's net-clearance gate."""
    return path_meets_clearance(points, profile=profile, frame=frame, units=units)


def _validate_profile_identity(value: Mapping[str, Any], scene: SceneProfile) -> None:
    if value.get("profile_id") != scene.profile_id:
        raise ProfileMismatchError("replan profile_id does not match scene profile")
    supplied_hashes = [value[name] for name in ("profile_hash", "canonical_hash") if name in value]
    if not supplied_hashes or any(type(item) is not str or item != scene.profile_hash
                                  for item in supplied_hashes):
        raise ProfileMismatchError("replan profile_hash does not match scene profile")


@dataclass(frozen=True)
class ReplanInput:
    """Validated offline start/goal input for one planner generation."""

    profile_id: str
    profile_hash: str
    frame: str
    units: str
    start: tuple[float, float, float]
    goal: tuple[float, float, float]
    generation: int | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "profile_id": self.profile_id,
            "profile_hash": self.profile_hash,
            "frame": self.frame,
            "units": self.units,
            "start": list(self.start),
            "goal": list(self.goal),
        }
        if self.generation is not None:
            result["generation"] = self.generation
        return result


def validate_replan_input(request_or_start: Any, goal: Any | None = None, *,
                          profile: SceneProfile | Mapping[str, Any] = EGO_SINGLE_BOX_V1,
                          profile_hash: str | None = None,
                          frame: str = FRAME, units: Any = LENGTH_UNIT,
                          generation: int | None = None) -> ReplanInput:
    """Validate explicit scene identity and finite ENU metre start/goal values.

    A mapping request must carry ``profile_id`` and ``profile_hash``.  The
    positional convenience form also requires ``profile_hash`` explicitly, so a
    caller cannot silently plan against an unverified profile.
    """
    scene = validate_profile(profile)
    request: Mapping[str, Any] | None = None
    if goal is None and type(request_or_start) is dict:
        request = request_or_start
        if set(request) - {"profile_id", "profile_hash", "canonical_hash", "frame", "units",
                            "start", "goal", "generation"}:
            raise SceneProfileError("replan input contains unknown fields")
        _validate_profile_identity(request, scene)
        frame = request.get("frame")
        units = request.get("units")
        start = request.get("start")
        goal = request.get("goal")
        generation = request.get("generation", generation)
        profile_hash = request.get("profile_hash", request.get("canonical_hash"))
    else:
        start = request_or_start
        if profile_hash != scene.profile_hash:
            raise ProfileMismatchError("replan profile_hash does not match scene profile")
    _validate_frame_units(frame, units)
    if profile_hash != scene.profile_hash:
        raise ProfileMismatchError("replan profile_hash does not match scene profile")
    first = _point(start, "replan.start")
    destination = _point(goal, "replan.goal")
    if not scene.contains(first) or not scene.contains(destination):
        raise SceneProfileError("replan start and goal must lie within map bounds")
    if scene.obstacle.contains(first) or scene.obstacle.contains(destination):
        raise SceneProfileError("replan start and goal must not lie inside the obstacle")
    if generation is not None:
        if type(generation) is not int or generation < 0:
            raise SceneProfileError("generation must be a non-negative integer")
    return ReplanInput(scene.profile_id, scene.profile_hash, FRAME, LENGTH_UNIT,
                       first, destination, generation)


validate_route_request = validate_replan_input


__all__ = [
    "AABB", "CANONICAL_PROFILE_HASH", "COORDINATE_SYSTEM", "DEFAULT_PROFILE",
    "EGO_SINGLE_BOX_V1", "FRAME", "GROUND_Z", "LENGTH_UNIT", "NO_ROUTE_PROFILE",
    "NO_ROUTE_PROFILE_ID", "OBSTACLE_MAX", "OBSTACLE_MIN", "ORIGIN", "PROFILE_ID",
    "PROFILE_VERSION", "ProfileMismatchError", "ReplanInput", "REQUIRED_CLEARANCE",
    "SCENE_PROFILE", "SCENE_PROFILE_HASH", "SIZE", "SceneProfile", "SceneProfileError",
    "TIME_UNIT", "ANGLE_UNIT", "VEHICLE_RADIUS", "VOXEL_ORDER", "VOXEL_RESOLUTION",
    "canonical_profile_hash", "minimum_path_clearance", "minimum_segment_clearance",
    "minimum_clearance", "validate_clearance",
    "no_route_profile", "path_clearance", "path_meets_clearance", "segment_clearance",
    "segment_surface_distance", "swept_segment_clearance", "validate_profile",
    "validate_replan_input", "validate_route_request",
]
