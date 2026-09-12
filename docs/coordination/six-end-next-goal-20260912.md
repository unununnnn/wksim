# 六席位下一阶段执行计划

2026-09-12。新Goal已由正式工具创建并为active；旧Goal已不存在，未改数据库。项目终态仍为全部已批准必需票据及Full/G0–G6，以下是当前关键路径，不缩减终态。

## 六席位与唯一写入者

用户明确保留Fast要求，三个Luna因接口不能选择/核验Fast而由主会话暂时代行。实际运行是三个外部代理加三个主会话工作项，不能写成六个代理都已启动。

| 席位 | 当前执行者 | 本轮任务 | 写入范围及状态 |
| --- | --- | --- | --- |
| Luna 1 | 主会话代行 | 完整性负例复现 | 独立负例目录；已删request4/command1并重新编号，旧审计仍pass，原件未变 |
| Luna 2 | 主会话代行 | 证据包和压缩原件校验 | 已核验25文件及解压SHA；报告artifact-integrity.json，不等于发布完整性 |
| Luna 3 | 主会话代行 | 真实Issue依赖与下一票选择 | 已核对82/83/84/101/102/29/33，报告issue-frontier.json |
| Oh My Pi | omp，23a | 修正BEST_EFFORT完整性误判及负例 | 只写Linux实验区tools/audit_planner_release.py、validation/test_planner_release_audit.py；running |
| Claude Code | claude-code，19a | 核对#82→#83新候选与完整PV冻结合同 | 只读，不改代码/Issue，不运行native；running |
| DeepSeek Harness | deepseek-harness，02 | 接替agy，复算写者归属与时钟域 | 只读；01的错误结论已退回，02正在修正；不作为通过证据 |

三个主会话代行项已完成首轮准备，后续承接集成、负例复核和准入。后续Fast可选择且可核验时才实际启动三Luna，仍使用Luna+xhigh。agy不再接收新任务。外部端保持各自原生默认模型/推理；DeepSeek本次工具回报DeepSeek-V4-Flash、thinking off，未宣称使用其他配置。

## 第一阶段：补齐发布证据，保留已验证物理事实

Claude18-AJ指出：PVProbe为BEST_EFFORT，sequence是接收后的本地编号，不能据此声称无丢失或源writer静默。主会话已在独立目录 `/root/wksim-audit-corruption-90c_v_lx` 复现：移除原sequence26880、tick52572、request4/command1，再重排接收sequence，原审计仍pass。原始飞行文件未改。这是审计缺口，不是假装新增一次飞行。

OMP修复应使用有明确写者归属和首尾界的发布侧证据；若无法证明完整性，明确报告该项未证明，不能通过弱化定义变绿。原bomvjsmg真实停止/落地与1ms数值事实保留，完整写入尝试覆盖声明待修正。主会话收取后运行针对性负例与原始数据审计；仅审计改动不重复飞行。

DeepSeek01不可采纳的错误：request66由独立PlannerTransportNode发布，因此AP Task自身的1..65,67,68账本是预期分工，不能归因单条落盘丢失；Task相对wall、runner相对wall、helper绝对monotonic不能直接比较；本地接收sequence连续不代表无丢帧。02已被要求使用生成消息离线解码并纠正上述结论。

## 第二阶段：完整PV及正式入口

#82为CLOSED；#83为OPEN/needs-triage，必须完成原两段PV与0.5x/100ms/10s/60s全部原审计。#84依赖#83，不能提前提升。Claude负责核对c2IXOr候选与原冻结合同；主会话最终决定必要的最小冻结变更和准确运行命令。不能用AP提前release/PX4一段的bomvjsmg结果替代#83。

这里“主工作区”指当前checkout `codex/independent-rgb-integration`，不是Git中名为main的旧分支。实验区是 `/root/wksim-release-acceptance-fe3` 的 `codex/planner-release-validation`（先前90bb3e1）；实时Git优先。

## 后续范围及门槛

#101已CLOSED，但#102还依赖OPEN的#29和#33，不能只看ready-for-agent标签就启动完整规划器验收。晚到起点语义未获用户回答，维持原闸门。其他已批准独立票据仍可推进，ABI、硬件、预算缺口仅阻塞各自分支。

不改1ms、native屏障、无追赶、100ms累计迟到及身份/新鲜度/物理门槛；主会话独占native执行线，启动前分别完成并评估两个WSL发行版进程检查。保护他方未提交修改。只有全部原AC真实完成才关闭对应票据；全部Full/G0–G6完成才结束Goal。
