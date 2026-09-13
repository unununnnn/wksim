# G6 budget related/SOURCE_HEAD P2 修复

切片：`cursor-g6-budget-related-source-p2-repair-20260914-01`  
判定：**P2 已在 `validate()` 内关闭**（不是 owner 批准，不关闭 #59/#10/G6/Full）  
工作类别：new-development / offline provenance repair（无验收运行）  
cwd / 分支 / HEAD：`C:\Users\PC\Documents\odid编译\wksim` / `main` / `6eafdf9c0b734db07a9fe790c86b409d3468c10b`  
祖先：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0  
来源钉祖先：`git merge-base --is-ancestor 6eafdf9c0b734db07a9fe790c86b409d3468c10b HEAD` → exit 0

独占写入：三份 budget 候选，以及本目录。未改 frame / G1 / G3 / Full 或历史回执。未 `git add/commit/stage/reset/clean`。未启动 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行，未重跑 #83。

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。修复在主代理内完成，没有改用其他子代理模型顶替。

已读：`AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`，以及 `cursor-g6-budget-frame-final-review-20260914-01/review.md` 与 hostile-matrix。

## 派发核验

| 项 | 值 |
| --- | --- |
| module / interface | E0 budget 台账 `validate()`：related 三元组精确冻结；SOURCE_HEAD 对象/祖先拒绝码 |
| 独占文件 | 三份 budget 候选；本目录新建 |
| 不在范围 | 三份 frame 候选、G1/G3/Full、历史回执、主仓 Git |
| 新跑 | Windows 与 Ubuntu-22.04：先定向复现，再 30 代表 + 定向 hostile；Windows 全量 153；低内存 Budget→Frame / Frame→Budget / empty 代表集 |
| 验收资源 | 不宣称 owner 批准，不关闭 #59/#10/G6/Full |

## 定向复现（修复前）

对照终审 F1/F2，在改候选前用同一探针打了 Windows 与 Ubuntu。六项 fail-open 一致：

| id | `validate()` 修复前 |
| --- | --- |
| P2-H21 反斜杠 frame 路径 + 当前哈希 `5d589…` | 放行（`check_git=False`） |
| P2-H22 `./` 前缀 frame 路径 + 当前哈希 | 放行 |
| P2-H23 重复 related path | 放行 |
| P2-H23b related 哈希被改 | 放行 |
| P2-H18 SOURCE_HEAD 对象缺失 | `validate(check_git=True)` 仍干净；helper 把双探针失败当成未跟踪 |
| P2-H18b SOURCE_HEAD 不是 HEAD 祖先 | 同上 |

顺序交换与缺行在修复前已因 id 列表比较失败关闭。before 哈希为终审当时的 `81a4c65d…` / `a8c76498…` / `d74854f5…`。

## 修复

1. 测试模块冻结 `RELATED_ARTIFACTS`：三条 `id→path→sha256` 三元组按顺序精确比较。路径拼写、哈希、顺序、重复 id/path、额外或缺失记录一律 `related_artifact_mismatch`。related 仍不得升为 pin / owner / derivation。陈旧 frame 精确路径与 `33c490…` 仍额外拒绝。
2. `validate(check_git=True)` 先查 `git cat-file -e SOURCE_HEAD^{commit}`，再查 `merge-base --is-ancestor`。缺失或非祖先返回稳定码 `source_head_missing_or_not_ancestor`。`git show` 与 `ls-tree` 不一致仍按 tracked 失败关闭。
3. `check_git=False` 只走结构路径：三元组、声明键、位置类仍可测，不探测 SOURCE_HEAD 对象或祖先。

保留：`tracked_at_source_head=false`、陈旧/精确 frame 拒绝、后续当前 HEAD 跟踪不自动晋升、C1 B07/B08/B16、七类 fail-open、Unicode/Win32。

## 当前候选哈希

三份 budget 为 LF。`PACKAGE_SHA256` 只钉台账与计划文。frame 三份未改，仍为终审值。

| 路径 | SHA-256 | 字节 | 本切片 |
| --- | --- | ---: | --- |
| `docs/plan/59-e0-budget-approval-provenance-20260914.md` | `15b4f457912aef9f31537b4a3660d32e8d90110f042550aa0b6d5909f6d277bd` | 21203 | 是 |
| `validation/e0-budget-approval-provenance-20260914.json` | `2962931a28dfc3cc05e201dc23b6073c30948080de34279e9f5b21ae23544d3d` | 285820 | 是 |
| `validation/test_e0_budget_approval_provenance.py` | `6030470ab32e28fd3a4b8401e4eb92875d22c16d8b7e56e8edfd9002f0636b44` | 151778 | 是；不在 `PACKAGE_SHA256` |
| `docs/plan/59-e0-frame-datum-binding-20260914.md` | `3fbb0e7fbdbc069a702dd0e8417c9b6a8dd3961575d5a188817990b280b553f8` | 15449 | 否 |
| `validation/e0-frame-datum-binding-20260914.json` | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | 105018 | 否 |
| `validation/test_e0_frame_datum_binding.py` | `e412f2d1981fd02b34531426f31c6f010c96d15331bf41f30fc136cc59f10da6` | 77146 | 否 |

## 本切片新跑

| 主机 | 30 代表 | 定向 hostile | 全量 |
| --- | --- | --- | --- |
| Windows 3.13.11 | Ran 30 / OK / 9.472 s / rc 0 | 31/31；P2 开放 0 | Ran **153** / OK / 153.278 s / rc 0 |
| Ubuntu-22.04 3.10.12 | Ran 30 / OK / 119.065 s / rc 0 | 31/31；P2 开放 0 | 未跑（按派发只要求 Windows 全量） |

测试计数由终审时的 139 增至 **153**（新增 `RelatedSourceP2RepairTests` 14 项）。精确报告，不把旧 139 当作本轮全量。

低内存临时仓（`git archive` 流式钉值 + alternates，不把整仓载入 Python）：

| 主机 | 顺序 | after-both 30 | empty HEAD 前进 | after-empty 30 | 主仓未动 |
| --- | --- | --- | --- | --- | --- |
| Windows | Budget→Frame | Ran 30 / OK / 9.627 s | 是 | Ran 30 / OK / 9.604 s | 是 |
| Windows | Frame→Budget | Ran 30 / OK / 9.474 s | 是 | Ran 30 / OK / 9.555 s | 是 |
| Ubuntu-22.04 | Budget→Frame | Ran 30 / OK / 7.800 s | 是 | Ran 30 / OK / 8.683 s | 是 |
| Ubuntu-22.04 | Frame→Budget | Ran 30 / OK / 9.247 s | 是 | Ran 30 / OK / 9.258 s | 是 |

empty `commit-tree` 移动 HEAD；来源钉只需祖先，不要求相等。后续把 related 路径跟踪进当前 HEAD 不会自动晋升。

## P1 / P2 / P3

| 优先级 | 项 | 状态 |
| --- | --- | --- |
| P1 | related 来源钉绑定、不自动晋升、陈旧/精确 frame 拒绝、C1 B07/B08/B16、七类、Unicode/Win32 | 保持关闭 |
| P1 | F1 related 三元组由 `validate()` 精确冻结 | 本切片关闭 |
| P1 | F2 SOURCE_HEAD 缺失/非祖先由 `validate(check_git=True)` 拒绝 | 本切片关闭 |
| P2 | 终审 F3：历史缺 `win-after-frame-then-budget.json` / `win-after-summary.json` | 历史回执缺口，本切片不补写 |
| P3 | `PACKAGE_SHA256` 不自哈希测试文件 | 预期，不评分 |

## 非声称

不是 owner 批准，不关闭 #59 / #10 / G6 / Full，不改判 R1 `numerical_failed`。未改 frame/G1/G3/Full，无主仓 Git 变更，未重跑 #83 或飞行。
