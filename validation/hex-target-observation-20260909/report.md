# AP Hex target observation and source-correct receipt audit

Implemented only in `Simulator/wksim_runtime/hex_task.py`, `tools/audit_hex_flight.py`, and new `validation/test_hex_target_observation.py`. No live process, UE, FC, ROS node or model was started. No protocol/plan/physical-budget bytes, runner, baseline source, original evidence, issue, commit or push was changed.

## Runtime observation

Before public control readiness/arming, AP requests exactly POSITION_TARGET_GLOBAL_INT (87), POSITION_TARGET_LOCAL_NED (85), and EXTENDED_SYS_STATE (245), each at 100,000 microseconds (10 Hz), via COMMAND_LONG/MAV_CMD_SET_MESSAGE_INTERVAL (511). The API accepts only these three integer message IDs and constructs the fixed observation command internally; it cannot send motion or arbitrary commands.

Each request is recorded as exact encoded bytes before sending. Only the identified local peer, source system/component 241/1 and ACK destination 245/190 with command 511 can acknowledge it. Requests are sequential with one outstanding at a time; denial/unsupported/failure rejects, IN_PROGRESS does not release, and missing/foreign ACKs time out. The existing `parameter_read_timeout_s` provides the hard deadline, checked before accepting even a late successful ACK; the existing overall watchdog remains unchanged. Ground freshness, peer, control epoch and native generation must remain valid. Raw ACK packets remain in the original native stream and are linked in the observation event record.

After `landed_disarmed_public`, AP waits for a newly received identity-checked EXTENDED_SYS_STATE landed=1 sample under the same existing bound. An already cached landed sample cannot retire the task. PX4 skips both new AP-only operations.

The offline auditor independently decodes the three outgoing request frames, verifies the fixed allowlist/arguments/source/destination, before-arm timing and sequential bounds, and associates each retained ACK packet with the independently decoded raw incoming datagrams. COMMAND_ACK has no message-ID echo: the report explicitly describes sequential single-outstanding association, not a native per-request identity guarantee.

## Native representations and chronology

The original DDS/Home association remains exact. For the global Location setter, GUIP records float32 latitude E7, longitude E7 and centimetres, with Type=2, Terrain=0 and zero velocity/acceleration. It is not metre-valued local target telemetry. `mode_guided.cpp:545` and `Log.cpp:363–378` supply this law. A preceding DDS goal already in transit at public acceptance is allowed until new-goal native evidence appears; afterwards old/unexplained goals reject. Every new waypoint must be corroborated by GUIP and both global/local target telemetry before landing. Native source timestamps and original CDR history supply association; no receipt is synthesized or accepted merely from a public ACK.

`get_wp` rebuilds a Location from the stored NED position. The auditor separately reproduces:

1. DDS double degrees → Location integer E7, float altitude → integer cm.
2. Home/origin altitude conversion, double NE position and float altitude as used by the pinned SITL build.
3. `Location::from_ekf_offset_NED_m` and `offset_latlng`, including the float32 inverse scaling constant.
4. Global telemetry altitude as **float32(float32(absolute_cm) × float32(0.01))**, matching the sender's `target.alt * 0.01f` expression.

For the actual retained input E7 `[401540571,1162593918]`, relative altitude 300 cm, Home altitude 4997 cm and origin altitude 5000 cm, an independently compiled, recording-only C++ arithmetic oracle confirms:

| Representation | Expected fields |
|---|---|
| GUIP input Location float32 | `[401540576,1162593920,300]` |
| Local target float32 metres | `[2.9944770336151123,1.9994386434555054,-2.9700000286102295]` |
| Rebuilt global target | `[401540570,1162593917,52.969997406005859]` |

The existing 1e-6 local wire tolerance and all physical tolerances are unchanged. GUIP and rebuilt global fields compare to their exact source-derived representation. Same-timestamp ordering across native telemetry/logs remains ambiguous; prior-goal telemetry is not accepted strictly later than the first new-goal GUIP proof. No exact first acceptance tick or per-packet publisher identity is claimed.

## Red/green checks and old-run boundary

Initial new regressions fail against the old source (retained red stdout/stderr and source hashes). `legacy_guip_regression.py` additionally loads the exact old auditor SHA `bf05c8c1c6e2cdbefd04f99542e37af61d48283ad36b9cba364961ab5108beed` and demonstrates its GUIP/metres assertion rejecting the source-correct representation. That isolation test uses clearly synthetic telemetry to reach the old GUIP assertion; it never modifies real run data. New tests cover legitimate preceding goals, unknown targets, old goals after new receipt, E7 echo mistakes, wrong float altitude, required messages, request allowlist, failed/unsupported/foreign/absent/in-progress/late ACKs, ground-generation loss, incomplete send, raw ACK binding and new landed observation.

**56/56 sourced WSL tests passed, zero skips**, including the complete retained historical PX4 audit and existing Hex/AP47/retirement suites; command and pins are in `green-tests.json`. The C++ expression oracle (`g++ -std=c++17 -O0`) has its source and exact output retained; it does not load or call the native vehicle/model implementation. `git diff --check` passed for the owned production files.

The original actual AP run was re-audited into a new report `old-ap-rejection.json` using distinct command metadata/log filenames. It still rejects, solely at `native_delivery` with `Missing/reordered AP observation requests/ACKs`. Its three absent telemetry types and missing observation setup remain absent; no old run was promoted. A fresh actual AP run is required for acceptance.

## Frozen handoff hashes

- HexTask: `c2c4ddeee188fdc0cb961deb62fb66a8f3a78f7099eb993c39de827813a9e28a`
- Auditor: `a776c4d9dc0192f599318f6fb2b84348794e04c5dd4b22590bbb9c5938ce6413`
- New tests: `5e65d1802558949f3cc314ee9bf610731894dbb8d7718e8b288a43474376ad2a`

Exact copies are in `run-source/`; fixed native C++ source hashes are in `native-source-sha256.json`. Legacy/PX4 protocol remains `33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc`, AP47v1 remains `cf9bfe890cc0a5e3c04d72dd0df5d1f9fd5bb18a2c60c588393266c542fac464`, and AP47v2 remains `ce4f0aeb3c2de250aaf10c224f3fa43c326fcfcf8140c3746770879558f9df37`. Runtime source is now ready for the parent's independent pre-run review; this implementation handoff is not a new flight acceptance.
