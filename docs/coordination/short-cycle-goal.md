# 当前 Goal 执行检查点

更新：2026-09-12。实时 Goal、Git、代理状态及原始证据优先。刷新前检查点逐字节保存在 [本次归档](short-cycle-goal-history-20260912-175837.md)，更早记录见 [历史归档](short-cycle-goal-history-20260912.md)。只在查证具体历史时读取归档；原验收范围见 [执行计划](next-acceptance-goal.md)。

## Goal 健康状态

- thread：`01a08b94-d2fe-7361-9c43-2d54e9490f32`；goal：`63bdd724-67ae-4701-8fae-73e2a03578f5`。
- 本次 get_goal 和只读数据库一致：active，token_budget=null，continuation deferral 为零；桌面实际 CLI 的 goals=true；任务未归档，接口返回 inProgress、error=null。
- 运行记录显示 07:53:23 UTC 和 08:32:10 UTC 两次回合结束后立即开始下一轮。续跑机制已有实际执行记录；清理后的下一回合已收到正式 Goal continuation，自动续跑验证完成。
- 不重复创建、不虚假结案、不改数据库。现有 Goal 工具没有 objective 编辑或 resume 参数；最新阶段和完成项以本检查点为准。累计 tokensUsed 是消耗统计，不能当作预算上限。
- heartbeat `wksim` 绑定同一任务，ACTIVE，每三分钟检查。无变化或不可行动时静默，只在重要变化、完成、失败或需用户行动时通知。心跳只辅助跟进，不能代替 Goal 完成验收。

## 当前关键路径

本轮已收到正式 Goal continuation，清理后自动续跑得到实际验证。最新 Git 为准。验收工作区仍在 Ubuntu-22.04 `/root/wksim-release-acceptance-fe3`、分支 `codex/planner-release-validation`，其私有实验改动尚未合入主仓库。主仓库只集成已验证的运行时修复与证据，保护他方 runner/runtime/控制器改动。

1. **非阻塞接收修复已通过主验。** 安装态 helper 02 暴露 Linux accept() 不继承 listener 的 nonblocking，第二次 recv 阻塞 ROS executor；receiver 又把 EAGAIN 当 invalid_socket。主会话修正 accepted socket.setblocking(False) 与 BlockingIOError→空批次，保留 EOF/身份/其他错误门。56 项纯检查、27 项实际 ROS 检查通过。首次 ROS 回归失败原件保留在 `validation/control-nonblocking-20260912/ros-tests.log`，通过记录是 ros-tests-02.log。
2. **新 Control 候选必须用于后续验证。** `/root/wksim-joint-control-c2IXOr/build.json`，SHA `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e`。已实际构建并 seal；私有 ap_mixed_candidate pin 已更新，主仓库最终飞行 pin 不变。BeqOco 含已证实的阻塞接收缺陷，不再用于新飞行。
3. **安装态 helper 03 已通过，但不是 FC 证明。** `validation/planner-release-helper-20260912-03/`：真实安装 Node/ROS/TCP，明确合成的状态与 ACK；唯一 SetupRequest=30，command 高水位=17，无 trajectory 输出；源码运行前封存、运行后 SHA 一致；Node 继承 task PGID，helper 只按 pid/start_ticks 核验并发送信号，正常退出0、日志为空，独立 /proc 证明该身份已退出。01 先关 socket 产生 EOF；02 改清理顺序后暴露阻塞并需 KILL；原件全部保留。
4. **下一步重新准入 c2IXOr，收取 Claude 18-AH 后进入真实 release。** 私有 `validation/planner-release-preflight-20260912/admission-03.json` 已对旧 BeqOco 返回 ok=true，children_created=0；正确顺序是原 run-joint-flight.sh 的 MUlZd0/FVMjak 历史 overlay，之后才激活 Rzj3Pf/新 Control。不能将旧 admission-03 当新候选准入；对 c2IXOr 写 admission-04。252 个历史 baseline 文件按原 SHA 复制的记录在 baseline-copy.json，不能发布原始厂商资产。

私有实验已有 PVTask prepare/begin_leg 提取、新 PlannerReleaseTask、显式 `--planner-release-proof` 和 10 项流程/入口检查；AP 在原 P+V 第一段确实移动时静默 writer，经真实公共 cancel→BRAKE 双阶段确认，再保留 2 秒准备、4 秒 <=.25m/s/<=1m 停止窗口及 AUTO.LAND。主会话已补整数 ROS ns 和 phase 状态快照。该场次只能是 diagnostic observed，不能算 #83 nominal PV 或 Full；实际 1ms truth 必须独立审计。

OMP 22l 主验仍发现请求从29正常领养30被误拒绝，以及独立子进程组可逃离父任务清理，已实际 cancel，read 确认 interrupted/turnId=null。主会话接管 helper 与测试，修正上述问题、同一 TCP 连接、安装环境、ROS deadline、失败记录、Linux start_ticks 索引19和 TERM/KILL 身份核验，29 项 helper/流程/准入纯检查通过。当前唯一写入者为主会话，不重新启动 OMP 覆盖这些文件。

Claude 18-AH（thread `4d5268f4-1d78-48ba-a5d6-aa800447cb1c`，turn `ab744e9d-f54a-4a03-b709-a289c20c7955`）最后实时状态 running，负责只读检查 task/runner，下一轮读状态与最终报告；不得因观察超时重启。agy turn `ddd29a53-9932-45e2-b956-566d6a1a4319` 返回 failed 但附带证据映射文字，仅作定位提示，不当主验；其 record_phase 等建议需核对真实API（实际是 task.phase），不能直接照抄。

本轮所有主会话 native/fixture/build handles 都已终态。下次任何 native 启动前重新分别完成并评估两 distro 进程检查。无需重做本轮安装夹具；先处理准入、独立审查和真实场次。

## 已完成，勿重复

- M1 kernel-bpf-03 地面诊断：10.000188298 秒、321461 事件，九任务/五 owner 身份、零 loss、解绑清理通过；无 fault，最差迟到 77.256332ms。仅诊断，不是 PV/长期倍率/Full。tick5504 直接测量 wait_px4=5419791ns、wait_ap=127634ns，不跨 run 编造因果。证据 `validation/scheduler-kernel-bpf-20260912-03/`。
- EGO 完整构建、真实 11000 点云及地图占用完成。静态夹具02真实输出 33 控制点/37 knots，采样折线净空 0.9971919183081722m；非连续曲线/飞行证明。只修正 fractional duration 的结束 tick，不改 start 时间门槛。证据 `validation/ego-planner-static-20260912-02/`。
- 完整 ros1_bridge 构建、字段映射、反向消息和暂停 clock 通过；netns FD 交接及跨 distro 五消息传输通过。私有 netns UDP loopback 例外不能套用到全局。证据 `validation/ros1-bridge-runtime-20260912/`、`validation/netns-handoff-20260912-03/`、`validation/cross-distro-ros-20260912-04/`。
- sender/node v2 接线、release 基础、真实 ROS1 订阅→TCP、真实 ROS2 clock→安装态 SetupRequest 装配已通过。`_planner_subscriptions` 修复避免覆盖 rclpy 内部字段。安装 smoke 只 capture Setup，release_confirmed=false，未证明 FC 停止。证据 `validation/ros1-sender-live-20260912-02/`、`validation/control-install-v2-20260912/`。
- #83 实跑 `joint-public-flight-nqyqcagl` FAILED：tick53128 迟到104260439ns，超过原100ms，两机起飞但任务未完成；源码不变、十个自有 PGID 清理通过。#83 仍 OPEN，禁止盲跑或标成通过。证据 `validation/33-final-combo-luna/20260912-nqyqcagl/`。wire 间隔含多段处理，不能直接当 AP 接收等待。

## 协作与执行边界

OMP：`6deb2e40-2240-4db2-8c7f-c06bf6724048`，22l 已中断，主会话接管；Claude：`4d5268f4-1d78-48ba-a5d6-aa800447cb1c`，18-AG 方案已完成，endpoint-held 是静止，不能充当移动中 release；agy：`d0a07619-281c-408c-813a-d0784cee52a3`，kernel-offcpu-analysis 草稿未核验，不接受宽泛因果结论。三 Luna 旧切片已交付，不能当作仍运行。续派前查实时状态、唯一写入者和当前模型约束；无法选择/验证 Fast 时如实报告，不虚报设置。外部派发遵循 codexhost delegate --help；JSON 最后一项 progress/result 优先，THREAD_BUSY 代表未送达。

主会话独占真实 SITL/ROS/UE/MATLAB/tracefs/BPF/原生构建线。本次 Goal 修复没有启动 native。新 native 前必须分别完成并评估 Ubuntu-22.04 与 RflySim-20.04 两端进程检查，再单独启动；不能把检查与启动连成未经评估的一次调用。所有历史 handle 已终态，不等待旧 handle。保持 1ms、native 输入/时钟屏障、无追赶、100ms 累计迟到及原身份/新鲜度/物理门槛。新场次用新目录，保留失败证据；不发布厂商源码/二进制、不终止用户进程。

晚到轨迹起点语义问题尚未获得用户回答；不修改 start_in_past/等值门槛，不把等待当批准，继续独立工作。G6 预算、未知 ABI、硬件或批准只阻塞相关分支。全部必需票据及 Full/G0-G6 真实完成才完成 Goal。

主工作区存在他方 controller/PID/runtime/UE/rover/runner 等改动，执行前读实时 git status，不覆盖或暂存。原保护清单包括 docs/Prometheus.gitmodules.reference、validation/coordination/short-cycle-dispatches.json、docs/coordination/agy-aruco-native-correlation.md、docs/coordination/claude-native-wait-next-probe.md、tools/inspect_aruco_native_targets.py、validation/test_aruco_native_targets.py、docs/coordination/acceptance-frontier.json。Git 推送可使用进程级 `git -c http.proxy= push origin HEAD`；不关闭 TLS、不改全局代理。
