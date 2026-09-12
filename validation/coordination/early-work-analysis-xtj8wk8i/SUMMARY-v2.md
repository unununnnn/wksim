# xtj8wk8i early-manager-work 分析摘要 v2（2026-09-13，纯离线）

输入同 v1（`joint-public-flight-xtj8wk8i/early-manager-work.json`，21239 样本、
epoch `792e1feb…`、segment 1）。**v1 的 analysis.json/SUMMARY.md 保留为被取代证据**；
v2 修正三项实质错误（峰值语义、身份严格性、单次读取），见文末。

## 峰值样本（同一完整样本记录；wall 峰与 CPU 峰通常是不同事件）

| phase | last_tick | wall 峰样本（tick / wall / 同样本 CPU，ns） | CPU 峰样本（tick / CPU / 同样本 wall，ns） |
|---|---:|---|---|
| manager_health | 5033 | 1586 / 869,102 / 872,058 | 1586 / 872,058 / 869,102 |
| rate_begin_group | 5032 | 3412 / 4,633,879 / 1,681,997 | **4584** / 1,865,671 / 4,149,306 |
| physics_advance | 5033 | **1999** / 6,622,100 / 1,292,890 | **854** / 1,984,444 / 2,289,732 |
| clock_publication_log | 5033 | 1393 / 433,381 / 433,444 | 1393 / 433,444 / 433,381 |
| post_advance_readiness_summary | 5033 | 2848 / 349,803 / 351,734 | 2848 / 351,734 / 349,803 |

中位分布（valid ok 样本；不再由独立中位之差称"组均差"）：
manager_health wall/CPU 中位 116,271/115,554；rate_begin_group 3,793,590/1,404,041；
physics_advance 783,737/598,220；clock_publication_log 79,246/78,771；
post_advance_readiness_summary 26,340/26,118。跨 10s 边界样本 1 个、错误结果 0、
无截断、无诊断错误。

## v1 错误纠正

1. v1 把"时间上最后 tick"当最大耗时样本（physics 写 5033）；真实 wall 峰在
   **tick 1999**（wall 6,622,100ns、同一样本 CPU 1,292,890ns）。v1 的独立列
   max 还把不同样本的 max wall 与 max CPU 当作同一事件；v2 分列完整峰样本。
2. v1 把两个独立中位之差称"组均差"；v2 只报各自中位，不做该声称。
3. v1 摘要"10s≈10000 tick 的前半"错误：本场 0.5× 实测窗口覆盖 tick 36→5033；
   墙钟窗口固定 10s，**不从 tick 换算秒**。

## 验收边界（不夸大）

真实 probe 记录 clean，但严格 PV 审计会因 **c2IXOr 与 ZlTVa4 的构建 pin 差异**
拒绝该场——**不能称整场正式通过**。本诊断不构成性能通过。runner/helper/阈值未变。

## v2 修复明细（analysis 侧）

- 每 phase 输出 `wall_peak_sample`/`cpu_peak_sample` 完整同一样本
  （tick/start/end/wall/cpu）；时间最后 tick 改名 `last_sample_tick`。
- `identity.segment` 必须 plain int（`True` 被拒且不再被 `==1` 放过）；
  计数/容量非负与 `diagnostic_errors` 列表/total/dropped 一致性硬校验。
- 无效样本总量与有界错误列表分别计数（200 条坏样本 → `invalid_samples=200`，
  不再被截断成 65）。
- CLI 单次读入原字节后再 decode/hash，分析字节与哈希不再错绑。
