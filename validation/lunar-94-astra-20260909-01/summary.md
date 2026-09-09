# #94 / 37-runtime — scope blocker, not completion

2026-09-09. Starting HEAD `0df80d8`, branch `codex/independent-rgb-integration`, initially clean. Read #94/#37/#35, #93 evidence and implementation, PID source/runtime reports and exact runtime source. #35 is OPEN. No subagents used.

Delivered `docs/plan/37-ne-runtime-contract.md` and this new evidence directory only. The contract identifies four exact required runtime edits, unchanged physical budgets, proposed NE parameters, calibration, reset/freshness/dual-stack obligations and independent audit requirements. No flight command or frozen runnable NE config exists yet. The two-file source allowlist does not permit the four required integrations or their tests. Needs main-agent ownership assignment before implementation.

Commands run from repository root:

```
python -B -m unittest validation.test_position_ne validation.test_pid_flight -q
python -B validation/lunar-94-astra-20260909-01/check_boundaries.py
git diff --check
```

Unit command exit 0; raw output:

```
----------------------------------------------------------------------
Ran 26 tests in 0.575s

OK
```

Zero skipped. Boundary reproduction exit 0, exact rejection: `unsupported external position controller: 'ne'`. Existing PID config loads successfully. Diff check exit 0. No FC/model/ROS/UE processes launched; no process cleanup required.

Read-back source SHA256:

| Path | SHA256 |
| --- | --- |
| Simulator/wksim_control/position_ne.py | 561761a8f70edff1dc6b68aa40c09f50f1f6b50469a94b2590d9d26ed011cac2 |
| Simulator/wksim_control/position_pid.py | e73848341c9ab226b7166c9f8572371b09979b1ca9211b3dbdd5e6a72490dc7e |
| Simulator/wksim_runtime/pid_task.py | f00c20d3a40588e39cf9e08f373134c04d80e3ed7e64b7f4f667ab796b1f5a81 |
| Simulator/wksim_runtime/pid-flight-v1.json | 25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0 |
| tools/run_pid_flight.py | 695e59e92700045e4d7ce297f9b11127939bf833855195edac27dc961d4c430f |
| tools/pid_physics.py | 2e540fed821c07df63e83252d8288d03599da613e2386cadd0e5dd04abcb0775 |
| tools/audit_pid_flight.py | 1fb12c0d3e6b9d8fafe459e7ff111159bddac48ae4cee3ebb269036e4939ef3d |
| validation/lunar-93-ne-20260909-02/result.json | 3503fdc6e61845280385c7467ce0a6bd7332ac2ccb4df4e9c17e8bdbc62d0ef5 |

Actual current thread `01a08576-5cdb-7fc1-999b-6ec9dca515a1` latest local rollout turn_context read back `model=gpt-6-astra`, `effort=low`. No inference from requested model was used.

AC1 (actual NE bounded runtime) is NOT MET. AC2 has source/check/failure evidence but lacks runnable stack commands and runtime results. Keep #94 OPEN / needs-triage. #95/#96 are not released. No flight, rate, physical or Full acceptance claimed. Scope blocker originates in #94's explicit allowlist, not a skill approval rule.
