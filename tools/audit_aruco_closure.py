"""Fail-closed, JSON-only closure audit for the retained #104/#40 ArUco runs.

The closure manifest pins one complete run/epoch for each selected stack and the
SHA-256 of every JSON report used by the closure decision.  This auditor reads
only those JSON files; it never replays a capture, imports ROS, or combines
reports from different runs.  A raw report may remain ``pending`` because its
native portions are intentionally audited separately, but only when its
loss/HOLD gate is closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Iterable


SCHEMA = "wksim.aruco-closure-audit.v1"
MANIFEST_SCHEMA = "wksim.aruco-closure-manifest.v1"
STACKS = ("arducopter", "px4")
REPORTS = (
    "physical",
    "rate",
    "raw",
    "native_moves",
    "native_holds",
    "native_timestamps",
    "publishers",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EPOCH_RE = re.compile(r"^[0-9a-f]{32}$")
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "validation/coordination/aruco-closure-manifest.json"
RATE_SCOPE = "Verify a recorded ArUco schedule/windows; not the complete three-epoch G2 campaign."
MOVE_SCOPE = "BODY velocity MOVE to native setpoint only; no HOLD/flight/rate verdict"
HOLD_SCOPE = (
    "Offline post-MOVE HOLD targets; requires the separate public/provenance audit.\n\n"
    "Control tick resolves CURRENT_POS_HOVER from that tick's state, caches it,\n"
    "publishes native output if due, then SessionState. Native samples therefore\n"
    "belong to the immediately following continuous SessionState, not the preceding\n"
    "one. The first state carrying a HOLD supplies its frozen position and heading.\n"
    "Only HOLDs following an executed MOVE are covered; initial takeover is separate.\n"
    "No ROS nodes, physical tolerance, or flight-completion verdict is introduced.\n"
)
TIMESTAMP_SCOPE = "Native setpoint payload/header timestamps versus real feedback; MOVE/HOLD windows only"


class ClosureAuditError(ValueError):
    """A manifest or retained JSON report failed a closure invariant."""


def _fail(message: str) -> None:
    raise ClosureAuditError(message)


def _reject_constant(value: str) -> None:
    _fail(f"non-standard JSON constant {value!r}")


def _read_json(path: Path, label: str) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream, parse_constant=_reject_constant)
    except FileNotFoundError:
        _fail(f"missing {label}: {path}")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail(f"cannot read {label} {path}: {error}")
    raise AssertionError("unreachable")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty string")
    return value


def _epoch(value: Any, label: str) -> str:
    value = _string(value, label)
    if EPOCH_RE.fullmatch(value) is None:
        _fail(f"{label} must be lowercase hex32")
    return value


def _sha(value: Any, label: str) -> str:
    value = _string(value, label)
    if SHA256_RE.fullmatch(value) is None:
        _fail(f"{label} must be a lowercase SHA-256 digest")
    return value


def _digest(path: Path, label: str) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        _fail(f"missing {label}: {path}")
    except OSError as error:
        _fail(f"cannot hash {label} {path}: {error}")
    return digest


def _relative_parts(raw: Any, label: str) -> tuple[str, ...]:
    raw = _string(raw, label)
    normalized = raw.replace("\\", "/")
    if PurePosixPath(normalized).is_absolute() or PureWindowsPath(raw).is_absolute():
        _fail(f"{label} must be a relative path")
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        _fail(f"{label} must not contain '..'")
    if not parts:
        _fail(f"{label} must not be empty")
    return parts


def _secure_path(raw: Any, label: str, repo_root: Path) -> Path:
    """Resolve a repository-relative path, rejecting escape and symlink components."""
    parts = _relative_parts(raw, label)
    root = repo_root.resolve(strict=True)
    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        _fail(f"missing or unresolvable {label}: {candidate} ({error})")
    if resolved != root and root not in resolved.parents:
        _fail(f"{label} resolves outside the repository root")
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            _fail(f"{label} contains symlink component: {current}")
    return resolved


def _report_entry(value: Any, label: str) -> tuple[str, Path]:
    value = _object(value, label)
    keys = set(value)
    allowed = {"path", "sha256"}
    if label.endswith(".capture.archive") or label.endswith(".archive"):
        allowed.add("archive_sha256")
    if label.endswith(".reports.raw") or label.endswith(".raw"):
        allowed.add("raw_sha256")
    if keys != allowed:
        _fail(f"{label} has an invalid field set")
    return _sha(value["sha256"], f"{label}.sha256"), Path(_string(value["path"], f"{label}.path"))


def _verify_hashed_json(entry: Any, label: str, repo_root: Path) -> tuple[dict[str, Any], str, Path]:
    expected_sha, raw_path = _report_entry(entry, label)
    path = _secure_path(raw_path.as_posix(), f"{label}.path", repo_root)
    actual_sha = _digest(path, label)
    if actual_sha != expected_sha:
        _fail(f"{label} SHA-256 differs: expected {expected_sha}, got {actual_sha}")
    return _object(_read_json(path, label), label), actual_sha, path


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _require_no_failures(report: dict[str, Any], label: str) -> None:
    for key, value in _walk(report):
        if key in {"failures", "unresolved"}:
            if not isinstance(value, list) or value:
                _fail(f"{label}.{key} is not empty")
        elif key == "failure_count":
            if value != 0:
                _fail(f"{label}.failure_count is non-zero")
        elif key == "failure_examples":
            if not isinstance(value, list) or value:
                _fail(f"{label}.failure_examples is not empty")


def _require_status(report: dict[str, Any], label: str, expected: str = "pass") -> None:
    if report.get("status") != expected:
        _fail(f"{label}.status must be {expected!r}")


def _normal_text(value: Any) -> str:
    if isinstance(value, str):
        return value.replace("\\", "/").lower()
    if isinstance(value, dict):
        return " ".join(_normal_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_normal_text(v) for v in value)
    return ""


def _canonical_path_text(value: Any, label: str = "publisher.path") -> str:
    """Canonicalize Windows and WSL spellings for retained absolute paths."""
    text = _string(value, label).replace("\\", "/").rstrip("/").lower()
    if len(text) >= 7 and text.startswith("/mnt/") and text[5].isalpha() and text[6] == "/":
        text = text[5] + ":/" + text[7:]
    return text


def _raw_evidence_key(report: dict[str, Any], stack: str, epoch: str, label: str) -> tuple[str, str]:
    """Return the one retained raw-capture evidence key for a stack/epoch."""
    evidence = _object(report.get("evidence_sha256"), f"{label}.evidence_sha256")
    matches: list[tuple[str, str]] = []
    for raw_key, raw_sha in evidence.items():
        if not isinstance(raw_key, str):
            continue
        key = raw_key.replace("\\", "/").strip("/").lower()
        parts = PurePosixPath(key).parts
        if (
            len(parts) >= 5
            and parts[0] == "epochs"
            and parts[1] == epoch
            and parts[2] == "tasks"
            and parts[-2] == stack
            and parts[-1] == "aruco-raw-dds.jsonl"
        ):
            matches.append((key, _sha(raw_sha, f"{label}.evidence_sha256.{raw_key}")))
    if len(matches) != 1:
        _fail(f"{label} must contain exactly one canonical raw-capture evidence key for {stack}/{epoch}")
    return matches[0]


def _secure_capture_child(root: Path, relative: str, label: str) -> Path:
    """Resolve a child of a checked capture root without following symlinks."""
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        _fail(f"{label} has an invalid relative path")
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            _fail(f"{label} contains symlink component: {current}")
    try:
        resolved = current.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        _fail(f"missing or unresolvable {label}: {current} ({error})")
    if not resolved.is_file():
        _fail(f"{label} must be a regular file")
    if root not in resolved.parents:
        _fail(f"{label} resolves outside its capture root")
    return resolved


def _read_raw_start_identity(path: Path, label: str) -> dict[str, Any]:
    """Read only the canonical start record needed for publisher identity closure."""
    try:
        with path.open("r", encoding="utf-8") as stream:
            line = stream.readline()
    except (OSError, UnicodeError) as error:
        _fail(f"cannot read {label}: {error}")
    if not line:
        _fail(f"{label} is empty")
    try:
        value = json.loads(line, parse_constant=_reject_constant)
    except (TypeError, json.JSONDecodeError) as error:
        _fail(f"{label} start record is invalid JSON: {error}")
    return _object(value, f"{label} start record")


def _check_manifest(manifest: dict[str, Any], repo_root: Path) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        _fail(f"manifest schema must be {MANIFEST_SCHEMA!r}")
    if manifest.get("status") != "closed":
        _fail("manifest status must be closed")
    if manifest.get("tickets") != {"#40": "closed", "#104": "closed"}:
        _fail("manifest must pin #40 and #104 as closed")
    runs = _object(manifest.get("runs"), "manifest.runs")
    if set(runs) != set(STACKS):
        _fail("manifest.runs must contain exactly arducopter and px4")
    paths: list[str] = []
    for stack in STACKS:
        run = _object(runs[stack], f"manifest.runs.{stack}")
        _string(run.get("run_id"), f"manifest.runs.{stack}.run_id")
        _epoch(run.get("epoch"), f"manifest.runs.{stack}.epoch")
        capture_root = _string(run.get("capture_root"), f"manifest.runs.{stack}.capture_root")
        capture_root_path = _secure_path(capture_root, f"manifest.runs.{stack}.capture_root", repo_root)
        if not capture_root_path.is_dir():
            _fail(f"manifest.runs.{stack}.capture_root is not a directory")
        capture = _object(run.get("capture"), f"manifest.runs.{stack}.capture")
        reports = _object(run.get("reports"), f"manifest.runs.{stack}.reports")
        if set(capture) != {"report", "archive"}:
            _fail(f"manifest.runs.{stack}.capture must contain report and archive")
        if set(reports) != set(REPORTS):
            _fail(f"manifest.runs.{stack}.reports must contain the seven closure reports")
        for label, entry in [*(capture.items()), *(reports.items())]:
            expected, raw_path = _report_entry(entry, f"manifest.runs.{stack}.{label}")
            del expected
            resolved = _secure_path(raw_path.as_posix(), f"manifest.runs.{stack}.{label}.path", repo_root)
            path_key = os.fspath(resolved).replace("\\", "/").lower()
            if path_key in paths:
                _fail(f"duplicate evidence path in manifest: {raw_path}")
            paths.append(path_key)
        for label in ("report", "archive"):
            entry = _object(capture[label], f"manifest.runs.{stack}.capture.{label}")
            evidence_path = _secure_path(entry["path"], f"manifest.runs.{stack}.capture.{label}.path", repo_root)
            if capture_root_path not in evidence_path.parents:
                _fail(f"manifest.runs.{stack}.capture.{label} is outside capture_root")


def _verify_capture(run: dict[str, Any], stack: str, repo_root: Path) -> tuple[dict[str, Any], str, dict[str, Any]]:
    run_id = _string(run.get("run_id"), f"{stack}.run_id")
    epoch = _epoch(run.get("epoch"), f"{stack}.epoch")
    capture_root = _string(run.get("capture_root"), f"{stack}.capture_root")
    capture_root_path = _secure_path(capture_root, f"{stack}.capture_root", repo_root)
    capture = _object(run.get("capture"), f"{stack}.capture")
    report, report_sha, report_path = _verify_hashed_json(capture["report"], f"{stack}.capture.report", repo_root)
    if capture_root_path not in report_path.parents:
        _fail(f"{stack} capture report is outside its resolved capture root")
    if report.get("status") != "captured_pending_independent_audit":
        _fail(f"{stack} capture report is not a completed capture")
    session = _object(report.get("session"), f"{stack}.capture.report.session")
    if session.get("run_id") != run_id:
        _fail(f"{stack} capture session run_id differs")
    config = _object(report.get("config"), f"{stack}.capture.report.config")
    if config.get("run_id") != run_id:
        _fail(f"{stack} capture config run_id differs")
    experiment = _object(config.get("aruco_experiment"), f"{stack} capture experiment")
    if experiment.get("selected_stack") != stack:
        _fail(f"{stack} capture selected_stack differs")
    result = _object(report.get("result"), f"{stack}.capture.report.result")
    if result.get("run_id") != run_id or result.get("status") != "stopped":
        _fail(f"{stack} capture result identity/status differs")
    epochs = result.get("epochs")
    if not isinstance(epochs, list) or len(epochs) != 1 or not isinstance(epochs[0], dict):
        _fail(f"{stack} capture must contain exactly one epoch")
    epoch_result = _object(epochs[0].get("result"), f"{stack}.capture epoch result")
    if epochs[0].get("epoch") != epoch or epoch_result.get("run_id") != run_id or epoch_result.get("epoch") != epoch:
        _fail(f"{stack} capture epoch identity differs")
    _epoch(epochs[0].get("epoch"), f"{stack}.capture epoch")
    _epoch(epoch_result.get("epoch"), f"{stack}.capture epoch result.epoch")
    if report.get("manager_returncode") != 0:
        _fail(f"{stack} manager return code is not zero")
    archive, archive_file_sha, archive_path = _verify_hashed_json(capture["archive"], f"{stack}.capture.archive", repo_root)
    if capture_root_path not in archive_path.parents:
        _fail(f"{stack} archive is outside its resolved capture root")
    archive_entry = _object(capture["archive"], f"{stack}.capture.archive")
    archive_sha = _sha(archive_entry.get("archive_sha256"), f"{stack}.capture.archive.archive_sha256")
    if archive.get("sha256") != archive_sha:
        _fail(f"{stack} archive.json internal SHA differs")
    return report, report_sha, {"report": report_file_name(report_path), "report_sha256": report_sha,
                               "archive": archive_file_name(Path(_string(archive_entry["path"], "archive.path"))),
                               "archive_file_sha256": archive_file_sha, "archive_sha256": archive_sha}


def report_file_name(path: Path) -> str:
    return path.as_posix()


def archive_file_name(path: Path) -> str:
    return path.as_posix()


def _require_scope(report: dict[str, Any], expected: str, label: str) -> None:
    if report.get("scope") != expected:
        _fail(f"{label}.scope differs from the frozen scope")


def _require_native_raw_sha(report: dict[str, Any], stack: str, expected: str, label: str) -> None:
    raw_sha = report.get("raw_sha256")
    if isinstance(raw_sha, str):
        if raw_sha != expected:
            _fail(f"{label}.raw_sha256 does not bind to the pinned raw capture")
        return
    if not isinstance(raw_sha, dict):
        _fail(f"{label}.raw_sha256 must be a SHA-256 string or map")
    matches = [value for key, value in raw_sha.items()
               if isinstance(key, str) and "/" + stack + "/aruco-raw-dds.jsonl" in key.replace("\\", "/")]
    if len(matches) != 1 or matches[0] != expected:
        _fail(f"{label}.raw_sha256 does not bind to the pinned raw capture")


def _verify_reports(run: dict[str, Any], stack: str, capture_sha: str, repo_root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    epoch = run["epoch"]
    run_id = run["run_id"]
    capture_root_path = _secure_path(run["capture_root"], f"{stack}.capture_root", repo_root)
    reports = _object(run.get("reports"), f"{stack}.reports")
    loaded: dict[str, dict[str, Any]] = {}
    report_shas: dict[str, str] = {}
    for name in REPORTS:
        loaded[name], report_shas[name], _ = _verify_hashed_json(reports[name], f"{stack}.{name}", repo_root)

    raw_manifest = _object(reports["raw"], f"{stack}.reports.raw")
    raw_capture_sha = _sha(raw_manifest.get("raw_sha256"), f"{stack}.reports.raw.raw_sha256")

    physical = loaded["physical"]
    _require_status(physical, f"{stack}.physical")
    _require_no_failures(physical, f"{stack}.physical")
    if physical.get("report_sha256") != capture_sha:
        _fail(f"{stack}.physical.capture report SHA differs")

    rate = loaded["rate"]
    _require_status(rate, f"{stack}.rate")
    _require_no_failures(rate, f"{stack}.rate")
    _epoch(rate.get("epoch"), f"{stack}.rate.epoch")
    if rate.get("epoch") != epoch:
        _fail(f"{stack}.rate epoch differs")
    _require_scope(rate, RATE_SCOPE, f"{stack}.rate")

    raw = loaded["raw"]
    if raw.get("status") not in {"pass", "pending"}:
        _fail(f"{stack}.raw.status must be pass or pending")
    _epoch(raw.get("epoch"), f"{stack}.raw.epoch")
    if raw.get("run_id") != run_id or raw.get("epoch") != epoch:
        _fail(f"{stack}.raw identity differs")
    loss_hold = _object(raw.get("loss_hold"), f"{stack}.raw.loss_hold")
    if loss_hold.get("gate") != "closed":
        _fail(f"{stack}.raw loss_hold gate is not closed")
    _require_no_failures(raw, f"{stack}.raw")
    if _object(raw.get("entry"), f"{stack}.raw.entry").get("capture_report_sha256") != capture_sha:
        _fail(f"{stack}.raw capture report SHA differs")
    evidence = _object(raw.get("evidence_sha256"), f"{stack}.raw.evidence_sha256")
    raw_capture_matches = [value for key, value in evidence.items()
                           if isinstance(key, str) and "/" + stack + "/aruco-raw-dds.jsonl" in key.replace("\\", "/")]
    if len(raw_capture_matches) != 1 or raw_capture_matches[0] != raw_capture_sha:
        _fail(f"{stack}.raw evidence does not match the pinned raw capture SHA")
    raw_stacks = _object(raw.get("stacks"), f"{stack}.raw.stacks")
    if set(raw_stacks) != set(STACKS):
        _fail(f"{stack}.raw.stacks must contain both stacks")
    for candidate in STACKS:
        if _object(raw_stacks[candidate], f"{stack}.raw.stacks.{candidate}").get("selected") != (candidate == stack):
            _fail(f"{stack}.raw selected stack binding differs")
    shared_epoch = _object(raw.get("timeline"), f"{stack}.raw.timeline").get("shared_epoch")
    _epoch(shared_epoch, f"{stack}.raw.timeline.shared_epoch")
    if shared_epoch != epoch:
        _fail(f"{stack}.raw shared epoch differs")

    moves = loaded["native_moves"]
    _require_status(moves, f"{stack}.native_moves")
    _require_no_failures(moves, f"{stack}.native_moves")
    _require_scope(moves, MOVE_SCOPE, f"{stack}.native_moves")
    _require_native_raw_sha(moves, stack, raw_capture_sha, f"{stack}.native_moves")
    move_stack = _object(_object(moves.get("stacks"), f"{stack}.native_moves.stacks").get(stack),
                         f"{stack}.native_moves.stacks.{stack}")
    _epoch(move_stack.get("epoch"), f"{stack}.native_moves.epoch")
    if move_stack.get("run_id") != run_id or move_stack.get("epoch") != epoch or move_stack.get("stack") != stack:
        _fail(f"{stack}.native_moves identity differs")
    if not isinstance(move_stack.get("moves"), list) or not move_stack["moves"]:
        _fail(f"{stack}.native_moves has no proven moves")

    holds = loaded["native_holds"]
    _require_status(holds, f"{stack}.native_holds")
    _require_no_failures(holds, f"{stack}.native_holds")
    if holds.get("scope") != HOLD_SCOPE:
        _fail(f"{stack}.native_holds.scope differs from the frozen scope")
    _require_native_raw_sha(holds, stack, raw_capture_sha, f"{stack}.native_holds")
    _epoch(holds.get("epoch"), f"{stack}.native_holds.epoch")
    if holds.get("epoch") != epoch or holds.get("stack") != stack:
        _fail(f"{stack}.native_holds identity differs")
    if not isinstance(holds.get("holds"), dict) or not holds["holds"]:
        _fail(f"{stack}.native_holds has no HOLD windows")

    timestamps = loaded["native_timestamps"]
    _require_status(timestamps, f"{stack}.native_timestamps")
    _require_no_failures(timestamps, f"{stack}.native_timestamps")
    _require_scope(timestamps, TIMESTAMP_SCOPE, f"{stack}.native_timestamps")
    _require_native_raw_sha(timestamps, stack, raw_capture_sha, f"{stack}.native_timestamps")
    _epoch(timestamps.get("epoch"), f"{stack}.native_timestamps.epoch")
    if timestamps.get("epoch") != epoch or timestamps.get("stack") != stack:
        _fail(f"{stack}.native_timestamps identity differs")
    windows = _object(timestamps.get("windows"), f"{stack}.native_timestamps.windows")
    for window in ("move", "hold"):
        values = _object(windows.get(window), f"{stack}.native_timestamps.windows.{window}")
        if not isinstance(values.get("samples"), int) or values["samples"] <= 0 or values.get("verified") != values["samples"]:
            _fail(f"{stack}.native_timestamps {window} window is not fully verified")

    publishers = loaded["publishers"]
    verdict = _object(publishers.get("overall_verdict"), f"{stack}.publishers.overall_verdict")
    if verdict.get("status") != "snapshots_verified_and_bound":
        _fail(f"{stack}.publishers overall verdict is not snapshots_verified_and_bound")
    if verdict.get("writer_binding") != "verified_bound" or verdict.get("snapshot_exclusivity") != "verified_at_snapshots":
        _fail(f"{stack}.publishers writer/snapshot verdict differs")
    if publishers.get("stacks_audited") != list(STACKS):
        _fail(f"{stack}.publishers audited stack set differs")
    root_text = _canonical_path_text(publishers.get("run_root"))
    expected_root_text = _canonical_path_text(capture_root_path.as_posix())
    if root_text != expected_root_text:
        _fail(f"{stack}.publishers run_root is not the pinned capture root")
    publisher_evidence = _object(publishers.get("evidence_sha256"), f"{stack}.publishers.evidence_sha256")
    results = _object(publishers.get("results_by_stack"), f"{stack}.publishers.results_by_stack")
    if set(results) != set(STACKS):
        _fail(f"{stack}.publishers result stack set differs")
    publisher_identities: dict[str, dict[str, str]] = {}
    for candidate in STACKS:
        candidate_result = _object(results[candidate], f"{stack}.publishers.results_by_stack.{candidate}")
        if candidate_result.get("stack") != candidate:
            _fail(f"{stack}.publishers {candidate} stack identity differs")
        result_text = _normal_text(candidate_result)
        if candidate not in result_text or run_id.lower() not in result_text or epoch.lower() not in result_text:
            _fail(f"{stack}.publishers {candidate} result is not bound to this run/epoch")
        raw_capture = _object(candidate_result.get("raw_capture"),
                              f"{stack}.publishers.results_by_stack.{candidate}.raw_capture")
        raw_path_text = _canonical_path_text(
            raw_capture.get("path"),
            f"{stack}.publishers.results_by_stack.{candidate}.raw_capture.path",
        )
        raw_key, raw_sha = _raw_evidence_key(raw, candidate, epoch, f"{stack}.raw")
        expected_raw = capture_root_path.joinpath("run", *PurePosixPath(raw_key).parts)
        expected_raw_text = _canonical_path_text(
            expected_raw.as_posix(),
            f"{stack}.publishers canonical {candidate} raw path",
        )
        if raw_path_text != expected_raw_text:
            _fail(
                f"{stack}.publishers {candidate} raw_capture.path is not the canonical "
                f"{candidate} raw capture for this run/epoch"
            )
        raw_path = _secure_capture_child(
            capture_root_path,
            PurePosixPath("run", *PurePosixPath(raw_key).parts).as_posix(),
            f"{stack}.publishers {candidate} raw_capture.path",
        )
        actual_raw_sha = _digest(raw_path, f"{stack}.publishers {candidate} raw capture")
        if actual_raw_sha != raw_sha:
            _fail(f"{stack}.publishers {candidate} raw capture SHA differs from raw evidence")
        publisher_raw_key = PurePosixPath("run", *PurePosixPath(raw_key).parts).as_posix()
        publisher_raw_matches = [
            (key, value)
            for key, value in publisher_evidence.items()
            if isinstance(key, str)
            and key.replace("\\", "/").strip("/").lower() == publisher_raw_key
        ]
        if len(publisher_raw_matches) != 1:
            _fail(f"{stack}.publishers {candidate} evidence lacks its canonical raw capture")
        publisher_raw_sha = _sha(
            publisher_raw_matches[0][1],
            f"{stack}.publishers.evidence_sha256.{publisher_raw_matches[0][0]}",
        )
        if publisher_raw_sha != actual_raw_sha:
            _fail(f"{stack}.publishers {candidate} evidence SHA does not bind to its raw capture")
        if raw_capture.get("hash_chain_valid") is not True:
            _fail(f"{stack}.publishers {candidate} raw capture hash chain is not valid")
        start = _read_raw_start_identity(raw_path, f"{stack}.publishers {candidate} raw capture")
        if (
            start.get("kind") != "aruco_raw_capture_start"
            or start.get("run_id") != run_id
            or start.get("epoch") != epoch
            or start.get("stack") != candidate
        ):
            _fail(f"{stack}.publishers {candidate} raw capture identity differs")
        publisher_identities[candidate] = {
            "stack": candidate,
            "run_id": run_id,
            "epoch": epoch,
            "raw_capture_path": raw_path_text,
            "raw_capture_sha256": actual_raw_sha,
        }
    result = {name: loaded[name].get("status") for name in REPORTS}
    result["publishers"] = verdict["status"]
    direct = {
        "capture": {"run_id": run_id, "epoch": epoch, "selected_stack": stack},
        "rate": {"epoch": rate["epoch"], "scope": rate["scope"]},
        "raw": {"run_id": raw["run_id"], "epoch": raw["epoch"], "selected_stack": stack},
        "native_moves": {"run_id": move_stack["run_id"], "epoch": move_stack["epoch"],
                         "stack": move_stack["stack"], "scope": moves["scope"]},
        "native_holds": {"epoch": holds["epoch"], "stack": holds["stack"], "scope": holds["scope"]},
        "native_timestamps": {"epoch": timestamps["epoch"], "stack": timestamps["stack"],
                               "scope": timestamps["scope"]},
        "publishers": {"run_root": publishers["run_root"], "results_by_stack": publisher_identities},
    }
    transitive = {
        "physical_report_sha256": physical["report_sha256"],
        "raw_report_sha256": report_shas["raw"],
        "raw_capture_sha256": raw_capture_sha,
        "native_raw_sha256": raw_capture_sha,
    }
    return result, {"direct": direct, "transitive": transitive}


def _verify(manifest_path: Path) -> dict[str, Any]:
    manifest = _object(_read_json(manifest_path, "manifest"), "manifest")
    repo_root = Path(__file__).resolve().parents[1]
    _check_manifest(manifest, repo_root)
    runs = _object(manifest["runs"], "manifest.runs")
    identities: dict[str, dict[str, str]] = {}
    reports: dict[str, dict[str, str]] = {}
    identity_bindings: dict[str, dict[str, Any]] = {}
    for stack in STACKS:
        run = _object(runs[stack], f"manifest.runs.{stack}")
        report, capture_sha, archive_info = _verify_capture(run, stack, repo_root)
        del report
        reports[stack], identity_bindings[stack] = _verify_reports(run, stack, capture_sha, repo_root)
        identities[stack] = {"run_id": run["run_id"], "epoch": run["epoch"]}
        identities[stack].update(archive_info)
    if identities["arducopter"]["run_id"] == identities["px4"]["run_id"] or identities["arducopter"]["epoch"] == identities["px4"]["epoch"]:
        _fail("AP and PX4 closure entries must be distinct runs and epochs")
    return {
        "schema": SCHEMA,
        "status": "pass",
        "manifest": manifest_path.as_posix(),
        "tickets": manifest["tickets"],
        "runs": identities,
        "reports": reports,
        "identity_bindings": identity_bindings,
        "claim": "#104/#40 closure evidence is complete under the pinned JSON reports; Full remains separate",
    }


def audit(manifest: Path | str = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Return a machine-readable pass/fail result without writing any files."""
    path = Path(manifest)
    try:
        return _verify(path)
    except (ClosureAuditError, OSError, TypeError, ValueError) as error:
        return {
            "schema": SCHEMA,
            "status": "failed",
            "manifest": path.as_posix(),
            "failures": [{"code": "closure_invariant_failed", "message": str(error)}],
        }


def write_report(report: dict[str, Any], output: Path | str) -> None:
    """Exclusively create a standards-compliant JSON audit report."""
    output_path = Path(output)
    with output_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("--manifest", dest="manifest_option", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.manifest is not None and args.manifest_option is not None:
        parser.error("provide the manifest either positionally or with --manifest, not both")
    report = audit(args.manifest_option or args.manifest or DEFAULT_MANIFEST)
    try:
        write_report(report, args.output)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": report["status"], "output": args.output.as_posix()}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
