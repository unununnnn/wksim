# wksim 自主模型运行核心：双飞控 SITL 首个实现

已实现一个可独立编译的模型宿主，并用真实 PX4 / ArduCopter 完成起飞、悬停、航点和降落测试。**这不是完整 CopterSim、Prometheus ROS2 移植或 UE5.5 交付。** 此入口仅允许本机回环 SITL，不用于真机。

构建使用本机保留的 `MulticopterModel.zip`；运行使用自行编译的 Linux `.so`，不调用原版 CopterSim.exe、闭源模型 DLL、Gazebo 或 MATLAB。厂商源码只解包到 WSL 临时目录，不收入仓库；当前没有确认其再发布许可。首次构建仍需要该本地 ZIP，不能声称仓库已能在没有本地资源的机器上完整自举。

## 在本机复现

需要已存在的 Ubuntu-22.04、G++、Python3、pymavlink 2.4.49，以及报告中固定的 PX4/ArduCopter 构建。下面命令均已实际执行；不会安装软件。

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'
wsl.exe -d Ubuntu-22.04 -- python3 -m unittest validation.test_wksim_core -v
wsl.exe -d Ubuntu-22.04 -- python3 tools/probe_generated_model.py
wsl.exe -d Ubuntu-22.04 -- python3 tools/validate_sitl_physics.py --stack arducopter
wsl.exe -d Ubuntu-22.04 -- python3 tools/validate_sitl_physics.py --stack px4
```

每个飞行命令会在全新目录构建模型、启动对应飞控、执行测试并回收自己创建的进程。`validation/<stack>-physics-*/result.json` 保存阈值、版本、源码/产物哈希、命令与结果；同目录的 `truth.jsonl`、`telemetry.jsonl` 和日志供复核。飞控自身日志保留在结果记录的 WSL `run_dir` 下。旧测试与用户原有进程不会被清理。

本机现已补齐 ROS2 Humble、原生 Agent 和启用 DDS 的独立 AP 构建。同域双飞控原生 DDS 任务与地面 Agent 重连也已通过：

```powershell
wsl.exe -d Ubuntu-22.04 --exec python3 -m unittest validation.test_wksim_core validation.test_sitl_dds -v
wsl.exe -d Ubuntu-22.04 --exec bash tools/run-dds-validation.sh both /root/wksim-dds-VxM6Ni
```

该入口把两套飞控、Agent和观察节点放进同一个独立网络命名空间。无需重新安装，细节和准确版本见 [原生DDS报告](../../docs/2026-09-05_native-dds-report.md)。它是接入诊断，不是 Prometheus 业务控制包的替代品。

命令返回 0 仅表示该物理集成门槛通过，不能替代原版数值对照或全部功能验收。失败时先查看结果的 `error`、`physics.log`、飞控日志及最近的 `STATUSTEXT`；不要通过关闭解锁检查或强制解锁来绕过故障。

## 实现分工

| 文件 | 职责 | 当前边界 |
| --- | --- | --- |
| [model.py](model.py) / [model.cpp](model.cpp) | 哈希校验、构建、模型生命周期和 C ABI | 固定 1 ms 步长，四旋翼 X；静态共享参数要求每机独立进程 |
| [ap_json.py](ap_json.py) | ArduCopter JSON 执行器/传感器闭环 | 16 通道报文，前4路电机；原生 NED/FRD；回环 UDP |
| [px4_mavlink.py](px4_mavlink.py) | PX4 HIL_SENSOR/HIL_GPS 与执行器闭环 | 每4个模型子步一帧IMU，250 Hz；启动后要求 lockstep；回环 TCP |
| [arducopter-quad-x.parm](arducopter-quad-x.parm) | AP 固定机型及 PWM 标度 | 保留正常解锁检查；叠加于 AP 官方 copter.parm |
| [px4-rc.mavlink](px4-rc.mavlink) | PX4 官方 rcS 的 PATH 扩展点 | 独立遥测端口，避免默认地面站分发；不改 PX4 原安装 |
| [validate_sitl_physics.py](../../tools/validate_sitl_physics.py) | 同一测试流程调度两栈 | 默认MAVLink诊断；DDS入口切换为原生指令，无飞行命令回退 |
| [sitl_dds.py](../../tools/sitl_dds.py) | 原生DDS诊断接口 | AP服务/全局位置话题、PX4指令/设定值话题及新响应 |
| [validate_dual_dds.py](../../tools/validate_dual_dds.py) | 同图双任务与独立观察 | 等待两机就绪，核验唯一发布端、状态新鲜度和同时解锁 |

AP 本机配置使用 physics UDP 19002、遥测 UDP 14660、system ID 241、实例11；PX4 使用 physics TCP 4581、遥测 UDP 14661/18591、system ID 22、实例21。启动前检查占用。两栈使用独立工作目录与模型进程；不可在同一端口重复启动同栈命令。

默认物理诊断不启动Agent；PX4 rcS会向专用18888端口尝试DDS连接，AP默认仍选原先未启用DDS的产物。DDS入口则使用独立编译的AP二进制、AP Agent端口12019、PX4端口18888、namespace `wksim_px4_21` 和domain77，并保留各自的物理/遥测端口。新AP路径是 `ap-dds-build/sitl/bin/arducopter`，不能误选私有源码副本中残留的旧 `build/sitl` 产物。

## 已处理的接口细节

- 输入为归一化电机命令，AP 的1000–2000微秒先转换；两栈的电机顺序与此模板一致，单电机力矩方向已测试。
- `Vehicle[24:27]` 是机体系速度导数，不是加速度计比力；传感器接口使用 `HILSensor30d` 的对应通道。四元数为 wxyz，位置/速度为 NED，角速度和比力为 FRD。
- AP 启动首帧实际报1200 Hz，即使启动参数为1000。官方允许后端自选步长；本实现始终推进1 ms并用时间戳反馈，不把提示频率误当已生效的仿真时钟。重复帧重发缓存，帧断序停止。
- 模板 GPS COG 使用 `atan2(north,east)`；PX4 适配边界按 MAVLink 定义从NED速度计算从北顺时针的COG，不修改厂商模型。已有北/东/西航向测试。
- PX4 采用该模型实际臂长和反扭矩比配置控制分配；未使用 Gazebo 物理或 SIH 内置动力学。物理连接中断后停止推进，正式重连/故障策略仍未验收。
- DDS模式下的PX4使用仿真时间戳并关闭Agent墙钟同步，防止3倍速时指令被误判陈旧；不关闭飞控失联保护。AP原生位置按源码转换ENU/NED，不仅依赖其 `base_link` 帧名。

## 后续与依据

双原生DDS固定任务与地面Agent重连、[UE5.5权威位姿实际显示及断流恢复](../../docs/2026-09-05_ue55-report.md)已验证；现有21项自动检查通过。UE入口见[显示模块说明](../ue55/README.md)，仍为四旋翼接入几何体和本机诊断桥。下一步迁移Prometheus消息/控制/实验并定型ROS2运行组织。MATLAB接口、原版DLL可选导入、数值对照、所有机型/模式/环境/界面/故障与性能覆盖仍保留在完整目标中。

见 [双飞控验证报告](../../docs/2026-09-05_sitl-physics-report.md)、[完整功能范围](../../docs/coptersim-reconstruction.md)、[ROS2准备调研](../../docs/research-ros2-bootstrap.md)、[Wayfinder验证票](https://github.com/unununnnn/wksim/issues/7)。接口依据是 [ArduPilot JSON定义](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.h)、[PX4 simulator_mavlink源码](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp)与本地模型源码；图索引仅用于导航。
