# Ingest manifest · CodeBuddy gc-freeze 上下文批次（2026-09-14-01，context-only，remediated / KEEP）

Owner：claude-ingest-manifest。manifested HEAD `cca825b5bac5bd8b7837a9ac75c85e715b67deb6`
（"Bind G6 architecture applicability offline"，branch `main`；写作全程 HEAD 未变，`git rev-parse HEAD`
现场复核）；独立审查 codebuddy-gc-freeze-independent-review-20260914-03 的 reviewed HEAD 为
`ee6eb88819cefe255f22e788c39a77c0bbab490e`（"Bind native-wait context offline"），是本 manifested HEAD 的
祖先（`git merge-base --is-ancestor ee6eb888… HEAD`，exit 0）。schema `wksim.ingest-manifest.v1`；scope
`context-only`；acceptance `non-acceptance`。

本 manifest 只把独立审查（review-03）终态 **KEEP** 的三件 gc-freeze 准入候选（历史语境审查文档 +
绑定 ingest note + 离线绑定测试的 remediated 版）连同其独立审查三件按字节收存为**历史上下文批次**。
review-03 裁决 KEEP：两项 dispatched remediation（P2-1、P3-1）均已真正闭合，无 P1、无未决 P2，
P3-2/3/4 为 informational。这是 context-only 收存，**不授予**任何工单（含 #83）的验收、批准、收口、
重跑许可；不授予任何当前速率门状态；不产生任何 native 结果或飞行证据；不把历史语境提升为当前权威。
KEEP 是独立审查对 remediated 候选"维持原样"的裁决，**不是**任何工单的验收。一切"当前是否满足 /
是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类裁决）基于当下工件重新作出。

## 1. 基线关系（祖先锚定 + 区间不相交）

- 架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为 HEAD 祖先
  （`git merge-base --is-ancestor f333316e… HEAD`，exit 0，本会话复核）。
- 写作时历史基线锚 `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` 为 HEAD 祖先（同法 exit 0）。两锚均为
  fail-closed 祖先要求（非精确 HEAD 钉），与套件 `TestArchitectureAncestor` 一致。
- manifested HEAD `cca825b5…` ≠ reviewed HEAD `ee6eb888…`；后者为前者祖先（exit 0）。区间
  `ee6eb888..HEAD` 恰 **1 个 intervening 提交**（`cca825b5`，"Bind G6 architecture applicability
  offline"），触及 **9 条路径**，全部属 architecture-applicability-g6-erratum 主题；与本批 10 路径求交
  （`comm -12` of `git log --name-only ee6eb888..HEAD | sort -u` 与 batch-10 | sort -u）= **0 条
  （zero overlap，程序化复核）**。故 reviewed HEAD 之后的前移不与本批任何路径相交，review-03 证据对本
  manifested HEAD 仍适用。

## 2. 精确路径集合（10 个唯一排序路径 = 3 候选 + 3 审查 + 4 输出）

`exact-paths.txt`（SHA256 `be92931e24459f459d2a3d289ee089b2fa5f11a5a5630f1b75acde5eb9bc4932`，
781 bytes）恰列 10 行、唯一、bytewise（`LC_ALL=C`）排序、LF-only、集合与本任务规定的 10 路径精确相等：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/coordination/codebuddy-gc-freeze-ingest-note-20260914.md` | 绑定与登记 note（remediated） |
| 2 | `docs/coordination/codebuddy-gc-freeze-review-20260912.md` | 历史语境审查文档（2026-09-12） |
| 3 | `validation/coordination/claude-gc-freeze-context-ingest-manifest-20260914-01/SHA256SUMS` | 本 manifest 校验和 |
| 4 | `validation/coordination/claude-gc-freeze-context-ingest-manifest-20260914-01/exact-paths.txt` | staging 契约 |
| 5 | `validation/coordination/claude-gc-freeze-context-ingest-manifest-20260914-01/review.json` | 本 manifest 记录 |
| 6 | `validation/coordination/claude-gc-freeze-context-ingest-manifest-20260914-01/review.md` | 本 manifest 报告 |
| 7 | `validation/coordination/codebuddy-gc-freeze-independent-review-20260914-03/SHA256SUMS` | 独立审查校验和清单 |
| 8 | `validation/coordination/codebuddy-gc-freeze-independent-review-20260914-03/review.json` | 独立审查记录 |
| 9 | `validation/coordination/codebuddy-gc-freeze-independent-review-20260914-03/review.md` | 独立审查报告 |
| 10 | `validation/test_codebuddy_gc_freeze_context.py` | 离线绑定测试（remediated） |

三集合（3 候选 / 3 审查 / 4 输出）两两路径不相交。

## 3. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| codebuddy-gc-freeze-review-20260912.md | `64d0e8766274df1ac8cd8d136ec9300b080bc755e0a1694a1272aae3ad406546` | 10594 |
| codebuddy-gc-freeze-ingest-note-20260914.md | `f68c165fc44e07b22f40b82f3df956dca03f13bea1d4bdcb2d35e3c8808fa853` | 14664 |
| test_codebuddy_gc_freeze_context.py | `91dc7bf443a6ad1117cf59c7cec8a0529ab9d90a5d27cc42ea4a8859669d8b6e` | 38435 |
| review-03 review.md | `922a71a26e11527aeeb0720aa8ef433e45dfc542c1e2e2712a6a4594dc2a6775` | 14314 |
| review-03 review.json | `123643303390a77c2d3a912b3bfa4eda86c80c0ef3ea565c221305ebf816458c` | 10691 |
| review-03 SHA256SUMS | `985a598b1d307694b7d1c1d3d51f87d0c4bceac821ac809678a9cff571031a27` | 154 |

- 6 输入哈希与字节数均现场重算：3 候选与接手任务给定身份逐字一致（remediated 版）；3 件 review-03
  工件重算一致。6 输入全部 untracked（`git ls-files -s` / `git ls-tree HEAD` 各 0 条）。
- review-03 目录 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、review.json OK，exit 0。
- review-03 `review.json` 严格解析通过：`real_repo_head=ee6eb888…`、`verdict=KEEP`、P1 无、P2 无未决、
  P3-1 resolved；Mode A 48/48 OK skipped=2、Mode B 48/48 OK skipped=0（temp index 恰 3 候选）、
  Mode C 48/48 OK skipped=2（scratch clone 自然提交）；real index 字节不变。本 manifest 原样保留
  P3-2/3/4 的 informational 定性，**不提升为 P2、不构成任何批准**。

## 4. 独立审查事实与发现的保真收存（review-03，KEEP）

- **裁决**：KEEP，remediated 三候选维持原样；无 P1；无未决 P2；P3-1 resolved；P3-2/3/4 informational，
  严重级未下调。
- **P2-1（review-02 遗留，resolved）**：`TestArchitectureAncestor.test_genuine_non_ancestor_rejected`
  （`validation/test_codebuddy_gc_freeze_context.py:591-648`）在 repo-external 临时 git 仓建两个无关联
  root commit（`mktree`+`commit-tree`），断言 raw `merge-base --is-ancestor` 对真非祖先 exit **1**、对
  捏造名 exit **128**，并驱动真实 `check_ancestor`（自祖先控制通过、真非祖先 raise；模块级 `git` 仅在
  期间 rebind、`finally` 恢复）。独立 fail-open 探针：control(real) ran=2 failed=0；mutant_exit128_only
  ran=2 failed=1（捕获 P2-1 所述 exit-1 fail-open 回归）；mutant_exit1_only ran=2 failed=1（两负例覆盖
  不同 exit code、非冗余）。
- **P3-1（resolved）**：`TestTemporaryIndex.test_candidates_staged_exactly`（`:805-822`）改断言
  `staged == set(CANDIDATE_PATHS)`（精确相等，非子集），并保留逐候选 stage-0 与 index-blob=工作树字节
  校验。4-entry 超集负控（多暂存 `AGENTS.md`）恰使该一条失败（Ran 48，FAILED failures=1），证明非
  vacuous；正例 exact-3 在 Mode B 绿。
- **P3-2（informational）**：新负例在其期间 rebind 模块级 `git`，`finally` 恢复；顺序 unittest/pytest
  下安全，进程内并行下不安全（套件无此模式，无需改）。
- **P3-3（informational）**：`test_head_drift_boundary` 仍字节钉当前 runner（`c8577093…` / 79221）；
  未来合法 runner 变更需 rebinding 修订（review-02 / note §9.2 已接受）。
- **P3-4（informational）**：Windows 上 Mode C 需 `core.longpaths=true`，否则 checkout 不完整、
  postcommit 运行无意义。
- **remediation 无回归**：除新增负例与收紧的相等断言外无行为变化；invalid-object 负例、字节绑定、
  pinned 快照、A/B/C 生命周期、mutation 负例、nonclosure、#83 边界均不变且三模式全绿。

## 5. 边界事实的收存（不削弱、不提升）

- **历史 23/23**：仅为 pinned 快照三元组（`637c403c`/`cbf7b018`/`fd0b7ee6`）的历史重跑记录；两个主体
  路径在 HEAD 均不存在，非当前执行、非批准、非 #83 证据、非收口（historical pinned evidence only）。
- **D3 已被取代**：当前 tracked 计划（`08e35350`，2026-09-14）的比较器直接消费
  `manager-gc-candidate.json`，**不存在**任何"手造 `gc-freeze.json`"契约；HEAD 比较器 0 处
  gc-freeze/freeze_calls 契约，`resolve_inputs` 于 `:333`。取代而非修复。
- **门与措辞原样保留**：1 ms tick、native barrier、4-tick、no-catch-up、100 ms/全窗、physics/identity
  门均不削弱；诊断场证据永不充当 #83 通过证据；C1 仍是 tracked 假说（无可复现稳态效应、无比较器
  performance_pass 输出）。
- **nonclosure**：note 的 `check_note_boundaries` 通过（必需否定短语俱在、十个升格短语俱无，并经套件外
  大小写不敏感扫描复核）；elevation-mutation 负例仍失败；review 文档 §7 保留 `未通过 / 未证` 清单。
- **#83 不重跑**：plan 当前结论块载 `#83 不重跑`（公共 PV `1w6dru32` 已 CLOSED）与 `C1 仍是假说`；
  note 载 `不是 #83 证据`；套件禁用短语拒绝 `#83 通过`；delivery 保持
  `candidate_source_delivery_not_flight` + `native_started=false`。

## 6. 测试事实（本会话执行 Mode A + Mode B；Mode C 证据由 review-03 保真携带、未重跑）

- **Mode A（normal，真实 index 未动，lifecycle state A pre-admission）**：
  `python -B validation/test_codebuddy_gc_freeze_context.py` → **Ran 48，OK（skipped=2），
  0 failures / 0 errors**，exit 0（2 skip 为 `TestTemporaryIndex`，按设计仅 temp-index 运行生效）。
  真实 index 指纹前后均为 `b76fe210…`。
- **Mode B（exact-3 temp index，repo-external）**：临时 `GIT_INDEX_FILE`（repo 外；
  `git read-tree --empty` 后 `git add -f` 恰好 3 候选；`git ls-files -s` = 恰 3 条、全 stage 0，blob
  `f5f5eb43…` / `a5359247…` / `d1f305a9…`，各等于工作树 `git hash-object`），
  `WKSIM_GC_FREEZE_TEMP_INDEX=1` → **Ran 48，OK（skipped=0）**，exit 0。temp index 已删除；真实 index
  指纹复算不变。
- **Mode C（review-03 证据，本会话未重跑）**：review-03 于 repo-external 单分支 scratch clone
  （`core.autocrlf=false`、`core.longpaths=true`，checkout 干净）自然 `git add`（3 候选）+ `git commit`，
  clone HEAD `2f47e116a822c824f35fbbf8bbd55194bb007779`（parent `ee6eb888…`），`git show --name-only`
  = 恰 3 候选；套件 **Ran 48，OK（skipped=2）**。本 manifest 不重跑 Mode C（无提交许可），仅按
  review-03 §3-C / review.json `test_runs.mode_c` 原样携带其数值，归属 review-03。
- **exact-10 read-tree HEAD 准入（repo-external，独立于 Mode B，不跑套件）**：临时 `GIT_INDEX_FILE`
  （repo 外；`git read-tree HEAD` 后 `git add -f` 恰好 exact-paths.txt 所列 **10 路径**）；临时 index 与
  真实 index 的 `git ls-files` 路径集差 = **恰 10 条新增、0 条移除**；临时 index 从未指向真实 index，
  用后删除。真实 index 指纹复算不变。
- **真实 index 完整性**：`git ls-files -s | git hash-object --stdin` 全程前后均为
  `b76fe21040609ac988dad1737d54209999df131c`；`.git/index` 原始字节 SHA256 写作前
  `7d83f465adfaa9e9e756765823ddf185b2427457e50da0315193aec66f52a712`（会话终态复核不变）。注：本指纹
  与 review-03 记录的 `eed3f181…` 不同，因 HEAD 已前移至 `cca825b5`；本会话内全程恒定。真实 index
  全程未暂存、未变。
- **diff-check（批次范围）**：`git diff --check -- <10 批次路径>` 干净（10 路径均非 tracked 修改，输出空、
  exit 0）；全树 `git diff --check` 仅在受保护脏文件 `docs/Prometheus.gitmodules.reference` 内有**预存**
  trailing-whitespace 告警（本任务之前即存在，非本任务产生，该文件属禁止触碰清单，本 owner 未读改）。

## 7. 边界与非主张

- 未修改本 manifest 四输出之外的任何文件；未暂存、未提交、未推送（真实 index 全程未动；temp index 与
  临时工件均 repo 外，用后删除）。
- 未触碰保护文件 `docs/Prometheus.gitmodules.reference` 与
  `validation/coordination/short-cycle-dispatches.json`（现场重算 = 基线 `5aa70302…` / `06e65cc1…`）；
  未读改禁止清单 `docs/coordination/rolling-six-plan-20260912.md`、
  `docs/coordination/claude-native-wait-next-probe.md`、`validation/_probe_delivery_contract.py`、
  `%TEMP%audit26-report.json`。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未重跑 #83；未查询或改动 GitHub；未用
  `git replace`；未触碰 sibling 项目。
- 本 manifest 是 context-only 收存：不构成 #83（或任何工单）的验收、批准、收口、复核或重跑许可；不授予
  当前速率门状态；不产生 native 结果或飞行证据；不把历史语境（含 23/23）提升为当前权威。KEEP 仅是独立
  审查对 remediated 候选"维持原样"的裁决。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入自引用，由会话终态
  报告记录。
