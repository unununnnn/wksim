#!/usr/bin/env python3
"""Offline negative-case executor for wksim release auditors.

Purpose
-------
Given a *complete raw evidence directory* (read-only baseline) and an auditor
module exposing ``audit(root) -> report`` that rejects by raising, this tool:

1. snapshots the SHA-256 of every file in the baseline,
2. builds one isolated copy per scenario in its own temporary directory,
3. applies exactly one deliberate corruption per scenario,
4. runs the real ``audit()`` against the copy,
5. records the outcome and whether the baseline changed.

A scenario "passes" only when the auditor actually **raises** on it. An
auditor that raises on everything does not pass, because an unmodified positive
copy must still be accepted.

Isolation rules (hard requirements)
----------------------------------
* The raw root is never opened for writing.  Mutations are written to a
  sibling temporary file and moved into place with ``os.replace``, so a
  hardlinked file is never written through to the original inode.
* Large files are hardlinked into the copy to avoid duplicating evidence;
  every file that a scenario changes is atomically replaced by an independent
  copy first.
* The raw root and every temporary/output root must be distinct and
  non-nested.  The raw root must not look like a whole workspace checkout.
* Clean-up only ever removes a directory this tool created, after verifying
  its name prefix and that it is disjoint from the raw root.

Message decoding
----------------
Command/setup payload tampering uses the *frozen generated messages* through
``rclpy.serialization.deserialize_message`` / ``serialize_message``.  CDR byte
offsets are never guessed.  If the generated message packages are not
importable the scenario is reported as ``env_missing`` (blocked), never as a
rejection or a pass.

This tool never launches ROS nodes, native binaries, builds, or flights.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

OWN_TEMP_PREFIX = "wksim-audit-probe-"
PROBE_TMP_SUFFIX = ".probe-new"
DEFAULT_HARDLINK_MIN_BYTES = 1 << 20
DEFAULT_REJECT_EXCEPTIONS = ("ValueError", "AssertionError")

REQUIRED_SCENARIOS = (
    "ledger_command_gap",
    "command_payload_tamper",
    "ledger_tail_truncation",
    "retained_source_change",
)
OPTIONAL_SCENARIOS = ("setup_mode_tamper",)

# Topic -> frozen message type.  Taken from the auditor's own routing table so
# that identification never depends on guessed byte layouts.
ROS_TOPIC_TYPES = {
    "/uav1/prometheus/text_info": "prometheus_msgs/msg/TextInfo",
    "/uav2/prometheus/text_info": "prometheus_msgs/msg/TextInfo",
    "/uav1/prometheus/v2/setup": "wksim_msgs/msg/SetupRequest",
    "/uav2/prometheus/v2/setup": "wksim_msgs/msg/SetupRequest",
    "/uav1/prometheus/v2/command": "wksim_msgs/msg/CommandRequest",
    "/uav2/prometheus/v2/command": "wksim_msgs/msg/CommandRequest",
    "/uav1/prometheus/v2/state": "wksim_msgs/msg/SessionState",
    "/uav2/prometheus/v2/state": "wksim_msgs/msg/SessionState",
}
AP_COMMAND_TOPIC = "/uav1/prometheus/v2/command"
AP_SETUP_TOPIC = "/uav1/prometheus/v2/setup"

# Evidence files the scenarios target, relative to the raw root.
LEDGER_REL = "arducopter/prometheus.jsonl"
CAPTURE_REL = "pv-dds.jsonl"
RESULT_REL = "result.json"
CONTROL_BUILD_REL = "control-build.json"

# The exact file set a release auditor reads.  The isolated copy contains
# nothing else: unlisted runtime/vendor trees are never duplicated.
AUDIT_INPUTS = (
    "result.json",
    "control-build.json",
    "arducopter/planner-release/planner-release-handoff.json",
    "arducopter-truth.jsonl",
    "px4-truth.jsonl",
    "rate.jsonl",
    "pv-dds.jsonl",
    "arducopter/prometheus.jsonl",
    "arducopter/result.json",
    "px4/prometheus.jsonl",
    "px4/result.json",
)

# Directories that must never be pulled into a probe copy.
FORBIDDEN_INPUT_PREFIXES = ("vendor/", "native-source/")


class ProbeError(Exception):
    """A defect in the probe invocation or environment, not a scenario result."""


class EnvMissing(Exception):
    """A required decoder/environment is absent; the scenario is blocked."""


# --------------------------------------------------------------------------
# hashing helpers
# --------------------------------------------------------------------------

def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> dict:
    """SHA-256 of every regular file in ``root`` keyed by POSIX relative path."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                out[rel] = "symlink:" + os.readlink(path)
            elif path.is_file():
                out[rel] = sha256_file(path)
    return out


# --------------------------------------------------------------------------
# path-safety helpers
# --------------------------------------------------------------------------

def is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def assert_disjoint(raw: Path, other: Path, other_label: str) -> None:
    raw = raw.resolve()
    other = other.resolve()
    if raw == other:
        raise ProbeError(f"{other_label} root equals the raw baseline root: {raw}")
    if is_within(other, raw) or is_within(raw, other):
        raise ProbeError(
            f"{other_label} root and raw baseline root must not be nested: "
            f"{other} vs {raw}"
        )


def assert_not_workspace_root(raw: Path) -> None:
    """Refuse a baseline that is really a whole checkout (no bulk copying)."""
    markers = (".git", "SOURCE_SNAPSHOT.json")
    present = [m for m in markers if (raw / m).exists()]
    if present:
        raise ProbeError(
            f"raw root {raw} looks like a source checkout ({', '.join(present)}); "
            "point --raw-root at a single evidence directory instead"
        )
    if raw.resolve() == Path(raw.resolve().anchor):
        raise ProbeError(f"raw root must not be a filesystem root: {raw}")
    if raw.resolve() == Path.home().resolve():
        raise ProbeError(f"raw root must not be the home directory: {raw}")


def safe_cleanup(work_root: Path, raw_root: Path) -> dict:
    """Remove only a directory this tool created, proven disjoint from raw."""
    work_root = Path(work_root)
    if not work_root.exists():
        return {"removed": False, "reason": "absent", "path": str(work_root)}
    if not work_root.name.startswith(OWN_TEMP_PREFIX):
        return {"removed": False, "reason": "name prefix is not probe-owned",
                "path": str(work_root)}
    try:
        assert_disjoint(raw_root, work_root, "work")
    except ProbeError as exc:
        return {"removed": False, "reason": str(exc), "path": str(work_root)}
    shutil.rmtree(work_root)
    return {"removed": True, "reason": "verified probe-owned directory",
            "path": str(work_root)}


# --------------------------------------------------------------------------
# audit input resolution + isolated copy
# --------------------------------------------------------------------------

def refuse_forbidden(rel: str) -> str:
    """Reject an input under a directory the probe must not duplicate."""
    normalized = rel.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        raise ProbeError(f"audit input must be a relative in-root path: {rel}")
    for prefix in FORBIDDEN_INPUT_PREFIXES:
        if normalized.startswith(prefix):
            raise ProbeError(
                f"refusing unlisted {prefix.rstrip('/')} input: {rel}")
    return normalized


def _source_file_for(name: str, prefix: str = "") -> str:
    return "source__" + prefix + name.replace("/", "__") + ".txt"


def resolve_audit_inputs(raw_root: Path) -> dict:
    """Resolve the exact set of files the auditor reads.

    Returns ``{"files": {rel: path}, "missing": [rel], "derived": [...]}``.
    Retained-source names are derived from the report's own manifests
    (``result.source_sha256`` and ``control-build.simulator_python_sha256``),
    never guessed.
    """
    files = {}
    missing = []
    for rel in AUDIT_INPUTS:
        rel = refuse_forbidden(rel)
        path = raw_root / rel
        if path.is_file():
            files[rel] = path
        else:
            missing.append(rel)

    derived = []
    manifests = ((RESULT_REL, "source_sha256", ""),
                 (CONTROL_BUILD_REL, "simulator_python_sha256", "Simulator__"))
    for manifest_rel, key, prefix in manifests:
        manifest_path = raw_root / manifest_rel
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except ValueError:
            continue
        for name in sorted(manifest.get(key, {}) or {}):
            rel = refuse_forbidden(_source_file_for(name, prefix))
            path = raw_root / rel
            if path.is_file():
                files[rel] = path
                derived.append(rel)
            else:
                missing.append(rel)
    return {"files": files, "missing": missing, "derived": derived}


def build_isolated_copy(inputs: dict, dest: Path,
                        hardlink_min_bytes: int) -> dict:
    """Materialise only the resolved audit inputs under ``dest``.

    Large files are hardlinked for read-only sharing; smaller files are
    duplicated.  Nothing outside ``inputs`` is copied.
    """
    if dest.exists():
        raise ProbeError(f"isolated copy target already exists: {dest}")
    dest.mkdir(parents=True)
    linked = copied = 0
    for rel, src in sorted(inputs.items()):
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        linked_ok = False
        if hardlink_min_bytes >= 0:
            try:
                if src.stat().st_size >= hardlink_min_bytes:
                    os.link(src, dst)
                    linked_ok = True
            except OSError:
                linked_ok = False
        if linked_ok:
            linked += 1
        else:
            shutil.copy2(src, dst)
            copied += 1
    return {"linked": linked, "copied": copied, "files": len(inputs)}


def atomic_replace_bytes(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` without ever writing through a hardlink."""
    tmp = path.with_name(path.name + PROBE_TMP_SUFFIX)
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_payload(path: Path) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


# --------------------------------------------------------------------------
# scenario mutations
# --------------------------------------------------------------------------

def _iter_json_lines(path: Path):
    with open(path, "rb") as handle:
        for lineno, raw in enumerate(handle, 1):
            if raw.strip():
                yield lineno, raw


def delete_first_topic_and_renumber(src: Path, topic: str) -> dict:
    """Delete the first row on ``topic`` and renumber ``sequence`` from 1.

    Renumbering is deliberate: it hides the removal from any check that only
    verifies local receive-sequence continuity.
    """
    target_lineno = None
    removed = None
    for lineno, raw in _iter_json_lines(src):
        row = json.loads(raw)
        if row.get("topic") == topic:
            target_lineno = lineno
            removed = row
            break
    if target_lineno is None:
        raise ProbeError(f"{src}: no row on topic {topic!r} to delete")

    out = bytearray()
    new_sequence = 0
    for lineno, raw in _iter_json_lines(src):
        if lineno == target_lineno:
            continue
        row = json.loads(raw)
        new_sequence += 1
        row["sequence"] = new_sequence
        out += json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n"
    atomic_replace_bytes(src, bytes(out))
    return {
        "topic": topic,
        "deleted_line": target_lineno,
        "deleted_sequence": removed.get("sequence"),
        "deleted_tick": removed.get("tick"),
        "remaining_rows": new_sequence,
        "renumbered": True,
    }


def truncate_from_last_publication(src: Path) -> dict:
    """Drop the last publication envelope and every line after it.

    Cutting a fixed number of trailing lines is not enough: a ledger's final
    lines are ordinary receive records, so a naive tail cut removes telemetry
    rather than a publication and the auditor is right to accept it.  This
    anchors on the last ``request_envelope`` row and records exactly which
    publication disappeared, plus how much unrelated telemetry went with it.
    """
    total = 0
    last_lineno = None
    with open(src, "rb") as handle:
        for lineno, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            total += 1
            if json.loads(raw).get("request_envelope"):
                last_lineno = lineno
    if last_lineno is None:
        raise ProbeError(
            f"{src}: no request_envelope publication record to truncate")

    kept = bytearray()
    dropped = 0
    publications = []
    non_publication = 0
    with open(src, "rb") as handle:
        for lineno, raw in enumerate(handle, 1):
            if lineno < last_lineno:
                kept += raw
                continue
            if not raw.strip():
                continue
            dropped += 1
            row = json.loads(raw)
            if row.get("request_envelope"):
                message = row.get("message") or {}
                publications.append({
                    "line": lineno,
                    "request_id": message.get("request_id"),
                    "published": row.get("published"),
                    "wall": row.get("wall"),
                })
            else:
                non_publication += 1

    if len(publications) != 1:
        raise ProbeError(
            f"{src}: expected exactly one publication at the truncation point, "
            f"found {len(publications)}")
    atomic_replace_bytes(src, bytes(kept))
    return {
        "truncated_from_line": last_lineno,
        "removed_request_id": publications[0]["request_id"],
        "removed_published": publications[0]["published"],
        "removed_wall": publications[0]["wall"],
        "removed_publication": publications[0],
        "publications_dropped": len(publications),
        "non_publication_dropped": non_publication,
        "dropped_lines": dropped,
        "total_records_before": total,
        "remaining_records": total - dropped,
    }


def append_marker_to_retained_source(src: Path, marker: bytes) -> dict:
    before = sha256_file(src)
    data = read_payload(src)
    atomic_replace_bytes(src, data + marker)
    return {"file": src.name, "sha256_before": before,
            "sha256_after": sha256_file(src), "appended_bytes": len(marker)}


def choose_retained_source(raw_root: Path, allowed_rels=None) -> dict:
    """Prefer a retained source the auditor actually hashes in result.json."""
    allowed = None if allowed_rels is None else set(allowed_rels)
    result_path = raw_root / RESULT_REL
    chosen = None
    reason = ""
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text())
        except ValueError as exc:
            result = {}
            reason = f"{RESULT_REL} unreadable ({exc}); "
        for name in sorted(result.get("source_sha256", {}) or {}):
            rel = _source_file_for(name)
            candidate = raw_root / rel
            if candidate.is_file() and (allowed is None or rel in allowed):
                chosen = candidate
                reason += "listed in result.json source_sha256"
                break
    if chosen is None:
        candidates = [p for p in sorted(raw_root.glob("source__*.txt"))
                      if allowed is None or p.name in allowed]
        if not candidates:
            raise ProbeError(
                f"{raw_root}: no retained source present in the resolved "
                "audit inputs")
        chosen = candidates[0]
        reason += "first resolved source__*.txt fallback"
    return {"path": chosen, "reason": reason}


# --------------------------------------------------------------------------
# message codec
# --------------------------------------------------------------------------

class RosCodec:
    """Frozen generated messages via rclpy; never guesses CDR offsets."""

    name = "rosidl/rclpy frozen generated messages"

    def __init__(self) -> None:
        try:
            from rclpy.serialization import deserialize_message, serialize_message
            from rosidl_runtime_py.utilities import get_message
        except ImportError as exc:  # pragma: no cover - env dependent
            raise EnvMissing(
                f"generated message runtime unavailable ({exc}); "
                "source a workspace providing rclpy, prometheus_msgs and wksim_msgs"
            ) from exc
        self._deserialize = deserialize_message
        self._serialize = serialize_message
        self._get_message = get_message
        self._cache = {}
        self._probe_packages()

    def _probe_packages(self) -> None:
        needed = sorted(set(ROS_TOPIC_TYPES.values()))
        missing = []
        for name in needed:
            try:
                self._cache[name] = self._get_message(name)
            except Exception as exc:  # noqa: BLE001 - report precisely
                missing.append(f"{name} ({exc})")
        if missing:
            raise EnvMissing("frozen generated messages unavailable: "
                             + "; ".join(missing))

    def deserialize(self, topic: str, raw: bytes):
        return self._deserialize(raw, self._cache[ROS_TOPIC_TYPES[topic]])

    def serialize(self, topic: str, message) -> bytes:
        return self._serialize(message)


def load_codec(module_path: str | None):
    """Return a codec.  Default is the ROS generated-message codec."""
    if module_path is None:
        return RosCodec()
    path = Path(module_path)
    if not path.is_file():
        raise ProbeError(f"codec module not found: {path}")
    path = path.resolve(strict=True)
    spec = importlib.util.spec_from_file_location("probe_codec_under_test", path)
    if spec is None or spec.loader is None:
        raise ProbeError(f"cannot load codec module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    factory = getattr(module, "make_codec", None)
    if factory is None:
        raise ProbeError(f"codec module {path} does not expose make_codec()")
    return factory()


_MISSING = object()


def _get(obj, key):
    if isinstance(obj, dict):
        return obj.get(key, _MISSING)
    return getattr(obj, key, _MISSING)


def _set(obj, key, value) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def _perturb_numeric(obj, path, delta):
    """Walk ``path`` and scale the addressed number; return (old, new)."""
    cursor = obj
    for step in path[:-1]:
        cursor = _get(cursor, step)
        if cursor is _MISSING or cursor is None:
            return None
    leaf = path[-1]
    if isinstance(leaf, int):
        container = cursor
        try:
            old = container[leaf]
        except (IndexError, KeyError, TypeError):
            return None
    else:
        old = _get(cursor, leaf)
        container = cursor
    if old is _MISSING or old is None:
        return None
    if isinstance(old, bool) or not isinstance(old, (int, float)):
        return None
    new = float(old) + delta
    if isinstance(leaf, int):
        container[leaf] = new
    else:
        _set(container, leaf, new)
    return float(old), new


def tamper_command_payload(topic: str, raw: bytes, codec) -> tuple:
    """Change one numeric payload item while preserving ids.

    Returns ``(new_bytes, detail)``.  Raises :class:`ProbeError` when no
    addressable numeric field can be found, rather than guessing byte offsets.
    """
    message = codec.deserialize(topic, raw)
    candidates = (
        ("command", "velocity_ref", 0),
        ("command", "position_ref", 0),
        ("command", "acceleration_ref", 0),
        ("command", "yaw_ref"),
        ("velocity_ref", 0),
        ("position_ref", 0),
    )
    for path in candidates:
        outcome = _perturb_numeric(message, path, 0.5)
        if outcome is not None:
            old, new = outcome
            return codec.serialize(topic, message), {
                "field": ".".join(str(p) for p in path),
                "old": old, "new": new, "ids_preserved": True,
            }
    raise ProbeError("no perturbable command payload field found via the "
                     "generated message; refusing to guess CDR offsets")


def tamper_setup_mode(topic: str, raw: bytes, codec, wrong_mode: str) -> tuple:
    """Change a setup mode while preserving ids and command identity."""
    message = codec.deserialize(topic, raw)
    for path in (("setup", "px4_mode"), ("px4_mode",)):
        cursor = message
        ok = True
        for step in path[:-1]:
            cursor = _get(cursor, step)
            if cursor is _MISSING or cursor is None:
                ok = False
                break
        if not ok:
            continue
        old = _get(cursor, path[-1])
        if isinstance(old, str):
            _set(cursor, path[-1], wrong_mode)
            return codec.serialize(topic, message), {
                "field": ".".join(path), "old": old, "new": wrong_mode,
                "ids_preserved": True,
            }
    raise ProbeError("no perturbable setup mode field found via the generated "
                     "message; refusing to guess CDR offsets")


def rewrite_row_at_topic(src: Path, topic: str, transform) -> dict:
    """Apply ``transform(topic, cdr_hex)`` to the first row on ``topic``."""
    lines = []
    chosen = None
    with open(src, "rb") as handle:
        for raw in handle:
            if not raw.strip():
                lines.append(raw)
                continue
            row = json.loads(raw)
            if chosen is None and row.get("topic") == topic:
                new_hex, detail = transform(topic, bytes.fromhex(row["cdr_hex"]))
                detail = dict(detail)
                detail["topic"] = topic
                detail["sequence"] = row.get("sequence")
                detail["tick"] = row.get("tick")
                detail["cdr_sha256_before"] = hashlib.sha256(
                    bytes.fromhex(row["cdr_hex"])).hexdigest()
                detail["cdr_sha256_after"] = hashlib.sha256(new_hex).hexdigest()
                row["cdr_hex"] = new_hex.hex()
                chosen = detail
            lines.append(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    if chosen is None:
        raise ProbeError(f"{src}: no row on topic {topic!r} to rewrite")
    atomic_replace_bytes(src, b"".join(lines))
    return chosen


# --------------------------------------------------------------------------
# auditor loading + invocation
# --------------------------------------------------------------------------

def load_auditor(path: Path):
    path = Path(path).resolve(strict=True)
    spec = importlib.util.spec_from_file_location("auditor_under_test", path)
    if spec is None or spec.loader is None:
        raise ProbeError(f"cannot load auditor module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "audit"):
        raise ProbeError(f"auditor {path} does not expose audit(root)")
    return module


def invoke_audit(module, root: Path, reject_types) -> dict:
    """Call audit(root) once and classify the outcome."""
    try:
        report = module.audit(str(root))
    except ImportError as exc:
        return {"outcome": "env_missing",
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()}
    except reject_types as exc:
        return {"outcome": "rejected",
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()}
    except Exception as exc:  # noqa: BLE001 - classify unexpected raises
        return {"outcome": "error",
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()}
    accepted = None
    if isinstance(report, dict):
        accepted = report.get("status")
    if accepted != "pass":
        return {"outcome": "error", "report_status": accepted,
                "exception": "audit() returned without a pass verdict"}
    return {"outcome": "accepted", "report_status": accepted,
            "report_keys": sorted(report)[:24] if isinstance(report, dict) else None}


# --------------------------------------------------------------------------
# scenario execution
# --------------------------------------------------------------------------

def _target_sha(raw_root: Path, rels) -> dict:
    out = {}
    for rel in rels:
        path = raw_root / rel
        if path.is_file():
            out[rel] = sha256_file(path)
    return out


def run_probe(args) -> dict:
    raw_root = Path(args.raw_root).resolve(strict=True)
    auditor_file = Path(args.auditor_file).resolve(strict=True)
    output_dir = Path(args.output_dir).resolve()
    assert_not_workspace_root(raw_root)

    if not (raw_root / RESULT_REL).is_file():
        raise ProbeError(f"{raw_root} does not look like an evidence root "
                         f"(missing {RESULT_REL})")

    assert_disjoint(raw_root, output_dir, "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    work_root = Path(tempfile.mkdtemp(prefix=OWN_TEMP_PREFIX)).resolve()
    assert_disjoint(raw_root, work_root, "work")
    log_lines = []

    def log(message):
        log_lines.append(message)
        print(message, flush=True)

    log(f"raw baseline : {raw_root}")
    log(f"auditor      : {auditor_file}")
    log(f"work root    : {work_root}")
    log(f"output dir   : {output_dir}")

    sha_before = tree_sha256(raw_root)
    log(f"baseline files hashed: {len(sha_before)}")

    inputs = resolve_audit_inputs(raw_root)
    log(f"audit inputs : {len(inputs['files'])} files "
        f"({len(inputs['derived'])} retained sources derived from manifests)")
    if inputs["missing"]:
        log(f"audit inputs missing from baseline: {inputs['missing']}")
    assert_disjoint(raw_root, output_dir, "output")

    codec = None
    codec_error = None
    try:
        codec = load_codec(args.codec_module)
        log(f"codec        : {getattr(codec, 'name', type(codec).__name__)}")
    except (EnvMissing, ProbeError, ImportError) as exc:
        codec_error = f"{type(exc).__name__}: {exc}"
        log(f"codec unavailable: {codec_error}")

    reject_types = _resolve_exceptions(args.reject_exception)

    try:
        auditor = load_auditor(auditor_file)
    except ImportError as exc:
        log(f"auditor import failed: {type(exc).__name__}: {exc}")
        raise ProbeError(f"auditor {auditor_file} could not be imported: {exc}") from exc
    auditor_sha = sha256_file(auditor_file)
    log(f"auditor sha  : {auditor_sha}")

    selected = list(args.scenario) if args.scenario else list(REQUIRED_SCENARIOS)
    if args.with_setup_tamper and "setup_mode_tamper" not in selected:
        selected.append("setup_mode_tamper")

    scenarios = []

    # ---- positive control: unmodified isolated copy -----------------------
    positive_dir = work_root / "positive-unmodified"
    log("\n== positive control: unmodified isolated copy ==")
    copy_stats = build_isolated_copy(inputs["files"], positive_dir,
                                     args.hardlink_min_bytes)
    result = invoke_audit(auditor, positive_dir, reject_types)
    scenarios.append({
        "name": "positive_unmodified",
        "kind": "positive",
        "expectation": "accepted",
        "mutations": [],
        "copy": copy_stats,
        "source_sha256": _target_sha(raw_root, [LEDGER_REL, CAPTURE_REL, RESULT_REL]),
        **result,
    })
    log(f"   outcome={result['outcome']} {result.get('exception', '')}")

    # ---- negatives --------------------------------------------------------
    for name in selected:
        case_dir = work_root / name
        stats = build_isolated_copy(inputs["files"], case_dir,
                                    args.hardlink_min_bytes)
        entry = {"name": name, "kind": "negative", "expectation": "rejected",
                 "mutations": [], "copy": stats}
        log(f"\n== scenario: {name} ==")
        try:
            entry["mutations"] = apply_scenario(
                name, raw_root, case_dir, codec, codec_error,
                allowed_rels=set(inputs["files"]))
        except EnvMissing as exc:
            entry.update({"outcome": "env_missing",
                          "exception": f"EnvMissing: {exc}"})
            log(f"   BLOCKED (environment): {exc}")
            scenarios.append(entry)
            continue
        except ImportError as exc:
            entry.update({"outcome": "env_missing",
                          "exception": f"{type(exc).__name__}: {exc}"})
            log(f"   BLOCKED (missing message runtime): {exc}")
            scenarios.append(entry)
            continue
        except ProbeError as exc:
            entry.update({"outcome": "error",
                          "exception": f"ProbeError: {exc}"})
            log(f"   ERROR (probe): {exc}")
            scenarios.append(entry)
            continue
        entry["source_sha256"] = {
            m["original_rel"]: m["original_sha256"] for m in entry["mutations"]}
        entry["case_sha256"] = {
            m["case_rel"]: m["case_sha256"] for m in entry["mutations"]}
        for mutation in entry["mutations"]:
            log(f"   mutated {mutation['case_rel']}: {mutation['summary']}")
        result = invoke_audit(auditor, case_dir, reject_types)
        entry.update(result)
        log(f"   outcome={result['outcome']} {result.get('exception', '')}")
        scenarios.append(entry)

    sha_after = tree_sha256(raw_root)
    unchanged = sha_before == sha_after
    if not unchanged:
        changed = sorted(set(sha_before) ^ set(sha_after)) or [
            rel for rel in sha_before if sha_before.get(rel) != sha_after.get(rel)]
        log(f"\n!! BASELINE CHANGED: {changed[:10]}")

    verdict, reasons = decide(scenarios, baseline_unchanged=unchanged)
    report = {
        "kind": "offline release-audit negative-case probe",
        "raw_root": str(raw_root),
        "auditor_file": str(auditor_file),
        "auditor_sha256": auditor_sha,
        "output_dir": str(output_dir),
        "work_root": str(work_root),
        "hardlink_min_bytes": args.hardlink_min_bytes,
        "codec": getattr(codec, "name", None) if codec else None,
        "codec_error": codec_error,
        "reject_exceptions": list(args.reject_exception),
        "audit_inputs": {
            "count": len(inputs["files"]),
            "resolved": sorted(inputs["files"]),
            "derived_retained_sources": sorted(inputs["derived"]),
            "missing": sorted(inputs["missing"]),
            "excluded_prefixes": list(FORBIDDEN_INPUT_PREFIXES),
        },
        "baseline": {
            "file_count": len(sha_before),
            "sha256_before": sha_before,
            "sha256_after": sha_after,
            "unchanged": unchanged,
        },
        "scenarios": scenarios,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "limitations": limitations(scenarios, codec, codec_error),
    }

    if args.cleanup_own_work:
        report["cleanup"] = safe_cleanup(work_root, raw_root)
        log(f"\ncleanup: {report['cleanup']}")
    else:
        report["cleanup"] = {"removed": False, "reason": "kept (default)",
                             "path": str(work_root)}

    (output_dir / "probe-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "probe.log").write_text("\n".join(log_lines) + "\n",
                                          encoding="utf-8")
    log(f"\nverdict: {verdict}")
    return report


def _resolve_exceptions(names):
    import builtins as _builtins
    resolved = []
    for name in names:
        obj = getattr(_builtins, name, None)
        if not (isinstance(obj, type) and issubclass(obj, BaseException)):
            raise ProbeError(f"--reject-exception {name!r} is not an exception type")
        resolved.append(obj)
    return tuple(resolved)


def _record(mutation: dict, raw_root: Path, case_dir: Path, rel: str,
            summary: str) -> dict:
    mutation.update({
        "original_rel": rel,
        "case_rel": rel,
        "original_sha256": sha256_file(raw_root / rel),
        "case_sha256": sha256_file(case_dir / rel),
        "summary": summary,
    })
    return mutation


def _require_file(case_dir: Path, rel: str) -> Path:
    path = case_dir / rel
    if not path.is_file():
        raise ProbeError(f"scenario target is missing from the baseline: {rel}")
    return path


def apply_scenario(name, raw_root, case_dir, codec, codec_error,
                   allowed_rels=None):
    """Apply one deliberate corruption; return a list of mutation records."""
    if name == "ledger_command_gap":
        rel = CAPTURE_REL
        detail = delete_first_topic_and_renumber(_require_file(case_dir, rel),
                                                 AP_COMMAND_TOPIC)
        summary = (f"deleted first {AP_COMMAND_TOPIC} row seq="
                   f"{detail['deleted_sequence']} and renumbered "
                   f"{detail['remaining_rows']} rows")
        return [_record(detail, raw_root, case_dir, rel, summary)]

    if name == "command_payload_tamper":
        if codec is None:
            raise EnvMissing(codec_error or "no message codec available")

        def transform(topic, raw):
            return tamper_command_payload(topic, raw, codec)

        detail = rewrite_row_at_topic(_require_file(case_dir, CAPTURE_REL),
                                      AP_COMMAND_TOPIC, transform)
        summary = (f"rewrote {detail['field']} {detail['old']}->{detail['new']} "
                   f"keeping request/command ids")
        return [_record(detail, raw_root, case_dir, CAPTURE_REL, summary)]

    if name == "setup_mode_tamper":
        if codec is None:
            raise EnvMissing(codec_error or "no message codec available")

        def transform(topic, raw):
            return tamper_setup_mode(topic, raw, codec, "AUTO.LOITER")

        detail = rewrite_row_at_topic(_require_file(case_dir, CAPTURE_REL),
                                      AP_SETUP_TOPIC, transform)
        summary = (f"rewrote {detail['field']} {detail['old']}->{detail['new']} "
                   f"keeping request ids")
        return [_record(detail, raw_root, case_dir, CAPTURE_REL, summary)]

    if name == "ledger_tail_truncation":
        rel = LEDGER_REL
        detail = truncate_from_last_publication(_require_file(case_dir, rel))
        summary = (f"truncated from last publication line "
                   f"{detail['truncated_from_line']} "
                   f"(request_id={detail['removed_request_id']}, "
                   f"{detail['removed_published']}); dropped "
                   f"{detail['dropped_lines']} line(s), of which "
                   f"{detail['non_publication_dropped']} non-publication")
        mutation = _record(detail, raw_root, case_dir, rel, summary)
        # The completion report is deliberately left byte-identical.
        mutation["report_untouched"] = RESULT_REL
        return [mutation]

    if name == "retained_source_change":
        chosen = choose_retained_source(raw_root, allowed_rels)
        rel = chosen["path"].relative_to(raw_root).as_posix()
        detail = append_marker_to_retained_source(
            _require_file(case_dir, rel),
            b"\n# release-audit-probe tamper marker\n")
        detail["selection_reason"] = chosen["reason"]
        summary = "appended marker to retained source (sha changed)"
        return [_record(detail, raw_root, case_dir, rel, summary)]

    raise ProbeError(f"unknown scenario {name!r}")


def decide(scenarios, baseline_unchanged=True):
    if not baseline_unchanged:
        return "fail", ["raw baseline changed during the probe"]
    reasons = []
    positive = [s for s in scenarios if s["kind"] == "positive"]
    negatives = [s for s in scenarios if s["kind"] == "negative"]

    if any(s["outcome"] == "env_missing" for s in scenarios):
        reasons.append("at least one scenario could not run: missing message/"
                       "auditor environment (reported, not counted as a rejection)")
        return "blocked", reasons
    if not positive:
        reasons.append("no positive control scenario was run")
        return "fail", reasons
    if len(positive) > 1:
        reasons.append("multiple positive controls; expected exactly one")
    for entry in positive:
        if entry["outcome"] != "accepted":
            reasons.append(
                f"positive control was not accepted (outcome={entry['outcome']})")
    if not negatives:
        reasons.append("no negative scenarios were run")
    for entry in negatives:
        if entry["outcome"] != "rejected":
            reasons.append(
                f"negative scenario {entry['name']} was not rejected "
                f"(outcome={entry['outcome']})")
    if any(s["outcome"] == "error" for s in scenarios):
        reasons.append("at least one scenario raised an unexpected exception "
                       "type; classify it with --reject-exception if it is a "
                       "genuine rejection")
    return ("pass" if not reasons else "fail"), reasons


def limitations(scenarios, codec, codec_error):
    notes = []
    if codec is None:
        notes.append("message decoding unavailable, so payload-tamper scenarios "
                     "were blocked rather than executed: " + str(codec_error))
    else:
        notes.append("payload tampering uses frozen generated messages via "
                     "deserialize_message/serialize_message; CDR offsets are "
                     "never guessed")
    accepted_corruptions = [s["name"] for s in scenarios
                            if s["kind"] == "negative" and s["outcome"] == "accepted"]
    if accepted_corruptions:
        notes.append("auditor accepted these deliberate corruptions: "
                     + ", ".join(sorted(accepted_corruptions)))
    notes.append("a local receive-sequence check cannot by itself prove absence "
                 "of transmission loss; this probe only asserts that the "
                 "auditor rejects the corruption it is given")
    return notes


def build_parser():
    parser = argparse.ArgumentParser(
        description="Offline negative-case executor for wksim release auditors.")
    parser.add_argument("--raw-root", required=True,
                        help="complete raw evidence directory (read-only baseline)")
    parser.add_argument("--auditor-file", required=True,
                        help="auditor module exposing audit(root) -> report")
    parser.add_argument("--output-dir", required=True,
                        help="directory for probe-report.json and probe.log")
    parser.add_argument("--scenario", action="append", default=None,
                        choices=list(REQUIRED_SCENARIOS) + list(OPTIONAL_SCENARIOS),
                        help="run only this scenario (repeatable); default all required")
    parser.add_argument("--with-setup-tamper", action="store_true",
                        help="also run the optional setup-mode tamper scenario")
    parser.add_argument("--hardlink-min-bytes", type=int,
                        default=DEFAULT_HARDLINK_MIN_BYTES,
                        help="hardlink files at least this large (default 1 MiB); "
                             "-1 disables hardlinking")
    parser.add_argument("--codec-module", default=None,
                        help="path to a module exposing make_codec(); default is "
                             "the rclpy frozen generated-message codec")
    parser.add_argument("--reject-exception", action="append",
                        default=list(DEFAULT_REJECT_EXCEPTIONS),
                        help="exception class name treated as rejection "
                             "(default ValueError, AssertionError)")
    parser.add_argument("--cleanup-own-work", action="store_true",
                        help="remove the probe-owned work directory after a run")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = run_probe(args)
    except ProbeError as exc:
        print(f"probe error: {exc}", file=sys.stderr)
        return 2
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
