# 2026-09-07 联合 UE 双载具显示证据轮报告（#21 进展，不关闭）

承接 `bb6e200`，分支 `codex/independent-rgb-integration`。本轮全部由主代理完成（本会话无 gpt-6-astra 可核验配置）。Goal active；未关闭任何 G2/Full 门槛。

## 结果总览

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 联合双机显示正式回归（基础） | **通过**（双机升空显示、相机选择 2→1、4s 暂停、4 tick 单步、继续、降落、manager 0、94156 tick） | `validation/joint-visual-20260907-run8/` |
| Actor 回读↔权威真值逐机核对 | **逐字段一致**：v1/AP [2.8,-3.7,295.7]cm ↔ truth [0.0281,-0.0365,2.9573]m；v2/PX4 [0.3,-1.2,285.2] ↔ [0.00293,-0.0123,2.8522]（tick 51608 同步） | 同上 report.json + truth.jsonl |
| UE 整进程空中重开 | **通过**：tick 52084 停 UE 后物理独立推进 1768 tick（→53852），新 UE 进程绑定当前代次继续显示至降落 | `validation/joint-visual-20260907-run9-reconnect/` |
| 冷重置显示代次隔离（新 `--reset-scene` 驱动扩展首次真实使用） | **通过**：gen 1→2、新 epoch、双机地面新鲜、task_state idle；旧代次数据报文由受验接收端（LatestJointState）拒绝 | `validation/joint-visual-20260907-run10-reset/` |
| 视觉/控制台回归 | 15 视觉 + 96 控制台通过 | 本机 unittest |
| UE 构建清单 | `a61e137…` 与当前 12 项构建输入逐哈希一致（未重编译） | `validation/ue55-build-a61e1371900245b6b2a0ffab531d5ee4/` |

## 实际命令（可复现）

```
D:/date/miniconda/python.exe -X utf8 tools/validate_joint_visual.py --manifest validation/ue55-build-a61e1371900245b6b2a0ffab531d5ee4/candidate-manifest.json --output validation/joint-visual-20260907-run8
… --output validation/joint-visual-20260907-run9-reconnect --reconnect-view
… --output validation/joint-visual-20260907-run10-reset --reset-scene
D:/date/miniconda/python.exe -X utf8 -B -m unittest validation.test_wksim_console_visual -v
```

`--reset-scene` 为本轮新增验证驱动选项（仅 tools/validate_joint_visual.py，不改产品代码）：降落后显式 cold-reset，核验新 epoch/generation 双机新鲜且旧代次不重现。

## 验收对照（#21）

1. **按载具身份创建/更新独立 Actor**：v3 ack 携带 vehicle_id 1/2 的独立位置/四元数/旋翼 RPM/旋翼偏航；相机选择 2→1 均有实际选中 Actor 回读，无硬编码单槽。
2. **同画面同场景时间双机不串机**：单一 ack 携带 step/sim_time_ns 与双机状态；回读位置与对应栈权威真值在 tick 51608 逐字段一致（上表），旋翼各自 4 旋翼实值。标签（HUD 文本）与经验证的逐 Actor 状态同源绑定，但 ack 不携带标签字段，无独立标签回读——记为边界。
3. **部分完成**：冷重置旧代次不重现已真实验证（run10 + 接收端拒绝规则）；**「一个载具断流时仅该载具标为陈旧」按当前架构无法由真实产品场景产生**（见下节 HITL）。
4. **真实联合场景+Actor 回读**：全部证据来自同一真实双栈联合场景与 UE ack 回读，未用多窗口/分别运行替代。

## HITL（提交用户，不代为回答）：验收标准 3 前半句与架构现实的冲突

联合状态流是**单一权威屏障**（1ms 步、4ms 输入屏障，双模型同 tick 提交）的全有或全无通道：每个数据报文含双机或整体丢弃（`emit` 对缺失机型 KeyError→丢包），不存在「一机断流、另一机继续新鲜」的产品场景；单机模型/链路死亡会冻结整场景（fail-closed），两机将同时标陈而非仅该载具。UE 侧确有逐载具陈旧实现（`IsJointStale` 逐机 0.75s 龄、`observed_vehicles` 逐机 step/stale/visible 回读），接收端允许同代次单机报文（传输层规则存在），但产品运行路径不产生它。

选项：(a) 修订验收措辞为「单机断流时该载具不得显示为新鲜；当前架构为整场景 fail-closed 同步标陈」；(b) 要求改为逐载具独立显示流架构（较大改动，影响联合权威屏障设计）；(c) 以传输层注入（验证侧 UDP 中继摘除一机报文）证明逐机标记路径，需接受该注入不属于产品场景。未替用户决定；#21 保持 open。

## 失败与边界样本（保留）

- 早前 `joint-visual-20260907-run1..run7-timing`（各轮宿主 100ms 资源冻结/传输零发送等）全部保留；本轮三次尝试一次通过/变体各一次通过。
- 本轮无新失败样本；三场运行服务日志与运行副本随证据目录保留。

## 残留与卫生

三场运行结束均 manager returncode 0、`remaining_group_members` 空；WSL 无 arducopter/px4/Agent/ROS 残留；Windows 无 Unreal 残留。驱动编辑期间 run9 以编辑前文件执行（进程启动时载入），run10 以最终文件执行并复验语法/帮助输出。

#21/#20/G2/Full 保持 open；未放宽任何阈值，未修改 Wayfinder 父图，未推送远端。
