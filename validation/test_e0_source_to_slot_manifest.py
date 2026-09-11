"""Pure offline tests for the e0 source-to-slot manifest slice."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_e0_source_to_slot_manifest import (  # noqa: E402
    DEFAULT_CONTRACT,
    FROZEN_CONTRACT_SHA256,
    build_manifest,
    dynamic_scalars,
)
from tools.validate_e0_source_to_slot_manifest import (  # noqa: E402
    validate_manifest,
)


CONTRACT = ROOT / DEFAULT_CONTRACT
SCHEMA = ROOT / "docs/plan/59-e0-source-to-slot-manifest.schema.json"


class TestE0SourceToSlotManifest(unittest.TestCase):
    def _write_manifest(self, value, directory):
        path = Path(directory) / "manifest.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_generator_expands_exact_dynamic_contract_coverage(self):
        manifest = build_manifest(CONTRACT)
        self.assertEqual(manifest["slot_count"], 56)
        keys = [(slot["array"], slot["index"]) for slot in manifest["slots"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 56)
        self.assertEqual(manifest["status"], "unresolved")
        self.assertTrue(all(slot["status"] == "unresolved" for slot in manifest["slots"]))
        self.assertTrue(all(slot["unit"] for slot in manifest["slots"]))
        self.assertTrue(all("hash" in slot and slot["hash"] is None for slot in manifest["slots"]))
        self.assertTrue(all("frame" in slot and slot["frame"] is None for slot in manifest["slots"]))

    def test_contract_dynamic_scalars_are_26_groups_and_56_scalars(self):
        with CONTRACT.open(encoding="utf-8") as stream:
            contract = json.load(stream)
        scalars = dynamic_scalars(contract)
        self.assertEqual(len(scalars), 56)
        self.assertEqual(len({observable["id"] for _, _, observable in scalars}), 26)

    def test_generated_manifest_validates(self):
        manifest = build_manifest(CONTRACT)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            self.assertEqual(validate_manifest(path, CONTRACT, SCHEMA), [])

    def test_checked_in_manifest_is_reproducible(self):
        checked_in = json.loads(
            (ROOT / "validation/e0-source-to-slot-manifest-20260911.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(checked_in, build_manifest(CONTRACT))
        self.assertEqual(checked_in["contract"]["sha256"], FROZEN_CONTRACT_SHA256)

    def test_duplicate_slot_is_rejected(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][1] = copy.deepcopy(manifest["slots"][0])
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            errors = validate_manifest(path, CONTRACT, SCHEMA)
        self.assertTrue(any("duplicate scalar" in error for error in errors), errors)
        self.assertTrue(any("coverage differs" in error for error in errors), errors)

    def test_budget_and_approval_fields_are_rejected_recursively(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["source_mapping"]["approval"] = "approved"
        manifest["slots"][0]["abs_budget"] = 0.0
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            errors = validate_manifest(path, CONTRACT, SCHEMA)
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("forbidden budget/approval field" in error for error in errors), errors)

    def test_null_evidence_must_be_marked_unresolved(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["unresolved_fields"].remove("frame")
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            errors = validate_manifest(path, CONTRACT, SCHEMA)
        self.assertTrue(any("null fields and unresolved_fields differ" in error for error in errors), errors)

    def test_malformed_source_mapping_is_rejected_without_crashing(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["source_mapping"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            errors = validate_manifest(path, CONTRACT, SCHEMA)
        self.assertTrue(any("source_mapping: must be an object" in error for error in errors), errors)

    def test_json_schema_is_applied(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["frame"] = 42
        manifest["slots"][0]["unresolved_fields"].remove("frame")
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            errors = validate_manifest(path, CONTRACT, SCHEMA)
        self.assertTrue(any("schema instance" in error and "frame" in error for error in errors), errors)

    def test_malformed_types_return_errors(self):
        mutations = (
            lambda slot: slot.update(array=[]),
            lambda slot: slot.update(unresolved_fields=[["frame"]]),
            lambda slot: slot["source_mapping"].update(path=7),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                manifest = build_manifest(CONTRACT)
                mutate(manifest["slots"][0])
                with tempfile.TemporaryDirectory() as directory:
                    path = self._write_manifest(manifest, directory)
                    errors = validate_manifest(path, CONTRACT, SCHEMA)
                self.assertTrue(errors)

    def test_alternate_contract_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "contract.json"
            alternate.write_bytes(CONTRACT.read_bytes())
            with self.assertRaisesRegex(ValueError, "frozen canonical"):
                build_manifest(alternate)
            manifest = build_manifest(CONTRACT)
            path = self._write_manifest(manifest, directory)
            errors = validate_manifest(path, alternate, SCHEMA)
        self.assertTrue(any("frozen canonical" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
