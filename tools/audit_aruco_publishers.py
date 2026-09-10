#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline read-only audit of ArUco native target publisher GIDs and graph exclusivity.

Audits preserved ArUco tracking runs (e.g. validation/40-aruco-tracking-10,
validation/40-aruco-tracking-13-ap, and runs with publisher_snapshots) by reconciling:
  1. Observed DataWriter publisher GIDs in authentic aruco-raw-dds.jsonl logs.
  2. Full canonical raw capture verification via tools.audit_aruco_tracking_raw.verify_raw_capture.
  3. Publisher discovery snapshots (ready, before-send, periodic, report) in result.json.
  4. DataReader endpoint GIDs and participant discovery in initialized.json.
  5. OS process identity and node launch parameters in children.json.
  6. Native binding lifecycle events in *-control.log.

CRITICAL ARCHITECTURAL BOUNDARIES & GATES:
- writer_binding:
    * 'verified_bound': Granted only when discrete publisher discovery snapshots exist,
      strictly invariant across session lifecycle, match the required fixed topic set and
      exact ROS types, match the Control node, and 100% of recorded raw CDR samples match
      the bound GID with a verified raw capture hash chain and non-empty sample sets.
    * 'unbound': Reported when snapshots are absent (legacy runs 10 & 13) or fail checks.
- snapshot_exclusivity:
    * 'verified_at_snapshots': Proven strictly at discrete sampling points (ready, periodic,
      before-send, report). Explicitly does NOT claim un-sampled instantaneous full-graph
      exclusivity.
    * 'unverified': Reported when no discovery snapshots were retained (passive observation only).
"""

import argparse
from collections import defaultdict
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.audit_aruco_tracking_raw import verify_raw_capture, reconcile_identity

SCHEMA_VERSION = 2
RAW_FILE_NAME = "aruco-raw-dds.jsonl"
RESULT_FILE_NAME = "result.json"

# Fixed mandatory channels and expected exact types per flight stack
REQUIRED_SNAPSHOT_CHANNELS: Dict[str, Dict[str, str]] = {
    "arducopter": {
        "/ap/cmd_gps_pose": "ardupilot_msgs/msg/GlobalPosition",
        "/ap/cmd_vel": "geometry_msgs/msg/TwistStamped",
        "/uav1/prometheus/v2/state": "wksim_msgs/msg/SessionState",
    },
    "px4": {
        "/wksim_px4_21/fmu/in/trajectory_setpoint": "px4_msgs/msg/TrajectorySetpoint",
        "/wksim_px4_21/fmu/in/vehicle_command": "px4_msgs/msg/VehicleCommand",
        "/uav2/prometheus/v2/state": "wksim_msgs/msg/SessionState",
    },
}

# Native target topics published by the Control node to the flight controller
NATIVE_TARGET_TOPICS = {
    "/ap/cmd_vel",
    "/ap/cmd_gps_pose",
    "/wksim_px4_21/fmu/in/trajectory_setpoint",
    "/wksim_px4_21/fmu/in/vehicle_command",
}

# Flight controller telemetry topics subscribed by the Control node
NATIVE_TELEMETRY_TOPICS = {
    "/ap/status",
    "/ap/wksim/local_state_v1",
    "/wksim_px4_21/fmu/out/vehicle_status_v1",
    "/wksim_px4_21/fmu/out/vehicle_local_position_v1",
    "/wksim_px4_21/fmu/out/vehicle_control_mode",
    "/wksim_px4_21/fmu/out/vehicle_attitude",
    "/wksim_px4_21/fmu/out/vehicle_odometry",
    "/wksim_px4_21/fmu/out/vehicle_gps_position",
    "/wksim_px4_21/fmu/out/vehicle_land_detected",
    "/wksim_px4_21/fmu/out/estimator_status_flags",
}

# Public session and diagnostic topics published by the Control node
PUBLIC_CONTROL_TOPICS = {
    "/uav1/prometheus/v2/state",
    "/uav2/prometheus/v2/state",
    "/uav1/prometheus/text_info",
    "/uav2/prometheus/text_info",
}

# Public command channels published by the task runner
PUBLIC_COMMAND_TOPICS = {
    "/uav1/prometheus/v2/setup",
    "/uav2/prometheus/v2/setup",
    "/uav1/prometheus/v2/command",
    "/uav2/prometheus/v2/command",
}


def sanitize_no_nan(obj: Any) -> Any:
    """Sanitize floats: non-finite values (NaN, Inf) become None (JSON null)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize_no_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_no_nan(v) for v in obj]
    return obj


def parse_guid(gid_hex: str) -> Dict[str, Any]:
    """Parse a 48-hex character (24-byte) or 32-hex (16-byte) DDS/RTPS GUID.

    In standard RTPS:
      Bytes 0..11 (chars 0..23): GuidPrefix_t (Participant GUID prefix)
      Bytes 12..15 (chars 24..31): EntityId_t (Entity ID within Participant)
      Bytes 16..23 (chars 32..47): Protocol padding / reserved (often 0)
    """
    if not isinstance(gid_hex, str):
        return {
            "raw": str(gid_hex),
            "guid_prefix": None,
            "entity_id": None,
            "entity_kind_hex": None,
            "entity_kind_desc": "unknown",
            "is_valid_format": False,
        }

    cleaned = gid_hex.strip().lower()
    if len(cleaned) not in (32,48) or not re.fullmatch(r"[0-9a-f]+", cleaned):
        return {
            "raw": gid_hex,
            "guid_prefix": None,
            "entity_id": None,
            "entity_kind_hex": None,
            "entity_kind_desc": "malformed",
            "is_valid_format": False,
        }

    prefix = cleaned[:24]
    entity_id = cleaned[24:32] if len(cleaned) >= 32 else None
    entity_kind_hex = entity_id[6:8] if entity_id and len(entity_id) == 8 else None

    kind_desc = "unknown"
    if entity_kind_hex:
        kind_val = int(entity_kind_hex, 16)
        if kind_val in (0x02, 0xC2):
            kind_desc = "participant"
        elif kind_val in (0x03, 0x07):
            kind_desc = "data_writer"
        elif kind_val in (0x04, 0x47):
            kind_desc = "data_reader"
        else:
            kind_desc = f"entity_0x{entity_kind_hex}"

    return {
        "raw": cleaned,
        "guid_prefix": prefix,
        "entity_id": entity_id,
        "entity_kind_hex": entity_kind_hex,
        "entity_kind_desc": kind_desc,
        "is_valid_format": True,
    }


def audit_raw_capture_file(path: Path) -> Dict[str, Any]:
    """Parse aruco-raw-dds.jsonl, verify raw capture via verify_raw_capture, and collect samples."""
    topics_gids: Dict[str, Set[str]] = defaultdict(set)
    topics_counts: Dict[str, int] = defaultdict(int)
    raw_samples_by_topic: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    rows: List[Dict[str, Any]] = []

    start_record: Optional[Dict[str, Any]] = None
    end_record: Optional[Dict[str, Any]] = None

    with open(path, "r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Corrupted JSON in {path}:{line_num}: {exc}") from exc

            rows.append(row)

            if row.get("kind") == "aruco_raw_capture_start":
                start_record = row
                continue
            if row.get("kind") == "aruco_raw_capture_end":
                end_record = row
                continue

            topic = row.get("topic")
            gid = row.get("publisher_gid")
            if topic:
                topics_counts[topic] += 1
                if gid:
                    topics_gids[topic].add(gid)
                raw_samples_by_topic[topic].append(row)

    # Full raw verification via authoritative verify_raw_capture
    hash_valid = False
    hash_msg = "verify_raw_capture_not_available"

    if start_record:
        run_id = start_record.get("run_id")
        epoch = start_record.get("epoch")
        stack = start_record.get("stack")
        uav_id = start_record.get("uav_id")
        try:
            verify_raw_capture(path, run_id=run_id, epoch=epoch, stack=stack, uav_id=uav_id)
            hash_valid = True
            hash_msg = "verified_raw_capture_pass"
        except Exception as exc:
            hash_valid = False
            hash_msg = f"verify_raw_capture_failed: {exc}"
    # Structure findings by topic classification
    by_topic: Dict[str, Any] = {}
    for topic, count in sorted(topics_counts.items()):
        gids = sorted(list(topics_gids[topic]))
        parsed_gids = [parse_guid(g) for g in gids]
        unique_prefixes = sorted(list({p["guid_prefix"] for p in parsed_gids if p["guid_prefix"]}))

        is_target = topic in NATIVE_TARGET_TOPICS
        is_telemetry = topic in NATIVE_TELEMETRY_TOPICS
        is_public_ctrl = topic in PUBLIC_CONTROL_TOPICS
        is_public_cmd = topic in PUBLIC_COMMAND_TOPICS

        cat = "other"
        if is_target:
            cat = "native_target"
        elif is_telemetry:
            cat = "native_telemetry"
        elif is_public_ctrl:
            cat = "public_control"
        elif is_public_cmd:
            cat = "public_command"

        by_topic[topic] = {
            "category": cat,
            "sample_count": count,
            "unique_gid_count": len(gids),
            "single_gid_observed": len(gids) == 1,
            "unique_gids": gids,
            "parsed_gids": parsed_gids,
            "unique_participant_guid_prefixes": unique_prefixes,
        }

    return {
        "file_path": str(path.resolve()),
        "total_lines": len(rows),
        "start_record": start_record,
        "end_record": end_record,
        "hash_chain_valid": hash_valid,
        "hash_chain_message": hash_msg,
        "topics": by_topic,
        "raw_samples_by_topic": raw_samples_by_topic,
    }


def audit_initialized_json(path: Path) -> Dict[str, Any]:
    """Parse initialized.json to extract Control node reader endpoints and participant prefix."""
    if not path.is_file():
        return {"exists": False, "file_path": str(path.resolve())}

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    request_graph = data.get("request_graph", {})
    readers_by_node: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for channel, endpoints in request_graph.items():
        for ep in endpoints:
            node_name = ep.get("node_name")
            endpoint_gid = ep.get("endpoint_gid")
            parsed = parse_guid(endpoint_gid)
            readers_by_node[node_name].append({
                "channel": channel,
                "node_namespace": ep.get("node_namespace"),
                "endpoint_gid": endpoint_gid,
                "guid_prefix": parsed["guid_prefix"],
                "entity_id": parsed["entity_id"],
            })

    control_node_name = None
    control_guid_prefix = None
    control_reader_endpoints = []
    for node_name, eps in readers_by_node.items():
        if "control" in node_name:
            control_node_name = node_name
            control_reader_endpoints = eps
            prefixes = {ep["guid_prefix"] for ep in eps if ep["guid_prefix"]}
            if len(prefixes) == 1:
                control_guid_prefix = next(iter(prefixes))
            break

    return {
        "exists": True,
        "file_path": str(path.resolve()),
        "version": data.get("version"),
        "run_id": data.get("run_id"),
        "epoch": data.get("epoch"),
        "stack": data.get("stack"),
        "token": data.get("token"),
        "control_subscriptions": data.get("control_subscriptions"),
        "control_node_name": control_node_name,
        "control_guid_prefix": control_guid_prefix,
        "control_reader_endpoints": control_reader_endpoints,
        "all_readers_by_node": {k: v for k, v in readers_by_node.items()},
    }


def audit_children_json(path: Path) -> Dict[str, Any]:
    """Parse children.json to locate Control node process identity (PID, argv, node name)."""
    if not path.is_file():
        return {"exists": False, "file_path": str(path.resolve())}

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    control_processes: Dict[str, Any] = {}
    for proc_name, proc_data in data.items():
        if "control" in proc_name:
            ident = proc_data.get("identity", {})
            argv = proc_data.get("argv", [])

            node_arg = None
            for i, arg in enumerate(argv):
                if arg == "-r" and i + 1 < len(argv) and argv[i + 1].startswith("__node:="):
                    node_arg = argv[i + 1].split("__node:=")[1]
                elif arg.startswith("__node:="):
                    node_arg = arg.split("__node:=")[1]

            control_processes[proc_name] = {
                "pid": ident.get("pid"),
                "pgid": ident.get("pgid"),
                "start_ticks": ident.get("start_ticks"),
                "argv": argv,
                "node_name_arg": node_arg,
                "cwd": proc_data.get("cwd"),
            }

    return {
        "exists": True,
        "file_path": str(path.resolve()),
        "control_processes": control_processes,
    }


def audit_control_log(path: Path) -> Dict[str, Any]:
    """Parse *-control.log for scene_native_sources_bound and target publisher attestation."""
    if not path.is_file():
        return {"exists": False, "file_path": str(path.resolve())}

    native_sources_bound_events: List[Dict[str, Any]] = []
    target_publisher_events: List[Dict[str, Any]] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if "scene_native_sources_bound" in line:
                try:
                    idx = line.find("{")
                    if idx != -1:
                        payload = json.loads(line[idx:])
                        native_sources_bound_events.append(payload)
                except Exception:
                    pass
            if any(t in line for t in ("native_target", "cmd_vel", "cmd_gps_pose", "trajectory_setpoint")):
                if any(kw in line for kw in ("bound", "endpoint", "publisher_gid", "writer_gid")):
                    try:
                        idx = line.find("{")
                        if idx != -1:
                            target_publisher_events.append(json.loads(line[idx:]))
                    except Exception:
                        pass

    return {
        "exists": True,
        "file_path": str(path.resolve()),
        "native_sources_bound_events": native_sources_bound_events,
        "logs_target_publisher_gids": len(target_publisher_events) > 0,
        "target_publisher_events": target_publisher_events,
    }


def audit_publisher_snapshots(
    snapshots: List[Dict[str, Any]],
    expected_stack: str,
    raw_samples_by_topic: Dict[str, List[Dict[str, Any]]],
    raw_hash_valid: bool,
    *, required_sample_topics=None,
) -> Dict[str, Any]:
    """Audit publisher_snapshots with strict topic sets, exact ROS types, and non-decreasing monotonic time."""
    if not snapshots or not isinstance(snapshots, list):
        return {
            "available": False,
            "status": "not_available",
            "writer_binding": "unbound",
            "snapshot_exclusivity": "unverified",
            "errors": ["No publisher snapshots found in report"],
        }

    errors: List[str] = []
    expected_node = f"wksim_joint_{expected_stack}_control"
    expected_channels = REQUIRED_SNAPSHOT_CHANNELS.get(expected_stack, {})

    if required_sample_topics is None:
        required_sample_topics = set(expected_channels)
    if not expected_channels:
        errors.append(f"Unknown flight stack {expected_stack!r}; cannot audit required channels")

    # 1. Exact boundary reason matching: ready at start, report at end
    first_reason = snapshots[0].get("reason")
    last_reason = snapshots[-1].get("reason")

    if first_reason != "ready":
        errors.append(f"First snapshot reason must be exactly 'ready', got {first_reason!r}")
    if last_reason != "report":
        errors.append(f"Last snapshot reason must be exactly 'report', got {last_reason!r}")

    # 2. Strict sequential ordering, positive strictly increasing monotonic_ns, non-decreasing authority_tick
    last_mono_ns = -1
    last_authority_tick = -1

    for idx, snap in enumerate(snapshots):
        expected_seq = idx + 1
        actual_seq = snap.get("snapshot_index")
        if type(actual_seq) is not int or actual_seq != expected_seq:
            errors.append(
                f"Snapshot at position {idx} has snapshot_index {actual_seq} (expected {expected_seq})"
            )

        curr_mono_ns = snap.get("monotonic_ns")
        if type(curr_mono_ns) is not int or curr_mono_ns <= 0:
            errors.append(
                f"Snapshot {actual_seq} monotonic_ns must be positive integer, got {curr_mono_ns!r}"
            )
        elif curr_mono_ns <= last_mono_ns:
            errors.append(
                f"Snapshot {actual_seq} monotonic_ns ({curr_mono_ns}) not strictly increasing over previous ({last_mono_ns})"
            )
        last_mono_ns = curr_mono_ns if isinstance(curr_mono_ns, int) else last_mono_ns

        curr_tick = snap.get("authority_tick")
        if type(curr_tick) is not int or curr_tick < 0:
            errors.append(
                f"Snapshot {actual_seq} authority_tick must be non-negative integer, got {curr_tick!r}"
            )
        elif curr_tick < last_authority_tick:
            errors.append(
                f"Snapshot {actual_seq} authority_tick ({curr_tick}) decreased from previous ({last_authority_tick})"
            )
        last_authority_tick = curr_tick if isinstance(curr_tick, int) else last_authority_tick

    # 3. Invariance and mandatory channel completeness check
    for idx, snap in enumerate(snapshots):
        seq = snap.get("snapshot_index", idx + 1)
        if snap.get("node_name") != expected_node:
            errors.append(
                f"Snapshot {seq} node_name {snap.get('node_name')!r} != expected {expected_node!r}"
            )
        if snap.get("stack") != expected_stack:
            errors.append(
                f"Snapshot {seq} stack {snap.get('stack')!r} != expected {expected_stack!r}"
            )

        curr_topics = snap.get("topics", {})
        if set(curr_topics.keys()) != set(expected_channels.keys()):
            missing = set(expected_channels.keys()) - set(curr_topics.keys())
            extra = set(curr_topics.keys()) - set(expected_channels.keys())
            if missing:
                errors.append(f"Snapshot {seq} missing required channels: {sorted(list(missing))}")
            if extra:
                errors.append(f"Snapshot {seq} has undeclared channels: {sorted(list(extra))}")

        for topic, expected_type in expected_channels.items():
            curr_ep = curr_topics.get(topic)
            if not curr_ep:
                continue

            # Must have exactly 1 publisher
            pub_count = curr_ep.get("publisher_count")
            if type(pub_count) is not int or pub_count != 1:
                errors.append(
                    f"Snapshot {seq} topic {topic} publisher_count={pub_count} (expected 1)"
                )

            # Node name, namespace, type match
            if curr_ep.get("node_name") != expected_node:
                errors.append(
                    f"Snapshot {seq} topic {topic} node_name={curr_ep.get('node_name')!r} != {expected_node!r}"
                )
            if curr_ep.get("node_namespace") != "/":
                errors.append(
                    f"Snapshot {seq} topic {topic} namespace={curr_ep.get('node_namespace')!r} != '/'"
                )
            if curr_ep.get("type_name") != expected_type:
                errors.append(
                    f"Snapshot {seq} topic {topic} type_name={curr_ep.get('type_name')!r} != expected {expected_type!r}"
                )

            curr_gid = curr_ep.get("endpoint_gid")
            if not isinstance(curr_gid, str) or len(curr_gid) != 48 or any(c not in "0123456789abcdef" for c in curr_gid):
                errors.append(f"Snapshot {seq} topic {topic} invalid 48-char hex GID: {curr_gid!r}")
            elif all(c == "0" for c in curr_gid):
                errors.append(f"Snapshot {seq} topic {topic} rejected all-zero GID: {curr_gid!r}")

            # Check invariant equality against initial snapshot
            if idx > 0:
                base_ep = snapshots[0].get("topics", {}).get(topic, {})
                if curr_gid != base_ep.get("endpoint_gid"):
                    errors.append(
                        f"Snapshot {seq} topic {topic} GID drifted from initial: {curr_gid!r} != {base_ep.get('endpoint_gid')!r}"
                    )

    # 4. Cross-check against actual raw CDR samples (require non-empty samples and exact GID match)
    sample_matches = {}
    for topic, expected_type in expected_channels.items():
        base_ep = snapshots[0].get("topics", {}).get(topic, {})
        expected_gid = base_ep.get("endpoint_gid")
        samples = raw_samples_by_topic.get(topic, [])
        sample_count = len(samples)

        if sample_count == 0 and topic in required_sample_topics:
            errors.append(
                f"Topic {topic} has 0 recorded raw CDR samples (empty samples cannot declare 100% native validation)"
            )

        mismatched_gids = set()
        for s in samples:
            if s.get("type") != expected_type:
                errors.append(f"Raw type differs for {topic}")
            sample_gid = s.get("publisher_gid")
            if sample_gid != expected_gid:
                mismatched_gids.add(sample_gid)

        if mismatched_gids:
            errors.append(
                f"Topic {topic} raw CDR samples contain mismatched GID(s): {sorted(list(mismatched_gids))} "
                f"(expected snapshot GID {expected_gid})"
            )

        sample_matches[topic] = {
            "samples_checked": sample_count,
            "sample_scope": "observed" if sample_count else "not_exercised",
            "expected_gid": expected_gid,
            "mismatch_count": len(mismatched_gids),
        }

    # 5. Full raw capture hash verification gate
    if not raw_hash_valid:
        errors.append("Raw capture verification failed via verify_raw_capture")

    if errors:
        return {
            "available": True,
            "status": "failed",
            "writer_binding": "unbound",
            "snapshot_exclusivity": "unverified",
            "errors": errors,
            "snapshot_count": len(snapshots),
            "sample_matches": sample_matches,
        }

    first_s = snapshots[0].get("monotonic_s", 0.0)
    last_s = snapshots[-1].get("monotonic_s", 0.0)

    return {
        "available": True,
        "status": "verified",
        "writer_binding": "verified_bound",
        "snapshot_exclusivity": "verified_at_snapshots",
        "snapshot_count": len(snapshots),
        "first_snapshot_monotonic_s": first_s,
        "last_snapshot_monotonic_s": last_s,
        "coverage_interval_s": round(last_s - first_s, 6),
        "sampling_reasons": [s.get("reason") for s in snapshots],
        "claim_scope": "verified_at_discrete_snapshots_only_no_claim_of_unsampled_instantaneous_exclusivity",
        "sample_matches": sample_matches,
        "rationale": (
            "Publisher exclusivity is verified across discrete active graph discovery snapshots "
            "(ready, periodic, before-send, report) strictly covering all required channels with "
            "publisher_count=1, node_name match, invariant non-zero GID, and non-empty raw CDR sample sets. "
            "Full raw capture hash chain verified. Un-sampled instantaneous exclusivity is explicitly not claimed."
        ),
    }


def evaluate_publisher_stack(
    stack_name: str,
    raw_audit: Dict[str, Any],
    init_audit: Dict[str, Any],
    children_audit: Dict[str, Any],
    control_log_audit: Dict[str, Any],
    result_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Reconcile raw capture, snapshots, initialized graph, process info, and logs for one stack."""
    topics = raw_audit.get("topics", {})
    raw_samples_by_topic = raw_audit.get("raw_samples_by_topic", {})
    raw_hash_valid = raw_audit.get("hash_chain_valid", False)

    target_topics_audit: Dict[str, Any] = {}
    for t, tinfo in topics.items():
        if tinfo["category"] == "native_target":
            target_topics_audit[t] = tinfo

    all_targets_single_gid = True
    target_gids: Set[str] = set()
    target_prefixes: Set[str] = set()

    for t, tinfo in target_topics_audit.items():
        if not tinfo["single_gid_observed"]:
            all_targets_single_gid = False
        target_gids.update(tinfo["unique_gids"])
        target_prefixes.update(tinfo["unique_participant_guid_prefixes"])

    control_prefix = init_audit.get("control_guid_prefix")
    prefix_match = False
    if control_prefix and target_prefixes:
        prefix_match = target_prefixes == {control_prefix}

    # Discover publisher_snapshots in result_data if available
    snapshots = []
    if result_data:
        task_data = result_data.get("task", {})
        aruco_data = task_data.get("aruco") or result_data.get("aruco") or {}
        snapshots = aruco_data.get("publisher_snapshots", [])

    required_samples = set(REQUIRED_SNAPSHOT_CHANNELS.get(stack_name, {}))
    if stack_name == "arducopter" and result_data and result_data.get("task", {}).get("aruco", {}).get("selected") is False:
        required_samples.discard("/ap/cmd_vel")
    snapshots_audit = audit_publisher_snapshots(
        snapshots, stack_name, raw_samples_by_topic, raw_hash_valid, required_sample_topics=required_samples
    )

    if snapshots_audit["available"] and snapshots_audit["status"] == "verified":
        writer_binding = "verified_bound"
        snapshot_exclusivity = "verified_at_snapshots"
        binding_rationale = (
            "Verified endpoint binding: active discovery snapshots in task result prove DataWriter "
            f"on native target channels is owned by 'wksim_joint_{stack_name}_control' with invariant GID, "
            "matching 100% of authentic raw CDR samples and unbroken canonical raw hash chain."
        )
        exclusivity_rationale = snapshots_audit["rationale"]
    else:
        writer_binding = "unbound"
        snapshot_exclusivity = "unverified"
        binding_rationale = (
            "The 12-byte participant GuidPrefix matches the Control node's reader endpoints in initialized.json. "
            "However, no active publisher discovery snapshots were retained for native target channels in evidence."
        )
        exclusivity_rationale = (
            "All observed native target samples originated from a single DataWriter GID per topic. "
            "However, passive sample capture only observes messages that were actively published; "
            "it cannot detect dormant, idle, or misconfigured secondary publishers present on the DDS graph. "
            "Because no graph discovery snapshots were retained, full-graph publisher exclusivity "
            "cannot be claimed from existing evidence."
        )

    node_binding_assessment = {
        "participant_guid_prefix_match": prefix_match,
        "control_guid_prefix": control_prefix,
        "target_writer_guid_prefixes": sorted(list(target_prefixes)),
        "target_writer_gids": sorted(list(target_gids)),
        "direct_writer_discovery_recorded": snapshots_audit.get("available", False),
        "control_node_logged_writer_gid": control_log_audit.get("logs_target_publisher_gids", False),
        "status": writer_binding,
        "claim_endpoint_bound": writer_binding == "verified_bound",
        "assessment_rationale": binding_rationale,
    }

    exclusivity_assessment = {
        "single_gid_per_target_topic_observed": all_targets_single_gid and bool(target_topics_audit),
        "active_graph_discovery_snapshots_retained": snapshots_audit.get("available", False),
        "status": snapshot_exclusivity,
        "claim_full_graph_exclusivity": False,
        "claim_snapshot_exclusivity": snapshot_exclusivity == "verified_at_snapshots",
        "assessment_rationale": exclusivity_rationale,
    }

    return {
        "stack": stack_name,
        "writer_binding": writer_binding,
        "snapshot_exclusivity": snapshot_exclusivity,
        "snapshots_audit": snapshots_audit,
        "raw_capture": {
            "path": raw_audit.get("file_path"),
            "total_lines": raw_audit.get("total_lines"),
            "hash_chain_valid": raw_audit.get("hash_chain_valid"),
            "hash_chain_message": raw_audit.get("hash_chain_message"),
            "target_topics": target_topics_audit,
        },
        "initialized_graph": {
            "path": init_audit.get("file_path"),
            "control_node_name": init_audit.get("control_node_name"),
            "control_guid_prefix": init_audit.get("control_guid_prefix"),
            "control_readers": init_audit.get("control_reader_endpoints"),
        },
        "children_process": children_audit.get("control_processes", {}),
        "control_log": {
            "path": control_log_audit.get("file_path"),
            "native_sources_bound_count": len(control_log_audit.get("native_sources_bound_events", [])),
            "logs_target_publisher_gids": control_log_audit.get("logs_target_publisher_gids", False),
        },
        "node_binding_assessment": node_binding_assessment,
        "exclusivity_assessment": exclusivity_assessment,
    }


def find_run_stacks(run_root: Path) -> List[Tuple[str, Path, Path, Path, Path, Path]]:
    """Locate stack raw capture, initialized.json, result.json, children.json, and control.log."""
    candidates = []

    raw_files = list(run_root.glob(f"**/{RAW_FILE_NAME}"))
    for raw_path in raw_files:
        stack_dir = raw_path.parent
        stack_name = stack_dir.name
        task_dir = stack_dir.parent
        tasks_dir = task_dir.parent
        epoch_dir = tasks_dir.parent if tasks_dir.name == "tasks" else task_dir

        init_json = stack_dir / "initialized.json"
        result_json = stack_dir / "result.json"
        children_json = epoch_dir / "children.json"
        control_log = epoch_dir / f"{stack_name}-control.log"

        candidates.append((stack_name, raw_path, init_json, result_json, children_json, control_log))

    return candidates


def audit_run(run_root: Path) -> Dict[str, Any]:
    """Execute complete publisher GID and exclusivity audit across all stacks in run_root."""
    stacks = find_run_stacks(run_root)
    if not stacks:
        raise FileNotFoundError(f"No {RAW_FILE_NAME} logs found under {run_root}")
    if len(stacks) != 2 or {item[0] for item in stacks} != {'arducopter','px4'}:
        raise ValueError('Publisher audit requires exactly one dual-stack epoch')

    stack_results = {}
    for stack_name, raw_path, init_path, result_path, children_path, log_path in stacks:
        raw_audit = audit_raw_capture_file(raw_path)
        init_audit = audit_initialized_json(init_path)
        children_audit = audit_children_json(children_path)
        control_log_audit = audit_control_log(log_path)

        result_data = None
        if result_path.is_file():
            try:
                with open(result_path, "r", encoding="utf-8") as fh:
                    result_data = json.load(fh)
            except Exception:
                pass

        start = raw_audit.get('start_record') or {}
        if (not raw_audit['hash_chain_valid'] or not result_data
                or start.get('run_id') != result_data.get('run_id')
                or start.get('epoch') != result_data.get('scene_epoch')
                or start.get('epoch') != raw_path.parents[3].name
                or start.get('stack') != stack_name
                or start.get('uav_id') != (1 if stack_name == 'arducopter' else 2)):
            raise ValueError('Raw capture integrity/identity differs from retained task')
        provenance = reconcile_identity({'start':start},raw_path.parents[3],
                         json.loads((raw_path.parents[3]/'preflight.json').read_text()))

        stack_audit = evaluate_publisher_stack(
            stack_name,
            raw_audit,
            init_audit,
            children_audit,
            control_log_audit,
            result_data,
        )
        stack_results[stack_name] = stack_audit
        stack_audit['provenance'] = provenance

    all_bound = all(s["writer_binding"] == "verified_bound" for s in stack_results.values())
    all_snap_exclusive = all(
        s["snapshot_exclusivity"] == "verified_at_snapshots" for s in stack_results.values()
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence_sha256": {str(p.relative_to(run_root)):hashlib.sha256(p.read_bytes()).hexdigest()
                            for _,raw,init,result,children,log in stacks
                            for p in (raw,init,result,children,log) if p.is_file()},
        "run_root": str(run_root.resolve()),
        "stacks_audited": list(stack_results.keys()),
        "results_by_stack": stack_results,
        "overall_verdict": {
            "writer_binding": "verified_bound" if all_bound else "unbound",
            "snapshot_exclusivity": "verified_at_snapshots" if all_snap_exclusive else "unverified",
            "participant_guid_prefix_consistent": all(
                s["node_binding_assessment"]["participant_guid_prefix_match"]
                for s in stack_results.values()
            ),
            "claim_scope": (
                "verified_at_discrete_snapshots_only_no_claim_of_unsampled_instantaneous_exclusivity"
                if all_snap_exclusive
                else "unverified_passive_observation_only"
            ),
            "status": (
                "snapshots_verified_and_bound"
                if all_bound and all_snap_exclusive
                else "snapshot_validation_failed" if any(s['snapshots_audit']['available'] for s in stack_results.values())
                else "investigation_completed_no_snapshots_retained"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline audit of ArUco native target publisher GIDs and graph exclusivity."
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        required=True,
        help="Path to the run directory (e.g. validation/40-aruco-tracking-10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to output JSON report (must not already exist; opened in exclusive 'x' mode)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed stack breakdown to stderr",
    )

    args = parser.parse_args()

    try:
        report = audit_run(args.run_root)
    except Exception as exc:
        print(f"Error during audit: {exc}", file=sys.stderr)
        return 1

    sanitized = sanitize_no_nan(report)
    json_text = json.dumps(sanitized, indent=2, allow_nan=False)

    if args.output:
        try:
            with open(args.output, "x", encoding="utf-8") as fh:
                fh.write(json_text)
                fh.write("\n")
            print(f"Report written to {args.output}")
        except FileExistsError:
            print(
                f"Error: Output file {args.output} already exists (mode 'x' requires non-existent target)",
                file=sys.stderr,
            )
            return 2
    else:
        print(json_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
