"""Deterministic fixtures only: no FC, GPS receiver, model, ROS or socket."""
from dataclasses import FrozenInstanceError, replace
import json
import unittest

from Simulator.wksim_core.gnss_event import GnssEventController, GnssEventPlan, GnssSample


def sample(tick, **changes):
    # Original current-adapter HIL_GPS order and integer wire units.
    value = GnssSample("run", "epoch1", 2, tick, tick,
                       (tick * 1000, 3, 473566000, 85430000, 488000,
                        100, 150, 0, 0, 0, 0, 0, 12))
    return replace(value, **changes)


def controller(**changes):
    args = dict(run_id="run", epoch="epoch1", vehicle_id=2, max_age_ticks=100,
                plan=GnssEventPlan("run", "epoch1", 2, 200, 400))
    args.update(changes)
    return GnssEventController(**args)


class GnssEventTests(unittest.TestCase):
    def test_exact_interval_and_fresh_recovery_preserve_original(self):
        control = controller()
        for tick, reason in ((199, "pass"), (200, "signal_loss"),
                             (399, "signal_loss"), (400, "pass"), (401, "pass")):
            with self.subTest(tick=tick):
                original = sample(tick)
                decision = control.decide(original, tick=tick)
                self.assertTrue(decision.accepted)
                self.assertEqual(decision.reason, reason)
                self.assertEqual(decision.outbound_gps, None if reason == "signal_loss" else original.gps)
                record = json.loads(json.dumps(decision.record(), allow_nan=False))
                self.assertEqual(record["sample"]["gps"], list(original.gps))
                self.assertEqual(record["sample"]["source_tick"], tick)
                self.assertEqual(record["tick"], tick)
                self.assertEqual(record["plan"]["end_tick"], 400)

    def test_same_sequence_is_deterministic_across_controllers(self):
        left, right = controller(), controller()
        inputs = ((sample(100), 100), (sample(200), 200), (sample(200), 200),
                  (sample(300), 399), (sample(400), 400))
        self.assertEqual([left.decide(s, tick=t).record() for s, t in inputs],
                         [right.decide(s, tick=t).record() for s, t in inputs])

    def test_invalid_fix_is_forwarded_without_rewriting_quality_or_time(self):
        control = controller()
        for tick in (100, 200, 400):
            original = sample(tick)
            original = replace(original, gps=(original.gps[0], 1, *original.gps[2:-1], 0))
            decision = control.decide(original, tick=tick)
            self.assertFalse(decision.source_fix_3d)
            self.assertEqual(decision.reason, "signal_loss" if tick == 200 else "invalid_fix")
            self.assertEqual(decision.outbound_gps, None if tick == 200 else original.gps)
            self.assertEqual(decision.sample, original)

    def test_stale_fix_never_becomes_valid_from_fresh_arrival_tick(self):
        control = controller(plan=None)
        self.assertEqual(control.decide(sample(100), tick=201).reason, "stale_source")
        # Even laundering only acquisition metadata cannot refresh original time.
        old_time = sample(300, gps=sample(100).gps)
        decision = control.decide(old_time, tick=300)
        self.assertEqual(decision.reason, "stale_source")
        self.assertIsNone(decision.outbound_gps)
        self.assertTrue(control.decide(sample(200), tick=200).accepted)

    def test_age_budget_inclusive_and_old_source_rejection(self):
        control = controller(plan=None)
        self.assertTrue(control.decide(sample(100), tick=200).accepted)
        for original in (sample(100), sample(101, sequence=100),
                         sample(101, gps=sample(100).gps)):
            decision = control.decide(original, tick=201)
            self.assertFalse(decision.accepted)
            self.assertEqual(decision.reason, "duplicate_or_old_source")
            self.assertIsNone(decision.outbound_gps)

    def test_outage_packet_cannot_be_replayed_at_recovery(self):
        control = controller()
        control.decide(sample(300), tick=300)
        decision = control.decide(sample(300), tick=400)
        self.assertEqual(decision.reason, "duplicate_or_old_source")
        self.assertFalse(decision.event_active)
        self.assertIsNone(decision.outbound_gps)
        self.assertEqual(control.decide(sample(400), tick=400).reason, "pass")

    def test_foreign_future_and_backward_inputs_do_not_poison_cursors(self):
        control = controller()
        control.decide(sample(100), tick=100)
        cases = [(sample(150, run_id="foreign"), 150, "foreign_identity"),
                 (sample(150, epoch="epoch2"), 150, "foreign_identity"),
                 (sample(150, vehicle_id=1), 150, "foreign_identity"),
                 (sample(151), 150, "future_source"),
                 (sample(150, gps=sample(151).gps), 150, "future_source"),
                 (sample(101), 99, "backward_tick")]
        for original, tick, reason in cases:
            with self.subTest(reason=reason, sample=original):
                decision = control.decide(original, tick=tick)
                self.assertEqual(decision.reason, reason)
                self.assertFalse(decision.accepted)
                self.assertIsNone(decision.outbound_gps)
                self.assertEqual(decision.record()["epoch"], "epoch1")
        self.assertEqual(control.decide(sample(101), tick=101).reason, "pass")

    def test_reset_clears_plan_and_samples_and_rejects_retired_epoch(self):
        control = controller()
        self.assertEqual(control.decide(sample(250), tick=250).reason, "signal_loss")
        control.reset("epoch2")
        self.assertEqual(control.decide(sample(251), tick=251).reason, "foreign_identity")
        fresh = sample(0, epoch="epoch2")
        self.assertEqual(control.decide(fresh, tick=0).reason, "pass")
        decision = control.decide(sample(250, epoch="epoch2"), tick=250)
        self.assertEqual(decision.reason, "pass")
        self.assertIsNone(decision.plan)
        for epoch in ("epoch1", "epoch2"):
            with self.assertRaises(ValueError):
                control.reset(epoch)
        control.reset("epoch3")
        control.schedule(GnssEventPlan("run", "epoch3", 2, 0, 10))
        self.assertEqual(control.decide(sample(0, epoch="epoch3"), tick=0).reason, "signal_loss")

    def test_reject_malformed_plans_and_late_duplicate_or_foreign_schedule(self):
        original = GnssEventPlan("run", "epoch1", 2, 200, 400)
        for changes in (dict(start_tick=True), dict(start_tick=-1), dict(end_tick=200),
                        dict(end_tick=2.5), dict(epoch=""), dict(vehicle_id=True)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(original, **changes)
        control = controller(plan=None)
        for plan in ("bad", replace(original, run_id="foreign"), replace(original, epoch="old")):
            with self.assertRaises(ValueError):
                control.schedule(plan)
        control.decide(sample(200), tick=200)
        with self.assertRaises(ValueError):
            control.schedule(original)
        control.schedule(replace(original, start_tick=201))
        with self.assertRaises(ValueError):
            control.schedule(replace(original, start_tick=500, end_tick=600))

    def test_malformed_samples_cannot_enter_controller(self):
        original = sample(100)
        for changes in (dict(sequence=True), dict(source_tick=-1), dict(vehicle_id=0),
                        dict(run_id="bad id"), dict(epoch=[]), dict(gps=list(original.gps)),
                        dict(gps=original.gps[:-1])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(original, **changes)
        for index, value in ((0, -1), (0, 2**64), (1, 9), (2, 900000001),
                             (3, -1800000001), (4, 2**31), (5, 65536),
                             (8, -32769), (11, 36000), (12, 256),
                             (6, float("nan")), (7, 0.0), (10, True)):
            gps = list(original.gps)
            gps[index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                replace(original, gps=tuple(gps))
        for budget in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                controller(max_age_ticks=budget)
        with self.assertRaises(ValueError):
            controller().decide({}, tick=100)
        with self.assertRaises(ValueError):
            controller().decide(original, tick=True)
        with self.assertRaises(FrozenInstanceError):
            original.source_tick = 200


if __name__ == "__main__":
    unittest.main()
