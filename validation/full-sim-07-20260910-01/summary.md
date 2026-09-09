# #125 / full-sim-07 summary

The five SIM-07 EXT_SIM_NET atoms were mapped to the frozen row, current ledger and the owned joint time seam. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/sim-07.md`, `docs/plan/full-contracts/sim-07.json`.
- Exact check: `python -B validation/full-sim-07-20260910-01/validate.py` — 16 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 4 SHA-256 values.
- Current result: one partial atom (owned joint time seam) and four blocked atoms (reference identity, physics authority, clock mapping, failure semantics).
- Exactly one authority per quantity; external clocks map through a pinned mapping only, never wall-clock alignment.
- No external link, implementation, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. EXT_SIM_NET completion requires a pinned reference system, the authority/clock contract and one bounded end-to-end slice.
