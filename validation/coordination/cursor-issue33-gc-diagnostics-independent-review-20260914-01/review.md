# #33/#84 前置 GC/倍率离线比较器 — 独立复核

日期：2026-09-14T09:35:26+09:00  
工作类别：new-development independent review  
只读六个源文件，未改源/refs/GitHub，未 git add/commit/push。

## 派发核验

| 项 | 值 |
| --- | --- |
| cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| branch | `main` |
| HEAD | `5370b2324672c9036d41239cb93e21fc5eb42897` |
| 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` | `git merge-base --is-ancestor` 退出码 **0** |
| 已读 | `AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`CONTEXT.md`、`docs/coordination/short-cycle-goal.md`、GitHub `#33` 与 `#84` |
| 本次 module / interface | 只读复核 `tools/compare_joint_gc_diagnostics.py` 离线比较器及其契约测试/文档；不改 runner、区间分析器、模型或固件 |
| 独占写入 | 仅本目录 `review.md` / `review.json` / `SHA256SUMS` |
| 未跑 | native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83 |

六个对象在 HEAD 上为**未跟踪工作区文件**；本复核绑定工作区字节 SHA，不是 commit blob。复核前后 SHA 不变。

## 总评

**PASS**（离线比较器切片成立；**不是** #33/#84 通过，也不是倍率门或 MIXED/G6/Full 通过）。

P1 = 0；P2 = 5；P3 = 4。  
主路径门（boot / source / `source_unchanged` / 完整窗口 / latch / 诊断标记 / overflow·lost=True 或正整数 / 身份）对正式夹具 fail-closed，缺值保持 `null` 不填 0，`causal` 恒 `false`，`performance_pass` 恒 `false`。  
四个已公布场 `oayggl_s` / `x39qjvkw` / `5lfbcy43` / `rfw9nmbb` 互配被拒绝。  
检查 1 与检查 4 为 **PARTIAL**：TEMP 额外负例证明 bool 时钟、乱序 GC 区间、`NaN`/`Infinity`/`"3"` lost 仍可走到 `compared`+`controlled_pairing=true`；`result.json=[]` 抛 `AttributeError` 而不是 `unavailable`。

GitHub 实读：`#33` **OPEN**；`#84` **OPEN**，前置仍为 `#83`。文档与 short-cycle-goal 一致：`#83` 不重跑、MIXED/G6/Full 未过、99 未过倍率门。

## 源 SHA

| 文件 | 期望 SHA256 | 实测 | 匹配 |
| --- | --- | --- | --- |
| `tools/compare_joint_gc_diagnostics.py` | `c3ef5ef5603f924d618ab93c15e786941cf666b5314471018e2314d7c7e2949d` | 同左，54046 B / 1131 行 | 是 |
| `validation/test_compare_joint_gc_diagnostics.py` | `d635d410eb1d73699ba2c6ea08f3b353fb0f829bb3e74c4aa031950e1210e2c1` | 同左，48896 B / 916 行 | 是 |
| `docs/coordination/c2-gap-bounds-20260913.md` | `f23d8e16fb7511f0996f3920309d27019d3544cab95ea1c6f1e59f85fcc59efc` | 同左，13199 B / 128 行 | 是 |
| `docs/coordination/c2-phase-correlation-20260913.md` | `11dfba6e9ed5fa3a4c087cb40330def2a6426033c9a17de242b90d6b90e8675e` | 同左，13574 B / 151 行 | 是 |
| `docs/plan/33-rate-measured-candidate-20260912.md` | `1be6b97bffc362bc29c33b464fbdfc72e243e99c5c81d3da191d8fb71b1b9d86` | 同左，12727 B / 155 行 | 是 |
| `docs/plan/33-rate-next-diagnostic-20260912.md` | `f8657d39a2f2a0c0894373c559ab3c3a2e4e915fb039598f3ee9aa804cb102ce` | 同左，23557 B / 321 行 | 是 |

## 检查 1 — fail-closed 门 / 缺值不转 0

**PARTIAL**（主门成立；类型/畸形值见 P2）。

| 门 | 实现 | 正式测试 | 本复核额外负例 |
| --- | --- | --- | --- |
| boot | UUID 才算；sidecar 可读；缺/不同 → 不兼容 | 缺 boot、不同 boot、sidecar | 未再扩 |
| source / `source_unchanged` | 须 `is True`；SHA 不一致拒绝 | SHA 不同、flag=false | 缺字段 → `None!=True` 拒绝；**双方空 map 仍 compared** |
| 时间窗 | `timed_bounds.observed` + `monotonic_ns` + latch `reconciled` | 无 anchor、无时钟 | 重复 anchor 拒绝；**bool `wall_ns`/`issued_monotonic_ns` 仍 observed** |
| latch | 复用区间分析器；缺 latch=`unavailable`/`null` | 无 latch、负残差 | 组 end&lt;start → 分析器拒绝 |
| 诊断标记 | 无 GC 行 → `missing_diagnostic_marks`；代价字段 `null` | 无 GC、无 wire | 空 wire：`samples=0` 且 max/sum=`null`，拒绝 |
| overflow / lost | `True` 或正整数才打中 | wire `lost=3` | `markers.lost_samples=True` 拒绝；**`Infinity`/`"3"` 未打中** |
| 身份 | 单场混 epoch 拒绝；manifest/profile/async/probe/CPU/group_work | 混身份、manifest、profile、async | 空 rate 被标成 `mixed_identity`（理由偏了，但仍拒绝） |

`_gc_ledger` 空行把 sum/max 写成 `None`；`deltas` 任一侧 `None` 则 `delta_ns=None`。这不是把缺测填 0。  
`_positive_int`/`_nonnegative_int` 排除 bool；`activation.moment_monotonic_ns` 与 `freeze_count_after` 也排除 bool。`scan_rate` / `_classify_window` 用 `isinstance(..., int)`，**不排除 bool**。

## 检查 2 — 四个已公布场不得误配

**PASS。**

`KNOWN_FIELD_CONDITIONS` 钉死：`oayggl_s` 无探针 99、`x39qjvkw` 有探针 99、`5lfbcy43` 有探针 50、`rfw9nmbb` 带 `group_work_timing`。两边都识别到 token 且条件表不等 → `known_field_compatible=false` → 拒绝、无 deltas、`causal=false`。正式测试覆盖四对互配。`group_work_timing` 与无探针场也不配对。

缺口（P2）：只有**两边都识别到 token** 才查条件表。`joint-public-flight-oayggl_s` 对无名 `run-a` 在其它门相同时可 `compared`。条件表里的 `manager_target` 也不对照 `pre_run_identity`。

## 检查 3 — descriptive / controlled_pairing / causal=false

**PASS。**

`claim_class` 初值 `descriptive=true`、`controlled_pairing=false`、`causal=false`。只有 `status=compared` 且非 `--self-check` 才把 `controlled_pairing` 置真；`causal` 从不置真。任一拒绝/不可用路径都写回 `controlled_pairing=false` 且不产出 `deltas`。`performance_pass` 恒 false。嵌套证据自带 limitation：只说明区间包含，不说明谁引起 wait。文档写明单样本/delta 不是因果。

sanity 正例：`compared` + `controlled_pairing=true` + `causal=false`。self-check 因无候选报告而为 `unavailable`，不会冒充 candidate。

## 检查 4 — 边界输入与测试独立性

**PARTIAL**（正式正负例独立且够用；类型族靠 TEMP 才暴露）。

正式套件自造 gzip 场、真实 `ManagerGCFreeze`+`FakeGC` 报告、混身份、无 latch、负残差、无 GC、无 wire、manifest/profile/async/boot/source、四场误配、result/旁文件不一致、freeze_count 对象语义。不是只复述常量。

TEMP 额外负例（≥4，已精确删除）：

| 编号 | 构造 | 结果 |
| --- | --- | --- |
| sanity | 合法配对 | `compared`，`causal=false` |
| neg1 | `rate_anchor.wall_ns=True` | **仍 `compared`**，`timed_start=true`（P2） |
| neg2 | `issued_monotonic_ns=True` | **仍 `compared`**，GC 被赶到 post，`timed_sum=null`（P2） |
| neg3 | GC `start>end` 且落在窗内 | **仍 `compared`**，算进 timed（P2） |
| neg4 | `thread_cpu_ns=NaN` | `compare()` 仍 compared；CLI `allow_nan=False` 崩溃（P2） |
| neg5 / neg6 | `lost=Infinity` / `lost="3"` | **仍 `compared`**，integrity=clean（P2） |
| neg7 | 空 rate | `rejected` / `mixed_identity_inside_one_field` |
| neg8 | 空 wire | `rejected` / 缺诊断标记；max/sum=`null` |
| neg9 | `result.json=[]` | **`AttributeError`**（P2） |
| neg10 | 两个 `rate_anchor` | `rejected` / 窗口不完整 |
| neg11 | 缺 `actual_end_ns` | `rejected` / `KeyError` |
| neg12 / neg13 | 目录不存在；`result.json` 是目录 | `unavailable` / `missing_input` |
| neg14 | `oayggl_s` vs `run-a` | **仍 `compared`**（P2） |
| neg15 | 双方空 `source_sha256` | **仍 `compared`**（P2） |
| neg16 | `group_work_timing.reports_dropped=2` | 因 mark 不匹配拒绝；嵌套 dropped **未**进 integrity |
| neg17 | 负 GC 时钟 | **仍 `compared`**，划进 preparation（P2） |
| neg18 | Infinity 时钟 | `rejected` / `timebase_inconsistent` |
| neg19 / neg20 | bool freeze_count / activation | `rejected`（合同侧挡 bool） |
| neg21 | 缺 `source_unchanged` | `rejected` |
| neg22 | 双方缺 async | **仍 `compared`**（P3） |
| neg23 | 组 end&lt;start | 区间分析器拒绝 |
| neg24 | `markers.lost_samples=True` | `rejected` / overflow_or_lost |
| neg25 | 两个 `oayggl_s` token | `compared`（同条件，预期） |

## 检查 5 — 文档与 #83 / MIXED / G6 / Full / 99

**PASS。**

四份文档 2026-09-14 边界段一致：

- **#83 不重跑**：`1w6dru32` PV 已 CLOSED；诊断包与 C2 分析不得触发或替代重跑。
- **MIXED / G6 / Full 未通过**；`#84` 仍开放。
- **99 未过倍率门**：最新无探针场 `oayggl_s` 为 `RateUnmet`，停止重复 99，不做因果归因。
- 四个已公布场不得受控配对；比较器只做离线解析。
- 下一 native 场仅主会话；本切片未跑 native/flight/#83。

`#33` 父票 AC 未勾；`#84` 完成条件未勾。本比较器不能关闭这两票。

## 正式测试

```text
python -B -m unittest validation.test_compare_joint_gc_diagnostics
```

**38/38 OK**，约 2.450 s。未 skip。真实 `manager_gc_candidate.py` 钉 SHA `cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66` 可达，子进程夹具也过。

## 额外 TEMP 负例（已精确删除）

根目录：`C:\Users\PC\AppData\Local\Temp\wksim-i33-gc-neg-t1j3rocz`。探针脚本与结果 JSON 同前缀。事后 `wksim-i33-gc-neg-*` 为空。未把夹具写入仓库。

## 发现

### P1

无。未宣称 `#33/#84` 通过，未重跑 `#83`，未把 `causal` 置真，未把缺 latch/缺 GC 填 0，未把四个已公布场互相标成受控配对，未启动 native/ROS/SITL/UE。

### P2

1. **bool 时钟被当成 int。** `scan_rate` 接受 `wall_ns=True`、`issued_monotonic_ns=True`；窗口仍 `complete`，可 `compared` 并出 deltas。后者把真实 GC 赶到 post。
2. **乱序/负 GC 时钟仍可配对。** `start>end` 且两端在窗内算 timed；负区间算 preparation。二者都 `compared`。
3. **integrity 只认 `True` 或正整数。** `lost=Infinity` / `lost="3"` 仍 clean；`thread_cpu_ns=NaN` 进入 compared，CLI `allow_nan=False` 崩溃。
4. **`result.json` 非对象未收口。** `[]` 在 `read_result` 触发 `AttributeError`；`analyse_field` 只接 `OSError/ValueError/KeyError/TypeError`。
5. **已知场对无名场、空 source map 仍可受控配对。** token 门要两边都识别；空 `source_sha256` 且 `source_unchanged=true` 视为 source_match。

### P3

1. 正式测试未钉 bool 时钟、乱序 GC、`NaN`/`Infinity`/`string` lost、非对象 result、空 source map、已知场对无名场。
2. 空 rate 报 `mixed_identity_inside_one_field`，理由不准。
3. `group_work_timing.reports_dropped` 不进 integrity；靠 mark 不匹配拒绝。
4. 双方缺 `async_model_evidence_requested` 仍可配对；`pre_run` 的 `manager_target` 不参与身份比较。

## 未决边界

- `#33` / `#84` 仍 OPEN；本工具不能代替正式入口或公共任务。
- `#83` 保持 CLOSED，不重跑。
- MIXED / G6 / Full 证据集仍未通过；99 保持 `oayggl_s` / `RateUnmet`。
- `compared` 只表示两份保留记录在比较器合同下可并列，不是性能通过，也不是因果。
- P2 未修前，不要把 `controlled_pairing=true` 当成类型安全窗口/完整性证明。
- 未改六个源文件，未 git add/commit/push。

## 结论

离线比较器作为 #33/#84 前置诊断工具：**PASS**。主合同与文档边界成立；类型族 fail-open 记为 P2，不升级为本切片 FAIL，也不解锁父票。
