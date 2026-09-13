# Full SIM-04 — Simulink and DLL SIL contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #124. A local model build is not the complete select/init/run/reset/export flow, and an original DLL is an optional plugin — never a core prerequisite.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:16` — pure model execution without a flight controller.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=SIM-04`, `followup_ids=[124]`; parent #26 (generated-model build import and MATLAB-free run, OPEN).
- `Simulator/wksim_core/README.md` and `tools/probe_generated_model.py`: the owned model host builds from the local vendor ZIP into a Linux `.so` and probes it without MATLAB at runtime; bounded pure-model runs exist.
- `tools/probe_simulink_sampling.py`/`.m`: sampling probes against the reference environment; they inform but do not accept the flow.
- Gap per the ticket: complete selection, initialization, run, reset and export flows are accepted separately; daily runs must not require Simulink. The original-DLL plugin ABI stays with #9 (open).

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| SIM-04-A | Owned model build | `partial`: local build evidence on record | Repeatable build with hashes per configuration |
| SIM-04-B | No-controller run | `partial`: bounded probes exist | Pure model run slices without any FC |
| SIM-04-C | Selection/initialization | `blocked`: flow unaccepted | Model selection and init with identity and typed errors |
| SIM-04-D | Reset/export | `blocked`: flow unaccepted | Reset semantics and export schema with file evidence |
| SIM-04-E | Original DLL plugin | `blocked`: ABI undecided (#9) | Optional plugin under verified ABI |
| SIM-04-F | Simulink not required | `partial`: principle recorded | Daily flows audited to never require Simulink |

## Run contract

Every SIL run must declare:

```text
model_identity, model_sha256, build_manifest, init_state, step_rate,
reset_semantics, export_schema, epoch, source_identity
```

A local build is evidence for the build atom only. Selection, initialization, run, reset and export are separate accepted items. An original DLL participates only as an optional plugin under a verified ABI; the owned core must remain fully functional without it. Any flow that requires Simulink for daily operation is `simulink_required_rejected`.

### Lifecycle

```text
select model with identity → initialize with recorded state
→ run at declared step rate → reset per declared semantics
→ export per schema → audit hashes and identities
```

`accepted` means each flow item is individually evidenced. It does not mean the original DLL behaves identically or that numerical conformance holds.

### Rejection boundary

Reject on missing model, build mismatch, invalid initialization, failed reset/export, unverified DLL ABI and Simulink-required flows. Keep `model_not_found`, `build_mismatch`, `init_invalid`, `reset_failed`, `export_failed`, `dll_abi_unverified` and `simulink_required_rejected` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket builds or runs no model.

1. **Flow itemization (owner: runtime maintainer):** freeze the reference select/init/run/reset/export item list before implementation tickets.
2. **Reset/export slice (owner: runtime maintainer):** implement the owned lifecycle items against the itemized list.
3. **DLL ABI (owner: plugin maintainer):** gated on the #9 decision; until then original DLLs stay out of scope.

No current command implements the complete flow, so none is claimed here.

## Non-goals and preserved blockers

- No model lifecycle code is implemented and no build/run is performed by this contract slice.
- #26 and #9 keep their open scope; MATLAB remains a minimal interface.
- #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for SIM-04 and for the project.
