# G1/G5 提交后 HEAD 语义修复

2026-09-14。只改 `validation/test_g1_g5_offline_drift.py`。新写仅
`validation/coordination/cursor-g1-g5-postcommit-head-repair-20260914-01/**`。
未改 G3、frame 或任何历史回执。

**本切片：候选语义已按 P1 改为来源/祖先钉，并在临时仓复测中绿。这不是晋升，不关闭 #39 / G1 / G5 / Full。**

## 派发

```text
工作类别：new-development（测试身份语义；非新架构验收、非历史对照、非晋升）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：CONTEXT-MAP.md、wksim/CONTEXT.md、ADR 0003（仅 Ubuntu-22.04 对照宿主）、
      AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、
      cursor-g1-g5-precommit-audit-20260914-01、
      cursor-g1-g5-s4-final-review-20260914-01、
      cursor-stable-slices-postcommit-sequence-20260914-01（P1 FAIL）
module / interface：G1/G5 离线身份门；SOURCE_HEAD 祖先钉 + 七行产品 blob
独占写入：validation/test_g1_g5_offline_drift.py
          validation/coordination/cursor-g1-g5-postcommit-head-repair-20260914-01/**
依赖（只读）：两枚 promotion-flight JSON、两个 helper（字节未改）；
             HEAD 中的七行产品源；切片 B/C 只读叠入临时仓
验证：Windows / Ubuntu-22.04 全套 pytest+unittest；
      低内存临时仓 A→B→C 与 C→B→A；提交后 / 终态 / empty commit；
      分叉与 blob 漂移 fail-closed；官方交错代表集
范围外：改 G3/frame/历史回执、主仓 add/commit/stage/reset/clean、
        整仓 archive 进内存、native / build / flight / #83
```

父级 CONTEXT-MAP 写明既有 AeroTwinSim ADR 不自动约束 wksim。ADR 0003 只作为 Ubuntu-22.04 对照宿主说明被读过。

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。修复在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 主仓 HEAD 仍为 `6eafdf9`，`f333316` 为祖先 | **PASS** | 开工与收工均为 `6eafdf9c…`，祖先退出码 0 |
| P1 不再要求当前 HEAD 精确等于来源钉 | **PASS** | `PINNED_HEAD` 已删除；`SOURCE_HEAD` 只作 `merge-base --is-ancestor` 祖先钉 |
| 精确 6 次只读 git 元数据调用 | **PASS** | `rev-parse HEAD`、`merge-base --is-ancestor SOURCE_HEAD HEAD`、`ls-tree HEAD -- <7>`、三次 `diff` |
| 七行产品 blob 仍从当前 HEAD 核对冻结 SHA-1/SHA-256 | **PASS** | 两序列每步 `seven_frozen=true`；empty commit 树不变 |
| staged / unstaged / 缺失 / 替换 / 历史分叉 fail-closed | **PASS** | 套件内 mutation；ABC 临时仓分叉 exit 1、blob 漂移红 |
| Windows 全套 G1/G5 | **PASS** | pytest **31 passed, 2 skipped, 8 subtests**；unittest **33 / OK (skipped=2)** |
| Ubuntu-22.04 全套 G1/G5 | **PASS** | pytest **33 passed, 8 subtests**；unittest **33 / OK** |
| 官方交错代表集在 HEAD 前进后仍绿 | **PASS** | 两端 ABC/CBA 终态与 empty 均为 **9 passed** |
| 主仓未被 add/commit/stage/reset/clean | **PASS** | HEAD 仍 `6eafdf9`；两处事先脏文件未触碰 |
| 两枚飞行钉与两个 helper 字节未改 | **PASS** | 四个 SHA-256 与预提交钉一致 |
| 本切片总体 | **候选语义 PASS** | 不关闭 #39 / G1 / G5 / Full |

## 修前失败绑定

见 `before-failure.json`。绑定刚完成的
`cursor-stable-slices-postcommit-sequence-20260914-01`：

- 旧候选 SHA-256 `0281f8317902d74add3b9f1648cbaeb578562616682e3a30437fd05c04538c92`（32738 字节）
- `HeadIdentityTests.test_head_and_row_blobs_fail_closed_on_drift` 第 344 行
  `self.assertEqual(identities["head"], PINNED_HEAD)`
- `PINNED_HEAD = 6eafdf9c0b734db07a9fe790c86b409d3468c10b`
- 旧 ABC after A HEAD `5f0e6125c984b89edd2e53eebe6cc3ee77a49449` 即红

旧候选从未入库；本切片覆盖工作区文件后不再重建旧字节。修前失败以该回执的哈希与断言文本为准。

## 候选新哈希与计数

| 项 | 旧 | 新 |
| --- | --- | --- |
| `validation/test_g1_g5_offline_drift.py` SHA-256 | `0281f831…538c92` | **`83234a89fa62be49931dc1adee7d36e8a7780d9f8f781b854f69214d388a12c5`** |
| 字节 | 32738 | **42074** |
| CR | 730 | 917（仍为 CRLF） |
| 只读 git 调用 | 5 | **6** |
| 收集用例 | 20 | **33** |
| Windows pytest | 18 passed + 2 skipped | **31 passed, 2 skipped, 8 subtests** |
| Windows unittest | 20 / skipped=2 | **33 / OK (skipped=2)** |
| Ubuntu pytest | 20 passed | **33 passed, 8 subtests** |
| Ubuntu unittest | 20 | **33 / OK** |

Windows 保留既有两项 skip：`test_posix_absent_receiver_in_owned_0700_directory`（非 POSIX）、`test_decode_datagram_on_available_pinned_dialect`（本机无 `/root/wksim-telemetry-dialects-20260906-3`）。Ubuntu-22.04 两项都跑到。

新增不是删断言：`SOURCE_HEAD` 祖先钉；后代 HEAD + 冻结 blob 必须过；`ancestor_code=1`、blob SHA-1 漂、缺失、替换、staged、unstaged、`vs_head`、丢掉 `merge-base` 调用必须红；写动词与无 `--is-ancestor` 的 `merge-base` 被拒绝；mock 读者对后代 HEAD 过、对分叉记 `ancestor_code=1` 再 fail-closed。

## 两序列（after）

临时仓：`objects/info/alternates` + `hash-object --no-filters` + `commit-tree`。未整仓 archive。Windows 与 Ubuntu 用相同作者/提交日期，逐步 commit SHA 一致。终态 tree 与顺序无关：`8ab33ef851c73a5bf32d5dbd848cc00c52a021d5`。

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

CBA after C 的 tree `6ca1639c…` 与既有 frame 单切片 tree 相同，说明未改 C。

ABC 分叉：`merge-base --is-ancestor SOURCE_HEAD HEAD` 退出码 1；身份门红（Ubuntu pytest 10 failed / 23 passed）。ABC blob 漂移：`task.py` HEAD blob 不再等于冻结钉；身份门红（Ubuntu pytest 11 failed / 22 passed）。

## 精确 force-add 依赖（字节未改）

| 路径 | SHA-256 | add |
| --- | --- | --- |
| `…/independent-candidate/flight-audit.json` | `b1df8a36…eb68b9a` | `-f` |
| `…/flown-source/manifest.json` | `156ed0de…3e1719` | `-f` |
| `…/stdlib_identity_plugin.py` | `e7044fb5…20101f` | `-f` |
| `…/isolation_after_g1g5.py` | `e540760a…33fa94` | `-f` |

## 非声称

不关闭 #39 / G1 / G5 / G3 / G6 / Full，不把 7/7 部分离线写成整行覆盖，也不把交错 9/9 或本切片绿写成 53/53、721、#83 或飞行验收。无动力学、套接字或产品进程声称。未做 native / model / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83。主仓无 `git add` / commit / stage / reset / clean。本文件不是 commit。
