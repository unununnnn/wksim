# #121 GNSS 运行入口准入与待交付边界

2026-09-09。状态：**实现前置不完整；本票保持 OPEN / needs-triage**。
这是当前可复查的准入交接，不是已完成的双栈飞行 runbook。
本轮只读核验与准确命令保存在
`validation/lunar-121-20260909-closeout-01/`。本票禁止提前运行 #111/#112 飞行。

## 已有资源及事实

#109 与 #110 的 GitHub 原生前置状态均为 CLOSED；它们分别证明以下限定接缝。

| 输入 | 已证明内容 | 尚不能推导的内容 |
| --- | --- | --- |
| #110 `GnssSendGate` | 实际 HIL_GPS 发包门、原包、源时间、质量与拒绝记录；合成状态加真实编码/socket 对测 | 故障飞行、定位失效、任务撤销、恢复接管 |
| #109 AP 原生候选 | 真实 AP 进程的 8000-tick 固定地面 JSON、原生延迟样本及 UBX 模拟串口写入 | 带 DDS 的悬停中断和真实模型飞行 |
| #22 已批准恢复 | Agent 链路中断、任务撤销、不重放、显式新请求及原生确认 | GNSS 中断的 EKF/failsafe 动作与对应数值预算；#22 正文明示仅限 Agent 链路 |

AP 资源为 `/root/wksim-ap-gnss-109-20260909-05/build/sitl/bin/arducopter`，
SHA256 `48062a2cc8f73c502174561c544730e9adc736b77819a513c48f40eab0c94478`。
候选头 SHA256 `67a70a07f379e096670355e551ca7d79539be10593177b1462b74b21576d53a9`。
完整模型、PX4、Control、消息覆盖层和参数组合还没有 #121 的联合准入清单；
不能借用 PID/姿态准入成功推导 GNSS 准入。

`SIM_WksimGNSS.h` 的 `Context` 将 `start=4000,end=6000` 编译固定；
`receive` 要求 tick 从 1 连续递增并在超过 60000 时退出109；
`sensor_created` 在计划开始后拒绝重建。只有身份和输出 trace 路径来自环境，
没有延后故障计划的运行参数。`probe.py` 的参数文件明确 `DDS_ENABLE 0`，
输入为固定地面真值且不解锁。这是其通过范围，不是该前置票的失败。

## 解除阻塞的具体交付

1. 为 AP 分配新的原生候选实现/构建归属，提供在真实初始化、定位和任务就绪之后
   冻结的单次 GNSS 故障计划。保留 run/epoch/vehicle/tick、原始源时间、代次、短写
   拒绝和旧候选证据；新计划及总 tick 上限需在新运行前明确审查。不得用变更时间戳、
   删除 JSON 真值或隐藏旧失败模拟新接口。#121 当前允许的八个文件不包含原生 AP
   头/生成器/固件构建修改，故本轮没有修改该候选。
2. 明确双栈 GNSS 故障的物理包线、无效/陈旧/GNSS抑制/链路中断的区分、失效与恢复
   观察窗、原生 failsafe 参数/动作、任务撤销触发及显式新请求资格。已批准的不重放、
   不自动抢模式原则继续成立；不能把 Agent 的2s/5s或测试样本年龄预算改称GNSS批准值。
   当前文档不选择新的安全动作或数值容差。
3. 在原票八个文件内实现完整运行器/任务/冻结配置、真实模型桥接和独立原始审计。
   AP 应保留全部模型传感器字段并增加规范身份前缀；PX4 应调用已有可选发包门，
   使用同步持久记录。只读预检必须核验实际安装、二进制、消息/源码与封存合同身份。
4. 原始审计应从输入原包、原生定位/模式/任务CDR、物理1ms记录及精确终态重建中断、
   有效性失效、撤销、新鲜恢复、显式新接管及降落。至少拒绝旧源新戳、缺tick/缺包、
   错run/epoch、抑制窗仍写入、缺撤销、自动重放/抢模式、无新原生确认和缺终态。
   原始 GNSS 源采集时间、AP HAL/UBX时间、权威tick和墙钟分别保存，不互换。

## 当前可复制命令

在 Windows 项目根 `C:/Users/PC/Documents/odid编译/wksim` 执行：

```powershell
gh issue view 121 --repo unununnnn/wksim --json number,state,title,body,labels,comments
gh api repos/unununnnn/wksim/issues/121/dependencies/blocked_by
python -B -m unittest validation.test_gnss_event validation.test_gnss_px4_injection validation.test_wksim_core.ProtocolTests -v
wsl -d Ubuntu-22.04 -u root -- /usr/bin/python3 -B -m unittest validation.test_gnss_event validation.test_gnss_px4_injection validation.test_wksim_core.ProtocolTests -v
python -B validation/lunar-121-20260909-closeout-01/collect.py
```

最后一条是**已执行后不可覆盖重跑**的证据收集入口：其所有输出独占创建。
要复查可读原件；要重新采集，将脚本放入新的 `validation/lunar-121-<唯一ID>/`
再执行。它仅运行现有离线测试、重审已归档地面原件及其临时篡改副本，读取资源
SHA和进程清单；不会启动 FC/模型/ROS。每条实际 argv/cwd/时间/返回码独立归档。
临时篡改副本由 `TemporaryDirectory` 退出时清理，原件保留。

两栈正式 `--help`、`--preflight`、一次飞行、独立整场审计和基于进程身份的清理命令
均**尚未交付，不能执行**。待上述实现完成后必须在本文补全实际可复制入口，
并记录新资源/输入 hash、输出 schema、真失败结果和只读预检；不得使用猜测路径
或把地面 `probe.py` 作为 #112 飞行入口。

当前审查输出 schema 为 `wksim.gnss.readiness-review.v1`；
`status=blocked`、`runtime_preflight_passed=false`、`full_flight_audit_passed=false`。
它不构成飞行审计 schema 或通过证明。#111/#112 保持原生依赖 #121；
任何检查或未来运行失败都保留原件，将 #121 保持 OPEN / needs-triage。

## 本票完成条件对照

| 完成要求 | 当前结论 |
| --- | --- |
| 双栈运行器/任务/冻结配置 | 未交付；AP 飞行计划接口和GNSS合同尚缺 |
| 独立整场审计与正负例 | 未交付；此次只重查既有传感器限定证据 |
| 两栈实际 help/只读预检通过 | 未完成；七个源码/配置/测试目标路径尚不存在 |
| 完整运行/审计/清理命令及身份 | 本文明确已验证命令与缺口，飞行入口待前置后实现 |
| 准确证据、范围、失败交接 | 本轮收尾的交付；不足以关闭 #121 |

R1、RateUnmet、#45原AC和Full结论保持其原有证据边界。
