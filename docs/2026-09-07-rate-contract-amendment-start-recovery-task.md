# 倍率合同修订：显式 start-recovery-task 作为分段重锚点（2026-09-07 批准）

本附录是对[首期倍率合同](2026-09-07_joint-rate-contract-accepted.md)的修订，不改写原文。

## 批准记录

2026-09-07，主代理就两个未决问题向用户提出选项（恢复风暴问题与持续 1× 问题，见[收口报告](2026-09-07-rate-recovery-rgb-closure-report.md)「未决（提交用户）」节），用户答复「全按照推荐进行」。恢复风暴问题的推荐项（a）即本修订：把操作员显式 `start-recovery-task` 列为与 recover/resume/set-rate 相同的显式分段重锚点，**所有数值阈值不变**。

## 修订内容

1. 操作员显式 `start-recovery-task` 请求受理时关闭当前倍率分段（`rate_segment_end`），并以 `transition=true` 重锚新分段（`rate_anchor` reason `start-recovery-task`）。任务进程启动引发的 DDS 发现风暴计入新过渡段，不再回算到恢复后已验证的前一连续段。
2. 请求若落在 4 tick 组中（非完整边界），重锚延迟到下一完整边界执行；延迟窗口 ≤3 tick 仍属旧段，语义与 pause/resume 的边界纪律一致。
3. **数值预算全部不变**：100ms 累计墙钟迟到硬上限在新段内同样适用（风暴超过 100ms 仍如实 rate_unmet 冻结）；10s 窗 ±2%、60s 段 ±1%、每档 ≥3 epoch ×60s 要求不变；过渡段与现行规则一样不进入稳态窗口审计。
4. 禁止事后放宽的纪律不变：重锚前的边界检查照常执行（transition 确认不能丢弃旧段未检迟到），重锚不解除 latched（本锚点不是 recovery 锚点）。

## 实现与证据

- 实现：`Simulator/wksim_runtime/joint_runtime.py`（start-recovery-task 分派处的即时/延迟重锚与 supersede 清理）；`Simulator/wksim_runtime/joint_rate.py` 未改。
- 单元证据：`validation/test_joint_rate.py` 新增 `test_start_recovery_task_anchor_resets_segment_but_not_budgets`（新段归零、transition 标记、段末记录、100ms 硬上限在新段内仍然锁存），并扩展 `test_transition_confirmation_cannot_discard_boundary_lateness` 覆盖新 reason；11/11 通过。
- 真实双飞控证据：修订前 AP/PX4 失联恢复回归已在**未修订**合同下如实通过（`product-joint-flow-etsaqmso` / `product-joint-flow-nasz1u3f`，风暴段最大累计 51.14/94.18ms<100ms，双侧原始审计各两次字节一致+篡改负例通过，`validation/recovery-regression-audit-20260907/`）；修订后的真实回归证据见本轮报告。
