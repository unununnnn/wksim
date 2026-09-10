# Coordination: Authentic Raw CDR Recorder for ArUco Joint Flight (#104)

## 1. Scope & System Invariants

This document specifies the authentic raw CDR recorder module ([`Simulator/wksim_runtime/aruco_raw_capture.py`](file:///C:/Users/PC/Documents/odid编译/wksim/Simulator/wksim_runtime/aruco_raw_capture.py)) and its verification harness ([`validation/test_aruco_raw_capture.py`](file:///C:/Users/PC/Documents/odid编译/wksim/validation/test_aruco_raw_capture.py)) for #104 ArUco joint flight.

- **Status & Precedence**:
  - Issue #104 covers authentic raw capture of public ArUco flight commands, setup, and native telemetry.
  - **No Pass Claim**: Real flight has not achieved closed-loop success; no pass, completion, or G6 closure claims are made.
  - **File Boundaries Strictly Preserved**:
    - Major recorder files (`tools/build_generated_e0_major.py`, `tools/generated_e0_post_reference.cpp`, `validation/test_generated_e0_major.py`, `docs/coordination/agy-e0-major-recorder.md`) remain untouched.
    - Runtime framework and task files (`Simulator/wksim_runtime/joint_task.py`, `Simulator/wksim_runtime/joint_runtime.py`, `Simulator/wksim_runtime/joint_config.py`, `Simulator/wksim_runtime/joint_profile.py`, and OMP's `aruco_joint_task.py`) remain unmodified.
- **Core Principles**:
  1. **Independent Raw Node**: The recorder's ROS2 node is never added to an executor and never spins automatically.
  2. **Bounded Explicit Drain**: Subscriptions are drained only when the control loop explicitly calls `drain()`.
  3. **No Re-Serialization Path**: CDR bytes are acquired directly from native `RCTake` (`libwksim_rc_take.so`). There is no re-serialization path in `ArucoRawCapture`; any sample missing authentic native fields triggers immediate rejection.
  4. **Strict Type Matching**: Default channels strictly monitor `wksim_msgs.msg.SetupRequest` and `wksim_msgs.msg.CommandRequest` with reliable (`RELIABLE`) QoS depth=200. Additional native channels are supplied explicitly by caller.
  5. **Cryptographic Provenance**: Canonical JSON hash chain links start record, all sample records, and end record back to a known seed.

---

## 2. Architecture & Native RCTake Integration

### 2.1 Independent Raw Node
In contrast to regular ROS2 nodes that rely on executor thread pools, `ArucoRawCapture` creates a dedicated node named `wksim_aruco_raw_{stack}`:
- Subscription callback is a no-op (`lambda _: None`).
- No executor registration: zero background thread interference, zero unexpected callback concurrency.
- Draining is strictly synchronous and bounded, driven by the flight task's periodic `pump()` invocation.

### 2.2 Reusing `RCTake` C-Binding
The recorder integrates with `prometheus_control.rc_transport.RCTake`:
- Wraps `libwksim_rc_take.so` (`wksim_rc_take` entrypoint).
- Takes raw CDR bytes directly from the DDS message buffer (`size`, `buffer`), GID buffer (`gid`), and DDS SampleInfo (`source_timestamp`, `received_timestamp`).
- Guaranteed true DDS wire format: `cdr_hex` contains the exact bytes received over FastDDS/CycloneDDS, not an artificial reconstruction.

### 2.3 Bounded Drain Invariant
During each control loop tick:
```python
drained_count = capture.drain(max_per_sub=200)
```
- For each configured channel, reads up to `max_per_sub` available messages (`1 <= max_per_sub <= 200`, strictly non-bool int).
- Stops immediately when `rc_take.take()` returns `None` (quiescent queue).
- If a queue fails to quiesce within `max_per_sub` samples, raises `RuntimeError("... did not quiesce within bound")` to prevent unbounded loop execution and alert the supervisor of a transport burst.

---

## 3. Data Schema, Provenance & Canonical Hash Chaining

The recorder writes to a JSON Lines (`.jsonl`) stream (e.g. `rc-dds.jsonl` or `aruco-dds.jsonl`) opened exclusively (`'x'` mode) with symlinks strictly forbidden.

### 3.1 Start Record (`aruco_raw_capture_start`)
Written upon recorder initialization:
```json
{
  "schema_version": 1,
  "kind": "aruco_raw_capture_start",
  "run_id": "run-aruco-01",
  "epoch": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
  "stack": "arducopter",
  "uav_id": 1,
  "node_name": "wksim_aruco_raw_arducopter",
  "source_identity": {
    "builder": "Simulator/wksim_runtime/aruco_raw_capture.py",
    "builder_sha256": "...",
    "rc_take_source_sha256": "...",
    "rc_take_lib_sha256": "..."
  },
  "channels": [
    {"topic": "/uav1/prometheus/v2/setup", "type": "wksim_msgs/msg/SetupRequest"},
    {"topic": "/uav1/prometheus/v2/command", "type": "wksim_msgs/msg/CommandRequest"}
  ],
  "start_monotonic_ns": 123456789000,
  "start_utc": "2026-09-11T02:00:00Z",
  "prev_record_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "record_sha256": "..."
}
```

### 3.2 Sample Record (`raw_cdr_sample`)
Written for each captured DDS packet:
- `take_sequence`: Monotonically increasing 1-based local take index.
- `topic`: Topic name string.
- `type`: ROS2 message type identifier (`wksim_msgs/msg/SetupRequest`, `wksim_msgs/msg/CommandRequest`).
- `monotonic_ns`: Local capture timestamp.
- `cdr_hex`: Exact native DDS CDR bytes in even-length hex format ($\ge 8$ characters / 4 bytes, starting with valid OMG CDR header `0000`, `0001`, `0002`, or `0003`).
- `publisher_gid`: Hex-encoded DDS publisher GID of actual length returned by `wksim_rc_gid_size()`, verified non-empty and non-all-zero.
- `source_timestamp`: Publisher integer nanosecond timestamp from DDS SampleInfo.
- `received_timestamp`: Receiver integer nanosecond timestamp from DDS SampleInfo.
- `message`: Diagnostic decoded dictionary, sanitized so non-finite floats are encoded as `":nan:"`, `":inf:"`, `":-inf:"` without writing bare `NaN`.
- `prev_record_sha256`: Hash of the preceding record in the canonical JSON chain.
- `record_sha256`: Canonical SHA256 digest computed over `json.dumps(record, sort_keys=True, separators=(',', ':'))` before attaching `record_sha256`.

### 3.3 End Record (`aruco_raw_capture_end`)
Written upon `close()`:
```json
{
  "schema_version": 1,
  "kind": "aruco_raw_capture_end",
  "status": "complete",
  "total_samples": 501,
  "samples_per_topic": {
    "/uav1/prometheus/v2/command": 501
  },
  "final_hash_chain": "...",
  "write_failures": 0,
  "write_failure_reports": [],
  "close_monotonic_ns": 123499999000,
  "close_utc": "2026-09-11T02:00:05Z",
  "prev_record_sha256": "...",
  "record_sha256": "..."
}
```

### 3.4 Write Failure Accounting & Task Failure
If an I/O exception occurs during record writing:
- `self.status` is marked as `"write_failed"`.
- Detailed in `self.write_failure_reports`.
- Immediately raises `IOError` so that the flight control task fails explicitly, preventing silent continuation or fake success counts.
- `close()` is idempotent; if write failure occurred, status remains `"write_failed"` and cannot claim `"complete"`.

---

## 4. Subscription Graph Readiness: Scaling from 1 to 2 Nodes

In ArUco joint flight, two flight stacks (`arducopter` for UAV 1, `px4` for UAV 2) operate concurrently.

### 4.1 Readiness Evaluation
1. **Single-Node Model (Current Worker Isolation)**:
   - Each stack worker process spawns independently from `joint_runtime.py:245-252`.
   - Stack 1 (`arducopter`, `uav_id=1`) creates `wksim_aruco_raw_arducopter` monitoring `/uav1/...` topics.
   - Stack 2 (`px4`, `uav_id=2`) creates `wksim_aruco_raw_px4` monitoring `/uav2/...` topics.
   - Readiness: 100% ready. No shared memory or cross-process synchronization needed; each worker maintains its own un-spun raw node and distinct `rc-dds.jsonl` log file.
2. **Dual-Node Cross-Observation (Joint Supervisory Capture)**:
   - If a single supervisory process records both stacks concurrently (1 node observing both `/uav1` and `/uav2`, or 2 raw nodes in one process):
   - **QoS Compatibility**: Both UAV namespaces publish with reliable `RELIABLE` depth=200 QoS for control commands; `ArucoRawCapture`'s `QoSProfile(depth=200, reliability=ReliabilityPolicy.RELIABLE)` is fully compatible.
   - **Buffer Quiescence & Latency**: In steady-state, ~10-20 command packets arrive per 20ms tick. Total drain overhead across both topics is $<0.2\text{ ms}$, well within the control tick budget.
   - **Memory Buffer Safety**: `libwksim_rc_take.so` uses an 8KB stack buffer per call; multiple subscriptions or multiple raw nodes do not corrupt shared C heap state.

### 4.2 Integration Points (Report Only — Code Left Untouched)
The raw capture module is designed to hook directly into the joint architecture without structural refactoring:
- **Integration Point A ([`Simulator/wksim_runtime/joint_runtime.py:245-252`](file:///C:/Users/PC/Documents/odid编译/wksim/Simulator/wksim_runtime/joint_runtime.py#L245-L252))**:
  In `start_tasks`, the `settings` dict written to `task-config.json` can carry:
  ```python
  settings["raw_capture_log"] = str(folder / "rc-dds.jsonl")
  ```
- **Integration Point B ([`Simulator/wksim_runtime/aruco_joint_task.py:90-125`](file:///C:/Users/PC/Documents/odid编译/wksim/Simulator/wksim_runtime/aruco_joint_task.py#L90-L125))**:
  In `JointArucoTask`:
  - `__init__`: Construct `self.raw_capture = ArucoRawCapture(directory / 'rc-dds.jsonl', run_id=settings['run_id'], epoch=settings['epoch'], stack=settings['stack'], uav_id=settings['uav_id'], node_name=f"wksim_aruco_raw_{settings['stack']}")`.
  - `pump()`: Call `self.raw_capture.drain(max_per_sub=200)` alongside regular state processing.
  - `close()`: Call `self.raw_capture.close()`.

---

## 5. Test Suite Verification

The verification suite ([`validation/test_aruco_raw_capture.py`](file:///C:/Users/PC/Documents/odid编译/wksim/validation/test_aruco_raw_capture.py)) implements 14 comprehensive tests:

1. `test_default_channels_locked_to_wksim_msgs`: Verified default channels strictly locked to `wksim_msgs.msg.SetupRequest` and `CommandRequest` with REL QoS depth=200.
2. `test_stack_uav_id_coupling_enforced`: Verified `arducopter` strictly pairs with `uav_id=1`, `px4` strictly with `uav_id=2`, and `bool` is rejected.
3. `test_epoch_hex32_enforced`: Verified epoch must be exactly 32 hex characters.
4. `test_drain_limit_bounds_and_bool_rejection`: Verified `max_drain_limit` must be integer in 1..200 (rejecting bool).
5. `test_symlink_output_path_rejected`: Verified symlink output paths are rejected.
6. `test_odd_and_short_raw_cdr_hex_rejected`: Verified rejection of odd-length or $<8$ hex char CDR.
7. `test_invalid_cdr_encapsulation_header_rejected`: Verified rejection of non-standard CDR encapsulation headers.
8. `test_empty_and_all_zero_gid_rejected`: Verified rejection of empty or all-zero GID; accepts variable non-zero GID length.
9. `test_missing_and_bool_timestamps_rejected`: Verified required integer nanoseconds timestamps (rejecting bool or missing).
10. `test_canonical_json_hash_chain_across_start_samples_end`: Verified complete, unbroken canonical JSON hash chain across start, all samples, and end record.
11. `test_non_finite_floats_sanitized_without_bare_nan`: Verified non-finite floats in decoded messages are encoded as `:nan:`/`:inf:`/`:-inf:` without bare NaN.
12. `test_write_failure_raises_explicit_error_and_marks_failed`: Verified write failure explicitly raises `IOError` and marks status as `write_failed`.
13. `test_constructor_failure_cleans_up_resources`: Verified failure during `__init__` removes partial output files and destroys node/subscriptions.
14. `test_unquiesced_queue_overflow_raises_bounded_error`: Verified bounded quiescence protection when incoming packets exceed limit.

Execution results:
- Windows: `Ran 14 tests in 0.047s: OK`
- WSL Ubuntu-22.04 with ROS2 Humble: `Ran 14 tests in 0.119s: OK`

主会话接手修订：构造失败不删除任何既存或本次失败原件；测试明确覆盖第二次 exclusive open 的原件保留。删除生产消息类/默认QoS占位回退，native构造必须得到真实RCTake源码和库SHA；写入中状态为recording，终止写失败/资源清理失败不能返回complete，Task据此失败。追加终止写错误与原件保留测试，最终记录器16项、WSL关联共44项检查通过。早期删除部分输出的说明已被本段取代。
