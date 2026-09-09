# Full OPS-01 — Model database and component library contract

Status: **defined, not implemented**. This contract closes only the expert-definition slice for GitHub #152. It does not close #24, #1, or the Full goal.

## Source and current boundary

- Frozen source row: `docs/plan/full-scope-expansion.md:69`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-01`, `followup_ids=[152]`.
- Related parent evidence: #24, `docs/2026-09-09-quad-parameters-report.md`, and `docs/2026-09-09-quad-parameters-closure-review.md`.
- The existing implementation is a named Quad X mass configuration. `Simulator/wksim_core/model_parameters.py` exposes one editable `mass` field and a fixed component description; `tools/quad_model_parameters.py` provides JSON save/import/export and isolated native build/run. It is not a database or a multi-model component library.

The contract therefore keeps the current evidence as partial evidence. It does not infer a catalog from the names of vendor files, and it does not permit deletion or mutation of a vendor installation.

## Atomic scope

| ID | Frozen capability | Current state | Required proof for a later implementation |
| --- | --- | --- | --- |
| OPS-01-A | Brand component parameters | `partial`: fixed Quad X component metadata exists; no catalog, version selection, or brand records | Catalog records for airframe, motor, rotor, frame and sensor components with source/version/hash, units and compatibility constraints |
| OPS-01-B | Custom parameters | `partial`: only Quad X mass is editable; the remaining 21 named values and mapping are fixed | Explicit editable-field schema, range/unit validation, canonical identity update, and a negative test for attempts to edit read-only components |
| OPS-01-C | Confirm and calculate | `partial`: canonical config validation and model-identity calculation exist; hover/performance/derived calculation is not present | A versioned calculation contract with formula/source identity, units, inputs, outputs, invalid-input behavior and golden cases |
| OPS-01-D | Add and remove a model | `blocked`: no catalog lifecycle API | Add creates a user-owned copy; remove requires an explicit workspace record and never touches a read-only source or another workspace |
| OPS-01-E | Database import/export | `partial`: `save_config`, `load_config`, and the CLI `export`/`import` aliases preserve one validated Quad X record | Versioned catalog manifest, dependency closure, provenance, atomic import, collision policy and a round-trip audit across more than one model |
| OPS-01-F | Backup and restore | `blocked`: no database backup/restore entry point | Snapshot/restore of catalog records and metadata, integrity verification, no-clobber behavior, rollback on failure and restore into a fresh workspace |

## Record and lifecycle contract

The minimum future record is a canonical JSON object with these required groups:

```text
schema                 # wksim.model-catalog.v1 (or a later explicit version)
model_id               # stable within the user workspace; never inferred from a filename
display_name
components             # typed records with id, version, source and SHA-256
parameters             # value + declared unit + editability + source field
derived                # value + formula/source identity + input identities
provenance              # repository, source artifact, model version and build recipe
```

The supported lifecycle is:

```text
select source → copy to user workspace → edit → confirm/calculate
→ add/update catalog record → export/import or backup/restore
→ select explicit record → build/run → inspect result → remove explicit copy
```

Each transition must preserve `model_id`, component identities, units, source hashes and the calculation input identities. A model is not considered accepted merely because its JSON parses or a UI form displays it.

### Storage and safety rules

1. The vendor/source catalog is read-only. Add, edit, delete, import and restore operate only under an explicitly selected user workspace.
2. File paths are resolved under that workspace; traversal, symlink escape, unknown schema, duplicate JSON keys, non-finite numbers, unknown fields and source/hash mismatch are rejected before any model is loaded.
3. Existing records are never silently overwritten. Import and restore must either use a new destination or return a collision error; failed operations leave the prior workspace unchanged.
4. A successful confirmation records the normalized values and the exact source/calculation identities. A later build must reject a record whose identity no longer matches its inputs.
5. Delete is a user-visible operation against one named workspace record. It is not a cleanup shortcut and cannot remove a factory/source record.

### Public result and error semantics

The operation result must distinguish `accepted`, `rejected`, `not_found`, `collision`, `source_mismatch`, `integrity_failed`, `calculation_failed` and `storage_failed`. `accepted` means the record was validated and saved; it does not mean a model was built, loaded, or flown. A failed import/restore must identify the record and validation stage without exposing private vendor material.

## Evidence-backed follow-up slices

These are proposed successors, not executable commands in the current checkout:

1. **Catalog storage (owner: model/parameter maintainer):** add `Simulator/wksim_core/model_catalog.py` and one standard-library CLI under `tools/`, with schema, workspace confinement, no-clobber writes and add/remove negative cases. It must reuse the canonical JSON and hashing behavior already in `model_parameters.py` rather than introduce a second identity algorithm.
2. **Component and calculation contract (owner: model/parameter maintainer):** extend the existing parameter module only after the formula/source for each derived value is fixed. Performance-calculation behavior belongs with OPS-02/#153; this slice must not invent formulas or budgets.
3. **Import/export and backup/restore (owner: catalog maintainer):** add round-trip, collision, tamper and fresh-workspace tests against the catalog CLI. Do not accept arbitrary paths or execute an imported manifest.
4. **UI integration (owner: operator-console maintainer):** consume the catalog contract through the existing workspace flow; this is also part of OPS-04/#155 and must not duplicate catalog storage.

The current repository has no executable command satisfying these slices, so no run is claimed here. Each successor must first reserve its exact files and then provide a new raw evidence directory.

## Non-goals and preserved blockers

- This contract does not implement a model database, performance calculator, additional model types, DLL import, MATLAB behavior or GUI behavior.
- #24 remains valid only for the finite Quad X mass workflow. #59/G6 and the numerical `R1=numerical_failed` result are unchanged.
- Hardware, vendor redistribution and plugin ABI decisions remain under #56/#58/#9. No source or vendor artifact is copied or modified by this slice.
- `full_complete` remains `false` for OPS-01 and for the project.
