# Full OPS-03 — XML and model metadata contract

Status: **defined, not implemented**. This is the bounded definition slice for GitHub #154. Reading an XML file or selecting a DLL is not treated as proof that the model configuration is usable.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:71`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-03`, `followup_ids=[154]`.
- Related parent: #26 remains open and concerns generated-model build/import, not a complete metadata parser.
- The read-only ABI evidence in `docs/plan/9-abi-environment-evidence.md` records `ModelInfo`, `HoverInfo` and `FrameInfo` observations for the local Hexa/F450 XML files and records `ClassID=-1` as a model-side selection clue. Those files are outside this checkout and are not copied into the repository.
- The owned Quad X path uses a validated JSON record in `Simulator/wksim_core/model_parameters.py`; it does not parse the XML metadata contract. `docs/plan/26-generation-contract.md` also keeps the generated ZIP/source identity boundary explicit.

## Atomic scope

| ID | Metadata atom | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-03-A | `ModelInfo` | `partial`: read-only vendor XML facts exist; no owned parser/normalized schema | Field names, types, units, defaults, source/hash and model identity are parsed and checked against the selected model |
| OPS-03-B | `HoverInfo` | `partial`: local evidence reports values such as steady speed and motor time; semantics are not accepted by wksim | Each field's units, reference condition, valid range and relationship to the model/configuration are frozen |
| OPS-03-C | `FrameInfo` | `partial`: Hexa/F450 rotor/arm counts were observed; no owned frame/mixer binding | Rotor/arm order, positions, rotation signs, actuator mapping and supported stack are tied to an explicit frame identity |
| OPS-03-D | `ClassID` | `blocked`: `-1` is only a source-side selection clue and does not bind a UE asset | Class ID namespace, asset path/hash, fallback behavior and mismatch rejection are proved with a saved asset manifest |
| OPS-03-E | Defaults, units and errors | `blocked`: no versioned parser contract defines missing/invalid/unknown metadata behavior | Required fields, unit conversions, defaults, finite/range checks, duplicate/unknown fields and error codes are fixed and tested |

## Normalized metadata contract

A future record must be canonical and source-bound. Its minimum fields are:

```text
schema, model_id, source.path, source.sha256, source.version,
model_info, hover_info, frame_info, class_id, defaults, units,
compatibility, parser_identity
```

Every numeric field carries its declared unit or is explicitly marked as a source-native code. The parser must preserve the original source identity and normalized value; it must not silently turn an absent value into zero or infer a ClassID, rotor order or asset from a neighboring filename.

The lifecycle is:

```text
select metadata source → verify path/hash/format → parse raw fields
→ normalize units/defaults → validate model/frame/class compatibility
→ bind to an explicit vehicle/asset record → build/run or reject
```

`accepted` means the metadata record is parsed, normalized and stored. It does not mean the model loaded, the visual asset rendered, or the physics is correct.

### Rejection boundary

Reject before model initialization on malformed XML, unsupported schema/version, duplicate or unknown required fields, missing units, non-finite/out-of-range values, inconsistent rotor counts, invalid ClassID/asset binding, source/hash mismatch, or a default outside the declared range. Preserve `parse_error`, `unsupported_schema`, `missing_field`, `invalid_unit`, `invalid_value`, `frame_mismatch`, `class_unbound`, `source_mismatch` and `asset_mismatch` as distinct reasons.

The legacy ABI wrapper's ctypes declarations are not an XML schema. Its `ClassID`, `ModelInfo`, `HoverInfo` and `FrameInfo` observations are evidence inputs only; the unresolved ABI return values, field ownership and vendor distribution status remain fail-closed under #9/#58.

## Evidence-backed follow-up slices

These are proposed successors; this ticket adds no executable parser or model runner.

1. **Metadata reader (owner: model-import maintainer):** reserve a new standard-library XML reader/normalizer and one targeted test file. The reader must accept an explicit source path, retain raw/source hashes, and never load a DLL as a substitute for metadata validation.
2. **Frame/class binding (owner: asset/runtime maintainer):** bind normalized `FrameInfo` and `ClassID` to an explicit asset manifest only after #56/#58 decisions and asset ownership are available. A `ClassID=-1` clue alone remains rejected for a visual run.
3. **Generated-model integration (owner: model-import maintainer):** connect the metadata manifest to the existing generation/import path only after #26's source-generation contract is resolved; reject XML/ZIP/DLL identity drift before build/load.
4. **Negative and round-trip audit (owner: validation maintainer):** exercise missing fields, unit mismatch, count mismatch, ClassID mismatch, source tamper and valid Hexa/F450 or owned-model fixtures. Vendor files stay read-only and local.

No current command implements these slices, so no build, DLL load, UE launch or flight is claimed by this contract.

## Non-goals and preserved blockers

- No XML parser, model database, DLL host, UE asset import or metadata-to-physics binding is implemented here.
- Vendor XML and SDK samples are referenced by hash and summarized from local read-only evidence; no vendor material is redistributed.
- #26, #9, #56 and #58 retain their original states/decisions. `R1=numerical_failed`, G6 and Full remain unchanged.
- `full_complete` remains `false` for OPS-03 and for the project.
