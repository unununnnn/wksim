# DS-B · ds-startup-cost-evidence-20260912 历史语境绑定与勘误登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`。本文件写作时的权威 HEAD `1c5656ed924020b3e626e68739caeeaef9f41a9e`（`Bind rate budget context offline`）；证据审计基线 HEAD `76f77470e91ecc742148df0f3eba6f5b5494511c` 是它的**直接父提交**，其间唯一提交 `1c5656ed` 只触及 rate-budget 路径（`docs/coordination/ds-rate-budget-*`、`validation/test_ds_rate_budget_context.py` 及其评审工件），与本绑定的两个文件完全不相交。架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为当前 HEAD 祖先（`git merge-base --is-ancestor` exit 0）。

## 0. 本文件的地位

本文件只做三件事：把下述两个文件**按字节绑定**为历史语境、登记独立证据审计的勘误与过时边界、并给出离线复检配方。它自身不构成任何验收、批准、收口或复核记录；被绑定的两个文件同样**不**构成这些。绑定只说明"当时观察到了什么"，不说明"现在是什么状态"；一切当前判定由当前权威基于当下工件重新作出。本文件不修改任何既有文件；两个被绑定文件在本写作时点仍为未跟踪（untracked）状态，字节与审计基线一致。

## 1. 历史语境绑定（字节级）

| 项 | 值 |
| --- | --- |
| 被绑定文件 1 | `docs/coordination/ds-startup-cost-evidence-20260912.json` |
| SHA256 / 大小 | `675026ab4f13b1a61e44fa60a208483faa26a3b08794a30118a453103689e709` / 18778 bytes |
| 被绑定文件 2 | `docs/coordination/ds-startup-cost-evidence-20260912.md` |
| SHA256 / 大小 | `a1df834b37241f7dc8fb2e1a9ec4407f330a05158e8e8b11f31ca6911800e2c4` / 17495 bytes |
| 性质 | DS-B 独立启动开销调查 v2（revision 2，schema `wksim.ds-startup-cost-evidence.v2`），2026-09-12 于 `/root/wksim-release-acceptance-fe3` 的只读调查快照 |

**历史语境（historical context only）**：两文件的任何结论、撤回、判定或"未排除"清单均不是当前的权威、批准、验收或收口状态。

**连续性证据**：`validation/architecture-decoupling-20260912/precommit-state.json`（HEAD `00d674c7…`，branch `codex/independent-rgb-integration`，`outside_owned`）与 `pre-main-switch-state.json`（`uncommitted_files`，main `a8f90b00…`→`f333316e…`）均在两个文件被分支/切主操作跨越时按字节记录了与上表完全相同的哈希。这两个状态文件的语义是**未提交文件连续性快照**：只证明字节稳定，不证明内容正确。

## 2. 跟踪工件的独立佐证（read-only 重算，基线 `76f77470`；写作时点复验于 `1c5656ed`，两文件字节未变）

### 2.1 算术逐位佐证（DS-B 值为精确值的最近 1000 ns 取整）

| 场次 | 组数 | DS-B creep | 跟踪值 creep_total_ns | DS-B work_over | 跟踪值 | DS-B release_excess | 跟踪值 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ztdsk269 | 24146 | 99688000 | 99687759 | 33372000 | 33372289 | 66315000 | 66315470 |
| vwen35gc | 21763 | 99637000 | 99636668 | 34869000 | 34868504 | 64768000 | 64768164 |
| 7bdfxkb_ | 27434 | 99718000 | 99717577 | 25704000 | 25703958 | 74014000 | 74013619 |

来源：`validation/33-rate-profile/diagnostic-triple-20260912/{ztdsk269,vwen35gc,7bdfxkb}.json`（已跟踪）。三份输出各自记录的 `trace_sha256` 与被绑定 JSON `terminal_shas.retained_raw` 的三个 `rate.jsonl` pin **逐一相同**（`9c798672…`、`e8c1c9e3…`、`484016e7…`）。latch `recorded_latch_lateness_ns = 100129488` 与 boundary tick `96624` 由已跟踪 `docs/coordination/ds-c1-actual-analysis-20260912.json` 的 `terminal_latch_closure`（`identity_sums_to_recorded: true`）与 `phase_partition_v3`（early 区间 246/248/249，groups_at_or_before_boundary 247/249/250）独立佐证。

### 2.2 源 pin 的历史解析

| pin | 解析 |
| --- | --- |
| `Simulator/wksim_core/joint.py` `f5433c2e…` | 当前树字节未变（引入于 `d78d279d`），文中对其全部行号引用当前成立 |
| `Simulator/wksim_runtime/joint_rate.py` `0b53a16a…` | 当前树字节未变（引入于 `767bd659`），`:89-130` 引用当前成立 |
| `Simulator/wksim_core/worker.py` `0becd1f3…` | = 提交 `acf81d56`（2026-09-11）的 blob；此后于 `1abf5f39`（2026-09-13）漂移 |
| `tools/analyze_joint_rate_intervals.py` `14ed9d64…` | = 提交 `e1c16314`（2026-09-11）的 blob，即被绑定文件自述的"fe3 过期私有副本" |
| `tools/run_joint_flight.py` `fd0b7ee6…` | **有跟踪历史 blob 锚但不在当前 HEAD 祖先链上**：内容 SHA256 逐位等于提交 `7cb7e8401776848fcb11e0a8dd2237c1eee2337b`（分支 `codex/planner-release-validation`，2026-09-12 22:43:12 +0900，"Add opt-in manager GC freeze candidate with lifecycle and entry checks"）中 `tools/run_joint_flight.py` 的 blob；`git merge-base --is-ancestor 7cb7e840… HEAD` 退出码 1，故该 pin 不解析到本检出主线的任何祖先版本。原文"在本仓库任何提交中均不存在/无跟踪锚"系**登记勘误**（2026-09-14 复核更正）；被绑定文件"fe3 私有副本"的自述按字节与该历史 blob 一致，其行号引用对该 blob 成立、对当前树过时（见 §4.1）。 |

## 3. 独立证据审计的四项勘误（P3）

| ID | 勘误 |
| --- | --- |
| P3-1 | 分析器锚差一代：`c3ba9de8…` 是 `f21fc3af` 版分析器的**内容 SHA256**，该版本**不含** `phase_partition`；`phase_partition` 自 `75353c06` 起才进入已提交分析器（内容 `1c43ac9c…`，即三份跟踪输出所 pin 的 `analyzer_sha256`）。被绑定文件"v3 phase_partition 只在已提交 c3ba9de8"应更正为"只在 `75353c06`（内容 `1c43ac9c…`）及其后"。已跟踪 `ds-c1-actual-analysis-20260912.json` 的 `terminal_latch_closure.authoritative_source` 也沿用 `c3ba9de8` 标签，读法同此更正。实质结论（fe3 副本过期、只引用既有输出值、未运行分析器）不受影响。 |
| P3-2 | §6 第二条前半句文件归属错误："worker.py:182-193 重建 per-RPC request dicts 并拷贝 120 元素 state 列表"的实际位置是 **`Simulator/wksim_core/joint.py:189-193`**（当前树仍成立）；后半句 `worker.py:228-236`（response/commands/input/extras 重建）在 pin 的 `acf81d56` blob 上正确。 |
| P3-3 | MD §1.3 "对全部 24147 组求和"为笔误：MD 头部与跟踪输出均为 **24146** 组。 |
| P3-4 | JSON 的 ns 粒度数值实为最近 1000 ns 取整；`equals_recorded_latch_ns: true`（100129000 vs latch 100129488）只在取整精度上成立（488 ns 差 < 500），应加取整限定语，不得当作逐位相等声称。 |

## 4. 过时/被取代的当前树边界（未来引用必须以当下锚为准）

1. **runner（历史 blob 锚在 HEAD 祖先链之外）**：pin `fd0b7ee6…` 逐位等于提交 `7cb7e8401776848fcb11e0a8dd2237c1eee2337b`（分支 `codex/planner-release-validation`，2026-09-12 22:43:12 +0900）中 `tools/run_joint_flight.py` 的 blob 内容 SHA256；`7cb7e840` 不是当前 HEAD 的祖先（`git merge-base --is-ancestor` 退出码 1）。原登记"pin 在本仓库历史中不存在/无跟踪锚"有误，现予更正：**锚存在，但只在 HEAD 祖先链之外的历史 ref 上**。被绑定文件对 runner 的行号引用（:296-305、:570-583、:750-757、:801/:812-816、:818、:901-903、:911、:916-919、:963-967）已逐段对照 `7cb7e840` blob 抽验**语义吻合**（`request_graph_ready` 门、`physics_health`、writers/`record`、`JointPhysics` 构造、tick-0 `snapshot=True` 只读请求、`physics.connect()`、reanchor 门、循环内 `import math` 等），即引用对该历史 blob 成立；相对当前树它们仍全部过时（该文件已被 `f333316e`、`100ef1aa`、`c3d4916f` 重写）。当前树锚不变：只读快照请求 `run_joint_flight.py:959`、reanchor 门 `:975`（现场复验在场）；§6 中 runner 侧的 `Path`/`import math` 循环内构造项按当下树仍存在、其 **C2 处置状态仍未解决**，须按当下树与当下计划核对，本登记不裁决。
2. **worker 漂移**：pin = `acf81d56` blob，当前树在 `1abf5f39` 漂移；被绑定文件的 worker 行号引用只对 `acf81d56` blob 成立。当前树锚（语义迁移后）：快照分支 ≈ `worker.py:94-96`、`initial_request` ≈ `:114`、initial sidecar ≈ `:249`。
3. **分析器链**：`e1c16314`（=fe3 pin）→ `f21fc3af`（内容 `c3ba9de8…`，无 phase_partition）→ `75353c06`（内容 `1c43ac9c…`，含 phase_partition，= 当前树）。
4. **raw 不在本检出**：6 个 `validation/joint-public-flight-*/` raw 文件不在本工作区，本地不可重算；其字节身份仅经跟踪工件 `trace_sha256`（3/3）间接佐证。条件采样计数（ztdsk269 ticks 40–1200 的 22 条 `diagnostic_step_cpu_timing`）与探针分账逐组均值（`final_spin_other` ≈ 955.1 µs 等）本地不可独立复算，仅由内部闭合（Σrelease_excess 取整 = latch，且跟踪侧 `identity_sums_to_recorded: true`）支撑。

## 5. 未解决的当前状态（本登记不裁决）

- §4 的未排除项（log flush/I/O 阻塞、线程竞争、decode/encode CPU 波动、宿主周期事件、热路径 `physics_health` 代价、anchor 后首次代价）在当前树上**仍然未排除**；M1/M2/M3 三项测量建议仍是开放建议，是否执行由当前权威决定。
- 重复构造（§6/勘误 P3-2 指向的 `joint.py:189-193` 与 `worker.py:228-236` 等）在当前树仍存在；主会话的 **C2 候选**（`Path` 构造移出循环）是否已落地、落在哪一版，须按当下树与当下计划核对——本文件不声称其已完成或已放弃。
- 本绑定不改变任何 rate 预算、frontier 或 #33/#26/#9 相关判定。

## 6. 离线复检配方（offline re-verification seam；无网络、无 native/MATLAB/构建）

1. **字节绑定**：`sha256sum` 两文件 == §1 两值且大小 18778/17495。任一不等则绑定失效，需重建登记。
2. **严格解析 + 11-of-11**：以拒绝重复键/NaN/Infinity 的严格 `json.loads` 解析 JSON（应成功，`kind=ds-startup-cost-evidence`，`revision=2`）；从 `terminal_shas`（sources 去掉 `*_role` 字符串键后 5 项 + retained_raw 6 项）取 11 个 pin，与 MD 终态 SHA 表逐项比对，必须 **11/11 一致**。
3. **算术佐证**：读三份 `validation/33-rate-profile/diagnostic-triple-20260912/*.json`，逐场核对 groups 与 creep/work_over/release_excess 等于 §2.1 表列值，且各自 `trace_sha256` == §2.2 三个 rate.jsonl pin；读 `ds-c1-actual-analysis-20260912.json` 的 `phase_partition_v3` 与 `terminal_latch_closure` 核对 246/248/249、247/249/250、100129488、96624。
4. **源 pin 解析**：`joint.py`/`joint_rate.py` 当前 sha256 == pin；`worker.py` == `git show acf81d56…:…` 的 sha256；分析器 pin == `git show e1c16314…:…`；runner pin == `git show 7cb7e8401776848fcb11e0a8dd2237c1eee2337b:tools/run_joint_flight.py` 的内容 sha256（原"全历史无匹配/无跟踪锚"说法已按 §2.2/§4.1 更正），且 `git merge-base --is-ancestor 7cb7e840… HEAD` 退出码 1（锚在 HEAD 祖先链之外）。
5. **边界行号抽查**：`joint.py:189-193` 仍为 request-dict/120 列表拷贝；`worker.py:94-96`/`:114`/`:249` 语义在位；`run_joint_flight.py:959`/`:975` 语义在位。任一失配表示当前树又漂移，需更新 §4。
6. **祖先**：`git merge-base --is-ancestor` 对 `f333316e…`、`76f77470…` 对运行 HEAD 均 exit 0。

任何一步失败均表示本登记过期，应以当时权威的工件重建登记，而不是沿用本文件结论。

## 7. 边界与不声称

- 本文件只读核验：未修改被绑定文件或任何既有文件；未运行 native/ROS/SITL/MATLAB/构建/模型加载；未嵌套代理；未查询或改动任何 GitHub 状态；未重跑 #83 的任何工作；未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`）。
- **不声称**：运行时已修；任何排他归因（宿主/飞控/GC/探针）；未排除项已被排除；C2 已完成；两个被绑定文件获得任何验收/批准/收口地位。
- 本文件创建后即为静态工件；其 SHA256 与大小在交付报告中给出，后续以此检测自身是否被篡改。
