# #83 实测候选：受控 GC 窗口（2026-09-12，诊断场 7bdfxkb_）

## 当前结论（2026-09-14）

- **#83 不重跑**：公共 PV `1w6dru32` 已通过并 CLOSED。本文的 C1 仍是假说，不得触发、建议或替代 #83 重跑，也不得把 7bdfxkb_ 或 manager99 失败写成 #83 未完成。
- **MIXED / G6 / Full 未通过**；#84 仍开放。
- **99 不满足倍率门**：最新无探针场 `oayggl_s` 为 `RateUnmet`，停止重复 99 配置，不做因果归因。
- **下一 native 场仅主会话执行**。本模块只维护离线比较器与纯测试。
- `oayggl_s` / `x39qjvkw` / `5lfbcy43` / `rfw9nmbb` 条件不同（无探针 99 / 有探针 99 / 有探针 50 且不同 boot / 带 `group_work_timing` 的 MIXED 诊断），比较器拒绝把它们当成受控配对。
- 比较器类型门：时钟/计数/lost·overflow 必须是非负 `int`，拒绝 `bool`；GC `end < start`、负时钟、倒序窗口 fail closed。CPU/代价/比例/持续时间必须有限，拒绝 `NaN`/`Infinity`/字符串/`bool`。结构门：`result.json`、source map、metadata 必须是 object，畸形结构返回 `unavailable`/`rejected` 而不是 `AttributeError`。pairing 身份：已知场不得对匿名 run；双方空 `source_sha256` 不得 `controlled_pairing`。`causal` 恒 false，缺量为 `null`。

本文件把真实诊断场 `joint-public-flight-7bdfxkb_` 的测量变成**一个**最小候选。候选尚未实现、未声称
有效；诊断场是 probe 场，永不得充当 #83 通过证据（`Simulator/wksim_runtime/joint_profile.py:219-220`）。

分析原件与全部数值见 `docs/coordination/ds-7bdfxkb-diagnostic-analysis.json`。本模块只做只读分析，
未启动 SITL/ROS/model/build，未改 runtime/调度/门槛，未新增代理，未覆盖原件。

## 1. 本场测量到的结构（先给结论性事实）

- 身份：run `joint-public-flight-7bdfxkb_`，epoch `85df8c49b8f64de8ba794cff149696d1`，
  `full_xyz_pv_yaw_v1`，AP mixed `1e6250ef…` + Control c2IXOr `6fe8c0b3…` + message `29969da0…`，
  `WKSIM_JOINT_CPU_TIMING=1`、`WKSIM_JOINT_RATE_TIMING_PROBE=1`、async evidence 两栈 closed；
  `source_unchanged=true`、`cleanup_errors=[]`、最终 `RateUnmet`，wall 269.5 s。
- 单段、单锚、27,434 组、27,435 行 probe（27,434 `started` + 1 `rate_unmet`）、1 行 latch。
- latch：tick 109,776，迟到 `100,050,657 ns`；**最后一组的起始迟到 99,880,816 ns、结束迟到
  96,205,477 ns 都未到 100 ms** → 与 zzmg3k47/tpwl1k4p 同形：守卫在下一组 `begin_group`
  释放等待里被推过（`latch_site=begin_group_release_wait`）。
- 区间核算（修复版分析器，`closes=true`，差 0 ns）：
  `163,239(首组) + 99,717,577(creep) + 169,841(末段) = 100,050,657(latch)`，
  其中 `creep = 25,703,958(work-over) + 74,013,619(release excess)`。
- probe 关键拆分：`entry_lateness_total = 26,515,920 ns`（**max 20,749,745 ns**）对
  `post_entry_excess_total = 73,534,737 ns`（**max 仅 323,350 ns**）。即：等待循环自身的越界
  每次都不超过 0.33 ms，而"进入 begin_group 之前就已经迟到"的一次可达 20.75 ms。

## 2. 决定性证据链：tick 107,572 的一次 gen-2 GC

同一 tick 的三条独立原始记录（均为本场实测，非推断）：

| 记录 | 数值 |
|---|---|
| `diagnostic_gc_timing` | `generation=2`，`thread_cpu_ns=24,329,672`，区间 `333123296937→333147623903` |
| `diagnostic_native_input_timing`（px4 wait） | `wall_ns=24,786,425`，`thread_cpu_ns=24,787,151`，区间 `333123246422→333148032847` |
| `diagnostic_step_cpu_timing` | `native_inputs` wall `24,975,402` / cpu `24,975,329`；该 tick step 合计 `25,464,842` |

三条区间的嵌套关系：**GC 区间完全落在 px4 wait 区间内**，而该 wait 又落在 `native_inputs` 阶段内；
px4 wait 的线程 CPU 与其墙钟几乎相等（24.787 ms vs 24.786 ms），说明这段时间监督器是**在 CPU 上运行**，
不是被阻塞在 I/O 上。

后果（同场 probe 直接量到）：跨 tick 107572 的那一组 work 超出约 20.75 ms，下一组
`begin_group` 的 entry lateness = 20,749,745 ns、post-entry excess = 20,785,815 ns
（该次等待本身只用了 36 µs，且 `loop_health_calls=0`、`sleep_calls=0`）。
**一次事件占本场 100.05 ms 预算的 20.8%。**

旁证：全部 94 条 GC 样本的 thread CPU 合计 31,147,795 ns，这一条占 78%；其余样本量级 ≤ 约 2 ms。
另外两处大的 entry lateness（tick 2000 = 3.06 ms、tick 5504 = 2.64 ms）同形，但**没有对应 GC 行**，
其 px4 wait 是 off-CPU（wall 6.6–6.9 ms / CPU 0.79–0.89 ms）——机制不同，本包不把它们混为一类。

## 3. 候选 C1（最小、可被反驳）

> **在计时段开始前对 manager 进程的 Python 循环 GC 做一次窗口控制：`arm()` 只读记录既有
> enabled/threshold/freeze_count；`prepare()` 在所有任务 `initialized` 且 tick-0 快照核验之后、
> `physics.connect()` 与首个 rate anchor 之前，执行**恰好一次** `gc.collect()` 加**一次**
> `gc.freeze()`；`restore()` 在 runner 外层 `finally`（**全部 native 清理之后**）只做一次
> `gc.unfreeze()`。没有第二次 collect。**

- **只用 collect + freeze + unfreeze**：**绝不**使用 `gc.disable()`，**绝不**调用
  `gc.set_threshold` 或任何方式改动阈值。当前实现（`tools/manager_gc_candidate.py`
  SHA256 `cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66`，runner
  `tools/run_joint_flight.py` SHA256 `fd0b7ee6…`）的可变调用集合就是 `collect`/`freeze`/`unfreeze`；
  **恢复阶段不做第二次 collect**。
- **候选合同由真实产物判定，不另造文件**：runner 写出 `result['manager_gc_candidate']`
  （`ManagerGCFreeze.report()`）与旁文件 `manager-gc-candidate.json`；两处都存在时必须一致。
  本模块的比较器 `tools/compare_joint_gc_diagnostics.py` 直接消费该报告并核验：
  `original.{gc_enabled,freeze_count,thresholds}`、`prepare_check.thresholds == original.thresholds`
  （阈值状态未变）、`freeze_count` 是冻结对象计数而不是 `freeze()` 调用次数（`after` 与
  `freeze_count_after` 须为正整数且一致；`restore_before_unfreeze` 可以为更小的非负整数）、
  `restore` 回到 0（`freeze_count_after_unfreeze=0`、`expected_original_freeze_count=0`、
  `restored_to_original=true`）、`activation.clock_tick == 0`（tick-0 准备）、`events` 含
  `armed→prepared→restored` 且无 skip/noop 路径、`source_sha256` 与
  `result['source_sha256']['tools/manager_gc_candidate.py']` 一致。
  缺证 → `unavailable`，矛盾（含 result 与旁文件不一致、恢复未回 0、阈值变化、非 tick-0 准备）→ `rejected`；
  不同 boot / 不同源码 / 缺完整窗口 / 缺失诊断标记 / overflow·lost / 时基或身份不一致 → `rejected`，
  不产出 delta；bool 时钟、乱序/负 GC 区间、非有限代价、非 object 的 result/source/metadata、
  已知场对匿名 run、双方空 source map 同样 fail closed。描述性数字、受控配对与因果结论分开标注，因果恒为 false。
  比较器**不**要求主会话手造 `gc-freeze.json`，也**不**转换证明或改 runner 迁就自己。
- **直接测量依据**：§2 的 tick 107,572 链条（GC 24.33 ms → px4 wait 24.79 ms → step 25.46 ms →
  20.75 ms work-over → latch 的 20.8%）。
- **实现层**：这是**运行器/管理进程侧的配置性改动**（GC 窗口与冻结调用），落在候选场次的
  manager 启动/段边界路径；不涉及 `JointRate` 门槛、物理、4 tick 屏障、单锚、调度优先级或任何
  滑窗预算。
- **C1 是假说，不是必要条件**：本场只观测到"一次 gen-2 GC 与一次 work-over 落在同一 tick 且区间
  嵌套"，既没有做对照，也没有重复场次，因此**是否可复现、是否必要、是否充分都未证明**。若主会话
  选择别的杠杆（例如 §4 的等待内阶段），C1 不构成前置条件。
- **理论上界不是实测保证**：本场 GC 线程 CPU 合计 31.1 ms、最大一条 24.3 ms；若同类停顿在候选场
  不再落在计时窗内，*理论上*最多影响该量级（约 20–26 ms）。这是**从单场单事件推出的上界推断**，
  不是实测节省；本场仍有 74.0 ms 分布式 release excess 未被动过，因此不得把该推断写成"必然转绿"
  或"已证明的必要不充分"。
- **可反驳判据**（同一诊断命令、同身份、同 env，重跑后逐项对照，不做与正式场的 A/B）：
  1. `diagnostic_gc_timing` 中是否仍有 gen-2 样本落在计时窗内，其 `thread_cpu_ns` 最大值；
  2. 同一 tick 的 `diagnostic_step_cpu_timing.native_inputs` wall/cpu 最大值是否仍出现 ~25 ms 级样本；
  3. 最大单次 work-over / 最大 `entry_lateness_ns` 是否仍出现 ~20 ms 级样本；
  4. 若上述三项均无变化，且最大 stall 仍无 GC 伴随 → **C1 被反驳**为该场主因（此时应转向 §4 的缺口）。

## 4. 本场仍不能区分的原因（准确缺口，不猜 AP/CPU/OS）

- 74.0 ms 的 release excess 分布在 27,433 个区间上（均值 2.7 µs），单次越界上限只有 0.323 ms。
  probe 的阶段量测的是**整段等待**（含合法的 sleep 与设计上最后 ~1 ms 自旋），不是"越界那部分"，
  因此本场无法把 2.7 µs/组 的残差判给：睡眠超时（全场 `sleep_max_overshoot` 合计 1.179 s，均值
  43 µs/组，被余量吸收）、等待中的 health 回调（100–500 µs 桶里 `loop_health` 合计 56.4 ms，
  ≥ 该桶 release excess 合计 52.1 ms；相关性，不是因果）、还是自旋后的调度/派发。
- tick 2000/5504 的 off-CPU px4 wait 只证明"监督器在等"，不说明 FC/宿主/Windows 哪一侧。
- **要关闭该缺口需要的测量**：逐次"越界部分"的阶段分解（excess 对 phase，而非整段等待对 phase），
  以及 wake-to-run/调度证据；本场没有记录这两项。

## 5. 执行与边界

- C1 与 §4 的补测都需要**新票据**：C1 属候选源码/配置改动，必须先冻结身份、单变量、同诊断命令复测，
  再走原验收；本包不实现、不改 runtime。
- 继续禁止：重锚、追赶、缩短轨迹/驻留、放宽 100 ms 或滑窗门槛、把本诊断场登记为 rate/PV/Full 通过。
- 本场是 probe 场（`formal_acceptance=false`，`joint_profile.py:219-220` 拒绝带 probe 的正式证据），
  其绝对迟到（100.050657 ms）与 269.5 s 墙钟**不得**与正式场做 A/B；只比较 §3 的四项同场特征。

## 6. 可复用只读比较器（本模块已交付）

`tools/compare_joint_gc_diagnostics.py`（契约测试 `validation/test_compare_joint_gc_diagnostics.py`；
候选合同正例由**真实** `ManagerGCFreeze` + 注入 `FakeGC` 的 `report()` 产生）把本场
分析变成可复用入口：输入两场的 `result.json` / `rate.jsonl(.gz)` / `joint-wire.jsonl(.gz)`，输出

- 身份与兼容性：单场内混身份 → `rejected`；两场 `run_id`/`epoch` 不同只是描述性并列，
  受控配对仍要求同一 boot、同一源码、完整窗口与诊断标记。profile / timing env（probe、
  CPU timing、`group_work_timing`）/ async / AP-Control-message-PX4 基线不一致 → `rejected`；
  `oayggl_s`/`x39qjvkw`/`5lfbcy43`/`rfw9nmbb` 的已公布条件不同 → `rejected`，不得当受控配对；
- GC：`gen2` 样本数、`gen2` 与全部 GC 的线程 CPU 最大/合计（缺失时 `null`，不填 0）；
- 区间嵌套证据：最大 GC 区间是否嵌在同 tick 的 native wait 内、该 wait 是否在 step 的
  `native_inputs` 内、该 wait 是否在 CPU 上（仅嵌套事实，不给因果）；
- 最大 entry lateness 与最大 work-over；区间核算的 creep / work-over / release excess 与 latch 闭合
  （直接复用 `tools/analyze_joint_rate_intervals.py`，未写第二套区间算术）；
- 候选 GC 合同：直接消费 `result['manager_gc_candidate']`（及/或旁文件 `manager-gc-candidate.json`，
  两处都有时必须一致），核验 §3 列出的字段；缺失 → `unavailable`，矛盾 → `rejected`；
  baseline 带候选报告 → `rejected`；
- 永不输出 `performance_pass`，`claim_limits` 明示"两场只说明共现、不构成因果"。

实跑自检（对原 7bdfxkb 只读，同一场与自身比较，`--self-check`；输出文件名不与上一版重叠）：

```bash
python3 -B tools/compare_joint_gc_diagnostics.py \
  --baseline /root/wksim-release-acceptance-fe3/validation/joint-public-flight-7bdfxkb_ \
  --candidate /root/wksim-release-acceptance-fe3/validation/joint-public-flight-7bdfxkb_ \
  --self-check \
  --output validation/coordination/gc-diagnostic-comparator-20260912/self-check-7bdfxkb-manager-gc.json
```

结果 `status=unavailable`、`reason=candidate:manager_gc_candidate_contract:unavailable:no_manager_gc_candidate_report`
—— 即"该场可被完整分析，但没有真实候选报告，因此**不能冒充 candidate**"；输出含原件 SHA
（rate `484016e7…`、result `cdfe7f49…`、wire `9035a4af…`）并逐项复现 §1/§2 的数值
（gen2 max 24,329,672 @107,572、嵌套为真、max entry 20,749,745、
creep 99,717,577 = 25,703,958 + 74,013,619、latch 100,050,657 闭合）。
