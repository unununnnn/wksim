# Route-B public command consumer

`Simulator/wksim_runtime/planner_transport_node.py` connects the TCP receiver
and pump to public ROS2 `CommandRequest` assembly. The pump and egress use the
same adapter/session and command allocator. `trajectory_bridge.py` shares the
field mapping, state checks, authority-tick conversion and ACK classification.

The node enforces the existing 2-second state budget, 1ms authority grid, exact
10-tick output schedule, one pending request, both high-water limits and
fail-closed ACK/transport behavior. It closes owned sockets on fault and node
destruction. One transport token binds one control epoch: an epoch change
faults the node instead of resetting the same wire sequence ledger. Restart
requires an explicitly fresh transport token; the node does not invent one.

Validation in an isolated Ubuntu network/IPC/mount namespace used Humble and
the current `/root/wksim-ros2-Rzj3Pf` message overlay: 67 tests passed, one
platform/precondition test was skipped. The new tests use generated ROS2
messages and a real TCP loopback socket, then record `CommandRequest` at the
publish boundary. They do not establish DDS delivery to a real ControlNode,
ROS1 planner transport, a shared scene clock, or flight behavior.

The separately enabled `PrivateTrajectoryBridgeRMWTests` also passed (1 test):
actual DDS publication/subscription, authoritative test clock updates, synthetic
peer ACKs, high-water handling and epoch reset on the existing trajectory bridge.
Its required domain 79 and recorded original `/dev/shm` device were honored;
earlier invocations without those exact isolation prerequisites were rejected.
This validates the shared ROS message assembly through RMW, not a real FC ACK
or a live ROS1-to-TCP-to-ControlNode mission.

The run caught and fixed a stale local `command` reference left in the bridge
after extracting message assembly. The test for unexpected callback exceptions
now injects at the extracted dependency actually called. It also caught the
need to close custom sockets and avoid token reuse across control epochs.
An earlier attempt selected an old message overlay without `command_high_water`;
that environment failure was corrected by selecting the current overlay.
The ambient ROS `launch_testing` pytest plugin is incompatible with the local
pytest; these standalone suites use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

Remaining Full work: actual ROS1 state/odom and shared-clock transport, the EGO
Bool output gate plus explicit cancel/no-route behavior, live planner inputs,
public control delivery, and physical arrival/collision/clearance checks. The
Bspline wire envelope carries no planner generation; that identity is supplied
locally by the receiver's caller. A control-event extension must advance the
pump's event allocator together with the shared session, preserving replan
ordering. Natural trajectory expiry is not evidence of explicit cancellation.

The pump now owns explicit `hold(..., current_tick=..., anchor=...)` and
`cancel(..., current_tick=...)` events as well as activation events. A successful
control event advances the same allocator and tick ledger; rejected identity,
tick, anchor or capacity checks do not change the session, decoder or allocator.
`TrajectorySession.stop` validates its event and prepares the anchor before
committing state, fixing the previous rejected-anchor sequence consumption.
The four focused session/pump/adapter/egress suites pass 142 checks. The TCP
control carrier and physical cancellation behavior remain unverified; v1
Bspline bytes and terminal output semantics are unchanged.

The official ROS1 bridge now builds with the bool-vector fix and a separate
mapping package for the frozen `Class`/`trackIds` renames. A real isolated
ROS2-to-ROS1 fixture forwarded Clock, Odometry, UAVControlState and nested
detection messages at three timestamps; ROS1 simulated time stayed frozen
during wall-time pauses. Evidence: `validation/ros1-bridge-runtime-20260912/`.
The fixture does not connect a real FC or planner; shared scene namespace,
actual state sources and end-to-end flight remain outstanding.
