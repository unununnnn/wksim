# #62 epoch-1 就绪期延迟分解证据（离线，双 evidence）

2026-09-12。`tools/analyze_joint_readiness_latency.py`（schema `wksim.readiness-latency.v2`）只读消费 #62 已封存失败原件，按 `failure-facts.json` 的**数据驱动 evidence 声明**（目录与 pins 均相对 evidence root）逐场分解 1× 4 ms 组周期内每个 timed group 的 work / start lateness / start-to-start creep，不修改任何计时合同、不声称根因。输出明确区分 `clock.jsonl` 的原始时钟相位与 scene 的 `faulted_clock` 发布相位。


## 输入封印（fail-closed，v2）

- **唯一 pin 权威**：`runs[].sha256`。旧顶层 `sha256` 集合已删除——其中 `case/run/result.json` 钉 `81da5a77…` 与本机留存字节 `e23404ea…`（2026-09-09 case）自相矛盾；未消费漂移**不**再钉成通过，历史值留在 git 历史与 #62 评论。`failure-facts.json` 出现顶层 `sha256` 即拒绝。
- 结构强制：恰好两个 evidence，`evidence_id`/`directory`/epoch 全部 distinct；每项另声明 `expected_run_id`，它必须同时等于 `result.json.run_id` 和 scene 中每个 `message.run_id`。两个 evidence 可以引用同一个真实 `run_id`，因为第二 case 是 2026-09-09 留存件的重算，**不是独立 run，也不是 epoch-2**；`epochs_run` 必须为 1。
- 目录校验：拒绝绝对路径、`..` 逃逸、软链（含中间组件解析出根）、缺失目录。
- 文件校验：五个消费输入（`rate/clock/scene-lifecycle/faults/result`）缺一、多钉、软链或字节漂移即拒绝。
- 锁存判等：计算值与 `expect` 逐字段精确相等（含 measured_rate 浮点判等，无容差）。
- 输出：同目录原子 create-only 写入（mkstemp + fsync 后以不可覆盖的 hard-link 发布，再删除临时名）、禁覆盖异字节（同字节幂等）；竞态中目标先出现也只能比较或拒绝，不能覆盖；`sort_keys` + `allow_nan=False`；stdout 与文件均为原始字节（Windows 不经文本转换）。

## 方法

- 周期显式参数化（默认 4_000_000 ns = 1× 四 tick）；`requested_rate` 必须精确等于 `4·TICK_NS/period`。
- 恒等式逐组闭合：`creep = previous_work_over + release_excess`（与 `analyze_joint_rate_intervals.py` 同一定义，周期泛化）。
- 相位 join：bootstrap（untimed 组）/ `running`（timed group 的 clock.jsonl 逐 tick 权威相位）× `stabilization|steady`（锚点 +2 s 冻结合同边界）；`faulted` 仅用于 scene 终止事件。
- 锁存自证（全部任一篡改即拒绝）：原始 `rate_anchor` 的 epoch/request/segment/anchor/measurement/steady 字段绑定到 `rate_unmet`；`rate_unmet` 与 `rate_segment_end` 的全部共享字段（含 completed_groups、measured_rate、worst_lateness_ns、anchor、steady_after_ns）逐项相等；`result.json`（status/epoch/run_id/error + authority tick/phase）及 `result.rate.last_segment` 再绑定到 `rate_segment_end`；三份 summary 的 group 数、worst lateness 与 `measured_rate = completed_groups × period / (last_end − anchor.wall_ns)` 均从实际 groups 精确复算（对应 `joint_rate.py:150-153`）；`rate_segment_end` 必须 reason=fault、tick=锁存；原始 `clock.jsonl` 必须连续记录到且仅到锁存 tick，最大 tick 和最后记录的 tick 均须等于锁存 tick，锁存 tick 的 raw phase 必须由原件验证为 `running`；最后与 `scene-lifecycle` 交叉核验：scene 的 `message.run_id` 全部绑定到真实 run，tick 非递减，锁存前不得有更早 tick 的 faulted/fault_latched，唯一 `faulted_clock` 的 scene phase 必须由原件验证为 `faulted`，并与唯一 `fault_latched` 同 tick、相邻结束，后者是最后记录。同 tick 的 `faulted` permission（如封存原件中的记录）必须出现在 `faulted_clock` 之前，两个终止事件之间不允许插入记录。两个相位来源分别输出为 `raw_clock_phase_at_latch` 与 `scene_faulted_clock_phase`，不把 scene 事件称为 raw clock phase。

## 两场封存失败的实测结果

**Evidence 1** `epoch-raw/`（evidence `epoch-raw@de6ba7f2…`，真实 run `rate61-cpu8-20260909-e1-e2561e27`，epoch `de6ba7f2…`）：

| 事实 | 值 |
| --- | --- |
| 锁存 | tick 7588，lateness 100,312,171 ns，completed 1887，measured 0.9871539539890174 |
| 组内最大 start/end lateness | 99,636,364 / 99,510,243 ns |
| creep 闭合 | 99,620,691 = work_over 73,636,728 + release_excess 25,983,963 |
| bootstrap | 10 组，最大单组 work 104,584,682 ns |

**Evidence 2** `case/run/epochs/2a8d5df1dd4244c3868dc7f38e85a369/`（evidence `case-20260909@2a8d…`，真实 run `rate61-cpu8-20260909-e1-e2561e27`，epoch `2a8d…`；2026-09-09 留存 case）：

| 事实 | 值 |
| --- | --- |
| 锁存 | tick 19608，lateness 105,497,865 ns，completed 4892，measured 0.994637564416662 |
| 组内最大 start/end lateness | 96,843,959 / 105,497,865 ns（end 即锁存组） |
| creep 闭合 | 96,827,880 = work_over 57,175,054 + release_excess 39,652,826 |
| bootstrap | 10 组，最大单组 work 105,848,751 ns |

相位形态（两场相位均只有 `running`，锁存前无 fault 相位）：

| run | raw clock phase / window | scene termination phase | 组数 | work p95 / p99 / max (ns) | start lateness p95 / max (ns) | release_excess p99 / max (ns) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | running / stabilization | faulted | 500 | 4,152,095 / 6,223,875 / 13,221,268 | 41,326,555 / 46,510,335 | 563,817 / 1,115,247 |
| 1 | running / steady 区 | faulted | 1387 | 3,657,706 / 4,590,086 / 11,614,223 | 98,404,692 / 99,636,364 | 222,082 / 4,773,044 |
| 2 | running / stabilization | faulted | 500 | 3,284,096 / 4,489,080 / 11,502,613 | 18,086,892 / 22,325,931 | 57,353 / 225,105 |
| 2 | running / steady 区 | faulted | 4392 | 3,354,098 / 3,951,579 / 12,653,906 | 94,234,205 / 96,843,959 | 224,144 / 2,543,594 |

两场输出的 `raw_clock_phase_at_latch` 均为 `running`，`scene_faulted_clock_phase` 均为 `faulted`。这是两份输入中的两个独立事实：`clock.jsonl` 的最后 raw snapshot 仍在运行，而 scene 随后发布同 tick 的 faulted clock，再记录 fault latch。

可直接观察到的共性（不推断原因）：

1. **两场同形**：creep 单调累计贴帽——stabilization p95 迟到一个数量级小于 steady 区（run1 41→98 ms，run2 18→94 ms），迟到在整段运行中持续积累直至锁存；不是单点突发。
2. 单组 work p95 约 3.3–4.2 ms，常态贴满 4 ms 预算；work_over 与 release_excess 双通道贡献（run1 约 74/26，run2 约 59/41）。
3. 两场 bootstrap 区各有一个 >100 ms 的 untimed 单组（未计时区，不受帽约束）。

## 边界与不声称

- 不构成 1× 通过、不重判旧失败、不打开 epoch-2/3；#62 保持 OPEN/needs-triage。
- release_excess 在 health 检查/记录写入/睡眠过冲/调度延迟之间的因果拆分**无法**从封存输入获得——那是私有 tracefs 采集器切片（需真实运行，仍推迟）。
- 场景相位只到 `running/faulted` 粒度；health/model 子相位不在封存输入内，不做冒充分解。
- 100 ms 监督、10 s/60 s 窗口、1 ms/4 tick、steady 合同与候选预算一律未动。

## 验证

`python -B -m unittest validation.test_analyze_joint_readiness_latency`：29 项。Windows 本地回归 29 项（symlink 用例无特权跳过 1）；同一命令可在 WSL Ubuntu-22.04 复跑。覆盖：双 evidence 分解与闭合、同真实 run_id 的身份绑定、确定性、CLI stdout/输出文件原始字节与重算一致、create-only 原子输出（含可确定复现的目标竞态：异字节拒绝、同字节幂等）、漂移/缺失/pin 集形状、旧顶层 pin 拒绝、恰好双 evidence/distinct 目录与 epoch/epochs_run=1、目录逃逸（`..`/绝对路径）、软链、期望篡改（tick 与 measured_rate）、错周期、错率、transition、换 epoch、精确 100ms 不可锁存伪故障、raw clock 连续性和 latch+1 拒绝、raw/scene paused 与 unknown phase 的 repin 后拒绝、catch-up 与 earliest_start 篡改、原始 anchor/unmet/segment_end/result summary 成对篡改拒绝、result/scene identity 篡改、scene 故障 tick/phase/顺序/终止邻接/同 tick permission 顺序/单调性篡改、跨记录不符；封存证据复现精确断言两场 tick/lateness/measured_rate、两个相位来源与相位形状，并断言输出文件与重算逐字节一致。
