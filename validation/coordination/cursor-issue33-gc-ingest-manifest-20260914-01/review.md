# #33 GC/倍率离线比较器精确入库审计与私有索引演练

2026-09-14。对已稳定的 #33 GC/倍率离线比较器候选做精确入库审计，并用系统 TEMP 中的独立 `GIT_INDEX_FILE` 演练暂存。不修改任何既有候选或历史回执。不使用真实 Git index。不 add/commit/push/关票。

**裁决：PASS。** 0 P1；0 P2。

这不是 #33/#84 验收，也不是 MIXED/G6/Full 通过或 owner approval。`causal=false`，`performance_pass=false`。

## 派发

```text
工作类别：review/ingest-planning
实际 cwd、分支、HEAD：C:/Users/PC/Documents/odid编译/wksim  main  5370b2324672c9036d41239cb93e21fc5eb42897
架构祖先检查退出码：0（f333316e6efa6b299b4288a9d91fb2bccedfb9d6 ⊆ HEAD）
已读：AGENTS.md、docs/architecture-implementation-20260912.md、docs/coordination/architecture-continuation-20260913.md
本次 module / interface：无产品代码变更；只审计 #33 已稳定离线比较器候选的入库集合
独占写入：validation/coordination/cursor-issue33-gc-ingest-manifest-20260914-01/{exact-paths.txt,review.md,review.json,SHA256SUMS}
直接依赖（只读）：下列恰好 12 路径；不改其字节
沿用的 adapter：无
受影响测试：只读重跑 validation.test_compare_joint_gc_diagnostics（53/53）
验收资源/候选身份：当前六源权威 SHA 见下；review-01 为修复前历史
交付后停止写入：本目录四文件写完即停
范围外：native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83；
        真实 git add/commit/push/关票/owner approval；
        docs/Prometheus.gitmodules.reference；
        validation/coordination/short-cycle-dispatches.json；
        #29/#60、delivery/scene frontier 及其他 untracked
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审计在主代理内完成，没有改用其他子代理模型顶替。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| HEAD 钉死且架构祖先为 0 | **PASS** | `5370b2324672c9036d41239cb93e21fc5eb42897`；`merge-base --is-ancestor f333316e… HEAD` 退出码 0 |
| 恰好 12 路径，皆普通文件，无符号链接 | **PASS** | 12/12 存在；`is_file`；`is_symlink=False`；Windows reparse=False |
| 当前权威六源哈希 | **PASS** | 六枚当前字节与派发钉一致 |
| 两份历史 review.json 严格解析 | **PASS** | UTF-8、无 BOM、无重复键；回执目录文件集合均为 `{review.md,review.json,SHA256SUMS}` |
| review-01 绑定修复前六源且 P2=5 | **PASS** | 按 **FAIL 待修历史**保留；历史 SHA 与当前字节不一致属预期，未改写旧回执 |
| review-02 绑定当前权威哈希且 0 P1/P2 | **PASS** | 六源均为当前钉，`match=true`；P1=0，P2=0，P3=5 |
| 正式测试 | **PASS** | `python -B -m unittest validation.test_compare_joint_gc_diagnostics` → 53/53 OK，1.265s |
| 声明边界 | **PASS** | `causal=false`，`performance_pass=false`；#33/#84/MIXED/G6/Full 未通过 |
| 私有 index 恰好 12 条 A | **PASS** | TEMP `GIT_INDEX_FILE` + `read-tree HEAD`；6 条普通 add、6 条 `-f`；cached 集合=12、全部 A |
| 禁入项未进入清单/私有 cached | **PASS** | 无两份受保护文件；无 #29/#60；无 delivery/scene frontier；无其它 untracked |
| 真实 index 仍为空 | **PASS** | `git diff --cached --name-only` 空；`.git/index` SHA-256/字节/mtime 演练前后相同 |
| 本审查总体 | **PASS** | 0 P1 / 0 P2 |

## 12 路径与状态

重新计算的 SHA-256（工作树当前字节）。全部为普通文件，无符号链接。

| # | 路径 | 字节 | SHA-256 | 状态 |
| ---: | --- | ---: | --- | --- |
| 1 | `tools/compare_joint_gc_diagnostics.py` | 64689 | `d836333025a186f6f2c7c085aff686271792cfcd4fbbda16cb7802f78c6c66e7` | 存在/普通文件；当前权威 tool |
| 2 | `validation/test_compare_joint_gc_diagnostics.py` | 59273 | `b53f427d05c4530600326a8068490feb9ab3a7c4729c28459c58d63338ca500d` | 存在/普通文件；当前权威 test |
| 3 | `docs/coordination/c2-gap-bounds-20260913.md` | 14207 | `63431c1b3289ba6f83db4cb2434f7c5ecf00ae6095f3d701656ec1de6daf93af` | 存在/普通文件；当前权威 C2 间隙 |
| 4 | `docs/coordination/c2-phase-correlation-20260913.md` | 14198 | `a8fef46b8fad7e83aaf4d9f1e8f94eb014fb7619af3baf905ffb3610d39038da` | 存在/普通文件；当前权威 C2 相位 |
| 5 | `docs/plan/33-rate-measured-candidate-20260912.md` | 13417 | `d02ba65adf7af9bd8883ce9b27d548b095785582b010279c5ddf0bddb9b03a50` | 存在/普通文件；当前权威实测候选 |
| 6 | `docs/plan/33-rate-next-diagnostic-20260912.md` | 23881 | `4ccf92ecd25cde1e778cd6b2c2102cbc12b32160c1aa23d9eeb3c0aa04b1b358` | 存在/普通文件；当前权威下一步诊断 |
| 7 | `validation/coordination/cursor-issue33-gc-diagnostics-independent-review-20260914-01/review.md` | 11687 | `1068a3bd587061996924335adacd74643df8c7a070e55aa662f5744cbe865c72` | 回执-01；未改 |
| 8 | `validation/coordination/cursor-issue33-gc-diagnostics-independent-review-20260914-01/review.json` | 11341 | `5cf4139ff0fb9ba56bdd15b76f0f4c3ed8b92ef3f471b15b7ee321027319a5f8` | 回执-01；未改 |
| 9 | `validation/coordination/cursor-issue33-gc-diagnostics-independent-review-20260914-01/SHA256SUMS` | 825 | `ea7272bec0d1b2f3bd8ea2ef53cc0ba11ba7fc24b988f6b64f64e07bd2645278` | 回执-01；未改 |
| 10 | `validation/coordination/cursor-issue33-gc-diagnostics-independent-review-20260914-02/review.md` | 12199 | `3efac0773e4e6d060d47e2b751dc1b286750908344a7ab6dc4ea6046bd4e150a` | 回执-02；未改 |
| 11 | `validation/coordination/cursor-issue33-gc-diagnostics-independent-review-20260914-02/review.json` | 17254 | `3b860a3643a59e1802d18f0ab84bc380a89d1c55fc855b01dec50bb225765e6f` | 回执-02；未改 |
| 12 | `validation/coordination/cursor-issue33-gc-diagnostics-independent-review-20260914-02/SHA256SUMS` | 154 | `8afffe5d0430c79e26ccdc292afdae892ba49727adfaf0e1b83e6266c68d7d3f` | 回执-02；未改 |

两个回执目录的文件集合均为恰好 3：`review.md`、`review.json`、`SHA256SUMS`。

## 历史哈希解释（预期不一致，不是缺陷）

review-01 绑定修复前六源，且含 P2=5。按本切片规则 **0 P1/P2 才 PASS**，因此将该回执明确按 **FAIL 待修历史**保留。其 `overall` 字段当时写成 `PASS`，本审计不回写、不改字节。历史 SHA 描述当时工作树，与**当前**权威六源不一致是预期，不得据此要求旧源 hash 等于当前，也不得回写旧文件。

| 对象 | review-01 历史 SHA | 当前权威 SHA | 相对当前 |
| --- | --- | --- | --- |
| tool | `c3ef5ef5603f924d618ab93c15e786941cf666b5314471018e2314d7c7e2949d` | `d836333025a186f6f2c7c085aff686271792cfcd4fbbda16cb7802f78c6c66e7` | 不一致（预期） |
| test | `d635d410eb1d73699ba2c6ea08f3b353fb0f829bb3e74c4aa031950e1210e2c1` | `b53f427d05c4530600326a8068490feb9ab3a7c4729c28459c58d63338ca500d` | 不一致（预期） |
| C2 间隙 | `f23d8e16fb7511f0996f3920309d27019d3544cab95ea1c6f1e59f85fcc59efc` | `63431c1b3289ba6f83db4cb2434f7c5ecf00ae6095f3d701656ec1de6daf93af` | 不一致（预期） |
| C2 相位 | `11dfba6e9ed5fa3a4c087cb40330def2a6426033c9a17de242b90d6b90e8675e` | `a8fef46b8fad7e83aaf4d9f1e8f94eb014fb7619af3baf905ffb3610d39038da` | 不一致（预期） |
| 实测候选 | `1be6b97bffc362bc29c33b464fbdfc72e243e99c5c81d3da191d8fb71b1b9d86` | `d02ba65adf7af9bd8883ce9b27d548b095785582b010279c5ddf0bddb9b03a50` | 不一致（预期） |
| 下一步诊断 | `f8657d39a2f2a0c0894373c559ab3c3a2e4e915fb039598f3ee9aa804cb102ce` | `4ccf92ecd25cde1e778cd6b2c2102cbc12b32160c1aa23d9eeb3c0aa04b1b358` | 不一致（预期） |

review-02 必须且已经绑定当前权威六源：六枚均为 `match=true`，P1=0，P2=0。

未篡改的历史记录：

- review-01：文件内 `overall=PASS`，P1=0，P2=5，P3=4，当时正式测试 38/38；本审计按 **FAIL 待修历史**保留
- review-02：`PASS`，P1=0，P2=0，P3=5，正式测试 53/53；离线比较器可用，不是 #33/#84 验收

issue33-01 的 `SHA256SUMS` 额外列出当时六份源文件哈希；这些行对应当时字节，不要求等于当前权威源。其 `review.md`/`review.json` 行仍与磁盘一致。

## 测试与声明边界

`python -B -m unittest validation.test_compare_joint_gc_diagnostics` → Ran 53 tests in 1.265s，OK。未重跑 native / UE / 物理闭环 / #83。

契约保持：`causal=false`，`performance_pass=false`，`classification=candidate_not_performance_pass`。#33 与 #84 仍 OPEN；MIXED / G6 / Full 未通过；manager99 倍率门未满足。compared 不是性能通过，也不是因果结论。

## 私有索引演练

主仓 `.git/index` 从未作为 `GIT_INDEX_FILE`。演练仅在

`C:\Users\PC\AppData\Local\Temp\wksim-i33-gc-ingest-20260914-01\private.index`

1. `GIT_INDEX_FILE=<TEMP>/…/private.index git read-tree HEAD`（退出码 0）
2. 非忽略 6 条精确 `git add -- <path>`
3. 忽略目录 6 条精确 `git add -f -- <path>`（`.gitignore` `/validation/*/`）
4. `git diff --cached --name-only` / `--name-status` 相对 HEAD
5. 删除私有 index 与目录；无 lock 残留

结果：私有 cached **集合恰好 12 路径**，全部 `A`，extra/missing/duplicate 空。`git diff --cached --name-only` 按路径排序输出，不等于 `exact-paths.txt` 的派发顺序；集合相等。未进入受保护文件、#29/#60、delivery/scene frontier、或其他工作树 untracked。12 路径均不在 HEAD 树中。

6 条普通 add：#1 tool、#2 test、#3 C2 间隙、#4 C2 相位、#5 实测候选、#6 下一步诊断。  
6 条 `-f`：两个回执目录各 3 个文件。

## 真实索引状态

演练前/后相同：

| 项 | 值 |
| --- | --- |
| HEAD / `main` | `5370b2324672c9036d41239cb93e21fc5eb42897` |
| `.git/index` SHA-256 | `f2c7c20360e034c6fa7c1be13029220cbdac7c50460b24b140a2fb4c679bb834` |
| `.git/index` 字节 | 1594024 |
| `.git/index` mtime UTC | 2026-09-14T00:15:29.695124Z |
| `.git/index` mtime_ns | 1789344929695124400 |
| `git diff --cached --name-only` | 空 |
| 进程/壳层 `GIT_INDEX_FILE` | 未设置 |
| TEMP 私有 index | 已删除 |

工作树仍有其它已跟踪脏文件与 untracked（含两份受保护文件、#29/#60 与 delivery/scene frontier）；它们不在本 12 路径清单，也未进入私有 cached。

## 绝不进入本清单

| 路径/类 | 处理 |
| --- | --- |
| `docs/Prometheus.gitmodules.reference` | 受保护；工作树已修改；未入 12，未入私有 cached |
| `validation/coordination/short-cycle-dispatches.json` | 受保护；工作树已修改；未入 12，未入私有 cached |
| #29/#60 源、报告与回执 | 不在 exact-paths；私有 add 未选中 |
| delivery/scene frontier 及其他 untracked | 不在 exact-paths；私有 add 未选中 |
| 本目录四件 | 描述 12 条集合，自身不计入这 12 |

## 限制

- 入库规划与私有演练，不是一次主仓 add/commit，也不关 #33/#84
- 不宣布 MIXED、G6、Full、Goal complete 或 owner approval
- 未重跑 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83
- 历史 review-01 的 P2=5 与当时 38/38 测试结果保持原记录，按 FAIL 待修历史保留
