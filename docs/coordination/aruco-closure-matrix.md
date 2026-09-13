# ArUco 双栈闭环收尾矩阵（#104 子票 / #40 父票）

状态：2026-09-11。把 #104 与父票 #40 的验收要求映射到已存证据与关闭判定。run21 已在冻结门槛下完成 PX4 单场闭环，并由七项同场审计闭合；run16–20 的失败原件与原判保持不变。

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
| component-candidate-02 | PX4 | v2 构建、封存、准入和同实例两批 WorkQueue 冒烟通过；已用于 run20 | `validation/px4-component-candidate-02`；manifest SHA256 `9806c6cb…2b80` |
| run20 | PX4 | 55 帧、43 MOVE 原生字段及 publisher 图通过；tick 65440 在 `101.021467ms` 倍率迟到失败，未完成终态 HOLD/降落 | `validation/40-aruco-tracking-20-px4-workqueue`；归档 SHA256 `06bf9c53…76c9c`；分析见 `docs/2026-09-11-aruco-tracking-20.md` |
| run21 | PX4 | **完整同场闭环全部本地门通过**：91 帧、73 MOVE、14 native HOLD、792 payload timestamp、AP/PX4 162/229 图快照、两机落地；最坏累计迟到 67.207ms | `validation/40-aruco-tracking-21-px4-lean`（568 成员/7 分片，SHA256 `2ce552fe…37f5`）；输出 `validation/coordination/aruco-21-px4-*.json`；详见 `docs/2026-09-11-aruco-tracking-21.md` |

## #104 子票完成条件

1. **双栈真实同场证据满足冻结上限、不许回放替代**
   - AP：**满足** — AP15 同场 图像→公共命令→原生 MOVE/HOLD→物理轨迹+退场，全门通过（12,001 tick、最大跟踪误差 0.472m、恢复末窗 0.148m、倍率单锚无追赶、72 MOVE/16 HOLD 字段精确、末尾 HOLD request91 在 LAND 前有真实原生位置样本、791 载荷时间戳）。
   - PX4：**满足** — run21 同场 91 帧四阶段、73 MOVE、14 native HOLD（含末尾 request91）、792 timestamp、publisher 图、物理/几何、倍率和退场全部通过。
2. **交付源码/配置身份、准确命令、原始结果、失败边界；仅关本子票** — **满足**：`docs/plan/40-aruco-run-contract.md` 提供冻结 profile、命令、candidate 和审计入口；AP15、PX4 run21 完整归档，run16–20 的失败边界保留。

操作步骤：①任务/运行器源 + RGB reader + target intent 公共速度入口 — 完成（contract 实际接口表）。②原生运行时 + 同场图像/目标/CDR/真值独立审计命令 — 完成（contract 独立验收表）。③每栈单独一场覆盖出现/移动/遮挡/恢复 — AP15 与 PX4 run21 均完成。

## #40 父票验收（原 AC，不因子票通过而关闭）

1. 冻结场景/标定/外参/有效期/遮挡策略 — **满足**（`aruco-tracking-v1.json` SHA 绑定；ID23/0.5m；age/distance/speed/jump/reprojection 上限；case5 遮挡/恢复）。
2. 图像/检测/机体系目标/**双栈**飞行同场关联 — **满足**：AP15 与 PX4 run21 各自保持单一 run/epoch 链。
3. 出现/移动/遮挡/恢复分别验证距离/速度/突跳门槛 — **满足**：两栈均由四阶段 physical/geometry 与 raw loss/recovery 审计验证。
4. 回放仅接口测试，真实传感器到飞行闭环才关闭 — **满足**：两场均为真实 UE + SITL + DDS 闭环，不使用回放替代。
5. 交付命令/身份/预期/结果/边界 + 主代理复核 — **满足**：运行合同、成功归档、独立审计和历史失败边界齐全，主代理已逐项复核。

## 同场链 vs 跨场拼接（关键纪律）

每栈的 图像→目标→CDR→真值 必须来自**同一 run/epoch**（contract 第 20 行）。AP 使用 AP15；PX4 使用 run21，未把 PX4-10 的 785 时间戳或其它不同场的证据拼接进新场闭环。

## 不新增的义务

连续 DDS setpoint **没有原生 ACK 通道**（contract 第 68 行）。公共受理、原生下发、离散服务/VehicleCommand ACK、动作完成分别报告。本矩阵**不为 setpoint 新增"原生 ACK"义务**；闭环由原生字段 + 飞控反馈 + 物理真值共同证明。

## PX4 同场闭合证据

run21 在单一 run/epoch 内通过 physical、rate、公共 raw/loss-HOLD、native MOVE、native HOLD、publisher/writer 和 native timestamp 七项审计。公共 raw 工具自身按契约返回 `pending`，其列出的 native setpoint 与 publisher 缺口由同场独立工具闭合；连续 setpoint 不存在的 native ACK 不作为新增义务。

## 关闭判定

#104 与 #40 已在证据提交 `d86efb3` 推送后分别按自身范围关闭。Full 继续 **OPEN**。R1、RateUnmet 和所有旧失败记录保持原判。
