"""Pure offline tests for the e0 source-to-slot manifest slice."""

import copy
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_e0_source_to_slot_manifest import (  # noqa: E402
    CURRENT_SLX_PATH,
    CURRENT_SLX_SHA256,
    DEFAULT_CONTRACT,
    FROZEN_CONTRACT_SHA256,
    MODEL_ARCHIVE_PATH,
    MODEL_ARCHIVE_SHA256,
    MODEL_MEMBER_PATH,
    MODEL_MEMBER_SHA256,
    build_manifest,
    dynamic_scalars,
    parse_cpp_line_ranges,
)
from tools import validate_e0_source_to_slot_manifest as validator  # noqa: E402


CONTRACT = ROOT / DEFAULT_CONTRACT
SCHEMA = ROOT / "docs/plan/59-e0-source-to-slot-manifest.schema.json"


class TestE0SourceToSlotManifest(unittest.TestCase):
    def _write_manifest(self, value, directory):
        path = Path(directory) / "manifest.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _sha256(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def _synthetic_validation(self, manifest, directory):
        """Write private-like fixtures and validate below an external root.

        The manifest retains the frozen logical paths. Only the expected bytes
        are replaced in this test fixture, and the validator's expected hashes
        are patched to the corresponding synthetic bytes. This keeps the unit
        suite independent of ignored vendor files while exercising the exact
        external-root resolution path.
        """
        artifact_root = Path(directory) / "artifact-root"
        archive_path = artifact_root / MODEL_ARCHIVE_PATH
        slx_path = artifact_root / CURRENT_SLX_PATH
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        slx_path.parent.mkdir(parents=True, exist_ok=True)
        member_bytes = b"synthetic Model 11.0 generated source\n"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(MODEL_MEMBER_PATH, member_bytes)
        slx_path.write_bytes(b"synthetic Model 11.8 SLX identity\n")
        archive_sha = self._sha256(archive_path)
        member_sha = hashlib.sha256(member_bytes).hexdigest()
        slx_sha = self._sha256(slx_path)

        model_source = manifest.get("model_source")
        if isinstance(model_source, dict):
            historical = model_source.get("historical_r1_cpp")
            archive = historical.get("archive") if isinstance(historical, dict) else None
            if isinstance(archive, dict):
                if archive.get("sha256") == MODEL_ARCHIVE_SHA256:
                    archive["sha256"] = archive_sha
                if archive.get("member_sha256") == MODEL_MEMBER_SHA256:
                    archive["member_sha256"] = member_sha
            current = model_source.get("current_slx_11_8")
            if isinstance(current, dict) and current.get("sha256") == CURRENT_SLX_SHA256:
                current["sha256"] = slx_sha

        path = self._write_manifest(manifest, directory)
        with patch.object(validator, "MODEL_ARCHIVE_SHA256", archive_sha), patch.object(
            validator, "MODEL_MEMBER_SHA256", member_sha
        ), patch.object(validator, "CURRENT_SLX_SHA256", slx_sha):
            return validator.validate_manifest(
                path,
                CONTRACT,
                SCHEMA,
                artifact_root=artifact_root,
            )

    def _validate(self, manifest, directory, contract=CONTRACT):
        """Validate one manifest using only temporary synthetic artifacts."""
        if contract != CONTRACT:
            path = self._write_manifest(manifest, directory)
            return validator.validate_manifest(
                path,
                contract,
                SCHEMA,
                artifact_root=Path(directory) / "missing-artifact-root",
            )
        return self._synthetic_validation(manifest, directory)

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
        self.assertEqual(manifest["model_source"]["historical_r1_cpp"]["status"], "bound")
        self.assertEqual(manifest["model_source"]["historical_r1_cpp"]["model_version"], "11.0")
        self.assertEqual(manifest["model_source"]["current_slx_11_8"]["status"], "unresolved")
        self.assertIsNone(manifest["model_source"]["current_slx_11_8"]["line_mapping"])
        for slot in manifest["slots"]:
            source = slot["source_mapping"]
            self.assertEqual(source["historical_r1_cpp"]["status"], "bound")
            self.assertEqual(source["historical_r1_cpp"]["line_ranges"], parse_cpp_line_ranges(source["raw"]))
            self.assertEqual(source["current_slx_11_8"], {"status": "unresolved", "line_ranges": None})

    def test_contract_dynamic_scalars_are_26_groups_and_56_scalars(self):
        with CONTRACT.open(encoding="utf-8") as stream:
            contract = json.load(stream)
        scalars = dynamic_scalars(contract)
        self.assertEqual(len(scalars), 56)
        self.assertEqual(len({observable["id"] for _, _, observable in scalars}), 26)

    def test_generated_manifest_validates(self):
        manifest = build_manifest(CONTRACT)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self._validate(manifest, directory), [])

    def test_missing_external_artifacts_fail_closed(self):
        manifest = build_manifest(CONTRACT)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            errors = validator.validate_manifest(
                path,
                CONTRACT,
                SCHEMA,
                artifact_root=Path(directory) / "missing-artifact-root",
            )
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("artifact-root file" in error for error in errors), errors)

    @unittest.skipUnless(
        (ROOT / MODEL_ARCHIVE_PATH).is_file() and (ROOT / CURRENT_SLX_PATH).is_file(),
        "private pinned model artifacts are not present",
    )
    def test_real_pinned_artifacts_validate_when_present(self):
        manifest = build_manifest(CONTRACT)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_manifest(manifest, directory)
            self.assertEqual(validator.validate_manifest(path, CONTRACT, SCHEMA), [])

    def test_frozen_archive_and_member_identity_are_pinned(self):
        manifest = build_manifest(CONTRACT)
        archive = manifest["model_source"]["historical_r1_cpp"]["archive"]
        self.assertEqual(archive["path"], MODEL_ARCHIVE_PATH.as_posix())
        self.assertEqual(archive["sha256"], MODEL_ARCHIVE_SHA256)
        self.assertEqual(archive["member"], MODEL_MEMBER_PATH)
        self.assertEqual(archive["member_sha256"], MODEL_MEMBER_SHA256)
        current = manifest["model_source"]["current_slx_11_8"]
        self.assertEqual(current["path"], CURRENT_SLX_PATH.as_posix())
        self.assertEqual(current["sha256"], CURRENT_SLX_SHA256)

    def test_archive_hash_drift_fails_closed(self):
        manifest = build_manifest(CONTRACT)
        manifest["model_source"]["historical_r1_cpp"]["archive"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
        self.assertTrue(any("archive.sha256 differs" in error for error in errors), errors)

    def test_member_path_and_hash_drift_fail_closed(self):
        for field, value, phrase in (
            ("member", "other.cpp", "archive.member differs"),
            ("member_sha256", "0" * 64, "archive.member_sha256 differs"),
            ("path", "validation/missing.zip", "archive.path differs"),
        ):
            with self.subTest(field=field):
                manifest = build_manifest(CONTRACT)
                manifest["model_source"]["historical_r1_cpp"]["archive"][field] = value
                with tempfile.TemporaryDirectory() as directory:
                    errors = self._validate(manifest, directory)
                self.assertTrue(any(phrase in error for error in errors), errors)

    def test_current_slx_mapping_stays_unresolved(self):
        manifest = build_manifest(CONTRACT)
        manifest["model_source"]["current_slx_11_8"]["line_mapping"] = [[1, 2]]
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
        self.assertTrue(any("line_mapping must remain null" in error for error in errors), errors)

    def test_current_unresolved_layer_prevents_complete_manifest(self):
        manifest = build_manifest(CONTRACT)
        manifest["status"] = "complete"
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
        self.assertTrue(any("manifest status should be 'unresolved'" in error for error in errors), errors)

    def test_line_ranges_must_match_raw_cpp_reference(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["source_mapping"]["historical_r1_cpp"]["line_ranges"] = [[1, 1]]
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
        self.assertTrue(any("line_ranges differ from raw" in error for error in errors), errors)

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
            errors = self._validate(manifest, directory)
        self.assertTrue(any("duplicate scalar" in error for error in errors), errors)
        self.assertTrue(any("coverage differs" in error for error in errors), errors)

    def test_budget_and_approval_fields_are_rejected_recursively(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["source_mapping"]["approval"] = "approved"
        manifest["slots"][0]["abs_budget"] = 0.0
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("forbidden budget/approval field" in error for error in errors), errors)

    def test_null_evidence_must_be_marked_unresolved(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["unresolved_fields"].remove("frame")
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
        self.assertTrue(any("null fields and unresolved_fields differ" in error for error in errors), errors)

    def test_malformed_source_mapping_is_rejected_without_crashing(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["source_mapping"] = None
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
        self.assertTrue(any("source_mapping: must be an object" in error for error in errors), errors)

    def test_json_schema_is_applied(self):
        manifest = build_manifest(CONTRACT)
        manifest["slots"][0]["frame"] = 42
        manifest["slots"][0]["unresolved_fields"].remove("frame")
        with tempfile.TemporaryDirectory() as directory:
            errors = self._validate(manifest, directory)
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
                    errors = self._validate(manifest, directory)
                self.assertTrue(errors)

    def test_adversarial_status_and_model_source_types_return_errors(self):
        mutations = (
            lambda manifest: manifest.update(status=[]),
            lambda manifest: manifest.update(model_source=None),
            lambda manifest: manifest["slots"][0].update(status=[]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                manifest = build_manifest(CONTRACT)
                mutate(manifest)
                with tempfile.TemporaryDirectory() as directory:
                    errors = self._validate(manifest, directory)
                self.assertTrue(errors)

    def test_malformed_semantic_status_is_rejected_without_type_error(self):
        with CONTRACT.open(encoding="utf-8") as stream:
            contract = json.load(stream)
        contract["observables"][0]["semantic_status"] = []
        with self.assertRaisesRegex(ValueError, "semantic_status"):
            dynamic_scalars(contract)

    def test_alternate_contract_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "contract.json"
            alternate.write_bytes(CONTRACT.read_bytes())
            with self.assertRaisesRegex(ValueError, "frozen canonical"):
                build_manifest(alternate)
            manifest = build_manifest(CONTRACT)
            errors = self._validate(manifest, directory, contract=alternate)
        self.assertTrue(any("frozen canonical" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
