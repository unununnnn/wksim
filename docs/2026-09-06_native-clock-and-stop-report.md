# 联合调度前置：原生时钟偏差与 AP 停机等待

2026-09-06 JST。延续[#8决策前有界验证](https://github.com/unununnnn/wksim/issues/8)；不修改生产调度、固件、准入哈希或原厂安装，不关闭#8/#19/#20/G2。

## 本轮改变了什么结论

两个新隔离实验都完成了真实双飞控共同模型步进、暂停、4ms单步与恢复，但**原生飞控时间不能直接视为精确同一时钟**：

| 证据 | 首轮 `joint-native-clock-q2bqs_u6` | 重复 `joint-native-clock-_2z0vuw0` |
|---|---:|---:|
| 每机实际1ms模型步 | 10,004 | 10,004 |
| 严格4ms输入边界 | 2,487，首次tick60 | 2,487，首次tick60 |
| AP原生微秒样本 | 389 | 386 |
| 与AP源码累计公式精确匹配的样本 | 389/389 | 386/386 |
| AP已观测匹配步的时间亏差 | 48–1,820µs | 48–1,820µs |
| PX4原生位置时间样本 | 477，全部落在整数毫秒网格 | 476，全部落在整数毫秒网格 |
| 两次暂停墙钟秒 | 2.014662 / 2.017772 | 2.002445 / 2.002903 |
| 实验总墙钟秒 | 23.151 | 23.796 |

AP原始CDR消息中的 `time_boot_us` 与 `header.stamp` 相互一致，但所有这些时间均偏离理想1ms网格。源代码累计公式的亏差从48µs变化至1,820µs，**不能靠一个常量启动偏移修正这组样本**。此结论由真实消息与实际发送模型时间序列的对应关系得出，不是对两个日志作事后对齐；没有改写原生或模型时间。

同一时刻的样本源时间与接收时刻还存在传输/调度延迟。首轮AP/PX4最大“当前模型时间−接收样本源时间”为3,820/10,000µs，重复为3,820/9,000µs；它们包含样本年龄，**不是飞控时钟误差预算**。没有据此放宽任何数值验收门槛。

独立停止侧线还确认：固定AP在传感器停流后接收SIGTERM，退出标志已为1，却仍在JSON收包重试，不能回到外层退出判断。不再发信号、只恢复合法的真实传感器输入，两个被测场景均再推进2个1ms步并退出0。SIGINT退出-2不能称为正常清理。见[13次诊断与完整限制](2026-09-06_ap-shutdown-diagnosis.md)。

## 实现与只读观测边界

- [原地面探针](../tools/probe_joint_clock.py)新增显式 `--native-clocks`，默认地面握手模式保留；[原隔离入口](../tools/run-joint-clock-probe.sh)转发参数。观测模式使用两个已有固定Agent和一个主进程内只读ROS节点，不启动Prometheus控制节点或任务。
- [NativeClockObserver](../tools/joint_clock_observer.py)只建立四个订阅：`/ap/wksim/local_state_v1`、`/ap/status`、`/wksim_px4_21/fmu/out/vehicle_local_position_v1`、`vehicle_status_v1`。使用BEST_EFFORT、VOLATILE、depth20，`spin_once(timeout_sec=0)`；不等新DDS样本来放行下一物理步。
- 实际节点图及源码共同检查：无飞行控制发布者、无服务客户端。rclpy自己的 `/parameter_events` 是允许的框架元数据发布，不是飞行命令；`use_sim_time=false`。没有发布任何权威 `/clock`，不把这个观测节点说成生产时钟发布者。
- 日志包含原始序列化CDR、准确订阅topic、抽取字段、回调时的模型tick、单调接收时间。未用假状态替换实际消息；无效姿态中的非有限字段保留在CDR，不强行变成有效位置数据。
- AP原生header与boot微秒必须完全一致；PX4原生system_id必须22；两栈状态保持未解锁；抽取的启动时钟不可回退或超过已经发送的物理时间。后者是测量边界，不是DDS延迟预算。
- 从本轮开始，每次实验保存当时实际执行源码快照及SHA256，连同失败包、源模型、启动参数、预检、原始物理状态和进程身份一起归档。上轮早期失败缺源码快照的事实不被追溯改写。

原始物理仍为单一父进程的整数tick，两份模型各在独立进程中运行。本轮每次共两个模型、两个飞控、两个Agent，全部为新建进程组；没有与已结束的AP停机侧线同时运行。AP的next-frame仍仅为JSON接收流程确认，不能升级为控制器计算完成ACK。

## 原生时钟偏差的一手来源与对照

实际源码和固件与前一报告一致：PX4 commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`，二进制SHA256 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`；AP commit `1511f27194f1dcc3728270883047bdf022b3fd53` 及既有DDS patch，二进制SHA256 `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5`。每次预检仍检查固定模型、消息/控制安装包与Agent身份，没有为新观测绕过准入。

AP的实际 `libraries/AP_DDS/AP_DDS_Client.cpp:54–63` 把 `AP_HAL::micros64()` 写入 `WksimState.time_boot_us` 和header；该字段由已存在的本地patch提供，不冒称upstream字段。`1962–1966` 的发布门槛是20ms，因此它不可能给每个4ms边界提供即时新样本。具体版本/字段来源见[上一轮AP源码研究](2026-09-06_joint-clock-source-research.md)。

固定 [SIM_JSON.cpp:499–521](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_JSON.cpp#L499-L521) 将外部double秒的相邻差乘1e6后复合累加到uint64微秒。主代理另复读 [Aircraft::time_advance](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/SITL/SIM_Aircraft.cpp#L249-L264)：常规正1ms增量已经改变模型时间，不会再补一个frame_time。HAL在更新模型后采用其时间；[HAL微秒接口](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_HAL_SITL/system.cpp#L163-L188)返回这个非零仿真时钟。

观测器内的 `ap_counter_recurrence` 只是该binary64/整数表达式的离线算术指纹，不驱动物理、飞控或任务。对每次**真实模型输出并发送过的**时间序列计算预测网格，再比对未经改写的真实CDR时间值：775/775个AP样本精确命中，匹配模型tick不晚于接收tick。这强力支持固定构建下累计量化造成偏差；不声称Python公式是独立重建飞控，也不把有限时长推广为任意时长/任意步长的保证。

PX4的 [VehicleLocalPosition schema](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/msg/versioned/VehicleLocalPosition.msg#L1-L7) 明确timestamp/timestamp_sample为启动微秒，版本1。主IMU设置虚拟CLOCK_MONOTONIC的源码与执行器时间证据仍见[前置报告](2026-09-06_joint-clock-ground-report.md)。此次只对测得样本和原有严格输入边界作结论，不扩大到所有PX4控制组件。

## 停机根因与主代理复核

侧线按diagnosing-bugs先建立实际可变红的单AP+真实模型反馈命令，缩短前置至2000tick；1000tick缺未解锁心跳，被判INVALID而非“修复”。六次有效“停流TERM且不恢复”均RED/-9；两次停流TERM后恢复均先RED再exit0；两次持续流TERM均exit0；两次INT均-2。全部13次及一次不完整的调试器身份取证保留。

主代理读取完整探针/隔离入口，并复读实际 [GDB原始记录](../validation/ap-shutdown-hz_ha1zu/gdb.txt)：AP主线程确在JSON接收链，退出标志字节为1，调试器正常detach。无GDB对照 [c6c6wjas](../validation/ap-shutdown-c6c6wjas/result.json) 在信号等待5.000379秒仍RED，恢复真实传感器后约5.021ms、tick2000→2002、AP exit0。主代理重新执行离线审计，产物 `validation/ap-shutdown-audit-fltci7fv/audit.json`，13份原始证据全部哈希和包级检查通过，记录的AP/调试器PID均已不存在。

本轮没有把“停机时多走两步”偷偷集成到联合场景，也没有把SIGINT当成优雅停止。仅诊断边界来自主代理本次委派，不否定用户对完整移植实施的总体授权；具体暂停/停止时间语义仍待#8确认。

Ptolemy代理 `01a07383-d73c-74c0-b231-5305cb6416f3` 显式选定并由主代理从实际turn_context核验gpt-6-astra/low；无嵌套，独占AP诊断工具/单一研究报告，已释放实测资源并关闭。主线串行运行双飞控原生观测。

## 复现、哈希与未完成项

```bash
# WSL Ubuntu-22.04/root，仓库目录；每次新建隔离网络和证据目录
bash tools/run-joint-clock-probe.sh --native-clocks
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test*joint_clock*.py' -v

# 仅离线CDR审计，不启动ROS节点/飞控：先加载与实测相同类型环境
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-MUlZd0/install/local_setup.bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/audit_joint_clock_probe.py validation/joint-native-clock-q2bqs_u6 --verify-current-sources
PYTHONDONTWRITEBYTECODE=1 python3 tools/audit_joint_clock_probe.py validation/joint-native-clock-_2z0vuw0 --verify-current-sources
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_ap_shutdown.py --audit
```

9项纯边界检查通过；两次双栈原始记录/CDR审计通过。没有因本轮而重称全产品回归或飞行验收完成。旧报告的 `--verify-current-sources` 证明的是其当时源码；本轮新增观测后旧脚本哈希自然改变，可用保留的哈希/快照区分版本，不改写历史结果为“当前源码运行”。

两个原生观测 `result.json` SHA256：`d410df00198f3f2a85fb477a5ad846e8973c456edbffc02aeab0aa94fb450b23`、`b31b517b0bd5cd39ba953d1682dbdda1cb0bd3059cdf56643de292c58b31fbc1`。审计源码SHA256 `1b3c2ccd79dfacc6f2b96b8258be665f1f372f535599c4c359ca4dfbf7771309`。十二个自建双栈实验进程组均完成清理；AP仍使用超时SIGKILL，不能声称停机问题已修复。

末次集成复核归档于 [integration.json](../validation/native-clock-integration-20260906/integration.json)，包含两次完整审计指标/哈希、13次AP结果映射、实际代理配置、末次内核PID/PGID及原AP/UE身份、9项测试输出和精确索引覆盖。07:06 JST检查十二个双栈PID/进程组无匹配，后续复查十三个AP诊断PID/进程组及已记录GDB PID也均不存在。Codebase Memory仍ready、92,892节点/202,270边；本轮工具与文档均按祖先目录排除/not_tracked，直接读源，不将其声称为已索引实现。

暂停期间两次实验均没有新原生DDS样本交付；不以沉默证明整个飞控/DDS进程冻结。实时通信/日志线程、模型时间、控制循环完成、公开ROS时钟和显示时钟继续分开看待。P450视觉资源、原AP/UE、产品控制代码和安装包均未改动。

## 待用户确认的生产候选（尚未采纳）

建议首期定义为：**1ms权威物理步、4ms传感器/执行器输入边界；允许各控制器按自身频率计算，不能把边界称作两者都完成一次新控制计算。任一参与飞控超时则停止整场景推进，显式恢复前不补发历史控制动作；冷重置使用新epoch并重新就绪。停止不额外推进已暂停的物理时间。**

为满足这一候选，应先在独立可重建AP候选中验证“整数微秒时间累计”和“等待可中断”的最小修正，保留当前固定构建作负对照。新候选须重新通过准入/正常飞行/暂停/停止证据后才能进入生产，不覆盖现有安装或放宽哈希检查。ROS任务虚拟时间、墙钟监督、掉队超时数值/重连条件及复位动作需在#8最终契约中明确，不由地面观测隐式决定。

此候选不修改兄弟AeroTwinSim的Gazebo/逐控制周期新输出ADR，也不将它们自动套给wksim；遵守本迁移已确认的自主物理分工。#8未决，#6数值预算/#5MATLAB操作范围/#9插件与环境反馈不变；Full Goal保持active。
