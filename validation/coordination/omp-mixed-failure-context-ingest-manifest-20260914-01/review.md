# Ingest manifest · OMP mixed-failure 历史上下文批次（2026-09-14，context-only）

Owner：codebuddy-ingest-manifest（接任；前任已终态取消，写入权已移交，残留输出经审计
后由本 owner 修正/补全）。manifested HEAD `4b13e7efaa19348d383c1c9d95af12348bac3087`
（"Bind startup cost context offline"）；独立审查 reviewed HEAD
`011818876c1b94875fd67cedaaa73abfac866633`（"Bind OMP delivery diagnostic context
offline"）。schema `wksim.ingest-manifest.v1`；scope `context-only`；acceptance
`non-acceptance`。写作全程 HEAD 未变。

本 manifest 只把独立审查终态 PASS 的三件套（两份历史语境文档/绑定 note + 一份离线绑定测试）
连同其独立审查三件按字节收存为**历史上下文批次**。它不构成 #83（或 #9/#26/#29/#62/#102 或
任何工单）的验收、批准、收口、复核或重跑许可；不授予任何当前速率门状态；不把历史语境提升为
当前权威。一切"当前是否满足 / 是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类裁决）基于
当下工件重新作出。

## 0. 前任残留审计（接手记录）

- 前任仅产出两文件：`exact-paths.txt`（SHA256
  `e86e278cad646dd419b272bc87be09e42896e0f1407e685545b71fb40a3f6946`，803 bytes）与
  `review.md`（SHA256
  `3b9e386a9da2c585e52ea14929a6950d7e56e9e00634829078e1f697f5bc2779`，5811 bytes），
  均与接手任务给定指纹逐字一致；`review.json` 与 `SHA256SUMS` 缺失。
- `exact-paths.txt` 经程序化审计：恰 10 行、唯一、`LC_ALL=C`（bytewise）排序、集合与本
  任务规定的 10 路径精确相等——**正确，本 owner 原样保留**（哈希不变）。
- 前任 `review.md` 内容自洽，但其锚定 manifested HEAD `011818876…` 并断言"审查基线与
  manifested HEAD 之间零 intervening 提交"。该断言在 `4b13e7ef` 落地后**已过期**；由本
  owner 重写（见 §1），并以本文件取代前任版本。

## 1. 基线关系（祖先锚定，不要求 HEAD equality）

- 独立审查三件的 reviewed HEAD = `011818876…`；本 manifest 的 manifested HEAD =
  `4b13e7ef…`。`git merge-base --is-ancestor 011818876… HEAD` 退出码 0（本会话复核）。
  测试套件与本 manifest 均只锚祖先关系，**不要求 HEAD 相等**，后代提交上套件仍然有效。
- 架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为 HEAD 祖先（退出码 0，本会话
  复核）。
- **区间核验（本会话）**：`git diff --name-status 011818876…..4b13e7ef…` 恰含 1 个提交
  （`4b13e7ef` "Bind startup cost context offline"），新增**恰好 11 条 startup 路径**
  （ds-startup-cost 证据两文档 + 其 ingest note + 独立审查三件 + ingest-manifest 四件 +
  `validation/test_ds_startup_cost_evidence_context.py`），全部含 "startup" 字样，与本批
  10 路径**不相交**（程序化集合断言），且不触碰任何保护文件。manifested_head 因此更新为
  `4b13e7ef`。

## 2. 精确路径集合（10 个唯一排序路径 = 6 输入 + 4 输出）

`exact-paths.txt`（SHA256 `e86e278cad646dd419b272bc87be09e42896e0f1407e685545b71fb40a3f6946`）
恰列 10 行、唯一、bytewise（`LC_ALL=C`）排序：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/coordination/omp-mixed-failure-ingest-note-20260914.md` | 绑定与取代登记 note |
| 2 | `docs/coordination/omp-mixed-failure-review-20260913.md` | 历史语境文档（2026-09-13 只读复核） |
| 3 | `validation/coordination/codebuddy-omp-mixed-failure-independent-review-20260914-01/SHA256SUMS` | 独立审查校验和清单 |
| 4 | `validation/coordination/codebuddy-omp-mixed-failure-independent-review-20260914-01/review.json` | 独立审查记录 |
| 5 | `validation/coordination/codebuddy-omp-mixed-failure-independent-review-20260914-01/review.md` | 独立审查报告 |
| 6 | `validation/coordination/omp-mixed-failure-context-ingest-manifest-20260914-01/SHA256SUMS` | 本 manifest 校验和 |
| 7 | `validation/coordination/omp-mixed-failure-context-ingest-manifest-20260914-01/exact-paths.txt` | staging 契约 |
| 8 | `validation/coordination/omp-mixed-failure-context-ingest-manifest-20260914-01/review.json` | 本 manifest 记录 |
| 9 | `validation/coordination/omp-mixed-failure-context-ingest-manifest-20260914-01/review.md` | 本 manifest 报告 |
| 10 | `validation/test_omp_mixed_failure_context.py` | 离线绑定测试 |

## 3. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| omp-mixed-failure-review-20260913.md | `2417c299d57ccdc79b7368e03180bd0b767aabb91c012257e1443a17fca331c3` | 4448 |
| omp-mixed-failure-ingest-note-20260914.md | `92f8adf24faf0ba924ed402c2f07a4b0a2ef68f2583639f38e8f1a7bd67862a4` | 9762 |
| test_omp_mixed_failure_context.py | `e13cfc72d44a4cd878f77ad3a95abcacea4003859c6458aa0f8f0000cef5f9fd` | 15148 |
| review 目录 review.md | `15cd3d97051f31a94de02e5f0a85b47d1eb78e7baf77eb3a75de6699c2245e2e` | 9713 |
| review 目录 review.json | `a8cfb38a54f2fd5120987eceb460813c1e0b93e2ee3d18ceb393f415acad8bc9` | 11698 |
| review 目录 SHA256SUMS | `ca4be7e0899f2bfe9f52bfbfdb736b99c8662c2392019fb48cb5b49df5ee9ef4` | 154 |

- 6 输入哈希与字节数均现场重算，与接手任务给定值逐字一致；6 输入本任务全程未修改。
- review 目录 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、review.json OK，
  退出码 0。
- 独立审查 `review.json` 严格解析通过：`reviewed_head=011818876…`、`verdict=PASS`、
  `P1=0、P2=0`、恰好 **4 项 P3**（P3-1 ~2.9µs 口径未标；P3-2 睡眠 2,050.6/2,107.3ms 本地不可
  复核；P3-3 "同场同身份" 歧义；P3-4 测试 `import re` 位置易碎）。本 manifest 原样保留 4 项
  P3 的非阻塞定性，**不提升为 P2、不构成任何批准**。

## 4. 测试事实（本会话两轮重跑）

- **run 1（normal）**：正常工作树、真实 index 未动 → **20/20 OK**，0 failures / 0 errors，
  exit 0。
- **run 2（staged）**：临时 `GIT_INDEX_FILE`（repo 外临时文件；`git read-tree HEAD` 后
  `git add -f` 恰好 exact-paths.txt 所列 **10 路径**；临时 index 与真实 index 的
  `git ls-files -s` 路径集差 = 恰 10 条新增、0 条移除）→ **20/20 OK**，exit 0；临时 index
  已删除。说明：前任未产出 `review.json`/`SHA256SUMS`，首次 run 2 因此缺 2 路径而失败
  （git exit 128，无副作用）；四输出补全后重跑通过。
- 真实 index `git ls-files -s | sha256sum` 两轮前后不变（均为
  `93ce9851638511abce6baa649f20f8948c8ba36f4b2ec699170af9429e3d822e`）；真实 index 全程
  未暂存。
- **diff-check**：`git diff --check` 对除保护文件
  `docs/Prometheus.gitmodules.reference` 外的全部路径干净（exit 0）；该保护文件的 24 行
  trailing-whitespace 告警全部来自其**预存未提交修改**（本会话开始前即存在，非本任务产生，
  且该文件属禁止触碰清单，本 owner 未读改）。
- 套件设计（独立审查记录 + 本 owner 浏览复核）：仅祖先断言、路径经 `__file__` 解析、
  无写入/网络/native、不读取 untracked 分类工件、不要求候选保持未跟踪。

## 5. 边界与非主张

- 未修改任何输入或输出目录之外的文件；未暂存、未提交、未推送（真实 index 全程未动）。
- 未触碰保护文件 `docs/Prometheus.gitmodules.reference` 与
  `validation/coordination/short-cycle-dispatches.json`（未读、未改；其预存 `M` 状态非本
  任务产生）。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未重跑 #83；未查询或改动 GitHub。
- 门与措辞原样保留（1 ms/4-tick/no-catch-up/100 ms/全窗/run 内单调差分；诊断场永不得充当
  #83 通过证据；mixed 能力证明行仍 MISSING）。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入自引用，
  由会话终态报告记录。
