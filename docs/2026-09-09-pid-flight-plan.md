# #35 外部 PID 双栈候选：冻结协议与未运行交接

2026-09-09。交付为可审阅的 Python 外部 PID 候选任务、独立运行入口、真实输入扰动 observer 和纯测试。**未启动 FC、模型、ROS 节点；未做本轮候选 preflight；未构建 C++；不是 #35 闭环验收，也不是 #34 姿态试验的新完成记录。** 最新主线指令是在此停止真实运行，交由剩余票据及 Lunar 接手计划安排后续。

## 入口与模型身份

入口 `bash tools/run-pid-flight.sh --stack {px4|arducopter} --run-id NEW --config Simulator/wksim_runtime/pid-flight-v1.json --output-root /root/wksim-pid-flight-NEW`。`--config` 必须提供；不提供即在参数解析阶段失败。`--preflight` 仅检查既有封存候选与实际导入，不启动飞行，但本轮尚未执行。真实运行要求原私有 net/IPC/mount、domain77、FastDDS/localhost 隔离；保留独立 native-attitude opt-in。runner 复用 #34 准入函数及相同退出/进程 maps/源码副本/前后身份检查结构，新增 PID 文件全纳入运行 seal，360 s 总墙钟 watchdog。

冻结文件原始字节 SHA256：

`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`

文件 `Simulator/wksim_runtime/pid-flight-v1.json` 与 `pid_task.py:CONFIG_SHA256` 必须一致。所有替代控制器（UDE、NE、native、空缺）和预算变更均拒绝，不能看试验数据后改预算覆盖原协议。

模型为已验收姿态候选使用的固定 quad-X native library：SHA256 `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`，mass=1.515 kg。模型身份定义为 `sha256:` 加该 library hash，准入与 physics observer 均查实际库字节。质量来自既有源参数逐项对照 `validation/model-reference-provenance-20260907/parameter-correspondence.json` 的 `ModelParam_uavMass`；当前 native wrapper 没有参数 getter，不能把 hash 绑定称为本轮运行时质量读回。

PID 每轴 Kp=2、Kv=2、Ki=.3、integral_limit=.5；tilt 参数8°是本候选预先选择的原算法配置。原算法对 XY 分别限倾角，合成倾角可大于8°；不改成另一限幅算法。完整实现来源、积分边界及 C++ oracle 见 `2026-09-09-pid-controller-port.md`。本任务确实实例化 `PositionPID`，接收原生估计状态并计算力和姿态；既有安装 Control 不需要安装 PID 库，仅消费公开姿态命令。

## 本轮悬停标定和外部控制权

每栈、每个全新 run 都必须先执行原生位置准备到 ENU `[2,3,3]`、yaw=0，维持既有 entry 门槛（.25m、.15m/s、轴倾角2°、yaw3°），采集连续3 s **原生 MAVLink ATTITUDE_TARGET collective**，用既有覆盖检查和 median 冻结该栈 hover。随后进行公开水平姿态2 s 验证：高度变化≤.3 m、垂直速度≤.2 m/s。标定结束后才构造 `NativeThrustConfig`，并写 `pid-resolved-config.json` 的 stack、mass、model_identity、真实样本、hover 与源时刻。绝不复用历史0.313/0.531示例、不取电机均值、不设默认 hover。

公共接口始终是 `session_v1` 的 `CommandRequest` / `UAVCommand(XYZ_ATT)`，att_ref=[roll,pitch,yaw,normalized collective]。AP 的 native mapping 为正 collective；PX4 native FRD thrust_body 为 `[0,0,-u]`；帧变换仍由已封存适配器完成。PID 保留原 `F_limited dot current_body_Z` 后再除以 `m*9.8/hover` 并夹 `[.1,1]`。这只是原 hover 附近线性映射，不声称与实际电机力曲线互为逆函数。

每个 PID stage 先复用 #34 PX4 新原生控制模式门与中性目标确认；AP 同样实际发一次中性 XYZ_ATT 并观察下游目标。运行中要求 fresh/armed、AP GUIDED 或 PX4 OFFBOARD、原 control epoch/native_generation、COMMAND_CONTROL；PX4 额外持续检查最新 VehicleControlMode 的 attitude/rates/allocation 真且 position/velocity/altitude 等假。AP 依赖先前 GUID_OPTIONS bit3 等参数实际读回、GUIDED 会话与实际姿态出口，未增加能等价于 PX4 VehicleControlMode 的新 AP 原生使能消息。此接缝仍需独立原始命令审计。

PID dt 是相邻**已消费的新鲜 public State 内原生 header 时间戳**差，不使用墙钟、不设假定40/200 Hz、不按中间实际未消费的样本补步。相同时间戳跳过；首拍仅建时间基准；负差、非有限或 dt>.2 s 清积分并失败，不 clamp。接管、退出、故障清积分；会话代次变化失败，禁止原 run 自动重置继续。轨迹参考使用模型物理接收 cursor 的 elapsed，dt 和参考时间基准均写入 trace，禁止把两个时钟当精确同钟。

最多一个公开请求等待 command_accepted，再用最新 native State 算下一输出；ack 最长 .2 simulated s / 2 wall s。逐拍不等待 native target matching，实际原生消费由 CDR / MAVLink 证据在后续独立审计逐窗确认。不要把 command_accepted 当动作完成或 native acceptance。此时序设计尚未在真实两栈验证，不能报告控制吞吐达标。

## 预声明窗口与阈值

所有 PID measured stage（包括 PID settling 段）仅发布 XYZ_ATT，`PIDTask.command` 在该阶段禁止准备/原生位置帮助函数。原生位置仅用于起飞/悬停标定准备、stage间恢复、最后落地，阶段标记明确 `measured_external_pid=false`。Task report 顶层使用 `external_pid`，不输出 `attitude_thrust` 完成报告；复用 observer 的 `attitude-native.jsonl` 文件名保留原意，不意味着本 run 做过 #34 步进实验。

| 阶段 | 固定参考及时间窗 | 判定预算 |
| --- | --- | --- |
| 定点 | `[2,3,3]` ENU、yaw=0；6 s settling 后4 s测量 | 3D位置误差≤.3 m、3D速度≤.3 m/s、yaw误差≤.15 rad |
| 小圆 | center=`[1.4,3,3]` ENU，R=.6 m，T=12 s，yaw=0；12 s settling 后12 s测量 | 3D位置误差≤.35 m、yaw误差≤.15 rad |
| 扰动 | `[2,3,3]`、yaw=0；先6 s PID settling，然后冻结下述唯一事件 | 整个事件声明后窗口误差≤.5 m；结束后8 s内恢复，最后固定1.5 s连续误差≤.3 m、速度≤.3 m/s、yaw≤.15 rad |

圆的第0秒和第24秒都在 `[2,3,3]`，避免位置 setpoint 跳变；第一拍非零速度和加速度前馈是协议的一部分。公式 p=c+R(cosωt,sinωt,0)，v=Rω(-sinωt,cosωt,0)，a=-Rω²(cosωt,sinωt,0)，ω=2π/12；真实 pos/vel/acc 三者都进入源 PID。移动参考触发原算法的积分清零规则，不予改写。

原包线保留：相对固定点距离≤4 m、height1.5..4.5 m、每轴roll/pitch≤15°。stage间 native position recovery 复用8 s timeout/1.5 s dwell/.4 m/.3 m/s/3°/3°，恢复指标不能算 PID 成绩。当前在线指标仅用原约20ms truth 采样，并明确 `online_ok`，全量1ms audit 尚缺；不得将它改名或汇报为完整flight PASS。

## 实际扰动及证据

`tools/pid_physics.py` 仅在该独立进程替换 adapter 的 Model 和输入解码观察函数；实际 native wrapper、固定1ms步进、报文解析实现、锁步和 sensor routing 不变。AP 保存完整原 SERVO16 字节/PWM16/解码input16；PX4 保存真实 `HIL_ACTUATOR_CONTROLS.get_msgbuf()` 字节、消息字段和解码input16。每个 physics step 保存最近实际源包、original_decoded_input16、applied_input16、output120、前后tick及扰动hash。PX4启动前无执行器包时可为null，不能伪造原始包；非空包是完整解析出的MAVLink frame，不冒称原TCP recv chunk。

在 disturbance settling 达6 s后，取 `origin_tick=ceil(latest_truth_time*1000)`，独占写 prepared 文件、fsync，然后hard-link原子发布 `disturbance-event.json`。JSON绑定run_id、固定协议hash、origin/start/end/permitted窗口、channels和multiplier，canonical UTF-8 字节、数值和字段全部固定。start=origin+2000，end=start+1000，permitted=[origin,end+8000)。physics首次装载必须距start至少1000tick；声明相对模型当前tick存在真实余量，过迟立即失败。

tick 指积分输入区间 `[tick,tick+1)`：**start含、end不含，恰好1000次1ms step** 对四路有效输入乘.97，后12路保持原值。公开位置/轨迹不因扰动改变，因此这是真实施加的输入扰动，不是setpoint step；也明确不是 #44 可配置电机效率/损伤参数验收。新run拒绝既有事件/撤销文件，tick必须逐次加一，原事件不能修改、删除、覆盖或第二次生效。故障写 `pid-disturbance-revoked.json` 后即停止施加；撤销是锁存的，删除撤销文件不能重启。事件保留不删除。

故障通过原公开LAND路径尽力降落，之后有界清理所有孩子和保存失败。不能保证所有飞行故障都正常落地；原生健康/通信已失败时仍可能只能 `unsuccessful_isolated_teardown`，结果不可标成功。

## 纯测试与尚未通过的接缝

`python -B -m unittest validation.test_pid_flight -v`：14项通过（Windows标准库，无ROS/native进程）。覆盖固定配置/UDE/NE/预算拒绝、真实PID force projection/两栈归一化、native时间戳重复与不连续、圆的一/二阶导、真实public XYZ_ATT envelope和请求/command id/ack门、原生位置旗标/代次拒绝、测量期间位置帮助函数拒绝、原AP数据包解码保真、恰好1000step四路扰动/后12路保留/实际消费输入、事件跨run/迟到/修改/重置/重复tick/撤销、指标违规以及CLI必选配置/launch plan。observer测试使用明确FakeModel输入记录器，绝不作为动力学oracle；launch plan使用mock，绝不作为实际启动证明。

下列接缝全部**待完成**，建议拆成可独立验收的小票，保留新run目录和原失败：

1. **只读准入复核**：在WSL执行两栈 `--preflight --config ...`，归档原始stdout/hash，核对 #34 封存Control/FC/模型/overlay实际身份、PID源副本和配置hash。任何准入不通过先定位，不替换默认profile、不偷偷重建安装包。
2. **实现独立原始审计器**：消费 `result.json`、run-source、pid-protocol/resolved-config、pid-progress、pid-trace、prometheus、原CDR/MAVLink、physics-actuator-packets及physics-1ms。逐条重算真实PID积分/力/投影/输出、公开request/command id到实际下游attitude/thrust，检查所有measure窗口没有native P/trajectory目标覆盖；AP/PX4各自 native执行记录必须对应真实输入。独立审计器不得只import调用在线evaluate_rows后返回同一结论。
3. **固定窗口1ms审计负例**：强制验证1ms连续覆盖和起止边界、不把receiver physical cursor当native acceptance time；验证圆参考时钟、原始公共payload、逐拍dt/reset和hover来自该栈该run；测试单tick超预算、错run、迟到事件、漏step、重复packet与held input、输入未真修改、PID标签却发XYZ_POS、outlet被原生位置环覆盖等拒绝。按冻结窗口重算所有物理阈值，保存完整失败，不能后移窗口。
4. **获单独RUN RELEASE后先单栈真实试验**：先PX4一轮，只验该轮，观察原始时序/标定/外部环行为并完成独立审计。当前最大不确定是Task ack驱动实际采样/新状态节拍、public-vs-model时钟差、原hover线性映射与未调参PID在该模型上的稳定性。真实失败意味着该轮失败；若改设计需另立协议和新轮，原数值门槛不默许放宽。
5. **另一栈独立真实试验**：AP须重新同run标定，核对GUID_OPTIONS、原生实际姿态执行、GUIA/RCOU和模型输入，不从PX4通过推导AP通过。单次通过不等于联合倍率/40Hz吞吐/Full。
6. **#35公开配置/UI接入**：本轮仅显式CLI试验入口；工作台选择PID、展示gains/mass/modelidentity/calibration、任务生命周期/重启状态、产品配置持久化尚未交付。任务层PID已运行不代表安装Control的正式controller feature完成。UDE/NE、联合、多载具和 #44 电机损伤各保留独立义务。

主代理可按最新目标转为Lunar接手计划。本交接未请求修改根AGENTS子代理模型政策；Lunar作为用户选择的接手者与该政策是不同事项。此文不自动授权任何真实运行。
