# #160 / full-ops-09 summary

The six OPS-09 fault atoms were mapped to the frozen row, current ledger, the GNSS event seam/report, the SceneClock fault semantics and the PID actuator-multiplier disturbance. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/ops-09.md`, `docs/plan/full-contracts/ops-09.json`.
- Exact check: `python -B validation/full-ops-09-20260910-01/validate.py` — 27 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 8 SHA-256 values.
- Current result: five partial atoms (motor fault, sensor bias/freeze/loss, communication anomaly, plan identity, recovery/reset) and one blocked atom (environment disturbance).
- The GNSS seam covers one signal-loss event with strict time/identity rules; the PID `disturbance` is an effective actuator command multiplier for controller evaluation, not a motor fault or wind model. No wind/gust or per-sensor bias/freeze model exists in the owned core.
- No fault injection, solver/runtime code, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Fault completion requires the approved #44 motor slice (#105–#108), a per-sensor fault model on the OPS-08 envelope, an owned disturbance source decision and a per-link communication anomaly audit.
