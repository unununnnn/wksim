# Full MODEL-15 — MultSILSwarm scene contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #149. A SIL swarm is a joint scene of model instances without FCs; dual-FC evidence covers two flight controllers, not a swarm.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:60` — MultSILSwarm; uncovered.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-15`, `followup_ids=[149]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_runtime/scene_clock.py` proves the owned joint authority-time seam for the dual-FC scene; no SIL swarm scene, member identity schema or shared-time mapping for model-only swarms exists.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-15-A | Swarm scene definition | `blocked`: none | Member count, spawn semantics and topology declared |
| MODEL-15-B | Member identity | `blocked`: none | Per-member identity resolvable in every record |
| MODEL-15-C | Shared time mapping | `blocked`: none | All members on one authoritative timeline |
| MODEL-15-D | Joint scene distinction | `partial`: rule fixed here | Dual-FC evidence never recorded as swarm coverage |

## Scene contract

A MultSILSwarm scene must declare:

```text
scene_id, member_count, member_identities, spawn_semantics,
topology, shared_time_mapping, epoch, source_identity
```

Every record resolves its member identity; ambiguous identity is `identity_ambiguous`, never merged. All members share one authoritative timeline via the declared mapping; per-member local clocks are not authority.

### Lifecycle

```text
declare scene, members and topology → spawn per declared semantics
→ map all members onto the shared timeline → run
→ stop; records keep per-member identity
```

`accepted` means the scene ran with resolvable member identities on the shared timeline. It does not mean swarm algorithms or FC-controlled swarms work.

### Rejection boundary

Reject on missing members, ambiguous identity, unmapped time, invalid topology and dual-FC substitution. Keep `member_missing`, `identity_ambiguous`, `time_unmapped`, `topology_invalid` and `dual_fc_substitution_rejected` distinct.

## Evidence-backed follow-up slices

1. **Swarm definition (owner: runtime maintainer):** freeze the scene and member identity schema.
2. **Swarm slice (owner: runtime maintainer):** run one bounded SIL swarm on the shared timeline with raw records.

No current command implements MultSILSwarm, so none is claimed here.

## Non-goals and preserved blockers

- No swarm scene is implemented by this contract slice.
- The dual-FC joint scene keeps its separate identity; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-15 and for the project.
