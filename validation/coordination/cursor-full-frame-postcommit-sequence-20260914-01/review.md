# 双顺序模拟提交审计 — Full 原始 AC 账本 × G6 frame/datum

- 切片：`cursor-full-frame-postcommit-sequence-20260914-01`
- 锚定 HEAD：`6eafdf9c0b734db07a9fe790c86b409d3468c10b`（`main`）
- 祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6`：exit 0
- 只读候选：Full 四份 + Frame 三份
- **总体：PASS** — 0 P1 / 0 P2 / 3 P3。Full→Frame 与 Frame→Full 均只在临时仓提交；每步基线祖先、候选 `HEAD:` blob 与 `git show` 语义成立。Windows 与 Ubuntu-22.04 最终态均为 Full **81/81** 与 frame **12/12**；空提交后树不变、HEAD 改变，依赖 HEAD 的代表项仍过。

这不是 owner 批准，也不关闭 Full / G6 / #59 / #60。R1 仍为 `numerical_failed`。

```text
工作类别           : read-only dual-order postcommit simulation audit
                     （非新架构验收、非历史对照晋升、非 owner 批准）
cwd / 分支 / HEAD  : C:/Users/PC/Documents/odid编译/wksim / main
                     6eafdf9c0b734db07a9fe790c86b409d3468c10b
架构祖先           : git merge-base --is-ancestor
                     f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> exit 0
module / interface : Full 原始 AC 缺口账本；G6/B2 e0 frame/datum 绑定
独占写入           : validation/coordination/cursor-full-frame-postcommit-sequence-20260914-01/**
只读输入           : 七份候选；
                     cursor-full-ac-precommit-audit-20260914-01/**
                     cursor-g6-frame-datum-precommit-audit-20260914-01/**
验证               : 路径限定 lean archive + 可弃用 git；
                     Full→Frame / Frame→Full；
                     Windows / Ubuntu-22.04 最终态 81+12；
                     空提交后复跑 HEAD 依赖代表项
范围外             : 候选编辑；历史回执改写；主树 add/commit/stage/reset/clean；
                     native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE /
                     构建 / 飞行 / #83
```

本界面不可选 `gpt-5.6-luna` / `gpt-6-astra`。审查在主代理完成，没有改用其他子代理模型顶替。

已读：`CONTEXT-MAP.md`、`wksim/CONTEXT.md`、父仓 `CONTEXT.md`、`wksim/AGENTS.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、两份 2026-09-14 precommit 回执。父仓 `docs/adr/*` 不自动约束 wksim；本检出没有本地 ADR。`docs/agents/issue-tracker.md` 在本检出中不存在，已记录缺失。

## 1. 门控表

| 门 | 判定 | 证据 |
| --- | --- | --- |
| 候选 SHA-256 等于 precommit 钉 | **PASS** | 七哈希全程一致；审计前后未漂 |
| 独立总量 38 / 255 / 190 / 65 / 40 / 150 / 22 / 8 / 8 | **PASS** | heading-stack 复算；65 非 AC 未进入 `omitted_acs` |
| frame RHS / counts / observables / manifest fail-closed | **PASS** | 两侧最终态 12/12；空提交后 8/8 HEAD 依赖仍过 |
| Full→Frame 每步祖先与 blob | **PASS** | 基线 `6eafdf9` 与 `f333316e` 均为祖先；`git show HEAD:` 与工作区钉值一致 |
| Frame→Full 每步祖先与 blob | **PASS** | 同上；同主机两种顺序最终 tree 相同 |
| 最终态 Full 81 + frame 12 | **PASS** | Windows 与 Ubuntu 各两顺序全套 81/81、12/12 |
| 空提交不改树、不误钉精确 HEAD | **PASS** | 四次空提交 `tree_unchanged`；HEAD 已不是 `6eafdf9`；代表项仍过 |
| 主仓未被改写 | **PASS** | 项目 HEAD 仍为 `6eafdf9`；七候选仍为 `??`；无 stage |
| 未整仓 archive 入内存 | **PASS** | lean tar 811 成员 / 546 007 040 字节，写盘后删除 |
| 本审计总体 | **PASS** | 最小提交集 = 七次普通 `git add`（分两组）；`git add -f` 为空 |

## 2. 冻结哈希（独立重算，未漂）

| 路径 | SHA-256 | 字节 | CR |
| --- | --- | ---: | ---: |
| `docs/plan/full-original-ac-gap-ledger-20260914.md` | `5a4d9a649abeb57b423d98b84fdf8c59c965afd74a92ba88061ee48a1c44ad3e` | 25570 | 216 |
| `validation/full-original-ac-gap-ledger-20260914.json` | `4e1f9b9e80ce07265c4b25cca6fc084a200a18051536d2b3f3243c5b79fd1d16` | 225429 | 6718 |
| `validation/test_full_original_ac_gap_ledger.py` | `d2a241c97c50549e2aae9226163a61f3445787f886b04eeae42fcf74af7367a1` | 75771 | 1554 |
| `validation/full-original-ac-gap-ledger-snapshot-20260914.json` | `c8af0dcef3dfc3a78141d381a9cb307fc5a0a223cc9c2898a5a34fd0ffae1ef4` | 91924 | 400 |
| `docs/plan/59-e0-frame-datum-binding-20260914.md` | `3fbb0e7fbdbc069a702dd0e8417c9b6a8dd3961575d5a188817990b280b553f8` | 15449 | 0 |
| `validation/e0-frame-datum-binding-20260914.json` | `5d589075c128e2a22d24d88d7dea0ce753a68f4d46937386c581d3fae945b69f` | 105018 | 0 |
| `validation/test_e0_frame_datum_binding.py` | `e412f2d1981fd02b34531426f31c6f010c96d15331bf41f30fc136cc59f10da6` | 77146 | 0 |

与 `cursor-full-ac-precommit-audit-20260914-01`、`cursor-g6-frame-datum-precommit-audit-20260914-01` 钉值一致。提交后 `git show HEAD:<path>` 的 SHA-256 与上表相同。

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
| CLOSED 仍有未勾选 AC | **22** |
| OPEN 仍有未勾选 AC | **8** |
| CLOSED 且 AC 全勾选 | **8** |

`omitted_acs` 61 条全部是 AC 形 id，与 65 个 `{issue}:x{ordinal}` 不相交。`full_program` / G0–G6 均为 `not-closed`，`claims_acceptance=false`。

## 4. 低内存临时树

方法：`git archive --format=tar -o <temp> HEAD --` 路径限定列表（`.gitignore` + Full `cited_sources` 中已在 HEAD 的项 + Frame 23 个 pin），流式解压后删除 tar。`objects/info/alternates` 指向主仓 objects，不复制对象库，不把整仓 archive 读进内存。

| 量 | 值 |
| --- | --- |
| lean 成员 | 811 |
| lean tar | 546 007 040 字节 |
| 整仓 archive 入内存 | 否 |
| 七候选在 HEAD archive | 否 |
| Windows 树 | `%TEMP%\wksim-full-frame-postcommit-win-jiwoxhro` |
| Ubuntu 树 | `/tmp/wksim-full-frame-postcommit-lin-snwnmui0` |

## 5. 两种提交序列

每步核验：`merge-base --is-ancestor 6eafdf9 HEAD`、`f333316e HEAD`、本组 `git show HEAD:` 与钉值一致、未提交组 `cat-file -e` 为 128。`git add -f` 未使用。

### 5.1 Full → Frame

| 主机 | 步 | HEAD | tree | parent |
| --- | --- | --- | --- | --- |
| Windows | 0 基线 | `6eafdf9c…` | `435471df…` | `0785f0e6…` |
| Windows | 1 Full | `83dd38259b9e1a47baa20e3bd903dab11c322389` | `6204cc12…` | `6eafdf9c…` |
| Windows | 2 Frame | `d5842e882c49fb6957d1382995e6d673ae1e4691` | `e608b71d…` | `83dd3825…` |
| Windows | 3 空提交 | `949e1e28c4e4edf9394eb1ba1a91f9b19c1ed2a3` | `e608b71d…`（不变） | `d5842e88…` |
| Ubuntu | 1 Full | `2cc416db9245d80dfa3159b592635a9e3c4b2712` | `e6248838…` | `6eafdf9c…` |
| Ubuntu | 2 Frame | `439d79ebcac912b6505f7fff40e341935d1269e7` | `818b62aa…` | `2cc416db…` |
| Ubuntu | 3 空提交 | `652e9f2de43e5f0df85ee048c0c1180cd73082de` | `818b62aa…`（不变） | `439d79eb…` |

### 5.2 Frame → Full

| 主机 | 步 | HEAD | tree | parent |
| --- | --- | --- | --- | --- |
| Windows | 1 Frame | `0738ff41c2965126d7e584181d9704ccbf0c3f45` | `6ca1639c…` | `6eafdf9c…` |
| Windows | 2 Full | `3cc6fe78ffde2ffd5f5525bebb99be9012e46f2c` | `e608b71d…` | `0738ff41…` |
| Windows | 3 空提交 | `7e80fb0b39044f0a8942902c1fa7e0b17ff85483` | `e608b71d…`（不变） | `3cc6fe78…` |
| Ubuntu | 1 Frame | `49e18b1f00ab43de6433b343421ab80bd6f49934` | `3a8920e0…` | `6eafdf9c…` |
| Ubuntu | 2 Full | `e65c72a2473ab1dc981372a03e94ec8f47caced4` | `818b62aa…` | `49e18b1f…` |
| Ubuntu | 3 空提交 | `775f06a126254063ecca56779f19b16852babc3d` | `818b62aa…`（不变） | `e65c72a2…` |

同主机两种顺序的最终 tree 相同（Windows `e608b71d…`，Ubuntu `818b62aa…`）。候选内容 blob SHA-1 两侧一致：

| 路径 | blob SHA-1 |
| --- | --- |
| Full plan | `bbc43cc3d086da97a4868f312e5ff13ca6e3f232` |
| Full ledger | `808959570f00131e10b37f2d9c0ff14151367982` |
| Full test | `6801fc45d30383ebea71172252a2fd274160dc6a` |
| Full snapshot | `67de6d93c09cdb96185ff2cc89097a8bd713a065` |
| Frame plan | `3ca1213488a70b9982a5c7705f51a6a66fd1ae79` |
| Frame payload | `64acd9c8e51e9418e05866f15631e1b8e1e2be80` |
| Frame test | `985d7c6fd8348b6aba5d0c126b22b3dc87271b6a` |

跨主机最终 tree 不同，见 P3。每步清单在 `steps/*.json`。

## 6. 最终态套件与空提交复跑

| 主机 | 顺序 | Full 81 | frame 12 | 空提交后 Full HEAD 依赖 | 空提交后 frame HEAD 依赖 |
| --- | --- | --- | --- | --- | --- |
| Windows 3.13.11 | Full→Frame | 81/81，7.895 s | 12/12，48.952 s | 5/5，7.924 s | 8/8，45.361 s |
| Windows 3.13.11 | Frame→Full | 81/81，9.011 s | 12/12，54.946 s | 5/5，8.974 s | 8/8，46.171 s |
| Ubuntu-22.04 3.10.12 | Full→Frame | 81/81，0.616 s | 12/12，25.381 s | 5/5，0.501 s | 8/8，23.203 s |
| Ubuntu-22.04 3.10.12 | Frame→Full | 81/81，0.625 s | 12/12，24.669 s | 5/5，0.529 s | 8/8，15.015 s |

空提交后 HEAD ≠ `6eafdf9`，tree 未变。Full 账本 JSON 里的 `head` 仍是捕获钉，不是当前 `rev-parse HEAD`。Frame `test_head_and_baseline` 用祖先关系，不要求精确 HEAD。因此精确 HEAD 误钉没有出现。

## 7. 按严重度排列的发现

无 P1。无 P2。

### P3 — F-windows-git-rmtree-locked

Windows 第一顺序完成后删除 disposable `.git` 时，`objects/04/d1741b…` 被锁（WinError 5）。第一顺序已经写完。第二顺序改为 `update-ref HEAD 6eafdf9` + `read-tree`，不再 `rmtree`。不是候选缺陷。

### P3 — F-path-limited-archive-required

完整 `git archive HEAD` 约 5.97 GiB。本审计只用 811 成员 / 546 MB 的路径限定 tar，且不把整仓读进内存。

### P3 — F-cross-host-tree-sha-filemode

同主机两种顺序最终 tree 相同；Windows `e608b71d…` 与 Ubuntu `818b62aa…` 不同。七份候选的内容 SHA-256 与 blob SHA-1 两侧相同。差异来自 WSL `/mnt/c` 上 overlay 文件的可执行位进入 tree，不是候选字节。套件判定不依赖跨主机 tree SHA。

## 8. 非声称

通过本审计、81 项或 12 项套件，不批准 owner 项，不关闭/重开任何 issue，不把 G0–G6、Full、#59、#60 写成已关闭，不改判 R1 `numerical_failed`。未重跑 #83，未做 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行。主仓无 `git add` / commit / stage / reset / clean。可弃用树里的 commit 只用于提交后探针，不是项目提交。
