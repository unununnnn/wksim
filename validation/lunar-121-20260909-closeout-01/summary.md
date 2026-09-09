# #121 / 45-runtime-auditor — scoped readiness closeout

2026-09-09. **Keep OPEN / needs-triage.** The full dual-stack runtime and flight
auditor acceptance is not met. Native prerequisite issues #109/#110 are CLOSED;
their delivered sensor seams pass their existing checks, but the GNSS flight
contract and AP flight-capable scheduling/admission prerequisite are incomplete.

## What changed

Only `docs/plan/45-gnss-runbook.md` and this new evidence directory are delivered.
The handoff guide section 5 explicitly permits new `validation/lunar-<issue>-<ID>/`
evidence in addition to a child's named files. No production source, AP candidate,
firmware generator, old evidence, numerical budget, AGENTS.md or guide was changed
for #121. The pre-existing shared active-file edit and #86 work are excluded.

The runbook records actual resources, evidence boundaries, executable read-only
commands, all missing deliverables, and the concrete next implementation inputs.
It explicitly does not claim an executable flight/preflight/audit entry exists.

## Verified results

- Windows and WSL: **28 tests passed each, zero skipped**, covering existing GNSS
  decision logic, real MAVLink encoding/socket send boundaries and protocol
  regressions. These are not new GNSS flight integration tests.
- The existing #109 raw auditor was rerun against unchanged archived ground
  inputs: **8000 continuous JSON ticks, 40 samples, 259 UBX packets including
  suppressed candidates**. Actual writes before/after: 6816/4686 bytes; 4260
  candidate bytes suppressed during `[4000,6000)`, actual writes there zero.
- Six mutations of temporary copies were rejected: missing terminal, foreign
  epoch, missing tick, missing GPS write group, writes during outage, corrupt UBX.
  Original input hashes were retained. This reuses #109's ground auditor; it does
  not implement or pass #121's required independent whole-flight auditor.
- Read-only hashes of the current WSL AP binary and four candidate source files
  match the archived build identity (5/5). See `resource-comparison.json`.
- Seven required runtime/config/audit/test paths are absent. Only the allowed
  runbook now exists; `deliverable-inventory.json` records exact paths and hashes.

## Concrete blockers

1. The AP candidate header fixes `start=4000,end=6000`; tick begins at 1 and
   `receive` rejects values beyond 60000. It has no post-readiness flight fault
   plan interface. Its passing probe uses fixed stationary truth and DDS_ENABLE=0.
   This does not prove that an in-flight GNSS invalidity/recovery sequence can be
   performed. Changing the native header/build generator is outside #121's eight
   named production paths and requires a separately scoped new candidate.
2. #22's approved acceptance explicitly covers the Agent link only. Its no-replay
   and explicit-new-takeover principles remain applicable; its evidence does not
   approve GNSS-specific failsafe actions, validity-loss/recovery observation
   windows or a GNSS physical envelope. #121 expressly requires a concrete
   contract before inventing new policy/budget values. The reviewed inputs do
   not provide that contract.
3. The task, frozen config, two runner files, full raw auditor and two integration
   test files remain unimplemented. No fabricated --help/preflight output or
   synthetic flight PASS is provided. #111/#112 remain blocked by #121.

## Exact commands and identities

Working directory: `C:/Users/PC/Documents/odid编译/wksim`.
Starting branch: `codex/independent-rgb-integration`; HEAD:
`1b3670b` (full hash in `head.stdout.log`).

```powershell
python -B validation/lunar-121-20260909-closeout-01/collect.py
python -B -m unittest validation.test_gnss_event validation.test_gnss_px4_injection validation.test_wksim_core.ProtocolTests -v
wsl -d Ubuntu-22.04 -u root -- /usr/bin/python3 -B -m unittest validation.test_gnss_event validation.test_gnss_px4_injection validation.test_wksim_core.ProtocolTests -v
```

The two test lines are the exact nested commands run by collect.py, not additional
test runs to add to totals. All gh/read-only hash/mutation commands retain their
actual argv, cwd, start/end UTC, return code, and raw stdout/stderr in separate
`*.command.json` and log files. Every nested command exited 0. Collection finished
with `readiness.json` status `blocked`, runtime_preflight_passed=false and
full_flight_audit_passed=false; exit 0 from evidence collection is not readiness.

AP binary SHA256:
`48062a2cc8f73c502174561c544730e9adc736b77819a513c48f40eab0c94478`.
AP header SHA256:
`67a70a07f379e096670355e551ca7d79539be10593177b1462b74b21576d53a9`.
Ground input source: `validation/45-ap-gnss-candidate/wksim-ap-gnss-109-ground-05/`.
All read input/source/config hashes: `input-sha256.json`; collected artifact
hashes: `artifact-sha256.json` (created before this final summary and handoff).

Readiness SHA256: `665ff09e06be33bc682120d15987d3ea5fa3a67b0d985c27e6699ae06556aae7`.
Ground reaudit SHA256: `040cce19297c64238004072e7b94ce914757afde7cc45681e5209dc15d4bf146`.
Mutation results SHA256: `dc27a18e1dd85f5fb1bb90107755248fd452cae395e1372f9a0ee6145d3b82e0`.

## Cleanup and acceptance

No FC, model, ROS node, UE or real flight was started for #121. Offline test
processes exited, socket fixtures closed, mutation copies were automatically
removed from their dedicated temporary directory. The process snapshot includes
a concurrent #86 PID runner; it is outside this ticket and was not terminated or
counted as #121 evidence. No blanket host cleanup was performed.

This is a scoped documentation/evidence delivery. Both #121 acceptance items
remain incomplete at full ticket scope. Keep #121 OPEN / needs-triage; do not
close the parent, change dependencies, or enter the successor flight tickets.
R1, RateUnmet and Full conclusions are unchanged. Main model/effort is not
independently exposed by this interface; no subagents were dispatched.
