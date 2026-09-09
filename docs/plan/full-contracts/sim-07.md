# Full SIM-07 — EXT_SIM_NET external simulation contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #125. No external interop claim exists until one reference system with authority, clock and failure semantics is pinned and observed.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:19` — connecting an external simulation system.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=SIM-07`, `followup_ids=[125]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_runtime/scene_clock.py`: the owned joint time/fault seam (committed ticks, barriers, suspend, recoverable) is the wksim-side base for any future external clock mapping. It is internal evidence only.
- Missing: the reference external system identity, the physics authority boundary, the clock relationship and the failure semantics.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| SIM-07-A | Reference system identity | `blocked`: unpinned | One named external system with version and source |
| SIM-07-B | Physics authority | `blocked`: undeclared | Explicit authority boundary; exactly one authority per quantity |
| SIM-07-C | Clock relationship | `blocked`: unmapped | Pinned clock mapping with deviation handling |
| SIM-07-D | Failure semantics | `blocked`: undefined | Disconnect/timeout/freeze results on both sides |
| SIM-07-E | Owned joint time seam | `partial`: SceneClock exists internally | wksim-side base preserved, never relabelled as interop |

## Link contract

Every EXT_SIM_NET link must declare:

```text
link_id, external_system_identity, external_version, physics_authority,
clock_mapping, deviation_budget_ns, failure_semantics, epoch, source_identity
```

Exactly one side is authoritative per physical quantity; dual authority is `authority_conflict`. External clocks map onto the authoritative timeline through the pinned mapping only — never by wall-clock alignment.

### Lifecycle

```text
pin reference system → declare authority boundary → pin clock mapping
→ define failure semantics → run one bounded end-to-end slice
→ disconnect/timeout/freeze produce declared results
```

`accepted` means the link honored its declared authority, clock and failure semantics. It does not mean any other external system is compatible.

### Rejection boundary

Reject on unpinned references, authority conflicts, unmapped clocks, exceeded deviation, lost links and foreign epochs. Keep `reference_unpinned`, `authority_conflict`, `clock_unmapped`, `deviation_exceeded`, `link_lost` and `foreign_epoch` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket connects nothing.

1. **Reference pin (owner: integration maintainer):** select and pin one external system with version and access.
2. **Authority and clock (owner: physics/runtime maintainers):** declare the authority boundary and clock mapping with deviation handling.
3. **End-to-end slice (owner: runtime maintainer):** one bounded run against the pinned system with declared failure results.

No current command implements or verifies EXT_SIM_NET, so none is claimed here.

## Non-goals and preserved blockers

- No external link is implemented or opened by this contract slice.
- The SceneClock seam remains internal evidence; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for SIM-07 and for the project.
