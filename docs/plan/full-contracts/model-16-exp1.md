# Full MODEL-16 (Exp1_MinModelTemp) — Generated-model template contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #150, the Exp1_MinModelTemp half of ledger row MODEL-16. A generated-model slice verifies only the selected sample; each template carries its own I/O and flow contract.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:61` — Exp1_MinModelTemp and Exp2_MaxModelTemp; generated-model slices verify only selected samples.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=MODEL-16`, `followup_ids=[150, 151]`; parent #26 (generated-model build import, OPEN).
- `tools/probe_model_reference_readiness.py` pins `Exp1_MinModelTemp.slx` (`c232e2e9…`) and `Exp1_MinModelTemp_init.m` (`9ca09a95…`) by SHA256 under a local `E:/rflysimtools/...` path, with `validation/generated-model-*` build logs. The material is local-only; redistribution is unresolved.
- Missing: the template's I/O schema, generation flow, build/import flow and run flow as accepted items.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| MODEL-16-E1-A | Template I/O | `blocked`: unpinned | I/O schema pinned from the .slx and init file |
| MODEL-16-E1-B | Generation flow | `blocked`: undefined | Fixed tool versions and hashes per generation |
| MODEL-16-E1-C | Build and import | `blocked`: slice evidence only | Import into the owned host with manifest identity |
| MODEL-16-E1-D | Run flow | `blocked`: undefined | Init/step/stop semantics and result identity |
| MODEL-16-E1-E | Editable material | `partial`: pinned local-only | Material status explicit; local-only never claimed distributable |

## Template contract

An Exp1_MinModelTemp delivery must declare:

```text
template_id, template_sha256, io_schema, generation_toolchain,
build_manifest, import_identity, run_semantics,
editable_material_status, source_identity
```

Missing editable material is an explicit `template_missing`/`material_local_only` blocker — never substituted by a binary or a screenshot. The owned host (`Simulator/wksim_core`) is the import target; MATLAB remains a minimal interface.

### Lifecycle

```text
pin template material → pin I/O schema → generate with fixed toolchain
→ build and import with manifest identity → run with recorded semantics
```

`accepted` means each flow item is individually evidenced. It does not mean numerical agreement with the reference environment.

### Rejection boundary

Reject on missing material, unpinned I/O, generation mismatch, build failure, import identity mismatch and run failure. Keep `template_missing`, `material_local_only`, `io_unpinned`, `generation_mismatch`, `build_failed`, `import_identity_mismatch` and `run_failed` distinct.

## Evidence-backed follow-up slices

1. **I/O freeze (owner: model maintainer):** read the pinned Exp1 material and pin the I/O schema.
2. **Build/run audit (owner: build maintainer):** one build-import-run chain with manifest and result identity.

No current command implements the Exp1 flow, so none is claimed here.

## Non-goals and preserved blockers

- No generation, build, import or run is performed by this contract slice.
- #26 keeps its open scope; Exp2_MaxModelTemp is handled under #151 on the same row.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for MODEL-16 (Exp1) and for the project.
