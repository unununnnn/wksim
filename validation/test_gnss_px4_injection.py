"""Real MAVLink codec/socket boundary with synthetic states; NOT flight evidence."""
import copy
import json
import os
import socket
import unittest

from Simulator.wksim_core.gnss_event import GnssEventController, GnssEventPlan
from Simulator.wksim_core.px4_mavlink import (
    GnssSendGate, Sender, gps_arguments, mavlink, send_sensors, serve,
)


IDENTITY = ("run110", "epoch1", 2)


def state(tick, source_us=None, fix=3):
    value = [0.] * 120
    value[2] = tick * .001
    value[60] = tick * 1000
    value[74] = 8191
    value[90:103] = [tick * 1000 if source_us is None else source_us,
                     473566000, 85430000, 488000, 100, 150, 500,
                     300, 400, -20, 0, fix, 12]
    return value


class InjectionTests(unittest.TestCase):
    def setUp(self):
        self.tx, self.rx = socket.socketpair()
        self.addCleanup(self.tx.close)
        self.addCleanup(self.rx.close)
        self.rx.settimeout(.1)
        self.protocol = mavlink.MAVLink(Sender(self.tx), srcSystem=254, srcComponent=51)
        self.records = []
        self.control = GnssEventController(*IDENTITY, max_age_ticks=100)
        self.gate = GnssSendGate(self.control, self.record)

    def record(self, entry):
        self.records.append(copy.deepcopy(entry))
        if os.environ.get("WKSIM_GNSS_EVIDENCE"):
            print(json.dumps({"test": self.id(), **entry}, allow_nan=False))

    def messages(self):
        data = self.rx.recv(65536)
        return mavlink.MAVLink(None).parse_buffer(data)

    def send(self, tick, **kwargs):
        return send_sensors(self.protocol, state(tick, **kwargs), tick,
                            gnss_gate=self.gate, identity=IDENTITY)

    def test_exact_boundaries_real_wire_and_unchanged_truth_imu(self):
        self.control.schedule(GnssEventPlan(*IDENTITY, 200, 400))
        for tick in (199, 200, 399, 400, 401):
            original = state(tick)
            before = original.copy()
            # Direct gate tests non-cadence boundaries too, using real codec.
            result = self.gate.send(self.protocol, gps_arguments(original), tick=tick, identity=IDENTITY)
            self.assertEqual(original, before)
            self.assertEqual(result["success"], tick not in (200, 399))
            if result["success"]:
                message = self.messages()[0]
                self.assertEqual(bytes(message.get_msgbuf()).hex(), result["raw_frames_hex"][0])
                self.assertEqual(message.time_usec, tick * 1000)
                self.assertEqual(message.get_srcSystem(), 254)
                self.assertEqual(message.get_srcComponent(), 51)
            else:
                self.assertEqual(result["raw_frames_hex"], [])

    def test_duplicate_outage_and_recovery_keep_all_imu_frames(self):
        self.control.schedule(GnssEventPlan(*IDENTITY, 200, 400))
        for tick, expected in ((100, True), (100, False), (200, False), (300, False), (400, True)):
            self.send(tick)
            messages = self.messages()
            self.assertEqual([m.get_type() for m in messages],
                             ["HIL_SENSOR", "HIL_GPS"] if expected else ["HIL_SENSOR"])
            self.assertEqual(messages[0].time_usec, tick * 1000)
        self.assertEqual(self.records[3]["decision"]["reason"], "signal_loss")

    def test_disabled_gate_retains_old_duplicate_semantics(self):
        for tick in (4, 100, 100):
            original = state(tick)
            send_sensors(self.protocol, original, tick)
            messages = self.messages()
            self.assertEqual(len(messages), 1 if tick == 4 else 2)
            if tick == 100:
                expected = mavlink.MAVLink(None).hil_gps_encode(*gps_arguments(original))
                self.assertEqual(messages[1].to_dict(), expected.to_dict())

    def test_no_plan_preserves_all_thirteen_fields_including_invalid_fix(self):
        result = self.send(100, source_us=99999, fix=1)
        gps = self.messages()[1]
        expected = mavlink.MAVLink(None).hil_gps_encode(*gps_arguments(state(100, 99999, 1)))
        self.assertEqual(gps.to_dict(), expected.to_dict())
        self.assertEqual(result["decision"]["reason"], "invalid_fix")
        self.assertEqual(result["original_gps"][0], 99999)
        self.assertEqual(result["decision"]["sample"]["source_tick"], 100)
        self.assertEqual(self.records[0]["raw_frames_hex"], [])
        self.assertFalse(self.records[0]["success"])

    def test_age_budget_exact_and_stale_source_not_restamped(self):
        result = self.send(200, source_us=100000)
        self.assertTrue(result["success"])
        self.assertEqual(self.messages()[1].time_usec, 100000)
        result = self.send(400, source_us=299999)
        self.assertFalse(result["attempted"])
        self.assertEqual(result["decision"]["reason"], "stale_source")
        self.assertEqual(len(self.messages()), 1)

    def test_foreign_and_future_dont_poison_next_candidate(self):
        for identity in (("foreign", "epoch1", 2), ("run110", "old", 2), ("run110", "epoch1", 1)):
            result = self.gate.send(self.protocol, gps_arguments(state(100)), tick=100, identity=identity)
            self.assertEqual(result["decision"]["reason"], "foreign_identity")
        result = self.send(100, source_us=100001)
        self.assertEqual(result["decision"]["reason"], "future_source")
        self.assertEqual(len(self.messages()), 1)
        self.assertTrue(self.send(100)["success"])
        self.assertEqual(len(self.messages()), 2)

    def test_outage_source_cannot_replay_after_recovery(self):
        self.control.schedule(GnssEventPlan(*IDENTITY, 200, 400))
        self.send(300)
        self.messages()
        result = self.send(400, source_us=300000)
        self.assertEqual(result["decision"]["reason"], "duplicate_or_old_source")
        self.assertEqual(len(self.messages()), 1)
        self.assertTrue(self.send(400)["success"])
        self.messages()

    def test_new_epoch_rejects_old_and_requires_new_plan(self):
        self.control.schedule(GnssEventPlan(*IDENTITY, 200, 400))
        self.send(200)
        self.messages()
        self.control.reset("epoch2")
        self.assertEqual(self.send(100)["decision"]["reason"], "foreign_identity")
        self.messages()
        result = self.gate.send(self.protocol, gps_arguments(state(0)), tick=0,
                                identity=("run110", "epoch2", 2))
        self.assertTrue(result["success"])
        self.assertIsNone(result["decision"]["plan"])
        self.messages()

    def test_socket_error_records_raw_attempt_and_propagates_without_retry(self):
        self.tx.close()
        with self.assertRaises(OSError):
            self.gate.send(self.protocol, gps_arguments(state(100)), tick=100, identity=IDENTITY)
        result = self.records[-1]
        self.assertTrue(result["attempted"])
        self.assertFalse(result["success"])
        self.assertEqual(len(result["raw_frames_hex"]), 1)
        self.assertIsNotNone(result["error"])
        self.assertIsNone(self.protocol.file.capture)
        result = self.gate.send(self.protocol, gps_arguments(state(100)), tick=100, identity=IDENTITY)
        self.assertFalse(result["attempted"])

    def test_malformed_input_recorded_before_send(self):
        gps = list(gps_arguments(state(100)))
        gps[1] = 9
        with self.assertRaises(ValueError):
            self.gate.send(self.protocol, tuple(gps), tick=100, identity=IDENTITY)
        self.assertFalse(self.records[-1]["attempted"])
        self.assertEqual(self.records[-1]["original_gps"][1], 9)
        self.assertEqual(self.records[-1]["raw_frames_hex"], [])

    def test_runtime_binding_checked_before_opening_resources(self):
        with self.assertRaisesRegex(ValueError, "explicit runtime"):
            serve("missing.so", 0, "must-not-create", gnss_gate=self.gate,
                  run_id="foreign", gnss_epoch="epoch1", vehicle_id=2)

    def test_recorder_failure_prevents_unlogged_send(self):
        def fail(entry):
            raise RuntimeError("evidence unavailable")
        gate = GnssSendGate(self.control, fail)
        with self.assertRaisesRegex(RuntimeError, "evidence unavailable"):
            gate.send(self.protocol, gps_arguments(state(100)), tick=100, identity=IDENTITY)
        self.assertIsNone(self.protocol.file.capture)
        self.assertEqual(self.protocol.total_packets_sent, 0)


if __name__ == "__main__":
    unittest.main()
