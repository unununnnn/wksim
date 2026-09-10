# SPDX-License-Identifier: Apache-2.0
"""Native target publisher graph guard for ArUco flight tracking.

Validates that outgoing native target command topics (e.g. /ap/cmd_vel,
/ap/cmd_gps_pose, /wksim_px4_21/fmu/in/trajectory_setpoint) have exactly one
active DataWriter on the DDS graph, strictly owned by 'wksim_joint_<stack>_control',
with exact message type matching and invariant non-zero GID across snapshots.

Intended usage by task runner:
  - Called at ready (session start) to establish initial bound snapshot.
  - Called before every public command publication.
  - Called periodically (e.g. 1 Hz) and before final report generation.
  - Called via validate_sample(topic, gid) to reject unverified publisher samples.

No timers, no background threads, no ROS node creation.
"""

from collections.abc import Mapping, Sequence
import copy
import time
from typing import Any, Dict, List, Optional, Tuple, Union


def _normalize_gid(gid: Any) -> str:
    """Normalize GID representation (bytes, list of ints, or hex string) to lowercase hex."""
    if isinstance(gid, str):
        cleaned = gid.strip().lower()
        if not cleaned:
            raise ValueError("Empty GID string")
        return cleaned
    if isinstance(gid, (bytes, bytearray)):
        return gid.hex().lower()
    if isinstance(gid, (list, tuple)):
        return bytes(gid).hex().lower()
    raise TypeError(f"Unsupported GID type: {type(gid).__name__}")


def _is_nonzero_gid(gid_hex: str) -> bool:
    """Check whether normalized GID hex is non-empty, non-zero, and sufficiently long."""
    # This pinned ROS/RMW transport records all 24 bytes, including padding.
    if len(gid_hex) != 48 or any(c not in '0123456789abcdef' for c in gid_hex):
        return False
    return any(c != "0" for c in gid_hex)


def _deduce_type_name(spec_or_type: Any) -> str:
    """Extract standard ROS 2 type name (e.g. 'geometry_msgs/msg/TwistStamped')."""
    # 1. Check explicit type_name attribute
    type_name = getattr(spec_or_type, "type_name", None)
    if isinstance(type_name, str) and type_name:
        return type_name

    # 2. Check msg_type attribute if ChannelSpec-like
    target_type = getattr(spec_or_type, "msg_type", spec_or_type)
    if isinstance(target_type, str):
        return target_type

    # 3. Derive from class module and name
    mod = getattr(target_type, "__module__", "")
    cls_name = getattr(target_type, "__name__", str(target_type))
    pkg = mod.split(".")[0] if mod else ""
    if pkg and cls_name:
        return f"{pkg}/msg/{cls_name}"
    return cls_name


class ArucoPublisherGuard:
    """Synchronous graph guard for native target publishers."""

    def __init__(
        self,
        node: Any,
        stack: str,
        topics: Union[
            Mapping[str, Any],
            Sequence[Any],
        ],
    ) -> None:
        """Initialize guard with existing node, flight stack, and expected target topics.

        Args:
            node: ROS2 Node instance (or mock implementing get_publishers_info_by_topic).
            stack: Flight stack string ('px4' or 'arducopter').
            topics: Mapping of {topic: type_or_name} or sequence of ChannelSpecs/tuples.
        """
        if stack not in ('px4', 'arducopter'):
            raise ValueError(f"Unsupported flight stack: {stack!r}")
        self._node = node
        self._stack = stack.lower()
        self._expected_node_name = f"wksim_joint_{self._stack}_control"
        self._expected_namespace = "/"

        self._expected_topics: Dict[str, str] = {}
        if isinstance(topics, Mapping):
            for t, val in topics.items():
                self._expected_topics[str(t)] = _deduce_type_name(val)
        elif isinstance(topics, Sequence):
            for item in topics:
                if hasattr(item, "topic"):
                    self._expected_topics[str(item.topic)] = _deduce_type_name(item)
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    t, val = item[0], item[1]
                    self._expected_topics[str(t)] = _deduce_type_name(val)
                else:
                    raise ValueError(f"Cannot extract topic from specification item: {item!r}")
        else:
            raise TypeError(f"topics must be Mapping or Sequence, got {type(topics).__name__}")

        if not self._expected_topics:
            raise ValueError("topics specification must not be empty")

        self._bound_snapshot: Optional[Dict[str, Any]] = None
        self._snapshot_count = 0

    @property
    def stack(self) -> str:
        return self._stack

    @property
    def expected_node_name(self) -> str:
        return self._expected_node_name

    @property
    def expected_topics(self) -> Dict[str, str]:
        return dict(self._expected_topics)

    @property
    def is_bound(self) -> bool:
        return self._bound_snapshot is not None

    @property
    def bound_snapshot(self) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._bound_snapshot)

    def snapshot(self) -> Dict[str, Any]:
        """Query discovery graph for each target topic and verify publisher integrity.

        On first invocation:
          - Asserts exactly 1 publisher per topic.
          - Asserts publisher node_name == 'wksim_joint_<stack>_control'.
          - Asserts publisher namespace == '/'.
          - Asserts message type matches expected ChannelSpec type.
          - Asserts GID is complete, non-zero, and valid.
          - Binds the initial graph topology with monotonic timestamp.

        On subsequent invocations:
          - Re-queries the graph for all topics.
          - Asserts strict equality against the initially bound topology.
          - Raises ValueError immediately on missing publisher, second publisher,
            or changed GID.

        Returns:
            Dictionary containing node_name, stack, monotonic timestamps, snapshot
            index, and per-topic endpoint information.
        """
        now_ns = time.monotonic_ns()
        now_s = time.monotonic()
        current_topics: Dict[str, Dict[str, str]] = {}

        for topic, expected_type in self._expected_topics.items():
            publishers = self._node.get_publishers_info_by_topic(topic)
            if not publishers:
                raise ValueError(
                    f"Native target topic {topic!r} has no publishers (expected exactly 1)"
                )
            if len(publishers) > 1:
                # Catch silent second publishers or multiple writers
                other_names = [getattr(p, "node_name", "unknown") for p in publishers]
                raise ValueError(
                    f"Native target topic {topic!r} has multiple publishers ({len(publishers)} found: {other_names})"
                )

            info = publishers[0]
            node_name = getattr(info, "node_name", None)
            if node_name != self._expected_node_name:
                raise ValueError(
                    f"Topic {topic!r} publisher node_name {node_name!r} != expected {self._expected_node_name!r}"
                )

            namespace = getattr(info, "node_namespace", None)
            if namespace != self._expected_namespace:
                raise ValueError(
                    f"Topic {topic!r} publisher node_namespace {namespace!r} != expected {self._expected_namespace!r}"
                )

            actual_type = (
                getattr(info, "topic_type", None)
                or getattr(info, "message_type", None)
                or getattr(info, "type_name", None)
            )
            if actual_type != expected_type:
                raise ValueError(
                    f"Topic {topic!r} message type {actual_type!r} != expected {expected_type!r}"
                )

            raw_gid = getattr(info, "endpoint_gid", None)
            gid_hex = _normalize_gid(raw_gid)
            if not _is_nonzero_gid(gid_hex):
                raise ValueError(
                    f"Topic {topic!r} publisher has zero or incomplete GID: {gid_hex!r}"
                )

            current_topics[topic] = {
                "publisher_count": len(publishers),
                "node_name": node_name,
                "node_namespace": namespace,
                "type_name": actual_type,
                "endpoint_gid": gid_hex,
            }

        self._snapshot_count += 1

        # Initial binding on first snapshot
        if self._bound_snapshot is None:
            self._bound_snapshot = {
                "node_name": self._expected_node_name,
                "stack": self._stack,
                "monotonic_ns": now_ns,
                "monotonic_s": now_s,
                "snapshot_index": self._snapshot_count,
                "topics": current_topics,
            }
            return copy.deepcopy(self._bound_snapshot)

        # Invariant verification on subsequent snapshots
        bound_topics = self._bound_snapshot["topics"]
        for topic, bound_ep in bound_topics.items():
            curr_ep = current_topics.get(topic)
            if curr_ep is None:
                raise ValueError(f"Guarded topic {topic!r} missing in subsequent snapshot")
            if curr_ep["endpoint_gid"] != bound_ep["endpoint_gid"]:
                raise ValueError(
                    f"Topic {topic!r} publisher GID changed across snapshots: "
                    f"bound={bound_ep['endpoint_gid']!r}, current={curr_ep['endpoint_gid']!r}"
                )
            if curr_ep["node_name"] != bound_ep["node_name"]:
                raise ValueError(
                    f"Topic {topic!r} publisher node_name changed across snapshots: "
                    f"bound={bound_ep['node_name']!r}, current={curr_ep['node_name']!r}"
                )
            if curr_ep["type_name"] != bound_ep["type_name"]:
                raise ValueError(
                    f"Topic {topic!r} publisher type_name changed across snapshots: "
                    f"bound={bound_ep['type_name']!r}, current={curr_ep['type_name']!r}"
                )

        return {
            "node_name": self._expected_node_name,
            "stack": self._stack,
            "monotonic_ns": now_ns,
            "monotonic_s": now_s,
            "snapshot_index": self._snapshot_count,
            "topics": current_topics,
        }

    def validate_sample(self, topic: str, gid: Any) -> bool:
        """Validate an incoming or recorded sample against the bound publisher GID.

        Args:
            topic: Topic string.
            gid: Sample's publisher_gid (hex string, bytes, or int sequence).

        Returns:
            True if publisher GID matches the bound publisher.

        Raises:
            ValueError: If guard is not bound, topic is unmanaged, or GID does not match.
        """
        if self._bound_snapshot is None:
            raise ValueError(
                "Cannot validate sample: publisher guard has not performed initial snapshot/binding"
            )

        str_topic = str(topic)
        if str_topic not in self._expected_topics:
            raise ValueError(
                f"Cannot validate sample: topic {str_topic!r} is not a guarded native target topic "
                f"(managed: {list(self._expected_topics.keys())})"
            )

        gid_hex = _normalize_gid(gid)
        expected_gid = self._bound_snapshot["topics"][str_topic]["endpoint_gid"]

        if gid_hex != expected_gid:
            raise ValueError(
                f"Rejected sample on topic {str_topic!r}: publisher GID {gid_hex!r} "
                f"does not match bound Control GID {expected_gid!r}"
            )

        return True
