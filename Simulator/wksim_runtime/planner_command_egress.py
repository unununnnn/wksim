"""#102 Route-B egress: TCP-held planner session -> public command intent seam.

This module closes the offline half of the P1 gap located in review 21v: the
Route-B transport chain (sender -> TCP envelope -> receiver -> pump) activates a
:class:`~Simulator.wksim_planning.trajectory_session.TrajectorySession` through
the planner pump, but nothing turned that session's adapter output into the
public command intent that the ROS2 bridge publishes as ``CommandRequest``.

Two pure seams live here so BOTH writers share one implementation:

- :func:`command_fields` -- the single intent -> command-field mapping. The
  ROS2 bridge (:mod:`Simulator.wksim_runtime.trajectory_bridge`) resolves the
  symbolic agent/move/control names to wire constants when it assembles real
  messages; the egress hands the plain field dict to an injected publisher.
- :func:`classify_command_event` -- the single ACK-event classifier (accept /
  reject / revoke / foreign-writer / duplicate). No mutation: the caller owns
  state transitions.

:class:`PlannerCommandEgress` drives the pump-held adapter directly. It NEVER
creates a second session: the adapter it receives is the same object the
caller constructed ``PlannerTransportPump`` with, so
``self._session is adapter.session`` holds by construction and the constructor
asserts it against the identity tuple. The gates are identical to the bridge's:
one pending command, monotonic request/command-id high waters, explicit
tick identity, and ownership/freshness verdicts supplied per step (the
verdict computation from SessionState stays in the ROS layer -- see the next
integration step in the report).

Fail-closed: any gate violation latches ``fault_reason`` and raises
:class:`EgressFault`; a faulted egress never publishes again. This module has
no ROS import and never reads a wall clock; ``now_ns`` comes from an injected
callable so tests and the future wired runtime share one code path.
"""

import math

from numbers import Real

from Simulator.wksim_planning.ego_trajectory_adapter import TICK_NS, EgoTrajectoryAdapter
from Simulator.wksim_planning.trajectory_session import MAX_COMMAND_ID


MAX_REQUEST_ID = 2**64 - 1

FAULT_PREFIX = "fault:"

STATE_STALE_SECONDS = 2.0


def authority_tick(clock_value_ns, anchor_ns, *, tick_ns=TICK_NS):
    """Compute the authoritative authority-grid tick from a clock reading; pure.

    Raises ValueError with the bridge's exact clock-fault reasons. Backwards
    clock detection is the caller's job (it owns the last-reading state).
    """
    if type(clock_value_ns) is not int:
        raise ValueError("invalid_ros_clock")
    if type(anchor_ns) is not int or anchor_ns < 0:
        raise ValueError("invalid_authority_anchor")
    if clock_value_ns < anchor_ns:
        raise ValueError("ros_clock_before_authority_anchor")
    delta = clock_value_ns - anchor_ns
    if delta % tick_ns:
        raise ValueError("ros_clock_off_grid")
    tick = delta // tick_ns
    if tick > 2**63 - 1:
        raise ValueError("authority_tick_overflow")
    return tick


def session_state_fresh_and_owned(*, now_s, published_s, received_s,
                                  received_valid, state_valid,
                                  control_is_command, failsafe,
                                  stale_seconds=STATE_STALE_SECONDS):
    """The 2-second freshness + ownership gate as a pure predicate.

    The caller extracts plain fields from the SessionState message; the wire
    type checks (valid_state, UAVControlState.COMMAND_CONTROL) stay in the ROS
    layer and arrive here as booleans. This is the exact predicate the ROS2
    bridge applies -- it is NOT weakened: both timing windows are inclusive,
    non-finite values fail, and failsafe always blocks.
    """
    return bool(
        isinstance(now_s, Real) and math.isfinite(now_s)
        and isinstance(published_s, Real) and math.isfinite(published_s)
        and 0.0 <= now_s - published_s <= stale_seconds
        and received_valid
        and isinstance(received_s, Real) and math.isfinite(received_s)
        and 0.0 <= now_s - received_s <= stale_seconds
        and state_valid
        and control_is_command
        and not failsafe
    )


def session_state_decision(fields, context):
    """Decide what one SessionState message means; pure, no mutation.

    ``fields``: plain values extracted from the message -- version_ok,
    run_match, control_epoch, epoch_well_formed (32-hex string), state_uav_match,
    control_uav_match, sequence, last_request_id, command_high_water.
    ``context``: retired_epochs (set), current_epoch, current_sequence,
    session_command_high_water, pending_request_id (or None).

    Returns ``(action, detail)`` with action in {'ignore', 'bind', 'update',
    'fault'}; detail is None or the fault reason. Mirrors the ROS2 bridge's
    on_session_state gate order exactly: identity gates -> uint gates ->
    sequence==0 -> epoch change binds before sequence monotonicity -> external
    writer faults.
    """
    if (not fields.get("version_ok") or not fields.get("run_match")
            or not fields.get("epoch_well_formed")
            or fields["control_epoch"] in context["retired_epochs"]
            or not fields.get("state_uav_match")
            or not fields.get("control_uav_match")):
        return "ignore", None
    for name, maximum in (("sequence", MAX_REQUEST_ID),
                          ("last_request_id", MAX_REQUEST_ID),
                          ("command_high_water", MAX_COMMAND_ID)):
        value = fields.get(name)
        if type(value) is not int or not 0 <= value <= maximum:
            return "ignore", None
    sequence = fields["sequence"]
    if sequence == 0:
        return "ignore", None
    if context["current_epoch"] != fields["control_epoch"]:
        return "bind", None
    if sequence <= context["current_sequence"]:
        return "ignore", None
    if fields["command_high_water"] > context["session_command_high_water"]:
        return "fault", "external_command_writer"
    pending = context["pending_request_id"]
    if pending is not None and fields["last_request_id"] > pending:
        return "fault", "external_request_writer"
    return "update", None


class EgressFault(ValueError):
    """A latched, fail-closed egress gate violation."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _explicit_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def command_fields(intent, now_ns):
    """Map one adapter intent to plain command fields; pure, no ROS, no state.

    This is the single mapping used by the ROS2 bridge and the offline egress.
    Symbolic names (MOVE/TRAJECTORY/XYZ_POS/DEFAULT_CONTROL) are resolved to
    wire constants by the caller's message layer.
    """
    if not isinstance(intent, dict):
        raise ValueError("intent must be a dict")
    required = ("intent", "position_ref", "velocity_ref", "acceleration_ref",
                "yaw_ref", "yaw_rate_mode", "yaw_rate_ref", "command_id")
    missing = [name for name in required if name not in intent]
    if missing:
        raise ValueError(f"intent missing fields: {missing}")
    if intent["intent"] not in ("trajectory", "hold"):
        raise ValueError(f"unknown intent kind: {intent['intent']!r}")
    if type(now_ns) is not int or now_ns < 0:
        raise ValueError("now_ns must be a non-negative integer")
    if isinstance(intent["command_id"], bool) or type(intent["command_id"]) is not int:
        raise ValueError("command_id must be an integer")

    def vector(name):
        values = intent[name]
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise ValueError(f"{name} must be a 3-vector")
        out = [float(value) for value in values]
        if not all(math.isfinite(value) for value in out):
            raise ValueError(f"{name} must be finite")
        return out

    yaw = float(intent["yaw_ref"])
    yaw_rate = float(intent["yaw_rate_ref"])
    if not math.isfinite(yaw) or not math.isfinite(yaw_rate):
        raise ValueError("yaw references must be finite")
    return {
        "stamp_sec": now_ns // 1_000_000_000,
        "stamp_nanosec": now_ns % 1_000_000_000,
        "frame_id": "map",
        "agent_cmd": "MOVE",
        "control_level": "DEFAULT_CONTROL",
        "move_mode": "TRAJECTORY" if intent["intent"] == "trajectory" else "XYZ_POS",
        "position_ref": vector("position_ref"),
        "velocity_ref": vector("velocity_ref"),
        "acceleration_ref": vector("acceleration_ref"),
        "yaw_ref": yaw,
        "yaw_rate_mode": bool(intent["yaw_rate_mode"]),
        "yaw_rate_ref": yaw_rate,
        "command_id": int(intent["command_id"]),
    }


def classify_command_event(event, message_type, *, run_id, epoch, pending,
                           last_ack, info_value, error_value):
    """Classify one command ACK event; pure, returns (outcome, pending, last_ack).

    Outcomes: 'ignored', 'duplicate_ack', 'accepted', or 'fault:<reason>'.
    The caller applies state transitions; this function never mutates.
    """
    if type(event) is not dict:
        return "fault:malformed_text_info", pending, last_ack
    if (type(event.get("version")) is not int or event["version"] != 1
            or event.get("run_id") != run_id or event.get("control_epoch") != epoch):
        return "ignored", pending, last_ack
    kind = event.get("event")
    if kind == "control_revoked":
        if message_type != error_value:
            return "fault:text_info_type_mismatch", pending, last_ack
        return "fault:control_revoked", pending, last_ack
    if kind not in ("command_accepted", "command_rejected"):
        return "ignored", pending, last_ack
    request_id = event.get("request_id")
    command_id = event.get("command_id")
    if (last_ack is not None and kind == "command_accepted"
            and (request_id, command_id) == last_ack):
        return "duplicate_ack", pending, last_ack
    if (pending is None or type(request_id) is not int or type(command_id) is not int
            or (request_id, command_id) != pending):
        return "fault:other_command_writer_event", pending, last_ack
    if kind == "command_rejected":
        if message_type != error_value:
            return "fault:text_info_type_mismatch", pending, last_ack
        return "fault:command_rejected", pending, last_ack
    if message_type != info_value:
        return "fault:text_info_type_mismatch", pending, last_ack
    return "accepted", None, (request_id, command_id)


class PlannerCommandEgress:
    """Drive the pump-held adapter and emit public command envelopes.

    The caller constructs one adapter, gives it to ``PlannerTransportPump`` and
    to this egress: both sides operate on the SAME session. The publisher is a
    callable receiving one envelope dict::

        {"run_id": ..., "control_epoch": ..., "request_id": ...,
         "command": <command_fields(...) dict>}

    Message assembly (ROS2 ``CommandRequest``/``UAVCommand``) belongs to the
    publisher's owner; the ROS2 bridge uses the same :func:`command_fields`
    mapping, so the wire shape cannot diverge between the two writers.
    """

    def __init__(self, adapter, publisher, *, run_id, mission_id, uav_id,
                 control_epoch, clock_ns, initial_request_high_water=0):
        if not isinstance(adapter, EgoTrajectoryAdapter):
            raise ValueError("adapter must be an EgoTrajectoryAdapter")
        if not callable(publisher):
            raise ValueError("publisher must be callable")
        if not callable(clock_ns):
            raise ValueError("clock_ns must be callable")
        _explicit_text(run_id, "run_id")
        _explicit_text(mission_id, "mission_id")
        _explicit_text(control_epoch, "control_epoch")
        if type(uav_id) is not int or uav_id < 0:
            raise ValueError("uav_id must be a non-negative integer")
        if (type(initial_request_high_water) is not int
                or not 0 <= initial_request_high_water <= MAX_REQUEST_ID):
            raise ValueError("initial_request_high_water must be in [0, 2**64-1]")
        session = adapter.session  # public attribute; never a second session
        identity = session.identity
        if (identity.run_id, identity.mission_id, identity.uav_id,
                identity.control_epoch) != (run_id, mission_id, uav_id, control_epoch):
            raise ValueError("adapter session identity differs from the egress binding")
        self._adapter = adapter
        self._session = session
        self._publisher = publisher
        self._clock_ns = clock_ns
        self._run_id = run_id
        self._control_epoch = control_epoch
        self._request_high_water = initial_request_high_water
        self._pending = None          # (request_id, command_id) or None
        self._last_ack = None
        self._fault_reason = None

    @property
    def session(self):
        """The shared pump session (same object the pump holds)."""
        return self._session

    @property
    def fault_reason(self):
        return self._fault_reason

    @property
    def request_high_water(self):
        return self._request_high_water

    @property
    def pending(self):
        return self._pending

    @property
    def last_ack(self):
        return self._last_ack

    def _identity(self):
        return dict(
            run_id=self._run_id,
            mission_id=self._session.identity.mission_id,
            uav_id=self._session.identity.uav_id,
            control_epoch=self._control_epoch,
            planner_generation=self._session.generation,
            command_high_water=self._session.last_command_id,
        )

    def _fault(self, reason):
        if self._fault_reason is None:
            self._fault_reason = reason
        raise EgressFault(reason)

    def step_and_publish(self, tick, owns_control, state_fresh):
        """Advance the shared adapter one tick and publish the resulting intent.

        Gate order mirrors the ROS2 bridge: faulted -> pending single ->
        request/command high-water caps -> adapter.step (which owns identity,
        tick monotonicity, and the owns_control/state_fresh safety path) ->
        mapping -> publish. Returns the published envelope dict.
        """
        if self._fault_reason is not None:
            raise EgressFault(self._fault_reason)
        if type(tick) is not int:
            raise ValueError("tick must be an integer")
        if self._pending is not None:
            self._fault("multiple_pending_commands")
        if self._request_high_water >= MAX_REQUEST_ID:
            self._fault("request_id_exhausted")
        if self._session.last_command_id >= MAX_COMMAND_ID:
            self._fault("command_id_exhausted")
        try:
            intent = self._adapter.step(
                self._identity(), tick, owns_control, state_fresh)
        except EgressFault:
            raise
        except Exception as error:
            self._fault(f"adapter_step_failed:{error}")
        if intent is None:
            self._fault("missing_trajectory_intent")
        now_ns = self._clock_ns()
        if type(now_ns) is not int or now_ns < 0:
            self._fault("invalid_clock")
        try:
            fields = command_fields(intent, now_ns)
        except (ValueError, OverflowError) as error:
            self._fault(f"command_fields_invalid:{error}")
        self._request_high_water += 1
        envelope = {
            "run_id": self._run_id,
            "control_epoch": self._control_epoch,
            "request_id": self._request_high_water,
            "command": fields,
        }
        self._pending = (envelope["request_id"], fields["command_id"])
        try:
            self._publisher(envelope)
        except Exception as error:
            self._fault(f"command_publish_failed:{error}")
        return envelope

    def on_command_event(self, event, message_type, *, info_value, error_value):
        """Apply one control-side ACK event through the shared classifier.

        Returns the outcome string. A 'fault:<reason>' outcome latches the
        egress fault and raises :class:`EgressFault`.
        """
        if self._fault_reason is not None:
            raise EgressFault(self._fault_reason)
        outcome, pending, last_ack = classify_command_event(
            event, message_type, run_id=self._run_id, epoch=self._control_epoch,
            pending=self._pending, last_ack=self._last_ack,
            info_value=info_value, error_value=error_value)
        self._pending = pending
        self._last_ack = last_ack
        if outcome.startswith(FAULT_PREFIX):
            self._fault(outcome[len(FAULT_PREFIX):])
        return outcome
