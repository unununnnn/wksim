# Full OPS-02 — Performance calculation contract

Status: **defined, not implemented**. This is the contract-definition slice for GitHub #153. It does not turn the #23 numerical comparison or a control hover observation into a propulsion-performance acceptance.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:70`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-02`, `followup_ids=[153]`.
- Related parent evidence: #23, `docs/2026-09-09-numerical-conformance-report.md`, and `docs/2026-09-09-numerical-ticket-acceptance-review.md`.
- `Simulator/wksim_core/model.py` accepts 16 finite normalized actuator commands, advances a fixed 1 ms model and returns 120 native doubles. Existing archived output labels some rotor slots as RPM, but the model boundary has no current, voltage, battery or energy channel.
- `Simulator/wksim_core/model_parameters.py` contains motor/rotor coefficients and units. `pid_task.py` can observe a control-level hover thrust value; that value is not an electrical power measurement or an endurance result.
- The existing #23 comparison is a valid fixed-model numerical delivery, with `R1=numerical_failed` retained. It does not establish a FlyEval formula, a physical power source, or a service integration contract.

## Atomic scope

| ID | Frozen capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-02-A | Hover time/endurance | `blocked`: no battery capacity, discharge, reserve or termination semantics at the model boundary | A source-bound battery/mission contract, initial state, usable-energy rule, load sampling and explicit end/failure conditions |
| OPS-02-B | Throttle/hover command | `partial`: normalized command and control hover observation exist; command-to-throttle calibration is not an endurance contract | Mapping, units, actuator limits, hover criterion and a source/version-bound calibration procedure |
| OPS-02-C | Motor current | `blocked`: no current output or sensor source in the owned model/ROS boundary | Per-motor and total-current source, units, sample time, validity and calibration evidence |
| OPS-02-D | Rotor speed | `partial`: archived 120-slot records label the active rotor slots as RPM; source-to-RPM meaning and calibration are not independently accepted | Four-motor mapping, RPM units, sample timing and an independent source/readback check |
| OPS-02-E | Input power | `blocked`: voltage/current channels and electrical losses are absent | Voltage/current acquisition or an explicitly sourced electrical model, with finite-value and stale-data handling |
| OPS-02-F | Efficiency | `blocked`: no accepted numerator/denominator or useful-output definition | Freeze whether efficiency is thrust/power, useful work/energy or another sourced metric; reject zero/invalid denominators |
| OPS-02-G | FlyEval reference flow | `blocked`: an online service and public formula are not established in this checkout | Separate local calculator and service adapter contracts, availability/authentication behavior and same-input comparison evidence |

## Calculation contract

Every result must bind:

```text
model_identity, component/source hashes, configuration identity, run_id,
control_epoch, authority time base, input profile, sample period,
calibration/parameter identity, formula identity, and result units
```

The input side must distinguish a normalized control command from a physical throttle, motor RPM, current, voltage, power and battery state. A control message being accepted is not a measurement. A model output slot being finite is not sufficient to assign it a physical unit without a source mapping.

The result schema should provide, at minimum, per-sample or explicitly aggregated values for `time_s`, `command`, `rpm`, `current_a`, `voltage_v`, `power_w`, `energy_j`, `thrust_n` and `efficiency`, with a validity/source flag for every derived value. Missing channels must be reported as `unavailable`, not filled with zero.

No formula is approved by this ticket. The later implementation must document the source for each formula before it runs. For example, `power_w = voltage_v × current_a` is only valid when both signals share a sample identity and the same electrical boundary; `energy_j` requires an explicit authority-time integration rule; and an efficiency denominator must not silently change between a local calculator and FlyEval.

### Lifecycle and failure semantics

```text
select model/config → freeze calibration and formula identities
→ validate finite inputs and required channels → run fixed or live sample source
→ calculate → write raw inputs and derived results → audit → optional service comparison
```

Reject before calculation on source/hash mismatch, missing required channel, invalid unit, non-finite value, negative physical quantity where the source forbids it, timestamp/epoch mismatch, stale sample, zero denominator or model identity mismatch. `accepted` means the input/result record was validated and stored; it does not mean the vehicle hovered or the energy estimate is physically accurate.

Local calculation and FlyEval integration are separate acceptance paths. A service timeout, unavailable account, changed remote formula or remote result mismatch must leave the local raw calculation intact and must not be converted to a local PASS.

## Evidence-backed follow-up slices

These are proposed successors; no executable performance command exists in the current checkout.

1. **Local metric source (owner: model/physics maintainer):** reserve at most four files, beginning with a new `Simulator/wksim_core/performance.py`, one CLI/runner and targeted validation. First freeze the electrical/propulsion source and unit mapping; do not derive current or power from normalized PWM without evidence.
2. **Local calculation and audit (owner: validation maintainer):** add the smallest standard-library calculator once inputs exist. Test missing/stale/foreign-epoch/zero-denominator/non-finite cases and verify raw inputs are retained. The #23 output comparison remains a source of model-state evidence, not a performance oracle.
3. **FlyEval adapter (owner: integration maintainer):** define a separate optional adapter only after endpoint, formula/version and authentication/availability are evidenced. Its failure cannot invalidate or rewrite the local record.
4. **Endurance run (owner: runtime maintainer):** add a new bounded run only after model, battery and safety budgets are approved; record stop reason and the complete source identities. No run is authorized by this contract alone.

## Non-goals and preserved blockers

- No performance formulas, battery model, service endpoint, calibration, threshold or physical budget is invented here.
- #23 remains closed for its original comparison-delivery scope, while `R1=numerical_failed` and G6 remain unchanged.
- This ticket does not modify the model, control path, native adapter, vendor resources, hardware or external FlyEval service.
- `full_complete` remains `false` for OPS-02 and for the project.
