"""Pure offline tests for the PROPOSED #9 vendor-ABI defer boundary.

Run from the repository root::

    python -B validation/test_issue_9_defer_boundary.py

The test never loads a DLL, never runs native/model/ROS/FC/UE/MATLAB/build or
#83 work, never touches the network and never mutates git or GitHub.  It reads
the tracked contract, re-hashes every decision-affecting pin against the
worktree bytes and the committed ``HEAD`` blob, and then proves the verifier
itself fails closed by replaying the contract from a scratch copy with
targeted mutations.
"""

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_RELATIVE = "docs/plan/9-vendor-abi-defer-boundary.json"
CONTRACT = ROOT / CONTRACT_RELATIVE
MARKDOWN_RELATIVE = "docs/plan/9-vendor-abi-defer-boundary.md"
TEST_RELATIVE = "validation/test_issue_9_defer_boundary.py"

SCHEMA = "wksim.9-vendor-abi-defer-boundary.v1"
KIND = "branch_isolation_contract"
AFFECTED = [27, 28, 73, 74, 76, 77, 78]
UNAFFECTED = [26, 29]
MUST_REMAIN_OPEN = sorted([9, 26, 27, 28, 29, 73, 74, 76, 77, 78])
VENDOR_PIN_IDS = {"abi_accepted", "abi_evidence", "vendor_control_wrapper"}
NATIVE_PIN_IDS = [
    "native_ac_evidence",
    "native_model_cpp",
    "native_model_py",
    "native_terrain_probe_result",
]
HOST_EXTERNAL_PIN_IDS = ["vendor_control_wrapper", "vendor_sample_dll"]
NATIVE_TERRAIN_DIMENSION = 15
NATIVE_EXPORT_SYMBOLS = [
    "wk_model_create",
    "wk_model_destroy",
    "wk_model_initial_state",
    "wk_model_step",
    "wk_model_step_with_terrain",
]
TERRAIN_BLOCKER_ID = "B-9-TERRAIN-THREE-WAY-SHAPE"
PERMITTED_ARTIFACTS = sorted([CONTRACT_RELATIVE, MARKDOWN_RELATIVE, TEST_RELATIVE])

TOP_KEYS = {
    "schema",
    "kind",
    "issue",
    "layer",
    "authority",
    "effective",
    "date",
    "title",
    "purpose",
    "claim_text",
    "observed_at",
    "evidence_policy",
    "observed",
    "policy",
    "owner_decision",
    "recommendation",
    "evidence_pins",
    "host_bounded_gaps",
    "unresolved_blockers",
    "scope_limits",
    "non_claims",
}
OBSERVED_AT_KEYS = {
    "head",
    "branch",
    "baseline_ancestor",
    "origin_main",
    "baseline_ancestor_is_ancestor_of_head",
    "recorded_utc",
}
EVIDENCE_POLICY_KEYS = {
    "digest_algorithm",
    "digest_encoding",
    "evidence_class_decision_affecting",
    "evidence_class_context_only",
    "require_tracked_at_head",
    "fail_closed_on",
}
FAIL_CLOSED_ON = {
    "unknown_key",
    "missing_key",
    "duplicate_key",
    "wrong_type",
    "uppercase_or_malformed_digest",
    "unreadable_path",
    "path_not_tracked_at_head",
    "path_absent_from_head_tree",
    "digest_mismatch_worktree",
    "digest_mismatch_head_blob",
    "host_external_digest_mismatch_when_present",
    "host_external_pin_promoted_to_decision",
    "rejection_or_closure_or_acceptance_claim",
    "owner_decision_made",
    "dependency_satisfied_by_defer",
    "native_vendor_shared_dependency",
    "native_path_vendor_reference",
    "affected_or_closure_set_drift",
    "issue_action_performed",
}
OBSERVED_KEYS = {
    "vendor_dll_abi_availability",
    "three_way_terrain_shape_contradiction",
    "native_wk_model_abi_path",
    "native_vendor_isolation",
    "observed_tickets",
    "issue_state_snapshot",
    "open_dependency_edges_preserved",
}
VENDOR_AVAILABILITY_KEYS = {
    "status",
    "conclusion",
    "unlock_preconditions_source",
    "unlock_preconditions_count",
    "unlock_preconditions",
    "official_source_gaps",
    "unavailable_count",
    "unavailable_of_total",
    "evidence_pin_ids",
    "note",
}
TERRAIN_CONTRADICTION_KEYS = {
    "evidence_pin_ids",
    "observations",
    "contradiction",
    "resolution_gap",
    "wksim_native_impact",
    "wksim_native_reason",
    "native_evidence_pin_ids",
    "blocks_issue_ids",
    "does_not_block_issue_ids",
    "role",
}
NATIVE_PATH_KEYS = {
    "status",
    "evidence_pin_ids",
    "exported_symbols",
    "export_declaration_file",
    "export_declaration_lines",
    "terrain_argument_guard_line",
    "python_declaration_lines",
    "terrain_path_lines",
    "declared_return_codes",
    "reviewed_evidence_pin_id",
    "reviewed_evidence_summary",
    "legacy_vendor_abi_compatibility_claimed",
    "isolated_from_vendor_abi",
    "evidence_that_observation_is_repository_local",
}
ISOLATION_KEYS = {
    "shared_media_files",
    "native_path_may_be_used_without_vendor_abi",
    "vendor_path_may_be_used_from_inferred_shapes",
    "native_evidence_pin_ids",
    "vendor_evidence_pin_ids",
    "rule",
}
OBSERVED_TICKET_KEYS = {
    "state",
    "parent_dependencies",
    "open_dependency_on_9",
    "role",
}
ISSUE_STATE_SNAPSHOT_KEYS = {"source", "read_only", "note", "issues"}
DEPENDENCY_EDGE_KEYS = {
    "issue",
    "depends_on_issue",
    "state",
    "satisfied_by_this_defer",
    "evidence_pin_ids",
}
POLICY_KEYS = {
    "defer_class",
    "rejection_class",
    "closure_class",
    "affected",
    "does_not_affect",
    "must_remain_open",
    "closure_requires",
    "acceptance_claimed",
    "acceptance_status_recommended",
    "implementation_authorized",
    "adr_required_before_any_acceptance",
}
OWNER_DECISION_KEYS = {
    "state",
    "made_by",
    "recorded_utc",
    "undecided_option",
    "observed_owner_evidence",
    "observed_owner_evidence_count",
    "observed_evidence_interpretation",
    "rejection_evidence_found",
    "rejection_decided",
    "closure_decided",
    "decision_text",
    "must_not_be_inferred_from_this_record",
}
RECOMMENDATION_KEYS = {
    "this_record_effect",
    "recommendation_scope",
    "defer_vendor_dll_abi",
    "reject_vendor_dll_abi",
    "close_issue_9",
    "close_issue_26",
    "close_issue_29",
    "native_path_remains_usable",
    "recommended_actions",
    "label_recommendations",
    "comment_recommendations",
    "proposed_actions",
}
PROPOSED_ACTIONS_KEYS = {
    "closure_performed",
    "rejection_performed",
    "label_change_performed",
    "comment_posted",
    "acceptance_granted",
    "github_mutated",
}
SCOPE_LIMITS_KEYS = {
    "tracked_artifacts_created",
    "native_run_performed",
    "model_run_performed",
    "ue_run_performed",
    "ros_or_dds_run_performed",
    "fc_or_sitl_run_performed",
    "matlab_run_performed",
    "build_performed",
    "issue_83_touched",
    "vendor_dll_loaded",
    "vendor_install_modified",
    "github_mutated",
    "existing_files_edited",
    "git_staging_performed",
}
BLOCKER_KEYS = {
    "blocker_id",
    "severity",
    "statement",
    "blocks",
    "does_not_block",
    "evidence_pin_ids",
}
HOST_GAP_KEYS = {
    "vendor_header_absence",
    "environment_acceptance_json",
    "audit_report",
    "audit_evidence_json",
    "interface_decision_packet",
    "acceptance_frontier",
}
UNTRACKED_GAP_KEYS = {"path", "sha256", "tracked", "reason"}

# Markers used to detect a claim of rejection, closure or acceptance in text.
FORBIDDEN_CLAIM_PHRASES = (
    "rejected",
    "wontfix",
    "abandoned",
    "closed",
    "acceptance granted",
    "accepted",
    "abi approved",
    "dll abi compatible",
)
NEGATION_MARKERS = (
    "not ",
    "no ",
    "never",
    "does not",
    "do not",
    "cannot",
    "without",
    "neither",
    "undecided",
    "not_decided",
)
CLAIM_UNIT_KEYS = {
    "acceptance_claimed",
    "acceptance_granted",
    "closure_decided",
    "rejection_decided",
    "rejection_evidence_found",
    "closure_performed",
    "rejection_performed",
}
# Only these declared prose fields are scanned for a forbidden claim; every
# other string in the document is an identifier, path or enum value.
CLAIM_PROSE_FIELDS = {
    "claim_text",
    "observed.vendor_dll_abi_availability.note",
    "observed.three_way_terrain_shape_contradiction.contradiction",
    "observed.three_way_terrain_shape_contradiction.resolution_gap",
    "observed.three_way_terrain_shape_contradiction.wksim_native_reason",
    "observed.native_wk_model_abi_path.reviewed_evidence_summary",
    "observed.native_vendor_isolation.rule",
    "owner_decision.undecided_option",
    "owner_decision.observed_evidence_interpretation",
    "unresolved_blockers[0].statement",
    "unresolved_blockers[1].statement",
}


class MissingDecision(Exception):
    """Raised when the contract itself is absent or not readable from git."""


def _reject_constant(name):
    raise ValueError(f"non-finite JSON constant {name}")


def load_document(path):
    """Load a contract document, rejecting duplicate keys and non-finite numbers."""

    def pairs_hook(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise ValueError(f"duplicate key {key!r}")
            seen.add(key)
        return dict(pairs)

    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=_reject_constant)


class Verifier:
    """Fail-closed verifier for the defer-boundary contract.

    Every violation is reported as ``"<code>: <detail>"`` so callers can assert
    on the exact failure mode instead of merely observing that something broke.
    """

    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.violations = []
        self._document = {}
        self._pins = {}
        self._tracked = None
        self._blobs = None

    # -- reporting ---------------------------------------------------------

    def flag(self, code, detail):
        self.violations.append(f"{code}: {detail}")

    def codes(self):
        return {item.split(":", 1)[0] for item in self.violations}

    # -- read-only git helpers --------------------------------------------

    def _git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def tracked_paths(self):
        if self._tracked is None:
            result = self._git("ls-files", "-z")
            if result.returncode != 0:
                raise MissingDecision(f"git ls-files failed: {result.stderr.strip()}")
            self._tracked = {item for item in result.stdout.split("\0") if item}
        return self._tracked

    def head_paths(self):
        if self._blobs is None:
            result = self._git("ls-tree", "-r", "-z", "--name-only", "HEAD")
            if result.returncode != 0:
                raise MissingDecision(f"git ls-tree HEAD failed: {result.stderr.strip()}")
            self._blobs = {item for item in result.stdout.split("\0") if item}
        return self._blobs

    def head_bytes(self, relative):
        result = subprocess.run(
            ["git", "cat-file", "blob", f"HEAD:{relative}"],
            cwd=self.root,
            check=False,
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    # -- primitive checks --------------------------------------------------

    def digest_is_canonical(self, value, label):
        if not isinstance(value, str):
            self.flag("wrong_type", f"{label}: digest must be a string")
            return False
        if len(value) != 64:
            self.flag("malformed_digest", f"{label}: digest length {len(value)} is not 64")
            return False
        if value != value.lower():
            self.flag("uppercase_digest", f"{label}: digest is not lower-case")
            return False
        if any(character not in "0123456789abcdef" for character in value):
            self.flag("malformed_digest", f"{label}: digest is not lower-case hex")
            return False
        return True

    def check_keys(self, value, expected, label):
        if not isinstance(value, dict):
            self.flag("wrong_type", f"{label}: expected an object")
            return
        actual = set(value)
        for key in sorted(expected - actual):
            self.flag("missing_key", f"{label}: missing key {key}")
        for key in sorted(actual - expected):
            self.flag("unknown_key", f"{label}: unknown key {key}")

    @staticmethod
    def is_repository_relative(path):
        if not isinstance(path, str) or not path:
            return False
        if path.startswith("/") or path.startswith("\\"):
            return False
        if ":" in path.split("/")[0]:
            return False
        parts = path.replace("\\", "/").split("/")
        return all(part not in ("", ".", "..") for part in parts)

    # -- document sections -------------------------------------------------

    def check_pin(self, pin_id, pin):
        label = f"evidence_pins.{pin_id}"
        if not isinstance(pin, dict):
            self.flag("wrong_type", f"{label}: expected an object")
            return
        evidence_class = pin.get("evidence_class")
        if evidence_class == "committed_repository_artifact":
            self.check_keys(pin, {"evidence_class", "path", "sha256", "role"}, label)
            path = pin.get("path")
            if not self.is_repository_relative(path):
                self.flag(
                    "path_not_tracked_at_head",
                    f"{label}: decision-affecting pin path is not repository-relative: {path!r}",
                )
                return
            if not self.digest_is_canonical(pin.get("sha256"), label):
                return
            if path not in self.tracked_paths():
                self.flag("path_not_tracked_at_head", f"{label}: {path} is not tracked")
            if path not in self.head_paths():
                self.flag("path_absent_from_head_tree", f"{label}: {path} is absent from HEAD")
            candidate = self.root / path
            if not candidate.is_file():
                self.flag("unreadable_path", f"{label}: {path} is not a readable regular file")
                return
            digest = pin["sha256"]
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != digest:
                self.flag(
                    "digest_mismatch_worktree",
                    f"{label}: worktree digest {actual} != pinned {digest}",
                )
            if path in self.head_paths():
                blob = self.head_bytes(path)
                if blob is None:
                    self.flag(
                        "path_absent_from_head_tree", f"{label}: HEAD blob for {path} unreadable"
                    )
                elif hashlib.sha256(blob).hexdigest() != digest:
                    self.flag(
                        "digest_mismatch_head_blob",
                        f"{label}: HEAD blob digest differs from pinned {digest}",
                    )
        elif evidence_class == "host_external_read_only":
            self.check_keys(
                pin, {"evidence_class", "path", "sha256", "role", "authority"}, label
            )
            if pin.get("authority") != "context_only":
                self.flag(
                    "host_external_pin_promoted_to_decision",
                    f"{label}: host-external pin authority must be context_only",
                )
            self.digest_is_canonical(pin.get("sha256"), label)
            external = Path(str(pin.get("path")))
            if external.is_file():
                actual = hashlib.sha256(external.read_bytes()).hexdigest()
                if actual != pin.get("sha256"):
                    self.flag(
                        "host_external_digest_mismatch_when_present",
                        f"{label}: host copy digest {actual} != pinned {pin.get('sha256')}",
                    )
        else:
            self.flag("wrong_type", f"{label}: unsupported evidence_class {evidence_class!r}")

    def check_pin_references(self, pin_ids, label):
        if not isinstance(pin_ids, list) or not pin_ids:
            self.flag("missing_key", f"{label}: evidence_pin_ids must be a non-empty list")
            return
        for pin_id in pin_ids:
            if pin_id not in self._pins:
                self.flag("missing_key", f"{label}: referenced pin {pin_id!r} is not defined")

    def check_identity(self, document):
        if document.get("schema") != SCHEMA:
            self.flag("wrong_type", f"schema must be {SCHEMA}")
        if document.get("kind") != KIND:
            self.flag("wrong_type", f"kind must be {KIND}")
        if document.get("issue") != 9:
            self.flag("wrong_type", "issue must be 9")
        if document.get("layer") != "proposed":
            self.flag("wrong_type", "layer must be proposed")
        if document.get("authority") != "proposal_only":
            self.flag("wrong_type", "authority must be proposal_only")
        if document.get("effective") is not False:
            self.flag("acceptance_claim", "effective must be false for a PROPOSED record")
        claim_text = document.get("claim_text")
        if not isinstance(claim_text, str) or not claim_text:
            self.flag("missing_key", "claim_text must state the record's own bounded claim")

    def check_observed_at(self, document):
        observed_at = document.get("observed_at")
        self.check_keys(observed_at, OBSERVED_AT_KEYS, "observed_at")
        if not isinstance(observed_at, dict):
            return
        for key in ("head", "origin_main"):
            value = observed_at.get(key)
            if not isinstance(value, str) or len(value) != 40 or value != value.lower():
                self.flag(
                    "wrong_type", f"observed_at.{key} must be a 40-character lower-case commit id"
                )
        if observed_at.get("branch") != "main":
            self.flag("wrong_type", "observed_at.branch must be main")
        ancestor = observed_at.get("baseline_ancestor")
        if not isinstance(ancestor, str) or len(ancestor) != 40:
            self.flag("wrong_type", "observed_at.baseline_ancestor must be a 40-character commit id")
        if observed_at.get("baseline_ancestor_is_ancestor_of_head") is not True:
            self.flag("wrong_type", "the baseline ancestor must be recorded as an ancestor of HEAD")
        if observed_at.get("head") != observed_at.get("origin_main"):
            self.flag("wrong_type", "observed HEAD must match origin/main in the recorded observation")

    def check_evidence_policy(self, document):
        policy = document.get("evidence_policy")
        self.check_keys(policy, EVIDENCE_POLICY_KEYS, "evidence_policy")
        if not isinstance(policy, dict):
            return
        if policy.get("digest_algorithm") != "sha256":
            self.flag("wrong_type", "evidence_policy.digest_algorithm must be sha256")
        if policy.get("digest_encoding") != "lowercase_hex":
            self.flag("wrong_type", "evidence_policy.digest_encoding must be lowercase_hex")
        if policy.get("evidence_class_decision_affecting") != "committed_repository_artifact":
            self.flag(
                "wrong_type",
                "decision-affecting evidence class must be committed_repository_artifact",
            )
        if policy.get("evidence_class_context_only") != "host_external_read_only":
            self.flag("wrong_type", "context-only evidence class must be host_external_read_only")
        if policy.get("require_tracked_at_head") is not True:
            self.flag("path_not_tracked_at_head", "pins must be required to be tracked at HEAD")
        actual = set(policy.get("fail_closed_on") or [])
        if actual != FAIL_CLOSED_ON:
            self.flag(
                "affected_or_closure_set_drift",
                "evidence_policy.fail_closed_on differs: missing "
                f"{sorted(FAIL_CLOSED_ON - actual)}, extra {sorted(actual - FAIL_CLOSED_ON)}",
            )

    def check_vendor_availability(self, observed):
        availability = observed.get("vendor_dll_abi_availability")
        self.check_keys(
            availability, VENDOR_AVAILABILITY_KEYS, "observed.vendor_dll_abi_availability"
        )
        if not isinstance(availability, dict):
            return
        if availability.get("status") != "official_source_unavailable":
            self.flag("wrong_type", "vendor availability status must be official_source_unavailable")
        if availability.get("conclusion") != (
            "deferred_pending_official_header_and_authorized_sample"
        ):
            self.flag("wrong_type", "vendor availability conclusion must record the defer condition")
        if availability.get("unlock_preconditions_count") != 5:
            self.flag("wrong_type", "exactly five unlock preconditions must be recorded")
        preconditions = availability.get("unlock_preconditions")
        if not isinstance(preconditions, list) or len(preconditions) != 5:
            self.flag("wrong_type", "unlock_preconditions must list exactly five entries")
        gaps = availability.get("official_source_gaps")
        if not isinstance(gaps, list) or len(gaps) != 8:
            self.flag("wrong_type", "exactly eight official-source ABI items must be listed")
        else:
            for index, gap in enumerate(gaps):
                self.check_keys(
                    gap, {"abi_item", "observed"}, f"official_source_gaps[{index}]"
                )
                if isinstance(gap, dict) and gap.get("observed") != "absent":
                    self.flag(
                        "wrong_type", f"official_source_gaps[{index}] must be recorded absent"
                    )
        if availability.get("unavailable_count") != 8:
            self.flag("wrong_type", "unavailable_count must be 8")
        if availability.get("unavailable_of_total") != 8:
            self.flag("wrong_type", "unavailable_of_total must be 8")
        self.check_pin_references(
            availability.get("evidence_pin_ids"), "observed.vendor_dll_abi_availability"
        )

    def check_terrain_contradiction(self, observed):
        contradiction = observed.get("three_way_terrain_shape_contradiction")
        self.check_keys(
            contradiction,
            TERRAIN_CONTRADICTION_KEYS,
            "observed.three_way_terrain_shape_contradiction",
        )
        if not isinstance(contradiction, dict):
            return
        expected_surfaces = {
            "wrapper_docstring": ("ii15f", 15),
            "wrapper_udp_pack_and_fill": ("ii20f", 20),
            "wrapper_ctypes_export_declaration": ("double[15]", 15),
        }
        observations = contradiction.get("observations")
        seen = {}
        if not isinstance(observations, list) or len(observations) != 3:
            self.flag("wrong_type", "the terrain contradiction must record exactly three observations")
        else:
            for index, item in enumerate(observations):
                label = f"terrain_contradiction.observations[{index}]"
                if not isinstance(item, dict):
                    self.flag("wrong_type", f"{label}: expected an object")
                    continue
                if item.get("surface") == "wrapper_udp_pack_and_fill":
                    expected_keys = {
                        "surface",
                        "observed_shape",
                        "observed_dimension",
                        "file",
                        "line",
                        "line_secondary",
                    }
                else:
                    expected_keys = {
                        "surface",
                        "observed_shape",
                        "observed_dimension",
                        "file",
                        "line",
                    }
                self.check_keys(item, expected_keys, label)
                seen[item.get("surface")] = (
                    item.get("observed_shape"),
                    item.get("observed_dimension"),
                )
                if not isinstance(item.get("line"), int) or item.get("line") < 1:
                    self.flag("wrong_type", f"{label}.line must be a positive integer")
        for surface, expected in expected_surfaces.items():
            if seen.get(surface) != expected:
                self.flag(
                    "wrong_type",
                    f"terrain contradiction {surface} must be {expected}, observed {seen.get(surface)}",
                )
        self.check_pin_references(
            contradiction.get("evidence_pin_ids"),
            "observed.three_way_terrain_shape_contradiction",
        )
        self.check_pin_references(
            contradiction.get("native_evidence_pin_ids"),
            "observed.three_way_terrain_shape_contradiction.native",
        )
        if sorted(contradiction.get("blocks_issue_ids") or []) != AFFECTED:
            self.flag(
                "affected_or_closure_set_drift",
                "the terrain contradiction must block the vendor-dependent set only",
            )
        if sorted(contradiction.get("does_not_block_issue_ids") or []) != UNAFFECTED:
            self.flag(
                "affected_or_closure_set_drift",
                "the terrain contradiction must not block the native/environment parents",
            )
        if contradiction.get("wksim_native_impact") != "none":
            self.flag("wrong_type", "the terrain contradiction native impact must be none")
        if contradiction.get("role") != "blocker_only":
            self.flag("wrong_type", "the terrain contradiction role must be blocker_only")
        for key in ("contradiction", "resolution_gap"):
            if not isinstance(contradiction.get(key), str) or not contradiction.get(key):
                self.flag("missing_key", f"the terrain contradiction must state {key}")
        blocker_ids = {
            item.get("blocker_id")
            for item in (self._document.get("unresolved_blockers") or [])
            if isinstance(item, dict)
        }
        if TERRAIN_BLOCKER_ID not in blocker_ids:
            self.flag(
                "missing_key",
                "the three-way terrain contradiction must appear as a recorded blocker",
            )

    def check_native_path(self, observed):
        native = observed.get("native_wk_model_abi_path")
        self.check_keys(native, NATIVE_PATH_KEYS, "observed.native_wk_model_abi_path")
        if not isinstance(native, dict):
            return
        if native.get("status") != "available_and_reviewed_in_source":
            self.flag("wrong_type", "the native path status must be available_and_reviewed_in_source")
        if list(native.get("exported_symbols") or []) != NATIVE_EXPORT_SYMBOLS:
            self.flag("wrong_type", "native exported symbols must be the five reviewed wk_model_* entries")
        source = native.get("export_declaration_file")
        if not self.is_repository_relative(source):
            self.flag(
                "native_path_vendor_reference",
                "the native export declaration must be repository-relative",
            )
        elif source not in self.tracked_paths():
            self.flag(
                "native_path_vendor_reference", f"native export declaration {source} is not tracked"
            )
        if native.get("terrain_argument_guard_line") != 91:
            self.flag("wrong_type", "the native terrain argument guard line must be 91")
        if native.get("isolated_from_vendor_abi") is not True:
            self.flag("native_vendor_shared_dependency", "the native path must be recorded as isolated")
        if native.get("legacy_vendor_abi_compatibility_claimed") is not False:
            self.flag(
                "acceptance_claim",
                "the native path must not claim legacy vendor ABI compatibility",
            )
        local_evidence = native.get("evidence_that_observation_is_repository_local")
        if not isinstance(local_evidence, list) or not local_evidence:
            self.flag(
                "native_path_vendor_reference",
                "the native observation must cite repository-local evidence",
            )
        self.check_pin_references(
            native.get("evidence_pin_ids"), "observed.native_wk_model_abi_path"
        )
        reviewed = native.get("reviewed_evidence_pin_id")
        if reviewed not in NATIVE_PIN_IDS:
            self.flag(
                "native_path_vendor_reference",
                f"reviewed native evidence pin {reviewed!r} is not a native pin",
            )

    def check_isolation(self, observed):
        isolation = observed.get("native_vendor_isolation")
        self.check_keys(isolation, ISOLATION_KEYS, "observed.native_vendor_isolation")
        if not isinstance(isolation, dict):
            return None
        if list(isolation.get("shared_media_files") or []):
            self.flag("native_vendor_shared_dependency", "native and vendor tracks must share no media file")
        if isolation.get("native_path_may_be_used_without_vendor_abi") is not True:
            self.flag(
                "native_vendor_shared_dependency",
                "the native path must stay usable without the vendor ABI",
            )
        if isolation.get("vendor_path_may_be_used_from_inferred_shapes") is not False:
            self.flag(
                "acceptance_claim", "the vendor path must not become usable from inferred shapes"
            )
        native_ids = set(isolation.get("native_evidence_pin_ids") or [])
        vendor_ids = set(isolation.get("vendor_evidence_pin_ids") or [])
        if not native_ids or not vendor_ids:
            self.flag("missing_key", "isolation must separate the native and vendor pin sets")
        if native_ids & vendor_ids:
            self.flag(
                "native_vendor_shared_dependency",
                f"native and vendor pin sets overlap: {sorted(native_ids & vendor_ids)}",
            )
        for pin_id in sorted(native_ids | vendor_ids):
            if pin_id not in self._pins:
                self.flag("missing_key", f"isolation references undefined pin {pin_id!r}")
        for pin_id in sorted(native_ids):
            pin = self._pins.get(pin_id) or {}
            if pin.get("evidence_class") != "committed_repository_artifact":
                self.flag(
                    "native_path_vendor_reference",
                    f"native pin {pin_id!r} must be a tracked repository artifact",
                )
        for pin_id in sorted(vendor_ids):
            if pin_id not in VENDOR_PIN_IDS:
                self.flag("affected_or_closure_set_drift", f"unexpected vendor pin {pin_id!r}")
        return native_ids, vendor_ids

    def check_tickets(self, observed):
        tickets = observed.get("observed_tickets")
        expected_numbers = {str(number) for number in MUST_REMAIN_OPEN}
        if not isinstance(tickets, dict) or set(tickets) != expected_numbers:
            self.flag(
                "affected_or_closure_set_drift",
                "observed_tickets must cover exactly the tickets that must remain open",
            )
        else:
            for number in MUST_REMAIN_OPEN:
                ticket = tickets.get(str(number))
                label = f"observed_tickets.{number}"
                if not isinstance(ticket, dict):
                    self.flag("wrong_type", f"{label}: expected an object")
                    continue
                self.check_keys(ticket, OBSERVED_TICKET_KEYS, label)
                if ticket.get("state") != "OPEN":
                    self.flag("affected_or_closure_set_drift", f"{label}: must be recorded open")
                dependencies = ticket.get("parent_dependencies")
                if not isinstance(dependencies, list) or any(
                    not isinstance(item, int) for item in dependencies
                ):
                    self.flag("wrong_type", f"{label}.parent_dependencies must be a list of integers")
                    dependencies = []
                if number == 9:
                    if dependencies:
                        self.flag(
                            "affected_or_closure_set_drift",
                            "#9 must have no parent dependency recorded",
                        )
                elif 9 not in dependencies:
                    self.flag(
                        "affected_or_closure_set_drift",
                        f"{label}: the parent dependency on #9 must stay recorded",
                    )
                if ticket.get("open_dependency_on_9") is not (number != 9):
                    self.flag("affected_or_closure_set_drift", f"{label}: open_dependency_on_9 is wrong")
                if number == 29 and sorted(dependencies) != [9, 17, 23]:
                    self.flag("affected_or_closure_set_drift", "#29 parent dependencies must remain 9, 17, 23")
                if number == 26 and dependencies != [9]:
                    self.flag("affected_or_closure_set_drift", "#26 parent dependency must remain #9")

        snapshot = observed.get("issue_state_snapshot")
        self.check_keys(snapshot, ISSUE_STATE_SNAPSHOT_KEYS, "observed.issue_state_snapshot")
        if isinstance(snapshot, dict):
            if snapshot.get("read_only") is not True:
                self.flag("acceptance_claim", "the issue state snapshot must be recorded read-only")
            issues = snapshot.get("issues")
            if not isinstance(issues, dict) or set(issues) != expected_numbers:
                self.flag(
                    "affected_or_closure_set_drift",
                    "the issue state snapshot must cover exactly the tickets that must remain open",
                )
            else:
                label_map = {}
                for number in MUST_REMAIN_OPEN:
                    record = issues.get(str(number)) or {}
                    self.check_keys(
                        record, {"state", "labels"}, f"issue_state_snapshot.{number}"
                    )
                    if record.get("state") != "OPEN":
                        self.flag(
                            "affected_or_closure_set_drift",
                            f"issue_state_snapshot.{number}: the observed state must be OPEN",
                        )
                    labels = record.get("labels")
                    if not isinstance(labels, list) or not labels:
                        self.flag(
                            "wrong_type", f"issue_state_snapshot.{number}.labels must be a non-empty list"
                        )
                        labels = []
                    label_map[number] = list(labels)
                if "wayfinder:grilling" not in label_map.get(9, []):
                    self.flag(
                        "affected_or_closure_set_drift", "#9 must keep its wayfinder:grilling label"
                    )
                for number in AFFECTED:
                    observed_labels = label_map.get(number, [])
                    if "ready-for-agent" not in observed_labels and "needs-triage" not in observed_labels:
                        self.flag(
                            "affected_or_closure_set_drift",
                            f"#{number} must be recorded with its observed blocking label",
                        )

        edges = observed.get("open_dependency_edges_preserved")
        if not isinstance(edges, list) or not edges:
            self.flag("missing_key", "open dependency edges must be preserved explicitly")
            return
        seen_dependents = set()
        seen_issues = set()
        for index, edge in enumerate(edges):
            label = f"open_dependency_edges_preserved[{index}]"
            self.check_keys(edge, DEPENDENCY_EDGE_KEYS, label)
            if not isinstance(edge, dict):
                continue
            issue = edge.get("issue")
            seen_issues.add(issue)
            if issue != 9 and edge.get("depends_on_issue") == 9:
                seen_dependents.add(issue)
            if edge.get("satisfied_by_this_defer") is not False:
                self.flag("dependency_satisfied_by_defer", f"{label}: the defer satisfies no dependency")
            if edge.get("state") != "OPEN":
                self.flag("affected_or_closure_set_drift", f"{label}: the dependency edge must stay open")
            self.check_pin_references(edge.get("evidence_pin_ids"), label)
        expected_dependents = set(MUST_REMAIN_OPEN) - {9}
        if seen_dependents != expected_dependents:
            self.flag(
                "affected_or_closure_set_drift",
                f"open dependency edges cover {sorted(seen_dependents)} instead of "
                f"{sorted(expected_dependents)}",
            )
        if seen_issues != set(MUST_REMAIN_OPEN):
            self.flag(
                "affected_or_closure_set_drift",
                f"open dependency edges name {sorted(seen_issues)} instead of "
                f"{sorted(MUST_REMAIN_OPEN)}",
            )

    def check_policy(self, document, observed):
        policy = document.get("policy")
        self.check_keys(policy, POLICY_KEYS, "policy")
        if not isinstance(policy, dict):
            return
        if policy.get("defer_class") != "deferred_with_explicit_unlock_preconditions":
            self.flag("wrong_type", "policy.defer_class must record the defer with unlock preconditions")
        if policy.get("rejection_class") != "not_decided":
            self.flag("acceptance_claim", "policy.rejection_class must be not_decided")
        if policy.get("closure_class") != "not_decided":
            self.flag("acceptance_claim", "policy.closure_class must be not_decided")
        if sorted(policy.get("affected") or []) != AFFECTED:
            self.flag("affected_or_closure_set_drift", "policy.affected must be the vendor-dependent set")
        if sorted(policy.get("does_not_affect") or []) != UNAFFECTED:
            self.flag(
                "affected_or_closure_set_drift",
                "policy.does_not_affect must be the native and environment parents",
            )
        if sorted(policy.get("must_remain_open") or []) != MUST_REMAIN_OPEN:
            self.flag("affected_or_closure_set_drift", "policy.must_remain_open is wrong")
        requires = policy.get("closure_requires")
        if not isinstance(requires, list) or not requires:
            self.flag("missing_key", "policy.closure_requires must list the closure conditions")
        elif not any("unlock" in str(item).lower() for item in requires):
            self.flag(
                "wrong_type", "policy.closure_requires must reference the unlock preconditions"
            )
        if policy.get("acceptance_claimed") is not False:
            self.flag("acceptance_claim", "policy.acceptance_claimed must be false")
        if policy.get("implementation_authorized") is not False:
            self.flag("acceptance_claim", "policy.implementation_authorized must be false")
        if policy.get("adr_required_before_any_acceptance") is not True:
            self.flag("acceptance_claim", "an ADR must be required before any acceptance")

    def check_owner_decision(self, document):
        owner = document.get("owner_decision")
        self.check_keys(owner, OWNER_DECISION_KEYS, "owner_decision")
        if not isinstance(owner, dict):
            return
        if owner.get("state") != "not_made":
            self.flag("owner_decision_made", "owner_decision.state must be not_made")
        for key in ("made_by", "recorded_utc", "decision_text"):
            if owner.get(key) is not None:
                self.flag("owner_decision_made", f"owner_decision.{key} must be null")
        if owner.get("rejection_decided") is not False:
            self.flag("acceptance_claim", "owner_decision.rejection_decided must be false")
        if owner.get("closure_decided") is not False:
            self.flag("acceptance_claim", "owner_decision.closure_decided must be false")
        if owner.get("rejection_evidence_found") is not False:
            self.flag(
                "acceptance_claim",
                "no rejection evidence may be recorded as found while the choice is open",
            )
        evidence = owner.get("observed_owner_evidence")
        if not isinstance(evidence, list) or not evidence:
            self.flag("missing_key", "observed owner evidence must be recorded")
        else:
            if owner.get("observed_owner_evidence_count") != len(evidence):
                self.flag("wrong_type", "observed_owner_evidence_count must match the recorded evidence")
            for index, item in enumerate(evidence):
                self.check_keys(
                    item,
                    {"pin_id", "lines", "observed"},
                    f"owner_decision.observed_owner_evidence[{index}]",
                )
        interpretation = str(owner.get("observed_evidence_interpretation") or "")
        if "defer" not in interpretation.lower():
            self.flag("missing_key", "the owner evidence interpretation must state the defer reading")
        forbidden = owner.get("must_not_be_inferred_from_this_record")
        if not isinstance(forbidden, list) or len(forbidden) < 4:
            self.flag("missing_key", "the owner decision must list what may not be inferred")

    def check_recommendation(self, document):
        recommendation = document.get("recommendation")
        self.check_keys(recommendation, RECOMMENDATION_KEYS, "recommendation")
        if not isinstance(recommendation, dict):
            return
        for key in ("defer_vendor_dll_abi", "native_path_remains_usable"):
            if recommendation.get(key) is not True:
                self.flag("wrong_type", f"recommendation.{key} must be true")
        for key in ("reject_vendor_dll_abi", "close_issue_9", "close_issue_26", "close_issue_29"):
            if recommendation.get(key) is not False:
                self.flag("acceptance_claim", f"recommendation.{key} must be false")

        actions = recommendation.get("proposed_actions")
        self.check_keys(actions, PROPOSED_ACTIONS_KEYS, "recommendation.proposed_actions")
        if isinstance(actions, dict):
            for key in sorted(PROPOSED_ACTIONS_KEYS):
                if actions.get(key) is not False:
                    self.flag("issue_action_performed", f"proposed_actions.{key} must be false")

        for key in ("label_recommendations", "comment_recommendations"):
            block = recommendation.get(key)
            if not isinstance(block, dict):
                self.flag("wrong_type", f"recommendation.{key} must be an object")
                continue
            if block.get("performed") is not False:
                self.flag("issue_action_performed", f"recommendation.{key}.performed must be false")

        labels = recommendation.get("label_recommendations") or {}
        add = labels.get("add")
        remove = labels.get("remove")
        keep = labels.get("keep")
        forbidden = labels.get("forbidden")
        if not isinstance(add, list) or not any(
            isinstance(item, dict)
            and item.get("issue") == 9
            and item.get("label") == "ready-for-human"
            for item in add
        ):
            self.flag(
                "missing_key",
                "the label recommendation must encode #9 -> ready-for-human without performing it",
            )
        if not isinstance(forbidden, list) or not any(
            isinstance(item, dict) and item.get("label") == "wontfix" for item in forbidden
        ):
            self.flag(
                "missing_key",
                "the label recommendation must record wontfix as forbidden while rejection is open",
            )
        remove_issues = {item.get("issue") for item in (remove or []) if isinstance(item, dict)}
        expected_blocked = {27, 28, 74, 76, 77, 78}
        if remove_issues != expected_blocked:
            self.flag(
                "affected_or_closure_set_drift",
                f"blocking label recommendations must target {sorted(expected_blocked)}",
            )
        for item in remove or []:
            if isinstance(item, dict) and not item.get("alternative_label"):
                self.flag("missing_key", "a blocking label recommendation needs an alternative label")
        keep_pairs = {
            (item.get("issue"), item.get("label"))
            for item in (keep or [])
            if isinstance(item, dict)
        }
        if (9, "wayfinder:grilling") not in keep_pairs:
            self.flag("affected_or_closure_set_drift", "#9 must keep wayfinder:grilling")
        if (73, "needs-triage") not in keep_pairs:
            self.flag("affected_or_closure_set_drift", "#73 must keep needs-triage")
        if any(isinstance(item, dict) and item.get("issue") == 9 for item in (forbidden or [])):
            self.flag("acceptance_claim", "#9 must not carry a wontfix recommendation")
        if not isinstance(recommendation.get("recommended_actions"), list) or not recommendation.get(
            "recommended_actions"
        ):
            self.flag("missing_key", "recommended_actions must record the advisory actions")

    def check_scope_and_blockers(self, document):
        scope = document.get("scope_limits")
        self.check_keys(scope, SCOPE_LIMITS_KEYS, "scope_limits")
        if isinstance(scope, dict):
            if sorted(scope.get("tracked_artifacts_created") or []) != PERMITTED_ARTIFACTS:
                self.flag(
                    "affected_or_closure_set_drift",
                    "scope_limits must record exactly the three permitted artifacts",
                )
            for key in sorted(SCOPE_LIMITS_KEYS - {"tracked_artifacts_created"}):
                if scope.get(key) is not False:
                    self.flag("wrong_type", f"scope_limits.{key} must be false")

        blockers = document.get("unresolved_blockers")
        if not isinstance(blockers, list) or not blockers:
            self.flag("missing_key", "unresolved_blockers must be recorded")
        else:
            identifiers = []
            for index, blocker in enumerate(blockers):
                label = f"unresolved_blockers[{index}]"
                self.check_keys(blocker, BLOCKER_KEYS, label)
                if not isinstance(blocker, dict):
                    continue
                identifiers.append(blocker.get("blocker_id"))
                if blocker.get("severity") not in ("blocking", "blocking_for_closure_only"):
                    self.flag("wrong_type", f"{label}.severity is not a blocking severity")
                self.check_pin_references(blocker.get("evidence_pin_ids"), label)
                if sorted(blocker.get("blocks") or []) not in (AFFECTED, [9]):
                    self.flag("affected_or_closure_set_drift", f"{label}.blocks is not a permitted set")
            if TERRAIN_BLOCKER_ID not in identifiers:
                self.flag("missing_key", "the terrain three-way shape blocker must be recorded")

        gaps = document.get("host_bounded_gaps")
        self.check_keys(gaps, HOST_GAP_KEYS, "host_bounded_gaps")
        if isinstance(gaps, dict):
            for key in sorted(HOST_GAP_KEYS - {"vendor_header_absence"}):
                entry = gaps.get(key)
                if not isinstance(entry, dict):
                    self.flag("wrong_type", f"host_bounded_gaps.{key} must be an object")
                    continue
                self.check_keys(entry, UNTRACKED_GAP_KEYS, f"host_bounded_gaps.{key}")
                if entry.get("tracked") is not False:
                    self.flag(
                        "host_external_pin_promoted_to_decision",
                        f"host_bounded_gaps.{key} must stay recorded as untracked",
                    )
                self.digest_is_canonical(entry.get("sha256"), f"host_bounded_gaps.{key}")

    def check_claim_scan(self, document):
        """Reject a rejection/closure/acceptance claim in the record's own words.

        Only the declared claim text is scanned as prose.  Identifiers, paths
        and enum values are deliberately excluded: a cited artifact whose file
        name contains a word such as ``accepted`` is not a claim by this record.
        """

        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{path}.{key}" if path else key)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")
            elif isinstance(node, bool):
                if path.rsplit(".", 1)[-1] in CLAIM_UNIT_KEYS and node:
                    self.flag("acceptance_claim", f"{path}: claim flag must be false")
            elif isinstance(node, str) and path in CLAIM_PROSE_FIELDS:
                lowered = node.lower()
                for phrase in FORBIDDEN_CLAIM_PHRASES:
                    if phrase not in lowered:
                        continue
                    if any(marker in lowered for marker in NEGATION_MARKERS):
                        continue
                    self.flag("acceptance_claim", f"{path}: forbidden claim phrase {phrase!r}")

        walk(document, "")

    # -- entry point -------------------------------------------------------

    def validate(self, document):
        if not isinstance(document, dict):
            self.flag("wrong_type", "document must be a JSON object")
            return self.violations
        self._document = document
        self._pins = document.get("evidence_pins") or {}
        self.check_keys(document, TOP_KEYS, "document")
        self.check_identity(document)
        self.check_observed_at(document)
        self.check_evidence_policy(document)

        if not isinstance(self._pins, dict) or not self._pins:
            self.flag("missing_key", "evidence_pins must not be empty")
            self._pins = {}
        else:
            decision_affecting = [
                pin_id
                for pin_id, pin in self._pins.items()
                if isinstance(pin, dict)
                and pin.get("evidence_class") == "committed_repository_artifact"
            ]
            if not decision_affecting:
                self.flag("missing_key", "at least one decision-affecting tracked pin is required")
            for pin_id in sorted(self._pins):
                self.check_pin(pin_id, self._pins[pin_id])

        observed = document.get("observed")
        self.check_keys(observed, OBSERVED_KEYS, "observed")
        if not isinstance(observed, dict):
            self.flag("wrong_type", "observed must be an object")
            return self.violations

        self.check_vendor_availability(observed)
        self.check_terrain_contradiction(observed)
        self.check_native_path(observed)
        isolation = self.check_isolation(observed)
        self.check_tickets(observed)
        self.check_policy(document, observed)
        self.check_owner_decision(document)
        self.check_recommendation(document)
        self.check_scope_and_blockers(document)
        self.check_claim_scan(document)

        if isolation:
            native_ids, vendor_ids = isolation
            native_paths = {
                (self._pins.get(pin_id) or {}).get("path") for pin_id in native_ids
            }
            vendor_paths = {
                (self._pins.get(pin_id) or {}).get("path") for pin_id in vendor_ids
            }
            shared = {path for path in native_paths & vendor_paths if path}
            if shared:
                self.flag(
                    "native_vendor_shared_dependency",
                    f"native and vendor pins share media: {sorted(shared)}",
                )
            if any(
                isinstance(path, str) and "rflysimtools" in path.lower() for path in native_paths
            ):
                self.flag(
                    "native_path_vendor_reference",
                    "a native evidence pin points at a vendor host path",
                )
        return self.violations


def verify_document(document, root=ROOT):
    return Verifier(root=root).validate(document)


def verify_contract(path=CONTRACT, root=ROOT):
    return verify_document(load_document(path), root=root)


class DeferBoundaryContractTests(unittest.TestCase):
    """Verify the tracked PROPOSED defer boundary against real repository bytes."""

    @classmethod
    def setUpClass(cls):
        if not CONTRACT.is_file():
            raise MissingDecision(f"missing contract {CONTRACT}")
        cls.document = load_document(CONTRACT)
        cls.verifier = Verifier(root=ROOT)
        cls.violations = cls.verifier.validate(copy.deepcopy(cls.document))
        cls.tracked = cls.verifier.tracked_paths()
        cls.head_paths = cls.verifier.head_paths()

    def codes(self):
        return {item.split(":", 1)[0] for item in self.violations}

    def test_contract_is_committed_at_head(self):
        """A PROPOSED tracked record only counts once it is committed.

        This assertion stays fail-closed: creating the artifact is not enough,
        an authorized commit must land it in the HEAD tree.
        """

        self.assertTrue(
            CONTRACT_RELATIVE in self.tracked,
            f"{CONTRACT_RELATIVE} must be tracked by git (stage it under an authorized commit)",
        )
        self.assertIn(
            CONTRACT_RELATIVE,
            self.head_paths,
            "the contract must exist in the HEAD tree; commit it before relying on it",
        )
        blob = self.verifier.head_bytes(CONTRACT_RELATIVE)
        self.assertIsNotNone(blob, "the HEAD blob must be readable")
        self.assertEqual(
            hashlib.sha256(blob).hexdigest(),
            hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
            "worktree contract bytes must equal the committed HEAD blob",
        )

    def test_no_uppercase_or_malformed_digests(self):
        for pin_id, pin in self.document["evidence_pins"].items():
            digest = pin["sha256"]
            with self.subTest(pin=pin_id):
                self.assertEqual(digest, digest.lower(), f"{pin_id} digest must be lower-case")
                self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_verifier_reports_no_violations(self):
        self.assertEqual(self.violations, [], "\n".join(self.violations))

    def test_decision_affecting_pins_match_worktree_and_head(self):
        checked = 0
        for pin_id, pin in self.document["evidence_pins"].items():
            if pin.get("evidence_class") != "committed_repository_artifact":
                continue
            checked += 1
            path = pin["path"]
            with self.subTest(pin=pin_id):
                self.assertTrue(self.verifier.is_repository_relative(path))
                self.assertIn(path, self.tracked, f"{path} must be tracked")
                self.assertIn(path, self.head_paths, f"{path} must exist at HEAD")
                worktree = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                blob = self.verifier.head_bytes(path)
                self.assertEqual(worktree, pin["sha256"], f"{path} worktree digest drifted")
                self.assertIsNotNone(blob, f"{path} HEAD blob unreadable")
                self.assertEqual(
                    hashlib.sha256(blob).hexdigest(),
                    pin["sha256"],
                    f"{path} HEAD blob digest drifted",
                )
        self.assertGreaterEqual(checked, 8, "the contract must cite committed artifacts")

    def test_untracked_context_is_never_authority(self):
        for key in (
            "environment_acceptance_json",
            "audit_report",
            "audit_evidence_json",
            "interface_decision_packet",
            "acceptance_frontier",
        ):
            entry = self.document["host_bounded_gaps"][key]
            with self.subTest(gap=key):
                self.assertIs(entry["tracked"], False)
                self.assertNotIn(entry["path"], self.tracked, f"{key} must stay untracked")
        for pin_id in HOST_EXTERNAL_PIN_IDS:
            pin = self.document["evidence_pins"][pin_id]
            with self.subTest(pin=pin_id):
                self.assertEqual(pin["evidence_class"], "host_external_read_only")
                self.assertEqual(pin["authority"], "context_only")
                self.assertFalse(self.verifier.is_repository_relative(pin["path"]))

    def test_vendor_abi_is_deferred_and_not_rejected(self):
        availability = self.document["observed"]["vendor_dll_abi_availability"]
        self.assertEqual(availability["status"], "official_source_unavailable")
        self.assertEqual(
            availability["conclusion"], "deferred_pending_official_header_and_authorized_sample"
        )
        self.assertEqual(availability["unlock_preconditions_count"], 5)
        self.assertEqual(availability["unavailable_count"], 8)
        owner = self.document["owner_decision"]
        self.assertEqual(owner["state"], "not_made")
        self.assertIsNone(owner["decision_text"])
        self.assertFalse(owner["rejection_decided"])
        self.assertFalse(owner["closure_decided"])
        self.assertFalse(owner["rejection_evidence_found"])
        self.assertFalse(self.document["policy"]["acceptance_claimed"])
        self.assertFalse(self.document["recommendation"]["reject_vendor_dll_abi"])
        self.assertTrue(self.document["recommendation"]["defer_vendor_dll_abi"])

    def test_affected_tickets_stay_open(self):
        policy = self.document["policy"]
        self.assertEqual(sorted(policy["affected"]), AFFECTED)
        self.assertEqual(sorted(policy["does_not_affect"]), UNAFFECTED)
        self.assertEqual(sorted(policy["must_remain_open"]), MUST_REMAIN_OPEN)
        observed = self.document["observed"]
        for number in MUST_REMAIN_OPEN:
            with self.subTest(issue=number):
                self.assertEqual(observed["observed_tickets"][str(number)]["state"], "OPEN")
                self.assertEqual(
                    observed["issue_state_snapshot"]["issues"][str(number)]["state"], "OPEN"
                )

    def test_parent_dependencies_are_preserved(self):
        edges = self.document["observed"]["open_dependency_edges_preserved"]
        self.assertEqual(len(edges), len(MUST_REMAIN_OPEN))
        for edge in edges:
            with self.subTest(issue=edge["issue"]):
                self.assertFalse(edge["satisfied_by_this_defer"])
                self.assertEqual(edge["state"], "OPEN")
        dependents = {edge["issue"] for edge in edges if edge["depends_on_issue"] == 9}
        self.assertEqual(dependents, set(MUST_REMAIN_OPEN) - {9})
        self.assertEqual(self.document["observed"]["observed_tickets"]["29"]["parent_dependencies"], [9, 17, 23])
        self.assertEqual(self.document["observed"]["observed_tickets"]["26"]["parent_dependencies"], [9])

    def test_no_rejection_closure_or_acceptance_claim(self):
        recommendation = self.document["recommendation"]
        for key, value in recommendation["proposed_actions"].items():
            with self.subTest(action=key):
                self.assertIs(value, False)
        self.assertFalse(recommendation["label_recommendations"]["performed"])
        self.assertFalse(recommendation["comment_recommendations"]["performed"])
        self.assertFalse(recommendation["close_issue_9"])
        self.assertFalse(recommendation["close_issue_26"])
        self.assertFalse(recommendation["close_issue_29"])
        self.assertNotIn("acceptance_claim", self.codes())
        self.assertNotIn("issue_action_performed", self.codes())
        self.assertNotIn("owner_decision_made", self.codes())

    def test_label_recommendations_are_encoded_but_not_performed(self):
        labels = self.document["recommendation"]["label_recommendations"]
        self.assertIs(labels["performed"], False)
        add_pairs = {(item["issue"], item["label"]) for item in labels["add"]}
        self.assertIn((9, "ready-for-human"), add_pairs)
        self.assertEqual({item["issue"] for item in labels["remove"]}, {27, 28, 74, 76, 77, 78})
        self.assertEqual({item["label"] for item in labels["forbidden"]}, {"wontfix"})
        self.assertNotIn(9, {item["issue"] for item in labels["forbidden"]})
        self.assertEqual(
            {(item["issue"], item["label"]) for item in labels["keep"]},
            {(9, "wayfinder:grilling"), (73, "needs-triage")},
        )

    def test_three_way_terrain_shape_contradiction_is_a_blocker_only(self):
        contradiction = self.document["observed"]["three_way_terrain_shape_contradiction"]
        shapes = {item["surface"]: item["observed_shape"] for item in contradiction["observations"]}
        self.assertEqual(
            shapes,
            {
                "wrapper_docstring": "ii15f",
                "wrapper_udp_pack_and_fill": "ii20f",
                "wrapper_ctypes_export_declaration": "double[15]",
            },
        )
        self.assertEqual(contradiction["wksim_native_impact"], "none")
        self.assertEqual(contradiction["role"], "blocker_only")
        self.assertEqual(contradiction["blocks_issue_ids"], AFFECTED)
        self.assertEqual(contradiction["does_not_block_issue_ids"], UNAFFECTED)
        blocker_ids = {item["blocker_id"] for item in self.document["unresolved_blockers"]}
        self.assertIn(TERRAIN_BLOCKER_ID, blocker_ids)
        vendor_pin = self.document["evidence_pins"]["vendor_control_wrapper"]
        self.assertEqual(vendor_pin["evidence_class"], "host_external_read_only")
        self.assertEqual(vendor_pin["authority"], "context_only")
        self.assertNotIn(vendor_pin["path"], self.tracked)
        for pin_id in contradiction["evidence_pin_ids"]:
            self.assertIn(pin_id, self.document["evidence_pins"])
        for pin_id in contradiction["native_evidence_pin_ids"]:
            self.assertEqual(
                self.document["evidence_pins"][pin_id]["evidence_class"],
                "committed_repository_artifact",
            )

    def test_native_and_vendor_paths_are_isolated(self):
        observed = self.document["observed"]
        isolation = observed["native_vendor_isolation"]
        native_ids = set(isolation["native_evidence_pin_ids"])
        vendor_ids = set(isolation["vendor_evidence_pin_ids"])
        self.assertFalse(native_ids & vendor_ids)
        self.assertEqual(isolation["shared_media_files"], [])
        self.assertTrue(isolation["native_path_may_be_used_without_vendor_abi"])
        self.assertFalse(isolation["vendor_path_may_be_used_from_inferred_shapes"])
        native = observed["native_wk_model_abi_path"]
        self.assertTrue(native["isolated_from_vendor_abi"])
        self.assertFalse(native["legacy_vendor_abi_compatibility_claimed"])
        self.assertEqual(native["exported_symbols"], NATIVE_EXPORT_SYMBOLS)
        for pin_id in native_ids:
            pin = self.document["evidence_pins"][pin_id]
            self.assertEqual(pin["evidence_class"], "committed_repository_artifact")
            self.assertNotIn("rflysimtools", pin["path"].lower())
        source = ROOT / native["export_declaration_file"]
        self.assertIn(native["export_declaration_file"], self.tracked)
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(),
            self.document["evidence_pins"]["native_model_cpp"]["sha256"],
        )
        text = source.read_text(encoding="utf-8")
        self.assertIn(
            f"terrain_count != {NATIVE_TERRAIN_DIMENSION}",
            text,
            "the native export must keep its own terrain dimension guard",
        )

    def test_permitted_files_only(self):
        scope = self.document["scope_limits"]
        self.assertEqual(sorted(scope["tracked_artifacts_created"]), PERMITTED_ARTIFACTS)
        for key, value in scope.items():
            if key == "tracked_artifacts_created":
                continue
            with self.subTest(limit=key):
                self.assertIs(value, False)


class FailClosedVerifierTests(unittest.TestCase):
    """Prove the verifier rejects drifted, uncommitted and over-claiming variants."""

    @classmethod
    def setUpClass(cls):
        cls.document = load_document(CONTRACT)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.scratch = Path(self.dir.name) / "contract.json"

    def verify(self, document):
        self.scratch.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return Verifier(root=ROOT).validate(load_document(self.scratch))

    def codes(self, violations):
        return {item.split(":", 1)[0] for item in violations}

    def mutate(self, change):
        document = copy.deepcopy(self.document)
        change(document)
        return document

    def test_unmodified_scratch_copy_still_passes(self):
        self.assertEqual(self.verify(copy.deepcopy(self.document)), [])

    def test_unknown_and_missing_keys_fail_closed(self):
        self.assertIn(
            "unknown_key", self.codes(self.verify(self.mutate(lambda doc: doc.update({"extra": 1}))))
        )
        self.assertIn(
            "missing_key",
            self.codes(self.verify(self.mutate(lambda doc: doc.pop("non_claims")))),
        )
        self.assertIn(
            "missing_key",
            self.codes(
                self.verify(
                    self.mutate(
                        lambda doc: doc["observed"]["native_vendor_isolation"].pop("rule")
                    )
                )
            ),
        )

    def test_uppercase_digest_fails_closed(self):
        def change(doc):
            pin = doc["evidence_pins"]["native_model_cpp"]
            pin["sha256"] = pin["sha256"].upper()

        codes = self.codes(self.verify(self.mutate(change)))
        self.assertIn("uppercase_digest", codes)

    def test_worktree_digest_drift_fails_closed(self):
        def change(doc):
            doc["evidence_pins"]["native_model_py"]["sha256"] = "0" * 64

        self.assertIn("digest_mismatch_worktree", self.codes(self.verify(self.mutate(change))))

    def test_digest_without_worktree_match_fails_closed(self):
        def change(doc):
            doc["evidence_pins"]["abi_evidence"]["sha256"] = "a" * 64

        codes = self.codes(self.verify(self.mutate(change)))
        self.assertIn("digest_mismatch_worktree", codes)
        self.assertIn("digest_mismatch_head_blob", codes)

    def test_pin_moved_to_untracked_path_fails_closed(self):
        untracked = ROOT / "docs/coordination/ds-interface-decision-packet-20260912.md"
        self.assertTrue(untracked.is_file(), "precondition: the packet exists locally")

        def change(doc):
            pin = doc["evidence_pins"]["native_ac_evidence"]
            pin["path"] = "docs/coordination/ds-interface-decision-packet-20260912.md"
            pin["sha256"] = hashlib.sha256(untracked.read_bytes()).hexdigest()

        self.assertIn("path_not_tracked_at_head", self.codes(self.verify(self.mutate(change))))

    def test_absolute_vendor_path_as_decision_pin_fails_closed(self):
        def change(doc):
            pin = doc["evidence_pins"]["native_ac_evidence"]
            pin["evidence_class"] = "committed_repository_artifact"
            pin["path"] = "E:/rflysimtools/RflySimAPIs/RflySimSDK/ctrl/DllSimCtrlAPI.py"
            pin["sha256"] = "0" * 64

        self.assertIn("path_not_tracked_at_head", self.codes(self.verify(self.mutate(change))))

    def test_host_external_pin_promoted_to_decision_fails_closed(self):
        def change(doc):
            doc["evidence_pins"]["vendor_control_wrapper"]["authority"] = "decision_affecting"

        self.assertIn(
            "host_external_pin_promoted_to_decision", self.codes(self.verify(self.mutate(change)))
        )

    def test_untracked_gap_promoted_to_tracked_fails_closed(self):
        def change(doc):
            doc["host_bounded_gaps"]["audit_report"]["tracked"] = True

        self.assertIn(
            "host_external_pin_promoted_to_decision", self.codes(self.verify(self.mutate(change)))
        )

    def test_owner_decision_made_fails_closed(self):
        def change(doc):
            doc["owner_decision"]["state"] = "decided_to_reject"

        codes = self.codes(self.verify(self.mutate(change)))
        self.assertIn("owner_decision_made", codes)

    def test_recorded_owner_decision_text_fails_closed(self):
        def change(doc):
            doc["owner_decision"]["decision_text"] = "the vendor DLL path is rejected"

        codes = self.codes(self.verify(self.mutate(change)))
        self.assertIn("owner_decision_made", codes)

    def test_rejection_claim_fails_closed(self):
        def change(doc):
            doc["recommendation"]["reject_vendor_dll_abi"] = True

        self.assertIn("acceptance_claim", self.codes(self.verify(self.mutate(change))))

    def test_closure_claim_fails_closed(self):
        def change(doc):
            doc["policy"]["closure_class"] = "closed"
            doc["recommendation"]["close_issue_9"] = True

        self.assertIn("acceptance_claim", self.codes(self.verify(self.mutate(change))))

    def test_acceptance_claim_fails_closed(self):
        def change(doc):
            doc["policy"]["acceptance_claimed"] = True

        self.assertIn("acceptance_claim", self.codes(self.verify(self.mutate(change))))

    def test_free_text_closure_claim_fails_closed(self):
        def change(doc):
            doc["observed"]["vendor_dll_abi_availability"]["note"] = (
                "The vendor DLL ABI is rejected and #9 is closed."
            )

        self.assertIn("acceptance_claim", self.codes(self.verify(self.mutate(change))))

    def test_dependency_satisfied_by_defer_fails_closed(self):
        def change(doc):
            for edge in doc["observed"]["open_dependency_edges_preserved"]:
                if edge["issue"] == 27:
                    edge["satisfied_by_this_defer"] = True

        self.assertIn("dependency_satisfied_by_defer", self.codes(self.verify(self.mutate(change))))

    def test_dropped_parent_dependency_fails_closed(self):
        def change(doc):
            doc["observed"]["observed_tickets"]["29"]["parent_dependencies"] = [17, 23]

        self.assertIn(
            "affected_or_closure_set_drift", self.codes(self.verify(self.mutate(change)))
        )

    def test_unaffected_ticket_added_to_blocked_set_fails_closed(self):
        def change(doc):
            doc["policy"]["affected"] = sorted(AFFECTED + [26])

        self.assertIn(
            "affected_or_closure_set_drift", self.codes(self.verify(self.mutate(change)))
        )

    def test_ticket_recorded_closed_fails_closed(self):
        def change(doc):
            doc["observed"]["observed_tickets"]["74"]["state"] = "CLOSED"

        self.assertIn(
            "affected_or_closure_set_drift", self.codes(self.verify(self.mutate(change)))
        )

    def test_vendor_pin_inside_native_set_fails_closed(self):
        def change(doc):
            doc["observed"]["native_vendor_isolation"]["native_evidence_pin_ids"].append(
                "vendor_control_wrapper"
            )

        codes = self.codes(self.verify(self.mutate(change)))
        self.assertTrue(
            {"native_vendor_shared_dependency", "native_path_vendor_reference"} & codes,
            codes,
        )

    def test_vendor_host_path_in_native_pin_fails_closed(self):
        def change(doc):
            doc["observed"]["native_wk_model_abi_path"]["export_declaration_file"] = (
                "E:/rflysimtools/CopterSim/external/model/Multicore.cpp"
            )

        self.assertIn("native_path_vendor_reference", self.codes(self.verify(self.mutate(change))))

    def test_native_compatibility_claim_fails_closed(self):
        def change(doc):
            doc["observed"]["native_wk_model_abi_path"][
                "legacy_vendor_abi_compatibility_claimed"
            ] = True

        self.assertIn("acceptance_claim", self.codes(self.verify(self.mutate(change))))

    def test_performed_label_action_fails_closed(self):
        def change(doc):
            doc["recommendation"]["label_recommendations"]["performed"] = True

        self.assertIn("issue_action_performed", self.codes(self.verify(self.mutate(change))))

    def test_performed_github_action_fails_closed(self):
        def change(doc):
            doc["recommendation"]["proposed_actions"]["github_mutated"] = True

        self.assertIn("issue_action_performed", self.codes(self.verify(self.mutate(change))))

    def test_terrain_contradiction_collapsed_fails_closed(self):
        def change(doc):
            doc["observed"]["three_way_terrain_shape_contradiction"]["observations"] = [
                item
                for item in doc["observed"]["three_way_terrain_shape_contradiction"]["observations"]
                if item["surface"] != "wrapper_ctypes_export_declaration"
            ]

        self.assertIn("wrong_type", self.codes(self.verify(self.mutate(change))))

    def test_terrain_shape_relabelled_fails_closed(self):
        def change(doc):
            for item in doc["observed"]["three_way_terrain_shape_contradiction"]["observations"]:
                if item["surface"] == "wrapper_udp_pack_and_fill":
                    item["observed_shape"] = "ii15f"
                    item["observed_dimension"] = 15

        self.assertIn("wrong_type", self.codes(self.verify(self.mutate(change))))

    def test_terrain_contradiction_claimed_to_block_native_fails_closed(self):
        def change(doc):
            doc["observed"]["three_way_terrain_shape_contradiction"]["blocks_issue_ids"] = sorted(
                AFFECTED + [26, 29]
            )

        self.assertIn(
            "affected_or_closure_set_drift", self.codes(self.verify(self.mutate(change)))
        )

    def test_terrain_contradiction_without_blocker_record_fails_closed(self):
        def change(doc):
            doc["unresolved_blockers"] = [
                item
                for item in doc["unresolved_blockers"]
                if item["blocker_id"] != TERRAIN_BLOCKER_ID
            ]

        self.assertIn("missing_key", self.codes(self.verify(self.mutate(change))))

    def test_recorded_run_limit_violation_fails_closed(self):
        def change(doc):
            doc["scope_limits"]["vendor_dll_loaded"] = True

        self.assertIn("wrong_type", self.codes(self.verify(self.mutate(change))))

    def test_extra_created_artifact_fails_closed(self):
        def change(doc):
            doc["scope_limits"]["tracked_artifacts_created"].append("docs/plan/other.md")

        self.assertIn(
            "affected_or_closure_set_drift", self.codes(self.verify(self.mutate(change)))
        )

    def test_duplicate_key_document_is_not_parseable(self):
        text = CONTRACT.read_text(encoding="utf-8")
        mutated = text.replace(
            '"layer": "proposed",', '"layer": "proposed", "layer": "proposed",', 1
        )
        self.scratch.write_text(mutated, encoding="utf-8")
        with self.assertRaises(ValueError):
            load_document(self.scratch)

    def test_non_finite_document_is_not_parseable(self):
        self.scratch.write_text('{"schema": NaN}\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_document(self.scratch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
