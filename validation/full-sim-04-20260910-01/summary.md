# #124 / full-sim-04 summary

The six SIM-04 Simulink/DLL SIL atoms were mapped to the frozen row, current ledger, the owned build evidence and the sampling probes. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/sim-04.md`, `docs/plan/full-contracts/sim-04.json`.
- Exact check: `python -B validation/full-sim-04-20260910-01/validate.py` — 20 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 6 SHA-256 values.
- Current result: three partial atoms (owned build, no-controller run, Simulink-not-required rule) and three blocked atoms (selection/init, reset/export, original DLL plugin).
- A local build is not the complete flow; original DLLs remain optional plugins gated on the open #9 ABI decision; daily runs never require Simulink.
- No build, run, implementation, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Simulink&DLL_SIL completion requires the itemized flow, the owned reset/export slice and the #9 ABI decision.
