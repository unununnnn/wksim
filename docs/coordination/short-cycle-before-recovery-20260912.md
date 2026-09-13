# 当前 Goal 执行检查点

更新：2026-09-12。实时 Goal、Git、代理状态及原始证据优先。刷新前检查点逐字节保存在 [本次归档](short-cycle-goal-history-20260912-175837.md)，更早记录见 [历史归档](short-cycle-goal-history-20260912.md)。只在查证具体历史时读取归档；原验收范围见 [执行计划](next-acceptance-goal.md)。

## Goal 健康状态

用户再次要求重规划，get_goal返回null后通过正式create_goal新建滚动Goal，createdAt1789213021，active，无预算。用户随后明确选择 **4 DeepSeek + Claude Code + Oh My Pi**，本轮不再占用三个无法核验Fast的Luna席位。最新唯一执行计划为 [六代理滚动计划](rolling-six-plan-20260912.md)，权责/句柄见validation/coordination/rolling-six-20260912/queue.json；此前“三Luna由主会话代行”已被该选择取代，历史计划不得覆盖当前阵容。

## 当前关键路径

**最新协调状态：**六外部任务已派，A/C/D首批交付后已立即续派下一项，主会话并行验收冻结副本。DeepSeek主实现，Claude独立复核，OMP小修补。原发布完整性误判的审计修订已通过真实正例并拒绝掉命令重编号负例；完整矩阵第一轮唯一问题是probe自身没删到发布记录，A1已修正并冻结（probe SHA92a83f4e…，tests07997136…），主会话只读真实probe-run-02仍在运行，handle35974；不得重复启动该handle的工作。A3正在主工作区继续补“选中场景pass不等于完整矩阵pass”标志，不覆盖其进行中的两文件。所有更旧代理状态和“待DeepSeek02纠正”文字仅为历史背景。


**新阶段优先项：**先修复18-AJ完整性误判并验证删除命令/重排编号负例；再按Claude19a核对#82/#83完整PV合同；DeepSeek02纠正其01的写者/时钟域误读。当前新计划优先于下方上一阶段记录。主会话已完成25文件完整性校验、实际负例复现和7票依赖核对；OMP独占Linux审计脚本/原测试文件，主会话勿覆盖其进行中的修改。


主仓库6d139b7已推送，包含真实release成功证据、独立审计工具与#39运行合同补充。实验分支 `codex/planner-release-validation` 已推送至90bb3e1；实际运行代码bc76fb6。Ubuntu-22.04工作区 `/root/wksim-release-acceptance-fe3` 保留所有实验代码及全量原件。主仓库他方runner/runtime/控制器修改未覆盖，实验分支尚未整体合并。

1. **真实移动公共 release 与双机 LAND 已实跑并通过当前原始审计，不重复该场次。** run `joint-public-flight-bomvjsmg`，scene epoch `fffc7da8ba73461fa26b1949a31b0007`，原件 `/root/wksim-release-acceptance-fe3/validation/joint-public-flight-bomvjsmg`，live `/root/wksim-joint-flight-4_nzkfc8`。结果 observed（明确不是nominalPV/Full），两任务与Control正常完成。AP在物理tick0预加载同一planner子进程，writer静默后激活，真实绑定run/epoch/request65/command62核对后发cancel；请求66的native_ack→setup_completed(BRAKE)成立，随后AP AUTO.LAND67、PX4 LAND126均有真实native ACK和模式确认。
2. **1ms与独立DDS审计03通过。** 两栈各92596个连续1ms真值；AP交接真值速度0.3064071141526029m/s。停止窗各4001个含端点样本：AP最大速度0.04970044238295725m/s、距释放前锚点最远0.4820302973402434m；PX4最大速度0.03930866587856656m/s、漂移0.09233400879439557m。独立CDR读取52713条DDS记录，命令/请求ID严格递增，最后SessionState真实解除武装、有效且在地面。23140个原.5rate组无追赶，最差迟到75321700ns。主仓库证据 `validation/39-planner-flight/release-bomvjsmg/`；全量真值仍在私有目录，Git中的stop-truth.gz只是明确4001行片段，不能冒充全量。审计工具SHA `c4a003c89396e733a068db81cf5b017ef02b3ecfdb4a546280623ff242c03471`，审计03和源码快照均保留。
3. **当前只剩该审计的独立代码复核，随后转下一验收切片。** Claude18-AJ，thread `4d5268f4-1d78-48ba-a5d6-aa800447cb1c`，turn `8bcc303b-8250-4b94-a551-423c72984c58`，最后实时状态running；范围是审计潜在误判，不运行native或全量raw扫描。其派发之后主会话已补原始LAND确认、最终SessionState、ID严格递增与物理窗口完整范围检查；回收报告时核对当前90bb3e1，不能照旧版本建议重复改动。仅有审计代码修正时复核原件，不重复飞行。
4. **后续优先核对#82→#83原合同与冻结候选。** #83刚读取仍OPEN，要求完整最终组合PV、原.5x/100ms/10s/60s合同与原audit_pv_trajectory，全两段；本次AP提前release/PX4仅一段不能关闭#83。先读取#82及 docs/2026-09-09-final-combo-pv-plan.md、mixed-production-seam、rate-release-check，核对新Control是否需要重新冻结合同，再决定一次完整PV验证。新common-prefix已真实运行至92596tick且通过，不能把旧53k失败直接当仍在运行，也不能无依据盲重跑旧条件。

#39/#102仍OPEN：本场没有真实EGO Bspline驱动的完整绕障、到达、净空/无接触、no-route或重规划。原晚到起点语义问题仍未得到用户回答，不能放宽start_in_past或等值闸门；继续独立票据工作。不要把公共释放完成当作map→planner→public control→flight全部完成。

Control仍为 `/root/wksim-joint-control-c2IXOr/build.json`，SHA `6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e`，两场前后完整check_control均一致，15个实际执行模块匹配封存；admission-04已准入。纯实验工具改动无需重建同样Control。环境顺序保留MUlZd0/FVMjak历史overlay，之后激活Rzj3Pf/候选，不削弱checks。BeqOco有阻塞recv缺陷，不用于新场次。

原8fmacpgy失败保留：epoch676a53981dd747cb93bfd5271d7f5d95，tick67996迟到134828282ns，最后组71993754ns；cancel晚于rate fault105068302ns，零ACK。启动重叠不证明唯一CPU/IO/FC原因。AP result.json曾因numpy.float32未落盘，8699169修复为Python float并通过真实numpy回归，不重写原件。证据 `validation/planner-release-native-20260912-01/`。

预热实现bc76fb6：原AP task在initialized.json前持有子进程和stdin；import+rclpy.init预加载后记录warm-ready0，激活前不创建Node/绑定会话。保留原5s传输、10s ROS截止、所有计数/身份检查；原task组清理，helper只核验并信号自有PID。34项检查与安装态合成输入预热05通过。Claude18-AI误称“时钟前只有runner存在”，已用实际launch_task→initialized gate源码纠正；不引入多余runner文件握手。OMP22l仍中断，主会话拥有helper，不重启覆盖。Luna接口Fast仍不可选择/验证，且用户新近明确保留该要求，由主会话暂时代行，不伪报设置。

本轮handle70504真实场次退出0，98999只读审计退出0；所有主会话native/fixture/build handles均终态。成功场次原10个PGID的独立/proc复查为空，warm child继承taskPGID并正常退出0。下次native前重新分别完成并评估两distro进程检查，再单独启动。全范围Goal尚未完成，新Goal为active；不关闭任何尚缺原AC的父/子票。

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
