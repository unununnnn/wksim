# Full SIM-11 — PX4_SIH_SITL mode contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #127. In SIH the flight-controller-internal model is the only physics authority; external-physics SITL evidence is a different mode.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:23` — SIH running inside the software flight controller.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=SIM-11`, `followup_ids=[127]`; parent #1 (Wayfinder, OPEN).
- `docs/project-isolation.md` pins the PX4 build (`d6f12ad1…`); `Simulator/wksim_core/px4_mavlink.py` and `Simulator/wksim_runtime/scene_clock.py` are the owned external-physics SITL path and joint time seam — neither exercises an FC-internal SIH model.
- Missing: verification that the pinned PX4 build provides the SIH mode and its interface, the unique-physics-authority rule under SIH, and the display/mission time remapping.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| SIM-11-A | SIH mode availability | `blocked`: unchecked in the pinned build | Source-level confirmation of the mode and its interface |
| SIM-11-B | Unique physics authority | `partial`: rule fixed here; joint seam proves single-authority discipline internally | Under SIH the FC-internal model is authoritative; no second physics core runs (`dual_physics_rejected`) |
| SIM-11-C | Time remapping | `blocked`: undefined | Display/mission time remapped onto the FC-internal timeline |
| SIM-11-D | Interface contract | `blocked`: unpinned | Per-message/field SIH interface map |
| SIM-11-E | External SITL distinction | `partial`: rule fixed here | External-physics evidence never recorded as SIH |

## Mode contract

Every PX4_SIH_SITL run must declare:

```text
mode_id, firmware_identity (commit + SHA256), sih_interface_map,
physics_authority=fc_internal, time_mapping, display_identity,
epoch, source_identity
```

With SIH there is exactly one physics authority — the FC-internal model. Display and mission layers consume remapped time; they never run or imply a second physics core. External-physics SITL results (owned or reference) are a different mode and cannot evidence this one.

### Lifecycle

```text
verify SIH in the pinned firmware → pin the interface map
→ declare fc_internal authority and the time mapping
→ run with single-authority audit → stop; reconnect re-binds identity
```

`accepted` means the mode ran with one physics authority and the declared time mapping. It does not mean the FC-internal model matches wksim's external physics numerically.

### Rejection boundary

Reject on unavailable SIH, unmapped interfaces, dual physics, unmapped time, firmware mismatch and foreign epochs. Keep `sih_unavailable`, `interface_unmapped`, `dual_physics_rejected`, `time_unmapped`, `firmware_mismatch` and `foreign_epoch` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket starts no flight controller.

1. **SIH source audit (owner: build maintainer):** verify the pinned PX4 build's SIH mode and interface in source before any run.
2. **Time mapping (owner: runtime maintainer):** implement display/mission remapping onto the FC-internal timeline.
3. **Live slice (owner: validation maintainer):** one bounded SIH run with single-authority and time-mapping evidence.

No current command implements or verifies PX4_SIH_SITL, so none is claimed here.

## Non-goals and preserved blockers

- No SIH mode is enabled and no flight controller is started by this contract slice.
- Owned external-physics SITL evidence keeps its separate mode identity; #1 keeps its scope and state.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for SIM-11 and for the project.
