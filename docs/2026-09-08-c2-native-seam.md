# 混合轴与轨迹的原生 DDS 接缝预检

2026-09-08，只读预检，项目 HEAD `d1006cac0cc7b5c881e4999edec6ca114f80dec5`。未启动 SITL/UE，未构建固件，未更改消息、产品源码、pin、契约、参数、阈值或 Issue。本文使用本轮任务简称“C2”；2026-09-07 批次提案把 #33 混合轴/轨迹列在 C1，不在此重新编号。范围对应 `docs/plan/tickets/23-mixed-trajectory.md`（GitHub #33），其 #32 前置和实际验收状态不因本报告改变。

结论：PX4 已有原生输入可表达 XY 速度/Z 位置和位置+速度前馈轨迹。批准 AP 固件的两个 DDS 运动输入均不能执行这些组合；AP 的完整 P+V 轨迹所需字段已经存在于 GlobalPosition schema，最短缺口是 DDS→ExternalControl 的固件接线。真正的 XY 速度/Z 位置还需要 AP Guided 对轴语义的显式扩展，不能把全位置+速度目标或外部 Z PID 冒充混合轴。

## 版本与取证边界

- 本子代理实际 JSONL `C:/Users/PC/.codex/sessions/2026/09/08/rollout-2026-09-08T15-24-45-01a07fb0-c02a-7b80-89c9-daa96621ea46.jsonl` 的 `turn_context` 已读回 `model=gpt-6-astra, effort=low`。没有嵌套委派。
- 已读根/context map、wksim AGENTS/CONTEXT、指定票据/批次提案、五项批准记录和 C1 报告。当前两份适配器与 shaping 均直接读取。
- 首次 Codebase Memory `list_projects` 返回 wksim 项目/root；`index_status` 为 ready、50,515 节点/163,780 边。精确覆盖时间 `2026-09-07T14:21:06Z`，两适配器 `no_recorded_issue` 但 `metadata_changed`。因此没有用旧图推断新增调用结构；本次已知文件直接读，外部 WSL 固件按 `docs/codebase-memory.md` 明确的图外路径直接读取。未为文档/已知文件做全库索引。下一次依赖变化后结构的图查询仍须刷新。
- AP 实读根 `/root/wksim-ap-clock-stop-OXQqdR/src`，提交 `1511f27194f1dcc3728270883047bdf022b3fd53` 加批准补丁 0001/0002/0003；manifest SHA256 `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a`。manifest 记录固件 SHA256 `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de`。
- PX4 实读根 `/root/wksim-px4-state-ONa1Kw/src`，提交 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` 加批准候选修改；manifest SHA256 `d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6`。manifest 记录固件 SHA256 `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a`。
- 下列关键外部源均重新 SHA256 并与各自 manifest `source.files` 匹配；这证明本次源引用与批准清单一致，不是本轮运行/加载证明。

| 源（相对于上述各 FC 根） | SHA256 |
| --- | --- |
| AP `libraries/AP_DDS/AP_DDS_ExternalControl.cpp` | `59c9e20ca9db9a8cfbbbe315000af52643a92d80d6117e52863d8b7ba23f7c25` |
| AP `ArduCopter/AP_ExternalControl_Copter.cpp` | `cb3dd63da635063805b983cd4ae06c921bc39f5c79454b625c273cb3fece1e09` |
| AP `ArduCopter/mode_guided.cpp` | `954836c2a3bb1418ed81fd0178abf5521e140a45fc27543896b3ea6d06df0a08` |
| AP `libraries/AP_DDS/Idl/ardupilot_msgs/msg/GlobalPosition.idl` | `945d2756cc07bfce84af46efb9e4c4d23634b14d2a3adee91217427422f4bb76` |
| AP `libraries/AP_DDS/AP_DDS_Client.cpp` | `e41fd119b40aac34d357b41f9588e04f5ea95b9a88ee0175968ec5341b6401c1` |
| AP `libraries/AP_DDS/AP_DDS_Topic_Table.h` | `43c1eb18a5c488a62281fbdcf38b97dcec5f869f00abcd6f5eb418824bd97d75` |
| PX4 `msg/versioned/TrajectorySetpoint.msg` | `d5671f1a094a9183e2337171ab738ae3395442e024b58aaacbf51c2b0188d5e2` |
| PX4 `src/modules/mc_pos_control/PositionControl/PositionControl.cpp` | `6c2eb1132c41b9cb8c87a1def69278327d45117553e88b2ece6944f3d5e96f08` |
| PX4 `src/modules/mc_pos_control/MulticopterPositionControl.cpp` | `0e025b28e1dcd40f8e861b64668b1bafc502b3223277a29b76564f8997dcbeac` |
| PX4 `src/modules/uxrce_dds_client/dds_topics.yaml` | `7e9c730d45b22af92acfebbb81cb5de4e4a69ac0ca46b012b71ed8fa5c89cbc0` |

仓库当前 `native_px4.py` SHA256 `de40ae6175c7e1b23908a791b077b310da81a8d5c264ff4af2620a733a4b2fe6`，`native_arducopter.py` `63255819c43e2683c3125c0e7e07e5622f676c78bc83ce744cd60e9d9caa42dc`，`shaping.py` `56782d96f9fc6f7df3ddadf80cd8c09f474af81c5c183d20d3d26c2f9e66bc69`，路径均为 `ros2/src/prometheus_control/prometheus_control/`。

## 能力逐项判定

| 语义 | PX4 当前原生路径 | AP 当前批准原生路径 | AP 最短扩展层 |
| --- | --- | --- | --- |
| XY 速度 + Z 位置 | 支持：P=(NaN,NaN,z)，V=(vx,vy,0)，各轴有效性独立，XY 成对 | 不支持：Twist 无位置字段，GlobalPosition handler 拒绝部分位置及所有速度 | DDS handler + ExternalControl 接口 + Guided 显式水平速度/垂直位置执行；已有 GlobalPosition mask 可表示所需轴，不强制新 wire schema |
| XYZ 位置 + XYZ 速度前馈 + yaw | 支持；同一 TrajectorySetpoint 携带 P/V，内部位置校正与 V 前馈相加 | schema 有字段；DDS handler 拒绝，适配器也拒绝；Guided 内部已有完整 P/V 执行 | 最小为现有 GlobalPosition 完整 P/V 掩码的显式固件接线；无需先扩展 schema 或改 Guided 控制律 |
| TRAJECTORY 加速度前馈 | 固件能加到速度控制输出；当前 Prometheus shaping 故意不发送轨迹加速度 | DDS handler 拒绝；Guided P/V/A 内层已有接口 | 第一切片显式“不执行”；若未来启用，另改输出契约和批准 profile，不借字段存在宣称生效 |
| 轨迹 yaw 角 | TrajectorySetpoint.yaw，适配器 ENU→NED | GlobalPosition.yaw 已有，当前位置+yaw 补丁可执行 | P/V 扩展沿用显式 yaw 转换 |

PX4 证据：`native_px4.py:233` 的 send 将 None 经坐标转换成为 NaN，发布 OffboardControlMode 和 TrajectorySetpoint。固件 `dds_topics.yaml:140,158` 有两入口；`MulticopterPositionControl.cpp:438,547,574` 读取、传入并执行设定值；`PositionControl.cpp:124` 把 P 误差速度加到已有 V，`:140` 把速度控制输出加到已有 A，`:224` 要求各轴至少一项有限且 XY 成对。`TrajectorySetpoint.msg:14` 的 jerk 仅日志，不是控制前馈。

AP 证据：`AP_DDS_Topic_Table.h:373-408` 的运动入口为 `rt/ap/cmd_vel` / TwistStamped 与 `rt/ap/cmd_gps_pose` / GlobalPosition；`AP_DDS_Client.cpp:939-967` 分别调用两个 handler。`AP_DDS_ExternalControl.cpp:19-33` 明确要求 IGNORE_VX/VY/VZ、IGNORE_AFX/AFY/AFZ、IGNORE_YAW_RATE 全设定，禁止部分位置；`:58` 起速度 handler 只把 Twist 线速度和角速度 z 转成 NED。`AP_ExternalControl_Copter.cpp:16-25` 最终调用 `set_vel_NED_ms`，不会携带 Z 位置；`:37-44` 的位置+yaw 仍是 destination 路径。不能交替发布两个 topic 来“叠加”控制，它们设置不同 Guided 目标/子模式，未形成原子混合输入。

AP 内层：`mode_guided.cpp:612-648` 的 `set_pos_vel_NED_m` / `set_pos_vel_accel_NED_m` 已有 fence 检查、yaw、目标保存和时间更新；`:912-964` 的执行分别向 NE 和 D 输入 P/V/A，并在原生超时后清零 V/A、停止速率偏航。当前该接口没有每轴 position-ignore 参数，也不以 NaN 作为 PX4 式失活轴契约。`:935-949` 有依赖稳定选项的 NE 路径，但全局参数改变会影响其他 Guided 行为，不能偷偷改 GUIDED_OPTIONS 或给任意 XY 锚点来宣称未激活位置轴。

`GlobalPosition.idl:16-33,38-57` 已有位置/速度/加速度轴 mask、latitude/longitude/altitude、velocity、acceleration_or_force、yaw，因此上述有限切片不必新增 schema。若要以精确 local-ENU XYZ 直接传输、避免经纬度量化/原点转换，才有理由另加明确命名并版本化的本地目标 schema/IDL/ROS overlay；当前 GlobalPosition 不应被重新解释成局部 XYZ。

## 可落地的最小垂直切片（建议，未实施）

1. 先做双栈完整 XYZ P+V+yaw 固定轨迹，明确 A 不执行。PX4 保持现有线协议；AP 在独立候选补丁中只接入此一个严格 mask 组合，经 GlobalPosition 的真实地理坐标/高度帧换到 EKF-origin NED，再由新增 ExternalControl 方法调用现有 Guided `set_pos_vel_NED_m`。沿用 readiness、fence 和 native timeout。不要把 home-relative 的坐标直接当 EKF-origin 坐标。
2. 当前 AP `native_arducopter.py:198-212,225-270` 仍按能力门拒绝 TRAJECTORY 和混合组合；仅在新固件/manifest 已验证且显式 profile 开启后，放行新增 P+V mask。原 profile 的拒绝和 pin 保留。应记录实际 DDS P/V/yaw、mask、时戳、身份及真值，不将无 ACK 的 setpoint 发布称为飞控受理；现有 AP client 对 handler 失败仅有 TODO，不能拿发送成功代替执行证据。
3. 离线边界先验证完整 P/V、坏 mask、非有限值、坐标/高度转换、yaw、原 profile 拒绝且无副作用；保留原命令/输出差分回归。`shaping.py:97-101` 的轨迹 A 只校验后不发送，此行为不修改。随后主代理预约真实资源、预先冻结票据要求的轨迹误差/驻留/恢复数值，再实施真实双栈轨迹和停止/恢复验证；本报告不臆造新阈值。
4. 再做真正 XY 速度/Z 位置：新增明确 Guided 轴 profile，使 NE 使用速度路径、D 使用位置路径，生命周期/超时原子更新。可复用 GlobalPosition 的“忽略 latitude/longitude、保留 altitude、启用 VX/VY”掩码，但在接入前应完整定义 VZ/A/yaw mask 与零保持切换规则。只填真实激活语义；若输出修整切换到全位置保持，执行层同步切换，不复用旧锚点。
5. 不新增外部 Z PID，不积分 XY 速度造全位置轨迹来伪装混合轴，不把未激活轴填 0。原 shaping 的历史速度死区/静止轴修整与本次新支持层分开审计，不能据其存在替 AP 兜底缺失的轴模式。

因此，在不改当前批准固件/pin 的范围内，可做 PX4 侧真实混合/轨迹验证和 AP 拒绝边界验证；不能宣布双栈 #33 完成。完整 P+V 是最小 AP 固件增量，混合轴是后续明确的内部模式增量。任何候选构建和准入提升仍需按既有流程获得源/二进制/运行证据，本文未执行这些步骤。
