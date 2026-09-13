# 模块交付与即时接续

## 当前运行与模块负责人

当前5个外部执行端为3 DeepSeek、Claude、OMP。codebuddy三席均429结束，重置提示2026-09-13 20:54:20 JST；不把它们计入活跃数量，也不循环重试。根Goal仍active，三分钟heartbeat保持PAUSED。

| 负责人 | thread / turn | 当前交付 |
| --- | --- | --- |
| DS-1 | 45decda4-b315-42b3-b7da-2b724dabfd4f / e676b0bd-ee12-40a3-8f76-d56662ee1582 | 修正G6时间规则：区分现有容差保护、binary64表达与样本观测 |
| DS-2 | e2a62dda-d7fa-43f0-bfdb-c62eb13ac86c / ad8395c9-56d4-4209-9063-3f58b7930f54 | 准备父探针只保留最近一个内存样本的私有runner补丁及等价验证 |
| DS-3 | 7849b551-87ef-4dd7-8322-cd7e72ea241d / f20f44e8-1871-4dd7-9228-363bfb80c6f6 | 固定token边界回归的不可变旧版本，完成可复现交付 |
| Claude | e64514a6-77c2-4b27-91a7-896c92a361fd / 50162f4e-9987-444b-8690-c3cdc2e9f3f2 | 用现有父探针entry/health/terminal字段划分释放超额，复用原件验证 |
| OMP | 51609e8d-e4ce-4a8e-8a0d-f7c896c24842 / e8d5eb2a-ef96-4991-ad39-911e30a2dbad | 父/子探针联合覆盖复核已交付，等待必要的最终接线审查 |

实时接续句柄与交付范围以validation/coordination/parent-probe-plan-20260913-01/dispatches.json为准。模块负责人负责内部测试/修复；交付稳定SHA后独立复核、批量集成。审计器5项缺口已修复，主会话独立反例7/7符合预期、20份交付哈希一致，5165781已推送；旧错误报告明确被v2替代。G6严格hex/目标序号修复经过52项作者检查及10项独立复核、15个输入/源码/回放哈希复验，13cf154已推送。aligned仍仅表示结构对齐，不能忽略numerator_equal/matrix_equal或据此宣称G6通过。

已推送ffb48b5、c1bfd42：准入独立测试与证据包10项检查、计时记录器/producer/独立对抗53项合并检查全部通过。G6合同已纠正旧“入口不存在”说法，当前缺口仍为有依据且approved的逐量预算。

最新无探针MIXED l6bxh4tn失败：epoch26acf41ac8904593a93427d530e59879，tick28604，迟到104381463ns，wall112.660268145s，未起飞。7141组、12工作超额组；工作超额合计18492055ns，start22420单次释放超额61209261ns，待独立定位，不能归因OS或缓存编码器。无诊断标记，source_unchanged=true，cleanup_errors=[]；同boot9f076946-7482-45bb-9188-a75badaa1958下PGID2210–2219独立全空。Keeper683/start147141按身份核验后SIGTERM且session69716终态；flight session31296终态，禁止再poll/restart这两个句柄。

本场唯一运行候选是worker.py缓存JSONEncoder：原0becd1f3…→38f34a8f…；主仓库与私有检出已接线，真实worker协议/日志测试Windows和WSL各18项通过，OMP实际WSL3.10等价6项通过。微基准不是整场收益；失败场保持failed。私有joint.py/runner已恢复为诊断前f5433c2e…/f5411627…，rate/probe保持0b53a16a…/a8bac9ac…。拒绝的追赶投影没有接入。下一步基于61ms区间证据选择改动，不盲重跑同配置；全部原门及已通过PV保持。

下一诊断选择既有父探针（RATE_TIMING_PROBE=1，CPU_TIMING unset，不用spin/group-work flag）。parent的entry_ns与前组end可直接划分begin前间隔，initial_health/terminal及聚合相位可再定位begin内；旧0fsmugd1有11737份父记录，不能只看子spin的1ms窗口。61ms在新无探针场的具体位置仍未知。先核验父探针内存留存有界补丁与离线区间分类器，再由主会话决定一次必要实跑，不做无依据的亲和性实验，不重跑已过PV。

上一有界诊断rfw9nmbb仍保留：24661完整组、18超额/16详细报告/2显式丢弃，diagnostic_only且failed。其48个详细间隙全部在各自4tick组内，旧“16宏边界间隙”分析已被主审拒绝。源快照、失败原件和旧报告保留，不能把CPU与wall移位窗口差值称为精确离CPU时间。

## 调度规则

1. 完成一项即验收、返修或接续独立任务，不等整批结束。每项任务包含内部修复、纯测试、真实原件复核和稳定SHA，减少主会话重复接手内部工作。
2. 每席只有一个正在执行的任务，并预先标明下一项及依赖。没有合法ready项时如实记录等待原因，不制造重复报告来填满席位。
3. 一个文件只有一个写入者；交付并确认终态后转移写入权。审查者收到稳定版本才审，主会话提交精确已验证版本，保护其它工作区修改。
4. 精确thread read/wait是状态依据；THREAD_BUSY不算排队，cancel回执不算终态。真实句柄见rolling-six-20260913-01.json；文档/JSON不自动执行调度。
5. 代理可跑纯测试和既有原件只读分析，禁止模型、MATLAB、ROS、飞控、UE和构建。主会话新native前分别核查两WSL，确认无竞争重负载后另一次调用启动。
6. 保留1ms/native屏障/4tick/无追赶/100ms/全部完整窗口及原物理和身份门。已通过飞行不重跑，失败原件不覆盖，不发布厂商源码或二进制，不操作用户进程。
7. Goal仍active；#83已关闭，#84/G6/Full未完成。以已验收交付与解除依赖衡量效率。历史记录仍可从Git读取，当前检查点为short-cycle-goal.md。

跨主题的新任务使用简短独立会话，减少无关历史；同一模块返修保留原负责人。新会话是否更快需实际观测，不据历史长度宣称已证性能提升。

每次native启动在入口复验当前boot与两发行版前检相符；不相符就重做前检。WSL保持进程须有自有PID/start_ticks/boot身份，结束时核验并清理。
