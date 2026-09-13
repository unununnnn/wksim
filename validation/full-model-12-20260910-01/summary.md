# #146 / full-model-12 summary

The four MODEL-12 MulticopterNoCtrl atoms were mapped to the frozen row, current ledger and the owned FC-driven multicopter base. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-12.md`, `docs/plan/full-contracts/model-12.json`.
- Exact check: `python -B validation/full-model-12-20260910-01/validate.py` — 18 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (owned multicopter base) and three blocked atoms (direct inputs, motion, reset).
- No-controller mode never boots a flight controller; reset is a declared state transition, not a pause.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. MulticopterNoCtrl completion requires the direct input schema and the reset slice.
