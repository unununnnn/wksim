"""Interface tests for tools/run_aruco_tracking.py against retained real evidence.

Uses validation/40-aruco-flight-scene-03 (a real captured run: 90 frames,
real Consumer targets, real scene manifests on disk). Nothing is resimulated;
no ROS/UE/SITL is started. Run with the pinned ArUco venv (cv2):

    work/dependencies/aruco-python/Scripts/python.exe -B -m unittest validation.test_run_aruco_tracking -v
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.run_aruco_tracking import atomic_json, episode_ready, observation
from Simulator.wksim_runtime.joint_aruco_profile import validate_experiment
from Simulator.wksim_runtime.joint_config import (
    validate_joint_config, ConfigError)
from Simulator.wksim_runtime import joint_aruco_profile
from Simulator.wksim_runtime.aruco_joint_task import (
    JointArUcoTask, load_frozen_profile, validate_aruco_settings)
import tools.run_aruco_tracking as coordinator

EVIDENCE = ROOT / "validation/40-aruco-flight-scene-03"
REPORT = json.loads((EVIDENCE / "report.json").read_text(encoding="utf-8"))
PROFILE, PROFILE_SHA = load_frozen_profile()

REAL_RUN = REPORT["config"]["run_id"]
REAL_FRAME = REPORT["frames"][0]
REAL_META = REAL_FRAME["frame"]["metadata"]
REAL_TARGET = REAL_FRAME["target"]
REAL_EPOCH = REAL_META["epoch"]
REAL_INSTANCE = REAL_META["instance_id"]
REAL_STREAM = REAL_META["stream_id"]
REAL_SCENE = Path(REAL_FRAME["scene_path"])


def real_binding():
    scene = json.loads(REAL_SCENE.read_text(encoding="utf-8"))
    return dict(schema="wksim.aruco-binding.v1", run_id=REAL_RUN, epoch=REAL_EPOCH,
                instance_id=REAL_INSTANCE, generation=1, stream_id=REAL_STREAM,
                camera=dict(vehicle_id=int(REAL_META["vehicle_id"]), sensor_id=REAL_META["sensor_id"]),
                first_step=scene["first_step"], profile_sha256=PROFILE_SHA)


def validator_stub(scene):
    """Task-side observation validator state matching the real run identity."""
    task = JointArUcoTask.__new__(JointArUcoTask)
    task.aruco = validate_aruco_settings({
        "profile": json.loads(json.dumps(PROFILE)), "scene_directory": str(scene),
        "binding_path": str(scene / "binding.json"), "observation_path": str(scene / "observation.json"),
        "selected_stack": "px4", "instance_id": REAL_INSTANCE, "generation": 1})
    task.run_id = REAL_RUN
    task.scene_epoch = REAL_EPOCH
    task.binding = {"stream_id": REAL_STREAM}
    task._last_sequence = None
    task._last_frame_id = None
    return task


class CoordinatorInterfaceTests(unittest.TestCase):
    def test_real_frames_produce_validator_accepted_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = validator_stub(Path(tmp))
            binding = real_binding()
            accepted = 0
            for entry in REPORT["frames"][:5]:
                row = observation(binding, entry["frame"], entry["target"], accepted + 1)
                now = entry["authority"]["tick"]
                sequence, capture_step, frame_id, target = task._validate_observation(row, now)
                self.assertEqual(sequence, accepted + 1)
                self.assertEqual(capture_step, int(entry["frame"]["metadata"]["step"]))
                # The Consumer target belongs to exactly this capture.
                self.assertEqual(int(target["step"]), capture_step)
                self.assertEqual(int(target["frame_id"]), frame_id)
                accepted += 1
            self.assertEqual(accepted, 5)

    def test_real_scene_manifest_drives_binding_first_step(self):
        scene = json.loads(REAL_SCENE.read_text(encoding="utf-8"))
        binding = real_binding()
        self.assertEqual(scene["schema"], "wksim.rgb-calibration-visual.v1")
        self.assertEqual(scene["case_id"], 5)
        self.assertEqual(binding["first_step"], scene["first_step"])
        self.assertEqual(scene["anchor_valid"], True)
        self.assertIn("phase", scene)

    def test_observation_rejects_foreign_frame_identity(self):
        binding = real_binding()
        frame = json.loads(json.dumps(REAL_FRAME["frame"]))
        frame["metadata"]["stream_id"] = "cd" * 16
        with self.assertRaises(ValueError):
            observation(binding, frame, None, 1)

    def test_task_validator_rejects_tampered_real_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = validator_stub(Path(tmp))
            row = observation(real_binding(), REAL_FRAME["frame"], REAL_TARGET, 1)
            now = REAL_FRAME["authority"]["tick"]
            task._validate_observation(row, now)
            for bad in ({"image_sha256": "zz"}, {"stream_id": "cd" * 16},
                        {"generation": 2}, {"capture_step": row["capture_step"] + 1}):
                with self.assertRaises(ValueError, msg=bad):
                    task._validate_observation(dict(row, **bad), now)

    def test_episode_ready_with_real_identity_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            shared = Path(tmp)
            group = shared / "epochs" / REAL_EPOCH / "tasks" / "grp"
            rows = {}
            for stack, uid in (("arducopter", 1), ("px4", 2)):
                folder = group / stack
                folder.mkdir(parents=True)
                row = dict(run_id=REAL_RUN, scene_epoch=REAL_EPOCH, stack=stack, uav_id=uid,
                           authority_tick=100, control_epoch="dd" * 16, selected=stack == "px4")
                (folder / "tracking-ready.json").write_text(json.dumps(row), encoding="utf-8")
                rows[stack] = row
            state = {"epoch": REAL_EPOCH, "epoch_dir": "/run/epochs/" + REAL_EPOCH,
                     "authority": {"tick": 200}}
            original = coordinator.unc
            coordinator.unc = lambda path: shared / "epochs" / REAL_EPOCH  # remap retained identity test
            try:
                state["epoch_dir"] = str(shared / "epochs" / REAL_EPOCH)
                state["authority"]["tick"] = 99
                self.assertIsNone(episode_ready(shared, state, REAL_RUN))
                self.assertEqual(state["authority"]["tick"], 99)
                state["authority"]["tick"] = 200
                ready = episode_ready(shared, state, REAL_RUN)
            finally:
                coordinator.unc = original
            self.assertEqual(ready["px4"]["uav_id"], 2)
            # Foreign uav identity is rejected.
            rows["px4"]["uav_id"] = 1
            (group / "px4" / "tracking-ready.json").write_text(json.dumps(rows["px4"]), encoding="utf-8")
            coordinator.unc = lambda path: shared / "epochs" / REAL_EPOCH
            try:
                with self.assertRaises(ValueError):
                    episode_ready(shared, state, REAL_RUN)
            finally:
                coordinator.unc = original

    def test_atomic_json_roundtrip_and_tmp_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observation.json"
            atomic_json(path, {"schema": "wksim.aruco-observation.v1", "sequence": 1})
            self.assertEqual(json.loads(path.read_text())["sequence"], 1)
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])


class ProfileAndConfigGateTests(unittest.TestCase):
    def test_experiment_pin_validation(self):
        good = {"selected_stack": "px4",
                "control": {"path": "/root/wksim-joint-control-aB12cd/build.json", "sha256": "ab" * 32},
                "px4": {"path": "/root/wksim-px4-land-aB12cd/land-build.json", "sha256": "cd" * 32}}
        self.assertEqual(validate_experiment(good)["selected_stack"], "px4")
        for bad in ({"selected_stack": "solo", **{k: good[k] for k in ("control", "px4")}},
                    {**good, "control": {"path": "/etc/build.json", "sha256": "ab" * 32}},
                    {**good, "px4": {"path": "/root/wksim-px4-land-aB12cd/build.json", "sha256": "cd" * 32}},
                    {k: good[k] for k in ("selected_stack", "control")}):
            with self.assertRaises(ValueError, msg=str(bad)[:60]):
                validate_experiment(bad)

    def test_joint_config_gates_the_experimental_task(self):
        base = {"schema_version": 1, "kind": "joint_scene", "run_id": "aruco-track-abc123",
                "runtime_profile": joint_aruco_profile.PROFILE, "task": joint_aruco_profile.TASK,
                "aruco_experiment": {
                    "selected_stack": "px4",
                    "control": {"path": "/root/wksim-joint-control-aB12cd/build.json", "sha256": "ab" * 32},
                    "px4": {"path": "/root/wksim-px4-land-aB12cd/land-build.json", "sha256": "cd" * 32}}}
        normalized = validate_joint_config(base)
        self.assertEqual(normalized["task"], joint_aruco_profile.TASK)
        for bad, marker in (
                (dict(base, runtime_profile="joint_quad_dds_v1"), "task without its profile"),
                (dict(base, task="public_position"), "profile without its task"),
                ({k: v for k, v in base.items() if k != "aruco_experiment"}, "missing experiment pins")):
            with self.assertRaises(ConfigError, msg=marker):
                validate_joint_config(bad)

    def test_experimental_profile_is_not_a_production_promotion(self):
        profile = joint_aruco_profile.select_config({
            "runtime_profile": joint_aruco_profile.PROFILE, "task": joint_aruco_profile.TASK,
            "aruco_experiment": {
                "selected_stack": "px4",
                "control": {"path": "/root/wksim-joint-control-aB12cd/build.json", "sha256": "ab" * 32},
                "px4": {"path": "/root/wksim-px4-land-aB12cd/land-build.json", "sha256": "cd" * 32}}})
        self.assertEqual(profile["capabilities"], [joint_aruco_profile.TASK])
        self.assertTrue(profile["experimental"])
        self.assertFalse(profile["production_admitted"])
        self.assertEqual(profile["control_workspace"], "/root/wksim-joint-control-aB12cd")


if __name__ == "__main__":
    unittest.main()
