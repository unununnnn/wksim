# e0 生成模型输出的采样相位

2026-09-08，主代理只读固定ZIP和现有wrapper，未编译或执行模型，未改变准入或数值预算。此项补齐[数值合同前置](2026-09-08-numerical-contract-readiness.md)中的step/输出相位问题。

## 实际源码

ZIP为 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`，其中 `e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/Exp1_MinModelTemp.cpp` 原始SHA256为 `a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019`。源文件包含非UTF-8注释，检查器使用Latin-1保留ASCII代码标识，不借解码替换改变原始哈希；行号按CRCRLF/CRLF规范化后的逻辑行计。

- `rt_ertODEUpdateContinuousStates` 2970–3034：切为MINOR，先计算f0，然后依次在 `x=y+h/2*f0`、`x=y+h/2*f1`、`x=y+h*f2` 三个暂存状态上调用 `this->step()`（3004、3013、3023）。最后3030行才写入RK4加权的最终连续状态 `y+h/6*(f0+2*f1+2*f2+f3)`；之后只切回MAJOR，没有再次调用输出计算。
- `step()` 3909–3917：minor调用将Timing.t[0]更新为solver时间，并用它生成输出时戳。最后minor调用在tnew。
- root输出时间 `HILSensor30d[0]`、`HILGPS30d[0]`、`VehileInfo60d[2]`，位置 `[6..8]` 和机体角速度 `[27..29]` 的赋值没有MAJOR保护。静态去注释/字符串后的花括号检查确认它们只位于step函数本体，而非major条件内。
- `step()` 8260–8282：调用ODE更新后仅推进绝对时钟/计数，没有重算root输出。
- 本项目 `Simulator/wksim_core/model.cpp` 在 `model->step()` 返回后直接复制Y的Vehicle60/Sensor30/GPS30；没有额外输出刷新。

完整源级行证据及括号作用域在 `validation/numerical-phase-20260908/phase-evidence.json`，可用同目录 `inspect_phase.py` 重建。这是静态代码证据，不是完整编译控制流分析或模型实测。

## 能确定的含义

对上述直接从连续状态写出的槽位，step返回的Y保留最后一次minor输出，即tnew时的RK4第四阶段预测状态 `y+h*f2`；其计算来源不同于随后提交的加权最终连续状态，但平衡状态、特定导数或舍入可能令数值相同。时间字段已经是tnew，故不能只看输出时间就声称全部字段来自最终提交状态。

其他输出还依赖B/DW和major更新的缓存，必须逐字段核对；本报告不把已证明的直接槽位结论无条件推广至120个槽位。现有飞控/日志/UE互相一致的证据仍是该API的运行证据，不因此变成或失去尚未完成的物理等价证明。

## 对照记录器应怎么做

候选方案是在独立源码副本中，于root输出全部赋值后、后续显式Update/ODE之前增加只读major输出采集点（7877之后，明确major guard），记录本次调用的k、t、输入及完整Y副本。此前已有初始化和部分B/DW更新，因此它不是完整状态检查点。记录器须按Vehicle60/Sensor30/GPS30逐数组复制，不能按原结构体内存顺序拼接；还须另记完整step返回状态。它只复制输出，不改变Y、连续/离散状态、随机源或后续积分；原始post-step API仍单独保留。该方案尚未实施或获准用作数值参考，不替换默认模型库。

[独立复核](2026-09-08-output-phase-review.md)确认六个直接状态槽位的来源、全部120项root输出覆盖及上述限制。取得k=0..500的501份major样本需要501次完整step；比较窗口终点为0.500s，引擎结束为0.501s，须同时记录。参考端的首次求值、输入左右侧约定与结束日志相位仍待独立确认。

以major采集对齐Simulink的major输出，比给现有post-step数组事后平移时间更明确。若要记录k=0..500，须在最终合同中写清实际step调用数、最后被记录时刻及引擎结束时刻，不能把一次step调用内部三次minor采样当成三个权威步。参考侧仍需独立核验正常日志相位。

不能为刷新Y简单多调用一次step：这会继续推进积分、随机源和离散更新。也不能在看过两侧误差后选一个最小误差时间偏移。生成源相位确认后，剩余库/单位/预算和真实采样仍按原门槛完成，#23/G6继续开放。
