# #59 review evidence

2026-09-09; base commit 0cba2da; branch codex/independent-rgb-integration.

Result: blocked_budget_and_same_source_entry. Route and implementation seams delivered; new numerical budget and executable same-source comparison are missing. Keep #59 OPEN / needs-triage. G6/Full unverified, R1 numerical_failed unchanged.

Read GitHub #59 and #10 with `gh issue view 59 --repo unununnnn/wksim --json title,body,state,labels,comments` and `gh issue view 10 --repo unununnnn/wksim --json body,comments`. Read #70 using `gh issue view 70 --repo unununnnn/wksim --json state,labels`: OPEN / needs-triage. Source inputs and original result fields are in inspection.json. It contains copied metadata, not newly simulated measurements.

Actual commands from project root:

```powershell
python validation/test_numerical_conformance.py
Get-FileHash Simulator/wksim_core/numerical-conformance-v1.json
$inspection = Get-Content validation/10-g6-remediation/review-20260909/inspection.json -Raw | ConvertFrom-Json
foreach ($item in $inspection.hashes) {
    if ((Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash.ToLower() -ne $item.sha256) { throw ('Hash changed: ' + $item.path) }
}
if (($inspection.results | Measure-Object -Property failed_values -Sum).Sum -ne 5684) {throw 'Failure total changed'}
git diff --check
```

Raw comparator stdout (exit 0):

```text
PASS: exact equality, signed zero, one-ULP and integer-token failure, complete scalar/failure retention, nonfinite/boolean/missing/input/clock rejection
```

Identity/result check stdout (exit 0):

```text
PASS: 15 identities unchanged; 5684 original failures retained
```

R1 hash: 23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0. No new vehicle, MATLAB, FC, ROS or UE run; no newly claimed physical pass. No vendor bytes published. Working-tree changes to AGENTS.md and the Luna guide excluded.

Actual model verified by reading only turn_context fields of the local session file named for CODEX_THREAD_ID 01a085ae-8e74-7431-aa16-113eac9436f4: model=gpt-6-astra, effort=low. No subagents.
