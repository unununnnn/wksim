# Full OPS-08 — Sensor contract

Status: **defined, not implemented**. This bounded definition slice is GitHub #159. It does not promote the accepted RGB/depth slices or the offline ArUco seam into a complete sensor capability.

## Source and current evidence

- Frozen source row: `docs/plan/full-scope-expansion.md:76`.
- Machine ledger row: `docs/plan/full-followup-tickets.json`, `id=OPS-08`, `followup_ids=[159]`; parents #30 (real RGB camera with time and calibration, CLOSED) and #31 (depth camera and depth-generated point cloud, CLOSED).
- `Simulator/ue55/Source/WksimVisual/WksimRgbSensor.{h,cpp}` with `docs/rgb-capture-component.md`: transient SceneCapture2D camera, BGRA8 readback, PNG/JSON persistence, explicit run/instance/epoch/step/model-time capture identity, strictly increasing steps, `DroppedBusy` semantics and no desktop/viewport capture.
- `Simulator/ue55/rgb.py`: current-epoch UDP notification `Reader` bound from authoritative run status (`set_epoch`), with generation and minimum-step admission.
- `Simulator/ue55/depth.py`: bounded depth notification reader with explicit `max_depth_meters` and indexed ENU point-cloud export.
- `docs/rgb-geometry-fixture.md`: frozen projection geometry/calibration fixtures for the RGB path.
- `Simulator/wksim_perception/aruco.py` and `docs/2026-09-09-aruco-consumer-report.md`: offline ArUco image-to-target seam with explicit dictionary/ID/side length, age/distance/speed/reprojection limits and Prometheus target output. The report explicitly states this is not a real sensor-to-dual-stack flight loop.
- The owned model core feeds truth-level state to PX4/ArduCopter SITL. No calibration, noise, bias or latency model exists for base sensors in `Simulator/wksim_core/`; scanning LiDAR and segmentation have no owned source in this checkout.

## Atomic scope

| ID | Sensor capability | Current state | Required proof |
| --- | --- | --- | --- |
| OPS-08-A | Base sensor truth feed | `partial`: owned core feeds truth-level IMU/GNSS-class state to both stacks with run identity | Per-sensor identity, units, frame, authoritative time and rate budget recorded per sample |
| OPS-08-B | Calibration/noise/latency | `blocked`: no calibration identity, noise, bias or latency model exists for base sensors | Explicit per-sensor model with source, parameters, budget and rejection of uncalibrated claims |
| OPS-08-C | RGB camera | `partial`: #30 closed a timed, calibrated, epoch-bound RGB slice | Live capture identity, mount extrinsics and current-generation delivery preserved under load |
| OPS-08-D | Depth and point cloud | `partial`: #31 closed depth with max-depth semantics and ENU point-cloud export | Depth/point-cloud identity, units and validity intervals audited end to end |
| OPS-08-E | Prometheus perception input | `partial`: offline ArUco consumer produces Prometheus-format targets from generated images | A live sensor-to-consumer loop on a real marked scene with the same contract |
| OPS-08-F | Extended capabilities | `blocked`: scanning LiDAR, segmentation and remaining capabilities have no owned source | Per-capability contract, owned implementation and acceptance evidence |

## Sensor sample contract

Every admitted sensor sample must carry an envelope containing:

```text
sensor_id, sensor_type, vehicle_id, mount_extrinsics (pose in vehicle frame),
coordinate_frame, units, calibration_identity/hash, epoch, generation, step,
sim_time_ns, acquisition_wall_time_ns, valid_from_step, valid_until_step,
rate_budget, payload_schema, source_identity
```

A sample without a resolvable sensor/calibration/mount identity is rejected. Wall-clock acquisition time is recorded separately and never substitutes for authoritative step/time. A render artifact or display frame is not simulated sensor data; a truth-level feed without a declared noise/latency model must not be reported as a calibrated sensor.

### Lifecycle

```text
declare sensor manifest → configure calibration/mount/units → bind epoch/generation
→ run with per-step identity and rate budget → drop/reject busy or stale explicitly
→ stop → reconnect/reset re-binds current epoch/generation only
→ result with raw sample identities retained
```

`accepted` means the sample envelope and identities are valid. It does not mean a consumer used the sample, a control loop closed on it, or a flight task succeeded. Reconnect delivers only current-generation data; retired streams and old epochs are rejected.

### Rejection boundary

Reject before admission on unknown sensor, missing calibration, mount/identity mismatch, unit or frame mismatch, stale/future/out-of-order samples, unsupported sensor type, unmet rate budget, busy capture (`busy_dropped`, never queued) and display-only sources. Keep `sensor_not_found`, `calibration_missing`, `mount_mismatch`, `unit_mismatch`, `frame_mismatch`, `stale_sample`, `future_sample`, `out_of_order`, `unsupported_sensor`, `rate_unmet`, `busy_dropped` and `display_only` distinct.

## Evidence-backed follow-up slices

These are proposed successors; this ticket implements no sensor model and starts no capture.

1. **Base sensor model (owner: model maintainer):** add the smallest per-sensor calibration/noise/latency seam in `Simulator/wksim_core/` with unit tests. Requires a frozen per-sensor parameter and error budget first; a truth feed stays the default, not a calibrated claim.
2. **Sensor manifest (owner: runtime maintainer):** bind sensor/calibration/mount identity into the run manifest so every sample resolves its envelope; reject unbound sensors before the run.
3. **Perception live loop (owner: perception maintainer):** reuse `Simulator/wksim_perception/aruco.py` unchanged and run one real marked-scene RGB-to-target loop with raw audit. The offline fixture evidence cannot be replayed as live proof.
4. **Scanning LiDAR slice (owner: UE/perception maintainer):** no owned source exists; requires an explicit capability decision and expert prerequisite before any implementation ticket is posted.

No current command implements base-sensor calibration/noise/latency, scanning LiDAR or segmentation, so no new sensor process or capture is claimed here.

## Non-goals and preserved blockers

- No sensor model, LiDAR, segmentation or live perception loop is implemented by this contract slice.
- #30 and #31 remain closed bounded slices; their evidence is not relabelled as full sensor acceptance. The ArUco seam remains offline interface evidence.
- #9 plugin/ABI, #56 device/license conditions and #23/G6 numerical prerequisites remain unchanged. `R1=numerical_failed` and #20/#33 RateUnmet are unaffected.
- `full_complete` remains `false` for OPS-08 and for the project.
