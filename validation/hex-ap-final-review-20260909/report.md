# Independent AP04 #66 final acceptance review

**#66 PASS for its bounded AP Hex flight plus live six-rotor display scope.** #67 AP cold-reset remains required; this review alone does not close #25. No runtime was started, no source/issue/commit changed, and only this new review directory was written.

## Independent verification performed

`verify_copies.py` rehashed all **75** provenance-listed source/copy file pairs: all match the exact recorded SHA256. The new bundle's `flight-audit.json` exactly equals the corrected physical report. The render review matches the same manifest binding and both captured-image hashes. Original rejected `flight-audit.json` and `automatic-audit.json` remain present and rejected, hashes recorded in `copy-verification.json`. This is a new analysis of unchanged original evidence, not a replacement flight or overwritten failure.

Repeated the complete physical/native audit against the actual retained Linux run. It passes with no errors, and its entire output is byte-identical to the supplied report: SHA256 **`116326e3a151c9dd60a0acf857d0c9423373fa352aca1865810034d333738850`** (`independent-physical-audit.json`). Repeated visual/raw/capture audit also passes and is byte-identical to the reviewed report: SHA256 **`861a20ee33aa41a55b4403e79d99c6c7ecc5b9e2ab022c376e98550070663128`** (`independent-visual-audit.json`).

## Physical/native invariants

The report binds AP04 to model `sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a`, library `b10ef333...`, configuration `sha256:94664f7e98b51ee2d55beadd3a7a9af0a06579f86dd8390f0e6912d267b0127e`, and AP47v2 protocol `ce4f0aeb3c2de250aaf10c224f3fa43c326fcfcf8140c3746770879558f9df37`. All20 executed sources, seals/maps,45 input artifacts and postflight identity are verified; no PX4 historical compatibility exception is used for AP.

- 65,159 continuous1ms physical steps and actuators, initial tick0, all six native motor channels active, expected owner-retirement end. All frozen physical windows pass: hold5021 samples, waypoint2001, landing-to-terminal160, parameter-ground421; zero violations.
- All33 native parameters pass before arm, including ARMING_SKIPCHK=0 and MAV1_POSITION/EXTRA1/EXTRA3=10/10/5. Native checks were not disabled.
- Six public requests/54 phases,151 waypoint DDS targets,151 GUI receipts (150 new plus one source-explained preceding goal),45 global and45 local FC target receipts. Three sequential allowlisted observation requests/ACKs for87/85/245 at100000µs precede arming. The auditor verifies raw COMMAND_LONG/COMMAND_ACK source/target identities, ACK result0 and deadlines; it explicitly does not invent a message-id echo in COMMAND_ACK.
- Read the actual pinned `mode_guided.cpp` path: its global Location branch logs lat/lon/alt through Vector3p; `Log.cpp:369–371` converts those components to float. Consequently GUIP represents float32 E7 latitude/longitude and centimeter altitude on this path, not local meters. The audit's E7 truncation, Home/origin, float32 projection and global/local receipt conversions reflect that source path. Local wire tolerance stays1e-6; global/log representations are exact.
- Global/local native masks are exactly0xFDF8/0x0DF8 with FORCE_SET excluded; no velocity/acceleration path or terrain target is accepted. DataFlash is exactly `logs/00000001.BIN`; the16,384-byte EEPROM is separately hash-bound parameter storage, not silently dropped or interpreted as DataFlash.
- Five native process identities are absent by boot_id/PID/starttime check. Flight and bridge return0, owned Windows handles exited, cleanup errors empty, sources/module unchanged. UE exit1 is recorded owned termination, **not graceful UE shutdown**; #66 does not require redefining that as graceful.

## Live visual and image check

All3011 accepted ACKs bind to the same fresh run/instance/model and actual raw ticks. Phase coverage is265 takeoff,230 hold,207 waypoint and380 landing ACKs. Every frozen numerical visual bound passes, including quaternion maximum5.8916577e-7 (<1e-6), world-origin maximum2.8171860e-5cm (<3e-4cm), exact RPM and phase maximum2.9103830e-11deg (<1e-6deg). Missing accepted-step phase history would reject; copied/static prior-state evidence was not used.

Independently viewed actual `frame-0045.png` and `frame-0048.png` via image viewer. Both show the six-arm/rotor Hex structure and green `LIVE / independent SITL physics` HUD. Hover shows sequence49700/sim49.700 with position N0.035/E-0.037/D-2.935m. Waypoint shows sequence55740/sim55.740 with N3.025/E2.015/D-2.971m, consistent with ENU[2,3,3]. Their hashes equal the explicit render review. HUD rejected counts3 and6 remain visible; accepted readbacks still pass unchanged guards. These screenshots prove rendered appearance at the inspected moments, while continuous ACK/raw records supply the numerical phase evidence.

Freshness evidence remains honestly bounded: source/transport ages plus actual receiver acceptance, no independent ACK-receive UTC. No arbitrary additional visual cadence threshold was introduced.

## Remaining work

#67 must use this accepted AP04 result as its exact SHA-bound parent, a new run/control epoch and fresh parameter/model lifetime; independently verify same configuration, tick0, no old task/process reuse and complete physical flight/reset. Its ticket allows reuse of these AP live visuals only if the visual path is unaffected. Current physical report explicitly says cold_reset not_present; this review does not imply it happened.

Accepted parent `/root/wksim-hex-flight-ap-live-observed-20260909-04/hex-ap-live-observed-20260909-04/result.json` SHA256: `d29308997ac1c71d7d89ad30ea5a0a8431164a19a12988f44efe188747531c86`.

#25 additionally requires its original dependency/child and dual-stack configuration/reset/display obligations to be reconciled, including the current #69 outcome; this review does not independently adjudicate the latest PX4 evidence. The result applies only to the frozen source-template Hex X, not real-aircraft calibration, other six-rotor geometries, R1/G6, #20/#62 or Full.
