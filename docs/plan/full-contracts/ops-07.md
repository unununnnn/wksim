# Full OPS-07 — Environment feedback contract

Status: **defined, not implemented**. This is the bounded definition slice for GitHub #158. The environment/visual decision is approved, but the approval is not a contact-model or full environment acceptance.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:75`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-07`, `followup_ids=[158]`.
- Approved decision: `docs/2026-09-07_environment-contract-accepted.md` and the recorded #9 decision response. It selects WSL static terrain/collision authority, UE display from the same version/hash configuration, explicit ENU/metres/origin, no epoch hot changes, and explicit freeze/recovery for missing/expired required dynamic feedback.
- `docs/plan/remaining-gates-proposal.md` supplies the proposed plane/box first slice but does not itself implement contact forces, friction, penetration resolution or a dynamic-object model.
- `Simulator/wksim_runtime/scene_clock.py` proves an existing joint time/fault seam: committed ticks, synchronized barriers, suspension and explicit repair/recovery. It is not an environment query implementation.
- Existing UE/P450 and Hex paths are display/geometry evidence. They do not make the city or visual fixture an authoritative collision world.

## Atomic scope

| ID | Environment capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-07-A | Static terrain/scene geometry | `partial`: the environment contract fixes the authority boundary and a candidate plane/box; no production scene query is owned | Versioned scene source/hash, ENU/metre geometry, origin, deterministic query and startup mismatch rejection |
| OPS-07-B | Collision/contact feedback | `blocked`: no accepted terrain/contact solver or force/penetration semantics | Contact input/output, body/geometry identity, normal/penetration units, solver/source and physical response evidence |
| OPS-07-C | Dynamic objects/environment changes | `blocked`: no dynamic object source, schedule or authority-time update path | Versioned changes, valid step interval, ordering, collision update and stale/missing behavior |
| OPS-07-D | Feedback freshness/expiry | `partial`: approved rule and several stream freshness checks exist; environment feedback is not wired into physics | `valid_from_step`/`valid_until_step`, step/epoch identity, one-step or approved age budget and precise reject/freeze result |
| OPS-07-E | Joint freeze and explicit recovery | `partial`: `SceneClock` supports faulted recoverable boundaries; no environment-specific admission/repair is connected | Required-feedback loss freezes only the affected joint scene at a completed boundary; explicit new valid feedback and recovery are required |
| OPS-07-F | UE/RGB mirror separation | `partial`: approved contract and existing display bridge keep visual loss off the physics clock; no complete environment/visual identity audit exists | Same scene hash/epoch/step in physics and display manifests, with display lag/loss unable to alter authoritative physics |

## Environment contract

Every loaded environment must have a manifest containing:

```text
schema, scene_id, scene_hash, source/license identity, coordinate_frame=ENU,
unit=metre, origin, static geometry, dynamic-object schedule,
authority epoch/step/time, valid intervals, collision/query version,
physics authority, visual mirror identity and supported feedback fields
```

The WSL physics side is the only authority for terrain, contact and truth. UE consumes a matching manifest and state as an asynchronous visual mirror. A scene or geometry mismatch is rejected before the run; scene configuration is immutable within an epoch.

### Query and feedback envelope

The minimum environment feedback envelope is:

```text
scene_id, scene_hash, epoch, step, sim_time_ns,
valid_from_step, valid_until_step, body_id, geometry_id,
contact_point_enu_m, normal_enu, penetration_m, source_identity
```

Optional force/friction/velocity fields require their own source and units; they are not implied by `penetration_m`. The query must state whether a no-contact result is a valid observation or an unavailable result. A finite contact point alone is not proof that the vehicle dynamics consumed it.

### Freshness, freeze and recovery

1. Static geometry is accepted only for the declared scene hash and current epoch. No hot change is allowed.
2. Dynamic feedback is valid only for its declared step interval and matching epoch/scene/body identity. Out-of-order, foreign, missing or expired required feedback is rejected.
3. If required feedback expires after a completed authoritative step, the affected joint scene freezes at that boundary and records the exact reason. It does not roll back a committed model step or silently reuse an old contact.
4. Recovery is an explicit state transition after a fresh valid feedback envelope and the existing synchronized input/barrier conditions are proven. It does not auto-resume or replay commands.
5. UE/RGB transport loss or stale display data does not freeze physics under this contract. The display becomes stale and may recover with current data; it cannot provide collision truth.

### Failure semantics

Keep `scene_not_found`, `scene_hash_mismatch`, `invalid_geometry`, `unsupported_query`, `foreign_epoch`, `stale_feedback`, `future_feedback`, `out_of_order`, `contact_invalid`, `feedback_unavailable`, `scene_frozen`, `recovery_required`, `display_stale` and `physics_completed` distinct. `physics_completed` means the authoritative step committed with the required inputs; it does not mean a render or contact query succeeded.

## Evidence-backed follow-up slices

These are proposed successors; this ticket adds no contact solver, terrain asset or dynamic object.

1. **Static query seam (owner: physics/environment maintainer):** implement the smallest versioned plane/box query using the approved ENU/metre/hash manifest. Reserve exact core files and add geometry/unit/hash negatives before connecting flight code.
2. **Contact response (owner: physics maintainer):** freeze the contact force/penetration/friction source and budget, then connect the query to the authoritative model. Do not infer a solver from UE collision or a screenshot.
3. **Dynamic updates and expiry (owner: joint-runtime maintainer):** add step-bounded dynamic objects and required-feedback expiry to the existing `SceneClock`/joint lifecycle, preserving no-rollback and explicit recovery semantics.
4. **Visual mirror audit (owner: UE/validation maintainer):** bind the same scene manifest to UE and RGB, then prove display lag/loss cannot alter physics; static RGB/Hex fixtures remain insufficient for contact acceptance.
5. **Real scene slice (owner: runtime/validation maintainer):** run one approved slope/obstacle case with raw geometry queries, contact/vehicle truth, scene epoch/step and clean stop/recovery evidence. #29's #23 numerical prerequisite remains unchanged.

No current command implements the complete environment feedback path. The approved decision releases the design gate; it does not authorize an unbounded implementation or flight.

## Non-goals and preserved blockers

- No terrain, collision solver, dynamic object, force/friction model or environment runtime is implemented here.
- The approved static WSL authority / UE mirror / RGB asynchronous policy is recorded; it does not close #9, #29 or the Full row.
- Existing `SceneClock` and display freshness evidence are not relabelled as contact acceptance. #23/G6, #56, plugin ABI and hardware boundaries remain unchanged.
- `full_complete` remains `false` for OPS-07 and for the project.
