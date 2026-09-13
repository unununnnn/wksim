"""Generate the deterministic initial G6 budget skeleton for the 56 dynamic slots.

Reads three pinned inputs — the byte-pinned current-RHS provenance artifact,
the source-to-slot manifest, and the frozen numerical conformance contract —
and emits one row per slot.  Every budget field stays null; status is
``blocked`` except the three time observables, which become
``pending_owner_decision`` (their path is a scheduling-semantics check, not a
physical accuracy budget).  This tool cannot approve anything: no ``approved``
status exists and no budget is ever filled.

Usage:
    python3 -B tools/generate_g6_budget_manifest.py [--output PATH]
    (default: deterministic bytes to stdout; nothing is written by default)
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

RHS_ARTIFACT = "validation/e0-current-rhs-references-20260912.json"
RHS_SHA256 = "fa068cc78f8f93e695417d6e315002c799f1bd4d7ef03641a5b236be9cddc188"
SLOT_MANIFEST = "validation/e0-source-to-slot-manifest-20260911.json"
SLOT_MANIFEST_SHA256 = "e48982b4732e4fd84ea26390eb516b7e35aea93267aa741ef3c32538cefa6867"
CONFORMANCE = "Simulator/wksim_core/numerical-conformance-v1.json"
CONFORMANCE_SHA256 = "23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0"

EXPECTED_SLOTS = 56
TIME_OBSERVABLES = frozenset({"vehicle_time", "sensor_time", "gps_time"})
EXPECTED_CONTRACT_ID = "wksim-e0-fixed-reference-native-preservation-v1"
EXPECTED_CONFORMANCE_OBSERVABLES = frozenset({
    "absolute_pressure", "accelerometer", "active_motor_speed",
    "body_angular_rate", "body_motion_acceleration", "differential_pressure",
    "euler_components", "extra_motor_speed", "gps_accuracy_indicators",
    "gps_altitude", "gps_course_encoded", "gps_fix_and_satellites",
    "gps_horizontal_speed", "gps_latitude_longitude", "gps_reserved",
    "gps_time", "gps_velocity_ned", "gyroscope", "magnetic_field",
    "position_ned", "pressure_altitude", "quaternion_components",
    "sensor_reserved", "sensor_time", "sensor_update_mask", "temperature",
    "truth_altitude", "truth_latitude_longitude", "vehicle_identity",
    "vehicle_reserved", "vehicle_time", "velocity_ned",
})


def _strict_json_constant(value):
    raise ValueError(f"non-finite JSON constant in pinned input: {value}")


def _strict_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in pinned input: {key}")
        result[key] = value
    return result


def _load_json_bytes(raw, source):
    try:
        text = raw.decode("utf-8")
    except Exception as error:
        raise ValueError(f"{source} is not UTF-8: {error}") from error
    return json.loads(text, object_pairs_hook=_strict_json_object,
                      parse_constant=_strict_json_constant)


def _load_pinned(root, relative, expected_sha):
    path = Path(root) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"pinned input missing or linked: {relative}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError(f"pinned input drifted: {relative}")
    return _load_json_bytes(raw, path)


def _require_object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _read_reference(root, reference, label):
    _require_object(reference, label)
    relative = reference.get("path")
    expected_sha = reference.get("sha256")
    if (not isinstance(relative, str) or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(expected_sha, str)):
        raise ValueError(f"{label} has malformed path/SHA reference")
    root_path = Path(root).resolve()
    path = root_path / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or linked: {relative}")
    resolved = path.resolve(strict=True)
    if root_path not in resolved.parents:
        raise ValueError(f"{label} escapes the pinned root: {relative}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError(f"{label} drifted: {relative}")
    return path, raw


def _validate_source_mapping(slot, label):
    _require_object(slot, label)
    mapping = slot.get("source_mapping")
    _require_object(mapping, f"{label}.source_mapping")
    if set(mapping) != {"raw", "historical_r1_cpp", "current_slx_11_8"}:
        raise ValueError(f"{label}.source_mapping keys are not exact")
    if not isinstance(mapping["raw"], str) or not mapping["raw"]:
        raise ValueError(f"{label}.source_mapping.raw is malformed")
    historical = _require_object(mapping["historical_r1_cpp"],
                                 f"{label}.source_mapping.historical_r1_cpp")
    current = _require_object(mapping["current_slx_11_8"],
                              f"{label}.source_mapping.current_slx_11_8")
    if set(historical) != {"status", "line_ranges"} \
            or set(current) != {"status", "line_ranges"}:
        raise ValueError(f"{label}.source_mapping nested keys are not exact")
    if historical.get("status") != "bound" or current.get("status") != "unresolved":
        raise ValueError(f"{label}.source_mapping statuses are malformed")
    ranges = historical.get("line_ranges")
    if (not isinstance(ranges, list) or not ranges
            or any(not isinstance(pair, list) or len(pair) != 2
                   or any(not isinstance(line, int) or line < 1 for line in pair)
                   or pair[0] > pair[1]
                   for pair in ranges)):
        raise ValueError(f"{label}.source_mapping historical line ranges are malformed")
    if current.get("line_ranges") is not None:
        raise ValueError(f"{label}.source_mapping current line mapping must be unresolved")
    if slot.get("status") != "unresolved":
        raise ValueError(f"{label} must remain unresolved")
    if slot.get("version") is not None or slot.get("hash") is not None:
        raise ValueError(f"{label} has fabricated source identity")
    if slot.get("unresolved_fields") != ["version", "hash", "frame", "datum"]:
        raise ValueError(f"{label}.unresolved_fields are not exact")


def _verify_provenance(root, rhs, source_manifest, conformance):
    """Close every provenance edge that can be checked from pinned bytes."""
    _require_object(rhs, "RHS provenance")
    _require_object(source_manifest, "source-to-slot manifest")
    _require_object(conformance, "numerical conformance")
    if rhs.get("kind") != "e0_current_rhs_references":
        raise ValueError("RHS provenance artifact kind differs")
    if source_manifest.get("kind") != "e0_source_to_slot_manifest":
        raise ValueError("source-to-slot manifest kind differs")
    if conformance.get("contract_id") != EXPECTED_CONTRACT_ID:
        raise ValueError("numerical conformance contract identity differs")
    rhs_slots = rhs.get("slots")
    source_slots = source_manifest.get("slots")
    observations = conformance.get("observables")
    if (not isinstance(rhs_slots, list) or not isinstance(source_slots, list)
            or not isinstance(observations, list)):
        raise ValueError("pinned provenance slot/observable collections are malformed")
    if (rhs.get("slot_count") != EXPECTED_SLOTS
            or source_manifest.get("slot_count") != EXPECTED_SLOTS
            or len(rhs_slots) != EXPECTED_SLOTS
            or len(source_slots) != EXPECTED_SLOTS):
        raise ValueError("pinned provenance does not carry exactly 56 slots")
    source_by_slot = {}
    for index, slot in enumerate(source_slots):
        _validate_source_mapping(slot, f"source slot {index}")
        key = slot.get("slot")
        if not isinstance(key, str) or key in source_by_slot:
            raise ValueError("source-to-slot manifest has duplicate or malformed slots")
        source_by_slot[key] = slot
    ids = []
    units = {}
    for index, observable in enumerate(observations):
        item = _require_object(observable, f"conformance observable {index}")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in units:
            raise ValueError("numerical conformance observable ids are malformed or duplicated")
        ids.append(identifier)
        units[identifier] = item.get("native_unit")
    if set(ids) != EXPECTED_CONFORMANCE_OBSERVABLES or len(ids) != len(EXPECTED_CONFORMANCE_OBSERVABLES):
        raise ValueError("numerical conformance observable set differs from the frozen contract")
    rhs_time = [slot.get("observable") for slot in rhs_slots
                if isinstance(slot, dict) and slot.get("observable") in TIME_OBSERVABLES]
    if set(rhs_time) != TIME_OBSERVABLES or len(rhs_time) != len(TIME_OBSERVABLES):
        raise ValueError("RHS time observables are not the exact vehicle/sensor/gps set")
    for index, slot in enumerate(rhs_slots):
        slot = _require_object(slot, f"RHS slot {index}")
        key = slot.get("slot")
        source_slot = source_by_slot.get(key)
        if (source_slot is None
                or any(source_slot.get(field) != slot.get(field)
                       for field in ("slot", "array", "index", "observable"))):
            raise ValueError(f"source-to-slot identity differs at {key}")
        if slot.get("observable") not in units or source_slot.get("unit") != units[slot["observable"]]:
            raise ValueError(f"pinned unit metadata differs at {key}")
    v1_reference = rhs.get("v1_artifact")
    artifact_path, artifact_raw = _read_reference(root, v1_reference, "RHS v1 artifact")
    artifact = _load_json_bytes(artifact_raw, artifact_path)
    _require_object(artifact, "RHS v1 artifact")
    if (artifact.get("kind") != "e0_current_source_mapping"
            or artifact.get("status") != "bound"
            or artifact.get("provenance_only") is not True
            or artifact.get("slot_count") != EXPECTED_SLOTS):
        raise ValueError("RHS v1 source-mapping artifact identity is malformed")
    artifact_slots = artifact.get("slots")
    if not isinstance(artifact_slots, list) or len(artifact_slots) != EXPECTED_SLOTS:
        raise ValueError("RHS v1 source-mapping artifact slots are malformed")
    for index, (rhs_slot, artifact_slot) in enumerate(zip(rhs_slots, artifact_slots)):
        _require_object(artifact_slot, f"RHS v1 artifact slot {index}")
        if any(artifact_slot.get(field) != rhs_slot.get(field)
               for field in ("slot", "array", "index", "observable", "outport", "line_ranges")):
            raise ValueError(f"RHS v1 source-mapping slot differs at {index}")
    generated_sources = []
    for owner, label in ((rhs, "RHS"), (artifact, "RHS v1 artifact")):
        generated = _require_object(owner.get("generated_source"), f"{label}.generated_source")
        generated_sources.append(generated)
    if generated_sources[0] != generated_sources[1]:
        raise ValueError("generated-source provenance differs across pinned artifacts")
    generated = generated_sources[0]
    source_path, source_raw = _read_reference(
        root,
        {"path": generated.get("artifact_relative_path"),
         "sha256": generated.get("sha256")},
        "generated source")
    if (generated.get("name") != "Exp1_MinModelTemp.cpp"
            or generated.get("model_version") != "11.8"
            or generated.get("generation_run") != "short-cycle-codegen-01"
            or generated.get("size_bytes") != len(source_raw)):
        raise ValueError("generated-source identity or size differs")
    evidence = _require_object(generated.get("evidence"), "generated-source evidence")
    evidence_path, evidence_raw = _read_reference(root, evidence, "generated-source evidence")
    evidence_json = _load_json_bytes(evidence_raw, evidence_path)
    _require_object(evidence_json, "generated-source evidence")
    evidence_sources = evidence_json.get("sources")
    if not isinstance(evidence_sources, list):
        raise ValueError("generated-source evidence sources are malformed")
    suffix = generated["artifact_relative_path"].replace("\\", "/")
    suffix = "/".join(suffix.split("/")[-2:])
    matches = [item for item in evidence_sources
               if isinstance(item, dict)
               and isinstance(item.get("relative_path"), str)
               and item["relative_path"].replace("\\", "/").endswith(suffix)]
    if len(matches) != 1 or matches[0].get("sha256") != generated.get("sha256") \
            or matches[0].get("size_bytes") != generated.get("size_bytes"):
        raise ValueError("generated-source evidence does not close the source bytes")
    contract = _require_object(source_manifest.get("contract"), "source contract")
    if (contract.get("path") != CONFORMANCE or contract.get("sha256") != CONFORMANCE_SHA256
            or contract.get("contract_id") != EXPECTED_CONTRACT_ID):
        raise ValueError("source contract provenance differs")
    artifact_contract = _require_object(artifact.get("contract"), "source-mapping contract")
    if artifact_contract != contract:
        raise ValueError("source-mapping contract provenance differs")
    model_source = _require_object(source_manifest.get("model_source"), "model source provenance")
    contract_identity = _require_object(conformance.get("identity"),
                                        "conformance identity provenance")
    conformance_archive = _require_object(contract_identity.get("archive"),
                                          "conformance archive provenance")
    conformance_slx = _require_object(contract_identity.get("slx"),
                                      "conformance SLX provenance")
    historical = _require_object(model_source.get("historical_r1_cpp"), "historical model source")
    archive = _require_object(historical.get("archive"), "historical model archive")
    if conformance_archive.get("sha256") != archive.get("sha256"):
        raise ValueError("historical archive is not bound to the conformance identity")
    archive_path, archive_raw = _read_reference(root, archive, "historical model archive")
    if historical.get("status") != "bound" or historical.get("model_version") != "11.0":
        raise ValueError("historical model provenance is not bound")
    member = archive.get("member")
    member_sha = archive.get("member_sha256")
    if not isinstance(member, str) or not isinstance(member_sha, str):
        raise ValueError("historical archive member provenance is malformed")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as bundle:
            member_raw = bundle.read(member)
    except Exception as error:
        raise ValueError(f"historical archive member is unreadable: {error}") from error
    if hashlib.sha256(member_raw).hexdigest() != member_sha:
        raise ValueError("historical archive member bytes drifted")
    if contract_identity.get("target_cpp_sha256") != member_sha:
        raise ValueError("historical archive member is not bound to the conformance identity")
    current = _require_object(model_source.get("current_slx_11_8"), "current SLX source")
    if current.get("status") != "unresolved" or current.get("line_mapping") is not None:
        raise ValueError("current SLX provenance must remain unresolved")
    if conformance_slx.get("sha256") != current.get("sha256"):
        raise ValueError("current SLX is not bound to the conformance identity")
    _read_reference(root, current, "current SLX source")
    return {"source_by_slot": source_by_slot, "units": units}


def generate(root=ROOT):
    """Build the skeleton manifest; fail closed on any pinned-input drift."""
    rhs = _load_pinned(root, RHS_ARTIFACT, RHS_SHA256)
    source_manifest = _load_pinned(root, SLOT_MANIFEST, SLOT_MANIFEST_SHA256)
    conformance = _load_pinned(root, CONFORMANCE, CONFORMANCE_SHA256)
    provenance = _verify_provenance(root, rhs, source_manifest, conformance)
    slots = rhs["slots"]
    source_by_slot = provenance["source_by_slot"]
    units = provenance["units"]

    rows = []
    for slot in slots:
        observable = slot["observable"]
        source_slot = source_by_slot.get(slot["slot"])
        identity_fields = ("slot", "array", "index", "observable")
        if (source_slot is None
                or any(source_slot.get(field) != slot.get(field) for field in identity_fields)):
            raise ValueError(f"source-to-slot identity differs at {slot['slot']}")
        if source_slot.get("unit") != units.get(observable):
            raise ValueError(f"pinned unit metadata differs at {slot['slot']}")
        rows.append({
            "slot": slot["slot"],
            "observable": observable,
            "source_mapping": {
                "array": slot["array"],
                "index": slot["index"],
                "outport": slot["outport"],
                "line_ranges": slot["line_ranges"],
            },
            "unit": source_slot.get("unit"),
            "frame": source_slot.get("frame"),
            "datum": source_slot.get("datum"),
            "sample_phase": source_slot.get("sample_phase"),
            "metric": None,
            "abs_budget": None,
            "rel_budget": None,
            "rms_budget": None,
            "derivation": None,
            "domain": None,
            "approval": None,
            "contract_sha256": None,
            "status": ("pending_owner_decision"
                       if observable in TIME_OBSERVABLES else "blocked"),
        })
    return {
        "schema_version": 1,
        "kind": "g6_budget_manifest",
        "acceptance": False,
        "inputs": {
            "rhs_references": {"path": RHS_ARTIFACT, "sha256": RHS_SHA256},
            "source_to_slot_manifest": {"path": SLOT_MANIFEST,
                                        "sha256": SLOT_MANIFEST_SHA256},
            "numerical_conformance": {"path": CONFORMANCE,
                                      "sha256": CONFORMANCE_SHA256},
        },
        "slot_count": EXPECTED_SLOTS,
        "rows": rows,
    }


def serialize(manifest):
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _canonical_output(path):
    target = Path(path).absolute()
    if target.exists() or target.is_symlink():
        raise ValueError("output already exists or is a symlink")
    parent = target.parent
    if (parent.is_symlink() or not parent.is_dir()
            or parent.resolve(strict=True) != parent):
        raise ValueError("output parent must be an existing canonical directory")
    return target


def _write_output(path, raw):
    """Publish bytes with create-only semantics in a canonical directory."""
    target = _canonical_output(path)
    if os.name == "nt":
        raise ValueError("create-only publication requires POSIX directory handles; unsupported on Windows")
    required = (os.O_DIRECTORY, os.O_NOFOLLOW)
    if any(not isinstance(flag, int) for flag in required) \
            or any(function not in os.supports_dir_fd
                   for function in (os.open, os.link, os.unlink, os.stat)):
        raise ValueError("create-only publication primitives are unavailable")
    parent = target.parent
    parent_fd = os.open(str(parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary_name = None
    temporary_fd = None
    try:
        parent_stat = os.fstat(parent_fd)
        path_stat = os.stat(str(parent), follow_symlinks=False)
        if (not stat.S_ISDIR(parent_stat.st_mode)
                or parent_stat.st_dev != path_stat.st_dev
                or parent_stat.st_ino != path_stat.st_ino):
            raise ValueError("output parent changed while it was opened")
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("output already exists or is a symlink")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        for _ in range(32):
            candidate = f".{target.name}.{secrets.token_hex(8)}"
            try:
                temporary_fd = os.open(candidate, flags, 0o600, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_fd is None or temporary_name is None:
            raise ValueError("unable to allocate a private output temporary")
        with os.fdopen(temporary_fd, "wb") as stream:
            temporary_fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link is create-only: it cannot replace a pre-existing target,
        # including one created after the initial canonical-path check.
        os.link(temporary_name, target.name, src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd, follow_symlinks=False)
        os.unlink(temporary_name, dir_fd=parent_fd)
        temporary_name = None
        os.fsync(parent_fd)
    except Exception:
        if temporary_fd is not None:
            try:
                os.close(temporary_fd)
            except OSError:
                pass
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        raise
    finally:
        os.close(parent_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = generate()
    except Exception as error:
        print(json.dumps({"status": "fail-closed", "error": str(error)}))
        return 2
    raw = serialize(manifest)
    if args.output:
        try:
            _write_output(args.output, raw)
        except Exception as error:
            print(json.dumps({"status": "fail-closed", "error": str(error)}))
            return 2
    sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
