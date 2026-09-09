# Same-run AP DataFlash classification and exact target-mask correction

**Strict physical/native audit PASS**, original run `hex-ap-live-observed-20260909-04`, with no new flight or runtime change. Final complete report is `strict-audit-final.json`, SHA256 `116326e3a151c9dd60a0acf857d0c9423373fa352aca1865810034d333738850`. Exact command/return code and separate stdout/stderr are retained as `audit-final.command.json` and matching logs. The Windows coordinator's original `flight-audit.json` and rejected automatic result were not overwritten.

## Changes

The pinned SITL `Storage.cpp:20` defines `eeprom.bin`, while `board/sitl.h:43` sets the logger directory to `logs` and `AP_Logger_File.cpp:377–380` generates `%08u.BIN`. The auditor now recognizes precisely `logs/NNNNNNNN.BIN` as DataFlash and exactly `eeprom.bin` as parameter storage. Unknown binary paths, absent logs and multiple DataFlash files reject. Every listed artifact still receives the original hash/size validation; EEPROM is neither dropped from the identity record nor decoded as a flight log. DataFlash reader resources are now closed on success and exception, avoiding leaked mapped-file handles during rejected-record tests.

The first re-audit then exposed my earlier target-mask arithmetic error. Actual and source-defined masks are `0xFDF8` global and `0x0DF8` local. The sum of VX/VY/VZ/AX/AY/AZ/YAW/YAW_RATE ignore flags excludes bit 9 (`FORCE_SET`). The previous `0xFFF8`/`0x0FF8` expectations incorrectly included that bit. The exact expectations were corrected, with a regression using actual masks and negative FORCE_SET variants. This is a field-definition correction, not relaxed axes or tolerance.

## Actual final evidence

- 65,159 continuous physics ticks and actuator records; complete expected owner-retirement terminal.
- 151 waypoint DDS targets and 151 GUI receipts: 150 new-goal receipts plus one explained preceding goal.
- 45 POSITION_TARGET_GLOBAL_INT and 45 POSITION_TARGET_LOCAL_NED receipts, matching exact frame/masks and the source-derived goal representations.
- Three exact observation requests/ACKs for 87/85/245 at 100,000 microseconds; a fresh native landed sample after the public landed phase.
- All actual global target fields are `[401540570,1162593917,52.96999740600586]`, as predicted before the run. Actual local values `[2.994476795196533,1.999438762664795,-2.9700000286102295]` are within the unchanged 1e-6 wire tolerance; no numerical tolerance or physical budget was changed.
- EEPROM remains hash-bound as `3a5d6d130e0dbfbb8ea9fd81e32200b186524290ab5278f22c0d7d411fdbbbe7`, size 16,384. Actual DataFlash is `logs/00000001.BIN`, hash `0600be089cfc3f1d38a5ef21a17d4cc623053c3b0bdbf3ca42e771d8f9e92d97`, size 2,977,792.

The intermediate `strict-audit.json` remains rejected at the mask check, preserving that failed attempt. Final `strict-audit-final.json` has `passed=true`, `errors=[]`; all existing identity/physical/public/parameter/retirement and native-delivery checks completed.

## Regression and handoff

The new EEPROM+DataFlash positive fixture failed the old classifier. Negative fixtures cover EEPROM alone, unknown filename/path, wrong case, duplicate logs, changed EEPROM bytes and an actual malformed DataFlash decode. An actual-mask fixture also failed before its exact correction. **59/59 sourced WSL tests pass**, including historical PX4 and existing Hex/AP observation/retirement tests; exact logs/commands are `tests-final.*`. `git diff --check` passed. No motion/resource launch occurred; only offline audit/tests ran against retained data.

Final auditor SHA256: `384ecfe4ab10e22567caf1aff499b4e98d9a85f9f33cbc2cb2d2f23359b48465`. Test SHA256: `e3497454233d43e9fc454b58a1a9acaf9ecb26520ea37fcae81820e8fbc31756`. HexTask remains unchanged at `c2c4ddeee188fdc0cb961deb62fb66a8f3a78f7099eb993c39de827813a9e28a`. Copies/pins are retained locally.

The root agent owns the separate rendered-image review. Since the unchanged live auditor reads a fixed `flight-audit.json`, a new review bundle with byte-identical original display evidence and the corrected strict report can preserve the original rejected coordinator reports. Do not overwrite the original failed evidence. This handoff is a physical/native PASS; full AP live/render acceptance remains the root's subsequent step.
