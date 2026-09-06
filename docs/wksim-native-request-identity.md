# Native request identity and receive freshness

Final integration is documented in [the control session contract](wksim-control-session.md)
and [the second-wave report](2026-09-05_product-second-wave-report.md): the new
candidate was built and both real FCs passed explicit ground process restart.
The original sidecar evidence and its earlier import/coverage limitations below
are retained as history, not substituted for that later integration.

Issue #14 sidecar contract, 2026-09-05. Only the two native adapters and native
validation files implement this portion; session envelopes, node integration and
durable allocation are owned by the main implementation.

## PX4 requests

`PX4Link(..., request_identity=callable)` calls the allocator once before each
native publish. The result is a two-integer pair in 1..255, stored on that pending
request and sent as `VehicleCommand.source_system/source_component`. Allocator
failure and a pair reused within this adapter prevent publication. Reservations
are not released after cancellation, completion, timeout or publication failure.
The main `RunSession.native_identity()` must durably reserve before returning,
including across process restarts, and fail closed at exhaustion. Its proposed
200..254 × 1..255 range (14,025 pairs) fits the actual schema and avoids target
system 22 and GCS system 255. Allocation must remain unique across any runs that
can still receive each other's delayed ACKs, not just within one process.

ACK admission checks the current request's pair, command, timestamp at least as
new as request publication's FC boot-time reference, and strictly advancing ACK
timestamps. IN_PROGRESS is not completion; decreasing reported progress and
replacement of an already terminal ACK are rejected. Wrong identities do not
advance any ACK watermark or invalidate state. `poll_request()` retains its
`None` or `(bool, reason)` interface and `native_result_N` diagnostics.

Without a callback, legacy direct diagnostics retain the fixed default 245/191
identity and existing constructor options. This mode is explicitly **unscoped**:
a delayed same-command ACK addressed to that fixed pair, generated after the new
request's boot-time reference, can complete the wrong request. Timestamp checking
alone cannot prove restart isolation. Product code must always supply the durable
allocator; this adapter cannot verify cross-process allocator durability.

Read-only source evidence from the actual local FC tree:

- `/opt/aerotwinsim/src/px4-d6f12ad1/src/modules/commander/Commander.cpp:2673`:
  ACK command/result are populated from the handled request; lines 2677–2679 copy
  `cmd.source_system` and `cmd.source_component`, then use `hrt_absolute_time()`.
- Its `msg/versioned/VehicleCommand.msg:193` declares `uint8 source_system` and
  **uint16** `source_component`; `VehicleCommandAck.msg` likewise has uint8 target
  system and uint16 target component. The chosen uint8-pair subset is valid, but
  claiming that the actual component schema is uint8 would be incorrect.
- ACK has `result_param1` (progress) and `result_param2`; it has no echoed request
  timestamp or application session UUID. Source inspection proves the Commander
  path, not delivery, queue retention or all possible third-party ACK producers.

## ArduCopter services

Each pending operation stores its exact `call_async` Future and client. Cancel
detaches the operation first, removes that exact Future from the client's pending
map, and cancels it. A later old Future completion cannot satisfy a new operation.
Mode success still requires both status success and the requested `curr_mode`.

Read-only evidence:

- `/root/wksim-ap-dds-yaw-state-4Wr27s/src/libraries/AP_DDS/AP_DDS_Client.cpp:982`
  receives `SampleIdentity* sample_id`. Arm, mode and takeoff replies at lines
  1018, 1048 and 1077 pass that same identity to `uxr_buffer_reply`.
- `/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/client.py:117`
  maps the returned sequence to a newly created Future; removal at 148–151 uses
  object identity. `executors.py:413` looks up the response sequence and ignores
  an absent pending request. DDS/RMW provides the writer identity boundary across
  newly created clients; these unit tests do not prove restart behavior of the
  live Agent/RMW transport or preservation of its identities.
- Cancellation prevents local completion, not execution of an already delivered
  FC command. Main session revocation must not claim physical command recall.

## State freshness and reset boundary

Both adapters accept only strictly advancing per-topic source stamps. PX4 checks
publication timestamp and, when present/nonzero, sample timestamp; AP uses
`WksimState.time_boot_us` and Status header sec/nanosec. AP source at 838–844
updates the Status stamp for changes and its periodic publication. WksimState
uses `AP_HAL::micros64()`. No boot clock is replaced by wall time.

Duplicates never replace cached content or refresh receive age. Any source or
sample regression is conservatively treated as a clock reset: clear all cached
state, retain watermarks, emit `clock`, and latch invalid for this adapter's
lifetime. Local monotonic-clock rewind/nonfinite time has the same effect.
Subsequent packets cannot resurrect stale state even after clocks catch up.
Recreating the adapter requires a deliberate transport/session reset outside this
sidecar; merely clearing `clock_invalid` is unsupported. A reordered packet can
therefore conservatively stop an operation. Forward-time yaw, position, attitude
and home resets retain their original classifications for the node to revoke or
handle during initial alignment. Duplicate packets cannot change reset tokens.

`state_received_monotonic` returns the accepted PX4 position/AP local sample's
original receive time, even when aged out, or None when absent/invalidated.
Main must use this stamp together with connection/validity, without re-stamping
old samples. Native topics carry no run UUID, so this does not establish the
provenance of the first sample after a brand-new adapter is created.

`consume_rejections()` drains a 128-entry deque of dictionaries containing
reason/source and source stamp, command or request identity when known. PX4 uses
the actual pair; AP cancellation's identity is a process-local Future object ID,
not a DDS identity or a durable token. Overflow drops oldest diagnostics only.
Humble discards canceled service responses before adapter delivery, so they
cannot all be logged here; cancellation itself is recorded. Main invokes this
drain from tick and owns persistent logging.

## Validation and limits

Validation uses repository Python modules first on PYTHONPATH, the already
installed real generated PX4/AP/Prometheus schemas, recording transports and an
isolated `unshare --net` namespace. No installed package is changed. Run:

```bash
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-0viK3f/install/local_setup.bash
export PYTHONPATH="$PWD/ros2/src/prometheus_control:$PWD/validation:$PYTHONPATH"
export PYTHONDONTWRITEBYTECODE=1
unshare --net bash -c 'ip link set lo up; ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=78 python3 -m unittest test_prometheus_native test_prometheus_native_epochs.EpochTests -v'
```

The PowerShell-to-WSL invocation initially lost inherited PYTHONPATH expansion:
two import-only attempts failed with missing ardupilot_msgs/px4_msgs. An explicit
colon-separated path list fixed this. The first successful 16-test run had
loopback down and FastDDS emitted whitelist-interface warnings; this is not live
DDS evidence. After enabling loopback in the private namespace, the final
adapter-only run passed **16 tests in 0.062 s**, exit 0: all eight `EpochTests`
plus the eight original NativeTests excluding the two node integration tests.
This includes actual generated-schema type assertions and serialization of both
range endpoints 200/1 and 254/255. The final full-suite attempt (before the last
schema test was added) passed 15 of 17 tests; the two node imports failed because
concurrent main changes now require `wksim_msgs`, absent from the old installed
overlay. Earlier node successes do not validate that new integration. Main must
run those two tests with its freshly built session schema and updated node tests.
The final selector after the environment setup above was:

```bash
python3 -m unittest test_prometheus_native_epochs.EpochTests \
  test_prometheus_native.NativeTests.test_ap_home_and_reset_epoch \
  test_prometheus_native.NativeTests.test_ap_position_wire_and_explicit_capability \
  test_prometheus_native.NativeTests.test_ap_service_ack_and_timeout \
  test_prometheus_native.NativeTests.test_ap_state_flags_and_wire_roundtrip \
  test_prometheus_native.NativeTests.test_frames_and_quaternion_roundtrip \
  test_prometheus_native.NativeTests.test_px_ground_alignment_and_native_takeoff \
  test_prometheus_native.NativeTests.test_px_native_axes_and_ack_correlation \
  test_prometheus_native.NativeTests.test_px_state_identity_and_epoch -v
```

No SITL/UE flight,
hardware, install, commit, push, or process cleanup was performed. PID 828 was
observed alive as `arducopter`. No structural graph discovery was needed: all
edited sources were known paths and external sources were read directly.
