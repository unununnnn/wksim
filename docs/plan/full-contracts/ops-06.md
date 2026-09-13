# Full OPS-06 — Vehicle and scene asset contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #157. It does not promote a visual fixture or a model filename into a complete vehicle/scene catalog.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:74`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-06`, `followup_ids=[157]`.
- Related evidence: #48's P450 product display and the Hex native/static evidence under #25. The ledger records these as partial evidence only.
- `Simulator/ue55/p450-visual-manifest.json` binds a Prometheus P450 visual asset to source/engine/import hashes, frame/scale, rotor order and an explicit limitation: the visual geometry runs on existing Quad X test dynamics and does not claim P450 inertia/aerodynamics or sensor functionality.
- `Simulator/ue55/README.md` describes the UE5.5 state bridge and explicitly calls the current four-rotor geometry an integration model, not a completed Prometheus vehicle asset. `Simulator/wksim_runtime/hex-flight-v1.json` binds the Hex native model/plan identity, but it is not a UE asset catalog or ClassID binding.
- The owned Quad X parameter path contains a fixed four-motor mapping. No owned catalog currently selects arbitrary vehicle/scene assets or binds model ClassID to an imported UE asset.

## Atomic scope

| ID | Asset capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-06-A | Correct vehicle body/geometry | `partial`: P450 content is imported and hash-bound; its physics scope is explicitly Quad X test dynamics | Per-vehicle geometry/source/license/hash, scale, frame and model-to-visual identity with a real render/readback |
| OPS-06-B | Rotor/actuator arrangement | `partial`: Quad X and Hex mappings are present in separate evidence paths; no complete asset catalog | Rotor count/order, origin, axis, rotation sign, actuator mapping and dimensions agree across model, manifest and UE |
| OPS-06-C | Scene selection | `blocked`: the current UE project has a bounded staging scene, not a versioned selectable scene catalog | Scene IDs, source/asset hashes, coordinate/origin/scale, selection and unsupported-scene errors |
| OPS-06-D | Asset import | `partial`: the P450 import manifest and build inputs are retained; no general import workflow exists | Import/validate/save/reload workflow with source ownership, license and deterministic manifest |
| OPS-06-E | Model `ClassID` mapping | `blocked`: source-side `ClassID=-1` is not an UE asset binding | Explicit ClassID namespace-to-asset record, mismatch rejection and a same-run actor/model identity readback |
| OPS-06-F | Vehicle/scene/physics identity | `partial`: manifests state their scope and hashes; no common cross-domain identity catalog | One manifest ties model, physics, vehicle geometry, scene and sensor attachments without silently mixing scopes |

## Asset manifest contract

Each selectable record must be a versioned, immutable-by-reference manifest containing:

```text
asset_id, vehicle_id, scene_id, source_repository/path/license,
source_sha256, import_sha256, engine_version, coordinate_frame,
unit_scale, origin/attachment offset, model_identity, class_id,
rotor/actuator mapping, sensor attachments, physics_scope,
supported_stacks, provenance and validation status
```

The manifest is the boundary between an editable user workspace and read-only source assets. A visual asset may mirror authoritative physics, but it must declare that it does not provide physics. A geometry-only sensor mount must not be reported as a simulated sensor.

### Selection and import lifecycle

```text
list catalog → select explicit vehicle/scene → validate source/license/hash
→ import or stage into owned workspace → bind model/frame/ClassID
→ preflight identity/scale/origin → run → read back actor/model identity
→ stop or restore the prior workspace
```

`accepted` means the manifest and import are valid. It does not mean a vehicle flew, a scene participated in collision, or a sensor produced valid data. An import must not overwrite a source catalog or an existing record without an explicit new destination/revision.

### Rejection boundary

Reject before UE/model launch on missing source/license, hash mismatch, unsupported engine, non-finite/invalid scale, frame/unit mismatch, rotor count/order mismatch, unknown ClassID, asset/model identity mismatch, duplicate ID, unsafe path or a scene that is not explicitly supported. Keep `asset_not_found`, `source_mismatch`, `license_unknown`, `engine_mismatch`, `frame_mismatch`, `mapping_mismatch`, `class_unbound`, `scene_unsupported` and `physics_scope_mismatch` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket creates no asset and modifies no Unreal package.

1. **Vehicle manifest/catalog (owner: asset maintainer):** define a small catalog schema and workspace-confined selector. Start with the already hash-bound P450 visual record and the owned Quad/Hex model identities, preserving their separate physics scopes.
2. **Rotor and frame binding (owner: model/runtime maintainer):** reuse the existing Quad/Hex actuator mappings, add one identity-bound cross-check and reject count/order/sign drift before launch.
3. **Scene catalog/import (owner: UE/asset maintainer):** add only explicitly owned/allowed scene records with engine/version/source/license hashes. Do not treat current UrbanBlock or staging content as a general catalog.
4. **ClassID and same-run audit (owner: UE/runtime maintainer):** bind an explicit ClassID to an asset manifest and read back actor/model identity from a real run; `ClassID=-1` alone is a rejection, not a fallback.
5. **Multi-stack asset acceptance (owner: validation maintainer):** run one new vehicle/scene per ticket and independently compare model, UE actor, rotor and sensor attachment identities. Existing P450/Hex evidence cannot be replayed as new live proof.

No current command implements the full manifest/selector/import contract, so no new UE process or asset write is claimed here.

## Non-goals and preserved blockers

- No Unreal asset is created, renamed, imported or modified by this contract slice.
- P450 visual assets remain local and license-bound; their manifest limitation is preserved. Hex native output is not a UE asset proof.
- #25, #48, #9, #56 and #58 retain their original scope/decision boundaries. `R1=numerical_failed`, G6 and Full remain unchanged.
- `full_complete` remains `false` for OPS-06 and for the project.
