# Precommit / 干净检出闭包审计 — Full 原始 AC 缺口账本

- 切片：`cursor-full-ac-precommit-audit-20260914-01`
- 锚定 HEAD：`6eafdf9c0b734db07a9fe790c86b409d3468c10b`（`main`）
- 祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`：exit 0
- 只读候选：`docs/plan/full-original-ac-gap-ledger-20260914.md`、`validation/full-original-ac-gap-ledger-20260914.json`、`validation/full-original-ac-gap-ledger-snapshot-20260914.json`、`validation/test_full_original_ac_gap_ledger.py`
- **总体：PASS** — 0 P1 / 0 P2 / 3 P3。最小提交集是四次普通 `git add`，`git add -f` 为空。Windows 与 Ubuntu-22.04 均在干净树上复核 **81/81**，提交后 blob 与工作区字节一致且 81/81 仍过。65 条非 AC 行没有进入 `omitted_acs`。

这不是 owner 批准，也不重开/关闭任何 issue，也不把 G0–G6 或 Full 写成已关闭。

```text
工作类别           : read-only precommit / clean-checkout audit
                     （非新架构验收、非历史对照晋升、非 owner 批准）
cwd / 分支 / HEAD  : C:/Users/PC/Documents/odid编译/wksim / main
                     6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先           : git merge-base --is-ancestor
                     f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> exit 0
module / interface : Full 原始 AC 缺口账本（只读）；heading-stack 总量、
                     omitted_acs 与非 AC 隔离、普通 add / force-add、
                     可弃用树 HEAD/blob 断言
独占写入           : validation/coordination/cursor-full-ac-precommit-audit-20260914-01/**
只读输入           : 四份候选；
                     cursor-full-ac-gap-ledger-finalize-20260914-01/**
                     cursor-full-ac-gap-ledger-final-review-20260914-01/**
                     cursor-full-ac-gap-ledger-repair-takeover-20260914-01/**
验证               : git archive HEAD 成员核验 + 路径限定可跑树；
                     Windows / Ubuntu-22.04 代表套件与新鲜 81/81
范围外             : 候选编辑；GitHub 写入；主树 add/commit/stage/reset/clean；
                     native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE /
                     构建 / 飞行 / #83
```

本界面不可选 `gpt-5.6-luna` / `gpt-6-astra`。审查在主代理完成，没有改用其他子代理模型顶替。

已读：`CONTEXT-MAP.md`、`wksim/CONTEXT.md`、`wksim/AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`validation/coordination/cursor-full-ac-gap-ledger-finalize-20260914-01/review.md`。父仓 `docs/adr/*` 不自动约束 wksim；本切片也没有本地 ADR。

## 1. 门控表

| 门 | 判定 | 证据 |
| --- | --- | --- |
| 候选 SHA-256 等于钉值 | **PASS** | 四哈希全程一致；接管 SHA256SUMS 28/28 绑定同一组 |
| 独立总量 38 / 255 / 190 / 65 / 40 / 150 / 22 / 8 / 8 | **PASS** | heading-stack 复算，不用候选 `EXPECTED_*` 当神谕 |
| 65 非 AC 未进入 `omitted_acs` | **PASS** | 65 个 `{n}:x{k}`；队列 61 条 omitted 全是 AC 形 id |
| `full_program` / G0–G6 未宣称关闭 | **PASS** | 全部 `not-closed`；`claims_acceptance=false` |
| 必须 `git add -f` 的忽略未跟踪运行依赖 | **PASS（空集）** | `force_add_required=[]` |
| archive + 四候选、无 git | **PASS（代表）** | Ubuntu 16/16；Windows 首轮 15/16 仅夹具错名，更正后 16/16 |
| archive + 四候选 + 可弃用 git | **PASS** | Windows 81/81（8.681 s）；Ubuntu-22.04 81/81（1.075 s） |
| 可弃用树提交后 HEAD/blob | **PASS** | 四次普通 add；blob 与工作区字节一致；两侧再跑 81/81 |
| 主仓未被改写 | **PASS** | 项目 HEAD 仍为 `6eafdf9`；四候选仍为 `??` |
| 本审计总体 | **PASS** | 最小提交集 = 四次普通 `git add` |

## 2. 冻结哈希（独立重算，未漂）

| 路径 | SHA-256 | 字节 | 忽略 | HEAD |
| --- | --- | ---: | --- | --- |
| `docs/plan/full-original-ac-gap-ledger-20260914.md` | `5a4d9a649abeb57b423d98b84fdf8c59c965afd74a92ba88061ee48a1c44ad3e` | 25570 | 否 | 否 |
| `validation/full-original-ac-gap-ledger-20260914.json` | `4e1f9b9e80ce07265c4b25cca6fc084a200a18051536d2b3f3243c5b79fd1d16` | 225429 | 否 | 否 |
| `validation/test_full_original_ac_gap_ledger.py` | `d2a241c97c50549e2aae9226163a61f3445787f886b04eeae42fcf74af7367a1` | 75771 | 否 | 否 |
| `validation/full-original-ac-gap-ledger-snapshot-20260914.json` | `c8af0dcef3dfc3a78141d381a9cb307fc5a0a223cc9c2898a5a34fd0ffae1ef4` | 91924 | 否 | 否 |

与 finalize / 接管 81 回执钉值一致。工作区含 CRLF（快照 400 CR / 400 LF）。项目 `core.autocrlf=false`，普通 `git add` 会原样入库。

## 3. 独立总量（heading-stack）

| 量 | 值 |
| --- | --- |
| issues（#11–#48） | 38（编号和 1121） |
| CLOSED / OPEN | 30 / 8 |
| raw checkboxes | **255** |
| 原始 AC | **190** |
| 节外 checkbox | **65** |
| 已勾选 AC | **40** |
| 未勾选 AC | **150** |
| CLOSED 仍有未勾选 AC | **22** — 13, 14, 18, 19, 21, 22, 25, 30, 31, 32, 35, 36, 37, 38, 40, 41, 42, 43, 44, 45, 47, 48 |
| OPEN 仍有未勾选 AC | **8** — 20, 26, 27, 28, 29, 33, 39, 46 |
| CLOSED 且 AC 全勾选 | **8** — 11, 12, 15, 16, 17, 23, 24, 34 |

全勾选只表示正文打勾，不是能力已复核。`omitted_acs` 共 61 条，全部是 `{issue}:{k}`，与 65 个 `{issue}:x{ordinal}` 不相交。

## 4. 最小提交清单

`.gitignore:53` `/validation/*/` 只匹配 `validation/` 下的**目录**。四份候选本身**不被忽略**，普通 `git add` 即可。

**必须 `git add -f` 的忽略、未跟踪、且为运行所必需的文件：无。**

账本 `cited_sources` 里已在 HEAD 的路径（含已被忽略但早已跟踪的 `validation/46-reexecution` 等目录）进入 `git archive HEAD`，不必再次 force-add。DeepSeek 协调目录与本审计目录都不是运行依赖。

套件用 `git check-ignore --no-index` 与 `git ls-files --error-unmatch` 判断 ignored+untracked；证据钉的 `blob_sha1` 由文件字节推导，不是 `git show HEAD:`。账本 / 快照里的 `head` 是捕获时的提交钉，**不是**“候选提交后当前 HEAD 必须仍为 `6eafdf9`”。

见 `minimal-commit-manifest.txt`。本审计没有在主仓执行这些命令。

## 5. 干净检出仿真

完整 `git archive HEAD` 已在 Windows 上产出：`%TEMP%\wksim-head-archive-probe.tar`，**5 971 220 480 字节**，`ls-tree` 成员 **10370**。四候选与四个 advisory 协调目录都不在 HEAD。该 tar 约 6 GiB，不解包进审计目录。

可跑树：`git archive HEAD -- .gitignore + cited_sources`（781 成员，545 413 120 字节）再只覆盖四候选。这仍是 HEAD 归档内容，只是去掉与本套件无关的 UE/固件大文件。

| 主机 | 树 | 无 git 代表 | 挂上 disposable git | 可弃用提交后 |
| --- | --- | --- | --- | --- |
| Windows 3.13.11 | `%TEMP%\wksim-full-ac-precommit-win-5txcbxeq` | 首轮 15/16（夹具错名）；更正后 16/16 | **81/81 OK，8.681 s** | **81/81 OK，8.602 s**；HEAD `875ca9a0…` |
| Ubuntu-22.04 3.10.12 | `/tmp/wksim-full-ac-precommit-lin-cchiab3o` | **16/16 OK，1.004 s** | **16/16 + 81/81 OK，1.075 s** | **81/81 OK，0.715 s**；HEAD `47022330…` |

无 git 时 `path_is_ignored_untracked` 的 git 调用在 stderr 打 `fatal: not a git repository`，返回“非 ignored-untracked”。代表套件仍 PASS。这是分类精度问题，不是 81 项内容失败。

可弃用树内四次普通 `git add` 退出码 0，`git add -f` 未使用。提交后 `git show HEAD:<候选>` 的 SHA-256 与工作区钉值相同。主仓 HEAD 未变，四候选仍未跟踪。

代表套件（16 项）：总量、抽取一致、HEAD/快照钉、counts、fail-closed、exact sets、CLOSED 不等于履行、非 AC 不计入、`omitted_acs`、证据钉 / blob、cited sources、队列可达、计划文档、HEAD 改写变异、omission 丢失变异。

## 6. 先验 81/81（哈希绑定，另加本轮新鲜复核）

接管 `cursor-full-ac-gap-ledger-repair-takeover-20260914-01`：SHA256SUMS **28/28**，Windows / Ubuntu 记录 81/81 + 隔离 81/81，四哈希等于当前候选。本轮**没有只复用**该回执：两侧都在干净树上重新跑了 81。

## 7. 按严重度排列的发现

无 P1。无 P2。

### P3 — F-full-archive-too-large-to-extract

完整 `git archive HEAD` 约 5.97 GiB。可跑闭包用路径限定归档 + 四候选即可证明最小提交集。不要把 6 GiB tar 纳入候选或本收据。

### P3 — F-git-helpers-are-classification-not-content

无 `.git` 时套件仍能靠文件存在性通过代表项；`path_is_ignored_untracked` 在无仓库时恒为假。要做 ignored+untracked 的真实分类，或做提交后 blob 探针，才需要可弃用 git 元数据。这不是第四个要 force-add 的文件。

### P3 — F-representative-fixture-wrong-class

Windows 第一次把 `test_totals_match_literal_constants` 挂到 `SnapshotIntegrityTests`。方法在 `ExtractorsAgreeTests`。更正后 16/16。候选未改。

finalize 留下的 `_accept_ledger` helper 宽度说明仍是历史 P3，本轮没有重跑 helper 变异，也不把它升级或关闭。

## 8. 非声称

通过本审计或 81 项套件，不批准 owner 项，不关闭/重开任何 issue，不把 G0–G6 或 Full 写成已关闭。未重跑 #83，未做 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行。主仓无 `git add` / commit / stage / reset / clean。可弃用树里的 commit 只用于 blob 探针，不是项目提交。
