# One independent experiment through the product entry

Issues #12–#14, 2026-09-05. Recommended configurations now use the session protocol;
see [control restart and transition rules](wksim-control-session.md). Historical
legacy configurations remain explicit compatibility fixtures, not restart-safe inputs.
`tools/run-wksim.sh` selects one stack from strict
JSON, admits its pinned installed resources, owns the physics/Agent/FC/control
process groups, runs the public Prometheus position task, and writes `result.json`.
The entry does not call `validate_sitl_physics.py`, `NativeDDS`, or the diagnostic
mission. Its in-process rclpy task owns its executor and publishes only
`/uav1/prometheus/v2/setup` and `/uav1/prometheus/v2/command`; session observations
use `/v2/state` and `text_info`. Legacy profile retains the old unwrapped topics.
PX4 additionally uses its
native VehicleStatus read-only to wait for current-mode pre-arm health.

## Commands for the coordinator's isolated test slot

Run from Ubuntu-22.04 as root (or with permission to create network namespaces).
Both stacks have now passed real product runs; see the [first-wave report](2026-09-05_product-first-wave-report.md) and
retained failure samples. Use a new output root or run ID for each repetition:

```bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/arducopter-session.json \
  --output-root /tmp/wksim-runtime-runs
bash tools/run-wksim.sh Simulator/wksim_runtime/examples/px4-session.json \
  --output-root /tmp/wksim-runtime-runs
```

They may run concurrently in separate isolated experiments; this is not a joint scene.
Each creates `OUTPUT_ROOT/run_id`; an existing directory
is rejected without overwriting it. For a repeat, use a new output root or a new
valid `run_id` in a copied configuration. The examples are owned by the shared
configuration slice. CLI options are `CONFIG.json` and `--output-root PATH`.
`python3 -m Simulator.wksim_runtime.runtime --help` displays help without ROS/FC
startup. The shell entry creates new network, IPC and mount namespaces, loopback
and a private `/dev/shm`; it never joins a previous experiment's namespace.

The selected overlays are sourced in order: DDS `ros-install/setup.bash`, AP
candidate `ros-install/local_setup.bash` for ArduCopter, then installed Prometheus
`install/local_setup.bash`. Environment fixes FastDDS, domain77, localhost-only
discovery, and the pinned Agent libraries. All child working directories are
the new run directory; the repository is placed on `PYTHONPATH` for the physics
module, while preflight verifies that the control package resolves under the
selected installed product workspace.

Pinned resources:

| Resource | Selection |
| --- | --- |
| DDS workspace | `/root/wksim-dds-VxM6Ni` |
| Installed product | `/root/wksim-ros2-2egljG` session; historical `/root/wksim-ros2-0viK3f` legacy |
| AP flown candidate | `/root/wksim-ap-dds-yaw-state-4Wr27s` |
| AP binary SHA256 | `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5` |
| PX4 | `/opt/aerotwinsim/src/px4-d6f12ad1` |
| PX4 binary SHA256 | `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd` |

The shared preflight returns the exact previously verified model library and
build identity. Runtime uses that file; it does not compile or substitute a
model after admission. The fresh AP `fJUTtb` build is not substituted. The prior
flights are recorded in `validation/arducopter-dds-urq9hofr/result.json` and
`validation/px4-dds-epf9gukj/result.json`; they remain diagnostic baseline evidence.

## Lifecycle and result meaning

Readiness advances through admission → model identity → resource checks →
physics listening (its emitted ready record) → Agent UDP listener → actual FC
physics trace → public valid state plus command/setup subscribers → task.
The combined public readiness establishes the installed control node's state
path; mode/setup completion is still required separately before each action.
Without the optional explicit ground restart, the public input sequence is identical for both FCs: AUTO.LOITER, ordinary arm,
COMMAND_CONTROL, ENU `[2,3,3]` with yaw0, LAND, ground AUTO.LOITER. The last
input follows landing; no diagnostic transport outage is injected.

The task retains the baseline integration gates: takeoff≥2.5m, five boot-clock
seconds of height error≤0.6m and tilt≤0.35rad, waypoint error≤0.5m and
speed≤0.5m/s for two boot-clock seconds, then disarmed and |height|<0.3m.
Freshness and timeouts use monotonic wall time; dwell uses the current FC's
public `UAVState.header` boot time. Frozen/backwards source time cannot satisfy
dwell. These are existing control integration gates, not new numerical
equivalence budgets or a joint simulation clock.

Normal stop additionally requires fresh model ground truth and truth evidence
of reaching takeoff and the waypoint. Public UAVState has no landed bit;
the stop gate therefore corroborates valid, fresh disarmed public state with
the physics ground-height record. `safe_landing=true` is recorded only after
these checks. `status=pass` also requires cleanup success. Results preserve
preflight identities, normalized config, exact child argv/PID/PGID/log paths,
environment overrides, source/binary hashes, public inputs/events/final state,
truth summary, phases, return codes and cleanup errors.

Any partial startup failure, timeout or SIGINT/SIGTERM records failure and
`stop_kind=unsuccessful_isolated_teardown` unless landing was already verified.
It sends no emergency/disarm/native control command. It terminates only groups
created by this runtime, in reverse creation order; remaining members receive
SIGKILL after the bounded TERM wait. Failed teardown is not a safe landing.
No process-name cleanup, existing-process interruption, commit or installation
mutation is performed. Uncatchable termination (SIGKILL/host crash) cannot
produce a guaranteed final result or cleanup.

Optional `display_socket` adds all of `--state-socket PATH --run-id ID
--vehicle-id 1` to physics. The socket lives in a private UID-owned 0700 directory
under `/tmp` containing `run_id`; runtime creates the parent if absent and leaves
an existing valid consumer socket alone. The display relay is owned by another
slice. UE readiness is not a startup dependency; this entry does not change
network isolation or take ownership of a relay launched elsewhere.

## Checks actually executed for this slice

```bash
python3 -m unittest discover -s validation -p test_wksim_runtime.py -v
bash -n tools/run-wksim.sh
```

Eleven tests passed in Ubuntu-22.04: both launch plans/display identities, public
topic names/elapsed log time, finite
disarmed ground state, frozen public time, preflight refusal with zero children,
existing run protection, shared-namespace refusal, injected partial-start failure
cleanup, identical six-input task sequence, physical truth parsing and actual
owned dummy-process cleanup while an unrelated dummy process survives (some
checks are grouped in one test), plus the current-mode PX4 pre-arm health gate.
Main subsequently verified both formal-entry live runs with UE, and the final
integrated suite passed80 tests without skips. Exact evidence, source/binary
hashes, observed failure samples and cleanup are in the first-wave report.

MATLAB operations, joint clock/dropout/airborne-stop policy, plugin ABI and
numerical budgets remain outside this slice.

The second wave additionally verifies concurrent session-profile runs, explicit
pre-arm control process restart, old envelope/MOVE/ACK rejection and UE regression.
It passed 122 session-profile checks plus eight legacy preflight checks without
skips. See the [second-wave evidence report](2026-09-05_product-second-wave-report.md).
## 首次集成发现与修正

新增的可选 `mission` 配置在同一正式入口启用三航点/多航点任务及明确身份的本地取消，不改变未设置mission的旧回归路径。新用户操作、状态与取消处置见[任务契约](wksim-missions.md)；10次真实场景、185项检查、独立物理窗口和失败样本见[第三批报告](2026-09-06_product-third-wave-report.md)。后续任务暂停/恢复将预算明确为 `180+45×航点数` 活动墙钟秒，只扣除 paused 状态中等待新显式操作的时间；物理以 `--run-until-stopped` 运行，进程/传感器/执行器/状态新鲜度及各操作超时仍有效。旧任务仍为180秒。`cancelled`且物理落地的退出码为0，失败不能被解读为安全降落。

2026-09-05首个PX4正式运行在定位有效后立即请求解锁，原生ACK返回临时拒绝，飞控日志为“Resolve system health failures first”。该失败完整保留。正式任务现只读订阅固定PX4的VehicleStatus，等待AUTO.LOITER下新的、持续更新且pre_flight_checks_pass为true的状态后才通过Prometheus公开入口发送普通解锁。没有固定延时替代健康判断，没有强制解锁或关闭检查；AP流程不受影响。命令仍全部走同一公开入口；这项原生健康订阅只用于准入观察。
