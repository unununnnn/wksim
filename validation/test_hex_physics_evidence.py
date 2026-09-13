"""Contract tests for the read-only Hex physics evidence audit."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.hex_physics_evidence import check
from tools import hex_physics
from Simulator.wksim_core import ap_json, px4_mavlink


MODEL_IDENTITY = "sha256:" + "a" * 64


def _px4_packet(controls=None, timestamp=1000, mode=128, flags=1):
    message = px4_mavlink.mavlink.MAVLink_hil_actuator_controls_message(
        timestamp, controls or [.1, .2, .3, .4, .5, .6] + [0.0] * 10, mode, flags)
    return message.pack(px4_mavlink.mavlink.MAVLink(None))


def _px4_case():
    controls = [.1, .2, .3, .4, .5, .6] + [0.0] * 10
    packet = _px4_packet(controls)
    decoded = px4_mavlink.mavlink.MAVLink(None).parse_buffer(packet)[0]
    normalized = hex_physics.actuator_commands(decoded)
    held = {"packet_hex": packet.hex(), "time_usec": 1000, "mode": 128, "flags": 1}
    start = {
        "kind": "start", "schema": "wksim.hex.physics.v1", "stack": "px4",
        "run_id": "hex-px4-03", "library": "/root/libwksim_hex_candidate.so",
        "library_sha256": "b" * 64, "model_identity": MODEL_IDENTITY, "dt_s": .001,
        "sources_sha256": {"tools/hex_physics.py": "c" * 64},
        "config": {"model_identity": MODEL_IDENTITY,
                   "profile": {"input_count": 16, "output_count": 120, "dt_s": .001}},
    }
    rows = [start, {"kind": "initialized", "initial_tick": 0}]
    for tick in (1, 2):
        rows.append({"kind": "step", "tick": tick, "group": 1, "group_steps": 2,
                     "substep": tick - 1, "input16": [0.0] * 16,
                     "output120": [0.0, 0.0, tick * .001] + [0.0] * 117,
                     "held_packet": None})
    rows.append({"kind": "actuator", **held})
    for tick in (3, 4):
        rows.append({"kind": "step", "tick": tick, "group": 2, "group_steps": 2,
                     "substep": tick - 3, "input16": normalized,
                     "output120": [0.0, 0.0, tick * .001] + [0.0] * 117,
                     "held_packet": held})
    rows.append({"kind": "end", "status": "completed"})
    return rows


def _ap_case():
    pwm = [1100, 1200, 1300, 1400, 1500, 1600] + [0] * 10
    packet = ap_json.SERVO_PACKET.pack(18458, 1000, 7, *pwm)
    normalized = hex_physics.decode_servos(packet)[3]
    held = {"packet_hex": packet.hex(), "frame": 7, "rate": 1000, "pwm16": pwm}
    start = {
        "kind": "start", "schema": "wksim.hex.physics.v1", "stack": "arducopter",
        "run_id": "hex-ap", "library": "/root/libwksim_hex_candidate.so",
        "library_sha256": "b" * 64, "model_identity": MODEL_IDENTITY, "dt_s": .001,
        "sources_sha256": {"tools/hex_physics.py": "c" * 64},
        "config": {"model_identity": MODEL_IDENTITY,
                   "profile": {"input_count": 16, "output_count": 120, "dt_s": .001}},
    }
    return [start, {"kind": "initialized", "initial_tick": 0},
            {"kind": "actuator", **held},
            {"kind": "step", "tick": 1, "group": 1, "group_steps": 1, "substep": 0,
             "input16": normalized, "output120": [0.0, 0.0, .001] + [0.0] * 117,
             "held_packet": held}, {"kind": "end", "status": "completed"}]


def _write_case(parent, rows):
    root = parent / "run"
    root.mkdir(parents=True)
    (root / "physics-1ms.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    return root


class HexPhysicsEvidenceTests(unittest.TestCase):
    def test_px4_real_shape_and_external_output_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = _write_case(parent, _px4_case())
            result = check(root, expected_run_id="hex-px4-03",
                           expected_model_identity=MODEL_IDENTITY,
                           output=parent / "audit.json")
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(result["counts"]["step"], 4)
            self.assertEqual(result["counts"]["groups"], 2)
            self.assertEqual(result["counts"]["held_packet_none_steps"], 2)
            self.assertEqual(json.loads((parent / "audit.json").read_text())["status"], "passed")

    def test_arducopter_decoder_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            result = check(_write_case(Path(directory), _ap_case()))
            self.assertTrue(result["passed"], result["errors"])

    def test_required_negative_records_are_rejected(self):
        mutations = {}
        rows = _px4_case()
        mutations["deleted_tick"] = rows[:2] + rows[3:]
        changed = copy.deepcopy(rows)
        changed[6]["input16"][0] = .9
        mutations["changed_input"] = changed
        changed_binding = copy.deepcopy(rows)
        changed_binding[0]["run_id"] = "wrong-run"
        mutations["changed_binding"] = changed_binding
        mutations["missing_terminal"] = rows[:-1]
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            for name, mutated in mutations.items():
                with self.subTest(name=name):
                    root = _write_case(parent / name, mutated)
                    result = check(root, expected_run_id="hex-px4-03",
                                   expected_model_identity=MODEL_IDENTITY)
                    self.assertFalse(result["passed"])
                    self.assertTrue(result["errors"], name)

    def test_output_inside_original_run_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _write_case(Path(directory), _px4_case())
            result = check(root, output=root / "audit.json")
            self.assertFalse(result["passed"])
            self.assertTrue(any(error["code"] == "output_write_failed" for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
