# 当前 Goal 执行检查点

更新：2026-09-12。实时 Goal、Git、代理状态及原始证据优先。刷新前检查点逐字节保存在 [本次归档](short-cycle-goal-history-20260912-175837.md)，更早记录见 [历史归档](short-cycle-goal-history-20260912.md)。只在查证具体历史时读取归档；原验收范围见 [执行计划](next-acceptance-goal.md)。

## Goal 健康状态

- thread：`01a08b94-d2fe-7361-9c43-2d54e9490f32`；goal：`63bdd724-67ae-4701-8fae-73e2a03578f5`。
- 本次 get_goal 和只读数据库一致：active，token_budget=null，continuation deferral 为零；桌面实际 CLI 的 goals=true；任务未归档，接口返回 inProgress、error=null。
- 运行记录显示 07:53:23 UTC 和 08:32:10 UTC 两次回合结束后立即开始下一轮。续跑机制已有实际执行记录；清理后的下一回合已收到正式 Goal continuation，自动续跑验证完成。
- 不重复创建、不虚假结案、不改数据库。现有 Goal 工具没有 objective 编辑或 resume 参数；最新阶段和完成项以本检查点为准。累计 tokensUsed 是消耗统计，不能当作预算上限。
- heartbeat `wksim` 绑定同一任务，ACTIVE，每三分钟检查。无变化或不可行动时静默，只在重要变化、完成、失败或需用户行动时通知。心跳只辅助跟进，不能代替 Goal 完成验收。

## 当前关键路径

主仓库最新已推送运行时修复为1521343；后续提交以实时Git为准。Ubuntu-22.04 `/root/wksim-release-acceptance-fe3` 的私有分支 `codex/planner-release-validation` 已提交实验准备 c97e92b、执行模块证据 e5a124e、失败记录 float32 修复8699169。主仓库他方 runner/runtime/控制器修改不覆盖，不整文件替换。

1. **真实移动中 release 首场 FAILED，禁止盲重跑。** 私有原始目录 `validation/joint-public-flight-8fmacpgy`，live `/root/wksim-joint-flight-zzt0406g`，epoch `676a53981dd747cb93bfd5271d7f5d95`，执行源码 e5a124e。tick67996 累计迟到134828282ns触发原100ms RateUnmet；此前两机已起飞并进入P+V。AP writer静默tick67940，公共速度0.26640569398276115m/s、同tick物理真值0.3055788437713588m/s。没有 release ACK，没有停止/LAND 验收，不能算 #83 nominal PV 或 Full。
2. **时序与清理已核验，因果仍有限。** 最后67992→67996组耗71993754ns；planner启动前最近组已有66800709ns累计迟到。子进程启动wall351.29149844，RateUnmet记录351.423954943，cancel在351.529023245，晚于rate fault105068302ns，events为空。启动重叠不证明唯一CPU/IO/FC原因。源码与完整Control候选均不变，原10个PGID的独立/proc检查为空；planner pid2501继承AP task pgid1927、退出0，无用户进程被终止。完整原件保留私有目录；主仓库选定原件及rate.gz/SHA清单在 `validation/planner-release-native-20260912-01/`。
3. **失败记录缺口已修复，原记录不重写。** AP result.json因release_stop中的numpy.float32无法JSON序列化而未写出；原始task log、progress、helper记录均保留。8699169仅把anchor和pre_release_velocity转Python float，真实numpy回归与6项流程/证据检查通过；不是改变坐标或阈值。
4. **下一步评审并实现启动预热，避免在计时飞行中临时加载整套ROS/Python模块。** 候选方案：同一密封planner子进程在 initialized.json/physics tick0屏障前完成模块加载，等待自有stdin激活令牌；writer静默且当前双高水位核对后，才实例化真正PlannerTransportNode并接收cancel。不能提前绑定epoch追随PV writer，不能提前分配请求，不改.5倍率/100ms/1ms/无追赶或停止锚点。Claude18-AI（thread `4d5268f4-1d78-48ba-a5d6-aa800447cb1c`，turn `4edadb23-c0ac-4634-9cf7-76c00f454998`）已派发只读边界复核，最后实时状态running；主会话拥有实现。先读其状态，不因观察超时重启。不直接复跑8fmacpgy原条件。

Control仍为 `/root/wksim-joint-control-c2IXOr/build.json`，SHA `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e`。admission-04已对该候选实际准入ok=true，零子进程；原overlay顺序MUlZd0/FVMjak，之后激活Rzj3Pf/新Control，不削弱checks。BeqOco有已证实的阻塞接收缺陷，不用于新飞行。新候选本轮实跑前后完整check_control一致，无须因实验工具修改而重建同样Control。

Claude18-AH已完成：采纳安装态模块证据缺口，e5a124e记录子进程实际加载15个Simulator模块并逐项对候选路径/哈希核验，赛后完整check_control；闭包源码和消息资产进入原source_unchanged。其子进程独立组担忧已由前轮继承task组/正常退出修复；其“速度必定>.25”数学推论不成立，以实测为准；其把anchor后移会放宽原停止距离，未采纳。安装态新增证据联调04验证15模块、退出0、源码不变，仍是合成ACK，不是FC证明。

已完成且不重复：非阻塞接收修复1521343（accepted socket显式nonblocking，BlockingIOError空批次，EOF/身份拒绝保留），56纯检查、27实际ROS检查；安装态03与04通过。证据 `validation/control-nonblocking-20260912/`、`validation/planner-release-helper-20260912-03/`；01/02旧失败原件保留。OMP22l已实际中断并确认interrupted，helper由主会话接管，不重启覆盖。agy旧映射结果状态failed，仅作定位提示，不当验收。

本轮真实场次handle38241已退出1；准入handle67838退出0；所有主会话native/fixture/build handles均终态。下次任何native启动前必须重新分别完成并评估两个distro进程检查，再单独启动。所有数值、身份、新鲜度、停止、时间门槛和历史失败均保留。

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
