"""Pure-mock + owned-subprocess tests for tools/planner_release_handoff.py.

No ROS, no build.  The correlation goes through the SHARED
classify_setup_event (TextInfo INFO=0/ERROR=2 preserved).  Orchestration is
exercised with a fully fake task (fake node/clock/pump) and stubbed
spawn/send steps; child identity uses REAL harmless owned subprocesses
(sleep), never ROS.

Run from the worktree root:
    python3 -B -m unittest validation.test_planner_release_handoff
"""
import json
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock as mock
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.planner_release_handoff import (
    ChildRecord,
    PlannerReleaseHandoff,
    handoff_and_release,
    mint_transport_session_id,
    record_child,
    read_start_ticks,
    terminate_child,
    verify_command_high_water_held,
    verify_session_high_water,
    verify_task_adoption,
)

RUN = "run-a"
EPOCH = "a" * 32
INFO = 0   # prometheus_msgs/TextInfo INFO
ERROR = 2  # prometheus_msgs/TextInfo ERROR


def make_release(request_id=30):
    return {"request_id": request_id, "mode": "BRAKE",
            "expected_native_mode": "BRAKE", "ack_received": False,
            "completed": False, "confirmed": False}


def event(kind, request_id, **fields):
    value = dict(event=kind, version=1, run_id=RUN, control_epoch=EPOCH,
                 request_id=request_id)
    value.update(fields)
    return value


def classify(event_dict, message_type, release):
    from Simulator.wksim_runtime.planner_command_egress import (
        classify_setup_event)
    return classify_setup_event(event_dict, message_type, run_id=RUN,
                                epoch=EPOCH, release=release,
                                info_value=INFO, error_value=ERROR)


class SharedClassifierCorrelationTests(unittest.TestCase):
    def test_full_two_phase_confirmation(self):
        release = make_release()
        outcome, release = classify(event("setup_received", 30), INFO, release)
        self.assertEqual(outcome, "setup_received")
        outcome, release = classify(
            event("native_ack", 30, accepted=True, stage="simple"), INFO, release)
        self.assertEqual(outcome, "ack_received")
        self.assertFalse(release["confirmed"])
        outcome, release = classify(
            event("setup_completed", 30, action="mode", value="BRAKE",
                  native_mode="BRAKE"), INFO, release)
        self.assertEqual(outcome, "confirmed")
        self.assertTrue(release["confirmed"])

    def test_negative_ack_is_info_and_rejects(self):
        outcome, _ = classify(
            event("native_ack", 30, accepted=False, stage="simple"),
            INFO, make_release())
        self.assertEqual(outcome, "fault:release_rejected")

    def test_old_request_ignored_newer_writer_faults(self):
        outcome, _ = classify(
            event("native_ack", 5, accepted=True, stage="simple"),
            INFO, make_release())
        self.assertEqual(outcome, "ignored")
        outcome, _ = classify(
            event("native_ack", 99, accepted=True, stage="simple"),
            INFO, make_release())
        self.assertEqual(outcome, "fault:other_setup_writer_event")


class IndependentHighWaterTests(unittest.TestCase):
    """PVTask counts commands independently: cmd=17 / req=29 must BOTH match."""

    def test_independent_counters_exact_match(self):
        self.assertIsNone(verify_session_high_water(
            {"last_request_id": 29, "command_high_water": 17},
            expected_request_id=29, expected_command_high_water=17))

    def test_independent_mismatches_rejected_separately(self):
        with self.assertRaisesRegex(ValueError, "request high-water mismatch"):
            verify_session_high_water(
                {"last_request_id": 30, "command_high_water": 17},
                expected_request_id=29, expected_command_high_water=17)
        with self.assertRaisesRegex(ValueError, "command high-water mismatch"):
            verify_session_high_water(
                {"last_request_id": 29, "command_high_water": 29},
                expected_request_id=29, expected_command_high_water=17)

    def test_adoption_is_exact_not_at_least(self):
        self.assertIsNone(verify_task_adoption(30, release_request_id=30))
        for bad in (29, 31):
            with self.assertRaisesRegex(ValueError, "expected exactly"):
                verify_task_adoption(bad, release_request_id=30)

    def test_command_high_water_must_not_move(self):
        self.assertIsNone(verify_command_high_water_held(17, 17))
        with self.assertRaisesRegex(ValueError, "moved during handoff"):
            verify_command_high_water_held(17, 18)


class FakeClock:
    def __init__(self):
        self.ns = 1_000_000_000

    def now(self):
        return self

    @property
    def nanoseconds(self):
        return self.ns


class FakeNode:
    def __init__(self):
        self.clock = FakeClock()
        self.destroyed_subscriptions = []
        self.node_destroyed = False

    def get_clock(self):
        return self.clock

    def create_subscription(self, msg_type, topic, callback, depth):
        self.destroyed_subscriptions.append  # silence lints
        return ("sub", topic)

    def destroy_subscription(self, subscription):
        self.destroyed_subscriptions.append(subscription)

    def destroy_node(self):
        self.node_destroyed = True


class OrchestrationTask:
    """A fake silent PVTask: command_id 17 / request_id 29, pumped by hand."""

    protocol = "session_v1"
    pending_request_id = None
    epoch = EPOCH
    run_id = RUN
    active = True
    request_id = 29
    command_id = 17
    topic_root = "/uav1/prometheus/"

    def __init__(self, directory):
        self.directory = Path(directory)
        self.node = FakeNode()
        self.script = []
        self.pumps = 0

    def pump(self):
        self.pumps += 1
        self.node.clock.ns += 100_000_000  # 100 ms of ROS time per pump
        for action in list(self.script):
            action(self)
            self.script.remove(action)


def make_handoff(task, output):
    handoff = PlannerReleaseHandoff(
        task, output=output, environment={"SEALED": "1"},
        mode="BRAKE", expected_native_mode="BRAKE")
    return handoff


class ConstructorTests(unittest.TestCase):
    def test_successful_constructor(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = OrchestrationTask(tmp)
            handoff = make_handoff(task, Path(tmp) / "release")
            self.assertEqual(handoff._baseline_request, None)
            self.assertTrue(Path(handoff.output_dir).is_dir())  # mkdir early
            self.assertEqual(handoff.environment, {"SEALED": "1"})
            self.assertEqual(len(handoff.transport_session_id), 32)
            self.assertGreater(handoff.listen_port, 0)

    def test_preconditions_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = OrchestrationTask(tmp)
            task.pending_request_id = 30
            with self.assertRaisesRegex(ValueError, "pending command"):
                make_handoff(task, Path(tmp) / "r")

            class BareTask(OrchestrationTask):
                pass
            bare = BareTask.__new__(BareTask)  # instance without class attrs
            for name in ("protocol", "pending_request_id", "epoch", "run_id",
                         "active", "request_id", "command_id", "topic_root"):
                object.__setattr__(bare, name,
                                   getattr(OrchestrationTask, name, None))
            bare.directory = Path(tmp)
            bare.node = FakeNode()
            object.__delattr__(bare, "command_id")  # instance shadow removed
            # class-level fallback also removed for this check:
            with mock.patch.object(OrchestrationTask, "command_id",
                                   None, create=True):
                with self.assertRaisesRegex(ValueError, "command_id"):
                    make_handoff(bare, Path(tmp) / "r")


class OrchestrationTests(unittest.TestCase):
    def prepare(self, tmp):
        task = OrchestrationTask(tmp)
        handoff = make_handoff(task, Path(tmp)/'release')
        handoff._baseline_request, handoff._baseline_command = 29, 17
        handoff.record.update(verified_request_high_water=29, verified_command_high_water=17)
        handoff.verify_public_high_water = lambda: None
        child = SimpleNamespace(pid=12345, args=['fixture'], returncode=-15, poll=lambda: None)
        def spawn():
            handoff._child = child
            handoff._child_record = ChildRecord(12345, 12345, 42, ['fixture'])
        handoff._spawn_transport_node = spawn
        handoff._wait_warm_ready = lambda: None
        handoff._activate = lambda: None
        handoff._verify_node_binding = lambda: None
        handoff._wait_node_ready = lambda: setattr(handoff, '_socket', mock.Mock())
        handoff._read_fresh_state_once = lambda: SimpleNamespace(last_request_id=30,command_high_water=17)
        modules = {'wksim_msgs':SimpleNamespace(), 'wksim_msgs.msg':SimpleNamespace(SessionState=object),
                   'prometheus_msgs':SimpleNamespace(),
                   'prometheus_msgs.msg':SimpleNamespace(TextInfo=SimpleNamespace(INFO=INFO,ERROR=ERROR))}
        return task,handoff,modules

    def run_record(self,handoff,modules,teardown='terminated'):
        with mock.patch.dict(sys.modules,modules), mock.patch(
                'tools.planner_release_handoff.terminate_child',return_value=teardown), \
                mock.patch('tools.planner_release_handoff.time.sleep'):
            return handoff.run()

    def confirm_and_adopt(self,task,handoff):
        for kind,fields in [('native_ack',dict(accepted=True,stage='simple')),
                            ('setup_completed',dict(action='mode',value='BRAKE',native_mode='BRAKE'))]:
            handoff._events.append(dict(wall=time.monotonic(),ros_ns=handoff._ros_ns(),
                message_type=INFO,event=event(kind,30,**fields)))
        task.request_id=30  # Public state can advance BEFORE ACK subscriber dispatch.

    def test_adoption_before_ack_observation_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            task,handoff,modules=self.prepare(tmp)
            task.script.append(lambda t:self.confirm_and_adopt(t,handoff))
            record=self.run_record(handoff,modules)
            self.assertEqual(record['outcome'],'release_confirmed_observed')
            self.assertEqual(record['adopted_request_high_water'],30)
            self.assertEqual(task.command_id,17)
            self.assertEqual(record['child_returncode'],-15)
            self.assertFalse(task.node.node_destroyed)
            handoff_path=Path(tmp)/'release/planner-release-handoff.json'
            self.assertEqual(json.loads(handoff_path.read_text())['outcome'],record['outcome'])

    def test_ros_deadline_fails_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            task,handoff,modules=self.prepare(tmp)
            with self.assertRaises(TimeoutError):self.run_record(handoff,modules)
            self.assertEqual(handoff.record['outcome'],'failed:TimeoutError')
            self.assertTrue((Path(tmp)/'release/planner-release-handoff.json').is_file())

    def test_foreign_command_or_request_rejected(self):
        for field,value in [('command_id',18),('request_id',31)]:
            with tempfile.TemporaryDirectory() as tmp:
                task,handoff,modules=self.prepare(tmp)
                task.script.append(lambda t:setattr(t,field,value))
                with self.assertRaises(ValueError):self.run_record(handoff,modules)

    def test_refused_teardown_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            task,handoff,modules=self.prepare(tmp)
            task.script.append(lambda t:self.confirm_and_adopt(t,handoff))
            with self.assertRaisesRegex(RuntimeError,'teardown refused'):
                self.run_record(handoff,modules,'identity_changed_refused')
            self.assertEqual(handoff.record['outcome'],'failed:child_teardown_refused')

    def test_failure_before_spawn_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            task,handoff,modules=self.prepare(tmp)
            def reject():raise ValueError('pre-spawn identity mismatch')
            handoff.verify_public_high_water=reject
            with self.assertRaisesRegex(ValueError,'pre-spawn identity'):self.run_record(handoff,modules)
            saved=json.loads((Path(tmp)/'release/planner-release-handoff.json').read_text())
            self.assertEqual(saved['error'],'pre-spawn identity mismatch')


class PrewarmGateTests(unittest.TestCase):
    def test_prepare_rejects_nonzero_clock_before_spawning(self):
        with tempfile.TemporaryDirectory() as tmp:
            handoff=make_handoff(OrchestrationTask(tmp),Path(tmp)/'release')
            with mock.patch.object(handoff,'_spawn_transport_node') as spawn:
                with self.assertRaisesRegex(RuntimeError,'precede the physical clock'):handoff.prepare()
                spawn.assert_not_called()

    def test_run_rechecks_pending_request_after_prewarm(self):
        with tempfile.TemporaryDirectory() as tmp:
            task=OrchestrationTask(tmp)
            handoff=make_handoff(task,Path(tmp)/'release')
            task.pending_request_id=30
            with mock.patch.object(handoff,'verify_public_high_water') as verify:
                with self.assertRaisesRegex(ValueError,'no pending request'):handoff.run()
                verify.assert_not_called()

    def test_child_program_is_valid_python(self):
        from tools.planner_release_handoff import PLANNER_PROCESS
        compile(PLANNER_PROCESS,'planner_prewarm_child','exec')


class RealChildTests(unittest.TestCase):
    """REAL harmless owned subprocesses (sleep); no ROS anywhere."""

    def test_record_and_terminate_own_child(self):
        process = subprocess.Popen(["/bin/sleep", "5"], start_new_session=True)
        try:
            record = record_child(process)
            self.assertEqual(record.pid, process.pid)
            self.assertEqual(record.pgid, process.pid)  # own session leader
            self.assertGreater(record.start_ticks, 0)
            self.assertEqual(read_start_ticks(process.pid), record.start_ticks)
            self.assertEqual(terminate_child(record, process), "terminated")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_kill_path_rechecks_identity(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(5)"],
            stdout=subprocess.PIPE, text=True, start_new_session=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'ready')
            process.stdout.close()
            record = record_child(process)
            outcome = terminate_child(record, process, timeout_s=0.3)
            self.assertEqual(outcome, "killed")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_identity_change_refused(self):
        process = subprocess.Popen(["/bin/sleep", "5"], start_new_session=True)
        try:
            record = record_child(process)
            tampered = ChildRecord(pid=record.pid, pgid=record.pgid,
                                   start_ticks=record.start_ticks + 1,
                                   argv=record.argv)
            self.assertEqual(
                terminate_child(tampered, process), "identity_changed_refused")
            self.assertIsNone(process.poll())  # never signaled
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


class GuardAndShapeTests(unittest.TestCase):
    def test_entry_point_signature_matches_caller(self):
        import inspect
        signature = inspect.signature(handoff_and_release)
        self.assertEqual(
            list(signature.parameters),
            ["task", "output", "environment", "mode", "expected_native_mode"])
        for name in ("output", "environment", "mode", "expected_native_mode"):
            self.assertEqual(
                signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_minted_session_id_shape(self):
        value = mint_transport_session_id()
        self.assertEqual(len(value), 32)
        self.assertTrue(all(char in "0123456789abcdef" for char in value))
        self.assertNotEqual(value, mint_transport_session_id())


if __name__ == "__main__":
    unittest.main()
