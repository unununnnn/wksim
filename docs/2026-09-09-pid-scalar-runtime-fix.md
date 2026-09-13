# PID scalar boundary repair and one PX4 run

Branch `codex/independent-rgb-integration`, starting commit `acf8c68`.
This advances #35/#86 but does **not** close either issue or unblock #87.

## Changes and reproduction

The actual ROS `UAVState.position` and `velocity` arrays yield `numpy.float32`.
The PID shared `_finite` validator accepted only Python int/float, rejecting
finite input before the first PID command. It now accepts `numbers.Real` and
normalizes to Python float, retaining boolean/non-real/nonfinite rejection.
No dependency or controller equation changed.

The archived `pid_point_begin` position was
`[1.9719982147216797, 2.9741711616516113, 2.9985885620117188]`.
Reconstructing the real ROS message reproduces the original error against
`acf8c68`; the changed implementation accepts exactly the same values.
The original run and its failed audit were not modified.

Two auditor representation defects surfaced after the successful run:

- Only optional public State `range`, `rel_alt`, `battery_state`, and
  `battery_percetage` nonfinite values are normalized for comparison between
  the explicit evidence marker and raw result encoding. Required nonfinite
  values do not gain equivalence. Neither input is mutated.
- The public envelope is already a float32 ROS message. Its comparison now
  uses the existing documented wire tolerance `1e-6`, matching the adjacent
  decoded-message check. Independent double recomputation remains `1e-10`.

Regression fixtures reproduced both the scalar rejection and float32 envelope
rejection before the respective fixes. New negative checks retain rejection of
nonfinite required state, changed optional values, changed counts, and an
envelope deviation of `2e-6`.

## Actual checks and run

Evidence: `validation/lunar-86-20260909-scalar-fix/`. Each `*.json` command record
contains argv, working directory, timestamps and return code; matching stdout
and stderr remain separate. `run.py`, `replay.py`, and `finish.py` record the
bounded procedure. These use exclusive log creation and do not retry flights.

Final sourced WSL test command:

```bash
/usr/bin/python3 -B -m unittest validation.test_pid_flight validation.test_position_pid validation.test_pid_flight_audit -v
```

**46 tests passed, zero skipped.** Includes an actual generated ROS State
through `PIDTask.offer_pid`; the recording transport is a test fixture.
The separate complete flight provides actual ROS/FC/model evidence.

```bash
bash tools/run-pid-flight.sh --stack px4 --run-id pid-px4-scalar-fix-20260909-01 --config Simulator/wksim_runtime/pid-flight-v1.json --output-root /root/wksim-pid-flight-pid-px4-scalar-fix-20260909-01
```

Preflight and the single flight each exited 0. Run directory:
`/root/wksim-pid-flight-pid-px4-scalar-fix-20260909-01/pid-px4-scalar-fix-20260909-01`.
Result is `observed`; safe_landing, children_reaped, source_unchanged and
candidate_unchanged are true; stop_kind is `landed_stop`; cleanup_errors is empty.
The recorded physics/Agent/FC/control PIDs no longer exist.
Frozen configuration SHA256 remains
`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`.

## Independent audit and remaining blocker

`pid-audit-final.json` retains the **rejected** result, with completed checks:

- 93,624 continuous physics ticks, 23,392 captured actuator packets, 1,000
  applied disturbance ticks.
- Fixed point/circle/disturbance physical gates pass. Maximum position errors
  are respectively 0.0882458 m, 0.0999026 m, and 0.1171971 m.
- Same-run hover calibration 0.5310004949569702 from 121 samples.
- Independent PID recomputation: point 501, circle 1,200, disturbance 850 updates.

First remaining failure: `No distinct native attitude CDR for PID request 10`.
The auditor requires a distinct matching native target after public reception
and within adjacent consumed native State timestamps. Do not relax that window,
accept a public ACK as native consumption, or report this flight as audited PASS.
Next step: inspect request 10 against adjacent State, raw receiver timestamps,
native targets and ULog to distinguish command coalescing, timestamp association,
or missing observation before changing the runtime or contract. No further
flight was attempted in this slice.

Audit execution uses the already installed private pyulog 1.2.2 location
`/root/wksim-attitude-audit-deps-g_2y8olg` plus the admitted ROS overlays.
Earlier audit attempts and their failures are retained: progress encoding,
float32 envelope comparison, then missing pyulog path. The last was an invocation
environment issue resolved by reusing the documented private package, without
installation. The first archived replay invocation also omitted ROS PYTHONPATH;
its failure and the corrected invocation are both retained.

`cleanup-and-hashes.stdout.log` and final audit input hashes bind raw data.
The large original result and raw streams remain in the sealed WSL directory;
the local result copy is not required in Git. Full, R1 and RateUnmet conclusions
are unchanged. No GitHub issue was closed and no successor flight was started.

Codebase Memory status was checked (50,865 nodes / 165,157 edges). Current PID
symbols were absent from the old graph, so known source paths and literal
diagnostics were read directly; no graph completeness claim or post-edit
structural query was made. Parent/sibling workspaces were not changed.

Subagents were not dispatched: the exposed interface could not explicitly
select and read back Fast as required by the project's delegation policy.
