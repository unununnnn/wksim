# #126 / full-sim-08 summary

The five SIM-08 APM_SITL_NET atoms were mapped to the frozen row, current ledger and the owned ArduCopter evidence. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/sim-08.md`, `docs/plan/full-contracts/sim-08.json`.
- Exact check: `python -B validation/full-sim-08-20260910-01/validate.py` — 18 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: three partial atoms (owned physics, native mission, vehicle scope rule) and two blocked atoms (NET operation mapping, stop/reconnect mapping).
- Verified ArduCopter evidence covers only that vehicle/configuration; other ArduPilot vehicles cannot substitute.
- No SITL session, implementation, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. APM_SITL_NET completion requires the itemized reference mapping and the stop/reconnect audit.
