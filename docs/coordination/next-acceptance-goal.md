# 下一阶段：以实际验收推进 Full

用户于 2026-09-12 要求重新规划目标，使用三个 Luna 与 agy、Claude Code、Oh My Pi 持续推进。

## 目标与退出条件

1. **M1：scheduler 全链路。** 合入并联调 Windows launcher、Linux EOF/清理、collector 两阶段外层 PID 证明。独立核验后，在全新目录运行一次真实诊断；原始 trace、身份、丢失计数与退出清理全部审计。诊断通过不等于倍率/PV/飞行通过；随后按 #33/#83 原 AC 继续。
2. **M2：规划器真实输入。** 关闭 GridMap 剩余内存边界缺口，构建完整 EGO（不仅 plan_env），验证 11,000 点真实 ROS 输入及地图占用，再通过原公共控制入口验证绕障。源码检查和编译不能替代真实 clearance/飞行。
3. **M3：逐票收口。** 用当前 GitHub 验收前沿选择依赖齐全的必需票。G6 预算、未知 ABI、硬件与批准缺项仅阻塞相关分支；父票仍按原 AC 与原依赖关闭。Full 全部必要证明齐全才完成总体任务。

衡量进度：实际验收完成、关键阻塞解除、可复查失败原因。测试数量、代理报告和文档篇幅不算产品验收。

## 当前六端分工

| 执行端 | 本切片 | 文件所有权 |
| --- | --- | --- |
| Luna `luna_ceiling_bounds` | 虚拟天花板负索引/非有限转换修复 | grid_map.cpp、test_grid_map_init_native.py |
| Luna `luna_planner_build_readiness` | 完整 EGO 构建依赖与最小修复集 | 只读，不构建 |
| Luna `luna_scheduler_shutdown_review` | Linux EOF、预检与进程组清理独立复核 | 只读 profile/host lifetime test |
| Claude `4d5268f4-1d78-48ba-a5d6-aa800447cb1c` | launcher 失败清理证据与 cleanup_verified | Windows launcher 及其测试 |
| Oh My Pi `6deb2e40-2240-4db2-8c7f-c06bf6724048` | collector pre-bootstrap/post-capture 身份接入 | collector 与对应夹具 |
| agy `d0a07619-281c-408c-813a-d0784cee52a3` | 当前最多五项实际验收前沿 | acceptance-frontier.json |
| 主会话 | 契约、集成、唯一真实执行线、提交与票据 | 不覆盖代理拥有的文件 |

三个 Luna 明确选择 gpt-5.6-luna / xhigh；本次用户再次明确要求派发三端，已执行。不声称接口无法选择/核验的 Fast 设置。外部 harness 保持现有默认配置。

## 缩短周期与质量门

- 每端一个完整小切片，通常 2–4 文件、5–15 分钟；交回代码/针对性测试或确切阻塞。完成即接手，不等待整批。
- 关键路径一轮独立复核后优先真实验证。新增反例才扩大测试；禁止反复全量审计、通读历史或重跑已验收票。
- 同一文件只保留一个写入者。串行安排 SITL、UE、MATLAB、tracefs 与原生构建；代理默认只做代码/离线检查。
- 运行使用新目录，保留失败原件，不覆盖既有证据。保留 1ms、native 输入/时钟屏障、无追赶、100ms 累计迟到及原数值/身份/新鲜度门槛。
- 原始日志与产物身份优先，证明范围写清。仅暂存归属明确、已验证且允许公开的内容，不发布厂商源码/二进制，不触碰用户保护文件。
- 无进展超过 10 分钟先检查真实状态再拆分；不重复启动仍运行的任务。

## Goal 服务状态

现有 Goal `01a08b94-d2fe-7361-9c43-2d54e9490f32` 实查仍为 blocked。主会话按用户请求尝试 create_goal，新目标被服务以 unfinished goal 拒绝；不能把未完成 Full 标成 complete 来绕过限制。

本文为已采用的新执行目标，heartbeat `wksim` 持续推进。Goal 服务记录与实际工作状态分开如实报告；接口目前不能替换/恢复未完成 Goal。
