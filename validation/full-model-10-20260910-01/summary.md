# #144 / full-model-10 summary

The four MODEL-10 CarNoCtrl atoms were mapped to the frozen row, current ledger, the FC-driven multicopter core and the OPS-07 contract. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-10.md`, `docs/plan/full-contracts/model-10.json`.
- Exact check: `python -B validation/full-model-10-20260910-01/validate.py` — 17 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (FC-independence rule) and three blocked atoms (direct inputs, observation, terrain).
- No-controller acceptance never boots a flight controller; observations are truth outputs, not FC telemetry.
- No model implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. CarNoCtrl completion requires a pinned source and the observation slice on the OPS-07 seam.
