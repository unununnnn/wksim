# #148 / full-model-14 summary

The four MODEL-14 CopterSILVelCtrl atoms were mapped to the frozen row, current ledger and the owned controller modules. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-14.md`, `docs/plan/full-contracts/model-14.json`.
- Exact check: `python -B validation/full-model-14-20260910-01/validate.py` — 19 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 6 SHA-256 values.
- Current result: two partial atoms (FC-velocity distinction, controller reuse) and two blocked atoms (SIL workflow, acceptance).
- The loop closes against model truth without an FC; #32's real-FC velocity evidence never covers this workflow.
- No loop implementation, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. CopterSILVelCtrl completion requires the frozen criteria and the SIL loop implementation.
