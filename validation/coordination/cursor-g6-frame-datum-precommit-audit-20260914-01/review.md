# Precommit / clean-checkout audit — G6/B2 frame/datum 终稿

- 切片：`cursor-g6-frame-datum-precommit-audit-20260914-01`
- 锚定 HEAD：`6eafdf9c0b734db07a9fe790c86b409d3468c10b`（`main`）
- 祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`：exit 0
- 只读候选：`docs/plan/59-e0-frame-datum-binding-20260914.md`、`validation/e0-frame-datum-binding-20260914.json`、`validation/test_e0_frame_datum_binding.py`
- **总体：PASS** — `git archive HEAD` 加上三份未忽略候选，再在可弃用树内挂上锚定 HEAD 的 git 元数据后，Windows 与 Ubuntu-22.04 的有界代表套件均为 12/12。没有必须 `git add -f` 的额外忽略工件。先验 45/45 捕获仍绑定当前三哈希，未重跑。

这不是 owner 批准，也不是 #59 / #60 / G6 / Full 关闭，R1 仍为 `numerical_failed`。

```text
工作类别           : read-only precommit / clean-checkout audit
                     （非新架构验收、非历史对照晋升、非 owner 批准）
cwd / 分支 / HEAD  : C:/Users/PC/Documents/odid编译/wksim / main
                     6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先           : git merge-base --is-ancestor
                     f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> exit 0
module / interface : G6/B2 e0 动态槽 frame/datum 绑定；validate_binding /
                     完整 RHS 身份 / counts 重算 / observables[] 精确字段 /
                     注入 manifest 缺失活动路径 / 重复 JSON 键
独占写入           : validation/coordination/cursor-g6-frame-datum-precommit-audit-20260914-01/**
只读输入           : 三份候选；
                     cursor-g6-frame-datum-p2-finalize-20260914-01/**
                     cursor-g6-frame-datum-p2-repair-20260914-01/**
                     cursor-g6-frame-datum-p2-repair-takeover-20260914-01/**
验证               : 仓库外 git archive 干净树；Windows 与 Ubuntu-22.04
                     代表 unittest；先验 45/45 只核哈希
范围外             : 候选编辑；GitHub 写入；主树 commit/stage/reset/clean；
                     native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE /
                     构建 / 飞行 / #83
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审查在主代理内完成，没有改用其他子代理模型顶替。

已读：`AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`。

## 1. 门控表

| 门 | 判定 | 证据 |
| --- | --- | --- |
| 候选 SHA-256 等于派发钉 | **PASS** | `3fbb0e7f…` / `5d589075…` / `e412f2d1…`，全程 LF |
| 先验 45/45 绑定当前哈希 | **PASS** | 5/5 哈希行一致；未重跑全量 |
| `git archive` + 仅三候选、无 git | **FAIL（预期）** | 两侧 10 failed / 2 passed；`git show HEAD:` 缺失 |
| archive + 三候选 + 可弃用 git | **PASS** | Windows 12/12（51.964 s）；Ubuntu-22.04 12/12（34.062 s） |
| 活路径独立核验 | **PASS** | 两侧 pristine 0；RHS / counts / observables / manifest 注入 / 重复键 |
| 必须 force-add 的忽略工件 | **PASS（空集）** | `force_add_required=[]` |
| 陈旧写入器缺席是干净检出依赖 | **PASS（否）** | archive / 覆盖树中均无；套件仍 PASS |
| 主仓未被改写 | **PASS** | 项目 HEAD 仍为 `6eafdf9` |
| 本审计总体 | **PASS** | 干净检出最小提交集 = 三次普通 `git add` |

## 2. 冻结哈希（独立重算，未漂）

| 路径 | SHA-256 | 字节 | 忽略 | HEAD |
| --- | --- | ---: | --- | --- |
| `docs/plan/59-e0-frame-datum-binding-20260914.md` | `3fbb0e7fbdbc069a702dd0e8417c9b6a8dd3961575d5a188817990b280b553f8` | 15449 | 否 | 否 |
| `validation/e0-frame-datum-binding-20260914.json` | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | 105018 | 否 | 否 |
| `validation/test_e0_frame_datum_binding.py` | `e412f2d1981fd02b34531426f31c6f010c96d15331bf41f30fc136cc59f10da6` | 77146 | 否 | 否 |

与 finalize、repair mutation、takeover mutation / reuse / after-delete 全部带哈希行一致。

## 3. 最小提交清单

`.gitignore:53` `/validation/*/` 匹配 `validation/` 下的**目录**。三份候选本身**不被忽略**，普通 `git add` 即可。

**必须 `git add -f` 的忽略、未跟踪、且为运行所必需的文件：无。**

23 个 `EXPECTED_PINS` 均已在 HEAD。其中两个命中忽略规则，但早已被跟踪，并出现在 `git archive HEAD` 中：

1. `validation/coordination/ds-g6-budget-evidence-20260913-01/audit.json`（`g6_budget_audit`）
2. `validation/coordination/luna-g6-frontier-20260914-01/review.md`（`g6_frontier_review`）

它们必须保持跟踪；本次候选提交不必再次 force-add。

校验器**从不哈希工作区 pin 字节**，只读 `git show HEAD:`。因此可弃用树还需要指向锚定提交的 git 元数据。这是运行时依赖，不是要入库的第四个文件。

见 `minimal-commit-manifest.txt`。本审计没有执行 `git add` / commit。

## 4. 干净检出仿真

方法：`git archive --format=tar HEAD` 解到仓库外临时目录，再只复制三份候选。不在主仓 `worktree add` / `clone` / `reset` / `clean`。

| 主机 | 树 | archive 成员 | 覆盖后无 git | 挂上 disposable git |
| --- | --- | ---: | --- | --- |
| Windows 3.13.11 | `%TEMP%\wksim-g6-fd-precommit-win-3ow_453i` | 与 Ubuntu 同源 HEAD | 10 failed / 2 passed | **12/12 OK，51.964 s** |
| Ubuntu-22.04 3.10.12 | `/tmp/wksim-g6-fd-precommit-lin-itb248hc` | 12085；无 `.git`；无三候选；无 `write_binding.py`；两个忽略 pin 在内 | 10 failed / 2 passed | **12/12 OK，34.062 s** |

无 git 时的失败一律是 `… is not tracked at committed HEAD` 或 `path_not_tracked_at_head`。`test_counts_match_payload` 与 `test_duplicate_json_key_fails_closed` 不走 `git show`，故无 git 也能过。

代表套件（12 项，未重跑 45）：

- 干净 payload：`test_committed_file_is_valid`
- HEAD / 祖先：`test_head_and_baseline`
- counts：匹配、谎报、多键/缺键
- 精确 RHS：篡改、子串 `Product`、12 个敌对身份
- `observables[]` 精确字段
- 注入 manifest 去掉 `Vehicle60[3]` 的活动缺失路径
- 重复 JSON 键

独立 live-path（两侧 PASS）：pristine 0 错；`Exp1_MinModelTemp_B.Product[2]` 命中；12/12 敌对拒绝；counts `56 / 25 / 31 / 10 / 46 / 24`；`m/s` / EV-13 / EV-14 精确命中，前缀/后缀/blob 返回 `quote_not_exact_observables_field`；注入后 HEAD manifest 仍干净。

Windows 第一次 `objects/info/alternates` 因文本解码得到 `objects?` 失败；在**已解压**的同一临时树上用 `--absolute-git-dir` 字节路径恢复。这是本审计夹具问题，不是候选缺陷。项目仓 HEAD 未变。

## 5. 先验 45/45（只核哈希，未重跑）

| 捕获 | 平台 | 结果 | 当前三哈希 |
| --- | --- | --- | --- |
| repair pytest / unittest | Windows | 45 passed / Ran 45 OK；字节等于 takeover `reuse-windows.json` | 一致 |
| takeover pytest / unittest | Ubuntu-22.04 | 45 passed in 495.52 s / Ran 45 OK in 475.493 s | 经 after-delete 与 mutation 绑定 |
| repair / takeover mutation 等 5 行 | 两侧 | 5/5 哈希可用 | 一致 |

repair 第一轮 Ubuntu 420 s 超时仍只作历史 FAIL，不抵消接管 45/45。

## 6. 陈旧写入器

`validation/coordination/codebuddy-g6-frame-datum-20260914-01/write_binding.py` **不在 HEAD、不在 archive、不在覆盖后的干净树**。删除记录哈希 `56df93cc…` 与 finalize / postreview-takeover 一致。

干净树上代表套件与 live-path 在**没有**该文件时为 PASS。因此它的缺席是 P2 终审事实，不是干净检出必须额外覆盖或 force-add 的依赖。`__pycache__/write_binding.cpython-313.pyc` 与 codebuddy `SHA256SUMS` / `notes.md` 残留不构成运行依赖。

## 7. 按严重度排列的发现

### I1 — F-git-runtime-not-a-blob

`validate_binding` 始终 `git show HEAD:`。仅 archive + 三候选不能跑代表套件。需要的是可弃用 git 元数据，不是第四个要提交的忽略文件。

### I2 — F-ignored-pins-already-tracked

两个 coordination pin 被 `/validation/*/` 命中，但已在 HEAD 且进入 archive。不要把它们写进本次 force-add 清单；也不要从跟踪集删掉。

### I3 — F-stale-writer-not-a-dependency

`write_binding.py` 缺席不是干净检出前置条件。套件不导入它。

### I4 — F-windows-alternates-encoding

Windows 夹具第一次挂 git 失败后已在同一解压树上恢复。候选未改。

## 8. 非声称

通过本审计或代表套件，不批准 owner 项，不关闭 #59 / #60 / G6 / Full，不改判 R1 `numerical_failed`。未重跑 45 项、#83，未做 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行。主仓无 `git add` / commit / stage / reset / clean。
