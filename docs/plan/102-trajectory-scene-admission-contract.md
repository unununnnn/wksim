# #102/#39 trajectory scene-admission contract

Status: offline geometry-admission slice only. This document records the boundary
for the `ego_scene_admission.py` seam. It does not close #102 or #39 and does not
claim UE, SITL, ROS, a planner, a socket, a wall clock, physical force response,
or — critically — continuous-trajectory safety.

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
against the committed `ego-single-box-v1` obstacle clearance and map envelope,
and only on a pass calls `EgoTrajectoryAdapter.replan_and_activate` exactly once.

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
authority-clock `anchor_ns`, and an optional `sample_period_s`. Construction is
fail-closed: a non-adapter (`invalid_adapter`), a non-binding
(`invalid_binding`), a negative/non-integer anchor (`invalid_anchor`), or a
non-positive/non-finite grid (`invalid_grid`) is rejected before any admission.
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
4. **Scene gate** — `assess_spline_clearance` over the sampled polyline (below).
   A shortfall is `clearance_violation` (obstacle) or `map_violation`
   (envelope), with the honest `SceneClearanceReport` attached to the error.
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
evaluation grid. **This is not a claim that a 10 ms stride is sufficient for
continuous-curve safety** (see "Honest evidence" below).

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

Every report carries `evidence_kind = "sampled_segment_checked"` and
`continuous_proof = False` (both constant). A PASS means only:

> every sampled polyline point sits at least `0.65` m inside the map, and every
> straight segment between adjacent samples keeps at least `0.30` m net
> clearance from the obstacle AABB.

It does **not** prove the continuous B-spline keeps clearance between sample
instants: a cubic B-spline does not in general coincide with the chords between
its samples, so the true curve can deviate from the checked polyline. Raising
the sample density narrows the gap but can never turn a sampled check into a
continuous guarantee. No result from this module is a continuous-trajectory
safety proof.

## Error reasons

`SceneAdmissionError.reason` is one of:

| Reason | Trigger |
| --- | --- |
| `invalid_adapter` | constructor `adapter` is not an `EgoTrajectoryAdapter` |
| `invalid_binding` | `binding` is not a `PlannerSceneBinding` |
| `invalid_anchor` | `anchor_ns` is not a non-negative integer |
| `invalid_grid` | `sample_period_s` not positive/finite, or grid exceeds `MAX_ADMISSION_SAMPLES` |
| `invalid_spline` | assessment input is not an `EgoSpline`, or its duration is not positive/finite |
| `invalid_mapping` | input is not a `dict` with exactly `BSPLINE_FIELDS` |
| `identity_mismatch` | identity unparseable, or stable tuple differs from the pinned session identity |
| `bridge_rejected` | `bridge_bspline` refused the payload/timing (`.bridge_reason` holds its reason) |
| `clearance_violation` | a sampled segment's obstacle clearance `< required_clearance` |
| `map_violation` | a sampled point's envelope clearance `< required_clearance` |
| `adapter_rejected` | the adapter/session refused activation (generation/tick/sequence/state) |

`assess_spline_clearance` raises `SceneAdmissionError` only for malformed inputs
(`invalid_binding` / `invalid_grid` / `invalid_spline`); a clearance or map
shortfall is returned as data (`report.admitted is False` + `violation`), never
raised, so callers can inspect the honest evidence.

## `SceneClearanceReport` fields

Immutable (frozen dataclass): `admitted`, `evidence_kind`
(`"sampled_segment_checked"`), `continuous_proof` (`False`), `scene_id`,
`scene_hash`, `geometry_id`, `profile_hash`, `vehicle_radius`,
`required_clearance`, `clearance_margin`, `sample_period_s`, `duration_s`,
`sample_count`, `segment_count`, `start_point` (= `position_at(0)`),
`end_point` (= `position_at(duration)`), `min_obstacle_clearance`,
`min_envelope_clearance`, `violation` (first failure mapping or `None`), and
`non_claims`.

## Non-claims

This slice does **not**:

- claim continuous-trajectory / continuous-curve safety (sampled polyline only);
- produce or claim force, impulse, damping, or any physical contact response;
- read or drive `Terrain15D` / terrain-height — the obstacle is a vertical AABB,
  not terrain support;
- claim UE, SITL, ROS, DDS, a planner, a socket, or a flight;
- read a wall clock;
- mint any identifier (`run_id`, `mission_id`, `epoch`, `request_id`,
  `command_id`, `trajectory_id` are all caller-supplied or session-owned).

## Verification boundary

`validation/test_ego_scene_admission.py` (22 tests, pure Python, no ROS/planner/
socket/SITL/UE/MATLAB/wall clock) verifies this contract:

- `ClearanceAssessmentTests` — clear polyline admitted; obstacle collision
  rejected; envelope-margin (0.1 m from the ceiling) and strictly-outside-map
  rejected; tail dip into the obstacle rejected; the grid includes the exact
  `0.0` / `duration` endpoints and the report's `start_point`/`end_point` equal
  `position_at(0)` / `position_at(duration)`; honest
  `sampled_segment_checked` + `continuous_proof=False` labelling; identity fields
  sourced from the committed binding; fail-closed malformed inputs; the
  `MAX_ADMISSION_SAMPLES` bound.
- `AdmissionWiringTests` — a pass activates the adapter **exactly once** with the
  bridged spline/`trajectory_id`/`start_tick`; collision, map, identity, bridge,
  and mapping failures never call the adapter and leave the session unchanged;
  adapter/session rejections roll back without mutation; successive admissions
  preserve the atomic identity/epoch/tick/sequence boundary; construction
  validates adapter/binding/anchor/grid.

The related committed suites (`test_ego_trajectory_adapter`,
`test_ego_bspline_bridge`, `test_scene_profile`, `test_planner_scene_binding`)
continue to pass; they are exercised as dependencies, not modified. These tests
do not start `JointPhysics`, a model worker, ROS/DDS, SITL, UE, or a flight, and
they do not assert any continuous-curve or physical-safety guarantee.
