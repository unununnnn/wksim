"""Fail-closed tests for the #59 G6 B1 budget approval-provenance ledger.

The ledger at ``validation/e0-budget-approval-provenance-20260914.json`` enumerates
the 120 frozen e0 output slots and records, per slot, the fields a budget
promotion would need: source identity, metric, domain, frame/datum, derivation,
the abs/rel/RMS triple, and the approval decision identity.  Today every budget
and every approval field is null / not_made.

This module is deliberately independent of the ledger it checks:

* the expected slot set and the pin ``id -> path`` mapping are frozen here and
  re-derived from the committed HEAD blobs, never read from the ledger;
* pin bytes come from ``git show HEAD:<path>``, never from the working
  tree, so staged-only, untracked or substituted pins are rejected;
* ``git diff HEAD`` must be clean for every pinned path (dirty or staged);
* the forbidden-provenance marker table and the loophole rules are frozen here,
  so a ledger that drops a rule or invents an approval route still fails closed;
* the closed sub-field sets of every slot sub-block, the slot-set partition and
  the counts are frozen here and cross-checked against the slot list, so a value
  planted outside `budgets` or an inconsistent summary block is rejected;
* an external owner/derivation record location is judged by *path class*, never by
  a hard-coded directory name: no coordination directory at any depth, no package
  file, no traversal, no absolute path.  Frozen input pins are a different class --
  they are admitted by pin id/path/sha256 against HEAD, so a tracked coordination
  artifact may stay a pin (see `pin:budget_evidence_audit`) without ever being
  admissible as a promotion record.  The pre-repair independent review and the
  repair outputs both live under `validation/coordination/**` and are therefore
  named in the plan and ledger as provenance, and are structurally inadmissible as
  owner or derivation evidence.  Those named review/repair directories are not
  clean-checkout disk dependencies.  ``6eafdf9`` is the source/ancestor pin, not a
  post-commit HEAD equality.  After commit the ledger should be a HEAD blob whose
  bytes match the working tree and the payload/plan pins.  Related-artifact
  untracked facts are bound to that source pin via ``git show`` / ``ls-tree``;
  later tracking at current HEAD does not promote them to pins, owner records
  or derivation evidence.  Each related id/path/sha256 triple is frozen here
  and compared exactly by ``validate()``; a path spelling, hash, order,
  duplicate id/path, extra or missing record fails closed and does not become
  an evidence pin.  ``validate(check_git=True)`` itself refuses a missing
  SOURCE_HEAD or a SOURCE_HEAD that is not an ancestor of HEAD with a stable
  token; ``check_git=False`` stays a structural path and skips those git
  object/ancestor probes.

A structurally valid ledger is still a blocked ledger: nothing here can approve
a budget, and editing the ledger can never create an approval route.

Run (pure offline, no native/model/MATLAB/ROS/FC/UE/build/flight):

    python -B -m unittest validation.test_e0_budget_approval_provenance
"""

import copy
import hashlib
import json
import math
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LEDGER_REL = "validation/e0-budget-approval-provenance-20260914.json"
DOC_REL = "docs/plan/59-e0-budget-approval-provenance-20260914.md"
TEST_REL = "validation/test_e0_budget_approval_provenance.py"
COORDINATION_DIR_REL = "validation/coordination"
# The location rule is a path *class*: a segment is compared case-folded, so this is
# the only spelling-dependent constant and it is used folded everywhere.
COORDINATION_SEGMENT = "coordination"
# Independent review artifacts of this slice, named here for provenance only.
# They are *documentation* constants, not the enforcement mechanism: the location
# rule below is structural (any coordination directory), so naming a directory is
# never what rejects a record.
PRE_REPAIR_REVIEW_DIR_REL = (
    "validation/coordination/deepseek-g6-budget-provenance-review-20260914-01")
REPAIR_DIR_REL = (
    "validation/coordination/deepseek-g6-budget-provenance-repair-20260914-01")
POST_REPAIR_REVIEW_DIR_REL = (
    "validation/coordination/cursor-g6-budget-postrepair-review-20260914-01")
REPAIR2_DIR_REL = (
    "validation/coordination/deepseek-g6-budget-provenance-repair2-20260914-01")
TAKEOVER_DIR_REL = (
    "validation/coordination/cursor-g6-budget-c1-takeover-20260914-01")
SEQUENCE_REPAIR_DIR_REL = (
    "validation/coordination/cursor-g6-budget-frame-sequence-repair-20260914-01")
FINAL_REVIEW_DIR_REL = (
    "validation/coordination/cursor-g6-budget-frame-final-review-20260914-01")
RELATED_SOURCE_P2_REPAIR_DIR_REL = (
    "validation/coordination/cursor-g6-budget-related-source-p2-repair-20260914-01")

LEDGER_PATH = ROOT / LEDGER_REL
DOC_PATH = ROOT / DOC_REL
TEST_PATH = ROOT / TEST_REL
LEDGER_TEXT = LEDGER_PATH.read_text(encoding="utf-8")

# Source pin recorded by this slice.  It must remain an ancestor of HEAD after
# the package is committed; current HEAD is not required to equal it.
SOURCE_HEAD = "6eafdf9c0b734db07a9fe790c86b409d3468c10b"
BASELINE_ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"

# Payload (ledger) and plan bytes are pinned here.  After commit, a HEAD blob
# for either path must match the working tree and these hashes.  The test file
# is not self-hashed.
PACKAGE_SHA256 = {
    LEDGER_REL: "2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d",
    DOC_REL: "15b4f457912aef9f31537b4a3660d32e8d90110f042550aa0b6d5909f6d277bd",
}

NAMED_COORDINATION_DIRS = (
    PRE_REPAIR_REVIEW_DIR_REL,
    REPAIR_DIR_REL,
    POST_REPAIR_REVIEW_DIR_REL,
    REPAIR2_DIR_REL,
    TAKEOVER_DIR_REL,
    SEQUENCE_REPAIR_DIR_REL,
    FINAL_REVIEW_DIR_REL,
    RELATED_SOURCE_P2_REPAIR_DIR_REL,
)

# Paths that may never be used as evidence for a promotion: an artifact cannot
# prove its own promotion.
PACKAGE_PATHS = (LEDGER_REL, DOC_REL, TEST_REL)
PACKAGE_PATHS_FOLDED = frozenset(_p.casefold() for _p in PACKAGE_PATHS)
UNTRACKED_NON_PACKAGE = "validation/e0-never-tracked-external-record-20260914.json"
FRAME_CANDIDATE_REL = "validation/e0-frame-datum-binding-20260914.json"
STALE_FRAME_RELATED_SHA256 = (
    "33c4909919d73c344336a9a56a4a824b3974473d8e063874ad088c32c534f39f")
RELATED_REQUIRED_KEYS = (
    "id", "path", "sha256", "tracked_at_source_head", "role",
)
# Authority for related_artifacts: exact id → path → sha256 triples, in order.
# validate() compares these literally.  A backslash, ./ prefix, hash edit,
# reorder, duplicate id/path, extra or missing row fails closed.  Related
# records are never admitted as pins, owner records or derivation records.
RELATED_ARTIFACTS = (
    ("frontier_audit_review",
     "validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/review.md",
     "d965a0802268a2bfcefdae897bbe6e93735233d70bc67c3b4ec1bfb7d465eece"),
    ("frontier_audit_json",
     "validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/frontier.json",
     "3d33edf3ec697f16b5dcd10abcaa26f7354098d335548ed04040e366d080cb00"),
    ("frontier_owner_input_template",
     "validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/owner-input-template.json",
     "2a15793bdac45b6747d4055c939d6429e1de26e889aac435e13339987640a656"),
)
RELATED_ARTIFACT_PATHS = {row[0]: row[1] for row in RELATED_ARTIFACTS}
RELATED_ARTIFACT_SHA256 = {row[0]: row[2] for row in RELATED_ARTIFACTS}

# Token emitted when an external owner/derivation record is not at an admissible
# location.  Distinct from self_referential_evidence (which names this slice's own
# package files) because a *tracked* coordination artifact is not a self-reference:
# it is the wrong location class for a promotion record.
LOCATION_VIOLATION_TOKEN = "external_record_location_violation"
RELATED_ARTIFACT_MISMATCH_TOKEN = "related_artifact_mismatch"
SOURCE_HEAD_VIOLATION_TOKEN = "source_head_missing_or_not_ancestor"

# --------------------------------------------------------------------------- #
# Frozen pin mapping.  The test is the authority; the ledger must agree with it.
# --------------------------------------------------------------------------- #
PIN_PATHS = {
    "r1_contract": "Simulator/wksim_core/numerical-conformance-v1.json",
    "slot_manifest": "validation/e0-source-to-slot-manifest-20260911.json",
    "rhs_references": "validation/e0-current-rhs-references-20260912.json",
    "current_source_mapping": "validation/e0-current-source-mapping-20260912.json",
    "budget_manifest_schema": "docs/plan/10-g6-budget-manifest.schema.json",
    "g6_remediation_contract": "docs/plan/10-g6-remediation-contract.md",
    "dynamic_budget_source_map": "docs/plan/59-e0-dynamic-budget-source-map.md",
    "same_source_command": "docs/plan/59-e0-same-source-command.md",
    "same_source_entry": "tools/run_e0_same_source_conformance.py",
    "budget_manifest_generator": "tools/generate_g6_budget_manifest.py",
    "budget_manifest_validator": "tools/validate_g6_budget_manifest.py",
    "solve_form_decision": "validation/e0-g6-solve-form-decision-20260914.json",
    "budget_evidence_audit":
        "validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json",
}

PIN_SHA256 = {
    "r1_contract":
        "23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0",
    "slot_manifest":
        "e48982b4732e4fd84ea26390eb516b7e35aea93267aa741ef3c32538cefa6867",
    "rhs_references":
        "fa068cc78f8f93e695417d6e315002c799f1bd4d7ef03641a5b236be9cddc188",
    "current_source_mapping":
        "28684e66cd6e49c90907dacdabf219608a3e3ba808e07e3bd9068233268489f8",
    "budget_manifest_schema":
        "c480b42d877bae5c435a39318ca61c77acb547593f3b3c9ce78cc3db0d4c2e5e",
    "g6_remediation_contract":
        "48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0",
    "dynamic_budget_source_map":
        "35a56084105409329131add7d4b9e35be6d1a145c6e18268c96324805313cd42",
    "same_source_command":
        "345caff0fd354717a64ed1dfac2c3ad33f87c72713cf3362483c395fb66b197e",
    "same_source_entry":
        "8398100b7fb6b839e279afd6e8f8708e57e415450dbb6621acdc9ea9ecc46517",
    "budget_manifest_generator":
        "2ae3c45dd27f5c5c8284c78ab0a94038313b81d184c0eb437a68f00edbbc6dd1",
    "budget_manifest_validator":
        "ee0ec4df76f98a9c006b44e957b7ac07e90edea6e2e2b07f14cd94f88971a49c",
    "solve_form_decision":
        "5086c3fbddd52b4e754a785706cce938ca7f8d68beb5056d564e7f116b34c293",
    "budget_evidence_audit":
        "04604840d3b79f6cfe26e2cc4e2547f6c15b3f7cc66aa1da0cb69527f0bf0d66",
}

# --------------------------------------------------------------------------- #
# Frozen slot set: slot_id -> (array, index, observable, semantic_status,
#                              partition, policy_class)
# --------------------------------------------------------------------------- #
FROZEN_SLOTS = {
    "Vehicle60[0]": ("Vehicle60", 0, "vehicle_identity", "interface_metadata", "policy_slot", "interface_metadata"),
    "Vehicle60[1]": ("Vehicle60", 1, "vehicle_identity", "interface_metadata", "policy_slot", "interface_metadata"),
    "Vehicle60[2]": ("Vehicle60", 2, "vehicle_time", "schedule_metadata", "dynamic_candidate", None),
    "Vehicle60[3]": ("Vehicle60", 3, "velocity_ned", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[4]": ("Vehicle60", 4, "velocity_ned", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[5]": ("Vehicle60", 5, "velocity_ned", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[6]": ("Vehicle60", 6, "position_ned", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[7]": ("Vehicle60", 7, "position_ned", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[8]": ("Vehicle60", 8, "position_ned", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[9]": ("Vehicle60", 9, "euler_components", "encoded_orientation_components_only", "dynamic_candidate", None),
    "Vehicle60[10]": ("Vehicle60", 10, "euler_components", "encoded_orientation_components_only", "dynamic_candidate", None),
    "Vehicle60[11]": ("Vehicle60", 11, "euler_components", "encoded_orientation_components_only", "dynamic_candidate", None),
    "Vehicle60[12]": ("Vehicle60", 12, "quaternion_components", "encoded_orientation_components_only", "dynamic_candidate", None),
    "Vehicle60[13]": ("Vehicle60", 13, "quaternion_components", "encoded_orientation_components_only", "dynamic_candidate", None),
    "Vehicle60[14]": ("Vehicle60", 14, "quaternion_components", "encoded_orientation_components_only", "dynamic_candidate", None),
    "Vehicle60[15]": ("Vehicle60", 15, "quaternion_components", "encoded_orientation_components_only", "dynamic_candidate", None),
    "Vehicle60[16]": ("Vehicle60", 16, "active_motor_speed", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[17]": ("Vehicle60", 17, "active_motor_speed", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[18]": ("Vehicle60", 18, "active_motor_speed", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[19]": ("Vehicle60", 19, "active_motor_speed", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[20]": ("Vehicle60", 20, "extra_motor_speed", "inactive_channels_not_aircraft_coverage", "dynamic_candidate", None),
    "Vehicle60[21]": ("Vehicle60", 21, "extra_motor_speed", "inactive_channels_not_aircraft_coverage", "dynamic_candidate", None),
    "Vehicle60[22]": ("Vehicle60", 22, "extra_motor_speed", "inactive_channels_not_aircraft_coverage", "dynamic_candidate", None),
    "Vehicle60[23]": ("Vehicle60", 23, "extra_motor_speed", "inactive_channels_not_aircraft_coverage", "dynamic_candidate", None),
    "Vehicle60[24]": ("Vehicle60", 24, "body_motion_acceleration", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[25]": ("Vehicle60", 25, "body_motion_acceleration", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[26]": ("Vehicle60", 26, "body_motion_acceleration", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[27]": ("Vehicle60", 27, "body_angular_rate", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[28]": ("Vehicle60", 28, "body_angular_rate", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[29]": ("Vehicle60", 29, "body_angular_rate", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[30]": ("Vehicle60", 30, "truth_latitude_longitude", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[31]": ("Vehicle60", 31, "truth_latitude_longitude", "mapped_physical_observable", "dynamic_candidate", None),
    "Vehicle60[32]": ("Vehicle60", 32, "truth_altitude", "height_datum_semantics_not_fully_verified", "dynamic_candidate", None),
    "Vehicle60[33]": ("Vehicle60", 33, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[34]": ("Vehicle60", 34, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[35]": ("Vehicle60", 35, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[36]": ("Vehicle60", 36, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[37]": ("Vehicle60", 37, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[38]": ("Vehicle60", 38, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[39]": ("Vehicle60", 39, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[40]": ("Vehicle60", 40, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[41]": ("Vehicle60", 41, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[42]": ("Vehicle60", 42, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[43]": ("Vehicle60", 43, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[44]": ("Vehicle60", 44, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[45]": ("Vehicle60", 45, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[46]": ("Vehicle60", 46, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[47]": ("Vehicle60", 47, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[48]": ("Vehicle60", 48, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[49]": ("Vehicle60", 49, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[50]": ("Vehicle60", 50, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[51]": ("Vehicle60", 51, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[52]": ("Vehicle60", 52, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[53]": ("Vehicle60", 53, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[54]": ("Vehicle60", 54, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[55]": ("Vehicle60", 55, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[56]": ("Vehicle60", 56, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[57]": ("Vehicle60", 57, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[58]": ("Vehicle60", 58, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Vehicle60[59]": ("Vehicle60", 59, "vehicle_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[0]": ("Sensor30", 0, "sensor_time", "schedule_metadata", "dynamic_candidate", None),
    "Sensor30[1]": ("Sensor30", 1, "accelerometer", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[2]": ("Sensor30", 2, "accelerometer", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[3]": ("Sensor30", 3, "accelerometer", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[4]": ("Sensor30", 4, "gyroscope", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[5]": ("Sensor30", 5, "gyroscope", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[6]": ("Sensor30", 6, "gyroscope", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[7]": ("Sensor30", 7, "magnetic_field", "wmm_physical_fidelity_unverified", "dynamic_candidate", None),
    "Sensor30[8]": ("Sensor30", 8, "magnetic_field", "wmm_physical_fidelity_unverified", "dynamic_candidate", None),
    "Sensor30[9]": ("Sensor30", 9, "magnetic_field", "wmm_physical_fidelity_unverified", "dynamic_candidate", None),
    "Sensor30[10]": ("Sensor30", 10, "absolute_pressure", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[11]": ("Sensor30", 11, "differential_pressure", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[12]": ("Sensor30", 12, "pressure_altitude", "height_datum_semantics_not_fully_verified", "dynamic_candidate", None),
    "Sensor30[13]": ("Sensor30", 13, "temperature", "mapped_physical_observable", "dynamic_candidate", None),
    "Sensor30[14]": ("Sensor30", 14, "sensor_update_mask", "interface_metadata", "policy_slot", "interface_metadata"),
    "Sensor30[15]": ("Sensor30", 15, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[16]": ("Sensor30", 16, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[17]": ("Sensor30", 17, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[18]": ("Sensor30", 18, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[19]": ("Sensor30", 19, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[20]": ("Sensor30", 20, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[21]": ("Sensor30", 21, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[22]": ("Sensor30", 22, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[23]": ("Sensor30", 23, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[24]": ("Sensor30", 24, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[25]": ("Sensor30", 25, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[26]": ("Sensor30", 26, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[27]": ("Sensor30", 27, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[28]": ("Sensor30", 28, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "Sensor30[29]": ("Sensor30", 29, "sensor_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[0]": ("GPS30", 0, "gps_time", "schedule_metadata", "dynamic_candidate", None),
    "GPS30[1]": ("GPS30", 1, "gps_latitude_longitude", "mapped_physical_observable_unquantized_double", "dynamic_candidate", None),
    "GPS30[2]": ("GPS30", 2, "gps_latitude_longitude", "mapped_physical_observable_unquantized_double", "dynamic_candidate", None),
    "GPS30[3]": ("GPS30", 3, "gps_altitude", "height_datum_semantics_not_fully_verified", "dynamic_candidate", None),
    "GPS30[4]": ("GPS30", 4, "gps_accuracy_indicators", "physical_accuracy_meaning_unverified", "dynamic_candidate", None),
    "GPS30[5]": ("GPS30", 5, "gps_accuracy_indicators", "physical_accuracy_meaning_unverified", "dynamic_candidate", None),
    "GPS30[6]": ("GPS30", 6, "gps_horizontal_speed", "mapped_physical_observable_unquantized_double", "dynamic_candidate", None),
    "GPS30[7]": ("GPS30", 7, "gps_velocity_ned", "mapped_physical_observable_unquantized_double", "dynamic_candidate", None),
    "GPS30[8]": ("GPS30", 8, "gps_velocity_ned", "mapped_physical_observable_unquantized_double", "dynamic_candidate", None),
    "GPS30[9]": ("GPS30", 9, "gps_velocity_ned", "mapped_physical_observable_unquantized_double", "dynamic_candidate", None),
    "GPS30[10]": ("GPS30", 10, "gps_course_encoded", "angular_units_and_convention_unverified", "dynamic_candidate", None),
    "GPS30[11]": ("GPS30", 11, "gps_fix_and_satellites", "interface_metadata", "policy_slot", "interface_metadata"),
    "GPS30[12]": ("GPS30", 12, "gps_fix_and_satellites", "interface_metadata", "policy_slot", "interface_metadata"),
    "GPS30[13]": ("GPS30", 13, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[14]": ("GPS30", 14, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[15]": ("GPS30", 15, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[16]": ("GPS30", 16, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[17]": ("GPS30", 17, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[18]": ("GPS30", 18, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[19]": ("GPS30", 19, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[20]": ("GPS30", 20, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[21]": ("GPS30", 21, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[22]": ("GPS30", 22, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[23]": ("GPS30", 23, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[24]": ("GPS30", 24, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[25]": ("GPS30", 25, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[26]": ("GPS30", 26, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[27]": ("GPS30", 27, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[28]": ("GPS30", 28, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
    "GPS30[29]": ("GPS30", 29, "gps_reserved", "reserved_not_physical_coverage", "policy_slot", "reserved_not_physical_coverage"),
}

EXPECTED_TOP_KEYS = frozenset({
    "schema", "kind", "issue", "parent_issue", "layer", "authority", "effective",
    "date", "work_class", "title", "budget_approved", "g6_acceptance",
    "physical_accuracy", "issues_closed", "owner_decisions_made", "r1_status",
    "claim_text", "observed_at", "evidence_policy", "pins", "related_artifacts",
    "slot_set", "counts", "required_slot_fields", "required_subfields",
    "status_vocabulary", "approval_state_vocabulary", "evidence_class_vocabulary",
    "owner_input_vocabulary", "slots", "external_owner_records",
    "external_derivation_records", "promotion_requirements",
    "forbidden_provenance_classes", "loophole_rules", "non_claims",
    "scope_limits", "validation",
})

REQUIRED_SLOT_KEYS = frozenset({
    "slot_id", "array", "index", "observable", "semantic_status", "partition",
    "policy_class", "source_identity", "metric", "domain", "frame_datum",
    "derivation", "budgets", "approval", "status", "owner_inputs",
})

STATUS_VOCABULARY = frozenset({"blocked", "pending_owner_policy"})
APPROVAL_STATE_VOCABULARY = frozenset({"not_made", "made", "rejected", "deferred"})
EVIDENCE_CLASS_VOCABULARY = frozenset({
    "committed_derivable", "committed_partial", "mixed", "owner_only",
    "owner_only_external", "not_applicable",
})
OWNER_INPUT_VOCABULARY = frozenset(
    "D-%02d" % number for number in range(1, 13))
RESOLUTION_VOCABULARY = frozenset({"terminal", "local_bound", "unresolved", None})
BUDGET_FIELDS = ("abs_budget", "rel_budget", "rms_budget")

FROZEN_METRIC = "abs_le_a_plus_r_absref_with_rms_cap_v1"

# Frozen forbidden-provenance marker table.  The ledger must declare every class
# id, but the markers that enforce them live here.
FORBIDDEN_MARKERS = {
    "RD-01": ("r1 delta", "r1 difference", "r1_diff", "5684", "cross-version delta",
              "cross version difference", "retained failure"),
    "RD-02": ("candidate difference", "same-source delta", "same source difference",
              "c0 diagnostic", "60120", "observed difference"),
    "RD-03": ("1 ulp", "one ulp", "2 ulp", "ulp budget", "vanished ulp",
              "ulp as budget"),
    "RD-04": ("o(h^4)", "order of accuracy", "grid convergence", "machine epsilon",
              "double epsilon", "step size", "rk4 order"),
    "RD-05": ("noise amplitude", "noise magnitude", "gain", "seed amplitude",
              "parameter value", "calibration course", "sensor course",
              "config value"),
    "RD-06": ("self hash", "self-referential", "self reference", "this ledger",
              "hash of itself", "contract_sha256 of itself"),
    "RD-07": ("tbd", "to be determined", "see analysis", "placeholder", "n/a",
              "unknown", "later", "t.b.d."),
    "RD-08": ("sitl threshold", "takeoff 2.5", "0.6 m", "0.35 rad",
              "waypoint 0.5", "land 0.3", "control integration threshold"),
    "RD-09": ("frame-datum binding", "untracked supplement", "in-flight supplement",
              "working-tree binding"),
    "RD-10": ("aligned", "0 ulp", "zero ulp", "diagonal candidate", "bit identical"),
    "RD-11": ("synthetic probe", "ordering probe", "validate_contract_reasons",
              "in-memory contract"),
    "RD-12": ("reserved as coverage", "covered by budget", "physical coverage",
              "counts as coverage"),
}
EXPECTED_FORBIDDEN_IDS = frozenset(FORBIDDEN_MARKERS)
EXPECTED_LOOPHOLE_IDS = frozenset({"L1", "L2", "L3", "L4"})

# Only these provenance-bearing fields are scanned for placeholders, forbidden
# markers and self-reference; scanning every string would false-positive on the
# legitimate vocabulary (for example partition "dynamic_candidate").
SCANNED_STRING_PATHS = (
    ("derivation", "ref"),
    ("derivation", "derivation_class"),
    ("derivation", "forbidden_class"),
    ("domain", "declared_domain"),
    ("frame_datum", "frame"),
    ("frame_datum", "datum"),
    ("approval", "decision_id"),
    ("approval", "decision_ref"),
    ("approval", "approver"),
)

# Closed sub-field sets.  The ledger declares the same sets in
# ``required_subfields`` and must agree exactly; the frozen copy is what is
# enforced, so deleting a declared sub-field fails closed instead of shrinking
# the check.
FROZEN_SUBFIELDS = {
    "source_identity": ("r1_observable_id", "native_unit", "native_unit_source",
                        "committed_source_mapping", "evidence_class"),
    "metric": ("frozen_metric", "equivalence_class_required", "equivalence_owner_input",
               "status"),
    "domain": ("excited_response_inventory_ref", "declared_domain", "status",
               "evidence_class"),
    "frame_datum": ("frame", "datum", "status", "evidence_class", "owner_input"),
    "derivation": ("required", "ref", "derivation_class", "status", "evidence_class",
                   "forbidden_class"),
    "budgets": ("abs_budget", "rel_budget", "rms_budget", "status"),
    "approval": ("state", "decision_id", "approver", "decided_utc",
                 "decision_text_digest", "decision_ref", "external_record_pinned",
                 "evidence_class"),
}
SOURCE_MAPPING_KEYS = frozenset({
    "status", "outport", "line_ranges", "rhs_resolution_status",
    "rhs_resolution_reason", "slot_manifest_status"})
# Sub-block status vocabularies.  `budgets`/`metric`/`domain`/`derivation` may
# never carry anything but `blocked`; `frame_datum` follows its slot.
SUBBLOCK_STATUS_VOCABULARY = frozenset({"blocked", "pending_owner_policy"})
BLOCKED_ONLY_SUBBLOCKS = ("metric", "domain", "derivation", "budgets")
SLOT_SET_KEYS = frozenset({
    "total_slots", "dynamic_candidate_slots", "policy_slots",
    "policy_interface_metadata", "policy_reserved_not_physical_coverage",
    "arrays", "partition_rule"})


# --------------------------------------------------------------------------- #
# git helpers: HEAD blobs only, never working-tree bytes.
# Pin bytes: ``git show HEAD:<path>``. Dirty/staged: ``git diff HEAD``.
# --------------------------------------------------------------------------- #
def _git(*args, env=None):
    return subprocess.run(["git", "-C", str(ROOT)] + list(args),
                          capture_output=True, env=env)


def head_blob(path):
    """Return the HEAD blob bytes via ``git show HEAD:path``, or None."""
    done = _git("show", "HEAD:" + path)
    return done.stdout if done.returncode == 0 else None


def head_sha256(path):
    data = head_blob(path)
    return None if data is None else hashlib.sha256(data).hexdigest()


def tracked_at_head(path):
    return head_blob(path) is not None


def source_blob(path):
    """Return the source-pin blob bytes via ``git show SOURCE_HEAD:path``, or None."""
    done = _git("show", SOURCE_HEAD + ":" + path)
    return done.stdout if done.returncode == 0 else None


def source_ls_tree_names(path):
    done = _git("ls-tree", "-r", "--name-only", SOURCE_HEAD, "--", path)
    return [line.replace("\\", "/")
            for line in done.stdout.decode("utf-8", "replace").splitlines()
            if line.strip()]


def tracked_at_source_head(path):
    """Related-artifact untracked facts are bound to SOURCE_HEAD, not current HEAD.

    ``git show`` and ``ls-tree`` must agree.  Disagreement is treated as tracked
    so an untracked claim fails closed.
    """
    if not isinstance(path, str) or not path:
        return False
    normalized = path.replace("\\", "/")
    show_ok = source_blob(normalized) is not None
    list_ok = normalized in source_ls_tree_names(normalized)
    if show_ok != list_ok:
        return True
    return show_ok


def source_head_commit_exists():
    """True only when SOURCE_HEAD names a commit object in this repository."""
    done = _git("cat-file", "-e", SOURCE_HEAD + "^{commit}")
    return done.returncode == 0


def source_head_is_ancestor_of_head():
    """True only when SOURCE_HEAD is an ancestor of the current HEAD."""
    done = _git("merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD")
    return done.returncode == 0


def head_drift(path, env=None):
    """Paths that differ between HEAD and index/worktree for this path."""
    done = _git("diff", "HEAD", "--name-only", "--", path, env=env)
    return [line.replace("\\", "/")
            for line in done.stdout.decode("utf-8", "replace").splitlines()
            if line.strip()]


def load_json_bytes(raw, source):
    def reject_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("duplicate JSON key %r in %s" % (key, source))
            seen[key] = value
        return seen

    def reject_constant(value):
        raise ValueError("non-finite JSON constant %r in %s" % (value, source))

    return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates,
                      parse_constant=reject_constant)


def load_ledger(path=LEDGER_PATH):
    return load_json_bytes(Path(path).read_bytes(), str(path))


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #
# These top-level blocks legitimately enumerate the package paths: they state the
# rule that no external record may live inside it, so they are not scanned.
NON_SCANNED_TOP_LEVEL_KEYS = frozenset({"promotion_requirements", "validation"})


def _is_nonfinite(value):
    return isinstance(value, float) and not math.isfinite(value)


def _walk_strings(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            for found in _walk_strings(item, path + (str(key),)):
                yield found
    elif isinstance(value, list):
        for position, item in enumerate(value):
            for found in _walk_strings(item, path + (str(position),)):
                yield found
    elif isinstance(value, str):
        yield path, value
    elif _is_nonfinite(value):
        yield path, value


def _provenance_strings(slot):
    """Yield (path, value) for the provenance-bearing string fields of a slot."""
    for outer, inner in SCANNED_STRING_PATHS:
        value = slot.get(outer, {}).get(inner) if isinstance(slot.get(outer), dict) else None
        if isinstance(value, str):
            yield (outer, inner), value


def _forbidden_hits(text):
    lowered = text.lower()
    return [class_id for class_id, markers in FORBIDDEN_MARKERS.items()
            if any(marker in lowered for marker in markers)]


def _norm_text(text):
    """Case- and separator-normalized comparison text for free-form provenance."""
    return str(text).replace("\\", "/").casefold()


def _package_self_reference(text):
    """Hits when free text names this slice's own package files.

    Comparison is case-insensitive and separator-insensitive (Windows accepts both
    separators and is case-insensitive on disk), so a spelling such as
    ``VALIDATION\\TEST_E0_BUDGET_APPROVAL_PROVENANCE.PY`` is the same self-reference
    as the frozen spelling.
    """
    normalized = _norm_text(text)
    hits = []
    for package_path in PACKAGE_PATHS:
        if package_path.casefold() in normalized \
                or Path(package_path).name.casefold() in normalized:
            hits.append(package_path)
    return hits


def _coordination_self_reference(text):
    """Hits when free text names a coordination directory path segment.

    Structural and case-insensitive: ``coordination`` must be a whole path segment,
    bounded by a separator or by the ends of a path-like token.  A longer segment
    (``coordinationish``, ``my-coordination``, ``coordination-notes``) is a different
    path class and is not a hit, which is why the boundary check exists instead of a
    substring test.
    """
    normalized = _norm_text(text)
    if "/" not in normalized:
        return []
    if re.search(r"(?:^|[^0-9a-z_-])coordination(?:[^0-9a-z_-]|$)", normalized):
        return [COORDINATION_DIR_REL + " (case-insensitive segment)"]
    return []


def _self_referential(text):
    """Self-reference hits for provenance-bearing free text (slot fields)."""
    return _package_self_reference(text) + _coordination_self_reference(text)


def _path_segments(path):
    """Return ``(segments, reason)`` for a repository-relative path.

    Separators are unified, empty segments collapse, ``.`` segments are dropped and
    ``..`` is rejected, so the comparison below sees path *segments* rather than a
    particular spelling.  ``reason`` is None when the path is well formed.
    """
    if not isinstance(path, str) or not path.strip():
        return [], "path must be a non-empty string"
    text = path.replace("\\", "/").strip()
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        return [], "path must be repository-relative"
    segments = []
    for part in text.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return [], "path must not contain a parent-directory segment"
        segments.append(part)
    if not segments:
        return [], "path must name at least one segment"
    return segments, None


def _fold_segment(segment):
    """Comparison key for one path segment.

    Unicode case-folded (``str.casefold``), and with trailing dots/spaces trimmed:
    Windows strips those from an on-disk component name, so ``Coordination.`` and
    ``Coordination `` name the same directory as ``coordination`` there and must not
    become a different path class.  ``casefold`` is the Unicode mapping, not an
    ASCII-only ``lower`` table (long s ``\\u017f`` folds to ``s``).
    """
    return segment.rstrip(". ").casefold()


def _folded_segments(segments):
    return [_fold_segment(segment) for segment in segments]


def _external_record_location_defect(path):
    """Return ``(token, reason)`` when `path` is not an admissible location for an
    external owner/derivation record, or None when it is admissible.

    Structural path-class rule; no directory name is hard-coded, and every segment
    comparison is case-folded **after** slash normalization and dot-segment handling
    (see ``_path_segments`` / ``_fold_segment``).  Case folding is required because
    the rule describes a path *class*: on Windows ``validation/COORDINATION/x`` is the
    same directory as ``validation/coordination/x``, and the ledger documents the
    class, not one spelling.  The rule rejects:

    * repository-relative only (no absolute path, no drive letter);
    * no parent-directory traversal;
    * never one of this slice's package files (ledger / plan / test), compared
      case-insensitively as a whole path;
    * never any path whose segments contain a ``coordination`` segment, at any depth,
      under any directory name or casing -- including the independent review and
      repair directories of this slice, which are provenance, not evidence.  The location
  rule is a path *class*: separators are unified, dot segments are handled, and every
  segment is case-folded before comparison, so `validation/COORDINATION/**`,
  `validation/Coordination/**` and backslash spellings are the same class as
  `validation/coordination/**` on Windows and on Linux.  Only whole-segment equality
  counts, so `coordinationish` and `my-coordination` stay a different class, and
  frozen input pins stay a separate allowed class (admitted by id/path/sha256 against
  HEAD, never by location).

    Non-segment prefixes stay legitimate: ``coordinationish`` and
    ``my-coordination`` are single different segments, so they are a different class.
    Frozen input pins are also a different class and are not judged here at all: they
    are admitted by pin id/path/sha256 against HEAD.
    """
    segments, reason = _path_segments(path)
    if reason is not None:
        return (LOCATION_VIOLATION_TOKEN, reason)
    folded = _folded_segments(segments)
    if "/".join(folded) in PACKAGE_PATHS_FOLDED:
        return ("self_referential_evidence",
                "path is this slice package (ledger/plan/test)")
    if COORDINATION_SEGMENT in folded:
        return (LOCATION_VIOLATION_TOKEN,
                "path lies inside a %s directory (case-insensitive segment "
                "comparison after separator and dot-segment normalization)"
                % COORDINATION_DIR_REL)
    return None


def validate(ledger, check_git=True):
    """Return a list of violation strings; empty means the ledger is admitted.

    An admitted ledger is a *blocked* ledger: no budget value, no approval and no
    acceptance claim can survive this function.
    """
    violations = []

    def fail(token, message):
        violations.append("%s: %s" % (token, message))

    # ---- top level -------------------------------------------------------- #
    if not isinstance(ledger, dict):
        return ["not_an_object: ledger root must be a JSON object"]
    keys = set(ledger)
    for missing in sorted(EXPECTED_TOP_KEYS - keys):
        fail("missing_required_key", "top level missing %s" % missing)
    for extra in sorted(keys - EXPECTED_TOP_KEYS):
        fail("unknown_top_level_key", "top level unknown key %s" % extra)

    # The advertised closed sets must agree with the frozen ones elementwise: a
    # ledger that drops a declared sub-field cannot shrink the check.
    declared_slot_fields = ledger.get("required_slot_fields")
    if not isinstance(declared_slot_fields, list):
        fail("missing_required_key", "required_slot_fields must be a list")
    elif set(declared_slot_fields) != set(REQUIRED_SLOT_KEYS) \
            or len(declared_slot_fields) != len(REQUIRED_SLOT_KEYS):
        fail("missing_required_key",
             "required_slot_fields %r does not match the frozen slot field set"
             % (declared_slot_fields,))
    declared_subfields = ledger.get("required_subfields")
    if not isinstance(declared_subfields, dict):
        fail("missing_required_key", "required_subfields must be an object")
    else:
        for block in sorted(set(FROZEN_SUBFIELDS) | set(declared_subfields)):
            frozen_fields = FROZEN_SUBFIELDS.get(block)
            declared_fields = declared_subfields.get(block)
            if frozen_fields is None or not isinstance(declared_fields, list) \
                    or list(declared_fields) != list(frozen_fields):
                fail("missing_required_key",
                     "required_subfields.%s is %r, frozen set is %r"
                     % (block, declared_fields, list(frozen_fields or ())))

    for flag in ("budget_approved", "g6_acceptance", "physical_accuracy",
                 "issues_closed", "owner_decisions_made", "effective"):
        if ledger.get(flag) is not False:
            fail("acceptance_flag_true", "%s must be exactly false, got %r"
                 % (flag, ledger.get(flag)))
    if ledger.get("r1_status") != "numerical_failed":
        fail("r1_status_changed", "r1_status must be numerical_failed, got %r"
             % (ledger.get("r1_status"),))
    if ledger.get("issue") != 59 or ledger.get("parent_issue") != 10:
        fail("identity_mismatch", "issue/parent_issue must be 59/10")

    for path, value in _walk_strings(ledger):
        if _is_nonfinite(value):
            fail("nonfinite_value", "non-finite number at %s" % (".".join(path),))
        elif path and path[0] not in NON_SCANNED_TOP_LEVEL_KEYS \
                and _package_self_reference(value):
            fail("self_referential_evidence",
                 "ledger field %s references this package" % (".".join(path),))
    def admit_external_records(records, kind):
        admitted = set()
        if records is None:
            return admitted
        if not isinstance(records, list):
            fail("missing_required_key", "%s must be a list" % kind)
            return admitted
        for record in records:
            if not isinstance(record, dict):
                fail("approval_without_external_record",
                     "%s entries must be objects" % kind)
                continue
            rec_id = record.get("id")
            path = record.get("path")
            digest = record.get("sha256")
            if not rec_id or not isinstance(path, str) or not isinstance(digest, str):
                fail("approval_without_external_record",
                     "%s %r is missing id/path/sha256" % (kind, rec_id))
                continue
            defect = _external_record_location_defect(path)
            if defect is not None:
                token, reason = defect
                fail(token, "%s %s path %r is not admissible: %s"
                     % (kind, rec_id, path, reason))
                continue
            if check_git:
                blob = head_blob(path)
                if blob is None:
                    fail("pin_untracked_or_staged_only",
                         "%s %s path %s is not a HEAD blob "
                         "(untracked or staged-only)" % (kind, rec_id, path))
                    continue
                if hashlib.sha256(blob).hexdigest() != digest:
                    fail("pin_hash_mismatch",
                         "%s %s HEAD blob hash differs from the declared sha256"
                         % (kind, rec_id))
                    continue
                drift = head_drift(path)
                if drift:
                    fail("pin_head_drift",
                         "%s %s path %s differs from HEAD: %s"
                         % (kind, rec_id, path, drift))
                    continue
            admitted.add(rec_id)
        return admitted

    pinned_owner_ids = admit_external_records(
        ledger.get("external_owner_records"), "external_owner_records")
    pinned_derivation_ids = admit_external_records(
        ledger.get("external_derivation_records"), "external_derivation_records")

    # ---- pins ------------------------------------------------------------- #
    pins = ledger.get("pins")
    if not isinstance(pins, dict):
        fail("pin_missing_or_substituted", "pins must be an object")
        pins = {}
    else:
        for pin_id in sorted(set(PIN_PATHS) - set(pins)):
            fail("pin_missing_or_substituted", "missing pin %s" % pin_id)
        for pin_id in sorted(set(pins) - set(PIN_PATHS)):
            fail("pin_missing_or_substituted", "unknown pin id %s" % pin_id)
        for pin_id, pin in sorted(pins.items()):
            if not isinstance(pin, dict):
                fail("pin_missing_or_substituted", "pin %s must be an object" % pin_id)
                continue
            expected_path = PIN_PATHS.get(pin_id)
            declared_path = pin.get("path")
            if declared_path != expected_path:
                fail("pin_missing_or_substituted",
                     "pin %s path is %r, frozen mapping requires %r"
                     % (pin_id, declared_path, expected_path))
            if pin.get("id") != pin_id:
                fail("pin_missing_or_substituted", "pin %s id field is %r"
                     % (pin_id, pin.get("id")))
            if pin.get("tracked_at_head") is not True:
                fail("pin_untracked_or_staged_only",
                     "pin %s declares tracked_at_head=%r" % (pin_id, pin.get("tracked_at_head")))
            declared = pin.get("sha256")
            if declared != PIN_SHA256.get(pin_id):
                fail("pin_hash_mismatch", "pin %s sha256 is %r, frozen value is %r"
                     % (pin_id, declared, PIN_SHA256.get(pin_id)))
            if check_git:
                if isinstance(declared_path, str) and not tracked_at_head(declared_path):
                    fail("pin_untracked_or_staged_only",
                         "pin %s declares path %s which is not tracked at HEAD"
                         % (pin_id, declared_path))
                if expected_path is not None:
                    if not tracked_at_head(expected_path):
                        fail("pin_untracked_or_staged_only",
                             "pin %s path %s is not tracked at HEAD" % (pin_id, expected_path))
                    else:
                        if head_sha256(expected_path) != PIN_SHA256.get(pin_id):
                            fail("pin_hash_mismatch",
                                 "pin %s HEAD blob hash differs from the frozen value" % pin_id)
                        drift = head_drift(expected_path)
                        if drift:
                            fail("pin_head_drift", "pin %s path %s differs from HEAD: %s"
                                 % (pin_id, expected_path, drift))

    # SOURCE_HEAD object/ancestor probes belong to check_git=True only.
    # check_git=False remains a structural path: related triples, declarations
    # and location class are still judged; missing/non-ancestor SOURCE_HEAD is not.
    if check_git:
        if not source_head_commit_exists():
            fail(SOURCE_HEAD_VIOLATION_TOKEN,
                 "SOURCE_HEAD %s is missing or is not a commit object"
                 % SOURCE_HEAD)
        elif not source_head_is_ancestor_of_head():
            fail(SOURCE_HEAD_VIOLATION_TOKEN,
                 "SOURCE_HEAD %s is not an ancestor of HEAD" % SOURCE_HEAD)

    related = ledger.get("related_artifacts", [])
    if not isinstance(related, list):
        fail("missing_required_key", "related_artifacts must be a list")
        related = []
    related_ids = []
    related_paths = []
    related_triples = []
    for artifact in related:
        if not isinstance(artifact, dict):
            fail("unknown_top_level_key", "related_artifacts entries must be objects")
            continue
        extra = sorted(set(artifact) - set(RELATED_REQUIRED_KEYS))
        if extra:
            fail("unknown_top_level_key",
                 "related artifact %s has unknown keys %s"
                 % (artifact.get("id"), extra))
        for key in RELATED_REQUIRED_KEYS:
            if key not in artifact:
                fail("missing_required_key",
                     "related artifact %s missing %s" % (artifact.get("id"), key))
        art_id = artifact.get("id")
        art_path = artifact.get("path")
        art_sha = artifact.get("sha256")
        related_ids.append(art_id)
        related_paths.append(art_path)
        related_triples.append((art_id, art_path, art_sha))
        if art_id in PIN_PATHS:
            fail("pin_untracked_or_staged_only",
                 "related artifact %s must not occupy a pin id" % art_id)
        if art_path == FRAME_CANDIDATE_REL or art_sha == STALE_FRAME_RELATED_SHA256:
            fail("pin_untracked_or_staged_only",
                 "related artifact %s must not name or hash the frame candidate; "
                 "stale path/hash pairs are misleading and later tracking is not a pin"
                 % art_id)
        if artifact.get("tracked_at_source_head") is not False:
            fail("pin_untracked_or_staged_only",
                 "related artifact %s must be declared untracked at source pin %s"
                 % (art_id, SOURCE_HEAD))
        if "tracked_at_head" in artifact:
            fail("unknown_top_level_key",
                 "related artifact %s must not claim current-HEAD tracking"
                 % art_id)
        frozen_path = RELATED_ARTIFACT_PATHS.get(art_id)
        frozen_sha = RELATED_ARTIFACT_SHA256.get(art_id)
        if frozen_path is None or frozen_sha is None:
            fail(RELATED_ARTIFACT_MISMATCH_TOKEN,
                 "related artifact id %r is not in the frozen triple table" % art_id)
        else:
            if art_path != frozen_path:
                fail(RELATED_ARTIFACT_MISMATCH_TOKEN,
                     "related artifact %s path is %r, frozen path is %r"
                     % (art_id, art_path, frozen_path))
            if art_sha != frozen_sha:
                fail(RELATED_ARTIFACT_MISMATCH_TOKEN,
                     "related artifact %s sha256 is %r, frozen sha256 is %r"
                     % (art_id, art_sha, frozen_sha))
        if check_git and isinstance(art_path, str) and tracked_at_source_head(art_path):
            fail("pin_untracked_or_staged_only",
                 "related artifact %s is tracked at source pin %s"
                 % (art_id, SOURCE_HEAD))
    expected_ids = [row[0] for row in RELATED_ARTIFACTS]
    if related_triples != list(RELATED_ARTIFACTS):
        fail(RELATED_ARTIFACT_MISMATCH_TOKEN,
             "related_artifacts id/path/sha256 triples are %r, frozen sequence is %r"
             % (related_triples, list(RELATED_ARTIFACTS)))
    seen_ids = []
    seen_paths = []
    for art_id, art_path, _sha in related_triples:
        if art_id in seen_ids:
            fail(RELATED_ARTIFACT_MISMATCH_TOKEN,
                 "duplicate related artifact id %r" % art_id)
        seen_ids.append(art_id)
        if isinstance(art_path, str) and art_path in seen_paths:
            fail(RELATED_ARTIFACT_MISMATCH_TOKEN,
                 "duplicate related artifact path %r" % art_path)
        if isinstance(art_path, str):
            seen_paths.append(art_path)
    if related_ids != expected_ids:
        fail(RELATED_ARTIFACT_MISMATCH_TOKEN,
             "related_artifacts ids are %r, frozen sequence is %r"
             % (related_ids, expected_ids))
    record_paths = [record.get("path") for record in ledger.get("external_owner_records", [])
                    if isinstance(record, dict)]
    record_paths += [record.get("path") for record in ledger.get("external_derivation_records", [])
                     if isinstance(record, dict)]
    for path in record_paths:
        defect = _external_record_location_defect(path)
        if defect is not None:
            token, reason = defect
            fail(token, "external record path %r is not admissible: %s" % (path, reason))

    # ---- forbidden classes and loophole rules ----------------------------- #
    declared_classes = ledger.get("forbidden_provenance_classes")
    if not isinstance(declared_classes, list):
        fail("missing_required_key", "forbidden_provenance_classes must be a list")
    else:
        declared_ids = {item.get("id") for item in declared_classes
                        if isinstance(item, dict)}
        for missing in sorted(EXPECTED_FORBIDDEN_IDS - declared_ids):
            fail("forbidden_provenance_class",
                 "forbidden provenance class %s is not declared" % missing)
        for item in declared_classes:
            if not isinstance(item, dict):
                continue
            if not item.get("markers") or not item.get("why") or not item.get("authority"):
                fail("forbidden_provenance_class",
                     "forbidden provenance class %s is incomplete" % item.get("id"))
    declared_loopholes = ledger.get("loophole_rules")
    if not isinstance(declared_loopholes, list):
        fail("missing_required_key", "loophole_rules must be a list")
    else:
        declared_ids = {item.get("id") for item in declared_loopholes if isinstance(item, dict)}
        for missing in sorted(EXPECTED_LOOPHOLE_IDS - declared_ids):
            fail("forbidden_provenance_class", "loophole rule %s is not declared" % missing)

    # ---- slots ------------------------------------------------------------ #
    slots = ledger.get("slots")
    if not isinstance(slots, list):
        fail("slot_count_not_120", "slots must be a list")
        return violations
    if len(slots) != 120:
        fail("slot_count_not_120", "slots has %d entries, must be 120" % len(slots))
    seen = set()
    policy_seen = 0
    dynamic_seen = 0
    numeric_budgets = 0
    approval_identity = 0
    for position, slot in enumerate(slots):
        label = slot.get("slot_id", "#%d" % position) if isinstance(slot, dict) else "#%d" % position
        if not isinstance(slot, dict):
            fail("missing_required_key", "slot %s must be an object" % label)
            continue
        slot_keys = set(slot)
        for missing in sorted(REQUIRED_SLOT_KEYS - slot_keys):
            fail("missing_required_key", "slot %s missing %s" % (label, missing))
        for extra in sorted(slot_keys - REQUIRED_SLOT_KEYS):
            fail("unknown_slot_key", "slot %s unknown key %s" % (label, extra))
        slot_id = slot.get("slot_id")
        if slot_id in seen:
            fail("duplicate_slot", "slot %s appears twice" % slot_id)
        seen.add(slot_id)
        frozen = FROZEN_SLOTS.get(slot_id)
        if frozen is None:
            fail("slot_set_mismatch", "slot %s is not in the frozen 120-slot set" % slot_id)
            continue
        array, index, observable, semantic, partition, policy_class = frozen
        if (slot.get("array"), slot.get("index"), slot.get("observable"),
                slot.get("semantic_status"), slot.get("partition"),
                slot.get("policy_class")) != (array, index, observable, semantic,
                                              partition, policy_class):
            fail("slot_set_mismatch", "slot %s does not match the frozen tuple %r"
                 % (slot_id, frozen))

        status = slot.get("status")
        if status not in STATUS_VOCABULARY:
            fail("status_vocabulary_violation", "slot %s status %r is not admitted"
                 % (slot_id, status))
        if partition == "policy_slot":
            policy_seen += 1
            if status != "pending_owner_policy":
                fail("policy_slot_dropped",
                     "policy slot %s must stay pending_owner_policy, got %r"
                     % (slot_id, status))
                if status == "approved" or (slot.get("approval") or {}).get("state") in (
                        "made", "approved"):
                    fail("policy_slot_auto_approved",
                         "policy slot %s must not be auto-approved" % slot_id)
        else:
            dynamic_seen += 1
            if status != "blocked":
                fail("status_vocabulary_violation",
                     "dynamic slot %s must stay blocked, got %r" % (slot_id, status))

        # ---- closed sub-blocks: exact keys, vocabularies, L2/L3 gates ------- #
        for block_name in sorted(FROZEN_SUBFIELDS):
            block = slot.get(block_name)
            if not isinstance(block, dict):
                fail("missing_required_key",
                     "slot %s %s must be an object" % (slot_id, block_name))
                continue
            allowed = set(FROZEN_SUBFIELDS[block_name])
            for extra in sorted(set(block) - allowed):
                fail("unknown_slot_key",
                     "slot %s %s has undeclared sub-key %s"
                     % (slot_id, block_name, extra))
            for absent in sorted(allowed - set(block)):
                fail("missing_required_key",
                     "slot %s %s missing sub-key %s" % (slot_id, block_name, absent))
            if "status" in allowed and block.get("status") not in SUBBLOCK_STATUS_VOCABULARY:
                fail("status_vocabulary_violation",
                     "slot %s %s.status %r is not admitted"
                     % (slot_id, block_name, block.get("status")))
        source_identity = slot.get("source_identity") \
            if isinstance(slot.get("source_identity"), dict) else {}
        mapping = source_identity.get("committed_source_mapping")
        if isinstance(mapping, dict):
            for extra in sorted(set(mapping) - SOURCE_MAPPING_KEYS):
                fail("unknown_slot_key",
                     "slot %s source_identity.committed_source_mapping has undeclared key %s"
                     % (slot_id, extra))
            for absent in sorted(SOURCE_MAPPING_KEYS - set(mapping)):
                fail("missing_required_key",
                     "slot %s source_identity.committed_source_mapping missing %s"
                     % (slot_id, absent))
        elif mapping is not None:
            fail("unknown_slot_key",
                 "slot %s source_identity.committed_source_mapping must be an object"
                 % slot_id)
        for block_name in BLOCKED_ONLY_SUBBLOCKS:
            block = slot.get(block_name)
            if isinstance(block, dict) and block.get("status") != "blocked":
                fail("status_vocabulary_violation",
                     "slot %s %s.status must stay blocked, got %r"
                     % (slot_id, block_name, block.get("status")))
        frame_datum = slot.get("frame_datum") \
            if isinstance(slot.get("frame_datum"), dict) else {}
        if frame_datum.get("status") != status:
            fail("status_vocabulary_violation",
                 "slot %s frame_datum.status %r must follow the slot status %r"
                 % (slot_id, frame_datum.get("status"), status))
        unit_source = source_identity.get("native_unit_source")
        if isinstance(unit_source, str) and unit_source.startswith("pin:") \
                and unit_source[len("pin:"):] not in PIN_PATHS:
            fail("unknown_slot_key",
                 "slot %s native_unit_source names unknown pin %r" % (slot_id, unit_source))

        metric = slot.get("metric") or {}
        if metric.get("frozen_metric") != FROZEN_METRIC:
            fail("unknown_slot_key", "slot %s metric is %r, must be the frozen %r"
                 % (slot_id, metric.get("frozen_metric"), FROZEN_METRIC))
        if metric.get("equivalence_class_required") is True:
            if metric.get("equivalence_owner_input") not in OWNER_INPUT_VOCABULARY:
                fail("unknown_slot_key",
                     "slot %s equivalence_owner_input %r is not an owner input id"
                     % (slot_id, metric.get("equivalence_owner_input")))
        elif metric.get("equivalence_class_required") is not False:
            fail("unknown_slot_key",
                 "slot %s metric.equivalence_class_required must be a boolean, got %r"
                 % (slot_id, metric.get("equivalence_class_required")))
        elif metric.get("equivalence_owner_input") is not None:
            fail("unknown_slot_key",
                 "slot %s equivalence_owner_input is set while equivalence_class_required "
                 "is false" % slot_id)

        budgets = slot.get("budgets") or {}
        for field in BUDGET_FIELDS:
            value = budgets.get(field)
            if value is None:
                continue
            numeric_budgets += 1
            fail("numeric_budget_present",
                 "slot %s carries %s=%r without a pinned derivation and an owner approval"
                 % (slot_id, field, value))
            if not isinstance(value, (int, float)) or isinstance(value, bool) \
                    or not math.isfinite(value) or value < 0:
                fail("nonfinite_value", "slot %s %s is not a finite non-negative number"
                     % (slot_id, field))

        approval = slot.get("approval") or {}
        state = approval.get("state")
        if state not in APPROVAL_STATE_VOCABULARY:
            fail("bare_approval_claim", "slot %s approval.state %r is not admitted"
                 % (slot_id, state))
        identity_fields = ("decision_id", "approver", "decided_utc",
                           "decision_text_digest", "decision_ref")
        present = [field for field in identity_fields if approval.get(field) is not None]
        if present:
            approval_identity += 1
            fail("approval_identity_present",
                 "slot %s carries approval identity fields %s; this ledger admits none"
                 % (slot_id, present))
        if state != "not_made" or present or approval.get("external_record_pinned"):
            decision_ref = approval.get("decision_ref")
            if decision_ref not in pinned_owner_ids or not approval.get("external_record_pinned"):
                fail("approval_without_external_record",
                     "slot %s claims approval state=%r fields=%s without a pinned external "
                     "owner record; editing this ledger is not an approval"
                     % (slot_id, state, present))
            for field in ("approver", "decided_utc", "decision_text_digest"):
                if approval.get(field) is None:
                    fail("approval_without_external_record",
                         "slot %s approval.%s is missing" % (slot_id, field))
            digest = approval.get("decision_text_digest")
            if isinstance(digest, str) and (len(digest) != 64
                                            or any(char not in "0123456789abcdef" for char in digest)):
                fail("approval_without_external_record",
                     "slot %s decision_text_digest is not 64 lowercase hex chars" % slot_id)

        derivation = slot.get("derivation") or {}
        derivation_ref = derivation.get("ref")
        if derivation.get("required") not in (True, False):
            fail("unknown_slot_key",
                 "slot %s derivation.required must be a boolean, got %r"
                 % (slot_id, derivation.get("required")))
        if derivation_ref is not None and derivation_ref not in pinned_derivation_ids:
            fail("derivation_without_external_record",
                 "slot %s derivation.ref %r is not a pinned external derivation record"
                 % (slot_id, derivation_ref))
        # Loophole rule L2: free-text derivation and domain.  A class name or a
        # prose domain is an assertion, not evidence, and only a pinned external
        # derivation record can carry it.
        if derivation.get("derivation_class") is not None \
                and derivation_ref not in pinned_derivation_ids:
            fail("derivation_without_external_record",
                 "slot %s derivation.derivation_class %r has no derivation.ref naming a "
                 "pinned external derivation record (loophole rule L2)"
                 % (slot_id, derivation.get("derivation_class")))
        if derivation.get("forbidden_class") is not None:
            fail("forbidden_provenance_class",
                 "slot %s derivation.forbidden_class %r is non-null; a blocked ledger "
                 "admits no forbidden provenance class"
                 % (slot_id, derivation.get("forbidden_class")))
        declared_domain = (slot.get("domain") or {}).get("declared_domain")
        if declared_domain is not None and derivation_ref not in pinned_derivation_ids:
            fail("derivation_without_external_record",
                 "slot %s domain.declared_domain %r has no derivation.ref naming a pinned "
                 "external derivation record (loophole rule L2)"
                 % (slot_id, declared_domain))
        # Loophole rule L3: free-text frame/datum.  The frame and the datum are an
        # owner decision, so they require a pinned external owner record.
        frame = frame_datum.get("frame")
        datum = frame_datum.get("datum")
        if frame is not None or datum is not None:
            decision_ref = approval.get("decision_ref")
            if decision_ref not in pinned_owner_ids \
                    or approval.get("external_record_pinned") is not True:
                fail("approval_without_external_record",
                     "slot %s asserts frame_datum.frame=%r datum=%r without an owner "
                     "decision recorded in a pinned external owner record "
                     "(loophole rule L3)" % (slot_id, frame, datum))

        for where, text in _provenance_strings(slot):
            for class_id in _forbidden_hits(text):
                fail("forbidden_provenance_class",
                     "slot %s field %s matches forbidden class %s"
                     % (slot_id, ".".join(where), class_id))
                if class_id == "RD-07":
                    fail("placeholder_value",
                         "slot %s field %s is a placeholder" % (slot_id, ".".join(where)))
            for hit in _self_referential(text):
                fail("self_referential_evidence",
                     "slot %s field %s references this package (%s)"
                     % (slot_id, ".".join(where), hit))

        for field in ("source_identity", "domain", "frame_datum", "derivation", "approval"):
            block = slot.get(field)
            if isinstance(block, dict) and "evidence_class" in block:
                if block["evidence_class"] not in EVIDENCE_CLASS_VOCABULARY:
                    fail("unknown_slot_key", "slot %s %s evidence_class %r is not admitted"
                         % (slot_id, field, block["evidence_class"]))
        resolution = (slot.get("source_identity") or {}).get("committed_source_mapping", {})
        if isinstance(resolution, dict) and \
                resolution.get("rhs_resolution_status") not in RESOLUTION_VOCABULARY:
            fail("unknown_slot_key", "slot %s rhs_resolution_status %r is not admitted"
                 % (slot_id, resolution.get("rhs_resolution_status")))
        for owner_input in slot.get("owner_inputs", []):
            if owner_input not in OWNER_INPUT_VOCABULARY:
                fail("unknown_slot_key", "slot %s owner_input %r is not admitted"
                     % (slot_id, owner_input))

    if len(seen) != len(slots):
        fail("duplicate_slot", "slot ids are not unique")
    if policy_seen != 64:
        fail("policy_slot_dropped", "policy slots counted %d, must be 64" % policy_seen)
    if dynamic_seen != 56:
        fail("slot_count_not_120", "dynamic candidate slots counted %d, must be 56"
             % dynamic_seen)

    # ---- slot set summary must agree with the slot list ------------------- #
    array_counts = {}
    interface_seen = 0
    reserved_seen = 0
    rhs_counts = {"terminal": 0, "local_bound": 0, "unresolved": 0}
    frame_bound = 0
    datum_bound = 0
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        array_counts[slot.get("array")] = array_counts.get(slot.get("array"), 0) + 1
        if slot.get("policy_class") == "interface_metadata":
            interface_seen += 1
        elif slot.get("policy_class") == "reserved_not_physical_coverage":
            reserved_seen += 1
        if slot.get("partition") == "dynamic_candidate":
            mapping = (slot.get("source_identity") or {}).get("committed_source_mapping")
            resolution = mapping.get("rhs_resolution_status") if isinstance(mapping, dict) else None
            if resolution in rhs_counts:
                rhs_counts[resolution] += 1
            frame_row = slot.get("frame_datum") if isinstance(slot.get("frame_datum"), dict) else {}
            if frame_row.get("frame") is not None:
                frame_bound += 1
            if frame_row.get("datum") is not None:
                datum_bound += 1

    slot_set = ledger.get("slot_set")
    if not isinstance(slot_set, dict):
        fail("slot_set_mismatch", "slot_set must be an object")
    else:
        expected_slot_set = {
            "total_slots": len(slots),
            "dynamic_candidate_slots": dynamic_seen,
            "policy_slots": policy_seen,
            "policy_interface_metadata": interface_seen,
            "policy_reserved_not_physical_coverage": reserved_seen,
            "arrays": array_counts,
        }
        for extra in sorted(set(slot_set) - SLOT_SET_KEYS):
            fail("slot_set_mismatch", "slot_set has unknown key %s" % extra)
        for missing in sorted(SLOT_SET_KEYS - set(slot_set)):
            fail("slot_set_mismatch", "slot_set missing key %s" % missing)
        for key, value in sorted(expected_slot_set.items()):
            if slot_set.get(key) != value:
                fail("slot_set_mismatch", "slot_set.%s is %r, recomputed %r"
                     % (key, slot_set.get(key), value))
        if not isinstance(slot_set.get("partition_rule"), str) \
                or not slot_set.get("partition_rule", "").strip():
            fail("slot_set_mismatch", "slot_set.partition_rule must be a non-empty string")

    counts = ledger.get("counts")
    if isinstance(counts, dict):
        expected = {
            "slots_total": len(slots),
            "slots_dynamic_candidate": dynamic_seen,
            "slots_policy": policy_seen,
            "slots_with_numeric_budget": numeric_budgets,
            "slots_with_approval_identity": approval_identity,
            "slots_approved": 0,
            "slots_blocked": sum(1 for slot in slots if slot.get("status") == "blocked"),
            "slots_pending_owner_policy": sum(
                1 for slot in slots if slot.get("status") == "pending_owner_policy"),
            "dynamic_rhs_resolution": dict(rhs_counts),
            "dynamic_slots_with_committed_frame_binding": frame_bound,
            "dynamic_slots_with_committed_datum_binding": datum_bound,
            "external_owner_records": len(ledger.get("external_owner_records", [])),
            "external_derivation_records": len(ledger.get("external_derivation_records", [])),
        }
        for extra in sorted(set(counts) - set(expected)):
            fail("counts_mismatch", "counts has unknown key %s" % extra)
        for missing in sorted(set(expected) - set(counts)):
            fail("counts_mismatch", "counts missing key %s" % missing)
        for key, value in sorted(expected.items()):
            if counts.get(key) != value:
                fail("counts_mismatch", "counts.%s is %r, recomputed %r"
                     % (key, counts.get(key), value))
    else:
        fail("missing_required_key", "counts must be an object")

    promotion = ledger.get("promotion_requirements")
    if not isinstance(promotion, dict) or not promotion.get("rule"):
        fail("missing_required_key", "promotion_requirements.rule is required")
    return violations


def violations_text(violations):
    return "; ".join(violations)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
class FrozenInputTests(unittest.TestCase):
    """The frozen pin mapping and slot set must agree with the HEAD blobs."""

    def test_pin_mapping_is_complete_and_consistent(self):
        self.assertEqual(set(PIN_PATHS), set(PIN_SHA256))

    def test_every_pin_is_tracked_at_head_with_frozen_hash(self):
        for pin_id, path in sorted(PIN_PATHS.items()):
            with self.subTest(pin=pin_id):
                shown = _git("show", "HEAD:" + path)
                self.assertEqual(shown.returncode, 0,
                                 "%s (%s) git show HEAD:path failed" % (pin_id, path))
                self.assertEqual(hashlib.sha256(shown.stdout).hexdigest(),
                                 PIN_SHA256[pin_id],
                                 "%s HEAD blob hash drifted" % pin_id)
                self.assertEqual(head_sha256(path), PIN_SHA256[pin_id])

    def test_no_pinned_path_drifts_from_head(self):
        drifted = {}
        for pin_id, path in sorted(PIN_PATHS.items()):
            shown = _git("diff", "HEAD", "--name-only", "--", path)
            names = [line.replace("\\", "/")
                     for line in shown.stdout.decode("utf-8", "replace").splitlines()
                     if line.strip()]
            if names:
                drifted[pin_id] = names
        self.assertEqual({}, drifted, "pinned paths differ from HEAD")

    def test_ledger_head_blob_matches_worktree_when_tracked(self):
        """The ledger may be untracked before commit and should be a HEAD blob after.

        If ``git show HEAD:ledger`` exists, its bytes and sha256 must match the
        working tree and the frozen payload/plan pins.  Absence of the blob is
        allowed only for the still-uncommitted candidate.
        """
        worktree = LEDGER_PATH.read_bytes()
        worktree_hash = hashlib.sha256(worktree).hexdigest()
        plan_bytes = DOC_PATH.read_bytes()
        plan_hash = hashlib.sha256(plan_bytes).hexdigest()
        self.assertEqual(worktree_hash, PACKAGE_SHA256[LEDGER_REL])
        self.assertEqual(plan_hash, PACKAGE_SHA256[DOC_REL])
        ledger = load_ledger()
        for pin_id, pin in ledger["pins"].items():
            self.assertEqual(pin["path"], PIN_PATHS[pin_id], pin_id)
            self.assertEqual(pin["sha256"], PIN_SHA256[pin_id], pin_id)
        plan_text = plan_bytes.decode("utf-8")
        for pin_id, path in PIN_PATHS.items():
            self.assertIn(path, plan_text, pin_id)

        shown = _git("show", "HEAD:" + LEDGER_REL)
        blob = head_blob(LEDGER_REL)
        if shown.returncode != 0:
            self.assertIsNone(blob)
            self.assertFalse(tracked_at_head(LEDGER_REL))
            return
        self.assertEqual(shown.stdout, worktree)
        self.assertEqual(blob, worktree)
        self.assertEqual(hashlib.sha256(shown.stdout).hexdigest(), worktree_hash)
        self.assertEqual(head_sha256(LEDGER_REL), PACKAGE_SHA256[LEDGER_REL])
        plan_blob = head_blob(DOC_REL)
        if plan_blob is not None:
            self.assertEqual(plan_blob, plan_bytes)
            self.assertEqual(hashlib.sha256(plan_blob).hexdigest(),
                             PACKAGE_SHA256[DOC_REL])

    def test_git_diff_head_detects_staged_only_change_in_private_index(self):
        """A private GIT_INDEX_FILE must not mutate the real index.

        Staging a deletion of a pin against HEAD is enough for ``git diff HEAD``
        to name the path; that is the dirty/staged rejection mechanism.
        """
        import os
        import tempfile

        pin_path = PIN_PATHS["r1_contract"]
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
            read = _git("read-tree", "HEAD", env=env)
            self.assertEqual(read.returncode, 0, read.stderr)
            removed = _git("update-index", "--force-remove", "--", pin_path, env=env)
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertIn(pin_path, head_drift(pin_path, env=env))
            real = _git("diff", "--cached", "--name-only", "--", pin_path)
            self.assertEqual(real.stdout.decode("utf-8", "replace").strip(), "",
                             "private index leaked into the real index")

    def test_source_head_is_ancestor_pin_not_current_equality(self):
        """``6eafdf9`` is the source/ancestor pin, not a post-commit HEAD equality."""
        ledger = load_ledger()
        self.assertEqual(ledger["observed_at"]["head"], SOURCE_HEAD)
        self.assertIn(SOURCE_HEAD, DOC_PATH.read_text(encoding="utf-8"))
        done = _git("merge-base", "--is-ancestor", SOURCE_HEAD, "HEAD")
        self.assertEqual(done.returncode, 0,
                         "source pin %s must be an ancestor of HEAD" % SOURCE_HEAD)

    def test_baseline_ancestor_is_ancestor_of_head(self):
        done = _git("merge-base", "--is-ancestor", BASELINE_ANCESTOR, "HEAD")
        self.assertEqual(done.returncode, 0)

    def test_frozen_slot_table_matches_head_contract(self):
        """The frozen 120-slot table is re-derived from the contract and the RHS pins."""
        conformance = load_json_bytes(head_blob(PIN_PATHS["r1_contract"]), "r1_contract")
        rhs = load_json_bytes(head_blob(PIN_PATHS["rhs_references"]), "rhs_references")
        dynamic = {slot["slot"] for slot in rhs["slots"]}
        derived = {}
        for observable in conformance["observables"]:
            for index in observable["indices"]:
                slot_id = "%s[%d]" % (observable["array"], index)
                if slot_id in dynamic:
                    partition, policy_class = "dynamic_candidate", None
                else:
                    partition = "policy_slot"
                    policy_class = observable["semantic_status"]
                derived[slot_id] = (observable["array"], index, observable["id"],
                                    observable["semantic_status"], partition, policy_class)
        self.assertEqual(len(derived), 120)
        self.assertEqual(derived, FROZEN_SLOTS)

    def test_frozen_partition_counts(self):
        dynamic = sum(1 for row in FROZEN_SLOTS.values() if row[4] == "dynamic_candidate")
        policy = sum(1 for row in FROZEN_SLOTS.values() if row[4] == "policy_slot")
        interface = sum(1 for row in FROZEN_SLOTS.values() if row[5] == "interface_metadata")
        reserved = sum(1 for row in FROZEN_SLOTS.values()
                       if row[5] == "reserved_not_physical_coverage")
        self.assertEqual((dynamic, policy, interface, reserved), (56, 64, 5, 59))


class LedgerContractTests(unittest.TestCase):
    def setUp(self):
        self.ledger = load_ledger()

    def test_ledger_validates_clean(self):
        self.assertEqual([], validate(self.ledger), violations_text(validate(self.ledger)))

    def test_top_level_keys_are_exactly_the_frozen_set(self):
        self.assertEqual(set(self.ledger), set(EXPECTED_TOP_KEYS))

    def test_flags_are_fail_closed(self):
        for flag in ("budget_approved", "g6_acceptance", "physical_accuracy",
                     "issues_closed", "owner_decisions_made", "effective"):
            self.assertIs(self.ledger[flag], False, flag)
        self.assertEqual(self.ledger["r1_status"], "numerical_failed")

    def test_slot_order_and_identity_match_the_frozen_set(self):
        self.assertEqual([slot["slot_id"] for slot in self.ledger["slots"]],
                         list(FROZEN_SLOTS))

    def test_partition_counts(self):
        slots = self.ledger["slots"]
        self.assertEqual(len(slots), 120)
        self.assertEqual(sum(1 for s in slots if s["partition"] == "dynamic_candidate"), 56)
        self.assertEqual(sum(1 for s in slots if s["partition"] == "policy_slot"), 64)
        self.assertEqual(sum(1 for s in slots if s["policy_class"] == "interface_metadata"), 5)
        self.assertEqual(sum(1 for s in slots
                             if s["policy_class"] == "reserved_not_physical_coverage"), 59)

    def test_every_slot_has_null_budgets(self):
        for slot in self.ledger["slots"]:
            for field in BUDGET_FIELDS:
                self.assertIsNone(slot["budgets"][field],
                                  "%s %s" % (slot["slot_id"], field))
            self.assertEqual(slot["budgets"]["status"], "blocked")

    def test_every_slot_has_no_approval_identity(self):
        for slot in self.ledger["slots"]:
            approval = slot["approval"]
            self.assertEqual(approval["state"], "not_made", slot["slot_id"])
            for field in ("decision_id", "approver", "decided_utc",
                          "decision_text_digest", "decision_ref"):
                self.assertIsNone(approval[field], "%s %s" % (slot["slot_id"], field))
            self.assertIs(approval["external_record_pinned"], False)

    def test_every_slot_has_null_derivation_and_domain(self):
        for slot in self.ledger["slots"]:
            self.assertIsNone(slot["derivation"]["ref"], slot["slot_id"])
            self.assertIsNone(slot["derivation"]["derivation_class"], slot["slot_id"])
            self.assertIsNone(slot["domain"]["declared_domain"], slot["slot_id"])
            self.assertIsNone(slot["frame_datum"]["frame"], slot["slot_id"])
            self.assertIsNone(slot["frame_datum"]["datum"], slot["slot_id"])

    def test_policy_slots_are_never_approved_or_covered(self):
        for slot in self.ledger["slots"]:
            if slot["partition"] == "policy_slot":
                self.assertEqual(slot["status"], "pending_owner_policy", slot["slot_id"])
                self.assertIn("D-01", slot["owner_inputs"], slot["slot_id"])

    def test_dynamic_slots_are_blocked(self):
        for slot in self.ledger["slots"]:
            if slot["partition"] == "dynamic_candidate":
                self.assertEqual(slot["status"], "blocked", slot["slot_id"])
                self.assertIsNone(slot["policy_class"], slot["slot_id"])

    def test_external_record_lists_are_empty(self):
        self.assertEqual(self.ledger["external_owner_records"], [])
        self.assertEqual(self.ledger["external_derivation_records"], [])

    def test_pins_match_the_frozen_mapping_and_head_blobs(self):
        pins = self.ledger["pins"]
        self.assertEqual(set(pins), set(PIN_PATHS))
        for pin_id, pin in pins.items():
            self.assertEqual(pin["path"], PIN_PATHS[pin_id], pin_id)
            self.assertEqual(pin["sha256"], PIN_SHA256[pin_id], pin_id)
            self.assertIs(pin["tracked_at_head"], True, pin_id)
            self.assertEqual(head_sha256(pin["path"]), pin["sha256"], pin_id)

    def test_related_artifacts_are_untracked_and_are_not_pins(self):
        related = self.ledger["related_artifacts"]
        self.assertTrue(related)
        self.assertEqual([artifact["id"] for artifact in related],
                         list(RELATED_ARTIFACT_PATHS))
        self.assertEqual(
            [(artifact["id"], artifact["path"], artifact["sha256"]) for artifact in related],
            list(RELATED_ARTIFACTS))
        self.assertNotIn("frame_datum_binding_inflight",
                         [artifact["id"] for artifact in related])
        for artifact in related:
            self.assertEqual(set(artifact), set(RELATED_REQUIRED_KEYS), artifact["id"])
            self.assertIs(artifact["tracked_at_source_head"], False, artifact["id"])
            self.assertNotIn("tracked_at_head", artifact, artifact["id"])
            self.assertNotIn(artifact["id"], PIN_PATHS, artifact["id"])
            self.assertEqual(artifact["path"], RELATED_ARTIFACT_PATHS[artifact["id"]],
                             artifact["id"])
            self.assertEqual(artifact["sha256"], RELATED_ARTIFACT_SHA256[artifact["id"]],
                             artifact["id"])
            self.assertNotEqual(artifact["path"], FRAME_CANDIDATE_REL, artifact["id"])
            self.assertNotEqual(artifact["sha256"], STALE_FRAME_RELATED_SHA256,
                                artifact["id"])
            self.assertFalse(tracked_at_source_head(artifact["path"]), artifact["id"])
        self.assertEqual([], validate(self.ledger),
                         "current-HEAD tracking of a sibling path must not fail the ledger")

    def test_forbidden_classes_and_loopholes_are_declared(self):
        declared = {item["id"] for item in self.ledger["forbidden_provenance_classes"]}
        self.assertEqual(declared, EXPECTED_FORBIDDEN_IDS)
        declared = {item["id"] for item in self.ledger["loophole_rules"]}
        self.assertEqual(declared, EXPECTED_LOOPHOLE_IDS)

    def test_promotion_requirements_describe_external_records(self):
        promotion = self.ledger["promotion_requirements"]
        self.assertIn("external_owner_records", promotion["rule"])
        self.assertIn("external_derivation_records", promotion["rule"])
        for field in ("external_owner_record_requirements",
                      "external_derivation_record_requirements",
                      "what_editing_this_ledger_can_never_do",
                      "per_observable_owner_inputs"):
            self.assertTrue(promotion[field], field)

    def test_deliverables_are_lf_normalized(self):
        for path in (LEDGER_PATH, DOC_PATH, TEST_PATH):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                self.assertNotIn(b"\r", raw, "%s contains CR" % path.name)

    def test_no_self_reference_anywhere_in_the_ledger(self):
        """No scanned ledger string may name this slice's own package files.

        The coordination-location rule is a *record* rule: it is enforced on the
        external-record paths and on provenance-bearing slot text, not on the pin
        table (a tracked coordination artifact is a legitimate frozen input pin).
        """
        hits = []
        for path, value in _walk_strings(self.ledger):
            if path and path[0] in NON_SCANNED_TOP_LEVEL_KEYS:
                continue
            if _package_self_reference(value):
                hits.append(".".join(path))
        self.assertEqual([], hits)

    def test_no_slot_provenance_string_names_a_coordination_directory(self):
        hits = []
        for slot in self.ledger["slots"]:
            for where, text in _provenance_strings(slot):
                if _coordination_self_reference(text):
                    hits.append("%s.%s" % (slot["slot_id"], ".".join(where)))
        self.assertEqual([], hits)

    def test_frozen_pin_may_live_in_a_coordination_directory(self):
        """Pins and promotion records are different classes.

        `pin:budget_evidence_audit` is a HEAD-tracked coordination artifact and
        must stay admissible as a frozen input; the same path must never be
        admissible as an external owner/derivation record.
        """
        pin_path = PIN_PATHS["budget_evidence_audit"]
        self.assertEqual(pin_path, self.ledger["pins"]["budget_evidence_audit"]["path"])
        self.assertIn("/coordination/", pin_path)
        token, _ = _external_record_location_defect(pin_path)
        self.assertEqual("external_record_location_violation", token)


class MutationTests(unittest.TestCase):
    """Every dishonest or weakening edit must fail closed."""

    def setUp(self):
        self.ledger = load_ledger()

    def mutate(self, mutator):
        clone = copy.deepcopy(self.ledger)
        mutator(clone)
        return validate(clone)

    def assertRejects(self, violations, token):
        self.assertTrue(any(item.startswith(token + ":") for item in violations),
                        "expected %s in %s" % (token, violations))

    # ---- flags ----------------------------------------------------------- #
    def test_budget_approved_true_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(budget_approved=True)),
                           "acceptance_flag_true")

    def test_g6_acceptance_true_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(g6_acceptance=True)),
                           "acceptance_flag_true")

    def test_physical_accuracy_true_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(physical_accuracy=True)),
                           "acceptance_flag_true")

    def test_issues_closed_true_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(issues_closed=True)),
                           "acceptance_flag_true")

    def test_effective_true_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(effective=True)),
                           "acceptance_flag_true")

    def test_owner_decisions_made_true_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(owner_decisions_made=True)),
                           "acceptance_flag_true")

    def test_r1_status_change_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(r1_status="strict_native_reference_conformance_pass_for_declared_cases_only")),
                           "r1_status_changed")

    def test_unknown_top_level_key_rejected(self):
        self.assertRejects(self.mutate(lambda c: c.update(approval="approved")),
                           "unknown_top_level_key")

    # ---- pins ------------------------------------------------------------ #
    def test_missing_pin_rejected(self):
        self.assertRejects(self.mutate(lambda c: c["pins"].pop("r1_contract")),
                           "pin_missing_or_substituted")

    def test_unknown_pin_rejected(self):
        def add(c):
            c["pins"]["invented"] = {"id": "invented", "path": "docs/plan/README.md",
                                     "sha256": "0" * 64, "tracked_at_head": True}
        self.assertRejects(self.mutate(add), "pin_missing_or_substituted")

    def test_tampered_pin_hash_rejected(self):
        def tamper(c):
            c["pins"]["r1_contract"]["sha256"] = "1" * 64
        self.assertRejects(self.mutate(tamper), "pin_hash_mismatch")

    def test_substituted_pin_path_rejected(self):
        def substitute(c):
            c["pins"]["r1_contract"]["path"] = PIN_PATHS["slot_manifest"]
        self.assertRejects(self.mutate(substitute), "pin_missing_or_substituted")

    def test_pin_declared_untracked_rejected(self):
        def untracked(c):
            c["pins"]["rhs_references"]["tracked_at_head"] = False
        self.assertRejects(self.mutate(untracked), "pin_untracked_or_staged_only")

    def test_untracked_artifact_promoted_into_pins_rejected(self):
        def promote(c):
            artifact = c["related_artifacts"][0]
            c["pins"][artifact["id"]] = {"id": artifact["id"], "path": artifact["path"],
                                         "sha256": artifact["sha256"],
                                         "tracked_at_head": False}
        self.assertRejects(self.mutate(promote), "pin_untracked_or_staged_only")

    def test_related_artifact_cannot_become_owner_or_derivation(self):
        def as_owner(c):
            artifact = c["related_artifacts"][0]
            c["external_owner_records"] = [{
                "id": artifact["id"], "path": artifact["path"],
                "sha256": artifact["sha256"],
            }]
            c["counts"]["external_owner_records"] = 1
        def as_derivation(c):
            artifact = c["related_artifacts"][0]
            c["external_derivation_records"] = [{
                "id": artifact["id"], "path": artifact["path"],
                "sha256": artifact["sha256"],
            }]
            c["counts"]["external_derivation_records"] = 1
        self.assertRejects(self.mutate(as_owner), LOCATION_VIOLATION_TOKEN)
        self.assertRejects(self.mutate(as_derivation), LOCATION_VIOLATION_TOKEN)

    def test_pin_object_with_wrong_id_rejected(self):
        def wrong(c):
            c["pins"]["r1_contract"]["id"] = "slot_manifest"
        self.assertRejects(self.mutate(wrong), "pin_missing_or_substituted")

    def test_related_artifact_declared_tracked_rejected(self):
        def tracked(c):
            c["related_artifacts"][0]["tracked_at_source_head"] = True
        self.assertRejects(self.mutate(tracked), "pin_untracked_or_staged_only")

    def test_related_artifact_current_head_claim_rejected(self):
        def claim(c):
            c["related_artifacts"][0]["tracked_at_head"] = False
        self.assertRejects(self.mutate(claim), "unknown_top_level_key")

    def test_stale_frame_related_artifact_rejected(self):
        def add(c):
            c["related_artifacts"].append({
                "id": "frame_datum_binding_inflight",
                "path": FRAME_CANDIDATE_REL,
                "sha256": STALE_FRAME_RELATED_SHA256,
                "tracked_at_source_head": False,
                "role": "stale misleading frame identity",
            })
        self.assertRejects(self.mutate(add), "pin_untracked_or_staged_only")
        self.assertRejects(self.mutate(add), RELATED_ARTIFACT_MISMATCH_TOKEN)

    # ---- policy slots ----------------------------------------------------- #
    def test_dropping_a_policy_slot_rejected(self):
        def drop(c):
            c["slots"] = [s for s in c["slots"] if s["slot_id"] != "GPS30[29]"]
        self.assertRejects(self.mutate(drop), "policy_slot_dropped")

    def test_dropping_a_dynamic_slot_rejected(self):
        def drop(c):
            c["slots"] = [s for s in c["slots"] if s["slot_id"] != "Vehicle60[3]"]
        self.assertRejects(self.mutate(drop), "slot_count_not_120")

    def test_duplicating_a_policy_row_rejected(self):
        def duplicate(c):
            policy = next(s for s in c["slots"] if s["partition"] == "policy_slot")
            c["slots"].append(copy.deepcopy(policy))
        violations = self.mutate(duplicate)
        self.assertRejects(violations, "duplicate_slot")
        self.assertRejects(violations, "slot_count_not_120")

    def test_auto_approving_a_policy_slot_rejected(self):
        def approve(c):
            for slot in c["slots"]:
                if slot["slot_id"] == "Sensor30[14]":
                    slot["status"] = "approved"
        violations = self.mutate(approve)
        self.assertRejects(violations, "status_vocabulary_violation")
        self.assertRejects(violations, "policy_slot_dropped")

    def test_marking_policy_slot_covered_rejected(self):
        def cover(c):
            for slot in c["slots"]:
                if slot["partition"] == "policy_slot":
                    slot["status"] = "blocked"
                    slot["derivation"]["ref"] = "counts as coverage after budget"
        violations = self.mutate(cover)
        self.assertRejects(violations, "policy_slot_dropped")
        self.assertRejects(violations, "forbidden_provenance_class")

    def test_narrowing_policy_slot_set_rejected(self):
        def narrow(c):
            c["slot_set"]["policy_slots"] = 0
            c["slots"] = [s for s in c["slots"] if s["partition"] == "dynamic_candidate"]
        violations = self.mutate(narrow)
        self.assertRejects(violations, "policy_slot_dropped")
        self.assertRejects(violations, "slot_count_not_120")

    # ---- budgets ---------------------------------------------------------- #
    def test_numeric_budget_rejected(self):
        def fill(c):
            c["slots"][3]["budgets"]["abs_budget"] = 1e-9
            c["slots"][3]["budgets"]["rel_budget"] = 1e-12
            c["slots"][3]["budgets"]["rms_budget"] = 1e-9
        self.assertRejects(self.mutate(fill), "numeric_budget_present")

    def test_zero_budget_rejected(self):
        def fill(c):
            c["slots"][3]["budgets"]["abs_budget"] = 0
        self.assertRejects(self.mutate(fill), "numeric_budget_present")

    def test_nonfinite_budget_rejected(self):
        def fill(c):
            c["slots"][3]["budgets"]["abs_budget"] = float("nan")
        self.assertRejects(self.mutate(fill), "numeric_budget_present")

    def test_negative_budget_rejected(self):
        def fill(c):
            c["slots"][3]["budgets"]["rel_budget"] = -1.0
        self.assertRejects(self.mutate(fill), "numeric_budget_present")

    # ---- approvals -------------------------------------------------------- #
    def test_bare_approval_claim_rejected(self):
        def approve(c):
            c["slots"][3]["approval"]["state"] = "approved"
        self.assertRejects(self.mutate(approve), "approval_without_external_record")

    def test_approval_identity_without_external_record_rejected(self):
        def approve(c):
            approval = c["slots"][3]["approval"]
            approval.update(state="made", decision_id="dec-1", approver="someone",
                            decided_utc="2026-09-14T00:00:00Z",
                            decision_text_digest="a" * 64,
                            decision_ref="docs/plan/owner-record.md",
                            external_record_pinned=False)
        self.assertRejects(self.mutate(approve), "approval_without_external_record")

    def test_self_pinned_external_record_rejected(self):
        def approve(c):
            c["external_owner_records"] = [
                {"id": "owner-1", "path": LEDGER_REL, "sha256": "b" * 64}]
            approval = c["slots"][3]["approval"]
            approval.update(state="made", decision_id="dec-1", approver="someone",
                            decided_utc="2026-09-14T00:00:00Z",
                            decision_text_digest="a" * 64, decision_ref="owner-1",
                            external_record_pinned=True)
        self.assertRejects(self.mutate(approve), "self_referential_evidence")

    def test_untracked_external_owner_record_rejected(self):
        def approve(c):
            c["external_owner_records"] = [
                {"id": "owner-1", "path": UNTRACKED_NON_PACKAGE, "sha256": "b" * 64}]
            approval = c["slots"][3]["approval"]
            approval.update(state="made", decision_id="dec-1", approver="someone",
                            decided_utc="2026-09-14T00:00:00Z",
                            decision_text_digest="a" * 64, decision_ref="owner-1",
                            external_record_pinned=True)
        violations = self.mutate(approve)
        self.assertRejects(violations, "pin_untracked_or_staged_only")
        self.assertRejects(violations, "approval_identity_present")

    def test_tracked_dummy_file_cannot_create_approval_route(self):
        def approve(c):
            c["external_owner_records"] = [{
                "id": "owner-1",
                "path": PIN_PATHS["g6_remediation_contract"],
                "sha256": PIN_SHA256["g6_remediation_contract"],
            }]
            approval = c["slots"][3]["approval"]
            approval.update(state="made", decision_id="dec-1", approver="someone",
                            decided_utc="2026-09-14T00:00:00Z",
                            decision_text_digest="a" * 64, decision_ref="owner-1",
                            external_record_pinned=True)
        violations = self.mutate(approve)
        self.assertRejects(violations, "approval_identity_present")
        self.assertNotEqual([], violations)

    def test_substituted_external_record_digest_rejected(self):
        def approve(c):
            c["external_owner_records"] = [{
                "id": "owner-1",
                "path": PIN_PATHS["g6_remediation_contract"],
                "sha256": "1" * 64,
            }]
            approval = c["slots"][3]["approval"]
            approval.update(state="made", decision_id="dec-1", approver="someone",
                            decided_utc="2026-09-14T00:00:00Z",
                            decision_text_digest="a" * 64, decision_ref="owner-1",
                            external_record_pinned=True)
        self.assertRejects(self.mutate(approve), "pin_hash_mismatch")

    def test_bad_decision_digest_rejected(self):
        def approve(c):
            c["external_owner_records"] = [{
                "id": "owner-1",
                "path": PIN_PATHS["g6_remediation_contract"],
                "sha256": PIN_SHA256["g6_remediation_contract"],
            }]
            approval = c["slots"][3]["approval"]
            approval.update(state="made", decision_id="dec-1", approver="someone",
                            decided_utc="2026-09-14T00:00:00Z",
                            decision_text_digest="not-hex", decision_ref="owner-1",
                            external_record_pinned=True)
        self.assertRejects(self.mutate(approve), "approval_without_external_record")

    # ---- forbidden provenance --------------------------------------------- #
    def test_placeholder_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["ref"] = "see analysis"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_tbd_frame_rejected(self):
        def fill(c):
            c["slots"][3]["frame_datum"]["frame"] = "TBD"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_r1_delta_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["ref"] = "R1 delta scaled by 10"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_candidate_difference_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["ref"] = "candidate difference observed at k153"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_observed_difference_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["ref"] = "observed difference from the reference"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_60120_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["derivation_class"] = "scale the 60120 residual"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_config_value_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["derivation_class"] = "copied from a config value"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_ulp_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["derivation_class"] = "absorb the observed 1 ULP"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_noise_or_config_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["derivation_class"] = "noise amplitude from config"
        violations = self.mutate(fill)
        self.assertRejects(violations, "forbidden_provenance_class")

    def test_order_or_epsilon_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["derivation_class"] = "machine epsilon times steps"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_sitl_threshold_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["derivation_class"] = "SITL threshold 0.6 m"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_untracked_supplement_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["frame_datum"]["datum"] = "untracked supplement binding"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_alignment_claim_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["derivation_class"] = "diagonal candidate is bit identical"
        self.assertRejects(self.mutate(fill), "forbidden_provenance_class")

    def test_derivation_without_pinned_record_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["ref"] = "docs/analysis/bound-note.md"
        self.assertRejects(self.mutate(fill), "derivation_without_external_record")

    def test_self_referential_derivation_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["ref"] = LEDGER_REL
        violations = self.mutate(fill)
        self.assertRejects(violations, "self_referential_evidence")

    def test_coordination_path_decision_ref_rejected(self):
        """Any coordination directory, not one hard-coded name (review dir M50)."""
        for directory in (PRE_REPAIR_REVIEW_DIR_REL, REPAIR_DIR_REL,
                          COORDINATION_DIR_REL + "/some-new-review-20260915"):
            with self.subTest(directory=directory):
                def fill(c, directory=directory):
                    c["slots"][3]["approval"]["decision_ref"] = directory + "/owner.json"
                self.assertRejects(self.mutate(fill), "self_referential_evidence")

    def test_nested_coordination_path_decision_ref_rejected(self):
        """A nested `coordination` segment is the same location class."""
        def fill(c):
            c["slots"][3]["approval"]["decision_ref"] = \
                "docs/x/coordination/y/owner.json"
        self.assertRejects(self.mutate(fill), "self_referential_evidence")

    # ---- structure --------------------------------------------------------- #
    def test_duplicate_slot_rejected(self):
        def duplicate(c):
            c["slots"].append(copy.deepcopy(c["slots"][0]))
        violations = self.mutate(duplicate)
        self.assertRejects(violations, "duplicate_slot")
        self.assertRejects(violations, "slot_count_not_120")

    def test_unknown_slot_key_rejected(self):
        def add(c):
            c["slots"][0]["abs_budget"] = None
        self.assertRejects(self.mutate(add), "unknown_slot_key")

    def test_missing_slot_key_rejected(self):
        def drop(c):
            c["slots"][0].pop("approval")
        self.assertRejects(self.mutate(drop), "missing_required_key")

    def test_unknown_slot_id_rejected(self):
        def rename(c):
            c["slots"][0]["slot_id"] = "Vehicle60[60]"
        self.assertRejects(self.mutate(rename), "slot_set_mismatch")

    def test_partition_mismatch_rejected(self):
        def swap(c):
            for slot in c["slots"]:
                if slot["slot_id"] == "GPS30[29]":
                    slot["partition"] = "dynamic_candidate"
                    slot["policy_class"] = None
                    slot["status"] = "blocked"
        violations = self.mutate(swap)
        self.assertRejects(violations, "slot_set_mismatch")
        self.assertRejects(violations, "policy_slot_dropped")

    def test_status_vocabulary_violation_rejected(self):
        def change(c):
            c["slots"][0]["status"] = "approved"
        self.assertRejects(self.mutate(change), "status_vocabulary_violation")

    def test_counts_drift_rejected(self):
        def change(c):
            c["counts"]["slots_approved"] = 120
        self.assertRejects(self.mutate(change), "counts_mismatch")

    def test_metric_switch_rejected(self):
        def change(c):
            c["slots"][0]["metric"]["frozen_metric"] = "exact_equality"
        self.assertRejects(self.mutate(change), "unknown_slot_key")

    def test_forbidden_class_removed_rejected(self):
        def drop(c):
            c["forbidden_provenance_classes"] = [
                item for item in c["forbidden_provenance_classes"]
                if item["id"] != "RD-01"]
        self.assertRejects(self.mutate(drop), "forbidden_provenance_class")

    def test_loophole_rule_removed_rejected(self):
        def drop(c):
            c["loophole_rules"] = [item for item in c["loophole_rules"]
                                   if item["id"] != "L1"]
        self.assertRejects(self.mutate(drop), "forbidden_provenance_class")

    def test_unknown_evidence_class_rejected(self):
        def change(c):
            c["slots"][0]["source_identity"]["evidence_class"] = "approved"
        self.assertRejects(self.mutate(change), "unknown_slot_key")

    def test_unknown_owner_input_rejected(self):
        def change(c):
            c["slots"][0]["owner_inputs"] = ["D-99"]
        self.assertRejects(self.mutate(change), "unknown_slot_key")


class RelatedSourceP2RepairTests(unittest.TestCase):
    """P2 residuals: freeze related triples in validate(); refuse SOURCE_HEAD gaps.

    The independent final review found that ``validate()`` only froze related
    ids, so a backslash or ``./`` spelling plus the current frame hash escaped
    the exact frame-path reject, and that a missing or non-ancestor SOURCE_HEAD
    was refused only by an outer unittest.  These cases are now judged inside
    ``validate()``.  Related records stay non-pins.
    """

    CURRENT_FRAME_SHA256 = (
        "5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f")

    def setUp(self):
        self.ledger = load_ledger()

    def mutate(self, mutator, check_git=False):
        clone = copy.deepcopy(self.ledger)
        mutator(clone)
        return validate(clone, check_git=check_git)

    def assertRejects(self, violations, token):
        self.assertTrue(any(item.startswith(token + ":") for item in violations),
                        "expected %s in %s" % (token, violations))

    def test_frozen_related_triples_match_ledger_and_constants(self):
        got = [(item["id"], item["path"], item["sha256"])
               for item in self.ledger["related_artifacts"]]
        self.assertEqual(got, list(RELATED_ARTIFACTS))
        self.assertEqual(RELATED_ARTIFACT_PATHS["frontier_audit_review"],
                         RELATED_ARTIFACTS[0][1])
        self.assertEqual(RELATED_ARTIFACT_SHA256["frontier_audit_review"],
                         RELATED_ARTIFACTS[0][2])
        self.assertEqual([], validate(self.ledger, check_git=False))

    def test_backslash_frame_path_with_current_hash_rejected(self):
        def mutate(c):
            c["related_artifacts"][0]["path"] = (
                "validation\\e0-frame-datum-binding-20260914.json")
            c["related_artifacts"][0]["sha256"] = self.CURRENT_FRAME_SHA256
        violations = self.mutate(mutate)
        self.assertRejects(violations, RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_dot_prefix_frame_path_with_current_hash_rejected(self):
        def mutate(c):
            c["related_artifacts"][0]["path"] = "./" + FRAME_CANDIDATE_REL
            c["related_artifacts"][0]["sha256"] = self.CURRENT_FRAME_SHA256
        violations = self.mutate(mutate)
        self.assertRejects(violations, RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_related_hash_mismatch_rejected(self):
        def mutate(c):
            c["related_artifacts"][0]["sha256"] = "ab" * 32
        self.assertRejects(self.mutate(mutate), RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_related_order_swap_rejected(self):
        def mutate(c):
            c["related_artifacts"][0], c["related_artifacts"][1] = (
                c["related_artifacts"][1], c["related_artifacts"][0])
        self.assertRejects(self.mutate(mutate), RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_duplicate_related_id_rejected(self):
        def mutate(c):
            c["related_artifacts"].append(copy.deepcopy(c["related_artifacts"][0]))
        self.assertRejects(self.mutate(mutate), RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_duplicate_related_path_rejected(self):
        def mutate(c):
            c["related_artifacts"][1]["path"] = c["related_artifacts"][0]["path"]
        self.assertRejects(self.mutate(mutate), RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_extra_related_record_rejected(self):
        def mutate(c):
            c["related_artifacts"].append({
                "id": "extra_related",
                "path": "validation/owner-records/extra.json",
                "sha256": "cd" * 32,
                "tracked_at_source_head": False,
                "role": "extra",
            })
        self.assertRejects(self.mutate(mutate), RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_missing_related_record_rejected(self):
        def mutate(c):
            c["related_artifacts"] = c["related_artifacts"][:2]
        self.assertRejects(self.mutate(mutate), RELATED_ARTIFACT_MISMATCH_TOKEN)

    def test_related_still_cannot_become_a_pin(self):
        def mutate(c):
            artifact = c["related_artifacts"][0]
            c["pins"][artifact["id"]] = {
                "id": artifact["id"], "path": artifact["path"],
                "sha256": artifact["sha256"], "tracked_at_head": False,
            }
        self.assertRejects(self.mutate(mutate), "pin_untracked_or_staged_only")

    def test_validate_rejects_missing_source_head(self):
        real_git = globals()["_git"]

        def missing(*args, env=None):
            if SOURCE_HEAD in " ".join(str(item) for item in args):
                return subprocess.CompletedProcess(args, 128, b"", b"missing")
            return real_git(*args, env=env)

        module = sys.modules[__name__]
        module._git = missing
        try:
            violations = validate(copy.deepcopy(self.ledger), check_git=True)
            structure = validate(copy.deepcopy(self.ledger), check_git=False)
        finally:
            module._git = real_git
        self.assertRejects(violations, SOURCE_HEAD_VIOLATION_TOKEN)
        self.assertEqual([], structure)

    def test_validate_rejects_source_head_not_ancestor(self):
        real_git = globals()["_git"]

        def not_ancestor(*args, env=None):
            joined = " ".join(str(item) for item in args)
            if args and args[0] == "cat-file" and SOURCE_HEAD in joined:
                return subprocess.CompletedProcess(args, 0, b"", b"")
            if args and args[0] == "merge-base" and SOURCE_HEAD in joined:
                return subprocess.CompletedProcess(args, 1, b"", b"not-ancestor")
            return real_git(*args, env=env)

        module = sys.modules[__name__]
        module._git = not_ancestor
        try:
            violations = validate(copy.deepcopy(self.ledger), check_git=True)
            structure = validate(copy.deepcopy(self.ledger), check_git=False)
        finally:
            module._git = real_git
        self.assertRejects(violations, SOURCE_HEAD_VIOLATION_TOKEN)
        self.assertEqual([], structure)

    def test_show_lstree_disagreement_still_fail_closed(self):
        real_git = globals()["_git"]

        def disagree(*args, env=None):
            if args and args[0] == "show" and SOURCE_HEAD in str(args[1]):
                return subprocess.CompletedProcess(args, 0, b"blob-bytes", b"")
            if args and args[0] == "ls-tree" and SOURCE_HEAD in args:
                return subprocess.CompletedProcess(args, 0, b"", b"")
            return real_git(*args, env=env)

        module = sys.modules[__name__]
        module._git = disagree
        try:
            helper = tracked_at_source_head(self.ledger["related_artifacts"][0]["path"])
            violations = validate(copy.deepcopy(self.ledger), check_git=True)
        finally:
            module._git = real_git
        self.assertIs(helper, True)
        self.assertRejects(violations, "pin_untracked_or_staged_only")

    def test_check_git_false_skips_source_head_object_probe(self):
        real_git = globals()["_git"]
        seen = []

        def deny_source(*args, env=None):
            seen.append(args)
            if SOURCE_HEAD in " ".join(str(item) for item in args):
                return subprocess.CompletedProcess(args, 128, b"", b"missing")
            return real_git(*args, env=env)

        module = sys.modules[__name__]
        module._git = deny_source
        try:
            violations = validate(copy.deepcopy(self.ledger), check_git=False)
        finally:
            module._git = real_git
        self.assertEqual([], violations)
        self.assertFalse(any(SOURCE_HEAD in " ".join(str(item) for item in args)
                             for args in seen))


class RepairRegressionTests(unittest.TestCase):
    """One regression per escaped hostile mutation of the pre-repair review.

    The pre-repair independent review (see ``PRE_REPAIR_REVIEW_DIR_REL``) found 14
    fail-open escapes in ``validate(ledger, check_git=False)`` plus one admitted
    benign reorder and one dangling provenance reference.  Each escape has a
    dedicated case below; the control that already passed before the repair
    (an owner record placed in the hard-coded directory) is kept as well.
    """

    def setUp(self):
        self.ledger = load_ledger()
        self.dynamic_index = next(i for i, s in enumerate(self.ledger["slots"])
                                  if s["partition"] == "dynamic_candidate")
        self.policy_index = next(i for i, s in enumerate(self.ledger["slots"])
                                 if s["partition"] == "policy_slot")

    def mutate(self, mutator, *args):
        clone = copy.deepcopy(self.ledger)
        mutator(clone, *args)
        return validate(clone, check_git=False)

    def assertRejects(self, violations, token):
        self.assertTrue(any(item.startswith(token + ":") for item in violations),
                        "expected %s in %s" % (token, violations))

    def owner_record(self, clone, path):
        clone["external_owner_records"] = [{"id": "own-x", "path": path,
                                            "sha256": "0" * 64,
                                            "slots": ["Vehicle60[2]"],
                                            "budgets": [0.0, 0.0, 0.0]}]
        clone["counts"]["external_owner_records"] = 1

    def derivation_record(self, clone, path):
        clone["external_derivation_records"] = [{"id": "drv-x", "path": path,
                                                 "sha256": "0" * 64,
                                                 "reference_quantity": "x"}]
        clone["counts"]["external_derivation_records"] = 1

    # ---- H1: loophole rule L2, derivation.derivation_class (M23/M23b) ------ #
    def test_derivation_class_without_pinned_record_rejected(self):
        for index in (self.policy_index, self.dynamic_index):
            with self.subTest(index=index):
                def fill(c, index=index):
                    c["slots"][index]["derivation"]["derivation_class"] = "RD-01"
                self.assertRejects(self.mutate(fill),
                                   "derivation_without_external_record")

    def test_plausible_derivation_class_without_pinned_record_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["derivation"]["derivation_class"] = \
                "grid convergence analysis"
        for index in (self.policy_index, self.dynamic_index):
            with self.subTest(index=index):
                self.assertRejects(self.mutate(fill, index),
                                   "derivation_without_external_record")

    def test_non_null_forbidden_class_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["derivation"]["forbidden_class"] = "RD-03"
        self.assertRejects(self.mutate(fill, self.dynamic_index),
                           "forbidden_provenance_class")

    # ---- H3: loophole rule L2, domain.declared_domain (M26/M26b) ---------- #
    def test_declared_domain_without_pinned_record_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["domain"]["declared_domain"] = "documented test envelope"
        for index in (self.policy_index, self.dynamic_index):
            with self.subTest(index=index):
                self.assertRejects(self.mutate(fill, index),
                                   "derivation_without_external_record")

    # ---- H2: loophole rule L3, frame/datum (M24/M25/M24b/M25b) ----------- #
    def test_free_text_frame_without_owner_record_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["frame_datum"]["frame"] = "ENU"
        for index in (self.policy_index, self.dynamic_index):
            with self.subTest(index=index):
                self.assertRejects(self.mutate(fill, index),
                                   "approval_without_external_record")

    def test_free_text_datum_without_owner_record_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["frame_datum"]["datum"] = "WGS84"
        for index in (self.policy_index, self.dynamic_index):
            with self.subTest(index=index):
                self.assertRejects(self.mutate(fill, index),
                                   "approval_without_external_record")

    # ---- M1: undeclared sub-block keys (M39) ----------------------------- #
    def test_undeclared_key_in_every_sub_block_rejected(self):
        for block in sorted(FROZEN_SUBFIELDS):
            with self.subTest(block=block):
                def fill(c, index=None, block=block):
                    c["slots"][index][block]["abs_budget"] = 0.3
                violations = self.mutate(fill, self.dynamic_index)
                if "abs_budget" in FROZEN_SUBFIELDS[block]:
                    self.assertRejects(violations, "numeric_budget_present")
                else:
                    self.assertRejects(violations, "unknown_slot_key")

    def test_missing_sub_block_key_rejected(self):
        for block in sorted(FROZEN_SUBFIELDS):
            with self.subTest(block=block):
                def drop(c, index=None, block=block):
                    c["slots"][index][block].pop(FROZEN_SUBFIELDS[block][0])
                self.assertRejects(self.mutate(drop, self.dynamic_index),
                                   "missing_required_key")

    def test_undeclared_source_mapping_key_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["source_identity"]["committed_source_mapping"]["budget"] = 1
        self.assertRejects(self.mutate(fill, self.dynamic_index), "unknown_slot_key")

    def test_shrunk_required_subfields_rejected(self):
        def drop(c, index=None):
            c["required_subfields"]["metric"] = ["frozen_metric"]
        self.assertRejects(self.mutate(drop), "missing_required_key")

    def test_shrunk_required_slot_fields_rejected(self):
        def drop(c, index=None):
            c["required_slot_fields"] = [f for f in c["required_slot_fields"]
                                         if f != "owner_inputs"]
        self.assertRejects(self.mutate(drop), "missing_required_key")

    def test_foreign_native_unit_source_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["source_identity"]["native_unit_source"] = "pin:invented"
        self.assertRejects(self.mutate(fill, self.dynamic_index), "unknown_slot_key")

    # ---- M2: sub-block status vocabularies (M41) ------------------------- #
    def test_budgets_status_outside_vocabulary_rejected(self):
        def fill(c, index=None):
            c["slots"][index]["budgets"]["status"] = "approved"
        self.assertRejects(self.mutate(fill, self.dynamic_index),
                           "status_vocabulary_violation")

    def test_blocked_only_sub_block_statuses_rejected(self):
        for block in BLOCKED_ONLY_SUBBLOCKS + ("frame_datum",):
            with self.subTest(block=block):
                def fill(c, index=None, block=block):
                    c["slots"][index][block]["status"] = "approved"
                self.assertRejects(self.mutate(fill, self.dynamic_index),
                                   "status_vocabulary_violation")

    def test_frame_datum_status_must_follow_slot_status(self):
        def fill(c, index=None):
            c["slots"][index]["frame_datum"]["status"] = "pending_owner_policy"
        self.assertRejects(self.mutate(fill, self.dynamic_index),
                           "status_vocabulary_violation")

    # ---- L1: slot_set / counts cross-checks (M45) ------------------------ #
    def test_slot_set_array_count_mismatch_rejected(self):
        def fill(c, index=None):
            c["slot_set"]["arrays"]["Vehicle60"] = 59
        self.assertRejects(self.mutate(fill), "slot_set_mismatch")

    def test_slot_set_scalar_and_unknown_key_rejected(self):
        for key, value in (("total_slots", 119), ("dynamic_candidate_slots", 55),
                           ("policy_slots", 65), ("policy_interface_metadata", 4),
                           ("policy_reserved_not_physical_coverage", 60)):
            with self.subTest(key=key):
                def fill(c, index=None, key=key, value=value):
                    c["slot_set"][key] = value
                self.assertRejects(self.mutate(fill), "slot_set_mismatch")

        def extra(c, index=None):
            c["slot_set"]["extra_summary"] = 1
        self.assertRejects(self.mutate(extra), "slot_set_mismatch")

        def blank(c, index=None):
            c["slot_set"]["partition_rule"] = " "
        self.assertRejects(self.mutate(blank), "slot_set_mismatch")

    def test_counts_rhs_resolution_and_binding_drift_rejected(self):
        def rhs(c, index=None):
            c["counts"]["dynamic_rhs_resolution"]["unresolved"] = 27
        self.assertRejects(self.mutate(rhs), "counts_mismatch")

        def frame(c, index=None):
            c["counts"]["dynamic_slots_with_committed_frame_binding"] = 1
        self.assertRejects(self.mutate(frame), "counts_mismatch")

        def datum(c, index=None):
            c["counts"]["dynamic_slots_with_committed_datum_binding"] = 1
        self.assertRejects(self.mutate(datum), "counts_mismatch")

        def drop(c, index=None):
            c["counts"].pop("slots_approved")
        self.assertRejects(self.mutate(drop), "counts_mismatch")

        def extra(c, index=None):
            c["counts"]["slots_approved_by_owner"] = 120
        self.assertRejects(self.mutate(extra), "counts_mismatch")

    # ---- P1: structural external-record location class (M49-M53) --------- #
    def test_owner_record_in_any_coordination_directory_rejected(self):
        paths = (
            PIN_PATHS["budget_evidence_audit"],                    # tracked pin path
            PRE_REPAIR_REVIEW_DIR_REL + "/owner.json",             # actual review dir
            REPAIR_DIR_REL + "/owner.json",                        # repair dir
            "validation/coordination/some-new-review-20260915/owner.json",
            "validation/coordination",                             # the directory itself
            "docs/x/coordination/y/owner.json",                    # nested segment
            "validation\\coordination\\owner.json",                # backslash form
        )
        for path in paths:
            with self.subTest(path=path):
                violations = self.mutate(lambda c, p=path: self.owner_record(c, p))
                self.assertRejects(violations, LOCATION_VIOLATION_TOKEN)

    def test_derivation_record_in_coordination_directory_rejected(self):
        """M52: the same rule must cover derivation records, not just owner ones."""
        def fill(c, index=None):
            self.derivation_record(c, PIN_PATHS["budget_evidence_audit"])
        self.assertRejects(self.mutate(fill), LOCATION_VIOLATION_TOKEN)

    def test_non_relative_or_traversing_record_path_rejected(self):
        for path in ("C:/owner/owner.json", "/etc/owner.json",
                     "validation/../owner.json", "", "   "):
            with self.subTest(path=path):
                violations = self.mutate(lambda c, p=path: self.owner_record(c, p))
                self.assertRejects(violations, LOCATION_VIOLATION_TOKEN)

    def test_package_file_record_paths_rejected_as_self_reference(self):
        for path in PACKAGE_PATHS:
            with self.subTest(path=path):
                violations = self.mutate(lambda c, p=path: self.owner_record(c, p))
                self.assertRejects(violations, "self_referential_evidence")

    def test_legitimate_external_location_is_admissible(self):
        """Negative control: the location rule is a class rule, not reject-all."""
        for path in ("validation/owner-records/owner-1.json",
                     "docs/coordination-free/owner-record.md",
                     PIN_PATHS["g6_remediation_contract"]):
            with self.subTest(path=path):
                self.assertIsNone(_external_record_location_defect(path))
        self.assertIsNotNone(
            _external_record_location_defect(PIN_PATHS["budget_evidence_audit"]))
        self.assertIsNone(_external_record_location_defect("validation/coordinationish.json"))

    def test_tracked_coordination_record_cannot_create_approval_route(self):
        """The pre-repair M51/M52 combination: pinned, tracked, still not evidence."""
        def fill(c, index=None):
            self.owner_record(c, PIN_PATHS["budget_evidence_audit"])
            c["external_owner_records"][0]["sha256"] = PIN_SHA256["budget_evidence_audit"]
            approval = c["slots"][self.dynamic_index]["approval"]
            approval.update(state="made", decision_id="dec-1", approver="someone",
                            decided_utc="2026-09-14T00:00:00Z",
                            decision_text_digest="a" * 64, decision_ref="own-x",
                            external_record_pinned=True)
            c["slots"][self.dynamic_index]["budgets"]["abs_budget"] = 1e-9
        violations = self.mutate(fill)
        self.assertRejects(violations, LOCATION_VIOLATION_TOKEN)
        self.assertRejects(violations, "numeric_budget_present")
        self.assertRejects(violations, "approval_identity_present")

    # ---- provenance truthfulness (dangling Cursor reference) ------------- #
    def test_dangling_cursor_review_reference_removed(self):
        # Assembled at runtime so this assertion does not match its own source.
        dangling = "cursor-" + "g6-budget-provenance"
        for path in (LEDGER_PATH, DOC_PATH, TEST_PATH):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8").lower()
                self.assertFalse(dangling in text,
                                 "%s still names the cancelled dangling directory"
                                 % path.name)

    def test_review_and_repair_directories_are_named_not_checkout_deps(self):
        """Named ignored review/repair dirs are provenance, not disk deps.

        A clean checkout need not contain the directories.  Names and the
        already-recorded source/hash (payload pins plus ``not_evidence_locations``)
        are checked.  The C1 owner gate is unchanged: these paths cannot be
        owner or derivation records.
        """
        plan = DOC_PATH.read_text(encoding="utf-8")
        ledger_text = LEDGER_TEXT
        ledger = load_ledger()
        location_policy = ledger["promotion_requirements"][
            "external_record_location_policy"]
        for rel in NAMED_COORDINATION_DIRS:
            with self.subTest(rel=rel):
                self.assertIn(rel, plan)
                self.assertIn(rel, ledger_text)
                self.assertTrue(any(entry.startswith(rel)
                                    for entry in location_policy["not_evidence_locations"]),
                                "%s missing from not_evidence_locations" % rel)
                token, _ = _external_record_location_defect(rel + "/owner.json")
                self.assertEqual(LOCATION_VIOLATION_TOKEN, token)
                token, _ = _external_record_location_defect(rel + "/derive.json")
                self.assertEqual(LOCATION_VIOLATION_TOKEN, token)
        for pin_id, pin in ledger["pins"].items():
            self.assertEqual(pin["sha256"], PIN_SHA256[pin_id], pin_id)
            self.assertEqual(pin["path"], PIN_PATHS[pin_id], pin_id)

    def test_location_class_is_in_the_documented_failure_boundary(self):
        policy = self.ledger["evidence_policy"]["fail_closed_on"]
        self.assertIn(LOCATION_VIOLATION_TOKEN, policy)
        self.assertIn(LOCATION_VIOLATION_TOKEN, DOC_PATH.read_text(encoding="utf-8"))
        location_policy = self.ledger["promotion_requirements"][
            "external_record_location_policy"]
        self.assertIn(COORDINATION_DIR_REL, location_policy["rule"])
        self.assertTrue(any(entry.startswith(PRE_REPAIR_REVIEW_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(any(entry.startswith(REPAIR_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(any(entry.startswith(POST_REPAIR_REVIEW_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(any(entry.startswith(REPAIR2_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(any(entry.startswith(TAKEOVER_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(any(entry.startswith(SEQUENCE_REPAIR_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(any(entry.startswith(FINAL_REVIEW_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(any(entry.startswith(RELATED_SOURCE_P2_REPAIR_DIR_REL)
                            for entry in location_policy["not_evidence_locations"]))
        self.assertTrue(location_policy["pins_are_a_different_class"])
        self.assertIn(RELATED_ARTIFACT_MISMATCH_TOKEN, policy)
        self.assertIn(SOURCE_HEAD_VIOLATION_TOKEN, policy)
        plan = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn(RELATED_ARTIFACT_MISMATCH_TOKEN, plan)
        self.assertIn(SOURCE_HEAD_VIOLATION_TOKEN, plan)


class LocationCaseFoldTests(unittest.TestCase):
    """C1 regression: the location class is case- and separator-insensitive.

    The post-repair independent review at
    ``validation/coordination/cursor-g6-budget-postrepair-review-20260914-01`` found
    that the case-sensitive segment test admitted ``validation/COORDINATION/**`` and
    ``validation/Coordination/**``.  Every path-segment comparison is now case-folded
    after slash normalization and dot-segment handling, on Windows and on Linux, and
    ``check_git=False`` is enough to see the rejection.
    """

    COORDINATION_SPELLINGS = (
        "validation/coordination/owner.json",
        "validation/COORDINATION/owner.json",
        "validation/Coordination/owner.json",
        "VALIDATION/COORDINATION/owner.json",
        "Validation/Coordination/owner.json",
        "validation\\Coordination\\owner.json",
        "validation/./COORDINATION/owner.json",
        "validation//Coordination//owner.json",
        "validation/COORDINATION/",
        "validation/Coordination./owner.json",
        "validation/Coordination /owner.json",
        "coordination/owner.json",
        "COORDINATION/owner.json",
        "docs/x/COORDINATION/y/owner.json",
        "docs\\x\\coordination\\y\\owner.json",
        "validation/CoOrDiNaTiOn/owner.json",
    )
    # A longer segment is a different path class, not a casing variant.
    PREFIX_NEGATIVES = (
        "validation/coordinationish.json",
        "validation/my-coordination/owner.json",
        "docs/coordination-notes/owner.md",
        "validation/coordination_notes/owner.md",
        "docs/my_coordination/owner.md",
    )
    PACKAGE_SPELLINGS = (
        "VALIDATION/TEST_E0_BUDGET_APPROVAL_PROVENANCE.PY",
        "Validation/./test_e0_budget_approval_provenance.py",
        "docs\\plan\\59-E0-BUDGET-APPROVAL-PROVENANCE-20260914.MD",
        "DOCS/PLAN/59-e0-budget-approval-provenance-20260914.md",
        LEDGER_REL.upper(),
    )

    def setUp(self):
        self.ledger = load_ledger()

    def mutate(self, mutator):
        clone = copy.deepcopy(self.ledger)
        mutator(clone)
        return validate(clone, check_git=False)

    def assertRejects(self, violations, token):
        self.assertTrue(any(item.startswith(token + ":") for item in violations),
                        "expected %s in %s" % (token, violations))

    def put_owner(self, clone, path):
        clone["external_owner_records"] = [{"id": "own-x", "path": path,
                                            "sha256": "0" * 64}]
        clone["counts"]["external_owner_records"] = 1

    def put_derivation(self, clone, path):
        clone["external_derivation_records"] = [{"id": "drv-x", "path": path,
                                                 "sha256": "0" * 64}]
        clone["counts"]["external_derivation_records"] = 1

    def test_owner_record_case_and_separator_variants_rejected(self):
        for path in self.COORDINATION_SPELLINGS:
            with self.subTest(path=path):
                violations = self.mutate(lambda c, p=path: self.put_owner(c, p))
                self.assertRejects(violations, LOCATION_VIOLATION_TOKEN)

    def test_derivation_record_case_and_separator_variants_rejected(self):
        spellings = (
            "validation/COORDINATION/derive.json",
            "validation/Coordination/derive.json",
            "VALIDATION/coordination/derive.json",
            "validation\\COORDINATION\\derive.json",
            "validation/./Coordination/derive.json",
            "VALIDATION\\Coordination\\derive.json",
            "validation/CoOrDiNaTiOn/derive.json",
        )
        for path in spellings:
            with self.subTest(path=path):
                violations = self.mutate(lambda c, p=path: self.put_derivation(c, p))
                self.assertRejects(violations, LOCATION_VIOLATION_TOKEN)

    def test_case_variants_are_the_same_class_on_either_separator(self):
        """The rejection reason names the class, not the spelling."""
        for path in ("validation/COORDINATION/owner.json",
                     "validation\\Coordination\\owner.json"):
            with self.subTest(path=path):
                token, reason = _external_record_location_defect(path)
                self.assertEqual(LOCATION_VIOLATION_TOKEN, token)
                self.assertIn(COORDINATION_DIR_REL, reason)

    def test_prefix_negative_controls_stay_admissible(self):
        for path in self.PREFIX_NEGATIVES:
            with self.subTest(path=path):
                self.assertIsNone(_external_record_location_defect(path))
                violations = self.mutate(lambda c, p=path: self.put_owner(c, p))
                self.assertEqual([], violations,
                                 "%s must stay a different path class" % path)

    def test_package_path_comparison_is_case_and_separator_insensitive(self):
        for path in self.PACKAGE_SPELLINGS:
            with self.subTest(path=path):
                token, reason = _external_record_location_defect(path)
                self.assertEqual("self_referential_evidence", token)
                violations = self.mutate(lambda c, p=path: self.put_owner(c, p))
                self.assertRejects(violations, "self_referential_evidence")

    def test_fold_segment_uses_unicode_casefold_not_ascii_lower(self):
        """Segment comparison uses Unicode casefold, not an ASCII-only table."""
        self.assertEqual(_fold_segment("COORDINATION"), COORDINATION_SEGMENT)
        self.assertEqual(_fold_segment("Coordination"), COORDINATION_SEGMENT)
        self.assertEqual(_fold_segment("CoOrDiNaTiOn"), COORDINATION_SEGMENT)
        # long s: str.lower keeps the character; str.casefold maps it to s.
        self.assertEqual("\u017f".lower(), "\u017f")
        self.assertEqual("\u017f".casefold(), "s")
        self.assertEqual(_fold_segment("\u017f"), "s")

    def test_location_helper_unit_contract(self):
        for path in self.COORDINATION_SPELLINGS:
            with self.subTest(path=path):
                self.assertIsNotNone(_external_record_location_defect(path))
        for path in self.PREFIX_NEGATIVES + (
                "docs/plan/10-g6-remediation-contract.md",
                "validation/owner-records/owner-1.json"):
            with self.subTest(path=path):
                self.assertIsNone(_external_record_location_defect(path))
        for path in ("/etc/owner.json", "C:/owner/owner.json",
                     "validation/../owner.json", "", "   "):
            with self.subTest(path=path):
                token, _ = _external_record_location_defect(path)
                self.assertEqual(LOCATION_VIOLATION_TOKEN, token)

    def test_free_text_scans_are_case_and_separator_insensitive(self):
        self.assertTrue(_coordination_self_reference("validation/COORDINATION/owner.json"))
        self.assertTrue(_coordination_self_reference("VALIDATION\\Coordination\\x.json"))
        self.assertTrue(_coordination_self_reference("see coordination/owner.json"))
        self.assertTrue(_package_self_reference(
            "VALIDATION\\TEST_E0_BUDGET_APPROVAL_PROVENANCE.PY"))
        self.assertTrue(_package_self_reference(
            "docs/PLAN/59-E0-BUDGET-APPROVAL-PROVENANCE-20260914.md"))
        for text in ("validation/coordinationish.json",
                     "validation/my-coordination/owner.json",
                     "docs/coordination-notes/owner.md",
                     "the coordination directory"):
            with self.subTest(text=text):
                self.assertEqual([], _coordination_self_reference(text))
                self.assertEqual([], _package_self_reference(text))

    def test_case_variant_decision_ref_rejected(self):
        def fill(c):
            c["slots"][3]["approval"]["decision_ref"] = "validation/COORDINATION/owner.json"
        violations = self.mutate(fill)
        self.assertRejects(violations, "self_referential_evidence")

    def test_case_variant_derivation_ref_rejected(self):
        def fill(c):
            c["slots"][3]["derivation"]["ref"] = \
                "VALIDATION\\TEST_E0_BUDGET_APPROVAL_PROVENANCE.PY"
        violations = self.mutate(fill)
        self.assertRejects(violations, "self_referential_evidence")
        self.assertRejects(violations, "derivation_without_external_record")

    def test_frozen_pin_class_stays_distinct_under_case_folding(self):
        """Pins are admitted by id/path/sha256, never by the location class."""
        pin_path = PIN_PATHS["budget_evidence_audit"]
        self.assertIn("/coordination/", pin_path)
        self.assertIsNotNone(_external_record_location_defect(pin_path))
        # The pristine ledger keeps that path as a pin and validates clean.
        self.assertEqual([], validate(self.ledger, check_git=False))
        self.assertEqual(pin_path, self.ledger["pins"]["budget_evidence_audit"]["path"])

        def recase(c):
            c["pins"]["budget_evidence_audit"]["path"] = \
                "VALIDATION/COORDINATION/ds-g6-budget-evidence-20260913-01/audit.json"
        # Pin path equality is deliberately exact: the frozen spelling is required,
        # and a case variant fails closed instead of silently resolving on Windows.
        self.assertRejects(self.mutate(recase), "pin_missing_or_substituted")


class NoApprovalRouteTests(unittest.TestCase):
    """Filling the ledger in place must still not produce an approval."""

    def setUp(self):
        self.ledger = load_ledger()

    def test_maximal_in_ledger_fill_is_still_rejected(self):
        clone = copy.deepcopy(self.ledger)
        for slot in clone["slots"]:
            slot["budgets"] = {"abs_budget": 1.0, "rel_budget": 1.0,
                               "rms_budget": 1.0, "status": "approved"}
            slot["derivation"] = {"required": True, "ref": "self hash",
                                  "derivation_class": "grid convergence",
                                  "status": "approved",
                                  "evidence_class": "committed_derivable",
                                  "forbidden_class": None}
            slot["approval"] = {"state": "made", "decision_id": "dec-x",
                                "approver": "agent", "decided_utc": "2026-09-14T00:00:00Z",
                                "decision_text_digest": "c" * 64,
                                "decision_ref": LEDGER_REL,
                                "external_record_pinned": True,
                                "evidence_class": "committed_derivable"}
            slot["status"] = "approved"
        violations = validate(clone)
        for token in ("numeric_budget_present", "approval_without_external_record",
                      "approval_identity_present", "self_referential_evidence",
                      "forbidden_provenance_class", "status_vocabulary_violation",
                      "policy_slot_dropped"):
            self.assertTrue(any(item.startswith(token + ":") for item in violations),
                            "expected %s in %s" % (token, violations))

    def test_external_record_lists_are_empty_so_no_promotion_exists(self):
        self.assertEqual(self.ledger["external_owner_records"], [])
        self.assertEqual(self.ledger["external_derivation_records"], [])
        for slot in self.ledger["slots"]:
            self.assertIs(slot["approval"]["external_record_pinned"], False)

    def test_promotion_rule_names_external_pins(self):
        rule = self.ledger["promotion_requirements"]["rule"]
        self.assertIn("external_owner_records", rule)
        self.assertIn("derivation.ref", rule)

    def test_ledger_never_cites_itself_or_siblings(self):
        for path, value in _walk_strings(self.ledger):
            if path and path[0] in NON_SCANNED_TOP_LEVEL_KEYS:
                continue
            self.assertFalse(_package_self_reference(value),
                             "self reference at %s" % (".".join(path),))


class IntegrationTests(unittest.TestCase):
    """The ledger must agree with the contracts that consume these slots."""

    def test_slot_ids_cover_exactly_the_entry_scalar_set(self):
        conformance = load_json_bytes(head_blob(PIN_PATHS["r1_contract"]), "r1_contract")
        expected = {"%s[%d]" % (o["array"], i)
                    for o in conformance["observables"] for i in o["indices"]}
        self.assertEqual({slot["slot_id"] for slot in load_ledger()["slots"]}, expected)

    def test_dynamic_slots_match_the_rhs_pin_slot_set(self):
        rhs = load_json_bytes(head_blob(PIN_PATHS["rhs_references"]), "rhs_references")
        dynamic = {slot["slot"] for slot in rhs["slots"]}
        ledger_dynamic = {slot["slot_id"] for slot in load_ledger()["slots"]
                          if slot["partition"] == "dynamic_candidate"}
        self.assertEqual(ledger_dynamic, dynamic)

    def test_slot_manifest_covers_the_same_dynamic_slots(self):
        manifest = load_json_bytes(head_blob(PIN_PATHS["slot_manifest"]), "slot_manifest")
        self.assertEqual({slot["slot"] for slot in manifest["slots"]},
                         {slot["slot_id"] for slot in load_ledger()["slots"]
                          if slot["partition"] == "dynamic_candidate"})

    def test_entry_requires_approval_string_and_budgets_for_all_120(self):
        """The gate this ledger exists to harden: 120 scalars, approved budgets."""
        source = head_blob(PIN_PATHS["same_source_entry"]).decode("utf-8")
        self.assertIn("OBSERVABLE_REQUIRED_FIELDS", source)
        self.assertIn("TOTAL_SCALARS = 120", source)
        self.assertIn("approval", source)
        self.assertIn("'approved'", source)


if __name__ == "__main__":
    unittest.main()
