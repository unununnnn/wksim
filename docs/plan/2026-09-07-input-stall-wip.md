# 输入掉队与倍率批准检查点

Goal active。本轮有实际源码和实飞进展，但输入/模型故障接缝尚未完成独立审计和全部回归，正式倍率尚未实现。

## 主机维护暂停

后续已解除暂停：迁移任务明确通知迁移完成并可恢复，注册/发行版位于`E:\WSL\Ubuntu-22.04`，Linux和项目路径保持不变。主代理已在新boot `f1a796ec-36ba-4e4a-bec8-8448b822bb22`核对三个固定候选清单哈希一致，WSL地址`172.31.183.225`（另有Docker桥`172.17.0.1`）；记录在`post-migration-host.json`。不要从下文历史暂停段落推导当前仍禁止测试。

Windows只读工作另完成6项输入边界检查、四epoch完整模型/原生线路/时钟/物理任务窗口、原始TextInfo与SessionState CDR解码及Task日志交叉核对，结果在`validation/joint-input-audit-20260907/windows-*.json`，未把历史记录当作当前Linux活性检查。

恢复后的新增变化正在验证：生产运行器改为记录真实host_boot_id，不再观测硬编码PID828；历史审计保留当时外部进程/组证据，`--current-host`只有同boot才查活PID和当前二进制。输入等待补充select之后/解析之后截止检查，迟到的真实ACK仅保留到显式repair；3项截止边界用例先红后绿，2项host身份用例通过。新的PX4模型RPC实测已启动，句柄9630，证据`validation/joint-input-stall-kp5klq6t`，WSL输出`/root/wksim-input-stall-5sam924n`；必须先查该句柄/真实状态，不因旧文档重启。

用户授权的 C 盘清理任务 `01a03c96-15a4-7f12-ad97-60475cf00801` 正在迁移 Ubuntu-22.04 的 VHD，要求本任务暂停 WSL 工作。主代理已确认全部本轮测试结束、8个记录的 manager/epoch 组为空，并通知对方。最后只读主机记录为 `validation/joint-input-stall-20260907/pre-migration-host.json`，旧 boot_id 为 `a938140e-61e6-46a6-89ed-0e61a87a0ba0`。

对方随后通知：已按用户授权停止原 AP PID828及空闲CI runner，sync/terminate Ubuntu；`--manage --move` 遇到 ERROR_SHARING_VIOLATION，注册仍在 C，源 VHD 完整，E 目标为空，正在另向用户确认能否停止全部WSL释放共享虚拟机锁。RflySim-20.04另有活动PX4/mavros/truth，主代理未操作它们。

**收到该迁移任务的明确完成通知前，不启动 Ubuntu-22.04 或新的 WSL 测试/构建。** 可做Windows侧只读和文档工作。不自行迁移、注销、删除或启动发行版。不因超时或目标目录出现就推定迁移完成。

原 AP `pid/pgid=828,start_ticks=19268` 在本任务最后核对时仍与所有运行记录一致，随后由迁移任务按用户授权停止。这是主机生命周期边界，不是本任务误杀/测试失败。恢复后旧审计里要求“当前PID828仍等于历史值”的检查会失去适用前提；应保留此次停机与当时清理证据，明确区分历史原始审计和当前运行活性核验，不能伪造旧进程或悄悄把当前检查算通过。

## 当前源码变化

- `wksim_core/worker.py`：RPC保持3s绝对墙钟截止，等待时可每20ms服务监督；监督中止仍令通道poison，禁止重试使用。
- `wksim_core/joint.py`：`InputTimeout`、实际未完成步骤`inflight`、`finish_inputs(recovering=True)`。恢复只补齐原来已产生的模型步的真实输入ACK，不再次调用模型RPC。
- `scene_clock.py`：`input_pending`、`suspend_input`、`repair_input`。双模型已提交且输入待确认可以锁存；精确修复后仍保持faulted，直到新显式recover。模型部分完成/未知RPC不可沿输入恢复路径修复。
- `joint_runtime.py`：超时锁存并保持服务可操作，保留`faults.json`/原始LC；已提交模型但输入未完成时补发唯一真实 `/clock` tick，之后只重发冻结时间；显式恢复重建屏障再确认新原生状态和新Task。长等待仍可处理stop/cold-reset。普通Task失败在完整输入边界撤销/冻结，而不是自动推进旧任务。
- `joint_actions.py`：等待期间仅取紧急操作，其他动作留给正常边界处理，避免被提前误拒绝。

以上源当前均未提交；HEAD仍`6d2e371d918f202acd64e822dee4300e86942bcd`。源码在修改前已通过CBM刷新与查询定位：2026-09-06 15:45:20 UTC，46,226 nodes / 156,582 edges，artifact已写；日志`C:/CBMData/logs/wksim-prometheus-1788709523.log`。`receive_worker`入向8项，真正生产调用为JointPhysics.advance及JointLifecycle.snapshot，实际源已读；tools目录按设计排除并直接检索。刷新后四个源仍metadata_changed，不声称图完整。修改后尚未做新依赖结构查询；下一此类查询须先检查/刷新。

## 真实证据与终态句柄

驱动`tools/validate_joint_input_stall.py`只调用正式操作API及对核验PID/启动时间/exe后的本实验进程SIGSTOP/SIGCONT；旧版本已封存 `validation/joint-input-stall-20260907/driver-v1.py`，SHA256 `7502a2f08b5046a3294ef85465a5a22e96758dd81e98d150f8e1c4a268abdab3`。下述三场均使用此版本。

|场景|证据|结果|
|---|---|---|
|旧实现PX4输入超时|`validation/joint-input-stall-ycad_am1`|失败：状态停留旧running，5s输入超时后退场；保留原始失败。|
|新实现PX4输入超时|`validation/joint-input-stall-kcnyjj8i`|驱动pass；tick52068双模型已提交、PX输入待确认，锁存后SIGCONT不推进；显式原屏障恢复、新Task降落到63764，再冷重置/停止。|
|新实现AP输入超时|`validation/joint-input-stall-shycq0pd`|驱动pass；完整阶段见flow/result，冷重置新地面epoch最终41012，组清空。|

43124、80471、78723均已确认结束；没有这些句柄要继续等待或重新启动。新的模型RPC超时真实测试还没有启动。

最小红→绿检查已执行：新增3项起初因缺失方法/参数失败，修复后worker/clock/action共28项运行，5项真实模型/ROS条件检查跳过，其余通过。完整候选与默认矩阵尚需新一轮回归，不能拿上一报告74/329结果覆盖本次新变更。

## 审计状态与具体后续

审计代理`joint_input_audit`已interrupted。其实际配置由主代理核验为gpt-6-astra/low，session`01a07783-5a1b-7983-89e0-3c77b8794aaa`，turn`01a07783-5b4f-7611-8d7d-c96723fb75f4`。继续接口不能显式选择该组合，因此不通过followup接口恢复它，主代理承担后续。

代理已写`tools/audit_joint_input_stall.py`和`validation/test_joint_input_audit.py`。前者FC分支待真正ROS环境验证，模型分支明确未实现而拒绝；`validation/joint-input-audit-20260907/px4-fc.json`目前是缺`rclpy`的失败记录，不能称独立审计通过。最后检查没有该审计进程。

恢复WSL后的顺序：

1. 核验迁移后发行版、主机boot身份与固定候选路径/哈希；保留历史活性证据的适用边界。
   生产运行器目前还硬编码观测PID828，审计`retained_identity`也把当前PID828与历史值直接比较。原用户进程已被授权维护退场后，这些假设不再适用；应将产品自身所有权/进程清理与验证用的外部进程哨兵分开，并用已封存的迁移前主机/清理记录解释旧证据。不能监视新boot下偶然复用828的无关进程，也不能为了变绿复建旧AP或删除历史失败。
2. 补充/核验输入等待在`select`返回后及实际接收接受处的截止时间边界，避免仅在等待前检查导致逾期包自动通过；当前源码只有等待前检查，边界用例尚未完成。不能放宽已批准5s。
3. 跑AP/PX4模型RPC SIGSTOP超过3s真实负例：记录poison及部分模型状态，迟到结果不得提交，不能recover，只stop/cold-reset；原始审计须单独处理不落地和可能`pending_tick`，不使用正常飞行假设冒充通过。
4. 完成两FC输入病例和模型负例的原始审计、损坏负例、健康/DDS恢复交叉回归、当次进程检查。审计源和依赖运行中保持不变；历史正例按其源码副本解释。
5. 按下面已经批准的倍率合同继续实现和真实验收，不再询问同一批准；保留更高倍率/全部Full义务。

## 已获倍率批准

用户已回答“批准该提案（推荐）”；首轮0.5×/1×、默认0.5×、累计墙钟迟到>100ms冻结撤销、不追赶补发/显式恢复、10s窗±2%/60s段±1%，以及提案其余分段/窗口规则已获批准。详见[批准记录](../2026-09-07_joint-rate-contract-accepted.md)。现有1ms物理、2s新鲜度、100/500ms许可、3s模型、5s输入/恢复值不变；这些不是G6等价预算。

获批原文SHA256 `54dcd1df7d70caeb483ab101e7071f8d48168f29e22a93da594e455a459a02a5`，副本/答复在`validation/joint-rate-contract-20260907/`。已发布并逐字读回#8评论`5560622276`，无需重复发布或再问。正式倍率实现/新倍率运行尚未开始。
