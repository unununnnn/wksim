"""Pure tests for tools/compare_first_step_trace.py.

The real-artifact replay reproduces comparison-v2's earliest difference
(p,q,r stage 2 derivatives[1], 1 ULP).  Negative fixtures are mutations of the
real artifacts.  No model/MATLAB/ROS/native execution.

Run from the repo root:  python -B -m unittest validation.test_compare_first_step_trace
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.compare_first_step_trace import (  # noqa: E402
    compare,
    decode_f64_hex,
    main,
    norm_hex,
    ulp_distance,
)

REFERENCE = (ROOT / "validation/coordination/g6-reference-probe-20260913"
             / "run-03/reference-first-step.json")
TARGET = (ROOT / "validation/coordination/g6-target-first-step-20260913"
          / "first-step-trace.jsonl")


def load():
    reference = json.loads(REFERENCE.read_bytes().decode("utf-8"))
    target = [json.loads(line)
              for line in TARGET.read_bytes().decode("utf-8").splitlines()
              if line.strip()]
    return reference, target


@unittest.skipUnless(REFERENCE.is_file() and TARGET.is_file(),
                     "proven artifacts not present")
class RealArtifactTests(unittest.TestCase):
    def test_replay_reproduces_v2_earliest_difference(self):
        reference, target = load()
        result = compare(reference, target)
        self.assertEqual(result["status"], "aligned")
        earliest = result["earliest_difference"]
        self.assertEqual(earliest["block"], "p,q,r")
        self.assertEqual(earliest["stage"], 2)
        self.assertEqual(earliest["field"], "derivatives")
        self.assertEqual(earliest["index"], 1)
        self.assertEqual(earliest["reference_hex"], "bc56d4db33a987b8")
        self.assertEqual(earliest["target_hex"], "0xbc56d4db33a987b9")
        self.assertEqual(earliest["ulp"], 1)
        counts = {b["block"]: b["stage_difference_count"]
                  for b in result["blocks"]}
        self.assertEqual(counts, {"q0 q1 q2 q3": 2, "p,q,r": 2,
                                  "xe,ye,ze": 0, "ub,vb,wb": 1})

    def test_cli_binds_hashes_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.json"
            code = main(["--reference", str(REFERENCE), "--target", str(TARGET),
                         "--output", str(output)])
            self.assertEqual(code, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            import hashlib
            self.assertEqual(written["reference_sha256"],
                             hashlib.sha256(REFERENCE.read_bytes()).hexdigest())
            self.assertEqual(written["target_sha256"],
                             hashlib.sha256(TARGET.read_bytes()).hexdigest())
            self.assertEqual(
                main(["--reference", str(REFERENCE), "--target", str(TARGET),
                      "--output", str(output)]), 1)
            self.assertEqual(json.loads(output.read_text())["status"],
                             "aligned")  # untouched by the refused second write


class NegativeFixtureTests(unittest.TestCase):
    """Mutations of the real artifacts must never align."""

    def compare_mutated(self, mutate_target=None, mutate_reference=None):
        reference, target = load()
        if mutate_reference:
            mutate_reference(reference)
        if mutate_target:
            mutate_target(target)
        return compare(reference, target)

    def test_missing_stage_rejected(self):
        result = self.compare_mutated(
            mutate_target=lambda t: t.pop(3))  # one ode4_stage row
        self.assertEqual(result["status"], "rejected")

    def test_wrong_stage_time_rejected(self):
        def mutate(t):
            for row in t:
                if row.get("kind") == "ode4_stage" and row.get("stage") == 2:
                    row["time_s"] = "0x3f60624dd2f1a9fc"  # 0.002
        result = self.compare_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_duplicate_stage_rejected(self):
        def mutate(t):
            stage2 = next(r for r in t if r.get("kind") == "ode4_stage"
                          and r.get("stage") == 2)
            t.insert(3, dict(stage2))
        result = self.compare_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_invalid_hex_rejected(self):
        def mutate(t):
            row = next(r for r in t if r.get("kind") == "ode4_stage")
            row["state_hex"][0] = "0xZZZZ"
        result = self.compare_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_nonfinite_hex_rejected(self):
        def mutate(t):
            row = next(r for r in t if r.get("kind") == "ode4_stage")
            row["state_hex"][0] = "0x7ff0000000000000"  # +inf
        result = self.compare_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_reference_missing_block_rejected(self):
        def mutate(r):
            r["events"] = [e for e in r["events"] if "p,q,r" not in e["block"]]
            r["event_count"] = len(r["events"])
        result = self.compare_mutated(mutate_reference=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_reference_merged_same_time_events_rejected(self):
        # Dropping one of the two t=0.0005 PostDerivatives breaks the real
        # callback-order sequence; the alignment must not survive.
        def mutate(r):
            seen = False
            kept = []
            for e in r["events"]:
                if (e.get("event") == "PostDerivatives" and e.get("time") == 0.0005
                        and "p,q,r" in e["block"]):
                    if seen:
                        continue
                    seen = True
                kept.append(e)
            r["events"] = kept
            r["event_count"] = len(kept)
        result = self.compare_mutated(mutate_reference=mutate)
        self.assertEqual(result["status"], "rejected")


class PrimitiveTests(unittest.TestCase):
    def test_hex_decode_and_ulp(self):
        self.assertEqual(decode_f64_hex("0x3ff0000000000000"), 1.0)
        self.assertEqual(decode_f64_hex("3ff0000000000000"), 1.0)
        self.assertEqual(norm_hex("0xABCDEF0123456789"), "abcdef0123456789")
        self.assertEqual(ulp_distance("3ff0000000000000", "0x3ff0000000000001"), 1)
        with self.assertRaises(ValueError):
            decode_f64_hex("0x123")
        with self.assertRaises(ValueError):
            decode_f64_hex("0x7ff8000000000000")  # NaN


TARGET_MAJOR = (ROOT / "validation/coordination/g6-target-first-step-20260913"
                / "with-major/first-step-trace.jsonl")


@unittest.skipUnless(TARGET_MAJOR.is_file(), "with-major artifact not present")
class WithMajorArtifactTests(unittest.TestCase):
    def test_with_major_trace_aligns_and_reproduces_v2(self):
        reference, target = load()
        target = [json.loads(line) for line in
                  TARGET_MAJOR.read_bytes().decode("utf-8").splitlines()
                  if line.strip()]
        result = compare(reference, target)
        self.assertEqual(result["status"], "aligned")
        earliest = result["earliest_difference"]
        self.assertEqual(earliest["block"], "p,q,r")
        self.assertEqual(earliest["stage"], 2)
        self.assertEqual(earliest["ulp"], 1)


class MainReviewFixTests(unittest.TestCase):
    """Each of the four main-review failures gets a proving negative."""

    def compare_mutated(self, mutate_target=None, mutate_reference=None):
        reference, target = load()
        if mutate_reference:
            mutate_reference(reference)
        if mutate_target:
            mutate_target(target)
        return compare(reference, target)

    def test_dropped_events_rejected(self):
        result = self.compare_mutated(
            mutate_reference=lambda r: r.update(dropped_events=1))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("dropped_events", result["reasons"][0])

    def test_update_post_hex_invalid_rejected(self):
        def mutate(t):
            row = next(r for r in t if r.get("kind") == "ode4_update")
            row["post_hex"][6] = "nothex"
        result = self.compare_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_update_nxc_and_width_rejected(self):
        def mutate(t):
            row = next(r for r in t if r.get("kind") == "ode4_update")
            row["nXc"] = 35
        result = self.compare_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")
        def mutate2(t):
            row = next(r for r in t if r.get("kind") == "ode4_update")
            row["pre_hex"] = row["pre_hex"][:-1]
        result = self.compare_mutated(mutate_target=mutate2)
        self.assertEqual(result["status"], "rejected")

    def test_reference_single_dtype_rejected(self):
        def mutate(r):
            for e in r["events"]:
                if e.get("event") == "PostDerivatives":
                    e["derivatives"]["dtype"] = "single"
        result = self.compare_mutated(mutate_reference=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_reference_wrong_shape_or_hex_length_rejected(self):
        def mutate(r):
            for e in r["events"]:
                if e.get("event") == "PostDerivatives" and "q0" in e["block"]:
                    e["cont_states"]["shape"] = [2, 2]
        result = self.compare_mutated(mutate_reference=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_pseudo_block_substring_never_matches(self):
        def mutate(r):
            real = [e for e in r["events"] if "p,q,r" not in e["block"]]
            pseudo = [dict(e, block="Exp1/fake/p,q,r_helper")
                      for e in r["events"] if "p,q,r" in e["block"]]
            r["events"] = real + pseudo
            r["event_count"] = len(r["events"])
        result = self.compare_mutated(mutate_reference=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_major_misplaced_rejected(self):
        def mutate(t):
            k1 = next(i for i, r in enumerate(t)
                      if r.get("kind") == "major_output" and r.get("k") == 1)
            row = t.pop(k1)
            t.insert(2, row)  # k=1 before the stages
        reference, target = load()
        target = [json.loads(line) for line in
                  TARGET_MAJOR.read_bytes().decode("utf-8").splitlines()
                  if line.strip()]
        mutate(target)
        result = compare(reference, target)
        self.assertEqual(result["status"], "rejected")

    def test_malformed_inputs_are_structured_rejections(self):
        result = compare({"events": "not-a-list"}, load()[1])
        self.assertEqual(result["status"], "rejected")
        result = compare(load()[0], ["not-a-dict"])
        self.assertEqual(result["status"], "rejected")

    def test_cross_sign_ulp_and_signed_zero_semantics(self):
        self.assertIsNone(ulp_distance("3ff0000000000000", "bff0000000000000"))
        self.assertIsNone(ulp_distance("0000000000000000", "8000000000000000"))
        self.assertEqual(ulp_distance("3ff0000000000000", "3ff0000000000001"), 1)
        # The difference record carries the sign_flip flag explicitly.
        reference, target = load()
        reference["events"] = [
            dict(e, **{"cont_states": dict(e["cont_states"],
                   hex=["8000000000000000" if h == "0000000000000000" else h
                        for h in e["cont_states"]["hex"]])})
            if e.get("event") == "PostDerivatives" else e
            for e in reference["events"]]
        result = compare(reference, target)
        flips = [d for b in result["blocks"] for d in b["stage_differences"]
                 if d["sign_flip"]]
        self.assertTrue(flips)
        self.assertTrue(all(d["ulp"] is None for d in flips))


REFERENCE_SOLVE = (ROOT / "validation/coordination/g6-reference-probe-20260913"
                   / "run-05/reference-first-step.json")
TARGET_SOLVE = (ROOT / "validation/coordination/g6-target-mrdivide-20260913"
                / "first-step-trace.jsonl")


def load_solve():
    reference = json.loads(REFERENCE_SOLVE.read_bytes().decode("utf-8"))
    target = [json.loads(line) for line in
              TARGET_SOLVE.read_bytes().decode("utf-8").splitlines() if line.strip()]
    return reference, target


@unittest.skipUnless(REFERENCE_SOLVE.is_file() and TARGET_SOLVE.is_file(),
                     "solve artifacts not present")
class SolveArtifactTests(unittest.TestCase):
    def test_malformed_solve_payloads_are_structured_rejections(self):
        mutations = [
            lambda r, t: r['pqr_input_probe']['events'][0]['inputs'].pop(),
            lambda r, t: r['pqr_input_probe']['events'][0]['inputs'].append({}),
            lambda r, t: r['pqr_input_probe'].update(event_count=6),
            lambda r, t: r['pqr_input_probe']['events'][0].update(time=False),
            lambda r, t: r['pqr_input_probe']['events'].__setitem__(0, None),
            lambda r, t: r['events'].__setitem__(0, None),
            lambda r, t: next(x for x in t if x['kind'] == 'mrdivide_solve').update(mrdivide_seq=False),
            lambda r, t: next(x for x in t if x['kind'] == 'mrdivide_solve').pop('time_s'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                reference, target = load_solve()
                mutate(reference, target)
                self.assertEqual(compare(reference, target)['status'], 'rejected')

    def test_disabled_optional_probe_remains_compatible_with_legacy_trace(self):
        reference, target = load()
        reference['pqr_input_probe'] = {'enabled': False}
        self.assertEqual(compare(reference, target)['status'], 'aligned')

    def test_real_solve_comparison_reproduces_boundary(self):
        reference, target = load_solve()
        result = compare(reference, target)
        self.assertEqual(result["status"], "aligned")
        rows = result["solve"]["rows"]
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["numerator_equal"] for row in rows))
        self.assertTrue(all(row["matrix_equal"] for row in rows))
        differences = [(row["sequence"], d) for row in rows
                       for d in row["result_differences"]]
        self.assertEqual(len(differences), 1)
        sequence, diff = differences[0]
        self.assertEqual(sequence, 2)
        self.assertEqual(diff["index"], 1)
        self.assertEqual(diff["reference_hex"], "bc56d4db33a987b8")
        self.assertEqual(diff["target_hex"], "0xbc56d4db33a987b9")
        self.assertEqual(diff["ulp"], 1)

    def compare_solve_mutated(self, mutate_target=None, mutate_reference=None):
        reference, target = load_solve()
        if mutate_reference:
            mutate_reference(reference)
        if mutate_target:
            mutate_target(target)
        return compare(reference, target)

    def test_missing_solve_row_rejected(self):
        result = self.compare_solve_mutated(
            mutate_target=lambda t: t.__setitem__(
                slice(None), [r for r in t if r.get("mrdivide_seq") != 3]))
        self.assertEqual(result["status"], "rejected")

    def test_out_of_order_solve_rejected(self):
        def mutate(t):
            rows = [r for r in t if r.get("kind") == "mrdivide_solve"]
            rows[1]["mrdivide_seq"], rows[2]["mrdivide_seq"] = 2, 1
        result = self.compare_solve_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_wrong_result_mapping_rejected(self):
        def mutate(t):
            rows = [r for r in t if r.get("kind") == "mrdivide_solve"]
            rows[0]["result_hex"] = list(rows[0]["result_hex"])
            rows[0]["result_hex"][1] = "0x3ff0000000000000"
        result = self.compare_solve_mutated(mutate_target=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_swapped_ports_rejected(self):
        def mutate(r):
            events = r["pqr_input_probe"]["events"]
            for event in events:
                event["inputs"] = [event["inputs"][1], event["inputs"][0]]
        result = self.compare_solve_mutated(mutate_reference=mutate)
        self.assertEqual(result["status"], "rejected")

    def test_wrong_config_rejected(self):
        result = self.compare_solve_mutated(
            mutate_reference=lambda r: r["pqr_input_probe"]["upstream"].update(
                Inputs="**"))
        self.assertEqual(result["status"], "rejected")

    def test_reference_missing_probe_rejected(self):
        result = self.compare_solve_mutated(
            mutate_reference=lambda r: r.pop("pqr_input_probe"))
        self.assertEqual(result["status"], "rejected")

    def test_solve_rows_without_reference_probe_rejected(self):
        # The old run-03 reference has no pqr_input_probe; the solve trace
        # must not align against it.
        reference, target = load_solve()
        reference, _ = load()
        result = compare(reference, target)
        self.assertEqual(result["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
