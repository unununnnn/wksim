# 联合 UE 单机断流同步标陈验收（2026-09-08）

用户既有五项批准中的 #21 选项 (a) 已同步到本地和 GitHub 验收正文：单机断流不得显示新鲜，单一权威屏障整场景同步标陈。#19/#17 前置已关闭；本轮完成最后缺口，#21 可按全部证据验收。Full、#20 的 1×、#31 的深度及 #42 的真实地面站交接分别保持开放。

## 结果与缺陷修复

真实 ArduCopter 输入停流首次揭示 UE 状态错误：权威物理正确冻结，但服务不断发送新鲜的 faulted 状态包，IsJointStale 仅按收包/源时间年龄判定，导致两机仍 fresh。失败完整保留于 validation/joint-stale-20260908/arducopter-run1；其 retained Actor 日志明确 phase=faulted、双 stale=false。

修复：IsJointStale 明确把 faulted/stopped 视为陈旧，正常 running/paused/stepping 不改变。新增只读 joint_actor_query 从实际 Actor 读取身份、位置、姿态、旋翼角与 stale/visible；查询不 ApplyPacket、不刷新源时间或接收龄。驱动通过 PID/PGID/start_ticks/exe 核验后只 SIGSTOP 本次选中 FC，等待真正 InputTimeout；不注入假显示状态。SIGCONT 只用于同一实例清理，无 recover 或抢回任务。

| 真实用例 | 结果 | 共同冻结 tick | 实际 Actor 与原始真值 |
| --- | --- | --- | --- |
| arducopter-run2 | pass | 51673 | 双机位置误差 0cm；四元数 L2 ≤ 2.67e-16；两次查询双 stale=true |
| px4-run1 | pass | 51696 | 双机位置误差 0cm；四元数 L2 ≤ 4.72e-16；两次查询双 stale=true |

两次查询相隔至少一秒，原始模型尾记录、显示位置/姿态/旋翼角均不变；每次新状态包的 sequence 可继续递增，因此 sequence 不被错误当成物理步号。两场正式 stop、manager=0、result=stopped，非正常落地用例，不声称完成任务。各有 11 条自有子进程记录，场景原生 remaining_group_members 为空。旧正常飞行/落地、2→1观察切换、4s暂停/4tick单步/继续、整 UE 空中重开、冷重置隔离仍由 2026-09-07 run8/run9/run10 的真实封存证据支撑。

主代理另直接查看 px4-run1 的 frame-0078.png：同屏真实 P450 机体与旋翼，AP #1 / PX4 #2 均显示 STALE / Step 51696；N/E/D HUD 与实际 Actor 回读一致。载具位置接近而可重叠，未为分开显示而伪造位移。

## 构建、命令与复核

最终候选：validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json；UE5.5.4 实际 C++ 构建成功，35.79s，含深度组件和只读查询；全部 source/staging SHA256 在构建清单。首次候选 9ffa7a33… 实跑暴露缺陷；代理在交付后统一换行造成的字节漂移，经逐文件仅换行等价核验后恢复到真实暂存字节，继而以真正状态修复重新构建，未把改过的源码冒称已构建。

```powershell
python -X utf8 -B tools/validate_joint_stale.py --manifest validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json --output validation/joint-stale-20260908/arducopter-run2 --target arducopter-fc
python -X utf8 -B tools/validate_joint_stale.py --manifest validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json --output validation/joint-stale-20260908/px4-run1 --target px4-fc
python -X utf8 -B tools/audit_joint_stale.py validation/joint-stale-20260908/arducopter-run2 --output validation/joint-stale-20260908/arducopter-audit.json
python -X utf8 -B tools/audit_joint_stale.py validation/joint-stale-20260908/px4-run1 --output validation/joint-stale-20260908/px4-audit.json
```

两个原始审计各重复运行两次，输出字节一致。审计重新读取 retained truth.jsonl/故障/进程结果，并与四次实际只读快照比较；不只信任驱动 pass 字段。第一次审计脚本仅在统计子进程记录时读错字段（KeyError children），已改读 epoch/children.json，未影响核心比较。驱动的针对性反例检查覆盖 fresh/错 epoch/位移/未来 tick 拒绝。

当前只读查询没有 RPM 字段；正常 Actor ACK 原有 RPM 和本次旋翼角冻结分别记录，不声称新增 RPM 独立回读。数值是显示几何误差，绝非 G6 动力学等价预算。未修改或关闭 Wayfinder 父图，未改许可、健康检查、RC、物理节拍或1×验收门槛。
