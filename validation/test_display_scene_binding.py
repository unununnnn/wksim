"""Pure offline tests for the #29 display-scene binding slice.

These tests bind existing display-manifest, contact, planner, and terrain
identities.  They do not start UE, ROS, FC, native, MATLAB, or a build, and
they do not treat a passing result as #29 acceptance.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from Simulator.wksim_planning.scene_profile import EGO_SINGLE_BOX_V1, PROFILE_ID
from Simulator.wksim_runtime.contact_observer import CONTACT_FIELDS, FROZEN_SCENE_SHA256
from Simulator.wksim_runtime.display_scene_binding import (
    AUTHORITY_TEXT,
    BINDING_SCHEMA,
    BINDING_SOURCE_IDENTITY,
    CONTACT_SCHEMA,
    DISPLAY_MANIFEST_SCHEMA,
    DISPLAY_SCENE_HASH,
    DISPLAY_SCENE_ID,
    FRAME_EVIDENCE_SCHEMA,
    FRAME_SCHEMA,
    PROBE_SCENE_HASH,
    PROBE_SCENE_ID,
    RETAINED_BOUNDARY_STEP,
    RETAINED_FREEZE_FRAME,
    RETAINED_LIVE_EPOCH,
    RETAINED_RECOVER_FRAME,
    FREEZE_REASONS,
    DisplaySceneBinding,
    DisplaySceneBindingError,
    DisplaySceneIdentityError,
    retained_offline_frame_evidence,
)
from Simulator.wksim_runtime.planner_scene_binding import (
    EGO_SINGLE_BOX_BINDING,
    EXPECTED_SCENE_HASH,
)
from Simulator.wksim_runtime.terrain_feedback import STACK_BODIES


ROOT = Path(__file__).resolve().parents[1]
RETAINED_DISPLAY_MANIFEST = ROOT / "validation/lunar-29-live-contact/display-manifest.json"
EPOCH = "e0f1a2b3c4d5e6f708192a3b4c5d6e7f"
FOREIGN_EPOCH = "11112222333344445555666677778888"


class DisplayManifestBindingTests(unittest.TestCase):
    def setUp(self):
        self.binding = DisplaySceneBinding(EPOCH)

    def test_observer_and_retained_manifests_share_the_frozen_fixture(self):
        observer_manifest = self.binding.display_manifest()
        retained_manifest = self.binding.retained_manifest()
        self.assertEqual(observer_manifest["schema"], DISPLAY_MANIFEST_SCHEMA)
        self.assertEqual(retained_manifest["schema"], DISPLAY_MANIFEST_SCHEMA)
        self.assertEqual(observer_manifest["scene_id"], DISPLAY_SCENE_ID)
        self.assertEqual(retained_manifest["scene_id"], DISPLAY_SCENE_ID)
        self.assertEqual(observer_manifest["scene_hash"], FROZEN_SCENE_SHA256)
        self.assertEqual(retained_manifest["scene_hash"], DISPLAY_SCENE_HASH)
        self.assertEqual(observer_manifest["coordinate_frame"], "ENU")
        self.assertEqual(observer_manifest["unit"], "metre")
        self.assertEqual(observer_manifest["plane"]["geometry_id"], "plane_z0")
        self.assertEqual(observer_manifest["box"]["center_enu_m"], [2.0, 0.0, 0.5])
        self.assertEqual(retained_manifest["authority"], AUTHORITY_TEXT)
        self.assertEqual(self.binding.validate_manifest(observer_manifest), observer_manifest)
        self.assertEqual(self.binding.validate_manifest(retained_manifest), retained_manifest)

    def test_retained_on_disk_manifest_is_accepted_and_not_mutated(self):
        loaded = self.binding.load_manifest(RETAINED_DISPLAY_MANIFEST)
        on_disk = json.loads(RETAINED_DISPLAY_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(loaded, on_disk)
        self.assertEqual(loaded["scene_hash"], DISPLAY_SCENE_HASH)
        self.assertNotEqual(loaded["scene_hash"], EXPECTED_SCENE_HASH)
        self.assertNotEqual(loaded["scene_hash"], PROBE_SCENE_HASH)

    def test_planner_and_probe_identities_are_rejected_as_display(self):
        retained = self.binding.retained_manifest()
        substitutions = (
            ("scene_id", PROFILE_ID),
            ("scene_hash", EXPECTED_SCENE_HASH),
            ("scene_id", PROBE_SCENE_ID),
            ("scene_hash", PROBE_SCENE_HASH),
        )
        for key, value in substitutions:
            with self.subTest(key=key, value=value):
                invalid = deepcopy(retained)
                invalid[key] = value
                with self.assertRaises(DisplaySceneIdentityError):
                    self.binding.validate_manifest(invalid)

    def test_manifest_frame_unit_extra_field_and_force_fail_closed(self):
        retained = self.binding.retained_manifest()
        for key, value in (("coordinate_frame", "NED"), ("unit", "cm"), ("schema", "other")):
            invalid = deepcopy(retained)
            invalid[key] = value
            with self.subTest(field=key), self.assertRaises(DisplaySceneBindingError):
                self.binding.validate_manifest(invalid)
        extra = deepcopy(retained)
        extra["force"] = [0.0, 0.0, 1.0]
        with self.assertRaises(DisplaySceneBindingError):
            self.binding.validate_manifest(extra)
        extra = deepcopy(retained)
        extra["unexpected"] = True
        with self.assertRaises(DisplaySceneBindingError):
            self.binding.validate_manifest(extra)


class ContactAndFrameConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.binding = DisplaySceneBinding(EPOCH)

    def test_observe_frame_binds_contact_step_to_the_display_frame(self):
        record = self.binding.observe_frame(7, "uav1", [0.0, 0.0, -0.05])
        self.assertEqual(record["schema"], FRAME_SCHEMA)
        self.assertEqual(record["result"], "contact")
        self.assertEqual(record["frame"], 7)
        envelope = record["envelope"]
        self.assertEqual(set(envelope), CONTACT_FIELDS)
        self.assertEqual(envelope["schema"], CONTACT_SCHEMA)
        self.assertEqual(envelope["scene_hash"], DISPLAY_SCENE_HASH)
        self.assertEqual(envelope["step"], 7)
        self.assertEqual(envelope["valid_from_step"], 7)
        self.assertEqual(envelope["valid_until_step"], 7)
        self.assertEqual(envelope["sim_time_ns"], 7_000_000)
        for field in ("force", "impulse", "stiffness", "damping"):
            self.assertNotIn(field, envelope)

    def test_observe_no_contact_then_foreign_epoch_freeze_and_recover(self):
        free = self.binding.observe_frame(1, "uav1", [0.0, 0.0, 5.0])
        self.assertEqual(free["result"], "no_contact")
        self.assertIsNone(free["envelope"])

        frozen = self.binding.observe_frame(2, "uav1", [0.0, 0.0, 5.0], epoch=FOREIGN_EPOCH)
        self.assertEqual(frozen["result"], "frozen")
        self.assertIsNone(frozen["envelope"])
        self.assertTrue(self.binding.observer.frozen)

        consumed = self.binding.consume_frame(frozen)
        self.assertEqual(consumed["result"], "frozen")

        recovered = self.binding.recover_frame(10, "uav1", [2.0, 0.0, 5.0], reason="test_recovery")
        self.assertEqual(recovered["result"], "no_contact")
        self.assertEqual(recovered["frame"], 10)
        self.assertFalse(self.binding.observer.frozen)

    def test_freeze_reason_frame_and_recovery_epoch_remain_bound(self):
        frozen = self.binding.observe_frame(1, "uav1", "not-a-point")
        self.assertEqual(frozen["result"], "frozen")
        self.assertEqual(self.binding.observer.freeze_reason, "invalid_geometry")
        self.assertIn("invalid_geometry", FREEZE_REASONS)

        later = deepcopy(frozen)
        later["frame"] = 10_000
        with self.assertRaises(DisplaySceneBindingError):
            self.binding.consume_frame(later)
        with self.assertRaises(DisplaySceneIdentityError):
            self.binding.recover_frame(
                2,
                "uav1",
                [0.0, 0.0, 5.0],
                epoch=FOREIGN_EPOCH,
            )

    def test_external_contact_envelope_is_consumed_once_and_rejects_forces(self):
        envelope = self.binding.observer.scene.query(
            EPOCH, 15, "uav1", [2.0, 0.0, 0.5])["envelope"]
        accepted = self.binding.consume_contact(envelope, 15)
        self.assertEqual(accepted["status"], "ok")
        self.assertFalse(accepted["freeze"])

        stale = self.binding.consume_contact(envelope, 15)
        self.assertEqual(stale["status"], "freeze")
        self.assertEqual(stale["reason"], "stale_feedback")

        other = DisplaySceneBinding(EPOCH)
        forced = deepcopy(envelope)
        forced["force"] = [0.0, 0.0, 1.0]
        with self.assertRaises(DisplaySceneBindingError):
            other.consume_contact(forced, 15)

        planner_like = deepcopy(envelope)
        planner_like["schema"] = "wksim.planner-contact.v1"
        with self.assertRaises(DisplaySceneIdentityError):
            DisplaySceneBinding(EPOCH).consume_contact(planner_like, 15)

    def test_consume_frame_rejects_identity_and_state_mismatches(self):
        envelope = self.binding.observer.scene.query(
            EPOCH, 4, "uav1", [0.0, 0.0, -0.01])["envelope"]
        live = {
            "schema": FRAME_SCHEMA,
            "scene_id": DISPLAY_SCENE_ID,
            "scene_hash": DISPLAY_SCENE_HASH,
            "epoch": EPOCH,
            "frame": 4,
            "result": "contact",
            "envelope": envelope,
        }
        self.assertEqual(self.binding.consume_frame(live)["frame"], 4)

        probe = deepcopy(live)
        probe["scene_hash"] = PROBE_SCENE_HASH
        probe["frame"] = 5
        with self.assertRaises(DisplaySceneIdentityError):
            DisplaySceneBinding(EPOCH).consume_frame(probe)

        planner = deepcopy(live)
        planner["scene_id"] = PROFILE_ID
        planner["scene_hash"] = EXPECTED_SCENE_HASH
        planner["frame"] = 5
        with self.assertRaises(DisplaySceneIdentityError):
            DisplaySceneBinding(EPOCH).consume_frame(planner)

        claimed_freeze = {
            "schema": FRAME_SCHEMA,
            "scene_id": DISPLAY_SCENE_ID,
            "scene_hash": DISPLAY_SCENE_HASH,
            "epoch": EPOCH,
            "frame": 20,
            "result": "frozen",
            "envelope": None,
        }
        fresh = DisplaySceneBinding(EPOCH)
        with self.assertRaises(DisplaySceneBindingError):
            fresh.consume_frame(claimed_freeze)

        fresh.observe_frame(1, "uav1", [0.0, 0.0, 5.0], epoch=FOREIGN_EPOCH)
        live_while_frozen = {
            "schema": FRAME_SCHEMA,
            "scene_id": DISPLAY_SCENE_ID,
            "scene_hash": DISPLAY_SCENE_HASH,
            "epoch": EPOCH,
            "frame": 2,
            "result": "no_contact",
            "envelope": None,
        }
        with self.assertRaises(DisplaySceneBindingError):
            fresh.consume_frame(live_while_frozen)

    def test_frame_step_time_must_be_identical(self):
        envelope = self.binding.observer.scene.query(
            EPOCH, 8, "uav1", [0.0, 0.0, -0.01])["envelope"]
        mismatched = {
            "schema": FRAME_SCHEMA,
            "scene_id": DISPLAY_SCENE_ID,
            "scene_hash": DISPLAY_SCENE_HASH,
            "epoch": EPOCH,
            "frame": 9,
            "result": "contact",
            "envelope": envelope,
        }
        with self.assertRaises(DisplaySceneBindingError):
            self.binding.consume_frame(mismatched)


class FrameEvidenceAndIdentityTests(unittest.TestCase):
    def setUp(self):
        self.binding = DisplaySceneBinding(RETAINED_LIVE_EPOCH)

    def test_retained_offline_freeze_recover_evidence_is_accepted(self):
        evidence = retained_offline_frame_evidence()
        accepted = self.binding.validate_frame_evidence(evidence)
        self.assertEqual(accepted["schema"], FRAME_EVIDENCE_SCHEMA)
        self.assertEqual(accepted["epoch"], RETAINED_LIVE_EPOCH)
        self.assertEqual(accepted["events"][0]["frame"], RETAINED_FREEZE_FRAME)
        self.assertEqual(accepted["events"][0]["boundary_step"], RETAINED_BOUNDARY_STEP)
        self.assertEqual(accepted["events"][1]["frame"], RETAINED_RECOVER_FRAME)
        self.assertIs(accepted["ue_session"], False)
        self.assertIs(accepted["acceptance"], False)
        self.assertIs(accepted["display_modifies_physics"], False)

        recorded_events = json.loads(
            (ROOT / "validation/lunar-29-live-contact/events.json").read_text(encoding="utf-8")
        )
        run_config = json.loads(
            (ROOT / "validation/lunar-29-live-contact/run-config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(accepted["events"], recorded_events)
        self.assertEqual(accepted["epoch"], run_config["epoch"])

    def test_frame_evidence_cannot_claim_ue_or_acceptance_or_reorder_events(self):
        evidence = retained_offline_frame_evidence()
        for key in ("ue_session", "ue_disconnect_reconnect", "acceptance",
                    "display_modifies_physics"):
            invalid = deepcopy(evidence)
            invalid[key] = True
            with self.subTest(key=key), self.assertRaises(DisplaySceneBindingError):
                self.binding.validate_frame_evidence(invalid)

        swapped = deepcopy(evidence)
        swapped["events"] = list(reversed(evidence["events"]))
        with self.assertRaises(DisplaySceneBindingError):
            self.binding.validate_frame_evidence(swapped)

        early_recover = deepcopy(evidence)
        early_recover["events"][1]["frame"] = RETAINED_FREEZE_FRAME
        with self.assertRaises(DisplaySceneBindingError):
            self.binding.validate_frame_evidence(early_recover)

        probe = deepcopy(evidence)
        probe["scene_hash"] = PROBE_SCENE_HASH
        with self.assertRaises(DisplaySceneIdentityError):
            self.binding.validate_frame_evidence(probe)

        foreign = deepcopy(evidence)
        foreign["epoch"] = FOREIGN_EPOCH
        with self.assertRaises(DisplaySceneIdentityError):
            self.binding.validate_frame_evidence(foreign)

    def test_binding_record_keeps_visual_mirror_unbound_and_issue_open(self):
        record = self.binding.binding_record()
        self.assertEqual(record["schema"], BINDING_SCHEMA)
        self.assertEqual(record["scene_hash"], DISPLAY_SCENE_HASH)
        self.assertEqual(record["visual_mirror"], {
            "system": "UE",
            "binding_status": "not_bound",
        })
        self.assertEqual(EGO_SINGLE_BOX_BINDING.manifest["visual_mirror"],
                         record["visual_mirror"])
        self.assertIs(record["acceptance"], False)
        self.assertIs(record["issue_29_open"], True)
        self.assertIs(record["ue_session"], False)
        self.assertFalse(record["capabilities"]["forces"])
        self.assertFalse(record["capabilities"]["ue_process_control"])
        self.assertEqual(record["binding_source_identity"], BINDING_SOURCE_IDENTITY)

    def test_identity_table_reuses_profile_planner_observer_and_terrain(self):
        table = self.binding.identity_table()
        self.assertEqual(table["display_fixture"]["scene_hash"], FROZEN_SCENE_SHA256)
        self.assertTrue(table["display_fixture"]["accepted_as_display"])
        self.assertEqual(table["planner_ego"]["scene_id"], EGO_SINGLE_BOX_V1.profile_id)
        self.assertEqual(table["planner_ego"]["scene_hash"], EXPECTED_SCENE_HASH)
        self.assertFalse(table["planner_ego"]["accepted_as_display"])
        self.assertEqual(table["planner_ego"]["visual_mirror"]["binding_status"], "not_bound")
        self.assertEqual(table["generated_model_probe"]["scene_id"], PROBE_SCENE_ID)
        self.assertFalse(table["generated_model_probe"]["accepted_as_display"])
        self.assertEqual(table["terrain_feedback"]["scene_hash"], DISPLAY_SCENE_HASH)
        self.assertEqual(table["terrain_feedback"]["stacks"], dict(STACK_BODIES))
        hashes = {
            table["display_fixture"]["scene_hash"],
            table["planner_ego"]["scene_hash"],
            table["generated_model_probe"]["scene_hash"],
        }
        self.assertEqual(len(hashes), 3)

    def test_init_rejects_probe_hash_and_invalid_epoch(self):
        with self.assertRaises(DisplaySceneIdentityError):
            DisplaySceneBinding(EPOCH, expected_sha256=PROBE_SCENE_HASH)
        with self.assertRaises(DisplaySceneBindingError):
            DisplaySceneBinding("not-an-epoch")

    def test_module_does_not_import_ue_or_claim_runtime_control(self):
        source = (ROOT / "Simulator/wksim_runtime/display_scene_binding.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Simulator.ue55", source)
        self.assertNotIn("UnrealEditor", source)
        self.assertNotIn("19060", source)
        record = self.binding.binding_record()
        self.assertFalse(record["capabilities"]["ue_process_control"])


if __name__ == "__main__":
    unittest.main()
