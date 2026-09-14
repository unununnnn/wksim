# Lane 1 远端六提交链（快速路径）

2026-09-14。执行
`validation/coordination/cursor-postcommit-three-lane-verification-plan-20260914-01/lane1.txt`。
用户绑定 ACTUAL：`FINAL_HEAD` / A–F。
独立 `ls-remote` + 从 `origin` 新建 `main` checkout。
`git clone --reference-if-able` 因主仓为浅克隆被拒绝，改用 `--filter=blob:none --no-checkout`。
**未运行 pytest/unittest。未重算 176 SHA-256。未做秘密扫描。未跑 native / 构建 / 飞行 / #83。**
**未改主仓现有文件。未 add / commit / push / reset / clean / rebase / force-push。不关闭任何 issue / gate。**
写入仅在
`validation/coordination/cursor-postcommit-lane1-remote-chain-fast-20260914-01/{review.md,review.json}`。
本目录不留脚本。

**裁决：PASS。** 步骤 1–7 全绿。绑定 SHA 与独立 clone 观察值一致。
`claims_owner_approval=false`。不关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。

## 派发

```text
工作类别：postcommit-lane1-remote-chain-fast
         （核查，非新开发、非新架构验收、非历史对照晋升）
规划仓 cwd / 分支 / HEAD：C:/Users/PC/Documents/odid编译/wksim
                         main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
clone cwd：C:/Users/PC/AppData/Local/Temp/wksim-lane1-fast-20260914-01-blobnone
           main / 59d8da51b4c31b6aa050929ebbe81ccc357acfb5
HEAD tree：5d1cbb9e0ca663d0f10f60d6b645b97b5998b256
架构祖先：git merge-base --is-ancestor
          f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD -> 退出码 0
SOURCE 祖先：6eafdf9c0b734db07a9fe790c86b409d3468c10b HEAD -> 退出码 0
已读：AGENTS.md、architecture-implementation-20260912.md、
      architecture-continuation-20260913.md、lane1.txt
module / interface：无产品代码变更
独占写入：本目录 review.md、review.json
依赖（只读）：six-groups.json 路径神谕；origin refs/heads/main
验证：独立 ls-remote；独立 origin clone；父链；六组 diff-tree；
      脏文件排除；fresh 176 可见
范围外：pytest/unittest；176 SHA-256；秘密扫描；native / 构建 / 飞行 / #83；
        主仓 add/commit/push；关闭 issue/gate
```

子代理策略要求的 `gpt-5.6-luna` / `gpt-6-astra` 不在本界面可选模型列表中。
本核查在主代理内完成，没有改用其他子代理模型顶替，也没有派发子代理。

## 绑定

用户给出的 ACTUAL 与 clone `rev-list --reverse` 观察值逐字相同。

| 符号 | ACTUAL / 观察值 |
| --- | --- |
| `<SOURCE_HEAD>` | `6eafdf9c0b734db07a9fe790c86b409d3468c10b` |
| `<SOURCE_TREE>` | `435471df1371a0bec80d4b6013c3bc9cbc8af938` |
| `<FINAL_HEAD>` = `<COMMIT_F>` | `59d8da51b4c31b6aa050929ebbe81ccc357acfb5` |
| `<FINAL_TREE>` = `<TREE_F>` | `5d1cbb9e0ca663d0f10f60d6b645b97b5998b256` |
| `<COMMIT_A>` / `<TREE_A>` | `14e474e47e1ee1c114d423870a034fbf2cb26e76` / `4ec2299950d72f0ce1f31cdba08c6afb468f9843` |
| `<COMMIT_B>` / `<TREE_B>` | `f5509c35db8fc62c5722fb55a29299cb60ff4f4a` / `0433687ca8a2f551b376a7728013fe3d1e4d239b` |
| `<COMMIT_C>` / `<TREE_C>` | `bc0648dcff8c1a4c2de55e6de67b30f2f524c457` / `5c6b3ae2430acc276f9ce73698a8ac6947f960b1` |
| `<COMMIT_D>` / `<TREE_D>` | `f30ebf0f116b75c56802375702eaa1b2cbc3beba` / `fbdf039f046e02a5b5d7e19d840dc525448ba0cf` |
| `<COMMIT_E>` / `<TREE_E>` | `88349152a30d29ca95ec92364c4228c2a37d617b` / `e5c98e40eb151d3054ae67fba0b1fe160809e569` |

未使用演练 commit-tree `afdc9b97…9c950627`。未把 integration2 tree `317b98b8` 当作 176 树。

## 步骤

| 步 | 门 | 裁决 | 证据 |
| --- | --- | --- | --- |
| 1 | 独立 `ls-remote` | **PASS** | 规划仓与 clone 各一次；恰好一行 `59d8da51…	refs/heads/main`；≠ `SOURCE_HEAD` |
| 2 | 独立 origin clone | **PASS** | `--no-tags --single-branch --branch main`；无 `--depth 1`；未用脏主工作树 |
| 3 | HEAD / 祖先 / 计数 | **PASS** | `HEAD=FINAL_HEAD`；`symbolic-ref=refs/heads/main`；两祖先退出码 0；`rev-list --count=6` |
| 4 | 父链 | **PASS** | `A^=SOURCE`；其后第一父即前一提交；无 merge；`F=FINAL_HEAD` |
| 5 | 六组路径 + 附加门 | **PASS** | 34/26/60/17/32/7；extra=missing=duplicate=[]；全部 `100644` blob |
| 6 | 两处脏文件排除 | **PASS** | 两段 `git log` 空；FINAL blob 仍为 SOURCE blob |
| 7 | fresh 176 | **PASS** | SOURCE 176 条 `cat-file -e` 均缺失；FINAL `ls-tree`/`rev-parse`/`ls-files --stage` 176 条均为 blob / `100644` |
|  | 本路总体 | **PASS** | 0 P1 |

失败门：无。

## 快速路径

1. `git clone --reference-if-able <规划仓>`：`reference repository is shallow`，未写入 `alternates`。
2. 带工作树的 `blob:none` clone 在拉取 HEAD blob 时卡住；按卡片改用 `blob:none`，并加 `--no-checkout`，再用 `git read-tree HEAD` 填索引。
3. clone 仍从 `https://github.com/unununnnn/wksim.git` 建立，且单独 `ls-remote`。

## 父链与标题

第一父链：`SOURCE → A → B → C → D → E → F`。每步一个父，无 merge。

| 组 | 标题 | 禁止词 |
| --- | --- | --- |
| A | Add G1/G5 offline-drift candidate and exact evidence | 无 |
| B | Add G3 exact-clearance candidate with postrepair3 and docfix2 | 无 |
| C | Add G6 budget-approval-provenance candidate and exact evidence | 无（候选名，不是批准） |
| D | Add G6 frame-datum-binding candidate and exact evidence | 无 |
| E | Add Full original AC gap-ledger candidate and exact evidence | 无 |
| F | Add five-slice dual-order integration2 receipt | 无 |

标题不含 `owner approval` / `closes` / `close gate` / `gate closed`。

## 附加语义

- 十五对交叉空。
- G1 四依赖只在 A。
- G3 postrepair3 + docfix2 只在 B（13 条路径）。
- C 不含三份 frame 候选。
- F 恰好七条 `cursor-five-slice-final-integration2-20260914-01` 终稿；F ∩ 169 = ∅。

## 脏文件

| 路径 | SOURCE / FINAL blob | 规划仓工作树 blob | clone 工作树 |
| --- | --- | --- | --- |
| `docs/Prometheus.gitmodules.reference` | `382f2c17feacc6c08af9db7c58b20cd1f76b7ea2` | `dc0a843a279ee1b3ddea4facd6b5a3457951a882` | 不存在 |
| `validation/coordination/short-cycle-dispatches.json` | `0688c231349cbdb32701495538d45c34252f6817` | `cc7c4dcb2e3c1de6f613a4b260f7d76722891eb1` | 不存在 |

两路径未进入任一 `diff-tree`。clone 未携带规划宿主脏字节。

## 未做 / 未宣称

未关闭 #39 / #102 / #59 / #10 / #60 / G1 / G5 / G3 / G6 / Full。
这不是 owner 批准。`claims_owner_approval=false`。
输出目录只有 `review.md` 与 `review.json`。
