# Ingest manifest · CodeBuddy audit-matrix 历史上下文批次（2026-09-14-02，context-only，P2 生命周期修复后复核批次）

Owner：codebuddy-ingest-manifest。manifested HEAD
`438ab764c0cf70f9e017cfbd82aeb04255282e3a`（会话起止两次 `git rev-parse HEAD` 复核，写作
全程未变）；被收存独立审查 `codebuddy-audit-matrix-independent-review-20260914-02` 的
authoritative head 为 `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（即 remediated note/test
的权威写作 HEAD）。区间 `31e5b65f..438ab764` 含 **2 个 intervening 提交**，
`git diff --name-only 31e5b65f..HEAD` 与本批 10 路径**不相交**（grep 审计无命中）。任务
仅要求后裔关系：`31e5b65f` 与架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`
均为 HEAD 祖先（`git merge-base --is-ancestor` 各自退出码 0，会话起止复核）。

本 manifest 只把 remediated audit-matrix 批次的三件准入候选（2026-09-12 审计矩阵历史
语境审查文档 + 2026-09-14 生命周期修复版绑定 ingest note + 离线绑定测试 -02）连同其
独立审查 -02 三件按字节收存为**历史上下文批次**。这是 context-only 收存，**不授予**
任何工单（含 #83）的验收、批准、收口、复核或重跑许可；不授予任何当前速率门状态；不产生
任何 native 结果或飞行证据；不把历史语境提升为当前权威。一切"当前是否满足 / 是否可
关闭"的判定由当前权威（主代理 / 主会话 / 人类裁决）基于当下工件重新作出。

## 1. 生命周期修复与取代关系（P2 修复批次）

- **P2 修复内容**：note -02（`7fa1bdcc…`，16071 bytes）§8 步骤 5/6 与测试 -02
  （`59fd4eaa…`，30616 bytes）把 `GIT_INDEX_FILE` staged 校验从原"恰 3 路径"改为
  **候选子集语义**（3 个候选路径全部在场、恰一次、mode `100644`/stage `0`、blob 与
  工作区字节一致；允许额外的独立复核/manifest 路径存在）。暂存集的**恰路径等式**由此
  manifest 强制（本目录 `exact-paths.txt` 的 10 路径集合相等证明，见 §2/§5）。
- `codebuddy-audit-matrix-independent-review-20260914-01`：**superseded**（其审查后候选
  note/test 字节变更），未触碰、未收存、排除在外。
- `codebuddy-audit-matrix-context-ingest-manifest-20260914-01`：**superseded/blocked**
  保持不变，其失败结论不变；本批次不使之一合格，未触碰、排除在外。
- 独立审查 -02 目录 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、
  review.json OK，退出码 0。

## 2. 精确路径集合（10 个唯一排序路径 = 6 输入 + 4 输出）

`exact-paths.txt`（SHA256
`ec96760a8ba3a69b820c75bc62ac4e1bf704c5979b6cf7e537ff15eb6447af38`，837 bytes）恰列
10 行、唯一、bytewise（`LC_ALL=C sort -c` 通过）排序、集合与本任务规定的 10 路径精确
相等：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/coordination/codebuddy-audit-matrix-review-20260912.md` | 历史语境审查文档（2026-09-12 审计矩阵复核快照） |
| 2 | `docs/coordination/codebuddy-audit-matrix-review-ingest-note-20260914.md` | 绑定与登记 note（生命周期修复版） |
| 3 | `validation/coordination/codebuddy-audit-matrix-context-ingest-manifest-20260914-02/SHA256SUMS` | 本 manifest 校验和 |
| 4 | `validation/coordination/codebuddy-audit-matrix-context-ingest-manifest-20260914-02/exact-paths.txt` | staging 契约 |
| 5 | `validation/coordination/codebuddy-audit-matrix-context-ingest-manifest-20260914-02/review.json` | 本 manifest 记录 |
| 6 | `validation/coordination/codebuddy-audit-matrix-context-ingest-manifest-20260914-02/review.md` | 本 manifest 报告 |
| 7 | `validation/coordination/codebuddy-audit-matrix-independent-review-20260914-02/SHA256SUMS` | 独立审查校验和清单 |
| 8 | `validation/coordination/codebuddy-audit-matrix-independent-review-20260914-02/review.json` | 独立审查记录 |
| 9 | `validation/coordination/codebuddy-audit-matrix-independent-review-20260914-02/review.md` | 独立审查报告 |
| 10 | `validation/test_codebuddy_audit_matrix_review_context.py` | 离线绑定测试（候选子集语义版） |

排除项核验：`docs/Prometheus.gitmodules.reference`、
`validation/coordination/short-cycle-dispatches.json`、
`docs/coordination/rolling-six-plan-20260912.md`、
`docs/coordination/claude-native-wait-next-probe.md`、
`validation/_probe_delivery_contract.py`、`%TEMP%audit26-report.json` 均不在上述
10 路径内且本任务全程未读改；取代的 -01 review/manifest 两目录（各 7 文件）不在批次内、
未触碰。

## 3. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| codebuddy-audit-matrix-review-20260912.md | `fbb2568bea73167997ee62782fb71f1aba98dd54cd3e2f99108c591f41abcbf1` | 5805 |
| codebuddy-audit-matrix-review-ingest-note-20260914.md | `7fa1bdcc2c210e3e6e3fbe76be1dded409abd793f66c2b643753712962b8f22c` | 16071 |
| test_codebuddy_audit_matrix_review_context.py | `59fd4eaa8d1ba35abf246b890a5db8ac979b00b2297ac3a8631f0e607b19a106` | 30616 |
| review-02 目录 review.md | `2ad5d3efbdc50b252a5af4d15269db2caa1d7414630081edee5e63cf068076df` | 8271 |
| review-02 目录 review.json | `3a24895c6ee105eebcc436cd4f35b2bf1897c7b68d2895feb6888cc869dd7f39` | 10183 |
| review-02 目录 SHA256SUMS | `4b374c8197b08cd2e25c9513a502425b57b164a0b040807c8da3de67361d1a25` | 154 |

- 6 输入哈希与字节数均现场重算：3 候选与任务给定身份逐字一致（review 文档为任务要求
  的全量复算；note/test 与给定 SHA256+size 逐字一致）；review-02 三件重算一致，且与
  review-02 `SHA256SUMS` 自记值一致。
- review-02 目录 `SHA256SUMS` 自检通过（`sha256sum -c`：review.md OK、review.json OK，
  退出码 0）。
- 独立审查 -02 `review.json` 严格解析通过（拒绝重复键/非有限常量）：authoritative head
  `31e5b65f…`、`verdict=ADOPT`、`P1=0、P2=0`、恰 3 项 P3（非阻塞）、normal 31 ran OK、
  10 路径生命周期证明（temp index 恰 10 条、均 100644/stage 0、blob 一致）31 ran OK。

## 4. 独立审查事实与发现的保真收存

- **裁决**：ADOPT，remediated 批次按原样准入；无 P1 / 无 P2；三项 P3（信息性/守卫深度
  限制，无需本批次动作），严重级未下调：
  - **P3-1**：`assert_no_promotion`（测试 PROMOTION_PATTERNS）为英文正则，note 主体为
    中文，中文提升措辞不会被该 regex 捕获；人工读无提升措辞。守卫深度限制，非本批次
    缺陷。
  - **P3-2**：`test_note_registers_line_drift` 断言裸子串 `"86"`，匹配面宽，弱于漂移
    登记检查；实际行锚由 `require_literal(SESSION_REL, "def accept(self, request):")`
    强制。表述性。
  - **P3-3**：候选子集语义下，套件不再检测过宽暂存批（额外路径静默通过）；恰路径等式
    按设计（note §8 步骤 5、测试 docstring）交由 manifest/final verifier 强制——本
    manifest §2/§5 的 exact-paths 集合相等证明即该强制点的本次履行。
- **边界原样保留**（不改判、不提升）：被绑定 review 文档为只读历史记录（F1–F5、
  boundary 判定均非当前权威）；note 只做历史语境绑定与漂移登记，拒绝一切验收/收口语义；
  外部 WSL run-02 工件保持 declaration-only；1..127 PX4 水位数字 declaration-only；
  #83 保持 CLOSED/PASS、从未重跑，本 manifest 全程未重跑；#84/G6/Full 保持未完成。

## 5. 测试与暂存事实（本会话执行）

- **run 1（normal）**：`python -B validation/test_codebuddy_audit_matrix_review_context.py`，
  正常工作树、真实 index 未动 → **Ran 31 tests, OK**，0 failures / 0 errors，exit 0。
- **run 2（repo 外私有临时 index，恰 10 批次路径，自当前 HEAD 播种）**：`mktemp -d`
  repo 外目录内私有 `GIT_INDEX_FILE`；先 `git read-tree HEAD`（自当前 HEAD `438ab764`
  播种），再 `git add -f` 恰好 `exact-paths.txt` 所列 10 路径（7 个 gitignored
  coordination 文件需 `-f`；候选 3 件 untracked，同样 `-f` 加入）。证明链：
  - **10 A / 0 M / 0 D**：`git status --porcelain`（临时 index）首列恰 10 个 `A`、
    0 个 staged `M`、0 个 staged `D`；`git diff --cached --name-status HEAD`（临时
    index）恰 10 行 `A`，无 M/D。
  - **恰 10 条、stage 0**：`git ls-files --stage`（临时 index）恰 10 条，全部
    mode `100644`、stage `0`。
  - **blob-equal**：10 条 staged sha1 逐条等于对应工作区字节 `git hash-object`（含
    `.gitattributes` `* -text` 下无 EOL 平移）。
  - **diff-check clean**：`git diff --cached --check`（临时 index）输出空、退出码 0。
  - **31/31**：同一临时 index staged 状态下运行同套件 → **Ran 31 tests, OK**，0
    failures / 0 errors，exit 0（P2 修复后该 10 路径状态为设计内通过态；对照 -01 批次
    时此状态被旧 exact-3 校验拒绝）。
  - **临时目录用后删除**；真实 index 全程未暂存。
- 真实 index 完整性：`git ls-files -s | sha256sum` 会话前后均为
  `5de63e159c44d37a72acfecee8c178ab154b80b00d36cb9130588e9042f5a8ef`；`.git/index` 原始
  字节 SHA256 首测 `327b22366c0ba7cb1e3fbddc8cd41023541b92f3cea745af754aba1b41862976`、
  终测复算一致；`git diff --cached --stat` 会话首测与终测均为空。会话前 2 个 intervening
  提交使 `ls-files -s` 哈希不同于 -02 审查记录的 `5e08ccab…`（该值对应 `31e5b65f`
  现场），语义上均为各自 HEAD 的干净 index。
- **diff-check（批次范围，真实 index）**：10 路径均为 untracked 新增，非 tracked 修改。

## 6. 边界与非主张

- 未修改本 manifest 四输出之外的任何文件；未暂存、未提交、未推送（真实 index 全程未动，
  无 reset/clean）；未触碰任何 ref/commit。
- 未触碰保护文件 `docs/Prometheus.gitmodules.reference` 与
  `validation/coordination/short-cycle-dispatches.json`（其预存状态先于本任务）；未读改
  禁止清单 `docs/coordination/rolling-six-plan-20260912.md`、
  `docs/coordination/claude-native-wait-next-probe.md`、
  `validation/_probe_delivery_contract.py`、`%TEMP%audit26-report.json`。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未重跑 #83；未查询或改动
  GitHub；未联网。
- 本 manifest 是 context-only 收存（no-promotion 限制）：不构成 #83（或任何工单）的
  验收、批准、收口、复核或重跑许可；不授予当前速率门状态；不产生 native 结果或飞行
  证据；不把历史语境提升为当前权威；门与措辞（1 ms tick、native barrier、4-tick、
  no-catch-up、100 ms/全窗、physics/identity 门）原样保留、不削弱。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入
  自引用，由会话终态报告记录。
