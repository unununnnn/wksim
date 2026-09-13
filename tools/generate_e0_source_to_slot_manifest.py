"""Generate the provenance-only e0 source-to-slot manifest.

This tool expands the frozen numerical contract's 26 dynamic observable groups
into exactly 56 scalar slots. It binds the historical R1 ``cpp:`` references
to the frozen Model 11.0 source member without extracting or rewriting it.
The current SLX 11.8 same-source mapping remains explicitly unresolved until
it is re-derived from that source. The output has no budget or approval fields
and is never an execution contract.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re


SCHEMA_VERSION = 2
KIND = "e0_source_to_slot_manifest"
EXPECTED_DYNAMIC_SLOTS = 56
EXCLUDED_SEMANTIC_STATUS = frozenset({
    "interface_metadata",
    "reserved_not_physical_coverage",
})
DEFAULT_CONTRACT = Path("Simulator/wksim_core/numerical-conformance-v1.json")
DEFAULT_OUTPUT = Path("validation/e0-source-to-slot-manifest-20260911.json")
ROOT = Path(__file__).resolve().parents[1]
FROZEN_CONTRACT_ID = "wksim-e0-fixed-reference-native-preservation-v1"
FROZEN_CONTRACT_SHA256 = "23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0"
MODEL_ARCHIVE_PATH = Path(
    "validation/model-reference-readiness-20260909/attempt-07/staged-model/MulticopterModel.zip"
)
MODEL_ARCHIVE_SHA256 = "d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed"
MODEL_MEMBER_PATH = "e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp"
MODEL_MEMBER_SHA256 = "a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019"
CURRENT_SLX_PATH = Path(
    "validation/model-reference-readiness-20260909/attempt-07/staged-model/Exp1_MinModelTemp.slx"
)
CURRENT_SLX_SHA256 = "c232e2e9f71a195ba77af628370a0b0f977104870673c91955e51c528a9a3392"
CPP_SOURCE_RE = re.compile(r"(?:^|;)\s*cpp:([^;]+)")
CPP_RANGE_RE = re.compile(r"^\s*(\d+)(?:-(\d+))?(?=\s|$)")


def sha256_file(path):
    """Return the lowercase SHA-256 digest of *path*."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path):
    """Load a JSON contract and reject a non-object root."""
    contract_path = Path(path)
    with contract_path.open("r", encoding="utf-8") as stream:
        contract = json.load(stream)
    if not isinstance(contract, dict):
        raise ValueError("contract root must be a JSON object")
    return contract


def dynamic_scalars(contract):
    """Expand dynamic contract observables into unique scalar descriptors."""
    observables = contract.get("observables")
    if not isinstance(observables, list):
        raise ValueError("contract observables must be a list")

    scalars = []
    seen = set()
    for observable in observables:
        if not isinstance(observable, dict):
            raise ValueError("contract observable must be an object")
        semantic_status = observable.get("semantic_status")
        if semantic_status is not None and not isinstance(semantic_status, str):
            raise ValueError("dynamic observable semantic_status must be a string or null")
        if semantic_status in EXCLUDED_SEMANTIC_STATUS:
            continue
        array = observable.get("array")
        indices = observable.get("indices")
        name = observable.get("id")
        if not isinstance(array, str) or not array:
            raise ValueError("dynamic observable array is missing")
        if not isinstance(name, str) or not name:
            raise ValueError("dynamic observable id is missing")
        if not isinstance(indices, list) or not indices:
            raise ValueError("dynamic observable indices are missing")
        for index in indices:
            if type(index) is not int or index < 0:
                raise ValueError(f"invalid index for {name}: {index!r}")
            key = (array, index)
            if key in seen:
                raise ValueError(f"duplicate dynamic scalar {array}[{index}]")
            seen.add(key)
            scalars.append((array, index, observable))

    if len(scalars) != EXPECTED_DYNAMIC_SLOTS:
        raise ValueError(
            f"dynamic scalar count is {len(scalars)}, "
            f"expected {EXPECTED_DYNAMIC_SLOTS}"
        )
    return scalars


def parse_cpp_line_ranges(source):
    """Parse the exact 1-based C++ line ranges from a contract source label."""
    if not isinstance(source, str) or not source:
        raise ValueError("source label must be a non-empty string")
    match = CPP_SOURCE_RE.search(source)
    if match is None:
        raise ValueError(f"source label has no cpp reference: {source!r}")
    ranges = []
    for token in match.group(1).split(","):
        range_match = CPP_RANGE_RE.match(token)
        if range_match is None:
            raise ValueError(f"invalid cpp line range {token!r}")
        start = int(range_match.group(1))
        end = int(range_match.group(2) or start)
        if start > end:
            raise ValueError(f"cpp line range is descending: {token!r}")
        ranges.append([start, end])
    if not ranges:
        raise ValueError("source label has an empty cpp reference")
    return ranges


def _source_mapping(source):
    """Build the two-layer historical/current source mapping."""
    if not isinstance(source, str) or not source:
        raise ValueError("historical source label must be a non-empty string")
    historical_ranges = parse_cpp_line_ranges(source)
    return {
        "raw": source,
        "historical_r1_cpp": {
            "status": "bound",
            "line_ranges": historical_ranges,
        },
        "current_slx_11_8": {
            "status": "unresolved",
            "line_ranges": None,
        },
    }


def _unresolved_fields(slot):
    """List every evidence field that remains null in a generated slot."""
    fields = [
        "version",
        "hash",
        "unit",
        "frame",
        "datum",
        "sample_phase",
    ]
    return [field for field in fields if _field_value(slot, field) is None]


def _field_value(slot, field):
    if field.startswith("source_mapping."):
        return slot["source_mapping"][field.split(".", 1)[1]]
    return slot[field]


def build_manifest(contract_path):
    """Build a deterministic two-layer source-to-slot manifest."""
    path = Path(contract_path).resolve()
    canonical = (ROOT / DEFAULT_CONTRACT).resolve()
    if path != canonical:
        raise ValueError(f"contract must be the frozen canonical file {DEFAULT_CONTRACT.as_posix()}")
    if sha256_file(path) != FROZEN_CONTRACT_SHA256:
        raise ValueError("frozen contract SHA-256 differs")
    contract = load_contract(path)
    if contract.get("contract_id") != FROZEN_CONTRACT_ID:
        raise ValueError("frozen contract ID differs")
    scalars = dynamic_scalars(contract)
    try:
        contract_display_path = path.relative_to(ROOT).as_posix()
    except ValueError:
        contract_display_path = path.as_posix()
    slots = []
    for array, index, observable in scalars:
        slot = {
            "slot": f"{array}[{index}]",
            "array": array,
            "index": index,
            "observable": observable["id"],
            "source_mapping": _source_mapping(observable.get("source")),
            "version": None,
            "hash": None,
            "unit": observable.get("native_unit"),
            "frame": None,
            "datum": None,
            "sample_phase": "major_root_output",
            "status": "unresolved",
        }
        slot["unresolved_fields"] = _unresolved_fields(slot)
        slots.append(slot)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": "unresolved",
        "contract": {
            "path": contract_display_path,
            "contract_id": contract.get("contract_id"),
            "sha256": FROZEN_CONTRACT_SHA256,
        },
        "model_source": {
            "historical_r1_cpp": {
                "status": "bound",
                "model_version": "11.0",
                "archive": {
                    "path": MODEL_ARCHIVE_PATH.as_posix(),
                    "sha256": MODEL_ARCHIVE_SHA256,
                    "member": MODEL_MEMBER_PATH,
                    "member_sha256": MODEL_MEMBER_SHA256,
                },
            },
            "current_slx_11_8": {
                "status": "unresolved",
                "model_version": "11.8",
                "path": CURRENT_SLX_PATH.as_posix(),
                "sha256": CURRENT_SLX_SHA256,
                "line_mapping": None,
                "unresolved_reason": (
                    "same-source line mapping must be re-derived from the current SLX 11.8 "
                    "generated source; historical Model 11.0 cpp lines are not reused"
                ),
            },
        },
        "slot_count": len(slots),
        "slots": slots,
    }


def write_manifest(contract_path, output_path):
    """Generate and write one manifest, creating only its parent directory."""
    manifest = build_manifest(contract_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    manifest = write_manifest(args.contract, args.output)
    print(json.dumps({"output": str(args.output), "slot_count": manifest["slot_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
