# #140 / full-model-07 (fixed-wing) summary

The four fixed-wing atoms of MODEL-07 were mapped to the frozen row, current ledger and the multicopter-only owned evidence. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-07-fw.md`, `docs/plan/full-contracts/model-07-fw.json`.
- Exact check: `python -B validation/full-model-07-fw-20260910-01/validate.py` — 17 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 4 SHA-256 values.
- Current result: one partial atom (no-forced-ArduCopter rule) and three blocked atoms (model source, stack/actuators, flight conditions).
- A multicopter stack is never a fixed-wing controller; the compound wing is handled separately under #141.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Fixed-wing completion requires a pinned model source, a declared fixed-wing stack and defined flight conditions.
