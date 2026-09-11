# 33 · 显式 JointRate 组间 timing probe

## 目的与边界

这是 #83 的下一短切片：为真实 `tools/run_joint_flight.py::run` 的 candidate/PV 路径增加一个仅显式环境变量启用的诊断入口。`joint_runtime.py` 不参与该路径，并已精确恢复 HEAD。默认 `JointRate`、1 ms 物理步、8 ms@0.5x 周期、四 tick 单锚、no-catch-up、100 ms 严格阈值、health cadence 和 release guard 均不改。本切片不运行 SITL、UE、MATLAB，不修改现有 dirty/Claude #102 文件。

实现文件限定为：

- `tools/run_joint_flight.py`：在 `run(args)` 第一条副作用前解析环境；candidate/PV 开启时构造 `JointRateTimingProbe`。
- `Simulator/wksim_runtime/joint_rate_probe.py`：严格解析环境、生成嵌套诊断身份、标注 rate 字段，以及 `JointRateTimingProbe`。
- `validation/test_joint_rate_probe.py`：fake-clock 行为、真实 runner 三态、类身份、源清单和副作用前 fail-closed 回归。
- `tools/audit_joint_rate.py` 与 `validation/test_audit_joint_rate.py`：独立固定并校验嵌套诊断身份；保留历史未知事件的原有处理，只拒绝缺失或被篡改的 probe 身份。
- 本文档。

环境合同：

- 缺失或精确值 `0`：关闭；runner 直接构造精确 `JointRate`，不产生 probe 事件或诊断字段；candidate/PV source manifest 仍保留运行时依赖的 `joint_rate.py` 与 `joint_rate_probe.py`。
- 精确值 `1`：仅允许 `args.task_profile` 属于 candidate/PV；满足时 runner 构造 `JointRateTimingProbe`，其它 profile 在任何副作用前 `ValueError` fail closed。
- 任何其它值（包括空串、`01`、`true`、空白值）：`ValueError` fail closed。

解析发生在 `run(args)` 的 `check_isolation()`、`tempfile.mkdtemp()`、任何 evidence 文件、ROS 初始化和任何 `Popen` 之前；非法值以及非 candidate/PV 的显式 probe 都不会创建临时运行目录或物理子进程。

## 为什么不能把历史 probe 静默放回默认路径

提交 `572c7bb^` 的旧实现直接在 `joint_rate.py::begin_group` 中加入 `probe_entry`、initial-health 后 `now()`、health 前后 `now()` 及 sleep 前后 `now()`。这些调用不是只读：它们会改变 fake clock 的步进次数，也会在真实单调时钟上消耗时间；因此可能改变 `next_health` 的基准、等待环何时进入 health 分支、剩余时间是否超过 1 ms、sleep 次数和 overshoot，最终改变 `actual_start_ns`、组间 release excess 及 100 ms 门的累计结果。即使业务算法文本不变，也不是 production 行为不变。

新 probe 的额外 clock/包装/记录开销仅存在于 `JointRateTimingProbe` 实例，样本不能冒充 production 性能基准。记录中带有明确的 `instrumentation_overhead` 说明；任何真实运行都必须把 probe 当作诊断候选单独标识。

## 样本合同

每次显式 `begin_group` 尝试追加一个 `TimingSample`，并通过现有 `record` 回调发出 `rate_timing_probe`。成功组的 `outcome` 为 `started`；等待期间超过严格阈值的失败尝试记录 `rate_unmet` 后原样重新抛出 `RateUnmet`。

时间字段均为非负整数纳秒：

- `entry_ns`、`initial_health_end_ns`、`terminal_ns`：单调 clock 观测点；成功时 `terminal_ns` 是 `actual_start_ns`，失败时是最后一次已观测 clock。
- `entry_to_initial_health_ns`：entry 到首次 health 完成，包含进入 `begin_group` 后至首次 health 的可观测时间。
- `loop_health_ns` / `loop_health_calls`：初始 health 之后等待环 health 的总耗时和次数。
- `sleep_requested_ns` / `sleep_elapsed_ns` / `sleep_calls` / `sleep_max_overshoot_ns`：每次 sleep 的请求总量、包裹测得实耗、次数和单次 `max(0, elapsed-requested)` 最大值。
- `final_spin_other_ns`：未被初始 health、循环 health 或 sleep 实耗解释的剩余可观测时间；包含最终 1 ms busy-spin 和其它 clock/check/包装开销。
- `release_excess_ns`：`max(0, terminal_ns-earliest_start_ns)`；成功时是实际起始相对 release edge 的超额，失败时标记“若释放”的终止超额，不宣称已经释放。
- `observed_elapsed_ns` 与 `phase_total_ns`：分别为 `terminal-entry` 和四段相加值，必须精确相等：

  `phase_total = entry_to_initial_health + loop_health + sleep_elapsed + final_spin_other = observed_elapsed`。

`release_excess_ns` 是相对 release edge 的结果量，不重复计入上述阶段和；它与阶段闭合同时报告。非单调 fake clock 会被 probe 拒绝，不产生负字段。

## 合同保持方式

`JointRateTimingProbe` 继承当前 `JointRate`，将原始 `now`/`sleep` 注入同一父类，并只覆写 `begin_group` 的调用包装：父类执行完整原始合同，health 和 sleep 包装器收集阶段数据。probe 不复制或修改 release loop，因而不会另立一份容易漂移的 pacing 算法；额外观测调用仍明确属于 opt-in 路径。

真实 runner 只增加环境解析、类选择、嵌套证据身份和 probe source manifest；`advance()` 的 pacing、health、physics、clock 或 release 调用顺序不变。`make_joint_rate(..., diagnostic=False)` 返回精确的 `JointRate`，`diagnostic=True` 才返回 `JointRateTimingProbe`。

开启后，`rate.jsonl` 每条 rate 记录与最终 `result.json` 都带独立嵌套的 `rate_timing_probe` 对象，包含 `diagnostic=joint_rate_timing_probe`、`classification=diagnostic_only`、`production_performance=false` 及 `instrumentation_overhead`。该对象不覆盖 `rate_bootstrap.classification=untimed_until_first_synchronized_barrier` 等既有字段，因此不能把 probe 运行宣称为 production 性能。

candidate/PV 的 source manifest 和 `source_unchanged` 始终纳入实际运行时依赖的 `Simulator/wksim_runtime/joint_rate.py` 与 `Simulator/wksim_runtime/joint_rate_probe.py`；环境值只决定是否构造 probe、记录诊断字段和使用其计时包装，不改变这两个运行时源的保留语义。默认关闭时仍是精确 production `JointRate`，不产生 probe 事件或诊断字段。

测试覆盖 fast/slow health、重复 sleep、sleep overshoot、work-over/no-catch-up、`RateUnmet`、环境三态、真实 runner 默认/开启类身份、嵌套身份不覆盖 bootstrap classification、probe source manifest、审计端精确身份验证，以及非法环境值在任何 isolation/tempfile/Popen 副作用前拒绝。测试仅使用 fake clock/纯 Python mock；不把它当作 SITL 或宿主性能证据。

## 尚未覆盖的边界

显式入口已经连接到真实 candidate/PV runner，但本切片没有执行真实运行。要获得可归档的诊断 profile，还需要用户明确设置环境变量 `WKSIM_JOINT_RATE_TIMING_PROBE=1`，且任务 profile 必须是 candidate/PV；并保留 `rate.jsonl`、`result.json` 及 source manifest 的诊断身份。没有该环境变量时仍是 production `JointRate` 路径；对非 candidate/PV 启用或使用非法值都会在任何 isolation、临时目录、evidence 或物理子进程副作用前失败。
