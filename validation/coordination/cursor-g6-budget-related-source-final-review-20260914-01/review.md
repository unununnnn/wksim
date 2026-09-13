# G6 budget related/SOURCE_HEAD P2 修复 — 独立差量终审

切片：`cursor-g6-budget-related-source-final-review-20260914-01`  
判定：**PASS**  
工作类别：independent differential final review（只读三份 budget 候选；仅写本目录）  
cwd / 分支 / HEAD：`C:\Users\PC\Documents\odid编译\wksim` / `main` / `6eafdf9c0b734db07a9fe790c86b409d3468c10b`  
祖先：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0  
来源钉祖先：`git merge-base --is-ancestor 6eafdf9c0b734db07a9fe790c86b409d3468c10b HEAD` → exit 0

独占写入：本目录。未改三份 budget 候选或三份 frame 候选，未覆盖 P2 修复回执、frame 终审回执或其它历史回执，未 `git add/commit/stage/reset/clean`，未启动 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行，未重跑 #83，未重复 Windows 153 全量。未留下临时脚本。

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审查在主代理内完成，没有改用其他子代理模型顶替。

已读：`AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`，以及 `cursor-g6-budget-related-source-p2-repair-20260914-01` 与 `cursor-g6-budget-frame-final-review-20260914-01`。

## 派发核验

| 项 | 值 |
| --- | --- |
| module / interface | E0 budget 台账 `validate()`：related `id/path/sha256` 精确冻结；`SOURCE_HEAD` 缺失/非祖先拒绝码 |
| 只读候选 | 三份 budget；对照只读三份 frame |
| 只读证据 | `cursor-g6-budget-related-source-p2-repair-20260914-01/**`、`cursor-g6-budget-frame-final-review-20260914-01/**` |
| 新跑 | Windows 与 Ubuntu-22.04 各一次：`RelatedSourceP2RepairTests` 14 项 + 17 条定向 hostile |
| 复用 | budget↔frame 两顺序 × after-both/after-empty 的 8 份 30 代表 txt，以及 empty `commit-tree` 信封；独立重算并核对 P2 `SHA256SUMS` |
| 验收资源 | 不宣称 owner 批准，不关闭 #59/#10/G6/Full |

## 当前候选哈希（独立重算，未改字节）

三份 budget 与三份 frame 均为 LF。`PACKAGE_SHA256` 只钉台账与计划文，等于工作树。测试模块不自哈希。frame 三份仍等于 frame 终审值。

| 路径 | SHA-256 | 字节 | 对照 |
| --- | --- | ---: | --- |
| `docs/plan/59-e0-budget-approval-provenance-20260914.md` | `15b4f457912aef9f31537b4a3660d32e8d90110f042550aa0b6d5909f6d277bd` | 21203 | 等于派发期望与 `PACKAGE_SHA256[DOC_REL]` |
| `validation/e0-budget-approval-provenance-20260914.json` | `2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d` | 285820 | 等于派发期望与 `PACKAGE_SHA256[LEDGER_REL]` |
| `validation/test_e0_budget_approval_provenance.py` | `6030470ab32e28fd3a4b8401e4eb92875d22c16d8b7e56e8edfd9002f0636b44` | 151778 | 等于派发期望；不在 `PACKAGE_SHA256` |
| `docs/plan/59-e0-frame-datum-binding-20260914.md` | `3fbb0e7fbdbc069a702dd0e8417c9b6a8dd3961575d5a188817990b280b553f8` | 15449 | 未改；等于 frame 终审 |
| `validation/e0-frame-datum-binding-20260914.json` | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | 105018 | 未改；不等于陈旧 `33c4909919…` |
| `validation/test_e0_frame_datum_binding.py` | `e412f2d1981fd02b34531426f31c6f010c96d15331bf41f30fc136cc59f10da6` | 77146 | 未改 |

六份均未跟踪于当前 HEAD，`check-ignore --no-index` 均不忽略。主仓 index 为空。台账字节不含 `33c4909919…` 或 `5d589075…`。

## 相对先前终审的差量

`cursor-g6-budget-frame-final-review-20260914-01` 在旧 budget 哈希 `81a4c65d…` / `a8c76498…` / `d74854f5…` 上把下列两项标为 **P2 残留、不否决**：

| 先前 id | 先前状态 | 本审 |
| --- | --- | --- |
| F1-validate-related-path-not-normalized | `validate()` 不冻 related 路径；`\\` / `./` + 当前 frame 哈希逃过精确拒绝 | **关闭**：`related_triples != RELATED_ARTIFACTS` 与逐字段精确比较一律 `related_artifact_mismatch` |
| F2-validate-missing-source-head | SOURCE_HEAD 缺失时 `validate()` 不独立拒绝 | **关闭**：`validate(check_git=True)` 先 `cat-file -e SOURCE_HEAD^{commit}`，再 `merge-base --is-ancestor`，稳定码 `source_head_missing_or_not_ancestor` |

P2 修复回执的 before 六项 fail-open 与本审独立复现一致，现均为拒绝。`check_git=False` 仍只走结构路径：三元组/声明键/位置类可测，不探测 SOURCE_HEAD 对象或祖先。这是文档化边界，不是残留缺口。

## 本切片新跑

未跑 30 代表集，未跑 153 全量，未重建临时仓顺序矩阵。

| 主机 | `RelatedSourceP2RepairTests` | 定向 hostile |
| --- | --- | --- |
| Windows 3.13.11 | Ran 14 / OK / 5.113 s / rc 0 | 17/17 |
| Ubuntu-22.04 3.10.12 | Ran 14 / OK / 89.878 s / rc 0 | 17/17 |

定向 hostile（两主机同一电池，均在 `validate()` 内判定）：

| id | 期望 | 结果 |
| --- | --- | --- |
| H00-pristine-check-git-true / false | 放行 | PASS |
| H-id-mismatch | `related_artifact_mismatch` | PASS |
| H-path-backslash-current-hash | 同上 | PASS |
| H-path-dot-prefix-current-hash | 同上 | PASS |
| H-sha256-mismatch | 同上 | PASS |
| H-order-swap | 同上 | PASS |
| H-duplicate-id / H-duplicate-path | 同上 | PASS |
| H-extra / H-missing | 同上 | PASS |
| H-source-head-missing-check-git-true | `source_head_missing_or_not_ancestor` | PASS |
| H-source-head-not-ancestor-check-git-true | 同上 | PASS |
| H-source-head-*-check-git-false | 结构放行 | PASS |
| H-check-git-false-skips-source-head-probe | 不探测 SOURCE_HEAD | PASS |
| H-package-sha256-cross-pin | 只钉 plan/ledger | PASS |

Ubuntu 探针在打印完整 17/17 JSON 后，WSL here-doc 结束符被当成多余 Python 名，进程退出码 1。有效载荷完整，不记敌意失败。

## 复用证据（独立校验哈希，未重跑）

P2 修复目录 `SHA256SUMS` 28 行全部与磁盘重算一致。8 份顺序 30 代表 txt 均可独立解析为 `Ran 30 / OK`。empty `commit-tree` 信封记录 `head_moved=true`、`same_tree=true`、`source_ancestor_exit=0`，来源钉只需祖先。Windows 153 全量捕获独立解析为 `Ran 153 / OK / 153.278 s`，本切片不把它当作新跑。

仍缺历史 `win-after-frame-then-budget.json` / `win-after-summary.json`。这是既有收据缺口，本切片不补写、不补跑。

## P1 / P2 / P3

| 优先级 | 项 | 状态 |
| --- | --- | --- |
| P1 | related `id/path/sha256` 由 `validate()` 精确冻结（顺序、重复、额外、缺失） | 关闭 |
| P1 | `SOURCE_HEAD` 缺失/非祖先由 `validate(check_git=True)` 失败关闭 | 关闭 |
| P1 | `check_git=False` 结构边界；两顺序 + empty commit 不要求 HEAD 相等 | 关闭 / 复用哈希通过 |
| P1 | 本切片 Windows 与 Ubuntu 各 14+17 | 通过 |
| P2 | 历史缺 `win-after-frame-then-budget.json` / `win-after-summary.json` | 列出，不否决 |
| P3 | 历史取消的第四次全量；`PACKAGE_SHA256` 不自哈希测试文件 | 不评分 / 预期 |

## 非声称

不是 owner 批准，不关闭 #59 / #10 / G6 / Full，不改判 R1 `numerical_failed`。未改候选，无主仓 Git 变更，未重跑 Windows 153 全量或 #83。
