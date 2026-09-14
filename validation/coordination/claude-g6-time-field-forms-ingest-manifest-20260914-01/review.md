# Ingest manifest · G6 time-field-forms 离线路次（2026-09-14-01，offline evidence/tool，独立审查 GO / 非验收）

Owner：claude-ingest-manifest。manifested HEAD `0b10f786e808eebe7698e9a277766bf2f68a4d35`
（"Bind GC-freeze review context offline"，branch `main`；写作全程 HEAD 未变，`git rev-parse HEAD`
现场复核），仅作 **manifested 观测值** 记录，**不是** 绑定钉。独立审查
claude-g6-time-field-forms-independent-review-20260914-01 的 observed HEAD 同为
`0b10f786e808eebe7698e9a277766bf2f68a4d35`（与 manifested HEAD 相同，区间为空，见 §1）。
schema `wksim.ingest-manifest.v1`；scope `offline-evidence-tool-delivery`；acceptance `non-acceptance`。

本 manifest 把已完成并经独立审查（review-01）终态 **GO** 的 G6 time-field-forms 离线路次四件候选
（独立结构核对器 + 确定性结果文档 + 离线测试套件 + 计划文档）连同其独立审查三件，按字节收存为
**离线证据/工具交付批次**。这是 offline evidence/tool delivery，**不授予** 任何工单（含 #59、#84、
G6、Full）的验收、批准、收口或重跑许可；**不是** 批准的逐量预算；**不是** G6 物理验收；**不产生**
任何 native 结果或飞行证据。GO 是独立审查对该离线路次交付质量的裁决，**不是** 任何工单的验收。
一切"当前是否满足 / 是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类裁决）基于当下工件重新作出。

## 1. 基线关系（祖先锚定 + 证据路径不相交；从不要求精确 HEAD 相等）

- 架构连续性锚 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 为 HEAD 祖先
  （`git merge-base --is-ancestor f333316e… HEAD`，exit 0，本会话复核）。该锚为 fail-closed 祖先
  要求（非精确 HEAD 钉），与候选生成器自身的溯源门一致。
- reviewed HEAD `0b10f786…` **等于** manifested HEAD `0b10f786…`（`git merge-base --is-ancestor
  0b10f786… HEAD`，exit 0；一提交对自身为祖先）。区间 `0b10f786..HEAD` **0 个 intervening 提交**，
  触及 **0 条路径**，与本批 11 路径求交 = **0 条（trivially zero overlap）**。故 reviewed HEAD 之后
  无任何前移，review-01 证据对本 manifested HEAD 直接适用。
- **诚实声明**：reviewed HEAD 与 manifested HEAD 相等只是**观测到的巧合**，**从不作为要求**。真正
  的绑定是 fail-closed 的 f333316 祖先锚 + 被钉住证据路径的稳定性；因此 HEAD 在锚的任何干净后代
  之间漂移时本 manifest 仍正确（`head_equality_required=false`）。
- **候选证据路径不相交**：六个被钉住的证据路径在锚→HEAD 区间**全部无变化**（`git diff f333316e..HEAD
  -- <path>` 逐路径为空，本会话复核；锚→HEAD 区间不触及其中任何一条）。这复刻了候选生成器自身的
  fail-closed pinned-path-overlap 门（review-01 检查 2/3），证明被复审证据在 manifested HEAD 仍有效：
  - `validation/e0-major-recorder-parent-final-01/record.jsonl`
  - `Simulator/wksim_core/numerical-conformance-v1.json`
  - `validation/coordination/major-time-acceptance-20260913-01/verification.json`
  - `validation/coordination/major-time-acceptance-20260913-01/initial-assumption-rejected.json`
  - `validation/coordination/major-time-acceptance-20260913-01/verify_times.py`
  - `docs/2026-09-13-major-time-conventions.md`

## 2. 精确路径集合（11 个唯一排序路径 = 4 候选 + 3 审查 + 4 输出）

`exact-paths.txt`（SHA256 `ed8ef7fd3541d86e80b8191eb7622bd5f896499ebe89585e38846d7f33e01356`，
814 bytes）恰列 11 行、唯一、bytewise（`LC_ALL=C`）排序、LF-only（0 个 CR 字节），集合与本任务规定的
11 路径精确相等：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/plan/59-g6-time-field-forms-20260914.md` | 计划文档（候选） |
| 2 | `tools/check_g6_time_field_forms.py` | 独立结构核对器（候选） |
| 3 | `validation/coordination/claude-g6-time-field-forms-independent-review-20260914-01/SHA256SUMS` | 独立审查校验和清单 |
| 4 | `validation/coordination/claude-g6-time-field-forms-independent-review-20260914-01/review.json` | 独立审查记录 |
| 5 | `validation/coordination/claude-g6-time-field-forms-independent-review-20260914-01/review.md` | 独立审查报告 |
| 6 | `validation/coordination/claude-g6-time-field-forms-ingest-manifest-20260914-01/SHA256SUMS` | 本 manifest 校验和 |
| 7 | `validation/coordination/claude-g6-time-field-forms-ingest-manifest-20260914-01/exact-paths.txt` | staging 契约 |
| 8 | `validation/coordination/claude-g6-time-field-forms-ingest-manifest-20260914-01/review.json` | 本 manifest 记录 |
| 9 | `validation/coordination/claude-g6-time-field-forms-ingest-manifest-20260914-01/review.md` | 本 manifest 报告 |
| 10 | `validation/g6-time-field-forms-20260914.json` | 确定性结果文档（候选） |
| 11 | `validation/test_check_g6_time_field_forms.py` | 离线测试套件（候选） |

三集合（4 候选 / 3 审查 / 4 输出）两两路径不相交。**注意**：11 路径中 7 条（3 审查 + 4 输出，均位于
`validation/coordination/<dir>/` 下）被 `.gitignore` 第 53 行 `/validation/*/` 忽略；4 件候选未被忽略；
故准入须 `git add -f`（见 §6）。

## 3. 输入绑定（7 件全部现场重算）

| 输入 | SHA256（现场重算） | bytes | git blob |
| --- | --- | --- | --- |
| tools/check_g6_time_field_forms.py | `23ad9e9263632d2d070726c113573ee0ced6a373712a2e48a12977304d8d1607` | 99822 | `520583cb…` |
| validation/g6-time-field-forms-20260914.json | `bf87ef7e2c0b6f2ea69b51ab18c92089741858ac32be50c26a09b437cb13b37d` | 117396 | `e4370b25…` |
| validation/test_check_g6_time_field_forms.py | `d5bd68b69e1d15d45cc6e36c90413f24004d39ffb72f739e0cb8b8481236b40c` | 71982 | `cd2799a9…` |
| docs/plan/59-g6-time-field-forms-20260914.md | `780b01713e7f029445f4d2176b900d5bc71aff4f2236d5470ab869b7ae62ef01` | 9248 | `1d8f3fd7…` |
| review-01 review.md | `a9947f0e57eb66c4d73743d63a0d333bcba83de8dc73a1fa221aaab6431d8387` | 6832 | `45d4319e…` |
| review-01 review.json | `0f4746b910298b37d2b7ef04b692b2e683299d520897c6a54bc6f88f0c6f8750` | 6498 | `beb47077…` |
| review-01 SHA256SUMS | `32a8d7504e5cdc56a5e9ebb67d78c9991ec5f1e4989a0d217ee708c686c599b9` | 434 | `12fcdce4…` |

- 7 输入哈希与字节数均现场重算；**4 件候选与 review-01 记录的重算值逐字一致**（`matches_expected_hash`
  皆 true）；3 件 review-01 工件重算入表。7 输入全部 untracked（`git ls-files -s` / `git ls-tree HEAD`
  各 0 条）。
- review-01 目录 `SHA256SUMS` 以 `sha256sum -c` 复核：因其列出的是**仓库相对**候选路径
  （`tools/…`、`validation/…`、`docs/plan/…`），故自**仓库根**运行，4/4 OK、exit 0。
- review-01 `review.json` 严格解析通过：schema `wksim.independent-review.g6-time-field-forms.v1`，
  `verdict=GO`，observed_head=`0b10f786…`，anchor=`f333316e…`，4 候选皆 match，8/8 检查全 pass。

## 4. 独立审查事实的保真收存（review-01，GO）

- **裁决**：**GO**；审查者 claude-opus-4.8 (1M context) 作为独立终审；日期 2026-09-14；对象 issue #59
  G6 time-field-forms 离线候选。证据为独立重导（只读 git、内存重建、自建沙箱仓、独立 AST/import 扫描）；
  测试套件被执行但其断言未替代人工检视。GO **不是** 工单验收，不授予任何批准。
- **8/8 检查全过**：①锚为 observed HEAD 祖先；②六条钉住证据路径锚→HEAD 无变化、无精确 HEAD 要求；
  ③fail-closed 负探针 18/18（非祖先 / 探针不可用 / observed HEAD=None / 缺原始输入 / 缺 tracked 证据 /
  pinned-path overlap）；④离线 hygiene（import 仅 stdlib，唯一 subprocess 程序为 git，子命令仅
  `ls-tree`/`rev-parse`/`merge-base`/`diff`，无 index/state 改动动词、无网络或模拟器面）；⑤内存重建 JSON
  字节一致、`validate` ok=true、决策面干净（见 §5）；⑥普通 unittest 68 OK（skipped=2）；⑦repo-external
  `GIT_INDEX_FILE` exact4 运行 68 OK、real index/HEAD 保持；⑧四候选哈希复核不变。
- **候选哈希**：4 件候选 recompute 全部 match expected，全部 untracked。

## 5. 边界事实的收存（非验收，不削弱、不提升）

- **离线证据/工具交付**：本批只是调度证据（三个 `schedule_metadata` 时间槽的乘积写法 `(k*0.001)*gain`
  与除法写法 `(k/1000)*gain`）的结构核对交付；动力学与物理预算（三数组其余 118 个非时间槽、任何
  绝对/相对误差预算、任何物理量精度）**未评估、未界定、未批准**。
- **证据 JSON 决策面**（schema `wksim.59-g6-time-field-forms.v1`，`status=ok`，`block_reason_codes=[]`，
  `base_ancestor=f333316e…`）：`authority="none"`、`effective=false`、`r1_status="numerical_failed"`、
  `g6_acceptance=false`、`physical_accuracy=false`、`issues_closed=false`、`budget_approved=false`、
  `pending_approvals=[]`、`open_items` 中 issue_84/g6/full 全 `open`、
  `evidence_class_split.evaluated_here=false`、`observed_head_recording="deliberately_not_recorded"`。
- **非批准的逐量预算**：`budget_approved=false`，无 forbidden budget/acceptance/closure 键。
- **非 G6 物理验收**：`g6_acceptance=false`、`physical_accuracy=false`；`r1_status` 仍 `numerical_failed`。
- **非 #84/Full 收口**：`issues_closed=false`；`open_items` issue_84/g6/full 全 `open`。
- **无 native 结果**：未运行任何模型、可执行体或求解器，仅重新解码已封存字节；不触发任何
  MATLAB/Simulink/native/ROS/DDS/SITL/flight/UE/build 执行；**#83 不重跑**。
- **门不削弱**：本 manifest 仅新增一个离线核对器，不削弱任何现有速率/物理/身份门，不授予当前门状态。

## 6. 测试事实与本会话核验（验收范围严格区分）

**独立测试事实（自 review-01 保真携带、本会话未重跑）**：以下 68 测试套件数值均为独立审查者
（claude-opus-4.8）本人的运行，本 manifest **未重跑** 该套件，仅按 review-01 §6/§7 与 review.json
checks 6/7 原样携带并归属 review-01：

- **普通模式**：`python -B -m unittest validation.test_check_g6_time_field_forms` → **68 tests，
  OK（skipped=2）**，exit 0；2 个 skip 为 `TestExact4TempIndex`（仅 temp-index 下有意义）。
- **repo-external `GIT_INDEX_FILE` exact4**：repo 外临时 index 仅 force-add 4 件候选；4 条 staged、
  全 stage 0、mode 100644、blob git-id 与 SHA256 皆等于工作树字节；套件 **68 tests，OK**，两个
  `TestExact4TempIndex` 测试本次运行并通过；real index 前后皆 `cf249890…`、HEAD 前后皆 `0b10f786…`。

**本会话核验（本 owner 自做，只读 / repo-external，与上面携带的套件事实相区分）**：

- **exact-11 read-tree HEAD 准入（repo-external，独立于 exact4，不跑套件）**：临时 `GIT_INDEX_FILE`
  （repo 外；`git read-tree HEAD` 后 `git add -f` 恰好 exact-paths.txt 所列 **11 路径**）；临时 index 与
  真实 index 的 `git ls-files` 路径集差 = **恰 11 条新增、0 条移除**；全 stage 0；staged blob 与工作树
  字节一致；临时 index 从未指向真实 index，用后删除。
- **真实 index 完整性**：`git ls-files -s | git hash-object --stdin` 全程前后均为
  `0d1d6e82938d145689e3f2d47bbda081918922bd`；`.git/index` 原始字节 SHA256 全程前后均为
  `cf249890d18567a9f62173ff1e8ac717362fe531ecea02a545a72ee185319a32`（与 review-01 记录的 real-index
  值一致；本会话内恒定）。HEAD 全程前后均为 `0b10f786…`。真实 index 全程未暂存、未变。
- **diff-check（批次范围）**：`git diff --check -- <11 批次路径>` 干净（11 路径均非 tracked 修改，输出空、
  exit 0）；全树 `git diff --check` 仅在受保护脏文件 `docs/Prometheus.gitmodules.reference` 内有**预存**
  trailing-whitespace 告警（本任务之前即存在，非本任务产生，该文件属禁止触碰清单，本 owner 未读改）。

## 7. 边界与非主张

- 未修改本 manifest 四输出之外的任何文件；未暂存、未提交、未推送（真实 index 全程未动；temp index 与
  临时工件均 repo 外，用后删除）。
- 未触碰保护文件 `docs/Prometheus.gitmodules.reference` 与
  `validation/coordination/short-cycle-dispatches.json`（现场重算 = `5aa70302…` / `06e65cc1…`，与既有
  基线一致）；未读改其它 agent 的 untracked 与脏文件。
- 未运行 model/MATLAB/Simulink/ROS/DDS/SITL/FC/UE/build/native/飞行；未重跑 #83；未查询或改动
  GitHub；未用 `git replace`；未触碰 sibling 项目。
- 本 manifest 是 offline evidence/tool delivery 收存：**不是** 批准的逐量预算、**不是** G6 物理验收、
  **不是** #84/Full 收口、**不产生** native 结果；不构成 #59（或任何工单）的验收、批准、收口、复核或
  重跑许可。GO 仅是独立审查对该离线路次交付质量的裁决。
- 当前 HEAD `0b10f786…` 仅作 manifested 观测；真正绑定是 fail-closed 的 f333316 祖先锚 + 钉住证据
  路径稳定性，**从不要求精确 HEAD 相等**。
- 68 测试套件数值自 review-01 原样携带并归属之，本 manifest **未重跑**；本会话自做核验仅限只读 /
  repo-external（输入重算、review 解析、祖先核验、exact-11 准入、real index/HEAD 字节同一、批次
  diff-check、SHA256SUMS 校验）。
- SHA256SUMS 仅覆盖 `exact-paths.txt`、`review.md`、`review.json`；其自身哈希不入自引用，由会话终态
  报告记录。
