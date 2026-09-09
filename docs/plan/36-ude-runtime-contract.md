# #90 UDE runtime and independent audit contract

2026-09-09. #35 and #89 prerequisites are closed. The main agent explicitly
expanded the former two-file design envelope to the four runtime edits below,
one new independent UDE auditor, bounded shared-auditor parameterization,
new tests, this document and fresh evidence. This supersedes the earlier blocked
runtime design in this document; historical intake/evidence remains unchanged.
The implementation is an offline-verified runnable candidate. Real installed-stack
preflight has also passed for PX4 and ArduCopter. The first PX4 attempt failed
before controller updates because integer JSON coordinates reached float-only
ROS message fields; its raw evidence and clean teardown are retained.
The second PX4 attempt passed a new complete strict audit after the documented
native recovery boundary repair. AP and #36 acceptance remain pending; see
`docs/2026-09-10-ude-flight-acceptance.md` for current flight evidence.

## Frozen inputs

The original candidate file `Simulator/wksim_runtime/ude-flight-v1.json` is
unchanged: SHA256 `4bca3479d61f73d2ab8253191bdc41938904a43877f6b688c0c55e32567c4590`.
Its historical `scope` text is retained byte-for-byte for protocol compatibility;
current implementation status comes from this contract and fresh evidence.
`position_ude.py` remains unchanged at
`811f7bab2ae022563035005a76b5475665f15e9f49380ee201a7a64e61c0787b`.
Upstream is Prometheus `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`,
`Modules/uav_control/include/Position_Controller/pos_controller_UDE.h`, working
bytes SHA256 `ae0c9a300e435775b836f56667aadf90e4779db0b116218178d747bb50ce6699`.
The #89 original C++ oracle remains separate; this slice does not rerun or alter it.

The quad-X library SHA256 is
`cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`, mass 1.515 kg,
identity `sha256:` plus that hash. UDE uses per-axis Kp=.5, Kd=2, T=1 s,
disturbance limit=1 and tilt=8 degrees; upstream default tilt=20 degrees is not
the flight setting. Model/calibration/timing/point/circle/disturbance/envelope
fields equal the PID protocol, whose bytes remain at
`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`.

## Source ownership and interface

Exactly four runtime files change:

1. `Simulator/wksim_control/position_pid.py`: only `select_controller` changes.
   `pid` requires PIDConfig and creates PositionPID; `ude` requires UDEConfig and
   creates PositionUDE. Empty/default/native/NE/unknown values and wrong config
   types reject. The local UDE import avoids the shared-state type import cycle.
2. `Simulator/wksim_runtime/pid_task.py`: separately pins both protocols, builds
   the selected typed controller, preserves PIDLoop/PIDTask signatures and
   public XYZ_ATT publication, and binds controller/implementation/config to
   report, trace, calibration and event. No PID computation is called for UDE.
3. `tools/run_pid_flight.py`: the same CLI accepts the exact UDE config, admits
   it before launch, retains UDE implementation/config in run-source and source
   hashes, and records `external_ude` in admission/run config. Existing resource
   reservation, process identity checks, before/after hashes and watchdog remain.
4. `tools/pid_physics.py`: selected protocol and physics schema bind each run;
   original actuator packet/input16, applied input16 and every 1 ms step remain.

Verification ownership explicitly adds `tools/audit_ude_flight.py`,
`validation/test_ude_runtime.py`, and bounded changes to `tools/audit_pid_flight.py`.
The new auditor owns independent UDE equations. The shared auditor receives an
explicit immutable caller-selected controller argument (PID default); it never
chooses the expected algorithm from the run's claimed label and never mutates a
global profile. Native decoding, request association, fixed metrics and physical
budgets retain their existing semantics. Existing PID auditor CLI/schema/defaults
remain compatible. Unknown audit profiles reject.

For outlet and evidence compatibility, `PIDLoop`, `PIDTask`, their internal
`pid_*` members, `pid_` phase labels, `measured_external_pid` phase flag,
`pid_updates`, `pid-protocol.json`, `pid-resolved-config.json`, `pid-progress.json`,
`pid-trace.jsonl`, `pid-disturbance-revoked.json`, and the output directory prefix
`/root/wksim-pid-flight-*` remain shared legacy names. They do not identify the
algorithm. UDE is proved by `controller=ude`, PositionUDE implementation identity,
`external_ude`, frozen UDE SHA, UDE nominal/disturbance output and independent
recomputation. Event schema is `wksim.ude-disturbance.v1`, physics schema is
`wksim.ude.physics.v1`, and audit schema is `wksim.ude.audit.v1`.

## State, calibration and timing

Each new selection constructs clean state. The loop resets integral, last_output
and timestamp on selection/takeover/release/restart or native authority/timing
failure. Successful task lifecycle records selection, takeover_point,
release_point, takeover_circle, release_circle, takeover_disturbance,
release_disturbance in `observer_resets`; each UDE trace retains reset_count and
the last reset's reason, native baseline and zero integral. The independent audit
starts each stage from zero and rejects a contaminated or mismatched history.
Changing native generation/epoch fails; the task does not silently restart.

Duplicate State stamps skip without updating the observer. The first stamp
establishes baseline; later dt must be actual native elapsed time in (0,.2] s.
Nonfinite/nonpositive/backward/over-limit times clear state and fail. Reference
elapsed time is separately taken from the model physical cursor. No fixed 200 Hz,
wall-clock replacement, dt clamping or catch-up updates are introduced.

UDE clamps position and velocity errors to [-3,3], computes nominal acceleration,
uses the old integral for disturbance estimation, then accumulates e*dt only
where abs(e)<.5 and otherwise clears that axis. Moving reference retains history.
Nominal minus limited disturbance passes through original vertical force scaling,
per-axis tilt limits, current-yaw rotation and current body-Z projection.

Each stack independently collects native ATTITUDE_TARGET collective for 3 s,
freezes its median, then validates level attitude for 2 s (height change <=.3 m,
vertical speed <=.2 m/s). No previous-run/default hover is admitted. Mapping uses
m*9.8/hover, clamp [.1,1]; AP uses positive collective and PX4 FRD [0,0,-u].
Calibration samples, stack/model/mass and phase ordering are independently checked.

Fresh armed state, COMMAND_CONTROL, unchanged epoch/generation, AP GUIDED with
GUID_OPTIONS bit3 readback/native entry target, or PX4 OFFBOARD with verified
attitude/rates/allocation enabled and position/velocity/altitude disabled remain
required. One public request stays pending until public ACK plus native outlet
and two distinct native feedback stamps; timeout remains .2 simulated/2 wall s.
Preparation/recovery/landing native position helpers remain outside measurements.

## Physical budgets and failure behavior

Point [2,3,3], yaw0: 6 s settling + 4 s measurement; position <=.3 m,
speed <=.3 m/s, yaw <=.15 rad. Circle center [1.4,3,3], radius .6 m,
period 12 s, yaw0: 12 s settling + 12 s measurement; position <=.35 m,
yaw <=.15 rad. Analytic position/velocity/acceleration all feed UDE.
Disturbance: settle 6 s, declare origin, start=origin+2000 ticks, load >=1000
ticks before start; channels 0..3 multiply .97 for exactly 1000 ticks. Other
12 inputs stay unchanged. Error <=.5 m, recover within 8 s after event end,
final fixed 1.5 s continuously <=.3 m position/.3 m/s speed/.15 rad yaw.
Envelope remains distance <=4 m, height 1.5..4.5 m, per-axis tilt <=15 degrees.
Model step is .001 s; 360 s wall watchdog unchanged. No extra UDE overshoot gate
or post-observation tolerance/physical tuning is introduced.

Any failure retains original evidence, latches disturbance revocation and uses
existing bounded LAND/owned-process teardown. No retry/fallback/retuning is part
of a run. `observed` and online metrics remain insufficient for audited PASS.

## Exact commands

Offline verification from the repository root (no native processes):

```powershell
python -B -m unittest validation.test_position_pid validation.test_position_ude validation.test_pid_flight validation.test_pid_flight_audit validation.test_ude_runtime -v
python -B tools/run_pid_flight.py --help
python -B tools/audit_ude_flight.py --help
python -B validation/ude-runtime-implementation-20260909/check.py --output validation/ude-runtime-implementation-20260909/offline-run-01
```

The check requires a new output directory, records commands/source identities,
raw equation comparisons and unittest stdout/stderr. A Windows ROS message test
may skip; this is reported, not counted as installed ROS proof.

Following commands are now implemented, but require main-agent resource release,
the sealed WSL candidate resources and fresh stack preflight before actual flight.
Execute from the repository root in Ubuntu-22.04; each command runs one stack.
The IDs below must be unused. Preserve each stdout and every raw run artifact.

```bash
bash tools/run-pid-flight.sh --stack px4 --run-id ude-px4-90-01 --config Simulator/wksim_runtime/ude-flight-v1.json --preflight
bash tools/run-pid-flight.sh --stack arducopter --run-id ude-ap-90-01 --config Simulator/wksim_runtime/ude-flight-v1.json --preflight
bash tools/run-pid-flight.sh --stack px4 --run-id ude-px4-90-01 --config Simulator/wksim_runtime/ude-flight-v1.json --output-root /root/wksim-pid-flight-ude-px4-90-01
bash tools/run-pid-flight.sh --stack arducopter --run-id ude-ap-90-01 --config Simulator/wksim_runtime/ude-flight-v1.json --output-root /root/wksim-pid-flight-ude-ap-90-01
```

For each independent audit, source the exact admitted overlay (the same list is
returned as admission.setup_files), then execute the corresponding command:

```bash
source /opt/ros/humble/setup.bash
source /root/wksim-dds-VxM6Ni/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
source /root/wksim-ap-attitude-msgs-qOmnF9fT/install/local_setup.bash
source /root/wksim-attitude-control-x3_2v4wb/install/local_setup.bash
export PYTHONPATH="/root/wksim-attitude-audit-deps-g_2y8olg:$PYTHONPATH"
python3 -B tools/audit_ude_flight.py --run-dir /root/wksim-pid-flight-ude-px4-90-01/ude-px4-90-01 --output /root/ude-px4-90-01-audit.json
python3 -B tools/audit_ude_flight.py --run-dir /root/wksim-pid-flight-ude-ap-90-01/ude-ap-90-01 --output /root/ude-ap-90-01-audit.json
```

Audit output is exclusively created outside the sealed run. Exit0 means
`recorded_evidence_pass`; exit1 means rejected/incomplete with completed checks
and first failure retained. Expected double recomputation tolerance is 1e-10,
wire tolerance 1e-6, exactly as the PID double audit; these do not relax physical
budgets or replace the separate original C++ float oracle's abs2e-6/rel2e-7.
Input file hashes plus retained run-source, admission/postflight, actual binaries,
loaded model, installed Control, calibration samples and event bytes are sealed.
Audit reports distinguish ude_recomputed, native associations, physics and metrics.

## Remaining acceptance boundaries

Offline implementation evidence is in `validation/ude-runtime-implementation-20260909/`.
Real installed-stack preflight evidence is in
`validation/ude-runtime-acceptance-20260909/`: PX4 and ArduCopter both returned
exit0, `ok=true`, an empty reasons list and the exact UDE protocol/implementation.
Both reported `children_created=0`, `ros_nodes_started=false` and `flown=false`;
preflight admission does not establish flight or physical acceptance.
Both PX4 and ArduCopter UDE flights have passed full native, physical, equation,
calibration and cleanup auditing. Earlier failed attempts/reports remain
unchanged. See the dated flight acceptance document for exact report hashes and
remaining boundaries.
No exact first native acceptance tick or activity between sampled native log
observations is established. No Full/UI/joint rate/NE/motor-efficiency acceptance
is claimed. The UDE runtime and dual-stack physical slice are accepted; the
remaining product work is tracked outside #36.
