# Failed AP Hex attempt: independent display/cleanup diagnostic

Run `hex-ap-live-20260909-01`; Windows evidence `validation/25-ap-live-20260909-01`; original Linux run `/root/wksim-hex-flight-ap-live-20260909-01/hex-ap-live-20260909-01`.

**Decision: failed pre-arm run, no flight or visual acceptance. No additional coordinator/display defect found in the path exercised.** The parameter failure `RuntimeError: Native parameter unavailable: ARMING_CHECK` is owned by the separate source/contract investigation. This review did not change runtime source, start UE/ROS/FC/model processes, inspect/rewrite parameters, or alter existing evidence.

## What actually ran

Result is `failed`, no armed state appears in retained task phases, `safe_landing=false`, stop kind `unsuccessful_isolated_teardown`. The coordinator preserved that failure: flight return 1, bridge return 0, owned UE termination return 1, and automatic audit `passed=false`, `status=rejected`, `Live run incomplete; preserve failure evidence`. The lack of `safe_landing` is expected here because no takeoff/landing mission completed; it is not promoted to a completed mission merely because teardown succeeded.

The complete raw stream contains one start, one initialized record, 41,526 actuator records, 41,526 physics steps and one terminal end. The terminal is `interrupted_or_failed`, `InterruptedError`, `Owned Hex physics process retired`, consistent with owned teardown of the failed task.

## Readback checks

The reviewer parsed all 1,929 rows in `readback.jsonl` and independently called the existing frozen packet validator and Actor error calculator for each packet/ACK pair, carrying the preceding actual ACK. First ACK has initial phase history, all subsequent `previous_step` values form a continuous accepted-state chain, and there are no numerical or phase-continuity failures.

Every displayed record matches its original raw physics tick exactly: time output[2], NED position[6:9], WXYZ quaternion[12:16], six rotor RPM[16:22], and observed Linux monotonic timestamp. Accepted ticks range from 20 to 41,520; maximum accepted step gap is 40 ms. Maximum transport age bound is 0.02314232507976044 s, below the unchanged 0.75 s limit.

Maximum errors: position 0 cm, quaternion L2 0, simulation time 0, local/world rotor origins each 5.0242958677880805e-15 cm, RPM 0, yaw 0, diameter 0, and accumulated phase 0. These are stationary, ground-only results. Zero RPM/phase error does not exercise rotating rotor dynamics or airborne tracking.

The log has 58 screenshot requests and all 58 PNG files exist. Of those, 29 initial requests have sequence -1 (no state yet); 29 have a nonnegative accepted sequence. Twenty-one requests are fresh and correlate to retained ACK sequences. The final request at frame-0057 has sequence 41,520, simulation time 41.52 s and `stale=1`. The ended source is therefore not being resent as newly LIVE. No image content was interpreted in this diagnostic; the parent owns actual PNG inspection. Screenshot-request metadata is distinct from proof of rendered content.

## Cleanup and relay

Completion reports all owned Windows processes exited and no cleanup errors. Independent current-process inspection confirms Windows UE PID 29824, bridge PID 56828 and WSL flight proxy PID 71964 are absent. Linux ownership inspection compares boot ID / PID / start time and confirms original physics 1868, Agent 1869, FC 1876, Control 1878 and supervisor 598 are absent. A read-only `/proc` search for this exact run plus `Simulator.ue55.hex_bridge --relay` found no matching surviving process. There is no separately retained Linux relay identity in the existing bridge; the exact-argv absence is corroboration, not a new persistent identity guarantee. Normal bridge exit 0, terminal end and no remaining relay are consistent with its EOF/close/wait path.

The coordinator correctly refuses its success audit when the flight fails. No minimal coordinator or visual-budget change is indicated from this run. Preserve the failure, resolve the actual ARMING_CHECK source/parameter contract, then use a new run/instance/evidence directory for any separately authorized next attempt. Do not relax physical phase requirements or visual acceptance to admit these ground-only records.

## Integrity

All 20 executed flight source snapshots and all 6 live-coordinator source snapshots match their retained manifests. SHA256 values at review:

| Evidence | SHA256 |
|---|---|
| Original result.json | `8e479b2a653ec3a8391c27d542e7fd0fba3092d45b21a8bb414b6bc49a88e59f` |
| Original physics-1ms.jsonl | `fb0362af9d49439cebf7f826cda1e9f2d7426afc74d91878e0e56d2bd0963115` |
| Windows manifest.json | `6429b740c26e3e764443a90d8ce6c90c98b9b0c7ee4714078bd300907470e855` |
| Windows completion.json | `e7bcc6616cdcc2454613f08d442998ec5d84ed80a6a4c102ceaf1208df13dbb6` |
| readback.jsonl | `541964a464f56042d950c43b3f2615785692bb682a4fb030efeb9613065418ee` |
| ue.log | `b191d3e0f18bb38beacfcf5795c77c76ba6dc46081d2580057e234a7a9da31e9` |

All diagnostics were finite, read-only Python/PowerShell operations against actual evidence. No synthetic flight, complete strict physical pass, or in-flight rendering is claimed.
