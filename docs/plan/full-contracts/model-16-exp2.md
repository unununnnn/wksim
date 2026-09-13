# Full MODEL-16 (Exp2_MaxModelTemp) — Generated-model template contract

Status: **defined, blocked on material**. This bounded definition slice is GitHub #151, the Exp2_MaxModelTemp half of ledger row MODEL-16. Exp1 material or build evidence never covers Exp2; absent material is an explicit blocker, not a reason to guess the template.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:61` — Exp1_MinModelTemp and Exp2_MaxModelTemp; generated-model slices verify only selected samples.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-16`, `followup_ids=[150, 151]`; parent #26 (generated-model build import, OPEN).
- `tools/probe_model_reference_readiness.py` pins only Exp1_MinModelTemp files by SHA256. No Exp2_MaxModelTemp material — editable or otherwise — is pinned anywhere in this checkout.
- Missing: the Exp2 material itself, then its I/O schema, generation flow, build/import flow and run flow.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-16-E2-A | Template I/O | `blocked`: no material | I/O schema pinned from the .slx and init file |
| MODEL-16-E2-B | Generation flow | `blocked`: no material | Fixed tool versions and hashes per generation |
| MODEL-16-E2-C | Build and import | `blocked`: no material | Import into the owned host with manifest identity |
| MODEL-16-E2-D | Run flow | `blocked`: no material | Init/step/stop semantics and result identity |
| MODEL-16-E2-E | Editable material | `blocked`: absent | Exp2 material obtained and pinned by SHA256 |

## Template contract

An Exp2_MaxModelTemp delivery must declare:

```text
template_id, template_sha256, io_schema, generation_toolchain,
build_manifest, import_identity, run_semantics,
editable_material_status, source_identity
```

Until the editable material is pinned, every flow item stays blocked; the contract is recorded so the blocker is explicit and reviewable, not silently skipped.

### Lifecycle

```text
obtain and pin Exp2 material → pin I/O schema → generate with fixed
toolchain → build and import with manifest identity → run with recorded
semantics
```

`accepted` means each flow item is individually evidenced. It does not mean numerical agreement with the reference environment.

### Rejection boundary

Reject on missing material, unpinned I/O, generation mismatch, build failure, import identity mismatch and run failure. Keep `template_missing`, `material_local_only`, `io_unpinned`, `generation_mismatch`, `build_failed`, `import_identity_mismatch` and `run_failed` distinct.

## Evidence-backed follow-up slices

1. **Material pin (owner: release maintainer):** obtain and pin the Exp2 editable material; this is the expert prerequisite for all other items.
2. **Build/run audit (owner: build maintainer):** one build-import-run chain after the material pin and I/O freeze.

No current command implements the Exp2 flow, so none is claimed here.

## Non-goals and preserved blockers

- No generation, build, import or run is performed by this contract slice; no material is fabricated.
- #26 keeps its open scope; Exp1_MinModelTemp is handled under #150 on the same row.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-16 (Exp2) and for the project.
