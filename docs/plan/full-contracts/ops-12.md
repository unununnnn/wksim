# Full OPS-12 — Self-contained resource delivery contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #163. It does not convert local compilation success into redistribution rights or a clean-machine bootstrap.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:80`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-12`, `followup_ids=[163]`; parents #26 (generated-model build import and MATLAB-free run, OPEN) and #1 (Wayfinder, OPEN).
- `Simulator/wksim_core/README.md`: the owned model host builds and runs without CopterSim.exe, closed model DLLs, Gazebo or MATLAB; the first build still requires the local `MulticopterModel.zip`, vendor source is unpacked only into a WSL temp directory, redistribution is unconfirmed, and the repository cannot yet claim a complete bootstrap on a machine without local resources.
- `docs/project-isolation.md`: project-owned dependency locations with pinned identities — PX4 commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` with firmware SHA256, legacy AP commit `1511f27194f1dcc3728270883047bdf022b3fd53` with firmware SHA256; UE environment/material files archived byte-verified under project-private `work/dependencies/ue55/`, kept local and never committed. Git/submodule boundaries were cleaned; old submodule definitions survive only as `docs/Prometheus.gitmodules.reference`.
- `docs/prometheus-p450-asset-provenance.md` with `tools/prepare_p450_asset.py`: the P450 asset provenance CLI reads local Git objects at the fixed Prometheus commit `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`, with redirect rejection, size/time budgets and Git blob SHA1 verification for the three permitted STL downloads.
- Missing: a license manifest covering the vendor ZIP and UE staging content, a clean-machine bootstrap audit, and an explicit publishable vs local-only distribution boundary.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-12-A | Independence from proprietary runtime | `partial`: owned core runs without the original program/DLLs; first build needs the local vendor ZIP | Build and run on record without CopterSim.exe/closed DLLs, with prerequisites enumerated |
| OPS-12-B | Model/asset availability | `partial`: P450 provenance CLI proves one pinned-source path | Every model/asset obtainable by pinned source/hash or explicitly marked local-only |
| OPS-12-C | Build instructions | `partial`: README and isolation doc pin the FC sources and versions | Clean-machine bootstrap naming each local-only requirement |
| OPS-12-D | Source licenses | `blocked`: vendor ZIP redistribution unconfirmed; UE staging local-only | License manifest with redistribution status per resource |
| OPS-12-E | Pinned dependency identity | `partial`: PX4/AP commits and firmware SHA256 recorded | All runtime resources pinned or explicitly unpinned-listed |
| OPS-12-F | Distribution boundary | `partial`: git/submodule boundary cleaned | Publishable vs local-only package definition |

## Resource manifest contract

Every delivered or required resource must have a manifest record containing:

```text
resource_id, kind (source | firmware | model | asset | environment),
source, source_commit, source_sha256, license, redistribution_status
(publishable | local_only | undetermined), owner, required,
bootstrap_path, local_only
```

Local compilation success is not redistribution rights; a mounted local asset is not a deliverable asset; and an archived byte-verified copy does not change its license. `undetermined` redistribution defaults to local-only handling.

### Lifecycle

```text
enumerate resources → pin source/commit/hash → record license and
redistribution status → classify publishable vs local-only
→ verify clean-machine bootstrap with the manifest → package only
publishable records → audit on change
```

`accepted` means the manifest record is complete and hash-consistent. It does not mean the license permits redistribution — that is determined by `redistribution_status`, never inferred from availability.

### Rejection boundary

Reject on missing resource, unknown license, denied or undetermined redistribution presented as publishable, hash mismatch, incomplete bootstrap and unpinned dependencies. Keep `resource_missing`, `license_unknown`, `redistribution_denied`, `hash_mismatch`, `bootstrap_incomplete` and `unpinned_dependency` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket downloads, packages or publishes nothing.

1. **License inventory (owner: release maintainer):** determine and record the vendor ZIP, UE staging and third-party asset licenses; until then all three stay local-only.
2. **Clean bootstrap audit (owner: build maintainer):** one recorded clean-machine attempt enumerating every local-only requirement; the current README already states the bootstrap claim is not yet made.
3. **Asset availability (owner: asset maintainer):** extend the P450 provenance pattern (pinned commit, verified fetch, no Git object writes) to the remaining models/assets.
4. **Distribution boundary (owner: release maintainer):** define the publishable package strictly from the completed license inventory.

No current command implements the license manifest, clean bootstrap or distribution package, so none is claimed here.

## Non-goals and preserved blockers

- No resource is downloaded, repackaged or published by this contract slice; no license is reinterpreted.
- #26 and #1 keep their original scope and state; the vendor ZIP and UE staging stay local-only.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for OPS-12 and for the project.
