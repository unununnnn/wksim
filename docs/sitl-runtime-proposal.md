# Prometheus 双飞控 SITL 已确认运行边界与实施状态

状态：2026-09-05 用户在本机验证后确认WSL自主物理/双原生DDS/Prometheus/ROS2编排、Windows UE5.5/可选DLL宿主分工，并确认同一联合场景共享权威仿真时间。正式决议在[RflySim 模块组织与 UE5.5 SITL 运行边界决策](https://github.com/unununnnn/wksim/issues/4#issuecomment-5550138622)，该决策票已关闭。Gazebo不是目标依赖；本文件是本地实施说明，不取代Issue中的唯一决议。联合场景调度、模型插件ABI、场景反馈及产品级状态分发仍须实现验证。

用户要求完整功能/操作流程复刻、wksim自有界面；核心自主构建运行，原版DLL可选导入。MATLAB可用于构建模型，运行时不依赖MATLAB。见 `coptersim-reconstruction.md`。2026-09-05已实现并通过一个本地模型的PX4/ArduCopter物理闭环，详见[集成证据](2026-09-05_sitl-physics-report.md)；随后通过[同域双原生DDS任务与地面Agent重连](2026-09-05_native-dds-report.md)，并通过[两栈分别接入UE5.5实际画面、坐标回读与显示断流恢复](2026-09-05_ue55-report.md)。最新已完成[Prometheus公开入口经原生控制节点驱动双飞控共同位置任务](2026-09-05_prometheus-native-report.md)，完整业务/工具工作流仍未迁移，UE仍使用验证几何体与诊断桥，不等于完整核心或产品完成。不删除本机已有Gazebo。

## 已确认约束与来源

主体为 Prometheus，首期包含 PX4、ArduCopter；Windows UE5.5 负责模型与场景显示，WSL Ubuntu22.04 使用 ROS2/DDS，参考本地 RflySim 工具组织，优先复用现有组件，MATLAB 只留接口。

代码基线为 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`。本机控制模块索引和源码核实了 `uav_controller.cpp:212` 的主循环：当前直接依赖 OFFBOARD、POSCTL、AUTO.LAND 和 PX4 参数操作；`uav_control_node.cpp` 使用 ROS1 的 100Hz 主循环。`sitl_px4_outdoor.launch` 依赖 ROS1、MAVROS 和 Gazebo Classic 的 spawn_model。移植需要更换这些边界，保留可追溯的 Prometheus 命令、控制行为和实验来源。

## 已选运行分工

| RflySim 参考角色 | Prometheus/wksim 迁移位置与职责 | 运行侧 |
| --- | --- | --- |
| SITLRun 启动入口 | 迁移 `Scripts` / `Simulator` 的启动定义，以 ROS2 launch 组织一次运行；Windows 入口只传配置和启动 WSL/视景 | Windows + WSL |
| CopterSim 动力学角色 | 自主可构建的模型运行核心承担外部物理SITL的物理、基础传感器和仿真时间；分别适配PX4/AP传感器与执行器接口。旧模型、SDK及本地模板作为输入和对照，不要求原版EXE/DLL存在 | WSL核心；Windows可选DLL宿主另行实现验证 |
| PX4 SITL | 复用 v1.17.0 源码/可执行文件候选；uXRCE-DDS 对接任务控制 | WSL |
| 新增 ArduCopter SITL | 复用 4.7.0 源码，确认并构建 AP_DDS；Guided 控制实现单独适配 | WSL |
| 任务与控制工具 | 从 `Modules/common/prometheus_msgs`、`Modules/uav_control` 和 `Modules/tutorial_demo` 迁移包，统一任务入口；47项ROS2接口及命令受理/参考量库已迁移，完整控制/任务仍待实现 | WSL / ROS2 |
| RflySim3D 视景角色 | 原生wksim UE5.5.4模块异步显示权威位姿，采用已通过实测的直接显示边界；不要求Cosys/AirSim运行时 | Windows |
| QGroundControl 地面站 | 复用本机地面站；MAVLink 承担查看与所需地面站功能，控制权切换须显式处理 | Windows |
| 运行证据 | ROS bag、飞控原生日志、物理真值及启动配置/版本清单 | WSL + Windows |

此表表示职责映射，完整复刻的版本与协议覆盖仍须锁定验收清单。UE本期承担显示，视景与动力学独立；地形/碰撞反馈的时序另行验证，不能把异步显示等同于没有物理环境耦合。PX4/AP任务侧DDS与物理链路分开管理。

## DDS、任务与坐标边界

依据 [双原生 DDS 调研](https://github.com/unununnnn/wksim/issues/3#issuecomment-5548993903)，推荐 ROS2 Humble，同一 DDS domain，首次验证采用两个独立 Agent（PX4 8888 / AP 2019 为候选端口，启动前检查占用）。消息分别固定 `px4_msgs` 与 ArduPilot 标准/自定义 IDL 版本。Agent 2.x 的交集是源码依据，共享 Agent 仍需单独实测，不作为首个闭环前提。

本机实测组合现为Humble、Agent2.4.2、Fast DDS2.6.12、独立Agent端口PX4=18888/AP=12019、domain77。AP使用新编译DDS固件，PX4消息60个schema匹配；同图命令、状态与地面重连已通过。3倍速独立模型测试中PX4关闭Agent墙钟同步，指令取本机仿真时间；这项验证没有解决多个物理实例的统一时钟，也没有把诊断节点定为最终Prometheus适配器。

Prometheus 任务层维持命令、状态和实验的语义；两套小型适配器承担模式、解锁、起飞、目标和降落。PX4 Offboard 保活与 AP Guided 超时独立实现。共同任务首次包含起飞、悬停、航点、降落；不支持的原始控制模式显式报告，不能悄悄改成另一种动作。

推荐 ROS 边界 ENU/FLU、米/秒/弧度，PX4 的 NED/FRD 转换只在适配边界执行。AP 按其 frame_id 和实际源码转换；UE 使用引擎坐标和厘米时，桥进行显式变换，并以位置轴、偏航和四元数用例验收。保留原消息枚举数值，ROS2 字段重命名建立映射；如需改变类型精度、拼写或能力集合，记录为接口变更。

联合场景只选一个权威仿真时间发布者；各载具独立计时仅适用于互不影响的独立实验。状态记录源时间、接收时间和运行实例。控制失联检测使用明确的时基，不能默认 `/clock` 暂停也暂停所有看门狗。QoS按实际发布端配置，命令确认和动作完成分别判断。不同飞控步长、暂停/单步/倍速、掉队与重置epoch的契约由[联合场景权威时间与双飞控步进策略决策](https://github.com/unununnnn/wksim/issues/8)推进，现有双独立循环不满足该新验收条件。

原ROS1消息包保持不变，新增`ros2/src/prometheus_msgs`覆盖43消息、3服务、1动作。96处必要命名/类型别名变化有逐项来源和哈希；Humble构建、104次序列化往返及代表性RMW交互通过，详见[接口包报告](2026-09-05_prometheus-ros2-report.md)。类型包可用不表示Prometheus业务或双飞控产品适配已迁移。

后续新增 `ros2/src/prometheus_control` 迁移命令受理、优先级和有效参考量，8项单测及102组原C++方法对照通过，见[命令迁移报告](2026-09-05_prometheus-command-report.md)。本地受理或降落意图不能算作飞控ACK/任务完成。

独立输出修整阶段保留按轴保持、死区与有效字段，并显式修复状态切换漏输出、混合历史和偏移位置问题；40项回归及332组输出对照通过，见[输出修整报告](2026-09-05_prometheus-shaping-report.md)。该阶段尚无完整控制器/任务节点/产品原生DDS发送，后续原生控制节点进展见下文。

随后实测发现固定ArduCopter原固件的 `GlobalPosition` 接入层不执行消息中的偏航，不能仅凭schema判定与Prometheus命令语义兼容。现已保存并重新构建一个**非默认、可选候选补丁**：在不改变消息的情况下接通位置＋偏航，显式拒绝未实现字段组合。三方向偏航/定点/降落/地面重连通过，未打补丁固件同条件负对照超时，PX4常规任务回归通过；41项单测和111条接入层断言通过，见[偏航能力报告](2026-09-05_arducopter-dds-yaw-report.md)。这仍是诊断链，不是Prometheus产品节点，也未证明全部控制模式、空中失联或联合场景共享时间。

## Windows / WSL 与生命周期

原生控制节点后续进展：两个飞控使用完全相同的六条Prometheus公开输入完成自主悬停、解锁、起飞接管、航点、降落和重连后模式切换。两次诊断观察层原生控制发送均为零，安装后产品节点承担实际DDS请求和目标流；51项自动检查通过，详见[原生节点报告](2026-09-05_prometheus-native-report.md)。AP新增可选WksimState快照，明确home、有效性与重置，不把旧topic存在当作定位可靠；PX4区分地面初始定位与离地最终航向对齐。两个闭环仍是独立实验，未实现联合场景时钟、空中失联矩阵或完整控制模式；MATLAB范围未被代答。

DDS 的飞控、Agent 和任务节点优先全部放在 WSL 内，降低跨 Windows 发现的初始复杂度。UE 显示桥是唯一必要的跨系统运行边界之一：具体协议以已有组件证据确定；NAT 模式下启动时解析宿主/WSL地址，不能硬编码127.0.0.1共享。地面站端口独立分配。多实例同时检查 namespace、MAVLink system ID、XRCE client key、UDP端口与模型名。

启动顺序由就绪条件控制：环境/端口检查 → 模型核心与飞控按各物理接口要求启动 → Agent与飞控接通 → 遥测/估计器就绪 → 任务节点可接收命令。UE和地面站可并行启动，未就绪不阻塞飞控保活。收到停止请求先停止新任务并执行已选安全动作，再按本次创建的PID收尾；不以全局进程名清理其他运行。

UE断连时标记画面陈旧并记录；重连只显示当前有效状态，不重放旧控制指令。DDS断连则由适配器与飞控失联配置处理，单独验收。渲染异常不能伪造飞控成功结果。

本机UE验证现已支持此分工：原生wksim UE5.5模块按权威NED真值更新Actor，两栈分别在3墙钟秒显示断流期间继续约9仿真秒并完成任务，捕获STALE及恢复LIVE画面。跨系统暂用共享JSONL只读尾读再经Windows回环UDP，避免暴露私有DDS网络；它不是已定型的生产ROS2状态分发。场景建筑仅显示、停机坪视觉零面对齐模型地面；地形/碰撞反馈仍未实现。

## 已完成的前置验证与后续边界

1. 检查本机已有PX4/AP二进制对应版本与DDS编译能力；安装/构建缺口须显式记录。
2. 两栈分别通过DDS发现、状态订阅、模式/解锁拒绝与接受、目标输入和Agent重连测试。
3. 复用一个基础场景和等义机型分别执行真实起飞—悬停—航点—降落，记录物理真值与飞控日志。
4. UE接收同一权威位姿，验证坐标和时间；故意暂停显示确认控制闭环继续，并验证断连陈旧提示。
5. 同时运行一个PX4与一个AP实例验证隔离；是否必须首批即通过由验收决策票锁定。

Gazebo/ros_gz不再是目标运行依赖。若自主物理接入或显示组件复用失败，记录证据并调整该边界的实现，不自动回退为Gazebo最终后端。MATLAB可用于构建期代码生成，但不作为主SITL启动依赖；最小输入输出与示例仍由[MATLAB接口决策](https://github.com/unununnnn/wksim/issues/5)限定。完整功能覆盖和精确验收阈值继续与用户确认。

MATLAB传输已由用户选择基础 `tcpclient` + JSON 可选桥；不要求ROS/Instrument Control Toolbox，原生ROS2直连待本机R2022b/Humble联测。功能范围仍待该决策票的另一项用户答复，客户端/桥尚未实现验证，见[本机依据与接口草案](matlab-interface-proposal.md)。

以上1–5的本机诊断验证已完成，但第5项只是同图并行的独立实验，未实现联合场景共享时间。完整Full仍包含其他SIL/HITL/SIH/外部仿真、UDP/MAVLink/SDK互操作、模型与完整工具工作流；SIH可由飞控内部拥有物理，不能被外部物理SITL的部署分工排除。可选DLL与地形/碰撞/视觉反馈的具体契约由[可选模型插件与场景反馈接口决策](https://github.com/unununnnn/wksim/issues/9)推进。异步画面不表示取消环境反馈，原DLL可选不表示取消插件导入功能。
