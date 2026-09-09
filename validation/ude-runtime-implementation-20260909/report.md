# #90 UDE runtime implementation evidence

2026-09-09. Status: **offline_checks_pass; native UDE flight unverified**. Main explicitly assigned the four runtime files and approved bounded shared audit parameterization. No commit/push/issue closure was performed.

## Delivered

- Explicit typed PID/UDE selection uses PositionUDE for UDE and rejects NE/unknown/config mismatch without fallback.
- Frozen UDE config is accepted by the existing run-pid-flight.sh / run_pid_flight.py CLI; selected protocol reaches task, source seals, disturbance event and raw physics header.
- UDE report uses external_ude and implementation identity. Trace retains observer nominal/disturbance, integral and reset records while public XYZ_ATT and native outlet remain shared.
- New audit_ude_flight.py owns independent UDE equations. Shared audit accepts a caller-selected profile with unchanged PID defaults; fixed metrics and native/physical semantics are reused.
- docs/plan/36-ude-runtime-contract.md records exact standalone preflight/run/audit commands for each stack, legacy pid_ naming, budgets and failure boundaries.

## Actual offline commands and results

```powershell
python -B validation/ude-runtime-implementation-20260909/check.py --output validation/ude-runtime-implementation-20260909/offline-run-01
git diff --check
```

The check executed the combined PID/UDE/controller/runtime/auditor suite: **71 tests executed, 70 passed, 1 skipped**. The skip requires installed ROS prometheus_msgs and is not counted as installed-runtime proof. Exit code 0. New UDE tests: 12. Both CLI --help checks exited 0. git diff --check passed.

**1,200 raw comparisons** across synthetic AP hover=.32 and PX4 hover=.53 were saved in offline-run-01/equations.jsonl. They cover moving/point references, observer history, force/attitude/projection and both native thrust conventions. Maximum absolute error **0**; frozen double tolerance **1e-10**. These synthetic hover inputs are never run calibration. The unchanged #89 original C++ oracle has separate existing evidence and was not rerun.

Negative checks cover wrong selection/config/protocol, duplicate/invalid/backward/over-limit timestamps, authority loss, old observer state, label-only output, wrong reset, missing/duplicate physics evidence, wrong applied actuator channel, changed event identity, native position override and insufficient result-only evidence. A synthetic public outlet test proves a real PositionUDE output feeds XYZ_ATT with one request pending.

## Identity

Before/after check source hashes were identical. Both frozen configs and position_ude.py remained unchanged. PositionPID computation was untouched; only select_controller changed.

| Path | SHA256 |
| --- | --- |
| `Simulator/wksim_control/position_pid.py` | `45355e6033de2272cc89fedb0736a7c16bd7397fe69dd12fab8425088b5a3140` |
| `Simulator/wksim_control/position_ude.py` | `811f7bab2ae022563035005a76b5475665f15e9f49380ee201a7a64e61c0787b` |
| `Simulator/wksim_runtime/pid_task.py` | `4a04522972cfa0a690ce76433cccad35d581eb43957b57302894347cdaa4a954` |
| `Simulator/wksim_runtime/pid-flight-v1.json` | `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0` |
| `Simulator/wksim_runtime/ude-flight-v1.json` | `4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590` |
| `tools/run_pid_flight.py` | `7975ef997365493b413c9e37c40f304679b233befa14b4a14199f5ae0c945548` |
| `tools/pid_physics.py` | `5c57811dc2b1f86282b409ca59bc3bdd0cfec6a6a2981620d784e500c80dad78` |
| `tools/audit_pid_flight.py` | `f569a5e56447115e60ece07aae3bfa4170dd9f33da90f96c9280e98dedfc370b` |
| `tools/audit_ude_flight.py` | `c6dfe380ce5dd9eee6e2614eac0f1f42a9ec27e2ae2419e2be43bc94e727c9a4` |
| `validation/test_ude_runtime.py` | `d6376687f3792029d279b95d46f2d36f0f3629679f59e10d926f3422ea60cc58` |
| `validation/test_position_pid.py` | `53fb56f578ba4226e33455c5bd2e2f5d9326edb01a160c441ca393297884ce01` |
| `validation/test_position_ude.py` | `892ae085cba3192df66b8d69ec86ed4c950dd12c6202a778c43cd59ff34f1beb` |
| `validation/test_pid_flight.py` | `8a894c70ef6c2a880010b5c7664abcd40324297c1507fe20562102fd4f97d48f` |
| `validation/test_pid_flight_audit.py` | `54424508e433380378aaccc02990178034c1eab16cbe4a846da100a4409a58b1` |
| `docs/plan/36-ude-runtime-contract.md` | `2d7c11bdc8b54389932fd66d5428b58f2289adb59ac69ea242599b374f18f27f` |
| `validation/ude-runtime-implementation-20260909/check.py` | `12902c89246878784772b06060767036afd6eee6a117b1747c0cdd6fb9990a5a` |

## Ownership and remaining scope

Runtime writes: Simulator/wksim_control/position_pid.py selector only; Simulator/wksim_runtime/pid_task.py; tools/run_pid_flight.py; tools/pid_physics.py. Additional explicitly reviewed verification writes: tools/audit_pid_flight.py bounded profile routing, new tools/audit_ude_flight.py, new validation/test_ude_runtime.py, docs/plan/36-ude-runtime-contract.md, and this fresh validation directory. No other production file changed by this agent.

pid_task.py was frozen at 4a04522972cfa0a690ce76433cccad35d581eb43957b57302894347cdaa4a954 for the parent rate diagnostic and remained unchanged throughout this evidence run.

No FC/ROS node/UE/native model process ran, and no real installed-stack preflight was performed. Actual source-sealed PX4/AP UDE flights, fresh per-run native hover calibration, point/circle/disturbance physics acceptance, raw native log association and safe cleanup still require scheduled #91/#92 runs. The current auditor has no real UDE run to certify. The historical frozen config scope still says blocked, retained to preserve exact bytes; the contract explains this historical text.

No physical/timing budgets were tuned. No Full/UI/joint rate/NE/motor-efficiency claim. The code is reviewable and runnable subject to actual preflight; offline pass alone is not #36 acceptance. Main retains #90 disposition.

Raw stdout/stderr, commands, per-sample expected/actual values, result/source manifest and artifact hashes are under offline-run-01/. This validation directory is covered by repository ignore rules and needs explicit force-add if the parent elects to commit evidence.
