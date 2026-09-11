"""Derive the e0 current-source (SLX 11.8) per-slot outport write map offline.

This binds the 56 dynamic contract slots to the exact root-outport write
statements inside the #70-generated ``Exp1_MinModelTemp.cpp`` (Model 11.8,
``MulticopterModelClass::step``).  The generated C++ stays in a private,
Git-ignored location; only its identity (path/SHA-256/size, cross-checked
against the committed codegen evidence manifest) and byte-based line ranges
enter the tracked artifact.  Line numbers are computed on raw bytes split at
``\\n`` so the GBK comment bytes and CRLF endings cannot shift them.

This is source-location provenance only.  It does not claim numerical or
physical equivalence, does not resolve #59 G6 budgets, and does not modify
the frozen v2 source-to-slot manifest, whose current layer stays
``unresolved``.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_e0_source_to_slot_manifest import (  # noqa: E402
    DEFAULT_CONTRACT,
    EXPECTED_DYNAMIC_SLOTS,
    FROZEN_CONTRACT_ID,
    FROZEN_CONTRACT_SHA256,
    dynamic_scalars,
    load_contract,
    sha256_file,
)

SCHEMA_VERSION = 1
KIND = "e0_current_source_mapping"
STATUS = "bound"
DERIVATION_RULE = "e0-current-outport-write-v1"
LINE_NUMBERING = "raw-bytes-split-lf"
ENCLOSING_FUNCTION = "MulticopterModelClass::step"
NON_CLAIMS = (
    "Source-location provenance only; not a numerical or physical equivalence "
    "claim, not a #59 G6 budget, not an execution contract. v1 maps each slot "
    "to its root-outport write statement only; upstream computation sites in "
    "the current source are out of scope. The generated C++ bytes remain "
    "private and are never committed."
)

GENERATED_NAME = "Exp1_MinModelTemp.cpp"
GENERATED_SHA256 = "2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274"
GENERATED_SIZE = 327598
GENERATION_RUN = "short-cycle-codegen-01"
MODEL_VERSION = "11.8"
GENERATED_RELATIVE_PATH = Path(
    "work/codegen-e0/short-cycle-codegen-01/codegen/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp"
)
EVIDENCE_PATH = Path("validation/codegen-e0/short-cycle-codegen-01/generated-sources-manifest.json")
EVIDENCE_SHA256 = "85c40213cec0f349d36664c5621bb53c46ad96f9756cdd4eaa2bb97a7b2acc67"
DEFAULT_OUTPUT = Path("validation/e0-current-source-mapping-20260912.json")

# Contract array -> generated root-outport identifier (the misspelling
# 'VehileInfo60d' is the actual generated port name and must not be fixed).
OUTPORTS = (("Vehicle60", "VehileInfo60d", 60),
            ("Sensor30", "HILSensor30d", 30),
            ("GPS30", "HILGPS30d", 30))
OUTPORT_BY_ARRAY = {array: name for array, name, _ in OUTPORTS}
OUTPORT_SIZES = {name: size for _, name, size in OUTPORTS}

FUNCTION_RE = re.compile(rb"^[\w:\*&\s]*\bMulticopterModelClass::(\w+)\s*\(")
ASSIGN_RE = re.compile(
    rb"^\s*Exp1_MinModelTemp_Y\.(VehileInfo60d|HILSensor30d|HILGPS30d)\[(\d+)\]\s*=")
MEMCPY_RE = re.compile(
    rb"^\s*std::memcpy\(&Exp1_MinModelTemp_Y\.(VehileInfo60d|HILSensor30d|HILGPS30d)\[(\d+)\],")
MEMCPY_COUNT_RE = re.compile(rb"(\d+)U?\s*\*\s*sizeof\(real_T\)")
ANY_OUTPORT_WRITE_RE = re.compile(rb"Exp1_MinModelTemp_Y\.(\w+)\[")
BOUNDARY_RE = re.compile(
    rb"^\s*(?:\}|\{|\b(?:if|for|while|switch|case|return|break|continue|void|double|real_T|int|static|const|struct)\b|"
    rb"[\w:\*&\s]*\bMulticopterModelClass::|"
    rb"(?:std::memcpy\(&)?Exp1_MinModelTemp_Y\.|"
    rb"(?:[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)(?:\[[^\]]*\])?\s*=)"
)
MAX_STATEMENT_LINES = 10


def _statement_end(lines, start, terminator):
    """Return the 1-based line on which the statement starting at *start* ends."""
    if terminator in lines[start - 1]:
        return start
    line = start + 1
    while line <= len(lines):
        if line - start > MAX_STATEMENT_LINES:
            raise ValueError(f"statement starting at line {start} never terminates with {terminator!r}")
        curr = lines[line - 1]
        clean = re.sub(rb"//.*", b"", curr).strip()
        if BOUNDARY_RE.match(curr) or clean.startswith(b"}") or clean.startswith(b"{") or FUNCTION_RE.match(curr):
            raise ValueError(f"statement starting at line {start} never terminates with {terminator!r}")
        if terminator in curr:
            return line
        line += 1
    raise ValueError(f"statement starting at line {start} never terminates with {terminator!r}")


def parse_outport_writes(source_bytes):
    """Map every root-outport slot to its single write statement in ``step``.

    Returns ``{(outport, index): (start_line, end_line, statement_kind)}``.
    Raises ValueError unless all 120 outport slots are covered exactly once,
    in range, and every outport write is enclosed by
    ``MulticopterModelClass::step``.
    """
    if not isinstance(source_bytes, bytes) or not source_bytes:
        raise ValueError("generated source must be non-empty bytes")
    lines = source_bytes.split(b"\n")
    coverage = {}
    enclosing = None
    brace_depth = 0
    had_open = False
    step_seen = False
    in_block_comment = False
    for number, line in enumerate(lines, 1):
        clean = line
        if in_block_comment:
            if b"*/" in clean:
                clean = clean.split(b"*/", 1)[1]
                in_block_comment = False
            else:
                clean = b""
        while b"/*" in clean:
            before, after = clean.split(b"/*", 1)
            if b"*/" in after:
                clean = before + after.split(b"*/", 1)[1]
            else:
                clean = before
                in_block_comment = True
                break
        clean = re.sub(rb"//.*", b"", clean)

        function = FUNCTION_RE.match(line)
        if function is not None:
            enclosing = function.group(1).decode("ascii")
            brace_depth = 0
            had_open = False
            step_seen = step_seen or enclosing == "step"

        opens = clean.count(b"{")
        closes = clean.count(b"}")
        if enclosing is not None:
            brace_depth += opens
            if opens > 0:
                had_open = True

        unknown = ANY_OUTPORT_WRITE_RE.search(line)
        if unknown is not None and unknown.group(1).decode("ascii") not in OUTPORT_SIZES:
            raise ValueError(
                f"unexpected root outport {unknown.group(1)!r} at line {number}")
        match = ASSIGN_RE.match(line)
        kind = "assignment"
        if match is None:
            match = MEMCPY_RE.match(line)
            kind = "memcpy"
        if match is not None:
            if enclosing != "step" or not had_open or brace_depth <= 0:
                raise ValueError(
                    f"outport write at line {number} is not enclosed by {ENCLOSING_FUNCTION}")
            outport = match.group(1).decode("ascii")
            index = int(match.group(2))
            if kind == "assignment":
                end = _statement_end(lines, number, b";")
                indices = (index,)
            else:
                end = _statement_end(lines, number, b");")
                block = b"\n".join(lines[number - 1:end])
                count = MEMCPY_COUNT_RE.search(block)
                if count is None:
                    raise ValueError(f"memcpy write at line {number} has no parseable element count")
                indices = range(index, index + int(count.group(1)))
            for slot_index in indices:
                if slot_index >= OUTPORT_SIZES[outport]:
                    raise ValueError(
                        f"outport write index {slot_index} out of range for {outport} "
                        f"at line {number}")
                key = (outport, slot_index)
                if key in coverage:
                    raise ValueError(f"duplicate write to {outport}[{slot_index}] at line {number}")
                coverage[key] = (number, end, kind)

        if enclosing is not None and had_open:
            brace_depth -= closes
            if brace_depth <= 0:
                enclosing = None
                had_open = False
                brace_depth = 0
    if not step_seen:
        raise ValueError(f"{ENCLOSING_FUNCTION} definition not found")
    missing = [f"{name}[{index}]" for name, size in OUTPORT_SIZES.items()
               for index in range(size) if (name, index) not in coverage]
    if missing:
        raise ValueError(f"outport slots without a write: {missing}")
    covered = len(coverage)
    if covered != sum(OUTPORT_SIZES.values()):
        raise ValueError(f"covered {covered} outport slots, expected {sum(OUTPORT_SIZES.values())}")
    return coverage


def build_artifact(source_bytes, contract):
    """Build the deterministic current-source mapping artifact."""
    scalars = dynamic_scalars(contract)
    coverage = parse_outport_writes(source_bytes)
    slots = []
    for array, index, observable in scalars:
        outport = OUTPORT_BY_ARRAY.get(array)
        if outport is None:
            raise ValueError(f"no outport binding for contract array {array!r}")
        key = (outport, index)
        if key not in coverage:
            raise ValueError(f"dynamic slot {array}[{index}] has no current-source write")
        start, end, kind = coverage[key]
        slots.append({
            "slot": f"{array}[{index}]",
            "array": array,
            "index": index,
            "observable": observable["id"],
            "outport": outport,
            "statement": kind,
            "line_ranges": [[start, end]],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": STATUS,
        "provenance_only": True,
        "non_claims": NON_CLAIMS,
        "contract": {
            "path": DEFAULT_CONTRACT.as_posix(),
            "contract_id": FROZEN_CONTRACT_ID,
            "sha256": FROZEN_CONTRACT_SHA256,
        },
        "generated_source": {
            "name": GENERATED_NAME,
            "model_version": MODEL_VERSION,
            "generation_run": GENERATION_RUN,
            "artifact_relative_path": GENERATED_RELATIVE_PATH.as_posix(),
            "sha256": GENERATED_SHA256,
            "size_bytes": GENERATED_SIZE,
            "evidence": {
                "path": EVIDENCE_PATH.as_posix(),
                "sha256": EVIDENCE_SHA256,
            },
        },
        "derivation": {
            "rule": DERIVATION_RULE,
            "line_numbering": LINE_NUMBERING,
            "enclosing_function": ENCLOSING_FUNCTION,
            "outports": [
                {"array": array, "outport": name, "size": size}
                for array, name, size in OUTPORTS
            ],
            "covered_output_slots": sum(OUTPORT_SIZES.values()),
        },
        "slot_count": len(slots),
        "slots": slots,
    }


def load_checked_contract(contract_path):
    """Load the frozen contract, pinned to the canonical path, ID and SHA-256."""
    path = Path(contract_path).resolve()
    canonical = (ROOT / DEFAULT_CONTRACT).resolve()
    if path != canonical:
        raise ValueError(f"contract must be the frozen canonical file {DEFAULT_CONTRACT.as_posix()}")
    if sha256_file(path) != FROZEN_CONTRACT_SHA256:
        raise ValueError("frozen contract SHA-256 differs")
    contract = load_contract(path)
    if contract.get("contract_id") != FROZEN_CONTRACT_ID:
        raise ValueError("frozen contract ID differs")
    return contract


def load_evidence(evidence_path):
    """Cross-check the pinned generated-source identity against #70 evidence."""
    path = Path(evidence_path)
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read codegen evidence: {exc}") from exc
    if sha256_file(path) != EVIDENCE_SHA256:
        raise ValueError("codegen evidence manifest SHA-256 differs")
    sources = evidence.get("sources") if isinstance(evidence, dict) else None
    if not isinstance(sources, list):
        raise ValueError("codegen evidence sources must be a list")
    matches = [entry for entry in sources
               if isinstance(entry, dict)
               and Path(str(entry.get("relative_path", "")).replace("\\", "/")).name == GENERATED_NAME]
    if len(matches) != 1:
        raise ValueError(f"codegen evidence must name {GENERATED_NAME} exactly once")
    entry = matches[0]
    if entry.get("sha256") != GENERATED_SHA256 or entry.get("size_bytes") != GENERATED_SIZE:
        raise ValueError("codegen evidence generated-source SHA-256/size differs from the pins")
    if entry.get("is_empty") is not False:
        raise ValueError("codegen evidence generated source must be non-empty")
    return evidence


def resolve_private_source(artifact_root, relative_path=GENERATED_RELATIVE_PATH):
    """Resolve the private generated C++ below *artifact_root*; fail closed."""
    root = Path(artifact_root).resolve()
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"generated source path escapes the artifact root: {relative_path}")
    candidate = root.joinpath(relative)
    resolved = candidate.resolve()
    if os.path.normcase(str(resolved)) != os.path.normcase(str(candidate)):
        raise ValueError(f"generated source path crosses a symlink: {relative_path}")
    if candidate.is_symlink():
        raise ValueError(f"generated source must not be a symlink: {relative_path}")
    if not resolved.is_file():
        raise ValueError(
            f"private generated source not found at {relative.as_posix()} below {artifact_root}; "
            "pass --artifact-root pointing at a mirror that reproduces the declared relative path")
    return resolved


def load_private_source(artifact_root):
    """Read the private generated C++ and verify its pinned identity."""
    path = resolve_private_source(artifact_root)
    data = path.read_bytes()
    if len(data) != GENERATED_SIZE:
        raise ValueError("generated source size differs from the #70 pin")
    if hashlib.sha256(data).hexdigest() != GENERATED_SHA256:
        raise ValueError("generated source SHA-256 differs from the #70 pin")
    return data


def serialize(artifact):
    """Serialize one artifact deterministically (LF newlines)."""
    return (json.dumps(artifact, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def derive(contract_path, evidence_path, artifact_root):
    """Derive the artifact from the pinned contract, evidence and private source."""
    contract = load_checked_contract(contract_path)
    load_evidence(evidence_path)
    source = load_private_source(artifact_root)
    return build_artifact(source, contract)


def write_artifact(artifact, output_path):
    """Write the artifact, refusing to overwrite through a symlink."""
    destination = Path(output_path)
    if destination.is_symlink():
        raise ValueError(f"output must not be a symlink: {output_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(serialize(artifact).decode("utf-8"))
    return destination


def check(artifact_path, contract_path, evidence_path, artifact_root):
    """Re-derive and require byte-identical content to the checked-in artifact."""
    path = Path(artifact_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"checked-in artifact is missing or not a regular file: {artifact_path}")
    expected = path.read_bytes()
    actual = serialize(derive(contract_path, evidence_path, artifact_root))
    if actual != expected:
        raise ValueError(f"checked-in artifact differs from re-derivation: {artifact_path}")
    return {"artifact": Path(artifact_path).as_posix(), "status": "match",
            "slot_count": EXPECTED_DYNAMIC_SLOTS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--artifact-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Re-derive and byte-compare against --output instead of writing")
    args = parser.parse_args(argv)
    try:
        if args.check:
            result = check(args.output, args.contract, args.evidence, args.artifact_root)
        else:
            artifact = derive(args.contract, args.evidence, args.artifact_root)
            destination = write_artifact(artifact, args.output)
            result = {"output": Path(destination).as_posix(), "status": "derived",
                      "slot_count": artifact["slot_count"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "fail-closed", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
