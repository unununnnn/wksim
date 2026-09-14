# Lane 1 fast 回执独立复核

2026-09-14。只读复核
`validation/coordination/cursor-postcommit-lane1-remote-chain-fast-20260914-01/{review.md,review.json}`。
读 `lane1.txt` 与 `six-groups.json`。从回执记录的临时 clone
`C:/Users/PC/AppData/Local/Temp/wksim-lane1-fast-20260914-01-blobnone`
读取 reflog / config / origin / promisor / shallow / symbolic-ref / HEAD。
独立 `ls-remote`。对六组首尾路径、G1 四依赖、G3 docfix2/postrepair3、F 七文件做
`cat-file` type / 可读 blob 抽查；缺失惰性 blob 从 GitHub 取回。
**未重扫 176 SHA-256。未运行 pytest/unittest / native / 构建 / 飞行 / #83。**
**未改源回执。未 add / commit / push / reset / clean / rebase / force-push。**
写入仅在
`validation/coordination/cursor-postcommit-lane1-fast-independent-review-20260914-01/{review.md,review.json}`。
本目录不留脚本。

**本复核裁决：PASS。0 P1。1 P2。**
源回执的 GitHub direct clone **确实**是 `blob:none --no-checkout`，不是 `--depth 1`、不是本地路径 clone、不是规划仓脏工作树。
**可作为 Lane 1 权威 PASS。**
先前
`cursor-postcommit-lane1-independent-review-20260914-01`
对非 fast 回执的 FAIL 仍只约束那份本地 clone 回执，不约束本 fast 回执。

这不是 owner 批准。`claims_owner_approval=false`。
不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。不改判 Lane 2 / Lane 3。

## 派发

```text
工作类别：postcommit-lane1-fast-independent-review
         （核查，非新开发、非新架构验收、非历史对照晋升）
规划仓 cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                         main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、lane1.txt、six-groups.json、
      cursor-postcommit-lane1-remote-chain-fast-20260914-01/{review.md,review.json}
module / interface：无产品代码变更
独占写入：本目录 review.md、review.json
依赖（只读）：源 fast 回执；lane1.txt；six-groups.json；
            回执 TEMP clone（抽查时惰性取回 12 个缺失 blob）
验证：独立 ls-remote；clone reflog/config/promisor/shallow/HEAD；
      六组首尾 + G1 四依赖 + G3 13 条 + F 七文件 cat-file；
      父链与 diff-tree 名称集合
范围外：完整 176 SHA-256；pytest/unittest；native / 构建 / 飞行 / #83；
        改源回执；规划仓 git 变更；关闭 issue/gate
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本复核在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 绑定

| 符号 | 值 |
| --- | --- |
| 独立 `ls-remote` `refs/heads/main` | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| 源回执 / 规划仓 / clone `HEAD` / `<FINAL_HEAD>` / `<COMMIT_F>` | 同上 |
| `<FINAL_TREE>` / `<TREE_F>` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` |
| `<SOURCE_HEAD>` | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| `<SOURCE_TREE>` | `435471df1371a0bec80d4b6013c3bc9cbc8af938` |
| 架构祖先退出码 | 0 |
| 源 `clone_cwd` | `C:/Users/PC/AppData/Local/Temp/wksim-lane1-fast-20260914-01-blobnone` |

未把演练 `afdc9b97…`–`9c950627…` 或 integration2 tree `317b98b8…` 当作 `FINAL_HEAD`。

## 步骤 2：是否 GitHub `blob:none --no-checkout`

`lane1.txt` 步骤 2 原文是

`git clone --no-tags --single-branch --branch main https://github.com/unununnnn/wksim.git <LANE1_CLONE>`。

禁止 `--depth 1`，禁止把 planner 脏工作树当作 fresh checkout。
源 fast 回执在 `reference-if-able` 因浅克隆被拒后，改用 `--filter=blob:none --no-checkout`。

本路在记录的 TEMP clone 上读到：

| 项 | 观察 |
| --- | --- |
| reflog / `logs/refs/heads/main` | `clone: from https://github.com/unununnnn/wksim.git` → `59d8da51…` |
| `remote.origin.url` | `https://github.com/unununnnn/wksim.git` |
| `remote.origin.promisor` | `true` |
| `remote.origin.partialclonefilter` | `blob:none` |
| `remote.origin.tagOpt` | `--no-tags` |
| `remote.origin.fetch` | `+refs/heads/main:refs/remotes/origin/main` |
| `.git/shallow` | 不存在；`rev-parse --is-shallow-repository=false` |
| `objects/info/alternates` | 不存在 |
| 工作树 | 仅 `.git`，无检出文件 |
| `HEAD` / `symbolic-ref` | `59d8da51…` / `refs/heads/main` |
| 规划仓两处脏工作树 blob | `dc0a843a…` / `cc7c4dcb…`；clone 工作树无这两路径 |

这不是本地路径 clone（对比非 fast 回执 reflog `clone: from C:\Users\PC\Documents\odid编译\wksim`）。
这不是 `--depth 1`。这不是规划仓脏工作树。
`lane1.txt` 正文仍写无 filter 的 clone 命令，但 FORBIDDEN 列表只禁 depth 1 与脏树；本复核按本次任务核验 `blob:none --no-checkout`，接受该快路径满足步骤 2 的 origin 程序门。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 源 JSON 可解析 | **PASS** | `review.json` 8097 B；`review.md` 6679 B |
| 独立 `ls-remote` | **PASS** | 恰好一行 `59d8da51…	refs/heads/main`；≠ `SOURCE_HEAD` |
| 步骤 2 GitHub `blob:none --no-checkout` | **PASS** | 上表；非 depth 1 / 非本地 clone / 非脏树 |
| 步骤 3 HEAD / 祖先 / 计数 | **PASS** | clone `HEAD=59d8da51…` / tree `5d1cbb9e…` / `refs/heads/main`；两祖先退出码 0；`rev-list --count=6` |
| 步骤 4 父链 A–F，无 merge | **PASS** | `A^=SOURCE`；其后每步一父；`FINAL_HEAD=COMMIT_F`；标题无禁止用语 |
| 步骤 5 六组集合 = 神谕 | **PASS** | 34/26/60/17/32/7；extra=missing=duplicate=[] |
| G1 四依赖只在 A | **PASS** | 两枚 promotion-flight JSON + 两个 uncovered-offline helper |
| G3 postrepair3 + docfix2 只在 B | **PASS** | 13 条，其余组 0 |
| C 不含三份 frame 候选 | **PASS** | 三份只在 D |
| F 恰七条 integration2 且 F ∩ 169 空 | **PASS** | 7 条均在 `cursor-five-slice-final-integration2-20260914-01/` |
| 步骤 6 两脏文件未入库 | **PASS** | 两段 `git log --oneline` 空；SOURCE/FINAL blob 仍为 `382f2c17…` / `0688c231…`；clone 工作树不存在 |
| 指定路径 type / 可读 blob | **PASS** | 34/34 为 `100644` blob；SOURCE `cat-file -e`=128；12 条本路惰性取回 |
| 源 1–7 全绿可作为 Lane 1 权威 | **PASS** | 步骤 2 程序门成立；对象层与抽查绿 |
| 未跑测试 / 未改源回执 / 不关闸 | **PASS** | 本目录仅两份回执；无脚本 |

失败门：无。

## 父链

`git rev-list --reverse --format=%H/%P/%T/%s`，clone 上 `SOURCE_HEAD..HEAD`：

| 步 | commit | 第一父 | tree | 标题 |
| --- | --- | --- | --- | --- |
| A | `14e474e4…` | `6eafdf9c…` | `4ec22999…` | Add G1/G5 offline-drift candidate and exact evidence |
| B | `f5509c35…` | `14e474e4…` | `0433687c…` | Add G3 exact-clearance candidate with postrepair3 and docfix2 |
| C | `bc0648dc…` | `f5509c35…` | `5c6b3ae2…` | Add G6 budget-approval-provenance candidate and exact evidence |
| D | `f30ebf0f…` | `bc0648dc…` | `fbdf039f…` | Add G6 frame-datum-binding candidate and exact evidence |
| E | `88349152…` | `f30ebf0f…` | `e5c98e40…` | Add Full original AC gap-ledger candidate and exact evidence |
| F | `59d8da51…` | `88349152…` | `5d1cbb9e…` | Add five-slice dual-order integration2 receipt |

每步恰好一父。`diff-tree` 名称集合与神谕 `paths[].path` 相等。

## 抽查

`GIT_NO_LAZY_FETCH=1` 先判断本地是否已有 blob，再允许从 origin 取回。
SOURCE 侧 34 条 `cat-file -e` 均为 128。FINAL 均为 `blob` / `100644`，内容可读。

六组神谕首尾：

| 组 | 角色 | 路径 | 本地先有 | 本路取回 | 字节 |
| --- | --- | --- | --- | --- | --- |
| A | first | `validation/test_g1_g5_offline_drift.py` | 是 | 否 | 42074 |
| A | last | `…/cursor-g1-g5-final-private-stage-finalize-20260914-01/SHA256SUMS` | 是 | 否 | 411 |
| B | first | `Simulator/wksim_planning/ego_exact_clearance.py` | 是 | 否 | 38854 |
| B | last | `…/cursor-g3-exact-precommit-audit-20260914-01/captures/prior-179-match.json` | 是 | 否 | 1802 |
| C | first | `docs/plan/59-e0-budget-approval-provenance-20260914.md` | 是 | 否 | 21203 |
| C | last | `…/cursor-g6-budget-related-source-final-review-20260914-01/SHA256SUMS` | 否 | 是 | 423 |
| D | first | `docs/plan/59-e0-frame-datum-binding-20260914.md` | 否 | 是 | 15449 |
| D | last | `…/cursor-g6-frame-datum-precommit-audit-20260914-01/captures/prior-full-suite-recheck.json` | 否 | 是 | 6073 |
| E | first | `docs/plan/full-original-ac-gap-ledger-20260914.md` | 否 | 是 | 25570 |
| E | last | `…/cursor-full-frame-postcommit-sequence-20260914-01/captures/lin-full-then-frame-final-frame-12.txt` | 否 | 是 | 128 |
| F | first | `…/cursor-five-slice-final-integration2-20260914-01/SHA256SUMS` | 否 | 是 | 513 |
| F | last | `…/cursor-five-slice-final-integration2-20260914-01/sequence-matrix.json` | 否 | 是 | 41406 |

G1 四依赖（仅 A，均已在 clone 本地可读）：`flight-audit.json` 7005 B；`flown-source/manifest.json` 12309 B；`stdlib_identity_plugin.py` 3373 B；`isolation_after_g1g5.py` 2067 B。

G3 `postrepair3` 9 条 + `docfix2` 4 条 = 13，均已在 clone 本地可读。

F 其余五文件本路惰性取回后可读：`candidate-hashes.json` 9973 B；`dependency-check.json` 2547 B；`durable-evidence-manifest.txt` 6061 B；`review.json` 1533 B；`review.md` 13497 B。

合计 34 条唯一路径；12 条取回前本地缺失，`git cat-file -t/-s/blob` 从 `https://github.com/unununnnn/wksim.git` 取回后均为可读 blob。
这证明缺失惰性 blob 可从 GitHub 取回，不是 176 SHA-256 重扫。

clone 索引经 `read-tree HEAD` 有 10546 条（全树），工作树空。源回执 `index_stage_100644=176` 指 176 条神谕路径均为 `100644`，不是索引只有 176 条。

## P1 / P2

P1：无。

P2-NO-176-SHA256-RESCAN：本路按任务未重扫 176 SHA-256，未跑测试 / native / 构建 / 飞行 / #83。步骤 7 只抽查上述 34 条。不否决源 1–7 全绿，也不把本路写成 Lane 3。

P3：`lane1.txt` 正文仍写无 filter 的 clone 命令；C 标题 `budget-approval-provenance` 是候选名；本复核不在 176；不授权入库；不关闸；本路向 TEMP clone 惰性取回了 12 个 blob，未改规划仓 git 或源回执。

## 权威性

**可以作为 Lane 1 权威 PASS。**

依据：独立 `ls-remote` 与 clone HEAD 均为 `59d8da51…`；clone reflog/config 证明 GitHub `blob:none --no-checkout`；父链、六组名称集合、脏文件排除与指定路径可读 blob 抽查成立；缺失惰性 blob 可从 GitHub 取回。

非 fast 回执
`cursor-postcommit-lane1-remote-chain-20260914-01`
仍不能当权威（本地 clone）。本 fast 回执取代它作为 Lane 1 权威，不改判 Lane 2 / Lane 3。

## 非声称

不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full，不批准 owner 项，
不授权 add / commit / push，不把本路写成代表测试或飞行验收。
未运行测试。未 176 SHA-256 重扫。未改源回执。规划仓无 git 变更。本文件不是 commit。

**PASS。可作为 Lane 1 权威 PASS。**
