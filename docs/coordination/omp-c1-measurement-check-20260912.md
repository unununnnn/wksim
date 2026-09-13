# OMP C1 实测分析独立复核（2026-09-12，只读）

对象：`docs/coordination/ds-c1-actual-analysis-20260912.json`（DS-A）对照两场原件
`validation/joint-public-flight-ztdsk269`（候选）与 `joint-public-flight-7bdfxkb_`（基线）
及 `Simulator/wksim_core/joint.py` 采样条件。未改 A/B 源码或报告；纯数据读。

## 已验证事实（原料逐字复核一致）

- 终末 latch：候选 tick 96624 lateness **100129488**、基线 tick 109776 lateness
  **100050657**，均 `resource_insufficient`/`latched=true`（rate.jsonl rate_unmet 行）✓
- anchor：两场 tick 40，`reason=synchronized_boundary`；候选 anchor.wall_ns
  1218406571925，基线 117986269506 ✓
- freeze 计数 **65783→65631→0**、permanent generation delta **−152**：与
  `manager-gc-candidate.json` 原件及主会话通报一致 ✓（其 source_sha256 `cbf7b018…`
  即今日实测 GC 模块哈希）
- GC 共同窗 [40,96624] 原料复算：候选 81 次/sum 5310019/max 379065；基线
  81/5996522/662721——与 A 完全相等 ✓；delta −11.4%/−42.8% 算术正确 ✓
- timed_window 时长算术正确（193.268s/219.572s）✓
- GC pre/timed/post 分段存在且内部自洽（候选 2+81+0=83=gen 76+6+1；基线
  2+92+0=94=85+8+1；共同窗基线 81 与全程 92 之差为 96624 后的 11 次，含
  gen2@107572）✓
- A 的非因果立场（不归因 freeze/OS/FC、不宣称收益/损害、n=1 无重复无主机负载控制）
成立 ✓；不改阈值的结论成立 ✓

## 需 A 修正清单

1. **anchor_warmup_s=20 错误**：原料两场 steady_after_ns−anchor.wall_ns =
   **2.0 s**（候选 1220406571925−1218406571925=2×10⁹ns；基线同 2×10⁹ns）。
   `units_and_anchors.anchor_warmup_s` 与 `normalisation_limits` 的"The 20 s
   warm-up"均须改为 2.0 s（单位复算，勿照抄）。
2. **common_window 组数 off-by-one 且自相矛盾**：原料两场 `rate_group_end`
   end_tick≤96624 各 **24146** 组；A 的 `common_window.groups` 写 24145/24145，
   而 `dominant_added_latency` 自述"identical **24146**-group window"。须声明端点
   约定（24145 对应 end<96624 排他）或更正为 24146。
3. **lateness_at_window_end 来源不明**：A 的 96241734/68818242 与原料最后一个
   窗内 group_end 的 lateness（96372932/68903042）及 group_start lateness 均不符；
   差值两臂不等（−131198/−84800 ns），推导未记录。须注明推导口径。
4. **执行源分叉**：A 钉分析器 `14ed9d64…`（e1c1631）；主会话当前已提交工具为
   `c3ba9de8…`（f21fc3a "Reconcile recorded rate faults with measured interval
   totals"，变更了 interval/fault 对账算术）。A 的 `terminal_latch_closure`
   （"zero unattributed work-over"）出自旧工具输出——**不得当作本轮新 latch 字段的
   对账结论**；须用 c3ba 重跑或显式标注执行源为 14ed。
5. **step 阶段 mean 的可比性表述不足**：`joint.py:214` 采样为条件式
   （step>2ms 必采 或 tick%250==0），窗内样本 451 vs 425——候选臂因更多 >2ms
   样本被结构性富集，均值组成性偏高。A 已注"sampling noise"，但 delta 表
   （+12~19%）未声明该组成偏差；建议改用 tick%250 周期子集均值对比，或在表上
   明示"慢步富集偏候选臂"。A 的不可归因结论不受影响。

## 可支持结论（本轮复核后）

- 两臂同 latch、候选以更少组到达 100ms 门、候选窗内 GC 暂停更低且 gen2 为零
  （窗内）、基线决定性 gen2 在候选寿命外（107572>96624）——均成立。
- "freeze 改善/损害性能"均不可宣称；+12~19% 每步成本上升不可归因于 freeze
  （GC 外阶段同样上升）。
- 修正 1-5 后，A 的 next_candidate 建议（截断同窗/覆盖 107572/交叉重复）仍成立。

## 边界

未运行 native/构建/模型；未嵌套；未提交 Git。3-4 两条的分叉程度未量化
（未重跑 c3ba 分析器）；prepare_collect 的 96.34ms 提前量未对原料复核
（A 标注 generation==2/tick==0 可溯源）。
