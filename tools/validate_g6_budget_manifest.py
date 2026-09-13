"""Fail-closed validator for the G6 budget skeleton manifest (#10/#59).

A valid manifest is proof of structure, never of budget approval.  The
validator re-reads the pinned inputs itself and requires:

- input pins (path + SHA-256) match the actual files;
- exactly 56 rows, unique slots, same order and identity as the pinned RHS
  provenance artifact;
- every row carries all contract fields; budgets null on ``blocked`` and
  ``pending_owner_decision`` rows;
- v1 has no pinned identity-rule source, so ``identity_check`` is forbidden;
  admitted rows remain blocked or pending owner decision;
- any admitted non-blocked row must carry a complete auditable chain
  (derivation, domain, approval, metric, unit, frame, datum, sample_phase);
- no status can ever be ``approved`` (not in the schema enum).

Usage:
    python3 -B tools/validate_g6_budget_manifest.py MANIFEST
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from generate_g6_budget_manifest import (
    CONFORMANCE,
    CONFORMANCE_SHA256,
    RHS_ARTIFACT,
    RHS_SHA256,
    SLOT_MANIFEST,
    SLOT_MANIFEST_SHA256,
    TIME_OBSERVABLES,
    EXPECTED_CONFORMANCE_OBSERVABLES,
    _verify_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/plan/10-g6-budget-manifest.schema.json"
# Filled from the final schema bytes.  Keeping this independent pin means a
# widened schema cannot silently enlarge the accepted manifest language.
SCHEMA_SHA256 = "c480b42d877bae5c435a39318ca61c77acb547593f3b3c9ce78cc3db0d4c2e5e"
EXPECTED_SLOTS = 56
BUDGET_FIELDS = ("abs_budget", "rel_budget", "rms_budget")
AUDIT_CHAIN_FIELDS = ("unit", "frame", "datum", "sample_phase", "metric",
                      "derivation", "domain", "approval", "contract_sha256")
CLAIM_FIELDS = ("metric", "abs_budget", "rel_budget", "rms_budget",
                "derivation", "domain", "approval", "contract_sha256")
PINNED_INPUTS = {
    "rhs_references": {"path": RHS_ARTIFACT, "sha256": RHS_SHA256},
    "source_to_slot_manifest": {"path": SLOT_MANIFEST,
                                "sha256": SLOT_MANIFEST_SHA256},
    "numerical_conformance": {"path": CONFORMANCE,
                              "sha256": CONFORMANCE_SHA256},
}


def _fail(report, message):
    report["status"] = "fail-closed"
    report["violations"].append(message)
    return report


def _strict_json_constant(value):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _load_json_bytes(raw, source):
    try:
        text = raw.decode("utf-8")
    except Exception as error:
        raise ValueError(f"{source} is not UTF-8: {error}") from error
    return json.loads(text,
                      object_pairs_hook=_strict_json_object,
                      parse_constant=_strict_json_constant)


def _load_json(path):
    target = Path(path)
    return _load_json_bytes(target.read_bytes(), target)


def validate(manifest_path):
    report = {"status": "valid_structure_blocked_budgets", "acceptance": False,
              "manifest": str(manifest_path), "violations": []}
    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file():
        return _fail(report, "manifest missing or not a regular file")
    try:
        manifest = _load_json(path)
    except Exception as error:
        return _fail(report, f"manifest is not readable JSON: {error}")

    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except Exception as error:
        return _fail(report, f"jsonschema package unavailable: {error}")

    try:
        schema_path = Path(SCHEMA)
        if schema_path.is_symlink() or not schema_path.is_file():
            raise ValueError("schema is missing, linked, or drifted from the pinned bytes")
        schema_raw = schema_path.read_bytes()
        if hashlib.sha256(schema_raw).hexdigest() != SCHEMA_SHA256:
            raise ValueError("schema is missing, linked, or drifted from the pinned bytes")
        schema = _load_json_bytes(schema_raw, schema_path)
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(manifest),
                        key=lambda e: list(e.absolute_path))
    except Exception as error:
        return _fail(report, f"schema validation is unavailable: {error}")
    for error in errors:
        _fail(report, "schema: " + error.message.replace("\n", " "))
    if errors:
        return report

    # Input pins re-verified against the actual files.
    if manifest["inputs"] != PINNED_INPUTS:
        _fail(report, "input path/SHA pins differ from the frozen G6 skeleton inputs")
        return report
    loaded_inputs = {}
    for name, pin in PINNED_INPUTS.items():
        try:
            target = ROOT / pin["path"]
            if target.is_symlink() or not target.is_file():
                raise ValueError(f"missing or linked: {pin['path']}")
            raw = target.read_bytes()
            if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
                raise ValueError(f"drifted: {pin['path']}")
            loaded_inputs[name] = _load_json_bytes(raw, target)
        except Exception as error:
            _fail(report, f"input {name} is unavailable: {error}")

    if report["violations"]:
        return report

    try:
        rhs = loaded_inputs["rhs_references"]
        source_manifest = loaded_inputs["source_to_slot_manifest"]
        conformance = loaded_inputs["numerical_conformance"]
        for value, label in ((rhs, "RHS provenance"),
                             (source_manifest, "source-to-slot manifest"),
                             (conformance, "numerical conformance")):
            if not isinstance(value, dict):
                raise ValueError(f"{label} must be a JSON object")
        _verify_provenance(ROOT, rhs, source_manifest, conformance)
    except Exception as error:
        return _fail(report, f"pinned provenance structure is invalid: {error}")

    admitted_statuses = {"blocked", "pending_owner_decision"}
    forbidden = [row["status"] for row in manifest["rows"]
                 if row["status"] not in admitted_statuses]
    if forbidden:
        _fail(report, "v1 has no pinned identity-rule source; status is not admitted: "
              + ", ".join(sorted(set(forbidden))))
        return report

    rows = manifest["rows"]
    slots = [row["slot"] for row in rows]
    if len(set(slots)) != len(slots):
        _fail(report, "duplicate slots")
    rhs_slots = rhs.get("slots", [])
    source_slots = source_manifest.get("slots", [])
    source_by_slot = {slot.get("slot"): slot for slot in source_slots
                      if isinstance(slot, dict)}
    units = {item.get("id"): item.get("native_unit")
             for item in conformance.get("observables", [])
             if isinstance(item, dict)}
    if set(units) != EXPECTED_CONFORMANCE_OBSERVABLES:
        _fail(report, "pinned conformance observable set differs from the frozen contract")
    rhs_time = [slot.get("observable") for slot in rhs_slots
                if slot.get("observable") in TIME_OBSERVABLES]
    if set(rhs_time) != TIME_OBSERVABLES or len(rhs_time) != len(TIME_OBSERVABLES):
        _fail(report, "pinned RHS time observables are not the exact vehicle/sensor/gps set")
    if len(rhs_slots) != EXPECTED_SLOTS or [s.get("slot") for s in rhs_slots] != slots:
        _fail(report, "row order or identity differs from the pinned RHS artifact")
    if len(source_by_slot) != EXPECTED_SLOTS:
        _fail(report, "pinned source-to-slot manifest is incomplete or duplicated")
    for row, rhs_slot in zip(rows, rhs_slots):
        source_slot = source_by_slot.get(row["slot"])
        expected_mapping = {field: rhs_slot.get(field)
                            for field in ("array", "index", "outport", "line_ranges")}
        if (row["source_mapping"] != expected_mapping
                or row["observable"] != rhs_slot.get("observable")):
            _fail(report, f"row {row['slot']} identity differs from pinned RHS provenance")
        if (source_slot is None
                or any(source_slot.get(field) != rhs_slot.get(field)
                       for field in ("slot", "array", "index", "observable"))):
            _fail(report, f"row {row['slot']} differs from pinned source-to-slot identity")
            continue
        expected_metadata = {
            "unit": source_slot.get("unit"),
            "frame": source_slot.get("frame"),
            "datum": source_slot.get("datum"),
            "sample_phase": source_slot.get("sample_phase"),
        }
        if source_slot.get("unit") != units.get(row["observable"]):
            _fail(report, f"row {row['slot']} has inconsistent pinned unit sources")
        if any(row[field] != value for field, value in expected_metadata.items()):
            _fail(report, f"row {row['slot']} metadata differs from pinned provenance")

    for row in rows:
        status = row["status"]
        budgets = {field: row[field] for field in BUDGET_FIELDS}
        if status in ("blocked", "pending_owner_decision"):
            claimed = [field for field in CLAIM_FIELDS if row[field] is not None]
            if claimed:
                _fail(report, f"{row['slot']}: {status} row carries unresolved claim fields: {claimed}")
            if status == "pending_owner_decision" and row["observable"] not in TIME_OBSERVABLES:
                _fail(report, f"{row['slot']}: pending_owner_decision is reserved for time semantics")
            if status == "blocked" and row["observable"] in TIME_OBSERVABLES:
                _fail(report, f"{row['slot']}: unresolved time semantics require owner decision")
        missing = [field for field in AUDIT_CHAIN_FIELDS if row[field] is None]
        if status not in admitted_statuses and missing:
            _fail(report, f"{row['slot']}: non-blocked row missing auditable fields: {missing}")
    return report


def serialize(report):
    return json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    report = validate(args.manifest)
    sys.stdout.buffer.write(serialize(report).encode("utf-8"))
    if report["violations"]:
        return 2
    # A structurally valid v1 skeleton is deliberately still blocked.  Keep
    # this distinct from malformed input so callers cannot mistake structure
    # validity for an accepted G6 budget.
    return 0 if report.get("acceptance") is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
