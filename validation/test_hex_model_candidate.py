"""Pure contract/source checks. Does not compile or load native libraries."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hex_candidate", ROOT / "tools/build_hex_model_candidate.py")
hex_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hex_model)


class HexCandidateTests(unittest.TestCase):
    def test_named_configuration_roundtrip_is_immutable(self):
        config = hex_model.make_config("hex-test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            hex_model.write_json(config, path)
            self.assertEqual(hex_model.load_config(path), config)
            with self.assertRaises(FileExistsError):
                hex_model.write_json(config, path)
        self.assertNotEqual(config["model_identity"], hex_model.make_config()["model_identity"])
        for key in ["ModelParam_uavMass", "ModelParam_uavType", "ModelParam_rotorCt", "ModelParam_3DType"]:
            changed = copy.deepcopy(config)
            changed["parameters"][key]["value"] += 1
            with self.assertRaises(ValueError):
                hex_model.validate(changed)
        self.assertEqual(len(config["parameters"]), 22)
        self.assertEqual(config["parameters"]["ModelParam_uavJ"]["value"], [.0211, 0., 0., 0., .0219, 0., 0., 0., .0366])

    def test_untrusted_config_rejected(self):
        for value in [None, [], {}, {"name": "../bad"}, {"name": True}]:
            with self.assertRaises(ValueError):
                hex_model.validate(value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"name":"x","name":"y"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                hex_model.load_config(path)
        config = hex_model.make_config()
        config["parameters"]["ModelParam_uavMass"]["value"] = float("nan")
        with self.assertRaises(ValueError):
            hex_model.validate(config)

    def test_wrapper_checks_before_initialize_and_native_unused_guard(self):
        wrapper = hex_model.wrapper_source(hex_model.make_config()).decode()
        self.assertLess(wrapper.index("ModelParam_uavType == 5"), wrapper.index("model->initialize()"))
        self.assertLess(wrapper.index("ModelParam_uavMass == 1.515"), wrapper.index("model->initialize()"))
        self.assertIn("for (int i = 6; i < count; ++i) if (commands[i] != 0) return 1;", wrapper)
        self.assertIn("static bool used = false", wrapper)
        self.assertIn("wk_hex_parameter", wrapper)
        self.assertEqual(hex_model.sha((ROOT / "Simulator/wksim_core/model.cpp").read_bytes()), hex_model.WRAPPER_HASH)

    def test_protocol_signs_derived_from_source_geometry(self):
        protocol = hex_model.protocol()
        for angle, spin, expected in zip(hex_model.ANGLES, hex_model.SPINS, protocol["expected_acceleration_signs"]):
            import math
            moments = [-math.sin(math.radians(angle)), math.cos(math.radians(angle)), -spin]
            signs = [0 if abs(value) < 1e-10 else (1 if value > 0 else -1) for value in moments]
            self.assertEqual(signs, expected)
        self.assertEqual(protocol["config"]["geometry"]["unused_input_indices"], list(range(6, 16)))

    def test_invalid_input_before_native_call(self):
        model = hex_model.HexModel.__new__(hex_model.HexModel)
        model.handle = 123
        for channel in range(6, 16):
            commands = [0.] * 16
            commands[channel] = .01
            with self.assertRaises(ValueError):
                model.step(commands)
        for commands in [[0.] * 15, [0.] * 17, [float("nan")] + [0.] * 15,
                         [float("inf")] + [0.] * 15, [-.1] + [0.] * 15, [1.1] + [0.] * 15]:
            with self.assertRaises(ValueError):
                model.step(commands)
        with self.assertRaises(ValueError):
            model.step([0.] * 16, True)
        model.handle = None
        with self.assertRaisesRegex(ValueError, "closed"):
            model.step([0.] * 16)

    def test_wrong_build_config_and_library_rejected_without_load(self):
        config = hex_model.make_config()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hex_model.write_json({"config": hex_model.make_config("different")}, root / "build.json")
            with patch.object(hex_model.ctypes, "CDLL", side_effect=AssertionError("Must not load")):
                with self.assertRaisesRegex(ValueError, "identity"):
                    hex_model.HexModel(root / hex_model.LIBRARY, config)
            (root / "build.json").unlink()
            hex_model.write_json({"config": config, "files_sha256": {}}, root / "build.json")
            hex_model.write_json(config, root / "config.json")
            with self.assertRaisesRegex(ValueError, "manifest"):
                hex_model.verify_build(root / "wrong.so", config)

    def test_exact_private_archive_parameterization(self):
        archive = hex_model.ARCHIVE if hex_model.ARCHIVE.exists() else Path("E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip")
        if not archive.exists():
            self.skipTest("Pinned private source ZIP not present")
        self.assertEqual(hex_model.sha(archive.read_bytes()), hex_model.EXPECTED_HASH)
        with zipfile.ZipFile(archive) as zipped:
            raw = zipped.read("e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp")
        changed = hex_model.parameterize_source(raw, hex_model.make_config())
        self.assertEqual(len(raw), len(changed))
        self.assertEqual([(a, b) for a, b in zip(raw, changed) if a != b], [(ord("3"), ord("5"))])
        with self.assertRaisesRegex(ValueError, "hash"):
            hex_model.parameterize_source(raw + b"\n", hex_model.make_config())


if __name__ == "__main__":
    unittest.main()
