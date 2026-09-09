# #159 / full-ops-08 summary

The six OPS-08 sensor atoms were mapped to the frozen row, current ledger, the closed #30/#31 slices, the RGB/depth components and the offline ArUco seam. The contract is complete; the Full row remains a gap.

- Files: `docs/plan/full-contracts/ops-08.md`, `docs/plan/full-contracts/ops-08.json`.
- Exact check: `python -B validation/full-ops-08-20260910-01/validate.py` — 28 assertions passed, 0 skipped.
- Inputs and source identities: `hashes.json`; the validator checked 9 SHA-256 values.
- Current result: four partial atoms (base truth feed, RGB, depth/point cloud, offline perception input) and two blocked atoms (calibration/noise/latency, extended capabilities such as scanning LiDAR and segmentation).
- `Simulator/wksim_core/` contains no noise/bias/calibration model; the ArUco report explicitly disclaims a live sensor-to-stack loop.
- No sensor implementation, capture, UE/model/FC/ROS/MATLAB process, hardware command or numerical-budget change occurred.

This is a contract-definition delivery only. Sensor completion requires a frozen per-sensor calibration/noise/latency budget, a sensor manifest binding, a live marked-scene loop and an owned LiDAR capability decision.
