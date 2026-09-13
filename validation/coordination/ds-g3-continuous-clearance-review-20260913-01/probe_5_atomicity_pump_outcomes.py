"""Probe 5 -- failure atomicity (adapter/session) and pump outcome mapping.

Adversarial questions:
  Q1  On EVERY admission rejection path (including the new strict continuous one),
      is the adapter called ZERO times and is the session snapshot bit-for-bit
      unchanged (state, generation, event sequence, command high-water, identity)?
  Q2  Can a strict rejection burn an event sequence or block the next valid frame?
      A rejection must leave the counter reusable.
  Q3  Does the pump keep the strict gate as its default, and does ``recover`` rebuild
      it identically (no silent degradation to the legacy sampled gate)?
  Q4  Is every admission reason the gate can actually raise a key of the pump's
      outcome mapping, and is ``continuous_clearance_unproven`` mapped to its own
      outcome rather than folded into ``rejected_clearance``?
"""
from __future__ import annotations

from probe_common import (  # noqa: E402
    IDENTITY,
    Probe,
    SceneAdmissionError,
    TrajectorySceneAdmission,
    attempt,
    clear_cps,
    collision_cps,
    count_adapter_calls,
    make_mapping,
    make_session_adapter,
    session_snapshot,
    uniform_knots,
    witness_cps,
    WITNESS_KNOT_H,
)

from Simulator.wksim_planning.ego_scene_admission import ADMISSION_REASONS  # noqa: E402
from Simulator.wksim_planning.ego_trajectory_adapter import EgoTrajectoryAdapter  # noqa: E402
from Simulator.wksim_planning.trajectory_session import TrajectorySession  # noqa: E402
from Simulator.wksim_runtime.bspline_tcp_envelope import (  # noqa: E402
    BsplineTcpDecoder,
    BsplineTcpEncoder,
    pack_frame,
    serialize_envelope_json,
)
from Simulator.wksim_runtime.planner_transport_pump import (  # noqa: E402
    PlannerTransportPump,
)
from Simulator.wksim_runtime.planner_transport_pump import (  # noqa: E402
    _ADMISSION_REASON_TO_OUTCOME,
)

SESSION_ID = "0123456789abcdef0123456789abcdef"
OTHER_SESSION_ID = "fedcba9876543210fedcba9876543210"


def envelope_margin_cps():
    return [(float(i) * 0.5, 3.0, 5.9) for i in range(7)]


def identity_for(session, **overrides):
    return dict(IDENTITY, planner_generation=session.generation, **overrides)


def run_rejection(probe, label, mapping, identity, *, expect_reason, event_sequence=1,
                  current_tick=0):
    session, adapter = make_session_adapter()
    calls = count_adapter_calls(adapter)
    controller = TrajectorySceneAdmission(adapter, anchor_ns=0)
    before = session_snapshot(session)
    result, error = attempt(controller.admit, mapping, identity=identity,
                            event_sequence=event_sequence, current_tick=current_tick,
                            fallback_yaw=0.0)
    reason = getattr(error, "reason", None)
    probe.check(isinstance(error, SceneAdmissionError) and reason == expect_reason,
                f"{label}: rejected with reason {expect_reason}",
                {"reason": reason, "error": None if error is None else str(error)[:120]})
    probe.check(not calls, f"{label}: adapter called ZERO times", {"calls": len(calls)})
    probe.check(session_snapshot(session) == before, f"{label}: session unchanged",
                {"before": before, "after": session_snapshot(session)})
    return reason


def raw_payload(cps, *, traj_id=1, sec=0, nanosec=0, knot_h=0.1):
    return {
        "drone_id": 0,
        "order": 3,
        "traj_id": traj_id,
        "start_time": {"sec": sec, "nanosec": nanosec},
        "knots": uniform_knots(cps, knot_h),
        "pos_pts": [tuple(float(c) for c in point) for point in cps],
        "yaw_pts": [],
        "yaw_dt": 0.0,
    }


def make_pump():
    session = TrajectorySession(dict(IDENTITY))
    adapter = EgoTrajectoryAdapter(session)
    decoder = BsplineTcpDecoder(SESSION_ID)
    pump = PlannerTransportPump(adapter, decoder=decoder, anchor_ns=0)
    return session, adapter, decoder, pump


def main():
    probe = Probe("PROBE-5", "failure atomicity and pump outcome mapping",
                  "probe_5_atomicity_pump_outcomes.json")

    reachable = set()

    # ---- Q1: one rejection per reason, all with zero mutation ---------------
    base_identity = dict(IDENTITY)
    reachable.add(run_rejection(probe, "identity_mismatch",
                                make_mapping(clear_cps()), dict(base_identity, run_id="other"),
                                expect_reason="identity_mismatch"))
    bad_mapping = make_mapping(clear_cps())
    del bad_mapping["knots"]
    reachable.add(run_rejection(probe, "invalid_mapping", bad_mapping, base_identity,
                                expect_reason="invalid_mapping"))
    reachable.add(run_rejection(probe, "bridge_rejected",
                                make_mapping(clear_cps(), traj_id=1, start_time_ns=500_000),
                                base_identity, expect_reason="bridge_rejected"))
    reachable.add(run_rejection(probe, "clearance_violation",
                                make_mapping(collision_cps()), base_identity,
                                expect_reason="clearance_violation"))
    reachable.add(run_rejection(probe, "map_violation",
                                make_mapping(envelope_margin_cps()), base_identity,
                                expect_reason="map_violation"))
    reachable.add(run_rejection(probe, "continuous_clearance_unproven",
                                make_mapping(witness_cps(), knot_h=WITNESS_KNOT_H), base_identity,
                                expect_reason="continuous_clearance_unproven"))

    # invalid_grid is reachable through admit() itself: a positive-but-tiny grid
    # passes construction and then exceeds MAX_ADMISSION_SAMPLES in _sample_times.
    session, adapter = make_session_adapter()
    calls = count_adapter_calls(adapter)
    tiny_grid_controller = TrajectorySceneAdmission(adapter, anchor_ns=0, sample_period_s=1e-100)
    before = session_snapshot(session)
    _, error = attempt(tiny_grid_controller.admit, make_mapping(clear_cps()),
                       identity=base_identity, event_sequence=1, current_tick=0, fallback_yaw=0.0)
    reachable.add(getattr(error, "reason", None))
    probe.check(getattr(error, "reason", None) == "invalid_grid",
                "invalid_grid: grid bound rejection reached through admit()",
                {"reason": getattr(error, "reason", None)})
    probe.check(not calls and session_snapshot(session) == before,
                "invalid_grid: zero adapter calls and unchanged session",
                {"calls": len(calls)})

    # adapter rejection: reuse an already-committed event sequence
    session, adapter = make_session_adapter()
    calls = count_adapter_calls(adapter)
    controller = TrajectorySceneAdmission(adapter, anchor_ns=0)
    controller.admit(make_mapping(clear_cps(), traj_id=1, start_time_ns=0),
                     identity=identity_for(session), event_sequence=1,
                     current_tick=0, fallback_yaw=0.0)
    before = session_snapshot(session)
    _, error = attempt(controller.admit, make_mapping(clear_cps(), traj_id=2, start_time_ns=0),
                       identity=identity_for(session), event_sequence=1,
                       current_tick=0, fallback_yaw=0.0)
    reachable.add(getattr(error, "reason", None))
    probe.check(getattr(error, "reason", None) == "adapter_rejected",
                "adapter_rejected: session-level rejection surfaces as adapter_rejected",
                {"reason": getattr(error, "reason", None)})
    probe.check(session_snapshot(session) == before,
                "adapter_rejected: session rolled back with zero mutation",
                {"before": before, "after": session_snapshot(session)})
    probe.check(len(calls) == 2, "adapter_rejected: the adapter WAS called (gate 5)",
                {"calls": len(calls)})

    # ---- Q2: a strict rejection burns nothing ------------------------------
    session, adapter = make_session_adapter()
    calls = count_adapter_calls(adapter)
    controller = TrajectorySceneAdmission(adapter, anchor_ns=0)
    controller.admit(make_mapping(clear_cps(), traj_id=1, start_time_ns=0),
                     identity=identity_for(session), event_sequence=1,
                     current_tick=0, fallback_yaw=0.0)
    after_first = session_snapshot(session)
    _, error = attempt(controller.admit, make_mapping(witness_cps(), traj_id=2,
                                                      knot_h=WITNESS_KNOT_H),
                       identity=identity_for(session), event_sequence=2,
                       current_tick=0, fallback_yaw=0.0)
    probe.check(getattr(error, "reason", None) == "continuous_clearance_unproven",
                "strict rejection after a commit is still continuous_clearance_unproven")
    probe.check(session_snapshot(session) == after_first,
                "strict rejection after a commit does not advance generation/sequence",
                {"before": after_first, "after": session_snapshot(session)})
    # the SAME event sequence must still activate the next valid trajectory
    report, accepted = controller.admit(make_mapping(clear_cps(), traj_id=3, start_time_ns=0),
                                        identity=identity_for(session), event_sequence=2,
                                        current_tick=0, fallback_yaw=0.0)
    probe.check(accepted == 3 and session.last_event_sequence == 2 and report.admitted,
                "the event sequence burned by no rejection is reusable immediately",
                {"accepted": accepted, "last_event_sequence": session.last_event_sequence})
    probe.check(len(calls) == 2, "exactly one adapter call per successful admission",
                {"calls": len(calls)})

    # ---- Q3: pump default is strict and recover preserves it ---------------
    session, adapter, decoder, pump = make_pump()
    probe.check(pump._admission._strict_continuous is True,
                "pump admission gate defaults to strict_continuous=True")
    probe.check(pump._admission._sample_period_s == 0.01,
                "pump admission keeps the default 10 ms grid")
    # poison the pump, then recover and check the rebuilt gate
    poisoner = BsplineTcpEncoder(SESSION_ID)
    payload = raw_payload(clear_cps(), traj_id=1)
    envelope = poisoner.build_envelope(payload)
    envelope["ros1_msg_sha256"] = "0" * 64
    outcomes = pump.feed(pack_frame(serialize_envelope_json(envelope)),
                         identity=dict(IDENTITY), current_tick=0, fallback_yaw=0.0)
    probe.check(pump.state == "POISONED" and outcomes[0].outcome == "poison",
                "pump poisoned by a transport-validation failure",
                {"outcomes": [outcome.outcome for outcome in outcomes]})
    recovered = PlannerTransportPump.recover(pump, transport_session_id=OTHER_SESSION_ID)
    probe.check(recovered._admission._strict_continuous is True
                and recovered._admission._sample_period_s == 0.01,
                "recover rebuilds the gate with the same strict mode and grid",
                {"strict": recovered._admission._strict_continuous,
                 "period": recovered._admission._sample_period_s})

    # ---- Q4: pump outcome mapping over a real byte stream ------------------
    session, adapter, decoder, pump = make_pump()
    encoder = BsplineTcpEncoder(SESSION_ID)
    witness_frame = encoder.encode_frame(raw_payload(witness_cps(), traj_id=1,
                                                     knot_h=WITNESS_KNOT_H))
    first_sequence = pump.next_event_sequence
    outcomes = pump.feed(witness_frame, identity=dict(IDENTITY), current_tick=0, fallback_yaw=0.0)
    probe.check(len(outcomes) == 1 and outcomes[0].outcome == "rejected_continuous",
                "witness frame -> rejected_continuous",
                {"outcomes": [outcome.outcome for outcome in outcomes]})
    outcome = outcomes[0]
    probe.check(outcome.transport_consumed and not outcome.session_activated
                and outcome.event_sequence is None and outcome.trajectory_id == 1,
                "rejected_continuous keeps the two-commit boundary explicit",
                {"transport_consumed": outcome.transport_consumed,
                 "session_activated": outcome.session_activated,
                 "event_sequence": outcome.event_sequence})
    probe.check(outcome.detail == "continuous_clearance_unproven",
                "rejected_continuous detail carries the admission reason",
                {"detail": outcome.detail})
    probe.check(outcome.report is not None
                and outcome.report.violation["kind"] == "continuous_clearance_unproven"
                and outcome.report.continuous_proof is False,
                "rejected_continuous attaches the honest report (no proof claimed)",
                {"violation": None if outcome.report is None else outcome.report.violation})
    probe.check(pump.next_event_sequence == first_sequence,
                "rejected_continuous burns no event sequence",
                {"before": first_sequence, "after": pump.next_event_sequence})
    probe.check((session.state, session.generation, session.last_event_sequence)
                == ("WAITING", 0, None),
                "rejected_continuous leaves the session untouched",
                {"state": session.state, "generation": session.generation})

    clear_frame = encoder.encode_frame(raw_payload(clear_cps(), traj_id=2))
    outcomes = pump.feed(clear_frame, identity=dict(IDENTITY), current_tick=0, fallback_yaw=0.0)
    probe.check(outcomes[0].outcome == "activated"
                and outcomes[0].event_sequence == first_sequence,
                "the next valid frame activates with the sequence the rejection did not burn",
                {"outcome": outcomes[0].outcome, "event_sequence": outcomes[0].event_sequence,
                 "expected": first_sequence})
    activated_identity = dict(IDENTITY, planner_generation=pump.session_generation,
                              command_high_water=pump.command_high_water)

    collision_frame = encoder.encode_frame(raw_payload(collision_cps(), traj_id=3))
    outcomes = pump.feed(collision_frame, identity=activated_identity, current_tick=0,
                         fallback_yaw=0.0)
    probe.check(outcomes[0].outcome == "rejected_clearance",
                "sampled obstacle collision -> rejected_clearance",
                {"outcome": outcomes[0].outcome})
    margin_frame = encoder.encode_frame(raw_payload(envelope_margin_cps(), traj_id=4))
    outcomes = pump.feed(margin_frame, identity=activated_identity, current_tick=0,
                         fallback_yaw=0.0)
    probe.check(outcomes[0].outcome == "rejected_map",
                "sampled envelope shortfall -> rejected_map",
                {"outcome": outcomes[0].outcome})
    # force the bridge rejection with an off-grid start time
    offgrid = encoder.encode_frame(raw_payload(clear_cps(), traj_id=5, nanosec=500_000))
    outcomes = pump.feed(offgrid, identity=activated_identity, current_tick=0, fallback_yaw=0.0)
    probe.check(outcomes[0].outcome == "rejected_bridge",
                "off-grid start time -> rejected_bridge",
                {"outcome": outcomes[0].outcome})
    probe.check(outcomes[0].detail == "bridge_rejected:start_off_grid",
                "rejected_bridge detail carries the bridge reason",
                {"detail": outcomes[0].detail})

    # mapping completeness vs the reachable reason set
    mapped = set(_ADMISSION_REASON_TO_OUTCOME)
    probe.observe("reachable_admission_reasons", sorted(reachable))
    probe.observe("mapped_reasons", sorted(mapped))
    probe.observe("unmapped_admission_reasons", sorted(set(ADMISSION_REASONS) - mapped))
    probe.check(reachable <= mapped,
                "every admission reason reachable through admit() is mapped by the pump",
                {"unmapped_reachable": sorted(reachable - mapped)})
    probe.check(len({_ADMISSION_REASON_TO_OUTCOME["clearance_violation"],
                     _ADMISSION_REASON_TO_OUTCOME["continuous_clearance_unproven"],
                     _ADMISSION_REASON_TO_OUTCOME["map_violation"]}) == 3,
                "clearance / continuous / map rejections keep three distinct outcomes",
                {key: _ADMISSION_REASON_TO_OUTCOME[key]
                 for key in ("clearance_violation", "continuous_clearance_unproven",
                             "map_violation")})
    probe.check(set(ADMISSION_REASONS) - mapped
                == {"invalid_adapter", "invalid_binding", "invalid_anchor", "invalid_spline"},
                "the only unmapped reasons are the constructor-only / unreachable ones",
                {"unmapped": sorted(set(ADMISSION_REASONS) - mapped)})
    return probe.finish()


if __name__ == "__main__":
    raise SystemExit(main())
