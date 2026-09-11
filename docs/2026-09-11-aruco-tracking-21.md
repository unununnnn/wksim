# ArUco PX4 第 21 场完整闭环结果

`validation/40-aruco-tracking-21-px4-lean` 使用标准 PX4 候选 `/root/wksim-px4-land-7RjMjQ/land-build.json`，关闭 CPU、write 和 WorkQueue 诊断计时，只保留既有异步公共证据与模型真值写入。run 为 `aruco-track-405ebd92a0`，scene epoch 为 `59e79980b4f849c082559e73108e63de`。运行完成 78,716 个固定 1ms 物理 tick，Task 完成后两机落地并正常退场；manager 返回 0，authority 无 fault，源码运行中无变化。

## 同场审计

七项审计全部取自本场自身。公共 raw 审计按设计保留 `pending` 状态，并明确把原生字段、publisher 和 ACK/动作完成留给独立工具；其中公共哈希链、身份、91 帧、13 个 loss→HOLD→recovery 周期、90 个已消费请求、78,717 个唯一 `/clock` tick 和 19,668 个严格原生 barrier 已闭合。其余六项补齐本票所需原生和图证据：

- physical/geometry：通过。91 帧覆盖 static 14、moving 30、occluded 17、recovered 30；最大像素误差 0.872px、最大平移误差 0.00630m。PX4 最大跟踪误差 0.410794m，恢复末窗 0.046968m，最大倾角 0.039287rad，最终高度约 `-2.43e-6m`；AP 协同栈同样落地。
- rate：通过。15 个完整 10 秒窗口均满足 0.5 倍速，首 60 秒实测 `0.4997765289`，整段最坏累计迟到 `67.206783ms`，低于冻结的 100ms 门。
- native MOVE：73 条 PX4 BODY MOVE 与真实 TrajectorySetpoint 逐字段匹配，0 failure、0 unresolved。
- native HOLD：14 个 HOLD 窗口通过，含 LAND 前最终 request 91 的 1 个真实原生位置样本，0 failure、0 unresolved。
- publisher/writer：AP 162、PX4 229 个离散图快照绑定实际 writer 与 raw GID，结论限定为采样时刻排他；writer 身份和退场完整。
- native timestamp：MOVE 616、HOLD 176，共 792 个 setpoint payload 时间戳与唯一 VehicleLocalPosition 匹配，0 failure、0 unresolved。

没有把连续 setpoint 声称为不存在的原生 ACK；公共受理、原生下发、飞控反馈和物理真值仍按运行合同分开报告。旧 run16–20 的倍率失败原件与边界不改判。

## 归档与关闭判定

原件共 568 个成员，归档为 205,190,596 字节、7 个不超过 32MiB 的分片，整档 SHA256 为 `2ce552fe17de60be8f1cbfda441256b0e07789f29000085f484e9e6908ef37f5`。主会话逐分片重算并重组，字节数、整档 SHA 和 568 个成员名都与 `archive.json` 一致，且归档不含 vendor 二进制。

AP15 与 PX4 run21 分别提供每栈单一 run/epoch 的真实传感器到飞行闭环。本场补齐 #104 的 PX4 缺口；结合已关闭的 #103/#53，#104 满足关闭条件。#40 的原依赖 #30/#32/#6 均已关闭，冻结场景/标定、同场双栈关联、四阶段门、真实闭环和交付边界也全部满足；主代理复核后具备独立关闭条件。#104 与 #40 仅在本证据提交推送后关闭，Full 仍按父规格继续推进。
