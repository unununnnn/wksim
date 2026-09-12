# 当前 Goal 执行检查点

更新：2026-09-12。只保留当前状态；旧记录逐字节保存在 [历史归档](short-cycle-goal-history-20260912.md)，仅查证历史时读取。原验收计划见 [执行计划](next-acceptance-goal.md)。实时工具、Git 与原始证据优先于文档。

## Goal 与续跑状态

本轮 get_goal 为 active，无 token 预算，thread `01a08b94-d2fe-7361-9c43-2d54e9490f32`，createdAt `1789170710`。只读数据库核对一致，continuation deferral 为零；任务接口返回 inProgress、error=null。实际桌面 CLI 的 goals feature 为 true。没有发现暂停或预算阻塞；保留当前 goal，不重复创建、不虚假完成、不直接修改数据库。

heartbeat `wksim` 绑定同一任务，保持 ACTIVE、每三分钟检查一次。续跑读取本检查点及所需源文件，不把历史 blocked、已退出 handle 或旧分工当成当前状态。正式 goal 工具无编辑 objective/resume 参数；阶段进度在本文件更新。清理后的下一回合已收到正式 goal continuation，自动续跑已实际触发。

## 已完成与证据范围

- HEAD/origin 基线 b1ad906；c63e3c2 保留 M1 kernel-bpf-03 原件，b1ad906 提交 timing-analysis，不重复同一诊断。
- M1 ground 诊断 formal 10.000188298 秒、321461 条事件；九任务/五 owner 前后身份、零 loss、BPF 解绑和清理通过；tick12184 无 fault，最差迟到 77.256332ms。仅诊断，不能充当 PV、长期倍率或 Full 验收。峰值在 formal 停止后 203.738653ms，不能编造内核因果。证据 `validation/scheduler-kernel-bpf-20260912-03/`。
- 完整 EGO 构建 029fae1、真实 ROS1 11000 点云与八个 GridMap 占用查询 214bdca 已完成；静态 odom 是夹具，真实绕障/净空/飞行未通过。
- ROS2 TCP 公共出口 0555f96 已完成 callback/传输及独立 RMW 检查；不是 FC 物理验收。
- 执行 handle 69221、18341、21242 均已终态，不再等待。本轮没有新启动 native 运行；下次启动前核对实际进程。

## 下一步：每次完成一个验收切片

1. **M2 bridge 复核和实际编译。** RflySim `/root/wksim-ros1-bridge-humble-8oGKuV/messages_ws` 两包已构建；bridge 两次失败日志保留。OMP22a 已交付 vector<bool> 模板补丁和 `validation/ros1_bridge_vector_bool_serialization_check.cpp`，尚未主验/编译。先核对 ROS1 bool Serializer/LStream API、空 vector front()、测试是否覆盖实际模板；现有 helper 已处理长度前缀，不可重复。使用完整 EGO `/root/wksim-ego-local-pGqjgO/devel`，msg-only overlay 缺 traj_utils 库。官方基线 611755fd917285316051cbea80507e8b2f6b7ec1。不得删除 FormationAssign 或用 -fpermissive。
2. **M3 Control 安装闭包主验及 fresh build。** Luna gridmap 已交付显式 Python 模块、两份冻结 Bspline.msg、安装态 fallback、sealer 资产校验；报告 39 项纯 Python 检查通过，已由主会话完成 39 项检查、Ubuntu fresh build、仓库外安装态 smoke 和 live sealer 三方校验；Claude18-AA 独立只读复核无阻断。新候选 /root/wksim-joint-control-ZlTVa4/build.json，SHA 3d04d53a5c41d374ee623d16a265e8816d481e5d4433f23a60140a8e8184ecc4；证据 validation/control-install-20260912/，没有物理验收。改动在 envelope、message_pins、build-joint-control.sh、Control CMake、joint_control_candidate.py 及两套测试。构建后必须从 repo 外仅用 install PYTHONPATH 实例化 decoder/节点。旧 rWolCy runtime 过期，不能复用或只改 pins。然后按 #83 原 0.5x/100ms/10s/60s 及双 native flags 实跑；#82 已关闭。
3. **M2 剩余闭环。** 真实反向 odom/control_state、同源 clock、stop/cancel、namespace 连接及实际绕障仍缺。Claude18z 已完成时序核对：生产端保存时刻和消费者零延迟/整毫秒要求冲突；保留原时间戳及无追赶约束，不擅加未来 δ 或放宽门槛。停发 Bool 不等于 terminal cancel，控制事件序号须由 pump 统一分配。

## 代理句柄：先查实时状态再续派

| 执行端 | 最近交付 |
| --- | --- |
| Luna luna2_scheduler_verify | timing-analysis 已集成 b1ad906 |
| Luna luna2_gridmap_probe | Control 模块/消息资产闭包已交付，待主验 |
| Luna luna2_cloud_publisher | bridge ABI/环境核对已交付 |
| Claude 4d5268f4-1d78-48ba-a5d6-aa800447cb1c | 18z 时序核对、18-AA 安装闭包复核已完成 |
| Oh My Pi 6deb2e40-2240-4db2-8c7f-c06bf6724048 | 22b 正修正 ROS bool/LStream/空 vector 和实际模板测试，禁止自行编译 |
| agy d0a07619-281c-408c-813a-d0784cee52a3 | 18-AK PV 准备报告已读，harness failed 与报告结论分开记录 |

按用户要求以三个 Luna 和三个外部端协作，遵守当前模型指令，不伪报 Fast。每切片唯一写入者，通常 2–4 文件；主验接手前明确所有权。外部派发前运行 codexhost delegate --help；读 JSON 最后一项 progress 和 result，THREAD_BUSY 代表消息未送达。

## 执行约束

主会话独占 SITL/ROS/UE/MATLAB/tracefs/BPF/原生构建执行线；真实性能运行时冻结源码并停止并行重负载。保留 1ms、native 输入/时钟屏障、无追赶、100ms 累计迟到及原身份/新鲜度门槛。真实运行用新目录并保留失败原件。G6 预算、未知 ABI、硬件或批准缺项只阻塞相关分支。全部 Full 必需证明完成后才结案。

不得暂存用户/未验证文件：docs/Prometheus.gitmodules.reference、validation/coordination/short-cycle-dispatches.json、docs/coordination/agy-aruco-native-correlation.md、docs/coordination/claude-native-wait-next-probe.md、tools/inspect_aruco_native_targets.py、validation/test_aruco_native_targets.py、docs/coordination/acceptance-frontier.json。不发布厂商源码/二进制，不终止用户进程。
