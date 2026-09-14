# #29/#60 精确入库审计与私有索引演练

2026-09-14。对已稳定的 #29 离线准入助手与 #60 Full 报告层候选做精确入库审计，并用系统 TEMP 中的独立 `GIT_INDEX_FILE` 演练暂存。不修改任何既有候选或历史回执。不使用真实 Git index。不 add/commit/push/关票。

**裁决：PASS。** 0 P1；0 P2。

这不是 #29/#60 验收，也不是 Full/G6 通过或 owner approval。

## 派发

```text
工作类别：review/ingest-planning
实际 cwd、分支、HEAD：C:/Users/PC/Documents/odid编译/wksim  main  5370b2324672c9036d41239cb93e21fc5eb42897
架构祖先检查退出码：0（f333316e6efa6b299b4288a9d91fb2bccedfb9d6 ⊆ HEAD）
已读：AGENTS.md、docs/architecture-implementation-20260912.md、docs/coordination/architecture-continuation-20260913.md
本次 module / interface：无产品代码变更；只审计 #29/#60 已稳定候选的入库集合
独占写入：validation/coordination/cursor-issue29-60-ingest-manifest-20260914-01/{exact-paths.txt,review.md,review.json,SHA256SUMS}
直接依赖（只读）：下列恰好 16 路径；不改其字节
沿用的 adapter：无
受影响测试：只读重跑 validation.test_aruco_native_targets（34/34）；#60 机械计数只读重验
验收资源/候选身份：#29 当前权威 tool/test/doc 与 #60 当前报告哈希见下
交付后停止写入：本目录四文件写完即停
范围外：native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83；
        真实 git add/commit/push/关票；#33 当前仍在修改的文件；
        docs/Prometheus.gitmodules.reference；
        validation/coordination/short-cycle-dispatches.json
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。审计在主代理内完成，没有改用其他子代理模型顶替。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| HEAD 钉死且架构祖先为 0 | **PASS** | `5370b2324672c9036d41239cb93e21fc5eb42897`；`merge-base --is-ancestor f333316e… HEAD` 退出码 0 |
| 恰好 16 路径，皆普通文件，无符号链接 | **PASS** | 16/16 存在；`is_file`；`is_symlink=False`；Windows reparse=False |
| 当前权威源哈希 | **PASS** | #29 tool/test/doc 与 #60 report 四枚当前字节与派发钉一致 |
| 四份历史 review.json 严格解析 | **PASS** | UTF-8、无 BOM、无重复键；回执目录文件集合均为 `{review.md,review.json,SHA256SUMS}` |
| review-01 绑定修复前源/报告 | **PASS** | 历史 SHA 与当前字节不一致，属预期，未改写历史 verdict |
| review-02 绑定当前权威哈希 | **PASS** | #29 三源与 #60 报告均为当前钉，`match=true` |
| #29 正式测试 | **PASS** | `python -B -m unittest validation.test_aruco_native_targets -v` → 34/34 OK，0.011s；未重跑 native |
| #60 机械计数与 G0–G6 | **PASS** | 源/报告 48/48、键序相同；accepted=0/partial=12/blocked=8/not-tested=28；G6=blocked |
| 私有 index 恰好 16 条 A | **PASS** | TEMP `GIT_INDEX_FILE` + `read-tree HEAD`；4 条普通 add、12 条 `-f`；cached 集合=16、全部 A |
| 禁入项未进入清单/私有 cached | **PASS** | 无两份受保护文件；无 #33 当前修改文件；无其它 untracked |
| 真实 index 仍为空 | **PASS** | `git diff --cached --name-only` 空；`.git/index` SHA-256/字节/mtime 演练前后相同 |
| 本审查总体 | **PASS** | 0 P1 / 0 P2 |

## 16 路径与状态

重新计算的 SHA-256（工作树当前字节）。全部为普通文件，无符号链接。

| # | 路径 | 字节 | SHA-256 | 状态 |
| ---: | --- | ---: | --- | --- |
| 1 | `docs/coordination/agy-aruco-native-correlation.md` | 6305 | `c2d863c76c1cf832699e919125b412c6280b036f7cd6c3bfd2454af505eaef51` | 存在/普通文件；当前权威 doc |
| 2 | `tools/inspect_aruco_native_targets.py` | 26202 | `03a36c58c67e1e361ddd035d3e3cc440f9ac0544256126687bfec5c7d500838e` | 存在/普通文件；当前权威 tool |
| 3 | `validation/test_aruco_native_targets.py` | 20271 | `e42a0824b8c2a8287dbfda178fa6f17c6e3840cce9bb2913262cdb84e7ed1097` | 存在/普通文件；当前权威 test |
| 4 | `validation/coordination/cursor-issue29-offline-independent-review-20260914-01/review.md` | 10001 | `7298f7babc44786a7c22baa84ba15096109388e736516b69504a80882b4da390` | 回执-01；未改 |
| 5 | `validation/coordination/cursor-issue29-offline-independent-review-20260914-01/review.json` | 9122 | `ff516905e77081f156d02f367275a2a598d5e7be108c71529519937b7c18806f` | 回执-01；未改 |
| 6 | `validation/coordination/cursor-issue29-offline-independent-review-20260914-01/SHA256SUMS` | 485 | `728ffe7210e4a273d0bf99e44d941405621cd068c57554e016c9cd34a93f1952` | 回执-01；未改 |
| 7 | `validation/coordination/cursor-issue29-offline-independent-review-20260914-02/review.md` | 9684 | `700adaf8c01fab6bf97b951ab10897e5c1c6d5922586242a11af2e2ccf03d97d` | 回执-02；未改 |
| 8 | `validation/coordination/cursor-issue29-offline-independent-review-20260914-02/review.json` | 11769 | `88ae7bc7250c2bf3a1bb033d51793dfa02b690d03b01436cda7a41c56d1b4c64` | 回执-02；未改 |
| 9 | `validation/coordination/cursor-issue29-offline-independent-review-20260914-02/SHA256SUMS` | 156 | `7f68b8cf25ccc46f3855699305d3e33f51ade7ea319ac9d63df5de667a58c609` | 回执-02；未改 |
| 10 | `docs/plan/full-acceptance-report.md` | 31086 | `daded67206356478badc508cb9a72544054bf7a0c69dff5477042c77c1caf514` | 存在/普通文件；当前权威 #60 报告 |
| 11 | `validation/coordination/cursor-issue60-full-report-independent-review-20260914-01/review.md` | 9314 | `8e6e64d24d6ae7fcf284c25137c66a7a29260fdb24ab3d5e62527513b79a8b74` | 回执-01；未改 |
| 12 | `validation/coordination/cursor-issue60-full-report-independent-review-20260914-01/review.json` | 13080 | `39de9b5fe5930c4204c9a3d9f87405c5341004d093c85b86cce42969d2fce975` | 回执-01；未改 |
| 13 | `validation/coordination/cursor-issue60-full-report-independent-review-20260914-01/SHA256SUMS` | 156 | `35cdf22b67c1ad8fd2c254a97dc9ad0de4a9862acbb5bf82128cf155ae50cb1f` | 回执-01；未改 |
| 14 | `validation/coordination/cursor-issue60-full-report-independent-review-20260914-02/review.md` | 9613 | `7d6e2f5b021d2f58c85073ed6425b6e7fbfb2f236ae69ead765d9b348db404af` | 回执-02；未改 |
| 15 | `validation/coordination/cursor-issue60-full-report-independent-review-20260914-02/review.json` | 13479 | `35ddcaa736e6ac6c7410ec2e0b5027e50a1726183314ff42d1c75609678bbc1b` | 回执-02；未改 |
| 16 | `validation/coordination/cursor-issue60-full-report-independent-review-20260914-02/SHA256SUMS` | 154 | `0f62129bd1be51c03e3f9bdcb32ba170b561e670951a854db263954cfe2365bd` | 回执-02；未改 |

四个回执目录的文件集合均为恰好 3：`review.md`、`review.json`、`SHA256SUMS`。

## 历史哈希解释（预期不一致，不是缺陷）

review-01 绑定修复前源/报告。其中记录的 source SHA 描述当时工作树，因此与**当前**字节不一致是预期，不得据此改写历史 verdict，也不得回写旧文件。

| 对象 | review-01 历史 SHA | 当前权威 SHA | 相对当前 |
| --- | --- | --- | --- |
| #29 tool | `b370d12dd8574c4d70cd14eb426f12c19b71dc77e4f7aae025a5479c430d7a05` | `03a36c58c67e1e361ddd035d3e3cc440f9ac0544256126687bfec5c7d500838e` | 不一致（预期） |
| #29 test | `fe391a386b26dfce54d99efe5610b167b15303c0e5e373d3d49b99d185cb1bc4` | `e42a0824b8c2a8287dbfda178fa6f17c6e3840cce9bb2913262cdb84e7ed1097` | 不一致（预期） |
| #29 doc | `f9c07b7588e3089bff23ecaf0da16685a92f310a2b01872726cb4af5edb602bc` | `c2d863c76c1cf832699e919125b412c6280b036f7cd6c3bfd2454af505eaef51` | 不一致（预期） |
| #60 report | `3edcc5c84b08cdf02648112c0aa9abd4ebc396dcb266bcc574277d34354721d1` | `daded67206356478badc508cb9a72544054bf7a0c69dff5477042c77c1caf514` | 不一致（预期） |

review-02 必须且已经绑定当前权威哈希：#29 三源与 #60 报告均为 `match=true`。

未篡改的历史 verdict：

- #29 review-01：`PASS`，P1=0，P2=3，P3=5，当时正式测试 28/28；含义为离线准入助手可用，不是 #29 验收
- #29 review-02：`PASS`，P1=0，P2=0，P3=5，正式测试 34/34
- #60 review-01：`PASS`，P1=0，P2=0，P3=2；报告层机械审查，不是 Full/G6 验收
- #60 review-02：`PASS`，P1=0，P2=0，P3=0；同上

issue29-01 的 `SHA256SUMS` 额外列出当时三份源文件哈希；这些行对应当时字节，不要求等于当前权威源。其 `review.md`/`review.json` 行仍与磁盘一致。

## 测试与机械结果

#29：`python -B -m unittest validation.test_aruco_native_targets -v` → Ran 34 tests in 0.011s，OK。未重跑 native / UE / 物理闭环。

#60 只读重验 `docs/plan/full-acceptance-report.md` 对 `docs/plan/full-scope-expansion.md`：

- 源模式 `^\| (SIM\|COMM\|MODEL\|OPS)-\d+ \|`：48 行、48 唯一键、无重复
- 源 SHA-256 `85c15ad817afe35fcd325435f02ccb894ad33015e223537daa3cc3706a564fee`
- 源状态：blocked=8，evidenced=12，not-implemented=28
- 报告：48/48，键集合与键序相同；verdict accepted=0，partial=12，blocked=8，not-tested=28；映射失败空
- partial：SIM-02, SIM-08, COMM-03, OPS-01, OPS-02, OPS-04, OPS-05, OPS-06, OPS-08, OPS-10, OPS-11, OPS-12
- blocked：SIM-01, SIM-05, SIM-06, SIM-09, SIM-10, SIM-12, MODEL-01, OPS-13
- G0–G6：G0/G1/G3/G5=partial，G2/G4/G6=blocked；无 accepted；G6 仍 blocked
- 结论可复述：Full 未通过，G6 未通过，#1/#10/#60 保持 OPEN，无 owner approval

## 私有索引演练

主仓 `.git/index` 从未作为 `GIT_INDEX_FILE`。演练仅在

`C:\Users\PC\AppData\Local\Temp\wksim-i29-60-ingest-20260914-01\private.index`

1. `GIT_INDEX_FILE=<TEMP>/…/private.index git read-tree HEAD`
2. 非忽略 4 条精确 `git add -- <path>`
3. 忽略目录 12 条精确 `git add -f -- <path>`（`.gitignore` `/validation/*/`）
4. `git diff --cached --name-only` / `--name-status` 相对 HEAD
5. 删除私有 index 与目录；无 lock 残留

结果：私有 cached **集合恰好 16 路径**，全部 `A`，extra/missing/duplicate 空。`git diff --cached --name-only` 按路径排序输出，不等于 `exact-paths.txt` 的派发顺序；集合相等。未进入受保护文件、#33 当前修改文件、或其它工作树 untracked。

4 条普通 add：#1 doc、#2 tool、#3 test、#10 report。  
12 条 `-f`：四个回执目录各 3 个文件。

## 真实索引状态

演练前/后相同：

| 项 | 值 |
| --- | --- |
| HEAD / `main` | `5370b2324672c9036d41239cb93e21fc5eb42897` |
| `.git/index` SHA-256 | `f2c7c20360e034c6fa7c1be13029220cbdac7c50460b24b140a2fb4c679bb834` |
| `.git/index` 字节 | 1594024 |
| `.git/index` mtime UTC | 2026-09-14T00:15:29.6951244Z |
| `git diff --cached --name-only` | 空 |
| 进程/壳层 `GIT_INDEX_FILE` | 未设置 |
| TEMP 私有 index | 已删除 |

工作树仍有其它已跟踪脏文件与 untracked（含两份受保护文件与 #33 当前修改文件）；它们不在本 16 路径清单，也未进入私有 cached。

## 绝不进入本清单

| 路径/类 | 处理 |
| --- | --- |
| `docs/Prometheus.gitmodules.reference` | 受保护；工作树已修改；未入 16，未入私有 cached |
| `validation/coordination/short-cycle-dispatches.json` | 受保护；工作树已修改；未入 16，未入私有 cached |
| `docs/plan/33-rate-measured-candidate-20260912.md` | #33 当前仍在修改 |
| `docs/plan/33-rate-next-diagnostic-20260912.md` | #33 当前仍在修改 |
| `tools/compare_joint_gc_diagnostics.py` | #33 当前仍在修改 |
| `validation/test_compare_joint_gc_diagnostics.py` | #33 当前仍在修改 |
| `validation/coordination/cursor-issue33-*`、`cursor-33-*`、`codebuddy-33-*` | #33 审查/诊断目录；不入库 |
| 其它 untracked / 已跟踪脏文件 | 不在 exact-paths；私有 add 未选中 |
| 本目录四件 | 描述 16 条集合，自身不计入这 16 |

## 限制

- 入库规划与私有演练，不是一次主仓 add/commit，也不关 #29/#60
- 不宣布 Full、G6、Goal complete 或 owner approval
- 未重跑 native / 模型 / MATLAB / ROS / DDS / SITL / FC / UE / 构建 / 飞行 / #83
- 历史 review-01 的 P2/P3 与当时 28/28 测试结果保持原记录
