# #141 / full-model-07 (compound wing) summary

The four compound-wing atoms of MODEL-07 were mapped to the frozen row, current ledger and the multicopter-only owned evidence. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-07-vtol.md`, `docs/plan/full-contracts/model-07-vtol.json`.
- Exact check: `python -B validation/full-model-07-vtol-20260910-01/validate.py` — 17 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 4 SHA-256 values.
- Current result: one partial atom (no-forced-ArduCopter rule) and three blocked atoms (model source, actuation, transition conditions).
- Both actuator sets and the transition regime are required; multicopter or fixed-wing evidence alone never covers the compound wing.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Compound-wing completion requires a pinned source, both actuator mappings and the transition audit.
