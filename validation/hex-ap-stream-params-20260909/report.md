# Complete AP stream-parameter review — proposal only

No production file changed. All files created/edited by this task are in this new evidence directory. The concurrent parent-owned PX4 run remains untouched. No simulation, native model, FC, ROS node, UE or serial resource was started.

## Complete census, not another one-parameter guess

The actual failed AP47 run `/root/wksim-hex-flight-ap-live-ap47-20260909-02/hex-ap-live-ap47-20260909-02` retained `logs/00000001.BIN`, SHA256 `8c8a1d8fd1fffa4ed9730451a4b78b0fe189db1da74e37dd1dcb9fd02c8f8861`. Offline DFReader inspection found **1,379 native PARM names**. Every one of the **33 proposed names exists** in this actual native log. All **30 unchanged names already equal the required values**; the only three old unavailable names are SR0_POSITION, SR0_EXTRA1 and SR0_EXTRA3. Their supported replacements exist but currently read 0 because the old SR0 defaults were ignored. The actual ARMING_SKIPCHK=0 guard passed before the latest failure.

Exact enumeration, expected/actual values and all source hashes/registration lines are in `native-parameter-inventory.json` and the generated `all-33-parameters.md`. This is native logging evidence, not a claim that the future DDS readbacks have run. Future ground readback must still validate every parameter and reject unavailable/mismatched responses.

## Source-backed names and semantics

Fixed AP source root remains `/root/wksim-ap-clock-stop-OXQqdR/src`, commit `1511f27194f1dcc3728270883047bdf022b3fd53`.

- `ArduCopter/Parameters.cpp:389` explicitly says SR0 through SR6 was here; line 590 registers GCS under `MAV`.
- `libraries/GCS_MAVLink/GCS.cpp:80` registers channel index 0 under `1`. `GCS_MAVLink_Parameters.cpp:156/166/185` register `_POSITION`, `_EXTRA1`, `_EXTRA3`. Therefore the exact native names are **MAV1_POSITION, MAV1_EXTRA1, MAV1_EXTRA3**, not guessed MAV0 or SERIAL0 names. The actual FC argv uses `--serial0 udpclient:127.0.0.1:14660`, with serial1/2 disabled.
- POSITION controls GLOBAL_POSITION_INT/LOCAL_POSITION_NED rate; EXTRA1 includes ATTITUDE and simulation/attitude-related messages; EXTRA3 includes AHRS, SYSTEM_TIME, EKF_STATUS_REPORT and sensor/status messages. The source declares each in Hz, range 0–50, reboot-required. Retain the intended **10, 10, 5 Hz** values and startup defaults/ground-readback workflow.
- Other parameters are supported at their current names: FRAME_TYPE/FRAME_CLASS (`Parameters.cpp:236/686`); MOT group at 459 and motor leaf PWM_MIN/MAX 107/116, BAT_VOLT_MIN/MAX 79/70; SIM prefix 424 and SITL RATE_HZ 549; ARMING prefix 240 and SKIPCHK 201; SERVO group 690, channel1..6 registrations 62..92 and MIN/MAX/FUNCTION leaves 37/46/172; AP_Vehicle DDS group 140 with ENABLE/UDP_PORT/DOMAIN_ID leaves 213/222/236; LOG group 274 with DISARMED leaf117. Their observed values all match the desired plan.

## Minimal versioned proposal

Inside the existing AP-only launch-plan branch, map exactly those three names to MAV1_* while preserving values and ARMING_SKIPCHK=0. Default/PX4 launch-plan output remains byte-value equivalent. Preserve both previous protocol files unchanged; add **hex-flight-ap47-v2.json** and point AP selection at it. Physical/time budgets are identical, differing only in schema label and plan identity.

- Proposed AP plan identity: `sha256:5c07a2d5c1e4b13580ae8b3ba43ce686324ec340adf2c12e9b4ffaabbba8486a`.
- Proposed AP47v2 protocol SHA256: `ce4f0aeb3c2de250aaf10c224f3fa43c326fcfcf8140c3746770879558f9df37`.
- Preserved AP47v1 SHA256: `cf9bfe890cc0a5e3c04d72dd0df5d1f9fd5bb18a2c60c588393266c542fac464`.
- Legacy/PX4 plan identity remains `sha256:319c5cba50eb11b81f70ac3ade707879c2fdba252335aa039674e93b9168e1a0`.

Reviewable copies are `hex_launch_plan_proposed.py`, `hex_candidate_proposed.py`, `hex_task_proposed.py`, `audit_hex_flight_proposed.py`, and new JSON. `proposed-runtime.patch` covers edits to the four existing files; the new JSON must be added separately after parent releases the runtime freeze. Nothing has been applied.

The audit proposal retains exact paired compatibility for **both** recipe versions already used by PX4: oldest5576/337e and current9e2a/ae6e, each paired explicitly with the proposed new-current recipe hash. The previously reviewed adapter pair is unchanged. No generic/future hash is accepted. The paired compatibility unit test must be updated from one pair per path to iterating the explicit tuple of pairs when this proposal is applied.

## Offline verification

`inspect_native.py` read only the retained BIN and source registrations. `propose.py` imports isolated proposed module copies and asserts complete default/PX4 plan equality, all77 PX4 parameter equality, all33 AP names present in native PARM evidence, other30 values unchanged, exact10/10/5 stream settings, all physical/time budgets unchanged, and positive/negative guards for every explicit source pair. Both commands exited0; logs and exact proposed source hashes are preserved in `proposal-checks.log`, `native-inspection.log`, and `proposal-result.json`.

After parent announces the PX4 run complete: apply the reviewed versioned patch, add the JSON and targeted stream-name/NOT_SET regressions, update paired-guard tests, independently audit both retained PX4 lifetimes against the explicit recipe pairs, and only then consider one fresh AP47v2 run. A native PARM name census is strong availability evidence but does not replace future DDS readback or flight acceptance.

## Applied after explicit parent release

Parent announced the PX4 run complete and released the freeze. The four proposed source files and new AP47v2 JSON have now been applied with the exact proposed hashes; tests were updated. `tools/run_hex_flight.py` remains exclusively parent-owned for the separate physics-first retirement fix and was not edited by this task. AP47v1 bytes still hash to `cf9bfe890cc0a5e3c04d72dd0df5d1f9fd5bb18a2c60c588393266c542fac464`.

Final combined WSL tests: **45/45 passed**, no skips (`applied-wsl-tests.log`), including actual PX4-03 full strict audit, all33 AP name/readback fixtures, absent/wrong stream-rate rejection, and paired-source adversarial guards.

The just-ended PX4 reset was also independently re-audited with `--require-cold-reset`: `recent-px4-reset-audit.json` passes identity and cold-reset linkage, with its recursively audited original PX4-03 parent passing. Its sole remaining rejection is the existing physical terminal failure caused by ConnectionResetError retirement; this task did not alter the terminal auditor or accept that failure. Thus both historical recipe generations are supported by explicit identity pairs, while unsuccessful physical retirement remains rejected.

Final source hashes are in `applied-source-hashes.json`. No new flight/UE/FC run was started by this task. Proposal-only sections above describe the preserved review stage; this addendum records the later explicitly authorized application.
