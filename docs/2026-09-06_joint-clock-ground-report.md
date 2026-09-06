# 双飞控共同时间地面握手验证

2026-09-06 JST。此轮属于 [#8 决策前允许的有界本机验证](https://github.com/unununnnn/wksim/issues/8)，不是已批准的生产联合调度，也不关闭 #19/#20 或 G2。

## 结论

两次全新隔离启动均通过：同一调度进程让两个独立进程中的真实生成模型各执行 **10,004 个 1ms 步**；AP 接收每个 1ms 状态，PX4 接收每个 4ms 状态。每次共有2,501个4ms边界，其中从 tick64 开始的2,486个边界同时具备“两个模型到达同一整数tick、AP进入下一传感器请求、PX4带回精确该时刻的执行器包”证据。

在 tick8000 暂停两秒，放行 tick8001–8004 一个4ms宏步，再暂停两秒，之后继续到10004。暂停中无模型步进、无传感器发送；两个完整模型状态哈希不变；AP每个暂停窗口重发一次相同待处理序号。该结果支持外部物理输入/时间边界的可行性，不是每4ms两飞控均完成新控制计算的证明。

保持未解锁，未发送飞行命令，未运行ROS任务/Agent/UE/QGC，也未修改原厂安装、现有产品运行器或任一飞控源码/参数基线。P450资产及用户原UE进程继续保留。实际浏览器依旧因管理员策略无法核验而拒绝；browser-automation工具索引缺失，没有另装驱动绕过。

## 实现与时钟契约

- [实验调度器](../tools/probe_joint_clock.py)：唯一父进程逐个下发下一整数tick；两个模型worker都返回对应真实状态后才发送传感器。生成模型存在共享静态参数，遵循既有 `model.cpp` 的一机一进程边界，不在同一进程装两个句柄。
- [隔离入口](../tools/run-joint-clock-probe.sh)：独立network/IPC/mount及私有 `/dev/shm`，仅loopback；复用已有模型构建、双栈固定身份预检与 `launch_spec`，不接入用户原实验网络。临时工作目录和EEPROM每次新建。
- PX4：一个执行器值在随后四个1ms模型子步中保持；每4ms发送实际模型HIL_SENSOR，100ms发GPS。最初无执行器的启动段明确不作为严格边界；首次执行器后必须收到精确当前时间，不能在超时后继续自由运行。
- AP：先接收servo C，积分一次1ms，回对应真实传感器，收到C+1后才允许下一步；明确 `no_lockstep=false`、`no_time_sync=false`。同序号重传只记录，不额外积分/发送。暂停持有下一请求。此轮没有注入丢包，不能证明UDP故障下exactly-once。
- 控制时序：AP JSON每1ms交换不等于AP主循环每1ms计算，主循环默认400Hz。AP下一序号是接收流程推进的间接证据，不是新控制结果ACK。本轮没有改变 `SCHED_LOOP_RATE`；实际有效参数未用原生参数读取/ACK逐项确认，因此不把源码默认值称为运行测得值。
- MAVLink遥测仅UDP接收。原始报文完整保留；只接收匹配系统身份的HEARTBEAT、ATTITUDE、LOCAL_POSITION_NED和SYSTEM_TIME作为观测。启动文本与未知消息不是时钟样本。未请求流速/模式/解锁；AP仅加载已存在的只读遥测流率参数文件。
- “3倍速”为既有飞控节流目标，本探针受IPC、记录和同步等待限制；没有测得或验收实际3倍速。墙钟超时90秒，暂停各2秒；这不是飞行任务、动力学等价或生产掉队阈值。

原始 `steps.jsonl`、每机完整120维 `*-truth.jsonl`、传感器/执行器 `wire.jsonl`、UDP原始字节与遥测解码、进程/启动参数和预检均在每次独立目录。未对日志时间事后对齐。

## 固定身份与一手来源

| 对象 | 本轮身份 |
|---|---|
| Prometheus主体 | upstream `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`，产品代码未改 |
| PX4 | `/opt/aerotwinsim/src/px4-d6f12ad1`，commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`；二进制 SHA256 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd` |
| ArduCopter | `/root/wksim-ap-dds-yaw-state-4Wr27s`，commit `1511f27194f1dcc3728270883047bdf022b3fd53` 及既有DDS patch；二进制 SHA256 `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5` |
| 本机SDK模型 | `MulticopterModel.zip` SHA256 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`；每次重新g++11.4构建，库 SHA256 `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3` |

预检没有改变或跳过原模型、固件、消息/控制安装包哈希条件。模型来自本地可构建生成源码，不依赖CopterSim.exe、Gazebo、闭源模型DLL或MATLAB运行时；授权不明的厂商源码/库不发布。P450视觉资产不等于已标定P450动力学。

主代理直接读取固定PX4源码：主IMU的 `time_usec` 设置 `CLOCK_MONOTONIC`，执行器包 `time_usec` 来自 `hrt_absolute_time()`；发送执行器前等待已注册lockstep组件。来源：[主IMU处理](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp#L503-L548)、[执行器时间与armed/lockstep位](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp#L116-L139)、[发送等待](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp#L1020-L1068)、[虚拟clock接口](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/platforms/posix/src/px4/common/drv_hrt.cpp#L468-L520)。这不是所有控制模块均有新计算的ACK。

research侧线的[固定AP源码研究](2026-09-06_joint-clock-source-research.md)给出完整来源与接缝限制；主代理另复读 `SIM_JSON.cpp:499–521`、`SITL_State.cpp:207–254`、`system.cpp:163–188`。重要约束：零时刻可能触发HAL墙钟回退，因此从真实第1ms步启动；重复timestamp仍可增序号；AP时钟由浮点差分累计到整数微秒，不能直接假设逐微秒精确一致；现有WksimState最多约50Hz，不可要求每4ms都有独立时间确认。

## 实测与失败保留

目录均相对于 `validation/`，无需任何运行进程即可阅读。

| 尝试 | 结果 | 有界结果/原因 |
|---|---|---|
| `joint-clock-ground-52s6xqtq` | failed | AP串行启动文本导致严格MAVLink解码在tick2失败；未放宽同步判据 |
| `joint-clock-ground-wz7mtrof` | failed | 未选中的PX4未知消息也提前检查system ID，解码器未知消息没有可用身份；在tick320中止 |
| `joint-clock-ground-91rnpgdz` | pass | 10,004步/机，2,486严格边界，暂停2.009955/2.009041秒，总墙钟20.918秒 |
| `joint-clock-ground-8o1sy6o6` | pass | 相同独立重复，暂停2.009356/2.008061秒，总墙钟22.216秒 |

第二次失败记录的原始AP文字可解码为实际 `Init ArduCopter V4.7.0 (1511f271)`、EEPROM初始化和logger提示。修正是为接收器开启BAD_DATA分类并保存原始字节，以及先选择本轮所需消息类型再核验身份；没有接受错误身份的目标遥测，更没有修改物理/握手门槛。每次都留各自源码SHA256、错误与进程清理记录；早期失败未保存完整源码快照，不能声称可只靠该目录还原当时整个脚本。

两次通过时各有AP10条、PX4 9条未解锁心跳；AP81条、PX4 396条ATTITUDE。暂停前后观测缓存不变，**没有新遥测不能独立证明每个瞬间FC微秒时钟冻结**。AP各有两次暂停中的原始同序号重发；PX4暂停中无新执行器包。

结果文件SHA256：

- 第一次通过：`9865fb363fad444a96ab666be79da9f7b6abf94e7b0826c9bb444221689ea186`。
- 独立重复：`c74da250a2ff52ff48b90867fedeffab5f831d3cf8c48962d3fa1b7f9a3979ef`。

## 审计、清理与复现

[离线审计器](../tools/audit_joint_clock_probe.py)复核所有证据哈希、两个模型每一实际状态/步号、AP原始包/传感器哈希、PX4原始包/有序时间、启动后的每一严格边界、暂停状态和发送计数、单步范围、心跳及清理记录。两个结果均以当前源码哈希重新审计通过。

第二名只读代理指出离线审计起初只看暂停前后快照，可能漏掉中途旧PX4时间包；已补逐包单调/暂停时间相等检查及两个反例测试。实际两份原始记录没有该异常，修复后仍通过。最终审计源码 SHA256 `e40eff3ebf2018ae55949b0b534aceb51866ab58d065d72003f738fd75ed0973`；5个探针单元测试全部通过。此轮不改产品实现，未重跑此前全部飞行回归；原完整回归不能借本轮5项检查重称为最新全量验证。

四次尝试的16个自建Linux进程组均记录无残留，随后内核PID检查也无这些PID。两次通过中模型均正常flush/退出，PX4 exit0；AP先SIGTERM，5秒内未退出后SIGKILL（exit -9）。**只有地面强制清理证据，不是AP优雅停机或空中安全停止证据。** 未按进程名清理。原AP PID828的argv、pgid、start_ticks19268前后一致；原UE PID35256的创建时间 `2026-09-06T02:20:00.4222100+09:00` 与命令行一致。仅证明这两个已知原进程身份未改变，不代表审计了机器上所有无关进程。

WSL Ubuntu-22.04，仓库工作目录下可执行：

```bash
bash tools/run-joint-clock-probe.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p test_probe_joint_clock.py -v
PYTHONDONTWRITEBYTECODE=1 python3 tools/audit_joint_clock_probe.py validation/joint-clock-ground-91rnpgdz --verify-current-sources
PYTHONDONTWRITEBYTECODE=1 python3 tools/audit_joint_clock_probe.py validation/joint-clock-ground-8o1sy6o6 --verify-current-sources
```

入口每次建立全新证据/临时目录；不要用本探针启动真实硬件、空中任务或生产联合场景。没有安装额外工具。

## 未验收与下一决策

生产单一ROS时间发布者、双载具公开namespace/epoch、Prometheus任务时间、UE双载具状态、真实联合飞行、掉队/迟到/断连/重传容错、倍速、冷重置与旧数据隔离均未实现/验收于本轮。原生微秒时间精确映射、AP控制计算相位、实际参数读取也待补证。

候选基线可以是“1ms权威物理、4ms输入边界、PX4区间保持、AP逐1ms交换”，但它并非用户已批准的生产决定。#8最终调度/掉队/暂停策略仍须确认；不把源码可行性或地面记录当成替用户作答。#6数值预算、#5 MATLAB范围、#9插件/场景反馈门槛继续保留。

两名侧线代理均显式指定并由主代理从实际turn_context核验 `gpt-6-astra` / `low`：Wegener `01a0736d-ee94-7e23-ae71-d9471cbfda10`（AP源码，独占一个研究文件）；Herschel `01a0737a-3ae3-71c2-a8a0-63aa22b852c3`（只读探针审计）。没有嵌套代理，均已关闭。research技能实际影响是把AP序号确认、HAL时间和控制计算完成拆开报告，而非把它们混成一个ACK。

Codebase Memory实读仍ready，快照20:55:19UTC、92,892节点/202,270边。精确覆盖确认四个新工具按tools祖先排除；四个复用core文件无记录解析缺口但metadata_changed，已直接读取并与运行哈希核对。固定WSL飞控源不在图内。此轮仅新增工具/文档，无依赖变更后产品结构的新查询，不为报告归档重建全库索引；不声称新工具已入图。Full Goal仍active。
