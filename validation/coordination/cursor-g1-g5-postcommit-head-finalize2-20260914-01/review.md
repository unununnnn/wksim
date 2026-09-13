# G1/G5 提交后 HEAD 修复独立正确性终审（finalize2）

2026-09-14。只读候选与既有回执。新写仅
`validation/coordination/cursor-g1-g5-postcommit-head-finalize2-20260914-01/**`。
未改候选、历史回执、git index 或 refs。未运行测试。

**本评总体：PASS（0 P1 / 0 P2 / 3 P3）。候选语义为来源/祖先钉，不是当前 HEAD 相等。这不是晋升，不关闭 #39 / G1 / G5 / Full。**

## 派发

```text
工作类别：independent-correctness-final-review-finalize2
          （只读收据；非新架构验收、非历史对照、非晋升）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、
      cursor-g1-g5-postcommit-head-final-review-20260914-01、
      cursor-g1-g5-postcommit-head-repair-20260914-01、
      validation/test_g1_g5_offline_drift.py（只读）
module / interface：G1/G5 离线身份门；SOURCE_HEAD 祖先钉 + 七行产品 blob
独占写入：validation/coordination/cursor-g1-g5-postcommit-head-finalize2-20260914-01/**
依赖（只读）：repair 回执与 SHA256SUMS；final-review 捕获/矩阵；
             两枚 promotion-flight JSON、两个 helper；HEAD 七行产品源
验证：独立重算候选/依赖 SHA-256；AST 重判 assertNotEqual；
      repair SHA256SUMS 77/77；七行三路与三次 diff 为空；
      只读跨系统/提交顺序/empty commit/hostile 收据
范围外：改候选或历史回执；主仓 add/commit/stage/reset/clean；
        运行 pytest/unittest；native / build / flight / #83
```

本界面不可选 `gpt-5.6-luna` / `gpt-6-astra`。终审在主代理完成，未派子代理。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 主仓 HEAD 仍为 `6eafdf9`，`f333316` 为祖先 | **PASS** | 开工 `6eafdf9c…`，祖先退出码 0；本评未动 refs |
| 候选 SHA-256 为钉值且非旧字节 | **PASS** | 独立重算 `83234a89fa62be49931dc1adee7d36e8a7780d9f8f781b854f69214d388a12c5`，42074 字节，917 CR；≠ `0281f831…538c92` |
| `assertNotEqual` 未被误判为当前 HEAD 相等 | **PASS** | AST 仅一处身份断言：L540 `assertNotEqual(identities["head"], SOURCE_HEAD)`，在后代 mock 中证明 HEAD 字符串 ≠ 来源钉后仍过祖先门。无 `assertEqual(..., SOURCE_HEAD/PINNED_HEAD)`，无 `==` 比较，无 `PINNED_HEAD` 名 |
| P1 不再要求当前 HEAD 精确等于来源钉 | **PASS** | `PINNED_HEAD` 已删除；`SOURCE_HEAD` 只作 `merge-base --is-ancestor`；`test_source_head_is_ancestor_pin_not_current_head_equality` 用 `"a"*40` 后代字符串仍过 `_assert_head_and_row_identities` |
| 精确 6 次只读 git 元数据调用 | **PASS** | 源码字面量：`rev-parse HEAD`、`merge-base --is-ancestor SOURCE_HEAD HEAD`、`ls-tree HEAD -- <7>`、三次 `diff` |
| 七行产品 blob 三路一致、三次 diff 为空 | **PASS** | 本评 `git ls-tree HEAD` 与工作区 blob SHA-1 / SHA-256 均等于冻结钉；`diff HEAD/--cached/unstaged -- <7>` 均为空 |
| repair SHA256SUMS | **PASS** | 列出 77 项，独立重算 77/77 匹配；0 缺失、0 漂移 |
| 跨系统提交身份 | **PASS** | Windows 与 Ubuntu-22.04 的 ABC/CBA commit/tree 逐步相同；commit-sequence 文本哈希相同 |
| 提交顺序无关终态 tree | **PASS** | ABC 终态 `2b4714f8…` / CBA 终态 `4dcfa55d…`，tree 均为 `8ab33ef851c73a5bf32d5dbd848cc00c52a021d5` |
| empty commit 树不变 | **PASS** | ABC empty `9f4f4765…`、CBA empty `e7da8047…`，tree 仍 `8ab33ef8…`；final-review 重跑 empty `be6efd86…` 同 tree |
| hostile fail-closed | **PASS** | 只读 46/46、三份矩阵 ID 集合相同。repair 分叉 exit 1 红、blob 漂移红。本评未重跑 |
| 四枚 force-add 依赖字节未改 | **PASS** | 两枚飞行钉 + 两个 helper 的 SHA-256 与 repair 钉一致 |
| 主仓未被 add/commit/stage/reset/clean | **PASS** | HEAD 仍 `6eafdf9`；本评只新增本目录未跟踪文件 |
| 本切片总体 | **PASS** | 0 P1 / 0 P2 / 3 P3。不关闭 #39 / G1 / G5 / Full |

## `assertNotEqual` 独立重判

naive 子串 `identities["head"], SOURCE_HEAD` 在候选中出现 **1** 次，位于：

`HeadIdentityMutationTests.test_reader_accepts_descendant_head_with_frozen_blobs` 第 540 行：

`self.assertNotEqual(identities["head"], SOURCE_HEAD)`

该测试先 mock `rev-parse HEAD` 为 `"c"*40`，再断言该字符串 **不等于** `SOURCE_HEAD`，然后 `_assert_head_and_row_identities` 仍过。含义是「后代 HEAD + 冻结 blob 必须被接受」，不是「当前 HEAD 必须等于来源钉」。

把它判成当前 HEAD 相等，是扫描谓词假阳性，不是候选 P1。独立 AST 只看到这一处身份断言；`assertEqual(identities["head"], SOURCE_HEAD/PINNED_HEAD)` 与 `identities["head"] == …` 均不存在。

## 跨系统 / 顺序 / empty / hostile（只读，未重跑）

repair 回执（SHA256SUMS 已复核）：

| 序列 | 步 | HEAD | tree | G1/G5 | 交错 |
| --- | --- | --- | --- | --- | --- |
| A→B→C | after A | `c844a061…` | `ed8281dc…` | 绿 | — |
| A→B→C | after B | `f7a0908d…` | `0b500bca…` | 绿 | 9/9 |
| A→B→C | after C | `2b4714f8…` | `8ab33ef8…` | 绿 | 9/9 |
| A→B→C | empty | `9f4f4765…` | `8ab33ef8…` | 绿 | 9/9 |
| C→B→A | after C | `6eba0da5…` | `6ca1639c…` | — | — |
| C→B→A | after B | `0a556bd4…` | `70f66fa0…` | — | — |
| C→B→A | after A | `4dcfa55d…` | `8ab33ef8…` | 绿 | 9/9 |
| C→B→A | empty | `e7da8047…` | `8ab33ef8…` | 绿 | 9/9 |

Windows / Ubuntu-22.04 上列 SHA 逐步相同。Windows 全套 31 passed + 2 skipped；Ubuntu 33 passed。分叉：Ubuntu pytest 10 failed / 23 passed；blob 漂移：11 failed / 22 passed。Windows 对应 10 failed / 21 passed + 2 skipped，以及 11 failed / 20 passed + 2 skipped。

final-review 在一次性仓重跑 empty：tree 仍 `8ab33ef8…`，身份 1 passed，交错 9 passed；hostile 矩阵 46/46。重跑 commit SHA 与 repair 不同（作者/日期另造），tree 相同，不构成身份漂移。

## 判定与发现

**PASS。** 候选钉值成立；`assertNotEqual` 是后代不等式，不是当前 HEAD 相等；repair SHA256SUMS 77/77；跨系统/顺序/empty/hostile 只读证据一致。

| 级 | id | 结论 |
| --- | --- | --- |
| P3 | F-p3-assertNotEqual-naive-substring | 子串 `identities["head"], SOURCE_HEAD` 命中 L540 `assertNotEqual`；独立 AST 已纠偏，不是候选缺陷。 |
| P3 | F-p3-prior-final-review-incomplete-self-patch | `cursor-g1-g5-postcommit-head-final-review-20260914-01` 无 `review.md`/`review.json`，留有 `run_review.py` 与 `_patch_static.py`；后者回写了 4 份 Windows/顶层 JSON。Linux hostile 矩阵不在回写名单且已记录 `no_head_equality_to_source=true`。不改变本评独立裁决。 |
| P3 | F-p3-prior-finalize-incomplete | `cursor-g1-g5-postcommit-head-finalize-20260914-01` 仅有 `candidate-hashes.json` 与 `_verify.py`。本目录是完成收据，不是候选缺陷。 |

## 非声称

不关闭 #39 / G1 / G5 / G3 / G6 / Full，不把 7/7 部分离线写成整行覆盖，也不把交错 9/9 或本评绿写成 53/53、721、#83 或飞行验收。未运行测试。未做 native / model / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83。主仓无 `git add` / commit / stage / reset / clean。本文件不是 commit。
