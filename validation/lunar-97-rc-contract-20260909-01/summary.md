# #97 · 38-input-contract 交付

结果：合同设计完成；源码/安装/运行未修改，没有执行飞行或宣称飞行通过。

文件：`docs/plan/38-rc-contract.md`。本目录为指南额外允许的新证据目录。基准 HEAD：`37a351b3491a0d35a8c4d8ed726683da0764928f`，分支 `codex/independent-rgb-integration`。

验收逐项：已复核原始 rc_input.h 与 uav_controller.cpp 的实际八通道语义、公共世界积分和 C2-after-C1；已选定同 WSL boot 的 wksim-software-rc-v1，冻结严格信封/所有权、50Hz、最大 dt=0.05s、双墙钟1.5s过期、显式交接、暂停/复位/旧流拒绝；已列四个确切接入文件以及 #98 的两文件边界。原解锁、原生模式/能力、运行身份与预算保留。合同中的新输入服务参数不是物理验收阈值。

证据：`raw-inspection.json` 保存工具原始输出、退出码及 11 个 SHA256（原始源码、ROS2当前源码、消息定义、输入决策与本合同）。原始上游两份源码与输入报告记录哈希一致。当前 command.py 仍未集成杆量，Node 仍拒绝 RC setup，合同明确这些事实。

执行命令（PowerShell，cwd 为本项目根）：

```powershell
gh issue view 97 --repo unununnnn/wksim --json title,body,state,labels
gh issue view 38 --repo unununnnn/wksim --json body
gh issue view 98 --repo unununnnn/wksim --json body
gh issue view 99 --repo unununnnn/wksim --json body
Get-Content Modules/uav_control/include/rc_input.h
Get-Content Modules/uav_control/src/uav_controller.cpp | Select-Object -Skip 451 -First 24
Get-Content Modules/uav_control/src/uav_controller.cpp | Select-Object -Skip 893 -First 180
Get-Content ros2/src/prometheus_control/prometheus_control/command.py
Get-Content ros2/src/prometheus_control/prometheus_control/node.py -TotalCount 460
Get-Content ros2/src/prometheus_control/prometheus_control/node.py | Select-Object -Skip 460 -First 220
Get-Content ros2/src/prometheus_control/prometheus_control/session.py
Get-Content ros2/src/wksim_msgs/msg/SetupRequest.msg
Get-FileHash -Algorithm SHA256 -LiteralPath docs/plan/38-rc-contract.md
git diff --check
```

实际结果：文档/源码静态审查完成，diff --check 无报错。产品测试执行数 0，未以文档检查冒充实现测试；后继测试命令在合同标为尚未交付。

读取失败及解决：接缝报告未列完整 ROS2 路径，首次尝试 Simulator/wksim_control/command.py、envelope.py、node.py 不存在，通过 rg --files 找到真实 ros2 路径并读源。docs/adr 及旧批准记录引用的 docs/2026-09-07-first-phase-batch-proposal.md 不存在，C2-after-C1 依据当前接缝与批准记录保留；不伪造旧提案内容。docs/codebase-memory.md 历史长输出截断；本任务按已知源和文件名定位，无结构图查询或修改代码，不依赖该截断历史作结构结论。

后继边界：#99 现有写入范围仅文档/证据，四文件接入需主代理落实实现子票；AP 安装能力、双栈断流后真实原生行为、物理移动/回中/偏航及 C1 完成均未由本票证明。停止 RC 发布不等于 AP 自动停止运动。R1、RateUnmet、父 #38 和 Full 未判通过。

实际模型/推理：用户派发声明 gpt-6-astra/low；本会话可见系统身份仅 GPT-6，未获得可独立读取验证的具体模型 ID/推理档元数据，故不声称已核验。没有派发子代理。

进程：只使用短时只读 shell/gh，未创建 FC、ROS、UE 或模型进程，无本票运行残留需要清理。原有 AGENTS.md 与推进指南改动保留且不暂存。
