import json
import unittest

from Simulator.wksim_control.rc_input import MAX_AGE_NS, RCInput, RCError, SOURCE, validate_frame


IDENTITY = dict(run_id="rc-run", control_epoch="a" * 32, uav_id=1, boot_id="b" * 32)
GID = "01" * 16


def frame(stream="c" * 32, sequence=1, produced=1_000_000_000, channels=None):
    return dict(version=1, source=SOURCE, **IDENTITY, stream_id=stream, sequence=sequence,
                produced_monotonic_ns=produced,
                channels_us=list(channels or [1500, 1500, 1500, 1500, 1000, 1500, 1000, 1000]))


def active():
    rc = RCInput(IDENTITY)
    rc.bind(frame(), GID, now_ns=1_000_000_100)
    rc.activate(now_ns=1_000_000_200, position=(1., 2., .3), yaw=.4)
    return rc


class RCInputTests(unittest.TestCase):
    def test_strict_envelope_and_deadzone_endpoints(self):
        values = validate_frame(frame(channels=[1000, 1475, 1525, 2000, 1000, 1500, 1000, 1000]),
                                expected=IDENTITY, now_ns=1_000_000_001)
        self.assertEqual(values["normalized"], (-1., 0., 0., 1.))
        with self.assertRaises(RCError): validate_frame(json.dumps(frame())[:-1] + ',"x":1}')
        duplicate = '{"version":1,"version":1}'
        with self.assertRaises(RCError): validate_frame(duplicate)
        for channels in ([1500] * 7, [1500] * 9, [1500, 1500, 1500, 1500, 1001, 1500, 1000, 1000]):
            with self.assertRaises(RCError): validate_frame(frame(channels=channels))

    def test_switches_reboot_and_nonfinite_are_rejected(self):
        for channels in ([1500, 1500, 1500, 1500, 1000, 1400, 1000, 1000],
                         [1500, 1500, 1500, 1500, 1000, 1500, 1000, 1001],
                         [1000, 1000, 1000, 2000, 1000, 1500, 1000, 1000]):
            with self.assertRaises(RCError): validate_frame(frame(channels=channels))
        bad = frame(); bad["channels_us"][0] = True
        with self.assertRaises(RCError): validate_frame(bad)
        for key, value in (("sequence", True), ("produced_monotonic_ns", float("nan"))):
            bad = frame(); bad[key] = value
            with self.assertRaises(RCError): validate_frame(bad)

    def test_binding_requires_neutral_candidate_and_explicit_activation(self):
        rc = RCInput(IDENTITY)
        self.assertEqual(rc.bind(frame(channels=[1600, 1500, 1500, 1500, 1000, 1500, 1000, 1000]), GID,
                                 now_ns=1_000_000_100)["reason"], "bind_requires_neutral_candidate")
        self.assertEqual(rc.state, "UNBOUND")
        self.assertEqual(rc.bind(frame(), GID, now_ns=1_000_000_100)["state"], "CANDIDATE")
        self.assertIsNone(rc.step(now_ns=1_000_000_200))
        self.assertEqual(rc.activate(now_ns=1_000_000_200, position=(0., 0., .2), yaw=0.)["state"], "ACTIVE_RC")

    def test_world_frame_integral_zero_dt_and_height_floor(self):
        rc = active()
        rc.receive(frame(sequence=2, produced=1_010_000_000,
                         channels=[2000, 1000, 1000, 2000, 1000, 1500, 1000, 1000]), GID,
                   received_ns=1_010_000_100)
        first = rc.step(now_ns=1_010_000_100)
        self.assertEqual(first["dt_s"], 0.)
        rc.receive(frame(sequence=3, produced=1_030_000_000,
                         channels=[2000, 1000, 1000, 2000, 1000, 1500, 1000, 1000]), GID,
                   received_ns=1_030_000_100)
        value = rc.step(now_ns=1_030_000_100)
        self.assertAlmostEqual(value["position"][0], .97)
        self.assertAlmostEqual(value["position"][1], 1.97)
        self.assertAlmostEqual(value["position"][2], .274)
        self.assertAlmostEqual(value["yaw"], .37)
        rc.receive(frame(sequence=4, produced=1_040_000_000,
                         channels=[1500, 1500, 1500, 1500, 1000, 1500, 1000, 1000]), GID,
                   received_ns=1_040_000_100)
        self.assertAlmostEqual(rc.step(now_ns=1_040_000_100)["position"][2], .274)
        rc.target["position"] = (rc.target["position"][0], rc.target["position"][1], .21)
        rc.receive(frame(sequence=5, produced=1_050_000_000,
                         channels=[1500, 1500, 1000, 1500, 1000, 1500, 1000, 1000]), GID,
                   received_ns=1_050_000_100)
        self.assertEqual(rc.step(now_ns=1_050_000_100)["position"][2], .2)

    def test_sequence_stream_owner_and_stale_frames_do_not_refresh(self):
        rc = active()
        old_received = rc.received_ns
        self.assertEqual(rc.receive(frame(sequence=1), "02" * 16, received_ns=1_005_000_000)["reason"], "publisher_not_owner")
        self.assertEqual(rc.received_ns, old_received)
        self.assertEqual(rc.receive(frame(sequence=1), GID, received_ns=1_005_000_000)["reason"], "sequence_not_increasing")
        self.assertEqual(rc.state, "REVOKED")
        rc.reset()
        rc.bind(frame(stream="d" * 32), GID, now_ns=1_000_000_100)
        self.assertEqual(rc.receive(frame(stream="c" * 32), GID, received_ns=1_005_000_000)["reason"], "wrong_stream_id")
        self.assertEqual(rc.state, "REVOKED")

    def test_expiry_dt_pause_and_switch_revoke_without_output(self):
        self.assertIsNotNone(validate_frame(frame(), expected=IDENTITY,
                                            now_ns=1_000_000_000 + MAX_AGE_NS))
        with self.assertRaises(RCError):
            validate_frame(frame(), expected=IDENTITY, now_ns=1_000_000_000 + MAX_AGE_NS + 1)
        rc = active()
        rc.receive(frame(sequence=2, produced=1_010_000_000), GID, received_ns=1_010_000_100)
        self.assertIsNone(rc.step(now_ns=1_010_000_100, operation_mode="paused"))
        self.assertEqual(rc.state, "REVOKED")
        for channels, reason in (([1500, 1500, 1500, 1500, 1000, 1000, 1000, 1000], "channel_release"),
                                 ([1500, 1500, 1500, 1500, 1000, 2000, 1000, 1000], "command_intent_requires_explicit_handoff")):
            rc = active()
            rc.receive(frame(sequence=2, produced=1_010_000_000, channels=channels), GID, received_ns=1_010_000_100)
            self.assertIsNone(rc.step(now_ns=1_010_000_100))
            self.assertEqual(rc.last_rejection, reason)
        rc = active()
        rc.receive(frame(sequence=2, produced=1_010_000_000), GID, received_ns=1_010_000_100)
        self.assertIsNone(rc.step(now_ns=2_510_000_101))
        self.assertEqual(rc.last_rejection, "input_expired")
        self.assertEqual(rc.state, "REVOKED")

    def test_reset_retires_stream_and_requires_new_stream(self):
        rc = active()
        self.assertEqual(rc.revoke("test")["state"], "REVOKED")
        self.assertEqual(rc.reset()["state"], "UNBOUND")
        self.assertEqual(rc.bind(frame(), GID, now_ns=1_000_000_100)["reason"], "retired_stream")
        self.assertEqual(rc.bind(frame(stream="d" * 32), GID, now_ns=1_000_000_100)["state"], "CANDIDATE")


if __name__ == "__main__": unittest.main()
