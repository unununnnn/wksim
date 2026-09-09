# #86 corrected command, frozen before execution

Prior attempt `pid-px4-luna-01` failed before any flight child was launched: output
`/root/wksim-pid-px4-luna-01` did not satisfy the runner's required prefix.
The current runner, guide section 6.1, and `docs/2026-09-09-pid-flight-plan.md`
all require `/root/wksim-pid-flight-*`. The ticket explicitly directs replacing
example run IDs/output directories and checking current source.

The main agent resolves this command-only triage within the continuing project
authorization. No new physics, numerical protocol, ABI, or resource is selected.
GitHub native dependencies #50 and #85 were read back CLOSED on 2026-09-09.
Old attempt evidence remains at `validation/lunar-86-5321a4b394e94d4fb20e232d70e1e915/`.

New run: `pid-px4-20260909-02-7e3ce147`.

```bash
bash tools/run-pid-flight.sh --stack px4 --run-id pid-px4-20260909-02-7e3ce147 --config Simulator/wksim_runtime/pid-flight-v1.json --output-root /root/wksim-pid-flight-pid-px4-20260909-02-7e3ce147
```

First run the identical command with `--preflight`; require `ok=true` and frozen
PID configuration SHA256 `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`.
Then execute at most one flight and invoke the existing independent auditor,
retaining rejection as rejection. Inspect exact owned process identities after
completion. Do not enter #87 before #86 acceptance.

This invocation's main model ID/effort is not independently exposed. No subagent
was dispatched because the interface cannot verify the required routing settings.
