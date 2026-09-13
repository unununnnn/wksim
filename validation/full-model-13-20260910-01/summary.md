# #147 / full-model-13 summary

The four MODEL-13 MulticopterNOpx4 atoms were mapped to the frozen row and current ledger. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-13.md`, `docs/plan/full-contracts/model-13.json`.
- Exact check: `python -B validation/full-model-13-20260910-01/validate.py` — 15 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 4 SHA-256 values.
- Current result: one partial atom (PX4-independence rule) and three blocked atoms (interface, control method, reference observation).
- The mode is defined by observed reference behavior; name inference and PX4 substitution are contract rejections.
- No implementation, observation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. MulticopterNOpx4 completion requires the reference observation first, then the interface freeze.
