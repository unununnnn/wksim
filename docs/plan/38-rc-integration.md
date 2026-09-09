# #99 RC integration status — bounded shared seam

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
