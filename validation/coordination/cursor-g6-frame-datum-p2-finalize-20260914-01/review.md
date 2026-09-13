# G6/B2 frame/datum P2 终审收据

切片：`cursor-g6-frame-datum-p2-finalize-20260914-01`  
判定：**PASS**  
工作类别：new-development / independent offline finalize（无验收运行）  
cwd / 分支 / HEAD：`C:\Users\PC\Documents\odid编译\wksim` / `main` / `6eafdf9c0b734db07a9fe790c86b409d3468c10b`  
祖先：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0

独占写入：本目录。未改候选、未覆盖 repair/takeover 探针目录，未 `git add/commit/push/reset/clean`，未启动 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行，未重跑 #83 与 45 项专用套件。

## 派发核验

| 项 | 值 |
| --- | --- |
| module / interface | G6/B2 e0 动态槽 frame/datum 绑定补充；`validate_binding` / 完整 RHS 身份 / `counts` 重算 / `observables[]` 精确字段 / 注入 manifest 缺失活动路径 |
| 只读候选 | `docs/plan/59-e0-frame-datum-binding-20260914.md`、`validation/e0-frame-datum-binding-20260914.json`、`validation/test_e0_frame_datum_binding.py` |
| 只读证据 | `cursor-g6-frame-datum-p2-repair-20260914-01/**`、`cursor-g6-frame-datum-p2-repair-takeover-20260914-01/**`；删除哈希对照 `cursor-g6-frame-datum-postreview-takeover-20260914-01/review.json` |
| 已读 | `AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md` |
| 验收资源 | 不宣称 G6/Full；本切片只复核 P2 修复关闭与陈旧写入器删除 |

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审查在主代理内完成，没有改用其他子代理模型顶替。

## 当前候选哈希（独立重算）

三份均为 LF。与 repair / takeover 全部带哈希捕获一致。

| 路径 | SHA-256 | 字节 | 与先验 |
| --- | --- | ---: | --- |
| `docs/plan/59-e0-frame-datum-binding-20260914.md` | `3fbb0e7fbdbc069a702dd0e8417c9b6a8dd3961575d5a188817990b280b553f8` | 15449 | 一致 |
| `validation/e0-frame-datum-binding-20260914.json` | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | 105018 | 一致 |
| `validation/test_e0_frame_datum_binding.py` | `e412f2d1981fd02b34531426f31c6f010c96d15331bf41f30fc136cc59f10da6` | 77146 | 一致 |

## 先验捕获（只读核验，未重跑长套件）

11/11 带哈希行与当前候选一致。

| 捕获 | 平台 | 结果 | 哈希 |
| --- | --- | --- | --- |
| repair mutation | Windows 3.13.11 | PASS 23/0，13/13 拒绝 | 当前三哈希 |
| repair mutation | Ubuntu-22.04 3.10.12 | PASS 23/0，13/13 拒绝 | 当前三哈希 |
| repair focused/full | Windows | pytest 45/45 246.90 s；unittest 45 OK 245.626 s | 接管复用同一捕获 |
| repair Ubuntu suite | Ubuntu-22.04 | 历史 FAIL：420 s 超时，14 个点 | 不作为当前 PASS |
| takeover mutation | Windows | PASS 60/0，21/21 拒绝 | 当前三哈希 |
| takeover after-delete | Windows / Ubuntu | 各 PASS 8/0 | 当前三哈希 |
| takeover Ubuntu pytest | Ubuntu-22.04 | **45/45 in 495.52 s**，exit 0 | 当前三哈希 |

## 陈旧写入器

`validation/coordination/codebuddy-g6-frame-datum-20260914-01/write_binding.py` **已不存在**。

删除记录 `stale-writer-delete.json` 的 `sha256_before_delete` 为  
`56df93cc6a74d432593b94e1ed6094a9cbe1b6ad586ef944aed99a6290e7681c`，  
与先前 postreview-takeover 的 F1 / `stale_writer.sha256` 以及该目录 `SHA256SUMS` 行一致。接管两侧 after-delete 仍为 PASS，候选哈希未漂。

残留（不构成 FAIL）：同目录 `SHA256SUMS` / `notes.md` 仍点名已删文件；`__pycache__/write_binding.cpython-313.pyc` 按接管约定未删。源文件已不在，无法再走 `main()` 覆写 payload。

## 独立 spot-check（未重跑 45 项）

Windows Python 3.13.11，`spotcheck.py`：**56/56 PASS**（约 43 s）。干净 payload `validate_binding` 0 错。验收位仍全 false，`r1_status=numerical_failed`。

| 路径 | 结果 |
| --- | --- |
| 精确 RHS 身份 `Exp1_MinModelTemp_B.Product[2]` | 命中；12 个敌对子串/前缀/后缀/换索引全部拒绝 |
| `counts` 独立重算 | 56 / 25 / 31 / 10 / 46 / 24，与 payload 一致；谎报、多键、缺键被拒 |
| `observables[]` 精确字段 | `m/s`、EV-13、EV-14 通过；前缀/后缀/blob/语义前缀返回 `quote_not_exact_observables_field` |
| 注入 manifest 缺失活动路径 | 去掉 `Vehicle60[3]` 后走活路径失败关闭；HEAD manifest 仍干净 |

先前 postreview 的 P2/P3 残留 F1–F5 在当前哈希上均已关闭。

## 判定与发现（按严重度）

**PASS。** P2 四条活路径关闭。陈旧写入器已删且删除哈希与先前审查一致。先验 Windows 全量/聚焦与 mutation、Ubuntu mutation/after-delete 与 45/45 pytest 均可复用当前哈希。

| 级 | id | 结论 |
| --- | --- | --- |
| closed | F1-stale-writer | 源文件已删；预删哈希等于 postreview-takeover `56df93cc…` |
| closed | F2-rhs-identity | 完整符号身份；`Product` 一类子串不再被接受 |
| closed | F3-observables-field | `observables[]` 要求合同元素字符串字段精确相等 |
| closed | F4-manifest-inject | `validate_binding(..., manifest=injected)` 走活动缺失路径 |
| closed | F5-counts-recompute | `counts` 全部键由槽/owner 结构重算 |
| info | I1-ubuntu-timeout-history | 第一轮 Ubuntu 套件 420 s 超时；接管以 495.52 s 收回 45/45 |
| info | I2-stale-index-text | codebuddy `SHA256SUMS` / `notes.md` 仍列出已删写入器 |
| info | I3-pycache-residual | `write_binding.cpython-313.pyc` 仍在；源文件不在 |

## 非声称

不是 owner 批准，不关闭 #59 / #60 / G6 / Full，不改判 R1 `numerical_failed`。未重跑 45 项套件、#83，未做 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行。无 Git 变更。
