# 模块交付与即时接续

## 当前运行与模块负责人

当前5个外部执行端为3 DeepSeek、Claude、OMP。codebuddy三席均429结束，重置提示2026-09-13 20:54:20 JST；不把它们计入活跃数量，也不循环重试。根Goal仍active，三分钟heartbeat保持PAUSED。

| 负责人 | thread / turn | 当前交付 |
| --- | --- | --- |
| DS-1 | 45decda4-b315-42b3-b7da-2b724dabfd4f / d8f0ed2e-c011-4291-aa3a-94777dd3a886 | 验证时间规则v3，分清整数ULP距离与相对精确有理数的误差 |
| DS-2 | e2a62dda-d7fa-43f0-bfdb-c62eb13ac86c / 1b8a5b44-c9d1-49c0-970f-7542c396aa0e | 只准备最后已完成sleep/loop-health时间字段，不增加时钟读取 |
| DS-3 | 7849b551-87ef-4dd7-8322-cd7e72ea241d / 624fc129-a613-4ba6-a925-e311274b4a55 | 独立验证回调字段候选的时钟/回调/异常等价性 |
| Claude | e64514a6-77c2-4b27-91a7-896c92a361fd / 2dff6812-a526-4015-91ca-a6505ae1f949 | 补齐父探针分析器全局流序校验并复核两场原件 |
| OMP | 51609e8d-e4ce-4a8e-8a0d-f7c896c24842 / e7b7b0b6-005c-419f-bee5-556be244293e | 按sleep/loop-health有无分组，独立核算新场remaining区间 |

实时接续句柄与交付范围以validation/coordination/parent-probe-run-20260913-01/dispatches.json为准。模块负责人负责内部测试/修复；交付稳定SHA后独立复核、批量集成。审计器5项缺口已修复，主会话独立反例7/7符合预期、20份交付哈希一致，5165781已推送；旧错误报告明确被v2替代。G6严格hex/目标序号修复经过52项作者检查及10项独立复核、15个输入/源码/回放哈希复验，13cf154已推送。aligned仍仅表示结构对齐，不能忽略numerator_equal/matrix_equal或据此宣称G6通过。

已推送ffb48b5、c1bfd42：准入独立测试与证据包10项检查、计时记录器/producer/独立对抗53项合并检查全部通过。G6合同已纠正旧“入口不存在”说法，当前缺口仍为有依据且approved的逐量预算。

最新无探针MIXED l6bxh4tn失败：epoch26acf41ac8904593a93427d530e59879，tick28604，迟到104381463ns，wall112.660268145s，未起飞。7141组、12工作超额组；工作超额合计18492055ns，start22420单次释放超额61209261ns，待独立定位，不能归因OS或缓存编码器。无诊断标记，source_unchanged=true，cleanup_errors=[]；同boot9f076946-7482-45bb-9188-a75badaa1958下PGID2210–2219独立全空。Keeper683/start147141按身份核验后SIGTERM且session69716终态；flight session31296终态，禁止再poll/restart这两个句柄。

本场唯一运行候选是worker.py缓存JSONEncoder：原0becd1f3…→38f34a8f…；主仓库与私有检出已接线，真实worker协议/日志测试Windows和WSL各18项通过，OMP实际WSL3.10等价6项通过。微基准不是整场收益；失败场保持failed。私有joint.py/runner已恢复为诊断前f5433c2e…/f5411627…，rate/probe保持0b53a16a…/a8bac9ac…。拒绝的追赶投影没有接入。下一步基于61ms区间证据选择改动，不盲重跑同配置；全部原门及已通过PV保持。

父探针诊断uy9ov56b已真实完成并失败：epochbf067fd133454585a0c2c62e9e2bcfb4，tick90132，wall232.496016401s，RateUnmet100116315ns。22523完整组及22524父探针记录（末次未成功begin单独报告）；无spin/census。源码未变、cleanup_errors=[]，同boot9150ec13-5eb1-44e4-ab9e-152e451dfb9b下PGID2086–2095独立全空。Keeper598/start337身份核验后SIGTERM，session20574终态；flight session67260终态，禁止重poll/restart。私有runner现08e20642…（父探针内存deque仅留最新1，完整JSONL保留），worker38f34a8f…、parenta8bac9ac…和rate0b53a16a…保持。Windows tools/run_joint_flight.py未改。

本场started转移分区已由主会话独立核算：priorwork35935249ns、outside_begin3094328ns、initial_health3153715ns、remaining_begin57609467ns；这是释放超额区间，不是总等待时间或OS归因。最大单次释放超额12877513ns@17852，其中12593632ns来自前组工作。本场未重现61ms间隔。末次未开始尝试跨沿197487ns后触发，不能伪造成完成start。分析器在补流序拒绝，当前数字不等于其所有解析路径已验收。

新计划仅准备复用已有sleep/loop-health前后读数的最后回调字段，无新增时钟读取/节拍算法/阈值变化；独立验证后再决定是否必要实跑。已过PV不重跑，所有诊断保持diagnostic_only。G6 token边界修复已以d21eae1推送，13项新/旧真实实现回归、18项原测试及17项候选身份核验通过，模型候选字节不变。

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
