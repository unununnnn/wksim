# Actual ROS1 point cloud and GridMap occupancy

The isolated run `run-01` passed with the real `plan_env` library from the
complete EGO build recorded in `../39-ego-full-build-20260912`. The probe calls
the product's public `GridMap` API after its real ROS cloud and odometry
callbacks. No planner, flight controller or control-state publisher ran.

- Distro: `RflySim-20.04`; build: `/root/wksim-gridmap-cloud-build-YFwqBG`.
- Runtime: `/root/wksim-gridmap-cloud-run-20260912-01`.
- Private ROS master: `http://127.0.0.1:49835`, PID checked against its owned
  subprocess before any parameters or messages were published.
- Cloud: 100 publications in 10 seconds; the probe received the complete
  11,000-point XYZ32 cloud, with zero duplicates, missing or invalid points.
- Independent Windows verification reconstructed the received 132,000-byte
  payload, compared it byte for byte to the frozen profile centers, checked
  all 11,000 voxel indices and matched the source hashes.
- All eight occupancy queries passed: start/goal and an exterior point free;
  obstacle center, first voxel and inflated edge occupied; exact map limits
  outside. See `run-01/probe.json` for coordinates and actual values.
- Probe and publisher exited 0. The owning runner terminated and reaped its
  master with SIGTERM. No forced kill was needed.

`run-01/received-cloud.json` preserves the actual received bytes as base64.
`provenance.json` pins the library, compiled probe and build sources;
`ldd-sourced.log` records library resolution in the sourced ROS environment.
No native binary or vendor source is included. The original failed builds
are retained: `build.log` lacked the PCL include dependency, and
`build-with-pcl.log` exposed a redundant bare `-lplan_env` link argument.
The corrected standalone target uses the catkin-exported library and passed
in `build-exported-library.log`.

Reproduction requires the sourced Noetic and EGO devel environments:

```sh
python3 validation/gridmap_cloud_probe/run_isolated.py \
  --probe /root/wksim-gridmap-cloud-build-YFwqBG/gridmap_cloud_probe \
  --expected-probe-sha256 b942ec31374fc00f63b09e378d9ebd91b69bf4adef6485301aa4fe9d0569c7b5 \
  --output /root/wksim-gridmap-cloud-run-NEW
```

The runner creates a fresh output directory and an independent master. Its
stationary odometry at `(-4, 0, 3)` is explicitly a synthetic map fixture.
`use_sim_time=false` applies only to this map test. This result does not prove
shared ROS1/ROS2 scene time, real flight feedback, planner output, collision
clearance, arrival, rate acceptance, or Full/G0–G6 completion.

After this run, review added an explicit expected binary hash and full probe
report validation to the runner. `run-01/runner-source.py` preserves the exact
runner used for the original run; the new validator was also applied to the
original raw probe report, without rewriting or rerunning that evidence.
