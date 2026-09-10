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
