# #164 / full-ops-13 summary

The six OPS-13 performance/scale atoms were mapped to the frozen row, current ledger, the JointRate/SceneClock semantics and the read-only tracefs diagnostics. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/ops-13.md`, `docs/plan/full-contracts/ops-13.json`.
- Exact check: `python -B validation/full-ops-13-20260910-01/validate.py` — 25 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 8 SHA-256 values.
- Current result: five partial atoms (vehicle count, step rate, throughput/load, record capacity, time deviation/recovery) and one blocked atom (distributed real time).
- Bounded profiles prove only their own configuration; #20/#33 RateUnmet semantics and the read-only collector remain unchanged.
- No benchmark, runtime change, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Completion requires a fixed target count and hardware identity, per-configuration load budgets, the OPS-11 capacity policy and a multi-host authority design.
