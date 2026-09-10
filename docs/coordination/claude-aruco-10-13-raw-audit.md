# Claude：tracking-10（PX4）与 13-ap（AP）成功捕获的原始 CDR 独立审计

对象：两份**成功**相机闭环捕获（原状态 `captured_pending_independent_audit`）——
`validation/40-aruco-tracking-10`（run `aruco-track-69b75c6f3c`，epoch
`e77b1ed46ede49d68e2e68edddc3fd25`，89 帧 / 16 null，camera vehicle_id=2 即 PX4
为选中栈）与 `validation/40-aruco-tracking-13-ap`（run `aruco-track-56b317f796`，
epoch `3662bc056ae74e0abed662214a8010bd`，90 帧 / 15 null，camera vehicle_id=1
即 **AP 为选中栈**，该路径首次真实行使）。审计器为同 tick 修复后的当前版本
（`tools/audit_aruco_tracking_raw.py`，48 项测试本短片在 WSL ROS 复跑全过）。

方法：完整实跑 `audit()`（capture-root 入口，含共享 timeline 阶段原阈值）＋
分阶段 `verify_raw_capture`/`reconcile_identity`/`public_chain`/`adapter_chain`/
`_verify_frames`/`loss_hold_chain`；WSL ROS 仅用于 CDR 反序列化，无节点/仿真/UE/
编译；证据只读；输出 x-mode 新写（绝不覆盖）：

- `validation/coordination/aruco-10-raw-audit.json`（30397 B，sha256
  `1c736f586ee333a7d00ffca63a05d790bf579b65cae7b0eced4e5b2426224c26`）
- `validation/coordination/aruco-13-ap-raw-audit.json`（30194 B，sha256
  `b68b34bb5c38ed23cf97a79603361acc22a954010e52a7bb3106d94732f14e44`）

## 结果（两场均首次完整实跑即通过全部子门；未发现 auditor bug，未做任何修复）

| 阶段 | 10：arducopter(peer) | 10：px4(选中) | 13-ap：arducopter(选中) | 13-ap：px4(peer) |
|---|---|---|---|---|
| hash 全链/计数/起止 | pass | pass | pass | pass |
| provenance 对账（builder/epoch source + rc_take pin） | pass | pass | pass | pass |
| public_chain（逐请求 deserialize↔envelope、恰一终态、SessionState 身份、异机样本） | pass：5 请求、**reject 0**、state 15764 | pass：93 请求、**reject 0**、state 15646 | pass：92 请求、**reject 0**、state 15802 | pass：5 请求、**reject 0**、state 15710 |
| adapter_chain | pass（0 动作） | pass（14220 动作 / 88 实发 = 72 MOVE+16 HOLD） | pass（14314 动作 / 87 实发 = 74 MOVE+13 HOLD） | pass（0 动作） |
| 异机 /prometheus/ 样本 | 0 | 0 | 0 | 0 |

- **frames 内容门**：10 = 89/89、13-ap = 90/90 全字段对账 + PNG 边界内重 hash 全过。
- **loss-HOLD 内容门**：均 **closed**——10：**14 周期**（89 观测 / 88 消费 / 72 MOVE /
  16 HOLD）；13-ap：**11 周期**（90 观测 / 89 消费 / 74 MOVE / 13 HOLD）。每周期为
  实测 null/过期失效 → 活动 MOVE 按 TTL 真实撤回 HOLD → 新鲜 target 恢复 MOVE。
- **整审 `audit()`**：两场均跑通，status **pending**（审计器永不发 pass）。

## 确切 uncovered（两场相同，逐字）

1. `native_setpoint_correlation: raw PX4 TrajectorySetpoint / AP cmd_gps_pose CDR
   content is not yet mapped field-by-field to the public MOVE/HOLD it carries`
2. `native_fc_ack_or_action_completion: only public TextInfo acceptance is proven;
   no native FC ACK or action completion is claimed`
3. `dds_publisher_exclusivity and full executed process identity beyond the
   reconciled recorder/control build pins are outside this audit`

limitations（同两场）：`Raw public chain and shared product timeline only; native
setpoint closure, native ACK/action completion and publisher exclusivity are not
certified.`

## 边界声明

pending ≠ flight pass 或全验收；失败 08 原判（收尾 rate_unmet）不改；本短片未动
runtime/生产代码/任何配置，未嵌套委派，未 commit/push。复现：
`wsl -d Ubuntu-22.04 -- bash <audit_10_13_raw.sh>`（source ROS + control install
后调用 auditor 现函数；输出 x-mode，已存在即拒绝重写）。
