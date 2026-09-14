# #60 Full 验收报告候选 — 独立复核

日期：2026-09-14T09:37:42+09:00  
工作类别：review  
只读源文件，未改 `docs/plan/full-acceptance-report.md` 或任何既有文件；未 git add/commit/push；未关票；未做 owner approval。

## 派发核验

| 项 | 值 |
| --- | --- |
| cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| branch | `main` |
| HEAD | `5370b2324672c9036d41239cb93e21fc5eb42897` |
| 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` | `git merge-base --is-ancestor` 退出码 **0** |
| 已读 | `AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、父目录 `CONTEXT-MAP.md`、`CONTEXT.md`、GitHub `#60`、`docs/plan/full-scope-expansion.md`、`docs/coordination/short-cycle-goal.md`、`docs/plan/goal-objective.md` |
| 本次 module / interface | Full/G0–G6 报告层（只读复核） |
| 被复核文件 | `docs/plan/full-acceptance-report.md` |
| 期望 SHA256 | `3edcc5c84b08cdf02648112c0aa9abd4ebc396dcb266bcc574277d34354721d1` |
| 实测 SHA256 | 同左；复核前后字节未变 |
| 独占写入 | 仅本目录 `review.md` / `review.json` / `SHA256SUMS` |
| GitHub 只读 | 一次 `gh issue view 60`；一次 `gh issue list --state all --limit 200` |
| 未跑 | native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83 / R1 / RateUnmet |

本检出无 ADR 文件；`CONTEXT-MAP.md` 不在 `wksim/` 内，只存在于父目录。报告未引用这两处，也未伪造路径。

## 总评

**PASS**（报告层机械复核成立；**不是** Full / G6 / Goal / #60 验收通过）。

P1 = 0；P2 = 0；P3 = 2。  
48 源键与 48 报告行集合精确相等；`accepted=0` / `partial=12` / `blocked=8` / `not-tested=28` 与重算一致；G0–G6 全覆盖且无一 `accepted`；Full/G6 未宣布通过；`#1/#10/#60` 与 Goal 保持 OPEN；一次实时 `gh` 列表与报告前置状态一致；R1 `numerical_failed`/5684、RateUnmet、`#83` CLOSED/PASS 原文保留且未声称重跑；明确引用的本地路径均存在且 SHA256 与报告一致。

## 机械计数

源：`docs/plan/full-scope-expansion.md`（SHA256 `85c15ad817afe35fcd325435f02ccb894ad33015e223537daa3cc3706a564fee`）。  
规则：`^\| (SIM|COMM|MODEL|OPS)-\d+ \|`。

| 项 | 源 | 报告 | 一致 |
| --- | ---: | ---: | --- |
| 机器键总数 | 48 | 48 | 是 |
| 唯一键 | 48 | 48 | 是 |
| 重复键 | 0 | 0 | 是 |
| 缺键 / 新增 | — | 0 / 0 | 是 |
| SIM / COMM / MODEL / OPS | 12 / 7 / 16 / 13 | 12 / 7 / 16 / 13 | 是 |

源状态：`blocked=8`，`evidenced=12`，`not-implemented=28`。  
报告 verdict 重算：`accepted=0`，`partial=12`，`blocked=8`，`not-tested=28`，合计 48。  
映射：源 `blocked→blocked`、`not-implemented→not-tested`、`evidenced→partial`；48 行 gap 原文与源复核表第 4 列逐字相同。无一行被升为 `accepted`。

partial 12 = SIM-02, SIM-08, COMM-03, OPS-01, OPS-02, OPS-04, OPS-05, OPS-06, OPS-08, OPS-10, OPS-11, OPS-12。  
blocked 8 = SIM-01, SIM-05, SIM-06, SIM-09, SIM-10, SIM-12, MODEL-01, OPS-13。  
与报告 L122–L124 列举一致。

复现：

```text
Select-String -LiteralPath docs/plan/full-scope-expansion.md -Pattern '^\| (SIM|COMM|MODEL|OPS)-\d+ \|'
Select-String -LiteralPath docs/plan/full-acceptance-report.md -Pattern '^\| (SIM|COMM|MODEL|OPS)-\d+ \|'
Get-FileHash -Algorithm SHA256 docs/plan/full-acceptance-report.md
Get-FileHash -Algorithm SHA256 docs/plan/full-scope-expansion.md
```

## 检查 1 — 源键集合

**PASS。** 源 48/48/无重复；报告 48 行键集合与源精确相等，顺序与源 L99–L146 及报告 L40–L42 序列相同。`US-01..US-48` 未混入本表。

## 检查 2 — 行状态与统计

**PASS。** 每行恰有 `accepted|partial|blocked|not-tested` 之一，无非法状态。重算统计与报告 L116–L120 一致（`accepted` 计数为 0，Counter 省略零键不改变合计）。证据不足行保持 `partial`/`blocked`/`not-tested`，未见提升为 `accepted`。

## 检查 3 — G0–G6 与 Full

**PASS。** 门表 L132–L138 覆盖 G0–G6，无重复门。分布：`accepted=0`，`partial=4`（G0/G1/G3/G5），`blocked=3`（G2/G4/G6），`not-tested=0`。与行证据相容：HITL/SIH 行 blocked、R1 失败、RateUnmet、28 行 not-tested、OPEN 前置均未把 G6/Full 写成通过。L27/L241/L253 明确 Full 未通过、G6 未通过、无 owner approval。

G0 的 `exit_copied` 等于 `goal-objective.md` 用户结果列与退出证据列的拼接；G1–G6 为缩写，见 P3-1。缩写未改变“门未通过”结论。

## 检查 4 — GitHub 状态

**PASS。** 一次 `gh issue view 60`：`#60` OPEN，标题 `[Astra] 按完整原规格及G0–G6进行最终Full复核`，标签 `wayfinder:task` / `ready-for-agent`。  
一次 `gh issue list --repo unununnnn/wksim --state all --limit 200 --json number,title,state` 与报告 L148–L174 对照：

| issue | 报告 | 实时 | 标题一致 |
| --- | --- | --- | --- |
| #1 / #10 / #60 | OPEN | OPEN | 是 |
| #9 / #20 / #26 / #27 / #28 / #29 / #33 / #46 / #84 | OPEN | OPEN | 是 |
| #55 / #56 / #59 / #25 / #35–#40 / #44 / #45 / #47 / #48 / #83 | CLOSED | CLOSED | 是 |

CLOSED 票未被写成 OPEN；OPEN 票未被写成完成。报告 L176 所列仍 OPEN 且阻塞 Full/G6 的前置与实时列表一致。Goal 未查 Goal DB；与报告及 `short-cycle-goal.md`「Goal 不可 complete」相容，见限制。

## 检查 5 — 保留失败 / 不重跑

**PASS。**

- R1：报告 L182 保留 `numerical_failed`、比较 180,360、严格不等 5,684、C0/C2G/C3G = 2/1943/3739。与 `docs/2026-09-09-numerical-conformance-report.md` L3/L7–L9 及 `validation/numerical-conformance-gxxh6xhr/run-index.json` 的 `failed_values=5684` 一致。未声称重跑。
- RateUnmet：报告 L188 保留 `oayggl_s` / `failed@tick108004` / 正式 MIXED 证据集为空。与 `docs/coordination/short-cycle-goal.md` L18/L46 一致。未声称重跑或修复。
- #83：报告 L192 写 CLOSED 且 `1w6dru32` PV PASS，并指向 `docs/2026-09-13-final-combo-pv-pass.md`。实时 `#83` CLOSED。明确「不重跑」「不等于 MIXED/Full/G6」。

## 检查 6 — 本地路径与身份

**PASS。** 报告明确引用且给出 SHA256 的本地路径全部存在，实测哈希与报告 L204–L218 逐项相同。候选报告自身 SHA256 与派发期望值相同。未见伪造 missing 路径。

`CONTEXT-MAP.md`、ADR、`docs/agents/issue-tracker.md` 不在本检出；报告未引用，故不记为报告缺证。冻结手册 SHA 与数值合同 SHA 按报告标注为源文/对照报告抄录，本复核核到源文件与 `run-index.json` 内相同字符串，未另找手册二进制。

## 检查 7 — 草稿 / 矛盾 / 关票暗示

**PASS。** 无 `TODO`/`TBD`/`FIXME`/`XXX`/`待填`/`WIP`/`占位符`。计数与结论无相互矛盾。owner approval 仅以否定句出现（L25/L27/L138/L241）。关票语句均为「不关闭 / 保持 OPEN」。未发现误关票指令。

## 检查 8 — 结构解析器负例

**PASS。** 对候选报告解析器在 TEMP `C:\Users\PC\AppData\Local\Temp\wksim-i60-full-neg-7ktm2qds` 构造 6 个负例，全部 `ok=false`；随后删除该目录，无残留。TEMP 之外未落盘。

| 负例 | 构造 | 解析器 |
| --- | --- | --- |
| `dup_key` | 复制 SIM-01 行 | `row_count=49`；`duplicate_row_keys:SIM-01` |
| `miss_key` | 删除 SIM-03 | `row_count=47`；`missing=['SIM-03']` |
| `illegal_status` | SIM-02 verdict=`pass` | `illegal_verdict line=54` |
| `dup_gate` | 复制 G0 门行 | `duplicate_gates:G0`；`n_gates=8` |
| `more_rows` | 插入 SIM-99 | `row_count=49`；`extra=['SIM-99']` |
| `fewer_rows` | 删除 OPS-13 | `row_count=47`；`missing=['OPS-13']` |

正例：原报告 `ok=true`，48 行 / 7 门。

## 发现

### P1

无。

### P2

无。

### P3

1. **P3-1** 行 128、133–138。L128 写「退出条件原文抄自 `docs/plan/goal-objective.md`」，但 G1–G6 的 `exit_copied` 是缩写/改写，不是退出证据列原文；G0 是「用户结果 + 退出证据」拼接（该拼接本身成立）。复现：对照 `docs/plan/goal-objective.md` L25–L31 与报告 L132–L138。影响：只读门表会漏掉 G1 产品节点/隔离收尾、G2 唯一时钟/不代以双独立循环、G5 许可冒充拒绝等条款；本报告仍把这些门标为 partial/blocked，且 Full/G6 未通过，故不升为 P2。
2. **P3-2** 行 3、14。工作类别写成 `new-development`，同时自称「只读复核，不改实现」。复现：读报告 L3–L8。影响：派发分类易与本复核的 `review` 混淆；不改变 48 行/G6 结论。

## 限制

- 本切片只复核报告层，未完成任何 native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight，也未重跑 #83、R1、RateUnmet。
- 未查询 Goal 数据库；Goal OPEN 只与报告正文和 `short-cycle-goal.md` 相容，不是 Goal 工具实读。
- 未把本文件当作 Full、G6、#60 或 Goal 完成。
- 未 add/commit/push，未关票，未做 owner approval。
- `CONTEXT-MAP.md` 与 ADR 不在本检出；父目录 map 已读，不作为报告证据。
