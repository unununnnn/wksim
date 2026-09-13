"""Deterministic offline tests for the #102 Route-B command egress slice.

No ROS, no SITL/UE/MATLAB, no wall clock, no real socket. The session and
adapter are built exactly like validation/test_ego_trajectory_adapter.py; the
egress receives the SAME adapter object a PlannerTransportPump would hold, so
the tests prove single-session sharing via the pump's public generation view.
"""
import unittest

from Simulator.wksim_planning.ego_evaluator import DEFAULT_ORDER, EgoSpline
from Simulator.wksim_planning.ego_trajectory_adapter import EgoTrajectoryAdapter
from Simulator.wksim_planning.trajectory_session import (
    MAX_COMMAND_ID,
    TrajectorySession,
)
from Simulator.wksim_runtime.planner_command_egress import (
    MAX_REQUEST_ID,
    EgressFault,
    PlannerCommandEgress,
    authority_tick,
    classify_command_event,
    command_fields,
    session_state_decision,
    session_state_fresh_and_owned,
)

IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1,
                control_epoch="epoch-a", planner_generation=0,
                command_high_water=0)

INFO = 0   # prometheus_msgs/TextInfo INFO
ERROR = 2  # prometheus_msgs/TextInfo ERROR


def identity(session):
    value = dict(IDENTITY)
    value["planner_generation"] = session.generation
    return value


def straight_spline(scale=0.5, points=7):
    return EgoSpline(DEFAULT_ORDER, None,
                     [(float(i) * scale, 0.0, 1.0) for i in range(points)])


def make_activated_adapter():
    session = TrajectorySession(IDENTITY)
    adapter = EgoTrajectoryAdapter(session)
    adapter.replan_and_activate(
        identity(session), 1, straight_spline(), 1, 0, 0.0)
    return session, adapter


class RecordingPublisher:
    def __init__(self, fail=False):
        self.envelopes = []
        self.fail = fail

    def __call__(self, envelope):
        if self.fail:
            raise RuntimeError("simulated publish failure")
        self.envelopes.append(envelope)


def make_egress(activated=True, clock=1_500_000_000, publisher=None, **kw):
    if activated:
        session, adapter = make_activated_adapter()
    else:
        session = TrajectorySession(IDENTITY)
        adapter = EgoTrajectoryAdapter(session)
    pub = publisher if publisher is not None else RecordingPublisher()
    egress = PlannerCommandEgress(
        adapter, pub, run_id=IDENTITY["run_id"],
        mission_id=IDENTITY["mission_id"], uav_id=IDENTITY["uav_id"],
        control_epoch=IDENTITY["control_epoch"],
        clock_ns=lambda: clock, **kw)
    return session, adapter, egress, pub


class CommandFieldsTests(unittest.TestCase):
    """The shared intent -> field mapping used by both public writers."""

    def intent(self, kind="trajectory", **overrides):
        value = dict(intent=kind, position_ref=(1.0, 2.0, 3.0),
                     velocity_ref=(0.5, 0.0, 0.0),
                     acceleration_ref=(0.0, 0.0, 0.0),
                     yaw_ref=0.25, yaw_rate_mode=False, yaw_rate_ref=0.0,
                     command_id=7)
        value.update(overrides)
        return value

    def test_trajectory_mapping(self):
        fields = command_fields(self.intent(), 1_500_000_001)
        self.assertEqual(fields["stamp_sec"], 1)
        self.assertEqual(fields["stamp_nanosec"], 500_000_001)
        self.assertEqual(fields["frame_id"], "map")
        self.assertEqual(fields["agent_cmd"], "MOVE")
        self.assertEqual(fields["control_level"], "DEFAULT_CONTROL")
        self.assertEqual(fields["move_mode"], "TRAJECTORY")
        self.assertEqual(fields["position_ref"], [1.0, 2.0, 3.0])
        self.assertEqual(fields["command_id"], 7)

    def test_hold_maps_to_xyz_pos(self):
        fields = command_fields(self.intent("hold"), 0)
        self.assertEqual(fields["move_mode"], "XYZ_POS")

    def test_missing_field_rejected(self):
        intent = self.intent()
        del intent["yaw_ref"]
        with self.assertRaises(ValueError):
            command_fields(intent, 0)

    def test_non_finite_vector_rejected(self):
        with self.assertRaises(ValueError):
            command_fields(
                self.intent(position_ref=(0.0, float("nan"), 0.0)), 0)

    def test_bad_kind_and_clock_rejected(self):
        with self.assertRaises(ValueError):
            command_fields(self.intent("teleport"), 0)
        with self.assertRaises(ValueError):
            command_fields(self.intent(), -1)
        with self.assertRaises(ValueError):
            command_fields(self.intent(), True)

    def test_bool_command_id_rejected(self):
        with self.assertRaises(ValueError):
            command_fields(self.intent(command_id=True), 0)


class ClassifyCommandEventTests(unittest.TestCase):
    """The shared ACK classifier; state transitions stay with the caller."""

    def event(self, kind, request_id=1, command_id=1, **overrides):
        value = dict(version=1, run_id=IDENTITY["run_id"],
                     control_epoch=IDENTITY["control_epoch"], event=kind,
                     request_id=request_id, command_id=command_id)
        value.update(overrides)
        return value

    def classify(self, event, message_type=INFO, pending=(1, 1), last_ack=None):
        return classify_command_event(
            event, message_type, run_id=IDENTITY["run_id"],
            epoch=IDENTITY["control_epoch"], pending=pending,
            last_ack=last_ack, info_value=INFO, error_value=ERROR)

    def test_accepted_clears_pending_and_records_ack(self):
        outcome, pending, last_ack = self.classify(self.event("command_accepted"))
        self.assertEqual(outcome, "accepted")
        self.assertIsNone(pending)
        self.assertEqual(last_ack, (1, 1))

    def test_duplicate_ack_ignored(self):
        outcome, pending, _ = self.classify(
            self.event("command_accepted"), last_ack=(1, 1))
        self.assertEqual(outcome, "duplicate_ack")
        self.assertEqual(pending, (1, 1))

    def test_rejected_faults(self):
        outcome, _, _ = self.classify(self.event("command_rejected"), ERROR)
        self.assertEqual(outcome, "fault:command_rejected")

    def test_type_mismatch_faults(self):
        self.assertEqual(self.classify(self.event("command_accepted"), ERROR)[0],
                         "fault:text_info_type_mismatch")
        self.assertEqual(self.classify(self.event("command_rejected"), INFO)[0],
                         "fault:text_info_type_mismatch")
        self.assertEqual(self.classify(self.event("control_revoked"), INFO)[0],
                         "fault:text_info_type_mismatch")

    def test_revoked_faults(self):
        self.assertEqual(self.classify(self.event("control_revoked"), ERROR)[0],
                         "fault:control_revoked")

    def test_foreign_event_ignored(self):
        self.assertEqual(
            self.classify(self.event("command_accepted", run_id="run-b"))[0],
            "ignored")
        self.assertEqual(
            self.classify(self.event("status_heartbeat"))[0], "ignored")
        self.assertEqual(
            self.classify(dict(version=2, run_id=IDENTITY["run_id"],
                               control_epoch=IDENTITY["control_epoch"]))[0],
            "ignored")

    def test_other_writer_faults(self):
        self.assertEqual(
            self.classify(self.event("command_accepted", request_id=99))[0],
            "fault:other_command_writer_event")
        self.assertEqual(
            self.classify(self.event("command_accepted"), pending=None)[0],
            "fault:other_command_writer_event")

    def test_malformed_faults(self):
        self.assertEqual(self.classify("not a dict")[0],
                         "fault:malformed_text_info")


class PlannerCommandEgressTests(unittest.TestCase):
    """The egress drives the pump-held adapter; no second session exists."""

    def test_shares_the_adapter_session(self):
        session, adapter, egress, _ = make_egress()
        self.assertIs(egress.session, session)
        self.assertIs(egress.session, adapter.session)

    def test_identity_mismatch_rejected(self):
        other = TrajectorySession(dict(IDENTITY, run_id="run-b"))
        adapter = EgoTrajectoryAdapter(other)
        with self.assertRaises(ValueError):
            PlannerCommandEgress(
                adapter, RecordingPublisher(), run_id=IDENTITY["run_id"],
                mission_id=IDENTITY["mission_id"], uav_id=IDENTITY["uav_id"],
                control_epoch=IDENTITY["control_epoch"], clock_ns=lambda: 0)

    def test_step_publishes_trajectory_envelope(self):
        session, _, egress, pub = make_egress()
        envelope = egress.step_and_publish(0, True, True)
        self.assertEqual(envelope["run_id"], IDENTITY["run_id"])
        self.assertEqual(envelope["control_epoch"], IDENTITY["control_epoch"])
        self.assertEqual(envelope["request_id"], 1)
        self.assertEqual(envelope["command"]["move_mode"], "TRAJECTORY")
        self.assertEqual(envelope["command"]["command_id"], 1)
        self.assertEqual(session.last_command_id, 1)
        self.assertEqual(egress.pending, (1, 1))
        self.assertEqual(pub.envelopes, [envelope])

    def test_pending_blocks_second_step_and_latches_fault(self):
        _, _, egress, pub = make_egress()
        egress.step_and_publish(0, True, True)
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(1, True, True)
        self.assertEqual(caught.exception.reason, "multiple_pending_commands")
        with self.assertRaises(EgressFault):
            egress.step_and_publish(2, True, True)
        self.assertEqual(len(pub.envelopes), 1)
        self.assertEqual(egress.request_high_water, 1)

    def test_ack_flow_releases_next_request(self):
        _, _, egress, pub = make_egress()
        first = egress.step_and_publish(0, True, True)
        outcome = egress.on_command_event(
            dict(version=1, run_id=IDENTITY["run_id"],
                 control_epoch=IDENTITY["control_epoch"],
                 event="command_accepted", request_id=1, command_id=1),
            INFO, info_value=INFO, error_value=ERROR)
        self.assertEqual(outcome, "accepted")
        self.assertIsNone(egress.pending)
        self.assertEqual(egress.last_ack, (1, 1))
        second = egress.step_and_publish(1, True, True)
        self.assertEqual(second["request_id"], first["request_id"] + 1)
        self.assertEqual(len(pub.envelopes), 2)

    def test_rejection_event_latches_fault(self):
        _, _, egress, pub = make_egress()
        egress.step_and_publish(0, True, True)
        with self.assertRaises(EgressFault) as caught:
            egress.on_command_event(
                dict(version=1, run_id=IDENTITY["run_id"],
                     control_epoch=IDENTITY["control_epoch"],
                     event="command_rejected", request_id=1, command_id=1),
                ERROR, info_value=INFO, error_value=ERROR)
        self.assertEqual(caught.exception.reason, "command_rejected")
        with self.assertRaises(EgressFault):
            egress.step_and_publish(1, True, True)
        self.assertEqual(len(pub.envelopes), 1)

    def test_revoke_event_latches_fault(self):
        _, _, egress, _ = make_egress()
        with self.assertRaises(EgressFault) as caught:
            egress.on_command_event(
                dict(version=1, run_id=IDENTITY["run_id"],
                     control_epoch=IDENTITY["control_epoch"],
                     event="control_revoked"),
                ERROR, info_value=INFO, error_value=ERROR)
        self.assertEqual(caught.exception.reason, "control_revoked")

    def test_missing_activation_faults_without_publish(self):
        _, _, egress, pub = make_egress(activated=False)
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(0, True, True)
        self.assertTrue(caught.exception.reason.startswith(
            ("missing_trajectory_intent", "adapter_step_failed")))
        self.assertEqual(pub.envelopes, [])
        self.assertEqual(egress.request_high_water, 0)

    def test_tick_regression_latches_fault(self):
        _, _, egress, pub = make_egress()
        egress.step_and_publish(0, True, True)
        egress.on_command_event(
            dict(version=1, run_id=IDENTITY["run_id"],
                 control_epoch=IDENTITY["control_epoch"],
                 event="command_accepted", request_id=1, command_id=1),
            INFO, info_value=INFO, error_value=ERROR)
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(0, True, True)
        self.assertTrue(caught.exception.reason.startswith("adapter_step_failed"))
        self.assertEqual(len(pub.envelopes), 1)

    def test_request_high_water_exhaustion_faults(self):
        session, adapter = make_activated_adapter()
        egress = PlannerCommandEgress(
            adapter, RecordingPublisher(), run_id=IDENTITY["run_id"],
            mission_id=IDENTITY["mission_id"], uav_id=IDENTITY["uav_id"],
            control_epoch=IDENTITY["control_epoch"], clock_ns=lambda: 0,
            initial_request_high_water=MAX_REQUEST_ID)
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(0, True, True)
        self.assertEqual(caught.exception.reason, "request_id_exhausted")

    def test_command_id_exhaustion_faults(self):
        session, adapter = make_activated_adapter()
        session.last_command_id = MAX_COMMAND_ID
        egress = PlannerCommandEgress(
            adapter, RecordingPublisher(), run_id=IDENTITY["run_id"],
            mission_id=IDENTITY["mission_id"], uav_id=IDENTITY["uav_id"],
            control_epoch=IDENTITY["control_epoch"], clock_ns=lambda: 0)
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(0, True, True)
        self.assertEqual(caught.exception.reason, "command_id_exhausted")

    def test_publish_failure_keeps_pending_and_latches(self):
        _, _, egress, _ = make_egress(publisher=RecordingPublisher(fail=True))
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(0, True, True)
        self.assertTrue(caught.exception.reason.startswith(
            "command_publish_failed"))
        self.assertEqual(egress.pending, (1, 1))
        self.assertEqual(egress.request_high_water, 1)

    def test_pump_generation_view_tracks_shared_session(self):
        """The same adapter handed to a pump and an egress is one session."""
        from Simulator.wksim_runtime.planner_transport_pump import (
            PlannerTransportPump,
        )
        from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpDecoder
        session, adapter = make_activated_adapter()
        pump = PlannerTransportPump(
            adapter, decoder=BsplineTcpDecoder("a" * 32), anchor_ns=0,
            initial_event_sequence=2)
        egress = PlannerCommandEgress(
            adapter, RecordingPublisher(), run_id=IDENTITY["run_id"],
            mission_id=IDENTITY["mission_id"], uav_id=IDENTITY["uav_id"],
            control_epoch=IDENTITY["control_epoch"], clock_ns=lambda: 0)
        self.assertEqual(pump.session_generation, session.generation)
        adapter.replan_and_activate(
            identity(session), 2, straight_spline(), 2, 1, 0.0)
        self.assertEqual(pump.session_generation, egress.session.generation)
        self.assertEqual(egress.session.generation, session.generation)



class AuthorityTickTests(unittest.TestCase):
    """Shared authoritative clock -> tick mapping (bridge fault reasons)."""

    def test_on_grid_tick(self):
        self.assertEqual(authority_tick(1_000_000_000 + 42 * 1_000_000,
                                        1_000_000_000), 42)
        self.assertEqual(authority_tick(1_000_000_000, 1_000_000_000), 0)

    def test_before_anchor_off_grid_and_overflow_fault(self):
        with self.assertRaisesRegex(ValueError, "ros_clock_before_authority_anchor"):
            authority_tick(999_999_999, 1_000_000_000)
        with self.assertRaisesRegex(ValueError, "ros_clock_off_grid"):
            authority_tick(1_000_000_500, 1_000_000_000)
        with self.assertRaisesRegex(ValueError, "authority_tick_overflow"):
            authority_tick(1_000_000_000 + (2**63) * 1_000_000, 1_000_000_000)
        with self.assertRaisesRegex(ValueError, "invalid_ros_clock"):
            authority_tick(1.5, 1_000_000_000)


class SessionStateFreshTests(unittest.TestCase):
    """Shared 2-second freshness + ownership predicate."""

    def fields(self, **overrides):
        value = dict(now_s=100.0, published_s=99.5, received_s=99.6,
                     received_valid=True, state_valid=True,
                     control_is_command=True, failsafe=False)
        value.update(overrides)
        return value

    def test_fresh_owned_passes(self):
        self.assertTrue(session_state_fresh_and_owned(**self.fields()))

    def test_stale_windows_fail(self):
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(published_s=97.9)))
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(received_s=97.9)))
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(published_s=100.1)))

    def test_ownership_and_safety_fail(self):
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(control_is_command=False)))
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(failsafe=True)))
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(received_valid=False)))
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(state_valid=False)))

    def test_non_finite_fails(self):
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(now_s=float("nan"))))
        self.assertFalse(session_state_fresh_and_owned(
            **self.fields(published_s=float("inf"))))


class SessionStateDecisionTests(unittest.TestCase):
    """Shared SessionState gate order; mirrors bridge on_session_state."""

    EPOCH = "a" * 32

    def fields(self, **overrides):
        value = dict(version_ok=True, run_match=True, control_epoch=self.EPOCH,
                     epoch_well_formed=True, state_uav_match=True,
                     control_uav_match=True, sequence=5, last_request_id=3,
                     command_high_water=2)
        value.update(overrides)
        return value

    def context(self, **overrides):
        value = dict(retired_epochs=set(), current_epoch=None,
                     current_sequence=0, session_command_high_water=2,
                     pending_request_id=None)
        value.update(overrides)
        return value

    def test_new_epoch_binds(self):
        self.assertEqual(
            session_state_decision(self.fields(), self.context()),
            ("bind", None))

    def test_identity_gates_ignore(self):
        for key in ("version_ok", "run_match", "epoch_well_formed",
                    "state_uav_match", "control_uav_match"):
            self.assertEqual(
                session_state_decision(self.fields(**{key: False}),
                                       self.context())[0], "ignore")
        self.assertEqual(
            session_state_decision(
                self.fields(), self.context(retired_epochs={self.EPOCH}))[0],
            "ignore")

    def test_uint_and_zero_sequence_ignore(self):
        for bad in (-1, 2**64, "5", None, True):
            self.assertEqual(
                session_state_decision(self.fields(sequence=bad),
                                       self.context())[0], "ignore")
        self.assertEqual(
            session_state_decision(self.fields(sequence=0),
                                   self.context())[0], "ignore")

    def test_bind_precedes_monotonicity(self):
        # A different epoch binds even when the sequence is not newer.
        self.assertEqual(
            session_state_decision(
                self.fields(control_epoch="b" * 32, sequence=1),
                self.context(current_epoch=self.EPOCH, current_sequence=9))[0],
            "bind")

    def test_regressed_sequence_ignores(self):
        self.assertEqual(
            session_state_decision(
                self.fields(sequence=5),
                self.context(current_epoch=self.EPOCH, current_sequence=5))[0],
            "ignore")

    def test_update_accepted(self):
        self.assertEqual(
            session_state_decision(
                self.fields(sequence=6),
                self.context(current_epoch=self.EPOCH, current_sequence=5)),
            ("update", None))

    def test_external_writers_fault(self):
        self.assertEqual(
            session_state_decision(
                self.fields(sequence=6, command_high_water=9),
                self.context(current_epoch=self.EPOCH, current_sequence=5,
                             session_command_high_water=2)),
            ("fault", "external_command_writer"))
        self.assertEqual(
            session_state_decision(
                self.fields(sequence=6, last_request_id=9),
                self.context(current_epoch=self.EPOCH, current_sequence=5,
                             pending_request_id=4)),
            ("fault", "external_request_writer"))


class ReleaseEgressTests(unittest.TestCase):
    """Public release (SET_PX4_MODE) through the shared request high-water."""

    def make_release_egress(self, **kw):
        session, adapter = make_activated_adapter()
        setup_pub = RecordingPublisher()
        egress = PlannerCommandEgress(
            adapter, RecordingPublisher(), run_id=IDENTITY["run_id"],
            mission_id=IDENTITY["mission_id"], uav_id=IDENTITY["uav_id"],
            control_epoch=IDENTITY["control_epoch"], clock_ns=lambda: 2_000_000_000,
            setup_publisher=setup_pub, **kw)
        return session, adapter, egress, setup_pub

    def setup_event(self, kind, request_id, **fields):
        event = dict(version=1, run_id=IDENTITY["run_id"],
                     control_epoch=IDENTITY["control_epoch"], event=kind,
                     request_id=request_id)
        event.update(fields)
        return event

    def test_release_modes_match_control_node_exit_modes(self):
        _, _, egress, published = self.make_release_egress()
        with self.assertRaises(ValueError):
            egress.request_release(mode="OFFBOARD", expected_native_mode="OFFBOARD",
                                   owns_control=True, state_fresh=True)
        self.assertEqual(egress.request_high_water, 0)
        outcome, envelope = egress.request_release(mode="BRAKE", expected_native_mode="BRAKE",
                                                   owns_control=True, state_fresh=True)
        self.assertEqual(outcome, "sent")
        self.assertEqual(envelope["setup"]["px4_mode"], "BRAKE")
        self.assertEqual(len(published.envelopes), 1)

    def test_release_requires_current_fresh_owned_state_without_mutation(self):
        for owned, fresh in ((False, True), (True, False), (1, True), (True, None)):
            _, _, egress, published = self.make_release_egress()
            with self.subTest(owned=owned, fresh=fresh), self.assertRaises(ValueError):
                egress.request_release(mode="POSCTL", expected_native_mode="POSCTL",
                                       owns_control=owned, state_fresh=fresh)
            self.assertEqual(egress.request_high_water, 0)
            self.assertIsNone(egress.release)
            self.assertFalse(published.envelopes)

    def test_matched_semantic_rejection_and_revoke_fault(self):
        for kind in ("setup_rejected", "control_revoked"):
            _, _, egress, _ = self.make_release_egress()
            _, envelope = egress.request_release(mode="POSCTL", expected_native_mode="POSCTL",
                                                 owns_control=True, state_fresh=True)
            with self.subTest(kind=kind), self.assertRaises(EgressFault) as caught:
                egress.on_setup_event(self.setup_event(kind, envelope["request_id"], reason="setup_busy"),
                                      ERROR, info_value=INFO, error_value=ERROR)
            self.assertEqual(caught.exception.reason, "release_rejected")
            self.assertFalse(egress.release["confirmed"])

    def test_old_setup_event_is_ignored_and_contradictory_confirmation_faults(self):
        _, _, egress, _ = self.make_release_egress(initial_request_high_water=8)
        _, envelope = egress.request_release(mode="POSCTL", expected_native_mode="POSCTL",
                                             owns_control=True, state_fresh=True)
        rid = envelope["request_id"]
        self.assertEqual(egress.on_setup_event(
            self.setup_event("native_ack", rid-1, accepted=True, stage="simple"),
            INFO, info_value=INFO, error_value=ERROR), "ignored")
        self.assertFalse(egress.release["ack_received"])
        egress.on_setup_event(self.setup_event("native_ack", rid, accepted=True, stage="simple"),
                              INFO, info_value=INFO, error_value=ERROR)
        completed = self.setup_event("setup_completed", rid, action="mode", value="POSCTL", native_mode="POSCTL")
        egress.on_setup_event(completed, INFO, info_value=INFO, error_value=ERROR)
        completed["native_mode"] = "OFFBOARD"
        with self.assertRaises(EgressFault):
            egress.on_setup_event(completed, INFO, info_value=INFO, error_value=ERROR)

    def test_unconfigured_release_is_caller_error_without_mutation(self):
        _, _, egress, _ = make_egress()
        before = egress.request_high_water
        with self.assertRaises(ValueError):
            egress.request_release(owns_control=True, state_fresh=True, mode="POSCTL", expected_native_mode="POSCTL")
        self.assertEqual(egress.request_high_water, before)
        self.assertIsNone(egress.release)

    def test_release_shares_request_high_water(self):
        _, _, egress, setup_pub = self.make_release_egress()
        first = egress.step_and_publish(0, True, True)
        self.assertEqual(first["request_id"], 1)
        egress.on_command_event(
            dict(version=1, run_id=IDENTITY["run_id"],
                 control_epoch=IDENTITY["control_epoch"],
                 event="command_accepted", request_id=1, command_id=1),
            INFO, info_value=INFO, error_value=ERROR)
        outcome, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        self.assertEqual(outcome, "sent")
        self.assertEqual(envelope["request_id"], 2)  # SAME counter
        self.assertEqual(envelope["run_id"], IDENTITY["run_id"])
        self.assertEqual(envelope["control_epoch"], IDENTITY["control_epoch"])
        self.assertEqual(envelope["setup"]["cmd"], "SET_PX4_MODE")
        self.assertEqual(envelope["setup"]["px4_mode"], "POSCTL")
        self.assertEqual(envelope["setup"]["stamp_sec"], 2)
        self.assertEqual(setup_pub.envelopes, [envelope])
        self.assertEqual(egress.release["request_id"], 2)
        self.assertFalse(egress.release["confirmed"])

    def test_busy_is_atomic_and_never_fakes_cancel(self):
        _, _, egress, setup_pub = self.make_release_egress()
        egress.step_and_publish(0, True, True)  # command pending now
        before = (egress.request_high_water, egress.pending, egress.release)
        outcome, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        self.assertEqual((outcome, envelope), ("busy", None))
        self.assertEqual((egress.request_high_water, egress.pending, egress.release), before)
        self.assertEqual(setup_pub.envelopes, [])
        # After the ACK clears the pending command, the release goes through.
        egress.on_command_event(
            dict(version=1, run_id=IDENTITY["run_id"],
                 control_epoch=IDENTITY["control_epoch"],
                 event="command_accepted", request_id=1, command_id=1),
            INFO, info_value=INFO, error_value=ERROR)
        outcome, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        self.assertEqual(outcome, "sent")
        self.assertEqual(envelope["request_id"], 2)

    def test_second_release_while_in_flight_is_busy(self):
        _, _, egress, setup_pub = self.make_release_egress()
        egress.request_release(owns_control=True, state_fresh=True, mode="POSCTL", expected_native_mode="POSCTL")
        before = egress.request_high_water
        self.assertEqual(
            egress.request_release(owns_control=True, state_fresh=True, mode="AUTO.LAND", expected_native_mode="AUTO.LAND"),
            ("busy", None))
        self.assertEqual(egress.request_high_water, before)
        self.assertEqual(len(setup_pub.envelopes), 1)

    def test_mode_validation_before_any_mutation(self):
        _, _, egress, _ = self.make_release_egress()
        before = egress.request_high_water
        for bad_call in (
                dict(mode="TELEPORT", expected_native_mode="POSCTL"),
                dict(mode="", expected_native_mode="POSCTL"),
                dict(mode="POSCTL", expected_native_mode=""),
                dict(mode="POSCTL", expected_native_mode=None)):
            with self.assertRaises(ValueError):
                egress.request_release(owns_control=True, state_fresh=True, **bad_call)
        self.assertEqual(egress.request_high_water, before)
        self.assertIsNone(egress.release)

    def test_no_trajectory_after_release_issued(self):
        _, _, egress, _ = self.make_release_egress()
        egress.request_release(owns_control=True, state_fresh=True, mode="POSCTL", expected_native_mode="POSCTL")
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(0, True, True)
        self.assertEqual(caught.exception.reason, "release_in_flight")
        self.assertIsNone(egress.fault_reason)  # general fault NOT latched

    def test_two_phase_confirmation(self):
        _, _, egress, _ = self.make_release_egress()
        _, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        rid = envelope["request_id"]
        # setup_received alone is NOT progress toward confirmed.
        self.assertEqual(
            egress.on_setup_event(self.setup_event("setup_received", rid),
                                  INFO, info_value=INFO, error_value=ERROR),
            "setup_received")
        self.assertFalse(egress.release["confirmed"])
        # Phase 1: native_ack accepted with the expected stage.
        self.assertEqual(
            egress.on_setup_event(
                self.setup_event("native_ack", rid, accepted=True, stage="simple"),
                INFO, info_value=INFO, error_value=ERROR),
            "ack_received")
        self.assertFalse(egress.release["confirmed"])  # ack alone != done
        self.assertEqual(
            egress.on_setup_event(
                self.setup_event("native_ack", rid, accepted=True, stage="simple"),
                INFO, info_value=INFO, error_value=ERROR),
            "duplicate_ack")
        # Phase 2: setup_completed with exact action/value/native_mode match.
        self.assertEqual(
            egress.on_setup_event(
                self.setup_event("setup_completed", rid, action="mode",
                                 value="POSCTL", native_mode="POSCTL"),
                INFO, info_value=INFO, error_value=ERROR),
            "confirmed")
        self.assertTrue(egress.release["confirmed"])
        self.assertEqual(
            egress.on_setup_event(
                self.setup_event("setup_completed", rid, action="mode",
                                 value="POSCTL", native_mode="POSCTL"),
                INFO, info_value=INFO, error_value=ERROR),
            "duplicate")
        with self.assertRaises(EgressFault) as caught:
            egress.step_and_publish(0, True, True)
        self.assertEqual(caught.exception.reason, "release_confirmed")

    def test_completion_before_ack_faults(self):
        _, _, egress, _ = self.make_release_egress()
        _, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        with self.assertRaises(EgressFault) as caught:
            egress.on_setup_event(
                self.setup_event("setup_completed", envelope["request_id"],
                                 action="mode", value="POSCTL",
                                 native_mode="POSCTL"),
                INFO, info_value=INFO, error_value=ERROR)
        self.assertEqual(caught.exception.reason, "release_completion_without_ack")

    def test_completion_mismatch_faults(self):
        _, _, egress, _ = self.make_release_egress()
        _, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        rid = envelope["request_id"]
        egress.on_setup_event(self.setup_event("native_ack", rid, accepted=True,
                                               stage="simple"),
                              INFO, info_value=INFO, error_value=ERROR)
        with self.assertRaises(EgressFault) as caught:
            egress.on_setup_event(
                self.setup_event("setup_completed", rid, action="mode",
                                 value="POSCTL", native_mode="AUTO.RTL"),
                INFO, info_value=INFO, error_value=ERROR)
        self.assertEqual(caught.exception.reason, "release_completion_mismatch")

    def test_native_reject_faults_closed(self):
        _, _, egress, _ = self.make_release_egress()
        _, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="AUTO.LAND", expected_native_mode="AUTO.LAND")
        with self.assertRaises(EgressFault) as caught:
            egress.on_setup_event(
                self.setup_event("native_ack", envelope["request_id"],
                                 accepted=False, stage="simple"),
                INFO, info_value=INFO, error_value=ERROR)
        self.assertEqual(caught.exception.reason, "release_rejected")

    def test_wrong_stage_faults(self):
        _, _, egress, _ = self.make_release_egress()
        _, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        rid = envelope["request_id"]
        with self.assertRaises(EgressFault) as caught:
            egress.on_setup_event(
                self.setup_event("native_ack", rid, accepted=True, stage="land"),
                INFO, info_value=INFO, error_value=ERROR)
        self.assertEqual(caught.exception.reason, "release_ack_stage_mismatch")

    def test_foreign_and_other_writer_events(self):
        _, _, egress, _ = self.make_release_egress()
        _, envelope = egress.request_release(owns_control=True, state_fresh=True,
            mode="POSCTL", expected_native_mode="POSCTL")
        rid = envelope["request_id"]
        foreign = self.setup_event("native_ack", rid, accepted=True, stage="simple")
        foreign["run_id"] = "run-b"
        self.assertEqual(
            egress.on_setup_event(foreign, INFO, info_value=INFO, error_value=ERROR),
            "ignored")
        with self.assertRaises(EgressFault) as caught:
            egress.on_setup_event(
                self.setup_event("native_ack", rid + 99, accepted=True, stage="simple"),
                INFO, info_value=INFO, error_value=ERROR)
        self.assertEqual(caught.exception.reason, "other_setup_writer_event")

    def test_setup_events_without_release_are_ignored(self):
        _, _, egress, _ = self.make_release_egress()
        self.assertEqual(
            egress.on_setup_event(self.setup_event("native_ack", 1, accepted=True,
                                                   stage="simple"),
                                  INFO, info_value=INFO, error_value=ERROR),
            "ignored")
        self.assertIsNone(egress.release)


if __name__ == "__main__":
    unittest.main()
