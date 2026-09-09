# #142 / full-model-08 summary

The four MODEL-08 CarAckerman atoms were mapped to the frozen row, current ledger, the multicopter-only core and the OPS-07 environment contract. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-08.md`, `docs/plan/full-contracts/model-08.json`.
- Exact check: `python -B validation/full-model-08-20260910-01/validate.py` — 17 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (ground-contact dependency rule) and three blocked atoms (interfaces, trajectory, terrain).
- Ground acceptance requires the OPS-07 terrain/contact implementation; aerial evidence never substitutes.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. CarAckerman completion requires a pinned source and the terrain query seam.
