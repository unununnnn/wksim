# #127 / full-sim-11 summary

The five SIM-11 PX4_SIH_SITL atoms were mapped to the frozen row, current ledger, the pinned PX4 identity and the owned external-SITL path. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/sim-11.md`, `docs/plan/full-contracts/sim-11.json`.
- Exact check: `python -B validation/full-sim-11-20260910-01/validate.py` — 19 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 6 SHA-256 values.
- Current result: two partial atoms (unique-authority and distinction rules fixed) and three blocked atoms (SIH availability, time remapping, interface map).
- Under SIH the FC-internal model is the only physics authority; owned external-physics SITL evidence never covers this mode.
- No SIH run, FC start, implementation, UE/model/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. PX4_SIH_SITL completion requires the source audit of the pinned firmware, the interface map and the time-mapping slice.
