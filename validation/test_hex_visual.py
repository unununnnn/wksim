"""Pure Hex view boundary checks; these are not UE build/render evidence."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from Simulator.ue55.hex_bridge import (ANGLES, SPINS, LiveRawTail, LatestHex, actor_readback_errors,
                                      binding, display_packet, packet_from_record, validate)

EXPECTED = binding("hex-test-run", "a"*32, "sha256:"+"b"*64)


def record(tick=100, mono=1_000_000_000):
    output = [0.] * 120
    output[2] = tick / 1000
    output[6:9] = [1., 2., -3.]
    output[12:16] = [1., 0., 0., 0.]
    output[16:22] = [1000., 2000., 3000., 4000., 5000., 6000.]
    return dict(kind="step", tick=tick, output120=output, observed_monotonic_ns=mono)


def packet(tick=100, mono=1_000_000_000):
    source = packet_from_record(record(tick, mono), EXPECTED, mono+10_000_000)
    envelope = dict(packet=source, relay_monotonic_s=(mono+10_000_000)/1e9, ended=False)
    return display_packet(envelope, EXPECTED, .02, 100.)


def ack(state, previous=None):
    # Deliberately simple identity orientation fixture; geometry oracle uses trig.
    step = state["step"]
    prior = -1 if previous is None else previous["step"]
    entries = []
    for i, angle in enumerate(ANGLES):
        phase = 0. if previous is None else previous["rotors"][i]["phase_deg"] + state["rotor_rpm"][i]*6*(step-prior)/1000*SPINS[i]
        local = [22.5*math.cos(math.radians(angle)), 22.5*math.sin(math.radians(angle)), 10.]
        entries.append(dict(motor=f"M{i+1}", spin=SPINS[i], rpm=state["rotor_rpm"][i], yaw_deg=phase % 360,
                            phase_deg=phase, origin_local_cm=local, origin_world_cm=[local[0]+100, local[1]+200, local[2]+300],
                            mesh_extent_cm=[20., 1., .2], scale=[.45]*3,
                            mesh="/Game/Wksim/P450/SM_p450_cw.SM_p450_cw" if SPINS[i] > 0 else "/Game/Wksim/P450/SM_p450_ccw.SM_p450_ccw"))
    return dict(version=4, kind="hex_actor", **EXPECTED, vehicle_id=1, sequence=state["sequence"], step=step,
                previous_step=prior, sim_time_ns=state["sim_time_ns"], sim_time_s=state["sim_time_s"],
                ue_position_cm=[100., 200., 300.], ue_quaternion_xyzw=[0., 0., 0., 1.],
                geometry_offset_cm=[0, 0, 10], rotors=entries)


class HexVisualChecks(unittest.TestCase):
    def test_native_mapping_and_freshness(self):
        state = packet()
        self.assertEqual(len(state), 25)
        self.assertEqual(state["rotor_rpm"], [1000., 2000., 3000., 4000., 5000., 6000.])
        self.assertEqual(state["position_ned_m"], [1., 2., -3.])
        self.assertAlmostEqual(state["transport_age_bound_s"], .03)
        self.assertAlmostEqual(state["display_wall_time_s"], 99.97)
        source = packet_from_record(record(), EXPECTED, 1_010_000_000)
        for envelope, delay in [
            (dict(packet=source, relay_monotonic_s=1.01, ended=False), .76),
            (dict(packet=source, relay_monotonic_s=1.74, ended=False), .02),
            (dict(packet=source, relay_monotonic_s=.99, ended=False), .01),
        ]:
            with self.subTest(envelope=envelope, delay=delay), self.assertRaises(ValueError):
                display_packet(envelope, EXPECTED, delay, 100.)
        self.assertIsNone(display_packet(dict(packet=source, relay_monotonic_s=1.01, ended=True), EXPECTED, .02, 100.))

    def test_invalid_packets_do_not_advance_acceptance(self):
        initial, later = packet(), packet(120, 1_020_000_000)
        latest = LatestHex(EXPECTED)
        latest.accept(initial, now=100.)
        mutations = {"run_id": "foreign", "instance_id": "c"*32, "model_identity": "sha256:"+"c"*64,
                     "version": 3, "vehicle_id": True, "sequence": 99, "step": 100,
                     "sim_time_ns": 120000001, "sim_time_s": float("nan"), "source_monotonic_s": .99,
                     "source_age_s": -.01, "transport_age_bound_s": .76,
                     "display_wall_time_s": 99., "configuration": "quad-X", "position_frame": "ENU",
                     "rotor_order": ["M1"]*6, "position_ned_m": [True, 2., -3.],
                     "quaternion_wxyz": [2., 0., 0., 0.], "rotor_rpm": [1.]*4}
        for key, value in mutations.items():
            invalid = copy.deepcopy(later)
            invalid[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                latest.accept(invalid, now=100.)
            self.assertIs(latest.packet, initial)
        for invalid in [dict(later, extra=1), dict(later, display_wall_time_s=100.3), dict(later, rotor_rpm=[1.,2.,3.,4.,5.,"6"])]:
            with self.assertRaises(ValueError):
                latest.accept(invalid, now=100.)
            self.assertIs(latest.packet, initial)
        latest.accept(later, now=100.)
        with self.assertRaises(ValueError):
            latest.accept(later, now=100.)

    def test_six_rotor_geometry_and_unwrapped_phase(self):
        first, second = packet(), packet(120, 1_020_000_000)
        before, after = ack(first), ack(second, ack(first))
        errors = actor_readback_errors(second, after, before)
        self.assertTrue(all(value is not None and value < 1e-8 for value in errors.values()))
        self.assertEqual([r["phase_deg"] for r in after["rotors"]], [120., -240., 360., -480., -600., 720.])
        centres = [r["origin_local_cm"] for r in after["rotors"]]
        self.assertAlmostEqual(min(math.dist(a,b) for i,a in enumerate(centres) for b in centres[i+1:]), 22.5)
        after["rotors"][5]["phase_deg"] += 1
        self.assertAlmostEqual(actor_readback_errors(second, after, before)["phase_deg"], 1.)
        after["rotors"][5]["spin"] = -1
        with self.assertRaises(ValueError):
            actor_readback_errors(second, after, before)

    def test_raw_tail_only_new_complete_records_and_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"raw.jsonl"
            start = dict(kind="start", schema="wksim.hex.physics.v1", run_id=EXPECTED["run_id"], model_identity=EXPECTED["model_identity"])
            path.write_text(json.dumps(start)+"\n"+json.dumps(record())+"\n")
            tail = LiveRawTail(path, EXPECTED)
            self.assertIsNone(tail.poll(now_ns=1_010_000_000))  # Existing recent data still excluded.
            new = json.dumps(record(120, 1_020_000_000)).encode()
            with path.open("ab") as out:
                out.write(new[:100])
            self.assertIsNone(tail.poll(now_ns=1_030_000_000))
            with path.open("ab") as out:
                out.write(new[100:]+b"\n")
            self.assertEqual(tail.poll(now_ns=1_030_000_000)["step"], 120)
            self.assertIsNone(tail.poll(now_ns=1_030_000_000))
            with path.open("ab") as out:
                out.write((json.dumps(record(140, 1_040_000_000))+"\n"+json.dumps(dict(kind="end"))+"\n").encode())
            self.assertIsNone(tail.poll(now_ns=1_050_000_000))
            self.assertTrue(tail.ended)
            self.assertTrue(LiveRawTail(path, EXPECTED).ended)

    def test_raw_tail_binding_stale_and_file_lifetime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"raw.jsonl"
            tail = LiveRawTail(path, EXPECTED)
            self.assertIsNone(tail.poll(now_ns=1_010_000_000))
            start = dict(kind="start", schema="wksim.hex.physics.v1", run_id=EXPECTED["run_id"], model_identity=EXPECTED["model_identity"])
            path.write_text(json.dumps(start)+"\n"+json.dumps(record())+"\n")
            self.assertIsNone(tail.poll(now_ns=2_000_000_000))  # Expired native clock.
            self.assertIsNone(tail.poll(now_ns=1_010_000_000))  # No resend on a later request.
            path.write_text("")
            with self.assertRaises(ConnectionError):
                tail.poll(now_ns=2_000_000_000)
            path.write_text(json.dumps(dict(start, run_id="foreign"))+"\n")
            with self.assertRaises(ValueError):
                LiveRawTail(path, EXPECTED)

    def test_new_file_binding_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"raw.jsonl"
            tail = LiveRawTail(path, EXPECTED)
            start = dict(kind="start", schema="wksim.hex.physics.v1", run_id=EXPECTED["run_id"], model_identity=EXPECTED["model_identity"])
            path.write_text(json.dumps(start)+"\n"+json.dumps(record())+"\n")
            self.assertEqual(tail.poll(now_ns=1_010_000_000)["step"], 100)
            with path.open("a") as out:
                out.write(json.dumps(record())+"\n")
            with self.assertRaises(ValueError):
                tail.poll(now_ns=1_020_000_000)

    def test_raw_file_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"raw.jsonl"
            start = dict(kind="start", schema="wksim.hex.physics.v1", run_id=EXPECTED["run_id"], model_identity=EXPECTED["model_identity"])
            path.write_text(json.dumps(start)+"\n")
            tail = LiveRawTail(path, EXPECTED)
            replacement = Path(directory)/"replacement.jsonl"
            replacement.write_text(json.dumps(start)+"\n"+json.dumps(record())+"\n")
            replacement.replace(path)
            with self.assertRaises(ConnectionError):
                tail.poll(now_ns=1_010_000_000)


if __name__ == "__main__":
    unittest.main()
