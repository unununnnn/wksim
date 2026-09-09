# #131 / full-comm-04 summary

The four COMM-04 Mavlink_Simple atoms were mapped to the frozen row, current ledger and the owned telemetry substrate. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/comm-04.md`, `docs/plan/full-contracts/comm-04.json`.
- Exact check: `python -B validation/full-comm-04-20260910-01/validate.py` — 20 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 5 SHA-256 values.
- Current result: one partial atom (distinct-implementation rule fixed) and three blocked atoms (reduction, frequencies, reference capture).
- The simple mode is defined by its pinned reduction versus the COMM-03 set; relabelling Full is a contract rejection; #32 is not evidence for this mode.
- No MAVLink implementation, capture, QGC session, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Mavlink_Simple completion requires the frozen reduction, a reference capture and a distinct implementation.
