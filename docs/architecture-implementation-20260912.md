# 解耦实施与实际控制器对照

用户已确认按 [架构检查](architecture-decoupling.md) 的推荐实施。本轮完成独立固件候选、固件内环 LQR/MPC、跨载具模型接口、UE 视觉模块和实验/部署分离。结果是可运行的实验候选；没有将实验结果自动升级为正式兼容矩阵或硬件验收。

## 已完成的行为

| 范围 | 具体变化 | 验证 |
| --- | --- | --- |
| 固件内环 | PX4 在角速度计算位置选择原生 PID、等价 PID、LQR、MPC；ArduCopter 在原生 PID+FF 之后接管 RPY 输出 | 两栈各自的四个选择均完成真实 SITL 解锁、起飞、悬停、航点、降落 |
| 扰动对照 | 悬停阶段按模型权威时间，对第一个电机命令乘 0.97，连续 1000 个 1 ms 区间 | 两栈四种选择共 8 个扰动运行完成；逐区间核对只改变指定通道，随后恢复原输入 |
| 控制算法 module | 共用无 ROS/UE 依赖、无堆分配的 C++14 预测控制 implementation；各飞控保留自己的 native adapter 与设计数据 | 2 套设计、4,808 个离线输入、14,400 个标量输出对照；原生 PX4 PID 20,000 周期/60,000 标量逐位一致 |
| 模型 module | `VehicleModel.step(具名执行器, steps)` 输出统一 SI/NED/FRD `VehicleState`；原 16/120 C ABI 留在 Quad adapter 中 | 原四旋翼 250 组状态、6 组字段与旧接口完全一致；新增地面模型方程与接口测试 |
| 地面载具 | 独立构建 ArduRover，接 Ackermann 平地参考模型；车辆路径跟踪 module 输出速度/转向率，由 Rover 内环执行 | 两航点、停车等待、HOLD、解除解锁；首个通过运行的最终真值误差 0.1013 m |
| UE 视觉 | P450/Hex/车辆几何与资产读取移入 `WksimVehicleVisual`；引用放入 `Config/WksimVisualAssets.json` | UE5.5 编译、三个外观的实际 Actor 回读、截图及断流变陈旧检查 |
| 实验与部署 | 实验文件只选语义、机型、固件别名和算法；路径/SHA256 放到独立部署文件 | 两类真实运行入口；错误家族、载具、未知算法与不合法路径在启动前拒绝 |

主要实现：

- `Simulator/firmware/rate_control/`：纯算法、每栈设计数据、PX4/AP adapter。
- `Simulator/wksim_core/{vehicle_models,vehicle_state,actuator_layout,ackermann,rover_json}.py`：模型与原生物理通信分工。
- `Simulator/wksim_planning/ground_path.py`：车辆路径意图，不负责原生报文或动力学。
- `Simulator/ue55/Source/WksimVisual/WksimVehicleVisual.*`：只负责外观；GameMode 保留显示生命周期与版本化状态处理。
- `Simulator/wksim_runtime/experiment_bundle.py`、`tools/run_experiment.py`：解析、匹配和运行入口。

四旋翼的 PX4 旋翼分配参数改为从既有模型参数目录导出，数值保持一致。新增依赖也已加入相关实验的源码归档清单，避免重构后出现未记录的执行源码。

## 实际效果

下面是各自固件候选的**单次普通工况**描述性结果。RMSE 单位为 rad/s，顺序为滚转/俯仰/偏航。它不是统计优越性结论，也不能跨飞控直接排序：两栈原生航点偏航行为、活动区间和计时位置不同。

| 飞控/算法 | 角速度误差 RMSE | 记录的计算耗时 P99 |
| --- | --- | --- |
| PX4 等价 PID | 0.05877 / 0.08873 / 0.02389 | 0.402 μs |
| PX4 LQR | 0.05821 / 0.08885 / 0.02136 | 0.607 μs |
| PX4 MPC | 0.05850 / 0.08848 / 0.02149 | 14.477 μs |
| ArduCopter 等价 PID | 0.02642 / 0.03168 / 0.32864 | 0.956 μs |
| ArduCopter LQR | 0.02355 / 0.04149 / 0.28613 | 1.337 μs |
| ArduCopter MPC | 0.02347 / 0.04146 / 0.28594 | 3.829 μs |

ArduCopter 的 LQR/MPC 在这组输入中降低了滚转与偏航误差，但增加了俯仰误差。扰动工况也呈现类似取舍。更换算法需要通过实验判断收益，不能仅依据算法名称。

主要对照矩阵为 **16 次真实 SITL 运行**：2 个飞控 × 4 个选择 × 普通/扰动。LQR/MPC 活动区间没有回退；约 **11.8 万个实际输出**由独立计算复核，最大误差小于 `4e-7`，门槛为 `1e-6`。8 次扰动均核对到完整 1000 个区间。启动地面阶段的已记录回退没有混入算法生效区间。

PX4 的活动区间按 armed 且非 landed 统计。AP 按 armed 且电机 spool unlimited 统计，是空中工作的保守超集。AP 保留上游 PID 计算并覆盖输出，其计时记录只覆盖附加观察/算法，不能拿该耗时与 PX4 或硬件总任务时间直接比较。

## 算法与适配约束

LQR 使用悬停附近的两状态模型：角速度误差与角加速度。模型包含电机响应；PX4 yaw 还以一阶近似包含原有 2 Hz 输出滤波。每栈的控制分配尺度、推力曲线与惯量分别绑定；输出是各自归一化控制量，**不是未经转换的 N·m**。

MPC 是 12 步、4 ms 周期的线性、逐轴 box-constrained MPC，终端成本来自离散 Riccati 解。采用有界次数坐标下降，独立对照使用另一种 active-set QP 求解。原始试验中的 `±0.3` 控制量约束未在活动区间触发；约束行为已在离线大输入病例中检验，本轮不据此宣称飞行约束极限已验证。

AP 候选显式固定 250 Hz 和推力曲线参数，两个算法共用这一工况。其角加速度来自 gyro 差分与 25 Hz 滤波。两栈保留原估计器与控制分配；物理真值用于验收，没有替换实时估计反馈。

算法选择在进程启动时固定。时间不匹配、求解失败或超过 500 μs 附加计算预算会记录明确的 PID 回退；活动区间出现回退则该对照失败。本轮没有验证飞行中切换算法、任意动态库导入、非线性 MPC 或目标飞控硬件算力。

## 使用新的实验入口

从本仓库根目录执行：

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'

# 只解析与检查组合，不启动仿真。
python tools/run_experiment.py Simulator/wksim_runtime/examples/experiments/rate-control.json --deployment Simulator/wksim_runtime/examples/experiments/local-deployment.json

# 实际执行 PX4 的四种内环选择。
wsl.exe -d Ubuntu-22.04 --exec python3 tools/run_experiment.py Simulator/wksim_runtime/examples/experiments/rate-control.json --deployment Simulator/wksim_runtime/examples/experiments/local-deployment.json --execute

# ArduCopter 与其扰动对照分别使用 copter-rate-control.json、copter-rate-disturbance.json。
# PX4 扰动对照使用 rate-disturbance.json。

# 地面车辆实际闭环。
wsl.exe -d Ubuntu-22.04 --exec python3 tools/run_experiment.py Simulator/wksim_runtime/examples/experiments/ground-waypoints.json --deployment Simulator/wksim_runtime/examples/experiments/local-deployment.json --execute
```

`local-deployment.json` 是本机部署示例，包含本机候选路径与 SHA256，不是可在其他电脑直接使用的发布包。更换新候选时只调整部署引用；实验意图可以保留。新固件版本仍需检查 native adapter 的源码接入位置、参数/消息语义，再构建并验收，不能只更换一个哈希放行。

构建入口为 `tools/rate_control_candidate.py build`、`tools/build_ap_rate_candidate.py` 和 `tools/build_rover_candidate.py`。它们各自建立独立源码/构建目录与收据，保留原候选。UI/正式兼容矩阵继续执行原有准入；本轮使用独立候选与明确的实验入口。

## 载具与视觉的后续扩展方式

地面参考模型明确是平地、有限速度与转向响应的自行车模型，不含轮胎滑移、悬架、复杂接地或地形。它已足以作为第二类真实 adapter 验证 module 的 seam；固定翼仍需实际气动来源、舵面布局、适用固件与工况，新接口不会把 `fixed_wing` 当作已支持项。

执行器按每个通道声明正值/有符号域；因此固定翼的正油门与有符号舵面无需共用一个“四旋翼油门”约定。固件家族与固件目标分开匹配，ArduCopter、Rover、Plane 不能因都来自 ArduPilot 而互换。

视觉 profile 选择与模型实现分开。资产路径由 JSON 目录管理，几何创建由视觉 module 管理；兼容位姿契约的地面模型版本不需要修改 GameMode。诊断输入明确标记为 FIXTURE，回放标为 REPLAY，避免把测试位姿称为真实物理运行。现有 joint/Hex 协议的来源身份与陈旧检查继续保留。

## 故障与保留证据

Rover 原生 SCurve 航点在本参考模型上越过目标后停止，没有满足位置门槛。该失败未被改成通过，也未放宽阈值；默认实验采用独立的曲率受限路径跟踪，向 Rover 原生速度/转向环发送目标，并在到点后明确停车保持。`--path-controller native_scurve` 保留复现入口。

源码核对还发现当前 AP 参数为 `ARMING_SKIPCHK`，旧 `ARMING_CHECK` 不再存在。新车辆配置使用 `ARMING_SKIPCHK=0`，并逐项回读原生参数确认，没有跳过检查或强制解锁。

本机证据位置：

| 证据 | 路径 |
| --- | --- |
| PX4 普通/扰动 | `validation/inner-loop-comparison-m7zy85gm/`、`validation/inner-loop-comparison-w2tz8gs_/` |
| AP 普通/扰动 | `validation/inner-loop-comparison-5joblsko/`、`validation/inner-loop-comparison-snwv1ei_/` |
| 独立数值复核 | 上述目录的 `independent-audit.json` |
| PX4 原生逐位对照 | `validation/native-rate-equivalence-apwp355c/` |
| 两栈 QP 离线对照 | `validation/predictive-rate-k3g_h41p/`、`validation/predictive-rate-ummd_zjz/` |
| 首个车辆闭环通过 | `validation/rover-reference-767zzqz1/` |
| 可移植入口车辆复测 | `validation/rover-reference-qo55xmyt/`，最终真值误差 0.0990 m |
| 最终 UE 构建/三外观检查 | `validation/ue55-build-796040e8260c4da283bccea5939963d1/`、`validation/visual-profiles-j92hcyco/` |
| 模型接口等价 | `validation/architecture-decoupling-20260912/quad-model-adapter-equivalence.json` |
| 汇总与最终校验 | `validation/architecture-decoupling-20260912/` |

这些验证目录、固件构建、模型二进制和 UE 资产仍是本机产物。模型源码/二进制的再发布许可没有因本轮试验改变。没有修改其他任务的规划器、调度或协作文件，也没有替换现有已发布验收结论。

最终相关离线回归共 152 项：146 通过、6 项依赖指定资源而跳过。Codebase Memory 已刷新并定位新的 `VehicleModel.step`；本轮索引日志为 `C:/CBMData/logs/wksim-prometheus-1789200511.log`。图的部分解析与排除仍是覆盖限制，不能用索引规模代替功能验收。
