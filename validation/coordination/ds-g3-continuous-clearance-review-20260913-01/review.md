# G3 连续清障修复：独立对抗审查

范围：`Simulator/wksim_planning/ego_scene_admission.py`、`Simulator/wksim_runtime/planner_transport_pump.py`、
`validation/test_ego_scene_admission.py`、`validation/test_planner_transport_pump.py`、
`docs/plan/102-trajectory-scene-admission-contract.md`，以及它们被读取的直接依赖
（`ego_evaluator.py`、`ego_bspline_bridge.py`、`scene_profile.py`、`ego_trajectory_adapter.py`、
`trajectory_session.py`、`planner_scene_binding.py`、`bspline_tcp_envelope.py`、
`planner_transport_receiver.py`，上游证据 `Modules/ego_planner_swarm/bspline_opt/src/uniform_bspline.cpp`）。

**只读声明：** 本审查未修改任何既有文件，未 `git add/commit/push`，未运行 native/构建/ROS/DDS/飞控/模型/UE/MATLAB，
未操作进程。唯一写入目录为本目录。未改动 issue。

---

## 0. 基线与并发核对

| 项 | 值 |
| --- | --- |
| cwd | `C:\Users\PC\Documents\odid编译\wksim` |
| 请求核对 HEAD | `72ef95d28eaa87490292e77a81b1de515d606c1e` |
| 审查开始 HEAD | `72ef95d…` |
| 审查结束 HEAD | `b1897c0b360efa75cd829c556e9922c8aec88241` |
| `f333316` 是 HEAD 祖先 | 是（`git merge-base --is-ancestor` exit 0） |
| Python | 3.13.11 |
| 5 个范围文件的工作区状态 | 全部为 ` M`（未提交），与任务描述一致 |

**并发写入事实（必须记录）：** 审查期间另一写入者推进 HEAD 两次：
`72ef95d` → `13096b5`（Record adversarial issue 26 readiness review）→ `b1897c0`（Document pinned core native load sites）。
两个提交只新增/修改 `docs/plan/75-core-no-dll-audit.md` 与
`validation/coordination/omp-26-readiness-review-20260913-01/` 下的文件，**未触碰本审查的 5 个范围文件**：
5 个文件的工作区 SHA256 在审查前后逐一相同（见 `review.json` 的 `reviewed_source_sha256`），且至今仍为未提交的 ` M`。
因此本审查的全部结论对**被审查字节**成立；若这些字节发生变化，结论需重新评估。

`docs/plan/102-planner-transport-pump-contract.md` **不在** `M` 列表中——这正是 P1 的成因（见 §3）。

---

## 1. 结论

**运行时无 P0，无运行时 P1。** 该修复在几何上可靠、保守、失败关闭，并在失败时保持适配器/会话原子性；
legacy 采样路径逐字未变；pump outcome 映射对 `admit()` 能真正抛出的每个 reason 都完整。

| 等级 | 数量 | 性质 |
| --- | --- | --- |
| P0 | 0 | — |
| P1 | 1 | **文档/合同**不一致（无运行时影响）：pump 合同文档未随 pump 代码更新 |
| P2 | 4 | 证据标签 1 项（可复现）、`intervals` 字段语义文档错误、repeated-knot 分组为死分支而文档称其生效、pump 映射静默 fallback |
| P3/信息 | 4 | 测试条数、`_aabb_gap` 舍入措辞、"clamped domain" 措辞、结构失败时 `-inf` 的 JSON 隐患 |

**批准口径：** 代码（运行时行为）可批准；合并前必须修 P1 文档（以及建议一并修 P2-1 的一行代码与 P2-2/P2-3 的文档措辞）。
本次审查只读，未替作者应用任何补丁。

---

## 2. 逐项核对结果

| 任务核对点 | 结论 | 关键证据 |
| --- | --- | --- |
| B-spline 活动控制点区间索引 | **正确** | 96 种 knot 布局上，证书 `intervals` 与独立推导的 `(u_j, u_{j+1}, j, j)` 完全逐元素相等；活动窗口 `P_{j-p}..P_j` 与上游 `evaluateDeBoor`（`uniform_bspline.cpp:67-81`）一致 |
| clamped / non-uniform / repeated knot 边界 | **数值正确，文档错误** | 严格递增布局（含 lengthenTime 形非均匀、平移域、极值间距 1e-6/50）全覆盖；真正的 clamped（端部重数 p+1）与任何重复 knot 均被拒绝 → 失败关闭；但"重复 knot 加宽活动集以保持界可靠"的分支**永不执行**（P2-3，`sys.settrace` 行覆盖证明） |
| 定义域全覆盖 | **正确** | 覆盖区间首尾 == `[u_p, u_{m-p}]`，无缝、连续，且跨度按位等于 `EgoSpline.duration`；采样门的 t=0 / t=duration 端点与之一致 |
| 控制盒 → AABB 净 clearance 公式 | **正确** | `_aabb_gap` 与精确盒盒距离最大偏差 1.35 ulp；报告的 gap 与逐区间独立重算逐位相等；`net == gap − vehicle_radius` 逐位成立 |
| 车辆半径与 required_clearance 是否重复/漏减 | **无重复、无漏减** | 经验阈值：障碍 `0.6500000000000001 m`、地图 inset `0.6499999999999999 m`，对照精确 double 和 `0.649999999999999966… m`（<1 ulp）；若重复半径为 1.00 m、若漏半径为 0.30 m，均被排除 |
| 逐轴地图 inset | **正确** | `_inset_clearance` 返回三轴带符号值，判定为"每轴 ≥ 0"；单轴 −0.65 m 侵入在跨轴均值 +4.02 m 的情况下仍被拒绝 |
| 浮点阈值语义 | **确定且不实质放宽** | 精确边界 ulp 阶梯（13 档）：被接纳的报告其精确 slack 均在 FP 噪声底；`>=` 语义明确；报告门是采样门与证书门的合取，绝不比原有采样门更宽松 |
| strict / legacy 兼容 | **兼容** | legacy 仍为 `sampled_segment_checked` / `continuous_proof=False` / `continuous_certificate=None`，且仍接纳审计 witness；同一 spline 的采样数值在两模式下逐位相同 |
| 失败时 adapter/session 原子性 | **成立** | 8 条可达拒绝路径：门 1–4 适配器调用 0 次且会话快照逐字段不变；`adapter_rejected` 仍回滚；严格拒绝不消耗 event_sequence，随后的合法帧用**同一**序号成功激活 |
| pump outcome 映射 | **代码正确、文档滞后** | 可达 8 个 reason 全部命中映射且互不混淆（`continuous_clearance_unproven → rejected_continuous` 独立于 `rejected_clearance`/`rejected_map`）；但 pump 合同文档缺该行并保留旧的诚实性声明（P1） |

---

## 3. 发现与最小补丁（建议，未应用）

### P1-DOC-PUMP-CONTRACT-STALE（文档，无运行时影响）

`docs/plan/102-planner-transport-pump-contract.md` 未随 `planner_transport_pump.py` 更新，三处与本改动直接矛盾：

1. §Outcome mapping 表（第 99–109 行）没有 `continuous_clearance_unproven → rejected_continuous` 行，
   而 pump 在**默认（strict）路径**下会产出该 outcome → 按文档实现 outcome 集合的下游消费者会遇到未处理取值。
2. §Non-claims（第 167–168 行）仍写 "claim continuous-curve or flight safety — scene clearance inherits the
   admission gate's `sampled_segment_checked` / `continuous_proof=False` honesty bound"，
   而本次改动在 `planner_transport_pump.py` 的 `NON_CLAIMS` 与 `102-trajectory-scene-admission-contract.md`
   中已把该声明改为"strict 时为连续证书、关闭时为采样检查"。
3. §Verification boundary（第 192–199 行）未列出新增的
   `test_continuous_unproven_reject_is_mapped_and_two_commit`。

**最小补丁（仅文档）：**

```diff
--- a/docs/plan/102-planner-transport-pump-contract.md
+++ b/docs/plan/102-planner-transport-pump-contract.md
@@ -106,6 +106,7 @@
 | `clearance_violation` | `rejected_clearance` | True | False |
+| `continuous_clearance_unproven` | `rejected_continuous` | True | False |
 | `map_violation` | `rejected_map` | True | False |
@@ -167,3 +168,3 @@
-- claim continuous-curve or flight safety — scene clearance inherits the admission
-  gate's `sampled_segment_checked` / `continuous_proof=False` honesty bound;
+- claim flight safety — scene clearance inherits the admission gate's honesty bound:
+  the geometric continuous-curve control-hull certificate when strict mode is on,
+  the sampled/segment check when it is off;
@@ -194,6 +195,7 @@
   and no `event_sequence` spent; bridge and identity rejections recorded;
+  a strict continuous-certificate rejection recorded as `rejected_continuous` with the
+  same two-commit boundary and no `event_sequence` spent;
```

### P2-1 EVIDENCE-LABEL-ON-REJECTED-REPORT（代码，1 行）

`ego_scene_admission.py:571` 的 `continuous_proof` 仅由 `certificate.proven` 决定，未与 `admitted` 合取。
于是 strict 模式下**未被接纳**的报告可能带 `continuous_proof=True` 与
`evidence_kind="convex_hull_span_certified"`，与本目录合同文档"`continuous_proof`（True only on a strict pass）"
及报告 docstring 相矛盾。已构造 3 个确定性反例（probe 3，2 项检查失败）：

| 场景 | 曲线 | admitted | violation | continuous_proof | evidence_kind | 精确 slack |
| --- | --- | --- | --- | --- | --- | --- |
| 障碍边界 | 常值点 `(0.0, 1.6500000000000001, 2.75)` | False | `obstacle_clearance` | **True** | `convex_hull_span_certified` | +1.67e-16 m |
| inset 边界 | 常值点 `(3.0, 3.0, 0.6499999999999999)` | False | `map_envelope` | **True** | `convex_hull_span_certified` | −5.55e-17 m |
| inset 边界 | 常值点 `(3.0, 3.0, 0.65)` | False | `map_envelope` | **True** | `convex_hull_span_certified` | +5.55e-17 m |

全部为失败关闭（未激活），且仓库内无消费者用 `continuous_proof` 做授权，故无安全影响；但标签语义与合同不符。

```diff
--- a/Simulator/wksim_planning/ego_scene_admission.py
+++ b/Simulator/wksim_planning/ego_scene_admission.py
@@ -571 +571 @@
-    continuous_proof = bool(certificate is not None and certificate.proven)
+    continuous_proof = bool(admitted and certificate is not None and certificate.proven)
```

（备选：保留代码、改文档措辞，但那样每个被拒报告仍宣称"已认证通过"，不如上式诚实。现有测试全部只在 admitted 报告上断言该标签，改动后仍全绿。）

### P2-2 INTERVALS-FIELD-SEMANTICS（文档）

`102-trajectory-scene-admission-contract.md:173-174` 把 `intervals` 每项写成
`(start_u, end_u, first_active_index, last_active_index)`，而实现写的是
`(interval_start, interval_end, index, last)`，其中 `index` 是**跨段索引 j**，不是首个活动控制点索引
（`first_active = j − p`）。按文档解读会读错控制点（3 次样条首个区间应为 `P_0..`，文档口径会读成 `P_3..`）。
仓库内测试用的是正确约定（`_points[first - 3:last + 1]`），因此仅文档有误。

```diff
-`intervals` (each `(start_u, end_u, first_active_index, last_active_index)`), `non_claims`.
+`intervals` (each `(start_u, end_u, span_index_j, last_knot_index)`; the active control
+window is `P_{j-order}..P_{last_knot_index}`, i.e. upstream `evaluateDeBoor`'s span-j set), `non_claims`.
```

### P2-3 REPEATED-KNOT-GROUPING-DORMANT（死分支 + 文档）

`ego_scene_admission.py:320-323` 与 `102-…-contract.md:150-154` 声称重复左 knot "加宽活动集，从而保持界可靠"、
零长跨段被"跳过"。实际 `386-389` 行的严格单调门槛对**任何**重复先返回 `non_monotone_knots`，
所以 `406-411` 行的分组/跳过分支是**死代码**，`c == j` 恒成立。`sys.settrace` 行覆盖证明
（probe 4）：行号 388（单调返回）/404（进入扫描）/408（跳过）/410-411（分组）/412（活动切片），
对 6 种保基数重复向量，只有 388 执行，408/410/411/412 从不执行；`interval_count=0`、`proven=False`。
行为仍失败关闭；且 `EgoSpline`/`bridge_bspline` 根本构造不出重复 knot（`ego_evaluator.py:88-90`），
评估器本身在部分重复向量上还会因 de Boor 分母为 0 抛 `SplineError`（probe 4 实测），
故"分组保持可靠"的论证不可达也无用。

最小补丁（推荐改措辞、不要放松门槛）：

```diff
-So a supplied knot vector is honoured when it is ... STRICTLY increasing ...
+... (unchanged)
-     Repeated knots therefore widen the active set, which keeps the bound sound; a
-     non-degenerate interval [u_j, u_{j+1}) gets the control box of P_{j-p}..P_c.
+     Any repeated (non-increasing) knot is rejected fail-closed as
+     ``non_monotone_knots`` BEFORE the walk, so every certified interval is a plain
+     strictly increasing span with c == j and active window P_{j-p}..P_j; the
+     grouping/degenerate-span handling below is defensive only (unreachable).
```

同时请修正 `validation/test_ego_scene_admission.py:517-523` 的 docstring 叙述
（把分组称为可由篡改触达的"纵深防御路径"与该篡改用例的实际结果相反），或直接删除死分支。

### P2-4 UNMAPPED-REASON-SILENT-FALLBACK（健壮性）

`planner_transport_pump.py:552` 用 `_ADMISSION_REASON_TO_OUTCOME.get(error.reason, "rejected_adapter")`。
`ADMISSION_REASONS` 有 12 项、映射表 8 项；未映射的 4 项（`invalid_adapter`/`invalid_binding`/`invalid_anchor`/
`invalid_spline`）经 probe 5 证实**不可经 `admit()` 到达**（构造期校验或 bridge 保证），因此今天完整；
但今后若新增 reason 而忘记加行，会被静默误标为 `rejected_adapter`，且
`102-…-contract.md:277` 的"maps every reason"只是空真。建议加入完备性测试（最小补丁）：

```python
from Simulator.wksim_planning.ego_scene_admission import ADMISSION_REASONS
...
self.assertEqual(set(ADMISSION_REASONS) - set(_ADMISSION_REASON_TO_OUTCOME),
                 {"invalid_adapter", "invalid_binding", "invalid_anchor", "invalid_spline"})
```

### P3 / 信息项

- `102-…-contract.md:312`："40 tests" 实为 **41**（15+15+11，实测 `Ran 41 tests`）。
- `ego_scene_admission.py:276-281` `_aabb_gap` docstring 称"All terms are exact real quantities; only the final
  sqrt rounds once"；实际逐轴减法、三个平方、两次加法、最后一次 `sqrt` 都会舍入（实测与精确值最大偏差 1.35 ulp），
  建议改为"a few ulp"措辞。
- 全文 "exact clamped domain" 措辞：真实 EGO 布局**不是** clamped（`uniform_bspline.cpp:29-41`），
  该域是上游 `getTimeSpan` 求值域；代码对一切可构造布局都正确，仅措辞误导。
- `violation["clearance"]` 在结构失败时为 `-inf`（`ego_scene_admission.py:362-363,564`）。当前报告只在内存中，
  无消费者序列化；若将来有证据写入者用 `json.dumps(..., allow_nan=False)`，会在此处抛错。仅备案。

---

## 4. 方法与证据（探针 ≠ 证明）

5 个纯 Python 对抗探针（固定种子、无墙钟、无网络、无 native/ROS/SITL/UE/MATLAB），共 **980 项检查，2 项检出**
（即 P2-1 的两个断言），全部可用一条命令重跑：

```powershell
python validation/coordination/ds-g3-continuous-clearance-review-20260913-01/run_probes.py
```

| 探针 | 主题 | 结果 |
| --- | --- | --- |
| `probe_1_cover_index.py` | 区间索引、覆盖完整性、clamped/非均匀/平移/极值 knot 布局、精确（Fraction）反例搜索 | 870/870 |
| `probe_2_clearance_accounting.py` | `_aabb_gap` 精确性、半径/required 是否重复或漏减、经验阈值二分、逐轴 inset | 30/30 |
| `probe_3_threshold_and_labels.py` | 边界 ulp 阶梯、严格/legacy 标签、strict bool 门槛、失败关闭 | 18/20（2 项即 P2-1） |
| `probe_4_knot_boundaries.py` | clamped 不可构造、`sys.settrace` 死分支证明、重复 knot 评估不可用、平移/非均匀覆盖 | 15/15 |
| `probe_5_atomicity_pump_outcomes.py` | 8 条拒绝路径的零变更原子性、序号不消耗、pump 默认 strict 与 recover、outcome 映射完备性 | 45/45 |

关键量化结果（详见 `review.json` 的 `measurements`）：曲线越出其所声称控制盒的最大量 **8.88e-16 m**；
`proven` 证书下唯一严格精确反例出现在 `y = nextafter(1.65)`，精确 slack **−2.78e-16 m**（约 2.5 ulp，
比 0.65 m 裕度小 15 个数量级）；`_aabb_gap` 与精确值最大偏差 **1.35 ulp**；两门经验阈值均在精确
double 和裕度 `0.649999999999999966… m` 的 1 ulp 内。

**方法边界（务必保留）：** 高密度数值扫描只用于寻找反例，**不构成证明**。本审查的正向结论来自
上表的数学论证（凸包性质、覆盖完整性、凸性推论、逐轴判定）+ 代码/上游源码逐行核对 +
反例搜索未能推翻；数值噪声底以上的"未发现反例"不等于"不可能存在反例"。

### 相关测试运行（纯 Python）

| 命令 | 结果 |
| --- | --- |
| `python -m unittest validation.test_ego_scene_admission -v` | OK，41 tests |
| `python -m unittest validation.test_planner_transport_pump -v` | OK，55 tests |
| `python -m unittest validation.test_planner_transport_receiver -v` | OK，27 tests |
| `python -m unittest validation.test_ego_bspline_bridge validation.test_ego_trajectory_adapter validation.test_trajectory_session validation.test_scene_profile validation.test_planner_scene_binding validation.test_bspline_tcp_envelope` | OK，158 tests（1 skipped） |

---

## 5. 复现与摘要

- 全部产物摘要见本目录 `SHA256SUMS`（覆盖含本文件与 `review.json` 在内的所有文件）。
- 本目录受 `.gitignore:53` 的 `/validation/*/` 规则忽略，因此 `git status` 不会显示它（与既有审查目录惯例一致）；
  这些证据是工作区本地产物，如需进入历史须由集成方显式 `git add -f`。本审查遵守"不 git add/commit/push"。
- 被审查源码工作区 SHA256 见 `review.json` 的 `reviewed_source_sha256`（例如
  `Simulator/wksim_planning/ego_scene_admission.py = 32f6c515…14dd`，
  `Simulator/wksim_runtime/planner_transport_pump.py = c650d40a…c3e3`）。
- 若上述任一源码摘要变化，本审查结论需重新评估（尤其 P2-1 的 571 行与 P2-3 的 386-411 行）。

## 6. 非声明

- 未做 native/构建/ROS/DDS/飞控/模型/UE/MATLAB，未操作进程，未改动本目录以外任何文件，未写 git。
- 不关闭 #102/#39，不主张任何飞行、动力学、跟踪误差、力/冲量、传感器或地形（Terrain15D）行为。
- 不主张"连续证明"是完备证明：证书只覆盖已提交 `ego-single-box-v1` 几何下的球体半径模型与静态 AABB 障碍；
  采样/证书的舍入容差在 1e-16 m 量级（已在 §4 量化），轨迹执行侧的动力学、跟踪与控制滞后不在本修复范围。
