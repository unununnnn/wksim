# #123 / full-sim-03 summary

The four SIM-03 PX4_SITL_RFLY atoms were mapped to the frozen row, current ledger and the pinned standard-PX4 identity. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/sim-03.md`, `docs/plan/full-contracts/sim-03.json`.
- Exact check: `python -B validation/full-sim-03-20260910-01/validate.py` — 18 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (non-substitution rule fixed) and three blocked atoms (firmware identity, protocol delta, use conditions).
- Only pinned RFly-custom firmware on its pinned protocol can evidence this mode; standard PX4 results are contract rejections here.
- No firmware fetch/pin/run, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. PX4_SITL_RFLY completion requires the pinned custom firmware, its protocol delta and recorded use conditions.
