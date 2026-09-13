# #99 RC integration status — bounded shared seam

2026-09-10 latest follow-up: the flight runner, actual Humble CDR/GID receiver,
and independent raw auditor are implemented. Six scenarios on each of PX4 and
ArduCopter passed on the installed WjBuqN control candidate. See
[the flight report](../2026-09-10-rc-flight-report.md) and
`validation/38-rc-flight/final-matrix.json`. Earlier checkpoints below remain
historical records. Formal default promotion, other RC modes and Full are separate.

2026-09-10. #98 is complete; #12, #14 and #6 are closed. This slice adds only
the smallest shared handoff needed before touching the ROS node: the existing
`CommandProcessor` accepts a validated `Desired('position', ...)` from the
pure `Simulator.wksim_control.rc_input.RCInput` module through
`set_rc_desired()` and clears it through `clear_rc_desired()`. RC output is
still returned only while the processor is in `RC_POS_CONTROL`; disarm clears
the target and returns the processor to INIT. Invalid kind, shape, nonfinite
values and wrong control state are rejected without mutation.

The source change is `ros2/src/prometheus_control/prometheus_control/command.py`
and its regression is `validation/test_rc_control.py`. The current installed
Control node remains unchanged: it still rejects non-COMMAND_CONTROL setup and
has no RC String subscription, MessageInfo publisher-GID binding, explicit
RC setup/activation, pause/reset stream revocation, or native RC handoff.
Therefore this is a shared seam check, not RC product acceptance.

Verification used the current repository source explicitly under the admitted
ROS overlays:

```text
10/10 validation.test_rc_control + validation.test_rc_input passed, 0 skipped
38/38 local trajectory/RC/global/joint regression tests passed (2 ROS tests skipped)
```

The remaining #99 work must reserve the node callback/setup/drive/revoke files,
build a fresh installed Control candidate, add a software-RC publisher and
independent evidence recorder, then run separate PX4/AP movement, recenter,
yaw, stream-stall, mode-out and new-takeover cases. No native command or real
RC flight was started by this slice, no RC budget was changed, and #99/#38
remain open.

# #99 node wiring status — 2026-09-10

The installed Control node now implements the RC_POS_CONTROL handoff:
`ros2/src/prometheus_control/prometheus_control/node.py` accepts
`SET_CONTROL_MODE` with `RC_POS_CONTROL` (same armed/valid/position-yaw
preconditions), binds a neutral software-RC stream through
`Simulator/wksim_control/rc_input.RCInput` with publisher-GID ownership,
activates only after an explicit setup, integrates stick frames in public
ENU per the documented actual mapping (x += ch[1]*1.5, y -= ch[0]*1.5,
z += ch[2]*1.3, yaw -= ch[3]*1.5 with 0.05 deadzone and 0.2 m z floor),
revokes on stream stall, foreign epoch/stream, switch intent, scene pause
or external mode loss, and never replays a revoked stream. `rc_boot_id`
(32-hex) configures the expected identity; without it the RC path is
disabled and setup rejects `rc_input_not_configured`.

Fresh installed Control candidate built:
`/root/wksim-rc-control-rc99` (colcon, packages-select prometheus_control);
source node.py SHA256 `04ac8a0b2e431e8ec44954b8e46cf3d320f8e48b31874e20099f7924f8d9922e`.
Regression: `validation.test_rc_control` + `validation.test_rc_input`
10/10 OK under the admitted overlays with the repository source first on
PYTHONPATH (`work/run-rc-tests.sh`), 0 skipped.

Remaining for #99: software-RC publisher with recorded profiles, the
scenario task runner, and the separate PX4/AP one-run verifications
(movement/recenter/yaw/stream-stall/mode-out/new-takeover) with
independent audits. No RC flight has been started; #99/#38 remain open.

# #99 publisher/task status — 2026-09-10 (second checkpoint)

- `Simulator/wksim_runtime/rc_task.py` (new): `RCTask` scenario driver on the
  session_v1 Task harness. The task node itself owns the software-RC
  publisher (in-process GID/epoch binding), keeps the neutral stream alive
  through arming, native takeoff and activation (`send_with_rc`), and
  implements six scenarios: movement, recenter, yaw, stream-stall,
  mode-out, new-takeover, each ending in a public AUTO.LAND + disarm.
- `tools/rc_publisher.py` (new): standalone profile-driven software-RC
  publisher (raw frame log), for negative/third-party publisher probes.
- Compiles clean under Windows and WSL `py_compile`.
- Not yet delivered: the flight runner (`run_rc_flight.py`), the
  independent audit and the six PX4/AP one-run verifications. No RC
  flight has been started; #99/#38 remain open.
