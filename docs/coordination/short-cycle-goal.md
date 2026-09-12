# 当前 Goal 执行检查点

更新：2026-09-12。只保留当前状态；旧记录逐字节保存在 [历史归档](short-cycle-goal-history-20260912.md)，仅查证历史时读取。原验收计划见 [执行计划](next-acceptance-goal.md)。实时工具、Git 与原始证据优先于文档。

## Goal 与续跑状态

本轮 get_goal 为 active，无 token 预算，thread `01a08b94-d2fe-7361-9c43-2d54e9490f32`，createdAt `1789170710`。只读数据库核对一致，continuation deferral 为零；任务接口返回 inProgress、error=null。实际桌面 CLI 的 goals feature 为 true。没有发现暂停或预算阻塞；保留当前 goal，不重复创建、不虚假完成、不直接修改数据库。

heartbeat `wksim` 绑定同一任务，保持 ACTIVE、每三分钟检查一次。续跑读取本检查点及所需源文件，不把历史 blocked、已退出 handle 或旧分工当成当前状态。正式 goal 工具无编辑 objective/resume 参数；阶段进度在本文件更新。清理后的下一回合已收到正式 goal continuation，自动续跑已实际触发。

## 已完成与证据范围

- HEAD/origin 已推进到 0769c3a（Control 安装闭包/实证/最终候选准入）；旧基线 b1ad906；c63e3c2 保留 M1 kernel-bpf-03 原件，b1ad906 提交 timing-analysis，不重复同一诊断。
- M1 ground 诊断 formal 10.000188298 秒、321461 条事件；九任务/五 owner 前后身份、零 loss、BPF 解绑和清理通过；tick12184 无 fault，最差迟到 77.256332ms。仅诊断，不能充当 PV、长期倍率或 Full 验收。峰值在 formal 停止后 203.738653ms，不能编造内核因果。证据 `validation/scheduler-kernel-bpf-20260912-03/`。
- 完整 EGO 构建 029fae1、真实 ROS1 11000 点云与八个 GridMap 占用查询 214bdca 已完成；静态 odom 是夹具，真实绕障/净空/飞行未通过。
- ROS2 TCP 公共出口 0555f96 已完成 callback/传输及独立 RMW 检查；不是 FC 物理验收。
- 当前没有存活的主会话 native/ROS/SITL 执行。handle22543 已链接失败，handle21492 添加字段映射后完整构建成功；reverse fixture L0Dfdj 已通过并清理。所有旧 handle 均已终态，不再等待或重启。

本轮 #83 实跑 joint-public-flight-nqyqcagl 已 FAILED：tick53128 累计迟到104260439ns，原100ms门槛触发 RateUnmet。双机已起飞但任务未完成，source_unchanged=true、Control正常退出、十个自有PGID独立清理通过。证据 validation/33-final-combo-luna/20260912-nqyqcagl，完整原件仍保留；绝对路径 raw PV audit在 failed-run gate拒绝。#83仍OPEN/needs-triage，评论 issuecomment-5643302702。rate-analysis.json数值已独立逐项复算；wire-interval-review.json纠正6.2/6.57ms是step→外发sensor间隔，含日志/clock/模型RPC等，不能排他归因AP。M1另有kernel-wire-correlation.json：tick5504直接诊断wait_px4=5419791ns、wait_ap=127634ns，不跨run外推。

当前新增 namespace 接线：netns_handoff.py 已实际 Ubuntu→Rfly SCM_RIGHTS 交接并通过 loopback，Rfly mount/IPC与Noetic路径保持不变；最终证据 validation/netns-handoff-20260912-03 已持久化并与当前源码SHA核对。旧 /mnt/wsl 临时结果曾随WSL boot变化丢失，不充当持久证据。handle41886/12942/21600均已退出0，当前无主会话native运行。跨distro ROS/DDS现已验证：validation/cross-distro-ros-20260912-04；01/02/03发现topic却收不到数据，03证明XML已加载且GUID不同，最终定位Humble ROS_LOCALHOST_ONLY=1在XML后重新加入SHM。04在已验证私有netns内使用XML的127.0.0.1 UDP白名单并设ROS_LOCALHOST_ONLY=0，三时间样本/五消息及暂停clock全通过，owner与visitor均退出0。不得将此网络配置全局套给现有飞控或放宽物理门槛。

待用户语义澄清：已通过异步问题请求确认是否允许 start_tick100、到达120 时保留start_time并首次求值t=.020、不补历史样本。该问题未获回答；不得把等待视为同意，不修改当前start_in_past/等值闸门。其他独立工作继续。

OMP22g已完成并由主会话通过202项检查：显式opt-in有序控制帧、完整gate身份门、v2冻结快照、recover保留模式均已修复；主会话去掉v1重复JSON解析。sender/node仍未启用，真实停止/释放ACK待接线，不能把CANCELLED无输出当FC已停。

## 下一步：每次完成一个验收切片

1. **M2 bridge 已构建并完成隔离反向传输验证。** bool模板修复后第一次链接暴露 BoundingBox.Class→class_name、DetectionInfoSub.trackIds→track_ids 缺映射；新增独立 wksim_ros1_bridge_mappings 包，未改冻结消息。完整构建3min13s成功，print-pairs核验六个必要类型；实际ROS2→ROS1 Clock/Odometry/UAVControlState/嵌套改名字段、三时间样本及暂停clock通过，四个自有进程退出0，namespace无残留。证据 validation/ros1-bridge-runtime-20260912。RflySim工作区 /root/wksim-ros1-bridge-humble-8oGKuV，消息56份源pin未变。下一步是真实联合场景namespace/状态源接线，不把夹具当FC闭环。
2. **M3 #83 保持失败，不重跑。** 0769c3a 的 ZlTVa4 曾通过实际构建/仓库外安装验证，并用于已失败的 nqyqcagl。此后新增pump控制事件和session.stop原子性修复，142项主验通过；因此ZlTVa4再次与当前runtime不一致，任何新实跑前必须fresh-build，不可仅修改pins。成功hold/cancel共用event allocator，错误identity/tick/anchor/计数不改状态；v1 wire和终态无输出语义未改，未证明物理取消。
3. **M2 剩余闭环。** 真实反向 odom/control_state、同源 clock、stop/cancel、namespace 连接及实际绕障仍缺。Claude18z 已完成时序核对：生产端保存时刻和消费者零延迟/整毫秒要求冲突；保留原时间戳及无追赶约束，不擅加未来 δ 或放宽门槛。停发 Bool 不等于 terminal cancel，控制事件序号须由 pump 统一分配。

## 代理句柄：先查实时状态再续派

| 执行端 | 最近交付 |
| --- | --- |
| Luna luna2_scheduler_verify | timing-analysis 已集成 b1ad906 |
| Luna luna2_gridmap_probe | Control 模块/消息资产闭包已交付，待主验 |
| Luna luna2_cloud_publisher | bridge ABI/环境核对已交付 |
| Claude 4d5268f4-1d78-48ba-a5d6-aa800447cb1c | 18-AC wire时序纠正已完成；不能排他归因模型RPC |
| Oh My Pi 6deb2e40-2240-4db2-8c7f-c06bf6724048 | 22d 控制事件原子性已交付并主验142项；22c错误烧序号版本已修正 |
| agy d0a07619-281c-408c-813a-d0784cee52a3 | rate数值修正版已主验；kernel-offcpu-analysis.json为未核验草稿，不暂存/不接受宽泛因果结论 |

按用户要求以三个 Luna 和三个外部端协作，遵守当前模型指令，不伪报 Fast。每切片唯一写入者，通常 2–4 文件；主验接手前明确所有权。外部派发前运行 codexhost delegate --help；读 JSON 最后一项 progress 和 result，THREAD_BUSY 代表消息未送达。

## 执行约束

主会话独占 SITL/ROS/UE/MATLAB/tracefs/BPF/原生构建执行线；真实性能运行时冻结源码并停止并行重负载。保留 1ms、native 输入/时钟屏障、无追赶、100ms 累计迟到及原身份/新鲜度门槛。真实运行用新目录并保留失败原件。G6 预算、未知 ABI、硬件或批准缺项只阻塞相关分支。全部 Full 必需证明完成后才结案。

不得暂存用户/未验证文件：docs/Prometheus.gitmodules.reference、validation/coordination/short-cycle-dispatches.json、docs/coordination/agy-aruco-native-correlation.md、docs/coordination/claude-native-wait-next-probe.md、tools/inspect_aruco_native_targets.py、validation/test_aruco_native_targets.py、docs/coordination/acceptance-frontier.json。不发布厂商源码/二进制，不终止用户进程。

工作区另有他方控制器/PID/独立profile/runtime/preflight/README/CONTEXT等改动；本轮未修改或暂存这些内容，禁止纳入本任务提交。

本轮EGO静态输入夹具 ego-planner-static-20260912-01 在30s内无Bspline，已失败并清理（handle65988终态）。因启动时发现另一任务在Ubuntu运行run_rate_control_comparison预检，可能有资源重叠，此结果不作性能/根因结论。记录coordination-note.json；后续必须先单独完成并评估两发行版进程检查，不能在同一未评估命令中紧接启动。源码/日志保留，尚无真实planner输出/净空证明。

后续独立两端进程检查均为空后，EGO静态夹具02已成功并退出：真实生成33控制点/37knots，观测障碍占用后合成COMMAND，两个点云、51184膨胀占用点。原始ROS1消息和JSON见validation/ego-planner-static-20260912-02。采样折线净空0.9971919183081722m通过，但不是连续曲线/飞行证明。实际duration=10.802539100943088s暴露适配器整毫秒时长限制；已仅修正终止tick为首次达到原始曲线结束时刻的整数tick，不改knots/start或晚到闸门。真实样条离线准入/完整回放到tick12404 HOLD通过，226项检查通过。当前没有主会话native运行。
