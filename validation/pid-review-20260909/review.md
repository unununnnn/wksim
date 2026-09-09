# Independent PID backpressure acceptance review

Reviewed baseline: `55d4e08bd5e1b2cba02e31dab1f8aa85efebbd68`.
PIDTask SHA256: `54eefcb81043992d1feb9c484510c51a1c1a8eea48ff5c3b1d16bf98bb4db695`.
Own session turn_context: model `gpt-6-astra`, effort `high`, service_tier null (existing setting retained).
No nested agents; no production, candidate, raw-run, GitHub, process, or parameter mutations.

## Confirmed findings

1. **AP exact telemetry quaternion matching blocks valid shaped requests.**
   `Simulator/wksim_runtime/pid_task.py:185` compares FC ATTITUDE_TARGET quaternion to the unshaped external command at `1e-6`. This requires a controller response that AP does not promise. The parent's first AP flight stopped on its first PID request with the public/native deadline; parent independently extracted equal thrust and a gradually changing quaternion from its retained telemetry.

   Verified against the actual admitted source under `/root/wksim-ap-attitude-hejigg76/src/`:
   - `ArduCopter/GCS_MAVLink_Copter.cpp:86`: ATTITUDE_TARGET uses `get_attitude_target_quat()`, `get_throttle_in()`, and current `AP_HAL::millis()`.
   - `ArduCopter/AP_ExternalControl_Copter.cpp:99`: accepted DDS target invokes `mode_guided.set_angle(..., thrust_norm, true)`.
   - `ArduCopter/mode_guided.cpp:771`: saves the requested quaternion and thrust; lines 785–791 log requested Euler angles to GUIA immediately.
   - `ArduCopter/mode_guided.cpp:1158`: running control invokes `input_quaternion()`; line 1163 passes thrust to `set_throttle_out()`.
   - `libraries/AC_AttitudeControl/AC_AttitudeControl.cpp:355`: enabled rate feedforward shapes attitude error through time constants and rate/acceleration limits. Only its disabled branch directly assigns desired quaternion at line 368.
   - `libraries/AC_AttitudeControl/AC_AttitudeControl_Multi.cpp:352`: `_throttle_in` is retained before motor angle boost/filtering.

   AP-only exact native CDR quaternion/thrust plus two distinct FC telemetry thrust observations is appropriate for pacing. Keep strict independent GUIA quaternion/thrust association unchanged. It is not proof that the FC accepted a particular attitude request when two requests share thrust.

2. **Delayed stale equal-value observations can release a newer request.**
   `Simulator/wksim_runtime/pid_task.py:173–185` filters native targets by arrival-list index and values, with no source-time lower bound tied to the request's consumed State. Targets sent before the request but queued until after it can satisfy this test. The subsequent telemetry filter uses that stale target's timestamp, so it can consume old telemetry too.

   A finite offline probe with request State 1.04 s, matching target timestamp 0.90 s and two matching telemetry timestamps 0.91/0.92 s returned `True`. All are within deadline by their local reception time. The exact matching source audit would normally reject such old CDR, so this finding does not invalidate the retained passing PX4 audit; it does mean online backpressure can release without any current observation.

   Store the request's native State timestamp and discard candidate native targets earlier than it, before selecting the target used as the telemetry lower bound. Keep value checks, two distinct timestamps, and current-State upper bound.

## Verified invariants and acceptance limits

- The finite probe confirmed duplicate telemetry timestamps cannot release the pending request, nor can two samples ahead of the current consumed State.
- Both physical age 0.201 s and wall age 2.01 s raise the original deadline exception even when public ACK and matching native observations are present. The bound is evaluated before ACK processing.
- Stage exit drains the last pending request through the same deadline guard before recording stage completion. Pump retains public freshness, fatal event, and physical envelope checks. Failure goes to recorded failure/landing handling.
- Current production Control has a separate steady timer and paced outlet (`node.py:49`, `:105`, `:622`), explaining why public acceptance alone cannot prevent target coalescing. The admitted native Control installation is separately sealed; current checkout files are navigation context, not a claim that an unsealed checkout was executed.
- `tools/audit_pid_flight.py:518–534` requires a distinct native CDR after public receipt and within adjacent consumed State timestamps, then a distinct matching execution-log row at or after that target and before the same interval end. It independently reconstructs PID equations and binds public CDR, native modes, physical ticks, motor samples, hashes, and terminal/cleanup conditions. Last-stage request has the explicitly existing `lo + 0.2` interval.
- Retained `validation/pid-native-association-20260909/audit.json` is `recorded_evidence_pass`, with 95,360 physics ticks, 1,000 disturbance ticks, 850 PID updates, and 512 motor comparisons. This review read the result and source logic; it did not independently rerun that large audit.
- Two FC observations are transport pacing. Exact first native acceptance tick, publisher GID, and unsampled native activity remain unproven as the auditor already states.

## Finite offline probe

The probe was first executed as a Python stdin script against the baseline source hash above, exit 0; its JSON output is retained in `initial-probe.json`. The same probe is provided as `reproduce_pending.py` and can be rerun with:

```text
python -B validation/pid-review-20260909/reproduce_pending.py
```

It uses only constructed Python objects and no ROS/native initialization. The initial source returns true for stale observation release and false for AP shaped-q release. Those two results should invert after the parent-owned fixes. No new full regression run was started while the parent owns production tests and flight validation.

Codebase Memory `index_status` returned ready, 50,865 nodes / 165,157 edges. The native symbol query returned no matches; current known files and excluded external native source were read directly. No graph completeness claim or refreshed index was needed for this read-only review. Initial guessed external source paths were corrected to the actual `src/` subtree; WSL lacks `rg`, so external literal searches used `grep`.

The two confirmed findings and native source evidence were sent to the parent before its next implementation/run. No additional blocker was identified for the proposed AP-only pacing correction plus stale-source filter, provided the unchanged strict native audit remains mandatory.

## Parent patch verification

After the parent applied its correction, the same finite probe was rerun with the command above, exit 0. Source SHA256 was `ffbddccff7a1135bb6342c6883d8a7c22b2922fc16b0d2652e4d80a8fc073d62`; output is retained in `patched-probe.json`. Stale target release changed to false and AP shaped-quaternion release changed to true. Current valid samples still release, duplicate/future samples still hold, and both deadlines still raise. The reviewed source keeps exact quaternion matching for PX4 and exact native outlet quaternion/thrust for both stacks. This verifies the bounded logic correction, not a new completed AP flight or acceptance audit.

The full parent diff was read, including its AP shaped-feedback, stale-source, changed-thrust, and PX4 negative checks. An extra finite assertion using the same shaped-quaternion fixture with `stack='px4'` returned false as required (exit 0). `tools/audit_pid_flight.py` SHA256 remains `f7a089c59d4bdf352ba0239ab6a32d645c177d371869f2035ef63fc8a00ee0b3`, exactly matching the earlier passing PX4 evidence manifest. The parent correction resolves both findings without changing the offline acceptance implementation, proof windows, controller equations, or frozen protocol. Full 47-test WSL success was reported by the parent; this independent review claims only the finite probes and direct patch/source verification described here.

## Final AP #87 decision: PASS for the frozen AP slice

Actual successful run: `pid-ap-shaped-feedback-20260909-02`, retained under `/root/wksim-pid-flight-pid-ap-shaped-feedback-20260909-02/pid-ap-shaped-feedback-20260909-02`.

The initial `ap-shaped-feedback-20260909/audit.json` is **command metadata, not the strict report**. Review found that `recorder.call('audit', ...)` overwrote the auditor output because both used that filename. The parent preserved existing files and reran the unchanged auditor against the same original run into `validation/35-pid-arducopter/ap-shaped-feedback-20260909/strict-audit-report.json`, with distinct `strict-audit-command.json` command metadata. That command exited 0 and the complete report says `recorded_evidence_pass`. Its SHA256 is `54500710ee49ba8513b48ab1a7d7e7374710eba5bd68fafd3c979735fc39d549`. No new AP flight was required for this evidence-retention repair.

Independent streaming verification (`verify_ap_artifacts.py`) checked:

- All 14 report input hashes against actual original files, all 28 retained executed source hashes against the raw run snapshots/result, and all 9 installed Control source hashes.
- Current and retained PIDTask hash `ffbddccff7a1135bb6342c6883d8a7c22b2922fc16b0d2652e4d80a8fc073d62`; unchanged auditor hash and frozen protocol hash recorded above; unchanged model library and native AP binary. The AP binary hash is `c1a38947d65aafa7a9051a850df46d9fd67c8f0723833bf3508245c81ab7b1c0`.
- Before/after candidate identity equality and actual native BIN hash `6c600942c000e7c3b79b7ab0a160e9326e50e4b8132b6232421f9fdd241c2036`.
- 656 unique request/command associations: point 128, circle 308, disturbance 220; all native target timestamps fall within the retained State intervals. Every online release has at least two distinct telemetry timestamps no older than its target/consumed State; each timestamp and exact collective is corroborated by a previously received retained MAVLink decoded record. This is additional pacing verification; strict original CDR and GUIA association remains the actual command proof.
- 126,163 continuous physics ticks and 126,163 captured AP actuator packets; exactly 1,000 disturbance ticks; 510 sampled native motor comparisons.
- Same-run measured hover `0.31346553564071655` from 121 observations; the report verifies separate level validation before PID. Full measured windows contain point 4,001, circle 12,001, and disturbance 11,001 ticks. Maximum position errors are respectively 0.0301363791 m, 0.1123534210 m, and 0.1692239502 m; the unchanged final recovery dwell passes.
- Result is `observed`, PID status `completed_pending_raw_audit`, `safe_landing=true`, `children_reaped=true`, `cleanup_errors=[]`, `source_unchanged=true`, `candidate_unchanged=true`, and stop kind `landed_stop`. Final public state is disarmed. Physics/FC/control exit 0; Agent exit -15 is the owned stop. At independent process inspection, physics PID 3689 and Agent 3690 were absent. PID 3697 and 3698 existed with different `/proc` start times from the retained original process records, so these are reused IDs, not surviving original children.

Actual verifier command, timings, exit 0 and full output are retained in `ap-artifact-verification-final.command.json`, `ap-artifact-verification-final.stdout.json`, and its stderr log. The first archival wrapper invocation incorrectly passed a Windows backslash path to WSL and failed before opening the script; its separate `ap-artifact-verification.*` files are retained, and the corrected invocation uses POSIX separators. A direct earlier verifier invocation also passed. No source, run data, firmware, model, parameter, or runtime process was changed during this final review.

The #87 issue body was read directly with `gh issue view 87 --repo unununnnn/wksim --json title,body,state`. Its frozen physical/native evidence completion conditions are satisfied by this successful AP candidate and the independently checked full strict report, with the preceding failure retained. No additional acceptance loophole was found after the two runtime fixes and report-path repair. This decision covers #87 only: the parent's final same-source PX4 flight and #35 aggregate closure are outside this final AP check. Full/UI/joint-rate/UDE/NE/motor-efficiency/hardware claims remain excluded; sampled logs still do not establish exact first acceptance tick, per-message publisher GID, or all activity between samples.
