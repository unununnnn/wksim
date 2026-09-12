# DS-A · C1 实跑结果分析（`--manager-gc-freeze`）—— 修订版 v3

分析对象：真实候选场 `joint-public-flight-ztdsk269`（PV+C1，**带**两计时探针）、`joint-public-flight-vwen35gc`（PV+C1，**无**探针），基线 `joint-public-flight-7bdfxkb_`。
只读分析；未运行新 native/ROS/SITL，未改 runtime/调度/阈值，未改任何被分析原件，未提交。
结构化数据见同目录 `ds-c1-actual-analysis-20260912.json`（schema v3）。

> **v3 修订 v2 的两处错误**：①v2 把 **2 墙钟秒换算成 2000 物理 tick**，并把稳态起点硬编码为 `anchor+2000`；正确做法是**直接用 `actual_start_ns` 与 `steady_after_ns` 比较**——0.5× 下 4-tick 组 = 8 ms 墙钟，2 秒 ≈ **250 组**（实测 247–250），且 anchor tick 本身可变（ztdsk269/7bdfxkb = 40，**vwen35gc = 44**）。②v2 的"稳态好 8.8%"**不成立、已撤回**：两个 C1 场在稳态相对同一基线**方向相反**（−13.3% / +12.9%）。
> 保留：**精确的 16.492919 ms 准备期 GC**、真实 freeze 事实、三场失败事实。
> **v3 新增**：分析器 `phase_partition` 精确三分（early/crossing/steady），**残差严格为 0，无 15 ns 缝**；三场输出见 `validation/33-rate-profile/diagnostic-triple-20260912/`。

## 0. 分析器与新增字段

| 项 | 值 |
|---|---|
| 使用的工具 | **`tools/analyze_joint_rate_intervals.py`（本次已扩展）** |
| 新增字段 | **`phase_partition`**：`boundary` / `classes{early,crossing,steady}` / `closure` |
| 边界来源 | `rate_anchor.steady_after_ns`（回退 `rate_unmet.steady_after_ns`），按已加载 rate 身份匹配；**无标记则 `available=false` 且 classes 为 null，绝不猜边界** |
| 分类规则 | interval **结束**于边界或之前 = early；interval **跨越**边界 = crossing（最多一个，单列）；interval **起始**于边界或之后 = steady |
| 闭合 | 三类**恰好**划分全部 interval → 三类 creep/work_over/release_excess 之和**严格等于**总量；残差非 0 或多于一个 crossing 即 **raise**，不做平滑 |
| 未改动 | 原有 totals、buckets、`top_*` interval 形状、`trace_sha256`、`analyzer_sha256`，以及**全部 latch 字段与 no-latch/null 语义** |

**终止 latch 权威闭合**（`main-rate-analysis.json`，分析器 `c3ba9de8…`）：`289518 + 99687759 + 152211 = 100129488` ✔

## 1. 三场身份与结果

| 场 | 角色 | anchor tick | 组数 | creep | work_over | release_excess | latch |
|---|---|---|---|---|---|---|---|
| `ztdsk269` | PV+C1，带探针 | 40 | 24 146 | 99 687 759 | 33 372 289 | 66 315 470 | 100 129 488 |
| `vwen35gc` | PV+C1，无探针 | **44** | 21 763 | 99 636 668 | 34 868 504 | 64 768 164 | 100 485 315 |
| `7bdfxkb_` | PV 基线 | 40 | 27 434 | 99 717 577 | 25 703 958 | 74 013 619 | 100 050 657 |

`vwen35gc` 与主会话已提交的核算逐位吻合：`151077 + 99636668 + 697570 = 100485315` ✔，`work_over 34868504` + `release_excess 64768164 = 99636668` ✔。

**同场身份**（前次已核）AP/control/message 三清单、`joint.py`、manager 调度、bounds、isolation 命名空间一致；差异仅 `run_joint_flight.py`（`fd0b7ee6` vs `92e3c7dc`）与 `manager_gc_candidate.py` 入账——即唯一受控变量。三场同为 `RateUnmet('rate_unmet/resource_insufficient')`。

## 2. 预热时长与是否排除（①，v3 修正）

- **源码事实**：`steady_after_ns = anchor.wall_ns + 2_000_000_000`（**2 秒**）。三场均为 2e9 ns。
- **正确的边界用法**：`steady_after_ns` 是**绝对墙钟纳秒**，必须与 `actual_start_ns` 直接比较。**不得**把墙秒换算成 tick 再加到 anchor tick 上：v2 的 `anchor+2000` 因此把 2 秒当成了 2000 tick（实为约 250 组），且 vwen35gc 的 anchor 根本不是 40。
- **实测边界处组数**：ztdsk269 **247**、vwen35gc **249**、7bdfxkb **250**（= 24 146 / 21 763 / 27 434 组的 1.02% / 1.14% / 0.91%）。
- **是否排除**：匹配窗口**含**预热段；v2 的"500 组 / 2.07%"来自被放大一倍的窗口，已纠正。本版不再靠手工窗口，而是由 `phase_partition` 显式给出三分。

## 3. 精确三分（三场，残差全 0）

| 场 | early 区间 | early creep | early work_over | early release_excess | crossing | steady 区间 | steady creep | steady 每区间 |
|---|---|---|---|---|---|---|---|---|
| `ztdsk269` | 246 | **23 900 631** | 12 665 444 | 11 235 187 | 1 / 4 ns | 23 898 | 75 787 124 | 3 171.3 |
| `vwen35gc` | 248 | **10 749 183** | 7 159 759 | 3 589 424 | 1 / 3 ns | 21 513 | 88 887 482 | 4 131.8 |
| `7bdfxkb_` | 249 | **272 029** | **0** | 272 029 | 1 / 36 ns | 27 183 | 99 445 512 | 3 658.4 |

- **每场三类之和 = 该场 creep 总量，误差 0 ns**（99 687 759 / 99 636 668 / 99 717 577），**无 15 ns 缝**；`classes_are_disjoint = true`。
- **跨界 interval 单列**：ztdsk269 在 tick 1036→1040、vwen35gc 同在 1036→1040、7bdfxkb 同在 1036→1040（creep 3–36 ns，可忽略）。
- **锚点后首 2 秒是新增损失所在**：两个 C1 场的 early creep 分别为基线的 **87.9×** 与 **39.5×**（超出 **+23.63 ms** / **+10.48 ms**）；而**基线的首 2 秒没有任何组工作超时（work_over 恰为 0）**，其 0.27 ms 全部是 release_excess。
- **稳态不可复现（撤回 v2 结论）**：ztdsk269 稳态每区间 3 171.3 ns（相对基线 **−13.3%**），vwen35gc 为 4 131.8 ns（**+12.9%**）。两场方向相反，且二者探针状态不同 → **不存在可复现的稳态 C1 效应**。

## 4. 最早新增损失窗口、top interval、wire 事件关联

**轴**：以各自 anchor 为原点的组索引（0.5× 下理想墙钟节奏相同，8 ms/组）。

- **最早出现正累积差**：组索引 **3**，距 anchor **24.15 ms**；候选累积 creep 2 824 ns vs 基线 133 ns（差 2 691 ns），且**自此持续为正**。
- **局部窗口 [2, 253]**（≈ 第 0–2.03 秒）：候选 creep **10 749 217 ns** vs 基线 **272 021 ns** → **+10 477 196 ns**。

**该窗口内 vwen35gc 的真实 top interval（由 rate 轨迹算术给出）**：

| 排名 | 组索引 | tick | creep | work_over | 前一组 work |
|---|---|---|---|---|---|
| 1 | 23 | 136→140 | **4 228 702** | 3 888 810 | **11 888 810** |
| 2 | 163 | 696→700 | **3 355 626** | 2 339 404 | **10 339 404** |
| 3 | 21 | 128→132 | 1 153 895 | 829 634 | 8 829 634 |
| 4 | 127 | 552→556 | 597 384 | 101 911 | 8 101 911 |
| 5 | 17 | 112→116 | 282 786 | 0 | 7 835 127 |

即早期损失由**两次显著组工作超时**主导（**11.889 ms 与 10.339 ms** 的组工作，对 8 ms 周期），不是零散的释放抖动。

**wire 事件关联（严格按可知证据）**：

- **vwen35gc：无法关联任何 wire 事件。** 其 `joint-wire.jsonl` 只有 `sensor/actuator/step/barrier/gps/connected`，**`diagnostic_*` 流为 0 条**（零 gc_timing、零 step/native CPU timing、零 rate_timing_probe）。因此该场早期损失**既不能归因 CPU 也不能归因 GC**——本报告不作任何此类声明。
- **ztdsk269：早期窗（tick 40..1040）内恰有 1 条 gen0 GC，pause 29 612 ns（0.0296 ms）**，对 23 900 631 ns 的 early creep 可忽略；其早期构成为 work_over 12 665 444 / release_excess 11 235 187。**测得 GC 停顿不解释该窗口。**

## 5. 归因边界与限度

- **不排他归因** OS 或飞控；**不宣称** freeze 提高或损害性能（三场结局同为 `RateUnmet`）。
- 早期损失**在两个 flag-on 场中都出现、基线不出现**（2 对 1），**提示性但非结论性**；两场早期量相差 2.2×，且与探针有无混淆。
- 准备期 `gc.collect()` = **16.492919 ms wall / 16.501333 ms CPU**，**在 anchor 前 96.344 ms 完成**（自身在计时段外），**不能解释**早期 10.48–23.63 ms 的额外 creep。
- 其他限度同前：全长总量不可比；基线唯一 gen2（tick 107572）在两 C1 场寿命之外；`diagnostic_step/native` 为慢富集 or 触发采样（只用其触发计数）；`rate_timing_probe` 自带未扣除开销；解冻成本未测；每臂 n=1 且无交替（主会话做了进程/负载前检并预约 native 资源，但单对历史场次无法控制全部宿主负载）。

## 6. 消化 OMP 测量报告

`docs/coordination/omp-c1-measurement-check-20260912.md`（针对 **v1**）五项：

| # | OMP 意见 | 处置 |
|---|---|---|
| 1 | `anchor_warmup_s=20` 错误，应 2.0 s | v2 已改；v3 用 `steady_after_ns − anchor.wall_ns = 2e9` 独立复算确认 |
| 2 | `common_window` 组数 off-by-one 且自相矛盾 | v2 已声明 start-tick 端点约定；匹配口径 **24 146 组 / 24 145 区间** |
| 3 | 窗口末 lateness 推导未注明 | v2 已改用权威 `last_group_start_lateness_ns 99977277` / `last_group_end_lateness_ns 96372932` |
| 4 | 执行源分叉（`14ed9d64` vs `c3ba9de8`） | v2 已改用已提交 `c3ba9de8` 并引用其 `analyzer_sha256` |
| 5 | step 条件采样偏置候选臂 | v2 已改用**触发计数**并披露慢富集 |
| **新** | OMP 未提出、之后发现 | **v2 仍有墙秒→tick 换算错误**（稳态起点 `anchor+2000`），v3 修正 |

## 7. 测量缺口（精确，非门限缺口）

1. 早期损失已在两个 flag-on 场中定位；分析器现已能报告该三分，**这不再是报表缺口，只是归因缺口**。
2. **vwen35gc 无任何 `diagnostic_*` 流** → 缺少用于解释早期损失的 CPU/GC 阶段诊断记录；普通 wire 事件仍可作时序关联，但不能据此推断 CPU/GC 成因。
3. ztdsk269 早期窗仅 1 条 gen0（0.0296 ms）→ 测得 GC 不解释该窗口。
4. 早期损失来自"freeze 效应 / 准备期 collect 余波 / 该区间状况"三者之一，**本组场次不可分离**。
5. **稳态效应不可复现**（−13.3% / +12.9%）。
6. 无任何 flag-on 场覆盖 tick 107572。

**不建议放宽任何门限**（`LATE_LIMIT_NS`、0.5、8 ms、4-tick、健康界限均不动）。

## 8. 下一代码 / 测量候选（由本轮证据导出，非盲重试）

**代码侧**

| ID | 状态 | 动作 |
|---|---|---|
| `phase-partition-consumers` | **本轮已交付** | `phase_partition` 精确三分已入库；下游比较应读该字段，不再自行按 tick 拼窗口 |
| `early-window-interval-export` | 建议 | 在同一分析器内增加**分类内**的 top-interval 排名（现仅全局排名），使早期主导区间可直接寻址 |

**测量侧**

| ID | 动作 | 为何是它 |
|---|---|---|
| `probe-on-flag-on-repeat` | 再跑 **1 场**带两探针的 flag-on | 现仅 ztdsk269 带探针、vwen35gc 无探针；早期 23.90 vs 10.75 ms 的 2.2× 差异与探针有无混淆 |
| `collect-without-freeze-arm` | **1 场**：同样 `gc.collect()` 但不 freeze | 唯一能把 prepare collect 与 freeze 分开的对照 |
| `early-window-native-trace` | 1 场，启 CPU timing 并在首 2 秒内对 manager 组工作本身做**工作轨迹**仪表 | 早期损失由**组工作超时**主导，现有诊断无法归因到任何内部阶段 |

**明确不再提**：同配置的盲目重复；以上每项都只隔离本轮暴露出的一处混淆变量。

## 9. 本轮未做

未运行新 native/ROS/SITL、未构建、未加载模型；未改 runtime/调度/阈值/容差；未改 runner 与 `JointRate` 门槛；未改 B 的比较器；未修改任何被分析原件；未提交 Git、未嵌套代理。
