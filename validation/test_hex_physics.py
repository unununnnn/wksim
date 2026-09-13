"""Pure packet/loop fixtures. No network, native model or FC processes."""
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import hex_physics as hex
from tools.hex_launch_plan import launch_plan
from tools.build_hex_model_candidate import make_config
from Simulator.wksim_core import ap_json as ap, px4_mavlink as px4


def servo(frame=0, pwm=None, magic=18458, rate=1000):
    return ap.SERVO_PACKET.pack(magic, rate, frame, *(pwm or [1100, 1200, 1300, 1400, 1500, 1600] + [0] * 10))


def hil(timestamp, controls=None, mode=128, flags=1):
    message = px4.mavlink.MAVLink_hil_actuator_controls_message(
        timestamp, controls if controls is not None else [.1, .2, .3, .4, .5, .6] + [0.] * 10, mode, flags)
    return message.pack(px4.mavlink.MAVLink(None))


def parsed(packet):
    return px4.mavlink.MAVLink(None).parse_buffer(packet)[0]


class Model:
    instances = []

    def __init__(self, *args):
        self.ticks, self.inputs = 0, []
        self.instances.append(self)

    def step(self, inputs, steps=1):
        self.ticks += steps
        self.inputs.append((list(inputs), steps))
        state = [0.] * 120
        state[2], state[12], state[60] = self.ticks * .001, 1., self.ticks * 1000.
        return state

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Connection:
    def __init__(self, packets):
        self.packets, self.sent = iter(packets), []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def bind(self, *args):
        pass

    def listen(self, *args):
        pass

    def settimeout(self, *args):
        pass

    def setsockopt(self, *args):
        pass

    def accept(self):
        return self, ("127.0.0.1", 12345)

    def recv(self, *args):
        return next(self.packets, b"")

    def recvfrom(self, *args):
        return next(self.packets)

    def sendall(self, packet):
        self.sent.append(packet)

    def sendto(self, packet, address):
        self.sent.append((packet, address))


class HexPhysicsTests(unittest.TestCase):
    def test_ap_original_four_and_hex_six_wire_semantics(self):
        packet = servo(pwm=[0, 1000, 1500, 2000, 1250, 1750] + [65535] * 10)
        self.assertEqual(ap.decode_servos(packet)[3], [0., 0., .5, 1.] + [0.] * 12)
        frame, rate, raw, normalized = hex.decode_servos(packet)
        self.assertEqual((frame, rate, raw[4:6]), (0, 1000, [1250, 1750]))
        self.assertEqual(normalized, [0., 0., .5, 1., .25, .75] + [0.] * 10)
        for channel in range(6):
            for invalid in (1, 999, 2001, 65535):
                values = [1000] * 16
                values[channel] = invalid
                with self.assertRaises(ValueError):
                    hex.decode_servos(servo(pwm=values))
        for invalid in (b"", servo()[:-1], servo() + b"x", servo(magic=0), servo(rate=0)):
            with self.assertRaises(ValueError):
                hex.decode_servos(invalid)

    def test_ap_original_lockstep_replay_wrap_and_rejection(self):
        model, stream = Model(), io.StringIO()
        original = ap.decode_servos
        with hex.bind(ap, Model, hex.Recorder(stream)):
            loop = ap.Lockstep(model)
            first, advanced = loop.update(servo(2**32 - 1))
            self.assertTrue(advanced)
            self.assertEqual(loop.update(servo(2**32 - 1)), (first, False))
            self.assertTrue(loop.update(servo(0))[1])
            for frame in (2, 2**32 - 1):
                with self.assertRaisesRegex(RuntimeError, "discontinuity"):
                    loop.update(servo(frame))
            self.assertEqual((model.ticks, loop.duplicates), (2, 1))
            self.assertEqual(model.inputs[0][0][4:6], [.5, .6])
        self.assertIs(ap.decode_servos, original)

    def test_ap_original_serve_rejects_changed_peer(self):
        peer, foreign = ("127.0.0.1", 10), ("127.0.0.1", 11)
        connection = Connection([(servo(0), peer), (servo(1), foreign), (servo(1), peer)])
        recorder = hex.Recorder(io.StringIO())
        with tempfile.TemporaryDirectory() as directory, hex.bind(ap, Model, recorder), \
                patch.object(ap.socket, "socket", return_value=connection):
            result = ap.serve("unused", 19002, Path(directory) / "trace", duration=.002)
        self.assertEqual(result["frames"], 2)
        self.assertEqual(len(connection.sent), 2)
        self.assertEqual(len(recorder.stream.getvalue().splitlines()), 2)

    def test_px4_actual_mavlink_wire_six_inputs_and_original_four(self):
        packet = hil(100, [0., .125, .25, .5, .75, 1.] + [float("nan")] * 10)
        message = parsed(packet)
        self.assertEqual(bytes(message.get_msgbuf()), packet)
        self.assertEqual(px4.actuator_commands(message), [0., .125, .25, .5] + [0.] * 12)
        self.assertEqual(hex.actuator_commands(message), [0., .125, .25, .5, .75, 1.] + [0.] * 10)
        for channel in range(6):
            for invalid in (-.01, 1.01, float("nan"), float("inf")):
                values = [0.] * 16
                values[channel] = invalid
                with self.assertRaises(ValueError):
                    hex.actuator_commands(parsed(hil(1, values)))
        self.assertEqual(hex.actuator_commands(parsed(hil(1, [float("nan")] * 16, mode=0))), [0.] * 16)
        message.controls = [0.] * 5
        with self.assertRaisesRegex(ValueError, "16 channels"):
            hex.actuator_commands(message)
        broken = bytearray(packet)
        broken[-1] ^= 1
        with self.assertRaises(px4.mavlink.MAVError):
            parsed(broken)

    def run_px4_loop(self, packets, duration=.012):
        connection, stream = Connection(packets), io.StringIO()
        with tempfile.TemporaryDirectory() as directory, hex.bind(px4, Model, hex.Recorder(stream)), \
                patch.object(px4.socket, "socket", return_value=connection), patch.object(px4.time, "sleep"):
            result = px4.serve("unused", 4581, Path(directory) / "trace", duration=duration, speedup=1)
        return result, Model.instances[-1], [json.loads(line) for line in stream.getvalue().splitlines()]

    def test_px4_original_replay_and_four_substep_hold(self):
        first = hil(4000)
        result, model, packets = self.run_px4_loop([first[:9], first[9:], hil(4000), hil(8000), hil(12000)])
        self.assertEqual((result["frames"], result["duplicates"], model.ticks), (3, 1, 12))
        self.assertEqual(model.inputs[0], ([0.] * 16, 4))
        self.assertEqual(model.inputs[1][0][4:6], list(parsed(first).controls[4:6]))
        self.assertEqual([packet["time_usec"] for packet in packets], [4000, 8000, 12000])
        self.assertEqual(packets[0]["packet_hex"], first.hex())

    def test_px4_original_clock_flags_and_disconnect_fail_closed(self):
        for packets, error, message in (([hil(4000), hil(3999)], RuntimeError, "backwards"),
                                        ([hil(4000, flags=0)], RuntimeError, "lockstep"),
                                        ([hil(4000), b""], ConnectionError, "closed")):
            original = px4.actuator_commands
            with self.assertRaisesRegex(error, message):
                self.run_px4_loop(packets)
            self.assertIs(px4.actuator_commands, original)

    def test_px4_original_timeout_never_free_runs_after_actuators(self):
        with patch.object(px4.time, "monotonic", side_effect=[0, 0, 0, 0, 0, 0, 6]):
            with self.assertRaisesRegex(TimeoutError, "actuator timeout"):
                self.run_px4_loop([hil(4000)])
        self.assertEqual(Model.instances[-1].ticks, 8)

    def test_observer_records_each_held_ms_without_native(self):
        recorder = hex.Recorder(io.StringIO())
        cls = hex.observed_model(make_config(), recorder)
        model = cls.__new__(cls)
        model.ticks, model.inputs = 0, []
        recorder.actuator(b"fixture", time_usec=4000)
        with patch.object(hex.HexModel, "step", Model.step):
            output = model.step([.5] * 6 + [0.] * 10, 4)
            for invalid in (0, 1001, True, 1.5):
                with self.assertRaises(ValueError):
                    model.step([0.] * 16, invalid)
        steps = [r for r in map(json.loads, recorder.stream.getvalue().splitlines()) if r["kind"] == "step"]
        self.assertEqual([r["tick"] for r in steps], [1, 2, 3, 4])
        self.assertEqual([r["substep"] for r in steps], [0, 1, 2, 3])
        self.assertTrue(all(r["input16"] == [.5] * 6 + [0.] * 10 and len(r["output120"]) == 120 for r in steps))
        self.assertTrue(all(r["held_packet"]["packet_hex"] == b"fixture".hex() for r in steps))
        self.assertEqual(output[2], .004)

    def test_runtime_wrong_candidate_rejected_before_any_native_load(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "wrong.so"
            library.write_bytes(b"not a model")
            with patch.object(hex, "load_config", return_value=make_config()), \
                    patch.object(hex, "verify_build", return_value=library), \
                    patch.object(hex, "observed_model", side_effect=AssertionError("must not load")):
                with self.assertRaisesRegex(ValueError, "candidate identity"):
                    hex.serve("px4", library, "unused", 4581, "unused", Path(directory) / "raw")
            self.assertFalse((Path(directory) / "raw").exists())

    def test_static_plan_exact_six_geometry_and_custom_startup(self):
        plan = launch_plan()
        self.assertEqual(plan["ap_parameters"]["FRAME_CLASS"], 2)
        self.assertEqual(plan["ap_parameters"]["FRAME_TYPE"], 1)
        self.assertEqual([plan["ap_parameters"][f"SERVO{i}_FUNCTION"] for i in range(1, 7)], list(range(33, 39)))
        params = plan["px4_parameters"]
        self.assertEqual((params["CA_ROTOR_COUNT"], params["MAV_TYPE"]), (6, 13))
        for i, spin in enumerate((1, -1, 1, -1, -1, 1)):
            self.assertAlmostEqual(math.hypot(params[f"CA_ROTOR{i}_PX"], params[f"CA_ROTOR{i}_PY"]), .225)
            self.assertEqual(params[f"CA_ROTOR{i}_KM"], -spin * 2.783e-7 / 1.681e-5)
            self.assertEqual(params[f"CA_ROTOR{i}_CT"], 6.5)
        self.assertEqual([params[f"PWM_MAIN_FUNC{i}"] for i in range(1, 17)], list(range(101, 107)) + [0] * 10)
        self.assertEqual(plan["px4_environment"]["PX4_SYS_AUTOSTART"], "10016")
        self.assertEqual(plan["model_identity"], hex.MODEL_IDENTITY)


if __name__ == "__main__":
    unittest.main()
