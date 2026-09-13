"""Pure tests for tools/compare_g6_c3g_stage2.py.

The comparator is a C3G-only, stage-2 operand-boundary reader. Tests are
synthetic except one optional replay of the retained first-step solve pair
already documented for p,q,r derivative index 1. No model, MATLAB, ROS,
native, UE, or build execution.

Run from the repo root:
    python -B -m unittest validation.test_compare_g6_c3g_stage2
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tools.compare_g6_c3g_stage2 import (  # noqa: E402
    DOCUMENTED_REF_Q,
    DOCUMENTED_TGT_Q,
    FROZEN_SELECTOR2,
    OPERAND_SCHEMA,
    STAGE2_TIME_HEX,
    compare,
    decode_f64_hex,
    main,
    ulp_distance,
)

REFERENCE_SOLVE = (
    ROOT / "validation/coordination/g6-reference-probe-20260913"
    / "run-05/reference-first-step.json"
)
TARGET_SOLVE = (
    ROOT / "validation/coordination/g6-target-mrdivide-20260913"
    / "first-step-trace.jsonl"
)
DOCUMENTED_V2 = (
    ROOT / "validation/coordination/g6-target-first-step-20260913"
    / "comparison-v2.json"
)

ZERO = "0000000000000000"
ONE = "3ff0000000000000"
RESIDUAL = ["3befff6b7cf92ee9", "bc000013449033b2", "36ad0bb96b047c00"]
PRODUCT_REF = ["3c47b1ebce4a1e30", DOCUMENTED_REF_Q, "36f8ccceed35d6fd"]
PRODUCT_TGT = ["3c47b1ebce4a1e30", DOCUMENTED_TGT_Q, "36f8ccceed35d6fd"]


def _hex_list(values):
    return [ZERO if value == 0 else value for value in values]


def packet(**overrides):
    """Minimal valid dedicated operand-boundary packet."""
    operands = {
        "residual": list(RESIDUAL),
        "selector2": list(FROZEN_SELECTOR2),
        "product2": list(PRODUCT_REF),
        "M1_1": ZERO,
        "Fd_0": ZERO,
        "Sum1_a_1": ZERO,
        "TT0gLR": ZERO,
        "Sum4_f": [ZERO, ZERO, ZERO],
        "aero_damp_q": ZERO,
    }
    if "operands" in overrides:
        operands.update(overrides.pop("operands"))
    payload = {
        "schema": OPERAND_SCHEMA,
        "case": "C3G",
        "k": [0, 1],
        "stage": 2,
        "time_s": STAGE2_TIME_HEX,
        "solver": "ode4",
        "block": "p,q,r",
        "field": "derivatives",
        "index": 1,
        "operands": operands,
    }
    payload.update(overrides)
    return payload


def documented_compact():
    return {
        "case": "C3G",
        "stage": 2,
        "field": "derivatives",
        "index": 1,
        "reference_hex": DOCUMENTED_REF_Q,
        "target_hex": DOCUMENTED_TGT_Q,
        "ulp": 1,
    }


class PrimitiveTests(unittest.TestCase):
    def test_documented_hex_is_one_ulp(self):
        self.assertEqual(ulp_distance(DOCUMENTED_REF_Q, "0x" + DOCUMENTED_TGT_Q), 1)
        self.assertAlmostEqual(decode_f64_hex(STAGE2_TIME_HEX), 0.0005)

    def test_frozen_selector2_is_diag_uavj(self):
        self.assertEqual(len(FROZEN_SELECTOR2), 9)
        self.assertEqual(FROZEN_SELECTOR2[0], "3f959b3d07c84b5e")
        self.assertEqual(FROZEN_SELECTOR2[4], "3f966cf41f212d77")
        self.assertEqual(FROZEN_SELECTOR2[8], "3fa2bd3c36113405")
        self.assertTrue(all(FROZEN_SELECTOR2[i] == ZERO for i in (1, 2, 3, 5, 6, 7)))


class DedicatedPacketTests(unittest.TestCase):
    def test_identical_operands_different_result_is_observation_not_cause(self):
        reference = packet()
        target = packet(operands={"product2": list(PRODUCT_TGT)})
        result = compare(reference, target)
        self.assertEqual(result["status"], "aligned", result.get("reasons"))
        self.assertEqual(result["observation"]["kind"],
                         "identical_operands_different_result")
        self.assertTrue(result["operands"]["residual"]["equal"])
        self.assertTrue(result["operands"]["selector2"]["equal"])
        diffs = result["operands"]["product2"]["differences"]
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["index"], 1)
        self.assertEqual(diffs[0]["ulp"], 1)
        self.assertFalse(diffs[0]["sign_flip"])
        self.assertEqual(result["causal"]["status"], "unproven")
        self.assertEqual(result["operands"]["subterms"]["status"], "compared")
        self.assertTrue(all(field["equal"]
                            for field in result["operands"]["subterms"]["fields"].values()))
        claims = " ".join(result["non_claims"])
        self.assertIn("G6", claims)
        self.assertIn("Full", claims)
        self.assertNotIn("accepted", json.dumps(result).lower())

    def test_residual_difference_classifies_upstream_branch(self):
        reference = packet()
        target = packet(operands={
            "residual": [RESIDUAL[0], "bc000013449033b3", RESIDUAL[2]],
            "product2": list(PRODUCT_TGT),
            "M1_1": ONE,
        })
        result = compare(reference, target)
        self.assertEqual(result["status"], "aligned", result.get("reasons"))
        self.assertEqual(result["observation"]["kind"], "residual_already_differs")
        self.assertFalse(result["operands"]["residual"]["equal"])
        self.assertEqual(result["operands"]["residual"]["differences"][0]["ulp"], 1)
        self.assertFalse(result["operands"]["subterms"]["fields"]["M1_1"]["equal"])
        self.assertTrue(result["operands"]["subterms"]["fields"]["Fd_0"]["equal"])
        self.assertEqual(result["causal"]["status"], "unproven")

    def test_selector2_difference_is_not_solve_kernel_observation(self):
        mutated = list(FROZEN_SELECTOR2)
        mutated[4] = "3f966cf41f212d78"
        result = compare(packet(), packet(operands={"selector2": mutated}))
        self.assertEqual(result["status"], "aligned", result.get("reasons"))
        self.assertEqual(result["observation"]["kind"], "selector2_already_differs")
        self.assertEqual(result["causal"]["status"], "unproven")

    def test_bitwise_match_is_still_not_acceptance(self):
        result = compare(packet(), packet())
        self.assertEqual(result["status"], "aligned")
        self.assertEqual(result["observation"]["kind"],
                         "identical_operands_identical_result")
        self.assertEqual(result["causal"]["status"], "unproven")
        self.assertIsNone(result["observation"].get("g6_accepted"))

    def test_documented_binding_accepts_matching_product2(self):
        target = packet(operands={"product2": list(PRODUCT_TGT)})
        result = compare(packet(), target, documented=documented_compact())
        self.assertEqual(result["status"], "aligned", result.get("reasons"))
        self.assertTrue(result["observation"]["matches_documented_divergence"])
        self.assertEqual(result["observation"]["documented_q_ulp"], 1)

    def test_documented_binding_rejects_wrong_product2_pair(self):
        target = packet(operands={"product2": [PRODUCT_TGT[0], ONE, PRODUCT_TGT[2]]})
        result = compare(packet(), target, documented=documented_compact())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("documented" in reason for reason in result["reasons"]))

    def test_incomplete_packet_rejected(self):
        reference = packet()
        del reference["operands"]["M1_1"]
        result = compare(reference, packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("incomplete" in reason for reason in result["reasons"]))

    def test_wrong_case_rejected(self):
        result = compare(packet(case="C0"), packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("C3G" in reason for reason in result["reasons"]))

    def test_wrong_stage_rejected(self):
        result = compare(packet(stage=1), packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("stage" in reason for reason in result["reasons"]))

    def test_stage_bool_rejected(self):
        result = compare(packet(stage=True), packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("stage" in reason for reason in result["reasons"]))

    def test_k_bool_rejected(self):
        result = compare(packet(k=[0, True]), packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("k" in reason for reason in result["reasons"]))

    def test_wrong_time_rejected(self):
        result = compare(packet(time_s="3f50624dd2f1a9fc"), packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("time" in reason for reason in result["reasons"]))

    def test_nonfinite_hex_rejected(self):
        result = compare(packet(operands={"TT0gLR": "7ff0000000000000"}), packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("non-finite" in reason for reason in result["reasons"]))

    def test_noncanonical_hex_rejected(self):
        result = compare(packet(operands={"Fd_0": "0000 0000 0000 0000"}), packet())
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("non-canonical" in reason for reason in result["reasons"]))

    def test_wrong_selector2_width_rejected(self):
        result = compare(packet(operands={"selector2": list(FROZEN_SELECTOR2)[:8]}),
                         packet())
        self.assertEqual(result["status"], "rejected")

    def test_format_mismatch_rejected(self):
        result = compare(packet(), [{"kind": "mrdivide_solve"}])
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("identity" in reason or "format" in reason
                            for reason in result["reasons"]))

    def test_malformed_payloads_are_structured_rejections(self):
        for reference, target in (
            (None, packet()),
            ("not-a-dict", packet()),
            (packet(), None),
            ({"schema": OPERAND_SCHEMA, "operands": "nope"}, packet()),
        ):
            result = compare(reference, target)
            self.assertEqual(result["status"], "rejected", (reference, result))
            self.assertTrue(result["reasons"])

    def test_sign_flip_has_no_ulp(self):
        target = packet(operands={"product2": [PRODUCT_REF[0], "3c56d4db33a987b8",
                                              PRODUCT_REF[2]]})
        result = compare(packet(), target)
        self.assertEqual(result["status"], "aligned", result.get("reasons"))
        diff = result["operands"]["product2"]["differences"][0]
        self.assertTrue(diff["sign_flip"])
        self.assertIsNone(diff["ulp"])
        self.assertEqual(result["causal"]["status"], "unproven")


@unittest.skipUnless(REFERENCE_SOLVE.is_file() and TARGET_SOLVE.is_file(),
                     "retained C3G solve traces not present")
class RetainedTraceTests(unittest.TestCase):
    def _load(self):
        reference = json.loads(REFERENCE_SOLVE.read_bytes().decode("utf-8"))
        target = [json.loads(line) for line in
                  TARGET_SOLVE.read_bytes().decode("utf-8").splitlines()
                  if line.strip()]
        return reference, target

    def test_retained_solve_pair_reproduces_documented_boundary(self):
        result = compare(*self._load())
        self.assertEqual(result["status"], "aligned", result.get("reasons"))
        self.assertEqual(result["identity"]["case"], "C3G")
        self.assertEqual(result["identity"]["stage"], 2)
        self.assertEqual(result["identity"]["index"], 1)
        self.assertTrue(result["operands"]["residual"]["equal"])
        self.assertTrue(result["operands"]["selector2"]["equal"])
        diffs = result["operands"]["product2"]["differences"]
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["index"], 1)
        self.assertEqual(norm_hex_pair(diffs[0]["reference_hex"]), DOCUMENTED_REF_Q)
        self.assertEqual(norm_hex_pair(diffs[0]["target_hex"]), DOCUMENTED_TGT_Q)
        self.assertEqual(diffs[0]["ulp"], 1)
        self.assertEqual(result["observation"]["kind"],
                         "identical_operands_different_result")
        self.assertEqual(result["operands"]["subterms"]["status"], "unobserved")
        self.assertEqual(result["causal"]["status"], "unproven")

    def test_retained_pair_binds_comparison_v2(self):
        documented = json.loads(DOCUMENTED_V2.read_bytes().decode("utf-8"))
        result = compare(*self._load(), documented=documented)
        self.assertEqual(result["status"], "aligned", result.get("reasons"))
        self.assertTrue(result["observation"]["matches_documented_divergence"])

    def test_wrong_case_on_retained_reference_rejected(self):
        reference, target = self._load()
        reference["case"] = "C2G"
        result = compare(reference, target)
        self.assertEqual(result["status"], "rejected")

    def test_missing_stage2_solve_row_rejected(self):
        reference, target = self._load()
        target = [row for row in target if row.get("mrdivide_seq") != 2]
        result = compare(reference, target)
        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("incomplete" in reason or "stage" in reason
                            for reason in result["reasons"]))

    def test_nonfinite_retained_numerator_rejected(self):
        reference, target = self._load()
        row = next(item for item in target if item.get("mrdivide_seq") == 2)
        row["numerator_hex"][1] = "0x7ff8000000000000"
        result = compare(reference, target)
        self.assertEqual(result["status"], "rejected")

    def test_bool_mrdivide_seq_rejected(self):
        reference, target = self._load()
        row = next(item for item in target if item.get("mrdivide_seq") == 2)
        row["mrdivide_seq"] = True
        result = compare(reference, target)
        self.assertEqual(result["status"], "rejected")

    def test_result_not_mapped_to_stage2_pqr_deriv_rejected(self):
        reference, target = self._load()
        row = next(item for item in target if item.get("mrdivide_seq") == 2)
        row["result_hex"] = list(row["result_hex"])
        row["result_hex"][1] = "0x3ff0000000000000"
        result = compare(reference, target)
        self.assertEqual(result["status"], "rejected")


def norm_hex_pair(value):
    text = value[2:] if isinstance(value, str) and value.startswith("0x") else value
    return text.lower()


class CliTests(unittest.TestCase):
    def test_cli_requires_explicit_paths_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            reference = directory / "reference.json"
            target = directory / "target.json"
            output = directory / "out.json"
            reference.write_text(json.dumps(packet()), encoding="utf-8")
            target.write_text(
                json.dumps(packet(operands={"product2": list(PRODUCT_TGT)})),
                encoding="utf-8")
            code = main(["--reference", str(reference), "--target", str(target),
                         "--output", str(output)])
            self.assertEqual(code, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["reference_sha256"],
                             hashlib.sha256(reference.read_bytes()).hexdigest())
            self.assertEqual(written["target_sha256"],
                             hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertEqual(written["observation"]["kind"],
                             "identical_operands_different_result")
            self.assertEqual(
                main(["--reference", str(reference), "--target", str(target),
                      "--output", str(output)]), 1)
            self.assertEqual(json.loads(output.read_text())["status"], "aligned")

    def test_cli_binds_documented_path_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            reference = directory / "reference.json"
            target = directory / "target.json"
            documented = directory / "documented.json"
            output = directory / "out.json"
            reference.write_text(json.dumps(packet()), encoding="utf-8")
            target.write_text(
                json.dumps(packet(operands={"product2": list(PRODUCT_TGT)})),
                encoding="utf-8")
            documented.write_text(json.dumps(documented_compact()), encoding="utf-8")
            self.assertEqual(
                main(["--reference", str(reference), "--target", str(target),
                      "--documented-divergence", str(documented),
                      "--output", str(output)]), 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["documented_sha256"],
                             hashlib.sha256(documented.read_bytes()).hexdigest())
            self.assertTrue(written["observation"]["matches_documented_divergence"])


if __name__ == "__main__":
    unittest.main()
