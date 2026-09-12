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
  external command/request writer faults, mutation order preserved). An
  in-flight release setup is correlated by its request_id exactly like a
  pending command.
- Single pending command, request/command high-water caps, TextInfo ACK
  correlation: owned by ``PlannerCommandEgress`` and the shared
  ``classify_command_event`` / ``classify_setup_event``.
- Wire assembly: ``build_ros_command_request`` and ``build_ros_mode_request``
  from the trajectory bridge are the ONLY symbolic->constant mappings.
- Drive schedule mirrors the bridge: an accepted frame publishes its first
  intent at the activation tick, then a 1 ms timer steps exactly every
  SAMPLE_STRIDE_TICKS; a missed tick, an un-acked pending command, or stale
  state at sample time all fail closed.

v2 control carrier (opt-in, ``accept_control``): gate/hold/cancel frames are
processed in exact transport-stream order. A closed gate halts trajectory
scheduling; a reopened gate NEVER resumes the old trajectory -- only a NEW
Bspline activation publishes again. An activation while the gate is closed
faults. A control rejection halts the previous activation's outputs. A
planner cancel halts scheduling immediately, keeps any pending command (its
ACK is still enforced on the original next-sample boundary), and only then
requests the public mode release through the egress -- with a 10-second
same-domain observation deadline, fail-closed. hold/cancel generation
changes are never mistaken for a Bspline activation: only an
OUTCOME_ACTIVATED outcome triggers the first publish.

Fail-closed: any pump/receiver/egress fault latches ``fault_reason``; the
node stops publishing and polling until process restart. A poisoned pump is
NEVER auto-recovered: recovery requires a NEW transport_session_id, which the
sender must mint -- this node refuses to auto-rewrite generations or session
ids.

This node does NOT claim the FC has stopped: a confirmed release only proves
the public two-phase acknowledgement; physical verification is a separate
slice. The reverse channel (control_state/odom ROS2 -> ROS1) is out of scope.
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
from wksim_msgs.msg import CommandRequest, SessionState, SetupRequest

from Simulator.wksim_planning.ego_trajectory_adapter import (
    SAMPLE_STRIDE_TICKS,
    TICK_NS,
    EgoTrajectoryAdapter,
)
from Simulator.wksim_planning.trajectory_session import TrajectorySession
from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpDecoder
from Simulator.wksim_runtime.planner_command_egress import (
    DEFAULT_RELEASE_MODES,
    EgressFault,
    PlannerCommandEgress,
    authority_tick,
    session_state_decision,
    session_state_fresh_and_owned,
)
from Simulator.wksim_runtime.planner_transport_pump import (
    OUTCOME_ACTIVATED,
    PlannerTransportPump,
    PumpError,
)
from Simulator.wksim_runtime.planner_transport_receiver import (
    PlannerTransportReceiver,
    ReceiverError,
)
from Simulator.wksim_runtime.trajectory_bridge import (
    build_ros_command_request,
    build_ros_mode_request,
)
from Simulator.wksim_runtime.task import valid_state


RECEIVE_POLL_SECONDS = 0.005
DRIVE_SECONDS = TICK_NS / 1_000_000_000
MAX_TRANSPORT_PORT = 65535
RELEASE_OBSERVE_SECONDS = 10.0  # same-domain operation deadline (ControlNode discipline)
SETUP_EVENT_KINDS = frozenset(
    ("native_ack", "setup_received", "setup_completed", "setup_rejected", "control_revoked"))


class PlannerTransportNode(Node):
    """One-UAV Route-B transport node bound to one public control epoch."""

    def __init__(self, *, run_id=None, mission_id=None, uav_id=None,
                 fallback_yaw=None, authority_anchor_ns=None,
                 listen_host=None, listen_port=None,
                 transport_session_id=None,
                 accept_control=None, cancel_mode=None,
                 expected_native_mode=None,
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
            "accept_control": False,
            "cancel_mode": "",
            "expected_native_mode": "",
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
            accept_control = parameter("accept_control", accept_control)
            cancel_mode = parameter("cancel_mode", cancel_mode)
            expected_native_mode = parameter(
                "expected_native_mode", expected_native_mode)
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
            if type(accept_control) is not bool:
                raise ValueError("accept_control must be a strict bool")
            if accept_control:
                # Opt-in control mode REQUIRES explicit release targets: the
                # node never guesses an FC type or a release mode.
                self._explicit_text(cancel_mode, "cancel_mode")
                self._explicit_text(expected_native_mode, "expected_native_mode")
                if cancel_mode not in DEFAULT_RELEASE_MODES:
                    raise ValueError(
                        f"cancel_mode must be one of {sorted(DEFAULT_RELEASE_MODES)}")
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
        self.accept_control = accept_control
        self.cancel_mode = cancel_mode
        self.expected_native_mode = expected_native_mode
        self._clock_ns = clock_ns or (lambda: self.get_clock().now().nanoseconds)
        self._clock_is_injected = clock_ns is not None
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
        self._trajectory_halted = False
        self._release_intent = False
        self._release_deadline_ns = None

        topic_root = f"/uav{uav_id}/prometheus"
        self.command_pub = self.create_publisher(
            CommandRequest, topic_root + "/v2/command", 10)
        self.setup_pub = (
            self.create_publisher(SetupRequest, topic_root + "/v2/setup", 10)
            if accept_control else None)
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
        if not self._clock_is_injected and self.get_parameter("use_sim_time").value is not True:
            self._fault("operation_clock_source_changed")
            return None
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
        self._trajectory_halted = False
        self._release_intent = False
        self._release_deadline_ns = None
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
            decoder=BsplineTcpDecoder(
                self.transport_session_id, accept_control=self.accept_control),
            anchor_ns=self.authority_anchor_ns,
            initial_event_sequence=1,
            initial_current_tick=0,
            accept_control=self.accept_control,
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
            setup_publisher=(
                self._publish_setup_envelope if self.accept_control else None),
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
            pending_request_id = None
            if self.egress is not None:
                if self.egress.pending is not None:
                    pending_request_id = self.egress.pending[0]
                elif (self.egress.release is not None
                        and not self.egress.release["confirmed"]):
                    # Correlate the in-flight release setup by its request_id
                    # exactly like a pending command.
                    pending_request_id = self.egress.release["request_id"]
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
                    pending_request_id=pending_request_id,
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

    # ---- publish seams ---------------------------------------------------------
    def _publish_envelope(self, envelope):
        request = build_ros_command_request(
            envelope["command"], run_id=envelope["run_id"],
            control_epoch=envelope["control_epoch"],
            request_id=envelope["request_id"])
        self.command_pub.publish(request)

    def _publish_setup_envelope(self, envelope):
        setup = envelope["setup"]
        request = build_ros_mode_request(
            mode=setup["px4_mode"],
            stamp_ns=setup["stamp_sec"] * 1_000_000_000 + setup["stamp_nanosec"],
            run_id=envelope["run_id"],
            control_epoch=envelope["control_epoch"],
            request_id=envelope["request_id"])
        self.setup_pub.publish(request)

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

    def _handle_activation(self, tick):
        """First publish for one OUTCOME_ACTIVATED at its activation tick."""
        if self.accept_control and not self.pump.output_gate_open:
            # Opt-in mode: an activation must never publish while the planner
            # output gate is closed (fail closed, nothing is fabricated).
            return self._fault("activation_with_gate_closed")
        if not self._state_fresh_and_owned():
            return self._fault("state_not_fresh_or_owned_at_activation")
        try:
            self.egress.step_and_publish(tick, True, True)
        except EgressFault as error:
            return self._fault(error.reason)
        self._trajectory_halted = False
        self._next_drive_tick = tick + SAMPLE_STRIDE_TICKS
        return True

    def on_receive_timer(self):
        if self.fault_reason is not None or self.pump is None:
            return False
        if not self._ensure_connection():
            return False
        tick = self._current_tick()
        if tick is None:
            return False
        gate_open = self.pump.output_gate_open if self.accept_control else True
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
        # The pump has already consumed this batch. Fold its ordered outcomes
        # before publishing, so a later close/stop can suppress an activation
        # from the same batch. Never publish the final adapter twice at one tick.
        publish_activation = False
        for outcome in outcomes:
            if outcome.outcome == OUTCOME_ACTIVATED:
                if not gate_open:
                    return self._fault("activation_with_gate_closed")
                publish_activation = True
                self._trajectory_halted = False
            elif outcome.outcome == "cancel":
                # Planner cancel: halt scheduling NOW, keep any pending
                # command (its ACK is still enforced on the original
                # next-sample boundary), then arm the public release request.
                self._trajectory_halted = True
                self._release_intent = True
                publish_activation = False
            elif outcome.outcome == "gate_open":
                gate_open = True
            elif outcome.outcome == "hold":
                publish_activation = False
                self._trajectory_halted = not gate_open
                if gate_open and self.egress.pending is None and (
                        self._next_drive_tick is None or self._next_drive_tick <= tick):
                    self._next_drive_tick = tick + SAMPLE_STRIDE_TICKS
            elif outcome.outcome in ("gate_closed", "rejected_hold",
                                     "rejected_cancel") or (
                    outcome.outcome == "rejected_identity" and outcome.trajectory_id is None):
                # Halt scheduling; a reopened gate never resumes the old
                # trajectory (a NEW Bspline activation is required), and a
                # rejected control must not leave the prior activation live.
                self._trajectory_halted = True
                publish_activation = False
                if outcome.outcome == "gate_closed":
                    gate_open = False
        if publish_activation and not self._trajectory_halted:
            return self._handle_activation(tick)
        return True

    # ---- drive loop --------------------------------------------------------------
    def _drive_release(self):
        """Advance the public release machine; returns False only on fault.

        The pending command is never cleared to fake a cancellation: the
        release is requested only after its ACK cleared the pending slot.
        The observation deadline is fail-closed; an unconfirmed release is
        never reported as an FC stop.
        """
        if not self._release_intent or self.egress is None:
            return True
        release = self.egress.release
        if release is not None and release["confirmed"]:
            self._release_intent = False
            return True
        if self._release_deadline_ns is not None and self.last_clock_ns > self._release_deadline_ns:
            return self._fault("release_confirmation_deadline_exceeded")
        if release is not None:
            return True  # sent; awaiting the two-phase acknowledgement
        if self.egress.pending is not None:
            return True  # keep the pending command; retry after its ACK
        if not self._state_fresh_and_owned():
            return self._fault("release_state_not_fresh_or_owned")
        try:
            outcome, _envelope = self.egress.request_release(
                mode=self.cancel_mode,
                expected_native_mode=self.expected_native_mode,
                owns_control=True, state_fresh=True)
        except (EgressFault, ValueError) as error:
            return self._fault(f"release_request_failed:{error}")
        if outcome == "busy":
            return True  # raced with a new pending; retry next tick
        self._release_deadline_ns = self.last_clock_ns + int(RELEASE_OBSERVE_SECONDS * 1_000_000_000)
        return True

    def on_drive_timer(self):
        if self.fault_reason is not None or self.egress is None:
            return False
        tick = self._current_tick()
        if tick is None:
            return False
        # The pending-command ACK boundary holds even while halted: an
        # outstanding command must be acked before its next-sample tick.
        if (self._trajectory_halted and self._next_drive_tick is not None
                and tick >= self._next_drive_tick
                and self.egress.pending is not None):
            return self._fault("ack_not_received_before_next_sample")
        if self._trajectory_halted or self._next_drive_tick is None:
            return self._drive_release() if self._release_intent else False
        if tick < self._next_drive_tick:
            return self._drive_release() if self._release_intent else False
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
        return self._drive_release()

    # ---- ACK events -----------------------------------------------------------------
    def on_text_info(self, msg):
        if self.fault_reason is not None or self.egress is None:
            return False
        try:
            event = json.loads(msg.message)
        except (TypeError, ValueError):
            return self._fault("malformed_text_info")
        kind = event.get("event") if isinstance(event, dict) else None
        try:
            if kind in SETUP_EVENT_KINDS and self.egress.release is not None:
                self.egress.on_setup_event(
                    event, msg.message_type,
                    info_value=TextInfo.INFO, error_value=TextInfo.ERROR)
            else:
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
