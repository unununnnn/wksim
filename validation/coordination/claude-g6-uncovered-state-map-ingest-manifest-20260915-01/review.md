# Ingest manifest · G6 uncovered-state-map 离线批次（2026-09-15-01，context-only，remediated / GO）

Owner：claude-ingest-manifest。manifested HEAD `0b10f786e808eebe7698e9a277766bf2f68a4d35`
（"Bind GC-freeze review context offline"，branch `main`；写作全程 HEAD 未变，`git rev-parse HEAD`
现场复核）。本地图冻结锚点为 `ee6eb88819cefe255f22e788c39a77c0bbab490e`（"Bind native-wait context
offline"），是 HEAD 的祖先（`git merge-base --is-ancestor ee6eb888… HEAD`，exit 0，本会话复核）。
独立复审 claude-g6-uncovered-state-map-independent-review-20260914-02 的 reviewed HEAD
（`repo_head_at_review`）为 `0b10f786…`，与本 manifested HEAD **相同**（0 个 intervening 提交）。
schema `wksim.ingest-manifest.v1`；scope `context-only`（离线 state-map/工具证据）；acceptance
`non-acceptance`。

本 manifest 只把独立复审（review-02）终态 **GO** 的四件 G6 36 态 uncovered-state-map 准入候选
（确定性离线生成器 + 机器可读覆盖图记录 + 离线自测 + 成对计划文档的 remediated 版）连同其独立复审
三件按字节收存为**历史上下文批次**。review-02 裁决 GO：前一轮 review-01 的 F1（P1 blocker）与
F2–F4（P2）全部 CLOSED，F5（P3）CLOSED，F6（P3）无新顾虑。这是 context-only 收存，**不授予**
任何工单（含 #84、G6、Full、#83）的验收、批准、收口、重跑许可；不授予任何预算批准或物理精度
验收；不产生任何 native 结果或飞行证据；不把离线清单提升为当前权威。GO 是独立复审对 remediated
候选"可收存"的裁决，**不是**任何工单的验收，也**不关闭** #84/G6/Full，`r1_status` 仍为
`numerical_failed`。一切"当前是否满足 / 是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类
裁决）基于当下工件重新作出。

## 1. 基线关系（祖先锚定 + 证据零漂移 / 区间不相交）

- 架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为 HEAD 祖先
  （`git merge-base --is-ancestor f333316e… HEAD`，exit 0，本会话复核）。
- 地图冻结锚 `ee6eb88819cefe255f22e788c39a77c0bbab490e` 为 HEAD 祖先（同法 exit 0）。两锚均为
  fail-closed 祖先要求（非精确 HEAD 钉），与生成器 `validate()` 的 `anchor_not_ancestor` /
  `base_ancestor_not_ancestor` 失败码一致。
- **当前 HEAD 仅作观测**：地图 `anchor_policy.observed_head_embedded=false`，HEAD 字面量
  `0b10f786…` 不写入地图 JSON（review-02 `grep -c` → 0，本会话复核一致）。无精确 HEAD 要求。
- **证据零漂移**：`git diff --name-only ee6eb888… HEAD -- <10 份 EVIDENCE_PINS>` → **空**
  （本会话复核；锚点以来 10 份钉住证据零改动）。
- **区间不相交**：`ee6eb888..HEAD` 恰 **5 个 intervening 提交**（`cca825b5` G6 architecture
  applicability、`f6d9b95a` Q01 owner-decision proposal、`fe680c2d` G6 owner-decision request、
  `573ca6dd` G6 same-source readiness、`0b10f786` GC-freeze review context），触及 **47 条路径**
  （全部为他方 context-ingest-manifest / independent-review / 计划工件）。求交
  （`LC_ALL=C comm -12`）：47 路径 ∩ 10 EVIDENCE_PINS = **0 条**；47 路径 ∩ 本批 11 路径 = **0 条**
  （zero overlap，程序化复核）。故锚点之后的前移既不与钉住证据相交，也不与本批任何路径相交，
  review-02 证据对本 manifested HEAD 仍适用。
- reviewed HEAD（`0b10f786`）== manifested HEAD（`0b10f786`），二者间 0 个 intervening 提交；
  地图本身钉住的是 `ee6eb888` 锚而非 HEAD。

## 2. 精确路径集合（11 个唯一排序路径 = 4 候选 + 3 复审 + 4 输出）

`exact-paths.txt`（SHA256 `a4fb0d90eb8d47dea103c4d715270a456bc9e0b1bd32cae92ab1c2cf9dd36b12`，
837 bytes）恰列 11 行、唯一、`LC_ALL=C` bytewise 排序、LF-only（单结尾 LF，0 个 CR）、集合与本
任务规定的 11 路径精确相等：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/plan/59-g6-uncovered-state-map-20260914.md` | 成对计划文档（覆盖清单，非验收） |
| 2 | `tools/map_g6_uncovered_states.py` | 确定性离线生成器 |
| 3 | `validation/coordination/claude-g6-uncovered-state-map-independent-review-20260914-02/SHA256SUMS` | 独立复审校验和清单 |
| 4 | `validation/coordination/claude-g6-uncovered-state-map-independent-review-20260914-02/review.json` | 独立复审记录 |
| 5 | `validation/coordination/claude-g6-uncovered-state-map-independent-review-20260914-02/review.md` | 独立复审报告 |
| 6 | `validation/coordination/claude-g6-uncovered-state-map-ingest-manifest-20260915-01/SHA256SUMS` | 本 manifest 校验和 |
| 7 | `validation/coordination/claude-g6-uncovered-state-map-ingest-manifest-20260915-01/exact-paths.txt` | staging 契约 |
| 8 | `validation/coordination/claude-g6-uncovered-state-map-ingest-manifest-20260915-01/review.json` | 本 manifest 记录 |
| 9 | `validation/coordination/claude-g6-uncovered-state-map-ingest-manifest-20260915-01/review.md` | 本 manifest 报告 |
| 10 | `validation/g6-uncovered-state-map-20260914.json` | 机器可读覆盖图记录（schema `wksim.59-g6-uncovered-state-map.v1`） |
| 11 | `validation/test_map_g6_uncovered_states.py` | 离线自测 |

三集合（4 候选 / 3 复审 / 4 输出）两两路径不相交。

## 3. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| tools/map_g6_uncovered_states.py | `d204fcd3563599bc1afb50f15a49636ca17a6cbb5544261428e6f6df863513a0` | 65196 |
| validation/g6-uncovered-state-map-20260914.json | `19fc85f32c040218896e6d3a3785074f6e782756b00849d519bcb68bf61cb468` | 99845 |
| validation/test_map_g6_uncovered_states.py | `955fbfa742119c172f067e9f93164e8c1d9f0499dc5d14d9e54ab105807389f1` | 40622 |
| docs/plan/59-g6-uncovered-state-map-20260914.md | `67beeb7c12daa43cfb948667801de17dd8041e32901081d202c12ff3b2264297` | 8074 |
| review-02 review.md | `cebea0d2af26e06554971c2e2f1ea92f811c850337eebbf4eb8658b0e32c1c4c` | 12216 |
| review-02 review.json | `9051b847db0a85ac9214c779af558829fc9d48d58645f7e5cdefb9e9157b48c6` | 11303 |
| review-02 SHA256SUMS | `ad2d98104582075b2d43cccfc72f23aa22471b7b35532b51f8b3f23d87692845` | 154 |

- 7 输入哈希与字节数均现场重算：4 候选与 review-02 §1 给定身份逐字一致（remediated 版，哈希不同于
  review-01 集合，确证已返修）；3 件 review-02 工件重算一致。
- 4 候选 untracked（`git status --porcelain` → `??`）；3 件 review-02 工件被 `.gitignore:53`
  `/validation/*/` 忽略（ignored，故 `git add` 需 `-f`）。11 路径在 HEAD 树均不存在
  （`git ls-tree -r HEAD -- <11 路径>` → 空）。
- review-02 目录 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、review.json OK，
  exit 0。
- review-02 `review.json` 严格解析通过：`verdict=GO`、`verdict_scope` 恰 4 候选、4 候选
  `hash_match` 全 true、totals 36/13/23、`r1_status=numerical_failed`、open_items
  issue_84/g6/full 全 open、g6_acceptance/physical_accuracy/issues_closed/budget_approved/
  effective 全 false、`authority=none`、`pending_approvals=[]`；closure F1–F5 CLOSED、F6
  NO_NEW_CONCERN。

## 4. 独立复审事实与发现的保真收存（review-02，GO）

- **裁决**：GO，remediated 四候选"held together"；前一轮 review-01（REWORK）的 F1 P1 blocker 与
  F2–F4 P2 全部 CLOSED，F5 P3 CLOSED，F6 P3 无新顾虑。
- **F1（was P1）`output_encoding.hex_stage2` — CLOSED**：committed
  `index_map[11].output_encoding.hex_stage2 = [3c47b1ebce4a1e30, bc56d4db33a987b9, 36f8ccceed35d6fd]`
  （p/q/r 三元组）。review-02 自钉住 trace 独立重推导：`first-step-trace.jsonl` stage-2 `deriv_hex`
  长度 36 且 `deriv_hex[10:13]` 恰为该三元组，逐字节一致。虚假"comparator-checked"措辞已除，note 写明
  仅作编码转录、无物理释义；validator 对 `hex_stage2` 双向绑定（记录常量 + 活体重读 trace）。
- **F2（was P2）陈旧/自欺 `head` + 红套件 — CLOSED**：改为钉住冻结锚 `ee6eb888…` +
  `base_ancestor=f333316…`，无 `head` 键，`anchor_policy.observed_head_embedded=false`；HEAD 仅
  观测。锚为 HEAD 祖先（exit 0）、`anchor..HEAD` 证据漂移为空、HEAD 字面量未嵌入（grep 0）。旧
  head-drift 测试由 `test_anchor_and_ancestors_are_recorded_and_verified` 取代。fail-closed 经
  review-02 独立 monkeypatch `_git_text`（非 shipped 测试）确认：非祖先 → `anchor_not_ancestor`；
  探针不可用 → `anchor_not_ancestor`+`evidence_drift_unverifiable`（另含
  `base_ancestor_not_ancestor`、`pin_tracked_flag_mismatch`）；重叠/证据漂移 → `evidence_drift`。
- **F3（was P2）证据字段校验盲点 — CLOSED**：`validate()` 现绑定 `output_encoding`、`hex_stage2`
  （双向）、`mrdivide_output_evidence`、top-level `line_bindings`、`doc_refs`；review-02 以自写
  mutation harness（直接调 `validate()`，非 shipped 测试）逐条验证 delete/corrupt 均 fail closed，
  baseline 未篡改返回 `ok:true, codes:[]`。
- **F4（was P2）符号冲突范围误判 — CLOSED**：`symbol_conflicts[0].scope` 与
  `unresolved.transferfcn_motor_symbol_order.scope` 均为 `indices 19..35`；索引 19..35 全为
  `conflicted_requires_archive_input`（0..18 全 `resolved`，无误分类）；19..24 的 `block_symbol`
  示为 `IntegratorSecondOrderLimited__n`，归属声明为 conflicted 而非 resolved。builder STATE_LAYOUT
  （19..24 `__n`、25..27 TransferFcn、28..35 Motor）与需求文本 `:36`（19–27 TransferFcn）的边界冲突
  如实暴露；无残留"逐索引顺序"误述（grep 0）。
- **F5（was P3）死数据/误标 — CLOSED**：`SYM_TABLE` 减为 3 元素 `(lo,hi,symbol)` 元组（删去死的
  `source`/`exact_binding` 元素）；`first_step_mapping` 更名 `first_step_timeline`；covered-range
  `symbol_note` 不再过度主张索引归属（归 `comparison-v2.json target_indices`，probe 仅"对同名刚体
  积分器注册 listener"）。
- **F6（was P3）次要措辞 — 无新顾虑**：`entry_classes.mrdivide_output_indices=[10,11,12]` 保留但
  现框定为求解结果向量跨距（`Product2[0..2]`），逐索引编码证据仅挂 index 11 且 note 明言；为
  validator 固定常量，非 per-index 证据过度主张。
- **Totals 与非收口（required）**：`counts` total 36、covered 13（`6..18`）、uncovered 23（`0..5`、
  `19..35`），`covered_indices`/`uncovered_indices` 精确匹配；`entry_classes` 残差/输出索引
  `[10,11,12]`，`physical_semantics_inferred:false`。非收口完整：`open_items` issue_84/g6/full 全
  open；`r1_status=numerical_failed`；`g6_acceptance`/`physical_accuracy`/`issues_closed`/
  `budget_approved`/`effective` 全 false；`authority:none`；`pending_approvals:[]`。无任何预算或
  物理精度验收。

## 5. 边界事实的收存（不削弱、不提升）

- **离线证据性质**：本批四候选是把冻结 R1/C3G 目标模型（`nXc=36`）扁平连续状态逐索引登记
  "已覆盖/未覆盖"的**证据清单**；生成器不重跑任何 trace、不做数值验收、不下 G6/Full 结论。ZIP 缺失处
  一律记 `unresolved`，不猜、不补。
- **13 个已覆盖索引只是清单覆盖**，不代表数值符合；其中 index 11 本身记录 1 ULP 分歧（target trace
  `bc56d4db33a987b9` vs comparison-v2 参考 `bc56d4db33a987b8`，hex-only，无物理释义）。
- **非收口**：`#84`、G6、Full 全 open；`r1_status=numerical_failed`；`g6_acceptance=false`、
  `physical_accuracy=false`、`issues_closed=false`、`budget_approved=false`、`effective=false`；
  `authority=none`；`pending_approvals=[]`。不提议、不申请、不登记任何预算、批准、验收或合同冻结。
- **门与措辞原样保留**：1 ms tick、native barrier、4-tick、no-catch-up、100 ms/全窗、physics/identity
  门均不削弱（本批不触碰这些门）；诊断场证据永不充当 #83 通过证据。
- **unresolved 需冻结 ZIP/归档输入**：`archive_source_line_mapping`、`authoritative_state_layout`
  （需归档成员 `Exp1_MinModelTemp.cpp/.h`）、`transferfcn_motor_symbol_order`（19..35 边界冲突）、
  `residual_component_binding_10/12`、`unmapped_reference_states` 等均如实记为未决，需冻结归档或
  新证据，不猜。
- **untracked provenance 不参与判定**：磁盘上确有哈希的生成 ERT C（`a35d7c8f…`，324922 bytes）
  单列为 `untracked_provenance`，其字节**不参与**任何覆盖/分类判定；review-02 复核其
  `available_on_disk:true`/`matches_expected:true` 为真。
- **#83 不重跑**：本批与 #83 无关；不启动 MATLAB/native/ROS/DDS/SITL/飞行/UE/#83；不构建；不修改
  任何既有 trace、合同、比较器或证据字节。

## 6. 测试事实（本会话执行 Mode A + exact-11 准入；Mode B 证据由 review-02 保真携带、未重跑）

- **Mode A（normal，真实 index 未动）——本会话自跑**：
  `python -B -m unittest validation.test_map_g6_uncovered_states` → **Ran 27，OK（skipped=1），
  0 failures / 0 errors**，exit 0（1 skip 为 `test_exact4_staging_binds_the_same_bytes`，按设计仅
  temp-index 运行生效）。与 review-02 Mode A（26 ok + 1 skip，OK）一致。跑后真实 index/HEAD 复核
  不变（见下）。
- **`--validate`（本会话自跑）**：`python -B tools/map_g6_uncovered_states.py --repo-root .
  --validate` → `{"ok": true, "codes": [], "errors": []}`，exit 0。
- **确定性再生（本会话自验）**：纯 Python `dumps(build_map('.'))` 与已提交 JSON **逐字节一致**
  （SHA256 `19fc85f3…1cb468`，99845 bytes，LF-only 单结尾 LF）。
- **Mode B（review-02 证据，本会话未重跑）**：review-02 于 repo-external 临时 `GIT_INDEX_FILE`
  （repo 外；`git read-tree --empty` 后 `git add -f` 恰好 4 候选），套件 **Ran 27，OK（skipped=0）**
  （exact4 运行、无 skip），exit 0。temp index 恰 4 条、全 stage 0、mode `100644`
  （`core.autocrlf=false`），各 staged blob SHA1 等于工作树 `git hash-object`：
  `docs/plan/59-…md` `44b08f41b5e12da9c51bdef64c3e2df93411b485`、`tools/map_g6_uncovered_states.py`
  `89c275458f30da81cad9d9abeabf42a97e059f56`、`validation/g6-uncovered-state-map-20260914.json`
  `d6a2f68ed7476909a3c0b2a53aa655605bb6033b`、`validation/test_map_g6_uncovered_states.py`
  `fff9293e3f8ef17557605eda4ac830997760e2f9`。真实 `.git/index` SHA256 前后均
  `cf249890…319a32`，HEAD `0b10f786…` 不变，temp index 用后删除。本 manifest 不重跑 Mode B（其
  exact4 临时索引与本节 exact-11 不同设），仅按 review-02 §5 / review.json `test_execution` 原样
  携带其数值，归属 review-02。
- **exact-11 read-tree HEAD 准入（repo-external，独立于 Mode B，不跑套件）——本会话自验**：临时
  `GIT_INDEX_FILE`（repo 外；`git read-tree HEAD` 后 `git add -f` 恰好 exact-paths.txt 所列
  **11 路径**）；临时 index 与真实 index 的 `git ls-files` 路径集差 = **恰 11 条新增、0 条移除**；
  11 条全部 stage 0；11 条 staged blob 逐一等于工作树 `git hash-object`（程序复核）；临时 index 从未
  指向真实 index，用后删除。真实 index 指纹复算不变。
- **真实 index 完整性**：`git ls-files -s | git hash-object --stdin` 全程前后均为
  `0d1d6e82938d145689e3f2d47bbda081918922bd`；`.git/index` 原始字节 SHA256 写作前
  `cf249890d18567a9f62173ff1e8ac717362fe531ecea02a545a72ee185319a32`（与 review-02 记录值一致，会话
  终态复核不变）。真实 index 全程未暂存、未变；HEAD 全程 `0b10f786…` 未变。
- **diff-check（批次范围）**：`git diff --check -- <11 批次路径>` 干净（11 路径均非 tracked 修改，
  输出空、exit 0）。全树 `git diff --check` 仅在受保护脏文件
  `docs/Prometheus.gitmodules.reference` 内有 **12 处预存** trailing-whitespace 告警（exit 2；本任务
  之前即存在，非本任务产生，该文件属禁止触碰清单，本 owner 未读改），其余他方 modified 文件
  （solve-form 三件、short-cycle-dispatches.json）无 diff-check 告警。

## 7. 边界与非主张

- 未修改本 manifest 四输出之外的任何文件；未暂存、未提交、未推送（真实 index 全程未动；temp index 与
  临时工件均 repo 外，用后删除）。
- 未触碰保护文件 `docs/Prometheus.gitmodules.reference` 与
  `validation/coordination/short-cycle-dispatches.json`（现场重算 = `5aa70302…` / `06e65cc1…`，与
  既有基线一致）；未读改 solve-form 三件（`docs/plan/59-g6-solve-form-decision-20260914.md`、
  `validation/e0-g6-solve-form-decision-20260914.json`、`validation/test_e0_g6_solve_form_decision.py`，
  现场重算 = `4c773018…` / `bc8302e9…` / `86c96dff…`，仅记录、未触碰）、任何 time-field 文件/manifest
  及所有他方工作。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未重跑 #83；未查询或改动 GitHub；未用
  `git replace`；未触碰 sibling 项目。
- 本 manifest 是 context-only 收存：仅离线 state-map/工具证据收存，不构成 #84/G6/Full/#83（或任何
  工单）的验收、批准、收口、复核或重跑许可；不授予任何预算批准或物理精度验收；不产生 native 结果或
  飞行证据；不把离线清单提升为当前权威。GO 仅是独立复审对 remediated 候选"可收存"的裁决，不关闭
  #84/G6/Full，`r1_status` 仍为 `numerical_failed`。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入自引用，由会话终态
  报告记录。
