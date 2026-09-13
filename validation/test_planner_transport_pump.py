"""Pure offline tests for the #102/#39 receive-side planner transport pump.

No socket, ROS, DDS, planner, SITL, UE, MATLAB, native build, or wall clock.  Bytes
are produced in-memory by the committed BsplineTcpEncoder and fed explicitly.  The
pump drives the public BsplineTcpDecoder.read_frame() (which commits the transport
sequence FIRST) and then the scene-admission gate, recording the two-commit
boundary explicitly on every frame: transport_consumed vs session_activated.

Scene geometry under test (committed ego-single-box-v1):
  obstacle AABB  min=(-0.5,-1.0,0.0) max=(0.5,1.0,5.5)
  map bounds     min=(-10,-6,0)      max=(10,6,6)
"""
import unittest

from Simulator.wksim_planning.ego_evaluator import UniformBspline
from Simulator.wksim_planning.ego_trajectory_adapter import (
    AdapterError,
    EgoTrajectoryAdapter,
    MAX_TICK,
)
from Simulator.wksim_planning.trajectory_session import (
    Identity,
    MAX_COMMAND_ID,
    MAX_GENERATION,
    TrajectorySession,
)
from Simulator.wksim_runtime.bspline_tcp_envelope import (
    BsplineTcpDecoder,
    BsplineTcpEncoder,
    pack_frame,
    serialize_envelope_json,
)
from Simulator.wksim_runtime.planner_transport_pump import (
    NON_CLAIMS,
    OUTCOME_ACTIVATED,
    OUTCOME_POISON,
    STATE_ACTIVE,
    STATE_POISONED,
    FrameOutcome,
    PlannerTransportPump,
    PumpError,
)

SESSION_ID = "0123456789abcdef0123456789abcdef"
OTHER_SESSION_ID = "fedcba9876543210fedcba9876543210"
IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1, control_epoch="epoch-a",
                planner_generation=0, command_high_water=0)


class ExplodingIdentityMapping(dict):
    """Mapping whose parser access fails like an untrusted external adapter."""

    def get(self, key, default=None):
        raise TypeError("identity mapping access failed")


class RaisingIdentityMapping(dict):
    """Mapping that lets the tests pin the parser exception boundary."""

    def __init__(self, error):
        super().__init__(IDENTITY)
        self._error = error

    def get(self, key, default=None):
        raise self._error


def clear_cps():
    """Straight order-3 path at y=3, z=1: clear of the obstacle and inside the map."""
    return [(float(i) * 0.5, 3.0, 1.0) for i in range(7)]


def collision_cps():
    """Straight path at y=0, z=1 crossing the obstacle x-slab: collides."""
    return [(float(i - 3) * 0.5, 0.0, 1.0) for i in range(7)]


def make_payload(cps, *, traj_id=1, sec=0, nanosec=0, order=3, drone_id=0):
    """A valid raw Bspline payload for the encoder (ROS1-relay input shape)."""
    return {
        "drone_id": drone_id,
        "order": order,
        "traj_id": traj_id,
        "start_time": {"sec": sec, "nanosec": nanosec},
        "knots": list(UniformBspline(order, cps, 0.1).knots),
        "pos_pts": [tuple(p) for p in cps],
        "yaw_pts": [],
        "yaw_dt": 0.0,
    }


def make_pump(session_id=SESSION_ID, anchor_ns=0, **kwargs):
    session = TrajectorySession(dict(IDENTITY))
    adapter = EgoTrajectoryAdapter(session)
    decoder = BsplineTcpDecoder(session_id)
    pump = PlannerTransportPump(adapter, decoder=decoder, anchor_ns=anchor_ns, **kwargs)
    return session, adapter, decoder, pump


def current_identity(pump):
    return dict(IDENTITY, planner_generation=pump.session_generation,
                command_high_water=pump.command_high_water)


def poison_frame(encoder, *, traj_id):
    """A frame that passes framing but fails the pinned message-hash check."""
    envelope = encoder.build_envelope(make_payload(clear_cps(), traj_id=traj_id))
    envelope["ros1_msg_sha256"] = "0" * 64
    return pack_frame(serialize_envelope_json(envelope))


def pump_snapshot(pump):
    return (pump.state, pump.next_event_sequence, pump.last_current_tick,
            pump.session_generation, pump.command_high_water)


class PumpReceiveTests(unittest.TestCase):
    def assert_pump_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(PumpError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_single_frame_activated(self):
        session, adapter, decoder, pump = make_pump()
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(make_payload(clear_cps(), traj_id=1))
        outcomes = pump.feed(frame, identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        self.assertEqual(outcome.outcome, OUTCOME_ACTIVATED)
        self.assertTrue(outcome.transport_consumed)
        self.assertTrue(outcome.session_activated)
        self.assertEqual(outcome.transport_sequence, 1)
        self.assertEqual(outcome.trajectory_id, 1)
        self.assertEqual(outcome.event_sequence, 1)
        self.assertEqual((session.state, session.generation, session.last_event_sequence),
                         ("ACTIVE", 1, 1))
        self.assertEqual(adapter.trajectory_id, 1)

    def test_fragmented_frame_completes_once(self):
        session, adapter, decoder, pump = make_pump()
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(make_payload(clear_cps(), traj_id=1))
        # Split the frame into three arbitrary chunks.
        third = len(frame) // 3
        chunks = [frame[:third], frame[third:2 * third], frame[2 * third:]]
        collected = []
        for chunk in chunks:
            collected.extend(pump.feed(chunk, identity=IDENTITY, current_tick=0, fallback_yaw=0.0))
        # Only the completing feed yields an outcome, exactly once.
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0].outcome, OUTCOME_ACTIVATED)
        self.assertEqual(session.generation, 1)

    def test_multiple_frames_processed_in_transport_order(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        f1 = encoder.encode_frame(make_payload(clear_cps(), traj_id=1))
        f2 = encoder.encode_frame(make_payload(clear_cps(), traj_id=2))
        outcomes = pump.feed(f1 + f2, identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        outcomes += pump.feed(b"", identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED, OUTCOME_ACTIVATED])
        self.assertEqual([o.transport_sequence for o in outcomes], [1, 2])
        self.assertEqual([o.trajectory_id for o in outcomes], [1, 2])
        self.assertEqual([o.event_sequence for o in outcomes], [1, 2])
        self.assertEqual((session.generation, session.last_event_sequence), (2, 2))

    def test_clearance_reject_makes_two_commit_gap_explicit(self):
        session, adapter, decoder, pump = make_pump()
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(make_payload(collision_cps(), traj_id=1))
        outcomes = pump.feed(frame, identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        # The transport committed (sequence burned) but the session did NOT activate.
        self.assertEqual(outcome.outcome, "rejected_clearance")
        self.assertTrue(outcome.transport_consumed)
        self.assertFalse(outcome.session_activated)
        self.assertIsNone(outcome.event_sequence)              # no event_sequence spent
        self.assertEqual(outcome.transport_sequence, 1)
        self.assertEqual(outcome.trajectory_id, 1)
        self.assertIsNotNone(outcome.report)                   # honest evidence attached
        self.assertEqual((session.state, session.generation, session.last_event_sequence),
                         ("WAITING", 0, None))                 # session untouched
        self.assertEqual(pump.next_event_sequence, 1)          # not burned

    def test_bridge_and_identity_rejects_are_recorded_without_activation(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        # order=2 passes the envelope (order>0) but the bridge rejects it.
        bad_order = encoder.encode_frame(make_payload(clear_cps(), traj_id=1, order=2))
        outcomes = pump.feed(bad_order, identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(outcomes[0].outcome, "rejected_bridge")
        self.assertEqual(outcomes[0].detail, "bridge_rejected:unsupported_order")
        self.assertTrue(outcomes[0].transport_consumed)
        self.assertFalse(outcomes[0].session_activated)
        # Identity mismatch (wrong stable tuple) is likewise consumed-but-not-activated.
        good = BsplineTcpEncoder(SESSION_ID)  # new session stream not needed; reuse seq 2
        frame2 = encoder.encode_frame(make_payload(clear_cps(), traj_id=2))
        outcomes2 = pump.feed(frame2, identity=dict(IDENTITY, run_id="other"),
                              current_tick=0, fallback_yaw=0.0)
        self.assertEqual(outcomes2[0].outcome, "rejected_identity")
        self.assertFalse(outcomes2[0].session_activated)
        self.assertEqual((session.generation, session.last_event_sequence), (0, None))

    def test_malformed_identity_rejection_is_two_commit(self):
        malformed = [
            {"run_id": "run-a", "mission_id": "mission-a", "control_epoch": "epoch-a"},
            {"mission_id": "mission-a", "uav_id": 1, "control_epoch": "epoch-a"},
            "not-a-mapping",
            ExplodingIdentityMapping(),
        ]
        for identity in malformed:
            with self.subTest(identity=type(identity).__name__):
                session, adapter, decoder, pump = make_pump()
                frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
                    make_payload(clear_cps(), traj_id=1))
                outcomes = pump.feed(frame, identity=identity, current_tick=0, fallback_yaw=0.0)
                self.assertEqual(len(outcomes), 1)
                outcome = outcomes[0]
                self.assertEqual(outcome.outcome, "rejected_identity")
                self.assertTrue(outcome.transport_consumed)
                self.assertFalse(outcome.session_activated)
                self.assertIsNone(outcome.event_sequence)
                self.assertEqual(decoder.high_water_sequence, 1)
                self.assertEqual((session.generation, session.last_event_sequence,
                                  adapter.trajectory_id, pump.next_event_sequence),
                                 (0, None, 0, 1))

    def test_identity_parser_exception_boundary_is_explicit(self):
        frame_factory = lambda: BsplineTcpEncoder(SESSION_ID).encode_frame(
            make_payload(clear_cps(), traj_id=1))
        for error in (ValueError("bad value"), KeyError("missing"), TypeError("bad type")):
            with self.subTest(error=type(error).__name__):
                session, adapter, decoder, pump = make_pump()
                outcome = pump.feed(
                    frame_factory(), identity=RaisingIdentityMapping(error),
                    current_tick=0, fallback_yaw=0.0)[0]
                self.assertEqual(outcome.outcome, "rejected_identity")
                self.assertTrue(outcome.transport_consumed)
                self.assertFalse(outcome.session_activated)
                self.assertEqual(decoder.high_water_sequence, 1)
                self.assertEqual((session.generation, session.last_event_sequence,
                                  adapter.trajectory_id, pump.next_event_sequence),
                                 (0, None, 0, 1))

        for error in (MemoryError("allocation"), RuntimeError("parser bug")):
            with self.subTest(error=type(error).__name__):
                session, adapter, decoder, pump = make_pump()
                before = pump_snapshot(pump)
                with self.assertRaises(type(error)):
                    pump.feed(
                        frame_factory(), identity=RaisingIdentityMapping(error),
                        current_tick=0, fallback_yaw=0.0)
                self.assertEqual(pump_snapshot(pump), before)
                self.assertEqual(decoder.high_water_sequence, 0)
                self.assertEqual((session.generation, session.last_event_sequence,
                                  adapter.trajectory_id, pump.next_event_sequence),
                                 (0, None, 0, 1))

    def test_malformed_identity_with_out_of_range_generation_is_pre_decoder_error(self):
        session, adapter, decoder, pump = make_pump()
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
            make_payload(clear_cps(), traj_id=1))
        identity = {"run_id": "run-a", "mission_id": "mission-a",
                    "control_epoch": "epoch-a", "planner_generation": MAX_GENERATION + 1}
        before = pump_snapshot(pump)
        self.assert_pump_error("generation_mismatch", pump.feed, frame,
                               identity=identity, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(pump_snapshot(pump), before)
        self.assertEqual(decoder.high_water_sequence, 0)

    def test_identity_object_generation_is_checked_pre_decoder(self):
        for generation in (MAX_GENERATION + 1, -1, 1):
            with self.subTest(generation=generation):
                session, adapter, decoder, pump = make_pump()
                frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
                    make_payload(clear_cps(), traj_id=1))
                identity = Identity("run-a", "mission-a", 1, "epoch-a", generation, 0)
                before = pump_snapshot(pump)
                self.assert_pump_error(
                    "generation_mismatch", pump.feed, frame, identity=identity,
                    current_tick=0, fallback_yaw=0.0)
                self.assertEqual(pump_snapshot(pump), before)
                self.assertEqual(decoder.high_water_sequence, 0)
                self.assertEqual((session.generation, session.last_event_sequence,
                                  adapter.trajectory_id, pump.next_event_sequence),
                                 (0, None, 0, 1))

    def test_invalid_fallback_is_two_commit_adapter_rejection(self):
        session, adapter, decoder, pump = make_pump()
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
            make_payload(clear_cps(), traj_id=1))
        before = pump_snapshot(pump)
        outcome = pump.feed(frame, identity=IDENTITY, current_tick=0,
                            fallback_yaw=float("nan"))[0]
        self.assertEqual(outcome.outcome, "rejected_adapter")
        self.assertTrue(outcome.transport_consumed)
        self.assertFalse(outcome.session_activated)
        self.assertIsNone(outcome.event_sequence)
        self.assertEqual(decoder.high_water_sequence, 1)
        self.assertEqual(pump_snapshot(pump), before)
        self.assertEqual((session.generation, session.last_event_sequence,
                          adapter.trajectory_id, pump.next_event_sequence),
                         (0, None, 0, 1))

    def test_adapter_reject_on_nonincreasing_trajectory_id(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        pump.feed(encoder.encode_frame(make_payload(clear_cps(), traj_id=5)),
                  identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        before = pump_snapshot(pump)
        # A reused trajectory_id passes transport + scene but the adapter rejects it.
        outcomes = pump.feed(encoder.encode_frame(make_payload(clear_cps(), traj_id=5)),
                             identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual(outcomes[0].outcome, "rejected_adapter")
        self.assertTrue(outcomes[0].transport_consumed)
        self.assertFalse(outcomes[0].session_activated)
        self.assertIsNone(outcomes[0].event_sequence)
        # Session advanced only by the first activation; the reject changed nothing.
        self.assertEqual(pump_snapshot(pump), before)

    def test_event_sequence_spent_only_on_activation(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        f1 = encoder.encode_frame(make_payload(clear_cps(), traj_id=1))
        f2 = encoder.encode_frame(make_payload(collision_cps(), traj_id=2))   # scene reject
        f3 = encoder.encode_frame(make_payload(clear_cps(), traj_id=3))
        outcomes = pump.feed(f1 + f2 + f3, identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        outcomes += pump.feed(b"", identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED, "rejected_clearance", OUTCOME_ACTIVATED])
        outcomes += pump.feed(b"", identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.event_sequence for o in outcomes], [1, None, 2])
        self.assertEqual([o.transport_sequence for o in outcomes], [1, 2, 3])
        self.assertEqual(pump.next_event_sequence, 3)
        # Session event sequence is contiguous (no gap from the rejected frame).
        self.assertEqual(session.last_event_sequence, 2)
        self.assertEqual(session.generation, 2)


class PumpPoisonRecoveryTests(unittest.TestCase):
    def assert_pump_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(PumpError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_poison_latches_and_refuses_further_bytes(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        good = encoder.encode_frame(make_payload(clear_cps(), traj_id=1))       # seq 1
        poison = poison_frame(encoder, traj_id=2)                                # seq 2, bad hash
        outcomes = pump.feed(good + poison, identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        outcomes += pump.feed(b"", identity=current_identity(pump), current_tick=0, fallback_yaw=0.0)
        # Good frame admitted; poison recorded but NOT consumed (transport seq frozen).
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED, OUTCOME_POISON])
        self.assertEqual(outcomes[0].transport_sequence, 1)
        self.assertIsNone(outcomes[1].transport_sequence)
        self.assertFalse(outcomes[1].transport_consumed)
        self.assertFalse(outcomes[1].session_activated)
        self.assertEqual(outcomes[1].detail, "hash_mismatch")
        self.assertEqual(pump.state, STATE_POISONED)
        # Decoder head-of-line: high-water frozen at 1, poisoned frame still blocking.
        self.assertEqual(decoder.high_water_sequence, 1)
        self.assertEqual(decoder.expected_sequence, 2)
        # Further bytes are refused with no state change.
        before = pump_snapshot(pump)
        self.assert_pump_error("poisoned", pump.feed, b"\x00\x00\x00\x00",
                               identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(pump_snapshot(pump), before)

    def test_recover_builds_new_session_and_decoder(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        pump.feed(encoder.encode_frame(make_payload(clear_cps(), traj_id=1)),
                  identity=IDENTITY, current_tick=7, fallback_yaw=0.0)
        pump.feed(poison_frame(encoder, traj_id=2), identity=IDENTITY, current_tick=7,
                  fallback_yaw=0.0)
        self.assertEqual(pump.state, STATE_POISONED)
        old_generation = pump.session_generation
        old_hw = pump.command_high_water
        old_next_es = pump.next_event_sequence

        new_pump = PlannerTransportPump.recover(pump, transport_session_id=OTHER_SESSION_ID)
        self.assertEqual(new_pump.state, STATE_ACTIVE)
        self.assertEqual(new_pump.transport_session_id, OTHER_SESSION_ID)
        # New planner generation domain; command high-water and event sequence preserved.
        self.assertEqual(new_pump.session_generation, old_generation + 1)
        self.assertEqual(new_pump.command_high_water, old_hw)
        self.assertEqual(new_pump.next_event_sequence, old_next_es)
        self.assertEqual(new_pump.last_current_tick, 7)        # authority clock not reset

        # The recovered pump admits a fresh frame on the new transport session.
        new_encoder = BsplineTcpEncoder(OTHER_SESSION_ID)
        frame = new_encoder.encode_frame(make_payload(clear_cps(), traj_id=10, nanosec=8_000_000))
        outcomes = new_pump.feed(frame, identity=current_identity(new_pump), current_tick=8, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertEqual(new_pump.session_generation, old_generation + 2)

    def test_recover_rejects_old_transport_session_frames(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        pump.feed(poison_frame(encoder, traj_id=1), identity=IDENTITY, current_tick=0,
                  fallback_yaw=0.0)
        new_pump = PlannerTransportPump.recover(pump, transport_session_id=OTHER_SESSION_ID)
        # A frame from the OLD transport session is poison to the new decoder.
        stale = BsplineTcpEncoder(SESSION_ID).encode_frame(make_payload(clear_cps(), traj_id=1))
        outcomes = new_pump.feed(stale, identity=current_identity(new_pump), current_tick=0, fallback_yaw=0.0)
        self.assertEqual(outcomes[0].outcome, OUTCOME_POISON)
        self.assertEqual(outcomes[0].detail, "session_mismatch")
        self.assertEqual(new_pump.state, STATE_POISONED)

    def test_recover_requires_poisoned_and_new_session(self):
        session, adapter, decoder, pump = make_pump()
        # Not poisoned -> recovery undefined.
        self.assert_pump_error("not_poisoned", PlannerTransportPump.recover, pump,
                               transport_session_id=OTHER_SESSION_ID)
        # Poison it, then reuse of the same transport_session_id is refused.
        encoder = BsplineTcpEncoder(SESSION_ID)
        pump.feed(poison_frame(encoder, traj_id=1), identity=IDENTITY, current_tick=0,
                  fallback_yaw=0.0)
        self.assert_pump_error("session_reuse", PlannerTransportPump.recover, pump,
                               transport_session_id=SESSION_ID)
        self.assert_pump_error("invalid_pump", PlannerTransportPump.recover, object(),
                               transport_session_id=OTHER_SESSION_ID)

    def test_recover_rejects_invalid_transport_session_id(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        pump.feed(poison_frame(encoder, traj_id=1), identity=IDENTITY, current_tick=0,
                  fallback_yaw=0.0)
        for bad in (None, "short", "A" * 32, "g" * 32):
            with self.subTest(bad=repr(bad)):
                self.assert_pump_error("invalid_session_id", PlannerTransportPump.recover,
                                       pump, transport_session_id=bad)

    def test_recover_rejects_generation_cap(self):
        identity = dict(IDENTITY, planner_generation=MAX_GENERATION)
        session = TrajectorySession(identity)
        adapter = EgoTrajectoryAdapter(session)
        decoder = BsplineTcpDecoder(SESSION_ID)
        pump = PlannerTransportPump(adapter, decoder=decoder, anchor_ns=0)
        # At MAX_GENERATION feed is intentionally blocked before decoder reads;
        # force the terminal fixture only to exercise recover's cap guard.
        pump._state = STATE_POISONED
        self.assert_pump_error("generation_exhausted", PlannerTransportPump.recover,
                               pump, transport_session_id=OTHER_SESSION_ID)


class PumpGuardTests(unittest.TestCase):
    def assert_pump_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(PumpError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_tick_regression_rejected_without_mutation(self):
        session, adapter, decoder, pump = make_pump()
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
            make_payload(clear_cps(), traj_id=1, nanosec=100_000_000))  # start_tick 100
        pump.feed(frame, identity=IDENTITY, current_tick=100, fallback_yaw=0.0)
        before = pump_snapshot(pump)
        self.assert_pump_error("tick_regressed", pump.feed, b"",
                               identity=IDENTITY, current_tick=50, fallback_yaw=0.0)
        self.assertEqual(pump_snapshot(pump), before)

    def test_tick_above_max_rejected_before_decoder_mutation(self):
        session, adapter, decoder, pump = make_pump()
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(make_payload(clear_cps(), traj_id=1))
        before = pump_snapshot(pump)
        self.assert_pump_error("invalid_tick", pump.feed, frame, identity=IDENTITY,
                               current_tick=MAX_TICK + 1, fallback_yaw=0.0)
        self.assertEqual(pump_snapshot(pump), before)
        self.assertEqual(decoder.high_water_sequence, 0)

    def test_generation_cap_rejected_before_decoder_mutation(self):
        identity = dict(IDENTITY, planner_generation=MAX_GENERATION)
        session = TrajectorySession(identity)
        adapter = EgoTrajectoryAdapter(session)
        decoder = BsplineTcpDecoder(SESSION_ID)
        pump = PlannerTransportPump(adapter, decoder=decoder, anchor_ns=0)
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
            make_payload(clear_cps(), traj_id=1))
        before = pump_snapshot(pump)
        for tick in (0, MAX_TICK):
            with self.subTest(tick=tick):
                self.assert_pump_error(
                    "generation_exhausted", pump.feed, frame,
                    identity=current_identity(pump), current_tick=tick, fallback_yaw=0.0)
                self.assertEqual(pump_snapshot(pump), before)
                self.assertEqual(decoder.high_water_sequence, 0)

    def test_initial_event_sequence_must_follow_existing_high_water(self):
        def build(high_water):
            identity = dict(IDENTITY)
            session = TrajectorySession(identity)
            session.last_event_sequence = high_water
            adapter = EgoTrajectoryAdapter(session)
            decoder = BsplineTcpDecoder(SESSION_ID)
            return session, decoder, adapter

        for initial in (MAX_COMMAND_ID - 2, MAX_COMMAND_ID - 1):
            with self.subTest(initial=initial):
                session, decoder, adapter = build(MAX_COMMAND_ID - 1)
                self.assert_pump_error(
                    "invalid_sequence", PlannerTransportPump, adapter,
                    decoder=decoder, anchor_ns=0, initial_event_sequence=initial)
                self.assertEqual(session.last_event_sequence, MAX_COMMAND_ID - 1)
                self.assertEqual(decoder.high_water_sequence, 0)

        session, decoder, adapter = build(MAX_COMMAND_ID)
        self.assert_pump_error(
            "invalid_sequence", PlannerTransportPump, adapter,
            decoder=decoder, anchor_ns=0, initial_event_sequence=MAX_COMMAND_ID)
        self.assertEqual(session.last_event_sequence, MAX_COMMAND_ID)
        self.assertEqual(decoder.high_water_sequence, 0)

        # MAX_COMMAND_ID remains usable exactly once when the existing high-water
        # is MAX_COMMAND_ID - 1.
        session, decoder, adapter = build(MAX_COMMAND_ID - 1)
        pump = PlannerTransportPump(
            adapter, decoder=decoder, anchor_ns=0,
            initial_event_sequence=MAX_COMMAND_ID)
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
            make_payload(clear_cps(), traj_id=1))
        outcome = pump.feed(frame, identity=current_identity(pump), current_tick=0,
                            fallback_yaw=0.0)[0]
        self.assertEqual(outcome.event_sequence, MAX_COMMAND_ID)
        self.assertEqual(pump.next_event_sequence, MAX_COMMAND_ID)

    def test_stale_and_future_generation_rejected_before_decoder_mutation(self):
        for generation in (-1, 1, MAX_GENERATION, MAX_GENERATION + 1):
            with self.subTest(future_generation=generation):
                session, adapter, decoder, pump = make_pump()
                frame = BsplineTcpEncoder(SESSION_ID).encode_frame(
                    make_payload(clear_cps(), traj_id=1))
                identity = dict(IDENTITY, planner_generation=generation)
                before = pump_snapshot(pump)
                self.assert_pump_error("generation_mismatch", pump.feed, frame,
                                       identity=identity, current_tick=0, fallback_yaw=0.0)
                self.assertEqual(pump_snapshot(pump), before)
                self.assertEqual(decoder.high_water_sequence, 0)

        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        pump.feed(encoder.encode_frame(make_payload(clear_cps(), traj_id=1)),
                  identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        before = pump_snapshot(pump)
        stale = encoder.encode_frame(make_payload(clear_cps(), traj_id=2))
        self.assert_pump_error("generation_mismatch", pump.feed, stale,
                               identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(pump_snapshot(pump), before)
        self.assertEqual(decoder.high_water_sequence, 1)

    def test_event_sequence_bounds_and_stable_exhaustion(self):
        with self.assertRaises(PumpError) as ctx:
            make_pump(initial_event_sequence=MAX_COMMAND_ID + 1)
        self.assertEqual(ctx.exception.reason, "invalid_sequence")

        session, adapter, decoder, pump = make_pump(initial_event_sequence=MAX_COMMAND_ID)
        encoder = BsplineTcpEncoder(SESSION_ID)
        frame = encoder.encode_frame(make_payload(clear_cps(), traj_id=1))
        outcomes = pump.feed(frame, identity=current_identity(pump), current_tick=0,
                             fallback_yaw=0.0)
        self.assertEqual(outcomes[0].event_sequence, MAX_COMMAND_ID)
        self.assertEqual(pump.next_event_sequence, MAX_COMMAND_ID)
        self.assertEqual(pump.state, STATE_ACTIVE)

        before = pump_snapshot(pump)
        next_frame = encoder.encode_frame(make_payload(clear_cps(), traj_id=2))
        self.assert_pump_error("sequence_exhausted", pump.feed, next_frame,
                               identity=current_identity(pump), current_tick=0,
                               fallback_yaw=0.0)
        self.assertEqual(pump_snapshot(pump), before)
        self.assertEqual(decoder.high_water_sequence, 1)

    def test_tiny_sample_period_maps_to_grid_rejection(self):
        session, adapter, decoder, pump = make_pump(sample_period_s=1e-100)
        frame = BsplineTcpEncoder(SESSION_ID).encode_frame(make_payload(clear_cps(), traj_id=1))
        outcomes = pump.feed(frame, identity=current_identity(pump), current_tick=0,
                             fallback_yaw=0.0)
        self.assertEqual(outcomes[0].outcome, "rejected_grid")
        self.assertEqual(outcomes[0].detail, "invalid_grid")
        self.assertTrue(outcomes[0].transport_consumed)
        self.assertFalse(outcomes[0].session_activated)
        self.assertEqual(pump_snapshot(pump), (STATE_ACTIVE, 1, 0, 0, 0))

    def test_invalid_chunk_rejected_without_mutation(self):
        session, adapter, decoder, pump = make_pump()
        before = pump_snapshot(pump)
        for bad in ("text", 123, None, [b"x"]):
            with self.subTest(bad=type(bad).__name__):
                self.assert_pump_error("invalid_chunk", pump.feed, bad,
                                       identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(pump_snapshot(pump), before)
        self.assertEqual(pump.state, STATE_ACTIVE)

    def test_construction_validates_components(self):
        session = TrajectorySession(dict(IDENTITY))
        adapter = EgoTrajectoryAdapter(session)
        decoder = BsplineTcpDecoder(SESSION_ID)
        self.assert_pump_error("invalid_adapter", PlannerTransportPump, object(),
                               decoder=decoder, anchor_ns=0)
        self.assert_pump_error("invalid_decoder", PlannerTransportPump, adapter,
                               decoder=object(), anchor_ns=0)
        self.assert_pump_error("invalid_anchor", PlannerTransportPump, adapter,
                               decoder=decoder, anchor_ns=-1)
        self.assert_pump_error("invalid_sequence", PlannerTransportPump, adapter,
                               decoder=decoder, anchor_ns=0, initial_event_sequence=-1)
        self.assert_pump_error("invalid_tick", PlannerTransportPump, adapter,
                               decoder=decoder, anchor_ns=0, initial_current_tick=-1)
        self.assert_pump_error("invalid_binding", PlannerTransportPump, adapter,
                               decoder=decoder, anchor_ns=0, binding=object())

    def test_non_claims_declared_and_no_forbidden_imports(self):
        text = " ".join(NON_CLAIMS).lower()
        for token in ("crash atomicity", "exactly-once", "no socket", "terrain15d",
                      "flight", "no identifier", "two separate"):
            self.assertIn(token, text)
        import Simulator.wksim_runtime.planner_transport_pump as module
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("import socket", "from socket", "import rospy", "import rclpy"):
            self.assertNotIn(forbidden, source)


def activate(pump, encoder, *, traj_id=1, tick=0, identity=None, nanosec=0):
    """Feed one clear frame and assert exactly one activation.

    The encoder MUST be the same instance across feeds of one pump: the
    transport sequence is per-stream, so a fresh encoder would restart it and
    poison the decoder.
    """
    frame = encoder.encode_frame(
        make_payload(clear_cps(), traj_id=traj_id, nanosec=nanosec))
    outcomes = pump.feed(frame, identity=identity or IDENTITY,
                         current_tick=tick, fallback_yaw=0.0)
    assert len(outcomes) == 1 and outcomes[0].outcome == OUTCOME_ACTIVATED
    return outcomes[0]
def control_snapshot(pump, session):
    from copy import deepcopy
    adapter = {name: id(value) if name in ("session", "_active_spline") else deepcopy(value)
               for name, value in vars(pump._adapter).items()}
    allocator = {name: id(value) if name == "_binding" else deepcopy(value)
                 for name, value in vars(pump).items()
                 if name not in ("_adapter", "_session", "_decoder", "_admission")}
    return (allocator, deepcopy(vars(session)), adapter, deepcopy(vars(pump._decoder)))


def session_event_snapshot(pump, session):
    """Full control_snapshot minus the fields a gate frame legitimately moves:
    decoder transport high-water/expectation/last envelope and the gate flag."""
    allocator, session_vars, adapter, decoder_vars = control_snapshot(pump, session)
    allocator = dict(allocator)
    allocator.pop("_output_gate_open", None)
    decoder_vars = dict(decoder_vars)
    for name in ("expected_sequence", "high_water_sequence", "last_envelope", "_buffer"):
        decoder_vars.pop(name, None)
    return allocator, session_vars, adapter, decoder_vars


class PumpControlEventTests(unittest.TestCase):
    """Pump-owned hold/cancel route through the pump event allocator."""

    def assert_pump_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(PumpError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_activate_hold_replan_sequence_strictly_increases(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        first = activate(pump, encoder, traj_id=1)
        self.assertEqual(first.event_sequence, 1)
        self.assertEqual(pump.next_event_sequence, 2)
        state = pump.hold(current_identity(pump), current_tick=0,
                          anchor=([1.0, 3.0, 1.0], 0.0))
        self.assertEqual(state, "HOLD")
        self.assertEqual(
            (session.state, session.generation, session.last_event_sequence),
            ("HOLD", 2, 2))
        self.assertEqual(pump.next_event_sequence, 3)
        self.assertEqual(pump.last_current_tick, 0)
        # The replan after the hold must use the NEXT sequence, never reuse 2.
        second = activate(pump, encoder, traj_id=2, tick=1, nanosec=1_000_000,
                          identity=current_identity(pump))
        self.assertEqual(second.event_sequence, 3)
        self.assertEqual(
            (session.state, session.generation, session.last_event_sequence),
            ("ACTIVE", 3, 3))
        self.assertEqual(pump.next_event_sequence, 4)

    def test_hold_without_usable_anchor_is_atomically_rejected(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        before = control_snapshot(pump, session)
        with self.assertRaises(ValueError) as ctx:
            pump.hold(current_identity(pump), current_tick=0)
        self.assertIn("hold anchor", str(ctx.exception))
        # Atomic: the rejection changed NOTHING -- no burned sequence.
        self.assertEqual(control_snapshot(pump, session), before)
        # The next replan uses the very next sequence, proving no burn.
        second = activate(pump, encoder, traj_id=2, tick=1, nanosec=1_000_000,
                          identity=current_identity(pump))
        self.assertEqual(second.event_sequence, 2)

    def test_hold_with_invalid_anchor_shape_is_atomically_rejected(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        before = control_snapshot(pump, session)
        with self.assertRaises(ValueError):
            pump.hold(current_identity(pump), current_tick=0, anchor=object())
        self.assertEqual(control_snapshot(pump, session), before)

    def test_hold_with_non_finite_anchor_is_atomically_rejected(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        before = control_snapshot(pump, session)
        with self.assertRaises(ValueError):
            pump.hold(current_identity(pump), current_tick=0,
                      anchor=([0.0, float("nan"), 1.0], 0.0))
        self.assertEqual(control_snapshot(pump, session), before)

    def test_hold_on_waiting_session_requires_anchor(self):
        session, adapter, decoder, pump = make_pump()
        before = control_snapshot(pump, session)
        with self.assertRaises(ValueError):
            pump.hold(current_identity(pump), current_tick=0)
        self.assertEqual(control_snapshot(pump, session), before)
        # With an explicit anchor the same hold succeeds from WAITING.
        state = pump.hold(current_identity(pump), current_tick=0,
                          anchor=([0.0, 0.0, 1.0], 0.0))
        self.assertEqual(state, "HOLD")
        self.assertEqual(
            (session.state, session.generation, session.last_event_sequence),
            ("HOLD", 1, 1))
        self.assertEqual(pump.next_event_sequence, 2)

    def test_control_tick_must_be_valid_and_not_regress(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1, tick=5, nanosec=5_000_000)
        before = control_snapshot(pump, session)
        for bad_tick in (-1, 1.5, "3", None, True, MAX_TICK + 1):
            self.assert_pump_error(
                "invalid_tick", pump.hold, current_identity(pump),
                current_tick=bad_tick, anchor=([0.0, 0.0, 1.0], 0.0))
        self.assert_pump_error(
            "tick_regressed", pump.hold, current_identity(pump),
            current_tick=4, anchor=([0.0, 0.0, 1.0], 0.0))
        self.assert_pump_error(
            "tick_regressed", pump.cancel, current_identity(pump),
            current_tick=0)
        self.assertEqual(control_snapshot(pump, session), before)
        # Equal tick is allowed (non-regression, not strict increase).
        state = pump.hold(current_identity(pump), current_tick=5,
                          anchor=([0.0, 0.0, 1.0], 0.0))
        self.assertEqual(state, "HOLD")
        self.assertEqual(pump.last_current_tick, 5)

    def test_failed_control_event_does_not_advance_pump_tick(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1, tick=2, nanosec=2_000_000)
        before = control_snapshot(pump, session)
        with self.assertRaises(ValueError):
            pump.hold(current_identity(pump), current_tick=7)
        self.assertEqual(control_snapshot(pump, session), before)
        self.assertEqual(pump.last_current_tick, 2)

    def test_generation_exhaustion_is_atomically_rejected(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        session.generation = MAX_GENERATION
        identity = current_identity(pump)
        before = control_snapshot(pump, session)
        with self.assertRaises(OverflowError):
            pump.hold(identity, current_tick=0,
                      anchor=([0.0, 0.0, 1.0], 0.0))
        with self.assertRaises(OverflowError):
            pump.cancel(identity, current_tick=0)
        self.assertEqual(control_snapshot(pump, session), before)

    def test_cancel_is_terminal_and_blocks_everything_after(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        state = pump.cancel(current_identity(pump), current_tick=0)
        self.assertEqual(state, "CANCELLED")
        self.assertEqual(
            (session.state, session.generation, session.last_event_sequence),
            ("CANCELLED", 2, 2))
        self.assertEqual(pump.next_event_sequence, 3)
        # Terminal rejections are atomic: nothing burns.
        before = control_snapshot(pump, session)
        with self.assertRaises(ValueError):
            pump.hold(current_identity(pump), current_tick=0,
                      anchor=([0.0, 0.0, 1.0], 0.0))
        with self.assertRaises(ValueError):
            pump.cancel(current_identity(pump), current_tick=0)
        self.assertEqual(control_snapshot(pump, session), before)
        # Replan after terminal cancel is refused by admission, no activation.
        frame = encoder.encode_frame(
            make_payload(clear_cps(), traj_id=2, nanosec=1_000_000))
        outcomes = pump.feed(frame, identity=current_identity(pump),
                             current_tick=1, fallback_yaw=0.0)
        self.assertEqual(len(outcomes), 1)
        self.assertNotEqual(outcomes[0].outcome, OUTCOME_ACTIVATED)
        self.assertFalse(outcomes[0].session_activated)
        self.assertEqual(session.last_event_sequence, 2)
        self.assertEqual(pump.next_event_sequence, 3)

    def test_stale_generation_rejected_before_any_mutation(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        before = control_snapshot(pump, session)
        stale = dict(current_identity(pump), planner_generation=0)
        self.assert_pump_error("generation_mismatch", pump.hold, stale,
                               current_tick=0,
                               anchor=([0.0, 0.0, 1.0], 0.0))
        self.assert_pump_error("generation_mismatch", pump.cancel, stale,
                               current_tick=0)
        self.assertEqual(control_snapshot(pump, session), before)

    def test_malformed_identity_rejected_without_burn(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        before = control_snapshot(pump, session)
        with self.assertRaises((AdapterError, ValueError)):
            pump.hold(ExplodingIdentityMapping(), current_tick=0,
                      anchor=([0.0, 0.0, 1.0], 0.0))
        self.assertEqual(control_snapshot(pump, session), before)

    def test_poisoned_pump_rejects_control_events(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        pump.feed(poison_frame(encoder, traj_id=2),
                  identity=current_identity(pump), current_tick=1,
                  fallback_yaw=0.0)
        self.assertEqual(pump.state, STATE_POISONED)
        before = control_snapshot(pump, session)
        self.assert_pump_error("poisoned", pump.hold, current_identity(pump),
                               current_tick=1,
                               anchor=([0.0, 0.0, 1.0], 0.0))
        self.assert_pump_error("poisoned", pump.cancel, current_identity(pump),
                               current_tick=1)
        self.assertEqual(control_snapshot(pump, session), before)

    def test_event_sequence_exhaustion_blocks_control_events(self):
        session, adapter, decoder, pump = make_pump(
            initial_event_sequence=MAX_COMMAND_ID)
        encoder = BsplineTcpEncoder(SESSION_ID)
        # The last available sequence is spent by the activation itself.
        first = activate(pump, encoder, traj_id=1)
        self.assertEqual(first.event_sequence, MAX_COMMAND_ID)
        before = control_snapshot(pump, session)
        self.assert_pump_error("sequence_exhausted", pump.hold,
                               current_identity(pump), current_tick=0,
                               anchor=([0.0, 0.0, 1.0], 0.0))
        self.assert_pump_error("sequence_exhausted", pump.cancel,
                               current_identity(pump), current_tick=0)
        self.assertEqual(control_snapshot(pump, session), before)


def make_control_pump(**kwargs):
    session = TrajectorySession(dict(IDENTITY))
    adapter = EgoTrajectoryAdapter(session)
    decoder = BsplineTcpDecoder(SESSION_ID, accept_control=True)
    pump = PlannerTransportPump(adapter, decoder=decoder, anchor_ns=0,
                                accept_control=True, **kwargs)
    return session, adapter, decoder, pump


class PumpControlCarrierTests(unittest.TestCase):
    """v2 control carrier through the opt-in pump: gate/hold/cancel in-stream."""

    def assert_pump_error(self, reason, callable_obj, *args, **kwargs):
        with self.assertRaises(PumpError) as ctx:
            callable_obj(*args, **kwargs)
        self.assertEqual(ctx.exception.reason, reason)
        return ctx.exception

    def test_control_mode_requires_opted_in_decoder(self):
        session = TrajectorySession(dict(IDENTITY))
        adapter = EgoTrajectoryAdapter(session)
        v1_decoder = BsplineTcpDecoder(SESSION_ID)
        self.assert_pump_error(
            "invalid_decoder", PlannerTransportPump, adapter,
            decoder=v1_decoder, anchor_ns=0, accept_control=True)
        decoder = BsplineTcpDecoder(SESSION_ID, accept_control=True)
        self.assert_pump_error(
            "invalid_decoder", PlannerTransportPump, adapter,
            decoder=decoder, anchor_ns=0, accept_control=1)

    def test_v1_pump_poisons_on_control_frame(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        outcomes = pump.feed(
            encoder.encode_control_frame({"kind": "gate", "open": True}),
            identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_POISON])
        self.assertEqual(pump.state, STATE_POISONED)

    def test_mixed_stream_order_and_shared_sequence(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        chunk = (encoder.encode_control_frame({"kind": "gate", "open": True})
                 + encoder.encode_frame(make_payload(clear_cps(), traj_id=1))
                 + encoder.encode_control_frame({"kind": "gate", "open": False}))
        outcomes = pump.feed(chunk, identity=IDENTITY, current_tick=0,
                             fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes],
                         ["gate_open", OUTCOME_ACTIVATED])
        self.assertEqual([o.transport_sequence for o in outcomes], [1, 2])
        # The activation bumped the generation: the buffered gate frame waits
        # for the caller to re-derive identity (existing feed rule).
        outcomes = pump.feed(b"", identity=current_identity(pump),
                             current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["gate_closed"])
        self.assertEqual(outcomes[0].transport_sequence, 3)
        self.assertEqual(session.state, "ACTIVE")
        # Gate frames spent zero session events: only the activation burned 1.
        self.assertEqual(session.last_event_sequence, 1)
        self.assertEqual(pump.next_event_sequence, 2)

    def test_gate_is_idempotent_and_touches_no_session_state(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        self.assertFalse(pump.output_gate_open)  # initial closed
        before = session_event_snapshot(pump, session)
        for flag in (True, True, False, False):
            outcomes = pump.feed(
                encoder.encode_control_frame({"kind": "gate", "open": flag}),
                identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(outcomes[0].transport_consumed, True)
            self.assertIsNone(outcomes[0].event_sequence)
        # Session/event state untouched; only the gate flag and the transport
        # high-water (1 per frame, honestly spent) moved.
        self.assertEqual(session_event_snapshot(pump, session), before)
        self.assertEqual(decoder.high_water_sequence, 4)
        self.assertFalse(pump.output_gate_open)

    def test_gate_closed_on_waiting_session_fabricates_nothing(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        before = session_event_snapshot(pump, session)
        outcomes = pump.feed(
            encoder.encode_control_frame({"kind": "gate", "open": False}),
            identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["gate_closed"])
        self.assertEqual(session_event_snapshot(pump, session), before)
        self.assertEqual(decoder.high_water_sequence, 1)
        self.assertEqual(session.state, "WAITING")

    def test_hold_frame_rejection_is_atomic_then_replan_continues(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        outcomes = pump.feed(encoder.encode_control_frame({"kind": "hold"}),
                             identity=current_identity(pump), current_tick=1,
                             fallback_yaw=0.0)
        # No hold anchor exists (no sample fed): atomic session rejection,
        # transport honestly consumed, zero event burn.
        self.assertEqual([o.outcome for o in outcomes], ["rejected_hold"])
        self.assertEqual(session.last_event_sequence, 1)
        self.assertEqual(pump.next_event_sequence, 2)
        self.assertEqual(session.state, "ACTIVE")
        # A successful pump-entry hold then a replan keep sequences strict.
        pump.hold(current_identity(pump), current_tick=1,
                  anchor=([1.0, 3.0, 1.0], 0.0))
        self.assertEqual(session.state, "HOLD")
        second = activate(pump, encoder, traj_id=2, tick=2, nanosec=2_000_000,
                          identity=current_identity(pump))
        self.assertEqual(second.event_sequence, 3)

    def test_cancel_frame_is_terminal_via_allocator(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        activate(pump, encoder, traj_id=1)
        outcomes = pump.feed(encoder.encode_control_frame({"kind": "cancel"}),
                             identity=current_identity(pump), current_tick=1,
                             fallback_yaw=0.0)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].outcome, "cancel")
        self.assertEqual(outcomes[0].event_sequence, 2)
        self.assertEqual(session.state, "CANCELLED")
        self.assertEqual(pump.next_event_sequence, 3)
        # Terminal: a later hold frame is atomically rejected, no burn.
        outcomes = pump.feed(encoder.encode_control_frame({"kind": "hold"}),
                             identity=current_identity(pump), current_tick=2,
                             fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["rejected_hold"])
        self.assertEqual(session.last_event_sequence, 2)
        self.assertEqual(pump.next_event_sequence, 3)

    def test_malformed_control_frame_poisons_pump(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        bad = encoder.build_control_envelope({"kind": "gate", "open": True})
        bad["control"] = {"kind": "gate", "open": "yes"}
        outcomes = pump.feed(
            pack_frame(serialize_envelope_json(bad)),
            identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_POISON])
        self.assertEqual(pump.state, STATE_POISONED)

    def test_generation_change_defers_buffered_control_to_next_feed(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        chunk = (encoder.encode_frame(make_payload(clear_cps(), traj_id=1))
                 + encoder.encode_control_frame({"kind": "gate", "open": True}))
        # The activation bumps the generation; the buffered control frame must
        # wait for the caller to re-derive identity (existing feed rule).
        outcomes = pump.feed(chunk, identity=IDENTITY, current_tick=0,
                             fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_ACTIVATED])
        self.assertFalse(pump.output_gate_open)
        outcomes = pump.feed(b"", identity=current_identity(pump),
                             current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["gate_open"])
        self.assertTrue(pump.output_gate_open)

    def test_control_events_reject_wrong_stable_tuple_before_any_change(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        before = session_event_snapshot(pump, session)
        for field, bad in (("run_id", "run-b"), ("mission_id", "mission-b"),
                           ("uav_id", 9), ("control_epoch", "epoch-b")):
            bad_identity = dict(IDENTITY, **{field: bad})
            outcomes = pump.feed(
                encoder.encode_control_frame({"kind": "gate", "open": True}),
                identity=bad_identity, current_tick=0, fallback_yaw=0.0)
            self.assertEqual([o.outcome for o in outcomes], ["rejected_identity"])
            self.assertTrue(outcomes[0].transport_consumed)
            self.assertFalse(pump.output_gate_open)  # never toggled
        self.assertEqual(session_event_snapshot(pump, session), before)
        # A legal identity still opens the gate afterwards.
        outcomes = pump.feed(
            encoder.encode_control_frame({"kind": "gate", "open": True}),
            identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["gate_open"])
        self.assertTrue(pump.output_gate_open)

    def test_control_events_reject_malformed_identity(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        before = session_event_snapshot(pump, session)
        outcomes = pump.feed(
            encoder.encode_control_frame({"kind": "gate", "open": True}),
            identity=ExplodingIdentityMapping(), current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["rejected_identity"])
        self.assertFalse(pump.output_gate_open)
        self.assertEqual(session_event_snapshot(pump, session), before)

    def test_recover_preserves_control_mode_and_resets_gate(self):
        session, adapter, decoder, pump = make_control_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        # Open the gate, then poison via a bad-frame hash mismatch.
        pump.feed(encoder.encode_control_frame({"kind": "gate", "open": True}),
                  identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertTrue(pump.output_gate_open)
        pump.feed(poison_frame(encoder, traj_id=1),
                  identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        self.assertEqual(pump.state, STATE_POISONED)
        recovered = PlannerTransportPump.recover(
            pump, transport_session_id=OTHER_SESSION_ID)
        # No silent v1 downgrade; gate restarts closed.
        self.assertTrue(recovered.accept_control)
        self.assertFalse(recovered.output_gate_open)
        # A legal gate frame works on the recovered pump (generation + 1).
        new_encoder = BsplineTcpEncoder(OTHER_SESSION_ID)
        identity = dict(IDENTITY,
                        planner_generation=recovered.session_generation,
                        command_high_water=recovered.command_high_water)
        outcomes = recovered.feed(
            new_encoder.encode_control_frame({"kind": "gate", "open": True}),
            identity=identity, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], ["gate_open"])
        self.assertTrue(recovered.output_gate_open)

    def test_recover_of_v1_pump_stays_v1(self):
        session, adapter, decoder, pump = make_pump()
        encoder = BsplineTcpEncoder(SESSION_ID)
        pump.feed(poison_frame(encoder, traj_id=1),
                  identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
        recovered = PlannerTransportPump.recover(
            pump, transport_session_id=OTHER_SESSION_ID)
        self.assertFalse(recovered.accept_control)
        # A control frame on the recovered v1 pump poisons like any v1 pump.
        new_encoder = BsplineTcpEncoder(OTHER_SESSION_ID)
        identity = dict(IDENTITY,
                        planner_generation=recovered.session_generation,
                        command_high_water=recovered.command_high_water)
        outcomes = recovered.feed(
            new_encoder.encode_control_frame({"kind": "gate", "open": True}),
            identity=identity, current_tick=0, fallback_yaw=0.0)
        self.assertEqual([o.outcome for o in outcomes], [OUTCOME_POISON])


if __name__ == "__main__":
    unittest.main()
