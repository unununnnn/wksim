# Full 原始 AC 账本独立终审收据

切片：`cursor-full-ac-gap-ledger-finalize-20260914-01`  
判定：**PASS**（0 P1 / 0 P2 / 1 P3 helper 宽度说明）  
工作类别：independent-hostile-final-review-finalize（只读收据，无验收运行）  
cwd / 分支 / HEAD：`C:\Users\PC\Documents\odid编译\wksim` / `main` / `6eafdf9c0b734db07a9fe790c86b409d3468c10b`  
祖先：`git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → exit 0

独占────────────────────────
工作类别：independent-hostile-final-review-finalize
实际 cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim ，main，6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先检查退出码：0
已读：AGENTS.md、architecture-implementation-20260912.md、architecture-continuation-20260913.md
本次 module / interface：Full 原始 AC 缺口账本（只读）；不改候选、不重跑 81 项套件
独占文件：validation/coordination/cursor-full-ac-gap-ledger-finalize-20260914-01/**
依赖：cursor-full-ac-gap-ledger-final-review-20260914-01/**（只读）、四份候选、接管 81/81 收据
验证：哈希与内部一致性抽查；heading-stack 复算独立总量
新开发或历史对照：既有独立敌意终审的收据化，不是新架构验收
────────────────────────────────────────────────────────

独占写入：本目录。未改候选，未覆盖终审/接管探针目录，未 `git add/commit/push/reset/clean`，未启动 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行，未重跑 #83 与 81 项专用套件。

本界面不可选 `gpt-5.6-luna`。收据在主代理完成，未派子代理。

## 1. 关口

| 关口 | 结论 | 证据 |
| --- | --- | --- |
| 机器终审 `review.json` | **PASS** | `cursor-full-ac-gap-ledger-final-review-20260914-01/review.json`：PASS，0 P1 / 0 P2 / 1 P3 |
| HEAD 与 `f333316` 祖先 | **PASS** | 当前 HEAD `6eafdf9c…`，祖先 exit 0 |
| 独立总量复算 | **PASS** | heading-stack：255 / 190 / 65 / 40 / 150；22 / 8 / 8；38 票，编号和 1121 |
| 账本整数与精确集合 | **PASS** | 账本 `counts` 与 `exact_sets` 与独立总量逐项相同 |
| 当前候选哈希 | **PASS** | 四份候选与终审钉值、Windows/Ubuntu 结果、接管 81 收据一致 |
| 既有 Windows / Ubuntu 81 | **PASS** | 接管目录 SHA256SUMS 28/28；两平台 81/81 + 隔离 81/81；哈希对应当前候选；本轮未重跑 |
| 双平台核心一致 | **PASS** | Windows 与 Ubuntu-22.04 的总量、逃逸名单、判定相同 |
| 六处 helper 逃逸 | **PASS / P3** | 全部被具名全套件测试接住，不是 fail-open |
| 未宣称验收 / 重开 / 关门 | **PASS** | `full_program=not-closed`；G0–G6 均为 `not-closed` |
| 本评总体 | **PASS** | 保留独立总量；P3 仅为 helper 窄于套件 |

## 2. 当前候选哈希（独立重算）

| 路径 | SHA-256 | 字节 | 与钉值 |
| --- | --- | ---: | --- |
| `docs/plan/full-original-ac-gap-ledger-20260914.md` | `5a4d9a649abeb57b423d98b84fdf8c59c965afd74a92ba88061ee48a1c44ad3e` | 25570 | 一致 |
| `validation/full-original-ac-gap-ledger-20260914.json` | `4e1f9b9e80ce07265c4b25cca6fc084a200a18051536d2b3f3243c5b79fd1d16` | 225429 | 一致 |
| `validation/test_full_original_ac_gap_ledger.py` | `d2a241c97c50549e2aae9226163a61f3445787f886b04eeae42fcf74af7367a1` | 75771 | 一致 |
| `validation/full-original-ac-gap-ledger-snapshot-20260914.json` | `c8af0dcef3dfc3a78141d381a9cb307fc5a0a223cc9c2898a5a34fd0ffae1ef4` | 91924 | 一致 |

四份均未忽略、未入 HEAD。`/validation/*/` 只匹配子目录，不匹配 `validation/` 根下文件，因此不需要 `git add -f`。

## 3. 独立总量（原样保留）

解析器：标题栈（heading-stack），不以候选 `EXPECTED_*` / 区间常量为神谕。本轮抽查从快照正文复算，与机器终审、Windows / Ubuntu recount、账本整数一致。

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

全勾选只表示正文打勾，不是能力已复核。

## 4. 既有 Windows / Ubuntu 结果（只读，未重跑）

接管：`cursor-full-ac-gap-ledger-repair-takeover-20260914-01`，SHA256SUMS **28/28**。

| 平台 | 套件 | 隔离 | 候选哈希 |
| --- | --- | --- | --- |
| Windows 3.13.11 | 81/81 PASS | 81/81 PASS | 与当前四份一致 |
| Ubuntu-22.04 3.10.12 | 81/81 PASS | 81/81 PASS | 与当前四份一致 |

机器终审两份 `results-*.json`：

- `review_verdict=PASS`，`failed_checks=[]`；
- 独立总量字节级相同；
- charter 面 18 处被 `_accept_ledger` 接住；
- helper 残差逃逸 6 处，全套件仍未接住的名单为空。

干净检出清单：87 个依赖，0 个 ignored-untracked，0 缺失，0 条仍引用被禁目录。

## 5. P3：六处 `_accept_ledger` 逃逸不是 fail-open

`_accept_ledger` 是套件内部的变异谓词，不是验收面。它检查顶层键、counts / inputs / verdict / scope 的键集合、headline 整数、HEAD / 快照钉、队列 `omitted_acs` 与 banned 引用，**不**检查：

- `exact_sets` 键集合；
- `ac_universe` 键集合；
- `source_snapshot_identity` 键集合；
- `exact_sets.closed_with_unchecked_issues` 是否丢掉 #48；
- `verdict.full_program` 与 `gate_claims` 的取值。

因此下列六次敌意变异能逃过 helper，但 Windows / Ubuntu 的全套件抽查均记录为 `caught=true`，`still_uncaught_by_full_suite=[]`：

| 逃逸 | 具名全套件接住测试 |
| --- | --- |
| `unknown_exact_sets_key` | `test_ledger_schema_keys` |
| `unknown_ac_universe_key` | `test_ledger_schema_keys` |
| `unknown_identity_key` | `test_ledger_schema_keys` |
| `exact_sets_drop_48` | `test_exact_sets_match_literals`、`test_ledger_counts_match_literals_and_snapshot`、`test_closed_state_never_implies_fulfilment`、`test_gap_sets_are_disjoint_and_cover_every_gap` |
| `verdict_full_closed` | `test_ledger_declares_fail_closed_policy` |
| `gate_g1_closed` | `test_ledger_declares_fail_closed_policy` |

这是 helper 宽度说明（P3），不是章程 P1/P2 漏检，也不是 fail-open：被测账本仍被具名测试拒绝。本轮只核对这些具名测试仍在候选源码中，并核对照终审已归档的套件抽查行；没有重跑 81 项。

## 6. 判定与发现

**PASS。** 独立总量保持 255 / 190 / 65 / 40 / 150 与 22 / 8 / 8。机器终审、双平台 81/81 与当前哈希一致。唯一发现是 P3 helper 宽度，且六处逃逸均被具名全套件测试接住。

| 级 | id | 结论 |
| --- | --- | --- |
| P3 | F-p3-accept-ledger-helper-narrower-than-suite | `_accept_ledger` 对六次额外攻击窄于 81 项套件；具名测试已接住，不是 fail-open。 |

## 7. 最小提交清单（只列清单，未执行）

四份候选可用普通 `git add`。本收据目录位于 `/validation/*/` 忽略规则下，不是候选提交集。详见 `minimal-commit-manifest.txt`。本评未执行这些命令。

## 8. 明确不声称

不是业主验收。不关闭、不重开、不评论任何 issue。G0–G6 与 Full 保持 `not-closed`。未改候选，未对主树做 commit / stage / reset / clean。未跑 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83，也未重跑已捕获的 81 项套件。
