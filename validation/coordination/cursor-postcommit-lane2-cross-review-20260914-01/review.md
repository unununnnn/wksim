# Lane 2 两份纠正 PASS 与原 FAIL 交叉复核

2026-09-14。只读
`cursor-postcommit-lane2-representative-matrix-20260914-01`（原 FAIL）、
`cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01`（纠正 PASS）、
`cursor-postcommit-lane2-representative-matrix-fast2-20260914-01`（影子 PASS）。
解析三份 `review.json`（`json.loads(..., strict=True)`）与关键 captures。
**未重跑 unittest / pytest。未 clone / native / 构建 / 飞行 / #83。**
**未改源回执。未 add / commit / push / reset / clean。**
写入仅在
`validation/coordination/cursor-postcommit-lane2-cross-review-20260914-01/{review.md,review.json,SHA256SUMS}`。

**本复核裁决：PASS。0 P1。3 P2。**
两份纠正回执均在 `FINAL_HEAD=59d8da51b4c31b6aa050929ebbe81ccc357acfb5` 上报告两机 A=`4/4/30/12/5`、B=`12`、tree=`5d1cbb9e0ca663d0f10f60d6b645b97b5998b256`、`autocrlf=false`；captures 计数与 `OK`/`rc=0` 一致。
empty-HEAD 六枚互不相同，均 `!= FINAL_HEAD`，回执均 `pushed=false`。
fast2 Ubuntu 捕获**不是**纠正重跑的同一份文件，但本卡片也**没有**对新 Ubuntu clone 重跑；不得写成独立复跑。
三份 SHA256SUMS：原 FAIL 无清单；纠正重跑 27/27；fast2 所列 2/2，captures 未列入。
原 FAIL 未改。

**最终权威（纠正 PASS）：** `cursor-postcommit-lane2-autocrlf-false-rerun-20260914-01`。
原 `representative-matrix` 仍是第一次运行的 **FAIL** 权威，不得改写成 PASS。
fast2 只作 Windows 换行路径的影子佐证，不能替代纠正重跑。

`claims_owner_approval=false`。不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。
`4/4/30/12/5` 不等于 53/153/179/721/45/81，也不是飞行验收。

## 派发

```text
工作类别：postcommit-lane2-cross-review
         （核查，非新开发、非新架构验收、非历史对照晋升）
规划仓 cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                         main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
SOURCE 祖先：6eafdf9c0b734db07a9fe790c86b409d3468c10b HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、三份源回执 review.json/md、
      纠正 SHA256SUMS、fast2 SHA256SUMS、关键 captures
module / interface：无产品代码变更
独占写入：本目录 review.md、review.json、SHA256SUMS
范围外：重跑测试；clone / native / 构建 / 飞行 / #83；
        改源回执；规划仓 git 变更；关闭 issue/gate
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本复核在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 绑定

| 符号 | 值 |
| --- | --- |
| `FINAL_HEAD` / 规划仓 HEAD / origin main（回执） | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| tree / `HEAD^{tree}` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` |
| `SOURCE_HEAD` | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| 架构祖先 | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` |
| 原 FAIL Windows empty | `b59660cf745e2015d949e1f94a713850aa33930f` |
| 原 FAIL Ubuntu empty | `83b53d7a005598b62225a4722d3c2f0d28404cbf` |
| 纠正 Windows empty | `ceb796310c2210ea93736dec7014033d45f2aad6` |
| 纠正 Ubuntu empty | `24800304ec20469cd787f9f64907fb01f1c45caa` |
| fast2 Windows empty | `7e4117ceec85abe052b77bee0bfe2894cf86ded1` |
| fast2 Ubuntu empty | `71c7d17aaa240edc33f24a6117ac32e6a554ab91` |

`HEAD != SOURCE_HEAD`。empty-HEAD 允许不同，且不得推送。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 三份 JSON 严格可解析 | **PASS** | 均 `json.loads(..., strict=True)`；FAIL 8410 B / 纠正 7185 B / fast2 9827 B |
| 三份 SHA256SUMS | **PASS（附范围）** | FAIL：**无清单**。纠正：27/27，无未列文件。fast2：所列 review.md/json 2/2 命中；40 份 captures 未列入 |
| 两份纠正 A 两机 4/4/30/12/5 | **PASS** | 纠正十份 `*.log` 与 fast2 最终 `win-A-*.txt` / `ubu-A-*.txt` 均为 Ran + OK；fast2 `*.rc` 均为 `0` |
| 两份纠正 B 两机 12 | **PASS** | 纠正 `*-pass-b.log` Ran 12 OK rc=0；fast2 `*-B-empty-nodes.txt` Ran 12 OK，`*.rc=0` |
| tree `5d1cbb9e…` | **PASS** | 三份 empty-head / JSON；规划仓 `HEAD^{tree}` 相同 |
| `FINAL_HEAD` `59d8da51…` | **PASS** | 三份 bind/identity；纠正 `origin-ls-remote`；本仓 HEAD |
| 纠正 `autocrlf=false` | **PASS** | 纠正 win/ubu bind 与 empty-head；fast2 最终 `win-lf-refresh` `AUTOCRLF_LOCAL=false` |
| empty SHA 可不同且未推送 | **PASS** | 六枚互异，均 `!= FINAL_HEAD`；纠正 `empty_heads_not_pushed=true`；fast2 `PUSHED=false` |
| fast2 Ubuntu 来源（不夸大） | **PASS** | 见下节；独立文件 ≠ 独立本轮复跑 |
| 原 FAIL 未改 | **PASS** | `review.json` SHA-256 `c94211fc…` 仍 FAIL；`windows/g1g5.log` 仍 `FAILED (failures=2)`；本路未写该目录 |
| 未跑测试 / 未改源回执 / 不关闸 | **PASS** | 本目录仅三份回执 |

失败门：无。

## 原 FAIL（权威：第一次运行）

`verdict=FAIL`。Windows `core.autocrlf=true`。Pass A：Ubuntu `4/4/30/12/5` 绿；Windows G1/G5 failures=2、budget failures=4。Pass B：Ubuntu 12 绿；Windows failures=2（同一 CRLF）。tree 已是 `5d1cbb9e…`。clone：`wksim-lane2-win-20260914-01` / `/root/wksim-lane2-ubu-20260914-01`。

现字节未改：`review.json` 8410 / `c94211fcb7449186ba93d1ac53064956929c870dd2feefef143b4a2ca1f2d97e`；`review.md` 6721 / `8a8d991e74b3fdb998ce9210b8ae8265bc6bce827a1f879d13ef1afc774be25f`。无 `SHA256SUMS`。

## 纠正重跑（最终权威 PASS）

同两棵 disposable clone，恢复到 `FINAL_HEAD`，`core.autocrlf=false`，Windows 经 `rm --cached` + 强制 checkout 重写 LF。两机实际重跑 A/B。

| 宿主 | A | B empty | tree | autocrlf | pushed |
| --- | --- | --- | --- | --- | --- |
| Ubuntu `/root/wksim-lane2-ubu-20260914-01` | 4/4/30/12/5 OK rc=0 | `24800304…` Ran 12 OK | `5d1cbb9e…` | false | false |
| Windows `…/wksim-lane2-win-20260914-01` | 4/4/30/12/5 OK rc=0 | `ceb79631…` Ran 12 OK | `5d1cbb9e…` | false | false |

`SHA256SUMS` 27/27。`original_receipt.overwritten=false`。origin ls-remote 仍 `59d8da51…`。

## fast2（影子，非最终权威）

本地 shared facade clone，**不是** origin clone。`from_origin=false`。Windows 先在系统 `autocrlf=true` 下 A 红（G1/G5 2、budget 4），LF 刷新后 A/B 绿。empty `7e4117ce…`，`PUSHED=false`。

Ubuntu：`pass_a/pass_b.reused_existing_captures=true`，`recloned=false`，`reran=false`。本卡片只核对本目录已有捕获，未再整仓 clone、未重跑。

相对纠正重跑的 Ubuntu 日志：g1g5/g3/budget/frame/B 哈希均不同；耗时亦不同（budget 13.278s vs 1.655s，frame 29.897s vs 2.47s）。clone 路径 `/root/wksim-lane2-fast2-ubu-20260914-01`，empty `71c7d17a…`。
`ubu-A-full.txt` 与原 FAIL `ubuntu/full.log` 字节相同（`f96363f8…`，`Ran 5 tests in 0.014s` + `OK`）。短输出可巧合撞哈希，**不能**据此说复用了原 FAIL 或纠正重跑。

结论：fast2 Ubuntu **文件不是**纠正重跑产物；fast2 **本轮也不是**独立 Ubuntu 复跑。不得写成“与纠正运行独立复证的 Ubuntu 新跑”。

`SHA256SUMS` 只列 `review.md` / `review.json`。

## P1 / P2

P1：无。

P2-NO-RERUN-TESTS：只解析回执。`fail_this_review=false`。
P2-FAST2-UBUNTU-REUSED-CAPTURES：Ubuntu 本卡片未重跑。`fail_this_review=false`。
P2-FAST2-SHA256SUMS-OMITS-CAPTURES：所列 2 条命中，captures 未覆盖。`fail_this_review=false`。

P3：原 FAIL 无 SHA256SUMS；纠正 review 文件含 CRLF 但按磁盘字节命中清单；fast2 非 origin clone；empty SHA 理应不同；代表集 ≠ 全量/飞行；不授权入库；不关闸。

## 哪份作为最终权威

| 问题 | 权威 |
| --- | --- |
| 第一次 Lane 2 代表矩阵结果 | 原 `representative-matrix-20260914-01` = **FAIL** |
| 关闭 autocrlf 后纠正是否绿 | **`autocrlf-false-rerun-20260914-01` = PASS** |
| Windows 换行红→绿是否再现 | fast2 可佐证，不能单独封口 |

选纠正重跑为最终权威，因为它与原 FAIL 共用隔离 clone、两机均实际重跑、origin 绑定、清单完整。fast2 的 Ubuntu 是既有捕获复用，且 clone 方法不同。

## 非声称

不关闭 issue/gate，不批准 owner 项，不授权 add/commit/push。
未运行测试。未改源回执。规划仓无 git 变更。本文件不是 commit。
不把 4/4/30/12/5 写成全量或飞行验收。不把 fast2 Ubuntu 写成独立复跑。
原 representative-matrix 保持 **FAIL**。

**PASS。**
