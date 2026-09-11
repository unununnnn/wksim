"""Pure offline tests for the e0 current-source RHS references slice."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import derive_e0_current_rhs_references as v2  # noqa: E402
from tools.derive_e0_current_source_mapping import GENERATED_RELATIVE_PATH  # noqa: E402

SCHEMA = ROOT / "docs/plan/59-e0-current-rhs-references.schema.json"
CHECKED_IN = ROOT / "validation/e0-current-rhs-references-20260912.json"
V1_MAPPING = ROOT / "validation/e0-current-source-mapping-20260912.json"
REAL_SOURCE = ROOT / GENERATED_RELATIVE_PATH

HEADER = b'#include "Exp1_MinModelTemp.h"\r\n\r\n'
STEP_OPEN = b'void MulticopterModelClass::step()\r\n{\r\n'
STEP_CLOSE = b'}\r\n'


def fixture(slot_writes, prefix_lines=b''):
    """Synthetic pinned-shape source: step with prefix defs then slot writes."""
    return HEADER + prefix_lines + STEP_OPEN + slot_writes + STEP_CLOSE


def mapping_for(source, slots):
    """Build a v1-shaped mapping whose line ranges come from the real parser."""
    from tools import derive_e0_current_source_mapping as v1_mod
    with patch.object(v1_mod, "OUTPORT_SIZES", {"VehileInfo60d": 2}):
        coverage = v1_mod.parse_outport_writes(source)
    out = []
    for array, index, observable, outport in slots:
        start, end, kind = coverage[(outport, index)]
        out.append({"slot": f"{array}[{index}]", "array": array, "index": index,
                    "observable": observable, "outport": outport,
                    "line_ranges": [[start, end]]})
    return {"kind": "e0_current_source_mapping", "slot_count": len(out),
            "generated_source": {"name": "Exp1_MinModelTemp.cpp",
                                 "sha256": "0" * 64, "size_bytes": 1},
            "slots": out}


class TestReferences(unittest.TestCase):
    def test_path_kinds_and_multi_level(self):
        refs = v2._references("Exp1_MinModelTemp_B.MotorNonlinearDynamic1.Motor_Dynamics[0]")
        self.assertEqual(refs, [{"kind": "block_output",
                                 "path": "Exp1_MinModelTemp_B.MotorNonlinearDynamic1.Motor_Dynamics[0]"}])
        refs = v2._references("Exp1_MinModelTemp_X.xeyeze_CSTATE[2]")
        self.assertEqual(refs[0]["kind"], "state")
        refs = v2._references("Exp1_MinModelTemp_P.Gain1_Gain_i")
        self.assertEqual(refs[0]["kind"], "parameter")
        refs = v2._references("(&Exp1_MinModelTemp_M)->Timing.t[0]")
        self.assertEqual(refs, [{"kind": "timing",
                                 "path": "Exp1_MinModelTemp_M->Timing.t[0]"}])

    def test_local_call_and_unknown(self):
        refs = v2._references("std::asin(rtb_Switch)")
        self.assertEqual(refs, [{"kind": "local", "name": "rtb_Switch", "indexed": False},
                                {"kind": "call", "name": "std::asin"}])
        with self.assertRaisesRegex(ValueError, "unknown reference form"):
            v2._references("mystery_global + 1")

    def test_call_with_model_symbol_first_arg_and_nested_calls(self):
        refs = v2._references("std::sin(Exp1_MinModelTemp_B.Product[0])")
        self.assertEqual(refs, [{"kind": "block_output",
                                 "path": "Exp1_MinModelTemp_B.Product[0]"},
                                {"kind": "call", "name": "std::sin"}])
        refs = v2._references("std::max(Exp1_MinModelTemp_P.Gain, 0.0)")
        self.assertEqual(refs, [{"kind": "parameter",
                                 "path": "Exp1_MinModelTemp_P.Gain"},
                                {"kind": "call", "name": "std::max"}])
        refs = v2._references("foo(bar(Exp1_MinModelTemp_B.Product[0]))")
        self.assertEqual(refs, [{"kind": "block_output",
                                 "path": "Exp1_MinModelTemp_B.Product[0]"},
                                {"kind": "call", "name": "foo"},
                                {"kind": "call", "name": "bar"}])
        refs = v2._references("std::atan2(Exp1_MinModelTemp_B.Product[0], Exp1_MinModelTemp_B.Product[1])")
        self.assertEqual(refs, [{"kind": "block_output",
                                 "path": "Exp1_MinModelTemp_B.Product[0]"},
                                {"kind": "block_output",
                                 "path": "Exp1_MinModelTemp_B.Product[1]"},
                                {"kind": "call", "name": "std::atan2"}])

    def test_model_reference_requires_timing_form(self):
        # The only legal model reference is (&...M)->Timing.t[<index>]; any other
        # Exp1_MinModelTemp_M use must be a stable fail-closed ValueError, never a
        # bare KeyError.
        refs = v2._references("(&Exp1_MinModelTemp_M)->Timing.t[1]")
        self.assertEqual(refs, [{"kind": "timing",
                                 "path": "Exp1_MinModelTemp_M->Timing.t[1]"}])
        with self.assertRaisesRegex(ValueError, "model .* must use"):
            v2._references("Exp1_MinModelTemp_M.SomeField")

    def test_constant_rhs_has_no_references(self):
        self.assertEqual(v2._references("0.0"), [])
        self.assertEqual(v2._references("2.5e3"), [])

    def test_comparison_operators_are_not_references(self):
        refs = v2._references("(rtb_a == rtb_b)")
        self.assertEqual(refs, [{"kind": "local", "name": "rtb_a", "indexed": False},
                                {"kind": "local", "name": "rtb_b", "indexed": False}])


class TestBuildArtifact(unittest.TestCase):
    def build(self, writes, prefix=b''):
        source = fixture(writes, prefix)
        mapping = mapping_for(source, [
            ("Vehicle60", 0, "obs_a", "VehileInfo60d"),
            ("Vehicle60", 1, "obs_b", "VehileInfo60d"),
        ])
        with patch.object(v2, "EXPECTED_SLOTS", 2):
            return v2.build_artifact(source, mapping)

    def test_declaration_without_definition_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no definition in step"):
            self.build(
                b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
                b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_once;\r\n',
                prefix=b'real_T rtb_once;\r\n')

    def test_local_bound_unique_unconditional_prior_definition(self):
        artifact = self.build(
            b'  rtb_once = Exp1_MinModelTemp_P.Gain * Exp1_MinModelTemp_B.In1;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_once;\r\n')
        bound = artifact["slots"][1]["resolution"]
        self.assertEqual(bound["status"], "local_bound")
        self.assertEqual(bound["hop"]["local"], "rtb_once")
        self.assertIn("rtb_once =", bound["hop"]["definition_text"])

    def test_reused_temporary_is_unresolved(self):
        artifact = self.build(
            b'  rtb_twice = Exp1_MinModelTemp_P.A;\r\n'
            b'  rtb_twice = Exp1_MinModelTemp_P.B;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_twice;\r\n')
        self.assertEqual(artifact["slots"][1]["resolution"],
                         {"status": "unresolved", "reason": "reused_temporary"})

    def test_control_flow_scoped_definition_is_unresolved(self):
        artifact = self.build(
            b'  if (Exp1_MinModelTemp_B.sw) {\r\n'
            b'    rtb_scoped = Exp1_MinModelTemp_P.A;\r\n'
            b'  }\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_scoped;\r\n')
        self.assertEqual(artifact["slots"][1]["resolution"],
                         {"status": "unresolved", "reason": "control_flow_scoped"})

    def test_compound_and_call_are_unresolved(self):
        artifact = self.build(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = rtb_a * Exp1_MinModelTemp_P.G;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = std::asin(rtb_b);\r\n')
        self.assertEqual(artifact["slots"][0]["resolution"],
                         {"status": "unresolved", "reason": "compound_expression"})
        self.assertEqual(artifact["slots"][1]["resolution"],
                         {"status": "unresolved", "reason": "call_expression"})

    def test_indexed_local_is_unresolved(self):
        artifact = self.build(
            b'  rtb_arr[0] = Exp1_MinModelTemp_P.A;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_arr[0];\r\n')
        self.assertEqual(artifact["slots"][1]["resolution"],
                         {"status": "unresolved", "reason": "array_local"})

    def test_definition_after_use_fails_closed(self):
        source = fixture(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_late;\r\n'
            b'  rtb_late = Exp1_MinModelTemp_P.A;\r\n')
        mapping = mapping_for(source, [
            ("Vehicle60", 0, "obs_a", "VehileInfo60d"),
            ("Vehicle60", 1, "obs_b", "VehileInfo60d"),
        ])
        with patch.object(v2, "EXPECTED_SLOTS", 2):
            with self.assertRaisesRegex(ValueError, "defined after its use"):
                v2.build_artifact(source, mapping)

    def test_missing_definition_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no definition in step"):
            self.build(
                b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
                b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_ghost;\r\n')

    def test_commented_out_definition_is_not_counted(self):
        artifact = self.build(
            b'  /* rtb_com = Exp1_MinModelTemp_P.A; */\r\n'
            b'  // rtb_com = Exp1_MinModelTemp_P.B;\r\n'
            b'  rtb_com = Exp1_MinModelTemp_P.C;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_com;\r\n')
        bound = artifact["slots"][1]["resolution"]
        self.assertEqual(bound["status"], "local_bound")
        self.assertIn("P.C", bound["hop"]["definition_text"])

    def test_local_bound_terminal_definition_is_fully_resolved(self):
        artifact = self.build(
            b'  rtb_clean = Exp1_MinModelTemp_P.Gain;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_clean;\r\n')
        hop = artifact["slots"][1]["resolution"]["hop"]
        self.assertEqual(hop["definition_rhs"], "Exp1_MinModelTemp_P.Gain")
        self.assertEqual(hop["definition_references"],
                         [{"kind": "parameter", "path": "Exp1_MinModelTemp_P.Gain"}])
        self.assertEqual(hop["unresolved_dependency"], False)
        self.assertIsNone(hop["dependency_reason"])

    def test_local_bound_hop_flags_interior_local_dependency(self):
        artifact = self.build(
            b'  rtb_outer = Exp1_MinModelTemp_P.Gain * rtb_inner;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_outer;\r\n')
        hop = artifact["slots"][1]["resolution"]["hop"]
        self.assertEqual([r["kind"] for r in hop["definition_references"]],
                         ["parameter", "local"])
        self.assertEqual(hop["unresolved_dependency"], True)
        self.assertEqual(hop["dependency_reason"], "local_dependency")

    def test_local_bound_hop_flags_compound_terminal_definition(self):
        artifact = self.build(
            b'  rtb_mix = Exp1_MinModelTemp_P.Gain * Exp1_MinModelTemp_B.In1;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_mix;\r\n')
        hop = artifact["slots"][1]["resolution"]["hop"]
        self.assertEqual(hop["unresolved_dependency"], True)
        self.assertEqual(hop["dependency_reason"], "compound_expression")

    def test_single_local_with_constant_or_operator_is_compound_expression(self):
        artifact = self.build(
            b'  rtb_once = Exp1_MinModelTemp_P.Gain;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_once + 1.0;\r\n')
        self.assertEqual(artifact["slots"][1]["resolution"],
                         {"status": "unresolved", "reason": "compound_expression"})

    def test_local_bound_hop_flags_compound_definition_with_constant(self):
        artifact = self.build(
            b'  rtb_offset = Exp1_MinModelTemp_P.Gain + 1.0;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[1];\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = rtb_offset;\r\n')
        hop = artifact["slots"][1]["resolution"]["hop"]
        self.assertEqual(hop["unresolved_dependency"], True)
        self.assertEqual(hop["dependency_reason"], "compound_expression")

    def test_comparison_line_is_not_counted_as_definition(self):
        clean = [b'void MulticopterModelClass::step()', b'{',
                 b'  if (rtb_a == 5) {', b'  }',
                 b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = rtb_a;', b'}']
        self.assertEqual(v2._find_local_definitions(clean, 1, 6, 'rtb_a', 5), [])

    def test_multi_line_rhs_references(self):
        artifact = self.build(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[0] +\r\n'
            b'      Exp1_MinModelTemp_P.Offset;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = Exp1_MinModelTemp_B.Product[1];\r\n')
        slot0 = artifact["slots"][0]
        self.assertEqual(slot0["rhs"]["lines"], 2)
        self.assertEqual(sorted(r["kind"] for r in slot0["references"]),
                         ["block_output", "parameter"])
        # Two terminal references and no local/call: fully typed, hence terminal.
        self.assertEqual(slot0["resolution"], {"status": "terminal", "reason": None})

    def test_trailing_comment_on_write_is_stripped(self):
        artifact = self.build(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = Exp1_MinModelTemp_B.Product[0];  // motor0\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[1] = Exp1_MinModelTemp_B.Product[1];\r\n')
        slot0 = artifact["slots"][0]
        self.assertEqual(slot0["rhs"]["text"], "Exp1_MinModelTemp_B.Product[0]")
        self.assertEqual(slot0["resolution"], {"status": "terminal", "reason": None})

    def test_string_literal_brace_does_not_corrupt_step_span(self):
        src = (b'void MulticopterModelClass::step()\r\n{\r\n'
               b'  const char* s = "{{{";\r\n'
               b'  rtb_a = Exp1_MinModelTemp_P.G;\r\n'
               b'  Exp1_MinModelTemp_Y.VehileInfo60d[0] = rtb_a;\r\n'
               b'}\r\n')
        clean = v2._strip_comments(src.split(b"\n"))
        self.assertEqual(v2._step_span(clean), (1, 6))


class TestSchema(unittest.TestCase):
    def test_checked_in_artifact_matches_schema(self):
        from jsonschema import Draft202012Validator
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        artifact = json.loads(CHECKED_IN.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(artifact)), [])

    def test_duplicate_slot_rejected_by_schema(self):
        from jsonschema import Draft202012Validator
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        artifact = json.loads(CHECKED_IN.read_text(encoding="utf-8"))
        tampered = dict(artifact)
        tampered["slots"] = [*artifact["slots"][:-1], artifact["slots"][0]]
        errors = list(Draft202012Validator(schema).iter_errors(tampered))
        # Structural schema validation alone does not express the contract's
        # 56 distinct identities; the semantic validator owns that check.
        self.assertFalse(errors)
        with self.assertRaisesRegex(ValueError, "duplicate slot"):
            v2.validate_artifact_semantics(tampered,
                                           json.loads(V1_MAPPING.read_text(encoding="utf-8")))

    def _semantic_errors(self, mutate):
        import copy
        artifact = copy.deepcopy(json.loads(CHECKED_IN.read_text(encoding="utf-8")))
        mapping = json.loads(V1_MAPPING.read_text(encoding="utf-8"))
        mutate(artifact)
        return artifact, mapping

    def test_semantic_validator_rejects_copied_slot_with_changed_observable(self):
        artifact, mapping = self._semantic_errors(lambda a: None)
        artifact["slots"][1]["observable"] = "vehicle_time"
        with self.assertRaisesRegex(ValueError, "slot identities differ"):
            v2.validate_artifact_semantics(artifact, mapping)

    def test_semantic_validator_rejects_duplicate_array_index(self):
        artifact, mapping = self._semantic_errors(
            lambda a: a["slots"].__setitem__(1, dict(a["slots"][0])))
        artifact["slots"][1]["slot"] = artifact["slots"][0]["slot"]
        artifact["slots"][1]["array"] = artifact["slots"][0]["array"]
        artifact["slots"][1]["index"] = artifact["slots"][0]["index"]
        with self.assertRaisesRegex(ValueError, "duplicate slot or array/index"):
            v2.validate_artifact_semantics(artifact, mapping)

    def _schema_errors(self, mutate):
        import copy
        from jsonschema import Draft202012Validator
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        artifact = copy.deepcopy(json.loads(CHECKED_IN.read_text(encoding="utf-8")))
        mutate(artifact)
        return list(Draft202012Validator(schema).iter_errors(artifact))

    def test_generated_source_rejects_extra_field(self):
        def mutate(a):
            a["generated_source"]["attacker_field"] = "x"
        self.assertTrue(self._schema_errors(mutate))

    def test_generated_source_rejects_dropped_evidence(self):
        def mutate(a):
            a["generated_source"].pop("evidence")
        self.assertTrue(self._schema_errors(mutate))

    def test_generated_source_rejects_relocated_path(self):
        def mutate(a):
            a["generated_source"]["artifact_relative_path"] = "work/tampered.cpp"
        self.assertTrue(self._schema_errors(mutate))

    def test_slot_array_outport_mismatch_rejected(self):
        def mutate(a):
            slot = next(s for s in a["slots"] if s["array"] == "Vehicle60")
            slot["outport"] = "HILGPS30d"
        self.assertTrue(self._schema_errors(mutate))

    def test_slot_index_out_of_range_rejected(self):
        def mutate(a):
            slot = next(s for s in a["slots"] if s["array"] == "GPS30")
            slot["index"] = 59
        self.assertTrue(self._schema_errors(mutate))

    def test_slot_string_array_mismatch_rejected(self):
        def mutate(a):
            slot = next(s for s in a["slots"] if s["array"] == "Sensor30")
            slot["slot"] = "GPS30[{}]".format(slot["index"])
        self.assertTrue(self._schema_errors(mutate))

    def test_resolution_local_bound_requires_hop(self):
        def mutate(a):
            slot = next(s for s in a["slots"]
                        if s["resolution"]["status"] == "local_bound")
            slot["resolution"].pop("hop")
        self.assertTrue(self._schema_errors(mutate))

    def test_resolution_terminal_forbids_hop(self):
        hop = {"local": "rtb_x", "definition_line_range": [1, 1],
               "definition_text": "rtb_x = 1;", "definition_rhs": "1",
               "definition_references": [], "unresolved_dependency": False,
               "dependency_reason": None}
        def mutate(a):
            slot = next(s for s in a["slots"]
                        if s["resolution"]["status"] == "terminal")
            slot["resolution"]["hop"] = hop
        self.assertTrue(self._schema_errors(mutate))

    def test_resolution_unresolved_requires_a_reason(self):
        def mutate(a):
            slot = next(s for s in a["slots"]
                        if s["resolution"]["status"] == "unresolved")
            slot["resolution"]["reason"] = None
        self.assertTrue(self._schema_errors(mutate))

    def test_hop_unresolved_dependency_requires_a_reason(self):
        def mutate(a):
            slot = next(s for s in a["slots"]
                        if s["resolution"]["status"] == "local_bound")
            slot["resolution"]["hop"]["dependency_reason"] = None
        self.assertTrue(self._schema_errors(mutate))

    def test_reference_rejects_name_in_block_output(self):
        def mutate(a):
            slot = next(s for s in a["slots"] if any(r["kind"] == "block_output" for r in s["references"]))
            ref = next(r for r in slot["references"] if r["kind"] == "block_output")
            ref["name"] = "rogue"
        self.assertTrue(self._schema_errors(mutate))

    def test_reference_rejects_path_in_local(self):
        def mutate(a):
            slot = next(s for s in a["slots"] if any(r["kind"] == "local" for r in s["references"]))
            ref = next(r for r in slot["references"] if r["kind"] == "local")
            ref["path"] = "Exp1_MinModelTemp_B.x"
        self.assertTrue(self._schema_errors(mutate))

    def test_reference_rejects_indexed_in_call(self):
        def mutate(a):
            slot = next(s for s in a["slots"] if any(r["kind"] == "call" for r in s["references"]))
            ref = next(r for r in slot["references"] if r["kind"] == "call")
            ref["indexed"] = True
        self.assertTrue(self._schema_errors(mutate))

    def test_reference_kind_and_path_are_exactly_bound(self):
        def mutate(a):
            slot = next(s for s in a["slots"]
                        if any(r["kind"] == "block_output" for r in s["references"]))
            ref = next(r for r in slot["references"] if r["kind"] == "block_output")
            ref["kind"] = "state"
        self.assertTrue(self._schema_errors(mutate))

    def test_reference_timing_path_is_exact(self):
        def mutate(a):
            ref = a["slots"][0]["references"][0]
            ref["kind"] = "timing"
            ref["path"] = "Exp1_MinModelTemp_M->Timing.other[0]"
        self.assertTrue(self._schema_errors(mutate))


@unittest.skipUnless(REAL_SOURCE.is_file(), "private generated source not present")
class TestCheckedInArtifact(unittest.TestCase):
    def test_real_artifact_shape(self):
        artifact = json.loads(CHECKED_IN.read_text(encoding="utf-8"))
        self.assertEqual(artifact["slot_count"], 56)
        from collections import Counter
        counts = Counter((s["resolution"]["status"], s["resolution"]["reason"])
                         for s in artifact["slots"])
        self.assertEqual(counts, {("terminal", None): 26,
                                  ("local_bound", None): 2,
                                  ("unresolved", "reused_temporary"): 6,
                                  ("unresolved", "call_expression"): 2,
                                  ("unresolved", "compound_expression"): 20})
        s13 = next(s for s in artifact["slots"] if s["slot"] == "Sensor30[13]")
        self.assertEqual(s13["resolution"], {"status": "unresolved", "reason": "compound_expression"})
        bound = {s["slot"]: s["resolution"]["hop"]["local"]
                 for s in artifact["slots"] if s["resolution"]["status"] == "local_bound"}
        self.assertEqual(bound, {"Sensor30[0]": "rtb_time_usec",
                                 "GPS30[0]": "rtb_time_usec"})
        # The bound local's own definition references an interior unbound local;
        # the hop must say so explicitly rather than implying a complete closure.
        for s in artifact["slots"]:
            if s["resolution"]["status"] == "local_bound":
                hop = s["resolution"]["hop"]
                self.assertEqual(hop["unresolved_dependency"], True)
                self.assertEqual(hop["dependency_reason"], "local_dependency")
                self.assertIn("rtb_time_usec_tmp",
                              {r.get("name") for r in hop["definition_references"]})

    def test_checked_in_artifact_is_byte_reproducible(self):
        result = v2.check(CHECKED_IN)
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["slot_count"], v2.EXPECTED_SLOTS)

    def test_main_check_returns_zero(self):
        import io
        from contextlib import redirect_stdout
        captured = io.BytesIO()
        wrapper = io.TextIOWrapper(captured, encoding="utf-8")
        with redirect_stdout(wrapper):
            self.assertEqual(v2.main(["--check"]), 0)
        self.assertTrue(len(captured.getvalue()) > 0)

    def test_deterministic_derivation(self):
        self.assertEqual(v2.serialize(v2.derive()), CHECKED_IN.read_bytes())


class TestOutputGuards(unittest.TestCase):
    def test_serialize_rejects_non_finite_numbers(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                v2.serialize({"value": value})

    def test_create_only_refuses_existing_and_symlink(self):
        artifact = {"slot_count": 0}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.json"
            v2.write_artifact(artifact, output)
            with self.assertRaisesRegex(ValueError, "create-only"):
                v2.write_artifact(artifact, output)
            link = Path(directory) / "link.json"
            try:
                link.symlink_to(output)
            except OSError:
                self.skipTest("symlink privilege unavailable")
            with self.assertRaisesRegex(ValueError, "symlink"):
                v2.write_artifact(artifact, link)
            parent = Path(directory) / "real-parent"
            parent.mkdir()
            parent_link = Path(directory) / "parent-link"
            try:
                parent_link.symlink_to(parent, target_is_directory=True)
            except OSError:
                self.skipTest("symlink privilege unavailable")
            with self.assertRaisesRegex(ValueError, "parent"):
                v2.write_artifact(artifact, parent_link / "nested" / "out.json")
            leftovers = [p for p in Path(directory).iterdir()
                         if p.name.startswith("out.json.")]
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
