# Independent UDE runtime pre-run review

Decision: **no algorithm/runtime blocker found; one operational documentation correction is required before using the advertised PX4 audit command.** This supports scheduling the existing read-only preflight and bounded future UDE stack runs after main-agent review. It is not UDE native/physical acceptance or closure of #36.

The reviewer read the UDE runtime contract, implementation report, four runtime changes, shared auditor changes, new UDE auditor/tests, unchanged PositionUDE implementation and original Prometheus UDE header. No production source was edited, no UDE/native/FC/ROS/UE process was launched, and no nested agent was dispatched. During the main agent's quiet rate diagnostic window, all local tests/compilation and file operations were paused. Checks resumed only after its release; committed worker `800666c8eb46794821a3cfcb70cf1b102d287d3f7611ac0dfdf96c40d49b6d2b` and absent temporary worker_timing helper were independently confirmed.

## Actionable finding

**[P2] Exact PX4 audit shell omits private pyulog dependency.** `docs/plan/36-ude-runtime-contract.md:160–162` sources the five admitted ROS overlays and immediately invokes `audit_ude_flight.py`. A fresh WSL shell with exactly those overlays gives `importlib.util.find_spec('pyulog') == None`. `audit_attitude_flight.py:308–309`, reached by the shared native PX4 audit, imports pyulog directly. Therefore the documented invocation will fail at native log decoding unless the caller happens to inherit an extra path.

Use the already installed `/root/wksim-attitude-audit-deps-g_2y8olg` in PYTHONPATH or document the existing wrapper that adds it. No installation, source algorithm change or physical budget relaxation is needed. Both independent legacy re-audits below used that retained private dependency explicitly.

## Verified code behavior

- `select_controller('ude', UDEConfig(...))` creates PositionUDE; PID and UDE reject wrong configuration types, and empty/NE/native/unknown selections reject. PositionUDE does not call PositionPID computation; shared state/reference/thrust types are used without a controller fallback.
- Original C++ and online/independent UDE equations agree: clipped position/velocity errors, nominal acceleration, old-integral disturbance estimate, subsequent per-axis integral accumulation/clearing, disturbance clamp, nominal-minus-disturbance, vertical force scaling, per-axis tilt cap, current-yaw attitude conversion and current body-Z projection. The independent auditor owns its equations and does not import the online implementation for expected values.
- Genuine UDE output includes nominal/disturbance terms and is published as the existing public XYZ_ATT envelope. Native AP/PX4 adapters and their previously reviewed backpressure behavior remain shared and unchanged. AP shaped quaternion feedback remains a pacing boundary; strict native GUIA/ULog association is still required.
- Selection/takeover/release/failure reset paths clear the UDE observer. Successful trace reset counts 2/4/6 and final seven-entry lifecycle history align with the actual execution order; each stage independently recomputes from zero history. Duplicate State timestamps do not integrate; invalid/backward/over-limit native time and authority loss reset and fail without dt clamping, catch-up or automatic restart.
- Frozen UDE protocol `4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590` and PositionUDE source `811f7bab2ae022563035005a76b5475665f15e9f49380ee201a7a64e61c0787b` are unchanged. PIDTask remains at the frozen `4a04522972cfa0a690ce76433cccad35d581eb43957b57302894347cdaa4a954`. Model/calibration/timing/point/circle/disturbance/envelope fields retain the PID protocol values; UDE gains are explicit, including flight tilt 8 degrees.
- The selected protocol/controller reaches admission, config, runtime source inventory, task output, resolved calibration, event schema/hash and full physical header. UDE files are included in run-source before runtime; later imported source must match admission or that sealed inventory. All original raw actuator packets/inputs and 1 ms states remain available for independent event/physical checks.
- Shared audit selection is caller-controlled: default PID CLI stays PID; the UDE wrapper explicitly requests UDE. Run labels do not choose the expected equations. No mutable global audit profile is introduced. UDE identity, reset, output and protocol checks reject relabelled PID evidence.
- Existing legacy `pid_*` filenames/phase labels are explicitly documented as naming compatibility, not proof of which controller ran. The exact controller, implementation, UDE fields and independent equations carry that proof.

## Independent validation

After the quiet window ended, the sourced WSL suite ran:

```text
bash validation/lunar-65-astra-20260909-01/run-audit.sh -m unittest validation.test_position_pid validation.test_position_ude validation.test_pid_flight validation.test_pid_flight_audit validation.test_ude_runtime -q
```

**71/71 tests passed, zero skips**, in 3.032 seconds. This includes the actual generated ROS State test, 1,200 synthetic UDE equation comparisons, selection/reset/authority negatives, event/physics guards and synthetic native association tests. They do not substitute for a UDE flight.

`recheck_pid.py` separately reran the current default shared auditor against both untouched accepted PID lifetimes, using each run's exact admitted overlays and the retained pyulog dependency:

| Original PID run | New independent verdict | Recomputed updates | Report SHA256 |
|---|---|---|---|
| pid-px4-final-source-20260909-02 | recorded_evidence_pass | point167 / circle400 / disturbance284 | `493eb8d946a4fbf0ce90bd372193ad2d465da0d188680abc94da373329b4df98` |
| pid-ap-shaped-feedback-20260909-02 | recorded_evidence_pass | point128 / circle308 / disturbance220 | `945c83a258da31c4f00bab421692ef2c483229c6cf500188656f38eb873a21dc` |

Fresh reports are `px4-legacy-pid-audit.json` and `ap-legacy-pid-audit.json`; exact command/timestamp/return code and separate output logs are beside them. Originals were not changed. These full raw/native/calibration/physics passes confirm legacy PID compatibility beyond API signatures and synthetic fixtures. `git diff --check` also passed for the reviewed runtime/shared-auditor changes.

## Remaining boundary

Real UDE installed-stack admission, same-run measured hover, actual PX4/AP UDE flight, full native request association and fixed physical budgets remain unverified until the scheduled #91/#92 runs. A candidate or observed result alone is not acceptance. Existing sampled-log, unknown exact-first-acceptance/publisher-GID, Full/UI/joint-rate/NE/motor-efficiency and hardware boundaries remain unchanged. Resolve the documented pyulog path and preserve source pins before scheduling; no further code blocker was found in this review.
