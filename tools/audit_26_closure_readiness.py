"""Fail-closed, offline closure-readiness audit for issue #26.

The audit checks a pinned evidence snapshot.  It deliberately does not query
GitHub: ``closure_blocker`` records the last observed state of issue #9 and
the local audit can only verify that the snapshot is still OPEN and intact.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/plan/26-closure-readiness-manifest.json"
MANIFEST_SCHEMA = "wksim.26-closure-readiness.v1"
AC_KEYS = (
    "source_chain",
    "matlab_license_actual_checkout",
    "matlab_free_lifecycle",
    "vendor_materials_controlled",
    "delivery_identity",
)
REQUIRED_STAGES = (
    "license_verification", "fileGenControl", "load_system", "verify_solver",
    "configure_target", "initialization", "slbuild", "artifact_verification",
    "close_model",
)
REQUIRED_LICENSES = (
    "SIMULINK", "Real_Time_Workshop", "RTW_Embedded_Coder",
    "Aerospace_Blockset", "Aerospace_Toolbox",
)
REQUIRED_GENERATED = {
    "Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "ert_main.cpp", "rtwtypes.h",
}
EXPECTED_PIN_PATHS = {
    "source_chain": {
        "docs/2026-09-10-generated-e0-lifecycle.md",
        "validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json",
    },
    "matlab_license_actual_checkout": {
        "validation/codegen-e0/short-cycle-codegen-01/codegen-report.json",
    },
    "matlab_free_lifecycle": {
        "validation/codegen-e0-lifecycle-01/audit.json",
    },
    "vendor_materials_controlled": {
        "validation/codegen-e0/short-cycle-codegen-01/summary.json",
    },
    "delivery_identity": {
        "validation/codegen-e0-build-short-cycle-01/build-manifest.json",
    },
}
ALLOWED_REPO_WRAPPERS = {
    "Simulator/wksim_core/model.cpp": "generated-model-wrapper",
}
PINNED_GENERATED_ROOT = "work/codegen-e0/short-cycle-codegen-01/codegen/"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
# Python exposes this on Windows; keep the documented value for POSIX hosts
# and older Python builds so the same lstat-based check remains portable.
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
EXPECTED_LIFECYCLE_RAW_KEYS = frozenset(
    {
        "original/cycle-0.jsonl",
        "original/cycle-1.jsonl",
        "cold/cycle-0.jsonl",
        "cold/cycle-1.jsonl",
    }
)


class AuditDataError(ValueError):
    """Malformed or incomplete evidence data."""


def _fail(report, message):
    report["violations"].append(str(message))
    return report


def _strict_object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditDataError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise AuditDataError(f"non-finite JSON number: {value}")


def _load_json(path, label):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AuditDataError(f"{label} cannot be read: {exc}") from exc
    try:
        return json.loads(
            raw,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, AuditDataError, TypeError) as exc:
        raise AuditDataError(f"{label} is malformed JSON: {exc}") from exc


def _object(value, label):
    if not isinstance(value, dict):
        raise AuditDataError(f"{label} must be a JSON object")
    return value


def _exact_keys(value, required, label, optional=()):
    _object(value, label)
    required = set(required)
    optional = set(optional)
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required - optional)
    if missing:
        raise AuditDataError(f"{label} missing fields: {missing}")
    if extra:
        raise AuditDataError(f"{label} has unexpected fields: {extra}")


def _string(value, label, *, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise AuditDataError(f"{label} must be a non-empty string")
    if CONTROL_RE.search(value):
        raise AuditDataError(f"{label} contains a control character")
    return value


def _strict_int(value, label, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuditDataError(f"{label} must be an integer")
    if positive and value <= 0:
        raise AuditDataError(f"{label} must be positive")
    if nonnegative and value < 0:
        raise AuditDataError(f"{label} must be non-negative")
    return value


def _strict_number(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditDataError(f"{label} must be a finite number")
    if not math.isfinite(value) or (positive and value <= 0):
        raise AuditDataError(f"{label} must be a finite positive number")
    return value


def _sha(value, label):
    _string(value, label)
    if not SHA256_RE.fullmatch(value):
        raise AuditDataError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _repo_relative(value, label):
    """Validate a canonical, slash-separated repository-relative path."""
    _string(value, label)
    if value != value.strip() or "\\" in value:
        raise AuditDataError(f"{label} must use canonical '/' separators")
    if WINDOWS_ABSOLUTE_RE.match(value) or value.startswith("/"):
        raise AuditDataError(f"{label} must be repository-relative")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise AuditDataError(f"{label} contains an empty or traversal path segment")
    return value


def _artifact_relative(value, label):
    """Validate legacy codegen-relative names without touching the repo.

    The generated-sources evidence predates this auditor and uses Windows
    separators.  It is a name relative to the private codegen directory, not
    a repository path; both separators are accepted after rejecting absolute
    and traversal forms.
    """
    _string(value, label)
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or WINDOWS_ABSOLUTE_RE.match(normalized):
        raise AuditDataError(f"{label} must be codegen-relative")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise AuditDataError(f"{label} contains an empty or traversal path segment")
    return normalized


def _absolute_source_path(value, label):
    """Validate an evidence provenance path, preserving Windows paths."""
    _string(value, label)
    if value.startswith("\\\\") or CONTROL_RE.search(value):
        raise AuditDataError(f"{label} has an invalid absolute path")
    if WINDOWS_ABSOLUTE_RE.match(value):
        normalized = value.replace("\\", "/")
        if any(part in ("", ".", "..") for part in normalized[3:].split("/")):
            raise AuditDataError(f"{label} has an invalid absolute path")
        return value
    if not value.startswith("/"):
        raise AuditDataError(f"{label} must be absolute provenance path")
    if any(part in ("", ".", "..") for part in value.split("/")[1:]):
        raise AuditDataError(f"{label} has an invalid absolute path")
    return value


def _is_reparse(path):
    """Return whether *path* is a link or Windows reparse point.

    ``Path.stat()`` follows directory junctions and other name-surrogate
    reparse points.  That makes a junction to an ordinary directory look
    ordinary and allows ``_secure_file`` to validate the wrong path.  ``lstat``
    inspects the directory entry itself on both POSIX and Windows; on Windows
    ``st_file_attributes`` retains ``FILE_ATTRIBUTE_REPARSE_POINT`` for a
    junction or mount reparse point.
    """
    try:
        metadata = path.lstat()
    except (AttributeError, OSError):
        return False
    return stat.S_ISLNK(getattr(metadata, "st_mode", 0)) or bool(
        getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT
    )


def _secure_file(root, relative, report, label="pinned evidence"):
    try:
        relative = _repo_relative(relative, f"{label} path")
    except AuditDataError as exc:
        _fail(report, str(exc))
        return None
    root = Path(root).resolve()
    candidate = root.joinpath(*relative.split("/"))
    cursor = root
    try:
        for part in relative.split("/"):
            cursor = cursor / part
            if cursor.is_symlink() or _is_reparse(cursor):
                _fail(report, f"{label} traverses a symlink or reparse point: {relative}")
                return None
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail(report, f"{label} escapes repository or is missing: {relative}")
        return None
    if not resolved.is_file() or resolved.is_symlink() or _is_reparse(resolved):
        _fail(report, f"{label} is not a regular file: {relative}")
        return None
    return resolved


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _actual_file(path, label, report, *, sha256=None, size_bytes=None):
    """Verify a retained or provenance file instead of trusting its metadata."""
    path = Path(path)
    try:
        if path.is_symlink() or _is_reparse(path) or not path.is_file():
            raise AuditDataError(f"{label} is not a regular file: {path}")
        observed_size = path.stat().st_size
        observed_sha = digest(path)
    except (AuditDataError, OSError, ValueError) as exc:
        _fail(report, str(exc))
        return False
    if size_bytes is not None and observed_size != size_bytes:
        _fail(report, f"{label} size drifted: expected {size_bytes}, observed {observed_size}: {path}")
        return False
    if sha256 is not None and observed_sha != sha256:
        _fail(report, f"{label} hash drifted: expected {sha256}, observed {observed_sha}: {path}")
        return False
    return True


def _provenance_path(value, root, label, report):
    """Resolve an absolute provenance path without treating it as repository data."""
    try:
        _absolute_source_path(value, label)
    except AuditDataError as exc:
        _fail(report, str(exc))
        return None
    candidate = _as_host_path(value, root)
    if candidate is None:
        _fail(report, f"{label} cannot be mapped on this host: {value}")
        return None
    candidate = Path(candidate)
    try:
        if not candidate.is_absolute():
            raise AuditDataError(f"{label} was treated as a relative path")
        # Check every existing component with lstat before resolving.  A
        # resolved path alone is insufficient: a symlink/reparse point can
        # escape the intended Windows drive or provenance boundary.
        for component in (candidate, *candidate.parents):
            try:
                metadata = component.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise AuditDataError(f"{label} cannot inspect path component {component}: {exc}") from exc
            if stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & REPARSE_POINT):
                raise AuditDataError(f"{label} traverses a symlink or reparse point: {value}")

        resolved = candidate.resolve(strict=False)
        boundary = _provenance_boundary(value, root)
        if boundary is not None:
            boundary = boundary.resolve(strict=False)
            try:
                resolved.relative_to(boundary)
            except ValueError as exc:
                raise AuditDataError(f"{label} escapes its mapped drive: {value}") from exc
    except (AuditDataError, OSError, RuntimeError, ValueError) as exc:
        _fail(report, str(exc))
        return None
    return candidate


def _check_source_actual(item, basename, root, report, label):
    """Rehash every readable source and bind model.cpp to the fixed repo wrapper."""
    source = _provenance_path(item["source_path"], root, f"{label}.source_path", report)
    if source is None:
        return False
    repo_rel = _repo_relative_from_source(item["source_path"], root)
    if basename == "model.cpp":
        if repo_rel != "Simulator/wksim_core/model.cpp":
            _fail(report, f"{label} external same-basename wrapper is not allowed: {item['source_path']}")
            return False
        if source.is_symlink() or _is_reparse(source):
            _fail(report, f"{label} repository wrapper is a symlink or reparse point")
            return False
    return _actual_file(
        source,
        label,
        report,
        sha256=item.get("sha256"),
        size_bytes=item.get("size_bytes"),
    )


def _load_for_check(path, label, report):
    try:
        return _load_json(path, label)
    except AuditDataError as exc:
        _fail(report, str(exc))
        return None


def _check_manifest_shape(manifest, report):
    try:
        _exact_keys(
            manifest,
            {"schema", "kind", "issue", "date", "claim", "closure_blocker", "acceptance_evidence"},
            "manifest",
        )
        if manifest["schema"] != MANIFEST_SCHEMA:
            raise AuditDataError("manifest schema differs")
        if manifest["kind"] != "closure_readiness_manifest" or manifest["issue"] != 26:
            raise AuditDataError("manifest identity differs")
        _string(manifest["date"], "manifest.date")
        _string(manifest["claim"], "manifest.claim")
        blocker = _object(manifest["closure_blocker"], "manifest.closure_blocker")
        _exact_keys(
            blocker,
            {"type", "issue", "relation", "state", "state_source", "realtime_check", "rule", "machine_decidable"},
            "manifest.closure_blocker",
        )
        if blocker["type"] != "formal_dependency" or blocker["issue"] != 9:
            raise AuditDataError("manifest closure blocker must name formal issue 9")
        if blocker["relation"] != "blocked-by" or blocker["state"] != "OPEN":
            raise AuditDataError("manifest closure blocker snapshot must remain OPEN")
        if blocker["state_source"] != "pinned_github_issue_snapshot":
            raise AuditDataError("manifest closure blocker must identify a pinned GitHub snapshot")
        if blocker["realtime_check"] != "not_performed_by_local_audit":
            raise AuditDataError("local audit must not claim a real-time GitHub check")
        _string(blocker["rule"], "manifest.closure_blocker.rule")
        if blocker["machine_decidable"] is not True:
            raise AuditDataError("manifest closure blocker machine_decidable must be true")

        evidence = _object(manifest["acceptance_evidence"], "manifest.acceptance_evidence")
        if set(evidence) != set(AC_KEYS):
            missing = [key for key in AC_KEYS if key not in evidence]
            extra = [key for key in evidence if key not in AC_KEYS]
            raise AuditDataError(f"acceptance evidence keys differ; missing={missing}, extra={extra}")
        for key in AC_KEYS:
            optional = {"requires", "rule"}
            if key == "matlab_free_lifecycle":
                optional.add("requirements")
            entry = _object(evidence[key], f"manifest.acceptance_evidence.{key}")
            _exact_keys(entry, {"ac", "pins"}, f"manifest.acceptance_evidence.{key}", optional)
            _string(entry["ac"], f"{key}.ac")
            if not isinstance(entry["pins"], list) or not entry["pins"]:
                raise AuditDataError(f"{key}.pins must be a non-empty list")
            seen = set()
            for index, pin in enumerate(entry["pins"]):
                pin = _object(pin, f"{key}.pins[{index}]")
                _exact_keys(pin, {"path", "sha256"}, f"{key}.pins[{index}]", {"requires"})
                rel = _repo_relative(pin["path"], f"{key}.pins[{index}].path")
                if rel in seen:
                    raise AuditDataError(f"{key}.pins contains duplicate path: {rel}")
                seen.add(rel)
                _sha(pin["sha256"], f"{key}.pins[{index}].sha256")
                if "requires" in pin:
                    _string(pin["requires"], f"{key}.pins[{index}].requires")
            if seen != EXPECTED_PIN_PATHS[key]:
                raise AuditDataError(f"{key}.pins must contain its exact required evidence paths")
            if key == "matlab_free_lifecycle":
                _check_lifecycle_requirements(entry.get("requirements"))
        return True
    except (AuditDataError, TypeError, KeyError) as exc:
        _fail(report, str(exc))
        return False


def _check_lifecycle_requirements(value):
    req = _object(value, "matlab_free_lifecycle.requirements")
    _exact_keys(
        req,
        {"status", "schema", "cycles", "library_sha256", "source_sha256", "raw_sha256", "run_bindings"},
        "matlab_free_lifecycle.requirements",
    )
    if req["status"] != "pass" or req["schema"] != "wksim.generated-e0-lifecycle.v1":
        raise AuditDataError("lifecycle requirements status/schema differs")
    _strict_int(req["cycles"], "lifecycle requirements.cycles", positive=True)
    _sha(req["library_sha256"], "lifecycle requirements.library_sha256")
    _check_sha_map(req["source_sha256"], "lifecycle requirements.source_sha256")
    _check_sha_map(
        req["raw_sha256"],
        "lifecycle requirements.raw_sha256",
        expected_keys=EXPECTED_LIFECYCLE_RAW_KEYS,
    )
    bindings = req["run_bindings"]
    if not isinstance(bindings, list) or len(bindings) != 2:
        raise AuditDataError("lifecycle requirements.run_bindings must contain two runs")
    names = set()
    total_cycles = 0
    for index, binding in enumerate(bindings):
        label = f"lifecycle requirements.run_bindings[{index}]"
        _exact_keys(
            binding,
            {"name", "pid", "pgid", "start_ticks", "argv", "returncode", "cycles", "library_sha256", "source_sha256", "raw_sha256"},
            label,
        )
        name = _string(binding["name"], f"{label}.name")
        if name in names:
            raise AuditDataError("lifecycle run binding names must be unique")
        names.add(name)
        for field in ("pid", "pgid", "start_ticks"):
            _strict_int(binding[field], f"{label}.{field}", positive=True)
        _check_argv(binding["argv"], f"{label}.argv")
        _strict_int(binding["returncode"], f"{label}.returncode")
        if binding["returncode"] != 0:
            raise AuditDataError(f"{label}.returncode must be 0")
        cycles = _strict_int(binding["cycles"], f"{label}.cycles", positive=True)
        total_cycles += cycles
        _sha(binding["library_sha256"], f"{label}.library_sha256")
        _check_sha_map(binding["source_sha256"], f"{label}.source_sha256")
        _check_sha_map(binding["raw_sha256"], f"{label}.raw_sha256")
    if total_cycles != req["cycles"]:
        raise AuditDataError("lifecycle run cycles do not sum to the pinned total")


def _check_sha_map(value, label, *, expected_keys=None):
    value = _object(value, label)
    if not value:
        raise AuditDataError(f"{label} must be non-empty")
    for key, item in value.items():
        _repo_relative(key, f"{label} key")
        _sha(item, f"{label}.{key}")
    if expected_keys is not None:
        expected_keys = set(expected_keys)
        actual_keys = set(value)
        if actual_keys != expected_keys:
            missing = sorted(expected_keys - actual_keys)
            extra = sorted(actual_keys - expected_keys)
            raise AuditDataError(
                f"{label} must contain the exact expected evidence set; "
                f"missing={missing}, extra={extra}"
            )


def _check_argv(value, label):
    if not isinstance(value, list) or not value:
        raise AuditDataError(f"{label} must be a non-empty string array")
    for index, item in enumerate(value):
        _string(item, f"{label}[{index}]")


def _probe_argument(command, label):
    indexes = [index for index, item in enumerate(command) if item == "--probe"]
    if len(indexes) != 1:
        raise AuditDataError(f"{label} must contain --probe followed by a library path")
    index = indexes[0]
    if index + 1 >= len(command):
        raise AuditDataError(f"{label} must contain --probe followed by a library path")
    value = command[index + 1]
    _absolute_source_path(value, f"{label} probe library")
    return value


def _check_pins(manifest, root, report):
    for ac_key, entry in manifest.get("acceptance_evidence", {}).items():
        for index, pin in enumerate(entry.get("pins", [])):
            path = _secure_file(root, pin.get("path"), report, f"{ac_key}.pins[{index}]")
            if path is None:
                continue
            try:
                if digest(path) != pin["sha256"]:
                    _fail(report, f"{ac_key}: pinned evidence drifted: {pin['path']}")
            except (OSError, KeyError, TypeError):
                _fail(report, f"{ac_key}: cannot hash pinned evidence: {pin.get('path')}")


def _check_codegen_report(root, report):
    path = root / "validation/codegen-e0/short-cycle-codegen-01/codegen-report.json"
    data = _load_for_check(path, "codegen report", report)
    if data is None:
        return None
    try:
        _exact_keys(data, {"status", "stages", "environment", "licenses", "solver", "original_target", "artifacts", "execution_override"}, "codegen report")
        if data["status"] != "generated":
            raise AuditDataError("codegen report status is not 'generated'")
        stages = data["stages"]
        if not isinstance(stages, list) or len(stages) != len(REQUIRED_STAGES):
            raise AuditDataError("codegen report must contain exactly nine stages")
        seen = set()
        for index, stage in enumerate(stages):
            label = f"codegen stages[{index}]"
            _exact_keys(stage, {"name", "command", "status", "identifier", "message", "report"}, label)
            name = _string(stage["name"], f"{label}.name")
            if name in seen:
                raise AuditDataError("codegen stages must have unique names")
            seen.add(name)
            _string(stage["command"], f"{label}.command")
            for field in ("identifier", "message", "report"):
                if not isinstance(stage[field], str):
                    raise AuditDataError(f"{label}.{field} must be a string")
            if stage["status"] != "ok":
                raise AuditDataError(f"codegen stage {name!r} did not pass")
        if seen != set(REQUIRED_STAGES):
            raise AuditDataError("codegen report stage set differs from the exact required nine")
        environment = _object(data["environment"], "codegen environment")
        _exact_keys(
            environment,
            {"version", "release", "matlabroot", "products", "startup_path", "isolated_path"},
            "codegen environment",
        )
        for field in ("version", "release", "matlabroot", "startup_path", "isolated_path"):
            _string(environment[field], f"codegen environment.{field}")
        products = environment["products"]
        if not isinstance(products, list) or not products:
            raise AuditDataError("codegen environment.products must be a non-empty array")
        product_names = set()
        for index, product in enumerate(products):
            label = f"codegen environment.products[{index}]"
            _exact_keys(product, {"Name", "Version", "Release", "Date"}, label)
            name = _string(product["Name"], f"{label}.Name")
            if name in product_names:
                raise AuditDataError("codegen environment product names must be unique")
            product_names.add(name)
            for field in ("Version", "Release", "Date"):
                _string(product[field], f"{label}.{field}")
        solver = _object(data["solver"], "codegen solver")
        _exact_keys(solver, {"Solver", "FixedStep", "SimulationMode"}, "codegen solver")
        for field in ("Solver", "FixedStep", "SimulationMode"):
            _string(solver[field], f"codegen solver.{field}")
        if solver != {"Solver": "ode4", "FixedStep": "0.001", "SimulationMode": "accelerator"}:
            raise AuditDataError("codegen solver contract differs")
        target = _object(data["original_target"], "codegen original_target")
        _exact_keys(target, {"SystemTargetFile", "TargetLang", "GenCodeOnly"}, "codegen original_target")
        for field in ("SystemTargetFile", "TargetLang", "GenCodeOnly"):
            _string(target[field], f"codegen original_target.{field}")
        if target != {"SystemTargetFile": "ert.tlc", "TargetLang": "C++", "GenCodeOnly": "on"}:
            raise AuditDataError("codegen original_target contract differs")
        artifacts = data["artifacts"]
        if not isinstance(artifacts, list) or len(artifacts) != len(REQUIRED_GENERATED):
            raise AuditDataError("codegen artifacts must contain exactly four entries")
        artifact_names = set()
        for index, artifact in enumerate(artifacts):
            label = f"codegen artifacts[{index}]"
            _exact_keys(artifact, {"name", "bytes", "relative_dir"}, label)
            name = _string(artifact["name"], f"{label}.name")
            if name in artifact_names:
                raise AuditDataError("codegen artifact names must be unique")
            artifact_names.add(name)
            _strict_int(artifact["bytes"], f"{label}.bytes", positive=True)
            _absolute_source_path(artifact["relative_dir"], f"{label}.relative_dir")
        if artifact_names != REQUIRED_GENERATED:
            raise AuditDataError("codegen artifact name set differs from required sources")
        override = _object(data["execution_override"], "codegen execution_override")
        _exact_keys(override, {"SimulationMode", "scope"}, "codegen execution_override")
        _string(override["SimulationMode"], "codegen execution_override.SimulationMode")
        _string(override["scope"], "codegen execution_override.scope")
        if override["SimulationMode"] != "normal":
            raise AuditDataError("codegen execution override must restore normal mode")
        licenses = _object(data["licenses"], "codegen licenses")
        _exact_keys(licenses, {"test", "checkout"}, "codegen licenses")
        for kind in ("test", "checkout"):
            values = _object(licenses[kind], f"codegen licenses.{kind}")
            if set(values) != set(REQUIRED_LICENSES):
                raise AuditDataError(f"codegen licenses.{kind} must contain exactly five required products")
            if any(type(value) is not int or value != 1 for value in values.values()):
                raise AuditDataError(f"codegen licenses.{kind} must record five successful checks")
        return data
    except (AuditDataError, TypeError, KeyError) as exc:
        _fail(report, str(exc))
        return None


def _check_generated_manifest(root, report):
    path = root / "validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json"
    data = _load_for_check(path, "generated-sources manifest", report)
    if data is None:
        return None
    try:
        _exact_keys(data, {"total_files", "cpp_count", "header_count", "sources"}, "generated-sources manifest")
        total = _strict_int(data["total_files"], "generated-sources total_files", positive=True)
        cpp = _strict_int(data["cpp_count"], "generated-sources cpp_count", nonnegative=True)
        headers = _strict_int(data["header_count"], "generated-sources header_count", nonnegative=True)
        sources = data["sources"]
        if not isinstance(sources, list) or len(sources) != total or total != len(REQUIRED_GENERATED):
            raise AuditDataError("generated-sources manifest file count is not the exact four-file set")
        seen = set()
        actual = {}
        for index, item in enumerate(sources):
            label = f"generated-sources sources[{index}]"
            _exact_keys(item, {"relative_path", "sha256", "size_bytes", "is_empty"}, label)
            relative = _artifact_relative(item["relative_path"], f"{label}.relative_path")
            basename = PurePosixPath(relative).name
            if basename in seen:
                raise AuditDataError(f"generated-sources has duplicate basename: {basename}")
            seen.add(basename)
            _sha(item["sha256"], f"{label}.sha256")
            _strict_int(item["size_bytes"], f"{label}.size_bytes", positive=True)
            if item["is_empty"] is not False:
                raise AuditDataError(f"{label}.is_empty must be false")
            actual[basename] = {"relative_path": relative, "sha256": item["sha256"], "size_bytes": item["size_bytes"]}
        if seen != REQUIRED_GENERATED:
            raise AuditDataError("generated-sources basename set differs from required sources")
        if cpp != 2 or headers != 2:
            raise AuditDataError("generated-sources C++/header counts must be 2 and 2")
        return actual
    except (AuditDataError, TypeError, KeyError) as exc:
        _fail(report, str(exc))
        return None


def _source_basename(value):
    return PurePosixPath(value.replace("\\", "/")).name


def _as_host_path(value, root):
    """Map a provenance path without letting a Windows path become POSIX-relative."""
    if WINDOWS_ABSOLUTE_RE.match(value):
        drive = value[0].lower()
        rest = value[3:].replace("\\", "/")
        if os.name != "nt":
            # WSL exposes every Windows drive at /mnt/<drive>.  This mapping
            # must apply to D: (and other non-current drives) as well as C:.
            return Path(f"/mnt/{drive}/{rest}")
        if str(Path(root)).replace("\\", "/")[:3].lower() == f"{drive}:/":
            return Path(value)
        return Path(value)
    if value.startswith("/") and os.name == "nt":
        # pathlib on Windows would turn /mnt/c/... into a path on the current
        # drive.  Such a WSL path is not a readable native-Windows path.
        return None
    return Path(value)


def _provenance_boundary(value, root):
    """Return the mapped drive root for a Windows path, when applicable."""
    if not WINDOWS_ABSOLUTE_RE.match(value):
        return None
    drive = value[0].lower()
    if os.name != "nt":
        return Path(f"/mnt/{drive}")
    return Path(f"{drive.upper()}:\\")


def _repo_relative_from_source(value, root):
    source = _as_host_path(value, root)
    if source is None:
        return None
    root = Path(root).resolve()
    try:
        return source.resolve(strict=False).relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None


def _check_build_manifest(root, generated, report):
    path = root / "validation/codegen-e0-build-short-cycle-01/build-manifest.json"
    data = _load_for_check(path, "build manifest", report)
    if data is None or generated is None:
        return None
    try:
        _exact_keys(data, {"build_id", "generation_run_id", "staged_sources", "excluded_files", "toolchain", "output_library", "ldd_audit", "test_probe"}, "build manifest")
        _string(data["build_id"], "build manifest.build_id")
        _string(data["generation_run_id"], "build manifest.generation_run_id")
        staged = _object(data["staged_sources"], "build manifest.staged_sources")
        excluded = data["excluded_files"]
        if (
            not isinstance(excluded, list)
            or any(type(item) is not str for item in excluded)
            or len(excluded) != len(set(excluded))
            or set(excluded) != {"ert_main.cpp"}
        ):
            raise AuditDataError("build manifest.excluded_files must be the exact set ['ert_main.cpp']")
        expected_staged = {"Exp1_MinModelTemp.cpp", "Exp1_MinModelTemp.h", "rtwtypes.h", "model.cpp", "rtw_continuous.h", "rtw_solver.h"}
        if set(staged) != expected_staged:
            raise AuditDataError("build manifest staged_sources set differs from the six pinned inputs")
        for basename, item in staged.items():
            label = f"build manifest.staged_sources.{basename}"
            _exact_keys(item, {"source_path", "wsl_staged_path", "sha256", "size_bytes"}, label)
            _absolute_source_path(item["source_path"], f"{label}.source_path")
            _string(item["wsl_staged_path"], f"{label}.wsl_staged_path")
            if not item["wsl_staged_path"].startswith("/") or "\\" in item["wsl_staged_path"]:
                raise AuditDataError(f"{label}.wsl_staged_path must be a canonical absolute POSIX path")
            if any(part in ("", ".", "..") for part in item["wsl_staged_path"].split("/")[1:]):
                raise AuditDataError(f"{label}.wsl_staged_path has an invalid segment")
            if _source_basename(item["source_path"]) != basename or _source_basename(item["wsl_staged_path"]) != basename:
                raise AuditDataError(f"{label} basename does not match its key")
            _sha(item["sha256"], f"{label}.sha256")
            _strict_int(item["size_bytes"], f"{label}.size_bytes", positive=True)
            _check_source_actual(item, basename, root, report, label)
        for basename, item in generated.items():
            if basename == "ert_main.cpp":
                if basename not in excluded or basename in staged:
                    raise AuditDataError("ert_main.cpp must be excluded from staged sources")
                continue
            if basename not in staged or staged[basename]["sha256"] != item["sha256"]:
                raise AuditDataError(f"generated source {basename} is not hash-bound by build manifest")
            if staged[basename]["size_bytes"] != item["size_bytes"]:
                raise AuditDataError(f"generated source {basename} size is not hash-bound")
        for basename, item in staged.items():
            repo_rel = _repo_relative_from_source(item["source_path"], root)
            if repo_rel is not None:
                if repo_rel not in ALLOWED_REPO_WRAPPERS:
                    if not (basename in REQUIRED_GENERATED and repo_rel.startswith("work/")):
                        raise AuditDataError(f"unapproved repository source in build manifest: {repo_rel}")
                if repo_rel in ALLOWED_REPO_WRAPPERS and not (root / repo_rel).is_file():
                    raise AuditDataError(f"approved repo wrapper is missing: {repo_rel}")
            elif basename in REQUIRED_GENERATED:
                raise AuditDataError(f"generated source provenance escaped private source boundary: {basename}")
        output = _object(data["output_library"], "build manifest.output_library")
        _exact_keys(output, {"filename", "sha256", "size_bytes"}, "build manifest.output_library")
        if output["filename"] != "libwksim_e0.so":
            raise AuditDataError("build output library filename differs")
        _sha(output["sha256"], "build manifest.output_library.sha256")
        _strict_int(output["size_bytes"], "build manifest.output_library.size_bytes", positive=True)
        toolchain = _object(data["toolchain"], "build manifest.toolchain")
        _exact_keys(toolchain, {"compiler", "flags", "compile_command"}, "build manifest.toolchain")
        _string(toolchain["compiler"], "build manifest.toolchain.compiler")
        if not isinstance(toolchain["flags"], list) or not toolchain["flags"]:
            raise AuditDataError("build manifest.toolchain.flags must be a non-empty string array")
        for index, flag in enumerate(toolchain["flags"]):
            _string(flag, f"build manifest.toolchain.flags[{index}]")
        _string(toolchain["compile_command"], "build manifest.toolchain.compile_command")
        ldd = _object(data["ldd_audit"], "build manifest.ldd_audit")
        _exact_keys(ldd, {"clean", "dependencies", "violations"}, "build manifest.ldd_audit")
        if type(ldd["clean"]) is not bool or ldd["clean"] is not True:
            raise AuditDataError("build ldd audit clean must be true")
        if not isinstance(ldd["dependencies"], list) or not ldd["dependencies"] or any(type(item) is not str for item in ldd["dependencies"]):
            raise AuditDataError("build ldd audit dependencies must be a non-empty string array")
        if not isinstance(ldd["violations"], list) or any(type(item) is not str for item in ldd["violations"]):
            raise AuditDataError("build ldd audit violations must be a string array")
        if ldd["violations"] != []:
            raise AuditDataError("build ldd audit is not clean")
        probe = _object(data["test_probe"], "build manifest.test_probe")
        _exact_keys(probe, {"success", "steps_evaluated", "step_size_seconds", "sim_time_seconds", "all_outputs_finite", "non_finite_step", "output_dimension", "copter_id", "vehicle_type", "sample_head", "sample_tail"}, "build manifest.test_probe")
        if type(probe["success"]) is not bool or probe["success"] is not True or type(probe["all_outputs_finite"]) is not bool or probe["all_outputs_finite"] is not True:
            raise AuditDataError("build probe did not pass")
        _strict_int(probe["steps_evaluated"], "build probe.steps_evaluated", positive=True)
        _strict_number(probe["step_size_seconds"], "build probe.step_size_seconds", positive=True)
        _strict_number(probe["sim_time_seconds"], "build probe.sim_time_seconds", positive=True)
        _strict_int(probe["output_dimension"], "build probe.output_dimension", positive=True)
        _strict_number(probe["copter_id"], "build probe.copter_id")
        _strict_number(probe["vehicle_type"], "build probe.vehicle_type")
        if probe["non_finite_step"] is not None:
            _strict_int(probe["non_finite_step"], "build probe.non_finite_step", nonnegative=True)
        for field in ("sample_head", "sample_tail"):
            values = probe[field]
            if not isinstance(values, list) or not values:
                raise AuditDataError(f"build probe.{field} must be a non-empty number array")
            for index, value in enumerate(values):
                _strict_number(value, f"build probe.{field}[{index}]")
        return data
    except (AuditDataError, TypeError, KeyError) as exc:
        _fail(report, str(exc))
        return None


def _check_lifecycle_evidence(root, manifest, build, report):
    path = root / "validation/codegen-e0-lifecycle-01/audit.json"
    audit = _load_for_check(path, "lifecycle audit", report)
    if audit is None:
        return None
    try:
        _exact_keys(audit, {"status", "schema", "runs", "ticks_per_cycle", "cycles", "compared_values", "clock_tolerance_s", "library_sha256", "cold_library", "source_sha256", "raw_sha256", "limitation"}, "lifecycle audit")
        if audit["status"] != "pass" or audit["schema"] != "wksim.generated-e0-lifecycle.v1":
            raise AuditDataError("lifecycle audit status/schema differs")
        _strict_int(audit["ticks_per_cycle"], "lifecycle ticks_per_cycle", positive=True)
        total_cycles = _strict_int(audit["cycles"], "lifecycle cycles", positive=True)
        _strict_int(audit["compared_values"], "lifecycle compared_values", positive=True)
        _strict_number(audit["clock_tolerance_s"], "lifecycle clock_tolerance_s", positive=True)
        _string(audit["limitation"], "lifecycle limitation")
        _sha(audit["library_sha256"], "lifecycle library_sha256")
        cold_path = _provenance_path(audit["cold_library"], root, "lifecycle cold_library", report)
        if cold_path is not None:
            _actual_file(cold_path, "lifecycle cold_library", report, sha256=audit["library_sha256"])
        _check_sha_map(audit["source_sha256"], "lifecycle source_sha256")
        _check_sha_map(
            audit["raw_sha256"],
            "lifecycle raw_sha256",
            expected_keys=EXPECTED_LIFECYCLE_RAW_KEYS,
        )
        runs = audit["runs"]
        if not isinstance(runs, list) or len(runs) != 2:
            raise AuditDataError("lifecycle audit must contain exactly two runs")
        names = set()
        for index, run in enumerate(runs):
            label = f"lifecycle runs[{index}]"
            _exact_keys(run, {"name", "command", "identity", "returncode"}, label)
            name = _string(run["name"], f"{label}.name")
            if name in names:
                raise AuditDataError("lifecycle run names must be unique")
            names.add(name)
            _check_argv(run["command"], f"{label}.command")
            probe_path = _probe_argument(run["command"], f"{label}.command")
            identity = _object(run["identity"], f"{label}.identity")
            _exact_keys(identity, {"pid", "pgid", "start_ticks", "argv"}, f"{label}.identity")
            for field in ("pid", "pgid", "start_ticks"):
                _strict_int(identity[field], f"{label}.identity.{field}", positive=True)
            _check_argv(identity["argv"], f"{label}.identity.argv")
            _strict_int(run["returncode"], f"{label}.returncode")
            if run["command"] != identity["argv"] or run["returncode"] != 0:
                raise AuditDataError(f"{label} command identity/returncode is not bound")
            run["_probe_path"] = probe_path
        if names != {"original", "cold"}:
            raise AuditDataError("lifecycle runs must be named exactly original and cold")
        if len({(r["identity"]["pid"], r["identity"]["start_ticks"], r["identity"]["pgid"], tuple(r["identity"]["argv"])) for r in runs}) != 2:
            raise AuditDataError("lifecycle runs must have two distinct process identities")
        requirements = manifest["acceptance_evidence"]["matlab_free_lifecycle"]["requirements"]
        req_runs = {item["name"]: item for item in requirements["run_bindings"]}
        if set(req_runs) != names:
            raise AuditDataError("lifecycle run names do not match pinned bindings")
        total_run_cycles = 0
        for run in runs:
            binding = req_runs[run["name"]]
            identity = run["identity"]
            for field in ("pid", "pgid", "start_ticks"):
                if binding[field] != identity[field]:
                    raise AuditDataError(f"lifecycle {run['name']} identity drifted from pinned binding")
            if binding["argv"] != identity["argv"] or binding["returncode"] != run["returncode"]:
                raise AuditDataError(f"lifecycle {run['name']} argv/returncode drifted")
            cycles = binding["cycles"]
            total_run_cycles += cycles
            raw_keys = {f"{run['name']}/cycle-{cycle}.jsonl" for cycle in range(cycles)}
            if set(binding["raw_sha256"]) != raw_keys:
                raise AuditDataError(f"lifecycle {run['name']} raw cycle binding is incomplete")
            for key in raw_keys:
                if binding["raw_sha256"][key] != audit["raw_sha256"].get(key):
                    raise AuditDataError(f"lifecycle {run['name']} raw hash is not cross-bound")
            if binding["source_sha256"] != audit["source_sha256"] or binding["library_sha256"] != audit["library_sha256"]:
                raise AuditDataError(f"lifecycle {run['name']} source/library hashes are not cross-bound")
        if total_run_cycles != total_cycles or requirements["cycles"] != total_cycles:
            raise AuditDataError("lifecycle cycle totals are not cross-bound")
        if requirements["library_sha256"] != audit["library_sha256"] or requirements["raw_sha256"] != audit["raw_sha256"] or requirements["source_sha256"] != audit["source_sha256"]:
            raise AuditDataError("lifecycle hashes differ from pinned requirement maps")
        raw_root = root / "validation/codegen-e0-lifecycle-01"
        for key, expected in audit["raw_sha256"].items():
            raw_path = _secure_file(raw_root, key, report, "lifecycle raw cycle")
            if raw_path is not None:
                _actual_file(raw_path, f"lifecycle raw cycle {key}", report, sha256=expected)
        if build is not None:
            if build["output_library"]["sha256"] != audit["library_sha256"]:
                raise AuditDataError("lifecycle library hash differs from build output pin")
            build_hashes = {name: item["sha256"] for name, item in build["staged_sources"].items()}
            if build_hashes != audit["source_sha256"]:
                raise AuditDataError("lifecycle source hashes differ from build staged-source hashes")
        original = next((run for run in runs if run["name"] == "original"), None)
        cold = next((run for run in runs if run["name"] == "cold"), None)
        if original is None or cold is None:
            raise AuditDataError("lifecycle runs must include original and cold runs")
        if cold["_probe_path"] != audit["cold_library"]:
            raise AuditDataError("lifecycle cold --probe path is not exactly bound to cold_library")
        cold_probe = _provenance_path(cold["_probe_path"], root, "lifecycle cold probe", report)
        if cold_probe is not None:
            _actual_file(
                cold_probe,
                "lifecycle cold probe",
                report,
                sha256=audit["library_sha256"],
            )
        output = _provenance_path(original["_probe_path"], root, "build output library", report)
        if output is not None:
            _actual_file(
                output,
                "build output library",
                report,
                sha256=audit["library_sha256"],
                size_bytes=(build["output_library"]["size_bytes"] if build is not None else None),
            )
        for run in runs:
            run.pop("_probe_path", None)
        return audit
    except (AuditDataError, TypeError, KeyError) as exc:
        _fail(report, str(exc))
        return None


def _check_generated_not_tracked(root, build, report):
    try:
        completed = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=60)
        if completed.returncode != 0:
            raise AuditDataError("git ls-files failed; generated-source exclusion undecidable")
        raw = completed.stdout
        if isinstance(raw, bytes):
            tracked = [item.decode("utf-8") for item in raw.split(b"\0") if item]
        else:
            tracked = [item for item in str(raw).split("\0") if item]
        tracked = {item.replace("\\", "/") for item in tracked}
        vendor_offenders = [name for name in tracked if re.search(r"(?:\.dll$|\.zip$|rflysim)", name, re.IGNORECASE)]
        if vendor_offenders:
            raise AuditDataError(f"vendor artifacts tracked in repository: {vendor_offenders[:5]}")
        generated_root_offenders = [
            name for name in tracked
            if name == PINNED_GENERATED_ROOT.rstrip("/") or name.startswith(PINNED_GENERATED_ROOT)
        ]
        if generated_root_offenders:
            raise AuditDataError(
                f"pinned generated root contains tracked entries: {generated_root_offenders[:5]}"
            )
        if build is None:
            return
        checked_prefixes = set()
        for basename, item in build["staged_sources"].items():
            rel = _repo_relative_from_source(item["source_path"], root)
            if rel is None or rel in ALLOWED_REPO_WRAPPERS:
                continue
            if rel in tracked:
                raise AuditDataError(f"private/generated source is tracked: {rel}")
            prefix = rel.rsplit("/", 1)[0] + "/"
            if prefix in checked_prefixes:
                continue
            checked_prefixes.add(prefix)
            if any(name.startswith(prefix) for name in tracked):
                raise AuditDataError(f"private generated subtree is tracked: {prefix}")
    except (AuditDataError, OSError, subprocess.SubprocessError) as exc:
        _fail(report, str(exc))


def audit(manifest_path=DEFAULT_MANIFEST, root=ROOT):
    report = {
        "status": "not_ready",
        "blocking_issue": 9,
        "claim": "Local audit verifies a pinned OPEN #9 snapshot; it cannot close #26 or query GitHub in real time.",
        "violations": [],
    }
    try:
        manifest_path = Path(manifest_path)
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return _fail(report, "closure-readiness manifest missing")
        manifest = _load_json(manifest_path, "closure-readiness manifest")
    except (AuditDataError, OSError, TypeError) as exc:
        return _fail(report, str(exc))
    if not _check_manifest_shape(manifest, report):
        return report
    _check_pins(manifest, root, report)
    _check_codegen_report(root, report)
    generated = _check_generated_manifest(root, report)
    build = _check_build_manifest(root, generated, report)
    _check_lifecycle_evidence(root, manifest, build, report)
    _check_generated_not_tracked(root, build, report)
    if not report["violations"]:
        report["status"] = "ready_blocked_by_formal_dependency"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit(args.manifest)
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(raw, encoding="utf-8", newline="\n")
    sys.stdout.buffer.write(raw.encode("utf-8"))
    return 0 if report["status"] == "ready_blocked_by_formal_dependency" else 2


if __name__ == "__main__":
    raise SystemExit(main())
