"""ROS2 Route-B transport node: TCP Bspline sender -> pump -> shared session ->
PlannerCommandEgress -> /uavN/prometheus/v2/command (CommandRequest).

This is the real wiring for the P1 gap closed offline in
``planner_command_egress.py``: ONE adapter/session is created per control
epoch and handed to BOTH the transport pump (receive side) and the command
egress (publish side) -- there is exactly one command-id writer per epoch.

Discipline (identical to the ROS2 trajectory bridge, via shared pure seams in
``planner_command_egress`` -- nothing is re-implemented or weakened here):

- 2-second freshness + ownership gate: ``session_state_fresh_and_owned``
  (published/received monotonic windows inclusive, source-received validity,
  valid_state, COMMAND_CONTROL, no failsafe).
- Authority clock: strict monotonic ROS clock, grid-checked through
  ``authority_tick`` with the bridge's exact fault reasons; ``use_sim_time``
  is required in production exactly like the bridge.
- SessionState: ``session_state_decision`` (version/run/32-hex epoch/retired
  epochs/uav ids, uint gates, sequence==0, epoch-bind before monotonicity,
  external command/request writer faults, mutation order preserved).
- Single pending command, request/command high-water caps, TextInfo ACK
  correlation: owned by ``PlannerCommandEgress`` and the shared
  ``classify_command_event``.
- Wire assembly: ``build_ros_command_request`` from the trajectory bridge is
  the ONLY symbolic->constant mapping for both writers.
- Drive schedule mirrors the bridge: an accepted frame publishes its first
  intent at the activation tick, then a 1 ms timer steps exactly every
  SAMPLE_STRIDE_TICKS; a missed tick, an un-acked pending command, or stale
  state at sample time all fail closed.

Fail-closed: any pump/receiver/egress fault latches ``fault_reason``; the
node stops publishing and polling until process restart. A poisoned pump is
NEVER auto-recovered: recovery requires a NEW transport_session_id, which the
sender must mint -- this node refuses to auto-rewrite generations or session
ids.

The reverse channel (control_state/odom ROS2 -> ROS1) and the EGO stop
carrier are separate slices; this node does not fake them.
"""

import json
import math
import re
import socket
import time
from numbers import Real

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from prometheus_msgs.msg import TextInfo, UAVControlState
from wksim_msgs.msg import CommandRequest, SessionState

from Simulator.wksim_planning.ego_trajectory_adapter import (
    SAMPLE_STRIDE_TICKS,
    TICK_NS,
    EgoTrajectoryAdapter,
)
from Simulator.wksim_planning.trajectory_session import TrajectorySession
from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpDecoder
from Simulator.wksim_runtime.planner_command_egress import (
    EgressFault,
    PlannerCommandEgress,
    authority_tick,
    session_state_decision,
    session_state_fresh_and_owned,
)
from Simulator.wksim_runtime.planner_transport_pump import (
    PlannerTransportPump,
    PumpError,
)
from Simulator.wksim_runtime.planner_transport_receiver import (
    PlannerTransportReceiver,
    ReceiverError,
)
from Simulator.wksim_runtime.trajectory_bridge import build_ros_command_request
from Simulator.wksim_runtime.task import valid_state


RECEIVE_POLL_SECONDS = 0.005
DRIVE_SECONDS = TICK_NS / 1_000_000_000
MAX_TRANSPORT_PORT = 65535


class PlannerTransportNode(Node):
    """One-UAV Route-B transport node bound to one public control epoch."""

    def __init__(self, *, run_id=None, mission_id=None, uav_id=None,
                 fallback_yaw=None, authority_anchor_ns=None,
                 listen_host=None, listen_port=None,
                 transport_session_id=None,
                 clock_ns=None, monotonic_s=None):
        super().__init__("wksim_planner_transport")
        self._listener = None
        self._connection = None
        descriptor = ParameterDescriptor(read_only=True)
        parameter_defaults = {
            "run_id": "",
            "mission_id": "",
            "uav_id": 0,
            "fallback_yaw": float("nan"),
            "authority_anchor_ns": -1,
            "listen_host": "",
            "listen_port": -1,
            "transport_session_id": "",
        }

        def parameter(name, supplied):
            default = parameter_defaults[name] if supplied is None else supplied
            return self.declare_parameter(name, default, descriptor).value

        try:
            run_id = self._explicit_text(parameter("run_id", run_id), "run_id")
            mission_id = self._explicit_text(
                parameter("mission_id", mission_id), "mission_id")
            uav_id = parameter("uav_id", uav_id)
            fallback_yaw = self._explicit_float(
                parameter("fallback_yaw", fallback_yaw), "fallback_yaw")
            authority_anchor_ns = self._explicit_uint(
                parameter("authority_anchor_ns", authority_anchor_ns),
                "authority_anchor_ns", 2**63 - 1)
            listen_host = self._explicit_text(
                parameter("listen_host", listen_host), "listen_host")
            listen_port = parameter("listen_port", listen_port)
            transport_session_id = self._explicit_text(
                parameter("transport_session_id", transport_session_id),
                "transport_session_id")
            if len(run_id) > 64:
                raise ValueError("run_id exceeds the CommandRequest wire limit")
            if type(uav_id) is not int or uav_id != 1:
                raise ValueError("planner transport node only supports uav_id=1")
            if authority_anchor_ns % TICK_NS:
                raise ValueError("authority_anchor_ns must land on the 1 ms grid")
            if type(listen_port) is not int or not 1 <= listen_port <= MAX_TRANSPORT_PORT:
                raise ValueError("listen_port must be an integer in [1, 65535]")
            if re.fullmatch(r'[0-9a-f]{32}', transport_session_id) is None:
                raise ValueError(
                    "transport_session_id must be exactly 32 lowercase hex "
                    "characters, configured identically on the ROS1 sender")
            if clock_ns is None and not self.get_parameter("use_sim_time").value:
                raise ValueError(
                    "production planner transport requires use_sim_time=true")
        except Exception:
            self.destroy_node()
            raise
        self.run_id = run_id
        self.mission_id = mission_id
        self.uav_id = uav_id
        self.fallback_yaw = fallback_yaw
        self.authority_anchor_ns = authority_anchor_ns
        self.transport_session_id = transport_session_id
        self._clock_ns = clock_ns or (lambda: self.get_clock().now().nanoseconds)
        self._monotonic_s = monotonic_s or time.monotonic

        # Listening socket for the ROS1 Bspline TCP sender (Route-B origin).
        try:
            self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._listener.bind((listen_host, listen_port))
            self._listener.listen(1)
            self._listener.setblocking(False)
        except OSError:
            self.destroy_node()
            raise
        self._connection = None

        self.epoch = None
        self.session_sequence = 0
        self.session = None
        self.adapter = None
        self.pump = None
        self.receiver = None
        self.egress = None
        self.retired_epochs = set()
        self.latest_state = None
        self.fault_reason = None
        self.last_clock_ns = None
        self.last_rejection = None
        self._next_drive_tick = None

        topic_root = f"/uav{uav_id}/prometheus"
        self.command_pub = self.create_publisher(
            CommandRequest, topic_root + "/v2/command", 10)
        self._subscriptions = [
            self.create_subscription(
                SessionState, topic_root + "/v2/state", self.on_session_state, 10),
            self.create_subscription(
                TextInfo, topic_root + "/text_info", self.on_text_info, 10),
        ]
        self.receive_timer = self.create_timer(
            RECEIVE_POLL_SECONDS, self.on_receive_timer)
        self.drive_timer = self.create_timer(DRIVE_SECONDS, self.on_drive_timer)

    # ---- small validators (bridge discipline) ------------------------------
    @staticmethod
    def _explicit_text(value, name):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _explicit_uint(value, name, maximum):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer in [0, {maximum}]")
        return value

    @staticmethod
    def _explicit_float(value, name):
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite real number")
        return float(value)

    def _fault(self, reason):
        if self.fault_reason is not None:
            return False
        self.fault_reason = reason
        self._close_transport()
        self.get_logger().error(f"planner transport fault: {reason}")
        return False

    def _close_transport(self):
        self._drop_connection()
        if self._listener is not None:
            self._listener.close()
            self._listener = None

    def destroy_node(self):
        try:
            self._close_transport()
        finally:
            result = super().destroy_node()
        return result

    # ---- authoritative clock ------------------------------------------------
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
        try:
            return authority_tick(value, self.authority_anchor_ns)
        except ValueError as error:
            self._fault(str(error))
            return None

    def _identity(self):
        return dict(
            run_id=self.run_id,
            mission_id=self.mission_id,
            uav_id=self.uav_id,
            control_epoch=self.epoch,
            planner_generation=self.session.generation,
            command_high_water=self.session.last_command_id,
        )

    def _state_fresh_and_owned(self):
        msg = self.latest_state
        if msg is None or self.fault_reason is not None:
            return False
        return session_state_fresh_and_owned(
            now_s=self._monotonic_s(),
            published_s=msg.published_monotonic_s,
            received_s=msg.source_received_monotonic_s,
            received_valid=msg.source_received_valid,
            state_valid=valid_state(msg.state, self.uav_id),
            control_is_command=(
                msg.control.control_state == UAVControlState.COMMAND_CONTROL),
            failsafe=bool(msg.control.failsafe))

    # ---- epoch binding -------------------------------------------------------
    def _bind_epoch(self, msg):
        if self.epoch is not None:
            self.retired_epochs.add(self.epoch)
        self._drop_connection()
        self.epoch = msg.control_epoch
        self.session_sequence = int(msg.sequence)
        self.latest_state = msg
        self._next_drive_tick = None
        self.session = TrajectorySession(dict(
            run_id=self.run_id,
            mission_id=self.mission_id,
            uav_id=self.uav_id,
            control_epoch=self.epoch,
            planner_generation=0,
            command_high_water=int(msg.command_high_water),
        ))
        # ONE adapter/session, shared by receive (pump) and publish (egress).
        self.adapter = EgoTrajectoryAdapter(self.session)
        self.pump = PlannerTransportPump(
            self.adapter,
            decoder=BsplineTcpDecoder(self.transport_session_id),
            anchor_ns=self.authority_anchor_ns,
            initial_event_sequence=1,
            initial_current_tick=0,
        )
        self.receiver = None  # built when the sender connects
        self.egress = PlannerCommandEgress(
            self.adapter,
            self._publish_envelope,
            run_id=self.run_id,
            mission_id=self.mission_id,
            uav_id=self.uav_id,
            control_epoch=self.epoch,
            clock_ns=self._clock_ns,
            initial_request_high_water=int(msg.last_request_id),
        )

    def _drop_connection(self):
        if self._connection is not None:
            try:
                self._connection.close()
            except OSError:
                pass
        self._connection = None
        self.receiver = None

    def on_session_state(self, msg):
        if self.fault_reason is not None:
            return False
        try:
            action, reason = session_state_decision(
                dict(
                    version_ok=(msg.version == SessionState.VERSION),
                    run_match=(msg.run_id == self.run_id),
                    control_epoch=msg.control_epoch,
                    epoch_well_formed=(re.fullmatch(r'[0-9a-f]{32}', msg.control_epoch) is not None),
                    state_uav_match=(msg.state.uav_id == self.uav_id),
                    control_uav_match=(msg.control.uav_id == self.uav_id),
                    sequence=msg.sequence,
                    last_request_id=msg.last_request_id,
                    command_high_water=msg.command_high_water,
                ),
                dict(
                    retired_epochs=self.retired_epochs,
                    current_epoch=self.epoch,
                    current_sequence=self.session_sequence,
                    session_command_high_water=(
                        self.session.last_command_id
                        if self.session is not None else 0),
                    pending_request_id=(
                        self.egress.pending[0]
                        if self.egress is not None
                        and self.egress.pending is not None else None),
                ))
            if action == "ignore":
                return False
            if action == "bind":
                if self.epoch is not None:
                    # A transport token cannot silently reset its sequence
                    # ledger across control epochs: old wire frames have no
                    # control_epoch field. Restart with a fresh transport token.
                    return self._fault("control_epoch_changed_requires_new_transport_session")
                self._bind_epoch(msg)
                return True
            # update/fault: sequence accepted; record state fields first,
            # matching the bridge's mutation order.
            self.session_sequence = msg.sequence
            self.latest_state = msg
            if action == "fault":
                return self._fault(reason)
            return True
        except Exception:
            return self._fault("internal_callback_error")

    # ---- publish seam ---------------------------------------------------------
    def _publish_envelope(self, envelope):
        request = build_ros_command_request(
            envelope["command"], run_id=envelope["run_id"],
            control_epoch=envelope["control_epoch"],
            request_id=envelope["request_id"])
        self.command_pub.publish(request)

    # ---- receive loop ----------------------------------------------------------
    def _ensure_connection(self):
        if self._connection is not None:
            return True
        try:
            connection, _peer = self._listener.accept()
        except BlockingIOError:
            return False
        except OSError as error:
            self._fault(f"accept_failed:{error}")
            return False
        self._connection = connection
        self.receiver = PlannerTransportReceiver(self.pump, connection=connection)
        return True

    def on_receive_timer(self):
        if self.fault_reason is not None or self.pump is None:
            return False
        if not self._ensure_connection():
            return False
        tick = self._current_tick()
        if tick is None:
            return False
        generation_before = self.pump.session_generation
        try:
            outcomes = self.receiver.poll(
                identity=self._identity(), current_tick=tick,
                fallback_yaw=self.fallback_yaw)
            if outcomes:
                # Flush frames held across the generation advance.
                outcomes.extend(self.receiver.drain(
                    identity=self._identity(), current_tick=tick,
                    fallback_yaw=self.fallback_yaw))
        except (ReceiverError, PumpError) as error:
            return self._fault(f"transport_receive_failed:{error}")
        if self.pump.session_generation != generation_before:
            # A trajectory was activated at this tick: publish its first intent
            # now (bridge on_bspline discipline) and schedule the stride steps.
            if not self._state_fresh_and_owned():
                return self._fault("state_not_fresh_or_owned_at_activation")
            try:
                self.egress.step_and_publish(tick, True, True)
            except EgressFault as error:
                return self._fault(error.reason)
            self._next_drive_tick = tick + SAMPLE_STRIDE_TICKS
        return True

    # ---- drive loop --------------------------------------------------------------
    def on_drive_timer(self):
        if (self.fault_reason is not None or self.egress is None
                or self._next_drive_tick is None):
            return False
        tick = self._current_tick()
        if tick is None:
            return False
        if tick < self._next_drive_tick:
            return False
        if tick > self._next_drive_tick:
            return self._fault("missed_adapter_tick")
        if self.egress.pending is not None:
            return self._fault("ack_not_received_before_next_sample")
        if not self._state_fresh_and_owned():
            return self._fault("state_not_fresh_or_owned_at_sample")
        try:
            self.egress.step_and_publish(tick, True, True)
        except EgressFault as error:
            return self._fault(error.reason)
        self._next_drive_tick += SAMPLE_STRIDE_TICKS
        return True

    # ---- ACK events -----------------------------------------------------------------
    def on_text_info(self, msg):
        if self.fault_reason is not None or self.egress is None:
            return False
        try:
            event = json.loads(msg.message)
        except (TypeError, ValueError):
            return self._fault("malformed_text_info")
        try:
            self.egress.on_command_event(
                event, msg.message_type,
                info_value=TextInfo.INFO, error_value=TextInfo.ERROR)
        except EgressFault as error:
            return self._fault(error.reason)
        return True


def main(args=None):
    node = None
    rclpy.init(args=args)
    try:
        node = PlannerTransportNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
