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
| Oh My Pi | #104 逐tick物理/几何审计只读复核 | 仅 physical-review 报告与 test_aruco_physical_review.py，运行源码冻结 |
| agy | #104 实际原生目标CDR解析与关联窗口检查器（不授予通过） | 仅 inspect_aruco_native_targets.py 与自己的 native-correlation 报告；raw记录器已交主会话 |
| Claude Code | #104 原始公共命令链和共同timeline离线审计 | 仅 audit_aruco_tracking_raw.py、测试与自己的报告；PX4候选已提交，源码冻结 |
| 主会话 | 三路结果独立复核、契约/集成、真实运行与票据收口 | 其它已预约接入位置；不与上述写入者并发改同一文件 |

真实 SITL/UE/MATLAB/tracefs 共用资源串行预约；每场唯一输出，只清理自有进程。纯代码/离线测试并行。下一实际运行优先选择依赖齐全且已通过代码复核的一条，不用模拟成功替代真实验收。

## 跟踪

完整 `delegationId/threadId/turnId/deepLink/status` 快照见 `validation/coordination/short-cycle-dispatches.json`；状态以 `codexhost thread read` 实时结果为准。

- [Oh My Pi](codex://threads/71b28520-5317-4b44-aab5-0f3b8329ae9f)
- [agy](codex://threads/9ef3a71a-c4fb-4b72-8950-1df2dae018de)
- [Claude Code](codex://threads/f0e405df-5143-41d8-a5e5-422b0a295c7f)

前轮大型推送已成功，push 进程 `33870` 已退出 0，不再等待该进程。后续仅增量推送已验证提交，未验证代理工作不随提交混入。

2026-09-11 本轮：`50897b8` 完成真实 SLX 11.8 生成、Linux 构建与核心冷重置/冷重建，#70/#71/#72 已逐票关闭；`f240694` 修正相机反馈与重放边界，并取得分栈原生等待真实记录；`071c7fc` 交付公共相机命令发送器，主会话的19项WSL真实消息构造/编排检查通过（含缓存MOVE过期不被去重跳过、ACK未定后重新悬停、uint32编号不回绕）。这些提交均已推送。详见 `docs/2026-09-11-short-cycle-results.md`。当前剩余 29 张开放票据，Full 未完成。#45 专属策略批准出处、ABI 样本合同、G6 数值预算和硬件条件必须按真实证据处理；只阻塞各自分支。原步长、权威时间、输入屏障、100ms 门槛、误差预算与失败原件不变。用户 `docs/Prometheus.gitmodules.reference` 的修改不属于本轮。

2026-09-11 新进展：`a429ccc` 已推送，case5 实际普通任务飞行中视觉采集/几何/速度验收通过，不等于闭环飞行；`32a1f5b` 已推送，同源完整31输入 major/post 两工况各60,120值零差异，26项检查通过，不等于G6。主会话正在显式实验资源准入、JointArUcoTask/raw节点图和Windows实时协调器集成，未经真实运行/独立审计不登记飞行通过。旧Control OEvS3W已实查与当前源码不一致，待PX4构建释放资源后构建新Control。

当前真实测试 `validation/40-aruco-tracking-01` 已启动（主进程session 46675）。PX4 `/root/wksim-px4-land-7RjMjQ` 与Control `/root/wksim-joint-control-FWBLNX` 构建完成，独立资源预检通过。运行源码冻结：三代理现在仅写各自离线审计/复核工具与测试，不改Simulator或运行器；OMP物理审计复核，agy原生目标关联检查器，Claude原始公共命令链+timeline审计。详细当前turn见dispatch JSON。

第一场tracking-01已失败并正常退出：run aruco-track-afba53e79a / epoch d17b518d73844c43ab670adc6845c1e6，tick848、lateness107146683ns触发原100ms倍率保护，RGB未启用、两机未解锁，组残留0。session46675已退出1（驱动），manager正常退0；失败原件已拷回run目录。当前唯一真实运行是tracking-02（session57563），增加既有WKSIM_JOINT_CPU_TIMING只读探针，以区分模型/监督器CPU与分栈native等待；没有放宽倍率或物理门槛。

tracking-02（session57563）已退出1并完成组清理：run aruco-track-0e74873eb6 / epoch48ab11fb5c4c4c679d55a2ed9d2b71f9，tick12136，lateness100152917ns，任务尚未解锁；两次失败不同进展但都不能验收。分阶段探针已取得，GC最高.42ms，晚期4–5ms CPU尖峰分布在health_and_models/encode_send/native_inputs，尚未确证根因。OMP下一片只读按时间重叠分析，agy修正原生分析器禁止坏CDR回退诊断message，Claude继续raw公共链审计。当前没有实际SITL/UE运行，主会话准备更精确采样探针。

tracking-03已退出1且所有运行组已清理：run aruco-track-556a1b0366 / epoch81f44463c34d476e90b7f44e93e6e2a7，tick13992再次rate_unmet，未解锁。session37908与采样74845都已结束。py-spy0.4.2安装在独立/root/wksim-pyspy-bpC2X3，非阻塞99Hz主线程采样2998条，证据validation/aruco-startup-pyspy-01；不作为飞行/倍率通过。主会话已去掉ArUco raw记录器的重复decoded诊断副本（CDR原字节/GID/时间保留）；OMP独占隔离ROS executor微基准，未改产品源码，完成即释放资源。当前无SITL/UE/MATLAB运行。

接续检查点：已推送提交为a429ccc（真实空中视觉场景）、32a1f5b（完整31输入major/post同源零差异）、0f756d6（PX4 land候选构建）。ArUco实验配置/任务/raw记录器/协调器/物理审计当前仍是工作区改动，先完成验收后分组提交；不能git add全库，用户Prometheus.gitmodules.reference保持不动。tracking-01/02已归档分片且逐成员验证，tracking-03已完整retire并拷回run，尚待归档（等微基准释放资源再压缩）。sampler37908/74845都结束，当前无SITL/UE。OMP微基准初稿发现两个执行器争同node和publish后一次spin不能保证callback的问题，已定向中断并在turn2fc3c7bc-04d4-4406-bc35-f465eb15a56c交代修法继续；不要使用该未通过微基准来改产品。Claude原始审计已退修实际task[aruco]嵌套、capture-root布局、真实f32序列化比较、provenance和loss-HOLD缺口（turnf7aa0ce5-baa7-4b2d-b356-0b714ad0b5b2）。agy原生分析器已移除CDR失败回退，并在第一场481条真实CDR解析成功但0命令、0目标，尚需主审有命令场景。下一优先收OMP/Claude；微基准可信后再决定是否复用持久executor。不放宽既有禁止追赶/暗中重锚规则与100ms门槛。

最新主线已推送：890c3c6接入与前三场证据，7752d5a原始公共审计+微基准，0ed3d30修ready快于旧status的竞态，e9e407b补AP真实cmd_vel原始频道，7e5045a补ArUco结束边界监督并保留第四场，d07fcba把相邻pump重复RMW take减为一次（finally中保留失败事件），39项WSL检查通过。第四场起飞成功但ready竞态停止，记录max53.195421ms；第五场run aruco-track-503a94d16a/epoch dfd6110631dd412aa051fec1489ccaee在tick6148再次rate_unmet（107.884012ms），已退场。第五场证明静态优化尚不能称倍率问题解决。当前无实际SITL/UE，准备验证单次drain路径；下一场继续保持无并行重测试/压缩。OMP执行器微基准负结果已接受，不改成持久executor；agy只写cmd_vel/ENU解析与测试定义，Claude只写loss-HOLD因果审计与测试定义，须主会话在真实运行结束后执行。
