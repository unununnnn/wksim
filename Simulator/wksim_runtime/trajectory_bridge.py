"""Fail-closed ROS 2 bridge from EGO Bspline output to public command requests.

The node reuses the reviewed pure B-spline bridge, trajectory adapter, and session
command allocator.  It owns one pending public request at a time and drives the
adapter only on the exact 10 ms sample grid.  Session high-water marks can detect
conflicting writers, but the current CommandRequest message has no owner token, so
this module does not claim atomic exclusive-writer proof.
"""
from dataclasses import dataclass
import json
import math
from numbers import Real
import time

from rclpy.node import Node
from prometheus_msgs.msg import Bspline, TextInfo, UAVCommand, UAVControlState
from wksim_msgs.msg import CommandRequest, SessionState

from Simulator.wksim_planning.ego_bspline_bridge import BridgeError, bridge_bspline
from Simulator.wksim_planning.ego_trajectory_adapter import (
    SAMPLE_STRIDE_TICKS,
    TICK_NS,
    AdapterError,
    EgoTrajectoryAdapter,
)
from Simulator.wksim_planning.trajectory_session import (
    MAX_COMMAND_ID,
    TrajectorySession,
)
from Simulator.wksim_runtime.task import valid_state


MAX_REQUEST_ID = 2**64 - 1
STATE_STALE_SECONDS = 2.0
CLOCK_FAULTS = frozenset((
    "invalid_ros_clock",
    "ros_clock_moved_backwards",
    "ros_clock_before_authority_anchor",
    "ros_clock_off_grid",
    "authority_tick_overflow",
))


@dataclass
class PendingCommand:
    request_id: int
    command_id: int


def _explicit_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _explicit_uint(value, name, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _explicit_float(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


class TrajectoryBridgeNode(Node):
    """Single-UAV planner bridge bound to one public control epoch at a time."""

    def __init__(self, *, run_id, mission_id, uav_id, fallback_yaw,
                 authority_anchor_ns, publisher_factory=None, clock_ns=None,
                 monotonic_s=None):
        run_id = _explicit_text(run_id, "run_id")
        mission_id = _explicit_text(mission_id, "mission_id")
        if len(run_id) > 64:
            raise ValueError("run_id exceeds the CommandRequest wire limit")
        if type(uav_id) is not int or uav_id != 1:
            raise ValueError("trajectory bridge only supports uav_id=1")
        fallback_yaw = _explicit_float(fallback_yaw, "fallback_yaw")
        authority_anchor_ns = _explicit_uint(
            authority_anchor_ns, "authority_anchor_ns", 2**63 - 1
        )
        if authority_anchor_ns % TICK_NS:
            raise ValueError("authority_anchor_ns must land on the 1 ms grid")

        super().__init__("wksim_trajectory_bridge")
        if clock_ns is None and not self.get_parameter("use_sim_time").value:
            self.destroy_node()
            raise ValueError("production trajectory bridge requires use_sim_time=true")
        self.run_id = run_id
        self.mission_id = mission_id
        self.uav_id = uav_id
        self.fallback_yaw = fallback_yaw
        self.authority_anchor_ns = authority_anchor_ns
        self._clock_ns = clock_ns or (lambda: self.get_clock().now().nanoseconds)
        self._monotonic_s = monotonic_s or time.monotonic

        self.epoch = None
        self.session_sequence = 0
        self.session = None
        self.adapter = None
        self.latest_state = None
        self.retired_epochs = set()
        self.request_high_water = 0
        self.event_sequence = 0
        self.pending = None
        self.next_drive_tick = None
        self.last_clock_ns = None
        self.last_ack = None
        self.last_rejection = None
        self.fault_reason = None

        topic_root = f"/uav{uav_id}/prometheus"
        publisher = publisher_factory or self.create_publisher
        self.command_pub = publisher(CommandRequest, topic_root + "/v2/command", 10)
        self._trajectory_subscriptions = [
            self.create_subscription(
                Bspline, f"/uav{uav_id}/planning/bspline", self.on_bspline, 10
            ),
            self.create_subscription(
                SessionState, topic_root + "/v2/state", self.on_session_state, 10
            ),
            self.create_subscription(
                TextInfo, topic_root + "/text_info", self.on_text_info, 10
            ),
        ]
        self.timer = self.create_timer(0.001, self.on_timer)

    def _fault(self, reason):
        if self.fault_reason is None:
            self.fault_reason = reason
        self.pending = None
        self.next_drive_tick = None
        return False

    def _identity(self):
        return dict(
            run_id=self.run_id,
            mission_id=self.mission_id,
            uav_id=self.uav_id,
            control_epoch=self.epoch,
            planner_generation=self.session.generation,
            command_high_water=self.session.last_command_id,
        )

    def _current_tick(self):
        value = self._clock_ns()
        if type(value) is not int:
            self._fault("invalid_ros_clock")
            return None
        if value == 0 and self.last_clock_ns is None:
            self.last_rejection = "clock_uninitialized"
            return None
        if self.last_clock_ns is not None and value < self.last_clock_ns:
            self._fault("ros_clock_moved_backwards")
            return None
        self.last_clock_ns = value
        if value < self.authority_anchor_ns:
            self._fault("ros_clock_before_authority_anchor")
            return None
        delta = value - self.authority_anchor_ns
        if delta % TICK_NS:
            self._fault("ros_clock_off_grid")
            return None
        tick = delta // TICK_NS
        if tick > 2**63 - 1:
            self._fault("authority_tick_overflow")
            return None
        return tick

    def _state_fresh_and_owned(self):
        msg = self.latest_state
        if msg is None or self.fault_reason is not None:
            return False
        now = self._monotonic_s()
        published = msg.published_monotonic_s
        received = msg.source_received_monotonic_s
        return bool(
            isinstance(now, Real) and math.isfinite(now)
            and math.isfinite(published) and 0.0 <= now - published <= STATE_STALE_SECONDS
            and msg.source_received_valid
            and math.isfinite(received) and 0.0 <= now - received <= STATE_STALE_SECONDS
            and valid_state(msg.state, self.uav_id)
            and msg.control.control_state == UAVControlState.COMMAND_CONTROL
            and not msg.control.failsafe
        )

    def _bind_epoch(self, msg):
        clock_fault = self.fault_reason if self.fault_reason in CLOCK_FAULTS else None
        if self.epoch is not None:
            self.retired_epochs.add(self.epoch)
        self.epoch = msg.control_epoch
        self.session_sequence = int(msg.sequence)
        self.request_high_water = int(msg.last_request_id)
        self.event_sequence = 0
        self.pending = None
        self.next_drive_tick = None
        self.last_ack = None
        self.last_rejection = None
        self.fault_reason = clock_fault
        self.session = TrajectorySession(dict(
            run_id=self.run_id,
            mission_id=self.mission_id,
            uav_id=self.uav_id,
            control_epoch=self.epoch,
            planner_generation=0,
            command_high_water=int(msg.command_high_water),
        ))
        self.adapter = EgoTrajectoryAdapter(self.session)
        self.latest_state = msg

    def on_session_state(self, msg):
        if (msg.version != SessionState.VERSION or msg.run_id != self.run_id
                or len(msg.control_epoch) != 32
                or msg.control_epoch in self.retired_epochs
                or msg.state.uav_id != self.uav_id
                or msg.control.uav_id != self.uav_id):
            return False
        try:
            sequence = _explicit_uint(msg.sequence, "session sequence", MAX_REQUEST_ID)
            request_id = _explicit_uint(msg.last_request_id, "last_request_id", MAX_REQUEST_ID)
            command_id = _explicit_uint(
                msg.command_high_water, "command_high_water", MAX_COMMAND_ID
            )
        except ValueError:
            return False

        if sequence == 0:
            return False
        if self.epoch != msg.control_epoch:
            self._bind_epoch(msg)
            return True
        if sequence <= self.session_sequence:
            return False
        self.session_sequence = sequence
        self.latest_state = msg
        self.request_high_water = max(self.request_high_water, request_id)
        if command_id > self.session.last_command_id:
            return self._fault("external_command_writer")
        if self.pending is not None and request_id > self.pending.request_id:
            return self._fault("external_request_writer")
        return True

    @staticmethod
    def _normalized_bspline(msg):
        sec = msg.start_time.sec
        nanosec = msg.start_time.nanosec
        if (type(sec) is not int or type(nanosec) is not int
                or sec < 0 or not 0 <= nanosec < 1_000_000_000):
            raise BridgeError("invalid_payload")
        return dict(
            drone_id=int(msg.drone_id),
            order=int(msg.order),
            traj_id=int(msg.traj_id),
            start_time=sec * 1_000_000_000 + nanosec,
            knots=list(msg.knots),
            pos_pts=[[point.x, point.y, point.z] for point in msg.pos_pts],
            yaw_pts=list(msg.yaw_pts),
            yaw_dt=msg.yaw_dt,
        )

    def on_bspline(self, msg):
        if self.fault_reason is not None or self.session is None:
            return False
        if self.pending is not None:
            self.last_rejection = "command_pending"
            return False
        if not self._state_fresh_and_owned():
            self.last_rejection = "state_not_fresh_or_owned"
            return False
        if self.request_high_water >= MAX_REQUEST_ID:
            return self._fault("request_id_exhausted")
        if self.session.last_command_id >= MAX_COMMAND_ID:
            return self._fault("command_id_exhausted")
        current_tick = self._current_tick()
        if current_tick is None:
            return False
        try:
            payload = self._normalized_bspline(msg)
            if payload["start_time"] < self.last_clock_ns:
                raise BridgeError("start_in_past")
            spline, trajectory_id, start_tick = bridge_bspline(
                payload,
                anchor_ns=self.authority_anchor_ns,
                current_tick=current_tick,
            )
            if start_tick != current_tick:
                raise AdapterError("start_tick_not_current")
            next_event = self.event_sequence + 1
            if next_event > MAX_COMMAND_ID:
                return self._fault("event_sequence_exhausted")
            self.adapter.replan_and_activate(
                self._identity(), next_event, spline, trajectory_id,
                start_tick, self.fallback_yaw,
            )
            self.event_sequence = next_event
            intent = self.adapter.step(
                self._identity(), current_tick, True, True
            )
        except (BridgeError, AdapterError, ValueError) as error:
            if isinstance(error.__cause__, OverflowError):
                return self._fault("planner_generation_exhausted")
            self.last_rejection = str(error)
            return False
        except OverflowError:
            return self._fault("command_id_exhausted")
        if intent is None:
            return self._fault("missing_trajectory_intent")
        self.next_drive_tick = current_tick + SAMPLE_STRIDE_TICKS
        return self._publish_intent(intent, self.last_clock_ns)

    def _publish_intent(self, intent, now_ns):
        if self.pending is not None:
            return self._fault("multiple_pending_commands")
        if self.request_high_water >= MAX_REQUEST_ID:
            return self._fault("request_id_exhausted")
        try:
            command = UAVCommand()
            command.header.stamp.sec = now_ns // 1_000_000_000
            command.header.stamp.nanosec = now_ns % 1_000_000_000
            command.header.frame_id = "map"
            command.agent_cmd = UAVCommand.MOVE
            command.control_level = UAVCommand.DEFAULT_CONTROL
            command.move_mode = (
                UAVCommand.TRAJECTORY if intent["intent"] == "trajectory"
                else UAVCommand.XYZ_POS
            )
            command.position_ref = [float(value) for value in intent["position_ref"]]
            command.velocity_ref = [float(value) for value in intent["velocity_ref"]]
            command.acceleration_ref = [float(value) for value in intent["acceleration_ref"]]
            command.yaw_ref = float(intent["yaw_ref"])
            command.yaw_rate_mode = bool(intent["yaw_rate_mode"])
            command.yaw_rate_ref = float(intent["yaw_rate_ref"])
            command.command_id = int(intent["command_id"])

            self.request_high_water += 1
            request = CommandRequest(
                version=CommandRequest.VERSION,
                run_id=self.run_id,
                control_epoch=self.epoch,
                request_id=self.request_high_water,
                command=command,
            )
        except Exception:
            return self._fault("command_message_invalid")
        self.pending = PendingCommand(request.request_id, command.command_id)
        try:
            self.command_pub.publish(request)
        except Exception:
            return self._fault("command_publish_failed")
        return True

    def on_text_info(self, msg):
        try:
            event = json.loads(msg.message)
        except (TypeError, ValueError):
            return self._fault("malformed_text_info")
        if type(event) is not dict:
            return self._fault("malformed_text_info")
        if (type(event.get("version")) is not int or event["version"] != 1
                or event.get("run_id") != self.run_id
                or event.get("control_epoch") != self.epoch):
            return False
        kind = event.get("event")
        if kind == "control_revoked":
            if msg.message_type != TextInfo.ERROR:
                return self._fault("text_info_type_mismatch")
            return self._fault("control_revoked")
        if kind not in ("command_accepted", "command_rejected"):
            return False
        request_id = event.get("request_id")
        command_id = event.get("command_id")
        if (self.last_ack is not None and kind == "command_accepted"
                and (request_id, command_id) == self.last_ack):
            return False
        if (self.pending is None
                or type(request_id) is not int or type(command_id) is not int
                or request_id != self.pending.request_id
                or command_id != self.pending.command_id):
            return self._fault("other_command_writer_event")
        if kind == "command_rejected":
            if msg.message_type != TextInfo.ERROR:
                return self._fault("text_info_type_mismatch")
            return self._fault("command_rejected")
        if msg.message_type != TextInfo.INFO:
            return self._fault("text_info_type_mismatch")
        self.last_ack = (request_id, command_id)
        self.pending = None
        return True

    def on_timer(self):
        if self.fault_reason is not None or self.next_drive_tick is None:
            return False
        current_tick = self._current_tick()
        if current_tick is None:
            return False
        if current_tick < self.next_drive_tick:
            return False
        if current_tick > self.next_drive_tick:
            return self._fault("missed_adapter_tick")
        if self.pending is not None:
            return self._fault("ack_not_received_before_next_sample")
        if not self._state_fresh_and_owned():
            return self._fault("state_not_fresh_or_owned_at_sample")
        if self.request_high_water >= MAX_REQUEST_ID:
            return self._fault("request_id_exhausted")
        if self.session.last_command_id >= MAX_COMMAND_ID:
            return self._fault("command_id_exhausted")
        try:
            intent = self.adapter.step(
                self._identity(), current_tick, True, True
            )
        except (AdapterError, ValueError, OverflowError):
            return self._fault("adapter_step_failed")
        if intent is None:
            return self._fault("missing_trajectory_intent")
        self.next_drive_tick += SAMPLE_STRIDE_TICKS
        return self._publish_intent(intent, self.last_clock_ns)
