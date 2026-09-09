# #121 handoff

Branch: codex/independent-rgb-integration. Starting HEAD is retained in
head.stdout.log. This delivery owns only docs/plan/45-gnss-runbook.md and this new
evidence directory. Exclude AGENTS.md, the lunar guide, shared active record and
all other tickets' files from staging.

Last completed step: live dependency inspection, 28 Windows + 28 WSL tests (zero
skip), archived AP ground raw reaudit, six mutation rejections and five current
AP resource identity comparisons. No #121 flight or full runtime preflight ran.
Exact commands and outputs are in this directory; summary.md maps every required
deliverable to the actual completion boundary.

Next action: scope and deliver an AP flight-capable fault-plan candidate plus a
reviewed GNSS-specific validity/failsafe/recovery/physical contract. The existing
ground candidate uses [4000,6000) and max tick 60000. Native source/build changes
are outside #121's named production-file allowance. Then implement the seven
missing runtime/config/audit/test files, complete the runbook commands and pass
both actual read-only preflights before restoring ready-for-agent.

#121 must remain OPEN + needs-triage. Do not auto-retry #111/#112, change physical
budgets, or replace the existing ground evidence with flight labels.

No #121-owned long-running process remains. A #86 PID runner was present in the
read-only process snapshot and is outside this delivery. The general Luna goal
remains active and incomplete.
