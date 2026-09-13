"""Offline orchestration tests for JointArUcoTask (no ROS node, no simulation).

Instances are built via __new__ with explicit state so the frozen
seam/adapter and the real message classes (WSL) or constant-identical stubs
(Windows, clearly not a ROS run) verify the wiring; Task.__init__ and its ROS
resources are never started here. The joint clock is simulated with raw
nanosecond values exactly as rclpy Time.nanoseconds delivers them.
"""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from Simulator.wksim_runtime.aruco_joint_task import (
    JointArUcoTask, load_frozen_profile, read_bounded_json,
    validate_aruco_settings, validate_binding,
    BINDING_SCHEMA, OBSERVATION_SCHEMA, STACK_UAV, MAX_FILE_BYTES)

try:
    from prometheus_msgs.msg import UAVCommand as CMD, UAVSetup as SETUP
    ROS_MESSAGES = True
except ImportError:
    ROS_MESSAGES = None

    class CMD:  # Orchestration stub with the public constants; NOT a ROS message.
        INIT_POS_HOVER, CURRENT_POS_HOVER, LAND, MOVE, USER_MODE = 1, 2, 3, 4, 5
        DEFAULT_CONTROL, ABSOLUTE_CONTROL, EXIT_ABSOLUTE_CONTROL = 0, 1, 2
        XYZ_POS, XY_VEL_Z_POS, XYZ_VEL, XYZ_POS_BODY = 0, 1, 2, 3
        XYZ_VEL_BODY, XY_VEL_Z_POS_BODY, TRAJECTORY, XYZ_ATT, LAT_LON_ALT = 4, 5, 6, 7, 8

        def __init__(self, **fields):
            self.agent_cmd = 0
            self.control_level = 0
            self.move_mode = 0
            self.position_ref = [0.0, 0.0, 0.0]
            self.velocity_ref = [0.0, 0.0, 0.0]
            self.acceleration_ref = [0.0, 0.0, 0.0]
            self.yaw_ref = 0.0
            self.yaw_rate_mode = False
            self.yaw_rate_ref = 0.0
            self.att_ref = [0.0, 0.0, 0.0, 0.0]
            self.latitude = self.longitude = self.altitude = 0.0
            self.command_id = 0
            for key, value in fields.items():
                if not hasattr(self, key):
                    raise TypeError(key)
                setattr(self, key, value)

    class SETUP:  # Same constants as ros2/.../UAVSetup.msg; NOT a ROS message.
        ARMING, SET_PX4_MODE, SET_CONTROL_MODE = 0, 1, 3

        def __init__(self, **fields):
            self.cmd = 0
            self.arming = False
            self.px4_mode = ""
            self.control_state = ""
            for key, value in fields.items():
                if not hasattr(self, key):
                    raise TypeError(key)
                setattr(self, key, value)


PROFILE, PROFILE_SHA = load_frozen_profile()
RUN = "aruco-scene-267899ace7"  # Real #103 identity shape.
EPOCH = "e6462b20c769429c9c559b241fc1dff1"
INSTANCE = "e02daa97ad87453082a07e61015f5932"
STREAM = "20f0765f86ae46dfb86e2e6368c3613c"
IMAGE_SHA = "ab" * 32


def target(step, frame, **overrides):
    value = {
        "schema": "wksim.aruco-target.v1",
        "run_id": RUN, "epoch": EPOCH, "instance_id": INSTANCE, "generation": 1,
        "stream_id": STREAM, "vehicle_id": "1", "sensor_id": "front_rgb",
        "step": str(step), "frame_id": str(frame), "valid_until_step": step + 300,
        "position_body_flu_m": [2.0, -0.3, 0.05],
    }
    value.update(overrides)
    return value


def make_settings(scene):
    return validate_aruco_settings({
        "profile": json.loads(json.dumps(PROFILE)),
        "scene_directory": str(scene),
        "binding_path": str(scene / "binding.json"),
        "observation_path": str(scene / "observation.json"),
        "selected_stack": "arducopter",
        "instance_id": INSTANCE,
        "generation": 1,
    })


def make_task(scene, *, selected=True, fail_on_send=False):
    task = JointArUcoTask.__new__(JointArUcoTask)
    task.aruco = make_settings(scene)
    task.directory = Path(scene)
    task.scene_epoch = EPOCH
    task.run_id = RUN
    task.uav_id = STACK_UAV["arducopter"] if selected else STACK_UAV["px4"]
    task.flight_stack = "arducopter" if selected else "px4"
    task.selected = selected
    task.binding = None
    task.seam = None
    task.adapter = None
    task._last_sequence = None
    task._last_observation_raw = None
    task._last_frame_id = None
    task._last_record = None
    task._last_clock_ns = None
    task._episode_completed = False
    task.observation_links = []
    task._hover_position = (0.0, 0.0, 3.0)
    task.epoch = "dd" * 16
    task.Cmd = CMD
    task.Setup = SETUP
    task.latest = {"state": SimpleNamespace(
        position=[0.0, 0.0, 3.0], velocity=[0.0, 0.0, 0.0], attitude=[0.0, 0.0, 0.0],
        connected=True, odom_valid=True, armed=False, uav_id=task.uav_id,
        header=SimpleNamespace(frame_id="map", stamp=SimpleNamespace(sec=1, nanosec=0)))}
    task.received = {"state": 0.0}
    task.sent = []
    task.fail_on_send = fail_on_send
    task.now_ns = [1_000_000_000]  # authority step 1000

    def now():
        return SimpleNamespace(nanoseconds=task.now_ns[0])

    task.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(now=now))

    def send(msg, label, timeout=None):
        # Mirrors JointArUcoTask.send: the profile acceptance timeout applies
        # only to visual tracking labels; everything else keeps Task default 10.
        if timeout is None:
            timeout = (PROFILE["mission"]["command_acceptance_timeout_s"]
                       if label.startswith("aruco-tracking-") else 10)
        task.sent.append((label, msg, timeout))
        if task.fail_on_send:
            raise TimeoutError(label)

    task.send = send
    task.fresh = lambda: True
    return task


def write_binding(scene, **overrides):
    value = {
        "schema": BINDING_SCHEMA,
        "run_id": RUN, "instance_id": INSTANCE, "epoch": EPOCH, "generation": 1,
        "stream_id": STREAM,
        "camera": {"vehicle_id": 1, "sensor_id": "front_rgb"},
        "first_step": 1000, "profile_sha256": PROFILE_SHA,
    }
    value.update(overrides)
    (scene / "binding.json").write_text(json.dumps(value), encoding="utf-8")
    return value


def write_observation(scene, sequence, capture_step, frame_id, obs_target, **overrides):
    value = {
        "schema": OBSERVATION_SCHEMA,
        "run_id": RUN, "instance_id": INSTANCE, "epoch": EPOCH, "generation": 1,
        "stream_id": STREAM, "sequence": sequence, "capture_step": capture_step,
        "frame_id": frame_id, "target": obs_target, "image_sha256": IMAGE_SHA,
    }
    value.update(overrides)
    (scene / "observation.json").write_text(json.dumps(value), encoding="utf-8")


class SettingsAndBindingTests(unittest.TestCase):
    def test_settings_require_the_frozen_profile_and_scene_local_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            settings = make_settings(scene)
            self.assertEqual(settings["profile_sha256"], PROFILE_SHA)
            self.assertEqual(settings["episode_steps"], 12000)
            for bad in ({"profile": dict(PROFILE, schema="wksim.other.v1")},
                        {"binding_path": "/etc/passwd"},
                        {"observation_path": "../observation.json"},
                        {"selected_stack": "solo"},
                        {"instance_id": "not-hex"}, {"generation": 0},
                        {"generation": True}):
                base = {"profile": json.loads(json.dumps(PROFILE)), "scene_directory": str(scene),
                        "binding_path": str(scene / "binding.json"),
                        "observation_path": str(scene / "observation.json"),
                        "selected_stack": "arducopter", "instance_id": INSTANCE, "generation": 1}
                base.update(bad)
                with self.assertRaises(ValueError, msg=bad):
                    validate_aruco_settings(base)

    def test_binding_identity_future_and_profile_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            settings = make_settings(scene)
            write_binding(scene)
            binding = validate_binding(json.loads((scene / "binding.json").read_text()),
                                       settings, run_id=RUN, scene_epoch=EPOCH, now_step=1000)
            self.assertEqual(binding["first_step"], 1000)
            self.assertEqual(binding["episode_end_step"], 13000)
            for bad in ({"schema": "wksim.other.v1"}, {"run_id": "other"},
                        {"epoch": "ab" * 16}, {"instance_id": "cd" * 16},
                        {"generation": 2}, {"generation": True},
                        {"camera": {"vehicle_id": 2, "sensor_id": "front_rgb"}},
                        {"camera": {"vehicle_id": 1, "sensor_id": "rear"}},
                        {"profile_sha256": "00" * 32}, {"first_step": -1}):
                write_binding(scene, **bad)
                with self.assertRaises(ValueError, msg=bad):
                    validate_binding(json.loads((scene / "binding.json").read_text()),
                                     settings, run_id=RUN, scene_epoch=EPOCH, now_step=1000)
            write_binding(scene, first_step=5000)
            with self.assertRaises(ValueError):  # first_step in the authority future
                validate_binding(json.loads((scene / "binding.json").read_text()),
                                 settings, run_id=RUN, scene_epoch=EPOCH, now_step=1000)

    def test_oversized_or_linked_files_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            big = scene / "observation.json"
            big.write_text(json.dumps({"schema": OBSERVATION_SCHEMA,
                                       "pad": "x" * MAX_FILE_BYTES}), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_bounded_json(big)
            real = scene / "real.json"
            real.write_text("{}", encoding="utf-8")
            link = scene / "link.json"
            try:
                os.symlink(real, link)
            except OSError:
                self.skipTest("symlink creation unavailable on this host")
            with self.assertRaises(ValueError):
                read_bounded_json(link)


class OrchestrationTests(unittest.TestCase):
    def bound_task(self, scene, **kwargs):
        task = make_task(scene, **kwargs)
        write_binding(scene)
        task._load_binding()
        return task

    def test_prefix_sends_the_real_setup_enum_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = make_task(Path(tmp))
            task.latest = {"state": SimpleNamespace(
                position=[0.0, 0.0, 0.0], velocity=[0.0, 0.0, 0.0], attitude=[0.0, 0.0, 0.0],
                connected=True, odom_valid=True, armed=False, uav_id=task.uav_id,
                header=SimpleNamespace(frame_id="map", stamp=SimpleNamespace(sec=1, nanosec=0)))}
            task.wait = lambda *a, **k: None
            task.dwell = lambda *a, **k: None
            task._takeoff_prefix()
            cmds = [msg.cmd for _, msg, _ in task.sent]
            self.assertEqual(cmds, [SETUP.SET_PX4_MODE, SETUP.ARMING, SETUP.SET_CONTROL_MODE])
            self.assertEqual((SETUP.SET_PX4_MODE, SETUP.ARMING, SETUP.SET_CONTROL_MODE), (1, 0, 3))
            self.assertEqual(task.sent[0][1].px4_mode, "AUTO.LOITER")
            self.assertEqual(task.sent[2][1].control_state, "COMMAND_CONTROL")
            self.assertTrue(all(timeout == 10 or label == "task_control_ready"
                                for label, _, timeout in task.sent))

    def test_authority_step_uses_raw_nanoseconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = make_task(Path(tmp))
            task.now_ns[0] = 101_000_000
            self.assertEqual(task._authority_step(), 101)
            task.now_ns[0] = 101_999_999
            self.assertEqual(task._authority_step(), 101)  # floored, never rounded
            task.now_ns[0] = 100_999_999
            with self.assertRaises(RuntimeError):  # clock moved backwards
                task._authority_step()

    def test_no_visual_move_before_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = make_task(Path(tmp))
            with self.assertRaises(RuntimeError):
                task._tracking_step(1000)
            self.assertEqual(task.sent, [])

    def test_new_observation_sends_move_and_links_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            write_observation(scene, 1, 1000, 1, target(1000, 1))
            task._tracking_step(1000)
            label, msg, timeout = task.sent[-1]
            self.assertEqual(msg.agent_cmd, CMD.MOVE)
            self.assertEqual(msg.move_mode, CMD.XYZ_VEL_BODY)
            self.assertEqual(msg.command_id, 1)
            self.assertEqual(timeout, PROFILE["mission"]["command_acceptance_timeout_s"])
            self.assertEqual(task.observation_links[-1]["sequence"], 1)
            self.assertEqual(task.observation_links[-1]["command_id"], 1)

    def test_missing_file_without_record_is_an_explicit_hold_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = self.bound_task(Path(tmp))
            task._tracking_step(1000)  # No observation file yet.
            self.assertEqual(task.sent[-1][1].agent_cmd, CMD.CURRENT_POS_HOVER)
            task._tracking_step(1100)  # Still nothing: suppressed, no spam.
            self.assertEqual(len(task.sent), 1)

    def test_unchanged_resident_file_never_refeds_and_expiry_hovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            write_observation(scene, 1, 1000, 1, target(1000, 1))
            task._tracking_step(1000)
            self.assertEqual(task.sent[-1][1].agent_cmd, CMD.MOVE)
            task.now_ns[0] = 1_100_000_000
            task._tracking_step(1100)  # Same file, byte-identical: cached record only.
            self.assertEqual(len(task.sent), 1)
            self.assertEqual(task.adapter.actions[-1]["action"], "duplicate_record")
            task.now_ns[0] = 1_500_000_000
            task._tracking_step(1500)  # valid_until 1300 passed: expired -> hover.
            self.assertEqual(task.sent[-1][1].agent_cmd, CMD.CURRENT_POS_HOVER)
            self.assertEqual(task.adapter.actions[-1]["seam_reason"],
                             "expired_move:target_accepted")

    def test_same_sequence_with_changed_content_is_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            write_observation(scene, 1, 1000, 1, target(1000, 1))
            task._tracking_step(1000)
            write_observation(scene, 1, 1000, 1, target(1000, 1), image_sha256="cd" * 32)
            with self.assertRaises(ValueError):
                task._tracking_step(1001)

    def test_sequence_regression_and_frame_regression_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            write_observation(scene, 2, 1000, 2, target(1000, 2))
            task._tracking_step(1000)
            write_observation(scene, 1, 1010, 3, target(1010, 3))  # sequence backwards
            with self.assertRaises(ValueError):
                task._tracking_step(1010)
            write_observation(scene, 3, 1010, 2, target(1010, 2))  # frame backwards
            with self.assertRaises(ValueError):
                task._tracking_step(1010)
            self.assertEqual(len(task.sent), 1)

    def test_capture_and_frame_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            write_observation(scene, 1, 1000, 1, target(1010, 1))  # target step mismatch
            with self.assertRaises(ValueError):
                task._tracking_step(1000)
            write_observation(scene, 1, 1000, 1, target(1000, 2))  # frame mismatch
            with self.assertRaises(ValueError):
                task._tracking_step(1000)
            self.assertEqual(task.sent, [])

    def test_foreign_observation_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            for bad in ({"run_id": "other"}, {"stream_id": "cd" * 16},
                        {"generation": 2}, {"generation": True},
                        {"image_sha256": "zz"}, {"target": "not-a-dict"}):
                write_observation(scene, 1, 1000, 1, target(1000, 1), **bad)
                with self.assertRaises(ValueError, msg=bad):
                    task._tracking_step(1000)
            self.assertEqual(task.sent, [])

    def test_future_capture_step_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            write_observation(scene, 1, 2000, 1, target(2000, 1))
            with self.assertRaises(ValueError):
                task._tracking_step(1000)

    def test_peer_binds_but_never_builds_seam_or_sends_visual_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = make_task(scene, selected=False)
            write_binding(scene)
            task._load_binding()
            self.assertIsNone(task.seam)
            self.assertIsNone(task.adapter)
            self.assertEqual(task.binding["episode_end_step"], 13000)
            with self.assertRaises(RuntimeError):
                task._tracking_step(1000)

    def test_completed_episode_rejects_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            task._episode_completed = True
            with self.assertRaises(RuntimeError):
                task._tracking_step(2000)

    def test_send_failure_keeps_consumed_id_and_next_send_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene, fail_on_send=True)
            write_observation(scene, 1, 1000, 1, target(1000, 1))
            with self.assertRaises(TimeoutError):
                task._tracking_step(1000)
            failed = task.adapter.actions[-1]
            self.assertTrue(failed["send_failed"])
            self.assertTrue(failed["ack_unconfirmed"])
            self.assertEqual(failed["command_id"], 1)
            task.fail_on_send = False
            write_observation(scene, 2, 1100, 2, target(1100, 2))
            task.now_ns[0] = 1_100_000_000
            task._tracking_step(1100)
            self.assertEqual(task.sent[-1][1].command_id, 2)

    def test_uint32_command_id_never_wraps(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            task.adapter._command_id = 2**32 - 1
            write_observation(scene, 1, 1000, 1, target(1000, 1))
            with self.assertRaises(ValueError):
                task._tracking_step(1000)

    def test_land_tail_uses_adapter_high_water(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp)
            task = self.bound_task(scene)
            write_observation(scene, 1, 1000, 1, target(1000, 1))
            task._tracking_step(1000)
            task.wait = lambda *a, **k: None
            task._land_tail()
            labels = [label for label, _, _ in task.sent]
            self.assertEqual(labels[0], "aruco-tracking-move")
            self.assertEqual(task.sent[1][1].agent_cmd, CMD.LAND)
            self.assertEqual(task.sent[1][1].command_id, 2)
            self.assertEqual(task.sent[2][1].cmd, SETUP.SET_PX4_MODE)
            self.assertEqual(task.sent[1][2], 10)  # LAND keeps the Task default timeout.


if __name__ == "__main__":
    unittest.main()
