# OMP mixed 场失败独立复核（2026-09-13，只读）

对象：`joint-public-flight-oxv29042`（epoch `18c96a7e…`）。只读该场 rate.jsonl 与
控制/Task 原件；不提升 profile；1ms/4tick/no-catchup/100ms/全窗未动。

## 核验的 latch 事实（raw 复算）

- 单段 anchor tick 40（wall 110030174978）；steady_after = anchor+**2.0s**（实算）。
- latch：**tick 131760，lateness 100034744ns**（超 100ms 门 34,744ns），
  reason `resource_insufficient`；完成组端 **32930** = (131760−40)/4 ✓ 精确。
- runner `status=failed`、`RateUnmet`，result.rate 未写（latch 在率环内）。

## 早期/稳态分区（更正版：墙钟域，2026-09-13 复核纠正）

- **分区按 actual_start_ns vs steady_after_ns（墙钟），不按 tick**；物理 tick
  不换算墙秒。此前本报告的 tick≤2040 划分（500/32429 区间）把 tick 2040 误当
  2 墙秒，已作废。
- 正确分区：早期 249 区间/975,731ns，跨界 1 区间/4ns，稳态 32,679 区间/
  98,805,073ns——与主会话 `phase_partition`（249/975731、1/4、32679/98805073）
  逐字一致 ✓；合计 99,780,808ns 与 creep 总量精确一致 ✓。
- work_over 15,139,984ns 一致；trace SHA `8725b63c…` 一致；终末闭链
  115,732 + 99,780,808 + 138,204 = 100,034,744 精确闭合 ✓。
- 最大区间（两臂一致）：tick 127940→127944，creep 5,547,162ns =
  前组 work_over 5,140,957（该组工作 13.14ms > 8ms 预算）+ release 超额
  406,205，等式精确 ✓。

引用主会话 `validation/current-mixed-20260913-01/main-rate-analysis.json`
（SHA `b4c7f44e…`，analyzer `1c43ac9c…`）；本复核独立验证了 creep/work_over
总量、最大区间、终末闭链与墙钟域分区，未重复扫描历史场。

## xtj8wk8i 诊断场 release 路径分类（同场同身份，可复核）

脚本与结果：`validation/33-formal-promotion/20260913-mixed-failure-review/`
`classify_xtj8wk8i_probe.py` + `xtj8wk8i-probe-classification.json`。

- 主会话初查集精确复现：release_excess≥10µs 且 entry/initial_health 均不迟于
  earliest_start 的 **894 组，合计 71,821,720ns**。
- **边界确认**：该 71.8ms 全部位于 initial_health_end 与 terminal 释放之间；
  不在初始 health 之前、不在 health 跨界（入选条件即证）。
- **睡眠越界只是它自身这个统计量**：各组越界合计 56,629,628ns（组均 63.3µs，
  最大 1.27ms，>1ms 仅 1 组）——**不支持盲目加大睡眠余量**。先前睡眠超时可能
  被尾部余量吸收，`final_spin_other` 还含其它记账开销，故**不从 release 总
  71.82ms 相减得"已归因残余"**（v1 的 15.19ms 残余叙述已撤回）。
- `final_spin_other` 中位 1,036,079ns、最大 1,399,275ns——**无等待路径的
  线程 CPU 分解，不能把 spin_other 直接叫 off-CPU**。
- 睡眠请求 2,050.6ms vs 实睡 2,107.3ms（全部入选组）；零睡眠组仅 2 个
  （超额 0.32ms）——超额主体在带睡眠路径。

## 任务终态与物理

- 最后任务阶段：`land_accepted`（ros 124.158s）；latch 在 tick 131760
  （≈131.76s）——**LAND 下降中被率门终止，Task 日志未达 landed/disarmed
  终态，不得计 pass**。
- latch 时刻：AP 0.905m 以 0.49m/s 正常下降（无明显物理失败）；PX4 已落地
  （0.0m、0.02m/s）。

## 结论

mixed 能力证明行仍 **MISSING**；本场为诊断证据。失败主导项是全程稳态释放
蠕变（98.8ms/99.8ms，稳态区间口径），非早期蠕变、非单点大组、非物理异常。

## 可复核的下一诊断问题（有界）

1. 稳态 ~2.9µs/区间的持续 release 超额：现有 interval 分解不含释放等待内部
   构成（分析自述 `not_separable_without_instrumentation`）——需要一次全程
   0.5× mixed 的分段采样场（已有 `diagnostic_step_cpu_timing` 条件采样 +
   `--early-work-timing` 式窗口扩展到全程），把 release 等待与组工作逐区间
   分离；不得改门。
2. tick 127940 单组 13.14ms 工作（LAND 下降段）：该组内 sensor/写入/native
   输入的分段构成，需对照当场 wire/truth 原件定位（本复核未展开）。

## 边界

未启动 native/构建；未嵌套/Git；PGID 2023–2032 主会话已独立核验全空（本复核
未重复）；不把未终态 Task 日志当通过；不重复全库测试或历史场扫描。
