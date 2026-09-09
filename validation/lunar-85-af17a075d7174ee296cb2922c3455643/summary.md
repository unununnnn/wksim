# #85 — 35-raw-auditor

Implemented `tools/audit_pid_flight.py` and `validation/test_pid_flight_audit.py`. Only these two source paths and this fresh evidence directory belong to this delivery. The shared active file and other tasks' files were not edited or included.

## Verified implementation

- Independent PID equations recompute native dt, stage takeover integral reset, original error discontinuities, moving-reference reset, integrals, acceleration/limited force, current-attitude projection and per-stack collective. The auditor does not call PositionPID, PIDLoop, reference, or evaluate_rows. Online labels cannot produce acceptance.
- The frozen protocol bytes, retained run-source hashes, actual admitted binaries/model/control, process maps and postflight seals are checked. The physical budget SHA remains `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`; model library SHA remains `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`. Full source identities are in `source-sha256.json`.
- Same-run MAVLink hover samples/median, three-second stable calibration and two-second level validation are recomputed against raw physical output. Calibration stack, mass and model are bound to the frozen run.
- Original public CDR is decoded using the existing #34 codec verifier, compared with retained requests, and joined to consumed state, request/command IDs and PID output. Every trace request requires a distinct native attitude CDR and a distinct matching native execution-log observation. Recorded native position/trajectory, setup and non-attitude public overrides inside measured stages are rejected. Native motor logs are compared with original actuator inputs.
- Full 1ms physical start/group/step/end continuity, original actuator packet decoding, held inputs and exact canonical disturbance declaration are verified. Exactly 1000 integration intervals change channels 0..3 by .97; other channels remain unchanged. Missing input, late load, duplicate integration, changed identity, revocation and missing terminal reject.
- Point/circle windows and final disturbance recovery dwell are fixed from the frozen configuration. Every 1ms state is checked, including envelope checks during settling. No shifted/best-window search and no physical tolerance increase.

## Exact commands and observed results

From `C:/Users/PC/Documents/odid编译/wksim`:

```powershell
python -B validation/lunar-85-af17a075d7174ee296cb2922c3455643/collect.py
python -B -m unittest validation.test_pid_flight_audit validation.test_pid_flight validation.test_position_pid -v
wsl -d Ubuntu-22.04 -u root -- python3 -B -m unittest validation.test_pid_flight_audit validation.test_pid_flight validation.test_position_pid -v
```

Both Windows and WSL: **42 tests passed, zero skipped**, including 16 new audit tests. Exact executable argv, cwd, timestamps and return codes are retained in `commands.json`; stdout/stderr are separate unmodified logs. The collection script refuses existing output files; copy it to a fresh permitted evidence directory to repeat collection.

Validation includes 1,000 independent equation comparisons against the existing candidate (500 per stack), analytic hover/reset checks, actual generated MAVLink frame/CRC decoding, full fixed-window synthetic positive evidence, AP/PX4 native association fixtures, and mutations for dt/reset, false PID, wrong hover/epoch, missing raw state/ack/stage, single-tick position/speed failure, native position override and missing native execution logs. Native execution fixtures deliberately mock log readers and do not represent a flown vehicle.

`physics.synthetic.jsonl.gz` and `packets.synthetic.jsonl.gz` retain a complete synthetic 3000-tick AP input trace. `physics-positive.synthetic.json` records exactly 1000 changed ticks. `negative-results.json` retains six independently rerun raw failures. Other mutations are in the tests and test logs.

The actual CLI was also invoked on `observed-only.synthetic/result.json`, which claims `observed` and `online_ok=true` but lacks evidence. It exited **1**, producing `observed-rejection.json` with status `rejected`. It did not promote either label to PASS.

Initial development test run: 10 tests succeeded and one test errored because its mutation attempted to edit a tuple in a Python fixture. The fixture now serializes through JSON, matching the actual trace format. No controller or physics-budget change resulted. Subsequent final 42-test runs passed.

## Audit entry for future real runs

Run offline in the same admitted WSL ROS/message overlay as the target run. This does not start a ROS node or flight:

```bash
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-ap-attitude-msgs-qOmnF9fT/install/local_setup.bash
source /root/wksim-attitude-control-x3_2v4wb/install/local_setup.bash
python3 -B tools/audit_pid_flight.py --run-dir /root/wksim-pid-flight-ID/ID --output /absolute/new-audit.json
```

`ID` and output path must be replaced by the actual completed run and a new file outside its sealed directory. The preceding command shape is a future entry, not a claim that a run with that name exists. The auditor validates decoder identities against the run admission.

Schema: `wksim.pid.audit.v1`; output includes status, completed check sections, input/source hashes, per-request associations and the first concrete failure. Exit 0 is `recorded_evidence_pass` for the declared recorded-evidence scope; exit 1 is rejected/incomplete. Output creation is exclusive and output inside the sealed run is forbidden. Partial successful checks survive later failure. Never treat this return code as Full acceptance.

## Boundaries and handoff

No completed real PID result was found in the checked `/root/wksim-pid-flight-*` run directories. No FC, model, ROS node, SITL flight or UI was launched for #85. The raw ROS/CDR + FC-log end-to-end route on actual PID flight data remains to be exercised by #86/#87; this delivery proves the implementation and explicit synthetic rejection behavior, not either flight's success.

Native logs/mode messages are sampled. The auditor refuses a missing per-request execution observation, even when online control says it succeeded; it does not interpolate missing native execution. Native timestamps, receiver monotonic times and physical reference cursors remain distinct. Exact first native acceptance tick, per-message DDS publisher GID and activity between native observations remain unverified. The strict per-request association may reject a real run whose log rate loses commands; retain that failure and review evidence acquisition rather than relaxing physical budgets or treating online_ok as proof.

Mass is source/hash-bound, not runtime getter readback. No claims about UDE/NE, UI selection, joint rate, Full, #44 motor efficiency, or the unchanged R1/RateUnmet failures. Only child #85 is eligible to close; #35 and #86/#87 retain their original acceptance requirements.

Execution identity: this work was performed in the main task without subagents. The supplied runtime instructions identify GPT-6, but this interface does not expose a verifiable backend model ID or effective reasoning-effort value. Requested `gpt-6-astra` / `low` is therefore **not independently verified**, and is not falsely reported as measured metadata.

No owned long-running process remains. Next step: run the authorized #86 candidate once with fresh run identity, then invoke this auditor on its sealed result and retain its complete failure or recorded-evidence output.
