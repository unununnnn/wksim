# #55 executed commands and boundaries

All project shell commands use cwd C:/Users/PC/Documents/odid编译/wksim (initial AGENTS read used parent cwd).

## Input/read-only evidence

- Get-Content -Raw AGENTS.md; Get-Content -Raw CONTEXT.md
- Get-Content -Raw lunar模型完整推进指南.md
- Get-Content -Raw docs/plan/full-remaining-ledger.json
- Get-Content -Raw docs/plan/full-remaining-ledger.md
- Get-Content -Raw docs/plan/full-scope-expansion.md
- Get-Content -Raw docs/plan/requirement-coverage.md
- Get-Content -Raw docs/plan/full-migration-spec.md
- Get-Content -Raw docs/plan/goal-objective.md
- Get-Content -Raw docs/plan/published-issues.json
- gh issue list --repo unununnnn/wksim --state all --limit 300 --json number,title,state,url,labels
- gh issue view N --repo unununnnn/wksim --json number,title,body,state,comments,url (N=1..48 except absent49; retained parent-evidence.json records actual returned set)
- gh issue view 54 --repo unununnnn/wksim --json number,title,state,closedAt,body,comments
- gh api repos/unununnnn/wksim/issues/55/dependencies/blocked_by --jq '.[] | {number,state}' → #54 closed
- Get-Content -Raw validation/first-phase-acceptance-20260909/matrix-audit.json
- Get-Content -Raw validation/quad-parameters-main-review-20260909/review.json
- Get-Content -Raw validation/numerical-conformance-audit-g44e4j8r/summary.json

## Runtime model verification

- Get-ChildItem Env:CODEX* | Where-Object Name -Match 'THREAD|MODEL|REASON'
- rg --files C:/Users/PC/.codex/sessions | rg '01a0853a-46bd-7f03-9f8e-b51ed4e33b7d'
- Parse turn_context records in the matching rollout using Get-Content / ConvertFrom-Json and Select-Object model,effort,reasoning_effort,turn_id.
- Actual matching turn_id 01a0853a-4768-7d41-bc85-cd17d2bbf708: gpt-6-astra / low. Earlier Luna turn records are not this turn. No delegation.

## Publishing

Exact gh commands, outputs and return codes: create-log.json. Remote exact-body readback commands: readback-commands.json, results: issued-readback.json. #135 scope refined before final readback to parameter product entry; existing #59 numerical route reused. No pre-existing issue modified except requested #55.

## Audit

python -X utf8 -B validation/lunar-55-astra-20260909-01/audit.py

Exit 0, 96 rows; 43 actual remote issue bodies match; 8 negative mutations rejected. audit-result.json includes source/report SHA256. This does not rerun historical physical audits.

## Failures / concurrency

- rg -n 'blocked_by|sub_issues|issue_id' tools/lunar* failed on PowerShell wildcard path (os error123); no source discovery claim based on it.
- Large combined reads/list including all issue bodies exceeded tool output limits; individual parent issue reads and bounded artifact reads replaced them. Snapshots are valid parsed JSON.
- An in-memory structuredClone call was unavailable; no files changed; JSON cloning used instead.
- A patch using delete/add for the same path was rejected; corrected as a single update; no partial change relied upon.
- Whole-worktree git diff --check reported CRLF trailing whitespace in concurrently modified validation/lunar-active.json. This agent never edited it. Scoped diff check on #55 files passes.
- Concurrent task advanced HEAD from 030c316a to 1d897c4 and added PID audit files. They are excluded from this commit; #55 input hashes remain independently verified.

No FC, model, ROS, UE or MATLAB run was started. No historical failure/threshold edited.
