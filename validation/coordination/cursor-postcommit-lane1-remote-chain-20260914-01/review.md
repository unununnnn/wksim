# Lane 1 — 远端 main 六提交链 / 路径集合 / 父链 / 脏文件排除 / fresh checkout

2026-09-14。按
`cursor-postcommit-three-lane-verification-plan-20260914-01`
执行 Lane 1。写入仅在
`validation/coordination/cursor-postcommit-lane1-remote-chain-20260914-01/**`。
**未运行 pytest/unittest。未重算 176 SHA-256。未做秘密扫描。**
**未改主仓 git index 或 refs。未 add / commit / push / reset / clean / rebase / force-push。不留脚本。**

**裁决：PASS。** 0 P1；0 P2。步骤 1–7 全绿。

这不是 owner 批准，也不关闭任何 issue / gate / G1 / G5 / G3 / G6 / Full。
本卡不授权 add / commit / push。

## 派发

```text
工作类别：postcommit-lane1-remote-chain-verification
         （非新架构验收、非历史对照、非晋升、非入库）
cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                   main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、
      cursor-postcommit-three-lane-verification-plan-20260914-01、
      cursor-final-176-six-commit-private-rehearsal-20260914-01/six-groups.json
module / interface：无产品代码变更
独占写入：validation/coordination/cursor-postcommit-lane1-remote-chain-20260914-01/**
依赖（只读）：远端 origin/main；six-groups.json 路径神谕
验证：ls-remote；独立 fresh checkout；六提交父链；
      六组 diff-tree 集合；两处无关脏文件排除；176 可见性
范围外：pytest/unittest；176 SHA-256 重算；秘密扫描；
        主仓 add/commit/push/reset/clean/rebase/force-push；
        关闭 issue/gate；native / 构建 / 飞行 / #83
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本路在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 绑定

| 符号 | SHA |
| --- | --- |
| `SOURCE_HEAD` | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| `SOURCE_TREE` | `435471df1371a0bec80d4b6013c3bc9cbc8af938` |
| `ARCHITECTURE_ANCESTOR` | `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` |
| `FINAL_HEAD` = `COMMIT_F` | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| `FINAL_TREE` = `TREE_F` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` |
| `COMMIT_A` / `TREE_A` | `14e474e47e1ee1c114d423870a034fbf2cb26e76` / `4ec2299950d72f0ce1f31cdba08c6afb468f9843` |
| `COMMIT_B` / `TREE_B` | `f5509c35db8fc62c5722fb55a29299cb60ff4f4a` / `0433687ca8a2f551b376a7728013fe3d1e4d239b` |
| `COMMIT_C` / `TREE_C` | `bc0648dcff8c1a4c2de55e6de67b30f2f524c457` / `5c6b3ae2430acc276f9ce73698a8ac6947f960b1` |
| `COMMIT_D` / `TREE_D` | `f30ebf0f116b75c56802375702eaa1b2cbc3beba` / `fbdf039f046e02a5b5d7e19d840dc525448ba0cf` |
| `COMMIT_E` / `TREE_E` | `88349152a30d29ca95ec92364c4228c2a37d617b` / `e5c98e40eb151d3054ae67fba0b1fe160809e569` |

未把演练 `afdc9b97…`–`9c950627…` 当作 `FINAL_HEAD`。
未把 integration2 十八文件 tree `317b98b8…` 当作 176 tree。

## 门

| 门 | 裁决 | 证据 |
| --- | --- | --- |
| 1. `ls-remote` 一行、40 hex、`FINAL_HEAD` ≠ `SOURCE_HEAD` | **PASS** | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5	refs/heads/main` |
| 2. 独立 fresh checkout，不是脏主工作树，不是 `--depth 1` | **PASS** | 检出 `C:/Users/PC/AppData/Local/Temp/wksim-lane1-fresh-20260914-01`；`git status --short` 空；clone 内 `git fetch origin main` 得同一 `FETCH_HEAD` |
| 3. clone `HEAD` / 祖先 / 计数 | **PASS** | `HEAD`=`59d8da51…`；`HEAD^{tree}`=`5d1cbb9e…`；`symbolic-ref`=`refs/heads/main`；`SOURCE_HEAD` 与 `f333316` 祖先退出码 0；`rev-list --count` = 6 |
| 4. 父链 A–F，无 merge，`FINAL_HEAD`=`COMMIT_F` | **PASS** | `COMMIT_A^`=`SOURCE_HEAD`；其后每步第一父为前一步；六步各一父 |
| 5. 六组 `diff-tree` 集合 = `six-groups.json` | **PASS** | A34 B26 C60 D17 E32 F7；extra=missing=duplicate=[]；全部 `100644` blob |
| 十五对交叉空 | **PASS** | A∩B…E∩F 均为 [] |
| G1 四依赖只在 A | **PASS** | 两枚 promotion-flight JSON + 两个 uncovered-offline helper |
| G3 postrepair3 + docfix2 只在 B | **PASS** | B 内 13 条，其余组 0 |
| C 不含三份 frame 候选 | **PASS** | 三份只在 D |
| F 恰为 integration2 七文件，且 F ∩ 169 空 | **PASS** | 169=A∪B∪C∪D∪E |
| 标题无禁止用语 | **PASS** | 无 `owner approval` / `closes` / `close gate` / `gate closed`。C 的 `budget-approval-provenance` 是候选名 |
| 6. 两处无关脏文件未入库 | **PASS** | 两段 `git log --oneline` 为空；FINAL blob 仍为 `382f2c17…` 与 `0688c231…` |
| 7. 176 在 SOURCE 不存在、在 FINAL 为 blob，且 ls-tree 全覆盖 | **PASS** | 176/176；fresh clone 未携带 planner 的 `short-cycle-dispatches.json` 脏字节 |
| 未改主仓 git / 未跑测试 / 未关闸 | **PASS** | 主仓仍为既有脏工作树；本目录只写 review 两件 |

失败门：无。

## 检出说明

按卡面启动了
`git clone --no-tags --single-branch --branch main https://github.com/unununnnn/wksim.git`
到 `%TEMP%\wksim-lane1-20260914-080259`。该整仓传输与 Lane 2 并行，执行期间 pack 仍为 0 字节、HEAD 未建立。

检验用独立目录 `%TEMP%\wksim-lane1-fresh-20260914-01`：不是 planner 脏工作树，不是 `--depth 1`，`status` 干净。先用 `ls-remote` 绑定远端 `main`，再在该 clone 内把 `origin` 设为
`https://github.com/unununnnn/wksim.git` 并 `git fetch --no-tags origin refs/heads/main`，
`FETCH_HEAD` = `59d8da51…`。步骤 3–7 都在这个 disposable checkout 上执行。这记为 P3，不否决。

## 六组标题（只核语义）

1. Add G1/G5 offline-drift candidate and exact evidence
2. Add G3 exact-clearance candidate with postrepair3 and docfix2
3. Add G6 budget-approval-provenance candidate and exact evidence
4. Add G6 frame-datum-binding candidate and exact evidence
5. Add Full original AC gap-ledger candidate and exact evidence
6. Add five-slice dual-order integration2 receipt

## 脏文件

| 路径 | SOURCE / FINAL blob | 六提交 log | fresh clone |
| --- | --- | --- | --- |
| `docs/Prometheus.gitmodules.reference` | `382f2c17feacc6c08af9db7c58b20cd1f76b7ea2` | 空 | 与 SOURCE blob 一致 |
| `validation/coordination/short-cycle-dispatches.json` | `0688c231349cbdb32701495538d45c34252f6817` | 空 | 工作树字节 ≠ planner 脏文件（1268 vs 1361） |

## 明确未做

- 主仓 `git add` / `commit` / `push` / `reset` / `clean` / `rebase` / `force-push`
- pytest / unittest（Lane 2）
- 176 SHA-256 重算与秘密扫描（Lane 3）
- native / 构建 / 飞行 / #83
- 关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full
