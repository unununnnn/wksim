# 双飞控自主模型 SITL 集成证据

2026-09-05。本报告记录一个已实现的物理集成阶段，不是完整产品完成声明，也不是原版 CopterSim 数值等价结论。Prometheus 仍是移植主体；本轮只新增其仿真后端，业务控制模块的 ROS2 迁移尚未完成。测试仅在 Ubuntu-22.04 的回环网络运行，未执行或修改厂商原版EXE/DLL，未启动 Gazebo/MATLAB/UE。

## 结果与固定门槛

已用同一份自行构建的六自由度模型，分别完成真实 ArduCopter 与 PX4 的正常解锁、3米起飞、5秒保持、NED `[3,2,-3]` 航点、2秒航点保持、降落与上锁。两套飞控均使用各自估计器和控制器；脚本没有代替飞控直接给出起飞油门。

门槛在运行前写入验证器并保存于各次 `result.json`：达到2.5米以上；初始5秒保持段高度误差≤0.6米、横滚/俯仰绝对值≤0.35弧度；航点三维位置误差≤0.5米、速度≤0.5米/秒并保持2秒；降落后上锁且估计/真值高度绝对值≤0.3米。该集成测试不测厂商对照误差；用户确认的固定工况数值对照还需另立工况与误差预算。

| 证据 | 飞控 | 仿真时长 | 最高真值高度 | 航点最小真值距离 | 结果 |
| --- | --- | ---: | ---: | ---: | --- |
| E-AP | ArduCopter4.7.0 | 65.04 s | 3.0091 m | 0.0163 m | pass |
| E-PX | PX4 v1.17.0 | 30.80 s | 3.0980 m | 0.0498 m | pass |
| E-DUAL-AP | 并行复测 ArduCopter | 65.04 s | 3.0091 m | 0.0182 m | pass |
| E-DUAL-PX | 并行复测 PX4 | 30.78 s | 3.0878 m | 0.0415 m | pass |

AP保持段最大估计高度误差0.4054米、最大倾角0.00457弧度；PX4分别0.4918米、0.00474弧度。此保持段从达到2.5米起算，包含接近3米设定值的收敛过程，不应称为已完成稳态精度评估。

## Evidence：可复现输入与输出

- E-AP：[ArduCopter结果](../validation/arducopter-physics-a01tdin8/result.json)，SHA256 `8b575368345bf359d174f60fcfd5f30833d539e438142e8322a98fedb5674576`；同目录含逐帧真值、MAVLink遥测、模型与飞控日志、实现哈希。复现命令见下。
- E-PX：[PX4结果](../validation/px4-physics-1h91oc9v/result.json)，SHA256 `a50f7202902da9d24d71bcf44e6d4a2d0845437818c699bbdea1abd32a260066`；同目录含真值与遥测。该次验证器尚未添加实现文件哈希字段，但已记录模型构建及PX4配置/二进制哈希。
- E-MODEL：[原有单模型回归](../validation/generated-model-533f975u/result.json)，SHA256 `e2bf2d7c86772f459bf514794976e45238721daa9a2f75843740fd23e7dab4b5`；迁移构建逻辑后仍通过3个2000步工况，得到相同可执行文件哈希，原ZIP未改动。
- E-SOURCE：输入 ZIP SHA256 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`，源接口/单位核对与旋翼方向测试见 [运行说明](../Simulator/wksim_core/README.md)；[12项自动化测试](../validation/test_wksim_core.py)已运行通过。源码位于本机原始ZIP，未随仓库再发布。
- E-DUAL-AP：[并行AP复测](../validation/arducopter-physics-v5_k6ybd/result.json)，SHA256 `5c84280e9fd063f630d014d31f1357c6ae8b1857fc0a116da293519a3e05202f`。
- E-DUAL-PX：[并行PX4复测](../validation/px4-physics-ya70gyd2/result.json)，SHA256 `093fe2c22d7cc53df448f5d04117634cc19466da5992c56762d7be9b60ca9b21`。两条相同命令通过工具并行启动，使用独立端口、system ID和工作目录，两组子进程均回收；原有AP实例PID828在测试后仍运行。这证明本次双物理实例可共存，不证明DDS命名空间或多机性能验收。

上述日期均为2026-09-05，精确 UTC 记录于结果JSON。飞控源码HEAD为 AP `1511f27194f1dcc3728270883047bdf022b3fd53`、PX4 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`；PX4已有本地改动，未清理或重建，已测对象以结果中的二进制SHA256为准，不宣称它等同于未改动的上游构建。工具复用 Ubuntu22.04.5、GCC11.4、Python3.10、pymavlink2.4.49，没有为该阶段安装依赖。

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'
wsl.exe -d Ubuntu-22.04 -- python3 -m unittest validation.test_wksim_core -v
wsl.exe -d Ubuntu-22.04 -- python3 tools/validate_sitl_physics.py --stack arducopter
wsl.exe -d Ubuntu-22.04 -- python3 tools/validate_sitl_physics.py --stack px4
```

复现仍依赖本机合法保留的模型ZIP和上述飞控构建，不等于无外部源码的可再分发产品。每次记录新的路径和哈希，不覆盖这里的历史证据。

## Finding 与已执行路径

F-CORE：E-SOURCE、E-MODEL、E-AP、E-PX共同证明：这份本地保留模型可经wksim自己的构建/调度/传输代码驱动两套真实飞控，不需要Gazebo、原版CopterSim或MATLAB运行时。结论仅覆盖该机型和测试工况。

P-AP：官方AP控制器 → JSON二进制PWM帧 → wksim PWM归一化 → 1ms模型步进 → JSON惯性/位置/姿态/速度 → AP估计器与控制器（E-AP/E-SOURCE）。

P-PX：PX4控制器 → HIL_ACTUATOR_CONTROLS → wksim四个1ms子步 → 250Hz HIL_SENSOR和10Hz HIL_GPS → PX4估计器与控制器（E-PX/E-SOURCE）。PX4 OFFBOARD保活与AP GUIDED行为由测试入口分别处理，不把两套控制状态机假装成同一套。

第一次AP接入因代码误将首帧1200Hz提示当作错误而停止：[失败记录](../validation/ap-physics-nqooyyoj/result.json)。按官方JSON接口允许固定物理步长的约定修正后通过，并加入回归测试；没有放宽飞行门槛。PX4边界还修正了模板COG方位定义并加入北/东/西测试。原始模型未改动。

## 未完成与下一阶段

截至本报告记录的物理测试，ROS2与Agent尚未安装，AP现有产物未启用DDS；本次MAVLink任务诊断不能称为DDS验收。UE5.5没有参与本次运行，Prometheus消息/任务迁移和MATLAB接口也尚未实现。原版DLL可选导入、全机型、GUI、环境/碰撞、复位/暂停/步进、多机规模性能、正式断连重连策略、完整版全部模式及数值对照仍待实现。

下一阶段从已通过的物理后端接入双原生DDS，而不是更换移植主体或回到Gazebo。依赖缺口详见 [ROS2调研](research-ros2-bootstrap.md)；[Wayfinder验证票](https://github.com/unununnnn/wksim/issues/7)保持开放。

后续更新：同日已安装Humble、隔离构建DDS工具链，并通过同图双原生DDS任务和地面Agent重连。该阶段独立记录在 [原生DDS报告](2026-09-05_native-dds-report.md)，不回写或冒用本报告的历史测试证据。
