# #90 / 36-runtime — blocked candidate contract

Inspected #90 and #35 live: #90 permits only the new UDE JSON and contract;
#35 is OPEN and is an explicit prerequisite. #89 evidence/source is available.
The current PID loader, loop/task, runner and physics observer hard-code PID.
No default or fallback was introduced. No runtime source was edited.

Delivered `Simulator/wksim_runtime/ude-flight-v1.json` and
`docs/plan/36-ude-runtime-contract.md`: candidate UDE parameters, unchanged PID
physical budgets, model/calibration/timing/reset/dual-stack requirements,
four precise proposed runtime file edits, conditional separate stack commands
and independent UDE/native/1ms audit plan. These are not runnable integration.

Command: `python -B validation/lunar-90-astra-20260909-01/check.py` from project root.
Windows result: exit0; 38 tests passed, zero skipped. Additional assertions prove
real pure UDE calculation, reset, both synthetic mappings, equal physical budget
fields and rejection by the actual current loader. Raw output and all relevant
source/config SHA256 identities are in `check.log`; check.py is reproducible.
No new flight/preflight/oracle run was performed; no FC/model/ROS/UE processes
were launched or left running. #89 oracle numbers are historical input evidence.

Candidate SHA256: `4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590`.
Existing PID protocol remains `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`.
Initial HEAD `0df80d8`, branch `codex/independent-rgb-integration`.
All changes are the two allowed files and this new evidence directory.

Acceptance: actual pure UDE yes; integrated selection/run/audit no. #90 remains
OPEN / needs-triage. Required next action: resolve #35 and explicitly assign the
four runtime source files listed in the contract plus test/audit ownership.
Do not unblock #91/#92 or close #36 on this configuration-only result.

Actual model settings verified from latest local rollout turn_context for this
thread `01a08576-5bf2-7132-9527-63ad32dc2a1c`: model=gpt-6-astra, effort=low.
No subagents used. No flight, performance or Full success claim.
