# 三代理短周期 Goal

2026-09-10 用户要求合理设置 Goal、缩短任务周期，并将 Claude Code 加入原 OMP/agy 分工。实查本任务 Goal 为空后已创建 active Goal，继承原 Full/G0–G6 和所有必需票据终态；未指定 token 预算，因此未设置预算。不能因一个切片或一轮任务完成而将此 Goal 标为完成。

## 执行节奏

- 每代理一次一个可独立验收的小切片，通常 2–4 个文件。以 5–15 分钟交付代码、针对性测试或准确阻塞为目标，不把此时间当完成保证。
- 完成一个就复核、合入或退回修正，然后派下一片；不等待整批完成。超过 10 分钟没有可见进展，先查实际状态，再拆小或调整，不直接取消重启。
- 主会话持续处理集成、实际验证和阻塞；后台接力沿用 automationId `wksim`，已从每 10 分钟缩短到每 3 分钟。主动工作时不等后台周期。没有实质变化时保持安静。
- 减少通读旧报告、重复发现、重复建图、长文档及对已通过项目的盲重跑。发现新失败或改动相关路径时才扩大检查。
- 默认保留三个明确指定的外部 Harness 配置，不改全局模型、权限或 Fast；不嵌套委派。

## 当前唯一写入者

| 代理 | 此轮交付 | 写入边界 |
| --- | --- | --- |
| Oh My Pi | #104 显式 flight fixture case5：初始RGB禁用、首张捕获锚定实际相机/载具、12s移动/遮挡/恢复场景；只实现，尚不编译/运行 | UE的RgbFixture.cpp/.h、GameMode.cpp、View visual.py与自己的报告；case0..4保持已验收行为 |
| agy | #59 同源 11.8 major记录器已报告交付及C0采样对齐，等待主会话独立复核，不等于G6通过 | `build_generated_e0_major.py`、`test_generated_e0_major.py`、自己的报告/新证据；源码/运行证据尚未主验收 |
| Claude Code | #20/#33 候选源码结论校正：不以无参数日志排除autosave、不以ekf2未注册屏障排除间接影响；只读 | `claude-native-wait-next-probe.md` 与自己的候选源 JSON；生产者/分析器冻结，下一测量由主会话安排 |
| 主会话 | 三路结果独立复核、契约/集成、真实运行与票据收口 | 其它已预约接入位置；不与上述写入者并发改同一文件 |

真实 SITL/UE/MATLAB/tracefs 共用资源串行预约；每场唯一输出，只清理自有进程。纯代码/离线测试并行。下一实际运行优先选择依赖齐全且已通过代码复核的一条，不用模拟成功替代真实验收。

## 跟踪

完整 `delegationId/threadId/turnId/deepLink/status` 快照见 `validation/coordination/short-cycle-dispatches.json`；状态以 `codexhost thread read` 实时结果为准。

- [Oh My Pi](codex://threads/71b28520-5317-4b44-aab5-0f3b8329ae9f)
- [agy](codex://threads/9ef3a71a-c4fb-4b72-8950-1df2dae018de)
- [Claude Code](codex://threads/f0e405df-5143-41d8-a5e5-422b0a295c7f)

前轮大型推送已成功，push 进程 `33870` 已退出 0，不再等待该进程。后续仅增量推送已验证提交，未验证代理工作不随提交混入。

2026-09-11 本轮：`50897b8` 完成真实 SLX 11.8 生成、Linux 构建与核心冷重置/冷重建，#70/#71/#72 已逐票关闭；`f240694` 修正相机反馈与重放边界，并取得分栈原生等待真实记录；`071c7fc` 交付公共相机命令发送器，主会话的19项WSL真实消息构造/编排检查通过（含缓存MOVE过期不被去重跳过、ACK未定后重新悬停、uint32编号不回绕）。这些提交均已推送。详见 `docs/2026-09-11-short-cycle-results.md`。当前剩余 29 张开放票据，Full 未完成。#45 专属策略批准出处、ABI 样本合同、G6 数值预算和硬件条件必须按真实证据处理；只阻塞各自分支。原步长、权威时间、输入屏障、100ms 门槛、误差预算与失败原件不变。用户 `docs/Prometheus.gitmodules.reference` 的修改不属于本轮。
