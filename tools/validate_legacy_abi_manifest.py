"""Fail-closed structural validator for legacy-DLL ABI manifest proposals.

This gate operationalizes the five #58 prerequisites for entering the #27/#73
implementation ticket into a machine-checkable object. It NEVER loads a DLL,
never approves an ABI, and cannot produce an accepted manifest: a structurally
valid proposal still reports ``gate=proposal_structure_only``,
``status=blocked_unapproved`` and ``acceptance=false``.

PROPOSAL GATE NOTICE:
CLI exit 0 means ONLY that the proposal structure is syntactically complete and
self-consistent enough to be reviewed by Astra/the user.
CLI EXIT 0 MUST NEVER BE INTERPRETED AS ABI PASSAGE OR ABI ACCEPTANCE.

Semantic gates beyond the JSON schema:

- lexical rejection of duplicate JSON keys and NaN/Infinity constants;
- every export carries calling convention, return type + non-empty error codes,
  ordered typed parameters with unique names and explicit array layout/length
  (array parameters must have type 'pointer');
- exports collectively cover the required lifecycle phases (init, input, step,
  output, reset, terminate);
- lifecycle transitions use strict 'from->to' syntax and form a connected graph;
- all paths (sample and evidence) are normalized relative repository paths
  without backslashes, NUL bytes, traversal '..' or absolute roots;
- evidence line intervals are strictly ascending and non-inverted;
- the two known SDK-consumer conflicts (``DllInputColls`` double[20] vs
  float[20]; ``DllInitPosAngStat`` name check vs ``DllInitPosAngState``
  access) MUST be declared exactly as unresolved conflicts with pinned evidence;
  any adjudication other than ``unresolved`` is out of scope and rejected;
- the sample SHA/source/license/local-use/readable-wrapper chain must be
  fully populated; missing links or placeholders reject the proposal.

Usage:
    python3 -B tools/validate_legacy_abi_manifest.py MANIFEST [--output REPORT]
"""

import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs/plan/27-legacy-abi-manifest.schema.json"

KNOWN_CONFLICTS = {
    "dllinputcolls-width": {
        "description": ("DllInputColls declared double[20] then overwritten as "
                        "float[20] in the SDK consumer"),
        "path": "RflySimSDK/ctrl/DllSimCtrlAPI.py",
        "lines": "1235-1239,1292-1296",
    },
    "dllinitposang-name": {
        "description": ("consumer checks DllInitPosAngStat but accesses "
                        "DllInitPosAngState"),
        "path": "RflySimSDK/ctrl/DllSimCtrlAPI.py",
        "lines": "1248-1255",
    },
}
SDK_WRAPPER_SHA256 = "0a2a30e91fe55590aec198f1e852a6d45d6aa34c029557de62880d0b81cf5420"
LIFECYCLE_STATES = ("unloaded", "loaded", "initialized", "stepping",
                    "resetting", "terminated")
PLACEHOLDER_VALUES = frozenset({"", "unknown", "todo", "n/a", "na", "tbd",
                                "unset", "unavailable"})
FORBIDDEN_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})
SAMPLE_PHASES = ("init", "pre_step", "post_step", "reset", "terminate",
                 "not_step_bound")
STEP_SEMANTICS = ("input_committed_before_step", "output_sampled_after_step",
                  "not_step_bound")


def _fail(report, message):
    report["violations"].append(message)
    return report


def _reject_duplicate_keys(pairs):
    seen = set()
    res = {}
    for k, v in pairs:
        if k in seen:
            raise ValueError(f"duplicate JSON key: {k!r}")
        seen.add(k)
        res[k] = v
    return res


def _reject_json_constant(c):
    raise ValueError(f"disallowed JSON constant: {c!r}")


def _normalized_casefold(value):
    """Return a comparison form without modifying the manifest value."""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _validate_text_values(value, where, report):
    """Reject blank, placeholder, and non-printable Unicode strings.

    The comparison form is used only for validation.  The manifest value is
    never normalized or otherwise rewritten, so a full-width/case-variant
    placeholder cannot bypass this gate and a valid Unicode value is retained
    exactly as supplied.
    """
    if isinstance(value, str):
        normalized = _normalized_casefold(value)
        if not value.strip():
            _fail(report, f"{where}: required string must not be blank or whitespace-only")
        elif normalized in PLACEHOLDER_VALUES:
            _fail(report, f"{where}: required string must not be blank or placeholder")
        forbidden = sorted({unicodedata.category(character)
                            for character in value
                            if unicodedata.category(character) in FORBIDDEN_UNICODE_CATEGORIES})
        if forbidden:
            _fail(report, f"{where}: string contains forbidden Unicode categories {forbidden}")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_text_values(child, f"{where}.{key}", report)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_text_values(child, f"{where}[{index}]", report)


def _validate_clean_relative_path(path_str, where, report):
    if not isinstance(path_str, str) or not path_str.strip():
        _fail(report, f"{where}: path must be a non-empty string")
        return
    if "\0" in path_str:
        _fail(report, f"{where}: path must not contain NUL byte")
        return
    if "\\" in path_str:
        _fail(report, f"{where}: path must use forward slashes, no backslashes: {path_str!r}")
        return
    if path_str != path_str.strip() or any(character.isspace() for character in path_str):
        _fail(report, f"{where}: path must not contain whitespace: {path_str!r}")
        return
    if path_str.startswith("/") or re.match(r"^[a-zA-Z]:", path_str):
        _fail(report, f"{where}: path must be relative, not absolute: {path_str!r}")
        return
    parts = path_str.split("/")
    if any(part == "" for part in parts):
        _fail(report, f"{where}: path must not contain empty segments: {path_str!r}")
        return
    if ".." in parts:
        _fail(report, f"{where}: path must not contain traversal segment '..': {path_str!r}")
        return
    if any(p == "." for p in parts):
        _fail(report, f"{where}: path must be normalized without '.' segments: {path_str!r}")
        return
    for index, part in enumerate(parts):
        if unicodedata.normalize("NFKC", part) != part:
            _fail(report, f"{where}: path segment {index} must use its NFKC-normalized spelling")
        if _normalized_casefold(part) in PLACEHOLDER_VALUES:
            _fail(report, f"{where}: path segment {index} must not be a placeholder")


def _validate_evidence_lines(lines_str, where, report):
    if not isinstance(lines_str, str) or not lines_str.strip():
        _fail(report, f"{where}: evidence.lines must be a non-empty string")
        return
    prev_end = -1
    for seg in lines_str.split(","):
        seg = seg.strip()
        if "-" in seg:
            parts = seg.split("-")
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                _fail(report, f"{where}: malformed line range segment: {seg!r}")
                continue
            s, e = int(parts[0]), int(parts[1])
            if s < 1 or e < 1:
                _fail(report, f"{where}: evidence line numbers must be >= 1: {seg!r}")
                continue
            if s > e:
                _fail(report, f"{where}: line range {s}-{e} must be ascending")
                continue
            if s <= prev_end:
                _fail(report, f"{where}: line segments must be strictly ascending: {seg} follows {prev_end}")
                continue
            prev_end = e
        else:
            if not seg.isdigit():
                _fail(report, f"{where}: malformed line segment: {seg!r}")
                continue
            s = int(seg)
            if s < 1:
                _fail(report, f"{where}: evidence line numbers must be >= 1: {seg!r}")
                continue
            if s <= prev_end:
                _fail(report, f"{where}: line segments must be strictly ascending: {s} follows {prev_end}")
                continue
            prev_end = s


def _validate_export(export, index, report):
    where = f"exports[{index}]({export.get('name', '?')})"

    ret = export.get("return", {})
    error_codes = ret.get("error_codes", [])
    if not error_codes:
        _fail(report, f"{where}: return.error_codes must be non-empty")

    units = export.get("units", "")
    if (not isinstance(units, str) or not units.strip() or
            _normalized_casefold(units) in PLACEHOLDER_VALUES):
        _fail(report, f"{where}: units must not be empty or placeholder")

    phase = export.get("sample_phase")
    if phase not in SAMPLE_PHASES:
        _fail(report, f"{where}: sample_phase {phase!r} must be in {SAMPLE_PHASES}")

    semantics = export.get("step_semantics")
    if semantics not in STEP_SEMANTICS:
        _fail(report, f"{where}: step_semantics {semantics!r} must be in {STEP_SEMANTICS}")

    parameters = export.get("parameters", [])
    orders = [p.get("order") for p in parameters]
    if sorted(orders) != list(range(len(orders))):
        _fail(report, f"{where}: parameter order must be exactly 0..{len(orders) - 1}")

    param_names = [p.get("name") for p in parameters]
    if len(set(param_names)) != len(param_names):
        _fail(report, f"{where}: duplicate parameter names: {param_names}")

    for position, parameter in enumerate(parameters):
        if parameter.get("order") != position:
            _fail(report, f"{where}: parameter at position {position} declares "
                          f"order {parameter.get('order')}")
        layout = parameter.get("array_layout", {})
        if layout.get("is_array"):
            if parameter.get("type") != "pointer":
                _fail(report, f"{where}.{parameter.get('name')}: array parameter must have type 'pointer', got {parameter.get('type')!r}")
            if layout.get("element_type") in (None, "none"):
                _fail(report, f"{where}.{parameter.get('name')}: array without element type")
            if not layout.get("length") or layout.get("length") <= 0:
                _fail(report, f"{where}.{parameter.get('name')}: array without positive length")
        elif layout.get("element_type") not in (None, "none") or layout.get("length") not in (None, 0):
            _fail(report, f"{where}.{parameter.get('name')}: non-array parameter carries array layout")

    evidence = export.get("evidence", {})
    _validate_clean_relative_path(evidence.get("path", ""), f"{where}.evidence.path", report)
    _validate_evidence_lines(evidence.get("lines", ""), f"{where}.evidence.lines", report)


def _validate_lifecycle(manifest, report):
    lifecycle = manifest.get("lifecycle", {})
    states = set(lifecycle.get("states", []))
    transitions = lifecycle.get("transitions", [])
    if states != set(LIFECYCLE_STATES):
        _fail(report, "lifecycle.states must contain exactly the six required states: "
              f"{list(LIFECYCLE_STATES)}")
    seen_trans = set()
    adjacency = {state: set() for state in states}
    for t in transitions:
        if not isinstance(t, str) or "->" not in t:
            _fail(report, f"lifecycle transition must use 'from->to' format: {t!r}")
            continue
        parts = t.split("->")
        if len(parts) != 2:
            _fail(report, f"lifecycle transition must have exactly one '->': {t!r}")
            continue
        src, dst = parts[0].strip(), parts[1].strip()
        if src not in states:
            _fail(report, f"lifecycle transition source {src!r} not in declared states")
        if dst not in states:
            _fail(report, f"lifecycle transition destination {dst!r} not in declared states")
        if t in seen_trans:
            _fail(report, f"duplicate lifecycle transition: {t!r}")
        seen_trans.add(t)
        if src in states and dst in states:
            adjacency.setdefault(src, set()).add(dst)

    if "unloaded" not in adjacency or not adjacency["unloaded"]:
        _fail(report, "lifecycle transitions must start from 'unloaded'")
    reachable = set()
    pending = ["unloaded"] if "unloaded" in states else []
    while pending:
        state = pending.pop()
        if state in reachable:
            continue
        reachable.add(state)
        pending.extend(adjacency.get(state, ()) - reachable)
    missing = states - reachable
    if missing:
        _fail(report, f"lifecycle states not reachable from 'unloaded': {sorted(missing)}")


def _validate_exports_lifecycle_coverage(manifest, report):
    exports = manifest.get("exports", [])
    phases = {e.get("sample_phase") for e in exports if isinstance(e, dict)}
    semantics = {e.get("step_semantics") for e in exports if isinstance(e, dict)}

    for req_phase in ("init", "reset", "terminate"):
        if req_phase not in phases:
            _fail(report, f"exports missing required lifecycle phase: {req_phase!r}")

    has_step = any(p in ("pre_step", "post_step") for p in phases)
    if not has_step:
        _fail(report, "exports missing step phase ('pre_step' or 'post_step')")

    has_input = "input_committed_before_step" in semantics or any(
        any(p.get("direction") in ("in", "inout") for p in e.get("parameters", []))
        for e in exports if isinstance(e, dict)
    )
    if not has_input:
        _fail(report, "exports missing input capability (direction 'in'/'inout' or 'input_committed_before_step')")

    has_output = "output_sampled_after_step" in semantics or any(
        any(p.get("direction") in ("out", "inout") for p in e.get("parameters", []))
        for e in exports if isinstance(e, dict)
    )
    if not has_output:
        _fail(report, "exports missing output capability (direction 'out'/'inout' or 'output_sampled_after_step')")


def _validate_conflicts(manifest, report):
    raw_conflicts = manifest.get("unresolved_conflicts", [])
    conflict_ids = [c.get("id") for c in raw_conflicts if isinstance(c, dict)]
    if len(set(conflict_ids)) != len(conflict_ids):
        _fail(report, f"duplicate conflict ids in unresolved_conflicts: {conflict_ids}")

    if set(conflict_ids) != set(KNOWN_CONFLICTS.keys()):
        _fail(report, f"unresolved_conflicts must exactly match known conflicts {sorted(KNOWN_CONFLICTS.keys())}, got {sorted(conflict_ids)}")

    declared = {c.get("id"): c for c in raw_conflicts if isinstance(c, dict)}
    for conflict_id, known in KNOWN_CONFLICTS.items():
        entry = declared.get(conflict_id)
        if entry is None:
            _fail(report, f"known conflict {conflict_id} not declared as unresolved")
            continue
        if entry.get("adjudication") != "unresolved":
            _fail(report, f"conflict {conflict_id}: adjudication other than "
                          "'unresolved' is out of scope for this gate")
        if entry.get("description") != known["description"]:
            _fail(report, f"conflict {conflict_id}: description must match the "
                          "pinned SDK-consumer description")
        evidence = entry.get("evidence", {})
        if evidence.get("path") != known["path"]:
            _fail(report, f"conflict {conflict_id}: evidence path must be the "
                          f"pinned SDK consumer path {known['path']!r}")
        if evidence.get("sha256") != SDK_WRAPPER_SHA256:
            _fail(report, f"conflict {conflict_id}: evidence must reference the "
                          "pinned SDK consumer SHA256")
        if evidence.get("lines") != known["lines"]:
            _fail(report, f"conflict {conflict_id}: evidence lines must be "
                          f"{known['lines']}")
        _validate_clean_relative_path(evidence.get("path", ""), f"conflict {conflict_id}.evidence.path", report)
        _validate_evidence_lines(evidence.get("lines", ""), f"conflict {conflict_id}.evidence.lines", report)


def _validate_sample(manifest, report):
    sample = manifest.get("sample", {})
    for key in ("source", "license", "permitted_local_use",
                "readable_header_or_wrapper"):
        value = sample.get(key, "")
        if (not isinstance(value, str) or not value.strip() or
                _normalized_casefold(value) in PLACEHOLDER_VALUES):
            _fail(report, f"sample.{key} is missing or a placeholder")
    _validate_clean_relative_path(sample.get("readable_header_or_wrapper", ""), "sample.readable_header_or_wrapper", report)


def _validate_isolation(manifest, report):
    isolation = manifest.get("isolation", {})
    for key in ("dll_crash", "step_error", "short_output", "repeated_reset",
                "thread_udp_residue"):
        value = isolation.get(key, "")
        normalized = _normalized_casefold(value) if isinstance(value, str) else ""
        if not isinstance(value, str) or not value.strip() or normalized in PLACEHOLDER_VALUES:
            _fail(report, f"isolation.{key} is missing or a placeholder")


def validate(manifest_path):
    """Validate one manifest proposal; always returns a blocked report."""
    report = {
        "gate": "proposal_structure_only",
        "status": "blocked_unapproved",
        "acceptance": False,
        "manifest": str(manifest_path),
        "violations": [],
    }
    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file():
        return _fail(report, "manifest is missing or not a regular file")
    try:
        manifest = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, ValueError) as error:
        return _fail(report, f"manifest is not readable JSON: {error}")

    from jsonschema import Draft202012Validator
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    schema_errors = sorted(Draft202012Validator(schema).iter_errors(manifest),
                           key=lambda e: list(e.absolute_path))
    for error in schema_errors:
        path_str = ".".join(str(p) for p in error.absolute_path)
        msg = f"{path_str}: {error.message}" if path_str else error.message
        _fail(report, "schema: " + msg.replace("\n", " "))
    if schema_errors:
        return report

    _validate_text_values(manifest, "manifest", report)
    if manifest.get("status") != "blocked_unapproved" or manifest.get("acceptance") is not False:
        _fail(report, "a proposal can never self-declare acceptance")
    names = [e.get("name") for e in manifest.get("exports", [])]
    if len(set(names)) != len(names):
        _fail(report, "duplicate export names")
    for index, export in enumerate(manifest.get("exports", [])):
        _validate_export(export, index, report)
    _validate_lifecycle(manifest, report)
    _validate_exports_lifecycle_coverage(manifest, report)
    _validate_conflicts(manifest, report)
    _validate_sample(manifest, report)
    _validate_isolation(manifest, report)
    return report


def serialize(report):
    return json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = validate(args.manifest)
    raw = serialize(report)
    if args.output:
        args.output.write_text(raw, encoding="utf-8", newline="\n")
    sys.stdout.buffer.write(raw.encode("utf-8"))
    return 0 if not report["violations"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
