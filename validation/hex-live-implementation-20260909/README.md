# Hex live coordinator implementation

No actual UE, FC, ROS, model or flight was launched. Fourteen finite offline tests passed, including an actual coordinator readiness-failure test with all external operations mocked, raw/ACK mismatch, numeric-budget failure, empty ACK, missing phase history, missing phase coverage, capture-review hash mismatch, stale capture, and exclusive report-file protection. PowerShell parsed without errors. Tests are synthetic acceptance-unit evidence, never rendering or flight evidence.

## Owned files

- `tools/run-hex-live.ps1`: thin Windows entry, exact named arguments.
- `tools/audit_hex_live.py`: Windows coordinator plus offline Actor/raw/capture audit.
- `validation/test_hex_live.py`: offline tests.

Coordinator verifies the pinned UE module, uses existing read-only Hex preflight, verifies model identity from its actual output, and launches the existing UE candidate with unchanged Hex flags. It waits for the exact bound `WKSIM_READY`, starts the unchanged bridge with the future raw path, waits for its exclusive evidence file creation, then launches the existing flight runner. Cold reset first independently audits its parent through the existing retained overlay runner and uses unchanged `--cold-reset-from`. The resulting physical audit uses `--require-cold-reset`.

Manifest, separate stdout/stderr logs, exact argv, retained-process-handle ownership records, source copies/hashes, capture PNGs, ACK JSONL, physical audit, and cleanup are preserved in the fresh output. Report files use exclusive creation; command logs never share report paths.

## Commands for parent scheduling — not executed

From the Windows repository root:

```powershell
./tools/run-hex-live.ps1 -Stack arducopter -RunId hex-ap-live-20260909-01 -OutputRoot /root/wksim-hex-flight-ap-live-20260909-01 -Output C:/Users/PC/Documents/odid编译/wksim/validation/25-ap-live-20260909-01
```

Fresh PX4 reset (schedule separately after AP review):

```powershell
./tools/run-hex-live.ps1 -Stack px4 -RunId hex-px4-live-reset-20260909-01 -OutputRoot /root/wksim-hex-flight-px4-live-reset-20260909-01 -Output C:/Users/PC/Documents/odid编译/wksim/validation/25-px4-reset-live-20260909-01 -ColdResetFrom /root/wksim-hex-flight-px4-03/hex-px4-03/result.json
```

All names must still be fresh. `-Python`, `-Stage`, `-Engine`, `-AuditRunner` are explicit optional parameters; defaults reuse the known candidate and `validation/lunar-65-astra-20260909-01/run-audit.sh`. No overlay discovery or changes are performed. Native `python -B tools/audit_hex_live.py run --help` lists equivalent arguments.

Exit 1 rejects; exit 2 means numeric Actor/raw/capture binding checks passed but rendered-image review is still required. It does not mean full acceptance. Automatic audit uses frozen `check_hex_view.LIMITS`, recomputes all Actor errors, rejects missing accepted-step phase history, and requires raw-correlated ACKs in each existing takeoff/hold/waypoint/landing phase. Accepted-step gaps are reported without inventing a new display cadence budget. Raw/result hashes must match the independent flight audit.

After parent inspects actual captured PNGs using `view_image`, create a new explicit review JSON, using the exact binding from `manifest.json` and image hashes from `automatic-audit.json`:

```json
{
  "binding": {"run_id": "actual-run-id", "instance_id": "actual-32-hex-instance", "model_identity": "sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a"},
  "reviewer": "actual reviewing agent/person",
  "six_rotor_structure_visible": true,
  "live_hud_visible": true,
  "captures": {"frame-actual.png": "actual SHA256"}
}
```

Only record those booleans after actually observing them. Then run the offline verdict to a different fresh filename:

```powershell
python -B tools/audit_hex_live.py audit --directory C:/path/to/fresh-live-evidence --render-review C:/path/to/render-review.json --output C:/path/to/fresh-live-evidence/reviewed-audit.json
```

## Explicit existing boundaries

The unchanged bridge has no relay-ready event. Readback-file creation proves the bridge reached its pipe-pull section, not a Linux child readiness handshake; subsequent absent ACKs fail the audit. No source/clock is retimestamped. Existing ACK records lack an independent ACK-receive UTC: audit checks recorded transport/source bounds and actual receiver acceptance, and reports that evidence limit.

Cleanup uses retained native Windows process handles, never process-name/global/PID-discovery kills. UE is terminated through its owned handle after the run; this is process retirement, not graceful GUI shutdown. If the flight supervisor exceeds its existing watchdog plus allowance, the coordinator deliberately leaves it owned/running and reports failure requiring inspection rather than killing its WSL proxy and potentially stranding native children. Normal flight retirement is independently checked by the existing flight auditor. Normal bridge completion closes/waits its relay using its existing implementation; abnormal bridge termination lacks separate Linux relay identity proof, remains a failure, and requires owner inspection.

No PID, sealed build, runtime budget, UE source, existing flight/bridge implementation, issue, commit or push changed.

## Pre-run review correction

The initial implementation incorrectly started takeoff display coverage at `task_control_ready`. Actual retained PX4-03 has `armed=4.24 s`, `task_control_ready=13.18 s`, and `takeoff_reached=13.200000000000001 s`. HexTask emits `armed` immediately before sending SET_CONTROL_MODE. The sealed Control node (`/root/wksim-joint-control-FVMjak/install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control/node.py`, native requests at lines 399 and 501) performs takeoff inside that operation before reporting setup completion. Starting at completion therefore considered only the last 20 ms and could reject valid lower-frequency UE ACKs.

Takeoff coverage now starts at the existing `armed` phase and ends at unchanged `takeoff_reached`; no new threshold or physical budget was introduced. `takeoff-tail-red.log` retains the failing original implementation against the actual phase-time shape (synthetic state/ACKs, no flight). The corrected version passes this regression.

The same review hardened retained provenance: audit now checks the exact six archived/current live source identities and rehashes every file listed by the independent flight audit, including native logs. Corrupted archived verifier/native-log regressions reject. Final `tests-after-review.log`: **17 tests passed**, no runtime started. Earlier 14-test evidence remains historical and unchanged.
