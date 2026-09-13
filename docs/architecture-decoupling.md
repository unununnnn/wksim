# 工具链解耦检查与控制算法扩展

2026-09-12。范围：wksim 当前源码，运动控制、模型插件、UE 视觉、实验与双飞控固件。用户补充目标：扩展地面车辆、固定翼；验证 LQR/MPC 替换**固件底层 PID**的实际效果。

以下保留最初检查时的发现与推荐。用户确认全部按推荐推进后，已完成双飞控内环 LQR/MPC 实际对照、地面车辆参考闭环、UE 视觉 module 与实验/部署拆分；最新状态、运行命令与证据见 [实施报告](architecture-implementation-20260912.md)。固定翼与正式支持组合仍须按各自工况继续验收。

## 现状与改动

| module | 已有 seam | 仍然耦合的地方 | 本轮结果 |
| --- | --- | --- | --- |
| 自主模型 | `model.py` 的 C ABI、独立进程，AP JSON/PX4 MAVLink 物理 adapter | 1 ms、16 输入/120 输出、固定四旋翼映射；`runtime.launch_spec` 仍拥有部分旋翼分配常数 | 保留实现，明确机型扩展路线 |
| 外部位置控制 | 三个真实 PID/UDE/NE implementation，共用 ENU/FLU 输入 | 原来 UDE/NE 依赖 PID 文件；NE 重置有初始位置语义，实验任务仍处理算法专属诊断 | 抽出公共输入、选择和推力标定；旧导入兼容 |
| 固件内环控制 | PX4 角速度控制计算点；AP CustomControl | 没有工具链拥有的 LQR/MPC implementation、准入和对照实验 | 已定位本机源码；不把外部位置环验收等同内环验收 |
| 固件资源 | 固定候选、消息集合与能力验收 | AP 独立输入与旧准入强制依赖 PX4 根目录；版本与能力散布在多个 profile | AP 只要求自己的固件根目录；既有版本验收保留 |
| UE 视觉 | 状态流与物理分开；画面 ACK 不推进物理 | `WksimVisualGameMode.cpp` 包含 P450 路径、四/六旋翼几何、部分飞控身份固定绑定 | 未改二进制资产或 GameMode；提出独立视觉模型 module |
| 实验 | 联合场景以 `runtime_profile` 选择已验证组合 | 独立示例仍有 `/root` 部署路径；部分算法实验复用姿态实验准备流程 | 新 AP 独立示例无 PX4 路径；部署 profile 全面统一留待后续 |

主要源文件：`Simulator/wksim_core/{model,model_parameters,ap_json,px4_mavlink}.py`、`Simulator/wksim_runtime/{runtime,config,preflight,independent_profile,pid_task,joint_profile}.py`、`Simulator/ue55/{product_bridge.py,Source/WksimVisual/WksimVisualGameMode.cpp}`。

### 已落地的两个修复

1. `Simulator/wksim_control/position_contract.py` 拥有位置控制输入 interface 与数值检查；`controllers.py` 按显式选择加载真实 adapter；`native_thrust.py` 拥有多旋翼悬停标定。PID/UDE/NE 算法公式、增益与重置逻辑保留。旧 `position_pid.PIDState/PIDReference/NativeThrustConfig/select_controller` 和包级 PID 导入仍兼容。
2. `config.py` 按飞控栈要求 `ap_candidate` 或 `px4_root`。`runtime.py` 只在 PX4 分支使用 PX4 路径；旧 `preflight.py` 不再解析 AP 未使用的 PX4 目录；`independent_profile.py` 只校验所选固件根目录。旧 AP 配置仍可带格式合法的 `px4_root`，但它不决定 AP 运行资源。DDS、控制包、所选固件、模型和历史证据仍按既有规则验收。

删除测试（deletion test）：删除共享控制契约，会将相同数值/坐标约束复制回三个算法；它提供 depth。删除 AP 对 PX4 的目录要求，不会失去 AP 行为，只去掉无用依赖。三个算法的独立导入测试证明其 seam 确实存在；不为尚未实现的 LQR/MPC 创建占位 adapter。

locality：新增外部位置算法时，类型不再归 PID implementation 所有；leverage：三个现有 adapter 复用同一输入 interface。这里的“公共”指现有位置控制数据，**不承诺**多旋翼推力标定可以用于固定翼舵面或车轮。

后续运行归档与原 C++ 数值对照工具已补入三个新 module 的源码记录。外部实验输出增加 `control_stage=external_position` 与 `firmware_inner_loop_replaced=false`，防止结果被误读为内环替换。

## LQR/MPC 应该放在哪里

必须先固定“替换哪一个环”。本路线首个建议切片是多旋翼角速度内环；如改为姿态＋角速度联合 MPC，应另定输入、输出与对照基线，不能混用验收结论。

```text
实验目标 → 任务/轨迹 → 位置控制 → 姿态控制 → 角速度内环 → 控制分配 → 执行器 → 模型
                                      ↑           ↑
                                  可另设切片    首个建议替换 seam
                                                  │
                                         PID / LQR / MPC
模型 → 仿真传感器 → 固件估计器 → 状态反馈 ──────────┘
模型真值 → 验收记录 / UE 视觉
```

当前 `native_px4.py` 发布 `VehicleAttitudeSetpoint` 并选择 `attitude=True`，因此经过固件内部控制。将外部位置算法改名为 LQR 或 MPC，不会改变这一事实。物理真值用于验收，不能偷偷替代新控制器的估计反馈，否则比较同时改变了估计条件。

### 已检查的本机固定源码

以下为保留源码的直接读取，不是声称最新上游接口，也未证明当前二进制启用了 CustomControl。详细路径与 SHA256 在本机 `validation/architecture-decoupling-20260912/firmware-source-inspection.json`。

| 飞控 | 已定位 seam | 保留在 native adapter 中的职责 |
| --- | --- | --- |
| PX4，多旋翼 | `/root/wksim-px4-state-ONa1Kw/src/src/modules/mc_rate_control/MulticopterRateControl.cpp:220` 调用 `RateControl::update`；随后发布 thrust/torque setpoints | 固件原生采样时刻、dt、角速度与角加速度输入、控制分配饱和反馈、落地/解锁重置，以及输出尺度 |
| ArduCopter | `/root/wksim-ap-clock-stop-OXQqdR/src/libraries/AC_CustomControl/AC_CustomControl.cpp:83` 调用 backend，`:90` 起按轴覆盖电机控制输入；`:159` 起重置并启用 | 编译选项、轴掩码、backend 生命周期、模式切换、积分重置、motor 输出语义及日志 |

PX4 的 `src/lib/rate_control/rate_control.cpp:71` 实现现有角速度 PID；AP 的 `AC_AttitudeControl_Multi.cpp:442` 起处理内环，`:458` 起写入 roll/pitch/yaw。AP CustomControl 后运行并覆盖选中输出，不能把这种“输出接管”描述成原 PID 完全不再计算。

这两个 seam 的数值尺度与控制分配语义不同。控制算法 module 可以使用物理量建模，但 native adapter 必须明确物理力矩与固件归一化输出的映射；不能把归一化 torque 直接标成 N·m。直接电机输出还会替换控制分配，属于另一个实验。

### 可验证的实施顺序

1. 在新的固件候选中接入 **等价 PID adapter**，复用原估计器、调度和控制分配，先证明接入没有改变基线行为。保留原固件候选供回归。
2. 在固定多旋翼模型与工作点上建立 LQR 模型、离散周期与增益，明确输入状态、目标、饱和和重置语义。纯算法实现不导入 UE、ROS、固件消息或项目实验；由每个飞控 native adapter 接入该算法。
3. 以同样 seam 接 MPC；记录求解状态、计算耗时、deadline miss、约束、warm-start 重置和降级次数。未收敛时的控制输出策略必须显式记录，不能悄悄退回 PID 后仍将整段记为 MPC。
4. 对每次运行归档固件源码/补丁/二进制、控制器身份、系数/模型/求解器构建信息、每周期实际生效算法与输出、估计状态、仿真真值和时钟。对相同任务、扰动、传感器噪声种子与初态做 PID/LQR/MPC 成对比较。
5. 比较跟踪误差、超调、收敛时间、扰动恢复、执行器饱和、控制量变化与计算预算；仿真倍率和宿主墙钟预算分开记录。SITL 通过不等于目标飞控硬件算力验收。

LQR/MPC 需要具体模型、工作点、控制周期、状态/输入定义及权重或约束。当前需求确定了替换用途，尚未确定这些参数，本轮没有虚构算法或修改在用固件。

## 车辆与固定翼扩展

以下是实现路线，尚未接入运行。沿用现有 Full 范围，不改写 `docs/plan/full-contracts/model-07-fw.json` 中固定翼尚无证据的状态。

| 独立选择 | 多旋翼 | 固定翼 | 地面车辆 |
| --- | --- | --- | --- |
| 模型插件 | 电机/旋翼、刚体 | 气动、空速、失速、舵面 | 轮胎/接地、转向、制动、传动 |
| 执行器布局 | 每个电机、旋向、位置、力/矩 | 副翼/升降舵/方向舵/油门、舵偏限幅 | 转向/左右轮或驱动/制动、正反向范围 |
| 固件目标 | ArduCopter / PX4 多旋翼 | ArduPlane / PX4 固定翼 | Rover / 经验证的车辆固件目标 |
| 固件内环 | 角速度/姿态 | 横滚/俯仰/偏航与速度相关控制 | 转向/横摆率/轮速等明确控制环 |
| 视觉模型 | 机身/旋翼 | 机身/舵面 | 车体/车轮 |

车辆规格、固件目标、算法选择和 UE 外观是四项独立身份；“独立选择”仍须通过兼容关系校验。ArduCopter 不能因为都使用 MAVLink 就作为固定翼或车辆控制固件；`stack` 最终应区分固件家族与固件目标，保留旧 `arducopter` 输入的明确迁移规则。

机型 module 应集中维护坐标/单位、动力学参数、执行器布局、传感器配置和模型 ABI 版本。AP JSON/PX4 物理 adapter 将原生输出映射到机型执行器；UE 只消费视觉所需状态与部件姿态。固定的 `16/120` 可以继续作为既有插件 adapter 的兼容格式，不能直接当作所有未来机型的唯一公共 interface。

先用一款确定模型的车或固定翼验证第二类实际 adapter，再形成稳定跨载具 seam；避免预先设计几十个空类。物理模型的数值验收、飞控目标构建、闭环实验与 UE 外观各自提供证据。共享权威时间、场景接触与环境反馈继续沿用既有决议。

## 固件升级与资产维护

固件候选发布 module 最终应集中拥有：上游版本、补丁集、编译目标/选项、native adapter 版本、消息集合、能力与控制器身份。实验只选择明确候选及能力；本机部署位置另行解析，产出完整配置快照后进入已有准入。每次升级应在新的候选目录构建并执行受影响实验，不能直接修改默认哈希来放行。

UE 后续把资产路径、缩放、轴向、部件布局与状态映射放到视觉模型 module；GameMode 保留显示生命周期与状态路由。P450 视觉与当前 quad-X 物理参数并不等价，换 UE 外观不会自动改变模型惯量或动力。当前硬编码来源已定位，尚未改动或重新构建 UE。

## 验证与覆盖限制

- 133 项相关离线测试，127 通过、6 个需显式本机资源的测试跳过；涵盖三算法、运行装配、旧/新准入、独立选择及新增 import 隔离检查。另有 4 项 Windows 独立导入测试通过；PID/UDE/NE 的算法与配置类 AST 与本轮修改前一致。首次新增测试把 NE 初始位置差异当作同值输出，修正测试初态后通过，算法实现未为此改动。
- 新增 AP 测试使用真实临时文件和缺失 PX4 目录，确认能检查自身固件及 Agent；改变自身固件字节仍被拒绝；测试在缺失模型处停止，**没有冒充完整资源准入**。
- 本轮未运行真实飞行、LQR/MPC、UE 构建或新机型数值验收；未更新固定准入哈希、历史证据和已发布 Full 完成状态。
- Codebase Memory 原快照为 2026-09-09；本轮依赖结构查询前刷新成功，113151 nodes / 328514 edges，日志 `C:/CBMData/logs/wksim-prometheus-1789189038.log`。图仅定位证据，存在部分解析/排除与动态调用覆盖限制；实际源码另行读取。源码改动后的后续结构查询需再检查刷新。
- 外部 WSL 固件源通过直接读取定位，不在本项目完整图覆盖内；未逐个读取 UE 二进制资产。本报告不据图缺边断言所有 module 均完全独立。

推荐后续首个实际算法切片：**固定四旋翼模型＋固件角速度内环等价 PID 接入，再做 LQR 对照**。MPC 与第二载具类别分别推进，避免同时更换模型、固件目标、控制环与算法后无法归因。
