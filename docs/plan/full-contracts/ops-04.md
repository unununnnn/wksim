# Full OPS-04 — CLI / NoUI / GUI parity contract

Status: **defined, not implemented**. This is the bounded contract-definition slice for GitHub #155. The existing operator-console evidence covers a normal UI path; it does not prove parity for every frozen startup-parameter combination.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:72`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-04`, `followup_ids=[155]`.
- Related parent: #18 is closed for its narrower real-browser/UI workflow. Its report explicitly keeps Full parameter combinations and error flows open.
- CLI surface: `tools/run-wksim.sh` accepts a runtime configuration and delegates to `Simulator.wksim_runtime.runtime` inside the existing WSL isolation boundary.
- NoUI/preflight surface: `Simulator/wksim_console/preflight_entry.py` loads the same strict config and calls the formal preflight entry.
- GUI surface: `Simulator/wksim_console/server.py` and `workspace.py` use `validate_config`/`checked_config`, then expose preflight/start/view/result endpoints. The UI does not own a second flight-control implementation.
- Current evidence demonstrates selected normal configurations, saved/reloaded configuration, error display and a local UI workflow. The frozen source path and SHA for the claimed 16-parameter handbook are not present in this checkout, so the parameter list cannot be safely reconstructed from names or from the current JSON fields.

## Atomic scope

| ID | Frozen capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-04-A | One canonical configuration and validation result | `partial`: CLI, NoUI and GUI converge on `validate_config`, while the console adds session/mission constraints | Same normalized config, identity and error class returned by all three surfaces |
| OPS-04-B | Multi-valued initial position/attitude/vehicle state | `blocked`: the 16 handbook arguments and their source are not available here | Frozen argument IDs, types, units, defaults, ranges, serialization and negative cases |
| OPS-04-C | GPS/origin selection | `partial`: current runtime configs carry stack/model paths and the model has a fixed source origin; full user-selectable GPS/origin parity is not proven | Explicit origin frame, GPS enable/disable semantics, datum/altitude units and equivalent CLI/NoUI/GUI behavior |
| OPS-04-D | Serial and baud-rate options | `blocked`: the accepted native runtime selects DDS; no frozen serial/baud contract is owned by this path | Source-backed device, baud, framing, ownership, unavailable-device and safe-failure behavior |
| OPS-04-E | Communication addresses and ports | `partial`: absolute WSL paths and bounded loopback forwarding are validated; the full handbook address matrix is not covered | Per-address namespace/instance rules, port collision checks and identical rejection/results across surfaces |
| OPS-04-F | Automatic start/connection | `partial`: GUI requires a successful exact preflight before start and the CLI runs a formal entry; all handbook auto-start combinations are not covered | Explicit ordering, readiness state, no-start-on-rejection and clean stop behavior for every supported mode |
| OPS-04-G | Real-time and logging options | `partial`: runtime and console retain logs/results and use an authority/runtime boundary; the full option matrix and resource semantics are not frozen | Option meanings, output/recording level, capacity and failure semantics, with no wall-clock substitution for simulation time |
| OPS-04-H | CLI / NoUI / GUI behavioral parity | `partial`: normal UI operations reach the formal WSL path; no complete 16-argument cross-surface matrix exists | Same accepted/rejected behavior, normalized identity, result path and error reason for every supported input |

## Canonical input/output contract

The three surfaces must submit one versioned configuration object. A surface-specific form or command line may be an adapter, but it cannot create a second semantic implementation. The normalized result must retain:

```text
schema_version, run_id, vehicle_id, stack, model_profile,
communication, workspaces/roots, initial state, GPS/origin,
serial/address options, auto-start, realtime/logging options,
capabilities, source/config identity and rejection reason
```

Each field requires a source-backed type, unit, default and allowed range. Values are validated before resource creation or FC/model launch. A successful `accepted` result means only that the configuration was normalized and admitted to the next formal stage; preflight pass, connection, task completion and flight success remain separate states.

### Surface rules

1. CLI and NoUI must call the same formal preflight/runtime logic used by the GUI. GUI code may collect and display state but must not publish flight commands itself.
2. Every surface uses the same canonical serialization and identity. Saved configuration reload must reproduce the same normalized bytes or return an explicit revision conflict.
3. Unsupported or not-yet-sourced handbook arguments are rejected as unsupported; they must not be silently ignored or mapped to a nearby field.
4. A rejected configuration starts no FC, model, ROS, UE or external service process. A failed preflight starts no flight. Stop/retry owns only the process group created by that run.
5. Logs and result paths are explicit outputs. A UI screenshot is presentation evidence only; the machine-readable result and source identities are authoritative.

### Error taxonomy

Use stable reasons such as `unknown_argument`, `missing_argument`, `invalid_type`, `invalid_unit`, `out_of_range`, `unsupported_mode`, `path_escape`, `address_collision`, `device_unavailable`, `preflight_failed`, `revision_conflict`, `runtime_failed` and `result_missing`. Do not collapse a GUI validation error, a connection failure and a task failure into one generic “start failed” message.

## Frozen-parameter gap

The “16 startup parameters” phrase is a scope requirement, not a usable source specification. Before implementation, obtain the exact handbook/source path and SHA and list the 16 stable IDs. Until then, the contract deliberately leaves the following facts unknown: exact names, multi-value initial-state encoding, GPS/serial/address defaults, auto-start order, real-time/logging meanings, and error behavior. Current `config.py` fields are not promoted to the handbook contract merely because they have similar names.

## Evidence-backed follow-up slices

These are proposed successors; this ticket adds no CLI option or runtime behavior.

1. **Freeze source parameter map (owner: product/compatibility maintainer):** record the exact handbook/source and SHA, map all 16 IDs to the canonical config schema and mark unsupported rows explicitly. If the source cannot be obtained, keep those rows blocked rather than guessing.
2. **Shared adapter (owner: runtime maintainer):** reserve the smallest changes around `config.py`, `preflight_entry.py` and the CLI/GUI adapters so all surfaces call one validator and formal entry. Add cross-surface accepted/rejected cases without launching FC/model processes.
3. **NoUI matrix (owner: validation maintainer):** exercise each supported value family, path/port collision, missing device and logging option, retaining exact normalized config/error identity.
4. **GUI matrix (owner: operator-console maintainer):** drive the same cases through the local browser after the source map is frozen; associate every UI result with the machine result and preserve accessibility/error focus checks.

No current command proves the frozen 16-parameter matrix. Existing #18 normal-path results remain valid but are not reused as Full parity evidence.

## Non-goals and preserved blockers

- No new startup arguments, serial support, GUI controls, or runtime semantics are implemented here.
- The current local-only security boundary, WSL isolation, session identity and formal task entry remain unchanged.
- #18 remains closed only for its original scope; #56 hardware/resource decisions and the missing handbook source remain blockers for the expanded line.
- `full_complete` remains `false` for OPS-04 and for the project.
