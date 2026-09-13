"""Pure offline tests for the #59 G6/B5 solve-form decision packet.

Run from the repository root::

    python -B -m unittest validation.test_e0_g6_solve_form_decision

The suite never launches MATLAB/native/ROS/FC/UE/build/#83, never mutates git
or GitHub, and never claims G6 or Full acceptance.  It re-hashes the pinned
run-05 / mrdivide / diagonal traces, recomputes the first-step and stage-2
compares, and then proves the verifier fails closed on malformed hex, wrong
case/stage, a non-diagonal Selector2, solve-form mismatch, missing or extra
pins, unknown option keys, a fourth option, an unknown top-level key, B1
approval, a B4 freeze, acceptance flips and tampering.
"""

from __future__ import annotations

import copy
import hashlib
import json
import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.compare_first_step_trace import (  # noqa: E402
    compare as compare_first,
    decode_f64_hex,
    norm_hex,
    ulp_distance,
)
from tools.compare_g6_c3g_stage2 import (  # noqa: E402
    FROZEN_SELECTOR2,
    compare as compare_stage2,
)

PACKET_RELATIVE = "validation/e0-g6-solve-form-decision-20260914.json"
PACKET = ROOT / PACKET_RELATIVE
MARKDOWN = ROOT / "docs/plan/59-g6-solve-form-decision-20260914.md"
COORD = ROOT / "validation/coordination/cursor-g6-solve-form-20260914-01"

SCHEMA = "wksim.59-g6-solve-form-decision.v1"
KIND = "g6_b5_solve_form_decision_packet"
HEAD = "768526aafa1e48c342c5c8840a9154e8ed90f68d"
ANCESTOR = "f333316e6efa6b299b4288a9d91fb2bccedfb9d6"
REF_HEX = "bc56d4db33a987b8"
DIV_HEX = "bc56d4db33a987b9"
NUM_Q = "bc000013449033b2"
DEN_JYY = "3f966cf41f212d77"
OWNER_IDS = (
    "adopt_diagonal_branch",
    "retain_division_absorb_ulp",
    "defer",
)
REQUIRED_PINS = (
    "reference_run05",
    "target_mrdivide",
    "diagonal_candidate",
)
TRACKED_PINS = REQUIRED_PINS + ("comparison_v2",)
DERIVED_PINS = (
    "division_vs_reference",
    "diagonal_vs_reference",
    "stage2_operand_boundary",
)
CLOSED_PINS = TRACKED_PINS + DERIVED_PINS
OPTION_KEYS = (
    "id",
    "label",
    "chosen",
    "summary",
)
FAIL_CLOSED_ON = (
    "unknown_key",
    "missing_key",
    "wrong_type",
    "malformed_hex",
    "wrong_case_or_stage",
    "non_diagonal_selector2",
    "solve_form_mismatch",
    "missing_pins",
    "tampering",
    "g6_or_physical_acceptance_claim",
    "owner_decision_made",
    "budget_or_contract_freeze",
)
TOP_KEYS = {
    "schema",
    "kind",
    "issue",
    "layer",
    "authority",
    "effective",
    "date",
    "title",
    "work_class",
    "g6_acceptance",
    "physical_accuracy",
    "r1_status",
    "issues_closed",
    "claim_text",
    "observed_at",
    "evidence_policy",
    "pins",
    "identity",
    "selector2",
    "residual_pair2",
    "discriminating_point",
    "solve_forms",
    "recheck",
    "unobserved_domain",
    "owner_options",
    "owner_decision",
    "b1_b4_effects",
    "non_claims",
    "scope_limits",
}
CANONICAL_HEX_DIGITS = frozenset("0123456789abcdef")


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path):
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def _load_jsonl(path):
    raw = Path(path).read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return rows, hashlib.sha256(raw).hexdigest()


def _canonical_hex(value):
    if not isinstance(value, str):
        return False
    text = value[2:] if value.startswith("0x") else value
    return len(text) == 16 and all(char in CANONICAL_HEX_DIGITS for char in text.lower()) and text == text.lower()


def _as_hex(value):
    if not isinstance(value, str):
        raise ValueError(f"non-canonical binary64 hex: {value!r}")
    text = value[2:] if value.startswith("0x") else value
    if not _canonical_hex(text):
        # allow the source traces' 0x-prefixed lowercase form via decode
        decode_f64_hex(value)
        return norm_hex(value)
    return text


def _head_blob_sha256(relative):
    raw = subprocess.check_output(
        ["git", "show", f"HEAD:{relative.replace(chr(92), '/')}"],
        cwd=ROOT,
    )
    return hashlib.sha256(raw).hexdigest()


def _ieee_pair(num_hex, den_hex):
    u0 = decode_f64_hex(num_hex)
    u1 = decode_f64_hex(den_hex)
    division = struct.pack(">d", u0 / u1).hex()
    reciprocal = struct.pack(">d", u0 * (1.0 / u1)).hex()
    return division, reciprocal


def _selector_is_diagonal(hexes):
    values = [_as_hex(item) for item in hexes]
    if len(values) != 9:
        return False
    off = all(values[index] == "0000000000000000" for index in (1, 2, 3, 5, 6, 7))
    diag = all(values[index] != "0000000000000000" for index in (0, 4, 8))
    return off and diag


class Verifier:
    def __init__(self):
        self.violations = []

    def flag(self, code, message):
        self.violations.append({"code": code, "message": message})

    def codes(self):
        return [item["code"] for item in self.violations]

    def check_keys(self, value, expected, label):
        if not isinstance(value, dict):
            self.flag("wrong_type", f"{label} must be an object")
            return
        extra = set(value) - set(expected)
        missing = set(expected) - set(value)
        if extra:
            self.flag("unknown_key", f"{label} has unknown keys {sorted(extra)}")
        if missing:
            self.flag("missing_key", f"{label} missing {sorted(missing)}")

    def digest_is_canonical(self, value, label):
        if not isinstance(value, str) or len(value) != 64 or value != value.lower():
            self.flag("malformed_hex", f"{label} is not a lowercase sha256")
            return False
        try:
            int(value, 16)
        except (TypeError, ValueError):
            self.flag("malformed_hex", f"{label} is not a lowercase sha256")
            return False
        return True

    def require_hex(self, value, label):
        try:
            return _as_hex(value)
        except (TypeError, ValueError) as error:
            self.flag("malformed_hex", f"{label}: {error}")
            return None

    def verify(self, document, *, traces=None):
        if not isinstance(document, dict):
            self.flag("wrong_type", "document must be a JSON object")
            return self._result()
        self.check_keys(document, TOP_KEYS, "document")
        if document.get("schema") != SCHEMA:
            self.flag("wrong_type", "schema mismatch")
        if document.get("kind") != KIND:
            self.flag("wrong_type", "kind mismatch")
        if document.get("issue") != 59:
            self.flag("wrong_type", "issue must be 59")
        if document.get("g6_acceptance") is not False:
            self.flag("g6_or_physical_acceptance_claim", "g6_acceptance must be false")
        if document.get("physical_accuracy") is not False:
            self.flag("g6_or_physical_acceptance_claim", "physical_accuracy must be false")
        if document.get("issues_closed") is not False:
            self.flag("g6_or_physical_acceptance_claim", "issues_closed must be false")
        if document.get("effective") is not False:
            self.flag("g6_or_physical_acceptance_claim", "effective must be false")
        if document.get("r1_status") != "numerical_failed":
            self.flag("wrong_type", "r1_status must remain numerical_failed")

        policy = document.get("evidence_policy")
        if isinstance(policy, dict):
            codes = policy.get("fail_closed_on")
            if not isinstance(codes, list):
                self.flag("wrong_type", "evidence_policy.fail_closed_on must be a list")
            else:
                extra_codes = set(codes) - set(FAIL_CLOSED_ON)
                missing_codes = set(FAIL_CLOSED_ON) - set(codes)
                if extra_codes:
                    self.flag("unknown_key", f"fail_closed_on has unknown codes {sorted(extra_codes)}")
                if missing_codes:
                    self.flag("missing_key", f"fail_closed_on missing {sorted(missing_codes)}")

        identity = document.get("identity")
        if not isinstance(identity, dict):
            self.flag("wrong_type", "identity must be an object")
        elif identity.get("case") != "C3G" or identity.get("stage") != 2:
            self.flag("wrong_case_or_stage", "identity.case must be C3G and identity.stage must be 2")

        observed = document.get("observed_at")
        if isinstance(observed, dict):
            if observed.get("head") != HEAD:
                self.flag("tampering", "observed_at.head does not match the required checkout")
            if observed.get("baseline_ancestor") != ANCESTOR:
                self.flag("tampering", "baseline ancestor pin differs")
            if observed.get("ancestor_check_exit") != 0:
                self.flag("tampering", "ancestor check must be exit 0")

        pins = document.get("pins")
        if not isinstance(pins, dict):
            self.flag("missing_pins", "pins must be an object")
            return self._result()
        extra_pins = set(pins) - set(CLOSED_PINS)
        missing_pins = set(CLOSED_PINS) - set(pins)
        if extra_pins:
            self.flag("unknown_key", f"pins has unknown keys {sorted(extra_pins)}")
        if missing_pins:
            self.flag("missing_pins", f"required pin {sorted(missing_pins)} is absent")
        loaded = {}
        for pin_id, pin in pins.items():
            if not isinstance(pin, dict):
                self.flag("wrong_type", f"pin {pin_id} must be an object")
                continue
            path = pin.get("path")
            digest = pin.get("sha256")
            if not self.digest_is_canonical(digest, f"pins.{pin_id}.sha256"):
                continue
            if not isinstance(path, str):
                self.flag("wrong_type", f"pins.{pin_id}.path must be a string")
                continue
            full = ROOT / path
            if not full.is_file():
                self.flag("missing_pins", f"pin {pin_id} path is unreadable")
                continue
            actual = _sha256(full)
            if actual != digest:
                self.flag("tampering", f"pin {pin_id} worktree digest differs")
            if pin.get("tracked_at_head") is True:
                try:
                    head_digest = _head_blob_sha256(path)
                except subprocess.CalledProcessError:
                    self.flag("missing_pins", f"pin {pin_id} is not in HEAD")
                    continue
                if head_digest != digest:
                    self.flag("tampering", f"pin {pin_id} HEAD blob digest differs")
            if traces and pin_id in traces:
                loaded[pin_id] = traces[pin_id]
            elif pin_id in ("reference_run05", "comparison_v2") or pin_id in DERIVED_PINS:
                loaded[pin_id], _ = _load_json(full)
            elif pin_id in ("target_mrdivide", "diagonal_candidate"):
                loaded[pin_id], _ = _load_jsonl(full)

        if any(pin_id not in loaded for pin_id in REQUIRED_PINS):
            return self._result()

        reference = loaded["reference_run05"]
        division = loaded["target_mrdivide"]
        diagonal = loaded["diagonal_candidate"]
        documented = loaded.get("comparison_v2")

        if not isinstance(reference, dict) or reference.get("case") != "C3G":
            self.flag("wrong_case_or_stage", "reference case must be C3G")
        start_div = next((row for row in division if row.get("kind") == "first_step_trace_start"), {})
        start_diag = next((row for row in diagonal if row.get("kind") == "first_step_trace_start"), {})
        if start_div.get("case") != "C3G" or start_diag.get("case") != "C3G":
            self.flag("wrong_case_or_stage", "target case must be C3G")

        try:
            events = reference["pqr_input_probe"]["events"]
            ref_event = events[2]
        except (KeyError, TypeError, IndexError):
            self.flag("wrong_case_or_stage", "reference pair 2 solve event missing")
            return self._result()
        if ref_event.get("time") != 0.0005 or ref_event.get("order") != 3:
            self.flag("wrong_case_or_stage", "reference pair 2 is not stage-2 t=0.0005")

        div_row = next((row for row in division if row.get("mrdivide_seq") == 2), None)
        diag_row = next((row for row in diagonal if row.get("mrdivide_seq") == 2), None)
        if div_row is None or diag_row is None:
            self.flag("wrong_case_or_stage", "pair 2 mrdivide_seq=2 row missing")
            return self._result()

        for label, hexes in (
            ("reference selector2", ref_event["inputs"][1]["hex"]),
            ("division selector2", div_row.get("matrix_hex")),
            ("diagonal selector2", diag_row.get("matrix_hex")),
            ("packet selector2", (document.get("selector2") or {}).get("hex")),
        ):
            if hexes is None:
                self.flag("malformed_hex", f"{label} missing")
                continue
            try:
                decoded = [_as_hex(item) for item in hexes]
            except (TypeError, ValueError) as error:
                self.flag("malformed_hex", f"{label}: {error}")
                continue
            if not _selector_is_diagonal(decoded):
                self.flag("non_diagonal_selector2", f"{label} is not the frozen diagonal J")
            if decoded != [norm_hex(item) for item in FROZEN_SELECTOR2]:
                self.flag("non_diagonal_selector2", f"{label} differs from frozen Selector2")

        for label, values in (
            ("packet residual", document.get("residual_pair2")),
            ("packet discriminating hexes", [
                (document.get("discriminating_point") or {}).get("reference_hex"),
                (document.get("discriminating_point") or {}).get("division_hex"),
                (document.get("discriminating_point") or {}).get("diagonal_hex"),
            ]),
        ):
            if not isinstance(values, list):
                self.flag("malformed_hex", f"{label} missing")
                continue
            for index, value in enumerate(values):
                self.require_hex(value, f"{label}[{index}]")

        try:
            first_div = compare_first(reference, division)
            first_diag = compare_first(reference, diagonal)
            stage2 = compare_stage2(reference, division, documented=documented)
        except (KeyError, TypeError, ValueError, IndexError) as error:
            self.flag("tampering", f"comparator rejected the traces: {error}")
            return self._result()

        if first_div.get("status") != "aligned" or first_diag.get("status") != "aligned":
            self.flag("tampering", "recomputed first-step compare is not aligned")
            return self._result()
        if stage2.get("status") != "aligned":
            self.flag("tampering", "recomputed stage-2 compare is not aligned")
            return self._result()

        earliest = first_div.get("earliest_difference") or {}
        if earliest.get("stage") != 2 or earliest.get("index") != 1 or earliest.get("block") != "p,q,r":
            self.flag("solve_form_mismatch", "earliest mapped difference is not pair 2 / index 1")
        point = document.get("discriminating_point") or {}
        if point.get("pair") != 2 or point.get("index") != 1 or point.get("verified") is not True:
            self.flag("solve_form_mismatch", "packet discriminating_point must be pair 2 / index 1")
        if point.get("stage") != 2:
            self.flag("wrong_case_or_stage", "discriminating_point.stage must be 2")

        try:
            ref_q = _as_hex(ref_event["outputs"][0]["hex"][1])
            div_q = _as_hex(div_row["result_hex"][1])
            diag_q = _as_hex(diag_row["result_hex"][1])
            packet_ref = _as_hex(point.get("reference_hex"))
            packet_div = _as_hex(point.get("division_hex"))
            packet_diag = _as_hex(point.get("diagonal_hex"))
        except (TypeError, ValueError, KeyError, IndexError) as error:
            self.flag("malformed_hex", f"pair 2 index 1 hex: {error}")
            return self._result()

        if (ref_q, div_q, diag_q) != (REF_HEX, DIV_HEX, REF_HEX):
            self.flag("solve_form_mismatch", "source pair 2 / index 1 hexes differ from the verified pair")
        if (packet_ref, packet_div, packet_diag) != (ref_q, div_q, diag_q):
            self.flag("solve_form_mismatch", "packet hexes do not match recomputed pair 2 / index 1")
        if ulp_distance(ref_q, div_q) != 1 or ulp_distance(ref_q, diag_q) != 0:
            self.flag("solve_form_mismatch", "ULP distances are not 1 / 0")
        if first_diag.get("earliest_difference") is not None:
            self.flag("solve_form_mismatch", "diagonal candidate is not bitwise equal on mapped states")

        solve_div = (first_div.get("solve") or {}).get("rows") or []
        if len(solve_div) != 5:
            self.flag("solve_form_mismatch", "division compare must have five solve pairs")
        else:
            for index, row in enumerate(solve_div):
                diffs = row.get("result_differences") or []
                if index == 2:
                    if len(diffs) != 1 or diffs[0].get("index") != 1 or diffs[0].get("ulp") != 1:
                        self.flag("solve_form_mismatch", "pair 2 is not the unique 1 ULP q difference")
                elif diffs:
                    self.flag("solve_form_mismatch", f"unexpected solve difference at pair {index}")

        try:
            offline_div, offline_rec = _ieee_pair(NUM_Q, DEN_JYY)
        except ValueError as error:
            self.flag("malformed_hex", f"offline operands: {error}")
            return self._result()
        forms = document.get("solve_forms") or {}
        offline = forms.get("offline_python_ieee754") or {}
        if offline_div != DIV_HEX or offline_rec != REF_HEX:
            self.flag("solve_form_mismatch", "offline division/reciprocal no longer match the pinned pair")
        if offline.get("direct_division_hex") != offline_div or offline.get("multiply_reciprocal_hex") != offline_rec:
            self.flag("solve_form_mismatch", "packet offline solve-form hexes do not match IEEE-754")
        if forms.get("division_form", {}).get("matches_reference") is not False:
            self.flag("solve_form_mismatch", "division form must not be recorded as matching reference")
        if forms.get("diagonal_reciprocal_form", {}).get("matches_reference") is not True:
            self.flag("solve_form_mismatch", "diagonal form must match reference at the verified point")

        unobserved = document.get("unobserved_domain") or {}
        if (
            unobserved.get("unmapped_states") != 23
            or unobserved.get("total_states") != 36
            or unobserved.get("mapped_states") != 13
            or unobserved.get("case_count") != 1
            or unobserved.get("step_count") != 1
            or unobserved.get("inertia") != "diagonal_J_only"
        ):
            self.flag("wrong_type", "unobserved domain must record 23/36, one case/one step, diagonal J only")

        options = document.get("owner_options")
        if not isinstance(options, list) or [item.get("id") for item in options] != list(OWNER_IDS):
            self.flag("wrong_type", "owner_options must be exactly the three listed options")
        else:
            for index, item in enumerate(options):
                self.check_keys(item, OPTION_KEYS, f"owner_options[{index}]")
                if item.get("chosen") is not False:
                    self.flag("owner_decision_made", "no owner option may be chosen")

        owner = document.get("owner_decision") or {}
        if owner.get("state") != "not_made" or owner.get("chosen_option") is not None:
            self.flag("owner_decision_made", "owner_decision must stay not_made")

        effects = document.get("b1_b4_effects") or {}
        if effects.get("chosen_for_owner") is not False:
            self.flag("owner_decision_made", "b1_b4_effects must not choose for the owner")
        for key in ("B1", "B4"):
            block = effects.get(key) or {}
            per_option = block.get("per_option") or {}
            if set(per_option) != set(OWNER_IDS):
                self.flag("missing_key", f"{key} must state effects for every owner option")
        if (effects.get("B1") or {}).get("current") != "unapproved":
            self.flag("budget_or_contract_freeze", "B1.current must remain exactly unapproved")
        if (effects.get("B4") or {}).get("current") != "unfrozen":
            self.flag("budget_or_contract_freeze", "B4.current must remain exactly unfrozen")

        return self._result()

    def _result(self):
        status = "verified" if not self.violations else "rejected"
        return {
            "status": status,
            "g6_acceptance": False,
            "physical_accuracy": False,
            "reasons": [item["message"] for item in self.violations],
            "codes": self.codes(),
        }


def verify_decision(document, traces=None):
    return Verifier().verify(document, traces=traces)


def load_packet():
    document, digest = _load_json(PACKET)
    return document, digest


def load_source_traces():
    document, _ = load_packet()
    pins = document["pins"]
    reference, _ = _load_json(ROOT / pins["reference_run05"]["path"])
    division, _ = _load_jsonl(ROOT / pins["target_mrdivide"]["path"])
    diagonal, _ = _load_jsonl(ROOT / pins["diagonal_candidate"]["path"])
    return reference, division, diagonal


class RealPacketTests(unittest.TestCase):
    def test_packet_verifies_and_never_accepts_g6(self):
        document, digest = load_packet()
        result = verify_decision(document)
        self.assertEqual(result["status"], "verified", result["reasons"])
        self.assertFalse(result["g6_acceptance"])
        self.assertFalse(result["physical_accuracy"])
        self.assertFalse(document["g6_acceptance"])
        self.assertFalse(document["physical_accuracy"])
        self.assertEqual(digest, _sha256(PACKET))

    def test_recomputed_pins_match_worktree_and_head(self):
        document, _ = load_packet()
        for pin_id in TRACKED_PINS:
            pin = document["pins"][pin_id]
            path = ROOT / pin["path"]
            self.assertEqual(pin["sha256"], _sha256(path))
            self.assertEqual(pin["sha256"], _head_blob_sha256(pin["path"]))
            self.assertTrue(pin["tracked_at_head"])

    def test_discriminating_point_is_exactly_pair_2_index_1(self):
        document, _ = load_packet()
        point = document["discriminating_point"]
        self.assertTrue(point["verified"])
        self.assertEqual(point["pair"], 2)
        self.assertEqual(point["index"], 1)
        self.assertEqual(point["mrdivide_seq"], 2)
        self.assertEqual(point["stage"], 2)
        self.assertEqual(point["reference_hex"], REF_HEX)
        self.assertEqual(point["division_hex"], DIV_HEX)
        self.assertEqual(point["diagonal_hex"], REF_HEX)
        self.assertEqual(point["ulp_division_vs_reference"], 1)
        self.assertEqual(point["ulp_diagonal_vs_reference"], 0)

    def test_unobserved_domain_is_explicit(self):
        document, _ = load_packet()
        domain = document["unobserved_domain"]
        self.assertEqual(domain["unmapped_states"], 23)
        self.assertEqual(domain["total_states"], 36)
        self.assertEqual(domain["mapped_states"], 13)
        self.assertEqual(domain["case_count"], 1)
        self.assertEqual(domain["step_count"], 1)
        self.assertEqual(domain["inertia"], "diagonal_J_only")

    def test_three_owner_options_none_chosen(self):
        document, _ = load_packet()
        self.assertEqual([item["id"] for item in document["owner_options"]], list(OWNER_IDS))
        self.assertTrue(all(item["chosen"] is False for item in document["owner_options"]))
        self.assertTrue(all(set(item) == set(OPTION_KEYS) for item in document["owner_options"]))
        self.assertIsNone(document["owner_decision"]["chosen_option"])
        self.assertFalse(document["b1_b4_effects"]["chosen_for_owner"])
        self.assertEqual(document["b1_b4_effects"]["B1"]["current"], "unapproved")
        self.assertEqual(document["b1_b4_effects"]["B4"]["current"], "unfrozen")
        self.assertEqual(document["identity"]["case"], "C3G")
        self.assertEqual(document["identity"]["stage"], 2)
        self.assertEqual(document["observed_at"]["head"], HEAD)
        self.assertEqual(set(document["pins"]), set(CLOSED_PINS))
        self.assertEqual(set(document["evidence_policy"]["fail_closed_on"]), set(FAIL_CLOSED_ON))
        for key in ("B1", "B4"):
            self.assertEqual(set(document["b1_b4_effects"][key]["per_option"]), set(OWNER_IDS))

    def test_coordination_replays_match_pins(self):
        document, _ = load_packet()
        for pin_id in DERIVED_PINS:
            pin = document["pins"][pin_id]
            self.assertEqual(pin["sha256"], _sha256(ROOT / pin["path"]))
            payload, _ = _load_json(ROOT / pin["path"])
            self.assertEqual(payload["status"], "aligned")
            self.assertFalse(payload.get("g6_acceptance", False))
        self.assertTrue(MARKDOWN.is_file())
        recheck, _ = _load_json(COORD / "recheck.json")
        self.assertFalse(recheck["g6_acceptance"])
        self.assertFalse(recheck["physical_accuracy"])
        self.assertTrue(recheck["discriminating_point"]["verified"])
        self.assertEqual(recheck["discriminating_point"]["pair"], 2)
        self.assertEqual(recheck["discriminating_point"]["index"], 1)
        self.assertEqual(recheck["owner_decision"], "not_made")
        self.assertEqual(recheck["checkout"]["head"], HEAD)
        self.assertEqual(recheck["source_pins"]["reference_run05"], document["pins"]["reference_run05"]["sha256"])
        self.assertEqual(recheck["source_pins"]["target_mrdivide"], document["pins"]["target_mrdivide"]["sha256"])
        self.assertEqual(recheck["source_pins"]["diagonal_candidate"], document["pins"]["diagonal_candidate"]["sha256"])

    def test_markdown_does_not_claim_acceptance(self):
        text = MARKDOWN.read_text(encoding="utf-8")
        self.assertIn("g6_acceptance=false", text)
        self.assertIn("physical_accuracy=false", text)
        self.assertIn("pair 2", text)
        self.assertIn("不是数值验收或 G6 通过", text)
        self.assertNotIn("G6/Full 已通过", text)
        self.assertNotIn("宣称 G6 通过", text)


class MutationTests(unittest.TestCase):
    def reject(self, mutate_document=None, traces=None):
        document, _ = load_packet()
        if mutate_document:
            mutate_document(document)
        if traces is None:
            reference, division, diagonal = load_source_traces()
            traces = {
                "reference_run05": reference,
                "target_mrdivide": division,
                "diagonal_candidate": diagonal,
            }
        return verify_decision(document, traces=traces)

    def test_malformed_hex_rejected(self):
        result = self.reject(lambda doc: doc["discriminating_point"].__setitem__("reference_hex", "bc56 ZZ"))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("malformed_hex", result["codes"])
        self.assertFalse(result["g6_acceptance"])

    def test_wrong_case_rejected(self):
        reference, division, diagonal = load_source_traces()
        reference["case"] = "C0"
        result = self.reject(traces={
            "reference_run05": reference,
            "target_mrdivide": division,
            "diagonal_candidate": diagonal,
        })
        self.assertEqual(result["status"], "rejected")
        self.assertIn("wrong_case_or_stage", result["codes"])

    def test_wrong_stage_rejected(self):
        def mutate(document):
            document["identity"]["stage"] = 1
        result = self.reject(mutate)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("wrong_case_or_stage", result["codes"])

    def test_identity_wrong_case_rejected(self):
        result = self.reject(lambda doc: doc["identity"].__setitem__("case", "C0"))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("wrong_case_or_stage", result["codes"])

    def test_non_diagonal_selector2_rejected(self):
        reference, division, diagonal = load_source_traces()
        mutated = list(division)
        row = next(item for item in mutated if item.get("mrdivide_seq") == 2)
        row["matrix_hex"] = list(row["matrix_hex"])
        row["matrix_hex"][1] = "0x3ff0000000000000"
        result = self.reject(traces={
            "reference_run05": reference,
            "target_mrdivide": mutated,
            "diagonal_candidate": diagonal,
        })
        self.assertEqual(result["status"], "rejected")
        self.assertIn("non_diagonal_selector2", result["codes"])

    def test_solve_form_mismatch_rejected(self):
        def mutate(document):
            document["discriminating_point"]["division_hex"] = REF_HEX
            document["solve_forms"]["division_form"]["matches_reference"] = True
        result = self.reject(mutate)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("solve_form_mismatch", result["codes"])

    def test_missing_pins_rejected(self):
        def mutate(document):
            del document["pins"]["diagonal_candidate"]
        result = self.reject(mutate)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("missing_pins", result["codes"])

    def test_extra_pin_rejected(self):
        def mutate(document):
            document["pins"]["bonus"] = dict(document["pins"]["comparison_v2"])
            document["pins"]["bonus"]["id"] = "bonus"
        result = self.reject(mutate)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("unknown_key", result["codes"])

    def test_unknown_option_key_rejected(self):
        result = self.reject(lambda doc: doc["owner_options"][0].__setitem__("secret", True))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("unknown_key", result["codes"])

    def test_fourth_option_rejected(self):
        def mutate(document):
            document["owner_options"].append(
                {"id": "secret_fourth", "label": "extra", "chosen": False, "summary": "x"}
            )
        result = self.reject(mutate)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("wrong_type", result["codes"])

    def test_unknown_top_level_key_rejected(self):
        result = self.reject(lambda doc: doc.__setitem__("bonus_option", True))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("unknown_key", result["codes"])

    def test_b1_approved_rejected(self):
        result = self.reject(lambda doc: doc["b1_b4_effects"]["B1"].__setitem__("current", "approved"))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("budget_or_contract_freeze", result["codes"])
        self.assertFalse(result["g6_acceptance"])
        self.assertFalse(result["physical_accuracy"])

    def test_b4_frozen_rejected(self):
        result = self.reject(lambda doc: doc["b1_b4_effects"]["B4"].__setitem__("current", "frozen"))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("budget_or_contract_freeze", result["codes"])
        self.assertFalse(result["g6_acceptance"])
        self.assertFalse(result["physical_accuracy"])

    def test_tampered_pin_hash_rejected(self):
        def mutate(document):
            document["pins"]["reference_run05"]["sha256"] = "0" * 64
        result = self.reject(mutate)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("tampering", result["codes"])

    def test_acceptance_flag_rejected(self):
        result = self.reject(lambda doc: doc.__setitem__("g6_acceptance", True))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("g6_or_physical_acceptance_claim", result["codes"])
        self.assertFalse(result["g6_acceptance"])
        self.assertFalse(result["physical_accuracy"])

    def test_physical_accuracy_flag_rejected(self):
        result = self.reject(lambda doc: doc.__setitem__("physical_accuracy", True))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("g6_or_physical_acceptance_claim", result["codes"])
        self.assertFalse(result["g6_acceptance"])
        self.assertFalse(result["physical_accuracy"])

    def test_owner_choice_rejected(self):
        def mutate(document):
            document["owner_options"][0]["chosen"] = True
            document["owner_decision"]["state"] = "made"
            document["owner_decision"]["chosen_option"] = "adopt_diagonal_branch"
        result = self.reject(mutate)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("owner_decision_made", result["codes"])


if __name__ == "__main__":
    unittest.main()
