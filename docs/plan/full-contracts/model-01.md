# Full MODEL-01 — Quadrotor parameter intake formal entry contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #135. It defines only the wiring contract from a selected mass configuration through save/import to the formal task, UE, cold rebuild and result identity. The numerical precision route stays with #59; R1 is unchanged.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:46` — quadrotor; fixed numerical comparison and parameter run slices are listed but not implemented as the formal entry.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-01`, `followup_ids=[135, 59]`; the ticket names #1, #23 (numerical conformance, CLOSED) and #24 (parameter edit/export/import and static response, CLOSED).
- `Simulator/wksim_core/model_parameters.py`: fixed Quad X component record (`motor_count=4` with its `uavType=3` basis), `make_config`/`validate`/`load_config` with canonical JSON and SHA identity, and explicit source rotation-sign records.
- `Simulator/wksim_core/arducopter-quad-x.parm` and `Simulator/wksim_runtime/parameter_protocol.py`/`parameter_storage.py`: the owned parameter surface the wiring would use.
- Gap per the ticket: the formal product parameter-run entry — task, UE, cold rebuild, result identity — is unaccepted.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-01-A | Parameter edit/import | `partial`: #24 closed the bounded slice | Mass edit, export/import, static response preserved |
| MODEL-01-B | Formal task wiring | `blocked`: unaccepted | Saved/imported config admitted into the formal task entry |
| MODEL-01-C | UE wiring | `blocked`: unaccepted | Config bound to UE with matching identity |
| MODEL-01-D | Cold rebuild identity | `blocked`: unaccepted | Cold rebuild reproduces the same config identity |
| MODEL-01-E | Result identity | `partial`: canonical hashing exists | Config hash flows into run/result identity |
| MODEL-01-F | Numerical route separation | `partial`: rule fixed here | #59 owns numerical precision; no duplication, no R1 change |

## Configuration wiring contract

Every parameter configuration entering the formal path must carry:

```text
config_id, config_sha256, model_identity, mass_kg, motor_count,
source_basis, task_entry, ue_binding, epoch, result_identity
```

A saved/imported configuration is not admitted to a formal task until the wiring is evidenced end to end: the same `config_sha256` must appear at task admission, UE binding and cold rebuild. Numerical precision is evaluated only on #59's route; this contract neither duplicates it nor relaxes R1 (`numerical_failed`).

### Lifecycle

```text
edit/validate config → save with canonical hash → import unchanged
→ admit into the formal task entry → bind UE identity
→ cold rebuild from the saved config → result identity ties back
```

`accepted` means identity is consistent across save/import, task admission, UE binding and rebuild. It does not mean the resulting flight met any numerical tolerance.

### Rejection boundary

Reject on missing config, hash mismatch, failed task admission, UE binding mismatch, rebuild identity mismatch and foreign epochs. Keep `config_not_found`, `hash_mismatch`, `task_admission_failed`, `ue_binding_mismatch`, `rebuild_identity_mismatch` and `foreign_epoch` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket changes no parameter, task or UE code.

1. **Task wiring (owner: runtime maintainer):** admit a saved/imported config into the formal task entry with recorded identity.
2. **UE binding (owner: UE maintainer):** bind the same config identity on the UE side.
3. **Cold rebuild (owner: build maintainer):** rebuild cold from the saved config and prove identity.

No current command implements the formal entry wiring, so none is claimed here.

## Non-goals and preserved blockers

- No parameter, task-entry or UE code is modified by this contract slice.
- #23 and #24 keep their closed bounded meaning; #59 owns the numerical precision route; R1 stays `numerical_failed`.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-01 and for the project.
