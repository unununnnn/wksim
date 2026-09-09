# #136 / full-model-03 summary

The four MODEL-03 tricopter atoms were mapped to the frozen row, current ledger and the owned Quad X/Hex identities. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-03.md`, `docs/plan/full-contracts/model-03.json`.
- Exact check: `python -B validation/full-model-03-20260910-01/validate.py` — 19 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (non-coverage rule) and three blocked atoms (configuration, servo mapping, model/tests).
- The tail servo is part of the actuation contract; quad/hex evidence never substitutes for a tricopter configuration.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Tricopter completion requires a pinned configuration source, the servo mapping freeze and owned model tests.
