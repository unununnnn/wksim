"""Validate the provenance-only e0 source-to-slot manifest offline.

The JSON Schema describes the shape. This validator adds the cross-record
checks that JSON Schema cannot express: exact 56-slot coverage, contract
observable/index ownership, historical R1 line-range parsing, direct ZIP
member identity checks without extraction, current SLX identity checks, and
recursive rejection of numerical-budget or approval fields.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import zipfile

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError
except ImportError:  # pragma: no cover - exercised only on an incomplete tool host
    Draft202012Validator = None
    SchemaError = Exception


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_e0_source_to_slot_manifest import (
    EXPECTED_DYNAMIC_SLOTS,
    EXCLUDED_SEMANTIC_STATUS,
    FROZEN_CONTRACT_ID,
    FROZEN_CONTRACT_SHA256,
    KIND,
    CURRENT_SLX_PATH,
    CURRENT_SLX_SHA256,
    MODEL_ARCHIVE_PATH,
    MODEL_ARCHIVE_SHA256,
    MODEL_MEMBER_PATH,
    MODEL_MEMBER_SHA256,
    SCHEMA_VERSION,
    dynamic_scalars,
    parse_cpp_line_ranges,
)


DEFAULT_SCHEMA = Path("docs/plan/59-e0-source-to-slot-manifest.schema.json")
DEFAULT_CONTRACT = Path("Simulator/wksim_core/numerical-conformance-v1.json")
DEFAULT_MANIFEST = Path("validation/e0-source-to-slot-manifest-20260911.json")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEYS = frozenset({"approval", "budget", "budgets"})
NULLABLE_FIELDS = frozenset({
    "version",
    "hash",
    "unit",
    "frame",
    "datum",
    "sample_phase",
})


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_zip_member(archive_path, member_path):
    """Hash one ZIP member in place; never extract it to the filesystem."""
    digest = hashlib.sha256()
    with zipfile.ZipFile(archive_path, "r") as archive:
        info = archive.getinfo(member_path)
        if info.is_dir():
            raise ValueError(f"ZIP member is a directory: {member_path}")
        with archive.open(info, "r") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value):
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _walk_forbidden(value, path="$", errors=None):
    errors = [] if errors is None else errors
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_KEYS or "budget" in lowered or "approval" in lowered:
                errors.append(f"{path}.{key}: forbidden budget/approval field")
            _walk_forbidden(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]", errors)
    return errors


def _field_value(slot, field):
    return slot.get(field)


def _resolve_artifact_path(value, artifact_root=None):
    """Resolve a declared artifact path inside the repo or an owned mirror.

    ``artifact_root`` is an external private-artifact mirror.  The manifest
    still carries the logical repository-relative path; supplying a root only
    changes where that exact path is looked up.  The resolved path must stay
    below the selected root so a malformed manifest cannot escape it.
    """
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    root = ROOT if artifact_root is None else Path(artifact_root).resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _validate_model_source(model_source, errors, artifact_root=None):
    """Validate both source layers and the exact frozen archive member."""
    prefix = "model_source"
    if not isinstance(model_source, dict):
        errors.append(f"{prefix}: must be an object")
        return
    expected_keys = {"historical_r1_cpp", "current_slx_11_8"}
    missing = expected_keys - set(model_source)
    extras = set(model_source) - expected_keys
    if missing:
        errors.append(f"{prefix}: missing fields {sorted(missing)}")
    if extras:
        errors.append(f"{prefix}: unknown fields {sorted(extras)}")

    historical = model_source.get("historical_r1_cpp")
    if not isinstance(historical, dict):
        errors.append(f"{prefix}.historical_r1_cpp: must be an object")
    else:
        if historical.get("status") != "bound":
            errors.append(f"{prefix}.historical_r1_cpp.status must be 'bound'")
        if historical.get("model_version") != "11.0":
            errors.append(f"{prefix}.historical_r1_cpp.model_version must be '11.0'")
        archive = historical.get("archive")
        if not isinstance(archive, dict):
            errors.append(f"{prefix}.historical_r1_cpp.archive: must be an object")
        else:
            expected_archive = {
                "path": MODEL_ARCHIVE_PATH.as_posix(),
                "sha256": MODEL_ARCHIVE_SHA256,
                "member": MODEL_MEMBER_PATH,
                "member_sha256": MODEL_MEMBER_SHA256,
            }
            for field, expected in expected_archive.items():
                if archive.get(field) != expected:
                    errors.append(
                        f"{prefix}.historical_r1_cpp.archive.{field} differs from frozen identity"
                    )
            archive_path = _resolve_artifact_path(archive.get("path"), artifact_root)
            if archive_path is None or not archive_path.is_file():
                location = "repository file" if artifact_root is None else "artifact-root file"
                errors.append(
                    f"{prefix}.historical_r1_cpp.archive.path is not a readable {location}"
                )
            else:
                try:
                    actual_archive = sha256_file(archive_path)
                except OSError as exc:
                    errors.append(f"{prefix}.historical_r1_cpp.archive.path cannot be read: {exc}")
                else:
                    if actual_archive != MODEL_ARCHIVE_SHA256:
                        errors.append(
                            f"{prefix}.historical_r1_cpp.archive SHA-256 differs from frozen bytes"
                        )
                    elif archive.get("member") == MODEL_MEMBER_PATH:
                        try:
                            actual_member = sha256_zip_member(archive_path, MODEL_MEMBER_PATH)
                        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
                            errors.append(
                                f"{prefix}.historical_r1_cpp.archive.member cannot be validated: {exc}"
                            )
                        else:
                            if actual_member != MODEL_MEMBER_SHA256:
                                errors.append(
                                    f"{prefix}.historical_r1_cpp.archive member SHA-256 differs"
                                )

    current = model_source.get("current_slx_11_8")
    if not isinstance(current, dict):
        errors.append(f"{prefix}.current_slx_11_8: must be an object")
    else:
        if current.get("status") != "unresolved":
            errors.append(f"{prefix}.current_slx_11_8.status must be 'unresolved'")
        if current.get("model_version") != "11.8":
            errors.append(f"{prefix}.current_slx_11_8.model_version must be '11.8'")
        if current.get("line_mapping") is not None:
            errors.append(f"{prefix}.current_slx_11_8.line_mapping must remain null")
        slx_path = _resolve_artifact_path(current.get("path"), artifact_root)
        if current.get("path") != CURRENT_SLX_PATH.as_posix():
            errors.append(f"{prefix}.current_slx_11_8.path differs from frozen identity")
        if current.get("sha256") != CURRENT_SLX_SHA256:
            errors.append(f"{prefix}.current_slx_11_8.sha256 differs from frozen identity")
        if slx_path is None or not slx_path.is_file():
            location = "repository file" if artifact_root is None else "artifact-root file"
            errors.append(
                f"{prefix}.current_slx_11_8.path is not a readable {location}"
            )
        else:
            try:
                actual_slx = sha256_file(slx_path)
            except OSError as exc:
                errors.append(f"{prefix}.current_slx_11_8.path cannot be read: {exc}")
            else:
                if actual_slx != CURRENT_SLX_SHA256:
                    errors.append(f"{prefix}.current_slx_11_8 bytes differ from frozen identity")


def _validate_slot_shape(slot, position, expected_by_key, errors):
    prefix = f"slots[{position}]"
    if not isinstance(slot, dict):
        errors.append(f"{prefix}: must be an object")
        return
    required = {
        "slot", "array", "index", "observable", "source_mapping", "version",
        "hash", "unit", "frame", "datum", "sample_phase", "status",
        "unresolved_fields",
    }
    missing = required - set(slot)
    extras = set(slot) - required
    if missing:
        errors.append(f"{prefix}: missing fields {sorted(missing)}")
    if extras:
        errors.append(f"{prefix}: unknown fields {sorted(extras)}")
    array = slot.get("array")
    index = slot.get("index")
    valid_key = isinstance(array, str) and type(index) is int
    key = (array, index) if valid_key else None
    if not valid_key or key not in expected_by_key:
        errors.append(f"{prefix}: unexpected scalar {array!r}[{index!r}]")
    else:
        expected = expected_by_key[key]
        if slot.get("observable") != expected["id"]:
            errors.append(
                f"{prefix}: observable {slot.get('observable')!r} does not own {array}[{index}]"
            )
        if slot.get("unit") != expected.get("native_unit"):
            errors.append(f"{prefix}: unit differs from frozen contract native_unit")
        mapping = slot.get("source_mapping")
        raw_source = mapping.get("raw") if isinstance(mapping, dict) else None
        if raw_source != expected.get("source"):
            errors.append(f"{prefix}: source_mapping.raw differs from frozen contract source")
    if slot.get("slot") != f"{array}[{index}]":
        errors.append(f"{prefix}: slot string does not match array/index")
    if type(index) is not int or index < 0:
        errors.append(f"{prefix}: index must be a non-negative integer")
    slot_status = slot.get("status")
    if not isinstance(slot_status, str) or slot_status not in {"unresolved", "complete"}:
        errors.append(f"{prefix}: invalid status")

    mapping = slot.get("source_mapping")
    if not isinstance(mapping, dict):
        errors.append(f"{prefix}.source_mapping: must be an object")
    else:
        required_mapping = {"raw", "historical_r1_cpp", "current_slx_11_8"}
        missing_mapping = required_mapping - set(mapping)
        extra_mapping = set(mapping) - required_mapping
        if missing_mapping:
            errors.append(f"{prefix}.source_mapping: missing fields {sorted(missing_mapping)}")
        if extra_mapping:
            errors.append(f"{prefix}.source_mapping: unknown fields {sorted(extra_mapping)}")
        historical = mapping.get("historical_r1_cpp")
        expected_ranges = []
        try:
            expected_ranges = parse_cpp_line_ranges(mapping.get("raw"))
        except ValueError as exc:
            errors.append(f"{prefix}.source_mapping.raw: {exc}")
        if not isinstance(historical, dict):
            errors.append(f"{prefix}.source_mapping.historical_r1_cpp: must be an object")
        else:
            if historical.get("status") != "bound":
                errors.append(f"{prefix}.source_mapping.historical_r1_cpp.status must be 'bound'")
            if historical.get("line_ranges") != expected_ranges:
                errors.append(
                    f"{prefix}.source_mapping.historical_r1_cpp.line_ranges differ from raw cpp references"
                )
        current = mapping.get("current_slx_11_8")
        if not isinstance(current, dict):
            errors.append(f"{prefix}.source_mapping.current_slx_11_8: must be an object")
        else:
            if current.get("status") != "unresolved":
                errors.append(f"{prefix}.source_mapping.current_slx_11_8.status must be 'unresolved'")
            if current.get("line_ranges") is not None:
                errors.append(f"{prefix}.source_mapping.current_slx_11_8.line_ranges must remain null")

    digest = slot.get("hash")
    if digest is not None and not _is_sha256(digest):
        errors.append(f"{prefix}.hash: expected lowercase SHA-256 or null")
    version = slot.get("version")
    if version is not None and (not isinstance(version, str) or not version):
        errors.append(f"{prefix}.version: expected non-empty string or null")
    unresolved = slot.get("unresolved_fields")
    if not isinstance(unresolved, list):
        errors.append(f"{prefix}.unresolved_fields: expected a unique string list")
        unresolved = []
    elif not all(isinstance(field, str) for field in unresolved):
        errors.append(f"{prefix}.unresolved_fields: expected a unique string list")
        unresolved = [field for field in unresolved if isinstance(field, str)]
    elif len(set(unresolved)) != len(unresolved):
        errors.append(f"{prefix}.unresolved_fields: expected a unique string list")
    if not all(field in NULLABLE_FIELDS for field in unresolved):
        errors.append(f"{prefix}.unresolved_fields: contains an unknown field")
    actual_nulls = {field for field in NULLABLE_FIELDS if _field_value(slot, field) is None}
    if set(unresolved) != actual_nulls:
        errors.append(
            f"{prefix}: null fields and unresolved_fields differ; "
            f"null={sorted(actual_nulls)}, unresolved={sorted(unresolved)}"
        )
    if actual_nulls and slot.get("status") != "unresolved":
        errors.append(f"{prefix}: null evidence requires status='unresolved'")
    if not actual_nulls and slot.get("status") != "complete":
        errors.append(f"{prefix}: complete evidence requires status='complete'")


def validate_manifest(
    manifest_path,
    contract_path,
    schema_path=DEFAULT_SCHEMA,
    artifact_root=None,
):
    """Return a list of validation errors; an empty list means valid."""
    errors = []
    manifest_path = Path(manifest_path)
    contract_path = Path(contract_path).resolve()
    schema_path = Path(schema_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"cannot read manifest: {exc}"]
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if Draft202012Validator is None:
            errors.append("jsonschema is required to validate the manifest schema")
        else:
            Draft202012Validator.check_schema(schema)
            errors.extend(
                f"schema instance {'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
                for error in sorted(
                    Draft202012Validator(schema).iter_errors(manifest),
                    key=lambda error: tuple(str(value) for value in error.absolute_path),
                )
            )
    except SchemaError as exc:
        errors.append(f"schema file is invalid: {exc.message}")
    except (OSError, ValueError) as exc:
        errors.append(f"cannot read schema: {exc}")
        schema = None
    canonical_contract = (ROOT / DEFAULT_CONTRACT).resolve()
    if contract_path != canonical_contract:
        return errors + [
            f"contract must be the frozen canonical file {DEFAULT_CONTRACT.as_posix()}"
        ]
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return errors + [f"cannot read contract: {exc}"]
    if not isinstance(manifest, dict):
        return errors + ["manifest root must be an object"]
    if not isinstance(contract, dict):
        return errors + ["contract root must be an object"]
    if sha256_file(contract_path) != FROZEN_CONTRACT_SHA256:
        errors.append("frozen contract SHA-256 differs")
    if contract.get("contract_id") != FROZEN_CONTRACT_ID:
        errors.append("frozen contract ID differs")
    errors.extend(_walk_forbidden(manifest))
    required = {
        "schema_version", "kind", "status", "contract", "model_source",
        "slot_count", "slots",
    }
    errors.extend(f"manifest missing field {field}" for field in sorted(required - set(manifest)))
    errors.extend(f"manifest has unknown field {field}" for field in sorted(set(manifest) - required))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest schema_version must be 2")
    if manifest.get("kind") != KIND:
        errors.append(f"manifest kind must be {KIND!r}")
    manifest_status = manifest.get("status")
    if not isinstance(manifest_status, str) or manifest_status not in {"unresolved", "complete"}:
        errors.append("manifest status must be unresolved or complete")
    _validate_model_source(manifest.get("model_source"), errors, artifact_root)

    contract_meta = manifest.get("contract")
    if not isinstance(contract_meta, dict):
        errors.append("manifest contract must be an object")
    else:
        if contract_meta.get("contract_id") != contract.get("contract_id"):
            errors.append("manifest contract_id differs from contract")
        if contract_meta.get("sha256") != sha256_file(contract_path):
            errors.append("manifest contract sha256 differs from contract bytes")
        if not isinstance(contract_meta.get("path"), str) or not contract_meta.get("path"):
            errors.append("manifest contract path must be non-empty")
        else:
            expected_path = contract_path.as_posix()
            try:
                expected_path = contract_path.relative_to(ROOT).as_posix()
            except ValueError:
                pass
            if contract_meta["path"] != expected_path:
                errors.append("manifest contract path differs from the supplied contract")

    try:
        dynamic = dynamic_scalars(contract)
    except ValueError as exc:
        return errors + [str(exc)]
    expected_by_key = {(array, index): observable for array, index, observable in dynamic}
    slots = manifest.get("slots")
    if manifest.get("slot_count") != EXPECTED_DYNAMIC_SLOTS:
        errors.append("slot_count must be 56")
    if not isinstance(slots, list) or len(slots) != EXPECTED_DYNAMIC_SLOTS:
        errors.append("slots must contain exactly 56 items")
        slots = slots if isinstance(slots, list) else []
    seen = set()
    for position, slot in enumerate(slots):
        _validate_slot_shape(slot, position, expected_by_key, errors)
        if isinstance(slot, dict):
            array, index = slot.get("array"), slot.get("index")
            if isinstance(array, str) and type(index) is int:
                key = (array, index)
                if key in seen:
                    errors.append(f"slots[{position}]: duplicate scalar {key[0]}[{key[1]}]")
                seen.add(key)
    if seen != set(expected_by_key):
        errors.append(
            f"slot coverage differs from contract: missing={sorted(set(expected_by_key) - seen)}, "
            f"extra={sorted(seen - set(expected_by_key))}"
        )
    expected_status = "complete" if slots and not any(
        slot.get("status") != "complete" or slot.get("unresolved_fields")
        for slot in slots if isinstance(slot, dict)
    ) else "unresolved"
    model_source = manifest.get("model_source")
    current_source = (
        model_source.get("current_slx_11_8")
        if isinstance(model_source, dict)
        else None
    )
    if isinstance(current_source, dict) and current_source.get("status") == "unresolved":
        expected_status = "unresolved"
    if manifest.get("status") != expected_status:
        errors.append(f"manifest status should be {expected_status!r}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help=(
            "external private-artifact mirror root; declared manifest paths "
            "are resolved below this directory"
        ),
    )
    args = parser.parse_args(argv)
    errors = validate_manifest(
        args.manifest,
        args.contract,
        args.schema,
        artifact_root=args.artifact_root,
    )
    result = {
        "manifest": str(args.manifest),
        "artifact_root": str(args.artifact_root) if args.artifact_root else None,
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
