# Ingest manifest · CodeBuddy owned-scheduling 历史语境批次（2026-09-14，context-only）

Owner：codebuddy-ingest-manifest。manifested HEAD
`31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（会话起止两次复核，写作全程未变，与独立审查
-01 的 reviewed HEAD 相同，区间为空）。schema `wksim.ingest-manifest.v1`；scope
`context-only`；acceptance `non-acceptance`。

本 manifest 只把独立审查终态 **PASS/ADOPT（P1=0、P2=0）** 的两件候选（owned-scheduling
绑定/登记 ingest note + 离线绑定测试）连同其独立审查三件（-01）按字节收存为**历史语境
批次**。它不构成 #83（或 #84/G6/Full 或任何工单）的验收、批准、收口、复核或重跑许可；
不授予任何当前速率门状态；不产生任何 native 结果或飞行证据；不把历史语境提升为当前
权威。一切"当前是否满足 / 是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类裁决）
基于当下工件重新作出。

## 0. 批次构成与排除

- 精确批次 = 5 输入 + 4 输出，共 **9 路径**（§2）。输入 = 2 候选 + 独立审查 -01 三件。
- 保护/无关路径**排除且未触碰**（未读改、未暂存）：`docs/Prometheus.gitmodules.reference`、
  `validation/coordination/short-cycle-dispatches.json`、
  `docs/coordination/rolling-six-plan-20260912.md`、
  `docs/coordination/claude-native-wait-next-probe.md`、
  `validation/_probe_delivery_contract.py`、`%TEMP%audit26-report.json`。
- 其它批次的全部被取代 review/manifest 目录均不在本 9 路径批次内，本会话未修改、未暂存。

## 1. 基线关系

- 本 manifest 的 manifested HEAD = 独立审查 -01 的 reviewed HEAD =
  `31e5b65f…`（-01 `review.json` 的 `authoritative_head` 字段即该值，`head_confirmed=true`）；
  会话起止复核 `git rev-parse HEAD` 未变。
- 架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为 HEAD 祖先
  （`git merge-base --is-ancestor` 退出码 0，本会话复核；-01 亦同法核验）。
- HEAD equality 不作为批次身份缝；后代提交上套件与字节绑定仍然有效
  （套件内容断言锚定于绝对 ANCHOR_COMMIT）。

## 2. 精确路径集合（9 个唯一排序路径 = 5 输入 + 4 输出）

`exact-paths.txt`（SHA256
`da50faabe22f292f2119abc727e2fb533305a38c841741ddfdf82192a6e2e9e2`，789 bytes）恰列
9 行、唯一、bytewise（`LC_ALL=C sort -c` 通过）排序、LF 结尾无 CRLF：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/coordination/codebuddy-owned-scheduling-ingest-note-20260914.md` | 候选：绑定与登记 ingest note |
| 2 | `validation/coordination/codebuddy-owned-scheduling-context-ingest-manifest-20260914-01/SHA256SUMS` | 本 manifest 校验和 |
| 3 | `validation/coordination/codebuddy-owned-scheduling-context-ingest-manifest-20260914-01/exact-paths.txt` | staging 契约 |
| 4 | `validation/coordination/codebuddy-owned-scheduling-context-ingest-manifest-20260914-01/review.json` | 本 manifest 记录 |
| 5 | `validation/coordination/codebuddy-owned-scheduling-context-ingest-manifest-20260914-01/review.md` | 本 manifest 报告 |
| 6 | `validation/coordination/codebuddy-owned-scheduling-independent-review-20260914-01/SHA256SUMS` | 独立审查校验和清单 |
| 7 | `validation/coordination/codebuddy-owned-scheduling-independent-review-20260914-01/review.json` | 独立审查记录 |
| 8 | `validation/coordination/codebuddy-owned-scheduling-independent-review-20260914-01/review.md` | 独立审查报告 |
| 9 | `validation/test_owned_scheduling_context.py` | 候选：离线绑定测试 |

## 3. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| codebuddy-owned-scheduling-ingest-note-20260914.md | `a8559e33f75d4475a4756787ab724b3c3338db4df8832a8fed6037c7d0da75a7` | 10688 |
| test_owned_scheduling_context.py | `07d5f11be9d6e83198a51828bc503e83a1f2c5ea3697120753cf0ed4a2f2a884` | 23376 |
| -01 review.md | `9d2acc9c0cc7e67775c13da6797f8600be2622cd9591af6d6f9c35e1ddddb75c` | 10850 |
| -01 review.json | `0a9e173f4bf17fb3936e7afc167b021e5cdf3cee4a24c10e4177a89081bdba5d` | 6790 |
| -01 SHA256SUMS | `93e4650def55edf87aaf9ed6d6a684abc8ad7511a6e29db41f991fef4be64a00` | 154 |

- 5 输入哈希与字节数均现场重算，与任务给定值逐字一致；5 输入本任务全程未修改。
- -01 `SHA256SUMS` 以 `sha256sum -c` 在其目录内复核：review.md OK、review.json OK，
  退出码 0。
- -01 `review.json` 严格解析通过：`authoritative_head=31e5b65f…`、
  `verdict=PASS/ADOPT`、`P1=0、P2=0、P3=3`、`all_identities_recomputed=true`、
  `real_index_mutated=false`。
- 本会话独立抽查：真实 index 对 5 输入路径 `git ls-files -s` 返回空（无一被暂存；
  候选未跟踪，`validation/*` 由 gitignore 覆盖，docs note 未跟踪）。

## 4. 独立审查 -01 终态（本 manifest 不改判）

-01 判定 **PASS/ADOPT**（规则：仅当 P1==0 且 P2==0）。无 P1、无 P2；三项 P3 原样登记：

1. **P3-1**：note §8 为显式占位，把最终 SHA/计数器委托给批次报告；其 §1/§2 表格完整且
   已被独立核验。
2. **P3-2**：候选测试钉住 note 的 NOTE_SHA256/NOTE_SIZE；未来 note 编辑需重钉两个常量
   （已登记的耦合）。
3. **P3-3**：40 项采集中 31 项计数源自 2026-09-13 复核文档（parametrize 展开）未重跑；
   18/23 def 计数经直接核验且一致。

本 manifest 原样保留该定性，**不提升、不改判、不构成任何批准**。-01 的边界与非主张
（diagnostic_only、full_acceptance=false、flight_completed=false、
performance_verdict=not_evaluated、历史测试钉 20cc4590/19740B 不得作为当前事实引用、
历史尾值不转移至当前 HEAD）全部原样承继。

## 5. 测试事实

- **run 1（normal）**：`python -B validation/test_owned_scheduling_context.py`
  正常工作树、真实 index 未动 → **Ran 25 tests, OK (skipped=1)**，24 通过 / 1 预期跳过
  （`TestStagedIndexMode.test_staged_index_contract` 在无 `GIT_INDEX_FILE` 时按设计不
  激活），0 failures / 0 errors，exit 0。
- **run 2（staged，恰 9 路径）**：临时 `GIT_INDEX_FILE`（repo 外 `mktemp` 文件；
  `git read-tree HEAD` 后 `git add -f` 恰好 exact-paths.txt 所列 **9 路径**；临时 index
  与真实 index 的 `git ls-files` 路径集差 = 恰 9 条新增、0 条移除；临时 index 全程不
  触碰真实 index）→ **Ran 25 tests, OK**，25/25，exit 0；临时 index 用后删除。
  - 自指说明：run 2 执行时本 review.md/review.json 的 run 结果字段仍为 PENDING 占位；
    staged-index 契约测试只绑定两候选拍 blob（与工作树字节逐字一致、全程未变），且
    9 路径集合相等断言与字节无关，故恰 9 路径收编对最终输出字节同样成立。
- 真实 index 完整性：`.git/index` 文件字节哈希 run 前
  `a7fd6154535cbcde789c99d6ee5f38097d914323453dde5d5ad97b1da09e9253`、run 后相同；
  `git ls-files -s | sha256sum` 前后均
  `5e08ccabec2775053b28f34e44eedd55db1a8b37ef8b4d895023d651f4b835ef`（与邻批
  module-review manifest 记录值一致）→ 真实 staged 集合逐字节不变、全程未暂存。
  `git status --porcelain`：本 manifest 四件输出创建前后逐行相同（22 行，哈希均
  `3958957ea18a84fdd337168fcdc123c1d85d5cfa2d6b88d633fdac23a78b78b4`；全部输出位于
  gitignore 覆盖的 `validation/coordination/`，不出现在 status 中）→ 本任务输出对
  status 零扰动。会话起点（`d5da1742f56c36ab59ea4083e01a11d78144abcdd8830fc5ad1fe0d57b206d10`）
  与输出创建之间的差异由**并发第三方会话**修改
  `docs/coordination/mixed-work-overrun-20260913-v2.md` 造成（mtime 2026-09-14
  20:16:23，落在本会话窗口内；该路径不属本批次，本任务未读改、未暂存）。
- 套件设计（-01 审查记录 + 本 owner 复核源码）：内容断言锚定绝对
  `ANCHOR_COMMIT=31e5b65f…`、安全漂移跳过、路径经 `__file__` 解析、无写入/网络/native、
  不读取 untracked 分类工件、不要求候选保持未跟踪；staged 模式额外断言两候选在外部
  index 的 blob == 工作树字节且不在真实 index。

## 6. 边界与非主张

- 未修改任何输入或输出目录之外的文件；未暂存、未提交、未推送（真实 index 全程未动）；
  无 reset/clean。
- 未触碰 §0 所列六个保护/无关路径；其它批次的被取代目录未触碰。
- 未运行 native/构建/MATLAB/ROS/DDS/SITL/FC/UE/模型/飞行；未重跑 #83；未查询或改动
  GitHub；未联网。
- 门与措辞原样保留（1 ms tick、native barrier、4-tick、no-catch-up、100 ms/全窗、
  physics/identity 门）；诊断场结果永不得充当 #83 通过证据。
- 本批次为 context-only 收编：不授予 #83/#84/G6/Full 验收/批准/收口/重跑、不授予当前
  速率门状态、不产生 native 结果或飞行证据。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入
  自引用，由会话终态报告记录。
