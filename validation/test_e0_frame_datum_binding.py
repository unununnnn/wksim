"""Fail-closed offline validator for the G6/B2 e0 frame/datum binding supplement.

The supplement is evidence binding only. This test never runs the model,
MATLAB, ROS, a flight controller, UE, a native binary or a build. It reads
committed blobs at HEAD and asserts that the supplement

* pins exactly the frozen id -> path table, with each digest equal to the
  SHA-256 of the committed blob at HEAD and no ``git diff HEAD`` drift,
* covers the exact committed 56 dynamic / 64 excluded slot set,
* uses only the frozen frame and datum tokens and only the frozen
  per-observable binding,
* cites only frozen evidence ids whose frozen locator/quote pair resolves
  against the committed HEAD blob and whose frozen support covers the value,
* keeps every null explicitly unresolved with a precise owner reason,
* covers every owner decision in both directions,
* treats ``current_generated_rhs`` as a complete pinned RHS symbol identity
  (``rhs.text`` or a ``references[].name`` / ``references[].path``), not a
  blob substring,
* recomputes every declared ``counts`` key from the payload structure, and
* never flips budget approval, G6 acceptance or physical accuracy.

A repeated JSON object key is refused at load time, because ``json.loads``
would silently keep the last value and could hide a substituted pin.

The worktree bytes of a pinned file are deliberately never hashed: checkout
EOL conversion must not change the verdict.

Run:

    python -B -m pytest validation/test_e0_frame_datum_binding.py -q -p no:cacheprovider
    python -B -m unittest validation.test_e0_frame_datum_binding -v
"""

import copy
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BINDING_PATH = ROOT / "validation" / "e0-frame-datum-binding-20260914.json"
CONTRACT_REL = "Simulator/wksim_core/numerical-conformance-v1.json"
MANIFEST_REL = "validation/e0-source-to-slot-manifest-20260911.json"
RHS_REL = "validation/e0-current-rhs-references-20260912.json"

FROZEN_CONTRACT_ID = "wksim-e0-fixed-reference-native-preservation-v1"
FROZEN_CONTRACT_SHA256 = "23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0"
BASELINE_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
EXCLUDED_STATUS = ("interface_metadata", "reserved_not_physical_coverage")
TOTAL_SLOTS = 120
DYNAMIC_SLOTS = 56
EXCLUDED_SLOTS = 64
SEMANTIC_DYNAMIC = 53
TIME_FIELDS = 3

HEX64 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA1 = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_KEY_RE = re.compile(
    r"abs_budget|rel_budget|rms_budget|approv|accept|sign_off|signed", re.IGNORECASE
)
ALLOWED_FLAG_KEYS = frozenset({"budget_approved", "g6_acceptance", "physical_accuracy"})
ALLOWED_BINDING_STATUS = frozenset({
    "bound",
    "bound_but_owner_items_open",
    "unresolved_owner_decision",
})
REQUIRED_SLOT_FIELDS = {
    "slot", "array", "index", "observable", "contract_semantic_status",
    "native_unit", "source_label", "current_generated_rhs", "sample_phase",
    "frame", "datum", "open_owner_decisions", "binding_status",
}

# ---------------------------------------------------------------------------
# Frozen identity tables.  These mirror committed evidence and are independent
# of the payload, so the payload cannot widen itself.
# ---------------------------------------------------------------------------
EXPECTED_PINS = {
    "frozen_contract": "Simulator/wksim_core/numerical-conformance-v1.json",
    "slot_manifest": "validation/e0-source-to-slot-manifest-20260911.json",
    "current_source_mapping": "validation/e0-current-source-mapping-20260912.json",
    "current_rhs_references": "validation/e0-current-rhs-references-20260912.json",
    "core_readme": "Simulator/wksim_core/README.md",
    "core_state_stream": "Simulator/wksim_core/state_stream.py",
    "core_model": "Simulator/wksim_core/model.py",
    "core_model_parameters": "Simulator/wksim_core/model_parameters.py",
    "core_px4_mavlink": "Simulator/wksim_core/px4_mavlink.py",
    "core_gnss_event": "Simulator/wksim_core/gnss_event.py",
    "ue55_readme": "Simulator/ue55/README.md",
    "readiness_plan": "docs/plan/2026-09-08-numerical-contract-readiness.md",
    "dynamic_source_map": "docs/plan/59-e0-dynamic-budget-source-map.md",
    "g6_remediation_contract": "docs/plan/10-g6-remediation-contract.md",
    "same_source_command": "docs/plan/59-e0-same-source-command.md",
    "stage2_boundary": "docs/plan/g6-c3g-stage2-boundary.md",
    "slot_manifest_schema": "docs/plan/59-e0-source-to-slot-manifest.schema.json",
    "sampling_contract": "docs/2026-09-09-reference-sampling-contract.md",
    "r1_report": "docs/2026-09-09-numerical-conformance-report.md",
    "slot_manifest_validator": "tools/validate_e0_source_to_slot_manifest.py",
    "slot_manifest_generator": "tools/generate_e0_source_to_slot_manifest.py",
    "g6_budget_audit": "validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json",
    "g6_frontier_review": "validation/coordination/luna-g6-frontier-20260914-01/review.md",
}

FRAME_TOKENS = frozenset({"NED", "FRD", "lat_lon_deg"})
DATUM_TOKENS = frozenset({
    "model_local_NED_frame_reference",
    "degC_zero_at_273.15000000000003_K",
})

# observable -> (frame, frame_owner, datum, datum_owner, open_owner_decisions)
_TIME_BINDING = (None, "OD-01", None, "OD-02", ("OD-01", "OD-02"))
_ALT_BINDING = (None, "OD-04", None, "OD-05", ("OD-04", "OD-05"))
_LL_BINDING = ("lat_lon_deg", None, None, "OD-03", ("OD-03",))
EXPECTED_BINDINGS = {
    "vehicle_time": _TIME_BINDING,
    "sensor_time": _TIME_BINDING,
    "gps_time": _TIME_BINDING,
    "velocity_ned": ("NED", None, "model_local_NED_frame_reference", None, ("OD-22",)),
    "position_ned": ("NED", None, "model_local_NED_frame_reference", None, ("OD-22",)),
    "gps_velocity_ned": ("NED", None, "model_local_NED_frame_reference", None, ("OD-22",)),
    "euler_components": (None, "OD-16", None, "OD-16", ("OD-16",)),
    "quaternion_components": (None, "OD-15", None, "OD-15", ("OD-15",)),
    "active_motor_speed": (None, "OD-19", None, "OD-19", ("OD-19",)),
    "extra_motor_speed": (None, "OD-19", None, "OD-19", ("OD-19", "OD-20")),
    "body_motion_acceleration": ("FRD", None, None, "OD-21", ("OD-21",)),
    "body_angular_rate": ("FRD", None, None, "OD-24", ("OD-24",)),
    "truth_latitude_longitude": _LL_BINDING,
    "gps_latitude_longitude": _LL_BINDING,
    "truth_altitude": _ALT_BINDING,
    "pressure_altitude": _ALT_BINDING,
    "gps_altitude": _ALT_BINDING,
    "accelerometer": ("FRD", None, None, "OD-18", ("OD-17", "OD-18")),
    "gyroscope": ("FRD", None, None, "OD-18", ("OD-17", "OD-18")),
    "magnetic_field": (None, "OD-06", None, "OD-07", ("OD-06", "OD-07")),
    "absolute_pressure": (None, "OD-08", None, "OD-09", ("OD-08", "OD-09")),
    "differential_pressure": (None, "OD-08", None, "OD-09", ("OD-08", "OD-09")),
    "temperature": (None, "OD-10", "degC_zero_at_273.15000000000003_K", None, ("OD-10",)),
    "gps_accuracy_indicators": (None, "OD-11", None, "OD-12", ("OD-11", "OD-12")),
    "gps_horizontal_speed": (None, "OD-23", None, "OD-23", ("OD-23",)),
    "gps_course_encoded": (None, "OD-13", None, "OD-14", ("OD-13", "OD-14")),
}

# evidence id -> (path, supports)
EXPECTED_EVIDENCE = {
    "EV-1": ("Simulator/wksim_core/README.md", frozenset({"NED"})),
    "EV-2": ("Simulator/wksim_core/README.md", frozenset({"FRD"})),
    "EV-3": ("Simulator/wksim_core/state_stream.py", frozenset({"NED"})),
    "EV-4": ("Simulator/wksim_core/state_stream.py", frozenset({"FRD"})),
    "EV-5": ("Simulator/wksim_core/model.py", frozenset({"NED", "FRD"})),
    "EV-6": ("Simulator/wksim_core/model_parameters.py",
             frozenset({"NED", "model_local_NED_frame_reference"})),
    "EV-7": ("Simulator/wksim_core/model_parameters.py", frozenset({"lat_lon_deg"})),
    "EV-8": ("docs/plan/2026-09-08-numerical-contract-readiness.md", frozenset({"NED"})),
    "EV-9": ("docs/plan/2026-09-08-numerical-contract-readiness.md", frozenset({"NED"})),
    "EV-10": ("docs/plan/2026-09-08-numerical-contract-readiness.md", frozenset({"FRD"})),
    "EV-11": ("docs/plan/2026-09-08-numerical-contract-readiness.md", frozenset({"FRD"})),
    "EV-12": ("docs/plan/2026-09-08-numerical-contract-readiness.md",
              frozenset({"model_local_NED_frame_reference"})),
    "EV-13": ("Simulator/wksim_core/numerical-conformance-v1.json", frozenset({"lat_lon_deg"})),
    "EV-14": ("Simulator/wksim_core/numerical-conformance-v1.json",
              frozenset({"degC_zero_at_273.15000000000003_K"})),
    "EV-15": ("validation/e0-current-rhs-references-20260912.json",
              frozenset({"degC_zero_at_273.15000000000003_K"})),
    "EV-16": ("Simulator/wksim_core/px4_mavlink.py", frozenset({"NED"})),
    "EV-17": ("Simulator/wksim_core/gnss_event.py", frozenset({"NED", "lat_lon_deg"})),
    "EV-18": ("Simulator/ue55/README.md", frozenset()),
}

# evidence id -> (locator, quote).  The payload's own locator/quote pair is
# frozen here and is then resolved against the committed HEAD bytes, so a
# fabricated or drifting citation fails closed.
EXPECTED_EVIDENCE_PROVENANCE = {
    "EV-1": ("line 52", "位置/速度为 NED"),
    "EV-2": ("line 52", "角速度和比力为 FRD"),
    "EV-3": ("line 10", 'position_frame="NED"'),
    "EV-4": ("line 11", 'body_frame="FRD"'),
    "EV-5": ("line 110", "coordinates NED / FRD"),
    "EV-6": ("line 33", '"m; NED"'),
    "EV-7": ("line 37", '"degree; latitude,longitude"'),
    "EV-8": ("line 105", "Ve，m/s，NED"),
    "EV-9": ("line 106", "Xe，m，NED"),
    "EV-10": ("line 110", "机体系运动加速度"),
    "EV-11": ("line 111", "wb，rad/s，机体系"),
    "EV-12": ("line 88", "ModelInit_PosE=[0,0,-10] m"),
    "EV-13": ("observables[]", "1e-7 degree per native unit"),
    "EV-14": ("observables[]", "cpp:7625-7626 subtract 273.15000000000003"),
    "EV-15": ("slots[Sensor30[13]].rhs.text", "273.15000000000003"),
    "EV-16": ("line 31", "derive COG from the already-scaled NED velocity"),
    "EV-17": ("line 64",
              "# time, fix, lat, lon, alt, eph, epv, vel, vn, ve, vd, cog, satellites"),
    "EV-18": ("line 37", "FRD机体到NED姿态"),
}

# (vocabulary, token) -> exact frozen committed_text entries.  The payload may
# not widen, drop, reorder or substitute any provenance row.
EXPECTED_VOCABULARY_TEXT = {
    ("frame_vocabulary", "FRD"): (
        "Simulator/wksim_core/README.md:52 角速度和比力为 FRD",
        'Simulator/wksim_core/state_stream.py:11 body_frame="FRD"',
        "Simulator/wksim_core/model.py:110 coordinates NED / FRD",
        "docs/plan/2026-09-08-numerical-contract-readiness.md:110 机体系运动加速度",
        "docs/plan/2026-09-08-numerical-contract-readiness.md:111 wb，rad/s，机体系",
    ),
    ("frame_vocabulary", "NED"): (
        "Simulator/wksim_core/README.md:52 位置/速度为 NED",
        'Simulator/wksim_core/state_stream.py:10 position_frame="NED"',
        "Simulator/wksim_core/model.py:110 coordinates NED / FRD",
        'Simulator/wksim_core/model_parameters.py:33 "m; NED"',
        "docs/plan/2026-09-08-numerical-contract-readiness.md:105 Ve，m/s，NED",
        "docs/plan/2026-09-08-numerical-contract-readiness.md:106 Xe，m，NED",
    ),
    ("frame_vocabulary", "lat_lon_deg"): (
        'Simulator/wksim_core/model_parameters.py:37 "degree; latitude,longitude"',
        "Simulator/wksim_core/numerical-conformance-v1.json:observables[]"
        " 1e-7 degree per native unit",
        "Simulator/wksim_core/gnss_event.py:64 lat, lon",
    ),
    ("datum_vocabulary", "degC_zero_at_273.15000000000003_K"): (
        "Simulator/wksim_core/numerical-conformance-v1.json:observables[]"
        " cpp:7625-7626 subtract 273.15000000000003",
        "validation/e0-current-rhs-references-20260912.json:"
        "slots[Sensor30[13]].rhs.text 273.15000000000003",
    ),
    ("datum_vocabulary", "model_local_NED_frame_reference"): (
        'Simulator/wksim_core/model_parameters.py:33 "m; NED"',
        "docs/plan/2026-09-08-numerical-contract-readiness.md:88 ModelInit_PosE=[0,0,-10] m",
    ),
}

ALLOWED_EVIDENCE_REF_FIELDS = frozenset({"path", "locator", "quote", "supports"})
ALLOWED_VOCABULARY_FIELDS = frozenset({"meaning", "committed_text", "does_not_claim"})
EXPECTED_COUNT_KEYS = (
    "slots_total",
    "frame_bound",
    "frame_unresolved",
    "datum_bound",
    "datum_unresolved",
    "owner_decision_count",
)

_TIME_SLOTS = ("Vehicle60[2]", "Sensor30[0]", "GPS30[0]")
_LL_SLOTS = ("Vehicle60[30]", "Vehicle60[31]", "GPS30[1]", "GPS30[2]")
_ALT_SLOTS = ("Vehicle60[32]", "Sensor30[12]", "GPS30[3]")
_MAG_SLOTS = ("Sensor30[7]", "Sensor30[8]", "Sensor30[9]")
_PRESSURE_SLOTS = ("Sensor30[10]", "Sensor30[11]")
_EPH_SLOTS = ("GPS30[4]", "GPS30[5]")
_QUAT_SLOTS = ("Vehicle60[12]", "Vehicle60[13]", "Vehicle60[14]", "Vehicle60[15]")
_EULER_SLOTS = ("Vehicle60[9]", "Vehicle60[10]", "Vehicle60[11]")
_IMU_SLOTS = ("Sensor30[1]", "Sensor30[2]", "Sensor30[3]",
              "Sensor30[4]", "Sensor30[5]", "Sensor30[6]")
_MOTOR_SLOTS = ("Vehicle60[16]", "Vehicle60[17]", "Vehicle60[18]", "Vehicle60[19]",
                "Vehicle60[20]", "Vehicle60[21]", "Vehicle60[22]", "Vehicle60[23]")
_EXTRA_MOTOR_SLOTS = ("Vehicle60[20]", "Vehicle60[21]", "Vehicle60[22]", "Vehicle60[23]")
_ABB_SLOTS = ("Vehicle60[24]", "Vehicle60[25]", "Vehicle60[26]")
_PQR_SLOTS = ("Vehicle60[27]", "Vehicle60[28]", "Vehicle60[29]")

EXPECTED_DECISIONS = {
    "OD-01": ("time_field_scope", _TIME_SLOTS),
    "OD-02": ("time_field_epoch", _TIME_SLOTS),
    "OD-03": ("lat_lon_horizontal_datum", _LL_SLOTS),
    "OD-04": ("altitude_axis_sign", _ALT_SLOTS),
    "OD-05": ("altitude_height_datum", _ALT_SLOTS),
    "OD-06": ("magnetic_field_frame", _MAG_SLOTS),
    "OD-07": ("magnetic_field_reference", _MAG_SLOTS),
    "OD-08": ("pressure_frame", _PRESSURE_SLOTS),
    "OD-09": ("pressure_datum", _PRESSURE_SLOTS),
    "OD-10": ("temperature_frame_and_domain", ("Sensor30[13]",)),
    "OD-11": ("accuracy_indicator_frame", _EPH_SLOTS),
    "OD-12": ("accuracy_indicator_semantics", _EPH_SLOTS),
    "OD-13": ("course_reference_frame", ("GPS30[10]",)),
    "OD-14": ("course_wrap_convention", ("GPS30[10]",)),
    "OD-15": ("quaternion_direction_and_metric", _QUAT_SLOTS),
    "OD-16": ("euler_frame_sequence_and_order", _EULER_SLOTS),
    "OD-17": ("imu_mounting_extrinsics", _IMU_SLOTS),
    "OD-18": ("imu_zero_reference", _IMU_SLOTS),
    "OD-19": ("rotor_speed_frame_and_reference", _MOTOR_SLOTS),
    "OD-20": ("inactive_channel_scope", _EXTRA_MOTOR_SLOTS),
    "OD-21": ("body_acceleration_reference", _ABB_SLOTS),
    "OD-22": ("ned_earth_model", ("Vehicle60[3]", "Vehicle60[4]", "Vehicle60[5]",
                                  "Vehicle60[6]", "Vehicle60[7]", "Vehicle60[8]",
                                  "GPS30[7]", "GPS30[8]", "GPS30[9]")),
    "OD-23": ("horizontal_speed_frame", ("GPS30[6]",)),
    "OD-24": ("angular_rate_zero_reference", _PQR_SLOTS),
}


def _git(*args):
    result = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def _git_bytes(*args):
    result = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True)
    return result.returncode, result.stdout


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def head_bytes(path):
    """Committed bytes of *path* at HEAD, or None when it is not at HEAD."""
    code, out = _git_bytes("show", "HEAD:" + path)
    return out if code == 0 else None


def pinned_rhs_identities(entry):
    """Complete pinned RHS identities for one slot: full text plus name/path."""
    identities = set()
    if not isinstance(entry, dict):
        return identities
    text = (entry.get("rhs") or {}).get("text")
    if isinstance(text, str) and text:
        identities.add(text)
    for reference in entry.get("references") or []:
        if not isinstance(reference, dict):
            continue
        for field in ("name", "path"):
            value = reference.get(field)
            if isinstance(value, str) and value:
                identities.add(value)
    return identities


def rhs_symbol_present(rhs_document, slot_key, symbol):
    """True when *symbol* is a complete pinned RHS identity for *slot_key*."""
    if not isinstance(symbol, str) or not symbol:
        return False
    for entry in rhs_document.get("slots", []):
        if entry.get("slot") != slot_key:
            continue
        return symbol in pinned_rhs_identities(entry)
    return False


def manifest_phase(manifest_document, slot_key):
    """Committed ``sample_phase`` for *slot_key*, or None when it is absent."""
    for entry in manifest_document.get("slots", []):
        if entry.get("slot") == slot_key:
            return entry.get("sample_phase")
    return None


def read_json_at_head(path):
    data = head_bytes(path)
    if data is None:
        raise AssertionError("%s is not tracked at committed HEAD" % path)
    return json.loads(data.decode("utf-8"))


def _no_duplicate_keys(pairs):
    """``object_pairs_hook`` that refuses a repeated JSON object key.

    ``json.loads`` silently keeps the last value, so a duplicate pin id (or a
    duplicate slot/decision/evidence entry) would otherwise be swallowed and
    could be used to hide a substituted entry behind an identical key.
    """
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate JSON key %r" % key)
        seen[key] = value
    return seen


def loads_no_duplicate_keys(text):
    return json.loads(text, object_pairs_hook=_no_duplicate_keys)


def head_text(path):
    """Committed HEAD blob of *path* decoded as text, or None."""
    blob = head_bytes(path)
    return None if blob is None else blob.decode("utf-8", "replace")


def locator_line(locator):
    """``"line 52"`` -> 52; any other locator -> None."""
    match = re.search(r"\bline\s+(\d+)\b", locator or "")
    return int(match.group(1)) if match else None


def split_slot_locator(locator):
    """``"slots[<key>].<dotted>"`` -> (key, dotted) where <key> may nest [ ]."""
    if not (locator or "").startswith("slots["):
        return None
    rest = locator[len("slots"):]
    depth = 0
    for position, char in enumerate(rest):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return rest[1:position], rest[position + 1:].lstrip(".")
    return None


def json_slot_value(document, locator):
    """Resolve a ``slots[<key>].<dotted>`` locator inside a parsed JSON doc."""
    parsed = split_slot_locator(locator)
    if parsed is None:
        return None, "not_a_slot_locator"
    key, dotted = parsed
    entry = None
    for item in document.get("slots", []):
        if item.get("slot") == key:
            entry = item
            break
    if entry is None:
        return None, "slot_not_found"
    node = entry
    for part in (dotted.split(".") if dotted else []):
        if not part:
            continue
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None, "path_not_found:%s" % part
    return (node if isinstance(node, str) else json.dumps(node, ensure_ascii=False)), None


def json_observables_field_match(document, quote):
    """Return None when *quote* equals a string field of some ``observables[]`` element."""
    items = document.get("observables")
    if not isinstance(items, list):
        return "observables_not_an_array"
    for item in items:
        if not isinstance(item, dict):
            continue
        for value in item.values():
            if isinstance(value, str) and value == quote:
                return None
    return "quote_not_exact_observables_field"


def verify_quote_against_head(path, locator, quote):
    """Return an error code when *quote* is not committed at *locator*, else None."""
    text = head_text(path)
    if text is None:
        return "path_not_tracked_at_head"
    if not quote:
        return "empty_quote"
    if quote not in text:
        return "quote_absent_from_committed_head_blob"
    line = locator_line(locator)
    if line is not None:
        lines = text.splitlines()
        if not (1 <= line <= len(lines)):
            return "cited_line_out_of_range"
        if quote not in lines[line - 1]:
            return "quote_not_on_cited_line"
        return None
    if split_slot_locator(locator) is not None and path.endswith(".json"):
        try:
            document = json.loads(text)
        except ValueError:
            return "pinned_json_unparsable"
        value, problem = json_slot_value(document, locator)
        if problem is not None:
            return "json_locator_%s" % problem
        if quote not in value:
            return "quote_not_in_json_locator_value"
        return None
    if locator == "observables[]" and path.endswith(".json"):
        try:
            document = json.loads(text)
        except ValueError:
            return "pinned_json_unparsable"
        return json_observables_field_match(document, quote)
    return None


def verify_committed_text_entry(entry):
    """Split ``path:locator fragment`` and verify the fragment at HEAD."""
    if not isinstance(entry, str):
        return "committed_text_entry_must_be_a_string"
    path, separator, rest = entry.partition(":")
    if not separator or not rest:
        return "committed_text_entry_not_path_locator_fragment"
    locator, _, fragment = rest.partition(" ")
    locator, fragment = locator.strip(), fragment.strip()
    if not fragment:
        return "committed_text_entry_has_empty_fragment"
    if locator.isdigit():
        text = head_text(path)
        if text is None:
            return "committed_text_path_not_tracked_at_head"
        lines = text.splitlines()
        number = int(locator)
        if not (1 <= number <= len(lines)):
            return "committed_text_line_out_of_range"
        if fragment not in lines[number - 1]:
            return "committed_text_fragment_not_on_cited_line"
        return None
    return verify_quote_against_head(path, locator, fragment)


def expected_slot_sets():
    """Return (dynamic, excluded) key sets derived from the frozen contract."""
    contract = read_json_at_head(CONTRACT_REL)
    if contract.get("contract_id") != FROZEN_CONTRACT_ID:
        raise AssertionError("frozen contract id differs")
    dynamic, excluded = set(), set()
    for observable in contract["observables"]:
        status = observable.get("semantic_status")
        for index in observable["indices"]:
            (excluded if status in EXCLUDED_STATUS else dynamic).add(
                "%s[%d]" % (observable["array"], index))
    return dynamic, excluded


def _walk_forbidden(value, path, errors):
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if FORBIDDEN_KEY_RE.search(lowered) and lowered not in ALLOWED_FLAG_KEYS:
                errors.append("%s.%s: forbidden budget/approval field" % (path, key))
            _walk_forbidden(child, "%s.%s" % (path, key), errors)
    elif isinstance(value, list):
        for position, child in enumerate(value):
            _walk_forbidden(child, "%s[%d]" % (path, position), errors)


def _validate_pins(payload, errors):
    pins = payload.get("pins")
    if not isinstance(pins, dict):
        errors.append("pins must be an object")
        return
    for pin_id in sorted(EXPECTED_PINS):
        if pin_id not in pins:
            errors.append("pins: missing pin %s" % pin_id)
    for pin_id in sorted(pins):
        if pin_id not in EXPECTED_PINS:
            errors.append("pins: extra pin %s" % pin_id)
    for pin_id, pin in sorted(pins.items()):
        prefix = "pins.%s" % pin_id
        if not isinstance(pin, dict):
            errors.append("%s: must be an object" % prefix)
            continue
        expected_path = EXPECTED_PINS.get(pin_id)
        path = pin.get("path")
        if path != expected_path:
            errors.append("%s: wrong_pin_path %r, expected %r" % (prefix, path, expected_path))
            continue
        digest = pin.get("sha256")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            errors.append("%s.sha256: must be lowercase SHA-256" % prefix)
        code, listing = _git("ls-tree", "HEAD", "--", path)
        if code != 0 or not listing:
            errors.append("%s: pin_not_at_head %s" % (prefix, path))
            continue
        blob = head_bytes(path)
        if blob is None:
            errors.append("%s: pin_not_at_head %s" % (prefix, path))
            continue
        if sha256_bytes(blob) != digest:
            errors.append("%s: pin_digest_differs_from_head_blob" % prefix)
        _, drift = _git("diff", "--name-only", "HEAD", "--", path)
        if drift:
            errors.append("%s: pin_worktree_drift %s" % (prefix, drift))

    policy = payload.get("evidence_policy")
    if not isinstance(policy, dict):
        errors.append("evidence_policy must be an object")
        return
    declared = policy.get("require_tracked_at_head")
    if not isinstance(declared, list):
        errors.append("evidence_policy.require_tracked_at_head must be a list")
        return
    if len(set(declared)) != len(declared):
        errors.append("evidence_policy.require_tracked_at_head has duplicates")
    if sorted(declared) != sorted(EXPECTED_PINS):
        errors.append(
            "evidence_policy.require_tracked_at_head mismatch: missing=%s extra=%s"
            % (sorted(set(EXPECTED_PINS) - set(declared)),
               sorted(set(declared) - set(EXPECTED_PINS)))
        )


def _validate_vocabularies(payload, errors):
    frames = payload.get("frame_vocabulary")
    datums = payload.get("datum_vocabulary")
    if not isinstance(frames, dict):
        errors.append("frame_vocabulary must be an object")
        frames = {}
    if not isinstance(datums, dict):
        errors.append("datum_vocabulary must be an object")
        datums = {}
    if set(frames) != FRAME_TOKENS:
        errors.append("frame_vocabulary keys differ from the frozen token set: %s"
                      % sorted(set(frames) ^ FRAME_TOKENS))
    if set(datums) != DATUM_TOKENS:
        errors.append("datum_vocabulary keys differ from the frozen token set: %s"
                      % sorted(set(datums) ^ DATUM_TOKENS))
    for kind, vocabulary in (("frame_vocabulary", frames), ("datum_vocabulary", datums)):
        for token, definition in sorted(vocabulary.items()):
            prefix = "%s.%s" % (kind, token)
            if not isinstance(definition, dict):
                errors.append("%s must be an object" % prefix)
                continue
            if not definition.get("committed_text"):
                errors.append("%s must carry committed_text" % prefix)
            if not definition.get("meaning"):
                errors.append("%s must carry a meaning" % prefix)
            unknown = set(definition) - ALLOWED_VOCABULARY_FIELDS
            if unknown:
                errors.append("%s: unknown fields %s" % (prefix, sorted(unknown)))
            entries = definition.get("committed_text")
            frozen = EXPECTED_VOCABULARY_TEXT.get((kind, token))
            if frozen is None:
                continue
            if not isinstance(entries, list) or list(entries) != list(frozen):
                errors.append("%s: committed_text differs from the frozen provenance"
                              % prefix)
                continue
            for entry in entries:
                problem = verify_committed_text_entry(entry)
                if problem is not None:
                    errors.append("%s: committed_text %r: %s" % (prefix, entry, problem))


def _validate_evidence_provenance(refs, errors):
    """Resolve each frozen locator/quote pair against committed HEAD bytes."""
    for ref_id in sorted(EXPECTED_EVIDENCE):
        ref = refs.get(ref_id)
        expected = EXPECTED_EVIDENCE_PROVENANCE.get(ref_id)
        if not isinstance(ref, dict) or expected is None:
            continue
        prefix = "evidence_refs.%s" % ref_id
        locator, quote = expected
        if ref.get("locator") != locator:
            errors.append("%s: locator differs from the frozen provenance" % prefix)
        if ref.get("quote") != quote:
            errors.append("%s: quote differs from the frozen provenance" % prefix)
        problem = verify_quote_against_head(EXPECTED_EVIDENCE[ref_id][0], locator, quote)
        if problem is not None:
            errors.append("%s: provenance not committed at HEAD: %s" % (prefix, problem))
        # Resolve the payload's own pair too, so a tampered locator or quote is
        # caught as a byte-level failure and not only as a table mismatch.
        declared = verify_quote_against_head(EXPECTED_EVIDENCE[ref_id][0],
                                             ref.get("locator"), ref.get("quote"))
        if declared is not None:
            errors.append("%s: declared citation not committed at HEAD: %s"
                          % (prefix, declared))


def _validate_evidence_refs(payload, errors):
    refs = payload.get("evidence_refs")
    if not isinstance(refs, dict):
        errors.append("evidence_refs must be an object")
        return {}
    for ref_id in sorted(EXPECTED_EVIDENCE):
        if ref_id not in refs:
            errors.append("evidence_refs: missing %s" % ref_id)
    for ref_id in sorted(refs):
        if ref_id not in EXPECTED_EVIDENCE:
            errors.append("evidence_refs: unknown evidence id %s" % ref_id)
    for ref_id, ref in sorted(refs.items()):
        expected = EXPECTED_EVIDENCE.get(ref_id)
        if expected is None or not isinstance(ref, dict):
            continue
        prefix = "evidence_refs.%s" % ref_id
        unknown = set(ref) - ALLOWED_EVIDENCE_REF_FIELDS
        if unknown:
            errors.append("%s: unknown fields %s" % (prefix, sorted(unknown)))
        if ref.get("path") != expected[0]:
            errors.append("%s: path differs from the frozen identity" % prefix)
        supports = ref.get("supports")
        if not isinstance(supports, list) or set(supports) != expected[1]:
            errors.append("%s: supports differs from the frozen identity" % prefix)
        if head_bytes(expected[0]) is None:
            errors.append("%s: %s is not tracked at HEAD" % (prefix, expected[0]))
    _validate_evidence_provenance(refs, errors)
    return refs


def _validate_field(slot_id, name, field, vocabulary, evidence_refs, decisions, errors):
    prefix = "slots[%s].%s" % (slot_id, name)
    if not isinstance(field, dict):
        errors.append("%s: must be an object" % prefix)
        return
    allowed = {"value", "status", "evidence", "reason", "owner_decision", "note"}
    required = {"value", "status", "evidence", "reason", "owner_decision"}
    missing = required - set(field)
    if missing:
        errors.append("%s: missing fields %s" % (prefix, sorted(missing)))
    if set(field) - allowed:
        errors.append("%s: unknown fields %s" % (prefix, sorted(set(field) - allowed)))
    value = field.get("value")
    status = field.get("status")
    if value is None:
        if status != "unresolved_owner_decision":
            errors.append("%s: null value requires status='unresolved_owner_decision'" % prefix)
        if field.get("evidence"):
            errors.append("%s: null value must not cite binding evidence" % prefix)
        reason = field.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 40:
            errors.append("%s: null value requires a precise owner-decision reason" % prefix)
        owner = field.get("owner_decision")
        if owner is None:
            errors.append("%s: null value requires an owner_decision id" % prefix)
        elif owner not in decisions:
            errors.append("%s: unknown owner_decision %r" % (prefix, owner))
        elif decisions[owner].get("state") != "not_made":
            errors.append("%s: owner_decision %s is no longer 'not_made'" % (prefix, owner))
        elif slot_id not in decisions[owner].get("slots", []):
            errors.append("%s: owner_decision %s does not list this slot" % (prefix, owner))
        return
    if status != "bound":
        errors.append("%s: bound value requires status='bound'" % prefix)
    if value not in vocabulary:
        errors.append("%s: forged or unknown %s value %r" % (prefix, name, value))
    if field.get("owner_decision") is not None:
        errors.append("%s: bound value must not carry an owner_decision" % prefix)
    evidence = field.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("%s: bound value requires at least one evidence id" % prefix)
        return
    for ref_id in evidence:
        if ref_id not in evidence_refs:
            errors.append("%s: unknown evidence id %r" % (prefix, ref_id))
            continue
        supports = evidence_refs[ref_id].get("supports")
        if not isinstance(supports, list) or value not in supports:
            errors.append("%s: evidence %s does not support %r" % (prefix, ref_id, value))


def _validate_counts(payload, slots, errors):
    """Recompute every declared ``counts`` key from the actual payload structure."""
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts must be an object")
        return
    frame_bound = frame_unresolved = datum_bound = datum_unresolved = 0
    slot_items = slots if isinstance(slots, list) else []
    for slot in slot_items:
        if not isinstance(slot, dict):
            continue
        frame = slot.get("frame") if isinstance(slot.get("frame"), dict) else {}
        datum = slot.get("datum") if isinstance(slot.get("datum"), dict) else {}
        if frame.get("value") is not None:
            frame_bound += 1
        else:
            frame_unresolved += 1
        if datum.get("value") is not None:
            datum_bound += 1
        else:
            datum_unresolved += 1
    owner_decisions = payload.get("owner_decisions")
    owner_count = len(owner_decisions) if isinstance(owner_decisions, list) else 0
    expected = {
        "slots_total": len(slot_items),
        "frame_bound": frame_bound,
        "frame_unresolved": frame_unresolved,
        "datum_bound": datum_bound,
        "datum_unresolved": datum_unresolved,
        "owner_decision_count": owner_count,
    }
    for extra in sorted(set(counts) - set(expected)):
        errors.append("counts: unknown key %s" % extra)
    for missing in sorted(set(expected) - set(counts)):
        errors.append("counts: missing key %s" % missing)
    for key in EXPECTED_COUNT_KEYS:
        if key in counts and counts.get(key) != expected[key]:
            errors.append("counts.%s is %r, recomputed %r"
                          % (key, counts.get(key), expected[key]))


def validate_binding(payload, check_pins=True, manifest=None):
    """Return a list of validation errors; an empty list means valid.

    *manifest* defaults to the committed HEAD slot manifest.  Tests may inject
    a temporary copy so the live missing-slot branch is exercised without
    mutating HEAD.
    """
    errors = []
    contract = read_json_at_head(CONTRACT_REL)
    if manifest is None:
        manifest = read_json_at_head(MANIFEST_REL)
    elif not isinstance(manifest, dict):
        errors.append("injected manifest must be an object")
        manifest = {}
    rhs_document = read_json_at_head(RHS_REL)
    dynamic_expected, excluded_expected = expected_slot_sets()
    if len(dynamic_expected) != DYNAMIC_SLOTS:
        errors.append("contract dynamic slot count is %d, expected %d"
                      % (len(dynamic_expected), DYNAMIC_SLOTS))
    if len(excluded_expected) != EXCLUDED_SLOTS:
        errors.append("contract excluded slot count is %d, expected %d"
                      % (len(excluded_expected), EXCLUDED_SLOTS))
    if len(dynamic_expected) + len(excluded_expected) != TOTAL_SLOTS:
        errors.append("contract slot total is not %d" % TOTAL_SLOTS)

    for flag in ("budget_approved", "g6_acceptance", "physical_accuracy", "issues_closed",
                 "effective"):
        if payload.get(flag) is not False:
            errors.append("acceptance flip: %s must be false" % flag)
    if payload.get("r1_status") != "numerical_failed":
        errors.append("acceptance flip: r1_status must stay 'numerical_failed'")
    _walk_forbidden(payload, "$", errors)

    if check_pins:
        _validate_pins(payload, errors)
    _validate_vocabularies(payload, errors)
    evidence_refs = _validate_evidence_refs(payload, errors)

    slot_set = payload.get("slot_set")
    if not isinstance(slot_set, dict):
        errors.append("slot_set must be an object")
        slot_set = {}
    for key, expected in (("total_slots", TOTAL_SLOTS), ("dynamic_slots", DYNAMIC_SLOTS),
                          ("excluded_slots", EXCLUDED_SLOTS),
                          ("semantic_dynamic_slots", SEMANTIC_DYNAMIC),
                          ("time_field_slots", TIME_FIELDS)):
        if slot_set.get(key) != expected:
            errors.append("slot_set.%s must be %s" % (key, expected))
    excluded_list = slot_set.get("excluded_slot_list")
    if not isinstance(excluded_list, list) or set(excluded_list) != excluded_expected:
        errors.append("slot_set.excluded_slot_list does not match the committed 64-slot set")
    elif len(excluded_list) != len(set(excluded_list)):
        errors.append("slot_set.excluded_slot_list contains duplicates")

    decisions = {}
    owner_decisions = payload.get("owner_decisions")
    if not isinstance(owner_decisions, list) or not owner_decisions:
        errors.append("owner_decisions must be a non-empty list")
        owner_decisions = []
    for decision in owner_decisions:
        if not isinstance(decision, dict) or not isinstance(decision.get("id"), str):
            errors.append("owner_decisions entry must carry a string id")
            continue
        ident = decision["id"]
        if ident in decisions:
            errors.append("owner_decisions: duplicate id %s" % ident)
        if decision.get("state") != "not_made":
            errors.append("owner_decisions.%s: must stay 'not_made'" % ident)
        if decision.get("chosen_option") is not None or decision.get("made_by") is not None:
            errors.append("owner_decisions.%s: must not record a decision" % ident)
        if not isinstance(decision.get("question"), str) or len(decision["question"]) < 20:
            errors.append("owner_decisions.%s: question must be precise" % ident)
        expected = EXPECTED_DECISIONS.get(ident)
        if expected is None:
            errors.append("owner_decisions.%s: unknown owner decision" % ident)
        else:
            if decision.get("topic") != expected[0]:
                errors.append("owner_decisions.%s: topic differs from the frozen identity" % ident)
            listed = decision.get("slots")
            if not isinstance(listed, list) or sorted(listed) != sorted(expected[1]):
                errors.append("owner_decisions.%s: slots differ from the frozen identity" % ident)
        decisions[ident] = decision
    if sorted(decisions) != sorted(EXPECTED_DECISIONS):
        errors.append("owner_decisions ids differ from the frozen set: %s"
                      % sorted(set(decisions) ^ set(EXPECTED_DECISIONS)))
    if payload.get("unresolved_owner_decisions") != sorted(EXPECTED_DECISIONS):
        errors.append("unresolved_owner_decisions must list every frozen owner decision id")

    contract_by_key = {}
    for observable in contract["observables"]:
        for index in observable["indices"]:
            contract_by_key["%s[%d]" % (observable["array"], index)] = observable

    if payload.get("slot_count") != DYNAMIC_SLOTS:
        errors.append("slot_count must be %d" % DYNAMIC_SLOTS)
    slots = payload.get("slots")
    if not isinstance(slots, list) or len(slots) != DYNAMIC_SLOTS:
        errors.append("slots must contain exactly %d items" % DYNAMIC_SLOTS)
        slots = slots if isinstance(slots, list) else []
    seen = set()
    for position, slot in enumerate(slots):
        prefix = "slots[%d]" % position
        if not isinstance(slot, dict):
            errors.append("%s: must be an object" % prefix)
            continue
        missing = REQUIRED_SLOT_FIELDS - set(slot)
        if missing:
            errors.append("%s: missing fields %s" % (prefix, sorted(missing)))
        if set(slot) - REQUIRED_SLOT_FIELDS:
            errors.append("%s: unknown fields %s"
                          % (prefix, sorted(set(slot) - REQUIRED_SLOT_FIELDS)))
        array, index = slot.get("array"), slot.get("index")
        if not isinstance(array, str) or type(index) is not int:
            errors.append("%s: array/index must be a string and an int" % prefix)
            continue
        key = slot.get("slot")
        if key != "%s[%d]" % (array, index):
            errors.append("%s: slot string does not match array/index" % prefix)
            continue
        if key in seen:
            errors.append("%s: duplicate slot %s" % (prefix, key))
        seen.add(key)
        if key not in dynamic_expected:
            errors.append("%s: %s is not a committed dynamic slot" % (prefix, key))
            continue
        observable = contract_by_key[key]
        if slot.get("observable") != observable["id"]:
            errors.append("%s: observable does not own %s" % (prefix, key))
        if slot.get("native_unit") != observable.get("native_unit"):
            errors.append("%s: native_unit differs from the frozen contract" % prefix)
        if slot.get("contract_semantic_status") != observable.get("semantic_status"):
            errors.append("%s: contract_semantic_status differs from the frozen contract" % prefix)
        if slot.get("source_label") != observable.get("source"):
            errors.append("%s: source_label differs from the frozen contract" % prefix)
        manifest_phase_value = manifest_phase(manifest, key)
        if manifest_phase_value is None:
            errors.append("%s: %s is missing from the committed slot manifest" % (prefix, key))
        elif slot.get("sample_phase") != manifest_phase_value:
            errors.append("%s: sample_phase differs from the committed manifest" % prefix)
        if not rhs_symbol_present(rhs_document, key, slot.get("current_generated_rhs")):
            errors.append("%s: current_generated_rhs %r is not a complete pinned RHS symbol identity"
                          % (prefix, slot.get("current_generated_rhs")))

        frame = slot.get("frame") if isinstance(slot.get("frame"), dict) else {}
        datum = slot.get("datum") if isinstance(slot.get("datum"), dict) else {}
        expected = EXPECTED_BINDINGS.get(observable["id"])
        if expected is None:
            errors.append("%s: no frozen binding for observable %s" % (prefix, observable["id"]))
        else:
            open_decisions = slot.get("open_owner_decisions")
            actual = (frame.get("value"), frame.get("owner_decision"),
                      datum.get("value"), datum.get("owner_decision"),
                      tuple(open_decisions) if isinstance(open_decisions, list) else None)
            if actual != expected:
                errors.append("%s: frozen_binding_mismatch actual=%r expected=%r"
                              % (prefix, actual, expected))

        _validate_field(key, "frame", slot.get("frame"), FRAME_TOKENS, evidence_refs,
                        decisions, errors)
        _validate_field(key, "datum", slot.get("datum"), DATUM_TOKENS, evidence_refs,
                        decisions, errors)

        open_decisions = slot.get("open_owner_decisions")
        if not isinstance(open_decisions, list) or not all(
            isinstance(item, str) for item in open_decisions
        ):
            errors.append("%s.open_owner_decisions: must be a string list" % prefix)
            open_decisions = []
        for ident in open_decisions:
            if ident not in decisions:
                errors.append("%s.open_owner_decisions: unknown id %r" % (prefix, ident))
        if len(set(open_decisions)) != len(open_decisions):
            errors.append("%s.open_owner_decisions: duplicates" % prefix)

        unresolved = frame.get("value") is None or datum.get("value") is None
        status = slot.get("binding_status")
        if status not in ALLOWED_BINDING_STATUS:
            errors.append("%s.binding_status: %r is not allowed" % (prefix, status))
        elif unresolved and status != "unresolved_owner_decision":
            errors.append(
                "%s.binding_status: unresolved fields require 'unresolved_owner_decision'" % prefix)
        elif not unresolved and status == "unresolved_owner_decision":
            errors.append(
                "%s.binding_status: bound fields must not be 'unresolved_owner_decision'" % prefix)
        elif not unresolved and open_decisions and status != "bound_but_owner_items_open":
            errors.append(
                "%s.binding_status: open owner items require 'bound_but_owner_items_open'" % prefix)
        elif not unresolved and not open_decisions and status != "bound":
            errors.append("%s.binding_status: fully bound slot must be 'bound'" % prefix)

    if seen != dynamic_expected:
        errors.append(
            "slot coverage differs from the committed set: missing=%s extra=%s"
            % (sorted(dynamic_expected - seen), sorted(seen - dynamic_expected))
        )

    time_list = slot_set.get("time_slot_list") or []
    semantic_list = slot_set.get("semantic_slot_list") or []
    if len(time_list) != TIME_FIELDS:
        errors.append("slot_set.time_slot_list must list %d slots" % TIME_FIELDS)
    if len(semantic_list) != SEMANTIC_DYNAMIC:
        errors.append("slot_set.semantic_slot_list must list %d slots" % SEMANTIC_DYNAMIC)
    if set(time_list) | set(semantic_list) != dynamic_expected:
        errors.append("time and semantic slot lists must partition the 56 dynamic slots")
    if set(time_list) & set(semantic_list):
        errors.append("time and semantic slot lists must not overlap")
    for key in time_list:
        if contract_by_key.get(key, {}).get("semantic_status") != "schedule_metadata":
            errors.append("slot_set.time_slot_list: %s is not schedule_metadata" % key)

    # Owner-decision coverage must hold in both directions: every frozen
    # decision is referenced by at least one slot, and every slot a decision
    # lists really references that decision.  A decision that no slot points at
    # would otherwise be an unaccounted "approval-shaped" entry.
    referenced = {ident: set() for ident in decisions}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        key = slot.get("slot")
        for field_name in ("frame", "datum"):
            field = slot.get(field_name)
            if isinstance(field, dict) and field.get("owner_decision"):
                referenced.setdefault(field["owner_decision"], set()).add(key)
        for ident in slot.get("open_owner_decisions") or []:
            referenced.setdefault(ident, set()).add(key)
    for ident, decision in sorted(decisions.items()):
        users = referenced.get(ident, set())
        if not users:
            errors.append("owner_decisions.%s: no slot references this decision" % ident)
        unbacked = sorted(set(decision.get("slots") or []) - users)
        if unbacked:
            errors.append("owner_decisions.%s: slots listed but not referencing it: %s"
                          % (ident, unbacked))
    _validate_counts(payload, slots, errors)
    return errors


def load_binding():
    return loads_no_duplicate_keys(BINDING_PATH.read_text(encoding="utf-8"))


class FrameDatumBindingTest(unittest.TestCase):
    def setUp(self):
        self.payload = load_binding()

    # --- positive ---------------------------------------------------------
    def test_committed_file_is_valid(self):
        self.assertEqual(validate_binding(self.payload), [])

    def test_head_and_baseline(self):
        recorded = self.payload["observed_at"]["head"]
        code, head = _git("rev-parse", "HEAD")
        self.assertEqual(code, 0)
        self.assertTrue(GIT_SHA1.fullmatch(recorded or ""), "recorded HEAD must be a full git sha")
        self.assertTrue(GIT_SHA1.fullmatch(self.payload["observed_at"]["baseline_ancestor"] or ""),
                        "recorded baseline ancestor must be a full git sha")
        recorded_code, _ = _git("merge-base", "--is-ancestor", recorded, "HEAD")
        self.assertEqual(recorded_code, 0,
                         "recorded dispatch HEAD %s is not an ancestor of %s" % (recorded, head))
        ancestor_code, _ = _git("merge-base", "--is-ancestor", BASELINE_ANCESTOR, "HEAD")
        self.assertEqual(ancestor_code, 0, "baseline f333316 is not an ancestor of HEAD")
        blob = head_bytes(CONTRACT_REL)
        self.assertIsNotNone(blob, "contract missing at HEAD")
        self.assertEqual(sha256_bytes(blob), FROZEN_CONTRACT_SHA256)
        changed = _git("diff", "--name-only", recorded, "HEAD", "--",
                       *sorted(EXPECTED_PINS.values()))[1]
        self.assertEqual(changed, "", "a pinned input changed between %s and HEAD" % recorded)

    def test_slot_partition_is_56_of_120(self):
        dynamic, excluded = expected_slot_sets()
        self.assertEqual(len(dynamic), DYNAMIC_SLOTS)
        self.assertEqual(len(excluded), EXCLUDED_SLOTS)
        self.assertEqual(len(dynamic) + len(excluded), TOTAL_SLOTS)

    def test_every_dynamic_slot_is_covered(self):
        dynamic, _ = expected_slot_sets()
        self.assertEqual({slot["slot"] for slot in self.payload["slots"]}, dynamic)

    def test_counts_match_payload(self):
        counts = self.payload["counts"]
        self.assertEqual(counts["slots_total"], DYNAMIC_SLOTS)
        self.assertEqual(counts["frame_bound"] + counts["frame_unresolved"], DYNAMIC_SLOTS)
        self.assertEqual(counts["datum_bound"] + counts["datum_unresolved"], DYNAMIC_SLOTS)
        self.assertEqual(counts["frame_bound"],
                         sum(1 for s in self.payload["slots"] if s["frame"]["value"] is not None))
        self.assertEqual(counts["datum_bound"],
                         sum(1 for s in self.payload["slots"] if s["datum"]["value"] is not None))
        self.assertEqual(counts["owner_decision_count"], len(EXPECTED_DECISIONS))

    def test_no_inferred_direction_scalar_or_origin_binding(self):
        for slot in self.payload["slots"]:
            observable = slot["observable"]
            if observable in ("euler_components", "quaternion_components"):
                self.assertIsNone(slot["frame"]["value"], observable)
            if observable in ("active_motor_speed", "extra_motor_speed",
                              "gps_horizontal_speed"):
                self.assertIsNone(slot["frame"]["value"], observable)
                self.assertIsNone(slot["datum"]["value"], observable)
            if observable == "body_angular_rate":
                self.assertIsNone(slot["datum"]["value"], observable)
        self.assertNotIn("geodetic", FRAME_TOKENS)

    # --- slot-set mutations ----------------------------------------------
    def test_missing_slot_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["slots"].pop(7)
        payload["slot_count"] = len(payload["slots"])
        errors = validate_binding(payload)
        self.assertTrue(any("slot coverage differs" in item for item in errors))

    def test_duplicate_slot_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["slots"].append(copy.deepcopy(payload["slots"][5]))
        payload["slot_count"] = len(payload["slots"])
        errors = validate_binding(payload)
        self.assertTrue(any("duplicate slot" in item for item in errors))

    def test_extra_reserved_slot_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        extra = copy.deepcopy(payload["slots"][0])
        extra.update({"slot": "Vehicle60[33]", "array": "Vehicle60", "index": 33})
        payload["slots"].append(extra)
        payload["slot_count"] = len(payload["slots"])
        errors = validate_binding(payload)
        self.assertTrue(any("not a committed dynamic slot" in item for item in errors))

    # --- attack 1: delete a pin from pins and from the policy list --------
    def test_attack_delete_pin_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["pins"].pop("g6_frontier_review")
        payload["evidence_policy"]["require_tracked_at_head"] = [
            item for item in payload["evidence_policy"]["require_tracked_at_head"]
            if item != "g6_frontier_review"
        ]
        errors = validate_binding(payload)
        self.assertTrue(any("missing pin g6_frontier_review" in item for item in errors))
        self.assertTrue(any("require_tracked_at_head mismatch" in item for item in errors))

    def test_attack_delete_pin_only_from_pins_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["pins"].pop("g6_frontier_review")
        errors = validate_binding(payload)
        self.assertTrue(any("missing pin g6_frontier_review" in item for item in errors))

    # --- attack 2: substitute pin path + digest ---------------------------
    def test_attack_substitute_pin_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        declared = payload["pins"]["g6_frontier_review"]
        declared["path"] = EXPECTED_PINS["core_readme"]
        declared["sha256"] = sha256_bytes(head_bytes(EXPECTED_PINS["core_readme"]))
        errors = validate_binding(payload)
        self.assertTrue(any("wrong_pin_path" in item for item in errors))

    def test_attack_substitute_digest_only_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["pins"]["g6_frontier_review"]["sha256"] = sha256_bytes(
            head_bytes(EXPECTED_PINS["core_readme"]))
        errors = validate_binding(payload)
        self.assertTrue(any("pin_digest_differs_from_head_blob" in item for item in errors))

    # --- attack 3: forged vocabulary entry + forged slot value ------------
    def test_attack_forged_vocabulary_and_value_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["frame_vocabulary"]["ENU"] = {
            "meaning": "invented frame",
            "committed_text": ["nowhere:1 nothing"],
            "does_not_claim": "invented",
        }
        payload["evidence_refs"]["EV-1"]["supports"] = ["NED", "ENU"]
        for slot in payload["slots"]:
            if slot["observable"] == "velocity_ned":
                slot["frame"]["value"] = "ENU"
                slot["frame"]["evidence"] = ["EV-1"]
                break
        errors = validate_binding(payload)
        self.assertTrue(any("frame_vocabulary keys differ" in item for item in errors))
        self.assertTrue(any("forged or unknown frame value" in item for item in errors))
        self.assertTrue(any("supports differs from the frozen identity" in item for item in errors))
        self.assertTrue(any("frozen_binding_mismatch" in item for item in errors))

    # --- attack 4: evidence that does not support the value ---------------
    def test_attack_unsupporting_evidence_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        for slot in payload["slots"]:
            if slot["observable"] == "temperature":
                slot["datum"]["evidence"] = ["EV-1"]
                break
        errors = validate_binding(payload)
        self.assertTrue(any("evidence EV-1 does not support" in item for item in errors))

    def test_frame_evidence_support_is_also_checked(self):
        payload = copy.deepcopy(self.payload)
        for slot in payload["slots"]:
            if slot["observable"] == "accelerometer":
                slot["frame"]["evidence"] = ["EV-8"]
                break
        errors = validate_binding(payload)
        self.assertTrue(any("evidence EV-8 does not support" in item for item in errors))

    # --- evidence provenance (locator / quote bytes at HEAD) --------------
    def test_evidence_quote_tamper_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["evidence_refs"]["EV-1"]["quote"] = "positions are NED"
        errors = validate_binding(payload)
        self.assertTrue(any("quote differs from the frozen provenance" in item
                            for item in errors), errors)

    def test_evidence_locator_tamper_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["evidence_refs"]["EV-3"]["locator"] = "line 11"
        errors = validate_binding(payload)
        self.assertTrue(any("locator differs from the frozen provenance" in item
                            for item in errors), errors)
        self.assertTrue(any("declared citation not committed at HEAD" in item
                            for item in errors), errors)

    def test_evidence_ref_unknown_field_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["evidence_refs"]["EV-1"]["note"] = "unfrozen extra field"
        errors = validate_binding(payload)
        self.assertTrue(any("unknown fields" in item for item in errors), errors)

    def test_vocabulary_committed_text_tamper_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["frame_vocabulary"]["NED"]["committed_text"][0] = \
            "Simulator/wksim_core/README.md:52 positions are NED"
        errors = validate_binding(payload)
        self.assertTrue(any("committed_text differs from the frozen provenance" in item
                            for item in errors), errors)

    def test_vocabulary_unknown_field_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["datum_vocabulary"]["model_local_NED_frame_reference"]["invented"] = True
        errors = validate_binding(payload)
        self.assertTrue(any("unknown fields" in item for item in errors), errors)

    def test_committed_text_resolver_rejects_bad_fragments(self):
        # Directly exercise the HEAD-byte resolver, independent of the payload.
        self.assertIsNone(verify_quote_against_head(
            "Simulator/wksim_core/README.md", "line 52", "位置/速度为 NED"))
        self.assertEqual(
            verify_quote_against_head("Simulator/wksim_core/README.md", "line 52",
                                      "positions are NED"),
            "quote_absent_from_committed_head_blob")
        self.assertEqual(
            verify_quote_against_head("Simulator/wksim_core/README.md", "line 11",
                                      "位置/速度为 NED"),
            "quote_not_on_cited_line")
        self.assertEqual(
            verify_quote_against_head("validation/definitely-not-committed.json",
                                      "line 1", "x"),
            "path_not_tracked_at_head")
        self.assertIsNone(verify_committed_text_entry(
            'Simulator/wksim_core/model_parameters.py:33 "m; NED"'))
        self.assertEqual(
            verify_committed_text_entry(
                'Simulator/wksim_core/model_parameters.py:33 "m; ENU"'),
            "committed_text_fragment_not_on_cited_line")
        self.assertIsNone(verify_committed_text_entry(
            "Simulator/wksim_core/numerical-conformance-v1.json:observables[]"
            " 1e-7 degree per native unit"))
        self.assertIsNone(verify_committed_text_entry(
            "Simulator/wksim_core/numerical-conformance-v1.json:observables[]"
            " cpp:7625-7626 subtract 273.15000000000003"))
        self.assertIsNone(verify_committed_text_entry(
            "validation/e0-current-rhs-references-20260912.json:"
            "slots[Sensor30[13]].rhs.text 273.15000000000003"))
        # A fragment that is committed elsewhere in the same blob (the slot
        # key) but not inside the locator's JSON value.
        self.assertEqual(
            verify_committed_text_entry(
                "validation/e0-current-rhs-references-20260912.json:"
                "slots[Sensor30[13]].rhs.text Sensor30[13]"),
            "quote_not_in_json_locator_value")
        self.assertEqual(
            verify_committed_text_entry(
                "validation/e0-current-rhs-references-20260912.json:"
                "slots[Sensor30[13]].rhs.text 273.16"),
            "quote_absent_from_committed_head_blob")

    # --- owner-decision coverage in both directions -----------------------
    def test_owner_decision_orphan_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        touched = 0
        for slot in payload["slots"]:
            if slot["observable"] == "extra_motor_speed":
                slot["open_owner_decisions"] = [
                    item for item in slot["open_owner_decisions"] if item != "OD-20"]
                touched += 1
        self.assertEqual(touched, 4, "expected four extra_motor_speed slots")
        errors = validate_binding(payload)
        self.assertTrue(any("no slot references this decision" in item for item in errors),
                        errors)

    def test_owner_decision_coverage_is_bidirectional(self):
        referenced = {decision["id"]: set() for decision in self.payload["owner_decisions"]}
        for slot in self.payload["slots"]:
            for field in ("frame", "datum"):
                ident = slot[field].get("owner_decision")
                if ident:
                    referenced[ident].add(slot["slot"])
            for ident in slot["open_owner_decisions"]:
                referenced[ident].add(slot["slot"])
        for decision in self.payload["owner_decisions"]:
            ident = decision["id"]
            self.assertTrue(referenced[ident], "%s is referenced by no slot" % ident)
            self.assertEqual(sorted(set(decision["slots"]) - referenced[ident]), [],
                             "%s lists slots that do not reference it" % ident)
            self.assertNotEqual(decision["state"], "made", ident)
            self.assertIsNone(decision.get("chosen_option"), ident)
            self.assertIsNone(decision.get("made_by"), ident)

    # --- policy list mutations -------------------------------------------
    def test_duplicate_policy_pin_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["evidence_policy"]["require_tracked_at_head"].append("g6_frontier_review")
        errors = validate_binding(payload)
        self.assertTrue(any("require_tracked_at_head has duplicates" in item for item in errors))

    def test_extra_policy_pin_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["evidence_policy"]["require_tracked_at_head"].append("invented_pin")
        errors = validate_binding(payload)
        self.assertTrue(any("require_tracked_at_head mismatch" in item for item in errors))

    def test_extra_pin_entry_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["pins"]["invented_pin"] = {
            "id": "invented_pin",
            "path": EXPECTED_PINS["core_readme"],
            "sha256": sha256_bytes(head_bytes(EXPECTED_PINS["core_readme"])),
            "role": "invented",
        }
        errors = validate_binding(payload)
        self.assertTrue(any("extra pin invented_pin" in item for item in errors))

    def test_duplicate_json_key_fails_closed(self):
        # json.loads would keep the last value and hide the substitution.
        with self.assertRaises(ValueError):
            loads_no_duplicate_keys('{"pins": {"g6_frontier_review": {},'
                                    ' "g6_frontier_review": {}}}')
        with self.assertRaises(ValueError):
            loads_no_duplicate_keys('{"slot_count": 1, "slot_count": 2}')
        # The committed payload itself must be duplicate-free ...
        text = BINDING_PATH.read_text(encoding="utf-8")
        committed = loads_no_duplicate_keys(text)
        self.assertEqual(committed["slot_count"], DYNAMIC_SLOTS)
        # ... and a real pin hidden behind a duplicate key must be refused.
        pin = committed["pins"]["g6_frontier_review"]
        injected = json.dumps({"pins": {"g6_frontier_review": pin, "other": pin}},
                              ensure_ascii=False)
        self.assertEqual(
            loads_no_duplicate_keys(injected)["pins"]["g6_frontier_review"], pin)
        with self.assertRaises(ValueError):
            loads_no_duplicate_keys(injected.replace('"other"', '"g6_frontier_review"'))

    # --- null / owner / acceptance mutations ------------------------------
    def test_forged_datum_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        for slot in payload["slots"]:
            if slot["datum"]["value"] is None:
                slot["datum"] = {"value": "WGS84", "status": "bound", "evidence": ["EV-7"],
                                 "reason": None, "owner_decision": None}
                break
        errors = validate_binding(payload)
        self.assertTrue(any("forged or unknown datum value" in item for item in errors))

    def test_null_treated_as_approval_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        for slot in payload["slots"]:
            if slot["frame"]["value"] is None:
                slot["frame"]["status"] = "bound"
                break
        self.assertTrue(any("null value requires status" in item
                            for item in validate_binding(payload)))

        payload = copy.deepcopy(self.payload)
        for slot in payload["slots"]:
            if slot["datum"]["value"] is None:
                slot["datum"]["reason"] = "pending"
                break
        self.assertTrue(any("precise owner-decision reason" in item
                            for item in validate_binding(payload)))

        payload = copy.deepcopy(self.payload)
        for slot in payload["slots"]:
            if slot["frame"]["value"] is None:
                slot["frame"]["owner_decision"] = None
                break
        self.assertTrue(any("requires an owner_decision id" in item
                            for item in validate_binding(payload)))

        payload = copy.deepcopy(self.payload)
        for slot in payload["slots"]:
            if slot["datum"]["value"] is None:
                slot["binding_status"] = "bound"
                break
        self.assertTrue(any("binding_status" in item for item in validate_binding(payload)))

    def test_decided_owner_decision_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["owner_decisions"][0]["state"] = "made"
        payload["owner_decisions"][0]["made_by"] = "someone"
        errors = validate_binding(payload)
        self.assertTrue(any("must stay 'not_made'" in item for item in errors))
        self.assertTrue(any("must not record a decision" in item for item in errors))

    def test_owner_decision_slots_tamper_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        for decision in payload["owner_decisions"]:
            if decision["id"] == "OD-23":
                decision["slots"] = ["GPS30[7]"]
                break
        errors = validate_binding(payload)
        self.assertTrue(any("slots differ from the frozen identity" in item for item in errors))

    def test_untracked_pin_path_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        pin_id = sorted(payload["pins"])[0]
        payload["pins"][pin_id]["path"] = "validation/definitely-not-committed.json"
        errors = validate_binding(payload)
        self.assertTrue(any("wrong_pin_path" in item for item in errors))

    def test_acceptance_flip_fails_closed(self):
        for flag in ("budget_approved", "g6_acceptance", "physical_accuracy",
                     "issues_closed", "effective"):
            payload = copy.deepcopy(self.payload)
            payload[flag] = True
            self.assertTrue(any("acceptance flip" in item for item in validate_binding(payload)),
                            flag)
        payload = copy.deepcopy(self.payload)
        payload["r1_status"] = "declared_cases_pass"
        self.assertTrue(any("r1_status" in item for item in validate_binding(payload)))

    def test_acceptance_like_key_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["g6_accepted"] = True
        errors = validate_binding(payload)
        self.assertTrue(any("forbidden budget/approval field" in item for item in errors))

    def test_budget_field_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["slots"][0]["abs_budget"] = 1e-9
        errors = validate_binding(payload)
        self.assertTrue(any("forbidden budget/approval field" in item for item in errors))
        self.assertTrue(any("unknown fields" in item for item in errors))

    def test_unit_mutation_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["slots"][3]["native_unit"] = "cm/s"
        errors = validate_binding(payload)
        self.assertTrue(any("native_unit differs" in item for item in errors))

    def test_generated_rhs_symbol_tamper_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        target = payload["slots"][3]
        target["current_generated_rhs"] = "Exp1_MinModelTemp_B.Invented[3]"
        errors = validate_binding(payload)
        self.assertTrue(any("current_generated_rhs" in item and
                            "not a complete pinned RHS symbol identity" in item
                            for item in errors), errors)

    def test_generated_rhs_substring_is_not_identity(self):
        payload = copy.deepcopy(self.payload)
        target = None
        for slot in payload["slots"]:
            if slot["slot"] == "Vehicle60[5]":
                target = slot
                break
        self.assertIsNotNone(target)
        self.assertEqual(target["current_generated_rhs"],
                         "Exp1_MinModelTemp_B.Product[2]")
        target["current_generated_rhs"] = "Product"
        errors = validate_binding(payload, check_pins=False)
        self.assertTrue(any("current_generated_rhs" in item and
                            "not a complete pinned RHS symbol identity" in item
                            for item in errors), errors)

    def test_generated_rhs_hostile_identity_mutations_fail_closed(self):
        rhs = read_json_at_head(RHS_REL)
        exact = "Exp1_MinModelTemp_B.Product[2]"
        self.assertTrue(rhs_symbol_present(rhs, "Vehicle60[5]", exact))
        hostile = (
            "Product",
            "Exp1_MinModelTemp_B.Product",
            "Exp1_MinModelTemp_B.Product[",
            "Product[2]",
            "Exp1_MinModelTemp_B.Product[1]",
            "Exp1_MinModelTemp_B.Product[0]",
            "Exp1_MinModelTemp_B.Product[20]",
            "Exp1_MinModelTemp_B.Product4[2]",
            "xExp1_MinModelTemp_B.Product[2]",
            "Exp1_MinModelTemp_B.Product[2]x",
            exact + exact,
            "Exp1_MinModelTemp_B.q_out[2]",
        )
        for symbol in hostile:
            self.assertFalse(rhs_symbol_present(rhs, "Vehicle60[5]", symbol), symbol)
            payload = copy.deepcopy(self.payload)
            for slot in payload["slots"]:
                if slot["slot"] == "Vehicle60[5]":
                    slot["current_generated_rhs"] = symbol
                    break
            errors = validate_binding(payload, check_pins=False)
            self.assertTrue(
                any("current_generated_rhs" in item and
                    "not a complete pinned RHS symbol identity" in item
                    for item in errors),
                (symbol, errors),
            )

    def test_counts_lie_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["counts"] = {
            "slots_total": 56,
            "frame_bound": 56,
            "frame_unresolved": 0,
            "datum_bound": 56,
            "datum_unresolved": 0,
            "owner_decision_count": 0,
        }
        errors = validate_binding(payload, check_pins=False)
        self.assertTrue(any(item.startswith("counts.") for item in errors), errors)
        self.assertTrue(any("counts.frame_bound" in item for item in errors), errors)
        self.assertTrue(any("counts.owner_decision_count" in item for item in errors), errors)

    def test_counts_unknown_or_missing_key_fails_closed(self):
        payload = copy.deepcopy(self.payload)
        payload["counts"]["invented_count"] = 1
        errors = validate_binding(payload, check_pins=False)
        self.assertTrue(any("counts: unknown key invented_count" in item for item in errors),
                        errors)
        payload = copy.deepcopy(self.payload)
        payload["counts"].pop("datum_bound")
        errors = validate_binding(payload, check_pins=False)
        self.assertTrue(any("counts: missing key datum_bound" in item for item in errors),
                        errors)
        payload = copy.deepcopy(self.payload)
        payload["counts"] = "not-an-object"
        errors = validate_binding(payload, check_pins=False)
        self.assertTrue(any("counts must be an object" in item for item in errors), errors)

    def test_observables_locator_requires_exact_field(self):
        contract = CONTRACT_REL
        self.assertIsNone(verify_quote_against_head(
            contract, "observables[]", "1e-7 degree per native unit"))
        self.assertIsNone(verify_quote_against_head(
            contract, "observables[]", "cpp:7625-7626 subtract 273.15000000000003"))
        # Exact native_unit fields remain exact element/field matches.
        self.assertIsNone(verify_quote_against_head(contract, "observables[]", "m/s"))
        hostile = (
            ("1e-7 degree", "prefix of native_unit"),
            ("per native unit", "suffix of native_unit"),
            ("subtract 273.15000000000003", "source-field substring"),
            ("1e-7 degree per native unit x", "suffix extra"),
            ("mapped_physical", "semantic_status prefix"),
            ("wksim-e0-fixed-reference-native-preservation-v1", "contract_id blob-only"),
        )
        for quote, label in hostile:
            self.assertEqual(
                verify_quote_against_head(contract, "observables[]", quote),
                "quote_not_exact_observables_field" if quote in head_text(contract)
                else "quote_absent_from_committed_head_blob",
                label,
            )
        self.assertEqual(
            verify_committed_text_entry(
                "Simulator/wksim_core/numerical-conformance-v1.json:observables[]"
                " subtract 273.15000000000003"),
            "quote_not_exact_observables_field")

    def test_pinned_rhs_and_manifest_helpers(self):
        rhs = read_json_at_head(RHS_REL)
        manifest = read_json_at_head(MANIFEST_REL)
        self.assertTrue(rhs_symbol_present(rhs, "Vehicle60[3]",
                                           "Exp1_MinModelTemp_B.Product[0]"))
        self.assertTrue(rhs_symbol_present(rhs, "Vehicle60[5]",
                                           "Exp1_MinModelTemp_B.Product[2]"))
        self.assertFalse(rhs_symbol_present(rhs, "Vehicle60[5]", "Product"))
        self.assertFalse(rhs_symbol_present(rhs, "Vehicle60[5]",
                                            "Exp1_MinModelTemp_B.Product"))
        self.assertFalse(rhs_symbol_present(rhs, "Vehicle60[3]", "invented_symbol"))
        self.assertFalse(rhs_symbol_present(rhs, "Vehicle60[999]", "anything"))
        self.assertFalse(rhs_symbol_present(rhs, "Vehicle60[3]", None))
        self.assertEqual(manifest_phase(manifest, "Vehicle60[3]"), "major_root_output")
        self.assertIsNone(manifest_phase(manifest, "Vehicle60[999]"))
        for slot in self.payload["slots"]:
            self.assertIsNotNone(manifest_phase(manifest, slot["slot"]), slot["slot"])

    def test_manifest_missing_slot_fails_closed(self):
        manifest = read_json_at_head(MANIFEST_REL)
        self.assertIsNone(manifest_phase(manifest, "GPS30[29]"))
        injected = copy.deepcopy(manifest)
        injected["slots"] = [entry for entry in injected["slots"]
                             if entry["slot"] != "Vehicle60[3]"]
        self.assertIsNone(manifest_phase(injected, "Vehicle60[3]"))
        errors = validate_binding(self.payload, manifest=injected)
        self.assertTrue(
            any("Vehicle60[3] is missing from the committed slot manifest" in item
                for item in errors),
            errors,
        )
        self.assertEqual(validate_binding(self.payload), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
