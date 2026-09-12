"""Pure offline tests for the #102 Route-B ROS1->TCP->receiver prototype.

No ROS, DDS, planner, SITL, UE, MATLAB, native build, wall clock, or external
network.  The transport is exercised over a loopback ``socket.socketpair()``; the
ROS1 sender's conversion core is tested ROS-less via a stand-in message object
(the sender's ``rospy``/``socket`` imports are confined to ``main()``).  Every
frame is produced by the sender's ``encode_bspline_frame`` so the send-side
conversion and the receive-side pump loop are tested together, exactly as Route B
wires them.

IDENTITY DISCIPLINE UNDER TEST (#102 correction): the receiver requires the
COMPLETE caller Identity (planner_generation + command_high_water included) on
every poll/drain and passes it through unchanged.  ``current_identity(pump)`` is
the CALLER explicitly building a current-generation identity from the pump's
public audit property -- the receiver never fills it in.  A stale/future
generation is rejected (``generation_mismatch``) BEFORE any socket recv or
decoder mutation; a missing stable field is a consumed ``rejected_identity``.

Scene geometry under test (committed ego-single-box-v1):
  obstacle AABB  min=(-0.5,-1.0,0.0) max=(0.5,1.0,5.5)
  map bounds     min=(-10,-6,0)      max=(10,6,6)
"""
import inspect
import socket
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SENDER_DIR = REPO_ROOT / "Modules" / "ego_planner_swarm" / "plan_manage" / "scripts"
if str(SENDER_DIR) not in sys.path:
    sys.path.insert(0, str(SENDER_DIR))

import bspline_tcp_sender as sender
from Simulator.wksim_planning.ego_evaluator import UniformBspline
from Simulator.wksim_planning.ego_trajectory_adapter import EgoTrajectoryAdapter
from Simulator.wksim_planning.trajectory_session import TrajectorySession
from Simulator.wksim_runtime.bspline_tcp_envelope import (
    BsplineTcpDecoder,
    BsplineTcpEncoder,
    pack_frame,
    serialize_envelope_json,
)
from Simulator.wksim_runtime.planner_transport_pump import (
    OUTCOME_ACTIVATED,
    OUTCOME_POISON,
    STATE_ACTIVE,
    STATE_POISONED,
    PlannerTransportPump,
    PumpError,
)
from Simulator.wksim_runtime.planner_transport_receiver import (
    NON_CLAIMS as RECEIVER_NON_CLAIMS,
    PlannerTransportReceiver,
    ReceiverError,
)

SESSION_ID = "0123456789abcdef0123456789abcdef"
OTHER_SESSION_ID = "fedcba9876543210fedcba9876543210"
# Stable identity tuple only; the generation and command high-water are supplied
# per call by the caller (see current_identity).
STABLE = dict(run_id="run-a", mission_id="mission-a", uav_id=1, control_epoch="epoch-a")


def current_identity(pump, *, generation=None, command_high_water=None):
    """The CALLER explicitly builds a complete identity carrying the current
    generation / command high-water (read from the pump's public audit
    properties).  The receiver never fills these in; this is the caller's job.
    """
    return dict(
        STABLE,
        planner_generation=pump.session_generation if generation is None else generation,
        command_high_water=pump.command_high_water if command_high_water is None else command_high_water,
    )


def clear_cps():
    """Straight order-3 path at y=3, z=1: clear of the obstacle and inside the map."""
    return [(float(i) * 0.5, 3.0, 1.0) for i in range(7)]


def collision_cps():
    """Straight path at y=0, z=1 crossing the obstacle x-slab: collides."""
    return [(float(i - 3) * 0.5, 0.0, 1.0) for i in range(7)]


class FakeTime:
    """ROS1 ``time`` stand-in: rospy/genpy expose ``secs``/``nsecs``."""
    def __init__(self, secs=0, nsecs=0):
        self.secs = secs
        self.nsecs = nsecs


class FakePoint:
    """``geometry_msgs/Point`` stand-in with x/y/z attributes."""
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z


class FakeBspline:
    """ROS-less stand-in for traj_utils/Bspline exposing the eight schema fields."""
    def __init__(self, cps, *, traj_id=1, secs=0, nsecs=0, order=3, drone_id=0):
        self.drone_id = drone_id
        self.order = order
        self.traj_id = traj_id
        self.start_time = FakeTime(secs, nsecs)
        self.knots = list(UniformBspline(order, cps, 0.1).knots)
        self.pos_pts = [FakePoint(*p) for p in cps]
        self.yaw_pts = []
        self.yaw_dt = 0.0


def make_pump(session_id=SESSION_ID, anchor_ns=0, **pump_kwargs):
    session = TrajectorySession(dict(STABLE, planner_generation=0, command_high_water=0))
    adapter = EgoTrajectoryAdapter(session)
    decoder = BsplineTcpDecoder(session_id)
    pump = PlannerTransportPump(adapter, decoder=decoder, anchor_ns=anchor_ns, **pump_kwargs)
    return session, decoder, pump


def poison_frame_bytes(encoder, *, traj_id):
    """A frame that passes framing but fails the pinned message-hash check."""
    envelope = encoder.build_envelope(sender.build_payload(FakeBspline(clear_cps(), traj_id=traj_id)))
    envelope["ros1_msg_sha256"] = "0" * 64
    return pack_frame(serialize_envelope_json(envelope))


class SenderConversionTests(unittest.TestCase):
    """ROS-less tests for the sender's eight-field -> pinned-envelope core."""

    def test_build_payload_preserves_identity_and_clock(self):
        message = FakeBspline(clear_cps(), traj_id=42, secs=7, nsecs=123456789)
        payload = sender.build_payload(message)
        self.assertEqual(set(payload), set(sender.BSPLINE_FIELDS))
        self.assertEqual(payload["traj_id"], 42)               # verbatim, not reminted
        self.assertEqual(payload["order"], 3)
        self.assertEqual(payload["drone_id"], 0)
        # start_time is passed through unchanged (the object itself), NOT flattened.
        self.assertIs(payload["start_time"], message.start_time)
        self.assertEqual(payload["yaw_pts"], [])
        self.assertEqual(payload["yaw_dt"], 0.0)

    def test_encode_round_trips_through_decoder(self):
        encoder = BsplineTcpEncoder(SESSION_ID)
        decoder = BsplineTcpDecoder(SESSION_ID)
        message = FakeBspline(clear_cps(), traj_id=9, secs=3, nsecs=250000000)
        frame = sender.encode_bspline_frame(encoder, message)
        self.assertIsInstance(frame, (bytes, bytearray))
        decoder.feed(frame)
        mapping = decoder.read_frame()
        self.assertEqual(mapping["traj_id"], 9)
        # The clock is flattened to integer nanoseconds ONLY at the decoder.
        self.assertEqual(mapping["start_time"], 3 * 1_000_000_000 + 250000000)
        self.assertEqual(mapping["pos_pts"][0], (0.0, 3.0, 1.0))
        self.assertEqual(mapping["order"], 3)

    def test_ros1_secs_nsecs_and_sec_nanosec_both_accepted(self):
        # ROS1 time uses secs/nsecs; the ROS2-style sec/nanosec object must also work.
        class Ros2Time:
            def __init__(self):
                self.sec = 1
                self.nanosec = 500000000
        message = FakeBspline(clear_cps(), traj_id=1, secs=1, nsecs=500000000)
        message.start_time = Ros2Time()
        encoder = BsplineTcpEncoder(SESSION_ID)
        decoder = BsplineTcpDecoder(SESSION_ID)
        decoder.feed(sender.encode_bspline_frame(encoder, message))
        self.assertEqual(decoder.read_frame()["start_time"], 1_500_000_000)

    def test_missing_field_rejected(self):
        message = FakeBspline(clear_cps())
        del message.yaw_dt
        with self.assertRaises(ValueError):
            sender.build_payload(message)

    def test_encode_rejects_non_encoder(self):
        with self.assertRaises(ValueError):
            sender.encode_bspline_frame(object(), FakeBspline(clear_cps()))

    def test_ros_imports_confined_to_main(self):
        # The module imported on this ROS-less host, so rospy/traj_utils cannot be
        # top-level imports.  They must live inside main().
        self.assertFalse(hasattr(sender, "rospy"))
        self.assertFalse(hasattr(sender, "socket"))
        main_source = inspect.getsource(sender.main)
        self.assertIn("import rospy", main_source)
        self.assertIn("import socket", main_source)


class ReceiverTransportTests(unittest.TestCase):
    """Route-B receive loop over a loopback socketpair (current-generation caller)."""

    def make_socket_receiver(self, pump):
        write_end, read_end = socket.socketpair()
        self.addCleanup(write_end.close)
        self.addCleanup(read_end.close)
        receiver = PlannerTransportReceiver(pump, connection=read_end)
        return write_end, receiver

    def test_single_frame_activated_over_socket(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1)))
        outcomes = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertTrue(outcomes[0].transport_consumed)
        self.assertTrue(outcomes[0].session_activated)
        self.assertEqual(outcomes[0].event_sequence, 1)
        self.assertEqual(session.generation, 1)
        self.assertEqual(receiver.session_generation, 1)

    def test_fragmented_frame_completes_once_over_socket(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        frame = sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1))
        third = len(frame) // 3
        collected = []
        for chunk in (frame[:third], frame[third:2 * third], frame[2 * third:]):
            write_end.sendall(chunk)
            # The generation is still current until the completing feed activates.
            collected.extend(receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0))
        self.assertEqual([o.outcome for o in collected], [OUTCOME_ACTIVATED])
        self.assertEqual(session.generation, 1)

    def test_multiframe_flushed_across_generation_by_drain(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(
            sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1))
            + sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=2)))
        # One recv carries both frames; only the first activates before the
        # generation advances and the pump stops draining.
        first = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in first], [OUTCOME_ACTIVATED])
        # drain() feeds no new bytes but presents the NEW generation, flushing f2.
        second = receiver.drain(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in second], [OUTCOME_ACTIVATED])
        self.assertEqual([o.trajectory_id for o in first + second], [1, 2])
        self.assertEqual([o.event_sequence for o in first + second], [1, 2])
        self.assertEqual(session.generation, 2)

    def test_collision_rejected_without_activation(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(collision_cps(), traj_id=1)))
        outcomes = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["rejected_clearance"])
        self.assertTrue(outcomes[0].transport_consumed)
        self.assertFalse(outcomes[0].session_activated)
        self.assertEqual(session.generation, 0)

    def test_poison_latches_then_recovers_on_new_session(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        good = sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1))
        write_end.sendall(good + poison_frame_bytes(encoder, traj_id=2))
        # First frame activates; the poison frame stays buffered past the
        # generation advance, so a generation-carrying drain() is what reads it.
        first = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in first], [OUTCOME_ACTIVATED])
        poisoned = receiver.drain(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in poisoned], [OUTCOME_POISON])
        self.assertEqual(receiver.state, STATE_POISONED)
        # Further polls raise BEFORE any blocking recv.
        with self.assertRaises(ReceiverError) as ctx:
            receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual(ctx.exception.reason, "receiver_poisoned")

        # Recovery: NEW socketpair + NEW transport_session_id -> generation + 1.
        new_write, new_read = socket.socketpair()
        self.addCleanup(new_write.close)
        self.addCleanup(new_read.close)
        receiver.recover(new_read, transport_session_id=OTHER_SESSION_ID)
        self.assertEqual(receiver.state, STATE_ACTIVE)
        self.assertEqual(receiver.transport_session_id, OTHER_SESSION_ID)
        self.assertEqual(receiver.session_generation, 2)   # old generation (1) + 1
        new_encoder = BsplineTcpEncoder(OTHER_SESSION_ID)
        new_write.sendall(
            sender.encode_bspline_frame(new_encoder, FakeBspline(clear_cps(), traj_id=10, nsecs=8000000)))
        outcomes = receiver.poll(identity=current_identity(receiver.pump), current_tick=8, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertEqual(receiver.session_generation, 3)

    def test_recovered_receiver_rejects_old_session_frame(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(poison_frame_bytes(encoder, traj_id=1))
        self.assertEqual(
            receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)[0].outcome,
            OUTCOME_POISON)
        new_write, new_read = socket.socketpair()
        self.addCleanup(new_write.close)
        self.addCleanup(new_read.close)
        receiver.recover(new_read, transport_session_id=OTHER_SESSION_ID)
        # A frame from the OLD transport session is poison to the recovered pump.
        stale = BsplineTcpEncoder(SESSION_ID).encode_frame(
            sender.build_payload(FakeBspline(clear_cps(), traj_id=1)))
        new_write.sendall(stale)
        outcomes = receiver.poll(identity=current_identity(receiver.pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_POISON])
        self.assertEqual(outcomes[0].detail, "session_mismatch")


class ReceiverGenerationIsolationTests(unittest.TestCase):
    """The #102 correction: stale/future/missing caller identity, zero consumption."""

    def make_socket_receiver(self, pump):
        write_end, read_end = socket.socketpair()
        self.addCleanup(write_end.close)
        self.addCleanup(read_end.close)
        return write_end, PlannerTransportReceiver(pump, connection=read_end)

    def test_stale_identity_after_activation_rejects_drain_before_consumption(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(
            sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1))
            + sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=2)))
        first = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in first], [OUTCOME_ACTIVATED])   # f1 -> gen 1; f2 buffered
        self.assertEqual(pump.session_generation, 1)
        # The OLD identity (generation 0) is now stale: drain must reject with
        # generation_mismatch and must NOT consume the buffered f2.
        stale = current_identity(pump, generation=0)
        with self.assertRaises(PumpError) as ctx:
            receiver.drain(identity=stale, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(ctx.exception.reason, "generation_mismatch")
        self.assertEqual(pump.session_generation, 1)                       # unchanged
        self.assertEqual(decoder.high_water_sequence, 1)                   # f2 still unread
        # Only after the caller explicitly refreshes may it drain the buffered frame.
        second = receiver.drain(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in second], [OUTCOME_ACTIVATED])
        self.assertEqual([o.trajectory_id for o in second], [2])
        self.assertEqual(pump.session_generation, 2)

    def test_future_generation_rejected_before_socket_recv(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1)))
        # A FUTURE generation (1 > current 0) is rejected BEFORE recv: the frame
        # bytes stay in the socket (no consumption).
        future = current_identity(pump, generation=1)
        with self.assertRaises(PumpError) as ctx:
            receiver.poll(identity=future, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(ctx.exception.reason, "generation_mismatch")
        self.assertEqual(pump.session_generation, 0)
        self.assertEqual(decoder.high_water_sequence, 0)
        # The bytes were not pulled: a current-identity poll receives + activates them.
        outcomes = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertEqual(pump.session_generation, 1)

    def test_stale_generation_poll_rejected_before_socket_recv(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1)))
        receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)   # -> gen 1
        # A new frame arrives; the caller mistakenly still presents the OLD generation 0.
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=2)))
        stale = current_identity(pump, generation=0)
        with self.assertRaises(PumpError) as ctx:
            receiver.poll(identity=stale, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(ctx.exception.reason, "generation_mismatch")
        self.assertEqual(pump.session_generation, 1)
        self.assertEqual(decoder.high_water_sequence, 1)                   # f2 not pulled
        # Bytes survived; the refreshed caller receives and activates f2.
        outcomes = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertEqual([o.trajectory_id for o in outcomes], [2])
        self.assertEqual(pump.session_generation, 2)

    def test_missing_generation_defaults_to_zero_and_is_stale(self):
        # Identity.from_value defaults a missing planner_generation to 0; once the
        # session is past generation 0 that omission is a stale caller.
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1)))
        receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)   # -> gen 1
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=2)))
        missing_gen = dict(STABLE, command_high_water=0)                   # no planner_generation -> 0 (stale)
        with self.assertRaises(PumpError) as ctx:
            receiver.poll(identity=missing_gen, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(ctx.exception.reason, "generation_mismatch")
        self.assertEqual(pump.session_generation, 1)

    def test_missing_stable_field_is_consumed_identity_rejection(self):
        # A missing stable field is NOT a generation error: it falls through to the
        # pump and is recorded as a consumed rejected_identity (two-commit boundary).
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1)))
        no_run_id = dict(mission_id="mission-a", uav_id=1, control_epoch="epoch-a",
                         planner_generation=0, command_high_water=0)
        outcomes = receiver.poll(identity=no_run_id, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["rejected_identity"])
        self.assertTrue(outcomes[0].transport_consumed)                    # frame burned
        self.assertFalse(outcomes[0].session_activated)
        self.assertEqual(pump.session_generation, 0)

    def test_command_high_water_is_telemetry_not_identity_gate(self):
        # command_high_water is carried + range-validated by Identity.from_value but
        # never gated by the session; a non-current in-range value still activates.
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1)))
        identity = current_identity(pump, command_high_water=7)            # telemetry, not gated
        outcomes = receiver.poll(identity=identity, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertEqual(session.generation, 1)

    def test_recover_rejects_old_generation_with_zero_consumption(self):
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(poison_frame_bytes(encoder, traj_id=1))
        self.assertEqual(
            receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)[0].outcome,
            OUTCOME_POISON)
        new_write, new_read = socket.socketpair()
        self.addCleanup(new_write.close)
        self.addCleanup(new_read.close)
        receiver.recover(new_read, transport_session_id=OTHER_SESSION_ID)
        new_generation = receiver.session_generation                       # old(0) + 1 == 1
        self.assertEqual(new_generation, 1)
        # The OLD generation (0) is rejected with zero consumption on the new pump.
        new_encoder = BsplineTcpEncoder(OTHER_SESSION_ID)
        new_write.sendall(
            new_encoder.encode_frame(sender.build_payload(FakeBspline(clear_cps(), traj_id=10, nsecs=8000000))))
        old_identity = current_identity(receiver.pump, generation=new_generation - 1)
        with self.assertRaises(PumpError) as ctx:
            receiver.poll(identity=old_identity, current_tick=8, fallback_yaw=0.0)
        self.assertEqual(ctx.exception.reason, "generation_mismatch")
        self.assertEqual(receiver.session_generation, new_generation)      # unchanged
        # The refreshed caller activates on the new generation.
        outcomes = receiver.poll(identity=current_identity(receiver.pump), current_tick=8, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertEqual(receiver.session_generation, new_generation + 1)


class ReceiverGuardTests(unittest.TestCase):
    def _pair(self):
        write_end, read_end = socket.socketpair()
        self.addCleanup(write_end.close)
        self.addCleanup(read_end.close)
        return write_end, read_end

    def make_socket_receiver(self, pump):
        write_end, read_end = self._pair()
        return write_end, PlannerTransportReceiver(pump, connection=read_end)

    def test_invalid_pump_rejected(self):
        _, read_end = self._pair()
        with self.assertRaises(ReceiverError) as ctx:
            PlannerTransportReceiver(object(), connection=read_end)
        self.assertEqual(ctx.exception.reason, "invalid_pump")

    def test_invalid_socket_rejected(self):
        _, _, pump = make_pump()
        for bad in (None, object(), 123):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(ReceiverError) as ctx:
                    PlannerTransportReceiver(pump, connection=bad)
                self.assertEqual(ctx.exception.reason, "invalid_socket")

    def test_invalid_recv_bytes_rejected(self):
        _, _, pump = make_pump()
        _, read_end = self._pair()
        for bad in (0, -1, True, "x"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ReceiverError) as ctx:
                    PlannerTransportReceiver(pump, connection=read_end, recv_bytes=bad)
                self.assertEqual(ctx.exception.reason, "invalid_socket")

    def test_peer_close_raises_connection_closed(self):
        _, _, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        write_end.close()   # peer closes -> recv returns b""
        with self.assertRaises(ReceiverError) as ctx:
            receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual(ctx.exception.reason, "connection_closed")

    def test_nonblocking_idle_preserves_decoder_and_accepts_next_frame(self):
        _, decoder, pump = make_pump()
        write_end, read_end = self._pair()
        read_end.setblocking(False)
        receiver = PlannerTransportReceiver(pump, connection=read_end)
        self.assertEqual(receiver.poll(identity=current_identity(pump), current_tick=0,
                                       fallback_yaw=0.0), [])
        self.assertEqual(decoder.high_water_sequence, 0)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(encoder.encode_frame(sender.build_payload(FakeBspline(clear_cps()))))
        outcomes = receiver.poll(identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual(outcomes[0].outcome, OUTCOME_ACTIVATED)
        self.assertEqual(decoder.high_water_sequence, 1)

    def test_recover_requires_poisoned(self):
        _, _, pump = make_pump()
        _, receiver = self.make_socket_receiver(pump)
        _, new_read = self._pair()
        with self.assertRaises(ReceiverError) as ctx:
            receiver.recover(new_read, transport_session_id=OTHER_SESSION_ID)
        self.assertEqual(ctx.exception.reason, "not_poisoned")

    def test_pump_protocol_errors_propagate(self):
        # A regressed tick surfaces as the pump's own reason, unchanged.
        session, decoder, pump = make_pump()
        write_end, receiver = self.make_socket_receiver(pump)
        encoder = BsplineTcpEncoder(SESSION_ID)
        write_end.sendall(
            sender.encode_bspline_frame(encoder, FakeBspline(clear_cps(), traj_id=1, nsecs=100000000)))
        receiver.poll(identity=current_identity(pump), current_tick=100, fallback_yaw=0.0)   # start_tick 100
        with self.assertRaises(PumpError) as ctx:
            receiver.drain(identity=current_identity(pump), current_tick=50, fallback_yaw=0.0)   # regressed
        self.assertEqual(ctx.exception.reason, "tick_regressed")

    def test_non_claims_declared_and_no_socket_creation(self):
        text = " ".join(RECEIVER_NON_CLAIMS).lower()
        for token in ("no ack", "no retransmission", "crash atomicity", "exactly-once",
                      "no socket creation", "no wall clock", "no identity rewriting", "flight"):
            self.assertIn(token, text)
        import Simulator.wksim_runtime.planner_transport_receiver as module
        source = inspect.getsource(module)
        # The receiver never imports socket, creates one, or touches ROS.  (The
        # docstring mentions "socket.socketpair()" only as caller-side prose, so
        # that word is not used as a no-socket-creation signal.)
        for forbidden in ("import socket", "from socket", "import rospy", "import rclpy",
                          ".bind(", ".listen(", ".connect("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
