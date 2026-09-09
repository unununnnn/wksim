# Independent Hex live pre-run review

Scope: uncommitted `tools/audit_hex_live.py`, `tools/run-hex-live.ps1`, and `validation/test_hex_live.py`, compared with `docs/2026-09-09-hex-visual-contract.md`, implementation README, actual existing bridge/flight/auditor sources, and accepted `hex-px4-03` result/audit evidence.

Own current session metadata verified `gpt-6-astra`, effort `high`, existing service tier unchanged. No native/ROS/model/UE process was launched, and no production source, existing run, PID report, issue, commit or push was modified. Only this new review directory is owned by the reviewer.

## Initial finding

**Takeoff coverage incorrectly starts after most of the takeoff.** `audit_hex_live.py` initially defines the takeoff interval as `task_control_ready` through `takeoff_reached`. `HexTask.execute()` waits for `SET_CONTROL_MODE` before recording readiness; native takeover includes autonomous takeoff. The actual accepted `/root/wksim-hex-flight-px4-03/hex-px4-03/result.json` records `armed=4.24`, `task_control_ready=13.18`, and `takeoff_reached=13.20` seconds. A valid approximately 30 Hz renderer can miss this 20 ms tail even when the entire actual ascent was shown.

Independent finite fixture reproduces rejection: an ACK at 1.0 s, armed at 0.9 s, control-ready at 1.48 s, and takeoff-reached at 1.5 s yields `No actual display evidence during takeoff`. The synthetic original success fixture had an unrealistically wide ready-to-reached interval, hiding this mismatch. Use the existing source-proven `armed` marker through `takeoff_reached` without inventing a new duration/cadence budget. The finding was sent to the parent and implementer before scheduling a live flight.

An additional provenance concern was sent for hardening: the initial replay auditor trusts completion booleans `source_unchanged`/`module_unchanged` but does not verify the manifest's retained source hashes and `run-source` copies. Post-coordination code/copy corruption can therefore escape the fresh replay verdict; source evidence should be verified rather than merely preserved.

## Confirmed compatibility and checks

- `python -B -m unittest validation.test_hex_live -v`: 14 tests passed in 0.133 s, no skips. These are offline fixtures only. PowerShell AST parsing of the wrapper returned no errors.
- The actual accepted PX4 result parses successfully through the new strict `read()` function. Optional State nonfinite markers are compatible; no NaN/parser change is indicated.
- The actual `validation/lunar-65-astra-20260909-01/px4-03-audit-final.json` has schema `wksim.hex.flight.audit.v1`, `passed=true`, matching `root`, `checks.result.run_id`, and `inputs_sha256` entries for result and raw physics. Existing cold-reset logic provides `tick0` plus recursive `parent_audit.passed` when a cold reset is supplied.
- Actual retained hold/waypoint/landing phase names and paths match the new live auditor. At px4-03 they are hold 13.20–18.22, waypoint 18.22–22.76, landing 22.76–30.50 seconds.
- Bridge CLI options (`--raw`, run/instance/model identity, `--wsl-repo`, `--port`, `--readback`, `--duration`) and flight CLI arguments match their existing parsers. The current WSL default user is root, so the unchanged bridge can read the private `/root` trace. The launch wrapper explicitly selects root for the flight/auditor.
- UE readiness and screenshot log patterns match current candidate source. The pinned ready marker cannot trigger before initial render readiness. Game-thread ACKs remain separate from required human/agent inspection of captured images.
- Report paths are distinct from command logs: `flight-audit.json` vs `flight-audit.log`, `parent-audit.json` vs `parent-audit.log`, and fresh automatic/reviewed outputs. The earlier PID audit/command-name collision is not present here.
- Coordinator starts the bridge before the raw file exists, allowing fresh start binding and appended-only consumption. It holds retained Windows process handles and preserves failure on abnormal bridge/flight completion. Successful acceptance additionally requires the existing independent physical/retirement audit. No global/PID-name termination is used.

## Remaining explicit limits

The bridge readiness file proves local pull-loop setup, not a Linux relay handshake. Missing ACKs later reject. The reader/bridge preserve source-age bounds; ACK evidence lacks a separately recorded receive UTC. The audit rejects missing accepted-step phase history and checks all six actual origins/scales/spins/RPM/phases against frozen limits. Accepted sample gaps are reported, with no newly invented cadence threshold. Actual screenshot review is still required after numerical acceptance; fixture PNG signatures are not render proof. A stalled flight supervisor is deliberately left running for owner inspection instead of killing a proxy and stranding its native children; that outcome is a failure, never acceptance.

## Final pre-run recommendation: GO for one bounded AP live attempt

The implementer corrected the start marker to `armed`, with a regression using the real accepted PX4 phase-time shape and synthetic ACK at 9 s, well before the 20 ms control-ready tail. Independent review read the corrected source/tests and reran the suite: **17 tests passed in 0.388 s, no skips**. The reviewer's original finite 1.0/1.48/1.5 s case now returns `render_review_required`; it no longer rejects a valid takeoff observation or claims rendered acceptance.

Provenance hardening was also applied and reviewed: all six declared archived/current live source hashes must match; every file listed in the independent flight audit (including native logs) is checked, with path traversal rejected. New corruption regressions pass. The actual configured candidate DLL's bytes match the pinned `MODULE_SHA`.

Final reviewed SHA256 values:

- `tools/audit_hex_live.py`: `f394317c89e1d35962f1538bd562d86e6386aa5da0ed672ac0beebde22bda3ac`
- `tools/run-hex-live.ps1`: `3432a6cb1262aacf5c6e275813e2b2ffbb5eed2870e09add70a0f91e4b40ee6c`
- `validation/test_hex_live.py`: `76619b11c1015637d202b186a469944c55d1b5a6e25456a08266bc9be6590cc3`

No unresolved blocker was found for scheduling the bounded AP attempt. This is a pre-run recommendation only: actual raw/ACK/retirement evidence and explicit PNG inspection remain required; no flight/render acceptance is claimed. The parent received the recommendation before scheduling runtime work.
