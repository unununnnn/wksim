# ds-manager99 candidate — manager-only scheduling change

`validation/coordination/ds-manager99-candidate-20260913-01`. A minimal,
reversible candidate that raises **only the manager's own FIFO priority** from 50 to
99, prepared from the frozen runner snapshot. It is a file: it is **not** applied to
any runtime, staging copy, or process, and no native, scheduling or model operation
was performed.

## Why this candidate

A real run recorded 11 processes before and after, with the manager main thread at
FIFO 50, PX4 `hpwork` at 98, several work-queue/hrtimer/sim threads at 99, and
commander at 90. That observation is **not a causal proof** and is not treated as
one. It does motivate one controlled comparison in which only the manager's own
priority changes.

## Frozen base

| item | value |
| --- | --- |
| snapshot | `validation/coordination/claude-owned-snapshot-wiring-20260913-01/run_joint_flight-owned-snapshot-candidate-v3.py.txt` |
| snapshot sha256 | `1c600d7f018376f5c6fe333f0fd5da75798834c5f09e843078b0939142774373` (98 262 B, 1 560 lines) |
| candidate sha256 | `9b97c124cc75c582aabaf72db2051f96f2b4777855f39645f5a75fb2d2d1e839` (98 579 B) |
| diff sha256 | `668475ec8d68e884253537e5ca7190448bbe82945c59b37ce44a32e5c15b5c7a` |

## The change — exact and reversible

In `scheduling()`, two snapshot lines are edited and four comment lines are added.
`candidate.diff` (unified, 6 lines of context) is the authoritative record:

```
-        value['target_fifo_priority'] = 50 if role=='manager' else 40
+        # Manager-only change under test: raise the manager target to FIFO/99, ...
+        value['target_fifo_priority'] = 99 if role=='manager' else 40
...
-        # and inherit FIFO/50.  The model leader is then explicitly promoted to
+        # and inherit FIFO/99.  The model leader is then explicitly promoted to
```

The second edit only keeps the pre-existing comment truthful about the level the
children would otherwise inherit. Reversal is a byte-exact restore of the snapshot
(verified: re-applying the inverse of the diff reproduces sha `1c600d7f…`).

## Preserved verbatim

Model and FC settings, `target_nice` (`-10` for manager/model/fc, `-5` otherwise),
`reset_on_fork = role in ('manager','model') and async_model_evidence`,
`SCHED_FIFO` + `SCHED_RESET_ON_FORK` policy composition, both error handlers, and
every other line of the runner — including all clock, 1 ms, four-tick, no-catch-up,
100 ms, command and physical gates. No new flag, option or framework was added.

## Verification — fake `os` call ledger

`verify_candidate.py` extracts the real `scheduling()` from both files by AST and
runs it against a recording fake `os` that performs **no** system call.

| role | target (snapshot → candidate) | os call ledger |
| --- | --- | --- |
| `manager` | **50 → 99** | differs only in the priority argument |
| `model` | 40 → 40 | identical |
| `fc` | 40 → 40 | identical |
| `task` / `agent` / `service` | no FIFO target | identical |

The recorded manager differences are exactly four, all priority arguments:

| flag | call | snapshot | candidate |
| --- | --- | --- | --- |
| `False` | `sched_param` | `[50]` | `[99]` |
| `False` | `sched_setscheduler` | `[0, 1, 50]` | `[0, 1, 99]` |
| `True` | `sched_param` | `[50]` | `[99]` |
| `True` | `sched_setscheduler` | `[0, 1073741825, 50]` | `[0, 1073741825, 99]` |

Failure behaviour is unchanged: injecting `OSError` into `setpriority`,
`sched_setscheduler`, `sched_getscheduler` and `sched_getparam` produces the same
outcome keys and the same error keys in both files.

Status `candidate_verified_as_manager_only`, 0 findings.

## Not claimed

- No performance, latency, jitter or acceptance claim. This validates **code and
  call paths only**; the observed 11-process priorities are not causal evidence.
- No native, scheduling, model, ROS, MATLAB or build operation was performed.
- Planned next step only: the same diagnostic configuration compared against this
  candidate; a probe-free formal run would be considered only if there is a measured
  benefit, and that decision is not made here.

## Reproduce

```
python build_candidate.py
python verify_candidate.py --out evidence/candidate-verification.json
```
