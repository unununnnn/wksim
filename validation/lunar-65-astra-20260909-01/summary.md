# #65 — Hex raw independent audit

2026-09-09. Stable key `25-raw-auditor`, prerequisite #52 CLOSED. Only the two
ticket-owned source files and this new evidence directory were changed. The
common evidence-directory allowance is in lunar模型完整推进指南.md §5. No flight,
FC, model library load, ROS node, UE, parameter write or default-manifest change.

## Result and acceptance scope

The final independent audit of `/root/wksim-hex-flight-px4-03/hex-px4-03` exits **0**,
`passed=true`, zero errors. Original result.json remains `observed` unchanged.
The auditor recomputes its verdict from retained sources, raw bytes and physical
values, rather than accepting the runner's status as sufficient evidence.

- Full stream: 38,644 records, 30,924 consecutive 1 ms steps, 7,731 groups,
  7,717 actuator packets; initial 56 zero-input steps with no held packet allowed.
- 77 native parameters independently decoded from original MAVLink payloads with
  pinned XML types and INT32 byte encoding; six-channel plan/config/model pins checked.
- 3,753 CDR records and 11,519 MAVLink messages independently decoded; all six
  public setup/command requests and completion/acceptance events corroborated.
- 140 waypoint DDS targets; 23 same-timestamp target matches in native ULog;
  309 ULog actuator-output groups matched against six physical wire inputs.
- Fixed closed windows: hold ticks 13,200–18,220 (5,021 samples), waypoint
  20,740–22,760 (2,021), landing through terminal 30,500–30,924 (425), parameter
  ground window (781). Zero physical violations. No best-window selection,
  interpolation, threshold increase or phase shift.
- Five owned process lifetimes (including supervisor) checked against current
  Linux boot ID/PID/start time. No signals sent. Before/after input hash maps agree.

## Implementation and verification

`tools/audit_hex_flight.py` exposes `check(root, require_cold_reset=False)` and CLI
`--run-dir`, `--output`, `--require-cold-reset`; output schema
`wksim.hex.flight.audit.v1`. CLI output must be a new file outside the original
run and any cold-reset ancestor. Exit 1 means rejected/incomplete evidence.

`validation/test_hex_flight_audit.py`: 25 checks. Combined with #52's four
foundation checks, **29 tests passed, zero skipped**, WSL /usr/bin/python3 and
the retained ROS overlays. `tests-final.log` contains the actual final output.

Adversarial cases include missing tick/terminal, swapped fifth/sixth actuator
channels (PX4 and AP decoder fixtures), changed model binding, one unsampled
1 ms hover violation, landing-tail violation, short dwell, relabelled cursor,
missing public request, wrong native target axes, missing/forged parameter,
deleted MAVLink datagram, invented publisher GID, false `observed`, static
fixture promotion, output overwrite/in-place write, a live process, and seven
cold-reset link changes (hash/run/epoch/tick/process/config/storage). Synthetic
guard cases do not establish a successful flight or cold reset.

## Exact rerunnable commands

From `C:/Users/PC/Documents/odid编译/wksim` in PowerShell:

```powershell
wsl -d Ubuntu-22.04 -u root -- bash validation/lunar-65-astra-20260909-01/run-audit.sh tools/audit_hex_flight.py --run-dir /root/wksim-hex-flight-px4-03/hex-px4-03 --output validation/lunar-65-astra-20260909-01/px4-03-audit-final.json
wsl -d Ubuntu-22.04 -u root -- bash validation/lunar-65-astra-20260909-01/verify.sh
```

These are the actual commands executed. For a repeat, select new audit/log
filenames; existing files are deliberately never overwritten. `run-audit.sh`
contains the exact five retained overlay setup paths and reuses private pyulog
at `/root/wksim-attitude-audit-deps-g_2y8olg`. It launches only the offline Python
command supplied to it. `verify.sh` contains the test command plus the exact
old-failure and required-cold-reset audits, expected exit codes and hash command.

## Preserved failures

- `px4-03-audit-01.json` and `-02.json`: rejected because the ad-hoc Windows→WSL
  command lost the inherited PYTHONPATH, so `rclpy` was unavailable. Selecting
  /usr/bin/python3 alone did not fix it. The retained shell file preserves the
  ROS environment correctly. An initial `set -u` wrapper attempt also stopped
  at ROS's unset `AMENT_TRACE_SETUP_FILES`; corrected to `set -eo pipefail`.
- `px4-03-audit-03.json`: initial complete pass, before final inventory/ground
  and native motor corroboration tightening; superseded by `-final.json`.
- `hex-px4-01-rejected.json`: exit 1, runner failure, physics terminal failure,
  original MAVLink decoded-payload mismatch and unsuccessful teardown rejected.
- `hex-px4-02-rejected.json`: exit 1, original runner/physics/teardown failures
  retained; not promoted by copying the PX4-03 result.
- `px4-03-cold-required.json`: exit 1 specifically because no cold-reset parent
  is supplied. An ordinary flight pass never silently becomes a cold-reset pass.

## Unverified boundaries / handoff

No actual Hex AP or cold-reset run was present. Read-only `/root` inventory
found PX4-01/02/03 and a ROS loopback fixture only. #66 remains the separate AP
flight/live-UE execution task and explicitly depends on #65; #67 is AP reset.
The AP audit path implements native GetParameters CDR, global-home target
reconstruction, MAVLink receipt, GUIP/RCOU/ARM BIN checks using the pinned source
schema; it has **not been validated end-to-end against an actual Hex AP run**.
Unexpected AP schema/binding will fail closed and require an auditor review,
never a relaxed physical budget. No AP flight PASS is claimed here.

Cold-reset checks recursively independently audit the parent result and bind
its immutable SHA, same configuration, different run/storage/epoch/processes,
tick zero and old process retirement. These are tested guards; actual reset
execution remains unverified. Current process absence cannot establish an
exact historical retirement instant, and this is not same-session hot recovery.

DDS discovery is endpoint discovery only: no per-message publisher GID exists
in this recorder. AP service serialization is not a captured server packet.
Native ULog/BIN observations are sampled, not proof of the exact first FC
acceptance tick. Source snapshots/build hashes prove the retained version;
they are not a new rebuild or a full current external source-tree audit.
UE rendering/live display, aircraft calibration, R1/G6, #25 and Full are outside
this audit. The old R1 and RateUnmet failures remain unchanged.

## Identity and execution settings

`hashes.txt` contains final auditor, tests, #52 foundation, frozen protocol,
final audit and test-log SHA256. The final audit includes all original run input
hashes and actual ROS/telemetry/ULog codec identities.

- Auditor: `3521e60140a5e2707aed00f62dde772a02968f8f077ada6aa20206676d0d660d`
- Tests: `97146893c9aea3dcb659252eaf422fe6751b7161c9c461d5aa7fda28cfe0c298`
- Raw physics: `2d93088f3d11945fc582d90f49310e867894f5f52216328ccd3f347afe85d5de`
- Library: `b10ef333129b44ce41d2d8d944a1e3d1161db9201bb1aea9eca88e726a5a7c9c`
- Protocol: `33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc`
- Final audit: `3bc1731769d49ea92c744180984fa39c0df1f459cea67b387e864a12dcf5d33d`

Actual session turn_context was read for task
`01a08555-4631-7021-baaf-c330155c22df`: **model=gpt-6-astra, effort=high**.
No subagents were created. Start HEAD was `e9a1d11`, branch
`codex/independent-rgb-integration`. Commit/push/Issue receipt is recorded separately.
The ponytail skill guided reuse of #52 and existing codecs without adding dependencies.
