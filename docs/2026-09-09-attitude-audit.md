# #34 双栈首轮独立原始审计：均未通过

2026-09-09。PX4 首轮在固定姿态跟踪窗失败；AP 首轮姿态阶跃通过，随后恢复触发倾角包线。两栈都走公开 failure LAND 并到达地面，进程均回收；未执行推力阶跃，不能关闭 #34。在线 `observed` 也只表示观察完成，审计器不会据此自动给 PASS。

实现为 `tools/audit_attitude_flight.py`、`validation/test_attitude_evidence.py`。本审计只读取已终结运行和封存来源，没有启动飞控、模型、ROS 节点或发布运动命令，没有修改预算、运行原件、控制候选或生产准入。采用 ponytail；主代理已实读验证本代理 `gpt-6-astra/high`，无嵌套委派。

## 固定证据和方法

原始目录：

- PX4：`/root/wksim-attitude-flight-px4-20260909-01/attitude-px4-01`。
- AP：`/root/wksim-attitude-flight-ap-20260909-01/attitude-ap-01`。
- 审计 JSON：`/root/wksim-attitude-audit-px4-verified.json`、`/root/wksim-attitude-audit-ap-verified.json`。JSON 保存逐文件证据 SHA256、实际 decoder 版本/路径、完整原生阶跃时间线、逐项检查和错误；失败审计退出码为 1。

冻结预算 SHA256 为 `9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f`。模型为原准入 generated quad-X 1 ms 原生库，SHA256 `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`；不从两栈 collective 数字相近推断同推力、加速度或硬件标定。

审计先核对每轮 admission/config、逐运行保留源文件、启动 argv、实际 firmware/Agent、安装 Control Python 和 maps。原始 CDR 使用本轮生成消息的实际安装路径和包哈希解码；AP 使用新 attitude overlay，不能套用旧消息包。原始 MAVLink datagram 由记录中 SHA 固定的各栈 dialect 重解码，并与已记录解码值逐条对照。公开请求的浮点数按真实生成 codec 量化后比较，避免把 float32 编码舍入误认成篡改。

PX4 ULog 使用私有目录 `/root/wksim-attitude-audit-deps-g_2y8olg` 中的 [PX4 pyulog 1.2.2](https://pypi.org/project/pyulog/1.2.2/)；`--no-deps --target` 安装，复用既有 numpy，没有改全局或 ROS 包。原生格式依实际 ULog 字段读取。AP BIN 使用已有 pymavlink 实际 FMT，姿态日志的真实名称是 **GUIA**，不是字面 `GUA`。

全部物理记录检查连续 1 ms tick、每组完整性、组内 16 路输入保持、120 路有限输出、下采样原 trace 输出完全相等以及相应 PWM/controls。另重读已封存的观察包装等价实验：200 组、800 步、24,000 个组末输出完全相等，确认使用同观察器/模型；没有重启模型重跑。

| 原始覆盖 | PX4 | AP |
| --- | ---: | ---: |
| 完整 1 ms 记录 | 35,840 | 69,499 |
| 原适配器组 | 8,960 × 4 步 | 69,499 × 1 步 |
| 原 truth 记录 | 1,793 | 3,475 |
| 实际 CDR | 7,795 | 10,335 |
| 公开请求 | 8 | 9 |
| 重解码原生 MAVLink | 13,556 | 1,233 |
| 电机原生采样对照 | 315 | 674 |
| 对下一组/步输入的最大误差 | 6.30e-8 | 0 |

PX4 trace 的 actuator timestamp 始终比该组末物理时间少 4 ms，验证 HIL 原生时钟等于物理微秒，输入用于其后四步。AP 固定源 `SIM_JSON.cpp` 对绝对 JSON 时间量化，`SITL_State.cpp` 先 `fill_fdm` 再 `stop_clock`，而 `SIM_Aircraft.cpp` 在 fill_fdm 内写 SIM2；因此 **SIM2 状态对应其 TimeUS 后一毫秒**。按这个源代码顺序核对 26,996 个 SIM2 状态，最大误差 1.20e-7。此关系不是搜索位移或拟合最佳曲线；GUIA/RCOU 的 HAL boot 时间另按正常控制时钟解释。

Humble 的 raw take_message 只提供 source/received timestamp；真正的 publisher discovery 单独记录，**不存在每包 GID**。物理观察器记录适配器归一化后的 input16，没有原始 actuator datagram，因此不声称每 1 ms 有独立网络包归因。ULog/RCOU 电机日志有采样限制；审计证明可用原生采样到适配器完整输入的对应关系。

## 冻结窗口复核

窗口由运行前预算及实际阶段标记确定，以每个真实 1 ms 样本计算，不插值、不挑选另一个通过窗口、不因 native 接收延迟平移门槛。在线 native_observed 的时间仍是接收器 physical cursor，不能改称飞控受理时刻。

| 条件 | PX4 | AP |
| --- | --- | --- |
| 固定 3 s native collective 中位数 | 0.5309605896472931，120 样本 | 0.31348326802253723，120 样本 |
| 2 s level 最大垂直漂移 / 速度 | 0.031660 m / 0.024964 m/s，通过 | 0.007611 m / 0.007632 m/s，通过 |
| roll 固定跟踪窗 | 27.86–28.26 s，27.88 s 已失败中止 | 59.84–60.24 s，完整 401 样本 |
| 窗内 roll/pitch/yaw 最大误差 | 已有 21 样本：2.29114° / 0.06641° / 0.51474°，失败 | 0.22708° / 0.15292° / 0.46568°，通过 |
| 姿态后恢复 | 未执行 | 60.34–60.96 s 后失败 |
| 恢复段最大位置差 / 速度 / 倾角 | 未验证 | 0.71382 m / 0.82580 m/s / 15.09171° |
| 倾角包线 | 已运行范围无越界 | 首次 60.958 s，至 60.960 共 3 个 1 ms 记录越界 |
| +0.03 推力 / 0.5 s、最终0.1与此前0.2速度差 | 未执行 | 未执行 |

恢复中的位置/速度上界仅是失败段测量，不能解释为必须从恢复第一毫秒就满足终端 dwell 门槛；真正导致 AP 中止的是 15° 全程安全包线，而 8 s 恢复/1.5 s dwell 尚未完成。完整位置+yaw 公共恢复请求和 native GUIP 都保留在原始证据中。

## 原生效果与失败边界

PX4 实际公开 CDR 在 boot timestamp 27.360 s 起提供正确 5°目标、FRD `thrust_body[2]=-0.53096056`，OffboardControlMode 只激活 attitude。然而 ULog 在 27.376、27.424 s 仍记录近 level 的旧位置控制姿态目标；27.464 s 首次采样到正确目标，27.520、27.576、27.624 s 又出现旧目标，27.640 s 之后所见采样才持续正确。因此不能把失败只归因于物理响应慢。原生控制模式发布节奏及旧位置控制发布者竞争的源码诊断由独立只读任务完成；本审计不改飞控或移动窗口。ULog 的第一次匹配是**第一次被日志采样观察到**，不是精确首次受理 tick。

配置 output rate 为40 Hz，但本轮 PX4 实际 level 段 native CDR 平均32.0 Hz、DDS source 平均31.96 Hz；roll 段为31.25 Hz / 30.77 Hz。审计记录实测间隔，不能从配置声称实际40 Hz，也没有补设容差来放行这一差异。

AP 101 条 native 姿态 CDR 与 101 条 GUIA 对应两段：level 67 条、roll 34 条。GUIA 的 ENU/FLU→NED/FRD roll/pitch/yaw、归一化 thrust、零 body rates、零 climb-rate 均与实际公开目标相符。固定姿态 tracking 区间内另有 13 条 GUIA 目标观察。其后恢复仍是原生位置出口；失败保留，不以阶跃通过覆盖恢复失败。

AP 实读 `GUID_OPTIONS=8`、`GUID_TIMEOUT=3`，其余为 `ATC_ANGLE_BOOST=1`、`PILOT_THR_FILT=0`、`MOT_THST_EXPO≈0.65`、`MOT_THST_HOVER≈0.39`、`MOT_HOVER_LEARN=2`、PWM 1000/2000、电池补偿电压0/0。GetParameters 响应经真实生成 codec 核对；记录是客户端返回响应的序列化，不冒充捕获的 DDS service packet。

PX4 实读 hover=0.5、min≈0.12、max=1、THR_MDL_FAC=0。`MPC_USE_HTE` 的 `PARAM_VALUE.param_type=6`，float 槽位的 `1.40129846e-45` 必须按 PX4 bytewise int32 解释为 **1**，不能当成接近零；源发送路径直接 `param_get` 填充该存储，审计已按实际 schema 解码。

首轮 PX4 `candidate_unchanged=false` 原样保留。前后固定 candidate 资源一致，postflight 源集合新增四个已在 run-source 预先封存的运行期导入模块。审计逐字节验证这个严格的“只增加已预封存项”关系，既不要求篡改旧 result，也不放过任何已有项变更。它不改变 PX4 的实际姿态失败结论。

## 重现与验证

在 ROS Humble、本项目 PX4/common messages、新 AP attitude messages overlay 环境中，离线运行：

```sh
python3 -B tools/audit_attitude_flight.py <terminated-run-directory> \
  --decoder-path /root/wksim-attitude-audit-deps-g_2y8olg \
  --output <new-audit-json>
python3 -B validation/test_attitude_evidence.py
```

11 个独立审计检查测试通过，覆盖缺 tick、缺 terminal、组内输入变化、不完整组、非有限输出、truth 重标记、缺失窗口不补点、独立旋转矩阵基变换、PX4 bytewise 参数及固定步骤不能被改名重解释。这些合成负例仅验证审计器，不构成飞行 PASS。两份原始首轮审计都没有解析/身份检查错误，最终状态仍 **failed**。

最终审计 JSON SHA256：PX4 `21d199446a22e96ae96bd142373f0870c936a2892fa5d848edabfedbb59674ea`；AP `d60e2e5a9b53191716f93f2f0a5430d83a26013289f0984832bd93d64a0e86b0`。
