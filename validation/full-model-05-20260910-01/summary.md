# #138 / full-model-05 summary

The four MODEL-05 X8 atoms were mapped to the frozen row, current ledger and the owned Quad X record. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-05.md`, `docs/plan/full-contracts/model-05.json`.
- Exact check: `python -B validation/full-model-05-20260910-01/validate.py` — 16 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 4 SHA-256 values.
- Current result: one partial atom (non-coverage rule) and three blocked atoms (configuration, propulsion, mixing).
- X8 is a distinct configuration; a scaled quadrotor mixing matrix is a contract rejection.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. X8 completion requires a pinned source, the propulsion parameters and the mixing audit.
