# 下一阶段：以实际验收推进 Full

用户于 2026-09-12 要求重新规划目标，使用三个 Luna 与 agy、Claude Code、Oh My Pi 持续推进。

## 目标与退出条件

1. **M1：scheduler 全链路。** 合入并联调 Windows launcher、Linux EOF/清理、collector 两阶段外层 PID 证明。独立核验后，在全新目录运行一次真实诊断；原始 trace、身份、丢失计数与退出清理全部审计。诊断通过不等于倍率/PV/飞行通过；随后按 #33/#83 原 AC 继续。
2. **M2：规划器真实输入。** 关闭 GridMap 剩余内存边界缺口，构建完整 EGO（不仅 plan_env），验证 11,000 点真实 ROS 输入及地图占用，再通过原公共控制入口验证绕障。源码检查和编译不能替代真实 clearance/飞行。
3. **M3：逐票收口。** 用当前 GitHub 验收前沿选择依赖齐全的必需票。G6 预算、未知 ABI、硬件与批准缺项仅阻塞相关分支；父票仍按原 AC 与原依赖关闭。Full 全部必要证明齐全才完成总体任务。

衡量进度：实际验收完成、关键阻塞解除、可复查失败原因。测试数量、代理报告和文档篇幅不算产品验收。

最新 M1：`6d38b54` 的 kernel-bpf-03 已完成并通过独立原始核验，正式10.000188298s、321461条事件全部在窗口和PID过滤内，9任务/5owner前后身份、零loss、BPF解绑及全部清理通过。场景tick12184无fault，worst lateness77.256332ms；这是一场ground diagnostic，不能关闭PV/倍率/Full父票。证据 validation/scheduler-kernel-bpf-20260912-03。下一M1/M3工作是分析现有trace并按#83原0.5x/100ms/10s/60s合同核对最终PV；#82已关闭。M2 RflySim消息overlay已真实构建，官方bridge源码已准备，bridge本体/真实反向状态与时钟/stop-cancel仍待完成。以short-cycle-goal.md顶部最新检查点为准。

## 历史阶段分工（不作为当前派发依据）

以下表格保留阶段来源；当前交付、所有权和下一动作统一见 [当前检查点](short-cycle-goal.md)。续派前实时读取代理状态。

| 执行端 | 本切片 | 文件所有权 |
| --- | --- | --- |
| Luna `luna2_scheduler_verify` | 已交付 M1 路径/进程组修复；map runner 窄审计已处理 | 当前只读，续派前核对状态 |
| Luna `luna2_gridmap_probe` | 已交付真实 GridMap 探针与完整体素输入校验 | 当前已交付，主会话集成 |
| Luna `luna2_cloud_publisher` | 已交付点云发布器、反向状态/时钟传输缺口核对 | 当前已交付，主会话集成 |
| Claude `4d5268f4-1d78-48ba-a5d6-aa800447cb1c` | M1 launcher/profile 最后接口复核 | 只读及离线检查 |
| Oh My Pi `6deb2e40-2240-4db2-8c7f-c06bf6724048` | TCP session 到公共 CommandRequest 出口 | planner_command_egress、trajectory_bridge 与测试 |
| agy `d0a07619-281c-408c-813a-d0784cee52a3` | M1 实际资源与 source pin 准入核对 | 只读 |
| 主会话 | 契约、集成、唯一真实执行线、提交与票据 | 不覆盖代理拥有的文件 |

三个 Luna 明确选择 gpt-5.6-luna / xhigh；本次用户再次明确要求派发三端，已执行。不声称接口无法选择/核验的 Fast 设置。外部 harness 保持现有默认配置。

最新已推送：`029fae1` 完整 EGO 构建；`214bdca` 实际 ROS 点云与 GridMap 占用验证。后者完整收到 11,000 个唯一体素，8 个查询通过，原始 132,000 字节独立核对一致；只代表地图输入，静态 odom 为测试夹具。ROS1 反向真实状态与共享 clock 传输尚缺，真实规划绕障和 Full 均未完成。上表为最近切片，执行状态每次实时读取。

## 缩短周期与质量门

- 每端一个完整小切片，通常 2–4 文件、5–15 分钟；交回代码/针对性测试或确切阻塞。完成即接手，不等待整批。
- 关键路径一轮独立复核后优先真实验证。新增反例才扩大测试；禁止反复全量审计、通读历史或重跑已验收票。
- 同一文件只保留一个写入者。串行安排 SITL、UE、MATLAB、tracefs 与原生构建；代理默认只做代码/离线检查。
- 运行使用新目录，保留失败原件，不覆盖既有证据。保留 1ms、native 输入/时钟屏障、无追赶、100ms 累计迟到及原数值/身份/新鲜度门槛。
- 原始日志与产物身份优先，证明范围写清。仅暂存归属明确、已验证且允许公开的内容，不发布厂商源码/二进制，不触碰用户保护文件。
- 无进展超过 10 分钟先检查真实状态再拆分；不重复启动仍运行的任务。

## Goal 服务状态

2026-09-12 再次排障：正式 get_goal 和只读数据库均为 active，无 token 预算、无 continuation deferral；当前任务 inProgress 且 error=null，实际桌面 CLI goals feature=true。没有发现需要清除的暂停状态。当前目标保留，heartbeat wksim 继续绑定同一任务；已精简当前检查点，将旧 blocked/进程记录完整归档。下面的重建事件属于先前历史，本次没有删除或重建 goal，也没有直接修改数据库。

2026-09-12 用户要求修复 Goal。最新 get_goal 返回 null，旧 unfinished 阻塞记录已不存在；主会话通过正式 create_goal 接口重建，并再次 get_goal 确認 `status=active`，threadId 仍为 `01a08b94-d2fe-7361-9c43-2d54e9490f32`，createdAt=`1789170710`，未设置 token 预算。

本文对应当前已生效 Goal；heartbeat `wksim` 保持 ACTIVE 并持续推进。旧 blocked/无法创建的记载属于历史，不再代表当前状态。没有将未完成 Full 伪标为 complete，也没有直接编辑 Goal 数据库。
