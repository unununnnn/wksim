"""Offline verification for the #59 G6 owner-decision request (2026-09-14).

The request (validation/e0-g6-owner-decision-request-20260914.json) asks the
owner for exactly three decision groups: the C3G first-step solve form, the
OD-01/OD-02 scheduling/time semantics of the three schedule_metadata time
fields, and the OD-20 active-vs-extra motor output scope.  This suite is
entirely offline: stdlib only, no MATLAB/native/ROS/FC/UE/build/#83, no git
mutation, no GitHub mutation, no network.

It proves the request is anchored and fail-closed:

- the document is schema-validated structurally (unknown keys, wrong types,
  exactly three decision groups, exact option vocabulary);
- every decision state is not_made, no option is chosen, no made-by/decided
  fields are populated, and no numeric budget or budget/tolerance field
  appears anywhere;
- at most the six listed sources are pinned, each by tracked HEAD SHA256 and
  size (git cat-file blob HEAD:<path>), with the working-tree bytes required
  to match the same digest/size;
- ancestry of 31e5b65f and f333316e is required (git merge-base
  --is-ancestor ... HEAD must exit 0) and exact-HEAD equality is explicitly
  not asserted, so later unrelated commits do not invalidate the request;
- any validation/coordination evidence path is rejected case-insensitively;
- RD-01..RD-12 derivations, budget approvals, owner choices and closure or
  acceptance claims are rejected;
- r1_status=numerical_failed, budget_approved/g6_acceptance/physical_accuracy
  stay false, issues_closed is empty, and B1/B3/B4, OD-03..OD-24 except
  OD-20, #84/G6/Full stay open;
- the OD-01/OD-02/OD-20 questions and slot sets are re-read from the pinned
  frame/datum binding and compared exactly.

Run modes:

- normal: python -B -m unittest validation.test_e0_g6_owner_decision_request
  Read-only git plumbing only; the real index is never written.
- repo-external temporary index (exact three candidates staged)::

      $env:GIT_INDEX_FILE = "$env:TEMP\\wksim-59-odr-index"
      git add --force -- docs/plan/59-g6-owner-decision-request-20260914.md `
          validation/e0-g6-owner-decision-request-20260914.json `
          validation/test_e0_g6_owner_decision_request.py
      $env:WKSIM_59_ODR_TEMP_INDEX = "1"
      python -B -m unittest validation.test_e0_g6_owner_decision_request

  The suite then additionally asserts that the external index holds exactly
  the three candidates at stage 0 with blob bytes identical to the working
  tree, and that the real index still stages none of them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

JSON_REL = "validation/e0-g6-owner-decision-request-20260914.json"
MD_REL = "docs/plan/59-g6-owner-decision-request-20260914.md"
TEST_REL = "validation/test_e0_g6_owner_decision_request.py"
CANDIDATE_PATHS = (MD_REL, JSON_REL, TEST_REL)
JSON_PATH = ROOT / JSON_REL
MD_PATH = ROOT / MD_REL

SCHEMA = "wksim.59-g6-owner-decision-request.v1"
KIND = "g6_owner_decision_request"
ISSUE = 59
PARENT_ISSUE = 10
REQUIRED_ANCESTORS = (
    "31e5b65f5448c5558450d16d0f46da0ef0f0a03c",
    "f333316e6efa6b299b4288a9d91fb2bccedfb9d6",
)

# The only pinned sources this request may carry: id -> (path, sha256, bytes).
PINS = {
    "g6_remediation_contract": (
        "docs/plan/10-g6-remediation-contract.md",
        "48da61ade51d46111db0be9a9288d93d4eec380251043c2e39bff66b74cae5c0",
        9935,
    ),
    "dynamic_budget_source_map": (
        "docs/plan/59-e0-dynamic-budget-source-map.md",
        "35a56084105409329131add7d4b9e35be6d1a145c6e18268c96324805313cd42",
        11215,
    ),
    "frame_datum_binding": (
        "validation/e0-frame-datum-binding-20260914.json",
        "5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f",
        105018,
    ),
    "solve_form_decision": (
        "validation/e0-g6-solve-form-decision-20260914.json",
        "5086c3fbddd52b4e754a785706cce938ca7f8d68beb5056d564e7f116b34c293",
        11339,
    ),
    "budget_approval_provenance": (
        "validation/e0-budget-approval-provenance-20260914.json",
        "2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d",
        285820,
    ),
    "r1_contract": (
        "Simulator/wksim_core/numerical-conformance-v1.json",
        "23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0",
        29846,
    ),
}
PIN_PATHS = tuple(item[0] for item in PINS.values())
PIN_IDS_CASEFOLD = frozenset(pin_id.casefold() for pin_id in PINS)

TOP_KEYS = {
    "schema",
    "kind",
    "issue",
    "parent_issue",
    "layer",
    "authority",
    "effective",
    "date",
    "title",
    "work_class",
    "claim_text",
    "request_for",
    "request_scope",
    "observed_at",
    "evidence_policy",
    "pins",
    "decision_groups",
    "open_items",
    "non_claims",
    "scope_limits",
    "budget_approved",
    "g6_acceptance",
    "physical_accuracy",
    "owner_decisions_made",
    "r1_status",
    "issues_closed",
}
PIN_KEYS = {"id", "path", "sha256", "size_bytes", "tracked_at_head", "role"}
GROUP_KEYS = {
    "id",
    "key",
    "title",
    "source_pin",
    "owner_decision_ids",
    "slots",
    "related_slots_out_of_scope",
    "question",
    "evidence_question_ref",
    "options",
    "state",
    "chosen_option",
    "decided_by",
    "decided_utc",
    "decision_text",
    "derivation_class",
    "derivation_ref",
    "blocked_by",
    "not_covered_by_this_group",
}
OPTION_KEYS = {"id", "label", "chosen"}
OBSERVED_KEYS = {
    "cwd",
    "branch",
    "observed_head",
    "observed_head_note",
    "required_ancestors",
    "required_ancestor_check",
    "exact_head_equality_asserted",
    "recorded_utc",
}
REQUEST_SCOPE_KEYS = {
    "decision_group_count",
    "decision_group_keys",
    "only_these_groups_requested",
    "requested_owner_decision_ids",
}
POLICY_KEYS = {
    "digest_algorithm",
    "digest_encoding",
    "pin_bytes_source",
    "pin_bytes_source_note",
    "tracked_pin_ids",
    "max_pins",
    "forbidden_evidence_paths_case_insensitive",
    "forbidden_evidence_path_prefix_casefold",
    "forbidden_derivation_classes",
    "forbidden_numeric_fields",
    "fail_closed_on",
}
OPEN_ITEM_KEYS = {
    "blockers_open",
    "blocker_notes",
    "owner_decisions_open",
    "issues_open",
    "issues_closed",
    "budget_approved",
}
SCOPE_LIMIT_KEYS = {
    "module",
    "writable_files",
    "native_or_model_launched",
    "matlab_launched",
    "ros_fc_ue_build_launched",
    "issue_83_launched",
    "issues_mutated",
    "git_index_mutated",
    "git_committed",
    "git_pushed",
}

# group id, key, option ids, slots, requested owner-decision ids
GROUP_SPECS = (
    (
        "DG-1",
        "solve_form_choice",
        ("adopt_diagonal_branch", "retain_division_absorb_ulp", "defer"),
        (),
        (),
    ),
    (
        "DG-2",
        "od01_od02_scheduling_time_semantics",
        ("exclude_from_physical_comparison", "include_with_own_metric", "defer"),
        ("Vehicle60[2]", "Sensor30[0]", "GPS30[0]"),
        ("OD-01", "OD-02"),
    ),
    (
        "DG-3",
        "od20_active_vs_extra_motor_output_scope",
        ("include_in_external_contract", "exclude_as_inactive_output", "defer"),
        ("Vehicle60[20]", "Vehicle60[21]", "Vehicle60[22]", "Vehicle60[23]"),
        ("OD-20",),
    ),
)
GROUP_ORDER = tuple(item[1] for item in GROUP_SPECS)
REQUESTED_ODS = tuple("OD-%02d" % number for number in (1, 2, 20))
OPEN_ODS = tuple("OD-%02d" % number for number in range(3, 25) if number != 20)
OPEN_BLOCKERS = ("B1", "B3", "B4")
OPEN_ISSUES = ("#84", "G6", "Full")
FORBIDDEN_DERIVATIONS = tuple("RD-%02d" % number for number in range(1, 13))
FORBIDDEN_NUMERIC_FIELDS = (
    "abs_budget",
    "rel_budget",
    "rms_budget",
    "budget",
    "budgets",
    "tolerance",
    "abs_tolerance",
    "rel_tolerance",
    "error_budget",
    "ulp_budget",
    "numeric_budget",
)
FAIL_CLOSED_ON = (
    "unknown_top_level_key",
    "unknown_decision_group_key",
    "missing_required_key",
    "wrong_type",
    "decision_group_count_not_three",
    "duplicate_decision_group",
    "unknown_owner_decision_id",
    "requested_decision_set_mismatch",
    "open_decision_list_mismatch",
    "blocker_dropped",
    "owner_decision_already_made",
    "option_already_chosen",
    "budget_approval_claim",
    "forbidden_budget_key",
    "numeric_budget_present",
    "closure_claim",
    "acceptance_claim",
    "r1_status_changed",
    "derivation_present",
    "forbidden_derivation",
    "forbidden_evidence_path",
    "pin_count_exceeded",
    "pin_path_not_listed",
    "pin_missing",
    "pin_extra",
    "pin_not_tracked_at_head",
    "pin_hash_mismatch",
    "pin_size_mismatch",
    "pin_worktree_drift",
    "required_ancestor_missing",
    "required_ancestor_not_ancestor",
    "exact_head_equality_claim",
    "mutation_scope_claim",
)
SCOPE_FALSE_FLAGS = (
    "native_or_model_launched",
    "matlab_launched",
    "ros_fc_ue_build_launched",
    "issue_83_launched",
    "issues_mutated",
    "git_index_mutated",
    "git_committed",
    "git_pushed",
)

PATH_KEYS = {"path", "evidence_path", "evidence_paths", "source_path", "record_path"}
DERIVATION_KEYS = {
    "derivation",
    "derivation_ref",
    "derivation_class",
    "derivation_state",
    "forbidden_class",
}
HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
RD_RE = re.compile(r"RD-\d{2}", re.IGNORECASE)
COORDINATION_PREFIX = "validation/coordination/"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def run_git(args, use_real_index=True):
    env = dict(os.environ)
    if use_real_index:
        # "real index" semantics even when the suite runs under a temporary
        # GIT_INDEX_FILE.
        env.pop("GIT_INDEX_FILE", None)
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def head_blob(relative):
    proc = run_git(["cat-file", "blob", "HEAD:" + relative.replace("\\", "/")])
    if proc.returncode:
        raise AssertionError(
            "not a HEAD blob: %s (%s)"
            % (relative, proc.stderr.decode("utf-8", "replace").strip())
        )
    return proc.stdout


def ancestor_exit(sha):
    return run_git(["merge-base", "--is-ancestor", sha, "HEAD"]).returncode


def find_non_ancestor():
    proc = run_git(["rev-list", "--all", "--not", "HEAD"])
    if proc.returncode:
        return None
    lines = proc.stdout.decode("utf-8", "replace").split()
    return lines[0] if lines else None


def normalize_path(value):
    text = str(value).replace("\\", "/").strip()
    text = re.sub(r"/{2,}", "/", text)
    while text.startswith("./"):
        text = text[2:]
    return text.casefold().lstrip("/")


def is_forbidden_evidence_path(value):
    """Case-insensitive rejection of validation/coordination evidence paths."""
    return normalize_path(value).startswith(COORDINATION_PREFIX)


def flatten_strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(flatten_strings(item))
        return found
    return []


def is_budget_key(key):
    lowered = key.casefold()
    if lowered == "budget_approved":
        # required false flag, never a budget carrier
        return False
    if lowered in PIN_IDS_CASEFOLD:
        # frozen pin vocabulary; validated separately, never a numeric field
        return False
    return lowered in FORBIDDEN_NUMERIC_FIELDS or "budget" in lowered or "tolerance" in lowered


class Verifier:
    """Structural verifier; check_git adds tracked-HEAD blob and ancestry probes."""

    def __init__(self, check_git=True):
        self.violations = []
        self.check_git = check_git

    def flag(self, code, message):
        self.violations.append({"code": code, "message": message})

    def codes(self):
        return [item["code"] for item in self.violations]

    def check_keys(self, value, expected, label, code):
        if not isinstance(value, dict):
            self.flag("wrong_type", "%s must be an object" % label)
            return False
        extra = set(value) - set(expected)
        missing = set(expected) - set(value)
        if extra:
            self.flag(code, "%s has unknown keys %s" % (label, sorted(extra)))
        if missing:
            self.flag("missing_required_key", "%s missing %s" % (label, sorted(missing)))
        return not extra and not missing

    def verify(self, document):
        if not isinstance(document, dict):
            self.flag("wrong_type", "document must be a JSON object")
            return self.result()

        self.check_keys(document, TOP_KEYS, "document", "unknown_top_level_key")
        if document.get("schema") != SCHEMA:
            self.flag("wrong_type", "schema must be %s" % SCHEMA)
        if document.get("kind") != KIND:
            self.flag("wrong_type", "kind must be %s" % KIND)
        if document.get("issue") != ISSUE or document.get("parent_issue") != PARENT_ISSUE:
            self.flag("wrong_type", "issue must be 59 and parent_issue must be 10")
        if document.get("effective") is not False:
            self.flag("acceptance_claim", "effective must be false")
        if document.get("budget_approved") is not False:
            self.flag("budget_approval_claim", "budget_approved must be false")
        if document.get("g6_acceptance") is not False:
            self.flag("acceptance_claim", "g6_acceptance must be false")
        if document.get("physical_accuracy") is not False:
            self.flag("acceptance_claim", "physical_accuracy must be false")
        if document.get("owner_decisions_made") is not False:
            self.flag("owner_decision_already_made", "owner_decisions_made must be false")
        if document.get("r1_status") != "numerical_failed":
            self.flag("r1_status_changed", "r1_status must remain numerical_failed")
        if document.get("issues_closed") != []:
            self.flag("closure_claim", "issues_closed must be empty")

        self.check_observed_at(document.get("observed_at"))
        self.check_policy(document.get("evidence_policy"))
        self.check_request_scope(document.get("request_scope"))
        pins = self.check_pins(document.get("pins"))
        self.check_groups(document.get("decision_groups"))
        self.check_open_items(document.get("open_items"))
        self.check_scope_limits(document.get("scope_limits"))
        self.scan(document)
        self.check_requested_set(pins)
        return self.result()

    def check_observed_at(self, observed):
        if not self.check_keys(observed, OBSERVED_KEYS, "observed_at", "unknown_top_level_key"):
            return
        if list(observed.get("required_ancestors") or []) != list(REQUIRED_ANCESTORS):
            self.flag("required_ancestor_missing", "required_ancestors must be exactly 31e5b65f and f333316e")
        if observed.get("exact_head_equality_asserted") is not False:
            self.flag("exact_head_equality_claim", "exact HEAD equality must not be asserted")
        head = observed.get("observed_head")
        if not isinstance(head, str) or not HEX40_RE.match(head):
            self.flag("wrong_type", "observed_head must be a 40-hex commit id")
        if self.check_git:
            for ancestor in REQUIRED_ANCESTORS:
                if ancestor_exit(ancestor) != 0:
                    self.flag(
                        "required_ancestor_not_ancestor",
                        "%s must be an ancestor of HEAD" % ancestor,
                    )

    def check_policy(self, policy):
        if not self.check_keys(policy, POLICY_KEYS, "evidence_policy", "unknown_top_level_key"):
            return
        if policy.get("digest_algorithm") != "sha256" or policy.get("digest_encoding") != "lowercase_hex":
            self.flag("wrong_type", "digest algorithm/encoding must be sha256/lowercase_hex")
        tracked = policy.get("tracked_pin_ids")
        if not isinstance(tracked, list) or set(tracked) != set(PINS) or len(tracked) != len(set(tracked)):
            self.flag("pin_path_not_listed", "tracked_pin_ids must be exactly the six pinned sources")
        if policy.get("max_pins") != 6:
            self.flag("pin_count_exceeded", "max_pins must be 6")
        if policy.get("forbidden_evidence_paths_case_insensitive") is not True:
            self.flag("forbidden_evidence_path", "evidence paths must be rejected case-insensitively")
        if normalize_path(policy.get("forbidden_evidence_path_prefix_casefold")) != COORDINATION_PREFIX:
            self.flag("forbidden_evidence_path", "forbidden evidence prefix must be validation/coordination/")
        if list(policy.get("forbidden_derivation_classes") or []) != list(FORBIDDEN_DERIVATIONS):
            self.flag("forbidden_derivation", "forbidden_derivation_classes must be exactly RD-01..RD-12")
        if sorted(policy.get("forbidden_numeric_fields") or []) != sorted(FORBIDDEN_NUMERIC_FIELDS):
            self.flag("forbidden_budget_key", "forbidden_numeric_fields must match the frozen budget key set")
        if sorted(policy.get("fail_closed_on") or []) != sorted(FAIL_CLOSED_ON):
            self.flag("missing_required_key", "fail_closed_on must state the frozen code set")

    def check_request_scope(self, scope):
        if not self.check_keys(scope, REQUEST_SCOPE_KEYS, "request_scope", "unknown_top_level_key"):
            return
        if scope.get("decision_group_count") != 3:
            self.flag("decision_group_count_not_three", "request_scope must declare exactly three groups")
        if list(scope.get("decision_group_keys") or []) != list(GROUP_ORDER):
            self.flag("unknown_decision_group_key", "decision_group_keys must be the three requested groups")
        if scope.get("only_these_groups_requested") is not True:
            self.flag("unknown_decision_group_key", "only_these_groups_requested must be true")
        if list(scope.get("requested_owner_decision_ids") or []) != list(REQUESTED_ODS):
            self.flag("requested_decision_set_mismatch", "only OD-01, OD-02 and OD-20 may be requested")

    def check_pins(self, pins):
        if not isinstance(pins, dict):
            self.flag("pin_missing", "pins must be an object")
            return None
        if len(pins) > 6:
            self.flag("pin_count_exceeded", "at most six sources may be pinned")
        for extra in sorted(set(pins) - set(PINS)):
            self.flag("pin_extra", "unknown pin %s" % extra)
        for missing in sorted(set(PINS) - set(pins)):
            self.flag("pin_missing", "pin %s is absent" % missing)
        for pin_id, pin in sorted(pins.items()):
            self.check_pin(pin_id, pin)
        return pins

    def check_pin(self, pin_id, pin):
        if not self.check_keys(pin, PIN_KEYS, "pins.%s" % pin_id, "unknown_top_level_key"):
            return
        if pin.get("id") != pin_id:
            self.flag("wrong_type", "pins.%s.id must echo its key" % pin_id)
        path = pin.get("path")
        expected = PINS.get(pin_id)
        if not isinstance(path, str):
            self.flag("wrong_type", "pins.%s.path must be a string" % pin_id)
            return
        if is_forbidden_evidence_path(path):
            self.flag("forbidden_evidence_path", "pins.%s points into validation/coordination" % pin_id)
        if expected is None or path != expected[0]:
            self.flag("pin_path_not_listed", "pins.%s.path is not the frozen path" % pin_id)
            return
        digest = pin.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            self.flag("pin_hash_mismatch", "pins.%s.sha256 is not a lowercase sha256" % pin_id)
        elif digest != expected[1]:
            self.flag("pin_hash_mismatch", "pins.%s.sha256 differs from the frozen digest" % pin_id)
        if pin.get("size_bytes") != expected[2]:
            self.flag("pin_size_mismatch", "pins.%s.size_bytes differs from the frozen size" % pin_id)
        if pin.get("tracked_at_head") is not True:
            self.flag("pin_not_tracked_at_head", "pins.%s must be tracked at HEAD" % pin_id)
        if not self.check_git:
            return
        try:
            blob = head_blob(path)
        except AssertionError:
            self.flag("pin_missing", "pins.%s is not a HEAD blob" % pin_id)
            return
        if sha256_bytes(blob) != expected[1]:
            self.flag("pin_hash_mismatch", "pins.%s HEAD blob digest differs" % pin_id)
        if len(blob) != expected[2]:
            self.flag("pin_size_mismatch", "pins.%s HEAD blob size differs" % pin_id)
        worktree = ROOT / path
        if not worktree.is_file():
            self.flag("pin_missing", "pins.%s worktree file is missing" % pin_id)
            return
        raw = worktree.read_bytes()
        if sha256_bytes(raw) != expected[1] or len(raw) != expected[2]:
            self.flag("pin_worktree_drift", "pins.%s worktree bytes differ from the HEAD blob" % pin_id)

    def check_groups(self, groups):
        if not isinstance(groups, list) or len(groups) != 3:
            self.flag("decision_group_count_not_three", "decision_groups must hold exactly three groups")
            return
        ids = [group.get("id") for group in groups if isinstance(group, dict)]
        if len(set(ids)) != len(ids):
            self.flag("duplicate_decision_group", "decision group ids must be unique")
        if ids != [spec[0] for spec in GROUP_SPECS]:
            self.flag("unknown_decision_group_key", "decision group ids must be DG-1, DG-2, DG-3 in order")
        if [group.get("key") for group in groups if isinstance(group, dict)] != list(GROUP_ORDER):
            self.flag("unknown_decision_group_key", "decision group keys must be the three requested keys")
        requested = []
        for index, spec in enumerate(GROUP_SPECS):
            if index >= len(groups):
                return
            group = groups[index]
            label = "decision_groups[%d]" % index
            if not self.check_keys(group, GROUP_KEYS, label, "unknown_decision_group_key"):
                continue
            self.check_group(group, spec, label, requested)
        declared = []
        for group in groups:
            declared.extend(group.get("owner_decision_ids") or [])
        if sorted(declared) != sorted(REQUESTED_ODS):
            self.flag("requested_decision_set_mismatch", "group owner_decision_ids must be exactly OD-01/OD-02/OD-20")
        self.requested = sorted(set(declared))

    def check_group(self, group, spec, label, requested):
        _, key, option_ids, slots, ods = spec
        if group.get("key") != key:
            self.flag("unknown_decision_group_key", "%s.key must be %s" % (label, key))
        if group.get("source_pin") not in PINS:
            self.flag("pin_missing", "%s.source_pin must name a pinned source" % label)
        own = group.get("owner_decision_ids")
        if not isinstance(own, list) or not all(isinstance(item, str) for item in own):
            self.flag("wrong_type", "%s.owner_decision_ids must be a list of ids" % label)
        else:
            if len(set(own)) != len(own):
                self.flag("requested_decision_set_mismatch", "%s repeats an owner decision id" % label)
            for item in own:
                if item not in REQUESTED_ODS:
                    self.flag("unknown_owner_decision_id", "%s requests unlisted %s" % (label, item))
            if list(own) != list(ods):
                self.flag("requested_decision_set_mismatch", "%s must request %s" % (label, list(ods)))
            requested.extend(own)
        if list(group.get("slots") or []) != list(slots):
            self.flag("wrong_type", "%s.slots must be the frozen slot set" % label)
        if group.get("state") != "not_made":
            self.flag("owner_decision_already_made", "%s.state must be not_made" % label)
        for field in ("chosen_option", "decided_by", "decided_utc", "decision_text"):
            if group.get(field) is not None:
                self.flag("owner_decision_already_made", "%s.%s must stay null" % (label, field))
        if group.get("derivation_ref") is not None:
            self.flag("derivation_present", "%s must not bind a derivation reference" % label)
        if group.get("derivation_class") is not None:
            self.flag("derivation_present", "%s must not bind a derivation class" % label)
        blocked = group.get("blocked_by")
        if not isinstance(blocked, list) or not blocked or set(blocked) - set(OPEN_BLOCKERS):
            self.flag("blocker_dropped", "%s.blocked_by must be a non-empty subset of B1/B3/B4" % label)
        options = group.get("options")
        if not isinstance(options, list) or [item.get("id") for item in options if isinstance(item, dict)] != list(option_ids):
            self.flag("wrong_type", "%s.options must be exactly the frozen option ids" % label)
            return
        for option_index, option in enumerate(options):
            option_label = "%s.options[%d]" % (label, option_index)
            self.check_keys(option, OPTION_KEYS, option_label, "unknown_decision_group_key")
            if not isinstance(option, dict):
                continue
            if option.get("chosen") is not False:
                self.flag("option_already_chosen", "%s.chosen must be false" % option_label)

    def check_open_items(self, open_items):
        if not self.check_keys(open_items, OPEN_ITEM_KEYS, "open_items", "unknown_top_level_key"):
            return
        if list(open_items.get("blockers_open") or []) != list(OPEN_BLOCKERS):
            self.flag("blocker_dropped", "blockers_open must be exactly B1/B3/B4")
        if not isinstance(open_items.get("blocker_notes"), dict) or set(open_items["blocker_notes"]) != set(OPEN_BLOCKERS):
            self.flag("blocker_dropped", "blocker_notes must cover exactly B1/B3/B4")
        if list(open_items.get("owner_decisions_open") or []) != list(OPEN_ODS):
            self.flag("open_decision_list_mismatch", "owner_decisions_open must be OD-03..OD-24 except OD-20")
        if list(open_items.get("issues_open") or []) != list(OPEN_ISSUES):
            self.flag("closure_claim", "issues_open must be exactly #84/G6/Full")
        if open_items.get("issues_closed") != []:
            self.flag("closure_claim", "open_items.issues_closed must be empty")
        if open_items.get("budget_approved") is not False:
            self.flag("budget_approval_claim", "open_items.budget_approved must be false")

    def check_scope_limits(self, scope):
        if not self.check_keys(scope, SCOPE_LIMIT_KEYS, "scope_limits", "unknown_top_level_key"):
            return
        if set(scope.get("writable_files") or []) != set(CANDIDATE_PATHS):
            self.flag("mutation_scope_claim", "writable_files must be exactly the three deliverables")
        for flag_name in SCOPE_FALSE_FLAGS:
            if scope.get(flag_name) is not False:
                self.flag("mutation_scope_claim", "scope_limits.%s must be false" % flag_name)

    def check_requested_set(self, pins):
        groups = self.requested if hasattr(self, "requested") else []
        overlap = sorted(set(groups) & set(OPEN_ODS))
        if overlap:
            self.flag("open_decision_list_mismatch", "requested ids may not also be listed open: %s" % overlap)
        if set(groups) | set(OPEN_ODS) != set(REQUESTED_ODS) | set(OPEN_ODS) or len(set(groups) | set(OPEN_ODS)) != 24:
            self.flag("requested_decision_set_mismatch", "OD-01..OD-24 must partition into requested and open ids")

    def scan(self, value, in_policy=False):
        if isinstance(value, dict):
            for key, item in value.items():
                nested_policy = in_policy or key == "evidence_policy"
                if not in_policy:
                    if is_budget_key(key):
                        if isinstance(item, bool) or not isinstance(item, (int, float)):
                            self.flag("forbidden_budget_key", "forbidden numeric field %r" % key)
                        else:
                            self.flag("numeric_budget_present", "numeric budget value in %r" % key)
                    if key in PATH_KEYS:
                        for text in flatten_strings(item):
                            if is_forbidden_evidence_path(text):
                                self.flag("forbidden_evidence_path", "%s is not admissible evidence" % text)
                    if key in DERIVATION_KEYS:
                        for text in flatten_strings(item):
                            if RD_RE.search(text):
                                self.flag("forbidden_derivation", "%s uses a forbidden derivation class" % text)
                self.scan(item, nested_policy)
        elif isinstance(value, list):
            for item in value:
                self.scan(item, in_policy)

    def result(self):
        return {
            "status": "verified" if not self.violations else "rejected",
            "budget_approved": False,
            "g6_acceptance": False,
            "physical_accuracy": False,
            "codes": self.codes(),
            "reasons": [item["message"] for item in self.violations],
        }


def verify_request(document, check_git=True):
    return Verifier(check_git=check_git).verify(document)


def load_request():
    return json.loads(JSON_PATH.read_bytes().decode("utf-8"))


def mutate_request(mutator):
    document = load_request()
    mutator(document)
    return verify_request(document, check_git=False)


class RealRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_request()

    def test_request_verifies_and_claims_nothing(self):
        result = verify_request(self.document)
        self.assertEqual(result["status"], "verified", result["reasons"])
        for field in ("budget_approved", "g6_acceptance", "physical_accuracy"):
            self.assertFalse(self.document[field])
            self.assertFalse(result[field])
        self.assertFalse(self.document["effective"])
        self.assertFalse(self.document["owner_decisions_made"])
        self.assertEqual(self.document["r1_status"], "numerical_failed")
        self.assertEqual(self.document["issues_closed"], [])
        for flag_name in SCOPE_FALSE_FLAGS:
            self.assertFalse(self.document["scope_limits"][flag_name], flag_name)

    def test_exactly_three_decision_groups(self):
        groups = self.document["decision_groups"]
        self.assertEqual(len(groups), 3)
        self.assertEqual([group["id"] for group in groups], ["DG-1", "DG-2", "DG-3"])
        self.assertEqual([group["key"] for group in groups], list(GROUP_ORDER))
        self.assertEqual(self.document["request_scope"]["decision_group_count"], 3)
        self.assertTrue(self.document["request_scope"]["only_these_groups_requested"])
        self.assertEqual(
            set(self.document["request_scope"]["decision_group_keys"]), set(GROUP_ORDER)
        )
        for group, spec in zip(groups, GROUP_SPECS):
            self.assertEqual(set(group), set(GROUP_KEYS))
            self.assertEqual(tuple(group["slots"]), spec[3])
            self.assertEqual(set(group["options"][0]), set(OPTION_KEYS))

    def test_all_decision_states_not_made(self):
        for group in self.document["decision_groups"]:
            self.assertEqual(group["state"], "not_made")
            for field in ("chosen_option", "decided_by", "decided_utc", "decision_text"):
                self.assertIsNone(group[field], "%s.%s" % (group["key"], field))
            self.assertTrue(all(option["chosen"] is False for option in group["options"]))
            self.assertIsNone(group["derivation_class"])
            self.assertIsNone(group["derivation_ref"])
            self.assertTrue(set(group["blocked_by"]) <= set(OPEN_BLOCKERS))
        self.assertFalse(self.document["owner_decisions_made"])

    def test_no_numeric_budget_anywhere(self):
        found = []

        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if is_budget_key(key):
                        found.append(key)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(self.document)
        self.assertEqual(found, [])
        self.assertFalse(self.document["budget_approved"])
        self.assertFalse(self.document["open_items"]["budget_approved"])
        self.assertEqual(
            sorted(self.document["evidence_policy"]["forbidden_numeric_fields"]),
            sorted(FORBIDDEN_NUMERIC_FIELDS),
        )

    def test_six_sources_pinned_at_tracked_head(self):
        pins = self.document["pins"]
        self.assertEqual(set(pins), set(PINS))
        self.assertEqual(len(pins), 6)
        self.assertEqual(self.document["evidence_policy"]["max_pins"], 6)
        for pin_id, (path, digest, size) in PINS.items():
            pin = pins[pin_id]
            self.assertEqual(pin["path"], path)
            self.assertEqual(pin["sha256"], digest)
            self.assertEqual(pin["size_bytes"], size)
            self.assertIs(pin["tracked_at_head"], True)
            blob = head_blob(path)
            self.assertEqual(sha256_bytes(blob), digest)
            self.assertEqual(len(blob), size)
            raw = (ROOT / path).read_bytes()
            self.assertEqual(sha256_bytes(raw), digest)
            self.assertEqual(len(raw), size)
            self.assertFalse(is_forbidden_evidence_path(path))

    def test_ancestry_required_without_exact_head_equality(self):
        observed = self.document["observed_at"]
        self.assertEqual(tuple(observed["required_ancestors"]), REQUIRED_ANCESTORS)
        self.assertIs(observed["exact_head_equality_asserted"], False)
        self.assertTrue(HEX40_RE.match(observed["observed_head"]))
        for ancestor in REQUIRED_ANCESTORS:
            self.assertEqual(ancestor_exit(ancestor), 0, ancestor)
        self.assertNotEqual(ancestor_exit("0" * 40), 0)
        unrelated = find_non_ancestor()
        if unrelated:
            self.assertNotEqual(ancestor_exit(unrelated), 0)

    def test_open_items_preserved(self):
        open_items = self.document["open_items"]
        self.assertEqual(tuple(open_items["blockers_open"]), OPEN_BLOCKERS)
        self.assertEqual(set(open_items["blocker_notes"]), set(OPEN_BLOCKERS))
        self.assertEqual(tuple(open_items["owner_decisions_open"]), OPEN_ODS)
        self.assertNotIn("OD-20", open_items["owner_decisions_open"])
        self.assertNotIn("OD-01", open_items["owner_decisions_open"])
        self.assertNotIn("OD-02", open_items["owner_decisions_open"])
        self.assertEqual(tuple(open_items["issues_open"]), OPEN_ISSUES)
        self.assertEqual(open_items["issues_closed"], [])
        self.assertEqual(self.document["issues_closed"], [])
        self.assertFalse(open_items["budget_approved"])

    def test_questions_match_pinned_frame_datum_binding(self):
        binding_path = ROOT / self.document["pins"]["frame_datum_binding"]["path"]
        binding = json.loads(binding_path.read_bytes().decode("utf-8"))
        catalog = {entry["id"]: entry for entry in binding["owner_decisions"]}
        groups = {group["key"]: group for group in self.document["decision_groups"]}
        for key in ("od01_od02_scheduling_time_semantics", "od20_active_vs_extra_motor_output_scope"):
            group = groups[key]
            self.assertTrue(group["owner_decision_ids"])
            for od in group["owner_decision_ids"]:
                entry = catalog[od]
                self.assertEqual(entry["state"], "not_made")
                self.assertIn(entry["question"], group["question"])
                self.assertEqual(set(entry["slots"]), set(group["slots"]))
        solve = groups["solve_form_choice"]
        solve_packet = json.loads(
            (ROOT / self.document["pins"]["solve_form_decision"]["path"]).read_bytes().decode("utf-8")
        )
        self.assertEqual(solve["state"], solve_packet["owner_decision"]["state"])
        self.assertEqual(
            [option["id"] for option in solve["options"]],
            [option["id"] for option in solve_packet["owner_options"]],
        )
        self.assertTrue(all(option["chosen"] is False for option in solve_packet["owner_options"]))

    def test_markdown_requests_without_closing_anything(self):
        text = MD_PATH.read_text(encoding="utf-8")
        for token in (
            "not_made",
            "r1_status=numerical_failed",
            "budget_approved=false",
            "g6_acceptance=false",
            "physical_accuracy=false",
            "issues_closed=[]",
            "RD-01",
            "RD-12",
            REQUIRED_ANCESTORS[0],
            REQUIRED_ANCESTORS[1],
            COORDINATION_PREFIX,
            "OD-01",
            "OD-02",
            "OD-20",
        ):
            self.assertIn(token, text, token)
        self.assertNotIn("G6/Full 已通过", text)
        self.assertIn("不是数值验收或 G6 通过", text)


class MutationTests(unittest.TestCase):
    def test_fourth_decision_group_rejected(self):
        def mutate(document):
            group = json.loads(json.dumps(document["decision_groups"][0]))
            group["id"] = "DG-4"
            group["key"] = "extra_group"
            document["decision_groups"].append(group)

        result = mutate_request(mutate)
        self.assertIn("decision_group_count_not_three", result["codes"])

    def test_unknown_decision_group_key_rejected(self):
        def mutate(document):
            document["decision_groups"][0]["key"] = "solve_form_scope"

        result = mutate_request(mutate)
        self.assertIn("unknown_decision_group_key", result["codes"])

    def test_owner_choice_rejected(self):
        def mutate(document):
            document["decision_groups"][0]["options"][0]["chosen"] = True
            document["decision_groups"][0]["state"] = "made"
            document["decision_groups"][0]["chosen_option"] = "adopt_diagonal_branch"

        result = mutate_request(mutate)
        self.assertIn("owner_decision_already_made", result["codes"])
        self.assertIn("option_already_chosen", result["codes"])

    def test_numeric_budget_rejected(self):
        def mutate(document):
            document["open_items"]["abs_budget"] = 0.5

        result = mutate_request(mutate)
        self.assertIn("numeric_budget_present", result["codes"])

    def test_budget_approval_flag_rejected(self):
        def mutate(document):
            document["budget_approved"] = True

        result = mutate_request(mutate)
        self.assertIn("budget_approval_claim", result["codes"])

    def test_closure_claim_rejected(self):
        def mutate(document):
            document["issues_closed"] = ["#59"]

        result = mutate_request(mutate)
        self.assertIn("closure_claim", result["codes"])

    def test_acceptance_flip_rejected(self):
        def mutate(document):
            document["g6_acceptance"] = True
            document["physical_accuracy"] = True

        result = mutate_request(mutate)
        self.assertIn("acceptance_claim", result["codes"])
        self.assertFalse(result["g6_acceptance"])
        self.assertFalse(result["physical_accuracy"])

    def test_r1_status_change_rejected(self):
        def mutate(document):
            document["r1_status"] = "declared_cases_pass"

        result = mutate_request(mutate)
        self.assertIn("r1_status_changed", result["codes"])

    def test_blocker_dropped_rejected(self):
        def mutate(document):
            document["open_items"]["blockers_open"].remove("B3")

        result = mutate_request(mutate)
        self.assertIn("blocker_dropped", result["codes"])

    def test_open_decision_list_changes_rejected(self):
        def drop(document):
            document["open_items"]["owner_decisions_open"].remove("OD-15")

        def add(document):
            document["open_items"]["owner_decisions_open"].append("OD-20")

        self.assertIn("open_decision_list_mismatch", mutate_request(drop)["codes"])
        self.assertIn("open_decision_list_mismatch", mutate_request(add)["codes"])

    def test_forbidden_derivation_rejected(self):
        def mutate(document):
            document["decision_groups"][1]["derivation_class"] = "RD-01"

        result = mutate_request(mutate)
        self.assertIn("forbidden_derivation", result["codes"])

    def test_non_null_derivation_rejected(self):
        def mutate(document):
            document["decision_groups"][2]["derivation_ref"] = "docs/plan/some-derivation.md"

        result = mutate_request(mutate)
        self.assertIn("derivation_present", result["codes"])

    def test_coordination_pin_path_rejected(self):
        def mutate(document):
            document["pins"]["solve_form_decision"]["path"] = (
                "VALIDATION//Coordination/g6-target-mrdivide-20260913/first-step-trace.jsonl"
            )

        result = mutate_request(mutate)
        self.assertIn("forbidden_evidence_path", result["codes"])

    def test_forbidden_path_detector_is_case_insensitive(self):
        for value in (
            "validation/coordination/x.json",
            "VALIDATION/COORDINATION/x.json",
            "Validation\\Coordination\\x.json",
            "./validation//coordination/x.json",
            "  validation/coordination/  ",
        ):
            self.assertTrue(is_forbidden_evidence_path(value), value)
        for value in (
            "validation/e0-frame-datum-binding-20260914.json",
            "docs/coordination/short-cycle-goal.md",
            "validation/COORDINATION-notes.md",
        ):
            self.assertFalse(is_forbidden_evidence_path(value), value)

    def test_pin_missing_or_extra_rejected(self):
        def drop(document):
            del document["pins"]["r1_contract"]

        def add(document):
            document["pins"]["bonus"] = json.loads(json.dumps(document["pins"]["r1_contract"]))

        self.assertIn("pin_missing", mutate_request(drop)["codes"])
        self.assertIn("pin_extra", mutate_request(add)["codes"])

    def test_pin_hash_or_size_tamper_rejected(self):
        def hash_tamper(document):
            document["pins"]["r1_contract"]["sha256"] = "0" * 64

        def size_tamper(document):
            document["pins"]["r1_contract"]["size_bytes"] = 29847

        self.assertIn("pin_hash_mismatch", mutate_request(hash_tamper)["codes"])
        self.assertIn("pin_size_mismatch", mutate_request(size_tamper)["codes"])

    def test_pin_tracking_and_path_flags_rejected(self):
        def untracked(document):
            document["pins"]["frame_datum_binding"]["tracked_at_head"] = False

        def unlisted(document):
            document["pins"]["frame_datum_binding"]["path"] = "docs/plan/unknown-evidence.md"

        self.assertIn("pin_not_tracked_at_head", mutate_request(untracked)["codes"])
        self.assertIn("pin_path_not_listed", mutate_request(unlisted)["codes"])

    def test_unknown_top_level_key_rejected(self):
        def mutate(document):
            document["closure_claim"] = False

        result = mutate_request(mutate)
        self.assertIn("unknown_top_level_key", result["codes"])


@unittest.skipUnless(
    os.environ.get("WKSIM_59_ODR_TEMP_INDEX") == "1",
    "only meaningful in the repo-external temporary GIT_INDEX_FILE run",
)
class TemporaryIndexTests(unittest.TestCase):
    """With a repo-external GIT_INDEX_FILE, exactly the three deliverables are
    staged at stage 0 with blob bytes identical to the working tree, and the
    real index still stages none of them."""

    def test_exactly_three_candidates_staged(self):
        index_file = os.environ.get("GIT_INDEX_FILE")
        self.assertTrue(index_file, "GIT_INDEX_FILE must point at a repo-external index")
        index_path = Path(index_file).resolve()
        self.assertFalse(
            str(index_path).startswith(str(ROOT.resolve())),
            "the temporary index must live outside the repository",
        )
        proc = run_git(["ls-files"], use_real_index=False)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        staged = proc.stdout.decode("utf-8", "replace").splitlines()
        self.assertEqual(set(staged), set(CANDIDATE_PATHS), sorted(staged))
        for relative in CANDIDATE_PATHS:
            listing = run_git(["ls-files", "-s", "--", relative], use_real_index=False)
            self.assertEqual(listing.returncode, 0)
            rows = [row for row in listing.stdout.decode("utf-8", "replace").splitlines() if row.strip()]
            self.assertEqual(len(rows), 1, relative)
            mode, blob_sha, stage, _path = rows[0].split(None, 3)
            self.assertEqual(stage, "0", relative)
            self.assertIn(mode, ("100644", "100755"), relative)
            blob = run_git(["cat-file", "blob", blob_sha], use_real_index=False)
            self.assertEqual(blob.returncode, 0, relative)
            self.assertEqual(blob.stdout, (ROOT / relative).read_bytes(), relative)

    def test_real_index_stages_none_of_the_candidates(self):
        proc = run_git(["ls-files"])
        self.assertEqual(proc.returncode, 0)
        real = set(proc.stdout.decode("utf-8", "replace").splitlines())
        for relative in CANDIDATE_PATHS:
            self.assertNotIn(relative, real, "real index must not stage " + relative)
        # a tracked pinned source is still present and byte-identical in the
        # real index, so the temporary index did not disturb it
        for relative in ("Simulator/wksim_core/numerical-conformance-v1.json",):
            listing = run_git(["ls-files", "-s", "--", relative])
            self.assertEqual(listing.returncode, 0)
            self.assertIn(relative, listing.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
