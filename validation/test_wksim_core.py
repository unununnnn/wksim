"""Run: python3 -m unittest validation.test_wksim_core -v"""
import json
import math
import unittest

from Simulator.wksim_core.ap_json import Lockstep, SERVO_PACKET, decode_servos, sensor_message
from Simulator.wksim_core.model import Model, build_model
from Simulator.wksim_core.px4_mavlink import actuator_commands, gps_arguments
from pymavlink.dialects.v20 import common as mavlink


def packet(frame=0, rate=1000, pwm=None):
    return SERVO_PACKET.pack(18458, rate, frame, *(pwm or [1000] * 16))


class ProtocolTests(unittest.TestCase):
    def test_pwm_units_order_and_inactive(self):
        frame, rate, _, commands = decode_servos(packet(12, pwm=[1000, 1500, 2000, 0] + [1000] * 12))
        self.assertEqual(frame, 12)
        self.assertEqual(rate, 1000)
        self.assertEqual(commands, [0, 0.5, 1, 0] + [0] * 12)

    def test_reject_invalid_packet_rate_and_pwm(self):
        for value in [b"x", packet()[:-1], packet(rate=0), packet(pwm=[999] * 16),
                      b"\x00\x00" + packet()[2:]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_servos(value)

    def test_sensor_axes_units_and_quaternion_order(self):
        state = list(range(120))
        message = sensor_message(state)
        self.assertTrue(message.startswith(b"\n") and message.endswith(b"\n"))
        data = json.loads(message)
        self.assertEqual(data["imu"]["accel_body"], [61, 62, 63])
        self.assertEqual(data["imu"]["gyro"], [64, 65, 66])
        self.assertEqual(data["position"], [6, 7, 8])
        self.assertEqual(data["velocity"], [3, 4, 5])
        self.assertEqual(data["quaternion"], [12, 13, 14, 15])
        self.assertEqual(data["timestamp"], 2)

    def test_px4_disarmed_and_normalized_commands(self):
        message = mavlink.MAVLink_hil_actuator_controls_message(1000, [0.1, 0.2, 0.3, 0.4] + [float("nan")] * 12, 0, 1)
        self.assertEqual(actuator_commands(message), [0] * 16)
        message.mode = mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        self.assertEqual(actuator_commands(message), [0.1, 0.2, 0.3, 0.4] + [0] * 12)
        message.controls[0] = float("nan")
        with self.assertRaises(ValueError):
            actuator_commands(message)

    def test_px4_gps_wire_units_and_course_from_north(self):
        state = [0.0] * 120
        state[90:103] = [1e6, 401540302, 1162593683, 50000, 30, 40, 100, 100, 0, -20, 999, 3, 10]
        arguments = gps_arguments(state)
        self.assertEqual(arguments, (1000000, 3, 401540302, 1162593683, 50000, 30, 40, 100, 100, 0, -20, 0, 10))
        state[97], state[98] = 0, 100
        self.assertEqual(gps_arguments(state)[11], 9000)
        state[97], state[98] = 0, -100
        self.assertEqual(gps_arguments(state)[11], 27000)

    def test_px4_hil_wire_roundtrip(self):
        state = [0.0] * 120
        state[90:103] = [10000, 401540302, 1162593683, 50000, 30, 40, 0, 0, 0, 0, 0, 3, 10]
        encoder = mavlink.MAVLink(None)
        packet_bytes = mavlink.MAVLink_hil_gps_message(*gps_arguments(state)).pack(encoder)
        decoded = mavlink.MAVLink(None).parse_buffer(packet_bytes)[0]
        self.assertEqual(decoded.lat, 401540302)
        self.assertEqual(decoded.alt, 50000)
        self.assertEqual(decoded.time_usec, 10000)


class NativeModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = build_model()

    def test_idle_clock_specific_force_and_quaternion(self):
        with Model(self.library) as model:
            state = model.step([0] * 16, 1000)
            self.assertTrue(all(math.isfinite(value) for value in state))
            self.assertAlmostEqual(state[2], 1, places=8)
            self.assertEqual(state[6:9], [0, 0, 0])
            self.assertEqual(state[12:16], [1, 0, 0, 0])
            self.assertLess(abs(state[63] + 9.80665), 0.5)

    def test_power_response_and_repeatability(self):
        states = []
        for _ in range(2):
            with Model(self.library) as model:
                states.append(model.step([0.65] * 4 + [0] * 12, 1000))
        self.assertEqual(states[0], states[1])
        self.assertLess(states[0][8], -1.0)
        self.assertGreater(min(states[0][16:20]), 5000)

    def test_front_right_motor_effectiveness(self):
        with Model(self.library) as model:
            model.step([0.55] * 4 + [0] * 12, 1000)
            state = model.step([0.57, 0.55, 0.55, 0.55] + [0] * 12, 20)
        self.assertLess(state[27], 0)     # FR rotor produces negative roll.
        self.assertGreater(state[28], 0)  # Positive pitch.
        self.assertGreater(state[29], 0)  # CCW rotor reaction produces positive yaw.

    def test_input_validation_no_clock_advance(self):
        with Model(self.library) as model:
            for values in [[0] * 4, [float("nan")] * 16, [1.1] * 16]:
                with self.assertRaises(ValueError):
                    model.step(values)
            self.assertEqual(model.ticks, 0)
            model.close()
            with self.assertRaises(RuntimeError):
                model.step([0] * 16)

    def test_duplicate_replay_and_discontinuity(self):
        with Model(self.library) as model:
            loop = Lockstep(model)
            reply, advanced = loop.update(packet())
            self.assertTrue(advanced)
            repeated, advanced = loop.update(packet())
            self.assertFalse(advanced)
            self.assertEqual(reply, repeated)
            self.assertEqual(model.ticks, 1)
            loop.update(packet(1))
            with self.assertRaises(RuntimeError):
                loop.update(packet(3))
            self.assertEqual(model.ticks, 2)

    def test_startup_rate_hint_does_not_change_model_step(self):
        with Model(self.library) as model:
            loop = Lockstep(model)
            loop.update(packet(0, rate=1200))
            loop.update(packet(1, rate=999))
            self.assertAlmostEqual(loop.state[2], 0.002)


if __name__ == "__main__":
    unittest.main()
