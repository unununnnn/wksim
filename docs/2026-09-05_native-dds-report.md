# 双飞控原生 DDS 本机验证

2026-09-05。本机已完成 ROS2 Humble 安装、独立 DDS 构建，以及 PX4/ArduCopter 通过各自原生 DDS 执行起飞、保持、航点、降落。同一 ROS2 图的并行复测和落地后 Agent 重启均通过。**这不是 Prometheus 业务模块移植完成、UE5.5 显示完成或 CopterSim 完整功能/数值等价验收。**

沿用已验证的自主模型和物理接口，没有调用 Gazebo、原版 CopterSim、闭源模型 DLL 或 MATLAB 运行时。模型构建仍依赖本机合法保留的源码 ZIP；未将厂商源码收入仓库。测试由 `tools/validate_sitl_physics.py` 统一调度，新增原生 DDS 命令路径，MAVLink 仅作心跳、遥测速率请求和独立状态观察，没有飞行控制回退。

## 复现已安装环境的验证

在本机 PowerShell 运行：

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'
wsl.exe -d Ubuntu-22.04 --exec python3 -m unittest validation.test_wksim_core validation.test_sitl_dds -v
wsl.exe -d Ubuntu-22.04 --exec bash tools/run-dds-validation.sh both /root/wksim-dds-VxM6Ni
```

16 项自动化检查已通过。第二条命令创建新的 `validation/dual-dds-*` 及两套飞控证据目录，不覆盖历史结果。当前机器之外还需要报告指定的模型 ZIP、飞控源码和编译环境，不能把本机路径当成通用安装器。

入口创建独立 Linux 网络命名空间，仅启用其回环接口，ROS domain 为 77。这是必要隔离：上游 Agent 的 UDP 实现绑定 `INADDR_ANY`，不能仅凭客户端目标为127.0.0.1就称为回环限定。测试不改变宿主防火墙，也不连接用户原有仿真或真机。只回收本次创建的进程；本机原有 AP 实例 PID828 在测试后仍运行。

## 固定工况与实际结果

沿用前一阶段的积分步长、机型、初态和门槛：四旋翼 X，模型 1ms，3 倍速，正常解锁检查；目标高度3m，达到2.5m后保持5个仿真秒，保持段高度误差≤0.6m、横滚/俯仰≤0.35rad；NED `[3,2,-3]` 航点位置误差≤0.5m且速度≤0.5m/s，保持2个仿真秒；降落上锁，估计和物理真值高度绝对值≤0.3m。DDS 状态也必须达到起飞、航点和落地门槛，消息陈旧超过2个墙钟秒会报错。

这些是接入测试门槛，不是厂商对照的动力学/传感器误差预算。航点“最小距离”不是全程误差或稳态精度，保持段仍包含向3m收敛的过程。正式数值对照继续按用户确认的固定工况与预先声明误差阈值另行验收。

| 最新并行复测 | ArduCopter | PX4 |
| --- | ---: | ---: |
| 最高物理真值高度 | 3.0036m | 3.1321m |
| 航点最小真值距离 | 0.0268m | 0.0411m |
| 3秒 Agent 停机期间飞控时钟推进 | 9.100s | 9.504s |
| Agent 重启至新状态及指令确认完成 | 0.571s | 0.690s |
| 任务 / 地面重连 | pass / pass | pass / pass |

独立观察节点在同一图中读取两套原生状态和位置，确认四个受检状态话题各只有一个发布端，并记录消息类型、GID 与 QoS。两机同时解锁的有效观察跨度约3.779秒；计入的两条状态接收年龄均小于0.5秒。观察节点另行确认两机最终位置在地面且均已上锁。这里只验证一个 AP 加一个 PX4，不证明两个 AP 固定 `/ap/*` 命名可以直接共存，也不证明共享 Agent 或大规模多机性能。

重连测试在**已落地并上锁后**终止该机 Agent，等待3个墙钟秒，确认状态陈旧且飞控/物理仍推进，再启动新 Agent，等待新状态和新的模式服务/命令确认。没有复用旧 ACK，也没有重放解锁指令。它不是空中断连、飞控重启、物理连接重建或 UE 断连验收。

## 已固定的环境与构建

新增 ROS 依赖前执行安装模拟：276个新包，0升级、0删除；源配置包另行安装。准备源、检查计划和安装分为 `bootstrap-humble-validation.sh prepare|plan|install` 三个显式阶段。源包 SHA256 与官方发布摘要和实际下载一致；安装后 `dpkg --audit` 无输出。未安装 Gazebo、桌面 ROS 全家桶或新 UE。

| 构件 | 本次版本/来源 | 位置或核验 |
| --- | --- | --- |
| ROS2 | Humble / Ubuntu22.04 | `/opt/ros/humble`，具体 Debian 版本见 E-INSTALL |
| Fast DDS / Fast CDR | 2.6.12 / 1.0.29 | 复用 Humble 系统库 |
| eProsima Agent | v2.4.2，`57d086216d01ec43121845d385894a25987f8a2c` | `/root/wksim-dds-VxM6Ni/agent-install` |
| micro-ROS Agent ROS 包 | humble，`c93ee764e0d2ef4907aeb29233c68cb5f4b56976` | 同目录下 `ros-install`；底层仍为 Agent2.4.2 |
| ArduPilot DDS Gen | v4.7.0，`b8840058b81c87e1169a5a0ed4744d7b3dc99e0b` | 私有构建目录，Java11 / Gradle7.6 |
| px4_msgs | `86d8239e962f6939e05c3737784f60c02fa884db` | 全部60个桥接及嵌套 schema 比对通过 |
| PX4 | v1.17.0，现有 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` 构建 | SHA256 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd` |
| ArduCopter | 4.7.0，`1511f27194f1dcc3728270883047bdf022b3fd53`，新构建 `AP_DDS_ENABLED=1` | SHA256 `cb90d1ea220d636e77c45b9833b9dc8b4dda43b13480cf8619ee0645754191fd` |

新 AP 二进制是 `/root/wksim-dds-VxM6Ni/ap-dds-build/sitl/bin/arducopter`，不是复制目录中残留的旧 `build/sitl/bin/arducopter`。原 AP/PX4 构建没有被覆盖。PX4 原源码有已有本地改动，本次受测对象以二进制哈希为准，不宣称等于无改动的上游构建。

构建脚本 `tools/build-dds-validation.sh` 的 fetch、runtime、firmware 阶段已实际执行，精确 pin 保存在脚本内。依赖检查和库链接日志位于 `/root/wksim-dds-VxM6Ni/logs/runtime-0h21kl.log`；新 AP 构建日志为 `firmware-w3h2RZ.log`。同目录中包含原始编译产物，不进行全局 Agent 安装或 `ldconfig` 修改。

## DDS 接口和时间问题

| 边界 | PX4 | ArduCopter |
| --- | --- | --- |
| XRCE 端口 | UDP18888 | UDP12019 |
| 命名 | `/wksim_px4_21/fmu/*`，非零消息版本追加 `_vN` | 原生 `/ap/*` |
| 模式/解锁 | `VehicleCommand` 和新 `VehicleCommandAck` | `ModeSwitch`、`ArmMotors` 服务响应 |
| 起飞/保持/航点 | `OffboardControlMode` + `TrajectorySetpoint` | `Takeoff` 服务 + `GlobalPosition` 的 `/ap/cmd_gps_pose` |
| 降落 | 原生 `VehicleCommand` LAND | `ModeSwitch` LAND=9 |
| 状态坐标 | 本地 NED | pose/twist 源码输出 ENU；适配器显式转 NED 后核验 |

AP4.7.0 的 `PoseStamped.header.frame_id` 为 `base_link`，但实际位置由相对 home 的 NED 转成 ENU；不能仅靠帧名字推断坐标。测试航点使用固定初始 origin/home 对应关系；不是任意 home 重设、地形高度或全局航线接口验收。

E-FAIL 复现了最初的 PX4 失败：三倍速物理时钟与 Agent 墙钟不同速，按系统时间填指令 timestamp 时，DDS 指令相对飞控状态落后约0.76至5.70秒。原生 `failsafe_flags.offboard_control_signal_lost=true`，`battery_warning=0`；PX4切入返航，不是电池问题。

F-CLOCK：本机生成的 `uORB/ucdr/offboard_control_mode.h` 明确会从接收时间戳扣除 Agent offset，PX4 的 `UXRCE_DDS_SYNCT` 配置允许仿真中禁用该同步。修复仅作用于本次启动参数：`PX4_PARAM_UXRCE_DDS_SYNCT=0`，指令时间戳取该机新鲜 DDS 状态携带的仿真微秒；不使用系统墙钟、不强制解锁、不放宽 Offboard 超时。输入发布队列保留最新一条。回归检查包含“仿真时间不是墙钟”和陈旧状态拒绝。

[PX4官方说明](https://docs.px4.io/main/en/middleware/uxrce_dds)解释了 Agent 版本选择、消息匹配与仿真时间同步选项；本机配置/生成源码和失败、修复后的实飞日志共同支持上述原因判断。此处的“每个独立实例使用自己的物理时间”不等于已经建立整个多机世界的统一 `/clock`；统一运行时与暂停/倍速语义仍需在运行边界决策中固定。

## Evidence → Finding → Path

以下路径相对 wksim；原始证据不覆盖。复现命令见前文，安装/构建证据只在拥有相同本地环境时可复现。

- E-INSTALL：[安装记录](../validation/humble-install-oJMjUK/output.log)、[安装计划](../validation/humble-install-oJMjUK/packages-plan.log)、[包版本](../validation/humble-install-oJMjUK/versions.txt)，UTC起点05:17:59；源准备见 `validation/humble-prepare-fb5JR2/`。源包使用固定官方 `ros2-apt-source_1.2.0.jammy_all.deb`，SHA256 `767884cf4ed03116b9d64438930a832ed854147ae435279a7924dfdf60f94433`。
- E-SCHEMA：[60个消息核验](../validation/dds-schemas-20260905.json)，逐项保存两份源文件 SHA256，比较字段、顺序、常量及嵌套定义，仅忽略注释与格式。
- E-FAIL：[带原生失效标志的失败记录](../validation/px4-dds-1kmv3fqt/result.json)及同目录 `dds.jsonl`；保留它作为时间基错误的反例，不能当作通过记录。
- E-PX：[修复后单栈通过](../validation/px4-dds-vqymk0dr/result.json)，完整任务、无飞行中 failsafe；该次尚未包含 Agent 重启。
- E-DUAL：[最终并行复测](../validation/dual-dds-x9znmhkr/result.json)，UTC05:46:57，SHA256 `130f2789b9c49bc7c5b8880fd5693327b752e4a2346ad7c14626a100a407e654`；独立观察、同图唯一发布端、同时解锁和两份任务结果指针。
- E-AP-FINAL：[AP任务及重连](../validation/arducopter-dds-w6nszerd/result.json)，SHA256 `e469bffce75077e693b3c1f9f5718e0735d18ecb73aae34d66c53e76b8361091`。
- E-PX-FINAL：[PX4任务及重连](../validation/px4-dds-k06naq0q/result.json)，SHA256 `00a89d90b8acc22b56ffa28b52930fe0521966c412bb6bc8a033d3ec6137208c`。
- E-REPEAT：[上一轮并行结果](../validation/dual-dds-q77ekyj8/result.json)，SHA256 `11d5a1115002c7354197d364c83095e70e6f7c03ec5eafada0e39597f19cfcc2`；同样通过。最终复测增加了独立观察状态新鲜度与最终上锁检查。

F-NATIVE（E-SCHEMA、E-AP-FINAL、E-PX-FINAL）：所固定版本的两套飞控均能通过原生 DDS 驱动自主模型完成该固定任务，指令确认、估计状态和物理真值三类证据均存在。消息语义不同，兼容的是可经适配形成共同任务，不是两套消息可以互换。

F-COEXIST（E-DUAL、E-REPEAT）：独立 Agent、相同 ROS domain、不同原生话题前缀的组合已本机验证。没有推导为共享 Agent、多 AP 自动命名或生产可靠性已通过。

P-AP：ROS2服务/位置命令 → AP原生DDS → AP控制器 → wksim JSON物理接口 → 自主模型 → AP估计器 → 原生DDS状态及MAVLink独立观察（E-AP-FINAL）。

P-PX：ROS2指令/Offboard设定值 → PX4原生DDS → PX4控制器 → wksim HIL物理接口 → 自主模型 → PX4估计器 → 原生DDS状态及MAVLink独立观察（E-PX-FINAL）。

## 下一步与明确未完成项

继续 [本机双原生 DDS 与 UE5.5 SITL 运行边界验证](https://github.com/unununnnn/wksim/issues/7)：接入已有 UE5.5 显示工程，以权威状态验证真实画面、坐标和显示断连不阻塞控制。保持该任务开放。

Prometheus 原始消息/控制/实验的 ROS2 迁移不能由当前诊断节点替代。MATLAB最小接口、可选原版DLL、全机型/环境/碰撞、完整界面和工具流程、暂停/复位/步进、HIL后续、数值对照、空中失联矩阵和多机性能均未完成；完整目标不缩减。
