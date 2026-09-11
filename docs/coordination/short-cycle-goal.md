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
| Oh My Pi | PX4 v2 trace 解析器只读复核 | 不写文件；核对字段、时间顺序、兼容性和因果边界 |
| agy | #104 GitHub 验收/依赖/标签只读复核 | 不写仓库或 GitHub；新线程 `a23348a3-8cda-4373-9144-af3451f418af` |
| Claude Code | PX4 WorkQueue 同实例两批次原生冒烟 | 仅 `tools/check_px4_workqueue_trace.py` 与对应测试；不改候选/patch/runtime |
| 主会话 | v2 主审、准入/冒烟复核、唯一 SITL 运行线、票据与提交收口 | 其它文件；不与 Claude 并发修改其两个文件 |

真实 SITL/UE/MATLAB/tracefs 共用资源串行预约；每场唯一输出，只清理自有进程。纯代码/离线测试并行。下一实际运行优先选择依赖齐全且已通过代码复核的一条，不用模拟成功替代真实验收。

## 跟踪

完整 `delegationId/threadId/turnId/deepLink/status` 快照见 `validation/coordination/short-cycle-dispatches.json`；状态以 `codexhost thread read` 实时结果为准。

- [Oh My Pi](codex://threads/71b28520-5317-4b44-aab5-0f3b8329ae9f)
- [agy](codex://threads/9ef3a71a-c4fb-4b72-8950-1df2dae018de)
- [Claude Code](codex://threads/586cc873-65e7-4d1e-975b-3de9bbac446e)

前轮大型推送已成功，push 进程 `33870` 已退出 0，不再等待该进程。后续仅增量推送已验证提交，未验证代理工作不随提交混入。

2026-09-11 本轮：`50897b8` 完成真实 SLX 11.8 生成、Linux 构建与核心冷重置/冷重建，#70/#71/#72 已逐票关闭；`f240694` 修正相机反馈与重放边界，并取得分栈原生等待真实记录；`071c7fc` 交付公共相机命令发送器，主会话的19项WSL真实消息构造/编排检查通过（含缓存MOVE过期不被去重跳过、ACK未定后重新悬停、uint32编号不回绕）。这些提交均已推送。详见 `docs/2026-09-11-short-cycle-results.md`。当前剩余 29 张开放票据，Full 未完成。#45 专属策略批准出处、ABI 样本合同、G6 数值预算和硬件条件必须按真实证据处理；只阻塞各自分支。原步长、权威时间、输入屏障、100ms 门槛、误差预算与失败原件不变。用户 `docs/Prometheus.gitmodules.reference` 的修改不属于本轮。

2026-09-11 新进展：`a429ccc` 已推送，case5 实际普通任务飞行中视觉采集/几何/速度验收通过，不等于闭环飞行；`32a1f5b` 已推送，同源完整31输入 major/post 两工况各60,120值零差异，26项检查通过，不等于G6。主会话正在显式实验资源准入、JointArUcoTask/raw节点图和Windows实时协调器集成，未经真实运行/独立审计不登记飞行通过。旧Control OEvS3W已实查与当前源码不一致，待PX4构建释放资源后构建新Control。

当前真实测试 `validation/40-aruco-tracking-01` 已启动（主进程session 46675）。PX4 `/root/wksim-px4-land-7RjMjQ` 与Control `/root/wksim-joint-control-FWBLNX` 构建完成，独立资源预检通过。运行源码冻结：三代理现在仅写各自离线审计/复核工具与测试，不改Simulator或运行器；OMP物理审计复核，agy原生目标关联检查器，Claude原始公共命令链+timeline审计。详细当前turn见dispatch JSON。

第一场tracking-01已失败并正常退出：run aruco-track-afba53e79a / epoch d17b518d73844c43ab670adc6845c1e6，tick848、lateness107146683ns触发原100ms倍率保护，RGB未启用、两机未解锁，组残留0。session46675已退出1（驱动），manager正常退0；失败原件已拷回run目录。当前唯一真实运行是tracking-02（session57563），增加既有WKSIM_JOINT_CPU_TIMING只读探针，以区分模型/监督器CPU与分栈native等待；没有放宽倍率或物理门槛。

tracking-02（session57563）已退出1并完成组清理：run aruco-track-0e74873eb6 / epoch48ab11fb5c4c4c679d55a2ed9d2b71f9，tick12136，lateness100152917ns，任务尚未解锁；两次失败不同进展但都不能验收。分阶段探针已取得，GC最高.42ms，晚期4–5ms CPU尖峰分布在health_and_models/encode_send/native_inputs，尚未确证根因。OMP下一片只读按时间重叠分析，agy修正原生分析器禁止坏CDR回退诊断message，Claude继续raw公共链审计。当前没有实际SITL/UE运行，主会话准备更精确采样探针。

tracking-03已退出1且所有运行组已清理：run aruco-track-556a1b0366 / epoch81f44463c34d476e90b7f44e93e6e2a7，tick13992再次rate_unmet，未解锁。session37908与采样74845都已结束。py-spy0.4.2安装在独立/root/wksim-pyspy-bpC2X3，非阻塞99Hz主线程采样2998条，证据validation/aruco-startup-pyspy-01；不作为飞行/倍率通过。主会话已去掉ArUco raw记录器的重复decoded诊断副本（CDR原字节/GID/时间保留）；OMP独占隔离ROS executor微基准，未改产品源码，完成即释放资源。当前无SITL/UE/MATLAB运行。

接续检查点：已推送提交为a429ccc（真实空中视觉场景）、32a1f5b（完整31输入major/post同源零差异）、0f756d6（PX4 land候选构建）。ArUco实验配置/任务/raw记录器/协调器/物理审计当前仍是工作区改动，先完成验收后分组提交；不能git add全库，用户Prometheus.gitmodules.reference保持不动。tracking-01/02已归档分片且逐成员验证，tracking-03已完整retire并拷回run，尚待归档（等微基准释放资源再压缩）。sampler37908/74845都结束，当前无SITL/UE。OMP微基准初稿发现两个执行器争同node和publish后一次spin不能保证callback的问题，已定向中断并在turn2fc3c7bc-04d4-4406-bc35-f465eb15a56c交代修法继续；不要使用该未通过微基准来改产品。Claude原始审计已退修实际task[aruco]嵌套、capture-root布局、真实f32序列化比较、provenance和loss-HOLD缺口（turnf7aa0ce5-baa7-4b2d-b356-0b714ad0b5b2）。agy原生分析器已移除CDR失败回退，并在第一场481条真实CDR解析成功但0命令、0目标，尚需主审有命令场景。下一优先收OMP/Claude；微基准可信后再决定是否复用持久executor。不放宽既有禁止追赶/暗中重锚规则与100ms门槛。

最新主线已推送：890c3c6接入与前三场证据，7752d5a原始公共审计+微基准，0ed3d30修ready快于旧status的竞态，e9e407b补AP真实cmd_vel原始频道，7e5045a补ArUco结束边界监督并保留第四场，d07fcba把相邻pump重复RMW take减为一次（finally中保留失败事件），39项WSL检查通过。第四场起飞成功但ready竞态停止，记录max53.195421ms；第五场run aruco-track-503a94d16a/epoch dfd6110631dd412aa051fec1489ccaee在tick6148再次rate_unmet（107.884012ms），已退场。第五场证明静态优化尚不能称倍率问题解决。当前无实际SITL/UE，准备验证单次drain路径；下一场继续保持无并行重测试/压缩。OMP执行器微基准负结果已接受，不改成持久executor；agy只写cmd_vel/ENU解析与测试定义，Claude只写loss-HOLD因果审计与测试定义，须主会话在真实运行结束后执行。

当前唯一实际验证：tracking-06，Tool session93912确认仍运行；目录/root/wksim-aruco-track-MJOU2Q1c/aruco-track-692e75fb3b，最近检查starting/tick0。此次无cpu/py-spy探针，使用d07fcba单次raw drain、0ed3d30就绪竞态修复、e9e407b cmd_vel频道与7e5045a结束倍率边界监督。不得在该运行结束前并行做测试、构建、归档压缩或推送；仅读小状态/源码与代理交付。AGY/Claude此轮获准代码编写但禁止测试，交回后也须等主线运行结束再执行。713f06a以前提交均已推送；第五场已归档分片，所有旧失败保留。第六场结果尚无，不能标为通过或重启同一run。

第六场已确认退出：tick6312、102.642592ms、0 RGB，全部组清理；证据已随0d793fc提交推送。0d793fc还接入DirectParentGuard（启动完整身份核验，每次getppid检测、无缓存/放宽频率）与默认关闭write-timing探针，相关48项WSL检查通过（3条件跳过）。当前第七场validation/40-aruco-tracking-07正在运行，Tool session9501，--write-timing观察监督器wire/rate/clock/public-dds/lifecycle的实际同步write；不改日志payload、不异步化、不代表已找到根因。不能重复启动。OMP guard完成并已主审接入；agy修BODY当world及任意0.05匹配阈值的问题；Claude修loss门真实sensor_id/target字符串、初始/终态HOLD、expired非空target、未来恢复误伤suppression等真实契约问题。两审计尚未主验收，不能提交全工作区。用户Prometheus.gitmodules.reference仍保持原修改。

第七场已确认失败并清理：run aruco-track-c7466446af / epoch30b9ba60b780465a908a1274db51b6e5，tick4860，101.200156ms；9501已退出1。真实write探针找到rate10.18ms与wire3.17ms，同版本缓冲重放逐调用字数/底层偏移精确吻合，分别触发65100/63650字节底层write；证据与工具已推送f035f1e，不代表解释全部迟到。当前无SITL/UE。主会话接手evidence_stream.py重写有界后台写入，保留旧草稿snapshot；OMP现在只写test_evidence_stream.py/报告作独立负例复核，不能改实现。新模块已按真实第七场节奏重放18266行、7711683字节，SHA完全一致，writer正常退场、提交调用max405402ns，证据validation/async-evidence-replay-01；68505退出0，不能称飞行通过。async-evidence接入当前仍WIP/未提交：仅明确ArUco实验允许，JSON状态/操作请求保持同步，5个JSONL日志通过有界队列，check/close错误及complete=false都会判失败；48项相关WSL检查通过（3条件跳过）。必须等待OMP边界测试/主审后才提交和开第八场，不能提交全库；用户Prometheus.gitmodules.reference保持不动。

最新：be461e8已推送，loss/HOLD/recovery审计真实schema/时间状态机修订经45项WSL检查及额外边界负例；fbf1fb1已推送，有界后台JSONL写入module及接入，14项Windows/WSL错误路径验证、相关62项WSL检查（3条件跳过）、真实18266行重放字节一致均通过。主会话接手重写实现，OMP仅独立测试，无Timer/关闭fd竞态；新模式只允许明确ArUco实验，默认同步不变，退出核验每流complete/实际文件字节数。当前第八场validation/40-aruco-tracking-08通过Tool session23245正在运行（--async-evidence --write-timing），不可重复启动；直到结束不做并行测试/压缩/推送。当前无其它SITL/UE任务。native inspector还未提交：主会话15项WSL检查通过，修改了BODY未知依据的过度断言；其输出仅observed/unresolved，不等于native关联门通过。所有失败与用户Prometheus.gitmodules.reference继续保留。

第八场已结束并保留failed：run aruco-track-32addd9c38 / epoch901d6d10a3934976a899633020d97657，85 RGB/70 target，两个Task pass且落地，收尾tick78248 rate_unmet。完整证据已推送2929d7d；内容诊断geometry/逐tick跟踪单项通过（max .426228m、恢复末窗 .046669m），只标diagnostic_only不改整场。五个async writer全部正常退场且字节数相等，主write最大<1ms；大型PX4 Task result6.96MB/14194actions实测读解析22.58–30.55ms。84cb1da已推送，把ArUco大报告读取移到停止/清理后，运行中仅依赖可信worker真实exit0，最终严格核验身份及exit/status双向一致；OMP独立复核发现的反向缺口已修，12项WSL负例通过。当前第九场validation/40-aruco-tracking-09经Tool session20675仍在运行（--async-evidence --write-timing），不能重复启动/并行压缩测试。Claude正在只读诊断08原始公共链与loss门（bec3bbc6-4fa0-4500-80dd-144c0e2efd0e），不改运行代码；OMP本次复核已完成。

第九场已确认retire：run aruco-track-acd136bb89/epoch648703857a1d46f5a1fb0146826cbf07，在tick65088再次rate_unmet，不能称收尾延迟读取已解决全部问题。新实证：仅操作自有短命进程的WSL两次probe证明，原SCHED_FIFO/50被所有子进程与新线程继承；RESET_ON_FORK后它们为SCHED_OTHER/0，父仍FIFO/50。b984415已推送，将该标志仅用于ArUco实验，native model/FC leader仍显式40；启动时保存所有自有线程实际policy/priority。当前第十场validation/40-aruco-tracking-10经Tool session84113正在运行（async-evidence/write-timing），不要重复启动，不并行重测试/压缩。第九场完整原件已随该commit归档。Claude已用08真实CDR验证两栈public/adapter链通过，但loss门误将同tick后处理MOVE消费算到早先suppressed_hold之前；新修复任务ef32be0f-150c-4699-affb-86ce7411ce98在跑，仅原auditor/test/report。整场08的rate failed继续保留。

第十场首次完整采集：run aruco-track-69b75c6f3c / epoche77b1ed46ede49d68e2e68edddc3fd25，84113退出0，89RGB、双Task pass/落地、authority无fault、所有writer/进程完整退场。物理/几何单项审计pass（max跟踪.410998m、恢复.049764m），原rate计划单anchor/no catch-up核验通过，15个10s窗通过，worst82.258203ms；无完整60s双机airborne窗，不能称三epoch G2通过。证据/工具/报告已推送b299322。仍待本场原始loss门/原生MOVE-HOLD字段关联和发布者身份等，#104未关闭。当前第十一场AP选中跟踪：validation/40-aruco-tracking-11-ap，Tool session4518确认运行中；候选candidate-arducopter.json仅selected_stack改arducopter，同资源同门槛，--async-evidence/--write-timing，不能重复启动或并行重测试压缩。OMP只写native MOVE独立审计工具/测试定义（09915340-3ce6-4758-854a-09afdd49d278），等运行结束主会话执行；Claude同tick loss误判修复仍在进行（ef32be0f-150c-4699-affb-86ce7411ce98）。

第11场AP相机选择在启动tick5532/100.925198ms rate_unmet失败，0RGB，4518已退出1且全部组清理。实际reset-on-fork策略与普通Control/Agent OTHER/0均核实，后台writer全部complete，没有发现继承修复未生效。已存在同固定资源PX4第10场完整通过，因此下一步仅做一次相同参数/源码的有界AP重复（第12场），用来区分启动间歇失败，不放宽门槛或改判原件。OMP native MOVE工具仍只写代码，Claude同tick loss门修复正在真实消息测试，未经主审不关闭#104。

第11场失败证据已推送ae61cae；当前第12场AP相同参数有界重复已由Tool session5842启动，目录validation/40-aruco-tracking-12-ap。此次未改源码/资源/门槛，依据同资源PX4第10场已完整通过，对启动间歇失败做一次重复确认。不要重复启动该run；保持无并行重测试/压缩/推送。第11场4518已终态，不能继续等它。

第12场AP有界重复也失败：run aruco-track-e1e60851a9 / epoch085074bb16c9481880ea37adf616a098，取得32帧、进入跟踪，但tick62348/100.015309ms触发原倍率保护，5842已终态、组无残留，原件已推送。查实worker.py每步仍先行缓冲同步write再回复RPC；12adf90新增显式async-model-evidence，默认行为不变，模型主线程40+RESET防记录线程继承，2s关闭上限、summary/实文件完整性核验。两个真实模型各1000步对照RPC与完整轨迹字节一致，43项WSL检查通过（2条件跳过），证据model-async-trace-equivalence-01。当前第13场AP试验validation/40-aruco-tracking-13-ap由Tool session60492运行，--async-evidence --async-model-evidence --write-timing；不能重复启动/并行重测试压缩。源码/依赖/门槛其它不变，尚无结果，不宣称性能解决。

第13场已结束并独立核验：aruco-track-56b317f796 / epoch3662bc056ae74e0abed662214a8010bd，60492退出0、90帧、双机落地，物理/几何及本场倍率pass；AP最大跟踪.475563860m、恢复末窗.035399126m，最坏迟到86.533429ms，15个10s窗/首60s通过，无完整60s双机空中窗。两份模型writer已关闭、无存活线程、字节完整（AP118955260/PX4124909836），其它五流也完整。完整归档572文件/7分片sha55e1345b8929ae10e3e15c9fe152f51a4f5f8c46ed8c342a6990415c3adc8754。当前无实际运行。OMP初稿发现AP XY交换及native→随后同tick SessionState时间窗错配，退修da2728cd；Claude核验10/13完整raw链564c01be；agy核验发布者身份/独占性31969cfe，详见dispatch JSON。#104仍待原生MOVE/HOLD/发布者等，Goal继续active，不改判历史失败。

最新主线5358d3c提交推送AP13完整采集；550f0f6提交推送两场真实public/raw/loss审计（PX4 14周期/AP11周期，整审仍pending native三项），主会话58项WSL复核通过。bc092f4补终态HOLD原生等待：AP13 request90末尾HOLD被同tickLAND91覆盖无SessionState；PX410 request91有state但无native位置样本；中途AP11段169样本/PX414段165样本字段一致。原件保留pending，不能回写通过。35927e8已推送具体writer绑定/每发送前+1s+report图快照/逐raw样本GID校验；隔离真实DDS213中silent second writer负例通过，所有节点关闭。当前无SITL/UE。末尾wait进一步要求armed+COMMAND_CONTROL，8项WSL测试通过，等待Claude独立复核后与图快照一起实跑14。OMP当前7a98bcd0补math.hypot/严格时间边界/控制epoch与scene分离/int UAV/真实10+13 MOVE；agy当前edcc599a将实际新publisher_snapshots接入其离线审计；Claude ba440584独立复核final-HOLD。源码所有者：主会话runtime/guard/HOLD工具；OMP native_moves；agy audit_aruco_publishers；Claude仅独立final_hold_review测试/报告。用户reference改动保持原状，Full及#104仍未完成。

83a8f90及此前已全部推送：f319760两场72/74条MOVE精确原生关联主验收；35927e8具体writer图与样本GID守卫、22ca026末尾HOLD armed/COMMAND_CONTROL；83a8f90离线snapshot严格审计与Claude独立最终HOLD两负例。Claude缩片cd1988f6完成、无阻断项；publisher主审去optional hash fallback、严格raw/provenance/Task身份、完整类型集合，AP peer未行使cmd_vel标not_exercised；15项原publisher+12项独立负例及最终HOLD独立2项已验证（review中把RTPS16byte诊断误当24byte绑定的负例已修，绑定仍严格24bytes）。OMP已完成空闲，agy只代码review并禁止运行测试；runtime只归主会话。第14场AP新验证已启动validation/40-aruco-tracking-14-ap，采用async-evidence/async-model-evidence/write-timing，加末尾HOLD等待与native publisher snapshots；不要并行重测试/归档/推送，不要重复启动。运行结果未知，#104/Full仍未完成。

第14场工具session为36716，已确认运行中；先poll该session，禁止另启副本。OMP下一片仅只读#82倍率复用路径与一页报告，不跑测试/建图/构建；当前runtime源码冻结。

第14场已retire，session36716退出1、manager0、55帧、tick65452 rate_unmet 100.165787ms，无残留/cleanup错误；完整442文件6分片与诊断已推送fefc501。实际publisher图AP177/PX4135次全部通过，同场具体writer+rawGID证明闭合；末尾HOLD未到达。两模型writer完整，AP底层一次23.225556ms异步写不等于模型主线程阻塞；write-timing主流无慢记录。rate重放精确RED，14场14个组>8ms，总前组超额49.799ms（13场9个/17.619ms），最大20.037ms在arm附近47312组，RGB前；无CPU探针故未指认具体模块。当前新15场validation/40-aruco-tracking-15-ap-cpu已启动，同源码资源参数加既有--cpu-timing定位峰值，禁止并行测试/压缩/推送与重复运行。OMP下一rate一页报告有陈旧反向拒绝描述（实际双向已修）且漏scheduler/model异步门控，已退修2e005ff6；Claude只读native完成合同02f67c85。#104及Full未完成。

第15场Tool session=61502；run_id=aruco-track-aa766cf3f8。下一接续先poll61502并读该run小status；仍运行时禁止重启、重测试、归档/推送。第14场36716与push9456均已终态，不要继续等待。

第15场61502已退出0，aruco-track-aa766cf3f8/epochd342bbd7a8c449e19aa63c9dc268c50e，90帧、双机落地、无fault/cleanup。0241d17及全部证据已推送（push59227终态0）。物理几何pass（APmax .472222570m/恢复末窗.148149505m），rate最坏97.970542ms、15个10s窗/首60s通过但无完整airborne60s。raw loss14周期闭合；72MOVE精确原生关联；15段HOLD173样本，末尾request91有1真实native位置样本，首次补齐terminalHOLD；AP229/PX4161图快照及GID全部验证。仍待payload timestamp独立审计以及PX4新修复对应场。15峰值转到57500附近：native_inputs样本wall53.861ms/线程CPU7.202ms，AP wait最高9.584750ms/CPU1.081238ms，不能直接归因AP或Windows；GCmax.300441ms。OMP820688ed仅代码实现有界外部/proc线程采样器（无当前实测/测试），Claude4b13ded4仅代码写payload时间戳审计，runtime冻结。当前第16场PX4对应验证validation/40-aruco-tracking-16-px4-cpu已启动，同async/模型async/write/cpu探针参数与15一致，仅selected_stack变PX4；禁止并发测试/压缩/推送和重复启动。

第16场Tool session=16857，run_id=aruco-track-8e056c491a。接续先poll16857；15场61502与push59227均终态，不要再等或重启。16运行期间禁止所有测试/构建/归档/推送；OMP/Claude均仅代码。Goal保持active，#104/Full未完成。

第16场16857已终态1，manager0；aruco-track-8e056c491a/epochd47cb442efcb48bcae670c0c7a246f6b，tick27956起飞前rate失败121.048875ms、0RGB。完整205文件3分片已归档，重放精确复现。6979组中位3.312ms/最大29.6425ms；失败窗阶段CPU/墙钟分布不同于15，仍未唯一归因，不能盲改AP。当前无实际SITL/UE；等待OMP有界外部线程采样器主审后再决定下一诊断。Claude旧4b13切片长时间读查无文件，已取消旧turn，转新任务586cc873-65e7-4d1e-975b-3de9bbac446e/turn44f0f8f1仅2文件compact时间戳审计；保留外部默认model+auto thinking（工具回执已验证），非nested。运行合同40-aruco-run-contract.md更新为实际已实现入口、冻结值和准确审计范围；不改变门槛。#104/Full仍OPEN。

当前无SITL/UE，16完整失败与实际运行合同已推c87548b；88d30a9已推，将fixed_task与ArUco统一三处延迟报告门控（退出、组完成、retirement），26项WSL检查通过/2个显式private ROS未启用，无正式mixed/PV实跑通过声明。OMP采样器已主审退修feec70c2：status路径应epoch.parent.parent、run/epoch绑定、TID start_ticks前后校验、PID批次后校验、完整argv、行数/参数界、自身CPU/耗时、schedstats标记；允许其离线及自建短命进程smoke，不启动SITL。主会话实查kernel.sched_schedstats=0，CLK_TCK=100，WSL6.6.87.2；不把runqueue0解释为无等待，未改变内核开关。Claude新任务586cc873的旧稿有tuple传resolve及“最新发布等于Control已消费”错误，已定向退修a34624e2：PX4以同tick后随state的sample stamp+ENU位置速度唯一定位此前LP，native.timestamp等于该LP.timestamp；新发布但未消费LP不误拒；AP同tickheader必须一致。source/test仍WIP未接收。当前不启动17，先等两个工具交付并主验收。Goal active，#104/Full未完。

0500175已推送有界线程采样器，主会话修复epoch入口、zombie退役、忙线程正常stat变化误丢、空重复目标、错误header、batch耗时/boot_id/CLK_TCK；14项WSL（含自建短命进程）通过。当前第17场validation/40-aruco-tracking-17-px4-threads，run_id aruco-track-83ab77c0eb，Tool session83436已启动；私有/root/wksim-aruco-track-sRS1gSkV/aruco-track-83ab77c0eb。计划于实际tick>=10000时触发外部40s/50Hz，目标supervisor/AP-fc/PX4-fc，不改kernel.sched_schedstats=0，排队计数标不可用。已开启600s自有WSL保活进程session74832，PID/PGID599 start_ticks330，boot_id87e04105-21a5-41fd-a4ea-11f182fe8eb7，约06:31:42开始，必须核实其自然退出或以完全身份匹配关闭；不改WSL配置。当前禁止测试/构建/压缩/推送，runtime/采样器源码冻结，Claude仅代码修timestamp工具。16session16857已终态，不能再等。

17场epoch=ddcbd0ee3cf54c2cb77de4fecd5a0d6c；运行Tool session83436。采样等待/执行协调器Tool session44389，等tick>=10000后运行40s/50Hz，触发记录validation/coordination/aruco-17-thread-sampler-launch.json，输出/root/wksim-thread-probe-17-83ab77c0eb。接续先poll83436和44389，不因观察超时重启；runtime/采样器仍冻结。WSL保活session74832有600s上限，需要确认终态。Claude时间戳工具已开始更新到14KB，测试尚待交，禁止在17期间运行测试。

17运行83436/采样44389/600s保活74832均已终态（driver1/sampler0/keepalive0），无当前残留需等待。17在40296/100.456794ms失败，0RGB，40s采样1991批123442行，实际覆盖10268..30240，不含最终失败；sampler自身CPU4.747s有明显开销，runqueue关闭不判无等待。原件/分析已推2c2ce49；b70ffb2主验收native payload timestamps，21测试，AP15=791/PX4-10=785全过，保留旧场缺口。13accd2新增仅CPU诊断开启的runtime-loop边界，管理/pacing/physics/clock_publish/clock_evidence/group_end_view，31测试通过（实际advance调用顺序、失败不推进、原RateUnmet不被日志错覆盖）；没有物理/倍率门槛变化，默认无额外clock读取。Graph已查ClockPublisher.publish并直接读源，未重建大索引。当前18场validation/40-aruco-tracking-18-px4-loop run_id=aruco-track-e8b6165cde已启动，无外部sampler/保活程序，采用新内部loop timing，同其它参数。禁止并发测试/构建/归档/推送；runtime冻结。Claude当前新任务586cc873 turn65a5e375仅只读复核13accd2（2–5min范围，不跑测试）；源码与timestamp工具已交主会话。#104/PX4修复后完整场仍未过，Full未完。

18场运行Tool session=62632，run_id aruco-track-e8b6165cde。接续先poll62632并找对应小status，不重启同一run。所有17相关句柄已终态，无外部采样器运行；本轮18期间不要测试/压缩/推送。

18场62632已终态1，manager0，tick9388失败230.194579ms、0RGB。新增loop probe将失败精确定位为PX4 input wait219.973566ms/线程CPU25.078397ms；此前start lag仅15.077ms，管理/clock发布/clock日志均短。原件183文件2分片已推d814982。native发送原代码先poll(100)再组件sem barrier，TCP_NODELAY已开；不按100ms倍数猜路径，不先认定logger。OMP草稿有空组件死锁/逐轮日志/虚构上下文，已拒；主会话从真实3文件生成0005，保留全部原sem/bitset/register/continue/empty-return，off无clock/log，trace only active>2ms或poll>20ms。1109步构建成功，私有/root/wksim-px4-component-q0zJqx，manifest SHA a627423fb28ac4ccf190514ef8f0a4378f41b760311cab523ced3bfb21d0d24b；严格3文件delta+产物+父7Rj来源封存。18检查Win/WSL通过，实际candidate component源码POSIX semaphore shim测试off/on/invalid均通过（off/invalid clock_reads0，无日志；on等待全部组件且释放bit2）。admission-exec.json ok=true/native_component_timing=true；两次手工检查的overlay失败保留，已确认是缺环境/WSL额外shell展开，必须wsl --exec且sourceFW overlay后保留PYTHONPATH。原运行器本就exec。37028构建/80382与8846失败复查/44248成功复查及67965推送都已终态。ff8ae96解析器4检查通过，只解读观测不归因，release pair非原子不可作唯一根因。当前19场validation/40-aruco-tracking-19-px4-component run_id=aruco-track-78cb277e06已启动，候选JSON validation/px4-component-candidate-01/candidate.json；只使用原生慢段+内部CPU/write计时，无外部采样/保活，kernel统计开关未改。禁止并发测试/构建/归档/推送，runtime/patch/checker冻结。下一接续poll本场，完成后跑analyze_px4_component_trace.py实际px4-fc.log，并做完整ArUco审计。#104/Full仍OPEN。

第19场Tool session=23939，run_id aruco-track-78cb277e06。接续先poll23939、找到该run小status；不得因观察超时重启。当前无其它SITL/采样/保活，19期间禁止所有测试/构建/压缩/推送。已推送HEAD ff8ae96。

第19场已终态失败并随 `8faa567` 推送：run `aruco-track-78cb277e06` / epoch `e60d74f1719f4e5684e144ff09513b76`，tick60168、100.119728ms、15帧；v1原生记录定位到约26.15ms组件等待，同时暴露81,563次WorkQueue动态注册，不能把旧release观察误作唯一原因。失败原件及归档保留。

当前无SITL/UE进程。PX4诊断v2候选 `/root/wksim-px4-component-ZNq7Mp` 已完成1109步构建、五文件严格delta封存和资源准入，manifest SHA256 `9806c6cbbf5318a33a9359de2846540a4a807a79101a2a426d78ec8d7e792b80`；原生barrier与一批次自删除WorkItem ASan冒烟通过。OMP复核确认ready时间戳在每批注销/复位后的首个Add重新建立，上一轮误报已撤回。Claude正在补同实例两批次同步冒烟；完成主审后才能启动run20。#104按票面失败处理保持OPEN并移至needs-triage，已写入AP15通过、PX4 run19失败与v2未飞行边界。固定1ms、时钟/输入屏障、无追赶/隐式重锚及100ms门槛不变。

run20 已用 v2 候选真实执行并完整 retire：`aruco-track-5bbf33c939` / `f70fb33ea2cc46e0a14e2738c3bbe72f`，55 帧、43 条 PX4 MOVE 已精确证明，AP/PX4 的 135/176 个 publisher 图快照通过；tick65440 以 `101.021467ms` 原倍率迟到失败，终态 HOLD、降落和完整闭环未完成。原件456成员/6分片，SHA256 `06bf9c53d91916c733d3a404dc22277b6a0c5866b912f5f82d41d8d071e76c9c`。v2 将 run19 约26ms最慢组件等待降到约7ms，但最后窗口无新 WorkQueue 慢段，实证是约98.625ms累计相位债务遇到组内波动越过门槛，不能声称单一根因。native MOVE审计器的无命令AP假阳性已修，15项WSL真实CDR测试及run20复审通过；原失败报告保留。OMP定位PX4具体WorkItem，Claude核对全场时序，agy复核审计器与热路径；主会话只接受不削弱每步时钟排他、输入/时钟屏障、无追赶/重锚和100ms门的减负改动，不盲跑相同候选。#104/#40/Full继续OPEN，Goal保持active。

run21 已用标准 PX4 候选完成真实闭环：`aruco-track-405ebd92a0` / `59e79980b4f849c082559e73108e63de`，78,716 tick、91 帧、两机落地、无 authority fault。physical、rate、native MOVE/HOLD、publisher 和 native timestamp 全过；raw 按契约 pending，但公共链、13 个 loss/recovery 周期已闭合，其列出的 native/publisher 项由同场工具补齐。最坏累计迟到 67.206783ms；73 MOVE、14 HOLD（含末尾 request91）、792 timestamp、AP/PX4 162/229 快照通过。568 成员/7 分片归档 SHA256 `2ce552fe17de60be8f1cbfda441256b0e07789f29000085f484e9e6908ef37f5` 已重组复核。主会话判定 #104 与 #40 技术关闭条件满足，待本证据提交推送后执行关闭；Goal 对 Full/G0–G6 继续 active。OMP、Claude、agy 正在分别复核 physical/rate、raw/HOLD/timestamp、MOVE/publisher/#104，均只读且不占运行资源。
