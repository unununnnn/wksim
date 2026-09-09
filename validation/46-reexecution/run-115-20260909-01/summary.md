# #115 / 46-reexecution-run independent acceptance

2026-09-09. PASS within the frozen static `quad-mass-cold-post-step-v1`
profile: 25 consecutive 1ms native integration calls, 3,000/3,000 output
comparisons exactly equal (atol=0, rtol=0). Only #115 is eligible for closure.

## Exact commands

From the Windows wksim repository root:

```powershell
wsl -d Ubuntu-22.04 -u root -- /usr/bin/python3 validation/46-reexecution/run-115-20260909-01/review.py
```

Exit 0. This single-use evidence driver independently checks #114 source
provenance, invokes these CLI commands, verifies results, runs refusal cases,
and archives all artifacts. From the WSL repository root the positive commands were:

```bash
/usr/bin/python3 tools/reexecute_model.py import --source /root/wksim-reexecution-114-20260909-03/source --output /root/wksim-reexecution-115-20260909-01/input
/usr/bin/python3 tools/reexecute_model.py run --input /root/wksim-reexecution-115-20260909-01/input --library /root/wksim-reexecution-114-20260909-03/build/libwksim_configured.so --output /root/wksim-reexecution-115-20260909-01/run
/usr/bin/python3 tools/reexecute_model.py audit --input /root/wksim-reexecution-115-20260909-01/input --run /root/wksim-reexecution-115-20260909-01/run --output /root/wksim-reexecution-115-20260909-01/audit.json
```

All three exit 0. Fully expanded argv, exits, stdout and stderr for every
positive/negative command are retained in `native/*.command.json` and logs.
Directories were exclusively created; these commands must use new paths if repeated.

## Independent evidence and identity

Reviewed #113's contract, #114's implementation and capture code, the #24 closure
review and #20 joint-step acceptance boundaries. #114 was CLOSED before execution.
The frozen source manifest SHA256 is
`1ae747154a72ac46435c33cede8642b81224c12c20f0b13f02825750108d314f`;
contract SHA256 is `54c93d120a9745bb9466b2b4279bafa0701b7b3c706f3728574a5797c719fac1`.

`native/preflight.json` records all source/build/library/dependency/platform hashes,
the observed source process exit receipt and frozen budget. All source package
bytes matched the archived #114 delivery, its expected outputs matched the raw
capture, and its plan matched the pre-capture plan. The capture implementation
calls ConfiguredModel.step against the real native library. The new execution
used a different process PID, checked the loaded library mapping and applied
one step per frozen input row. It did not use the replay reader.

`native/audit.json` contains all 120 per-slot metrics: maximum absolute and relative
error zero, zero failures and no first mismatch. `native/independent-comparison.json`
records a second direct row/slot comparison and exact time-grid verification.
`native/run/` preserves request, loaded mappings, actual output, terminal, child
exit, stdout/stderr and the tool's own audit. The engine reached 25,000,000ns.

Nine real-source copies test missing tick, changed input, foreign model, changed
seed, missing initialization, stale event, missing terminal, truncation and phase
mismatch. All exit 2 before child/request creation; copies and exact rejection
reasons are retained. A separate audit-only output mutation with a recomputed
stream hash exits 1 / numerical_failed, exactly one mismatch at tick 10, slot 10.
No extra physical rerun was used for that negative. No tests were skipped.

Source package and build identities were checked unchanged after execution.
`native/review.json` records tool/test/contract/driver hashes and every command;
`archive-hashes.json` indexes all archived native evidence bytes. No vendor source,
ZIP or library is included in this delivery. Runtime originals remain under the
new `/root/wksim-reexecution-115-20260909-01` directory.

## Boundaries and completion

This proves same-build cold recomputation of this complete 25ms static source,
not a flight, arbitrary recording import, lifecycle/event support, cross-platform
accuracy, sustained 1x performance or Full/G6. The old #24 insufficient recording,
R1 numerical_failed and RateUnmet conclusions remain applicable. Parent #46 and
its #16/#20/#24 dependencies require their own acceptance.

All owned child processes returned; no FC, ROS, UE or control publisher was
launched. The inspected execution path only loads the explicit model and invokes
its native integration API; no control destination is accepted by this CLI.
The WSL launcher printed its host localhost-proxy warning; all workload commands
completed successfully and their raw stdout/stderr are retained.

AC1: met for the frozen complete source, same build, unchanged zero budget,
new output directory and no original-run writes. AC2: identity, exact commands,
raw results and failures/boundaries archived. No production source modified.

Model/effort: user-specified `gpt-6-astra / low`; current tool interface does not
expose independent verification of the exact main-session ID/effort. The runtime
identifies the assistant as GPT-6. No subagents were dispatched.
