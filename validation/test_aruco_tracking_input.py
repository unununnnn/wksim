"""Pure contract tests for the joint-gated ArUco target to velocity seam.

Default fixtures use the real #103 run identity values from
validation/40-aruco-live-scene/run-514743f-03/report.json (run_id
``aruco-scene-267899ace7`` is not hex32; instance/epoch/stream are hex32),
so identity rules are tested against actual shapes, not all-hex mocks.
"""
import copy
import unittest

from Simulator.wksim_perception.target_intent import TargetIntentConfig
from Simulator.wksim_runtime.aruco_tracking_input import (
    ArucoTrackingSeam, command_fields, hold_action, validate_authority,
    AUTHORITY_SCHEMA, SEAM_SCHEMA, MAX_STEP)


# Real #103 run-514743f-03 identities (read-only source of the shapes).
RUN = "aruco-scene-267899ace7"
EPOCH = "e6462b20c769429c9c559b241fc1dff1"
EPOCH2 = "cc" * 16
INSTANCE = "e02daa97ad87453082a07e61015f5932"
STREAM = "20f0765f86ae46dfb86e2e6368c3613c"
STREAM2 = "ff" * 16


def authority(**overrides):
    run_id = overrides.get("run_id", RUN)
    epoch = overrides.get("epoch", EPOCH)
    value = {
        "schema": AUTHORITY_SCHEMA,
        "kind": "joint_scene",
        "run_id": run_id,
        "epoch": epoch,
        "instance_id": INSTANCE,
        "generation": 1,
        "stream_id": STREAM,
        "authority_step": 0,
        "camera": {"vehicle_id": 1, "sensor_id": "rgb_front"},
        "vehicles": {
            "px4": {"uav_id": 1, "run_id": run_id, "epoch": epoch},
            "arducopter": {"uav_id": 2, "run_id": run_id, "epoch": epoch},
        },
    }
    value.update(overrides)
    return value


def target(step, **overrides):
    value = {
        "schema": "wksim.aruco-target.v1",
        "run_id": RUN,
        "epoch": EPOCH,
        "instance_id": INSTANCE,
        "generation": 1,
        "stream_id": STREAM,
        "vehicle_id": "1",
        "sensor_id": "rgb_front",
        "step": str(step),
        "valid_until_step": step + 300,
        "position_body_flu_m": [2.0, 0.0, 0.0],
        "position_world_ue_m": [1.0, 2.0, 3.0],
        "velocity_world_ue_mps": [9.0, 9.0, 9.0],
        "reprojection_rms_px": 0.2,
    }
    value.update(overrides)
    return value


def seam(**overrides):
    config = TargetIntentConfig((0.0, 0.0, 0.0), overrides.get("gain_per_s", 1.0),
                                overrides.get("max_speed_mps", 2.0))
    return ArucoTrackingSeam(config, authority=authority())


class AuthorityTests(unittest.TestCase):
    def test_real_scene_run_identity_shape_is_accepted(self):
        # #103 run_id is hyphenated and not hex32; the project run_id rule allows it.
        value = validate_authority(authority())
        self.assertEqual(value["run_id"], "aruco-scene-267899ace7")
        self.assertEqual(value["kind"], "joint_scene")
        self.assertEqual(set(value["vehicles"]), {"px4", "arducopter"})

    def test_run_id_rule_boundaries(self):
        for bad in ("", "-" + "a" * 5, "_abc", "a" * 65, "has space", 7):
            with self.assertRaises(ValueError):
                validate_authority(authority(run_id=bad))
        self.assertEqual(validate_authority(authority(run_id="a" * 64))["run_id"], "a" * 64)

    def test_epoch_stream_instance_stay_strict_hex32(self):
        for key in ("epoch", "stream_id", "instance_id"):
            with self.assertRaises(ValueError):
                validate_authority(authority(**{key: "not-hex32"}))

    def test_single_stack_authority_is_rejected(self):
        single = authority(vehicles={"px4": {"uav_id": 1, "run_id": RUN, "epoch": EPOCH}})
        with self.assertRaises(ValueError):
            validate_authority(single)

    def test_vehicle_epoch_mismatch_is_rejected(self):
        mismatched = authority()
        mismatched["vehicles"]["arducopter"]["epoch"] = EPOCH2
        with self.assertRaises(ValueError):
            validate_authority(mismatched)

    def test_non_joint_kind_and_bad_generation_are_rejected(self):
        for bad in (authority(kind="single_scene"), authority(generation=0),
                    authority(schema="wksim.other.v1"),
                    authority(camera={"vehicle_id": 3, "sensor_id": "rgb_front"})):
            with self.assertRaises(ValueError):
                validate_authority(bad)

    def test_config_is_explicit_without_flight_defaults(self):
        with self.assertRaises(TypeError):
            ArucoTrackingSeam({"gain_per_s": 1.0}, authority=authority())

    def test_authority_step_string_path_keeps_the_upper_bound(self):
        for bad in (str(MAX_STEP + 1), "9999999999999999999", -1, True, 1.5):
            with self.assertRaises(ValueError):
                validate_authority(authority(authority_step=bad))
        self.assertEqual(validate_authority(authority(authority_step=str(MAX_STEP)))["authority_step"],
                         MAX_STEP)


class SeamTests(unittest.TestCase):
    def test_fresh_target_maps_to_public_velocity_command_only(self):
        result = seam().update(target(100), authority_step=100)
        self.assertEqual(result["schema"], SEAM_SCHEMA)
        self.assertEqual(result["intent"]["move_mode"], "XYZ_VEL_BODY")
        command = result["command"]
        self.assertEqual(command, {"agent_cmd": "MOVE", "move_mode": "XYZ_VEL_BODY",
                                   "velocity_ref": [2.0, 0.0, 0.0],
                                   "yaw_rate_mode": True, "yaw_rate_ref": 0.0})
        self.assertIsNone(result["hold_action"])
        for diagnostic in ("position_world_ue_m", "velocity_world_ue_mps", "reprojection_rms_px"):
            self.assertNotIn(diagnostic, command)
            self.assertNotIn(diagnostic, result["intent"])

    def test_hold_carries_an_explicit_stop_requirement(self):
        result = seam().update(None, authority_step=50)
        self.assertIsNone(result["command"])
        self.assertEqual(result["intent"]["velocity_ref"], [0.0, 0.0, 0.0])
        action = result["hold_action"]
        self.assertEqual(action["required"], True)
        self.assertEqual(action["public_command"], "CURRENT_POS_HOVER")
        self.assertIsNone(command_fields({"move_mode": "HOLD"}))

    def test_regressing_authority_step_raises_and_never_commands(self):
        c = seam()
        c.update(target(100), authority_step=100)
        with self.assertRaises(ValueError):
            c.update(target(101), authority_step=99)

    def test_duplicate_target_step_holds_without_command(self):
        c = seam()
        self.assertIsNotNone(c.update(target(100), authority_step=100)["command"])
        replayed = c.update(target(100), authority_step=101)
        self.assertIsNone(replayed["command"])
        self.assertIn("duplicate", replayed["intent"]["reason"])

    def test_expired_and_future_targets_hold(self):
        c = seam()
        expired = c.update(target(10, valid_until_step=20), authority_step=100)
        self.assertIsNone(expired["command"])
        future = c.update(target(200), authority_step=100)
        self.assertIsNone(future["command"])

    def test_foreign_camera_identity_holds_without_consuming_a_step(self):
        c = seam()
        rejected = c.update(target(100, vehicle_id="2"), authority_step=100)
        self.assertIsNone(rejected["command"])
        self.assertEqual(rejected["reason"], "foreign_camera_stream")
        accepted = c.update(target(100), authority_step=101)
        self.assertIsNotNone(accepted["command"])

    def test_foreign_instance_generation_sensor_and_stream_hold(self):
        for override in ({"instance_id": "11" * 16}, {"generation": 2},
                         {"sensor_id": "rgb_rear"}, {"stream_id": STREAM2}):
            result = seam().update(target(100, **override), authority_step=100)
            self.assertIsNone(result["command"], override)

    def test_identical_rebind_is_noop_and_preserves_dedup_history(self):
        c = seam()
        c.update(target(100), authority_step=100)
        returned = c.rebind(authority(authority_step=100), authority_step=100)
        self.assertEqual(returned["epoch"], EPOCH)
        duplicate = c.update(target(100), authority_step=101)
        self.assertIsNone(duplicate["command"])
        self.assertIn("duplicate", duplicate["intent"]["reason"])

    def test_new_epoch_rebind_requires_strictly_higher_generation(self):
        c = seam()
        for bad_generation in (1, 0):
            fresh = authority(epoch=EPOCH2, generation=bad_generation)
            fresh["vehicles"]["px4"]["epoch"] = EPOCH2
            fresh["vehicles"]["arducopter"]["epoch"] = EPOCH2
            with self.assertRaises(ValueError):
                c.rebind(fresh, authority_step=0)

    def test_new_epoch_rebind_clears_history_with_higher_generation(self):
        c = seam()
        c.update(target(100), authority_step=100)
        fresh = authority(epoch=EPOCH2, stream_id=STREAM2, generation=2, authority_step=0)
        fresh["vehicles"]["px4"]["epoch"] = EPOCH2
        fresh["vehicles"]["arducopter"]["epoch"] = EPOCH2
        c.rebind(fresh, authority_step=0)
        result = c.update(target(100, epoch=EPOCH2, stream_id=STREAM2, generation=2),
                          authority_step=100)
        self.assertIsNotNone(result["command"])

    def test_retired_epoch_and_stream_never_revive(self):
        c = seam()
        fresh = authority(epoch=EPOCH2, stream_id=STREAM2, generation=2, authority_step=0)
        fresh["vehicles"]["px4"]["epoch"] = EPOCH2
        fresh["vehicles"]["arducopter"]["epoch"] = EPOCH2
        c.rebind(fresh, authority_step=0)
        for retired in (authority(generation=3), authority(generation=3, stream_id=STREAM)):
            with self.assertRaises(ValueError):
                c.rebind(retired, authority_step=0)

    def test_generation_cannot_advance_within_one_epoch(self):
        with self.assertRaises(ValueError):
            seam().rebind(authority(generation=2), authority_step=0)

    def test_cold_reset_can_keep_the_existing_rgb_stream(self):
        c=seam()
        fresh=authority(epoch=EPOCH2,generation=2,authority_step=0)
        c.rebind(fresh,authority_step=0)
        c.rebind(fresh,authority_step=0)
        self.assertIsNotNone(c.update(target(100,epoch=EPOCH2,generation=2),authority_step=100)['command'])

    def test_camera_restart_in_one_epoch_retires_only_the_old_stream(self):
        c=seam();c.update(target(100),authority_step=100)
        fresh=authority(stream_id=STREAM2,authority_step=110)
        c.rebind(fresh,authority_step=110)
        self.assertEqual(c.update(target(100,stream_id=STREAM2),authority_step=110)['reason'],'target_before_binding')
        self.assertIsNotNone(c.update(target(111,stream_id=STREAM2),authority_step=111)['command'])
        with self.assertRaisesRegex(ValueError,'retired stream'):
            c.rebind(authority(authority_step=112),authority_step=112)

    def test_lost_target_does_not_allow_replay_after_hold(self):
        c=seam();c.update(target(100),authority_step=100)
        c.update(None,authority_step=101)
        replay=c.update(target(100),authority_step=102)
        self.assertIsNone(replay['command'])
        self.assertIn('duplicate',replay['intent']['reason'])

    def test_rebind_step_must_not_contradict_the_record(self):
        with self.assertRaises(ValueError):
            seam().rebind(authority(authority_step=0), authority_step=5)

    def test_failed_rebind_does_not_partially_rewrite_state(self):
        c = seam()
        c.update(target(100), authority_step=100)
        with self.assertRaises(ValueError):
            c.rebind(authority(generation=0), authority_step=0)
        self.assertEqual(c.authority["epoch"], EPOCH)
        self.assertEqual(c.authority["generation"], 1)
        duplicate = c.update(target(100), authority_step=101)
        self.assertIn("duplicate", duplicate["intent"]["reason"])

    def test_invalid_target_shape_holds(self):
        c = seam()
        for bad in ("not-a-dict", target(100, schema="wksim.other.v1"),
                    target(100, position_body_flu_m=[float("nan"), 0.0, 0.0])):
            result = c.update(bad, authority_step=100)
            self.assertIsNone(result["command"])
            self.assertTrue(result["hold_action"]["required"])

    def test_seam_record_is_json_safe(self):
        import json
        record = seam().update(target(100), authority_step=100)
        self.assertEqual(json.loads(json.dumps(record, allow_nan=False))["schema"], SEAM_SCHEMA)


if __name__ == "__main__":
    unittest.main()
