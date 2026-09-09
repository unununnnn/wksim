# #122 / full-sim-02 summary

The five SIM-02 PX4_SITL atoms were mapped to the frozen row, current ledger and the owned PX4 physics/DDS evidence. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/sim-02.md`, `docs/plan/full-contracts/sim-02.json`.
- Exact check: `python -B validation/full-sim-02-20260910-01/validate.py` — 18 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 6 SHA-256 values.
- Current result: three partial atoms (owned physics, native DDS mission, product entry) and two blocked atoms (TCP mode selection, stop/reconnect mapping).
- Owned-path success is not the reference mode's operation mapping; each mode item requires individual verification.
- No SITL session, implementation, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. PX4_SITL completion requires the itemized reference mode mapping and the stop/reconnect audit.
