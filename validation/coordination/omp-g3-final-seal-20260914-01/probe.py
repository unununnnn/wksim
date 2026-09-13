"""Final-seal probe for the G3 continuous-clearance workspace (#102/#39 slice).

Independent read-only verification of the closure of
validation/coordination/ds-g3-continuous-clearance-review-20260913-01 findings
P1, P2-1, P2-2, P2-3, P2-4, plus the seal-specific checkpoints:

  - continuous_proof is published ONLY on a final strict pass
  - ulp-boundary witnesses are not mislabeled as certified passes
  - repeated knots fail closed (non_monotone_knots) before the interval walk
  - the certificate interval tuple (start_u, end_u, span_index_j, last) matches
    the documented span-j semantics and covers the exact domain gap-free
  - every admission reason admit() can raise is mapped; an unknown reason fails
    loudly (RuntimeError), calls no adapter, and spends no event_sequence
  - the legacy strict_continuous=False opt-out is value-by-value compatible
  - contract docs match the implementation (outcome rows, non-claims, counts)

Pure Python, fixed seed, no wall clock, no network, no native/ROS/SITL/UE/MATLAB.
Writes probe-output.json next to itself.  Read-only with respect to the rest of
the repository.
"""
import json
import math
import os
import random
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)

from Simulator.wksim_planning.ego_bspline_bridge import BridgeError  # noqa: E402
from Simulator.wksim_planning.ego_evaluator import EgoSpline, SplineError, UniformBspline  # noqa: E402
from Simulator.wksim_planning.ego_scene_admission import (  # noqa: E402
    ADMISSION_REASONS,
    CONTINUOUS_EVIDENCE_KIND,
    EVIDENCE_KIND,
    TrajectorySceneAdmission,
    assess_spline_clearance,
    certify_continuous_clearance,
)
from Simulator.wksim_planning.ego_trajectory_adapter import EgoTrajectoryAdapter  # noqa: E402
from Simulator.wksim_planning.scene_profile import segment_clearance  # noqa: E402
from Simulator.wksim_planning.trajectory_session import TrajectorySession  # noqa: E402
from Simulator.wksim_runtime.bspline_tcp_envelope import BsplineTcpDecoder, BsplineTcpEncoder  # noqa: E402
from Simulator.wksim_runtime.planner_scene_binding import EGO_SINGLE_BOX_BINDING  # noqa: E402
from Simulator.wksim_runtime.planner_transport_pump import (  # noqa: E402
    _ADMISSION_REASON_TO_OUTCOME,
    PlannerTransportPump,
)
from Simulator.wksim_planning.ego_scene_admission import SceneAdmissionError  # noqa: E402

REQUIRED = EGO_SINGLE_BOX_BINDING.profile.required_clearance      # 0.30
RADIUS = EGO_SINGLE_BOX_BINDING.profile.vehicle_radius            # 0.35
IDENTITY = dict(run_id="run-a", mission_id="mission-a", uav_id=1, control_epoch="epoch-a",
                planner_generation=0, command_high_water=0)
SESSION_ID = "0123456789abcdef0123456789abcdef"
SEED = 20260914

checks = []


def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": detail})


def make_spline(cps, knot_h=0.1):
    return EgoSpline(3, list(UniformBspline(3, cps, knot_h).knots), [tuple(p) for p in cps])


def clear_cps():
    return [(float(i) * 0.5, 3.0, 1.0) for i in range(7)]


def witness_cps():
    return [(1.15 - 0.30 * ((-1) ** i), 0.0, 2.0) for i in range(203)]


def witness_spline():
    cps = witness_cps()
    return EgoSpline(3, list(UniformBspline(3, cps, 0.005).knots), [tuple(p) for p in cps])


def make_mapping(cps, *, traj_id=1, knot_h=0.1):
    knots = list(UniformBspline(3, cps, knot_h).knots)
    return {"drone_id": 0, "order": 3, "traj_id": traj_id,
            "start_time": {"sec": 0, "nanosec": 0}, "knots": knots,
            "pos_pts": [list(p) for p in cps], "yaw_pts": [], "yaw_dt": 0.0}


def make_pump():
    session = TrajectorySession(dict(IDENTITY))
    adapter = EgoTrajectoryAdapter(session)
    decoder = BsplineTcpDecoder(SESSION_ID)
    pump = PlannerTransportPump(adapter, decoder=decoder, anchor_ns=0)
    return session, adapter, decoder, pump


def pump_state(pump):
    return (pump.state, pump.next_event_sequence, pump.last_current_tick,
            pump.session_generation, pump.command_high_water)


# ---------------------------------------------------------------- A. labels
report = assess_spline_clearance(make_spline(clear_cps()))
check("A1 strict pass publishes continuous_proof", report.admitted and report.continuous_proof
      and report.evidence_kind == CONTINUOUS_EVIDENCE_KIND and report.continuous_certificate.proven)

boundary_scenes = [
    ((0.0, 1.6500000000000001, 2.75), "obstacle_clearance"),
    ((3.0, 3.0, 0.6499999999999999), "map_envelope"),
    ((3.0, 3.0, 0.65), "map_envelope"),
]
for point, kind in boundary_scenes:
    r = assess_spline_clearance(make_spline([point] * 7))
    check(f"A2 boundary {point} not mislabeled",
          (not r.admitted) and r.violation["kind"] == kind
          and r.continuous_certificate.proven          # certificate itself proves (ulp boundary)
          and (not r.continuous_proof) and r.evidence_kind == EVIDENCE_KIND,
          detail=f"admitted={r.admitted} proof={r.continuous_proof} kind={r.violation['kind']}")

w = assess_spline_clearance(witness_spline())
check("A3 witness rejected as continuous_clearance_unproven",
      (not w.admitted) and w.violation["kind"] == "continuous_clearance_unproven"
      and (not w.continuous_proof) and w.evidence_kind == EVIDENCE_KIND
      and w.min_obstacle_clearance >= REQUIRED      # sampled grid still clean
      and w.continuous_certificate.min_net_obstacle_clearance < REQUIRED)

wl = assess_spline_clearance(witness_spline(), strict_continuous=False)
check("A4 legacy opt-out still admits witness with honest sampled labels",
      wl.admitted and (not wl.continuous_proof) and wl.evidence_kind == EVIDENCE_KIND
      and wl.continuous_certificate is None and wl.violation is None)

# ------------------------------------------------- B. span-j semantics/cover
generator = random.Random(SEED)
cover_checked = 0
hull_ok = True
tuple_ok = True
for _ in range(120):
    count = generator.randint(4, 10)
    knot_h = generator.choice((0.05, 0.1, 0.2))
    ox = generator.uniform(-3.0, 4.0)
    cps = [(ox + generator.uniform(-1.2, 1.2) + i * knot_h,
            generator.uniform(-2.5, 2.5), generator.uniform(0.4, 5.0)) for i in range(count)]
    spline = make_spline(cps, knot_h)
    cert = certify_continuous_clearance(spline)
    if cert.structural_reason is not None:
        continue
    cover_checked += 1
    knots = tuple(spline.position.knots)
    p = spline.position.order
    n = len(cps) - 1
    expected = [(knots[j], knots[j + 1], j, j) for j in range(p, n + 1)]
    if tuple(cert.intervals) != tuple(expected):
        tuple_ok = False
    if not (cert.intervals[0][0] == knots[p] and cert.intervals[-1][1] == knots[len(cps)]
            and all(cert.intervals[i][1] == cert.intervals[i + 1][0]
                    for i in range(len(cert.intervals) - 1))):
        tuple_ok = False
    duration = spline.duration
    if not (cert.domain_start_u == 0.0 and abs(cert.domain_end_u - duration) <= 1e-12):
        tuple_ok = False
    for start_u, end_u, j, last in cert.intervals:
        active = spline.position._points[j - p:last + 1]
        low = [min(pt[a] for pt in active) for a in range(3)]
        high = [max(pt[a] for pt in active) for a in range(3)]
        for s in range(21):
            pt = spline.position_at(start_u + (end_u - start_u) * s / 20.0)
            for a in range(3):
                if max(low[a] - pt[a], pt[a] - high[a]) > 1e-9:
                    hull_ok = False
check("B1 interval tuple == (u_j, u_{j+1}, j, j) with gap-free exact-domain cover",
      tuple_ok, detail=f"splines checked={cover_checked}")
check("B2 active window P_{j-p}..P_last contains the curve (dense check)", hull_ok)

# ------------------------------------------------------- C. repeated knots
spline = make_spline(clear_cps())
knots = list(spline.position._knots)
knots[5] = knots[4]
spline.position._knots = knots
cert = certify_continuous_clearance(spline)
check("C1 tampered repeated knot fails closed as non_monotone_knots",
      (not cert.proven) and cert.structural_reason == "non_monotone_knots"
      and cert.interval_count == 0)
# A repeated-knot vector cannot be built through the bridge either.
try:
    EgoSpline(3, [0.0] * 4 + [0.05, 0.05, 0.1, 0.15, 0.2, 0.25] + [0.3] * 4,
              [(float(i) * 0.2, 3.0, 1.0) for i in range(10)])
    bridge_blocks = False
except (SplineError, BridgeError, ValueError, ZeroDivisionError):
    bridge_blocks = True
check("C2 repeated-knot vector is not constructible (SplineError)", bridge_blocks)
# And admit() maps the tampered structure to continuous_clearance_unproven
# without ever calling the adapter.
session = TrajectorySession(dict(IDENTITY))
adapter = EgoTrajectoryAdapter(session)
gate = TrajectorySceneAdmission(adapter, anchor_ns=0)
calls = []
real = adapter.replan_and_activate
adapter.replan_and_activate = lambda *a, **k: calls.append(1) or real(*a, **k)
tampered = make_mapping(clear_cps())
tk = list(tampered["knots"])
tk[5] = tk[4]
tampered["knots"] = tk
snap = (session.state, session.generation, session.last_event_sequence, session.last_command_id)
try:
    gate.admit(tampered, identity=dict(IDENTITY), event_sequence=1, current_tick=0, fallback_yaw=0.0)
    admitted_reason = "NO-RAISE"
except SceneAdmissionError as error:
    admitted_reason = error.reason
check("C3 tampered repeated knot rejects at the bridge with zero mutation",
      admitted_reason == "bridge_rejected" and calls == []
      and (session.state, session.generation, session.last_event_sequence,
           session.last_command_id) == snap,
      detail=f"reason={admitted_reason}")

# ------------------------------------------------- D. reason-map completeness
unmapped = set(ADMISSION_REASONS) - set(_ADMISSION_REASON_TO_OUTCOME)
check("D1 unmapped set is exactly the four unreachable reasons",
      unmapped == {"invalid_adapter", "invalid_anchor", "invalid_binding", "invalid_spline"},
      detail=sorted(unmapped))
check("D2 outcome values are pairwise distinct", len(set(_ADMISSION_REASON_TO_OUTCOME.values()))
      == len(_ADMISSION_REASON_TO_OUTCOME))
check("D3 continuous reason maps to its own outcome",
      _ADMISSION_REASON_TO_OUTCOME["continuous_clearance_unproven"] == "rejected_continuous"
      and _ADMISSION_REASON_TO_OUTCOME["continuous_clearance_unproven"]
      not in ("rejected_clearance", "rejected_map"))

# ------------------------------------------------------ E. unknown reason
class StubAdmission:
    def __init__(self, error):
        self._error = error
        self.calls = 0

    def admit(self, *args, **kwargs):
        self.calls += 1
        raise self._error


session, adapter, decoder, pump = make_pump()
real_admission = pump._admission
err = SceneAdmissionError("adapter_rejected", "placeholder")
err.reason = "future_unmapped_reason"
pump._admission = StubAdmission(err)
before = pump_state(pump)
encoder = BsplineTcpEncoder(SESSION_ID)
frame = encoder.encode_frame(make_mapping(clear_cps(), traj_id=1))
raised = None
try:
    pump.feed(frame, identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
except RuntimeError as error:
    raised = str(error)
check("E1 unknown reason raises a reason-naming RuntimeError",
      raised is not None and "future_unmapped_reason" in raised, detail=raised)
check("E2 unknown reason: no adapter activation, no event_sequence spent, no mutation",
      pump._admission.calls == 1 and adapter.trajectory_id == 0
      and (session.state, session.generation, session.last_event_sequence) == ("WAITING", 0, None)
      and pump_state(pump) == before and pump.state == "ACTIVE"
      and decoder.high_water_sequence == 1)          # transport commit honestly consumed
pump._admission = real_admission
outcomes = pump.feed(encoder.encode_frame(make_mapping(clear_cps(), traj_id=2)),
                     identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
check("E3 pump not burned: same legal frame activates on the unconsumed sequence",
      [o.outcome for o in outcomes] == ["activated"] and outcomes[0].event_sequence == 1)

# ------------------------------------------- F. legacy per-value compatibility
legacy_ok = True
generator = random.Random(SEED + 1)
for _ in range(40):
    count = generator.randint(4, 8)
    cps = [(generator.uniform(-4.0, 4.0) + i * 0.4, generator.uniform(1.5, 4.5),
            generator.uniform(0.8, 5.0)) for i in range(count)]
    spline = make_spline(cps, generator.choice((0.05, 0.1)))
    strict = assess_spline_clearance(spline)
    legacy = assess_spline_clearance(spline, strict_continuous=False)
    if not (strict.min_obstacle_clearance == legacy.min_obstacle_clearance
            and strict.min_envelope_clearance == legacy.min_envelope_clearance
            and strict.start_point == legacy.start_point
            and strict.end_point == legacy.end_point
            and strict.sample_count == legacy.sample_count
            and strict.segment_count == legacy.segment_count
            and strict.duration_s == legacy.duration_s
            and legacy.evidence_kind == EVIDENCE_KIND
            and legacy.continuous_proof is False
            and legacy.continuous_certificate is None):
        legacy_ok = False
check("F1 legacy opt-out is value-by-value identical on the sampled fields", legacy_ok)

# ------------------------------------------- G. pump strict-reject atomicity
session, adapter, decoder, pump = make_pump()
g_encoder = BsplineTcpEncoder(SESSION_ID)
witness_frame = g_encoder.encode_frame(
    {"drone_id": 0, "order": 3, "traj_id": 1,
     "start_time": {"sec": 0, "nanosec": 0},
     "knots": list(UniformBspline(3, witness_cps(), 0.005).knots),
     "pos_pts": [list(p) for p in witness_cps()], "yaw_pts": [], "yaw_dt": 0.0})
snap = (session.state, session.generation, session.last_event_sequence, session.last_command_id)
outcomes = pump.feed(witness_frame, identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
o = outcomes[0]
check("G1 witness frame rejected_continuous with honest two-commit record",
      o.outcome == "rejected_continuous" and o.transport_consumed and (not o.session_activated)
      and o.event_sequence is None
      and (session.state, session.generation, session.last_event_sequence,
           session.last_command_id) == snap and pump.next_event_sequence == 1)
outcomes = pump.feed(g_encoder.encode_frame(make_mapping(clear_cps(), traj_id=2)),
                     identity=IDENTITY, current_tick=0, fallback_yaw=0.0)
check("G2 next legal frame reuses the unconsumed event_sequence",
      [x.outcome for x in outcomes] == ["activated"] and outcomes[0].event_sequence == 1)

# ------------------------------------------------------- H. doc consistency
def doc(path):
    with open(os.path.join(REPO, path), encoding="utf-8") as handle:
        return handle.read()


pump_doc = doc("docs/plan/102-planner-transport-pump-contract.md")
adm_doc = doc("docs/plan/102-trajectory-scene-admission-contract.md")
check("H1 pump doc maps continuous_clearance_unproven -> rejected_continuous",
      "| `continuous_clearance_unproven` | `rejected_continuous` |" in pump_doc)
check("H2 pump doc non-claim no longer asserts the old sampled-only honesty bound",
      "geometric continuous-curve control-hull certificate when strict" in pump_doc
      and "sampled_segment_checked` / `continuous_proof=False` honesty bound" not in pump_doc)
check("H3 pump doc verification boundary records rejected_continuous",
      "rejected_continuous" in pump_doc.split("## Verification boundary")[1])
check("H4 admission doc records span-j interval semantics",
      "(start_u, end_u, span_index_j, last_knot_index)" in adm_doc
      and "P_{span_index_j-order}..P_{last_knot_index}" in adm_doc)
check("H5 admission doc states repeated knots fail closed before the walk",
      "rejected fail-closed as `non_monotone_knots`\n  BEFORE the walk" in adm_doc)
check("H6 admission doc test count matches the suite (42)",
      "42 tests" in adm_doc)
check("H7 admission doc keeps the strict/legacy honesty split in non-claims",
      "claim continuous clearance on the legacy `strict_continuous=False` path" in adm_doc)
check("H8 admission doc pins pump mapping of the continuous reason",
      "`continuous_clearance_unproven` maps to `rejected_continuous`" in adm_doc)

passed = sum(1 for c in checks if c["ok"])
output = {
    "seed": SEED,
    "checks": checks,
    "passed": passed,
    "failed": len(checks) - passed,
    "verdict": "PASS" if passed == len(checks) else "FAIL",
}
out_path = os.path.join(os.path.dirname(__file__), "probe-output.json")
with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(output, handle, indent=2, ensure_ascii=False)
    handle.write("\n")
print(f"{passed}/{len(checks)} checks passed -> {output['verdict']}")
sys.exit(0 if passed == len(checks) else 1)
