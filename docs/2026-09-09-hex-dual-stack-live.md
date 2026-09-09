# Hex live and PX4 cold-reset acceptance

Both stacks now have real six-rotor UE display evidence, full physical/native
audits and explicit inspection of actual hover/waypoint PNGs. These are
independent runs, not joint-scene or real-time-rate acceptance.

| Slice | Run | Physical report | Reviewed display |
| --- | --- | --- | --- |
| #69 PX4 cold reset | `hex-px4-live-reset-20260909-02` | `validation/25-px4-reset-live-20260909-02/flight-audit.json` | same directory `reviewed-audit.json`: passed, 1,417 ACKs |
| #66 AP live | `hex-ap-live-observed-20260909-04` | `validation/hex-ap-dataflash-20260909/strict-audit-final.json` | `validation/25-ap-live-observed-20260909-04-reviewed/reviewed-audit.json`: passed, 3,011 ACKs |

PX4 source parent is the original accepted `hex-px4-03` result SHA256
`ab9aeff2e222bb7105a8dfe9a6e25420eb1768ec062eaaf3deba40b8eba3b3ff`.
The parent was recursively re-audited. The new run has the same configuration,
new run/control epoch, new owned processes and native storage, and model tick0.
Actual owner retirement and cleanup pass. First reset attempt remains rejected
because FC-first shutdown caused a physical `ConnectionResetError`; the runner
now reaps physics first using the existing bounded group cleanup. No peer-reset
exception was added to the physical auditor. Partial-tail failures remain rejected.

## AP source compatibility and observation corrections

The admitted AP4.7 source uses `ARMING_SKIPCHK=0`, equivalent to legacy
`ARMING_CHECK=1` (all native checks enabled). Its first MAVLink stream group is
`MAV1_`, replacing the planned legacy `SR0_` names. A complete native 33-parameter
census confirmed the remaining names and values; rates remain 10/10/5 Hz.
AP47v1/v2 are explicit versioned protocol files; legacy PX4 protocol bytes and
plan identity remain unchanged. Physical/time budgets did not change.

The runtime explicitly requests only target/global/local/landed observation
messages 87/85/245 at 10Hz through identity-checked COMMAND_LONG511. All three
raw requests/ACKs are checked before arming; a new native landed sample is
required after public landing. This observation socket cannot send motion.

Source-derived AP audit fixes distinguish raw global Location inputs logged by
GUIP (E7/E7/cm stored as float32) from local metres and the reconstructed global
target. A C++ source-expression oracle verifies the exact inverse-scale and
float32 encodings. Legitimate preceding-target receipts before the new target
are handled chronologically; unexplained/later old targets are rejected. The
exact emitted masks are global `0xFDF8`, local `0xDF8`; FORCE_SET is not an ignore
bit. EEPROM parameter storage is still hash-checked but is not a DataFlash log.

The accepted AP raw run has 65,159 physics ticks, 33 parameter readbacks, 151
DDS targets, 150 new-goal GUIP receipts plus one preceding-goal receipt, and 45
each global/local target telemetry receipts. This is source-time/value evidence,
not per-request native identity or an exact first-acceptance-tick claim.

## Preserved failures and reanalysis

The original AP04 coordinator/flight-audit reports remain rejected and unchanged.
After correcting only the audit implementation, the same immutable raw run
passed the new strict report SHA256
`116326e3a151c9dd60a0acf857d0c9423373fa352aca1865810034d333738850`.
No extra flight was used to hide the audit defects.

`reanalysis_bundle.py` created a fresh review directory with byte-identical
manifest, completion, raw readback, UE log, source copies and PNGs, plus the new
strict physical report. `reanalysis-provenance.json` records all original paths
and hashes; original failed reports are also copied under distinct names.
Both primary and independent reviewers inspected actual frames0045/0048 for AP
and0026/0029 for PX4. Independent AP review rehashed all75 copied/source pairs;
physical and visual re-audits reproduced the stored reports byte-for-byte.

## Source/test evidence and limits

Evidence directories include `hex-ap-arming-review-20260909`,
`hex-ap-stream-params-20260909`, `hex-historical-px4-review-20260909`,
`hex-retirement-review-20260909`, `hex-target-observation-20260909`,
`hex-ap-dataflash-20260909`, `hex-px4-final-review-20260909` and
`hex-ap-final-review-20260909` under `validation/`. Final AP observation/audit
suite: 59 sourced WSL tests passed. Source-era compatibility permits only
explicit archived/reviewed-current pairs, backed by actual packet/sensor replay;
unknown current/historical hashes still reject.

Raw native runs remain in their `/root/wksim-hex-flight-*` directories. Dense
readbacks/all frames remain in local validation; compact reports, hashes and
selected actual PNGs are delivered in Git. UE module remains the pinned
`15af1f6e400e77d6a8a207fd047b48b1d04c54260a5668312178051c119e6245`.

#67 AP cold reset is the remaining #25 obligation. No three-axis-six-rotor,
other vehicle, numerical R1/G6, Full, hardware, production-admission, or real-time
rate result is implied. All prior failed experiments remain intact.
