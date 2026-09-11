"""Derive per-slot verbatim RHS and typed references for the e0 dynamic slots.

Second provenance layer on top of the pinned v1 current-source map: for each
of the 56 dynamic contract slots this records the exact right-hand-side text
of its root-outport write in the pinned generated C++ ``step`` and classifies
every referenced symbol (block output / state / parameter / timing / local /
call).  A one-hop local definition is bound ONLY when the local has exactly
one assignment in ``step`` at top-level brace depth that precedes the use;
reused temporaries, control-flow-scoped or indexed definitions, calls and
compound expressions are reported as explicit unresolved reasons.  No
dominance across control flow is ever guessed.

A ``local_bound`` hop stays one level deep by design: it additionally records
``definition_rhs`` and the typed ``definition_references`` of that single
bound definition, but never recurses into them.  When the bound definition's
own RHS references another local, calls a function, or is itself compound,
the hop sets ``unresolved_dependency`` with a ``dependency_reason`` so the
binding is never mistaken for a complete dependency closure.  The timing
model is referenced only as ``(&Exp1_MinModelTemp_M)->Timing.t[<index>]``; any
other ``Exp1_MinModelTemp_M`` use is rejected.  A constant right-hand side has
no symbol references (``references`` is empty) and resolves ``terminal``.

Usage:
    python3 -B tools/derive_e0_current_rhs_references.py [--check]
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import derive_e0_current_source_mapping as v1  # noqa: E402

SCHEMA_VERSION = 1
KIND = "e0_current_rhs_references"
STATUS = "bound"
DERIVATION_RULE = "e0-current-rhs-references-v1"
V1_ARTIFACT = Path("validation/e0-current-source-mapping-20260912.json")
V1_ARTIFACT_SHA256 = "28684e66cd6e49c90907dacdabf219608a3e3ba808e07e3bd9068233268489f8"
DEFAULT_OUTPUT = Path("validation/e0-current-rhs-references-20260912.json")
EXPECTED_SLOTS = 56
NON_CLAIMS = (
    "provenance only; no numeric, rate, latency, safety or flight acceptance claim",
    "unresolved slots are not decomposed; their reasons name the parse boundary",
    "no dominance or reaching-definition analysis across control flow",
    "call targets are external semantics; only the call site is recorded",
    "a constant RHS carries references=[] and resolves terminal",
    "local_bound binds only the single prior top-level assignment; its "
    "definition_references resolve that one definition one level and are not "
    "recursively decomposed (an interior local/call/compound sets "
    "unresolved_dependency with a reason)",
)

PATH_RE = re.compile(
    r"&?Exp1_MinModelTemp_([BXP])((?:\.\w+)+(?:\[\d+\])?)")
TIMING_RE = re.compile(r"\(&?Exp1_MinModelTemp_M\)->(Timing\.t\[\d+\])")
MODEL_RE = re.compile(r"\bExp1_MinModelTemp_M\b")
LOCAL_RE = re.compile(r"\b(rtb_\w+)((?:\[\d+\])?)")
CALL_RE = re.compile(r"\b((?:std::)?[a-zA-Z_]\w*)\s*\(")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d*)?(?:[eE][+-]?\d+)?[UuFf]?\b")
PATH_KIND = {"B": "block_output", "X": "state", "P": "parameter"}
MAX_RHS_LINES = v1.MAX_STATEMENT_LINES

RESOLUTION_STATUSES = ("terminal", "local_bound", "unresolved")
UNRESOLVED_REASONS = ("reused_temporary", "control_flow_scoped", "array_local",
                      "call_expression", "compound_expression")
# Reasons a bound local's own definition is not a complete one-level closure.
DEPENDENCY_REASONS = ("local_dependency", "call_expression", "compound_expression")


def _strip_comments(lines):
    """Remove comments and blank string/char literals; keep line count/positions.

    Line comments drop the remainder of the line; block-comment and quoted
    literal contents are blanked (with backslash escapes honored) so a ``{`` /
    ``}`` or ``;`` inside them can never corrupt brace-depth or statement
    detection.  Generated numeric ``step`` code contains no string literals;
    any that appear are neutralized, never parsed as code.
    """
    clean = []
    in_block = False
    for line in lines:
        out = bytearray()
        quote = None  # None, or the opening b'"' / b"'" while inside a literal
        i = 0
        n = len(line)
        while i < n:
            ch = line[i:i + 1]
            nxt = line[i + 1:i + 2]
            if in_block:
                if ch == b"*" and nxt == b"/":
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            if quote is not None:
                if ch == b"\\":
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch == b"/" and nxt == b"/":
                break
            if ch == b"/" and nxt == b"*":
                in_block = True
                i += 2
                continue
            if ch == b'"' or ch == b"'":
                quote = ch
                i += 1
                continue
            out += ch
            i += 1
        clean.append(bytes(out))
    return clean


def _step_span(clean):
    """Locate the step definition body; fail closed if absent or unterminated."""
    start = None
    for index, line in enumerate(clean, 1):
        function = v1.FUNCTION_RE.match(line)
        if function is not None and function.group(1) == b"step":
            start = index
            break
    if start is None:
        raise ValueError("MulticopterModelClass::step definition not found")
    depth = 0
    opened = False
    for index in range(start, len(clean) + 1):
        depth += clean[index - 1].count(b"{")
        if depth > 0:
            opened = True
        depth -= clean[index - 1].count(b"}")
        if opened and depth == 0:
            return start, index
    raise ValueError("step body never closes")


def _assignment_rhs(statement, label):
    """Return the right-hand side of an assignment statement ending in ';'."""
    if "=" not in statement:
        raise ValueError(f"{label}: statement has no assignment")
    rhs = statement.split("=", 1)[1].strip()
    if not rhs.endswith(";"):
        raise ValueError(f"{label}: statement does not end with ';'")
    rhs = rhs[:-1].strip()
    if not rhs:
        raise ValueError(f"{label}: empty RHS")
    return rhs


def _extract_rhs(clean, slot):
    """Slice the verbatim RHS text of one mapped slot write; fail closed.

    Operates on the comment/literal-stripped lines (line positions unchanged)
    so a trailing comment or a quoted literal can never masquerade as part of
    the expression.
    """
    ranges = slot["line_ranges"]
    if len(ranges) != 1:
        raise ValueError(f"slot {slot['slot']}: expected exactly one line range")
    start, end = ranges[0]
    if end - start + 1 > MAX_RHS_LINES:
        raise ValueError(f"slot {slot['slot']}: statement exceeds {MAX_RHS_LINES} lines")
    if start < 1 or end > len(clean) or end < start:
        raise ValueError(f"slot {slot['slot']}: line range outside the generated source")
    raw = b"\n".join(clean[start - 1:end])
    match = v1.ASSIGN_RE.match(raw)
    if match is None:
        raise ValueError(f"slot {slot['slot']}: v1 line range does not start an assignment")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(f"slot {slot['slot']}: statement is not ASCII") from error
    lines_text = [line.rstrip() for line in text.split("\n")]
    statement = "\n".join(lines_text).strip()
    rhs = _assignment_rhs(statement, f"slot {slot['slot']}")
    return {"text": rhs, "lines": end - start + 1}


def _references(rhs):
    """Classify every referenced symbol; reject unknown reference forms."""
    references = []
    for match in TIMING_RE.finditer(rhs):
        references.append({"kind": "timing", "path": "Exp1_MinModelTemp_M->" + match.group(1)})
    for match in PATH_RE.finditer(rhs):
        references.append({"kind": PATH_KIND[match.group(1)],
                           "path": "Exp1_MinModelTemp_" + match.group(1) + match.group(2)})
    for match in LOCAL_RE.finditer(rhs):
        references.append({"kind": "local", "name": match.group(1),
                           "indexed": bool(match.group(2))})
    for match in CALL_RE.finditer(rhs):
        name = match.group(1)
        if name.startswith("Exp1_MinModelTemp_") or name == "rtb_":
            continue
        references.append({"kind": "call", "name": name})
    without_timing = TIMING_RE.sub("", rhs)
    if MODEL_RE.search(without_timing):
        raise ValueError("model (Exp1_MinModelTemp_M) reference must use the "
                         "(&Exp1_MinModelTemp_M)->Timing.t[<index>] form")
    residual = without_timing
    residual = CALL_RE.sub("(", residual)
    residual = PATH_RE.sub("", residual)
    residual = LOCAL_RE.sub("", residual)
    residual = NUMBER_RE.sub("", residual)
    residual = re.sub(r"[\s+\-*/(),;.<>=!&|%~^?:\[\]]", "", residual)
    if residual:
        raise ValueError(f"unknown reference form in RHS: {residual!r}")
    return references


def validate_artifact_semantics(artifact, mapping):
    """Require every slot identity to match the pinned v1 mapping exactly.

    JSON Schema can constrain the shape of one slot, but it cannot express the
    contract's 56 distinct ``(array, index, observable, outport)`` bindings.
    Keep that semantic check in the derivation tool so a copied slot whose
    observable or array/index was edited cannot pass structural validation.
    """
    expected_slots = mapping.get("slots") if isinstance(mapping, dict) else None
    if not isinstance(expected_slots, list):
        raise ValueError("v1 mapping has no slot list")
    if len(expected_slots) != EXPECTED_SLOTS:
        raise ValueError(
            f"v1 mapping has {len(expected_slots)} slots, expected {EXPECTED_SLOTS}")
    actual_slots = artifact.get("slots") if isinstance(artifact, dict) else None
    if not isinstance(actual_slots, list) or len(actual_slots) != EXPECTED_SLOTS:
        raise ValueError(f"artifact has {len(actual_slots) if isinstance(actual_slots, list) else 'invalid'} "
                         f"slots, expected {EXPECTED_SLOTS}")

    def identity(slot):
        if not isinstance(slot, dict):
            raise ValueError("slot must be an object")
        required = ("slot", "array", "index", "observable", "outport")
        if any(key not in slot for key in required):
            raise ValueError("slot is missing semantic identity fields")
        if slot["slot"] != f"{slot['array']}[{slot['index']}]":
            raise ValueError(f"slot identity is inconsistent: {slot.get('slot')!r}")
        return tuple(slot[key] for key in required)

    expected = [identity(slot) for slot in expected_slots]
    actual = [identity(slot) for slot in actual_slots]
    if len(set((slot[0], slot[1], slot[2]) for slot in expected)) != EXPECTED_SLOTS:
        raise ValueError("v1 mapping contains duplicate slot or array/index identity")
    if len(set((slot[0], slot[1], slot[2]) for slot in actual)) != EXPECTED_SLOTS:
        raise ValueError("artifact contains duplicate slot or array/index identity")
    if set(actual) != set(expected):
        raise ValueError("artifact slot identities differ from the v1 mapping")


def validate_semantics(artifact, mapping=None):
    """Validate a v2 artifact against the pinned v1 slot identity mapping."""
    if mapping is None:
        mapping = json.loads((ROOT / V1_ARTIFACT).read_bytes().decode("utf-8"))
    validate_artifact_semantics(artifact, mapping)


def _find_local_definitions(clean, step_start, step_end, name, use_line):
    """All assignments to a local inside step: (line, depth, indexed, text)."""
    pattern = re.compile(rb"^\s*" + re.escape(name.encode("ascii"))
                         + rb"(\s*\[[^\]]*\])?\s*=[^=]")
    definitions = []
    depth = 0
    for index in range(step_start, step_end + 1):
        line = clean[index - 1]
        match = pattern.match(line)
        if match is not None:
            end = v1._statement_end(clean, index, b";")
            text = b"\n".join(clean[index - 1:end]).decode("ascii").strip()
            definitions.append({"line": index, "end": end, "depth": depth,
                                "indexed": bool(match.group(1)), "text": text})
        depth += line.count(b"{")
        depth -= line.count(b"}")
    return definitions


def _resolve(rhs, references, clean, step_start, step_end, slot, use_line):
    """Bind at most one hop; never guess across control flow."""
    calls = [r for r in references if r["kind"] == "call"]
    locals_ = [r for r in references if r["kind"] == "local"]
    if calls:
        return {"status": "unresolved", "reason": "call_expression"}
    if not locals_:
        return {"status": "terminal", "reason": None}
    if len(locals_) != 1 or len(references) != 1:
        return {"status": "unresolved", "reason": "compound_expression"}
    local = locals_[0]
    if local["indexed"]:
        return {"status": "unresolved", "reason": "array_local"}
    if rhs.strip() != local["name"]:
        return {"status": "unresolved", "reason": "compound_expression"}
    definitions = _find_local_definitions(clean, step_start, step_end,
                                          local["name"], use_line)
    if not definitions:
        raise ValueError(f"slot {slot['slot']}: local {local['name']} has no definition in step")
    if any(d["indexed"] for d in definitions):
        return {"status": "unresolved", "reason": "array_local"}
    if len(definitions) != 1:
        return {"status": "unresolved", "reason": "reused_temporary"}
    definition = definitions[0]
    if definition["depth"] != 1:
        return {"status": "unresolved", "reason": "control_flow_scoped"}
    if definition["line"] >= use_line:
        raise ValueError(f"slot {slot['slot']}: local {local['name']} defined after its use")
    # One hop only: type the bound definition's own RHS, but never recurse.
    # An interior local/call/compound means the dependency is NOT a clean
    # one-level closure; surface that explicitly instead of implying it.
    definition_rhs = _assignment_rhs(definition["text"],
                                     f"slot {slot['slot']} definition of {local['name']}")
    definition_references = _references(definition_rhs)
    internal_calls = [r for r in definition_references if r["kind"] == "call"]
    internal_locals = [r for r in definition_references if r["kind"] == "local"]
    if internal_calls:
        unresolved_dependency, dependency_reason = True, "call_expression"
    elif internal_locals:
        unresolved_dependency, dependency_reason = True, "local_dependency"
    elif not definition_references:
        unresolved_dependency, dependency_reason = False, None
    elif len(definition_references) == 1 and (
        definition_rhs.strip() == definition_references[0].get("path")
        or (definition_references[0]["kind"] == "timing"
            and TIMING_RE.fullmatch(definition_rhs.strip()) is not None)
    ):
        unresolved_dependency, dependency_reason = False, None
    else:
        unresolved_dependency, dependency_reason = True, "compound_expression"
    return {"status": "local_bound", "reason": None,
            "hop": {"local": local["name"],
                    "definition_line_range": [definition["line"], definition["end"]],
                    "definition_text": definition["text"],
                    "definition_rhs": definition_rhs,
                    "definition_references": definition_references,
                    "unresolved_dependency": unresolved_dependency,
                    "dependency_reason": dependency_reason}}


def build_artifact(source_bytes, mapping):
    """Build the v2 artifact from pinned source bytes and a parsed v1 mapping."""
    if mapping.get("kind") != "e0_current_source_mapping" \
            or mapping.get("slot_count") != EXPECTED_SLOTS \
            or len(mapping.get("slots", [])) != EXPECTED_SLOTS:
        raise ValueError("v1 mapping artifact shape differs")
    clean = _strip_comments(source_bytes.split(b"\n"))
    step_start, step_end = _step_span(clean)
    slots = []
    for slot in mapping["slots"]:
        rhs = _extract_rhs(clean, slot)
        references = _references(rhs["text"])
        resolution = _resolve(rhs["text"], references, clean, step_start, step_end,
                              slot, slot["line_ranges"][0][0])
        slots.append({"slot": slot["slot"], "array": slot["array"], "index": slot["index"],
                      "observable": slot["observable"], "outport": slot["outport"],
                      "line_ranges": slot["line_ranges"], "rhs": rhs,
                      "references": references, "resolution": resolution})
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": STATUS,
        "provenance_only": True,
        "non_claims": NON_CLAIMS,
        "v1_artifact": {"path": V1_ARTIFACT.as_posix(), "sha256": V1_ARTIFACT_SHA256},
        "generated_source": mapping["generated_source"],
        "derivation": {
            "rule": DERIVATION_RULE,
            "enclosing_function": v1.ENCLOSING_FUNCTION,
            "step_line_range": [step_start, step_end],
            "resolution_statuses": RESOLUTION_STATUSES,
            "unresolved_reasons": UNRESOLVED_REASONS,
            "dependency_reasons": DEPENDENCY_REASONS,
        },
        "slot_count": len(slots),
        "slots": slots,
    }
    validate_artifact_semantics(artifact, mapping)
    return artifact


def derive(artifact_root=ROOT):
    """Derive the v2 artifact from the byte-verified v1 map and pinned source."""
    v1.check(ROOT / V1_ARTIFACT, v1.DEFAULT_CONTRACT, v1.EVIDENCE_PATH, artifact_root)
    source = v1.load_private_source(artifact_root)
    v1_bytes = (ROOT / V1_ARTIFACT).read_bytes()
    if hashlib.sha256(v1_bytes).hexdigest() != V1_ARTIFACT_SHA256:
        raise ValueError("v1 mapping artifact SHA-256 differs from the pin")
    mapping = json.loads(v1_bytes.decode("utf-8"))
    return build_artifact(source, mapping)


def serialize(artifact):
    """Serialize one artifact deterministically (LF newlines)."""
    return (json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False)
            + "\n").encode("utf-8")


def _is_link_or_reparse(path):
    """Return whether *path* is a symlink or a Windows reparse point."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)


def _prepare_output_parent(destination):
    """Create a parent chain without following links or escaping it."""
    if any(part == ".." for part in destination.parts):
        raise ValueError(f"output path must not contain parent escape: {destination}")
    absolute = destination if destination.is_absolute() else Path.cwd() / destination
    parent = absolute.parent
    anchor = Path(absolute.anchor)
    current = anchor
    for part in parent.relative_to(anchor).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_link_or_reparse(current):
                raise ValueError(f"output parent must not be a symlink or reparse point: {current}")
            if not current.is_dir():
                raise ValueError(f"output parent is not a directory: {current}")
        else:
            current.mkdir()
            if _is_link_or_reparse(current) or not current.is_dir():
                raise ValueError(f"output parent failed safe creation: {current}")
    # Canonical containment must still point at the walked parent.  This also
    # catches a concurrent reparse/symlink substitution before mkstemp.
    try:
        canonical_parent = parent.resolve(strict=True)
        walked_parent = current.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"output parent cannot be canonicalized: {parent}") from exc
    if canonical_parent != walked_parent:
        raise ValueError(f"output parent escaped canonical containment: {parent}")
    if _is_link_or_reparse(parent):
        raise ValueError(f"output parent must not be a symlink or reparse point: {parent}")
    return destination


def write_artifact(artifact, output_path):
    """Atomically create the artifact; never overwrite."""
    destination = Path(output_path)
    if _is_link_or_reparse(destination):
        raise ValueError(f"output must not be a symlink: {output_path}")
    if destination.exists():
        raise ValueError(f"output exists; create-only refusal: {output_path}")
    _prepare_output_parent(destination)
    if _is_link_or_reparse(destination.parent):
        raise ValueError(f"output parent must not be a symlink or reparse point: {destination.parent}")
    handle, temporary = tempfile.mkstemp(prefix=destination.name + ".",
                                         dir=destination.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(serialize(artifact))
            stream.flush()
            os.fsync(stream.fileno())
        if _is_link_or_reparse(destination):
            raise ValueError(f"output must not be a symlink: {output_path}")
        os.link(temporary, destination)  # atomic create-only on both platforms
    except BaseException:
        raise
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
    return destination


def check(artifact_path, artifact_root=ROOT):
    """Re-derive and require byte-identical content to the checked-in artifact."""
    path = Path(artifact_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"checked-in artifact is missing or not a regular file: {artifact_path}")
    expected = path.read_bytes()
    try:
        expected_artifact = json.loads(expected.decode("utf-8"))
        mapping = json.loads((ROOT / V1_ARTIFACT).read_bytes().decode("utf-8"))
        validate_artifact_semantics(expected_artifact, mapping)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"checked-in artifact is not valid JSON: {artifact_path}") from exc
    actual = serialize(derive(artifact_root))
    if actual != expected:
        raise ValueError(f"checked-in artifact differs from re-derivation: {artifact_path}")
    return {"artifact": path.as_posix(), "status": "match", "slot_count": EXPECTED_SLOTS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Re-derive and byte-compare against --output instead of writing")
    args = parser.parse_args(argv)
    try:
        if args.check:
            result = check(args.output, args.artifact_root)
        else:
            artifact = derive(args.artifact_root)
            destination = write_artifact(artifact, args.output)
            result = {"output": destination.as_posix(), "status": "derived",
                      "slot_count": artifact["slot_count"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "fail-closed", "error": str(exc)}, ensure_ascii=False))
        return 2
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8") + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
