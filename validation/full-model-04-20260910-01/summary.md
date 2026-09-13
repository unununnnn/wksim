# #137 / full-model-04 summary

The five MODEL-04 coaxial Y6 atoms were mapped to the frozen row, current ledger and the planar Hex identity. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-04.md`, `docs/plan/full-contracts/model-04.json`.
- Exact check: `python -B validation/full-model-04-20260910-01/validate.py` — 17 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (non-coverage rule) and four blocked atoms (geometry, rotation signs, allocation, parameters).
- Coaxial interaction is modeled from a pinned source or declared unmodeled; planar allocation never substitutes.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Y6 completion requires a pinned coaxial source, the allocation matrix and owned tests.
