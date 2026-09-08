# AP mixed native target silence contract v1

Frozen before execution on 2026-09-09. Scope: `ap_mixed_native_timeout_v1`.
This is an AP native DDS diagnostic followed by a new public recovery Task.
PX4 remains disarmed; both real FCs and both model workers participate in the
unchanged SceneClock/JointPhysics timeline. This is not a two-stack public
mixed mission, production admission, native pause test, or completion of #33.

The exact AP input is `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json`, SHA256
`1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c`.
The control manifest and its external SHA256 are mandatory inputs; no fallback
installation or rebuild is allowed. Admission verifies all fixed resources.

| Stage | Frozen measurement |
| --- | --- |
| Preflight | Actual DataFlash PARM: GUID_TIMEOUT=3.0 s, GUID_OPTIONS bits 4/5 clear, LOG_DISARMED=1. Record all FENCE/AVOID parameters. FENCE_ENABLE must be 0 in this first diagnostic; enabled fences require a separate reviewed contract. No parameter writes. |
| Native takeoff | Fresh advancing WksimState, valid navigation/home/origin, normal GUIDED/arm/takeoff services. Altitude 3 m, speed norm ≤0.5 m/s, altitude error ≤0.5 m for 2 sim s. |
| Mixed baseline | `map`, frame 6, mask 2531, ENU Vxy=(0.8,0.4) m/s, altitude=3 m, yaw=0 rad. After readiness and 2 sim s preparation, 3 continuous sim s: each velocity error ≤0.3 m/s, height error ≤0.5 m, yaw error ≤0.15 rad. |
| Last target | Change only altitude to 15 m for 0.2 sim s at 20 Hz simulated cadence. Stop sending every target; no zero velocity, full-position target, mode call or LAND in the observation window. |
| Timeout | Runtime waits 3.2 sim s from final publication, a conservative scheduling marker only. Offline evidence determines the actual strict `millis-last_update > timeout_ms` boundary from final GUIP type 7 acceptance and native boot samples; publication is not ACK. |
| Stop | At most 10 sim s preparation after the true native timeout boundary, then 3 continuous sim s with XY speed ≤0.25 m/s, height error to 15 m ≤0.5 m, XY drift from dwell start ≤1 m. Every model tick is independently audited. |
| Z discrimination | From terminal burst through the native timeout bracket, every model tick has absolute Vz ≤3 m/s; the bracket ends within 3.4 sim s of burst start. At the bracketed native timeout boundary the observed true altitude error to 15 m must remain >0.75 m, then decrease to ≤0.5 m. If already closer, report `inconclusive`, retain the original run and recover/land; never move the target or retune bounds after seeing results. The observed error remains mandatory; the design bound is not substituted for flight evidence. |
| Transfer | Destroy the diagnostic target publisher; require no pending service and zero target publishers for 0.2 sim s. Start one new sealed ControlNode and a never-used session_v1 Task. Matching one-time start offer includes run, scene, control epoch and token. Call unchanged `Task.recover_then_land()`; exact-one setup/command subscribers and existing freshness/revocation checks remain. |
| Finish | Public disarmed ground plus both final model heights <0.3 m. Stop at a four-tick boundary, normal model/recovery/control exits, clean owned groups, unchanged source/build identities. |

All phases retain the 900 wall second / 180000 tick caps, 0.5× JointRate and
its existing 100 ms lateness gate. Physical envelope is ≤100 m per position
axis, height ≤17 m, speed norm ≤5 m/s and roll/pitch ≤0.7 rad; PX4 stays within
0.3 m of ground and never arms. Native status/local freshness must be
≤2 wall seconds and source stamps must advance. Origin is finite immutable
metadata, recorded at the native 1000 ms delay (strict `>` in the actual
AP_DDS_Client loop); at 0.5× this is over 2 wall seconds and therefore is not
misused as a 2-wall-second dynamic freshness signal. Home/origin/position-reset
changes after normal arming fail. Initial native takeoff may perform one final
yaw alignment as detailed below; all resets after the mixed reference is
established fail. These are refusal guards, not bypasses for arming.

Before the first timeout run, the supervisor approved the 15 m terminal target
and 17 m envelope in place of the seam's unvalidated 6 m suggestion. Read-only
PARM evidence from nominal archive `joint-public-flight-zk5_nukn` gives
`WP_SPD_UP=2.5`, `WP_ACC_Z=1.0`, `GUID_TIMEOUT=3.0`, `GUID_OPTIONS=0`,
`FENCE_ENABLE=0`, `AVOID_ENABLE=3`. Actual sealed `AC_WPNav.h/.cpp` and
`AC_PosControl.cpp` use the SI WP names and jerk/overspeed shaping; those are
desired/correction limits, not a hard physical speed bound. The separately
measured ≤3 m/s truth guard and ≤3.4 s bracket instead bound a qualifying run
by 3.5+3×3.4=13.7 m, leaving ≥1.3 m design separation below 15 m. Actual
bracket error is still audited. No trajectory fitting or parameter write was
used. The existing public recovery Task's 30 sim second landing timeout stays
unchanged and can fail this run.

Raw CDR with the supported MessageInfo source/receive timestamps and joint
tick is retained continuously for AP targets/native state, PX4 status and
public session/events. The installed Humble Python binding does **not** expose
per-message publisher GID. It is marked unavailable, never reconstructed from
discovery. Strict discovered endpoint name/namespace/GID sets are retained:
one diagnostic target publisher, observed zero for 0.2 sim s after retirement,
then one new named Control publisher with a different discovered GID. This
establishes bounded graph/process attribution, not per-packet attribution. The
recorder deliberately has no public setup/command subscriptions. Requests
are retained by Task envelopes and Control events, preserving its exact-one
subscriber gate. The diagnostic node owns exactly one native GPS publisher.

The separate recorder node is never added to an executor. Its supported
`subscription.handle.take_message(type, True)` returns actual raw bytes and
the available timestamps. The ordinary native node retains its normal spin.
An isolated node/codec smoke passed. A subsequent raw loopback exposed that
the installed executor invokes a one-argument callback and discards the info
tuple, so the initial two-argument callback failed with TypeError. Direct
supported take inspection confirmed the timestamps-only metadata. The final
runner archives this installed executor source and SHA256; no executor, ROS
binding, ctypes ABI or installed package is patched.

DataFlash logs retain PARM, GUIP, ORGN and original bytes. GUIP type 7 confirms
accepted Pz/Vxy; ORGN and home resolve ABOVE_HOME to ABOVE_ORIGIN. No zero
GUIP record is expected when timeout clears velocity internally. Offline
audit requires target silence, actual native clock crossing, deceleration,
Pz convergence, continuously advancing model/clock evidence and explicit
new public takeover/landing. Live runtime completion alone is `observed`;
only a successful offline audit can produce a boundary PASS.

No pause/resume DDS service exists. Real fence rejection, pause via MAVLink,
reset injection, arbitrary airborne Control hot restart, avoidance effects,
and the public mixed-controller shutdown variant remain unsupported by this
runner. The first native phase starts without a ControlNode, so the later
epoch is newly created, not evidence that an old public task can resume.

Run in the isolated WSL profile, only when the host is released for physics:

```bash
bash tools/run-ap-mixed-timeout.sh --control-manifest /root/wksim-joint-control-OEvS3W/build.json --control-sha256 d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e
python3 -B tools/run_ap_mixed_timeout.py audit /path/to/retained/run --output /path/outside/raw/timeout-audit.json
python3 -B -m unittest discover -s validation -p test_ap_mixed_timeout.py
```

The lightweight checks exercise refusal/configuration and mathematical
classification only. They do not use mock flight as native behavior proof.

Implementation validation before handoff: five pure tests passed; shell syntax
passed; isolated real ROS node construction, 15 m GlobalPosition codec and
NaN-bearing SessionState codec passed. The final supported manual reader also
passed a real isolated DDS loopback (152-byte target CDR, actual source/receive
timestamps), observed one discovered publisher and then zero after destruction.
There were no FC/model/Agent processes in these smoke checks and no timeout
flight was run by this implementation task.

Revision before trial 03: trials `l_mg2f8w` and `qwnu_ksm` both failed during
native takeoff at ~2.64 m, with yaw_reset_ms changing 5375→48775 while home,
origin and position-reset counters stayed fixed. Raw failure logs are kept;
their DataFlash files end at 48.753/48.755 s, just before the reset, so those
files cannot identify its reason. Actual sealed AP_NavEKF3_MagFusion.cpp
controlMagYawReset and AP_NavEKF3_core.h define final airborne yaw alignment
above 2.5 m. The diagnostic now permits at most one yaw-only counter advance
at observed native height 2.5..3.5 m during the initial native takeoff, with
all other identities unchanged. It records old/new counters and source boot
time. Offline acceptance additionally requires the actual native MSG
`in-flight yaw alignment complete` within 200 ms of that counter; absence
fails this classification. The 3 m / ≤0.5 m/s / 2 s takeoff hold finishes before
freezing the mixed reference. No public ControlNode/Task exists in this
initial phase. Once mixed preparation begins, every reset again fails;
production ControlNode and public Task reset/revocation rules are unchanged.
