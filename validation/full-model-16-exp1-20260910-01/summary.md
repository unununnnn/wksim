# #150 / full-model-16 (Exp1_MinModelTemp) summary

The five Exp1 atoms of MODEL-16 were mapped to the frozen row, current ledger, the readiness probe's pinned material and the owned build host. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/model-16-exp1.md`, `docs/plan/full-contracts/model-16-exp1.json`.
- Exact check: `python -B validation/full-model-16-exp1-20260910-01/validate.py` — 19 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (editable material pinned, local-only) and four blocked atoms (I/O, generation, build/import, run).
- Missing editable material is an explicit blocker, never substituted; MATLAB remains a minimal interface.
- No generation/build/run, UE/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Exp1 completion requires the I/O freeze and one build-import-run audit.
