# AP Hex native-delivery failure: independent source/raw diagnosis

Run: `hex-ap-live-ap47v2-20260909-03`. Existing strict report remains rejected at `native_delivery`. The identity, physics, public chain, physical windows, all 33 native parameters and retirement checks pass. No production source or original evidence was modified and no runtime was launched by this review.

## Current first failure is missing telemetry, not a numerical mismatch

Full retained MAVLink decoding through the existing sealed codecs finds **zero POSITION_TARGET_GLOBAL_INT, zero POSITION_TARGET_LOCAL_NED and zero EXTENDED_SYS_STATE messages in the entire run**. During the waypoint monotonic window `[574.127704371, 578.667743163)`, there are 46 GLOBAL_POSITION_INT and 46 LOCAL_POSITION_NED messages, which describe actual state and are not target receipt messages. Thus `native_delivery()`'s `received` list is empty; its generic `AP FC global target receipt differs from DDS/home` assertion fails regardless of tolerance or coordinate calculation. Its later local-target and final landed-state checks would also fail.

Native source confirms the configuration distinction: `libraries/GCS_MAVLink/GCS_MAVLink_Parameters.cpp:272–277` puts only MSG_LOCATION/MSG_LOCAL_POSITION in STREAM_POSITION. Global-target telemetry belongs to STREAM_EXTENDED_STATUS near line 266; local-target telemetry has no corresponding default stream entry. The configured MAV1_POSITION/EXTRA1/EXTRA3 rates therefore do not guarantee the three messages required by this auditor, and HexTask contains no explicit message-interval setup.

The minimum prospective observation fix is bounded requests for message IDs 87 (POSITION_TARGET_GLOBAL_INT), 85 (POSITION_TARGET_LOCAL_NED) and 245 (EXTENDED_SYS_STATE), using identity-checked MAV_CMD_SET_MESSAGE_INTERVAL requests and real acknowledgment/appropriate stage observation. Do not wait for a position target while AP is still in a mode with no target; `ModeGuided::get_wp` and local-target send only expose suitable Guided submodes. Missing messages must remain a failure. The current run cannot acquire those missing past observations by changing a tolerance.

## A second source/encoding bug is masked by the missing messages

The auditor incorrectly assumes all GUIP rows contain origin-relative NED metres. The actual global DDS path calls the `Location` overload of `ModeGuided::set_destination`. In fixed `ArduCopter/mode_guided.cpp:496/545` that overload logs `Vector3p(dest_loc.lat, dest_loc.lng, dest_loc.alt)` — latitude E7, longitude E7 and centimetres — through the GUIP float fields. The separate local-vector overload logs local NED metres at lines 394/436. `Type=2` is Guided Pos mode and does not by itself distinguish these overloaded source representations.

The independent full codec diagnostic found 151 waypoint DDS targets. All exactly match their timestamp-bound Home projection:

| Field | Actual value |
|---|---:|
| Home latitude E7 | 401540302 |
| Home longitude E7 | 1162593683 |
| Home altitude cm | 4997 |
| DDS latitude | 40.1540571 |
| DDS longitude | 116.2593918 |
| DDS relative altitude m | 3.0 |
| Native requested latitude E7 | 401540571 |
| Native requested longitude E7 | 1162593918 |
| Exact float32 GUIP fields | `[401540576.0, 1162593920.0, 300.0]` |

Actual matching GUIP at 52.331 s contains exactly those float32 fields, with zero velocity/acceleration and Terrain=0. These values must not be compared directly to metre-valued POSITION_TARGET_LOCAL_NED coordinates. The smallest source-specific regression uses these retained integers, float32 serialization via `struct.pack/unpack`, and the actual matching GUIP fields; require exact wire-equivalent values rather than raising a physical or generic numerical tolerance.

## Association also needs the actual native chronology

The waypoint native window is `[52.294, 56.831)` seconds. Its first GUIP at 52.304 s still contains the previous hover target `[401540288.0, 1162593664.0, 300.0]`; the first new DDS target has native stamp 52.316 s and receiver monotonic time 574.153642043. The next GUIP at 52.331 s matches the new target. This is a real queued old output after public acceptance, not a wrong new command. Associate original source-timestamped DDS records to their subsequent GUI receipts, including the preceding retained target for transition rows. Do not require every native record after public ACK to already equal the new target, and do not simply discard unmatched rows without explaining them from original earlier CDR.

## Evidence and disposition

`diagnose_native_receipt.py` runs read-only with the existing sealed overlay helper and exits 0, verifying the raw DDS/Home relation and extracting actual BIN fields. Hex-native SHA256: `4229b791aa42d71d80b9531b6f8d0937b2701d027ccb39b34b0b593232c3bd27`; BIN SHA256: `7bfa753c705b703dda2f08adf3514dfbc7681694f35e8da529a9f08ac76beb0d`. An initial diagnostic filename `inspect.py` shadowed Python's standard-library inspect module and failed during import; it was renamed before the successful diagnostic. No original data was changed.

**Do not promote the existing strict run under its current target/landed-telemetry requirements.** There is positive accepted-command evidence in GUIP, but using direct GUIP plus source-derived DDS/Home/origin checks as a replacement proof would be an explicit independently reviewed evidence-contract decision, not a numeric bug fix. A new run with complete observation setup and the corrected GUIP representation/association preserves the current intended receipt proof. All physical budgets remain unchanged.
