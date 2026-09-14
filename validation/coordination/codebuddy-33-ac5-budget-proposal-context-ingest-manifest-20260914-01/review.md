# Ingest manifest · CodeBuddy #33 AC5 预算行提案历史语境批次（2026-09-14，context-only）

Owner：codebuddy-ingest-manifest。manifested HEAD
`ee6eb88819cefe255f22e788c39a77c0bbab490e`（会话起止两次复核，写作全程未变）。anchored
独立审查 -01 的 reviewed HEAD 为 `acf322860831cb2a7c83a45cb4e2586922444c57`；本批次不绑定
HEAD 精确值，仅以 ancestry（`31e5b65f…`、`f333316e…`）为身份缝。schema
`wksim.ingest-manifest.v1`；scope `context-only`；acceptance `non-acceptance`。

本 manifest 只把独立审查终态 **KEEP（P1=0、P2=0、P3=1）** 的两件候选（#33 AC5 Q01
每量误差/驻留/恢复预算行提案 + 其离线绑定测试）连同其独立审查三件（-01）按字节收存为
**历史语境批次**。它不构成 #33、#84、Q01、G6、Full 或任何工单的验收、批准、收口、复核
或重跑许可；不授予任何当前速率门或预算状态；不产生任何 native 结果或飞行证据；不把
历史语境提升为当前权威。**待所有者签署的决策保持待决（PENDING OWNER DECISION），P3 措辞
保留不代改**。一切"当前是否满足 / 是否可关闭"的判定由当前权威（主代理 / 主会话 / 人类
裁决）基于当下工件重新作出。

## 0. 批次构成与排除

- 精确批次 = 5 输入 + 4 输出，共 **9 路径**（§2）。输入 = 2 候选 + 独立审查 -01 三件。
- 保护/无关路径**排除且未触碰**（未读改、未暂存）：`docs/Prometheus.gitmodules.reference`
  （M）、`validation/coordination/short-cycle-dispatches.json`（M）、
  `%TEMP%audit26-report.json`、`docs/coordination/claude-native-wait-next-probe.md`、
  `docs/coordination/codebuddy-architecture-applicability-g6-erratum-20260914.md`、
  `docs/coordination/codebuddy-gc-freeze-ingest-note-20260914.md`、
  `docs/coordination/codebuddy-gc-freeze-review-20260912.md`、
  `docs/coordination/rolling-six-plan-20260912.md`、
  `docs/plan/59-g6-owner-decision-request-20260914.md`、`validation/_probe_delivery_contract.py`、
  `validation/e0-g6-owner-decision-request-20260914.json`、
  `validation/test_codebuddy_architecture_applicability_g6_erratum.py`、
  `validation/test_codebuddy_gc_freeze_context.py`。
- 其它批次的全部被取代 review/manifest 目录（含本目录的兄弟批次）均不在本 9 路径批次内，
  本会话未修改、未暂存、未创建。

## 1. 基线关系

- manifested HEAD = `ee6eb888…`（会话起止复核 `git rev-parse HEAD` 未变）；anchored 独立审查
  -01 的 reviewed HEAD = `acf32286…`（**observation only**：`acf32286` 为 `31e5b65f` 的后代，
  故其审查结论按字节落入本批次的 ancestry 区间内）。
- ancestry 锚 `31e5b65f5448c5558450d16d0f46da0ef0f0a03c` 与
  `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 均为 HEAD 祖先
  （`git merge-base --is-ancestor` 退出码 0，本会话复核；-01 亦同法核验）。
- **与区间提交零重叠**：`31e5b65f..HEAD` 共 6 提交（`ab165c3f`、`438ab764`、`acf32286`、
  `e832fd2a`、`615c2f8c`、`ee6eb888`），`f333316e..HEAD` 共 77 提交；
  `git log <anchor>..HEAD -- <exact9>` 在两段区间分别返回**空**——9 路径中无任何一件被区间内
  任何提交增删改；`git ls-tree -r HEAD` 对 9 路径全部返回空（候选与审查/清单工件均未入树），
  真实索引对 9 路径 `git ls-files -s` 为空（未暂存）。
- HEAD equality 不作为批次身份缝；后代提交上套件与字节绑定仍然有效（套件内容断言锚定于
  绝对 ANCESTOR_COMMIT，且专门有守卫测试禁止引入精确 HEAD 常量）。

## 2. 精确路径集合（9 个唯一排序路径 = 2 候选 + 3 审查 + 4 输出）

`exact-paths.txt`（SHA256 `5dec706de737db5f4643162a1d71ebbd46fa2b005eaedee89c2f7edd8b47c495`，
819 bytes，blob `b087dbbd5465ed252d486c1a962100bb4f7e5e9d`）恰列 9 行、唯一（`sort -u` 计数 9）、
bytewise 排序（`LC_ALL=C sort -c` 退出码 0）、末字节 LF（0x0A）、无 CRLF：

| # | 路径 | 角色 |
| --- | --- | --- |
| 1 | `docs/plan/33-ac5-budget-row-proposal-20260914.md` | 候选：Q01 预算行提案 |
| 2 | `validation/coordination/codebuddy-33-ac5-budget-proposal-context-ingest-manifest-20260914-01/SHA256SUMS` | 本 manifest 校验和 |
| 3 | `validation/coordination/codebuddy-33-ac5-budget-proposal-context-ingest-manifest-20260914-01/exact-paths.txt` | staging 契约 |
| 4 | `validation/coordination/codebuddy-33-ac5-budget-proposal-context-ingest-manifest-20260914-01/review.json` | 本 manifest 记录 |
| 5 | `validation/coordination/codebuddy-33-ac5-budget-proposal-context-ingest-manifest-20260914-01/review.md` | 本 manifest 报告 |
| 6 | `validation/coordination/codebuddy-33-ac5-budget-proposal-independent-review-20260914-01/SHA256SUMS` | 独立审查校验和清单 |
| 7 | `validation/coordination/codebuddy-33-ac5-budget-proposal-independent-review-20260914-01/review.json` | 独立审查记录 |
| 8 | `validation/coordination/codebuddy-33-ac5-budget-proposal-independent-review-20260914-01/review.md` | 独立审查报告 |
| 9 | `validation/test_codebuddy_33_ac5_budget_proposal.py` | 候选：离线绑定测试 |

## 3. 输入绑定（全部现场重算，逐字一致）

| 输入 | SHA256 | bytes |
| --- | --- | --- |
| 33-ac5-budget-row-proposal-20260914.md | `998ed98cc668bc36e08acbc401f60e5aa50e356250cd9a82fa6cde5e5c3db5c0` | 5790 |
| test_codebuddy_33_ac5_budget_proposal.py | `9f196f82e0fde227e9ceaae0d5407af5ebdfb195b7d54bc7f00b9269c57d581b` | 14993 |
| -01 review.md | `8f287e2c024bef7924d5421389710e426267a14c628826930dc558b41b92d345` | 10965 |
| -01 review.json | `d00bea931c75e395993c426025620ba996c49af6f51773cc54bf9b83bca9674d` | 3057 |
| -01 SHA256SUMS | `f07b57a5351d06cf3cdafcd7c83ba1d0a85f5a42437c8cce973087c7646f50c1` | 299 |

五项哈希与字节数均与派发任务给定值逐字一致；-01 `SHA256SUMS` 内两行（review.md、review.json）
在本目录内 `sha256sum -c` 通过（`review.md: OK`、`review.json: OK`，退出码 0）。5 输入在本会话
全程字节未变，未被暂存、未被修改、未被重写。对应 blob SHA1：
`2a620fbcb312a50cd07cf320b252711e36443278`（提案）、
`236ecce397302757d3845962024a25f660ebc375`（测试）、
`da1104a0ca01825a708acf747550e7f95d1452df`（-01 review.md）、
`6247fbdaf77dafc99900419a9a8a039a8f5c9316`（-01 review.json）、
`d389d569258b1a17afdafdc68cd73672a7a773fc`（-01 SHA256SUMS）。

## 4. 被收存的审查事实（-01，不改判）

- 终态：**KEEP**；计数 **P1=0、P2=0、P3=1**；`decision_readiness` 不受 P3 影响。
- 唯一 P3-1（`docs/plan/33-ac5-budget-row-proposal-20260914.md:57`，§6 括注）为**措辞澄清**：
  括注可被误读为 PV 第 01–04 轮均带 `RateUnmet`/`numerical_failed` 分类；被引报告中仅第 04 轮
  属墙钟超时类失败（111.68 ms > 100 ms），01–03 轮分别为诊断崩溃、就绪超时、numpy.float32
  JSON 写入失败，且报告未对任何一轮标注这两个 token；`numerical_failed` 属冻结 R1 数值一致性
  状态族（#23/G6 链），括注并未引用该记录。原报告同时确认"保留/不重判"主张本身正确、无失败
  记录被改动。
- **措辞细微差异按原样保留**：本 manifest 只登记该 P3 措辞与建议（点名第 04 轮为墙钟超时样本、
  另行显式引用冻结 R1 记录承载 `numerical_failed`），**不代改措辞、不重判 P3、不将其提升为
  P2、不据此修改任何候选字节**（候选字节 SHA256 仍为 §3 原值）。
- `review_grants_approval=false`；-01 为只读切片，未编辑任何候选或仓库文件，未动真实索引，
  未提交/推送，仅创建其自身三件工件。
- 数值核验（五位跨报告观测最大值、冻结倍率与监督界、7 个 §4 复选框与 3 个 §8 复选框全未勾选、
  范围分离、探针字段排除、非关闭声明）已由 -01 独立核验为准确；本 manifest 不重复裁决，
  仅按字节收存。
- 未决/未签署状态保持：`PENDING OWNER DECISION`（≥6 处）、§8 签署块空白签名/日期行、
  `- [ ]` 全 10 处无勾选；本 manifest **不代签、不关闭 Q01 与 `33:5`**。

## 5. Repo-external 临时索引证（read-tree HEAD + add -f exact9）

方法：`GIT_INDEX_FILE` 指向仓库**外部**的非存在路径
（`C:/Users/PC/AppData/Local/Temp/wksim-tmpidx-33budget-exact9`，`read-tree` 前不存在
（`exists_before=False`），已确认不在 `git rev-parse --show-toplevel` 之下
（`A_outside_repo=True`）），`git read-tree HEAD`（退出码 0）后按 `exact-paths.txt` 逐条
`git add -f` 恰 9 路径；全程不读、不写、不指纹共享真实索引。实测：

| 断言 | 实测 |
| --- | --- |
| `read-tree` 后临时索引条目 | 10 833（= HEAD 树） |
| `add -f` 后临时索引条目 | 10 842（= 10 833 + 9） |
| `git diff-index --cached --name-status HEAD` | **9 行：9 A / 0 M / 0 D** |
| 临时索引中 9 路径条目数 | 9（路径集合与 `exact-paths.txt` 全等） |
| 9 条目 mode | 全 `100644`（非 100644 计数 0） |
| 9 条目 stage | 全 `0`（非 stage-0 计数 0） |
| 9 条目 blob == 工作树字节 | 9/9 一致，mismatch **0** |
| `git diff --cached --check HEAD -- <9 路径>`（空白/冲突检查） | **干净**：输出 0 行，退出码 0 |
| `git diff-index --cached --name-only HEAD -- <9 路径>` | 9 行（9 件对 HEAD 均为新增，符合 9A/0M/0D；非"无变更"） |
| 临时 vs 真实索引路径集合差 | 新增 9、删除 0（10 842 − 10 833 = 9，无删除） |
| `git status --porcelain`（临时索引） | 30 行，其中 9 行为 `A ` 恰为本批次 9 路径 |

- 真实索引前后指纹：`.git/index` sha256
  `38bb9b6cdb2fca67ca8099b7b201f29a06c65d7905181fefeddfae83291fa736`（1 634 702 bytes）、
  `git ls-files -s | sha256` `ffce6973f89f0e1ec49a2fd6ad1c735a48450750b51a946f171c059a6442b7b6`
  （10 833 行）在本会话前后逐字节一致；真实索引对 9 路径 `git ls-files -s` 计数为 0；
  临时索引已删除（`Test-Path` 为 false）。
- 说明：`scoped diff-check clean` 按 `git diff --cached --check` 语义满足（0 行输出 / 退出码 0，
  无空白错误、无冲突标记）；`--name-only` 分支输出 9 行属预期——9 件工件对 HEAD 全部为新增，
  与 9A/0M/0D 同源一致。两者均照实记录，不作选择性表述。
- **终态复验**：四个工件冻结为最终字节后，本节全部断言与 §6 两模式套件均**再跑一次**并保持
  同值（9A/0M/0D、9 条目 stage 0 / mode 100644、blob mismatch 0、空白检查 0 行 / 退出码 0、
  17 tests `OK (skipped=1)` 两模式；真实索引 sha256 前后同为 `38bb9b6c…`）。9 条 staged blob SHA1
  被逐条实测（0 失配），其中 5 件冻结输入的 blob 与本文档所列完全一致；4 件 manifest 输出因
  定稿后字节重写而 blob 自然变化，其权威值可由 `git hash-object` 现场重算。`review.json` 的
  `external_index_proof.staged_blob_sha1` 与 `final_freeze_measurements` 为对应记录，最终数字
  以其定稿后的 `output_bindings.files`（2 件冻结输入）与 `sha256sum -c SHA256SUMS` 为准。

## 6. 测试事实（锚定 -01 结果，本会话复核）

- 命令：`python -B validation/test_codebuddy_33_ac5_budget_proposal.py`（两模式各 **17 tests**）。
- **normal/untracked 模式**：`Ran 17 tests` → `OK (skipped=1)`，退出码 0。跳过者为
  `test_external_index_has_exactly_two_candidates`（按设计仅在 external-index 模式生效）；
  同模式的 `test_untracked_mode_never_touches_any_index` 断言本模式**零**索引触碰 git 调用。
- **external-index 模式**：套件自身契约要求外部索引**恰含两件候选**，故另建一个仓库外部索引
  （`wksim-tmpidx-33budget-candidates`，同样位于仓库外）以 `git add -f` 恰 2 候选
  （`B_temp_entries=2`；两件均 `100644`、stage `0`、blob == 工作树字节，mismatch 0；
  blob 分别为 `2a620fbc…`/`236ecce3…`）。该模式下 `Ran 17 tests` → `OK (skipped=1)`，退出码 0
  （跳过者为本模式的对称项 `test_untracked_mode_never_touches_any_index`）。
  两个临时索引均位于仓库外，均未写入共享真实索引。
- 套件设计：只做 ancestor 断言（无精确 HEAD 常量，守卫测试禁止引入），内容锚定绝对
  ANCHOR_COMMIT 与 7 份来源文档 SHA256/size/内容，写入/网络/native 均为零，不读取未跟踪的
  分类工件，不要求候选保持未跟踪；`_git` 除显式 `ls-files` 外剥离 `GIT_INDEX_FILE`。
- 会话内已实测记录：先以 9 路径外部索引运行 external-index 模式会失败
  （`AssertionError: 10842 != 2`），因为套件断言外部索引恰 2 条目；因此 9 路径索引只用于
  §5 的准入证，套件按自身契约使用 2 条目外部索引。该差异为方法学事实，照实登记。

## 7. 边界与非主张

- 只读离线批次：未编辑任何输入或候选（5 输入字节未变）；未向真实索引暂存；未 commit/push/
  reset/clean/checkout/restore，未改 ref；未触碰兄弟批次目录与 §0 所列保护/无关路径；
  无网络、无 `gh`、无 native/MATLAB/ROS/DDS/UE/SITL/FC/构建/飞行，未重跑 #83。
- 本 manifest 不是验收动作，不提升任何历史语境为批准；不关闭 #33、#84、Q01、G6 或 Full；
  `Full = not-closed`、G0–G6 全 `not-closed` 保持不变；`33:5` 保持未勾选。
- 待所有者签署的决策保持待决：第 3 节五行门槛原值/替代值、0.4 m/s 航点余量、恢复后是否复用、
  每档 ≥3 epoch 要求、加速度前馈、yaw-rate/原生边界、G6 每量预算，均**未决**。

## 8. 输出工件

- `exact-paths.txt`：SHA256 `5dec706de737db5f4643162a1d71ebbd46fa2b005eaedee89c2f7edd8b47c495`，
  819 bytes；9 行唯一、C 排序（`LC_ALL=C sort -c` 退出码 0）、LF 结尾、无 CRLF。
- `review.md`（本文件）：报告；其 SHA256/字节数与 blob SHA1 由同目录 `review.json` 的
  `output_bindings.files` 权威记录（本文件不自引用哈希，避免循环修订）。
- `review.json`：本批次记录；其 SHA256/字节数与 blob SHA1 同样记于
  `output_bindings.files`（自哈希在最终字节确定后计算，`review.md` 不再回写，故无循环）。
- `SHA256SUMS`：覆盖 `exact-paths.txt`、`review.md`、`review.json` 三行，**不自引用**；
  其自身 SHA256 与 blob SHA1 亦记于 `review.json` 的 `output_bindings.files`。
- 现场复核命令：`sha256sum -c SHA256SUMS` 于本目录（相对路径）应全部 `OK`。
