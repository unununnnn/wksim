"""Deterministic unit tests for ContactObserver (#29 pure geometry slice)."""

from pathlib import Path
import unittest

from Simulator.wksim_core.static_contact import ContactError
from Simulator.wksim_runtime.contact_observer import (
    ContactObserver,
    DEFAULT_SCENE_PATH,
    FROZEN_SCENE_SHA256,
)

EPOCH = "e0f1a2b3c4d5e6f708192a3b4c5d6e7f"
FOREIGN_EPOCH = "11112222333344445555666677778888"


class ContactObserverTests(unittest.TestCase):
    def setUp(self):
        self.observer = ContactObserver(DEFAULT_SCENE_PATH, run_epoch=EPOCH)

    def test_init_valid(self):
        self.assertEqual(self.observer.epoch, EPOCH)
        self.assertEqual(self.observer.expected_sha256, FROZEN_SCENE_SHA256)
        self.assertEqual(self.observer.scene.scene_sha256, FROZEN_SCENE_SHA256)
        self.assertFalse(self.observer.frozen)
        self.assertIsNone(self.observer.freeze_reason)
        self.assertIsNone(self.observer.last_step)

    def test_init_invalid_epoch(self):
        for bad in ("", "short", "A" * 32, "g" * 32, 12345, None):
            with self.assertRaises(ContactError):
                ContactObserver(DEFAULT_SCENE_PATH, run_epoch=bad)

    def test_init_missing_scene_file(self):
        with self.assertRaises(ContactError) as ctx:
            ContactObserver(Path("non_existent_scene_file.json"), run_epoch=EPOCH)
        self.assertEqual(ctx.exception.reason, "scene_not_found")

    def test_init_hash_mismatch(self):
        bad_hash = "0" * 64
        with self.assertRaises(ContactError) as ctx:
            ContactObserver(DEFAULT_SCENE_PATH, run_epoch=EPOCH, expected_sha256=bad_hash)
        self.assertEqual(ctx.exception.reason, "scene_hash_mismatch")

    def test_observe_no_contact(self):
        res = self.observer.observe_step(step=1, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0])
        self.assertEqual(res["status"], "ok")
        self.assertFalse(res["freeze"])
        self.assertEqual(res["result"], "no_contact")
        self.assertIsNone(res["envelope"])
        self.assertIsNone(self.observer.last_envelope)
        self.assertEqual(self.observer.last_step, 1)
        self.assertFalse(self.observer.frozen)

    def test_observe_plane_contact(self):
        res = self.observer.observe_step(step=2, body_id="uav1", point_enu_m=[0.0, 0.0, -0.05])
        self.assertEqual(res["status"], "ok")
        self.assertFalse(res["freeze"])
        self.assertEqual(res["result"], "contact")
        env = res["envelope"]
        self.assertIsNotNone(env)
        self.assertEqual(env["schema"], "wksim.contact.v1")
        self.assertEqual(env["geometry_id"], "plane_z0")
        self.assertEqual(env["step"], 2)
        self.assertEqual(env["epoch"], EPOCH)
        self.assertAlmostEqual(env["penetration_m"], 0.05)
        self.assertEqual(env["normal_enu"], [0.0, 0.0, 1.0])

    def test_observe_box_contact(self):
        res = self.observer.observe_step(step=3, body_id="uav1", point_enu_m=[2.0, 0.0, 0.5])
        self.assertEqual(res["status"], "ok")
        self.assertFalse(res["freeze"])
        self.assertEqual(res["result"], "contact")
        env = res["envelope"]
        self.assertEqual(env["geometry_id"], "box_0")
        self.assertEqual(env["step"], 3)
        self.assertAlmostEqual(env["penetration_m"], 0.5)

    def test_foreign_epoch_triggers_freeze(self):
        res = self.observer.observe_step(step=4, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0], epoch=FOREIGN_EPOCH)
        self.assertEqual(res["status"], "freeze")
        self.assertTrue(res["freeze"])
        self.assertEqual(res["reason"], "foreign_epoch")
        self.assertEqual(res["freeze_step"], 4)
        self.assertTrue(self.observer.frozen)
        self.assertEqual(self.observer.freeze_reason, "foreign_epoch")

    def test_stale_step_triggers_freeze(self):
        res1 = self.observer.observe_step(step=10, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0])
        self.assertEqual(res1["status"], "ok")

        # Querying an earlier step (step 5 <= 10)
        res2 = self.observer.observe_step(step=5, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0])
        self.assertEqual(res2["status"], "freeze")
        self.assertTrue(res2["freeze"])
        self.assertEqual(res2["reason"], "stale_feedback")
        self.assertEqual(res2["freeze_step"], 5)
        self.assertTrue(self.observer.frozen)

    def test_frozen_observer_blocks_subsequent_steps(self):
        # Trigger freeze on step 10
        self.observer.observe_step(step=10, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0], epoch=FOREIGN_EPOCH)
        self.assertTrue(self.observer.frozen)

        # Subsequent step 11 must receive frozen response
        res = self.observer.observe_step(step=11, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0])
        self.assertEqual(res["status"], "frozen")
        self.assertTrue(res["freeze"])
        self.assertEqual(res["reason"], "foreign_epoch")
        self.assertEqual(res["freeze_step"], 10)
        self.assertEqual(res["step"], 11)
        self.assertIsNone(res["envelope"])

    def test_explicit_recovery(self):
        self.observer.observe_step(step=10, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0], epoch=FOREIGN_EPOCH)
        self.assertTrue(self.observer.frozen)

        rec = self.observer.recover(
            current_step=20, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0],
            reason="test_recovery")
        self.assertEqual(rec["status"], "recovered")
        self.assertFalse(rec["freeze"])
        self.assertEqual(rec["step"], 20)
        self.assertFalse(self.observer.frozen)
        self.assertIsNone(self.observer.freeze_reason)
        self.assertEqual(rec["result"], "no_contact")
        self.assertIsNone(rec["envelope"])

        # Fresh step 21 should now succeed
        res = self.observer.observe_step(step=21, body_id="uav1", point_enu_m=[0.0, 0.0, 5.0])
        self.assertEqual(res["status"], "ok")
        self.assertFalse(res["freeze"])

    def test_validate_envelope_stale_and_future(self):
        envelope = self.observer.scene.query(
            EPOCH, 15, "uav1", [0.0, 0.0, -0.01])["envelope"]

        # Valid on current_step=15
        v_ok = self.observer.validate_envelope(envelope, current_step=15)
        self.assertEqual(v_ok["status"], "ok")
        self.assertFalse(v_ok["freeze"])

        # Future check: current_step=10 < valid_from_step=15.
        future_observer = ContactObserver(DEFAULT_SCENE_PATH, run_epoch=EPOCH)
        v_fut = future_observer.validate_envelope(envelope, current_step=10)
        self.assertEqual(v_fut["status"], "freeze")
        self.assertEqual(v_fut["reason"], "future_feedback")
        self.assertTrue(future_observer.frozen)

        # Stale check: current_step=16 > valid_until_step=15
        stale_observer = ContactObserver(DEFAULT_SCENE_PATH, run_epoch=EPOCH)
        v_stale = stale_observer.validate_envelope(envelope, current_step=16)
        self.assertEqual(v_stale["status"], "freeze")
        self.assertEqual(v_stale["reason"], "stale_feedback")
        self.assertTrue(stale_observer.frozen)

    def test_validate_envelope_cannot_regress_last_step(self):
        self.observer.observe_step(100, "uav1", [0.0, 0.0, 5.0])
        old = self.observer.scene.query(
            EPOCH, 20, "uav1", [0.0, 0.0, -0.01])["envelope"]
        rejected = self.observer.validate_envelope(old, 20)
        self.assertEqual(rejected["reason"], "stale_feedback")
        self.assertEqual(self.observer.last_step, 100)

    def test_recovery_rejects_no_fault_and_backward_watermark(self):
        with self.assertRaises(ContactError) as no_fault:
            self.observer.recover(1, "uav1", [0.0, 0.0, 5.0])
        self.assertEqual(no_fault.exception.reason, "contact_invalid")
        self.observer.observe_step(10, "uav1", [0.0, 0.0, 5.0])
        self.observer.observe_step(5, "uav1", [0.0, 0.0, 5.0])
        with self.assertRaises(ContactError) as backward:
            self.observer.recover(10, "uav1", [0.0, 0.0, 5.0])
        self.assertEqual(backward.exception.reason, "stale_feedback")
        self.observer.recover(11, "uav1", [0.0, 0.0, 5.0])
        self.assertEqual(self.observer.last_step, 11)

    def test_external_envelope_requires_complete_exact_shape(self):
        envelope = self.observer.scene.query(
            EPOCH, 4, "uav1", [0.0, 0.0, -0.01])["envelope"]
        envelope["force"] = [0.0, 0.0, 1.0]
        rejected = self.observer.validate_envelope(envelope, 4)
        self.assertEqual(rejected["reason"], "contact_invalid")
        self.assertTrue(self.observer.frozen)

    def test_invalid_epoch_freezes_as_invalid(self):
        result = self.observer.observe_step(
            4, "uav1", [0.0, 0.0, 5.0], epoch="bad")
        self.assertEqual(result["reason"], "contact_invalid")
        self.assertEqual(self.observer.epoch, EPOCH)

    def test_display_manifest_binding(self):
        manifest = self.observer.get_display_manifest()
        self.assertEqual(manifest["schema"], "wksim.display-manifest.v1")
        self.assertEqual(manifest["scene_id"], "static-plane-box-v1")
        self.assertEqual(manifest["scene_hash"], FROZEN_SCENE_SHA256)
        self.assertEqual(manifest["coordinate_frame"], "ENU")
        self.assertEqual(manifest["unit"], "metre")
        self.assertEqual(manifest["plane"]["geometry_id"], "plane_z0")
        self.assertEqual(manifest["box"]["geometry_id"], "box_0")

    def test_no_physics_or_force_fields(self):
        res = self.observer.observe_step(step=50, body_id="uav1", point_enu_m=[2.0, 0.0, 0.5])
        env = res["envelope"]
        for forbidden in ("force", "contact_force", "impulse", "stiffness", "damping", "torque", "wrench"):
            self.assertNotIn(forbidden, res)
            self.assertNotIn(forbidden, env)


if __name__ == "__main__":
    unittest.main()
