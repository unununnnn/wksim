# Lane 3 hash-integrity 回执独立复核

2026-09-14。只读复核
`validation/coordination/cursor-postcommit-lane3-hash-integrity-20260914-01/{review.md,review.json,hashes.json}`。
从 git 对象 `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` 按组随机抽查 blob SHA-256。
**未重跑完整 176 扫描。未运行 pytest/unittest。未跑 native / 构建 / 飞行 / #83。**
**未改现有文件。未 add / commit / push。不关闭任何 issue / gate。**
写入仅在 `validation/coordination/cursor-postcommit-lane3-independent-review-20260914-01/{review.md,review.json}`。
本目录不留脚本。

**裁决：PASS。** 0 P1。1 条 P2（不否决）。源回执 JSON 可解析；`<FINAL_HEAD>` 绑定；176/176 与 7/7 抽查命中；`secret_hits=[]`；`scripts=[]`；`claims_owner_approval=false`。

这不是 owner 批准。`claims_owner_approval=false`。不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。

## 派发

```text
工作类别：postcommit-lane3-independent-review
         （非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、
      cursor-postcommit-three-lane-verification-plan-20260914-01、
      cursor-postcommit-lane3-hash-integrity-20260914-01/{review.md,review.json,hashes.json}
module / interface：无产品代码变更
独占写入：validation/coordination/cursor-postcommit-lane3-independent-review-20260914-01/review.md
         validation/coordination/cursor-postcommit-lane3-independent-review-20260914-01/review.json
依赖（只读）：Lane 3 三份回执；FINAL_HEAD git 对象
验证：JSON 可解析；FINAL_HEAD；176/176 结构；7/7 addon；
      secret_hits=[]；scripts=[]；claims_owner_approval=false；
      每组至少 2 路径随机抽查；7 addon 全部；related 三条；
      cited_sources 计数
范围外：完整 176 重扫；pytest/unittest；native / model / MATLAB /
        ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83；
        主仓 add/commit/push；改现有文件；关闭 issue/gate
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本复核在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 绑定

| 符号 | 值 |
| --- | --- |
| `<FINAL_HEAD>`（源回执与本复核） | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| 本工作区 `HEAD` | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| `<FINAL_TREE>` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` |
| `<SOURCE_HEAD>`（源回执转述） | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| 架构祖先退出码 | 0 |

源 `review.json` / `hashes.json` 的 `final_head` 与本工作区 `HEAD` 均为同一 40 hex。
抽查哈希来自 `git -c core.autocrlf=false cat-file blob 59d8da51…:<path>` 原始字节，未经文本管道改写 CRLF。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| JSON 可解析 | **PASS** | `review.json` 11173 B；`hashes.json` 78601 B |
| `FINAL_HEAD` | **PASS** | 源回执、`hashes.json`、本 `HEAD` 均为 `59d8da51…` |
| A 176/176 | **PASS** | `paths[]` 长 176；组 34/26/60/17/32/7；抽查 17/17 |
| B 7/7 | **PASS** | 7 addon 全部重算命中；SUMS 6 行、不列自身 |
| `secret_hits=[]` | **PASS** | 源 `C.secret_hits=[]`；本路未重扫 176 |
| `scripts=[]` | **PASS** | 源目录仅 `review.md` / `review.json` / `hashes.json` |
| `claims_owner_approval=false` | **PASS** | 源字段与本文均为 false |
| related 三条未入库 | **PASS** | 三处 `git cat-file -e` 退出码 128/128/128 |
| `cited_sources` 计数 | **PASS** | 账本 `inputs.cited_sources` = 83，唯一 83 |
| 未跑测试 / 未改 git / 不关闸 | **PASS** | 本目录无脚本；不关 issue/gate |
| 本路总体 | **PASS** | 0 P1 |

失败门：无。

## 抽查

随机种子 `20260914`。A–E 各 2 条；F / addon 7 条全部。方法：`git -c core.autocrlf=false cat-file blob <FINAL_HEAD>:<path>`，再 `sha256(raw)` 与 `len(raw)`。

| 组 | 路径 | SHA-256 前缀 | 字节 | 命中 |
| --- | --- | --- | --- | --- |
| A | `…/cursor-g1-g5-postcommit-head-finalize2-20260914-01/durable-evidence-manifest.txt` | `58553946…` | 4081 | 是 |
| A | `…/cursor-g1-g5-final-private-stage-finalize-20260914-01/review.json` | `f50105ca…` | 3337 | 是 |
| B | `…/cursor-g3-exact-precommit-audit-20260914-01/captures/pytest-candidate-linux-ubuntu-22.04.txt` | `5bba34bb…` | 111 | 是 |
| B | `…/cursor-g3-exact-postrepair3-review-20260914-01/captures/unittest-candidate-linux-ubuntu-22.04.txt` | `4f20643eba…` | 153 | 是 |
| C | `…/cursor-g6-budget-related-source-p2-repair-20260914-01/candidate-hashes.json` | `90aa4fb6…` | 2175 | 是 |
| C | `…/cursor-g6-budget-related-source-p2-repair-20260914-01/captures/win-seq-budget-then-frame-after-empty-budget-30.txt` | `68dcc7e9…` | 134 | 是 |
| D | `docs/plan/59-e0-frame-datum-binding-20260914.md` | `3fbb0e7f…` | 15449 | 是 |
| D | `…/cursor-g6-frame-datum-precommit-audit-20260914-01/minimal-commit-manifest.txt` | `bd21ab39…` | 3853 | 是 |
| E | `…/cursor-full-frame-postcommit-sequence-20260914-01/review.md` | `1ddde2c2…` | 10841 | 是 |
| E | `…/cursor-full-ac-precommit-audit-20260914-01/minimal-commit-manifest.txt` | `d7a00115…` | 3605 | 是 |
| F | `…/cursor-five-slice-final-integration2-20260914-01/SHA256SUMS` | `166b9e9a…` | 513 | 是 |
| F | `…/candidate-hashes.json` | `6b7293e3…` | 9973 | 是 |
| F | `…/dependency-check.json` | `be3f3c74…` | 2547 | 是 |
| F | `…/durable-evidence-manifest.txt` | `a644faa0…` | 6061 | 是 |
| F | `…/review.json` | `e5d9255c…` | 1533 | 是 |
| F | `…/review.md` | `fe859410…` | 13497 | 是 |
| F | `…/sequence-matrix.json` | `e5af8dd6…` | 41406 | 是 |

抽查 17/17 命中源 `hashes.json` 的 `sha256` / `expected_sha256` / `bytes`。
`SHA256SUMS` 自身钉 `166b9e9a…`；正文 6 行全命中；清单不列自身。这是预期。

related B1/B4 三条 **不在** `<FINAL_HEAD>`：

| 路径 | `cat-file -e` |
| --- | --- |
| `validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/review.md` | 128 |
| `validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/frontier.json` | 128 |
| `validation/coordination/codebuddy-g6-b1-b4-frontier-20260914-01/owner-input-template.json` | 128 |

`cited_sources`：从 `<FINAL_HEAD>:validation/full-original-ac-gap-ledger-20260914.json` 读取 `inputs.cited_sources`，计数 **83**，唯一 83。
存在性抽查 5 条（下标 0/20/41/62/82）`cat-file -e` 均为 0。
补充类型计数（非完整哈希扫描）：76 blob + 7 tree，missing=[]。
7 个 tree：`validation/pid-final-px4-20260909`、`ude-runtime-acceptance-20260909`、`ne-runtime-acceptance-20260910`、`46-reexecution`、`47-global-flight`、`lunar-20-epoch-1`、`velocity-yaw-20260908`。
`git ls-tree -d` 仍给出 `validation/pid-final-px4-20260909`。

源 Lane 3 目录文件恰好三份，无 `.py` / `.ps1` / `.sh` / `.bat` / `.cmd` / `.js`。`scripts=[]`。
源 `review.json` 用 `scripts_left=false` 表达同一事实，没有名为 `scripts` 的数组字段。

## P1 / P2

P1：无。

P2-CITED-SOURCES-SEVEN-TREES：源回执写「83 条均为 FINAL 仓库文件」。独立计数仍是 83，且 `cat-file -e` 全为 0；其中 7 条是 tree 不是 blob。计划门只要存在性，并单独要求 pid 目录在树中。本条不否决。

P3：SUMS 不列自身；本复核不在 176；未重扫秘密/卫生/大文件；未跑测试；不授权入库。

## 非声称

不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full，不批准 owner 项，
不改判既有 PASS/FAIL，不授权 add / commit / push，不把本路写成代表测试或飞行验收。
未运行测试。未重跑完整扫描。主仓无 git 变更。本文件不是 commit。

**PASS。**
