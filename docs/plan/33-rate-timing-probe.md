# 33 · 显式 JointRate 组间 timing probe

## 目的与边界

这是 #83 的下一短切片：为 `JointRate.begin_group` 增加一个仅显式实例化才会启用的诊断包装器。默认 `JointRate`、`joint_runtime`、CLI、1 ms 物理步、8 ms@0.5x 周期、四 tick 单锚、no-catch-up、100 ms 严格阈值、health cadence 和 release guard 均不改。本切片不运行 SITL、UE、MATLAB，不修改现有 dirty/Claude #102 文件。

实现文件限定为：

- `Simulator/wksim_runtime/joint_rate_probe.py`：`JointRateTimingProbe` 和不可变的单组计时样本；复用 `JointRate` 的实际 `begin_group`，只在显式 probe 实例上包裹 clock、health、sleep。
- `validation/test_joint_rate_probe.py`：fake-clock 行为与默认实现身份回归。
- 本文档。

不接入 production profile 或入口。使用者必须显式导入并构造 `JointRateTimingProbe`；默认 `JointRate(...)` 没有任何 probe 分支。

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

测试覆盖 fast/slow health、重复 sleep、sleep overshoot、work-over/no-catch-up、`RateUnmet`，以及默认 `JointRate` 源码 SHA256 和无 `timing_probe` 事件/默认行为。测试仅使用 fake clock；不把它当作 SITL 或宿主性能证据。

## 尚未覆盖的边界

代码交付只能提供可显式构造的诊断 profile。要让真实 `joint_runtime` 或正式飞行入口连接该 profile，需要另一个明确的入口/配置变更，并必须单独审查其 instrumentation overhead、证据身份和运行许可；本切片不连接，也不改变默认生产路径。
