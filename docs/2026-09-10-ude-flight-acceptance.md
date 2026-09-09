# UDE dual-stack flight acceptance

Implementation commit: `d64010f` on `codex/independent-rgb-integration`.
The existing PID task entry selects actual PositionUDE from the exact frozen
`ude-flight-v1.json`, SHA256
`4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590`.
No gains, physical thresholds, timing budgets or model identities were changed.

## Preserved attempts

PX4 `ude-px4-acceptance-20260909-01` failed before controller updates because
integer configuration coordinates reached generated ROS float-only fields.
The message boundary now validates finite real numbers before conversion to
float. Actual ROS regression reproduced the failure; 48 targeted tests and an
independent boundary review passed. The independent review also verified 21
invalid inputs and unchanged default PID message bytes. Failed evidence remains
in `validation/ude-runtime-acceptance-20260909/px4-attempt-01/`.

PX4 `ude-px4-acceptance-20260909-02` completed all flight stages, landed and
disarmed, with all children reaped and no cleanup errors. Its original strict
audit rejected `Native trajectory override`. The report remains unchanged as
`validation/ude-runtime-acceptance-20260909/px4-02-strict-audit-report.json`.
That report already verified 92,840 physical ticks, the exact 1,000-tick
disturbance, and 851 independent UDE equation updates. Its physical results were:

| Window | Maximum position error | Frozen limit |
| --- | ---: | ---: |
| Point | 0.068449 m | 0.30 m |
| Circle | 0.125528 m | 0.35 m |
| Disturbance | 0.115242 m | 0.50 m |

The original rejection remains preserved. A new complete audit passed after
the stage-boundary attribution fix:
`px4-02-boundary-strict-audit-report.json`, SHA256
`e3e10485029c225b432ccc89f5eaef05c719fc5efffd2c7f14ad3b9f01857486`.
All 851 native request associations passed. The sole boundary trajectory has
source stamp 37.78 s, exactly the physical end, but was published and received
after the stage ended. The auditor requires the later recorded recovery request
177 / command 174, raw acknowledgement, matching NED target, and position-only
axis declaration. Interior timestamps or missing evidence still reject.
The native stamp comes from the latest position sample; physical cursor samples
are discrete. Neither establishes an exact native acceptance time.

AP is now scheduled with the same frozen configuration; its acceptance and #36
remain pending.
Full, hardware, joint real-time rate, NE and motor-efficiency acceptance are
outside the evidence established here.

## Reproduction and evidence

The acceptance directory retains `flight.py` and `audit.py`, exact command
records, separate stdout/stderr, copied result/progress records, and original
strict reports. Native logs and dense physical records remain in each fresh
`/root/wksim-pid-flight-<run-id>/<run-id>` directory in Ubuntu-22.04.
Audit reports bind their original input hashes; never replace a prior report
with a corrected verdict. See `docs/plan/36-ude-runtime-contract.md` for exact
installed overlays and command prerequisites.
