# #35 PID 控制器选择与结果契约

2026-09-09。本文是 #88 的 bounded acceptance contract/report，复核既有 PID CLI 配置入口和实际 `external_pid` 结果。它不新增工作台 UI 验收阈值，也不改变 #35 原始 AC、#34 依赖或 Full 范围。

## 结论与边界

既有配置路径满足 #35 对“选择并显示实际 PID”的要求：CLI 使用 `--config <path>`，冻结 JSON 的 `controller` 字段为 `pid`；运行结果同时保存 `config.external_pid`、实际实现 `Simulator.wksim_control.position_pid.PositionPID`、解析后的配置、同轮 hover 标定和 `external_pid` 阶段结果。`controller` 不是只读标签：独立审计重算 PID 输出，验证 public `XYZ_ATT` 载荷、request/command 身份和 native attitude/thrust 消费，并拒绝测量窗内的原生位置/轨迹覆盖。

双栈物理 AC 已有两个独立 `recorded_evidence_pass`：PX4 与 ArduCopter 各自完成定点、圆轨迹、扰动、恢复和安全落地。`validation/pid-final-review-20260909/pair-acceptance.json` 的 `status` 为 `passed`，并确认五个共享核心源文件的当前字节 hash 同时匹配两份严格审计报告。关闭 #35 仍须由主代理确认 #34 父依赖及工单状态；本文不执行工单变更。

严格报告仍保留边界：没有 exact first native acceptance tick 或 publisher GID；native 日志和 mode 证据是采样记录；质量由源/模型 hash 绑定而非 runtime getter；没有 Full、工作台 UI、joint-rate、UDE/NE 或 #44 电机效率验收。`production_admitted=false` 仍是候选运行的真实状态，不能改写为生产准入。

## 选择入口与结果契约

入口必须是下列现有命令形态，且 `--config` 指向冻结配置文件；不存在隐含默认 controller：

```bash
bash tools/run-pid-flight.sh --stack {px4|arducopter} \
  --run-id <fresh-id> \
  --config Simulator/wksim_runtime/pid-flight-v1.json \
  --output-root /root/wksim-pid-flight-<fresh-id>
```

配置文件 `Simulator/wksim_runtime/pid-flight-v1.json` 的 schema 是 `wksim.pid-flight.v1`，原始字节 SHA256 为 `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`，并包含 `controller: "pid"`、固定 quad-X model identity、质量、PID gains、同轮 hover 标定策略、时序和三段冻结预算。

选择和传播要求如下：

1. `Simulator/wksim_runtime/pid_task.py:load_config()` 先验证配置字节 hash，再构造 `PIDConfig` 并调用 `select_controller()`；`Simulator/wksim_control/position_pid.py:select_controller()` 只接受 `pid`，UDE、NE、native、空值或未知值拒绝。
2. `tools/run_pid_flight.py` 要求 `--config`，在 admission、运行 `config.json`、`pid-protocol.json`、`pid-resolved-config.json`、PID trace 和 task report 中传播同一配置及协议 hash。
3. `PIDTask` 必须实例化 `PositionPID`，在测量阶段只发布 public `XYZ_ATT`；原生位置只允许出现在准备、恢复和落地阶段，并由 phase/`measured_external_pid` 标记区分。
4. 每个 PID trace row 必须带 controller、run/epoch/native generation、state 时间戳与 dt、reference、PID output、normalized collective、model identity、质量、校准值和 public request/command identity。接管、释放、authority loss、重启和时间不连续都必须复位；重复状态时间戳跳过，非法 dt 失败。
5. `result.task.external_pid.status=completed_pending_raw_audit` 只代表任务完成候选；只有独立审计 `status=recorded_evidence_pass` 才能作为结果证据。`observed` 或在线 `online_ok` 单独不能通过。

这份契约把现有 CLI 配置作为 #88 的配置入口证据。更广的工作台选择、参数展示和产品配置持久化属于 Full/产品台账，不在本票追加新的 UI 门槛。

## 固定来源与共享身份

PID 纯算法来源为上游 Prometheus commit `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`，原文件 `Modules/uav_control/include/Position_Controller/pos_controller_PID.h`，当前原始来源 SHA256 `4f75efa91ead6518cf778a2b3294621944e842274a4c1826577fd32c63823f9e`。初始化、reset、质量、重力、力投影、推力映射和有意边界见 `docs/2026-09-09-pid-controller-port.md`；纯算法 C++ oracle 已通过其固定容差。

`validation/pid-final-review-20260909/pair-acceptance.json` SHA256 为 `76e59aef5355540455dabb0e51e29e5c730bdf4f9ccf90cf2648a5d592dbd0ba`，其中共享核心文件 hash 为：

| 文件 | SHA256 |
| --- | --- |
| `Simulator/wksim_runtime/pid_task.py` | `ffbddccff7a1135bb6342c6883d8a7c22b2922fc16b0d2652e4d80a8fc073d62` |
| `Simulator/wksim_control/position_pid.py` | `96160fcfbabed9660c06599679cadaa4530a3ef7a60cc442432af549da2d7884` |
| `Simulator/wksim_runtime/pid-flight-v1.json` | `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0` |
| `tools/run_pid_flight.py` | `695e59e92700045e4d7ce297f9b11127939bf833855195edac27dc961d4c430f` |
| `tools/pid_physics.py` | `2e540fed821c07df63e83252d8288d03599da613e2386cadd0e5dd04abcb0775` |

两份严格报告的审计器 hash 均为 `f7a089c59d4bdf352ba0239ab6a32d645c177d371869f2035ef63fc8a00ee0b3`；运行 wrapper `tools/run-pid-flight.sh` 的 hash 为 `c772423deea8dde33914f05edef5777cf116c06cbae4c008f9accaea09ae8302`。每个严格报告还保存完整 `run-source`、安装包、固件、agent、模型库、argv 和 maps 身份，pair 检查只把上表五个跨栈共享文件作为最终同源门。

## 双栈实证

两次实际命令均使用 `Simulator/wksim_runtime/pid-flight-v1.json` 和新鲜 `/root/wksim-pid-flight-*` 输出根；命令原件见各自 `flight.json`。

| 栈 | run ID | 严格报告（SHA256） | 实际 result SHA256 | physics ticks | PID 重算 | native 关联 | 扰动 applied ticks |
| --- | --- | --- | --- | ---: | --- | ---: | ---: |
| PX4 | `pid-px4-final-source-20260909-02` | [`validation/pid-final-px4-20260909/strict-audit-report.json`](../../validation/pid-final-px4-20260909/strict-audit-report.json) (`a8f36504d69dc213ab2845eb1880a8292120b03c10330de15f05e33028e435fc`) | `9eee7ee89330e1720bd991fb186dbb7e6250cfffdca9f8f6877dc53f2180bb01` | 92888 | point 167 / circle 400 / disturbance 284 | 851 | 1000 |
| ArduCopter | `pid-ap-shaped-feedback-20260909-02` | [`validation/35-pid-arducopter/ap-shaped-feedback-20260909/strict-audit-report.json`](../../validation/35-pid-arducopter/ap-shaped-feedback-20260909/strict-audit-report.json) (`54500710ee49ba8513b48ab1a7d7e7374710eba5bd68fafd3c979735fc39d549`) | `5bdfec3476ece0e8b3b45f06b7474edb93ebf4d2a76da1a40f487d343d3c1b4a` | 126163 | point 128 / circle 308 / disturbance 220 | 656 | 1000 |

两份报告的状态都是 `wksim.pid.audit.v1 / recorded_evidence_pass`，终止均为 `landed_stop; all owned children reaped`。固定审计还分别比较了 PX4 511、AP 510 个 native motor 输出；两栈扰动都是四路输入恰好 1000 个 1 ms tick 乘 0.97，未把扰动解释为可配置电机效率。

完整固定窗口的审计最大值如下；circle 原协议只有位置和 yaw 门，没有独立速度门：

| 栈 | 阶段 | 位置误差 m | 速度 m/s | yaw 误差 rad |
| --- | --- | ---: | ---: | ---: |
| PX4 | point | 0.067212 | 0.030775 | 0.005244 |
| PX4 | circle | 0.125813 | 0.320587 | 0.010779 |
| PX4 | disturbance | 0.142362 | 0.149714 | 0.009135 |
| ArduCopter | point | 0.030136 | 0.018735 | 0.009853 |
| ArduCopter | circle | 0.112353 | 0.339233 | 0.002238 |
| ArduCopter | disturbance | 0.169224 | 0.220841 | 0.004113 |

这些值分别低于原始 point `0.3 m / 0.3 m/s / 0.15 rad`、circle `0.35 m / 0.15 rad` 和 disturbance `0.5 m` 事件窗及结束后 `8 s` 内末 `1.5 s` 连续 `0.3 m / 0.3 m/s / 0.15 rad` 的门槛。两栈均完成同轮 native hover median、level validation、native authority、public request 到 native target/执行记录关联、完整 1 ms 物理审计和地面终止。

## #35 原始 AC 对照

| 原始 AC | 结论 | 证据 |
| --- | --- | --- |
| 固定上游来源，记录初始化、reset、质量和推力映射 | 通过 | `2026-09-09-pid-controller-port.md`、`position_pid.py`、冻结配置、两份 `pid-resolved-config` 与严格 source identity |
| 配置/结果显示实际使用 PID，不能仅改标签而走飞控位置环 | 通过 bounded path | `--config` loader/selector、`external_pid` implementation、逐条 PID 重算、public `XYZ_ATT` 和 native position/trajectory override rejection |
| 双栈定点、轨迹、预声明扰动按冻结指标通过 | 通过 | PX4/AP 两份 `recorded_evidence_pass` 与 `pair-acceptance.json:status=passed` |
| 建立选择/reset 契约，供后续 UDE/NE 复用，原 ROS1 不改 | 通过 PID slice | selector 只接受 `pid`；PIDLoop/PIDTask 在选择、接管、释放、失权、重启和时间不连续处复位；上游 ROS1 文件保持只读来源 |
| 交付命令、版本/身份、预期与结果、失败/未验证边界 | 通过 | 两份 `flight.json`、严格报告、pair 文件、本契约的身份和限制记录 |

原始 AC 的父依赖 #34 仍由主代理在关闭 #35 前另行确认。本文不把严格报告的采样限制、`production_admitted=false` 或 Full/UI 未验收改写成生产完成。

## 失败和复核规则

后续复核必须保留两份严格报告及所有输入 SHA，不使用旧 `validation/pid-native-association-20260909/audit.json` 作为最终 PX4 同源证明；最终 PX4 证据是 `validation/pid-final-px4-20260909/strict-audit-report.json`。运行源码、配置、模型或安装包的行为变化需要新鲜 run 和新的 source/result hash。审计实现修正可对未改动的封存原始数据生成新报告，须保留旧失败并重新核对影响；不能修改旧数值窗口、预算或 evidence。

结论可写为：`#88 bounded configuration/result contract accepted; #35 dual-stack external PID evidence accepted, subject to parent #34 state and final issue review.` 这句话不等价于 Full、生产准入或 UDE/NE 完成。
