#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline admission assist for #29 scene feedback / ArUco visual targets.

Reads existing scene and evidence JSON. Correlates a visual ArUco target with a
physical contact envelope only when coordinate frame, feedback validity, source
identity, and stale/disconnect semantics are all present and consistent.

This is not UE, native, ROS, or #29 acceptance. It never invents an approved
contact-force budget, never treats a visual offset as collision, and never
unlocks #29/#79/#80/#81 while #9 is OPEN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATIC_SCENE_PATH = REPO / "Simulator" / "wksim_runtime" / "static-scene-v1.json"
EVIDENCE_MANIFEST_PATH = REPO / "docs" / "plan" / "29-terrain-evidence-manifest.json"

PACK_SCHEMA = "wksim.aruco-native-target-pack.v1"
REPORT_SCHEMA = "wksim.aruco-native-target-inspect.v1"
CONTACT_SCHEMA = "wksim.contact.v1"
ARUCO_TARGET_SCHEMA = "wksim.aruco-target.v1"
STATIC_SCENE_SCHEMA = "wksim.static-scene.v1"
EVIDENCE_MANIFEST_SCHEMA = "wksim.29-terrain-evidence.v1"
DISPLAY_MANIFEST_SCHEMA = "wksim.display-manifest.v1"

VISUAL_STATIC_SCENE_ID = "static-plane-box-v1"
VISUAL_STATIC_SCENE_HASH = (
    "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514"
)
PROBE_SCENE_ID = "static-plane-box-v1-real-tick0"
PROBE_SCENE_HASH = (
    "4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300"
)
PLANNER_SCENE_HASH = (
    "40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba"
)

PARENT_TICKETS = ("#29", "#79", "#80", "#81")
ISSUE_9_OPEN = "OPEN"
TICK_NS = 1_000_000

CONTACT_REQUIRED = (
    "schema",
    "scene_id",
    "scene_hash",
    "epoch",
    "step",
    "sim_time_ns",
    "valid_from_step",
    "valid_until_step",
    "body_id",
    "geometry_id",
    "contact_point_enu_m",
    "normal_enu",
    "penetration_m",
    "source_identity",
)
SCENE_REQUIRED = ("scene_id", "scene_hash", "coordinate_frame", "unit")
VISUAL_REQUIRED = (
    "schema",
    "coordinate_frame",
    "source_identity",
    "epoch",
    "step",
    "valid_from_step",
    "valid_until_step",
)
SEMANTICS_REQUIRED = (
    "stale_feedback",
    "disconnect",
    "render_frame_advances_physics",
)
FORBIDDEN_BUDGET_KEYS = frozenset(
    {
        "force",
        "contact_force",
        "impulse",
        "stiffness",
        "damping",
        "friction",
        "torque",
        "wrench",
        "contact_budget",
        "approved_contact_budget",
    }
)
VISUAL_OFFSET_KEYS = frozenset(
    {
        "visual_ground_offset_m",
        "visual_offset_m",
        "ground_offset_m",
        "display_z_offset_m",
    }
)
REUSE_TOKENS = frozenset({"reuse", "reuse_old_feedback", "silent_reuse", "cache"})


class InspectError(ValueError):
    """Raised for unreadable or malformed evidence, not for semantic rejection."""


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise InspectError(f"missing JSON file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise InspectError(f"cannot read {path}: {error}") from error
    if not text.endswith("\n") and "\n" not in text:
        raise InspectError(f"truncated JSON at {path}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise InspectError(f"corrupt JSON at {path}: {error}") from error


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def _is_identity(value: Any) -> bool:
    """Non-empty string, or a non-empty object of identity strings/objects."""
    if _is_nonempty_str(value):
        return True
    if isinstance(value, dict):
        if not value:
            return False
        return all(_is_nonempty_str(key) and _is_identity(item) for key, item in value.items())
    return False


def _is_nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_step(value: Any) -> bool:
    return _is_nonneg_int(value)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_finite_vector(value: Any, length: int = 3) -> bool:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        return False
    if len(value) != length:
        return False
    return all(_is_finite_number(item) for item in value)


def _finite_vector(value: Any) -> bool:
    return _is_finite_vector(value, 3)


def _walk_forbidden_budget(obj: Any, found: list[str] | None = None) -> list[str]:
    found = found if found is not None else []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_BUDGET_KEYS:
                found.append(key)
            _walk_forbidden_budget(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_forbidden_budget(item, found)
    return found


def _locked_parents() -> dict[str, bool]:
    return {ticket: False for ticket in PARENT_TICKETS}


def _base_report() -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "role": "offline_read_only_admission_assist",
        "description": (
            "Correlate visual ArUco and physical contact records only when "
            "offline evidence is complete. Not UE/native/#29 acceptance."
        ),
        "status": "rejected",
        "correlated": False,
        "rejection_reasons": [],
        "issue_9_state": ISSUE_9_OPEN,
        "parent_tickets_unlocked": _locked_parents(),
        "unlock_blocked_by": ["#9 OPEN"],
        "contact_budget_invented": False,
        "visual_treated_as_collision": False,
        "render_frame_advances_physics": False,
    }


def _visual_offset_only(visual: Any, physical: Any) -> bool:
    if not isinstance(physical, dict):
        return True
    if any(key in physical for key in VISUAL_OFFSET_KEYS):
        return True
    if physical.get("collision_from") in {"visual", "visual_offset", "aruco"}:
        return True
    if physical.get("schema") != CONTACT_SCHEMA:
        return True
    if not isinstance(visual, dict):
        return False
    contact = physical.get("contact_point_enu_m")
    for key in ("position_world_ue_m", "position_body_flu_m", "position_optical_m"):
        pose = visual.get(key)
        if _finite_vector(contact) and _finite_vector(pose) and list(contact) == list(pose):
            return True
    return False


def _identity_conflated(scene_id: Any, scene_hash: Any) -> bool:
    known = {
        (VISUAL_STATIC_SCENE_ID, VISUAL_STATIC_SCENE_HASH),
        (PROBE_SCENE_ID, PROBE_SCENE_HASH),
    }
    if scene_hash == PLANNER_SCENE_HASH:
        return True
    if scene_id == VISUAL_STATIC_SCENE_ID and scene_hash == PROBE_SCENE_HASH:
        return True
    if scene_id == PROBE_SCENE_ID and scene_hash == VISUAL_STATIC_SCENE_HASH:
        return True
    if (scene_id, scene_hash) in known:
        return False
    return False


def inspect_pack(pack: dict[str, Any]) -> dict[str, Any]:
    """Inspect one in-memory evidence pack. Semantic gaps become rejections."""
    report = _base_report()
    reasons: list[str] = []

    if not isinstance(pack, dict):
        raise InspectError("evidence pack must be a JSON object")
    if pack.get("schema") != PACK_SCHEMA:
        reasons.append("unknown_pack_schema")

    if pack.get("issue_9_state") == "CLOSED":
        reasons.append("fabricated_issue_9_closure")
    report["issue_9_state"] = ISSUE_9_OPEN
    report["unlock_blocked_by"] = [
        "#9 OPEN",
        "offline_tool_is_not_ue_or_physics_acceptance",
    ]

    budget_keys = _walk_forbidden_budget(pack)
    if budget_keys:
        reasons.append("unapproved_contact_budget")
        report["contact_budget_invented"] = False

    scene = pack.get("scene")
    visual = pack.get("visual_target")
    physical = pack.get("physical_target")
    semantics = pack.get("feedback_semantics")
    current_step = pack.get("current_step")

    if not isinstance(scene, dict):
        reasons.append("missing_scene")
        scene = {}
    if not isinstance(visual, dict):
        reasons.append("missing_visual_target")
        visual = {}
    if not isinstance(physical, dict):
        reasons.append("missing_physical_target")
        physical = {}
    if not isinstance(semantics, dict):
        reasons.append("missing_stale_or_disconnect_semantics")
        semantics = {}

    for field in SCENE_REQUIRED:
        value = scene.get(field)
        if not _is_nonempty_str(value):
            reasons.append(
                "missing_coordinate_frame"
                if field == "coordinate_frame"
                else f"missing_scene_{field}"
            )
    if _is_nonempty_str(scene.get("coordinate_frame")) and scene.get("coordinate_frame") != "ENU":
        reasons.append("missing_coordinate_frame")
    if _is_nonempty_str(scene.get("unit")) and scene.get("unit") != "metre":
        reasons.append("unsupported_unit")
    if "source_identity" in scene and not _is_identity(scene.get("source_identity")):
        reasons.append("missing_source_identity")
    if "epoch" in scene and not _is_nonempty_str(scene.get("epoch")):
        reasons.append("invalid_identity_type")
    if "origin_enu_m" in scene and not _is_finite_vector(scene.get("origin_enu_m"), 3):
        reasons.append("invalid_vector")

    if visual.get("schema") not in (None, "") and visual.get("schema") != ARUCO_TARGET_SCHEMA:
        reasons.append("unknown_visual_schema")
    if "schema" in visual and not _is_nonempty_str(visual.get("schema")):
        reasons.append("unknown_visual_schema")
    for field in VISUAL_REQUIRED:
        value = visual.get(field)
        if field in {"step", "valid_from_step", "valid_until_step"}:
            if not _is_nonneg_int(value):
                reasons.append("missing_feedback_valid_time")
        elif field == "source_identity":
            if not _is_identity(value):
                reasons.append("missing_source_identity")
        elif field == "coordinate_frame":
            if not _is_nonempty_str(value) or value != "ENU":
                reasons.append("missing_coordinate_frame")
        elif not _is_nonempty_str(value):
            reasons.append(f"missing_visual_{field}")
    for field in ("scene_id", "scene_hash", "epoch"):
        if field in visual and not _is_nonempty_str(visual.get(field)):
            reasons.append("invalid_identity_type")
    for field in ("position_world_ue_m", "position_body_flu_m", "position_optical_m"):
        if field in visual and not _is_finite_vector(visual.get(field), 3):
            reasons.append("invalid_vector")
    if "valid_for_steps" in visual and not _is_nonneg_int(visual.get("valid_for_steps")):
        reasons.append("missing_feedback_valid_time")

    missing_contact_fields = [field for field in CONTACT_REQUIRED if field not in physical]
    if missing_contact_fields:
        if "source_identity" in missing_contact_fields:
            reasons.append("missing_source_identity")
        if {"valid_from_step", "valid_until_step"} & set(missing_contact_fields):
            reasons.append("missing_feedback_valid_time")
        if physical:
            reasons.append("incomplete_physical_envelope")
    elif not _is_nonempty_str(physical.get("schema")) or physical.get("schema") != CONTACT_SCHEMA:
        reasons.append("incomplete_physical_envelope")
    if physical:
        if not _is_identity(physical.get("source_identity")):
            reasons.append("missing_source_identity")
        for field in ("step", "valid_from_step", "valid_until_step", "sim_time_ns"):
            if field in physical and not _is_nonneg_int(physical.get(field)):
                reasons.append("missing_feedback_valid_time")
        if "valid_for_steps" in physical and not _is_nonneg_int(physical.get("valid_for_steps")):
            reasons.append("missing_feedback_valid_time")
        for field in ("contact_point_enu_m", "normal_enu"):
            if field in physical and not _is_finite_vector(physical.get(field), 3):
                reasons.append("invalid_vector")
        if "penetration_m" in physical and not _is_finite_number(physical.get("penetration_m")):
            reasons.append("invalid_scalar_type")
        for field in ("scene_id", "scene_hash", "epoch", "body_id", "geometry_id"):
            if field in physical and not _is_nonempty_str(physical.get(field)):
                reasons.append("invalid_identity_type")

    if any(field not in semantics for field in SEMANTICS_REQUIRED):
        reasons.append("missing_stale_or_disconnect_semantics")
    else:
        stale_policy = semantics.get("stale_feedback")
        disconnect_policy = semantics.get("disconnect")
        render_advances = semantics.get("render_frame_advances_physics")
        if not _is_nonempty_str(stale_policy) or not _is_nonempty_str(disconnect_policy):
            reasons.append("missing_stale_or_disconnect_semantics")
        elif stale_policy in REUSE_TOKENS or disconnect_policy in REUSE_TOKENS:
            reasons.append("missing_stale_or_disconnect_semantics")
        if render_advances is True:
            reasons.append("render_frame_advances_physics")
            report["render_frame_advances_physics"] = True
        elif render_advances is not False:
            reasons.append("missing_stale_or_disconnect_semantics")

    if _visual_offset_only(visual, physical):
        reasons.append("visual_offset_only")
        report["visual_treated_as_collision"] = False

    scene_id = scene.get("scene_id") if _is_nonempty_str(scene.get("scene_id")) else physical.get("scene_id")
    scene_hash = (
        scene.get("scene_hash") if _is_nonempty_str(scene.get("scene_hash")) else physical.get("scene_hash")
    )
    if _is_nonempty_str(scene_id) and _is_nonempty_str(scene_hash) and _identity_conflated(scene_id, scene_hash):
        reasons.append("scene_identity_conflation")
    if (
        _is_nonempty_str(physical.get("scene_id"))
        and _is_nonempty_str(scene.get("scene_id"))
        and physical["scene_id"] != scene["scene_id"]
    ) or (
        _is_nonempty_str(physical.get("scene_hash"))
        and _is_nonempty_str(scene.get("scene_hash"))
        and physical["scene_hash"] != scene["scene_hash"]
    ):
        reasons.append("scene_identity_mismatch")
    if (
        _is_nonempty_str(visual.get("scene_id"))
        and _is_nonempty_str(scene.get("scene_id"))
        and visual["scene_id"] != scene["scene_id"]
    ) or (
        _is_nonempty_str(visual.get("scene_hash"))
        and _is_nonempty_str(scene.get("scene_hash"))
        and visual["scene_hash"] != scene["scene_hash"]
    ):
        reasons.append("scene_identity_mismatch")

    pack_epoch = pack.get("epoch")
    if "epoch" in pack and not _is_nonempty_str(pack_epoch):
        reasons.append("invalid_identity_type")
    epoch = scene.get("epoch") if _is_nonempty_str(scene.get("epoch")) else pack_epoch
    if (
        _is_nonempty_str(visual.get("epoch"))
        and _is_nonempty_str(physical.get("epoch"))
        and visual["epoch"] != physical["epoch"]
    ):
        reasons.append("foreign_epoch")
    if _is_nonempty_str(epoch) and _is_nonempty_str(physical.get("epoch")) and epoch != physical["epoch"]:
        reasons.append("foreign_epoch")

    if not _is_step(current_step):
        reasons.append("missing_feedback_valid_time")
    else:
        visual_from = visual.get("valid_from_step", visual.get("step"))
        visual_until = visual.get("valid_until_step")
        physical_from = physical.get("valid_from_step")
        physical_until = physical.get("valid_until_step")
        if _is_nonneg_int(physical.get("step")) and _is_nonneg_int(physical.get("sim_time_ns")):
            if physical["sim_time_ns"] != physical["step"] * TICK_NS:
                reasons.append("missing_feedback_valid_time")
        if all(_is_nonneg_int(value) for value in (visual_from, visual_until, physical_from, physical_until)):
            if current_step > visual_until or current_step > physical_until:
                reasons.append("stale_feedback")
            if current_step < visual_from or current_step < physical_from:
                reasons.append("future_feedback")

    # Deduplicate while preserving order.
    ordered = []
    for reason in reasons:
        if reason not in ordered:
            ordered.append(reason)
    report["rejection_reasons"] = ordered
    report["correlated"] = not ordered
    report["status"] = "correlated" if report["correlated"] else "rejected"
    report["scene"] = {
        "scene_id": scene.get("scene_id"),
        "scene_hash": scene.get("scene_hash"),
        "coordinate_frame": scene.get("coordinate_frame"),
        "unit": scene.get("unit"),
    }
    report["current_step"] = current_step if _is_step(current_step) else None
    return report


def inspect_evidence_manifest(manifest: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Read the retained #29 evidence manifest. It cannot unlock parent tickets."""
    report = _base_report()
    report["retained_manifest"] = str(path) if path is not None else None
    reasons = ["insufficient_offline_pair"]
    if manifest.get("schema") != EVIDENCE_MANIFEST_SCHEMA:
        reasons.append("unknown_pack_schema")
    if manifest.get("acceptance") is True:
        reasons.append("fabricated_parent_acceptance")
    if manifest.get("blocking_issue") != 9:
        reasons.append("missing_issue_9_block")
    identities = manifest.get("scene_identities") or {}
    visual = identities.get("visual_static_scene") or {}
    real = identities.get("real_terrain_scene") or {}
    if visual.get("scene_sha256") == real.get("scene_sha256"):
        reasons.append("scene_identity_conflation")
    if visual.get("scene_sha256") != VISUAL_STATIC_SCENE_HASH:
        reasons.append("scene_identity_mismatch")
    if real.get("scene_sha256") != PROBE_SCENE_HASH:
        reasons.append("scene_identity_mismatch")
    report["issue_9_state"] = ISSUE_9_OPEN
    report["unlock_blocked_by"] = [
        "#9 OPEN",
        "offline_tool_is_not_ue_or_physics_acceptance",
    ]
    report["unproven_boundaries"] = manifest.get("unproven_boundaries") or {}
    report["rejection_reasons"] = reasons
    report["status"] = "rejected"
    report["correlated"] = False
    report["scene"] = {
        "scene_id": visual.get("scene_id"),
        "scene_hash": visual.get("scene_sha256"),
        "coordinate_frame": "ENU",
        "unit": "metre",
    }
    return report


def inspect_retained_paths(repo: Path = REPO) -> dict[str, Any]:
    """Inspect committed scene/evidence JSON paths. Missing live dirs stay unavailable."""
    scene_path = repo / STATIC_SCENE_PATH.relative_to(REPO)
    manifest_path = repo / EVIDENCE_MANIFEST_PATH.relative_to(REPO)
    report = _base_report()
    report["paths"] = {
        "static_scene": str(scene_path),
        "evidence_manifest": str(manifest_path),
        "lunar_29_static_contact": str(repo / "validation" / "lunar-29-static-contact"),
        "lunar_29_live_contact": str(repo / "validation" / "lunar-29-live-contact"),
    }
    report["path_availability"] = {}

    if scene_path.is_file():
        scene = load_json(scene_path)
        report["path_availability"]["static_scene"] = True
        report["static_scene_sha256"] = digest_file(scene_path)
        if (
            scene.get("schema") != STATIC_SCENE_SCHEMA
            or scene.get("scene_id") != VISUAL_STATIC_SCENE_ID
            or scene.get("scene_sha256") != VISUAL_STATIC_SCENE_HASH
            or scene.get("coordinate_frame") != "ENU"
            or scene.get("unit") != "metre"
        ):
            report["rejection_reasons"].append("scene_identity_mismatch")
        report["scene"] = {
            "scene_id": scene.get("scene_id"),
            "scene_hash": scene.get("scene_sha256"),
            "coordinate_frame": scene.get("coordinate_frame"),
            "unit": scene.get("unit"),
        }
    else:
        report["path_availability"]["static_scene"] = False
        report["rejection_reasons"].append("missing_scene")

    if manifest_path.is_file():
        manifest_report = inspect_evidence_manifest(load_json(manifest_path), manifest_path)
        report["path_availability"]["evidence_manifest"] = True
        report["evidence_manifest_sha256"] = digest_file(manifest_path)
        report["unproven_boundaries"] = manifest_report.get("unproven_boundaries")
        for reason in manifest_report["rejection_reasons"]:
            if reason not in report["rejection_reasons"]:
                report["rejection_reasons"].append(reason)
    else:
        report["path_availability"]["evidence_manifest"] = False
        report["rejection_reasons"].append("insufficient_offline_pair")

    live_manifest = repo / "validation" / "lunar-29-live-contact" / "display-manifest.json"
    report["paths"]["live_display_manifest"] = str(live_manifest)
    for key in ("lunar_29_static_contact", "lunar_29_live_contact"):
        available = Path(report["paths"][key]).is_dir()
        report["path_availability"][key] = available
        if not available:
            report["rejection_reasons"].append("retained_live_evidence_unavailable")
    if live_manifest.is_file():
        display = load_json(live_manifest)
        report["path_availability"]["live_display_manifest"] = True
        report["live_display_manifest_sha256"] = digest_file(live_manifest)
        authority = display.get("authority") or ""
        if (
            display.get("schema") != DISPLAY_MANIFEST_SCHEMA
            or display.get("scene_id") != VISUAL_STATIC_SCENE_ID
            or display.get("scene_hash") != VISUAL_STATIC_SCENE_HASH
            or display.get("coordinate_frame") != "ENU"
            or "cannot alter physics" not in authority
        ):
            report["rejection_reasons"].append("scene_identity_mismatch")
        if "display-only" not in authority:
            report["rejection_reasons"].append("visual_offset_only")
    else:
        report["path_availability"]["live_display_manifest"] = False

    ordered = []
    for reason in report["rejection_reasons"]:
        if reason not in ordered:
            ordered.append(reason)
    report["rejection_reasons"] = ordered
    report["status"] = "rejected"
    report["correlated"] = False
    report["unlock_blocked_by"] = [
        "#9 OPEN",
        "offline_tool_is_not_ue_or_physics_acceptance",
    ]
    return report


def inspect_path(path: Path) -> dict[str, Any]:
    """Load a pack, retained manifest, or directory containing a pack file."""
    path = path.resolve()
    if path.is_dir():
        pack_file = path / "aruco-native-target-pack.json"
        if not pack_file.is_file():
            raise InspectError(
                f"directory {path} has no aruco-native-target-pack.json"
            )
        path = pack_file
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise InspectError(f"{path} must contain a JSON object")
    if payload.get("schema") == EVIDENCE_MANIFEST_SCHEMA:
        report = inspect_evidence_manifest(payload, path)
    elif payload.get("schema") == STATIC_SCENE_SCHEMA:
        report = inspect_pack({"scene": payload})
    elif payload.get("schema") == DISPLAY_MANIFEST_SCHEMA:
        report = inspect_pack({"scene": payload})
    else:
        report = inspect_pack(payload)
    report["input_path"] = str(path)
    report["input_sha256"] = digest_file(path)
    return report


def write_report(report: dict[str, Any], output: Path) -> None:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Output file already exists, refusing overwrite: {output}")
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Offline #29 admission assist: correlate ArUco visual targets with "
            "physical contact only when evidence is complete."
        )
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=None,
        help="Pack JSON, retained evidence manifest, or directory with aruco-native-target-pack.json.",
    )
    parser.add_argument(
        "--retained-paths",
        action="store_true",
        help="Inspect committed static-scene and #29 evidence-manifest paths.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write the report in exclusive 'x' mode (refuses overwrite).",
    )
    args = parser.parse_args(argv)

    if args.evidence is not None:
        report = inspect_path(args.evidence)
    elif args.retained_paths or args.evidence is None:
        report = inspect_retained_paths()
    report["inspector_sha256"] = digest_file(Path(__file__).resolve())

    if args.output is not None:
        write_report(report, args.output)
        print(f"Analysis written to: {args.output.resolve()}")

    print(
        json.dumps(
            {
                "role": report["role"],
                "status": report["status"],
                "correlated": report["correlated"],
                "rejection_reasons": report["rejection_reasons"],
                "issue_9_state": report["issue_9_state"],
                "parent_tickets_unlocked": report["parent_tickets_unlocked"],
                "unlock_blocked_by": report["unlock_blocked_by"],
            },
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
