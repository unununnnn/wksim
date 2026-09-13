# Budget/Frame 交叉提交语义 — 已取消收口的独立终审

切片：`cursor-g6-budget-frame-sequence-finalize-20260914-01`  
收口对象：已取消的交叉提交修复 `817ddc81-c897-4e9b-85ac-11dc4c825051`  
只读证据：`validation/coordination/cursor-g6-budget-frame-sequence-repair-20260914-01/**`  
判定：**PASS**  
工作类别：new-development / independent offline finalize（无验收运行、未重跑任何测试）  
cwd / 分支 / HEAD：`C:\Users\PC\Documents\odid编译\wksim` / `main` / `6eafdf9c0b734db07a9fe790c86b409d3468c10b`  
祖先：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0  
来源钉祖先：`git merge-base --is-ancestor 6eafdf9c0b734db07a9fe790c86b409d3468c10b HEAD` → exit 0

独占写入：本目录。未改三份 budget 候选或三份 frame 候选，未覆盖 repair 捕获，未 `git add/commit/stage/reset/clean`，未启动 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行，未重跑 #83、30/12/136/139 套件或 `run_sequence_repair.py`。

## 派发核验

| 项 | 值 |
| --- | --- |
| module / interface | E0 budget 台账 `related_artifacts` 来源钉绑定 + frame 陈旧记录移除；临时仓 Budget→Frame 与 Frame→Budget |
| 只读候选 | `docs/plan/59-e0-budget-approval-provenance-20260914.md`、`validation/e0-budget-approval-provenance-20260914.json`、`validation/test_e0_budget_approval_provenance.py`；三份 frame 候选未改 |
| 只读证据 | `cursor-g6-budget-frame-sequence-repair-20260914-01/**`（含 `run_sequence_repair.py` 与全部现有捕获） |
| 已读 | `AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md` |
| 验收资源 | 不宣称 owner 批准，不关闭 #59/#10/G6/Full |

## 当前候选哈希（独立重算，未改字节）

三份 budget 与三份 frame 均为 LF。`PACKAGE_SHA256` 只钉台账与计划文；测试模块不自哈希，C1 捕获里 `matches_package_pin=false` 与源码注释一致。

| 路径 | SHA-256 | 字节 | 对照 |
| --- | --- | ---: | --- |
| `docs/plan/59-e0-budget-approval-provenance-20260914.md` | `81a4c65d56f2c35cf617441822fc14b3d81e9da614c1ef3837ab6fca7f7d93a3` | 19267 | 等于 `PACKAGE_SHA256[DOC_REL]`，等于全部 after C1 / lin-after-summary |
| `validation/e0-budget-approval-provenance-20260914.json` | `a8c76498f86d48945842e5b9bd9361293ebc93c954e5b14661304abc9208204a` | 284045 | 等于 `PACKAGE_SHA256[LEDGER_REL]` |
| `validation/test_e0_budget_approval_provenance.py` | `d74854f5e993fce6835ef1db63bcd4cf556a91c9c6d70b80ce18712087ba7c01` | 138557 | 等于 after 捕获；不在 `PACKAGE_SHA256` |
| `docs/plan/59-e0-frame-datum-binding-20260914.md` | `3fbb0e7fbdbc069a702dd0e8417c9b6a8dd3961575d5a188817990b280b553f8` | 15449 | 与修复前 `before-failure/candidate-hashes.json` 一致 |
| `validation/e0-frame-datum-binding-20260914.json` | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | 105018 | 同上；不等于陈旧 `33c4909919…` |
| `validation/test_e0_frame_datum_binding.py` | `e412f2d1981fd02b34531426f31c6f010c96d15331bf41f30fc136cc59f10da6` | 77146 | 同上 |

六份均未跟踪于当前 HEAD（`git show HEAD:<path>` exit 128），`check-ignore --no-index` 均不忽略。

## related_artifacts 与来源钉

当前台账只保留三条 B1/B4 前沿记录。独立 `git show` / `ls-tree` 对来源钉 `6eafdf9c0b734db07a9fe790c86b409d3468c10b`：三条路径与 frame JSON 的 `show` 均为 128，`ls-tree` 名为空，故 `tracked_at_source_head=false`。

- 每条只有 `id/path/sha256/tracked_at_source_head/role`，没有 `tracked_at_head`。
- 没有 `frame_datum_binding_inflight`，没有陈旧哈希 `33c4909919d73c344336a9a56a4a824b3974473d8e063874ad088c32c534f39f`。
- 校验器把 `tracked_at_source_head is not False`、出现 `tracked_at_head`、frame 路径或陈旧哈希、把 related 写入 pins / owner / derivation，一律失败关闭。后续当前 HEAD 跟踪某条 related 路径，也不能自动升为 pin、owner 或 derivation。

修复前摘录仍把 frame 写成 `tracked_at_head=false` 且哈希 `33c490…`。那是修复前证据，不是当前台账。

## 修复前：current-HEAD related_artifact 失败（P1，已核验）

两主机、两顺序、两提交之后的 budget 30 均独立解析为 **Ran 30 / FAILED (failures=2) / returncode 1**。失败句是 `related artifact frame_datum_binding_inflight is tracked at HEAD`。Frame→Budget 在只提交 frame 后已经失败，因为 disposable HEAD 已跟踪 frame，而旧规则对照的是当前 HEAD。

| 主机 | 顺序 | after-first 30 | after-both 30 |
| --- | --- | --- | --- |
| lin / win | budget-then-frame | OK / rc 0（只提交 budget） | FAIL / rc 1 |
| lin / win | frame-then-budget | FAIL / rc 1（只提交 frame） | FAIL / rc 1 |

## 修复后捕获（独立解析 txt，未重跑）

派发口令里的 “budget 136” 是历史全量套件标签。本轮独立解析到的全量计数是 **Ran 139 / OK**，不是 136。这是套件在交叉提交修复后增加用例后的实测计数，不构成 FAIL。

### Linux after（P1）

两顺序 `after-both` 与 `after-empty`：budget 30 与 frame 12 均为 Ran N / OK / 与 JSON `returncode=0` 一致。Linux 未跑全量，本切片也不要求。空提交 `head_moved=true`，`source_ancestor_exit=0`，项目 HEAD 仍为来源钉。

Frame→Budget 的 `after-frame` budget 30 现为 OK：frame 已在 disposable HEAD 跟踪，但 related 不再对照当前 HEAD，也不再点名 frame 路径。

### Windows after

| 顺序 | 步骤 | 30 | 12 | 全量 | 信封 JSON |
| --- | --- | ---: | ---: | --- | --- |
| budget-then-frame | after-both | 30 OK rc 0 | 12 OK rc 0 | 139 OK rc 0 | 有 `win-after-budget-then-frame.json` |
| budget-then-frame | after-empty | 30 OK rc 0 | 12 OK rc 0 | 139 OK rc 0 | 同上 |
| frame-then-budget | after-both | 30 OK | 12 OK | 139 OK | **缺** `win-after-frame-then-budget.json` |
| frame-then-budget | after-empty | 30 OK | 12 OK | **P3 取消** | 同上 |

第二顺序 empty 后的第四次全量被主会话为节省周期取消。磁盘上留有 `win-after-frame-then-budget-after-empty-budget-full.txt`，独立解析可见 `Ran 139 tests in 126.393s` 与 `OK`，但本切片**不把它记为完成，也不记为失败**。该格不进入 PASS 证据。同顺序 `after-both` 全量与第一顺序 `after-empty` 全量已经覆盖同一套件。

缺 `win-after-frame-then-budget.json` 与 `win-after-summary.json`。这是 P2 收据缺口：第二顺序的 30/12/after-both 全量与 C1 JSON 仍在，Linux 同顺序信封已记录祖先/related/空提交语义。禁止补跑。

## C1 spotcheck（四份已有 JSON，未重跑）

`lin/win` × `budget-then-frame/frame-then-budget` 四份均为 `verdict=PASS`，`fail_reasons=[]`，干净台账 0 违反，B07/B08/B16 关闭，七类 fail-open 关闭，Win32 六项关闭。Unicode：`coordinaſion` / Kelvin / 西里尔 es 不拒，ASCII `coordination` 拒，包文件长 s 自指拒。候选哈希与上表一致。

## 来源祖先语义

已有 sequence JSON（Linux 两顺序 after、Windows 第一顺序 after、两主机 before）里，每次 disposable `commit-tree` / 空提交的 `source_ancestor_exit` 均为 0，`head_equals_source` 在提交后为 false，`project_repo_untouched=true`，`final_project_head` 仍为 `6eafdf9c…`，index 为空。当前工作区祖先检查同样为 0。

## 判定与发现

**PASS。** P1 格子均可由已有捕获独立核验。P2 只缺 Windows 第二顺序信封与 after 汇总 JSON。P3 取消的第四次全量不评分。

| 级 | id | 结论 |
| --- | --- | --- |
| info | F1-cancelled-p3-full | 第二顺序 empty 后第四次全量由主会话取消；残留 txt 不记完成、不记失败 |
| info | F2-missing-win-envelope | 缺 `win-after-frame-then-budget.json` 与 `win-after-summary.json`；原子 txt / C1 / Linux 同序信封仍在 |
| info | F3-full-count-139 | 派发称 136；独立解析 after 全量为 139 |
| info | F4-test-not-self-hashed | `PACKAGE_SHA256` 不钉测试文件，与源码一致 |

## 被取消的冗余运行（P1 / P2 / P3）

| 优先级 | 运行 | 状态 |
| --- | --- | --- |
| P1 | 修复前两主机两顺序 after-both budget 30 | 已有，独立核验 FAIL |
| P1 | 修复后 Linux 两顺序 after-both / after-empty 的 30 与 12 | 已有，独立核验 OK |
| P1 | 修复后 Windows 两顺序 after-both 的 30 / 12 / 全量 | 已有 txt；第一顺序另有信封 JSON |
| P1 | 修复后 Windows 第一顺序 after-empty 的 30 / 12 / 全量 | 已有 |
| P1 | 修复后 Windows 第二顺序 after-empty 的 30 / 12 | 已有 |
| P1 | 四份 C1、当前哈希、来源钉祖先、陈旧 frame 已移除、related 不可自动晋升 | 已有 |
| P2 | Windows 第二顺序 sequence JSON / win-after-summary | **缺失，只列明，不补跑** |
| P2 | 中间步 after-budget / after-frame 的 30 | 已有，作对照 |
| P3 | Windows 第二顺序 after-empty 全量 | **主会话取消；不完成、不失败** |
| P3 | Linux 全量、#83、native / 构建 / 飞行、本切片重跑任何 unittest | **未跑，且禁止** |

## 非声称

不是 owner 批准，不关闭 #59 / #10 / G6 / Full，不改判 R1 `numerical_failed`。未重跑测试，未改候选，无 Git 变更。
