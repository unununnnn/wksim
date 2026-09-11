"""Pure offline receive loop for the #102 Route-B Bspline TCP transport.

This module owns the smallest receive-side socket loop that turns a pinned
``wksim.bspline-tcp-envelope.v1`` byte stream into scene-admitted trajectories.
It sits between a connected socket -- the ONLY thing borrowed from the operating
system -- and the committed receive-side pump
(``Simulator/wksim_runtime/planner_transport_pump.py``):

    connection.recv() -> PlannerTransportPump.feed(identity=caller_identity) -> list[FrameOutcome]

It is pure with respect to ROS/DDS/SITL/UE/MATLAB/native builds: the socket is
INJECTED by the caller (a loopback ``socket.socketpair()`` in tests, a real
accepted TCP connection in deployment).  This module never imports ``socket``,
never binds/listens/connects, never reads a wall clock, and never mints an
identifier -- it only calls ``.recv()`` on the injected connection.

IDENTITY DISCIPLINE (the #102 critical correction, restated for this layer):
  The caller MUST supply the COMPLETE ``Identity`` -- including
  ``planner_generation`` and ``command_high_water`` -- on EVERY ``poll``/``drain``.
  The receiver passes that identity to the pump UNCHANGED.  It NEVER reads the
  pump's current ``session_generation``/``command_high_water`` to fill in or
  overwrite the caller's identity: doing so would be auto-stamping and would
  re-break the stale-caller isolation the pump's generation gate exists to
  provide.

  The pump rejects a stale/future ``planner_generation`` (``generation_mismatch``)
  BEFORE the decoder consumes a byte.  To honor that boundary at the socket
  layer, ``poll`` applies the SAME generation gate BEFORE calling ``recv()`` --
  otherwise a stale caller's ``recv`` would pull bytes off the socket that the
  pump then refuses, silently dropping them.  This pre-check reads the pump's
  current generation ONLY to REJECT a mismatch (isolation), never to write it
  into the caller's identity.  It mirrors the pump's pre-consumption gate
  exactly: a well-formed identity with a non-current generation (or a numerically
  explicit out-of-range generation) is refused with ``generation_mismatch``
  before any recv/decoder mutation, while a malformed or stable-tuple-mismatched
  identity falls through to the pump, which preserves the two-commit boundary by
  recording it as a consumed ``rejected_identity``.

  After an activation advances the session generation, the caller's previous
  identity is stale: any next ``poll``/``drain`` presenting it raises
  ``generation_mismatch`` with ZERO socket recv and ZERO decoder mutation.  Only
  after the caller explicitly refreshes to the new generation may it drain a
  buffered frame.  After ``recover`` the old generation is likewise rejected with
  zero consumption.  ``command_high_water`` is telemetry, not an identity gate:
  ``Identity.from_value`` range-validates it and the session uses it only to
  initialize its command counter at construction, so the receiver passes it
  through verbatim and never gates on it.

TRANSACTION / DELIVERY NON-CLAIMS (inherited from the pump, restated):
  The transport is fire-and-forget: there is NO ACK, NO retransmission, NO
  back-pressure, and NO feedback path to the sender.  The pump's two-commit
  boundary is inherited unchanged (``read_frame()`` commits the transport
  sequence BEFORE admission runs, so a frame can be transport-consumed yet never
  activate the session).  There is NO crash atomicity and NO exactly-once
  guarantee.  A poisoned pump latches terminal ``POISONED``; the ONLY recovery is
  a NEW connection on a NEW ``transport_session_id`` via :meth:`recover`.  This
  module does not drive the control/execution path (no ``step``/command output)
  and produces no flight evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, List

from Simulator.wksim_planning.trajectory_session import (
    MAX_GENERATION,
    Identity,
)
from Simulator.wksim_runtime.planner_transport_pump import (
    FrameOutcome,
    PlannerTransportPump,
    PumpError,
    STATE_POISONED,
)

DEFAULT_RECV_BYTES = 65536

RECEIVER_REASONS = (
    "invalid_pump",
    "invalid_socket",
    "connection_closed",
    "receiver_poisoned",
    "not_poisoned",
)

NON_CLAIMS = (
    "no ACK, no retransmission, no back-pressure, no feedback path to the sender",
    "no crash atomicity and no exactly-once delivery; the pump's two-commit "
    "boundary is inherited unchanged",
    "no socket creation: the connection is injected; this module never imports "
    "socket, binds, listens, or connects",
    "no wall clock; current_tick is caller-supplied per call and only bounded / "
    "non-regression-checked by the pump",
    "no identifier minting and no identity rewriting: the caller supplies the "
    "complete Identity (planner_generation and command_high_water included) on "
    "every call and the receiver passes it through unchanged; the pump's current "
    "generation is read only to REJECT a stale/future caller, never to fill it in",
    "does not drive the control/execution path and produces no flight evidence",
)


class ReceiverError(ValueError):
    """A stable reason-coded receiver rejection raised before any state change."""

    def __init__(self, reason: str, message: str = ""):
        if reason not in RECEIVER_REASONS:
            raise ValueError(f"unknown receiver error reason: {reason!r}")
        super().__init__(f"[{reason}] {message}" if message else reason)
        self.reason = reason
        self.message = message


class PlannerTransportReceiver:
    """Drive an injected socket through the receive-side pump, one feed per call.

    The receiver owns no socket lifecycle, no clock, and no identity: the caller
    injects a connected socket and supplies the COMPLETE ``identity`` plus
    ``current_tick`` / ``fallback_yaw`` on every ``poll``/``drain``.  Pump protocol
    errors (``PumpError``: ``generation_mismatch``, ``generation_exhausted``,
    ``sequence_exhausted``, ``invalid_tick``, ``tick_regressed``) propagate
    unchanged so the caller sees the exact pump reason; receiver-level conditions
    are reported as :class:`ReceiverError`.
    """

    def __init__(self, pump: PlannerTransportPump, *, connection: Any,
                 recv_bytes: int = DEFAULT_RECV_BYTES):
        if not isinstance(pump, PlannerTransportPump):
            raise ReceiverError("invalid_pump", "pump must be a PlannerTransportPump")
        self._check_connection(connection, "connection")
        if isinstance(recv_bytes, bool) or type(recv_bytes) is not int or recv_bytes <= 0:
            raise ReceiverError("invalid_socket", "recv_bytes must be a positive integer")
        self._pump = pump
        self._connection = connection
        self._recv_bytes = recv_bytes

    # ---- construction helpers --------------------------------------------
    @staticmethod
    def _check_connection(connection: Any, name: str) -> None:
        if connection is None or not callable(getattr(connection, "recv", None)):
            raise ReceiverError("invalid_socket", f"{name} must expose a callable recv()")

    # ---- read-only audit ---------------------------------------------------
    @property
    def pump(self) -> PlannerTransportPump:
        return self._pump

    @property
    def state(self) -> str:
        return self._pump.state

    @property
    def session_generation(self) -> int:
        return self._pump.session_generation

    @property
    def transport_session_id(self) -> str:
        return self._pump.transport_session_id

    # ---- identity gate -----------------------------------------------------
    def _require_current_identity(self, identity: Any) -> None:
        """Reject a stale/future caller generation BEFORE any recv/decoder mutation.

        This mirrors the pump's pre-consumption generation gate (see
        ``PlannerTransportPump._check_feed_identity``) so a stale caller is refused
        WITHOUT pulling bytes off the socket.  It reads the pump's current
        generation ONLY to reject a mismatch -- it never writes that value into the
        caller's identity (that would be auto-stamping).  A malformed or
        stable-tuple-mismatched identity is NOT pre-rejected here: it falls through
        to the pump, which records it as a consumed ``rejected_identity`` so the
        two-commit boundary is preserved.
        """
        try:
            candidate = Identity.from_value(identity)
        except ValueError:
            raw_generation = identity.get("planner_generation") if isinstance(identity, Mapping) else None
            if type(raw_generation) is int and not 0 <= raw_generation <= MAX_GENERATION:
                raise PumpError(
                    "generation_mismatch",
                    "caller planner_generation is outside the supported range")
            return
        if candidate.planner_generation != self._pump.session_generation:
            raise PumpError(
                "generation_mismatch",
                "caller planner_generation must equal the current session generation")

    # ---- receive loop ------------------------------------------------------
    def poll(self, *, identity: Any, current_tick: int, fallback_yaw: float) -> List[FrameOutcome]:
        """recv one chunk and feed it under the caller-supplied ``identity``.

        The poison latch and the caller-generation gate are both checked BEFORE
        the (possibly blocking) ``recv`` so a poisoned receiver never blocks, and
        a stale caller never pulls bytes the pump would refuse.  A clean peer
        close (``recv`` returns ``b""``) raises ``connection_closed``.
        """
        if self._pump.state == STATE_POISONED:
            raise ReceiverError(
                "receiver_poisoned",
                "pump is poisoned; call recover() with a NEW transport_session_id")
        self._require_current_identity(identity)
        try:
            chunk = self._connection.recv(self._recv_bytes)
        except OSError as error:
            raise ReceiverError("invalid_socket", f"recv failed: {error}") from error
        if not isinstance(chunk, (bytes, bytearray)):
            raise ReceiverError("invalid_socket", "recv() must return bytes")
        if len(chunk) == 0:
            raise ReceiverError("connection_closed", "peer closed the connection")
        return self._pump.feed(
            chunk, identity=identity, current_tick=current_tick, fallback_yaw=fallback_yaw)

    def drain(self, *, identity: Any, current_tick: int, fallback_yaw: float) -> List[FrameOutcome]:
        """Feed no new bytes so the pump flushes generation-held buffered frames.

        After an activation advances the session generation, a frame that arrived
        in the same chunk stays buffered (the pump stops draining before the next
        ``read_frame()``).  ``drain()`` performs the follow-up feed under the
        caller-supplied ``identity`` WITHOUT a ``recv``; the generation gate runs
        first, so a stale caller cannot flush the held frame.
        """
        if self._pump.state == STATE_POISONED:
            raise ReceiverError(
                "receiver_poisoned",
                "pump is poisoned; call recover() with a NEW transport_session_id")
        self._require_current_identity(identity)
        return self._pump.feed(
            b"", identity=identity, current_tick=current_tick, fallback_yaw=fallback_yaw)

    # ---- recovery ----------------------------------------------------------
    def recover(self, new_connection: Any, *, transport_session_id: str) -> PlannerTransportPump:
        """Recover from poison on a NEW connection + NEW ``transport_session_id``.

        Only defined while poisoned (``not_poisoned`` otherwise).  Builds a new
        pump via ``PlannerTransportPump.recover`` (new transport session, planner
        generation + 1, command high-water preserved) and swaps the connection.
        The pump's own recovery errors (``invalid_session_id``, ``session_reuse``,
        ``generation_exhausted``) propagate unchanged.  The caller's identity is
        untouched here; the OLD generation is rejected with zero consumption on
        the next ``poll``/``drain``.
        """
        if self._pump.state != STATE_POISONED:
            raise ReceiverError("not_poisoned", "recover is only defined for a poisoned receiver")
        self._check_connection(new_connection, "new_connection")
        self._pump = PlannerTransportPump.recover(
            self._pump, transport_session_id=transport_session_id)
        self._connection = new_connection
        return self._pump
