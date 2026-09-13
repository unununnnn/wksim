# #102/#39 trajectory scene-admission contract

Status: offline geometry-admission slice only. This document records the boundary
for the `ego_scene_admission.py` seam. It does not close #102 or #39 and does not
claim UE, SITL, ROS, a planner, a socket, a wall clock, physical force response,
tracking error, controller lag, or flight safety.

> **Revision note (G3 frontier P1 closure).** The clearance gate now runs a
> CONTINUOUS certificate by default (`strict_continuous=True`) instead of
> sampling only. The audit
> `validation/coordination/ds-g3-closure-frontier-20260913-01/` showed that a
> 10 ms sampled polyline can pass while the continuous curve intrudes the margin
> by 0.10 m (its alternating-control-point witness); that payload is now rejected
> as `continuous_clearance_unproven`. The sampled polyline remains the evidence
> on the explicitly requested legacy path (`strict_continuous=False`), where the
> old `sampled_segment_checked` / `continuous_proof=False` labelling is unchanged.

## The gap this slice closes

Each existing committed piece stops one step short of admitting a planner
trajectory against the scene:

- `Simulator/wksim_runtime/bspline_tcp_envelope.py` (`BsplineTcpDecoder`)
  guarantees transport fidelity only; its own contract states downstream
  admission is narrower than envelope validity.
- `Simulator/wksim_planning/ego_bspline_bridge.py` (`bridge_bspline`) converts
  the decoded mapping into an `(EgoSpline, trajectory_id, start_tick)` triple but
  performs no scene geometry check.
- `Simulator/wksim_runtime/planner_scene_binding.py` (`PlannerSceneBinding`)
  exposes only point-versus-AABB contact queries, not a swept-trajectory gate.
- `Simulator/wksim_planning/ego_trajectory_adapter.py` (`EgoTrajectoryAdapter`)
  activates any spline it is handed; it has no obstacle/map knowledge.

`Simulator/wksim_planning/ego_scene_admission.py` closes exactly that gap and
nothing more: it bridges the decoded mapping, checks the resulting `EgoSpline`
against the committed `ego-single-box-v1` obstacle clearance and map envelope —
sampled polyline plus, by default, a continuous control-hull certificate — and
only on a pass calls `EgoTrajectoryAdapter.replan_and_activate` exactly once.

## Authority and identity

Geometry and scene identity come from the committed binding
`EGO_SINGLE_BOX_BINDING` (`Simulator/wksim_runtime/planner_scene_binding.py`),
which wraps `Simulator/wksim_planning/scene_profile.py`. This module copies no
obstacle, map, vehicle, or clearance constants; it reads them from
`binding.profile`. The identity it reports is the committed one:

| Field | Value |
| --- | --- |
| `scene_id` | `ego-single-box-v1` |
| `scene_hash` | `40ee928113c1ad6b2f9987c01506ee34171bd15099e6e7c9425496498cb8d0ba` |
| `profile_hash` | `49da4cccaf3c172c510daa3cc3bd0ddad521669c4d64f3c8bc1a7fe71d9730f7` |
| `geometry_id` | `ego-single-box-v1:obstacle` |
| obstacle AABB | min `(-0.5, -1.0, 0.0)`, max `(0.5, 1.0, 5.5)` |
| map bounds | min `(-10.0, -6.0, 0.0)`, max `(10.0, 6.0, 6.0)` |
| `vehicle_radius` | `0.35` |
| `required_clearance` | `0.30` |
| clearance margin | `0.65` (= `vehicle_radius + required_clearance`) |
| frame / units | `map` / `ENU` / metres / seconds |

The module imports only committed modules (`ego_bspline_bridge`, `ego_evaluator`,
`ego_trajectory_adapter`, `trajectory_session`, `scene_profile`,
`planner_scene_binding`). It deliberately does **not** import the TCP envelope
module: it consumes the decoder's *output mapping* by data-flow, so this seam is
independent of that module's internals.

## Input contract

The admission input is the **already-decoded bridge mapping** — the dictionary
produced by `BsplineTcpDecoder.decode_frame` / `read_frame` (its
`_to_bridge_mapping` output), not raw bytes and not the decoder object. It must
be a `dict` with exactly the eight `BSPLINE_FIELDS` keys (`drone_id`, `order`,
`traj_id`, `start_time`, `knots`, `pos_pts`, `yaw_pts`, `yaw_dt`), with
`start_time` already normalized to integer nanoseconds and `pos_pts` a list of
`(x, y, z)` tuples. `TrajectorySceneAdmission.admit` does not re-validate the
wire envelope; structural enforcement of this shape is delegated to
`bridge_bspline`, and a wrong container or field set is rejected as
`invalid_mapping` before bridging.

## Admission gate order

`TrajectorySceneAdmission` is constructed against one `EgoTrajectoryAdapter`
(hence one `TrajectorySession`), one committed `PlannerSceneBinding`, a fixed
authority-clock `anchor_ns`, an optional `sample_period_s`, and an optional
`strict_continuous` flag (**default `True`**: the continuous certificate is
required for a PASS; `False` restores the legacy sampled-only gate explicitly).
Construction is fail-closed: a non-adapter (`invalid_adapter`), a non-binding
(`invalid_binding`), a negative/non-integer anchor (`invalid_anchor`), a
non-positive/non-finite grid or a non-bool `strict_continuous` (`invalid_grid`)
is rejected before any admission.
The session's stable identity tuple `(run_id, mission_id, uav_id,
control_epoch)` is pinned at construction from `adapter.session.identity`.

`admit(mapping, *, identity, event_sequence, current_tick, fallback_yaw)` runs a
fixed, fail-closed order. **No step mutates the adapter or session on failure.**

1. **Identity/epoch gate** — `identity` is parsed with `Identity.from_value` and
   its stable tuple must equal the pinned tuple, else `identity_mismatch`. (The
   planner generation is intentionally *not* pinned here — it advances per
   replan; it is enforced downstream by the adapter/session.)
2. **Mapping-shape gate** — exact `dict` + `BSPLINE_FIELDS`, else
   `invalid_mapping`.
3. **Bridge gate** — `bridge_bspline(mapping, anchor_ns=self.anchor_ns,
   current_tick=current_tick)` enforces payload shape, `drone_id == 0`,
   `order == 3`, knot cardinality, `traj_id` range, empty yaw, and the
   authority-clock anchor / 1 ms-grid / not-in-past checks. Any `BridgeError` is
   re-raised as `bridge_rejected` with `.bridge_reason` preserved.
4. **Scene gate** — `assess_spline_clearance` over the sampled polyline AND, by
   default, the continuous control-hull certificate (below). A sampled shortfall
   is `clearance_violation` (obstacle) or `map_violation` (envelope); an
   unprovable continuous certificate is `continuous_clearance_unproven`, with the
   honest `SceneClearanceReport` (and its `continuous_certificate`) attached.
5. **Atomic activation** — only if every gate passed: a **single**
   `adapter.replan_and_activate(identity, event_sequence, spline,
   trajectory_id, start_tick, fallback_yaw)`. An `(AdapterError, ValueError,
   OverflowError)` here is re-raised as `adapter_rejected` (report attached).

Returns `(report, accepted_trajectory_id)` on a pass; raises
`SceneAdmissionError` otherwise.

## Deterministic sampling grid

`_sample_times(duration, step)` builds the grid `0, step, 2*step, …` while
`n*step < duration`, then appends the literal `duration`. The first entry is
therefore exactly `0.0` and the last is exactly `duration` — the curve's domain
endpoints are always evaluated (the final segment may be shorter than `step`).
The endpoint reserves one sample slot, so a duration exactly equal to
`(MAX_ADMISSION_SAMPLES - 1) * step` is allowed and produces exactly
`MAX_ADMISSION_SAMPLES` samples; a duration strictly above that boundary (and,
in particular, `MAX_ADMISSION_SAMPLES * step`) fails closed with
`invalid_grid`. The boundary uses the same direct floating-point `n*step`
comparison as the grid, so adjacent representable durations are classified
without a rounded `duration / step` count. Every returned grid is strictly
increasing and has `sample_count <= MAX_ADMISSION_SAMPLES`.

The default step is `DEFAULT_SAMPLE_PERIOD_S = 0.010 s`, reused from the
adapter's `SAMPLE_PERIOD_S` streaming cadence purely as a deterministic
evaluation grid. **A stride is not a safety parameter** (see "Honest evidence"
below); the sampled grid is now a fast necessary condition, not the deciding
evidence, on the default strict path.

## Continuous control-hull certificate (default gate)

`certify_continuous_clearance(spline, *, binding)` (and the internal builder used
by the gate) certifies the WHOLE continuous curve without sampling it:

- A degree-`p` B-spline restricted to a knot interval `[u_k, u_{k+1})` is a convex
  combination of its active control points `P_{k-p}..P_k`, so the curve there lies
  in their convex hull and hence in their axis-aligned bounding box (AABB).
- The certificate walks every knot span index `j` of the evaluation domain
  `[u_p, u_{m-p}]` and takes the AABB of the active window `P_{j-p}..P_j` (the
  plain `p+1`-point window, upstream `evaluateDeBoor`'s span-`j` set). Any
  repeated (non-increasing) knot is rejected fail-closed as `non_monotone_knots`
  BEFORE the walk, so every certified interval is a strictly increasing span;
  the walk's repeated-knot grouping and degenerate-span skip are defensive only
  (unreachable), not a live soundness argument.
- Per interval it requires `aabb_gap(control_box, obstacle) - vehicle_radius >=
  required_clearance` on the obstacle and `inset_clearance(control_box, map
  inset) >= 0.0` **per axis** on the map envelope. The certificate passes only
  when EVERY interval passes, so its interval cover is a gap-free bound on every
  instant of the curve — including curvatures a finite time grid straddles.
- Malformed internal structure (knot cardinality, non-monotone knots, degenerate
  domain, no non-degenerate interval) FAILS CLOSED: `proven=False` with a
  `structural_reason`, no PASS, no clearance claim.
- Conservatism is one-directional: the AABB is an outer approximation of the hull
  and the gap test is a box test, so some genuinely safe curves are rejected;
  an intruding curve is never accepted. Documented in `non_claims` as such.
- Cost is `O(num_control_points)` time and `O(interval_count)` space, with no
  iteration over time and no native/ROS/planner work.

`ContinuousClearanceCertificate` fields: `proven`, `evidence_kind`
(`convex_hull_span_certified`), `order`, `control_point_count`, `knot_count`,
`interval_count`, `domain_start_u`, `domain_end_u`, `obstacle_hull_gap`,
`min_net_obstacle_clearance`, `min_hull_inset_clearance`, `required_clearance`,
`vehicle_radius`, `structural_reason`, `intervals` (each
`(start_u, end_u, span_index_j, last_knot_index)`; the active control window is
`P_{span_index_j-order}..P_{last_knot_index}`, i.e. upstream `evaluateDeBoor`'s
span-`j` set), `non_claims`.

## Clearance and map-envelope determination

Threshold semantics are the existing `vehicle_radius + required_clearance`
throughout (margin `0.65` m); nothing new is invented.

- **Obstacle surface** — for every adjacent sample pair `(p[i], p[i+1])` the gate
  calls `scene_profile.segment_clearance(p[i], p[i+1], profile=profile)`, which
  is the exact minimum segment↔AABB surface distance (split at face crossings,
  sampling-independent within a segment) minus `vehicle_radius`. It must be
  `>= required_clearance` (`0.30`). `min_obstacle_clearance` is the minimum over
  all segments.
- **Map envelope** — for every sampled point the gate computes the inward face
  distance to `map_bounds`, `min over axes of min(c - lo, hi - c)`, and requires
  it minus `vehicle_radius` to be `>= required_clearance`, i.e. each centre must
  sit at least `0.65` m inside every map face. Because the inset region is a
  convex AABB, when both endpoints of every segment satisfy this the whole
  segment does too — exact for the polyline. A point outside the map yields a
  negative inward distance, so one formula catches both strict exit and margin
  shortfall. `min_envelope_clearance` is the minimum over all samples.

The recorded `violation` is the **first** failure in time order
(`map_envelope` or `obstacle_clearance`, with index, time, clearance, and
threshold); the scan still completes so `min_obstacle_clearance` and
`min_envelope_clearance` are full-coverage evidence.

## Atomic activation boundary

The only adapter interaction is the single `replan_and_activate` in step 5. The
adapter re-checks identity + current generation, `trajectory_id` strictly
increasing, `start_tick` strictly greater than the highest observed tick, and a
positive finite duration, then calls `session.replan_and_accept`, which validates
event-sequence strictly increasing, generation, a non-empty interval, and a
non-terminal state — **all before mutating any session field**. Consequently:

- a failure at gates 1–4 never calls the adapter at all (**zero** adapter calls);
- a failure at gate 5 (`adapter_rejected`) still leaves the session's `state`,
  `generation`, `last_event_sequence`, and command high-water **unchanged**
  (zero mutation);
- a pass commits identity/epoch/tick/generation/trajectory atomically and
  preserves the caller-supplied `run_id`/`mission_id`/`uav_id`/`control_epoch`,
  the monotonic authority tick, the session event sequence, and the upstream
  `trajectory_id`.

## Honest evidence: what a PASS does and does not mean

The report carries two constant families:

- **Strict path (default)** — `evidence_kind = "convex_hull_span_certified"` and
  `continuous_proof = True`. A PASS then means:

  > every knot interval's control-point AABB keeps `>= 0.30 m` net clearance from
  > the obstacle AABB and stays inside the map inset by `vehicle_radius +
  > required_clearance` on every axis, so the continuous B-spline curve is proven
  > clear for the committed geometry at every instant.

  It does **not** claim dynamics, tracking error, controller lag, force/impulse,
  sensor behaviour, planner intent, or flight safety; the vehicle extent behind
  `vehicle_radius` is assumed spherical and the obstacle is assumed to be exactly
  the committed AABB for the whole duration.

- **Legacy sampled path (`strict_continuous=False`)** — `evidence_kind =
  "sampled_segment_checked"` and `continuous_proof = False` (both unchanged). A
  PASS means only:

  > every sampled polyline point sits at least `0.65` m inside the map, and every
  > straight segment between adjacent samples keeps at least `0.30` m net
  > clearance from the obstacle AABB.

  It does **not** prove the continuous B-spline keeps clearance between sample
  instants. This is the mode the audit's witness defeats; it stays available only
  as an explicit opt-in.

Either way, a not-admitted strict report keeps the certificate attached with
`proven=False`, so a caller can distinguish "sampled polyline failed"
(`violation.kind` = `obstacle_clearance` / `map_envelope`) from "continuous curve
could not be proven" (`violation.kind` = `continuous_clearance_unproven`).

## Error reasons

`SceneAdmissionError.reason` is one of:

| Reason | Trigger |
| --- | --- |
| `invalid_adapter` | constructor `adapter` is not an `EgoTrajectoryAdapter` |
| `invalid_binding` | `binding` is not a `PlannerSceneBinding` |
| `invalid_anchor` | `anchor_ns` is not a non-negative integer |
| `invalid_grid` | `sample_period_s` not positive/finite, `strict_continuous` not a strict bool, or grid exceeds `MAX_ADMISSION_SAMPLES` |
| `invalid_spline` | assessment input is not an `EgoSpline`, its duration is not positive/finite, or its internal structure is unreadable |
| `invalid_mapping` | input is not a `dict` with exactly `BSPLINE_FIELDS` |
| `identity_mismatch` | identity unparseable, or stable tuple differs from the pinned session identity |
| `bridge_rejected` | `bridge_bspline` refused the payload/timing (`.bridge_reason` holds its reason) |
| `clearance_violation` | a sampled segment's obstacle clearance `< required_clearance` |
| `map_violation` | a sampled point's envelope clearance `< required_clearance` |
| `continuous_clearance_unproven` | the continuous certificate could not be built or did not prove the required clearance/envelope |
| `adapter_rejected` | the adapter/session refused activation (generation/tick/sequence/state) |

`assess_spline_clearance` raises `SceneAdmissionError` only for malformed inputs
(`invalid_binding` / `invalid_grid` / `invalid_spline`); a clearance, map, or
certificate shortfall is returned as data (`report.admitted is False` +
`violation`), never raised, so callers can inspect the honest evidence.

`Simulator/wksim_runtime/planner_transport_pump.py` maps every reason to a pump
outcome; `continuous_clearance_unproven` maps to `rejected_continuous` (it is
deliberately NOT folded into `rejected_clearance`).

## `SceneClearanceReport` fields

Immutable (frozen dataclass): `admitted`, `evidence_kind`
(`"convex_hull_span_certified"` on a strict pass, else
`"sampled_segment_checked"`), `continuous_proof` (`True` only on a strict pass),
`scene_id`, `scene_hash`, `geometry_id`, `profile_hash`, `vehicle_radius`,
`required_clearance`, `clearance_margin`, `sample_period_s`, `duration_s`,
`sample_count`, `segment_count`, `start_point` (= `position_at(0)`),
`end_point` (= `position_at(duration)`), `min_obstacle_clearance`,
`min_envelope_clearance`, `violation` (first failure mapping or `None`),
`non_claims`, and `continuous_certificate` (the
`ContinuousClearanceCertificate`, or `None` on the legacy path).

## Non-claims

This slice does **not**:

- claim continuous clearance on the legacy `strict_continuous=False` path
  (sampled polyline only); the strict path proves the geometric continuous curve
  by convex-hull bounding and claims nothing beyond that geometry;
- claim dynamics, tracking error, controller lag, or flight safety;
- produce or claim force, impulse, damping, or any physical contact response;
- read or drive `Terrain15D` / terrain-height — the obstacle is a vertical AABB,
  not terrain support;
- claim UE, SITL, ROS, DDS, a planner, a socket, or a flight;
- read a wall clock;
- mint any identifier (`run_id`, `mission_id`, `epoch`, `request_id`,
  `command_id`, `trajectory_id` are all caller-supplied or session-owned).

## Verification boundary

`validation/test_ego_scene_admission.py` (42 tests, pure Python, no ROS/planner/
socket/SITL/UE/MATLAB/wall clock) verifies this contract:

- `ClearanceAssessmentTests` — clear polyline admitted; obstacle collision
  rejected; envelope-margin (0.1 m from the ceiling) and strictly-outside-map
  rejected; tail dip into the obstacle rejected; the grid includes the exact
  `0.0` / `duration` endpoints and the report's `start_point`/`end_point` equal
  `position_at(0)` / `position_at(duration)`; honest labelling in BOTH modes;
  identity fields sourced from the committed binding; fail-closed malformed
  inputs; the `MAX_ADMISSION_SAMPLES` bound; non-bool `strict_continuous`.
- `ContinuousCertificateTests` — the audit's 0.20 m alternating-control-point
  witness is rejected as `continuous_clearance_unproven` with its sampled grid
  still clean, independently cross-checked against a dense scan and stable under
  every stride; safe parallel and small-sinusoid curves are proved; exact
  threshold equality (obstacle gap and map inset, including the adjacent double);
  structural failures and non-monotone knots fail closed; legacy mode still
  admits and labels the witness honestly; interval cover is gap-free and exact
  over `[u_p, u_{m-p}]`.
  A strict rejection at the ulp boundary (sampled gate rejects while the
  certificate still proves) never publishes the certified-pass labels
  (`continuous_proof` stays `False`, evidence stays `sampled_segment_checked`).
- `AdmissionWiringTests` — a pass activates the adapter **exactly once** with the
  bridged spline/`trajectory_id`/`start_tick`; collision, map, continuous,
  identity, bridge, and mapping failures never call the adapter and leave the
  session unchanged; adapter/session rejections roll back without mutation;
  successive admissions preserve the atomic identity/epoch/tick/sequence
  boundary; construction validates adapter/binding/anchor/grid/strict flag.

`validation/test_planner_transport_pump.py` additionally covers the runtime
mapping: the witness frame is recorded as `rejected_continuous` with the two
commits (transport consumed, session untouched) explicit.

The related committed suites (`test_ego_trajectory_adapter`,
`test_ego_bspline_bridge`, `test_scene_profile`, `test_planner_scene_binding`)
continue to pass; they are exercised as dependencies, not modified. These tests do
not start `JointPhysics`, a model worker, ROS/DDS, SITL, UE, or a flight.
