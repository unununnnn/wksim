# Lane 1 remote-chain 回执独立复核

2026-09-14。只读复核
`validation/coordination/cursor-postcommit-lane1-remote-chain-20260914-01/{review.md,review.json}`。
读 `lane1.txt` 原卡片与 `six-groups.json`。从当前 git 对象抽查父链、每组首尾路径、两处脏文件 blob。
只读查看源回执声称的 TEMP 检出，**未执行完整 clone、完整 176 SHA-256 重扫、pytest/unittest**。
**未改原回执。未 add / commit / push / reset / clean / rebase / force-push。**
写入仅在 `validation/coordination/cursor-postcommit-lane1-independent-review-20260914-01/{review.md,review.json}`。
本目录不留脚本。

**核心判断：不足以支持步骤 1–7 全绿 PASS。**
从已绑定 `FINAL_HEAD` 做本地独立 clone、再把 `origin` 指回 GitHub 并 `fetch`，可以支持步骤 1 的 tip 绑定，以及步骤 3–6、步骤 7 的对象层抽查；**不能**把卡片步骤 2 标成 PASS。
源回执写「0 P1；0 P2。步骤 1–7 全绿」过宽。

**本复核裁决：FAIL。** 1 条 P1（否决源 1–7 全绿）。2 条 P2（不单独改写对象层抽查）。

这不是 owner 批准。`claims_owner_approval=false`。不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。不改判 Lane 2 / Lane 3。

## 派发

```text
工作类别：postcommit-lane1-independent-review
         （非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、
      cursor-postcommit-three-lane-verification-plan-20260914-01/{plan.md,plan.json,lane1.txt}、
      cursor-final-176-six-commit-private-rehearsal-20260914-01/six-groups.json、
      cursor-postcommit-lane1-remote-chain-20260914-01/{review.md,review.json}
module / interface：无产品代码变更
独占写入：validation/coordination/cursor-postcommit-lane1-independent-review-20260914-01/review.md
         validation/coordination/cursor-postcommit-lane1-independent-review-20260914-01/review.json
依赖（只读）：Lane 1 两份回执；lane1.txt；six-groups.json；当前 git 对象；
            源声称 TEMP 检出（只读，未新建 clone）
验证：源 JSON 可解析；FINAL_HEAD 绑定；步骤 2 替代是否等于直接 origin clone；
      父链 A–F；每组首尾路径 + 名称集合；两脏文件 blob；
      声称 fresh clone 的 reflog / origin / FETCH_HEAD
范围外：完整 origin clone；完整 176 SHA-256 重扫；pytest/unittest；
        native / 构建 / 飞行 / #83；改原回执；主仓 git 变更；关闭 issue/gate
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本复核在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 绑定

| 符号 | 值 |
| --- | --- |
| 源回执与本工作区 `HEAD` / `<FINAL_HEAD>` / `<COMMIT_F>` | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| `<FINAL_TREE>` / `<TREE_F>` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` |
| `<SOURCE_HEAD>` | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| `<SOURCE_TREE>` | `435471df1371a0bec80d4b6013c3bc9cbc8af938` |
| 架构祖先退出码 | 0 |
| 源 `lane1_clone` | `C:/Users/PC/AppData/Local/Temp/wksim-lane1-fresh-20260914-01` |
| 源未完成 origin clone | `C:/Users/PC/AppData/Local/Temp/wksim-lane1-20260914-080259` |

未把演练 `afdc9b97…`–`9c950627…` 或 integration2 tree `317b98b8…` 当作 `FINAL_HEAD`。本工作区无这三枚对象。

## 步骤 2 替代是否足够

`lane1.txt` 步骤 2 原文是

`git clone --no-tags --single-branch --branch main https://github.com/unununnnn/wksim.git <LANE1_CLONE>`。

禁止 `--depth 1`，禁止把 planner 脏工作树当作 fresh checkout。

源回执承认：对该 URL 的整仓 clone（`…080259`）pack 仍为 0、HEAD 未建立，`origin_full_clone_completed=false`。
本路只读复核该目录：无工作树子项、无 pack、`.git/HEAD` 空、无 `FETCH_HEAD`。卡面指定的直接 origin clone **没有完成**。

实际检验目录 `…fresh-20260914-01` 的 reflog / `logs/refs/heads/main` 均为：

`clone: from C:\Users\PC\Documents\odid编译\wksim`

随后 `origin` 被设为 `https://github.com/unununnnn/wksim.git`，`FETCH_HEAD` 为
`59d8da51…    branch 'main' of https://github.com/unununnnn/wksim`。
非 shallow，无 alternates，`status --short` 空，`rev-list --count SOURCE..HEAD` = 6。
这是「本地物化后再指回 GitHub」，不是卡片指定的直接 origin clone。

该替代：

- **能支持**步骤 1 的 tip 身份：`FETCH_HEAD` 与源 `ls-remote` 均为 `59d8da51…`，且 ≠ `SOURCE_HEAD`。同一 SHA 内容寻址，父链与 tree 唯一。
- **能支持**步骤 3–6 的对象层抽查（见下）。在已有该 SHA 的本地对象上 `fetch` 可以不下载 pack，因此 **不能**把「对象来自 GitHub pack」写成已证明。
- **不能**把步骤 2 标 PASS。卡片步骤 2 是一条独立绿门，不是 P3 备注。源把它记为 P3 并仍写「步骤 2 PASS / 1–7 全绿 / 0 P1 0 P2」，本复核不接受。

`lane1.txt` 的 FAIL/STOP 列表写的是远端未前进、计数 ≠ 6、父链断、集合不等、脏文件入库、fresh tree 缺 176。
这些结果门可在本地对象上抽查；**结果门绿不能回填步骤 2 的程序门**。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 源 JSON 可解析 | **PASS** | `review.json` 9408 B；`review.md` 7021 B |
| `FINAL_HEAD` 绑定 | **PASS** | 源回执、本 `HEAD`、fresh clone `HEAD`/`FETCH_HEAD` 均为 `59d8da51…` |
| 步骤 1 tip ≠ `SOURCE_HEAD` | **PASS**（未重跑 `ls-remote`） | 本路以 fresh `FETCH_HEAD` 与源一行记录交叉；未新建网络 clone |
| 步骤 2 直接 origin clone | **FAIL** | 指定 clone 无 HEAD；检验目录 reflog 为本地路径 clone |
| 步骤 3 clone HEAD / 祖先 / 计数 | **PASS**（对象层） | 本仓与 fresh 均为 `59d8da51…` / `5d1cbb9e…` / `refs/heads/main`；两祖先退出码 0；计数 6 |
| 步骤 4 父链 A–F，无 merge | **PASS**（对象层） | `A^`=`SOURCE_HEAD`；其后每步一父；`FINAL_HEAD`=`COMMIT_F`；标题无禁止用语 |
| 步骤 5 六组集合 = 神谕 | **PASS**（名称集合） | 34/26/60/17/32/7；extra=missing=duplicate=[]；十五对交叉空 |
| G1 四依赖只在 A | **PASS** | 两枚 promotion-flight JSON + 两个 uncovered-offline helper 仅 A |
| G3 postrepair3 + docfix2 只在 B | **PASS** | B=13，其余组 0 |
| C 不含三份 frame 候选 | **PASS** | 三份只在 D |
| F 恰七条 integration2 且 F ∩ 169 空 | **PASS** | 7 条均在 `cursor-five-slice-final-integration2-20260914-01/` |
| 步骤 6 两脏文件未入库 | **PASS**（对象层） | 两段 `git log --oneline` 空；SOURCE/FINAL blob 仍为 `382f2c17…` / `0688c231…` |
| 步骤 7 首尾路径可见性 | **PASS**（抽查，非 176 重扫） | 六组 12 条 SOURCE `cat-file -e`=128，FINAL 为 `100644` blob；fresh index 同 |
| 源 1–7 全绿 / 0 P1 0 P2 | **FAIL** | 步骤 2 不能绿 |
| 未跑测试 / 未改原回执 / 不关闸 | **PASS** | 本目录仅两份回执；无脚本 |

失败门：步骤 2；源「1–7 全绿」。

## 抽查

父链（`git rev-list --reverse --format=%H/%P/%T`，`SOURCE_HEAD..HEAD`）：

| 步 | commit | 第一父 | tree | 标题 |
| --- | --- | --- | --- | --- |
| A | `14e474e4…` | `6eafdf9c…` | `4ec22999…` | Add G1/G5 offline-drift candidate and exact evidence |
| B | `f5509c35…` | `14e474e4…` | `0433687c…` | Add G3 exact-clearance candidate with postrepair3 and docfix2 |
| C | `bc0648dc…` | `f5509c35…` | `5c6b3ae2…` | Add G6 budget-approval-provenance candidate and exact evidence |
| D | `f30ebf0f…` | `bc0648dc…` | `fbdf039f…` | Add G6 frame-datum-binding candidate and exact evidence |
| E | `88349152…` | `f30ebf0f…` | `e5c98e40…` | Add Full original AC gap-ledger candidate and exact evidence |
| F | `59d8da51…` | `88349152…` | `5d1cbb9e…` | Add five-slice dual-order integration2 receipt |

每组恰好一父。`diff-tree` 名称集合与 `six-groups.json` 的 `paths[].path` 相等。
`diff-tree` 按路径排序，神谕按 ordinary∪force 列表序，故除 F 外首尾字符串不必相同；比较的是集合，不是序。

每组神谕首尾（存在性 / 类型，不是 SHA-256）：

| 组 | 神谕首 / 尾 | SOURCE `cat-file -e` | FINAL 类型 / mode |
| --- | --- | --- | --- |
| A | `validation/test_g1_g5_offline_drift.py` | 128 | blob `100644` |
| A | `…/cursor-g1-g5-final-private-stage-finalize-20260914-01/SHA256SUMS` | 128 | blob `100644` |
| B | `Simulator/wksim_planning/ego_exact_clearance.py` | 128 | blob `100644` |
| B | `…/cursor-g3-exact-precommit-audit-20260914-01/captures/prior-179-match.json` | 128 | blob `100644` |
| C | `docs/plan/59-e0-budget-approval-provenance-20260914.md` | 128 | blob `100644` |
| C | `…/cursor-g6-budget-related-source-final-review-20260914-01/SHA256SUMS` | 128 | blob `100644` |
| D | `docs/plan/59-e0-frame-datum-binding-20260914.md` | 128 | blob `100644` |
| D | `…/cursor-g6-frame-datum-precommit-audit-20260914-01/captures/prior-full-suite-recheck.json` | 128 | blob `100644` |
| E | `docs/plan/full-original-ac-gap-ledger-20260914.md` | 128 | blob `100644` |
| E | `…/cursor-full-frame-postcommit-sequence-20260914-01/captures/lin-full-then-frame-final-frame-12.txt` | 128 | blob `100644` |
| F | `…/cursor-five-slice-final-integration2-20260914-01/SHA256SUMS` | 128 | blob `100644` |
| F | `…/cursor-five-slice-final-integration2-20260914-01/sequence-matrix.json` | 128 | blob `100644` |

上述 12 条在 fresh clone 的 `HEAD:<path>` 与 `ls-files --stage` 同为 `100644` blob。
这不是 176 全覆盖证明。

脏文件：

| 路径 | SOURCE blob | FINAL blob | `git log --oneline SOURCE..FINAL` | planner 工作树 | fresh 工作树原始字节 |
| --- | --- | --- | --- | --- | --- |
| `docs/Prometheus.gitmodules.reference` | `382f2c17…`（480 B） | 同 | 空 | 492 B，与 checkout/CRLF 展开一致 | 492 B，过滤后仍钉 `382f2c17…` |
| `validation/coordination/short-cycle-dispatches.json` | `0688c231…`（1361 B） | 同 | 空 | 1268 B，≠ HEAD | 1361 B，原始 SHA-256 = HEAD |

fresh clone **未**携带 planner 的 1268 字节短周期脏文件。这支持步骤 7 的「不带 planner 脏字节」，不把步骤 2 补绿。

## P1 / P2

P1-STEP2-LOCAL-CLONE-NOT-ORIGIN：卡片步骤 2 要求直接 `clone` GitHub URL。指定目录 `…080259` 仍无 HEAD。检验目录 reflog 为从本机 `C:\Users\PC\Documents\odid编译\wksim` clone，再改 `origin` 并 `fetch`。content-addressing + `FETCH_HEAD` 不能把步骤 2 改写成 PASS，也不能支持源「步骤 1–7 全绿」。本条否决源总体 PASS。

P2-ORIGIN-CLONE-STILL-HEADLESS：`…080259` 现仍无 pack / HEAD / `FETCH_HEAD`，不能事后冒充已完成的步骤 2。不改变上面对象层抽查。

P2-NO-176-SHA256-AND-NO-LSREMOTE-RERUN：本路按任务未做完整 176 重扫、未重跑 `ls-remote`、未跑测试。步骤 7 只抽查每组首尾 12 条。不否决对象层抽查，也不给源 1–7 全绿补票。

P3：C 标题含 `budget-approval-provenance` 是候选名；本复核不在 176；不授权入库；不关闸。

## 仍需什么证据

要把步骤 1–7 标成全绿，还缺至少一项：

1. 按 `lane1.txt` 完成
   `git clone --no-tags --single-branch --branch main https://github.com/unununnnn/wksim.git <新目录>`，
   且该目录 `HEAD` 建立为 `59d8da51…`，`symbolic-ref` 为 `refs/heads/main`，不是 `--depth 1`，不是 planner 脏树；或
2. owner 另写书面接受：「本地路径 clone + 改 origin + `ls-remote`/`fetch` tip 绑定」等价于步骤 2。
   本复核不代写该接受。

仅有当前本地对象抽查、仅有 `FETCH_HEAD`、仅有未完成的 `…080259`，不够。
完整 176 SHA-256 与秘密扫描仍归 Lane 3，不在本路补做。

## 非声称

不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full，不批准 owner 项，
不改判 Lane 2 / Lane 3，不授权 add / commit / push，不把本路写成代表测试或飞行验收。
未运行测试。未完整 clone。未 176 SHA-256 重扫。未改原回执。主仓无 git 变更。本文件不是 commit。

**FAIL。**
