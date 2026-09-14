# #33 AC5 · Q01 每量误差/驻留/恢复预算行提案

**状态：PENDING OWNER DECISION（待所有者决策）。Q01 保持开放；本文件未获所有者签署，不构成任何批准。**

- 切片：`codebuddy-33-ac5-budget-row-proposal-20260914-01`
- 对象：`docs/plan/full-original-ac-gap-ledger-20260914.md` 工作队列第 1 行 Q01（AC `33:5`，门 G3，类别 `blocked-owner-decision`）
- 性质：控制集成（控制接缝）预算行提案；只读离线切片，不运行原生、模型、MATLAB、ROS/DDS、SITL、FC、UE、构建或飞行路径，不重跑 #83
- 本提案不绑定 HEAD 精确值；仅要求检出包含提交 `31e5b65f` 与 `f333316e`（ancestry 由配套离线单测验证）

## 1. 任务与关闭规则（冻结引用）

- 账本 Q01 行原文：`Q01 Commit the per-quantity error/dwell/recovery budget row for #33 AC5`；关闭规则原文：`an owner-signed budget row committed in docs/plan naming each quantity, its threshold and its dwell window`。
- #23 AC5（`docs/plan/tickets/23-mixed-trajectory.md`）原文：固定轨迹的误差、驻留和恢复门槛预先确定，两栈保存真值证据。
- 本文件提供"命名每量、阈值、驻留窗口"的预算行形式，但**未获所有者签署**；签署前 Q01 与 `33:5` 保持未勾选、未关闭。

## 2. 已冻结的已批准倍率与监督界（不重新决策）

来源：docs/2026-09-07_joint-rate-contract-accepted.md、docs/2026-09-06_joint-wall-supervision-accepted.md、docs/2026-09-07-recovery-staging-revert-correction-report.md。以下各行是所有者已批准的冻结值，本提案原样保留、不改动：

| 量 | 已批准界 | 窗口 / 语义 |
| --- | --- | --- |
| 累计墙钟迟到 | >100 ms 即锁存 `rate_unmet`/`resource_insufficient`，在最后完整屏障冻结并撤销控制 | 迟到只向后滑动；不连续补跑积压组（no catch-up） |
| 相对请求倍率误差 | ±2% | 每个不重叠 10 s 窗口 |
| 相对请求倍率误差 | ±1% | 完整 60 s 有效段 |
| 物理步 | dt = 1 ms | 不改 dt、不跳 tick、不稀释传感器 |
| 共同输入屏障 | 4 ms（单步严格四 tick） | 0.5× 组周期 8 ms / 1× 组周期 4 ms |
| 显式恢复就绪等待 | 5 s | 恢复物理后必须另发新任务请求；故障不得以变速绕过恢复 |

## 3. 提案：携带到真正混合轴模式的每量轨迹预算行（未批准）

观测来源：docs/2026-09-09-pv-flight-report.md（PX4 第 1 段）与 docs/2026-09-13-final-combo-pv-pass.md（停止保持最大值）；"跨报告观测最大值"取两份报告的最坏值。这些数值属于既有 AP/PV 有界实验记录，不是对真正混合轴新原生子模式的验收。

| 量 | 提议阈值 | 驻留窗口 | 跨报告观测最大值 | 状态 |
| --- | --- | --- | --- | --- |
| 轨迹位置误差 | ≤0.5 m | 每连续 12 s 轨迹段 | 0.12668 m | PENDING OWNER DECISION |
| 逐轴速度误差 | ≤0.3 m/s | 每连续 12 s 轨迹段 | 0.07790 m/s | PENDING OWNER DECISION |
| yaw 角误差 | ≤0.15 rad | 每连续 12 s 轨迹段 | 0.03950 rad | PENDING OWNER DECISION |
| 停止保持速度 | ≤0.25 m/s | 每连续 4 s 停止保持段 | 0.040880 m/s | PENDING OWNER DECISION |
| 停止保持漂移 | ≤1 m | 每连续 4 s 停止保持段 | 0.091560 m | PENDING OWNER DECISION |

## 4. 显式未决的所有者选择（本提案不代答）

- [ ] 第 3 节五行门槛：原值携带到真正混合轴模式，或另设替代值（未选）
- [ ] 航点进入余量：是否沿用 fresh 估计速度 ≤0.4 m/s 作为进入航点保持的余量（未选）
- [ ] 恢复后是否复用第 3 节轨迹门槛（显式恢复就绪 5 s 语义已冻结；复用与否未选）
- [ ] 是否保留已批准的每档至少 3 个独立 epoch 要求（保留或更改，未选）
- [ ] 加速度前馈是否执行必须显式声明，不能因消息带字段就声称生效（是否执行未决）
- [ ] yaw-rate 与其它原生边界（既有候选中原生 A/yaw-rate 轴失活；边界未决）
- [ ] G6 每量动力学等价预算是否给出及如何给出（未决）

## 5. 范围分离

本文件第 2、3 节全部数值属于控制集成（控制接缝）预算：轨迹跟随、停止保持、倍率墙钟监督与恢复语义。它们不是 G6 每量动力学等价预算；G6 预算仍须所有者按第 4 节末项单独决定。已批准记录本身亦声明：其百分比与 100 ms 属于墙钟性能预算，不是动力学等价误差。

## 6. 冻结记录与探针字段排除（原样保留）

- 既有 `RateUnmet` / `numerical_failed` 失败记录原样保留（含 docs/2026-09-09-pv-flight-report.md 第 01–04 轮失败样本、docs/2026-09-07-recovery-staging-revert-correction-report.md 冻结样本）；本提案不改判、不复用、不抹除任何失败记录。
- 探针字段排除：`rate_timing_probe` 记录带 `classification=diagnostic_only`、`production_performance=false`（docs/plan/33-rate-timing-probe.md）；探针样本不得冒充 production 性能，不得作为本预算行的验收证据。2026-09-13 最终组合运行时两项计时探针均关闭。

## 7. 非关闭声明

本文件不关闭 #33、#84、Q01、G6 或 Full 中的任何一项；`Full = not-closed`，G0–G6 全部 `not-closed` 保持不变。#84 仍需同组合 mixed 能力证明、精确映射和真实正式入口验证。

## 8. 所有者签署块（未签署）

- [ ] 批准第 3 节五行预算行原值。
- [ ] 批准第 4 节各项的具体决定（逐项标注）。
- [ ] 确认第 5 节范围分离与第 6 节保留条款。

签署人：＿＿＿＿＿＿　日期：＿＿＿＿＿＿

**以上三项签署复选框全部未勾选。签署前本提案不构成任何批准；Q01 与 `33:5` 保持开放。**
