# AP Hex pre-arm parameter diagnosis and explicit AP4.7 contract

Actual failed experiment: `/root/wksim-hex-flight-ap-live-20260909-01/hex-ap-live-20260909-01`. No additional flight, native model, FC, ROS node or UE was started for this work. Existing evidence and sealed source/binaries were read only.

## Demonstrated cause

The admitted AP commit is `1511f27194f1dcc3728270883047bdf022b3fd53`, binary SHA `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de`. Fresh read-only file hashes are in `source-provenance.json`.

`ArduCopter/Parameters.cpp:240` registers `ARMING_`. `libraries/AP_Arming/AP_Arming.cpp:160` explicitly reserves former CHECK index 8; line 201 registers `SKIPCHK` at index 13 with default 0. Lines 228–255 document and implement the 4.7 conversion: old CHECK bit 0 enabled (CHECK=1) maps to SKIPCHK=0, preserving all native checks. `check_enabled` line 326 uses `(checks_to_skip & check) == 0`.

The actual `/ap/get_parameters` response for ARMING_CHECK is `type=0` (NOT_SET), with leftover `integer_value=1000` from prior service storage. The exact request/response CDR and converted response were preserved in `actual-dds-not-set.json`. `AP_DDS_Client.cpp:1241–1245` produces NOT_SET when `AP_Param::find` returns null; lines 1261–1264 support INT32 normally. This is not a timeout, numeric decoder, or unsupported integer type. The existing HexTask guard correctly rejects the missing name.

`probe.py` exercises the actual `HexTask.ground_parameters` method with mocked DDS only. The real NOT_SET shape reproduces `Native parameter unavailable: ARMING_CHECK`; the proposed SKIPCHK=0 fixture succeeds, and SKIPCHK=-1 rejects. Fixture success is not a claim that a new native readback was performed.

## Authorized explicit revision

Parent approved ARMING_CHECK=1 → ARMING_SKIPCHK=0 while preserving every native check and legacy PX4 identity. `launch_plan()` and `launch_plan('px4')` still produce the unchanged legacy plan. `launch_plan('arducopter')` selects the renamed parameter; AP admission, defaults, task and auditor select the explicit new AP contract. Admission JSON shape remains unchanged.

| Identity | Legacy PX4 | New AP4.7 |
|---|---|---|
| Plan SHA identity | `319c5cba50eb11b81f70ac3ade707879c2fdba252335aa039674e93b9168e1a0` | `27d3b397feace63eb308365aee3d034733ea136f956bce797a0545219600f8fc` |
| Protocol file | `hex-flight-v1.json` | `hex-flight-ap47-v1.json` |
| Protocol SHA256 | `33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc` | `cf9bfe890cc0a5e3c04d72dd0df5d1f9fd5bb18a2c60c588393266c542fac464` |

The new JSON differs only in schema label and plan identity. Tests compare all remaining physical/time fields exactly. All PX4 parameters/environment and default plan output remain equal; the legacy JSON was never edited. The cold-reset guard chooses the stack's original/new protocol explicitly.

Historical PX4-03 identity recipes (`hex_candidate.py`, `hex_launch_plan.py`) necessarily differ in current source due to additive AP support. Auditor accepts their two exact previously retained SHA pins on PX4 only, verifies their archived bytes, and independently recomputes the unchanged PX4 parameter/configuration identity. It does not broadly accept old source versions. Shared native decoder/model checks remain unchanged.

## Verification and remaining external blocker

Windows launch/protocol suite: 13 tests, 12 passed and one sealed-WSL dialect test skipped. AP4.7 guard suite: 3 passed, including NOT_SET and every nonzero skip mask tested rejecting. Combined WSL suite with actual retained PX4-03: 41 tests, 40 passed, one existing real-run audit failed.

The actual strict re-audit is retained as `px4-03-strict-audit.json`. Its sole rejection is current `Simulator/wksim_core/px4_mavlink.py` drift from the archived `08b3d5fbf6754822572240ceb6beb289341bd0c6653455a35b60b3fb3d85ab3d` to `e8c903f2b4c84a261adf6f512c8437c51364143dc048d1ac2cb873e7cfb53260`. The current file has optional GNSS gate work not made in this AP contract change. No decoder whitelist, rollback or relaxed check was introduced. Parent has been asked to resolve that separate historical-source compatibility boundary; PX4 plan/protocol equality alone is not described as a full strict-audit pass.

Files changed: `tools/hex_launch_plan.py`, `tools/hex_candidate.py`, `tools/run_hex_flight.py`, `tools/audit_hex_flight.py`, `Simulator/wksim_runtime/hex_task.py`, new AP protocol, `validation/test_hex_flight.py`, new `validation/test_hex_ap47.py`. No coordinator, PID, sealed build, physical budget, UE source, issue, commit or push changed.

Final targeted WSL run excludes the declared historical decoder blocker rather than concealing it: `validation.test_hex_flight`, `validation.test_hex_ap47`, and `validation.test_hex_flight_audit.PureGuards` all pass, **24/24**, no skips (`targeted-wsl-tests.log`). Source/protocol pins are frozen in `final-source-hashes.json` and `protocol-hashes.json`. The failed full historical audit remains unchanged for the independent decoder review. No real flight/UE/FC was launched by this task.

## Independently reviewed paired historical compatibility

After the preceding rejection, parent authorized a narrowly paired PX4-only compatibility check based on `validation/hex-historical-px4-review-20260909/review.md`. The independent replay proved identical processing of 7,717 actual actuator packets, 7,731 actual sensor groups and 309 duplicate-send probes, without opening sockets or starting a model/FC/ROS/UE. Replay script SHA is `4a262673f3741f89d9aca99ad9fb4f19a28dbc5b5bc9df44398a75e017757d45`; replay-result SHA is `57b48618911ceaba0c30f2ce773bb091f355317a70de930b6176dcb5151c73ab`.

`audit_hex_flight.py` now requires both the exact historical and exact reviewed-current SHA for each of the three named legacy pairs (two identity recipes plus PX4 adapter). No future-current or unknown archived hash receives this exception; AP rules are unchanged. Archived source bytes, legacy PX4 plan/protocol, actual configuration, native delivery, physical budgets and process retirement remain independently checked. The accepted compatibility pairs are listed explicitly in the final audit's identity section.

`paired-pin-red.log` preserves the old historical-only exception failing to reject an altered current recipe at the intended guard. The new regression rejects it correctly. Pure adversarial checks additionally reject changed-current, changed-archived and AP use of each pair.

Actual PX4-03 complete strict re-audit **passed**, errors empty: `px4-03-paired-strict-audit.json`, SHA256 **`d834b59dfceec656c376dcc3d31a31b227a6262288159487531e3aec390e1fbe`**. The earlier rejected report is untouched. Final combined WSL tests **43/43 passed**, no skips (`paired-full-wsl-tests.log`). Only the offline auditor and its tests changed during parent's concurrent AP47 run; all runtime, plan, config, runner, UE and bridge files remained frozen. These checks do not claim a new PX4 flight or cold-reset execution.
