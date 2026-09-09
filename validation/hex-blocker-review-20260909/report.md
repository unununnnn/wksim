# Hex #66 / #69 blocker review — 2026-09-09

## Verified scope

Own session turn_context: gpt-6-astra, effort low, service_tier null (unchanged). No nested agent. Read-only existing source/evidence and GitHub issue bodies/comments. No FC, ROS, model, UE, flight, production source, existing evidence, or issue mutations. New files only in this directory. Known source paths came from the issue documentation; direct source reads apply, so no structural graph exploration or index refresh was needed.

## Priority diagnosis

The demonstrated blocker is the missing **owned live-run orchestration and final visual acceptance** around an already implemented Hex bridge. This is not evidence of an AP controller, Hex physics, PX4-reset, or rotor renderer defect.

Both issue comments accurately identify missing reviewed live invocation. `tools/run_hex_flight.py:49` deterministically writes `<output-root>/<run-id>/physics-1ms.jsonl`. `Simulator/ue55/hex_bridge.py` already accepts that path plus explicit run/model/instance/port and writes correlated packet/Actor ACK rows. `tools/check-hex-view.ps1` already launches the candidate UE with the same binding shape, but deliberately supplies synthetic states via `check_hex_view.py`; it cannot be reused as a live acceptance command unchanged.

Actual retained PX4-03 raw was read under WSL without running any simulation:

- `/root/wksim-hex-flight-px4-03/hex-px4-03/physics-1ms.jsonl`: 55,545,097 bytes, 38,644 records, largest record 4,082 bytes.
- Bound start: `run_id=hex-px4-03`, model `sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a`.
- First/last step 1 / 30,924; observed monotonic span 30.92049828 seconds.
- Final record explicitly says `kind=end`, `status=interrupted_or_failed`, `error_type=InterruptedError`, `error=Owned Hex physics process retired`. This specific owner-retirement ending is independently distinguished from failed physics by the existing audit. Do not relabel its raw terminal.
- Existing `validation/lunar-65-astra-20260909-01/px4-03-audit-final.json` has passing 1 ms hold (ticks 13200–18220) and waypoint (20740–22760) windows. It explicitly excludes UE and does not supply cold reset evidence. The separate `--require-cold-reset` audit rejects absent reset evidence.

`LiveRawTail._open` correctly treats that completed trace as ended and skips existing state. Feeding it to the bridge cannot supply LIVE proof. The correct solution is preparing the display/relay before a fresh experiment, not replaying PX4-03.

## Demonstrated acceptance trap (offline red)

`probe.py` invokes the actual `bridge` function with mocked transport containing a terminal envelope and no ACK. It returns normally with zero sends and a zero-byte evidence file. `probe-result.json` retains this result; process exit was 1 only because the diagnostic asserted that normal return implied an ACK. No external process or socket was created.

This does **not** mean the bridge falsely reports `passed`; it reports no verdict. It proves that a new wrapper must not interpret bridge exit 0 as successful LIVE display. The current flight auditor also deliberately excludes UE. Simply writing down three launch commands would leave this acceptance gap.

## One feasible implementation slice

Add one tool-owned Windows coordinator, e.g. `tools/run-hex-live.ps1`, reusing the candidate UE launch shape and unchanged flight runner/bridge. It should freeze one fresh run/instance/model/port/raw/readback manifest, verify candidate module and model identities, start UE and wait for its bound `WKSIM_READY`, start the bridge against the not-yet-existing future raw path, then start one flight. Preserve all launch arguments, source/module hashes, process identities, logs, screenshots, and cleanup. The runner's existing preflight and physical budgets remain authoritative. The wrapper needs an outer watchdog because bridge's blocking `stdout.readline` is not interrupted by its own duration condition.

Add a small tool-owned visual audit (or a local audit function in that coordinator) that requires nonempty correlated ACKs and recomputes all frozen visual errors, treats missing phase continuity (`phase_deg=None`) as unproven, verifies binding to actual raw step/output values, retains freshness evidence, and checks rendered capture evidence separately. Do not treat a numeric errors dictionary as a pass automatically: the bridge records errors without applying pass thresholds. Coverage must include the actual takeoff/hold/waypoint/landing phases, not a single successful ground ACK. Do not invent a new cadence threshold: use the frozen contract and report source/ACK gaps explicitly.

Ownership: new `tools/run-hex-live.ps1` plus new visual-audit tests/tool and evidence. Reuse read-only `tools/run_hex_flight.py`, `Simulator/ue55/hex_bridge.py`, `tools/check-hex-view.ps1` launch pattern, and `tools/audit_hex_flight.py`. No need to alter PID files, flight controller, model, protocol budgets, or UE C++ for this blocker.

## Exact binding shape for parent review (not executed)

For a fresh chosen AP run `hex-ap-live-review-20260909-01`, output root `/root/wksim-hex-flight-ap-live-review-20260909-01`, and generated 32-lowercase-hex instance, the bridge must use:

```powershell
python -B -m Simulator.ue55.hex_bridge --wsl-repo '/mnt/c/Users/PC/Documents/odid编译/wksim' --raw '/root/wksim-hex-flight-ap-live-review-20260909-01/hex-ap-live-review-20260909-01/physics-1ms.jsonl' --run-id hex-ap-live-review-20260909-01 --instance-id $instance --model-identity sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a --port $port --readback $freshReadback --duration 330
```

The UE launch must use those exact run/instance/model/port values and `-WksimConfiguration=hex-X -WksimVehicle=1`, candidate project `E:/ue5.5/build/wksim-native-hex-20260909-01/WksimVisual.uproject`, candidate module SHA `15af1f6e400e77d6a8a207fd047b48b1d04c54260a5668312178051c119e6245`, and a fresh capture directory. Review candidate identity again before execution; this report did not freshly hash the binary.

WSL flight invocation bound to that same raw file:

```bash
bash tools/run-hex-flight.sh --stack arducopter --run-id hex-ap-live-review-20260909-01 --output-root /root/wksim-hex-flight-ap-live-review-20260909-01
```

#69 analogously uses a fresh PX4 run/output/UE instance and `--cold-reset-from /root/wksim-hex-flight-px4-03/hex-px4-03/result.json`. First independently recheck the accepted parent's exact hash and retirement; afterward run the flight audit with `--require-cold-reset`, as well as the separate visual audit.

These are explicit binding shapes, not a claim that the still-missing coordinator/audit was implemented or that live prerequisites have passed.

## Smallest regression and acceptance sequence

First make a pure coordinator/auditor regression: an empty readback with a successful bridge return must reject before any acceptance promotion. `probe.py` is the current red-capable concrete demonstration. Add one nominal correlated ACK fixture and mutations for foreign binding, over-budget error, and missing phase continuity to exercise the verdict without UE. A mocked readiness failure must assert the flight launch was never invoked.

Then run exactly one AP flight with already-ready actual UE and bridge, retain raw + captures + ACKs, independently audit both physical and visual acceptance, and record owned-process retirement. Only after that repeat for fresh PX4 cold-reset with the exact accepted parent. Each child remains open unless both its original physical and visual criteria pass. R1/G6/Full remain separate.
