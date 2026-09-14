# C2 大慢组的“传感器到执行器不足以解释”边界定位 — 2026-09-13

独立只读流水时序分析。未启动 native/模型/ROS/构建，未做嵌套委派，未用 Git，未改动 OMP、runner、runtime 或任何现有分析器。
唯一新增：`validation/coordination/c2-gap-bounds-20260913/`（脚本 + 结果）与本文件。
实际运行（raw）：`/root/wksim-release-acceptance-fe3/validation/joint-public-flight-lcgv0yte`。

## 当前结论边界（2026-09-14）

本文件只描述历史 C2 场 `lcgv0yte` 的可证明区间；**不是** MIXED / G6 / Full 通过，也**不是**倍率门通过。

- **#83 不重跑**：`1w6dru32` PV 已通过并 CLOSED；本分析不得触发、建议或替代 #83 重跑。
- **MIXED / G6 / Full 未通过**；正式 mixed 证据集仍为空。
- **99 不满足倍率门**：最新无探针场 `oayggl_s` 为 `RateUnmet`，停止重复 99 配置。
- **下一 native 场仅主会话执行**。比较器 `tools/compare_joint_gc_diagnostics.py` 只做离线解析。
- **不得误配**：`oayggl_s`（无探针 manager99）、`x39qjvkw`（有探针 manager99）、`5lfbcy43`（有探针 manager50，不同 boot）、`rfw9nmbb`（带 `group_work_timing` 的 MIXED 诊断）条件不同。不同 boot / 不同源码 / 缺完整窗口 / 缺失诊断标记 / overflow·lost / 时基或身份不一致一律拒绝受控配对；下列 C2 数字只是描述性并列，**不是因果**。
- **比较器类型门**：`wall_ns` / `issued_monotonic_ns` / GC 起止 / 窗口起止 / lost·overflow·count·marker 必须是非负 `int`，显式拒绝 `bool`；GC `end < start`、负时钟、倒序窗口 fail closed，不得进入 `compared`。CPU/代价/比例/持续时间必须是有限数，拒绝 `NaN` / `Infinity` / `-Infinity` / 字符串 / `bool`；输出不依赖 JSON `allow_nan`。
- **比较器结构门**：`result.json`、source map、admission/manifest/markers 等必须先是 object；`[]` / `null` / 字符串稳定返回 `unavailable`/`rejected` 和明确理由，不得抛 `AttributeError`。
- **pairing 身份**：已知场不得与匿名 run 配对；双方 `source_sha256` 为空不得 `controlled_pairing`。只有可验证的非空、相容来源身份和完整条件表才允许受控配对。四个已知场互配仍拒绝；两个相同 token（如两个 `oayggl_s`）在其它门满足时可配对。`causal` 恒 false，`performance_pass` 恒 false，缺量为 `null`。

## 1. 结论速览

- 用同场程序顺序（`rate_group_start` 先于该组首条 wire 记录、末条 wire 记录先于 `rate_group_end`）可以把两条进程内时钟的**共同 offset** `S` 证明性地夹在
  **`[36 828 936 893, 36 829 347 824] ns`**（宽 **410 931 ns ≈ 0.411 ms**），交集**非空**；18 292 个组全部参与、0 个跳过，回验 0 条约束冲突。
- 前 8 大 creep 组中，判为“**sensor→actuator 不足以解释工作耗时**”的是 **2772、38528、38520、38564** 四组。对这四组，可证明地把主要耗时定位到 **sensor 之前的区域**（组边界 release 边沿→首条 sensor 记录，以及相邻 tick 的 step→sensor 段），而不是 native 输入段：
  - **2772**：最大单段是**精确**的 8.320 ms `step@2775 → sensor@2776`（无需 offset）；native 并集只有 3.096 ms。
  - **38528**：组边界 pre-sensor **可证明 ≥ 5.301 ms**（区间 [5.301, 5.712] ms），占 12.531 ms 工作的 ≥42%；native 并集 2.218 ms。
  - **38520**：组边界 pre-sensor **可证明 ≥ 3.607 ms**（区间 [3.607, 4.018] ms）；native 并集 2.485 ms。
  - **38564**：组边界 pre-sensor **可证明 ≥ 2.565 ms**（区间 [2.565, 2.976] ms）；native 并集 1.480 ms。
- 其余四组（2764、2928、43840、1996）不属于此类：它们的 work 主要由 **native sensor→actuator** 段解释（并集 16.827 / 12.131 / 9.012 / 7.703 ms）。

## 2. 输入与 SHA256

| 文件 | SHA256 |
|---|---|
| `.../joint-public-flight-lcgv0yte/rate.jsonl` | `a1fe39d4aed3450e87975e1717f70c641427429ca6b628651b415f90e5afb13f` |
| `.../joint-public-flight-lcgv0yte/joint-wire.jsonl` | `0eb097211ba18b2bc6aa7251b38fe03dffcd3b8a6e47fcd54c4c372db1bd0a3a` |
| `.../joint-public-flight-lcgv0yte/source__tools__run_joint_flight.py.txt` | `c208b1d07a9054458e13b3f7bf74c145cb8641ec495e46fc7df5b6fb1626e408` |
| `.../joint-public-flight-lcgv0yte/source__Simulator__wksim_core__joint.py.txt` | `f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50` |
| `.../33-final-combo-c2-20260913-01/main-rate-analysis.json` | `26827386d4a432e9121106f47ea59eb11a9aa88374476e632f0256bacf4e2cbc` |
| 本报告脚本 `analyze_gap_bounds.py` | `459dc44e67f9a8bb9529fbb978d085db01e7ba1c7b3397721375ffea964971da` |
| 本报告结果 `result.json` | `a5375471423929c53ef4f6f7cd67c1d8b3f8a3369fe7805ae1f3ad1efc7580a2` |

**provenance 校验**：`rate.jsonl` 的 SHA 等于 `main-rate-analysis.json` 的 `trace_sha256`（同一条 trace）。

> **来源说明（2026-09-13 更正）**：本报告初版曾写“……`analyzer_sha256=1c43ac9c…` 与当前磁盘分析器 `14ed9d64…` 不一致”。核实后更正：`14ed9d64…` 只是 WSL 私有目录里的旧副本；产生 `main-rate-analysis.json` 的是主 Windows 仓库 `tools/analyze_joint_rate_intervals.py`，其 SHA 正是 **`1c43ac9c4b80f2dcc8eb52ffd9c3fe061f5cd2ef9206d839fe20e7af2f783fc7`**，与记录一致——**来源链明确，并非未知执行源**。本次分析仍独立从 `rate.jsonl` 重建分组（前 8 组起始 tick 与既有分析完全一致，`matches_prior=true`），未改动其余冻结结果。

## 3. 共同 offset 的上下界（可证明的推导）

两条时钟同属 runner 进程：`record()` 写 `wall = time.monotonic() - started`，`JointRate` 写 `actual_start_ns/actual_end_ns = time.monotonic_ns()`。因此存在唯一 `S`（= `started` 的 ns 值）使
`wire_绝对ns(event) = S + round(wall_seconds·1e9)`。

由 `source__Simulator__wksim_core__joint.py.txt` 的 `JointPhysics.advance()` 与 runner 的 `advance()` 可确定程序顺序：
`rate_group_start` →（该组 4 个 tick 的全部 wire 记录：`sensor`→`actuator`（macro tick 还有 `sensor[px4]`/`gps`/`barrier`）→`step`）→ `rate_group_end`。
另由 `scene_clock.begin_step/commit` 得：**rate 组起始 `start_tick=P` 拥有 wire tick `P+1..P+4`**（本次实证成立）。

于是对每个组 g：`S > A_g − w_首·1e9` 且 `S < B_g − w_末·1e9`。对所有组求交：

- **下界** `S_lo = 36 828 936 893 ns`（由组 **19328** 给出）
- **上界** `S_hi = 36 829 347 824 ns`（由组 **26148** 给出）
- **宽度** `W = 410 931 ns`，交集非空
- 参与组 18 292，跳过 0，**回验冲突 0**（对全部组内 wire 事件重算，均与 `[S_lo,S_hi]` 相容）

**为什么宽度不能再小**：`W = min_g(pre_sensor_g) + min_g(post_step_g)`，即全场“最好的一个 release→首 sensor 段”与“最好的一个末 step→release 段”之和。仅凭程序顺序无法再把两者分开——**不编造 offset**，只给区间。

**映射反控**（`result.json.mapping_control`）：只有 `P+1..P+4` 使交集非空（宽 410 931 ns）；`P..P+3` 与 `P+2..P+5` 都会把窗口外的记录混进来，交集分别塌缩为 −8 131 810 ns 与 −7 055 061 ns（空）。这同时独立佐证了“rate 组起始 `P` 拥有 wire tick `P+1..P+4`”。

**浮点与精度**：`wall_seconds` 是 float64 单调差分的 JSON 十进制（表示误差 ≈1e-5 ns），十进制→整数 ns 误差 ≤0.5 ns；两者相对 410 931 ns 的 slack 可忽略。**本报告不据此宣称纳秒级精度**，结论一律按 ms 表述。

## 4. 前 8 大组分解（单位 ms）

`interior = 末条 wire 记录 − 首条 wire 记录`（**精确**，与 S 无关）；`R = work − interior = pre_sensor + post_step`（**精确**）；pre/post 用一个自由度 `S` 互补拆分。native 并集 = 各组内 `sensor→actuator` 区间的**并集**（macro tick 上 AP/PX4 区间重叠，故只取并集，不把两栈相加）。

| 组(P) | work | interior | R | pre-sensor 区间 | post-step 区间 | native 并集(占比) | interior−native | 最大单段（类别） |
|---:|---:|---:|---:|---|---|---:|---:|---:|
| 2764 | 22.689 | 21.363 | 1.326 | [0.763, 1.174] | [0.152, 0.563] | 16.827 (74%) | 4.536 | 15.596 s→a[AP]@2766 |
| 2928 | 17.347 | 16.141 | 1.207 | [0.681, 1.092] | [0.114, 0.525] | 12.131 (70%) | 4.010 | 11.134 s→a[AP]@2930 |
| **2772** | 14.505 | 13.414 | 1.091 | [0.535, 0.946] | [0.145, 0.556] | **3.096 (21%)** | 10.318 | **8.320 step@2775→sensor@2776** |
| **38528** | 12.531 | 6.737 | 5.794 | **[5.301, 5.712]** | [0.082, 0.493] | **2.218 (18%)** | 4.520 | 2.038 step@38530→sensor@38531 |
| 43840 | 12.263 | 11.356 | 0.908 | [0.400, 0.811] | [0.096, 0.507] | 9.012 (73%) | 2.344 | 8.243 APact→PX4act@43844 |
| **38520** | 11.009 | 6.759 | 4.249 | **[3.607, 4.018]** | [0.231, 0.642] | **2.485 (23%)** | 4.275 | 1.496 step@38523→sensor@38524 |
| 1996 | 10.542 | 9.587 | 0.954 | [0.457, 0.867] | [0.087, 0.498] | 7.703 (73%) | 1.884 | 7.034 APact→PX4act@2000 |
| **38564** | 9.585 | 6.547 | 3.038 | **[2.565, 2.976]** | [0.061, 0.472] | **1.480 (15%)** | 5.068 | 2.274 step@38566→sensor@38567 |

（“APact→PX4act”是 macro tick 上 AP 执行器记录到 PX4 执行器记录之间的段，落在 PX4 的 `sensor→actuator` 宽区间内，属 native 等待的一部分。）

## 5. “sensor→actuator 不足”四组的可支持结论

这四组 native 并集只占 work 的 15%–23%，**组内最大单次 `sensor→actuator` 也只有 work 的 5%–12%**（其余四组为 64%–69%），且最大单段不是最大的 `sensor→actuator`，而是 **sensor 之前的段**：

- **2772**：最大单段 8.320 ms 是 `step@2775 → sensor@2776`，**wire 精确值**（同一条时钟内的差，无需 offset）。它属于下一 tick 的 sensor 前区间（模型 RPC / supervisor 循环在 sensor 记录之前）。native 仅 3.096 ms。→ **定位到 sensor 前，且该段本身是精确可举证的**。
- **38528**：组边界 pre-sensor（release 边沿→首条 sensor）**可证明 ≥ 5.301 ms、≤ 5.712 ms**；此外 interior 内 4.520 ms 非 native，前三段均为 step→sensor（2.038 / 1.256 / 1.134 ms）。native 2.218 ms。→ **定位到 sensor 前（组边界 + tick 间）**。
- **38520**：组边界 pre-sensor **≥ 3.607 ms、≤ 4.018 ms**；interior 内非 native 4.275 ms（前三段 step→sensor：1.496 / 1.448 / 1.208 ms）；native 2.485 ms。→ **定位到 sensor 前**。
- **38564**：组边界 pre-sensor **≥ 2.565 ms、≤ 2.976 ms**；interior 内非 native 5.068 ms（前两段 step→sensor：2.274 / 1.865 ms）；native 1.480 ms。→ **定位到 sensor 前**。

对照组（不属于本类）：2764、2928 由 AP 的单次大 `sensor→actuator`（15.596 / 11.134 ms）解释；43840、1996 由 macro tick 上 PX4 的 `sensor→actuator`（8.410 / 7.205 ms）解释。

## 6. 手算正/反例与 8 组输出一致性

脚本内置三组可手算用例（`result.json.self_tests`，全部通过）：

- **正例** `positive_recovers_true_offset`：取真值 `S=36e9`，构造两个窗口并求交，得 `[35 999 500 000, 36 000 500 000]`，含真值 ✓。
- **反例** `negative_empty_intersection`：追加一个“end 早于其事件”的窗口，交集塌缩为 `S_lo > S_hi`（36 000 000 000 > 35 999 999 999），被显式判为不成立 ✓。
- **边界** `edge_min_max_binding`：`A=1000, B=5000, walls=2 ns, 4 ns → [998, 4996]` ✓。

**实际 8 组一致性**（`result.json.group_consistency`，全部为真）：对每组 `pre_lo ≤ pre_hi`、`post_lo ≤ post_hi`、`pre_lo + post_hi = R`、`pre_hi + post_lo = R`、`R = work − interior`、且 pre/post 区间宽度都等于同一个 `W`。

**手工核对样例（组 38528，可逐位复算）**：
`A=164407712883`，`B=164420244083`，`work=12 531 200`；`w_首=127 584 076 731`，`w_末=127 590 814 129`。
`LO=A−w_首=36 823 636 152`；`HI=B−w_末=36 829 429 954`；`interior=6 737 398`；`R=5 793 802`。
`pre_lo=S_lo−LO=5 300 741`；`pre_hi=S_hi−LO=5 711 672`；`post_lo=HI−S_hi=82 130`；`post_hi=HI−S_lo=493 061`；`pre_lo+post_hi=5 793 802=R` ✓。

## 7. 只能支持到哪一步 / 限制

- 仅用同场**相对 wire 时间戳**与**程序顺序**；**未把任何 tick 换算成墙秒**，time 值只来自两条时钟的 ns。
- **不给虚假纳秒精度**：区间端点按 ns 列出，但真实不确定度是 410 931 ns 的 program-order slack（≫ 表示误差）。结论按 ms 表述。
- **pre 与 post 是同一自由度的两种视角**：其和 `R` 精确，二者**相关**；不同组的 `W` 也是同一 `S` 的同一个 slack，**不得跨组相加**，也**不得把二者当作独立误差**来闭合。
- **区间重叠不相加**：macro tick 上 AP/PX4 的 `sensor→actuator` 区间重叠，本报告只取**并集**（`native 并集`）；`arducopter_total`/`px4_total` 两列不可相加。
- interior 各段是 wire 精确差，但每段仍混有记录/序列化/I-O 等待/可能的调度延迟；**不是**纯 CPU、纯网络或纯飞控时长，**不作排他归因**。
- 本场**无 CPU/队列探针**（wire 中无任何 `diagnostic_*` kind，仅 `sensor/actuator/step/barrier/gps/connected`），因此**无法区分“进程在运行”与“进程在等待”**。38528/38520/38564 组边界那 2.6–5.3 ms 的 pre-sensor 段，**只能证明它落在该区域**，不能证明它由 CPU 争用、模型 RPC 还是调度延迟单独造成。
- 未启动新 native 场，`performance_pass=false`；本分析不改动任何现有实现或分析器。

## 8. 复现

```
python3 -u validation/coordination/c2-gap-bounds-20260913/analyze_gap_bounds.py \
  --raw /root/wksim-release-acceptance-fe3/validation/joint-public-flight-lcgv0yte \
  --rate-analysis /root/wksim-release-acceptance-fe3/validation/33-final-combo-c2-20260913-01/main-rate-analysis.json \
  --output validation/coordination/c2-gap-bounds-20260913/result.json
```

完整逐事件邻域、逐段 gap、native 分栈明细、自测与 provenance 见 `result.json`。
