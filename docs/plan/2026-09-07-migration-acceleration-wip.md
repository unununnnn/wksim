# 2026-09-07 加速实施检查点

当前 Goal active；完整 G0–G6 / 冻结 Full 终态不变。主任务 `01a077e8-dfc4-7981-91cf-5d8e43418395` 接续已 idle/interrupted 的 `01a07641-2eac-79d1-8e98-27ff1ff9ad23`，承接 `6d2e371`，代码已整合到本地 `codex/independent-rgb-integration` 分支；当前提交以 `git rev-parse HEAD` 为准。历史未提交状态不覆盖本节。

## 最新执行点（覆盖后文历史状态）

2026-09-08 G6来源链与执行方案轮（全部主代理完成）：e1 版本一致链（SLX↔ZIP 1.1183，R2024b）确立但动力学异于 e0；e0 SLX 11.8 为 R2022b 保存、本机可仿真；11.0↔11.8 漂移刻画完成——大气（ISA 常量预计算一致到 15 位）/重力（9.81）语义相同，噪声功率/种子（SLX 11.8 显式 [23093–23098]+noisePowerIMU vs ZIP 无此字面量）为唯一真实开放项，结构等价留待确定性对照行为判定；本机 Simulink Coder 无许可（checkout -5,357）不可再生成、Embedded Coder 可用（`a12d1a3`）。#42 受控构建方案全要素核实（Qt6.8.3/VS2022/cmake4.3.1、QGC_NO_SERIAL_LINK 编译去串口、私有 ini 播种与无 GUI 读回验证，`0d43ddf`）；#31 深度实施方案镜像 RGB（R32F SceneDepth→float32 平面 Z 米制+NaN、内参反投影→ENU 点云，`2aaea6d`）。Goal active；五项决策包待用户，批准后即执行 C1/#31/#42。

2026-09-07 #42核查与决策包轮（全部主代理完成）：#42 厂商证据核查（HowToUse.pdf 全文/官网检索/exe 字符串+GitHub API 实查）维持「无受控启动机制」结论；新事实为本机 `../qgroundcontrol/` 完整现代源码检出（CLI 无 --settings-file），唯一可核验路径 QGC_CUSTOM_DIR 定制构建（独立身份/关闭自动连接/回环链路），构建授权与界面动作分工已提交用户（`63b4cd2`）。#6 首期批次与验收矩阵提案（已验证项基线+C1→C2→C3 控制链批次）与 #31 深度点云约定提案已发布（`ff2cc22`）。CBM 原生刷新 50,515/163,780 ready。Goal active；#20/#21/#42/1×/G2/Full 不关闭，等待用户批答后可执行前沿为 C1 控制链与 #31 实施。

2026-09-07 #22关闭与#21证据轮（全部主代理完成）：#22 按「主代理复核后关闭」流程关闭并读回（CLOSED/COMPLETED 2026-09-07T12:10:29Z，票文件/status.json 已更新，`bb6e200`）。#21 三场真实联合 UE 回归通过：run8 基础双机显示/相机选择 2→1/4s 暂停/4tick 单步/继续/降落（Actor 回读↔权威真值逐机一致，94156 tick）；run9 UE 整进程空中重开、物理独立推进 1768 tick；run10 冷重置 gen 1→2 代次隔离（新增 `--reset-scene` 验证驱动选项，`7333aba`）。视觉15+控制台96通过，WSL/Windows 无残留。**#21 验收3前半句与单一权威屏障架构冲突（产品路径不产生一机断流一机新鲜场景）已作为 HITL 提交用户**，见 [#21证据报告](../2026-09-07-joint-ue-visual-evidence-report.md) 与 issue 评论；#21/#20/G2/Full 不关闭，1× 维持未决。

2026-09-07 归因纠正与修订后双侧通过轮（全部主代理完成）：本会话查明 `c162fa7` 报告中三次「recover 窗口末端停顿」失败（w1wi0gpj/dtcollzf/523cme9k）实为**本会话一项未提交工程实验**（recover 窗内同步预生成恢复任务进程组，390–613ms 等待被 recover_confirmed 边界检查如实计入）所致，三样本均带 `recovery_task_transport_initialized` 标记紧邻违例；已回滚（`4cc93ca`），修订合同与数值不变，「recover 窗口风暴」未决问题随之撤回。回滚后修订合同下双侧失联恢复真实通过：AP `_yrr1_v8`（recover 窗 0.77ms、锚点段 94.87ms<100ms）、PX4 `ffi_57_3`（窗 0.04ms、段 61.60ms<100ms、第三次尝试；前两次保持驻留门槛 failsafe 瞬态边际失败，无 rate_unmet，样本保留）；两侧原始审计各两次字节一致+三篡改负例通过。`y_3hsz3y` 为回滚后 recover 窗健康（2.30ms）但锚点段宿主持续漂移 100.13ms 如实冻结的第二样本。矩阵 404(38跳过)/旧预检11/候选79（新构建 veonAO）/Windows 96+4 全绿；WSL VM 曾在矩阵完成后重启（uptime 佐证），未完成句柄无残留。详见[本轮纠正报告](../2026-09-07-recovery-staging-revert-correction-report.md)。1×（47.1s/60s）维持原未决。Goal active，#20/#22/G2/Full 不关闭。

2026-09-07 恢复/修订/1×重测轮（全部主代理完成）：用户「全按照推荐进行」已执行。AP/PX4 失联恢复回归修订前合同下双通过（etsaqmso/nasz1u3f，审计各两次字节一致+负例）。start-recovery-task 重锚修订已实现+单测 11/11+[合同附录](../2026-09-07-rate-contract-amendment-start-recovery-task.md)；修订后 4 次真实尝试全部如实失败于锚点之前（q2qexeye EKF origin 复位；w1wi0gpj/dtcollzf/523cme9k recover 窗口末端 >100ms 单次停顿），当晚宿主显著更噪（seg1 worst 75–95ms vs 早晨 46–82ms）。1× 重测三 epoch（vmmemWSL=High 核验 priority=13，VM 重启需重设）：47.1/41.1/23.7s 仍未达 60s×3（较 31.3s 提升 50%）。矩阵 404(38跳过)/11/79/96+4 全绿，残留干净。**recover 窗口风暴新合同问题与 1× 后续选项已提交用户**，见[本轮报告](../2026-09-07-recovery-amendment-1x-retest-report.md)。Goal active，#20/#22/G2/Full 不关闭。

2026-09-07 收口轮（全部主代理完成，本会话无 gpt-6-astra 可核验配置）：临时 timing_probe 已按基准精确清理；新增自有进程 nice/FIFO 调度、AP 包单次序列化、健康轮询 1ms 限频（检测仍 ≤1ms）。四矩阵 403(38跳过)/11/79/96+4 全绿。RGB 生产者停启/重连/冷重置旧 epoch 隔离与空中公共任务实时 RGB 均真实通过并审计（`joint-rgb-lifecycle-20260907-run2`、`joint-rgb-airborne-20260907-run2`）。0.5× 生命周期回归以 cohort 同字节 wrapper 通过（`joint-rate-flow-ox8h58cv`）。**持续 1× 最佳 31.3s/需 60s 仍失败**，迟到实测为宿主机层停顿（FIFO 无可测改善）；**AP 失联恢复在 0.5× 监督下因 start-recovery-task 的 DDS 发现风暴（FC 锁步停顿 69.57/15.31/6.85ms）如实 rate_unmet 失败**。两项未决问题已提交用户，见 [本轮报告](../2026-09-07-rate-recovery-rgb-closure-report.md)。失败样本全部保留，Goal active，#19/#20/#21/#22/G2/Full 不关闭。

本轮最新：RGB四个几何/遮挡场景共60帧通过，增加v2生产实例身份并修复真实重连晚到旧帧；持续1×仍失败。当前未提交改动及资源/测试边界见 [最新检查点](../2026-09-07-rgb-geometry-rate-wip.md)。所有本轮真实实验已结束，Goal active。

本节最新：新独立默认 PX4/AP 三航点、准入来源绑定和真实 MATLAB 双栈联测通过；AP 同时通过新 UE 单载具实时显示。RGB ground run2 产生 35 张原生 PNG、消费解码 15 张，关闭消费者 3.0404s 后物理推进 1556 步，真值/权威时钟/位姿原始审计及三个篡改反例通过。默认配置和 UE build manifest 已提升，旧配置/构建清单保留。详见 [本轮整合报告](../2026-09-07-independent-rgb-report.md)。

本轮所有真实 FC/UE/MATLAB 运行均已结束，所有 exec 句柄已 wait 完成；没有活动实验。最后正确配置的矩阵：默认399（36跳过）、旧预检11、候选79、Windows产品104通过。最初未设置环境的 discover 失败保留。22 个代理均已结束且实际 gpt-6-astra/low 核验入档。Goal active，#30 几何/空中/旧代次真实验收及 Full 不关闭；联合时序探针和持续倍率问题仍待后续处理。

以下为此前原样保留的历史执行记录，不覆盖本节最新状态：

**最近状态：所有真实FC/UE运行均已结束，当前没有活动实验。** 最后 session12366 的 `joint-visual-20260907-run7-timing` 在地面33788tick资源冻结后正常退场；对应所有工具句柄已wait结束。18个代理实际gpt-6-astra/low核验已全部存入agents.json，当前均已结束。代码仍未新增提交/推送，Goal active。

最新诊断结果 `probe-analysis.json`：累计99.773533ms的起点滑移中，前一组超过周期60.373781ms、组间调用4.909002ms、首次health1.822535ms、等待阶段32.668215ms。组内最长延迟分布在模型响应/下一AP传感器前，以及AP输入等待；`wire-gap-analysis.json`记录13493前10.95ms、13495前15.69ms、1926 AP输入10.18ms等实际窗口，不等于已证明OS或磁盘原因。应继续对RPC/输入/健康计算或阻塞做有界定位，不再无依据整轮重试。

run5历史零发送不能归因15FPS：捕获该病例第4步真实状态送本地datagram成功，预绑定socket跨overlay成功，真正host receiver/private-net+mount sender也成功。Writer已新增last_error；run6实际sent1415/dropped0/last_error=null，显示传输可通但0.5倍率仍地面39324tick失败。之前7轮中没有完整联合UE验收成功，不能关闭#21。固定0.5与1×三epoch/长窗验收仍待当前代码重做，不借旧串行cohort代替。

临时timing_probe仍在joint_rate.py，原文件 `before_timing_probe.py` 可作精确清理基准；纯pacer基线和ROS executor替换微基准均未支持直接优化，尚未改节拍算法。需要在最终回归前处理探针、跑新全矩阵。两份准备后的三航点独立配置尚未执行，工作台/MATLAB默认仍旧候选；下轮可先完成这个独立可执行前沿，避免全被联合性能一项拖住。

后续（2026-09-07，当前主线）：用户已明确批准 #9 环境与视觉合同，批准记录 `docs/2026-09-07_environment-contract-accepted.md`，GitHub #9 评论 `5563452378` 已逐字读回；DLL/数值/硬件部分保持各自门槛。两套新独立 profile 的基础六输入实飞均通过（`independent-flight-{px4,ap}-20260907-run1`），已创建三航点候选配置 `validation/independent-mission-20260907/`，尚未跑这两套完整 MissionTask/未提升工作台默认。

联合 UE 源协议 v3 和 C++ 候选已实现（当前 manifest `ue55-build-e4167b0ee15a41ddb827b799dbeb6fdb/candidate-manifest.json` / stage `wksim-native-joint21-20260907-d`）。增加相机专用 SDK 选择入口，实际两次选择与回读在 run2/run4 有记录；原生 keyboard Computer Use 通过 `@oai/sky` 初始化后 list_apps/list_windows 均报 `codex app-server exited before returning response 1`，重置后仍失败，未用其他 Windows UI 自动化绕过。键盘验收保留。

`joint-visual-20260907-run1` 遇到真实 Windows 读句柄导致 view.json 替换失败：View._persist 现对短暂 PermissionError 有0.25s有界重试，真实不共享 DELETE 的读取锁测试通过。其 UNC 复制 PX4 runtime links 失败，保留原部分副本，并通过 WSL 原生复制另留 `run-wsl-copy` / `retention-recovery.json`。后续驱动改为 WSL 原生复制。

run2 实际双机显示、相机SDK选择、4秒暂停/4tick均通过；退出UE后物理仍推进1768tick，但重开UE时tick55980触发100ms资源冻结，整轮失败。run3在首次UE启动时地面tick2252冻结。为使操作者先完成显示初始化，新增正式 `--prepare-run` 和 `--use-prepared-run PATH`：准备只生成随机instance、固定配置及空目录，显式执行一次性消费；不查询UE、不改变物理调度。七项文件契约以及Linux所有权/链接/重放测试通过。普通入口默认语义保持。

run4通过准备→先打开UE→执行真实仿真，完成双机实际画面/选择/暂停/四步/继续，接近最终降落tick92192仍累计迟到101.097733ms冻结，整轮未通过。快照可见双P450真实Actor与同一84836步；未改位置作展示偏移。run5改联合显示15FPS，但发送器sent0/dropped1922，不能当有效负载比较；run6相同档位sent1415/dropped0，地面tick39324仍资源冻结。所有失败保留且实际核心组已正常退场。#21/#20继续开放，不用局部通过关闭。

时序离线工具 `tools/replay_joint_rate_timing.py` 已在约1秒内精确重现run4/case2的原始失败和已知成功，见 `validation/rate-timing-diagnosis-20260907/{replay.json,report.md}`。run4最后组起点已迟到99.448039ms，9.649694ms组后过线；前组超过8ms和组间延迟都有贡献，不能归因OS或I/O。纯pacer实际空循环1000组平均释放滑移仅0.68–1.34µs；复用ROS executor的空订阅微基准反而更慢，两个方向均未据此修改运行算法。

当前 **临时诊断修改**：joint_rate.py 的 rate_group_start 增加 `timing_probe`（入口、首次health结束、等待期间health与sleep耗时）；未改预算/节拍算法。原文件存于 `validation/rate-timing-diagnosis-20260907/before_timing_probe.py`。活跃测试 **Windows exec session 12366**，`joint-visual-20260907-run7-timing`；先查这个运行并分析，不并行启动其他FC/UE/MATLAB。诊断结束须清理临时计时探针或明确保留为产品证据接口，不能把带探针的失败当最终验收。

补修两个审查问题：可选 JointStateWriter socket创建OSError禁用显示且记录setup_error，不使物理退出；旧/迟到ACK不回退product_bridge/console的观察代次和序号。增加真实datagram背压、旧代次缓存与可选setup失败测试。Writer还保留last_error，区分验证/发送失败。捕获case5模型第4步送真实本地socket、以及host receiver/private网络+挂载sender两种快速探针通过；case5历史全丢的确切原因仍未知，不伪称已定位。

MATLAB旧病例因当前源码演进，现在通过显式 `--source-archive validation/matlab-retained-sources-20260907` 审计：26个唯一源文件覆盖每例24必需哈希，恢复原字节而未执行；两例和篡改测试通过，`current_checkout_accepted=false`。默认当前源码校验仍拒绝老源码不匹配。原始MATLAB证据未改。

2026-09-07：#5/#8 依据原有明确批准关闭决策；#41 可选 MATLAB 桥、#19 首期唯一权威时间公共任务闭环经主代理复核关闭。原 Wayfinder #1、#6/#9、#20/#21/#22 与 Full 仍开放。最新共同时间原始审计为 `rate-lifecycle-boundary-audit.json`：`joint-rate-flow-bqozl_ek` 82216tick、27.002s同飞、暂停4.112343931s及56156→56160四步；精确重锚边界采样也通过。`ngzzz774` 虽行为通过，但尚缺边界采样日志，原始倍率审计拒绝，未改判。

当前推进两条切片：独立正式入口 `runtime_profile=independent_quad_dds_v1` 重用已核验的无Gazebo PX4 ONa1Kw / AP OXQqdR 与 Control8xt3WC，保留旧基线。两栈正式预检通过；PX4 独立实飞 `independent-flight-px4-20260907-run1` 通过，实际五类进程映射/四组清理有记录，AP `independent-flight-ap-20260907-run1` 正在验证，默认工作台尚未提升。共享 `joint_profile.check_resources` 按所选固件验证，原双机默认契约保留；主线负责config/preflight/runtime接入。

#21 UE 双机 C++ 接收/HUD/观察目标切换已有新候选编译通过，资产未修改。第一编译Owner遮蔽错误保留；最终显示时钟兼容版为 `ue55-build-59420eb971bb47eaade5da8c0876d57c/candidate-manifest.json`，stage `E:/ue5.5/build/wksim-native-joint21-20260907-c`，尚未真实UE联测/全局提升。新 `joint_state_stream.py` 与 product_bridge/state_relay 复用通道：WSL19字段→Windows追加3个已有保守显示年龄字段→UE22字段，物理时钟原样保留。manager instance/generation 与可选display_socket正在接入；协议/背压等33项局部检查通过，首轮测试默认发送缓冲未填满，调整为测试专用4KiB发送缓冲后实际EAGAIN通过，原失败保留。

`remaining-gates-proposal.md` 的 #9 环境合同已向用户异步询问，尚未取得答复，不执行依赖它的环境工作。来源核对 `model-reference-provenance.md` 确认ZIP 11.0与相邻SLX11.8不一致，22项参数匹配不足以成立独立数值参考；未编造G6预算。所有新代理实际配置核验已扩至14条，无嵌套；两个最近代理已完成，主线掌握所有文件。未新增提交或推送。

## 已核对的批准与执行前沿

- G0：#10 / #11–#48 已发布；38 票的 87 条原生阻塞边实读与 `published-issues.json` 一致。48 项故事及 Full 扩展仍有归属。#11–#17 已关闭，#18–#48 开放。
- #5 首期 MATLAB 范围、#8 联合调度/墙钟监督/倍率均已有批准，不重问、不重复建票。#6 数值/最终矩阵、#9 插件/环境合同及硬件条件保留真实门槛。
- Ubuntu-22.04 迁移已完成；旧主任务最后两模型 RPC 故障与四份原始审计实际上已通过，但旧 WIP 顶部未及时更新。历史原生进程/boot 证据不直接查询当前复用 PID。

## 本轮写入与验证

主线负责 `joint_runtime.py` 及真实资源串行验证。`recover_physics` / exercise resume 的 5s 截止由独占代理修复；最高公开工作台接缝的 MATLAB 桥由另一代理在新目录实施；死亡故障原始审计另有独占工具/测试文件代理。无嵌套。四代理实际 `turn_context` 均为 `gpt-6-astra / low`，见 `validation/migration-resume-20260907/agents.json`。

完成的改动：恢复/继续收齐 ACK 后仍检查原绝对截止；模型/FC 已退出时保存明确的 unavailable maps 记录并允许冷重置退场；退场异常请求有 failed 终态，不能伪报 completed。SIGTERM 后使用本机 Humble 实际提供的 `rclpy.try_shutdown`，避免重复关闭覆盖原错误。19 项 Windows 边界/保留证据检查通过；不是完整候选矩阵或飞行验收。

真实新样本：

- `validation/joint-input-stall-2bglzwj8`：失败并保留。验证驱动将完整 authority（包括变化的 fault 诊断文本）等同于物理时间；实际模型死亡触发两条故障原因。驱动改为精确核对 tick/time/输入屏障/pending/recoverable，不放宽任何数值阈值。
- `validation/joint-input-stall-5o_zb26v`：PX4 模型进程 SIGKILL 后驱动通过，冻结已提交 tick 52056，pending 52057 不提交；显式冷重置、新地面 epoch、stop、manager/epoch 无残留。独立原始审计尚在实施。
- AP FC 退出真实验证当前句柄 `51908`，证据 `validation/joint-input-stall-0fexbp4y`，原 WSL 输出 `/root/wksim-input-stall-lu54vqv1`。先查询真实状态再决定下一次启动。

## 尚待完成

2026-09-07后续：AP FC退出 `0fexbp4y` 已通过，两份死亡完整ROS原始审计也通过（`validation/retirement-audit-20260907/*-audit.json`）。健康 `product-joint-flow-koyf3_wj`、PX4 DDS `product-joint-flow-d3dqnmx8`、AP DDS `product-joint-flow-2nzfj9ta` 三真实驱动及原始审计均通过，健康同飞13.960s、69572 tick。Windows51项、安装候选79项、默认355项（29跳过）、旧预检11项通过。初次默认矩阵因新的生命周期测试导入旧无scene模块失败，已改为遵循既有候选门槛并在真实安装候选矩阵执行；原失败保留。

MATLAB桥真实R2022b协议通过。首次启动触发本机Documents/MATLAB/startup.m的RflySim自动配置更新（原日志和未知变更边界在docs/matlab-bridge.md）；随后任务私有startup.m/-sd/which校验实际通过，不再执行原自动注册。PX4实飞run1因旧/tmp模型已丢失被预检正确拒绝；主线用原build_model在 `/root/wksim-dependencies/models/wksim-model-1__iz_qj`重建同SHA256库，通过 `capability-index.resource_locations.model_library`统一映射，不改历史基线/准入哈希，双栈公开预检通过。

MATLAB PX4 run2正式任务pass：真实MATLAB退出后FC boot推进62.344s、物理推进63.24s、正常落地；UE无Actor记录，仍未验收。AP run1因验证器未等合法resume offer失败，取消已受理后以当前新鲜合法offer显式恢复并LAND，最终cancelled/safe_landing/children_reaped成立，不改失败。生产records仅记录非有限可选遥测诊断，没有证据把瞬时stale归因于NaN；验证器已改为20s有界只读等offer，并用raw_json保留MATLAB单元素数组形状。

UE无数据已在实际无飞控namespace/socket复现：overlay内同名目录遮住主机后来绑定的receiver。主线 `isolate_temporary_files(consumer_sockets=())`用目录FD+no-canonicalize bind只保留获准消费者目录的同一host inode，其余/tmp仍私有；两个真实mount/socket检查通过（`private-consumer-mount-final.log`）。第一次bind被mount用户态路径规范化误指到overlay，已保留失败并修正。此修复之后新的当前真实验证为 `validation/matlab-flight-px4-20260907-run3`，主代理终端句柄待工具返回后记录。后续需AP重跑、原始独立MATLAB/UE审计、最终回归及报告/票据。首期倍率和其他G3–G6/Full义务仍未完成。

## 后续已完成与当前前沿（本段覆盖上述旧进行中状态）

- MATLAB PX4 run3、AP run2均完整通过并退场；独立原始审计和两个篡改负例通过。PX4退出后物理推进61.72s/FC61.56s，16张有效UE原生帧；AP物理66.78s/FC65.427417s。清理选择中的30个Windows PID、12个不同单机Linux组当前实读均无残留。`tools/validate_matlab_cancel.py`与`matlab/validate_cancel.m`已写，正常MATLAB cancel真实一例仍待跑。
- 完整本轮报告在 `docs/2026-09-07_accelerated-integration-report.md`；#18/#19/#20/#22/#41五条进展已通过gh发布并逐字读回，票据仍OPEN，发布记录 `validation/migration-resume-20260907/publication/publication.json`。
- 0.5倍率等待末端使用1ms保护区，避免sleep过冲和临界点回调；准备任务传输、模型零tick快照及映射哈希移至时钟启动之前，staged Task仍必须经显式start-task产生go才能执行。两次未前移的0.5失败 `_v2ol_cm`/`uzsz7zlx`已保留，没有放宽100ms。
- 同一串行RPC源码的0.5正式三epoch `joint-rate-flow-7tcgrb6o`、`ynhheu8i`、`iz01zhz7`，均真实飞行/正常退出/完整raw审计通过。合计78个10s窗，各有60s真实双机空中段，hold/waypoint各有完整窗口；最坏迟到分别28.607132/53.680553/66.825204ms。`rate-half-cohort.json`关联三份原始审计，明确该cohort的源码版本，不能直接充作后续batch版本通过。
- 串行1× `joint-rate-flow-sufbeqlt`资源不足在tick3032/100.318ms冻结；没有标1×通过。为改善1×，新的双模型批量RPC已在worker.py/joint.py实施：同tick先发两端，再收齐，唯一clock.commit未移动，每channel rpc.tick仍为实际确认前沿；所有传输异常poison整批。
- 主线另复现/修复持续半帧饿住health回调、KeyboardInterrupt后未poison两个边界，17项无跳过检查通过，真实1000步顺序/批量120状态和trace完全相等。持久证据 `validation/parallel-model-rpc-20260907/checks-green/`；旧代理/tmp证据已因WSL生命周期不可见，不再引用为保留文件。实际诊断吞吐2205.6→3970.1tick/s，不是实飞或G6结论。
- 新batch 1× `joint-rate-flow-p7xgcrmv`在tick12528/100.164ms迟到冻结，实测速率0.992176×，仍未通过，不继续盲调或放宽阈值。先按效率优先收口0.5、生命周期/过载恢复及其他可执行前沿，1×性能与Full义务保持开放。
- 三份串行0.5完整原始审计现在全部通过，`rate-half-cohort.json`汇总3个相同源码epoch、78个完整10s窗、每场连续60s真实双机空中段及hold/waypoint窗口，区分地面且精确验证启动动作之前无已受理的飞行请求。
- 当前所有子代理均已完成/闲置，八个实际配置见agents.json；不可通过无法显式选择模型的followup接口恢复。正常MATLAB取消新测试已由主线启动，目录`validation/matlab-cancel-px4-20260907-run1`，具体句柄以最近工具结果为准。后续仍需batch .5真实回归/故障、过载/变速/暂停/单步/恢复/冷重置、源变更后矩阵和报告/票据收口。
