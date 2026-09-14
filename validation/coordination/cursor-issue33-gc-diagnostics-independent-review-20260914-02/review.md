# #33/#84 前置 GC/倍率离线比较器 — 第二轮独立复核

日期：2026-09-14T09:54:43+09:00  
工作类别：review  
只读六个源文件与历史 review-01，未改源/refs/GitHub，未 git add/commit/push。

## 派发核验

| 项 | 值 |
| --- | --- |
| cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| branch | `main` |
| HEAD | `5370b2324672c9036d41239cb93e21fc5eb42897` |
| 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` | `git merge-base --is-ancestor` 退出码 **0** |
| 已读 | `CONTEXT-MAP.md`、`CONTEXT.md`（wksim 无本地 ADR；父级 AeroTwinSim ADR 不自动约束）、`AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`docs/coordination/short-cycle-goal.md`、GitHub `#33` 与 `#84`、历史 `validation/coordination/cursor-issue33-gc-diagnostics-independent-review-20260914-01/` |
| 本次 module / interface | 只读复核修复后的 `tools/compare_joint_gc_diagnostics.py` 及其契约测试/文档；不改 runner、区间分析器、模型或固件 |
| 独占写入 | 仅本目录 `review.md` / `review.json` / `SHA256SUMS` |
| 未跑 | native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83 |

六个对象在 HEAD 上为**未跟踪工作区文件**；本复核绑定工作区字节 SHA，不是 commit blob。复核前后 SHA 不变。

## 总评

**PASS**（离线比较器修复后切片成立；**不是** #33/#84 通过，也不是倍率门或 MIXED/G6/Full 通过）。

P1 = 0；P2 = 0；P3 = 5。  
review-01 五类 P2 均已 fail-closed：bool 时钟、负/倒序 GC 时钟、NaN/Infinity/字符串/bool 的 CPU·lost·overflow、`result.json`/source map/admission/manifest/markers 的 `[]`/字符串及 result/source/admission/manifest 的 `null`、已知场对匿名与双方空 `source_sha256`。CLI 对无效输入写稳定 JSON，不因 `allow_nan=False` 或 `AttributeError` 崩溃；退出码与 `status` 一致。  
合法边界成立：`lost=0`/`overflow=0`、零时长 GC、有限 float CPU、两个同 token `oayggl_s` 仍可比较；缺 CPU 保持 `null`。  
boot / source / 完整窗口 / latch / 诊断标记 / overflow·lost / 四已知场互配仍拒绝；`causal` 恒 `false`，`performance_pass` 恒 `false`。

GitHub 实读：`#33` **OPEN**；`#84` **OPEN**，前置仍为 `#83`。文档与 short-cycle-goal 一致：`#83` 不重跑、MIXED/G6/Full 未过、99 未过倍率门。

## 源 SHA

| 文件 | 期望 SHA256 | 实测 | 匹配 |
| --- | --- | --- | --- |
| `tools/compare_joint_gc_diagnostics.py` | `d836333025a186f6f2c7c085aff686271792cfcd4fbbda16cb7802f78c6c66e7` | 同左，64689 B / 1375 行 | 是 |
| `validation/test_compare_joint_gc_diagnostics.py` | `b53f427d05c4530600326a8068490feb9ab3a7c4729c28459c58d63338ca500d` | 同左，59273 B / 1119 行 | 是 |
| `docs/coordination/c2-gap-bounds-20260913.md` | `63431c1b3289ba6f83db4cb2434f7c5ecf00ae6095f3d701656ec1de6daf93af` | 同左，14207 B / 131 行 | 是 |
| `docs/coordination/c2-phase-correlation-20260913.md` | `a8fef46b8fad7e83aaf4d9f1e8f94eb014fb7619af3baf905ffb3610d39038da` | 同左，14198 B / 154 行 | 是 |
| `docs/plan/33-rate-measured-candidate-20260912.md` | `d02ba65adf7af9bd8883ce9b27d548b095785582b010279c5ddf0bddb9b03a50` | 同左，13417 B / 157 行 | 是 |
| `docs/plan/33-rate-next-diagnostic-20260912.md` | `4ccf92ecd25cde1e778cd6b2c2102cbc12b32160c1aa23d9eeb3c0aa04b1b358` | 同左，23881 B / 322 行 | 是 |

相对 review-01：比较器由 1131 行扩到 1375 行；正式测试由 38 项扩到 53 项，新增 `TypeStructurePairingGateTests`。

## 检查 1 — fail-closed 门 / 缺值不转 0

**PASS。**

| 门 | 实现 | 正式测试 | 本复核独立重放 |
| --- | --- | --- | --- |
| boot | UUID 才算；sidecar 可读；缺/不同 → 不兼容 | 缺 boot、不同 boot、sidecar | 缺/不同 boot → `rejected` |
| source / `source_unchanged` | 须可验证非空 map 且 `is True` | SHA 不同、flag=false、空 map | 空 map / `null` map → `source:unverifiable_or_empty`；flag 缺或 false 拒绝 |
| 时间窗 | `_clock_ns` 排除 bool；倒序窗口 `unavailable` | bool wall/issued、缺 anchor | `wall_ns=True/False`、`issued_monotonic_ns=True`、float wall → `invalid_clock`，非 `compared` |
| latch | 复用区间分析器；缺 latch=`unavailable`/`null` | 无 latch、负残差 | 无 latch 拒绝；缺 `actual_end_ns` 由分析器 `ValueError` 拒绝，无崩溃 |
| 诊断标记 | 无 GC 行 → `missing_diagnostic_marks`；代价字段 `null` | 无 GC、无 wire | 空 wire：`samples=0` 且 max/sum=`null`，拒绝 |
| overflow / lost | `True`/正整数打中；非负整数 0 干净；其它类型 `*_invalid_type` | lost=3、Infinity、`"3"`、bool | Infinity/`"3"`/`False`/`True`/`-1`/`overflow="1"` 均拒绝 |
| 身份 | 单场混 epoch 拒绝；已知场互配拒绝 | 混身份、四场互配 | 四对已知场互配拒绝；`oayggl_s` 对 `run-a` 拒绝 |

`_gc_ledger` 空可用行把 sum/max 写成 `None`；`deltas` 任一侧 `None` 则 `delta_ns=None`。缺测不填 0。

## 检查 2 — 四个已公布场不得误配

**PASS。**

`KNOWN_FIELD_CONDITIONS` 仍钉：`oayggl_s` 无探针 99、`x39qjvkw` 有探针 99、`5lfbcy43` 有探针 50、`rfw9nmbb` 带 `group_work_timing`。两边都识别且条件表不等 → `known_field_compatible=false`。一边识别一边匿名 → `known_field_vs_anonymous` 拒绝（review-01 P2-5 已关）。两个相同 token 在其它门满足时可配对。

## 检查 3 — descriptive / controlled_pairing / causal=false

**PASS。**

`claim_class` 初值 `descriptive=true`、`controlled_pairing=false`、`causal=false`。只有 `status=compared` 且非 `--self-check` 才把 `controlled_pairing` 置真；`causal` 从不置真。`performance_pass` 恒 false。TEMP 全部 68 例 `causal=false`、`performance_pass=false`。

## 检查 4 — 边界输入、CLI 稳定、测试独立性

**PASS。**

正式套件现含 15 项类型/结构/pairing 回归，覆盖 review-01 五类 P2 与合法边界（`lost=0`、零时长 GC、两 `oayggl_s`）。不是只复述常量。

CLI：`compare()` 与 `json.dumps(..., allow_nan=False)` 均有收口（1311–1371）。NaN CPU → 退出码 1、`status=rejected`、JSON 可再 `allow_nan=False` 序列化。`result.json=[]` → 退出码 1、`unavailable`、`result_not_object:list`，无 `AttributeError`。合法配对退出码 0 且 `status=compared`。

独立重放 review-01 五类 P2（均已关闭）：

| 编号 | 构造 | 结果 |
| --- | --- | --- |
| p2-bool-wall / issued | `wall_ns=True`；`issued_monotonic_ns=True` | `rejected` / `invalid_clock` |
| p2-reversed-gc | GC `start>end` | `rejected` / `timebase_inconsistent`，`unclassified_reversed_interval` |
| p2-negative-gc | 负 GC 时钟 | `rejected` / `invalid_clock`，`unclassified_invalid_clock` |
| p2-nan-cpu | `thread_cpu_ns=NaN` | `rejected` / `invalid_cost`；CLI 稳定 JSON，退出码 1 |
| p2-lost-inf / string / bool | `lost=Infinity` / `"3"` / `False` | `rejected` / `overflow_or_lost` |
| p2-result-array | `result.json=[]` | `unavailable` / `TypeError`，无 `AttributeError` |
| p2-source/admission/manifest/markers [] 或字符串 | 非 object | `unavailable` / `*_not_object` |
| p2-source-null / manifest-null | JSON `null` | `_optional_object` 收成空 map 后身份拒绝 |
| p2-named-vs-anon | `oayggl_s` vs `run-a` | `rejected` / `known_field_vs_anonymous` |
| p2-empty-source-maps | 双方 `{}` | `rejected` / `source:unverifiable_or_empty` |

合法边界（均为 `compared`，`causal=false`）：`lost=0`、`overflow=0`、零时长 GC、CPU=`24.5`、两个 `oayggl_s`、缺 `thread_cpu_ns` 时 max/sum=`null`。

TEMP 额外负例/边界 ≥12（本轮共 68 例，其中额外族 27+）：`wall_ns=False`、`lost=True`、`overflow="1"`、CPU Infinity/−Infinity/bool/字符串、`lost=-1`、`result.json=null`/字符串、重复 anchor、空 rate/空 wire、缺目录、`result.json` 是目录、组 end&lt;start、`markers.lost_samples=True`、float `wall_ns`、Infinity GC 时钟、bool 组时钟、rate 行是数组、`pre-run-identity.json=[]`、缺 `actual_end_ns`、`identities=[]`、双方缺 async、双方嵌套 `reports_dropped=2`。0 次未捕获异常。

## 检查 5 — 文档与 #83 / MIXED / G6 / Full / 99

**PASS**（主边界一致；可选 `null` 的措辞见 P3）。

四份文档 2026-09-14 边界段一致：

- **#83 不重跑**：`1w6dru32` PV 已 CLOSED；诊断包与 C2 分析不得触发或替代重跑。
- **MIXED / G6 / Full 未通过**；`#84` 仍开放。
- **99 未过倍率门**：最新无探针场 `oayggl_s` 为 `RateUnmet`，停止重复 99，不做因果归因。
- 四个已公布场不得受控配对；比较器只做离线解析。
- 类型/结构/pairing 门与当前实现的 fail-closed 路径一致；`causal` 恒 false，`performance_pass` 恒 false，缺量为 `null`。
- 下一 native 场仅主会话；本切片未跑 native/flight/#83。

`#33` 父票 AC 未勾；`#84` 完成条件未勾。本比较器不能关闭这两票。

## 正式测试

```text
python -B -m unittest validation.test_compare_joint_gc_diagnostics
```

**53/53 OK**，约 2.411 s。未 skip。真实 `manager_gc_candidate.py` 钉 SHA `cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66` 可达。

## 额外 TEMP 负例（已精确删除）

根目录：`C:\Users\PC\AppData\Local\Temp\wksim-i33-gc-rev02-en4f68hv`。探针脚本 `C:\Users\PC\AppData\Local\Temp\wksim-i33-gc-rev02-probe.py`。事后 `wksim-i33-gc-rev02-*` 为空。未把夹具写入仓库。

## 发现

### P1

无。未宣称 `#33/#84` 通过，未重跑 `#83`，未把 `causal` 置真，未把缺 latch/缺 GC 填 0，未把四个已公布场互相标成受控配对，未启动 native/ROS/SITL/UE。

### P2

无。review-01 五类 P2 独立重放全部 fail-closed；CLI 不再因 `allow_nan=False`/`AttributeError` 崩溃。不得再出现 PASS 同时 P2&gt;0，本轮满足。

### P3

1. **可选 object 的 JSON `null` 被收成 `{}`。** `_optional_object`（142–145）与 `read_result` 对 `markers`/`source_sha256`/`manifest_sha256`（364–366）把 `null` 当成缺省空对象。`markers=null` 仍可 `compared`+`controlled_pairing=true`（与合法空 `{}` 同路径）。`[]`/字符串仍 `unavailable`；`source_sha256=null`/`manifest_sha256=null` 仍因空 map 身份拒绝。文档/claim_limits（1208）把 optional `null` 写成一律 `unavailable`/`rejected`，比实现更严。
2. **`group_work_timing.reports_dropped` 仍不进 integrity。** `scan_integrity`（238–269）只扫 jsonl 行、result 顶层与 `markers`。双方都带 `group_work_timing={"reports_dropped":2}` 时 `integrity=clean` 且可 `compared`。单侧仍会被 mark 不匹配拒绝。与 review-01 P3-3 同族，本轮补了双侧实证。
3. **空 `rate.jsonl` 仍报 `mixed_identity_inside_one_field`。** `scan_rate`（641–642）+ `analyse_field`（947–950）：0 个 identity tuple 被当成混身份。仍拒绝，理由不准。
4. **双方缺 `async_model_evidence_requested` 仍可配对**（`compare_identity` 1049–1053、1138–1139）；`pre_run` 的 `manager_target` 不参与身份比较。
5. **畸形 `pre-run-identity.json=[]` 不阻断比较。** `analyse_field`（927–940）记下 `pre_run_identity_unreadable` 后若 result 已有 boot 仍可 `compared`。sidecar 本可选，但字段 reasons 未提升到 compare 拒绝。

## 未决边界

- `#33` / `#84` 仍 OPEN；本工具不能代替正式入口或公共任务。
- `#83` 保持 CLOSED，不重跑。
- MIXED / G6 / Full 证据集仍未通过；99 保持 `oayggl_s` / `RateUnmet`。
- `compared` 只表示两份保留记录在比较器合同下可并列，不是性能通过，也不是因果。
- 未改六个源文件，未 git add/commit/push。

## 结论

修复后的离线比较器作为 #33/#84 前置诊断工具：**PASS**。review-01 五类 P2 已关闭；剩余为 P3，不升级为本切片 FAIL，也不解锁父票。
