#!/usr/bin/env python3
"""Publish the frozen EGO profile as a finite ROS1 PointCloud2 stream.

This helper owns only the scene point cloud.  It deliberately does not publish
odometry or control state, start a ROS master, start a planner, or claim flight
or clearance evidence.  The profile is expressed in ``map`` coordinates; the
ROS1 contract uses ``world`` as the same-origin, same-axis alias.

The pure payload helpers stay importable on hosts without ROS.  ROS imports are
kept inside ``publish`` so the offline payload tests do not require a ROS
installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
from typing import Iterable, Sequence
from urllib.parse import urlparse

try:
    from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1, SceneProfile
except ModuleNotFoundError:
    # ``python tools/publish_ego_profile_scene.py`` puts ``tools/`` first on
    # sys.path; add the repository root for direct CLI use without changing
    # the package's import layout.
    repository_root = str(Path(__file__).resolve().parents[1])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1, SceneProfile


TOPIC = "/map_generator/global_cloud"
FRAME_ALIAS = "world"
POINT_STEP_XYZ32 = 12
POINT_FIELD_FLOAT32 = 7  # sensor_msgs/PointField.FLOAT32
DEFAULT_RATE_HZ = 10.0
DEFAULT_SUBSCRIBER_TIMEOUT_S = 5.0
WALL_SLEEP_QUANTUM_S = 0.05


Point = tuple[float, float, float]
VoxelIndex = tuple[int, int, int]


class PayloadMismatchError(ValueError):
    """Raised when a PointCloud2 message does not encode the frozen profile."""


def _finite_positive(value: str) -> float:
    """Parse a finite positive CLI number."""

    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a finite positive number") from error
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return parsed


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def voxel_set_hash(indices: Iterable[VoxelIndex]) -> str:
    """Hash the sorted reconstructed voxel set, independent of float bytes.

    This is intentionally a set hash with its own schema.  It is not the
    profile's canonical ``voxel_hash`` and is never used as a float32 byte hash.
    """

    canonical_indices = sorted(set(tuple(int(axis) for axis in index) for index in indices))
    return hashlib.sha256(_canonical_json(canonical_indices)).hexdigest()


def float32_round_trip(points: Iterable[Sequence[float]]) -> tuple[Point, ...]:
    """Return the exact XYZ values represented by a ROS XYZ float32 payload."""

    return tuple(
        tuple(struct.unpack("<fff", struct.pack("<fff", *(float(coord) for coord in point))))
        for point in points
    )


def _pack_point(point: Sequence[float]) -> bytes:
    if len(point) != 3:
        raise ValueError("each point must contain exactly three coordinates")
    return struct.pack("<fff", float(point[0]), float(point[1]), float(point[2]))


def pack_xyz32(points: Iterable[Sequence[float]]) -> bytes:
    """Encode XYZ points exactly as sensor_msgs/PointCloud2 XYZ float32 fields."""

    return b"".join(_pack_point(point) for point in points)


def decode_xyz32(data: bytes, *, point_step: int = POINT_STEP_XYZ32,
                 count: int | None = None) -> tuple[Point, ...]:
    """Decode contiguous little-endian XYZ float32 fields from a PointCloud2."""

    if point_step < POINT_STEP_XYZ32:
        raise ValueError("point_step must contain x/y/z float32 fields")
    if len(data) % point_step != 0:
        raise ValueError("PointCloud2 data length is not aligned to point_step")
    available = len(data) // point_step
    if count is None:
        count = available
    if count < 0 or count > available:
        raise ValueError("PointCloud2 count is outside the data payload")
    return tuple(
        tuple(struct.unpack_from("<fff", data, offset=index * point_step))
        for index in range(count)
    )


def point_to_voxel_index(point: Sequence[float], profile: SceneProfile = EGO_SINGLE_BOX_V1) -> VoxelIndex:
    """Map an XYZ point to the profile's x,y,z voxel index using floor."""

    if len(point) != 3:
        raise ValueError("point must contain exactly three coordinates")
    return tuple(
        math.floor((float(coordinate) - origin) / profile.voxel_resolution)
        for coordinate, origin in zip(point, profile.origin)
    )  # type: ignore[return-value]


def source_points(profile: SceneProfile = EGO_SINGLE_BOX_V1) -> tuple[Point, ...]:
    """Read the point cloud from the profile's public API and validate count."""

    points = tuple(tuple(float(coordinate) for coordinate in point)
                   for point in profile.point_cloud())
    if len(points) != 11000:
        raise ValueError(f"profile point count changed: expected 11000, got {len(points)}")
    return points


def validate_pointcloud_message(message: object,
                                profile: SceneProfile = EGO_SINGLE_BOX_V1) -> tuple[Point, ...]:
    """Fail closed unless a PointCloud2 has the exact frozen XYZ32 payload.

    The validation deliberately inspects the message produced by ROS rather
    than trusting the source points used to construct it.  This catches field
    layout, shape, byte-order, and float32 reconstruction changes before the
    first message can be published.
    """

    expected_points = source_points(profile)
    expected_indices = tuple(profile.voxel_indices())
    if len(expected_indices) != len(expected_points):
        raise PayloadMismatchError(
            f"profile voxel count changed: expected {len(expected_points)}, "
            f"got {len(expected_indices)}"
        )

    header = getattr(message, "header", None)
    if getattr(header, "frame_id", None) != FRAME_ALIAS:
        raise PayloadMismatchError(f"PointCloud2 frame must be {FRAME_ALIAS!r}")

    expected_fields = (
        ("x", 0, POINT_FIELD_FLOAT32, 1),
        ("y", 4, POINT_FIELD_FLOAT32, 1),
        ("z", 8, POINT_FIELD_FLOAT32, 1),
    )
    fields = tuple(getattr(message, "fields", ()))
    actual_fields = tuple(
        (
            getattr(field, "name", None),
            getattr(field, "offset", None),
            getattr(field, "datatype", None),
            getattr(field, "count", None),
        )
        for field in fields
    )
    if actual_fields != expected_fields:
        raise PayloadMismatchError(
            f"PointCloud2 fields must be XYZ float32 at offsets 0/4/8, got {actual_fields!r}"
        )
    if getattr(message, "is_bigendian", None) is not False:
        raise PayloadMismatchError("PointCloud2 must use little-endian float32 data")
    if getattr(message, "point_step", None) != POINT_STEP_XYZ32:
        raise PayloadMismatchError(
            f"PointCloud2 point_step must be {POINT_STEP_XYZ32}, "
            f"got {getattr(message, 'point_step', None)!r}"
        )

    expected_count = len(expected_points)
    width = getattr(message, "width", None)
    height = getattr(message, "height", None)
    if width != expected_count or height != 1:
        raise PayloadMismatchError(
            f"PointCloud2 shape must be {expected_count}x1, got {width!r}x{height!r}"
        )
    expected_row_step = expected_count * POINT_STEP_XYZ32
    if getattr(message, "row_step", None) != expected_row_step:
        raise PayloadMismatchError(
            f"PointCloud2 row_step must be {expected_row_step}, "
            f"got {getattr(message, 'row_step', None)!r}"
        )
    data = getattr(message, "data", None)
    if data is None or len(data) != expected_row_step:
        raise PayloadMismatchError(
            f"PointCloud2 data must contain {expected_row_step} bytes, "
            f"got {0 if data is None else len(data)}"
        )

    try:
        decoded_points = decode_xyz32(
            data,
            point_step=message.point_step,
            count=width * height,
        )
    except (TypeError, ValueError, struct.error) as error:
        raise PayloadMismatchError(f"PointCloud2 XYZ32 payload is invalid: {error}") from error
    if len(decoded_points) != expected_count:
        raise PayloadMismatchError(
            f"PointCloud2 point count must be {expected_count}, got {len(decoded_points)}"
        )
    try:
        actual_indices = tuple(point_to_voxel_index(point, profile) for point in decoded_points)
    except (ValueError, OverflowError) as error:
        raise PayloadMismatchError(
            f"PointCloud2 float32 payload has non-finite coordinates: {error}"
        ) from error
    if set(actual_indices) != set(expected_indices):
        raise PayloadMismatchError(
            "PointCloud2 float32 reconstruction does not match the profile voxel set"
        )
    return decoded_points


def payload_identity(profile: SceneProfile = EGO_SINGLE_BOX_V1) -> dict[str, object]:
    """Return offline identity and float32-reconstructed voxel evidence."""

    points = source_points(profile)
    source_indices = tuple(profile.voxel_indices())
    message_points = float32_round_trip(points)
    message_indices = tuple(point_to_voxel_index(point, profile) for point in message_points)
    message_set = set(message_indices)
    source_set = set(source_indices)
    return {
        "profile_id": profile.profile_id,
        "profile_hash": profile.profile_hash,
        "voxel_hash": profile.voxel_hash,
        "source_voxel_set_hash": voxel_set_hash(source_indices),
        "message_voxel_set_hash": voxel_set_hash(message_indices),
        "message_matches_source_voxel_set": message_set == source_set,
        "point_count": len(points),
        "message_point_count": len(message_points),
        "frame_alias": FRAME_ALIAS,
        "topic": TOPIC,
    }


def _parse_master_uri(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("must be an http(s) ROS master URI")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master-uri", required=True, type=_parse_master_uri,
                        help="ROS1 master URI, for example http://127.0.0.1:11311")
    parser.add_argument("--duration", required=True, type=_finite_positive,
                        help="finite publish duration in seconds")
    parser.add_argument("--rate", type=_finite_positive, default=DEFAULT_RATE_HZ,
                        help=f"publish rate in Hz (default: {DEFAULT_RATE_HZ:g})")
    parser.add_argument("--subscriber-timeout", type=_finite_positive,
                        default=DEFAULT_SUBSCRIBER_TIMEOUT_S,
                        help=f"finite wait for a subscriber (default: {DEFAULT_SUBSCRIBER_TIMEOUT_S:g}s)")
    return parser


def _sleep_until_wall(deadline: float) -> None:
    """Sleep against the wall clock in bounded chunks so shutdown is observed."""

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return
        time.sleep(min(remaining, WALL_SLEEP_QUANTUM_S))


def publish(args: argparse.Namespace) -> dict[str, object]:
    """Publish profile points after a subscriber connects, then stop."""

    os.environ["ROS_MASTER_URI"] = args.master_uri

    # Keep ROS imports runtime-only so payload generation and tests work offline.
    import rospy  # type: ignore
    import sensor_msgs.point_cloud2 as point_cloud2  # type: ignore
    from sensor_msgs.msg import PointCloud2  # type: ignore
    from std_msgs.msg import Header  # type: ignore

    profile = EGO_SINGLE_BOX_V1
    points = source_points(profile)
    message_points = float32_round_trip(points)

    rospy.init_node("ego_profile_scene_publisher", anonymous=False)
    use_sim_time = bool(rospy.get_param("/use_sim_time", False))
    publisher = rospy.Publisher(TOPIC, PointCloud2, queue_size=1, latch=True)

    header = Header(frame_id=FRAME_ALIAS)
    message = point_cloud2.create_cloud_xyz32(header, message_points)
    decoded_message_points = validate_pointcloud_message(message, profile)

    wait_deadline = time.monotonic() + args.subscriber_timeout
    while publisher.get_num_connections() == 0:
        if rospy.is_shutdown():
            raise RuntimeError("ROS shutdown while waiting for PointCloud2 subscriber")
        if time.monotonic() >= wait_deadline:
            raise TimeoutError(f"no subscriber connected to {TOPIC} within {args.subscriber_timeout:g}s")
        _sleep_until_wall(min(wait_deadline, time.monotonic() + WALL_SLEEP_QUANTUM_S))
    if rospy.is_shutdown():
        raise RuntimeError("ROS shutdown before PointCloud2 publishing started")
    message_indices = tuple(point_to_voxel_index(point, profile)
                            for point in decoded_message_points)
    source_indices = tuple(profile.voxel_indices())
    summary = payload_identity(profile)
    summary.update({
        "message_voxel_set_hash": voxel_set_hash(message_indices),
        "message_matches_source_voxel_set": set(message_indices) == set(source_indices),
        "message_point_count": len(decoded_message_points),
        "published_count": 0,
        "use_sim_time": use_sim_time,
    })

    publish_start = time.monotonic()
    publish_deadline = publish_start + args.duration
    next_publish = publish_start
    published_count = 0
    while time.monotonic() < publish_deadline:
        if rospy.is_shutdown():
            raise RuntimeError(
                f"ROS shutdown before publish duration elapsed; published {published_count} message(s)"
            )
        message.header.stamp = rospy.Time.now()
        publisher.publish(message)
        published_count += 1
        next_publish += 1.0 / args.rate
        _sleep_until_wall(min(next_publish, publish_deadline))
        if rospy.is_shutdown() and time.monotonic() < publish_deadline:
            raise RuntimeError(
                f"ROS shutdown before publish duration elapsed; published {published_count} message(s)"
            )
    if published_count == 0:
        raise RuntimeError("publish duration elapsed without publishing a PointCloud2 message")
    summary["published_count"] = published_count
    summary["duration_s"] = args.duration
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = publish(args)
    except (ImportError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"publish_ego_profile_scene: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
