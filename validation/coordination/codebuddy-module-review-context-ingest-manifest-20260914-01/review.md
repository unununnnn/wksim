# Ingest manifest · CodeBuddy module-review 历史上下文批次（2026-09-14，context-only）

Owner：codebuddy-ingest-manifest。manifested HEAD
`31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（会话起止两次复核，写作全程未变，与独立审查
-02 的 reviewed HEAD 相同，区间为空）。schema `wksim.ingest-manifest.v1`；scope
`context-only`；acceptance `non-acceptance`。

本 manifest 只把独立审查终态 PASS 的三件候选（2026-09-12 模块复核文档 + 2026-09-14 绑定
note + 离线绑定测试）连同其独立审查三件（-02）按字节收存为**历史上下文批次**。它不构成
#83（或 #9/#26/#29/#62/#102 或任何工单）的验收、批准、收口、复核或重跑许可；不授予任何
当前速率门状态；不产生任何 native 结果或飞行证据；不把历史语境提升为当前权威。一切"当前
是否满足 / 是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类裁决）基于当下工件重新作出。

## 0. 批次构成与 -01 处置

- 精确批次 = 6 输入 + 4 输出，共 10 路径（§2）。输入 3 候选 + 独立审查 -02 三件。
- 失败的独立审查
  `validation/coordination/codebuddy-module-review-independent-review-20260914-01/`
  **原样保留为历史证据**（本会话 `sha256sum -c` 其自带 SHA256SUMS：review.md OK、
  review.json OK，exit 0），但**不列入本 10 路径批次**；本会话未修改、未暂存该目录。
- 独立审查 -02（PASS）已独立证明 -01 全部五项 P3 处置有效（§4）；-01 的失败结论由此被
  -02 取代，其字节保留仅作历史证据。

## 1. 基线关系

- 本 manifest 的 manifested HEAD = 独立审查 -02 的 reviewed HEAD =
  `31e5b65f…`（-02 `review.json` 的 `head_verified` 字段即该值）；会话起止复核
  `git rev-parse HEAD` 未变。祖先锚定天然满足，区间为空（0 个 intervening 提交）。
- 架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为 HEAD 祖先
  （`git merge-base --is-ancestor` 退出码 0，本会话复核）。
- HEAD equality 不作为批次身份缝；后代提交上套件与字节绑定仍然有效。

## 2. 精确路径集合（10 个唯一排序路径 = 6 输入 + 4 输出）

`exact-paths.txt`（SHA256
`6a44aebbd35ea933430f274b3566b1021deae79c279884788f75d00a8947adf1`，826 bytes）恰列
10 行、唯一、bytewise（`LC_ALL=C sort -c` 通过）排序：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/coordination/codebuddy-module-review-20260912.md` | 历史语境文档（2026-09-12 模块复核快照） |
| 2 | `docs/coordination/codebuddy-module-review-ingest-note-20260914.md` | 绑定与折叠登记 note（修订版） |
| 3 | `validation/coordination/codebuddy-module-review-context-ingest-manifest-20260914-01/SHA256SUMS` | 本 manifest 校验和 |
| 4 | `validation/coordination/codebuddy-module-review-context-ingest-manifest-20260914-01/exact-paths.txt` | staging 契约 |
| 5 | `validation/coordination/codebuddy-module-review-context-ingest-manifest-20260914-01/review.json` | 本 manifest 记录 |
| 6 | `validation/coordination/codebuddy-module-review-context-ingest-manifest-20260914-01/review.md` | 本 manifest 报告 |
| 7 | `validation/coordination/codebuddy-module-review-independent-review-20260914-02/SHA256SUMS` | 独立审查校验和清单 |
| 8 | `validation/coordination/codebuddy-module-review-independent-review-20260914-02/review.json` | 独立审查记录 |
| 9 | `validation/coordination/codebuddy-module-review-independent-review-20260914-02/review.md` | 独立审查报告 |
| 10 | `validation/test_codebuddy_module_review_context.py` | 离线绑定测试（修订版） |

## 3. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| codebuddy-module-review-20260912.md | `7fd97029dfd4c0a8f301badfdc3abadb02a097b184c9908a07aa9f85e6f2e2db` | 7544 |
| codebuddy-module-review-ingest-note-20260914.md | `0841c96a5a27b1b554c342610eb6e05141c81d2e037682bb0dcea13ed7e27703` | 8221 |
| test_codebuddy_module_review_context.py | `bc56db56480ff05ba542cad7401f4284116aa358ed31561df1597b65fa0fd2fd` | 12778 |
| -02 review.md | `c049c56d96144c3b4f5cd6bb0c15db3d1e4b39542712dc585ad75ca0aa56ed9d` | 10483 |
| -02 review.json | `e134bf3c0219624f1260856d6c1d59cb6c3d68624c275d2f77175173bf22a114` | 11245 |
| -02 SHA256SUMS | `e8526bfbac864e39e69be9484fb5155d33f067396b67cede8c848e584fb41271` | 154 |

- 6 输入哈希与字节数均现场重算，与任务给定值逐字一致；6 输入本任务全程未修改。
- -02 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、review.json OK，
  退出码 0。
- -02 `review.json` 严格解析通过：`head_verified=31e5b65f…`、`verdict=PASS`、
  `P1=0、P2=0、P3_new=0`、`prior_p3_remediations_verified=5`、`findings=[]`。
- 本会话独立抽查复核（不重复 -02 全量范围）：
  - D5 活性事实仍在：`ds-26-host-recheck-20260912.json` 含 "782"（1 处）、全文无 "886"；
    `wc -l validation/test_build_generated_e0.py` = 886。
  - 当前门内容锚：`Simulator/wksim_runtime/joint_profile.py:274-276` 的 marker 循环
    `raise ValueError('Formal mixed/PV evidence cannot include '+marker)` 在场。

## 4. 独立审查 -02 终态与五项 P3 处置（本 manifest 不改判）

-02（PASS，无 P1/P2/新 P3）独立证明 -01 五项 P3 修复有效：

1. **P3-1**：note §2.2 现引当前内容锚 :274-276，:219-220 登记为历史读数（2026-09-12 时点）。
2. **P3-2**：D2 更正唯一归属 `parser_coverage.structural_reason`；
   `diagnostic_constraint` 非顶层键、仅嵌套于 `next_minimal_diagnosis`；全部 12 条 D1/D2
   锚文本在 `structural_reason`。
3. **P3-3**：测试内过期的现在时 219-220 注释移除，新增 live 内容锚测试。
4. **P3-4**：mutation 负例与正例共用生产式 helper（`d1_folding_ok`/`d2_folding_ok`/
   `count_lines`/`sha256_of_bytes`/`strict_load`），失效类互不冗余；撤除同义反复测试。
5. **P3-5**：重复键负例改为确定性最小构造 `{"schema": "a", "schema": "b"}`，经同一
   `strict_load` 断言拒绝。

本 manifest 原样保留该定性（处置=修正完成，不声称 P3 "清零"），**不提升、不改判、不构成
任何批准**。D5 仍为活性事实纠错（782 vs 886，未折叠、未修复）。

## 5. 测试事实

- **run 1（normal）**：`python -B validation/test_codebuddy_module_review_context.py`
  正常工作树、真实 index 未动 → **Ran 25 tests, OK**，0 failures / 0 errors，exit 0。
- **run 2（staged）**：临时 `GIT_INDEX_FILE`（repo 外 `mktemp` 文件；`git read-tree HEAD`
  后 `git add -f` 恰好 exact-paths.txt 所列 **10 路径**；临时 index 与真实 index 的
  `git ls-files -s` 路径集差 = 恰 10 条新增、0 条移除；临时 index 全程不触碰真实
  index）→ **Ran 25 tests, OK**，exit 0；临时 index 用后删除。
- 真实 index 完整性：`.git/index` 文件字节哈希 run 前
  `7cf4a1989043e82954f59bd4aa704cbee88703cce2aba095428dd3a329ca26b1`、run 后相同（与
  -02 记录值一致）；`git ls-files -s | sha256sum` 前后均
  `5e08ccabec2775053b28f34e44eedd55db1a8b37ef8b4d895023d651f4b835ef`。真实 index 全程
  未暂存。
- **diff-check**：批次 10 路径 scoped `git diff --check` 干净（exit 0）；全树
  `git diff --check` 仅剩保护文件 `docs/Prometheus.gitmodules.reference` 的**预存**
  trailing-whitespace 告警（来自其会话开始前即存在的未提交修改，非本任务产生，该文件属
  禁止触碰清单，本 owner 未读改）。
- 套件设计（-02 审查记录 + 本 owner 复核）：仅祖先断言、路径经 `__file__` 解析、无写入/
  网络/native、不读取 untracked 分类工件、不要求候选保持未跟踪。

## 6. 边界与非主张

- 未修改任何输入或输出目录之外的文件；未暂存、未提交、未推送（真实 index 全程未动）；
  无 reset/clean。
- 未触碰保护文件 `docs/Prometheus.gitmodules.reference` 与
  `validation/coordination/short-cycle-dispatches.json`（未读改；其预存 `M` 状态非本
  任务产生）。未触碰 `rolling-six-plan-20260912.md`、`claude-native-wait-next-probe.md`、
  `validation/_probe_delivery_contract.py`、`%TEMP%audit26-report.json`。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未重跑 #83；未查询或改动
  GitHub；未联网。
- 门与措辞原样保留（1 ms tick、native barrier、4-tick、no-catch-up、100 ms/全窗、
  physics/identity 门）；诊断场结果永不得充当 #83 通过证据。
- 本批次为 context-only 收编：不授予 #83 验收/批准/收口/重跑、不授予当前速率门状态、
  不产生 native 结果或飞行证据。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入
  自引用，由会话终态报告记录。
