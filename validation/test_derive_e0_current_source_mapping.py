"""Pure offline tests for the e0 current-source mapping slice."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import derive_e0_current_source_mapping as derive_mod  # noqa: E402
from tools.derive_e0_current_source_mapping import (  # noqa: E402
    EVIDENCE_PATH,
    GENERATED_NAME,
    GENERATED_RELATIVE_PATH,
    GENERATED_SHA256,
    GENERATED_SIZE,
    build_artifact,
    load_checked_contract,
    load_evidence,
    load_private_source,
    parse_outport_writes,
    resolve_private_source,
    serialize,
)
from tools.generate_e0_source_to_slot_manifest import (  # noqa: E402
    DEFAULT_CONTRACT,
    dynamic_scalars,
    load_contract,
)

CONTRACT = ROOT / DEFAULT_CONTRACT
SCHEMA = ROOT / "docs/plan/59-e0-current-source-mapping.schema.json"
CHECKED_IN = ROOT / "validation/e0-current-source-mapping-20260912.json"
REAL_SOURCE = ROOT / GENERATED_RELATIVE_PATH


def fixture_cpp():
    """Synthetic ERT-style source: CRLF, non-UTF-8 comment, all 120 writes."""
    lines = [
        b'#include "Exp1_MinModelTemp.h"',
        b'// GBK comment bytes: \xd4\xd8\xb1\xbe',
        b'',
        b'void MulticopterModelClass::initialize()',
        b'{',
        b'}',
        b'',
        b'void MulticopterModelClass::step()',
        b'{',
        b"  // Outport: '<Root>/VehileInfo60d'",
    ]
    for index in range(33):
        if index == 5:
            lines += [b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +',
                      b'      rtb_b;']
        else:
            lines.append(b'  Exp1_MinModelTemp_Y.VehileInfo60d[%d] = rtb_v%d;' % (index, index))
    lines += [
        b'  std::memcpy(&Exp1_MinModelTemp_Y.VehileInfo60d[33],',
        b'              &Exp1_MinModelTemp_P.Constant_Value_ea[0], 27U * sizeof(real_T));',
    ]
    for index in range(15):
        lines.append(b'  Exp1_MinModelTemp_Y.HILSensor30d[%d] = rtb_s%d;' % (index, index))
    lines += [
        b'  std::memcpy(&Exp1_MinModelTemp_Y.HILSensor30d[15],',
        b'              &Exp1_MinModelTemp_P.Constant1_Value_i2[0], 15U * sizeof(real_T));',
    ]
    for index in range(13):
        lines.append(b'  Exp1_MinModelTemp_Y.HILGPS30d[%d] = rtb_g%d;' % (index, index))
    lines += [
        b'  std::memcpy(&Exp1_MinModelTemp_Y.HILGPS30d[13],',
        b'              &Exp1_MinModelTemp_P.Constant_Value_f3[0], 17U * sizeof(real_T));',
        b'}',
        b'',
    ]
    blob = b'\r\n'.join(lines)
    assert b'\r\n' in blob and b'\xd4\xd8' in blob
    return blob


class TestParseOutportWrites(unittest.TestCase):
    def test_fixture_full_coverage_and_kinds(self):
        coverage = parse_outport_writes(fixture_cpp())
        self.assertEqual(len(coverage), 120)
        for name, size in (("VehileInfo60d", 60), ("HILSensor30d", 30), ("HILGPS30d", 30)):
            for index in range(size):
                self.assertIn((name, index), coverage)
        self.assertEqual(coverage[("VehileInfo60d", 0)][2], "assignment")
        self.assertEqual(coverage[("VehileInfo60d", 59)][2], "memcpy")
        self.assertEqual(coverage[("HILSensor30d", 29)][2], "memcpy")
        self.assertEqual(coverage[("HILGPS30d", 13)][2], "memcpy")
        # The multi-line assignment spans exactly its two lines.
        start, end, kind = coverage[("VehileInfo60d", 5)]
        self.assertEqual((end - start, kind), (1, "assignment"))

    def test_missing_write_fails_closed(self):
        broken = fixture_cpp().replace(
            b'  Exp1_MinModelTemp_Y.HILGPS30d[7] = rtb_g7;\r\n', b'')
        with self.assertRaisesRegex(ValueError, "without a write"):
            parse_outport_writes(broken)

    def test_duplicate_write_fails_closed(self):
        broken = fixture_cpp().replace(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[4] = rtb_v4;',
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[4] = rtb_v4;\r\n'
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[4] = rtb_v4b;')
        with self.assertRaisesRegex(ValueError, "duplicate write"):
            parse_outport_writes(broken)

    def test_out_of_range_index_fails_closed(self):
        broken = fixture_cpp().replace(
            b'Exp1_MinModelTemp_Y.VehileInfo60d[32] = rtb_v32;',
            b'Exp1_MinModelTemp_Y.VehileInfo60d[60] = rtb_v32;')
        with self.assertRaisesRegex(ValueError, "out of range"):
            parse_outport_writes(broken)

    def test_write_outside_step_fails_closed(self):
        broken = fixture_cpp().replace(
            b'void MulticopterModelClass::initialize()\r\n{\r\n}',
            b'void MulticopterModelClass::initialize()\r\n{\r\n'
            b'  Exp1_MinModelTemp_Y.HILSensor30d[0] = rtb_init;\r\n}')
        with self.assertRaisesRegex(ValueError, "not enclosed"):
            parse_outport_writes(broken)

    def test_unexpected_outport_fails_closed(self):
        broken = fixture_cpp().replace(
            b'  std::memcpy(&Exp1_MinModelTemp_Y.VehileInfo60d[33],',
            b'  Exp1_MinModelTemp_Y.Other9d[0] = rtb_x;\r\n'
            b'  std::memcpy(&Exp1_MinModelTemp_Y.VehileInfo60d[33],')
        with self.assertRaisesRegex(ValueError, "unexpected root outport"):
            parse_outport_writes(broken)

    def test_memcpy_count_unparseable_fails_closed(self):
        broken = fixture_cpp().replace(
            b'27U * sizeof(real_T)', b'sizeof(rtb_buf)')
        with self.assertRaisesRegex(ValueError, "no parseable element count"):
            parse_outport_writes(broken)

    def test_missing_step_function_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "definition not found"):
            parse_outport_writes(b'void MulticopterModelClass::initialize()\r\n{\r\n}\r\n')

    def test_unterminated_statement_fails_closed(self):
        broken = fixture_cpp().replace(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b;',
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b')
        with self.assertRaisesRegex(ValueError, "never terminates"):
            parse_outport_writes(broken)

    def test_write_after_step_closing_brace_fails_closed(self):
        broken = fixture_cpp() + b'\r\nExp1_MinModelTemp_Y.HILSensor30d[0] = rtb_extra;\r\n'
        with self.assertRaisesRegex(ValueError, "not enclosed"):
            parse_outport_writes(broken)

    def test_write_before_step_opening_brace_fails_closed(self):
        broken = fixture_cpp().replace(
            b'void MulticopterModelClass::step()\r\n{\r\n',
            b'void MulticopterModelClass::step()\r\n'
            b'  Exp1_MinModelTemp_Y.HILSensor30d[0] = rtb_pre;\r\n{\r\n')
        with self.assertRaisesRegex(ValueError, "not enclosed"):
            parse_outport_writes(broken)

    def test_unterminated_assignment_swallowing_ordinary_statement_fails_closed(self):
        broken = fixture_cpp().replace(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b;',
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b\r\n  rtb_c = 1.0;')
        with self.assertRaisesRegex(ValueError, "never terminates"):
            parse_outport_writes(broken)

    def test_unterminated_assignment_swallowing_block_closure_fails_closed(self):
        broken = fixture_cpp().replace(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b;',
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b\r\n}')
        with self.assertRaisesRegex(ValueError, "never terminates"):
            parse_outport_writes(broken)

    def test_unterminated_assignment_swallowing_function_boundary_fails_closed(self):
        broken = fixture_cpp().replace(
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b;',
            b'  Exp1_MinModelTemp_Y.VehileInfo60d[5] = rtb_a +\r\n      rtb_b\r\n'
            b'void MulticopterModelClass::terminate()\r\n{\r\n  cleanup();\r\n}')
        with self.assertRaisesRegex(ValueError, "never terminates"):
            parse_outport_writes(broken)

    def test_unterminated_memcpy_swallowing_ordinary_statement_fails_closed(self):
        broken = fixture_cpp().replace(
            b'27U * sizeof(real_T));',
            b'27U * sizeof(real_T)\r\n  rtb_c = 1.0;')
        with self.assertRaisesRegex(ValueError, "never terminates"):
            parse_outport_writes(broken)


class TestBuildArtifact(unittest.TestCase):
    def test_fixture_artifact_ownership_and_ranges(self):
        with CONTRACT.open(encoding="utf-8") as stream:
            contract = json.load(stream)
        artifact = build_artifact(fixture_cpp(), contract)
        self.assertEqual(artifact["slot_count"], 56)
        self.assertEqual(artifact["derivation"]["covered_output_slots"], 120)
        expected = {(array, index): observable["id"]
                    for array, index, observable in dynamic_scalars(contract)}
        self.assertEqual({(slot["array"], slot["index"]): slot["observable"]
                          for slot in artifact["slots"]}, expected)
        by_slot = {slot["slot"]: slot for slot in artifact["slots"]}
        self.assertEqual(by_slot["Vehicle60[2]"]["observable"], "vehicle_time")
        self.assertEqual(by_slot["Vehicle60[2]"]["statement"], "assignment")
        start, end = by_slot["Vehicle60[5]"]["line_ranges"][0]
        self.assertEqual(end - start, 1)  # multi-line velocity write
        self.assertTrue(all(slot["statement"] == "assignment" for slot in artifact["slots"]))
        self.assertTrue(all(slot["line_ranges"][0][0] >= 1 for slot in artifact["slots"]))

    def test_checked_in_artifact_matches_schema(self):
        from jsonschema import Draft202012Validator
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        artifact = json.loads(CHECKED_IN.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(artifact))
        self.assertEqual(errors, [error.message for error in errors] and errors or [])
        self.assertEqual(errors, [])

    def test_duplicate_slot_rejected_by_schema(self):
        from jsonschema import Draft202012Validator
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        artifact = json.loads(CHECKED_IN.read_text(encoding="utf-8"))
        tampered = dict(artifact)
        tampered_slots = list(artifact["slots"])
        tampered_slots[-1] = dict(tampered_slots[0])
        tampered["slots"] = tampered_slots
        v = Draft202012Validator(schema)
        errors = list(v.iter_errors(tampered))
        self.assertTrue(any("non-unique" in e.message.lower() or "duplicate" in e.message.lower() or "uniqueitems" in str(e.schema).lower() for e in errors))


class TestIdentityAndPaths(unittest.TestCase):
    def test_real_codegen_evidence_crosscheck_passes(self):
        evidence = load_evidence(ROOT / EVIDENCE_PATH)
        self.assertEqual(evidence["total_files"], 4)

    def test_evidence_entry_drift_fails_closed(self):
        drifted = {"sources": [{"relative_path": "Exp1_MinModelTemp_ert_rtw\\" + GENERATED_NAME,
                                "sha256": "0" * 64, "size_bytes": GENERATED_SIZE,
                                "is_empty": False}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(drifted), encoding="utf-8")
            with patch.object(derive_mod, "EVIDENCE_SHA256",
                              hashlib.sha256(path.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, "SHA-256/size differs"):
                    load_evidence(path)

    def test_contract_must_be_canonical(self):
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "contract.json"
            alternate.write_bytes(CONTRACT.read_bytes())
            with self.assertRaisesRegex(ValueError, "frozen canonical"):
                load_checked_contract(alternate)

    def test_private_source_identity_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / GENERATED_RELATIVE_PATH
            fake.parent.mkdir(parents=True)
            fake.write_bytes(b"not the generated source")
            with self.assertRaisesRegex(ValueError, "size differs"):
                load_private_source(directory)

    def test_private_source_missing_fails_closed_with_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "artifact-root"):
                resolve_private_source(directory)

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for bad in ("../outside.cpp", "work/../../outside.cpp"):
                with self.subTest(bad=bad):
                    with self.assertRaisesRegex(ValueError, "escapes"):
                        resolve_private_source(directory, bad)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "real.cpp"
            target.write_bytes(b"x")
            link = Path(directory) / GENERATED_RELATIVE_PATH
            link.parent.mkdir(parents=True)
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Windows symlink privilege unavailable")
            with self.assertRaisesRegex(ValueError, "symlink"):
                resolve_private_source(directory)

    def test_real_source_matches_pins(self):
        if not REAL_SOURCE.is_file():
            self.skipTest("private generated source not present")
        data = load_private_source(ROOT)
        self.assertEqual(len(data), GENERATED_SIZE)
        self.assertEqual(hashlib.sha256(data).hexdigest(), GENERATED_SHA256)


@unittest.skipUnless(REAL_SOURCE.is_file(), "private generated source not present")
class TestCheckedInArtifact(unittest.TestCase):
    def test_checked_in_artifact_is_byte_reproducible(self):
        artifact = derive_mod.derive(DEFAULT_CONTRACT, EVIDENCE_PATH, ROOT)
        self.assertEqual(serialize(artifact), CHECKED_IN.read_bytes())

    def test_main_check_returns_zero(self):
        self.assertEqual(derive_mod.main(["--check"]), 0)


class TestMainEntry(unittest.TestCase):
    def test_check_without_private_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(derive_mod.main(["--check", "--artifact-root", directory]), 2)

    def test_derive_to_symlink_output_fails_closed(self):
        if not REAL_SOURCE.is_file():
            self.skipTest("private generated source not present")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = Path(directory) / "out.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Windows symlink privilege unavailable")
            self.assertEqual(derive_mod.main(["--output", str(link)]), 2)

    def test_check_result_path_is_posix(self):
        if not REAL_SOURCE.is_file():
            self.skipTest("private generated source not present")
        res = derive_mod.check(CHECKED_IN, DEFAULT_CONTRACT, EVIDENCE_PATH, ROOT)
        self.assertIn("/", res["artifact"])
        self.assertNotIn("\\", res["artifact"])


if __name__ == "__main__":
    unittest.main()
