# OMP 当前 Control/waypoint 修复独立审查（2026-09-13，只读）

范围：主会话当前三项源改动（`ap_mixed_candidate` FINAL_CONTROL→c2、
`audit_mixed_control` current→c2 保留历史、`pv_trajectory_task` waypoint 入场余量）
与证据原件。未改实现/旧原件；无 native/构建/Git/嵌套；只做定向纯读与反例核对。

## 1. 身份层：严格单一新运行身份成立，历史链正确

- `ap_mixed_candidate.py:23` `FINAL_CONTROL_SHA=6fe8c0b3…`（c2IXOr）；
  `:26` LEGACY 保留 `d9fdfc74…` 且 `:89` 历史路径要求"exact manifest 且无消息候选"——
  新运行只认 c2 ✓。
- `audit_mixed_control.py:27` current=c2；`:30-31` 保留
  `HISTORICAL_PV_CONTROL_SHA`（a6a17b42=ZlTVa4）与 `PREVIOUS_PV_CONTROL_SHA`
  （3d04d53a=rWolCy），`:28-29` 注释明写"历史运行按原候选审计，不接纳其入新飞"；
  `:160-170` 历史 SHA 只进**审计选择集**并配消息一致性分支——审计链保留而未放宽准入 ✓。
- 证据 `installed-check.json`：c2IXOr 通过 repo/staged/install/build/message 全套
  check()；ZlTVa4 因 8 份支持文件失配被拒——拒绝理由实证、严格 ✓。
- 诊断不得提升规则原样：`joint_profile.py:219-220`
  `if 'rate_timing_probe' in flight: raise` 未动 ✓。

## 2. 发现：`docs/plan/33-final-combo-rate-candidate.md` 未同步

主会话"docs final-combo 当前命令同步"在本树不成立：该文档 12-16 行仍给
`--control-manifest …/wksim-joint-control-0DQQz9/…`，59-63 行诊断命令仍是
**OEvS3W**（已被 33 文档自身宣布淘汰）。`39-planner-run-contract.md:118` 已是
c2IXOr。**阻断项**：33 文档的0DQQz9/OEvS3W命令必须从"当前命令"降格为历史或更新为
c2IXOr，否则读者可误执行旧身份。

## 3. waypoint 源改动审查（pv_trajectory_task.py diff edc717a）

改动：wait 入场条件加 `fresh()` 与速度 ≤.4 余量；dwell 仍 2s、原 .5/.5/.15 门不变。
- **无短窗/滑窗挪动**：被审计物理窗口与三门未动（失败证据
  `baseline-physical-failure.json` scope 自证"no changed bound/window/axis"）；
  失败形态为窗口**起始样本** tick 55012 速度 .505341（2001 样本中 2 次违例均在
  起始），与"入场余量"修复方向一致 ✓。
- **无动作顺序/取消语义问题**：offer→wait→dwell→legs 顺序未动；`fresh()` 只读，
  dwell 的取消/轮询机制未动；fresh 加入使 dwell **更严**（陈旧状态失败而非放行），
  非弱化 ✓。
- **但修复未证实，不应用边界失败换通过**：
  a) 审计测**物理** 1ms 真值，余量设在**估计**侧——估计滞后时物理仍可在窗口内超 .5；
  b) .4 余量没有实测减速剖面证据（应从 xtj8wk8i 原件的真值轨迹量出 AP 从 .5 降到
  ≤.4 所需 tick 数再定余量，或用停留窗替代猜定阈值）；
  c) 新运行**尚未执行**，修复有效性零证据。
  结论：方向正确、语义安全，但必须由新真实运行+原 raw 审计复核；若再失败，
  应改为有证据的入场稳定窗（实测减速剖面定长）而非继续调余量。

## 4. 明确阻断清单

1. 33 文档旧身份命令未降格（§2）。
2. .4 余量无实测依据；新运行未执行——当前**不能**据本改动称 waypoint 修复成立。
3. 原始物理失败保持 OPEN：tick 55012 速度 .505341 vs 原门 .5，PX4 已通过、AP 未过。

## 有界结论

身份层与历史链审查**通过**（严格单一 c2 准入、历史只读、诊断不提升规则完好）；
waypoint 改动**语义安全但未证实**；文档同步缺失为当前唯一可立即执行的修正项。
