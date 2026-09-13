# #102/#39 planner transport pump contract (receive side)

Status: offline receive-side orchestration slice only. This document records the
boundary for `Simulator/wksim_runtime/planner_transport_pump.py`. It does not
close #102 or #39 and does not claim a socket, ROS, a planner, SITL, UE, a flight,
physical force response, crash atomicity, or exactly-once delivery.

## The gap this slice closes

The committed chain stops one step short of a receive loop:

- `Simulator/wksim_runtime/bspline_tcp_envelope.py` (`BsplineTcpDecoder`) turns a
  byte stream into validated bridge mappings and owns the transport sequence.
- `Simulator/wksim_planning/ego_scene_admission.py` (`TrajectorySceneAdmission`)
  gates one decoded mapping through the scene and, on a pass, activates the
  adapter exactly once.

Nothing owned the loop that feeds bytes, drains frames, admits each in order, and
reconciles the transport ledger against the session ledger.
`PlannerTransportPump` closes exactly that loop and nothing more. It is pure and
deterministic: bytes are supplied explicitly by the caller; the pump never opens a
connection, reads a wall clock, or mints an identifier.

## The two-commit transaction boundary (central honesty contract)

Transport receipt and session activation are **two separate atomic commits with a
real gap**, and the pump makes that gap explicit rather than hiding it:

1. `decoder.read_frame()` — the decoder's **public** API — commits the transport
   sequence high-water and removes the frame from the buffer **first**. The pump
   uses only this public API; it never reads or modifies the decoder's private
   buffer, so it cannot and does not interpose admission before that commit.
2. Only then does the pump run the identity/bridge/scene/adapter admission for
   the decoded mapping.

Therefore a frame can be transport-consumed yet never activate the session. When
the pump returns an outcome, it records both sides of the boundary:

| Field | Meaning |
| --- | --- |
| `transport_consumed` | `read_frame()` committed the transport sequence |
| `session_activated` | `replan_and_accept` committed the session |

On any admission rejection the outcome is `transport_consumed=True,
session_activated=False`: the transport sequence and the payload `trajectory_id`
are **burned**, but the pump spends **no** `event_sequence`. The pump provides
**no crash atomicity and no exactly-once guarantee**: if the process stops between
the two commits, the frame and its outcome may be gone from both ledgers.

## Receive loop semantics

`feed(chunk, *, identity, current_tick, fallback_yaw) -> list[FrameOutcome]`:

- `chunk` must be bytes-like (`invalid_chunk`), the pump must be `ACTIVE`
  (`poisoned`), `current_tick` must be an integer in `[0, 2**63-1]` and must not
  regress across feeds (`invalid_tick` / `tick_regressed`), and a well-formed
  caller identity must carry the pump's current `planner_generation`
  (`generation_mismatch`). These checks happen **before** any decoder or pump
  ledger mutation.
- The chunk is appended via `decoder.feed()`, then `read_frame()` is drained until
  it returns `None`. **Fragmentation** (a frame split across feeds) yields no
  outcome until the completing feed; **multiple frames** in one chunk are admitted
  in transport order while the caller generation remains current. After an
  activation advances that generation, later buffered frames remain unread until
  a subsequent feed supplies the new generation.
- Identity parsing is fail-closed for known input/parser errors: a non-Mapping
  value, a missing required key (including `uav_id`), or a `ValueError`,
  `KeyError`, or `TypeError` raised while parsing an external Mapping becomes a
  consumed-frame `rejected_identity` outcome with no session/event mutation.
  `MemoryError` and unrelated exceptions (for example a `RuntimeError` from an
  external Mapping or an internal parser bug) propagate before decoder mutation;
  they are not relabeled as identity rejection and the transport sequence stays
  unchanged. An explicit integer `planner_generation` outside
  `[0, MAX_GENERATION]`, whether supplied by a Mapping or a direct `Identity`,
  remains a caller protocol error and is rejected before decoder mutation with
  `generation_mismatch`.
- The pump passes the caller's `Identity` through unchanged. After an activation,
  the session generation advances; before the next `read_frame()` the pump stops
  draining, leaving later buffered frames for a subsequent feed with the new
  generation. A transport frame can therefore never be consumed on behalf of a
  stale or future caller generation.
- `event_sequence` is a session-scoped ordering counter owned by the pump. It is
  passed to `admit` and **incremented only on a successful activation**, so the
  session's event sequence stays contiguous across rejected frames.
- `initial_event_sequence` and every next event sequence are bounded by
  `MAX_COMMAND_ID`, and an initial value must be strictly greater than the
  session's existing event high-water (`invalid_sequence`). The value
  `MAX_COMMAND_ID` may be spent once when the existing high-water is lower; after
  a successful activation at that value, later feeds fail with
  `PumpError("sequence_exhausted")` before decoder mutation. An invalid initial
  value is rejected before construction completes.
- A session already at `MAX_GENERATION` cannot activate another trajectory.
  Every feed then fails with `PumpError("generation_exhausted")` before tick or
  decoder mutation, so a valid frame cannot become a repeated
  `rejected_adapter`.

## Outcome mapping

| Admission/transport result | `outcome` | consumed | activated |
| --- | --- | --- | --- |
| activation committed | `activated` | True | True |
| `identity_mismatch` | `rejected_identity` | True | False |
| `invalid_mapping` | `rejected_mapping` | True | False |
| `bridge_rejected` | `rejected_bridge` (detail carries the bridge reason) | True | False |
| `invalid_grid` | `rejected_grid` | True | False |
| `clearance_violation` | `rejected_clearance` | True | False |
| `map_violation` | `rejected_map` | True | False |
| `adapter_rejected` | `rejected_adapter` | True | False |
| transport validation failure | `poison` | False | False |

`FrameOutcome` is frozen: `transport_sequence`, `trajectory_id`, `outcome`,
`transport_consumed`, `session_activated`, `event_sequence`, `detail`, `report`
(the admission `SceneClearanceReport` when admission ran, else `None`).

## State machine, poison, and recovery

- `ACTIVE --feed--> ACTIVE`; `ACTIVE --transport error--> POISONED` (latched,
  terminal); `POISONED --feed--> PumpError("poisoned")` with no state change.
- A transport error (a frame failing envelope validation, or bytes the decoder
  rejects outright) latches `POISONED`. Frames already admitted earlier in the
  same `feed()` stay admitted; the poisoned frame is **not** consumed and blocks
  the decoder head-of-line (`expected_sequence`/high-water freeze).
- Recovery is a **new** pump via
  `PlannerTransportPump.recover(prior, *, transport_session_id)`, defined only for
  a `POISONED` prior (`not_poisoned`) and only with a **new**, valid
  32-character lowercase-hex `transport_session_id` (`session_reuse` /
  `invalid_session_id`). It builds:
  - a new `BsplineTcpDecoder` on that new transport session;
  - a new `TrajectorySession` sharing the stable identity tuple but starting at
    `planner_generation + 1` (`generation_exhausted` at the cap), so a replayed
    stale frame is rejected by **both** the new transport session and the new
    generation;
  - `command_high_water` preserved, so public command IDs keep increasing across
    the reconnect; and a fresh admission gate.
  `event_sequence` and the tick high-water continue from the prior pump — the
  authority clock does not reset on a transport reconnect.

The pump builds its admission gate from the supplied `adapter` and `anchor_ns`
(plus `binding` / `sample_period_s` pass-throughs) so `recover` can rebuild an
identical gate. Read-only audit properties: `state`, `next_event_sequence`,
`last_current_tick`, `transport_session_id`, `session_generation`,
`command_high_water`.

## Error reasons

`PumpError.reason` is one of `invalid_adapter`, `invalid_decoder`,
`invalid_anchor`, `invalid_binding`, `invalid_grid`, `invalid_sequence`,
`invalid_tick`, `invalid_chunk`, `tick_regressed`, `poisoned`, `invalid_pump`,
`not_poisoned`, `session_reuse`, `invalid_session_id`, `generation_mismatch`,
`sequence_exhausted`, `generation_exhausted`. All argument/state errors are raised
before any decoder or pump-ledger mutation.

## Non-claims

This slice does **not**:

- provide crash atomicity, exactly-once, or any transport-delivery guarantee —
  transport receipt and session activation are two separate commits, recorded in a
  returned per-frame outcome when the process reaches that point;
- open a socket or use ROS/DDS/a planner/SITL/UE/MATLAB/a native build — pure
  in-memory bytes and objects;
- read a wall clock — `current_tick` is caller-supplied, bounded to the adapter's
  integer tick range, and checked for non-regression;
- mint any identifier — `trajectory_id` comes from the payload, `event_sequence`
  is a session-scoped ordering counter, generation is read from public session
  state;
- claim continuous-curve or flight safety — scene clearance inherits the admission
  gate's `sampled_segment_checked` / `continuous_proof=False` honesty bound;
- produce force, impulse, or Terrain15D/terrain coupling — the obstacle is a
  vertical AABB, not terrain;
- drive the control/execution path — it never calls `step`/`next_output`, never
  produces a public command output, and never touches a vehicle.

## Why this cannot cross the UE/SITL/flight acceptance boundary

#102 closes only on actual map→planner→public-control→flight evidence, and #39
adds public-control passage, arrival/collision/clearance truth, and real SITL/UE
via main-agent-reserved isolated resources. This pump operates entirely on
in-memory bytes and pure objects: it never opens a socket, subscribes to a topic,
drives a session's public command output, or touches UE/SITL. It does not even
exercise the execution (`step`) path — it only admits trajectories into the
offline session. It produces no flight evidence and explicitly disclaims the real
ROS1↔ROS2 remap that #102 comment `0a7b5a7` records as still open. It is a
prerequisite seam that makes the offline transport→activation loop auditable, and
it leaves #102/#39 open.

## Verification boundary

`validation/test_planner_transport_pump.py` (boundary-focused pure Python tests, no socket/ROS/
planner/SITL/UE/MATLAB/wall clock) verifies this contract on Windows and WSL:

- `PumpReceiveTests` — single-frame activation; fragmentation completing exactly
  once; buffered frames held across a generation change; a clearance rejection recorded as
  `transport_consumed=True, session_activated=False` with the session untouched
  and no `event_sequence` spent; bridge and identity rejections recorded;
  explicit `ValueError`/`KeyError`/`TypeError` identity rejection versus
  `MemoryError`/`RuntimeError` propagation; direct `Identity` generation bounds;
  adapter rejection on a non-increasing `trajectory_id`; `event_sequence` spent
  only on activation across a mixed clear/collision/clear stream.
- `PumpPoisonRecoveryTests` — poison latches, refuses further bytes, and freezes
  the decoder high-water; `recover` builds a new transport session and a new
  generation while preserving command high-water and continuing
  `event_sequence`/tick; an old-transport-session frame is poison to the
  recovered pump; `recover` requires a poisoned prior, a new session id, and a
  valid generation boundary.
- `PumpGuardTests` — stale/future generations, tick bounds, event-sequence
  exhaustion, generation exhaustion, existing event high-water boundaries,
  invalid session ids, tiny-grid mapping, and non-bytes chunks are rejected with
  zero pre-consumption mutation; construction validates
  adapter/decoder/anchor/sequence/tick/binding; non-claims declared and no
  socket/ROS imports.

The related committed suites (`test_ego_scene_admission`,
`test_bspline_tcp_envelope`, `test_ego_trajectory_adapter`,
`test_ego_bspline_bridge`, `test_scene_profile`, `test_planner_scene_binding`) are
exercised as dependencies and continue to pass; they are not modified. These tests
do not start `JointPhysics`, a model worker, ROS/DDS, SITL, UE, or a flight, and
they assert no continuous-curve, delivery-guarantee, or physical-safety claim.
