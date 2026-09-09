# Full OPS-13 — Performance and scale contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #164. It does not extrapolate single-machine or two-vehicle evidence to ten vehicles, arbitrary hardware or distributed real time.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:81`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-13`, `followup_ids=[164]`; parent #1 (Wayfinder, OPEN).
- `Simulator/wksim_runtime/joint_rate.py`: `JointRate` admits only requested rates 0.5 or 1 and raises `RateUnmet` (`rate_unmet/resource_insufficient`) with lateness in nanoseconds; the #20/#33 RateUnmet semantics are preserved unchanged.
- `Simulator/wksim_runtime/scene_clock.py`: 1 ms ticks, 4 ms macro barriers, suspend/fault and recoverable boundaries — the semantic base for time deviation and recovery, without quantified budgets at scale.
- `validation/rate-syscall-scheduler-plan-20260909/` (`report.md`, `COLLECTOR.md`, `collect_tracefs.py`): a read-only WSL syscall/scheduler forensics plan and a hardened private tracefs collector for rate diagnostics. The report records real environment readings (kernel, strace 5.16, tracefs instances, permission knobs) and explicitly does not prove runtime permissions or buffer capacity.
- Existing single-machine speedup (up to 3x) and two-vehicle joint validations are bounded profiles of their own configurations. No ten-vehicle, arbitrary-hardware or multi-host distributed real-time acceptance exists.

## Atomic scope

| ID | Capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-13-A | Target vehicle count | `partial`: two-vehicle joint evidence exists | Declared target count met on the joint scene with per-vehicle identity |
| OPS-13-B | Step rate / speedup | `partial`: 0.5/1.0 rate validation with explicit RateUnmet | Declared rate/speedup sustained per configuration profile |
| OPS-13-C | Throughput and CPU/GPU load | `partial`: read-only tracefs diagnostics exist | Explicit per-configuration load budget met and audited |
| OPS-13-D | Record capacity | `partial`: OPS-11 single-file cap and diagnostics | Recording capacity/throughput at target scale |
| OPS-13-E | Time deviation and recovery window | `partial`: barrier/suspend/recovery semantics unquantified | Quantified deviation bounds and recovery windows at scale |
| OPS-13-F | Distributed real time | `blocked`: no multi-host validation | Multi-host profile with per-host identity and authority time |

## Performance profile contract

Every performance claim must be bound to a profile containing:

```text
profile_id, vehicle_count, step_rate_hz, speedup, hardware_identity,
cpu_budget, gpu_budget, record_throughput, record_capacity,
time_deviation_budget_ns, recovery_window_s, epoch, source_identity
```

A bounded profile proves only its own configuration: hardware, vehicle count and speedup do not extrapolate. A rate breach is reported as `rate_unmet` with lateness evidence — never hidden by averaging. Diagnostics (tracefs collector) inform budgets but are not themselves budget proofs.

### Lifecycle

```text
declare profile with explicit budgets → preflight hardware/permissions
→ run at declared rate and scale → measure with per-step lateness
→ breach = explicit typed error, run continues only by policy
→ stop and seal raw measurements → compare against budgets
```

`accepted` means the measured profile stayed inside every declared budget. It does not mean a different vehicle count, hardware or speedup would pass.

### Rejection boundary

Reject or fail loudly on unmet rate, insufficient resources, exceeded capacity, exceeded time deviation, missed recovery windows, unsupported scale and unverified hardware. Keep `rate_unmet`, `resource_insufficient`, `capacity_exceeded`, `deviation_exceeded`, `recovery_window_missed`, `scale_unsupported` and `hardware_unverified` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket starts no benchmark and changes no rate semantics.

1. **Scale profile (owner: runtime maintainer):** run the declared target vehicle count on the joint scene with per-vehicle identity; requires the target count and hardware identity to be fixed first.
2. **Load budget (owner: performance maintainer):** turn the read-only collector into per-configuration CPU/GPU budget audits; budget values must be decided before running.
3. **Capacity plan (owner: runtime maintainer):** recording capacity at scale under the OPS-11 record contract and its pending capacity policy.
4. **Distributed slice (owner: performance maintainer):** no multi-host authority/identity design exists; expert prerequisite before any distributed ticket.

No current command implements ten-vehicle, arbitrary-hardware or distributed real-time acceptance, so none is claimed here.

## Non-goals and preserved blockers

- No benchmark is run and no rate, barrier or collector semantics are changed by this contract slice.
- #20/#33 RateUnmet semantics and #8 supervision budgets are unchanged; the tracefs collector remains read-only diagnostics.
- #23/G6 numerical prerequisites, #9 plugin/ABI and #56 device/license conditions remain unchanged. `R1=numerical_failed` is unaffected.
- `full_complete` remains `false` for OPS-13 and for the project.
