"""Offline contract tests for the ArUco seam to public UAVCommand adapter.

In WSL with the ROS overlay paths on PYTHONPATH this uses the real
prometheus_msgs UAVCommand class (message construction only; no ROS node,
simulation or DDS participant is started). Without ROS messages a stub with
identical public constants verifies the orchestration only and is clearly not
a ROS run.
"""
import unittest

from Simulator.wksim_perception.target_intent import TargetIntentConfig
from Simulator.wksim_runtime.aruco_tracking_input import (
    ArucoTrackingSeam, AUTHORITY_SCHEMA)
from Simulator.wksim_runtime.aruco_task import ArucoCommandAdapter, ACTION_SCHEMA

try:
    from prometheus_msgs.msg import UAVCommand as CMD
    ROS_MESSAGES = True
except ImportError:
    ROS_MESSAGES = None

    class CMD:  # Orchestration stub with the public constants; NOT a ROS message.
        INIT_POS_HOVER, CURRENT_POS_HOVER, LAND, MOVE, USER_MODE = 1, 2, 3, 4, 5
        DEFAULT_CONTROL, ABSOLUTE_CONTROL, EXIT_ABSOLUTE_CONTROL = 0, 1, 2
        XYZ_POS, XY_VEL_Z_POS, XYZ_VEL, XYZ_POS_BODY = 0, 1, 2, 3
        XYZ_VEL_BODY, XY_VEL_Z_POS_BODY, TRAJECTORY, XYZ_ATT, LAT_LON_ALT = 4, 5, 6, 7, 8

        def __init__(self):
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


RUN = "aruco-scene-267899ace7"  # Real #103 run-514743f-03 identity shape.
EPOCH = "e6462b20c769429c9c559b241fc1dff1"
INSTANCE = "e02daa97ad87453082a07e61015f5932"
STREAM = "20f0765f86ae46dfb86e2e6368c3613c"


def authority(**overrides):
    value = {
        "schema": AUTHORITY_SCHEMA,
        "kind": "joint_scene",
        "run_id": RUN,
        "epoch": EPOCH,
        "instance_id": INSTANCE,
        "generation": 1,
        "stream_id": STREAM,
        "authority_step": 0,
        "camera": {"vehicle_id": 1, "sensor_id": "rgb_front"},
        "vehicles": {
            "px4": {"uav_id": 1, "run_id": RUN, "epoch": EPOCH},
            "arducopter": {"uav_id": 2, "run_id": RUN, "epoch": EPOCH},
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
    }
    value.update(overrides)
    return value


class FakeTask:
    """Send hook standing at the Task.send entry; performs no ROS work itself."""

    def __init__(self, run_id=RUN, uav_id=1, fail_on_send=False):
        self.run_id = run_id
        self.uav_id = uav_id
        self.Cmd = CMD
        self.sent = []
        self.fail_on_send = fail_on_send

    def send(self, msg, label, timeout=10):
        self.sent.append((label, msg))
        if self.fail_on_send:
            raise TimeoutError(label)  # Published, but the ACK wait failed.


def rig(last_command_id=0, **task_kwargs):
    seam = ArucoTrackingSeam(TargetIntentConfig((0.0, 0.0, 0.0), 1.0, 2.0),
                             authority=authority())
    task = FakeTask(**task_kwargs)
    return seam, task, ArucoCommandAdapter(task, seam, scene_epoch=EPOCH,
                                           last_command_id=last_command_id)


class AdapterGateTests(unittest.TestCase):
    def test_camera_vehicle_must_match_the_control_vehicle(self):
        seam = ArucoTrackingSeam(TargetIntentConfig((0, 0, 0), 1.0, 2.0), authority=authority())
        with self.assertRaises(ValueError):
            ArucoCommandAdapter(FakeTask(uav_id=2), seam, scene_epoch=EPOCH, last_command_id=0)

    def test_run_and_scene_epoch_must_match(self):
        seam = ArucoTrackingSeam(TargetIntentConfig((0, 0, 0), 1.0, 2.0), authority=authority())
        with self.assertRaises(ValueError):
            ArucoCommandAdapter(FakeTask(run_id="other-run"), seam, scene_epoch=EPOCH,
                                last_command_id=0)
        with self.assertRaises(ValueError):
            ArucoCommandAdapter(FakeTask(), seam, scene_epoch="ab" * 16, last_command_id=0)

    def test_unbound_or_wrong_objects_are_rejected(self):
        with self.assertRaises(TypeError):
            ArucoCommandAdapter(FakeTask(), object(), scene_epoch=EPOCH, last_command_id=0)

        class NoSend:  # No send entry: the adapter must refuse, never self-create one.
            run_id, uav_id, Cmd = RUN, 1, CMD

        seam = ArucoTrackingSeam(TargetIntentConfig((0, 0, 0), 1.0, 2.0), authority=authority())
        with self.assertRaises(TypeError):
            ArucoCommandAdapter(NoSend(), seam, scene_epoch=EPOCH, last_command_id=0)

    def test_command_id_high_water_is_explicit(self):
        seam = ArucoTrackingSeam(TargetIntentConfig((0, 0, 0), 1.0, 2.0), authority=authority())
        for bad in (None, -1, 1.5, True):
            with self.assertRaises((ValueError, TypeError)):
                ArucoCommandAdapter(FakeTask(), seam, scene_epoch=EPOCH, last_command_id=bad)


class CommandTests(unittest.TestCase):
    def test_move_maps_real_public_fields_and_enums(self):
        seam, task, adapter = rig()
        record = seam.update(target(100), authority_step=100)
        action = adapter.process(record, authority_step=100)
        self.assertEqual(action["schema"], ACTION_SCHEMA)
        self.assertEqual(action["action"], "move")
        self.assertEqual(action["command_id"], 1)
        label, msg = task.sent[-1]
        self.assertEqual(label, "aruco-tracking-move")
        self.assertEqual(msg.agent_cmd, CMD.MOVE)
        self.assertEqual(CMD.MOVE, 4)
        self.assertEqual(msg.move_mode, CMD.XYZ_VEL_BODY)
        self.assertEqual(CMD.XYZ_VEL_BODY, 4)
        self.assertEqual(list(msg.velocity_ref), [2.0, 0.0, 0.0])
        self.assertEqual(msg.yaw_rate_mode, True)
        self.assertEqual(msg.yaw_rate_ref, 0.0)
        self.assertEqual(msg.control_level, CMD.DEFAULT_CONTROL)
        self.assertEqual(CMD.DEFAULT_CONTROL, 0)
        self.assertEqual(msg.command_id, 1)
        self.assertFalse(action["send_failed"])
        self.assertFalse(action["ack_unconfirmed"])

    def test_first_hold_sends_hover_replacing_a_possible_host_move(self):
        # The host task may have published a MOVE before this adapter existed;
        # the first HOLD must not be suppressed.
        seam, task, adapter = rig()
        hold = adapter.process(seam.update(None, authority_step=50), authority_step=50)
        self.assertEqual(hold["action"], "hover")
        self.assertEqual(hold["command_id"], 1)
        label, msg = task.sent[-1]
        self.assertEqual(label, "aruco-tracking-hover")
        self.assertEqual(msg.agent_cmd, CMD.CURRENT_POS_HOVER)
        self.assertEqual(CMD.CURRENT_POS_HOVER, 2)

    def test_command_id_continues_the_host_high_water(self):
        # Host already used command_id 7 before the adapter was created.
        seam, task, adapter = rig(last_command_id=7)
        action = adapter.process(seam.update(target(100), authority_step=100),
                                 authority_step=100)
        self.assertEqual(action["command_id"], 8)
        self.assertEqual(task.sent[-1][1].command_id, 8)

    def test_repeated_hold_after_confirmed_hover_is_suppressed(self):
        seam, task, adapter = rig()
        adapter.process(seam.update(target(100), authority_step=100), authority_step=100)
        adapter.process(seam.update(None, authority_step=101), authority_step=101)
        suppressed = adapter.process(seam.update(None, authority_step=102), authority_step=102)
        self.assertEqual(suppressed["action"], "suppressed_hold")
        self.assertIsNone(suppressed["command_id"])
        self.assertEqual([msg.command_id for _, msg in task.sent], [1, 2])

    def test_expired_move_is_never_published_and_degrades_to_hover(self):
        seam, task, adapter = rig()
        record = seam.update(target(100), authority_step=100)  # valid_until 400
        action = adapter.process(record, authority_step=500)
        self.assertEqual(action["action"], "hover")
        self.assertEqual(action["seam_reason"], "expired_move:target_accepted")
        self.assertEqual(task.sent[-1][1].agent_cmd, CMD.CURRENT_POS_HOVER)
        self.assertNotEqual(task.sent[-1][1].move_mode, CMD.XYZ_VEL_BODY)

    def test_duplicate_record_is_an_idempotent_no_send(self):
        seam, task, adapter = rig()
        record = seam.update(target(100), authority_step=100)
        adapter.process(record, authority_step=100)
        again = adapter.process(record, authority_step=120)
        self.assertEqual(again["action"], "duplicate_record")
        self.assertIsNone(again["command_id"])
        self.assertEqual(len(task.sent), 1)

    def test_cached_move_still_expires_when_no_new_frame_arrives(self):
        seam,task,adapter=rig()
        record=seam.update(target(100),authority_step=100)
        adapter.process(record,authority_step=100)
        adapter.process(record,authority_step=400)
        expired=adapter.process(record,authority_step=401)
        self.assertEqual(expired['action'],'hover')
        self.assertEqual([msg.agent_cmd for _,msg in task.sent],[CMD.MOVE,CMD.CURRENT_POS_HOVER])
        adapter.process(record,authority_step=500)
        self.assertEqual(len(task.sent),2)
        with self.assertRaisesRegex(ValueError,'regressed'):
            adapter.process(record,authority_step=450)

    def test_unconfirmed_move_requires_a_new_hover_after_previous_hover(self):
        seam,task,adapter=rig()
        adapter.process(seam.update(None,authority_step=100),authority_step=100)
        task.fail_on_send=True
        with self.assertRaises(TimeoutError):
            adapter.process(seam.update(target(110),authority_step=110),authority_step=110)
        task.fail_on_send=False
        recovery=adapter.process(seam.update(None,authority_step=111),authority_step=111)
        self.assertEqual((recovery['action'],recovery['command_id']),('hover',3))

    def test_malformed_move_does_not_consume_an_id(self):
        import copy
        seam,task,adapter=rig()
        good=seam.update(target(100),authority_step=100)
        for field,value in (('velocity_ref',[float('nan'),0,0]),('velocity_ref',[1]),
                ('move_mode','XYZ_POS'),('yaw_rate_mode',False)):
            bad=copy.deepcopy(good);bad['command'][field]=value
            with self.assertRaises(ValueError):adapter.process(bad,authority_step=100)
        self.assertEqual((len(task.sent),adapter._command_id),(0,0))

    def test_uint32_command_number_cannot_wrap(self):
        seam,task,adapter=rig(last_command_id=2**32-1)
        with self.assertRaisesRegex(ValueError,'exhausted'):
            adapter.process(seam.update(target(100),authority_step=100),authority_step=100)
        self.assertEqual(task.sent,[])

    def test_regressing_now_step_or_old_record_raises_without_sending(self):
        seam, task, adapter = rig()
        adapter.process(seam.update(target(100), authority_step=100), authority_step=100)
        with self.assertRaises(ValueError):
            adapter.process(seam.update(target(150), authority_step=150), authority_step=99)
        stale = seam.update(target(150), authority_step=150)
        adapter.process(stale, authority_step=150)
        with self.assertRaises(ValueError):
            adapter.process(dict(stale, authority_step=100), authority_step=160)
        self.assertEqual(len(task.sent), 2)

    def test_future_intent_capture_is_rejected(self):
        seam, task, adapter = rig()
        record = seam.update(target(100), authority_step=100)
        with self.assertRaises(ValueError):
            adapter.process(record, authority_step=50)
        self.assertEqual(task.sent, [])

    def test_send_failure_keeps_the_consumed_id_and_propagates(self):
        seam, task, adapter = rig(fail_on_send=True)
        with self.assertRaises(TimeoutError):
            adapter.process(seam.update(target(100), authority_step=100), authority_step=100)
        failed = adapter.actions[-1]
        self.assertEqual(failed["command_id"], 1)
        self.assertTrue(failed["send_failed"])
        self.assertTrue(failed["ack_unconfirmed"])
        task.fail_on_send = False
        recovered = adapter.process(seam.update(target(150), authority_step=150),
                                    authority_step=150)
        self.assertEqual(recovered["command_id"], 2)  # Id 1 is never reused.

    def test_foreign_or_illegal_records_rejected_before_any_id_spend(self):
        seam, task, adapter = rig()
        good = seam.update(target(100), authority_step=100)
        for bad in (None, {"schema": "wksim.other.v1"},
                    dict(good, run_id="other-run"), dict(good, epoch="ab" * 16),
                    dict(good, stream_id="cd" * 16), dict(good, generation=2),
                    dict(good, command={"agent_cmd": "LAND"}), dict(good, command=None, hold_action=None)):
            with self.assertRaises(ValueError):
                adapter.process(bad, authority_step=100)
        self.assertEqual(task.sent, [])
        self.assertEqual(adapter.actions, [])
        self.assertEqual(adapter._command_id, 0)

    def test_recovery_correlates_seam_reason_with_public_command(self):
        seam, task, adapter = rig()
        adapter.process(seam.update(target(100), authority_step=100), authority_step=100)
        lost = adapter.process(seam.update(None, authority_step=101), authority_step=101)
        self.assertEqual(lost["seam_reason"], "target_missing")
        recovered = adapter.process(seam.update(target(150), authority_step=150),
                                    authority_step=150)
        self.assertEqual(recovered["seam_reason"], "target_accepted")
        self.assertEqual([a["command_id"] for a in adapter.actions], [1, 2, 3])
        self.assertEqual([a["action"] for a in adapter.actions], ["move", "hover", "move"])


if __name__ == "__main__":
    unittest.main()
