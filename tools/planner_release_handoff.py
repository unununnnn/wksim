"""Narrow public-release handoff helper for real validation (#102 release slice).

Entry point (matches the caller in tools/planner_release_task.py)::

    handoff_and_release(task, output=..., environment=dict(os.environ),
                        mode="BRAKE", expected_native_mode="BRAKE")

Given a REAL session_v1 PVTask whose last command was ACKed and which is now
silent, this helper:

1. subscribes the real SessionState ON THE TASK'S OWN NODE (pumped via
   ``task.pump()`` -- the task never loses pumping) and verifies BOTH
   independent high-waters EXACTLY: the public request high-water equals
   ``task.request_id`` and the command high-water equals the explicit
   ``task.command_id`` (PVTask counts commands independently; a missing or
   non-integer ``command_id`` is refused, never guessed);
2. registers the TextInfo observation and the expected release request id
   (verified high-water + 1) BEFORE any cancel is sent, so a fast ACK is
   never missed;
3. starts one real ``PlannerTransportNode`` process: plain argv list, the
   caller-supplied ``environment`` mapping UNCHANGED (the sealed installed
   control overlay keeps precedence; no repository PYTHONPATH substitution),
   cwd = the task's output directory, stdout/stderr appended to the helper's
   OWN log file (never an unread PIPE);
4. reuses ONE retained TCP connection (the ready probe IS the cancel
   connection -- the receiver is one-shot and an early close would read EOF
   as connection_closed) and sends ONE real cancel control frame;
5. observes the release through real TextInfo events correlated by the SHARED
   ``classify_setup_event`` from planner_command_egress (message_type passed
   through unchanged), with the release deadline on the TASK'S ROS operation
   clock (same domain as the control runtime) while wall bounds only guard
   transport reads; ``task.pump()`` keeps health every iteration;
6. continuously verifies BOTH high-waters stay at the verified baseline for
   the whole handoff, then requires the task to adopt EXACTLY the release
   request id (not >=) with the command high-water unmoved (re-checked
   against a fresh SessionState);
7. records its own child pid/pgid/start-ticks (re-verified before TERM and
   again before KILL; inherits the task group for supervisor cleanup), timestamps, and raw events; destroys only its own
   subscriptions/socket/child -- never ``task.node``.  A refused teardown
   can never be reported as success.

This helper NEVER claims a full physical stop or a normal LAND.  The caller
afterwards uses the original stop window and the truth audit, and owns the
final teardown.  Pure helpers stay importable without ROS.
"""

import json
import os
import secrets
import signal
import socket as socket_module
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from Simulator.wksim_runtime.planner_command_egress import classify_setup_event


RELEASE_DEADLINE_NS = 10_000_000_000  # 10 s on the task's ROS operation clock
TRANSPORT_READY_S = 5.0               # wall bound for transport reads, retained
SESSION_READ_S = 5.0                  # wall bound for the fresh state read


# ---- pure verification helpers (no ROS) ---------------------------------------

def verify_session_high_water(state_fields, *, expected_request_id,
                              expected_command_high_water):
    """Verify BOTH independent high-waters EXACTLY from a fresh SessionState."""
    if type(state_fields) is not dict:
        raise ValueError("session state fields must be a dict")
    request_hw = state_fields.get("last_request_id")
    command_hw = state_fields.get("command_high_water")
    if type(request_hw) is not int or type(command_hw) is not int:
        raise ValueError("session high-water fields must be integers")
    if request_hw != expected_request_id:
        raise ValueError(
            f"request high-water mismatch: session {request_hw} != task {expected_request_id}")
    if command_hw != expected_command_high_water:
        raise ValueError(
            f"command high-water mismatch: session {command_hw} != task {expected_command_high_water}")
    return None


def verify_task_adoption(task_request_id, *, release_request_id):
    """The task must adopt EXACTLY the release request id, never beyond."""
    if type(task_request_id) is not int:
        raise ValueError("task request id must be an integer")
    if task_request_id != release_request_id:
        raise ValueError(
            f"task adopted {task_request_id}, expected exactly {release_request_id}")
    return None


def verify_command_high_water_held(command_hw_before, command_hw_after):
    """The command high-water must not move during the whole handoff."""
    if command_hw_after != command_hw_before:
        raise ValueError(
            f"command high-water moved during handoff: {command_hw_before} -> {command_hw_after}")
    return None


def mint_transport_session_id():
    """A fresh 32-hex transport session id for the helper's own node."""
    return secrets.token_hex(16)


@dataclass
class ChildRecord:
    """Own-child identity; raw values only, no namespace guessing."""
    pid: int
    pgid: int
    start_ticks: int
    argv: list
    alive_at_record: bool = True


def read_start_ticks(pid):
    """Linux /proc/<pid>/stat field 22 (starttime): after dropping the
    ``pid (comm)`` prefix, field 3 becomes index 0, so field 22 is index 19."""
    with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as handle:
        return int(handle.read().rsplit(")", 1)[1].split()[19])


def record_child(process):
    """Capture pid/pgid/start-ticks of a child THIS helper spawned."""
    pid = process.pid
    return ChildRecord(pid=pid, pgid=os.getpgid(pid),
                       start_ticks=read_start_ticks(pid),
                       argv=list(process.args))


def _child_identity_intact(record):
    try:
        if os.getpgid(record.pid) != record.pgid:
            return False
        return read_start_ticks(record.pid) == record.start_ticks
    except (ProcessLookupError, FileNotFoundError):
        return None  # gone


def terminate_child(record, process, *, timeout_s=5.0):
    """Terminate ONLY the helper's own child, identity re-verified before
    TERM and again before KILL.  A changed identity is always refused."""
    if process.poll() is not None:
        return "already_exited"
    intact = _child_identity_intact(record)
    if intact is None:
        return "already_exited"
    if not intact:
        return "identity_changed_refused"
    os.kill(record.pid, signal.SIGTERM)
    try:
        process.wait(timeout=timeout_s)
        return "terminated"
    except subprocess.TimeoutExpired:
        intact = _child_identity_intact(record)
        if not intact:
            return "identity_changed_refused"
        os.kill(record.pid, signal.SIGKILL)
        process.wait(timeout=timeout_s)
        return "killed"


# ---- ROS orchestration (lazy ROS imports; task.node is reused) ---------------

class PlannerReleaseHandoff:
    """Drive one real cancel->release handoff against a live joint runtime."""

    def __init__(self, task, *, output, environment, mode, expected_native_mode):
        # Preconditions: the source writer is silent with its last command ACKed.
        if getattr(task, "protocol", None) != "session_v1":
            raise ValueError("handoff requires a session_v1 task")
        if getattr(task, "pending_request_id", None) is not None:
            raise ValueError("task still has a pending command: not a completed ACK")
        if getattr(task, "epoch", None) is None:
            raise ValueError("task has no control epoch")
        if getattr(task, "active", False) is not True:
            raise ValueError("task must be live (active) for a handoff")
        command_id = getattr(task, "command_id", None)
        if type(command_id) is not int or command_id < 0:
            raise ValueError(
                "task.command_id (explicit PV command high-water) is required; "
                "it is never derived from request_id")
        if type(getattr(task, "request_id", None)) is not int or task.request_id < 0:
            raise ValueError("task.request_id must be a non-negative integer")
        for name, value in (("mode", mode), ("expected_native_mode", expected_native_mode)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty explicit string")
        if type(environment) is not dict:
            raise ValueError("environment must be an explicit mapping")
        if not hasattr(task, "node") or not hasattr(task, "directory"):
            raise ValueError("task must expose its own node and output directory")
        self.task = task
        self.output_dir = Path(output)
        # Persistability first: the record must exist even if the pre-spawn
        # verification fails.
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.environment = dict(environment)
        self.mode = mode
        self.expected_native_mode = expected_native_mode
        self.transport_session_id = mint_transport_session_id()
        self.listen_host = "127.0.0.1"
        self.listen_port = self._allocate_port()
        self._child = None
        self._child_record = None
        self._log_handle = None
        self._socket = None
        self._own_subscriptions = []
        self._events = []
        self._release = None
        self._text_info_types = None
        self._session_state_type = None
        self._baseline_request = None
        self._baseline_command = None
        self._public_state = None
        self._initial_request = task.request_id
        self._initial_command = task.command_id
        self.record = {
            "mode": mode, "expected_native_mode": expected_native_mode,
            "transport_session_id": self.transport_session_id,
            "listen_port": self.listen_port,
            "deadline_ros_ns": RELEASE_DEADLINE_NS,
            "outcome": "not_run", "events": [], "child": None,
            "timestamps": {},
        }

    # -- helpers ------------------------------------------------------------------
    def _allocate_port(self):
        probe = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
        probe.bind((self.listen_host, 0))
        port = probe.getsockname()[1]
        probe.close()
        return port

    def _ros_ns(self):
        """The task's ROS operation clock (same domain as the control runtime)."""
        return self.task.node.get_clock().now().nanoseconds

    def _subscribe_own(self, msg_type, topic, callback):
        subscription = self.task.node.create_subscription(msg_type, topic, callback, 10)
        self._own_subscriptions.append(subscription)
        return subscription

    def _check_invariants(self):
        if self._baseline_request is None:
            return
        allowed_requests = {self._baseline_request}
        if 'cancel_sent_ros_ns' in self.record['timestamps']:
            allowed_requests.add(self._baseline_request + 1)
        if self.task.request_id not in allowed_requests:
            raise ValueError('unexpected task request high-water during release')
        verify_command_high_water_held(self._baseline_command, self.task.command_id)
        if self._public_state is not None:
            self._validate_public_identity(self._public_state)
            verify_command_high_water_held(self._baseline_command,
                                           self._public_state.command_high_water)
            if self._public_state.last_request_id not in allowed_requests:
                raise ValueError('unexpected public request high-water during release')

    def _validate_public_identity(self, msg):
        if (msg.version != 1 or msg.sequence <= 0 or msg.run_id != self.task.run_id
                or msg.control_epoch != self.task.epoch
                or msg.state.uav_id != self.task.uav_id or msg.control.uav_id != self.task.uav_id):
            raise RuntimeError('SessionState identity differs from the task')
        now = time.monotonic()
        if (not msg.source_received_valid
                or not 0 <= now - msg.published_monotonic_s <= 2
                or not 0 <= now - msg.source_received_monotonic_s <= 2):
            raise RuntimeError('SessionState is stale during handoff')

    def _pump(self):
        self.task.pump()
        self._check_invariants()

    # -- step 1: fresh SessionState on the task's node -----------------------------
    def verify_public_high_water(self):
        from wksim_msgs.msg import SessionState
        self._session_state_type = SessionState
        received = []
        def on_state(msg):
            self._public_state = msg
            received.append(msg)
        self._subscribe_own(
            SessionState, self.task.topic_root + "v2/state", on_state)
        deadline = time.monotonic() + SESSION_READ_S
        while not received and time.monotonic() < deadline:
            self._pump()
            time.sleep(0.01)
        if not received:
            raise TimeoutError("no fresh SessionState within the read window")
        msg = received[-1]
        self._validate_public_identity(msg)
        verify_session_high_water(
            {"last_request_id": int(msg.last_request_id),
             "command_high_water": int(msg.command_high_water)},
            expected_request_id=self._initial_request,
            expected_command_high_water=self._initial_command)
        self._baseline_request = int(msg.last_request_id)
        self._baseline_command = int(msg.command_high_water)
        self.record["timestamps"]["high_water_verified_wall"] = time.monotonic()
        self.record["verified_request_high_water"] = self._baseline_request
        self.record["verified_command_high_water"] = self._baseline_command
        return msg

    # -- step 2: observation registered BEFORE cancel -------------------------------
    def _register_observation(self):
        if self._text_info_types is None:
            from prometheus_msgs.msg import TextInfo
            self._text_info_types = (int(TextInfo.INFO), int(TextInfo.ERROR))

        def on_text(msg):
            try:
                event = json.loads(msg.message)
            except (TypeError, ValueError):
                return
            self._events.append({
                "wall": time.monotonic(),
                "ros_ns": self._ros_ns(),
                "message_type": int(msg.message_type),
                "event": event,
            })

        self._subscribe_own(
            TextInfo, self.task.topic_root + "text_info", on_text)
        self._release = {
            "request_id": self._baseline_request + 1,
            "mode": self.mode,
            "expected_native_mode": self.expected_native_mode,
            "ack_received": False,
            "completed": False,
            "confirmed": False,
        }
        return self._release["request_id"]

    # -- step 3: node process ---------------------------------------------------------
    def _spawn_transport_node(self):
        argv = [
            "/usr/bin/python3", "-B", "-c",
            "import hashlib,json,pathlib,sys; "
            "import Simulator.wksim_runtime.planner_transport_node as node; "
            "loaded={name:{'path':str(pathlib.Path(module.__file__).resolve()),"
            "'sha256':hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()} "
            "for name,module in sys.modules.items() "
            "if name.startswith('Simulator.') and getattr(module,'__file__',None)}; "
            "print(json.dumps({'planner_loaded_modules':loaded}),flush=True); node.main()",
            "--ros-args",
            "-p", f"run_id:={self.task.run_id}",
            "-p", f"mission_id:={self.task.run_id}-release",
            "-p", "uav_id:=1",
            "-p", "fallback_yaw:=0.0",
            # Cancel-only handoff: no trajectory frames are admitted, so the
            # authority anchor only needs to be an explicit on-grid floor.
            "-p", "authority_anchor_ns:=0",
            "-p", f"listen_host:={self.listen_host}",
            "-p", f"listen_port:={self.listen_port}",
            "-p", f"transport_session_id:={self.transport_session_id}",
            "-p", "accept_control:=true",
            "-p", f"cancel_mode:={self.mode}",
            "-p", f"expected_native_mode:={self.expected_native_mode}",
            "-p", "use_sim_time:=true",
        ]
        self._log_handle = open(
            self.output_dir / "planner-transport-node.log", "ab", buffering=0)
        try:
            self._child = subprocess.Popen(
                argv, cwd=str(self.task.directory), env=self.environment,
                stdout=self._log_handle, stderr=subprocess.STDOUT,
                # Inherit the task group so supervisor teardown also reaches
                # this node if the task is killed before its finally block.
                start_new_session=False)
        except Exception:
            self._log_handle.close()
            self._log_handle = None
            raise
        self._child_record = record_child(self._child)
        self.record["child"] = vars(self._child_record)
        self.record["timestamps"]["node_spawned_wall"] = time.monotonic()
        return self._child

    def _wait_node_ready(self):
        """Bounded wall retry; the SUCCESSFUL connection is RETAINED (the
        receiver is one-shot -- a probe close would read as EOF poison)."""
        deadline = time.monotonic() + TRANSPORT_READY_S
        while time.monotonic() < deadline:
            if self._child.poll() is not None:
                raise RuntimeError(
                    f"transport node exited during startup: {self._child.returncode}")
            self._pump()
            try:
                self._socket = socket_module.create_connection(
                    (self.listen_host, self.listen_port), timeout=0.2)
            except OSError:
                time.sleep(0.05)
                continue
            return True
        raise TimeoutError("transport node listener not ready in time")

    # -- step 4: cancel on the retained connection --------------------------------------
    def _send_cancel(self):
        from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpEncoder
        if self._socket is None:
            raise RuntimeError("cancel requires the retained ready connection")
        encoder = BsplineTcpEncoder(self.transport_session_id)
        self._socket.sendall(encoder.encode_control_frame({"kind": "cancel"}))
        self.record["timestamps"]["cancel_sent_wall"] = time.monotonic()
        self.record["timestamps"]["cancel_sent_ros_ns"] = self._ros_ns()

    # -- step 5: observation on the task's ROS clock ---------------------------------------
    def _observe_release(self):
        deadline_ros_ns = self._ros_ns() + RELEASE_DEADLINE_NS
        info_value, error_value = self._text_info_types
        cursor = 0
        while not self._release["confirmed"]:
            if self._ros_ns() >= deadline_ros_ns:
                raise TimeoutError("release observation ROS-clock deadline exceeded")
            if self._child.poll() is not None:
                raise RuntimeError(
                    f"transport node exited early: {self._child.returncode}")
            self._pump()
            while cursor < len(self._events):
                row = self._events[cursor]
                cursor += 1
                outcome, self._release = classify_setup_event(
                    row["event"], row["message_type"],
                    run_id=self.task.run_id, epoch=self.task.epoch,
                    release=self._release,
                    info_value=info_value, error_value=error_value)
                if outcome.startswith("fault:"):
                    raise RuntimeError(f"release observation failed: {outcome}")
            time.sleep(0.01)
        self.record["timestamps"]["release_confirmed_wall"] = time.monotonic()
        self.record["timestamps"]["release_confirmed_ros_ns"] = self._ros_ns()
        return self._release["request_id"]

    # -- step 6: exact adoption, command high-water unmoved ----------------------------------
    def _verify_task_adoption(self, release_request_id):
        deadline = time.monotonic() + TRANSPORT_READY_S
        while time.monotonic() < deadline:
            self._pump()
            verify_command_high_water_held(self._baseline_command,
                                           self.task.command_id)
            if self.task.request_id >= release_request_id:
                verify_task_adoption(self.task.request_id,
                                     release_request_id=release_request_id)
                # Fresh public state must agree: request adopted exactly,
                # command baseline unmoved.
                msg = self._read_fresh_state_once()
                verify_session_high_water(
                    {"last_request_id": int(msg.last_request_id),
                     "command_high_water": int(msg.command_high_water)},
                    expected_request_id=release_request_id,
                    expected_command_high_water=self._baseline_command)
                self.record["timestamps"]["task_adopted_wall"] = time.monotonic()
                self.record["adopted_request_high_water"] = self.task.request_id
                return True
            if self.task.request_id != self._baseline_request:
                raise RuntimeError(
                    f"task request high-water skipped the release id: "
                    f"{self.task.request_id}")
            time.sleep(0.01)
        raise TimeoutError("task did not adopt the release high-water in time")

    def _read_fresh_state_once(self):
        received = []
        self._subscribe_own(
            self._session_state_type, self.task.topic_root + "v2/state",
            received.append)
        deadline = time.monotonic() + SESSION_READ_S
        while not received and time.monotonic() < deadline:
            self._pump()
            time.sleep(0.01)
        if not received:
            raise TimeoutError("no fresh SessionState for the adoption check")
        self._validate_public_identity(received[-1])
        return received[-1]

    # -- lifecycle ------------------------------------------------------------------------------
    def run(self):
        """Execute the full handoff; the record is persisted on ANY failure,
        and a refused child teardown can never report success."""
        try:
            self.verify_public_high_water()
            self._register_observation()
            self._spawn_transport_node()
            self._wait_node_ready()
            self._send_cancel()
            release_request_id = self._observe_release()
            self._verify_task_adoption(release_request_id)
            self.record["outcome"] = "release_confirmed_observed"
        except Exception as error:
            self.record["outcome"] = f"failed:{type(error).__name__}"
            self.record["error"] = str(error)
            raise
        finally:
            try:
                self._cleanup()
            except Exception as cleanup_error:
                self.record["cleanup_error"] = str(cleanup_error)
            if (self.record["outcome"] == "release_confirmed_observed"
                    and self.record.get("child_teardown") not in
                    ("terminated", "killed", "already_exited")):
                self.record["outcome"] = "failed:child_teardown_refused"
                try:
                    self._write_record()
                finally:
                    raise RuntimeError(
                        "child teardown refused; release cannot report success")
            try:
                self._write_record()
            except Exception as write_error:
                self.record["write_error"] = str(write_error)
                raise
        return self.record

    def _cleanup(self):
        """Stop the own node before closing TCP: EOF is a transport fault.

        The node inherits the task's group for outer-supervisor cleanup, but
        this helper only signals the verified child PID, never that group.
        """
        try:
            if self._child is not None and self._child_record is not None:
                self.record['child_teardown'] = terminate_child(self._child_record, self._child)
                self.record['child_returncode'] = self._child.returncode
                self._child = None
        finally:
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError as error:
                    self.record.setdefault('cleanup_notes', []).append(f'socket_close:{error}')
                self._socket = None
            for subscription in self._own_subscriptions:
                try:
                    self.task.node.destroy_subscription(subscription)
                except Exception as error:
                    self.record.setdefault('cleanup_notes', []).append(f'subscription:{error}')
            self._own_subscriptions = []
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None

    def _write_record(self):
        self.record["events"] = self._events
        log = self.output_dir / 'planner-transport-node.log'
        if log.is_file():
            for line in log.read_text(errors='replace').splitlines():
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if isinstance(message, dict) and 'planner_loaded_modules' in message:
                    self.record['planner_loaded_modules'] = message['planner_loaded_modules']
                    break
        path = self.output_dir / "planner-release-handoff.json"
        tmp = self.output_dir / ".planner-release-handoff.json.tmp"
        tmp.write_text(json.dumps(self.record, indent=2, default=str),
                       encoding="utf-8")
        os.replace(tmp, path)
        return path


def handoff_and_release(task, *, output, environment, mode, expected_native_mode):
    """Module-level entry point used by tools/planner_release_task.py."""
    return PlannerReleaseHandoff(
        task, output=output, environment=environment,
        mode=mode, expected_native_mode=expected_native_mode).run()
