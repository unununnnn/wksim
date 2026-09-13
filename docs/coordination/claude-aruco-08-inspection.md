# Claude：tracking-08 原始公共命令链 + loss-HOLD 内容核验（diagnostic_only）

对象：`validation/40-aruco-tracking-08`（run `aruco-track-32addd9c38`，epoch
`901d6d10a3934976a899633020d97657`）——第一份完整相机闭环留存（85 帧 / 70 target /
15 null；两 Task 均 status pass 且已落地）。**原判不可改：主监督器收尾 tick 78248
rate_unmet/resource_insufficient，整场 failed；本核验不改判、不构成 flight pass
或全验收。** 结果文件：`validation/coordination/aruco-08-raw-inspection.json`
（x-mode 新写；含全部输入证据 sha256 与审计器本体 sha256。修复后已由 v3 脚本
重生成——旧文件系本诊断自身产物，删除重写，原始 08 证据未动）。

方法：只读逐项诊断，全部使用 `tools/audit_aruco_tracking_raw.py` 现有函数
（`verify_raw_capture`/`reconcile_identity`/`public_chain`/`adapter_chain`/
`_verify_frames`/`loss_hold_chain`/`audit`），WSL ROS 仅用于 CDR 反序列化，
无节点/仿真/UE/编译；raw 以 `aruco-raw-dds.jsonl` 实际 CDR 为准，未用
task.sent 充当。v1/v2 运行不改 auditor；v3（本次）运行在**修复后**的 auditor
上——修复属本短片三文件（auditor + 测试 + 报告），见下"发现与修复"。

## 逐项结果（真实数据）

| 阶段 | arducopter | px4 |
|---|---|---|
| hash 全链/计数/起止 | **pass**（21112 样本） | **pass**（21309 样本） |
| provenance 对账（builder/epoch source + rc_take 源码/库 pin） | **pass** | **pass** |
| public_chain（实际 deserialize 每请求 ↔ envelope 全字段、每请求恰一终态、SessionState 身份、异机样本=0） | **pass**：5 请求（4 setup + LAND），终态全 setup_completed/command_accepted，**reject 事件 0** | **pass**：90 请求（4 setup + 86 command），终态全部 command_accepted（rid 4–89）+ setup_completed（rid 1–3, 90），**reject 事件 0** |
| adapter_chain | **pass**（0 动作；peer 无视觉 MOVE） | **pass**（14194 动作 / 85 实发 = 69 MOVE + 16 HOLD；85 实发恰对上 86 命令减 1 LAND） |
| SessionState 样本 | 15736 | 15608 |

- **frames 内容子门（`_verify_frames` 独立运行）：pass，85/85 帧**——obs↔frame 全字段
  对账（真实十进制字符串 step/frame_id、字符串 sensor_id）、entry.target==obs.target
  深等值、85 张 PNG 全部在 capture-root 边界内重算 sha256 一致（WSL 路径转换）。
- **整审 `audit()`（修复前，v2 运行）：fail** —— 错误为 `suppressed_hold after a
  fresh target was consumed in the hold window`。共享 timeline 阶段（
  `audit_product_timeline` 原阈值）与 hash/provenance/public/adapter 阶段均已在
  loss-HOLD 门前通过；收尾 rate_unmet 本身未被该阶段判失（它检查的是 epoch 留存
  时钟/导线证据）。失败点出在 loss-HOLD 门的动作状态机。
- **整审 `audit()`（修复后，v3 复核）：跑通，status pending** —— loss-HOLD 门
  **closed，14 个完整 失效→TTL撤回→恢复 周期**（85 帧 / 84 消费 / 69 MOVE /
  16 HOLD）；uncovered 只剩 native 三项（见下）。原始 failed 判定不动。

## 发现与修复（loss_hold，照实记录）

- **原审计器裁定（修复前）**：fail，如上。
- **定位**：px4 动作 pos 1686 `suppressed_hold`（record step 59016，now 59252，
  seam_reason `expired_move:target_accepted`）与 link seq 10（新鲜 target step
  59144，valid_until 59444）——该 target 由 **MOVE command_id=14 在同一 authority
  step 59252、但在动作序中更靠后（pos 1687）** 吸收。窗口检查用 `<= now` 把同 step
  后处理的消费算了进去。
- **分类（修复前判定）：审计器模型缺口，非运行时异常**——suppressed 发生的瞬间尚无
  新鲜 target 被消费，紧邻的下一动作即恢复 MOVE，运行时行为本身自洽。
- **修复（本短片已落地）**：删除 suppressed_hold 对全部 links 的 O(actions×links)
  时间窗扫描；安全改由**处理序吸收**结构性保证——MOVE 消费新鲜 target 会保持
  MOVE 活动（其后 suppressed 即 fail）；duplicate 带新鲜 link 时 MOVE 保持活动；
  每个无 command_id link 在其抑制动作消费时做 `_target_verdict`；结尾要求
  idle links 全部被消费。新增真实刻度回归
  `test_same_step_recovery_after_suppression_closes`（复刻 pos 1686：record step
  59016、now 59250/59252 两次 suppressed 后接同 step 59252 的恢复 MOVE），保留
  "suppressed 吸收新鲜 target 即 fail" 负例；48 项测试 Windows/WSL ROS 双环境
  全过，tracking-01/02 失败 run 回归判定不变。
- **修复后真实 08 复核**：loss-HOLD 门 **closed，14 周期**；独立吸收序复算
  （仍标注非审计裁定）同为 closed/14 周期，两实现一致。14 周期中失效类型含
  cached_move_expiry（TTL 到期撤回，如周期 3：撤回 HOLD cid13 @now 59221，
  target 58920 TTL 59220 到期 → 恢复 MOVE cid14 @59252，新鲜 target 59144）与
  消费 null 观测两类；14 周期对应 15 个 null（一个 null 消费时无活动 MOVE）。

## 仍待核验（不补造）

- `native_setpoint_correlation`：PX4 TrajectorySetpoint / AP cmd_gps_pose 的 raw CDR
  已留存（在同 hash 链内），尚未与公共 MOVE/HOLD 逐字段映射。
- `native_fc_ack_or_action_completion`：仅枚举了公共 TextInfo 接受；不声明任何
  native FC ACK 或动作完成。
- `dds_publisher_exclusivity` 及超出已对账 recorder/control build pin 的执行身份。
- `loss_hold_correlation`：**修复后已在真实 run 上关闭**（14 周期；独立复算一致）。
  这只闭合内容子门，不改变原 failed 判定，也不覆盖下列 native 项。
- 收尾 rate_unmet：主监督器资源/速率问题本身另行处置，原 failed 不改。

## 复现

```
wsl -d Ubuntu-22.04 -- bash <诊断脚本>   # source ROS humble + control install 后
# 阶段化调用 tools/audit_aruco_tracking_raw.py 现有函数；
# 输出 x-mode 写 validation/coordination/aruco-08-raw-inspection.json
```

本片未 commit/push、未嵌套委派、未动 runtime/auditor/配置。主会话的收尾大报告
延迟读取改动（PX4 result ~7MB / 14194 actions）与本核验无冲突。
