# ArUco 双栈闭环收尾矩阵（#104 子票 / #40 父票）

状态：2026-09-11。把 #104 与父票 #40 的验收要求映射到已存证据与剩余缺口。run19 已以原倍率门失败；PX4 原生诊断 v2 候选已构建和准入，但尚未飞行，**不计入闭环通过证据**。

## 依赖状态（与验收证据分开判定）

- #40 父票原依赖：**#30 CLOSED、#32 CLOSED、#6 CLOSED** — 全部清除。
- #104 子票自身前置：**#103 CLOSED、#53 CLOSED** — 全部清除。
- 所有阻塞票均已关闭；能否收尾只取决于下列验收证据，不再有依赖阻塞。父票关闭仍须另核原 AC + 原依赖 + 全部必要证明，子票通过 ≠ 物理/Full 通过。

## 运行现状

| 场 | 栈 | 结果 | 证据路径 |
| --- | --- | --- | --- |
| tracking-15-ap-cpu | AP | 完整同场闭环全部本地门通过（含 791 载荷时间戳） | `validation/40-aruco-tracking-15-ap-cpu`（577 成员/7 分片，SHA256 `2bba6fed…c94771`）；输出 `validation/coordination/aruco-15-ap-*.json` |
| tracking-10 | PX4 | 旧成功场；785 载荷时间戳通过，**末尾 HOLD 缺口 + writer 图缺口保持原判** | `validation/40-aruco-tracking-10` |
| run16–18 | PX4 | 修复线均为**倍率失败** | 各场快照（原判不放宽） |
| run19 | PX4 | 原生组件计时 v1，tick 60168 在 100.119728ms 失败；15 帧 | `validation/40-aruco-tracking-19-px4-component`；归档 SHA256 `0c42c2c…10bb` |
| component-candidate-02 | PX4 | v2 构建、封存、准入和有界原生冒烟通过；**未飞行** | `validation/px4-component-candidate-02`；manifest SHA256 `9806c6cb…2b80` |

## #104 子票完成条件

1. **双栈真实同场证据满足冻结上限、不许回放替代**
   - AP：**满足** — AP15 同场 图像→公共命令→原生 MOVE/HOLD→物理轨迹+退场，全门通过（12,001 tick、最大跟踪误差 0.472m、恢复末窗 0.148m、倍率单锚无追赶、72 MOVE/16 HOLD 字段精确、末尾 HOLD request91 在 LAND 前有真实原生位置样本、791 载荷时间戳）。
   - PX4：**未满足** — 缺修复后完整同场通过（见下「PX4 闭合所需新证据」）。
2. **交付源码/配置身份、准确命令、原始结果、失败边界；仅关本子票** — 基本具备：`docs/plan/40-aruco-run-contract.md`（冻结 profile SHA、命令、candidate、审计入口）、AP15 归档与失败边界记录。AC1 双栈满足前子票保持 OPEN。

操作步骤：①任务/运行器源 + RGB reader + target intent 公共速度入口 — 完成（contract 实际接口表）。②原生运行时 + 同场图像/目标/CDR/真值独立审计命令 — 完成（contract 独立验收表）。③每栈单独一场覆盖出现/移动/遮挡/恢复 — AP 完成（AP15 四阶段）；PX4 待完整场。

## #40 父票验收（原 AC，不因子票通过而关闭）

1. 冻结场景/标定/外参/有效期/遮挡策略 — **满足**（`aruco-tracking-v1.json` SHA 绑定；ID23/0.5m；age/distance/speed/jump/reprojection 上限；case5 遮挡/恢复）。
2. 图像/检测/机体系目标/**双栈**飞行同场关联 — AP 满足；**PX4 未满足**（无修复后完整同场）。
3. 出现/移动/遮挡/恢复分别验证距离/速度/突跳门槛 — AP 满足（四阶段分别审计）；PX4 未完整。
4. 回放仅接口测试，真实传感器到飞行闭环才关闭 — 两场均真实 SITL；AP 闭环已过，PX4 待定。
5. 交付命令/身份/预期/结果/边界 + 主代理复核 — 交付物在；双栈 AC2 与主代理复核未完成。

## 同场链 vs 跨场拼接（关键纪律）

每栈的 图像→目标→CDR→真值 必须来自**同一 run/epoch**（contract 第 20 行）。不得把 AP15 的图像链、PX4-10 的时间戳或任何不同场的原生证据拼成一个"闭环"。PX4-10 的 785 时间戳只属于该旧场，不能抵 PX4 修复后新场的门。

## 不新增的义务

连续 DDS setpoint **没有原生 ACK 通道**（contract 第 68 行）。公共受理、原生下发、离散服务/VehicleCommand ACK、动作完成分别报告。本矩阵**不为 setpoint 新增"原生 ACK"义务**；闭环由原生字段 + 飞控反馈 + 物理真值共同证明。

## PX4 闭合子票所需的确切新证据

一场新的 PX4 v2 诊断候选运行（下一编号 run20），在**单一 run/epoch** 内通过 AP15 已过的全部同场门，且全部取自该场自身：

- physical：几何/逐 tick 跟踪/恢复/包线/两机落地 — `tools/audit_aruco_tracking_physical.py`
- rate：单锚/累计迟到/完整倍率窗 — `tools/audit_aruco_rate.py`（run16–18 在此失败）
- 公共原始链 + loss-HOLD — `tools/audit_aruco_tracking_raw.py`（自身 pending，原生另验）
- native moves 字段精确 — `tools/audit_aruco_native_moves.py`
- native holds **含末尾 HOLD**（LAND 前需真实原生位置样本）— `tools/audit_aruco_native_holds.py`（PX4-10 缺）
- publisher/writer 图（记录时刻排他 + writer 完整退场）— `tools/audit_aruco_publishers.py`（PX4-10 缺）
- 原生载荷时间戳 — `tools/audit_aruco_native_timestamps.py`（须取新场自身样本，非 PX4-10 旧值）

真实运行非回放；v2 的构建、准入和原生冒烟不能代替 run20 的完整同场结果。

## 仍 OPEN

#104、#40、Full 均 **OPEN**。单项通过或普通飞行采集不等于完整闭环验收；R1、RateUnmet、旧失败记录保持原判。
