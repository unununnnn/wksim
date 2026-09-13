# #133 / full-comm-06 summary

The five COMM-06 Mavlink_NoGPS atoms were mapped to the frozen row, current ledger and the GNSS event seam. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/comm-06.md`, `docs/plan/full-contracts/comm-06.json`.
- Exact check: `python -B validation/full-comm-06-20260910-01/validate.py` — 21 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (fault/mode distinction) and four blocked atoms (sensor set, positioning, control conditions, reference behavior).
- The #45 GNSS seam is an interruption event inside a GPS-capable configuration; it is not this mode's configuration contract.
- No mode declaration, implementation, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Mavlink_NoGPS completion requires a frozen mode definition, the control legality matrix and an observed live slice.
